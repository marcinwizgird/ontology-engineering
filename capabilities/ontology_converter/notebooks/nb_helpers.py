"""
Helpers shared by the FIBO visualization notebooks.

Reuses the ETL classes from ``ontology_to_lpg.py`` (RecursiveOntologyLoader +
UniversalOntologyConverter) to build the NetworkX meta-graph IR, but deliberately
*stops before* the FalkorDB load step -- these notebooks only load & visualise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

# Make ../ (the converter package) importable from the notebooks/ folder.
_CONV_DIR = Path(__file__).resolve().parent.parent
if str(_CONV_DIR) not in sys.path:
    sys.path.insert(0, str(_CONV_DIR))

from ontology_to_lpg import RecursiveOntologyLoader, UniversalOntologyConverter  # noqa: E402


# --------------------------------------------------------------------------
# Locate the local FIBO clone (…/Ontology Repository/FIBO/fibo)
# --------------------------------------------------------------------------
def find_fibo_root() -> Path:
    """Best-effort discovery of the local FIBO ontology tree."""
    candidates = [
        _CONV_DIR.parent.parent / "Ontology Repository" / "FIBO" / "fibo",
        Path.home() / "OneDrive" / "DEV" / "EDU" / "AIML" / "Graph ML" /
        "Ontology Engineering" / "Ontology Repository" / "FIBO" / "fibo",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "Could not locate the FIBO clone. Set FIBO_ROOT manually in the notebook.")


# Colour palettes -----------------------------------------------------------
LABEL_COLORS = {
    "OWLClass": "#4C78A8",
    "ObjectProperty": "#F58518",
    "DatatypeProperty": "#54A24B",
    "AnnotationProperty": "#B279A2",
    "Ontology": "#E45756",
    "Resource": "#BAB0AC",       # external / untyped reference stub
}
EDGE_COLORS = {
    "SUBCLASS_OF": "#4C78A8",
    "SUBPROPERTY_OF": "#F58518",
    "HAS_DOMAIN": "#54A24B",
    "HAS_RANGE": "#72B7B2",
    "DEFINED_IN": "#BAB0AC",
    "IMPORTS": "#E45756",
}


# --------------------------------------------------------------------------
# Load -> transform (no LPG export)
# --------------------------------------------------------------------------
def load_ontology_ir(path, follow_imports: bool = False,
                     uri_to_location: dict | None = None) -> nx.MultiDiGraph:
    """Load an ontology file and return the populated NetworkX meta-graph IR."""
    loader = RecursiveOntologyLoader(uri_to_location=uri_to_location,
                                     follow_imports=follow_imports)
    rdf_graph, ir = loader.load(str(path))
    UniversalOntologyConverter(rdf_graph, ir).convert()
    return ir


def primary_label(data: dict) -> str:
    labels = data.get("labels") or {"Resource"}
    # Prefer a schema label over the generic Ontology/Resource tags.
    for pref in ("OWLClass", "ObjectProperty", "DatatypeProperty", "AnnotationProperty"):
        if pref in labels:
            return pref
    return sorted(labels)[0]


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------
def summarize_ir(ir: nx.MultiDiGraph) -> dict[str, pd.DataFrame]:
    """Return label counts, edge-type counts, and a node table as DataFrames."""
    label_counts: dict[str, int] = {}
    for _, d in ir.nodes(data=True):
        label_counts[primary_label(d)] = label_counts.get(primary_label(d), 0) + 1
    edge_counts: dict[str, int] = {}
    for _, _, d in ir.edges(data=True):
        t = d.get("type", "?")
        edge_counts[t] = edge_counts.get(t, 0) + 1

    nodes = pd.DataFrame([
        {"qname": d.get("qname"), "label": primary_label(d),
         "rdfs_label": d.get("rdfs_label", ""),
         "definition": (d.get("skos_definition", "") or "")[:70]}
        for _, d in ir.nodes(data=True)
    ]).sort_values(["label", "qname"]).reset_index(drop=True)

    return {
        "labels": pd.DataFrame(sorted(label_counts.items()),
                               columns=["node_label", "count"]),
        "edges": pd.DataFrame(sorted(edge_counts.items()),
                              columns=["edge_type", "count"]),
        "nodes": nodes,
    }


# --------------------------------------------------------------------------
# Composition of several ontologies into one IR (for the multi-ontology view)
# --------------------------------------------------------------------------
def compose_named(named_irs: dict[str, nx.MultiDiGraph]) -> nx.MultiDiGraph:
    """Merge several IRs into one graph, tagging each node with its source(s).

    A node URI that appears in more than one ontology is tagged ``source='shared'``
    -- these are the cross-references that connect the otherwise separate modules.
    Node ``labels`` sets are unioned so a class typed in one module is not demoted
    to a stub by another module that only references it.
    """
    combined = nx.MultiDiGraph()
    seen_in: dict[str, set[str]] = {}
    for name, ir in named_irs.items():
        for uri, data in ir.nodes(data=True):
            seen_in.setdefault(uri, set()).add(name)
            if uri not in combined:
                combined.add_node(uri, **{k: (set(v) if k == "labels" else v)
                                          for k, v in data.items()})
            else:
                combined.nodes[uri].setdefault("labels", set()).update(
                    data.get("labels") or set())
                for k, v in data.items():
                    if k != "labels":
                        combined.nodes[uri].setdefault(k, v)
        for u, v, key, data in ir.edges(keys=True, data=True):
            if not combined.has_edge(u, v, key=key):
                combined.add_edge(u, v, key=key, **data)

    for uri, srcs in seen_in.items():
        combined.nodes[uri]["source"] = "shared" if len(srcs) > 1 else next(iter(srcs))
    return combined


# --------------------------------------------------------------------------
# Filtering (to keep large graphs readable)
# --------------------------------------------------------------------------
def filter_ir(ir: nx.MultiDiGraph, keep_labels=None, drop_labels=None,
              keep_edge_types=None) -> nx.MultiDiGraph:
    """Return a copy of ``ir`` restricted to the given node labels / edge types."""
    out = nx.MultiDiGraph()
    for n, d in ir.nodes(data=True):
        lbl = primary_label(d)
        if keep_labels and lbl not in keep_labels:
            continue
        if drop_labels and lbl in drop_labels:
            continue
        out.add_node(n, **d)
    for u, v, key, d in ir.edges(keys=True, data=True):
        if u in out and v in out and (not keep_edge_types or d.get("type") in keep_edge_types):
            out.add_edge(u, v, key=key, **d)
    return out


# --------------------------------------------------------------------------
# Visualization
# --------------------------------------------------------------------------
def _layout(g, seed=42):
    # Kamada-Kawai gives clean layouts for small/connected schema graphs; use
    # spring for larger or disconnected graphs (multi-ontology views).
    n = g.number_of_nodes() or 1
    if n <= 40 and nx.is_weakly_connected(g):
        try:
            return nx.kamada_kawai_layout(g)
        except Exception:  # noqa: BLE001
            pass
    return nx.spring_layout(g, seed=seed, k=2.2 / (n ** 0.5))


def draw_meta_graph(ir: nx.MultiDiGraph, title: str, color_by: str = "label",
                    source_colors: dict | None = None, figsize=(14, 10),
                    font_size=8, node_size=900):
    """Draw the ontology meta-graph.

    color_by='label'  -> colour nodes by LPG label (OWLClass/ObjectProperty/...)
    color_by='source' -> colour nodes by originating ontology (needs 'source' attr)
    """
    g = ir
    pos = _layout(g)
    plt.figure(figsize=figsize)

    # Nodes
    if color_by == "source":
        groups: dict[str, list] = {}
        for n, d in g.nodes(data=True):
            groups.setdefault(d.get("source", "?"), []).append(n)
        palette = source_colors or {}
        for i, (src, nodes) in enumerate(sorted(groups.items())):
            nx.draw_networkx_nodes(
                g, pos, nodelist=nodes, node_size=node_size,
                node_color=palette.get(src, f"C{i}"),
                edgecolors="#333", linewidths=0.6, label=src)
    else:
        for lbl, color in LABEL_COLORS.items():
            nodes = [n for n, d in g.nodes(data=True) if primary_label(d) == lbl]
            if nodes:
                nx.draw_networkx_nodes(
                    g, pos, nodelist=nodes, node_size=node_size, node_color=color,
                    edgecolors="#333", linewidths=0.6, label=lbl)

    # Edges, grouped and coloured by relationship type
    by_type: dict[str, list] = {}
    for u, v, d in g.edges(data=True):
        by_type.setdefault(d.get("type", "?"), []).append((u, v))
    for etype, elist in by_type.items():
        nx.draw_networkx_edges(
            g, pos, edgelist=elist, edge_color=EDGE_COLORS.get(etype, "#999"),
            width=1.3, alpha=0.7, arrows=True, arrowstyle="-|>", arrowsize=11,
            connectionstyle="arc3,rad=0.06")

    labels = {n: d.get("qname", n) for n, d in g.nodes(data=True)}
    nx.draw_networkx_labels(g, pos, labels=labels, font_size=font_size)

    # Two legends: node groups (auto) + edge types (manual)
    from matplotlib.lines import Line2D
    edge_handles = [Line2D([0], [0], color=EDGE_COLORS.get(t, "#999"), lw=2, label=t)
                    for t in sorted(by_type)]
    node_legend = plt.legend(loc="upper left", fontsize=8, title="Nodes")
    plt.gca().add_artist(node_legend)
    plt.legend(handles=edge_handles, loc="lower left", fontsize=8, title="Edges")

    plt.title(title, fontsize=13)
    plt.axis("off")
    plt.tight_layout()
    plt.show()
