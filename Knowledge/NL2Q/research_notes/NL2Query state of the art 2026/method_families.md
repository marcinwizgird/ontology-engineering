# Method families in LLM-based Text-to-SQL / NL-to-query: ablation evidence (as of 2026-10-19)

Conventions: EX = execution accuracy. "pp" = percentage points. A delta is the drop when a component is removed, or the gain when it is added, on the named benchmark and model. Most ablations use BIRD dev, a 10% subset of BIRD dev, Spider dev, or Spider 2.0. None of the single-paper ablations has been replicated, so treat deltas under about 1 pp as noise. Dates are arXiv first-submission dates unless stated otherwise.

## 1. Schema linking / pruning and value retrieval (literal grounding)

### Takeaway
With frontier long-context models and schemas that fit in context, aggressive schema linking *hurts*: the recall loss outweighs the noise reduction, costing -2.7 to -11.6 pp. Recall-oriented light pruning, or the full schema, is preferred. Schema pruning still pays off for small and open models, for very large enterprise schemas (Spider 2.0), and for cost. Value retrieval (grounding literals to DB cell values) is a consistent mid-size win of +0.4 to +2.9 pp. Its benefit is larger when questions contain literals.

### Cited Findings
- Maamari et al., "The Death of Schema Linking?" (Aug 2024), BIRD dev 10% subset: replacing the full schema with table/column schema linking cut EX by -4.77 pp (TCSL) and -11.57 pp (SCSL) for fine-tuned GPT-4o (full pipeline 67.35). The drops were -4.76/-5.44 for Gemini 1.5 Pro and -2.72/-4.76 for Llama 3.1-405B. Every schema-linking variant lowered EX for all three models. The full schema gives 100% recall of required columns; TCSL gives 77.44%. The final pipeline skips schema linking whenever the schema fits in context. — [arXiv 2408.07702v2](https://arxiv.org/html/2408.07702v2)
- Chung et al. (Google), "Is Long Context All You Need?" (Jan 2025), gemini-1.5-pro, BIRD dev: EX was 38.01 with the top-1 retrieved table, 54.69 with the top-7, and 62.32 with all tables of the DB. The authors conclude that recall matters more than precision, since accuracy did not degrade much with many irrelevant tables. They observed no "lost in the middle" effect. Latency grows near-linearly with context and becomes high and variable beyond about 32k tokens. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- Same paper, incremental ablation: adding BIRD evidence/hints gave +16.36 pp (43.87 -> 60.23), the largest single gain. Sample column values gave +1.76 pp. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- CHESS (May 2024): the schema selector adds about 2% accuracy and cuts LLM tokens about 5x on large schemas. BIRD test 71.10%. — [arXiv 2405.16755](https://arxiv.org/abs/2405.16755)
- DIN-SQL (2023, CodeX Davinci, Spider dev): removing the schema-linking module drops EX from 69.9 to 65.9 (-4.0 pp). This is an older-generation model, and the figures come from a search summary of the paper. — [arXiv 2304.11015](https://arxiv.org/pdf/2304.11015)
- RSL-SQL argues that schema linking is still needed, though it can omit required elements. It uses bidirectional linking plus self-correction and reaches 67.2% on BIRD and 87.9% on Spider with GPT-4o. — [arXiv 2411.00073v2](https://arxiv.org/html/2411.00073v2)
- Value retrieval in CHASE-SQL: removing LSH value retrieval drops EX from 73.01 to 70.09 (-2.92 pp, Gemini 1.5 Pro, BIRD dev). — [arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- Value retrieval on an RL-trained model adds only +0.4 pp at both 14B and 32B (32B: 70.5 -> 70.9 BIRD dev). — [Arctic-Text2SQL-R1, arXiv 2505.20315v2](https://arxiv.org/html/2505.20315v2)
- Spider 2.0 (enterprise schemas on Snowflake/BigQuery), ReFoRCE ablation with o3: DB-info compression is the most valuable single component, costing -3.65 pp on Snow and -3.47 pp on Lite when removed. Removing column exploration costs -2.56/-2.37 pp. Supplying the gold tables adds only +0.37 pp, so table selection is not the bottleneck once compression and exploration are in place. — [arXiv 2502.00675](https://arxiv.org/html/2502.00675)
- Text-to-Cypher (Neo4j blog, Apr 2025; Llama-3.1-8B-Instruct 4-bit, not fine-tuned): exact-match schema pruning shortened prompts about 6x and gave the best results. NER masking and similarity pruning did not help. The authors caution that filtering may not help more advanced LLMs. Metric values appear only in charts, so this is weak evidence. — [Neo4j blog](https://neo4j.com/blog/developer/schema-representation-in-text2cypher/)

### Inferences
- For frontier models: pass the full schema, or prune for maximum recall, and add column descriptions and sample values. Spend effort on value retrieval and on injecting evidence and business glossaries rather than on tight schema linking. For 7-8B models, or schemas larger than about 30k tokens, pruning still improves both accuracy and cost.
- The largest single context gain in any ablation found here is external knowledge/hints (+16 pp). In a semantic platform this corresponds to grounding in an ontology or glossary.

### Gaps
- The RESDSQL ablation (cross-encoder schema ranking, 2023) was not fetched in this pass.
- I found no controlled 2026 replication of the "schema linking unnecessary" result with reasoning models (o3, GPT-5, Claude 4.x).

## 2. Few-shot selection, decomposition, intermediate representations

### Takeaway
Similarity-based example selection (DAIL-SQL) gave +3-5 pp on GPT-4-era Spider. With long-context Gemini on BIRD, retrieved many-shot examples give under 1 pp, and fine-tuned models lose their in-context learning (ICL) ability. Decomposition and structured-CoT generators (DIN-SQL; CHASE-SQL's divide-and-conquer and query-plan CoT) each add +4 to +7 pp over a plain prompt. Inside a multi-candidate ensemble, however, each generator contributes only about 0.6-1.2 pp. Their main value there is candidate *diversity*.

### Cited Findings
- DAIL-SQL (Aug 2023), GPT-4, Spider dev EX: 0-shot 72.3. With 5 shots: random 79.5, question similarity 79.9, masked-question similarity 82.0, DAIL selection (masked question plus query similarity) 82.4. DAIL selection beats random by +2.9 EX and +20 EM. DAIL organization raises 0-shot EX from 72.3 to 83.5. Self-consistency adds only +0.4 (86.2 -> 86.6 on the Spider leaderboard) at much higher cost. — [arXiv 2308.15363v4](https://arxiv.org/html/2308.15363v4)
- DAIL-SQL: supervised fine-tuning removes ICL ability. Fine-tuned LLaMA-7B scores 66.7 at 0-shot and falls to about 61.4 with 1-shot examples. — [arXiv 2308.15363v4](https://arxiv.org/html/2308.15363v4)
- Long-context Gemini study: retrieved train examples moved EX from 61.60 (none) to 62.52 (100 similar examples). Synthetic examples added +1.05 overall but cost about -1.4 on challenging questions. Injecting one ground-truth example lifts EX to about 78%, so relevance matters, not volume. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- DIN-SQL (NeurIPS 2023, CodeX, Spider dev): removing classification/decomposition drops EX from 69.9 to 63.1 (-6.8 pp). Removing self-correction drops it to 67.3 (-2.6). These figures come from a search summary of the paper. — [arXiv 2304.11015](https://arxiv.org/pdf/2304.11015)
- CHASE-SQL (Oct 2024, Gemini 1.5 Pro, BIRD dev), single generators against a zero-shot CoT baseline of 57.75: query-plan CoT 63.62 (+5.9), divide-and-conquer CoT 63.92 (+6.2), online synthetic instance-aware examples 67.09 (+9.3). In the full ensemble, removing QP CoT costs -0.65, OS -0.85, and DC -1.24 pp. — [arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- OmniSQL (7B): CoT-augmented training data beats the original SQL-only Spider+BIRD data by +4.5 on BIRD dev and +5.9 on Spider test, but loses 5.4 on EHRSQL. — [arXiv 2503.02240v2](https://arxiv.org/html/2503.02240v2)

### Inferences
- Instance-aware synthetic examples were CHASE-SQL's strongest single prompting generator. For a domain platform, examples generated against the actual schema will likely beat retrieved generic examples.
- Explicit decomposition prompts matter most for weaker or older models, and reasoning models appear to internalise much of it. More thinking is not automatically better for SQL, though: the reasoning-tuned QwQ-32B was a worse RL starting point than a coder instruct model (see section 5).

### Gaps
- Ablations for MAC-SQL, NatSQL and other intermediate representations (IRs) were not fetched. I found no 2025-2026 evidence on whether IRs still help frontier models.

## 3. Multi-candidate generation + selection, execution-feedback self-correction, cost

### Takeaway
This family has the most robust evidence that it still helps as of 2024-2025. A trained pairwise selector beats self-consistency by about 4-6 pp, and execution-guided fixing or self-correction adds +1.4 to +3.8 pp. Plain self-consistency or majority voting gives only +0.4 to +2.5 pp on strong or RL-trained models. The oracle gap is large: pass@N reaches 82.8 against 73.0 for the selected answer in CHASE-SQL, so selection is the main lever.

### Cited Findings
- CHASE-SQL ablation (BIRD dev, Gemini 1.5 Pro): the full system scores 73.01. Replacing the selector with self-consistency gives 68.84 (-4.17). Replacing it with a ranker agent gives 65.51 (-7.50). Removing the query fixer gives 69.23 (-3.78). Per generator with 10 samples, the selector beats self-consistency by about 6 pp on average (e.g. QP 65.78 -> 71.70; DC 66.43 -> 71.31). The oracle upper bound over all candidates is 82.79. The selector is a LoRA-fine-tuned Gemini 1.5 Flash. The Claude 3.5 Sonnet variant scores 69.53. BIRD test 73.0. — [arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- Same paper: the fixer adds +0.9 to +3.8 pp per generator (baseline 57.75 -> 61.58; OS 67.09 -> 68.02). — [arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- Maamari et al.: removing candidate selection costs -2.04 (fine-tuned GPT-4o), -2.72 (Gemini 1.5 Pro) and -0.68 (Llama-405B). Removing self-correction costs -1.36, -3.40 and -3.40. — [arXiv 2408.07702v2](https://arxiv.org/html/2408.07702v2)
- Long-context Gemini: self-correction adds +2.81 and verify-and-retry adds +0.58. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- Majority voting on trained models: OmniSQL gains +1.7 to +2.5 on BIRD dev. Arctic-R1 32B gains +0.7 with majority@8, and +1.0 combined with value retrieval. — [arXiv 2503.02240v2](https://arxiv.org/html/2503.02240v2); [arXiv 2505.20315v2](https://arxiv.org/html/2505.20315v2)
- ReFoRCE (o3, Spider 2.0): removing majority voting costs -2.01 on Snow and -1.83 on Lite. — [arXiv 2502.00675](https://arxiv.org/html/2502.00675)
- DAIL-SQL: self-consistency adds +0.4 at "much higher time and cost". — [arXiv 2308.15363v4](https://arxiv.org/html/2308.15363v4)
- Cost: CHESS reports about 83% fewer LLM calls than the then-leading proprietary pipeline while staying within 2 pp of it. — [arXiv 2405.16755](https://arxiv.org/abs/2405.16755)
- Cost: the long-context pipeline accumulates about 399k tokens per request with online synthetic generation. The authors recommend dropping disambiguation and online example generation to meet production latency. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- Small grammar-constrained models (Qwen2.5 0.5-7B, Spider dev, Aug 2026): beam search and sample+vote help mostly at small sizes, but moving to a larger model beats adding inference compute. Beam search beats sample+vote at a matched budget. Only the abstract was read, which gives no numbers. — [arXiv 2608.25761](https://arxiv.org/abs/2608.25761)
- A caution from outside SQL (Jul 2026, Qwen2.5-7B, GSM8K and HumanEval): on GSM8K, 2-call self-refinement scored 86.2 at 7.4x fewer tokens, against 45 (JSON) or 82 (plaintext) for a 5-role multi-agent pipeline. On HumanEval, self-refinement hurt: 96.3 -> 66.5. Format and implementation details mattered more than architecture. — [arXiv 2607.26922](https://arxiv.org/abs/2607.26922)

### Inferences
- Priority by evidence: (1) an execution-guided fixer, (2) a trained or strong pairwise selector over diverse candidates, (3) plain voting last. Voting gains shrink below 1 pp on RL-trained models.
- Self-correction can regress when the model is already accurate. Trigger it on execution errors or empty results rather than running it every time.

### Gaps
- The MCS-SQL and XiYan-SQL ablation tables were not fetched in this pass. XiYan-SQL is the base system in AmbiSQL, and Arctic-R1 32B beats XiYan-32B by 2.8 pp on BIRD test ([arXiv 2505.20315v2](https://arxiv.org/html/2505.20315v2)).
- I found no 2026 ablation measuring selector gains with GPT-5- or Claude 4.x-class models on BIRD.

## 4. Agentic DB exploration (Spider-Agent, ReFoRCE, MCP-style tools)

### Takeaway
On enterprise-scale benchmarks (Spider 2.0), agentic exploration is essential and its gains are large. ReFoRCE roughly doubles GPT-4o (10.05 -> 20.84) and adds about +11.5 pp over Spider-Agent with o3. By late 2026 the self-reported Spider 2.0 leaderboards reach about 96.7 (Snow) and 76.2 (Lite). The top entries are heavily engineered commercial agents, unverified and without ablations.

### Cited Findings
- Spider 2.0 baselines: o1-preview solved 17.1% in the original paper. Spider-Agent + o1-preview scores 23.58 on Snow and 23.03 on Lite. — [Spider 2.0 site](https://spider2-sql.github.io/)
- ReFoRCE (Snowflake, Feb 2025, later updated with o3), EX on Snow/Lite:

  | Method | GPT-4o | o4-mini | o3 |
  |---|---|---|---|
  | Spider-Agent | 10.05 / 12.80 | 21.94 / 23.40 | 24.31 / 24.86 |
  | ReFoRCE | 20.84 / 21.76 | 29.80 / 31.99 | 35.83 / 36.56 |

  Ablation with o3: removing column exploration costs -2.56/-2.37 (EX@8 on Lite: -4.76). Removing DB-info compression costs -3.65/-3.47. Removing majority voting costs -2.01/-1.83. Supplying gold tables adds +0.37. Cost: ReFoRCE makes 3.52v LLM calls at about 23k tokens per call, where v is the number of votes. Without column exploration it makes 1.69 calls at about 15k tokens per call. Spider-Agent makes about 11v LLM calls at about 8k tokens per call. — [arXiv 2502.00675](https://arxiv.org/html/2502.00675)
- Spider 2.0 leaderboard (accessed 2026-10-19; entries are undated and self-reported):
  - Snow: Genloop Sentinel Agent v2 Pro 96.70; Native mini 96.53; QUVI-3 + Gemini-3-pro-preview 94.15; Tencent TCDataAgent-SQL 93.97; Prism Swarm + Claude-Sonnet-4.5 90.49; QUVI-3 + Claude-Opus-4.6 86.28; AT&T/RelationalAI "Ask Data with Relational Knowledge Graph" 86.28.
  - Lite: Tianqiong Data Agent + GLM 5.2 76.23; DivSkill-SQL (Snowflake x UCSD) 73.13; Databao Agent (JetBrains) 69.65; Claude Code Agent + Sonnet 61.2.
  — [Spider 2.0 site](https://spider2-sql.github.io/)

### Inferences
- Snow went from about 36 (ReFoRCE + o3, 2025) to about 95 (2026), driven by agentic systems that use contextual scaling, skills and knowledge graphs. A KG-backed entry (RelationalAI) in the Snow top 10 is evidence that semantic-layer grounding competes at the frontier. This evidence is weak: most entries have no paper or ablation, and some may be tuned to the benchmark.
- A generic coding agent (Claude Code + Sonnet, 61.2 on Lite) already beats the 2025 research pipelines by a wide margin. Tool-using frontier agents with DB tools (MCP-style) are therefore a strong baseline.

### Gaps
- I found no controlled ablation of MCP-style tool sets. Spider-Agent's own ablations were not fetched.

## 5. SFT on synthetic data and RL with execution reward

### Takeaway
Fine-tuning brings 7-32B open models to or above GPT-4o on BIRD and Spider. Synthetic SFT (OmniSQL on SynSQL-2.5M) adds +9 to +13 pp over the base model at 7B. RL with an execution-only reward (GRPO) adds another +5-6 pp at matched size: Arctic-Text2SQL-R1 32B reaches 70.5 on BIRD dev and 71.83 on BIRD test. The gains shrink with model size and do not carry over to enterprise SQL, where Spider 2.0-SQLite scores stay at 10-16%. Simple rewards beat shaped rewards, and data filtering is essential.

### Cited Findings
- OmniSQL / SynSQL-2.5M (Mar 2025): 2.5M samples over 16k synthetic DBs, each with a CoT solution. Greedy BIRD dev: 7B 63.9, 14B 64.2, 32B 64.5 (67.0 with majority voting), against GPT-4o 61.9 and DeepSeek-V3 63.2. Spider test: 87.6-88.3 against GPT-4o 83.2. On Spider2.0-SQLite, however, OmniSQL scores 10.4-11.9 against GPT-4o 14.8. — [arXiv 2503.02240v2](https://arxiv.org/html/2503.02240v2)
- OmniSQL data ablation (7B, greedy, BIRD dev): base 50.9; SynSQL only 59.9; CoT Spider+BIRD only 59.6; full 63.9. The full mix beats in-domain-only data by +4.3 on BIRD dev, +4.5 on Spider2 and +8.9 on EHRSQL. The gain over the Qwen2.5-Coder base on BIRD dev is +13.0 at 7B, +2.7 at 14B and 0.0 at 32B. — [arXiv 2503.02240v2](https://arxiv.org/html/2503.02240v2)
- Arctic-Text2SQL-R1 (Snowflake, May 2025; ACL Findings 2026) — [arXiv 2505.20315v2](https://arxiv.org/html/2505.20315v2):
  - The reward is execution correctness only. Fine-grained rewards induced "lazy" behaviour, and no reward variant improved results.
  - Data: filtered Gretel synthetic data gave +1.6 BIRD dev (14B); the unfiltered version gave -0.3. Unfiltered LLM-augmented BIRD data cost -2.4.
  - Training: online RL beats batch RL by +1.7. An OmniSQL-32B initialisation beats Qwen-Inst by +1.3. An OmniSQL-style prompt adds +2.6. GRPO beats PPO by +1.9, though PPO was under-tuned.
  - Starting point: the reasoning model QwQ-32B started at 55.2, against 64.9 for Qwen-Coder-Inst.
  - Final BIRD dev: 7B 68.9, 14B 70.1, 32B 70.5. BIRD test (32B): 71.83. That is +5.0 to +5.9 BIRD dev over OmniSQL at the same size. Spider2.0-SQLite: 15.6-16.3.
  - The prompt alone moved Llama-3.1-70B from 57.4 to 65.1.
- Comparisons in the Arctic paper (BIRD-train data only) — [arXiv 2505.20315v2](https://arxiv.org/html/2505.20315v2):
  - Against Reasoning-SQL at 14B: +2.28 on BIRD dev (66.49 vs 64.21).
  - Against SQL-R1 on OmniSQL-7B: +2.8 on BIRD dev with majority voting (69.4 vs 66.6). SQL-R1 is 0.1 higher on Spider test.
  - SQL-R1 with 200K SFT examples before RL scored worse than without (59.2 vs 63.1).
- Venue: Arctic-Text2SQL-R1 is listed in ACL 2026 Findings. — [ACL Anthology](https://preview.aclanthology.org/ingest-acl/2026.findings-acl.1345/)

### Inferences
- For self-hosted or private deployment, RL from execution on an SFT'd coder model is the route with the best evidence. A 7-32B model at about 70-72% on BIRD roughly matches CHASE-SQL from a single call, at much lower inference cost.
- The benefit shrinks with scale (OmniSQL 32B gains 0 over its base on BIRD dev). None of these specialised models handles enterprise SQL (Spider 2.0) well; frontier agents dominate there.

### Gaps
- The Reasoning-SQL and SQL-R1 ablation tables (partial rewards, schema-linking reward) were not fetched directly; only Arctic's re-comparison was used.
- I checked no 2026 RL papers other than Arctic.

## 6. Constrained decoding (PICARD, grammar-constrained, JSON-schema outputs)

### Takeaway
Constrained decoding was decisive for fine-tuned T5-era models: PICARD lets T5-Base beat an unconstrained T5-Large. I found no evidence that it improves frontier LLM accuracy on BIRD or Spider, where syntax errors are rare and most errors are semantic. 2026 evidence on small models suggests that inference-time techniques under grammar constraints are outperformed by simply using a bigger model. The evidence overall is weak.

### Cited Findings
- PICARD (2021): constrained decoding by incremental parsing made fine-tuned T5 state of the art on Spider and CoSQL. T5-Base with PICARD outperforms T5-Large without it. — [arXiv 2109.05093](https://arxiv.org/pdf/2109.05093)
- T5QL (2022): PICARD prunes beams and may produce no answer. With PICARD, T5-3B reaches about 75.5% EM against about 66.6% for T5-Base. T5QL's own constrained decoding reaches 69.3% EM with T5-Base. — [T5QL](https://ar5iv.labs.arxiv.org/html/2209.10254)
- Grammar-constrained small models (Qwen2.5 0.5B-7B 4-bit, Spider dev, Aug 2026): beam search and sample+vote help mostly at small sizes. A larger model usually beats more inference compute. Beam search beats sample+vote at a matched budget, which contrasts with unconstrained findings. The abstract gives no numbers. — [arXiv 2608.25761](https://arxiv.org/abs/2608.25761)
- Indirect evidence: in the long-context Gemini study, SQLite documentation did not help and errors were "mostly semantic". This is consistent with syntax constraints having little headroom for frontier models. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)

### Inferences
- Use constrained decoding or JSON-schema outputs for small or local models and for structural safety (valid, parseable, read-only queries), not to raise accuracy with frontier models.
- A related, non-SQL result: in a 7B multi-agent study, JSON-format communication between agents caused a large accuracy drop against plaintext (45 vs 82 on GSM8K) — [arXiv 2607.26922](https://arxiv.org/abs/2607.26922). Forcing structured output may hurt reasoning in small models.

### Gaps
- I found no measured study of JSON-schema or structured-output modes for Text-to-SQL with frontier models, and none on grammar-constrained SPARQL or Cypher.

## 7. Clarification / interactive disambiguation

### Takeaway
Ambiguity is a major remaining source of errors. A small study shows a very large gain when clarification is added (+50 pp EM on 40 hand-picked ambiguous queries), while a realistic conversational benchmark shows systems still struggle. Within non-interactive pipelines, automatic disambiguation adds under 1 pp. The evidence is weak and small-scale.

### Cited Findings
- AmbiSQL (Aug 2025, GPT-4o with XiYan-SQL): ambiguity detection reaches P 87.2 / R 89.1 / F1 88.2. On 40 ambiguous BIRD/TAG queries, EM rises from 42.5 to 92.5 with clarification (TAG 20 -> 85; BIRD 75 -> 100). The paper does not describe how the clarification answers were produced. — [arXiv 2508.15276v1](https://arxiv.org/html/2508.15276v1)
- PRACTIQ (NAACL 2025): a conversational dataset of ambiguous and unanswerable questions with clarify-then-answer turns. State-of-the-art systems struggle with these questions. — [arXiv 2410.11076](https://arxiv.org/html/2410.11076v1); [ACL Anthology](https://aclanthology.org/2025.naacl-long.13)
- Long-context Gemini pipeline: an automatic disambiguation step adds +0.71 pp on BIRD dev, and the authors recommend dropping it for latency. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)

### Inferences
- In benchmarks with annotated evidence (BIRD), the hints already resolve much of the ambiguity. In real deployments without hints, clarification likely matters far more, which supports a human-in-the-loop gate design.

### Gaps
- I found no large-scale clarification ablation with simulated users and frontier models.

## 8. Transfer to Text-to-SPARQL / Text-to-Cypher

### Takeaway
The same families reappear: schema or ontology pruning, similarity-selected few-shot examples, entity linking, verification and repair, and fine-tuning on synthetic data. The ablation evidence is much thinner, though, and mostly workshop-level. Entity linking plays the role that value retrieval plays in SQL, and studies repeatedly identify it as the key source of errors.

### Cited Findings
- Text2Cypher schema pruning: exact-match pruning worked best and shortened prompts about 6x (Llama-3.1-8B, Neo4j Text2Cypher 2024 dataset, 22,093 train / 2,471 test). The authors note it may not help advanced LLMs. — [Neo4j blog, Apr 2025](https://neo4j.com/blog/developer/schema-representation-in-text2cypher/)
- Auto-Cypher (NAACL 2025 short): a synthetic-data pipeline with LLM-supervised generation and verification, using "LLM-as-database-filler" to ensure Cypher correctness. — [papers.cool listing](https://papers.cool/venue/2025.naacl-short.53@ACL)
- Text-to-SPARQL on Digital Humanities KGs (2025): few-shot examples selected by semantic similarity work best, and error analysis flags entity linking as essential. The dataset has 477 questions, augmented to 1,895 by paraphrasing. — [CEUR Vol-4009 paper 12](https://ceur-ws.org/Vol-4009/paper_12.pdf)
- WikiKGQA 2026 submission: BM25-selected demonstrations and entity/property mention annotations substantially improve SPARQL generation. Query repair is also tested. — [CEUR Vol-4284 paper 3](https://ceur-ws.org/Vol-4284/paper3.pdf)
- D'Abramo et al. (KnowledgeNLP 2025): ICL with retrieved demonstrations plus multiple generated hypotheses gives state-of-the-art results on several KGQA benchmarks without fine-tuning. Few-shot and multi-candidate methods therefore transfer. — [ACL Anthology](https://preview.aclanthology.org/setup/2025.knowledgenlp-1.5)
- 2024 baseline assuming gold entity linking: 62.7% EM at 3-shot, with entity-linking F1 of 0.809. — [arXiv 2402.00969](https://arxiv.org/html/2402.00969v1)
- A 2025 survey on text-to-SPARQL/KGQA is available for further references. — [arXiv 2510.02200](https://arxiv.org/pdf/2510.02200v1)

### Inferences
- For an ontology/KG platform, the priorities are: (1) entity/IRI linking, the analogue of value retrieval; (2) ontology-module pruning, only when the ontology is large or the model is small; (3) similarity-selected examples; (4) execution-based repair and multi-candidate selection. Execution checks against Fuseki (non-empty results, SHACL/type consistency) are a natural analogue of SQL execution feedback, but no SPARQL ablation quantifies them.

### Gaps
- I found no SPARQL or Cypher paper with a CHASE-style component ablation table, and verified no RL-with-execution-reward study for SPARQL or Cypher. The numbers in this section are mostly qualitative.
