"""Static checks of R2RML mappings against the (staged) ontology and the source schema,
coverage of the ontology by the mappings, and the impact of ontology refactorings.

Findings are dicts ``{severity, code, map, message}`` with severity ``error`` (the map
produces wrong or no data), ``warning`` (probably wrong) or ``info``. Codes:

=====================  =============================================================
unknown-class          rr:class is not a class of the ontology
unknown-property       rr:predicate is not declared in the ontology
property-kind          IRI objects on a datatype property, or literals on an object
                       property
deprecated-term        the map uses an owl:deprecated term
unknown-source         the map names no registered database
unknown-table          rr:tableName is not in the schema
bad-sql                rr:sqlQuery is not a read-only SELECT, or does not run
unknown-column         rr:column / join column not in the logical table
unknown-placeholder    a template placeholder is not a column of the logical table
no-placeholder         a subject template without placeholders (every row -> one IRI)
datatype-mismatch      SQL column type vs rr:datatype / the property's xsd range
unknown-parent         rr:parentTriplesMap names no triples map
join-required          a parent map over a different logical table without a join
iri-space-clash        maps minting subjects in one IRI space with different templates
=====================  =============================================================
"""

from __future__ import annotations

import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..owl.rendering import local_name
from .r2rml import TermMap, TriplesMap
from .source import RelationalSource, UnsafeSQL, check_select, unquote

__all__ = ["validate", "coverage", "impact", "rename_in_mappings"]

_BUILTIN = (str(RDF), str(RDFS), str(OWL), str(SKOS), str(XSD))

_COMPATIBLE = {
    "integer": {"integer", "int", "long", "short", "byte", "nonNegativeInteger",
                "positiveInteger", "nonPositiveInteger", "negativeInteger", "unsignedLong",
                "unsignedInt", "unsignedShort", "unsignedByte", "decimal", "double", "float",
                "boolean", "gYear", "string"},
    "decimal": {"decimal", "double", "float", "string"},
    "float": {"double", "float", "decimal", "string"},
    "boolean": {"boolean", "string"},
    "date": {"date", "dateTime", "string"},
    "datetime": {"dateTime", "dateTimeStamp", "date", "string"},
    "string": None,          # text columns can carry any lexical form (sqlite stores dates)
    "binary": {"hexBinary", "base64Binary"},
}


def sql_category(sql_type: str) -> str | None:
    t = (sql_type or "").upper()
    if not t:
        return None
    if "INT" in t:
        return "integer"
    if "BOOL" in t:
        return "boolean"
    if "TIMESTAMP" in t or "DATETIME" in t:
        return "datetime"
    if "DATE" in t:
        return "date"
    if any(x in t for x in ("CHAR", "CLOB", "TEXT", "STRING", "UUID", "JSON")):
        return "string"
    if any(x in t for x in ("REAL", "FLOA", "DOUB")):
        return "float"
    if any(x in t for x in ("DEC", "NUMERIC", "MONEY")):
        return "decimal"
    if "BLOB" in t or "BINARY" in t or "BYTEA" in t:
        return "binary"
    return None


def _kind_of(g: Graph, iri: URIRef) -> set[str]:
    types = set(g.objects(iri, RDF.type))
    out = set()
    if types & {OWL.Class, RDFS.Class}:
        out.add("class")
    if OWL.ObjectProperty in types:
        out.add("object")
    if OWL.DatatypeProperty in types:
        out.add("data")
    if types & {OWL.AnnotationProperty, RDF.Property}:
        out.add("annotation")
    return out


def _deprecated(g: Graph, iri: URIRef) -> bool:
    return any(str(v).lower() in ("true", "1") for v in g.objects(iri, OWL.deprecated))


def _f(sev: str, code: str, tm: TriplesMap | None, msg: str, **kw) -> dict:
    return {"severity": sev, "code": code, "map": tm.iri if tm else None, "message": msg, **kw}


def _columns(tm: TriplesMap, src: RelationalSource, out: list[dict]) -> dict[str, str] | None:
    """column name (lower-case) -> SQL type ('' if unknown) of the map's logical table."""
    if tm.table_name:
        t = src.schema().table(tm.table_name)
        if t is None:
            out.append(_f("error", "unknown-table", tm,
                          f"table {tm.table_name!r} is not in source {src.id!r}"))
            return None
        return {c.name.lower(): c.type for c in t.columns}
    try:
        check_select(tm.sql_query)
        cols = src.columns_of(tm.sql_query)
    except UnsafeSQL as e:
        out.append(_f("error", "bad-sql", tm, str(e)))
        return None
    except Exception as e:
        out.append(_f("error", "bad-sql", tm, f"query does not run: {e}"))
        return None
    types: dict[str, str] = {}
    m = re.search(r'(?is)\bfrom\s+("?[A-Za-z_][\w$]*"?)', tm.sql_query)  # best-effort types
    base = src.schema().table(m.group(1)) if m else None
    for c in cols:
        bc = base.column(c) if base else None
        types[c.lower()] = bc.type if bc else ""
    return types


def _check_term(tm: TriplesMap, t: TermMap, cols: dict | None, out: list[dict], where: str,
                subject: bool = False) -> None:
    if t.template is not None and subject and not t.columns():
        out.append(_f("warning", "no-placeholder", tm,
                      f"{where} template {t.template!r} has no column placeholder: every row "
                      "maps to the same IRI"))
    if cols is None:
        return
    for c in t.columns():
        if unquote(c).lower() not in cols:
            code = "unknown-column" if t.column is not None else "unknown-placeholder"
            out.append(_f("error", code, tm, f"{where}: column {c!r} is not in the logical table",
                          column=c))


def validate(maps: list[TriplesMap], ontology: Graph, sources: dict[str, RelationalSource],
             *, default_source: str | None = None) -> list[dict]:
    out: list[dict] = []
    by_iri = {m.iri: m for m in maps}
    for tm in maps:
        sid = tm.source or default_source or (next(iter(sources)) if len(sources) == 1 else None)
        src = sources.get(sid) if sid else None
        if src is None:
            out.append(_f("error", "unknown-source", tm,
                          f"no registered database {sid!r}" if sid else
                          "the map names no database and several are registered"))
        cols = _columns(tm, src, out) if src else None
        _check_term(tm, tm.subject, cols, out, "subject", subject=True)
        if tm.subject.kind(subject=True) == "literal":
            out.append(_f("error", "property-kind", tm, "a subject cannot be a literal"))
        for c in tm.classes:
            ci = URIRef(c)
            if "class" not in _kind_of(ontology, ci):
                out.append(_f("error", "unknown-class", tm,
                              f"{local_name(c)} is not a class of the ontology", term=c))
            elif _deprecated(ontology, ci):
                out.append(_f("warning", "deprecated-term", tm,
                              f"class {local_name(c)} is deprecated", term=c))
        for p in tm.poms:
            pi = URIRef(p.predicate)
            builtin = p.predicate.startswith(_BUILTIN)
            kinds = _kind_of(ontology, pi)
            if not builtin and not kinds:
                out.append(_f("error", "unknown-property", tm,
                              f"{local_name(p.predicate)} is not declared in the ontology",
                              term=p.predicate))
            elif _deprecated(ontology, pi):
                out.append(_f("warning", "deprecated-term", tm,
                              f"property {local_name(p.predicate)} is deprecated",
                              term=p.predicate))
            yields = "iri" if p.ref is not None else p.object.kind()
            if "data" in kinds and "object" not in kinds and yields != "literal":
                out.append(_f("error", "property-kind", tm,
                              f"{local_name(p.predicate)} is a datatype property but the map "
                              "produces IRIs (use rr:column / a literal)", term=p.predicate))
            if "object" in kinds and "data" not in kinds and yields == "literal":
                out.append(_f("error", "property-kind", tm,
                              f"{local_name(p.predicate)} is an object property but the map "
                              "produces literals (use rr:template / a parent map)",
                              term=p.predicate))
            if p.object is not None:
                _check_term(tm, p.object, cols, out, f"object of {local_name(p.predicate)}")
                if p.object.column is not None and cols is not None and yields == "literal":
                    cat = sql_category(cols.get(unquote(p.object.column).lower(), ""))
                    dt = p.object.datatype or next(
                        (str(r) for r in ontology.objects(pi, RDFS.range)
                         if str(r).startswith(str(XSD))), None)
                    ok = _COMPATIBLE.get(cat) if cat else None
                    if dt and ok is not None and dt.startswith(str(XSD)) \
                            and dt[len(str(XSD)):] not in ok:
                        out.append(_f("warning", "datatype-mismatch", tm,
                                      f"column {p.object.column!r} ({cat}) mapped to "
                                      f"xsd:{dt[len(str(XSD)):]} for {local_name(p.predicate)}",
                                      column=p.object.column))
            else:
                parent = by_iri.get(p.ref.parent)
                if parent is None:
                    out.append(_f("error", "unknown-parent", tm,
                                  f"parent triples map {p.ref.parent} does not exist"))
                    continue
                same = (parent.table_name or parent.sql_query) == (tm.table_name or tm.sql_query)
                if not p.ref.joins and not same:
                    out.append(_f("error", "join-required", tm,
                                  f"parent {parent.id} has another logical table: add a "
                                  "join condition"))
                if cols is not None:
                    for child, _ in p.ref.joins:
                        if unquote(child).lower() not in cols:
                            out.append(_f("error", "unknown-column", tm,
                                          f"join child column {child!r} is not in the "
                                          "logical table", column=child))
                psrc = sources.get(parent.source or sid or "") if (parent.source or sid) else None
                if psrc is not None and p.ref.joins:
                    pcols = _columns(parent, psrc, [])
                    if pcols is not None:
                        for _, par in p.ref.joins:
                            if unquote(par).lower() not in pcols:
                                out.append(_f("error", "unknown-column", tm,
                                              f"join parent column {par!r} is not in the "
                                              f"logical table of {parent.id}", column=par))
    # IRI spaces: same constant prefix, different templates
    spaces: dict[str, set[str]] = {}
    owners: dict[str, list[str]] = {}
    for tm in maps:
        t = tm.subject.template
        if not t or "{" not in t:
            continue
        prefix = t.split("{", 1)[0]
        shape = re.sub(r"\{[^}]*\}", "{}", t)
        spaces.setdefault(prefix, set()).add(shape)
        owners.setdefault(prefix, []).append(tm.iri)
    for prefix, shapes in spaces.items():
        if len(shapes) > 1:
            out.append(_f("warning", "iri-space-clash", None,
                          f"maps {sorted(owners[prefix])} mint subjects under {prefix!r} with "
                          f"different template shapes {sorted(shapes)}"))
    return out


def coverage(maps: list[TriplesMap], ontology: Graph, namespace: str | None = None) -> dict:
    """Which classes / properties of the ontology (optionally one namespace) are mapped."""
    used = set()
    for m in maps:
        used |= m.terms()

    def pick(*types) -> list[str]:
        return sorted({str(s) for t in types for s in ontology.subjects(RDF.type, t)
                       if isinstance(s, URIRef) and not _deprecated(ontology, s)
                       and (namespace is None or str(s).startswith(namespace))})
    classes = pick(OWL.Class)
    props = pick(OWL.ObjectProperty, OWL.DatatypeProperty)
    mc = [c for c in classes if c in used]
    mp = [p for p in props if p in used]
    total = len(classes) + len(props)
    return {"classes": {"mapped": mc, "unmapped": [c for c in classes if c not in used]},
            "properties": {"mapped": mp, "unmapped": [p for p in props if p not in used]},
            "ratio": round((len(mc) + len(mp)) / total, 3) if total else 1.0}


def impact(maps: list[TriplesMap], entities: list[str]) -> list[dict]:
    """Triples maps affected by renaming/deleting *entities*, and where they use them."""
    want = set(entities)
    out = []
    for m in maps:
        uses = []
        for c in m.classes:
            if c in want:
                uses.append({"entity": c, "where": "rr:class"})
        for p in m.poms:
            if p.predicate in want:
                uses.append({"entity": p.predicate, "where": "rr:predicate"})
            if p.object is not None:
                if p.object.datatype in want:
                    uses.append({"entity": p.object.datatype, "where": "rr:datatype"})
                if p.object.constant in want:
                    uses.append({"entity": p.object.constant, "where": "rr:constant"})
        if m.subject.constant in want:
            uses.append({"entity": m.subject.constant, "where": "subject rr:constant"})
        if uses:
            out.append({"map": m.iri, "id": m.id, "uses": uses})
    return out


def rename_in_mappings(g: Graph, old: URIRef, new: URIRef) -> tuple[list[tuple], list[tuple]]:
    """(removals, additions) that rewrite every IRI-valued use of *old* in the mappings
    graph to *new* — triples maps and alignment cells alike. Literals (templates, SQL)
    are never rewritten: they hold data IRIs and column names, not ontology terms."""
    rem, add = [], []
    for t in set(g.triples((old, None, None))) | set(g.triples((None, old, None))) \
            | set(g.triples((None, None, old))):
        s, p, o = t
        if isinstance(o, Literal) and s != old and p != old:
            continue
        rem.append(t)
        add.append((new if s == old else s, new if p == old else p, new if o == old else o))
    return rem, add
