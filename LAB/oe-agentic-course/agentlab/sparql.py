"""One SPARQL interface over an in-memory rdflib graph.

Chapter 1 · Notebook 1 reads an ontology's vocabulary and axioms with SPARQL, and
the problem set queries submissions the same way. Everything a chapter needs fits
in memory, so this module wraps an rdflib graph; Chapter 8 (linking ontologies to
data) adds a live Fuseki backend behind the same methods.

Results are normalised to plain Python (``list[dict[str, str]]`` for SELECT), so
deterministic metrics can compare answers without caring where they came from.
"""

from __future__ import annotations

import rdflib

INTRODUCED_IN = 1

__all__ = ["SparqlStore", "PREFIXES", "with_prefixes"]

#: Prefixes prepended to every query, so exercises stay readable.
PREFIXES = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX awo:  <http://example.org/awo#>
PREFIX ex:   <http://example.org/oe/>
"""


def with_prefixes(query: str) -> str:
    """Prepend the standard prefixes unless the query declares its own."""
    return query if "PREFIX" in query.upper() else PREFIXES + query


class SparqlStore:
    """A SPARQL endpoint over a local rdflib graph."""

    def __init__(self, graph: rdflib.Graph | None = None):
        self.graph = graph if graph is not None else rdflib.Graph()

    @classmethod
    def in_memory(cls, ttl: str | None = None) -> "SparqlStore":
        """An in-memory store, optionally seeded with Turtle text."""
        store = cls()
        if ttl:
            store.load_text(ttl)
        return store

    def load_text(self, data: str, fmt: str = "turtle") -> "SparqlStore":
        self.graph.parse(data=data, format=fmt)
        return self

    def select(self, query: str) -> list[dict[str, str]]:
        """Run a SELECT and return rows as plain dicts of strings."""
        return [{str(v): "" if row[v] is None else str(row[v]) for v in row.labels}
                for row in self.graph.query(with_prefixes(query))]

    def ask(self, query: str) -> bool:
        return bool(self.graph.query(with_prefixes(query)).askAnswer)

    def construct(self, query: str) -> rdflib.Graph:
        g = rdflib.Graph()
        for triple in self.graph.query(with_prefixes(query)):
            g.add(triple)
        return g

    def update(self, query: str) -> None:
        self.graph.update(with_prefixes(query))

    def size(self) -> int:
        return len(self.graph)

    def __repr__(self) -> str:  # pragma: no cover - display only
        return f"<SparqlStore in-memory triples={self.size()}>"
