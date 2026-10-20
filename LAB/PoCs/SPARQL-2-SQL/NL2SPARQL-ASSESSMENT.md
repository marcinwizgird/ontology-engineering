# NL → SPARQL layer for the FIBO VKG PoC: critical assessment and design

Input: `knowledge/NL2Q/Ontology-Based NL2Q Deep Research.pdf` (the "deep research").
Goal: decide whether a natural-language layer on top of this PoC is feasible, and if so,
specify one that is scientifically grounded, pragmatic and **measurable**, with
evaluation sets that can drive optimisation.

Sources were checked on 2026-10-17. Where a claim could not be traced to its primary
source it is marked as such; nothing below relies on an unverified number.

**Verdict: feasible, and the PoC is an unusually good base for it.** The VKG (Ontop) and
the SPARQL-to-SQL compiler already remove the hardest relational decisions (joins, subclass
expansion, dialects), and the PoC already has the key evaluation ingredient: a way to turn
any gold SPARQL query into gold rows (compile → execute → compare with the oracle). What is
missing is (a) the NL front end and (b) a much stronger evaluation substrate: the demo
database is too small to discriminate right from wrong queries. The deep research's
direction is right (ontology + VKG + validation), but several of its numbers are
misattributed or overstated, and its single "mandatory" technique (grammar-constrained
decoding) is not available on hosted frontier models. Section 3 replaces it with
something that is.

---

## 1. What the deep research gets right, and what it gets wrong

### 1.1 Claims audit

| # | Claim in the deep research | Primary source | Verdict |
|---|---|---|---|
| 1 | GPT-4 text-to-SQL 16.7% → 54.2% with an ontology/KG (insurance) | Sequeda, Allemang, Jacob 2023 (arXiv 2311.07509); figures restated in Allemang & Sequeda 2024 (arXiv 2405.11706) | **Confirmed.** It omits the follow-up result that matters most for design: ontology-based query checking + LLM repair raised accuracy to **72.55%** with 8% "I don't know" and a 19.4% error rate (2405.11706, Table 1). |
| 2 | Removing domain/range/comments drops SPARQL accuracy by up to 19 pp, SQL by 14 pp | Fitch & Kurtz 2026 (arXiv 2607.18029) | **Partly verified.** The abstract confirms that readable names and annotations mattered more than model or prompt choice (MRI-archive metadata, one domain). The exact pp figures were not checked. |
| 3 | Fine-tuned Llama: 60.68% Macro-F1 on DBpedia vs 13.36% on Wikidata | cited as arXiv 2609.11569 (EXYGEN) | **Not found in the cited source.** EXYGEN reports SciQA execution exact-match 0.419. The direction (opaque IDs hurt) is well established; the numbers are untraceable. |
| 4 | Semantic layer + GPT-5.3-Codex ≈ 100% | dbt Labs, "Semantic Layer vs. Text-to-SQL: 2026 Benchmark Update" | **Confirmed but selectively reported.** The same study measured *text-to-SQL* at 90.0% (Claude Sonnet 4.6) and 84.1% (GPT-5.3-Codex) on 11 questions, after adding 3 models. On the minimally modelled configuration it was 72.7% vs 64.5%. **The gap narrows sharply with frontier models.** |
| 5 | Comparison table: ontology/KG "High (~85–95%)" | none that supports it | **Overstated.** The best published ontology-based figure on the same benchmark lineage is 72.55% (OBQC + repair). Only bounded-planning systems with deterministic compilation report >95% (SPC 2026, see 1.2). |
| 6 | Spider4SPARQL shows the value of ontological context | Kosten, Cudré-Mauroux, Stockinger 2023 | **Misread.** Spider4SPARQL found LLMs reached **at most ~45% execution accuracy** on SPARQL. That is evidence that SPARQL generation is *hard*, not that it is easier than SQL. |
| 7 | SPARQL-LLM: "+59% accuracy over purely relational approaches" | arXiv 2610.13648 / 2512.14277 | **Misattributed.** The 59% is the F1 margin over the **second-best Text2SPARQL system**, not over relational approaches. The method itself (retrieved examples + VoID/ShEx schema context + validation) is directly reusable. |
| 8 | Adaptive metadata pruning doubled the execution rate in a power grid domain, 40.2% → 84.6% | SQL-GRID (EAI Energy Web, 2026) | **Misattributed.** The figures are real, but they come from a retrieval + validation + **interactive disambiguation** text-to-SQL agent, not from schema pruning. |
| 9 | Grammar-constrained decoding gives 100% syntactic validity, "mathematically guaranteed at the hardware level"; a 7B model's execution accuracy doubles (BIM) | Smirnov et al., EC3 2026 | **Partly verified, framing wrong.** The abstract confirms 100% schema compliance and *improved* execution accuracy for small open models. "Doubles" was not verified. Syntactic validity does not imply semantic correctness, and the Claude API offers no grammar-constrained decoding (§1.3). |
| 10 | CypherBench: Claude 3.5 Sonnet ≈ 61.58% | Feng et al. 2024 (arXiv 2412.18702) | Consistent with the paper; not relevant to the SPARQL path. |
| 11 | "If Manager ⊑ Employee, the LLM instinctively understands that employees include managers" | n/a | **Conceptually wrong for a VKG.** The *reasoner* does this: Ontop's T-mappings expand the class hierarchy (PoC Q2). The LLM should be told **not** to enumerate subclasses, because hand-expanded UNIONs are a source of errors. |

Further weaknesses:
* Many references are vendor blogs or aggregators (Medium, Atlan, Timbr, colrows,
  cloudsoftsol, Scribd).
* Accuracy figures from incompatible metrics (Macro-F1, execution accuracy, exact match)
  are compared in one table.
* There is no evaluation methodology at all.

### 1.2 What the deep research misses, and the design needs

| Gap | Why it matters here | Source |
|---|---|---|
| **ATHENA / ATHENA++ and the FIBEN benchmark** | An ontology-mediated NLIDB on a **FIBO + FRO** ontology, the same domain this PoC slices from. FIBEN: 300 NL questions, 237 gold SQL queries, 152 tables; 130 non-nested and 170 nested (N/A/J/JA). ATHENA++ reports 88.33%. Apache-2.0, includes data (80 MB). The gold queries touch only **24 tables**. | Sen et al., VLDB 2020; github.com/IBM/fiben-benchmark |
| **Ontology-based query check (OBQC) + repair** | Eight deterministic rules (domain, range, double-domain, double-range, domain-range, unknown property, IRI output, subject output). A failing query is repaired by the LLM, up to 3 times, else "I don't know". It gave the largest gain on high-schema-complexity questions (17.2% → 76.3%). The PoC ontology already declares `rdfs:domain`/`rdfs:range` for every property, so this costs almost nothing. | Allemang & Sequeda 2024 |
| **Bounded semantic planning + deterministic compilation (SPC)** | The LLM may only ground phrases and choose from finite, question-specific option sets. Paths, roles, grain and SQL are built by code. On ACME: 97.4% solid success vs 55.3% for DDL-to-SQL; exact McNemar p = 3.05·10⁻⁵; **zero wrong-but-executed runs** in 114. The authors are honest that semantic knowledge is not held constant between arms. This is the strongest current evidence for *where* to put the LLM boundary. | Yi Ai 2026, arXiv 2608.16663 |
| **Test-suite / counterfactual accuracy** | Execution accuracy on one database accepts wrong queries that happen to return the same rows. Evaluate on several database instances built to separate right from wrong. | Zhong et al. 2020; SPC §5 |
| **Abstention as an outcome** | Separate "answered correctly", "refused" and "**wrong but executed**". The last is the costly failure; score it accordingly. | TrustSQL 2024; Allemang & Sequeda 2024 |
| **Fan traps / aggregation grain** | SPARQL has bag semantics: a `SUM` across a 1:n join silently multiplies, exactly as in SQL. Ontop does not protect against this; PoC Q4-style questions are exposed to it. | SPC §2.3, §4.7 |
| **Value (literal) grounding** | "NYSE", "Apple", "retail clients": wrong literals give an *empty* or wrong answer that is still syntactically perfect. Value retrieval is a standard component of strong text-to-SQL systems. | CHESS 2024; SPARQL-LLM |
| **Public ACME insurance benchmark** | Ontology, R2RML, data and gold SQL/SPARQL for the 16.7 / 54.2 / 72.55 / 97.4% results. Apache-2.0. Lets this PoC report numbers **directly comparable with the literature**. | github.com/datadotworld/cwd-benchmark-data |

### 1.3 Feasibility of each recommendation

| Deep-research recommendation | Assessment for this PoC |
|---|---|
| 1. Move away from raw text-to-SQL | **Agree, for a different reason.** With 2026 frontier models the raw accuracy gap on small schemas is ~8–16 pp (dbt 2026), not 40 pp. The durable advantages are governance: answers stay inside the mapped, governed vocabulary; unmapped data is unanswerable by construction; refusals are explainable; and the SQL is deterministic and auditable. Measure this rather than assume it (§4, baseline arm T). |
| 2. VKG as integration bridge | **Done.** This is what the PoC proved (offline Ontop sidecar, four dialects, oracle-checked). |
| 3. Mandatory grammar-constrained decoding | **Not feasible as stated** with hosted Claude models: the API offers JSON-schema structured outputs and strict tool use (`enum`, `anyOf`, `$ref`; **no recursion, no custom grammars**). GCD is only available with self-hosted open-weight models (vLLM/Outlines). **Replace it with:** (a) a non-recursive JSON intermediate representation whose ontology terms are `enum`-constrained, which gives the same vocabulary guarantee at the semantic level, plus (b) a post-hoc parser and OBQC. With frontier models, syntax is not the bottleneck; semantic errors are. |
| 4. Multi-agent verification | **Adopt the verification, not the agent count.** Deterministic checks (parse, vocabulary, OBQC, compile, result sanity) plus at most 2–3 bounded repair turns. An LLM "critic" of results is weakly evidenced and costly; keep it as an optional, measured arm. |
| 5. Schema pruning (VoID/SHACL) | **Unnecessary at PoC scale.** 13 classes and 30 properties fit in about 2–3 k tokens, and the context is cacheable. It becomes necessary on full FIBO (thousands of classes). Build it as a measured ablation when the ontology grows. |
| 6. Iterative tools (MCP-style) instead of one-shot generation | **Agree, in SPC's bounded form**: tools return finite, typed choice sets (classes, properties, routes, values) and the model selects among them. |

---

## 2. What the PoC gives us, and what limits it

Assets:
* `/v1/compile`: SPARQL → SQL, offline, 4–6 ms. A 422 for unsupported constructs is a free
  "compile rate" signal.
* `tests/oracle.py`: R2RML materialisation + subclass reasoning + rdflib, an independent
  answer check.
* Ontop expands class hierarchies, so the LLM never has to.
* Every property has `rdfs:domain` and `rdfs:range`, so OBQC applies directly.

Limits that matter for an NL layer:
1. **The database is too small to discriminate.** It has 8 companies, 13 securities,
   4 customers and 9 holdings. Many wrong queries return the right rows, or empty results
   on both sides. Evaluation needs a larger seeded instance and **K perturbed instances**
   (§4.3).
2. **The ontology has no `rdfs:label` and no `rdfs:comment`.** These annotations are the
   cheapest proven lever (claims 2 and 1.2). Add them, and measure their effect as an
   ablation.
3. **Some data is deliberately unmapped.** The DDL has columns with no mapping:
   * `MATURITY_DATE`, `SHARES_OUTSTANDING`, `TOTAL_ASSETS_USD`, `FISCAL_PERIOD`
   * `ACC_STATUS`, `CURRENCY`, `TRADE_DATE`, `LIMIT_PRICE`, `VALUATION_DATE`
   * `COUNTRY_INC`, `EXCH_NAME`, `SEC_TYPE`, `TAX_ID`

   This is a feature for evaluation: questions about them are **gold "cannot answer"**
   cases. A raw text-to-SQL baseline *would* answer them, which shows what the governed
   path buys.
4. **The rdflib oracle is wrong for correlated subqueries** (`tools/coverage.md`). For
   gold answers, use the compiled SQL on DuckDB, cross-checked by the oracle where the
   query class is known to be safe.
5. **Construct coverage.** Anything outside the compiler's finishing set returns 422. The
   NL layer must stay inside the supported SPARQL subset: the renderer in §3 guarantees
   that for arm C.

---

## 3. Design: the NL2SPARQL layer

### 3.1 Placement

```
                 llm-net (egress to the LLM API only)          compile-net (internal, no DB, no egress)
user question ─► nl2sparql-service ─────────────────────────► sparql2sql-service ─► ontop-sidecar
                 │  context builder (build-time artefacts)      (unchanged)
                 │  planner (LLM or offline simulator)
                 │  renderer + validators (deterministic)
                 └─► demo plane: execute SQL on DuckDB, return rows + provenance
```

* The compilation plane stays exactly as verified (DoD 1).
* The new service is the only component with model access.
* Like the rest of the repo, it is **offline by default**: a deterministic simulator
  planner for tests, and the live model as opt-in (`NL2Q_MODEL=...`).

### 3.2 Build-time artefacts (deterministic, versioned)

1. **Ontology card.** Generated from `fibo-subset.ttl` + the R2RML.
   * It lists only what is **mapped**, so unmapped terms can't be asked for.
   * For each class: label, comment, superclasses.
   * For each property: label, comment, domain → range, datatype.
   * It includes a rule: "never expand subclasses; the reasoner does".
   * Turtle and a verbalised form are both kept, so the format can be ablated.
2. **Route table.** All paths of up to *h* hops (h = 3) between mapped classes in the
   domain/range graph, with canonical IDs. These are SPC's path handles.
3. **Value index.** Distinct values of low-cardinality and name-like literal columns
   (exchange symbols, tickers, legal names, customer types, order types), keyed by
   property. Fuzzy and alias matching ("Apple" → "Apple Inc.").
   * It is built from the sandbox database at build time, like `db-metadata.json`, so the
     compile plane stays database-free.
   * It exposes data values to the model. That is a governance decision, recorded in the
     design.
4. **Example pool.** (NL, SPARQL) pairs from the **dev** split only, for retrieval of
   few-shot examples by similarity.

### 3.3 Arms (each one is an evaluated configuration, not a commitment)

| Arm | Planner output | Checks | Literature anchor |
|---|---|---|---|
| **T** (baseline) | Raw SQL from the DDL (text-to-SQL) | parse | Sequeda 2023 SQL arm; dbt 2026 |
| **A** | SPARQL text from the ontology card + retrieved examples | parse, compile | Sequeda 2023 KG arm; SPARQL-LLM |
| **B** | A + OBQC (8 rules) + repair ≤ 3 + "cannot answer" | parse, OBQC, compile | Allemang & Sequeda 2024 |
| **C** | **Structured IR** via strict tool use / JSON schema, terms `enum`-constrained, routes and values chosen from the build-time tables; **deterministic renderer** IR → SPARQL; one retry carrying only the refusal reason | schema, review, render, compile | SPC 2026 (bounded planning) |

The IR for arm C is non-recursive, because the API cannot constrain recursive schemas:

```json
{
  "answerable": true,
  "focus": "fibo-sec-eq-eq:ListedShare",
  "routes": ["ListedShare>Exchange#1", "ListedShare>Corporation#1"],
  "project": [{"node": "ListedShare", "property": "ex-fibo:tickerSymbol"},
              {"node": "Corporation", "property": "ex-fibo:legalName"}],
  "filters": [{"node": "Exchange", "property": "ex-fibo:exchangeSymbol",
               "op": "=", "value_id": "v:exchangeSymbol:NYSE"}],
  "aggregate": null, "group_by": [], "order_by": [{"var": "tickerSymbol", "dir": "asc"}],
  "limit": null, "negate_routes": []
}
```

* The renderer emits only constructs the compiler supports, so arm C cannot produce a
  422 by construction.
* The renderer owns aggregation grain: a `SUM` across a fanning route is either rewritten
  as a sub-select at the measure's grain or refused (SPC §4.7). This closes the fan-trap
  gap that arms A and B leave open.
* Questions the IR cannot express (for example, nested comparisons against a per-group
  aggregate) produce `answerable: false, reason: "unsupported"`. They count as refusals,
  not as errors.

### 3.4 Response contract

The service returns:
* the rows;
* the SPARQL query and the SQL query;
* the ontology terms used, with labels;
* the checks passed, and any refusal reason.

For arm C it also returns the IR. That gives an auditable explanation without asking a
model to explain itself.

---

## 4. Evaluation: what to measure, on what, and how

### 4.1 Datasets

| Set | Built how | Size | Purpose |
|---|---|---|---|
| **E0 PoC-FIBO** (own) | SPARQL-first (details below) | 300–500 questions | Fast optimisation loop on the PoC schema |
| **E1 ACME** (external) | data.world benchmark: ontology, R2RML, data and gold queries loaded into the same Ontop pipeline | 43 questions (+ SPC's adjudicated 38) | **Comparability** with the published 16.7 / 54.2 / 72.55 / 97.4% results |
| **E2 FIBEN-VKG** (external) | Real FIBEN schema (class-per-table, columns named after properties); generate ontology + R2RML for the 24 tables the gold queries use (near-mechanical); load the CSVs into DuckDB; transpile gold SQL Db2 → DuckDB with sqlglot | 300 questions (237 unique SQL) | External validity on FIBO; nested-query stress; comparison with ATHENA++ 88.33% |

How E0 is built, SPARQL-first:
1. Enumerate query templates over the route table. The template features are:
   * hops 1–3;
   * filter on a literal or numeric value;
   * subclass reasoning;
   * OPTIONAL, NOT EXISTS / MINUS;
   * COUNT, SUM or AVG + GROUP BY;
   * ORDER BY / LIMIT.
2. Fill the templates with literals from the value index.
3. **Gold rows** = compile + execute + oracle cross-check.
4. Verbalise each query into NL with an LLM, with 2–3 paraphrases each.
5. Have a human review a stratified sample (≥ 20%), with the defect rate reported.
6. Add **gold "cannot answer" questions** about the unmapped columns (§2.3) and out-of-domain
   ones. They make up about 15% of the set.

Generated questions are more regular than real ones. That is why E1/E2 (human-written)
are the headline sets and E0 is the optimisation set.

Splits: E0 is split dev / test 50/50, stratified by feature tag. The example pool, prompt
tuning and model selection use **dev only**. E1 and E2 are test-only (no tuning), and are
reported once per frozen configuration.

### 4.2 Metrics

* **Primary.**
  * **Execution accuracy (EX)**: multiset equality of result rows; order-sensitive only
    when the question asks for an order; column order ignored; numeric tolerance on
    decimals.
  * **Test-suite EX**: correct on *all* K database instances (§4.3).
* **Safety.**
  * **Wrong-but-executed rate.** The headline risk metric.
  * **Abstention**: precision and recall on the gold "cannot answer" set.
  * **Selective accuracy**: EX on the questions the system did answer.
  * A TrustSQL-style penalty score (wrong = −c, refuse = 0, right = +1), reported for
    c ∈ {1, 5}.
* **Pipeline diagnostics.** Parse validity, vocabulary validity, OBQC pass on the first
  attempt, compile rate (non-422), repair success, and errors by type:
  * entity (value) linking;
  * property choice;
  * direction;
  * missing filter;
  * grain / fan trap;
  * aggregation;
  * unsupported construct.
* **Robustness.**
  * Paraphrase consistency (same answer across paraphrases).
  * **Solid success**: k/k correct over repeated runs (k = 3).
* **Cost.** Tokens, USD per question, and P50/P95 latency per arm.
* **Secondary, for comparability.** Answer-set F1, as used by QALD/Text2SPARQL (E1
  only), which makes the numbers comparable with the challenge literature.

### 4.3 Making EX discriminative

* **A larger seed.** Grow the database generator to about 200 companies and 1–2 k
  securities, holdings and reports. Include every edge case: securities with no exchange,
  customers with several accounts, companies with no reports, ties in ORDER BY, NULLs in
  optional attributes.
* **K = 5 perturbed instances.** For example:
  * shuffle the foreign keys;
  * duplicate a 1:n edge to expose fan traps;
  * flip which subclass a row belongs to;
  * move literals across tables;
  * add homonyms such as "Apple Hospitality".

  Gold rows are recomputed per instance by compiling and executing the gold SPARQL. This
  is Zhong et al.'s test-suite idea, and SPC's counterfactual instances.
* **Validate the metric itself (mutation testing).** Apply known-wrong edits to the gold
  queries: drop a filter, reverse a property, replace a class with its superclass, add a
  fanning join before SUM. Report the share of mutants that test-suite EX catches. The
  target is ≥ 95%. This check needs no LLM and can be done first.

### 4.4 Statistics

* Compare arms **paired** on the same questions, using exact McNemar on solid success.
* Report bootstrap 95% confidence intervals for EX and for the wrong-but-executed rate.
* With about 200 test questions, paired differences of about 10 pp are detectable.
  Smaller differences need more questions or more runs.
* Report per feature stratum, so a gain on simple lookups cannot hide a loss on
  aggregations.

### 4.5 Optimisation loop (dev split only)

Knobs to vary:
* the model tier and effort level;
* the ontology-card format (Turtle vs verbalised; with or without labels and comments);
* the number of few-shot examples (0 / 3 / 8) and how they are retrieved;
* value-index matching thresholds;
* the repair budget (0 / 1 / 3);
* the IR expressiveness (which constructs the renderer supports).

Change one knob per round. Record each round. Re-score the test split only to confirm a
frozen configuration.

### 4.6 Cost envelope (estimate, to be measured)

* **Per question.** About 3 k cached context tokens + about 0.5–2 k output tokens with
  thinking. That is roughly 1–3 US cents on Sonnet 5.5 and about 2× that on Opus 5.5. It
  is a fraction of a cent on Haiku 5.5.
* **A full E0-test sweep.** About 250 questions × 4 arms × 3 runs is 3 000 calls. That is
  on the order of US$50–150 per model tier, and the Batch API halves it.
* **Verbalising E0.** A one-off of a few dollars.

Every live run needs explicit approval first (`ANTHROPIC_API_KEY` is set in this
environment).

---

## 5. Plan

| Phase | Work | LLM? | Exit criterion |
|---|---|---|---|
| **P0** | Add labels and comments to the ontology. Grow the seed and build K perturbed instances. Build the route table and the value index. Implement the OBQC checker and the IR → SPARQL renderer. Write the E0 template generator, with gold via compile + execute. Build the metrics harness and the mutation test of the metric. Write a simulator planner (replays the gold IR) to test the pipeline end to end. | **No** | Mutant detection ≥ 95%. The renderer round-trips 100% of the E0 gold IRs. The pipeline passes with the simulator. |
| **P1** | Verbalise E0 (one batch) and review it by hand. Run arms T, A and B on E0-dev. | Yes (approval) | A baseline table with confidence intervals. |
| **P2** | Arm C, then the ablations of §4.5 on dev; freeze; score E0-test. | Yes | C ≥ B on test-suite EX, with wrong-but-executed ≤ 2% (target, to be revised after P1). |
| **P3** | E1 ACME (small, comparable with the literature), then E2 FIBEN-VKG (larger: R2RML for 24 tables, 80 MB of data, nested queries). | Yes | Results reported against the published numbers. |

**Kill / rethink signals:**
* If after P2 the best arm has wrong-but-executed > 5% on E0-test, or test-suite EX
  < 70%, stop and fix the IR, the value grounding or the ontology before going external.
* If arm T comes within 3 pp of the best arm *and* matches its abstention, the ontology
  layer's value is governance only, and the write-up should say so.

---

## 6. Risks and open questions

* **Circularity in E0.** The gold queries come from templates the IR can express, so E0
  flatters arm C. E1 and E2 exist to correct for that; read headline claims from them.
* **Developer leakage.** SPC notes that its compiler was built while inspecting the
  benchmark. Freeze the design before touching E1/E2 test questions.
* **Generated NL is too clean.** Measure the E0 → E1/E2 drop explicitly.
* **The value index exposes data to the model.** Restrict it to non-sensitive columns
  (names, symbols, types); customer names are a policy decision.
* **FIBEN gold SQL is Db2-flavoured, and some questions are nested types (A, JA).** SPARQL
  1.1 subqueries plus Ontop may not unfold all of them; report the compiler ceiling (the
  share of gold queries expressible as compilable SPARQL) separately from NL accuracy.
* **Model drift.** Pin model IDs and record them with every result.

---

## Sources

* Sequeda, Allemang, Jacob (2023). *A Benchmark to Understand the Role of Knowledge Graphs on LLM Accuracy for QA on Enterprise SQL Databases.* https://arxiv.org/abs/2311.07509
* Allemang, Sequeda (2024). *Increasing the LLM Accuracy for Question Answering: Ontologies to the Rescue!* https://arxiv.org/html/2405.11706v1
* Yi Ai (2026). *Bounded Semantic Planning and Deterministic Compilation for Reliable Enterprise Text-to-SQL.* https://arxiv.org/pdf/2608.16663
* dbt Labs (2026). *Semantic Layer vs. Text-to-SQL: 2026 Benchmark Update.* https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026
* Kosten, Cudré-Mauroux, Stockinger (2023). *Spider4SPARQL.* https://arxiv.org/abs/2309.16248
* Smeros et al. (2026). *SPARQL-LLM in the TEXT2SPARQL 2026 Challenge.* https://papers.cool/arxiv/2610.13648 ; *SPARQL-LLM: Real-Time SPARQL Query Generation.* https://arxiv.org/abs/2512.14277
* Singh et al. (2026). *EXYGEN.* https://arxiv.org/pdf/2609.11569
* Fitch, Kurtz (2026). *Natural Language Access to Domain-Specific Metadata.* https://arxiv.org/abs/2607.18029
* SQL-GRID (2026). https://publications.eai.eu/index.php/ew/article/view/14071
* Smirnov et al. (2026). *IDS-Constrained Text-To-Graph Querying for IFC Models.* https://ec-3.org/publication/ec32026_306/
* Sen et al. (2020). *ATHENA++.* https://www.vldb.org/pvldb/vol13/p2747-sen.pdf ; FIBEN: https://github.com/IBM/fiben-benchmark
* data.world ACME insurance benchmark: https://github.com/datadotworld/cwd-benchmark-data
* Text2SPARQL challenge: https://text2sparql.aksw.org ; proceedings https://ceur-ws.org/Vol-4094/
* Zhong, Yu, Klein (2020). *Semantic Evaluation for Text-to-SQL with Distilled Test Suites.* EMNLP 2020.
