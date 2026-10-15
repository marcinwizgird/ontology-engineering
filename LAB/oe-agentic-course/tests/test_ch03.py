"""Chapter 3: the DL engine's certified corpus, the contamination twins, SIP's fleet modules,
and the tool/agent wiring.

The agent test runs LangChain's real ``create_agent`` loop through ``agentlab.agents``
with a scripted chat model, so it checks the wiring (tools called, calls logged, answer
extracted, usage priced) without calling the API.
"""

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agentlab import agents, tools
from conftest import chapter_path

chapter_path("ch03")
import ch03_agentic as AG  # noqa: E402
import ch03_toolkit as dl  # noqa: E402

A = dl.Atomic


def test_every_stored_label_is_certified():
    how = AG.validate_gold()
    assert len(how) == len(AG.CASES) + len(AG.FIELD_CASES)
    splits = {s: [c for c in AG.CASES if c.split == s] for s in ("train", "dev", "test")}
    for rows in splits.values():
        assert len(rows) == 8 and sum(c.gold_subsumed for c in rows) == 4


def test_contamination_twins():
    rows = AG.contamination_dataset()
    assert len(rows) == 15
    by = {(r.item, r.variant): r for r in rows}
    famous_names = set(AG.RENAME)
    for item, *_ in AG.PIZZA_ITEMS:
        famous, renamed, counter = (by[(item, v)] for v in AG.VARIANTS)
        assert renamed.gold_subsumption == famous.gold_subsumption, item
        assert counter.gold_subsumption != famous.gold_subsumption, item
        words = set(re.findall(r"[A-Za-z]+", renamed.kb + renamed.query))
        assert not words & famous_names, (item, words & famous_names)
        assert {r.gold_dl for r in (famous, renamed, counter)} == {"ALC"}
    # memory and logic disagree on the counterfactuals in both directions
    assert {r.gold_subsumption for r in rows if r.variant == "counterfactual"} == {True, False}


def test_fleet_modules_are_certified_and_mixed():
    rows = AG.fleet_dataset()
    assert len(rows) == 7 and {r.split for r in rows} == {"fleet"}
    assert {r.gold_subsumption for r in rows} == {True, False}
    by = {r.id: r for r in rows}
    # one axiom ("every vehicle has an engine") turns 'only' into 'some'
    assert not by["fleet-truck-diesel-open"].gold_subsumption
    assert by["fleet-truck-diesel-closed"].gold_subsumption
    assert not by["fleet-hybrid-unsat"].sub_satisfiable and by["fleet-hybrid-unsat"].gold_subsumption


def test_review_tools_are_logged_and_errors_are_text():
    ws = AG.ReviewWorkspace("viaduct-critical")
    ts = {t.name: t for t in AG.build_review_tools(ws)}
    assert json.loads(ts["check_subsumption"].invoke(
        {"sub": "Viaduct", "sup": "CriticalStructure"}))["subsumed"] is True
    assert json.loads(ts["dl_expressivity"].invoke({}))["dl"] == "ALC"
    assert ws.log.names() == ["check_subsumption", "dl_expressivity"]
    log = tools.ToolCallLog()
    boom = tools.make_tools([_boom], log)[0]
    assert boom.invoke({"x": 1}).startswith("ERROR: no") and log.summary()["failures"] == 1


def _boom(x: int) -> str:
    """Always fails."""
    raise ValueError("no")


class _ScriptedChat(BaseChatModel):
    """Calls check_subsumption once, then answers with the tool's verdict."""

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        usage = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
        done = [m for m in messages if m.type == "tool"]
        if not done:
            m = re.search(r"is (\w+) subsumed by (\w+)", messages[-1].content)
            msg = AIMessage(content="", usage_metadata=usage, tool_calls=[
                {"name": "check_subsumption", "args": {"sub": m[1], "sup": m[2]}, "id": "1"}])
        else:
            verdict = json.loads(done[-1].content)["subsumed"]
            msg = AIMessage(content=[{"type": "text", "text": json.dumps({"subsumed": verdict})}],
                            usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_agent_loop_calls_the_reasoner_and_prices_the_episode():
    ws = AG.ReviewWorkspace("electrified-low-bridge")
    agent = agents.build_agent(AG.build_review_tools(ws), system_prompt="review",
                               model=_ScriptedChat())
    run = agents.run_agent(agent, "Formally: is ElectrifiedLowBridge subsumed by Tunnel?",
                           log=ws.log)
    assert json.loads(run.answer) == {"subsumed": True}          # vacuously: the subject is unsat
    assert ws.log.names() == ["check_subsumption"]
    usage = agents.chat_usage(run.messages, model="claude-sonnet-5-5")
    assert usage["model_turns"] == 2 and usage["input_tokens"] == 2000
    assert usage["usd_estimate"] == round((2000 * 2.0 + 200 * 10.0) / 1e6, 4)
    assert run.summary()["n_calls"] == 1


def test_revisit_reproduces_chapter_1_and_2_gold():
    import ch01_agentic as ch1
    import ch02_toolkit as fol
    import ch03_revisit as R

    for ex in ch1.build_dataset():
        e = json.loads(R.registry_evidence(ex.id))
        level = e["spectrum"]["level"]
        smells = R.reportable_smells({f["smell"] for f in e["scanner_findings"]}, level)
        assert (level, smells, R.intake_decision(smells, e["submission"]["declared_level"],
                                                 level)) == (ex.level, ex.smells, ex.decision)
        assert R.triage_score(ex, type("P", (), {"level": level, "smells": smells,
                                                 "decision": ex.decision})()) == 1.0
    premises = R.PolicyWorkspace().premises()
    for _, _, conclusion, gold in R.COMPLIANCE_QUERIES:
        assert R.verdict(premises, fol.parse(conclusion)) == gold
