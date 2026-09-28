"""Build the Chapter 2 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch02_first_order_logic/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 2 — First-Order Logic and Reasoning",
    title="Formalising a hospital access policy with Claude",
    coverage=("Keet §2.1 (syntax, semantics, formalising natural language), §2.2 "
              "(reasoning, finite models, resolution); course notebooks 01–03 of this "
              "chapter. Tools: DSPy + GEPA, LangChain agents, the Chapter 2 model checker "
              "and resolution prover."),
    scenario="""
    St. Brigid's Hospital is replacing a manual access review with an automated
    **compliance checker**. The data-governance office writes its access policy in
    English; the checker needs it in first-order logic so it can *decide* whether a
    request is permitted. You are the ontology engineer on the project. Your brief:

    1. **Build the grader first.** The office will not accept "the model looks right".
       Formalisations are graded by a decision procedure — equivalence over finite
       models — with partial credit and diagnostics that name the mistake.
    2. **Build a Claude formaliser** that turns policy sentences into formulas over a
       fixed, reviewed vocabulary, measure it on a development split, and improve it
       with GEPA. Report on a **held-out test split** you never optimised against,
       with the cost of getting there and the run-to-run noise.
    3. **Ship a compliance agent** that answers access questions with tool-checked
       verdicts — *yes*, *no*, or *the policy does not settle it* — and never
       guesses.
    4. **Price the proofs.** Model proof search as an MDP and work out when proving is
       worth its cost.

    The policy corpus (24 sentences, split 8/8/8 by item), the predicate vocabulary,
    the formalised policy and the audit-day facts are provided in `ch02_agentic.py`.
    """,
    effort="10–12 hours",
    api_budget="≈ $6–12 estimated on `claude-opus-5` for a full run (≈ 250 model calls; "
               "GEPA is the largest line). Re-running unchanged cells is free — DSPy caches "
               "identical requests.",
)

ps.setup("""
import difflib, time
import dspy
import pandas as pd
import ch02_toolkit as fol
import ch02_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
GOLD = {ex.id: fol.parse(ex.gold_formula) for ex in train + dev + test}
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
print(A.vocabulary_text())
""")

# =========================================================================== #
ps.part("A", "Semantic grading and its limits", """
Before you let a model near the policy, decide how its output will be judged. The
Chapter 2 model checker gives you `A.equivalent(f, g, max_size)`: two closed formulas
agree on **every** interpretation with a domain of at most `max_size` elements.
""")

ps.problem("A1", "Why string similarity cannot grade formalisations", 10, """
For **three** policy items of your choice, write two alternative formalisations each:

* `"equivalent"` — means the same as the gold formula but is written *differently*
  (not just re-spaced): contraposition, De Morgan, a renamed variable, …;
* `"mistake"` — one of the classic §2.1 errors (conjunction under a universal,
  implication under an existential, negation scope, quantifier order).

Build a DataFrame `a1` with one row per alternative and columns `item`, `kind`,
`formula`, `equivalent` (the checker's verdict against gold) and `string_similarity`
(`difflib.SequenceMatcher` ratio against the gold text). Choose your items so that at
least once the *mistake* is textually closer to gold than the equivalent is.

Then answer in writing: why does this rule out string overlap (BLEU, edit distance)
as the metric for this task, and what does it imply for LLM-as-judge grading here?
""", auto_points=6)
ps.todo(
    stub="""
    alternatives = {
        # "item-id": {"equivalent": "...", "mistake": "..."},
    }
    # TODO: fill `alternatives` for three items, then build the DataFrame `a1`.
    a1 = None
    """,
    solution="""
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
    """)
ps.check("A1", """
assert isinstance(a1, pd.DataFrame) and len(alternatives) >= 3
assert {"item", "kind", "formula", "equivalent", "string_similarity"} <= set(a1.columns)
gold_text = {ex.id: ex.gold_formula for ex in train + dev + test}
for item, alt in alternatives.items():
    assert A.equivalent(fol.parse(alt["equivalent"]), GOLD[item]), f"{item}: 'equivalent' is not"
    assert not A.equivalent(fol.parse(alt["mistake"]), GOLD[item]), f"{item}: 'mistake' is equivalent"
    assert alt["equivalent"].replace(" ", "") != gold_text[item].replace(" ", ""), \\
        f"{item}: rewrite the equivalent, don't copy gold"
sim = a1.pivot(index="item", columns="kind", values="string_similarity")
assert (sim["mistake"] > sim["equivalent"]).any(), "find a case where the mistake looks closer"
""")
ps.written("""
In the table the negation-scope mistake for *no-contractor-clinician* scores ≈0.9
similarity while the correct De Morgan rewrite scores ≈0.6: string overlap rewards the
*wrong* answer. Meaning in FOL is fixed by the models a formula admits, and small edits
(moving one `~`, swapping `&` for `->`) change the models completely, while large
edits (contraposition, De Morgan, renaming) change nothing. Any surface metric
therefore both penalises correct answers and rewards classic errors.

An LLM judge is better at paraphrase but is itself unvalidated and probabilistic; it
would need its own labelled evaluation, and it would still be wrong exactly on the
subtle scope errors this chapter is about. When a task has a decision procedure, use
it: it is cheaper, reproducible and its "no" comes with a witness (a countermodel).
""")

ps.problem("A2", "What the finite-model grader can and cannot see", 10, """
(a) Using only vocabulary predicates, find a pair of closed formulas `pair` that the
checker calls equivalent at `max_size=1` but not at `max_size=2`. (Hint: think about
the policy items that differ only in quantifier order.)

(b) The checker enumerates all `2**bits` interpretations, where `bits` is
`A.model_space_bits(formulas, size)`. For three gold formulas with different
signatures, build `a2` with columns `item`, `size`, `bits`, `seconds` for sizes 1–4,
timing a fresh self-entailment check (`fol.entails([f], f, size)`) **only when
`bits <= 16`** and recording `None` otherwise.

(c) In writing: which size would you run the production grader at, and why? State
precisely which kind of grading error remains possible at that size, and which cannot
happen.
""", auto_points=5)
ps.todo(
    stub="""
    pair = ("...", "...")       # TODO (a)

    a2 = None                   # TODO (b): one row per (item, size)
    """,
    solution="""
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
    """)
ps.check("A2", """
f, g = (fol.parse(t) for t in pair)
assert not fol.free_vars(f) and not fol.free_vars(g)
assert all(p in A.VOCABULARY for p in {**fol.predicates(f), **fol.predicates(g)})
assert A.equivalent(f, g, max_size=1) and not A.equivalent(f, g, max_size=2)
assert isinstance(a2, pd.DataFrame) and a2["item"].nunique() >= 3
assert set(a2["size"]) >= {1, 2, 3, 4}
for _, grp in a2.sort_values("size").groupby("item"):
    assert list(grp["bits"]) == sorted(grp["bits"]), "bits must grow with the domain size"
    assert all((s is None or s != s) == (b > 16) for s, b in zip(grp["seconds"], grp["bits"]))
""")
ps.written("""
Size 2 is the practical choice for this corpus: every gold formula has at most 12 bits
at size 2 (≤ 4096 interpretations, well under a second), whereas at size 3 the richest
items reach 20+ bits (millions of interpretations) and at size 4 the unary-plus-binary
signatures are hopeless. Size 1 is not enough: (a) shows that a one-element domain
cannot distinguish quantifier orders, the single most important error in the corpus.

The remaining error is one-sided. If the grader says **not equivalent**, the
countermodel it found is a real model separating the two readings — that verdict is
sound at any size. If it says **equivalent**, it only means no difference exists on
domains up to 2; two formulas that first differ at size 3 (e.g. counting-style
statements like "at least three records") would be wrongly accepted. So the grader can
over-award, never under-award, and the report should say "equivalent up to size 2".
""")

# =========================================================================== #
ps.part("B", "Build the grader and the formaliser", """
The guidelines a scorer can report are in `A.POLICY_RULEBOOK` — ids plus the sentence
GEPA's reflection step will read:
""")
ps.code("""
for rule in A.POLICY_RULEBOOK:
    print(f"{rule.id:30s} {rule.description[:90]}")
""")

ps.problem("B1", "A staged, diagnostic scorer", 14, """
Implement `policy_scorer(gold, pred, max_size=2) -> ev.ScoreReport`, where `gold` is a
dataset row (`gold.gold_formula`) and `pred.formula` is the model's answer. Stages, in
this order:

| outcome | score | `violated` |
|---|---|---|
| empty, or `fol.parse` raises | 0.0 | `["emit-parseable-formula"]` |
| free variables | 0.0 | `["close-every-variable"]` |
| a predicate not in `A.VOCABULARY`, a wrong arity, or any constant | 0.1 | `["use-the-vocabulary"]` |
| well-formed but not equivalent (at `max_size`) | 0.25 | `[A.diagnose(...)]`, or `["match-the-intended-reading"]` when it returns `None` |
| equivalent | 1.0 | `[]` |

Refuse to model-check (score 0.1, `match-the-intended-reading`) when
`A.model_space_bits([pred, gold], max_size) > 16`. For a wrong meaning, put the
produced and intended formulas **and a countermodel** (`fol.find_countermodel(...)
.describe()`, in whichever direction exists) in `notes` — that text is what GEPA reads.

Why the partial credit? A flat zero tells an optimiser only *that* it failed; 0.1 /
0.25 steps give it a gradient: first be parseable, then use the vocabulary, then be
right.
""", auto_points=12)
ps.todo(
    stub="""
    MAX_BITS = 16

    def policy_scorer(gold, pred, max_size: int = 2) -> ev.ScoreReport:
        text = str(getattr(pred, "formula", "") or "").strip()
        gold_f = fol.parse(gold.gold_formula)
        # TODO: the five stages from the table, in order.
        raise NotImplementedError
    """,
    solution="""
    MAX_BITS = 16

    def policy_scorer(gold, pred, max_size: int = 2) -> ev.ScoreReport:
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
        wrong = {p: a for p, a in fol.predicates(f).items()
                 if p not in A.VOCABULARY or A.VOCABULARY[p][0] != a}
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
    """)
ps.check("B1", """
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
""")

ps.problem("B2", "The formaliser as a DSPy program", 7, """
Write a signature `PolicyFormalisation` with inputs `statement` and `vocabulary` and
output `formula`, and a factory `PolicyFormaliser(instruction)` returning a
`dspy.Module` with a single `dspy.Predict` whose instruction is `instruction`. The
field descriptions are part of the prompt — write them as you would brief a colleague
(manual marks). Then configure Claude and run the program once on `train[0]`.
""", auto_points=4)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = "Formalise the policy sentence in first-order logic."

    # TODO: class PolicyFormalisation(dspy.Signature): ...
    # TODO: def PolicyFormaliser(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: PolicyFormaliser()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = "Formalise the policy sentence in first-order logic."

    class PolicyFormalisation(dspy.Signature):
        \"\"\"Formalise one sentence of a hospital access policy in first-order logic.\"\"\"

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
    """)
ps.check("B2", """
assert set(PolicyFormalisation.input_fields) == {"statement", "vocabulary"}
assert "formula" in PolicyFormalisation.output_fields
program = PolicyFormaliser("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.formula, str) and smoke.formula.strip()
""")

ps.problem("B3", "Baseline on the development split, with its cost", 9, """
Evaluate the baseline program on `dev` with `ev.evaluate_dataset`, inside
`llm.meter(lm)` so you know what it cost. Store the result in `baseline_dev` and the
cost in `baseline_dev_cost`. Print the per-item rows.

Then write a short **error analysis**: for each non-perfect item, which guideline was
violated and *why* you think Claude made that choice. Separate genuine logic errors from
vocabulary/format problems — they call for different fixes.
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(PolicyFormaliser(), dev, policy_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    pd.DataFrame(baseline_dev["rows"])
    """)
ps.check("B3", """
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
A typical baseline run scores high on the plain universals and existentials and loses
points in three places — the answer to hand in is the analysis of *your* run:

* **Format/vocabulary** (0.0/0.1): wrapping the formula in prose or a code fence,
  Unicode connectives (∀, →), or synonyms such as `Supervisor(x)` instead of the
  listed `Supervises(x, y)`. These are prompt/format problems, fixed by stating the
  output contract — not by teaching logic.
* **Scope and direction** (0.25): *supervisors-of-nurses-clinicians* and
  *contractors-no-access* nest a quantifier inside an implication; the model sometimes
  pulls the existential out (`exists y` over the whole rule), which changes the
  meaning. These are genuine logic errors.
* **Quantifier order** on *every-nurse-supervised* is usually right with Claude; when
  it is wrong, the countermodel in the notes makes it obvious.

Cost: 8 calls, a few cents; this is the unit price for every later comparison.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
GEPA rewrites the instruction by reflecting on the scorer's feedback. It is only as
good as that feedback, it overfits small training sets, and every metric call is a
billed request. The rules for this part: **optimise on `train`, select on `dev`,
report on `test`** — and put a cost and a noise estimate next to every number.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 12, """
1. Build the GEPA feedback metric from your scorer and `A.POLICY_RULEBOOK`, and a
   separate reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare the baseline and the tuned program on **`test`** with `opt.compare`
   (store as `c1`) and print `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch02_policy_formaliser_instruction.txt"` — it is a learned artefact and belongs
   under review like code.

In writing: read the instruction diff. Which guidelines did GEPA put into words, which
did it miss, and did it add anything that is *not* a guideline (over-fitting to the
eight training sentences)?
""", auto_points=6)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch02_policy_formaliser_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(policy_scorer, A.POLICY_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(PolicyFormaliser(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(PolicyFormaliser(), tuned, test, policy_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch02_policy_formaliser_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
ids = lambda rows: {ex.id for ex in rows}
assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test)
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 200
""")
ps.written("""
Look for three things in the diff (your run will differ in wording):

* **Guidelines made explicit.** A good run writes down the output contract (ASCII
  only, formula alone, lower-case variables), "use only the listed predicates with the
  listed arity", and at least the implication/conjunction pairing. These come straight
  from the `VIOLATED GUIDELINE` lines, which is the point of a feedback metric.
* **Guidelines missed.** Rules no training item violated never appear in feedback, so
  GEPA cannot learn them — e.g. if Claude never mis-scoped a negation on train,
  `negation-scope` will be absent even though a test item needs it. The optimiser
  learns the *training failures*, not the task.
* **Over-fitting.** Instructions that quote training sentences or their predicates
  ("for statements about nurses…") are memorised, not general; they cost tokens on
  every call and do nothing on test.

If the test delta is ≈0, that is a legitimate result: a strong model's baseline may
already be near ceiling on the logic, and GEPA mostly fixed format.
""")

ps.problem("C2", "Was the optimiser worth it? Three programs, one table", 8, """
Add a third contender: the **hand-written guidelines** —
`A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)`. Evaluate baseline, guidelines
and GEPA-tuned on `test`, each inside its own `llm.meter`, and build `c2` with columns
`program` (`"baseline"`, `"guidelines"`, `"gepa"`), `test_mean`, `violations`,
`eval_usd`, and `optimisation_usd` (the GEPA cost for `"gepa"`, 0 otherwise).

In writing: which would you deploy, and what would change your mind? Consider score,
per-call token cost (instruction length), optimisation cost, and maintenance.
""", auto_points=3)
ps.todo(
    stub="""
    guidelines_instruction = A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    c2 = None    # TODO
    """,
    solution="""
    guidelines_instruction = A.POLICY_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    contenders = {"baseline": PolicyFormaliser(),
                  "guidelines": PolicyFormaliser(guidelines_instruction),
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
    """)
ps.check("C2", """
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "guidelines", "gepa"}
assert {"test_mean", "violations", "eval_usd", "optimisation_usd"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines"], "optimisation_usd"].eq(0).all()
""")
ps.written("""
The usual pattern: the hand-written guidelines recover most of GEPA's gain at zero
optimisation cost, because the guidelines *are* the knowledge the feedback conveys;
GEPA earns its cost when the failure modes are not known in advance, or when it finds
phrasing that fixes format errors the guidelines did not anticipate. Deploy the
cheapest program whose test score is within noise (Problem C3) of the best — usually
the guidelines — and re-run GEPA only when the error analysis shows failures the
guidelines do not cover. A longer instruction is paid on every call, forever.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 8, """
Eight test items and a sampling temperature of 1.0: a delta of one item is 0.09 in
mean score. Estimate the noise directly. With caching **disabled**
(`fresh = llm.dspy_lm(cache=False)` and `with dspy.context(lm=fresh): ...`), run the
baseline and the GEPA-tuned programs on `test` three times each; store the mean scores
in `runs = {"baseline": [..3..], "gepa": [..3..]}`.

Compute each program's mean and sample standard deviation and set `verdict_c3` to
`"significant"` if `|mean_gepa - mean_baseline| > 2 * max(sd_gepa, sd_baseline)`,
else `"not significant"`. In writing: what does this say about the C1 result, and what
would a credible evaluation of this system need?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs, then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    import statistics as st

    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(PolicyFormaliser(), test, policy_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, policy_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
import statistics as _st
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
_m = {k: _st.mean(v) for k, v in runs.items()}
_s = {k: _st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
""")
ps.written("""
Three runs is a crude noise estimate, but it is enough to stop over-claiming: if the
run-to-run spread of one program is as large as the gap between programs, the C1 delta
is not evidence of improvement. A credible evaluation needs (i) more test items — the
8-item split can only resolve differences of roughly ±0.1; (ii) repeated runs, reported
as mean ± sd or with a paired bootstrap over items; (iii) the comparison made on the
*same* items with the *same* sampling settings; and (iv) the cost of each run. The
honest sentence for the report is "GEPA changed the mean test score by X ± Y over 3
runs of 8 items, at a cost of $Z" — not "GEPA improved accuracy by X".
""")

# =========================================================================== #
ps.part("D", "A compliance agent that proves its verdicts", """
The formalised policy (`A.POLICY_KB`) and the audit-day facts (`A.FACTS`) are
provided. The domain is **closed**: only the named individuals exist, which turns
entailment into propositional satisfiability — decided exactly by
`A.ground_entails`. The agent's tools wrap it; your job is the agent, its output
contract, and its evaluation.
""")
ps.code("""
ws_demo = A.PolicyWorkspace()
premises = ws_demo.premises()
gold_verdicts = {qid: A.verdict(premises, fol.parse(c)) for qid, _, c, _ in A.COMPLIANCE_QUERIES}
assert gold_verdicts == {qid: g for qid, _, _, g in A.COMPLIANCE_QUERIES}
pd.DataFrame([{"id": q, "question": text, "conclusion": c, "gold": g}
              for q, text, c, g in A.COMPLIANCE_QUERIES])
""")

ps.problem("D1", "Build and evaluate the compliance agent", 12, """
1. Write `COMPLIANCE_PROMPT`, the agent's system prompt. It must make the agent read
   the policy and facts, **check both the claim and its negation** before answering,
   answer *undetermined* when neither is entailed, and end with a JSON object
   `{"verdict": "yes" | "no" | "undetermined", "evidence": [...]}`.
2. Write `parse_verdict(text) -> str`: return the verdict from the agent's final text
   (the JSON may be inside a code fence or surrounded by prose), or `"unparseable"`.
3. For every query, build a fresh `A.PolicyWorkspace()`, its tools
   (`A.build_policy_tools(ws)`), an agent (`agents.build_agent(ws, system_prompt=...,
   tools=...)`), run it with `agents.run_agent`, and collect `d1` with columns `id`,
   `gold`, `predicted`, `correct`, `tool_calls`, `checked_both` (did the log contain at
   least two `check_entailment` calls?) and `usd_estimate`
   (`llm.chat_usage(run.messages)`).

In writing: report accuracy with its sample size, the cost per question, and examine
every error and every *undetermined* case. Is the Dee–R1 verdict a model error or a
gap in the policy? What would you tell the governance office?
""", auto_points=5)
ps.todo(
    stub="""
    COMPLIANCE_PROMPT = \"\"\"TODO\"\"\"

    def parse_verdict(text: str) -> str:
        # TODO
        raise NotImplementedError

    d1 = None   # TODO: run the agent on every query
    """,
    solution="""
    import re

    COMPLIANCE_PROMPT = \"\"\"\\
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
    \"\"\"

    VERDICTS = {"yes", "no", "undetermined"}

    def parse_verdict(text: str) -> str:
        for blob in reversed(re.findall(r"\\{[^{}]*\\}", text or "")):
            try:
                value = str(json.loads(blob).get("verdict", "")).strip().lower()
            except (json.JSONDecodeError, AttributeError):
                continue
            if value in VERDICTS:
                return value
        return "unparseable"

    rows = []
    for qid, question, _, gold in A.COMPLIANCE_QUERIES:
        ws = A.PolicyWorkspace()
        agent, _ = agents.build_agent(ws, system_prompt=COMPLIANCE_PROMPT,
                                      tools=A.build_policy_tools(ws))
        run = agents.run_agent(agent, ws, question)
        predicted = parse_verdict(run.answer)
        names = ws.log.names()
        rows.append({"id": qid, "gold": gold, "predicted": predicted,
                     "correct": predicted == gold, "tool_calls": len(names),
                     "checked_both": names.count("check_entailment") >= 2,
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(f"accuracy {d1.correct.mean():.2f} on n={len(d1)}; "
          f"cost ≈ ${d1.usd_estimate.sum():.3f} total")
    d1
    """)
ps.check("D1", """
assert parse_verdict('{"verdict": "yes", "evidence": []}') == "yes"
assert parse_verdict('Checked both.\\n```json\\n{"verdict": "undetermined", "evidence": ["x"]}\\n```') == "undetermined"
assert parse_verdict('prose {"note": 1} then {"verdict": "NO", "evidence": []}') == "no"
assert parse_verdict("I think yes.") == "unparseable"
assert isinstance(d1, pd.DataFrame) and len(d1) == len(A.COMPLIANCE_QUERIES)
assert {"id", "gold", "predicted", "correct", "tool_calls", "checked_both",
        "usd_estimate"} <= set(d1.columns)
assert set(d1["predicted"]) <= {"yes", "no", "undetermined", "unparseable"}
assert (d1["correct"] == (d1["predicted"] == d1["gold"])).all()
""")
ps.written("""
With the procedure above Claude typically answers all six correctly (n = 6 — report it
as "6/6", not "100 % accuracy"), with 4–6 tool calls and a few cents per question. The
instructive cases:

* **Ben–R2 (undetermined).** Ben is a clinician but is not recorded as treating Ole,
  so the treating-clinician rule does not fire — and nothing *forbids* access either.
  The policy grants access in some cases and denies it in others; it is silent here.
* **Dee–R1 (undetermined).** Dee is an external auditor, but the auditor rule only
  protects *sensitive* records, and R1 is not sensitive. Access would require Dee to be
  a clinician (only-clinicians-access), and nothing says she is not. This is **not** a
  model error; it is a gap in the policy. An agent that "helpfully" answers *no* here
  is guessing, and a checker that guesses cannot be audited.

For the governance office: either add "auditors are not clinicians" (then Dee–R1
becomes *no*), or adopt an explicit default-deny rule — a decision for them, not for
the model. If any row shows `checked_both == False` with a correct verdict, the agent
got lucky; the prompt should be tightened, because a one-sided check cannot tell *no*
from *undetermined*.
""")

ps.problem("D2", "Pricing a proof", 10, """
A proof has a price: each resolution step costs time and tokens. `A.ProofSearchMDP`
rewards a *justified* verdict with +1, charges `step_cost` per derivation and
`wrong_verdict_penalty` for a wrong or unjustified claim. Use the provided clauses
(Ana is a nurse ⇒ clinician ⇒ employee; goal `Employee(Ana)`).

1. Solve the MDP at `step_cost=0.05` with `mdp.value_iteration` and roll out the greedy
   policy; set `k` to the number of derivations in the optimal proof.
2. Derive, on paper, the step cost `c*` above which not proving (and taking the
   penalty) beats proving, as a function of `k` and the penalty `p`; implement it as
   `threshold(k, p)`.
3. Verify it: for `p` in `[1.0, 2.0]`, sweep `step_cost` over `np.linspace(0.05, 1.5,
   30)` and record in `d2` (columns `penalty`, `step_cost`, `proves`) whether the
   optimal policy still derives the empty clause before claiming.

In writing: what does this say about giving an agent expensive reasoning tools, and
about the penalty you should attach to unverified answers?
""", auto_points=6)
ps.code("""
import numpy as np

chain = [fol.parse("forall x (Nurse(x) -> Clinician(x))"),
         fol.parse("forall x (Clinician(x) -> Employee(x))"),
         fol.parse("Nurse(Ana)")]
goal = fol.parse("Employee(Ana)")
clauses = []
for f in chain + [fol.Not(goal)]:
    clauses += fol.to_cnf_clauses(fol.ground(f, ["Ana"]))
clauses
""")
ps.todo(
    stub="""
    k = None                          # TODO (1)

    def threshold(k: int, p: float) -> float:
        # TODO (2)
        raise NotImplementedError

    d2 = None                         # TODO (3)
    """,
    solution="""
    M = A.ProofSearchMDP(clauses, entailed=True, step_cost=0.05)
    V, pi = mdp.value_iteration(M)
    episode = mdp.run_episode(M, mdp.greedy_policy(pi))
    for t in episode.transitions:
        print(f"  {M.describe_action(t.action):40s} r={t.reward:+.2f}")
    k = len(episode) - 1

    def threshold(k: int, p: float) -> float:
        # proving: 1 - k*c ; not proving: -p  =>  prove iff c < (1 + p) / k
        return (1 + p) / k

    rows = []
    for p in [1.0, 2.0]:
        for c in np.linspace(0.05, 1.5, 30):
            Mc = A.ProofSearchMDP(clauses, entailed=True, step_cost=float(c),
                                  wrong_verdict_penalty=p)
            Vc, pic = mdp.value_iteration(Mc)
            ep = mdp.run_episode(Mc, mdp.greedy_policy(pic))
            rows.append({"penalty": p, "step_cost": round(float(c), 3),
                         "proves": len(ep) > 1})
    d2 = pd.DataFrame(rows)
    print(f"k = {k}; predicted thresholds:", {p: round(threshold(k, p), 3) for p in [1.0, 2.0]})
    d2.groupby("penalty").apply(lambda g: g[g.proves].step_cost.max())
    """)
ps.check("D2", """
assert k == 3
assert abs(threshold(3, 1.0) - 2 / 3) < 1e-9 and abs(threshold(4, 2.0) - 0.75) < 1e-9
assert isinstance(d2, pd.DataFrame) and set(d2["penalty"]) == {1.0, 2.0}
for p, grp in d2.groupby("penalty"):
    c_star = threshold(k, p)
    clear = grp[(grp.step_cost - c_star).abs() > 0.03]
    assert (clear.proves == (clear.step_cost < c_star)).all(), f"sweep disagrees with c* at p={p}"
""")
ps.written("""
Proving pays `1 − k·c`; skipping the proof pays `−p` (an unjustified claim is
penalised however it turns out), so the agent should prove iff `c < (1 + p)/k`. With
`k = 3` that is `c* = 2/3` at `p = 1` and `c* = 1` at `p = 2`, and the sweep flips at
exactly those points.

Two design lessons. First, the value of a reasoning tool falls with the length of the
proof it needs: on a real policy, where `k` is in the hundreds, an agent charged
realistic tool costs will rationally stop verifying unless the penalty for unverified
answers is large. Second, that penalty is *the* design lever: in a compliance setting,
set it high (or make unverified answers impossible, as the D1 contract does) so that
checking always beats guessing — and budget for the tool calls that implies.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
