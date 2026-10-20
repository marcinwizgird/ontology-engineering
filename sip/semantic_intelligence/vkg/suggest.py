"""Mapping suggestions from a relational schema and the ontology — proposals only.

Lexical matching normalises both sides to a token list and a joined key:
``LISTEDSECURITY``, ``listed_security``, ``ListedSecurity`` and the label
"listed security" all become ``listedsecurity``; plural table names are singularised.
Ontology terms are matched on ``rdfs:label``, ``skos:prefLabel`` and the local name.

What is proposed (each with a score in [0, 1] and the reasons behind it):

* ``class``           table -> class (rr:class);
* ``iriTemplate``     subject IRI template from the primary key;
* ``datatypeProperty`` column -> datatype property (also tried as ``<table><column>``,
  so ``customers.name`` finds ``customerName``); domain agreement adds to the score;
* ``objectProperty``  foreign key column -> object property, domain/range aware: a
  property whose domain is the child class and range the parent class is proposed even
  without a lexical match; one in the opposite direction is proposed as ``inverse``;
* ``subclassTable``   a table whose primary key is also a foreign key to its parent's
  primary key: same subject IRIs as the parent, rr:class of the subclass;
* ``subClassOf``      the matching rdfs:subClassOf, as a *separate* proposal, when the
  ontology lacks it (an ontology edit is the modeller's decision, not the mapper's);
* ``discriminator``   a low-cardinality text column whose values name classes
  (``customer_type = 'CORPORATE'`` -> CorporateCustomer) -> an rr:sqlQuery logical table;
* ``triplesMap``      a draft map per matched table assembling the above, in the dict
  form ``mapping.addTriplesMap`` accepts.

Nothing here writes; the caller decides what to apply.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..owl.rendering import local_name
from .source import RelationalSource, Schema, Table

__all__ = ["tokens", "key", "suggest", "OntologyIndex"]

_TEXT_TYPES = ("CHAR", "CLOB", "TEXT", "STRING", "VARCHAR")


def tokens(s: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(s))
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", s) if t]


def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def key(s: str) -> str:
    toks = tokens(s)
    if toks:
        toks[-1] = _singular(toks[-1])
    return "".join(toks)


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


class OntologyIndex:
    """Classes and properties of the ontology with their lexical keys."""

    def __init__(self, g: Graph) -> None:
        self.g = g
        self.classes = sorted({c for t in (OWL.Class, RDFS.Class)
                               for c in g.subjects(RDF.type, t) if isinstance(c, URIRef)})
        self.data = sorted(p for p in g.subjects(RDF.type, OWL.DatatypeProperty)
                           if isinstance(p, URIRef))
        self.obj = sorted(p for p in g.subjects(RDF.type, OWL.ObjectProperty)
                          if isinstance(p, URIRef))
        self.keys = {e: self._keys(e) for e in self.classes + self.data + self.obj}

    def _keys(self, e: URIRef) -> set[str]:
        out = {key(local_name(e))}
        for p in (RDFS.label, SKOS.prefLabel):
            out |= {key(str(v)) for v in self.g.objects(e, p)}
        return {k for k in out if k}

    def best(self, candidates: list[URIRef], text_keys: list[str]) -> list[tuple[float, URIRef, str]]:
        out = []
        for e in candidates:
            best, why = 0.0, ""
            for k in self.keys.get(e, ()):
                for t in text_keys:
                    s = _sim(t, k)
                    if s > best:
                        best, why = s, f"'{t}' ~ '{k}'"
            out.append((best, e, why))
        return sorted(out, key=lambda x: (-x[0], str(x[1])))

    def domains(self, p: URIRef) -> set[URIRef]:
        return set(self.g.objects(p, RDFS.domain))

    def ranges(self, p: URIRef) -> set[URIRef]:
        return set(self.g.objects(p, RDFS.range))

    def is_subclass(self, sub: URIRef, sup: URIRef) -> bool:
        seen, todo = set(), [sub]
        while todo:
            c = todo.pop()
            if c == sup:
                return True
            if c in seen:
                continue
            seen.add(c)
            todo += [o for o in self.g.objects(c, RDFS.subClassOf) if isinstance(o, URIRef)]
            todo += [o for o in self.g.objects(c, OWL.equivalentClass) if isinstance(o, URIRef)]
        return False

    def above(self, c: URIRef) -> set[URIRef]:
        out, todo = set(), [c]
        while todo:
            x = todo.pop()
            if x in out:
                continue
            out.add(x)
            todo += [o for o in self.g.objects(x, RDFS.subClassOf) if isinstance(o, URIRef)]
        return out


def _xsd_for(sql_type: str) -> URIRef | None:
    t = sql_type.upper()
    if "INT" in t:
        return XSD.integer
    if any(x in t for x in ("DEC", "NUMERIC", "MONEY")):
        return XSD.decimal
    if any(x in t for x in ("REAL", "FLOA", "DOUB")):
        return XSD.double
    if "BOOL" in t:
        return XSD.boolean
    if "TIMESTAMP" in t or "DATETIME" in t:
        return XSD.dateTime
    if "DATE" in t:
        return XSD.date
    return None


def _template(base: str, table: Table, cols: list[str] | None = None) -> str:
    cols = cols or table.primary_key or [table.columns[0].name]
    slug = "-".join(tokens(table.name)) or table.name
    return f"{base}{slug}/" + "/".join(f"{{{c}}}" for c in cols)


def suggest(src: RelationalSource, ontology: Graph, *, data_base: str,
            threshold: float = 0.75, tables: list[str] | None = None,
            discriminators: bool = True) -> list[dict]:
    """Scored proposals for mapping *src* onto *ontology* (see module doc)."""
    schema: Schema = src.schema()
    ix = OntologyIndex(ontology)
    out: list[dict] = []
    chosen: dict[str, tuple[URIRef, float]] = {}
    templates: dict[str, str] = {}
    todo = [schema.tables[t] for t in sorted(schema.tables)
            if tables is None or t in tables or t.lower() in {x.lower() for x in tables}]

    # -- tables -> classes, IRI templates ------------------------------------ #
    for t in todo:
        templates[t.name] = _template(data_base, t)
        hits = [h for h in ix.best(ix.classes, [key(t.name)]) if h[0] >= threshold][:3]
        for score, c, why in hits:
            out.append({"kind": "class", "table": t.name, "term": str(c),
                        "score": round(score, 3), "reasons": [f"table name {why}"]})
        if hits:
            chosen[t.name] = (hits[0][1], hits[0][0])
        out.append({"kind": "iriTemplate", "table": t.name, "template": templates[t.name],
                    "score": 1.0 if t.primary_key else 0.4,
                    "reasons": ["from the primary key " + ", ".join(t.primary_key)]
                    if t.primary_key else ["no primary key: first column used, review"]})

    # -- subclass tables: PK is an FK to the parent's PK ------------------------ #
    for t in todo:
        for fk in t.foreign_keys:
            parent = schema.table(fk.ref_table)
            if not (t.primary_key and sorted(fk.columns) == sorted(t.primary_key)
                    and parent is not None and sorted(fk.ref_columns) == sorted(parent.primary_key)):
                continue
            ptemplate = templates.get(parent.name) or _template(data_base, parent)
            # the child's rows share the parent's subject IRIs: substitute child columns
            mapping = dict(zip(fk.ref_columns, fk.columns))
            tpl = ptemplate
            for pc, cc in mapping.items():
                tpl = tpl.replace("{" + pc + "}", "{" + cc + "}")
            templates[t.name] = tpl
            for x in out:                       # the table's IRI template is the parent's
                if x["kind"] == "iriTemplate" and x["table"] == t.name:
                    x["template"] = tpl
                    x["reasons"] = [f"subclass table: the subject IRIs of {parent.name}"]
            sub, sup = chosen.get(t.name, (None, 0))[0], chosen.get(parent.name, (None, 0))[0]
            out.append({"kind": "subclassTable", "table": t.name, "parent": parent.name,
                        "template": tpl, "term": str(sub) if sub else None,
                        "parentTerm": str(sup) if sup else None, "score": 0.9,
                        "reasons": [f"primary key {t.primary_key} of {t.name} is a foreign key "
                                    f"to the primary key of {parent.name}: same individuals, "
                                    "subclass rows"]})
            if sub is not None and sup is not None and sub != sup and not ix.is_subclass(sub, sup):
                out.append({"kind": "subClassOf", "sub": str(sub), "sup": str(sup),
                            "score": 0.8, "table": t.name,
                            "reasons": [f"{t.name} is a subclass table of {parent.name}, but the "
                                        f"ontology does not entail {local_name(sub)} "
                                        f"SubClassOf {local_name(sup)}",
                                        "an ontology edit: apply with owl.addAxiom if correct"]})

    # -- columns -> properties -------------------------------------------------- #
    drafts: dict[str, dict] = {}
    for t in todo:
        cls = chosen.get(t.name, (None, 0))[0]
        if cls is None:
            continue
        cls_above = ix.above(cls)
        draft = {"id": f"{re.sub(r'[^A-Za-z0-9]', '', t.name.title())}Map",
                 "source": src.id, "logicalTable": {"tableName": t.name},
                 "subject": {"template": templates[t.name], "classes": [str(cls)]},
                 "predicateObjects": []}
        fk_cols = {fk.columns[0]: fk for fk in t.foreign_keys if len(fk.columns) == 1}
        tkey = key(t.name)
        picked: dict[str, tuple[float, dict]] = {}
        for col in t.columns:
            if col.name in fk_cols:
                continue
            if col.primary_key and len(t.primary_key) == 1 and col.name.lower() in ("id", "pk"):
                continue
            ck = key(col.name)
            merged = {e: (sc, w) for sc, e, w in ix.best(ix.data, [ck])}
            for sc, e, w in ix.best(ix.data, [tkey + ck]):     # <table><column>, discounted
                if sc * 0.9 > merged[e][0]:
                    merged[e] = (sc * 0.9, w + " (with the table name)")
            hits = sorted(((sc, e, w) for e, (sc, w) in merged.items()),
                          key=lambda x: (-x[0], str(x[1])))
            best = None
            for score, p, why in hits[:5]:
                reasons = [f"column name {why}"]
                doms = ix.domains(p)
                if doms and doms & cls_above:
                    score = min(1.0, score + 0.1)
                    reasons.append("domain agrees with the table's class")
                elif doms:
                    score -= 0.15
                    reasons.append("domain is another class")
                rng = next(iter(ix.ranges(p)), None)
                if score < threshold:
                    continue
                out.append({"kind": "datatypeProperty", "table": t.name, "column": col.name,
                            "term": str(p), "score": round(score, 3), "reasons": reasons,
                            "datatype": str(rng) if rng is not None and str(rng).startswith(str(XSD))
                            else (str(_xsd_for(col.type)) if _xsd_for(col.type) else None)})
                best = best or out[-1]
            if best and best["score"] > picked.get(best["term"], (0.0, None))[0]:
                picked[best["term"]] = (best["score"], best)
        for _, best in sorted(picked.values(), key=lambda x: x[1]["column"]):
            pom = {"predicate": best["term"], "column": best["column"]}   # one column each
            if best.get("datatype") and best["datatype"] != str(XSD.string):
                pom["datatype"] = best["datatype"]
            draft["predicateObjects"].append(pom)
        for col_name, fk in fk_cols.items():
            parent = schema.table(fk.ref_table)
            pcls = chosen.get(parent.name, (None, 0))[0] if parent else None
            if parent is None or sorted(fk.columns) == sorted(t.primary_key):
                continue                                 # subclass link, handled above
            ck = key(re.sub(r"(?i)[_ ]?(id|key|fk|no|code)$", "", col_name)) or key(col_name)
            for score, p, why in ix.best(ix.obj, [ck, key(parent.name)])[:8]:
                doms, rngs = ix.domains(p), ix.ranges(p)
                reasons = [f"column name {why}"] if score >= 0.6 else []
                inverse = False
                pabove = ix.above(pcls) if pcls else set()
                if doms & cls_above and rngs & pabove:
                    score = max(score, 0.6) + 0.25
                    reasons.append("domain = table class, range = referenced table class")
                elif pcls and doms & pabove and rngs & cls_above:
                    score = max(score, 0.6) + 0.2
                    inverse = True
                    reasons.append("domain/range run the other way: an inverse link map")
                elif doms or rngs:
                    score -= 0.2
                    reasons.append("domain/range do not fit")
                score = min(1.0, score)
                if score < threshold:
                    continue
                ptpl = templates.get(parent.name) or _template(data_base, parent)
                otpl = ptpl
                for pc, cc in zip(fk.ref_columns, fk.columns):
                    otpl = otpl.replace("{" + pc + "}", "{" + cc + "}")
                out.append({"kind": "objectProperty", "table": t.name, "column": col_name,
                            "references": parent.name, "term": str(p), "inverse": inverse,
                            "template": otpl, "score": round(score, 3), "reasons": reasons})
                if not inverse and not any(x["predicate"] == str(p)
                                           for x in draft["predicateObjects"]):
                    draft["predicateObjects"].append({"predicate": str(p), "template": otpl})
                break
        drafts[t.name] = draft

    # -- discriminator columns --------------------------------------------------- #
    if discriminators:
        for t in todo:
            for col in t.columns:
                if col.primary_key or not any(x in col.type.upper() for x in _TEXT_TYPES) \
                        or t.fk_for(col.name):
                    continue
                if not re.search(r"(?i)(type|kind|category|class|segment|role)$", col.name):
                    continue
                try:
                    values = src.distinct_values(t.name, col.name)
                except Exception:
                    continue
                if not values or len(values) > 20:
                    continue
                tkey = key(t.name)
                for v in values:
                    if v is None:
                        continue
                    vk = key(str(v))
                    hits = [h for h in ix.best(ix.classes, [vk + tkey, vk]) if h[0] >= threshold]
                    if not hits:
                        continue
                    score, c, why = hits[0]
                    lit = str(v).replace("'", "''")
                    qcol = col.name.replace('"', '""')
                    qt = t.name.replace('"', '""')
                    sql = f"SELECT * FROM \"{qt}\" WHERE \"{qcol}\" = '{lit}'"
                    out.append({"kind": "discriminator", "table": t.name, "column": col.name,
                                "value": v, "term": str(c), "sqlQuery": sql,
                                "template": templates[t.name], "score": round(score * 0.95, 3),
                                "reasons": [f"value {v!r} of {col.name}: {why}",
                                            "rows with this value are instances of the class"]})

    for name, d in sorted(drafts.items()):
        out.append({"kind": "triplesMap", "table": name, "map": d,
                    "score": round(chosen[name][1], 3),
                    "reasons": ["draft assembled from the best proposals; review before adding"]})
    return out
