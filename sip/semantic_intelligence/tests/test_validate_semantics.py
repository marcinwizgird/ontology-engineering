"""Validate stage: CQs that could have failed (FR-QA-03) and a calibrated semantic critic
that asks whether each axiom is true in the domain (FR-QA-04)."""

import json

import pytest
from rdflib import Graph

from semantic_intelligence.agents.orchestrator import Conductor
from semantic_intelligence.agents.simulators import simulated_model
from semantic_intelligence.core.principal import Principal
from semantic_intelligence.platform import Platform
from semantic_intelligence.quality import cq as cqmod
from semantic_intelligence.quality import semantic

PREFIX = ("PREFIX : <https://ex.org/t#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
          "PREFIX owl: <http://www.w3.org/2002/07/owl#> ")
REFERENCE = ("A car is a kind of vehicle. A truck is a kind of vehicle. "
             "Every vehicle has several wheels. Every vehicle has an engine.")


@pytest.fixture
def P():
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u in ("pat", "ann", "val"):
        p.registry.add_principal(Principal(u))
    p.call("admin", None, "governance.createProject", name="t", base_uri="https://ex.org/t",
           languages=["en"])
    p.call("admin", "t", "governance.bind", principal="pat", roles=["projectmanager"])
    p.call("admin", "t", "governance.bind", principal="ann", roles=["ontologist"])
    p.call("admin", "t", "governance.bind", principal="val", roles=["validator"])
    for n in ("Vehicle", "Car", "Truck", "Wheel", "Engine"):
        p.call("ann", "t", "owl.createClass", name=n)
    for n in ("Car", "Truck"):
        p.call("ann", "t", "owl.addAxiom", subject=n, kind="SubClassOf", expression="Vehicle")
    p.call("ann", "t", "owl.createProperty", name="hasWheel", domain="Vehicle", range="Wheel")
    p.call("ann", "t", "owl.createProperty", name="hasEngine", domain="Vehicle", range="Engine")
    p.call("ann", "t", "owl.addAxiom", subject="Vehicle", kind="SubClassOf",
           expression="hasWheel some Wheel")
    return p


def _cq(id_, body, expectation="ask:true"):
    return cqmod.CompetencyQuestion(id_, id_, PREFIX + body, expectation)


def test_cq_discrimination_finds_tests_that_cannot_fail(P):
    g = P.projects["t"].ontology()
    cases = {
        # the zero-length path binds :Vehicle itself: true on any graph
        "vacuous": _cq("v", "ASK { ?x rdfs:subClassOf* :Vehicle }"),
        # passes, but not because of the terms it names
        "insensitive": _cq("i", "ASK { { ?c rdfs:subClassOf :Wheel } UNION "
                                "{ ?c rdfs:subClassOf ?d } }"),
        "discriminating": _cq("d", "ASK { :Car rdfs:subClassOf :Vehicle }"),
        "negative": _cq("n", "ASK { :Car rdfs:subClassOf :Wheel }", "ask:false"),
        "failing": _cq("f", "ASK { :Wheel rdfs:subClassOf :Vehicle }"),
    }
    for status, q in cases.items():
        assert cqmod.discrimination(q, g)["status"] == status, status
    assert cqmod.terms(cases["discriminating"]) == {
        cqmod.URIRef("https://ex.org/t#Car"), cqmod.URIRef("https://ex.org/t#Vehicle")}


def test_release_gate_warns_about_a_must_cq_that_tests_nothing(P):
    P.call("pat", "t", "quality.addCompetencyQuestion", id="cq_vac", question="Vehicles?",
           sparql=PREFIX + "ASK { ?x rdfs:subClassOf* :Vehicle }", expectation="ask:true")
    for c in P.call("val", "t", "validation.pending"):
        P.call("val", "t", "validation.accept", commit=c["id"])
    checked = P.call("pat", "t", "quality.checkCompetencyQuestions")
    assert [(c["id"], c["status"]) for c in checked] == [("cq_vac", "vacuous")]
    gate = P.call("pat", "t", "quality.releaseGate")
    assert gate["passed"]                                   # a warning, not a blocker
    assert any("test nothing: cq_vac (vacuous)" in w for w in gate["warnings"])


def test_verbalisation_and_seeded_mutants(P):
    ctx = P.projects["t"]
    g, sfp = ctx.ontology(), ctx.sfp()
    st = {s.english for s in semantic.statements(g, sfp)}
    assert "Every car is a vehicle." in st
    assert "Every vehicle is related by 'has wheel' to at least one wheel." in st
    assert "Anything related by 'has engine' to something is a vehicle." in st
    ms = semantic.mutants(g, sfp)
    assert {m.mutation for m in ms} == set(semantic.MUTATIONS)
    assert not {m.manchester for m in ms} & {s.manchester for s in semantic.statements(g, sfp)}
    assert "Every vehicle is related by 'has wheel' to no wheel." in {m.english for m in ms}


def test_calibration_scores_a_verifier():
    o = [semantic.Statement(f"ax-{i}", "SubClassOf", "A", f"o{i}", "x") for i in range(4)]
    m = [semantic.Statement(f"mu-{i}", "SubClassOf", "A", f"m{i}", "x", "reverse")
         for i in range(4)]
    always_false = {s.id: "false" for s in o + m}
    c = semantic.calibration(always_false, o, m)
    assert (c["recall"], c["precision"], c["false_alarms"]) == (1.0, 0.5, 4)
    c = semantic.calibration({}, o, m)
    assert (c["recall"], c["precision"], c["coverage"]) == (0.0, None, 0.0)


def test_semantic_critic_flags_a_wrong_axiom_with_measured_precision(P):
    # a human models the engine as a wheel: consistent, so no reasoner or ICV check sees it
    P.call("ann", "t", "owl.addAxiom", subject="Vehicle", kind="SubClassOf",
           expression="hasEngine some Wheel")
    C = Conductor(P, simulated_model())
    C.enable_agents("t", "pat")
    run = C.agent("t", "semantic-critic").run("t", reference=REFERENCE)
    out = run.output
    assert [f["axiom"] for f in out["findings"]] == ["Vehicle SubClassOf hasEngine some Wheel"]
    assert out["findings"][0]["severity"] == "advisory"
    cal = out["calibration"]
    assert cal["mutants"] > 0 and cal["recall"] is not None and cal["precision"] is not None
    assert run.proposals == []                               # advisory: it writes nothing
    assert out["judged"]["Car SubClassOf Vehicle"] == "holds"


def test_semantic_critic_hides_which_statements_are_mutants(P):
    model = simulated_model()
    C = Conductor(P, model)
    C.enable_agents("t", "pat")
    C.agent("t", "semantic-critic").run("t", reference=REFERENCE)
    prompt_out = next(t for t in model.transcript if "verdicts" in t["output"])
    ids = [v["id"] for v in prompt_out["output"]["verdicts"]]
    assert all(i.startswith("s") and i[1:].isdigit() for i in ids)


def test_semantic_critic_degrades_without_model_permission(P):
    ctx = P.projects["t"]
    ctx.config.ai_policy.llm_allowed = False
    C = Conductor(P, simulated_model())
    C.enable_agents("t", "pat")
    run = C.agent("t", "semantic-critic").run("t", reference=REFERENCE)
    assert run.status == "degraded" and run.output["findings"] == []


def test_validate_stage_reports_cq_checks_and_semantic_verdicts():
    from semantic_intelligence import demo
    import io
    r = demo.run(out=io.StringIO(), verbose=False)
    val = next(x for x in r["reports"] if x.stage == "validate")
    assert {c["status"] for c in val.output["competency_questions"]} <= {
        "discriminating", "failing", "negative"}
    sem = val.output["semantic"]
    assert sem["calibration"]["mutants"] > 0
    assert any(x["agent"] == "semantic-critic" for x in val.runs)
    json.dumps(sem)                                          # serialisable for the API
