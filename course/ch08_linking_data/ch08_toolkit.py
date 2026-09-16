"""Chapter 8 toolkit — ontology-based data access, both ways round.

Chapter 8's subject is the gap between an ontology and the data that is supposed
to instantiate it. The data lives in a relational database that knows nothing
about your classes; the questions are asked in the ontology's vocabulary. A
**mapping** bridges the two, and there are exactly two ways to use it:

* **materialisation** — run the mapping once, generate triples, query the graph;
* **query rewriting** — leave the data where it is, translate the *query* into
  SQL and run it against the source.

Both are implemented here over the same mappings, and the notebooks check the
property that makes OBDA a discipline rather than a hope: **they return the same
answers**. Once that holds, choosing between them is an engineering trade —
storage and staleness against query latency — which is what §8.2 is about and
what the chapter's MDP optimises.

Everything runs on the standard library's ``sqlite3`` plus ``rdflib``; no server
and no triplestore required.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from rdflib import RDF, RDFS, Graph, Literal, URIRef

__all__ = [
    "build_database", "SCHEMA_SQL", "SAMPLE_ROWS",
    "ClassMap", "PropertyMap", "MAPPINGS", "MED",
    "materialise", "ConjunctiveQuery", "to_sparql", "to_sql",
    "answers_via_materialisation", "answers_via_rewriting",
    "QUERIES", "mapping_report",
]

MED = "http://example.org/med#"
BASE = "http://example.org/data/"


# --------------------------------------------------------------------------- #
# The relational source
# --------------------------------------------------------------------------- #
SCHEMA_SQL = """
CREATE TABLE ward (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    speciality TEXT NOT NULL
);
CREATE TABLE patient (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    ward_id INTEGER REFERENCES ward(id)
);
CREATE TABLE diagnosis (
    patient_id INTEGER REFERENCES patient(id),
    code       TEXT NOT NULL
);
CREATE TABLE code_lookup (
    code     TEXT PRIMARY KEY,
    label    TEXT NOT NULL,
    category TEXT NOT NULL
);
"""

SAMPLE_ROWS = {
    "ward": [
        (1, "Ward A", "cardiology"),
        (2, "Ward B", "respiratory"),
        (3, "Ward C", "cardiology"),
    ],
    "patient": [
        (101, "Ada", 1),
        (102, "Brahim", 2),
        (103, "Chen", 3),
        (104, "Dara", 1),
        (105, "Eze", 2),
    ],
    "diagnosis": [
        (101, "I21"),
        (102, "J45"),
        (103, "I50"),
        (104, "I21"),
        (105, "J45"),
    ],
    "code_lookup": [
        ("I21", "acute myocardial infarction", "cardiac"),
        ("I50", "heart failure", "cardiac"),
        ("J45", "asthma", "respiratory"),
    ],
}


def build_database(rows=None) -> sqlite3.Connection:
    """An in-memory hospital database — the 'legacy source' of §8.1."""
    rows = rows or SAMPLE_ROWS
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    for table, values in rows.items():
        placeholders = ",".join("?" * len(values[0]))
        conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", values)
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# Mappings (an R2RML-flavoured subset)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClassMap:
    """``table`` rows become instances of ``rdf_class``, with IRIs from a template."""

    rdf_class: str
    table: str
    id_column: str
    template: str
    label_column: str | None = None

    def iri(self, value) -> str:
        return self.template.format(value)


@dataclass(frozen=True)
class PropertyMap:
    """A column pair in ``table`` becomes a triple.

    ``object_template`` builds an IRI; when it is ``None`` the object is a
    literal — the distinction R2RML draws between a referencing object map and a
    plain one.
    """

    predicate: str
    table: str
    subject_column: str
    object_column: str
    subject_template: str
    object_template: str | None = None


PATIENT = ClassMap(MED + "Patient", "patient", "id", BASE + "patient/{}", "name")
WARD = ClassMap(MED + "Ward", "ward", "id", BASE + "ward/{}", "name")
DISORDER = ClassMap(MED + "Disorder", "code_lookup", "code", BASE + "disorder/{}", "label")

MAPPINGS = {
    "classes": [PATIENT, WARD, DISORDER],
    "properties": [
        PropertyMap(MED + "inWard", "patient", "id", "ward_id",
                    BASE + "patient/{}", BASE + "ward/{}"),
        PropertyMap(MED + "hasDisorder", "diagnosis", "patient_id", "code",
                    BASE + "patient/{}", BASE + "disorder/{}"),
        PropertyMap(MED + "speciality", "ward", "id", "speciality",
                    BASE + "ward/{}", None),
        PropertyMap(MED + "category", "code_lookup", "code", "category",
                    BASE + "disorder/{}", None),
    ],
}


def mapping_report(mappings=None):
    """A readable table of what each mapping produces."""
    mappings = mappings or MAPPINGS
    rows = [
        {"kind": "class", "target": c.rdf_class.split("#")[-1], "source": c.table,
         "produces": c.template}
        for c in mappings["classes"]
    ]
    rows += [
        {"kind": "property", "target": p.predicate.split("#")[-1],
         "source": f"{p.table}.{p.subject_column} -> {p.table}.{p.object_column}",
         "produces": "literal" if p.object_template is None else p.object_template}
        for p in mappings["properties"]
    ]
    return rows


# --------------------------------------------------------------------------- #
# Strategy 1: materialisation
# --------------------------------------------------------------------------- #
def materialise(conn: sqlite3.Connection, mappings=None) -> Graph:
    """Run every mapping and build the RDF graph — the ETL answer to §8.2."""
    mappings = mappings or MAPPINGS
    g = Graph()
    g.bind("med", MED)

    for cmap in mappings["classes"]:
        columns = [cmap.id_column] + ([cmap.label_column] if cmap.label_column else [])
        for row in conn.execute(f"SELECT {','.join(columns)} FROM {cmap.table}"):
            subject = URIRef(cmap.iri(row[0]))
            g.add((subject, RDF.type, URIRef(cmap.rdf_class)))
            if cmap.label_column:
                g.add((subject, RDFS.label, Literal(row[1])))

    for pmap in mappings["properties"]:
        query = (f"SELECT {pmap.subject_column}, {pmap.object_column} "
                 f"FROM {pmap.table} WHERE {pmap.object_column} IS NOT NULL")
        for subject_value, object_value in conn.execute(query):
            subject = URIRef(pmap.subject_template.format(subject_value))
            obj = (URIRef(pmap.object_template.format(object_value))
                   if pmap.object_template else Literal(object_value))
            g.add((subject, URIRef(pmap.predicate), obj))
    return g


# --------------------------------------------------------------------------- #
# A conjunctive query — the fragment both strategies support
# --------------------------------------------------------------------------- #
@dataclass
class ConjunctiveQuery:
    """``select`` variables over class atoms, property atoms and equality filters.

    Deliberately restricted to the conjunctive fragment. That is not a
    simplification for teaching's sake: query rewriting is *defined* only for
    fragments where it is possible, which is exactly why OWL 2 QL exists
    (Chapter 4) and why §8.3 insists on a rewriting-friendly profile.
    """

    select: list
    class_atoms: list = field(default_factory=list)
    property_atoms: list = field(default_factory=list)
    filters: list = field(default_factory=list)


def _short(iri: str) -> str:
    return iri.split("#")[-1]


def to_sparql(query: ConjunctiveQuery) -> str:
    """Render the query as SPARQL, for the materialised graph."""
    header = " ".join("?" + v for v in query.select)
    lines = [f"PREFIX med: <{MED}>", f"SELECT DISTINCT {header} WHERE {{"]
    for var, cls in query.class_atoms:
        lines.append(f"  ?{var} a med:{_short(cls)} .")
    for subject, predicate, obj in query.property_atoms:
        lines.append(f"  ?{subject} med:{_short(predicate)} ?{obj} .")
    for var, value in query.filters:
        lines.append('  FILTER(str(?' + var + ') = "' + value + '")')
    lines.append("}")
    return "\n".join(lines)


def to_sql(query: ConjunctiveQuery, mappings=None) -> str:
    """Rewrite the query into SQL against the original source.

    This is the heart of §8.3. Each atom is replaced by the table its mapping
    names, variables become columns, and a variable occurring in two atoms
    becomes a **join condition**. At runtime the ontology does not exist — it
    has been compiled away into SQL.
    """
    mappings = mappings or MAPPINGS
    class_by_iri = {c.rdf_class: c for c in mappings["classes"]}
    property_by_iri = {p.predicate: p for p in mappings["properties"]}

    froms = []
    wheres = []
    bindings = {}

    def bind(var, expression, template):
        bindings.setdefault(var, []).append((expression, template))

    for index, (var, cls) in enumerate(query.class_atoms):
        cmap = class_by_iri[cls]
        alias = f"c{index}"
        froms.append(f"{cmap.table} {alias}")
        bind(var, f"{alias}.{cmap.id_column}", cmap.template)

    for index, (subject, predicate, obj) in enumerate(query.property_atoms):
        pmap = property_by_iri[predicate]
        alias = f"p{index}"
        froms.append(f"{pmap.table} {alias}")
        bind(subject, f"{alias}.{pmap.subject_column}", pmap.subject_template)
        bind(obj, f"{alias}.{pmap.object_column}", pmap.object_template)

    # A variable occurring in more than one atom becomes a join.
    for occurrences in bindings.values():
        first = occurrences[0][0]
        for other, _ in occurrences[1:]:
            wheres.append(f"{first} = {other}")

    for var, value in query.filters:
        wheres.append(bindings[var][0][0] + " = '" + value + "'")

    def projection(var):
        expression, template = bindings[var][0]
        if template is None:
            return f"{expression} AS {var}"
        prefix = template.replace("{}", "")
        return "('" + prefix + "' || " + expression + ") AS " + var

    sql = ("SELECT DISTINCT " + ", ".join(projection(v) for v in query.select)
           + "\nFROM " + ", ".join(froms))
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)
    return sql


# --------------------------------------------------------------------------- #
# Running a query both ways
# --------------------------------------------------------------------------- #
def answers_via_materialisation(conn, query, mappings=None, graph=None):
    """Materialise (unless a graph is supplied) and answer with SPARQL."""
    g = graph if graph is not None else materialise(conn, mappings)
    rows = []
    for row in g.query(to_sparql(query)):
        rows.append({str(var): str(row[var]) for var in row.labels})
    return sorted(rows, key=lambda r: tuple(sorted(r.items())))


def answers_via_rewriting(conn, query, mappings=None):
    """Rewrite to SQL and answer from the live source."""
    cursor = conn.execute(to_sql(query, mappings))
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, (str(v) for v in values))) for values in cursor.fetchall()]
    return sorted(rows, key=lambda r: tuple(sorted(r.items())))


# --------------------------------------------------------------------------- #
# The chapter's worked queries
# --------------------------------------------------------------------------- #
QUERIES = {
    "patients": ConjunctiveQuery(
        select=["p"],
        class_atoms=[("p", MED + "Patient")],
    ),
    "patients-in-cardiology": ConjunctiveQuery(
        select=["p", "w"],
        property_atoms=[("p", MED + "inWard", "w"), ("w", MED + "speciality", "spec")],
        filters=[("spec", "cardiology")],
    ),
    "patients-with-cardiac-disorder": ConjunctiveQuery(
        select=["p", "d"],
        property_atoms=[("p", MED + "hasDisorder", "d"), ("d", MED + "category", "cat")],
        filters=[("cat", "cardiac")],
    ),
    "cardiac-patients-in-cardiology": ConjunctiveQuery(
        select=["p"],
        property_atoms=[("p", MED + "hasDisorder", "d"), ("d", MED + "category", "cat"),
                        ("p", MED + "inWard", "w"), ("w", MED + "speciality", "spec")],
        filters=[("cat", "cardiac"), ("spec", "cardiology")],
    ),
}
