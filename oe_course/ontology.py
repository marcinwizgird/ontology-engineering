"""Measurable properties of an ontology: metrics, spectrum position, defects.

Keet's Chapter 1 asks three questions in prose — *what does an ontology look
like*, *what is an ontology*, and *what separates a good one from a bad one*.
This module turns each into something a program can compute and a grader can
check:

* :func:`graph_metrics` — what the artefact contains;
* :func:`classify_spectrum` — where it sits on the vocabulary → taxonomy →
  thesaurus → formal-ontology spectrum, with the evidence that placed it;
* :func:`scan_smells` — which known modelling defects it exhibits.

The detectors are deliberately *syntactic and explainable*: each returns the
triple that triggered it. That makes them usable both as an autograder and as
the ground truth for the Chapter 1 agent's evaluation dataset.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable

import rdflib
from rdflib import OWL, RDF, RDFS, SKOS, Graph, URIRef
from rdflib.namespace import DCTERMS

__all__ = [
    "graph_metrics",
    "classify_spectrum",
    "scan_smells",
    "Finding",
    "Smell",
    "SMELLS",
    "SMELL_IDS",
    "SPECTRUM_LEVELS",
    "load_graph",
]

SPECTRUM_LEVELS = [
    "controlled-vocabulary",  # terms with labels, no structure
    "taxonomy",               # + a subsumption hierarchy
    "thesaurus",              # + associative/lexical relations (SKOS-style)
    "formal-ontology",        # + logical axioms a reasoner can use
]


def load_graph(source: str | Iterable[str], fmt: str | None = None) -> Graph:
    """Parse Turtle text, a path, or an iterable of either into one graph."""
    g = Graph()
    sources = [source] if isinstance(source, str) else list(source)
    for s in sources:
        if "\n" in s or s.strip().startswith("@prefix"):
            g.parse(data=s, format=fmt or "turtle")
        else:
            g.parse(s, format=fmt or rdflib.util.guess_format(s) or "turtle")
    return g


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _classes(g: Graph) -> set:
    return {s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)} | {
        s for s in g.subjects(RDF.type, RDFS.Class) if isinstance(s, URIRef)
    }


def _object_properties(g: Graph) -> set:
    return {s for s in g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(s, URIRef)}


def _individuals(g: Graph) -> set:
    named = {s for s in g.subjects(RDF.type, OWL.NamedIndividual) if isinstance(s, URIRef)}
    classes = _classes(g)
    for s, _, o in g.triples((None, RDF.type, None)):
        if isinstance(s, URIRef) and o in classes:
            named.add(s)
    return named - classes


def graph_metrics(g: Graph) -> dict:
    """Counts that describe the shape of an ontology.

    ``axiom_richness`` — logical axioms per class — is the single number the
    course uses to argue about "how much ontology" an artefact really contains.
    """
    classes = _classes(g)
    restrictions = set(g.subjects(RDF.type, OWL.Restriction))
    subclass_axioms = sum(1 for _ in g.triples((None, RDFS.subClassOf, None)))
    disjointness = sum(1 for _ in g.triples((None, OWL.disjointWith, None))) + sum(
        1 for _ in g.subjects(RDF.type, OWL.AllDisjointClasses)
    )
    equivalences = sum(1 for _ in g.triples((None, OWL.equivalentClass, None)))
    domains = sum(1 for _ in g.triples((None, RDFS.domain, None)))
    ranges = sum(1 for _ in g.triples((None, RDFS.range, None)))
    property_characteristics = sum(
        1
        for c in (
            OWL.TransitiveProperty,
            OWL.SymmetricProperty,
            OWL.AsymmetricProperty,
            OWL.FunctionalProperty,
            OWL.InverseFunctionalProperty,
            OWL.ReflexiveProperty,
            OWL.IrreflexiveProperty,
        )
        for _ in g.subjects(RDF.type, c)
    )
    skos_relations = sum(
        1
        for p in (SKOS.broader, SKOS.narrower, SKOS.related, SKOS.closeMatch, SKOS.exactMatch)
        for _ in g.triples((None, p, None))
    )
    labels = sum(1 for _ in g.triples((None, RDFS.label, None))) + sum(
        1 for _ in g.triples((None, SKOS.prefLabel, None))
    )
    annotations = labels + sum(1 for _ in g.triples((None, RDFS.comment, None))) + sum(
        1 for _ in g.triples((None, DCTERMS.description, None))
    )

    logical_axioms = (
        subclass_axioms
        + disjointness
        + equivalences
        + len(restrictions)
        + domains
        + ranges
        + property_characteristics
    )
    return {
        "triples": len(g),
        "classes": len(classes),
        "object_properties": len(_object_properties(g)),
        "data_properties": len(set(g.subjects(RDF.type, OWL.DatatypeProperty))),
        "individuals": len(_individuals(g)),
        "subclass_axioms": subclass_axioms,
        "restrictions": len(restrictions),
        "disjointness_axioms": disjointness,
        "equivalence_axioms": equivalences,
        "domain_axioms": domains,
        "range_axioms": ranges,
        "property_characteristics": property_characteristics,
        "skos_relations": skos_relations,
        "labels": labels,
        "annotations": annotations,
        "logical_axioms": logical_axioms,
        "axiom_richness": round(logical_axioms / len(classes), 3) if classes else 0.0,
    }


# --------------------------------------------------------------------------- #
# Spectrum
# --------------------------------------------------------------------------- #
def classify_spectrum(g: Graph) -> dict:
    """Place an artefact on the ontology spectrum, with the evidence used.

    The rule is cumulative and mirrors the book's progression: structure first
    (subsumption), then lexical/associative relations, then logic. An artefact
    only reaches ``formal-ontology`` when it carries axioms a reasoner can act
    on beyond plain subsumption.
    """
    m = graph_metrics(g)
    evidence: list[str] = []
    level = "controlled-vocabulary"

    if m["labels"] or m["classes"]:
        evidence.append(f"{m['classes']} classes, {m['labels']} labels -> named terms exist")

    has_hierarchy = m["subclass_axioms"] > 0 or any(g.triples((None, SKOS.broader, None)))
    if has_hierarchy:
        level = "taxonomy"
        evidence.append(f"{m['subclass_axioms']} subsumption axioms -> a hierarchy exists")

    if m["skos_relations"] > 0:
        level = "thesaurus"
        evidence.append(f"{m['skos_relations']} SKOS relations -> associative/lexical structure")

    reasoner_relevant = (
        m["restrictions"]
        + m["disjointness_axioms"]
        + m["equivalence_axioms"]
        + m["property_characteristics"]
    )
    if reasoner_relevant > 0 and has_hierarchy:
        level = "formal-ontology"
        evidence.append(
            f"{reasoner_relevant} axioms beyond subsumption "
            f"(restrictions/disjointness/equivalence/property characteristics) -> "
            "a reasoner can derive new facts"
        )

    return {"level": level, "evidence": evidence, "metrics": m}


# --------------------------------------------------------------------------- #
# Smells
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Finding:
    """One detected defect, with the term that triggered it."""

    smell: str
    subject: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Smell:
    id: str
    title: str
    why: str
    detector: Callable[[Graph], list[Finding]] = field(repr=False)


def _q(term) -> str:
    return str(term)


def _detect_subsumption_cycle(g: Graph) -> list[Finding]:
    parents = defaultdict(set)
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            parents[s].add(o)

    findings, seen = [], set()
    for start in parents:
        stack, path = [(start, (start,))], None
        visited = set()
        while stack:
            node, path = stack.pop()
            for parent in parents.get(node, ()):
                if parent == start:
                    key = frozenset(path)
                    if key not in seen:
                        seen.add(key)
                        findings.append(
                            Finding(
                                "subsumption-cycle",
                                _q(start),
                                "cycle: " + " SubClassOf ".join(_q(p) for p in path + (start,)),
                            )
                        )
                elif parent not in visited:
                    visited.add(parent)
                    stack.append((parent, path + (parent,)))
    return findings


def _detect_class_as_individual(g: Graph) -> list[Finding]:
    classes = _classes(g)
    findings = []
    for s, _, o in g.triples((None, RDF.type, None)):
        if s in classes and o in classes and o != OWL.Class:
            findings.append(
                Finding(
                    "class-as-individual",
                    _q(s),
                    f"declared owl:Class but also asserted rdf:type {_q(o)} — "
                    "class/instance levels are conflated",
                )
            )
    return findings


def _detect_individual_as_class(g: Graph) -> list[Finding]:
    classes = _classes(g)
    findings = []
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and s not in classes and (s, RDF.type, OWL.NamedIndividual) in g:
            findings.append(
                Finding(
                    "individual-as-class",
                    _q(s),
                    f"an individual placed in a subsumption axiom (SubClassOf {_q(o)}); "
                    "instances relate to classes by rdf:type, not rdfs:subClassOf",
                )
            )
    return findings


def _detect_property_without_domain_or_range(g: Graph) -> list[Finding]:
    findings = []
    for p in sorted(_object_properties(g)):
        missing = []
        if not any(g.triples((p, RDFS.domain, None))):
            missing.append("domain")
        if not any(g.triples((p, RDFS.range, None))):
            missing.append("range")
        if missing:
            findings.append(
                Finding(
                    "property-without-domain-or-range",
                    _q(p),
                    f"object property has no {' and no '.join(missing)}; "
                    "its intended use is not machine-checkable",
                )
            )
    return findings


def _detect_no_disjointness(g: Graph) -> list[Finding]:
    m = graph_metrics(g)
    if m["classes"] < 2 or m["disjointness_axioms"] > 0:
        return []
    siblings = defaultdict(list)
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            siblings[o].append(s)
    if not any(len(v) > 1 for v in siblings.values()):
        return []
    parent = next(k for k, v in siblings.items() if len(v) > 1)
    return [
        Finding(
            "no-disjointness",
            _q(parent),
            f"{len(siblings[parent])} sibling classes under {_q(parent)} and no disjointness "
            "axiom anywhere; nothing prevents an individual from being all of them at once",
        )
    ]


def _detect_undeclared_term(g: Graph) -> list[Finding]:
    classes = _classes(g)
    findings, seen = [], set()
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        for term in (s, o):
            if isinstance(term, URIRef) and term not in classes and term not in seen:
                if (term, RDF.type, OWL.NamedIndividual) in g:
                    continue  # reported by individual-as-class
                seen.add(term)
                findings.append(
                    Finding(
                        "undeclared-term",
                        _q(term),
                        "used in a subsumption axiom but never declared owl:Class",
                    )
                )
    return findings


def _detect_missing_labels(g: Graph) -> list[Finding]:
    findings = []
    for c in sorted(_classes(g)):
        if not any(g.triples((c, RDFS.label, None))) and not any(
            g.triples((c, SKOS.prefLabel, None))
        ):
            findings.append(
                Finding(
                    "missing-label",
                    _q(c),
                    "class has no rdfs:label; the intended meaning rests on the IRI alone",
                )
            )
    return findings


SMELLS: list[Smell] = [
    Smell(
        "subsumption-cycle",
        "Cycle in the class hierarchy",
        "A ⊑ B ⊑ A forces the classes to be equivalent, which is almost never intended "
        "and silently collapses the taxonomy under a reasoner.",
        _detect_subsumption_cycle,
    ),
    Smell(
        "class-as-individual",
        "Class used as an instance",
        "Conflating the class and instance levels (without deliberate punning) makes the "
        "ontology's commitments ambiguous — the classic 'is Lion a kind or a thing?' error.",
        _detect_class_as_individual,
    ),
    Smell(
        "individual-as-class",
        "Individual used in a subsumption axiom",
        "rdfs:subClassOf between an individual and a class is a category error; the author "
        "meant rdf:type.",
        _detect_individual_as_class,
    ),
    Smell(
        "property-without-domain-or-range",
        "Object property lacking domain or range",
        "Without domain/range the property carries no ontological commitment and a reasoner "
        "can infer nothing from its use.",
        _detect_property_without_domain_or_range,
    ),
    Smell(
        "no-disjointness",
        "Sibling classes with no disjointness",
        "Absent disjointness, most modelling errors stay satisfiable and the reasoner cannot "
        "report them — the single most common reason a 'bad' ontology looks fine.",
        _detect_no_disjointness,
    ),
    Smell(
        "undeclared-term",
        "Term used but never declared",
        "Referring to an undeclared IRI leaves its type implicit and defeats tooling that "
        "enumerates the vocabulary.",
        _detect_undeclared_term,
    ),
    Smell(
        "missing-label",
        "Class without a human-readable label",
        "Keet's 'good ontology' criteria include documentation: an unlabelled class cannot be "
        "reviewed by a domain expert.",
        _detect_missing_labels,
    ),
]

SMELL_IDS = [s.id for s in SMELLS]
_SMELL_BY_ID = {s.id: s for s in SMELLS}


def scan_smells(g: Graph, only: Iterable[str] | None = None) -> list[Finding]:
    """Run every detector (or a named subset) and return the findings."""
    chosen = [_SMELL_BY_ID[i] for i in only] if only else SMELLS
    out: list[Finding] = []
    for smell in chosen:
        out.extend(smell.detector(g))
    return out


def smell_summary(g: Graph) -> dict[str, int]:
    """``{smell_id: count}`` — the compact form the agent's metrics compare."""
    counts: dict[str, int] = {}
    for f in scan_smells(g):
        counts[f.smell] = counts.get(f.smell, 0) + 1
    return counts
