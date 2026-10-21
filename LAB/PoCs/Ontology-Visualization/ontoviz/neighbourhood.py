"""Search-first ego view: degree-of-interest expansion under a hard cap.

A simplified form of van Ham & Perer's "search, show context, expand on demand"
(InfoVis 2009). Starting at the seed, candidates are taken best-first by

    DOI(n) = w_kind(edge reaching n) - 0.5 * hops(n) + 0.25 * API(n)

where API is the log-scaled degree. Best-first order keeps the view connected (a node
enters only through a node already in the view). Two limits are always enforced:

* ``cap``        the most nodes a view may hold (seed included);
* ``hub_limit``  a non-seed node with more neighbours than this is *guarded*: it is
  shown, but its neighbours are not pulled in until the user confirms the expansion
  (it is listed in ``expand``). This is the "big-node guard" used by Siren and Bloom.
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field

from .index import DEFAULT_KINDS, Edge, OntologyIndex

KIND_WEIGHT = {"subClassOf": 1.0, "equivalentClass": 1.0, "broader": 1.0,
               "restriction": 0.8, "objectProperty": 0.6, "optional": 0.4, "disjointWith": 0.3}
HOP_PENALTY, API_WEIGHT = 0.5, 0.25


@dataclass
class View:
    seed: str
    nodes: dict[str, dict] = field(default_factory=dict)    # iri -> {dist, doi, via}
    edges: list[Edge] = field(default_factory=list)
    guarded: dict[str, int] = field(default_factory=dict)   # iri -> neighbours held back
    hidden: dict[str, int] = field(default_factory=dict)    # iri -> neighbours not shown
    candidates: int = 0
    truncated: int = 0
    params: dict = field(default_factory=dict)
    ms: float = 0.0


def doi(index: OntologyIndex, iri: str, dist: int, kind: str) -> float:
    return KIND_WEIGHT.get(kind, 0.5) - HOP_PENALTY * dist + API_WEIGHT * index.api(iri)


def neighbourhood(index: OntologyIndex, seed: str, *, hops: int = 2, cap: int = 60,
                  kinds=DEFAULT_KINDS, hub_limit: int = 25, expand=(), extra=()) -> View:
    """``extra`` edges (e.g. inferred superclasses) join the adjacency for this view only."""
    if seed not in index.nodes:
        raise KeyError(f"{seed} is not a class or concept in this ontology")
    if cap < 1 or hops < 0:
        raise ValueError("cap must be >= 1 and hops >= 0")
    t0 = time.perf_counter()
    kinds, expand = tuple(kinds), set(expand)
    more: dict[str, list[tuple[str, Edge]]] = {}
    for e in extra:
        if e.kind in kinds and e.source in index.nodes and e.target in index.nodes:
            more.setdefault(e.source, []).append((e.target, e))
            more.setdefault(e.target, []).append((e.source, e))

    def nbrs(n: str) -> list[tuple[str, Edge]]:
        return index.neighbours(n, kinds) + more.get(n, [])

    view = View(seed, params={"hops": hops, "cap": cap, "kinds": list(kinds),
                              "hub_limit": hub_limit, "expand": sorted(expand)})
    view.nodes[seed] = {"dist": 0, "doi": None, "via": None}
    seen = {seed}
    heap: list = []

    def push_from(n: str, dist: int) -> None:
        for m, e in nbrs(n):
            if m not in view.nodes:
                seen.add(m)
                heapq.heappush(heap, (-doi(index, m, dist + 1, e.kind), dist + 1, m, e.kind))

    if hops > 0:
        push_from(seed, 0)
    while heap and len(view.nodes) < cap:
        neg, dist, m, kind = heapq.heappop(heap)
        if m in view.nodes:
            continue
        view.nodes[m] = {"dist": dist, "doi": round(-neg, 4), "via": kind}
        if dist >= hops:
            continue
        if len({x for x, _ in nbrs(m)}) > hub_limit and m not in expand:
            view.guarded[m] = 0            # filled in below
            continue
        push_from(m, dist)

    inside = view.nodes.keys()
    keys = set()
    for n in inside:
        out = 0
        for m, e in nbrs(n):
            if m in inside:
                if e.key not in keys:
                    keys.add(e.key)
                    view.edges.append(e)
            else:
                out += 1
        if out:
            view.hidden[n] = out
    for g in view.guarded:
        view.guarded[g] = view.hidden.get(g, 0)
    view.edges.sort(key=lambda e: e.key)
    view.candidates = len(seen)
    view.truncated = len(seen - set(inside))
    view.ms = round((time.perf_counter() - t0) * 1000, 2)
    return view
