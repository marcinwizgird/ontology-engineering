"""Virtual knowledge graph: R2RML mappings authored and queried while editing the ontology."""

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, XSD

from semantic_intelligence.core.principal import Principal
from semantic_intelligence.governance.registry import AuthorizationError
from semantic_intelligence.platform import Platform
from semantic_intelligence.vkg.r2rml import RR, TriplesMap, parse_maps
from semantic_intelligence.vkg.source import RelationalSource, UnsafeSQL, check_select
from semantic_intelligence.vkg.suggest import key

NS = "https://ex.org/bank#"
DATA = "https://ex.org/bank/data/"

BANK = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, customer_type TEXT,
                        country TEXT);
CREATE TABLE corporate_customers (customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
                                  registration_number TEXT);
CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_number TEXT, balance DECIMAL(12,2),
                       customer_id INTEGER REFERENCES customers(id));
CREATE TABLE holdings (id INTEGER PRIMARY KEY, account_id INTEGER REFERENCES accounts(id),
                       ticker TEXT, quantity REAL);
INSERT INTO customers VALUES (1, 'Ada', 'RETAIL', 'GB'), (2, 'Acme Ltd', 'CORPORATE', 'US'),
                             (3, 'Bob', 'RETAIL', 'PL'), (4, 'Globex', 'CORPORATE', 'DE');
INSERT INTO corporate_customers VALUES (2, 'US-123'), (4, 'DE-456');
INSERT INTO accounts VALUES (10, 'A-10', 100.5, 1), (11, 'A-11', 2000, 2), (12, 'A-12', 5, 4);
INSERT INTO holdings VALUES (100, 10, 'IBM', 3), (101, 11, 'MSFT', 10), (102, 12, 'SAP', 1.5);
"""

CUSTOMER_MAP = {"id": "CustomerMap", "logicalTable": {"tableName": "customers"},
                "subject": {"template": DATA + "customer/{id}", "classes": ["Customer"]},
                "predicateObjects": [{"predicate": "customerName", "column": "name"}]}
CORPORATE_MAP = {"id": "CorporateMap", "logicalTable": {"tableName": "corporate_customers"},
                 "subject": {"template": DATA + "customer/{customer_id}",
                             "classes": ["CorporateCustomer"]},
                 "predicateObjects": [{"predicate": "registrationNumber",
                                       "column": "registration_number"}]}
ACCOUNT_MAP = {"id": "AccountMap", "table": "accounts",
               "subject": {"template": DATA + "account/{id}", "classes": ["Account"]},
               "predicateObjects": [
                   {"predicate": "balance", "column": "balance", "datatype": "xsd:decimal"},
                   {"predicate": "heldBy", "parent": "CustomerMap",
                    "joins": [["customer_id", "id"]]}]}


@pytest.fixture
def P():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u in ("ann", "mia", "lex"):
        p.registry.add_principal(Principal(u))
    p.call("admin", None, "governance.createProject", name="bank", base_uri="https://ex.org/bank")
    p.call("admin", "bank", "governance.bind", principal="ann", roles=["ontologist"])
    p.call("admin", "bank", "governance.bind", principal="mia", roles=["mapper"])
    p.call("admin", "bank", "governance.bind", principal="lex", roles=["lexicographer"])
    for c in ("Party", "Customer", "CorporateCustomer", "Account", "Holding"):
        p.call("ann", "bank", "owl.createClass", name=c, iri=NS + c)
    for name, kind, dom, rng in (
            ("customerName", "data", "Customer", "xsd:string"),
            ("registrationNumber", "data", "CorporateCustomer", "xsd:string"),
            ("balance", "data", "Account", "xsd:decimal"),
            ("accountNumber", "data", "Account", "xsd:string"),
            ("heldBy", "object", "Account", "Customer"),
            ("inAccount", "object", "Holding", "Account")):
        p.call("ann", "bank", "owl.createProperty", name=name, kind=kind, domain=dom, range=rng,
               iri=NS + name)
    p.call("mia", "bank", "mapping.registerDatabase", source_id="core", script=BANK)
    return p


def _q(P, query, who="ann", **kw):
    return P.call(who, "bank", "mapping.queryData", query=f"PREFIX : <{NS}> " + query, **kw)


def test_register_and_introspect(P):
    dbs = P.call("ann", "bank", "mapping.introspect")["databases"]
    assert dbs[0]["source"] == "core" and dbs[0]["in_memory"]
    s = {t["name"]: t for t in P.call("ann", "bank", "mapping.introspect",
                                      source_id="core")["tables"]}
    assert set(s) == {"customers", "corporate_customers", "accounts", "holdings"}
    assert s["accounts"]["primary_key"] == ["id"]
    assert s["accounts"]["foreign_keys"] == [{"columns": ["customer_id"],
                                              "ref_table": "customers", "ref_columns": ["id"]}]
    assert s["corporate_customers"]["foreign_keys"][0]["ref_columns"] == ["id"]
    assert {c["name"]: c["type"] for c in s["accounts"]["columns"]}["balance"] == "DECIMAL(12,2)"


def test_non_select_sql_is_rejected(P):
    for bad in ("DELETE FROM customers", "SELECT 1; DROP TABLE customers",
                "WITH x AS (SELECT 1) INSERT INTO customers VALUES (9,'x','y','z')",
                "PRAGMA table_info(customers)"):
        with pytest.raises(UnsafeSQL):
            check_select(bad)
    assert check_select("SELECT * FROM customers WHERE name = 'drop;'")
    bad_map = dict(CUSTOMER_MAP, id="Bad", logicalTable={"sqlQuery": "UPDATE customers SET x=1"})
    with pytest.raises(UnsafeSQL):
        P.call("ann", "bank", "mapping.addTriplesMap", map=bad_map)
    with pytest.raises(UnsafeSQL):
        P.call("ann", "bank", "mapping.addTriplesMap",
               map=dict(CUSTOMER_MAP, id="Bad2", logicalTable={"tableName": "x; DROP TABLE y"}))
    src = P.projects["bank"].databases["core"]
    with pytest.raises(UnsafeSQL):
        src.query("DELETE FROM customers")
    assert len(src.query("SELECT * FROM customers")[1]) == 4      # nothing was touched


def test_lexical_keys():
    assert key("LISTEDSECURITY") == key("ListedSecurity") == key("listedSecurity")
    assert key("listed_securities") == key("ListedSecurity") == key("listed security")
    assert key("corporate_customers") == key("CorporateCustomer")


def test_suggest_tables_fks_and_subclass_tables(P):
    props = P.call("ann", "bank", "mapping.suggest", source_id="core")
    by = lambda k: [x for x in props if x["kind"] == k]           # noqa: E731
    classes = {(x["table"], x["term"]) for x in by("class")}
    assert {("customers", NS + "Customer"), ("accounts", NS + "Account"),
            ("holdings", NS + "Holding"),
            ("corporate_customers", NS + "CorporateCustomer")} <= classes
    fk = {(x["table"], x["column"]): x for x in by("objectProperty")}
    assert fk[("accounts", "customer_id")]["term"] == NS + "heldBy"          # domain/range only
    assert fk[("holdings", "account_id")]["term"] == NS + "inAccount"
    assert any("domain = table class" in r for r in fk[("accounts", "customer_id")]["reasons"])
    sub = by("subclassTable")[0]
    assert sub["table"] == "corporate_customers" and sub["parent"] == "customers"
    assert sub["template"] == DATA + "customers/{customer_id}"
    assert by("subClassOf") == [dict(by("subClassOf")[0], sub=NS + "CorporateCustomer",
                                     sup=NS + "Customer")]
    disc = {x["value"]: x["term"] for x in by("discriminator")}
    assert disc == {"CORPORATE": NS + "CorporateCustomer"}
    dp = {}
    for x in sorted(by("datatypeProperty"), key=lambda x: x["score"]):   # best per column
        dp[(x["table"], x["column"])] = x["term"]
    assert dp[("customers", "name")] == NS + "customerName"
    assert dp[("accounts", "balance")] == NS + "balance"
    drafts = {x["table"]: x["map"] for x in by("triplesMap")}
    c = P.call("mia", "bank", "mapping.addTriplesMap", map=drafts["accounts"])
    assert c.status == "committed"                                  # suggestions apply cleanly
    assert P.call("ann", "bank", "mapping.validate")["summary"]["error"] == 0
    assert P.call("ann", "bank", "history.list")[-1]["operation"] == "mapping.addTriplesMap"


def test_add_remove_commit_stage_and_undo(P):
    lay = P.projects["bank"].layout
    c = P.call("mia", "bank", "mapping.addTriplesMap", map=CUSTOMER_MAP, source_id="core")
    assert c.status == "committed" and {q[3] for q in c.additions} == {lay.mappings}
    tm = URIRef("urn:sip:p:bank:r2rml#CustomerMap")
    assert (tm, RDF.type, RR.TriplesMap) in P.store.graph(lay.mappings)
    with pytest.raises(ValueError):
        P.call("mia", "bank", "mapping.addTriplesMap", map=CUSTOMER_MAP)
    P.registry.add_principal(Principal("kg@bank", is_machine=True, on_behalf_of="ann"))
    P.call("admin", "bank", "governance.bind", principal="kg@bank", roles=["agent-mapper"])
    s = P.call("kg@bank", "bank", "mapping.addTriplesMap", map=ACCOUNT_MAP)
    assert s.status == "staged"
    assert not list(P.store.graph(lay.mappings).triples(
        (URIRef("urn:sip:p:bank:r2rml#AccountMap"), None, None)))
    status = {m["id"]: m["status"] for m in P.call("ann", "bank", "mapping.list")["maps"]}
    assert status == {"CustomerMap": "committed", "AccountMap": "staged"}
    assert [m["id"] for m in P.call("ann", "bank", "mapping.list", staged=False)["maps"]] == \
        ["CustomerMap"]
    with pytest.raises(ValueError):                                 # parent of AccountMap
        P.call("mia", "bank", "mapping.removeTriplesMap", map_id="CustomerMap")
    P.call("admin", "bank", "validation.reject", commit=s.id)
    upd = dict(CUSTOMER_MAP, predicateObjects=[{"predicate": "customerName", "column": "name",
                                                "language": "en"}])
    u = P.call("mia", "bank", "mapping.updateTriplesMap", map=upd)
    assert len(u.additions) == 1 and len(u.removals) == 0
    assert P.call("mia", "bank", "mapping.list")["maps"][0]["source"] == "core"
    r = P.call("mia", "bank", "mapping.removeTriplesMap", map_id="CustomerMap")
    assert r.removals and not list(P.store.graph(lay.mappings))
    P.call("mia", "bank", "history.undo")
    assert (tm, RDF.type, RR.TriplesMap) in P.store.graph(lay.mappings)


def test_only_mapping_capable_roles_edit_maps(P):
    with pytest.raises(AuthorizationError):
        P.call("lex", "bank", "mapping.addTriplesMap", map=CUSTOMER_MAP)
    with pytest.raises(AuthorizationError):
        P.call("lex", "bank", "mapping.registerDatabase", source_id="x", script="SELECT 1;")
    assert P.call("lex", "bank", "mapping.list")["maps"] == []      # reading is R
    P.call("mia", "bank", "mapping.addTriplesMap", map=CUSTOMER_MAP)
    with pytest.raises(AuthorizationError):
        P.call("lex", "bank", "mapping.removeTriplesMap", map_id="CustomerMap")


def test_export_import_roundtrip(P):
    for m in (CUSTOMER_MAP, CORPORATE_MAP, ACCOUNT_MAP):
        P.call("mia", "bank", "mapping.addTriplesMap", map=m, source_id="core")
    ttl = P.call("ann", "bank", "mapping.export")
    g = Graph().parse(data=ttl, format="turtle")
    assert len(set(g.subjects(RDF.type, RR.TriplesMap))) == 3
    assert not any(str(o).startswith("urn:sip:p:bank:r2rml#CustomerMap/") for o in g.objects())
    before = P.call("ann", "bank", "mapping.list")["maps"]
    P.call("admin", None, "governance.createProject", name="bank2",
           base_uri="https://ex.org/bank")
    c = P.call("admin", "bank2", "mapping.import", data=ttl)
    assert c.status == "committed"
    after = P.call("admin", "bank2", "mapping.list")["maps"]
    strip = lambda ms: [{k: v for k, v in m.items() if k != "iri"} for m in ms]  # noqa: E731
    assert strip(after) == strip(before)
    assert P.call("admin", "bank2", "mapping.import", data=ttl) is None   # idempotent
    # an R2RML document in the PoC style: relative IRIs, blank nodes, quoted columns
    doc = f"""@prefix rr: <http://www.w3.org/ns/r2rml#> . @prefix : <{NS}> .
    <#RetailMap> a rr:TriplesMap ;
      rr:logicalTable [ rr:sqlQuery "SELECT \\"id\\", \\"name\\" FROM customers WHERE customer_type = 'RETAIL'" ] ;
      rr:subjectMap [ rr:template "{DATA}customer/{{\\"id\\"}}" ; rr:class :Customer ] ;
      rr:predicateObjectMap [ rr:predicate :customerName ; rr:objectMap [ rr:column "\\"name\\"" ] ] ."""
    P.call("mia", "bank", "mapping.import", data=doc, source_id="core")
    prev = P.call("ann", "bank", "mapping.preview", map_id="RetailMap")
    names = sorted(t["o"] for t in prev["triples"] if t["p"] == NS + "customerName")
    assert names == ["Ada", "Bob"]


def test_validate_catches_mapping_errors(P):
    bad = {"id": "BadMap", "table": "accounts",
           "subject": {"template": DATA + "account", "classes": ["Acount"]},
           "predicateObjects": [
               {"predicate": "heldBy", "column": "customer_id"},            # object prop + literal
               {"predicate": "balance", "template": DATA + "b/{balance}"},  # data prop + IRI
               {"predicate": "accountNumber", "column": "acct_no"},         # unknown column
               {"predicate": "registrationNumber", "column": "balance",
                "datatype": "xsd:date"},                                    # decimal -> date
               {"predicate": "nosuchProp", "column": "id"}]}
    P.call("mia", "bank", "mapping.addTriplesMap", map=bad)
    P.call("mia", "bank", "mapping.addTriplesMap", map={
        "id": "BadPlaceholder", "table": "accounts",
        "subject": {"template": DATA + "account/{acc_id}", "classes": ["Account"]}})
    r = P.call("ann", "bank", "mapping.validate")
    codes = {(f["code"], f["map"].split("#")[-1] if f["map"] else None) for f in r["findings"]}
    assert {("unknown-class", "BadMap"), ("property-kind", "BadMap"),
            ("unknown-column", "BadMap"), ("no-placeholder", "BadMap"),
            ("datatype-mismatch", "BadMap"), ("unknown-property", "BadMap"),
            ("unknown-placeholder", "BadPlaceholder")} <= codes
    kinds = [f["message"] for f in r["findings"] if f["code"] == "property-kind"]
    assert len(kinds) == 2
    assert r["summary"]["error"] >= 5
    assert NS + "Holding" in r["coverage"]["classes"]["unmapped"]


def test_preview_with_provenance(P):
    for m in (CUSTOMER_MAP, ACCOUNT_MAP):
        P.call("mia", "bank", "mapping.addTriplesMap", map=m)
    prev = P.call("ann", "bank", "mapping.preview", map_id="AccountMap", limit=2)
    assert prev["rows"] == {"urn:sip:p:bank:r2rml#AccountMap": 2}
    held = [t for t in prev["triples"] if t["p"] == NS + "heldBy"]
    assert {(t["s"], t["o"]) for t in held} == {(DATA + "account/10", DATA + "customer/1"),
                                                (DATA + "account/11", DATA + "customer/2")}
    assert all(t["maps"] == ["urn:sip:p:bank:r2rml#AccountMap"] for t in prev["triples"])
    bal = next(t for t in prev["triples"] if t["p"] == NS + "balance")
    assert bal["o"] in ("100.5", "2000")
    by_term = P.call("ann", "bank", "mapping.preview", term="customerName")
    assert {t["maps"][0].split("#")[1] for t in by_term["triples"]} == {"CustomerMap"}


def test_query_data_follows_ontology_edits(P):
    """FR-VKG-02: editing the ontology changes answers over the mapped data, no re-mapping."""
    P.call("mia", "bank", "mapping.addTriplesMap", map=CORPORATE_MAP)
    q = "SELECT ?x WHERE { ?x a :Customer } ORDER BY ?x"
    assert _q(P, q)["rows"] == []
    P.call("ann", "bank", "owl.addAxiom", subject="CorporateCustomer", kind="SubClassOf",
           expression="Customer")
    rows = _q(P, q)["rows"]
    assert [r["x"] for r in rows] == [DATA + "customer/2", DATA + "customer/4"]
    # a machine proposal is visible in the staged view only
    P.registry.add_principal(Principal("mod@bank", is_machine=True, on_behalf_of="ann"))
    P.call("admin", "bank", "governance.bind", principal="mod@bank",
           roles=["agent-ontology-copilot"])
    c = P.call("mod@bank", "bank", "owl.addAxiom", subject="Customer", kind="SubClassOf",
               expression="Party")
    assert c.status == "staged"
    qp = "SELECT (COUNT(?x) AS ?n) WHERE { ?x a :Party }"
    assert _q(P, qp)["rows"] == [{"n": "2"}]
    assert _q(P, qp, staged=False)["rows"] == [{"n": "0"}]
    assert _q(P, qp, entailment="none")["rows"] == [{"n": "0"}]
    assert _q(P, qp, entailment="owlrl")["rows"] == [{"n": "2"}]
    # subproperties and joins through the virtual graph
    for m in (CUSTOMER_MAP, ACCOUNT_MAP):
        P.call("mia", "bank", "mapping.addTriplesMap", map=m)
    r = _q(P, "SELECT ?n ?b WHERE { ?a :heldBy ?c . ?c a :CorporateCustomer ; "
              ":customerName ?n . ?a :balance ?b } ORDER BY ?n")
    assert [x["n"] for x in r["rows"]] == ["Acme Ltd", "Globex"]
    assert r["mapped_triples"] > 0 and r["engine"] == "local"
    with pytest.raises(ValueError):
        _q(P, q, engine="ontop")                 # optional engine: off without an endpoint


def test_impact_and_rename_keep_mappings_consistent(P):
    for m in (CUSTOMER_MAP, CORPORATE_MAP, ACCOUNT_MAP):
        P.call("mia", "bank", "mapping.addTriplesMap", map=m)
    imp = P.call("ann", "bank", "mapping.impact", entities=["CorporateCustomer", "customerName"])
    assert {(a["id"], u["where"]) for a in imp["affected"] for u in a["uses"]} == {
        ("CorporateMap", "rr:class"), ("CustomerMap", "rr:predicate")}
    c = P.call("ann", "bank", "refactor.renameIRI", old="CorporateCustomer",
               new="BusinessCustomer")
    lay = P.projects["bank"].layout
    assert {q[3] for q in c.additions} == {lay.main, lay.mappings}
    corp = next(m for m in P.call("ann", "bank", "mapping.list")["maps"]
                if m["id"] == "CorporateMap")
    assert corp["subject"]["classes"] == [NS + "BusinessCustomer"]
    assert P.call("ann", "bank", "mapping.validate")["summary"]["error"] == 0
    P.call("ann", "bank", "history.undo")                    # one commit, one undo
    corp = next(m for m in P.call("ann", "bank", "mapping.list")["maps"]
                if m["id"] == "CorporateMap")
    assert corp["subject"]["classes"] == [NS + "CorporateCustomer"]
    # deleting an entity leaves the maps alone, and validation + impact report it
    P.call("ann", "bank", "refactor.deleteEntity", entity="customerName")
    findings = P.call("ann", "bank", "mapping.validate")["findings"]
    assert [f["code"] for f in findings if f["severity"] == "error"] == ["unknown-property"]
    assert P.call("ann", "bank", "mapping.impact",
                  entities=["customerName"])["affected"][0]["id"] == "CustomerMap"


def test_r2rml_model_roundtrip_and_file_sources(tmp_path):
    tm = TriplesMap.from_dict(ACCOUNT_MAP, mint=lambda i: "urn:m#" + i,
                              resolve=lambda x: NS + x)
    g = Graph()
    for t in tm.triples():
        g.add(t)
    back = parse_maps(g)
    assert [b.as_dict() for b in back] == [tm.as_dict()]
    assert back[0].poms[0].object.datatype == str(XSD.decimal)
    import sqlite3
    f = tmp_path / "bank db.sqlite"
    con = sqlite3.connect(f)
    con.executescript(BANK)
    con.close()
    src = RelationalSource("file", path=str(f))
    assert len(src.query("SELECT * FROM holdings", limit=2)[1]) == 2
    with pytest.raises(sqlite3.OperationalError):              # opened read-only
        src.connect().execute("DELETE FROM holdings")
    src.close()
