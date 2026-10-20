"""Load the FIBEN CSVs (Db2 DEL export: no header, quoted strings, ``+1.2E+003`` floats,
``YYYY-MM-DD-HH.MM.SS.ffffff`` timestamps, ``YYYYMMDD`` dates) into DuckDB, schema
``FIBEN``, with the DDL's primary keys. Quoted upper-case identifiers, as the gold SQL
and the R2RML mapping reference them.

    python -m nl2q.load_fiben          # builds data/fiben.duckdb (~1 min)
"""

from __future__ import annotations

import sys
import time

import duckdb

from . import paths, schema


def _cast(col: schema.Column) -> str:
    c = f'NULLIF(TRIM("{col.name}"), \'\')'
    if col.sql_type == "TIMESTAMP":
        return f"strptime({c}, '%Y-%m-%d-%H.%M.%S.%f')"
    if col.sql_type == "DATE":
        return f"CAST(strptime({c}, '%Y%m%d') AS DATE)"
    if col.sql_type in ("BIGINT", "INTEGER", "DOUBLE"):
        return f"CAST({c} AS {col.sql_type})"
    return c


def build(db_path=paths.DB, csv_dir=paths.FIBEN_CSV, verbose: bool = True) -> dict[str, int]:
    s = schema.load()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(f'CREATE SCHEMA "{paths.SCHEMA}"')
    counts = {}
    t0 = time.time()
    for t in s.tables.values():
        cols = ", ".join(f'"{c.name}" {c.duck_type}' for c in t.columns)
        con.execute(f'CREATE TABLE "{paths.SCHEMA}"."{t.name}" ({cols}, '
                    f'PRIMARY KEY ({", ".join(chr(34) + k + chr(34) for k in t.pk)}))')
        src = csv_dir / f"{t.name}.csv"
        names = "{" + ", ".join(f"'{c.name}': 'VARCHAR'" for c in t.columns) + "}"
        select = ", ".join(_cast(c) for c in t.columns)
        con.execute(f'INSERT INTO "{paths.SCHEMA}"."{t.name}" SELECT {select} FROM '
                    f"read_csv('{src.as_posix()}', header=false, quote='\"', "
                    f"columns={names}, auto_detect=false, null_padding=true)")
        counts[t.name] = con.execute(f'SELECT count(*) FROM "{paths.SCHEMA}"."{t.name}"').fetchone()[0]
    con.close()
    if verbose:
        print(f"loaded {len(counts)} tables, {sum(counts.values()):,} rows in {time.time() - t0:.0f}s"
              f" -> {db_path}")
    return counts


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(paths.DB), read_only=read_only)
    con.execute("SET enable_progress_bar = false")
    return con


if __name__ == "__main__":
    build()
    sys.exit(0)
