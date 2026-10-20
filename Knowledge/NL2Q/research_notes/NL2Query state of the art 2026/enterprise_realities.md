# Enterprise realities of NL-to-query systems (as of 19 Oct 2026)

Evidence-quality labels used below: **[vendor]** = published by a company selling the approach; **[vendor-competitor]** = a vendor measuring a rival; **[practitioner]** = in-house engineering team reporting its own internal system (no product to sell, but self-reported); **[academic]** = peer-reviewed or arXiv preprint without an obvious commercial interest; **[secondary]** = aggregator or commentary.

## Q1. Semantic layers vs ontology/KG approaches: published accuracy numbers and evidence quality

### Takeaway
Every head-to-head number in this space comes from one small benchmark family: data.world's ACME/OMG insurance dataset, with 11-43 questions. Nearly all of it is vendor-run. The consistent signal is that a governed semantic artefact (an ontology+mappings, a MetricFlow/LookML/Cortex semantic model, or even a 4 KB markdown description) lifts accuracy by roughly 17-40 points over raw schema. Deterministic compilation from that artefact (semantic layer APIs, semantic path compilation) mainly changes the *failure mode*: errors and refusals replace plausible wrong numbers. No independent study shows ontologies beating semantic layers, or the reverse, on accuracy.

### Cited Findings
**Ontology / KG side**
- data.world (Sequeda, Allemang, Jacob; Nov 2023) built an enterprise insurance benchmark on the OMG P&C model. Zero-shot GPT-4 scored 16% when querying SQL directly and 54% when querying a KG representation (ontology + R2RML-style mappings) **[vendor]**. The press release called this "3x". — [arXiv 2311.07509](https://arxiv.org/abs/2311.07509); [data.world press release, Dec 2023](https://data.world/company/press-room/new-data-world-report-finds-a-technique-for-making-llms-3x-more-accurate-in-answering-business-questions/)
- Allemang & Sequeda (20 May 2024) added an Ontology-based Query Check (OBQC), which flags SPARQL that is inconsistent with the ontology's domain/range, followed by an LLM repair loop. Results: 72% accurate, a further 8% "I don't know", and a 20% error rate **[vendor]**. For an FIBO/Ontop design this is the most directly relevant result, because it puts the ontology to work as a *validator* and an *abstention trigger*, not only as context. — [arXiv 2405.11706](https://arxiv.org/abs/2405.11706)
- Semantic path compilation (SPC), Yi Ai, arXiv 2608.16663 (17 Aug 2026). The LLM makes only bounded choices among governed semantic options; code then does graph traversal, role predicates, grain lowering, SQL construction and checks. On ACME insurance (38 adjudicated questions × 3 runs), SPC was correct on all runs for 37/38 questions (97.4%), against 21/38 (55.3%) for direct DDL→SQL. McNemar p≈3×10⁻⁵. SPC had one refusal and zero "wrong-but-executed" runs; the baseline had 29 wrong runs plus 7 coincidental data matches. The author caveats this as a systems claim, not a causal one, because SPC gets governed artefacts the baseline lacks. The affiliation is not stated on the abstract page, and a company blog promotes SPC, so treat it as **[vendor-adjacent preprint]**. — [arXiv 2608.16663](https://arxiv.org/abs/2608.16663)
- ATHENA++ (IBM, PVLDB vol. 13, 2020) is a pre-LLM system that combines an ontology with linguistic patterns to generate nested SQL. It scored 88.33% on FIBEN (300 NL queries, 170 of them nested, over a FIBO/FRO-grounded schema) and 78.89% on Spider **[academic/industrial research]**. FIBEN is a FIBO-grounded benchmark that a FIBO practitioner can reuse. — [ATHENA++ PVLDB paper](https://www.vldb.org/pvldb/vol13/p2747-sen.pdf); [FIBEN benchmark repo](https://github.com/IBM/fiben-benchmark); [IBM Research page](https://research.ibm.com/publications/athena-natural-language-querying-for-complex-nested-sql-queries)
- Timbr ("SQL knowledge graph"/ontology semantic layer) publishes only marketing claims, with no benchmark numbers **[vendor]**. — [Timbr blog](https://timbr.ai/why-enterprise-llms-need-sql-knowledge-graphs-for-accurate-nl2sql/)
- Stardog Voicebox is marketed as "100% hallucination-free" (Safety RAG, Sept 2025). The mechanism is that answers come only from KG queries, with the LLM restricted to translating the question. No independent benchmark was found. Competitor Atlan notes that Voicebox docs concede the external-LLM agent "may contain hallucinations", so the guarantee in practice amounts to provenance labelling **[vendor / vendor-competitor]**. — [Stardog news](https://www.stardog.com/news/stardogs-hallucination-free-answer-engine-brings-ai-insights-to-high-stakes-industries/); [VentureBeat](https://venturebeat.com/ai/stardogs-karaoke-offers-on-premises-zero-hallucination-llm-solution-for-enterprises); [Stardog Voicebox FAQ](https://www.stardog.com/blog/stardog-voicebox-faq-how-llm-generative-ai-and-knowledge-graphs-are-the-future-of-data-management/); [Atlan comparison](https://atlan.com/know/ai-agent/knowledge-graph/stardog-vs-atlan.md)

**Semantic layer side**
- dbt Labs (2023) ran the same ACME benchmark through the dbt Semantic Layer and reported 83%, against 16.7% for text-to-SQL and 54.2% for the KG. It used only the "high question complexity / low schema complexity" subset, i.e. aggregation questions without many joins **[vendor]**. — [dbt blog](https://www.getdbt.com/blog/semantic-layer-as-the-data-interface-for-llms); [benchmark repo](https://github.com/dbt-labs/semantic-layer-llm-benchmarking)
- dbt Labs 2026 update (Ganz & Perigaud, 7 Apr 2026) **[vendor]**:
  - Setup: ACME Insurance, 15 tables in 3NF, 11 questions × 20 runs.
  - Original schema: text-to-SQL rose from 32.7% (GPT-4, 2023) to 64.5% (Sonnet 4.6 and GPT-5.3 Codex); the semantic layer rose from 60.5% to 72.7%.
  - On questions needing too many entity hops, the semantic layer scored **0%**, because MetricFlow could not express them, while text-to-SQL scored 70-100% on the same questions.
  - After the LLM wrote 3 extra dbt models: text-to-SQL 90.0% (Sonnet) / 84.1% (GPT-5.3 Codex); semantic layer 98.2% / 100%.
  - Semantic layer failures surfaced as errors, not wrong data. Reasoning effort barely mattered. Higher reasoning effort (`xhigh`) took more than 20 s/query against 8 s at `high`, with no gain.
  - Sources: [dbt developer blog](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
- Rumiantsau & Fokeev (arXiv 2604.25149, 28 Apr 2026, promoted by Cube) tested 100 questions on Contoso/ClickHouse, single-shot. Adding a hand-written 4 KB markdown "semantic layer" document raised accuracy from 45.5-50.5% to 67.7-68.7% (+17 to +23 pp) for Opus 4.7, Sonnet 4.6 and GPT-5.4. Model choice within the tier was statistically insignificant **[vendor-adjacent]**. — [arXiv 2604.25149](https://arxiv.org/abs/2604.25149); [Cube blog](https://cube.dev/blog/why-semantic-layers-make-llm-analytics-reliable-a-paired-benchmark-across-three-frontier-models)
- Snowflake Cortex Analyst (29 Aug 2024 engineering blog) **[vendor]**:
  - Claims "90%+ SQL accuracy on real-world use cases" on an internal 150-question benchmark of mostly flattened, pre-joined wide tables.
  - Reports itself as about 2x single-prompt GPT-4o (51%) and about 14% ahead of an unnamed competitor.
  - Scoring is lenient: column-level precision/recall against multiple human-marked gold queries. The team rejected LLM-as-judge as "nearly as hard as generating".
  - Sources: [Snowflake engineering blog](https://snowflake.com/en/engineering-blog/cortex-analyst-text-to-sql-accuracy-bi)
- VentureBeat (2024) put Databricks Genie at about 79% on Snowflake's internal benchmark **[vendor-competitor]**. — [VentureBeat](https://venturebeat.com/ai/snowflake-launches-cortex-analyst-an-agentic-ai-system-for-accurate-data-analytics)
- AtScale claims Cortex Analyst + AtScale reached 100% on "AtScale's NLQ benchmark", against "54% industry average" and "16% raw SQL". Those baselines are data.world's numbers reused **[vendor]**. — [AtScale blog](https://atscale.com/blog/semantic-layer-cortex-analyst-accuracy/)
- Google says Looker's semantic layer "reduces data errors in gen AI natural language queries by as much as two thirds" (internal test, no methodology published) **[vendor]**. — [Google Cloud blog](https://cloud.google.com/blog/products/business-intelligence/how-lookers-semantic-layer-enhances-gen-ai-trustworthiness)
- Databricks' own walkthrough (6 Feb 2026) used a 13-question benchmark. Genie went from 0% with cryptic names and no metadata, to 54% after metadata, PK/FK keys and value sampling, to 77% after example SQL for custom metrics, to 100% after text instructions for domain rules **[vendor, illustrative]**. — [Databricks blog](https://www.databricks.com/blog/how-build-production-ready-genie-spaces-and-build-trust-along-way)

**Benchmarks for context**
- Spider 2.0 (ICLR 2025): an o1-preview agent solved 21.3%, against 91.2% on Spider 1.0 and 73.0% on BIRD. A June 2026 third-party snapshot shows the Spider 2.0-Lite top at 52.9% (one vendor's reported result). The Spider2-Snow evaluation account was suspended in Aug 2026 **[academic]**. — [Spider2 repo](https://github.com/xlang-ai/Spider2); [arXiv 2411.07763](https://arxiv.org/abs/2411.07763); [BenchLM](https://www.benchlm.ai/benchmarks/spider2Lite)

### Inferences
- The ACME insurance benchmark has become the de facto arena for "semantic artefact vs raw schema". It is tiny (11-43 questions), and data.world, dbt, AtScale and SPC each choose their own subsets and scoring. Cross-paper comparisons (e.g. "SL 83% vs KG 54%") are therefore not apples to apples. The KG number is from 2023 GPT-4 zero-shot; the SL number is from a favourable subset.
- Frontier models have narrowed the raw text-to-SQL gap on small schemas: dbt measured 64.5-90%. The remaining case for a semantic artefact is less about raw accuracy and more about (a) deterministic metric semantics, (b) failure as refusal rather than wrong numbers, and (c) scale beyond what fits in context.
- dbt's 0% on multi-hop questions is a real expressiveness limit of metric-centric layers. Ontology/KG approaches (SPC graph traversal, ATHENA++ nesting, Ontop query rewriting) target exactly this multi-hop, role- and path-sensitive space. That is the most defensible positioning for an FIBO/Ontop layer.
- The OBQC 72/8/20 split, SPC's "zero wrong-but-executed runs" and dbt's "errors not wrong data" all point the same way. The value an ontology can measurably add is *checkability* (domain/range, path validity, grain), which turns silent errors into refusals.

### Gaps
- No independent (non-vendor) head-to-head of ontology/KG-mediated NL→SPARQL→SQL against a metric semantic layer on the same questions was found.
- No published accuracy numbers were found for Palantir Ontology/AIP NL querying, data.world's production AI Context Engine, Timbr, AtScale (independently audited), Power BI/Fabric Copilot, Amazon Q in QuickSight, or Looker Conversational Analytics.
- Databricks reportedly published internal Genie benchmark numbers in May 2026 (mentioned secondhand by a Refonte Learning article); not verified.

## Q2. Production case studies with metrics

### Takeaway
In-house deployments at Uber, LinkedIn and Pinterest report productivity and adoption gains: hundreds of weekly or daily users, roughly 3x faster authoring, 35% faster task completion. Correctness numbers are modest (LinkedIn: 53% correct-or-close by expert review). The successful pattern is a *copilot for people who can read SQL*, with human table confirmation, not autonomous answers for business users. Vendor products (Cortex Analyst, Genie, Power BI Copilot) frame success as configuration work on the semantic model plus benchmark gates.

### Cited Findings
- **Uber QueryGPT** (engineering blog, 19 Sep 2024) **[practitioner]**:
  - History: began at a May 2023 hackathon and went through 20+ iterations.
  - Architecture: 12 system "workspaces" (curated tables + SQL samples per domain) plus Intent, Table (user can accept or edit) and Column-Prune agents. GPT-4 Turbo 128K.
  - Context: Uber runs about 1.2M interactive queries per month, 36% from Operations.
  - Results: query authoring fell from about 10 min to about 3 min. About 300 DAU in a limited release; 78% said it reduced their time.
  - Evaluation metrics: intent accuracy, table overlap, successful run, run-has-output, and LLM-scored similarity to golden SQL. Run-to-run variance is about 5%.
  - Open issues: hallucinated tables/columns are unsolved, and a validation agent is planned. 200+ column tables consume 40-60K tokens. Wrong filter values produce successful but empty runs. Many questions have multiple valid answers.
  - Lessons: narrow single-purpose agents work best; vague prompts needed a "prompt enhancer"; users expect queries that "just work".
  - Sources: [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)
- **LinkedIn SQL Bot** (arXiv 2507.14372, 18 Jul 2025, KDD'25 Agentic AI for Enterprise workshop) **[practitioner]**. It is built on a knowledge graph indexing table metadata, historical query logs, wikis and code, with clustering to scope tables per team. The agent ranks context, writes SQL and self-corrects. 300+ weekly users; 53% of responses rated correct or close to correct by expert review on an internal benchmark. — [arXiv 2507.14372](https://arxiv.org/abs/2507.14372)
  - A secondary summary of LinkedIn's Dec 2024 blog says 95% of users rated accuracy "Passes" or better, and that "Fix with AI" (debugging) was the most-used feature. Built on LangChain/LangGraph and works within user permissions **[secondary]**. — [ZenML LLMOps database](https://www.zenml.io/llmops-database/building-a-production-text-to-sql-assistant-with-multi-agent-architecture)
- **Pinterest** (Querybook text-to-SQL, 2024) **[practitioner, via secondary]**. It reported a 35% improvement in task-completion speed for writing SQL with AI assistance, noting that this did not control for task differences. Table selection is two-step: a vector index of table summaries and historical queries, then the LLM picks tables for the user to confirm. — [Wren AI write-up](https://getwren.ai/post/deep-dive-into-how-pinterest-built-its-text-to-sql-solution); [Analytics Vidhya replication guide](https://www.analyticsvidhya.com/blog/2025/10/build-a-text-to-sql-system/)
- **Snowflake Cortex Analyst** **[vendor]**: 90%+ on the internal benchmark (see Q1). Failure modes Snowflake itself lists: unstated assumptions (Christmas 2022 instead of the most recent Christmas), LAG over non-consecutive dates, filtering before a rolling window, substituting a different metric definition, returning a minimum value without its date. The UI shows "Here's our interpretation of your question". — [Snowflake engineering blog](https://snowflake.com/en/engineering-blog/cortex-analyst-text-to-sql-accuracy-bi)
- **Databricks Genie**:
  - Official benchmarks feature allows up to 500 questions per space, tracked over time **[vendor docs]**. — [Databricks docs](https://docs.databricks.com/aws/en/genie/benchmarks)
  - One community practitioner got 6/20 correct out of the box. A legacy dataset never exceeded 75% after tuning and only reached 100% after the underlying data was rebuilt **[practitioner anecdote]**. — [Databricks community](https://community.databricks.com/t5/genie-hub/operationalizing-a-live-genie-space-benchmarking-governance-amp/td-p/167186)
  - Partner Koantek uses promotion gates of dev ≥60%, staging ≥70%, prod ≥80% **[partner]**. — [Koantek](https://www.koantek.com/blog-posts/productizing-databricks-genie-at-enterprise-scale)
  - Databricks says above 80% on benchmarks is typical before UAT **[vendor]**. — [Databricks blog](https://www.databricks.com/blog/how-build-production-ready-genie-spaces-and-build-trust-along-way)
- **Power BI / Fabric Copilot & data agents** **[vendor docs + practitioner]**:
  - The DAX generation tool relies *solely* on semantic-model metadata and "Prep for AI" (AI data schema, verified answers, AI instructions). It ignores agent-level instructions.
  - Practitioners report confident-but-wrong answers that trace back to unclear KPI definitions and missing descriptions (Fabric community, June 2026).
  - Sources: [Microsoft Learn](https://learn.microsoft.com/fabric/data-science/data-agent-semantic-model); [Fabric community thread](https://community.fabric.microsoft.com/t5/Service/Copilot-theory-versus-practice/m-p/5283765)

### Inferences
- The production pattern is converging. A curated, domain-scoped context store (Uber workspaces, LinkedIn's KG of metadata, query logs and wikis, Genie spaces, Snowflake semantic views, Power BI Prep for AI) does the real work. Its curation and maintenance is the dominant operational cost. This is the same job an ontology plus mappings does in an Ontop VKG.
- LinkedIn's internal context store is literally called a knowledge graph, but it is a retrieval index over usage artefacts (query logs, wikis), not a formal ontology. Mining query logs is cheap and high-signal context that an FIBO-only design would miss.
- The reported metrics are mostly time-saved and satisfaction metrics for SQL-literate users. Claims of autonomous correctness for business users rest on vendor benchmarks.

### Gaps
- Airbnb, Amazon Q in QuickSight, Wren AI and Vanna: no production metrics were retrieved within the search budget.
- Pinterest's original post (medium.com/pinterest-engineering) returned 403. The often-quoted first-shot acceptance rate and table-search hit-rate figures could not be verified, so they are omitted.
- No longitudinal data (accuracy drift over months, retention) was found from any deployment.

## Q3. Operational concerns: ambiguity, metric definitions, access control, injection, cost/latency, auditability, abstention, monitoring

### Takeaway
The hard operational problems are well documented:
- Ambiguity is the dominant error source in interactive settings.
- Metric-definition drift produces silent wrong answers.
- Prompt-to-SQL injection is real and cannot be fixed in the prompt.
- Abstention is hard to do better than a trivial baseline.

Vendors handle access control by executing generated SQL under the caller's database role, but they publish little detail. Evaluation in production is benchmark-gated and human-curated, and scoring itself is contested.

### Cited Findings
- **Ambiguity / clarification**:
  - BIRD-Interact (arXiv 2510.05318; ICLR 2026 oral): GPT-5 completes only 8.67% of tasks in conversational and 17.00% in agentic interactive mode. In a 50-case error analysis, more than 80% of errors came from incomplete ambiguity resolution. Systems asked for clarification about once per task even though tasks contain about 4 ambiguities **[academic]**. — [arXiv 2510.05318](https://arxiv.org/abs/2510.05318v2); [ICLR 2026](https://iclr.cc/virtual/2026/oral/10007487)
  - A VLDB 2026 AIDB workshop paper detects ambiguity by sampling multiple SQL candidates, gaining about 3-7 pp over the ReAct baseline **[academic]**. — [VLDB AIDB 2026](https://www.vldb.org/2026/Workshops/VLDB-Workshops-2026/AIDB/aidb26_10.pdf)
  - Uber needed a "prompt enhancer" for vague questions. — [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)
- **Metric definitions**:
  - Snowflake documents the LLM swapping in a different forecast-error metric than the customer's definition. — [Snowflake blog](https://snowflake.com/en/engineering-blog/cortex-analyst-text-to-sql-accuracy-bi)
  - Databricks shows custom metrics (CTR) and subjective terms ("high CTR") failing until example SQL or instructions are added. — [Databricks blog](https://www.databricks.com/blog/how-build-production-ready-genie-spaces-and-build-trust-along-way)
  - dbt recommends the semantic layer specifically for "board data, auditors, OKRs, KPIs". — [dbt blog](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
- **Access control / row-level security**:
  - Cortex Analyst "fully integrates with Snowflake's RBAC policies, ensuring that SQL queries generated and executed adhere to all established access controls". It uses semantic-model metadata only for generation, and SQL runs in the customer's warehouse.
  - With legacy stage-hosted YAML, "any role with access to the stage can access the semantic models on that stage" even without table access. Semantic views (schema objects with native RBAC) are now recommended. The docs do not explicitly name row-access or masking policies **[vendor docs, accessed Oct 2026]**.
  - Sources: [Snowflake docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
  - Genie is "governed through Unity Catalog". The overview gives no detail on embedded vs per-user credentials or row filters. — [Databricks docs](https://docs.databricks.com/aws/en/genie/)
  - Security commentary: generated SQL can retrieve more rows than a human analyst would **[secondary]**. — [nhimg](https://nhimg.org/?p=119149)
- **Prompt-to-SQL injection**: P2SQL (Pedro, Castro, Carreira, Santos; arXiv 2308.01990; ICSE 2025) **[academic]**. It demonstrated injection through LangChain/LlamaIndex across 7 LLMs and found vulnerabilities in 5 real-world apps, including unauthorized reads and writes. Prompt-level restrictions were bypassable. The authors propose 4 defences, e.g. database permission hardening and query rewriting/guarding. — [arXiv 2308.01990](https://arxiv.org/abs/2308.01990); [ICSE 2025 listing](https://conf.researchr.org/details/icse-2025/icse-2025-research-track/31/Prompt-to-SQL-Injections-in-LLM-Integrated-Web-Applications-Risks-and-Defenses)
- **Abstention**: TrustSQL (Lee et al., KAIST; arXiv 2403.15879) uses penalty-based scoring, where wrong answers cost more than abstentions. Answerability and error detectors did not consistently beat a naive "abstain on everything" baseline under severe penalties **[academic]**. — [arXiv 2403.15879](https://arxiv.org/abs/2403.15879)
  - Positive data points for ontology checks: OBQC produced 8% "I don't know" instead of wrong answers ([arXiv 2405.11706](https://arxiv.org/abs/2405.11706)), and SPC had one refusal and zero wrong-but-executed runs ([arXiv 2608.16663](https://arxiv.org/abs/2608.16663)).
- **Cost / latency**:
  - Uber's Column-Prune agent exists to cut tokens, cost and latency; wide tables exceeded context limits. — [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)
  - dbt: GPT-5.3 Codex at `xhigh` took more than 20 s/query against 8 s at `high`, with no accuracy gain. Reasoning effort barely moved semantic layer accuracy. — [dbt blog](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
  - Rumiantsau & Fokeev found model choice within a tier insignificant once semantics were supplied, which argues for cheaper models. — [arXiv 2604.25149](https://arxiv.org/abs/2604.25149)
- **Data residency**: Cortex Analyst defaults to Snowflake-hosted models ("no data, including metadata or prompts, leaves Snowflake's governance boundary"). It can optionally use Claude Sonnet 4.6/4.5 or GPT-4.1, with cross-region inference. It does not train on customer data. — [Snowflake docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- **Auditability / explanation**:
  - Uber returns SQL plus an explanation. — [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)
  - Cortex Analyst restates its interpretation. — [Snowflake blog](https://snowflake.com/en/engineering-blog/cortex-analyst-text-to-sql-accuracy-bi)
  - Stardog tags each answer fragment's provenance (KG query vs RAG vs external LLM). — [Atlan comparison](https://atlan.com/know/ai-agent/knowledge-graph/stardog-vs-atlan.md)
- **Monitoring / production evaluation**:
  - Uber evaluates on golden sets mined from logs, in "vanilla" vs "decoupled" (given intent and tables) modes, and tracks results per run over time. — [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)
  - Genie benchmarks support up to 500 questions per space, with an evaluations history. — [Databricks docs](https://docs.databricks.com/aws/en/genie/benchmarks)
  - Practitioners warn that teams validate with a few demo questions and then stop re-evaluating. — [Microsoft Tech Community](https://techcommunity.microsoft.com/t5/azure/an-azure-databricks-data-agent-that-never-gets-re-evaluated-is-a/m-p/4557958)
  - Execution accuracy wrongly rejects valid alternatives. Snowflake uses multiple human-marked golds; Renggli, Ilyas and Rekatsinas argue single-gold benchmarks hide valid alternatives and the inherent ambiguity of mapping one question to one query. — [arXiv 2501.18197](https://arxiv.org/abs/2501.18197)

### Inferences
- For an Ontop VKG design, access control should be enforced in the database/virtualisation layer, under the end user's identity. Ontop rewrites SPARQL to SQL that runs with the connection's credentials, so per-user connections or RLS in the source DB are required. P2SQL shows that prompt-level guards are insufficient. A read-only role, a SPARQL-only surface (no raw SQL from the LLM), and the ontology/OBQC check as a query firewall are natural defences.
- Ambiguity is where most interactive failures sit. An ontology gives a principled source of clarification options: alternative properties or paths between classes, roles, and grain.
- No vendor publishes production (in-the-wild) accuracy. Everyone publishes curated-benchmark accuracy, so an FIBO layer should ship its own benchmark harness, e.g. FIBEN plus domain golden sets, with promotion gates.

### Gaps
- No public documentation was found of exactly how Genie, Cortex Analyst, Power BI Copilot or Looker apply row-access/masking policies to generated queries in embedded or shared-credential deployments, or of any incident reports.
- No published per-query cost figures for any enterprise deployment were found.
- No source quantified clarification-dialogue uptake or abstention rates in production.

## Q4. Open problems named in 2025-2026 surveys / position papers

### Takeaway
Surveys and benchmarks name a consistent set of open problems. Even in 2026 the best agents solve only about half of realistic enterprise tasks.
- Open-world and enterprise schemas (Spider 2.0-scale)
- Ambiguity and interaction
- Trustworthy, abstaining systems
- Evaluation validity (multiple correct queries)
- Cost-effective solutions
- Robustness, safety and benchmarking for agentic data systems

### Cited Findings
- The NL2SQL survey (Liu et al., arXiv 2408.05109; v4/v5) names open-world NL2SQL, cost-effective NL2SQL and trustworthy solutions as open problems. — [arXiv 2408.05109](https://arxiv.org/abs/2408.05109)
- The generative-AI Text-to-SQL survey (arXiv 2412.05208) names ambiguous or underspecified questions as a key challenge and proposes interactive clarification. — [arXiv 2412.05208](https://arxiv.org/abs/2412.05208)
- Renggli, Ilyas, Rekatsinas (Jan 2025) give a taxonomy of Text2SQL limitations. Single-gold evaluation is fundamentally flawed, and they list open challenges in deploying mitigations. — [arXiv 2501.18197](https://arxiv.org/abs/2501.18197)
- The LLM-based data science agents survey (arXiv 2510.04023, Oct 2025) analysed 45 systems and found gaps in robustness, trust, safety, scalability and benchmarking. Compliance and human oversight are needed before reliable deployment. — [arXiv 2510.04023](https://arxiv.org/abs/2510.04023)
- BIRD-Interact (ICLR 2026): even frontier models fail interactive tasks mainly through ambiguity handling (see Q3). — [arXiv 2510.05318](https://arxiv.org/abs/2510.05318v2)
- Spider 2.0: enterprise workflows remain unsolved (21% at publication; about 53% on the Lite variant by mid-2026 per a third-party snapshot). — [Spider2 repo](https://github.com/xlang-ai/Spider2); [BenchLM](https://www.benchlm.ai/benchmarks/spider2Lite)
- TrustSQL: reliable abstention is still unsolved. — [arXiv 2403.15879](https://arxiv.org/abs/2403.15879)
- LinkedIn: benchmark performance does not translate into enterprise readiness; keeping semantics current in a fast-changing data lake is central. — [arXiv 2507.14372](https://arxiv.org/abs/2507.14372)
- Uber: hallucinated schema elements are "not fully solved". — [Uber blog](https://www.uber.com/en-us/blog/query-gpt/)

### Inferences
- "Semantic freshness" (LinkedIn) and "semantic model curation cost" (Genie, Power BI, dbt) are the operational face of the open-world problem. An ontology layer inherits the same maintenance burden, plus mapping maintenance in Ontop, and should plan for it, e.g. log-mined suggestions for mapping updates.

### Gaps
- No dedicated 2026 NL2SQL survey was found. An HKUST data-agents survey (thesis defence, Apr 2026) exists but its contents were not accessible. The VLDB 2025 tutorial "NL2SQL: State of the Art and Open Problems" was identified but not read.

## Q5. Where ontologies demonstrably add value vs semantic layers or raw schemas, and where evidence is weak or vendor-driven

### Takeaway
There is demonstrated value, though on small and vendor-authored benchmarks, in four areas:
1. Lifting accuracy over raw schema: 16% to 54% in 2023, and 55% to 97% for SPC in 2026.
2. Using the ontology as a *validator* that converts errors into repairs or abstentions (OBQC: 72% correct, 8% "I don't know").
3. Multi-hop, path- and role-sensitive questions where metric-centric semantic layers cannot express the query (dbt's 0% on too-many-hops questions).
4. Nested BI queries over FIBO-grounded schemas (ATHENA++ 88% on FIBEN).

Evidence is weak or absent for ontologies beating a well-modelled semantic layer on aggregate-KPI questions, for "hallucination-free" claims, and for anything at production scale.

### Cited Findings
- Raw schema → KG: 16% → 54% (GPT-4, 2023) **[vendor]**. — [arXiv 2311.07509](https://arxiv.org/abs/2311.07509)
- KG + ontology check + repair: 72% correct / 8% abstain / 20% wrong **[vendor]**. — [arXiv 2405.11706](https://arxiv.org/abs/2405.11706)
- Governed semantic graph + deterministic compilation (SPC): 97.4% vs 55.3%, with zero wrong-but-executed runs; author concedes non-causal **[vendor-adjacent preprint]**. — [arXiv 2608.16663](https://arxiv.org/abs/2608.16663)
- Metric semantic layer: 0% on multi-hop questions until extra models were added, and 98-100% after **[vendor]**. — [dbt blog](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
- On the same ACME benchmark, dbt's 2023 subset gave semantic layer 83% vs KG 54.2%. The vendor chose the subset to avoid many joins **[vendor]**. — [dbt 2023 blog](https://www.getdbt.com/blog/semantic-layer-as-the-data-interface-for-llms)
- Even an unstructured 4 KB semantic document gives +17 to +23 pp. This suggests much of the gain comes from *having* curated semantics, not from its formalism **[vendor-adjacent]**. — [arXiv 2604.25149](https://arxiv.org/abs/2604.25149)
- ATHENA++ on FIBEN (FIBO-grounded): 88.33%, including nested queries **[industrial research, pre-LLM]**. — [PVLDB vol. 13](https://www.vldb.org/pvldb/vol13/p2747-sen.pdf)
- LinkedIn's production system uses a "knowledge graph" of metadata, logs, wikis and code: an informal KG, not OWL. — [arXiv 2507.14372](https://arxiv.org/abs/2507.14372)
- Timbr and Stardog: no independent numbers; "hallucination-free" is a provenance guarantee on the KG path only. — [Timbr](https://timbr.ai/why-enterprise-llms-need-sql-knowledge-graphs-for-accurate-nl2sql/); [Atlan on Stardog](https://atlan.com/know/ai-agent/knowledge-graph/stardog-vs-atlan.md)

### Inferences
- **Strong positioning for an FIBO + Ontop NL→SPARQL→SQL layer**:
  - Multi-hop, role- and path-sensitive questions across normalised schemas. FIBO's party/role/contract patterns are exactly the "too many hops" class.
  - Ontology-based query validation and abstention (OBQC-style domain/range and path checks before execution).
  - Reuse across tools via standards (SPARQL/R2RML) rather than a proprietary metric API.
  - A ready FIBO-grounded benchmark (FIBEN) for honest evaluation.
- **Weak positioning**:
  - Simple KPI and aggregation questions, where a metric semantic layer (MetricFlow, Cortex semantic views, LookML) is simpler and already near 100% on vendor benchmarks.
  - Teams without ontology skills: the curation cost is higher than for YAML metric definitions.
  - Performance and latency of two-stage translation (SPARQL→SQL via Ontop), for which no enterprise NL numbers exist.
- A hybrid reading of dbt's own recommendation (semantic layer first, fallback otherwise) maps naturally onto SIP. Metric definitions can be declared as ontology-anchored measures, with path-compiled SPARQL for the long tail of questions.
- Every pro-ontology number traces back to data.world authors, an SPC author with commercial ties, or pre-LLM IBM research. Practitioners should present ontology value as plausible and mechanism-backed, not independently proven.

### Gaps
- No independent replication of the data.world, OBQC or SPC results was found.
- No published evaluation of Ontop-based (VKG) LLM question answering at enterprise scale with accuracy, latency and cost was found within budget.
- No Palantir Ontology accuracy data was found; Palantir publishes customer stories, not NL-query benchmarks.
