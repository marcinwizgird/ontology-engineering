"""Semantic enrichment (nl2q.enrich, nl2q.usgaap): the review is complete and well-formed,
taxonomy linking behaves as specified, and the enrichment cannot read benchmark answers.

Pure-logic tests always run; tests that need the loaded DuckDB or the downloaded US GAAP
linkbases skip with the reason.
"""

from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl2q import enrich, paths, usgaap  # noqa: E402

HAS_DB = paths.DB.exists()
HAS_USGAAP = usgaap.available()
HAS_FIBO = (paths.CACHE / "fibo.pkl").exists() or paths.FIBO_DIR.exists()


def _alignment():
    with (paths.KNOWLEDGE_DIR / "alignment.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ----------------------------------------------------------------------------- review
def test_every_suggested_alignment_is_reviewed():
    suggested = {(r["fiben"], r["kind"]) for r in _alignment() if r["status"] == "suggested"}
    reviewed = {(r["fiben"], r["kind"]) for r in enrich.load_review()}
    assert len(suggested) == 25
    assert suggested <= reviewed


def test_review_rows_are_well_formed():
    known = {(r["fiben"], r["kind"]) for r in _alignment()}
    for r in enrich.load_review():
        assert (r["fiben"], r["kind"]) in known, r["fiben"]
        assert r["decision"] in enrich.MATCH_TYPES
        assert r["rationale"], f"{r['fiben']}: a decision needs a rationale"
        assert (r["decision"] == "reject") == (not r["fibo"]), r["fiben"]


@pytest.mark.skipif(not HAS_FIBO, reason="FIBO not available")
def test_review_targets_exist_in_fibo_with_the_right_kind():
    from nl2q import fibo
    f = fibo.load()
    for r in enrich.load_review():
        if r["decision"] == "reject":
            continue
        assert r["fibo"] in f.terms, f"{r['fiben']}: {r['fibo']} is not a FIBO term"
        assert (f.terms[r["fibo"]].kind == "class") == (r["kind"] == "class"), r["fiben"]


# ----------------------------------------------------------------------------- US GAAP
_LINKBASE = """<?xml version='1.0' encoding='UTF-8'?>
<link:linkbase xmlns:link='http://www.xbrl.org/2003/linkbase' xmlns:xlink='http://www.w3.org/1999/xlink'>
<link:labelLink xlink:role='http://www.xbrl.org/2003/role/link' xlink:type='extended'>
<link:loc xlink:href='us-gaap-2015-01-31.xsd#us-gaap_Revenues' xlink:label='loc_Revenues' xlink:type='locator'/>
<link:label xlink:label='lab_Revenues' xlink:role='http://www.xbrl.org/2003/role/label' xlink:type='resource'>Revenues</link:label>
<link:label xlink:label='lab_Revenues' xlink:role='http://www.xbrl.org/2003/role/documentation' xlink:type='resource'>Amount of
   revenue recognized.</link:label>
<link:label xlink:label='lab_Revenues' xlink:role='http://www.xbrl.org/2003/role/totalLabel' xlink:type='resource'>Total</link:label>
<link:labelArc xlink:from='loc_Revenues' xlink:to='lab_Revenues' xlink:type='arc'/>
</link:labelLink>
</link:linkbase>"""


def test_linkbase_parsing_follows_arcs_and_roles(tmp_path):
    p = tmp_path / "lab.xml"
    p.write_text(_LINKBASE, encoding="utf-8")
    els: dict = {}
    usgaap.parse_linkbase(p, els)
    e = els["Revenues"]
    assert e.label == "Revenues"
    assert e.documentation == "Amount of revenue recognized."   # whitespace normalised
    assert e.labels() == ["Revenues"]                           # total label not used


def _tx(*names):
    els = {n: usgaap.Element(n, label=n, documentation=f"doc {n}") for n in names}
    return usgaap.Taxonomy(els, {k.upper(): k for k in els})


@pytest.mark.parametrize("table, observed, names, expected, method", [
    # the data's own elements win, and the one named like the class comes first
    ("LIABILITY", {"LIABILITY": ["LiabilitiesAndStockholdersEquity", "Liabilities"]},
     ["LiabilitiesAndStockholdersEquity", "Liabilities"], ["Liabilities", "LiabilitiesAndStockholdersEquity"], "observed"),
    ("GOODWILL", {}, ["Goodwill", "GoodwillDisclosureTextBlock"], ["Goodwill", "GoodwillDisclosureTextBlock"], "name"),
    ("DIVIDENDSPAYABLE", {}, ["DividendsPayableCurrent"], ["DividendsPayableCurrent"], "name-variant"),
    ("REVENUE", {}, ["Revenues"], ["Revenues"], "name-variant"),
    ("BUSINESSCOMBINATIONDISCLOSURE", {}, ["BusinessCombinationDisclosureTextBlock"],
     ["BusinessCombinationDisclosureTextBlock"], "text-block"),
    ("FRESHSTARTADJUSTMENTS", {}, ["FreshStartAdjustmentIncreaseDecrease"], [], ""),  # no fuzzy matches
])
def test_taxonomy_linking(table, observed, names, expected, method):
    assert enrich.link_elements(table, _tx(*names), observed) == (expected, method)


# ----------------------------------------------------------------------------- integrity
def test_enrichment_cannot_read_benchmark_answers():
    """Unlike the K4 glossary, enrichment must not see gold SQL/SPARQL or the questions."""
    tree = ast.parse((ROOT / "nl2q" / "enrich.py").read_text(encoding="utf-8"))
    imported = {a.name.split(".")[-1] for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert not imported & {"gold", "splits", "evaluate", "glossary", "ceiling", "sql2sparql"}
    src = (ROOT / "nl2q" / "enrich.py").read_text(encoding="utf-8")
    assert "GOLD_DIR" not in src and "FIBEN_QUERIES" not in src


@pytest.mark.skipif(not HAS_FIBO, reason="FIBO not available")
def test_without_enrichment_the_pack_is_unchanged():
    from nl2q import knowledge
    terms = [t for t in knowledge.build_terms(()) if t.tier == "mapped"]
    assert len(terms) == 220
    assert sum(bool(t.definition) for t in terms) == 48


@pytest.mark.skipif(not (HAS_DB and HAS_USGAAP and HAS_FIBO), reason="needs the DuckDB, FIBO and the US GAAP linkbases")
def test_enrichment_defines_nearly_every_mapped_term():
    from nl2q import knowledge
    terms = {t.local: t for t in knowledge.build_terms(enrich.LAYERS) if t.tier == "mapped"}
    assert sum(bool(t.definition) for t in terms.values()) >= 210
    assert terms["Revenue"].source == "us-gaap" and "revenue" in terms["Revenue"].definition.lower()
    assert "Net Income (Loss) Attributable to Parent" in terms["ComprehensiveIncome"].synonyms
    assert terms["FinancialMarket"].source == "fibo-reviewed"           # reviewed: close to Exchange
    assert terms["Liability"].source == "us-gaap"                        # rejected FIBO, US GAAP instead
    assert "10-K" in terms["hasDocumentType"].definition                 # derived, with its codes
    # a broad match contributes its label, never its definition
    assert "income" in terms["InvestmentIncome"].synonyms
    assert terms["InvestmentIncome"].source != "fibo-reviewed"
