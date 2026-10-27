"""H1 (offline part): grounding quality per retriever x knowledge level x re-ranker.

For every question the same mentions are used (rule-based, so the comparison isolates
retrieval and re-ranking); gold concepts are the ontology terms of the accepted gold
SPARQL. Metrics:

* ``cand_recall`` — share of gold terms among all candidates (what the planner can see);
* ``tree_recall`` / ``tree_precision`` — gold terms in the best re-ranked tree;
* ``connected`` — share of questions with a connected best tree;
* ``context_terms`` — how many distinct terms the planner is shown (cost proxy). The
  whole-ontology-in-context baseline shows all 220 mapped terms with recall 1 by
  construction; the question H1 asks is whether grounding keeps recall while showing
  far fewer terms, and whether the graph helps choose.

Each configuration also names the semantic-enrichment layers of the knowledge pack
(``nl2q.enrich``). The original configurations run with none, as published; the ``+E``
configurations add the layers cumulatively (reviewed FIBO, US GAAP, derived) to measure
how far enrichment alone, with no glossary, lifts recall.

    python -m nl2q.h1 --split train
"""

from __future__ import annotations

import argparse
import json
import time

from . import evaluate, grounding as G, knowledge, paths, splits

R, RU, RUD = ("review",), ("review", "usgaap"), ("review", "usgaap", "derived")
CONFIGS = [
    # (name, mode, level, scorer, enrichment layers)
    ("bm25-K1", "bm25", 1, "steiner", ()),
    ("tfidf-K1", "tfidf", 1, "steiner", ()),
    ("hybrid-K1", "hybrid", 1, "steiner", ()),
    ("hybrid-K2", "hybrid", 2, "steiner", ()),
    ("hybrid-K4", "hybrid", 4, "steiner", ()),
    ("hybrid-K4-ppr", "hybrid", 4, "ppr", ()),
    ("hybrid-K4-k5", "hybrid", 4, "steiner-k5", ()),
    # semantic enrichment, no glossary
    ("bm25-K1+E", "bm25", 1, "steiner", RUD),
    ("tfidf-K1+E", "tfidf", 1, "steiner", RUD),
    ("hybrid-K1+E:review", "hybrid", 1, "steiner", R),
    ("hybrid-K1+E:review,usgaap", "hybrid", 1, "steiner", RU),
    ("hybrid-K1+E", "hybrid", 1, "steiner", RUD),
    ("hybrid-K2+E:review,usgaap", "hybrid", 2, "steiner", RU),
    ("hybrid-K2+E", "hybrid", 2, "steiner", RUD),
    # enrichment and the glossary together
    ("hybrid-K4+E", "hybrid", 4, "steiner", RUD),
]


def run(split: str = "train") -> dict:
    concepts = evaluate.gold_concepts()
    qs = [q for q in splits.questions(split) if q.sql_id in concepts]
    res = {}
    for name, mode, level, scorer, layers in CONFIGS:
        knowledge.ENRICH = layers
        k = 5 if scorer.endswith("k5") else 3
        sc = scorer.split("-")[0]
        cr, tr, tp, conn, ctx = [], [], [], 0, []
        t0 = time.time()
        for q in qs:
            gc = concepts[q.sql_id]
            specs = G.rule_mentions(q.question)
            gr = G.ground(q.question, specs, k=k, level=level, mode=mode, scorer=sc)
            cands = {c.local for m in gr.mentions for c in m.candidates} | \
                    {c.cls for m in gr.mentions for c in m.candidates if c.cls}
            for t in gr.trees:
                cands |= set(t.classes) | {x for s, p, o in t.tree for x in (s, p, o)}
            cr.append(len(gc & cands) / len(gc))
            best = gr.concepts()
            tr.append(len(gc & best) / len(gc))
            tp.append(len(gc & best) / len(best) if best else 0.0)
            conn += gr.best is not None
            ctx.append(len(cands))
        n = len(qs)
        res[name] = {"n": n, "cand_recall": round(sum(cr) / n, 3), "tree_recall": round(sum(tr) / n, 3),
                     "tree_precision": round(sum(tp) / n, 3), "connected": round(conn / n, 3),
                     "context_terms": round(sum(ctx) / n, 1), "sec": round(time.time() - t0, 1),
                     "enrichment": list(layers)}
        print(name, res[name])
    res["in_context_baseline"] = {"cand_recall": 1.0, "context_terms": 220}
    (paths.GOLD_DIR / f"h1_{split}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    run(ap.parse_args().split)
