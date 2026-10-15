"""SPARQL -> SQL compilation: validate, reformulate (Ontop sidecar), finish, transpile.

The compiler holds no database connection and needs none:

1. **validate** the SPARQL 1.1 text with rdflib (SELECT queries only);
2. **reformulate** it with the offline Ontop sidecar, which unfolds the query through the
   OWL 2 QL ontology and the R2RML mappings into PostgreSQL SQL over the FIBEN tables
   (``/ontop/reformulate`` returns the native SQL *and* how each SPARQL variable is built
   from its columns);
3. **finish** the SQL. Ontop's native query returns raw columns and builds IRIs and RDF
   literals in Java; a SQL consumer needs them in SQL. The SELECT list is rewritten so each
   SPARQL variable becomes one SQL expression (an IRI template becomes string
   concatenation, a literal becomes its typed column), aliased with the variable's name.
   ``WHERE``, ``GROUP BY`` and ``ORDER BY`` are left exactly as Ontop wrote them;
4. **transpile** the PostgreSQL AST to the target dialect with sqlglot.
"""

from __future__ import annotations

import functools
import http.client
import json
import os
import re
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

import sqlglot
from rdflib.plugins.sparql import prepareQuery
from sqlglot import exp

DIALECTS = ("postgres", "duckdb", "snowflake", "bigquery")
SIDECAR_URL = os.environ.get("ONTOP_SIDECAR_URL", "http://localhost:18080")


class CompileError(Exception):
    """A query the PoC cannot compile; ``stage`` says where it failed."""

    def __init__(self, stage: str, message: str, status: int = 422):
        super().__init__(message)
        self.stage, self.status = stage, status


@dataclass
class Compiled:
    sql: str
    dialect: str
    projection: list[str]
    native_sql: str
    tables: list[str]
    join_count: int
    timings_ms: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 1. validation
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=4096)
def validate(sparql: str) -> None:
    """rdflib's SPARQL 1.1 parser (~16 ms per query on the PoC machine); memoised, since
    the verdict depends only on the text. A failure raises and is not cached."""
    try:
        q = prepareQuery(sparql)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        raise CompileError("validate", f"invalid SPARQL 1.1: {exc}", 400) from exc
    if q.algebra.name != "SelectQuery":
        raise CompileError("validate", f"only SELECT queries compile to SQL, not {q.algebra.name}", 400)


# --------------------------------------------------------------------------- #
# 2. reformulation (one persistent HTTP connection per thread: latency matters)
# --------------------------------------------------------------------------- #
_local = threading.local()


def _connection() -> http.client.HTTPConnection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        u = urllib.parse.urlsplit(SIDECAR_URL)
        conn = _local.conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=30)
        conn.connect()
        # headers and body go out in separate writes; without TCP_NODELAY, Nagle's algorithm
        # waits for the server's delayed ACK and adds ~40 ms to every request
        conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return conn


def reformulate(sparql: str) -> dict:
    # a GET is one write: a POST sends headers and body separately and, against the JDK
    # HTTP server, stalls on a delayed ACK (~50 ms measured on Docker Desktop)
    path = "/ontop/reformulate?" + urllib.parse.urlencode({"query": sparql})
    for attempt in (1, 2):
        conn = _connection()
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            payload = json.loads(resp.read())
            break
        except (http.client.HTTPException, OSError) as exc:
            conn.close()
            _local.conn = None
            if attempt == 2:
                raise CompileError("reformulate", f"Ontop sidecar unreachable: {exc}", 503) from exc
    if resp.status != 200:
        raise CompileError("reformulate", payload.get("error", "Ontop reformulation failed"))
    if payload.get("sql") is None:
        raise CompileError("reformulate",
                           "Ontop could not push this query into a single SQL statement "
                           f"(plan nodes outside SQL: {payload.get('other_nodes')})")
    return payload


def sidecar_healthy() -> bool:
    try:
        conn = _connection()
        conn.request("GET", "/health")
        resp = conn.getresponse()
        resp.read()
        return resp.status == 200
    except (http.client.HTTPException, OSError):
        _local.conn = None
        return False


# --------------------------------------------------------------------------- #
# 3. finishing: RDF terms -> SQL expressions
# --------------------------------------------------------------------------- #
_CAST = re.compile(r"^[A-Z]+ToTEXT$")


def _term_sql(term: dict, columns: dict[str, exp.Expression], as_text: bool) -> exp.Expression:
    """The SQL for one Ontop term. ``as_text`` keeps casts (IRI building needs strings);
    otherwise literal casts are dropped so the column keeps its SQL type."""
    if "var" in term:
        if term["var"] not in columns:
            raise CompileError("finish", f"variable {term['var']} is not a native column")
        return columns[term["var"]].copy()
    if "const" in term:
        return exp.Literal.string(term["const"])
    fn, args = term["fn"], term["args"]
    if fn == "RDF":
        lexical, rdf_type = args
        is_iri = rdf_type.get("const") == "IRI"
        return _term_sql(lexical, columns, as_text=is_iri)
    if "{}" in fn:                                    # IRI template
        parts = fn.split("{}")
        if len(parts) - 1 != len(args):
            raise CompileError("finish", f"template {fn} has {len(args)} arguments")
        pieces: list[exp.Expression] = []
        for i, text in enumerate(parts):
            if text:
                pieces.append(exp.Literal.string(text))
            if i < len(args):
                pieces.append(_term_sql(args[i], columns, as_text=True))
        out = pieces[0]
        for p in pieces[1:]:
            out = exp.DPipe(this=out, expression=p, safe=True)
        return out
    if "Concat" in term.get("class", ""):            # SPARQL CONCAT left above the SQL
        parts_sql = [_term_sql(a, columns, as_text=True) for a in args]
        out = parts_sql[0]
        for piece in parts_sql[1:]:                   # null-rejecting, as in SPARQL
            out = exp.DPipe(this=out, expression=piece)
        return out
    if _CAST.match(fn) or "Cast" in term.get("class", ""):
        inner = _term_sql(args[0], columns, as_text)
        return exp.cast(inner, "TEXT") if as_text else inner
    raise CompileError("finish", f"unsupported term function {fn!r} ({term.get('class')})")


def finish(payload: dict) -> exp.Select:
    tree = sqlglot.parse_one(payload["sql"], read="postgres")
    if not isinstance(tree, exp.Select):
        raise CompileError("finish", f"native SQL is a {type(tree).__name__}, not a SELECT")
    columns: dict[str, exp.Expression] = {}
    for item in tree.expressions:
        alias = item.alias_or_name
        columns[alias] = item.this if isinstance(item, exp.Alias) else item
    projected = []
    for var in payload["projection"]:
        term = payload["terms"].get(var)
        expr = _term_sql(term, columns, as_text=False) if term else exp.Null()
        projected.append(exp.alias_(expr, var, quoted=True))
    if tree.args.get("distinct"):
        # dropping helper columns under DISTINCT would change which rows are distinct
        inner = tree.copy()
        outer = exp.select(*[exp.column(v, table="q", quoted=True) for v in payload["projection"]])
        inner.set("expressions", projected + [e for e in tree.expressions])
        return _pin_decimals(outer.from_(inner.subquery("q")))
    tree.set("expressions", projected)
    return _pin_decimals(tree)


def _pin_decimals(tree: exp.Expression) -> exp.Expression:
    """Ontop writes ``CAST(x AS DECIMAL)``: unbounded in PostgreSQL, but NUMBER(38,0) in
    Snowflake (fractions silently dropped) and DECIMAL(18,3) in DuckDB (overflow above
    ~1e15). Pin an explicit precision so every dialect keeps the value."""
    for dt in tree.find_all(exp.DataType):
        if dt.this == exp.DataType.Type.DECIMAL and not dt.expressions:
            dt.set("expressions", [exp.DataTypeParam(this=exp.Literal.number(38)),
                                   exp.DataTypeParam(this=exp.Literal.number(6))])
    return tree


# --------------------------------------------------------------------------- #
# 4. the pipeline
# --------------------------------------------------------------------------- #
def compile_sparql(sparql: str, dialect: str = "postgres") -> Compiled:
    if dialect not in DIALECTS:
        raise CompileError("request", f"target_dialect must be one of {DIALECTS}", 400)
    t0 = time.perf_counter()
    validate(sparql)
    t1 = time.perf_counter()
    payload = reformulate(sparql)
    t2 = time.perf_counter()
    tree = finish(payload)
    sql = tree.sql(dialect=dialect, pretty=True)
    t3 = time.perf_counter()
    tables = sorted({t.name for t in tree.find_all(exp.Table) if t.name})
    table_refs = [t for t in tree.find_all(exp.Table) if t.name]
    return Compiled(
        sql=sql, dialect=dialect, projection=list(payload["projection"]),
        native_sql=payload["sql"], tables=tables, join_count=max(len(table_refs) - 1, 0),
        timings_ms={"validate": round((t1 - t0) * 1e3, 3),
                    "reformulate": round((t2 - t1) * 1e3, 3),
                    "ontop_internal": round(payload["micros"] / 1e3, 3),
                    "finish_and_transpile": round((t3 - t2) * 1e3, 3),
                    "total": round((t3 - t0) * 1e3, 3)})
