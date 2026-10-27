"""Closed-world shapes for the FIBEN knowledge graph (specification Gate 1.3).

Shapes are generated from the DDL, one NodeShape per class:

* every attribute: ``sh:datatype``, ``sh:maxCount 1``, and ``sh:minCount 1`` when NOT NULL;
* every relation: ``sh:class`` (its foreign-key target) and ``sh:maxCount 1``.

FIBEN has 11.7M rows per instance, far beyond what pySHACL can hold, so the shapes are
validated **compiled to SQL** over each database instance:

* minCount → NULL counts;
* maxCount → duplicate keys;
* sh:class → the referenced row exists;
* the subclass entailment → the parent row exists (``gate1.key_integrity``);
* sh:datatype → guaranteed by the column type, recorded as such.

The compilation is checked against pySHACL itself (``cross_check``): a sample of rows is
materialised to RDF with defects injected, and both validators must report the same
violations.

    python -m nl2q.evalkit.shacl      # writes artifacts/eval/gate1/shapes.ttl and the SQL report
"""

from __future__ import annotations

import json

import duckdb
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef, XSD

from .. import paths, schema, vkg_build
from . import gate1

SH = Namespace("http://www.w3.org/ns/shacl#")
VOC = Namespace(vkg_build.VOC)
SHAPES = Namespace("https://example.org/fiben/shapes#")
DATA = "https://example.org/fiben/data/"


def shapes(s: schema.Schema | None = None) -> Graph:
    s = s or schema.load()
    g = Graph()
    g.bind("sh", SH)
    g.bind("fiben", VOC)
    for t in s.tables.values():
        node = SHAPES[vkg_build.class_name(t.name)]
        g.add((node, RDF.type, SH.NodeShape))
        g.add((node, SH.targetClass, VOC[vkg_build.class_name(t.name)]))
        for c in t.data_columns:
            p = BNode()
            g.add((node, SH.property, p))
            g.add((p, SH.path, VOC[vkg_build.prop_name(c.name)]))
            g.add((p, SH.datatype, XSD[c.xsd]))
            g.add((p, SH.maxCount, Literal(1)))
            if not c.nullable:
                g.add((p, SH.minCount, Literal(1)))
        for f in t.relation_fks:
            p = BNode()
            g.add((node, SH.property, p))
            g.add((p, SH.path, VOC[vkg_build.prop_name(f.column)]))
            g.add((p, SH["class"], VOC[vkg_build.class_name(f.ref_table)]))
            g.add((p, SH.maxCount, Literal(1)))
    return g


def validate_sql(schema_name: str, con) -> dict:
    """The shapes compiled to SQL over one instance: violations per constraint kind."""
    s = schema.load()
    out = {"minCount": [], "maxCount": [], "class": [], "subclass": []}
    for t in s.tables.values():
        pk = t.pk[0]
        for c in t.data_columns:
            if not c.nullable:
                n = con.execute(f'SELECT count(*) FROM "{schema_name}"."{t.name}" WHERE "{c.name}" IS NULL').fetchone()[0]
                if n:
                    out["minCount"].append({"shape": t.name, "path": c.name, "violations": n})
        dup = con.execute(f'SELECT count(*) FROM (SELECT "{pk}" FROM "{schema_name}"."{t.name}" '
                          f'GROUP BY 1 HAVING count(*) > 1)').fetchone()[0]
        if dup:
            out["maxCount"].append({"shape": t.name, "path": pk, "violations": dup})
    for v in gate1.key_integrity(schema_name, con):
        out["class" if v["kind"] == "relation" else "subclass"].append(v)
    total = sum(x.get("violations", x.get("dangling", 0)) for k in out for x in out[k])
    return {"violations": total, **out, "datatype": "guaranteed by the column types"}


def report() -> dict:
    gate1.OUT.mkdir(parents=True, exist_ok=True)
    shapes().serialize(gate1.OUT / "shapes.ttl", format="turtle")
    con = duckdb.connect(str(paths.DB), read_only=True)
    rep = {sch: validate_sql(sch, con) for sch in gate1.present_instances(con)}
    con.close()
    return rep


# ----------------------------------------------------------------------------- pySHACL cross-check
CROSS_TABLES = ("FINANCIALSERVICEACCOUNT", "HOLDING", "PERSON", "LISTEDSECURITY", "SECURITY")


def _iri(s, table: str, key) -> URIRef:
    return URIRef(f"{DATA}{vkg_build.class_name(gate1_root(s, table))}/{key}")


def gate1_root(s, table: str) -> str:
    parent = dict(s.subclass_edges)
    while table in parent:
        table = parent[table]
    return table


def sample_graph(con, rows_per_table: int = 60, inject: bool = True) -> tuple[Graph, dict]:
    """Rows of a few tables as RDF (with the types of their reference targets), plus
    injected defects: a NULL in a NOT NULL attribute and a dangling reference. Returns the
    graph and the defects injected, by kind."""
    s = schema.load()
    g = Graph()
    injected = {"minCount": 0, "class": 0}
    for name in CROSS_TABLES:
        t = s.tables[name]
        cur = con.execute(f'SELECT * FROM "{paths.SCHEMA}"."{name}" ORDER BY 1 LIMIT {rows_per_table}')
        cols = [d[0] for d in cur.description]
        for i, r in enumerate(cur.fetchall()):
            row = dict(zip(cols, r))
            subj = _iri(s, name, row[t.pk[0]])
            g.add((subj, RDF.type, VOC[vkg_build.class_name(name)]))
            for c in t.data_columns:
                v = row[c.name]
                if inject and i == 0 and not c.nullable:
                    injected["minCount"] += 1
                    continue                                     # defect 1: required value missing
                if v is not None:
                    g.add((subj, VOC[vkg_build.prop_name(c.name)], Literal(v, datatype=XSD[c.xsd])))
            for f in t.relation_fks:
                v = row[f.column]
                if v is None:
                    continue
                if inject and i == 1:
                    injected["class"] += 1
                    v = -1                                       # defect 2: reference to nothing
                obj = _iri(s, f.ref_table, v)
                g.add((subj, VOC[vkg_build.prop_name(f.column)], obj))
                exists = con.execute(f'SELECT 1 FROM "{paths.SCHEMA}"."{f.ref_table}" WHERE '
                                     f'"{s.tables[f.ref_table].pk[0]}" = ?', [v]).fetchone()
                if exists:
                    g.add((obj, RDF.type, VOC[vkg_build.class_name(f.ref_table)]))
    return g, injected


def cross_check(rows_per_table: int = 60) -> dict:
    """pySHACL and the SQL compilation must agree on a sample with injected defects."""
    from pyshacl import validate
    con = duckdb.connect(str(paths.DB), read_only=True)
    g, injected = sample_graph(con, rows_per_table)
    con.close()
    sg = shapes()
    conforms, results, _ = validate(g, shacl_graph=sg, inference="none")
    found = {"minCount": 0, "class": 0, "other": 0}
    for r in results.subjects(RDF.type, SH.ValidationResult):
        comp = str(results.value(r, SH.sourceConstraintComponent))
        kind = "minCount" if comp.endswith("MinCountConstraintComponent") else \
            "class" if comp.endswith("ClassConstraintComponent") else "other"
        found[kind] += 1
    return {"conforms": conforms, "injected": injected, "pyshacl_found": found,
            "agree": found["minCount"] == injected["minCount"] and found["class"] == injected["class"]
                     and found["other"] == 0}


if __name__ == "__main__":
    rep = report()
    rep_summary = {k: v["violations"] for k, v in rep.items()}
    xc = cross_check()
    out = gate1.OUT / "shacl.json"
    out.write_text(json.dumps({"instances": rep, "cross_check": xc}, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"violations_per_instance": rep_summary, "cross_check": xc}, indent=1))
