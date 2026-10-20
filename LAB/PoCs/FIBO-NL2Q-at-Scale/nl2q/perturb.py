"""Perturbed database instances for test-suite accuracy (Zhong et al. 2020; SPC 2026).

Execution accuracy on one database accepts wrong queries that happen to return the same
rows. Each variant is a schema of **views** over the base tables (no data copied), built so
that typical wrong queries diverge from the gold answer:

* ``V1`` drop — a deterministic ~25% of the rows of every *unreferenced* table disappear
  (changes counts, sums, averages). Referenced rows stay: Ontop trusts declared foreign
  keys, so a dangling reference would make the instance invalid (found by the witness
  check);
* ``V2`` rewire — relationship foreign keys are re-pointed to another existing row of the
  same target table for ~30% of rows (a query following the wrong path stops agreeing);
* ``V3`` fan-out — Holding and SecuritiesTransaction rows are duplicated with fresh keys
  (aggregates over a fanning join diverge from aggregates at the right grain);
* ``V4`` reclassify — ~20% of the rows of each subclass table of ElementOfFinancialStatement
  and Disclosure move to a sibling subclass (wrong-class queries diverge).

Gold rows are recomputed per variant by executing the gold SQL against the variant schema.

    python -m nl2q.perturb        # creates schemas FIBEN_V1..V4 in the database (views)
"""

from __future__ import annotations

import duckdb

from . import paths, schema

VARIANTS = ("V1", "V2", "V3", "V4")


def _h(expr: str, salt: int) -> str:
    return f"(hash({expr}, {salt}) % 100)"


def build(db_path=paths.DB) -> None:
    s = schema.load()
    con = duckdb.connect(str(db_path))
    base = paths.SCHEMA
    for v in VARIANTS:
        con.execute(f'DROP SCHEMA IF EXISTS "{base}_{v}" CASCADE')
        con.execute(f'CREATE SCHEMA "{base}_{v}"')
    # V1 may only drop rows nothing references: Ontop trusts declared foreign keys (it
    # eliminates joins through them), so a dangling reference makes an instance invalid.
    referenced = {f.ref_table for f in s.relation_fks} | {p for _, p in s.subclass_edges}
    for t in s.tables.values():
        pk = t.pk[0]
        cols = ", ".join(f'"{c.name}"' for c in t.columns)
        src = f'"{base}"."{t.name}"'
        # V1: drop ~25% of the rows of unreferenced (leaf) tables; materialised
        if t.name in referenced:
            con.execute(f'CREATE VIEW "{base}_V1"."{t.name}" AS SELECT {cols} FROM {src}')
        else:
            con.execute(f'CREATE TABLE "{base}_V1"."{t.name}" AS SELECT {cols} FROM {src} '
                        f'WHERE {_h(chr(34) + pk + chr(34), 11)} >= 25')
        # V2: re-point relationship FKs for ~30% of rows to another existing target id
        sel = []
        for c in t.columns:
            fk = next((f for f in t.relation_fks if f.column == c.name), None)
            if fk is None:
                sel.append(f'"{c.name}"')
                continue
            tgt = f'"{base}"."{fk.ref_table}"'
            sel.append(
                f'CASE WHEN {_h(chr(34) + pk + chr(34), 23)} < 30 THEN '
                f'(SELECT "{fk.ref_column}" FROM {tgt} ORDER BY hash("{fk.ref_column}", hash(x."{pk}")) LIMIT 1) '
                f'ELSE "{c.name}" END AS "{c.name}"')
        if t.relation_fks:
            # deterministic shift: the FK value of the row 7 positions later (an existing
            # key of the same target table) — cheap, unlike a correlated lookup per row
            sel2 = []
            for c in t.columns:
                fk = next((f for f in t.relation_fks if f.column == c.name), None)
                if fk is None:
                    sel2.append(f'x."{c.name}"')
                else:
                    sel2.append(f'CASE WHEN {_h("x." + chr(34) + pk + chr(34), 23)} < 30 THEN '
                                f'coalesce(lead(x."{c.name}", 7) OVER (ORDER BY x."{pk}"), x."{c.name}") '
                                f'ELSE x."{c.name}" END AS "{c.name}"')
            con.execute(f'CREATE VIEW "{base}_V2"."{t.name}" AS SELECT {", ".join(sel2)} FROM {src} AS x')
        else:
            con.execute(f'CREATE VIEW "{base}_V2"."{t.name}" AS SELECT {cols} FROM {src}')
        # V3: duplicate fan-out tables with fresh keys
        if t.name in ("HOLDING", "SECURITIESTRANSACTION"):
            dup = ", ".join(f'"{c.name}" + 900000000000000' if c.name == pk else f'"{c.name}"'
                            for c in t.columns)
            con.execute(f'CREATE TABLE "{base}_V3"."{t.name}" AS SELECT {cols} FROM {src} '
                        f'UNION ALL SELECT {dup} FROM {src} WHERE {_h(chr(34) + pk + chr(34), 31)} < 40')
        else:
            con.execute(f'CREATE VIEW "{base}_V3"."{t.name}" AS SELECT {cols} FROM {src}')
    # V4: reclassify subclass rows between siblings (same parent)
    by_parent: dict[str, list[str]] = {}
    for t in s.tables.values():
        if t.parent_fk and t.parent_fk.ref_table in ("ELEMENTOFFINANCIALSTATEMENT", "DISCLOSURE"):
            by_parent.setdefault(t.parent_fk.ref_table, []).append(t.name)
    moved: set[str] = set()
    for parent, kids in by_parent.items():
        kids = sorted(kids)
        for i, k in enumerate(kids):
            nxt = kids[(i + 1) % len(kids)]
            prv = kids[(i - 1) % len(kids)]
            tk, tp = s.tables[k], s.tables[prv]
            cols_k = [c.name for c in tk.columns]
            if [c.name for c in tp.columns][1:] != cols_k[1:]:
                continue
            pk_k, pk_p = tk.pk[0], tp.pk[0]
            keep = f'SELECT * FROM "{base}"."{k}" WHERE {_h(chr(34) + pk_k + chr(34), 41)} >= 20'
            take = f'SELECT * FROM "{base}"."{prv}" WHERE {_h(chr(34) + pk_p + chr(34), 41)} < 20'
            con.execute(f'CREATE TABLE "{base}_V4"."{k}" AS {keep} UNION ALL {take}')
            moved.add(k)
    for t in s.tables.values():
        if t.name not in moved:
            cols = ", ".join(f'"{c.name}"' for c in t.columns)
            con.execute(f'CREATE VIEW "{base}_V4"."{t.name}" AS SELECT {cols} FROM "{base}"."{t.name}"')
    # V2's window functions are recomputed by every query against the view: materialise
    # it (same rows, so gold signatures are unchanged)
    for t in s.tables.values():
        if t.relation_fks:
            v2 = f'"{base}_V2"."{t.name}"'
            con.execute(f'CREATE TABLE "{base}_V2"."{t.name}__m" AS SELECT * FROM {v2}')
            con.execute(f"DROP VIEW {v2}")
            con.execute(f'ALTER TABLE "{base}_V2"."{t.name}__m" RENAME TO "{t.name}"')
    con.close()
    print(f"built variants {VARIANTS}; V2 materialised; V4 reclassified {len(moved)} subclass tables")


if __name__ == "__main__":
    build()
