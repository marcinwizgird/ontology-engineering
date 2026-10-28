"""Evaluation framework stages S4 (Gate 2) and S6 (datasets), specification §8.
Pure logic unless marked; the database tests need ``data/fiben_vkg.duckdb``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl2q import gold, paths, splits  # noqa: E402
from nl2q.evalkit import gate2, gold_intermediates as gi, gtrain, obfuscate  # noqa: E402

HAS_DB = paths.DB.exists()
P = "PREFIX fiben: <https://example.org/fiben/voc#> SELECT "


# ----------------------------------------------------------------------------- S4 oracles
def test_gold_intermediates_from_sparql():
    q = (P + '?n WHERE { ?s a fiben:ListedSecurity . ?m a fiben:MonetaryAmount . '
         '?s fiben:hasLastTradedValue ?m . ?s fiben:hasLegalName ?n . ?m fiben:hasAmount ?a '
         'FILTER((?n = "Alphabet Inc.")) FILTER((?a > 100.5)) }')
    it = gi.extract(q)
    assert it["gold_subgraph_edges"] == [("ListedSecurity", "hasLastTradedValue", "MonetaryAmount")]
    assert set(it["gold_tier1_iris"]) == {"ListedSecurity", "MonetaryAmount", "hasLastTradedValue",
                                          "hasLegalName", "hasAmount"}
    vals = {(d["value"], d["cls"], d["prop"], d["kind"]) for d in it["gold_filter_values"]}
    assert vals == {("Alphabet Inc.", "ListedSecurity", "hasLegalName", "string"),
                    ("100.5", "MonetaryAmount", "hasAmount", "number")}
    assert gi.partial_mentions("What is Alphabet Inc.'s price?", it) == ["Alphabet Inc."]


def test_recall_at_k_and_mrr():
    m = gate2.recall_mrr(["a", "x", "b", "y", "z", "c"], {"a", "b", "c", "d"})
    assert m["recall@5"] == 0.5 and m["recall@20"] == 0.75 and m["mrr"] == 1.0
    assert gate2.recall_mrr(["x", "a"], {"a"})["mrr"] == 0.5


def test_refusal_precision_reweighted_to_20pct():
    r = gate2.refusal_metrics([True, False, False, False], {"U1": [True, True], "U2": [False, True]})
    assert r["recall"] == {"U1": 1.0, "U2": 0.5} and r["false_refusal_rate"] == 0.25
    assert r["precision_at_20pct"] == pytest.approx(0.75 * 0.2 / (0.75 * 0.2 + 0.25 * 0.8), abs=1e-4)


# ----------------------------------------------------------------------------- S6 Gtrain
def test_gtrain_refuses_questions_outside_the_train_split():
    val = splits.questions("val")[:1]
    with pytest.raises(gtrain.LeakError):
        gtrain.induce(val, gi.load())


def test_gtrain_entries_cite_train_queries_only():
    g = gtrain.load()
    train = set(splits.load()["train"])
    assert g["entries"] and g["access"]["split"] == "train"
    for e in g["entries"]:
        assert e["derived_from"] and set(e["derived_from"]) <= train, e["term"]


# ----------------------------------------------------------------------------- S6 obfuscation
def test_name_map_is_opaque_and_bijective():
    m = obfuscate.name_map()
    assert len(set(m["tables"].values())) == len(m["tables"]) == 152
    assert all(v.startswith("TBL_C") for v in m["tables"].values())
    # numbered in a seeded order, not alphabetically: the number says nothing about the name
    assert [m["tables"][t] for t in sorted(m["tables"])] != sorted(m["tables"].values())
    assert m == obfuscate.name_map()


def test_gold_sql_rewrite_leaves_no_original_names():
    m = obfuscate.name_map()
    sql = ('SELECT oL."HASLEGALNAME" AS n FROM FIBEN."LISTEDSECURITY" AS oL INNER JOIN FIBEN."MONETARYAMOUNT" AS oM '
           'ON oL."HASLASTTRADEDVALUE" = oM."MONETARYAMOUNTID" WHERE oM."HASAMOUNT" > 10')
    out = obfuscate.rewrite_sql(sql, m)
    assert "LISTEDSECURITY" not in out.upper() and "HASAMOUNT" not in out.upper().replace('"N"', "")
    assert f'"{obfuscate.OBF}"."{m["tables"]["LISTEDSECURITY"]}"' in out


# ----------------------------------------------------------------------------- database
@pytest.mark.skipif(not HAS_DB, reason="FIBEN database not present")
def test_l15_views_flatten_the_financial_statement_hierarchy():
    from nl2q.load_fiben import connect
    con = connect()
    if not con.execute("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'FIBEN_L15'").fetchone()[0]:
        pytest.skip("L1.5 views not built (python -m nl2q.evalkit.l15)")
    n_rev = con.execute('SELECT count(*) FROM FIBEN."REVENUE"').fetchone()[0]
    n_view = con.execute("SELECT count(*) FROM FIBEN_L15.ELEMENTOFFINANCIALSTATEMENT "
                         "WHERE list_contains(string_split(SUBCLASSES, ','), 'Revenue')").fetchone()[0]
    assert n_rev == n_view > 0
    # a subclass view carries its ancestors' columns
    cols = {r[0] for r in con.execute("DESCRIBE FIBEN_L15.LISTEDSECURITY").fetchall()}
    assert {"HASTICKERSYMBOL", "ISTRADEDON", "ISPROVIDEDBY"} <= cols


@pytest.mark.skipif(not HAS_DB, reason="FIBEN database not present")
def test_u3_values_are_absent_from_the_data():
    from nl2q.evalkit import unanswerable
    from nl2q.load_fiben import connect
    con = connect()
    u3 = [i for i in unanswerable.load()["items"] if i["stratum"] == "U3"]
    assert len(u3) == unanswerable.PER_STRATUM
    for it in u3[:10]:
        assert con.execute(it["construction"]["evidence_sql"]).fetchone()[0] == 0, it["id"]


def test_unanswerable_strata_are_split_and_labelled_by_construction():
    from nl2q.evalkit import unanswerable
    items = unanswerable.load()["items"]
    assert {i["stratum"] for i in items} == {"U1", "U2", "U3"}
    assert all(i["split"] in ("train", "val", "test") for i in items)
    assert all(not i["construction"]["mapped"] for i in items if i["stratum"] == "U1")
    assert all(i["construction"]["path_within_2_hops"] is False for i in items if i["stratum"] == "U2")
    qs = {q.question for q in gold.questions()}
    assert not qs & {i["question"] for i in items}
