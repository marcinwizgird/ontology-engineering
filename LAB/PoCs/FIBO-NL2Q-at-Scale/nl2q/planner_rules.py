"""A rule-based planner (arm R): grounding -> plan with no language model.

It serves two purposes: the **no-LLM baseline** every learned arm must beat, and the
offline **simulator** that exercises the whole pipeline (grounding, rendering, checks,
compilation, execution, scoring) in tests and CI without API calls.

Heuristics (ATHENA-style, deliberately simple): nodes and links from the best grounding
tree; value mentions become equality filters on their (class, property); a numeric
comparison phrase ("more than 1500", "below 10") becomes a filter on the measure the
question mentions; "how many / number of" -> COUNT, "average" -> AVG, "total / sum" ->
SUM, "highest / maximum" -> MAX, "lowest / minimum" -> MIN; projections are the
attributes the question mentions, else the name-like attributes of the focus class.
"""

from __future__ import annotations

import re

from . import ir
from .grounding import GroundingResult
from .obqc import prop_range
from .querygraph import load as load_graph

NAME_PROPS = ("hasLegalName", "hasPersonName", "hasTickerSymbol", "hasName", "hasFormalName",
              "hasAccountNumber", "hasTitle")
_CMP = [(r"(?:more|greater|bigger|higher|larger) than|above|over|exceed(?:s|ing)?", ">"),
        (r"(?:less|smaller|lower|fewer) than|below|under", "<"),
        (r"at least|equal to or (?:greater|more) than|not (?:less|lower) than", ">="),
        (r"at most|equal to or (?:less|lower) than|not (?:more|higher|greater) than", "<="),
        (r"equal to|equals?", "=")]
_NUM = r"(-?\d+(?:\.\d+)?)\s*(million|billion|thousand|k|m|bn)?"
_SCALE = {"million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "thousand": 1e3, "k": 1e3}


def _agg(question: str) -> str | None:
    q = question.lower()
    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", q):
        return "COUNT"
    if re.search(r"\baverage\b|\bmean\b", q):
        return "AVG"
    if re.search(r"\btotal\b|\bsum\b", q):
        return "SUM"
    if re.search(r"\bhighest\b|\bmaximum\b|\bmax\b|\blargest\b|\bmost\b", q):
        return "MAX"
    if re.search(r"\blowest\b|\bminimum\b|\bmin\b|\bsmallest\b|\bleast\b", q):
        return "MIN"
    return None


def plan(question: str, gr: GroundingResult) -> ir.Plan:
    g = load_graph()
    best = gr.best
    if best is None:
        why = "; ".join(gr.unmapped_hints) or "the question's concepts do not connect in the mapped data"
        return ir.Plan(answerable=False, reason=why)
    nodes: dict[str, str] = {}

    def node(cls: str) -> str:
        if cls not in nodes:
            nodes[cls] = f"n{len(nodes) + 1}"
        return nodes[cls]

    links = []
    for s, p, o in best.tree:
        links.append(ir.Link(subj=node(s), prop=p, obj=node(o)))
    for c in best.classes:
        node(c)
    attrs: list[ir.Attr] = []
    filters: list[ir.Filter] = []
    mentioned: list[str] = []

    def attr(cls: str, prop: str) -> str:
        for a in attrs:
            if a.node == node(cls) and a.prop == prop:
                return a.id
        aid = f"a{len(attrs) + 1}"
        attrs.append(ir.Attr(id=aid, node=node(cls), prop=prop))
        return aid

    def host(prop: str) -> str | None:
        for cls in nodes:
            if prop in g.attributes(cls):
                return cls
        doms = sorted(g.domains_of(prop))
        return doms[0] if doms else None

    for c in best.choice:
        if c.kind == "value" and c.cls:
            filters.append(ir.Filter(target=attr(c.cls, c.local), op="=", value=c.value))
        elif c.kind == "datatype":
            h = c.cls or host(c.local)
            if h:
                if h not in nodes:
                    continue
                mentioned.append(attr(h, c.local))
    # numeric comparison on a mentioned numeric attribute
    q = question.lower()
    for pat, op in _CMP:
        m = re.search(rf"(?:{pat})\s+\$?{_NUM}", q)
        if m:
            val = float(m.group(1)) * _SCALE.get((m.group(2) or "").lower(), 1)
            num = [a for a in mentioned if prop_range(next(x.prop for x in attrs if x.id == a)) in ("integer", "double")]
            if not num:
                for cls in nodes:
                    for p in ("hasAmount", "hasMetricValue", "hasCount"):
                        if p in g.attributes(cls):
                            num = [attr(cls, p)]
                            break
                    if num:
                        break
            if num:
                filters.append(ir.Filter(target=num[0], op=op, value=repr(val)))
            break
    agg = _agg(question)
    projections: list[ir.Projection] = []
    focus = best.classes[0] if best.classes else next(iter(nodes))
    for c in best.choice:
        if c.kind == "class":
            focus = c.local
            break
    if agg == "COUNT":
        projections.append(ir.Projection(target=node(focus), agg="COUNT", distinct=True))
    elif agg:
        num = [a for a in mentioned if prop_range(next(x.prop for x in attrs if x.id == a)) in ("integer", "double")]
        if num:
            projections.append(ir.Projection(target=num[0], agg=agg))
    plain = [a for a in mentioned if not any(p.target == a for p in projections)]
    if not plain and not projections:
        for p in NAME_PROPS:
            if p in g.attributes(focus):
                plain = [attr(focus, p)]
                break
        if not plain:
            plain = [node(focus)]
    projections = [ir.Projection(target=t) for t in plain if t not in {f.target for f in filters}] + projections
    if not projections:
        projections = [ir.Projection(target=node(focus))]
    return ir.Plan(nodes=[ir.Node(id=i, cls=c) for c, i in nodes.items()], links=links, attrs=attrs,
                   filters=filters, projections=projections)
