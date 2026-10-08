"""
NetworkX diagrams for the enrichment notebook.

Builds three views straight from the enricher's rdflib graphs:
  * hbim_taxonomy_graph  -- the original, fabricated HBIM SKOS taxonomy
  * fibo_subset_graph    -- the subset of FIBO actually used (class hierarchy + restrictions)
  * mapping_inference_graph -- HBIM + FIBO after mapping & reasoning (the outcome)

Each returns a networkx.DiGraph whose nodes carry {label, kind} and whose edges
carry {etype}; draw_graph() renders them with a shared colour/'style legend and a
tidy top-down (general-at-top) layered layout.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
from rdflib import RDF, RDFS, OWL, URIRef, BNode
from rdflib.namespace import SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import is_fibo, is_hbim          # noqa: E402
from enricher import q                        # noqa: E402

# ---- styling --------------------------------------------------------------
NODE_STYLE = {
    "hbim":     {"color": "#4C78A8", "label": "HBIM concept"},
    "fibo":     {"color": "#F58518", "label": "FIBO class"},
    "instance": {"color": "#54A24B", "label": "HBIM instance"},
}
EDGE_STYLE = {   # etype -> (colour, matplotlib linestyle, width, legend text)
    "broader":    ("#8C8C8C", "solid",  1.6, "skos:broader (HBIM taxonomy)"),
    "subClassOf": ("#E6A25C", "solid",  1.6, "rdfs:subClassOf (FIBO)"),
    "restriction":("#72B7B2", "dotted", 1.4, "FIBO restriction (some)"),
    "exact":      ("#2CA02C", "solid",  2.4, "exactMatch → owl:equivalentClass"),
    "bridge":     ("#2CA02C", "dashed", 1.8, "close/broadMatch → rdfs:subClassOf"),
    "inferred":   ("#D62728", "dashed", 1.8, "INFERRED rdfs:subClassOf"),
}
# edge types that mean "points to something more general" (used for layout)
_UPWARD = {"broader", "subClassOf", "bridge", "inferred"}
# per-type transparency + curvature so dense inferred edges stay legible
EDGE_ALPHA = {"inferred": 0.45, "bridge": 0.85, "exact": 0.95}
EDGE_RAD = {"inferred": 0.14, "restriction": 0.05}


# ---- graph builders -------------------------------------------------------
def hbim_taxonomy_graph(e) -> nx.DiGraph:
    G = nx.DiGraph()
    for c in e.hbim_concepts():
        G.add_node(str(c), label=q(e.hbim, c), kind="hbim")
    for c in e.hbim_concepts():
        for p in e.hbim.objects(c, SKOS.broader):
            G.add_edge(str(c), str(p), etype="broader")
    return G


def fibo_subset_graph(e, restrictions: bool = True) -> nx.DiGraph:
    G = nx.DiGraph()
    # named class -> named class subClassOf
    for s, o in e.fibo.subject_objects(RDFS.subClassOf):
        if isinstance(o, BNode) or isinstance(s, BNode):
            if restrictions and isinstance(o, BNode):
                prop = next(e.fibo.objects(o, OWL.onProperty), None)
                filler = next(e.fibo.objects(o, OWL.someValuesFrom), None)
                if prop is not None and filler is not None:
                    G.add_node(str(s), label=q(e.fibo, s), kind="fibo")
                    G.add_node(str(filler), label=q(e.fibo, filler), kind="fibo")
                    G.add_edge(str(s), str(filler), etype="restriction",
                               elabel=q(e.fibo, prop))
            continue
        G.add_node(str(s), label=q(e.fibo, s), kind="fibo")
        G.add_node(str(o), label=q(e.fibo, o), kind="fibo")
        G.add_edge(str(s), str(o), etype="subClassOf")
    return G


def mapping_inference_graph(e, subsumption: dict) -> nx.DiGraph:
    """HBIM + FIBO after mapping and reasoning (the enrichment outcome)."""
    G = nx.DiGraph()

    def add(node, kind_hint=None):
        s = str(node)
        if s not in G:
            kind = "hbim" if is_hbim(node) else ("fibo" if is_fibo(node) else "fibo")
            G.add_node(s, label=q(e.inferred, node), kind=kind_hint or kind)
        return s

    # HBIM concepts + their taxonomy
    for c in e.hbim_concepts():
        add(c)
    for c in e.hbim_concepts():
        for p in e.hbim.objects(c, SKOS.broader):
            add(p)
            G.add_edge(str(c), str(p), etype="broader")

    # mapping edges (asserted bridge) from the SKOS mappings
    for hb, fb in e.maps.subject_objects(SKOS.exactMatch):
        add(hb); add(fb); G.add_edge(str(hb), str(fb), etype="exact")
    for prop in (SKOS.closeMatch, SKOS.broadMatch):
        for hb, fb in e.maps.subject_objects(prop):
            add(hb); add(fb); G.add_edge(str(hb), str(fb), etype="bridge")

    # inferred FIBO ancestry (the outcome) + the FIBO hierarchy it lifts into
    for c in e.hbim_concepts():
        info = subsumption.get(q(e.inferred, c))
        if not info:
            continue
        for anc_q in info["inferred_ancestors"]:
            anc = _resolve(e, anc_q)
            if anc is not None:
                add(anc)
                G.add_edge(str(c), str(anc), etype="inferred")
    # draw FIBO internal subClassOf among the FIBO nodes now present
    present = set(G.nodes)
    for s, o in e.fibo.subject_objects(RDFS.subClassOf):
        if isinstance(o, BNode) or isinstance(s, BNode):
            continue
        if str(s) in present and str(o) in present and not G.has_edge(str(s), str(o)):
            G.add_edge(str(s), str(o), etype="subClassOf")
    return G


def _resolve(e, qname):
    if ":" not in qname:
        return None
    pfx, local = qname.split(":", 1)
    ns = dict(e.inferred.namespaces()).get(pfx)
    return URIRef(str(ns) + local) if ns else None


# ---- layout ---------------------------------------------------------------
def concept_enrichment_graph(e, subsumption, concept_local: str) -> nx.DiGraph:
    """Focused before/after for ONE HBIM concept: its taxonomy parent, its mapping,
    and the FIBO ancestry inference lifts it into."""
    from common import HBIM
    concept = HBIM[concept_local]
    G = nx.DiGraph()
    G.add_node(str(concept), label=q(e.inferred, concept), kind="hbim")

    def add(n):
        if str(n) not in G:
            kind = "hbim" if is_hbim(n) else "fibo"
            G.add_node(str(n), label=q(e.inferred, n), kind=kind)
        return str(n)

    for p in e.hbim.objects(concept, SKOS.broader):
        add(p); G.add_edge(str(concept), str(p), etype="broader")
    for hb, fb in e.maps.subject_objects(SKOS.exactMatch):
        if hb == concept:
            add(fb); G.add_edge(str(hb), str(fb), etype="exact")
    for prop in (SKOS.closeMatch, SKOS.broadMatch):
        for hb, fb in e.maps.subject_objects(prop):
            if hb == concept:
                add(fb); G.add_edge(str(hb), str(fb), etype="bridge")
    info = subsumption.get(q(e.inferred, concept), {})
    ancestors = set()
    for anc_q in info.get("inferred_ancestors", []):
        anc = _resolve(e, anc_q)
        if anc is not None:
            ancestors.add(anc)
            add(anc); G.add_edge(str(concept), str(anc), etype="inferred")
    # FIBO backbone among the ancestors, so the lift reads as a real hierarchy
    present = set(G.nodes)
    for s, o in e.fibo.subject_objects(RDFS.subClassOf):
        if isinstance(s, BNode) or isinstance(o, BNode):
            continue
        if str(s) in present and str(o) in present and not G.has_edge(str(s), str(o)):
            G.add_edge(str(s), str(o), etype="subClassOf")
    return G


def _layered_pos(G, x_gap=2.4, y_gap=1.6):
    """Top-down layout: general classes on top, specific below.

    Depth = longest chain of upward (is-a) edges below a node.
    """
    up = nx.DiGraph()
    up.add_nodes_from(G.nodes)
    up.add_edges_from((u, v) for u, v, d in G.edges(data=True)
                      if d.get("etype") in _UPWARD and u != v)
    memo = {}

    def depth(n, stack):
        if n in memo:
            return memo[n]
        outs = [v for _, v in up.out_edges(n) if v not in stack]
        d = 0 if not outs else 1 + max(depth(v, stack | {n}) for v in outs)
        memo[n] = d
        return d

    depths = {n: depth(n, frozenset()) for n in up.nodes}
    maxd = max(depths.values()) if depths else 0
    by_level = {}
    for n, d in depths.items():
        by_level.setdefault(d, []).append(n)
    pos = {}
    for d, nodes in by_level.items():
        nodes = sorted(nodes, key=lambda n: G.nodes[n].get("label", n))
        for i, n in enumerate(nodes):
            pos[n] = ((i - (len(nodes) - 1) / 2) * x_gap, (maxd - d) * y_gap)
    return pos


# ---- drawing --------------------------------------------------------------
def draw_graph(G, title, figsize=(13, 8), node_size=2000, font_size=8,
               edge_labels=False, x_gap=2.4, y_gap=1.6):
    pos = _layered_pos(G, x_gap=x_gap, y_gap=y_gap)
    plt.figure(figsize=figsize)

    for kind, style in NODE_STYLE.items():
        nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == kind]
        if nodes:
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_color=style["color"],
                                   node_size=node_size, edgecolors="#333", linewidths=0.8)

    for etype, (color, ls, width, _) in EDGE_STYLE.items():
        elist = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == etype]
        if elist:
            nx.draw_networkx_edges(G, pos, edgelist=elist, edge_color=color, width=width,
                                   style=ls, arrows=True, arrowstyle="-|>", arrowsize=13,
                                   node_size=node_size, alpha=EDGE_ALPHA.get(etype, 0.85),
                                   connectionstyle=f"arc3,rad={EDGE_RAD.get(etype, 0.03)}")
    if edge_labels:
        elabels = {(u, v): d["elabel"] for u, v, d in G.edges(data=True) if "elabel" in d}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=elabels, font_size=7,
                                     font_color="#337", bbox=dict(alpha=0))

    nx.draw_networkx_labels(G, pos, labels={n: d["label"] for n, d in G.nodes(data=True)},
                            font_size=font_size)

    # legends: node kinds present + edge types present
    kinds = {d.get("kind") for _, d in G.nodes(data=True)}
    etypes = {d.get("etype") for _, _, d in G.edges(data=True)}
    node_handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=NODE_STYLE[k]["color"],
                           markeredgecolor="#333", markersize=11, label=NODE_STYLE[k]["label"])
                    for k in NODE_STYLE if k in kinds]
    edge_handles = [Line2D([0], [0], color=EDGE_STYLE[t][0], lw=2, ls=EDGE_STYLE[t][1],
                           label=EDGE_STYLE[t][3]) for t in EDGE_STYLE if t in etypes]
    leg1 = plt.legend(handles=node_handles, loc="upper left", fontsize=8, title="Nodes")
    plt.gca().add_artist(leg1)
    plt.legend(handles=edge_handles, loc="lower left", fontsize=7.5, title="Edges")

    plt.title(title, fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    plt.show()
