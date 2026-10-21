"""Offline tests for the ontology-visualization PoC (no network, no live models).

Run from the PoC folder:  python -m pytest tests -q
"""

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ontoviz import _paths, demo  # noqa: E402
from ontoviz.index import DEFAULT_KINDS, OntologyIndex  # noqa: E402
from ontoviz.neighbourhood import neighbourhood  # noqa: E402
from ontoviz.svg import render_svg  # noqa: E402
from semantic_intelligence.core.principal import Principal  # noqa: E402
from semantic_intelligence.governance.registry import AuthorizationError  # noqa: E402
from semantic_intelligence.platform import OPERATIONS, describe_operations  # noqa: E402

F = demo.FLEET_NS


@pytest.fixture(scope="module")
def P():
    return demo.build()


def view(P, seed, **kw):
    return P.call("val", "fleet", "viz.neighbourhood", seed=seed, **kw)


def ents(v):
    return {e["id"]: e for e in v["entityTypes"]}


def rels(v):
    return {(r["from"].split("#")[-1], r["kind"], r["to"].split("#")[-1]): r
            for r in v["relationships"]}


def fleet_index():
    g = Graph().parse(data=demo.FLEET, format="turtle")
    return OntologyIndex(g)


# --------------------------------------------------------------------------- index
def test_restrictions_become_tagged_edges_and_complex_axioms_badges():
    ix = fleet_index()
    e = {(x.source.split("#")[-1], x.kind, x.tag, x.target.split("#")[-1]): x
         for x in ix.edges.values()}
    assert ("Vehicle", "restriction", "some", "Wheel") in e
    assert ("Vehicle", "restriction", "min 1", "Manufacturer") in e       # qualified card
    assert ("Vehicle", "objectProperty", "", "Manufacturer") in e         # domain -> range
    assert ("Car", "disjointWith", "", "Truck") in e
    assert ("Automobile", "equivalentClass", "", "Car") in e
    # a union filler is drawn as one edge per member, marked via "or"
    assert e[("FleetVehicle", "restriction", "some", "Company")].via == "or"
    # a definition's conjuncts are necessary conditions, drawn via "≡"
    assert e[("HybridCar", "subClassOf", "", "Car")].via == "≡"
    assert ix.nodes[F + "HybridCar"].defined
    # data restrictions are attributes; complements and union equivalences are badges
    assert "'has VIN' exactly 1" in ix.nodes[F + "Vehicle"].attributes
    assert any("not bicycle" in c for c in ix.nodes[F + "FleetVehicle"].complex)
    assert any(c.startswith("EquivalentTo:") for c in ix.nodes[F + "MotorVehicle"].complex)
    assert ix.nodes[F + "Battery"].label == "Battery"                     # local-name fallback


def test_min_zero_restrictions_are_optional_edges_off_by_default():
    g = Graph().parse(data=demo.FLEET + """
        @prefix : <https://ex.org/fleet#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        :Truck rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :hasPart ;
            owl:minQualifiedCardinality "0"^^xsd:nonNegativeInteger ; owl:onClass :Battery ] .
        """, format="turtle")
    ix = OntologyIndex(g)
    opt = [x for x in ix.edges.values() if x.kind == "optional"]
    assert len(opt) == 1 and opt[0].tag == "min 0" and "optional" not in DEFAULT_KINDS
    v = neighbourhood(ix, F + "Truck", hops=1)
    assert all(x.kind != "optional" for x in v.edges)
    v = neighbourhood(ix, F + "Truck", hops=1, kinds=DEFAULT_KINDS + ("optional",))
    assert any(x.kind == "optional" for x in v.edges)


# --------------------------------------------------------------------------- neighbourhood
def star(n_children=50):
    ttl = ["@prefix : <urn:x#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
           ":Seed rdfs:subClassOf :Hub . :Hub rdfs:subClassOf :Top . :Leaf rdfs:subClassOf :Seed ."]
    ttl += [f":C{i} rdfs:subClassOf :Hub ." for i in range(n_children)]
    return OntologyIndex(Graph().parse(data="\n".join(ttl), format="turtle"))


def test_cap_connectivity_and_hub_guard():
    ix = star()
    v = neighbourhood(ix, "urn:x#Seed", hops=3, cap=10, hub_limit=25)
    assert len(v.nodes) <= 10
    # connected: every node reaches the seed through view edges
    adj = {}
    for e in v.edges:
        adj.setdefault(e.source, set()).add(e.target)
        adj.setdefault(e.target, set()).add(e.source)
    seen, todo = {"urn:x#Seed"}, ["urn:x#Seed"]
    while todo:
        for m in adj.get(todo.pop(), ()):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    assert seen == set(v.nodes)
    # the hub is shown but guarded: its 50 children are held back
    assert "urn:x#Hub" in v.guarded and v.hidden["urn:x#Hub"] >= 49
    assert not any(n.startswith("urn:x#C") for n in v.nodes)
    # confirming the expansion lifts the guard (still under the cap)
    v2 = neighbourhood(ix, "urn:x#Seed", hops=3, cap=30, hub_limit=25, expand=["urn:x#Hub"])
    assert "urn:x#Hub" not in v2.guarded and len(v2.nodes) == 30
    children = sum(n.startswith("urn:x#C") for n in v2.nodes)
    assert children >= 26
    assert v2.truncated == v2.candidates - 30


def test_doi_prefers_close_hierarchy_and_is_deterministic():
    ix = fleet_index()
    a = neighbourhood(ix, F + "ElectricCar", hops=3, cap=6)
    b = neighbourhood(ix, F + "ElectricCar", hops=3, cap=6)
    assert list(a.nodes) == list(b.nodes) and [e.key for e in a.edges] == [e.key for e in b.edges]
    order = list(a.nodes)
    assert order[0] == F + "ElectricCar" and F + "Car" in order[:3]       # superclass first
    assert a.nodes[F + "Car"]["dist"] == 1


def test_operation_arguments_are_validated(P):
    with pytest.raises(ValueError):
        view(P, "Vehicle", cap=0)
    with pytest.raises(ValueError):
        view(P, "Vehicle", kinds=["partOf"])
    with pytest.raises(ValueError):
        view(P, "Vehicle", overlays=["heatmap"])
    with pytest.raises(KeyError):
        view(P, "NoSuchClass")


# --------------------------------------------------------------------------- overlays
def test_staged_overlay_matches_real_staged_commits():
    p = demo.build()
    v = view(p, "Vehicle")
    e, r = ents(v), rels(v)
    assert e[F + "Scooter"]["sip"]["state"] == "staged_add"
    assert r[("Scooter", "subClassOf", "Vehicle")]["sip"]["state"] == "staged_add"
    assert r[("Bicycle", "subClassOf", "Vehicle")]["sip"]["state"] == "staged_del"
    assert r[("Truck", "restriction", "Engine")]["sip"]["state"] == "staged_add"
    truck = e[F + "Truck"]["sip"]
    assert truck["state"] == "modified"
    assert truck["commits"][0]["principal"] == "modeler@fleet" and truck["commits"][0]["machine"]
    assert v["sip"]["summary"]["pendingCommits"] == 3
    for c in p.call("val", "fleet", "validation.pending"):
        p.call("val", "fleet", "validation.accept", commit=c["id"])
    v = view(p, "Vehicle")
    r = rels(v)
    assert ("Bicycle", "subClassOf", "Vehicle") not in r
    assert r[("Scooter", "subClassOf", "Vehicle")]["sip"]["state"] == "asserted"
    assert all(x["sip"]["state"] == "asserted" for x in v["entityTypes"])


def test_inferred_edges_are_new_direct_superclasses_only(P):
    r = rels(view(P, "MotorVehicle", hops=1))
    assert r[("Car", "subClassOf", "MotorVehicle")]["sip"]["inferred"]
    assert r[("Truck", "subClassOf", "MotorVehicle")]["sip"]["inferred"]
    r = rels(view(P, "Vehicle", hops=2, cap=60))
    inferred = {k for k, x in r.items() if x["sip"]["inferred"]}
    # entailed but already visible through an asserted edge or an equivalence: not drawn
    assert ("ElectricCar", "subClassOf", "Automobile") not in inferred
    assert ("Automobile", "subClassOf", "Vehicle") not in inferred
    assert ("ElectricCar", "subClassOf", "Vehicle") not in inferred
    v = view(P, "MotorVehicle", hops=1, overlays=["staged"])
    assert not any(x["sip"]["inferred"] for x in v["relationships"])      # overlay off


def test_unsatisfiable_and_findings(P):
    e = ents(view(P, "Car", hops=1))
    assert e[F + "AmphibiousTruckCar"]["sip"]["unsatisfiable"]
    b = ents(view(P, "Part", hops=1))[F + "Battery"]["sip"]
    assert b["findingCount"] >= 1 and b["worstSeverity"] in ("blocker", "major")
    assert any("label" in f["message"] for f in b["findings"])


def test_cq_coverage_including_the_effect_of_staged_commits(P):
    v = view(P, "Truck", hops=1)
    t = ents(v)[F + "Truck"]["sip"]["cq"]
    assert "cq_Truck_Engine" in t["fail"] and "cq_Truck_Engine" in t["fixedByStaged"]
    assert {q["id"] for q in v["sip"]["cqs"]} >= {"cq_Truck_Engine"}
    assert "cq_Vehicle_Wheel" in ents(view(P, "Vehicle", hops=1))[F + "Vehicle"]["sip"]["cq"]["pass"]


def test_individuals_paged_and_by_subclass(P):
    r = P.call("val", "fleet", "viz.individuals", cls="Manufacturer")
    assert r["total"] == 2 and {i["label"] for i in r["items"]} == {"Tesla", "Volvo"}
    r = P.call("val", "fleet", "viz.individuals", cls="Vehicle", include_subclasses=True,
               limit=1)
    assert r["total"] == 2 and len(r["items"]) == 1                       # car1, truck7
    assert ents(view(P, "Truck", hops=0))[F + "Truck"]["sip"]["instances"] == 1


# --------------------------------------------------------------------------- governance
def test_viz_operations_go_through_the_pdp(P):
    for name in ("viz.neighbourhood", "viz.search", "viz.individuals", "viz.exportSVG",
                 "viz.stats"):
        spec = OPERATIONS[name]
        assert spec.crudv == "R" and spec.capability.startswith("rdf") and not spec.writes
    assert {"viz.neighbourhood", "viz.search"} <= {o["name"] for o in describe_operations()}
    if "outsider" not in P.registry.principals:
        P.registry.add_principal(Principal("outsider"))
    with pytest.raises(AuthorizationError):
        P.call("outsider", "fleet", "viz.neighbourhood", seed="Vehicle")


# --------------------------------------------------------------------------- contract, svg, http
def _playground_model():
    path = (_paths.REPO / "capabilities" / "ontology_modeler" / "ontology_modeler" /
            "playground" / "model.py")
    spec = importlib.util.spec_from_file_location("pg_model", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pg_model"] = mod          # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_payload_is_a_playground_ontology_superset(P):
    try:
        pg = _playground_model()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Playground model not importable: {exc}")
    v = view(P, "Vehicle")
    o = pg.Ontology.from_dict(json.loads(json.dumps(v)))
    assert {e.id for e in o.entityTypes} == {e["id"] for e in v["entityTypes"]}
    assert {r.kind for r in o.relationships} >= {"subClassOf", "objectProperty"}
    assert all(e["kind"] in pg.NODE_KINDS for e in v["entityTypes"])


def test_svg_is_wellformed_and_deterministic(P):
    a = P.call("val", "fleet", "viz.exportSVG", seed="Vehicle", hops=1)
    b = P.call("val", "fleet", "viz.exportSVG", seed="Vehicle", hops=1)
    assert a == b
    root = ET.fromstring(a)
    assert root.tag.endswith("svg") and root.get("role") == "img"
    assert "+ scooter" in a and "− " in a                            # not colour alone
    assert render_svg(view(P, "Vehicle", hops=1)) == render_svg(view(P, "Vehicle", hops=1))


def test_http_route_and_static_viewer(P):
    from fastapi.testclient import TestClient
    from ontoviz.server import make_app
    c = TestClient(make_app(platform=P))
    h = {"X-SIP-Principal": "val"}
    hits = c.post("/projects/fleet/ops/viz.search", json={"text": "car"}, headers=h).json()
    assert {x["label"] for x in hits} >= {"car", "electric car"}
    v = c.post("/projects/fleet/ops/viz.neighbourhood", json={"seed": "Vehicle"}, headers=h)
    assert v.status_code == 200 and v.json()["sip"]["seed"] == F + "Vehicle"
    assert c.post("/projects/fleet/ops/viz.neighbourhood", json={"seed": "Vehicle"},
                  headers={"X-SIP-Principal": "nobody"}).status_code == 401
    assert c.post("/projects/fleet/ops/viz.neighbourhood", json={"seed": "Vehicle", "cap": 0},
                  headers=h).status_code == 422
    assert "Cytoscape" in c.get("/viz").text or "cytoscape" in c.get("/viz").text
    assert c.get("/viz/static/vendor/cytoscape.min.js").status_code == 200


# --------------------------------------------------------------------------- FIBO
@pytest.fixture(scope="module")
def fibo_index():
    if not (_paths.FIBO.exists() or (_paths.DATA / "fibo.nt").exists()):
        pytest.skip("FIBO corpus not present")
    return OntologyIndex(Graph().parse(data=demo.fibo_ntriples(), format="nt"))


def test_fibo_scale_view(fibo_index):
    ix = fibo_index
    s = ix.stats()
    assert s["nodes"] > 3000 and s["edges_by_kind"]["restriction"] > 1500
    assert s["edges_by_kind"]["optional"] > 0
    loan = "https://spec.edmcouncil.org/fibo/ontology/LOAN/LoansGeneral/Loans/Loan"
    v = neighbourhood(ix, loan, hops=2, cap=40, hub_limit=25)
    assert len(v.nodes) == 40 and v.truncated > 0 and v.guarded
    assert any(e.kind == "restriction" and e.source == loan for e in v.edges)
    assert v.ms < 250
