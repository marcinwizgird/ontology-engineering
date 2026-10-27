"""The R2RML mapping specification: the generated Turtle is current, it conforms to the
database metadata and the TBox, and every conformance rule catches the defect it targets
(each test breaks the spec or the Turtle in one way and expects that rule to fire).

Offline: needs neither the sidecar nor the compiler.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from rdflib import Graph

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import build_mappings  # noqa: E402
import check_mappings  # noqa: E402

ARTIFACTS = build_mappings.ARTIFACTS


@pytest.fixture(scope="module")
def spec():
    return build_mappings.load()


@pytest.fixture(scope="module")
def tables():
    return check_mappings.load_metadata(ARTIFACTS / "db-metadata.json")


@pytest.fixture(scope="module")
def tbox():
    return check_mappings.load_tbox(ARTIFACTS / "fibo-subset.ttl")


def _findings(turtle: str, tables, tbox, **kw):
    g = Graph().parse(data=turtle, format="turtle", publicID="file:///mapping.ttl")
    return check_mappings.check(g, tables, tbox, **kw)


def _rules(findings, severity="error"):
    return {f.rule for f in findings if f.severity == severity}


def _map(spec, map_id):
    return next(m for m in spec["maps"] if m["id"] == map_id)


def _prop(m, predicate):
    return next(p for p in m["properties"] if p["predicate"] == predicate)


def test_committed_turtle_is_generated_from_the_spec():
    assert build_mappings.is_current(), "run `python tools/build_mappings.py`"


def test_mapping_conforms(spec, tables, tbox):
    findings = _findings(build_mappings.render(spec), tables, tbox)
    assert [f for f in findings if f.severity != "info"] == []


def test_coverage_reports_unmapped_columns(spec, tables, tbox):
    info = [f.message for f in _findings(build_mappings.render(spec), tables, tbox, coverage=True)
            if f.rule == "M12"]
    assert "COMPANY: unmapped columns COUNTRY_INC" in info
    assert not any(m.startswith("CUSTOMER:") and "CUST_TYPE" in m for m in info), \
        "a filter column counts as used"


# --- each rule fires on the defect it targets --------------------------------------------

def _break_spec(spec, edit):
    s = copy.deepcopy(spec)
    edit(s)
    return build_mappings.render(s)


@pytest.mark.parametrize("rule, edit", [
    ("M02", lambda s: _prop(_map(s, "CompanyMapping"), "ex-fibo:legalName").update(column="COMP_TITLE")),
    ("M04", lambda s: _map(s, "CompanyMapping").update(subject_column="SIC_CODE")),
    ("M05", lambda s: _prop(_map(s, "SecurityMapping"), "ex-fibo:issuedBy").update(column="SYMBOL")),
    ("M05", lambda s: _prop(_map(s, "SecurityMapping"), "ex-fibo:issuedBy").update(column="EXCH_ID")),
    ("M07", lambda s: _map(s, "BondMapping").update({"class": "fibo-sec-dbt-bnd:Debenture"})),
    ("M07", lambda s: _prop(_map(s, "BondMapping"), "ex-fibo:creditRating").update(predicate="ex-fibo:rating")),
    ("M08", lambda s: _map(s, "SecurityMapping")["properties"].append(
        {"predicate": "ex-fibo:issuedBy", "column": "ISSUER_COMP_ID"})),
    ("M09", lambda s: _prop(_map(s, "SecurityMapping"), "ex-fibo:lastPrice").pop("datatype")),
    ("M09", lambda s: _prop(_map(s, "SecurityMapping"), "ex-fibo:lastPrice").update(datatype="xsd:integer")),
    ("M10", lambda s: _prop(_map(s, "SecurityMapping"), "ex-fibo:issuedBy").update(ref="exchange", column="EXCH_ID")),
])
def test_rule_catches_its_defect(spec, tables, tbox, rule, edit):
    assert rule in _rules(_findings(_break_spec(spec, edit), tables, tbox))


def test_untyped_iri_family_is_reported(spec, tables, tbox):
    turtle = _break_spec(spec, lambda s: s["maps"].remove(_map(s, "ExchangeMapping")))
    assert "M06" in _rules(_findings(turtle, tables, tbox), "warning")


@pytest.mark.parametrize("rule, old, new", [
    # a hand edit that drops a column the map still uses from the view
    ("M02", 'SELECT \\"CUST_ID\\", \\"FULL_NAME\\", \\"DOMICILE\\" FROM \\"PUBLIC\\".\\"CUSTOMER\\" '
            "WHERE \\\"CUST_TYPE\\\" = 'RETAIL'",
            'SELECT \\"CUST_ID\\", \\"FULL_NAME\\" FROM \\"PUBLIC\\".\\"CUSTOMER\\" '
            "WHERE \\\"CUST_TYPE\\\" = 'RETAIL'"),
    # the defect the PoC hit: PostgreSQL folds unquoted placeholders to lower case
    ("M03", 'company/{\\"COMP_ID\\"}', "company/{COMP_ID}"),
    ("M03", 'rr:tableName "\\"PUBLIC\\".\\"COMPANY\\""', 'rr:tableName "PUBLIC.COMPANY"'),
    ("M01", '\\"PUBLIC\\".\\"EXCHANGE\\"', '\\"PUBLIC\\".\\"MARKET\\"'),
])
def test_rule_catches_hand_edits(spec, tables, tbox, rule, old, new):
    turtle = build_mappings.render(spec)
    assert old in turtle, "the test's search text no longer occurs in the generated Turtle"
    assert rule in _rules(_findings(turtle.replace(old, new, 1), tables, tbox))


@pytest.mark.parametrize("edit, message", [
    (lambda s: _map(s, "StockMapping").update(subject="share"), "unknown subject entity"),
    (lambda s: _prop(_map(s, "HoldingMapping"), "ex-fibo:holdsSecurity").update(ref="asset"), "unknown ref"),
    (lambda s: _map(s, "BondMapping").update(id="StockMapping"), "used more than once"),
    (lambda s: _map(s, "BondMapping").update({"class": "bnd:Bond"}), "unknown prefix"),
    (lambda s: _prop(_map(s, "HoldingMapping"), "ex-fibo:holdsSecurity").update(datatype="xsd:string"),
     "takes no datatype"),
])
def test_spec_structure_is_validated(spec, edit, message):
    s = copy.deepcopy(spec)
    edit(s)
    with pytest.raises(build_mappings.SpecError, match=message):
        build_mappings.validate(s)
