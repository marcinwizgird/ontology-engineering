"""SPARQL -> SQL -> rows over the FIBEN virtual knowledge graph.

Compilation reuses the verified compiler of ``LAB/PoCs/SPARQL-2-SQL`` (validate with
rdflib, reformulate with the offline Ontop sidecar, finish the SELECT list, transpile with
sqlglot), pointed at the FIBEN sidecar (``NL2Q_SIDECAR_URL``, default :18081).
Execution runs the DuckDB SQL read-only on ``data/fiben_vkg.duckdb``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache

from . import paths
from .load_fiben import connect

PREFIXES = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX fiben: <https://example.org/fiben/voc#>
"""


@lru_cache(maxsize=1)
def _compiler():
    os.environ["ONTOP_SIDECAR_URL"] = paths.SIDECAR_URL
    spec = importlib.util.spec_from_file_location(
        "nl2q_vkg_compiler", paths.COMPILER_APP / "app" / "compiler.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nl2q_vkg_compiler"] = mod
    spec.loader.exec_module(mod)
    mod.SIDECAR_URL = paths.SIDECAR_URL
    return mod


@dataclass
class Execution:
    ok: bool
    stage: str = ""                 # validate | reformulate | finish | execute | "" when ok
    error: str = ""
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    ms: dict = field(default_factory=dict)


def compile_sparql(sparql: str, dialect: str = "duckdb"):
    """Returns the compiler's ``Compiled`` or raises its ``CompileError``."""
    return _compiler().compile_sparql(sparql, dialect)


def compile_error_type():
    return _compiler().CompileError


_CON = None


def _con():
    global _CON
    if _CON is None:
        _CON = connect()
    return _CON


def run(sparql: str, *, row_cap: int = 100_000, schema: str | None = None,
        timeout_s: float = 30.0) -> Execution:
    """Compile and execute. ``schema`` re-targets the SQL to a perturbed copy of the
    database (see ``nl2q.perturb``)."""
    CE = compile_error_type()
    t0 = time.perf_counter()
    try:
        c = compile_sparql(sparql)
    except CE as exc:
        return Execution(False, exc.stage, str(exc)[:500])
    sql = fix_temporal_projection(c.sql)
    if schema is not None:
        sql = retarget(sql, schema)
    t1 = time.perf_counter()
    con = _con()
    timer = threading.Timer(timeout_s, con.interrupt)   # a runaway join must not stall a run
    timer.start()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(row_cap)
        n = len(rows)
    except Exception as exc:  # noqa: BLE001
        msg = "timeout" if time.perf_counter() - t1 >= timeout_s - 0.05 else f"{type(exc).__name__}: {str(exc)[:400]}"
        return Execution(False, "execute", msg, sql)
    finally:
        timer.cancel()
    return Execution(True, "", "", sql, cols, rows, n,
                     {"compile": round((t1 - t0) * 1e3, 1),
                      "execute": round((time.perf_counter() - t1) * 1e3, 1)})


def run_guarded(sparql: str, *, schema: str | None = None, timeout_s: float = 30.0,
                row_cap: int = 5_000_000) -> Execution:
    """Like :func:`run`, but proof against queries DuckDB does not interrupt promptly: the
    query runs in a worker thread on its *own* connection; if it outlives the timeout it is
    interrupted and abandoned (the thread is a daemon) and a timeout is reported."""
    CE = compile_error_type()
    try:
        c = compile_sparql(sparql)
    except CE as exc:
        return Execution(False, exc.stage, str(exc)[:500])
    sql = fix_temporal_projection(c.sql)
    if schema is not None:
        sql = retarget(sql, schema)
    result: dict = {}
    con = connect()

    def work():
        try:
            cur = con.execute(sql)
            result["cols"] = [d[0] for d in cur.description]
            result["rows"] = cur.fetchmany(row_cap)
        except Exception as exc:  # noqa: BLE001
            result["err"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        try:
            con.interrupt()
        except Exception:  # noqa: BLE001
            pass
        th.join(5)
        return Execution(False, "execute", "timeout", sql)
    try:
        con.close()
    except Exception:  # noqa: BLE001
        pass
    if "err" in result:
        return Execution(False, "execute", result["err"], sql)
    return Execution(True, "", "", sql, result["cols"], result["rows"], len(result["rows"]))


def fix_temporal_projection(sql: str) -> str:
    """Ontop renders a projected timestamp as PostgreSQL ``TO_JSON(x)#>>'{}'`` (the ISO
    lexical form); sqlglot transpiles that to ``JSONB_EXTRACT_SCALAR``, which DuckDB lacks.
    The plain column carries the same value. (A finishing gap of the SPARQL-2-SQL PoC's
    compiler, found here; it only affects projected timestamps.)"""
    if "JSONB_EXTRACT_SCALAR" not in sql.upper():
        return sql
    import sqlglot
    from sqlglot import exp
    tree = sqlglot.parse_one(sql, read="duckdb")
    for node in list(tree.find_all(exp.JSONBExtractScalar, exp.JSONExtractScalar)):
        inner = node.this
        if isinstance(inner, (exp.Anonymous, exp.Func)) and inner.args.get("this") is not None \
                and "JSON" in inner.sql().upper():
            inner = inner.this if not isinstance(inner, exp.Anonymous) else inner.expressions[0]
        node.replace(inner.copy())
    return tree.sql(dialect="duckdb")


def retarget(sql: str, schema: str) -> str:
    import sqlglot
    from sqlglot import exp
    tree = sqlglot.parse_one(sql, read="duckdb")
    for t in tree.find_all(exp.Table):
        if t.args.get("db") is not None and t.db.upper() == paths.SCHEMA:
            t.set("db", exp.to_identifier(schema, quoted=True))
    return tree.sql(dialect="duckdb")


def sidecar_ok() -> bool:
    return _compiler().sidecar_healthy()
