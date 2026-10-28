# Results: FIBO NL2Q at scale

Measured on 2026-10-19/20 on Windows 11, Docker Desktop 29.6, Ontop 5.5.0 (offline
sidecar), DuckDB 1.5.6, sqlglot 30.22, DSPy 3.0.4, Claude Sonnet 5.5.

**Status.**
* The offline phases are complete.
* The metric was strengthened with a **witness instance** (§7).
* One **small live check** ran: every arm, once, on the 63 validation questions (§9),
  for about US$20 in total.
* GEPA, repeated runs and the test split have not been run.
* The go / no-go criteria of PLAN.md §8 cannot be decided on this evidence: the sample is
  small, and no arm reaches the accuracy thresholds.

> **Updates superseding earlier sections.**
> * The ceiling is now verified on the base data **and** all five variants: **219 of 237
>   (92%)**, 128 of 141 non-empty (§3 shows the base-data-only figures).
> * Mutation detection after strengthening is in §7.

## 1. Data and gold (P0)

* **FIBEN.** All 152 tables loaded into DuckDB: 11,668,125 rows in 149 s.
* **The schema is an ontology encoding.** 135 foreign keys are subclass links (PK = FK to
  the parent), and 24 are object properties named after FIBO properties.
* **Gold SQL: 237 of 237 queries execute** after two minimal repairs of FIBEN defects:
  * sql_id 136 has an unclosed `IN (`;
  * sql_id 172 has a truncated literal.
* **Benchmark data mismatch.** The published data is a regenerated instance
  (transactions 2015-06 to 2016-06, prices at most 200, synthetic people). 96 gold
  queries have **empty** gold results, so only 141 gold queries can discriminate. Every
  result reports accuracy on non-empty gold separately.
* **Splits** by gold query (paraphrases never cross): train 94, val 47, test 96 gold
  queries (120 / 63 / 117 questions).

## 2. The generated virtual knowledge graph (P0)

* The ontology, the R2RML (one map per table, 152), and Ontop's `db-metadata.json` are
  generated from the DDL. Every class compiles and executes through Ontop.
* Superclass counts include their subclasses, so Ontop reasoning over the reconstructed
  hierarchy is verified: `ElementOfFinancialStatement` (443,794) ⊇ `Revenue` (42,474),
  and `AutonomousAgent` (52,424) = `Person` + `Corporation`.
* **Alignment to FIBO** (exact matches on the squashed label or local name):

  | | classes | properties |
  |---|---|---|
  | exact match to FIBO | 19 of 152 | 30 of 68 |
  | no match | 116 | 30 |
  | suggested, needs review | 17 | 8 |

  * The 116 unmatched classes are us-gaap disclosure types (from FRO), which FIBO doesn't
    model.
  * Fuzzy suggestions are mostly wrong ("revenue" → "revenue bond"), so they are never
    used automatically. This confirms the plan's design: mapping is a reviewed design-time
    step.

## 3. Compiler ceiling (P1): how much of FIBEN the VKG route can express

Each gold SQL query is translated to SPARQL by a deterministic translator (no LLM) and
accepted only if its Ontop-compiled SQL reproduces the gold rows exactly:

| query type | n | match (ceiling) | match on non-empty gold |
|---|---|---|---|
| non-nested | 106 | **101 (95%)** | 65/70 |
| type-a | 45 | **43 (96%)** | 25/27 |
| type-j | 27 | **27 (100%)** | 12/12 |
| type-ja | 31 | **28 (90%)** | 9/10 |
| type-n | 28 | **27 (96%)** | 22/22 |
| **all** | 237 | **226 (95%)** | 133/141 |

PLAN.md's P1 exit criterion was a ceiling of at least 60%; it is far exceeded. The
remaining 11 failures:
* 2 queries with derived tables in `FROM`;
* 2 cases of the compiler's finishing step not supporting `COALESCE`;
* 3 Ontop plans it can't express as one SQL statement;
* 4 result mismatches.

**By-product: the first public FIBO NL→SPARQL gold set that executes over a VKG**
(`artifacts/gold/gold_sparql.json`).

## 4. Knowledge pack

| | |
|---|---|
| mapped terms (answerable) | 220, of which 48 carry a FIBO definition |
| FIBO-known but unmapped terms (for explained refusals) | 4,079 |
| indexed values (names, tickers, codes, places) | 81,681 |
| curated glossary entries (K4) | 41 |
| allowed edges (with inheritance) | 222 |

## 5. H1 (offline part): grounding quality

Train split, 108 questions whose gold SPARQL is accepted. Every configuration gets the
same rule-extracted mentions, so the comparison isolates retrieval and re-ranking.

| configuration | candidate recall | tree recall | tree precision | terms shown |
|---|---|---|---|---|
| BM25, K1 (labels + definitions) | 0.473 | 0.382 | 0.535 | 15.6 |
| TF-IDF char n-grams, K1 | 0.496 | 0.388 | 0.466 | 18.5 |
| hybrid, K1 | 0.484 | 0.381 | 0.472 | 17.9 |
| hybrid, K2 (+ FIBO synonyms) | 0.481 | 0.373 | 0.468 | 17.9 |
| **hybrid, K4 (+ curated glossary)** | **0.641** | **0.465** | **0.592** | 17.3 |
| hybrid, K4, PPR instead of Steiner | 0.590 | 0.461 | 0.515 | 14.6 |
| hybrid, K4, top-5 candidates | 0.678 | 0.458 | 0.584 | 20.8 |
| whole ontology in context | 1.0 (by construction) | n/a | n/a | 220 |

Findings:
* **Curated knowledge is the lever, not the retriever.** Adding the glossary raises
  candidate recall by 16 points and tree precision by 12. Retriever choice changes recall
  by at most 2 points, and FIBO's own synonyms add nothing. This replicates, on FIBO, the
  literature's "context beats models" pattern
  ([state-of-the-art report](../../../knowledge/NL2Q/reports/NL2Query%20state%20of%20the%20art%202026.md)).
* **Steiner versus PPR.** Personalized PageRank matches Steiner on recall with lower
  precision, and is about 70× faster.
* **The mentions limit the absolute numbers.** Rule-extracted mentions cap absolute
  recall. LLM mention extraction (module M1) is the next lever and is measured in the live
  runs.

### 5.1 Semantic enrichment without the glossary (2026-10-26)

**The gap.** Only 48 of the 220 mapped terms had a definition:
* the 116 FRO / US GAAP classes have no FIBO counterpart;
* the 25 suggested FIBO matches were never reviewed;
* most properties match nothing in FIBO.

**What was built** (`nl2q/enrich.py`, `nl2q/usgaap.py`). Three switchable layers, with each definition's source recorded:

| layer | source | terms defined |
|---|---|---|
| review | `artifacts/knowledge/alignment_review.csv`: the 25 suggestions decided, plus one match found during review | 4 (2 exact, 2 close); 4 broad and 7 related add a synonym only; 11 rejected |
| usgaap | FASB US GAAP 2015 taxonomy: documentation and labels of the elements a class links to | 69 (6 by the elements its rows carry, 39 by name or name variant, 24 by disclosure text block) |
| derived | schema: what a property belongs to, its type, and its values for code columns | 95 |

**Result.** 216 of 220 mapped terms now have a definition, up from 48. The 4 left are root classes (`AutonomousAgent`, `Country`, `FinancialReport`, `ElementsOfFinancialReport`). Their FIBO counterparts now live in OMG Commons and LCC, which the local FIBO copy doesn't include.

**The review rejected 11 of the 25 suggestions as wrong senses**, for example `Revenue` → *revenue bond*, `Liability` → *liability capacity* and `NoncontrollingInterest` → *interest* (the cost of credit). Before the review they were display-only, so no wrong definitions had been imported. Every decision carries a rationale and is marked *proposed*: the `approved` column is for the data owner.

**H1 with enrichment** (train, 104 questions whose gold SPARQL passes the stricter ceiling of §7.1, so the baselines differ slightly from §5's 108):

| configuration | cand. recall | tree recall | tree precision |
|---|---|---|---|
| hybrid K1, no enrichment | 0.491 | 0.390 | 0.472 |
| hybrid K1 + review | 0.493 | 0.401 | 0.482 |
| hybrid K1 + review + US GAAP | 0.493 | 0.388 | 0.485 |
| hybrid K1 + all three layers | 0.497 | 0.388 | 0.486 |
| BM25 K1 → + all layers | 0.481 → 0.490 | 0.384 → 0.383 | 0.538 → 0.524 |
| TF-IDF K1 → + all layers | 0.505 → 0.508 | 0.401 → 0.396 | 0.474 → 0.484 |
| hybrid K4 (glossary) → + all layers | **0.651 → 0.624** | 0.466 → 0.455 | 0.583 → 0.572 |

Findings:
* **The missing definitions did not cap recall; the gap is vocabulary.** Enrichment adds at most 0.9 points of candidate recall, against the glossary's 16. Two reasons:
  * The 116 FRO classes hardly occur in FIBEN's questions: the terms enrichment newly defines are mostly properties (`hasTickerSymbol`, `refersTo`, `hasType`).
  * Most missed gold terms already had a FIBO definition: at least 344 of the 574 missed occurrences (`hasLegalName`, `hasAmount`, `isOwnedBy` ...). A question says "company name" or "bought"; a formal definition doesn't contain those words. That is what the glossary's business synonyms and codes supply.
* **Enrichment dilutes the glossary.** With K4, the extra definition and label text competes with the glossary phrases and costs 2.7 points. Enrichment is therefore **off by default** (`NL2Q_ENRICH=none`), so every arm keeps the pack its published results used.
* **Where the enrichment still pays:**
  * it removes the glossary's benchmark-leakage risk for definitions, since no layer reads gold or questions;
  * it gives the planner real definitions to read, which retrieval recall cannot measure and needs a live arm-S ablation (billed);
  * it improves refusal explanations and documentation;
  * it supplies SKOS mappings to FIBO and US GAAP (`artifacts/knowledge/enrichment.ttl`) for SIP.
* **The next lever stays the one §5 named:** LLM mention extraction (M1), plus synonym mining from sources that don't see the gold, e.g. US GAAP labels for the business words of financial questions.

## 6. Arm R: the no-LLM baseline (val, 63 questions)

| metric | value |
|---|---|
| execution accuracy | 0.079 (95% CI 0.016–0.143) |
| test-suite accuracy (4 perturbed instances) | 0.079 |
| accuracy on non-empty gold (36) | 0.056 |
| wrong but executed | **0.778** |
| refused / failed | 0.127 / 0.016 |
| penalty score (c = 1 / c = 5) | −0.70 / −3.81 (abstaining on everything scores 0) |
| refusal recall on the unanswerable set (24) | 0.042 |
| gold-term recall: candidates / final plan | 0.629 / 0.491 |
| latency P50 / P95 | 0.22 s / 3.4 s |

As intended, this is the floor: heuristic planning answers confidently and is mostly
wrong. It is also the worst case for the penalty score, which is the reason the score
exists. Every learned arm must beat it on accuracy *and* on wrong-but-executed.

## 7. Validating the metric

* **Perturbed instances discriminate.** Compared with the base data, the gold answer
  changes for 109 (V1 drop), 114 (V2 rewire), 43 (V3 fan-out) and 22 (V4 reclassify) of
  the 237 gold queries.
* **The ontology query check has no false positives.** On the 226 accepted gold SPARQL
  queries it flags none. It reports wrong directions, unknown terms, domain/range
  violations and cross products with repair-ready messages.
* **Mutation testing** (849 mutants of accepted gold SPARQL; 777 execute):

  | | detection rate |
  |---|---|
  | all executable mutants | 0.405 |
  | executable mutants, non-empty gold | 0.582 |
  | … excluding superclass mutants | 0.752 |
  | base database only, non-empty gold | 0.509 (the perturbed instances add +7 points) |
  | caught only by the perturbed instances | 43 mutants |

  **The detection rate is far below the plan's 95% target.** Two causes:
  1. On empty gold answers, almost every mutant also returns nothing (269 of the
     undetected mutants).
  2. Many mutants are *equivalent on this data*. Every Security in FIBEN is a
     ListedSecurity, so swapping a class for its superclass changes nothing; many filters
     are redundant given the others.

  **Consequence.** Execution accuracy on the public FIBEN instance, even with four
  variants, cannot separate right from subtly wrong queries well enough to support the
  go / no-go thresholds.

### 7.1 Strengthening: the witness instance (V5) and valid variants

* **Targeted instance synthesis** (`nl2q/witness.py`). From each gold query's structure,
  4,540 synthetic rows were generated:
  * witness chains satisfying every filter;
  * two chains per group with different measures, so aggregates disagree;
  * one near miss per filter;
  * superclass near misses;
  * correlated rows for nested queries.

  **78 of the 96 empty gold answers become non-empty** on V5.
* **The witness exposed invalid test instances.**
  * **The witness itself.** A superclass near miss that dropped a subclass row still
    referenced by a declared foreign key is invalid: Ontop trusts declared FKs and
    eliminates joins through them. Near misses now respect referential integrity.
  * **V1.** The same flaw existed in V1, whose dropped rows left dangling references. V1
    now drops rows only from unreferenced tables.
  * **V3 / V4.** "Disagreements" on them were query timeouts over views. They are now
    materialised.
* **Two translation errors in the gold SPARQL** (sql_id 31, 197) appeared only on the
  witness instance. Acceptance now requires agreement on the base data and all five
  variants: **ceiling 219 of 237 (92%)**.
* **Mutation testing after strengthening** (820 mutants, 750 execute):

  | | before | after |
  |---|---|---|
  | all executable mutants | 0.405 | **0.583** |
  | non-empty gold | 0.582 | **0.621** |
  | non-empty gold, excluding superclass swaps | 0.752 | **0.844** |
  | caught only by the variants | 43 | **170** |
  | undetected because gold is empty | 269 | **145** |

  Per operator after strengthening: dropped filter 80%, flipped comparison 89%, swapped
  aggregate 84%, shifted number 88% of executable. Superclass swaps are caught 9 of 218
  times. They are largely *equivalent on this data* (every Security is a ListedSecurity),
  and a valid superclass near miss is possible only where no FK references the subclass
  row. That is the remaining gap to the 95% target.

### 7.2 Repair of the witness instance (2026-10-27)

The evaluation specification's Gate 1 key-integrity check found V5 invalid. Its witness
rows broke 4 subclass foreign keys: 1,570 subclass rows had no parent row (e.g. 685
`ListedSecurity` rows without a `Security` row). Ontop trusts declared keys, so on V5 a
SPARQL query and the gold SQL could disagree because of the data.

`witness.Builder.close_parents` now adds the parent chain (2,255 rows). After the repair:
* **every instance** (Base, V1–V6) has zero dangling keys and zero SHACL violations;
* the **compiler ceiling** is unchanged (219/237);
* **mutation detection** moved from 58.3% to 58.5% of executable mutants;
* the **live check** moved by 1.6–4.8 points for R, S and S2 (§9).

The new taxonomic counterfactual instance V6 (`nl2q/evalkit/v6.py`) showed that **199 of
the 218 superclass mutants are equivalent under the declared keys**: the swapped variable
is reached through a key that targets the subclass (`HOLDING.REFERSTO -> LISTEDSECURITY`),
so no valid instance can separate the two queries. The 9/218 above measured the schema,
not the metric.

### 7.3 Gate 2 and the new datasets (2026-10-27)

Evaluation-framework stages S4 and S6 (`docs/nl2q_evaluation_specification.md` §8) cost $0.

**Gate 2** (`python -m nl2q.evalkit.gate2 --split val`, `artifacts/eval/gate2/gate2_val.md`) scores the v1 grounding components against oracles extracted from the gold SPARQL. Val has 56 answerable questions and 30 unanswerable.

* **Retrieval.** Recall@20 of the gold terms is 31% with no glossary, 38% with `Gtrain` (induced from train only) and 64% with the v1 glossary. Gv1 was written after reading all gold. The 25-point gap between the two glossaries is the size of the contamination risk §5 flagged.
* **Value linking.** F1 is 0.65 on the properties the value index covers. Codes such as `hasType = "1"` are not linked at all.
* **Grounding.** The best re-ranked tree covers every gold term for only 25–30% of questions. Equivalence-aware matching adds nothing on val.
* **Refusal (v1 rule gate).** Recall is 100% on U1, 40% on U2 and 20–70% on U3, with 23% false refusals. Precision at 20% prevalence is 43%, against a target of 90%.

**New datasets:**
* **U1–U3** (`nl2q/evalkit/unanswerable.py`): 150 questions labelled by construction.
* **FIBEN-Obfuscated** (`obfuscate.py`): opaque names over views. The gold gives identical answers on all 7 instances, apart from ties under `LIMIT`. The renamed mapping passes M01–M12.
* **`Gtrain`** (`gtrain.py`).
* **L1.5 hierarchy views** (`l15.py`): verified on all 7 instances.

## 8. ACME insurance on the same stack (literature comparability, P4)

* 29 tables loaded; the data.world R2RML adapted for Ontop (table names, `sqlQuery` as
  views, the DDL's types so the ontology's datatypes match).
* Gold SQL: **44 of 44** execute.
* Gold SPARQL through Ontop: **26 of 44** compile and run. **All 26 agree exactly with
  the gold SQL.**
* The other 18 are Ontop or compiler limits: 13 cannot be pushed into one SQL statement,
  4 hit the `COALESCE` finishing gap, 1 is an Ontop error.

## 9. Small live check (Sonnet 5.5, val, one run per arm)

Re-scored offline (`nl2q/rescore.py`) on the base data and all five variants. **Updated
2026-10-27** after the V5 repair (§7.2): R, S and S2 changed by 1.6–4.8 points; the other
arms are unchanged.
* **Relaxed** means the answer may omit the gold query's extra context columns; FIBEN's gold
  SQL projects names and tickers a direct answer leaves out.
* **Suite** means correct on the base data and every variant.

| Arm | n | strict EX (base) | relaxed EX (base) | **suite, relaxed** | **wrong-but-executed (suite)** | refused | $/question |
|---|---|---|---|---|---|---|---|
| R: rules, no LLM | 63 | 0.079 | 0.254 | 0.079 | 0.714 | 0.127 | 0 |
| **S: grounding + plan + checks** | 63 | 0.159 | 0.476 | **0.270** | **0.444** | 0.286 | 0.018 |
| S2: S + link neighbourhood + glossary fix | 63 | 0.190 | 0.571 | 0.222 | 0.619 | 0.159 | 0.020 |
| A: direct SPARQL | 63 | 0.222 | 0.492 | 0.190 | 0.635 | 0 (0.175 failed) | 0.012 |
| B: A + OBQC + repair | 63 | 0.222 | 0.619 | 0.206 | 0.794 | 0 | 0.015 |
| T: text-to-SQL over the DDL | 59 † | 0.220 | 0.593 | 0.288 | 0.712 | 0 | 0.085 |
| G: tool agent (schema browse + SQL) | 57 † | 0.088 | 0.123 | 0.088 | 0.088 | 0.737 ‡ | 0.134 |

† Stopped at the per-arm budget cap. ‡ For G, "refused" means the agent returned no SQL
(it ran out of steps); that is not a principled refusal.

Unanswerable set (24 questions the mapping cannot answer):

| Arm | refused |
|---|---|
| S | **24 / 24** |
| S2 | 23 / 24 |
| B | 1 / 24 |
| A | 0 / 24 |
| T, G | not run (budget) |

Findings:
* **No accuracy winner at n = 63.** Re-analysed under the evaluation specification
  (`artifacts/eval/campaigns/fiben_v1_val.scorecard.md`: gold-query cluster bootstrap,
  McNemar on paired outcomes, Holm correction), no arm differs from T on suite accuracy
  except R and G (both worse). The minimum detectable differences are 11–29 points.
* **Safety is the measurable difference.** S has the lowest confidently-wrong rate of all
  arms that answer (44% vs 62–79%), and the only principled refusals. Against T the gap is
  −27 points (95% CI −41 to −13, Holm p = 0.001), but part of it comes from S refusing 29%
  of answerable questions.
* **More context made S answer more, not better.** S2's change (all links touching the
  involved classes) cut refusals by 13 points and raised wrong answers by 18. The
  recall-over-pruning recommendation does not hold here as stated: unless the planner can
  tell a missing link from an unmapped concept, it trades refusals for errors.
* **The base-data score is misleading.** Relaxed base EX (48–62%) more than halves under
  the suite, because many base-data "matches" are empty-versus-empty coincidences. Without
  the witness instance, the live check would have overstated every arm.
* **Cost.** Ontology-scoped context costs $0.012–0.020 per question. Passing the full
  152-table DDL costs $0.085 (no prompt caching through DSPy). The agent costs $0.134.
* **The tool agent issued runaway queries.** DuckDB did not honour interrupts, so
  model-written SQL now runs in a killable worker process (`nl2q/sqlworker.py`), and
  results are written after every question.

## 10. Further live runs (not run): what remains and what it costs

| Run | Calls | Rough cost (Sonnet 5.5) |
|---|---|---|
| Spike: DSPy + LiteLLM + current Claude API constraints | ~5 | < US$0.10 |
| Arms S, A, B, T, G on val (63 + 24 unanswerable) × 3 runs | ~3–4k | US$75–110 |
| GEPA, light budget (train/val) | ~1–2k metric calls | US$30–60 + reflection model |
| Knowledge ablation K1/K4 and mention ablation for arm S on val | ~1k | US$15–25 |
| Final: frozen release candidate + baselines on test (117 + 12), 3 runs | ~2–3k | US$40–60 |

These are estimates. Actual costs are recorded per question (`cost_usd`) and summed in
every run summary.

## 11. Defects found along the way

* **FIBEN gold:** two malformed queries (§1); a data instance that doesn't match its
  questions.
* **SPARQL-2-SQL PoC compiler:**
  * a projected timestamp transpiles to `JSONB_EXTRACT_SCALAR`, which DuckDB lacks
    (worked around in `nl2q/vkg.py`);
  * `COALESCE` terms are not supported by the finishing step (2 FIBEN and 4 ACME gold
    queries).
* **Ontop (offline mode):** it can't build black-box views for mapping SQL it doesn't
  parse (worked around by turning such SQL into database views); some plans cannot be
  pushed into one SQL statement.
* **DuckDB:** interrupting a query is not immediate. A 17-billion-row cross product
  outlived its 30 s timeout. Prevented upstream by the cross-product check.
