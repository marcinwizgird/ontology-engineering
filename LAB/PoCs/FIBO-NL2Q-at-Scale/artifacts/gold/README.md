# Gold artefacts

| File | Content | Produced by |
|---|---|---|
| `gold_sql.json` | 237 gold SQL queries transpiled to DuckDB; per query a result **signature** (row count, per-column and row-multiset digests, 20 sample rows) | `python -m nl2q.gold` |
| `gold_variants.json` | The same signatures on the four perturbed instances V1–V4 | `gold.run_gold_variants()` |
| `gold_sparql.json` | The deterministic SPARQL translation of every gold query, with its compile/execute outcome and whether it reproduces the gold rows | `python -m nl2q.ceiling` |
| `ceiling.md` | The compiler ceiling per query type | `python -m nl2q.ceiling` |
| `splits.json` | train / val / test by gold query id (seed 20261019) | `nl2q.splits` |
| `unanswerable.json` | 24 hand-written questions this mapping cannot answer (gold outcome: refuse) | written for the PoC |
| `h1_train.json` | Grounding experiment results | `python -m nl2q.h1` |
| `mutation.json` | Metric mutation testing | `python -m nl2q.mutate` |

## FIBEN gold defects found and repaired

* **sql_id 136**: the `IN (` subquery is never closed. Repaired by closing it.
* **sql_id 172**: the last literal is truncated (`'2017-12-31 23:59:00.000` with no closing
  quote). Repaired by closing it.
* **Display caps.** `FETCH FIRST 1000 ROWS ONLY` without `ORDER BY` selects an arbitrary
  subset, so it is removed for gold answers. A `FETCH FIRST 1` inside a scalar subquery is
  semantic and kept (removing it breaks 5 queries).
* **Relative dates.** `CURRENT DATE` is fixed to 2018-01-01. No accepted gold query
  depends on it.

## Benchmark data mismatch

The published data is a regenerated instance:
* transactions span 2015-06-15 to 2016-06-15;
* last traded values are at most 199.84;
* people have synthetic names.

Questions written against the original instance ("bought on 17 May 2016", "last traded
value above 1500", "Hakon Schuster") therefore return no rows. 96 of the 237 gold
queries have empty gold results. They cannot tell a right query from many wrong ones, so
they are flagged in every result and accuracy on non-empty gold is reported separately.
