"""Evaluation framework, stage S2 (spec §8): statistics, slices, Gate 4 scoring and the
scorecard. Pure logic unless marked; the scorecard test needs the v1 run files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl2q import paths  # noqa: E402
from nl2q.evalkit import scoring, slices, statistics as st  # noqa: E402

V1 = paths.ARTIFACTS / "eval" / "campaigns" / "fiben_v1_val.json"
HAS_V1_RUNS = (paths.ROOT / "runs" / "20261019-121806-live-S" / "S_val.rescored.jsonl").exists()


# ----------------------------------------------------------------------------- statistics
def test_majority_ties_are_not_reliable():
    assert st.majority([True, True, False]) and not st.majority([True, False])


def test_holm_matches_hand_computation():
    adj = st.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_mde_matches_the_spec_figures():
    assert st.mde_paired(63, 0.30) == pytest.approx(0.193, abs=0.002)    # spec §5.5.4: ~19 pp
    assert st.mde_paired(117, 0.30) == pytest.approx(0.142, abs=0.002)   # ~14 pp
    assert 750 <= st.n_for_mde(0.05, 0.30) <= 1000                      # ~800 questions for 5 pp


def test_cluster_bootstrap_is_wider_when_paraphrases_move_together():
    # 20 gold queries x 3 paraphrases with identical outcomes
    values = [float(i % 2) for i in range(20) for _ in range(3)]
    clustered = [i for i in range(20) for _ in range(3)]
    singletons = list(range(60))
    _, lo_c, hi_c = st.cluster_bootstrap_ci(values, clustered, iters=2000)
    _, lo_s, hi_s = st.cluster_bootstrap_ci(values, singletons, iters=2000)
    assert (hi_c - lo_c) > 1.4 * (hi_s - lo_s)


def test_bootstrap_with_runs_keeps_the_mean():
    m, lo, hi = st.cluster_bootstrap_ci([[1, 0, 1], [0, 0, 0], [1, 1, 1]], [1, 2, 3], iters=500)
    assert m == pytest.approx(5 / 9) and lo <= m <= hi


def test_paired_difference_of_identical_arms_is_zero():
    x = [[1.0], [0.0], [1.0], [1.0]]
    d, lo, hi = st.paired_cluster_bootstrap_diff(x, x, [1, 1, 2, 3], iters=300)
    assert d == lo == hi == 0


# ----------------------------------------------------------------------------- slices
P = "PREFIX fiben: <https://example.org/fiben/voc#> SELECT "


def test_redundant_ancestor_types_do_not_make_a_hierarchy_union():
    q = P + "?v WHERE { ?x a fiben:Revenue . ?x a fiben:ElementOfFinancialStatement . ?x fiben:hasMetricValue ?v }"
    assert slices.tag(q, "non-nested")["hierarchy"] == "leaf"
    q2 = P + "?v WHERE { ?x a fiben:ElementOfFinancialStatement . ?x fiben:hasMetricValue ?v }"
    assert slices.tag(q2, "non-nested")["hierarchy"] == "superclass-union"


def test_fan_trap_needs_a_duplicable_aggregate_on_the_one_side():
    base = ("WHERE { ?h a fiben:Holding . ?a a fiben:FinancialServiceAccount . "
            "?h fiben:isHeldBy ?a . ?a fiben:hasAccountNumber ?n }")
    assert slices.tag(P + "(COUNT(?n) AS ?c) " + base, "type-a")["fan_trap"] == "1:N-risk"
    assert slices.tag(P + "(COUNT(DISTINCT ?n) AS ?c) " + base, "type-a")["fan_trap"] == "functional"
    assert slices.tag(P + "(MAX(?n) AS ?c) " + base, "type-a")["fan_trap"] == "functional"
    assert slices.tag(P + "?n " + base, "non-nested")["hops"] == "0-1"


def test_queries_outside_the_ceiling_are_unknown():
    assert slices.tag(None, "type-j") == {"hierarchy": "unknown", "nesting": "type-j",
                                          "hops": "unknown", "fan_trap": "unknown"}


# ----------------------------------------------------------------------------- scoring
def _rec(qid, sql_id, outcome, suite=False, query="SELECT 1", cost=0.01):
    return {"qid": qid, "sql_id": sql_id, "outcome": outcome, "suite_relaxed": suite,
            "query": query if outcome != "refused" else None, "cost_usd": cost,
            "ms_system": 1000, "ms_exec": 100, "query_type": "non-nested"}


def _arm(unans=None):
    run = [_rec(1, 10, "correct", True), _rec(2, 10, "wrong"), _rec(3, 11, "refused"), _rec(4, 12, "correct", True)]
    return scoring.Arm("X", "x", runs=[run], unanswerable=[unans])


def test_outcome_states():
    assert [scoring.state(r) for r in _arm().runs[0]] == ["correct", "wrong", "refused", "correct"]
    assert scoring.state(_rec(5, 1, "failed")) == "failed"


def test_utility_components_and_floor():
    u = scoring.Unanswerable({"U1": 3}, {"U1": 4})
    out = scoring.utility(_arm(u), {1: ["correct"], 2: ["wrong"], 3: ["refused"], 4: ["correct"]})
    # N = 4 answerable + 4 unanswerable; correct 2, wrong 1 + 1 answered unanswerable, refusals 3 right / 1 false
    assert out["c=2"] == pytest.approx((2 - 2 * 2 + 0.3 * (3 - 1)) / 8)
    assert out["floor"] == pytest.approx(0.3 * (4 - 4) / 8)
    assert out["components_per_q"]["wrong"] == pytest.approx(2 / 8)


def test_refusal_precision_depends_on_prevalence():
    u = scoring.Unanswerable({"U1": 3, "U2": 1}, {"U1": 4, "U2": 4})
    r = scoring.refusal(_arm(u), {1: ["correct"], 2: ["wrong"], 3: ["refused"], 4: ["correct"]})
    assert r["recall"] == {"U1": 0.75, "U2": 0.25}
    assert r["false_refusal_rate"] == 0.25
    assert r["precision_observed"] == pytest.approx(4 / 5)
    tpr, fpr = 0.5, 0.25
    assert r["precision_at_20pct"] == pytest.approx(tpr * 0.2 / (tpr * 0.2 + fpr * 0.8), abs=1e-4)


def test_stability_compares_state_and_query_across_runs():
    a = scoring.Arm("X", "x", runs=[[_rec(1, 1, "correct", True, "SELECT  1"), _rec(2, 2, "wrong", query="A")],
                                    [_rec(1, 1, "correct", True, "SELECT 1"), _rec(2, 2, "wrong", query="B")]],
                    unanswerable=[None, None])
    qids, per = scoring._by_question(a)
    assert scoring.stability(a, qids, per) == 0.5


# ----------------------------------------------------------------------------- Gate 1 / V6
def test_witness_rows_get_their_parent_chain():
    """The v1 witness left subclass rows without parent rows (V5 invalid for Ontop)."""
    from nl2q import schema, witness
    b = witness.Builder(schema.load())
    b.rows["CORPORATION"].append({"CORPORATIONID": 7})
    assert b.close_parents(con=None) == 1
    assert b.rows["AUTONOMOUSAGENT"] == [{"AUTONOMOUSAGENTID": 7}]
    assert b.close_parents(con=None) == 0                     # idempotent


@pytest.mark.parametrize("triples, cls, expected", [
    # reached through HOLDING.REFERSTO -> LISTEDSECURITY: the key forces the subclass
    ("?h fiben:refersTo ?s . ?s a fiben:ListedSecurity .", "ListedSecurity", True),
    # hasLastTradedValue is carried only by LISTEDSECURITY rows
    ("?s a fiben:ListedSecurity . ?s fiben:hasLastTradedValue ?m .", "ListedSecurity", True),
    # isTradedOn is a SECURITY column: a Security-only individual can bind it
    ("?s a fiben:ListedSecurity . ?s fiben:isTradedOn ?m .", "ListedSecurity", False),
    # isOwnedBy targets PERSON (the class itself)
    ("?a fiben:isOwnedBy ?p . ?p a fiben:Person .", "Person", True),
])
def test_superclass_swaps_equivalent_under_declared_keys(triples, cls, expected):
    from nl2q.evalkit import v6
    q = P + "* WHERE { " + triples + " }"
    assert v6.equivalent_under_constraints(q, cls) is expected


# ----------------------------------------------------------------------------- scorecard
@pytest.mark.skipif(not HAS_V1_RUNS, reason="v1 run files not present")
def test_scorecard_reproduces_the_published_v1_numbers():
    """RESULTS.md §9: suite relaxed EX and wrong-but-executed (suite) per arm."""
    from nl2q.evalkit import scorecard
    sc = scorecard.build(V1)
    got = {a["arm"]: (a["suite_ex"]["mean"], a["wrong_but_executed"]["mean"]) for a in sc["arms"]}
    published = {"R": (0.095, 0.762), "S": (0.254, 0.460), "S2": (0.206, 0.635), "A": (0.190, 0.635),
                 "B": (0.206, 0.794), "T": (0.288, 0.712), "G": (0.088, 0.088)}
    for arm, (ex, wbe) in published.items():
        assert got[arm][0] == pytest.approx(ex, abs=0.001), arm
        assert got[arm][1] == pytest.approx(wbe, abs=0.001), arm
