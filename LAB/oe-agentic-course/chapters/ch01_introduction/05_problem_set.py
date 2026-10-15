# %% [markdown] assignment
# # Problem Set: Triaging submissions to an ontology registry with Claude
# ### Chapter 1 — Introduction
#
# **Topic coverage:** Keet §1.1 (what an ontology looks like: the vocabulary → taxonomy → thesaurus → formal-ontology spectrum), §1.2 (why ontologies pay off), §1.3 (what makes an ontology good or bad); course notebooks 01–04 of this chapter. Tools: DSPy, and the Chapter 1 modules of `agentlab` (`ontology`, `llm`, `evaluation`, `grading`). This is the course's foundation problem set: every later chapter reuses its discipline.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 82 (Part A 10 / Part B 30 / Part C 18 / Part D 18 / Part E 6); 48 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 8–10 hours.
#
# **API budget:** ≈ \$0.85 **measured** for one full run in the reference run (`claude-sonnet-5-5`; ≈ 160 calls at ≈ \$0.005 each, ≈ \$0.013 for a real FIBO module; Part D's 80 FIBO triages are the largest line). Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# **Meridian Rail** runs a company-wide **ontology registry**: before a team's vocabulary
# or ontology is published for other systems to depend on, the data architecture office
# reviews it at *intake*. The review answers three questions — where does the submission
# sit on the ontology spectrum, which modelling defects does it have, and is it
# **accepted**, sent back to **revise**, or **rejected** — and ends with a short report to
# the submitting team. The rules are the office's written *intake policy (v3)*, printed
# below. The backlog is 24 submissions from 16 teams and growing; the head of data
# architecture wants to know whether Claude can take over first-line triage, and on what
# evidence. You are the ontology engineer asked to find out. Your brief:
#
# 1. **Pin the task down.** Write the policy's decidable clauses as code. Applied to the
#    registry's measurements, that code is the control every Claude number is compared
#    with.
# 2. **Build the grader first**, with diagnostics that say what went wrong, not only how
#    much.
# 3. **Build a Claude triage program**, measure it — including the written report, the
#    one part code cannot produce — write the policy into its instruction, and report on a
#    **held-out test split** with its cost and its run-to-run noise.
# 4. **Try it on real ontologies**: 40 modules of FIBO. Find out whether the *policy*
#    survives contact with them, and fix it if not.
# 5. **Triage the platform's own output**: the ontology the Semantic Intelligence Platform
#    (`sip/` in this repository) builds in its demo.
#
# The 24 submissions (split 8 / 8 / 8 by submission, each split containing every
# decision and every spectrum level) and the board's gold labels, the 40 FIBO modules and
# the registry's import index are provided in `ch01_agentic.py`.
#
# > The office's original brief went further: validate an LLM judge for what a code check
# > of the report cannot see, improve the program with GEPA, compare a tool-calling agent with a pipeline,
# > price evidence-gathering as an MDP, and ship a gated, self-improving skill. Each of
# > those returns in the chapter that introduces its layer: GEPA in Chapter 2, tools and
# > agents in Chapter 3, the judge in Chapter 5, MDPs in Chapter 6, self-improvement in
# > Chapter 10. The gold labels are
# checked against Chapter 1's own spectrum classifier and defect scanner when the
# notebook starts.
#
# ## Submission requirements
#
# 1. **This notebook, executed top to bottom**, with every `TODO` implemented and every *Your answer* cell written.
# 2. **The artefacts it saves** under `artifacts/` (exported submissions, run logs) — they are evidence, not by-products.
# 3. **Honest reporting.** A number without its split, its sample size and its cost earns no credit. Report the runs you did, including the ones that did not improve anything.
#
# The check cells are the marking scheme for the auto-graded points; do not edit them. The final self-test prints your auto-graded subtotal.
#
# > Solutions: `05_solutions.ipynb` — do not open it until you have attempted every problem.

# %% [markdown] solution
# # Problem Set: Triaging submissions to an ontology registry with Claude — Solutions
# ### Chapter 1 — Introduction
#
# **Topic coverage:** Keet §1.1 (what an ontology looks like: the vocabulary → taxonomy → thesaurus → formal-ontology spectrum), §1.2 (why ontologies pay off), §1.3 (what makes an ontology good or bad); course notebooks 01–04 of this chapter. Tools: DSPy, and the Chapter 1 modules of `agentlab` (`ontology`, `llm`, `evaluation`, `grading`). This is the course's foundation problem set: every later chapter reuses its discipline.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 82 (Part A 10 / Part B 30 / Part C 18 / Part D 18 / Part E 6); 48 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 8–10 hours.
#
# **API budget:** ≈ \$0.85 **measured** for one full run in the reference run (`claude-sonnet-5-5`; ≈ 160 calls at ≈ \$0.005 each, ≈ \$0.013 for a real FIBO module; Part D's 80 FIBO triages are the largest line). Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# **Meridian Rail** runs a company-wide **ontology registry**: before a team's vocabulary
# or ontology is published for other systems to depend on, the data architecture office
# reviews it at *intake*. The review answers three questions — where does the submission
# sit on the ontology spectrum, which modelling defects does it have, and is it
# **accepted**, sent back to **revise**, or **rejected** — and ends with a short report to
# the submitting team. The rules are the office's written *intake policy (v3)*, printed
# below. The backlog is 24 submissions from 16 teams and growing; the head of data
# architecture wants to know whether Claude can take over first-line triage, and on what
# evidence. You are the ontology engineer asked to find out. Your brief:
#
# 1. **Pin the task down.** Write the policy's decidable clauses as code. Applied to the
#    registry's measurements, that code is the control every Claude number is compared
#    with.
# 2. **Build the grader first**, with diagnostics that say what went wrong, not only how
#    much.
# 3. **Build a Claude triage program**, measure it — including the written report, the
#    one part code cannot produce — write the policy into its instruction, and report on a
#    **held-out test split** with its cost and its run-to-run noise.
# 4. **Try it on real ontologies**: 40 modules of FIBO. Find out whether the *policy*
#    survives contact with them, and fix it if not.
# 5. **Triage the platform's own output**: the ontology the Semantic Intelligence Platform
#    (`sip/` in this repository) builds in its demo.
#
# The 24 submissions (split 8 / 8 / 8 by submission, each split containing every
# decision and every spectrum level) and the board's gold labels, the 40 FIBO modules and
# the registry's import index are provided in `ch01_agentic.py`.
#
# > The office's original brief went further: validate an LLM judge for what a code check
# > of the report cannot see, improve the program with GEPA, compare a tool-calling agent with a pipeline,
# > price evidence-gathering as an MDP, and ship a gated, self-improving skill. Each of
# > those returns in the chapter that introduces its layer: GEPA in Chapter 2, tools and
# > agents in Chapter 3, the judge in Chapter 5, MDPs in Chapter 6, self-improvement in
# > Chapter 10. The gold labels are
# checked against Chapter 1's own spectrum classifier and defect scanner when the
# notebook starts.
#
# > This is the **instructor solutions** notebook. It runs clean end to end against the live API and ends by asserting that every check passed. Student version: `05_assignment.ipynb`.
#
# > Answers produced by a live model vary between runs. The model answers below describe what a good submission shows; the check cells test properties that hold for any competent run, not recorded outputs.

# %%
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
GRADER = Grader('Chapter 1 — Introduction — Triaging submissions to an ontology registry with Claude')

import re, time
import statistics as st
from typing import Iterable
import dspy
import pandas as pd
import ch01_agentic as A
from agentlab import evaluation as ev, ontology as ont
from agentlab.sparql import SparqlStore
pd.set_option("display.width", 140)
pd.set_option("display.max_colwidth", 70)

problems = A.validate_gold()
assert not problems, problems      # the gold labels agree with Chapter 1's engine
train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
ALL = train + dev + test
ROW = {ex.id: ex for ex in ALL}
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}; gold labels validated")

# %% [markdown]
# ### The corpus and the policy
#
# One row per submission. `level` and `raw_smells` are what Chapter 1's classifier and
# scanner report (validated above); `smells` and `decision` are the review board's gold
# answer under the policy.

# %%
print(A.INTAKE_POLICY)
pd.DataFrame([{"id": ex.id, "split": ex.split, "team": ex.team, "declared": ex.declared_level,
               "level": ex.level, "raw_smells": ex.raw_smells, "smells": ex.smells,
               "decision": ex.decision} for ex in ALL])

# %% [markdown]
# ## Where the submissions live, and how to load them
#
# There are no separate `.ttl` files to download. The 24 submissions are **embedded as
# Turtle text** in `ch01_agentic.py` (the list `A.SUBMISSIONS`), so the problem set runs
# with no file paths and no triplestore. Each entry is an `A.Submission`; `A.get(id)`
# returns one, and its `.turtle` attribute is a complete Turtle document (prefix header
# included).
#
# Three ways to load one, from lowest to highest level:
#
# | you want | call | you get |
# |---|---|---|
# | the raw text | `A.get("safety-incidents").turtle` | `str` (Turtle) |
# | an RDF graph to inspect in Python | `ont.load_graph(A.get(id).turtle)` (= `rdflib.Graph().parse(data=..., format="turtle")`) | `rdflib.Graph` |
# | a SPARQL store to query it | `SparqlStore.in_memory(A.get(id).turtle)` | `store.select(...)` returns `list[dict]` |
#
# The next cell prints one submission, loads it three ways, and **exports all 24 as `.ttl`
# files** under `artifacts/ch01_submissions/`, so you can open them in Protégé or
# any RDF editor. Editing those files does not change the corpus; the module is the source
# of truth.

# %%
from rdflib import Graph

sub = A.get("safety-incidents")
print(sub.turtle)

g = ont.load_graph(sub.turtle)                       # rdflib.Graph
print(f"{len(g)} triples;", ont.classify_spectrum(g)["level"], ";",
      sorted(ont.smell_summary(g)))

store = SparqlStore.in_memory(sub.turtle)            # SPARQL over the same triples
print(store.select("SELECT ?c WHERE { ?c a owl:Class } ORDER BY ?c")[:3])

out_dir = agentlab.artifacts_dir() / "ch01_submissions"
out_dir.mkdir(parents=True, exist_ok=True)
for s in A.SUBMISSIONS:
    (out_dir / f"{s.id}.ttl").write_text(s.turtle, encoding="utf-8")
print(f"\nexported {len(A.SUBMISSIONS)} files to {out_dir}")

# %% [markdown]
# ## Background — the system you are building
#
# This section explains the moving parts and **why** they are shaped the way they are. The
# problems ask you to make design decisions; these are the concepts those decisions are
# about.
#
# ```
#  submission id
#       │
#       ▼
#  A.gather_evidence ──── code measures: intake form, metrics, spectrum position, scanner findings
#       │
#       ├──────────────────────────────┐
#       ▼                              ▼
#  the policy as code (A1)        DSPy program (B2):
#  = the deterministic control    ONE Claude call interprets the evidence
#       │                              │
#       └──────────────┬───────────────┘
#                      ▼
#       answer = level, smells, decision, report
#                      │
#      scorer (B1) compares with the gold labels ──► score + named violations + notes
#                      │
#      report scorer (B3) checks the written report by code
#                      │
#      Part C: write the policy into the instruction, and measure the noise
#      Part D: 40 real FIBO modules — and a policy clause that breaks on them
#      Part E: the Semantic Intelligence Platform's own ontology
# ```
#
# ### 1. The task: intake triage
#
# A team submits an ontology; the registry answers four things: its **level** on the
# ontology spectrum, the **defects** to report, a **decision**, and a **report** to the
# team. The first three follow mechanically from the policy and the measurements; the
# fourth is language. That split is the reason the problem set is built the way it is: it
# lets you measure exactly how faithfully Claude applies written rules, and shows where a
# model adds something code cannot.
#
# The **spectrum classifier** (`ont.classify_spectrum`) is cumulative: any subsumption
# (or `skos:broader`) makes a *taxonomy*; SKOS relations (`broader`, `related`, …) make a
# *thesaurus*; restrictions, disjointness, equivalence or property characteristics **on
# top of a hierarchy** make a *formal-ontology*. The **scanner** (`ont.scan_smells`)
# returns one finding per defect instance. Both are in `agentlab/ontology.py`; read them
# with `agentlab.show(ont.classify_spectrum)`.
#
# ### 2. Evidence bundle, and "tools measure, the model interprets"
#
# `A.gather_evidence(id)` computes the intake form, the graph metrics, the spectrum
# position and the scanner findings, and returns them as one JSON document. The B2 program
# gives that document to Claude in a **single** call. The design principle: put
# measurement in code (exact, free, repeatable) and use the model only for interpretation
# and language. It makes the system cheaper and easier to evaluate, and it leaves exactly
# one instruction to change.
#
# ### 3. DSPy — signature, predictor, module
#
# * A **signature** (`class X(dspy.Signature)`) is the typed contract of one LM call:
#   input fields, output fields, their descriptions, and an **instruction** (the
#   docstring, or `.with_instructions(...)`). It replaces a hand-written prompt string.
# * A **predictor** (`dspy.Predict(signature)`) turns the signature into a prompt, makes
#   one LM call and parses the reply back into typed fields.
# * A **module** (`dspy.Module` with a `forward` method) is your program: ordinary Python
#   that calls functions and predictors. Calling it returns a `dspy.Prediction`.
#
# The point of DSPy here: the **instruction is a parameter**, separate from the code, so
# you can version, diff and review it like any other artefact — and, from Chapter 2, an
# optimiser can rewrite it. `dspy.inspect_history(n=1)` prints the exact prompt DSPy sent:
# there is no hidden prompt.
#
# ### 4. Scorer, notes and rulebook
#
# A **scorer** turns (gold row, prediction) into an `ev.ScoreReport`: a number, a list of
# **named violations** (ids from `A.INTAKE_RULEBOOK`) and **notes** that say what was
# expected. The number drives evaluation; the ids and notes drive *improvement*: here your
# own error analysis and the instruction you write by hand in Part C, and in Chapter 2 the
# GEPA optimiser, which can only fix what the feedback names. A scorer that returns only a
# number tells nobody what to change.
#
# ### Coming in later chapters
#
# The same registry returns as each agent-engineering layer is introduced: the evidence
# functions become **tools** a Claude **agent** chooses between (Chapter 3), what the B3
# report checks cannot see gets an **LLM judge** validated against reviewer labels
# (Chapter 5), evidence
# gathering is priced as an **MDP** (Chapter 6), and the triage program ships as a
# **skill** behind a gated self-improvement loop (Chapter 10).

# %% [markdown]
# ## Reference — data, types and APIs used in this problem set
#
# Read this once before Part A, and come back to it whenever a contract below names a type.
# Every problem also has its own **Contract** block, just before its TODO cell, with the
# exact signatures, what each parameter is, what must be returned, and which variables the
# check cell reads.
#
# ### Type notation
#
# `list[str]` a Python list of strings · `frozenset[str]` an immutable set ·
# `dict[str, bool]` a dict with string keys and bool values · `Iterable[str]` anything you
# can loop over (list, set, tuple, `pd.Series`) · `T | None` a `T` or `None` ·
# `pd.DataFrame` a pandas table (column names given in each contract).
#
# ### Dataset rows — `train`, `dev`, `test`, `ALL`, `ROW`
#
# `train`, `dev` and `test` are `list[dspy.Example]` (8 each); `ALL = train + dev + test`
# (24); `ROW` is `dict[str, dspy.Example]` keyed by submission id. Read fields as
# attributes (`ex.level`) or keys (`ex["level"]`). **The input** is `submission` — that is
# what `program(**ex.inputs())` passes; everything else is a gold label or metadata.
#
# | field | type | example | meaning |
# |---|---|---|---|
# | `id`, `submission` | `str` | `"safety-incidents"` | the submission id (same value; `submission` is the program input) |
# | `split` | `str` | `"train"` | `"train"`, `"dev"` or `"test"` |
# | `team` | `str` | `"Safety & Incidents"` | submitting team |
# | `declared_level` | `str` | `"formal-ontology"` | what the team *claims* on the intake form |
# | `level` | `str` | `"formal-ontology"` | gold: what the spectrum classifier *measures* |
# | `raw_smells` | `list[str]`, sorted | `["missing-label", "property-without-domain-or-range"]` | gold: every smell id the scanner finds |
# | `smells` | `list[str]`, sorted | same, minus waived ids | gold: what the policy says must be *reported* |
# | `decision` | `str` | `"revise"` | gold: `"accept"`, `"revise"` or `"reject"` |
# | `note` | `str` | | why the board labelled it so (do not use it as model input) |
#
# ### Constants
#
# | name | value |
# |---|---|
# | `ont.SPECTRUM_LEVELS` | `["controlled-vocabulary", "taxonomy", "thesaurus", "formal-ontology"]` — **ordered** from least to most formal |
# | `A.DECISIONS` | `["accept", "revise", "reject"]` |
# | `A.BLOCKING_SMELLS` | `frozenset({"subsumption-cycle", "class-as-individual", "individual-as-class", "undeclared-term"})` |
# | `A.WAIVABLE_AT` | `frozenset({"controlled-vocabulary", "thesaurus"})` — measured levels at which `no-disjointness` is waived (W1) |
# | `A.INTAKE_RULEBOOK` | `RuleBook` of 7 `Rule(id, description)`; `A.INTAKE_RULEBOOK.ids` is the ordered id list; `"x" in A.INTAKE_RULEBOOK` |
#
# **The seven scanner smell ids** (`ont.SMELL_IDS`): `subsumption-cycle`,
# `class-as-individual`, `individual-as-class`, `undeclared-term` (these four are
# blocking), `property-without-domain-or-range`, `no-disjointness`, `missing-label`.
#
# ### The evidence bundle — `A.gather_evidence(submission_id) -> str`
#
# Loads the submission, runs `ont.graph_metrics`, `ont.classify_spectrum` and
# `ont.scan_smells` on it, and returns **JSON text**:
#
# ```
# {"submission":       {"submission": str, "team": str, "declared_level": str, "purpose": str},
#  "metrics":          {"classes": int, "subclass_axioms": int, ...},
#  "spectrum":         {"level": str, "evidence": [str, ...]},
#  "scanner_counts":   {"missing-label": int, ...},
#  "scanner_findings": [{"smell": str, "subject": str, "detail": str}, ...],   # first 25
#  "imports":          {"declared": [...], "held_by_registry": int, "unresolved": [...],
#                       "undeclared_terms_declared_in_imports": [...],
#                       "undeclared_terms_unexplained": [...]}}               # empty for the 24
# ```
#
# ### Course library calls used here
#
# All of them are in `agentlab`, introduced in this chapter; `agentlab.show(f)` prints any
# of them.
#
# | call | returns / notes |
# |---|---|
# | `ev.ScoreReport(score, notes, violated)` | `score: float` in [0, 1]; `notes: list[str]`; `violated: list[str]` of rulebook ids |
# | `ev.parse_label_list(value)` | `list[str]` from a list, a JSON array string `'["a","b"]'`, a comma/space-separated string, or `None` → `[]` |
# | `ev.set_f1(predicted, gold)` | `(precision, recall, f1)` floats over two iterables of labels; both empty → `(1.0, 1.0, 1.0)` |
# | `ev.evaluate_dataset(program, dataset, scorer)` | `{"mean_score": float, "n": int, "violations": {rule_id: count}, "rows": [{"item": id, "score": float, "violated": [...]}]}` — one LM call per row |
# | `A.INTAKE_RULEBOOK.as_guidelines(preamble)` | the rules written out under a preamble: a hand-written instruction (Part C) |
# | `A.REPORT_RULEBOOK`, `A.offending_terms(id)`, `A.terms_in(id)` | the report guidelines and the measurements B3 checks them with |
# | `A.build_real_dataset()` | the 40 FIBO rows: `level`, `raw_smells`, no decision (Part D) |
# | `A.import_report(id)`, `A.registry_classes(id)`, `A.unresolved_imports(id)`, `A.undeclared_terms(id)` | what the registry knows about a submission's imports (Part D) |
# | `A.register(id, turtle, team=, declared_level=, purpose=)` | add an outside ontology to the registry (Part E) |
# | `llm.configure_dspy()` | installs Claude as DSPy's default LM and returns it (`lm`) |
# | `llm.dspy_lm(cache=False)` | a separate, uncached `dspy.LM` (C2) |
# | `with llm.meter(lm, ...) as cost:` | after the block, `cost == {"calls": int, "input_tokens": int, "output_tokens": int, "usd": float}` |
# | `agentlab.artifacts_dir()` | `Path` to `artifacts/` (created on first use) |
#
# Run the next cell to see a real row and a real evidence bundle — no API calls are made.

# %%
ex = ROW["safety-incidents"]
print("row:", {k: ex[k] for k in ("id", "declared_level", "level", "raw_smells", "smells", "decision")})
print("program input:", ex.inputs())

evidence_ref = json.loads(A.gather_evidence(ex.id))
print("\nevidence keys:", list(evidence_ref), "| declared:", evidence_ref["submission"]["declared_level"])
print("spectrum:", evidence_ref["spectrum"]["level"])
print("scanner:", [f["smell"] for f in evidence_ref["scanner_findings"]])

# %% [markdown]
# ---
#
# ## Part A — The task, and a deterministic control
#
# Before a model is involved, pin down what the task *is*. Three clauses of the policy are
# decidable from tool output; one (the report) is not. Coding the decidable ones gives you
# a reference implementation, a way to validate the gold labels, and the control that any
# Claude system must be compared with.

# %% [markdown]
# ### A1. The intake policy as code (10 pts)
#
# Implement, from the policy text (not from the gold labels):
#
# * `reportable_smells(raw, measured_level) -> list[str]` — clause 2: the sorted scanner
#   ids that must be reported, after waiver W1;
# * `intake_decision(reported, declared_level, measured_level) -> str` — clause 3:
#   `"accept"`, `"revise"` or `"reject"`. Use `ont.SPECTRUM_LEVELS` for the level order.
#
# The check runs both on all 24 submissions against the board's labels, and on edge cases
# the corpus does not contain.
#
# In writing: (a) the policy keys waiver W1 on the *measured* level, not the declared one —
# give the argument for that choice, and one submission in the corpus whose decision would
# change if it were keyed on the declared level; (b) name one question the policy text
# leaves open that you had to decide in code; (c) what does this exercise tell you about
# asking an LLM to "apply the policy"?

# %% [markdown]
# #### Background and design decisions — A1
#
# You are turning prose into a **reference implementation**. It serves two purposes
# here: it validates the gold labels, and, applied to the registry's measurements, it is
# the deterministic *control* the Claude program is compared with. Later chapters reuse it
# as the engine of a critic (Chapter 3) and of an MDP (Chapter 6). So it must follow the **policy text**,
# not the labels. If you tune it until the labels match, you can no longer detect a wrong
# label.
#
# Decisions you make:
#
# * **Which level the waiver keys on.** The policy says *measured*; the written part asks
#   you to argue why that is the right design, not merely what the text says.
# * **Rule order.** Clause 3 is ordered: *reject* beats *revise* beats *accept*. Encoding it
#   as ordered checks makes the precedence explicit; a points-based encoding hides it.
# * **Level comparison.** "Below the declared level" needs an order; derive it from
#   `ont.SPECTRUM_LEVELS` rather than hard-coding one, so the policy and the classifier
#   cannot drift apart.
# * **Purity.** No tools and no model inside these functions: a critic or an MDP calls them
#   hundreds of times, and they must give the same answer every time.

# %% [markdown]
# #### Contract — A1
#
# ```python
# def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]
# def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str
# ```
#
# **`reportable_smells`** — policy clause 2.
#
# | parameter | type | value in the corpus | meaning |
# |---|---|---|---|
# | `raw` | `Iterable[str]` (list or set) | `ex.raw_smells` | smell ids the scanner found |
# | `measured_level` | `str`, one of `ont.SPECTRUM_LEVELS` | `ex.level` | the level the classifier measured |
#
# Returns a **sorted `list[str]`** with no duplicates: every id in `raw`, except
# `"no-disjointness"` when `measured_level` is in `A.WAIVABLE_AT`. Never add an id that is
# not in `raw`; do not modify `raw`. The check compares with `==` against `ex.smells`, so a
# set or an unsorted list fails.
#
# **`intake_decision`** — policy clause 3.
#
# | parameter | type | value in the corpus | meaning |
# |---|---|---|---|
# | `reported` | `Iterable[str]` | output of `reportable_smells` | the smells being reported (already waived) |
# | `declared_level` | `str` | `ex.declared_level` | what the team claimed |
# | `measured_level` | `str` | `ex.level` | what the classifier measured |
#
# Returns exactly one of `"accept"`, `"revise"`, `"reject"`, decided **in this order**:
# `"reject"` if `reported` contains any id in `A.BLOCKING_SMELLS`; else `"revise"` if
# `reported` is non-empty **or** `measured_level` comes *before* `declared_level` in
# `ont.SPECTRUM_LEVELS`; else `"accept"`.
#
# | call | returns |
# |---|---|
# | `reportable_smells({"no-disjointness", "missing-label"}, "controlled-vocabulary")` | `["missing-label"]` |
# | `reportable_smells(["no-disjointness"], "formal-ontology")` | `["no-disjointness"]` |
# | `intake_decision(["subsumption-cycle", "missing-label"], "formal-ontology", "taxonomy")` | `"reject"` |
# | `intake_decision([], "thesaurus", "taxonomy")` | `"revise"` (over-promises) |
# | `intake_decision([], "controlled-vocabulary", "formal-ontology")` | `"accept"` (exceeds the declaration) |
#
# Both functions are pure: no tools, no model. B2 and Part C compare Claude with them.

# %% assignment
def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]:
    """Policy clause 2 (see Contract A1): sorted reportable smell ids after waiver W1."""
    # TODO
    raise NotImplementedError

def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str:
    """Policy clause 3 (see Contract A1): "accept", "revise" or "reject"."""
    # TODO
    raise NotImplementedError

# %% solution
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

# %%
# Marking scheme for A1 -- do not edit.
with GRADER.check('A1', points=6):
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

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# **(a) Measured, not declared.** The waiver exists because a navigation vocabulary makes no
# disjointness commitment; whether a submission *is* such a vocabulary is a fact about the
# artefact, which the classifier measures, not about the form. Keying it on the declaration
# would let any team silence a defect by ticking "thesaurus". The corpus contains exactly
# that case: **customer-complaints** declares *thesaurus* but has no SKOS relations
# (measured *taxonomy*); keyed on the declaration, `no-disjointness` would be waived and
# the decision would still be *revise* only because of the over-promise — while
# **accessibility-services** (declared *taxonomy*, measured *thesaurus*) would lose its
# waiver and flip from *accept* to *revise*.
#
# **(b) Open questions** a good answer names one of: does a submission that *exceeds* its
# declaration need correcting (the policy says accept, but the registry entry is then
# wrong the other way); are duplicate findings of the same id one defect or several (the
# scanner reports `property-without-domain-or-range` twice for *station-assets*; the
# policy talks about ids); when a blocking and a non-blocking defect co-occur, must the
# report still list both (yes — clause 2 is independent of clause 3). Each is a decision
# the code makes silently and a model makes differently on different days.
#
# **(c)** Three of four clauses are decidable, and the deterministic version is exact,
# free and auditable. An LLM asked to "apply the policy" is being asked to re-implement
# this function from prose, probabilistically. That is worth doing only for what cannot be
# coded — here the report — or when the policy is too large or too fluid to code; and the
# coded clauses are then the ideal *test* of whether the model follows written rules.

# %% [markdown]
# ---
#
# ## Part B — Build the graders and the Claude program
#
# The guidelines a scorer can report are in `A.INTAKE_RULEBOOK` — ids plus the sentence
# that says what to do instead:

# %%
for rule in A.INTAKE_RULEBOOK:
    print(f"{rule.id:24s} {rule.description[:95]}")

# %% [markdown]
# ### B1. A diagnostic triage scorer (12 pts)
#
# Implement `intake_scorer(gold, pred) -> ev.ScoreReport`. `gold` is a dataset row
# (`level`, `raw_smells`, `smells`, `decision`); `pred` has `level`, `smells` (anything
# `ev.parse_label_list` accepts), `decision`, `report`.
#
# `score = 0.3 * level_ok + 0.4 * smell_f1 + 0.3 * decision_ok`, where level and decision
# are compared after `strip().lower()`, and `smell_f1` is `ev.set_f1(pred, gold.smells)`.
# Violations (list them in `A.INTAKE_RULEBOOK` order, without duplicates):
#
# | condition | violated |
# |---|---|
# | level or decision not in the allowed labels | `use-label-vocabulary` |
# | a valid level, but wrong | `cite-spectrum-evidence` |
# | a gold smell not reported | `report-all-smells` |
# | a reported smell the scanner found but the policy waives | `apply-waivers` |
# | a reported smell the scanner did not find | `no-unsupported-claims` |
# | a valid decision, but wrong | `decide-by-policy` |
# | an empty report (no score change) | `ground-in-tool-output` |
#
# `notes` must say what was expected for every wrong field — that text is what you (and, from Chapter 2, GEPA) read.
# Why separate `apply-waivers` from `no-unsupported-claims`? Both are "reported something
# not in gold", but they call for different fixes, and feedback that cannot tell them
# apart cannot teach either.

# %% [markdown]
# #### Background and design decisions — B1
#
# The scorer is the most reused piece of the problem set: it grades the baseline and the
# hand-written instruction here, and in later chapters it becomes GEPA's objective, the
# agent's score and the MDP's reward. Write its **notes** for a reader who will rewrite the
# prompt (Background §4): in Part C that reader is you, in Chapter 2 it is GEPA.
#
# Decisions you make:
#
# * **Weights.** 0.3 / 0.4 / 0.3 is given; notice what it implies: a perfect decision with
#   the wrong level still earns 0.7.
# * **Partial credit for smells** via F1 rather than all-or-nothing: an optimiser (or you) gets a
#   gradient (reporting 2 of 3 defects beats reporting none), and precision and recall
#   errors stay separate.
# * **Normalisation.** Accept `" Taxonomy "` but not `"hierarchy"`: be tolerant about
#   format and strict about vocabulary.
# * **Distinct violation ids for distinct fixes**: `apply-waivers` (knows the scanner, not
#   the policy) versus `no-unsupported-claims` (invents defects). If the feedback merges
#   them, the optimiser cannot learn either fix.
# * **The report does not change the score** but still records a violation: the report is
#   graded by an LLM judge in Chapter 5; here you only notice that it is missing.

# %% [markdown]
# #### Contract — B1
#
# ```python
# WEIGHTS = {"level": 0.3, "smells": 0.4, "decision": 0.3}
# def intake_scorer(gold: dspy.Example, pred) -> ev.ScoreReport
# ```
#
# | parameter | type | fields read | meaning |
# |---|---|---|---|
# | `gold` | `dspy.Example` (a dataset row) | `level`, `raw_smells`, `smells`, `decision` | the board's answer |
# | `pred` | any object with attributes (usually `dspy.Prediction`) | `level`, `smells`, `decision`, `report` | the system's answer |
#
# **Read `pred` defensively**: a field may be missing, `None`, or oddly formatted. Use
# `getattr(pred, "level", "")`; normalise `level` and `decision` with
# `str(...).strip().lower()`; parse `smells` with `ev.parse_label_list(...)` (it accepts a
# list, a JSON string such as `'["a", "b"]'`, a comma-separated string, or `None`); treat
# `report` as empty when `str(...).strip() == ""`.
#
# **Returns** `ev.ScoreReport(score, notes, violated)`:
#
# * `score: float` = `0.3 * level_ok + 0.4 * smell_f1 + 0.3 * decision_ok`, where `level_ok`
#   and `decision_ok` are 1.0 or 0.0 and `smell_f1 = ev.set_f1(pred_smells, gold.smells)[2]`.
#   The report never changes the score.
# * `violated: list[str]` — the rule ids from the table in the brief, **each at most once,
#   in `A.INTAKE_RULEBOOK.ids` order**. Only the ids in that rulebook are allowed.
# * `notes: list[str]` — one sentence per wrong field that states the **expected** value
#   (for example the correct decision); a final summary line is fine.
#
# How to split "reported something not in gold": let `extra = pred_smells - set(gold.smells)`.
# Ids in `extra ∩ gold.raw_smells` were found but waived → `apply-waivers`; ids in
# `extra - gold.raw_smells` were never found → `no-unsupported-claims`.
#
# | gold row | prediction | score | violated |
# |---|---|---|---|
# | `signalling-equipment` | perfect | 1.0 | `[]` |
# | same | `level="hierarchy"` | 0.7 | `["use-label-vocabulary"]` |
# | same | `smells=["subsumption-cycle"]` (misses one of two) | 0.3 + 0.4·(2/3) + 0.3 | `["report-all-smells"]` |
# | same | perfect, but `report="  "` | 1.0 | `["ground-in-tool-output"]` |

# %% assignment
WEIGHTS = {"level": 0.3, "smells": 0.4, "decision": 0.3}

def intake_scorer(gold: dspy.Example, pred) -> ev.ScoreReport:
    """0.3*level + 0.4*smell F1 + 0.3*decision, with rulebook violations (see Contract B1)."""
    # TODO
    raise NotImplementedError

# %% solution
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

# %%
# Marking scheme for B1 -- do not edit.
with GRADER.check('B1', points=10):
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

# %% [markdown]
# ### B2. The Claude triage program, and its baseline (10 pts)
#
# Tools measure, the model interprets: the program gathers evidence deterministically
# (`A.gather_evidence(submission)` — record, metrics, spectrum, scanner findings) and makes
# **one** LM call.
#
# 1. Write a signature `IntakeTriage` with input `evidence` and outputs `level`,
#    `smells` (`list[str]`), `decision`, `report`, and a factory
#    `TriageProgram(instruction=BASELINE_INSTRUCTION)` returning a `dspy.Module` with a
#    single `dspy.Predict` whose forward takes `submission`. Field descriptions are part of
#    the prompt — write them as you would brief a colleague (manual marks). The baseline
#    instruction deliberately does **not** contain the policy.
# 2. Configure Claude (`lm = llm.configure_dspy()`), run once on `train[0]` (`smoke`).
# 3. Evaluate on `dev` with `ev.evaluate_dataset` inside `llm.meter(lm)`; store
#    `baseline_dev` and `baseline_dev_cost`.
#
# In writing: an error analysis of the baseline — for each non-perfect item, which
# guideline and why you think Claude did it — and compare with the control (A1's functions applied to the evidence, 1.0 by construction). Which
# errors come from *not knowing the policy*, and which from *not reading the evidence*?

# %% [markdown]
# #### Background and design decisions — B2
#
# This is the "tools measure, model interprets" design (Background §2–3): deterministic
# evidence gathering, then **one** Claude call through a DSPy predictor. The baseline
# instruction deliberately omits the policy, so the baseline shows how Claude behaves
# *without* the rules, and Part C shows how much writing them down is worth.
#
# Decisions you make:
#
# * **Signature fields and descriptions.** They are part of the prompt. Listing the allowed
#   labels in a field description ("one of: accept, revise, reject") is cheap and often
#   fixes vocabulary errors before any optimisation.
# * **Output types.** `smells: list[str]` makes DSPy ask for, and parse, a list; a `str`
#   field would leave the parsing to you (and to `ev.parse_label_list`).
# * **One predictor, not several.** One instruction is one thing to optimise and one thing to
#   attribute a change to. Splitting level, smells and decision into three calls would
#   triple cost and make each change harder to attribute.
# * **What goes into the prompt.** The whole evidence bundle, not the Turtle source: the
#   model interprets measurements; it does not re-derive them from raw RDF.

# %% [markdown]
# #### Contract — B2
#
# ```python
# BASELINE_INSTRUCTION: str                       # given; do not add the policy to it
# class IntakeTriage(dspy.Signature): ...
# def TriageProgram(instruction: str = BASELINE_INSTRUCTION) -> dspy.Module
# lm, smoke, baseline_dev, baseline_dev_cost
# ```
#
# **`IntakeTriage`** — exactly one input field and four output fields:
#
# | field | kind | type | content |
# |---|---|---|---|
# | `evidence` | `dspy.InputField` | `str` | the JSON text from `A.gather_evidence(...)` |
# | `level` | `dspy.OutputField` | `str` | one spectrum level |
# | `smells` | `dspy.OutputField` | `list[str]` | smell ids to report |
# | `decision` | `dspy.OutputField` | `str` | accept / revise / reject |
# | `report` | `dspy.OutputField` | `str` | a short report to the team |
#
# **`TriageProgram(instruction)`** returns a `dspy.Module` that:
#
# * holds **exactly one** `dspy.Predict` on `IntakeTriage` whose instruction is `instruction`
#   (use `IntakeTriage.with_instructions(instruction)`), so that
#   `list(TriageProgram("x").named_predictors())[0][1].signature.instructions == "x"`;
# * has `forward(self, submission: str) -> dspy.Prediction`, which calls
#   `A.gather_evidence(submission)` and passes the result as `evidence=`.
#
# It is called as `program(**ex.inputs())`, i.e. `program(submission="station-facility-types")`,
# and returns a prediction with `.level`, `.smells`, `.decision`, `.report`.
#
# **Variables the check reads**
#
# | name | type | how to produce it |
# |---|---|---|
# | `lm` | `dspy.LM` | `llm.configure_dspy()` |
# | `smoke` | `dspy.Prediction` | `TriageProgram()(**train[0].inputs())` — one billed call |
# | `baseline_dev` | `dict` | `ev.evaluate_dataset(TriageProgram(), dev, intake_scorer)` (shape in the Reference) |
# | `baseline_dev_cost` | `dict` | `with llm.meter(lm) as baseline_dev_cost:` around the evaluation |

# %% assignment
BASELINE_INSTRUCTION = ("You review ontology submissions to Meridian Rail's ontology "
                        "registry. From the evidence, give the submission's level, the "
                        "defects to report, the intake decision and a report to the team.")

# TODO: class IntakeTriage(dspy.Signature): ...
# TODO: def TriageProgram(instruction=BASELINE_INSTRUCTION): ...

lm = llm.configure_dspy()
smoke = None               # TODO
# TODO: baseline_dev, baseline_dev_cost

raise NotImplementedError

# %% solution
BASELINE_INSTRUCTION = ("You review ontology submissions to Meridian Rail's ontology "
                        "registry. From the evidence, give the submission's level, the "
                        "defects to report, the intake decision and a report to the team.")

class IntakeTriage(dspy.Signature):
    """Triage one submission to the ontology registry from the gathered evidence."""

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

# %%
# Marking scheme for B2 -- do not edit.
with GRADER.check('B2', points=4):
    assert set(IntakeTriage.input_fields) == {"evidence"}
    assert {"level", "smells", "decision", "report"} <= set(IntakeTriage.output_fields)
    program = TriageProgram("custom instruction")
    assert len(list(program.named_predictors())) == 1
    assert list(program.named_predictors())[0][1].signature.instructions == "custom instruction"
    assert isinstance(smoke.level, str) and smoke.level.strip()
    assert baseline_dev["n"] == len(dev) == 8
    assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
    assert {"calls", "usd"} <= set(baseline_dev_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# The analysis to hand in is of *your* run. In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook) the baseline scored **0.80 on `dev`**,
# with violations `decide-by-policy` ×4 and `apply-waivers` ×1:
#
# * **Level** was right on every item: the classifier's level is in the evidence and
#   Claude copies it.
# * **Smells**: reported faithfully from the scanner, so the one error is *over*-reporting on
#   a waived thesaurus (`apply-waivers` on *accessibility-services*): W1 is only in the
#   policy, so this is a *not-knowing-the-policy* error that no amount of evidence fixes.
# * **Decision** is where the baseline loses: on *depot-register*, *procurement-documents*
#   and *interlocking-import* it chose *revise* where the policy says *reject* (it does not
#   know which defects are blocking), and it sent the waived thesaurus back for revision.
#
# Against the control (1.0 by construction) the gap is policy knowledge, not evidence
# reading, which predicts Part C: writing the policy into the instruction should close it.
# Cost: 8 calls, ≈ $0.04 — about half a cent per triage, the unit price of everything
# that follows.

# %% [markdown]
# ### B3. Grade the report — by code, not by a judge (8 pts)
#
# Level, defects and decision are decided by the policy; the **report** is where Claude is
# actually doing something code does not. Clause 4 of the policy says what a report must
# contain, and most of it is checkable without a model. `A.REPORT_RULEBOOK` names four
# guidelines; implement `report_scorer(gold, pred) -> ev.ScoreReport` that checks them,
# using the registry's measurements:
#
# | guideline | passes when | measurement |
# |---|---|---|
# | `state-the-decision` | the report contains the gold decision (`accept…`, `revis…`, `reject…`, case-insensitive) | `gold.decision` |
# | `name-offending-terms` | for each smell in `gold.smells`, one of its flagged terms is named | `A.offending_terms(gold.id)` |
# | `no-invented-terms` | every prefixed name in the report (`mr:Something`) is a term of the submission; names in the standard vocabularies (`owl:`, `rdf:`, `rdfs:`, `skos:`, `xsd:`, `dct:`) are advice, not claims, and are not checked | `A.terms_in(gold.id)` |
# | `cite-a-measurement` | the report contains at least one digit | — |
#
# `score` is the fraction of the four that pass; `name-offending-terms` counts as passed in
# proportion to the smells covered (all of them when there are none). Then score the
# baseline's reports on `dev` (`baseline_reports`): the B2 calls are cached, so this costs
# nothing.
#
# In writing: which guideline do the baseline's reports break most? Name one property of a
# good report that this scorer cannot see, and say what would be needed to check it (you
# will build that in Chapter 5).

# %% [markdown]
# #### Background and design decisions — B3
#
# The written report is the part of the task where a model adds value, so it is the part
# you most need to measure — and the part people hand straight to an LLM judge. Much of
# what makes a report useful is mechanical and checkable for free: does it say the
# decision, does it name what to fix, does it invent terms. Check those by code first;
# reserve a judge (Chapter 5) for what code cannot see, such as whether the advice is
# *right*.
#
# Decisions you make:
#
# * **Lenient on wording, strict on content.** `revis` matches "revise" and "revision";
#   a term matches with or without its prefix and in any case.
# * **What counts as invented.** Only prefixed names (`mr:Platform`) are checked: they are
#   claims about the submission's vocabulary. Plain English words are not.
# * **Partial credit** for naming terms, so a report that covers two of three defects
#   scores better than one that covers none.

# %% [markdown]
# #### Contract — B3
#
# ```python
# def report_scorer(gold: dspy.Example, pred) -> ev.ScoreReport
# baseline_reports: dict   # ev.evaluate_dataset(TriageProgram(), dev, report_scorer)
# ```
#
# | helper | returns |
# |---|---|
# | `A.offending_terms(id)` | `{"subsumption-cycle": ["LinesideEquipment"], "no-disjointness": ["Signal"]}` — local names per smell |
# | `A.terms_in(id)` | `set[str]` of local names of every IRI in the submission |
# | `A.REPORT_RULEBOOK.ids` | the four guideline ids, in order |
#
# `violated` lists the failed guidelines in `A.REPORT_RULEBOOK.ids` order; `notes` say what
# was missing (the decision expected, the terms not named, the invented names).
#
# | gold row | report | score | violated |
# |---|---|---|---|
# | `signalling-equipment` | "Reject: mr:LinesideEquipment and mr:Signal form a cycle; 3 siblings under mr:Signal lack disjointness." | 1.0 | `[]` |
# | same | "Rejected. Please fix the hierarchy." | 0.5 | `["name-offending-terms", "cite-a-measurement"]` |
# | same | "Reject: mr:Platform has 2 problems with mr:Signal and mr:LinesideEquipment." | 0.75 | `["no-invented-terms"]` |

# %% assignment
def report_scorer(gold, pred) -> ev.ScoreReport:
    report = str(getattr(pred, "report", "") or "")
    # TODO: the four checks from the table, in A.REPORT_RULEBOOK order.
    raise NotImplementedError

baseline_reports = None   # TODO: ev.evaluate_dataset(TriageProgram(), dev, report_scorer)

# %% solution
DECISION_STEM = {"accept": "accept", "revise": "revis", "reject": "reject"}
PREFIXED = re.compile(r"\b([a-z][a-z0-9-]*):([A-Za-z_][\w-]*)")
STANDARD = {"owl", "rdf", "rdfs", "skos", "xsd", "dct", "dcterms"}   # advice may cite these

def report_scorer(gold, pred) -> ev.ScoreReport:
    report = str(getattr(pred, "report", "") or "")
    low = report.lower()
    notes, violated, passed = [], [], 0.0

    if DECISION_STEM[gold.decision] in low:
        passed += 1
    else:
        violated.append("state-the-decision")
        notes.append(f"The report does not state the decision ({gold.decision!r}).")

    flagged = A.offending_terms(gold.id)
    covered, missing = 0, []
    for smell in gold.smells:
        terms = flagged.get(smell, [])
        if any(re.search(rf"\b{re.escape(t.lower())}\b", low) for t in terms):
            covered += 1
        else:
            missing.append(f"{smell} ({', '.join(terms)})")
    passed += covered / len(gold.smells) if gold.smells else 1.0
    if missing:
        violated.append("name-offending-terms")
        notes.append(f"Defects reported without naming the flagged term: {missing}.")

    known = {t.lower() for t in A.terms_in(gold.id)}
    invented = sorted({name for prefix, name in PREFIXED.findall(report)
                       if prefix not in STANDARD and name.lower() not in known})
    if invented:
        violated.append("no-invented-terms")
        notes.append(f"Names terms the submission does not contain: {invented}.")
    else:
        passed += 1

    if re.search(r"\d", report):
        passed += 1
    else:
        violated.append("cite-a-measurement")
        notes.append("Cites no number from the evidence.")
    return ev.ScoreReport(passed / 4, notes, violated)

with llm.meter(lm) as report_cost:          # cached B2 calls: expect usd 0.0
    baseline_reports = ev.evaluate_dataset(TriageProgram(), dev, report_scorer)
print("report mean:", baseline_reports["mean_score"], baseline_reports["violations"], report_cost)

# %%
# Marking scheme for B3 -- do not edit.
with GRADER.check('B3', points=6):
    sig = ROW["signalling-equipment"]
    R = lambda text: dspy.Prediction(report=text)
    cases = [
        ("Reject: mr:LinesideEquipment and mr:Signal form a cycle; 3 siblings under "
         "mr:Signal lack disjointness.", 1.0, []),
        ("Rejected. Please fix the hierarchy.", 0.5, ["name-offending-terms", "cite-a-measurement"]),
        ("Reject: mr:Platform has 2 problems with mr:Signal and mr:LinesideEquipment.", 0.75,
         ["no-invented-terms"]),
        ("Reject: break the cycle at mr:LinesideEquipment; add owl:AllDisjointClasses under "
         "mr:Signal (3 siblings).", 1.0, []),
        ("Revise the cycle between LinesideEquipment and Signal (2 axioms).", 0.75,
         ["state-the-decision"]),
    ]
    for text, score, violated in cases:
        r = report_scorer(sig, R(text))
        assert abs(r.score - score) < 1e-9 and r.violated == violated, (text, r.score, r.violated)
    assert report_scorer(sig, R("Reject; the cycle via LinesideEquipment, 2 siblings.")).score == 0.875
    assert baseline_reports["n"] == len(dev)
    assert all(v in A.REPORT_RULEBOOK for v in baseline_reports["violations"])

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook) the baseline's reports scored **0.81 on `dev`**, and the failures were not
# the ones you might expect:
#
# * `name-offending-terms` **never** failed: Claude names the flagged terms reliably when
#   the evidence lists them.
# * `state-the-decision` failed **4** times — exactly the four items where the *decision*
#   was wrong. The report faithfully states the model's own (wrong) decision. A report
#   check is only as good as the decision it checks against.
# * `cite-a-measurement` failed twice: short "reject" letters with no count in them.
# * `no-invented-terms` never fired here, but it did fire in an earlier version of this
#   scorer — on `owl:AllDisjointClasses`, which is good advice, not an invention. That is why the
#   scorer skips the standard vocabularies: a scorer has false positives too, and you find
#   them by reading the failures.
#
# What this scorer cannot see: whether the *advice* is right (which axiom of a cycle to
# remove), whether the tone suits the team, whether the report would actually let the
# team fix the submission. Those need a reader — a validated LLM judge in Chapter 5, or a
# human reviewer. Check by code what code can check, so the judge is asked only what needs
# judgement.

# %% [markdown]
# ---
#
# ## Part C — Write the policy into the prompt — and report it honestly
#
# The baseline does not know the policy. The cheapest fix is to write it down: the
# rulebook *is* the policy, phrased as instructions. Whether that helps is an empirical
# question, and the answer is only worth something on data you did not look at while
# writing it (**`test`**), with its cost, and next to the run-to-run noise.

# %% [markdown]
# ### C1. Write the policy into the instruction (10 pts)
#
# Two contenders on `test`, each evaluated inside its own `llm.meter(lm)`:
#
# * `"baseline"`: `TriageProgram()` from B2;
# * `"guidelines"`: the policy and the report guidelines written into the prompt by hand:
#   `A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION) + "\n" +
#   A.REPORT_RULEBOOK.as_guidelines("The report to the team:")`.
#
# Build `c1` with columns `program`, `test_mean`, `violations`, `report_mean` (B3's
# scorer on the same answers: the calls are cached, so it is free), `eval_usd`,
# `instruction_chars`, and save the guidelines instruction to
# `agentlab.artifacts_dir() / "ch01_registry_triage_instruction.txt"`.
#
# In writing: which violations did the guidelines remove, and which remain? Did the
# report guidelines move `report_mean`? For each that
# remains, is it a *not-knowing-the-policy* error or a *not-reading-the-evidence* error (B2)?
# What does the longer instruction cost on every future call?

# %% [markdown]
# #### Background and design decisions — C1
#
# A change to the program is a finding only if it beats the program you already have, on
# data neither was tuned on. Here the change is free to make (you write the guidelines by
# hand), so the only costs are the evaluation and the longer instruction, paid on every
# call.
#
# Decisions you make:
#
# * **Which split.** `dev` is where you looked at failures in B2; `test` has not been
#   looked at, so only `test` can tell you whether the guidelines generalise.
# * **What to compare.** Mean score and the violation histogram: the mean says how much,
#   the histogram says *which rules* the change fixed.
# * **The instruction is an artefact.** Save it, read it, and treat it like code under
#   review: it will run on every future call. In Chapter 2 an optimiser (GEPA) proposes
#   instructions like this one automatically, and this hand-written version is the
#   baseline it has to beat.

# %% [markdown]
# #### Contract — C1
#
# **`c1`** — a 2-row DataFrame, both evaluated on `test`, each inside its own `llm.meter(lm)`:
#
# | column | type | content |
# |---|---|---|
# | `program` | `str` | `"baseline"`, `"guidelines"` |
# | `test_mean` | `float` | `ev.evaluate_dataset(...)["mean_score"]` |
# | `violations` | `dict` | `ev.evaluate_dataset(...)["violations"]` |
# | `report_mean` | `float` | `ev.evaluate_dataset(program, test, report_scorer)["mean_score"]` |
# | `eval_usd` | `float` | the `"usd"` of that evaluation's meter |
# | `instruction_chars` | `int` | the length of the program's instruction |
#
# Also:
#
# | name | type | content |
# |---|---|---|
# | `guidelines_instruction` | `str` | the two rulebooks written out, as above |
# | `results_c1` | `dict[str, dict]` | the two `evaluate_dataset` results, keyed by program name |
# | `instruction_path` | `pathlib.Path` | `agentlab.artifacts_dir() / "ch01_registry_triage_instruction.txt"`, containing `guidelines_instruction` |

# %% assignment
guidelines_instruction = (A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION) + "\n"
                          + A.REPORT_RULEBOOK.as_guidelines("The report to the team:"))

# TODO: evaluate "baseline" and "guidelines" on test, each in its own llm.meter(lm);
#       build results_c1 and the DataFrame c1; save the instruction to instruction_path.
results_c1 = {}
c1 = None
instruction_path = None
raise NotImplementedError

# %% solution
guidelines_instruction = (A.INTAKE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION) + "\n"
                          + A.REPORT_RULEBOOK.as_guidelines("The report to the team:"))

contenders = {"baseline": BASELINE_INSTRUCTION, "guidelines": guidelines_instruction}
results_c1, rows = {}, []
for name, instruction in contenders.items():
    with llm.meter(lm) as cost:
        results_c1[name] = ev.evaluate_dataset(TriageProgram(instruction), test, intake_scorer)
        reports = ev.evaluate_dataset(TriageProgram(instruction), test, report_scorer)  # cached
    rows.append({"program": name, "test_mean": results_c1[name]["mean_score"],
                 "violations": results_c1[name]["violations"],
                 "report_mean": reports["mean_score"], "eval_usd": cost["usd"],
                 "instruction_chars": len(instruction)})
c1 = pd.DataFrame(rows)

instruction_path = agentlab.artifacts_dir() / "ch01_registry_triage_instruction.txt"
instruction_path.write_text(guidelines_instruction, encoding="utf-8")
print(guidelines_instruction)
c1

# %%
# Marking scheme for C1 -- do not edit.
with GRADER.check('C1', points=5):
    assert isinstance(c1, pd.DataFrame) and set(c1["program"]) == {"baseline", "guidelines"}
    assert {"test_mean", "violations", "report_mean", "eval_usd", "instruction_chars"} <= set(c1.columns)
    ids = lambda rows: {ex.id for ex in rows}
    assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
    for name in ("baseline", "guidelines"):
        assert {r["item"] for r in results_c1[name]["rows"]} == ids(test), "report on test"
    assert c1.set_index("program").loc["guidelines", "instruction_chars"] > \
        c1.set_index("program").loc["baseline", "instruction_chars"]
    assert instruction_path.is_file()
    assert instruction_path.read_text(encoding="utf-8") == guidelines_instruction

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook) the guidelines took the **test** score from **0.84 to 1.00** and removed every
# violation (`decide-by-policy` ×3 and `apply-waivers` ×1 before); the report score went
# from **0.91 to 1.00**. Both remaining classes of error were *not-knowing-the-policy*:
# once the decision rule and W1 were in the prompt, Claude applied them.
#
# The cost: the instruction grew from 186 to about 1,600 characters, paid on every call;
# the test evaluation cost ≈ $0.042 → ≈ $0.048. At registry volumes that is negligible, but
# it is the price to state. The honest headline is "with the policy written down, Claude
# applied it without error on 8 held-out submissions" — and Part D shows what that
# statement does *not* cover: whether the policy itself is right.

# %% [markdown]
# ### C2. Is the difference bigger than the noise? (8 pts)
#
# Eight test items at temperature 1.0: one item is 0.125 of the mean. Estimate the noise.
# With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, `with dspy.context(lm=fresh)`),
# run the baseline and the guidelines programs on `test` three times each; store the mean
# scores in `runs = {"baseline": [..3..], "guidelines": [..3..]}` and the cost in `c2_cost`.
#
# Set `verdict_c2` to `"significant"` if `|mean_guidelines - mean_baseline| > 2 *
# max(sd_guidelines, sd_baseline)` (sample sd), else `"not significant"`. In writing: what
# does this say about C1, and what would a credible evaluation of the triage system need?

# %% [markdown]
# #### Background and design decisions — C2
#
# Claude samples at temperature 1.0, and each split has 8 items, so a single number moves
# by 0.125 per item. Before claiming that the guidelines helped, measure how much a score
# moves when **nothing** changes. DSPy caches identical requests, so repeated runs return
# the same answer unless you use an uncached LM (`cache=False`).
#
# Decisions you make:
#
# * **How many repeats.** Three is the minimum for a standard deviation; say what it can
#   and cannot resolve.
# * **The decision rule.** The rule here (difference greater than twice the larger sd) is
#   deliberately simple; the written part asks what a credible evaluation would need
#   instead.

# %% [markdown]
# #### Contract — C2
#
# | name | type | content |
# |---|---|---|
# | `fresh` | `dspy.LM` | `llm.dspy_lm(cache=False)` — an uncached LM, so repeated runs really re-sample |
# | `runs` | `dict[str, list[float]]` | exactly the keys `"baseline"` and `"guidelines"`, each a list of **3** mean test scores |
# | `c2_cost` | `dict` | `llm.meter(fresh)` around all six evaluations |
# | `verdict_c2` | `str` | `"significant"` or `"not significant"` |
#
# Run the evaluations inside `with dspy.context(lm=fresh):` so the programs use the
# uncached LM. Compute the mean and the **sample** standard deviation
# (`statistics.stdev`) of each list; the verdict is `"significant"` iff
# `abs(mean_guidelines - mean_baseline) > 2 * max(sd_guidelines, sd_baseline)`. The check
# recomputes it from `runs`, so the verdict must follow from the numbers you stored.

# %% assignment
fresh = llm.dspy_lm(cache=False)

# TODO: three uncached runs of each program on test; the verdict from the numbers.
runs = {"baseline": [], "guidelines": []}
c2_cost = {}
verdict_c2 = None
raise NotImplementedError

# %% solution
fresh = llm.dspy_lm(cache=False)
runs = {"baseline": [], "guidelines": []}
with llm.meter(fresh) as c2_cost, dspy.context(lm=fresh):
    for _ in range(3):
        runs["baseline"].append(
            ev.evaluate_dataset(TriageProgram(), test, intake_scorer)["mean_score"])
        runs["guidelines"].append(
            ev.evaluate_dataset(TriageProgram(guidelines_instruction), test,
                                intake_scorer)["mean_score"])
stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
delta = stats["guidelines"][0] - stats["baseline"][0]
verdict_c2 = ("significant"
              if abs(delta) > 2 * max(stats["guidelines"][1], stats["baseline"][1])
              else "not significant")
print(stats, f"delta={delta:+.3f}", verdict_c2, c2_cost)

# %%
# Marking scheme for C2 -- do not edit.
with GRADER.check('C2', points=4):
    assert set(runs) == {"baseline", "guidelines"} and all(len(v) == 3 for v in runs.values())
    assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
    _m = {k: st.mean(v) for k, v in runs.items()}
    _s = {k: st.stdev(v) for k, v in runs.items()}
    _expected = ("significant" if abs(_m["guidelines"] - _m["baseline"]) > 2 * max(_s.values())
                 else "not significant")
    assert verdict_c2 == _expected
    assert {"calls", "usd"} <= set(c2_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook), three uncached runs each gave **baseline 0.838 ± 0.000** and **guidelines
# 1.000 ± 0.000**: a difference of 0.16 with no spread, so *significant* by the rule. (In
# an earlier run the baseline varied, 0.825 ± 0.022: the baseline's decisions are where
# run-to-run variation lives; the policy-bearing instruction was stable in both.) Stability is a property worth reporting in
# its own right — a triage system that decides differently on Tuesday is a governance
# problem even when its mean is fine.
#
# A credible evaluation still needs: (i) more items — 8 per split resolves differences of
# about ±0.1 at best; (ii) repeated runs, reported as mean ± sd or a paired bootstrap over
# items; (iii) the same items and sampling settings for every contender; (iv) the cost per
# run (≈ $0.28 for these six runs); and (v) per-field results. The sentence for the
# report: "the guidelines changed the mean test score by +0.16 over 3 runs of 8 items
# (sd 0.00 here, 0.02 in an earlier run), at ≈ $0.05 per run".

# %% [markdown]
# ### Where Chapter 2 picks this up
#
# You wrote the instruction by hand from a rulebook you already had. Chapter 2 adds the
# next layer: **GEPA**, an optimiser that reads your scorer's notes on training failures
# and rewrites the instruction itself. The discipline you used here carries over
# unchanged: learn on `train`, choose on `dev`, report on `test`, with a cost and a noise
# estimate next to every number; and the hand-written guidelines are the baseline an
# optimiser must beat.

# %% [markdown]
# ---
#
# ## Part D — Real submissions: 40 FIBO modules, and a policy that breaks on them
#
# Everything so far ran on 24 small submissions written for this problem set. A registry
# receives real ontologies. `A.build_real_dataset()` holds **40 modules of FIBO**, the
# EDM Council's Financial Industry Business Ontology (MIT licence), sampled at random
# from every FIBO domain and vendored unchanged in `fibo/`. Each row carries what the
# registry *measures* (`level`, `raw_smells`); none carries a decision. Applying the
# policy is your job — with the A1 functions you already wrote.
#
# Real modules **import** other modules. The evidence bundle's `imports` section says
# which imported ontologies the registry holds (the other FIBO modules), which it does
# not (FIBO also imports OMG Commons, which this registry does not hold), and which
# "undeclared" terms are in fact declared in an imported module.

# %%
real = A.build_real_dataset()
print(len(real), "FIBO modules;",
      pd.Series([r.level for r in real]).value_counts().to_dict())
example_real = json.loads(A.gather_evidence(real[0].id))
print(real[0].id, "->", {k: (len(v) if isinstance(v, list) else v)
                         for k, v in example_real["imports"].items()})

# %% [markdown]
# ### D1. What policy v3 does to real ontologies (8 pts)
#
# 1. Label every FIBO row with **your** A1 functions: build `real_v3`, a list of
#    `dspy.Example` rows equal to `real` plus `smells` and `decision` under policy v3
#    (`ex.copy(smells=..., decision=...).with_inputs("submission")`: `copy` does not keep
#    the input marking).
# 2. Evaluate the C1 guidelines program on `real_v3` with `intake_scorer`, inside
#    `llm.meter(lm)`; store `real_v3_eval` and `real_v3_cost`.
#
# In writing: v3 rejects most of FIBO. Read the evidence for two rejected modules. Is the
# rejection right? Which clause of the policy is wrong for real ontologies, and why did
# the 24 hand-made submissions never expose it?

# %% [markdown]
# #### Background and design decisions — D1
#
# A policy is a model of the world, and its first contact with real data is a test of it.
# The 24 submissions were self-contained: every term they use, they declare. Real
# ontologies are built from **modules** that import each other, so a module evaluated on
# its own "uses terms it never declares" by design. The scanner is not wrong — the terms
# really are undeclared *in the file*. The policy is wrong to treat that as a blocking
# defect without looking at the imports.
#
# Your A1 code is the labeller here: there are no hand labels for FIBO, and there do not
# need to be, because the policy is decidable. What you learn is what the policy decides.

# %% [markdown]
# #### Contract — D1
#
# | name | type | content |
# |---|---|---|
# | `real_v3` | `list[dspy.Example]` | the 40 rows of `real`, each with `smells = reportable_smells(row.raw_smells, row.level)` and `decision = intake_decision(smells, row.declared_level, row.level)` added |
# | `real_v3_eval` | `dict` | `ev.evaluate_dataset(TriageProgram(guidelines_instruction), real_v3, intake_scorer)` |
# | `real_v3_cost` | `dict` | `llm.meter(lm)` around that evaluation |

# %% assignment
real_v3 = []            # TODO: label each row of `real` with your A1 functions
real_v3_eval = None
real_v3_cost = {}
raise NotImplementedError

# %% solution
real_v3 = []
for row in real:
    smells = reportable_smells(row.raw_smells, row.level)
    real_v3.append(row.copy(smells=smells,
                            decision=intake_decision(smells, row.declared_level, row.level))
                   .with_inputs("submission"))          # copy() forgets which keys are inputs
print("v3 decisions:", pd.Series([r.decision for r in real_v3]).value_counts().to_dict())

with llm.meter(lm) as real_v3_cost:
    real_v3_eval = ev.evaluate_dataset(TriageProgram(guidelines_instruction), real_v3,
                                       intake_scorer)
print("guidelines program on FIBO, v3 gold:", real_v3_eval["mean_score"],
      real_v3_eval["violations"], real_v3_cost)

# %%
# Marking scheme for D1 -- do not edit.
with GRADER.check('D1', points=4):
    assert len(real_v3) == 40 and {r.id for r in real_v3} == {r.id for r in real}
    for r in real_v3:
        assert r.smells == reportable_smells(r.raw_smells, r.level)
        assert r.decision in A.DECISIONS
    assert sum(r.decision == "reject" for r in real_v3) > 20, "v3 should reject most of FIBO"
    assert {r["item"] for r in real_v3_eval["rows"]} == {r.id for r in real_v3}
    assert {"calls", "usd"} <= set(real_v3_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Policy v3 **rejects 33 of the 40 FIBO modules** and revises the other 7 — it accepts
# none. Nearly every rejection is `undeclared-term`, and the import report shows why: the
# "undeclared" classes are declared in modules the submission imports (other FIBO modules)
# or in OMG Commons, which FIBO imports and this registry does not hold. FIBO is not
# broken; clause 3 treats a property of a *file* as a property of the *ontology*. The 24
# hand-made submissions never exposed it because none of them imports anything — a test
# set written by the policy's authors shares the policy's blind spots.
#
# What the program did is the second lesson. In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook) the guidelines program scored
# **0.99 against v3 gold**: told to follow the policy, it rejected FIBO too, faithfully.
# A high score against a wrong policy is a wrong system, measured precisely. Note also the
# evidence: real modules cost ≈ $0.013 per triage (larger evidence), so 40 of them ≈ $0.53.

# %% [markdown]
# ### D2. Policy v4: judge a module with its imports (10 pts)
#
# Write the clause the policy is missing, implement it, and measure what it changes.
#
# 1. `findings_v4(submission_id) -> list[str]`: the scanner's smell ids, except that
#    `undeclared-term` is re-examined using the registry's imports:
#    * a term declared in a module the registry holds and the submission imports is
#      **not** a defect;
#    * a term in the namespace of an import the registry does **not** hold becomes
#      `unresolved-import` (the registry cannot check it; not blocking);
#    * any other undeclared term stays `undeclared-term` (still blocking).
# 2. `real_v4`: the FIBO rows re-labelled with `raw_smells = findings_v4(...)` and your A1
#    functions (`unresolved-import` is reported like any non-blocking smell).
# 3. `POLICY_V4_CLAUSE`: one or two sentences stating the new rule for the model, and
#    `v4_instruction = guidelines_instruction + "\n" + POLICY_V4_CLAUSE`.
# 4. Evaluate on `real_v4`, each inside `llm.meter(lm)`: the guidelines program (`"v3"`)
#    and `TriageProgram(v4_instruction)` (`"v4"`). Build `d2` with columns `program`,
#    `real_mean`, `violations`, `eval_usd`.
#
# In writing: how did the decisions change from v3 to v4? Is `unresolved-import` a defect
# of the submission or of the registry? Would you publish a FIBO module the registry
# cannot fully check?

# %% [markdown]
# #### Background and design decisions — D2
#
# The fix belongs in the policy and in the measurement code, not in the prompt alone:
# whether a term is declared in an import is a fact the registry can compute, so it is
# computed (`A.registry_classes`, `A.unresolved_imports`), and the model is only told the
# rule. The new finding `unresolved-import` separates "this ontology is wrong" from "we
# cannot check this ontology" — a distinction the original policy collapsed into
# *reject*.
#
# | helper | returns |
# |---|---|
# | `A.undeclared_terms(id)` | IRIs the scanner flags as `undeclared-term` in the file alone |
# | `A.registry_classes(id)` | classes declared in the modules of the submission's registry import closure |
# | `A.unresolved_imports(id)` | IRIs of imports (direct or transitive) the registry does not hold |
# | `A.import_report(id)` | all of the above, as the evidence bundle shows it |

# %% [markdown]
# #### Contract — D2
#
# | name | type | content |
# |---|---|---|
# | `findings_v4` | `(str) -> list[str]` | sorted smell ids, as specified above |
# | `real_v4` | `list[dspy.Example]` | the 40 rows with `raw_smells`, `smells`, `decision` under v4 |
# | `POLICY_V4_CLAUSE` | `str` | the new rule, in words a model can follow |
# | `v4_instruction` | `str` | `guidelines_instruction + "\n" + POLICY_V4_CLAUSE` |
# | `d2` | `pd.DataFrame` | rows `"v3"`, `"v4"`; columns `program`, `real_mean`, `violations`, `eval_usd` |

# %% assignment
def findings_v4(submission_id: str) -> list[str]:
    # TODO: re-examine undeclared-term with A.registry_classes and A.unresolved_imports
    raise NotImplementedError

real_v4 = []
POLICY_V4_CLAUSE = "TODO"
v4_instruction = None
d2 = None

# %% solution
def findings_v4(submission_id: str) -> list[str]:
    g = ont.load_graph(A.get(submission_id).turtle)
    smells = set(ont.smell_summary(g))
    if "undeclared-term" in smells:
        smells.discard("undeclared-term")
        declared_elsewhere = A.registry_classes(submission_id)
        unresolved = A.unresolved_imports(submission_id)
        for term in A.undeclared_terms(submission_id):
            if term in declared_elsewhere:
                continue
            if any(term.startswith(ns) for ns in unresolved):
                smells.add("unresolved-import")
            else:
                smells.add("undeclared-term")
    return sorted(smells)

real_v4 = []
for row in real:
    raw = findings_v4(row.id)
    smells = reportable_smells(raw, row.level)
    real_v4.append(row.copy(raw_smells=raw, smells=smells,
                            decision=intake_decision(smells, row.declared_level, row.level))
                   .with_inputs("submission"))
print("v4 decisions:", pd.Series([r.decision for r in real_v4]).value_counts().to_dict())

POLICY_V4_CLAUSE = (
    "- Judge a module together with its imports (policy v4): a term the scanner reports as "
    "undeclared is not a defect if the evidence lists it under "
    "undeclared_terms_declared_in_imports. A term that belongs to an import the registry "
    "does not hold (imports.unresolved) is reported as unresolved-import, which is not "
    "blocking. Only the remaining undeclared terms are undeclared-term.")
v4_instruction = guidelines_instruction + "\n" + POLICY_V4_CLAUSE

rows = []
for name, instruction in (("v3", guidelines_instruction), ("v4", v4_instruction)):
    with llm.meter(lm) as cost:
        result = ev.evaluate_dataset(TriageProgram(instruction), real_v4, intake_scorer)
    rows.append({"program": name, "real_mean": result["mean_score"],
                 "violations": result["violations"], "eval_usd": cost["usd"]})
d2 = pd.DataFrame(rows)
d2

# %%
# Marking scheme for D2 -- do not edit.
with GRADER.check('D2', points=6):
    for r in real:
        mine = findings_v4(r.id)
        assert mine == sorted(set(mine))
        terms = A.undeclared_terms(r.id)
        known, unresolved = A.registry_classes(r.id), A.unresolved_imports(r.id)
        rest = [t for t in terms if t not in known]
        external = [t for t in rest if any(t.startswith(ns) for ns in unresolved)]
        assert ("unresolved-import" in mine) == bool(external), r.id
        assert ("undeclared-term" in mine) == (len(external) < len(rest)), r.id
        assert set(mine) - {"undeclared-term", "unresolved-import"} == \
            set(r.raw_smells) - {"undeclared-term"}, r.id
    assert len(real_v4) == 40 and all(r.decision in A.DECISIONS for r in real_v4)
    assert sum(r.decision == "reject" for r in real_v4) < sum(r.decision == "reject" for r in real_v3)
    assert isinstance(d2, pd.DataFrame) and set(d2["program"]) == {"v3", "v4"}
    assert POLICY_V4_CLAUSE != "TODO" and v4_instruction.endswith(POLICY_V4_CLAUSE)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Under v4 the rejections disappear: **36 modules move to *revise* and 4 to *accept***,
# none is rejected. The remaining findings are real — missing labels, properties without a
# domain or range — plus `unresolved-import` on the 22 modules whose terms come from OMG
# Commons.
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook) the old (v3) instruction scored **0.60 against v4 gold** (`decide-by-policy` and
# `no-unsupported-claims` on most modules: it still rejects and still reports
# `undeclared-term`), while the v4 instruction scored **1.00**: given one clause and an
# `imports` section in the evidence, Claude applied the new rule on every module. That is
# the deployment pattern worth remembering: compute the fact in code (which terms are
# declared in an import), state the rule in the instruction, and the model's job becomes
# reading, not deciding what an import means.
#
# `unresolved-import` is a property of the **registry**, not of the submission: FIBO is
# not wrong to import OMG Commons; the registry simply does not hold it. That is why it
# must not block, and why the right operational fix is to load the missing imports into
# the registry rather than send every FIBO team a *revise*. Publishing a module the
# registry cannot fully check is a governance decision — state it in the policy, which is
# what v4 does.

# %% [markdown]
# ---
#
# ## Part E — Into the Semantic Intelligence Platform
#
# The registry's job in this repository is real: the **Semantic Intelligence Platform**
# (SIP, `sip/`) builds ontologies with agents and publishes them, and a registry decides
# whether they are fit to depend on. Run SIP's end-to-end demo (offline, deterministic,
# free: its agents use simulators), export the ontology it built, and triage it.

# %% [markdown]
# ### E1. Triage SIP's own ontology (6 pts)
#
# 1. Run `semantic_intelligence.demo.run(verbose=False)`; export the `fleet` project's
#    ontology with `P.call("pat", "fleet", "io.export")`.
# 2. Register it: `A.register("sip-fleet", ttl, team="SIP fleet project",
#    declared_level="formal-ontology", purpose=<the project's ORSD purpose, from
#    P.call("pat", "fleet", "scope.specification")>)`.
# 3. Decide it with your A1 functions (`sip_decision`, from the scanner's findings and the
#    measured level), and run your best program on it (`sip_pred`).
#
# In writing: would you publish SIP's fleet ontology? Which SIP lifecycle stage
# (scope → acquire → model → validate → review) should have caught each finding, and did
# the program's report tell the fleet team what to change?

# %% [markdown]
# #### Contract — E1
#
# | name | type | content |
# |---|---|---|
# | `sip_ttl` | `str` | the exported Turtle |
# | `sip_sub` | `A.RealSubmission` | the registered submission (`id == "sip-fleet"`) |
# | `sip_decision` | `str` | your A1 decision for it |
# | `sip_pred` | `dspy.Prediction` | your best program's answer for `submission="sip-fleet"` |
#
# The SIP package lives at `<repository root>/sip`; the cell below puts it on the path.

# %%
SIP_ROOT = next((p / "sip" for p in [Path.cwd(), *Path.cwd().parents]
                 if (p / "sip" / "semantic_intelligence").is_dir()), None)
assert SIP_ROOT is not None, "Part E needs the repository's sip/ folder"
sys.path.insert(0, str(SIP_ROOT))
from semantic_intelligence import demo as sip_demo

# %% assignment
sip_ttl = None          # TODO: run the demo, export the fleet ontology
sip_sub = None
sip_decision = None
sip_pred = None
raise NotImplementedError

# %% solution
sip_run = sip_demo.run(verbose=False)            # offline simulators: no API calls
SIP = sip_run["platform"]
sip_ttl = SIP.call("pat", "fleet", "io.export")
purpose = SIP.call("pat", "fleet", "scope.specification")["specification"]["purpose"]
sip_sub = A.register("sip-fleet", sip_ttl, team="SIP fleet project",
                     declared_level="formal-ontology", purpose=purpose)

sip_graph = ont.load_graph(sip_ttl)
sip_level = ont.classify_spectrum(sip_graph)["level"]
sip_smells = reportable_smells(ont.smell_summary(sip_graph), sip_level)
sip_decision = intake_decision(sip_smells, "formal-ontology", sip_level)
print("policy:", sip_level, sip_smells, "->", sip_decision)

with llm.meter(lm) as sip_cost:
    sip_pred = TriageProgram(guidelines_instruction)(submission="sip-fleet")
print("program:", sip_pred.level, sip_pred.smells, sip_pred.decision, sip_cost)
print(sip_pred.report)

# %%
# Marking scheme for E1 -- do not edit.
with GRADER.check('E1', points=3):
    assert isinstance(sip_ttl, str) and len(ont.load_graph(sip_ttl)) > 20
    assert sip_sub.id == "sip-fleet" and A.get("sip-fleet") is sip_sub
    assert sip_decision in A.DECISIONS
    assert str(getattr(sip_pred, "decision", "")).strip().lower() in A.DECISIONS
    assert str(getattr(sip_pred, "report", "")).strip()

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook), SIP's fleet ontology measured as a **formal ontology** (7 classes, 6
# subsumption axioms, 3 existential restrictions), with one finding: **`no-disjointness`
# under `fleet#Vehicle`** (two sibling classes, car and truck, and no disjointness axiom).
# Policy and program agreed: **revise**. The program's report named `fleet#Vehicle`, cited
# the counts, and asked for disjointness between the sibling subclasses — a report the
# fleet team could act on.
#
# Which SIP stage should have caught it: **model**. SIP's ModelingCopilot proposed the
# existential restrictions but never disjointness, and SIP's quality checks (Semantic
# Turkey's ICV set) do not ask for it. The practical consequence: the registry's scanner
# belongs in SIP's *validate* stage, before a human closes the review gate, so intake never
# sees a finding the platform could have caught. That is how the course's checks become
# platform checks.

# %% [markdown]
# ---
#
# ## Grading rubric
#
# | Part | Problem | Auto | Manual | Pts |
# |---|---|---|---|---|
# | A | A1 The intake policy as code | 6 | 4 | 10 |
# | B | B1 A diagnostic triage scorer | 10 | 2 | 12 |
# | B | B2 The Claude triage program, and its baseline | 4 | 6 | 10 |
# | B | B3 Grade the report — by code, not by a judge | 6 | 2 | 8 |
# | C | C1 Write the policy into the instruction | 5 | 5 | 10 |
# | C | C2 Is the difference bigger than the noise? | 4 | 4 | 8 |
# | D | D1 What policy v3 does to real ontologies | 4 | 4 | 8 |
# | D | D2 Policy v4: judge a module with its imports | 6 | 4 | 10 |
# | E | E1 Triage SIP's own ontology | 3 | 3 | 6 |
# | **Total** | | | | **82** |
#
# *Manual* points are for the written answers and for the quality of the engineering evidence (splits, sample sizes, cost, honest negative results).

# %% [markdown]
# ---
#
# ## Self-test
#
# Re-run this cell after finishing. It lists every auto-graded problem and whether its check passed.

# %%
AUTO_GRADED = ['A1', 'B1', 'B2', 'B3', 'C1', 'C2', 'D1', 'D2', 'E1']
_ = GRADER.summary(AUTO_GRADED)

# %% solution
GRADER.assert_all_passed(AUTO_GRADED)
