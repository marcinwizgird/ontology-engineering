"""The query graph: which classes connect, through which properties, at what cost.

Nodes are the mapped FIBEN classes. Edges:

* object-property edges from the allowed (domain, property, range) triples, cost 1.0;
* ``rdfs:subClassOf`` edges, cost 0.3 — cheap, because the reasoner (Ontop) handles the
  hierarchy and a subclass and its parent are the *same individual*.

Properties are inherited: a ListedSecurity is a Security, so ``isProvidedBy`` (declared
on Security) is usable from a ListedSecurity node by crossing the subclass edge.
Unmapped relations simply do not exist here — that is the coverage constraint.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import networkx as nx

from . import knowledge

SUBCLASS_COST = 0.3
EDGE_COST = 1.0


@dataclass(frozen=True)
class Edge:
    src: str
    prop: str               # property local name, or "subClassOf"
    dst: str


class QueryGraph:
    def __init__(self):
        pack = knowledge.load()
        self.pack = pack
        self.classes = {t.local for t in pack.mapped() if t.kind == "class"}
        self.parent = dict(pack.subclass)
        self.obj_edges: list[Edge] = []
        self.data_props: dict[str, set[str]] = {c: set() for c in self.classes}
        self.prop_domains: dict[str, set[str]] = {}
        self.prop_kind: dict[str, str] = {}
        for d, p, r in pack.edges:
            if r in self.classes:
                self.obj_edges.append(Edge(d, p, r))
                self.prop_kind[p] = "object"
            else:
                self.data_props.setdefault(d, set()).add(p)
                self.prop_kind[p] = "datatype"
            self.prop_domains.setdefault(p, set()).add(d)
        self.g = nx.Graph()
        self.g.add_nodes_from(self.classes)
        self.via: dict[frozenset, list[Edge]] = {}
        # Inherited edges instead of subclass edges: if A -p-> B is allowed, then every
        # subclass C of A may have p to every subclass D of B. Walking up and down the
        # hierarchy would otherwise "connect" disjoint siblings through a common ancestor.
        self.children: dict[str, set[str]] = {}
        for c, p in self.parent.items():
            self.children.setdefault(p, set()).add(c)
        for e in self.obj_edges:
            for c in self.descendants(e.src):
                for d in self.descendants(e.dst):
                    self._add(Edge(c, e.prop, d), EDGE_COST)

    def _add(self, e: Edge, cost: float) -> None:
        if e.src == e.dst:
            return
        key = frozenset((e.src, e.dst))
        if e in self.via.get(key, []):
            return
        self.via.setdefault(key, []).append(e)
        w = min(cost, self.g[e.src][e.dst]["weight"]) if self.g.has_edge(e.src, e.dst) else cost
        self.g.add_edge(e.src, e.dst, weight=w)

    # ----- hierarchy -----------------------------------------------------------
    def descendants(self, c: str) -> list[str]:
        out, todo = [c], [c]
        while todo:
            for ch in self.children.get(todo.pop(), ()):
                out.append(ch)
                todo.append(ch)
        return out

    def ancestors(self, c: str) -> list[str]:
        out = []
        while c in self.parent:
            c = self.parent[c]
            out.append(c)
        return out

    def attributes(self, c: str) -> set[str]:
        """Datatype properties usable on *c* (own and inherited)."""
        out = set(self.data_props.get(c, set()))
        for a in self.ancestors(c):
            out |= self.data_props.get(a, set())
        return out

    def domains_of(self, prop: str) -> set[str]:
        """Classes on which *prop* can be used, including subclasses of declared domains."""
        base = self.prop_domains.get(prop, set())
        return {c for c in self.classes if c in base or any(a in base for a in self.ancestors(c))}

    def edges_between(self, a: str, b: str) -> list[Edge]:
        return self.via.get(frozenset((a, b)), [])

    def allowed(self, s_cls: str, prop: str, o_cls: str | None) -> bool:
        """Ontology check: may an individual of *s_cls* have *prop* (to an *o_cls*)?"""
        chain_s = [s_cls] + self.ancestors(s_cls)
        if self.prop_kind.get(prop) == "datatype":
            return any(prop in self.data_props.get(c, ()) for c in chain_s)
        for e in self.obj_edges:
            if e.prop != prop or e.src not in chain_s:
                continue
            if o_cls is None:
                return True
            chain_o = [o_cls] + self.ancestors(o_cls)
            # the object may be the declared range, a subclass of it, or a superclass of it
            if e.dst in chain_o or o_cls in ([e.dst] + self.ancestors(e.dst)):
                return True
        return False

    def directed(self, a: str, b: str) -> list[tuple[str, str, str]]:
        """Triples (subject class, property, object class) realising a step a~b."""
        out = []
        for e in self.edges_between(a, b):
            out.append((e.src, e.prop, e.dst))
        return out


@lru_cache(maxsize=1)
def load() -> QueryGraph:
    return QueryGraph()
