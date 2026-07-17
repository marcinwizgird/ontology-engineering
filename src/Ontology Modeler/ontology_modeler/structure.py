"""StructureExplorer -- queries for comprehending ontology structure.

Inventory (classes, object/data properties, SKOS relations), hierarchy analysis
(super/subclasses, roots/leaves, cross-ontology subclass edges), object-property
analysis, and a cross-ontology dependency matrix. Every method returns a pandas
DataFrame whose rows are JSON-serialisable, so each is a ready-made agent function-tool.

Two invariants, learned from the loaded FIBO data:
  * Scope by ontology IRI *namespace* (STRSTARTS on the entity IRI), because that is the
    identifier an agent will have -- not a file or graph path.
  * Transitive hierarchy queries are unqualified (union default graph) so rdfs:subClassOf+
    crosses ontology boundaries; wrapping a path in GRAPH ?g evaluates it per file and
    silently drops cross-ontology ancestry.
"""

from __future__ import annotations

from typing import Optional

from .fuseki import FusekiClient

SKOS_RELATIONS = [
    "broader", "narrower", "broaderTransitive", "narrowerTransitive", "related",
    "broadMatch", "narrowMatch", "exactMatch", "closeMatch", "relatedMatch",
    "mappingRelation", "isNarrowerThan", "isBroaderThan",
]


def _scope(var: str, ontology: Optional[str]) -> str:
    """A FILTER restricting `var` to an ontology's IRI namespace, or '' for no scope."""
    return f'FILTER(STRSTARTS(STR({var}), "{ontology}"))' if ontology else ""


class StructureExplorer:
    """Structural queries over a Fuseki dataset via the shared client."""

    def __init__(self, client: FusekiClient | None = None):
        self.client = client or FusekiClient()

    def _df(self, sparql: str):
        return self.client.select_df(sparql)

    # -- inventory ----------------------------------------------------------- #

    def list_ontologies(self):
        """Every owl:Ontology header: IRI, label, and the named graph holding it.

        The returned `ontology` IRI is what you pass as `ontology=` to the other methods.
        """
        return self._df("""
            SELECT ?ontology ?label ?graph WHERE {
              GRAPH ?graph { ?ontology a owl:Ontology
                             OPTIONAL { ?ontology rdfs:label ?label } }
            } ORDER BY ?ontology
        """)

    def classes(self, ontology: Optional[str] = None):
        """All owl:Class entities (class, label, definition), optionally scoped."""
        return self._df(f"""
            SELECT DISTINCT ?class ?label ?definition WHERE {{
              ?class a owl:Class FILTER(isIRI(?class))
              {_scope("?class", ontology)}
              OPTIONAL {{ ?class rdfs:label ?label }}
              OPTIONAL {{ ?class skos:definition ?definition }}
            }} ORDER BY ?label ?class
        """)

    def object_properties(self, ontology: Optional[str] = None):
        """owl:ObjectProperty entities with named domain/range and label."""
        return self._df(f"""
            SELECT DISTINCT ?property ?label ?domain ?range WHERE {{
              ?property a owl:ObjectProperty FILTER(isIRI(?property))
              {_scope("?property", ontology)}
              OPTIONAL {{ ?property rdfs:label  ?label }}
              OPTIONAL {{ ?property rdfs:domain ?domain FILTER(isIRI(?domain)) }}
              OPTIONAL {{ ?property rdfs:range  ?range  FILTER(isIRI(?range)) }}
            }} ORDER BY ?label ?property
        """)

    def data_properties(self, ontology: Optional[str] = None):
        """owl:DatatypeProperty entities with domain, datatype range and label."""
        return self._df(f"""
            SELECT DISTINCT ?property ?label ?domain ?datatype WHERE {{
              ?property a owl:DatatypeProperty FILTER(isIRI(?property))
              {_scope("?property", ontology)}
              OPTIONAL {{ ?property rdfs:label  ?label }}
              OPTIONAL {{ ?property rdfs:domain ?domain FILTER(isIRI(?domain)) }}
              OPTIONAL {{ ?property rdfs:range  ?datatype }}
            }} ORDER BY ?label ?property
        """)

    def skos_relations(self, ontology: Optional[str] = None):
        """SKOS semantic/mapping relations (broader/narrower/*Match/related/...) present.

        FIBO barely uses these -- its hierarchy is rdfs:subClassOf -- but the method works
        for vocabularies that do, and documents the gap for those that don't.
        """
        values = " ".join(f"skos:{r}" for r in SKOS_RELATIONS)
        return self._df(f"""
            SELECT ?source ?relation ?target WHERE {{
              VALUES ?relation {{ {values} }}
              ?source ?relation ?target
              {_scope("?source", ontology)}
            }} ORDER BY ?relation ?source
        """)

    def skos_relation_summary(self):
        """Count of every SKOS predicate in use (relations and annotations)."""
        return self._df("""
            SELECT ?predicate (COUNT(*) AS ?count) WHERE {
              ?s ?predicate ?o
              FILTER(STRSTARTS(STR(?predicate), "http://www.w3.org/2004/02/skos/core#"))
            } GROUP BY ?predicate ORDER BY DESC(?count)
        """)

    # -- hierarchy ----------------------------------------------------------- #

    def superclasses(self, cls: str, direct: bool = True):
        """Named superclasses of a class. direct=False walks the full ancestry
        (rdfs:subClassOf+, unqualified so it crosses ontologies)."""
        step = "rdfs:subClassOf" if direct else "rdfs:subClassOf+"
        return self._df(f"""
            SELECT DISTINCT ?superclass ?label WHERE {{
              <{cls}> {step} ?superclass FILTER(isIRI(?superclass) && ?superclass != <{cls}>)
              OPTIONAL {{ ?superclass rdfs:label ?label }}
            }} ORDER BY ?label
        """)

    def subclasses(self, cls: str, direct: bool = True):
        """Named subclasses (descendants) of a class. `direct` mirrors superclasses."""
        step = "rdfs:subClassOf" if direct else "rdfs:subClassOf+"
        return self._df(f"""
            SELECT DISTINCT ?subclass ?label WHERE {{
              ?subclass {step} <{cls}> FILTER(isIRI(?subclass) && ?subclass != <{cls}>)
              OPTIONAL {{ ?subclass rdfs:label ?label }}
            }} ORDER BY ?label
        """)

    def roots_and_leaves(self, ontology: str):
        """Classify each class in an ontology as root (no named superclass) / leaf
        (no named subclass). Scope is required."""
        return self._df(f"""
            SELECT ?class ?label (!BOUND(?parent) AS ?is_root) (!BOUND(?child) AS ?is_leaf) WHERE {{
              {{
                SELECT ?class (SAMPLE(?p) AS ?parent) (SAMPLE(?c) AS ?child) WHERE {{
                  ?class a owl:Class FILTER(isIRI(?class))
                  {_scope("?class", ontology)}
                  OPTIONAL {{ ?class rdfs:subClassOf ?p FILTER(isIRI(?p) && ?p != ?class) }}
                  OPTIONAL {{ ?c rdfs:subClassOf ?class FILTER(isIRI(?c) && ?c != ?class) }}
                }} GROUP BY ?class
              }}
              OPTIONAL {{ ?class rdfs:label ?label }}
            }} ORDER BY DESC(?is_root) ?label
        """)

    def cross_ontology_subclass_edges(self, min_edges: int = 1):
        """Subclass edges whose child and parent live in different ontologies, per pair.

        Each class is attributed to its ontology via the named graph it was loaded from
        (one file = one graph = one owl:Ontology), exact regardless of IRI nesting.
        """
        return self._df(f"""
            SELECT ?child_ontology ?parent_ontology (COUNT(*) AS ?edges) WHERE {{
              GRAPH ?gc {{ ?c a owl:Class ; rdfs:subClassOf ?p FILTER(isIRI(?c) && isIRI(?p)) }}
              GRAPH ?gc {{ ?child_ontology  a owl:Ontology }}
              GRAPH ?gp {{ ?p a owl:Class . ?parent_ontology a owl:Ontology }}
              FILTER(?gc != ?gp)
            }}
            GROUP BY ?child_ontology ?parent_ontology
            HAVING (COUNT(*) >= {int(min_edges)})
            ORDER BY DESC(?edges)
        """)

    # -- object-property analysis ------------------------------------------- #

    def property_domain_range(self, ontology: Optional[str] = None):
        """Object properties with named domain AND range classes."""
        return self._df(f"""
            SELECT DISTINCT ?property ?label ?domain ?range WHERE {{
              ?property a owl:ObjectProperty ; rdfs:domain ?domain ; rdfs:range ?range
              FILTER(isIRI(?property) && isIRI(?domain) && isIRI(?range))
              {_scope("?property", ontology)}
              OPTIONAL {{ ?property rdfs:label ?label }}
            }} ORDER BY ?label
        """)

    def cross_ontology_object_properties(self):
        """Object properties whose domain and range live in different ontologies, per pair."""
        return self._df("""
            SELECT ?domain_ontology ?range_ontology (COUNT(DISTINCT ?property) AS ?properties) WHERE {
              GRAPH ?gp { ?property a owl:ObjectProperty ; rdfs:domain ?d ; rdfs:range ?r
                          FILTER(isIRI(?d) && isIRI(?r)) }
              GRAPH ?gd { ?d a owl:Class . ?domain_ontology a owl:Ontology }
              GRAPH ?gr { ?r a owl:Class . ?range_ontology  a owl:Ontology }
              FILTER(?gd != ?gr)
            }
            GROUP BY ?domain_ontology ?range_ontology
            ORDER BY DESC(?properties)
        """)

    def dependency_matrix(self):
        """child-ontology x parent-ontology matrix of cross-ontology subclass edge counts.

        A non-zero cell [A, B] means classes in A are subclasses of classes in B -- i.e.
        A structurally depends on B. Short labels (segment after /ontology/) keep it legible.
        """
        edges = self.cross_ontology_subclass_edges(min_edges=1)

        def short(iri: str) -> str:
            s = iri.rstrip("/").split("/ontology/")[-1]
            return s if len(s) <= 40 else s[:37] + "..."

        edges = edges.copy()
        edges["child"] = edges["child_ontology"].map(short)
        edges["parent"] = edges["parent_ontology"].map(short)
        edges["edges"] = edges["edges"].astype(int)
        return (edges.pivot_table(index="child", columns="parent", values="edges",
                                  aggfunc="sum", fill_value=0).astype(int))
