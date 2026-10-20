"""Build the FIBEN virtual knowledge graph artefacts from the DDL (design time).

Outputs (``artifacts/ontop/``, mounted into the FIBEN Ontop sidecar):

* ``fiben-ontology.ttl`` — one class per table, ``rdfs:subClassOf`` from the subclass
  tables (PK = FK to the parent), one object property per relation-FK column name, one
  datatype property per data column name; labels from word segmentation;
* ``fiben-mapping.r2rml.ttl`` — generated R2RML for all 152 tables. A subclass row and
  its parent row are the *same individual*, so every table in a hierarchy mints IRIs
  from the hierarchy's root table;
* ``db-metadata.json`` — Ontop's offline schema description, generated from the DDL
  (no database needed).

And ``artifacts/knowledge/``:

* ``alignment.csv`` — each FIBEN term against FIBO: ``exact`` (squashed label/local name
  match), ``suggested`` (token overlap, needs review) or ``none``;
* ``edges.json`` — the allowed (domain class, property, range class) triples the schema
  realises, which the query graph and the ontology query check use. Properties are shared
  across tables (``hasName`` is on 130 tables), so OWL ``rdfs:domain`` would mean the
  intersection and is deliberately not asserted.

    python -m nl2q.vkg_build
"""

from __future__ import annotations

import csv
import json
import math
import re
from functools import lru_cache

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from . import fibo, paths, schema

VOC = Namespace("https://example.org/fiben/voc#")
DATA = "https://example.org/fiben/data/"
RR = Namespace("http://www.w3.org/ns/r2rml#")

_EXTRA_WORDS = {"autonomous", "impaired", "pronouncement", "vest", "unrealized", "reconciliation", "extinguishment", "troubled", "translation", "email", "phone", "temporary", "carry", "past", "due", "has", "is", "of", "to", "by", "on", "in", "for", "and", "or", "the", "id",
                "uri", "url", "ticker", "cik", "lei", "sic", "naics", "iso", "gaap", "disclosure",
                "receivable", "payable", "accrued", "deferred", "unrecorded", "noncontrolling",
                "antidilutive", "amortization", "depreciation", "comprehensive", "line1",
                "line2", "postal", "zip", "fiscal", "calendar", "quarter", "metric",
                "domicile", "domiciled", "citizenship", "settlement", "facilitated", "refers",
                "index", "member", "provided", "traded", "managed", "owned", "held", "classified",
                "defined", "initial", "middle", "gender", "birth", "abandoned", "held",
                "qualifying", "valuation", "allowance", "impairment", "restructuring"}


_SHORT = {"of", "to", "by", "on", "in", "or", "is", "id", "as", "at", "an"}


def _camel_words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z][a-z]+|[a-z]+", text)]


@lru_cache(maxsize=1)
def _vocab() -> dict[str, float]:
    """Word costs from FIBO local names and labels plus the us-gaap element names stored
    in FIBEN's own data (``SalesRevenueNet``, ``us-gaap/2015_LiabilitiesCurrent``)."""
    from collections import Counter
    freq: Counter = Counter()
    for t in fibo.load().terms.values():
        freq.update(w for w in _camel_words(t.local) if len(w) > 2)
        freq.update(w for w in re.findall(r"[a-z]+", t.label.lower()) if len(w) > 2)
        # definitions and notes: a few thousand sentences of financial English
        freq.update(w for w in re.findall(r"[a-z]+", f"{t.definition} {t.note}".lower()) if len(w) > 2)
    try:
        from .load_fiben import connect
        con = connect()
        for (v,) in con.execute('SELECT DISTINCT "HASUNIQUEIDENTIFIER" FROM "FIBEN"."ELEMENTOFFINANCIALSTATEMENT"').fetchall():
            if v:
                freq.update(w for w in _camel_words(v.split("_")[-1]) if len(w) > 2)
        for t in schema.load().tables.values():
            if any(c.name == "HASNAME" for c in t.columns) and t.parent_fk:
                for (v,) in con.execute(f'SELECT DISTINCT "HASNAME" FROM "FIBEN"."{t.name}" LIMIT 200').fetchall():
                    if v:
                        freq.update(w for w in _camel_words(v) if len(w) > 2)
    except Exception:  # noqa: BLE001 - the data is an optional source of words
        pass
    for w in _EXTRA_WORDS | _SHORT:
        freq[w] += 200
    total = sum(freq.values())
    return {w: -math.log(c / total) for w, c in freq.items()}


_SUFFIXES = ("ations", "ation", "ions", "ion", "ities", "ity", "ments", "ment", "ings", "ing",
             "ies", "es", "ed", "s", "able", "ables", "ally", "al", "ive", "ives", "er", "ers")


def _word_cost(w: str, cost: dict[str, float]) -> float | None:
    """Vocabulary cost of *w*, accepting regular inflections of known stems
    (computation <- compute, liabilities <- liability, charges <- charge)."""
    c = cost.get(w)
    if c is not None:
        return c
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[: -len(suf)]
            for cand in (stem, stem + "e", stem + "y"):
                if cand in cost:
                    return cost[cand] + 1.5
    return None


def segment(token: str) -> list[str]:
    """Split an upper-case identifier into words (Viterbi over FIBO's word costs)."""
    s = token.lower()
    cost = _vocab()
    unknown = max(cost.values()) + 6
    best = [(0.0, 0)] + [(math.inf, 0)] * len(s)
    for i in range(1, len(s) + 1):
        for j in range(max(0, i - 24), i):
            w = s[j:i]
            c = _word_cost(w, cost)
            if c is None:
                c = unknown * len(w) if not w.isdigit() else 1.0
            if best[j][0] + c < best[i][0]:
                best[i] = (best[j][0] + c, j)
    words, i = [], len(s)
    while i > 0:
        j = best[i][1]
        words.append(s[j:i])
        i = j
    return list(reversed(words))


NAMES_JSON = paths.KNOWLEDGE_DIR / "names.json"


@lru_cache(maxsize=1)
def _frozen() -> dict[str, list[str]]:
    """Identifiers must not change between runs: the segmentation is computed once and
    frozen in ``artifacts/knowledge/names.json`` (delete it to recompute)."""
    import json as _json
    if NAMES_JSON.exists():
        return _json.loads(NAMES_JSON.read_text(encoding="utf-8"))
    s = schema.load()
    tokens = set(s.tables) | {c.name for t in s.tables.values() for c in t.columns}
    names = {tok: segment(tok) for tok in sorted(tokens)}
    NAMES_JSON.parent.mkdir(parents=True, exist_ok=True)
    NAMES_JSON.write_text(_json.dumps(names, indent=0), encoding="utf-8")
    return names


def words(token: str) -> list[str]:
    return _frozen().get(token) or segment(token)


def class_name(table: str) -> str:
    return "".join(w.capitalize() for w in words(table))


def prop_name(column: str) -> str:
    ws = words(column)
    return ws[0] + "".join(w.capitalize() for w in ws[1:])


def label(token: str) -> str:
    return " ".join(words(token))


def root(s: schema.Schema, table: str) -> str:
    t = s.tables[table]
    while t.parent_fk:
        t = s.tables[t.parent_fk.ref_table]
    return t.name


def subject_template(s: schema.Schema, table: str) -> str:
    r = root(s, table)
    pk = s.tables[table].pk[0]
    return f'{DATA}{r.lower()}/{{"{pk}"}}'


# --------------------------------------------------------------------------- #
def build_ontology(s: schema.Schema) -> tuple[Graph, list[dict], list[tuple[str, str, str]]]:
    g = Graph()
    g.bind("fiben", VOC)
    g.bind("owl", OWL)
    g.bind("skos", SKOS)
    onto = URIRef("https://example.org/fiben/ontology")
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, RDFS.comment, Literal("Reconstructed from the FIBEN DDL (IBM, Apache-2.0); "
                                       "aligned to FIBO where labels match.")))
    idx = fibo.squash_index()
    f = fibo.load()
    align: list[dict] = []

    def add_term(iri: URIRef, kind: str, token: str, typ) -> None:
        g.add((iri, RDF.type, typ))
        g.add((iri, RDFS.label, Literal(label(token), lang="en")))
        g.add((iri, SKOS.notation, Literal(token)))
        hits = [h for h in idx.get(fibo.squash(token), [])
                if f.terms[h].kind == ("class" if kind == "class" else f.terms[h].kind)]
        if kind != "class":
            hits = [h for h in hits if f.terms[h].kind in ("object", "datatype")]
        status, target = "none", ""
        if hits:
            status, target = "exact", hits[0]
            g.add((iri, SKOS.exactMatch, URIRef(target)))
        else:
            toks = set(words(token)) - {"has", "is", "of", "by", "to", "the"}
            best, score = "", 0.0
            for t in f.terms.values():
                if (kind == "class") != (t.kind == "class") or not t.label:
                    continue
                tw = set(re.findall(r"[a-z]+", t.label.lower()))
                if not tw:
                    continue
                j = len(toks & tw) / len(toks | tw)
                if j > score:
                    best, score = t.iri, j
            if score >= 0.5:
                status, target = "suggested", best
        align.append({"fiben": token, "iri": str(iri), "kind": kind, "status": status,
                      "fibo": target, "fibo_label": f.terms[target].label if target else ""})

    for t in s.tables.values():
        c = VOC[class_name(t.name)]
        add_term(c, "class", t.name, OWL.Class)
        if t.parent_fk:
            g.add((c, RDFS.subClassOf, VOC[class_name(t.parent_fk.ref_table)]))

    edges: list[tuple[str, str, str]] = []
    seen_props: set[str] = set()
    for t in s.tables.values():
        dom = str(VOC[class_name(t.name)])
        for fk in t.relation_fks:
            p = VOC[prop_name(fk.column)]
            if str(p) not in seen_props:
                add_term(p, "object", fk.column, OWL.ObjectProperty)
                seen_props.add(str(p))
            edges.append((dom, str(p), str(VOC[class_name(fk.ref_table)])))
        for col in t.data_columns:
            p = VOC[prop_name(col.name)]
            if str(p) not in seen_props:
                add_term(p, "datatype", col.name, OWL.DatatypeProperty)
                seen_props.add(str(p))
            edges.append((dom, str(p), str(XSD[col.xsd])))
    return g, align, edges


def build_mapping(s: schema.Schema) -> Graph:
    g = Graph()
    g.bind("rr", RR)
    g.bind("fiben", VOC)
    g.bind("xsd", XSD)
    base = "https://example.org/fiben/mapping#"
    for t in s.tables.values():
        tm = URIRef(base + t.name)
        g.add((tm, RDF.type, RR.TriplesMap))
        lt = URIRef(base + t.name + "_table")
        g.add((tm, RR.logicalTable, lt))
        g.add((lt, RR.tableName, Literal(f'"{paths.SCHEMA}"."{t.name}"')))
        sm = URIRef(base + t.name + "_subject")
        g.add((tm, RR.subjectMap, sm))
        g.add((sm, RR.template, Literal(subject_template(s, t.name))))
        g.add((sm, RR["class"], VOC[class_name(t.name)]))
        for i, col in enumerate(t.data_columns):
            pom = URIRef(f"{base}{t.name}_d{i}")
            om = URIRef(f"{base}{t.name}_d{i}_o")
            g.add((tm, RR.predicateObjectMap, pom))
            g.add((pom, RR.predicate, VOC[prop_name(col.name)]))
            g.add((pom, RR.objectMap, om))
            g.add((om, RR.column, Literal(f'"{col.name}"')))
            if col.xsd != "string":
                g.add((om, RR.datatype, XSD[col.xsd]))
        for i, fk in enumerate(t.relation_fks):
            pom = URIRef(f"{base}{t.name}_r{i}")
            om = URIRef(f"{base}{t.name}_r{i}_o")
            g.add((tm, RR.predicateObjectMap, pom))
            g.add((pom, RR.predicate, VOC[prop_name(fk.column)]))
            g.add((pom, RR.objectMap, om))
            g.add((om, RR.template, Literal(f'{DATA}{root(s, fk.ref_table).lower()}/{{"{fk.column}"}}')))
    return g


def build_db_metadata(s: schema.Schema) -> dict:
    q = lambda x: f'"{x}"'  # noqa: E731
    rels = []
    for t in s.tables.values():
        rels.append({
            "uniqueConstraints": [{"name": f"{t.name}_pkey", "determinants": [q(k) for k in t.pk],
                                   "isPrimaryKey": True}],
            "otherFunctionalDependencies": [],
            "foreignKeys": [{"name": fk.name,
                             "from": {"relation": [q(paths.SCHEMA), q(t.name)], "columns": [q(fk.column)]},
                             "to": {"relation": [q(paths.SCHEMA), q(fk.ref_table)], "columns": [q(fk.ref_column)]}}
                            for fk in t.fks],
            "columns": [{"name": q(c.name), "isNullable": c.nullable and c.name not in t.pk,
                         "datatype": c.pg_type} for c in t.columns],
            "name": [q(paths.SCHEMA), q(t.name)],
        })
    return {"relations": rels,
            "metadata": {"dbmsProductName": "PostgreSQL", "dbmsVersion": "16.0",
                         "driverName": "PostgreSQL JDBC Driver", "driverVersion": "42.7.4",
                         "quotationString": "\"", "extractionTime": "generated-from-DDL",
                         "idFactoryType": "POSTGRESQL"}}


ONTOP_PROPERTIES = """# Offline: Ontop reads the schema from db-metadata.json and never connects.
jdbc.url=jdbc:postgresql://no-database.invalid:5432/fiben
jdbc.driver=org.postgresql.Driver
jdbc.user=none
jdbc.password=none
"""


def main() -> None:
    s = schema.load()
    onto, align, edges = build_ontology(s)
    paths.ONTOP_DIR.mkdir(parents=True, exist_ok=True)
    paths.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    onto.serialize(paths.ONTOLOGY_TTL, format="turtle")
    build_mapping(s).serialize(paths.MAPPING_TTL, format="turtle")
    paths.DB_METADATA.write_text(json.dumps(build_db_metadata(s), indent=1), encoding="utf-8")
    (paths.ONTOP_DIR / "ontop.properties").write_text(ONTOP_PROPERTIES, encoding="utf-8")
    with (paths.KNOWLEDGE_DIR / "alignment.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(align[0]))
        w.writeheader()
        w.writerows(align)
    (paths.KNOWLEDGE_DIR / "edges.json").write_text(json.dumps(edges, indent=0), encoding="utf-8")
    from collections import Counter
    c = Counter((a["kind"], a["status"]) for a in align)
    print(f"ontology: {len(s.tables)} classes, {len({e[1] for e in edges})} properties, "
          f"{len(edges)} allowed edges; alignment {dict(c)}")


if __name__ == "__main__":
    main()
