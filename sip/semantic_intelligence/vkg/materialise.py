"""An R2RML processor: run logical tables against a source and generate RDF.

Follows R2RML §11 for the generated terms: an ``rr:template`` with term type IRI
percent-encodes each value (IRI-safe), a ``NULL`` in any referenced column produces no
term (so no triple), literals take the natural RDF datatype of the SQL value unless
``rr:datatype``/``rr:language`` say otherwise, and a referencing object map uses the
parent map's subject — directly when there is no join condition and the logical tables
coincide, otherwise by joining the child and parent rows on the join columns.

Every generated triple records which triples map produced it (``provenance``), so a
preview can say where a fact came from and an edit can show what it changes.

``limit`` bounds the rows read per logical table (previews); ``None`` reads everything
(small databases, or materialisation for ``mapping.queryData``).
"""

from __future__ import annotations

import datetime as _dt
import decimal
from dataclasses import dataclass, field
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from .r2rml import TermMap, TriplesMap, placeholders, _PH
from .source import RelationalSource, unquote

__all__ = ["Materialised", "materialise", "logical_sql"]


@dataclass
class Materialised:
    graph: Graph = field(default_factory=Graph)
    provenance: dict[tuple, set[str]] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def add(self, t: tuple, tm: str) -> None:
        self.graph.add(t)
        self.provenance.setdefault(t, set()).add(tm)


def logical_sql(tm: TriplesMap, src: RelationalSource) -> str:
    return tm.sql_query if tm.sql_query else src.table_query(tm.table_name)


class _Row:
    """Case-tolerant column lookup on one result row (R2RML column names are SQL
    identifiers: quoted ones match exactly, unquoted ones per the DB's folding)."""

    def __init__(self, cols: list[str], values: tuple) -> None:
        self.exact = dict(zip(cols, values))
        self.lower = {c.lower(): v for c, v in self.exact.items()}

    def get(self, name: str):
        n = unquote(name)
        if n in self.exact:
            return self.exact[n]
        if n.lower() in self.lower:
            return self.lower[n.lower()]
        raise KeyError(name)


def _lexical(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return repr(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.hex().upper()
    return str(v)


def _natural(v) -> Literal:
    """R2RML natural RDF literal of a SQL value."""
    if isinstance(v, bool):
        return Literal(v, datatype=XSD.boolean)
    if isinstance(v, int):
        return Literal(v, datatype=XSD.integer)
    if isinstance(v, float):
        return Literal(v, datatype=XSD.double)
    if isinstance(v, decimal.Decimal):
        return Literal(v, datatype=XSD.decimal)
    if isinstance(v, _dt.datetime):
        return Literal(v.isoformat(), datatype=XSD.dateTime)
    if isinstance(v, _dt.date):
        return Literal(v.isoformat(), datatype=XSD.date)
    if isinstance(v, bytes):
        return Literal(v.hex().upper(), datatype=XSD.hexBinary)
    return Literal(str(v))


def _fill(template: str, row: _Row, iri_safe: bool) -> str | None:
    out, pos = [], 0
    for m in _PH.finditer(template):
        out.append(template[pos:m.start()].replace("\\{", "{").replace("\\}", "}"))
        name = placeholders(m.group(0))[0]
        v = row.get(name)
        if v is None:
            return None
        s = _lexical(v)
        out.append(quote(s, safe="-._~") if iri_safe else s)
        pos = m.end()
    out.append(template[pos:].replace("\\{", "{").replace("\\}", "}"))
    return "".join(out)


def _term(t: TermMap, row: _Row, *, subject: bool = False, bnodes: dict | None = None):
    kind = t.kind(subject=subject)
    if t.constant is not None:
        if kind == "iri":
            return URIRef(t.constant)
        return Literal(t.constant, datatype=URIRef(t.datatype) if t.datatype else None,
                       lang=t.language)
    if t.column is not None:
        v = row.get(t.column)
        if v is None:
            return None
        if kind == "iri":
            return URIRef(_lexical(v))
        if kind == "blanknode":
            return (bnodes or {}).setdefault(("c", _lexical(v)), BNode())
        if t.datatype:
            return Literal(_lexical(v), datatype=URIRef(t.datatype))
        if t.language:
            return Literal(_lexical(v), lang=t.language)
        return _natural(v)
    s = _fill(t.template, row, iri_safe=(kind == "iri"))
    if s is None:
        return None
    if kind == "iri":
        return URIRef(s)
    if kind == "blanknode":
        return (bnodes or {}).setdefault(("t", s), BNode())
    return Literal(s, datatype=URIRef(t.datatype) if t.datatype else None, lang=t.language)


def materialise(maps: list[TriplesMap], sources: dict[str, RelationalSource], *,
                default_source: str | None = None, limit: int | None = None,
                only: set[str] | None = None) -> Materialised:
    """Run *maps* (or the subset whose IRIs are in *only*) and collect the triples."""
    res = Materialised()
    by_iri = {m.iri: m for m in maps}
    cache: dict[tuple[str, str], tuple[list[str], list[tuple]]] = {}
    bnodes: dict = {}

    def src_of(tm: TriplesMap) -> RelationalSource | None:
        sid = tm.source or default_source
        if sid is None and len(sources) == 1:
            sid = next(iter(sources))
        return sources.get(sid) if sid else None

    def rows_of(tm: TriplesMap, src: RelationalSource, lim: int | None):
        sql = logical_sql(tm, src)
        key = (src.id, sql, lim)
        if key not in cache:
            cache[key] = src.query(sql, limit=lim)
        return cache[key]

    for tm in maps:
        if only is not None and tm.iri not in only:
            continue
        src = src_of(tm)
        if src is None:
            res.warnings.append(f"{tm.iri}: no registered source "
                                f"{tm.source or default_source or ''}".rstrip())
            continue
        try:
            cols, rows = rows_of(tm, src, limit)
        except Exception as e:                      # bad SQL is a finding, not a crash
            res.warnings.append(f"{tm.iri}: {e}")
            continue
        res.rows[tm.iri] = len(rows)
        parents = {}
        for p in tm.poms:
            if p.ref is None:
                continue
            parent = by_iri.get(p.ref.parent)
            if parent is None:
                res.warnings.append(f"{tm.iri}: unknown parent triples map {p.ref.parent}")
                continue
            psrc = src_of(parent) or src
            if p.ref.joins:
                pcols, prow = rows_of(parent, psrc, None)
                index: dict[tuple, list] = {}
                for r in prow:
                    pr = _Row(pcols, r)
                    try:
                        key = tuple(_lexical(pr.get(j[1])) for j in p.ref.joins)
                    except KeyError as e:
                        res.warnings.append(f"{tm.iri}: parent column {e} not found")
                        break
                    s = _term(parent.subject, pr, subject=True, bnodes=bnodes)
                    if s is not None:
                        index.setdefault(key, []).append(s)
                parents[id(p)] = (parent, index)
            else:
                parents[id(p)] = (parent, None)
        for values in rows:
            row = _Row(cols, values)
            try:
                s = _term(tm.subject, row, subject=True, bnodes=bnodes)
            except KeyError as e:
                res.warnings.append(f"{tm.iri}: column {e} not in the logical table")
                break
            if s is None:
                continue
            for c in tm.classes:
                res.add((s, RDF.type, URIRef(c)), tm.iri)
            for p in tm.poms:
                pred = URIRef(p.predicate)
                try:
                    if p.object is not None:
                        o = _term(p.object, row, bnodes=bnodes)
                        if o is not None:
                            res.add((s, pred, o), tm.iri)
                        continue
                    if id(p) not in parents:
                        continue
                    parent, index = parents[id(p)]
                    if index is None:
                        o = _term(parent.subject, row, subject=True, bnodes=bnodes)
                        if o is not None:
                            res.add((s, pred, o), tm.iri)
                    else:
                        vals = [row.get(j[0]) for j in p.ref.joins]
                        if any(v is None for v in vals):
                            continue
                        for o in index.get(tuple(_lexical(v) for v in vals), []):
                            res.add((s, pred, o), tm.iri)
                except KeyError as e:
                    msg = f"{tm.iri}: column {e} not in the logical table"
                    if msg not in res.warnings:
                        res.warnings.append(msg)
    return res
