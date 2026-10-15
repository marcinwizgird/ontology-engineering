# %% [markdown] assignment
# # Problem Set: Formalising a hospital access policy with Claude
# ### Chapter 2 — First-Order Logic and Reasoning
#
# **Topic coverage:** Keet §2.1 (syntax, semantics, formalising natural language), §2.2 (reasoning, finite models, resolution); course notebooks 01–03 of this chapter. Tools: DSPy, and GEPA through `agentlab.optimize` (new in this chapter); the Chapter 2 model checker.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 86 (Part A 20 / Part B 30 / Part C 28 / Part D 8); 47 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 10–12 hours.
#
# **API budget:** ≈ \$0.65 **measured** for one full run in the reference run (`claude-sonnet-5-5` for the formaliser, `claude-opus-5-5` for GEPA's reflection; ≈ 350 short calls; the GEPA run cost \$0.30). Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# St. Brigid's Hospital is replacing a manual access review with an automated
# **compliance checker**. The data-governance office writes its access policy in
# English; the checker needs it in first-order logic so it can *decide* whether a
# request is permitted. You are the ontology engineer on the project. Your brief:
#
# 1. **Build the grader first.** The office will not accept "the model looks right".
#    Formalisations are graded by a decision procedure — equivalence over finite
#    models — with partial credit and diagnostics that name the mistake.
# 2. **Build a Claude formaliser** that turns policy sentences into formulas over a
#    fixed, reviewed vocabulary, measure it on a development split, and improve it
#    with GEPA. Report on a **held-out test split** you never optimised against,
#    with the cost of getting there and the run-to-run noise.
#
# The policy corpus (48 sentences, split 16/16/16 by item: 24 written for the course and
# 24 modelled on HIPAA Privacy Rule provisions on research use, minors and guardians, and
# minimum-necessary access) and the predicate vocabulary are provided in `ch02_agentic.py`.
# Part D tests the result on a domain it never saw: the requirements of SIP's demo.
#
# > The original brief went on to a **compliance agent** that proves its verdicts and an
# > **MDP over proof search**. They return in Chapter 3 (tool-calling agents) and
# > Chapter 6 (MDPs), the chapters that introduce those layers.
#
# ## Submission requirements
#
# 1. **This notebook, executed top to bottom**, with every `TODO` implemented and every *Your answer* cell written.
# 2. **The artefacts it saves** under `artifacts/` (optimised instructions, run logs) — they are evidence, not by-products.
# 3. **Honest reporting.** A number without its split, its sample size and its cost earns no credit. Report the runs you did, including the ones that did not improve anything.
#
# The check cells are the marking scheme for the auto-graded points; do not edit them. The final self-test prints your auto-graded subtotal.
#
# > Solutions: `04_solutions.ipynb` — do not open it until you have attempted every problem.

# %% [markdown] solution
# # Problem Set: Formalising a hospital access policy with Claude — Solutions
# ### Chapter 2 — First-Order Logic and Reasoning
#
# **Topic coverage:** Keet §2.1 (syntax, semantics, formalising natural language), §2.2 (reasoning, finite models, resolution); course notebooks 01–03 of this chapter. Tools: DSPy, and GEPA through `agentlab.optimize` (new in this chapter); the Chapter 2 model checker.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 86 (Part A 20 / Part B 30 / Part C 28 / Part D 8); 47 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 10–12 hours.
#
# **API budget:** ≈ \$0.65 **measured** for one full run in the reference run (`claude-sonnet-5-5` for the formaliser, `claude-opus-5-5` for GEPA's reflection; ≈ 350 short calls; the GEPA run cost \$0.30). Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# St. Brigid's Hospital is replacing a manual access review with an automated
# **compliance checker**. The data-governance office writes its access policy in
# English; the checker needs it in first-order logic so it can *decide* whether a
# request is permitted. You are the ontology engineer on the project. Your brief:
#
# 1. **Build the grader first.** The office will not accept "the model looks right".
#    Formalisations are graded by a decision procedure — equivalence over finite
#    models — with partial credit and diagnostics that name the mistake.
# 2. **Build a Claude formaliser** that turns policy sentences into formulas over a
#    fixed, reviewed vocabulary, measure it on a development split, and improve it
#    with GEPA. Report on a **held-out test split** you never optimised against,
#    with the cost of getting there and the run-to-run noise.
#
# The policy corpus (48 sentences, split 16/16/16 by item: 24 written for the course and
# 24 modelled on HIPAA Privacy Rule provisions on research use, minors and guardians, and
# minimum-necessary access) and the predicate vocabulary are provided in `ch02_agentic.py`.
# Part D tests the result on a domain it never saw: the requirements of SIP's demo.
#
# > The original brief went on to a **compliance agent** that proves its verdicts and an
# > **MDP over proof search**. They return in Chapter 3 (tool-calling agents) and
# > Chapter 6 (MDPs), the chapters that introduce those layers.
#
# > This is the **instructor solutions** notebook. It runs clean end to end against the live API and ends by asserting that every check passed. Student version: `04_assignment.ipynb`.
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
GRADER = Grader('Chapter 2 — First-Order Logic and Reasoning — Formalising a hospital access policy with Claude')

import difflib, functools, time
import dspy
import pandas as pd
import ch02_toolkit as fol
import ch02_agentic as A
from agentlab import evaluation as ev, optimize as opt

train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
GOLD = {ex.id: fol.parse(ex.gold_formula) for ex in train + dev + test}
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
print(A.vocabulary_text())

# %% [markdown]
# ---
#
# ## Part A — Semantic grading and its limits
#
# Before you let a model near the policy, decide how its output will be judged. The
# Chapter 2 model checker gives you `A.equivalent(f, g, max_size)`: two closed formulas
# agree on **every** interpretation with a domain of at most `max_size` elements.

# %% [markdown]
# ### A1. Why string similarity cannot grade formalisations (10 pts)
#
# For **three** policy items of your choice, write two alternative formalisations each:
#
# * `"equivalent"` — means the same as the gold formula but is written *differently*
#   (not just re-spaced): contraposition, De Morgan, a renamed variable, …;
# * `"mistake"` — one of the classic §2.1 errors (conjunction under a universal,
#   implication under an existential, negation scope, quantifier order).
#
# Build a DataFrame `a1` with one row per alternative and columns `item`, `kind`,
# `formula`, `equivalent` (the checker's verdict against gold) and `string_similarity`
# (`difflib.SequenceMatcher` ratio against the gold text). Choose your items so that at
# least once the *mistake* is textually closer to gold than the equivalent is.
#
# Then answer in writing: why does this rule out string overlap (BLEU, edit distance)
# as the metric for this task, and what does it imply for LLM-as-judge grading here?

# %% assignment
alternatives = {
    # "item-id": {"equivalent": "...", "mistake": "..."},
}
# TODO: fill `alternatives` for three items, then build the DataFrame `a1`.
a1 = None

raise NotImplementedError

# %% solution
alternatives = {
    "no-contractor-clinician": {
        "equivalent": "~exists x (Contractor(x) & Clinician(x))",
        "mistake": "~forall x (Contractor(x) -> Clinician(x))",      # negation scope
    },
    "some-auditor-external": {
        "equivalent": "exists y (External(y) & Auditor(y))",
        "mistake": "exists x (Auditor(x) -> External(x))",           # implication under exists
    },
    "clinicians-are-employees": {
        "equivalent": "forall x (~Employee(x) -> ~Clinician(x))",    # contraposition
        "mistake": "forall x (Clinician(x) & Employee(x))",          # conjunction under forall
    },
}
gold_text = {ex.id: ex.gold_formula for ex in train + dev + test}
rows = []
for item, alt in alternatives.items():
    for kind, text in alt.items():
        rows.append({
            "item": item, "kind": kind, "formula": text,
            "equivalent": A.equivalent(fol.parse(text), GOLD[item]),
            "string_similarity": round(
                difflib.SequenceMatcher(None, text, gold_text[item]).ratio(), 3),
        })
a1 = pd.DataFrame(rows)
a1

# %%
# Marking scheme for A1 -- do not edit.
with GRADER.check('A1', points=6):
    assert isinstance(a1, pd.DataFrame) and len(alternatives) >= 3
    assert {"item", "kind", "formula", "equivalent", "string_similarity"} <= set(a1.columns)
    gold_text = {ex.id: ex.gold_formula for ex in train + dev + test}
    for item, alt in alternatives.items():
        assert A.equivalent(fol.parse(alt["equivalent"]), GOLD[item]), f"{item}: 'equivalent' is not"
        assert not A.equivalent(fol.parse(alt["mistake"]), GOLD[item]), f"{item}: 'mistake' is equivalent"
        assert alt["equivalent"].replace(" ", "") != gold_text[item].replace(" ", ""), \
            f"{item}: rewrite the equivalent, don't copy gold"
    sim = a1.pivot(index="item", columns="kind", values="string_similarity")
    assert (sim["mistake"] > sim["equivalent"]).any(), "find a case where the mistake looks closer"

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the table the negation-scope mistake for *no-contractor-clinician* scores ≈0.9
# similarity while the correct De Morgan rewrite scores ≈0.6: string overlap rewards the
# *wrong* answer. Meaning in FOL is fixed by the models a formula admits, and small edits
# (moving one `~`, swapping `&` for `->`) change the models completely, while large
# edits (contraposition, De Morgan, renaming) change nothing. Any surface metric
# therefore both penalises correct answers and rewards classic errors.
#
# An LLM judge is better at paraphrase but is itself unvalidated and probabilistic; it
# would need its own labelled evaluation, and it would still be wrong exactly on the
# subtle scope errors this chapter is about. When a task has a decision procedure, use
# it: it is cheaper, reproducible and its "no" comes with a witness (a countermodel).

# %% [markdown]
# ### A2. What the finite-model grader can and cannot see (10 pts)
#
# (a) Using only vocabulary predicates, find a pair of closed formulas `pair` that the
# checker calls equivalent at `max_size=1` but not at `max_size=2`. (Hint: think about
# the policy items that differ only in quantifier order.)
#
# (b) The checker enumerates all `2**bits` interpretations, where `bits` is
# `A.model_space_bits(formulas, size)`. For three gold formulas with different
# signatures, build `a2` with columns `item`, `size`, `bits`, `seconds` for sizes 1–4,
# timing a fresh self-entailment check (`fol.entails([f], f, size)`) **only when
# `bits <= 16`** and recording `None` otherwise.
#
# (c) In writing: which size would you run the production grader at, and why? State
# precisely which kind of grading error remains possible at that size, and which cannot
# happen.

# %% assignment
pair = ("...", "...")       # TODO (a)

a2 = None                   # TODO (b): one row per (item, size)

raise NotImplementedError

# %% solution
pair = ("exists x forall y (Nurse(y) -> Supervises(x, y))",
        "forall y (Nurse(y) -> exists x Supervises(x, y))")
print("size 1:", A.equivalent(*map(fol.parse, pair), max_size=1),
      " size 2:", A.equivalent(*map(fol.parse, pair), max_size=2))

rows = []
for item in ["clinicians-are-employees", "records-about-patients",
             "external-auditors-no-sensitive"]:
    f = GOLD[item]
    for size in range(1, 5):
        bits = A.model_space_bits([f], size)
        seconds = None
        if bits <= 16:
            t0 = time.perf_counter()
            fol.entails([f], f, size)
            seconds = round(time.perf_counter() - t0, 4)
        rows.append({"item": item, "size": size, "bits": bits, "seconds": seconds})
a2 = pd.DataFrame(rows)
a2

# %%
# Marking scheme for A2 -- do not edit.
with GRADER.check('A2', points=5):
    f, g = (fol.parse(t) for t in pair)
    assert not fol.free_vars(f) and not fol.free_vars(g)
    assert all(p in A.VOCABULARY for p in {**fol.predicates(f), **fol.predicates(g)})
    assert A.equivalent(f, g, max_size=1) and not A.equivalent(f, g, max_size=2)
    assert isinstance(a2, pd.DataFrame) and a2["item"].nunique() >= 3
    assert set(a2["size"]) >= {1, 2, 3, 4}
    for _, grp in a2.sort_values("size").groupby("item"):
        assert list(grp["bits"]) == sorted(grp["bits"]), "bits must grow with the domain size"
        assert all((s is None or s != s) == (b > 16) for s, b in zip(grp["seconds"], grp["bits"]))

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Size 2 is the practical choice for this corpus: every gold formula has at most 12 bits
# at size 2 (≤ 4096 interpretations, well under a second), whereas at size 3 the richest
# items reach 20+ bits (millions of interpretations) and at size 4 the unary-plus-binary
# signatures are hopeless. Size 1 is not enough: (a) shows that a one-element domain
# cannot distinguish quantifier orders, the single most important error in the corpus.
#
# The remaining error is one-sided. If the grader says **not equivalent**, the
# countermodel it found is a real model separating the two readings — that verdict is
# sound at any size. If it says **equivalent**, it only means no difference exists on
# domains up to 2; two formulas that first differ at size 3 (e.g. counting-style
# statements like "at least three records") would be wrongly accepted. So the grader can
# over-award, never under-award, and the report should say "equivalent up to size 2".

# %% [markdown]
# ---
#
# ## Part B — Build the grader and the formaliser
#
# The guidelines a scorer can report are in `A.POLICY_RULEBOOK` — ids plus the sentence
# GEPA's reflection step will read:

# %%
for rule in A.POLICY_RULEBOOK:
    print(f"{rule.id:30s} {rule.description[:90]}")

# %% [markdown]
# ### B1. A staged, diagnostic scorer (14 pts)
#
# Implement `policy_scorer(gold, pred, max_size=2, vocabulary=None) -> ev.ScoreReport`
# (`vocabulary` defaults to `A.VOCABULARY`; Part D passes another one), where `gold` is a
# dataset row (`gold.gold_formula`) and `pred.formula` is the model's answer. Stages, in
# this order:
#
# | outcome | score | `violated` |
# |---|---|---|
# | empty, or `fol.parse` raises | 0.0 | `["emit-parseable-formula"]` |
# | free variables | 0.0 | `["close-every-variable"]` |
# | a predicate not in the vocabulary, a wrong arity, or any constant | 0.1 | `["use-the-vocabulary"]` |
# | well-formed but not equivalent (at `max_size`) | 0.25 | `[A.diagnose(...)]`, or `["match-the-intended-reading"]` when it returns `None` |
# | equivalent | 1.0 | `[]` |
#
# Refuse to model-check (score 0.1, `match-the-intended-reading`) when
# `A.model_space_bits([pred, gold], max_size) > 16`. For a wrong meaning, put the
# produced and intended formulas **and a countermodel** (`fol.find_countermodel(...)
# .describe()`, in whichever direction exists) in `notes` — that text is what GEPA reads.
#
# Why the partial credit? A flat zero tells an optimiser only *that* it failed; 0.1 /
# 0.25 steps give it a gradient: first be parseable, then use the vocabulary, then be
# right.

# %% assignment
MAX_BITS = 16

def policy_scorer(gold, pred, max_size: int = 2, vocabulary: dict | None = None) -> ev.ScoreReport:
    text = str(getattr(pred, "formula", "") or "").strip()
    gold_f = fol.parse(gold.gold_formula)
    # TODO: the five stages from the table, in order.
    raise NotImplementedError

# %% solution
MAX_BITS = 16

def policy_scorer(gold, pred, max_size: int = 2, vocabulary: dict | None = None) -> ev.ScoreReport:
    text = str(getattr(pred, "formula", "") or "").strip()
    gold_f = fol.parse(gold.gold_formula)
    if not text:
        return ev.ScoreReport(0.0, ["No formula produced."], ["emit-parseable-formula"])
    try:
        f = fol.parse(text)
    except Exception as exc:
        return ev.ScoreReport(0.0, [f"Does not parse ({exc}). Answer with the formula "
                                    f"alone, e.g. 'forall x (P(x) -> Q(x))'."],
                              ["emit-parseable-formula"])
    free = fol.free_vars(f)
    if free:
        return ev.ScoreReport(0.0, [f"Free variable(s) {sorted(free)}: bind them."],
                              ["close-every-variable"])
    vocab = vocabulary or A.VOCABULARY
    wrong = {p: a for p, a in fol.predicates(f).items()
             if p not in vocab or vocab[p][0] != a}
    consts = fol.constants_in(f)
    if wrong or consts:
        return ev.ScoreReport(0.1, [f"Outside the vocabulary: predicates {wrong}, "
                                    f"constants {sorted(consts)}."],
                              ["use-the-vocabulary"])
    if A.model_space_bits([f, gold_f], max_size) > MAX_BITS:
        return ev.ScoreReport(0.1, ["Formula too large to grade; simplify it."],
                              ["match-the-intended-reading"])
    if A.equivalent(f, gold_f, max_size):
        return ev.ScoreReport(1.0, [f"Equivalent (up to size {max_size}) to "
                                    f"{gold.gold_formula}."], [])
    pitfall = A.diagnose(f, gold_f) or "match-the-intended-reading"
    notes = ["Well-formed, but not the intended reading.",
             f"  produced: {fol.to_string(f)}",
             f"  intended: {gold.gold_formula}"]
    model = (fol.find_countermodel([f], gold_f, max_size)
             or fol.find_countermodel([gold_f], f, max_size))
    if model is not None:
        notes.append("  a model where the two readings differ:")
        notes += [f"    {line}" for line in model.describe().splitlines()]
    return ev.ScoreReport(0.25, notes, [pitfall])

# %%
# Marking scheme for B1 -- do not edit.
with GRADER.check('B1', points=12):
    gold = next(ex for ex in dev if ex.id == "nurses-are-clinicians")
    P = lambda text: dspy.Prediction(formula=text)
    cases = [
        ("forall x (Nurse(x) -> Clinician(x))", 1.0, []),
        ("forall y (~Clinician(y) -> ~Nurse(y))", 1.0, []),
        ("", 0.0, ["emit-parseable-formula"]),
        ("The formula is: forall x (Nurse(x) -> Clinician(x)).", 0.0, ["emit-parseable-formula"]),
        ("forall x (Nurse(x) -> Clinician(y))", 0.0, ["close-every-variable"]),
        ("forall x (Nurse(x) -> IsClinician(x))", 0.1, ["use-the-vocabulary"]),
        ("forall x (Nurse(x) -> Treats(x))", 0.1, ["use-the-vocabulary"]),
        ("Nurse(Ana) -> Clinician(Ana)", 0.1, ["use-the-vocabulary"]),
        ("forall x (Nurse(x) & Clinician(x))", 0.25, ["universal-uses-implication"]),
        ("forall x (Clinician(x) -> Nurse(x))", 0.25, ["match-the-intended-reading"]),
    ]
    for text, score, violated in cases:
        r = policy_scorer(gold, P(text))
        assert abs(r.score - score) < 1e-9 and r.violated == violated, (text, r.score, r.violated)
        assert all(v in A.POLICY_RULEBOOK for v in r.violated)
    wrong = policy_scorer(gold, P("forall x (Clinician(x) -> Nurse(x))"))
    assert any("domain" in n for n in wrong.notes), "a wrong reading must come with a countermodel"

# %% [markdown]
# ### B2. The formaliser as a DSPy program (7 pts)
#
# Write a signature `PolicyFormalisation` with inputs `statement` and `vocabulary` and
# output `formula`, and a factory `PolicyFormaliser(instruction)` returning a
# `dspy.Module` with a single `dspy.Predict` whose instruction is `instruction`. The
# field descriptions are part of the prompt — write them as you would brief a colleague
# (manual marks). Then configure Claude and run the program once on `train[0]`.

# %% assignment
BASELINE_INSTRUCTION = "Formalise the policy sentence in first-order logic."

# TODO: class PolicyFormalisation(dspy.Signature): ...
# TODO: def PolicyFormaliser(instruction=BASELINE_INSTRUCTION): ...

lm = llm.configure_dspy()
smoke = None     # TODO: PolicyFormaliser()(**train[0].inputs())

raise NotImplementedError

# %% solution
BASELINE_INSTRUCTION = "Formalise the policy sentence in first-order logic."

class PolicyFormalisation(dspy.Signature):
    """Formalise one sentence of a hospital access policy in first-order logic."""

    statement: str = dspy.InputField(desc="one policy sentence in English")
    vocabulary: str = dspy.InputField(
        desc="the only predicates you may use, one per line: Name(args): meaning")
    formula: str = dspy.OutputField(
        desc="one closed formula in ASCII FOL: forall/exists, ~ & | -> <->, "
             "lower-case variables, e.g. forall x (Nurse(x) -> Clinician(x))")

def PolicyFormaliser(instruction: str = BASELINE_INSTRUCTION):
    class _Formaliser(dspy.Module):
        def __init__(self):
            super().__init__()
            self.formalise = dspy.Predict(
                PolicyFormalisation.with_instructions(instruction))

        def forward(self, statement: str, vocabulary: str):
            return self.formalise(statement=statement, vocabulary=vocabulary)

    return _Formaliser()

lm = llm.configure_dspy()
smoke = PolicyFormaliser()(**train[0].inputs())
print(train[0].statement, "->", smoke.formula)

# %%
# Marking scheme for B2 -- do not edit.
with GRADER.check('B2', points=4):
    assert set(PolicyFormalisation.input_fields) == {"statement", "vocabulary"}
    assert "formula" in PolicyFormalisation.output_fields
    program = PolicyFormaliser("custom instruction")
    assert len(list(program.named_predictors())) == 1
    assert opt.instruction_of(program) == "custom instruction"
    assert isinstance(smoke.formula, str) and smoke.formula.strip()

# %% [markdown]
# ### B3. Baseline on the development split, with its cost (9 pts)
#
# Evaluate the baseline program on `dev` with `ev.evaluate_dataset`, inside
# `llm.meter(lm)` so you know what it cost. Store the result in `baseline_dev` and the
# cost in `baseline_dev_cost`. Print the per-item rows.
#
# Then write a short **error analysis**: for each non-perfect item, which guideline was
# violated and *why* you think Claude made that choice. Separate genuine logic errors from
# vocabulary/format problems — they call for different fixes.

# %% assignment
# TODO: baseline_dev = ..., baseline_dev_cost = ...

raise NotImplementedError

# %% solution
with llm.meter(lm) as baseline_dev_cost:
    baseline_dev = ev.evaluate_dataset(PolicyFormaliser(), dev, policy_scorer)
print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
print("cost:", baseline_dev_cost)
pd.DataFrame(baseline_dev["rows"])

# %%
# Marking scheme for B3 -- do not edit.
with GRADER.check('B3', points=3):
    assert baseline_dev["n"] == len(dev) == 16
    assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
    assert 0.0 <= baseline_dev["mean_score"] <= 1.0
    assert {"calls", "usd"} <= set(baseline_dev_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# A typical baseline run scores high on the plain universals and existentials and loses
# points in three places — the answer to hand in is the analysis of *your* run:
#
# * **Format/vocabulary** (0.0/0.1): wrapping the formula in prose or a code fence,
#   Unicode connectives (∀, →), or synonyms such as `Supervisor(x)` instead of the
#   listed `Supervises(x, y)`. These are prompt/format problems, fixed by stating the
#   output contract — not by teaching logic.
# * **Scope and direction** (0.25): *supervisors-of-nurses-clinicians* and
#   *contractors-no-access* nest a quantifier inside an implication; the model sometimes
#   pulls the existential out (`exists y` over the whole rule), which changes the
#   meaning. These are genuine logic errors.
# * **Quantifier order** on *every-nurse-supervised* is usually right with Claude; when
#   it is wrong, the countermodel in the notes makes it obvious.
#
# Cost: 16 calls, a few cents; this is the unit price for every later comparison.

# %% [markdown]
# ---
#
# ## Part C — Optimise with GEPA — and report it honestly
#
# GEPA rewrites the instruction by reflecting on the scorer's feedback. It is only as
# good as that feedback, it overfits small training sets, and every metric call is a
# billed request. The rules for this part: **optimise on `train`, select on `dev`,
# report on `test`** — and put a cost and a noise estimate next to every number.
#
# **First, check that there is something to optimise.** The B2 formaliser, with its
# careful field descriptions, is already at or near the ceiling on a current model (the
# live run scored 1.0 on `dev`); GEPA then has no failures to reflect on and returns the
# instruction unchanged. Part C therefore optimises the formaliser a team typically ships
# *first*: `BareFormaliser`, the same task with a bare signature and no syntax hints. On
# `claude-sonnet-5-5` it writes correct logic in Unicode notation (`∀x (Clinician(x) →
# Employee(x))`), and none of it parses. Whether GEPA can recover the output contract from
# the scorer's feedback alone is the question.

# %%
class BareFormalisation(dspy.Signature):
    """Formalise the policy sentence in first-order logic."""

    statement: str = dspy.InputField()
    vocabulary: str = dspy.InputField()
    formula: str = dspy.OutputField()


def BareFormaliser(instruction: str = BASELINE_INSTRUCTION):
    """The first version a team ships: the task, and nothing about the output syntax."""
    class _Bare(dspy.Module):
        def __init__(self):
            super().__init__()
            self.formalise = dspy.Predict(BareFormalisation.with_instructions(instruction))

        def forward(self, statement: str, vocabulary: str):
            return self.formalise(statement=statement, vocabulary=vocabulary)

    return _Bare()


with llm.meter(lm) as headroom_cost:
    headroom = ev.evaluate_dataset(BareFormaliser(), dev, policy_scorer)
print("bare formaliser on dev:", headroom["mean_score"], headroom["violations"], headroom_cost)

# %% [markdown]
# ### C1. A budgeted GEPA run with a held-out report (12 pts)
#
# 1. Build the GEPA feedback metric from your scorer and `A.POLICY_RULEBOOK`, and a
#    separate reflection LM (`llm.reflection_lm()`).
# 2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
#    inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
# 3. Compare the bare baseline (`BareFormaliser()`) and the tuned program on **`test`**
#    with `opt.compare`
#    (store as `c1`) and print `c1.report()`.
# 4. Save the tuned instruction to `agentlab.artifacts_dir() /
#    "ch02_policy_formaliser_instruction.txt"` — it is a learned artefact and belongs
#    under review like code.
#
# In writing: read the instruction diff. Which guidelines did GEPA put into words, which
# did it miss, and did it add anything that is *not* a guideline (over-fitting to the
# sixteen training sentences)?

# %% assignment
GEPA_BUDGET = 60
# TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
instruction_path = agentlab.artifacts_dir() / "ch02_policy_formaliser_instruction.txt"

raise NotImplementedError

# %% solution
GEPA_BUDGET = 60
gepa_metric = opt.make_gepa_metric(policy_scorer, A.POLICY_RULEBOOK)
reflect = llm.reflection_lm()
with llm.meter(lm, reflect) as gepa_cost:
    tuned = opt.run_gepa(BareFormaliser(), train, gepa_metric, valset=dev,
                         max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
c1 = opt.compare(BareFormaliser(), tuned, test, policy_scorer)
print(c1.report())
print("\nGEPA cost:", gepa_cost)

instruction_path = agentlab.artifacts_dir() / "ch02_policy_formaliser_instruction.txt"
instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")

# %%
# Marking scheme for C1 -- do not edit.
with GRADER.check('C1', points=6):
    ids = lambda rows: {ex.id for ex in rows}
    assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
    assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
    assert c1.before["n"] == c1.after["n"] == len(test)
    assert instruction_path.is_file()
    assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
    assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 200

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook): the bare formaliser scored **0.00** on `test` — every answer was correct logic
# in Unicode notation (`∀x (… → …)`), and every one failed `emit-parseable-formula`. GEPA
# (budget 60; 68 calls including the reflection model, **$0.30**) took it to **1.00**.
#
# Read the diff, because it is three different things:
#
# * **The output contract, recovered from feedback alone**: "ASCII only, never ∀ ∃ ¬ ∧ ∨ →",
#   the connective table, "the formula alone, no prose or code fences". This is what the
#   `emit-parseable-formula` feedback named on every training failure, and it is the whole
#   of the score gain.
# * **The guidelines, rediscovered**: universal → implication, existential → conjunction,
#   "no A is B", quantifier order, "only if". These were already right in the baseline's
#   (unparseable) logic; GEPA wrote them down anyway.
# * **Over-fitting**: the instruction names the hospital ("one hospital data-access policy
#   sentence"), lists this vocabulary's predicates, and even quotes one training failure
#   verbatim ("The graded wrong answer was: …"). None of that helps on a new sentence;
#   all of it is paid on every call (2,782 characters), and Part D shows what it costs on
#   a new domain.
#
# The general lesson: GEPA learns what the metric's feedback names, from what fails on
# `train`. It found the format problem because the scorer named it; it could not tell the
# general rules from the hospital-specific ones, because nothing in the feedback did.

# %% [markdown]
# ### C2. Was the optimiser worth it? Three programs, one table (8 pts)
#
# Add a third contender: the **hand-written guidelines** —
# `BareFormaliser(A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION))`. Evaluate baseline, guidelines
# and GEPA-tuned on `test`, each inside its own `llm.meter`, and build `c2` with columns
# `program` (`"baseline"`, `"guidelines"`, `"gepa"`), `test_mean`, `violations`,
# `eval_usd`, and `optimisation_usd` (the GEPA cost for `"gepa"`, 0 otherwise).
#
# In writing: which would you deploy, and what would change your mind? Consider score,
# per-call token cost (instruction length), optimisation cost, and maintenance.

# %% assignment
guidelines_instruction = A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
c2 = None    # TODO

raise NotImplementedError

# %% solution
guidelines_instruction = A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
contenders = {"baseline": BareFormaliser(),
              "guidelines": BareFormaliser(guidelines_instruction),
              "gepa": tuned}
rows = []
for name, program in contenders.items():
    with llm.meter(lm) as cost:
        result = ev.evaluate_dataset(program, test, policy_scorer)
    rows.append({"program": name, "test_mean": result["mean_score"],
                 "violations": result["violations"], "eval_usd": cost["usd"],
                 "optimisation_usd": gepa_cost["usd"] if name == "gepa" else 0.0,
                 "instruction_chars": len(opt.instruction_of(program))})
c2 = pd.DataFrame(rows)
c2

# %%
# Marking scheme for C2 -- do not edit.
with GRADER.check('C2', points=3):
    assert isinstance(c2, pd.DataFrame)
    assert set(c2["program"]) == {"baseline", "guidelines", "gepa"}
    assert {"test_mean", "violations", "eval_usd", "optimisation_usd"} <= set(c2.columns)
    assert c2.set_index("program").loc[["baseline", "guidelines"], "optimisation_usd"].eq(0).all()

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook), on `test`: baseline **0.00**, hand-written guidelines **1.00** (1,141
# characters, $0 to optimise), GEPA **1.00** (2,782 characters, $0.30 to optimise). The
# cheap alternative matched the optimiser. That is the usual outcome when the rulebook
# already states the policy — the rulebook *is* what the baseline lacked — and it is why
# "the optimiser helped" is only a finding when it beats the hand-written baseline.
#
# Deploy the guidelines: same score, less than half the instruction length (paid on every
# call), no optimisation cost, and every line traceable to a rule someone owns. Reach for
# GEPA when the failures are *not* known in advance — new output formats, new phrasings —
# and use its diff as a source of candidate rules to promote into the rulebook by hand.
# Part D gives a second reason to prefer the guidelines.

# %% [markdown]
# ### C3. Is the difference bigger than the noise? (8 pts)
#
# Sixteen test items and a sampling temperature of 1.0: one item moves the mean by up to
# 0.06. Estimate the noise directly. With caching **disabled**
# (`fresh = llm.dspy_lm(cache=False)` and `with dspy.context(lm=fresh): ...`), run the
# bare baseline (`BareFormaliser()`) and the GEPA-tuned programs on `test` three times each; store the mean scores
# in `runs = {"baseline": [..3..], "gepa": [..3..]}`.
#
# Compute each program's mean and sample standard deviation and set `verdict_c3` to
# `"significant"` if `|mean_gepa - mean_baseline| > 2 * max(sd_gepa, sd_baseline)`,
# else `"not significant"`. In writing: what does this say about the C1 result, and what
# would a credible evaluation of this system need?

# %% assignment
fresh = llm.dspy_lm(cache=False)
runs = {"baseline": [], "gepa": []}
# TODO: fill runs, then compute verdict_c3
verdict_c3 = None

raise NotImplementedError

# %% solution
import statistics as st

fresh = llm.dspy_lm(cache=False)
runs = {"baseline": [], "gepa": []}
with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
    for _ in range(3):
        runs["baseline"].append(
            ev.evaluate_dataset(BareFormaliser(), test, policy_scorer)["mean_score"])
        runs["gepa"].append(ev.evaluate_dataset(tuned, test, policy_scorer)["mean_score"])
stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
delta = stats["gepa"][0] - stats["baseline"][0]
verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
              else "not significant")
print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)

# %%
# Marking scheme for C3 -- do not edit.
with GRADER.check('C3', points=4):
    import statistics as _st
    assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
    assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
    _m = {k: _st.mean(v) for k, v in runs.items()}
    _s = {k: _st.stdev(v) for k, v in runs.items()}
    _expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
                 else "not significant")
    assert verdict_c3 == _expected

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook), three uncached runs each: baseline **0.00 ± 0.00**, GEPA **1.00 ± 0.00** —
# *significant* by any rule. This is the rare case where noise does not matter: a
# format failure is deterministic (Unicode never parses), and so is its fix. Most real
# comparisons are not like this — Chapter 1's baseline moved by ±0.02 between runs — so
# the habit stands: report the spread before the claim.
#
# A credible evaluation needs (i) more test items — 16 resolve differences of roughly
# ±0.07; (ii) repeated runs, reported as mean ± sd or with a paired bootstrap over items;
# (iii) the same items and sampling settings for every contender; and (iv) the cost of
# each run (≈ $0.28 for these six). The sentence for the report: "GEPA changed the mean
# test score from 0.00 to 1.00 (sd 0.00 over 3 runs of 16 items), at $0.30 to optimise —
# and hand-written guidelines did the same at no cost".

# %% [markdown]
# ---
#
# ## Part D — Does it transfer? The Semantic Intelligence Platform's requirements
#
# A formaliser is worth tuning only if what it learned is *logic*, not *hospital*. The
# Semantic Intelligence Platform (SIP, `sip/` in this repository) turns a project brief
# into competency questions; its demo brief and source document contain exactly the kind
# of sentences you have been formalising, in a different domain. `A.build_sip_dataset()`
# holds seven of them, verbatim, with gold formulas over a fleet vocabulary
# (`A.SIP_VOCABULARY`).

# %%
sip = A.build_sip_dataset()
for ex in sip:
    print(f"{ex.statement:70s} {ex.gold_formula}")
print()
print(A.sip_vocabulary_text())

# %% [markdown]
# ### D1. Does the tuned formaliser transfer? SIP's requirements (8 pts)
#
# Grade with your B1 scorer, pointed at the fleet vocabulary:
# `sip_scorer = functools.partial(policy_scorer, vocabulary=A.SIP_VOCABULARY)`. Evaluate
# the three C2 contenders (`"baseline"`, `"guidelines"`, `"gepa"`) on `sip`, each inside
# its own `llm.meter(lm)`, and build `d1` with columns `program`, `sip_mean`,
# `violations`, `eval_usd`.
#
# In writing: (a) which lines of the GEPA instruction are about *logic* (they should
# transfer) and which are about the *hospital* (they cannot)? (b) Does the ranking of the
# three programs on `sip` match their ranking on `test`? (c) SIP's RequirementsAgent writes
# competency questions as SPARQL tests; what would you change before using this
# formaliser to check that a CQ's SPARQL says what its English sentence says?

# %% [markdown]
# #### Background and design decisions — D1
#
# A held-out *test split* measures generalisation to new sentences from the same policy.
# A *transfer set* measures generalisation to a new domain — the question that decides
# whether an optimised instruction is a reusable asset or a fitted one. Seven items is
# small; read the per-item rows, not only the mean.
#
# Decisions you make:
#
# * **Same grader, new vocabulary.** The scorer's logic does not change; only the
#   vocabulary does. That is why B1 takes `vocabulary` as a parameter.
# * **No re-tuning.** Run the programs exactly as C1 and C2 left them: re-tuning on the
#   transfer set would make it a training set.

# %% [markdown]
# #### Contract — D1
#
# | name | type | content |
# |---|---|---|
# | `sip_scorer` | callable | `functools.partial(policy_scorer, vocabulary=A.SIP_VOCABULARY)` |
# | `results_d1` | `dict[str, dict]` | the three `ev.evaluate_dataset(program, sip, sip_scorer)` results, keyed by program name |
# | `d1` | `pd.DataFrame` | 3 rows; columns `program`, `sip_mean`, `violations`, `eval_usd` |

# %% assignment
sip_scorer = None      # TODO: functools.partial(policy_scorer, vocabulary=A.SIP_VOCABULARY)
results_d1 = {}
d1 = None
raise NotImplementedError

# %% solution
sip_scorer = functools.partial(policy_scorer, vocabulary=A.SIP_VOCABULARY)
results_d1, rows = {}, []
for name, program in contenders.items():
    with llm.meter(lm) as cost:
        results_d1[name] = ev.evaluate_dataset(program, sip, sip_scorer)
    rows.append({"program": name, "sip_mean": results_d1[name]["mean_score"],
                 "violations": results_d1[name]["violations"], "eval_usd": cost["usd"]})
d1 = pd.DataFrame(rows)
d1

# %%
# Marking scheme for D1 -- do not edit.
with GRADER.check('D1', points=4):
    assert isinstance(d1, pd.DataFrame) and set(d1["program"]) == {"baseline", "guidelines", "gepa"}
    assert {"sip_mean", "violations", "eval_usd"} <= set(d1.columns)
    for name in ("baseline", "guidelines", "gepa"):
        assert {r["item"] for r in results_d1[name]["rows"]} == {ex.id for ex in sip}
    gold_pred = dspy.Prediction(formula=sip[0].gold_formula)
    assert sip_scorer(sip[0], gold_pred).score == 1.0, "a SIP gold formula must score 1.0"
    assert policy_scorer(sip[0], gold_pred).violated == ["use-the-vocabulary"], \
        "the default vocabulary is still the hospital's"

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# In the reference run (`claude-sonnet-5-5`, October 2026; the executed solutions notebook), on SIP's seven requirements: baseline **0.00** (Unicode again),
# guidelines **1.00**, GEPA **0.89** (one sentence with the wrong reading).
#
# **(a)** The GEPA instruction's lines on syntax and on quantifier rules transfer; its
# lines on the hospital do not — "Translate one hospital data-access policy sentence", a
# list of the hospital's predicates, a hospital training failure quoted verbatim. On the
# fleet vocabulary they are at best wasted tokens and at worst a nudge toward the wrong
# reading, which is what the one failure shows.
#
# **(b)** The ranking changed: tied on `test`, the guidelines beat GEPA on the new domain.
# With seven items, one item is 0.14 of the mean, so this is a signal, not a proof — but it
# points the same way as the diff: what GEPA learned is partly hospital, what the rulebook
# states is only logic.
#
# **(c)** SIP's CQs pair an English question with a SPARQL `ASK`. To check them you would
# formalise the English with this program (with an instruction stripped of domain detail),
# translate the `ASK` pattern into the same FOL vocabulary (a deterministic step, since the
# CQ uses the project's own classes and properties), and compare the two with the
# Chapter 2 grader: a countermodel then shows exactly where the SPARQL test and the
# sentence disagree. The vocabulary, and its typing axioms, must come from the project's
# ontology rather than be written by hand as here.

# %% [markdown]
# ---
#
# ## Grading rubric
#
# | Part | Problem | Auto | Manual | Pts |
# |---|---|---|---|---|
# | A | A1 Why string similarity cannot grade formalisations | 6 | 4 | 10 |
# | A | A2 What the finite-model grader can and cannot see | 5 | 5 | 10 |
# | B | B1 A staged, diagnostic scorer | 12 | 2 | 14 |
# | B | B2 The formaliser as a DSPy program | 4 | 3 | 7 |
# | B | B3 Baseline on the development split, with its cost | 3 | 6 | 9 |
# | C | C1 A budgeted GEPA run with a held-out report | 6 | 6 | 12 |
# | C | C2 Was the optimiser worth it? Three programs, one table | 3 | 5 | 8 |
# | C | C3 Is the difference bigger than the noise? | 4 | 4 | 8 |
# | D | D1 Does the tuned formaliser transfer? SIP's requirements | 4 | 4 | 8 |
# | **Total** | | | | **86** |
#
# *Manual* points are for the written answers and for the quality of the engineering evidence (splits, sample sizes, cost, honest negative results).

# %% [markdown]
# ---
#
# ## Self-test
#
# Re-run this cell after finishing. It lists every auto-graded problem and whether its check passed.

# %%
AUTO_GRADED = ['A1', 'A2', 'B1', 'B2', 'B3', 'C1', 'C2', 'C3', 'D1']
_ = GRADER.summary(AUTO_GRADED)

# %% solution
GRADER.assert_all_passed(AUTO_GRADED)
