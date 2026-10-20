# Text-to-SQL Benchmarks, Leaderboards and State of the Art (as of 19 October 2026)

Scope: the Text-to-SQL benchmarks that matter in 2026, current top results, the gap to enterprise reality, data/licence availability, and how reasoning models and RL changed the numbers from 2024 to 2026. All leaderboard pages were fetched on 2026-10-19.

Evidence labels:
- **[PR]** peer-reviewed paper
- **[arXiv]** preprint
- **[LB]** leaderboard entry only: self-reported, usually without a paper
- **[Vendor]** vendor blog
- **[2nd]** secondary source

## Q1. Benchmark inventory and current top results

### Takeaway
Spider 1.0 is saturated: about 91% EX since 2023–24. BIRD is close to saturated: top test EX is 82.95% (GrainSQL, 2026-09-26, leaderboard-only) against 92.96% for humans. About half of BIRD's gold labels contain errors, so rankings at the top are unreliable.

The frontier has moved to Spider 2.0 and the BIRD family:
- **Spider 2.0-Snow:** vendor agents claim 90–97%. These scores are suspect because the gold answers and gold tables are public.
- **Spider 2.0-Lite:** top score about 76%.
- **Spider 2.0-DBT:** top score about 66%.
- **LiveSQLBench:** best 48% success rate.
- **BIRD-Interact:** best 17%.

### Cited Findings

**Spider 1.0** (Yale, 2018). Cross-domain, about 200 small SQLite databases. Metrics: EX and exact match.
- MiniSeek (Seek AI) is reported at 91.2% test EX [Vendor] — [Seek AI blog](https://seek.ai/blog/miniseek-first-model-to-surpass-90-accuracy-on-spider-test-benchmark). An Awesome-Text2SQL commit records 91.6 instead, so the figure is in conflict — [commit](https://cdn05042023.gitlink.org.cn/dnrops/Awesome-Text2SQL/commit/d2106fee85c53cbebd9fd25875db2924c311b190).
- DAIL-SQL with GPT-4 reached 86.2% EX, or 86.6% with self-consistency (September 2023) [PR, VLDB 2024] — [arXiv 2308.15363](https://arxiv.org/abs/2308.15363).
- The Spider 2.0 paper cites 91.2% on Spider 1.0 as the state reached by late 2024 — [arXiv 2411.07763](https://arxiv.org/abs/2411.07763).

**BIRD** (HKU + Alibaba, NeurIPS 2023) — [bird-bench.github.io](https://bird-bench.github.io/)
- Size: 12,751 question–SQL pairs over 95 databases (33.4 GB) in 37+ professional domains. Questions come with external-knowledge "evidence".
- Metrics: EX and R-VES (reward-based valid efficiency score).
- Licence: CC BY-SA 4.0 since 2024-04-27.
- Human performance: 92.96 EX, 83.26 R-VES.
- Top 10 by test EX (fetched 2026-10-19):

| # | System (org) | Test EX | R-VES | Date | Evidence |
|---|---|---|---|---|---|
| 1 | GrainSQL (Purdue, S. Chaudhry) | 82.95 | 84.10 | 2026-09-26 | [LB], no paper |
| 2 | DataGallery-Text2SQL (Huawei 2012 Labs) | 82.39 | 77.64 | 2026-09-07 | [LB] |
| 3 | SiriusAI-SQL (Tencent) | 82.28 | 74.76 | 2026-08-22 | [LB] |
| 4 | AskData + GPT-4o (AT&T CDO) | 81.95 | 76.31 | 2025-12-16 | [arXiv 2505.19988](https://arxiv.org/abs/2505.19988) |
| 5 | Agentar-Scale-SQL (Ant Group) | 81.67 | 77.00 | 2025-09-25 | [arXiv 2509.24403](https://arxiv.org/abs/2509.24403) |
| 6 | Sber Text2SQL (SberData) | 81.33 | 73.75 | 2026-06-19 | [LB] |
| 7 | Xiaomi Text2SQL | 80.83 | 73.93 | 2026-05-27 | [LB] |
| 8 | RAS (Adya AI) | 79.82 | 74.95 | 2026-08-19 | [LB] |
| 9 | DeepEye (HKUST-GZ) | 79.09 | 69.85 | 2026-07-14 | [arXiv 2603.28889](https://arxiv.org/abs/2603.28889) |
| 10 | MarkovSQL (anonymous) | 78.70 | 74.68 | 2026-07-04 | [LB] |

- **Agentar-Scale-SQL** — [arXiv 2509.24403](https://arxiv.org/abs/2509.24403); [HF model card](https://huggingface.co/antgroup/Agentar-Scale-SQL-Generation-32B)
  - Scores: test EX 81.67, dev EX 74.90, R-VES 77.00.
  - Method: three kinds of test-time scaling.
    - Internal: RL-trained reasoning.
    - Sequential: iterative refinement.
    - Parallel: diverse candidate synthesis followed by tournament selection.
  - The generator was fine-tuned from OmniSQL-32B with GRPO.
  - The GitHub roadmap suggests code and models may not be fully released — [GitHub](https://github.com/antgroup/Agentar-Scale-SQL).
- The Agentar model card's comparison table gives test EX for earlier systems: CHASE-SQL + Gemini 76.02, XiYan-SQL 75.63, AskData + GPT-4o 80.88 (at that time) — [HF model card](https://huggingface.co/antgroup/Agentar-Scale-SQL-Generation-32B).
- **BIRD Mini-Dev:** 500 examples in SQLite, MySQL and PostgreSQL; the three dialects were added in July 2025. The top entry is Jitto Build at 75.60 on SQLite — [bird-bench.github.io](https://bird-bench.github.io/).
- **BIRD 2.0** is under development and targets "complex real-world industrial data" — [bird-bench.github.io](https://bird-bench.github.io/).

**Spider 2.0** (XLang/HKU, ICLR 2025 oral). Enterprise workflows on BigQuery, Snowflake, SQLite, DuckDB and dbt; databases often have more than 1,000 columns — [arXiv 2411.07763](https://arxiv.org/abs/2411.07763)
- The original release had 632 tasks. An o1-preview code agent solved 21.3%, against 91.2% on Spider 1.0 and 73.0% on BIRD — [arXiv 2411.07763](https://arxiv.org/abs/2411.07763).
- Current settings — [spider2-sql.github.io](https://spider2-sql.github.io/):
  - Snow: 547 tasks, Snowflake.
  - Lite: 547 tasks (BigQuery 214, Snowflake 198, SQLite 135).
  - DBT: 68 tasks, DuckDB/dbt.
  - The original agentic "Spider2" setting was removed on 2025-05-22.
- Leaderboard leaders, fetched 2026-10-19. **The page gives no dates per entry**, and all entries are [LB] — [spider2-sql.github.io](https://spider2-sql.github.io/).

  **Snow:**

  | System (org) | Score |
  |---|---|
  | Genloop Sentinel Agent v2 Pro | 96.70 |
  | Native mini (usenative.ai) | 96.53 |
  | QUVI-3 + Gemini-3-pro-preview (DAQUV) | 94.15 |
  | TCDataAgent-SQL (Tencent Cloud) | 93.97 |
  | Prism Swarm + Claude-Sonnet-4.5 (Paytm) | 90.49 |
  | QUVI-3 + Claude-Opus-4.6 | 86.28 |
  | AT&T Ask Data with RelationalAI knowledge graph | 86.28 |

  **Lite:**

  | System (org) | Score |
  |---|---|
  | Tianqiong Data Agent + GLM 5.2 (Tencent) | 76.23 |
  | DecisionX Agent | 74.95 |
  | ktx (Kaelio) | 73.67 |
  | DivSkill-SQL (Snowflake AI Research x UCSD) | 73.13 |
  | SOMA-SQL (Oracle OCI) | 72.02 |
  | Databao (JetBrains) | 69.65 |
  | QUVI-2.3 + Claude-Opus-4.5 | 65.81 |

  **DBT:**

  | System (org) | Score |
  |---|---|
  | SignalPilot | 65.6 |
  | Databao (JetBrains) | 60.29 |
  | Shadowfax + GPT-5 | 41.18 |
  | Spider-Agent-Extended + GPT-5 | 39.71 |
  | USTC-KCIL + GPT-5.4 | 39.71 |
  | C3 AI DIA | 37.50 |

- Contamination warnings from the maintainers — [spider2-sql.github.io](https://spider2-sql.github.io/):
  - 2024-12-24: all examples and gold answers were released for self-evaluation.
  - 2025-01-07: users were told not to fine-tune on the released gold SQL.
  - 2025-04-20: ground-truth tables were released; runs that use them must be labelled "oracle-table".

**BIRD family** (HKU BIRD team + Google Cloud): contamination-resistant and interactive benchmarks
- **LiveSQLBench** covers BI and CRUD tasks — [livesqlbench.ai](https://livesqlbench.ai/)
  - Releases:
    - Base-Lite (2025-05-28): 270 tasks over 18 PostgreSQL databases; a SQLite version followed on 2025-07-28.
    - Base-Full v1 (2025-09-04): 600 tasks over 22 databases, with knowledge-base documents.
    - Large-v1 (2026-03-02): 480 tasks over 18 industrial databases of about 1,000 columns each, with prompts averaging about 84K tokens.
    - Version 1.5 is "coming soon"; 2.0 is in development.
  - Metric: success rate (SR). SELECT queries are checked by comparing results with the gold query; DML/DDL is checked with test cases.
  - Contamination design:
    - Databases are built from regularly updated CSV sources.
    - Each release's hidden test set becomes the next release's open set.
    - Business rules change between releases.
- LiveSQLBench top overall results [LB] — [livesqlbench.ai](https://livesqlbench.ai/):

  | System | SR | Date |
  |---|---|---|
  | C3 AI DIA | 48.00 | 2026-05-29 |
  | Jitto Build (Claude Opus 5.5, high) | 41.33 | 2026-09-26 |
  | MiniMax M3 (Claude Code) | 40.17 | 2026-06-01 |
  | Claude Opus 4.6 (OpenHands CLI) | 38.00 | 2026-03-27 |
  | Gemini 3.1 Pro | 36.50 | 2026-04-26 |

  The page's "Last Updated" date (2026-03-02) is earlier than several of these entries.
- **BIRD-INTERACT** [PR, ICLR 2026 oral] — [arXiv 2510.05318](https://arxiv.org/abs/2510.05318); [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/496b549556509bbb9770bf9d335c5800-Abstract-Conference.html)
  - Built on LiveSQLBench. Each database comes with a hierarchical knowledge base, metadata and a function-driven user simulator.
  - Two settings:
    - c-Interact: a fixed conversational protocol.
    - a-Interact: agentic; the model decides when to ask the user or explore the database.
  - FULL has 600 tasks, which unfold into up to 11,796 interactions. LITE has 300 tasks.
  - GPT-5 solved 8.67% in c-Interact and 17.00% in a-Interact.
  - A SQLite "Mini-Interact" version has been released — [bird-bench.github.io](https://bird-bench.github.io/).
- **BIRD-Critic / SWE-SQL** asks the model to debug real user SQL issues. Metric: SR — [bird-critic.github.io](https://bird-critic.github.io/)
  - Variants:

    | Variant | Tasks | Dialects |
    |---|---|---|
    | Flash | 200 | PostgreSQL |
    | Open | 570 | PostgreSQL, MySQL, SQL Server, Oracle |
    | PostgreSQL | 530 | PostgreSQL |
    | BigQuery | 200 | BigQuery |
    | SQLite | 500 | SQLite (released 2026-03-23, with RL-trained BIRD-Talon-14B/7B and BIRD-Zeno-7B) |

  - Human performance is about 80% on Flash and 78.87% on the single-dialect sets.
  - Top Open scores are o1-preview 35.5 and DeepSeek-R1 32.0. These entries date from 2024–25, so the leaderboard looks stale.

**Enterprise and domain benchmarks**
- **BEAVER** (MIT) — [arXiv 2409.02038](https://arxiv.org/abs/2409.02038)
  - Built from three anonymised enterprise data warehouses. The SQL comes from real query logs and production reports.
  - Off-the-shelf LLMs reach about 0% end-to-end EX, even with prompt engineering and RAG.
  - A review describes two warehouses — DW with 99 tables / 1,544 columns and NW with 366 tables / 2,708 columns — and 203 questions [2nd] — [Moonlight review](https://www.themoonlight.io/review/beaver-an-enterprise-benchmark-for-text-to-sql). The paper says three warehouses, so the warehouse count is in conflict.
  - One example gold query is over 100 lines long, with 6 joins and 3 levels of nesting.
  - BenchPress [PR, CIDR 2026] adds detail — [arXiv 2510.13853](https://arxiv.org/abs/2510.13853):
    - BEAVER's query logs span more than 300 schemas and about 4,000 queries.
    - BEAVER-DW queries average about 99.8 tokens and 2.05 nesting levels, far above Spider.
- **EntSQL** (HKUST-GZ + Alibaba, June 2026) [arXiv] — [arXiv 2606.03363](https://arxiv.org/abs/2606.03363)
  - 1,066 aligned Chinese–English examples in five business domains: finance, treasury, business management, party building and HR.
  - Most examples need private business knowledge.
  - The best system reaches 15.9% on English inputs, even when the long-form documents are provided.
- **Falcon** (Ant Group, 2025-10-23) [arXiv] — [arXiv 2510.24762](https://arxiv.org/abs/2510.24762)
  - 600 Chinese questions over 28 databases, in the MaxCompute/Hive dialect.
  - 77% need multi-table reasoning, and more than half touch over 4 tables.
  - State-of-the-art LLMs, including DeepSeek, reach at most 50%.
- **EHRSQL** [PR, NeurIPS 2022 Datasets & Benchmarks track] — [arXiv 2301.07695](https://arxiv.org/abs/2301.07695)
  - Questions were collected from 222 hospital staff and linked to the MIMIC-III and eICU databases.
  - Includes time expressions and unanswerable questions.
- **Archer** [PR, EACL 2024] — [EACL 2024](https://virtual2024.eacl.org/paper_19-Oral.html)
  - 1,042 English and 1,042 Chinese questions with 521 SQL queries over 20 Spider databases.
  - Targets arithmetic, commonsense and hypothetical reasoning.
  - A high-ranked Spider model scored 6.73% EX on the Archer test set.

### Inferences
- BIRD test EX rose from about 73% (end of 2024, as cited by Spider 2.0) to 81.67–82.95% by late 2026: about 1–2 points per year at the top. Given roughly 50% gold-label noise (Q2), gaps of less than about 3 points between top entries are probably not meaningful.
- Spider 2.0-Snow scores above 90% from vendor agents are not comparable with the paper's 21.3%. Likely reasons:
  - the task set has changed;
  - gold answers and tables are public, which allows overfitting or leakage;
  - the agent harnesses are heavily engineered.
- Spider 2.0-Lite (about 76%) and DBT (about 66%) are probably more honest signals, though both are still leaderboard-only.
- A suggested practitioner suite for 2026:
  - BIRD dev or Mini-Dev, for sanity checks and regression only;
  - Spider 2.0-Lite or DBT, for warehouse-scale agentic work;
  - LiveSQLBench, for contamination-resistant tracking;
  - BIRD-Interact, for clarification behaviour;
  - a private BEAVER-style set built from your own query logs, as the deciding test.

### Gaps
- The Spider 2.0 leaderboard shows no date per entry, so its scores can only be dated "as listed on 2026-10-19".
- No 2026 data was gathered on Dr.Spider (robustness perturbations), ScienceBenchmark, or finance-specific benchmarks such as BULL or FinSQL; these were outside the search budget.
- EHRSQL's exact current size and its shared-task results were not verified.
- 2026 peer-reviewed numbers for successors of CHASE-SQL and XiYan-SQL were not verified beyond the Agentar model-card table.

## Q2. Known flaws: annotation noise, contamination and leaderboard hygiene

### Takeaway
A 2026 audit found annotation-error rates of 52.8% on BIRD Mini-Dev and 62.8% on Spider 2.0-Snow, judged by experts. Correcting the labels moves BIRD rankings by up to 9 places. Add public gold for Spider 2.0 and unregulated decoding settings, and top leaderboard numbers become weak evidence.

### Cited Findings
- **Jin, Choi, Zhu and Kang (UIUC)** [PR, CIDR 2026 and PVLDB vol. 19] — [arXiv 2601.08778](https://arxiv.org/abs/2601.08778) (v3, 2026-01-19); [CIDR 2026](https://vldb.org/cidrdb/2026/text-to-sql-benchmarks-are-broken-an-in-depth-analysis-of-annotation-errors.html); [PVLDB 19](https://vldb.org/pvldb/volumes/19/paper/Pervasive%20Annotation%20Errors%20Break%20Text-to-SQL%20Benchmarks%20and%20Leaderboards)
  - Annotation-error rates: BIRD Mini-Dev 52.8% (previous estimate: 36.1%); Spider 2.0-Snow 62.8%, measured on the subset with open gold.
  - 16 open-source BIRD agents were re-evaluated on a corrected BIRD Dev subset:
    - relative performance changed by −7% to +31%;
    - ranks moved by −9 to +9;
    - Spearman correlation with the full-Dev ranking was 0.85 on the uncorrected subset but only 0.32 on the corrected subset (p=0.23).
  - The CIDR version reports two figures that differ from the arXiv version:
    - CHESS rose from 62% to 81%, moving from 4th to 1st among the 5 agents re-evaluated there;
    - the Spider 2.0-Snow error rate is given as 66.1% over 121 problems.
  - Error categories:
    - SQL does not match the question's logic;
    - SQL does not match the schema;
    - domain-knowledge errors;
    - ambiguous questions.
- About 49% of BIRD's finance-domain items reportedly contain errors [2nd, unverified] — [beancount.io research log](https://beancount.io/bean-labs/research-logs/2026/06/06/bird-benchmark-text-to-sql-real-database-gap).
- Spider 2.0 released its gold SQL and answers on 2024-12-24 and its gold tables on 2025-04-20, and warned against fine-tuning on them — [spider2-sql.github.io](https://spider2-sql.github.io/).
- The BIRD leaderboard has no rule on greedy versus multi-sample decoding, so entries are not comparable — Arctic-Text2SQL-R1 authors, [arXiv 2505.20315](https://arxiv.org/abs/2505.20315).
- Most entries in the BIRD top 10 list their model as "UNK" and have no paper — [bird-bench.github.io](https://bird-bench.github.io/).

### Inferences
- When reporting BIRD results, use a corrected subset, or execution checks plus manual review, rather than raw EX.
- Treat any vendor Spider 2.0-Snow score above 90% as unverified.

### Gaps
- No independent audit of the Spider 2.0-Lite or DBT gold labels, or of LiveSQLBench, was found.

## Q3. Gap between public SOTA and enterprise-schema performance

### Takeaway
The same class of systems that scores about 80% on BIRD and 91% on Spider 1.0 scores much lower elsewhere:
- about 15–50% on enterprise-knowledge benchmarks (EntSQL, Falcon, LiveSQLBench-Large);
- about 0% on BEAVER's real warehouses.

The main drivers are not SQL syntax. They are:
- schema scale (1,000+ columns);
- private business knowledge;
- warehouse dialects;
- multi-step workflows;
- ambiguity.

### Cited Findings
- **Spider 2.0:** an o1-preview agent scored 21.3%, against 91.2% on Spider 1.0 and 73.0% on BIRD. Databases often have more than 1,000 columns — [arXiv 2411.07763](https://arxiv.org/abs/2411.07763).
- **BEAVER:** about 0% EX on real enterprise warehouses — [arXiv 2409.02038](https://arxiv.org/abs/2409.02038).
- **EntSQL:** the best system reaches 15.9%, even with the documents provided — [arXiv 2606.03363](https://arxiv.org/abs/2606.03363).
- **Falcon:** at most 50%. The main error sources are schema linking and mapping colloquial language to exact aggregations, predicates and time windows — [arXiv 2510.24762](https://arxiv.org/abs/2510.24762).
- **LiveSQLBench:** best overall SR is 48.00 (C3 AI DIA, 2026-05-29). The Large-v1 split uses databases of about 1,000 columns and prompts of about 84K tokens — [livesqlbench.ai](https://livesqlbench.ai/).
- **BIRD-Interact:** GPT-5 reaches 17.00% in the agentic a-Interact setting — [arXiv 2510.05318](https://arxiv.org/abs/2510.05318).
- **Original BIRD paper:** GPT-4 scored 54.89% EX with the curated evidence and 34.88% without it [2nd citation of the BIRD paper] — [beancount.io](https://beancount.io/bean-labs/research-logs/2026/06/06/bird-benchmark-text-to-sql-real-database-gap).
- GPT-4o scores 86.6% on Spider 1.0 versus 10.1% on Spider 2.0 [Vendor, weak] — [particula.tech](https://particula.tech/blog/text-to-sql-accuracy-benchmarks-semantic-layer).
- A 2026 preprint, GROUND, frames enterprise failures as missing business-metric semantics, addressed through governed semantic definitions — [arXiv 2608.26157](https://arxiv.org/abs/2608.26157).
- On Spider 2.0-Snow, "Ask Data with Relational Knowledge Graph" (AT&T with RelationalAI) scores 86.28 [LB]. It shows ontology/knowledge-graph grounding among the top entries — [spider2-sql.github.io](https://spider2-sql.github.io/).

### Inferences
- The gap is mainly about knowledge and context: business rules, metric definitions and schema semantics. Three findings point this way:
  - BIRD's roughly 20-point effect from providing evidence;
  - EntSQL's design around private knowledge;
  - knowledge-graph and semantic-layer entries near the top of leaderboards.

  This supports a semantic-layer or ontology approach, which is relevant to SIP.
- Expected performance on an unseen enterprise warehouse:
  - without curated semantics, somewhere between BEAVER and EntSQL (roughly 0–20%);
  - with a curated knowledge layer plus an agentic loop, the LiveSQLBench and Spider 2.0-Lite range (roughly 50–75%) is the upper reference.

### Gaps
- No peer-reviewed 2026 study was found that measures one top BIRD system directly on a private enterprise warehouse.

## Q4. Execution-ready data (gold SQL plus databases) and licences

### Takeaway
These benchmarks ship databases or environments for execution-based evaluation:
- BIRD (CC BY-SA 4.0);
- BIRD-Interact (the arXiv HTML is marked CC BY-SA 4.0);
- Spider 2.0 (gold SQL, answers and tables released);
- LiveSQLBench (open development set, hidden test set);
- BIRD-Critic.

Several landing pages state no licence.

### Cited Findings
- **BIRD:** 95 databases (33.4 GB) plus gold SQL; CC BY-SA 4.0 since 2024-04-27. Mini-Dev comes in SQLite, MySQL and PostgreSQL — [bird-bench.github.io](https://bird-bench.github.io/).
- **Spider 2.0:** — [spider2-sql.github.io](https://spider2-sql.github.io/)
  - Gold answers and examples were released 2024-12-24; gold tables 2025-04-20.
  - Snow needs Snowflake hosting and credentials. Part of Lite needs BigQuery credentials.
  - The landing page states no licence.
- **LiveSQLBench:** open development set plus hidden test set. Databases are available in PostgreSQL and SQLite. The site states no licence — [livesqlbench.ai](https://livesqlbench.ai/).
- **BIRD-INTERACT:** the arXiv HTML is marked CC BY-SA 4.0, which may cover the paper rather than the data — [arXiv HTML v3](https://arxiv.org/html/2510.05318v3).
- **BIRD-Critic:** execution environment covering PostgreSQL, MySQL, SQL Server, Oracle, BigQuery and SQLite. The page shows no licence — [bird-critic.github.io](https://bird-critic.github.io/).
- **EHRSQL:** built on MIMIC-III and eICU, which require PhysioNet credentialed access — [arXiv 2301.07695](https://arxiv.org/abs/2301.07695); [GitHub glee4810/EHRSQL](https://github.com/glee4810/EHRSQL).
- **BEAVER:** built from anonymised real warehouses — [arXiv 2409.02038](https://arxiv.org/abs/2409.02038).

### Inferences
- For SIP's Fuseki-to-SQL/SPARQL work, the most practical execution-ready corpora are the BIRD SQLite databases and the LiveSQLBench PostgreSQL databases. Spider 2.0-Snow and the BigQuery tasks need cloud accounts.

### Gaps
- The licence texts in the GitHub repositories were not fetched: Spider 2.0, LiveSQLBench, BIRD-Critic, BEAVER, Archer, SParC and CoSQL. Verify them before redistributing anything.
- SParC and CoSQL (multi-turn, Yale, 2019) were not researched in this pass. Unverified background knowledge says their leaderboards have been essentially inactive since about 2023. BIRD-Interact is the active multi-turn successor.

## Q5. How much did reasoning models and RL move the numbers, 2024–2026?

### Takeaway
Three shifts:
- **Single models:** reinforcement learning with execution rewards (GRPO) on open 7–32B models pushed BIRD test EX above 70%. These models start from large synthetic fine-tuning corpora such as OmniSQL's SynSQL-2.5M. Best result: Arctic-Text2SQL-R1-32B at 71.83%.
- **Full systems:** RL-trained generators combined with test-time scaling and candidate selection reached about 82%.
- **Agentic warehouse tasks:** reasoning-model agents moved Spider 2.0 from about 21% (o1-preview, late 2024) to about 76% on Lite (2026).

Interactive and contamination-resistant tasks are still below 50%.

### Cited Findings
- **OmniSQL** [arXiv; 2025-03-04, revised 2025-07-13] — [arXiv 2503.02240](https://arxiv.org/abs/2503.02240); [HF model](https://huggingface.co/seeklhy/OmniSQL-32B)
  - Training data, SynSQL-2.5M: 2,544,390 samples with chain-of-thought over 16,583 synthetic databases.
  - 7B, 14B and 32B models claim to match or beat GPT-4o and DeepSeek-V3 across 9 datasets.
  - A later evaluation lists OmniSQL at 66.75 on the original BIRD dev set — [arXiv 2604.27261](https://arxiv.org/abs/2604.27261).
- **Arctic-Text2SQL-R1** (Snowflake) [PR, ACL Findings 2026] — [arXiv 2505.20315](https://arxiv.org/abs/2505.20315); [ACL Anthology](https://aclanthology.org/2026.findings-acl.1345/); [Snowflake blog](https://www.snowflake.com/en/blog/engineering/arctic-text2sql-r1-sql-generation-benchmark/)
  - GRPO with a reward based only on execution correctness, starting from OmniSQL checkpoints.
  - The 32B model reaches 71.83% BIRD test EX as a single model with greedy decoding, 2.8 points above XiYan-32B.
  - The 14B and 32B models both exceed 70%. The 7B model matches ExCoT-70B.
- **Reasoning-SQL** (Google) [PR, COLM 2025] — [Google Research](https://research.google/pubs/reasoning-sql-reinforcement-learning-with-partial-rewards-for-reasoning-enhanced-text-to-sql/)
  - GRPO with partial rewards for schema linking, AI feedback, n-gram overlap and syntax.
  - The 14B model beats o3-mini by 4% and Gemini-1.5-Pro-002 by 3% on BIRD.
- **Reward-SQL:** a GRPO-aligned Qwen2.5-Coder-7B reaches 68.9% on BIRD dev [2nd review] — [Moonlight review](https://www.themoonlight.io/fr/review/reward-sql-boosting-text-to-sql-via-stepwise-reasoning-and-process-supervised-rewards).
- **R³-SQL:** on BIRD dev, using OmniSQL-7B candidates, CHASE-SQL-style selection scores 68.38, XiYan-SQL 68.06 and R³-SQL 71.83 — [arXiv 2604.25325](https://arxiv.org/abs/2604.25325).
- **Agentar-Scale-SQL:** an RL (GRPO) generator plus test-time scaling reaches 81.67 test EX, about 5.6 points above CHASE-SQL + Gemini (76.02) — [arXiv 2509.24403](https://arxiv.org/abs/2509.24403); [HF card](https://huggingface.co/antgroup/Agentar-Scale-SQL-Generation-32B).
- **BIRD-Critic:** RL-trained BIRD-Talon-14B/7B and BIRD-Zeno-7B were released with the SQLite set on 2026-03-23 — [bird-bench.github.io](https://bird-bench.github.io/).
- **Frontier reasoning models on agentic benchmarks** [LB] — [livesqlbench.ai](https://livesqlbench.ai/); [spider2-sql.github.io](https://spider2-sql.github.io/)
  - LiveSQLBench: they cluster at 36–41% SR — Claude Opus 5.5 inside Jitto Build 41.33, Claude Opus 4.6 38.00, Gemini 3.1 Pro 36.50.
  - Spider 2.0-DBT: GPT-5 and GPT-5.4 agents score about 35–41%.

### Inferences
- **BIRD:** RL closed the open-versus-closed gap. Open 7–32B models now match or beat the GPT-4o pipelines of 2024. Full-system SOTA, however, gained only about 6–9 points over 2024–26, consistent with a ceiling set by label noise (Q2).
- **Agentic warehouse benchmarks:** the biggest movement came from reasoning models plus agent harnesses (tool use, schema exploration, self-verification). Spider 2.0-Lite went from about 21% to about 76%, subject to the comparability caveats in Q1 and Q2.
- **Interactive and contamination-resistant benchmarks:** reasoning models have not yet closed the gap (BIRD-Interact 17%, LiveSQLBench 48%). These are the right targets for 2026–27.

### Gaps
- No clean same-harness ablation of reasoning versus non-reasoning models on Spider 2.0 or LiveSQLBench was found.
- The exact BIRD test scores reported in the original Reasoning-SQL and CHASE-SQL papers were not verified within the search budget.
