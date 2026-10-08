"""Quad store abstraction: one interface, two realisations.

``InMemoryStore`` (rdflib ``Dataset``) runs everything offline and in tests;
``FusekiStore`` speaks SPARQL 1.1 Update + Graph Store Protocol to Apache Jena
Fuseki and is the production canonical store.

The interface is deliberately narrow, and it has exactly **one** write method,
:meth:`Store.apply`. That is the generalisation of Semantic Turkey's SAIL
interception (every write passes ``ChangeTrackerConnection``) to a store that has
no interception point: if the only way in is ``apply``, then whoever calls
``apply`` — the change tracker — sees every write. Reads hand out read-only
views so a feature cannot write around the tracker by accident.
"""

from __future__ import annotations

import threading
from typing import Iterable, Iterator, Protocol, runtime_checkable

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.graph import ReadOnlyGraphAggregate
from rdflib.term import Node

Quad = tuple[Node, Node, Node, URIRef]

__all__ = ["Quad", "Store", "InMemoryStore", "FusekiStore", "union_view", "materialise"]


@runtime_checkable
class Store(Protocol):
    def graph(self, iri: URIRef) -> Graph: ...
    def graphs(self) -> set[URIRef]: ...
    def contains(self, quad: Quad) -> bool: ...
    def apply(self, additions: Iterable[Quad], removals: Iterable[Quad]) -> None: ...
    def query(self, sparql: str, graphs: Iterable[URIRef] | None = None): ...
    def size(self, iri: URIRef) -> int: ...


def union_view(store: Store, iris: Iterable[URIRef]) -> Graph:
    """A read-only union of several named graphs (``main ∪ imports ∪ inferred``)."""
    return ReadOnlyGraphAggregate([store.graph(i) for i in iris])


def materialise(store: Store, include: Iterable[URIRef],
                exclude: Iterable[URIRef] = ()) -> Graph:
    """``⋃ include ∖ ⋃ exclude`` as a fresh, writable graph.

    This is the staged read of Semantic Turkey's validation mode:
    ``main ∪ staging-add ∖ staging-del`` — what the ontology *would* be if every
    pending proposal were accepted.
    """
    out = Graph()
    for iri in include:
        for t in store.graph(iri):
            out.add(t)
    for iri in exclude:
        for t in store.graph(iri):
            out.remove(t)
    return out


class InMemoryStore:
    """rdflib ``Dataset`` with a single-writer lock — the TDB2 discipline, offline."""

    def __init__(self) -> None:
        self.ds = Dataset(default_union=False)
        self._lock = threading.RLock()

    # -- reads -------------------------------------------------------------- #
    def _g(self, iri: URIRef) -> Graph:
        return self.ds.graph(URIRef(iri))

    def graph(self, iri: URIRef) -> Graph:
        return ReadOnlyGraphAggregate([self._g(iri)])

    def graphs(self) -> set[URIRef]:
        return {g.identifier for g in self.ds.graphs()
                if isinstance(g.identifier, URIRef) and len(g) > 0}

    def contains(self, quad: Quad) -> bool:
        s, p, o, g = quad
        return (s, p, o) in self._g(g)

    def size(self, iri: URIRef) -> int:
        return len(self._g(iri))

    def query(self, sparql: str, graphs: Iterable[URIRef] | None = None):
        if graphs is None:
            return self.ds.query(sparql)
        return union_view(self, list(graphs)).query(sparql)

    # -- the one write path -------------------------------------------------- #
    def apply(self, additions: Iterable[Quad], removals: Iterable[Quad]) -> None:
        """Removals first, then additions, atomically under the writer lock.

        Removing first means a change set that moves a triple between graphs, or
        rewrites a value in place, lands in the intended final state.
        """
        rem, add = list(removals), list(additions)
        with self._lock:
            for s, p, o, g in rem:
                self._g(g).remove((s, p, o))
            for s, p, o, g in add:
                self._g(g).add((s, p, o))

    def load(self, iri: URIRef, data: str | Graph, fmt: str = "turtle") -> int:
        """Bulk-load bypassing tracking. Only for bootstrapping/tests and import
        graphs, which are derived content and not editable."""
        src = data if isinstance(data, Graph) else Graph().parse(data=data, format=fmt)
        with self._lock:
            g = self._g(iri)
            for t in src:
                g.add(t)
        return len(src)

    def drop(self, iri: URIRef) -> None:
        with self._lock:
            self.ds.remove_graph(self._g(iri))


def _nt(term: Node, bnodes: str = "label") -> str:
    """N-Triples form of *term*. In an ``INSERT DATA`` blank nodes keep their label
    (fresh nodes, consistent within one request); in a ``DELETE`` template they
    become variables, because a blank node cannot be addressed across requests."""
    if isinstance(term, BNode):
        return f"_:{term}" if bnodes == "label" else f"?b_{term}"
    return term.n3()


class FusekiStore:
    """Fuseki over HTTP. Every :meth:`apply` is ONE SPARQL Update request — so the
    content delta and its history record land in one TDB2 transaction or not at all.

    ``client`` is duck-typed against ``ontology_modeler.fuseki.FusekiClient``
    (``update``, ``get_graph``, ``select``), which this repository already uses
    live against the 133k-triple dataset; nothing is re-implemented.
    """

    def __init__(self, client) -> None:
        self.client = client
        self._lock = threading.RLock()

    def graph(self, iri: URIRef) -> Graph:
        return ReadOnlyGraphAggregate([self.client.get_graph(str(iri))])

    def graphs(self) -> set[URIRef]:
        rows = self.client.select("SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }")
        return {URIRef(r["g"]) for r in rows}

    def contains(self, quad: Quad) -> bool:
        s, p, o, g = quad
        return self.client.ask(
            f"ASK {{ GRAPH <{g}> {{ {_nt(s, 'var')} {_nt(p, 'var')} {_nt(o, 'var')} }} }}")

    def size(self, iri: URIRef) -> int:
        rows = self.client.select(
            f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{iri}> {{ ?s ?p ?o }} }}")
        return int(rows[0]["n"]) if rows else 0

    def query(self, sparql: str, graphs: Iterable[URIRef] | None = None):
        return self.client.select(sparql)

    @staticmethod
    def update_text(additions: Iterable[Quad], removals: Iterable[Quad]) -> str:
        """One SPARQL Update request: ground removals as ``DELETE DATA``, removals
        that touch blank nodes as a ``DELETE … WHERE`` whose blank nodes are
        variables (the bnode-closure technique of ``ontology_modeler/diff.py``),
        then ``INSERT DATA``. Operations in one request share a transaction."""
        def block(quads: Iterable[Quad], bnodes: str) -> str:
            by_g: dict[URIRef, list[str]] = {}
            for s, p, o, g in quads:
                by_g.setdefault(g, []).append(
                    f"{_nt(s, bnodes)} {_nt(p, bnodes)} {_nt(o, bnodes)} .")
            return "\n".join(f"GRAPH <{g}> {{ " + " ".join(ts) + " }}"
                             for g, ts in by_g.items())
        rem, add = list(removals), list(additions)
        ground = [q for q in rem if not any(isinstance(t, BNode) for t in q[:3])]
        anon = [q for q in rem if any(isinstance(t, BNode) for t in q[:3])]
        parts = []
        if ground:
            parts.append("DELETE DATA { " + block(ground, "label") + " }")
        if anon:
            pattern = block(anon, "var")
            parts.append(f"DELETE {{ {pattern} }} WHERE {{ {pattern} }}")
        if add:
            parts.append("INSERT DATA { " + block(add, "label") + " }")
        return " ;\n".join(parts)

    def apply(self, additions: Iterable[Quad], removals: Iterable[Quad]) -> None:
        text = self.update_text(additions, removals)
        if text:
            with self._lock:
                self.client.update(text)


def iter_quads(graph: Graph, g: URIRef) -> Iterator[Quad]:
    for s, p, o in graph:
        yield (s, p, o, g)


def lit(value, lang: str | None = None, datatype: URIRef | None = None) -> Literal:
    return Literal(value, lang=lang, datatype=datatype)
