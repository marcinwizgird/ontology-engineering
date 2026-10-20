"""Graph re-ranking: choose the combination of candidates that fits together in the graph.

Each mention (a phrase from the question) has a few candidates from text retrieval —
classes, properties, or values (a value is a (class, property) anchor). For every
combination (one candidate per mention) the *terminal classes* are collected and the
cheapest subgraph connecting them is computed — for two terminals the k cheapest simple
paths (alternatives for the planner), for more a Steiner tree (2-approximation).
Combinations are scored

    score = sum_i text_i - lambda * tree_cost      (-inf when the terminals do not connect)

Edges named by curated path hints (glossary entries matching the question) are
discounted, so the intended route can beat a merely shorter one. When nothing connects,
the result says so — the signal for clarification or refusal.

Alternative scorer ``ppr``: Personalized PageRank seeded with all candidates; compared
with ``steiner`` in the H1 experiment.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import networkx as nx
from networkx.algorithms.approximation import steiner_tree

from .querygraph import QueryGraph, load as load_graph


@dataclass
class Candidate:
    kind: str               # class | object | datatype | value
    local: str              # class or property local name (value: the property)
    text: float             # retrieval score, normalised to [0, 1]
    cls: str | None = None  # value / attribute anchor class
    value: str | None = None


@dataclass
class Mention:
    text: str
    candidates: list[Candidate]


@dataclass
class Grounding:
    handle: str
    score: float
    choice: list[Candidate]                  # one candidate per mention
    classes: list[str]
    tree: list[tuple[str, str, str]]         # (subject class, property, object class)
    cost: float
    connected: bool = True
    notes: list[str] = field(default_factory=list)


def _anchor_options(c: Candidate, g: QueryGraph) -> list[frozenset[str]]:
    """Alternative terminal sets a candidate imposes."""
    if c.kind == "class":
        return [frozenset([c.local])] if c.local in g.classes else []
    if c.kind == "value":
        return [frozenset([c.cls])] if c.cls else []
    if c.kind == "datatype":
        if c.cls:
            return [frozenset([c.cls])]
        doms = sorted(g.prop_domains.get(c.local, set()))
        return [frozenset([d]) for d in doms[:4]]
    if c.kind == "object":
        es = [e for e in g.obj_edges if e.prop == c.local]
        return [frozenset([e.src, e.dst]) for e in es[:4]]
    return []


def _reduce(g: QueryGraph, terms: set[str]) -> set[str]:
    """A terminal that is an ancestor of another terminal is the same individual."""
    return {t for t in terms if not any(t in g.ancestors(o) for o in terms if o != t)}


def _weighted(g: QueryGraph, discount: set[str]) -> nx.Graph:
    if not discount:
        return g.g
    h = g.g.copy()
    for a, b, d in h.edges(data=True):
        props = {e.prop for e in g.edges_between(a, b)}
        if props & discount or (a in discount and b in discount):
            d["weight"] = d["weight"] * 0.5
    return h


def _trees(g: QueryGraph, h: nx.Graph, terminals: set[str], alternatives: int = 3):
    """[(cost, [(s, p, o)...]), ...] cheapest first; [] when not connected."""
    terminals = {t for t in _reduce(g, terminals) if t in h}
    if not terminals:
        return []
    if len(terminals) == 1:
        return [(0.0, [])]
    if len(terminals) == 2:
        a, b = sorted(terminals)
        if not nx.has_path(h, a, b):
            return []
        out = []
        for path in itertools.islice(nx.shortest_simple_paths(h, a, b, weight="weight"), alternatives):
            out.append(_as_triples(g, h, list(zip(path, path[1:]))))
        return out
    comp = nx.node_connected_component(h, next(iter(terminals)))
    if not terminals <= comp:
        return []
    st = steiner_tree(h.subgraph(comp), list(terminals), weight="weight")
    return [_as_triples(g, h, list(st.edges()))]


def _as_triples(g: QueryGraph, h: nx.Graph, pairs):
    cost, triples = 0.0, []
    for a, b in pairs:
        cost += h[a][b]["weight"]
        step = g.directed(a, b)
        triples.append(step[0] if step else (a, "?", b))
    return cost, triples


def rank(mentions: list[Mention], lam: float = 0.25, k: int = 3, top: int = 5,
         scorer: str = "steiner", graph: QueryGraph | None = None,
         discount: set[str] | None = None) -> list[Grounding]:
    g = graph or load_graph()
    pools = [m.candidates[:k] or [None] for m in mentions]
    if scorer == "ppr":
        return _rank_ppr(g, pools, top)
    h = _weighted(g, discount or set())
    out: list[Grounding] = []
    for combo in itertools.islice(itertools.product(*pools), 3000):
        choice = [c for c in combo if c is not None]
        text = sum(c.text for c in choice)
        options = [_anchor_options(c, g) or [frozenset()] for c in choice]
        found = False
        for anchors in itertools.islice(itertools.product(*options), 64):
            terms = set().union(*anchors) if anchors else set()
            for cost, tree in _trees(g, h, terms):
                found = True
                out.append(Grounding("", text - lam * cost, choice, sorted(_reduce(g, terms)),
                                     tree, cost))
        if not found:
            out.append(Grounding("", -math.inf, choice, [], [], math.inf, connected=False,
                                 notes=["the chosen concepts do not connect in the mapped data"]))
    out.sort(key=lambda x: -x.score)
    seen, uniq = set(), []
    for gr in out:
        key = (tuple(gr.classes), tuple(gr.tree),
               tuple((c.kind, c.local, c.value) for c in gr.choice))
        if key in seen:
            continue
        seen.add(key)
        gr.handle = f"T{len(uniq) + 1}"
        uniq.append(gr)
        if len(uniq) >= top:
            break
    return uniq


def _rank_ppr(g: QueryGraph, pools, top) -> list[Grounding]:
    seed: dict[str, float] = {}
    for pool in pools:
        for c in pool:
            if c is None:
                continue
            for opt in _anchor_options(c, g):
                for a in opt:
                    seed[a] = seed.get(a, 0.0) + c.text
    if not seed:
        return []
    pr = nx.pagerank(g.g, alpha=0.85, personalization=seed, weight=None)

    def mass(c):
        return c.text + max((sum(pr.get(a, 0) for a in o) for o in _anchor_options(c, g)), default=0)
    choice = [max((c for c in pool if c), key=mass, default=None) for pool in pools]
    choice = [c for c in choice if c is not None]
    terms: set[str] = set()
    for c in choice:
        opts = _anchor_options(c, g)
        if opts:
            terms |= max(opts, key=lambda o: sum(pr.get(a, 0) for a in o))
    trees = _trees(g, g.g, terms, 1)
    if not trees:
        return [Grounding("T1", -math.inf, choice, sorted(terms), [], math.inf, False,
                          ["the chosen concepts do not connect in the mapped data"])]
    cost, tree = trees[0]
    return [Grounding("T1", sum(c.text for c in choice) - 0.25 * cost, choice,
                      sorted(_reduce(g, terms)), tree, cost)][:top]
