"""Targeted instance synthesis: a *witness* database instance (variant V5).

Random perturbation (V1–V4) leaves two holes the mutation test exposed: gold queries with
empty answers (any mutant also returns nothing) and data on which a wrong query happens
to coincide with the right one. Following the idea of distilled test suites (Zhong et
al. 2020) and query-aware test-data generation, this module reads each gold query's
structure and synthesises rows:

* **witness rows** — a chain of rows along the query's joins whose columns satisfy every
  filter, so the gold answer is non-empty;
* **aggregate spread** — at least two witness chains in the same group with different
  measure values (10 and 30), so SUM / AVG / MIN / MAX / COUNT disagree; enough chains to
  satisfy ``HAVING COUNT(...) > n``;
* **near misses** — one extra chain per filter that violates exactly that filter, so
  dropping or flipping it changes the answer;
* **superclass near miss** — for an alias on a subclass table, a chain with the parent row
  but without the subclass row, so replacing the class by its parent changes the answer;
* **nested queries** — the subquery gets its own witness rows; correlated columns copy the
  value of the *first* outer witness only, so semi-joins, anti-joins and correlated
  aggregates discriminate.

All rows go to schema ``FIBEN_W``; ``FIBEN_V5`` is the base data plus the witness rows
(views ``UNION ALL``). Gold answers on V5 are recomputed from the gold SQL — the gold SQL
defines correctness, synthetic rows only make it observable.

    python -m nl2q.witness          # builds FIBEN_W / FIBEN_V5, gold on V5, report
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

import duckdb
import sqlglot
from sqlglot import exp

from . import gold, paths, schema, sql2sparql

ID_BASE = 800_000_000_000_000
NUM_FOR = {"BIGINT", "INTEGER", "DOUBLE"}


def _strip(e):
    while isinstance(e, exp.Paren):
        e = e.this
    return e


@dataclass
class Scope:
    aliases: dict[str, str]                                   # alias(lower) -> table
    joins: list[tuple[tuple[str, str], tuple[str, str]]]      # ((alias, col), (alias, col))
    filters: list[tuple[str, str, str, object]]               # (alias, col, op, value)
    likes: list[tuple[str, str, str]]
    measures: list[tuple[str, str, str]]                      # (agg, alias, col)
    having: list[tuple[str, str, str, str, object]]           # (agg, alias, col, op, value)
    group: list[tuple[str, str]]
    subs: list[tuple["Scope", list[tuple[tuple[str, str], tuple[str, str]]], str]] = field(default_factory=list)
    # (sub-scope, correlations (outer col, inner col), kind: in | notin | scalar | exists)


class Builder:
    def __init__(self, s: schema.Schema):
        self.s = s
        self.rows: dict[str, list[dict]] = defaultdict(list)
        self.next_id = ID_BASE
        self.samples: dict[tuple[str, str], object] = {}

    def fresh(self) -> int:
        self.next_id += 1
        return self.next_id

    # ----- parsing --------------------------------------------------------------
    def scope(self, sel: exp.Select, outer: Scope | None = None) -> Scope:
        sc = Scope({}, [], [], [], [], [], [])
        frm = sel.args.get("from_") or sel.args.get("from")
        for t in [frm.this] + [j.this for j in sel.args.get("joins") or []]:
            if isinstance(t, exp.Table) and t.name.upper() in self.s.tables:
                sc.aliases[t.alias_or_name.lower()] = t.name.upper()
        conds = []
        for j in sel.args.get("joins") or []:
            if j.args.get("on") is not None:
                conds.append(j.args["on"])
        if sel.args.get("where") is not None:
            conds.append(sel.args["where"].this)
        for c in conds:
            self._cond(sc, c, outer)
        for item in sel.expressions:
            e = _strip(item.this if isinstance(item, exp.Alias) else item)
            if isinstance(e, (exp.Sum, exp.Avg, exp.Max, exp.Min, exp.Count)) and isinstance(_strip(e.this), exp.Column):
                col = _strip(e.this)
                if col.table and col.table.lower() in sc.aliases:
                    sc.measures.append((type(e).__name__.upper(), col.table.lower(), col.name.upper()))
        g = sel.args.get("group")
        if g:
            for x in g.expressions:
                x = _strip(x)
                if isinstance(x, exp.Column) and x.table:
                    sc.group.append((x.table.lower(), x.name.upper()))
        h = sel.args.get("having")
        if h is not None:
            self._having(sc, h.this, outer)
        return sc

    def _col(self, sc: Scope, outer: Scope | None, e) -> tuple[str, str, bool] | None:
        e = _strip(e)
        if isinstance(e, exp.Column) and e.table:
            a = e.table.lower()
            if a in sc.aliases:
                return a, e.name.upper(), True
            if outer is not None and a in outer.aliases:
                return a, e.name.upper(), False
        return None

    def _lit(self, e):
        e = _strip(e)
        if isinstance(e, exp.Neg) and isinstance(_strip(e.this), exp.Literal):
            return -float(_strip(e.this).this)
        if isinstance(e, exp.Literal):
            return e.this if e.is_string else float(e.this)
        return None

    def _cond(self, sc: Scope, c, outer: Scope | None) -> None:
        c = _strip(c)
        if isinstance(c, exp.And):
            self._cond(sc, c.this, outer)
            self._cond(sc, c.expression, outer)
            return
        if isinstance(c, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ)):
            op = {exp.EQ: "=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<=", exp.NEQ: "!="}[type(c)]
            l, r = self._col(sc, outer, c.this), self._col(sc, outer, c.expression)
            if l and r:
                if l[2] and r[2]:
                    sc.joins.append(((l[0], l[1]), (r[0], r[1])))
                elif outer is not None:                       # correlation inner <-> outer
                    inner, out = (l, r) if l[2] else (r, l)
                    sc.joins.append((("^" + out[0], out[1]), (inner[0], inner[1])))
                return
            sub = _strip(c.expression) if isinstance(_strip(c.expression), exp.Subquery) else None
            if l and sub is not None and l[2]:
                inner = self.scope(sub.this, sc)
                sc.subs.append((inner, [], "scalar"))
                return
            v = self._lit(c.expression)
            if l and l[2] and v is not None:
                sc.filters.append((l[0], l[1], op, v))
            elif r and r[2] and self._lit(c.this) is not None:
                flip = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "=": "=", "!=": "!="}[op]
                sc.filters.append((r[0], r[1], flip, self._lit(c.this)))
            return
        if isinstance(c, exp.Between):
            l = self._col(sc, outer, c.this)
            if l and l[2]:
                sc.filters.append((l[0], l[1], ">=", self._lit(c.args["low"])))
                sc.filters.append((l[0], l[1], "<=", self._lit(c.args["high"])))
            return
        if isinstance(c, exp.Like):
            l = self._col(sc, outer, c.this)
            if l and l[2]:
                sc.likes.append((l[0], l[1], str(c.expression.this)))
            return
        neg = isinstance(c, exp.Not)
        inner_c = _strip(c.this) if neg else c
        if isinstance(inner_c, exp.In):
            l = self._col(sc, outer, inner_c.this)
            q = inner_c.args.get("query")
            if q is not None and l and l[2]:
                sel = q.this if isinstance(q, exp.Subquery) else q
                inner = self.scope(sel, sc)
                key = _strip(sel.expressions[0])
                key = _strip(key.this) if isinstance(key, exp.Alias) else key
                k = self._col(inner, None, key)
                corr = [((l[0], l[1]), (k[0], k[1]))] if k else []
                sc.subs.append((inner, corr, "notin" if neg else "in"))
            elif l and l[2] and not neg and inner_c.expressions:
                sc.filters.append((l[0], l[1], "=", self._lit(inner_c.expressions[0])))
            return
        if isinstance(inner_c, exp.Exists):
            sc.subs.append((self.scope(inner_c.this, sc), [], "notexists" if neg else "exists"))

    def _having(self, sc: Scope, h, outer) -> None:
        h = _strip(h)
        if isinstance(h, exp.And):
            self._having(sc, h.this, outer)
            self._having(sc, h.expression, outer)
            return
        if isinstance(h, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ)):
            op = {exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<=", exp.EQ: "="}[type(h)]
            agg = _strip(h.this)
            if isinstance(agg, (exp.Sum, exp.Avg, exp.Max, exp.Min, exp.Count)):
                col = _strip(agg.this)
                v = self._lit(h.expression)
                if isinstance(col, exp.Column) and col.table and col.table.lower() in sc.aliases:
                    if v is not None:
                        sc.having.append((type(agg).__name__.upper(), col.table.lower(), col.name.upper(), op, v))
                    elif isinstance(_strip(h.expression), exp.Subquery):
                        sc.subs.append((self.scope(_strip(h.expression).this, sc), [], "scalar"))

    # ----- values ---------------------------------------------------------------
    def _sample(self, con, table: str, col: str):
        key = (table, col)
        if key not in self.samples:
            r = con.execute(f'SELECT "{col}" FROM "{paths.SCHEMA}"."{table}" WHERE "{col}" IS NOT NULL LIMIT 1').fetchone()
            self.samples[key] = r[0] if r else None
        return self.samples[key]

    def _typed(self, table: str, col: str, v):
        t = self.s.tables[table].column(col).sql_type
        if v is None:
            return None
        if t in ("BIGINT", "INTEGER"):
            return int(float(v))
        if t == "DOUBLE":
            return float(v)
        if t == "TIMESTAMP":
            return v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(str(v)[:19].replace(" ", "T"))
        if t == "DATE":
            return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])
        return str(v)

    def _satisfy(self, table: str, col: str, cons: list[tuple[str, object]], k: int):
        t = self.s.tables[table].column(col).sql_type
        eq = [v for op, v in cons if op == "="]
        if eq:
            return self._typed(table, col, eq[0])
        lo = [self._typed(table, col, v) for op, v in cons if op in (">", ">=")]
        hi = [self._typed(table, col, v) for op, v in cons if op in ("<", "<=")]
        strict_lo = any(op == ">" for op, _ in cons)
        strict_hi = any(op == "<" for op, _ in cons)
        if t in ("TIMESTAMP", "DATE"):
            one = dt.timedelta(days=1)
            a = max(lo) if lo else None
            b = min(hi) if hi else None
            if a is not None and b is not None:
                return a + (b - a) / 2
            if a is not None:
                return a + one * (1 + k)
            if b is not None:
                return b - one * (1 + k)
        if t in NUM_FOR:
            a = max(lo) if lo else None
            b = min(hi) if hi else None
            if a is not None and b is not None:
                return self._typed(table, col, (a + b) / 2)
            if a is not None:
                return self._typed(table, col, a + (1 if strict_lo or True else 0) + 10 * k)
            if b is not None:
                return self._typed(table, col, b - 1 - 10 * k if b > 1 else b / 2)
        neq = [v for op, v in cons if op == "!="]
        if neq:
            return f"W-not-{neq[0]}"
        return None

    def _violate(self, table: str, col: str, op: str, v):
        t = self.s.tables[table].column(col).sql_type
        tv = self._typed(table, col, v)
        if op == "=":
            if t in NUM_FOR:
                return self._typed(table, col, tv + 7)
            if t in ("TIMESTAMP", "DATE"):
                return tv + dt.timedelta(days=400)
            return f"{tv} (near miss)"
        if op in (">", ">="):
            return tv - (dt.timedelta(days=30) if t in ("TIMESTAMP", "DATE") else (abs(tv) + 1 if t in NUM_FOR else 0))
        if op in ("<", "<="):
            return tv + (dt.timedelta(days=30) if t in ("TIMESTAMP", "DATE") else (abs(tv) + 1 if t in NUM_FOR else 0))
        return None

    # ----- generation -----------------------------------------------------------
    def chain(self, con, sc: Scope, tag: str, k: int, *, override: dict | None = None,
              skip_tables: set[str] | None = None, outer_vals: dict | None = None,
              measure_value: float | None = None) -> dict[tuple[str, str], object]:
        """Insert one witness chain for scope *sc*; returns the values used per (alias, col)."""
        override = override or {}
        skip_tables = skip_tables or set()
        # identity groups: aliases joined PK=PK share one individual
        parent: dict[str, str] = {a: a for a in sc.aliases}

        def find(a):
            while parent[a] != a:
                a = parent[a]
            return a
        fkset: dict[tuple[str, str], str] = {}
        eqval: list[tuple[tuple[str, str], tuple[str, str]]] = []
        corr: list[tuple[tuple[str, str], tuple[str, str]]] = []
        for (a1, c1), (a2, c2) in sc.joins:
            if a1.startswith("^"):
                corr.append(((a1[1:], c1), (a2, c2)))
                continue
            t1, t2 = self.s.tables[sc.aliases[a1]], self.s.tables[sc.aliases[a2]]
            pk1, pk2 = c1 in t1.pk, c2 in t2.pk
            if pk1 and pk2:
                parent[find(a1)] = find(a2)
            elif pk2:
                fkset[(a1, c1)] = a2
            elif pk1:
                fkset[(a2, c2)] = a1
            else:
                eqval.append(((a1, c1), (a2, c2)))
        ids = {}
        for a in sc.aliases:
            r = find(a)
            if r not in ids:
                ids[r] = self.fresh()
        vals: dict[tuple[str, str], object] = {}
        cons = defaultdict(list)
        for a, c, op, v in sc.filters:
            cons[(a, c)].append((op, v))
        for agg, a, c, op, v in sc.having:
            if agg in ("SUM", "AVG", "MIN", "MAX"):
                cons[(a, c)].append((op, v))
        for (a, c), v in override.items():
            cons[(a, c)] = [("=", v)]
        for a, table in sc.aliases.items():
            if table in skip_tables:
                continue
            t = self.s.tables[table]
            row = {}
            for col in t.columns:
                key = (a, col.name)
                if col.name in t.pk:
                    row[col.name] = ids[find(a)]
                elif key in fkset:
                    row[col.name] = ids[find(fkset[key])]
                elif key in cons:
                    row[col.name] = self._satisfy(table, col.name, cons[key], k)
                elif any(f.column == col.name for f in t.relation_fks):
                    row[col.name] = self._sample(con, table, col.name)
                elif measure_value is not None and (a, col.name) in {(m[1], m[2]) for m in sc.measures}:
                    row[col.name] = self._typed(table, col.name, measure_value)
                elif col.sql_type in ("VARCHAR", "CHAR"):
                    row[col.name] = f"W{tag}-{k} {col.name.lower()}"
                else:
                    row[col.name] = self._sample(con, table, col.name)
                vals[key] = row[col.name]
            self.rows[table].append(row)
        # data = data joins: copy values
        for (a1, c1), (a2, c2) in eqval:
            v = vals.get((a1, c1))
            for r in self.rows[sc.aliases[a2]][-1:]:
                if c2 in r:
                    r[c2] = v
            vals[(a2, c2)] = v
        # correlations with the outer witness
        if outer_vals is not None:
            for (oa, oc), (ia, ic) in corr:
                v = outer_vals.get((oa, oc))
                for r in reversed(self.rows[sc.aliases[ia]]):
                    if ic in r and r is not None:
                        r[ic] = v
                        break
                vals[(ia, ic)] = v
        # LIKE patterns
        for a, c, pat in sc.likes:
            v = pat.replace("%", "x").replace("_", "y")
            for r in reversed(self.rows[sc.aliases[a]]):
                if c in r:
                    r[c] = v
                    break
            vals[(a, c)] = v
        return vals

    def for_query(self, con, sql: str, tag: str) -> int:
        tree = sqlglot.parse_one(sql, read="postgres")
        selects = [tree] if isinstance(tree, exp.Select) else [
            b for b in tree.find_all(exp.Select) if b.parent is None or isinstance(b.parent, exp.Union)]
        before = sum(map(len, self.rows.values()))
        for sel in selects:
            if not isinstance(sel, exp.Select):
                continue
            sc = self.scope(sel)
            if not sc.aliases:
                continue
            n_chains = 2
            for agg, a, c, op, v in sc.having:
                if agg == "COUNT" and op in (">", ">="):
                    n_chains = max(n_chains, min(20, int(v) + 2))
            group_override = {}
            first = None
            for k in range(n_chains):
                vals = self.chain(con, sc, tag, k, override=group_override,
                                  measure_value=10.0 + 20.0 * k if sc.measures else None)
                if k == 0:
                    first = vals
                    group_override = {g: vals.get(g) for g in sc.group if vals.get(g) is not None}
            # near misses: one filter violated each
            for i, (a, c, op, v) in enumerate(sc.filters):
                bad = self._violate(sc.aliases[a], c, op, v)
                if bad is not None:
                    self.chain(con, sc, f"{tag}n{i}", 0, override={(a, c): bad})
            # superclass near miss: drop the subclass row of a subclass alias — only when no
            # declared foreign key references that subclass table (Ontop trusts declared
            # FKs and eliminates joins; a dangling reference would make the instance invalid)
            referenced = {f.ref_table for (x, _), (y, _) in sc.joins if not x.startswith("^")
                          for f in self.s.tables[sc.aliases.get(x, sc.aliases.get(y))].relation_fks}
            referenced |= {f.ref_table for a2 in sc.aliases.values() for f in self.s.tables[a2].relation_fks}
            # a subclass row's PK is itself an FK to its parent row: parents are referenced too
            referenced |= {self.s.tables[a2].parent_fk.ref_table for a2 in sc.aliases.values()
                           if self.s.tables[a2].parent_fk is not None}
            for a, table in sc.aliases.items():
                if self.s.tables[table].parent_fk is not None and table not in referenced:
                    self.chain(con, sc, f"{tag}s", 0, skip_tables={table})
                    break
            # nested scopes: witness for the inner query, correlated to the first outer chain
            for inner, corr, kind in sc.subs:
                for (oa, oc), (ia, ic) in corr:
                    inner.joins.append((("^" + oa, oc), (ia, ic)))
                self.chain(con, inner, f"{tag}i", 0, outer_vals=first,
                           measure_value=5.0 if inner.measures else None)
        return sum(map(len, self.rows.values())) - before


def build(db_path=paths.DB) -> dict:
    s = schema.load()
    b = Builder(s)
    con = duckdb.connect(str(db_path))
    per_query = {}
    seen = set()
    for q in gold.questions():
        if q.sql_id in seen:
            continue
        seen.add(q.sql_id)
        try:
            per_query[q.sql_id] = b.for_query(con, sql2sparql.prepare_gold_sql(q.sql), str(q.sql_id))
        except Exception as exc:  # noqa: BLE001
            per_query[q.sql_id] = f"error: {type(exc).__name__}: {str(exc)[:120]}"
    W, V5 = f"{paths.SCHEMA}_W", f"{paths.SCHEMA}_V5"
    for sch in (W, V5):
        con.execute(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE')
        con.execute(f'CREATE SCHEMA "{sch}"')
    total = 0
    for t in s.tables.values():
        cols = ", ".join(f'"{c.name}" {c.duck_type}' for c in t.columns)
        con.execute(f'CREATE TABLE "{W}"."{t.name}" ({cols})')
        rows = b.rows.get(t.name, [])
        if rows:
            names = [c.name for c in t.columns]
            ph = ", ".join("?" for _ in names)
            con.executemany(f'INSERT INTO "{W}"."{t.name}" VALUES ({ph})',
                            [[r.get(n) for n in names] for r in rows])
            total += len(rows)
        cl = ", ".join(f'"{c.name}"' for c in t.columns)
        # materialised (not a view): heavy nested queries over UNION ALL views time out
        con.execute(f'CREATE TABLE "{V5}"."{t.name}" AS SELECT {cl} FROM "{paths.SCHEMA}"."{t.name}" '
                    f'UNION ALL SELECT {cl} FROM "{W}"."{t.name}"')
    con.close()
    errors = {k: v for k, v in per_query.items() if isinstance(v, str)}
    return {"witness_rows": total, "queries": len(per_query), "errors": len(errors),
            "error_sample": list(errors.items())[:5]}


def gold_on_v5() -> dict:
    """Gold signatures on V5, merged into gold_variants.json; how many become non-empty."""
    from .compare import signature
    from .vkg import retarget
    from .load_fiben import connect
    con = connect()
    sch = f"{paths.SCHEMA}_V5"
    con.execute(f"SET search_path = '{sch}'")
    base = gold.load_results()
    res, now_nonempty, still_empty = {}, 0, 0
    for sid, g in base.items():
        try:
            cur = con.execute(retarget(g.duck_sql, sch))
            rows = cur.fetchall()
            res[sid] = signature(rows, len(cur.description)).to_json()
            if g.row_count == 0:
                if rows:
                    now_nonempty += 1
                else:
                    still_empty += 1
        except Exception as exc:  # noqa: BLE001
            res[sid] = {"error": str(exc)[:200]}
    f = paths.GOLD_DIR / "gold_variants.json"
    allv = json.loads(f.read_text(encoding="utf-8"))
    allv["V5"] = res
    f.write_text(json.dumps(allv), encoding="utf-8")
    empty_v5 = sum(1 for r in res.values() if "error" not in r and r["count"] == 0)
    return {"empty_gold_base": sum(1 for g in base.values() if g.row_count == 0),
            "made_nonempty_by_witness": now_nonempty, "still_empty": still_empty,
            "empty_on_v5": empty_v5, "errors": sum("error" in r for r in res.values())}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str))
    print(json.dumps(gold_on_v5(), indent=1))
