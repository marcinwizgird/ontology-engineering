"""Conformance checks for an R2RML mapping against the database metadata and the TBox.

Works on any R2RML graph (the generated FIBEN mapping or a hand-written one), using the
same db-metadata.json that Ontop compiles against and the OWL TBox the queries use. A
mapping that passes cannot produce the defects the PoC hit by hand: unquoted placeholders,
columns that don't exist, links that don't follow a foreign key, literals whose datatype
disagrees with the ontology.

    python tools/check_mappings.py                # errors and warnings; exit 1 on any error
    python tools/check_mappings.py --coverage     # also list unmapped tables and columns
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from rdflib import OWL, RDF, RDFS, XSD, Graph, Namespace, URIRef
from sqlglot import exp

RR = Namespace("http://www.w3.org/ns/r2rml#")
ARTIFACTS = Path(__file__).resolve().parents[1] / "vkg-artifacts"

RULES = {
    "M01": "logical table resolves to one table in the database metadata",
    "M02": "every referenced column exists (and, for an rr:sqlQuery, is selected)",
    "M03": "identifiers and template placeholders are double-quoted",
    "M04": "a typed subject's template is keyed by a unique key of its table",
    "M05": "an IRI used outside its typing table follows a foreign key to that table's key",
    "M06": "every IRI template family is typed by at least one map",
    "M07": "classes and predicates are declared in the TBox",
    "M08": "template objects use object properties; column objects use datatype properties",
    "M09": "literal datatype matches the TBox range and the column's SQL type",
    "M10": "subjects and objects are compatible with rdfs:domain / rdfs:range",
    "M11": "subject template columns are NOT NULL",
    "M12": "coverage: tables and columns no map uses",
}

_PART = re.compile(r'"([^"]*)"|([^."]+)')
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_STRINGS = {XSD.string}
_COMPATIBLE = {  # SQL kind -> datatypes that represent it without loss
    "integer": {XSD.integer, XSD.int, XSD.long, XSD.short, XSD.decimal},
    "decimal": {XSD.decimal, XSD.double, XSD.float},
    "string": _STRINGS,
    "date": {XSD.date},
    "datetime": {XSD.dateTime},
    "boolean": {XSD.boolean},
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # error | warning | info
    map: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.rule} {self.map}: {self.message}"


# --- inputs -------------------------------------------------------------------------------

def _split_ident(name: str) -> tuple[tuple[str, ...], bool]:
    """'"PUBLIC"."COMPANY"' -> (('PUBLIC', 'COMPANY'), all parts quoted)."""
    parts = _PART.findall(name)
    return tuple(q or u for q, u in parts), all(q for q, _ in parts)


def _sql_kind(sql_type: str) -> str:
    t = sql_type.lower()
    if t.startswith(("int", "bigint", "smallint", "serial", "bigserial")):
        return "integer"
    if t.startswith(("numeric", "decimal", "real", "double", "float")):
        return "decimal"
    if t.startswith("timestamp"):
        return "datetime"
    if t.startswith("date"):
        return "date"
    if t.startswith("bool"):
        return "boolean"
    return "string"


@dataclass
class Table:
    columns: dict[str, dict]  # name -> {"nullable": bool, "kind": str}
    keys: list[frozenset[str]] = field(default_factory=list)
    fks: dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]] = field(default_factory=dict)


def load_metadata(path: Path) -> dict[tuple[str, ...], Table]:
    tables: dict[tuple[str, ...], Table] = {}
    for rel in json.loads(path.read_text(encoding="utf-8"))["relations"]:
        name = tuple(_split_ident(p)[0][0] for p in rel["name"])
        cols = {_split_ident(c["name"])[0][0]: {"nullable": c["isNullable"],
                                                "kind": _sql_kind(c["datatype"])}
                for c in rel["columns"]}
        t = Table(cols, [frozenset(_split_ident(d)[0][0] for d in u["determinants"])
                         for u in rel.get("uniqueConstraints", [])])
        for fk in rel.get("foreignKeys", []):
            src = tuple(_split_ident(c)[0][0] for c in fk["from"]["columns"])
            dst_t = tuple(_split_ident(p)[0][0] for p in fk["to"]["relation"])
            t.fks[src] = (dst_t, tuple(_split_ident(c)[0][0] for c in fk["to"]["columns"]))
        tables[name] = t
    return tables


@dataclass
class TBox:
    classes: set[URIRef]
    object_props: set[URIRef]
    data_props: set[URIRef]
    domain: dict[URIRef, URIRef]
    range: dict[URIRef, URIRef]
    supers: dict[URIRef, set[URIRef]]  # reflexive-transitive

    def subsumed(self, cls: URIRef, by: URIRef) -> bool:
        return by in self.supers.get(cls, {cls})


def load_tbox(path: Path) -> TBox:
    g = Graph().parse(path)
    direct = defaultdict(set)
    for c, s in g.subject_objects(RDFS.subClassOf):
        direct[c].add(s)
    classes = set(g.subjects(RDF.type, OWL.Class)) | set(direct)

    def closure(c):
        seen, todo = {c}, [c]
        while todo:
            for s in direct.get(todo.pop(), ()):
                if s not in seen:
                    seen.add(s)
                    todo.append(s)
        return seen

    return TBox(classes, set(g.subjects(RDF.type, OWL.ObjectProperty)),
                set(g.subjects(RDF.type, OWL.DatatypeProperty)),
                {p: o for p, o in g.subject_objects(RDFS.domain)},
                {p: o for p, o in g.subject_objects(RDFS.range)},
                {c: closure(c) for c in classes})


# --- the mapping, normalised --------------------------------------------------------------

@dataclass
class Template:
    family: str            # the template with every placeholder replaced by {}
    columns: tuple[str, ...]
    quoted: bool


def _template(text: str) -> Template:
    inner = _PLACEHOLDER.findall(text)
    return Template(_PLACEHOLDER.sub("{}", text),
                    tuple(i.strip('"') for i in inner),
                    all(len(i) > 1 and i[0] == i[-1] == '"' for i in inner))


@dataclass
class TriplesMap:
    name: str
    table: tuple[str, ...] | None = None
    view_columns: set[str] | None = None   # columns an rr:sqlQuery exposes; None for a table
    query_columns: set[str] = field(default_factory=set)
    subject: Template | None = None
    classes: list[URIRef] = field(default_factory=list)
    poms: list[tuple[URIRef, str, object, URIRef | None]] = field(default_factory=list)
    # (predicate, "column" | "template", column name | Template, datatype)


def _parse_maps(m: Graph, out: list[Finding]) -> list[TriplesMap]:
    maps = []
    for node in sorted(m.subjects(RDF.type, RR.TriplesMap), key=str):
        tm = TriplesMap(str(node).rsplit("#", 1)[-1])
        lt, sm = m.value(node, RR.logicalTable), m.value(node, RR.subjectMap)
        if lt is None or sm is None:
            out.append(Finding("M01", "error", tm.name, "needs rr:logicalTable and rr:subjectMap"))
            continue
        if (name := m.value(lt, RR.tableName)) is not None:
            tm.table, quoted = _split_ident(str(name))
            if not quoted:
                out.append(Finding("M03", "error", tm.name, f"table name {name} is not quoted"))
        elif (query := m.value(lt, RR.sqlQuery)) is not None:
            _parse_view(tm, str(query), out)
        else:
            out.append(Finding("M01", "error", tm.name, "logical table has no table or query"))
        if (tpl := m.value(sm, RR.template)) is None:
            out.append(Finding("M04", "error", tm.name, "subject map has no rr:template"))
            continue
        tm.subject = _template(str(tpl))
        tm.classes = sorted(m.objects(sm, RR["class"]), key=str)
        for pom in m.objects(node, RR.predicateObjectMap):
            om, pred = m.value(pom, RR.objectMap), m.value(pom, RR.predicate)
            if (col := m.value(om, RR.column)) is not None:
                name, quoted = _split_ident(str(col))
                if not quoted:
                    out.append(Finding("M03", "error", tm.name, f"column {col} is not quoted"))
                tm.poms.append((pred, "column", name[-1], m.value(om, RR.datatype)))
            elif (t := m.value(om, RR.template)) is not None:
                tm.poms.append((pred, "template", _template(str(t)), None))
        tm.poms.sort(key=lambda p: str(p[0]))
        maps.append(tm)
    return maps


def _parse_view(tm: TriplesMap, query: str, out: list[Finding]) -> None:
    try:
        tree = sqlglot.parse_one(query, read="postgres")
    except sqlglot.errors.ParseError as e:
        out.append(Finding("M01", "error", tm.name, f"rr:sqlQuery does not parse: {e}"))
        return
    tables = list(tree.find_all(exp.Table))
    if not isinstance(tree, exp.Select) or len(tables) != 1:
        out.append(Finding("M01", "warning", tm.name,
                           "rr:sqlQuery is not a single-table SELECT; columns not checked"))
        return
    t = tables[0]
    tm.table = tuple(p for p in (t.catalog, t.db, t.name) if p)
    if not all(i.quoted for i in tree.find_all(exp.Identifier)):
        out.append(Finding("M03", "error", tm.name, "rr:sqlQuery has unquoted identifiers"))
    tm.view_columns = {e.alias_or_name for e in tree.expressions}
    tm.query_columns = {c.name for c in tree.find_all(exp.Column)}


# --- checks -------------------------------------------------------------------------------

def check(mapping: Graph, tables: dict[tuple[str, ...], Table], tbox: TBox,
          coverage: bool = False) -> list[Finding]:
    out: list[Finding] = []
    maps = _parse_maps(mapping, out)
    resolved: dict[str, Table] = {}
    for tm in maps:
        t = tables.get(tm.table) if tm.table else None
        if tm.table and t is None:
            out.append(Finding("M01", "error", tm.name, f"table {'.'.join(tm.table)} is not in the metadata"))
        if t is not None:
            resolved[tm.name] = t

    # Template families: which tables type them, and by which key column(s).
    typing: dict[str, dict[tuple[str, ...], tuple[str, ...]]] = defaultdict(dict)
    family_classes: dict[str, set[URIRef]] = defaultdict(set)
    for tm in maps:
        if tm.classes and tm.table:
            typing[tm.subject.family][tm.table] = tm.subject.columns
            family_classes[tm.subject.family] |= set(tm.classes)

    for tm in maps:
        t = resolved.get(tm.name)
        _check_columns(tm, t, out)
        if not tm.subject.quoted or any(not tpl.quoted for _, kind, tpl, _ in tm.poms if kind == "template"):
            out.append(Finding("M03", "error", tm.name, "template placeholders must be quoted, e.g. {\"ID\"}"))
        if t is None:
            continue
        s_cols = tm.subject.columns
        if tm.classes and frozenset(s_cols) not in t.keys:
            out.append(Finding("M04", "error", tm.name,
                               f"subject {tm.subject.family} uses {s_cols}, not a unique key of {tm.table[-1]}"))
        for c in s_cols:
            if c in t.columns and t.columns[c]["nullable"]:
                out.append(Finding("M11", "warning", tm.name,
                                   f"subject column {c} is nullable: rows where it is NULL produce no subject"))
        if not tm.classes:
            _check_link(tm, tm.subject, t, typing, out, "subject")
        for pred, kind, obj, _ in tm.poms:
            if kind == "template":
                _check_link(tm, obj, t, typing, out, f"object of {_short(pred)}")
        _check_vocabulary(tm, t, tbox, family_classes, out)

    for fam in {tm.subject.family for tm in maps} | {
            o.family for tm in maps for _, k, o, _ in tm.poms if k == "template"}:
        if fam not in typing:
            out.append(Finding("M06", "warning", "-", f"IRIs {fam} are never given a class"))
    if coverage:
        out += _coverage(maps, tables)
    return out


def _check_columns(tm: TriplesMap, t: Table | None, out: list[Finding]) -> None:
    used = set(tm.subject.columns)
    for _, kind, obj, _ in tm.poms:
        used |= set(obj.columns) if kind == "template" else {obj}
    if tm.view_columns is not None:
        for c in sorted(used - tm.view_columns):
            out.append(Finding("M02", "error", tm.name, f"column {c} is not selected by the rr:sqlQuery"))
    if t is None:
        return
    source = tm.query_columns if tm.view_columns is not None else used
    for c in sorted(source - set(t.columns)):
        out.append(Finding("M02", "error", tm.name, f"column {c} does not exist in {tm.table[-1]}"))


def _check_link(tm, tpl: Template, t: Table, typing, out, role: str) -> None:
    owners = typing.get(tpl.family)
    if not owners:
        return  # reported once by M06
    if owners.get(tm.table) == tpl.columns:
        return  # the map's own table types this IRI with the same key
    fk = t.fks.get(tpl.columns)
    if fk is None:
        out.append(Finding("M05", "error", tm.name,
                           f"{role} {tpl.family} uses {tpl.columns}, which is not a foreign key"))
    elif owners.get(fk[0]) != fk[1]:
        out.append(Finding("M05", "error", tm.name,
                           f"{role} {tpl.family} follows {tpl.columns} -> {fk[0][-1]}{fk[1]}, "
                           f"which is not the key that table's maps use for these IRIs"))


def _check_vocabulary(tm, t: Table, tbox: TBox, family_classes, out) -> None:
    for c in tm.classes:
        if c not in tbox.classes:
            out.append(Finding("M07", "error", tm.name, f"class {_short(c)} is not declared in the TBox"))
    subj_classes = family_classes.get(tm.subject.family, set())
    for pred, kind, obj, dt in tm.poms:
        p = _short(pred)
        if pred not in tbox.object_props | tbox.data_props:
            out.append(Finding("M07", "error", tm.name, f"predicate {p} is not declared in the TBox"))
            continue
        if kind == "template" and pred not in tbox.object_props:
            out.append(Finding("M08", "error", tm.name, f"{p} links to an IRI but is a datatype property"))
        if kind == "column" and pred not in tbox.data_props:
            out.append(Finding("M08", "error", tm.name, f"{p} maps a column but is an object property"))
        if (d := tbox.domain.get(pred)) and subj_classes and not any(
                tbox.subsumed(c, d) for c in subj_classes):
            out.append(Finding("M10", "error", tm.name,
                               f"{p} has domain {_short(d)}; the subject is only ever "
                               f"{', '.join(sorted(_short(c) for c in subj_classes))}"))
        if kind == "template":
            r, obj_classes = tbox.range.get(pred), family_classes.get(obj.family, set())
            if r and obj_classes and not any(tbox.subsumed(c, r) for c in obj_classes):
                out.append(Finding("M10", "error", tm.name,
                                   f"{p} has range {_short(r)}; the object is only ever "
                                   f"{', '.join(sorted(_short(c) for c in obj_classes))}"))
        elif kind == "column":
            _check_datatype(tm, pred, obj, dt, t, tbox, out)


def _check_datatype(tm, pred, col: str, dt, t: Table, tbox: TBox, out) -> None:
    p, r = _short(pred), tbox.range.get(pred)
    effective = dt or XSD.string
    if r is not None and r not in _STRINGS and dt is None:
        out.append(Finding("M09", "error", tm.name,
                           f"{p} has range {_short(r)} but the map produces a plain literal; "
                           f"add rr:datatype {_short(r)}"))
    elif r is not None and dt is not None and dt != r:
        out.append(Finding("M09", "error", tm.name,
                           f"{p} has range {_short(r)} but the map declares {_short(dt)}"))
    if col in t.columns:
        kind = t.columns[col]["kind"]
        if effective not in _COMPATIBLE[kind]:
            sev = "warning" if effective in _STRINGS else "error"
            out.append(Finding("M09", sev, tm.name,
                               f"{p}: column {col} is {kind} but the literal is {_short(effective)}"))


def _coverage(maps: list[TriplesMap], tables) -> list[Finding]:
    used: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for tm in maps:
        if tm.table:
            used[tm.table] |= set(tm.subject.columns) | tm.query_columns
            for _, kind, obj, _ in tm.poms:
                used[tm.table] |= set(obj.columns) if kind == "template" else {obj}
    out = []
    for name, t in sorted(tables.items()):
        if name not in used:
            out.append(Finding("M12", "info", "-", f"table {name[-1]} is not mapped"))
            continue
        missing = [c for c in t.columns if c not in used[name]]
        if missing:
            out.append(Finding("M12", "info", "-", f"{name[-1]}: unmapped columns {', '.join(missing)}"))
    return out


def _short(iri) -> str:
    s = str(iri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mapping", type=Path, default=ARTIFACTS / "fiben-mappings.r2rml.ttl")
    ap.add_argument("--metadata", type=Path, default=ARTIFACTS / "db-metadata.json")
    ap.add_argument("--ontology", type=Path, default=ARTIFACTS / "fibo-subset.ttl")
    ap.add_argument("--coverage", action="store_true", help="also list unmapped tables and columns")
    args = ap.parse_args(argv)
    findings = check(Graph().parse(args.mapping), load_metadata(args.metadata),
                     load_tbox(args.ontology), coverage=args.coverage)
    for f in findings:
        print(f)
    errors = sum(f.severity == "error" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    print(f"{args.mapping.name}: {errors} errors, {warnings} warnings ({len(RULES)} rules)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
