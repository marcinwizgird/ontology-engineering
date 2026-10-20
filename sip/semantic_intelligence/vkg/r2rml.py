"""The W3C R2RML model (https://www.w3.org/TR/r2rml/) over the ``mappings`` named graph.

Supported subset — what Ontop-style virtual knowledge graphs use in practice:

* ``rr:TriplesMap`` with ``rr:logicalTable`` (``rr:tableName`` or ``rr:sqlQuery``);
* ``rr:subjectMap`` (``rr:template`` | ``rr:column`` | ``rr:constant``, ``rr:class``,
  ``rr:termType``);
* ``rr:predicateObjectMap`` with ``rr:predicate`` (or a constant ``rr:predicateMap``) and
  an ``rr:objectMap`` (``rr:column`` | ``rr:template`` | ``rr:constant``, ``rr:datatype``,
  ``rr:language``, ``rr:termType``) or a referencing object map
  (``rr:parentTriplesMap`` + ``rr:joinCondition`` ``rr:child``/``rr:parent``); the
  shortcuts ``rr:object``/``rr:subject``/``rr:class`` are read too.

Not supported (reported as warnings on import, never silently dropped from a parse):
``rr:graphMap``/``rr:graph``, ``rr:sqlVersion`` and non-constant predicate maps.

**Storage form.** In the platform the nested nodes of a triples map are *skolem IRIs*
under the map's IRI (``<map>/logicalTable``, ``<map>/pom/0/objectMap`` …) instead of
blank nodes, so that a change set can remove a map exactly, the history records stable
terms and the Fuseki store can delete them by value. :func:`to_graph` with
``bnodes=True`` writes the idiomatic blank-node form for export to Ontop and friends.
SIP adds one triple per map, ``sip:source "<id>"``, naming the registered database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from rdflib.term import Node

from ..core.namespaces import SIP

__all__ = ["RR", "TermMap", "RefObjectMap", "PredicateObjectMap", "TriplesMap",
           "parse_maps", "to_graph", "map_nodes", "placeholders", "MappingError"]

RR = Namespace("http://www.w3.org/ns/r2rml#")
_TERM_TYPES = {"iri": RR.IRI, "blanknode": RR.BlankNode, "literal": RR.Literal}


class MappingError(ValueError):
    """A triples map that cannot be represented."""


_PH = re.compile(r"(?<!\\)\{((?:[^{}\\]|\\.)*)\}")


def placeholders(template: str) -> list[str]:
    """Column names referenced by an ``rr:template`` (quotes and escapes removed)."""
    out = []
    for m in _PH.finditer(template or ""):
        name = m.group(1).replace("\\{", "{").replace("\\}", "}")
        if len(name) >= 2 and name[0] == name[-1] == '"':
            name = name[1:-1].replace('""', '"')
        out.append(name)
    return out


@dataclass
class TermMap:
    """A subject or object map (rr:column | rr:template | rr:constant)."""

    column: str | None = None
    template: str | None = None
    constant: str | None = None
    term_type: str | None = None          # iri | blanknode | literal (None = R2RML default)
    datatype: str | None = None
    language: str | None = None
    constant_is_literal: bool = False

    def __post_init__(self) -> None:
        n = sum(x is not None for x in (self.column, self.template, self.constant))
        if n != 1:
            raise MappingError("a term map needs exactly one of column, template, constant")
        if self.term_type is not None:
            self.term_type = self.term_type.lower().replace("rr:", "")
            if self.term_type not in _TERM_TYPES:
                raise MappingError("termType is iri | blanknode | literal")
        if self.datatype and self.language:
            raise MappingError("a term map cannot have both datatype and language")

    def kind(self, *, subject: bool = False) -> str:
        """The effective term type (R2RML §7.4 defaults)."""
        if self.term_type:
            return self.term_type
        if self.datatype or self.language:
            return "literal"
        if self.constant is not None:
            return "literal" if self.constant_is_literal else "iri"
        if subject or self.template is not None:
            return "iri"
        return "literal"

    def columns(self) -> list[str]:
        if self.column is not None:
            return [self.column]
        if self.template is not None:
            return placeholders(self.template)
        return []

    def as_dict(self) -> dict:
        d = {k: v for k, v in (("column", self.column), ("template", self.template),
                               ("constant", self.constant), ("termType", self.term_type),
                               ("datatype", self.datatype), ("language", self.language))
             if v is not None}
        if self.constant is not None and self.constant_is_literal:
            d["literal"] = True
        return d


@dataclass
class RefObjectMap:
    parent: str                                   # IRI of the parent triples map
    joins: list[tuple[str, str]] = field(default_factory=list)   # (child, parent)

    def as_dict(self) -> dict:
        return {"parent": self.parent, "joins": [list(j) for j in self.joins]}


@dataclass
class PredicateObjectMap:
    predicate: str
    object: TermMap | None = None
    ref: RefObjectMap | None = None

    def __post_init__(self) -> None:
        if (self.object is None) == (self.ref is None):
            raise MappingError(f"predicate {self.predicate}: give an object map or a parent map")

    def as_dict(self) -> dict:
        d = {"predicate": self.predicate}
        d.update(self.object.as_dict() if self.object else self.ref.as_dict())
        return d


@dataclass
class TriplesMap:
    iri: str
    subject: TermMap
    table_name: str | None = None
    sql_query: str | None = None
    classes: list[str] = field(default_factory=list)
    poms: list[PredicateObjectMap] = field(default_factory=list)
    source: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if (self.table_name is None) == (self.sql_query is None):
            raise MappingError(f"{self.iri}: logical table needs exactly one of "
                               "tableName or sqlQuery")
        self.classes = sorted(set(self.classes))
        self.poms.sort(key=_pom_key)       # stable order -> stable skolem IRIs

    # -- the user-facing dict form ---------------------------------------- #
    @property
    def id(self) -> str:
        return re.split(r"[#/:]", self.iri)[-1] or self.iri

    def as_dict(self) -> dict:
        lt = {"tableName": self.table_name} if self.table_name else {"sqlQuery": self.sql_query}
        d = {"iri": self.iri, "id": self.id, "logicalTable": lt,
             "subject": dict(self.subject.as_dict(), classes=list(self.classes)),
             "predicateObjects": [p.as_dict() for p in self.poms]}
        if self.source:
            d["source"] = self.source
        if self.label:
            d["label"] = self.label
        return d

    @classmethod
    def from_dict(cls, d: dict, *, mint: Callable[[str], str] = lambda x: x,
                  resolve: Callable[[str], str] = lambda x: x) -> "TriplesMap":
        """Build from the dict form. ``mint`` turns an ``id`` into a map IRI, ``resolve``
        turns a CURIE / local name of an ontology term into an IRI."""
        if not isinstance(d, dict):
            raise MappingError("a triples map is a dict")
        iri = d.get("iri") or (mint(d["id"]) if d.get("id") else None)
        if not iri:
            raise MappingError("a triples map needs an id or an iri")
        lt = dict(d.get("logicalTable") or {})
        if "table" in d:
            lt.setdefault("tableName", d["table"])
        if "sql" in d:
            lt.setdefault("sqlQuery", d["sql"])
        subj = dict(d.get("subject") or {})
        classes = [resolve(c) for c in subj.pop("classes", []) or []]
        if subj.get("class"):
            classes.append(resolve(subj.pop("class")))
        poms = []
        for p in d.get("predicateObjects") or []:
            p = dict(p)
            pred = resolve(p.pop("predicate"))
            if "parent" in p:
                parent = p["parent"]
                parent = parent if _is_iri(parent) else mint(parent)
                poms.append(PredicateObjectMap(pred, ref=RefObjectMap(
                    parent, [tuple(j) for j in p.get("joins") or []])))
            else:
                poms.append(PredicateObjectMap(pred, object=_term_from_dict(p, resolve)))
        return cls(iri, _term_from_dict(subj, resolve), lt.get("tableName"), lt.get("sqlQuery"),
                   classes, poms, d.get("source"), d.get("label"))

    # -- RDF ----------------------------------------------------------------- #
    def triples(self, *, bnodes: bool = False) -> list[tuple[Node, Node, Node]]:
        me = URIRef(self.iri)

        def node(path: str) -> Node:
            return BNode() if bnodes else URIRef(f"{self.iri}/{path}")
        out: list[tuple[Node, Node, Node]] = [(me, RDF.type, RR.TriplesMap)]
        lt = node("logicalTable")
        out.append((me, RR.logicalTable, lt))
        if self.table_name:
            out.append((lt, RR.tableName, Literal(self.table_name)))
        else:
            out.append((lt, RR.sqlQuery, Literal(self.sql_query)))
        sm = node("subjectMap")
        out.append((me, RR.subjectMap, sm))
        out += _term_triples(sm, self.subject)
        for c in self.classes:
            out.append((sm, RR["class"], URIRef(c)))
        for i, p in enumerate(self.poms):
            pom = node(f"pom/{i}")
            out.append((me, RR.predicateObjectMap, pom))
            out.append((pom, RR.predicate, URIRef(p.predicate)))
            om = node(f"pom/{i}/objectMap")
            out.append((pom, RR.objectMap, om))
            if p.object is not None:
                out += _term_triples(om, p.object)
            else:
                out.append((om, RR.parentTriplesMap, URIRef(p.ref.parent)))
                for j, (child, parent) in enumerate(p.ref.joins):
                    jc = node(f"pom/{i}/join/{j}")
                    out += [(om, RR.joinCondition, jc), (jc, RR.child, Literal(child)),
                            (jc, RR.parent, Literal(parent))]
        if self.source:
            out.append((me, SIP.source, Literal(self.source)))
        if self.label:
            out.append((me, URIRef("http://www.w3.org/2000/01/rdf-schema#label"),
                        Literal(self.label)))
        return out

    def terms(self) -> set[str]:
        """Ontology terms this map refers to (classes, predicates, datatypes, constants)."""
        out = set(self.classes)
        for p in self.poms:
            out.add(p.predicate)
            if p.object is not None:
                if p.object.datatype:
                    out.add(p.object.datatype)
                if p.object.constant is not None and p.object.kind() == "iri":
                    out.add(p.object.constant)
        if self.subject.constant is not None:
            out.add(self.subject.constant)
        return out


def _is_iri(x: str) -> bool:
    return x.startswith(("http://", "https://", "urn:", "file:"))


def _term_from_dict(d: dict, resolve: Callable[[str], str]) -> TermMap:
    dt = d.get("datatype")
    if dt:
        dt = str(XSD) + dt[4:] if dt.startswith("xsd:") else resolve(dt)
    const = d.get("constant")
    lit = bool(d.get("literal"))
    if const is not None and not lit and not d.get("datatype") and not d.get("language"):
        const = resolve(const) if (d.get("termType") or "iri").lower() == "iri" else const
    return TermMap(d.get("column"), d.get("template"), const, d.get("termType"), dt,
                   d.get("language"), lit)


def _term_triples(n: Node, t: TermMap) -> list[tuple]:
    out = []
    if t.column is not None:
        out.append((n, RR.column, Literal(t.column)))
    if t.template is not None:
        out.append((n, RR.template, Literal(t.template)))
    if t.constant is not None:
        out.append((n, RR.constant, Literal(t.constant) if t.kind() == "literal"
                    else URIRef(t.constant)))
    if t.term_type:
        out.append((n, RR.termType, _TERM_TYPES[t.term_type]))
    if t.datatype:
        out.append((n, RR.datatype, URIRef(t.datatype)))
    if t.language:
        out.append((n, RR.language, Literal(t.language)))
    return out


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def _one(g: Graph, s: Node, p: Node) -> Node | None:
    return next(iter(g.objects(s, p)), None)


def _parse_term(g: Graph, n: Node) -> TermMap:
    tt = _one(g, n, RR.termType)
    const = _one(g, n, RR.constant)
    col, tpl = _one(g, n, RR.column), _one(g, n, RR.template)
    dt, lang = _one(g, n, RR.datatype), _one(g, n, RR.language)
    return TermMap(str(col) if col is not None else None, str(tpl) if tpl is not None else None,
                   str(const) if const is not None else None,
                   {RR.IRI: "iri", RR.BlankNode: "blanknode", RR.Literal: "literal"}.get(tt)
                   if tt is not None else None,
                   str(dt) if dt is not None else None, str(lang) if lang is not None else None,
                   isinstance(const, Literal))


def triples_map_iris(g: Graph) -> list[URIRef]:
    s = set(g.subjects(RDF.type, RR.TriplesMap)) | set(g.subjects(RR.logicalTable, None))
    return sorted(x for x in s if isinstance(x, URIRef))


def parse_maps(g: Graph, warnings: list[str] | None = None) -> list[TriplesMap]:
    """Every triples map in *g* (other content, e.g. alignment cells, is ignored)."""
    warn = warnings if warnings is not None else []
    out = []
    for tm in triples_map_iris(g):
        try:
            lt = _one(g, tm, RR.logicalTable)
            table = _one(g, lt, RR.tableName) if lt is not None else None
            sql = _one(g, lt, RR.sqlQuery) if lt is not None else None
            sm = _one(g, tm, RR.subjectMap)
            if sm is not None:
                subj = _parse_term(g, sm)
                classes = sorted(str(c) for c in g.objects(sm, RR["class"]))
                if _one(g, sm, RR.graphMap) is not None or _one(g, sm, RR.graph) is not None:
                    warn.append(f"{tm}: rr:graphMap is not supported and was ignored")
            else:
                s_const = _one(g, tm, RR.subject)
                if s_const is None:
                    raise MappingError("no subject map")
                subj, classes = TermMap(constant=str(s_const)), []
            poms = []
            for pom in g.objects(tm, RR.predicateObjectMap):
                preds = [str(p) for p in g.objects(pom, RR.predicate)]
                for pm in g.objects(pom, RR.predicateMap):
                    c = _one(g, pm, RR.constant)
                    if c is None:
                        warn.append(f"{tm}: only constant predicate maps are supported")
                    else:
                        preds.append(str(c))
                objs: list = []
                for o in g.objects(pom, RR.object):
                    objs.append(TermMap(constant=str(o), constant_is_literal=isinstance(o, Literal)))
                for om in g.objects(pom, RR.objectMap):
                    parent = _one(g, om, RR.parentTriplesMap)
                    if parent is not None:
                        joins = sorted((str(_one(g, j, RR.child)), str(_one(g, j, RR.parent)))
                                       for j in g.objects(om, RR.joinCondition))
                        objs.append(RefObjectMap(str(parent), joins))
                    else:
                        objs.append(_parse_term(g, om))
                if _one(g, pom, RR.graphMap) is not None or _one(g, pom, RR.graph) is not None:
                    warn.append(f"{tm}: rr:graphMap is not supported and was ignored")
                for p in preds:
                    for o in objs:
                        poms.append(PredicateObjectMap(p, ref=o) if isinstance(o, RefObjectMap)
                                    else PredicateObjectMap(p, object=o))
            src = _one(g, tm, SIP.source)
            label = _one(g, tm, URIRef("http://www.w3.org/2000/01/rdf-schema#label"))
            out.append(TriplesMap(str(tm), subj, str(table) if table is not None else None,
                                  str(sql) if sql is not None else None, classes, poms,
                                  str(src) if src is not None else None,
                                  str(label) if label is not None else None))
        except MappingError as e:
            warn.append(f"{tm}: {e}")
    return out


def _pom_key(p: PredicateObjectMap):
    """Stable order so that re-serialising a parsed map yields the same skolem IRIs."""
    return (p.predicate, sorted(p.as_dict().items(), key=str).__repr__())


def to_graph(maps: Iterable[TriplesMap], *, bnodes: bool = True,
             prefixes: dict[str, str] | None = None) -> Graph:
    g = Graph()
    g.bind("rr", RR)
    g.bind("xsd", XSD)
    g.bind("sip", SIP)
    for p, ns in (prefixes or {}).items():
        g.bind(p, ns)
    for m in maps:
        for t in m.triples(bnodes=bnodes):
            g.add(t)
    return g


def map_nodes(g: Graph, tm: URIRef) -> list[tuple]:
    """Every stored triple that belongs to triples map *tm*: its own triples plus the
    nested nodes (skolem IRIs under ``tm/`` or blank nodes), never another map."""
    maps = set(triples_map_iris(g))
    out, seen, todo = [], {tm}, [tm]
    prefix = f"{tm}/"
    while todo:
        s = todo.pop()
        for t in g.triples((s, None, None)):
            out.append(t)
            o = t[2]
            if o in seen or o in maps:
                continue
            if isinstance(o, BNode) or (isinstance(o, URIRef) and str(o).startswith(prefix)):
                seen.add(o)
                todo.append(o)
    return out
