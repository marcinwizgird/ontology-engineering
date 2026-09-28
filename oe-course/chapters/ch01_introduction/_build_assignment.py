"""Build the Chapter 1 problem set: 05_assignment.ipynb + 05_solutions.ipynb.

Run from anywhere:  python chapters/ch01_introduction/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 1 — Introduction",
    title="Triaging submissions to an ontology registry with Claude",
    coverage=("Keet §1.1 (what an ontology looks like: the vocabulary → taxonomy → "
              "thesaurus → formal-ontology spectrum), §1.2 (why ontologies pay off), §1.3 "
              "(what makes an ontology good or bad); course notebooks 01–04 of this chapter. "
              "Tools: LangChain tool-calling agents, DSPy + GEPA, an LLM judge, "
              "`oe_course.mdp`, `oe_course.skills`, `oe_course.selfimprove`. This is the "
              "course's foundation problem set: every later chapter reuses its discipline."),
    scenario="""
    **Meridian Rail** runs a company-wide **ontology registry**: before a team's vocabulary
    or ontology is published for other systems to depend on, the data architecture office
    reviews it at *intake*. The review answers three questions — where does the submission
    sit on the ontology spectrum, which modelling defects does it have, and is it
    **accepted**, sent back to **revise**, or **rejected** — and ends with a short report to
    the submitting team. The rules are the office's written *intake policy (v3)*, printed
    below. The backlog is 24 submissions from 16 teams and growing; the head of data
    architecture wants to know whether Claude can take over first-line triage, and on what
    evidence. You are the ontology engineer asked to find out. Your brief:

    1. **Pin the task down.** Write the policy's decidable clauses as code, and establish
       what a deterministic reviewer with the registry's tools already achieves. That is
       the control every Claude number is compared with.
    2. **Build the grader first**, with diagnostics an optimiser can act on — and validate
       the LLM judge the office wants to use for the written reports *before* trusting it.
    3. **Build a Claude triage program**, measure it on a development split, improve it with
       GEPA, and report on a **held-out test split** with its cost and its run-to-run noise.
    4. **Decide the architecture**: a single tool-calling agent, or a decomposed pipeline
       with a verifying critic; price evidence-gathering as an MDP; and ship the result as a
       versioned skill behind a gated self-improvement loop.

    The 24 submissions (split 8 / 8 / 8 by submission, each split containing every
    decision and every spectrum level), the board's gold labels, the registry tools and a
    set of reviewer-labelled reports are provided in `ch01_agentic.py`. The gold labels are
    checked against Chapter 1's own spectrum classifier and defect scanner when the
    notebook starts.
    """,
    effort="10–12 hours",
    api_budget=("≈ $8–20 **estimated** on `claude-opus-5` for one full run (≈ 330 DSPy calls "
                "and ≈ 60 agent turns; the two GEPA runs and the noise study are the largest "
                "lines). Nothing in this notebook has been run live by the authors, so these "
                "are estimates from list prices ($5 / $25 per MTok in / out), not measurements "
                "— your `llm.meter` lines are the real numbers. Re-running unchanged cells is "
                "free: DSPy caches identical requests."),
)

ps.setup("""
import re, time
import statistics as st
from typing import Iterable
import dspy
import pandas as pd
import ch01_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents, ontology as ont
from oe_course.skills import Skill
from oe_course.selfimprove import SelfImprovingSkill
pd.set_option("display.width", 140)
pd.set_option("display.max_colwidth", 70)

problems = A.validate_gold()
assert not problems, problems      # the gold labels agree with Chapter 1's engine
train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
ALL = train + dev + test
ROW = {ex.id: ex for ex in ALL}
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}; gold labels validated")
""")

ps.md("""
### The corpus and the policy

One row per submission. `level` and `raw_smells` are what Chapter 1's classifier and
scanner report (validated above); `smells` and `decision` are the review board's gold
answer under the policy.
""")
ps.code("""
print(A.INTAKE_POLICY)
pd.DataFrame([{"id": ex.id, "split": ex.split, "team": ex.team, "declared": ex.declared_level,
               "level": ex.level, "raw_smells": ex.raw_smells, "smells": ex.smells,
               "decision": ex.decision} for ex in ALL])
""")

ps.md(r'''
## Where the submissions live, and how to load them

There are no separate `.ttl` files to download. The 24 submissions are **embedded as
Turtle text** in `ch01_agentic.py` (the list `A.SUBMISSIONS`), so the problem set runs
with no file paths and no triplestore. Each entry is an `A.Submission`; `A.get(id)`
returns one, and its `.turtle` attribute is a complete Turtle document (prefix header
included).

Three ways to load one, from lowest to highest level:

| you want | call | you get |
|---|---|---|
| the raw text | `A.get("safety-incidents").turtle` | `str` (Turtle) |
| an RDF graph to inspect in Python | `ont.load_graph(A.get(id).turtle)` (= `rdflib.Graph().parse(data=..., format="turtle")`) | `rdflib.Graph` |
| everything the tools need | `ws = A.RegistryWorkspace(); ws.load(id)` | `ws.graph` (rdflib) and `ws.store` (a SPARQL store over the same triples) |

The tools never read files: `load_submission(id)` calls `ws.load(id)`, and every other
tool works on `ws.graph` / `ws.store`. Fuseki is not needed; if it is running, nothing
in this problem set uses it.

The next cell prints one submission, loads it three ways, and **exports all 24 as `.ttl`
files** under `course/artifacts/ch01_submissions/`, so you can open them in Protégé or
any RDF editor. Editing those files does not change the corpus; the module is the source
of truth.
''')
ps.code(r'''
from rdflib import Graph

sub = A.get("safety-incidents")
print(sub.turtle)

g = ont.load_graph(sub.turtle)                       # rdflib.Graph
print(f"{len(g)} triples;", ont.classify_spectrum(g)["level"], ";",
      sorted(ont.smell_summary(g)))

ws_src = A.RegistryWorkspace()
ws_src.load(sub.id)                                  # what load_submission does
print(ws_src.store.select("SELECT ?c WHERE { ?c a owl:Class } ORDER BY ?c")[:3])

out_dir = config.artifacts_dir() / "ch01_submissions"
out_dir.mkdir(parents=True, exist_ok=True)
for s in A.SUBMISSIONS:
    (out_dir / f"{s.id}.ttl").write_text(s.turtle, encoding="utf-8")
print(f"\nexported {len(A.SUBMISSIONS)} files to {out_dir}")
''')
ps.md(r'''
## Background — the system you are building

This section explains the moving parts and **why** they are shaped the way they are. The
problems ask you to make design decisions; these are the concepts those decisions are
about.

```
 submission id
      │
      ▼
 RegistryWorkspace ──── holds the loaded ontology (rdflib Graph + SPARQL store) and a call log
      │
      ▼
 registry tools ─────── narrow functions over the workspace: record, metrics, spectrum, scanner, SPARQL
      │   every call is logged
      ├──────────────────────┬───────────────────────────┐
      ▼                      ▼                           ▼
 scripted reviewer      DSPy program                LangChain agent
 (A2: code only)        (B2: fixed tool calls,      (D1: Claude chooses which
                         then ONE Claude call)       tool to call, turn by turn)
      │                      │                           │
      └──────────┬───────────┴───────────────────────────┘
                 ▼
      answer = level, smells, decision, report
                 │
     scorer (B1) compares with the gold labels ──► score + named violations + notes
                 │
     GEPA (C) rewrites the program's instruction from those notes
     judge (B3) grades the free-text report · MDP (D2) prices the evidence
     skill + gate (D3) versions the result and controls how it may change
```

### 1. The task: intake triage

A team submits an ontology; the registry answers four things: its **level** on the
ontology spectrum, the **defects** to report, a **decision**, and a **report** to the
team. The first three follow mechanically from the policy and the tool output; the
fourth is language. That split is the reason the problem set is built the way it is: it
lets you measure exactly how faithfully Claude applies written rules, and shows where a
model adds something code cannot.

The **spectrum classifier** (`ont.classify_spectrum`) is cumulative: any subsumption
(or `skos:broader`) makes a *taxonomy*; SKOS relations (`broader`, `related`, …) make a
*thesaurus*; restrictions, disjointness, equivalence or property characteristics **on
top of a hierarchy** make a *formal-ontology*. The **scanner** (`ont.scan_smells`)
returns one finding per defect instance.

### 2. The workspace — `A.RegistryWorkspace`

A workspace is the **state one review works on**: which submission is loaded (`ws.submission`),
its RDF graph (`ws.graph`), a SPARQL store over it (`ws.store`), and the log of every
tool call made against it (`ws.log`). Think of it as a session or a sandbox.

Why an object instead of global variables:

* **Isolation.** The tools take almost no arguments (`spectrum_position()` means "of the
  loaded submission"), so they need somewhere to find that submission. If that were a
  global, two reviews running at once — or an agent run and your own debugging — would
  overwrite each other. One workspace per review keeps them apart.
* **A record per episode.** The log belongs to the workspace, so one workspace = one
  trajectory = one cost. That is what makes A2's comparison, D1's tool counts and D2's
  replay possible.
* **Reproducibility.** A fresh workspace always starts empty; nothing leaks from the
  previous item.

*Design decisions:* a **fresh workspace per item** when you want per-item trajectories
(A2, D1); a **shared workspace** when you want one log for a whole run, e.g. to cost a
dataset evaluation (`A.gather_evidence(id, ws)` accepts one for this reason).

### 3. Tools and the tool registry — `A.build_registry_tools(ws)`

A **tool** is a Python function wrapped as a LangChain `StructuredTool`: a `name`, a
`description` (the docstring) and an argument schema inferred from the type hints. The
same tool object can be used in three ways:

1. **by your code**: `tool.invoke({"submission_id": "x"})`, a normal function call (A2, B2);
2. **by Claude**: the agent receives each tool's name, description and schema, and
   *decides* which to call and with what arguments (D1);
3. **inside a fixed pipeline**: `A.gather_evidence` calls five tools in a fixed order.

The **tool registry** (or *tool belt*) is simply the list `A.build_registry_tools(ws)`
returns: the actions available to a reviewer, all bound to one workspace. Choosing that
list is a design decision in its own right.

Design choices already made in these tools, and why:

* **Narrow tools** (one measurement each) rather than one `review_everything` tool: the
  trajectory shows *what* evidence a decision used; an agent can be given only what it
  needs (least privilege); outputs stay small, and every agent turn re-sends them.
  `A.build_monolithic_tool` exists so A2 can measure the difference.
* **Descriptions say when to call**, not only what the tool does ("Call this before
  deciding, because …"). A model picks tools from their descriptions; a missing trigger
  sentence means a tool that never gets called.
* **JSON strings in, JSON strings out**: readable by a model, loggable, and identical
  whether a person or a model made the call.
* **Errors come back as text** (`"ERROR: No submission loaded…"`) instead of exceptions,
  so an agent can read the mistake and recover instead of crashing the run.

### 4. The call log — `ws.log`

Every tool is wrapped by `oe_course.tools.instrument`, which records a `ToolCall` (name,
arguments, success, seconds, size of the result) before returning. The log **is** the
agent's trajectory. You read it to cost a run, to see which evidence a decision rested on
(A2), to count tool calls (D1) and to replay an agent's episode inside the MDP (D2).

### 5. Evidence bundle, and "tools measure, the model interprets"

`A.gather_evidence(id)` runs the record, metrics, spectrum and scanner tools and returns
their outputs as one JSON document. The B2 program gives that document to Claude in a
**single** call. The design principle: put measurement in code (exact, free, repeatable)
and use the model only for interpretation and language. It makes the system cheaper and
easier to evaluate, and it leaves exactly one instruction to optimise.

### 6. DSPy — signature, predictor, module

* A **signature** (`class X(dspy.Signature)`) is the typed contract of one LM call:
  input fields, output fields, their descriptions, and an **instruction** (the
  docstring, or `.with_instructions(...)`). It replaces a hand-written prompt string.
* A **predictor** (`dspy.Predict(signature)`) turns the signature into a prompt, makes
  one LM call and parses the reply back into typed fields.
* A **module** (`dspy.Module` with a `forward` method) is your program: ordinary Python
  that calls tools and predictors. Calling it returns a `dspy.Prediction`.

The point of DSPy here: the **instruction is a parameter**, separate from the code, so an
optimiser can rewrite it and you can version, diff and review it like any other artefact.

### 7. Scorer, feedback and rulebook

A **scorer** turns (gold row, prediction) into a `ScoreReport`: a number, a list of
**named violations** (ids from `A.INTAKE_RULEBOOK`) and **notes** that say what was
expected. The number drives evaluation; the ids and notes drive optimisation, because
GEPA can only fix what the feedback names. A scorer that returns only a number gives an
optimiser nothing to act on.

### 8. GEPA

GEPA improves an instruction by **reflection**: it runs the program on a few training
items, collects the metric's feedback text, asks a *reflection LM* to write a better
instruction, and keeps candidates that do best on the validation set. Its budget
(`max_metric_calls`) is the number of program runs it may make; each is a billed call.
It learns only from failures that occur in `train`, which is why the splits matter as
much as the optimiser.

### 9. LLM-as-judge

A judge is a model that scores something no function can, here the written report. A
judge is itself a classifier with errors, so it must be **validated against human labels**
(agreement, κ) before its scores are trusted. B3 does this before anything relies on it.

### 10. Agent loop vs pipeline

An **agent** (D1) is a loop: Claude sees the conversation and the tool schemas, either
requests a tool call or answers; each tool result is appended and the loop repeats (up to
25 steps here). It is flexible, since the order of work can depend on what it finds, but
each turn re-sends the whole transcript, the trajectory varies from run to run, and it can
skip evidence. A **pipeline** fixes the order in code; a **critic** is a pipeline stage
that checks the model's claims against raw tool output. Use an agent only when the order
of work genuinely depends on intermediate results.

### 11. MDP

Formalising the review as a Markov decision process (states = evidence held, actions =
tool calls or *submit*, reward = answer quality minus a cost per call) turns "is the agent
efficient?" into arithmetic: solve for the optimal value V\*, and an agent's **regret** is
how far below V\* its actual trajectory scored.

### 12. Skill and gated self-improvement

A **skill** bundles an instruction with the tools it assumes, the data it is measured on
and the metric, and versions them together, so a change in the prompt always travels with
the evidence for it. **Self-improvement** means mining the skill's own failures,
re-optimising, and **promoting a new version only if it beats the current one by a margin
on a holdout the optimiser never saw**. Without that gate, "self-improving" means drifting
while confidently reporting progress.
''')

ps.md(r'''
## Reference — data, types and APIs used in this problem set

Read this once before Part A, and come back to it whenever a contract below names a type.
Every problem also has its own **Contract** block, just before its TODO cell, with the
exact signatures, what each parameter is, what must be returned, and which variables the
check cell reads.

### Type notation

`list[str]` a Python list of strings · `frozenset[str]` an immutable set ·
`dict[str, bool]` a dict with string keys and bool values · `Iterable[str]` anything you
can loop over (list, set, tuple, `pd.Series`) · `T | None` a `T` or `None` ·
`pd.DataFrame` a pandas table (column names given in each contract).

### Dataset rows — `train`, `dev`, `test`, `ALL`, `ROW`

`train`, `dev` and `test` are `list[dspy.Example]` (8 each); `ALL = train + dev + test`
(24); `ROW` is `dict[str, dspy.Example]` keyed by submission id. Read fields as
attributes (`ex.level`) or keys (`ex["level"]`). **The input** is `submission` — that is
what `program(**ex.inputs())` passes; everything else is a gold label or metadata.

| field | type | example | meaning |
|---|---|---|---|
| `id`, `submission` | `str` | `"safety-incidents"` | the submission id (same value; `submission` is the program input) |
| `split` | `str` | `"train"` | `"train"`, `"dev"` or `"test"` |
| `team` | `str` | `"Safety & Incidents"` | submitting team |
| `declared_level` | `str` | `"formal-ontology"` | what the team *claims* on the intake form |
| `level` | `str` | `"formal-ontology"` | gold: what the spectrum classifier *measures* |
| `raw_smells` | `list[str]`, sorted | `["missing-label", "property-without-domain-or-range"]` | gold: every smell id the scanner finds |
| `smells` | `list[str]`, sorted | same, minus waived ids | gold: what the policy says must be *reported* |
| `decision` | `str` | `"revise"` | gold: `"accept"`, `"revise"` or `"reject"` |
| `note` | `str` | | why the board labelled it so (do not use it as model input) |

### Constants

| name | value |
|---|---|
| `ont.SPECTRUM_LEVELS` | `["controlled-vocabulary", "taxonomy", "thesaurus", "formal-ontology"]` — **ordered** from least to most formal |
| `A.DECISIONS` | `["accept", "revise", "reject"]` |
| `A.BLOCKING_SMELLS` | `frozenset({"subsumption-cycle", "class-as-individual", "individual-as-class", "undeclared-term"})` |
| `A.WAIVABLE_AT` | `frozenset({"controlled-vocabulary", "thesaurus"})` — measured levels at which `no-disjointness` is waived (W1) |
| `A.EVIDENCE_KINDS` | `["record", "metrics", "spectrum", "smells", "catalogue", "sparql"]` |
| `A.TOOL_TO_EVIDENCE` | `dict[str, str]`: tool name → evidence kind (`"scan_smells" → "smells"`, …); tools not listed buy nothing |
| `A.INTAKE_RULEBOOK` | `RuleBook` of 7 `Rule(id, description)`; `A.INTAKE_RULEBOOK.ids` is the ordered id list; `"x" in A.INTAKE_RULEBOOK` |

**The seven scanner smell ids** (`ont.SMELL_IDS`): `subsumption-cycle`,
`class-as-individual`, `individual-as-class`, `undeclared-term` (these four are
blocking), `property-without-domain-or-range`, `no-disjointness`, `missing-label`.

### Registry tools — `A.build_registry_tools(ws)`

`ws = A.RegistryWorkspace()` is a fresh, empty workspace with its own call log `ws.log`.
`A.build_registry_tools(ws)` returns a `list` of LangChain tools bound to `ws`; index them
with `tools = {t.name: t for t in A.build_registry_tools(ws)}`. Call a tool with
**`tools[name].invoke({arg: value})`** (`{}` for no arguments). Every tool returns a
**JSON string** — decode it with `json.loads`. A tool that fails returns a string starting
with `"ERROR:"` and the call is logged with `ok=False`. Call `load_submission` first.

| tool | arguments | returns (after `json.loads`) |
|---|---|---|
| `load_submission` | `submission_id: str` | `{"loaded": "safety-incidents", "triples": 15}` |
| `submission_record` | — | `{"submission": ..., "team": ..., "declared_level": "formal-ontology", "purpose": ...}` |
| `graph_metrics` | — | `{"classes": 5, "subclass_axioms": 3, "disjointness_axioms": 1, "labels": 5, ...}` (17 counts) |
| `spectrum_position` | — | `{"level": "formal-ontology", "evidence": ["5 classes, 5 labels -> ...", ...]}` |
| `scan_smells` | — | `[{"smell": "missing-label", "subject": "<IRI>", "detail": "..."}, ...]` — one entry **per finding** (an id can repeat) |
| `smell_catalogue` | — | `[{"id": ..., "title": ..., "why": ...}, ...]` |
| `sparql_select` | `query: str` | `list[dict]` (≤ 100 rows) |
| `sparql_ask` | `query: str` | `{"answer": true}` |
| `list_submissions` | — | `list[str]` of ids |

`A.build_monolithic_tool(ws)` returns a one-element list holding `review_submission(submission_id)`,
which returns everything at once.

**The call log.** `ws.log` is a `ToolCallLog`: `ws.log.calls` is a `list[ToolCall]`; each
`ToolCall` has `name: str`, `args: dict`, `ok: bool`, `seconds: float`,
`result_chars: int`, `error: str`. `ws.log.names()` is the list of tool names in call order.

### The evidence bundle — `A.gather_evidence(submission_id, ws=None) -> str`

Runs `load_submission`, `submission_record`, `graph_metrics`, `spectrum_position`,
`scan_smells` (five logged calls, in `ws` if you pass one) and returns **JSON text**:

```
{"submission":       {"submission": str, "team": str, "declared_level": str, "purpose": str},
 "metrics":          {"classes": int, "subclass_axioms": int, ...},
 "spectrum":         {"level": str, "evidence": [str, ...]},
 "scanner_findings": [{"smell": str, "subject": str, "detail": str}, ...]}
```

### Course library calls used here

| call | returns / notes |
|---|---|
| `ev.ScoreReport(score, notes, violated)` | `score: float` in [0, 1]; `notes: list[str]`; `violated: list[str]` of rulebook ids |
| `ev.parse_label_list(value)` | `list[str]` from a list, a JSON array string `'["a","b"]'`, a comma/space-separated string, or `None` → `[]` |
| `ev.set_f1(predicted, gold)` | `(precision, recall, f1)` floats over two iterables of labels; both empty → `(1.0, 1.0, 1.0)` |
| `ev.evaluate_dataset(program, dataset, scorer)` | `{"mean_score": float, "n": int, "violations": {rule_id: count}, "rows": [{"item": id, "score": float, "violated": [...]}]}` — one LM call per row |
| `ev.make_gepa_metric(scorer, rulebook)` | a GEPA metric: `(gold, pred, trace=None, pred_name=None, pred_trace=None) -> dspy.Prediction(score=..., feedback=...)` |
| `ev.judge(task, gold, report)` | `ScoreReport` from the configured DSPy LM: `.score` in [0, 1], `.notes[0]` the critique. One billed call |
| `llm.configure_dspy()` | installs Claude as DSPy's default LM and returns it (`lm`) |
| `llm.dspy_lm(cache=False)` / `llm.reflection_lm()` | a separate `dspy.LM` (uncached / for GEPA reflection) |
| `with llm.meter(lm, ...) as cost:` | after the block, `cost == {"calls": int, "input_tokens": int, "output_tokens": int, "usd": float}` |
| `llm.chat_usage(messages)` | `{"model_turns", "input_tokens", "output_tokens", "usd_estimate"}` for a LangChain transcript |
| `opt.run_gepa(program, trainset, metric, *, valset, max_metric_calls, reflection_lm)` | the optimised program (a `dspy.Module`) |
| `opt.compare(before, after, dataset, scorer)` | `OptimisationResult`: `.before` / `.after` (evaluate_dataset dicts), `.instruction_before`, `.instruction_after`, `.delta`, `.report()` |
| `opt.instruction_of(program)` | the instruction text of a single-predictor program |
| `agents.build_agent(ws, system_prompt=..., tools=...)` | `(agent, ws)` — a LangChain tool-calling agent on Claude |
| `agents.run_agent(agent, ws, task)` | `AgentRun`: `.answer` (final text), `.messages` (transcript), `.log` (= `ws.log`) |
| `config.artifacts_dir()` | `Path` to `course/artifacts/` (created on first use) |

The MDP (`mdp`) and skill (`Skill`, `SelfImprovingSkill`) APIs are described in the D2 and
D3 contracts, where they are used.

Run the next cell to see a real row, real tool output and a real evidence bundle — no API
calls are made.
''')
ps.code(r'''
ex = ROW["safety-incidents"]
print("row:", {k: ex[k] for k in ("id", "declared_level", "level", "raw_smells", "smells", "decision")})
print("program input:", ex.inputs())

ws_ref = A.RegistryWorkspace()
tools_ref = {t.name: t for t in A.build_registry_tools(ws_ref)}
print("\nload_submission ->", tools_ref["load_submission"].invoke({"submission_id": ex.id}))
print("spectrum_position ->", json.loads(tools_ref["spectrum_position"].invoke({}))["level"])
print("scan_smells ->", [f["smell"] for f in json.loads(tools_ref["scan_smells"].invoke({}))])
print("log ->", [(c.name, c.ok, c.result_chars) for c in ws_ref.log.calls])

evidence_ref = json.loads(A.gather_evidence(ex.id))
print("\nevidence keys:", list(evidence_ref), "| declared:", evidence_ref["submission"]["declared_level"])
''')

# =========================================================================== #
ps.part("A", "The task, its tools, and a deterministic control", """
Before a model is involved, pin down what the task *is*. Three clauses of the policy are
decidable from tool output; one (the report) is not. Coding the decidable ones gives you
a reference implementation, a way to validate the gold labels, and the control that any
Claude system must be compared with.
""")

ps.problem("A1", "The intake policy as code", 10, """
Implement, from the policy text (not from the gold labels):

* `reportable_smells(raw, measured_level) -> list[str]` — clause 2: the sorted scanner
  ids that must be reported, after waiver W1;
* `intake_decision(reported, declared_level, measured_level) -> str` — clause 3:
  `"accept"`, `"revise"` or `"reject"`. Use `ont.SPECTRUM_LEVELS` for the level order.

The check runs both on all 24 submissions against the board's labels, and on edge cases
the corpus does not contain.

In writing: (a) the policy keys waiver W1 on the *measured* level, not the declared one —
give the argument for that choice, and one submission in the corpus whose decision would
change if it were keyed on the declared level; (b) name one question the policy text
leaves open that you had to decide in code; (c) what does this exercise tell you about
asking an LLM to "apply the policy"?
""", auto_points=6)
ps.md(r'''
#### Background and design decisions — A1

You are turning prose into a **reference implementation**. It serves three purposes
later: it validates the gold labels, it becomes the deterministic *control* (A2), and it
is the engine of the critic (D1) and the MDP (D2). So it must follow the **policy text**,
not the labels. If you tune it until the labels match, you can no longer detect a wrong
label.

Decisions you make:

* **Which level the waiver keys on.** The policy says *measured*; the written part asks
  you to argue why that is the right design, not merely what the text says.
* **Rule order.** Clause 3 is ordered: *reject* beats *revise* beats *accept*. Encoding it
  as ordered checks makes the precedence explicit; a points-based encoding hides it.
* **Level comparison.** "Below the declared level" needs an order; derive it from
  `ont.SPECTRUM_LEVELS` rather than hard-coding one, so the policy and the classifier
  cannot drift apart.
* **Purity.** No tools and no model inside these functions: they are called hundreds of
  times in D2, and they must give the same answer every time.
''')
ps.md(r'''
#### Contract — A1

```python
def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]
def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str
```

**`reportable_smells`** — policy clause 2.

| parameter | type | value in the corpus | meaning |
|---|---|---|---|
| `raw` | `Iterable[str]` (list or set) | `ex.raw_smells` | smell ids the scanner found |
| `measured_level` | `str`, one of `ont.SPECTRUM_LEVELS` | `ex.level` | the level the classifier measured |

Returns a **sorted `list[str]`** with no duplicates: every id in `raw`, except
`"no-disjointness"` when `measured_level` is in `A.WAIVABLE_AT`. Never add an id that is
not in `raw`; do not modify `raw`. The check compares with `==` against `ex.smells`, so a
set or an unsorted list fails.

**`intake_decision`** — policy clause 3.

| parameter | type | value in the corpus | meaning |
|---|---|---|---|
| `reported` | `Iterable[str]` | output of `reportable_smells` | the smells being reported (already waived) |
| `declared_level` | `str` | `ex.declared_level` | what the team claimed |
| `measured_level` | `str` | `ex.level` | what the classifier measured |

Returns exactly one of `"accept"`, `"revise"`, `"reject"`, decided **in this order**:
`"reject"` if `reported` contains any id in `A.BLOCKING_SMELLS`; else `"revise"` if
`reported` is non-empty **or** `measured_level` comes *before* `declared_level` in
`ont.SPECTRUM_LEVELS`; else `"accept"`.

| call | returns |
|---|---|
| `reportable_smells({"no-disjointness", "missing-label"}, "controlled-vocabulary")` | `["missing-label"]` |
| `reportable_smells(["no-disjointness"], "formal-ontology")` | `["no-disjointness"]` |
| `intake_decision(["subsumption-cycle", "missing-label"], "formal-ontology", "taxonomy")` | `"reject"` |
| `intake_decision([], "thesaurus", "taxonomy")` | `"revise"` (over-promises) |
| `intake_decision([], "controlled-vocabulary", "formal-ontology")` | `"accept"` (exceeds the declaration) |

Both functions are pure: no tools, no model. Later problems (A2, D1, D2) reuse them.
''')
ps.todo(
    stub="""
    def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]:
        \"\"\"Policy clause 2 (see Contract A1): sorted reportable smell ids after waiver W1.\"\"\"
        # TODO
        raise NotImplementedError

    def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str:
        \"\"\"Policy clause 3 (see Contract A1): "accept", "revise" or "reject".\"\"\"
        # TODO
        raise NotImplementedError
    """,
    solution="""
    RANK = {level: i for i, level in enumerate(ont.SPECTRUM_LEVELS)}

    def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]:
        smells = set(raw)
        if measured_level in A.WAIVABLE_AT:          # W1: navigation vocabularies
            smells.discard("no-disjointness")
        return sorted(smells)

    def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str:
        reported = set(reported)
        if reported & A.BLOCKING_SMELLS:
            return "reject"
        if reported or RANK[measured_level] < RANK[declared_level]:
            return "revise"
        return "accept"

    for ex in ALL:
        mine = reportable_smells(ex.raw_smells, ex.level)
        print(f"{ex.id:28s} {intake_decision(mine, ex.declared_level, ex.level):7s} {mine}")
    """)
ps.check("A1", """
for ex in ALL:
    mine = reportable_smells(ex.raw_smells, ex.level)
    assert mine == ex.smells, (ex.id, mine, ex.smells)
    assert intake_decision(mine, ex.declared_level, ex.level) == ex.decision, ex.id
assert reportable_smells({"no-disjointness", "missing-label"}, "controlled-vocabulary") == ["missing-label"]
assert reportable_smells({"no-disjointness"}, "formal-ontology") == ["no-disjointness"]
assert intake_decision([], "controlled-vocabulary", "formal-ontology") == "accept"    # exceeds declaration
assert intake_decision(["undeclared-term"], "taxonomy", "formal-ontology") == "reject"
assert intake_decision(["missing-label"], "taxonomy", "taxonomy") == "revise"
assert intake_decision(["subsumption-cycle", "missing-label"], "formal-ontology", "taxonomy") == "reject"
assert intake_decision([], "thesaurus", "taxonomy") == "revise"                        # over-promises
""")
ps.written("""
**(a) Measured, not declared.** The waiver exists because a navigation vocabulary makes no
disjointness commitment; whether a submission *is* such a vocabulary is a fact about the
artefact, which the classifier measures, not about the form. Keying it on the declaration
would let any team silence a defect by ticking "thesaurus". The corpus contains exactly
that case: **customer-complaints** declares *thesaurus* but has no SKOS relations
(measured *taxonomy*); keyed on the declaration, `no-disjointness` would be waived and
the decision would still be *revise* only because of the over-promise — while
**accessibility-services** (declared *taxonomy*, measured *thesaurus*) would lose its
waiver and flip from *accept* to *revise*.

**(b) Open questions** a good answer names one of: does a submission that *exceeds* its
declaration need correcting (the policy says accept, but the registry entry is then
wrong the other way); are duplicate findings of the same id one defect or several (the
scanner reports `property-without-domain-or-range` twice for *station-assets*; the
policy talks about ids); when a blocking and a non-blocking defect co-occur, must the
report still list both (yes — clause 2 is independent of clause 3). Each is a decision
the code makes silently and a model makes differently on different days.

**(c)** Three of four clauses are decidable, and the deterministic version is exact,
free and auditable. An LLM asked to "apply the policy" is being asked to re-implement
this function from prose, probabilistically. That is worth doing only for what cannot be
coded — here the report — or when the policy is too large or too fluid to code; and the
coded clauses are then the ideal *test* of whether the model follows written rules.
""")

ps.problem("A2", "Tools, trajectories, and what a mega-tool hides", 8, """
The registry tools (`A.build_registry_tools(ws)`) are narrow and logged: every call lands
in `ws.log` (a `ToolCallLog`). `A.TOOL_TO_EVIDENCE` names the kind of evidence each tool
buys.

1. Write `evidence_from_log(log) -> frozenset` — the evidence kinds a trajectory bought.
2. Write `scripted_review(submission_id, ws) -> dict` with keys `level`, `smells`,
   `decision`: a *deterministic reviewer* that invokes (with `.invoke`) only the registry
   tools it needs and applies your A1 functions. Run it on all 24 submissions, each in a
   fresh workspace, and set `control_accuracy` to the fraction it gets fully right.
3. Build `a2`, one row per toolset for the submission `"interlocking-import"`: the
   decomposed trajectory of your scripted reviewer and one call of the monolithic
   `A.build_monolithic_tool(ws)`; columns `toolset` (`"decomposed"` / `"monolithic"`),
   `calls`, `result_chars` (sum over the log), `evidence_visible`
   (`sorted(evidence_from_log(...))`).

In writing: what does the monolithic tool cost you — think of the trajectory as a record,
of reward shaping, and of least privilege — and when would you still ship one? Read the
tool descriptions in `ch01_agentic.py`: which sentence in `submission_record`'s description
makes an agent call it, and what would happen if it were missing?
""", auto_points=4)
ps.md(r'''
#### Background and design decisions — A2

This is where you meet the **workspace** and the **tool registry** (Background §2–4) as
a user. Build the tools on a workspace, call them with `.invoke`, decode the JSON, and
look at `ws.log`. The scripted reviewer shows what the task costs *without any model*: if
code gets 24/24 with four calls, every Claude result later is measured against that.

Decisions you make:

* **Which tools to call.** Only what the policy needs: the record (declared level), the
  spectrum (measured level), the scanner. `graph_metrics` is not needed to decide; every
  extra call is cost and noise in the trajectory.
* **A fresh workspace per submission**, so each log is one clean trajectory and nothing
  from the previous item leaks into the next.
* **What counts as evidence.** `evidence_from_log` counts only successful calls: a failed
  call bought nothing. `load_submission` buys no evidence; it only makes the others
  possible.
* **Narrow vs monolithic.** The monolithic tool is *one* call that returns everything,
  so the log cannot say what the decision used. The written part asks when you would still
  ship one.
''')
ps.md(r'''
#### Contract — A2

```python
def evidence_from_log(log: ToolCallLog) -> frozenset[str]
def scripted_review(submission_id: str, ws: A.RegistryWorkspace) -> dict
control_accuracy: float
a2: pd.DataFrame
```

**`evidence_from_log(log)`** — `log` is a workspace's `ws.log`. Loop over `log.calls`;
for every call with `ok == True` whose `name` is a key of `A.TOOL_TO_EVIDENCE`, collect
`A.TOOL_TO_EVIDENCE[name]`. Return the kinds as a `frozenset[str]` (a subset of
`A.EVIDENCE_KINDS`). Example: a log of `load_submission, spectrum_position, scan_smells`
→ `frozenset({"spectrum", "smells"})`.

**`scripted_review(submission_id, ws)`** — a deterministic reviewer, no model.

| parameter | type | meaning |
|---|---|---|
| `submission_id` | `str` | e.g. `"signalling-equipment"` |
| `ws` | `A.RegistryWorkspace` | a **fresh** workspace; build the tools on it so every call lands in `ws.log` |

It must call `load_submission` first, then only the tools whose output it needs
(`submission_record` for the declared level, `spectrum_position`, `scan_smells`), **at
most 5 calls in total, none failing**. Returns a dict with **exactly** these three keys
(the check compares the whole dict with `==`):

```python
{"level": "taxonomy",                                   # str, the measured level
 "smells": ["no-disjointness", "subsumption-cycle"],    # reportable_smells(...) output
 "decision": "reject"}                                  # intake_decision(...) output
```

Remember that `scan_smells` returns one entry per finding, so collect the `"smell"` values
into a set before calling `reportable_smells`.

**`control_accuracy`** — `float` in [0, 1]: over all 24 rows of `ALL`, the fraction for
which `scripted_review(ex.id, A.RegistryWorkspace()) == {"level": ex.level, "smells":
ex.smells, "decision": ex.decision}`.

**`a2`** — a 2-row DataFrame for submission `"interlocking-import"`:

| column | type | meaning |
|---|---|---|
| `toolset` | `str` | `"decomposed"` (your `scripted_review`) or `"monolithic"` (one `review_submission` call) |
| `calls` | `int` | `len(ws.log.calls)` for that toolset's workspace |
| `result_chars` | `int` | `sum(c.result_chars for c in ws.log.calls)` |
| `evidence_visible` | `list[str]` | `sorted(evidence_from_log(ws.log))` |

Use a separate fresh workspace for each row. The monolithic tool is
`A.build_monolithic_tool(ws)[0].invoke({"submission_id": "interlocking-import"})`.
''')
ps.code("""
ws_demo = A.RegistryWorkspace()
for t in A.build_registry_tools(ws_demo):
    params = list(t.args_schema.model_json_schema().get("properties", {}))
    print(f"{t.name:18s} {str(params):18s} {t.description.splitlines()[0][:80]}")
""")
ps.todo(
    stub="""
    def evidence_from_log(log) -> frozenset[str]:
        \"\"\"Evidence kinds bought by the ok calls in a ToolCallLog (see Contract A2).\"\"\"
        # TODO
        raise NotImplementedError

    def scripted_review(submission_id: str, ws) -> dict:
        tools = {t.name: t for t in A.build_registry_tools(ws)}
        \"\"\"Deterministic review -> {"level", "smells", "decision"} (see Contract A2).\"\"\"
        # TODO: invoke only the tools you need, then apply reportable_smells / intake_decision
        raise NotImplementedError

    control_accuracy = None   # TODO
    a2 = None                 # TODO
    """,
    solution="""
    def evidence_from_log(log) -> frozenset[str]:
        return frozenset(A.TOOL_TO_EVIDENCE[c.name] for c in log.calls
                         if c.ok and c.name in A.TOOL_TO_EVIDENCE)

    def scripted_review(submission_id: str, ws) -> dict:
        tools = {t.name: t for t in A.build_registry_tools(ws)}
        tools["load_submission"].invoke({"submission_id": submission_id})
        record = json.loads(tools["submission_record"].invoke({}))
        level = json.loads(tools["spectrum_position"].invoke({}))["level"]
        raw = {f["smell"] for f in json.loads(tools["scan_smells"].invoke({}))}
        smells = reportable_smells(raw, level)
        return {"level": level, "smells": smells,
                "decision": intake_decision(smells, record["declared_level"], level)}

    hits = []
    for ex in ALL:
        out = scripted_review(ex.id, A.RegistryWorkspace())
        hits.append(out == {"level": ex.level, "smells": ex.smells, "decision": ex.decision})
    control_accuracy = sum(hits) / len(hits)
    print(f"deterministic control: {sum(hits)}/{len(hits)} fully correct")

    ws_d, ws_m = A.RegistryWorkspace(), A.RegistryWorkspace()
    scripted_review("interlocking-import", ws_d)
    A.build_monolithic_tool(ws_m)[0].invoke({"submission_id": "interlocking-import"})
    a2 = pd.DataFrame([
        {"toolset": name, "calls": len(ws.log.calls),
         "result_chars": sum(c.result_chars for c in ws.log.calls),
         "evidence_visible": sorted(evidence_from_log(ws.log))}
        for name, ws in [("decomposed", ws_d), ("monolithic", ws_m)]])
    print("trajectory:", " -> ".join(ws_d.log.names()))
    a2
    """)
ps.check("A2", """
ws_c = A.RegistryWorkspace()
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
""")
ps.written("""
The deterministic control is **24/24** with four tool calls and no model. Everything
Claude does on the structured fields later is measured against that — the honest framing
of the whole problem set is "how faithfully does a model apply a written policy from
evidence", which matters because real policies have clauses that cannot be coded, and
the coded clauses are the only place where faithfulness can be measured exactly.

**What the mega-tool costs.** (i) *Record*: the log shows one opaque call, so you cannot
tell afterwards which evidence the decision rested on — `evidence_visible` is empty.
(ii) *Reward shaping*: the MDP in Part D charges and credits evidence kinds; a single
call that buys everything cannot be priced, so "gathered too much" is invisible. (iii)
*Least privilege and cost*: it returns the whole catalogue and all metrics every time
(several times the characters of the narrow trajectory), which is paid in input tokens
on every agent turn. It is still the right design when the combined call is the only
unit that is ever used, when latency per round-trip dominates, or for a trusted batch
job that is not an agent.

**Trigger sentences.** `submission_record` says *"Call this before deciding, because the
decision compares the measured level with the level the team declared."* Models select
tools from descriptions; without the *when* and *why*, an agent that has spectrum and
scanner output will usually decide without the form and get every over-promising
submission (e.g. *rostering-roles*, *network-routes*) wrong — the decision needs the
declared level and nothing else in the tool belt provides it.
""")

# =========================================================================== #
ps.part("B", "Build the grader, the Claude program, and validate the judge", """
The guidelines a scorer can report are in `A.INTAKE_RULEBOOK` — ids plus the sentence
GEPA's reflection step will read:
""")
ps.code("""
for rule in A.INTAKE_RULEBOOK:
    print(f"{rule.id:24s} {rule.description[:95]}")
""")

ps.problem("B1", "A diagnostic triage scorer", 12, """
Implement `intake_scorer(gold, pred) -> ev.ScoreReport`. `gold` is a dataset row
(`level`, `raw_smells`, `smells`, `decision`); `pred` has `level`, `smells` (anything
`ev.parse_label_list` accepts), `decision`, `report`.

`score = 0.3 * level_ok + 0.4 * smell_f1 + 0.3 * decision_ok`, where level and decision
are compared after `strip().lower()`, and `smell_f1` is `ev.set_f1(pred, gold.smells)`.
Violations (list them in `A.INTAKE_RULEBOOK` order, without duplicates):

| condition | violated |
|---|---|
| level or decision not in the allowed labels | `use-label-vocabulary` |
| a valid level, but wrong | `cite-spectrum-evidence` |
| a gold smell not reported | `report-all-smells` |
| a reported smell the scanner found but the policy waives | `apply-waivers` |
| a reported smell the scanner did not find | `no-unsupported-claims` |
| a valid decision, but wrong | `decide-by-policy` |
| an empty report (no score change) | `ground-in-tool-output` |

`notes` must say what was expected for every wrong field — that text is what GEPA reads.
Why separate `apply-waivers` from `no-unsupported-claims`? Both are "reported something
not in gold", but they call for different fixes, and feedback that cannot tell them
apart cannot teach either.
""", auto_points=10)
ps.md(r'''
#### Background and design decisions — B1

The scorer is the most reused piece of the problem set: it grades the baseline, it is
GEPA's objective, it scores the agent, and it is the MDP's reward. Its **notes** are also
what GEPA's reflection reads (Background §7–8), so write them for a reader who will
rewrite the prompt.

Decisions you make:

* **Weights.** 0.3 / 0.4 / 0.3 is given; notice what it implies: a perfect decision with
  the wrong level still earns 0.7.
* **Partial credit for smells** via F1 rather than all-or-nothing: an optimiser gets a
  gradient (reporting 2 of 3 defects beats reporting none), and precision and recall
  errors stay separate.
* **Normalisation.** Accept `" Taxonomy "` but not `"hierarchy"`: be tolerant about
  format and strict about vocabulary.
* **Distinct violation ids for distinct fixes**: `apply-waivers` (knows the scanner, not
  the policy) versus `no-unsupported-claims` (invents defects). If the feedback merges
  them, the optimiser cannot learn either fix.
* **The report does not change the score** but still records a violation: the report is
  graded elsewhere (B3); here you only notice that it is missing.
''')
ps.md(r'''
#### Contract — B1

```python
WEIGHTS = {"level": 0.3, "smells": 0.4, "decision": 0.3}
def intake_scorer(gold: dspy.Example, pred) -> ev.ScoreReport
```

| parameter | type | fields read | meaning |
|---|---|---|---|
| `gold` | `dspy.Example` (a dataset row) | `level`, `raw_smells`, `smells`, `decision` | the board's answer |
| `pred` | any object with attributes (usually `dspy.Prediction`) | `level`, `smells`, `decision`, `report` | the system's answer |

**Read `pred` defensively**: a field may be missing, `None`, or oddly formatted. Use
`getattr(pred, "level", "")`; normalise `level` and `decision` with
`str(...).strip().lower()`; parse `smells` with `ev.parse_label_list(...)` (it accepts a
list, a JSON string such as `'["a", "b"]'`, a comma-separated string, or `None`); treat
`report` as empty when `str(...).strip() == ""`.

**Returns** `ev.ScoreReport(score, notes, violated)`:

* `score: float` = `0.3 * level_ok + 0.4 * smell_f1 + 0.3 * decision_ok`, where `level_ok`
  and `decision_ok` are 1.0 or 0.0 and `smell_f1 = ev.set_f1(pred_smells, gold.smells)[2]`.
  The report never changes the score.
* `violated: list[str]` — the rule ids from the table in the brief, **each at most once,
  in `A.INTAKE_RULEBOOK.ids` order**. Only the ids in that rulebook are allowed.
* `notes: list[str]` — one sentence per wrong field that states the **expected** value
  (for example the correct decision); a final summary line is fine.

How to split "reported something not in gold": let `extra = pred_smells - set(gold.smells)`.
Ids in `extra ∩ gold.raw_smells` were found but waived → `apply-waivers`; ids in
`extra - gold.raw_smells` were never found → `no-unsupported-claims`.

| gold row | prediction | score | violated |
|---|---|---|---|
| `signalling-equipment` | perfect | 1.0 | `[]` |
| same | `level="hierarchy"` | 0.7 | `["use-label-vocabulary"]` |
| same | `smells=["subsumption-cycle"]` (misses one of two) | 0.3 + 0.4·(2/3) + 0.3 | `["report-all-smells"]` |
| same | perfect, but `report="  "` | 1.0 | `["ground-in-tool-output"]` |
''')
ps.todo(
    stub="""
    WEIGHTS = {"level": 0.3, "smells": 0.4, "decision": 0.3}

    def intake_scorer(gold: dspy.Example, pred) -> ev.ScoreReport:
        \"\"\"0.3*level + 0.4*smell F1 + 0.3*decision, with rulebook violations (see Contract B1).\"\"\"
        # TODO
        raise NotImplementedError
    """,
    solution="""
    WEIGHTS = {"level": 0.3, "smells": 0.4, "decision": 0.3}

    def intake_scorer(gold: dspy.Example, pred) -> ev.ScoreReport:
        level = str(getattr(pred, "level", "") or "").strip().lower()
        decision = str(getattr(pred, "decision", "") or "").strip().lower()
        smells = set(ev.parse_label_list(getattr(pred, "smells", None)))
        report = str(getattr(pred, "report", "") or "").strip()
        notes, violated = [], set()

        level_ok = float(level == gold.level)
        if level not in ont.SPECTRUM_LEVELS:
            violated.add("use-label-vocabulary")
            notes.append(f"Level {level!r} is not a spectrum level; expected {gold.level!r}.")
        elif not level_ok:
            violated.add("cite-spectrum-evidence")
            notes.append(f"Level {level!r} is wrong: the classifier measured {gold.level!r}.")

        _, _, f1 = ev.set_f1(smells, gold.smells)
        missed = sorted(set(gold.smells) - smells)
        extra = smells - set(gold.smells)
        waived = sorted(extra & set(gold.raw_smells))
        invented = sorted(extra - set(gold.raw_smells))
        if missed:
            violated.add("report-all-smells")
            notes.append(f"Defects found by the scanner but not reported: {missed}.")
        if waived:
            violated.add("apply-waivers")
            notes.append(f"Reported {waived}, which the policy waives at level {gold.level!r}.")
        if invented:
            violated.add("no-unsupported-claims")
            notes.append(f"Reported {invented}, which the scanner did not find.")

        decision_ok = float(decision == gold.decision)
        if decision not in A.DECISIONS:
            violated.add("use-label-vocabulary")
            notes.append(f"Decision {decision!r} is not one of {A.DECISIONS}; "
                         f"expected {gold.decision!r}.")
        elif not decision_ok:
            violated.add("decide-by-policy")
            notes.append(f"Decision {decision!r} is wrong; the policy gives {gold.decision!r}.")

        if not report:
            violated.add("ground-in-tool-output")
            notes.append("No report to the submitting team.")

        score = (WEIGHTS["level"] * level_ok + WEIGHTS["smells"] * f1
                 + WEIGHTS["decision"] * decision_ok)
        notes.append(f"level={level_ok:.0f} smell_f1={f1:.2f} decision={decision_ok:.0f}")
        order = A.INTAKE_RULEBOOK.ids
        return ev.ScoreReport(score, notes, [r for r in order if r in violated])
    """)
ps.check("B1", """
P = lambda **kw: dspy.Prediction(**{"level": "taxonomy", "decision": "reject", "report": "r",
                                    "smells": ["subsumption-cycle", "no-disjointness"], **kw})
sig, thes = ROW["signalling-equipment"], ROW["timetable-service-thesaurus"]
cases = [
    (sig, P(), 1.0, []),
    (sig, P(level=" Taxonomy ", smells='["no-disjointness", "subsumption-cycle"]'), 1.0, []),
    (sig, P(level="hierarchy"), 0.7, ["use-label-vocabulary"]),
    (sig, P(level="thesaurus"), 0.7, ["cite-spectrum-evidence"]),
    (sig, P(smells=["subsumption-cycle"]), 0.3 + 0.4 * 2 / 3 + 0.3, ["report-all-smells"]),
    (sig, P(smells=["subsumption-cycle", "no-disjointness", "missing-label"]), 0.92,
     ["no-unsupported-claims"]),
    (sig, P(decision="revise"), 0.7, ["decide-by-policy"]),
    (sig, P(decision="REJECTED"), 0.7, ["use-label-vocabulary"]),
    (sig, P(report="  "), 1.0, ["ground-in-tool-output"]),
    (thes, P(level="thesaurus", smells=["no-disjointness"], decision="accept"), 0.6,
     ["apply-waivers"]),
    (thes, P(level="taxonomy", smells=["no-disjointness", "missing-label"], decision="revise", report=""),
     0.0, ["cite-spectrum-evidence", "apply-waivers", "no-unsupported-claims",
           "decide-by-policy", "ground-in-tool-output"]),
]
for gold, pred, score, violated in cases:
    r = intake_scorer(gold, pred)
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (gold.id, dict(pred), r.score, r.violated)
    assert all(v in A.INTAKE_RULEBOOK for v in r.violated)
r = intake_scorer(sig, P(decision="revise"))
assert any("reject" in n for n in r.notes), "say what was expected"
""")

ps.problem("B2", "The Claude triage program, and its baseline", 10, """
Tools measure, the model interprets: the program gathers evidence deterministically
(`A.gather_evidence(submission)` — record, metrics, spectrum, scanner findings) and makes
**one** LM call.

1. Write a signature `IntakeTriage` with input `evidence` and outputs `level`,
   `smells` (`list[str]`), `decision`, `report`, and a factory
   `TriageProgram(instruction=BASELINE_INSTRUCTION)` returning a `dspy.Module` with a
   single `dspy.Predict` whose forward takes `submission`. Field descriptions are part of
   the prompt — write them as you would brief a colleague (manual marks). The baseline
   instruction deliberately does **not** contain the policy.
2. Configure Claude (`lm = llm.configure_dspy()`), run once on `train[0]` (`smoke`).
3. Evaluate on `dev` with `ev.evaluate_dataset` inside `llm.meter(lm)`; store
   `baseline_dev` and `baseline_dev_cost`.

In writing: an error analysis of the baseline — for each non-perfect item, which
guideline and why you think Claude did it — and compare with the control (A2). Which
errors come from *not knowing the policy*, and which from *not reading the evidence*?
""", auto_points=4)
ps.md(r'''
#### Background and design decisions — B2

This is the "tools measure, model interprets" design (Background §5–6): deterministic
evidence gathering, then **one** Claude call through a DSPy predictor. The baseline
instruction deliberately omits the policy, so the baseline shows how Claude behaves
*without* the rules, and Part C shows how much writing them down is worth.

Decisions you make:

* **Signature fields and descriptions.** They are part of the prompt. Listing the allowed
  labels in a field description ("one of: accept, revise, reject") is cheap and often
  fixes vocabulary errors before any optimisation.
* **Output types.** `smells: list[str]` makes DSPy ask for, and parse, a list; a `str`
  field would leave the parsing to you (and to `ev.parse_label_list`).
* **One predictor, not several.** One instruction is one thing to optimise and one thing to
  attribute a change to. Splitting level, smells and decision into three calls would
  triple cost and make GEPA's job harder.
* **What goes into the prompt.** The whole evidence bundle, not the Turtle source: the
  model interprets measurements; it does not re-derive them from raw RDF.
''')
ps.md(r'''
#### Contract — B2

```python
BASELINE_INSTRUCTION: str                       # given; do not add the policy to it
class IntakeTriage(dspy.Signature): ...
def TriageProgram(instruction: str = BASELINE_INSTRUCTION) -> dspy.Module
lm, smoke, baseline_dev, baseline_dev_cost
```

**`IntakeTriage`** — exactly one input field and four output fields:

| field | kind | type | content |
|---|---|---|---|
| `evidence` | `dspy.InputField` | `str` | the JSON text from `A.gather_evidence(...)` |
| `level` | `dspy.OutputField` | `str` | one spectrum level |
| `smells` | `dspy.OutputField` | `list[str]` | smell ids to report |
| `decision` | `dspy.OutputField` | `str` | accept / revise / reject |
| `report` | `dspy.OutputField` | `str` | a short report to the team |

**`TriageProgram(instruction)`** returns a `dspy.Module` that:

* holds **exactly one** `dspy.Predict` on `IntakeTriage` whose instruction is `instruction`
  (use `IntakeTriage.with_instructions(instruction)`), so that
  `opt.instruction_of(TriageProgram("x")) == "x"`;
* has `forward(self, submission: str) -> dspy.Prediction`, which calls
  `A.gather_evidence(submission)` and passes the result as `evidence=`.

It is called as `program(**ex.inputs())`, i.e. `program(submission="station-facility-types")`,
and returns a prediction with `.level`, `.smells`, `.decision`, `.report`.

**Variables the check reads**

| name | type | how to produce it |
|---|---|---|
| `lm` | `dspy.LM` | `llm.configure_dspy()` |
| `smoke` | `dspy.Prediction` | `TriageProgram()(**train[0].inputs())` — one billed call |
| `baseline_dev` | `dict` | `ev.evaluate_dataset(TriageProgram(), dev, intake_scorer)` (shape in the Reference) |
| `baseline_dev_cost` | `dict` | `with llm.meter(lm) as baseline_dev_cost:` around the evaluation |
''')
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = ("You review ontology submissions to Meridian Rail's ontology "
                            "registry. From the evidence, give the submission's level, the "
                            "defects to report, the intake decision and a report to the team.")

    # TODO: class IntakeTriage(dspy.Signature): ...
    # TODO: def TriageProgram(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None               # TODO
    # TODO: baseline_dev, baseline_dev_cost
    """,
    solution="""
    BASELINE_INSTRUCTION = ("You review ontology submissions to Meridian Rail's ontology "
                            "registry. From the evidence, give the submission's level, the "
                            "defects to report, the intake decision and a report to the team.")

    class IntakeTriage(dspy.Signature):
        \"\"\"Triage one submission to the ontology registry from the gathered evidence.\"\"\"

        evidence: str = dspy.InputField(
            desc="JSON: the team's intake form (declared level, purpose), graph metrics, the "
                 "spectrum classifier's level and evidence, and the defect scanner's findings")
        level: str = dspy.OutputField(
            desc="one of: controlled-vocabulary, taxonomy, thesaurus, formal-ontology")
        smells: list[str] = dspy.OutputField(
            desc="the defect ids to report, exactly as the scanner names them; [] if none")
        decision: str = dspy.OutputField(desc="one of: accept, revise, reject")
        report: str = dspy.OutputField(
            desc="3-5 sentences to the submitting team: the decision, and for each defect "
                 "the offending term, the evidence, and what to change")

    def TriageProgram(instruction: str = BASELINE_INSTRUCTION):
        class _Triage(dspy.Module):
            def __init__(self):
                super().__init__()
                self.triage = dspy.Predict(IntakeTriage.with_instructions(instruction))

            def forward(self, submission: str):
                return self.triage(evidence=A.gather_evidence(submission))

        return _Triage()

    lm = llm.configure_dspy()
    smoke = TriageProgram()(**train[0].inputs())
    print(train[0].id, "->", smoke.level, smoke.smells, smoke.decision)
    print(smoke.report)

    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(TriageProgram(), dev, intake_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    pd.DataFrame(baseline_dev["rows"])
    """)
ps.check("B2", """
assert set(IntakeTriage.input_fields) == {"evidence"}
assert {"level", "smells", "decision", "report"} <= set(IntakeTriage.output_fields)
program = TriageProgram("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.level, str) and smoke.level.strip()
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
The analysis to hand in is of *your* run; a live baseline typically shows this pattern:

* **Level** is almost always right — the classifier's level is in the evidence and Claude
  copies it. The exception to look for is *accessibility-services* / *customer-complaints*,
  where the declared and measured levels differ and a model sometimes reports the
  declared one (`cite-spectrum-evidence`): a *reading-the-evidence* error.
* **Smells**: the baseline reports the scanner's findings faithfully, so it *over*-reports
  on the waived thesauri (`apply-waivers` on *accessibility-services*) — it cannot know
  W1, which is only in the policy. That is a *not-knowing-the-policy* error, and no amount
  of evidence fixes it.
* **Decision** is where the baseline loses most: without clause 3 it improvises —
  "revise" for a subsumption cycle, "accept" for an over-promising but clean submission,
  "reject" for a missing label. Every one of those is the policy missing from the prompt.

Against the control (1.0 by construction), the baseline's gap is almost entirely policy
knowledge, not evidence reading. That predicts what Part C should find: writing the
policy into the instruction (by hand or by GEPA) closes most of the gap. Cost: 8 calls;
note the per-call cost from `baseline_dev_cost` — it is the unit price of everything
that follows.
""")

ps.problem("B3", "Validate the LLM judge before trusting it", 10, """
The office wants to grade the free-text reports with an LLM judge (`ev.judge`). A judge
is itself a model: it has to be validated against human labels before its scores mean
anything. `A.LABELLED_REPORTS` holds 12 reports the board's reviewers labelled
*grounded* (every claim supported by the tool output, with specific terms or counts) or
not — half of each.

1. Implement `judge_agreement(labels, scores, threshold=0.5) -> dict` with keys `n`,
   `accuracy`, `precision`, `recall` (positive class = grounded; predicted grounded iff
   `score >= threshold`; precision/recall are 0.0 when undefined) and `kappa` (Cohen's κ;
   when chance agreement is 1, return 1.0 if observed agreement is 1, else 0.0).
2. Run `ev.judge(task, gold, report)` on every labelled report inside `llm.meter(lm)` —
   `task` describes the intake review, `gold` is the JSON of that submission's gold
   `level`/`smells`/`decision`. Build `b3` with columns `report`, `submission`, `label`,
   `judge_score`, and set `b3_stats = judge_agreement(...)` at 0.5 and `b3_cost`.
3. Build `b3_thresholds`: one row per threshold in `[0.3, 0.5, 0.7]` with the agreement
   statistics.

In writing: is this judge fit to grade the reports, on this evidence? What does n = 12
let you conclude? Which kinds of ungrounded report would you expect it to miss, and what
would you change before using it?
""", auto_points=5)
ps.md(r'''
#### Background and design decisions — B3

The judge (Background §9) will grade the free-text reports, the one field no function
can score. Before trusting it, treat it as a classifier and measure it against the
board's labels. The labelled set is small and balanced (6 grounded, 6 not) on purpose.

Decisions you make:

* **Metric.** Report κ as well as accuracy: on a balanced set a judge that always says
  "grounded" gets 0.5 accuracy but κ = 0.
* **Threshold.** The judge returns a number; "grounded" is a threshold choice. The
  threshold table shows the trade between catching fabrications and failing good reports.
* **What the judge sees.** Here it gets the gold labels, not the tool output, so it cannot
  check a count. The written part asks what you would change before relying on it.
* **What n = 12 supports.** Very little; say so.
''')
ps.md(r'''
#### Contract — B3

```python
def judge_agreement(labels: Iterable[bool], scores: Iterable[float], threshold: float = 0.5) -> dict
b3: pd.DataFrame;  b3_stats: dict;  b3_cost: dict;  b3_thresholds: pd.DataFrame
```

**`judge_agreement`** — pure arithmetic, no model.

| parameter | type | meaning |
|---|---|---|
| `labels` | `Iterable[bool]` (list or `pd.Series`) | human verdict per report: `True` = grounded |
| `scores` | `Iterable[float]` in [0, 1], same length | the judge's score per report |
| `threshold` | `float` | predicted grounded iff `score >= threshold` |

Returns `{"n": int, "accuracy": float, "precision": float, "recall": float, "kappa": float}`,
with grounded as the positive class. `precision = TP / (TP + FP)` and
`recall = TP / (TP + FN)`, each `0.0` when its denominator is 0. Cohen's
`kappa = (p_o - p_e) / (1 - p_e)`, where `p_o` is the observed agreement (= accuracy) and
`p_e = P(pred grounded)·P(label grounded) + P(pred not)·P(label not)`; when `p_e == 1`,
return `1.0` if `p_o == 1` else `0.0`. Example:
`judge_agreement([True, True, False, False], [0.9, 0.4, 0.2, 0.6])` →
`{"n": 4, "accuracy": 0.5, "precision": 0.5, "recall": 0.5, "kappa": 0.0}`.

**Data.** `A.LABELLED_REPORTS` is a `list` of 12 tuples
`(report_id: str, submission_id: str, text: str, grounded: bool)`. The judge call is
`ev.judge(task, gold, text)`, where `task` is a `str` describing the intake review and
`gold` is `json.dumps({"level": ..., "smells": [...], "decision": ...})` for that
submission (take the values from `ROW[submission_id]`). It returns a `ScoreReport`: use
`.score`.

| name | type | content |
|---|---|---|
| `b3` | DataFrame, 12 rows | columns `report` (id), `submission`, `label` (bool), `judge_score` (float in [0, 1]) |
| `b3_stats` | `dict` | exactly `judge_agreement(b3.label, b3.judge_score)` (threshold 0.5) |
| `b3_cost` | `dict` | `llm.meter(lm)` around the 12 judge calls |
| `b3_thresholds` | DataFrame, 3 rows | column `threshold` = `[0.3, 0.5, 0.7]` plus the five `judge_agreement` keys |
''')
ps.todo(
    stub="""
    def judge_agreement(labels: Iterable[bool], scores: Iterable[float], threshold: float = 0.5) -> dict:
        \"\"\"{"n", "accuracy", "precision", "recall", "kappa"} (see Contract B3).\"\"\"
        # TODO
        raise NotImplementedError

    b3, b3_stats, b3_cost, b3_thresholds = None, None, None, None   # TODO
    """,
    solution="""
    def judge_agreement(labels: Iterable[bool], scores: Iterable[float], threshold: float = 0.5) -> dict:
        labels = [bool(x) for x in labels]
        preds = [s >= threshold for s in scores]
        n = len(labels)
        tp = sum(l and p for l, p in zip(labels, preds))
        fp = sum(p and not l for l, p in zip(labels, preds))
        fn = sum(l and not p for l, p in zip(labels, preds))
        po = sum(l == p for l, p in zip(labels, preds)) / n
        pe = (sum(preds) / n) * (sum(labels) / n) + \\
             (1 - sum(preds) / n) * (1 - sum(labels) / n)
        kappa = (po - pe) / (1 - pe) if pe < 1 else (1.0 if po == 1 else 0.0)
        return {"n": n, "accuracy": po,
                "precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0,
                "kappa": kappa}

    JUDGE_TASK = ("Review a submission to an ontology registry: report its spectrum level, the "
                  "scanner defects to report, the intake decision, and a report to the team "
                  "that cites the tool evidence.")
    rows = []
    with llm.meter(lm) as b3_cost:
        for rid, sid, text, label in A.LABELLED_REPORTS:
            gold = json.dumps({k: ROW[sid][k] for k in ("level", "smells", "decision")})
            verdict = ev.judge(JUDGE_TASK, gold, text)
            rows.append({"report": rid, "submission": sid, "label": label,
                         "judge_score": verdict.score, "critique": verdict.notes[0][:80]})
    b3 = pd.DataFrame(rows)
    b3_stats = judge_agreement(b3.label, b3.judge_score)
    b3_thresholds = pd.DataFrame([{"threshold": t, **judge_agreement(b3.label, b3.judge_score, t)}
                                  for t in (0.3, 0.5, 0.7)])
    print(b3_stats, b3_cost)
    b3_thresholds
    """)
ps.check("B3", """
s = judge_agreement([True, True, False, False], [0.9, 0.4, 0.2, 0.6])
assert s["n"] == 4 and abs(s["accuracy"] - 0.5) < 1e-9 and abs(s["kappa"]) < 1e-9
assert abs(s["precision"] - 0.5) < 1e-9 and abs(s["recall"] - 0.5) < 1e-9
s = judge_agreement([True, True, False, False, False], [0.9, 0.6, 0.4, 0.2, 0.7])
assert abs(s["accuracy"] - 0.8) < 1e-9 and abs(s["kappa"] - 0.32 / 0.52) < 1e-9
assert abs(s["precision"] - 2 / 3) < 1e-9 and s["recall"] == 1.0
assert judge_agreement([True, True], [0.9, 0.8])["kappa"] == 1.0
assert judge_agreement([False, False], [0.9, 0.1], 0.5)["precision"] == 0.0
assert isinstance(b3, pd.DataFrame) and len(b3) == len(A.LABELLED_REPORTS) == 12
assert {"report", "submission", "label", "judge_score"} <= set(b3.columns)
assert all(0.0 <= x <= 1.0 for x in b3.judge_score)
assert b3_stats == judge_agreement(b3.label, b3.judge_score, 0.5)
assert list(b3_thresholds["threshold"]) == [0.3, 0.5, 0.7] and {"accuracy", "kappa"} <= set(b3_thresholds.columns)
assert {"calls", "usd"} <= set(b3_cost)
""")
ps.written("""
Report κ, not accuracy: with a balanced 6/6 set, a judge that says "grounded" to
everything scores 0.5 accuracy and κ = 0. A live Claude judge usually separates the
*vague* reports (r02, r06, r08) cleanly, because the judge prompt penalises claims
without cited evidence. The hard cases are the **confidently specific but wrong** ones —
r04 (invents "12 classes" and a cycle), r10 (a missing-label finding that does not
exist), r12 (a reason outside the policy): they *look* grounded, and the judge has only
the gold labels, not the tool output, so it cannot check a count. Expect those to be the
disagreements, and expect the threshold table to show a trade between catching them and
failing good reports.

With n = 12, one flipped report moves accuracy by 0.08; a κ of, say, 0.67 has a
confidence interval spanning roughly 0.2–1.0. The honest conclusion is "the judge
catches vague reports; this sample cannot establish that it catches fabricated
specifics". Before using it: give the judge the **evidence JSON** (not just the gold
labels) so it can check claims; label 50+ reports, stratified by failure type; fix the
threshold on one half and report κ on the other; and re-validate whenever the judge
prompt or model changes. Until then, the judge is a triage aid for human reviewers, not
a grader.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
GEPA rewrites the instruction by reflecting on the scorer's feedback. It is only as good
as that feedback, it overfits small training sets, and every metric call is billed. The
rules for this part: **optimise on `train`, select on `dev`, report on `test`** — with a
cost and a noise estimate next to every number.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 10, """
1. Build the feedback metric from your scorer and `A.INTAKE_RULEBOOK`
   (`ev.make_gepa_metric`) and a reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost` and the program in
   `tuned`.
3. Compare baseline and tuned on **`test`** with `opt.compare` (`c1`); print
   `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch01_registry_triage_instruction.txt"`.

In writing: read the instruction diff. Which policy clauses did GEPA write down, which
did it miss, and why? (Look at which blocking defects occur in `train`.) Did it add
anything that is not policy?
""", auto_points=5)
ps.md(r'''
#### Background and design decisions — C1

GEPA (Background §8) rewrites the B2 instruction using your B1 feedback. The three splits
have three jobs: **train** is what GEPA learns from, **dev** is what it uses to choose
between candidate instructions, and **test** is only for the report. Using test for
anything else makes the reported number optimistic.

Decisions you make:

* **Budget.** `max_metric_calls` is the cost dial: each call is one billed program run.
  60 on 8 training items is enough for a few reflection rounds; more mostly buys
  over-fitting.
* **Which LMs to meter.** GEPA uses the task LM *and* the reflection LM; meter both, or
  the cost line is wrong.
* **The instruction is an artefact.** Save it, read the diff, and treat it like code under
  review: it will run on every future call.
''')
ps.md(r'''
#### Contract — C1

| name | type | how to produce it |
|---|---|---|
| `GEPA_BUDGET` | `int` ≤ 100 | given (60): the maximum number of metric calls GEPA may make |
| `gepa_metric` | callable | `ev.make_gepa_metric(intake_scorer, A.INTAKE_RULEBOOK)` |
| `reflect` | `dspy.LM` | `llm.reflection_lm()` — the model that proposes new instructions |
| `tuned` | `dspy.Module` | `opt.run_gepa(TriageProgram(), train, gepa_metric, valset=dev, max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)` |
| `gepa_cost` | `dict` | `with llm.meter(lm, reflect) as gepa_cost:` around `run_gepa` (meter **both** LMs) |
| `c1` | `OptimisationResult` | `opt.compare(TriageProgram(), tuned, test, intake_scorer)` — on **`test`**, never on `train`/`dev` |
| `instruction_path` | `pathlib.Path` | `config.artifacts_dir() / "ch01_registry_triage_instruction.txt"`, whose content must equal `opt.instruction_of(tuned)` (`instruction_path.write_text(..., encoding="utf-8")`) |

`train` is what GEPA learns from; `dev` (`valset`) is what it uses to choose between
candidate instructions; `test` is only for the report. `c1.report()` prints the before and
after means, the violation histograms and the instruction diff.
''')
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch01_registry_triage_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(intake_scorer, A.INTAKE_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(TriageProgram(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(TriageProgram(), tuned, test, intake_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch01_registry_triage_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
ids = lambda rows: {ex.id for ex in rows}
assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test)
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 100
""")
ps.written("""
Your wording will differ; look for three things.

* **Written down.** A good run states the label vocabularies, "report the scanner's ids
  exactly", the W1 waiver (train has *timetable-service-thesaurus*), "reject on a
  subsumption cycle / class-as-individual" (train has *signalling-equipment* and
  *freight-commodities*) and the over-promise rule (train has *rostering-roles*). Each
  comes from a `VIOLATED GUIDELINE` line the baseline triggered on train.
* **Missed.** `individual-as-class` and `undeclared-term` never occur in `train`, so no
  training failure ever mentions them. Unless the reflection LM generalises from the
  rulebook sentence for `decide-by-policy` (which lists all four), the tuned instruction
  may treat *driver-register* or *work-orders* in `test` as "revise". GEPA learns the
  training failures, not the policy — the split, not the optimiser, bounds what can be
  learned.
* **Not policy.** Instructions that mention specific teams, class names or "signalling
  submissions" are memorised training detail: they cost tokens on every call and do
  nothing on test.

A test delta near zero, or a delta inside the noise of C3, is a legitimate finding. So is
a large one — but only with the diff that explains it.
""")

ps.problem("C2", "Was the optimiser worth it — and was the feedback?", 8, """
Four contenders on `test`, each evaluated inside its own `llm.meter(lm)`:

* `"baseline"`, `"gepa"` (from C1);
* `"guidelines"`: `TriageProgram(A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION))`
  — the policy written into the prompt by hand;
* `"gepa-blind"`: GEPA with the same budget but a metric whose feedback is only the
  score (`f"Score: {s:.3f}"`) — the ablation that shows what the diagnostic feedback is
  worth. Meter its optimisation too.

Build `c2` with columns `program`, `test_mean`, `violations`, `eval_usd`,
`optimisation_usd` (0 for the two unoptimised programs), `instruction_chars`.

In writing: which would you deploy, and what would change your mind? What does the
blind run tell you about metric design?
""", auto_points=3)
ps.md(r'''
#### Background and design decisions — C2

An optimiser's gain is only a finding if it beats the **cheap alternatives**. Two
controls: the policy written into the prompt by hand (*guidelines*, free), and GEPA with
a feedback-free metric (*blind*), which isolates what the diagnostic notes are worth.

Decisions you make:

* **What to deploy.** The cheapest program whose score is within the C3 noise of the
  best, counting both optimisation cost (once) and instruction length (paid on every
  call).
* **What the blind run tells you about metric design**: if it matches the diagnostic run,
  the notes were not doing the work; if it lags, they were.
''')
ps.md(r'''
#### Contract — C2

**The blind metric** has the same signature as a GEPA metric:

```python
def blind_metric(gold, pred, trace=None, pred_name=None, pred_trace=None) -> dspy.Prediction
    # returns dspy.Prediction(score=<intake_scorer score>, feedback=f"Score: {score:.3f}")
```

Optimise it exactly like C1 (`train`, `valset=dev`, the same `GEPA_BUDGET` and `reflect`),
metered with `llm.meter(lm, reflect)`.

**`c2`** — a 4-row DataFrame, all evaluated on `test`, each inside its own `llm.meter(lm)`:

| column | type | content |
|---|---|---|
| `program` | `str` | `"baseline"`, `"guidelines"`, `"gepa"`, `"gepa-blind"` |
| `test_mean` | `float` | `evaluate_dataset(...)["mean_score"]` |
| `violations` | `dict` | `evaluate_dataset(...)["violations"]` |
| `eval_usd` | `float` | the `"usd"` of that evaluation's meter |
| `optimisation_usd` | `float` | `0.0` for baseline and guidelines; `gepa_cost["usd"]` for gepa; the blind run's optimisation cost for gepa-blind |
| `instruction_chars` | `int` | `len(opt.instruction_of(program))` |

`"guidelines"` is `TriageProgram(A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION))`.
''')
ps.todo(
    stub="""
    guidelines_instruction = A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    c2 = None    # TODO
    """,
    solution="""
    guidelines_instruction = A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)

    def blind_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
        s = intake_scorer(gold, pred).score
        return dspy.Prediction(score=s, feedback=f"Score: {s:.3f}")

    with llm.meter(lm, reflect) as blind_cost:
        blind = opt.run_gepa(TriageProgram(), train, blind_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)

    contenders = {"baseline": (TriageProgram(), 0.0),
                  "guidelines": (TriageProgram(guidelines_instruction), 0.0),
                  "gepa": (tuned, gepa_cost["usd"]),
                  "gepa-blind": (blind, blind_cost["usd"])}
    rows = []
    for name, (program, optimisation_usd) in contenders.items():
        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, test, intake_scorer)
        rows.append({"program": name, "test_mean": result["mean_score"],
                     "violations": result["violations"], "eval_usd": cost["usd"],
                     "optimisation_usd": optimisation_usd,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    c2
    """)
ps.check("C2", """
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "guidelines", "gepa", "gepa-blind"}
assert {"test_mean", "violations", "eval_usd", "optimisation_usd", "instruction_chars"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines"], "optimisation_usd"].eq(0).all()
assert c2.set_index("program").loc["gepa", "optimisation_usd"] == gepa_cost["usd"]
""")
ps.written("""
The usual pattern: **guidelines** recovers most or all of GEPA's gain at zero
optimisation cost, because the rulebook *is* the policy and the policy is what the
baseline lacked. GEPA earns its cost when the failure modes are not known in advance, or
when it finds phrasing for format problems the rulebook did not anticipate. Deploy the
cheapest program whose test score is within the C3 noise of the best — usually the
guidelines — and re-optimise only when an error analysis shows failures the guidelines
do not cover. Note `instruction_chars`: a longer instruction is paid on every call.

**The blind run** typically improves format at best: reflection sees "Score: 0.700" and
has to *guess* what went wrong, so it rarely writes down W1 or the decision rule. If it
scores close to the diagnostic run on your 8 test items, check C3 before concluding
anything. The lesson stands either way: the optimiser can only write down what the metric
told it, so the scorer's `notes` and rule ids are part of the optimiser, not paperwork.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 8, """
Eight test items at temperature 1.0: one item is 0.125 of the mean. Estimate the noise.
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, `with dspy.context(lm=fresh)`),
run the baseline and the GEPA-tuned programs on `test` three times each; store the mean
scores in `runs = {"baseline": [..3..], "gepa": [..3..]}` and the cost in `c3_cost`.

Set `verdict_c3` to `"significant"` if `|mean_gepa - mean_baseline| > 2 * max(sd_gepa,
sd_baseline)` (sample sd), else `"not significant"`. In writing: what does this say about
C1 and C2, and what would a credible evaluation of the triage system need?
""", auto_points=4)
ps.md(r'''
#### Background and design decisions — C3

Claude samples at temperature 1.0, and each test split has 8 items, so a single number
moves by 0.125 per item. Before claiming that GEPA helped, measure how much a score moves
when **nothing** changes. DSPy caches identical requests, so repeated runs return the
same answer unless you use an uncached LM (`cache=False`).

Decisions you make:

* **How many repeats.** Three is the minimum for a standard deviation; say what it can
  and cannot resolve.
* **The decision rule.** The rule here (difference greater than twice the larger sd) is
  deliberately simple; the written part asks what a credible evaluation would need
  instead.
''')
ps.md(r'''
#### Contract — C3

| name | type | content |
|---|---|---|
| `fresh` | `dspy.LM` | `llm.dspy_lm(cache=False)` — an uncached LM, so repeated runs really re-sample |
| `runs` | `dict[str, list[float]]` | exactly the keys `"baseline"` and `"gepa"`, each a list of **3** mean test scores |
| `c3_cost` | `dict` | `llm.meter(fresh)` around all six evaluations |
| `verdict_c3` | `str` | `"significant"` or `"not significant"` |

Run the evaluations inside `with dspy.context(lm=fresh):` so the programs use the
uncached LM. Compute the mean and the **sample** standard deviation
(`statistics.stdev`) of each list; the verdict is `"significant"` iff
`abs(mean_gepa - mean_baseline) > 2 * max(sd_gepa, sd_baseline)`. The check recomputes it
from `runs`, so the verdict must follow from the numbers you stored.
''')
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs (inside llm.meter(fresh) as c3_cost), then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(TriageProgram(), test, intake_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, intake_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
_m = {k: st.mean(v) for k, v in runs.items()}
_s = {k: st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
assert {"calls", "usd"} <= set(c3_cost)
""")
ps.written("""
Three runs is a crude estimate, but enough to stop over-claiming. A baseline without the
policy tends to be *noisy* on the decision field (it improvises differently each time),
while a policy-bearing instruction is usually stable; so the gap can be significant even
on 8 items when the baseline is far from the policy — and not significant when both are
near ceiling. Whatever your verdict, the C1 and C2 numbers are single samples and must be
reported with this spread.

A credible evaluation needs: (i) more items — 8 per split resolves differences of about
±0.1 at best; (ii) repeated runs, reported as mean ± sd or a paired bootstrap over items;
(iii) the same items and sampling settings for every contender; (iv) the cost per run;
and (v) per-field results, because a mean over level/smells/decision hides that the
fields fail for different reasons. The sentence for the report is "the tuned instruction
changed the mean test score by X ± Y over 3 runs of 8 items, at $Z" — not "GEPA
improved accuracy by X".
""")

# =========================================================================== #
ps.part("D", "Architecture: agent or pipeline, the price of evidence, and a gated skill", """
Three decisions remain: whether the system is one tool-calling loop or a decomposed
pipeline; how much evidence is worth buying; and how the deployed skill is allowed to
change itself.
""")

ps.problem("D1", "One agent loop, or a pipeline with a verifying critic?", 8, """
1. Write `AGENT_PROMPT`: a system prompt for a tool-calling agent over
   `A.build_registry_tools(ws)` that must end its reply with one JSON object
   `{"level": ..., "smells": [...], "decision": ..., "report": ...}`; and
   `parse_triage_answer(text) -> dspy.Prediction` (fields `level`, `smells`, `decision`,
   `report`; the *last* JSON object that has a `decision` key, possibly inside a code
   fence or prose, may contain nested brackets; empty fields when there is none).
2. Write `critic(pred, evidence) -> (dspy.Prediction, list[str])`: a deterministic
   verification stage with the raw evidence JSON (`A.gather_evidence`). It overrides any
   field the evidence decides — level, reportable smells, decision (your A1 functions) —
   keeps the report, and returns one human-readable string per correction.
3. On every `test` submission, run (a) the agent (fresh workspace each; keep the logs in
   `agent_logs[id]`), (b) the tuned program from C1, (c) the same program followed by the
   critic. Build `d1` with columns `approach` (`"agent"`, `"program"`,
   `"program+critic"`), `id`, `score` (`intake_scorer`), `tool_calls`, `usd`
   (`llm.chat_usage(...)["usd_estimate"]` for the agent, `llm.meter` for the program).

In writing: compare the three on score, cost and legibility. If the critic can override
all three structured fields, what is Claude for in this system — and how would you
evaluate that part?
""", auto_points=4)
ps.md(r'''
#### Background and design decisions — D1

The architecture question (Background §10). The **agent** lets Claude choose the tool
calls; the **program** fixes them; the **critic** checks the program's structured answer
against the raw evidence using your A1 functions. Same tools, same scorer: compare them on
score, cost and how easy the run is to audit.

Decisions you make:

* **Agent prompt.** What procedure and output contract to give it. A fixed final JSON
  object makes the answer parseable; stating the policy in the prompt is the agent's
  version of the *guidelines* program.
* **Parsing.** Agents write prose around their answer; your parser decides how forgiving
  to be. Taking the *last* object with a `decision` key handles drafts that are corrected
  later in the same reply.
* **What the critic may override.** Everything the evidence decides (level, smells,
  decision), but not the report. The written part asks what that leaves Claude to do.
* **Fresh workspace per agent run**, so each `agent_logs[id]` is one trajectory for D2.
''')
ps.md(r'''
#### Contract — D1

```python
AGENT_PROMPT: str
def parse_triage_answer(text: str) -> dspy.Prediction
def critic(pred, evidence: str) -> tuple[dspy.Prediction, list[str]]
agent_logs: dict[str, ToolCallLog];  d1: pd.DataFrame
```

**`parse_triage_answer(text)`** — `text` is the agent's final reply (`run.answer`): prose,
possibly a Markdown code fence, possibly several JSON objects, possibly nested braces.
Find **the last JSON object that has a `"decision"` key** (tip: try
`json.JSONDecoder().raw_decode(text, i)` at every `{`). Return
`dspy.Prediction(level=str, smells=list[str], decision=str, report=str)`, with `smells`
through `ev.parse_label_list`. No such object → `level=""`, `smells=[]`, `decision=""`,
`report=""`; never raise.

**`critic(pred, evidence)`** — a deterministic verifier.

| parameter | type | meaning |
|---|---|---|
| `pred` | a prediction (may be an **empty** `dspy.Prediction()`) | the model's answer; read it with `getattr(..., default)` |
| `evidence` | `str` | the JSON text from `A.gather_evidence(submission_id)` |

From the evidence take `spectrum.level` (measured), `submission.declared_level` and the
set of `scanner_findings[*].smell`; compute the correct smells and decision with your A1
functions. Return a tuple:

1. a new `dspy.Prediction(level=measured, smells=<reportable list>, decision=<policy decision>, report=<pred's report, or "">)`;
2. `list[str]`: one human-readable correction per field the model got wrong (for example
   `"decision 'revise' -> 'accept'"`, one entry per dropped or added smell). An empty
   list means the model agreed with the evidence on all three fields.

**Running the three approaches on `test`**

* agent: a fresh `ws = A.RegistryWorkspace()` per item;
  `agent, _ = agents.build_agent(ws, system_prompt=AGENT_PROMPT, tools=A.build_registry_tools(ws))`;
  `run = agents.run_agent(agent, ws, "Triage the registry submission '<id>'.")`; score
  `parse_triage_answer(run.answer)`; store `agent_logs[id] = ws.log`.
* program: `tuned(submission=id)` inside `llm.meter(lm)`.
* program+critic: `critic(<program prediction>, A.gather_evidence(id))[0]`.

**`d1`** — 24 rows (3 approaches × 8 test items):

| column | type | content |
|---|---|---|
| `approach` | `str` | `"agent"`, `"program"`, `"program+critic"` |
| `id` | `str` | the submission id |
| `score` | `float` | `intake_scorer(ex, prediction).score` |
| `tool_calls` | `int` | calls in that item's workspace log |
| `usd` | `float` | agent: `llm.chat_usage(run.messages)["usd_estimate"]`; program rows: that call's `llm.meter` `"usd"` |
''')
ps.todo(
    stub="""
    AGENT_PROMPT = "TODO"

    def parse_triage_answer(text: str) -> dspy.Prediction:
        \"\"\"Last JSON object with a "decision" key -> Prediction(level, smells, decision, report).\"\"\"
        # TODO
        raise NotImplementedError

    def critic(pred, evidence: str) -> tuple[dspy.Prediction, list[str]]:
        \"\"\"Override level/smells/decision from the evidence; keep the report (see Contract D1).\"\"\"
        # TODO: return (corrected prediction, list of corrections)
        raise NotImplementedError

    agent_logs = {}
    d1 = None   # TODO
    """,
    solution="""
    AGENT_PROMPT = '''You triage submissions to Meridian Rail's ontology registry under
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
    '''

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

    rows, agent_logs, corrections_log = [], {}, {}
    for ex in test:
        ws = A.RegistryWorkspace()
        agent, _ = agents.build_agent(ws, system_prompt=AGENT_PROMPT,
                                      tools=A.build_registry_tools(ws))
        run = agents.run_agent(agent, ws, f"Triage the registry submission '{ex.id}'.")
        agent_logs[ex.id] = ws.log
        rows.append({"approach": "agent", "id": ex.id,
                     "score": intake_scorer(ex, parse_triage_answer(run.answer)).score,
                     "tool_calls": len(ws.log.calls),
                     "usd": llm.chat_usage(run.messages)["usd_estimate"]})

        with llm.meter(lm) as cost:
            pred = tuned(submission=ex.id)
        ws_p = A.RegistryWorkspace()
        evidence = A.gather_evidence(ex.id, ws_p)
        fixed, corrections_log[ex.id] = critic(pred, evidence)
        for name, p in [("program", pred), ("program+critic", fixed)]:
            rows.append({"approach": name, "id": ex.id,
                         "score": intake_scorer(ex, p).score,
                         "tool_calls": len(ws_p.log.calls), "usd": cost["usd"]})
    d1 = pd.DataFrame(rows)
    print({k: v for k, v in corrections_log.items() if v})
    d1.groupby("approach")[["score", "tool_calls", "usd"]].agg(["mean", "sum"])
    """)
ps.check("D1", """
p = parse_triage_answer('Done.\\n```json\\n{"level": "taxonomy", "smells": ["missing-label"], '
                        '"decision": "revise", "report": "Label mr:X."}\\n```')
assert (p.level, p.smells, p.decision) == ("taxonomy", ["missing-label"], "revise")
p = parse_triage_answer('{"note": {"a": 1}} then {"level": "thesaurus", "smells": [], '
                        '"decision": "accept", "report": "x", "extra": {"k": [1, 2]}}')
assert (p.level, p.smells, p.decision) == ("thesaurus", [], "accept")
p = parse_triage_answer("I think it should be rejected.")
assert (p.level, p.smells, p.decision) == ("", [], "")

evidence = A.gather_evidence("timetable-service-thesaurus")
bad = dspy.Prediction(level="taxonomy", smells=["no-disjointness", "missing-label"],
                      decision="revise", report="keep me")
fixed, corrections = critic(bad, evidence)
assert (fixed.level, list(fixed.smells), fixed.decision, fixed.report) == \\
    ("thesaurus", [], "accept", "keep me")
assert len(corrections) >= 4
good = dspy.Prediction(level="thesaurus", smells=[], decision="accept", report="ok")
assert critic(good, evidence)[1] == []

assert isinstance(d1, pd.DataFrame)
assert set(d1["approach"]) == {"agent", "program", "program+critic"}
assert {"approach", "id", "score", "tool_calls", "usd"} <= set(d1.columns)
assert all(set(g["id"]) == {ex.id for ex in test} for _, g in d1.groupby("approach"))
assert set(agent_logs) == {ex.id for ex in test}
_crit = d1[d1.approach == "program+critic"].set_index("id")["score"]
assert all(abs(_crit[ex.id] - intake_scorer(ex, critic(dspy.Prediction(), A.gather_evidence(ex.id))[0]).score) < 1e-9
           for ex in test)
""")
ps.written("""
Expected shape of a live run (yours is the answer): the **agent** usually matches the
program on the structured fields when its prompt carries the policy, but costs several
times more per item (5–8 turns, each re-sending the growing transcript and the tool
schemas) and its trajectory varies — sometimes it skips `submission_record` and misses
an over-promise, sometimes it calls `smell_catalogue` or SPARQL for nothing. The
**program** makes exactly five tool calls and one model call. **program+critic** scores
1.0 on the structured fields *by construction*: the critic has the raw evidence and the
policy as code, so a hallucinated defect or an improvised decision cannot survive it. The
corrections list is the log of what the model got wrong — a monitoring signal worth
keeping even when the critic fixes it.

**What is Claude for, then?** The report: explaining each defect in the team's terms and
saying what to change. That is the part no function computes, and the part the B3 judge
was meant to grade — which is why the judge had to be validated first. The design lesson
generalises: put measurement and decidable rules in code, use the model for what is
genuinely judgement or language, and verify the model's claims against raw tool output
before they leave the system. The agent loop is the right choice only when the order of
work genuinely depends on what is found — not here, where the evidence plan is fixed.
""")

ps.problem("D2", "The price of evidence: an MDP", 8, """
`mdp.EvidenceMDP(kinds, score, step_cost)` models a reviewer buying evidence (one tool
call per kind in `A.EVIDENCE_KINDS`) and then submitting; the submit reward is the
answer quality the evidence supports. Define that precisely: a field is **determined**
by an evidence set `E` when the policy gives the same answer for every value the missing
evidence could take — the measured level ranges over all four levels if `"spectrum"` is
not in `E`, the declared level over all four if `"record"` is not in `E`; without
`"smells"`, nothing about defects or the decision is determined (an unseen scan could
return anything). The level is determined iff `"spectrum"` is in `E`.

1. Implement `determined(row, E) -> dict` (keys `level`, `smells`, `decision`, bools) and
   `quality(row, E) = 0.3*level + 0.4*smells + 0.3*decision` — the scorer's weights,
   because a determined field is answered correctly.
2. For every submission, solve its MDP at `step_cost=0.05` with `mdp.value_iteration`;
   build `d2` with columns `id`, `v_star`, `plan` (the evidence kinds the greedy optimal
   rollout buys, as a sorted list).
3. Pool the items (score = mean quality over all 24) — a reviewer who does not know in
   advance which submission it faces. Sweep `step_cost` over
   `np.round(np.arange(0.0, 0.31, 0.01), 2)` and set `c_record` to the smallest cost at
   which the pooled optimal plan no longer buys `"record"`.
4. Replay each D1 agent trajectory (`mdp.episode_from_tool_log`, with its D1 score) in its
   item's MDP and build `d2_regret` with columns `id`, `agent_return`, `v_star`, `regret`.

In writing: explain `c_record` analytically; say what the per-item V\\* assumes that no
real reviewer has; and interpret the agent's regret — how much is procedure, how much is
answer quality, and how much is the reward model's fault?
""", auto_points=5)
ps.md(r'''
#### Background and design decisions — D2

The MDP (Background §11) prices evidence. State = the evidence kinds held; actions = buy
one more kind (one tool call, cost `step_cost`) or *submit*; the submit reward = how good
an answer that evidence supports. Solving it gives the best achievable trade-off, V\*, and
the agent's regret is its distance from it.

Decisions you make:

* **What "the evidence supports an answer" means.** Here: a field counts as answered only
  if the policy gives the same answer for **every** value the missing evidence could take.
  That is a pessimistic, checkable definition; the written part asks what it assumes.
* **Per item vs pooled.** A per-item MDP assumes the reviewer knows in advance which
  submission it faces (and so which evidence will matter); the pooled MDP does not. The
  gap between them is the value of that foresight.
* **The reward model.** The step cost is a made-up price; regret is only meaningful if the
  cost reflects what actually costs money (tokens per turn, not tool calls).
''')
ps.md(r'''
#### Contract — D2

```python
def determined(row: dspy.Example, E: Iterable[str]) -> dict[str, bool]
def quality(row: dspy.Example, E: Iterable[str]) -> float
d2: pd.DataFrame;  c_record: float;  d2_regret: pd.DataFrame
```

| parameter | type | meaning |
|---|---|---|
| `row` | dataset row | fields read: `level`, `declared_level`, `raw_smells` |
| `E` | `Iterable[str]`, a subset of `A.EVIDENCE_KINDS` | the evidence a reviewer holds, e.g. `{"spectrum", "smells"}` |

**`determined(row, E)`** returns `{"level": bool, "smells": bool, "decision": bool}`:

* `level` is `True` iff `"spectrum" in E`;
* without `"smells"` in `E`, `smells` and `decision` are both `False`;
* otherwise let the candidate measured levels be `[row.level]` if `"spectrum" in E`, else
  all of `ont.SPECTRUM_LEVELS`, and the candidate declared levels be
  `[row.declared_level]` if `"record" in E`, else all four. `smells` is `True` iff
  `reportable_smells(row.raw_smells, m)` is the same for every candidate `m`; `decision` is
  `True` iff `intake_decision(...)` is the same for every candidate pair `(m, d)`.

Example: for `signalling-equipment` (it has a subsumption cycle),
`determined(row, {"smells"}) == {"level": False, "smells": False, "decision": True}`,
because every level gives *reject* but the waiver makes the reported smells depend on the
level.

**`quality(row, E)`** = `0.3*level + 0.4*smells + 0.3*decision` (bools count as 0/1). It
is called thousands of times; memoise it (e.g. `functools.lru_cache` on
`(row.id, frozenset(E))`).

**MDP API**

| call | returns |
|---|---|
| `mdp.EvidenceMDP(A.EVIDENCE_KINDS, score, step_cost=0.05)` | an MDP; `score` is a function `frozenset[str] -> float` (e.g. `lambda E: quality(ex, E)`) |
| `mdp.value_iteration(M)` | `(V, pi)`: `V[state] -> float`, `pi[state] -> action`; the start value is `V[M.initial_state()]` |
| `mdp.run_episode(M, mdp.greedy_policy(pi))` | an `Episode`; `.actions` is the list of actions taken, ending with `mdp.SUBMIT` (`"submit"`) |
| `mdp.episode_from_tool_log(log, M, A.TOOL_TO_EVIDENCE, final_score)` | an `Episode` replaying a real tool log; `.discounted_return()` is its return |

In the lambda, bind the loop variable (`lambda E, ex=ex: quality(ex, E)`), or every MDP
scores the last row.

| name | type | content |
|---|---|---|
| `d2` | DataFrame, 24 rows | `id`, `v_star` (float), `plan` (sorted `list[str]` of the evidence kinds the greedy rollout buys, without `"submit"`) |
| `c_record` | `float` | smallest `step_cost` in `np.round(np.arange(0.0, 0.31, 0.01), 2)` at which the **pooled** optimal plan (score = mean quality over all 24 rows) no longer buys `"record"` |
| `d2_regret` | DataFrame, 8 rows | `id`, `agent_return`, `v_star`, `regret = v_star - agent_return`, using `agent_logs[id]` and that item's D1 agent score |
''')
ps.code("""
import functools
import numpy as np
print(A.EVIDENCE_KINDS)
print(A.TOOL_TO_EVIDENCE)
""")
ps.todo(
    stub="""
    def determined(row: dspy.Example, E: Iterable[str]) -> dict[str, bool]:
        \"\"\"{"level", "smells", "decision"} -> is the field determined by evidence E? (Contract D2)\"\"\"
        # TODO
        raise NotImplementedError

    def quality(row: dspy.Example, E: Iterable[str]) -> float:
        \"\"\"0.3*level + 0.4*smells + 0.3*decision over determined(row, E) (Contract D2).\"\"\"
        # TODO
        raise NotImplementedError

    d2 = None           # TODO (2)
    c_record = None     # TODO (3)
    d2_regret = None    # TODO (4)
    """,
    solution="""
    LEVELS = ont.SPECTRUM_LEVELS

    def determined(row: dspy.Example, E: Iterable[str]) -> dict[str, bool]:
        E = set(E)
        level = "spectrum" in E
        if "smells" not in E:
            return {"level": level, "smells": False, "decision": False}
        measured = [row.level] if level else LEVELS
        declared = [row.declared_level] if "record" in E else LEVELS
        reports = {tuple(reportable_smells(row.raw_smells, m)) for m in measured}
        decisions = {intake_decision(reportable_smells(row.raw_smells, m), d, m)
                     for m in measured for d in declared}
        return {"level": level, "smells": len(reports) == 1, "decision": len(decisions) == 1}

    @functools.lru_cache(maxsize=None)
    def _quality(item: str, E: frozenset) -> float:
        d = determined(ROW[item], E)
        return 0.3 * d["level"] + 0.4 * d["smells"] + 0.3 * d["decision"]

    def quality(row: dspy.Example, E: Iterable[str]) -> float:
        return _quality(row.id, frozenset(E))

    def solve(score, cost):
        M = mdp.EvidenceMDP(A.EVIDENCE_KINDS, score, step_cost=cost)
        V, pi = mdp.value_iteration(M)
        plan = sorted(a for a in mdp.run_episode(M, mdp.greedy_policy(pi)).actions
                      if a != mdp.SUBMIT)
        return M, V[M.initial_state()], plan

    item_mdp, rows = {}, []
    for ex in ALL:
        M, v, plan = solve(lambda E, ex=ex: quality(ex, E), 0.05)
        item_mdp[ex.id] = (M, v)
        rows.append({"id": ex.id, "v_star": round(v, 4), "plan": plan})
    d2 = pd.DataFrame(rows)

    pooled = lambda E: sum(quality(ex, E) for ex in ALL) / len(ALL)
    sweep = []
    for c in np.round(np.arange(0.0, 0.31, 0.01), 2):
        _, v, plan = solve(pooled, float(c))
        sweep.append({"step_cost": float(c), "v_star": round(v, 4), "plan": plan})
    sweep = pd.DataFrame(sweep)
    c_record = float(sweep[~sweep.plan.apply(lambda p: "record" in p)].step_cost.min())
    print("per-item plans:", d2.plan.apply(tuple).value_counts().to_dict())
    print("c_record =", c_record)

    reg = []
    for ex in test:
        M, v = item_mdp[ex.id]
        score = d1[(d1.approach == "agent") & (d1.id == ex.id)].score.iloc[0]
        G = mdp.episode_from_tool_log(agent_logs[ex.id], M, A.TOOL_TO_EVIDENCE, score).discounted_return()
        reg.append({"id": ex.id, "agent_return": round(G, 4), "v_star": round(v, 4),
                    "regret": round(v - G, 4)})
    d2_regret = pd.DataFrame(reg)
    d2_regret
    """)
ps.check("D2", """
sig, rost, delay = ROW["signalling-equipment"], ROW["rostering-roles"], ROW["delay-reason-codes"]
assert determined(sig, {"smells"}) == {"level": False, "smells": False, "decision": True}
assert determined(rost, {"spectrum", "smells"})["decision"] is False
assert determined(rost, {"record", "spectrum", "smells"}) == {"level": True, "smells": True, "decision": True}
assert determined(delay, {"record", "smells"}) == {"level": False, "smells": True, "decision": True}
assert determined(ROW["crew-competence"], {"spectrum", "smells"})["decision"] is True
assert abs(quality(sig, {"spectrum", "smells"}) - 1.0) < 1e-9 and quality(sig, set()) == 0.0
assert isinstance(d2, pd.DataFrame) and len(d2) == 24 and {"id", "v_star", "plan"} <= set(d2.columns)
_d2 = d2.set_index("id")
assert list(_d2.loc["signalling-equipment", "plan"]) == ["smells", "spectrum"]
assert abs(_d2.loc["signalling-equipment", "v_star"] - 0.90) < 1e-6
assert list(_d2.loc["rostering-roles", "plan"]) == ["record", "smells", "spectrum"]
assert abs(_d2.loc["rostering-roles", "v_star"] - 0.85) < 1e-6
assert abs(c_record - 0.10) <= 0.015
assert isinstance(d2_regret, pd.DataFrame) and set(d2_regret.id) == {ex.id for ex in test}
assert {"agent_return", "v_star", "regret"} <= set(d2_regret.columns)
assert all(abs(r.regret - (r.v_star - r.agent_return)) < 1e-3 for r in d2_regret.itertuples())
""")
ps.written("""
**`c_record = 0.10`.** The record only matters for the decision, and only for the 8
submissions whose decision depends on the declared level — the clean or fully-waived
ones below formal-ontology (a blocking defect decides *reject*, a reportable defect
decides *revise*, a clean formal ontology cannot over-promise). Pooled over 24 items the
record is worth 0.3 × 8/24 = 0.10 of expected score, so it is bought iff the step cost is
below 0.10 (at exactly 0.10 buying and skipping tie; value iteration's tie-break buys, so
the grid reports `c_record = 0.11`). Spectrum and scan are worth far more (level 0.3
alone, plus most of smells and decision), so they survive to much higher costs.

**The per-item V\\* is clairvoyant**: it is the value of a reviewer who knows, before
looking, which submission it has and therefore which evidence will matter. That reviewer
skips the form on 16 of 24 items and averages 1 − 2c − c·8/24; the pooled reviewer must
buy the form every time (1 − 3c). The difference, c·16/24 ≈ 0.033 at c = 0.05, is the
value of that foresight — the per-item V\\* is an upper bound for analysis, not a policy
an agent can follow. The honest model is a POMDP over which submission it is; the pooled
MDP is its simplest approximation.

**Regret.** The replay charges every call, including `load_submission` (which the MDP
never credits) and any `smell_catalogue`/SPARQL calls, so an agent with a perfect answer
still shows ≈ 0.05–0.15 regret: *procedure*. Answer errors show up as the submit reward
falling below 1. And part of it is the **reward model's** fault: loading is unavoidable,
and the MDP's step cost is a made-up price — before telling the agent it is wasteful,
check that the reward charges what really costs money (tokens per turn, not tool calls).
""")

ps.problem("D3", "Ship it as a skill, behind a gated self-improvement loop", 8, """
A skill is a versioned bundle: instruction, tools, dataset, metric. `SelfImprovingSkill`
serves requests, mines labelled failures, re-optimises on them, and **promotes a
candidate only if it beats the current version by `min_gain` on a holdout the optimiser
never sees**.

1. Build `skill = Skill(...)` for the triage program (baseline instruction, your scorer,
   `dataset=test`, the tools the program uses).
2. Build `sis = SelfImprovingSkill(skill, holdout=dev, optimise=..., min_gain=MIN_GAIN)`
   where `optimise` runs GEPA with `max_metric_calls=SI_BUDGET`. Inside
   `llm.meter(lm, reflect)` as `d3_cost`: serve `train` (`sis.run_all`), run one
   improvement round, then replace `sis.optimise` with a **no-op control**
   (`lambda program, trainset: program`) and run a second round; finally
   `skill.evaluate()` so the card's claim is measured on `test`.
3. Save the skill to `config.artifacts_dir() / "ch01_registry_triage_skill.json"` as
   `skill_path`; print `sis.report()` and `skill.card()`.

In writing: justify your `MIN_GAIN` from C3. What should the control round do, and what
would it mean if it were promoted? Why must the holdout differ from the experience the
failures were mined from — and why is `test` still not the right holdout here?
""", auto_points=3)
ps.md(r'''
#### Background and design decisions — D3

Packaging and change control (Background §12). A `Skill` keeps the instruction, the tools
it assumes, its evaluation data and its metric together and versioned.
`SelfImprovingSkill` serves requests, mines the labelled failures, re-optimises, and asks
a **gate** whether the candidate is really better.

Decisions you make:

* **`MIN_GAIN`.** The margin a candidate must beat on the holdout. Set it below the
  run-to-run noise from C3 and noise gets promoted; set it far above and nothing ever is.
  Derive it from your measurement.
* **The no-op control round.** It deliberately proposes "no change". A correct gate must
  reject it; if it is promoted, the gate is broken.
* **Which data is which.** Experience (`train`) is mined for failures; the holdout (`dev`)
  is the only data the gate reads; the skill card reports on `test`. Mixing any two leaks
  the answer into the measurement.
''')
ps.md(r'''
#### Contract — D3

**`Skill`** (from `oe_course.skills`)

```python
Skill(name: str, description: str,
      build: Callable[[str], dspy.Module],     # instruction -> fresh program: pass TriageProgram
      scorer,                                  # intake_scorer
      dataset: list,                           # test: what the skill card reports on
      instruction: str,                        # BASELINE_INSTRUCTION
      tools: list[str])                        # names of the registry tools the program uses
```

Useful members: `.version` (int, starts at 1), `.instruction`, `.history`
(`list[SkillVersion]` with `.score`, `.dataset`, `.note`), `.evaluate()` (scores
`.dataset` and records it on the current version), `.card()` (str),
`.save(path) -> Path` (JSON).

**`SelfImprovingSkill`** (from `oe_course.selfimprove`)

```python
SelfImprovingSkill(skill, holdout: list, optimise: Callable[[dspy.Module, list], dspy.Module],
                   *, min_gain: float)
```

* `optimise(program, trainset)` returns a new program. Here, GEPA with `gepa_metric`,
  `max_metric_calls=SI_BUDGET` and `reflection_lm=reflect`. Replace it later with the
  no-op control `lambda program, trainset: program` by assigning `sis.optimise = ...`.
* `sis.run_all(examples)` serves each example and stores it in `sis.experience`. Call it
  **once**, on `train` (the check expects `len(sis.experience) == len(train)`).
* `sis.improve()` runs one round and returns an `ImprovementRound` (`.before`, `.after`,
  `.promoted`, `.reason`); it promotes only if `after - before >= min_gain` on `holdout`.
  All rounds are in `sis.rounds`; `sis.report()` summarises them.

| name | type | content |
|---|---|---|
| `MIN_GAIN`, `SI_BUDGET` | `float`, `int` | given (0.05, 30); justify `MIN_GAIN` in writing |
| `skill` | `Skill` | as above |
| `sis` | `SelfImprovingSkill` | `holdout=dev` |
| `d3_cost` | `dict` | `llm.meter(lm, reflect)` around serving, both rounds and `skill.evaluate()` |
| `skill_path` | `Path` | `skill.save(config.artifacts_dir() / "ch01_registry_triage_skill.json")` |
''')
ps.todo(
    stub="""
    MIN_GAIN, SI_BUDGET = 0.05, 30
    skill = None      # TODO
    sis = None        # TODO
    # TODO: serve, improve, control round, evaluate (inside llm.meter -> d3_cost); save -> skill_path
    """,
    solution="""
    MIN_GAIN, SI_BUDGET = 0.05, 30
    skill = Skill(
        name="registry-intake-triage",
        description="Measure a registry submission's spectrum level and defects and decide "
                    "accept / revise / reject under intake policy v3.",
        build=TriageProgram, scorer=intake_scorer, dataset=test,
        instruction=BASELINE_INSTRUCTION,
        tools=["load_submission", "submission_record", "graph_metrics",
               "spectrum_position", "scan_smells"])
    sis = SelfImprovingSkill(
        skill, holdout=dev, min_gain=MIN_GAIN,
        optimise=lambda program, trainset: opt.run_gepa(
            program, trainset, gepa_metric, max_metric_calls=SI_BUDGET, reflection_lm=reflect))

    with llm.meter(lm, reflect) as d3_cost:
        sis.run_all(train)
        print(sis.improve())
        sis.optimise = lambda program, trainset: program        # no-op control
        print(sis.improve())
        skill.evaluate()

    skill_path = skill.save(config.artifacts_dir() / "ch01_registry_triage_skill.json")
    print(sis.report())
    print()
    print(skill.card())
    print("cost:", d3_cost)
    """)
ps.check("D3", """
assert isinstance(skill, Skill) and isinstance(sis, SelfImprovingSkill)
assert len(sis.rounds) == 2 and len(sis.experience) == len(train)
for r in sis.rounds:
    assert r.promoted == (r.after - r.before >= sis.min_gain), r
assert skill.version == 1 + sum(r.promoted for r in sis.rounds)
saved = json.loads(skill_path.read_text(encoding="utf-8"))
assert len(saved["history"]) == skill.version and saved["instruction"] == skill.instruction
assert skill.history[-1].score is not None and skill.history[-1].dataset == f"{len(test)} examples"
assert {"calls", "usd"} <= set(d3_cost)
""")
ps.written("""
**`MIN_GAIN`.** It must exceed the run-to-run noise on the holdout, or noise alone gets
promoted. From C3, a program's sd over 8 items is typically 0.02–0.06; 0.05 is at the
edge of that and a defensible minimum; 0.1 (one item's worth of score) is safer on a
holdout this small. Whatever you choose, derive it from your measured sd, not by taste.

**The control round** returns the current program unchanged. With DSPy's cache, its
holdout score is *identical* to the current version's, the gain is exactly 0, and the
gate must reject it. If it were promoted, the gate would be broken — it would be adopting
noise (e.g. caching disabled and `min_gain` below the sd) — and every "improvement" the
loop ever reported would be suspect. A rejected round is a result, not a failure; a loop
that never rejects anything is a random walk.

**Separate datasets.** The failures were mined from `train` experience and GEPA optimised
on them; scoring the candidate on the same items rewards memorising them. The holdout
(`dev`) is the only data the gate reads. `test` is not the right holdout because it is
the data the *skill card* reports on: if the gate selected on it, the card's number would
be optimistically biased — the same leak, one level up. In production the experience
stream replaces `train`, needs a labelling path (unlabelled failures cannot be mined),
and the holdout must be refreshed and kept away from the optimiser as policy changes.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "05"):
        print("wrote", path.name)
