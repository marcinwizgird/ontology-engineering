"""P1: gold SPARQL for every FIBEN query, and the compiler ceiling.

For each unique gold SQL: translate to SPARQL (``sql2sparql``), compile through Ontop,
execute on DuckDB, and compare the rows with the gold signature. A gold SPARQL is
*accepted* only if it reproduces the gold rows (strict). The share accepted per query
type is the **ceiling** of the VKG route on FIBEN.

    python -m nl2q.ceiling        # writes artifacts/gold/gold_sparql.json + ceiling.md
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict

from . import compare, gold, paths, sql2sparql, vkg


def run() -> list[dict]:
    results = gold.load_results()
    qs = {q.sql_id: q for q in gold.questions()}
    out = []
    for sid, g in sorted(results.items()):
        q = qs[sid]
        rec = {"sql_id": sid, "query_type": g.query_type, "gold_rows": g.row_count,
               "sparql": None, "stage": "", "error": "", "strict": False, "lenient": False}
        try:
            rec["sparql"] = sql2sparql.to_sparql(q.sql)
        except Exception as exc:  # noqa: BLE001
            rec.update(stage="translate", error=f"{type(exc).__name__}: {exc}"[:300])
            out.append(rec)
            continue
        t0 = time.perf_counter()
        ex = vkg.run(rec["sparql"], row_cap=10_000_000)
        rec["ms"] = round((time.perf_counter() - t0) * 1e3)
        if not ex.ok:
            rec.update(stage=ex.stage, error=ex.error[:300])
            out.append(rec)
            continue
        m = compare.compare(g.sig, ex.rows, len(ex.columns))
        rec.update(stage="compare", strict=m.strict, lenient=m.lenient, error=m.reason,
                   pred_rows=ex.row_count)
        out.append(rec)
    return out


def report(rows: list[dict]) -> str:
    by = defaultdict(Counter)
    for r in rows:
        t = r["query_type"]
        by[t]["n"] += 1
        by[t]["translated"] += r["sparql"] is not None
        by[t]["compiled+ran"] += r["stage"] == "compare"
        by[t]["strict"] += r["strict"]
        by[t]["strict_nonempty"] += r["strict"] and r["gold_rows"] > 0
        by[t]["nonempty"] += r["gold_rows"] > 0
    lines = ["| query type | n | translated | compiled & ran | **match (ceiling)** | match on non-empty gold |",
             "|---|---|---|---|---|---|"]
    tot = Counter()
    for t in sorted(by):
        c = by[t]
        tot.update(c)
        lines.append(f"| {t} | {c['n']} | {c['translated']} | {c['compiled+ran']} | "
                     f"**{c['strict']}** ({100 * c['strict'] / c['n']:.0f}%) | "
                     f"{c['strict_nonempty']}/{c['nonempty']} |")
    lines.append(f"| **all** | {tot['n']} | {tot['translated']} | {tot['compiled+ran']} | "
                 f"**{tot['strict']}** ({100 * tot['strict'] / tot['n']:.0f}%) | "
                 f"{tot['strict_nonempty']}/{tot['nonempty']} |")
    fails = Counter((r["stage"], r["error"].split(":")[0][:60]) for r in rows if not r["strict"])
    lines += ["", "Failure causes:", ""] + [f"* {n} x {s}: {e}" for (s, e), n in fails.most_common(15)]
    return "\n".join(lines)


def verify_variants(rows: list[dict], variants=("V1", "V2", "V3", "V4", "V5")) -> list[dict]:
    """Acceptance requires agreement on the base data **and** every perturbed / witness
    instance: a translation that coincides with the gold SQL only on the base data is not
    accepted (the witness instance revealed two such cases)."""
    gv = gold.load_variants()
    for r in rows:
        r["strict_base"] = r.get("strict_base", r["strict"])
        if not r["strict_base"]:
            r["strict"] = False
            continue
        bad = []
        for v in variants:
            sig = gv.get(v, {}).get(r["sql_id"])
            if sig is None:
                continue
            ex = vkg.run_guarded(r["sparql"], row_cap=10_000_000, schema=f"{paths.SCHEMA}_{v}", timeout_s=60)
            if not ex.ok or not compare.compare(sig, ex.rows, len(ex.columns)).strict:
                bad.append(v)
        r["variants_disagree"] = bad
        r["strict"] = not bad
        print(f"verified sql_id {r['sql_id']}: {'ok' if not bad else 'disagrees on ' + ','.join(bad)}", flush=True)
    return rows


if __name__ == "__main__":
    import sys
    if "--verify-variants" in sys.argv:
        rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
        rows = verify_variants(rows)
        (paths.GOLD_DIR / "gold_sparql.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        md = report(rows)
        (paths.GOLD_DIR / "ceiling.md").write_text(
            "# Compiler ceiling on FIBEN\n\nAccepted = reproduces the gold rows on the base data and on "
            "all five variants (V1-V4 perturbed, V5 witness).\n\n" + md + "\n", encoding="utf-8")
        print(md)
        raise SystemExit(0)
    rows = run()
    paths.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (paths.GOLD_DIR / "gold_sparql.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    md = report(rows)
    (paths.GOLD_DIR / "ceiling.md").write_text("# Compiler ceiling on FIBEN\n\n" + md + "\n",
                                               encoding="utf-8")
    print(md)
