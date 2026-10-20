"""The plan IR the planner (LLM or rule-based) submits; SPARQL is rendered from it by code.

Deliberately **non-recursive** (structured-output APIs cannot constrain recursive JSON
schemas): a plan has one main pattern, at most a few *negations* (NOT EXISTS of a flat
pattern) and *comparisons* against one scalar sub-plan (flat). That covers FIBEN's
non-nested and the N/A/J/JA nesting types to the depth they occur.

Identifiers inside a plan are short ids (``n1``, ``a1``); ontology terms are FIBEN local
names (``ListedSecurity``, ``hasTickerSymbol``), checked by :mod:`nl2q.obqc`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Op = Literal["=", "!=", "<", "<=", ">", ">=", "contains", "starts_with", "between", "in"]
Agg = Literal["COUNT", "SUM", "AVG", "MIN", "MAX"]


class Node(BaseModel):
    id: str = Field(description="short id, e.g. n1")
    cls: str = Field(description="ontology class local name, e.g. ListedSecurity")


class Link(BaseModel):
    subj: str = Field(description="node id of the subject")
    prop: str = Field(description="object property local name, e.g. isTradedOn")
    obj: str = Field(description="node id of the object")


class Attr(BaseModel):
    id: str = Field(description="short id, e.g. a1")
    node: str = Field(description="node id")
    prop: str = Field(description="datatype property local name, e.g. hasTickerSymbol")


class Filter(BaseModel):
    target: str = Field(description="attr id (or node id for = on an individual)")
    op: Op
    value: Optional[str] = None
    value2: Optional[str] = Field(None, description="upper bound for between")
    values: list[str] = Field(default_factory=list, description="for in")


class Projection(BaseModel):
    target: str = Field(description="attr id or node id ('*' with COUNT)")
    agg: Optional[Agg] = None
    distinct: bool = False


class Having(BaseModel):
    agg: Agg
    target: str
    op: Op
    value: str


class Order(BaseModel):
    projection: int = Field(description="0-based index into projections")
    desc: bool = False


class Pattern(BaseModel):
    nodes: list[Node] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    attrs: list[Attr] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)


class Join(BaseModel):
    outer: str = Field(description="id in the main pattern (node or attr)")
    inner: str = Field(description="id in the inner pattern (node or attr) that must be equal")


class Negation(BaseModel):
    """FILTER NOT EXISTS { pattern } joined to the main pattern on `joins`."""
    pattern: Pattern
    joins: list[Join]


class Comparison(BaseModel):
    """left OP (scalar value of the sub-plan), e.g. SUM(a3) > (SUM of b2 in pattern)."""
    left_target: str
    left_agg: Optional[Agg] = None
    op: Literal["=", "!=", "<", "<=", ">", ">="]
    sub_pattern: Pattern
    sub_target: str
    sub_agg: Optional[Agg] = None
    correlate: list[Join] = Field(default_factory=list,
                                  description="equalities linking the sub-plan to the main pattern")
    offset: Optional[float] = Field(None, description="left + offset OP sub (e.g. price + 50 < last)")


class Plan(BaseModel):
    answerable: bool = True
    reason: str = Field("", description="why not answerable, or a short note")
    nodes: list[Node] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    attrs: list[Attr] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    projections: list[Projection] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list, description="attr ids (auto-derived if empty)")
    having: list[Having] = Field(default_factory=list)
    order_by: list[Order] = Field(default_factory=list)
    limit: Optional[int] = None
    distinct: bool = False
    negations: list[Negation] = Field(default_factory=list)
    comparisons: list[Comparison] = Field(default_factory=list)


def schema_json() -> dict:
    return Plan.model_json_schema()
