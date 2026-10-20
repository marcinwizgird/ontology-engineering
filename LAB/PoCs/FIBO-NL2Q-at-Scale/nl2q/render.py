"""Deterministic IR -> SPARQL rendering (only constructs the VKG compiler supports).

The renderer owns everything the planner must not improvise: variable naming, typed
literals (from the property's datatype), OPTIONAL vs required attributes (SQL keeps a row
whose projected column is NULL), automatic GROUP BY, NOT EXISTS sharing variables with
the outer pattern (Ontop requires a common variable), and correlated scalar sub-plans as
grouped sub-selects joined on their correlation variables.
"""

from __future__ import annotations

import re

from . import ir
from .obqc import prop_range
from .vkg import PREFIXES


class RenderError(ValueError):
    pass


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def literal(v: str, xsd: str | None) -> str:
    if xsd in ("integer",):
        return str(int(float(v)))
    if xsd in ("double", "decimal"):
        return repr(float(v))
    if xsd == "dateTime":
        m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2})?))?", v.strip())
        if not m:
            raise RenderError(f"not a date-time: {v!r}")
        t = m.group(2) or "00:00:00"
        t = t if len(t) == 8 else t + ":00"
        return f'"{m.group(1)}T{t}"^^xsd:dateTime'
    if xsd == "date":
        return f'"{v.strip()[:10]}"^^xsd:date'
    return f'"{_esc(v)}"'


class _Scope:
    def __init__(self, prefix: str, outer: "_Scope | None" = None):
        self.prefix, self.outer = prefix, outer
        self.var: dict[str, str] = {}
        self.xsd: dict[str, str | None] = {}
        self.required: list[str] = []
        self.optional: list[str] = []
        self.filters: list[str] = []
        self.blocks: list[str] = []

    def v(self, id_: str) -> str:
        if id_ in self.var:
            return self.var[id_]
        if self.outer is not None:
            return self.outer.v(id_)
        raise RenderError(f"unknown id {id_}")

    def has(self, id_: str) -> bool:
        return id_ in self.var or (self.outer is not None and self.outer.has(id_))

    def body(self) -> str:
        parts = list(dict.fromkeys(self.required))
        parts += [f"OPTIONAL {{ {t} }}" for t in dict.fromkeys(self.optional) if t not in self.required]
        parts += self.blocks + [f"FILTER({f})" for f in self.filters]
        return " ".join(parts)


def _pattern(sc: _Scope, p: ir.Pattern, used: set[str], aliases: dict[str, str] | None = None) -> None:
    aliases = aliases or {}
    for n in p.nodes:
        sc.var[n.id] = aliases.get(n.id) or f"?{sc.prefix}{n.id}"
        sc.required.append(f"{sc.var[n.id]} a fiben:{n.cls} .")
    for l in p.links:
        sc.required.append(f"{sc.v(l.subj)} fiben:{l.prop} {sc.v(l.obj)} .")
    for a in p.attrs:
        sc.var[a.id] = aliases.get(a.id) or f"?{sc.prefix}{a.id}"
        sc.xsd[a.id] = prop_range(a.prop)
        triple = f"{sc.v(a.node)} fiben:{a.prop} {sc.var[a.id]} ."
        (sc.required if a.id in used else sc.optional).append(triple)
    for f in p.filters:
        sc.filters.append(_filter(sc, f))


def _filter(sc: _Scope, f: ir.Filter) -> str:
    x = sc.v(f.target)
    xsd = sc.xsd.get(f.target)
    if f.op in ("=", "!=", "<", "<=", ">", ">="):
        if f.value is None:
            raise RenderError(f"filter {f.target} {f.op} needs a value")
        return f"{x} {f.op} {literal(f.value, xsd)}"
    if f.op == "between":
        return f"{x} >= {literal(f.value, xsd)} && {x} <= {literal(f.value2, xsd)}"
    if f.op == "in":
        return f"{x} IN ({', '.join(literal(v, xsd) for v in f.values)})"
    if f.op == "contains":
        return f'CONTAINS(LCASE(STR({x})), "{_esc((f.value or "").lower())}")'
    if f.op == "starts_with":
        return f'STRSTARTS(LCASE(STR({x})), "{_esc((f.value or "").lower())}")'
    raise RenderError(f"unsupported op {f.op}")


def _used_ids(plan: ir.Plan) -> set[str]:
    used = {f.target for f in plan.filters} | set(plan.group_by) | {h.target for h in plan.having}
    used |= {p.target for p in plan.projections if p.agg}
    used |= {j.outer for n in plan.negations for j in n.joins}
    used |= {j.outer for c in plan.comparisons for j in c.correlate} | {c.left_target for c in plan.comparisons}
    return used


def render(plan: ir.Plan) -> str:
    if not plan.answerable:
        raise RenderError("plan is marked not answerable")
    main = _Scope("")
    used = _used_ids(plan)
    _pattern(main, ir.Pattern(nodes=plan.nodes, links=plan.links, attrs=plan.attrs,
                              filters=plan.filters), used)
    # negations: inner join ids take the outer variable names (shared variables)
    for k, neg in enumerate(plan.negations):
        inner = _Scope(f"x{k}_", outer=main)
        aliases = {j.inner: main.v(j.outer) for j in neg.joins}
        inner_used = {f.target for f in neg.pattern.filters} | set(aliases)
        _pattern(inner, neg.pattern, inner_used, aliases)
        main.filters.append(f"NOT EXISTS {{ {inner.body()} }}")
    # scalar comparisons
    having_extra, group_extra = [], []
    for k, c in enumerate(plan.comparisons):
        sub = _Scope(f"s{k}_")
        sub_used = {f.target for f in c.sub_pattern.filters} | {c.sub_target} | {j.inner for j in c.correlate}
        _pattern(sub, c.sub_pattern, sub_used)
        val = sub.v(c.sub_target)
        agg = f"{c.sub_agg}({val})" if c.sub_agg else f"SAMPLE({val})"
        out = f"?sub{k}"
        proj = " ".join(f"({sub.v(j.inner)} AS {main.v(j.outer)})" for j in c.correlate)
        group = (" GROUP BY " + " ".join(sub.v(j.inner) for j in c.correlate)) if c.correlate else ""
        main.blocks.append(f"{{ SELECT {proj} ({agg} AS {out}) WHERE {{ {sub.body()} }}{group} }}")
        left = main.v(c.left_target)
        if c.offset:
            left = f"({left} + {c.offset})"
        if c.left_agg:
            having_extra.append(f"{c.left_agg}({left}) {c.op} {out}")
            group_extra.append(out)
        else:
            main.filters.append(f"{left} {c.op} {out}")
    # projection, grouping
    cols, aggregated = [], any(p.agg for p in plan.projections) or bool(plan.having) or bool(having_extra)
    plain = []
    for i, p in enumerate(plan.projections):
        if p.agg:
            arg = "*" if p.target == "*" else main.v(p.target)
            cols.append(f"({p.agg}({'DISTINCT ' if p.distinct else ''}{arg}) AS ?p{i})")
        else:
            v = main.v(p.target)
            cols.append(v if v not in cols else f"({v} AS ?p{i})")
            plain.append(v)
    tail = ""
    if aggregated:
        keys = [main.v(g) for g in plan.group_by] or plain
        keys = list(dict.fromkeys(keys + group_extra))
        if keys:
            tail += " GROUP BY " + " ".join(keys)
        hv = [f"{h.agg}({'*' if h.target == '*' else main.v(h.target)}) {h.op} "
              f"{literal(h.value, main.xsd.get(h.target) or 'double')}" for h in plan.having]
        hv += having_extra
        if hv:
            tail += " HAVING (" + " && ".join(hv) + ")"
    if plan.order_by:
        keys = []
        for o in plan.order_by:
            c = cols[o.projection]
            m = re.search(r"AS (\?\w+)\)$", c)
            expr = m.group(1) if m and plan.projections[o.projection].agg else (
                main.v(plan.projections[o.projection].target))
            keys.append(f"DESC({expr})" if o.desc else f"ASC({expr})")
        tail += " ORDER BY " + " ".join(keys)
    if plan.limit:
        tail += f" LIMIT {int(plan.limit)}"
    distinct = "DISTINCT " if plan.distinct else ""
    return PREFIXES + f"SELECT {distinct}{' '.join(cols)} WHERE {{ {main.body()} }}{tail}"
