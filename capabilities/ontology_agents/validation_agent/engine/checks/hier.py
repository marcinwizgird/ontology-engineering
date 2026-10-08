"""HIER: the asserted class hierarchy as a networkx DiGraph (child -> parent)."""

from __future__ import annotations

from itertools import combinations

import networkx as nx
from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .. import vocab as V
from ..registry import CheckContext, detector, finding


def hierarchy(ctx: CheckContext) -> nx.DiGraph:
    def build() -> nx.DiGraph:
        h = nx.DiGraph()
        for c in V.declared_classes(ctx.graph):
            h.add_node(c)
        for s, o in ctx.graph.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o and o != OWL.Thing:
                h.add_edge(s, o)
        return h
    return ctx.memo("hierarchy", build)


def disjoint_pairs(ctx: CheckContext) -> list[tuple[URIRef, URIRef, str]]:
    g, out = ctx.graph, []
    for a, b in g.subject_objects(OWL.disjointWith):
        if isinstance(a, URIRef) and isinstance(b, URIRef):
            out.append((a, b, f"<{a}> owl:disjointWith <{b}>"))
    for node in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members = [m for m in V.rdf_list(g, g.value(node, OWL.members)) if isinstance(m, URIRef)]
        for a, b in combinations(sorted(members, key=str), 2):
            out.append((a, b, "owl:AllDisjointClasses (" + " ".join(V.local_name(m) for m in members) + ")"))
    for owner, head in g.subject_objects(OWL.disjointUnionOf):
        members = [m for m in V.rdf_list(g, head) if isinstance(m, URIRef)]
        for a, b in combinations(sorted(members, key=str), 2):
            out.append((a, b, f"<{owner}> owl:disjointUnionOf (...)"))
    return sorted(out, key=lambda t: (str(t[0]), str(t[1]), t[2]))


@detector("HIER-01")
def subsumption_cycle(ctx: CheckContext):
    h = hierarchy(ctx)
    out = []
    sccs = [sorted(c, key=str) for c in nx.strongly_connected_components(h) if len(c) > 1]
    for scc in sorted(sccs, key=lambda c: str(c[0])):
        cycle = scc + [scc[0]]
        out.append(finding(
            "HIER-01", scc[0], "Subsumption cycle: " + " -> ".join(V.local_name(c) for c in cycle)
            + ". Every class in it is entailed equivalent to the others.",
            related=scc[1:], evidence={"cycle": [str(c) for c in scc],
                                       "triples": sorted(f"<{a}> rdfs:subClassOf <{b}>"
                                                         for a, b in h.subgraph(scc).edges())},
            fix_hint="Remove the subClassOf edge that points back up the hierarchy; if the "
                     "classes really are the same, merge them or state owl:equivalentClass."))
    return out


@detector("HIER-02")
def individual_in_subsumption(ctx: CheckContext):
    g = ctx.graph
    classes = set(V.declared_classes(g))
    inds = set(V.individuals(g)) - classes
    out = []
    for s, o in sorted(g.subject_objects(RDFS.subClassOf), key=lambda t: (str(t[0]), str(t[1]))):
        bad = [t for t in (s, o) if t in inds]
        for t in bad:
            out.append(finding(
                "HIER-02", t, f"Individual {V.local_name(t)} appears in a subClassOf axiom "
                f"({V.local_name(s)} subClassOf {V.local_name(o)}).",
                related=[x for x in (s, o) if x != t and isinstance(x, URIRef)],
                evidence={"triples": [f"<{s}> rdfs:subClassOf {o.n3()}"]},
                fix_hint="Use rdf:type to say the individual is a member of the class; "
                         "subClassOf relates classes only."))
    return out


@detector("HIER-05")
def disjoint_with_ancestor(ctx: CheckContext):
    h = hierarchy(ctx)
    out = []
    for a, b, axiom in disjoint_pairs(ctx):
        for child, ancestor in ((a, b), (b, a)):
            if child in h and ancestor in h and child != ancestor and nx.has_path(h, child, ancestor):
                path = nx.shortest_path(h, child, ancestor)
                out.append(finding(
                    "HIER-05", child, f"{V.local_name(child)} is disjoint with its ancestor "
                    f"{V.local_name(ancestor)}, so it can have no members.",
                    related=[ancestor], evidence={"triples": [axiom], "path": [str(p) for p in path]},
                    fix_hint=f"Remove the disjointness, or move {V.local_name(child)} out of the "
                             f"{V.local_name(ancestor)} branch."))
    return out


@detector("HIER-08")
def missing_sibling_disjointness(ctx: CheckContext):
    h = hierarchy(ctx)
    disjoint = {frozenset((a, b)) for a, b, _ in disjoint_pairs(ctx)}
    min_siblings = ctx.param("HIER-08", "min_siblings", 2)
    out = []
    for parent in sorted(h.nodes, key=str):
        children = sorted(h.predecessors(parent), key=str)
        if len(children) < min_siblings:
            continue
        if any(frozenset(p) in disjoint for p in combinations(children, 2)):
            continue
        out.append(finding(
            "HIER-08", parent, f"The {len(children)} subclasses of {V.local_name(parent)} have "
            "no disjointness axiom among them.",
            related=children, evidence={"children": [str(c) for c in children]},
            fix_hint="If the subclasses cannot share members, state owl:AllDisjointClasses "
                     "(or owl:disjointUnionOf) for them; otherwise a reasoner cannot detect "
                     "an individual classified into two of them."))
    return out
