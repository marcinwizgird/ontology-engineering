# FIBO NL2Q at scale: ontology-grounded NL → SPARQL → SQL over all of FIBEN

Implements [`PLAN.md`](PLAN.md) on top of the verified SPARQL→SQL compiler in
[`../SPARQL-2-SQL`](../SPARQL-2-SQL). Evidence base:
[`knowledge/NL2Q/reports/NL2Query state of the art 2026.md`](../../../knowledge/NL2Q/reports/NL2Query%20state%20of%20the%20art%202026.md).

**Status (2026-10-19).** All offline phases are built and measured: P0 foundations, P1
gold SPARQL and the compiler ceiling, the rule-based baseline, the H1 grounding
experiment, and mutation testing of the metric. The language-model arms (S, A, B, T, G)
and the GEPA optimisation are implemented and tested offline, but **not yet run**: they
are billed and need approval. Results are in [`RESULTS.md`](RESULTS.md).

## What is here

| Module | Role |
|---|---|
| `nl2q/schema.py`, `load_fiben.py` | Parse the FIBEN DDL (152 tables: 135 subclass tables, 24 property FKs) and load 11.7M rows into DuckDB |
| `nl2q/gold.py` | Execute the 237 gold SQL queries (Db2 → DuckDB), store order-independent result signatures; gold on perturbed instances |
| `nl2q/fibo.py` | Full FIBO as the grounding search space (4,209 terms, 1,990 restriction edges) |
| `nl2q/vkg_build.py` | Generate the ontology, R2RML for all 152 tables, Ontop `db-metadata.json` and the FIBO alignment from the DDL |
| `nl2q/vkg.py` | SPARQL → SQL (Ontop sidecar on :18081, the SPARQL-2-SQL compiler) → DuckDB rows, with a timeout |
| `nl2q/sql2sparql.py`, `ceiling.py` | Deterministic gold SQL → SPARQL translation; the compiler ceiling |
| `nl2q/knowledge.py`, `glossary.py` | The knowledge pack: two-tier concept index (mapped / FIBO-known), value index (81,681 values), curated glossary (K4) |
| `nl2q/enrich.py`, `usgaap.py` | Semantic enrichment of the mapped terms without the glossary: the reviewed FIBO suggestions (`artifacts/knowledge/alignment_review.csv`), US GAAP 2015 definitions and labels, schema-derived definitions. Off by default (`NL2Q_ENRICH`); see RESULTS §5.1 |
| `nl2q/retrieval.py` | BM25, character n-gram TF-IDF, hybrid (RRF); value linking |
| `nl2q/querygraph.py`, `rerank.py`, `grounding.py` | Query graph with inherited edges; Steiner / k-shortest-path and Personalized-PageRank re-ranking; mentions → candidates → trees |
| `nl2q/ir.py`, `render.py`, `obqc.py` | Non-recursive plan IR, deterministic SPARQL rendering, restriction-aware ontology query checks (IR and free SPARQL) |
| `nl2q/planner_rules.py` | Arm R: a rule-based planner (no-LLM baseline and offline simulator) |
| `nl2q/program.py` | DSPy modules: arm S (mentions → plan → repair), A/B (direct SPARQL ± OBQC repair), T (text-to-SQL), G (tool agent) |
| `nl2q/evaluate.py`, `perturb.py`, `mutate.py`, `stats.py`, `splits.py` | Harness: outcomes, test-suite accuracy on 4 perturbed instances, refusal scoring, paired statistics, metric mutation testing |
| `nl2q/optimize.py` | GEPA optimisation of the DSPy program (governed loop) |
| `nl2q/h1.py` | H1 grounding experiment (offline part) |
| `artifacts/` | Versioned outputs: Ontop inputs, knowledge pack, gold signatures/SPARQL, splits, results |

## Running it

Needs Docker (Ontop sidecar image `fibo-ontop-sidecar`, built by the SPARQL-2-SQL PoC) and
Python with `duckdb`, `sqlglot`, `rdflib`, `networkx`, `scikit-learn`, `dspy`, `pydantic`.

```bash
# data (git-ignored): download FIBEN into data/raw/fiben (see PLAN.md §2), then
python -m nl2q.load_fiben          # ~2.5 min, 11.7M rows -> data/fiben_vkg.duckdb
python -m nl2q.vkg_build           # ontology, R2RML, db-metadata, alignment
docker run -d --name fiben-ontop-sidecar -p 18081:8080 \
  -e ONTOP_ONTOLOGY=fiben-ontology.ttl -e ONTOP_MAPPING=fiben-mapping.r2rml.ttl \
  -v "$(pwd)/artifacts/ontop:/opt/ontop/input:ro" fibo-ontop-sidecar
python -m nl2q.gold                # gold rows (signatures)
python -m nl2q.ceiling             # gold SPARQL + compiler ceiling
python -m nl2q.knowledge           # knowledge pack
# optional: US GAAP 2015 label linkbases (free, ~29 MB) for the enrichment, then
#   curl -O https://xbrl.fasb.org/us-gaap/2015/elts/us-gaap-{doc,lab}-2015-01-31.xml  (into data/raw/us-gaap-2015)
python -m nl2q.enrich              # enrichment.csv / .ttl / _summary.json; use with NL2Q_ENRICH=review,usgaap,derived
python -m nl2q.perturb             # perturbed instances (views + one materialised)
python -m pytest tests -q          # 32 offline tests

python -m nl2q.evaluate --arm R --split val     # offline baseline
python -m nl2q.h1 --split train                 # grounding experiment
python -m nl2q.mutate                           # does the metric catch wrong queries?

# live, billed — ask first:
NL2Q_MODEL=anthropic/claude-sonnet-5-5 python -m nl2q.evaluate --arm S --split val
NL2Q_MODEL=... NL2Q_REFLECTION_MODEL=anthropic/claude-opus-5-5 python -m nl2q.optimize --auto light
```

## Notes

* **Benchmark data mismatch.** The public FIBEN data is a regenerated instance:
  transactions span 2015-06 to 2016-06, prices are at most 200, and people have
  synthetic names. 96 of the 237 gold queries therefore return empty results. They are
  kept, flagged, and reported separately; accuracy on non-empty gold is the primary
  number.
* **Gold defects repaired:** sql_id 136 (unclosed `IN (` subquery) and 172 (truncated
  literal). Display caps (`FETCH FIRST n ROWS ONLY` without `ORDER BY`) are removed from
  gold answers; semantic `FETCH FIRST 1` inside scalar subqueries is kept.
* **A compiler gap found in the SPARQL-2-SQL PoC.** A projected timestamp
  (`TO_JSON(x)#>>'{}'` from Ontop) transpiles to `JSONB_EXTRACT_SCALAR`, which DuckDB
  lacks. Worked around in `nl2q/vkg.py`; the first PoC's compiler should get the same
  fix.
* **Glossary provenance.** The curated glossary was written after seeing FIBEN's gold SQL
  and may carry benchmark knowledge. The knowledge ablation (K1–K4) and the transfer set
  bound its effect.
