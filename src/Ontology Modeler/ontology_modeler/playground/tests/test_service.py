"""Offline E2E of the whole save path -- load, edit, merge, guard, and SYNC -- with no live
Fuseki. A FakeClient backs the service with an rdflib Dataset that honours the same surface
GraphSynchronizer uses (get_graph / update / put_graph), so the SPARQL the differ emits is
actually applied and the post-write graph is verified for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))   # .../src/Ontology Modeler

from rdflib import Dataset, Graph, URIRef, RDF, RDFS, OWL, Literal, BNode
from rdflib.namespace import SKOS

from ontology_modeler.config import REPO_ROOT
from ontology_modeler.playground.service import PlaygroundService, guard, PreservationError
from ontology_modeler.playground.model import Ontology, EntityType

GRAPH_URI = "urn:graph:test/ontology"
_fail = 0


def check(cond: bool, msg: str) -> None:
    global _fail
    if not cond:
        _fail += 1
    print(f"    [{'  ok ' if cond else 'FAIL '}] {msg}")


class FakeClient:
    """A FusekiClient-shaped stand-in over an in-memory Dataset (named-graph aware)."""

    def __init__(self):
        self.ds = Dataset()

    def preload(self, uri: str, graph: Graph) -> None:
        ctx = self.ds.graph(URIRef(uri))
        for t in graph:
            ctx.add(t)

    def is_up(self) -> bool:
        return True

    def get_graph(self, uri: str, timeout: int = 120) -> Graph:
        g = Graph()
        for t in self.ds.get_context(URIRef(uri)):
            g.add(t)
        return g

    def put_graph(self, uri, data, content_type="text/turtle", timeout=300) -> None:
        ctx = self.ds.get_context(URIRef(uri))
        for t in list(ctx):
            ctx.remove(t)
        src = data if isinstance(data, Graph) else Graph().parse(data=data, format="turtle")
        for t in src:
            ctx.add(t)

    def update(self, sparql: str, timeout: int = 300) -> None:
        self.ds.update(sparql)


def load_base() -> Graph:
    g = Graph()
    g.parse(str(REPO_ROOT / "Ontology Repository/FIBO/fibo/BE/LegalEntities/CorporateBodies.rdf"))
    return g


def test_guard_blocks_illegal_delete() -> None:
    """A merged graph that dropped a restriction triple must be caught by the guard."""
    base = load_base()
    merged = Graph()
    dropped = None
    for t in base:
        # drop one blank-node (restriction) triple to simulate a merge bug
        if dropped is None and any(isinstance(x, BNode) for x in t):
            dropped = t
            continue
        merged.add(t)
    violations = guard(base, merged)
    check(dropped is not None and len(violations) >= 1,
          "guard flags an illegal restriction deletion")


def test_full_save_cycle() -> None:
    client = FakeClient()
    client.preload(GRAPH_URI, load_base())
    svc = PlaygroundService(client)

    base_before = client.get_graph(GRAPH_URI)
    bnodes_before = {t for t in base_before if any(isinstance(x, BNode) for x in t)}

    env = svc.load(GRAPH_URI)
    ont = Ontology.from_dict(env["ontology"])
    check(len(ont.entityTypes) > 0, f"loaded {len(ont.entityTypes)} nodes from graph")

    # edit: rename first node + add a concept
    ont.entityTypes[0].name = (ont.entityTypes[0].name or "X") + " [edited]"
    new_iri = env["baseNs"] + "ServiceTestConcept"
    ont.entityTypes.append(EntityType(id=new_iri, name="Service Test Concept", kind="concept"))

    dry = svc.save(GRAPH_URI, ont, dry_run=True)
    check(dry.method == "dry-run" and dry.added > 0, f"dry-run reports +{dry.added}/-{dry.removed}, no write")
    check(len(client.get_graph(GRAPH_URI)) == len(base_before), "dry-run wrote nothing")

    res = svc.save(GRAPH_URI, ont)
    check(res.applied and res.verified, f"save applied and verified (method={res.method})")

    after = client.get_graph(GRAPH_URI)
    check((URIRef(new_iri), RDF.type, SKOS.Concept) in after, "new concept persisted in store")
    check(bnodes_before <= set(after),
          f"all {len(bnodes_before)} restriction/bnode triples still in store after write")

    # idempotency: saving the same projection again is a no-op
    env2 = svc.load(GRAPH_URI)
    res2 = svc.save(GRAPH_URI, env2["ontology"])
    check(res2.method == "noop", "re-saving an unedited reload is a no-op")


def main() -> int:
    for fn in (test_guard_blocks_illegal_delete, test_full_save_cycle):
        print(f"\n=== {fn.__name__}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            global _fail
            _fail += 1
            import traceback
            print(f"    [FAIL ] exception: {exc}")
            traceback.print_exc()
    print(f"\n{'='*60}\n{'ALL CHECKS PASSED' if _fail == 0 else f'{_fail} CHECK(S) FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
