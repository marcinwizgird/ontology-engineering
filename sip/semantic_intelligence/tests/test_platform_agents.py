"""Platform facade, agents, orchestrator, API — the cross-cutting guarantees."""

import pytest
from fastapi.testclient import TestClient

from semantic_intelligence.agents.base import AgentRuntime, Proposal
from semantic_intelligence.agents.llm import SimulatedModel
from semantic_intelligence.agents.orchestrator import Conductor
from semantic_intelligence.agents.simulators import simulated_model
from semantic_intelligence.agents.specialists import ExtractionAgent, ModelingCopilot
from semantic_intelligence.api.app import create_app
from semantic_intelligence.core.principal import Principal
from semantic_intelligence.governance.registry import AuthorizationError
from semantic_intelligence.platform import OPERATIONS, STAGES, Platform


@pytest.fixture
def P():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u in ("pat", "ann", "val"):
        p.registry.add_principal(Principal(u))
    p.call("admin", None, "governance.createProject", name="t", base_uri="https://ex.org/t",
           languages=["en", "fr"])
    p.call("admin", "t", "governance.bind", principal="pat", roles=["projectmanager"])
    p.call("admin", "t", "governance.bind", principal="ann", roles=["ontologist"])
    p.call("admin", "t", "governance.bind", principal="val", roles=["validator"])
    return p


def test_every_operation_is_guarded_and_staged():
    """QR-SEC-01: an operation without a capability fails the build."""
    assert len(OPERATIONS) >= 60
    for o in OPERATIONS.values():
        assert o.capability and o.crudv and set(o.crudv) <= set("CRUDV"), o.name
        assert o.stage in STAGES, o.name
    covered = {o.stage for o in OPERATIONS.values()}
    assert covered >= {"scope", "acquire", "model", "validate", "review", "populate", "reason",
                       "publish", "consume"}


def test_authoring_flow_and_validator_roles(P):
    P.call("ann", "t", "owl.createClass", name="Vehicle")
    P.call("ann", "t", "owl.createClass", name="Car", parent="Vehicle")
    P.call("ann", "t", "owl.createProperty", name="hasPart", label="has part")
    c = P.call("ann", "t", "owl.addAxiom", subject="Car", kind="SubClassOf",
               expression="'has part' some Vehicle")
    assert c.status == "committed"
    with pytest.raises(AuthorizationError):
        P.call("val", "t", "owl.createClass", name="Bus")          # validators do not edit
    with pytest.raises(AuthorizationError):
        P.call("ann", "t", "validation.accept", commit=c.id)       # ontologist lacks rdf V
    r = P.call("ann", "t", "owl.removeAxiom", subject="Car", kind="SubClassOf",
               expression="'has part' some Vehicle")
    assert len(r.removals) == 4
    with pytest.raises(ValueError):
        P.call("ann", "t", "owl.removeAxiom", subject="Car", kind="SubClassOf",
               expression="'has part' some Vehicle")
    assert P.call("ann", "t", "owl.checkExpression", expression="hasPart sme X")["ok"] is False


def test_sparql_update_goes_through_history(P):
    P.call("ann", "t", "owl.createClass", name="A")
    P.call("admin", "t", "governance.bind", principal="ann", roles=["rdfgeek"])
    c = P.call("ann", "t", "sparql.update", update=(
        "PREFIX owl: <http://www.w3.org/2002/07/owl#> "
        "INSERT DATA { <https://ex.org/t#B> a owl:Class }"))
    assert c.operation == "sparql.update" and len(c.additions) == 1
    hist = P.call("ann", "t", "history.list", operation_name="sparql.update")
    assert hist and hist[0]["added"] == 1


def test_machine_proposals_need_a_human_validator(P):
    P.registry.add_principal(Principal("bot", is_machine=True, on_behalf_of="pat"))
    P.call("pat", "t", "governance.bind", principal="bot", roles=["agent-ontology-copilot"])
    c = P.call("bot", "t", "owl.createClass", name="Truck")
    assert c.status == "staged"
    assert P.call("ann", "t", "browse.classTree", staged=False) == []
    assert [n["show"] for n in P.call("ann", "t", "browse.classTree", staged=True)] == ["Truck"]
    with pytest.raises(AuthorizationError):
        P.call("bot", "t", "validation.accept", commit=c.id)
    with pytest.raises(AuthorizationError):
        P.call("bot", "t", "lifecycle.setStage", stage="review", state="done")
    assert P.call("val", "t", "validation.accept", commit=c.id)["status"] == "accepted"


def test_critic_rejects_ungrounded_extraction(P):
    model = SimulatedModel()
    model.register("extraction.candidates", lambda prompt, schema: {
        "classes": [{"name": "Rocket", "quote": "rockets fly"}],   # not in the source
        "subclasses": [], "properties": []})
    rt = AgentRuntime(P, model)
    P.registry.add_principal(Principal("ex@t", is_machine=True, on_behalf_of="pat"))
    P.call("pat", "t", "governance.bind", principal="ex@t", roles=["agent-ontology-copilot"])
    P.call("pat", "t", "acquire.registerSource", source_id="d", kind="document",
           content="Cars are vehicles.")
    run = ExtractionAgent(rt, P.registry.principal("ex@t")).run("t", "d")
    assert run.proposals[0].critic and run.proposals[0].commit is None
    assert P.call("val", "t", "validation.pending") == []


def test_modeling_critic_rejects_unsatisfiable_proposal(P):
    for n in ("Animal", "Plant", "Triffid"):
        P.call("ann", "t", "owl.createClass", name=n)
    P.call("ann", "t", "owl.addAxiom", subject="Animal", kind="DisjointWith", expression="Plant")
    P.call("ann", "t", "owl.addAxiom", subject="Triffid", kind="SubClassOf", expression="Animal")
    model = SimulatedModel()
    model.register("modeling.axioms", lambda p, s: {"axioms": [
        {"kind": "SubClassOf", "expression": "Plant", "rationale": "bad", "quote": "",
         "confidence": 0.9}]})
    P.registry.add_principal(Principal("mod@t", is_machine=True, on_behalf_of="pat"))
    P.call("pat", "t", "governance.bind", principal="mod@t", roles=["agent-ontology-copilot"])
    run = ModelingCopilot(AgentRuntime(P, model), P.registry.principal("mod@t")).run("t", "Triffid")
    assert any("unsatisfiable" in c for c in run.proposals[0].critic)


def test_ai_policy_degrades_and_kill_switch(P):
    C = Conductor(P, simulated_model())
    C.enable_agents("t", "pat")
    P.projects["t"].config.ai_policy.llm_allowed = False
    run = C.agent("t", "requirements").run("t", "Every vehicle has one or more wheels.")
    assert run.status == "degraded" and not run.proposals
    assert C.runtime.policy_log[-1]["allowed"] is False
    P.projects["t"].config.ai_policy.llm_allowed = True
    agent = C.agent("t", "requirements")
    r = agent.start("t")
    C.runtime.stop(r.id)
    with pytest.raises(Exception, match=r.id):
        agent.ask(r, "requirements.cqs", "{}", {})


def test_enable_agents_requires_rbac(P):
    C = Conductor(P, simulated_model())
    with pytest.raises(AuthorizationError):
        C.enable_agents("t", "ann")                                # ontologist lacks rbac C
    ids = C.enable_agents("t", "pat")
    assert len(ids) == 9 and all(P.registry.principal(i).on_behalf_of == "pat" for i in ids)


def test_end_to_end_demo():
    from semantic_intelligence.demo import run
    r = run(verbose=False)
    P = r["platform"]
    assert r["accepted"] >= 20 and r["rejected"] == 0
    # the CQ the sources cannot satisfy is what keeps the release gate shut
    assert r["gate"]["passed"] is False
    assert r["gate"]["reasons"] == ["competency questions failing: cq_Manufacturer_Country"]
    assert "Scania" in r["qa"][0]["answer"] and r["qa"][0]["grounded"]
    assert any(v.endswith("/m3") for v in r["qa"][0]["cited_values"])
    frame = P.call("pat", "fleet", "browse.classFrame", cls="Vehicle")["SubClass Of"]
    assert any("some wheel" in row["text"] for row in frame)
    hist = P.call("pat", "fleet", "history.list")
    assert any(h["operation"] == "kg.assertSameAs" for h in hist)
    agents = {h["principal"] for h in hist if h["machine"]}
    assert {"extraction@fleet", "modeling@fleet", "kg-builder@fleet"} <= agents
    metrics = r["conductor"].runtime.metrics("fleet")
    assert metrics["extraction"]["acceptance_rate"] == 1.0


def test_api(P):
    client = TestClient(create_app(P))
    assert client.get("/health").json()["operations"] == len(OPERATIONS)
    h = {"X-SIP-Principal": "ann"}
    r = client.post("/projects/t/ops/owl.createClass", json={"name": "Thing2"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "committed"
    assert client.post("/projects/t/ops/owl.createClass", json={"name": "X"},
                       headers={"X-SIP-Principal": "val"}).status_code == 403
    assert client.post("/projects/t/ops/nope", json={}, headers=h).status_code == 404
    assert client.get("/operations").json()[0]["name"]
    assert client.post("/projects/t/agents/enable", headers={"X-SIP-Principal": "pat"}).status_code == 200


def test_thesaurus_project_and_per_fix_capabilities():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    p.call("admin", None, "governance.createProject", name="th", base_uri="https://ex.org/th",
           model="skos", lexicalization="skos", languages=["en"])
    for u, r in (("terry", "thesaurus-editor"), ("lou", "lurker"), ("pm", "projectmanager")):
        p.registry.add_principal(Principal(u))
        p.call("admin", "th", "governance.bind", principal=u, roles=[r])
    p.call("terry", "th", "skos.createConceptScheme", label="S", iri="https://ex.org/th#S")
    p.call("terry", "th", "skos.createConcept", label="animal", schemes=["S"],
           iri="https://ex.org/th#animal")
    p.call("terry", "th", "skos.createConcept", label="dog", schemes=["S"], broader="animal",
           iri="https://ex.org/th#dog")
    p.call("terry", "th", "skos.removeBroader", concept="dog", broader="animal")
    checks = {f["check"] for f in p.call("terry", "th", "quality.runChecks")["findings"]}
    assert "listDanglingConcepts" in checks
    with pytest.raises(AuthorizationError):        # lurker: rdf R only
        p.call("lou", "th", "quality.applyFix", check="listDanglingConcepts")
    c = p.call("terry", "th", "quality.applyFix", check="listDanglingConcepts")
    assert c and c.operation == "icv.setAllDanglingAsTopConcept"
    tops = [n["iri"] for n in p.call("terry", "th", "skos.topConcepts", schemes=["S"])]
    assert "https://ex.org/th#dog" in tops
    with pytest.raises(AuthorizationError):        # thesaurus editors do not author OWL classes
        p.call("terry", "th", "owl.createClass", name="Dog")
    # quality agent: its fix proposals go through the same per-fix capability, staged
    C = Conductor(p, simulated_model())
    C.enable_agents("th", "pm")
    p.call("terry", "th", "skos.createConcept", label="cat ", schemes=["S"],
           iri="https://ex.org/th#cat", broader="animal")
    run = C.agent("th", "quality").run("th")
    fixes = [x for x in run.proposals if x.operation == "quality.applyFix"]
    assert fixes and all(x.commit for x in fixes), [x.error for x in fixes]
    assert all(c["machine"] for c in p.call("pm", "th", "validation.pending"))


def test_quality_agent_explains_and_repairs_unsatisfiable_class(P):
    """Scenario S4: a human makes Triffid unsatisfiable; the quality agent justifies it
    and proposes removing the class's own conflicting assertion — staged, with evidence."""
    for n in ("Animal", "Plant", "Triffid"):
        P.call("ann", "t", "owl.createClass", name=n)
    P.call("ann", "t", "owl.addAxiom", subject="Animal", kind="DisjointWith", expression="Plant")
    P.call("ann", "t", "owl.addAxiom", subject="Triffid", kind="SubClassOf", expression="Animal")
    P.call("ann", "t", "owl.addAxiom", subject="Triffid", kind="SubClassOf", expression="Plant")
    C = Conductor(P, simulated_model())
    C.enable_agents("t", "pat")
    run = C.agent("t", "quality").run("t")
    assert run.output["unsatisfiable"] == ["Triffid"]
    repairs = [x for x in run.proposals if x.operation == "owl.removeAxiom"]
    assert len(repairs) == 1 and repairs[0].commit and not repairs[0].critic
    assert repairs[0].arguments["subject"] == "Triffid"
    assert repairs[0].evidence["justifications"]
    P.call("val", "t", "validation.accept", commit=repairs[0].commit)
    after = P.call("ann", "t", "reasoning.classify")
    assert after["unsatisfiable"] == [] and after["consistent"]
