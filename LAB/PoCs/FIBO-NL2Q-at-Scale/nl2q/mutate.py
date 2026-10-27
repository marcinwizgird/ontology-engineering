"""Mutation testing of the metric: does test-suite accuracy catch known-wrong queries?

Each accepted gold SPARQL is mutated with edits that change its meaning:

* ``drop_filter``   remove one FILTER;
* ``flip_cmp``      > <-> < , >= <-> <= in one FILTER;
* ``shift_number``  change one numeric literal (x 1.5);
* ``swap_agg``      SUM <-> AVG, MAX <-> MIN, COUNT -> COUNT DISTINCT;
* ``superclass``    replace one class by its parent (a ListedSecurity -> Security, Revenue -> ElementOfFinancialStatement);
* ``drop_distinct`` remove DISTINCT;
* ``drop_negation`` remove one NOT EXISTS block;
* ``drop_limit``    remove LIMIT.

A mutant is *detected* when it fails to compile/execute or its rows differ from the gold
rows on the base database or on any perturbed instance. Mutants identical in meaning
(e.g. SUM->AVG over single rows) exist, so detection < 100% is expected; the target is
>= 95% on mutants that execute.

A superclass mutant that the declared foreign keys make equivalent (the variable is
reached through a key that targets the subclass, so every valid instance agrees) is
counted as ``equivalent_under_constraints``, not as a detection failure
(``nl2q.evalkit.v6.equivalent_under_constraints``).

    python -m nl2q.mutate                        # Base + V1-V5 (v1 protocol)
    python -m nl2q.mutate --variants V1,V2,V3,V4,V5,V6
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter

from . import compare, gold, knowledge, paths, vkg

VARIANTS = ("V1", "V2", "V3", "V4", "V5")


def _filters(q: str) -> list[re.Match]:
    return list(re.finditer(r"FILTER\((?:[^()]|\([^()]*\))*\)", q))


def mutants(q: str, rng: random.Random) -> list[tuple[str, str]]:
    out = []
    fs = [m for m in _filters(q) if "EXISTS" not in m.group(0)]
    if fs:
        m = rng.choice(fs)
        out.append(("drop_filter", q[:m.start()] + q[m.end():]))
        cmp_ = [m for m in fs if re.search(r"[<>]=?", m.group(0))]
        if cmp_:
            m = rng.choice(cmp_)
            flipped = re.sub(r"(<=|>=|<|>)", lambda x: {"<": ">", ">": "<", "<=": ">=", ">=": "<="}[x.group(1)],
                             m.group(0), count=1)
            out.append(("flip_cmp", q[:m.start()] + flipped + q[m.end():]))
    nums = list(re.finditer(r"(?<![\w\"?.])(\d+\.\d+|\d{2,})(?![\w\"-])", q.split("WHERE", 1)[-1]))
    if nums:
        m = rng.choice(nums)
        off = len(q.split("WHERE", 1)[0]) + len("WHERE")
        v = float(m.group(1)) * 1.5
        new = str(int(v)) if "." not in m.group(1) else repr(v)
        out.append(("shift_number", q[:off + m.start()] + new + q[off + m.end():]))
    for a, b in (("SUM(", "AVG("), ("AVG(", "SUM("), ("MAX(", "MIN("), ("MIN(", "MAX("),
                 ("COUNT(?", "COUNT(DISTINCT ?")):
        if a in q:
            out.append(("swap_agg", q.replace(a, b, 1)))
            break
    sub = knowledge.load().subclass
    classes = [c for c in re.findall(r"a fiben:(\w+)", q) if c in sub]
    if classes:
        c = rng.choice(classes)
        out.append(("superclass", q.replace(f"a fiben:{c} ", f"a fiben:{sub[c]} ", 1)))
    if "SELECT DISTINCT" in q:
        out.append(("drop_distinct", q.replace("SELECT DISTINCT", "SELECT", 1)))
    neg = [m for m in _filters(q) if "NOT EXISTS" in m.group(0)]
    if neg:
        # NOT EXISTS blocks nest braces; remove the first FILTER(NOT EXISTS {...}) by brace matching
        i = q.find("FILTER(NOT EXISTS")
        if i >= 0:
            depth, j = 0, q.index("{", i)
            for k in range(j, len(q)):
                depth += {"{": 1, "}": -1}.get(q[k], 0)
                if depth == 0:
                    end = q.index(")", k) + 1
                    out.append(("drop_negation", q[:i] + q[end:]))
                    break
    if re.search(r"LIMIT \d+", q):
        out.append(("drop_limit", re.sub(r"\s*LIMIT \d+", "", q)))
    return [(k, m) for k, m in out if m != q]


def detected(m: str, sid: int, base: compare.Signature, gv, variants=VARIANTS) -> tuple[bool, str]:
    ex = vkg.run_guarded(m, row_cap=5_000_000, timeout_s=30)
    if not ex.ok:
        return True, "does not execute"
    if not compare.compare(base, ex.rows, len(ex.columns)).strict:
        return True, "base"
    for v in variants:
        sig = gv.get(v, {}).get(sid)
        if sig is None:
            continue
        e2 = vkg.run_guarded(m, row_cap=5_000_000, schema=f"{paths.SCHEMA}_{v}", timeout_s=30)
        if not e2.ok or not compare.compare(sig, e2.rows, len(e2.columns)).strict:
            return True, v
    return False, "undetected"


def _rate(xs: list[dict], base_only: bool = False) -> float | None:
    if not xs:
        return None
    hit = sum(x["where"] == "base" if base_only else x["detected"] for x in xs)
    return round(hit / len(xs), 4)


def _swapped_class(q: str, m: str) -> str | None:
    """The class a superclass mutant replaced."""
    before = re.findall(r"a fiben:(\w+) ", q)
    after = re.findall(r"a fiben:(\w+) ", m)
    return next((b for b, a in zip(before, after) if a != b), None)


def main(limit: int | None = None, variants=VARIANTS, out_name: str = "mutation.json") -> dict:
    from .evalkit import v6
    hier = v6.Hierarchy(v6.schema.load())
    rng = random.Random(42)
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    base = gold.load_results()
    gv = gold.load_variants()
    stats = Counter()
    by_op: dict[str, Counter] = {}
    undetected = []
    records = []
    acc = [r for r in rows if r["strict"]][:limit]
    for r in acc:
        sid = r["sql_id"]
        for op, m in mutants(r["sparql"], rng):
            d, where = detected(m, sid, base[sid].sig, gv, variants)
            equiv = False
            if op == "superclass" and not d:
                c = _swapped_class(r["sparql"], m)
                equiv = bool(c) and v6.equivalent_under_constraints(r["sparql"], c, hier)
            records.append({"sql_id": sid, "op": op, "detected": d, "where": where,
                            "empty_gold": base[sid].row_count == 0, "equivalent_under_constraints": equiv})
            c = by_op.setdefault(op, Counter())
            c["n"] += 1
            c["detected"] += d
            c["by_base"] += where == "base"
            c["only_by_variants"] += where in variants
            c["equivalent_under_constraints"] += records[-1]["equivalent_under_constraints"]
            c["not_executable"] += where == "does not execute"
            if not d:
                undetected.append({"sql_id": sid, "op": op, "empty_gold": base[sid].row_count == 0})
    total = Counter()
    for c in by_op.values():
        total.update(c)
    exe = total["n"] - total["not_executable"]
    res = {"mutants": total["n"], "detected": total["detected"],
           "detection_rate": round(total["detected"] / total["n"], 4) if total["n"] else None,
           "executable_mutants": exe,
           "detection_rate_executable": round((total["detected"] - total["not_executable"]) / exe, 4) if exe else None,
           "caught_only_by_variants": total["only_by_variants"],
           "base_only_detection_rate_executable": round(total["by_base"] / exe, 4) if exe else None,
           "undetected_on_empty_gold": sum(u["empty_gold"] for u in undetected),
           "detection_rate_executable_nonempty_gold": _rate([x for x in records if not x["empty_gold"]
                                                            and x["where"] != "does not execute"]),
           "detection_rate_executable_nonempty_excl_superclass": _rate(
               [x for x in records if not x["empty_gold"] and x["where"] != "does not execute"
                and x["op"] != "superclass"]),
           "base_only_rate_executable_nonempty_gold": _rate(
               [x for x in records if not x["empty_gold"] and x["where"] != "does not execute"], base_only=True),
           "superclass_detection_rate_executable_nonempty_excl_equivalent": _rate(
               [x for x in records if not x["empty_gold"] and x["where"] != "does not execute"
                and x["op"] == "superclass" and not x["equivalent_under_constraints"]]),
           "superclass_equivalent_under_constraints": sum(x["equivalent_under_constraints"] for x in records),
           "variants": list(variants),
           "by_op": {k: dict(v) for k, v in by_op.items()}}
    (paths.GOLD_DIR / out_name).write_text(json.dumps({**res, "undetected": undetected}, indent=1),
                                                  encoding="utf-8")
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--out", default="mutation.json")
    a = ap.parse_args()
    print(json.dumps(main(variants=tuple(a.variants.split(",")), out_name=a.out), indent=1))
