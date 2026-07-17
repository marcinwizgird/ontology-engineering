"""Extraction strategy: pull the TBox from Fuseki with SPARQL (spec Section 3).

Queries A (classes + lexical labels), B (subclass taxonomy, minus owl:Thing), and C
(object properties with named domain/range), run over the shared FusekiClient. All
unqualified over the union default graph, so the whole loaded TBox is seen as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..fuseki import FusekiClient
from ..rdf import short_name, rel_type_of, local_name

# Query A -- classes + labels + definitions + collapsed synonyms
QUERY_CLASSES = """
SELECT DISTINCT ?class ?label ?definition
       (GROUP_CONCAT(DISTINCT ?alt; separator="||") AS ?alt_labels)
WHERE {
  ?class rdf:type owl:Class .
  FILTER(isIRI(?class))
  OPTIONAL { ?class rdfs:label ?label }
  OPTIONAL { ?class skos:definition ?definition }
  OPTIONAL { ?class skos:altLabel ?alt }
}
GROUP BY ?class ?label ?definition
"""

# Query B -- subclass taxonomy, excluding owl:Thing roots
QUERY_TAXONOMY = """
SELECT DISTINCT ?subClass ?superClass WHERE {
  ?subClass rdfs:subClassOf ?superClass .
  FILTER(isIRI(?subClass) && isIRI(?superClass) && ?superClass != owl:Thing)
}
"""

# Query C -- object properties with named domain and range
QUERY_PROPERTIES = """
SELECT DISTINCT ?property ?label ?domain ?range ?definition WHERE {
  ?property rdf:type owl:ObjectProperty .
  ?property rdfs:domain ?domain .
  ?property rdfs:range ?range .
  OPTIONAL { ?property rdfs:label ?label }
  OPTIONAL { ?property rdfs:comment ?definition }
  FILTER(isIRI(?property) && isIRI(?domain) && isIRI(?range))
}
"""


@dataclass
class ClassRecord:
    """One :Class node's source data (spec 2.1)."""

    iri: str
    short_name: str
    name: str | None = None
    definition: str | None = None
    alt_labels: list[str] = field(default_factory=list)


@dataclass
class TaxonomyEdge:
    """One SUBCLASS_OF edge (spec 2.2)."""

    sub_iri: str
    super_iri: str


@dataclass
class PropertyEdge:
    """One object-property edge with its domain/range (spec 2.3)."""

    prop_iri: str
    rel_type: str
    name: str | None
    definition: str | None
    domain_iri: str
    range_iri: str


class TboxExtractor:
    """Pulls classes, taxonomy and object properties from Fuseki via the shared client."""

    def __init__(self, client: FusekiClient | None = None):
        self.client = client or FusekiClient()

    def ping(self) -> None:
        self.client.ping()

    def classes(self) -> list[ClassRecord]:
        records = []
        for r in self.client.select(QUERY_CLASSES):
            alt = r.get("alt_labels") or ""
            records.append(ClassRecord(
                iri=r["class"],
                short_name=short_name(r["class"]),
                name=r.get("label"),
                definition=r.get("definition"),
                alt_labels=[a for a in alt.split("||") if a],
            ))
        return records

    def taxonomy(self) -> list[TaxonomyEdge]:
        return [TaxonomyEdge(sub_iri=r["subClass"], super_iri=r["superClass"])
                for r in self.client.select(QUERY_TAXONOMY)]

    def object_properties(self) -> list[PropertyEdge]:
        return [PropertyEdge(
                    prop_iri=r["property"],
                    rel_type=rel_type_of(r["property"]),
                    name=r.get("label"),
                    definition=r.get("definition"),
                    domain_iri=r["domain"],
                    range_iri=r["range"],
                ) for r in self.client.select(QUERY_PROPERTIES)]
