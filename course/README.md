# Ontology Engineering — a practice-first graduate course

A graduate course built on Keet, *An Introduction to Ontology Engineering* (2nd ed.),
recast so that **every claim the book makes in prose, you make in code**: measured,
tested, and defensible to a grader.

Two things distinguish it from a reading course:

1. **Every example and exercise is executable.** Chapters ship Jupyter notebooks that
   run end to end; exercise solutions carry assertions, and those assertions are the
   marking scheme.
2. **Every chapter ends with an agentic lab.** You build a LangChain/LangGraph agent
   for that chapter's task, formalise it as an MDP, construct an evaluation dataset and
   metrics (deterministic *and* LLM-as-judge), optimise it with DSPy — including GEPA —
   and, where it applies, close a self-improvement loop behind a promotion gate.

---

## Status

| Part | Chapters | Notebooks | Agentic lab |
|---|---|---|---|
| — | **1. Introduction** | ✅ complete (6 notebooks) | ✅ complete |
| I | **2. First-Order Logic and Reasoning** | ✅ complete (5 notebooks) | ✅ complete |
| I | **3. Description Logics** | ✅ complete (6 notebooks) | ✅ complete |
| I | **4. The Web Ontology Languages** | ✅ complete (6 notebooks) | ✅ complete |
| II | **5. Methods and Methodologies** | ✅ complete (5 notebooks) | ✅ complete |
| II | **6. Top-down Ontology Development** | ✅ complete (5 notebooks) | ✅ complete |
| II | 7. Bottom-up Ontology Development | partial — see `bottomup_ontology/` | specified below |
| III | 8. Linking Ontologies to Data | planned | specified below |
| III | 9. Ontologies and Natural Languages | planned | specified below |
| III | 10. Rough, Temporal, and Fuzzy Modelling | planned | specified below |
| III | 11. More Topics to Explore | planned | specified below |

**Part I is complete**, and **Part II is half built** (Ch. 5–6 of 7). Each chapter has
its own executable engine — a FOL model checker and resolution prover (Ch. 2), an ALC
tableau reasoner (Ch. 3), an OntoClean constraint checker (Ch. 5), a part-whole
taxonomy with a chaining checker (Ch. 6) — and its own agentic lab. The per-chapter
specifications below fix the task, the MDP, the metrics and the self-improvement angle
for what remains.

### The six MDP shapes built so far

Each completed chapter contributes a genuinely different decision problem. That is the
point: "formalise the task as an MDP" is not one exercise repeated six times.

| Chapter | Shape | Actions | Transitions |
|---|---|---|---|
| 1 | **evidence gathering** | buy a piece of evidence, or submit | deterministic |
| 2 | **proof search** | derive a resolvent, or claim a verdict | deterministic |
| 3 | **budgeted oracle** | guess cheaply, or pay for soundness | **stochastic** |
| 4 | **construction** | assert an axiom (changing the artefact), or submit | deterministic |
| 5 | **planning under prerequisites** | perform a step whose preconditions are met, or ship | deterministic |
| 6 | **diagnosis** | ask a discriminating question, or commit | **stochastic** |

Chapter 6's is the one to look at if you only look at one: solving it exactly
**derives DOLCE's decision tree** — endurant/perdurant first, then telicity — from a
cost model, rather than taking the textbook's tree on authority.

---

## Running it

```bash
pip install -r requirements.txt

# Every chapter builds and runs the same way
for ch in course/ch0*/; do
  (cd "$ch" && python _build_notebooks.py \
     && python -m jupyter nbconvert --to notebook --execute --inplace 0*.ipynb)
done

# Chapter 4 has a second build script for its agentic lab
(cd course/ch04_web_ontology_languages && python _build_agentic_lab.py)

# ...or just read them
jupyter lab
```

Notebooks are **build artefacts**: edit the `_build_*.py` source, not the `.ipynb`.
Authoring in Python keeps diffs reviewable and makes course-wide changes one edit.

### Two modes, one codebase

Everything runs **offline** — no API key, no Docker, no cost:

| | offline (default) | live |
|---|---|---|
| LLM | deterministic simulator | Claude (`claude-opus-5`) via `langchain-anthropic` / DSPy |
| triplestore | in-memory `rdflib` | Apache Jena Fuseki (`infra/fuseki`) |
| enabled by | nothing to do | `export ANTHROPIC_API_KEY=...`, `docker compose up -d` |

> **What the offline LLM is, precisely.** It is a *simulator*, not a model: a weak agent
> that follows explicit instructions and ignores everything else. This is a deliberate
> design choice, because a fake LLM that ignored its prompt would make prompt
> optimisation a no-op — GEPA would search instructions that cannot change the score,
> and students would watch a loop that proves nothing. The simulator instead starts from
> a naive strategy and adopts a better one for each rule the instruction conveys, so the
> optimisation loop genuinely converges for a reason you can read in the instruction diff.
>
> **Numbers obtained offline describe the simulator, not Claude.** The notebooks say so
> at every point where a number appears. Set `ANTHROPIC_API_KEY` and the identical code
> produces numbers about the model.

---

## Course infrastructure — `oe_course/`

| Module | What it provides |
|---|---|
| `config` | environment detection, model ids, offline/live switch |
| `llm` | Anthropic clients; the rule-conditioned task and reflection simulators |
| `sparql` | one SPARQL API over Fuseki **or** in-memory rdflib |
| `ontology` | graph metrics, spectrum classification, modelling-defect detectors |
| `tools` | LangChain function tools, bound to a workspace, with call logging |
| `agents` | single-loop agents and decomposed plan→act→critique pipelines |
| `mdp` | finite MDPs, value iteration, policy evaluation, trajectory replay |
| `evaluation` | datasets, deterministic metrics, LLM-as-judge, GEPA feedback metrics |
| `optimize` | GEPA/DSPy compilation with before/after and instruction diffs |
| `skills` | versioned capability bundles and skill cards |
| `selfimprove` | experience buffers, failure mining, held-out promotion gates |
| `programs` | the worked reference task (ontology triage) |
| `data/corpus` | 11 labelled ontologies — the shared evaluation substrate |

### The five things every agentic lab does

1. **Function tools.** Narrow, composable, bound to a `ToolContext`, every call logged.
   Descriptions state a *trigger* ("call this whenever asked to review an ontology"), not
   just a behaviour — models select tools from descriptions.
2. **Functional decomposition.** Compare a single ReAct loop against an explicit
   plan→act→critique pipeline on **score and cost**. The critic stage is a verification
   step with access to raw tool output, which turns a class of hallucination into an
   impossibility.
3. **MDP formulation.** State, actions, transitions, reward, γ — written down, then
   solved exactly by value iteration so the agent's **regret** against `V*` can be
   reported. "Is the agent efficient?" becomes arithmetic.
4. **Evaluation.** A dataset split *by artefact* (never by random row), a deterministic
   metric, an LLM-as-judge for the qualities set comparison cannot reach, and a
   **GEPA feedback metric** that emits `MISSING RULE <id>: <fix>` lines. A metric that
   returns only a number cannot drive reflection — this is the single most common reason
   GEPA appears not to work.
5. **Optimisation and self-improvement.** GEPA on `train`, report on held-out `dev`,
   attribute the gain to a specific instruction change, package as a versioned skill,
   then run failure-mining rounds behind a promotion gate with a minimum margin.

---

## Per-chapter specifications

Each entry fixes the chapter's agent task, its MDP, and its metrics.

### Chapter 1 — Introduction ✅
*Notebooks:* spectrum classification · integration with a reasoner (recall 0 → 1) ·
the definition game as a scorecard · defect scanning · exercises · agentic lab.

**Agent:** ontology triage — place an artefact on the spectrum and list its defects.
**MDP:** *evidence-gathering.* S = evidence held; A = one tool per evidence kind + submit;
R = −cost per call, task score on submit.
**Metrics:** level exact-match + defect-set F1 (deterministic); groundedness of the
written justification (judge).
**Self-improvement:** mine mislabelled artefacts, re-optimise, promote only on held-out gain.

### Chapter 2 — First-Order Logic and Reasoning ✅
*Notebooks:* syntax as an AST + Tarskian semantics as code · entailment, countermodels,
resolution proofs, and the decidability wall · exercises · agentic lab.

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
measuring what expressivity costs · reasoning services · exercises · agentic lab.

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
**OntoClean** · exercises · agentic lab.

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
chaining** · exercises · agentic lab.

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
Existing implementation: `bottomup_ontology/` (Fig. 7.7 pipeline as a networkx graph with
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
| 30% | Agentic labs — a working agent **with a skill card**: held-out score, the diff that caused it, and the failure mode it did not fix |
| 20% | A written critique of one metric in the course: what it fails to measure, with evidence |
| 20% | Capstone (Ch. 11) — an ontology matcher evaluated against a reference alignment |

**The habit the course is built to instil:** never report an agent improvement without
three things — the held-out score, the diff that caused it, and the failure mode it did
not fix.
