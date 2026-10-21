"""Review-gate overlays on a view, keyed by IRI.

Each overlay comes from data SIP already produces; none needs a new store:

* **staged**    stable index vs staged index (``ctx.ontology(staged=False/True)``): nodes and
  edges are ``asserted``, ``staged_add``, ``staged_del`` or (nodes) ``modified``; pending
  commits that touch a node are listed so the reviewer can open them.
* **inferred**  OWL 2 RL (owlrl) closure, reduced transitively, so only *new direct*
  superclasses are drawn (dashed); unsatisfiable classes are flagged.
* **findings**  ``quality.runChecks`` findings, by resource IRI, worst severity first.
* **cq**        competency questions whose SPARQL names the node (``quality.cq.terms``),
  split by pass / fail.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDFS

from .index import Edge, OntologyIndex
from .neighbourhood import View

SEVERITY = ("blocker", "major", "minor", "info")


@dataclass
class OverlayInputs:
    stable: OntologyIndex | None = None       # None: no staged differences
    staged: OntologyIndex | None = None
    pending: list[dict] = field(default_factory=list)
    inferred: Graph | None = None
    inferred_source: str | None = None        # "stable" | "preview"
    unsatisfiable: set[str] = field(default_factory=set)
    findings: list[dict] = field(default_factory=list)
    cqs: list[dict] = field(default_factory=list)   # {id, question, priority, passed, terms}


def staged_state(view: View, inp: OverlayInputs):
    nodes, edges = {}, {}
    if inp.stable is None or inp.staged is None:
        return nodes, edges
    st, sg = inp.stable, inp.staged
    for n in view.nodes:
        a, b = n in st.nodes, n in sg.nodes
        nodes[n] = "staged_add" if b and not a else "staged_del" if a and not b else "asserted"
    for e in view.edges:
        a, b = e.key in st.edges, e.key in sg.edges
        edges[e.id] = "staged_add" if b and not a else "staged_del" if a and not b \
            else "asserted"
    return nodes, edges


def touching_commits(view: View, pending: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for c in pending:
        subjects = {t[0] for t in c.get("additions", [])} | {t[0] for t in c.get("removals", [])}
        for n in view.nodes:
            if n in subjects:
                out[n].append({"id": c["id"], "operation": c["operation"],
                               "principal": c["principal"], "machine": c.get("machine", False)})
    return out


def _supers(g: Graph, x: URIRef, cache: dict) -> set[URIRef]:
    if x not in cache:
        cache[x] = {y for y in g.objects(x, RDFS.subClassOf)
                    if isinstance(y, URIRef) and y != x and y not in (OWL.Thing, OWL.Nothing)}
    return cache[x]


def inferred_edges(index: OntologyIndex, inferred: Graph, nodes=None) -> list[Edge]:
    """New direct superclasses: transitive reduction of (asserted ∪ inferred), minus asserted
    and minus equivalents of asserted parents. Both ends are index nodes."""
    closure = Graph()
    for t in inferred.triples((None, RDFS.subClassOf, None)):
        closure.add(t)
    for t in index.graph.triples((None, RDFS.subClassOf, None)):
        closure.add(t)
    cache: dict = {}
    asserted: set[tuple[str, str]] = set()
    for e in index.edges.values():
        if e.kind == "subClassOf":
            asserted.add((e.source, e.target))
        elif e.kind == "equivalentClass":
            asserted |= {(e.source, e.target), (e.target, e.source)}
    parents: dict[str, set[str]] = defaultdict(set)
    for a, b in asserted:
        parents[a].add(b)

    def equivalent(a: URIRef, b: URIRef) -> bool:
        return b in _supers(closure, a, cache) and a in _supers(closure, b, cache)

    out = []
    for n in sorted(index.nodes if nodes is None else nodes):
        sup = _supers(closure, URIRef(n), cache)
        for y in sorted(sup):
            ys = str(y)
            if ys not in index.nodes or (n, ys) in asserted:
                continue
            # an equivalent of an asserted parent adds nothing the diagram does not show
            if any(equivalent(y, URIRef(z)) for z in parents[n]):
                continue
            # ... nor does a parent already asserted on an equivalent of n
            if any((str(z), ys) in asserted for z in sup if equivalent(z, URIRef(n))):
                continue
            # y is direct iff no other superclass z of n (not equivalent to y) sits below y
            if any(y in _supers(closure, z, cache) and z not in _supers(closure, y, cache)
                   and not equivalent(z, URIRef(n)) for z in sup if z != y):
                continue
            out.append(Edge(n, ys, "subClassOf", via="inferred"))
    return out


def annotate(view: View, index: OntologyIndex, inp: OverlayInputs) -> dict:
    node_state, edge_state = staged_state(view, inp)
    commits = touching_commits(view, inp.pending)
    findings: dict[str, list[dict]] = defaultdict(list)
    for f in inp.findings:
        if f.get("resource") in view.nodes:
            findings[f["resource"]].append({k: f.get(k) for k in ("check", "severity",
                                                                  "message")})
    cq: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for q in inp.cqs:
        now, then = q.get("passed"), q.get("passedStaged", q.get("passed"))
        for t in q.get("terms", ()):
            if t in view.nodes:
                cq[t]["pass" if now else "fail"].append(q["id"])
                if now != then:
                    cq[t]["fixedByStaged" if then else "brokenByStaged"].append(q["id"])

    nodes = {}
    for n in view.nodes:
        state = node_state.get(n, "asserted")
        if state == "asserted" and n in commits:
            state = "modified"
        fs = sorted(findings.get(n, []), key=lambda f: SEVERITY.index(f["severity"])
                    if f["severity"] in SEVERITY else 9)
        nodes[n] = {"state": state, "commits": commits.get(n, []),
                    "findings": fs[:5], "findingCount": len(fs),
                    "worstSeverity": fs[0]["severity"] if fs else None,
                    "unsatisfiable": n in inp.unsatisfiable,
                    "cq": {k: sorted(cq[n].get(k, [])) for k in
                           ("pass", "fail", "fixedByStaged", "brokenByStaged")}}
    edges = {e.id: {"state": edge_state.get(e.id, "asserted"), "inferred": e.via == "inferred"}
             for e in view.edges}
    summary = {
        "staged": {s: sum(1 for v in nodes.values() if v["state"] == s)
                   for s in ("staged_add", "staged_del", "modified")},
        "stagedEdges": {s: sum(1 for v in edges.values() if v["state"] == s)
                        for s in ("staged_add", "staged_del")},
        "pendingCommits": len(inp.pending),
        "inferredEdges": sum(1 for v in edges.values() if v["inferred"]),
        "inferredSource": inp.inferred_source,
        "unsatisfiable": sorted(n for n in view.nodes if n in inp.unsatisfiable),
        "findings": sum(v["findingCount"] for v in nodes.values()),
        "cq": {k: len({i for v in nodes.values() for i in v["cq"][k]})
               for k in ("pass", "fail", "fixedByStaged", "brokenByStaged")},
    }
    return {"nodes": nodes, "edges": edges, "summary": summary}
