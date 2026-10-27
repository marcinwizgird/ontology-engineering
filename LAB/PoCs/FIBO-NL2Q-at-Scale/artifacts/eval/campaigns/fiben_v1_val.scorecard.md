# Scorecard: FIBEN v1 small live check

* Dataset / split: FIBEN-Standard / val; date 2026-10-19/20; model anthropic/claude-sonnet-5-5 (snapshot not pinned in v1)
* Baseline for comparisons: arm T
* v1 predates the Semantic Ladder: arms are mapped to their nearest rung, one run each, unanswerable suite unstratified (24 questions, results reconstructed from the run summaries). K4 runs used the v1 glossary (Gv1), which was written after seeing all gold SQL: those results are possibly contaminated (spec §4.5).

Intervals: 95% bootstrap resampling gold queries (paraphrases move together), runs nested in questions; comparisons: exact McNemar on majority outcomes, Holm-corrected across the table; MDE: smallest difference detectable at power 0.8 (spec §5.5).

## Table A: Gate 1 build & ontology health

Not yet produced: Gate 1 is implementation stage S3 (spec §8).

## Table B: Gate 3 oracle ceilings

Not yet produced: the C1–C6 ports and oracle adapters are stage S5 (spec §8).

## Table C: Gate 4 comparison

| Arm | Rung | E / G | n | Suite EX | Suite EX in ceiling | Hierarchy slice | Nested slice | Wrong-but-executed ↓ | Refusal recall · false-refusal ↓ | Utility c=2 / c=5 (floor) | Δ suite EX vs T | Δ wrong vs T | Stability | P95 s | $/q · $/correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R: rules, no LLM | floor | E0 / Gv1 | 63 | 9.5% [2%–19%] | 10.7% [2%–22%] | 11.5% [0%–27%] | 7.9% (n=38) | 76.2% [63%–88%] | 4% · 12.7% | -1.59 / -4.04 (-0.13) | -18.6% [-31%, -7%], p=0.00 (Holm 0.03), MDE 17% | +3.4% [-14%, +20%], p=0.82 (Holm 1.00), MDE 21% | — | 3.28 | 0.000 · — |
| T: text-to-SQL over the DDL | L0 (T-Raw) | - / G0 | 59 | 28.8% [16%–42%] | 31.5% [19%–46%] | 20.8% [5%–41%] | 14.7% (n=34) | 71.2% [58%–84%] | — · 0.0% | -1.14 / -3.27 (-0.30) | — | — | — | 8.59 | 0.085 · 0.30 |
| A: direct SPARQL | L2 without OBQC | E0 / Gv1 | 63 | 19.1% [10%–30%] | 19.6% [10%–31%] | 11.5% [0%–26%] | 10.5% (n=38) | 63.5% [51%–75%] | 0% · 0.0% | -1.33 / -3.54 (-0.13) | -10.2% [-18%, -3%], p=0.03 (Holm 0.25), MDE 12% | -5.1% [-17%, +7%], p=0.55 (Holm 1.00), MDE 16% | — | 4.78 | 0.012 · 0.06 |
| B: direct SPARQL + OBQC + repair | L2 (B-TBox) | E0 / Gv1 | 63 | 20.6% [10%–33%] | 21.4% [11%–34%] | 11.5% [0%–26%] | 13.2% (n=38) | 79.4% [67%–90%] | 4% · 0.0% | -1.53 / -4.04 (-0.13) | -8.5% [-16%, -2%], p=0.06 (Holm 0.44), MDE 11% | +8.5% [+2%, +16%], p=0.06 (Holm 0.44), MDE 11% | — | 15.26 | 0.015 · 0.07 |
| S: grounding + IR plan + checks | v1 S (L3 precursor) | E0 / Gv1 | 63 | 25.4% [15%–38%] | 28.6% [17%–43%] | 23.1% [8%–43%] | 5.3% (n=38) | 46.0% [33%–59%] | 100% · 28.6% | -0.46 / -1.46 (-0.13) | -1.7% [-11%, +8%], p=1.00 (Holm 1.00), MDE 13% | -25.4% [-39%, -12%], p=0.00 (Holm 0.00), MDE 20% | — | 13.64 | 0.018 · 0.07 |
| S2: S + link neighbourhood | v1 S2 | E0 / Gv1 | 63 | 20.6% [11%–32%] | 23.2% [13%–36%] | 15.4% [3%–33%] | 5.3% (n=38) | 63.5% [51%–75%] | 96% · 15.9% | -0.75 / -2.16 (-0.13) | -6.8% [-17%, +3%], p=0.29 (Holm 1.00), MDE 13% | -6.8% [-18%, +3%], p=0.34 (Holm 1.00), MDE 15% | — | 14.7 | 0.020 · 0.10 |
| G: tool agent (schema browse + SQL) | Arm G | - / G0 | 57 | 8.8% [2%–18%] | 9.6% [2%–19%] | 4.5% [0%–15%] | 3.1% (n=32) | 8.8% [2%–17%] | — · 73.7% | -0.31 / -0.57 (-0.30) | -21.1% [-35%, -10%], p=0.00 (Holm 0.02), MDE 18% | -61.4% [-75%, -47%], p=0.00 (Holm 0.00), MDE 29% | — | 57.87 | 0.134 · 1.53 |

Notes:
* **T**: stopped at the budget cap after 59 questions
* **G**: stopped at the budget cap after 57 questions; most refusals are step exhaustion
* Utility without an unanswerable suite scores answerable questions only (floor −0.30); with it, answering an unanswerable question counts as wrong-but-executed.
* Stability needs ≥ 2 runs; tokens per question are recorded from stage S5 on.

## Table D: reproducibility & curation

v1 runs did not record the pins of spec §5.5.6 (model snapshot, program and pack hashes); they are reportable only as exploratory evidence. Curation hours were not logged.
