# Text-to-SPARQL (KGQA) and Text-to-Cypher/GQL: benchmarks, SOTA and methods (as of 2026-10-19)

Scope: NL -> SPARQL over public KGs (Wikidata, DBpedia) and enterprise/domain KGs, NL -> Cypher/GQL, plus OBDA/VKG (Ontop/R2RML) and SPARQL-vs-SQL evidence. Written for a practitioner building NL->SPARQL over an OWL ontology + Ontop VKG on a relational DB (FIBO). About 28 searches/fetches. Where the evidence is weak, I say so. Metrics are often incompatible across benchmarks; see the notes under each item.

## 1. Benchmarks: size, metric, flaws

### Takeaway
The live yardsticks in 2025-26 are now challenge-style hidden test sets: TEXT2SPARQL 2025/2026 (DBpedia plus a small private "corporate" KG, set-based F1/nDCG) and WikiKGQA 2026 (Wikidata, Macro QALD-F1). They are small, with 50 to 200 questions per track. The legacy corpora (QALD-9/10, LC-QuAD 1/2, Spider4SPARQL, SciQA) now serve mainly as training data and few-shot example pools. They suffer from known template, annotation and contamination problems. On the Cypher side, the benchmark mix is CypherBench (Wikidata-derived property graphs, execution accuracy), the Neo4j and IBM Text2Cypher corpora, and the new Text2GQL-Bench.

### Cited Findings
**TEXT2SPARQL 2025 (1st edition, ESWC 2025)**
- Held with Text2KG at ESWC 2025, Portoroz, on 2025-06-01. Participants deployed REST services taking `question` and `dataset` GET parameters, with a 10-minute timeout per query. There was a 5-day test phase. — [ARUQULA paper](https://arxiv.org/html/2510.02200v1)
- DB25 is an English and Spanish subset of DBpedia 2015-10 with 200 manually curated questions (100 per language). CK25 is a corporate KG built by the organizers, with 50 English questions written with corporate stakeholders. — [ARUQULA paper](https://arxiv.org/html/2510.02200v1)
- Proceedings are CEUR Vol-4094 (6 of 9 submitted papers accepted): Wardenga & Kafer (data shapes), Soru et al. (fine-tuned autoregressive models), Graf von Data (Dorsch et al., organisational KGQA agent), ARUQULA, AIRI, and mKGQAgent (Perevalov & Both). — [CEUR Vol-4094](https://ceur-ws.org/Vol-4094/)

**TEXT2SPARQL 2026 (2nd edition, ESWC 2026)**
- Co-located with Text2KG at ESWC26, Dubrovnik, on 2026-05-10. Eight competing approaches; languages English, Spanish and German. — [SPARQL-LLM in T2S 2026](https://arxiv.org/abs/2610.13648)
- The corporate KG is "compact and highly specialized": 13 classes, 30 properties, 2,626 described resources and 26,587 statements. Questions cover people, departments, managers and contact details. Metrics are Precision, Recall and F1, nDCG where order matters, and a query complexity analysis (triple patterns, joins, modifiers). Training may use DBNQA, QALD and LC-QuAD. The prize is 500 EUR. — [Challenge description](https://text2sparql.aksw.org/latest/participation/challenge/)
- Timeline: DBpedia evaluation started 2026-04-10; the corporate dataset was released 2026-04-13 and evaluated from 2026-04-15; results were announced 2026-05-13. Listed teams: ADFR, INFAI ETI & Friends A/B/C, IRIS, LiberAI Claude, LiberAI Qwen, SPARQL-LLM. — [TEXT2SPARQL 2026 site](https://text2sparql.aksw.org/latest/)
- Test sets: DBpedia has 50 questions (EN+ES) over a well-documented KG. The corporate set has 50 questions (EN+DE) over a private, undocumented KG. The 2025 test set (100 questions) was reused as example data. Scores are F1 via the T2S-Metrics library, with NDCG for corporate. — [SPARQL-LLM in T2S 2026, HTML](https://arxiv.org/html/2610.13648) (the question count was inferred from a garbled table rendering)

**WikiKGQA 2026 (1st edition, ISWC 2026, Bari, 2026-10-25)**
- The task is EN and ES questions to SPARQL over Wikidata. Training/dev data is the QAWiki v2026.2 snapshot (2026-04-08), and the competition runs on Codabench. — [W3C semantic-web list CfP](https://lists.w3.org/Archives/Public/semantic-web/2026Jun/0026.html); [CEUR Vol-4284](https://ceur-ws.org/Vol-4284/)
- The hidden test set has 150 manually built questions over 4 tracks: EN/ES, each with or without hand-crafted entity and relation mentions. The with- and without-mention sets are disjoint, 75 questions each. The metric is Macro QALD-F1: macro precision and recall are computed first, then F1. — [WikiKGQA overview paper](https://ceur-ws.org/Vol-4284/intro1.pdf); [metric definition](https://www.nliwod.org/challenge#evaluation-metric); [implementation](https://github.com/debayan/wikikgqa-public)
- Flaws the organizers acknowledge:
  - Two gold questions had quality issues, and Wikidata itself contains data errors.
  - No test query uses OPTIONAL, and the queries are entity-centric.
  - There are too few hard questions, so the top scores cluster in [0.8, 0.9).
  - Answers can be produced from parametric knowledge by "reverse-engineering" a query.
  - The organizers propose a future track with a novel or less-known KG. — [WikiKGQA overview paper](https://ceur-ws.org/Vol-4284/intro1.pdf)

**Legacy and other SPARQL benchmarks**
- QALD-10 has 394 complex test queries in 4 languages, with aggregations and subqueries. LC-QuAD 2.0 is template-generated and English-only, with about 30k train and 6k test questions. — [search summary citing GRISP and related](https://arxiv.org/pdf/2604.21133) (weak: drawn from a search snippet)
- Spider4SPARQL (Kosten et al., IEEE BigData 2023) has 9,693 NL questions, 4,721 unique SPARQL queries, and 166 KGs/ontologies covering 138 domains. These are Spider's relational DBs turned into KGs. KGQA systems and LLMs reached at most 45% execution accuracy. — [arXiv 2309.16248](https://arxiv.org/abs/2309.16248); [repo](https://github.com/ckosten/spider4sparql)
- SciQA (ORKG scholarly KG) is used by EXYGEN (Sep 2026). Its best configuration reaches only 0.419 execution-result exact match and still trails fully fine-tuned approaches. — [EXYGEN, arXiv 2609.11569](https://arxiv.org/abs/2609.11569)
- Benchmark quality: LC-QuAD 1/2 combine templates with human paraphrase. Changing the benchmark alone can flip which QA system ranks best. A survey of 100 publications found no central, up-to-date leaderboard for LC-QuAD/QALD. — [VLDB 2022, Orogat et al.](https://www.vldb.org/pvldb/vol15/p3662-orogat.pdf)
- A 2025 audit of 16 KGQA datasets found inaccurate, incomplete or outdated gold answers and ambiguous questions, especially in WebQSP and CWQ. It found that exact match undercounts correct answers, and it proposed KGQAGen-10k with SPARQL-verified answers. — [arXiv 2505.23495](https://arxiv.org/html/2505.23495v4)
- Biomedical: SPARQL-LLM evaluates on UniProt, Cellosaurus and Bgee with 3-fold CV and result-based F1, excluding zero-result queries. It reports F1 0.414 on 126 UniProt queries versus GRASP's 0.207 on 50 queries; the authors say these are not comparable. — [SPARQL-LLM v1](https://arxiv.org/html/2512.14277v1)
- AutoSchema evaluates on resource-focused and multi-resource biomedical KGQA, longitudinal BioASQ Task B, and transfer to an undocumented chemistry RDF graph. Its baseline is TogoMCP. No numbers appear in the abstract. — [arXiv 2608.14228](https://arxiv.org/abs/2608.14228)

**Cypher / GQL benchmarks**
- CypherBench (Feng, Papicchio, Rahman; v2 2025-04-04) has 11 property-graph views over Wikidata with 7.8M entities and more than 10k questions. It covers 12 graph patterns, including special patterns (comparison, grouping, optional, time-sensitive, union) and "global" queries. Metrics are Execution Accuracy and Provenance Subgraph Jaccard Similarity. — [arXiv 2412.18702](https://arxiv.org/abs/2412.18702); [alphaXiv overview](https://www.alphaxiv.org/overview/2412.18702v2)
- Neo4j Text2Cypher (2024) merges public datasets into 44,387 instances (GenAIK 2025). It is evaluated by Google-BLEU, exact match and execution comparison. — [arXiv 2412.10064](https://arxiv.org/abs/2412.10064); [ACL Anthology](https://aclanthology.org/2025.genaik-1.11); [Neo4j benchmark blog](https://neo4j.com/developer-blog/benchmarking-neo4j-text2cypher-dataset)
- Mind the Query (IBM, EMNLP 2025 Industry track) has 27,529 NL-Cypher pairs over 11 real graphs, validated by schema, runtime and value checks plus manual review. — [IBM Research](https://researchweb.draco.res.ibm.com/publications/mind-the-query-a-benchmark-dataset-towards-text2cypher-task)
- PIPE-Cypher (Jun 2026) generates enterprise Text2Cypher benchmarks automatically with Qwen3.5-9B: 3,000 FinBench/SNB examples. Zero-shot transfer is weak, and few-shot example banks help some model families. — [papers.cool 2606.08481](https://papers.cool/arxiv/2606.08481)
- CypherSmith (ACL 2026) is a synthetic instruction-tuning set more than 12x larger than prior public Text2Cypher sets. — [ACL Anthology preview](https://preview.aclanthology.org/ingest-acl/2026.acl-long.1601/)
- Text2GQL-Bench (Feb 2026) builds a unified multi-language benchmark. Cypher is parsed into an intermediate representation and translated to ISO GQL and other languages; SQL is converted to Cypher first. Queries are execution-filtered. — [arXiv 2602.11745](https://arxiv.org/abs/2602.11745v1)

### Inferences
- The TEXT2SPARQL corporate KG (13 classes, 30 properties, about 27k triples) is far smaller and simpler than FIBO. "Enterprise" results there say little about large, deep OWL ontologies, but they are the closest public proxy.
- All challenge test sets have 50 to 200 questions, so differences of a few F1 points are within noise. None of these sets reports confidence intervals.
- The metrics are incompatible:
  - TEXT2SPARQL uses set-based F1 (micro-ish, via T2S-Metrics), with nDCG for ordered results.
  - WikiKGQA uses Macro QALD-F1.
  - CypherBench and Spider4SPARQL use execution accuracy (exact result match).
  - Neo4j uses BLEU/EM.
  - Do not compare these numbers across benchmarks.

### Gaps
- I could not find an official TEXT2SPARQL 2025 leaderboard with numbers (the results pages were not fetched), nor the 2026 per-team scores outside the SPARQL-LLM paper.
- I found nothing on "Build2SPARQL"; it may not exist under that name.
- DBLP-QuAD and KQA Pro were not re-verified this round; no 2026 SOTA numbers were found for them.
- I found no published Text2Cypher/GQL leaderboard dedicated to multi-agent systems.

## 2. SOTA systems and scores; public vs enterprise gap

### Takeaway
SPARQL-LLM (SIB) won TEXT2SPARQL 2026. Its F1 scores are 0.72 to 0.78 on DBpedia and 0.81 to 0.85 on the corporate KG, against about 0.49 to 0.64 for the runner-up ARUQULA. It got there with metadata plus retrieved examples plus validator loops, using GPT-5.2 at under $3 for the whole challenge. On Wikidata (WikiKGQA 2026), agentic systems (ASTER, AMA-KBQA, GRASP) reach Macro F1 0.79 to 0.88. Strikingly, the organizers note that off-the-shelf Claude Code baselines are competitive. The public-vs-enterprise gap persists mainly when no examples are available. When synthetic, execution-checked examples are generated for the private KG, corporate scores can exceed DBpedia scores.

### Cited Findings
- **TEXT2SPARQL 2026 F1, SPARQL-LLM vs second best (ARUQULA v1):**
  - DBpedia EN: 0.7192 vs 0.6142
  - DBpedia ES: 0.7810 vs 0.4904 (+59%)
  - Corporate EN: 0.8539 vs 0.6409
  - Corporate DE: 0.8141 vs 0.6242
  - Other competitors: GRASP, IRIS, LiberAI v1/v2, ARUQULA v1-v3.
  - Setup: GPT-5.2 at temperature 0. Corporate examples were synthesised with DeepSeek-V3 and kept only if they returned results on the endpoint. Total LLM cost was under $3.
  - Source: authors' own paper, not the official leaderboard. — [arXiv 2610.13648 HTML](https://arxiv.org/html/2610.13648)
- Confirmation that SPARQL-LLM ranked first among 8 approaches comes from the same team. The team's LinkedIn reports a "Best Award". — [arXiv 2610.13648](https://arxiv.org/abs/2610.13648); [P. Smeros LinkedIn](https://ch.linkedin.com/in/psmeros) (weak: self-reported)
- SPARQL-LLM journal version (ACM TWEB 2026):
  - Up to 59% higher F1 than the second-best challenge system, up to 27x faster, at most $0.01 per question.
  - The v1 preprint (Dec 2025, against the 2025 challenge) claimed +24% F1 and up to 36x faster.
  - DBpedia EN median latency was 3.1 s versus 112.5 s for the 2025 winner.
  - Cost per question: about $0.01 (large), $0.0007 (small), $0.0004 (gpt-oss-120b).
  - Source: [arXiv 2512.14277](https://arxiv.org/abs/2512.14277); [v1 HTML](https://arxiv.org/html/2512.14277v1)
- **2025 winners (conflicting claims):**
  - The SPARQL-LLM paper says ARUQULA won DBpedia EN and Corporate, and mKGQAgent won DBpedia ES. — [SPARQL-LLM](https://arxiv.org/pdf/2512.14277)
  - The mKGQAgent abstract says it "took first place among the other participants" on DBpedia and Corporate benchmarks. — [arXiv 2507.16971](https://arxiv.org/abs/2507.16971v1)
  - AIRI reports 3rd on DBpedia and 5th on Corporate. — [CEUR Vol-4094 paper5](https://ceur-ws.org/Vol-4094/paper5.pdf)
  - Unresolved; the official leaderboard should be checked.
- ARUQULA (INFAI/AKSW) generalizes SPINACH to arbitrary RDF KGs. It uses a ReAct agent with 6 tools: entity, property and class search, entry inspection, property examples, and SPARQL execution. Retrieval is Qdrant hybrid (dense + BM25) plus a Lucene entity index, with GPT-4.1-mini on QLever. It takes about 51 to 66 s and 8 to 11 steps per question. — [arXiv 2510.02200](https://arxiv.org/html/2510.02200v1)
- mKGQAgent is a multilingual multi-agent workflow (planning, entity linking, query refinement) with an "experience pool" of examples for in-context learning. — [arXiv 2507.16971](https://arxiv.org/abs/2507.16971v1)
- Wardenga & Kafer (KIT) put shape constraints (ShEx) into the LLM context; ShEx-augmented prompting reached F1 0.28 (setting unclear from the snippet). — [CEUR Vol-4094 paper1](https://ceur-ws.org/Vol-4094/paper1.pdf) (weak: snippet only)
- **WikiKGQA 2026 Macro QALD-F1 (best per team):**
  - EN with mentions: ASTER (IBM, skill-driven agent) 0.88; AMA-KBQA (multi-agent ReAct, typed MCP tools wrapping SPARQL, answer-convention alignment) 0.87; P3 (TF-IDF example retrieval + execution-guided selection, open-weight LLMs) 0.65; WikiProSP (prompt-based) 0.63.
  - EN without mentions: GRASP/GRISP 0.85; ASTER 0.81; AMA-KBQA 0.79.
  - ES with mentions: P3 0.63.
  - ES without mentions: GRASP/GRISP 0.83.
  - Source: [WikiKGQA overview](https://ceur-ws.org/Vol-4284/intro1.pdf)
- WikiKGQA organizers: "generic baselines based on Claude achieve competitive results with KGQA-specific approaches". Walter & Bast compared GRASP and GRISP with an off-the-shelf Claude Code solution. — [WikiKGQA overview](https://ceur-ws.org/Vol-4284/intro1.pdf)
- GRASP (Walter & Bast, ISWC 2025) is zero-shot and agentic for arbitrary RDF KGs, evaluated on Wikidata and Freebase. — [arXiv 2507.08107](https://arxiv.org/html/2507.08107v2)
- GRISP (2026) uses a fine-tuned small LM to generate a SPARQL skeleton, then a backtracking search fills the IRIs by retrieval and re-ranking under graph constraints. It reportedly scores QALD-10 EM 46.9 / F1 47.6 and LC-QuAD 2.0 EM 73.2 / F1 74.5 with Qwen2.5-7B. — [arXiv 2604.21133](https://arxiv.org/abs/2604.21133) (numbers from a search snippet; unverified against the paper)
- AutoSchema (Zhang & Tsuda, Aug 2026) is a training-free MCP server for live schema grounding: schema discovery, entity search and expansion, and cross-database bridges. It needs no LLM inside. It reports higher factoid accuracy than TogoMCP, with fewer tool calls. — [arXiv 2608.14228](https://arxiv.org/abs/2608.14228)
- EXYGEN (Singh et al., Sep 2026) is a RAG pipeline built on VoID + ShEx + retrieved triples + examples, with predicate-coverage-aware sampling for very large KGs (more than 80x faster metadata generation). It reaches 0.419 EM on SciQA. — [arXiv 2609.11569](https://arxiv.org/abs/2609.11569)
- **Text2Cypher SOTA (CypherBench EX):** Claude-3.5-Sonnet 61.58; GPT-4o 60.18; Qwen2.5-72B 41.87; Llama3.1-70B 38.84; models under 10B below 20%. — [alphaXiv overview of 2412.18702](https://www.alphaxiv.org/overview/2412.18702v2) (secondary summary; older-generation models)

### Inferences
- On a fresh, private KG, the biggest lever was example generation: synthetic question-query pairs, execution-filtered against the endpoint. The agent architecture mattered less. SPARQL-LLM beat the exploration-heavy ARUQULA by about 20 F1 points on corporate, at a fraction of the latency.
- For a FIBO/Ontop VKG, generating and executing a synthetic example bank over your own endpoint is the highest-ROI step.
- Agentic exploration (ARUQULA, GRASP, ASTER) is strongest on huge open KGs without examples (WikiKGQA "without mentions"). The trade-off is latency: about 1 to 2 minutes per question versus about 3 s.
- Frontier general agents (Claude Code) are now competitive with bespoke KGQA systems on Wikidata. Part of that may come from parametric knowledge of Wikidata IDs, which does not transfer to private ontologies.

### Gaps
- There is no independent leaderboard verification of the 2026 scores; all numbers come from the winning team's preprint.
- I found no head-to-head numbers for fine-tuned small models (GRISP) on the corporate KG.
- I found no multi-agent Text2Cypher system with benchmark numbers.

## 3. Graph-query-specific methods

### Takeaway
The converging recipe is:
1. Compact schema context (VoID class/property statistics, plus ShEx/SHACL shapes per class, plus verbalised labels).
2. Retrieval of similar question-query examples.
3. Entity and IRI linking via full-text or hybrid search against the endpoint.
4. A validate-and-repair loop that checks triple patterns against the schema or ontology and executes the query.

Agentic exploration tools cover KGs without metadata. Skeleton-then-fill and fine-tuned small models are the low-cost local alternative. I found no 2025-26 evidence that grammar-constrained decoding is a deciding factor at the top of the leaderboards.

### Cited Findings
- Ontology/schema context and validation in SPARQL-LLM:
  - It pulls subject-class / predicate / object-class and datatype relations from VoID, generating VoID if missing.
  - It summarises each class as a ShEx shape and stores examples using SHACL vocabulary.
  - It embeds questions and classes in a vector DB.
  - Its validator parses the generated query, extracts triple patterns and checks them against the schema, returning errors with alternatives. This usually yields an executable query within up to 3 revisions. — [SPARQL-LLM v1](https://arxiv.org/html/2512.14277v1)
- EXYGEN ablates the KG-derived context. The best configuration combines ShEx schemas, retrieved triples and example pairs. — [arXiv 2609.11569](https://arxiv.org/abs/2609.11569)
- Ontology-based query check (OBQC) plus LLM repair over the data.world insurance KG raised accuracy to 72%, with an additional 8% "I don't know" and a 20% error rate. — [Allemang & Sequeda, arXiv 2405.11706](https://arxiv.org/abs/2405.11706)
- Readable entity names and semantic annotations in the ontology were the dominant accuracy factors across 8 ontology representations, "more significant than model choice or prompt engineering" (21 competency questions, neuroimaging domain, local LLMs). — [Fitch & Kurtz, arXiv 2607.18029](https://arxiv.org/abs/2607.18029) (small study)
- Agentic exploration tools are covered under section 2: ARUQULA's 6 tools [arXiv 2510.02200](https://arxiv.org/html/2510.02200v1); AutoSchema's live-schema MCP [arXiv 2608.14228](https://arxiv.org/abs/2608.14228); AMA-KBQA's typed MCP tools; ASTER's skill-driven steps (exploration, entity/relation linking, construction, result validation). — [WikiKGQA overview](https://ceur-ws.org/Vol-4284/intro1.pdf)
- Skeleton/template: GRISP generates a skeleton with a fine-tuned small LM, then fills IRIs by constrained backtracking search. — [arXiv 2604.21133](https://arxiv.org/abs/2604.21133)
- Execution-guided selection: P3 samples candidates at several temperatures and keeps one that returns at least one result. WikiProSP uses LLM self-review and repair. — [WikiKGQA overview](https://ceur-ws.org/Vol-4284/intro1.pdf)
- Mention annotations (gold entity and relation mentions) help. The same systems score lower without them (ASTER 0.88 to 0.81, AMA-KBQA 0.87 to 0.79). Caveat: the with- and without-mention question sets are disjoint. — [WikiKGQA overview](https://ceur-ws.org/Vol-4284/intro1.pdf)
- Fine-tuned vs prompted:
  - Neo4j found large foundation models best, with fine-tuning promising. — [arXiv 2412.10064](https://arxiv.org/abs/2412.10064)
  - On CypherBench, models under 10B score below 20% EX. — [alphaXiv](https://www.alphaxiv.org/overview/2412.18702v2)
  - EXYGEN (RAG, no fine-tuning) still trails fully fine-tuned approaches on SciQA. — [arXiv 2609.11569](https://arxiv.org/abs/2609.11569)
- Schema size: CypherBench argues that full RDF schemas (Wikidata, Freebase) exceed LLM context. It proposes domain property-graph views via RDF-to-PG conversion. — [arXiv 2412.18702](https://arxiv.org/abs/2412.18702)
- Common Cypher error classes: reversed relation direction, entity-linking mismatch, schema violations. — [alphaXiv](https://www.alphaxiv.org/overview/2412.18702v2)

### Inferences
- For an OWL + Ontop stack, the ontology is the natural source of the VoID/ShEx-style context and of OBQC rules (domain/range, class disjointness, property direction). The R2RML mappings also tell you which classes and properties are actually populated, so the context can be pruned to mapped terms only.
- The SPARQL-LLM validator (triple patterns checked against schema) is cheap to implement with rdflib and fits an offline-by-default platform.

### Gaps
- I found no 2025-26 paper isolating grammar-constrained decoding for SPARQL or Cypher at frontier-model scale.
- I found no controlled study of verbalised ontology versus ShEx versus SHACL as prompt format on the same benchmark, beyond the EXYGEN and Fitch & Kurtz ablations.

## 4. OBDA / VKG + LLM

### Takeaway
Direct evidence is thin. The data.world benchmark is the canonical OBDA-style result: OWL + R2RML over 13 insurance tables, 43 questions, 54% with SPARQL rising to 72% with OBQC. Spider4SPARQL is the large-scale relational-to-KG benchmark. I found no published 2025-26 system that evaluates LLM-generated SPARQL executed specifically through Ontop.

### Cited Findings
- Sequeda, Allemang & Jacob (2023): an enterprise insurance SQL schema (13 tables), 43 questions from simple lookups to analytics, and a KG layer as an OWL ontology plus R2RML mappings. GPT-4 zero-shot scored 16.7% on SQL versus 54.2% on SPARQL over the KG. — [arXiv 2311.07509](https://arxiv.org/pdf/2311.07509)
- Allemang & Sequeda (2024) added OBQC plus LLM repair: 72% accurate, 8% "I don't know". — [arXiv 2405.11706](https://arxiv.org/abs/2405.11706)
- Spider4SPARQL derives 166 KGs/ontologies from Spider DBs; LLMs and KGQA systems reach at most 45% EX. — [arXiv 2309.16248](https://arxiv.org/abs/2309.16248)
- Ontop translates SPARQL over the VKG into SQL via R2RML/OBDA mappings, without materialising the data. — [Ontop guide](https://ontop-vkg.org/guide/)
- A domain-KG failure mode: LLMs write correct queries for generic questions but fail on domain KGs because they do not know the ontology vocabulary or schema. — [arXiv 2502.01298](https://arxiv.org/pdf/2502.01298)
- LLM-assisted mapping construction for ontology-based data integration (LAMP, 2025) is a related line of work. — [CEUR Vol-4245 paper9](https://ceur-ws.org/Vol-4245/paper9.pdf) (snippet only)

### Inferences
- In an Ontop setup, accuracy depends on two layers: the LLM writing correct SPARQL, and the mappings covering the query. Unmapped properties return empty results, which a naive execution-guided "non-empty result" filter would treat as wrong. Example banks should therefore be generated over the mapped vocabulary.
- I found no evidence that Ontop's SPARQL coverage limits (some SPARQL 1.1 features, property paths) have been studied with LLM-generated queries; this should be tested locally.

### Gaps
- I found no 2025-26 benchmark or system paper reporting NL->SPARQL accuracy through Ontop.
- I found no FIBO-specific NL->SPARQL benchmark.

## 5. SPARQL vs SQL generation accuracy over the same data

### Takeaway
The evidence consistently favours an ontology/KG layer, but it is weak in volume:
- data.world 2023: 16.7% for SQL vs 54.2% for SPARQL, 43 questions, a vendor-affiliated study.
- Fitch & Kurtz 2026: OWL gives a "substantial advantage" over auto-generated SQL DDL, 21 questions.

The gain seems to come from semantics in context (readable names, annotations, explicit relationships) more than from the query language itself. Zero-shot SPARQL without examples can be much worse than SQL.

### Cited Findings
- On the same insurance data, SQL scored 16.7% average execution accuracy and SPARQL over the OWL/R2RML KG scored 54.2% (about 3x). — [arXiv 2311.07509](https://arxiv.org/pdf/2311.07509)
- An OWL ontology versus an SQL schema auto-generated from it, with the same competency questions on both backends: OWL structure gives a substantial advantage, and names and annotations dominate. — [arXiv 2607.18029](https://arxiv.org/abs/2607.18029)
- A blog comparison found SPARQL zero-shot accuracy below 4%, versus much higher for SQL, with few-shot examples closing much of the gap. — [Towards Data Science](https://towardsdatascience.com/can-llms-talk-sql-sparql-cypher-and-mongodb-query-language-mql-equally-well-a478f64cc769/) (weak: blog, different benchmark)
- CypherBench argues that RDF's large schemas are a disadvantage for LLMs and favours compact property-graph views. — [arXiv 2412.18702](https://arxiv.org/abs/2412.18702)

### Inferences
- The SPARQL-over-KG advantage in the data.world study conflates two things: the language and the added ontology semantics (business-level classes and relations, versus 13 normalised tables). A fair test would give the SQL generator equivalent semantic annotations, for example a semantic layer or view definitions. No study found does this.
- For FIBO plus Ontop, expect SPARQL to win when the ontology context is compact and well-labelled. Expect it to lose if raw FIBO, which is very large, is dumped into the prompt without pruning to mapped terms.

### Gaps
- I found no large-scale, controlled SPARQL-vs-SQL comparison on identical data with modern (2026) models and an equal semantic context.
- I found no 2025 or later replication of the data.world benchmark with newer models.
