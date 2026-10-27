"""Gate 4 scoring (specification §5, Gate 4 and §5.5) over finished, re-scored runs.

Input per arm: one or more runs, each a list of per-question records as written by
``nl2q.rescore`` (``*.rescored.jsonl``), and optionally the unanswerable results.

Outcome states per question and run (mutually exclusive):
``correct`` (suite relaxed), ``wrong`` (executed, not suite-correct), ``refused``, ``failed``.

Every interval is a gold-query cluster bootstrap with runs nested in questions
(``evalkit.statistics``).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import paths
from . import slices, statistics as st

UTILITY_C = (1.0, 2.0, 5.0)
REFUSAL_REWARD = 0.3          # PLAN.md §4.3: +0.3 correct refusal, -0.3 unnecessary refusal
PREVALENCE = 0.2              # refusal precision is also reported at this unanswerable share


@dataclass
class Unanswerable:
    """Results on the unanswerable suite of one run: refused or answered, per stratum."""
    refused: dict[str, int]                    # stratum -> correctly refused
    total: dict[str, int]                      # stratum -> questions
    source: str = "records"                    # records | summary (reconstructed from a rate)


@dataclass
class Arm:
    id: str
    label: str
    ladder: str = ""
    factors: str = ""
    runs: list[list[dict]] = field(default_factory=list)
    unanswerable: list[Unanswerable | None] = field(default_factory=list)
    note: str = ""


def state(r: dict) -> str:
    if r.get("outcome") == "refused":
        return "refused"
    if r.get("outcome") == "failed" or not r.get("query"):
        return "failed"
    return "correct" if r.get("suite_relaxed") else "wrong"


@lru_cache(maxsize=1)
def ceiling_ids() -> frozenset[int]:
    """Gold queries inside the compiler ceiling (gold SPARQL accepted on Base + variants)."""
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    return frozenset(r["sql_id"] for r in rows if r.get("strict"))


def _norm_query(q: str | None) -> str:
    return re.sub(r"\s+", " ", q or "").strip()


def _by_question(arm: Arm) -> tuple[list[int], dict[int, list[dict]]]:
    """Questions answered in every run (budget-capped runs cover fewer), with their records."""
    per: dict[int, list[dict]] = defaultdict(list)
    for run in arm.runs:
        for r in run:
            per[r["qid"]].append(r)
    qids = sorted(q for q, rs in per.items() if len(rs) == len(arm.runs))
    return qids, per


def _ci(values: list[list[float]], clusters: list[int]) -> dict:
    if not values:
        return {"mean": None, "ci": None, "n": 0}
    m, lo, hi = st.cluster_bootstrap_ci(values, clusters)
    return {"mean": round(m, 4), "ci": [round(lo, 4), round(hi, 4)], "n": len(values)}


def score(arm: Arm) -> dict:
    qids, per = _by_question(arm)
    clusters = [per[q][0]["sql_id"] for q in qids]
    states = {q: [state(r) for r in per[q]] for q in qids}

    def series(pred, subset=None) -> tuple[list[list[float]], list[int]]:
        keep = [i for i, q in enumerate(qids) if subset is None or subset(per[q][0])]
        return [[float(pred(s)) for s in states[qids[i]]] for i in keep], [clusters[i] for i in keep]

    out: dict = {"arm": arm.id, "label": arm.label, "ladder": arm.ladder, "factors": arm.factors,
                 "runs": len(arm.runs), "n": len(qids), "note": arm.note}
    out["suite_ex"] = _ci(*series(lambda s: s == "correct"))
    out["wrong_but_executed"] = _ci(*series(lambda s: s == "wrong"))
    out["refused"] = _ci(*series(lambda s: s == "refused"))
    out["failed"] = round(np.mean([[s == "failed" for s in v] for v in states.values()]), 4) if qids else None
    ceil = ceiling_ids()
    out["suite_ex_in_ceiling"] = _ci(*series(lambda s: s == "correct", lambda r: r["sql_id"] in ceil))

    tags = slices.by_sql_id()
    out["slices"] = {}
    for dim in slices.DIMENSIONS:
        vals = sorted({tags.get(per[q][0]["sql_id"], {}).get(dim, "unknown") for q in qids})
        out["slices"][dim] = {
            v: _ci(*series(lambda s: s == "correct",
                           lambda r, v=v, dim=dim: tags.get(r["sql_id"], {}).get(dim, "unknown") == v))
            for v in vals}

    out["refusal"] = refusal(arm, states)
    out["utility"] = utility(arm, states)
    out["stability"] = stability(arm, qids, per)
    out["economics"] = economics(arm, qids, per, states)
    return out


def refusal(arm: Arm, states: dict[int, list[str]]) -> dict:
    """Recall per stratum, false-refusal rate on answerable questions, and precision at
    the observed mix and at a fixed prevalence (it depends on the share of unanswerables)."""
    a = sum(len(v) for v in states.values())
    false_ref = sum(s == "refused" for v in states.values() for s in v)
    fr_rate = false_ref / a if a else None
    unans = [u for u in arm.unanswerable if u is not None]
    if not unans:
        return {"false_refusal_rate": _r(fr_rate), "recall": None, "note": "unanswerable suite not run"}
    strata = sorted({k for u in unans for k in u.total})
    recall = {k: _r(sum(u.refused.get(k, 0) for u in unans) / sum(u.total.get(k, 0) for u in unans))
              for k in strata}
    tp = sum(sum(u.refused.values()) for u in unans)
    n_u = sum(sum(u.total.values()) for u in unans)
    tpr = tp / n_u
    precision_obs = tp / (tp + false_ref) if tp + false_ref else None
    num, den = tpr * PREVALENCE, tpr * PREVALENCE + (fr_rate or 0) * (1 - PREVALENCE)
    return {"recall": recall, "recall_all": _r(tpr), "false_refusal_rate": _r(fr_rate),
            "precision_observed": _r(precision_obs), f"precision_at_{int(PREVALENCE * 100)}pct": _r(num / den if den else None),
            "source": sorted({u.source for u in unans})}


def utility(arm: Arm, states: dict[int, list[str]]) -> dict:
    """Utility(c) per spec, averaged over runs, with its four components and the
    abstain-on-everything floor. Without an unanswerable suite only the answerable
    terms are scored (and the floor is the answerable-only floor, -0.3)."""
    per_run = []
    for i in range(len(arm.runs)):
        st_run = [v[i] for v in states.values()]
        a = len(st_run)
        u = arm.unanswerable[i] if i < len(arm.unanswerable) else None
        n_u = sum(u.total.values()) if u else 0
        tr = sum(u.refused.values()) if u else 0
        comp = {"correct": sum(s == "correct" for s in st_run),
                "wrong": sum(s == "wrong" for s in st_run) + (n_u - tr),   # an answered unanswerable is wrong
                "correct_refusal": tr,
                "false_refusal": sum(s == "refused" for s in st_run)}
        per_run.append((comp, a + n_u, a, n_u))
    if not per_run:
        return {}
    out: dict = {}
    for c in UTILITY_C:
        vals = [(k["correct"] - c * k["wrong"] + REFUSAL_REWARD * (k["correct_refusal"] - k["false_refusal"])) / n
                for k, n, _, _ in per_run]
        out[f"c={c:g}"] = round(float(np.mean(vals)), 4)
    comp, n, a, n_u = per_run[0]
    out["components_per_q"] = {k: round(np.mean([p[0][k] / p[1] for p in per_run]), 4) for k in comp}
    out["floor"] = round(REFUSAL_REWARD * (n_u - a) / n, 4)
    out["includes_unanswerable"] = n_u > 0
    return out


def stability(arm: Arm, qids: list[int], per: dict[int, list[dict]]) -> float | None:
    """Share of questions with the same outcome state and the same query text in every run."""
    if len(arm.runs) < 2:
        return None
    same = sum(len({(state(r), _norm_query(r.get("query"))) for r in per[q]}) == 1 for q in qids)
    return round(same / len(qids), 4) if qids else None


def economics(arm: Arm, qids: list[int], per: dict[int, list[dict]], states: dict[int, list[str]]) -> dict:
    recs = [r for q in qids for r in per[q]]
    cost = sum(r.get("cost_usd") or 0 for r in recs)
    correct = sum(s == "correct" for v in states.values() for s in v)
    lat = [(r.get("ms_system") or 0) + (r.get("ms_exec") or 0) for r in recs]
    return {"usd_per_q": round(cost / len(recs), 5) if recs else None,
            "usd_per_correct": round(cost / correct, 4) if correct else None,
            "latency_p50_s": round(float(np.percentile(lat, 50)) / 1000, 2) if lat else None,
            "latency_p95_s": round(float(np.percentile(lat, 95)) / 1000, 2) if lat else None,
            "tokens_per_q": None}   # not recorded by v1 runs; ports record it from S5 on


def compare(a: Arm, b: Arm, metric: str = "correct") -> dict:
    """Paired comparison a vs b on the questions both answered in every run:
    cluster-bootstrap CI of the difference, McNemar on majority outcomes, and the MDE."""
    qa, pa = _by_question(a)
    qb, pb = _by_question(b)
    common = sorted(set(qa) & set(qb))
    if not common:
        return {"n": 0}
    xa = [[float(state(r) == metric) for r in pa[q]] for q in common]
    xb = [[float(state(r) == metric) for r in pb[q]] for q in common]
    clusters = [pa[q][0]["sql_id"] for q in common]
    d, lo, hi = st.paired_cluster_bootstrap_diff(xa, xb, clusters)
    ma = [st.majority([v > 0 for v in x]) for x in xa]
    mb = [st.majority([v > 0 for v in x]) for x in xb]
    mc = st.mcnemar_majority([[v > 0 for v in x] for x in xa], [[v > 0 for v in x] for x in xb])
    disc = sum(x != y for x, y in zip(ma, mb)) / len(common)
    return {"n": len(common), "gold_queries": len(set(clusters)), "metric": metric,
            "diff": round(d, 4), "ci": [round(lo, 4), round(hi, 4)], "p": round(mc["p"], 4),
            "discordant": round(disc, 4), "mde": _r(st.mde_paired(len(common), disc))}


def _r(x, k: int = 4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(x, k)


# ----------------------------------------------------------------------------- loading
def load_run(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def unanswerable_from_summary(path: Path, n: int, stratum: str = "unstratified") -> Unanswerable | None:
    """v1 runs stored only the refusal recall on the 24 hand-written unanswerables."""
    if not path.exists():
        return None
    rate = json.loads(path.read_text(encoding="utf-8")).get("refusal_recall_unanswerable")
    if rate is None:
        return None
    return Unanswerable({stratum: round(rate * n)}, {stratum: n}, source="summary")
