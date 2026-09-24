# Ontology Engineering — a practice-first graduate course

A graduate course built on Keet, *An Introduction to Ontology Engineering* (2nd ed.),
recast so that **every claim the book makes in prose, you make in code**: measured,
tested, and defensible to a grader.

Two things distinguish it from a reading course:

1. **Every example and exercise is executable.** Chapters ship Jupyter notebooks that
   run end to end; exercise solutions carry assertions, and those assertions are the
   marking scheme.
2. **Every chapter ends with a real-life problem set.** A concrete brief from a
   (fictional) organisation, worked with Claude on the live API: build the grader, build
   a DSPy/LangChain program or agent for the chapter's task, optimise it with GEPA on an
   honest train/dev/test split, put a cost and a noise estimate next to every number,
   and analyse the chapter's decision problem as an MDP.

---

## Status

| Part | Chapter | Chapter notebooks | Problem set |
|---|---|---|---|
| — | **1. Introduction** | ✅ 5 | ✅ Triaging submissions to an ontology registry |
| I | **2. First-Order Logic and Reasoning** | ✅ 4 | ✅ Formalising a hospital access policy |
| I | **3. Description Logics** | ✅ 5 | ✅ Reviewing rail-ontology change requests |
| I | **4. The Web Ontology Languages** | ✅ 5 | ✅ Axiomatising a conservancy's ontology inside OWL 2 profiles |
| II | **5. Methods and Methodologies** | ✅ 4 | ✅ An automated first-pass ontology design review |
| II | **6. Top-down Ontology Development** | ✅ 4 | ✅ Untangling a museum catalogue's single `partOf` |
| II | 7. Bottom-up Ontology Development | partial — see `../bottomup_ontology/` | specified below |
| III | **8. Linking Ontologies to Data** | ✅ 4 | ✅ Mapping and serving a hospital trust's clinical data |
| III | **9. Ontologies and Natural Languages** | ✅ 4 | ✅ Multilingual review sheets for a zoo alliance |
| III | **10. Rough, Temporal, and Fuzzy Modelling** | ✅ 4 | ✅ Choosing — and pricing — the formalism for an ED ontology |
| III | 11. More Topics to Explore | planned | specified below |

Each chapter has its own executable engine — a FOL model checker and resolution prover
(Ch. 2), an ALC tableau reasoner (Ch. 3), OWL 2 profile checking (Ch. 4), an OntoClean
constraint checker (Ch. 5), a part-whole taxonomy with a chaining checker (Ch. 6), and
so on — and the problem sets use that engine as the grader wherever the task has a
decision procedure.

### The MDP shapes

Each chapter contributes a different decision problem: "formalise the task as an MDP"
is not one exercise repeated nine times.

| Chapter | Shape | Actions | Transitions |
|---|---|---|---|
| 1 | **evidence gathering** | buy a piece of evidence, or submit | deterministic |
| 2 | **proof search** | derive a resolvent, or claim a verdict | deterministic |
| 3 | **budgeted oracle** | guess cheaply, or pay for soundness | **stochastic** |
| 4 | **construction** | assert an axiom (changing the artefact), escalate, or submit | deterministic |
| 5 | **planning under prerequisites** | perform a step whose preconditions are met, or ship | deterministic |
| 6 | **diagnosis** | ask a discriminating question, or commit | **stochastic** |
| 8 | **execution strategy** | materialise or rewrite, under staleness and latency | see the problem set |
| 9 | **revision / stopping** | redraft a verbalisation, or stop | **stochastic** |
| 10 | **search cost** | propagate constraints, or commit | deterministic |

---

## Layout

```
oe-course/
├── README.md              ← you are here
├── .env.example           # copy to .env and add ANTHROPIC_API_KEY
├── requirements.txt
├── oe_course/             # the shared framework package
└── chapters/
    ├── ch01_introduction/
    ├── ch02_first_order_logic/
    └── …                  # one directory per chapter
```

Each chapter directory holds its notebooks, its engine (`chNN_toolkit.py`), the problem
set's provided code (`chNN_agentic.py`), and the builders that emit the notebooks:

```
chapters/ch02_first_order_logic/
├── 00_overview_and_setup.ipynb
├── 01_syntax_and_semantics.ipynb
├── 02_reasoning.ipynb
├── 03_exercises.ipynb
├── 04_assignment.ipynb     ← the problem set (student)
├── 04_solutions.ipynb      ← the same problem set, worked (instructor)
├── ch02_toolkit.py · ch02_agentic.py
├── _build_notebooks.py     # chapter notebooks
└── _build_assignment.py    # the problem set
```

Chapter 7's material lives outside this directory, in `../bottomup_ontology/`, because it
is also a standalone component of the wider repository rather than course-only material.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env            # then put your ANTHROPIC_API_KEY in it

# Rebuild everything
for ch in chapters/ch*/; do
  (cd "$ch" && python _build_notebooks.py && python _build_assignment.py)
done

jupyter lab
```

Notebooks are **build artefacts**: edit the `_build_*.py` source, not the `.ipynb`.

**The problem sets call the live Anthropic API** (`claude-opus-5` by default; override
with `OE_COURSE_MODEL`). There is no offline mode: the numbers in a problem set are
numbers about the model, and each one costs money. Every problem set states its
estimated budget in its header (typically $5–20 for a full run), and `llm.meter(...)`
records what each block of work actually cost. DSPy caches identical requests on disk,
so re-running unchanged cells is free. Fuseki is optional; without it the course uses an
in-memory rdflib store.

## Problem sets

Each chapter's problem set ships as a **pair** of notebooks, built from one source by
`oe_course.assignment.ProblemSet`:

| | contains | executes clean |
|---|---|---|
| `NN_assignment.ipynb` | the brief, provided code, `# TODO` stubs ending in `raise NotImplementedError`, and *Your answer* cells | **no** — by design |
| `NN_solutions.ipynb` | the same problem set with every stub implemented and every written answer given | yes, and it ends by asserting every check passed |

The format:

* **A brief** — a stakeholder, an artefact, a real problem — plus topic coverage, total
  points, estimated effort and **API budget**.
* **Parts A–D**, typically: A — concepts and the limits of the chapter's machinery;
  B — build the grader/metric and the Claude program; C — optimise with GEPA honestly
  (optimise on `train`, select on `dev`, report on `test`, with cost and run-to-run
  noise); D — the agent and the chapter's MDP.
* **100 points per set**, roughly half auto-graded by `with GRADER.check("B1", points=…)`
  cells and half marked by hand against the rubric (written answers, error analyses, the
  quality of the engineering evidence).
* **Checks never assert on model quality.** They test deterministic behaviour (scorers on
  hand-made predictions, tools, parsers, MDP properties) and the *reporting discipline*
  of live runs (right split, sample size, cost recorded, artefacts saved, verdicts
  consistent with the statistics). A student is graded on doing the work properly, not
  on how Claude happened to sample that day.
* **A grading rubric and a self-test** close every notebook.

To hand out a repository without answers:

```bash
rm chapters/*/[0-9]*_solutions.ipynb
```

### Authoring a problem set

```python
from oe_course.assignment import ProblemSet

ps = ProblemSet(chapter="Chapter 2 — …", title="…", coverage="…", scenario="…",
                effort="10–12 hours", api_budget="≈ $6–12 estimated …")
ps.setup("import ch02_agentic as A")
ps.part("B", "Build the grader")
ps.problem("B1", "A staged, diagnostic scorer", 14, "brief…", auto_points=12)
ps.todo(stub="def policy_scorer(gold, pred): ...", solution="def policy_scorer(gold, pred): …")
ps.written("model answer…")          # a *Your answer* cell in the assignment
ps.check("B1", "assert policy_scorer(...).score == 1.0")
ps.save(HERE, "04")                  # -> 04_assignment.ipynb, 04_solutions.ipynb
```

Cells not marked for one variant — the brief, the provided code, the checks — go into
both notebooks, so the two cannot drift apart.

---

## Course infrastructure — `oe_course/`

The framework package. It sits beside `chapters/`, which is what makes
`import oe_course` work from any notebook: the setup cell walks up from the
notebook's directory until it finds a folder containing `oe_course`, and that
folder is this one.

| Module | What it provides |
|---|---|
| `config` | model ids, credentials (`.env`), Fuseki settings, paths |
| `llm` | Anthropic clients (LangChain `ChatAnthropic`, DSPy `LM`), spend accounting (`meter`, `spend`, `chat_usage`) |
| `sparql` | one SPARQL API over Fuseki **or** in-memory rdflib |
| `ontology` | graph metrics, spectrum classification, modelling-defect detectors |
| `tools` | LangChain function tools, bound to a workspace, with call logging |
| `agents` | single-loop agents and decomposed plan→act→critique pipelines |
| `mdp` | finite MDPs, value iteration, policy evaluation, trajectory replay |
| `evaluation` | rulebooks, datasets, deterministic metrics, LLM-as-judge, GEPA feedback metrics |
| `optimize` | GEPA/DSPy compilation with before/after and instruction diffs |
| `skills` | versioned capability bundles and skill cards |
| `selfimprove` | experience buffers, failure mining, held-out promotion gates |
| `programs` | the worked reference task (ontology triage) |
| `assignment` · `grading` | the problem-set builder and its runtime marking |
| `data/corpus` | 11 labelled ontologies — the shared evaluation substrate |

### The five things every problem set exercises

1. **Function tools.** Narrow, composable, bound to a workspace, every call logged.
   Descriptions state a *trigger*, not just a behaviour — models select tools from
   descriptions.
2. **Functional decomposition.** Where it applies, compare a single loop against an
   explicit pipeline, or a program that puts measurement in code and only judgement in
   the model, on **score and cost**.
3. **MDP formulation.** State, actions, transitions, reward, γ — written down, solved
   exactly by value iteration, with decision thresholds derived in closed form and
   checked by a sweep.
4. **Evaluation.** A dataset split *by item* (never by random row), a deterministic
   metric wherever a decision procedure exists, an LLM-as-judge **validated against
   labels** where one does not, and a **GEPA feedback metric** that emits
   `VIOLATED GUIDELINE <id>: <fix>` lines. A metric that returns only a number cannot
   drive reflection.
5. **Optimisation, honestly reported.** GEPA on `train`, selection on `dev`, the report on
   an untouched `test`; the cost of the run; the run-to-run noise; and a comparison
   against a hand-written-guidelines baseline, because "the optimiser helped" is only a
   finding if it beats the cheap alternative.

---

## Per-chapter specifications

Each entry fixes the chapter's agent task, its MDP, and its metrics.

### Chapter 1 — Introduction ✅
*Notebooks:* spectrum classification · integration with a reasoner (recall 0 → 1) ·
the definition game as a scorecard · defect scanning · exercises · problem set.

**Agent:** ontology triage — place an artefact on the spectrum and list its defects.
**MDP:** *evidence-gathering.* S = evidence held; A = one tool per evidence kind + submit;
R = −cost per call, task score on submit.
**Metrics:** level exact-match + defect-set F1 (deterministic); groundedness of the
written justification (judge).
**Self-improvement:** mine mislabelled artefacts, re-optimise, promote only on held-out gain.

### Chapter 2 — First-Order Logic and Reasoning ✅
*Notebooks:* syntax as an AST + Tarskian semantics as code · entailment, countermodels,
resolution proofs, and the decidability wall · exercises · problem set.

**Engine:** `ch02_toolkit` — tokeniser, recursive-descent parser, evaluator, finite-model
enumerator, ground resolution prover. No external solver.
**Agent:** English statement → FOL formula.
**MDP:** *proof search.* S = clauses derived; A = derive a resolvent, or claim a verdict;
R = −cost per step, **+1 only for a *justified* correct verdict** (the empty clause must
actually be derived — guessing right is not proving).
**Metrics:** the grader is a **decision procedure**, not a string match: two formulas score
equal when they have the same models up to a finite size. Feedback carries the
countermodel that witnesses a difference.
**What GEPA learns:** in two stages — first emit a bare parseable formula, then the
quantifier semantics (`∀` takes implication, `∃` takes conjunction, order matters,
negation scope).
**Headline result:** held-out **0.00 → 1.00**, all five rules discovered; a budget sweep
(20/40/80 rollouts → 3/4/5 rules) shows optimisation is search under a budget.

### Chapter 3 — Description Logics ✅
*Notebooks:* concepts, models and **a tableau you can read** · naming the logic and
measuring what expressivity costs · reasoning services · exercises · problem set.

**Engine:** `ch03_toolkit` — concept AST, NNF, expressivity analysis, and a working **ALC
tableau reasoner** with TBox internalisation and subset blocking (so cyclic axioms such as
`A ⊑ ∃r.A` terminate). Number restrictions, inverses and transitivity are *analysed* by the
DL namer but not reasoned over; the notebooks say so where it matters.
**Agent:** name the DL a knowledge base needs, and answer a subsumption query.
**MDP:** *budgeted oracle*, and the course's **only stochastic one** — per query, guess
cheaply (correct with probability `pᵢ`) or pay for a sound reasoner call under a budget.
Value iteration recovers the rule `reason iff 1 − cost > pᵢ` and spends the budget where
the heuristic is weakest.
**Metrics:** half for the DL name (with the *specific missing letter* named in feedback),
half for the verdict.
**Self-improvement:** the tableau is a free, sound oracle, so **every failure labels
itself** — no annotation budget, no human in the loop.
**Headline results:** held-out **0.50 → 1.00**, all five rules; the tableau exhibits
exactly **2ⁿ − 1** branch points on an unsatisfiable input, putting the ExpTime bound on
screen; and an ablation (Exercise 5.1) shows that an all-true dataset silently prevents
the agent from ever learning to call the reasoner.

### Chapter 4 — The Web Ontology Languages ✅
**Agent:** requirement → OWL axiom, inside a requested OWL 2 profile.
**MDP:** *construction* — actions change the artefact; R = entailment coverage − profile
penalty − step cost.
**Metrics:** half faithfulness (axiom exact match), half profile compliance.
**GEPA discovers:** existential vs universal, is-a vs instance-of, EL/QL/RL restrictions.

### Chapter 5 — Methods and Methodologies ✅
*Notebooks:* methodology selection + **competency questions as SPARQL tests** ·
**OntoClean** · exercises · problem set.

**Engine:** `ch05_toolkit` — a methodology catalogue with selection *signals*, competency
questions that execute, and an OntoClean constraint checker (rigidity, identity, unity,
dependence).
**The chapter's claim:** *consistency is not correctness.* Every taxonomy error in this
chapter is logically consistent — the Chapter 3 tableau is run on them and finds
nothing. A reasoner amplifies whatever you assert, including your mistakes.
**Agent:** recommend a methodology from a brief, and report the OntoClean violations in
a taxonomy.
**MDP:** *planning under prerequisites* — you cannot write axioms before a taxonomy
exists, and rewards come from **measured** competency-question coverage (0.33 for a
taxonomy alone, 0.83 with axioms, 1.0 with instances).
**Headline results:** held-out **0.30 → 1.00**, all six rules. The optimal plan
**skips evaluation** — a reward-model bug, not a solver bug, and Exercise 4.2 fixes the
reward rather than the plan. Exercise 4.1 ablates two axioms out of the training set and
shows a rule becoming permanently unlearnable.

### Chapter 6 — Top-down Ontology Development ✅
*Notebooks:* foundational categories + a decision procedure · **part-whole relations and
chaining** · exercises · problem set.

**Engine:** `ch06_toolkit` — a DOLCE-style category tree with yes/no decision questions,
a DOLCE↔BFO comparison, the seven-way part-whole taxonomy with parthood/transitivity
flags, and `can_chain`.
**The chapter's claim:** *"part of" in English is at least seven different relations.*
Three of them (constitution, containment, participation) are not parthood at all.
**Agent:** name the relation a statement expresses, and decide whether it is genuine
parthood — the half that governs what may be inferred.
**MDP:** *diagnosis* — ask a discriminating question (stochastic answer) or commit;
committing with `k` candidates is right with probability `1/k`.
**Headline results:** held-out **0.31 → 1.00**, all eight rules. Value iteration
**derives DOLCE's decision tree** (V\* = 0.85, ~3.02 questions on average), and raising
the question cost past 0.3 makes blind guessing optimal — since one of seven is worth
0.143. Exercise 2.1 completes Chapter 5's unfinished repair: `Statue ⊑ Clay` becomes
*constituted-of*, which is not a subsumption at all.

### Chapter 7 — Bottom-up Ontology Development
Existing implementation: `../bottomup_ontology/` (Fig. 7.7 pipeline as a networkx graph with
step functions already exposed as agentic tools).
**Agent:** drive that pipeline — choose which optional steps to run on a given corpus.
**MDP:** *pipeline configuration* — S = steps completed; A = run the next step or stop;
R = gold-standard F1 of the extracted ontology − compute cost. Directly reuses the existing
`tool_specs()` registry.
**Metrics:** deterministic — precision/recall/F1 of extracted terms and relations against a
gold ontology; judge — plausibility of the extracted axioms.
**Self-improvement:** human-in-the-loop verification (step 6) is a natural labelling path,
so mined failures carry gold labels for free.

### Chapter 8 — Linking Ontologies to Data
**Agent:** write and repair OBDA mappings (R2RML-style) between a relational source and an
ontology; decide materialisation vs query rewriting.
**Tools:** `inspect_schema`, `propose_mapping`, `rewrite_query`, `materialise`,
`compare_answer_sets`, plus **Fuseki** as the target store.
**MDP:** *materialise-or-rewrite under a budget* — the trade already met in Ch. 1 Notebook 2
(33 → 314 triples), now the decision itself. R = answer-set F1 − storage cost − latency cost.
**Metrics:** deterministic — SPARQL answer-set match (`answer_set_match` already ships);
judge — mapping readability and maintainability.

### Chapter 9 — Ontologies and Natural Languages
**Agent:** multilingual labelling and **ontology verbalisation** (§9.2) — render axioms as
controlled natural language, and parse CNL back.
**Tools:** `verbalise_axiom`, `parse_cnl`, `lexicalise` (lemon-style), `round_trip_check`.
**MDP:** *round-trip fidelity* — R = 1 if `parse(verbalise(axiom)) == axiom`, minus length
penalty. A rare case with a free, exact reward signal.
**Metrics:** deterministic — round-trip identity; judge — fluency and unambiguity of the
verbalisation. The clearest chapter for contrasting the two metric families, because the
deterministic one is exact and still misses everything a reader cares about.

### Chapter 10 — Rough, Temporal, and Fuzzy Modelling
**Agent:** choose a representation (crisp / rough / fuzzy / temporal) for a requirement and
implement it.
**Tools:** `temporal_operators`, `fuzzy_membership`, `rough_approximation`,
`check_temporal_consistency`.
**MDP:** *representation selection* — A = commit to a formalism or gather more requirement
detail; R = requirement coverage − complexity cost. Encodes the chapter's core trade:
expressivity is never free.
**Metrics:** deterministic — does the chosen formalism satisfy the stated constraints;
judge — justification of the expressivity/tractability trade.

### Chapter 11 — More Topics to Explore
**Agent:** **ontology matching** (§11.2) and **modularisation** (§11.1) — the capstone.
**Tools:** `lexical_match`, `structural_match`, `logical_match`, `extract_module`,
`check_module_coverage`.
**MDP:** *matcher-portfolio selection* — A = run a matcher, accept/reject a correspondence,
or stop; R = alignment F1 − matcher cost. A genuinely multi-armed problem, unlike the
earlier chapters.
**Metrics:** deterministic — precision/recall/F1 against a reference alignment (OAEI-style);
judge — quality of justifications for contested correspondences.
**Self-improvement:** accepted/rejected correspondences accumulate as labelled experience,
making this the chapter where the self-improvement loop has the most to work with.

---

## Assessment

| Weight | Component |
|---|---|
| 30% | Notebook exercises (autograded by the shipped assertions) |
| 30% | Problem sets — a working agent **with a skill card**: held-out score, the diff that caused it, and the failure mode it did not fix |
| 20% | A written critique of one metric in the course: what it fails to measure, with evidence |
| 20% | Capstone (Ch. 11) — an ontology matcher evaluated against a reference alignment |

**The habit the course is built to instil:** never report an agent improvement without
three things — the held-out score, the diff that caused it, and the failure mode it did
not fix.
