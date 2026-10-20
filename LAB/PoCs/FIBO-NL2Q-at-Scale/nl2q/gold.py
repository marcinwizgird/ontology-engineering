"""FIBEN questions and their gold answers.

``FIBEN_Queries.json`` holds 300 questions over 237 distinct gold SQL queries (written for
Db2). Each gold query is transpiled to DuckDB with sqlglot plus a few Db2-specific
rewrites, executed on the loaded data, and its rows are stored as the **gold rows**. A
query that does not run is kept with its error: the ceiling is reported, not hidden.

    python -m nl2q.gold          # writes artifacts/gold/gold_sql.json
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field

import sqlglot

from . import paths
from .compare import Signature, signature
from .load_fiben import connect

ROW_CAP = 5000                     # gold rows kept per query (counts are always exact)


@dataclass
class Question:
    qid: int                       # position in FIBEN_Queries.json
    sql_id: int                    # uniqueQueryID: paraphrases share it
    question: str
    sql: str
    query_type: str                # non-nested | type-n | type-a | type-j | type-ja
    paraphrased: bool


def questions() -> list[Question]:
    raw = json.loads(paths.FIBEN_QUERIES.read_text(encoding="utf-8"))
    return [Question(i, int(q["uniqueQueryID"]), q["question"].strip(), q["SQL"].strip(),
                     q["queryType"].strip().lower(), bool(q["isParaphrased"]))
            for i, q in enumerate(raw)]


_DB2_FIXES = [
    (re.compile(r"\bCURRENT\s+DATE\b", re.I), "CURRENT_DATE"),
    (re.compile(r"\bCURRENT\s+TIMESTAMP\b", re.I), "CURRENT_TIMESTAMP"),
    (re.compile(r"\bFETCH\s+FIRST\s+(\d+)\s+ROWS?\s+ONLY\b", re.I), r"LIMIT \1"),
    (re.compile(r"\bWITH\s+UR\b", re.I), ""),
]

#: FIBEN's data ends in 2017-2018; "last N years" questions were written against the
#: benchmark's reference date. A fixed reference keeps gold answers reproducible.
REFERENCE_DATE = "2018-01-01"


# only a *trailing, top-level* cap: inside a scalar subquery FETCH FIRST 1 is semantic
_FETCH = re.compile(r"\s*\bFETCH\s+FIRST\s+\d+\s+ROWS?\s+ONLY\s*$", re.I)


def strip_display_cap(sql: str) -> str:
    """FIBEN appends ``FETCH FIRST 1000 ROWS ONLY`` to many queries as a page size. Without
    ORDER BY it selects an arbitrary subset, so the cap is removed for gold answers."""
    if re.search(r"\bORDER\s+BY\b", sql, re.I):
        return sql
    return _FETCH.sub("", sql)


def to_duckdb(sql: str) -> str:
    s = strip_display_cap(sql)
    # FIBEN gold defects, repaired minimally and listed in artifacts/gold/README.md:
    if s.count("'") % 2:                       # sql_id 172: truncated mid-literal
        s += "'"
    if s.count("(") > s.count(")"):            # sql_id 136: unclosed IN (subquery)
        s += ")" * (s.count("(") - s.count(")"))
    s = re.sub(r"(?<![\w.])(\d+\.\d+)E(\d+)\b", lambda m: repr(float(m.group(0))), s)
    for pat, rep in _DB2_FIXES:
        s = pat.sub(rep, s)
    s = re.sub(r"\bCURRENT_DATE\b", f"DATE '{REFERENCE_DATE}'", s)
    s = re.sub(r"\bCURRENT_TIMESTAMP\b", f"TIMESTAMP '{REFERENCE_DATE} 00:00:00'", s)
    try:
        return sqlglot.transpile(s, read="postgres", write="duckdb")[0]
    except sqlglot.errors.ParseError:
        return sqlglot.transpile(s, read="db2" if "db2" in sqlglot.dialects.DIALECTS else "postgres",
                                 write="duckdb")[0]


@dataclass
class GoldResult:
    sql_id: int
    query_type: str
    duck_sql: str
    ok: bool
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    signature: dict = field(default_factory=dict)
    error: str | None = None
    ms: float = 0.0

    @property
    def sig(self) -> Signature:
        return Signature.from_json(self.signature)


def _jsonable(v):
    if v is None or isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    return str(v)


def run_gold(con=None) -> dict[int, GoldResult]:
    con = con or connect()
    con.execute(f"SET search_path = '{paths.SCHEMA}'")   # a few gold queries omit the schema
    out: dict[int, GoldResult] = {}
    for q in questions():
        if q.sql_id in out:
            continue
        try:
            duck = to_duckdb(q.sql)
        except Exception as exc:  # noqa: BLE001
            out[q.sql_id] = GoldResult(q.sql_id, q.query_type, "", False, error=f"transpile: {exc}")
            continue
        t0 = time.perf_counter()
        try:
            cur = con.execute(duck)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out[q.sql_id] = GoldResult(q.sql_id, q.query_type, duck, True, cols, len(rows),
                                       signature(rows, len(cols)).to_json(),
                                       ms=round((time.perf_counter() - t0) * 1e3, 1))
        except Exception as exc:  # noqa: BLE001
            out[q.sql_id] = GoldResult(q.sql_id, q.query_type, duck, False,
                                       error=f"{type(exc).__name__}: {str(exc)[:300]}")
    return out


def run_gold_variants(variants=("V1", "V2", "V3", "V4"), con=None) -> dict[str, dict[int, dict]]:
    """Gold signatures on each perturbed instance (``nl2q.perturb``): the gold SQL re-targeted
    to schema ``FIBEN_Vk``."""
    from .vkg import retarget
    con = con or connect()
    base = load_results()
    out: dict[str, dict[int, dict]] = {}
    for v in variants:
        schema_name = f"{paths.SCHEMA}_{v}"
        con.execute(f"SET search_path = '{schema_name}'")
        res = {}
        for sid, g in base.items():
            if not g.ok:
                continue
            try:
                cur = con.execute(retarget(g.duck_sql, schema_name))
                rows = cur.fetchall()
                res[sid] = signature(rows, len(cur.description)).to_json()
            except Exception as exc:  # noqa: BLE001
                res[sid] = {"error": str(exc)[:200]}
        out[v] = res
    con.execute(f"SET search_path = '{paths.SCHEMA}'")
    (paths.GOLD_DIR / "gold_variants.json").write_text(json.dumps(out), encoding="utf-8")
    return out


def load_variants() -> dict[str, dict[int, Signature]]:
    raw = json.loads((paths.GOLD_DIR / "gold_variants.json").read_text(encoding="utf-8"))
    return {v: {int(k): Signature.from_json(s) for k, s in d.items() if "error" not in s}
            for v, d in raw.items()}


def save(results: dict[int, GoldResult]) -> None:
    paths.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (paths.GOLD_DIR / "gold_sql.json").write_text(
        json.dumps([asdict(r) for r in results.values()], indent=1), encoding="utf-8")


def load_results() -> dict[int, GoldResult]:
    data = json.loads((paths.GOLD_DIR / "gold_sql.json").read_text(encoding="utf-8"))
    return {d["sql_id"]: GoldResult(**d) for d in data}


def report(results: dict[int, GoldResult]) -> str:
    by = Counter((r.query_type, r.ok) for r in results.values())
    types = sorted({r.query_type for r in results.values()})
    lines = ["| query type | executed | failed | empty result |", "|---|---|---|---|"]
    for t in types:
        empty = sum(1 for r in results.values() if r.query_type == t and r.ok and r.row_count == 0)
        lines.append(f"| {t} | {by[(t, True)]} | {by[(t, False)]} | {empty} |")
    ok = sum(r.ok for r in results.values())
    lines.append(f"| **all** | **{ok}/{len(results)}** | {len(results) - ok} | "
                 f"{sum(1 for r in results.values() if r.ok and r.row_count == 0)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    res = run_gold()
    save(res)
    print(report(res))
    for r in res.values():
        if not r.ok:
            print(r.sql_id, r.error[:160])
