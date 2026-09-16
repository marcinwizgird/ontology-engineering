"""One SPARQL interface over two backends: live Fuseki, or in-memory rdflib.

The course's agents call SPARQL through :class:`SparqlStore`, never through a
backend directly. ``SparqlStore.auto()`` probes ``infra/fuseki`` and falls back
to an embedded rdflib graph with an identical API, so every exercise runs with
or without Docker — and the *same* agent code is what students later point at a
real endpoint.

Results are normalised to plain Python (``list[dict[str, str]]`` for SELECT), so
deterministic evaluation metrics can compare answers across backends.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import rdflib

from oe_course import config

__all__ = ["SparqlStore", "fuseki_available", "PREFIXES", "with_prefixes"]

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


@functools.lru_cache(maxsize=1)
def fuseki_available() -> bool:
    """True when a Fuseki server answers ``/$/ping`` on the configured URL.

    Cached: probing on every tool call would dominate the runtime of an agent
    loop. Call ``fuseki_available.cache_clear()`` after starting Docker.
    """
    try:
        import requests

        r = requests.get(f"{config.FUSEKI_URL}/$/ping", timeout=config.FUSEKI_TIMEOUT)
        return r.ok
    except Exception:
        return False


class SparqlStore:
    """A SPARQL endpoint — Fuseki over HTTP, or a local rdflib graph."""

    def __init__(self, graph: rdflib.Graph | None = None, endpoint: str | None = None):
        self.endpoint = endpoint
        self.graph = graph if graph is not None else (None if endpoint else rdflib.Graph())

    # -- construction -------------------------------------------------------
    @classmethod
    def auto(cls, *, prefer_fuseki: bool = True) -> "SparqlStore":
        """Live Fuseki when reachable, otherwise a fresh in-memory graph."""
        if prefer_fuseki and fuseki_available():
            return cls(endpoint=f"{config.FUSEKI_URL}/{config.FUSEKI_DATASET}")
        return cls(graph=rdflib.Graph())

    @classmethod
    def in_memory(cls, ttl: str | None = None) -> "SparqlStore":
        """An in-memory store, optionally seeded with Turtle text."""
        store = cls(graph=rdflib.Graph())
        if ttl:
            store.load_text(ttl)
        return store

    @property
    def backend(self) -> str:
        return "fuseki" if self.endpoint else "rdflib-memory"

    # -- loading ------------------------------------------------------------
    def load_text(self, data: str, fmt: str = "turtle") -> "SparqlStore":
        if self.endpoint:
            self._post_update_data(data, fmt)
        else:
            self.graph.parse(data=data, format=fmt)
        return self

    def load_file(self, path: str | Path, fmt: str | None = None) -> "SparqlStore":
        path = Path(path)
        fmt = fmt or rdflib.util.guess_format(str(path)) or "turtle"
        return self.load_text(path.read_text(encoding="utf-8"), fmt)

    def _post_update_data(self, data: str, fmt: str) -> None:
        """Push a document into Fuseki's default graph via the GSP endpoint."""
        import requests

        mime = {
            "turtle": "text/turtle",
            "ttl": "text/turtle",
            "xml": "application/rdf+xml",
            "nt": "application/n-triples",
            "json-ld": "application/ld+json",
        }.get(fmt, "text/turtle")
        r = requests.post(
            f"{self.endpoint}/data?default",
            data=data.encode("utf-8"),
            headers={"Content-Type": mime},
            timeout=30,
        )
        r.raise_for_status()

    # -- querying -----------------------------------------------------------
    def select(self, query: str) -> list[dict[str, str]]:
        """Run a SELECT and return rows as plain dicts of strings."""
        query = with_prefixes(query)
        if self.endpoint:
            return self._remote_select(query)
        rows = []
        for row in self.graph.query(query):
            rows.append({str(v): _term_to_str(row[v]) for v in row.labels})
        return rows

    def ask(self, query: str) -> bool:
        query = with_prefixes(query)
        if self.endpoint:
            return bool(self._remote_json(query).get("boolean"))
        return bool(self.graph.query(query).askAnswer)

    def construct(self, query: str) -> rdflib.Graph:
        query = with_prefixes(query)
        if self.endpoint:
            import requests

            r = requests.post(
                f"{self.endpoint}/query",
                data={"query": query},
                headers={"Accept": "text/turtle"},
                timeout=30,
            )
            r.raise_for_status()
            return rdflib.Graph().parse(data=r.text, format="turtle")
        g = rdflib.Graph()
        for triple in self.graph.query(query):
            g.add(triple)
        return g

    def update(self, query: str) -> None:
        query = with_prefixes(query)
        if self.endpoint:
            import requests

            r = requests.post(f"{self.endpoint}/update", data={"update": query}, timeout=30)
            r.raise_for_status()
        else:
            self.graph.update(query)

    def size(self) -> int:
        if self.endpoint:
            rows = self.select("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
            return int(rows[0]["n"]) if rows else 0
        return len(self.graph)

    # -- remote helpers -----------------------------------------------------
    def _remote_json(self, query: str) -> dict[str, Any]:
        import requests

        r = requests.post(
            f"{self.endpoint}/query",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _remote_select(self, query: str) -> list[dict[str, str]]:
        payload = self._remote_json(query)
        out = []
        for binding in payload.get("results", {}).get("bindings", []):
            out.append({k: v.get("value", "") for k, v in binding.items()})
        return out

    def __repr__(self) -> str:  # pragma: no cover - display only
        where = self.endpoint or "in-memory"
        return f"<SparqlStore {self.backend} {where} triples={self.size()}>"


def _term_to_str(term) -> str:
    """Render an rdflib term the way the SPARQL JSON results format would."""
    if term is None:
        return ""
    return str(term)
