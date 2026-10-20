"""GEPA optimisation of the DSPy program (hypothesis H3). **Live and billed: ask first.**

GEPA (Agrawal et al., ICLR 2026) evolves the instructions of the program's predictors
(M1 mentions, M2 planner, M3 repair) by reflecting on textual feedback. The metric below
returns a score in [0, 1] — wrong answers score *below* refusals — and feedback built
from deterministic signals:

* the outcome (correct / wrong / refused / failed) and, for wrong answers, the row-count
  difference and a sample of gold rows (train/val only — never test);
* the ontology check and compiler messages;
* grounding misses: ontology terms the gold query uses that the plan did not.

Self-evolution is a governed loop (PLAN.md §4.4): GEPA proposes a program version on
train/val; the frozen test split and a human release gate decide whether it ships. The
optimised program is saved with its id; every answer records which version produced it.

    NL2Q_MODEL=anthropic/claude-sonnet-5-5 NL2Q_REFLECTION_MODEL=anthropic/claude-opus-5-5 \\
        python -m nl2q.optimize --auto light
"""

from __future__ import annotations

import argparse
import json
import os
import time

import dspy

from . import evaluate, gold, paths, splits
from .program import NL2SPARQL, make_lm

SCORE = {"correct": 1.0, "refused": 0.25, "failed": 0.1, "wrong": 0.0}


def examples(split: str) -> list[dspy.Example]:
    out = [dspy.Example(question=q.question, qid=q.qid, sql_id=q.sql_id).with_inputs("question")
           for q in splits.questions(split)]
    un = json.loads((paths.GOLD_DIR / "unanswerable.json").read_text(encoding="utf-8"))["questions"]
    # half of the unanswerable set trains refusals; the other half stays for testing
    pick = un[::2] if split == "train" else un[1::2] if split == "val" else []
    out += [dspy.Example(question=u["question"], qid=-1, sql_id=-1, why=u["why"]).with_inputs("question")
            for u in pick]
    return out


class Metric:
    def __init__(self):
        self.golds = gold.load_results()
        self.concepts = evaluate.gold_concepts()
        self.qs = {q.qid: q for q in gold.questions()}

    def __call__(self, example, pred, trace=None, pred_name=None, pred_trace=None):
        if example.sql_id == -1:                      # unanswerable
            refused = bool(getattr(pred, "refused", False))
            fb = ("Correctly refused." if refused else
                  f"This question cannot be answered from the data ({example.why}); the plan "
                  "should have been answerable=false with that reason instead of a query.")
            return dspy.Prediction(score=1.0 if refused else 0.0, feedback=fb)
        q = self.qs[example.qid]
        g = self.golds[q.sql_id]
        o = evaluate.score("S", q, pred, g, None, self.concepts)
        fb = [f"Outcome: {o.outcome}."]
        if o.outcome == "wrong":
            fb.append(f"Returned {o.pred_rows} rows; the correct answer has {g.row_count} rows "
                      f"({o.error}). Gold sample: {g.sig.sample[:3]}")
        if o.outcome == "refused":
            fb.append(f"Refused although the data can answer it. Reason given: {o.reason[:200]}")
        if o.outcome == "failed":
            fb.append(f"The query did not execute: {o.error[:300]}")
        probs = getattr(pred, "problems", None)
        if probs:
            fb.append("Checker messages: " + " | ".join(probs[:5]))
        gc = self.concepts.get(q.sql_id)
        plan = getattr(pred, "plan", None)
        if gc and plan is not None and o.outcome != "correct":
            pc = {n.cls for n in plan.nodes} | {l.prop for l in plan.links} | {a.prop for a in plan.attrs}
            missing = sorted(gc - pc)
            extra = sorted(pc - gc)
            if missing:
                fb.append(f"The correct query uses these ontology terms the plan did not: {missing}.")
            if extra:
                fb.append(f"The plan used terms the correct query does not need: {extra}.")
        return dspy.Prediction(score=SCORE[o.outcome], feedback=" ".join(fb))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", default="light", choices=["light", "medium", "heavy"])
    ap.add_argument("--max-metric-calls", type=int)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    lm = make_lm()
    refl = make_lm(os.environ.get("NL2Q_REFLECTION_MODEL") or os.environ.get("NL2Q_MODEL"))
    if lm is None:
        raise SystemExit("set NL2Q_MODEL (live, billed — ask first)")
    dspy.configure(lm=lm)
    run_dir = paths.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-gepa")
    run_dir.mkdir(parents=True, exist_ok=True)
    kw = {"max_metric_calls": a.max_metric_calls} if a.max_metric_calls else {"auto": a.auto}
    opt = dspy.GEPA(metric=Metric(), reflection_lm=refl, num_threads=a.threads, track_stats=True,
                    log_dir=str(run_dir / "gepa"), seed=0, **kw)
    best = opt.compile(NL2SPARQL(), trainset=examples("train"), valset=examples("val"))
    best.save(str(run_dir / "program.json"))
    cost = sum((h.get("cost") or 0.0) for h in lm.history) + (
        sum((h.get("cost") or 0.0) for h in refl.history) if refl is not lm else 0.0)
    (run_dir / "meta.json").write_text(json.dumps({"model": lm.model, "reflection": refl.model,
                                                   "budget": kw, "cost_usd": round(cost, 2)}, indent=1))
    print(f"optimised program -> {run_dir / 'program.json'} (cost ${cost:.2f})")


if __name__ == "__main__":
    main()
