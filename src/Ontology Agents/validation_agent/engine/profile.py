"""Measure what the submission is: counts, spectrum level, OWL 2 profiles, expressivity.

The measured profile plans the run (which ``applies`` profiles hold) and feeds the policy:
waivers are keyed on the *measured* level, never on what the publisher declares
(SPECIFICATION.md s.6.2).

The spectrum classifier places an artefact on the formality spectrum
controlled-vocabulary -> taxonomy -> thesaurus -> formal-ontology. The rule is cumulative:
structure first (subsumption), then associative relations, then logic. An artefact reaches
``formal-ontology`` only when it carries axioms a reasoner can act on beyond subsumption.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from . import vocab as V

SPECTRUM = ("controlled-vocabulary", "taxonomy", "thesaurus", "formal-ontology")
DECLARABLE_LEVELS = SPECTRUM


def spectrum_rank(level: str | None) -> int:
    return SPECTRUM.index(level) if level in SPECTRUM else -1


CHARACTERISTICS = (OWL.TransitiveProperty, OWL.SymmetricProperty, OWL.AsymmetricProperty,
                   OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
                   OWL.ReflexiveProperty, OWL.IrreflexiveProperty)


def metrics(g: Graph) -> dict[str, int | float]:
    classes = V.declared_classes(g)
    restrictions = set(g.subjects(RDF.type, OWL.Restriction)) | set(g.subjects(OWL.onProperty, None))
    count = lambda p: sum(1 for _ in g.triples((None, p, None)))  # noqa: E731
    disjoint = count(OWL.disjointWith) + sum(1 for _ in g.subjects(RDF.type, OWL.AllDisjointClasses)) \
        + count(OWL.disjointUnionOf)
    characteristics = sum(1 for c in CHARACTERISTICS for _ in g.subjects(RDF.type, c))
    skos_rel = sum(count(p) for p in (SKOS.broader, SKOS.narrower, SKOS.related,
                                       SKOS.closeMatch, SKOS.exactMatch, SKOS.broadMatch,
                                       SKOS.narrowMatch, SKOS.relatedMatch))
    labels = sum(count(p) for p in V.LABEL_PROPERTIES)
    logical = (count(RDFS.subClassOf) + disjoint + count(OWL.equivalentClass) + len(restrictions)
               + count(RDFS.domain) + count(RDFS.range) + characteristics
               + count(RDFS.subPropertyOf) + count(OWL.inverseOf))
    return {
        "triples": len(g),
        "classes": len(classes),
        "object_properties": len(V.object_properties(g)),
        "datatype_properties": len(V.datatype_properties(g)),
        "annotation_properties": len(set(g.subjects(RDF.type, OWL.AnnotationProperty))),
        "individuals": len(V.individuals(g)),
        "skos_concepts": len(set(g.subjects(RDF.type, SKOS.Concept))),
        "subclass_axioms": count(RDFS.subClassOf),
        "equivalence_axioms": count(OWL.equivalentClass),
        "disjointness_axioms": disjoint,
        "restrictions": len(restrictions),
        "domain_axioms": count(RDFS.domain),
        "range_axioms": count(RDFS.range),
        "property_characteristics": characteristics,
        "skos_relations": skos_rel,
        "labels": labels,
        "logical_axioms": logical,
        "axiom_richness": round(logical / len(classes), 3) if classes else 0.0,
    }


def classify_spectrum(g: Graph, m: dict | None = None) -> dict:
    m = m or metrics(g)
    evidence: list[str] = []
    level = "controlled-vocabulary"
    if m["labels"] or m["classes"] or m["skos_concepts"]:
        evidence.append(f"{m['classes']} classes, {m['skos_concepts']} SKOS concepts, "
                        f"{m['labels']} labels: named terms exist")
    broader = sum(1 for _ in g.triples((None, SKOS.broader, None))) + \
        sum(1 for _ in g.triples((None, SKOS.narrower, None)))
    has_hierarchy = m["subclass_axioms"] > 0 or broader > 0
    if has_hierarchy:
        level = "taxonomy"
        evidence.append(f"{m['subclass_axioms']} subClassOf and {broader} broader/narrower "
                        "links: a hierarchy exists")
    if m["skos_relations"] - broader > 0:
        level = "thesaurus"
        evidence.append(f"{m['skos_relations'] - broader} associative/mapping SKOS relations")
    reasoner_relevant = (m["restrictions"] + m["disjointness_axioms"] + m["equivalence_axioms"]
                         + m["property_characteristics"])
    if reasoner_relevant > 0 and has_hierarchy:
        level = "formal-ontology"
        evidence.append(f"{reasoner_relevant} axioms beyond subsumption (restrictions, "
                        "disjointness, equivalence, characteristics): a reasoner can derive facts")
    return {"level": level, "evidence": evidence}


# --------------------------------------------------------------------------- #
# OWL 2 profiles (DL-08) -- a syntactic approximation of the OWL 2 profile grammars
# --------------------------------------------------------------------------- #
def _superclass_expressions(g: Graph):
    for s, o in g.subject_objects(RDFS.subClassOf):
        yield s, o
    for s, o in g.subject_objects(OWL.equivalentClass):
        yield s, o
        yield o, s


def owl_profiles(g: Graph) -> dict[str, dict]:
    """``{EL|QL|RL: {in_profile, first_violation}}``. Violations are listed in a sorted,
    deterministic order; the first one is reported."""
    violations: dict[str, list[str]] = {"EL": [], "QL": [], "RL": []}

    def add(profile: str, construct: str, where) -> None:
        if not isinstance(where, URIRef):
            owners = V.named_owners(g, where)
            where = owners[0] if owners else None
        violations[profile].append(f"{construct} ({V.local_name(where) if where is not None else 'anonymous'})")

    for r in sorted(set(g.subjects(OWL.onProperty, None)), key=str):
        if (r, OWL.allValuesFrom, None) in g:
            add("EL", "owl:allValuesFrom", r); add("QL", "owl:allValuesFrom", r)
        for card in (OWL.cardinality, OWL.minCardinality, OWL.maxCardinality,
                     OWL.qualifiedCardinality, OWL.minQualifiedCardinality,
                     OWL.maxQualifiedCardinality):
            if (r, card, None) in g:
                add("EL", V.local_name(card), r); add("QL", V.local_name(card), r)
                value = g.value(r, card)
                if card in (OWL.cardinality, OWL.minCardinality, OWL.qualifiedCardinality,
                            OWL.minQualifiedCardinality) or str(value) not in ("0", "1"):
                    add("RL", f"{V.local_name(card)} {value} as superclass", r)
        if (r, OWL.hasValue, None) in g:
            add("QL", "owl:hasValue", r)
        if (r, OWL.hasSelf, None) in g:
            add("QL", "owl:hasSelf", r); add("RL", "owl:hasSelf", r)
    for sub, sup in _superclass_expressions(g):
        if isinstance(sup, BNode) and (sup, OWL.someValuesFrom, None) in g:
            add("RL", "owl:someValuesFrom as superclass", sub)
        if isinstance(sub, BNode) and (sub, OWL.someValuesFrom, None) in g:
            if g.value(sub, OWL.someValuesFrom) != OWL.Thing:
                add("QL", "qualified owl:someValuesFrom as subclass", sup)
        if isinstance(sup, BNode) and (sup, OWL.unionOf, None) in g:
            add("RL", "owl:unionOf as superclass", sub)
        if isinstance(sup, BNode) and (sup, OWL.complementOf, None) in g and isinstance(sub, BNode):
            add("RL", "owl:complementOf with complex subclass", sub)
    for s in sorted(set(g.subjects(OWL.unionOf, None)), key=str):
        add("EL", "owl:unionOf", s); add("QL", "owl:unionOf", s)
    for s in sorted(set(g.subjects(OWL.complementOf, None)), key=str):
        add("EL", "owl:complementOf", s)
    for s in sorted(set(g.subjects(OWL.oneOf, None)), key=str):
        add("QL", "owl:oneOf", s)
        if len(V.rdf_list(g, g.value(s, OWL.oneOf))) > 1:
            add("EL", "owl:oneOf with several members", s)
    for p in sorted(set(g.subjects(OWL.inverseOf, None)), key=str):
        add("EL", "owl:inverseOf", p)
    for p in sorted(set(g.subjects(RDF.type, OWL.FunctionalProperty)), key=str):
        if p not in set(V.datatype_properties(g)):
            add("EL", "functional object property", p)
        add("QL", "owl:FunctionalProperty", p)
    for t, label in ((OWL.InverseFunctionalProperty, "owl:InverseFunctionalProperty"),
                     (OWL.SymmetricProperty, "owl:SymmetricProperty"),
                     (OWL.AsymmetricProperty, "owl:AsymmetricProperty"),
                     (OWL.IrreflexiveProperty, "owl:IrreflexiveProperty")):
        for p in sorted(set(g.subjects(RDF.type, t)), key=str):
            add("EL", label, p)
    for p in sorted(set(g.subjects(RDF.type, OWL.TransitiveProperty)), key=str):
        add("QL", "owl:TransitiveProperty", p)
    for p in sorted(set(g.subjects(OWL.propertyChainAxiom, None)), key=str):
        add("QL", "owl:propertyChainAxiom", p)
    for s in sorted(set(g.subjects(OWL.disjointUnionOf, None)), key=str):
        for prof in ("EL", "QL", "RL"):
            add(prof, "owl:disjointUnionOf", s)
    for p in sorted(set(g.subjects(RDF.type, OWL.ReflexiveProperty)), key=str):
        add("RL", "owl:ReflexiveProperty", p)
    out = {}
    for prof in ("EL", "QL", "RL"):
        vs = sorted(set(violations[prof]))
        out[prof] = {"in_profile": not vs, "first_violation": vs[0] if vs else None,
                     "violations": len(vs)}
    return out


def expressivity(g: Graph) -> str:
    """A description-logic name such as ``ALCHIQ(D)`` for the constructs used (METRIC-02)."""
    has = lambda p: any(True for _ in g.triples((None, p, None)))  # noqa: E731
    typed = lambda t: any(True for _ in g.subjects(RDF.type, t))  # noqa: E731
    letters = ""
    complement = has(OWL.complementOf) or has(OWL.disjointWith) or typed(OWL.AllDisjointClasses)
    union = has(OWL.unionOf) or has(OWL.disjointUnionOf)
    if complement or (union and has(OWL.someValuesFrom)):
        base = "ALC"
    else:
        base = "AL"
        if union:
            letters += "U"
        if has(OWL.someValuesFrom):
            letters += "E"
    if typed(OWL.TransitiveProperty):
        base = "S" if base == "ALC" else base + "+"
    if has(OWL.propertyChainAxiom) or typed(OWL.ReflexiveProperty) or \
            typed(OWL.IrreflexiveProperty) or typed(OWL.AsymmetricProperty) or \
            has(OWL.propertyDisjointWith) or has(OWL.hasSelf):
        letters += "R"
    elif has(RDFS.subPropertyOf):
        letters += "H"
    if has(OWL.oneOf) or has(OWL.hasValue):
        letters += "O"
    if has(OWL.inverseOf) or typed(OWL.InverseFunctionalProperty) or typed(OWL.SymmetricProperty):
        letters += "I"
    if any(has(p) for p in V.QUALIFIED):
        letters += "Q"
    elif any(has(p) for p in (OWL.cardinality, OWL.minCardinality, OWL.maxCardinality)):
        letters += "N"
    elif typed(OWL.FunctionalProperty):
        letters += "F"
    data = bool(V.datatype_properties(g)) or any(
        str(o).startswith(str(V.XSD)) for o in g.objects(None, RDFS.range))
    name = base + letters + ("(D)" if data else "")
    if name == "AL" and not has(OWL.someValuesFrom) and not has(OWL.allValuesFrom):
        return "RDFS" + ("(D)" if data else "") if has(RDFS.subClassOf) else "none"
    return name


# --------------------------------------------------------------------------- #
# Measured profile
# --------------------------------------------------------------------------- #
@dataclass
class MeasuredProfile:
    spectrum_level: str
    spectrum_evidence: list[str]
    declared_level: str | None
    applies: list[str]
    owl_profiles: dict[str, dict]
    expressivity: str
    counts: dict
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def measure(g: Graph, declared_level: str | None = None, shapes: bool = False,
            baseline: bool = False, cqs: bool = False) -> MeasuredProfile:
    m = metrics(g)
    spec = classify_spectrum(g, m)
    uses_owl = any(str(p).startswith(str(OWL)) for p in g.predicates()) or any(
        str(o).startswith(str(OWL)) for o in g.objects(None, RDF.type))
    uses_rdfs = uses_owl or m["subclass_axioms"] > 0 or any(True for _ in g.subjects(RDF.type, RDFS.Class))
    uses_skos = any(str(p).startswith(str(SKOS)) for p in g.predicates()) or m["skos_concepts"] > 0
    applies = ["all"]
    if uses_rdfs:
        applies.append("rdfs")
    if uses_owl:
        applies += ["owl", "dl"]
    if uses_skos:
        applies.append("skos")
    if m["individuals"]:
        applies.append("abox")
    if shapes:
        applies.append("shacl")
    if baseline:
        applies.append("versioned")
    if cqs:
        applies.append("cq")
    notes = []
    if declared_level is None:
        notes.append("no declared level: METRIC-01 has nothing to compare against")
    return MeasuredProfile(spec["level"], spec["evidence"], declared_level, applies,
                           owl_profiles(g), expressivity(g), m, notes)
