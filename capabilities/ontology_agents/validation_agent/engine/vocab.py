"""Vocabulary helpers shared by the detectors.

Every helper returns sorted results so detectors iterate in a stable order (the
determinism contract, SPECIFICATION.md s.5.6).
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD

SH = Namespace("http://www.w3.org/ns/shacl#")
OBO = Namespace("http://purl.obolibrary.org/obo/")
IAO_DEFINITION = OBO["IAO_0000115"]
CC = Namespace("http://creativecommons.org/ns#")
SCHEMA = Namespace("https://schema.org/")
OVA = Namespace("urn:ova:")

NO_BASE = "http://ova.invalid/no-base/"
"""Base IRI used when parsing, so that relative IRIs without an ``@base`` stay
recognisable (SYN-02) instead of silently resolving against the file path."""

RESERVED = {
    str(RDF): set(RDF.__annotations__) | {"_1", "_2", "_3", "_4", "_5"},
    str(RDFS): set(RDFS.__annotations__),
    str(OWL): set(OWL.__annotations__),
    str(XSD): set(XSD.__annotations__),
}
"""The terms the four reserved vocabularies define (DECL-04)."""

KNOWN_VOCABULARIES = tuple(RESERVED) + (
    str(SKOS), str(DCTERMS), str(DC), str(SH), str(CC), "http://xmlns.com/foaf/0.1/",
    "http://www.w3.org/ns/prov#", "http://purl.org/vocab/vann/", "http://schema.org/",
    str(SCHEMA), "http://www.w3.org/2004/02/skos/core", "http://purl.obolibrary.org/obo/IAO_",
    "http://www.w3.org/ns/dcat#", "http://www.w3.org/2003/01/geo/wgs84_pos#",
)
"""Namespaces whose terms are declared by their own vocabulary, so using them is not an
undeclared use (DECL-01/02)."""

CLASS_TYPES = (OWL.Class, RDFS.Class)
OBJECT_PROPERTY_TYPES = (
    OWL.ObjectProperty, OWL.TransitiveProperty, OWL.SymmetricProperty,
    OWL.AsymmetricProperty, OWL.ReflexiveProperty, OWL.IrreflexiveProperty,
    OWL.InverseFunctionalProperty,
)
PROPERTY_TYPES = OBJECT_PROPERTY_TYPES + (
    OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.FunctionalProperty,
    OWL.OntologyProperty, RDF.Property,
)
META_TYPES = set(CLASS_TYPES) | set(PROPERTY_TYPES) | {
    OWL.NamedIndividual, OWL.Ontology, OWL.Restriction, RDFS.Datatype,
    OWL.AllDisjointClasses, OWL.AllDifferent, OWL.Axiom, OWL.Annotation,
    OWL.DeprecatedClass, OWL.DeprecatedProperty, OWL.NegativePropertyAssertion,
    OWL.AllDisjointProperties, RDF.List, RDF.Statement,
}
LABEL_PROPERTIES = (RDFS.label, SKOS.prefLabel)
DEFINITION_PROPERTIES = (SKOS.definition, IAO_DEFINITION, RDFS.comment)
RESTRICTION_FILLERS = (
    OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue, OWL.hasSelf,
    OWL.cardinality, OWL.minCardinality, OWL.maxCardinality,
    OWL.qualifiedCardinality, OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality,
)
QUALIFIED = (OWL.qualifiedCardinality, OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality)
SCHEMA_PREDICATES = {
    RDF.type, RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range,
    OWL.equivalentClass, OWL.disjointWith, OWL.inverseOf, OWL.equivalentProperty,
    OWL.propertyDisjointWith, OWL.complementOf, OWL.unionOf, OWL.intersectionOf, OWL.oneOf,
    OWL.onProperty, OWL.imports, OWL.sameAs, OWL.differentFrom, OWL.members,
    OWL.distinctMembers, OWL.disjointUnionOf, OWL.propertyChainAxiom, OWL.hasKey,
    RDF.first, RDF.rest, *RESTRICTION_FILLERS, OWL.onClass, OWL.onDataRange,
}


def is_builtin(term) -> bool:
    return isinstance(term, URIRef) and str(term).startswith(KNOWN_VOCABULARIES)


def sorted_terms(terms) -> list:
    return sorted(set(terms), key=str)


def named(terms) -> list[URIRef]:
    return sorted_terms(t for t in terms if isinstance(t, URIRef))


def declared_classes(g: Graph) -> list[URIRef]:
    return named(s for t in CLASS_TYPES for s in g.subjects(RDF.type, t))


def declared_properties(g: Graph) -> list[URIRef]:
    return named(s for t in PROPERTY_TYPES for s in g.subjects(RDF.type, t))


def object_properties(g: Graph) -> list[URIRef]:
    return named(s for t in OBJECT_PROPERTY_TYPES for s in g.subjects(RDF.type, t))


def datatype_properties(g: Graph) -> list[URIRef]:
    return named(g.subjects(RDF.type, OWL.DatatypeProperty))


def individuals(g: Graph) -> list[URIRef]:
    """Named individuals: declared ``owl:NamedIndividual`` or typed by a non-meta class."""
    out = set(g.subjects(RDF.type, OWL.NamedIndividual))
    for s, o in g.subject_objects(RDF.type):
        if o not in META_TYPES and not is_builtin(o) or o == SKOS.Concept:
            out.add(s)
    return named(out)


def ontology_nodes(g: Graph) -> list:
    return sorted_terms(g.subjects(RDF.type, OWL.Ontology))


def rdf_list(g: Graph, head) -> list:
    """Items of a well-formed rdf:List (stops on a cycle; SYN-05 checks malformation)."""
    items, seen = [], set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = g.value(head, RDF.first)
        if first is not None:
            items.append(first)
        head = g.value(head, RDF.rest)
    return items


def label(g: Graph, term) -> str:
    """A human label for ``term``: rdfs:label/skos:prefLabel (English first), else the
    local name."""
    if not isinstance(term, URIRef):
        return str(term)
    labels = [o for p in LABEL_PROPERTIES for o in g.objects(term, p) if isinstance(o, Literal)]
    labels.sort(key=lambda l: (l.language not in ("en", None), l.language or "", str(l)))
    if labels:
        return str(labels[0])
    return local_name(term)


def local_name(term) -> str:
    s = str(term)
    for sep in ("#", "/", ":"):
        if sep in s.rstrip(sep):
            s = s.rstrip(sep).rsplit(sep, 1)[-1]
            break
    return s


def is_term(term) -> bool:
    return isinstance(term, (URIRef, BNode))


def named_owners(g: Graph, node, limit: int = 50) -> list[URIRef]:
    """Named entities whose axioms contain the anonymous ``node`` (walks up through
    rdf:List cells and nested class expressions)."""
    owners, seen, frontier = set(), {node}, [node]
    while frontier and len(seen) < limit:
        nxt = []
        for n in frontier:
            for s in g.subjects(None, n):
                if isinstance(s, URIRef):
                    owners.add(s)
                elif s not in seen:
                    seen.add(s)
                    nxt.append(s)
        frontier = nxt
    return sorted(owners, key=str)
