"""ACME insurance (data.world, Apache-2.0): the literature-comparability track (PLAN.md P4).

The benchmark behind the published 16.7% (SQL) / 54.2% (KG) / 72.55% (OBQC+repair) /
97.4% (SPC) results. This module puts it on the same VKG stack as FIBEN:

1. load the 29 CSV tables into ``data/acme_vkg.duckdb`` (schema ``public``, lower-case
   names, as the R2RML's unquoted identifiers expect);
2. rewrite the data.world R2RML (``myinsurancecompany.omg-pc-database.x`` table names) for
   Ontop and generate ``db-metadata.json`` from the loaded database;
3. read the questions with their gold SQL and gold SPARQL from ``acme-benchmark.ttl``
   (the SPARQL's ``SERVICE :mapped { }`` wrapper — data.world's virtualisation — is
   removed: the mapping *is* the virtual graph here);
4. execute gold SQL on DuckDB and gold SPARQL through an ACME Ontop sidecar (:18082), and
   report how often the two published gold languages agree with each other.

    python -m nl2q.acme load        # database + Ontop artefacts (artifacts/acme/)
    python -m nl2q.acme gold        # needs the ACME sidecar on :18082
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import duckdb
from rdflib import Graph, Literal, Namespace

from . import compare, paths

RAW = paths.ROOT / "data" / "raw" / "acme"
DB = paths.ROOT / "data" / "acme_vkg.duckdb"
OUT = paths.ARTIFACTS / "acme"
SIDECAR = "http://localhost:18082"
RR = Namespace("http://www.w3.org/ns/r2rml#")
QA = "http://models.data.world/benchmarks/QandA#"


def load() -> dict:
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA public")
    counts = {}
    types = _types_from_ddl()
    for f in sorted((RAW / "data").glob("*.csv")):
        t = f.stem.lower()
        con.execute(f'CREATE TABLE public."{t}" AS SELECT * FROM read_csv_auto(\'{f.as_posix()}\', header=true, all_varchar=true)')
        cols = [r[0] for r in con.execute(f"DESCRIBE public.\"{t}\"").fetchall()]
        for c in cols:
            if c != c.lower():
                con.execute(f'ALTER TABLE public."{t}" RENAME COLUMN "{c}" TO "{c.lower()}"')
            # the DDL's type (datetime -> TIMESTAMP etc.): the ontology's ranges follow it
            typ = types.get(t, {}).get(c.lower())
            if typ:
                con.execute(f'ALTER TABLE public."{t}" ALTER COLUMN "{c.lower()}" TYPE {typ} '
                            f'USING TRY_CAST(NULLIF(TRIM("{c.lower()}"), \'\') AS {typ})')
        counts[t] = con.execute(f'SELECT count(*) FROM public."{t}"').fetchone()[0]
    OUT.mkdir(parents=True, exist_ok=True)
    _rewrite_mapping(con)
    meta = _metadata(con)
    con.close()
    (OUT / "db-metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (OUT / "ontology.ttl").write_text((RAW / "insurance.ttl").read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "ontop.properties").write_text(
        "jdbc.url=jdbc:postgresql://no-database.invalid:5432/acme\njdbc.driver=org.postgresql.Driver\n"
        "jdbc.user=none\njdbc.password=none\n", encoding="utf-8")
    return counts


_PG = {"BIGINT": "int8", "INTEGER": "int4", "DOUBLE": "float8", "DATE": "date", "TIMESTAMP": "timestamp",
       "VARCHAR": "varchar", "BOOLEAN": "bool", "DECIMAL": "numeric"}


def _types_from_ddl() -> dict[str, dict[str, str]]:
    ddl = (RAW / "ACME_small.ddl").read_text(encoding="utf-8", errors="replace")
    conv = [(r"^bigint", "BIGINT"), (r"^int", "INTEGER"), (r"^smallint", "INTEGER"),
            (r"^datetime", "TIMESTAMP"), (r"^date", "DATE"), (r"^decimal\((\d+),\s*(\d+)\)", r"DECIMAL(\1,\2)"),
            (r"^numeric\((\d+),\s*(\d+)\)", r"DECIMAL(\1,\2)"), (r"^float|^real", "DOUBLE"),
            (r"^bit", "BOOLEAN"), (r"^(var)?char", "VARCHAR")]
    out: dict[str, dict[str, str]] = {}
    for t, body in re.findall(r"CREATE TABLE\s+(\w+)\s*\((.*?)\n\)", ddl, re.S | re.I):
        cols = {}
        for line in body.splitlines():
            m = re.match(r"\s*(\w+)\s+(\w+(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)", line)
            if not m or m.group(1).upper() in ("PRIMARY", "FOREIGN", "CONSTRAINT"):
                continue
            raw = m.group(2).lower()
            for pat, rep in conv:
                if re.match(pat, raw):
                    cols[m.group(1).lower()] = re.sub(pat, rep, raw) if "\\" in rep else rep
                    break
        out[t.lower()] = cols
    return out


def _pk_from_ddl() -> dict[str, list[str]]:
    ddl = (RAW / "ACME_small.ddl").read_text(encoding="utf-8", errors="replace")
    out = {}
    for t, body in re.findall(r"CREATE TABLE\s+(\w+)\s*\((.*?)\n\)", ddl, re.S | re.I):
        m = re.search(r"PRIMARY KEY\s*\(([^)]*)\)", body, re.I)
        if m:
            out[t.lower()] = [c.strip().split()[0].lower() for c in m.group(1).split(",")]
    return out


def _metadata(con) -> dict:
    pks = _pk_from_ddl()
    rels = []
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type IN ('BASE TABLE','VIEW')").fetchall():
        cols = con.execute(f"DESCRIBE public.\"{t}\"").fetchall()
        q = lambda x: f'"{x}"'  # noqa: E731
        pk = [c for c in pks.get(t, []) if c in {r[0] for r in cols}]
        rels.append({"uniqueConstraints": ([{"name": f"{t}_pkey", "determinants": [q(c) for c in pk],
                                              "isPrimaryKey": True}] if pk else []),
                     "otherFunctionalDependencies": [], "foreignKeys": [],
                     "columns": [{"name": q(c[0]), "isNullable": c[0] not in pk,
                                  "datatype": _PG.get(c[1].split("(")[0], "varchar")} for c in cols],
                     "name": [q("public"), q(t)]})
    return {"relations": rels, "metadata": {"dbmsProductName": "PostgreSQL", "dbmsVersion": "16.0",
                                            "driverName": "PostgreSQL JDBC Driver", "driverVersion": "42.7.4",
                                            "quotationString": "\"", "extractionTime": "generated",
                                            "idFactoryType": "POSTGRESQL"}}


def _rewrite_mapping(con) -> None:
    """data.world table names -> ``"public"."x"``; every ``rr:sqlQuery`` becomes a DuckDB view
    referenced as a table (Ontop's offline mode cannot build black-box views for SQL it
    does not parse, and needs no SQL parsing for a table)."""
    g = Graph().parse(RAW / "mapping.r2rml", format="turtle")
    for s, o in list(g.subject_objects(RR.tableName)):
        name = str(o).rsplit(".", 1)[-1].lower()
        g.remove((s, RR.tableName, o))
        g.add((s, RR.tableName, Literal(f'"public"."{name}"')))
    views: dict[str, str] = {}
    for s, o in list(g.subject_objects(RR.sqlQuery)):
        sql = str(o)
        name = views.get(sql)
        if name is None:
            name = f"r2rml_view_{len(views) + 1}"
            views[sql] = name
            con.execute("SET search_path = 'public'")
            con.execute(f'CREATE VIEW public."{name}" AS {sql}')
        g.remove((s, RR.sqlQuery, o))
        g.add((s, RR.tableName, Literal(f'"public"."{name}"')))
    g.serialize(OUT / "mapping.r2rml.ttl", format="turtle")
    (OUT / "views.json").write_text(json.dumps({v: k for k, v in views.items()}, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------- questions
def questions() -> list[dict]:
    g = Graph().parse(RAW / "acme-benchmark.ttl")
    out = []
    for inq in g.subjects(predicate=None, object=None):
        prompt = g.value(inq, _u(QA + "prompt"))
        if prompt is None:
            continue
        rec = {"id": str(inq).rsplit("/", 1)[-1], "question": str(prompt), "sql": None, "sparql": None}
        for q in g.objects(inq, _u(QA + "expects")):
            lang = str(g.value(q, _u(QA + "inLanguage")) or "")
            text = str(g.value(q, _u(QA + "queryText")) or "")
            if lang.endswith("SQL"):
                rec["sql"] = text
            elif lang.endswith("SPARQL"):
                rec["sparql"] = text
        if rec not in out:
            out.append(rec)
    return sorted({r["id"]: r for r in out}.values(), key=lambda r: r["question"])


def _u(s):
    from rdflib import URIRef
    return URIRef(s)


def strip_service(sparql: str) -> str:
    """Remove data.world's ``SERVICE :mapped { ... }`` wrapper (keep its body)."""
    i = sparql.find("SERVICE")
    if i < 0:
        return sparql
    j = sparql.index("{", i)
    depth = 0
    for k in range(j, len(sparql)):
        depth += {"{": 1, "}": -1}.get(sparql[k], 0)
        if depth == 0:
            return sparql[:i] + sparql[j + 1:k] + sparql[k + 1:]
    return sparql


@lru_cache(maxsize=1)
def _compiler():
    spec = importlib.util.spec_from_file_location("acme_compiler", paths.COMPILER_APP / "app" / "compiler.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["acme_compiler"] = mod
    spec.loader.exec_module(mod)
    mod.SIDECAR_URL = SIDECAR
    return mod


def run_sparql(con, sparql: str):
    from .vkg import fix_temporal_projection
    c = _compiler()
    try:
        comp = c.compile_sparql(sparql, "duckdb")
    except c.CompileError as exc:
        return None, f"{exc.stage}: {str(exc)[:200]}"
    try:
        cur = con.execute(fix_temporal_projection(comp.sql))
        return (cur.fetchall(), len(cur.description)), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"execute: {str(exc)[:200]}"


def gold() -> dict:
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET search_path = 'public'")
    rows = []
    for q in questions():
        rec = {"id": q["id"], "question": q["question"]}
        sig = None
        if q["sql"]:
            try:
                try:
                    cur = con.execute(q["sql"])
                except duckdb.Error:          # a few gold queries use T-SQL (DATEDIFF(day, a, b))
                    import sqlglot
                    cur = con.execute(sqlglot.transpile(q["sql"], read="tsql", write="duckdb")[0])
                r = cur.fetchall()
                sig = compare.signature(r, len(cur.description))
                rec.update(sql_ok=True, sql_rows=len(r))
            except Exception as exc:  # noqa: BLE001
                rec.update(sql_ok=False, sql_error=str(exc)[:200])
        if q["sparql"]:
            res, err = run_sparql(con, strip_service(q["sparql"]))
            rec["sparql_ok"] = res is not None
            if res is None:
                rec["sparql_error"] = err
            else:
                rec["sparql_rows"] = len(res[0])
                if sig is not None:
                    m = compare.compare(sig, res[0], res[1])
                    rec.update(agree_strict=m.strict, agree_lenient=m.lenient, agree_note=m.reason)
        if sig is not None:
            rec["signature"] = sig.to_json()
        rows.append(rec)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gold.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    n = len(rows)
    summ = {"questions": n,
            "sql_executes": sum(r.get("sql_ok", False) for r in rows),
            "sparql_compiles_and_runs_via_ontop": sum(r.get("sparql_ok", False) for r in rows),
            "sql_and_sparql_agree_strict": sum(r.get("agree_strict", False) for r in rows),
            "sql_and_sparql_agree_lenient": sum(r.get("agree_lenient", False) for r in rows)}
    (OUT / "gold_summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    return summ


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "load"
    print(json.dumps(load() if cmd == "load" else gold(), indent=1))
