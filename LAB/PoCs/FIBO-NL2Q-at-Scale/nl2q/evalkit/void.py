"""VoID partition metadata for the FIBEN knowledge graph (specification §2 L3, §3 C3/C4).

Describes what the data actually holds, for closed-world grounding and refusals:

* a ``void:classPartition`` per class with ``void:entities``. A subclass row always has its
  parent row (enforced by Gate 1 key integrity), so the parent table counts all instances;
* a ``void:propertyPartition`` per property with ``void:triples`` (non-NULL values);
* a ``void:Linkset`` per relation (class, property, target class) with ``void:triples`` and
  its cardinality: the maximum number of subjects sharing one target, which flags the
  1:N fan-out side;
* min / max bounds of numeric and date attributes, used to construct the out-of-range
  unanswerable stratum U3.

    python -m nl2q.evalkit.void        # writes artifacts/eval/void.ttl and void.json (Base)
"""

from __future__ import annotations

import json

import duckdb
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef

from .. import paths, schema, vkg_build

VOID = Namespace("http://rdfs.org/ns/void#")
EV = Namespace("https://example.org/fiben/eval#")
VOC = Namespace(vkg_build.VOC)


def compute(schema_name: str = paths.SCHEMA) -> dict:
    s = schema.load()
    con = duckdb.connect(str(paths.DB), read_only=True)
    q = lambda sql: con.execute(sql).fetchone()                              # noqa: E731
    out = {"classes": {}, "properties": {}, "linksets": [], "bounds": {}}
    for t in s.tables.values():
        cls = vkg_build.class_name(t.name)
        out["classes"][cls] = q(f'SELECT count(*) FROM "{schema_name}"."{t.name}"')[0]
        for c in t.data_columns:
            p = vkg_build.prop_name(c.name)
            n = q(f'SELECT count("{c.name}") FROM "{schema_name}"."{t.name}"')[0]
            out["properties"][p] = out["properties"].get(p, 0) + n
            if c.sql_type in ("BIGINT", "INTEGER", "DOUBLE", "DATE", "TIMESTAMP") and n:
                lo, hi = q(f'SELECT min("{c.name}"), max("{c.name}") FROM "{schema_name}"."{t.name}"')
                out["bounds"][f"{cls}.{p}"] = [str(lo), str(hi)]
        for f in t.relation_fks:
            p = vkg_build.prop_name(f.column)
            n = q(f'SELECT count("{f.column}") FROM "{schema_name}"."{t.name}"')[0]
            fan = q(f'SELECT coalesce(max(k), 0) FROM (SELECT count(*) AS k FROM "{schema_name}"."{t.name}" '
                    f'WHERE "{f.column}" IS NOT NULL GROUP BY "{f.column}")')[0]
            out["properties"][p] = out["properties"].get(p, 0) + n
            out["linksets"].append({"subject": cls, "property": p, "object": vkg_build.class_name(f.ref_table),
                                    "triples": n, "max_subjects_per_object": fan})
    con.close()
    return out


def to_rdf(v: dict) -> Graph:
    g = Graph()
    g.bind("void", VOID)
    g.bind("fiben", VOC)
    ds = URIRef("https://example.org/fiben/dataset")
    g.add((ds, RDF.type, VOID.Dataset))
    for cls, n in v["classes"].items():
        p = BNode()
        g.add((ds, VOID.classPartition, p))
        g.add((p, VOID["class"], VOC[cls]))
        g.add((p, VOID.entities, Literal(n)))
    for prop, n in v["properties"].items():
        p = BNode()
        g.add((ds, VOID.propertyPartition, p))
        g.add((p, VOID.property, VOC[prop]))
        g.add((p, VOID.triples, Literal(n)))
    for ls in v["linksets"]:
        p = BNode()
        g.add((p, RDF.type, VOID.Linkset))
        g.add((p, VOID.subset, ds))
        g.add((p, VOID.linkPredicate, VOC[ls["property"]]))
        g.add((p, EV.subjectClass, VOC[ls["subject"]]))
        g.add((p, EV.objectClass, VOC[ls["object"]]))
        g.add((p, VOID.triples, Literal(ls["triples"])))
        g.add((p, EV.maxSubjectsPerObject, Literal(ls["max_subjects_per_object"])))
    return g


if __name__ == "__main__":
    v = compute()
    out = paths.ARTIFACTS / "eval"
    (out / "void.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
    to_rdf(v).serialize(out / "void.ttl", format="turtle")
    empty = sorted(c for c, n in v["classes"].items() if n == 0)
    print(json.dumps({"classes": len(v["classes"]), "empty_classes": len(empty), "properties": len(v["properties"]),
                      "linksets": len(v["linksets"]), "bounded_attributes": len(v["bounds"])}, indent=1))
