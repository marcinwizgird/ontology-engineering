"""Mapping patterns: the unit of authoring above R2RML (Mapping Studio design, §6–§7).

A *pattern* is a recurring relational shape with a known R2RML rendering. People and the
mapping agent choose patterns and fill in their parameters; :func:`compile_map` writes the
triples maps. The R2RML in the ``mappings`` graph stays the single source of truth:
:func:`lift` reads a triples map back into a pattern and its parameters, and succeeds only
if compiling those parameters reproduces the map's triples *exactly* — anything else is a
**custom** map, shown and edited field by field, never rewritten.

**IRI policy.** An :class:`EntityDef` is one identity: a base IRI, a path segment and the
key column(s) of its root table, so its template is ``<base><path>/{"<key>"}``. Every
subject map and every IRI-valued object map is compiled from an EntityDef, never typed.
Tables in a hierarchy share their root's EntityDef (a subclass row and its parent row are
the same IRI); a map on a member table names its own key column with ``subject_column``.

**Map parameters** are the dict form of the SPARQL-2-SQL PoC's ``mapping-spec.yaml``
(``id``, ``table``, ``subject``, ``subject_column``, ``class``, ``filter``,
``properties``), with full IRIs instead of CURIEs (:mod:`.spec` converts). Two optional
extras carry what the spec cannot: ``schema`` when a map's schema differs from the
default, and ``iri`` / ``source`` / ``label`` from the stored map.

Catalogue (R0: P01–P08)::

    P01 entity table          typed map on the entity's root table
    P02 subclass table        typed map on a member table of the entity (PK = FK)
    P03 discriminator         typed map over rr:sqlQuery ... WHERE "col" = 'value'
    P04 forward link          class-less map of links on the entity's own table
    P05 inverse link          class-less map keyed by an FK; the link points back to the
                              table's own entity (ACCOUNT.CUST_ID: Customer hasAccount Account)
    P06 join table (m:n)      class-less map keyed by one FK, linking to another FK's entity
    P07 associative entity    typed map on a table with two or more FKs and own attributes
    P08 code / lookup table   typed map whose properties are only labels / notations
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from ..core.namespaces import SIP
from .r2rml import PredicateObjectMap, TermMap, TriplesMap, placeholders
from .source import Schema, unquote

__all__ = ["EntityDef", "PATTERNS", "compile_map", "compile_pattern", "lift", "lift_all",
           "classify", "infer_entities", "detect", "entity_triples", "parse_entities",
           "PatternError", "LABEL_PREDICATES", "entity_iri"]

PATTERNS = {
    "P01": "entity table",
    "P02": "subclass table",
    "P03": "discriminator subclass",
    "P04": "forward link",
    "P05": "inverse link",
    "P06": "join table (m:n)",
    "P07": "associative entity",
    "P08": "code / lookup table",
}

LABEL_PREDICATES = {str(RDFS.label), str(SKOS.prefLabel), str(SKOS.altLabel),
                    str(SKOS.notation), str(SKOS.definition)}


class PatternError(ValueError):
    """Pattern parameters that cannot be compiled."""


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _keys(k) -> list[str]:
    return [k] if isinstance(k, str) else list(k)


@dataclass
class EntityDef:
    """One identity of the IRI policy: ``<base><path>/{"<key>"}``."""

    name: str
    path: str
    table: str
    key: list[str]
    base: str

    def __post_init__(self) -> None:
        self.key = _keys(self.key)
        if not self.key:
            raise PatternError(f"entity {self.name!r} needs a key column")

    @property
    def prefix(self) -> str:
        return f"{self.base}{self.path}/"

    def template(self, columns=None) -> str:
        return self.prefix + "/".join("{" + _q(c) + "}" for c in _keys(columns or self.key))

    def columns_of(self, template: str) -> list[str] | None:
        """The key columns a template of this entity uses, or None if it is not one."""
        if not template.startswith(self.prefix):
            return None
        rest = template[len(self.prefix):]
        cols = placeholders(rest)
        return cols if cols and self.template(cols) == template else None

    def as_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "table": self.table,
                "key": self.key[0] if len(self.key) == 1 else list(self.key), "base": self.base}


# --------------------------------------------------------------------------- #
# EntityDefs in the mappings graph
# --------------------------------------------------------------------------- #

def entity_iri(project: str, name: str) -> URIRef:
    # Not under the r2rml# namespace: map_nodes() treats "<map>/..." IRIs as map nodes.
    return URIRef(f"urn:sip:p:{project}:entity#{name}")


def entity_triples(project: str, e: EntityDef) -> list[tuple]:
    me = entity_iri(project, e.name)
    return [(me, RDF.type, SIP.EntityDef), (me, SIP.entityName, Literal(e.name)),
            (me, SIP.pathSegment, Literal(e.path)), (me, SIP.rootTable, Literal(e.table)),
            (me, SIP.keyColumns, Literal(",".join(e.key))), (me, SIP.baseIRI, Literal(e.base))]


def parse_entities(g: Graph) -> dict[str, EntityDef]:
    out = {}
    for s in g.subjects(RDF.type, SIP.EntityDef):
        v = {p: str(g.value(s, p)) for p in (SIP.entityName, SIP.pathSegment, SIP.rootTable,
                                             SIP.keyColumns, SIP.baseIRI)}
        e = EntityDef(v[SIP.entityName], v[SIP.pathSegment], v[SIP.rootTable],
                      v[SIP.keyColumns].split(","), v[SIP.baseIRI])
        out[e.name] = e
    return out


# --------------------------------------------------------------------------- #
# compile
# --------------------------------------------------------------------------- #

def _table_ref(m: dict, schema: str | None) -> str:
    s = m.get("schema", schema)
    return f"{_q(s)}.{_q(m['table'])}" if s else _q(m["table"])


def _columns_used(m: dict, entities: dict[str, EntityDef]) -> list[str]:
    cols = _keys(m.get("subject_column") or entities[m["subject"]].key)
    for p in m.get("properties", []):
        cols += _keys(p.get("column") or entities[p["ref"]].key) if "ref" in p else [p["column"]]
    return list(dict.fromkeys(cols))


def _filter_sql(m: dict, entities, schema: str | None) -> str:
    cols = ", ".join(_q(c) for c in _columns_used(m, entities))
    where = " AND ".join(f"{_q(c)} = '{str(v).replace(chr(39), chr(39) * 2)}'"
                         for c, v in m["filter"].items())
    return f"SELECT {cols} FROM {_table_ref(m, schema)} WHERE {where}"


def compile_map(m: dict, entities: dict[str, EntityDef], *, schema: str | None = None,
                mint: Callable[[str], str] = lambda i: i) -> TriplesMap:
    """One map in spec form -> a triples map (the PoC generator's conventions)."""
    for k in ("id", "table", "subject"):
        if not m.get(k):
            raise PatternError(f"map {m.get('id', '?')!r}: missing {k!r}")
    ent = entities.get(m["subject"])
    if ent is None:
        raise PatternError(f"map {m['id']!r}: unknown entity {m['subject']!r}")
    if not m.get("class") and not m.get("properties"):
        raise PatternError(f"map {m['id']!r} produces no triples (no class, no properties)")
    poms = []
    for p in m.get("properties", []):
        if "ref" in p:
            ref = entities.get(p["ref"])
            if ref is None:
                raise PatternError(f"map {m['id']!r}: unknown entity {p['ref']!r}")
            poms.append(PredicateObjectMap(p["predicate"], object=TermMap(
                template=ref.template(p.get("column")))))
        elif "column" in p:
            poms.append(PredicateObjectMap(p["predicate"], object=TermMap(
                column=_q(p["column"]), datatype=p.get("datatype"))))
        else:
            raise PatternError(f"map {m['id']!r}: a property needs 'column' or 'ref'")
    table = sql = None
    if m.get("filter"):
        sql = _filter_sql(m, entities, schema)
    else:
        table = _table_ref(m, schema)
    return TriplesMap(m.get("iri") or mint(m["id"]),
                      TermMap(template=ent.template(m.get("subject_column"))), table, sql,
                      [m["class"]] if m.get("class") else [], poms, m.get("source"),
                      m.get("label"))


def compile_pattern(pattern: str, params: dict, entities: dict[str, EntityDef], *,
                    schema: str | None = None,
                    mint: Callable[[str], str] = lambda i: i) -> list[TriplesMap]:
    """A pattern with its parameters -> triples maps (some patterns yield several).

    Every pattern accepts a single map in spec form. Two have a multi-map form:
    P03 ``{id, table, subject, column, cases: {value: {id, class}}, properties}`` (one
    map per discriminator value) and P07 ``{...entity map..., links: [{id, subject,
    subject_column, predicate}]}`` (the associative entity plus one P05 link per side).
    """
    if pattern not in PATTERNS:
        raise PatternError(f"unknown pattern {pattern!r}; known: {sorted(PATTERNS)}")
    if pattern == "P03" and "cases" in params:
        maps = [dict({k: v for k, v in params.items() if k not in ("cases", "column", "id")},
                     id=c["id"], **{"class": c["class"]}, filter={params["column"]: value})
                for value, c in params["cases"].items()]
    elif pattern == "P07" and "links" in params:
        base = {k: v for k, v in params.items() if k != "links"}
        maps = [base] + [{"id": ln["id"], "table": params["table"], "subject": ln["subject"],
                          "subject_column": ln["subject_column"],
                          "properties": [{"predicate": ln["predicate"],
                                          "ref": params["subject"]}]}
                         for ln in params["links"]]
    else:
        maps = [params]
    out = [compile_map(m, entities, schema=schema, mint=mint) for m in maps]
    for m, tm in zip(maps, out):
        got = classify(m, entities)
        if pattern in ("P01", "P02", "P03", "P04", "P05", "P06") and got != pattern \
                and not (pattern == "P07" and got == "P05"):
            raise PatternError(f"map {m['id']!r} is a {got} ({PATTERNS[got]}), not a "
                               f"{pattern} ({PATTERNS[pattern]})")
    return out


# --------------------------------------------------------------------------- #
# classify / lift
# --------------------------------------------------------------------------- #

def classify(m: dict, entities: dict[str, EntityDef], schema: Schema | None = None) -> str:
    """The pattern a map in spec form instantiates. P07 needs the schema (FK count)."""
    ent = entities[m["subject"]]
    props = m.get("properties", [])
    same_table = m["table"].lower() == (ent.table or "").lower()
    if m.get("class"):
        if m.get("filter"):
            return "P03"
        if not same_table:
            return "P02"
        if props and all(p.get("predicate") in LABEL_PREDICATES for p in props):
            return "P08"
        t = schema.table(m["table"]) if schema else None
        if t is not None and len(_entity_refs(t, schema)) >= 2:
            return "P07"
        return "P01"
    own_key = _keys(m.get("subject_column") or ent.key) == ent.key
    if same_table and own_key:
        return "P04"
    if any("ref" in p and (entities[p["ref"]].table or "").lower() == m["table"].lower()
           for p in props):
        return "P05"
    return "P06"


def _is_code_table(t) -> bool:
    """A code list: at most three columns, one text primary key, no foreign keys."""
    if t is None or len(t.primary_key) != 1 or len(t.columns) > 3 or t.foreign_keys:
        return False
    col = t.column(t.primary_key[0])
    return col is not None and any(x in col.type for x in ("CHAR", "TEXT", "STRING"))


def _entity_refs(t, schema: Schema) -> set[str]:
    """Tables *t* references by foreign key, other than itself and code lists."""
    return {f.ref_table.lower() for f in t.foreign_keys
            if f.ref_table.lower() != t.name.lower()
            and not _is_code_table(schema.table(f.ref_table))}


_SQL = re.compile(r'^SELECT (?P<cols>.+?) FROM (?P<table>.+?) WHERE (?P<where>.+)$', re.S)
_COND = re.compile(r'^"((?:[^"]|"")+)" = \'((?:[^\']|\'\')*)\'$')
_QUOTED = re.compile(r'^(?:"((?:[^"]|"")+)"\.)?"((?:[^"]|"")+)"$')


def _split_table(ref: str) -> tuple[str | None, str] | None:
    m = _QUOTED.match(ref.strip())
    if not m:
        return None
    s = m.group(1).replace('""', '"') if m.group(1) else None
    return s, m.group(2).replace('""', '"')


def _entity_of(template: str, entities: dict[str, EntityDef]):
    for e in entities.values():
        cols = e.columns_of(template)
        if cols is not None:
            return e, cols
    return None, None


def _params(tm: TriplesMap, entities: dict[str, EntityDef], schema: str | None) -> dict | None:
    """Best-effort reverse compilation; :func:`lift` verifies it."""
    if tm.subject.template is None or len(tm.classes) > 1:
        return None
    ent, scols = _entity_of(tm.subject.template, entities)
    if ent is None:
        return None
    m: dict = {"id": tm.id, "iri": tm.iri}
    order: list[str] | None = None
    if tm.table_name is not None:
        st = _split_table(tm.table_name)
        if st is None:
            return None
        s, m["table"] = st
    else:
        q = _SQL.match(tm.sql_query.strip())
        if not q:
            return None
        st = _split_table(q.group("table"))
        if st is None:
            return None
        s, m["table"] = st
        flt = {}
        for cond in q.group("where").split(" AND "):
            c = _COND.match(cond.strip())
            if not c:
                return None
            flt[c.group(1).replace('""', '"')] = c.group(2).replace("''", "'")
        m["filter"] = flt
        order = [unquote(c) for c in q.group("cols").split(", ")]
    if s != schema:
        m["schema"] = s
    m["subject"] = ent.name
    # link maps on another table always name the column they key on, as the PoC spec does
    if scols != ent.key or (not tm.classes and m["table"].lower() != ent.table.lower()):
        m["subject_column"] = scols[0] if len(scols) == 1 else scols
    if tm.classes:
        m["class"] = tm.classes[0]
    props = []
    for p in tm.poms:
        o = p.object
        if o is None or o.constant is not None or o.language or o.term_type:
            return None
        if o.template is not None:
            ref, rcols = _entity_of(o.template, entities)
            if ref is None or o.datatype:
                return None
            d = {"predicate": p.predicate, "ref": ref.name}
            if rcols != ref.key:
                d["column"] = rcols[0] if len(rcols) == 1 else rcols
        else:
            d = {"predicate": p.predicate, "column": unquote(o.column)}
            if o.datatype:
                d["datatype"] = o.datatype
        props.append(d)
    if order is not None:       # the SELECT list fixes the property order
        def pos(d):
            c = _keys(d.get("column") or entities[d["ref"]].key)[0] if "ref" in d else d["column"]
            return order.index(c) if c in order else len(order)
        props.sort(key=pos)
    if props:
        m["properties"] = props
    for k in ("source", "label"):
        if getattr(tm, k):
            m[k] = getattr(tm, k)
    return m


def lift(tm: TriplesMap, entities: dict[str, EntityDef], *, schema: str | None = None,
         db_schema: Schema | None = None) -> tuple[str, dict] | None:
    """``(pattern, params)`` if a pattern reproduces *tm* exactly, else ``None`` (custom)."""
    m = _params(tm, entities, schema)
    if m is None:
        return None
    try:
        again = compile_map(m, entities, schema=schema)
    except PatternError:
        return None
    if set(again.triples()) != set(tm.triples()):
        return None
    return classify(m, entities, db_schema), m


def lift_all(maps: list[TriplesMap], entities: dict[str, EntityDef], *,
             schema: str | None = None, db_schema: Schema | None = None) -> dict:
    """Pattern view of a whole mapping: per map its pattern (or ``custom``) + a summary."""
    rows, counts = [], {}
    for tm in maps:
        got = lift(tm, entities, schema=schema, db_schema=db_schema)
        pid = got[0] if got else "custom"
        counts[pid] = counts.get(pid, 0) + 1
        rows.append({"map": tm.iri, "id": tm.id, "pattern": pid,
                     "name": PATTERNS.get(pid, "custom map"),
                     "params": got[1] if got else None})
    n = len(maps)
    return {"maps": rows, "counts": dict(sorted(counts.items())),
            "custom_share": round(counts.get("custom", 0) / n, 4) if n else 0.0}


# --------------------------------------------------------------------------- #
# inferring an IRI policy from existing maps (imported R2RML)
# --------------------------------------------------------------------------- #

_TPL = re.compile(r'^(?P<prefix>[^{}]*/)(?P<keys>\{"[^"{}]+"\}(?:/\{"[^"{}]+"\})*)$')


def infer_entities(maps: list[TriplesMap]) -> tuple[dict[str, EntityDef], str | None]:
    """EntityDefs and the default schema implied by maps that follow the conventions
    (``<base><path>/{"KEY"}`` templates, quoted ``"SCHEMA"."TABLE"`` names). The root
    table of an entity is the typed table named like its path, else the first typed one;
    its key is the column that table's subject template uses."""
    typed: dict[str, list[tuple[str, list[str]]]] = {}
    seen: list[str] = []
    schemas: dict[str | None, int] = {}

    def table_of(tm):
        ref = tm.table_name
        if ref is None:
            q = _SQL.match(tm.sql_query.strip())
            ref = q.group("table") if q else None
        return _split_table(ref) if ref else None

    for tm in maps:
        st = table_of(tm)
        if st:
            schemas[st[0]] = schemas.get(st[0], 0) + 1
        tpls = [(tm.subject.template, True)] + [(p.object.template, False) for p in tm.poms
                                                 if p.object and p.object.template]
        for tpl, is_subject in tpls:
            mt = _TPL.match(tpl or "")
            if not mt:
                continue
            prefix = mt.group("prefix")
            if prefix not in seen:
                seen.append(prefix)
            if is_subject and tm.classes and st:
                typed.setdefault(prefix, []).append((st[1], placeholders(mt.group("keys"))))
    out: dict[str, EntityDef] = {}
    for prefix in seen:
        base, path = prefix[:-1].rsplit("/", 1)
        squash = re.sub(r"[^a-z0-9]", "", path.lower())
        cands = sorted(typed.get(prefix, []))
        root = next((c for c in cands if re.sub(r"[^a-z0-9]", "", c[0].lower()) == squash),
                    cands[0] if cands else None)
        name = path if path not in out else f"{path}_{len(out)}"
        if root:
            out[name] = EntityDef(name, path, root[0], root[1], base + "/")
        else:                                  # only ever an object: key from first use
            tpl = next(p.object.template for tm in maps for p in tm.poms
                       if p.object and p.object.template and p.object.template.startswith(prefix))
            out[name] = EntityDef(name, path, "", placeholders(tpl[len(prefix):]), base + "/")
    default = max(schemas, key=schemas.get) if schemas else None
    return out, default


# --------------------------------------------------------------------------- #
# detectors (schema shapes; deliberately simple, see suggest.py for scoring)
# --------------------------------------------------------------------------- #

def detect(schema: Schema) -> list[dict]:
    """Candidate patterns per table from keys and foreign keys alone."""
    out = []
    referenced = {f.ref_table.lower() for t in schema.tables.values() for f in t.foreign_keys}
    for name, t in sorted(schema.tables.items()):
        pk = t.primary_key
        fks = t.foreign_keys
        fk_cols = {c for f in fks for c in f.columns}
        parent = next((f for f in fks if pk and f.columns == pk), None)
        others = [c.name for c in t.columns if c.name not in fk_cols and c.name not in pk]
        if parent is not None:
            out.append({"pattern": "P02", "table": name, "parent": parent.ref_table,
                        "reason": "primary key is a foreign key to the parent's key"})
        elif len(fks) >= 2 and pk and set(pk) <= fk_cols and not others:
            out.append({"pattern": "P06", "table": name,
                        "sides": [f.ref_table for f in fks[:2]],
                        "reason": "primary key is exactly two foreign keys, no attributes"})
        elif len(_entity_refs(t, schema)) >= 2 and others:
            out.append({"pattern": "P07", "table": name,
                        "sides": sorted(_entity_refs(t, schema)),
                        "reason": "two or more foreign keys plus own attributes"})
        elif name.lower() in referenced and _is_code_table(t):
            out.append({"pattern": "P08", "table": name,
                        "reason": "small table referenced by foreign keys (code list)"})
        elif pk:
            out.append({"pattern": "P01", "table": name, "reason": "table with a primary key"})
        for f in fks:
            if parent is None or f is not parent:
                out.append({"pattern": "P04", "table": name, "column": f.columns,
                            "target": f.ref_table, "reason": "foreign key on the table"})
    return out

