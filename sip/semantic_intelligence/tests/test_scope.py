"""Stage 1 (scope): the ORSD, reuse candidates, pre-glossary, exit criteria, prioritised
competency questions, project templates and the RequirementsAgent."""

import pytest
from rdflib.namespace import RDF

from semantic_intelligence.agents.base import AgentRuntime
from semantic_intelligence.agents.llm import SimulatedModel
from semantic_intelligence.agents.orchestrator import Conductor
from semantic_intelligence.agents.simulators import simulated_model
from semantic_intelligence.agents.specialists import RequirementsAgent
from semantic_intelligence.core.namespaces import SIP, VOID
from semantic_intelligence.core.principal import Principal
from semantic_intelligence.governance.registry import AuthorizationError
from semantic_intelligence.platform import Platform

BRIEF = ("The fleet team needs an ontology of vehicles and their parts. "
         "Every vehicle has one or more wheels. "
         "We need to know which manufacturers exist. "
         "Labels must be available in English and French. "
         "Manufacturers should be aligned with schema.org.")


@pytest.fixture
def P():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u in ("pat", "ann", "val", "lex"):
        p.registry.add_principal(Principal(u))
    p.call("admin", None, "governance.createProject", name="t", base_uri="https://ex.org/t")
    for u, r in (("pat", "projectmanager"), ("ann", "ontologist"), ("val", "validator"),
                 ("lex", "lexicographer")):
        p.call("admin", "t", "governance.bind", principal=u, roles=[r])
    return p


def _ready(P, **kw):
    return P.call("val", "t", "scope.readiness", **kw)


def test_specification_fields_replace_and_are_guarded(P):
    P.call("ann", "t", "scope.setSpecification", purpose="Answer fleet questions",
           intended_users=["fleet team", "analysts"])
    P.call("pat", "t", "scope.setSpecification", intended_users=["fleet team"])
    spec = P.call("val", "t", "scope.specification")["specification"]
    assert spec["purpose"] == "Answer fleet questions"          # kept: not given
    assert spec["intended_users"] == ["fleet team"]             # replaced
    assert spec["implementation_language"] == "OWL 2"           # from the project model
    for who in ("val", "lex"):                                   # no rdf(ontology) U
        with pytest.raises(AuthorizationError):
            P.call(who, "t", "scope.setSpecification", purpose="x")
    with pytest.raises(ValueError):
        P.call("ann", "t", "scope.setSpecification")
    meta = P.store.graph(P.projects["t"].layout.metadata)
    assert (None, RDF.type, SIP.RequirementsSpecification) in meta
    assert P.call("ann", "t", "history.list", operation_name="scope.setSpecification")


def test_exit_criteria(P):
    r = _ready(P)
    assert not r["ready"] and len(r["missing"]) == 5           # SCP-01..05
    P.call("ann", "t", "scope.setSpecification", purpose="p", scope="vehicles",
           intended_users=["fleet team"], intended_uses=["find manufacturers"])
    P.call("ann", "t", "quality.addCompetencyQuestion", id="cq1",
           question="Which manufacturers are there?",
           sparql="SELECT ?x WHERE { ?x a :Manufacturer }")
    r = _ready(P)
    assert r["ready"] and r["missing"] == []
    assert any(a.startswith("add these terms to the pre-glossary: Manufacturer")
               for a in r["advice"])
    # a CQ that cannot run blocks the stage; a 'should' CQ alone would not satisfy SCP-05
    P.call("ann", "t", "quality.addCompetencyQuestion", id="cq2", question="Broken?",
           sparql="SELECT WHERE {", priority="should")
    r = _ready(P)
    assert not r["ready"] and r["missing"] == ["fix the competency questions that cannot "
                                               "run: cq2"]
    P.call("ann", "t", "quality.removeCompetencyQuestion", id="cq2")
    P.call("ann", "t", "scope.addGlossaryTerms", terms=["manufacturers", "engine"])
    r = _ready(P)
    crit = {c["id"]: c["ok"] for c in r["criteria"]}
    assert crit["SCP-07"] is True                                # plural and case ignored
    assert crit["SCP-08"] is False                               # 'engine' has no CQ
    P.call("ann", "t", "scope.removeGlossaryTerm", label="engine")
    assert {c["id"]: c["ok"] for c in _ready(P)["criteria"]}["SCP-08"] is True


def test_reuse_candidates_are_void_datasets(P):
    P.call("ann", "t", "scope.addReuseCandidate", iri="https://schema.org/",
           title="Schema.org", mode="align", rationale="shared vocabulary")
    meta = P.store.graph(P.projects["t"].layout.metadata)
    assert (None, RDF.type, VOID.Dataset) in meta
    [r] = P.call("val", "t", "scope.specification")["reuse"]
    assert r["mode"] == "align" and r["title"] == "Schema.org"
    with pytest.raises(ValueError):
        P.call("ann", "t", "scope.addReuseCandidate", iri="https://x.org/", title="X",
               mode="copy")
    with pytest.raises(ValueError):
        P.call("ann", "t", "scope.addReuseCandidate", iri="schema", title="X")
    P.call("ann", "t", "scope.removeReuseCandidate", iri="https://schema.org/")
    assert P.call("val", "t", "scope.specification")["reuse"] == []


def test_cq_priority_and_release_gate(P):
    P.call("ann", "t", "owl.createClass", name="Vehicle")
    P.call("ann", "t", "quality.addCompetencyQuestion", id="must1", question="Vehicles?",
           sparql="ASK { :Vehicle a owl:Class }", expectation="ask:true")
    P.call("ann", "t", "quality.addCompetencyQuestion", id="nice1", question="Boats?",
           sparql="ASK { :Boat a owl:Class }", expectation="ask:true", priority="should")
    gate = P.call("pat", "t", "quality.releaseGate")
    assert gate["passed"] and gate["warnings"] == ["competency questions failing: "
                                                   "nice1 (should)"]
    with pytest.raises(ValueError):
        P.call("ann", "t", "quality.addCompetencyQuestion", id="x", question="?",
               sparql="ASK {}", priority="urgent")
    with pytest.raises(ValueError):
        P.call("ann", "t", "quality.addCompetencyQuestion", id="x", question="?",
               sparql="ASK {}", expectation="some")


def test_export_is_a_neon_orsd(P):
    P.call("ann", "t", "scope.setSpecification", purpose="p", non_functional=["English"])
    doc = P.call("val", "t", "scope.exportSpecification")
    for heading in ("## 1. Purpose", "## 2. Scope", "## 3. Implementation language",
                    "## 4. Intended end-users", "## 5. Intended uses",
                    "### a. Non-functional requirements", "## 7. Pre-glossary of terms",
                    "## 8. Reuse candidates", "## Exit criteria"):
        assert heading in doc
    assert "**Ready to close scope:** no" in doc and "* English" in doc


def test_project_templates_seed_the_scope_stage():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    p.registry.add_principal(Principal("pat"))
    p.call("admin", None, "governance.saveTemplate", name="finance", languages=["en", "de"],
           validation=True,
           specification={"non_functional": ["Labels in English and German"]},
           reuse=[{"iri": "https://spec.edmcouncil.org/fibo/ontology/", "title": "FIBO",
                   "mode": "align"}])
    assert [t["name"] for t in p.call("admin", None, "governance.listTemplates")] == ["finance"]
    with pytest.raises(AuthorizationError):
        p.call("pat", None, "governance.saveTemplate", name="mine")
    with pytest.raises(ValueError):
        p.call("admin", None, "governance.saveTemplate", name="bad",
               reuse=[{"iri": "https://x.org/", "title": "X", "mode": "copy"}])
    p.call("admin", None, "governance.createProject", name="bank",
           base_uri="https://ex.org/bank", template="finance", validation=False)
    cfg = p.projects["bank"].config
    assert cfg.languages == ("en", "de") and cfg.validation_enabled is False   # override
    p.call("admin", "bank", "governance.bind", principal="pat", roles=["projectmanager"])
    spec = p.call("pat", "bank", "scope.specification")
    assert spec["specification"]["non_functional"] == ["Labels in English and German"]
    assert spec["reuse"][0]["title"] == "FIBO"
    with pytest.raises(KeyError):
        p.call("admin", None, "governance.createProject", name="x", base_uri="https://x.org",
               template="nope")


def test_requirements_agent_builds_a_grounded_orsd(P):
    C = Conductor(P, simulated_model())
    C.enable_agents("t", "pat")
    run = C.agent("t", "requirements").run("t", BRIEF)
    assert run.status == "done" and all(p.commit for p in run.proposals)
    ops = {p.operation for p in run.proposals}
    assert ops == {"scope.setSpecification", "scope.addReuseCandidate",
                   "scope.addGlossaryTerms", "quality.addCompetencyQuestion"}
    assert all(c["machine"] for c in P.call("val", "t", "validation.pending"))
    assert run.output["readiness"]["ready"] is True                  # staged view
    assert _ready(P)["ready"] is False                               # nothing accepted yet
    for c in P.call("val", "t", "validation.pending"):
        P.call("val", "t", "validation.accept", commit=c["id"])
    r = P.call("val", "t", "scope.specification")
    assert r["readiness"]["ready"] and r["readiness"]["advice"] == []
    assert r["specification"]["scope"] == "vehicles and their parts"
    assert r["specification"]["intended_users"] == ["fleet team"]
    assert r["specification"]["non_functional"] == [
        "Labels must be available in English and French."]
    assert r["reuse"][0]["iri"] == "https://schema.org/" and r["reuse"][0]["mode"] == "align"
    assert {q["id"]: q["priority"] for q in r["competency_questions"]} == {
        "cq_Manufacturer": "must", "cq_Vehicle_Wheel": "must"}


def test_requirements_critic_rejects_ungrounded_items(P):
    model = SimulatedModel()
    q = {"text": "", "quote": ""}
    model.register("requirements.cqs", lambda prompt, schema: {
        "specification": {"purpose": {"text": "Track rockets", "quote": "rockets fly"},
                          "scope": q, "intended_users": [], "intended_uses": [],
                          "non_functional": [{"text": "fast", "quote": "Labels must be "
                                                                         "available"}]},
        "reuse": [{"iri": "https://schema.org/", "title": "Schema.org", "mode": "copy",
                   "rationale": "", "quote": "aligned with schema.org"},
                  {"iri": "urn:not-http", "title": "X", "mode": "align", "rationale": "",
                   "quote": "aligned with schema.org"}],
        "terms": ["vehicle", "rocket"],
        "cqs": [{"id": "c", "question": "?", "sparql": "ASK {", "expectation": "ask:true",
                 "priority": "must", "quote": ""}]})
    P.registry.add_principal(Principal("req@t", is_machine=True, on_behalf_of="pat"))
    P.call("pat", "t", "governance.bind", principal="req@t", roles=["agent-ontology-copilot"])
    run = RequirementsAgent(AgentRuntime(P, model), P.registry.principal("req@t")).run("t", BRIEF)
    submitted = {(p.operation, tuple(p.arguments)) for p in run.proposals if p.commit}
    assert submitted == {("scope.setSpecification", ("non_functional",)),
                         ("scope.addGlossaryTerms", ("terms",))}
    rejected = [p.critic[0] for p in run.proposals if p.critic]
    assert "quote is not verbatim from the brief" in rejected               # purpose
    assert any("mode 'copy'" in c for c in rejected)
    assert any("not an absolute http(s) IRI" in c for c in rejected)
    assert any("'rocket' does not occur" in c for c in rejected)
    assert any("SPARQL does not parse" in c for c in rejected)
