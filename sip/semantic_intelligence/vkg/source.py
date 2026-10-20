"""Relational sources for the virtual knowledge graph.

A :class:`RelationalSource` is a registered database the mappings read from. Two kinds:

* ``sqlite`` (default, stdlib ``sqlite3``): a database file opened **read-only**
  (``mode=ro``), or an in-memory database built from a DDL + INSERT ``script`` and then
  switched to ``PRAGMA query_only``;
* ``duckdb``: a database file opened ``read_only=True``. DuckDB is optional; the kind is
  refused with a clear message when the package is not importable.

The platform never writes to a source. Every SQL text that reaches a connection passes
:func:`check_select` first (one statement, ``SELECT``/``WITH`` only, no DDL/DML
keyword outside string literals), and the connection itself is read-only as a second
line of defence.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Column", "ForeignKey", "Table", "Schema", "RelationalSource", "UnsafeSQL",
           "check_select", "check_table_name", "unquote", "duckdb_available"]


class UnsafeSQL(ValueError):
    """SQL that is not a single read-only SELECT."""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex|"
    r"truncate|grant|revoke|copy|install|load|begin|commit|rollback|savepoint)\b", re.I)
_IDENT = r'(?:"(?:[^"]|"")+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_$]*)'
_TABLE_NAME = re.compile(rf"^\s*{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}}\s*$")


def _blank_literals(sql: str) -> str:
    """Remove comments and the contents of string literals / quoted identifiers."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def check_select(sql: str) -> str:
    """Return *sql* without a trailing ``;`` if it is one read-only SELECT, else raise."""
    if not sql or not sql.strip():
        raise UnsafeSQL("empty SQL")
    body = sql.strip().rstrip(";").strip()
    bare = _blank_literals(body)
    if ";" in bare:
        raise UnsafeSQL("only one SQL statement is allowed")
    head = bare.lstrip("( \t\r\n").split(None, 1)[0].lower() if bare.strip() else ""
    if head not in ("select", "with"):
        raise UnsafeSQL(f"only SELECT queries are allowed in logical tables, got {head!r}")
    bad = _FORBIDDEN.search(bare)
    if bad:
        raise UnsafeSQL(f"keyword {bad.group(1).upper()!r} is not allowed in a read-only query")
    return body


def check_table_name(name: str) -> str:
    if not _TABLE_NAME.match(name or ""):
        raise UnsafeSQL(f"not a table name: {name!r}")
    return name.strip()


def unquote(identifier: str) -> str:
    """``"COMP_ID"`` -> ``COMP_ID``; the last part of a qualified name."""
    s = identifier.strip()
    parts = re.findall(_IDENT, s)
    s = parts[-1] if parts else s
    if len(s) >= 2 and (s[0], s[-1]) in (('"', '"'), ("`", "`"), ("[", "]")):
        s = s[1:-1].replace('""', '"')
    return s


def duckdb_available() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class Column:
    name: str
    type: str = ""
    nullable: bool = True
    primary_key: bool = False


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def column(self, name: str) -> Column | None:
        n = unquote(name)
        for c in self.columns:
            if c.name == n:
                return c
        low = n.lower()
        return next((c for c in self.columns if c.name.lower() == low), None)

    def fk_for(self, column: str) -> ForeignKey | None:
        return next((f for f in self.foreign_keys if f.columns == [column]), None)


@dataclass
class Schema:
    tables: dict[str, Table] = field(default_factory=dict)

    def table(self, name: str) -> Table | None:
        n = unquote(name)
        if n in self.tables:
            return self.tables[n]
        low = n.lower()
        return next((t for k, t in self.tables.items() if k.lower() == low), None)

    def as_dict(self) -> dict:
        return {"tables": [asdict(t) for t in self.tables.values()]}


class RelationalSource:
    """A registered, read-only relational database."""

    def __init__(self, source_id: str, kind: str = "sqlite", path: str | None = None,
                 script: str | None = None, title: str = "",
                 ontop_endpoint: str | None = None) -> None:
        if kind not in ("sqlite", "duckdb"):
            raise ValueError("kind is sqlite | duckdb")
        if kind == "duckdb" and not duckdb_available():
            raise ValueError("kind 'duckdb' needs the optional duckdb package")
        if bool(path) == bool(script):
            raise ValueError("give exactly one of path or script")
        if kind == "duckdb" and script:
            raise ValueError("duckdb sources are registered by file path")
        if path and not Path(path).is_file():
            raise FileNotFoundError(path)
        self.id, self.kind, self.path, self.title = source_id, kind, path, title or source_id
        self.ontop_endpoint = ontop_endpoint
        self._conn: Any = None
        self._script = script
        self._schema: Schema | None = None
        self.connect()

    # -- connection ------------------------------------------------------- #
    def connect(self):
        if self._conn is not None:
            return self._conn
        if self.kind == "duckdb":
            import duckdb
            self._conn = duckdb.connect(self.path, read_only=True)
        elif self.path:
            uri = Path(self.path).resolve().as_uri() + "?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.executescript(self._script)
            self._conn.execute("PRAGMA query_only = ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None and self.path:   # an in-memory script DB would be lost
            self._conn.close()
            self._conn = None

    def describe(self) -> dict:
        return {"source": self.id, "kind": self.kind, "path": self.path, "title": self.title,
                "in_memory": self.path is None, "ontop_endpoint": self.ontop_endpoint,
                "tables": sorted(self.schema().tables)}

    # -- schema ------------------------------------------------------------ #
    def schema(self, refresh: bool = False) -> Schema:
        if self._schema is None or refresh:
            self._schema = self._duck_schema() if self.kind == "duckdb" else self._sqlite_schema()
        return self._schema

    def _sqlite_schema(self) -> Schema:
        c = self.connect()
        out = Schema()
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            q = name.replace('"', '""')
            cols = c.execute(f'PRAGMA table_info("{q}")').fetchall()
            pk = [r[1] for r in sorted((r for r in cols if r[5]), key=lambda r: r[5])]
            t = Table(name, [Column(r[1], (r[2] or "").upper(), not r[3] and not r[5], bool(r[5]))
                             for r in cols], pk)
            fks: dict[int, ForeignKey] = {}
            for r in c.execute(f'PRAGMA foreign_key_list("{q}")').fetchall():
                fk = fks.setdefault(r[0], ForeignKey([], r[2], []))
                fk.columns.append(r[3])
                fk.ref_columns.append(r[4])
            for fk in fks.values():         # REFERENCES parent  ->  the parent's primary key
                if any(rc is None for rc in fk.ref_columns):
                    parent = [r[1] for r in sorted(
                        (r for r in c.execute(
                            f'PRAGMA table_info("{fk.ref_table.replace(chr(34), chr(34) * 2)}")'
                        ).fetchall() if r[5]), key=lambda r: r[5])]
                    fk.ref_columns = parent or fk.ref_columns
            t.foreign_keys = list(fks.values())
            out.tables[name] = t
        return out

    def _duck_schema(self) -> Schema:
        c = self.connect()
        out = Schema()
        for (name,) in c.execute("SELECT table_name FROM information_schema.tables "
                                 "WHERE table_schema = 'main' ORDER BY table_name").fetchall():
            cols = c.execute("SELECT column_name, data_type, is_nullable FROM "
                             "information_schema.columns WHERE table_name = ? "
                             "ORDER BY ordinal_position", [name]).fetchall()
            t = Table(name, [Column(r[0], str(r[1]).upper(), r[2] == "YES") for r in cols])
            for ctype, ccols, rtable, rcols in c.execute(
                    "SELECT constraint_type, constraint_column_names, referenced_table, "
                    "referenced_column_names FROM duckdb_constraints() WHERE table_name = ?",
                    [name]).fetchall():
                if ctype == "PRIMARY KEY":
                    t.primary_key = list(ccols)
                elif ctype == "FOREIGN KEY":
                    t.foreign_keys.append(ForeignKey(list(ccols), rtable, list(rcols or [])))
            for col in t.columns:
                col.primary_key = col.name in t.primary_key
                col.nullable = col.nullable and not col.primary_key
            out.tables[name] = t
        return out

    # -- queries ----------------------------------------------------------- #
    def query(self, sql: str, limit: int | None = None) -> tuple[list[str], list[tuple]]:
        """Run one read-only SELECT; ``limit`` wraps it in an outer ``LIMIT``."""
        body = check_select(sql)
        if limit is not None:
            body = f"SELECT * FROM ({body}) AS _sip_q LIMIT {int(limit)}"
        cur = self.connect().execute(body)
        cols = [d[0] for d in cur.description or ()]
        return cols, [tuple(r) for r in cur.fetchall()]

    def table_query(self, table_name: str) -> str:
        return f"SELECT * FROM {check_table_name(table_name)}"

    def columns_of(self, sql: str) -> list[str]:
        return self.query(sql, limit=0)[0]

    def distinct_values(self, table: str, column: str, max_values: int = 20) -> list:
        q = column.replace('"', '""')
        cols, rows = self.query(f'SELECT DISTINCT "{q}" FROM {check_table_name(table)}',
                                limit=max_values + 1)
        return [r[0] for r in rows]
