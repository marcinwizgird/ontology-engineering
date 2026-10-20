"""Deterministic translation of FIBEN gold SQL into SPARQL over the FIBEN ontology.

FIBEN's gold SQL is ontology-shaped (one table per class, joins on property columns),
so it can be lifted mechanically; the result is verified by compiling it through Ontop
and comparing its rows with the gold rows. This yields (a) a gold SPARQL set and (b) the
**compiler ceiling**: the share of FIBEN questions the VKG route can express.

Translation rules:

* every table alias is a variable typed with the table's class;
* a join between two *entity* columns (primary or foreign keys) unifies the two terms:
  ``fk = pk`` becomes the triple ``?a :prop ?b``; ``pk = pk`` (subclass tables) makes the
  two aliases one individual; a join between data columns shares the value variable;
* data columns become ``?alias :prop ?alias_prop`` — OPTIONAL when only projected (SQL
  keeps the row when the column is NULL), required when filtered, grouped or aggregated;
* ``IN``/``NOT IN`` subqueries become ``FILTER [NOT] EXISTS``; when the subquery
  aggregates, a ``SELECT DISTINCT`` sub-select joined (or ``MINUS``-ed) on the key;
* scalar subqueries become aggregate sub-selects grouped by their correlation
  variables and joined on them;
* typed literals come from the column's SQL type.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from . import gold, schema, vkg_build

PRE = "fiben:"


class Unsupported(Exception):
    pass


@dataclass
class Alias:
    table: schema.Table
    var: str


def _sv(name: str) -> str:
    return "?" + re.sub(r"[^A-Za-z0-9_]", "_", name).lower()


_AGG = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


class Ctx:
    def __init__(self, s: schema.Schema, outer: "Ctx | None" = None, prefix: str = ""):
        self.s, self.outer, self.prefix = s, outer, prefix
        self.aliases: dict[str, Alias] = {}
        self.parent: dict[str, str] = {}
        self.required: dict[tuple, None] = {}
        self.optional: dict[tuple, None] = {}
        self.types: list[tuple[str, str]] = []
        self.filters: list[str] = []
        self.blocks: list[str] = []
        self.colvars: dict[tuple[str, str], str] = {}
        self.xsd: dict[str, str] = {}
        self.extra_group: list[str] = []
        self.correlations: list[tuple[str, str]] = []   # (inner var, outer var)
        self._n = itertools.count()

    # ----- variables ---------------------------------------------------------
    def find(self, v: str) -> str:
        """Local union-find. Variables of an outer query pass through unchanged here and
        are renamed when the outer body is rendered (it substitutes inside sub-blocks)."""
        p = self.parent.get(v, v)
        if p == v:
            return v
        r = self.find(p)
        self.parent[v] = r
        return r

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb
            self.parent.setdefault(rb, rb)

    def fresh(self, base: str) -> str:
        return f"?{self.prefix}{base}{next(self._n)}"

    # ----- columns -----------------------------------------------------------
    def lookup(self, alias: str) -> tuple["Ctx", Alias]:
        c: Ctx | None = self
        while c is not None:
            if alias.lower() in c.aliases:
                return c, c.aliases[alias.lower()]
            c = c.outer
        raise Unsupported(f"unknown alias {alias}")

    def term(self, col: exp.Column, required: bool = True) -> str:
        if not col.table:
            target = getattr(self, "select_aliases", {}).get(col.name.lower())
            if target is not None:              # ORDER BY / HAVING on a SELECT alias
                return self.translator.expr(self, target)
            raise Unsupported(f"unqualified column {col.sql()}")
        owner, a = self.lookup(col.table)
        name = col.name.upper()
        t = a.table
        if name in t.pk:
            return a.var
        fk = next((f for f in t.relation_fks if f.column == name), None)
        key = (col.table.lower(), name)
        var = owner.colvars.get(key)
        if var is None:
            prop = vkg_build.prop_name(name)
            var = f"{a.var}_{prop.lower()}"
            owner.colvars[key] = var
            if fk is None:
                c = t.column(name)
                owner.xsd[var] = c.xsd
        triple = (a.var, PRE + vkg_build.prop_name(name), var)
        if required:
            owner.required[triple] = None
            owner.optional.pop(triple, None)
        elif triple not in owner.required:
            owner.optional[triple] = None
        return var

    def is_entity(self, col: exp.Column) -> bool:
        _, a = self.lookup(col.table)
        n = col.name.upper()
        return n in a.table.pk or any(f.column == n for f in a.table.relation_fks)

    def is_local(self, col: exp.Column) -> bool:
        return col.table and col.table.lower() in self.aliases


# --------------------------------------------------------------------------- #
def _lit(value: exp.Literal, xsd: str | None) -> str:
    v = value.this
    if xsd in ("integer",):
        return str(int(float(v)))
    if xsd in ("double", "decimal"):
        return repr(float(v))
    if xsd == "dateTime":
        m = re.match(r"(\d{4}-\d{2}-\d{2})[ T]?(\d{2}:\d{2}:\d{2})?", str(v))
        if not m:
            raise Unsupported(f"bad timestamp {v}")
        return f'"{m.group(1)}T{m.group(2) or "00:00:00"}"^^xsd:dateTime'
    if xsd == "date":
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return f'"{m.group(1)}"^^xsd:date'
    if not value.is_string:
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _strip(e):
    while isinstance(e, exp.Paren):
        e = e.this
    return e


class Translator:
    def __init__(self):
        self.s = schema.load()

    # ----- expressions ------------------------------------------------------
    def expr(self, ctx: Ctx, e, xsd_hint: str | None = None, required: bool = True) -> str:
        e = _strip(e)
        if isinstance(e, exp.Column):
            return ctx.term(e, required)
        if isinstance(e, exp.Literal):
            return _lit(e, xsd_hint)
        if isinstance(e, exp.Neg):
            return "-" + self.expr(ctx, e.this, xsd_hint)
        if isinstance(e, exp.Boolean):
            return "true" if e.this else "false"
        if isinstance(e, exp.Null):
            raise Unsupported("NULL literal")
        if isinstance(e, exp.Star):
            return "*"
        if isinstance(e, _AGG):
            name = {exp.Count: "COUNT", exp.Sum: "SUM", exp.Avg: "AVG", exp.Max: "MAX",
                    exp.Min: "MIN"}[type(e)]
            inner = e.this
            distinct = isinstance(inner, exp.Distinct)
            if distinct:
                inner = inner.expressions[0]
            arg = "*" if isinstance(inner, exp.Star) or inner is None else self.expr(ctx, inner)
            return f"{name}({'DISTINCT ' if distinct else ''}{arg})"
        if isinstance(e, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
            op = {exp.Add: "+", exp.Sub: "-", exp.Mul: "*", exp.Div: "/"}[type(e)]
            hint = self._hint(ctx, e.this) or self._hint(ctx, e.expression)
            return f"({self.expr(ctx, e.this, hint)} {op} {self.expr(ctx, e.expression, hint)})"
        if isinstance(e, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
            return self.comparison(ctx, e)
        if isinstance(e, exp.And):
            return f"({self.expr(ctx, e.this)} && {self.expr(ctx, e.expression)})"
        if isinstance(e, exp.Or):
            return f"({self.expr(ctx, e.this)} || {self.expr(ctx, e.expression)})"
        if isinstance(e, exp.Not):
            return f"!({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Like):
            pat = e.expression.this
            rx = "^" + re.escape(pat).replace("%", ".*").replace("_", ".") + "$"
            rx = rx.replace("\\%", ".*").replace("\\_", ".")
            return f'REGEX(STR({self.expr(ctx, e.this)}), "{rx}", "i")'
        if isinstance(e, exp.Between):
            h = self._hint(ctx, e.this)
            x = self.expr(ctx, e.this)
            return f"({x} >= {self.expr(ctx, e.args['low'], h)} && {x} <= {self.expr(ctx, e.args['high'], h)})"
        if isinstance(e, exp.In) and not e.args.get("query"):
            h = self._hint(ctx, e.this)
            return f"({self.expr(ctx, e.this)} IN ({', '.join(self.expr(ctx, v, h) for v in e.expressions)}))"
        if isinstance(e, exp.Year):
            return f"YEAR({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Month):
            return f"MONTH({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Day):
            return f"DAY({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Upper):
            return f"UCASE({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Lower):
            return f"LCASE({self.expr(ctx, e.this)})"
        if isinstance(e, exp.Cast):
            return self.expr(ctx, e.this, xsd_hint)
        if isinstance(e, exp.Is):
            x = self.expr(ctx, e.this, required=False)
            return f"!BOUND({x})" if isinstance(e.expression, exp.Null) else f"BOUND({x})"
        if isinstance(e, exp.Subquery):
            return self.scalar_subquery(ctx, e)
        raise Unsupported(f"expression {type(e).__name__}: {e.sql()[:80]}")

    def _hint(self, ctx: Ctx, e) -> str | None:
        e = _strip(e)
        if isinstance(e, exp.Column):
            try:
                owner, a = ctx.lookup(e.table)
            except Unsupported:
                return None
            n = e.name.upper()
            if n in a.table.pk or any(f.column == n for f in a.table.relation_fks):
                return None
            return a.table.column(n).xsd
        if isinstance(e, (exp.Sum, exp.Avg, exp.Max, exp.Min)):
            return self._hint(ctx, e.this) or "double"
        if isinstance(e, exp.Count):
            return "integer"
        return None

    def comparison(self, ctx: Ctx, e) -> str:
        op = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<",
              exp.LTE: "<="}[type(e)]
        h = self._hint(ctx, e.this) or self._hint(ctx, e.expression)
        return f"({self.expr(ctx, e.this, h)} {op} {self.expr(ctx, e.expression, h)})"

    # ----- subqueries -------------------------------------------------------
    def scalar_subquery(self, ctx: Ctx, sq: exp.Subquery) -> str:
        """Aggregate (or first-value) sub-select grouped by its correlation variables."""
        inner_sel = sq.this
        sub = Ctx(self.s, outer=ctx, prefix="s%d_" % next(ctx._n))
        sub.scalar_mode = True
        self.from_where(sub, inner_sel)
        if len(inner_sel.expressions) != 1:
            raise Unsupported("scalar subquery with several columns")
        val_e = _strip(inner_sel.expressions[0])
        if isinstance(val_e, exp.Alias):
            val_e = val_e.this
        val = self.expr(sub, val_e)
        agg = val if isinstance(val_e, _AGG) else f"SAMPLE({val})"
        out = ctx.fresh("sub")
        keys = []
        for inner_v, outer_v in sub.correlations:
            keys.append((sub.find(inner_v), outer_v))
        proj = " ".join(f"({k} AS {o})" for k, o in keys) + f" ({agg} AS {out})"
        group = (" GROUP BY " + " ".join(k for k, _ in keys)) if keys else ""
        ctx.blocks.append("{ SELECT " + proj + " WHERE { " + self.body(sub) + " }" + group + " }")
        if getattr(ctx, "in_having", False):      # compared after aggregation: must be grouped
            ctx.extra_group.append(out)
        return out

    def in_subquery(self, ctx: Ctx, e: exp.In, negate: bool) -> None:
        q = e.args["query"]
        sel = q.this if isinstance(q, exp.Subquery) else q
        has_agg = bool(sel.args.get("group")) or any(isinstance(_strip(x), _AGG) for x in sel.expressions)
        sub = Ctx(self.s, outer=ctx, prefix="i%d_" % next(ctx._n))
        self.from_where(sub, sel)
        key_e = _strip(sel.expressions[0])
        if isinstance(key_e, exp.Alias):
            key_e = key_e.this
        key = sub.find(self.expr(sub, key_e))
        outer_term = self.expr(ctx, e.this)
        if not has_agg:
            # Ontop needs a variable shared through a triple pattern: unify the inner key
            # with the outer term instead of FILTER(?inner = ?outer)
            if outer_term.startswith("?"):
                sub.parent[key] = outer_term
                body = self.body(sub)
                cond = ""
            else:
                body, cond = self.body(sub), f" FILTER({key} = {outer_term})"
            kw = "NOT EXISTS" if negate else "EXISTS"
            ctx.filters.append(f"{kw} {{ {body}{cond} }}")
            return
        if sub.correlations:
            raise Unsupported("correlated aggregate IN-subquery")
        group = self.group_having(sub, sel)
        inner = f"SELECT DISTINCT ({key} AS {outer_term}) WHERE {{ {self.body(sub)} }}{group}"
        if negate:
            ctx.blocks.append(f"MINUS {{ {inner} }}")
        else:
            ctx.blocks.append(f"{{ {inner} }}")

    def exists(self, ctx: Ctx, e: exp.Exists, negate: bool) -> None:
        sub = Ctx(self.s, outer=ctx, prefix="e%d_" % next(ctx._n))
        self.from_where(sub, e.this)
        kw = "NOT EXISTS" if negate else "EXISTS"
        ctx.filters.append(f"{kw} {{ {self.body(sub)} }}")

    # ----- clauses ----------------------------------------------------------
    def add_table(self, ctx: Ctx, t: exp.Table) -> None:
        name = t.name.upper()
        if name not in self.s.tables:
            raise Unsupported(f"unknown table {name}")
        alias = t.alias_or_name
        var = _sv(ctx.prefix + alias)
        ctx.aliases[alias.lower()] = Alias(self.s.tables[name], var)
        ctx.parent.setdefault(var, var)
        ctx.types.append((var, PRE + vkg_build.class_name(name)))

    def condition(self, ctx: Ctx, cond) -> None:
        cond = _strip(cond)
        if isinstance(cond, exp.And):
            self.condition(ctx, cond.this)
            self.condition(ctx, cond.expression)
            return
        if isinstance(cond, exp.EQ):
            l, r = _strip(cond.this), _strip(cond.expression)
            if isinstance(l, exp.Column) and isinstance(r, exp.Column):
                ll, rl = ctx.is_local(l), ctx.is_local(r)
                if ll and rl:
                    if ctx.is_entity(l) and ctx.is_entity(r):
                        ctx.union(ctx.term(l), ctx.term(r))
                        return
                    if not ctx.is_entity(l) and not ctx.is_entity(r):
                        ctx.union(ctx.term(l), ctx.term(r))
                        return
                elif ll != rl:                    # correlation with the outer query
                    inner, outer = (l, r) if ll else (r, l)
                    iv = ctx.term(inner)
                    ov = ctx.outer.term(outer) if ctx.outer else None
                    if ov is None:
                        raise Unsupported("correlation without outer query")
                    if getattr(ctx, "scalar_mode", False):
                        ctx.correlations.append((iv, ov))
                    else:                         # EXISTS: share the outer variable
                        ctx.parent[ctx.find(iv)] = ov
                    return
        if isinstance(cond, exp.In) and cond.args.get("query"):
            self.in_subquery(ctx, cond, negate=False)
            return
        if isinstance(cond, exp.Not) and isinstance(_strip(cond.this), exp.In) and \
                _strip(cond.this).args.get("query"):
            self.in_subquery(ctx, _strip(cond.this), negate=True)
            return
        if isinstance(cond, exp.Exists):
            self.exists(ctx, cond, False)
            return
        if isinstance(cond, exp.Not) and isinstance(_strip(cond.this), exp.Exists):
            self.exists(ctx, _strip(cond.this), True)
            return
        ctx.filters.append(self.expr(ctx, cond))

    def from_where(self, ctx: Ctx, sel: exp.Select) -> None:
        frm = sel.args.get("from_") or sel.args.get("from")
        if frm is None:
            raise Unsupported("no FROM")
        tables = [frm.this] + [j.this for j in sel.args.get("joins") or []]
        for t in tables:
            if not isinstance(t, exp.Table):
                raise Unsupported(f"FROM item {type(t).__name__}")
            self.add_table(ctx, t)
        for j in sel.args.get("joins") or []:
            if j.args.get("side"):
                raise Unsupported(f"{j.args['side']} JOIN")
            if j.args.get("on") is not None:
                self.condition(ctx, j.args["on"])
        where = sel.args.get("where")
        if where is not None:
            self.condition(ctx, where.this)

    def group_having(self, ctx: Ctx, sel: exp.Select, proj_aggs: dict | None = None) -> str:
        out = ""
        g = sel.args.get("group")
        keys = [self.expr(ctx, x) for x in g.expressions] if g else []
        having = sel.args.get("having")
        ctx.in_having = True
        hav = self.expr(ctx, having.this) if having is not None else ""
        ctx.in_having = False
        keys = [ctx.find(k) for k in keys] + ctx.extra_group
        if keys:
            out += " GROUP BY " + " ".join(dict.fromkeys(keys))
        if hav:
            out += f" HAVING ({hav})"
        return out

    def body(self, ctx: Ctx) -> str:
        sub = lambda s: re.sub(r"\?[A-Za-z0-9_]+", lambda m: ctx.find(m.group(0)), s)  # noqa: E731
        parts = [f"{ctx.find(v)} a {c} ." for v, c in ctx.types]
        parts += [f"{ctx.find(s)} {p} {ctx.find(o)} ." for s, p, o in ctx.required]
        parts += [f"OPTIONAL {{ {ctx.find(s)} {p} {ctx.find(o)} }}" for s, p, o in ctx.optional]
        parts += [sub(b) for b in ctx.blocks]
        parts += [f"FILTER({sub(f)})" for f in ctx.filters]
        return " ".join(parts)

    # ----- top level --------------------------------------------------------
    def select(self, sel: exp.Select, union_cols: list[str] | None = None) -> str:
        ctx = Ctx(self.s)
        ctx.translator = self
        ctx.select_aliases = {item.alias.lower(): item.this for item in sel.expressions
                              if isinstance(item, exp.Alias)}
        self.from_where(ctx, sel)
        projections, aggregated = [], False
        for i, item in enumerate(sel.expressions):
            e = item.this if isinstance(item, exp.Alias) else item
            e = _strip(e)
            name = union_cols[i] if union_cols else None
            if isinstance(e, exp.Column) and union_cols is None:
                v = ctx.term(e, required=False)
                projections.append(("var", v))
            else:
                if isinstance(e, _AGG) or e.find(*_AGG):
                    aggregated = True
                out = name or f"?agg{i}"
                projections.append(("expr", f"({self.expr(ctx, e, required=not isinstance(e, exp.Column))} AS {out})"))
        tail = self.group_having(ctx, sel)
        if aggregated and not sel.args.get("group") and ctx.extra_group:
            tail = tail.replace(" GROUP BY ", " GROUP BY ", 1)
        order = sel.args.get("order")
        if order is not None:
            keys = []
            for o in order.expressions:
                x = self.expr(ctx, o.this)
                keys.append(f"DESC({x})" if o.args.get("desc") else f"ASC({x})")
            tail += " ORDER BY " + " ".join(keys)
        lim = sel.args.get("limit")
        if lim is not None:
            n = lim.args.get("count") or lim.expression
            tail += f" LIMIT {int(n.this)}"
        seen: dict[str, int] = {}
        cols = []
        for kind, p in projections:
            if kind == "var":
                v = ctx.find(p)
                if v in seen:
                    v = f"({v} AS ?dup{len(cols)})"
                seen[v] = 1
                cols.append(v)
            else:
                cols.append(re.sub(r"\?[A-Za-z0-9_]+", lambda m: ctx.find(m.group(0)), p))
        distinct = "DISTINCT " if sel.args.get("distinct") else ""
        return f"SELECT {distinct}{' '.join(cols)} WHERE {{ {self.body(ctx)} }}{tail}"

    def translate(self, sql: str) -> str:
        tree = sqlglot.parse_one(sql, read="postgres")
        if isinstance(tree, exp.Union):
            branches, node = [], tree
            while isinstance(node, exp.Union):
                branches.append(node.expression)
                node = node.this
            branches.append(node)
            branches.reverse()
            n = len(branches[0].expressions)
            cols = [f"?c{i}" for i in range(n)]
            parts = [f"{{ {self.select(b, cols)} }}" for b in branches]
            distinct = "DISTINCT " if tree.args.get("distinct", True) else ""
            return f"SELECT {distinct}{' '.join(cols)} WHERE {{ {' UNION '.join(parts)} }}"
        if not isinstance(tree, exp.Select):
            raise Unsupported(type(tree).__name__)
        return self.select(tree)


def prepare_gold_sql(sql: str) -> str:
    """The same minimal repairs as the gold execution (display cap, defects)."""
    s = gold.strip_display_cap(sql)
    if s.count("'") % 2:
        s += "'"
    if s.count("(") > s.count(")"):
        s += ")" * (s.count("(") - s.count(")"))
    return s


def to_sparql(sql: str) -> str:
    from .vkg import PREFIXES
    return PREFIXES + Translator().translate(prepare_gold_sql(sql))
