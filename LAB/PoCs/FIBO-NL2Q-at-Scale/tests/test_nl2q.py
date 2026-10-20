"""Offline tests for the FIBO NL2Q-at-scale PoC.

Pure-logic tests always run. Tests that need the loaded DuckDB (``python -m
nl2q.load_fiben``) or the FIBEN Ontop sidecar on :18081 skip with the reason when those
are absent. No test calls a language model.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl2q import compare, paths, schema, stats  # noqa: E402

HAS_DB = paths.DB.exists()


def _sidecar() -> bool:
    if not HAS_DB:
        return False
    try:
        from nl2q import vkg
        return vkg.sidecar_ok()
    except Exception:  # noqa: BLE001
        return False


HAS_SIDECAR = _sidecar()
needs_db = pytest.mark.skipif(not HAS_DB, reason="data/fiben_vkg.duckdb not built")
needs_sidecar = pytest.mark.skipif(not HAS_SIDECAR, reason="FIBEN Ontop sidecar not running on :18081")


# ----------------------------------------------------------------------------- schema
def test_fiben_schema_is_an_ontology_encoding():
    s = schema.load()
    assert len(s.tables) == 152
    assert len(s.subclass_edges) == 135          # PK = FK to the parent
    assert len(s.relation_fks) == 24             # named after FIBO object properties
    assert ("LISTEDSECURITY", "SECURITY") in s.subclass_edges


def test_generated_names_are_frozen_and_readable():
    from nl2q import vkg_build
    assert (paths.KNOWLEDGE_DIR / "names.json").exists()
    assert vkg_build.class_name("AUTONOMOUSAGENT") == "AutonomousAgent"
    assert vkg_build.class_name("FINANCIALSERVICEACCOUNT") == "FinancialServiceAccount"
    assert vkg_build.prop_name("HASLASTTRADEDVALUE") == "hasLastTradedValue"


def test_mapping_and_metadata_cover_every_table():
    from rdflib import Graph, Namespace
    rr = Namespace("http://www.w3.org/ns/r2rml#")
    g = Graph().parse(paths.MAPPING_TTL)
    assert len(set(g.subjects(None, rr.TriplesMap))) == 152
    meta = json.loads(paths.DB_METADATA.read_text(encoding="utf-8"))
    assert len(meta["relations"]) == 152


# ----------------------------------------------------------------------------- comparison
def test_compare_permutation_iri_and_float_tolerance():
    gold_rows = [(1001000, "DDD", 39.920000001), (1001001, "MMM", 21.53)]
    sig = compare.signature(gold_rows)
    pred = [("MMM", 21.53, "https://example.org/fiben/data/security/1001001"),
            ("DDD", 39.92, "https://example.org/fiben/data/security/1001000")]
    m = compare.compare(sig, pred, 3)
    assert m.strict and m.lenient


def test_compare_rejects_wrong_rows_and_counts():
    sig = compare.signature([("a", 1), ("b", 2)])
    assert not compare.compare(sig, [("a", 1)], 2).strict
    assert not compare.compare(sig, [("a", 1), ("b", 3)], 2).strict


def test_compare_lenient_accepts_extra_columns():
    sig = compare.signature([("a",), ("b",)])
    m = compare.compare(sig, [("a", 1), ("b", 2)], 2)
    assert not m.strict and m.lenient


# ----------------------------------------------------------------------------- gold
def test_every_gold_query_executes_and_ceiling_is_recorded():
    rows = json.loads((paths.GOLD_DIR / "gold_sql.json").read_text(encoding="utf-8"))
    assert len(rows) == 237 and all(r["ok"] for r in rows)
    sp = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    accepted = sum(r["strict"] for r in sp)
    assert accepted / len(sp) >= 0.9


def test_splits_are_by_gold_query_without_leakage():
    from nl2q import gold, splits
    s = splits.load()
    sets = [set(v) for v in s.values()]
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])
    owner = {sid: k for k, v in s.items() for sid in v}
    for q in gold.questions():
        assert q.sql_id in owner                       # every paraphrase lands with its query


# ----------------------------------------------------------------------------- translator
def test_sql2sparql_semijoin_becomes_shared_variable_not_exists():
    from nl2q import gold, sql2sparql
    q = next(q for q in gold.questions() if q.sql_id == 107)
    s = sql2sparql.to_sparql(q.sql)
    assert "NOT EXISTS" in s and "?operson_haspersonname ." in s.split("NOT EXISTS", 1)[1]


# ----------------------------------------------------------------------------- checks / graph
@needs_db
def test_obqc_has_no_false_positives_on_accepted_gold():
    from nl2q import obqc
    sp = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    flagged = [r["sql_id"] for r in sp if r["strict"] and obqc.check_sparql(r["sparql"])]
    assert flagged == []


@needs_db
def test_obqc_reports_wrong_direction_and_unknown_terms():
    from nl2q import ir, obqc
    p = ir.Plan(nodes=[ir.Node(id="n1", cls="Person"), ir.Node(id="n2", cls="FinancialServiceAccount")],
                links=[ir.Link(subj="n1", prop="isOwnedBy", obj="n2")],
                attrs=[ir.Attr(id="a1", node="n1", prop="hasTickerSymbol")],
                projections=[ir.Projection(target="a1")])
    msgs = " ".join(obqc.check_plan(p))
    assert "reverse direction" in msgs and "has no hasTickerSymbol" in msgs


@needs_db
def test_query_graph_uses_inheritance_not_sibling_hubs():
    from nl2q.querygraph import load
    g = load()
    # a ListedSecurity may use isTradedOn, declared on its parent Security
    assert g.allowed("ListedSecurity", "isTradedOn", "FinancialMarket")
    # two disclosure siblings are not "connected" through their common ancestor
    import networkx as nx
    a, b = "Revenue", "Goodwill"
    if nx.has_path(g.g, a, b):
        path = nx.shortest_path(g.g, a, b)
        assert "Disclosure" not in path[1:-1]


@needs_db
def test_rerank_prefers_the_connected_reading():
    from nl2q import grounding as G
    r = G.ground("What are all the accounts managed by Nam Davarian?")
    assert r.best is not None
    assert ("FinancialServiceAccount", "isManagedBy", "Person") in r.best.tree


# ----------------------------------------------------------------------------- end to end
@needs_sidecar
def test_ir_renders_to_gold_rows():
    from nl2q import gold, ir, render, vkg
    golds = gold.load_results()
    p = ir.Plan(nodes=[ir.Node(id="n1", cls="ListedSecurity"), ir.Node(id="n2", cls="MonetaryAmount")],
                links=[ir.Link(subj="n1", prop="hasLastTradedValue", obj="n2")],
                attrs=[ir.Attr(id="a1", node="n1", prop="hasTickerSymbol"),
                       ir.Attr(id="a2", node="n1", prop="hasLegalName"),
                       ir.Attr(id="a3", node="n2", prop="hasAmount")],
                filters=[ir.Filter(target="a2", op="=", value="Alphabet Inc.")],
                projections=[ir.Projection(target="a1"), ir.Projection(target="a2"),
                             ir.Projection(target="a3")])
    e = vkg.run(render.render(p))
    assert e.ok and compare.compare(golds[1].sig, e.rows, len(e.columns)).strict


@needs_sidecar
def test_rule_arm_runs_end_to_end_offline():
    from nl2q import evaluate
    outs = evaluate.run("R", "val", limit=3, variants=False, verbose=False)
    assert len(outs) == 3 and all(o.outcome in ("correct", "wrong", "refused", "failed") for o in outs)


# ----------------------------------------------------------------------------- statistics / mutants
def test_mcnemar_and_bootstrap():
    a = [True] * 10 + [False] * 10
    b = [True] * 10 + [True] * 8 + [False] * 2
    r = stats.mcnemar_exact(a, b)
    assert r["n01"] == 8 and r["n10"] == 0 and r["p"] < 0.01
    m, lo, hi = stats.bootstrap_ci([1.0] * 50 + [0.0] * 50)
    assert lo < m < hi and abs(m - 0.5) < 1e-9
    assert stats.cohen_kappa([True, False] * 5, [True, False] * 5) == 1.0


@needs_db
def test_witness_instance_makes_empty_gold_observable():
    from nl2q import gold
    base = gold.load_results()
    v5 = gold.load_variants().get("V5", {})
    empty = [sid for sid, g in base.items() if g.row_count == 0]
    now = [sid for sid in empty if sid in v5 and v5[sid].count > 0]
    assert len(now) >= 0.75 * len(empty)            # 78 of 96 at build time


def test_witness_value_synthesis_respects_bounds():
    from nl2q import witness
    b = witness.Builder(schema.load())
    v = b._satisfy("MONETARYAMOUNT", "HASAMOUNT", [(">", 1500.0)], 0)
    assert v > 1500
    t = b._satisfy("SECURITIESTRANSACTION", "HASSETTLEMENTDATE",
                   [(">=", "2016-05-17 00:00:00"), ("<=", "2016-05-17 23:59:00")], 0)
    assert str(t).startswith("2016-05-17")
    assert b._violate("FINANCIALMARKET", "HASNAME", "=", "NYSE") != "NYSE"


@needs_db
def test_mutation_operators_change_the_query():
    from nl2q import mutate
    sp = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    q = next(r["sparql"] for r in sp if r["strict"] and "FILTER" in r["sparql"])
    ms = mutate.mutants(q, random.Random(0))
    assert ms and all(m != q for _, m in ms)
