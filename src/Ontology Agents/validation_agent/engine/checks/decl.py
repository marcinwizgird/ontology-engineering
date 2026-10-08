"""DECL: is every term declared, and is the reserved vocabulary spelled correctly?"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .. import vocab as V
from ..registry import CheckContext, detector, finding

CLASS_PAIR_PREDICATES = (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, OWL.complementOf)
CLASS_FILLERS = (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass)
CLASS_LISTS = (OWL.unionOf, OWL.intersectionOf, OWL.members, OWL.disjointUnionOf)


def _class_uses(g) -> dict[URIRef, list[str]]:
    uses: dict[URIRef, list[str]] = defaultdict(list)

    def use(term, triple: str) -> None:
        if isinstance(term, URIRef) and not V.is_builtin(term):
            uses[term].append(triple)

    for s, o in g.subject_objects(RDF.type):
        if o not in V.META_TYPES:
            use(o, f"<{s}> rdf:type <{o}>")
    for p in CLASS_PAIR_PREDICATES:
        for s, o in g.subject_objects(p):
            use(s, f"<{s}> {V.local_name(p)} {o.n3()}")
            use(o, f"{s.n3()} {V.local_name(p)} <{o}>")
    for p in CLASS_FILLERS:
        for r, o in g.subject_objects(p):
            use(o, f"restriction {V.local_name(p)} <{o}>")
    for p in CLASS_LISTS:
        for s, head in g.subject_objects(p):
            for item in V.rdf_list(g, head):
                use(item, f"{s.n3()} {V.local_name(p)} (... <{item}> ...)")
    for p, o in g.subject_objects(RDFS.domain):
        use(o, f"<{p}> rdfs:domain <{o}>")
    datatype_props = set(V.datatype_properties(g))
    for p, o in g.subject_objects(RDFS.range):
        if p not in datatype_props:
            use(o, f"<{p}> rdfs:range <{o}>")
    return uses


@detector("DECL-01")
def undeclared_class(ctx: CheckContext):
    g = ctx.graph
    declared = set(V.declared_classes(g)) | set(g.subjects(RDF.type, RDFS.Datatype))
    out = []
    for term, triples in sorted(_class_uses(g).items(), key=lambda kv: str(kv[0])):
        if term in declared:
            continue
        out.append(finding(
            "DECL-01", term, f"{V.local_name(term)} is used as a class but never declared "
            "owl:Class or rdfs:Class.",
            evidence={"triples": sorted(set(triples))[:5], "uses": len(set(triples))},
            fix_hint=f"Add `<{term}> a owl:Class` (with a label and definition), or correct "
                     "the IRI if it is a typo for a declared class."))
    return out


def _property_uses(g) -> dict[URIRef, list[str]]:
    uses: dict[URIRef, list[str]] = defaultdict(list)

    def use(term, why: str) -> None:
        if isinstance(term, URIRef) and not V.is_builtin(term):
            uses[term].append(why)

    for p in set(g.predicates()):
        use(p, "used as a predicate")
    for o in g.objects(None, OWL.onProperty):
        use(o, "owl:onProperty of a restriction")
    for p in (RDFS.subPropertyOf, OWL.inverseOf, OWL.equivalentProperty, OWL.propertyDisjointWith):
        for s, o in g.subject_objects(p):
            use(s, f"subject of {V.local_name(p)}")
            use(o, f"object of {V.local_name(p)}")
    for p in (RDFS.domain, RDFS.range):
        for s in g.subjects(p, None):
            use(s, f"has rdfs:{V.local_name(p)}")
    return uses


@detector("DECL-02")
def undeclared_property(ctx: CheckContext):
    g = ctx.graph
    declared = set(V.declared_properties(g))
    out = []
    for term, why in sorted(_property_uses(g).items(), key=lambda kv: str(kv[0])):
        if term in declared:
            continue
        out.append(finding(
            "DECL-02", term, f"{V.local_name(term)} is used as a property but never declared "
            "as an object, datatype or annotation property.",
            evidence={"uses": sorted(set(why))},
            fix_hint="Declare it as owl:ObjectProperty, owl:DatatypeProperty or "
                     "owl:AnnotationProperty; a DL parser otherwise has to guess its kind."))
    return out


@detector("DECL-03")
def ontology_header(ctx: CheckContext):
    nodes = V.ontology_nodes(ctx.graph)
    source = ctx.load.source if ctx.load else "document"
    if not nodes:
        return [finding("DECL-03", source, "The document has no owl:Ontology header.",
                        fix_hint="Add `<ontology-iri> a owl:Ontology` with title, version "
                                 "and licence metadata.")]
    if len(nodes) > 1:
        return [finding("DECL-03", nodes[0], f"The document declares {len(nodes)} owl:Ontology "
                        "nodes.", related=nodes[1:], evidence={"ontologies": [str(n) for n in nodes]},
                        fix_hint="Keep one ontology per document; split the rest into their "
                                 "own files and link them with owl:imports.")]
    return []


@detector("DECL-04")
def reserved_vocabulary_typo(ctx: CheckContext):
    terms = {t for triple in ctx.graph for t in triple if isinstance(t, URIRef)}
    out = []
    for t in sorted(terms, key=str):
        s = str(t)
        for ns, defined in V.RESERVED.items():
            if s.startswith(ns):
                local = s[len(ns):]
                if local and local not in defined and not re.fullmatch(r"_\d+", local):
                    lower = {d.lower(): d for d in defined}
                    guess = lower.get(local.lower()) or next(iter(
                        difflib.get_close_matches(local, sorted(defined), n=1, cutoff=0.75)), None)
                    hint = f"Did you mean {ns}{guess}?" if guess else "Remove or correct the term."
                    out.append(finding(
                        "DECL-04", t, f"<{s}> is not a term of the {ns} vocabulary"
                        + (f" (did you mean {V.local_name(ns + guess)}?)" if guess else "") + ".",
                        evidence={"namespace": ns, "local_name": local, "suggestion": guess},
                        fix_hint=hint + " Tools silently treat an unknown reserved term as a "
                                        "plain IRI, so the axiom it was meant to express is lost."))
                break
    return out
