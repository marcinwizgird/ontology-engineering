"""The per-campaign scorecard (specification §6).

A campaign file (``artifacts/eval/campaigns/*.json``) lists the arms, their ladder rung
and factors, and their run files. The scorecard scores every arm (Gate 4), compares each
arm with the campaign's baseline on the headline accuracy and safety metrics, applies the
Holm correction across those comparisons, and writes ``scorecard.json`` and
``scorecard.md`` next to the campaign file (``<campaign>.scorecard.*``).

    python -m nl2q.evalkit.scorecard artifacts/eval/campaigns/fiben_v1_val.json

Tables A (Gate 1) and B (Gate 3) are filled once those gates are implemented (spec §8);
until then the Markdown says so instead of printing empty rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import paths
from . import scoring, slices, statistics as st


def load_campaign(path: Path) -> tuple[dict, list[scoring.Arm]]:
    c = json.loads(path.read_text(encoding="utf-8"))
    arms = []
    for a in c["arms"]:
        runs = [scoring.load_run(paths.ROOT / r) for r in a["runs"]]
        unans = [scoring.unanswerable_from_summary(paths.ROOT / s, c.get("unanswerable_n", 24))
                 for s in a.get("summaries", [])]
        arms.append(scoring.Arm(a["id"], a["label"], a.get("ladder", ""), a.get("factors", ""),
                                runs, unans + [None] * (len(runs) - len(unans)), a.get("note", "")))
    return c, arms


def build(path: Path) -> dict:
    c, arms = load_campaign(path)
    scores = [scoring.score(a) for a in arms]
    base = next(a for a in arms if a.id == c["baseline"])
    comps, pvals = {}, {}
    for a in arms:
        if a is base:
            continue
        for metric in ("correct", "wrong"):
            r = scoring.compare(a, base, metric)
            comps[f"{a.id}:{metric}"] = r
            if r.get("n"):
                pvals[f"{a.id}:{metric}"] = r["p"]
    for k, p in st.holm(pvals).items():
        comps[k]["p_holm"] = round(p, 4)
    return {"campaign": {k: v for k, v in c.items() if k != "arms"}, "gate1": gate1_status(),
            "arms": scores, "vs_baseline": comps}


# ----------------------------------------------------------------------------- Table A
def _json(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def gate1_status() -> dict:
    """Gate 1 results from the artifacts each step writes, and the must-pass verdict."""
    ev = paths.ARTIFACTS / "eval"
    g1 = _json(ev / "gate1" / "gate1.json") or {}
    sh = _json(ev / "gate1" / "shacl.json") or {}
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    ceiling = sum(bool(r.get("strict")) for r in rows)
    out = {"annotation": g1.get("annotation_coverage"), "cq": g1.get("cq"), "ova": g1.get("ova"),
           "key_integrity": {k: sum(v["dangling"] for v in vs) for k, vs in g1.get("key_integrity", {}).items()},
           "shacl": {k: v["violations"] for k, v in sh.get("instances", {}).items()},
           "shacl_cross_check": sh.get("cross_check"),
           "ceiling": {"accepted": ceiling, "of": len(rows), "recorded_v1": 219},
           "ceiling_v6": _json(ev / "ceiling_v6.json"),
           "mutation_v1_v5": _json(paths.GOLD_DIR / "mutation.json"),
           "mutation_v1_v6": _json(paths.GOLD_DIR / "mutation_v6.json")}
    must = {
        "key integrity (all instances)": bool(out["key_integrity"]) and not any(out["key_integrity"].values()),
        "SHACL (all instances)": bool(out["shacl"]) and not any(out["shacl"].values()),
        "competency questions": bool(out["cq"]) and out["cq"]["passed"] == out["cq"]["total"],
        "compiler ceiling no regression": ceiling >= 219,
    }
    out["must_pass"] = must
    return out


def table_a() -> list[str]:
    st_ = gate1_status()
    if not st_["cq"]:
        return ["Not yet produced: run `python -m nl2q.evalkit.gate1` (spec §8, stage S3)."]
    a, ova = st_["annotation"], st_["ova"]

    def sev(x):
        return f"{x['by_severity']['major']} / {x['by_severity']['minor']}"
    mut = st_["mutation_v1_v6"] or st_["mutation_v1_v5"] or {}
    cv6 = st_["ceiling_v6"]
    lines = ["| Check | Kind | Result |", "|---|---|---|",
             f"| 1.1 Pitfall scan (OVA, OOPS! stand-in; major / minor) | reported | E0 {sev(ova['E0'])} · E1 {sev(ova['E1'])}; "
             f"covers {len(ova['catalogue']['oops_pitfalls_referenced'])} of 41 OOPS! pitfalls |",
             f"| 1.2 Annotation coverage (definitions) | reported | E0 {a['E0']}/{a['terms']} · E1 {a['E1']}/{a['terms']} "
             f"(missing: {', '.join(a['E1_missing'])}) |",
             f"| 1.3 Competency questions (SPARQL ASK) | must-pass | {st_['cq']['passed']}/{st_['cq']['total']} |",
             "| 1.3 Key integrity per instance (dangling keys) | must-pass | "
             + ", ".join(f"{k.replace(paths.SCHEMA, 'Base').replace('Base_', '')} {v}" for k, v in st_["key_integrity"].items()) + " |",
             "| 1.3 SHACL per instance (violations) | must-pass | "
             + (", ".join(f"{k.replace(paths.SCHEMA, 'Base').replace('Base_', '')} {v}" for k, v in st_["shacl"].items())
                or "not run") + (f"; pySHACL cross-check {'agrees' if (st_['shacl_cross_check'] or {}).get('agree') else 'DISAGREES'}"
                                 if st_["shacl_cross_check"] else "") + " |",
             f"| 1.4 Compiler ceiling (Base + V1–V5) | must-pass | {st_['ceiling']['accepted']}/{st_['ceiling']['of']} "
             f"(v1 recorded 219)" + (f"; {cv6['agree_v6']}/{cv6['accepted_v1_v5']} also agree on V6" if cv6 else "") + " |"]
    if mut:
        lines.append(f"| 1.4 Mutant detection (executable; non-empty gold; superclass excl. equivalent) | reported (goal ≥ 90% / ≥ 75%) | "
                     f"{mut.get('detection_rate_executable', 0):.1%}; {mut.get('detection_rate_executable_nonempty_gold', 0):.1%}; "
                     f"{(mut.get('superclass_detection_rate_executable_nonempty_excl_equivalent') or 0):.1%} "
                     f"({mut.get('superclass_equivalent_under_constraints', 0)} superclass swaps equivalent under the declared keys); "
                     f"variants {','.join(mut.get('variants', []))} |")
    verdict = "PASS" if all(st_["must_pass"].values()) else "FAIL: " + ", ".join(k for k, v in st_["must_pass"].items() if not v)
    lines += ["", f"**Gate 1 must-pass: {verdict}**"]
    return lines


# ----------------------------------------------------------------------------- markdown
def _pct(m: dict | None) -> str:
    if not m or m.get("mean") is None:
        return "—"
    lo, hi = m["ci"]
    return f"{m['mean']:.1%} [{lo:.0%}–{hi:.0%}]"


def _p(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def _cmp(c: dict | None) -> str:
    if not c or not c.get("n"):
        return "—"
    return f"{c['diff']:+.1%} [{c['ci'][0]:+.0%}, {c['ci'][1]:+.0%}], p={c['p']:.2f} (Holm {c.get('p_holm', c['p']):.2f}), MDE {c['mde']:.0%}"


def markdown(sc: dict) -> str:
    c = sc["campaign"]
    lines = [f"# Scorecard: {c['name']}", "",
             f"* Dataset / split: {c['dataset']} / {c['split']}; date {c.get('date', '?')}; model {c.get('model', '?')}",
             f"* Baseline for comparisons: arm {c['baseline']}",
             f"* {c.get('note', '')}", "",
             "Intervals: 95% bootstrap resampling gold queries (paraphrases move together), runs nested "
             "in questions; comparisons: exact McNemar on majority outcomes, Holm-corrected across the table; "
             "MDE: smallest difference detectable at power 0.8 (spec §5.5).", "",
             "## Table A: Gate 1 build & ontology health", "",
             *table_a(), "",
             "## Table B: Gate 3 oracle ceilings", "",
             "Not yet produced: the C1–C6 ports and oracle adapters are stage S5 (spec §8).", "",
             "## Table C: Gate 4 comparison", "",
             "| Arm | Rung | E / G | n | Suite EX | Suite EX in ceiling | Hierarchy slice | Nested slice | "
             "Wrong-but-executed ↓ | Refusal recall · false-refusal ↓ | Utility c=2 / c=5 (floor) | "
             f"Δ suite EX vs {c['baseline']} | Δ wrong vs {c['baseline']} | Stability | P95 s | $/q · $/correct |",
             "|" + "---|" * 16]
    for a in sc["arms"]:
        h = a["slices"]["hierarchy"].get("superclass-union")
        nested = {k: v for k, v in a["slices"]["nesting"].items() if k != "non-nested"}
        n_nest = sum(v["n"] for v in nested.values())
        nest = (sum(v["mean"] * v["n"] for v in nested.values() if v["mean"] is not None) / n_nest) if n_nest else None
        ref = a["refusal"]
        rr = "—" if not ref.get("recall") else f"{ref['recall_all']:.0%}"
        u = a["utility"]
        floor = u.get("floor")
        util = f"{u['c=2']:+.2f} / {u['c=5']:+.2f} ({floor:+.2f})" if u else "—"
        e = a["economics"]
        econ = f"{e['usd_per_q']:.3f} · {e['usd_per_correct']:.2f}" if e["usd_per_correct"] else \
            (f"{e['usd_per_q']:.3f} · —" if e["usd_per_q"] is not None else "—")
        comp = sc["vs_baseline"]
        stab = "—" if a["stability"] is None else f"{a['stability']:.0%}"
        lines.append(
            f"| {a['label']} | {a['ladder']} | {a['factors']} | {a['n']} | {_pct(a['suite_ex'])} | "
            f"{_pct(a['suite_ex_in_ceiling'])} | {_pct(h)} | {_p(nest)} (n={n_nest}) | {_pct(a['wrong_but_executed'])} | "
            f"{rr} · {_p(ref.get('false_refusal_rate'))} | {util} | "
            f"{_cmp(comp.get(a['arm'] + ':correct'))} | {_cmp(comp.get(a['arm'] + ':wrong'))} | "
            f"{stab} | "
            f"{e['latency_p95_s'] if e['latency_p95_s'] is not None else '—'} | {econ} |")
    lines += ["", "Notes:"]
    lines += [f"* **{a['arm']}**: {a['note']}" for a in sc["arms"] if a["note"]]
    lines += ["* Utility without an unanswerable suite scores answerable questions only (floor −0.30); "
              "with it, answering an unanswerable question counts as wrong-but-executed.",
              "* Stability needs ≥ 2 runs; tokens per question are recorded from stage S5 on.",
              "", "## Table D: reproducibility & curation", "",
              "v1 runs did not record the pins of spec §5.5.6 (model snapshot, program and pack hashes); "
              "they are reportable only as exploratory evidence. Curation hours were not logged."]
    return "\n".join(lines) + "\n"


def write(path: Path) -> dict:
    sc = build(path)
    stem = path.with_suffix("")
    stem.with_suffix(".scorecard.json").write_text(json.dumps(sc, indent=1, default=str), encoding="utf-8")
    stem.with_suffix(".scorecard.md").write_text(markdown(sc), encoding="utf-8")
    return sc


if __name__ == "__main__":
    for p in sys.argv[1:] or [str(paths.ARTIFACTS / "eval" / "campaigns" / "fiben_v1_val.json")]:
        sc = write(Path(p))
        print(f"{p}: {len(sc['arms'])} arms scored")
