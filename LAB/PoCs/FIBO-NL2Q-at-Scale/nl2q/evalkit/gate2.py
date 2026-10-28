"""Gate 2: component metrics against the gold intermediates (specification §5, Gate 2).

Offline and free. The v1 components are measured as they are; the ports refactor (S5)
will run the same metrics on any adapter.

* **C1 + C2 retrieval.** Concept recall@k (k = 5, 10, 20) and MRR of the mapped terms the
  term index returns for the question's mentions (a value mention contributes the class
  and property of its linked values), against ``gold_tier1_iris``. The
  mentions' ranked lists are merged rank by rank (every mention's first hit, then every
  second hit, ...). MRR is the reciprocal rank of the first gold term.
* **Value linking F1** over ``(value, property)`` pairs against the string filter values,
  overall and on the properties the value index covers.
* **C3 grounding.** The pruned subgraph is the best re-ranked tree: its classes, its
  properties and the datatype properties of its classes (what the planner is shown).
  The **grounding ceiling** is the share of questions whose subgraph covers the gold
  terms: *literal*, and *equivalence-aware*, where a gold class also counts as covered
  by a superclass in the subgraph when the swap cannot change the answer (declared keys,
  ``v6.equivalent_under_constraints``, or no superclass-only individual on any instance).
  Alternative paths that pass the suite need a planner (C5) and are not counted yet.
  **Edge precision / recall**: tree edges against gold edges, strict and up to the class
  hierarchy; next to the subgraph's size in tokens (characters / 4).
* **C4 refusal.** The v1 rule gate (refuse when a mention matches an unmapped FIBO term
  or no connected tree exists) on the answerable questions plus ``U1``-``U3``.

Configurations vary retriever, knowledge level, enrichment (E0/E1) and glossary
(G0 / Gtrain / Gv1). Gv1 results are labelled *possibly contaminated*.

    python -m nl2q.evalkit.gate2 --split val
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from functools import lru_cache

from .. import grounding as G, knowledge, paths, querygraph, retrieval, schema, splits, vkg_build
from ..knowledge import VALUE_COLUMNS
from . import gold_intermediates, unanswerable, v6

OUT = paths.ARTIFACTS / "eval" / "gate2"
KS = (5, 10, 20)
E1 = ("review", "usgaap", "derived")
CONFIGS = [
    # (name, mode, level, enrichment, glossary)
    ("bm25-K1-E0-G0", "bm25", 1, (), "none"),
    ("hybrid-K1-E0-G0", "hybrid", 1, (), "none"),
    ("hybrid-K1-E1-G0", "hybrid", 1, E1, "none"),
    ("hybrid-K2-E0-G0", "hybrid", 2, (), "none"),
    ("hybrid-K4-E0-Gtrain", "hybrid", 4, (), "train"),
    ("hybrid-K4-E0-Gv1", "hybrid", 4, (), "v1"),
]
INDEXED = {(vkg_build.class_name(t), vkg_build.prop_name(c)) for t, c, _ in VALUE_COLUMNS}


# ----------------------------------------------------------------------------- retrieval
def ranked_terms(specs: list[G.MentionSpec], level: int, mode: str, depth: int = 20) -> list[str]:
    ti, vi = retrieval.term_index(level), retrieval.value_index()
    lists = []
    for s in specs:
        if s.kind == "value":                  # a linked value grounds its class and property
            lists.append([x for h in vi.link(s.text, depth // 2) for x in (h.cls, h.prop)])
        else:
            lists.append([h.local for h in ti.search(s.text, depth, mode=mode)])
    out, seen = [], set()
    for r in range(depth):
        for lst in lists:
            if r < len(lst) and lst[r] not in seen:
                seen.add(lst[r])
                out.append(lst[r])
    return out


def recall_mrr(ranked: list[str], gold: set[str]) -> dict:
    out = {f"recall@{k}": len(gold & set(ranked[:k])) / len(gold) for k in KS}
    out["mrr"] = next((1 / (i + 1) for i, t in enumerate(ranked) if t in gold), 0.0)
    return out


def value_pairs(specs: list[G.MentionSpec]) -> set[tuple[str, str, str]]:
    out = set()
    for s in specs:
        if s.kind == "value":
            hits = retrieval.value_index().link(s.text, 1)
            if hits:
                out.add((hits[0].value.lower(), hits[0].cls, hits[0].prop))
    return out


def prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "pred": n_pred, "gold": n_gold}


# ----------------------------------------------------------------------------- grounding
@lru_cache(maxsize=1)
def _hier():
    return v6.Hierarchy(schema.load())


@lru_cache(maxsize=None)
def superclass_only_rows(sub_cls: str, sup_cls: str) -> int:
    """Individuals of ``sup`` outside ``sub``, summed over every instance (0 = the data
    makes the swap equivalent)."""
    from ..load_fiben import connect
    from .gate1 import present_instances
    h = _hier()
    sub, sup = h.table_of[sub_cls], h.table_of[sup_cls]
    con = connect()
    n = 0
    for inst in present_instances(con):
        n += con.execute(f'SELECT count(*) FROM "{inst}"."{sup}" p WHERE NOT EXISTS (SELECT 1 FROM '
                         f'"{inst}"."{sub}" c WHERE c."{h.s.tables[sub].pk[0]}" = p."{h.s.tables[sup].pk[0]}")'
                         ).fetchone()[0]
    con.close()
    return n


def subgraph_terms(gr: G.GroundingResult) -> tuple[set[str], set[str], list[tuple[str, str, str]]]:
    qg = querygraph.load()
    best = gr.trees[0] if gr.trees else None
    if best is None:
        return set(), set(), []
    classes = set(best.classes) | {c.cls for c in best.choice if c.cls}
    classes |= {c.local for c in best.choice if c.kind == "class"}
    props = {p for _, p, _ in best.tree} | {c.local for c in best.choice if c.kind != "class"}
    for c in list(classes):
        props |= qg.attributes(c)
    return classes, props, list(best.tree)


def covered(gold_cls: str, classes: set[str], sparql: str) -> str | None:
    """How a gold class is covered: literal, or by an equivalent superclass."""
    if gold_cls in classes:
        return "literal"
    qg = querygraph.load()
    for sup in qg.ancestors(gold_cls):
        if sup in classes:
            if v6.equivalent_under_constraints(sparql, gold_cls, _hier()):
                return "keys"
            if superclass_only_rows(gold_cls, sup) == 0:
                return "data"
    return None


def _related(a: str, b: str) -> bool:
    qg = querygraph.load()
    return a == b or a in qg.ancestors(b) or b in qg.ancestors(a)


def edge_scores(tree: list[tuple], gold: list[tuple]) -> dict:
    t, g = {tuple(e) for e in tree}, {tuple(e) for e in gold}
    strict = len(t & g)
    relaxed_t = sum(any(p == gp and _related(s, gs) and _related(o, go) for gs, gp, go in g) for s, p, o in t)
    relaxed_g = sum(any(p == gp and _related(s, gs) and _related(o, go) for s, p, o in t) for gs, gp, go in g)
    return {"n_tree": len(t), "n_gold": len(g), "strict_tp": strict, "relaxed_tp_tree": relaxed_t,
            "relaxed_tp_gold": relaxed_g}


def tokens_of(classes: set[str], props: set[str], tree: list[tuple]) -> int:
    text = " ".join(sorted(classes)) + " " + " ".join(sorted(props)) + " " + \
           " ".join(f"{s} {p} {o}" for s, p, o in tree)
    return len(text) // 4


# ----------------------------------------------------------------------------- refusal
def rule_refuses(gr: G.GroundingResult) -> bool:
    return bool(gr.unmapped_hints) or gr.best is None


def refusal_metrics(ans_refused: list[bool], unans: dict[str, list[bool]]) -> dict:
    rec = {s: round(sum(v) / len(v), 4) for s, v in unans.items() if v}
    tp = sum(sum(v) for v in unans.values())
    n_u = sum(len(v) for v in unans.values())
    fp = sum(ans_refused)
    tpr = tp / n_u if n_u else 0.0
    fpr = fp / len(ans_refused) if ans_refused else 0.0
    at20 = (tpr * 0.2) / (tpr * 0.2 + fpr * 0.8) if tpr or fpr else 0.0
    return {"recall": rec, "recall_overall": round(tpr, 4), "false_refusal_rate": round(fpr, 4),
            "precision_observed": round(tp / (tp + fp), 4) if tp + fp else 0.0,
            "precision_at_20pct": round(at20, 4), "n_answerable": len(ans_refused), "n_unanswerable": n_u}


# ----------------------------------------------------------------------------- run
def run(split: str = "val") -> dict:
    gi = gold_intermediates.load()
    sparql = {str(r["sql_id"]): r["sparql"] for r in
              json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8")) if r.get("strict")}
    qs = [q for q in splits.questions(split) if str(q.sql_id) in gi["queries"]]
    un = unanswerable.items(split)
    res = {"split": split, "questions": len(qs), "gold_queries": len({q.sql_id for q in qs}),
           "unanswerable": len(un), "configs": {}}
    saved = knowledge.ENRICH, knowledge.GLOSSARY
    try:
        for name, mode, level, enrich, gloss in CONFIGS:
            knowledge.ENRICH, knowledge.GLOSSARY = enrich, gloss
            t0 = time.time()
            acc = defaultdict(list)
            vt = defaultdict(int)
            edges = defaultdict(int)
            cover = defaultdict(int)
            ans_ref = []
            for q in qs:
                it = gi["queries"][str(q.sql_id)]
                gold = set(it["gold_tier1_iris"])
                specs = G.rule_mentions(q.question)
                for k, v in recall_mrr(ranked_terms(specs, level, mode), gold).items():
                    acc[k].append(v)
                # value linking
                pred = value_pairs(specs)
                gv = {(d["value"].lower(), d["cls"], d["prop"]) for d in it["gold_filter_values"] if d["kind"] == "string"}
                pv, gvp = {(v, p) for v, _, p in pred}, {(v, p) for v, _, p in gv}
                vt["tp"] += len(pv & gvp)
                vt["pred"] += len(pv)
                vt["gold"] += len(gvp)
                gvi = {(v, p) for v, c, p in gv if (c, p) in INDEXED}
                pvi = {(v, p) for v, c, p in pred if (c, p) in INDEXED}
                vt["tp_i"] += len(pvi & gvi)
                vt["pred_i"] += len(pvi)
                vt["gold_i"] += len(gvi)
                # grounding
                gr = G.ground(q.question, specs, k=3, level=level, mode=mode)
                classes, props, tree = subgraph_terms(gr)
                gprops = gold - set(it["gold_classes"])
                lit = set(it["gold_classes"]) <= classes and gprops <= props
                how = {c: covered(c, classes, sparql[str(q.sql_id)]) for c in it["gold_classes"]}
                eq = all(how.values()) and gprops <= props
                cover["literal"] += lit
                cover["equivalence_aware"] += eq
                cover["via_keys"] += eq and "keys" in how.values()
                cover["via_data"] += eq and "data" in how.values()
                cover["connected"] += gr.best is not None
                for k2, v2 in edge_scores(tree, it["gold_subgraph_edges"]).items():
                    edges[k2] += v2
                acc["tokens"].append(tokens_of(classes, props, tree))
                acc["gold_class_recall"].append(len(set(it["gold_classes"]) & classes) / max(len(it["gold_classes"]), 1))
                ans_ref.append(rule_refuses(gr))
            unref = defaultdict(list)
            for u in un:
                gr = G.ground(u["question"], k=3, level=level, mode=mode)
                unref[u["stratum"]].append(rule_refuses(gr))
            n = len(qs)
            out = {k: round(sum(v) / n, 4) for k, v in acc.items()}
            out["value_linking"] = {"all_string": prf(vt["tp"], vt["pred"], vt["gold"]),
                                    "indexed_properties": prf(vt["tp_i"], vt["pred_i"], vt["gold_i"])}
            out["grounding_ceiling"] = {k: round(v / n, 4) for k, v in cover.items()}
            out["edges"] = {"precision_strict": round(edges["strict_tp"] / edges["n_tree"], 4) if edges["n_tree"] else 0.0,
                            "precision_relaxed": round(edges["relaxed_tp_tree"] / edges["n_tree"], 4) if edges["n_tree"] else 0.0,
                            "recall_strict": round(edges["strict_tp"] / edges["n_gold"], 4) if edges["n_gold"] else 0.0,
                            "recall_relaxed": round(edges["relaxed_tp_gold"] / edges["n_gold"], 4) if edges["n_gold"] else 0.0,
                            "tree_edges_per_q": round(edges["n_tree"] / n, 2)}
            out["refusal_rule_gate"] = refusal_metrics(ans_ref, unref)
            out["contamination"] = "possibly contaminated (Gv1 written after seeing all gold)" if gloss == "v1" else "clean"
            out["sec"] = round(time.time() - t0, 1)
            res["configs"][name] = out
            print(name, {k: out[k] for k in ("recall@5", "recall@20", "mrr")}, out["grounding_ceiling"],
                  f"{out['sec']}s", flush=True)
    finally:
        knowledge.ENRICH, knowledge.GLOSSARY = saved
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"gate2_{split}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (OUT / f"gate2_{split}.md").write_text(markdown(res), encoding="utf-8")
    return res


def _p(x: float) -> str:
    return f"{100 * x:.1f}%"


def markdown(res: dict) -> str:
    L = [f"# Gate 2: component metrics ({res['split']} split)", "",
         f"Generated by `python -m nl2q.evalkit.gate2 --split {res['split']}`; do not edit. "
         f"{res['questions']} answerable questions ({res['gold_queries']} gold queries), "
         f"{res['unanswerable']} unanswerable (U1-U3). Gv1 rows are *possibly contaminated*.", "",
         "## C1 + C2 retrieval and value linking", "",
         "| config | recall@5 | recall@10 | recall@20 | MRR | value F1 (all) | value F1 (indexed) |",
         "|---|---|---|---|---|---|---|"]
    for n, c in res["configs"].items():
        L.append(f"| {n} | {_p(c['recall@5'])} | {_p(c['recall@10'])} | {_p(c['recall@20'])} | {c['mrr']:.3f} | "
                 f"{c['value_linking']['all_string']['f1']:.3f} | {c['value_linking']['indexed_properties']['f1']:.3f} |")
    L += ["", "## C3 grounding", "",
          "| config | ceiling literal | ceiling equivalence-aware | gold class recall | edge P strict / relaxed | edge R strict / relaxed | tokens |",
          "|---|---|---|---|---|---|---|"]
    for n, c in res["configs"].items():
        g, e = c["grounding_ceiling"], c["edges"]
        L.append(f"| {n} | {_p(g['literal'])} | {_p(g['equivalence_aware'])} | {_p(c['gold_class_recall'])} | "
                 f"{_p(e['precision_strict'])} / {_p(e['precision_relaxed'])} | "
                 f"{_p(e['recall_strict'])} / {_p(e['recall_relaxed'])} | {c['tokens']:.0f} |")
    L += ["", "## C4 refusal (v1 rule gate)", "",
          "| config | recall U1 | recall U2 | recall U3 | false refusals | precision @20% |", "|---|---|---|---|---|---|"]
    for n, c in res["configs"].items():
        r = c["refusal_rule_gate"]
        L.append(f"| {n} | {_p(r['recall'].get('U1', 0))} | {_p(r['recall'].get('U2', 0))} | "
                 f"{_p(r['recall'].get('U3', 0))} | {_p(r['false_refusal_rate'])} | {_p(r['precision_at_20pct'])} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="val")
    run(ap.parse_args().split)
