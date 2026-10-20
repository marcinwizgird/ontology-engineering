"""The evaluation harness: run an arm on a split, execute, score, summarise.

Outcomes per question (mutually exclusive):

* ``correct``  — rows equal the gold rows (strict) on the base database;
* ``wrong``    — the query executed but the rows differ (the costly failure);
* ``refused``  — the system declined to answer (plan not answerable, checks failed);
* ``failed``   — the system produced a query that did not compile/execute.

``suite`` additionally requires equality on every perturbed instance (test-suite
accuracy). Questions whose gold result is empty are flagged — they cannot discriminate
and are reported separately. The penalty score counts +1 correct, 0 refused/failed,
−c wrong (c = 1 and 5); the abstain-on-everything floor is 0.

    python -m nl2q.evaluate --arm R --split val
    NL2Q_MODEL=anthropic/claude-sonnet-5-5 python -m nl2q.evaluate --arm S --split val   # live, billed
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import compare, gold, paths, splits, stats, vkg

VARIANTS = ("V1", "V2", "V3", "V4", "V5")


@dataclass
class Outcome:
    arm: str
    qid: int
    sql_id: int
    query_type: str
    question: str
    outcome: str = ""
    suite: bool = False
    lenient: bool = False
    gold_empty: bool = False
    query: str | None = None
    reason: str = ""
    error: str = ""
    pred_rows: int = 0
    ms_system: int = 0
    ms_exec: int = 0
    cost_usd: float = 0.0
    concept_recall: float | None = None
    candidate_recall: float | None = None
    concept_precision: float | None = None
    repairs: int = 0
    plan: dict | None = None


# ----------------------------------------------------------------------------- #
_FIBEN = re.compile(r"fiben:([A-Za-z][A-Za-z0-9]*)")


def gold_concepts() -> dict[int, set[str]]:
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    return {r["sql_id"]: set(_FIBEN.findall(r["sparql"] or "")) for r in rows if r.get("strict")}


def _execute(pred, variant: str | None = None):
    """-> (ok, rows, ncols, stage, error, ms)"""
    t0 = time.perf_counter()
    if getattr(pred, "sparql", None):
        ex = vkg.run_guarded(pred.sparql, row_cap=5_000_000, timeout_s=60,
                             schema=None if variant is None else f"{paths.SCHEMA}_{variant}")
        return ex.ok, ex.rows, len(ex.columns), ex.stage, ex.error, round((time.perf_counter() - t0) * 1e3)
    sql = getattr(pred, "sql", None)
    if sql:
        # model-written SQL runs in a killable worker process (DuckDB interrupt is not reliable)
        from .sqlworker import worker
        sp = paths.SCHEMA if variant is None else f"{paths.SCHEMA}_{variant}"
        try:
            q = sql if variant is None else vkg.retarget(sql, sp)
        except Exception as exc:  # noqa: BLE001
            return False, [], 0, "execute", f"retarget: {str(exc)[:200]}", 0
        status, cols, rows = worker().run(q, search_path=sp, timeout_s=60)
        if status != "ok":
            return False, [], 0, "execute", str(cols)[:300], 0
        return True, rows, len(cols), "", "", round((time.perf_counter() - t0) * 1e3)
    return False, [], 0, "none", "no query", 0


def score(arm: str, q: gold.Question, pred, g: gold.GoldResult,
          gv: dict[str, dict[int, compare.Signature]] | None,
          concepts: dict[int, set[str]] | None = None) -> Outcome:
    o = Outcome(arm, q.qid, q.sql_id, q.query_type, q.question, gold_empty=g.row_count == 0,
                ms_system=int(getattr(pred, "ms", 0) or 0))
    o.query = getattr(pred, "sparql", None) or getattr(pred, "sql", None)
    plan = getattr(pred, "plan", None)
    if plan is not None:
        o.plan = plan.model_dump(exclude_defaults=True)
        o.repairs = sum(1 for s in (getattr(pred, "trace", None) or []) if s.get("step") == "check") - 1
    if concepts and q.sql_id in concepts and plan is not None:
        gc = concepts[q.sql_id]
        pc = {n.cls for n in plan.nodes} | {l.prop for l in plan.links} | {a.prop for a in plan.attrs}
        o.concept_recall = round(len(gc & pc) / len(gc), 3) if gc else None
        o.concept_precision = round(len(gc & pc) / len(pc), 3) if pc else None
        cands = set(getattr(pred, "candidates", []) or [])
        o.candidate_recall = round(len(gc & cands) / len(gc), 3) if gc else None
    if getattr(pred, "refused", False) or not o.query:
        o.outcome, o.reason = "refused", (getattr(pred, "reason", "") or "")[:300]
        return o
    ok, rows, ncols, stage, err, ms = _execute(pred)
    o.ms_exec = ms
    if not ok:
        o.outcome, o.error = "failed", f"{stage}: {err}"[:300]
        return o
    o.pred_rows = len(rows)
    m = compare.compare(g.sig, rows, ncols)
    o.lenient = m.lenient
    if not m.strict:
        o.outcome, o.error = "wrong", m.reason
        return o
    o.outcome = "correct"
    o.suite = True
    if gv:
        for v in VARIANTS:
            sig = gv.get(v, {}).get(q.sql_id)
            if sig is None:
                continue
            okv, rv, nv, _, _, _ = _execute(pred, v)
            if not okv or not compare.compare(sig, rv, nv).strict:
                o.suite = False
                o.error = f"differs on {v}"
                break
    return o


# ----------------------------------------------------------------------------- #
#: USD per million tokens (input, output, cache read) — Anthropic list prices, 2026-10
PRICES = {"claude-sonnet-5-5": (2.0, 10.0, 0.20), "claude-opus-5-5": (4.0, 20.0, 0.20),
          "claude-haiku-5-5": (0.10, 0.50, 0.01)}


def entry_cost(h: dict, model: str) -> float:
    """LiteLLM's cost when it knows the model, else computed from token usage."""
    if h.get("cost"):
        return float(h["cost"])
    u = h.get("usage") or {}
    key = next((k for k in PRICES if k in model), None)
    if key is None:
        return 0.0
    pin, pout, pcache = PRICES[key]
    det = u.get("prompt_tokens_details")
    det_cached = det.get("cached_tokens", 0) if isinstance(det, dict) else getattr(det, "cached_tokens", 0)
    cached = det_cached or u.get("cache_read_input_tokens", 0) or 0
    prompt = (u.get("prompt_tokens") or 0) - cached
    return (prompt * pin + cached * pcache + (u.get("completion_tokens") or 0) * pout) / 1e6


def _cost_since(lm, start: int) -> float:
    if lm is None:
        return 0.0
    return float(sum(entry_cost(h, lm.model) for h in lm.history[start:]))


class BudgetExceeded(RuntimeError):
    pass


def check_budget(lm) -> float:
    """Hard stop for live runs: NL2Q_BUDGET_USD caps the spend of this process."""
    import os
    spent = _cost_since(lm, 0)
    cap = float(os.environ.get("NL2Q_BUDGET_USD", "0") or 0)
    if cap and spent >= cap:
        raise BudgetExceeded(f"budget US${cap:.2f} reached (spent US${spent:.2f})")
    return spent


def run(arm: str, split: str = "val", limit: int | None = None, variants: bool = True,
        program=None, out_dir: Path | None = None, verbose: bool = True,
        question_ids: list[int] | None = None) -> list[Outcome]:
    import dspy
    from .program import ARMS, LIVE_ARMS, make_lm
    lm = None
    if arm in LIVE_ARMS:
        lm = dspy.settings.lm or make_lm()
        if lm is None:
            raise SystemExit(f"arm {arm} needs a model: set NL2Q_MODEL (live, billed — ask first)")
        dspy.configure(lm=lm)
    prog = program or ARMS[arm]()
    golds = gold.load_results()
    gv = gold.load_variants() if variants else None
    concepts = gold_concepts()
    qs = splits.questions(split)
    if question_ids:
        qs = [q for q in qs if q.qid in set(question_ids)]
    if limit:
        qs = qs[:limit]
    out: list[Outcome] = []
    for i, q in enumerate(qs):
        if lm is not None:
            try:
                check_budget(lm)
            except BudgetExceeded as exc:
                print(f"STOP: {exc}")
                break
        start = len(lm.history) if lm is not None else 0
        try:
            pred = prog(question=q.question)
        except Exception as exc:  # noqa: BLE001
            o = Outcome(arm, q.qid, q.sql_id, q.query_type, q.question, outcome="failed",
                        error=f"system: {type(exc).__name__}: {str(exc)[:200]}",
                        gold_empty=golds[q.sql_id].row_count == 0)
            out.append(o)
            continue
        o = score(arm, q, pred, golds[q.sql_id], gv, concepts)
        o.cost_usd = round(_cost_since(lm, start), 5)
        out.append(o)
        if out_dir is not None:                 # incremental: a hang never loses the run
            out_dir.mkdir(parents=True, exist_ok=True)
            with (out_dir / f"{arm}_{split}.partial.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(o), default=str) + "\n")
        if verbose:
            print(f"[{i + 1}/{len(qs)}] {o.outcome:8s} suite={int(o.suite)} {q.query_type:10s} {q.question[:70]}")
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{arm}_{split}.jsonl").write_text(
            "\n".join(json.dumps(asdict(o), default=str) for o in out), encoding="utf-8")
    return out


def run_unanswerable(arm: str, program=None) -> list[dict]:
    """Refusal precision/recall: the hand-written unanswerable set."""
    import dspy
    from .program import ARMS, LIVE_ARMS, make_lm
    if arm in LIVE_ARMS:
        dspy.configure(lm=dspy.settings.lm or make_lm())
    prog = program or ARMS[arm]()
    data = json.loads((paths.GOLD_DIR / "unanswerable.json").read_text(encoding="utf-8"))
    res = []
    lm = dspy.settings.lm if arm in LIVE_ARMS else None
    for item in data["questions"]:
        if lm is not None:
            try:
                check_budget(lm)
            except BudgetExceeded as exc:
                print(f"STOP (unanswerable): {exc}")
                break
        try:
            p = prog(question=item["question"])
            refused = bool(getattr(p, "refused", False)) or not (getattr(p, "sparql", None) or getattr(p, "sql", None))
        except Exception:  # noqa: BLE001
            refused = True
        res.append({"id": item["id"], "refused": refused})
    return res


# ----------------------------------------------------------------------------- #
def summarize(outs: list[Outcome], unanswerable: list[dict] | None = None,
              answered_controls: list[Outcome] | None = None) -> dict:
    n = len(outs)
    c = Counter(o.outcome for o in outs)
    ne = [o for o in outs if not o.gold_empty]
    s = {
        "n": n,
        "EX": round(c["correct"] / n, 4) if n else None,
        "EX_ci": stats.bootstrap_ci([float(o.outcome == "correct") for o in outs])[1:] if n else None,
        "suite_EX": round(sum(o.suite for o in outs) / n, 4) if n else None,
        "EX_nonempty_gold": round(sum(o.outcome == "correct" for o in ne) / len(ne), 4) if ne else None,
        "n_nonempty_gold": len(ne),
        "lenient_EX": round(sum(o.lenient for o in outs) / n, 4) if n else None,
        "wrong_but_executed": round(c["wrong"] / n, 4) if n else None,
        "refused": round(c["refused"] / n, 4) if n else None,
        "failed": round(c["failed"] / n, 4) if n else None,
        "penalty_c1": round(sum({"correct": 1, "wrong": -1}.get(o.outcome, 0) for o in outs) / n, 4) if n else None,
        "penalty_c5": round(sum({"correct": 1, "wrong": -5}.get(o.outcome, 0) for o in outs) / n, 4) if n else None,
        "selective_accuracy": round(c["correct"] / (c["correct"] + c["wrong"]), 4) if c["correct"] + c["wrong"] else None,
        "cost_usd_total": round(sum(o.cost_usd for o in outs), 4),
        "cost_usd_per_q": round(sum(o.cost_usd for o in outs) / n, 5) if n else None,
        "latency_ms_p50": sorted(o.ms_system + o.ms_exec for o in outs)[n // 2] if n else None,
        "latency_ms_p95": sorted(o.ms_system + o.ms_exec for o in outs)[min(n - 1, int(0.95 * n))] if n else None,
    }
    rec = [o.concept_recall for o in outs if o.concept_recall is not None]
    crec = [o.candidate_recall for o in outs if o.candidate_recall is not None]
    if rec:
        s["concept_recall_plan"] = round(sum(rec) / len(rec), 4)
    if crec:
        s["concept_recall_candidates"] = round(sum(crec) / len(crec), 4)
    by = defaultdict(list)
    for o in outs:
        by[o.query_type].append(o)
    s["by_type"] = {t: {"n": len(v), "EX": round(sum(x.outcome == "correct" for x in v) / len(v), 3),
                        "suite": round(sum(x.suite for x in v) / len(v), 3)} for t, v in sorted(by.items())}
    if unanswerable is not None:
        tp = sum(u["refused"] for u in unanswerable)
        fp = sum(o.outcome == "refused" for o in (answered_controls or outs))
        s["refusal_recall_unanswerable"] = round(tp / len(unanswerable), 4)
        s["refusal_precision"] = round(tp / (tp + fp), 4) if tp + fp else None
    return s


def markdown(arm: str, split: str, s: dict) -> str:
    keys = ["n", "EX", "EX_ci", "suite_EX", "EX_nonempty_gold", "n_nonempty_gold", "lenient_EX",
            "wrong_but_executed", "refused", "failed", "selective_accuracy", "penalty_c1", "penalty_c5",
            "refusal_recall_unanswerable", "refusal_precision", "concept_recall_candidates",
            "concept_recall_plan", "cost_usd_per_q", "latency_ms_p50", "latency_ms_p95"]
    lines = [f"### arm {arm} on {split}", "", "| metric | value |", "|---|---|"]
    for k in keys:
        if k in s and s[k] is not None:
            v = s[k]
            if isinstance(v, (list, tuple)):
                v = "[" + ", ".join(f"{x:.3f}" for x in v) + "]"
            lines.append(f"| {k} | {v} |")
    lines += ["", "| query type | n | EX | suite EX |", "|---|---|---|---|"]
    lines += [f"| {t} | {d['n']} | {d['EX']} | {d['suite']} |" for t, d in s["by_type"].items()]
    return "\n".join(lines)


def compare_arms(a: list[Outcome], b: list[Outcome]) -> dict:
    """Paired comparison on the same questions (exact McNemar + bootstrap of the difference)."""
    ka = {o.qid: o for o in a}
    kb = {o.qid: o for o in b}
    common = sorted(set(ka) & set(kb))
    xa = [ka[i].outcome == "correct" for i in common]
    xb = [kb[i].outcome == "correct" for i in common]
    wa = [float(ka[i].outcome == "wrong") for i in common]
    wb = [float(kb[i].outcome == "wrong") for i in common]
    return {"n": len(common), "mcnemar_EX": stats.mcnemar_exact(xa, xb),
            "EX_diff_ci": stats.paired_bootstrap_diff([float(x) for x in xa], [float(x) for x in xb]),
            "mcnemar_wrong": stats.mcnemar_exact([bool(x) for x in wa], [bool(x) for x in wb]),
            "wrong_diff_ci": stats.paired_bootstrap_diff(wa, wb)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="R")
    ap.add_argument("--split", default="val")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-variants", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    out_dir = paths.RUNS / (time.strftime("%Y%m%d-%H%M%S") + (f"-{a.tag}" if a.tag else ""))
    outs = run(a.arm, a.split, a.limit, not a.no_variants, out_dir=out_dir)
    un = run_unanswerable(a.arm)
    s = summarize(outs, un)
    (out_dir / f"{a.arm}_{a.split}_summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    md = markdown(a.arm, a.split, s)
    (out_dir / f"{a.arm}_{a.split}_summary.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\nwritten to {out_dir}")


if __name__ == "__main__":
    main()
