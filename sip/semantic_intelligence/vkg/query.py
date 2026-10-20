"""SPARQL over the virtual knowledge graph while the ontology is being edited.

The virtual graph is ``mapped data ∪ ontology`` where the ontology is the project's
**staged** view by default. Entailment is applied at query time, so an ontology edit —
say ``CorporateCustomer SubClassOf Customer``, even one still awaiting validation —
changes the answers immediately, without touching a mapping. This is the "T-mappings"
effect Ontop obtains by saturating mappings with the TBox, computed here by
materialising and closing instead of rewriting.

Entailment regimes:

* ``rdfs`` (default): a light closure — transitive ``rdfs:subClassOf`` /
  ``rdfs:subPropertyOf`` with ``owl:equivalentClass`` / ``owl:equivalentProperty``,
  type propagation (rdfs9), property propagation (rdfs7), ``owl:inverseOf``, and
  rdfs2/rdfs3 domain/range typing. Fast and predictable.
* ``owlrl``: the owlrl OWL 2 RL closure (slower; same backend as the reasoner).
* ``none``: asserted triples only.

Optional external engine: :func:`ontop_query` sends the query to an Ontop SPARQL
endpoint (e.g. the sidecar of ``LAB/PoCs/SPARQL-2-SQL``). It is off unless an endpoint
is given explicitly; that engine answers with *its* ontology, not the staged one.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

__all__ = ["light_closure", "virtual_graph", "run_sparql", "ontop_query", "ENTAILMENTS"]

ENTAILMENTS = ("rdfs", "owlrl", "none")


def _closure(pairs: set[tuple]) -> dict:
    """Reflexive-transitive closure of a binary relation as node -> ancestors."""
    up: dict = {}
    for a, b in pairs:
        up.setdefault(a, set()).add(b)
    out = {}
    for start in up:
        seen, todo = set(), [start]
        while todo:
            x = todo.pop()
            for y in up.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        seen.discard(start)
        out[start] = seen
    return out


def light_closure(g: Graph) -> Graph:
    """Add the RDFS-style entailments listed in the module doc to *g* (in place)."""
    named = lambda x: isinstance(x, URIRef)  # noqa: E731
    sub = {(a, b) for a, b in g.subject_objects(RDFS.subClassOf) if named(a) and named(b)}
    for a, b in g.subject_objects(OWL.equivalentClass):
        if named(a) and named(b):
            sub |= {(a, b), (b, a)}
    subp = {(a, b) for a, b in g.subject_objects(RDFS.subPropertyOf) if named(a) and named(b)}
    for a, b in g.subject_objects(OWL.equivalentProperty):
        if named(a) and named(b):
            subp |= {(a, b), (b, a)}
    inv = {(a, b) for a, b in g.subject_objects(OWL.inverseOf) if named(a) and named(b)}
    inv |= {(b, a) for a, b in inv}
    sup_c, sup_p = _closure(sub), _closure(subp)
    dom = {(p, c) for p, c in g.subject_objects(RDFS.domain) if named(c)}
    rng = {(p, c) for p, c in g.subject_objects(RDFS.range) if named(c)}
    for _ in range(3):                       # property layer feeds the class layer
        before = len(g)
        for p, sups in sup_p.items():
            for s, o in list(g.subject_objects(p)):
                for q in sups:
                    g.add((s, q, o))
        for p, q in inv:
            for s, o in list(g.subject_objects(p)):
                if named(o):
                    g.add((o, q, s))
        for p, c in dom:
            for s in list(g.subjects(p, None)):
                g.add((s, RDF.type, c))
        for p, c in rng:
            for o in list(g.objects(None, p)):
                if named(o):
                    g.add((o, RDF.type, c))
        for x, c in list(g.subject_objects(RDF.type)):
            for d in sup_c.get(c, ()):
                g.add((x, RDF.type, d))
        if len(g) == before:
            break
    return g


def virtual_graph(ontology: Graph, data: Graph, entailment: str = "rdfs") -> Graph:
    if entailment not in ENTAILMENTS:
        raise ValueError(f"entailment is one of {ENTAILMENTS}")
    g = Graph()
    for pfx, ns in ontology.namespaces():
        g.bind(pfx, ns, override=True)
    for t in ontology:
        g.add(t)
    for t in data:
        g.add(t)
    if entailment == "rdfs":
        light_closure(g)
    elif entailment == "owlrl":
        import owlrl
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
    return g


def run_sparql(g: Graph, query: str, limit: int | None = None) -> dict:
    res = g.query(query)
    if res.type == "ASK":
        return {"type": "ASK", "rows": [{"ask": bool(res.askAnswer)}]}
    if res.type in ("CONSTRUCT", "DESCRIBE"):
        rows = [{"s": str(s), "p": str(p), "o": str(o)} for s, p, o in res.graph]
    else:
        rows = [{str(k): (str(v) if v is not None else None) for k, v in r.asdict().items()}
                for r in res]
    total = len(rows)
    if limit is not None:
        rows = rows[:limit]
    return {"type": res.type, "rows": rows, "total": total, "truncated": total > len(rows)}


def ontop_query(endpoint: str, query: str, timeout: float = 30.0) -> dict:
    """POST the query to an Ontop (or any SPARQL 1.1) endpoint; JSON results only."""
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("the Ontop endpoint must be an http(s) URL")
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (explicit URL)
        body = json.loads(r.read().decode("utf-8"))
    if "boolean" in body:
        return {"type": "ASK", "rows": [{"ask": body["boolean"]}], "engine": "ontop"}
    rows = [{k: v.get("value") for k, v in b.items()} for b in body["results"]["bindings"]]
    return {"type": "SELECT", "rows": rows, "total": len(rows), "truncated": False,
            "engine": "ontop"}
