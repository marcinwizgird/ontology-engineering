# %% [markdown] assignment
# # Problem Set 2: Agents on the registry and the compliance checker
# ### Chapter 3 — revisiting Chapters 1 and 2
#
# **Topic coverage:** the agent layer of Chapter 3 (`agentlab.tools`, `agentlab.agents`), applied to the tasks of Chapter 1 (the ontology registry, Keet §1.2–1.3) and Chapter 2 (formalised policy, closed-domain entailment, Keet §2.2).
#
# **Level:** Graduate (practice-first).
#
# **Total points:** 30 (Part A 8 / Part B 10 / Part C 12); 13 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 4–5 hours.
#
# **API budget:** ≈ \$0.50–1.50 **estimated, not yet measured** on `claude-sonnet-5-5`: 14 agent episodes (a few cents each) and 8 DSPy calls. Part A calls no model.
#
# ## Why this problem set exists
#
# Chapters 1 and 2 built their tasks before the course had tools or agents, so their problem sets stopped where an agent was needed. Those parts return here, on the original tasks and data:
#
# * **Part A** (original Chapter 1, A2): the registry as narrow, logged tools — and what a one-call "mega-tool" hides.
# * **Part B** (original Chapter 1, D1): one agent loop against a fixed program with a verifying critic, on Meridian Rail's intake triage.
# * **Part C** (original Chapter 2, D1): a compliance agent that proves its verdicts with an entailment checker, on St. Brigid's access policy.
#
# The support code is `ch03_revisit.py`. It imports Chapter 1's registry corpus and Chapter 2's FOL engine: a revisit problem set may reach *back* to an earlier chapter, never ahead. Chapter 1's policy functions (its A1 answer) are provided as `R.reportable_smells` and `R.intake_decision`.
#
# ## Submission requirements
#
# 1. **This notebook, executed top to bottom**, with every `TODO` implemented and every *Your answer* cell written.
# 2. **Honest reporting.** A number without its sample size and its cost earns no credit.
#
# The check cells are the marking scheme for the auto-graded points; do not edit them. The final self-test prints your auto-graded subtotal.
#
# > Solutions: `06_solutions.ipynb` — do not open it until you have attempted every problem.

# %% [markdown] solution
# # Problem Set 2: Agents on the registry and the compliance checker — Solutions
# ### Chapter 3 — revisiting Chapters 1 and 2
#
# **Topic coverage:** the agent layer of Chapter 3 (`agentlab.tools`, `agentlab.agents`), applied to the tasks of Chapter 1 (the ontology registry, Keet §1.2–1.3) and Chapter 2 (formalised policy, closed-domain entailment, Keet §2.2).
#
# **Level:** Graduate (practice-first).
#
# **Total points:** 30 (Part A 8 / Part B 10 / Part C 12); 13 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 4–5 hours.
#
# **API budget:** ≈ \$0.50–1.50 **estimated, not yet measured** on `claude-sonnet-5-5`: 14 agent episodes (a few cents each) and 8 DSPy calls. Part A calls no model.
#
# ## Why this problem set exists
#
# Chapters 1 and 2 built their tasks before the course had tools or agents, so their problem sets stopped where an agent was needed. Those parts return here, on the original tasks and data:
#
# * **Part A** (original Chapter 1, A2): the registry as narrow, logged tools — and what a one-call "mega-tool" hides.
# * **Part B** (original Chapter 1, D1): one agent loop against a fixed program with a verifying critic, on Meridian Rail's intake triage.
# * **Part C** (original Chapter 2, D1): a compliance agent that proves its verdicts with an entailment checker, on St. Brigid's access policy.
#
# The support code is `ch03_revisit.py`. It imports Chapter 1's registry corpus and Chapter 2's FOL engine: a revisit problem set may reach *back* to an earlier chapter, never ahead. Chapter 1's policy functions (its A1 answer) are provided as `R.reportable_smells` and `R.intake_decision`.
#
# ## Submission requirements
#
# 1. **This notebook, executed top to bottom**, with every `TODO` implemented and every *Your answer* cell written.
# 2. **Honest reporting.** A number without its sample size and its cost earns no credit.
#
# The check cells are the marking scheme for the auto-graded points; do not edit them. The final self-test prints your auto-graded subtotal.
#
# > This is the **instructor solutions** notebook. Student version: `06_assignment.ipynb`.

# %%
# revisits: ch01_introduction, ch02_first_order_logic
import sys, json, logging
from pathlib import Path

# Make the course root (the folder holding agentlab/) and this chapter importable.
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "agentlab").is_dir():
        sys.path.insert(0, str(candidate))
        break
sys.path.insert(0, str(here))

import agentlab
from agentlab import llm
from agentlab.grading import Grader

print(json.dumps(agentlab.describe_environment(), indent=1))
llm.require_credentials()             # this problem set calls the live Anthropic API
logging.getLogger("dspy").setLevel(logging.WARNING)
GRADER = Grader('Chapter 3 — Problem Set 2 — Agents on the registry and the compliance checker')

import re
import dspy
import pandas as pd
from agentlab import evaluation as ev, agents
import ch03_revisit as R
import ch01_agentic as A          # Chapter 1: the registry corpus
import ch02_toolkit as fol        # Chapter 2: the FOL engine

ALL, test = A.build_dataset(), A.build_dataset("test")
reportable_smells, intake_decision = R.reportable_smells, R.intake_decision
print(f"{len(ALL)} registry submissions ({len(test)} in test); "
      f"{len(R.COMPLIANCE_QUERIES)} compliance questions")

# %% [markdown]
# ---
#
# ## Part A — The registry as tools (original Chapter 1, A2)

# %% [markdown]
# ### A2. Tools, trajectories, and what a mega-tool hides (8 pts)
#
# The registry tools (`R.build_registry_tools(ws)`) are narrow and logged: every call lands
# in `ws.log` (a `ToolCallLog`). `R.TOOL_TO_EVIDENCE` names the kind of evidence each tool
# buys.
#
# 1. Write `evidence_from_log(log) -> frozenset` — the evidence kinds a trajectory bought.
# 2. Write `scripted_review(submission_id, ws) -> dict` with keys `level`, `smells`,
#    `decision`: a *deterministic reviewer* that invokes (with `.invoke`) only the registry
#    tools it needs and applies your A1 functions. Run it on all 24 submissions, each in a
#    fresh workspace, and set `control_accuracy` to the fraction it gets fully right.
# 3. Build `a2`, one row per toolset for the submission `"interlocking-import"`: the
#    decomposed trajectory of your scripted reviewer and one call of the monolithic
#    `R.build_monolithic_tool(ws)`; columns `toolset` (`"decomposed"` / `"monolithic"`),
#    `calls`, `result_chars` (sum over the log), `evidence_visible`
#    (`sorted(evidence_from_log(...))`).
#
# In writing: what does the monolithic tool cost you — think of the trajectory as a record,
# of reward shaping, and of least privilege — and when would you still ship one? Read the
# tool descriptions in `ch01_agentic.py`: which sentence in `submission_record`'s description
# makes an agent call it, and what would happen if it were missing?

# %% [markdown]
# #### Background and design decisions — A2
#
# This is where you meet the **workspace** and the **tool registry** (Background §2–4) as
# a user. Build the tools on a workspace, call them with `.invoke`, decode the JSON, and
# look at `ws.log`. The scripted reviewer shows what the task costs *without any model*: if
# code gets 24/24 with four calls, every Claude result later is measured against that.
#
# Decisions you make:
#
# * **Which tools to call.** Only what the policy needs: the record (declared level), the
#   spectrum (measured level), the scanner. `graph_metrics` is not needed to decide; every
#   extra call is cost and noise in the trajectory.
# * **A fresh workspace per submission**, so each log is one clean trajectory and nothing
#   from the previous item leaks into the next.
# * **What counts as evidence.** `evidence_from_log` counts only successful calls: a failed
#   call bought nothing. `load_submission` buys no evidence; it only makes the others
#   possible.
# * **Narrow vs monolithic.** The monolithic tool is *one* call that returns everything,
#   so the log cannot say what the decision used. The written part asks when you would still
#   ship one.

# %% [markdown]
# #### Contract — A2
#
# ```python
# def evidence_from_log(log: ToolCallLog) -> frozenset[str]
# def scripted_review(submission_id: str, ws: R.RegistryWorkspace) -> dict
# control_accuracy: float
# a2: pd.DataFrame
# ```
#
# **`evidence_from_log(log)`** — `log` is a workspace's `ws.log`. Loop over `log.calls`;
# for every call with `ok == True` whose `name` is a key of `R.TOOL_TO_EVIDENCE`, collect
# `R.TOOL_TO_EVIDENCE[name]`. Return the kinds as a `frozenset[str]` (a subset of
# `R.EVIDENCE_KINDS`). Example: a log of `load_submission, spectrum_position, scan_smells`
# → `frozenset({"spectrum", "smells"})`.
#
# **`scripted_review(submission_id, ws)`** — a deterministic reviewer, no model.
#
# | parameter | type | meaning |
# |---|---|---|
# | `submission_id` | `str` | e.g. `"signalling-equipment"` |
# | `ws` | `R.RegistryWorkspace` | a **fresh** workspace; build the tools on it so every call lands in `ws.log` |
#
# It must call `load_submission` first, then only the tools whose output it needs
# (`submission_record` for the declared level, `spectrum_position`, `scan_smells`), **at
# most 5 calls in total, none failing**. Returns a dict with **exactly** these three keys
# (the check compares the whole dict with `==`):
#
# ```python
# {"level": "taxonomy",                                   # str, the measured level
#  "smells": ["no-disjointness", "subsumption-cycle"],    # reportable_smells(...) output
#  "decision": "reject"}                                  # intake_decision(...) output
# ```
#
# Remember that `scan_smells` returns one entry per finding, so collect the `"smell"` values
# into a set before calling `reportable_smells`.
#
# **`control_accuracy`** — `float` in [0, 1]: over all 24 rows of `ALL`, the fraction for
# which `scripted_review(ex.id, R.RegistryWorkspace()) == {"level": ex.level, "smells":
# ex.smells, "decision": ex.decision}`.
#
# **`a2`** — a 2-row DataFrame for submission `"interlocking-import"`:
#
# | column | type | meaning |
# |---|---|---|
# | `toolset` | `str` | `"decomposed"` (your `scripted_review`) or `"monolithic"` (one `review_submission` call) |
# | `calls` | `int` | `len(ws.log.calls)` for that toolset's workspace |
# | `result_chars` | `int` | `sum(c.result_chars for c in ws.log.calls)` |
# | `evidence_visible` | `list[str]` | `sorted(evidence_from_log(ws.log))` |
#
# Use a separate fresh workspace for each row. The monolithic tool is
# `R.build_monolithic_tool(ws)[0].invoke({"submission_id": "interlocking-import"})`.

# %%
ws_demo = R.RegistryWorkspace()
for t in R.build_registry_tools(ws_demo):
    params = list(t.args_schema.model_json_schema().get("properties", {}))
    print(f"{t.name:18s} {str(params):18s} {t.description.splitlines()[0][:80]}")

# %% assignment
def evidence_from_log(log) -> frozenset[str]:
    """Evidence kinds bought by the ok calls in a ToolCallLog (see Contract A2)."""
    # TODO
    raise NotImplementedError

def scripted_review(submission_id: str, ws) -> dict:
    tools = {t.name: t for t in R.build_registry_tools(ws)}
    """Deterministic review -> {"level", "smells", "decision"} (see Contract A2)."""
    # TODO: invoke only the tools you need, then apply reportable_smells / intake_decision
    raise NotImplementedError

control_accuracy = None   # TODO
a2 = None                 # TODO

# %% solution
def evidence_from_log(log) -> frozenset[str]:
    return frozenset(R.TOOL_TO_EVIDENCE[c.name] for c in log.calls
                     if c.ok and c.name in R.TOOL_TO_EVIDENCE)

def scripted_review(submission_id: str, ws) -> dict:
    tools = {t.name: t for t in R.build_registry_tools(ws)}
    tools["load_submission"].invoke({"submission_id": submission_id})
    record = json.loads(tools["submission_record"].invoke({}))
    level = json.loads(tools["spectrum_position"].invoke({}))["level"]
    raw = {f["smell"] for f in json.loads(tools["scan_smells"].invoke({}))}
    smells = reportable_smells(raw, level)
    return {"level": level, "smells": smells,
            "decision": intake_decision(smells, record["declared_level"], level)}

hits = []
for ex in ALL:
    out = scripted_review(ex.id, R.RegistryWorkspace())
    hits.append(out == {"level": ex.level, "smells": ex.smells, "decision": ex.decision})
control_accuracy = sum(hits) / len(hits)
print(f"deterministic control: {sum(hits)}/{len(hits)} fully correct")

ws_d, ws_m = R.RegistryWorkspace(), R.RegistryWorkspace()
scripted_review("interlocking-import", ws_d)
R.build_monolithic_tool(ws_m)[0].invoke({"submission_id": "interlocking-import"})
a2 = pd.DataFrame([
    {"toolset": name, "calls": len(ws.log.calls),
     "result_chars": sum(c.result_chars for c in ws.log.calls),
     "evidence_visible": sorted(evidence_from_log(ws.log))}
    for name, ws in [("decomposed", ws_d), ("monolithic", ws_m)]])
print("trajectory:", " -> ".join(ws_d.log.names()))
a2

# %%
# Marking scheme for A2 -- do not edit.
with GRADER.check('A2', points=4):
    ws_c = R.RegistryWorkspace()
    out = scripted_review("signalling-equipment", ws_c)
    assert out == {"level": "taxonomy", "smells": ["no-disjointness", "subsumption-cycle"],
                   "decision": "reject"}, out
    assert not any(not c.ok for c in ws_c.log.calls), "no failed tool calls"
    assert len(ws_c.log.calls) <= 5, "call only the tools you need"
    assert evidence_from_log(ws_c.log) >= {"spectrum", "smells"}
    assert control_accuracy == 1.0
    assert isinstance(a2, pd.DataFrame) and set(a2["toolset"]) == {"decomposed", "monolithic"}
    m = a2.set_index("toolset")
    assert m.loc["monolithic", "calls"] == 1 and list(m.loc["monolithic", "evidence_visible"]) == []
    assert {"spectrum", "smells"} <= set(m.loc["decomposed", "evidence_visible"])

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# The deterministic control is **24/24** with four tool calls and no model. Everything
# Claude does on the structured fields later is measured against that — the honest framing
# of the whole problem set is "how faithfully does a model apply a written policy from
# evidence", which matters because real policies have clauses that cannot be coded, and
# the coded clauses are the only place where faithfulness can be measured exactly.
#
# **What the mega-tool costs.** (i) *Record*: the log shows one opaque call, so you cannot
# tell afterwards which evidence the decision rested on — `evidence_visible` is empty.
# (ii) *Reward shaping*: the MDP of Chapter 6 charges and credits evidence kinds; a single
# call that buys everything cannot be priced, so "gathered too much" is invisible. (iii)
# *Least privilege and cost*: it returns the whole catalogue and all metrics every time
# (several times the characters of the narrow trajectory), which is paid in input tokens
# on every agent turn. It is still the right design when the combined call is the only
# unit that is ever used, when latency per round-trip dominates, or for a trusted batch
# job that is not an agent.
#
# **Trigger sentences.** `submission_record` says *"Call this before deciding, because the
# decision compares the measured level with the level the team declared."* Models select
# tools from descriptions; without the *when* and *why*, an agent that has spectrum and
# scanner output will usually decide without the form and get every over-promising
# submission (e.g. *rostering-roles*, *network-routes*) wrong — the decision needs the
# declared level and nothing else in the tool belt provides it.

# %% [markdown]
# ---
#
# ## Part B — One agent loop, or a pipeline with a verifying critic? (original Chapter 1, D1)

# %% [markdown]
# ### B1. Agent, program, program + critic (10 pts)
#
# The architecture question of Chapter 1, now that the course has agents. The **agent**
# lets Claude choose the tool calls; the **program** fixes them (it reads the evidence
# bundle `R.registry_evidence`, gathered through the same logged tools); the **critic**
# checks the program's structured answer against the raw evidence with the policy as code.
#
# 1. Write `AGENT_PROMPT`: a system prompt for a tool-calling agent over
#    `R.build_registry_tools(ws)` that must end its reply with one JSON object
#    `{"level": ..., "smells": [...], "decision": ..., "report": ...}`; and
#    `parse_triage_answer(text) -> dspy.Prediction` (fields `level`, `smells`, `decision`,
#    `report`; the *last* JSON object that has a `decision` key, possibly inside a code
#    fence or prose, possibly with nested brackets; empty fields when there is none).
# 2. Write the **program**: a signature `Triage` with input `evidence` and outputs `level`,
#    `smells` (`list[str]`), `decision` and `report`, run by `dspy.Predict` with
#    `A.INTAKE_POLICY` as its instruction (Chapter 1's *guidelines* program).
# 3. Write `critic(pred, evidence) -> (dspy.Prediction, list[str])`: a deterministic
#    verification stage over the raw evidence JSON. It overrides any field the evidence
#    decides — level, reportable smells, decision (`R.reportable_smells`,
#    `R.intake_decision`) — keeps the report, and returns one human-readable string per
#    correction.
# 4. On every `test` submission run (a) the agent (fresh `R.RegistryWorkspace()` each;
#    `agents.build_agent(R.build_registry_tools(ws), system_prompt=AGENT_PROMPT)`,
#    `agents.run_agent(agent, f"Triage the registry submission '{id}'.", log=ws.log)`;
#    keep `agent_logs[id] = ws.log`), (b) the program, (c) the program followed by the
#    critic. Build `b1` with columns `approach` (`"agent"`, `"program"`,
#    `"program+critic"`), `id`, `score` (`R.triage_score`), `tool_calls`, `usd`
#    (`agents.chat_usage(run.messages)["usd_estimate"]` for the agent, `llm.meter` for the
#    program).
#
# In writing: compare the three on score, cost and legibility. If the critic can override
# all three structured fields, what is Claude for in this system — and how would you
# evaluate that part?

# %% assignment
AGENT_PROMPT = "TODO"

def parse_triage_answer(text: str) -> dspy.Prediction:
    """Last JSON object with a "decision" key -> Prediction(level, smells, decision, report)."""
    # TODO
    raise NotImplementedError

# TODO: class Triage(dspy.Signature): ...; program = dspy.Predict(...)

def critic(pred, evidence: str) -> tuple[dspy.Prediction, list[str]]:
    """Override level/smells/decision from the evidence; keep the report."""
    # TODO: return (corrected prediction, list of corrections)
    raise NotImplementedError

lm = llm.configure_dspy()
agent_logs = {}
b1 = None   # TODO

# %% solution
AGENT_PROMPT = """You triage submissions to Meridian Rail's ontology registry under
intake policy v3. Use the registry tools; never answer from memory.

Procedure:
1. load_submission, then submission_record, spectrum_position and scan_smells.
2. Level: the level spectrum_position measured (not the declared level).
3. Defects: every scanner id, except no-disjointness when the measured level is
   controlled-vocabulary or thesaurus. Never add an id the scanner did not return.
4. Decision: reject if any of subsumption-cycle, class-as-individual,
   individual-as-class, undeclared-term is reported; otherwise revise if any defect is
   reported or the measured level is below the declared level; otherwise accept.
5. Report: 3-5 sentences to the team citing the terms and counts the tools returned.

End your reply with exactly one JSON object and nothing after it:
{"level": "...", "smells": ["..."], "decision": "...", "report": "..."}
"""

_DECODER = json.JSONDecoder()

def parse_triage_answer(text: str) -> dspy.Prediction:
    text, found = text or "", {}
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = _DECODER.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "decision" in obj:
            found = obj
    return dspy.Prediction(level=str(found.get("level", "")),
                           smells=ev.parse_label_list(found.get("smells")),
                           decision=str(found.get("decision", "")),
                           report=str(found.get("report", "")))

class Triage(dspy.Signature):
    """Triage one registry submission from its evidence bundle."""

    evidence: str = dspy.InputField(desc="JSON: the intake form, metrics, measured spectrum level and scanner findings")
    level: str = dspy.OutputField(desc="the measured spectrum level")
    smells: list[str] = dspy.OutputField(desc="the reportable scanner ids")
    decision: str = dspy.OutputField(desc="accept, revise or reject")
    report: str = dspy.OutputField(desc="3-5 sentences to the submitting team")

program = dspy.Predict(Triage.with_instructions(A.INTAKE_POLICY))

def critic(pred, evidence: str) -> tuple[dspy.Prediction, list[str]]:
    e = json.loads(evidence)
    measured = e["spectrum"]["level"]
    smells = reportable_smells({f["smell"] for f in e["scanner_findings"]}, measured)
    decision = intake_decision(smells, e["submission"]["declared_level"], measured)
    claimed = set(ev.parse_label_list(getattr(pred, "smells", None)))
    corrections = []
    if str(getattr(pred, "level", "")).strip().lower() != measured:
        corrections.append(f"level {getattr(pred, 'level', '')!r} -> {measured!r}")
    for s in sorted(claimed - set(smells)):
        corrections.append(f"dropped unsupported or waived defect {s!r}")
    for s in sorted(set(smells) - claimed):
        corrections.append(f"added missed defect {s!r}")
    if str(getattr(pred, "decision", "")).strip().lower() != decision:
        corrections.append(f"decision {getattr(pred, 'decision', '')!r} -> {decision!r}")
    fixed = dspy.Prediction(level=measured, smells=smells, decision=decision,
                            report=str(getattr(pred, "report", "")))
    return fixed, corrections

lm = llm.configure_dspy()
rows, agent_logs, corrections_log = [], {}, {}
for ex in test:
    ws = R.RegistryWorkspace()
    agent = agents.build_agent(R.build_registry_tools(ws), system_prompt=AGENT_PROMPT)
    run = agents.run_agent(agent, f"Triage the registry submission '{ex.id}'.", log=ws.log)
    agent_logs[ex.id] = ws.log
    rows.append({"approach": "agent", "id": ex.id,
                 "score": R.triage_score(ex, parse_triage_answer(run.answer)),
                 "tool_calls": len(ws.log.calls),
                 "usd": agents.chat_usage(run.messages)["usd_estimate"]})

    ws_p = R.RegistryWorkspace()
    evidence = R.registry_evidence(ex.id, ws_p)
    with llm.meter(lm) as cost:
        pred = program(evidence=evidence)
    fixed, corrections_log[ex.id] = critic(pred, evidence)
    for name, p in [("program", pred), ("program+critic", fixed)]:
        rows.append({"approach": name, "id": ex.id, "score": R.triage_score(ex, p),
                     "tool_calls": len(ws_p.log.calls), "usd": cost["usd"]})
b1 = pd.DataFrame(rows)
print({k: v for k, v in corrections_log.items() if v})
b1.groupby("approach")[["score", "tool_calls", "usd"]].agg(["mean", "sum"])

# %%
# Marking scheme for B1 -- do not edit.
with GRADER.check('B1', points=4):
    p = parse_triage_answer('Done.\n```json\n{"level": "taxonomy", "smells": ["missing-label"], '
                            '"decision": "revise", "report": "Label mr:X."}\n```')
    assert (p.level, p.smells, p.decision) == ("taxonomy", ["missing-label"], "revise")
    p = parse_triage_answer('{"note": {"a": 1}} then {"level": "thesaurus", "smells": [], '
                            '"decision": "accept", "report": "x", "extra": {"k": [1, 2]}}')
    assert (p.level, p.smells, p.decision) == ("thesaurus", [], "accept")
    p = parse_triage_answer("I think it should be rejected.")
    assert (p.level, p.smells, p.decision) == ("", [], "")

    evidence = R.registry_evidence("timetable-service-thesaurus")
    bad = dspy.Prediction(level="taxonomy", smells=["no-disjointness", "missing-label"],
                          decision="revise", report="keep me")
    fixed, corrections = critic(bad, evidence)
    assert (fixed.level, list(fixed.smells), fixed.decision, fixed.report) == \
        ("thesaurus", [], "accept", "keep me")
    assert len(corrections) >= 4
    good = dspy.Prediction(level="thesaurus", smells=[], decision="accept", report="ok")
    assert critic(good, evidence)[1] == []

    assert isinstance(b1, pd.DataFrame)
    assert set(b1["approach"]) == {"agent", "program", "program+critic"}
    assert {"approach", "id", "score", "tool_calls", "usd"} <= set(b1.columns)
    assert all(set(g["id"]) == {ex.id for ex in test} for _, g in b1.groupby("approach"))
    assert set(agent_logs) == {ex.id for ex in test}
    _crit = b1[b1.approach == "program+critic"].set_index("id")["score"]
    assert all(abs(_crit[ex.id] - 1.0) < 1e-9 for ex in test), "the critic decides every field"

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Expected shape of a live run (yours is the answer): the **agent** usually matches the
# program on the structured fields when its prompt carries the policy, but costs several
# times more per item (5–8 turns, each re-sending the growing transcript and the tool
# schemas) and its trajectory varies — sometimes it skips `submission_record` and misses
# an over-promise, sometimes it calls `smell_catalogue` or SPARQL for nothing. The
# **program** makes exactly five tool calls and one model call. **program+critic** scores
# 1.0 on the structured fields *by construction*: the critic has the raw evidence and the
# policy as code, so a hallucinated defect or an improvised decision cannot survive it. The
# corrections list is the log of what the model got wrong — a monitoring signal worth
# keeping even when the critic fixes it.
#
# **What is Claude for, then?** The report: explaining each defect in the team's terms and
# saying what to change. That is the part no function computes, and the part that needs a
# validated judge (Chapter 5) or a human reader to evaluate. The design lesson is the one
# Chapter 3's main problem set reached on the reasoner: put measurement and decidable rules
# in code, use the model for what is genuinely judgement or language, and verify the
# model's claims against raw tool output before they leave the system. The agent loop is
# the right choice only when the order of work genuinely depends on what is found — not
# here, where the evidence plan is fixed.

# %% [markdown]
# ---
#
# ## Part C — A compliance agent that proves its verdicts (original Chapter 2, D1)

# %% [markdown]
# ---
#
# # The formalised policy (`R.POLICY_KB`) and the audit-day facts (`R.FACTS`) are
# provided. The domain is **closed**: only the named individuals exist, which turns
# entailment into propositional satisfiability — decided exactly by
# `R.ground_entails`. The agent's tools wrap it; your job is the agent, its output
# contract, and its evaluation.

# %%
ws_demo = R.PolicyWorkspace()
premises = ws_demo.premises()
gold_verdicts = {qid: R.verdict(premises, fol.parse(c)) for qid, _, c, _ in R.COMPLIANCE_QUERIES}
assert gold_verdicts == {qid: g for qid, _, _, g in R.COMPLIANCE_QUERIES}
pd.DataFrame([{"id": q, "question": text, "conclusion": c, "gold": g}
              for q, text, c, g in R.COMPLIANCE_QUERIES])

# %% [markdown]
# ### C1. Build and evaluate the compliance agent (12 pts)
#
# 1. Write `COMPLIANCE_PROMPT`, the agent's system prompt. It must make the agent read
#    the policy and facts, **check both the claim and its negation** before answering,
#    answer *undetermined* when neither is entailed, and end with a JSON object
#    `{"verdict": "yes" | "no" | "undetermined", "evidence": [...]}`.
# 2. Write `parse_verdict(text) -> str`: return the verdict from the agent's final text
#    (the JSON may be inside a code fence or surrounded by prose), or `"unparseable"`.
# 3. For every query, build a fresh `R.PolicyWorkspace()`, its tools
#    (`R.build_policy_tools(ws)`), an agent (`agents.build_agent(tools,
#    system_prompt=...)`), run it with `agents.run_agent(agent, question, log=ws.log)`, and
#    collect `c1` with columns `id`,
#    `gold`, `predicted`, `correct`, `tool_calls`, `checked_both` (did the log contain at
#    least two `check_entailment` calls?) and `usd_estimate`
#    (`agents.chat_usage(run.messages)`).
#
# In writing: report accuracy with its sample size, the cost per question, and examine
# every error and every *undetermined* case. Is the Dee–R1 verdict a model error or a
# gap in the policy? What would you tell the governance office?

# %% assignment
COMPLIANCE_PROMPT = """TODO"""

def parse_verdict(text: str) -> str:
    # TODO
    raise NotImplementedError

c1 = None   # TODO: run the agent on every query

# %% solution
COMPLIANCE_PROMPT = """\
You are the compliance checker for St. Brigid's Hospital. Answer one access
question using only the formalised policy and the facts, which you read with your
tools. The domain is closed: only the named individuals exist.

Procedure:
1. Read the policy and the facts.
2. Formalise the question as a closed formula over the policy's predicates and the
   capitalised constants (e.g. CanAccess(Ana, R1)).
3. Call check_entailment on the claim AND on its negation.
4. Verdict: "yes" if the claim is entailed, "no" if its negation is entailed,
   "undetermined" if neither is. Never guess; the checker decides.

End your reply with a JSON object and nothing after it:
{"verdict": "yes" | "no" | "undetermined", "evidence": ["policy ids and facts used"]}
"""

VERDICTS = {"yes", "no", "undetermined"}

def parse_verdict(text: str) -> str:
    for blob in reversed(re.findall(r"\{[^{}]*\}", text or "")):
        try:
            value = str(json.loads(blob).get("verdict", "")).strip().lower()
        except (json.JSONDecodeError, AttributeError):
            continue
        if value in VERDICTS:
            return value
    return "unparseable"

rows = []
for qid, question, _, gold in R.COMPLIANCE_QUERIES:
    ws = R.PolicyWorkspace()
    agent = agents.build_agent(R.build_policy_tools(ws), system_prompt=COMPLIANCE_PROMPT)
    run = agents.run_agent(agent, question, log=ws.log)
    predicted = parse_verdict(run.answer)
    names = ws.log.names()
    rows.append({"id": qid, "gold": gold, "predicted": predicted,
                 "correct": predicted == gold, "tool_calls": len(names),
                 "checked_both": names.count("check_entailment") >= 2,
                 "usd_estimate": agents.chat_usage(run.messages)["usd_estimate"]})
c1 = pd.DataFrame(rows)
print(f"accuracy {c1.correct.mean():.2f} on n={len(c1)}; "
      f"cost ≈ ${c1.usd_estimate.sum():.3f} total")
c1

# %%
# Marking scheme for C1 -- do not edit.
with GRADER.check('C1', points=5):
    assert parse_verdict('{"verdict": "yes", "evidence": []}') == "yes"
    assert parse_verdict('Checked both.\n```json\n{"verdict": "undetermined", "evidence": ["x"]}\n```') == "undetermined"
    assert parse_verdict('prose {"note": 1} then {"verdict": "NO", "evidence": []}') == "no"
    assert parse_verdict("I think yes.") == "unparseable"
    assert isinstance(c1, pd.DataFrame) and len(c1) == len(R.COMPLIANCE_QUERIES)
    assert {"id", "gold", "predicted", "correct", "tool_calls", "checked_both",
            "usd_estimate"} <= set(c1.columns)
    assert set(c1["predicted"]) <= {"yes", "no", "undetermined", "unparseable"}
    assert (c1["correct"] == (c1["predicted"] == c1["gold"])).all()

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# With the procedure above Claude typically answers all six correctly (n = 6 — report it
# as "6/6", not "100 % accuracy"), with 4–6 tool calls and a few cents per question. The
# instructive cases:
#
# * **Ben–R2 (undetermined).** Ben is a clinician but is not recorded as treating Ole,
#   so the treating-clinician rule does not fire — and nothing *forbids* access either.
#   The policy grants access in some cases and denies it in others; it is silent here.
# * **Dee–R1 (undetermined).** Dee is an external auditor, but the auditor rule only
#   protects *sensitive* records, and R1 is not sensitive. Access would require Dee to be
#   a clinician (only-clinicians-access), and nothing says she is not. This is **not** a
#   model error; it is a gap in the policy. An agent that "helpfully" answers *no* here
#   is guessing, and a checker that guesses cannot be audited.
#
# For the governance office: either add "auditors are not clinicians" (then Dee–R1
# becomes *no*), or adopt an explicit default-deny rule — a decision for them, not for
# the model. If any row shows `checked_both == False` with a correct verdict, the agent
# got lucky; the prompt should be tightened, because a one-sided check cannot tell *no*
# from *undetermined*.

# %% [markdown]
# ---
#
# ## Grading rubric
#
# | Part | Problem | Auto | Manual | Pts |
# |---|---|---|---|---|
# | A | A2 Tools, trajectories, and what a mega-tool hides (original Ch 1 A2) | 4 | 4 | 8 |
# | B | B1 Agent, program, program + critic (original Ch 1 D1) | 4 | 6 | 10 |
# | C | C1 Build and evaluate the compliance agent (original Ch 2 D1) | 5 | 7 | 12 |
# | **Total** | | | | **30** |
#
# *Manual* points are for the written answers and for the quality of the engineering evidence (sample sizes, cost, honest negative results).

# %% [markdown]
# ---
#
# ## Self-test
#
# Re-run this cell after finishing. It lists every auto-graded problem and whether its check passed.

# %%
AUTO_GRADED = ['A2', 'B1', 'C1']
_ = GRADER.summary(AUTO_GRADED)

# %% solution
GRADER.assert_all_passed(AUTO_GRADED)
