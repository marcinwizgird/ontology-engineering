"""An independent reference answer for every query: no Ontop, no SQL compilation.

1. **Materialise** the knowledge graph: read the R2RML mapping with rdflib and run each
   triples map's logical table against the DuckDB fixture, producing the RDF triples the
   mapping defines (subject templates, rr:class, column / template objects, datatypes).
2. **Reason**: add every superclass type the ontology entails through rdfs:subClassOf
   (the only TBox axiom the four queries depend on).
3. **Answer** the SPARQL query with rdflib's own engine.

If the compiled SQL returns the same rows as this pipeline, the compiler preserved the
query's meaning, not just its syntax.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import duckdb
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef

RR = Namespace("http://www.w3.org/ns/r2rml#")
ARTIFACTS = Path(__file__).resolve().parents[2] / "vkg-artifacts"
_PLACEHOLDER = re.compile(r'\{"?([A-Za-z_][A-Za-z0-9_]*)"?\}')


def _unquote(col: str) -> str:
    return col.strip().strip('"')


def materialise(con: duckdb.DuckDBPyConnection) -> Graph:
    m = Graph().parse(ARTIFACTS / "fiben-mappings.r2rml.ttl")
    kg = Graph()
    for tm in m.subjects(RDF.type, RR.TriplesMap):
        lt = m.value(tm, RR.logicalTable)
        table, query = m.value(lt, RR.tableName), m.value(lt, RR.sqlQuery)
        sql = str(query) if query is not None else f"SELECT * FROM {table}"
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        sm = m.value(tm, RR.subjectMap)
        s_tpl, s_cls = str(m.value(sm, RR.template)), list(m.objects(sm, RR["class"]))
        poms = []
        for pom in m.objects(tm, RR.predicateObjectMap):
            om = m.value(pom, RR.objectMap)
            poms.append((m.value(pom, RR.predicate), m.value(om, RR.column),
                         m.value(om, RR.template), m.value(om, RR.datatype)))
        for row in rows:
            s = _fill(s_tpl, row)
            if s is None:
                continue
            for c in s_cls:
                kg.add((s, RDF.type, c))
            for p, col, tpl, dt in poms:
                if tpl is not None:
                    o = _fill(str(tpl), row)
                else:
                    v = row.get(_unquote(str(col)))
                    o = None if v is None else Literal(v, datatype=dt) if dt else Literal(str(v))
                if o is not None:
                    kg.add((s, p, o))
    return kg


def _fill(template: str, row: dict) -> URIRef | None:
    out, missing = template, False

    def sub(m):
        nonlocal missing
        v = row.get(m.group(1))
        missing |= v is None
        return "" if v is None else str(v)

    out = _PLACEHOLDER.sub(sub, out)
    return None if missing else URIRef(out)


def reason(kg: Graph) -> Graph:
    tbox = Graph().parse(ARTIFACTS / "fibo-subset.ttl")
    supers: dict = {}
    for sub, sup in tbox.subject_objects(RDFS.subClassOf):
        supers.setdefault(sub, set()).add(sup)
    for s, c in list(kg.subject_objects(RDF.type)):
        todo, seen = [c], {c}
        while todo:
            for up in supers.get(todo.pop(), ()):
                if up not in seen:
                    seen.add(up)
                    todo.append(up)
                    kg.add((s, RDF.type, up))
    return kg


def answer(kg: Graph, sparql: str) -> list[tuple]:
    return [tuple(_py(v) for v in row) for row in kg.query(sparql)]


def _py(v):
    if v is None:
        return None
    if isinstance(v, Literal):
        val = v.toPython()
        return Decimal(str(val)) if isinstance(val, (int, float, Decimal)) else val
    return str(v)
