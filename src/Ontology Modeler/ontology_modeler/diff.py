"""Incremental ontology updates: diff a new version against the store, patch with SPARQL.

Two responsibilities, deliberately split:

* OntologyDiffer -- pure, client-free. Given two rdflib graphs it computes a blank-node
  aware delta (UpdatePlan) and renders it as one atomic SPARQL update. The hard part is
  blank nodes: OWL writes restrictions and lists as anonymous subgraphs and Protege
  reassigns their ids on every save, so a naive triple diff reports unchanged structures
  as deleted-and-re-added. Ground triples diff by set difference; anonymous structures
  diff per named anchor by isomorphism.

* GraphSynchronizer -- takes a FusekiClient and applies a plan: fetch the old side, apply
  the patch in one transaction, verify the result is isomorphic to the target, and fall
  back to a full PUT when a diff is large, blank nodes are unsafe, or verification fails.

DELETE DATA of an absent triple and INSERT DATA of a present one are both no-ops, so a
patch converges on re-apply rather than corrupting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdflib import BNode, Graph
from rdflib.compare import isomorphic

from .fuseki import FusekiClient


# --------------------------------------------------------------------------- #
# Blank-node helpers                                                           #
# --------------------------------------------------------------------------- #

def has_bnode(triple) -> bool:
    return any(isinstance(t, BNode) for t in triple)


def named_anchors(graph: Graph) -> set:
    """Named subjects that link directly to a blank node."""
    return {s for s, p, o in graph if isinstance(o, BNode) and not isinstance(s, BNode)}


def bnode_closure(graph: Graph, root) -> set:
    """Every triple of the blank-node tree hanging off `root`.

    For an owl:Restriction this is the `<root> rdfs:subClassOf _:r` link plus `_:r`'s
    type/onProperty/filler triples. Assumes OWL's tree-shaped anonymous structures;
    shared blank nodes are reported by floating_bnodes and steer to the PUT fallback.
    """
    out: set = set()
    frontier = []
    for s, p, o in graph.triples((root, None, None)):
        if isinstance(o, BNode):
            out.add((s, p, o))
            frontier.append(o)
    seen: set = set()
    while frontier:
        b = frontier.pop()
        if b in seen:
            continue
        seen.add(b)
        for s, p, o in graph.triples((b, None, None)):
            out.add((s, p, o))
            if isinstance(o, BNode) and o not in seen:
                frontier.append(o)
    return out


def floating_bnodes(graph: Graph) -> set:
    """Blank nodes not reachable from any named anchor (shared or orphaned).

    Non-empty means per-anchor replacement can't be trusted complete -> PUT fallback.
    """
    reachable: set = set()
    for anchor in named_anchors(graph):
        for s, p, o in bnode_closure(graph, anchor):
            if isinstance(s, BNode):
                reachable.add(s)
            if isinstance(o, BNode):
                reachable.add(o)
    all_bnodes = {t for triple in graph for t in triple if isinstance(t, BNode)}
    return all_bnodes - reachable


def _ntriple(triple) -> str:
    """Serialise a triple as N-Triples (blank nodes as _:labels, valid in INSERT DATA)."""
    return " ".join(t.n3() for t in triple) + " ."


def _pattern(star: set) -> str:
    """Render an anonymous-structure star as a graph pattern with bnodes -> variables."""
    vmap: dict = {}
    def term(t):
        if isinstance(t, BNode):
            return vmap.setdefault(t, f"?b{len(vmap)}")
        return t.n3()
    ordered = sorted(star, key=lambda t: (isinstance(t[0], BNode), str(t)))
    return "\n".join(f"    {term(s)} {term(p)} {term(o)} ." for s, p, o in ordered)


def _closures_isomorphic(star_old: set, star_new: set) -> bool:
    if not star_old and not star_new:
        return True
    if bool(star_old) != bool(star_new):
        return False
    a, b = Graph(), Graph()
    for t in star_old:
        a.add(t)
    for t in star_new:
        b.add(t)
    return isomorphic(a, b)


# --------------------------------------------------------------------------- #
# Plan                                                                         #
# --------------------------------------------------------------------------- #

@dataclass
class UpdatePlan:
    """A blank-node-aware delta between two graphs, ready to render as SPARQL."""

    graph_uri: str
    ground_del: set = field(default_factory=set)
    ground_add: set = field(default_factory=set)
    del_stars: list = field(default_factory=list)   # [(anchor, {triples}), ...]
    add_stars: list = field(default_factory=list)
    unsafe: bool = False                             # floating/shared blank nodes

    @property
    def changed_triples(self) -> int:
        return (len(self.ground_del) + len(self.ground_add)
                + sum(len(s) for _, s in self.del_stars)
                + sum(len(s) for _, s in self.add_stars))

    @property
    def is_empty(self) -> bool:
        return self.changed_triples == 0

    def summary(self) -> str:
        lines = [
            f"ground deletions : {len(self.ground_del)}",
            f"ground additions : {len(self.ground_add)}",
            f"anonymous structures deleted (anchors): {len(self.del_stars)}",
            f"anonymous structures inserted (anchors): {len(self.add_stars)}",
            f"total triples changed: {self.changed_triples}",
        ]
        if self.unsafe:
            lines.append("WARNING: shared/floating blank nodes present -- prefer PUT fallback")
        return "\n".join(lines)

    def to_sparql(self) -> str:
        """Render the delta as one SPARQL update (';'-separated ops, deletions first)."""
        g = self.graph_uri
        ops: list[str] = []

        if self.ground_del:
            body = "\n".join("    " + _ntriple(t) for t in sorted(self.ground_del, key=str))
            ops.append(f"DELETE DATA {{\n  GRAPH <{g}> {{\n{body}\n  }}\n}}")

        for _anchor, star in self.del_stars:
            pattern = _pattern(star)
            ops.append(f"WITH <{g}>\nDELETE {{\n{pattern}\n}}\nWHERE {{\n{pattern}\n}}")

        insert_lines = [_ntriple(t) for t in sorted(self.ground_add, key=str)]
        for _anchor, star in self.add_stars:
            insert_lines.extend(_ntriple(t) for t in star)
        if insert_lines:
            body = "\n".join("    " + line for line in insert_lines)
            ops.append(f"INSERT DATA {{\n  GRAPH <{g}> {{\n{body}\n  }}\n}}")

        return " ;\n".join(ops)


class OntologyDiffer:
    """Pure, client-free diffing of two rdflib graphs."""

    @staticmethod
    def naive_diff(old: Graph, new: Graph) -> tuple[set, set]:
        """Plain set difference over ALL triples -- kept to show why it is wrong for OWL:
        blank-node relabelling makes unchanged structures look changed."""
        return set(old) - set(new), set(new) - set(old)

    @staticmethod
    def plan(old: Graph, new: Graph, graph_uri: str) -> UpdatePlan:
        """Compute the blank-node-aware delta from `old` to `new`."""
        plan = UpdatePlan(graph_uri=graph_uri)

        ground_old = {t for t in old if not has_bnode(t)}
        ground_new = {t for t in new if not has_bnode(t)}
        plan.ground_del = ground_old - ground_new
        plan.ground_add = ground_new - ground_old

        for anchor in named_anchors(old) | named_anchors(new):
            star_old = bnode_closure(old, anchor)
            star_new = bnode_closure(new, anchor)
            if not star_old and not star_new:
                continue
            if _closures_isomorphic(star_old, star_new):
                continue
            if star_old:
                plan.del_stars.append((anchor, star_old))
            if star_new:
                plan.add_stars.append((anchor, star_new))

        plan.unsafe = bool(floating_bnodes(old) or floating_bnodes(new))
        return plan


# --------------------------------------------------------------------------- #
# Synchronizer                                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class SyncResult:
    """Outcome of a GraphSynchronizer.sync call."""

    plan: UpdatePlan
    sparql: str
    method: str                  # 'incremental' | 'put' | 'incremental+put-fallback'
    ratio: float
    applied: bool = False
    verified: bool | None = None


class GraphSynchronizer:
    """Applies an ontology diff to a Fuseki named graph, with a full-PUT fallback."""

    def __init__(self, client: FusekiClient | None = None):
        self.client = client or FusekiClient()

    def verify(self, graph_uri: str, expected: Graph) -> bool:
        return isomorphic(self.client.get_graph(graph_uri), expected)

    def sync(self, graph_uri: str, new_graph: Graph, *,
             old_graph: Graph | None = None, dry_run: bool = False,
             fallback_threshold: float = 0.5) -> SyncResult:
        """Diff `new_graph` against the store and patch it incrementally.

        old_graph: the 'old' side; if None, fetched from Fuseki (recommended).
        dry_run: build the plan/SPARQL and choose a method, but do not apply.
        fallback_threshold: if changed triples exceed this fraction of the old graph
            (or blank nodes are unsafe), replace the whole graph with PUT instead.
        """
        old = old_graph if old_graph is not None else self.client.get_graph(graph_uri)
        plan = OntologyDiffer.plan(old, new_graph, graph_uri)
        sparql = plan.to_sparql()

        ratio = plan.changed_triples / max(len(old), 1)
        use_fallback = plan.unsafe or ratio > fallback_threshold
        result = SyncResult(plan=plan, sparql=sparql,
                            method="put" if use_fallback else "incremental", ratio=ratio)
        if dry_run:
            return result

        if plan.is_empty and not use_fallback:
            result.verified = self.verify(graph_uri, new_graph)
            return result

        if use_fallback:
            self.client.put_graph(graph_uri, new_graph)
        else:
            self.client.update(sparql)
        result.applied = True
        result.verified = self.verify(graph_uri, new_graph)

        # Guaranteed convergence: an incremental patch that didn't verify -> full PUT.
        if not result.verified and not use_fallback:
            self.client.put_graph(graph_uri, new_graph)
            result.method = "incremental+put-fallback"
            result.verified = self.verify(graph_uri, new_graph)

        return result
