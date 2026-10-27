# Evaluation Specification & Methodology: Neuro-Symbolic NL2Q (With vs. Without Ontologies)

* **Document ID:** EVAL-SPEC-NL2Q-2026-V3.1 (supersedes V2; changes in §9)
* **Date:** 2026-10-27
* **Scope:** Standardized Evaluation Protocol for FIBO/FIBEN NL2Q PoC v2.0 and Cross-Benchmark PoCs (ACME Insurance, BIRD `financial`, FIBEN-Obfuscated)
* **Core Engine Anchor:** Verified `SPARQL-2-SQL` Compiler (Ontop 5.5.0 sidecar + sqlglot transpiler + DuckDB 1.5.6 execution worker)
* **Implementation:** `nl2q/evalkit/` (stages and status in §8)

---

## 1. Executive Summary & Experimental Philosophy

A recurring flaw in enterprise AI evaluations is treating **"With Ontology"** versus **"Without Ontology"** as a binary black-box comparison. When an ontology-backed system outperforms a naive zero-shot Text-to-SQL prompt, stakeholders cannot tell whether the gain came from:
* **better prose definitions**, which could equally have been placed in SQL `COMMENT ON` statements or a Markdown data catalog; or
* **true semantic graph capabilities**: taxonomic `rdfs:subClassOf` reasoning, explicit join-path encapsulation, SHACL closed-world validation, and VoID empirical partition metadata.

Conversely, when an ontology-backed system underperforms, the cause has to be located before it is blamed on the Virtual Knowledge Graph (VKG) paradigm. PoC v1.0 is the cautionary example. Its weak grounding recall was first attributed to missing definitions (172 of 220 mapped terms had none). Enriching those terms to 216/220 changed recall by less than one point (`RESULTS.md` §5.1). The real loss was the **vocabulary gap** between business phrasing ("company name", "bought") and formal labels.

This specification establishes a **multi-gate evaluation methodology**. Its conclusions are protected by a pre-registered statistical analysis plan (§5.5) and explicit contamination controls (§4.5). It is designed to:
1. **Isolate the value of each semantic layer** via a **Semantic Ladder (`L0`–`L4`, with control `L1.5`)**. Every rung changes one factor.
2. **Modularize the agentic runtime into 6 testable ports (`C1`–`C6`)**, with **oracle-injected ablations** that bound the loss at each stage of the Grounding → Abstention → Query Synthesis path.
3. **Evaluate the ontology and data artifacts intrinsically** at build time. Must-pass checks gate the LLM runs; reported-only checks never block them (Gate 1).
4. **Score SQL and SPARQL arms on an identical execution and safety yardstick** across perturbed and synthetic witness instances (`Base + V1–V6`).

---

## 2. The "Semantic Ladder": Controlled Experimental Arms

**Controls common to every arm:**
* the **same foundation model snapshot and decoding settings** (§5.5.6);
* the **same train/val/test splits**, split by gold query so paraphrases never cross splits;
* the **same ABox Value Index** (`81,681` indexed database values);
* the **same prompt-optimization budget** (§5.5.5);
* a **context-token budget** that is either equal across arms or reported as a covariate. More context is not better structure: in v1, arm S2 answered more but worse.

| Ladder Level | Arm Identifier | Schema & Semantic Context Provided to the Agent | Target Query Language & Execution Route | Primary Hypothesis Isolated |
| :--- | :--- | :--- | :--- | :--- |
| **L0** | **`Arm T-Raw`** *(Physical DDL Baseline)* | Raw physical SQL DDL (`CREATE TABLE`, PK/FK constraints) + top-$k$ ABox value matches. Zero prose definitions. | `NL → SQL → DuckDB` | Baseline LLM performance relying solely on physical table/column names and memorized SQL patterns. |
| **L1** | **`Arm T-Catalog`** *(Enriched DDL / Markdown Control)* | Raw SQL DDL **+ the exact same prose definitions, synonyms (`skos:altLabel`), and column statistics** as the ontology arms receive, as a Markdown Data Dictionary. | `NL → SQL → DuckDB` | **Crucial control:** the lift of *prose documentation* (`L1 − L0`). |
| **L1.5** | **`Arm T-Views`** *(Flattened-Hierarchy Control)* | `L1` context + SQL views that pre-flatten every class hierarchy (`ElementOfFinancialStatement` = union of its 8 subclass tables; `Disclosure` = union of its 118). | `NL → SQL over views → DuckDB` | Separates **taxonomic reasoning** (`L1.5 − L1`) from the **change of query language and Ontop route** (`L2 − L1.5`). |
| **L2** | **`Arm B-TBox`** *(Open-World Ontology + OBQC)* | OWL TBox + R2RML mapping + restriction-aware **OBQC** static checker + $\le 2$ repair retries. | `NL → Free SPARQL → Ontop → SQL → DuckDB` | The lift of **join encapsulation and static domain/range checking** over SQL with the same hierarchy knowledge. |
| **L3** | **`Arm S-v2`** *(Closed-World VoID/SHACL + Bounded IR)* | TBox + **VoID Partition Metadata** (entity counts, empirical join cardinalities, min/max bounds) + **SHACL Shapes** + **Dedicated Refusal Gate (`C4`)** + **Bounded JSON IR**. | `NL → Bounded IR → Deterministic SPARQL → Ontop → SQL` | The lift of **closed-world data awareness, decoupled abstention, and syntax-error-free IR compilation**. |
| **L4** | **`Arm S-Agentic`** *(Multi-Path)* | All `L3` features + **Multi-Candidate Diversity / Ontology-ReAct / Execution Critic (`C6`)**. | `NL → Multi-IR + Critic → SPARQL → Ontop → SQL` | The **upper bound of multi-path neuro-symbolic agents** against unconstrained SQL tool agents (`Arm G`). |

**Factors crossed with the ladder** (each reported as a separate column, never folded into a rung):
* **Enrichment `E0` / `E1`.** E0 is the FIBO-exact pack (48/220 definitions). E1 adds reviewed FIBO, US GAAP and derived definitions (216/220). Measured so far: +0.6 pp candidate recall without the glossary and −2.7 pp with it (`RESULTS.md` §5.1). It is therefore a factor to measure, not the baseline.
* **Glossary `G0` / `Gtrain`.** No glossary, or a glossary authored from the **train split only** (§4.5). The v1 glossary (`Gv1`) was written after seeing all gold SQL. It is used only for reproducing v1 numbers, and every result that uses it is labelled *possibly contaminated*.
* **Optimization `fixed` / `GEPA`.** Every arm is reported with its fixed prompt. A GEPA row is added only when **every** compared arm received the same optimization budget (§5.5.5).

---

## 3. Componentized System Architecture & Oracle Testability (`C1`–`C6`)

To evaluate techniques from **TEXT2SPARQL/CK25**, **data.world**, **BIRD**, and **Spider 2.0** without rebuilding the pipeline each time, the runtime is partitioned into **six pluggable ports (`C1`–`C6`)** (`nl2q/evalkit/ports.py`). Every port implements a typed contract and supports an **`OracleAdapter`** that injects ground-truth intermediate outputs (§5, Gate 2: sources of each oracle):

```text
User Question
  │
  ▼
[C1: Decomposer & Mention Extractor] ──► MentionSet (concept spans, value spans, sub-questions, skeleton)
  │
  ▼
[C2: Dual-Strategy Concept & Value Linker]
  ├──► TBox Engine (Hybrid Dense + BM25 over FIBO/FRO labels, synonyms, definitions)
  └──► ABox Engine (Lexical BM25 + Char 3-gram + Edit Distance over 81,681 DB values)
  │
  ▼
[C3: Data-Aware Subgraph Pruner] ──► GroundedSubgraph (Steiner/PPR tree + VoID counts & N:1/1:N tags + SHACL shapes)
  │
  ├────────────────────────────────────────────┐
  ▼                                            ▼
[C4: Dedicated Refusal & Clarification Gate] [C5: Symbolic Query Synthesizer]
  │ (Decoupled from Planner to prevent S2      │ (Bounded IR / Compositional / Multi-Path)
  │  hallucinations on unmapped links)         ▼
  ▼                                          Deterministic Renderer ──► SPARQL ──► OBQC + Ontop Compiler
Explainable Abstention / Clarification                                               │
                                                                                     ▼
                                             [C6: Static & Execution Critic] ◄── DuckDB Worker (sqlworker.py)
```

Every port records **its own latency, token count and cost**, so the operational envelope (§5, Gate 4) can be attributed to C1–C6.

### Pluggable Technique Matrix Across Ports

| Port | Baseline Adapter (v1) | Competition-Inspired Adapters to Benchmark (v2) | Isolated Component Metrics (Gate 2) |
| :--- | :--- | :--- | :--- |
| **`C1`** | Rule-based phrase extractor | • Zero-shot LLM Mention Extractor (`M1`)<br>• **Sub-Question Decomposer** (`SPARQL-LLM`, `OntoAxiom`)<br>• **Entity-Masked Skeleton Extractor** (`DAIL-SQL`, `Agentar-Scale-SQL`) | • Mention Span Recall (needs annotated spans, §5 Gate 2)<br>• Skeleton Match Accuracy |
| **`C2`** | BM25 / Char TF-IDF / Hybrid RRF over the mapped tier (E0, K1–K4) | • **Enriched index (E1)**<br>• **Dual-Engine** (Dense+BM25 for TBox; n-gram + Levenshtein for ABox values)<br>• LLM Cross-Encoder Reranker | • **TBox Concept Recall@$k$** ($k \in \{5, 10, 20\}$) & MRR<br>• **ABox Value Linking F1** (exact cell value + owning property) |
| **`C3`** | Unweighted Steiner tree (`Arm S`) or raw 1-hop links (`Arm S2`) | • **VoID-Weighted Steiner Tree / PPR** (weights edges by `void:triples`, penalizes unpopulated paths)<br>• **Hierarchy-Compressed SHACL/VoID Serializer** (`ReFoRCE`, `IIS-Q`)<br>• **Bounded Ontology-ReAct Explorer** (`Arm G-Onto`) | • **Grounding Ceiling** (equivalence-aware, Gate 2)<br>• Subgraph Edge Precision & Token Count |
| **`C4`** | Bundled inside the planner | • **Dedicated Abstention Classifier** (inspects mapped-tier vs. FIBO-tier matches, missing VoID linksets, `void:entities == 0`) | • **Refusal recall per stratum `U1`–`U3`**, false-refusal rate on answerable questions, precision at stated prevalence |
| **`C5`** | Single-pass Bounded IR (`Arm S`) or Free SPARQL (`Arm A`) | • **Grain-Explicit Bounded IR** (`GrainSQL`)<br>• **Divide-and-Conquer Compositional IR** (`CHASE-SQL`, for nested queries)<br>• **Multi-Generator Candidate Pool** ($N=3$–$5$, `PExA`) | • IR Syntax Validity Rate<br>• First-Pass OBQC & Ontop Compilation Pass Rate |
| **`C6`** | Static OBQC repair ($\le 2$ retries) | • **Privacy-Safe Execution Metadata Critic** (`ReFoRCE`: refines on `0 rows`, `100% NULL`, or fan-trap row explosion)<br>• **Execution-Cluster Pairwise Selection Judge** (`XiYan-SQL`, `CHASE-SQL`) | • Repair Recovery Rate<br>• Critic False-Rejection Rate |

---

## 4. Benchmark Datasets & Instance Suite Design

### 4.1 Cross-PoC Dataset Matrix
To show that findings are not an artifact of a single schema, evaluate across four complementary environments:

1. **FIBEN-Standard (Primary Scale Benchmark).**
   * 152 tables (135 subclass tables, 24 object-property FKs), 11.7M rows.
   * 237 gold SQL queries; 300 questions split train 120 / val 63 / test 117.
   * The R2RML is frozen from v1. **Recorded suite compiler ceiling: 219/237 (92%)** on Base + V1–V5.
2. **FIBEN-Obfuscated (Contamination & Legacy Bank Probe).**
   * Identical data and ontology to FIBEN-Standard.
   * The physical table and column names in DuckDB and the R2RML are replaced by opaque legacy identifiers (`TBL_C001`, `ATTR_04`), and the mapping and `db-metadata.json` are regenerated.
   * Separates semantic grounding from LLM memorization of the public FIBEN schema. By design, `L0` loses its name signal here; `L1` keeps the catalog.
3. **ACME Insurance (`cwd-benchmark-data`, literature comparability).**
   * 29 tables, 44 gold queries, human-authored OWL and multi-table `rr:sqlQuery` R2RML views.
   * **Recorded:** 44/44 gold SQL execute; 26/44 gold SPARQL compile through Ontop, and all 26 match.
   * Published reference points come from **different studies**:
     * data.world (GPT-4, 2023): 16.7% raw SQL, 54.2% with the KG;
     * the ontology-based query check: 72.55% with 8% refusals;
     * Semantic Path Compilation (2026): 97.4% on its own 38-question set.

     Cite each with its source and model. They are not one progression.
4. **BIRD `financial` (Zero-Shot Retail Banking Transfer).**
   * 8 tables (accounts, clients, loans, cards, transactions) with a FIBO mapping.
   * **The mapping is authored blind** (§4.5), from the schema and the BIRD column descriptions, before anyone reads the questions.
   * Strictly test-only: no prompt or glossary tuning. Measures the domain-transfer drop (target ≤ 15 pp).

### 4.2 Strengthening the Discriminative Database Suite (`Base + V1–V6`)
Evaluating on base FIBEN data alone is invalid (`RESULTS.md` §1, §7, §9). 96 of the 237 gold queries return empty sets on Base, so base relaxed EX (48–62%) overstates suite accuracy by more than 2× through empty-vs-empty coincidences. Every query is scored on **seven referential-integrity-compliant instances**, with the gold answer on each re-derived by executing the gold SQL on that instance:

* **`Base`:** the original 11.7M-row FIBEN instance.
* **`V1 (Drop)`:** unreferenced leaf rows dropped. Declared FKs are respected, so Ontop join elimination stays sound.
* **`V2 (Rewire)`:** shuffled foreign keys, to catch missing or wrong join predicates.
* **`V3 (Fan-out)`:** materialized duplicated `1:N` edges, to expose fan traps and grain errors (`DISTINCT` vs. non-distinct aggregation).
* **`V4 (Reclassify)`:** materialized shifted subclass memberships.
* **`V5 (Targeted Witness Instance, nl2q/witness.py)`:** 4,540+ synthetic rows:
  * positive witness chains for every filter;
  * two chains per group with distinct measures;
  * filter near-misses;
  * correlated nested rows.

  It converts 78 of 96 empty queries to non-empty.

  **Repaired in V3.1.** The v1 witness rows broke 4 subclass foreign keys: 1,570 subclass rows had no parent row. The builder now adds the parent chain (2,255 rows). The repair left the compiler ceiling unchanged (219/237) and moved executable-mutant detection from 58.3% to 58.5%.
* **`V6 (Taxonomic Counterfactual Witness Instance, nl2q/evalkit/v6.py)`:** remedies v1's superclass-mutation blind spot. Superclass swaps were caught only 9 of 218 times, because every `Security` is a `ListedSecurity`.
  * For every subclass relationship $C_{\text{sub}} \sqsubseteq C_{\text{super}}$ used by a gold query, V6 inserts rows into $C_{\text{super}}$ (and its parent chain) that are **absent from $C_{\text{sub}}$** and unreferenced by child-only FKs.
  * The witness rows of $C_{\text{sub}}$ are mirrored onto the new superclass-only individual, so replacing $C_{\text{sub}}$ with $C_{\text{super}}$ in a query changes the returned row signature.
  * References to the clone are mirrored only through foreign keys that target $C_{\text{super}}$ or an ancestor; keys that target $C_{\text{sub}}$ are never mirrored, because that would make the instance invalid.

  **Measured (V3.1):**
  * V6 is valid (zero dangling keys) and changes the gold answer of 63 queries.
  * All 219 accepted gold SPARQL queries also agree on V6.
  * **199 of the 218 v1 superclass mutants are *equivalent under the declared keys*.** The swapped variable is reached through a key that targets the subclass (e.g. `HOLDING.REFERSTO → LISTEDSECURITY`), so no valid instance can tell the two queries apart. v1's "9/218 detected" was measuring the schema, not the test suite.
  * On the 19 remaining swaps, V6 adds no detection beyond Base.

### 4.3 Stratified Unanswerable & Abstention Benchmark (`U1`–`U3`)
Each split includes an **Unanswerable & Clarification Suite**. Every stratum is labelled **by construction** from the ontology and the data, never from the gold:
* **`U1` (FIBO-Known, Unmapped Concept):** the question targets a FIBO-tier concept (4,079 terms) with no R2RML mapping. Construction: the target term's IRI is not in the mapped tier.
* **`U2` (Mapped Concepts, Unmapped Relationship):** both classes are mapped (220 terms), but no mapped path links them in the requested sense. Construction: no edge between them in the allowed-edge graph, inheritance included. This directly regression-tests the **Arm S2** trap.
* **`U3` (Out-of-Range Slice):** the filter lies outside the populated VoID bounds, e.g. a year with no facts or an unknown ticker. Construction: the filter value is absent from the value index or outside the min/max partition bounds. Grain ambiguity, which has no objective construction, is held out of U3. It may be added only as **`U3b`**, labelled by two annotators, with Cohen's κ reported and κ ≥ 0.7 required.

### 4.4 Stratification Tags for Slice Analysis
Every answerable question is tagged across four structural dimensions, derived automatically from the gold SPARQL and the schema (`nl2q/evalkit/slices.py`). Results are reported per slice rather than hidden in one macro-average:
1. **Taxonomic Reasoning Depth:** `Single-Table Leaf` vs. `Superclass Hierarchy Union`. Examples: `ElementOfFinancialStatement` spans 8 subclass tables; `Disclosure` spans 118.
2. **Query Nesting Type:** `non-nested`, `type-a`, `type-j`, `type-ja`, `type-n`.
3. **Join Path Complexity:** `0–1 hops` vs. `2 hops` vs. `3+ hops`.
4. **Fan-Trap Risk:** `Functional (N:1 / 1:1 joins only)` vs. `Multi-Grain / 1:N Fan-Trap Risk`.

Slice results are **descriptive**. A slice difference counts as a finding only if it is a pre-registered secondary hypothesis (§5.5.1) and survives the Holm correction.

### 4.5 Contamination & Leakage Controls

| Risk | Control | Verified by |
| :--- | :--- | :--- |
| Curated knowledge written after seeing the gold (the v1 glossary) | `Gv1` is used only to reproduce v1. `Gtrain` is authored from train-split gold only, and its author's access is logged. | Glossary entries list the train query IDs they were derived from |
| Enrichment reading benchmark answers | `nl2q/enrich.py` may not import or read gold, splits or questions | `tests/test_enrich.py::test_enrichment_cannot_read_benchmark_answers` |
| A transfer mapping tuned to its questions (BIRD) | The mapping is authored and committed before the questions file is opened; the commit precedes the first evaluation run | Git history |
| Schema memorization (FIBEN public since 2020) | FIBEN-Obfuscated | §4.1 |
| Question memorization | **Fresh-paraphrase probe:** 30 test questions re-phrased by a person who has not seen FIBEN. The accuracy drop vs. the originals is reported. | Scorecard Table C, column "Δ paraphrase" |
| Test-set reuse | The test split is scored only for a frozen release candidate (`PLAN.md` §4.4), and every scoring is logged | Run registry |

---

## 5. The 4-Gate Evaluation Protocol & Metrics

Evaluation proceeds through four gates. A higher gate runs only after the **must-pass** checks of the lower gates pass. Reported-only checks never block a run. This preserves the API budget and keeps the diagnosis clear.

---

### Gate 1: Build-Time Ontology, Mapping & Metric Health ($0 API Cost)

**Tooling.** OOPS!, FOOPS! and Themis need Java (not installed here) or their public web services. Sending the ontology to a public service is an outward-facing decision, taken explicitly per campaign and off by default. The offline fallbacks are:

| Spec tool | Offline fallback | Coverage note |
| :--- | :--- | :--- |
| OOPS! (41 pitfalls) | SIP Ontology Validation Agent (`capabilities/ontology_agents/validation_agent`, 131 checks in 16 families) | The scorecard lists which OOPS! pitfall IDs the fallback covers |
| FOOPS! (FAIR) | Annotation-coverage and metadata checks (`nl2q/evalkit/gate1.py`) | Coverage and labels only; no FAIR resolvability tests offline |
| Themis | Competency questions as SPARQL `ASK` tests over the TBox (`artifacts/eval/cq/*.rq`) | Same pass/fail semantics |
| SHACL validator | pySHACL 0.40 on shapes generated from the DDL (keys, datatypes, FK targets) | Full |

| Check | Tool / Module | Metric Recorded | Status | Exit Threshold |
| :--- | :--- | :--- | :--- | :--- |
| **1.1 Structural & Logical Pitfall Scan** | OOPS! or fallback | Count of `Critical`, `Important`, `Minor` findings | **Reported** | Critical findings documented with a disposition |
| **1.2 Annotation Completeness** | `knowledge.py` / `enrich.py` | Share of mapped terms (152 classes, 68 properties) with `rdfs:label` and a definition, **per enrichment level** | **Reported** | Recorded: E0 48/220, E1 216/220. The 4 E1 gaps (`AutonomousAgent`, `Country`, `FinancialReport`, `ElementsOfFinancialReport`) need OMG Commons / LCC. |
| **1.3 Competency & Closed-World Conformance** | CQ `ASK` tests & pySHACL | CQ pass rate; SHACL conformance per instance `Base + V1–V6` | **Must-pass** | 100% CQ; zero SHACL violations on every instance |
| **1.4 Compiler Ceiling & Metric Mutation Power** | `ceiling.py`, `mutate.py` on `Base + V1–V6` | Suite compiler ceiling; mutant detection rate (all / non-empty gold / superclass swaps **excluding swaps equivalent under the declared keys**) | **Must-pass** (no regression) | Ceiling ≥ the recorded value (FIBEN 219/237, ACME 26/44); detection ≥ the recorded value. **Goals** (reported, not gating): non-empty detection ≥ 90%, superclass detection ≥ 75% on non-equivalent swaps. **Recorded (V3.1):** 58.4% / 61.9% / 44.4% (8 of 18 executable, non-empty); 199 of 218 swaps equivalent. |

---

### Gate 2: Component-Level Unit Evaluations (Isolated Port Benchmarks)

**Sources of the oracles.** Each oracle has a stated provenance:
* **Gold terms (`gold_tier1_iris`), gold edges (`gold_subgraph_edges`) and filter values (`gold_filter_values`)** are extracted automatically from the accepted gold SPARQL (`nl2q/evalkit/gold_intermediates.py`).
* **Gold mention spans** cannot be derived from SPARQL. They need **human span annotation** of the questions. The annotator, date and inter-annotator agreement on a 20% double-annotated sample are recorded. Until the annotation exists, the `C1` oracle substitutes value spans found verbatim in the question, and is labelled *partial*.

1. **Retrieval Quality (`C1 + C2`):**
   * $\text{Concept Recall@}k = \frac{|\text{Retrieved mapped IRIs}_k \cap \text{Gold IRIs}|}{|\text{Gold IRIs}|}$ for $k \in \{5, 10, 20\}$, plus MRR.
   * **Value Linking F1:** precision and recall of `(value, owning property)` pairs against `gold_filter_values`.
2. **Subgraph Pruning Quality (`C3`):**
   * **Grounding Ceiling (equivalence-aware):** the share of answerable questions whose pruned subgraph contains a sufficient term set. A term set is sufficient if it covers the gold terms **up to the equivalences this data makes true**: a superclass that has no instances outside the gold subclass on every instance, or an alternative path whose query passes the suite. A literal gold-term match alone would count valid alternatives as misses.
   * **Subgraph Edge Precision** $= \frac{|\text{Gold Edges} \cap \text{Subgraph Edges}|}{|\text{Subgraph Edges}|}$, reported next to the subgraph's token count.
3. **Refusal Gate Accuracy (`C4`)**, on the combined answerable + `U1`–`U3` validation split:
   * **Refusal recall** per stratum and overall (target ≥ 0.80);
   * **False-refusal rate** on answerable questions;
   * **Refusal precision at a stated prevalence:** precision depends on the share of unanswerables, so it is reported at the split's actual mix **and** re-weighted to a fixed 20% unanswerable prevalence (target ≥ 0.90).

---

### Gate 3: The Oracle-Injected Diagnostic Matrix (Ceilings Along One Path)

Before full multi-seed sweeps, run the matrix on the validation split: $n = 63$ answerable + $n = 24$–$60$ unanswerable, single run. **Estimated cost:** 5 runs × ~87–123 questions × ~US$0.02 ≈ **US$9–13**, recorded per call.

| Diagnostic Run | `C1` (Mentions) | `C2` (Linker) | `C3` (Subgraph) | `C4` (Refusal Gate) | `C5 + C6` (Planner + Repair) | What This Run Measures |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Run O-1 (*Planner Ceiling*)** | Oracle | Oracle | **Oracle Gold Subgraph** | Oracle | **Learned** | Synthesis accuracy given perfect ontology context. |
| **Run O-2 (*Pruning Ceiling*)** | Oracle | **Oracle Candidates** | **Learned** | Oracle | **Learned** | Accuracy when only pruning is learned. |
| **Run O-3 (*Retrieval Ceiling*)** | **Oracle Mentions** | **Learned** | **Learned** | Oracle | **Learned** | Accuracy when linking and pruning are learned. |
| **Run O-4 (*Mention Loss*)** | **Learned** | **Learned** | **Learned** | Oracle | **Learned** | Accuracy with all grounding learned. |
| **Run E2E (*Full Pipeline*)** | **Learned** | **Learned** | **Learned** | **Learned** | **Learned** | End-to-end accuracy and the refusal trade-off. |

**Interpretation rule.** The differences between consecutive runs are **ceilings along this one path**, not an additive decomposition. A component's loss depends on what upstream hands it, so the stage losses need not sum to `O-1 − E2E`. They are interaction effects, not error shares. The run with the largest drop identifies where to look first; it does not apportion blame.

> **Governance Rule:** targeted prompt optimization (**DSPy + GEPA**) is applied to the module(s) showing the largest drop, **and** the comparison arms receive the same optimization budget (§5.5.5) before any ladder comparison is reported.

---

### Gate 4: End-to-End Execution, Safety & Economic Scoring

All candidate arms are scored on the identical execution harness (`nl2q/evaluate.py`, `nl2q/rescore.py`, `nl2q/evalkit/scoring.py`) across **3 independent runs**.

#### 1. Primary Accuracy Metrics
* **Strict Base EX:** exact column and row signature match on `Base`.
* **Relaxed Base EX:** allows omitting extra context columns (e.g. the company names and tickers FIBEN gold SQL projects alongside the answer).
* **Suite Relaxed EX (headline accuracy metric):** relaxed match on **every instance (`Base + V1–V6`)**.
* **Ceiling-Normalized Suite EX:** suite relaxed EX on the questions inside the compiler ceiling, so agent performance is separated from Ontop/compiler limits. The SQL arms are reported on the same question subset.

#### 2. Primary Safety & Abstention Metrics
Every outcome is one of four mutually exclusive states: `Correct`, `Wrong-but-Executed`, `Refused/Clarified`, `Failed/Timeout`.
* **Wrong-but-Executed Rate (headline safety metric):** the share of questions that execute and return rows that disagree with the gold suite signature. Target ≤ 2%, and significantly below the `L0`/`L1` SQL baselines.
* **Cost-Sensitive Banking Utility Score:**
  $$\text{Utility}(c) = \frac{1}{N} \sum_{i=1}^{N} \Big( +1.0 \cdot \mathbb{I}[\text{SuiteCorrect}_i] - c \cdot \mathbb{I}[\text{WrongExecuted}_i] + 0.3 \cdot \mathbb{I}[\text{CorrectRefusal}_i] - 0.3 \cdot \mathbb{I}[\text{FalseRefusal}_i] \Big)$$
  * Reported at $c = 1.0$, $c = 2.0$ (the GEPA objective, `PLAN.md` §4.3) and $c = 5.0$ (strict banking risk aversion).
  * **The abstain-on-everything floor is not 0.** Refusing everything scores $0.3 \cdot (|U| - |A|)/N$, which is negative on a mostly answerable split. The floor is computed and printed per dataset and split.
  * The **four components are always reported next to the total**, so a safety regression cannot hide inside the sum.

#### 3. Statistical Significance, Stability & Operational Economics
Applied as specified in the analysis plan (§5.5):
* **Paired comparisons:** exact McNemar on per-question majority outcomes, plus the **gold-query-clustered paired bootstrap** CI of the difference.
* **Run-to-Run Structural Stability:** share of questions with the same execution signature in all 3 runs (target ≥ 90%).
* **Latency & Cost:**
  * P50 / P95 latency, end to end and per port (capped by the 30 s `sqlworker.py` timeout; target P95 ≤ 10 s);
  * mean cost per question and **cost per correct answer** (target ≤ US$0.05 per question);
  * context tokens per question (the covariate of §2).
* **Curation cost:** person-hours spent on mappings, glossary, review decisions and annotation, per dataset. The business case is accuracy and safety per unit of curation.

---

### 5.5 Statistical Analysis Plan (pre-registered)

Fixed before the test split is scored. Changes after that point are logged as deviations.

#### 5.5.1 Hypotheses
* **Primary (H1):** on the FIBEN test split, the ontology arm (`L3`) has a **lower wrong-but-executed rate** than the documented SQL arm (`L1`).
* **Key secondary (tested in order, Holm-corrected):**
  * H2: `L3` suite relaxed EX ≥ `L1` (non-inferiority margin 5 pp);
  * H3: `L1.5 − L1` > 0 on the superclass-hierarchy slice;
  * H4: `L3` refusal recall on `U2` > `L2`.
* Everything else (other slices, other arm pairs, other metrics) is **exploratory** and labelled as such.

#### 5.5.2 Unit of analysis and clustering
* The 300 questions are paraphrases of 237 gold queries, and paraphrases of one query succeed or fail together.
* All confidence intervals therefore use a **cluster bootstrap that resamples gold queries** (10,000 resamples), carrying all their paraphrases.
* Question-level bootstraps understate the width and are not reported.

#### 5.5.3 Repeated runs
* Each arm runs 3 times. Per question, the **majority outcome** across runs is the unit for McNemar.
* The paired bootstrap resamples gold queries and then runs within each query, so run-to-run variance enters the CI.
* Runs are never pooled as independent questions.

#### 5.5.4 Power and minimum detectable effect
* **Reported with every comparison:** the minimum detectable difference at α = 0.05, power 0.8, using the observed discordant-pair rate.
* **At v1's discordance (~30%):** about **19 pp** on val (n = 63) and **14 pp** on test (n = 117).
* **Interpretation:** a difference below the MDE that is not significant is "not detected", never "no difference".
* **Data needed:** reaching 5 pp needs ~800 questions. This is the case for the fresh-paraphrase and BIRD sets.

#### 5.5.5 Equal optimization budget
* Ladder comparisons use **fixed prompts** for every arm.
* An optimized comparison is reported only when every compared arm received the same GEPA budget: metric calls, reflection model, and train/val data.

#### 5.5.6 Reproducibility pins
Every run records:
* the model snapshot ID and decoding parameters (temperature, max tokens);
* the DSPy, LiteLLM, Ontop, sqlglot and DuckDB versions;
* hashes of the prompt/program, knowledge pack (with enrichment and glossary level), ontology, mapping and gold files;
* the split file and seed.

A result without its pins is not reportable.

---

## 6. Standardized Reporting Template (Per-PoC Scorecard)

Every campaign emits `scorecard.json` and `scorecard.md` (`python -m nl2q.evalkit.scorecard`):

### Table A: Gate 1 Build & Ontology Health Card
| Dataset | Classes / Props | Annotation Coverage (E0 / E1) | Pitfall Findings (Crit / Imp / Min, tool) | CQ Pass | SHACL Violations (Base…V6) | Suite Compiler Ceiling | Mutant Detection (All / Non-empty / Superclass) |
|---|---|---|---|---|---|---|---|
| FIBEN-v2 | 152 / 68 | 48 / 216 of 220 | x / x / x (fallback) | x% | 0 … 0 | 219/237 | x% / x% / x% |

### Table B: Gate 3 Oracle Ceilings (Validation Split, $n = 63$ + unanswerables)
| Diagnostic Stage | Suite EX [95% CI] | Δ vs. previous stage | Where to look first |
|---|---|---|---|
| O-1: Oracle Subgraph → Planner (Planner Ceiling) | xx.x% | — | C5/C6 synthesis |
| O-2: Oracle Candidates → C3 Pruner → Planner | xx.x% | x.x pp | C3 pruning |
| O-3: Oracle Mentions → C2 Linker → C3 → Planner | xx.x% | x.x pp | C2 retrieval |
| O-4: Learned C1 → C2 → C3 → Planner | xx.x% | x.x pp | C1 mentions |
| E2E: Full Pipeline (with C4 Refusal Gate) | xx.x% | x.x pp | C4 abstention trade-off |

*Stage deltas are ceilings along one path, not an additive decomposition (Gate 3).*

### Table C: Gate 4 Semantic Ladder (3-Run Majority; 95% CI by gold-query cluster bootstrap)
| Arm | E / G | Suite EX (All) | Suite EX (Hierarchy Slice) | Suite EX (Nested Slice) | Wrong-but-Executed ↓ | Refusal Recall U1/U2/U3 · False-Refusal ↓ | Utility c=2 / c=5 (floor) ↑ | Δ vs L1 [CI], p, MDE | Stability | Latency P95 | $/Q · $/Correct | Tokens/Q | Δ paraphrase |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L0: T-Raw | | | | | | | | | | | | | |
| L1: T-Catalog | | | | | | | | baseline | | | | | |
| L1.5: T-Views | | | | | | | | | | | | | |
| L2: B-TBox | | | | | | | | | | | | | |
| L3: S-v2 | | | | | | | | | | | | | |
| L4: S-Agentic | | | | | | | | | | | | | |

### Table D: Reproducibility & Curation
| Arm | Model snapshot | Program hash | Pack (E/G) hash | Runs | Curation hours (mapping / glossary / review / annotation) |
|---|---|---|---|---|---|

---

## 7. Governance & Bank-Readiness Go / No-Go Criteria

In line with `PLAN.md` §4.4, §7 and §8, no prompt or architecture reaches release-candidate status without satisfying these criteria on the **frozen test split**, under the analysis plan of §5.5:

1. **Value of the ontology proven:**
   * H1 holds: `L3` (or `L4`) has a lower wrong-but-executed rate than `L1`, with the Holm-corrected $p < 0.05$, and also lower than `L0`.
   * H2 holds (non-inferior accuracy).
   * The hierarchy and obfuscated-schema slices show the expected direction.
2. **Productisation thresholds (`PLAN.md` §8):**
   * **Ceiling-normalized suite accuracy:** ≥ 85% on answerable queries.
   * **Wrong-but-executed rate:** ≤ 2%.
   * **Refusal:** recall ≥ 0.80 per stratum `U1`–`U3`, and precision ≥ 0.90 at 20% prevalence.
   * **Zero-shot transfer drop (BIRD `financial`):** ≤ 15 pp below FIBEN test accuracy, with the mapping authored blind.
   * **Run-to-run stability:** ≥ 90% identical answers across 3 runs.
   * **Operational envelope:** latency P95 ≤ 10 s; mean cost ≤ US$0.05 per question.
   * **Auditability & data privacy:**
     * 100% of runs log the full provenance tuple `(question, mentions, candidate_iris, void_subgraph, gate_decision, ir, sparql, sql, result_hash, pack_version, program_version)` plus the pins of §5.5.6;
     * zero database rows are transmitted to the LLM.
3. **Contamination controls passed** (§4.5): `Gtrain` only, the fresh-paraphrase drop is reported, and the BIRD mapping commit precedes its first run.

---

## 8. Implementation Stages & Status

`nl2q/evalkit/` implements the framework. Each stage ends runnable and tested. Live (billed) runs need explicit approval.

| Stage | Content | Cost | Status |
|---|---|---|---|
| **S1** | This specification (V3) | — | done |
| **S2** | Scoring core: cluster bootstrap, run aggregation, McNemar on majorities, MDE, Holm, utility with floor and components, refusal metrics at prevalence, stability, $/correct, ceiling-normalized EX, slice tags; scorecard Table C from existing runs | $0 | **done**: `evalkit/statistics.py`, `slices.py`, `scoring.py`, `scorecard.py`; `tests/test_evalkit.py` (14). The v1 scorecard (`artifacts/eval/campaigns/fiben_v1_val.scorecard.md`) reproduces `RESULTS.md` §9 exactly. |
| **S3** | Gate 1: V6 instance, SHACL shapes + pySHACL on Base + V1–V6, VoID partitions, CQ ASK tests, annotation coverage, ceiling + mutation on Base + V1–V6, SIP validation-agent scan; Table A | $0 | **done; Gate 1 must-pass: PASS**. Files: `evalkit/gate1.py`, `v6.py`, `shacl.py`, `void.py`, `artifacts/eval/cq/` (17 CQs).<br>• Key integrity: 0 dangling keys on all 7 instances, after the V5 repair.<br>• SHACL: 0 violations on all 7 instances; pySHACL agrees with the SQL compilation on injected defects.<br>• CQs: 17/17.<br>• Ceiling: 219/237, and 219/219 on V6.<br>• OVA (reported): E0 1 major / 415 minor, E1 1 / 157; covers 33 of 41 OOPS! pitfalls.<br>• VoID: 111 of 152 classes are empty.<br>• Rescoring of the v1 live runs on the repaired V5 is in progress. |
| **S4** | Gate 2: gold intermediates from gold SPARQL, recall@k / MRR, value-linking F1, equivalence-aware grounding ceiling, edge precision | $0 | planned |
| **S5** | Ports C1–C6 with OracleAdapters (refactor of `program.py`), per-port latency/tokens/cost; Gate 3 matrix runnable offline with the simulator | $0 (live run ≈ US$9–13) | planned |
| **S6** | Datasets: U1–U3 by construction, FIBEN-Obfuscated, `Gtrain` glossary, L1.5 hierarchy views | $0 | planned |
| **S7** | Arms: L1 T-Catalog, L1.5 T-Views, L3 S-v2 (VoID/SHACL + C4 + IR), L4 S-Agentic | $0 to build; live runs billed | planned |
| **S8** | BIRD `financial` (blind mapping), fresh-paraphrase probe (needs a person), curation-hours log | $0 to build | planned |

---

## 9. Revision Log (V2 → V3)

* **Enrichment** became an ablation factor (`E0`/`E1`) instead of the baseline. Coverage is corrected to 216/220, and the v1 diagnosis is corrected (vocabulary gap, not missing definitions).
* **New `L1.5` arm**, separating hierarchy reasoning from the change of query language. The ladder now has an equal optimization budget and a context-token covariate.
* **Statistical analysis plan (§5.5):** gold-query cluster bootstrap, run handling, MDE, Holm, pre-registered hypotheses.
* **Contamination controls (§4.5):** glossary quarantine (`Gv1` / `Gtrain`), blind BIRD mapping, fresh-paraphrase probe.
* **Gate 1** split into must-pass and reported checks, with offline tool fallbacks. Thresholds replaced by recorded values (ceiling 219/237, ACME 26/44); aspirational targets kept as goals.
* **Gate 2:** oracle provenance stated (mention spans need annotation) and an equivalence-aware grounding ceiling.
* **Gate 3** reinterpreted as ceilings along one path; cost re-estimated.
* **Gate 4:** utility floor computed per split with components shown, refusal precision at a stated prevalence, ceiling-normalized EX on a common subset, reproducibility pins, curation cost.
* **ACME literature figures** attributed to their separate studies.
* **U3** defined by construction; grain ambiguity moved to an annotated `U3b`.

**V3.1 (2026-10-27).** Stage S3 findings folded in:
* V5 repaired (parent rows for subclass witness rows);
* V6 built and validated;
* superclass mutation detection re-based on swaps that are not equivalent under the declared keys;
* Gate 1 passes.
