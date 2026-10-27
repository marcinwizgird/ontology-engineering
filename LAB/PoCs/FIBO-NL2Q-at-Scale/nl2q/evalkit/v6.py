"""V6: the taxonomic counterfactual witness instance (specification §4.2).

v1's mutation test caught a superclass swap (``?x a fiben:ListedSecurity`` ->
``?x a fiben:Security``) only 9 times in 218: every Security in FIBEN is a ListedSecurity,
so the two queries coincide on every instance V1-V5. V6 adds, for each subclass edge
``sub ⊑ sup`` a gold query uses, **counterfactual individuals**: clones of ``sub``
individuals that exist in ``sup`` and its ancestors but **not** in ``sub``. A query typed
``sup`` now sees them and a query typed ``sub`` does not.

Validity comes first: Ontop trusts declared foreign keys, so V6 must not create a
dangling reference.

* The clone keeps the source's attribute values and outgoing references, which point to
  existing rows.
* References *to* the clone are mirrored only through foreign keys whose target table is
  ``sup`` or one of its ancestors, so the target exists. The referencing individual is
  cloned with a fresh key across its whole class chain.
* A foreign key that targets ``sub`` itself (``HOLDING.REFERSTO -> LISTEDSECURITY``) is
  never mirrored. On every valid instance it forces the referenced individual to be a
  ``sub``, so a query that reaches the variable through it cannot distinguish ``sub`` from
  ``sup``. ``equivalent_under_constraints`` reports such swaps; they are not detection
  failures.

Sources are the witness rows of ``sub`` (FIBEN_W, which satisfy the gold filters), then a
deterministic sample of base rows. V6 = V5 + the counterfactual rows: affected tables are
materialized, the rest are views onto V5.

    python -m nl2q.evalkit.v6        # builds FIBEN_CF / FIBEN_V6 and gold on V6
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import duckdb

from .. import gold, paths, schema, vkg_build

ID_BASE = 900_000_000_000_000
SOURCES_PER_EDGE = 6
REFS_PER_SOURCE = 3
CF, V5, V6 = f"{paths.SCHEMA}_CF", f"{paths.SCHEMA}_V5", f"{paths.SCHEMA}_V6"


class Hierarchy:
    def __init__(self, s: schema.Schema):
        self.s = s
        self.parent = dict(s.subclass_edges)
        self.children: dict[str, list[str]] = defaultdict(list)
        for c, p in s.subclass_edges:
            self.children[p].append(c)
        self.table_of = {vkg_build.class_name(t): t for t in s.tables}

    def ancestors(self, t: str) -> list[str]:
        out = []
        while t in self.parent:
            t = self.parent[t]
            out.append(t)
        return out

    def subtree(self, t: str) -> set[str]:
        out, todo = {t}, [t]
        while todo:
            for c in self.children.get(todo.pop(), []):
                out.add(c)
                todo.append(c)
        return out

    def root(self, t: str) -> str:
        a = self.ancestors(t)
        return a[-1] if a else t


def gold_subclass_edges(h: Hierarchy) -> list[tuple[str, str]]:
    """(sub table, sup table) for every class an accepted gold query types that has a parent."""
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    used = {c for r in rows if r.get("strict") for c in re.findall(r"a fiben:(\w+)", r["sparql"])}
    out = set()
    for c in used:
        t = h.table_of.get(c)
        if t and t in h.parent:
            out.add((t, h.parent[t]))
    return sorted(out)


class Builder:
    def __init__(self, con, h: Hierarchy):
        self.con, self.h = con, h
        self.rows: dict[str, list[dict]] = defaultdict(list)
        self.next_id = ID_BASE
        self.report: dict[str, dict] = {}

    def _fresh(self) -> int:
        self.next_id += 1
        return self.next_id

    def _rows(self, table: str, keys: list) -> dict:
        """key -> row of a V5 table, for many keys in one query."""
        if not keys:
            return {}
        pk = self.h.s.tables[table].pk[0]
        cur = self.con.execute(f'SELECT * FROM "{V5}"."{table}" WHERE "{pk}" IN '
                               f'(SELECT unnest(?::BIGINT[]))', [list(keys)])
        cols = [d[0] for d in cur.description]
        return {r[cols.index(pk)]: dict(zip(cols, r)) for r in cur.fetchall()}

    def _clone(self, tables: list[str], mapping: dict, overrides: dict | None = None) -> set:
        """Copy the rows of individuals ``mapping`` (old key -> new key) in ``tables``;
        ``overrides[(table, old key)]`` replaces columns. Returns the old keys found."""
        found = set()
        for table in tables:
            pk = self.h.s.tables[table].pk[0]
            for old, r in self._rows(table, list(mapping)).items():
                r[pk] = mapping[old]
                r.update((overrides or {}).get((table, old), {}))
                self.rows[table].append(r)
                found.add(old)
        return found

    def _sources(self, sub: str) -> list:
        pk = self.h.s.tables[sub].pk[0]
        wit = [r[0] for r in self.con.execute(
            f'SELECT DISTINCT "{pk}" FROM "{paths.SCHEMA}_W"."{sub}" ORDER BY 1 LIMIT {SOURCES_PER_EDGE}').fetchall()]
        if len(wit) < SOURCES_PER_EDGE:
            wit += [r[0] for r in self.con.execute(
                f'SELECT "{pk}" FROM "{paths.SCHEMA}"."{sub}" ORDER BY hash("{pk}") '
                f'LIMIT {SOURCES_PER_EDGE - len(wit)}').fetchall()]
        return wit

    def edge(self, sub: str, sup: str) -> None:
        chain = [sup, *self.h.ancestors(sup)]                     # where the clone lives
        allowed = set(chain)                                      # FK targets that may point at it
        fks = [f for f in self.h.s.relation_fks if f.ref_table in allowed]
        blocked = [f"{f.table}.{f.column}" for f in self.h.s.relation_fks if f.ref_table in self.h.subtree(sub)]
        clone_of = {src: self._fresh() for src in self._sources(sub)}
        clones = len(self._clone(chain, clone_of))
        mirrored = 0
        for f in fks:
            ref_pk = self.h.s.tables[f.table].pk[0]
            refs = self.con.execute(
                f'SELECT "{ref_pk}", "{f.column}" FROM "{V5}"."{f.table}" '
                f'WHERE "{f.column}" IN (SELECT unnest(?::BIGINT[])) '
                f'QUALIFY row_number() OVER (PARTITION BY "{f.column}" ORDER BY "{ref_pk}") <= {REFS_PER_SOURCE}',
                [list(clone_of)]).fetchall()
            if not refs:
                continue
            # the referencing individual lives in its table, its ancestors and possibly its subclasses
            tables = [*self.h.ancestors(f.table), *self.h.subtree(f.table)]
            mapping = {rid: self._fresh() for rid, _ in refs}
            overrides = {(f.table, rid): {f.column: clone_of[src]} for rid, src in refs}
            mirrored += len(self._clone(tables, mapping, overrides))
        self.report[f"{sub} ⊑ {sup}"] = {"clones": clones, "mirrored_references": mirrored,
                                        "mirrored_through": [f"{f.table}.{f.column}" for f in fks],
                                        "not_mirrorable": blocked}


def build(db_path=paths.DB) -> dict:
    s = schema.load()
    h = Hierarchy(s)
    con = duckdb.connect(str(db_path))
    b = Builder(con, h)
    for sub, sup in gold_subclass_edges(h):
        b.edge(sub, sup)
    for sch in (CF, V6):
        con.execute(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE')
        con.execute(f'CREATE SCHEMA "{sch}"')
    total = 0
    for t in s.tables.values():
        cl = ", ".join(f'"{c.name}"' for c in t.columns)
        rows = b.rows.get(t.name, [])
        if not rows:
            con.execute(f'CREATE VIEW "{V6}"."{t.name}" AS SELECT {cl} FROM "{V5}"."{t.name}"')
            continue
        cols = ", ".join(f'"{c.name}" {c.duck_type}' for c in t.columns)
        con.execute(f'CREATE TABLE "{CF}"."{t.name}" ({cols})')
        names = [c.name for c in t.columns]
        con.executemany(f'INSERT INTO "{CF}"."{t.name}" VALUES ({", ".join("?" for _ in names)})',
                        [[r.get(n) for n in names] for r in rows])
        total += len(rows)
        con.execute(f'CREATE TABLE "{V6}"."{t.name}" AS SELECT {cl} FROM "{V5}"."{t.name}" '
                    f'UNION ALL SELECT {cl} FROM "{CF}"."{t.name}"')
    con.close()
    return {"counterfactual_rows": total, "edges": b.report}


def gold_on_v6() -> dict:
    """Gold signatures on V6, merged into gold_variants.json."""
    from ..compare import signature
    from ..load_fiben import connect
    from ..vkg import retarget
    con = connect()
    con.execute(f"SET search_path = '{V6}'")
    res, changed = {}, 0
    gv = json.loads((paths.GOLD_DIR / "gold_variants.json").read_text(encoding="utf-8"))
    for sid, g in gold.load_results().items():
        if not g.ok:
            continue
        try:
            cur = con.execute(retarget(g.duck_sql, V6))
            res[sid] = signature(cur.fetchall(), len(cur.description)).to_json()
            changed += res[sid] != gv.get("V5", {}).get(str(sid))
        except Exception as exc:  # noqa: BLE001
            res[sid] = {"error": str(exc)[:200]}
    gv["V6"] = res
    (paths.GOLD_DIR / "gold_variants.json").write_text(json.dumps(gv), encoding="utf-8")
    return {"gold_on_v6": len(res), "differs_from_v5": changed,
            "errors": sum("error" in r for r in res.values())}


def equivalent_under_constraints(sparql: str, var_class: str, h: Hierarchy | None = None) -> bool:
    """True when the declared keys force every binding of the variable typed ``var_class``
    into that class, so a swap to its superclass cannot change the answer on any valid
    instance: the variable is the object of a property whose foreign keys all target the
    class's subtree, or the subject of a property only that subtree carries."""
    h = h or Hierarchy(schema.load())
    sub = h.table_of.get(var_class)
    if not sub:
        return False
    tree = h.subtree(sub)
    owners: dict[str, set[str]] = defaultdict(set)      # property -> tables carrying it (subject side)
    targets: dict[str, set[str]] = defaultdict(set)     # object property -> FK target tables
    for t in h.s.tables.values():
        for c in t.columns:
            if c.name not in t.pk:
                owners[vkg_build.prop_name(c.name)].add(t.name)
        for f in t.relation_fks:
            targets[vkg_build.prop_name(f.column)].add(f.ref_table)
    for var in {v for v, c in re.findall(r"(\?\w+)\s+a\s+fiben:(\w+)", sparql) if c == var_class}:
        for s_, p, o in re.findall(r"(\?\w+)\s+fiben:(\w+)\s+(\?\w+)", sparql):
            if o == var and targets.get(p) and targets[p] <= tree:
                return True
            if s_ == var and owners.get(p) and owners[p] <= tree:
                return True
    return False


if __name__ == "__main__":
    from .gate1 import key_integrity
    print(json.dumps(build(), indent=1, ensure_ascii=False))
    bad = key_integrity(V6)
    print("integrity:", "ok" if not bad else bad)
    if bad:
        raise SystemExit("V6 is invalid: gold not computed")
    print(json.dumps(gold_on_v6(), indent=1))
