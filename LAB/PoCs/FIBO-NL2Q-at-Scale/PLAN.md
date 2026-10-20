# PoC plan: ontology-grounded NL → SPARQL → SQL at scale (FIBO / FIBEN)

**Status:** plan, not started. **Date:** 2026-10-19.
**Builds on:** `LAB/PoCs/SPARQL-2-SQL` (the offline Ontop compiler, verified) and its
`NL2SPARQL-ASSESSMENT.md`; the evidence base is in
`knowledge/NL2Q/reports/NL2Query state of the art 2026.md`.
**Intent:** if the results are good enough (§8), turn this into a product for banks.

---

## 1. The question this PoC answers

> Can a natural-language query layer, grounded in FIBO and compiled through a virtual
> knowledge graph, answer analysts' questions over a realistic bank-shaped database
> **accurately, safely** (refusing rather than returning wrong answers), **auditably**,
> and at **acceptable cost**? Does a self-optimising agent (DSPy + GEPA) improve it
> measurably and reproducibly over a fixed pipeline and over plain text-to-SQL?

Three hypotheses, each with a measurement that can falsify it:

| # | Hypothesis | Falsified if |
|---|---|---|
| H1 | Grounding through FIBO, with graph re-ranking, beats both "whole ontology in the prompt" and plain text retrieval once the vocabulary is FIBO-sized. | Concept recall@5 and end-to-end accuracy are not better than the in-context baseline on the held-out split. |
| H2 | The ontology route (bounded plan → SPARQL → Ontop → SQL) produces fewer wrong-but-executed answers than text-to-SQL and a generic tool agent, at comparable accuracy. | Its wrong-but-executed rate is not lower (paired McNemar p ≥ 0.05), or its accuracy is more than 5 pp lower. |
| H3 | GEPA optimisation of the DSPy program improves held-out accuracy, and the gain survives re-runs and a fresh split. | The test-split gain is under 3 pp, or not reproducible across 3 seeds. |

---

## 2. Data: what "at scale" means here

| Dataset | What it adds | Size | Licence | Role |
|---|---|---|---|---|
| **FIBEN** (IBM) | All **152 tables**. 135 are class-hierarchy tables (primary key = foreign key to the parent: 118 under `DISCLOSURE`, 8 under `ELEMENTOFFINANCIALSTATEMENT`, …). 24 foreign keys are named after FIBO object properties (`isProvidedBy`, `isTradedOn`, `hasCurrency`, `isOwnedBy` …). Real data, about 80 MB of CSV. 300 questions → 237 gold SQL queries; 130 non-nested, 170 nested. | 152 tables | Apache-2.0 | **Primary benchmark**, banking- and markets-shaped |
| **Full FIBO** (local copy, `Ontology Repository/FIBO`) | About 3,150 classes, 1,200 properties, 17k labels, 6k definitions, 12k individuals, 3.2k restrictions | ontology only | MIT (EDM Council) | **The grounding search space.** Two tiers: the *mapped* part (answerable) and *FIBO-known but unmapped* (used to explain refusals) |
| **BIRD `financial`** (Czech bank: accounts, clients, loans, cards, transactions) | Retail-banking semantics FIBEN lacks (loans, cards, transactions); a second, hand-written FIBO mapping, which tests how well the approach transfers | 8 tables, about 100 dev questions (count to verify) | CC BY-SA 4.0 | **Transfer test** (no tuning on it) |
| **ACME insurance** (data.world) | The only benchmark with published ontology-vs-SQL numbers (16.7 / 54.2 / 72.55 / 97.4%) | 13 tables, 43 questions | Apache-2.0 | **Comparability with the literature** (test only) |
| **GLEIF LEI data** (optional, P4) | Millions of real legal-entity names, which stress value grounding at bank scale | millions of rows | open (CC0, to verify) | **Value-index scale test** |

"At scale" means three things, and each is measured separately:
1. **Vocabulary scale.** About 170 mapped FIBEN classes inside about 3,150 FIBO classes.
   The PoC so far had 13.
2. **Structural scale.** Deep class hierarchies (Ontop reasoning), multi-hop
   party / account / security / transaction paths, and nested queries.
3. **Value scale.** Real entity names, tickers and codes (FIBEN), then optionally millions
   (GLEIF).

---

## 3. Architecture

The compilation plane of the existing PoC stays unchanged (offline Ontop sidecar +
compiler, no database, no internet). Everything new sits in front of it.

```
BUILD TIME (deterministic, versioned "knowledge pack")
 FIBEN DDL ─► ontology reconstruction ─► alignment to FIBO IRIs (suggested by embeddings/LLM, reviewed by a person)
          └► auto-generated R2RML (subclass tables → rr:class + rdfs:subClassOf; FKs → object properties)
 FIBO + mapping ─► query graph (allowed edges from restrictions + domain/range, unmapped edges cost ∞)
               ─► two-tier concept index (lexical: labels/synonyms/abbreviations; dense: definitions)
 data (through the mapping) ─► value index (names, tickers, codes; personal data excluded by policy)
 gold SPARQL bank ─► example bank (execution-verified)

RUNTIME (a DSPy program; every LLM step is an optimisable module)
 question
  → [M1 Mentions]      LLM: find concept, value and operator phrases
  → candidates          lexical + dense retrieval over the two-tier index (top-k per mention)
  → graph re-rank       Steiner tree / Personalized PageRank; no connection → clarify
  → [M2 Plan]           LLM: bounded choice among ranked trees + aggregation/grain → IR (JSON, terms limited to enums)
  → render              deterministic IR → SPARQL (only constructs the compiler supports)
  → validate            parse · restriction-aware ontology query check (OBQC) · compile (Ontop) · result sanity
  → [M3 Repair]         LLM: ≤ 2 retries, given only the checker's messages
  → [M4 Clarify/Refuse] LLM: an explanation grounded in the two-tier index
  → execute (caller's DB role) → rows + provenance (concepts, tree, IR, SPARQL, SQL, prompt version)
```

Implementation notes:
* **Graph and index.** For the PoC, use in-memory networkx plus a vector index. In SIP this
  becomes the FalkorDB derived projection. Only the *query graph* is projected, not raw
  OWL, which is lossy as a property graph.
* **The R2RML for FIBEN is generated, not written by hand.** 135 subclass foreign keys and
  24 relationship foreign keys follow two patterns. Upper-case names lose their word
  boundaries (`LONGLIVEDASSETSHELDFORSALE`), so they need word segmentation and alignment
  to FIBO IRIs. That alignment is the *design-time mapping* problem: automated
  suggestions, approved by a person, recorded with provenance.
* **DSPy models.** Use DSPy through LiteLLM (`anthropic/claude-sonnet-5-5` for the program;
  `claude-opus-5-5` as GEPA's reflection model, to be confirmed). P0 includes a spike that
  checks how DSPy/LiteLLM handles the current Claude API constraints: Opus 5.5 always
  thinks, and forced tool choice is rejected.
* **Offline by default.** A deterministic simulator stands in for every LLM module, so the
  harness, the metrics and CI run without API calls. Live runs are opt-in and approved
  per run.

---

## 4. Self-optimisation with DSPy + GEPA

### 4.1 Why GEPA fits

* GEPA (Agrawal et al., ICLR 2026) evolves prompts by **reflecting on rich textual
  feedback**. It reported an average +6 pp over GRPO with up to 35× fewer rollouts, and
  more than +10 pp over MIPROv2.
* This pipeline produces exactly that kind of feedback, deterministically:
  * ontology-check violations ("`isOwnedBy` expects `FinancialServiceAccount` as subject,
    got `Person`");
  * compiler 422s;
  * grounding misses (gold concept not in the top-k);
  * differences between returned rows and the gold rows;
  * grain errors.
* That combination (cheap, precise, explainable feedback) is GEPA's best case.
* **Caveat:** GEPA has not been evaluated on NL2Query. Its value here is a hypothesis
  (H3), not an established result.

### 4.2 What GEPA optimises, and what it does not

| Component | Optimiser |
|---|---|
| Instructions of M1–M4 (mention extraction, plan choice, repair, clarification) | **GEPA** (`dspy.GEPA`, metric returns `dspy.Prediction(score, feedback)`) |
| Few-shot demonstrations per module | GEPA / DSPy bootstrapping, drawn from the train-split example bank only |
| Re-ranker numbers (λ, edge costs, k, PageRank damping) | **Numeric search** (grid or Optuna). These are not prompts. |
| Knowledge pack (synonyms, glossary, metric definitions) | Curation. GEPA can *propose* glossary entries from failures, but **a person approves them** (§4.4). |
| Model tier, effort level | Grid, by cost per correct answer |

### 4.3 The metric GEPA optimises (a weighted sum, with feedback text)

```
score = 1.0 · correct_on_all_K_db_variants
      − 2.0 · wrong_but_executed          # wrong answers cost more than refusals
      + 0.3 · correct_refusal             # on gold "cannot answer" questions
      − 0.3 · unnecessary_refusal
feedback = checker messages + grounding diff + row diff + grain notes
```

* The weights are fixed before optimisation starts.
* The scored components are reported separately, so GEPA cannot hide a safety regression
  inside the total.

### 4.4 "Self-evolving", in a form a bank can accept

Self-evolution is a **governed release loop**, not online learning:

```
production logs ─► failures + user feedback ─► triage by a person ─► new gold items (train/val only)
      ▲                                                               │
      │                       GEPA re-optimisation (offline, budgeted) ◄┘
      │                                       │
  deploy ◄── release gate (person) ◄── regression suite: frozen test + all past gold, safety thresholds
```

* No prompt reaches production without passing the frozen test set and a human release
  gate. This mirrors SIP's existing release gate.
* Every answer records which program version produced it, so results can be audited and
  rolled back.
* User feedback is noisy, so it only ever becomes gold after a person validates it.

---

## 5. Evaluation design

**Splits.**
* Split FIBEN by **`uniqueQueryID`**, so paraphrases never cross splits:
  * train 40%: example bank and GEPA training set;
  * validation 20%: GEPA's Pareto set and numeric tuning;
  * test 40%: frozen, scored only for a release candidate.
* Stratify by query type (non-nested, N, A, J, JA).
* BIRD `financial` and ACME are **test-only**.

**Gold answers.**
* FIBEN gold SQL is transpiled from Db2 to DuckDB (sqlglot) and executed: the gold rows.
* Gold **SPARQL** is written per unique query (LLM-drafted), and accepted only when its
  compiled SQL returns the gold rows.
* This gives the **compiler ceiling**: the share of FIBEN questions the VKG route can
  express at all. Nested types are the risk.
* The result is also a new artefact: a FIBO NL→SPARQL benchmark that executes against a
  VKG. None exists publicly.

**Discriminative accuracy.**
* Score on K = 5 perturbed database instances:
  * shuffled foreign keys;
  * duplicated one-to-many edges, to expose fan traps;
  * moved subclass membership;
  * homonym entities.
* The metric itself is validated with **mutation tests** on gold queries. Target: at least
  95% of mutants caught.

**Grounding metrics** (gold is extracted from the gold SPARQL automatically):
* concept recall@k;
* path accuracy, including "no path → clarify";
* value-linking accuracy;
* aggregation / grain correctness.

**Safety metrics:**
* wrong-but-executed rate (the headline);
* refusal precision and recall on gold "cannot answer" questions. These are written against
  *unmapped* FIBO concepts and out-of-domain topics, and make up about 15% of each split.
* A penalty score, reported against the abstain-on-everything floor.

**Arms**, compared on identical questions with at least 3 runs each:

| Arm | Description |
|---|---|
| T | Text-to-SQL over the raw FIBEN DDL (strong prompt, examples from the same train split) |
| G | A generic tool-using agent (schema browse + SQL execute) |
| S | The fixed ontology pipeline (§3), hand-written prompts |
| S+GEPA | S after GEPA optimisation |
| S+GEPA − X | Ablations: no graph re-rank; no restriction edges; no value index; no FIBO annotations; knowledge as markdown instead of a graph |

**Statistics.**
* Paired exact McNemar on correct answers; paired bootstrap CIs (10k resamples).
* Kappa against human review for any LLM-judged item.
* Report per query type.

**Contamination probes.** FIBO and FIBEN are public, so also score:
* a renamed-schema copy (opaque table and column names, mapping updated);
* fresh paraphrases of the test questions.

A drop much larger than the paraphrase noise indicates memorisation.

---

## 6. Phases

| Phase | Work | LLM | Deliverable | Exit criterion |
|---|---|---|---|---|
| **P0 Foundations** (offline) | Load FIBEN into DuckDB; transpile and execute gold SQL. Reconstruct the ontology from the DDL; generate the R2RML; align to FIBO (suggestions + review). Ontop compiles over all 152 tables. Build the query graph, two-tier index and value index. Write the IR renderer, restriction-aware OBQC and simulator modules. Build the eval harness with K variants and mutation tests. Run the DSPy/LiteLLM spike. | No (spike: a few calls, approved) | Knowledge pack v1, harness, gold rows | Gold SQL execution ≥ 95% of the 237 queries. Ontop compiles a probe query per class. Mutants caught ≥ 95%. Simulator run end-to-end green. |
| **P1 Gold SPARQL and compiler ceiling** | Draft and verify gold SPARQL for the 237 unique queries | Yes (batch, approved) | FIBO-VKG gold SPARQL set; ceiling per query type | Ceiling measured. If below 60% overall, rescope to the expressible subset and report it. |
| **P2 Baselines** | Arms T, G and S on train/val. Retriever comparison for H1 (in-context, BM25, dense, hybrid + graph re-rank, optionally OWL2Vec*). | Yes | Baseline table with CIs | H1 decided on validation |
| **P3 Optimisation** | GEPA on S (light, then medium budget); numeric re-ranker tuning; ablations; freeze; score test once | Yes | Release-candidate program; H2/H3 verdicts | §8 thresholds evaluated |
| **P4 Transfer and scale** | BIRD `financial` with a hand-written FIBO mapping (no re-tuning); ACME; optionally the GLEIF value-index scale test | Yes | Transfer report | Transfer drop quantified; ACME comparable with the literature |
| **P5 Bank-readiness review** | Threat model, access control under the caller's role, audit log, data-flow and residency options, governed evolution loop dry-run | Minimal | Productisation brief | Go / no-go (§8) |

Rough effort for one engineer with assistance: P0 3–4 weeks, P1 1–2, P2 2, P3 2–3, P4 2,
P5 1–2. This is an estimate, to be re-planned after P0.

**Cost envelope** (estimate, measured in P2):
* About 1–3 US cents per question per run on Sonnet 5.5.
* A full arm sweep (about 120 test questions × 4 arms × 3 runs): roughly US$15–50.
* One GEPA medium run (thousands of metric calls): roughly US$50–200, plus the reflection
  model.
* The Batch API halves non-interactive costs.

Every live run needs explicit approval (`ANTHROPIC_API_KEY` is set in this environment).

---

## 7. Bank-productisation requirements, designed in from P0

* **Data flow.** The LLM sees only the question, ontology fragments and value candidates.
  Rows never go to the model. The value index excludes personal data by default, and
  customer names are a policy switch.
* **Deployment options.** The model runs either on a cloud provider in-region (Bedrock,
  Vertex or Foundry, EU regions) or self-hosted. GEPA also optimises small open models (the
  paper used Qwen3-8B), which keeps an on-premises option open.
* **Access control.** Generated SQL is read-only and runs under the *caller's* database
  role. Row-level security and masking are enforced by the database, not the model. Query
  cost and row limits apply.
* **Auditability.** Every answer stores:
  * question, concepts and tree;
  * IR, SPARQL and SQL;
  * result hash;
  * knowledge-pack version and program version.

  The SPARQL and IR are themselves a readable explanation of the answer.
* **Governance.** Program versions are released through the human gate (§4.4). Evaluation
  reports are kept as model-risk evidence. Which regulations apply (model risk management,
  ICT-risk rules such as DORA, AI Act classification) is to be confirmed with compliance,
  not assumed here.
* **Mapping as the main ongoing cost.** Refusals on unmapped concepts are logged as the
  mapping backlog. That is how coverage grows in a bank.

---

## 8. Go / no-go criteria for a bank product

These are initial thresholds, revisited after P2 with real baselines. All are measured on
the frozen FIBEN test split, plus BIRD `financial` for transfer.

| Criterion | Threshold |
|---|---|
| Accuracy (correct on all K variants), within the compiler ceiling | ≥ 85%, and not worse than arm T |
| Wrong-but-executed | ≤ 2% (and significantly below T and G) |
| Refusal precision / recall on "cannot answer" | ≥ 0.9 / ≥ 0.8 |
| Transfer drop on BIRD `financial` | ≤ 15 pp |
| Run-to-run stability (same answer, 3 runs) | ≥ 90% of questions |
| Latency P95 / cost per question | ≤ 10 s / ≤ US$0.05 |
| GEPA gain (H3) | ≥ 3 pp on test, reproduced over 3 seeds; otherwise ship the fixed pipeline |

On ATHENA++: its published 88.33% on FIBEN is a *reference*, not a like-for-like target.
It used a different protocol and no wrong-but-executed accounting.

---

## 9. Main risks

* **Nested FIBEN queries exceed the VKG route.** P1 measures the ceiling early. Fallback:
  answer the non-nested subset, and refuse the rest with an explanation.
* **FIBEN ontology reconstruction and alignment quality.** Mistakes in the mapping are
  systematic and silent. Mitigations: a person reviews the alignment, and mapping tests
  compare the data materialised through the mapping with the gold rows.
* **GEPA overfitting a small train/validation set.** Mitigations: Pareto selection on
  validation, a frozen test set, a fresh-paraphrase probe, and seeds.
* **Benchmark leakage.** FIBEN is public. The renamed-schema probe guards against
  memorisation, and the design is frozen before the test split is touched.
* **FIBEN gold errors.** A 2026 audit found 50–60% annotation errors in other benchmarks.
  Budget time to triage disagreements, and report corrected and uncorrected scores.

---

## Sources

* GEPA: Agrawal et al., *Reflective Prompt Evolution Can Outperform Reinforcement Learning*, ICLR 2026 — https://arxiv.org/abs/2507.19457 ; code https://github.com/gepa-ai/gepa
* DSPy GEPA API — https://dspy.ai/api/optimizers/GEPA/overview/ ; https://dspy.ai/diving-deeper/gepa-in-depth/
* FIBEN — https://github.com/IBM/fiben-benchmark ; ATHENA++ https://www.vldb.org/pvldb/vol13/p2747-sen.pdf
* ACME — https://github.com/datadotworld/cwd-benchmark-data
* BIRD — https://bird-bench.github.io
* Evidence base and further sources — `knowledge/NL2Q/reports/NL2Query state of the art 2026.md`
