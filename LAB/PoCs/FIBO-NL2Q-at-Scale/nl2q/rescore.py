"""Re-score a finished run offline (no model calls): re-execute every stored query on the
base data and on all variants (V1–V4 perturbed, V5 witness) and report

* strict EX  — rows and columns equal the gold (FIBEN convention);
* relaxed EX — the answer omits some of the gold's context columns (same rows, each answer
  column equals a distinct gold column);
* lenient EX — the answer adds columns to the gold's;
* suite variants of strict and relaxed — equal on the base data and on every variant
  (the witness instance makes empty gold answers discriminative);
* wrong-but-executed under the relaxed criterion.

    python -m nl2q.rescore runs/<run-dir>          # every *.jsonl in it
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from . import compare, gold, paths, stats
from .evaluate import VARIANTS, _execute


class _P:
    def __init__(self, q: str | None):
        if q and q.lstrip().upper().startswith(("PREFIX", "SELECT")) and "fiben:" in q:
            self.sparql, self.sql = q, None
        else:
            self.sparql, self.sql = None, q


def rescore_file(path: Path) -> dict:
    golds = gold.load_results()
    gv = gold.load_variants()
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        r.update(strict=False, relaxed=False, lenient2=False, suite_strict=False, suite_relaxed=False)
        if r["outcome"] in ("refused",) or not r.get("query"):
            continue
        p = _P(r["query"])
        ok, res, n, stage, err, _ = _execute(p)
        if not ok:
            r["outcome"] = "failed"
            continue
        g = golds[r["sql_id"]].sig
        m = compare.compare_all(g, res, n)
        r.update(strict=m.strict, relaxed=m.relaxed, lenient2=m.lenient)
        if not (m.strict or m.relaxed):
            continue
        s_ok, r_ok = m.strict, m.relaxed
        for v in VARIANTS:
            sig = gv.get(v, {}).get(r["sql_id"])
            if sig is None:
                continue
            okv, rv, nv, _, _, _ = _execute(p, v)
            if not okv:
                s_ok = r_ok = False
                break
            mv = compare.compare_all(sig, rv, nv)
            s_ok, r_ok = s_ok and mv.strict, r_ok and mv.relaxed
            if not (s_ok or r_ok):
                break
        r.update(suite_strict=s_ok, suite_relaxed=r_ok)
    path.with_suffix(".rescored.jsonl").write_text("\n".join(json.dumps(r, default=str) for r in rows),
                                                   encoding="utf-8")
    n = len(rows)
    executed = [r for r in rows if r["outcome"] in ("correct", "wrong")]
    ne = [r for r in rows if not r["gold_empty"]]

    def rate(key, xs=rows):
        return round(sum(bool(r[key]) for r in xs) / len(xs), 4) if xs else None
    out = {
        "file": path.name, "n": n,
        "EX_strict": rate("strict"), "EX_strict_ci": stats.bootstrap_ci([float(r["strict"]) for r in rows])[1:],
        "EX_relaxed": rate("relaxed"), "EX_relaxed_ci": stats.bootstrap_ci([float(r["relaxed"]) for r in rows])[1:],
        "EX_lenient": rate("lenient2"),
        "suite_strict": rate("suite_strict"), "suite_relaxed": rate("suite_relaxed"),
        "suite_relaxed_nonempty_gold": rate("suite_relaxed", ne),
        "wrong_but_executed_relaxed": round(sum(1 for r in executed if not r["relaxed"]) / n, 4),
        "wrong_but_executed_suite": round(sum(1 for r in executed if not r["suite_relaxed"]) / n, 4),
        "refused": round(sum(r["outcome"] == "refused" for r in rows) / n, 4),
        "failed": round(sum(r["outcome"] == "failed" for r in rows) / n, 4),
        "cost_usd_per_q": round(sum(r.get("cost_usd", 0) for r in rows) / n, 5),
        "by_type_suite_relaxed": {t: round(sum(r["suite_relaxed"] for r in rows if r["query_type"] == t) /
                                           max(1, sum(r["query_type"] == t for r in rows)), 3)
                                  for t in sorted({r["query_type"] for r in rows})},
    }
    path.with_suffix(".rescored.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def paired(a_file: Path, b_file: Path, key: str = "suite_relaxed") -> dict:
    a = {r["qid"]: r for r in map(json.loads, a_file.read_text(encoding="utf-8").splitlines())}
    b = {r["qid"]: r for r in map(json.loads, b_file.read_text(encoding="utf-8").splitlines())}
    common = sorted(set(a) & set(b))
    xa = [bool(a[i][key]) for i in common]
    xb = [bool(b[i][key]) for i in common]
    return {"n": len(common), "mcnemar": stats.mcnemar_exact(xa, xb),
            "diff_ci": stats.paired_bootstrap_diff([float(x) for x in xa], [float(x) for x in xb])}


if __name__ == "__main__":
    for d in sys.argv[1:]:
        for f in sorted(Path(d).glob("*.jsonl")):
            if ".rescored" in f.name:
                continue
            print(json.dumps(rescore_file(f), indent=1, default=str))
