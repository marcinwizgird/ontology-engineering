"""Mapping Studio R0: IRI policy, pattern catalogue P01-P08, lifting, the YAML spec and the
merged conformance / data checks (sip/architecture/components/MAPPING_STUDIO.md §15)."""

import importlib.util
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from semantic_intelligence.core.principal import Principal
from semantic_intelligence.platform import Platform
from semantic_intelligence.vkg import patterns as pt
from semantic_intelligence.vkg import spec as sp
from semantic_intelligence.vkg.r2rml import PredicateObjectMap, RefObjectMap, TermMap, \
    TriplesMap, parse_maps, to_graph
from semantic_intelligence.vkg.source import RelationalSource
from semantic_intelligence.vkg.validate import conformance, data_checks

NS = "https://ex.org/bank#"
DATA = "https://ex.org/bank/data/"
REPO = Path(__file__).resolve().parents[3]
POC = REPO / "LAB" / "PoCs" / "SPARQL-2-SQL"
FIBEN = REPO / "LAB" / "PoCs" / "FIBO-NL2Q-at-Scale" / "artifacts" / "ontop" / "fiben-mapping.r2rml.ttl"

BANK = """
CREATE TABLE currencies (code TEXT PRIMARY KEY, name TEXT);
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, customer_type TEXT,
                        nickname TEXT);
CREATE TABLE corporate_customers (customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
                                  registration_number TEXT);
CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_number TEXT, balance DECIMAL(12,2),
                       customer_id INTEGER REFERENCES customers(id),
                       currency TEXT REFERENCES currencies(code));
CREATE TABLE securities (id INTEGER PRIMARY KEY, ticker TEXT);
CREATE TABLE holdings (id INTEGER PRIMARY KEY, account_id INTEGER REFERENCES accounts(id),
                       security_id INTEGER REFERENCES securities(id), quantity REAL);
CREATE TABLE watchlist (account_id INTEGER REFERENCES accounts(id),
                        security_id INTEGER REFERENCES securities(id),
                        PRIMARY KEY (account_id, security_id));
INSERT INTO currencies VALUES ('EUR', 'Euro'), ('USD', 'US dollar');
INSERT INTO customers VALUES (1, 'Ada', 'RETAIL', NULL), (2, 'Acme Ltd', 'CORPORATE', 'acme'),
                             (3, 'Bob', 'RETAIL', NULL);
INSERT INTO corporate_customers VALUES (2, 'US-123');
INSERT INTO accounts VALUES (10, 'A-10', 100.5, 1, 'EUR'), (11, 'A-11', 2000, 2, 'USD'),
                            (12, 'A-12', 5, 99, 'EUR');
INSERT INTO securities VALUES (500, 'IBM'), (501, 'SAP');
INSERT INTO holdings VALUES (100, 10, 500, 3), (101, 11, 501, 10);
INSERT INTO watchlist VALUES (10, 501), (11, 500);
"""


def _ents() -> dict:
    return {e.name: e for e in (
        pt.EntityDef("customer", "customer", "customers", "id", DATA),
        pt.EntityDef("account", "account", "accounts", "id", DATA),
        pt.EntityDef("security", "security", "securities", "id", DATA),
        pt.EntityDef("holding", "holding", "holdings", "id", DATA),
        pt.EntityDef("currency", "currency", "currencies", "code", DATA))}


CASES = [
    ("P01", {"id": "CustomerMap", "table": "customers", "subject": "customer",
             "class": NS + "Customer",
             "properties": [{"predicate": NS + "customerName", "column": "name"}]}),
    ("P02", {"id": "CorporateMap", "table": "corporate_customers", "subject": "customer",
             "subject_column": "customer_id", "class": NS + "CorporateCustomer",
             "properties": [{"predicate": NS + "registrationNumber",
                             "column": "registration_number"}]}),
    ("P03", {"id": "Customers", "table": "customers", "subject": "customer",
             "column": "customer_type",
             "cases": {"RETAIL": {"id": "RetailMap", "class": NS + "RetailCustomer"}},
             "properties": [{"predicate": NS + "customerName", "column": "name"}]}),
    ("P04", {"id": "AccountLinks", "table": "accounts", "subject": "account",
             "properties": [{"predicate": NS + "heldBy", "ref": "customer",
                             "column": "customer_id"}]}),
    ("P05", {"id": "CustomerAccountLink", "table": "accounts", "subject": "customer",
             "subject_column": "customer_id",
             "properties": [{"predicate": NS + "hasAccount", "ref": "account"}]}),
    ("P06", {"id": "Watchlist", "table": "watchlist", "subject": "account",
             "subject_column": "account_id",
             "properties": [{"predicate": NS + "watches", "ref": "security",
                             "column": "security_id"}]}),
    ("P07", {"id": "HoldingMap", "table": "holdings", "subject": "holding",
             "class": NS + "Holding",
             "properties": [{"predicate": NS + "quantity", "column": "quantity"},
                            {"predicate": NS + "ofSecurity", "ref": "security",
                             "column": "security_id"}],
             "links": [{"id": "AccountHoldingLink", "subject": "account",
                        "subject_column": "account_id", "predicate": NS + "hasHolding"}]}),
    ("P08", {"id": "CurrencyMap", "table": "currencies", "subject": "currency",
             "class": NS + "Currency",
             "properties": [{"predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                             "column": "name"}]}),
]


@pytest.mark.parametrize("pid,params", CASES, ids=[c[0] for c in CASES])
def test_pattern_compiles_and_lifts_back(pid, params):
    db = RelationalSource("core", script=BANK).schema()
    maps = pt.compile_pattern(pid, params, _ents(), mint=lambda i: "urn:m#" + i)
    assert maps
    got = pt.lift(maps[0], _ents(), db_schema=db)
    assert got is not None and got[0] == pid
    again = pt.compile_map(got[1], _ents())
    assert set(again.triples()) == set(maps[0].triples())       # exact reproduction
    if pid == "P07":                                            # the link side is a P05
        assert pt.lift(maps[1], _ents(), db_schema=db)[0] == "P05"


def test_compile_pattern_refuses_the_wrong_shape():
    with pytest.raises(pt.PatternError, match="is a P01"):
        pt.compile_pattern("P02", CASES[0][1], _ents())


def test_maps_outside_the_patterns_stay_custom():
    e = _ents()
    ref = TriplesMap("urn:m#A", TermMap(template=DATA + 'account/{"id"}'), '"accounts"',
                     classes=[NS + "Account"], poms=[PredicateObjectMap(
                         NS + "heldBy", ref=RefObjectMap("urn:m#C", [("customer_id", "id")]))])
    unquoted = TriplesMap("urn:m#B", TermMap(template=DATA + "account/{id}"), "accounts",
                          classes=[NS + "Account"])
    foreign = TriplesMap("urn:m#F", TermMap(template="https://other.org/x/{\"id\"}"),
                         '"accounts"', classes=[NS + "Account"])
    assert pt.lift(ref, e) is None and pt.lift(unquoted, e) is None
    assert pt.lift(foreign, e) is None
    view = pt.lift_all([ref, unquoted], e)
    assert view["counts"] == {"custom": 2} and view["custom_share"] == 1.0


def test_detectors_find_the_schema_shapes():
    found = {(d["pattern"], d["table"]) for d in pt.detect(
        RelationalSource("core", script=BANK).schema())}
    assert {("P02", "corporate_customers"), ("P06", "watchlist"), ("P07", "holdings"),
            ("P08", "currencies"), ("P01", "customers"), ("P04", "accounts")} <= found


def test_spec_round_trip_without_yaml():
    spec = {"base_iri": DATA, "prefixes": {"b": NS, "xsd": "http://www.w3.org/2001/XMLSchema#"},
            "entities": {"customer": {"path": "customer", "table": "customers", "key": "id"},
                         "account": {"path": "account", "table": "accounts", "key": "id"}},
            "maps": [{"id": "CustomerMap", "table": "customers", "subject": "customer",
                      "class": "b:Customer",
                      "properties": [{"predicate": "b:customerName", "column": "name"}]},
                     {"id": "RetailMap", "table": "customers",
                      "filter": {"customer_type": "RETAIL"}, "subject": "customer",
                      "class": "b:RetailCustomer"},
                     {"id": "AccountMap", "table": "accounts", "subject": "account",
                      "class": "b:Account",
                      "properties": [{"predicate": "b:balance", "column": "balance",
                                      "datatype": "xsd:decimal"},
                                     {"predicate": "b:heldBy", "ref": "customer",
                                      "column": "customer_id"}]}]}
    ents, maps = sp.compile_spec(spec)
    back = sp.maps_to_spec(maps, ents, base_iri=DATA, prefixes=spec["prefixes"])
    assert "custom" not in back and back["entities"] == spec["entities"]
    key = lambda s: sorted((dict(m, properties=sorted(m.get("properties", []), key=str))  # noqa
                            for m in s["maps"]), key=str)
    assert key(back) == key(spec)
    with pytest.raises(sp.SpecError, match="unknown subject entity"):
        sp.validate_spec(dict(spec, maps=[dict(spec["maps"][0], subject="nobody")]))


# ----------------------------------------------------------------------------- exit criteria
needs_yaml = pytest.mark.skipif(importlib.util.find_spec("yaml") is None,
                                reason="PyYAML not installed")


@needs_yaml
@pytest.mark.skipif(not (POC / "vkg-artifacts" / "mapping-spec.yaml").exists(),
                    reason="SPARQL-2-SQL PoC not present")
def test_poc_spec_imports_lifts_and_renders_byte_identical():
    """R0 exit criterion: the PoC's spec lifts with zero custom maps, and the rendered
    R2RML equals the PoC generator's committed output byte for byte."""
    text = (POC / "vkg-artifacts" / "mapping-spec.yaml").read_text(encoding="utf-8")
    committed = (POC / "vkg-artifacts" / "fiben-mappings.r2rml.ttl").read_text(
        encoding="utf-8").replace("\r\n", "\n")
    spec = sp.load_spec(text)
    header = committed.split("\n\n", 1)[0] + "\n"            # the PoC's own comment lines
    assert sp.render_r2rml(spec, header=header) == committed
    ents, maps = sp.compile_spec(spec, mint=lambda i: "http://x/m#" + i)
    view = pt.lift_all(maps, ents, schema=spec["schema"])
    assert view["custom_share"] == 0.0 and len(view["maps"]) == len(spec["maps"])
    assert isomorphic(to_graph(maps), Graph().parse(data=committed, format="turtle",
                                                    publicID="http://x/m"))
    back = sp.maps_to_spec(maps, ents, base_iri=spec["base_iri"], prefixes=spec["prefixes"],
                           schema=spec["schema"])
    key = lambda s: [dict(m, properties=sorted(m.get("properties", []), key=str))  # noqa
                     for m in s["maps"]]
    assert key(back) == key(spec) and back["entities"] == spec["entities"]
    assert sp.load_spec(sp.dump_spec(back)) == back             # YAML text round trip


@pytest.mark.skipif(not FIBEN.exists(), reason="FIBO-NL2Q-at-Scale artefacts not present")
def test_fiben_mapping_lifts_with_few_custom_maps():
    """R0 exit criterion: the generated 152-table FIBEN mapping lifts with <= 5% custom
    maps under an IRI policy inferred from its templates."""
    maps = parse_maps(Graph().parse(FIBEN))
    ents, schema = pt.infer_entities(maps)
    view = pt.lift_all(maps, ents, schema=schema)
    assert len(maps) == 152 and schema == "FIBEN"
    assert view["custom_share"] <= 0.05, view["counts"]


# ----------------------------------------------------------------------------- platform
@pytest.fixture
def P():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u in ("ann", "mia"):
        p.registry.add_principal(Principal(u))
    p.call("admin", None, "governance.createProject", name="bank", base_uri="https://ex.org/bank")
    p.call("admin", "bank", "governance.bind", principal="ann", roles=["ontologist"])
    p.call("admin", "bank", "governance.bind", principal="mia", roles=["mapper"])
    for c, parent in (("Customer", None), ("CorporateCustomer", "Customer"),
                      ("RetailCustomer", "Customer"), ("Account", None), ("Security", None),
                      ("Holding", None), ("Currency", None)):
        p.call("ann", "bank", "owl.createClass", name=c, parent=parent)
    for name, kind, dom, rng in (
            ("customerName", "data", "Customer", "xsd:string"),
            ("registrationNumber", "data", "CorporateCustomer", "xsd:string"),
            ("balance", "data", "Account", "xsd:decimal"),
            ("quantity", "data", "Holding", "xsd:decimal"),
            ("heldBy", "object", "Account", "Customer"),
            ("hasAccount", "object", "Customer", "Account"),
            ("hasHolding", "object", "Account", "Holding"),
            ("ofSecurity", "object", "Holding", "Security"),
            ("watches", "object", "Account", "Security")):
        p.call("ann", "bank", "owl.createProperty", name=name, kind=kind, domain=dom, range=rng)
    p.call("mia", "bank", "mapping.registerDatabase", source_id="core", script=BANK)
    return p


def _policy(P):
    for name, table, key in (("customer", "customers", "id"), ("account", "accounts", "id"),
                             ("security", "securities", "id"), ("holding", "holdings", "id")):
        P.call("mia", "bank", "mapping.setEntity", name=name, path=name, table=table, key=key)


def _codes(findings, sev=None):
    return {(f["code"], (f["map"] or "").split("#")[-1]) for f in findings
            if sev is None or f["severity"] == sev}


def test_apply_patterns_preview_lift_and_validate(P):
    with pytest.raises(Exception, match="IRI policy first"):
        P.call("mia", "bank", "mapping.applyPattern", pattern="P01", params={})
    _policy(P)
    P.call("mia", "bank", "mapping.applyPattern", pattern="P01", params={
        "id": "CustomerMap", "table": "customers", "subject": "customer", "class": "Customer",
        "properties": [{"predicate": "customerName", "column": "name"}]})
    P.call("mia", "bank", "mapping.applyPattern", pattern="P02", params={
        "id": "CorporateMap", "table": "corporate_customers", "subject": "customer",
        "subject_column": "customer_id", "class": "CorporateCustomer",
        "properties": [{"predicate": "registrationNumber", "column": "registration_number"}]})
    P.call("mia", "bank", "mapping.applyPattern", pattern="P03", params={
        "id": "Customers", "table": "customers", "subject": "customer",
        "column": "customer_type", "cases": {"RETAIL": {"id": "RetailMap",
                                                        "class": "RetailCustomer"}},
        "properties": [{"predicate": "customerName", "column": "name"}]})
    P.call("mia", "bank", "mapping.applyPattern", pattern="P01", params={
        "id": "AccountMap", "table": "accounts", "subject": "account", "class": "Account",
        "properties": [{"predicate": "balance", "column": "balance", "datatype": "xsd:decimal"},
                       {"predicate": "heldBy", "ref": "customer", "column": "customer_id"}]})
    P.call("mia", "bank", "mapping.applyPattern", pattern="P05", params={
        "id": "CustomerAccountLink", "table": "accounts", "subject": "customer",
        "subject_column": "customer_id",
        "properties": [{"predicate": "hasAccount", "ref": "account"}]})
    view = P.call("ann", "bank", "mapping.lift")
    assert {m["id"]: m["pattern"] for m in view["maps"]} == {
        "CustomerMap": "P01", "CorporateMap": "P02", "RetailMap": "P03", "AccountMap": "P01",
        "CustomerAccountLink": "P05"}
    assert not view["entities_inferred"]
    prev = P.call("ann", "bank", "mapping.preview", map_id="RetailMap")
    assert sorted(t["o"] for t in prev["triples"] if t["p"] == NS + "customerName") == [
        "Ada", "Bob"]
    rows = P.call("ann", "bank", "mapping.queryData",
                  query=f"PREFIX : <{NS}> SELECT ?n WHERE {{ ?c a :Customer ; :customerName ?n }}")
    assert sorted(r["n"] for r in rows["rows"]) == ["Acme Ltd", "Ada", "Bob"]
    r = P.call("ann", "bank", "mapping.validate")
    assert r["summary"]["error"] == 0, [f for f in r["findings"] if f["severity"] == "error"]
    # account 12 points at customer 99, which does not exist
    assert ("D4", "AccountMap") in _codes(r["findings"])
    assert any(f["code"] == "M12" and f.get("table") == "watchlist" for f in r["findings"])


def test_set_entity_recompiles_maps_in_one_commit(P):
    _policy(P)
    P.call("mia", "bank", "mapping.applyPattern", pattern="P01", params={
        "id": "AccountMap", "table": "accounts", "subject": "account", "class": "Account",
        "properties": [{"predicate": "heldBy", "ref": "customer", "column": "customer_id"}]})
    P.call("mia", "bank", "mapping.setEntity", name="customer", path="party", table="customers",
           key="id")
    acc = next(m for m in P.call("ann", "bank", "mapping.list")["maps"] if m["id"] == "AccountMap")
    assert acc["predicateObjects"][0]["template"] == DATA + 'party/{"customer_id"}'
    P.call("mia", "bank", "history.undo")                      # one commit, one undo
    acc = next(m for m in P.call("ann", "bank", "mapping.list")["maps"] if m["id"] == "AccountMap")
    assert acc["predicateObjects"][0]["template"] == DATA + 'customer/{"customer_id"}'
    with pytest.raises(Exception, match="compiled from entity"):
        P.call("mia", "bank", "mapping.removeEntity", name="customer")
    P.call("mia", "bank", "mapping.removeEntity", name="holding")


def test_export_and_import_spec_between_projects(P):
    _policy(P)
    P.call("mia", "bank", "mapping.applyPattern", pattern="P01", params={
        "id": "CustomerMap", "table": "customers", "subject": "customer", "class": "Customer",
        "properties": [{"predicate": "customerName", "column": "name"}]})
    spec = P.call("ann", "bank", "mapping.exportSpec", staged=True, format="dict")
    assert spec["prefixes"]["bank"] == NS
    assert spec["maps"] == [{"id": "CustomerMap", "table": "customers", "subject": "customer",
                             "class": "bank:Customer",
                             "properties": [{"predicate": "bank:customerName",
                                             "column": "name"}]}]
    P.call("admin", None, "governance.createProject", name="bank2", base_uri="https://ex.org/bank")
    P.call("admin", "bank2", "mapping.importSpec", spec=spec, source_id="core")
    a = P.call("ann", "bank", "mapping.list")["maps"]
    b = P.call("admin", "bank2", "mapping.list")["maps"]
    strip = lambda ms: [{k: v for k, v in m.items() if k not in ("iri", "source", "status")}  # noqa
                        for m in ms]
    assert strip(a) == strip(b)
    assert set(P.call("admin", "bank2", "mapping.lift")["entities"]) == {
        "customer", "account", "security", "holding"}
    if importlib.util.find_spec("yaml"):
        text = P.call("ann", "bank", "mapping.exportSpec", staged=True)
        assert "CustomerMap" in text and "base_iri" in text


# ----------------------------------------------------------------------------- the rules
def test_conformance_and_data_rules_fire():
    src = RelationalSource("core", script=BANK)
    onto = Graph().parse(data=f"""
        @prefix : <{NS}> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        :Customer a owl:Class . :Account a owl:Class . :Security a owl:Class .
        :heldBy a owl:ObjectProperty ; rdfs:domain :Account ; rdfs:range :Customer .
        :ticker a owl:DatatypeProperty ; rdfs:domain :Security .""", format="turtle")

    def tm(i, tpl, table, classes=(), poms=(), sql=None):
        return TriplesMap("urn:m#" + i, TermMap(template=tpl), table, sql, list(classes),
                          list(poms))
    maps = [
        tm("Cust", DATA + 'customer/{"id"}', '"customers"', [NS + "Customer"]),
        # M04: typed by a non-key column; M11: that column is nullable
        tm("ByNick", DATA + 'nick/{"nickname"}', '"customers"', [NS + "Customer"]),
        # M05: link through a column that is not a foreign key; M06: family never typed
        tm("Acc", DATA + 'account/{"id"}', '"accounts"', [NS + "Account"], [
            PredicateObjectMap(NS + "heldBy", object=TermMap(
                template=DATA + 'customer/{"account_number"}')),
            PredicateObjectMap(NS + "inCurrency", object=TermMap(
                template=DATA + 'currency/{"currency"}'))]),
        # M10: ticker's domain is Security, the subject is a Customer
        tm("Bad", DATA + 'customer/{"id"}', '"customers"', [NS + "Customer"], [
            PredicateObjectMap(NS + "ticker", object=TermMap(column='"name"'))]),
        # D1: no rows; D3: repeated keys
        tm("None", DATA + 'customer/{"id"}', None, [NS + "Customer"],
           sql="SELECT \"id\" FROM \"customers\" WHERE \"customer_type\" = 'NOPE'"),
        tm("Dup", DATA + 'account/{"customer_id"}', None, [NS + "Account"],
           sql='SELECT "customer_id" FROM "accounts" UNION ALL SELECT "customer_id" FROM "accounts"'),
    ]
    found = conformance(maps, onto, {"core": src}) + data_checks(maps, {"core": src})
    codes = _codes(found)
    assert {("M04", "ByNick"), ("M11", "ByNick"), ("M05", "Acc"), ("M06", ""),
            ("M10", "Bad"), ("D1", "None"), ("D2", "ByNick"), ("D3", "Dup")} <= codes
    assert ("M12", "") in codes                                # unmapped tables
    assert not {c for c in codes if c[1] == "Cust"}            # the clean map stays clean
