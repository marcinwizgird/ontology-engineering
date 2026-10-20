# Evaluation methodology for NL-to-query systems (Text-to-SQL / Text-to-SPARQL / Text-to-Cypher), as of October 2026

Scope note: researched on 2026-10-19 with about 25 searches and fetches. Most quantitative claims come from arXiv abstracts or HTML pages. Where only a search snippet or a secondary aggregator was available, the claim is flagged **(weak)**. Dates are arXiv submission or venue dates.

## 1. Metrics: exact match, execution accuracy, test-suite accuracy, VES, answer-set F1, LLM-as-judge, formal equivalence checkers, and agreement with humans

### Takeaway
No single metric is sound on its own. Exact or set match produces false negatives. Single-database execution accuracy (EX) produces both false positives and false negatives. Test suites and synthesised databases reduce false positives but cost compute. LLM judges agree with experts much better than EX does (Cohen's kappa about 0.87 for FLEX vs about 0.62 for EX), but they are probabilistic. Formal equivalence checkers are sound but support only a small fraction of real query pairs. For SPARQL the community standard is answer-set F1 (QALD/Text2SPARQL). Text2Cypher evaluation is the least mature: it still relies on BLEU plus stringified exact match.

### Cited Findings
**Exact match vs execution vs test-suite**
- Zhong, Yu & Klein (EMNLP 2020) define *test-suite accuracy*. They distil a small set of databases with high code coverage of the gold query from many randomly generated databases, then compare denotations on all of them. This gives an "upper bound on semantic accuracy". — [ACL Anthology 2020.emnlp-main.29](https://aclanthology.org/2020.emnlp-main.29); [ar5iv HTML](https://ar5iv.labs.arxiv.org/html/2010.02840)
- In the same paper, Spider's official exact-set-match metric has a 2.5% false-negative rate on average and 8.1% in the worst case across 21 Spider leaderboard models. Test-suite accuracy was correct on all 100 manually checked examples. Distilled suites for 11 datasets are released (tooling: `taoyds/test-suite-sql-eval`). — [ar5iv 2010.02840](https://ar5iv.labs.arxiv.org/html/2010.02840)
- Critique from ETM (2024): test-suite matching reduces EX false positives but "is not scalable and suffers from long execution times". ETM also reports high false-positive and false-negative rates for both EX and exact set match. — [arXiv 2407.07313](https://arxiv.org/html/2407.07313v3)
- Renggli, Ilyas & Rekatsinas (Jan 2025) argue that using different match functions as approximations of SQL equivalence introduces bias. They also argue that aggregate metrics hide risk and that benchmark data ignores the probabilistic nature of NL-to-SQL. They propose a taxonomy of limitations that cause both prediction and evaluation errors. (Abstract only; no numbers.) — [arXiv 2501.18197](https://arxiv.org/abs/2501.18197)
- Neither EX nor test-suite accuracy catches every blind spot:
  - An incomplete WHERE clause passes if the test data happens to satisfy the missing condition, and empty result sets make many wrong queries look correct. — [arXiv 2506.09359](https://arxiv.org/pdf/2506.09359) **(weak, from snippet)**
  - ModularSQL argues that BIRD's set-based comparison hides duplicate-row (multiplicity) errors. — [arXiv 2609.29573](https://arxiv.org/pdf/2609.29573) **(weak, from snippet)**
- SQLStructEval (Apr 2026) notes that syntactically distinct SQL can yield identical execution results. It proposes structure-aware metrics to expose instability that EX misses. — [arXiv 2604.06736](https://arxiv.org/pdf/2604.06736) **(weak, from snippet)**

**VES (BIRD)**
- BIRD (Li et al., NeurIPS 2023): 12,751 pairs over 95 databases (33.4 GB) in 37 domains. At release, human EX was 92.96% and ChatGPT reached 40.08%. — [arXiv 2305.03111](https://arxiv.org/abs/2305.03111)
- R-VES (the reward-based Valid Efficiency Score) is computed only over EX-correct queries. Each predicted query's runtime is compared with the gold query's: the reward is 1.0 if the prediction is at least as fast and falls to a floor of 0.5 for very slow queries; rewards are averaged over the set. — [Medium secondary analysis](https://medium.com/@adnanmasood/pushing-towards-human-level-text-to-sql-an-analysis-of-top-systems-on-bird-benchmark-666efd211a2d) **(weak; exact formula not verified against BIRD's evaluation code)**

**SPARQL: answer-set F1 and related metrics**
- The Text2SPARQL 2025 challenge (a shared task co-located with ESWC 2025) used an execution-based F1 over result sets, 2·|T∩G| / (|T|+|G|) (the "TREC F1"), according to the SPARQL-LLM paper. — [arXiv 2512.14277](https://arxiv.org/pdf/2512.14277); challenge preface [CEUR Vol-4094](https://ceur-ws.org/Vol-4094/preface.pdf); results [text2sparql.aksw.org/2025/results](https://text2sparql.aksw.org/2025/results/) (official metric list not independently fetched)
- T2S-Metrics (Taghzouti et al., 22 Apr 2026) is a library of more than 20 metrics:
  - query-based: token precision/recall/F1, BLEU/ROUGE/METEOR/CodeBLEU, variable-normalised SP-BLEU and SP-F1, graph- and URI-based exact match;
  - answer-set: F1-QALD and Jaccard;
  - ranking: MRR, NDCG, P@k, Hit@k;
  - LLM-as-judge.

  It was used to evaluate the Text2SPARQL'25 outputs on the CK25 dataset. Its abstract reports no human-correlation study. — [arXiv 2604.26971](https://arxiv.org/abs/2604.26971); [docs](https://t2s-metrics.readthedocs.io/en/latest/)
- A GRPO-based Text-to-SPARQL paper on DBLP reports exact match together with answer-set F1, which gives partial credit on multi-answer questions. — [arXiv 2605.20066](https://arxiv.org/pdf/2605.20066) **(weak, from snippet)**

**Cypher**
- Neo4j's Text2Cypher (2024) benchmark (a blog post, not peer-reviewed) has two procedures. "Translation" scores query text with Google BLEU; "execution" scores stringified results with ExactMatch. GPT-4o and a fine-tuned model reach about 30% execution match. Neo4j itself warns that ExactMatch is thrown off by a newline or an extra space, and lists parse-tree comparison as future work. — [Neo4j blog: benchmarking](https://neo4j.com/blog/developer/benchmarking-neo4j-text2cypher-dataset/); [Neo4j blog: model struggles](https://neo4j.com/blog/developer/text2cypher-model-struggles-dataset-improvements/)

**LLM-as-judge**
- FLEX (Kim et al., NAACL 2025) uses an LLM to emulate expert evaluation. Cohen's kappa with human experts rises from 62 (EX) to 87.04 (FLEX); the arXiv v1 figures were 61 to 78.17. Re-scoring top Spider/BIRD models shifts rankings: on average -3.15 points from correcting false positives and +6.07 from correcting false negatives. — [ACL Anthology 2025.naacl-long.228](https://aclanthology.org/2025.naacl-long.228); [arXiv 2409.19014](https://arxiv.org/html/2409.19014v2)
- LLM-SQL-Solver (Zhao et al., arXiv 2312.10321) distinguishes *semantic* from *relaxed* equivalence and proposes the "Miniature & Mull" and "Explain & Compare" prompting methods. GPT-4o "can assist" but "may yield incorrect responses". — [arXiv 2312.10321v4](https://arxiv.org/html/2312.10321v4)
- LLM judges are sensitive to temperature in task-dependent ways (2026). — [arXiv 2603.28304](https://arxiv.org/html/2603.28304) **(weak, from snippet)**

**Formal equivalence checkers**
- On the SQLEquiQuest benchmark, SQLSolver supports only about 30% of query pairs and VeriEQL only 2.8%. Checkers such as Cosette also fail to explain their verdicts. — [arXiv 2412.05561](https://arxiv.org/html/2412.05561v2)
- Verifying SQL equivalence is NP-hard. The QUITE query-rewrite system runs SQLSolver first and falls back to LLM judgement. — [arXiv 2506.07675](https://arxiv.org/pdf/2506.07675)

### Inferences
- A defensible metric stack has three tiers:
  1. Primary: answer/denotation match on several database instances (test suites or synthesised databases).
  2. A formal checker where it supports the query pair, as a sound tie-breaker.
  3. An LLM judge for the remaining cases, calibrated against a human-labelled sample, with kappa reported. FLEX's kappa of about 0.87 is the bar to beat.
- For SPARQL, report answer-set F1 together with strict answer-set exact match. Ordering-sensitive questions (ORDER BY/LIMIT) and aggregate questions need separate handling. Text-similarity metrics (BLEU, SP-BLEU) are diagnostics, not measures of correctness.
- Cypher has no community-standard semantic metric. A project like SIP should compare normalised result sets (order-insensitive multisets, type-normalised values) instead of using Neo4j's string ExactMatch.

### Gaps
- I found no published human-agreement study for SPARQL answer-set F1 or for T2S-Metrics' LLM-judge metrics.
- The exact current R-VES formula is unverified, and I did not find whether Spider 2.0 has an efficiency metric.
- I did not retrieve QED's or VeriEQL's own coverage and soundness numbers, only the third-party coverage figures on SQLEquiQuest.

## 2. Annotation errors in BIRD, Spider and Spider 2.0, and their effect on rankings

### Takeaway
A 2026 PVLDB audit estimates that 52.8% of BIRD Mini-Dev and 62.8% of the auditable Spider 2.0-Snow examples are erroneous. Correcting a BIRD Dev subset reorders the leaderboard: ranks shift by up to 9 places in either direction, and the leading system falls from 1st to 7th. Leaderboard rankings computed on uncorrected data are unreliable at the top.

### Cited Findings
- Jin, Choi, Zhu & Kang, "Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards" (arXiv 2601.08778, Jan 2026; PVLDB vol. 19):
  - BIRD Mini-Dev: 263 of 498 examples (52.8%) are erroneous. Arcwise had previously reported 32.3%.
  - Spider 2.0-Snow: 76 of 121 (62.8%). Only 121 of its 547 examples have public gold SQL, so only those could be audited.

  — [arXiv HTML](https://arxiv.org/html/2601.08778v3); [PVLDB page](https://vldb.org/pvldb/volumes/19/paper/Pervasive%20Annotation%20Errors%20Break%20Text-to-SQL%20Benchmarks%20and%20Leaderboards)
- Error taxonomy, as a share of erroneous examples (BIRD / Spider 2.0-Snow; an example can have several types):

  | Type | Description | BIRD | Spider 2.0-Snow |
  |---|---|---|---|
  | E1 | Query logic does not match the question | 29.3% | 48.7% |
  | E2 | Query does not match the data or schema | 57.8% | 57.9% |
  | E3 | Incorrect domain knowledge | 10.7% | 11.8% |
  | E4 | Ambiguous question or output format | 29.7% | 23.7% |

  Spider 2.0 examples include `TO_TIMESTAMP` truncation of end dates, row inflation from JOIN/FLATTEN, and quotation-mark formatting that the evaluator requires but the question never specifies. — [arXiv 2601.08778v3](https://arxiv.org/html/2601.08778v3)
- Audit method: the SAR-Agent (OpenAI o3, up to 30 iterations) produced a diagnostic report per example; humans adjudicated the flags and then extended manual review to recurring patterns. The agent's flag precision was 83% on BIRD and 89% on Spider 2.0-Snow. Two authors judged each example independently, but **no inter-annotator kappa is reported**. — [arXiv 2601.08778v3](https://arxiv.org/html/2601.08778v3)
- Ranking impact: 16 open-source BIRD agents were re-evaluated on a corrected Dev subset.
  - Relative score changes ranged from -7% to +31%, and rank changes from -9 to +9.
  - Contextual-SQL fell from 1st to 7th; GenaSQL and CHESS tied for 1st.
  - Rankings on the uncorrected subset correlate with full-Dev rankings at Spearman 0.85; rankings on the corrected subset correlate at only 0.32.

  — [Substack summary by D. Kang](https://ddkang.substack.com/p/pervasive-annotation-errors-break); [arXiv](https://arxiv.org/html/2601.08778v3)
- The paper recommends: automated review followed by human adjudication; validating queries against the actual data, since E2 is the most common error; specifying output formats; and adding distinguishing records so that wrong queries cannot match the gold results by coincidence. — [arXiv 2601.08778v3](https://arxiv.org/html/2601.08778v3)
- FLEX's re-scoring (see Section 1) also changes Spider/BIRD rankings, through both false-positive and false-negative corrections. — [ACL Anthology](https://aclanthology.org/2025.naacl-long.228)
- LC-QuAD 2.0 (SPARQL) has decayed: many of its queries no longer return answers on current Wikidata, and the original dump is no longer online. About 16% of questions require copying input tokens into the query. — [arXiv 2204.12793](https://arxiv.org/pdf/2204.12793)

### Inferences
- With error rates above 50%, differences of a few points between top systems on BIRD or Spider 2.0 are within annotation noise. SIP should choose models using an internally audited evaluation set.
- Knowledge-graph benchmarks have an extra failure mode: endpoint drift, as with LC-QuAD 2.0 on live Wikidata. A custom SPARQL evaluation set must pin a dataset snapshot (for example, a fixed Fuseki dataset version) to stay valid.

### Gaps
- I found no quantified audit of the original Spider 1.0 dev set comparable to the 2026 paper, and none of Text2Cypher datasets.
- I could not confirm whether the corrected 100-example BIRD Dev subset is publicly released.

## 3. Ambiguity and underspecification, unanswerable questions and abstention, robustness, paraphrase consistency, and repeated-run stability

### Takeaway
Each of these failure modes has dedicated benchmarks: AmbiQT, AMBROSIA and PRACTIQ for ambiguity, TrustSQL and EHRSQL for abstention, and Dr.Spider for robustness to perturbations. All show large drops compared with clean benchmarks. Outputs vary between repeated runs even at temperature 0, but this is rarely reported. TrustSQL's penalty-based score is the most principled way to fold abstention into a single number.

### Cited Findings
- **AmbiQT** (Bhaskar et al., EMNLP 2023): every question has two plausible SQL readings. Systems, including LLM-based ones, "fall well short" of generating all valid interpretations. — [ACL Anthology 2023.emnlp-main.436](https://aclanthology.org/2023.emnlp-main.436)
- **AMBROSIA** (Saparina & Lapata, NeurIPS 2024 Datasets & Benchmarks): covers scope ambiguity, attachment ambiguity and vagueness, and pairs each interpretation with its SQL. Even the most advanced LLMs struggle to recognise the ambiguity. — [NeurIPS 2024](https://papers.neurips.cc/paper_files/paper/2024/hash/a4c942a8405cc910f0a833d28d2573cc-Abstract-Datasets_and_Benchmarks_Track.html)
- **PRACTIQ** (AWS, arXiv 2410.11076): conversational text-to-SQL with ambiguous and unanswerable categories. State-of-the-art systems struggle with both. — [arXiv 2410.11076](https://arxiv.org/html/2410.11076v1); [Amazon Science](https://amazon.science/publications/practiq-a-practical-conversational-text-to-sql-dataset-with-ambiguous-and-unanswerable-queries)
- A later system reports "full coverage" (all valid interpretations generated) of 72.6% on AmbiQT, against 53.2% for the prior state of the art (DFPL). On AMBROSIA+ (6,777 examples) it reports 73.0% against 30.5%. — [Georgia Tech news on an IEEE paper](https://scp.cc.gatech.edu/external-news/ieee-xplore-rag-or-not-rag-question-effective-text-sql-generation-under-ambiguity) **(weak, single secondary source)**
- **TrustSQL** (Lee et al., arXiv 2403.15879): the model either outputs SQL or abstains. The Reliability Score rewards correct SQL on feasible questions and abstention on unanswerable ones, and applies a penalty for incorrect SQL. It covers Spider, ATIS, Advising and EHRSQL. No method consistently beats the naive baseline that abstains on every question, across the penalty levels tested. — [arXiv 2403.15879v4](https://arxiv.org/html/2403.15879v4)
- The **EHRSQL 2024** shared task used TrustSQL's Reliability Score as its primary metric. — [arXiv 2403.15879](https://arxiv.org/html/2403.15879v4); [overview review](https://themoonlight.io/review/overview-of-the-ehrsql-2024-shared-task-on-reliable-text-to-sql-modeling-on-electronic-health-records) **(secondary)**
- **Dr.Spider** (Chang et al., ICLR 2023): 17 perturbations of the Spider dev set (3 database, 9 natural-language question, 5 SQL). Even the most robust model drops 14.0% overall and 50.7% on the hardest perturbation. — [arXiv 2301.08881](https://arxiv.org/abs/2301.08881); [GitHub awslabs/diagnostic-robustness-text-to-sql](https://github.com/awslabs/diagnostic-robustness-text-to-sql)
- **Paraphrase sensitivity as a probe:** SPENCE varies question syntax and tracks how EX changes (see Section 4). — [arXiv 2604.17771](https://arxiv.org/abs/2604.17771)
- **Repeated-run stability:**
  - Even at temperature 0, the same prompt can produce different outputs depending on serving conditions (batch size, load). Autocorrelation across runs is near zero, so runs can be treated as independent trials (Jul 2026). — [arXiv 2607.03991](https://arxiv.org/pdf/2607.03991) **(weak, from snippet)**
  - The ALeRCE astronomy text-to-SQL system ran 10 trials per setup. Consistency at temperature 0 varies by model; older models are less stable on medium and hard queries. — [arXiv 2606.18108](https://arxiv.org/pdf/2606.18108) **(weak, from snippet)**
  - A general LLM study found "an alarming degree of variation" across runs in settings presumed deterministic, and noted that benchmarks usually report a single run. — [arXiv 2408.04667](https://arxiv.org/pdf/2408.04667v5)
- BIRD-Interact (ICLR 2026) evaluates ambiguity resolution interactively, with a user simulator, in two settings: c-Interact (a predefined conversational protocol) and a-Interact (open-ended and agentic). It covers the full CRUD range with executable test cases. — [arXiv 2510.05318](https://arxiv.org/html/2510.05318v3); [ICLR 2026](https://proceedings.iclr.cc/paper_files/paper/2026/hash/496b549556509bbb9770bf9d335c5800-Abstract-Conference.html)

### Inferences
- Label every item in a custom evaluation set as answerable and unambiguous, ambiguous (with all gold interpretations), or unanswerable (out of schema or out of the KG). Score ambiguous items by interpretation coverage and unanswerable items by abstention precision and recall. Report a TrustSQL-style penalised score at several penalty values.
- Report stability as the mean and spread over at least 3 runs, plus a per-item breakdown into always, sometimes and never correct. Single-run numbers overstate precision.
- Dr.Spider's taxonomy carries over to SPARQL and Cypher: question paraphrases and synonyms, schema renames (ontology label or IRI changes), and data or value perturbations. I found no equivalent KG benchmark.

### Gaps
- I found no SPARQL or Cypher benchmark dedicated to ambiguity or abstention, and no Dr.Spider-style robustness suite for knowledge graphs.
- I found no paper that systematically reports repeated-run variance on the Spider or BIRD leaderboards.

## 4. Contamination and memorisation; live and held-out benchmarks

### Takeaway
Spider shows clear signs of training-data leakage. BIRD (released May 2023) appears largely clean, according to SPENCE (Apr 2026). The field's response is live or hidden-test benchmarks such as LiveSQLBench and BIRD-Interact. For in-house work, privately constructed held-out sets over unseen schemas are the strongest control.

### Cited Findings
- Ranaldi et al. (Findings of ACL 2024): GPT-3.5 performs significantly worse on Termite, a new dataset built to be absent from training data, than on Spider. The drop persists even with Adversarial Table Disconnection (removing foreign-key structure). The model can also reconstruct missing schema information, which the authors treat as a contamination signal. — [arXiv 2402.08100](https://arxiv.org/html/2402.08100v1); [ACL Anthology](https://aclanthology.org/2024.findings-acl.827)
- SPENCE (Safarzadeh, Patel, Orojlooyjadid, Horwood, Roth; arXiv 2604.17771, 20 Apr 2026; ACL 2026 Main):
  - generates syntactic variants of the test questions for Spider, SParC, CoSQL and BIRD, and measures how EX decays as syntax diverges;
  - measures rank sensitivity with Kendall's tau and bootstrap confidence intervals, aligned with each benchmark's release date;
  - finds the strongest negative tau on Spider (most likely leakage), while BIRD is "largely uncontaminated".

  — [arXiv 2604.17771](https://arxiv.org/abs/2604.17771)
- LiveSQLBench (BIRD team at HKU, with Google Cloud) is described as "contamination-free" and continuously evolving:
  - each release adds about 20 new databases, up to more than 1,340 columns;
  - SELECT tasks are scored with Soft EX and CRUD tasks with test cases;
  - it has an open development phase and a hidden test phase.

  — [HF dataset card](https://huggingface.co/datasets/birdsql/livesqlbench-base-full-v1). An aggregator lists top success rates of about 43%. — [benchmarklist.com](https://benchmarklist.com/benchmarks/livesqlbench/) **(weak, aggregator)**
- BIRD-Interact is built on LiveSQLBench's tasks and sandbox. — [arXiv 2510.05318](https://arxiv.org/html/2510.05318v3)
- Text2SPARQL 2025 was evaluated on challenge datasets, including CK25, in a shared-task format with fresh test data. — [CEUR Vol-4094 preface](https://ceur-ws.org/Vol-4094/preface.pdf); [arXiv 2604.26971](https://arxiv.org/abs/2604.26971)

### Inferences
- Practical contamination controls for an in-house evaluation set:
  - use schemas and ontologies that are not on the public web (FIBO is public, so FIBO-based items are at risk);
  - pin release dates;
  - measure accuracy deltas under paraphrase probes (SPENCE-style);
  - run schema-renaming probes (similar in spirit to Ranaldi et al.'s schema perturbation).
- Contamination matters less for private enterprise schemas. Any public seed data (FIBO, Wikidata, DBpedia) should be assumed to have been seen by frontier models.

### Gaps
- I found no contamination study of SPARQL benchmarks (QALD, LC-QuAD) or Text2Cypher datasets.
- I did not obtain SPENCE's per-dataset tau values.

## 5. Building custom evaluation sets: query-first then verbalise, human validation, stratification, split hygiene, sample sizes and statistical tests

### Takeaway
The dominant recipe is query-first, then verbalise:
1. Generate executable queries over the target schema or KG, from templates or with an LLM.
2. Turn them into natural-language questions, using crowd workers or an LLM.
3. Validate each item by executing it and by human review.

For template-generated SPARQL questions, LLM verbalisation now matches crowd rephrasing. The 2026 audit shows that human adjudication plus checks against the real data are mandatory. Comparisons between systems should be paired: McNemar's test and the paired bootstrap are the norm in 2026 papers.

### Cited Findings
- **OmniSQL / SynSQL-2.5M** (Li et al., arXiv 2503.02240; PVLDB 18): about 2.5M samples over more than 16,000 synthetic databases. Each sample has a database, question, SQL and chain-of-thought solution. It was generated with open LLMs and is released under Apache 2.0.
  - Quality rubric: excellent, good, average or poor, weighted 1.0, 0.75, 0.5 and 0.25.
  - On 1,000 random samples from each dataset, SynSQL beats BIRD on nearly all criteria, for example 0.94 vs 0.707 on unambiguous phrasing.
  - **Who did the rating is unclear (possibly an LLM)**, so this is weak evidence of quality.

  — [arXiv 2503.02240](https://arxiv.org/html/2503.02240v2); [PVLDB](https://vldb.org/pvldb/volumes/18/paper/OmniSQL%3A%20Synthesizing%20High-quality%20Text-to-SQL%20Data%20at%20Scale)
- **LC-QuAD 2.0** (Dubey et al., ISWC 2019): 30,000 questions with paraphrases and SPARQL, for Wikidata and DBpedia 2018. Pipeline: template SPARQL, then automatically generated Normalised Natural Question Templates (NNQT), then crowd verbalisation and paraphrasing. — [ISWC 2019 PDF](https://jens-lehmann.org/files/2019/iswc_lcquad2.pdf)
- An IBM Research paper (CEUR, 2025) describes NNQT questions as rigid and says manual rephrasing "is resource-intensive and does not always yield high-quality results". An LLM can regenerate the questions with similar quality and comparable downstream fine-tuning results. — [CEUR Vol-4108 paper4](https://ceur-ws.org/Vol-4108/paper4.pdf)
- Test databases can be generated from the question and schema rather than from the gold SQL (SynSQL-DB; Habibollah & Rafiei, Apr 2026). This avoids biasing the test data towards the gold query. Its three stages are schema selection, question-guided data synthesis, and constraint-aware critique with iterative refinement. — [arXiv 2604.27261](https://arxiv.org/abs/2604.27261)
- **Validation and audit:** an LLM auditor (SAR-Agent, flag precision 83–89%) combined with two independent human reviewers and adjudication. Most errors are mismatches with the data or schema, so validate against the real data. — [arXiv 2601.08778](https://arxiv.org/html/2601.08778v3)
- **Statistical tests in 2026 text-to-SQL papers:**
  - McNemar's test plus paired bootstrap percentile intervals on the accuracy difference (10,000 resamples). Exact binomial p-values are used where the normal approximation fails at extreme tail probabilities, and discordant-pair counts are reported. — [arXiv 2608.22651](https://arxiv.org/pdf/2608.22651)
  - Exact McNemar plus paired bootstrap; one improvement was declared inconclusive (p = 0.125, interval including 0). — [arXiv 2609.00834](https://arxiv.org/pdf/2609.00834)
  - Three runs per model, with the median run used to build the McNemar matrix. — [arXiv 2305.13073](https://arxiv.org/pdf/2305.13073)
  - McNemar's test used to show that normalisation effects were not significant. — [arXiv 2305.11853](https://arxiv.org/pdf/2305.11853)
- SPENCE uses bootstrap confidence intervals on Kendall's tau to assess rank stability. — [arXiv 2604.17771](https://arxiv.org/abs/2604.17771)

### Inferences
(These are the researcher's synthesis, not sourced claims.)
- **Recipe for a SIP evaluation set:**
  1. Enumerate query templates for each ontology pattern: class lookup, property path, aggregation, negation (FILTER NOT EXISTS), OPTIONAL, ordering/top-k, temporal.
  2. Instantiate them against the pinned Fuseki snapshot. Keep only queries whose answers are non-empty and non-trivial.
  3. Have an LLM verbalise each query into several paraphrases, including lexical variation drawn from `skos:altLabel`.
  4. Add ambiguous and unanswerable items.
  5. Have two humans review a stratified sample (or every item) and report their agreement.
  6. Stratify the reported results by template, hop count, operator, and seen versus unseen schema region.
- **Split hygiene:** split by template and schema region, not by question, so that paraphrases of the same query never appear on both sides of a train/dev–test boundary. Keep a sealed test set that is never used for prompt tuning.
- **Sample sizes:** for a single system with accuracy p, the standard error is sqrt(p(1-p)/n). At p = 0.7, the 95% confidence interval is about ±4.0 points with n = 500 and about ±2.8 points with n = 1,000. For paired comparisons, McNemar's power depends on the number of discordant pairs (questions where the two systems disagree), so the required n depends on how often they disagree rather than on overall accuracy. Report confidence intervals for every headline number, and n for every stratum.

### Gaps
- I found no published human-validation acceptance rate for LLM-verbalised synthetic text-to-SQL or text-to-SPARQL items (that is, what share of generated pairs annotators accept).
- I found no 2025–26 guidance specific to NL-to-query on planning sample sizes, or on clustering by database or template in significance tests.

## 6. Counterfactual and perturbed databases to separate correct from coincidentally correct queries

### Takeaway
EX on a single database instance overestimates accuracy. Evaluating on several synthesised database instances lowers scores by about 3–14% (SynSQL-DB, Apr 2026). This is the most direct defence against coincidentally correct queries, and it carries over naturally to knowledge graphs by perturbing the triple store.

### Cited Findings
- The precedent is Zhong et al.'s (2020) test suites: databases produced by fuzzing, selected for high code coverage of the gold query. — [ar5iv 2010.02840](https://ar5iv.labs.arxiv.org/html/2010.02840)
- SynSQL-DB (Habibollah & Rafiei, arXiv 2604.27261, 29 Apr 2026): across 10 text-to-SQL models on Spider, BIRD and Spider 2.0, evaluation on synthesised databases shows performance drops of 3–14% compared with static evaluation. — [arXiv 2604.27261](https://arxiv.org/abs/2604.27261). A snippet from the same paper says the compound metric (correct on all instances) lowers BIRD accuracy by about 6–9% relative to official EX. **(weak, from snippet)**
- The 2026 annotation audit recommends adding distinguishing records to benchmark databases, so that incorrect queries cannot return the gold results. — [arXiv 2601.08778](https://arxiv.org/html/2601.08778v3)
- Dr.Spider's database perturbations (such as schema synonyms) test schema-linking robustness, which is different from data-level counterfactuals. — [arXiv 2301.08881](https://arxiv.org/abs/2301.08881)
- Coincidental matches also affect selection inside systems. R³-SQL groups candidate queries by their execution results, so "lucky-guess" queries land in the correct group, and then uses a pointwise ranker to pick a representative. By the same logic, coincidental matches can also distort self-consistency voting. — [arXiv 2604.25325](https://arxiv.org/pdf/2604.25325) **(weak, from snippet)**
- A counterfactual-validation approach for Text-to-SPARQL over heterogeneous KGs exists. — [arXiv 2508.01815](https://arxiv.org/pdf/2508.01815) **(title only; content not verified)**

### Inferences
- For SIP on Fuseki, counterfactual evaluation is cheap. Build k perturbed named-graph variants for each test item:
  - delete or add triples that would satisfy a missing FILTER;
  - duplicate entities to expose DISTINCT and multiplicity errors;
  - flip literal values near thresholds;
  - rename labels.

  Count an item as correct only if the answers match the gold on all variants. FalkorDB projections can be perturbed the same way for Cypher.

### Gaps
- I found no published knowledge-graph-specific counterfactual evaluation study with numbers. I did not open arXiv 2508.01815.
