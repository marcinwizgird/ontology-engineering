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

Conformance rules merged from the SPARQL-2-SQL PoC (``tools/check_mappings.py``); an IRI
*family* is a template's constant prefix (``https://…/data/customer/``):

=====================  =============================================================
M04                    a typed subject's template is keyed by its table's primary key
M05                    an IRI used outside its typing tables follows a foreign key to
                       the key those tables' maps use
M06                    every IRI family is typed by at least one map
M10                    subjects / objects compatible with rdfs:domain / rdfs:range
M11                    subject template columns are NOT NULL
M12                    coverage: tables and columns no map uses (info)
=====================  =============================================================

Data checks on a sample (``data_limit`` rows per logical table; ``None`` skips them):

=====================  =============================================================
D1                     the logical table returns rows
D2                     rows whose subject key is NULL (they produce no subject)
D3                     a typed map's subject key repeats within the sample
D4                     IRI links whose key has no row in the typing tables (orphans)
=====================  =============================================================
"""

from __future__ import annotations

import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..owl.rendering import local_name
from .r2rml import TermMap, TriplesMap
from .materialise import logical_sql
from .source import RelationalSource, Table, UnsafeSQL, check_select, unquote

__all__ = ["validate", "conformance", "data_checks", "coverage", "impact",
           "rename_in_mappings"]

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
             *, default_source: str | None = None, data_limit: int | None = 1000,
             unused: bool = True) -> list[dict]:
    """Every check: the static ones below, the PoC's conformance rules (:func:`conformance`)
    and, unless ``data_limit`` is None, the data checks (:func:`data_checks`)."""
    out = _static(maps, ontology, sources, default_source)
    out += conformance(maps, ontology, sources, default_source=default_source, unused=unused)
    if data_limit is not None:
        out += data_checks(maps, sources, default_source=default_source, limit=data_limit)
    return out


def _static(maps: list[TriplesMap], ontology: Graph, sources: dict[str, RelationalSource],
            default_source: str | None) -> list[dict]:
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


# --------------------------------------------------------------------------- #
# conformance rules (M04-M06, M10-M12) and data checks (D1-D4)
# --------------------------------------------------------------------------- #

def _source_of(tm: TriplesMap, sources: dict, default_source: str | None):
    sid = tm.source or default_source or (next(iter(sources)) if len(sources) == 1 else None)
    return sources.get(sid) if sid else None


_FROM = re.compile(r'(?is)\bfrom\s+((?:"(?:[^"]|"")+"|[A-Za-z_][\w$]*)'
                   r'(?:\s*\.\s*(?:"(?:[^"]|"")+"|[A-Za-z_][\w$]*))?)')


def _base_table(tm: TriplesMap, src: RelationalSource | None) -> Table | None:
    """The table a map reads: its rr:tableName, or the FROM table of a one-table query."""
    if src is None:
        return None
    name = tm.table_name
    if name is None:
        m = _FROM.search(tm.sql_query)
        if not m or re.search(r"(?i)\bjoin\b", tm.sql_query):
            return None
        name = m.group(1)
    return src.schema().table(name)


def family(template: str) -> str:
    """An IRI family: the constant prefix of a template."""
    return template.split("{", 1)[0]


def _cols(t: TermMap) -> tuple[str, ...]:
    return tuple(unquote(c).lower() for c in t.columns())


def _ancestors(g: Graph):
    """class -> itself and its ancestors (rdfs:subClassOf, owl:equivalentClass)."""
    up: dict = {}
    for s, o in g.subject_objects(RDFS.subClassOf):
        up.setdefault(s, set()).add(o)
    for s, o in g.subject_objects(OWL.equivalentClass):
        up.setdefault(s, set()).add(o)
        up.setdefault(o, set()).add(s)
    memo: dict = {}

    def close(c):
        if c not in memo:
            seen, todo = {c}, [c]
            while todo:
                for p in up.get(todo.pop(), ()):
                    if p not in seen:
                        seen.add(p)
                        todo.append(p)
            memo[c] = seen
        return memo[c]
    return close


def conformance(maps: list[TriplesMap], ontology: Graph, sources: dict[str, RelationalSource],
                *, default_source: str | None = None, unused: bool = True) -> list[dict]:
    """The SPARQL-2-SQL PoC's rules M04-M06 and M10-M12 over SIP's model."""
    out: list[dict] = []
    tables = {tm.iri: _base_table(tm, _source_of(tm, sources, default_source)) for tm in maps}
    typing: dict[str, dict[str, tuple]] = {}       # family -> {table: subject columns}
    fam_classes: dict[str, set] = {}
    for tm in maps:
        if tm.classes and tm.subject.template:
            f, t = family(tm.subject.template), tables[tm.iri]
            typing.setdefault(f, {})[(t.name if t else tm.table_name or tm.iri).lower()] = \
                _cols(tm.subject)
            fam_classes.setdefault(f, set()).update(URIRef(c) for c in tm.classes)
    close = _ancestors(ontology)

    def subsumed(classes: set, target) -> bool:
        return target == OWL.Thing or any(target in close(c) for c in classes)

    def link(tm: TriplesMap, tpl: TermMap, t: Table, role: str) -> None:
        f = family(tpl.template)
        owners = typing.get(f)
        if not owners or owners.get(t.name.lower()) == _cols(tpl):
            return                          # M06 reports untyped families once
        cols = [unquote(c).lower() for c in tpl.columns()]
        fk = next((k for k in t.foreign_keys if [c.lower() for c in k.columns] == cols), None)
        if fk is None:
            out.append(_f("error", "M05", tm, f"{role} {f}... uses {cols}, which is not a "
                          f"foreign key of {t.name}"))
        elif owners.get(fk.ref_table.lower()) != tuple(c.lower() for c in fk.ref_columns):
            out.append(_f("error", "M05", tm, f"{role} {f}... follows {cols} -> "
                          f"{fk.ref_table}{fk.ref_columns}, not the key that table's maps use "
                          "for these IRIs"))

    by_iri = {m.iri: m for m in maps}
    for tm in maps:
        t = tables[tm.iri]
        if t is not None and tm.subject.template:
            pk = tuple(c.lower() for c in t.primary_key)
            if tm.classes and pk and set(_cols(tm.subject)) != set(pk):
                out.append(_f("error", "M04", tm, f"subject uses {list(_cols(tm.subject))}, "
                              f"not the primary key {t.primary_key} of {t.name}"))
            for c in _cols(tm.subject):
                col = t.column(c)
                if col is not None and col.nullable:
                    out.append(_f("warning", "M11", tm, f"subject column {col.name} is "
                                  "nullable: rows where it is NULL produce no subject",
                                  column=col.name))
            if not tm.classes:
                link(tm, tm.subject, t, "subject")
            for p in tm.poms:
                if p.object is not None and p.object.template and p.object.kind() == "iri":
                    link(tm, p.object, t, f"object of {local_name(p.predicate)}")
        subj = {URIRef(c) for c in tm.classes} | (
            fam_classes.get(family(tm.subject.template), set()) if tm.subject.template else set())
        for p in tm.poms:
            pi = URIRef(p.predicate)
            for d in ontology.objects(pi, RDFS.domain):
                if isinstance(d, URIRef) and subj and not subsumed(subj, d):
                    out.append(_f("error", "M10", tm, f"{local_name(p.predicate)} has domain "
                                  f"{local_name(d)}; the subject is only ever "
                                  f"{', '.join(sorted(local_name(c) for c in subj))}"))
            if p.ref is not None:
                parent = by_iri.get(p.ref.parent)
                objs = {URIRef(c) for c in parent.classes} if parent else set()
            elif p.object.template and p.object.kind() == "iri":
                objs = fam_classes.get(family(p.object.template), set())
            else:
                continue
            for r in ontology.objects(pi, RDFS.range):
                if isinstance(r, URIRef) and objs and not subsumed(objs, r):
                    out.append(_f("error", "M10", tm, f"{local_name(p.predicate)} has range "
                                  f"{local_name(r)}; the object is only ever "
                                  f"{', '.join(sorted(local_name(c) for c in objs))}"))
    fams = {family(tm.subject.template) for tm in maps if tm.subject.template} | {
        family(p.object.template) for tm in maps for p in tm.poms
        if p.object is not None and p.object.template and p.object.kind() == "iri"}
    for f in sorted(fams - set(typing)):
        out.append(_f("warning", "M06", None, f"IRIs {f}... are never given a class"))
    if unused:
        out += _unused(maps, sources, tables, default_source)
    return out


def _unused(maps, sources, tables, default_source) -> list[dict]:
    """M12: per source a map reads, the tables and columns no map uses."""
    used: dict[tuple[str, str], set[str]] = {}
    for tm in maps:
        src, t = _source_of(tm, sources, default_source), tables[tm.iri]
        if src is None or t is None:
            continue
        cols = set(_cols(tm.subject))
        for p in tm.poms:
            cols |= set(_cols(p.object)) if p.object is not None else {
                unquote(c).lower() for c, _ in p.ref.joins}
        if tm.sql_query:                    # filter columns count as used
            low = tm.sql_query.lower()
            cols |= {c.name.lower() for c in t.columns
                     if re.search(rf'(?<![\w$]){re.escape(c.name.lower())}(?![\w$])', low)}
        used.setdefault((src.id, t.name), set()).update(cols)
    out = []
    for sid in sorted({k[0] for k in used}):
        for name, t in sorted(sources[sid].schema().tables.items()):
            u = used.get((sid, name))
            if u is None:
                out.append(_f("info", "M12", None, f"table {name} ({sid}) is not mapped",
                              table=name))
                continue
            missing = [c.name for c in t.columns if c.name.lower() not in u]
            if missing:
                out.append(_f("info", "M12", None, f"{name} ({sid}): unmapped columns "
                              f"{', '.join(missing)}", table=name))
    return out


def data_checks(maps: list[TriplesMap], sources: dict[str, RelationalSource], *,
                default_source: str | None = None, limit: int = 1000) -> list[dict]:
    """D1-D4 on at most *limit* rows per logical table. A query that fails here is
    reported by the static checks (bad-sql, unknown-table), so it is skipped."""
    out: list[dict] = []
    typed: dict[str, list[tuple]] = {}        # family -> [(source, sql, key columns)]
    for tm in maps:
        src = _source_of(tm, sources, default_source)
        if tm.classes and tm.subject.template and src is not None:
            typed.setdefault(family(tm.subject.template), []).append(
                (src, logical_sql(tm, src), _cols(tm.subject)))
    known_cache: dict[str, set | None] = {}

    def known_keys(f: str, src) -> set | None:
        if f not in known_cache:
            keys: set | None = set()
            for s, sql, kc in typed.get(f, []):
                if s is not src:
                    continue
                try:
                    cols, rows = s.query(sql)
                except Exception:
                    keys = None
                    break
                low = [c.lower() for c in cols]
                if not all(c in low for c in kc):
                    keys = None
                    break
                ix = [low.index(c) for c in kc]
                keys |= {tuple(r[i] for i in ix) for r in rows}
            known_cache[f] = keys
        return known_cache[f]

    for tm in maps:
        src = _source_of(tm, sources, default_source)
        if src is None:
            continue
        try:
            cols, rows = src.query(logical_sql(tm, src), limit=limit)
        except Exception:
            continue
        if not rows:
            out.append(_f("warning", "D1", tm, "the logical table returns no rows"))
            continue
        idx = {c.lower(): i for i, c in enumerate(cols)}

        def key(row, t: TermMap):
            ix = [idx.get(c) for c in _cols(t)]
            return None if not ix or None in ix else tuple(row[i] for i in ix)
        keys = [key(r, tm.subject) for r in rows]
        nulls = sum(k is not None and None in k for k in keys)
        if nulls:
            out.append(_f("warning", "D2", tm, f"{nulls} of {len(rows)} sampled rows have a "
                          "NULL subject key and produce no subject",
                          rate=round(nulls / len(rows), 4)))
        full = [k for k in keys if k is not None and None not in k]
        if tm.classes and len(set(full)) < len(full):
            out.append(_f("warning", "D3", tm, f"{len(full) - len(set(full))} repeated subject "
                          f"keys in {len(rows)} sampled rows: the template is not a key of "
                          "this logical table"))
        links = [tm.subject] if not tm.classes and tm.subject.template else []
        links += [p.object for p in tm.poms if p.object is not None and p.object.template
                  and p.object.kind() == "iri"]
        for t in links:
            f = family(t.template)
            if f not in typed:
                continue
            known = known_keys(f, src)
            if not known:
                continue
            vals = [k for k in (key(r, t) for r in rows) if k is not None and None not in k]
            orphans = [v for v in vals if v not in known]
            if orphans:
                out.append(_f("warning", "D4", tm, f"{len(orphans)} of {len(vals)} sampled "
                              f"links to {f}... have no typed row (e.g. {list(orphans[0])})",
                              rate=round(len(orphans) / len(vals), 4)))
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
