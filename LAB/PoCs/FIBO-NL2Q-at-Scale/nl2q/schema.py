"""The FIBEN relational schema, parsed from ``FIBEN.sql`` (Db2 / PostgreSQL DDL).

FIBEN's schema is a relational encoding of an ontology, and the parser keeps that
structure explicit:

* a table whose primary key is also a foreign key to another table's primary key is a
  **subclass table** (``LONGTERMDEBT.LONGTERMDEBTID -> DISCLOSURE.DISCLOSUREID``);
* any other foreign key is an **object property** named after the column
  (``SECURITY.ISTRADEDON -> FINANCIALMARKET``);
* the remaining columns are **datatype properties** (``LISTEDSECURITY.HASTICKERSYMBOL``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import paths

_CREATE = re.compile(r"CREATE TABLE\s+(\w+)\s*\((.*?)\);", re.S | re.I)
_FK = re.compile(r"ALTER TABLE\s+(\w+)\s+ADD CONSTRAINT\s+(\w+)\s+FOREIGN KEY\s*\((\w+)\)\s*"
                 r"REFERENCES\s+(\w+)\s*\((\w+)\)", re.S | re.I)
_PK = re.compile(r"PRIMARY KEY\s*\(([^)]*)\)", re.I)


@dataclass
class Column:
    name: str
    sql_type: str           # normalised: BIGINT, INTEGER, VARCHAR, TIMESTAMP, DATE, DOUBLE, CHAR
    nullable: bool = True

    @property
    def xsd(self) -> str:
        return {"BIGINT": "integer", "INTEGER": "integer", "DOUBLE": "double",
                "DATE": "date", "TIMESTAMP": "dateTime"}.get(self.sql_type, "string")

    @property
    def pg_type(self) -> str:
        return {"BIGINT": "int8", "INTEGER": "int4", "DOUBLE": "float8", "DATE": "date",
                "TIMESTAMP": "timestamp", "CHAR": "bpchar"}.get(self.sql_type, "varchar")

    @property
    def duck_type(self) -> str:
        return {"CHAR": "VARCHAR"}.get(self.sql_type, self.sql_type)


@dataclass
class ForeignKey:
    name: str
    table: str
    column: str
    ref_table: str
    ref_column: str


@dataclass
class Table:
    name: str
    columns: list[Column]
    pk: list[str]
    fks: list[ForeignKey] = field(default_factory=list)

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)

    @property
    def parent_fk(self) -> ForeignKey | None:
        """The FK that makes this a subclass table (PK -> parent PK), if any."""
        return next((f for f in self.fks if [f.column] == self.pk), None)

    @property
    def relation_fks(self) -> list[ForeignKey]:
        return [f for f in self.fks if [f.column] != self.pk]

    @property
    def data_columns(self) -> list[Column]:
        fk_cols = {f.column for f in self.fks}
        return [c for c in self.columns if c.name not in self.pk and c.name not in fk_cols]


@dataclass
class Schema:
    tables: dict[str, Table]

    @property
    def subclass_edges(self) -> list[tuple[str, str]]:
        return [(t.name, t.parent_fk.ref_table) for t in self.tables.values() if t.parent_fk]

    @property
    def relation_fks(self) -> list[ForeignKey]:
        return [f for t in self.tables.values() for f in t.relation_fks]


def _norm_type(raw: str) -> str:
    r = raw.upper()
    for key, norm in (("BIGINT", "BIGINT"), ("INTEGER", "INTEGER"), ("DOUBLE", "DOUBLE"),
                      ("TIMESTAMP", "TIMESTAMP"), ("DATE", "DATE"), ("CHARACTER", "CHAR"),
                      ("VARCHAR", "VARCHAR")):
        if r.startswith(key):
            return norm
    raise ValueError(f"unsupported column type {raw!r}")


def parse_ddl(text: str) -> Schema:
    tables: dict[str, Table] = {}
    for name, body in _CREATE.findall(text):
        pk = [c.strip() for c in _PK.search(body).group(1).split(",")]
        body_wo_pk = _PK.sub("", body)
        cols = []
        for part in body_wo_pk.split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"(\w+)\s+(.+?)(\s+NOT NULL)?$", part, re.I)
            cols.append(Column(m.group(1), _norm_type(m.group(2)), not m.group(3)))
        tables[name] = Table(name, cols, pk)
    for table, cname, col, ref_t, ref_c in _FK.findall(text):
        tables[table].fks.append(ForeignKey(cname, table, col, ref_t, ref_c))
    return Schema(tables)


@lru_cache(maxsize=1)
def load() -> Schema:
    return parse_ddl(paths.FIBEN_DDL.read_text(encoding="utf-8"))
