"""Tool belt, critic and the Ontology Review Assistant (offline and a scripted Claude loop)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from validation_agent.agent import assistant as A
from validation_agent.agent.critic import ground
from validation_agent.agent.gateway import LlmGateway
from validation_agent.review import STEPS, ReviewRecord
from validation_agent.tools.belt import ToolBelt, as_langchain_tools

from .conftest import SAMPLES, run_file


@pytest.fixture()
def belt(rail_ws):
    return ToolBelt(rail_ws, actor="test")


def test_sparql_guard(belt):
    assert belt.call("sparql_select", {"query": "DELETE WHERE { ?s ?p ?o }"}).startswith("ERROR")
    assert belt.call("sparql_select", {"query": "SELECT * WHERE { SERVICE <http://x> { ?s ?p ?o } }"}).startswith("ERROR")
    r = belt.call("sparql_select", {"query": "SELECT ?s ?x WHERE { ?s ?p ?o . ?x ?q ?y }"})
    assert len(r["rows"]) == 100 and r["truncated"]
    assert belt.call("sparql_ask", {"query": "ASK { ?s a owl:Class }"}) == {"answer": True}


def test_tools_report_errors_as_text(belt):
    assert belt.call("describe_entity", {"iri": "https://example.org/rail#Nope"}).startswith("ERROR")
    assert belt.call("no_such_tool").startswith("ERROR")
    assert belt.call("get_finding", {"bogus": 1}).startswith("ERROR")
    assert belt.ws.tool_log[-1]["ok"] is False


def test_entity_card_and_neighbourhood(belt):
    card = belt.call("describe_entity", {"iri": "https://example.org/rail#Locomotive"})
    assert card["parents"] == ["https://example.org/rail#RailVehicle"]
    assert {f["check_id"] for f in card["findings"]} >= {"HIER-05", "SYN-06"}
    h = belt.call("hierarchy_neighbourhood", {"iri": "https://example.org/rail#Locomotive"})
    assert "https://example.org/rail#Wagon" in h["siblings"]


def test_what_if_policy_does_not_change_the_run(belt):
    verdict = belt.ws.decision.verdict
    r = belt.call("apply_policy", {"policy": "ci-lenient-v1"})
    assert r["what_if"] and belt.ws.decision.verdict == verdict


def test_langchain_tools(belt):
    tools = as_langchain_tools(belt)
    names = {t.name for t in tools}
    assert "describe_entity" in names
    out = next(t for t in tools if t.name == "check_catalogue").invoke({"check_id": "HIER-05"})
    assert "Disjoint with an ancestor" in out


def test_critic(rail_ws):
    assert ground("See `https://example.org/rail#Locomotive` and f-0001 (HIER-05).", rail_ws) == []
    c = ground("The class https://example.org/rail#Ghost (HIER-99, f-9999) means the verdict is accept.", rail_ws)
    assert len(c) == 4


@pytest.mark.parametrize("sample,declared,shapes", [
    ("rail.ttl", "formal-ontology", "rail_shapes.ttl"),
    ("clean_rail.ttl", "formal-ontology", None),
    ("transport_thesaurus.ttl", "thesaurus", None)])
def test_offline_assistant_answers_every_suggested_question(sample, declared, shapes):
    ws = run_file(SAMPLES / sample, declared=declared, shapes=SAMPLES / shapes if shapes else None)
    verdict = ws.decision.verdict
    findings = [f.to_dict() for f in ws.findings]
    bot = A.ReviewAssistant(ws, ReviewRecord(), LlmGateway(model_id=None))
    for step in STEPS:
        for q in step["questions"] + ["explain f-0001", "how do I fix f-0001?"]:
            r = bot.ask(step["id"], q)
            assert r.answer.strip() and r.model == "simulated"
            assert r.corrections == [], (step["id"], q, r.corrections, r.answer)
    assert ws.decision.verdict == verdict                       # the assistant cannot decide
    assert [f.to_dict() for f in ws.findings] == findings       # ... nor touch findings
    assert bot.status()["critic_corrections"] == 0


# --------------------------------------------------------------------------- #
# Claude back end with a scripted client: checks the tool loop, not the model
# --------------------------------------------------------------------------- #
def _block(**kw):
    return SimpleNamespace(**kw)


class ScriptedClient:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        return self.script.pop(0)


def _response(stop, content):
    return SimpleNamespace(stop_reason=stop, content=content, usage=SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


def test_claude_tool_loop(monkeypatch, rail_ws):
    script = [
        _response("tool_use", [_block(type="text", text="Looking it up."),
                               _block(type="tool_use", id="tu1", name="get_finding",
                                      input={"finding_id": "f-0015"}),
                               _block(type="tool_use", id="tu2", name="describe_entity",
                                      input={"iri": "https://example.org/rail#Locomotive"})]),
        _response("end_turn", [_block(type="text", text="f-0015 (HIER-05): `https://example.org/rail#Locomotive` "
                                                       "is disjoint with its ancestor.")]),
    ]
    client = ScriptedClient(script)

    def fake_init(self, ws, belt, gateway):
        self.client, self.ws, self.belt, self.gateway = client, ws, belt, gateway
        self.model_id, self.tools, self.calls = gateway.model_id, A.anthropic_tools(), []

    monkeypatch.setattr(A.ClaudeBackend, "__init__", fake_init)
    bot = A.ReviewAssistant(rail_ws, ReviewRecord(), LlmGateway(model_id="claude-opus-5-5"))
    r = bot.ask("custom", "Why is Locomotive empty?", finding_id="f-0015")
    assert r.model == "claude-opus-5-5" and r.corrections == []
    assert [c["tool"] for c in r.tool_calls] == ["get_finding", "describe_entity"]
    second = client.requests[1]
    assert second["model"] == "claude-opus-5-5" and second["thinking"] == {"type": "adaptive"}
    results = second["messages"][-1]
    assert results["role"] == "user" and [b["tool_use_id"] for b in results["content"]] == ["tu1", "tu2"]
    assert "<assessment>" in second["messages"][0]["content"][0]["text"]
    assert bot.gateway.calls == 2 and bot.status()["mode"] == "live"


def test_claude_failure_falls_back_offline(monkeypatch, rail_ws):
    def boom(self, ws, belt, gateway):
        raise RuntimeError("no network")
    monkeypatch.setattr(A.ClaudeBackend, "__init__", boom)
    bot = A.ReviewAssistant(rail_ws, ReviewRecord(), LlmGateway(model_id="claude-opus-5-5"))
    r = bot.ask("verdict", "Why is the verdict what it is?")
    assert "offline answer" in r.answer and "reject" in r.answer


def test_gateway_budget_and_allow_list(monkeypatch):
    monkeypatch.setenv("OVA_ASSISTANT_MODEL", "gpt-x")
    with pytest.raises(ValueError):
        LlmGateway.from_env()
    monkeypatch.delenv("OVA_ASSISTANT_MODEL")
    assert LlmGateway.from_env().live is False
    g = LlmGateway(model_id="claude-opus-5-5", max_calls=0)
    assert not g.allow()
