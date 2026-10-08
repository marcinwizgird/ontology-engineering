"""SKOS: integrity of concept schemes."""

from __future__ import annotations

import networkx as nx
from rdflib import URIRef
from rdflib.namespace import SKOS

from .. import vocab as V
from ..registry import CheckContext, detector, finding


@detector("SKOS-05")
def broader_cycle(ctx: CheckContext):
    g = ctx.graph
    h = nx.DiGraph()
    for s, o in g.subject_objects(SKOS.broader):
        if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
            h.add_edge(s, o)
    for s, o in g.subject_objects(SKOS.narrower):
        if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
            h.add_edge(o, s)
    out = []
    sccs = [sorted(c, key=str) for c in nx.strongly_connected_components(h) if len(c) > 1]
    for scc in sorted(sccs, key=lambda c: str(c[0])):
        out.append(finding(
            "SKOS-05", scc[0], "skos:broader cycle: " +
            " -> ".join(V.label(g, c) for c in scc + [scc[0]]) + ".",
            related=scc[1:], evidence={"cycle": [str(c) for c in scc]},
            fix_hint="Remove the broader (or narrower) link that points back down; a concept "
                     "cannot be broader than itself."))
    return out
