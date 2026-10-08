"""Render a grounded extraction as OWL, with provenance on every axiom.

This is where LangExtract's span grounding earns its keep.  An LLM asked to
"write me some Turtle" produces an ontology nobody can audit.  Here, every
asserted axiom is reified as an ``owl:Axiom`` (the OWL 2 way to annotate an
axiom rather than an entity) carrying:

* ``prov:wasQuotedFrom`` — the source document,
* ``lxo:exactQuote``     — the sentence that licensed the axiom,
* ``lxo:charStart`` / ``lxo:charEnd`` — where in the document it sits,
* ``lxo:alignment``      — how confidently LangExtract re-aligned the quote,
* ``lxo:extractedBy``    — which model produced it.

A reviewer can therefore ask of any axiom: *what in the text made you say
this?* — and get an answer, which is exactly the review loop the
human-in-the-loop step of Fig. 7.7 needs.
"""

from __future__ import annotations

import re
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from . import schema as S
from .extract import GroundedItem, OntologyExtraction

#: Provenance vocabulary minted for this prototype.
LXO = Namespace("https://w3id.org/langextract-ontology#")

DEFAULT_BASE = "https://example.org/onto/"

_QUANTIFIERS = {
    "exactly": OWL.qualifiedCardinality,
    "at least": OWL.minQualifiedCardinality,
    "min": OWL.minQualifiedCardinality,
    "at most": OWL.maxQualifiedCardinality,
    "max": OWL.maxQualifiedCardinality,
}


# --------------------------------------------------------------------------- #
# IRI minting
# --------------------------------------------------------------------------- #
def class_ident(label: str) -> str:
    """CamelCase OWL class name from a natural-language label."""
    parts = [p for p in re.split(r"[\s\-_/]+", label.strip()) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Thing"


def property_ident(label: str) -> str:
    """lowerCamelCase OWL property name from a label (already-camel stays)."""
    label = label.strip()
    if not label:
        return "relatedTo"
    if re.fullmatch(r"[a-z]+(?:[A-Z][a-zA-Z]*)*", label):
        return label  # the model already gave us lowerCamelCase
    parts = [p for p in re.split(r"[\s\-_/]+", label) if p]
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def individual_ident(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", label.strip()) or "individual"


# --------------------------------------------------------------------------- #
# The builder
# --------------------------------------------------------------------------- #
class OwlBuilder:
    """Accumulates an rdflib graph from a :class:`OntologyExtraction`."""

    def __init__(
        self,
        extraction: OntologyExtraction,
        base: str = DEFAULT_BASE,
        ontology_iri: str | None = None,
    ) -> None:
        self.extraction = extraction
        self.ns = Namespace(base)
        self.graph = Graph()
        self.graph.bind("", self.ns)
        self.graph.bind("owl", OWL)
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("skos", SKOS)
        self.graph.bind("prov", PROV)
        self.graph.bind("dcterms", DCTERMS)
        self.graph.bind("xsd", XSD)
        self.graph.bind("lxo", LXO)

        self.ontology_iri = URIRef(ontology_iri or base.rstrip("/#"))
        self.document_iri = URIRef(f"{base}source/{extraction.document_id}")
        self._declared: set[URIRef] = set()

    # -- helpers ------------------------------------------------------------- #
    def cls(self, label: str) -> URIRef | None:
        label = (label or "").strip()
        if not label:
            return None
        iri = self.ns[class_ident(label)]
        if iri not in self._declared:
            self.graph.add((iri, RDF.type, OWL.Class))
            self.graph.add((iri, RDFS.label, Literal(label)))
            self._declared.add(iri)
        return iri

    def _datatype(self, name: str) -> URIRef:
        name = (name or "xsd:string").strip()
        if name.startswith("xsd:"):
            return XSD[name[4:]]
        if name.startswith("http"):
            return URIRef(name)
        return XSD[name]

    def annotate(
        self,
        triple: tuple[Any, Any, Any],
        item: GroundedItem,
    ) -> BNode:
        """Reify ``triple`` as an ``owl:Axiom`` carrying its provenance."""
        subject, predicate, obj = triple
        axiom = BNode()
        self.graph.add((axiom, RDF.type, OWL.Axiom))
        self.graph.add((axiom, OWL.annotatedSource, subject))
        self.graph.add((axiom, OWL.annotatedProperty, predicate))
        self.graph.add((axiom, OWL.annotatedTarget, obj))
        self.graph.add((axiom, PROV.wasQuotedFrom, self.document_iri))
        self.graph.add((axiom, LXO.exactQuote, Literal(item.quote)))
        self.graph.add((axiom, LXO.extractionClass, Literal(item.kind)))
        self.graph.add((axiom, LXO.alignment, Literal(item.alignment)))
        self.graph.add((axiom, LXO.extractedBy, Literal(self.extraction.model_name)))
        if item.grounded:
            self.graph.add((axiom, LXO.charStart, Literal(item.start, datatype=XSD.integer)))
            self.graph.add((axiom, LXO.charEnd, Literal(item.end, datatype=XSD.integer)))
        return axiom

    def assert_grounded(self, triple: tuple[Any, Any, Any], item: GroundedItem) -> None:
        self.graph.add(triple)
        self.annotate(triple, item)

    # -- build --------------------------------------------------------------- #
    def build(self) -> Graph:
        g, ns, ex = self.graph, self.ns, self.extraction

        g.add((self.ontology_iri, RDF.type, OWL.Ontology))
        g.add((self.ontology_iri, DCTERMS.source, self.document_iri))
        g.add((self.document_iri, RDF.type, PROV.Entity))
        g.add((self.document_iri, DCTERMS.identifier, Literal(ex.document_id)))
        g.add((self.ontology_iri, PROV.wasGeneratedBy, Literal(f"langextract/{ex.model_name}")))

        # Declare every class the extraction mentions, however it mentioned it.
        for label in ex.class_labels():
            self.cls(label)

        for item in ex.classes():
            iri = self.cls(item.attr("label") or item.quote)
            definition = item.attr("definition")
            if iri is not None and definition:
                self.assert_grounded((iri, SKOS.definition, Literal(definition)), item)

        for item in ex.subsumptions():
            sub, sup = self.cls(item.attr("subclass")), self.cls(item.attr("superclass"))
            if sub is None or sup is None or sub == sup:
                continue
            self.assert_grounded((sub, RDFS.subClassOf, sup), item)

        for item in ex.object_properties():
            prop = ns[property_ident(item.attr("property"))]
            g.add((prop, RDF.type, OWL.ObjectProperty))
            domain, rng = self.cls(item.attr("domain")), self.cls(item.attr("range"))
            if domain is not None:
                self.assert_grounded((prop, RDFS.domain, domain), item)
            if rng is not None:
                self.assert_grounded((prop, RDFS.range, rng), item)

        for item in ex.data_properties():
            prop = ns[property_ident(item.attr("property"))]
            g.add((prop, RDF.type, OWL.DatatypeProperty))
            domain = self.cls(item.attr("domain"))
            if domain is not None:
                self.assert_grounded((prop, RDFS.domain, domain), item)
            self.assert_grounded(
                (prop, RDFS.range, self._datatype(item.attr("datatype"))), item
            )

        for item in ex.individuals():
            label = item.attr("label") or item.quote
            ind = ns[individual_ident(label)]
            g.add((ind, RDF.type, OWL.NamedIndividual))
            g.add((ind, RDFS.label, Literal(label)))
            type_iri = self.cls(item.attr("type"))
            if type_iri is not None:
                self.assert_grounded((ind, RDF.type, type_iri), item)

        for item in ex.axioms():
            self._axiom(item)

        return g

    # -- the constraint cases ------------------------------------------------ #
    def _axiom(self, item: GroundedItem) -> None:
        g, ns = self.graph, self.ns
        kind = item.attr("axiom_type").lower()
        subject = self.cls(item.attr("subject"))
        filler = self.cls(item.attr("filler"))
        expression = item.attr("expression")

        if subject is None:
            return

        if kind == "disjointness" and filler is not None:
            self.assert_grounded((subject, OWL.disjointWith, filler), item)
        elif kind == "equivalence" and filler is not None:
            self.assert_grounded((subject, OWL.equivalentClass, filler), item)
        elif kind in ("cardinality", "existential", "universal") and filler is not None:
            prop = ns[property_ident(item.attr("property") or f"has {item.attr('filler')}")]
            g.add((prop, RDF.type, OWL.ObjectProperty))
            restriction = BNode()
            g.add((restriction, RDF.type, OWL.Restriction))
            g.add((restriction, OWL.onProperty, prop))
            if kind == "existential":
                g.add((restriction, OWL.someValuesFrom, filler))
            elif kind == "universal":
                g.add((restriction, OWL.allValuesFrom, filler))
            else:
                predicate = _QUANTIFIERS.get(_quantifier_of(expression), OWL.qualifiedCardinality)
                count = item.attr("cardinality") or "1"
                g.add((restriction, OWL.onClass, filler))
                g.add((restriction, predicate, Literal(count, datatype=XSD.nonNegativeInteger)))
            self.assert_grounded((subject, RDFS.subClassOf, restriction), item)
        elif kind == "functional" and item.attr("property"):
            prop = ns[property_ident(item.attr("property"))]
            self.assert_grounded((prop, RDF.type, OWL.FunctionalProperty), item)
        elif expression:
            # An axiom type we do not render structurally is still worth
            # keeping as a traceable, human-readable note rather than dropping.
            self.assert_grounded((subject, RDFS.comment, Literal(expression)), item)


def _quantifier_of(expression: str) -> str:
    """Recover 'exactly' / 'at least' / 'at most' from a Manchester expression."""
    low = expression.lower()
    for key in ("at least", "at most", "exactly", "min", "max"):
        if key in low:
            return key
    return "exactly"


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def to_graph(
    extraction: OntologyExtraction,
    base: str = DEFAULT_BASE,
    ontology_iri: str | None = None,
) -> Graph:
    """Render a grounded extraction as an rdflib :class:`~rdflib.Graph`."""
    return OwlBuilder(extraction, base=base, ontology_iri=ontology_iri).build()


def to_turtle(
    extraction: OntologyExtraction,
    base: str = DEFAULT_BASE,
    path: str | None = None,
) -> str:
    """Serialise the extraction to Turtle, optionally writing it to ``path``."""
    turtle = to_graph(extraction, base=base).serialize(format="turtle")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(turtle)
    return turtle


def provenance_of(graph: Graph, subject: URIRef, predicate: URIRef) -> list[dict[str, Any]]:
    """Every recorded justification for triples ``(subject, predicate, *)``.

    The review question — *why does the ontology say this?* — answered as a
    SPARQL-free lookup over the ``owl:Axiom`` reifications.
    """
    rows = []
    for axiom in graph.subjects(OWL.annotatedSource, subject):
        if (axiom, OWL.annotatedProperty, predicate) not in graph:
            continue
        rows.append(
            {
                "target": graph.value(axiom, OWL.annotatedTarget),
                "quote": str(graph.value(axiom, LXO.exactQuote) or ""),
                "start": graph.value(axiom, LXO.charStart),
                "end": graph.value(axiom, LXO.charEnd),
                "alignment": str(graph.value(axiom, LXO.alignment) or ""),
                "model": str(graph.value(axiom, LXO.extractedBy) or ""),
            }
        )
    return rows
