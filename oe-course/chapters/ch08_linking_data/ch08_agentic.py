"""Chapter 8 problem-set support — mapping a hospital's clinical database, and serving it.

Provided code for ``04_assignment.ipynb``. The student builds the mapping grader,
the Claude mapping designer, the lint, and the design-review agent in the
notebook; this module supplies what a real integration project would already
have in its codebase:

* the **Trust source database** — Northgate Regional Health Trust's clinical
  schema (11 tables, declared foreign keys) with a small, realistic extract;
* the reviewed **class maps** and the production **property mappings**
  (:data:`TRUST_MAPPINGS`) — the gold standard, built from the schema's own
  foreign-key metadata, never typed in by hand;
* the **integration requests** (:data:`REQUESTS`, 24 items, split 8/8/8 by
  item): each asks for one column to be exposed as an ontology property for one
  consuming service, and needs two decisions — the mapping shape (IRI to which
  class, or literal) and the execution strategy (materialise or rewrite);
* the **materialise-or-rewrite MDP** (:class:`MaterialisationMDP`) that decides
  every gold strategy label from the workload's numbers;
* **connectivity diagnostics** (:func:`property_triples`, :func:`object_profile`)
  and the design-review agent's **tools** (:func:`build_trust_tools`).

The two decisions fail in very different ways. A wrong *mapping shape* fails
silently: a foreign key mapped to a literal produces the same number of triples,
raises no error, and disconnects every join through it. A wrong *strategy*
fails expensively or, worse, stalely: a materialised copy that is not refreshed
returns confident wrong answers. Both are graded here by execution — the gold
mapping and the MDP — not by string comparison.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from rdflib import RDF, Literal, URIRef

import ch08_toolkit as ch8

__all__ = [
    "TRUST_SCHEMA_SQL", "TRUST_ROWS", "build_trust_database", "foreign_keys",
    "CLASS_MAPS", "class_for_table", "subject_class",
    "Request", "REQUESTS", "REQUEST_BY_ID", "gold_property_map", "TRUST_MAPPINGS", "build_dataset",
    "PLATFORM_COSTS", "PLATFORM_NOTE",
    "property_triples", "class_graph", "object_profile", "OBDA_RULEBOOK",
    "BASELINE_INSTRUCTION", "workload_string", "optimal_strategy", "validate_gold",
    "TrustWorkspace", "build_trust_tools", "ServeState", "MaterialisationMDP",
]

MED = ch8.MED
BASE = "http://example.org/trust/"


# --------------------------------------------------------------------------- #
# The source: Northgate Regional Health Trust's clinical database
# --------------------------------------------------------------------------- #
TRUST_SCHEMA_SQL = """
CREATE TABLE ward (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    speciality TEXT NOT NULL
);
CREATE TABLE bed (
    id      INTEGER PRIMARY KEY,
    ward_id INTEGER NOT NULL REFERENCES ward(id),
    status  TEXT NOT NULL            -- 'free' | 'occupied' | 'cleaning'
);
CREATE TABLE staff (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    role    TEXT NOT NULL,           -- 'consultant' | 'registrar' | 'nurse' | 'pharmacist'
    ward_id INTEGER REFERENCES ward(id)
);
CREATE TABLE patient (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    nhs_number  TEXT NOT NULL,       -- national identifier, 10 digits
    ward_id     INTEGER REFERENCES ward(id)
);
CREATE TABLE admission (
    id           INTEGER PRIMARY KEY,
    patient_id   INTEGER NOT NULL REFERENCES patient(id),
    bed_id       INTEGER REFERENCES bed(id),
    admitted_on  TEXT NOT NULL,
    referring_gp TEXT                -- free text, as written on the referral letter
);
CREATE TABLE transfer (
    id         INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patient(id),
    from_ward  INTEGER NOT NULL REFERENCES ward(id),
    to_ward    INTEGER NOT NULL REFERENCES ward(id),
    moved_at   TEXT NOT NULL
);
CREATE TABLE code_lookup (
    code     TEXT PRIMARY KEY,       -- ICD-10
    label    TEXT NOT NULL,
    category TEXT NOT NULL
);
CREATE TABLE diagnosis (
    patient_id INTEGER NOT NULL REFERENCES patient(id),
    code       TEXT NOT NULL REFERENCES code_lookup(code)
);
CREATE TABLE drug (
    code TEXT PRIMARY KEY,           -- ATC code
    name TEXT NOT NULL,
    form TEXT NOT NULL
);
CREATE TABLE prescription (
    id         INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patient(id),
    drug_code  TEXT NOT NULL REFERENCES drug(code),
    dose_mg    REAL NOT NULL,
    prescriber INTEGER NOT NULL REFERENCES staff(id)
);
CREATE TABLE lab_result (
    id         INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patient(id),
    test       TEXT NOT NULL,        -- local test name, e.g. 'troponin'
    value      REAL NOT NULL,
    unit       TEXT NOT NULL
);
""".strip()

#: A small, internally consistent extract. Bed ids deliberately overlap ward ids
#: (1-3), so a mapping that points a ward reference at the Bed template does
#: not dangle — it silently links patients to the wrong resources.
TRUST_ROWS: dict[str, list[tuple]] = {
    "ward": [(1, "Ward A", "cardiology"), (2, "Ward B", "respiratory"),
             (3, "Ward C", "cardiology")],
    "bed": [(1, 1, "occupied"), (2, 1, "free"), (3, 2, "occupied"), (4, 2, "cleaning"),
            (5, 3, "occupied"), (6, 3, "free")],
    "staff": [(201, "Dr Okafor", "consultant", 1), (202, "Nurse Silva", "nurse", 2),
              (203, "Dr Lindqvist", "registrar", 3), (204, "M. Haddad", "pharmacist", None)],
    "patient": [(101, "Ada", "9434765919", 1), (102, "Brahim", "9434765870", 2),
                (103, "Chen", "9434765862", 3), (104, "Dara", "9434765854", 1),
                (105, "Eze", "9434765846", 2), (106, "Fatima", "9434765838", 1)],
    "admission": [(501, 101, 1, "2026-09-01", "Dr Patel"),
                  (502, 102, 3, "2026-09-03", "Dr Moreau"),
                  (503, 103, 5, "2026-09-04", "Dr Patel"),
                  (504, 105, 4, "2026-09-11", "Dr Moreau"),
                  (505, 106, 2, "2026-09-20", "Dr Nguyen")],
    "transfer": [(701, 104, 2, 1, "2026-09-10T14:05"), (702, 105, 1, 2, "2026-09-12T09:30"),
                 (703, 106, 3, 1, "2026-09-21T22:15")],
    "code_lookup": [("I21", "acute myocardial infarction", "cardiac"),
                    ("I50", "heart failure", "cardiac"), ("J45", "asthma", "respiratory")],
    "diagnosis": [(101, "I21"), (102, "J45"), (103, "I50"), (104, "I21"), (105, "J45"),
                  (106, "I21")],
    "drug": [("B01AC06", "aspirin", "tablet"), ("C03CA01", "furosemide", "injection"),
             ("R03AC02", "salbutamol", "inhaler")],
    "prescription": [(801, 101, "B01AC06", 75.0, 201), (802, 103, "C03CA01", 40.0, 203),
                     (803, 102, "R03AC02", 0.1, 202), (804, 106, "B01AC06", 75.0, 203)],
    "lab_result": [(901, 101, "troponin", 52.0, "ng/L"), (902, 103, "NT-proBNP", 1800.0, "pg/mL"),
                   (903, 102, "CRP", 12.0, "mg/L"), (904, 106, "troponin", 64.0, "ng/L"),
                   (905, 105, "CRP", 8.0, "mg/L")],
}


def build_trust_database(rows=None) -> sqlite3.Connection:
    """The Trust's source database, in memory, with its extract loaded.

    ``check_same_thread=False``: DSPy's evaluator and GEPA call the scorer from
    worker threads, and the scorer reads this connection (read-only; the
    sqlite3 module serialises access).
    """
    rows = rows or TRUST_ROWS
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(TRUST_SCHEMA_SQL)
    for table, values in rows.items():
        if values:
            marks = ",".join("?" * len(values[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({marks})", values)
    conn.commit()
    return conn


def foreign_keys(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    """``{(table, column): (referenced_table, referenced_column)}`` from the catalogue.

    This — the schema's own declaration, not a column's name — is what decides
    whether a column maps to an IRI.
    """
    out = {}
    tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        for row in conn.execute(f"PRAGMA foreign_key_list({table})"):
            out[(table, row[3])] = (row[2], row[4])
    return out


# --------------------------------------------------------------------------- #
# Class maps (reviewed; one per entity table)
# --------------------------------------------------------------------------- #
def _cm(name, table, id_column, path, label=None):
    return ch8.ClassMap(MED + name, table, id_column, BASE + path + "/{}", label)


#: class name -> ClassMap. Instances get IRIs from these templates.
CLASS_MAPS: dict[str, ch8.ClassMap] = {
    "Ward": _cm("Ward", "ward", "id", "ward", "name"),
    "Bed": _cm("Bed", "bed", "id", "bed"),
    "Staff": _cm("Staff", "staff", "id", "staff", "name"),
    "Patient": _cm("Patient", "patient", "id", "patient", "name"),
    "Admission": _cm("Admission", "admission", "id", "admission"),
    "Transfer": _cm("Transfer", "transfer", "id", "transfer"),
    "Disorder": _cm("Disorder", "code_lookup", "code", "disorder", "label"),
    "Drug": _cm("Drug", "drug", "code", "drug", "name"),
    "Prescription": _cm("Prescription", "prescription", "id", "prescription"),
    "LabResult": _cm("LabResult", "lab_result", "id", "lab-result"),
}


def class_for_table(table: str) -> str | None:
    """The class whose instances are the rows of ``table`` (None for link tables)."""
    return next((name for name, c in CLASS_MAPS.items() if c.table == table), None)


def subject_class(conn, table: str, subject_column: str) -> str:
    """Which class the subject of a property map on ``table.subject_column`` belongs to.

    The table's own class when the column is its key; the referenced table's
    class when it is a foreign key (e.g. ``diagnosis.patient_id`` -> Patient).
    """
    own = class_for_table(table)
    if own and CLASS_MAPS[own].id_column == subject_column:
        return own
    ref = foreign_keys(conn).get((table, subject_column))
    if ref and class_for_table(ref[0]):
        return class_for_table(ref[0])
    raise ValueError(f"{table}.{subject_column} identifies no mapped class")


# --------------------------------------------------------------------------- #
# The integration requests
# --------------------------------------------------------------------------- #
#: Serving costs on the Trust's data platform, in reward units of the MDP (a
#: correct answer is worth 1). A full refresh is priced per request, as a
#: multiple of one rewritten query.
PLATFORM_COSTS = {"rewrite": 0.30, "materialised": 0.05}

PLATFORM_NOTE = ("Platform costs: a query answered from a materialised copy costs about "
                 "1/6 of a rewritten query; a refresh must complete before a stale copy "
                 "can answer correctly, and a stale copy's answers are wrong.")


@dataclass(frozen=True)
class Request:
    """One integration request: expose a column for one consuming service."""

    id: str
    split: str
    predicate: str          # local name in the med: namespace
    table: str
    subject_column: str
    object_column: str
    consumer: str           # the requesting team / service
    workload: str           # how the consumer reads and the source changes (prose)
    reads_per_update: int   # reads between consecutive relevant source updates
    refresh_queries: float  # cost of one full refresh, in rewritten-query units


#: Split fixed by item, balanced by (mapping shape x strategy): two of each of
#: the four combinations per split, and each split carries its share of the
#: traps — foreign keys without an ``_id`` suffix, ID-like attributes, and
#: workloads where the rule of thumb ("live data -> rewrite") is wrong.
REQUESTS: list[Request] = [
    # --- train ---------------------------------------------------------------
    Request("inward-bedboard", "train", "inWard", "patient", "id", "ward_id",
            "Bed-management board (site operations)",
            "Thirty ward screens poll the board all day. Between two consecutive "
            "admissions or transfers the board is read about 15 times. The patient-to-ward "
            "slice is small: re-materialising it costs about as much as 2 rewritten queries.",
            15, 2),
    Request("hasdisorder-cohort", "train", "hasDisorder", "diagnosis", "patient_id", "code",
            "Cardiology research cohort builder",
            "Analysts run about 40 cohort queries between the weekly diagnosis loads. A full "
            "refresh of the diagnosis graph costs about 10 rewritten queries.",
            40, 10),
    Request("fromward-flow", "train", "fromWard", "transfer", "id", "from_ward",
            "Patient-flow alerting service",
            "The alerting rule fires on every transfer, so the source changes between almost "
            "every pair of reads: about 1 read per update. A refresh costs about 5 rewritten "
            "queries.",
            1, 5),
    Request("prescriber-cdaudit", "train", "prescribedBy", "prescription", "id", "prescriber",
            "Controlled-drugs audit trail (pharmacy)",
            "Pharmacists check the trail as prescriptions are written: about 2 reads per new "
            "prescription. Re-materialising the prescription graph costs about 8 rewritten "
            "queries.",
            2, 8),
    Request("nhsnumber-mpi", "train", "nhsNumber", "patient", "id", "nhs_number",
            "Master patient index lookup",
            "Clinical systems look patients up about 25 times between registrations. A "
            "refresh costs about 3 rewritten queries.",
            25, 3),
    Request("speciality-quarterly", "train", "speciality", "ward", "id", "speciality",
            "Quarterly specialty-capacity report (finance)",
            "The report pack re-reads ward data about 30 times per quarter; wards are "
            "reconfigured at most once a quarter. A refresh costs about 4 rewritten queries.",
            30, 4),
    Request("bedstatus-cleaning", "train", "bedStatus", "bed", "id", "status",
            "Housekeeping tablets",
            "Each status change is read once, by the cleaner it is assigned to: about 1 read "
            "per update. A refresh costs about 3 rewritten queries.",
            1, 3),
    Request("labvalue-sepsis", "train", "resultValue", "lab_result", "id", "value",
            "Sepsis early-warning score",
            "The score is recomputed on every new result and read about twice before the "
            "next one arrives. The lab history is large: a refresh costs about 25 rewritten "
            "queries.",
            2, 25),
    # --- dev -----------------------------------------------------------------
    Request("drugcode-formulary", "dev", "prescribes", "prescription", "id", "drug_code",
            "Formulary analytics (medicines optimisation)",
            "About 20 analysis queries run between the nightly prescription loads. A refresh "
            "costs about 6 rewritten queries.",
            20, 6),
    Request("staffward-rota", "dev", "worksOn", "staff", "id", "ward_id",
            "Nurse-rota planner",
            "Planners open the rota about 12 times between staffing changes. The staff table "
            "is tiny: a refresh costs about 1 rewritten query.",
            12, 1),
    Request("admissionof-ed", "dev", "admissionOf", "admission", "id", "patient_id",
            "Emergency-department admissions tracker",
            "Every admission is shown once on the tracker as it happens: about 1 read per "
            "update. A refresh costs about 2 rewritten queries.",
            1, 2),
    Request("inbed-porters", "dev", "inBed", "admission", "id", "bed_id",
            "Porter dispatch",
            "Dispatch reads an admission's bed about twice before the next admission is "
            "written. A refresh costs about 6 rewritten queries.",
            2, 6),
    Request("category-coding", "dev", "category", "code_lookup", "code", "category",
            "Clinical-coding reference browser",
            "Coders browse categories about 50 times between releases of the code list. A "
            "refresh costs about 5 rewritten queries.",
            50, 5),
    Request("referringgp-letters", "dev", "referringGP", "admission", "id", "referring_gp",
            "Discharge-letter generator",
            "Letters are drafted and re-drafted: about 6 reads between new admissions. A "
            "refresh costs about 2 rewritten queries.",
            6, 2),
    Request("dose-druground", "dev", "doseMg", "prescription", "id", "dose_mg",
            "Drug-round screens",
            "Nurses read a dose about twice before the next prescription change. The "
            "prescription graph is large: a refresh costs about 10 rewritten queries.",
            2, 10),
    Request("labtest-research", "dev", "testName", "lab_result", "id", "test",
            "Retrospective research extract",
            "Researchers query the whole lab history only about 3 times between monthly "
            "loads, and a full refresh of ten years of results costs about 30 rewritten "
            "queries.",
            3, 30),
    # --- test ----------------------------------------------------------------
    Request("toward-capacity", "test", "toWard", "transfer", "id", "to_ward",
            "Weekly capacity-planning report",
            "The planning pack re-reads transfer data about 40 times between weekly loads. A "
            "refresh costs about 8 rewritten queries.",
            40, 8),
    Request("resultfor-portal", "test", "resultFor", "lab_result", "id", "patient_id",
            "Patient portal (results page)",
            "Each new result is viewed about once by its patient before the next result "
            "arrives. The lab history is large: a refresh costs about 25 rewritten queries.",
            1, 25),
    Request("bedward-capacity", "test", "bedInWard", "bed", "id", "ward_id",
            "Live capacity dashboard (control room)",
            "The control-room wall refreshes constantly: about 18 reads between two bed "
            "reassignments. The bed table is tiny: a refresh costs about 2 rewritten queries.",
            18, 2),
    Request("prescribedfor-pharmacy", "test", "prescribedFor", "prescription", "id",
            "patient_id", "Pharmacy verification queue",
            "Each new prescription is verified about twice before the next one arrives. A "
            "refresh costs about 9 rewritten queries.",
            2, 9),
    Request("role-directory", "test", "staffRole", "staff", "id", "role",
            "Staff directory (intranet)",
            "The directory is read about 60 times between staffing changes. A refresh costs "
            "about 2 rewritten queries.",
            60, 2),
    Request("drugform-catalogue", "test", "drugForm", "drug", "code", "form",
            "Medicines catalogue",
            "The catalogue is read about 35 times between formulary updates. A refresh costs "
            "about 3 rewritten queries.",
            35, 3),
    Request("unit-archive", "test", "resultUnit", "lab_result", "id", "unit",
            "Lab-archive search",
            "Archive searches over the full lab history run only about 4 times between "
            "monthly loads; a refresh of the whole history costs about 40 rewritten queries.",
            4, 40),
    Request("movedat-transferlog", "test", "movedAt", "transfer", "id", "moved_at",
            "Live transfer log (bed bureau)",
            "The bureau reads each transfer about once as it is logged. A refresh costs "
            "about 3 rewritten queries.",
            1, 3),
]


#: id -> Request, for looking up a dataset row's source columns and workload numbers.
REQUEST_BY_ID: dict[str, Request] = {r.id: r for r in REQUESTS}


def _subject_template(conn, req: Request) -> str:
    return CLASS_MAPS[subject_class(conn, req.table, req.subject_column)].template


def gold_property_map(req: Request, conn=None) -> ch8.PropertyMap:
    """The correct mapping for a request — derived from the schema, not typed in.

    A declared foreign key becomes an IRI built from the *referenced* table's
    class template; any other column becomes a literal.
    """
    conn = conn or build_trust_database()
    ref = foreign_keys(conn).get((req.table, req.object_column))
    object_template = CLASS_MAPS[class_for_table(ref[0])].template if ref else None
    return ch8.PropertyMap(MED + req.predicate, req.table, req.subject_column,
                           req.object_column, _subject_template(conn, req), object_template)


def _gold_target(req: Request, conn) -> str:
    ref = foreign_keys(conn).get((req.table, req.object_column))
    return class_for_table(ref[0]) if ref else "none"


def _request_text(req: Request, conn) -> str:
    subj = subject_class(conn, req.table, req.subject_column)
    return (f"Expose column `{req.table}.{req.object_column}` as the ontology property "
            f"`med:{req.predicate}`. The subject of each triple is the {subj} identified by "
            f"`{req.table}.{req.subject_column}`. Requested by: {req.consumer}.")


def _build_mappings() -> dict:
    conn = build_trust_database()
    return {"classes": list(CLASS_MAPS.values()),
            "properties": [gold_property_map(r, conn) for r in REQUESTS]}


#: The production mapping: every class map plus the gold property map of every request.
TRUST_MAPPINGS = _build_mappings()


def build_dataset(split: str = "all"):
    """The requests as ``dspy.Example`` rows (inputs: request, workload, schema)."""
    import dspy

    conn = build_trust_database()
    rows = []
    for req in REQUESTS:
        strategy = optimal_strategy(req.reads_per_update, req.refresh_queries)["strategy"]
        rows.append(dspy.Example(
            id=req.id, split=req.split,
            request=_request_text(req, conn),
            workload=f"{req.consumer}. {req.workload} {PLATFORM_NOTE}",
            schema=TRUST_SCHEMA_SQL,
            gold_object_kind="iri" if _gold_target(req, conn) != "none" else "literal",
            gold_target_class=_gold_target(req, conn),
            gold_strategy=strategy,
            predicate=req.predicate, table=req.table, subject_column=req.subject_column,
            object_column=req.object_column, reads_per_update=req.reads_per_update,
            refresh_queries=req.refresh_queries,
        ).with_inputs("request", "workload", "schema"))
    return rows if split == "all" else [r for r in rows if r.split == split]


# --------------------------------------------------------------------------- #
# Executing a mapping: triples and connectivity
# --------------------------------------------------------------------------- #
def property_triples(conn, pmap: ch8.PropertyMap) -> set[tuple[str, str, str]]:
    """The triples one property map produces, as ``(s, p, o)`` with the object's kind.

    Objects are rendered ``<iri>`` or ``"literal"`` so that an IRI and a literal
    with the same text never compare equal — which is exactly the bug.
    """
    g = ch8.materialise(conn, {"classes": [], "properties": [pmap]})
    return {(str(s), str(p), f"<{o}>" if isinstance(o, URIRef) else f'"{o}"')
            for s, p, o in g}


def class_graph(conn):
    """Only the class-map triples (instances and labels) of the Trust mapping."""
    return ch8.materialise(conn, {"classes": list(CLASS_MAPS.values()), "properties": []})


def object_profile(conn, pmap: ch8.PropertyMap, classes=None) -> dict:
    """Where a property map's objects land: typed instances, literals, or nowhere.

    ``typed_as`` counts objects that are instances of each class; ``literals``
    are values that can never be joined to a resource; ``dangling`` are IRIs
    no class map produces. Only ``typed_as`` objects are *connected*.
    """
    classes = classes if classes is not None else class_graph(conn)
    by_iri = {}
    for s, _, o in classes.triples((None, RDF.type, None)):
        by_iri[str(s)] = str(o).split("#")[-1]
    g = ch8.materialise(conn, {"classes": [], "properties": [pmap]})
    profile = {"triples": 0, "typed_as": {}, "literals": 0, "dangling": 0}
    for _, _, o in g:
        profile["triples"] += 1
        if isinstance(o, Literal):
            profile["literals"] += 1
        elif str(o) in by_iri:
            cls = by_iri[str(o)]
            profile["typed_as"][cls] = profile["typed_as"].get(cls, 0) + 1
        else:
            profile["dangling"] += 1
    return profile


# --------------------------------------------------------------------------- #
# The guidelines a mapping-decision scorer reports
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("answer-in-the-contract",
             "Answer object_kind with exactly 'iri' or 'literal', target_class with one of "
             "the mapped class names (Ward, Bed, Staff, Patient, Admission, Transfer, "
             "Disorder, Drug, Prescription, LabResult) or 'none' for a literal, and strategy "
             "with exactly 'materialise' or 'rewrite'."),
        Rule("iri-for-foreign-keys",
             "When the schema declares the column a foreign key (REFERENCES t(c)), map it to "
             "an IRI of the referenced table's class, whatever the column is called. A "
             "literal there silently disconnects the graph: no join through it ever matches."),
        Rule("reference-the-right-table",
             "Point a foreign-key IRI at the class of the table named in its REFERENCES "
             "clause (e.g. from_ward -> Ward, prescriber -> Staff, code -> Disorder). The "
             "wrong template either dangles or silently links to the wrong resources."),
        Rule("literal-for-attributes",
             "When the column holds a value rather than a declared reference — a name, a "
             "status, a code with no REFERENCES clause, an identifier such as an NHS number "
             "— map it to a literal; an IRI there names a resource that does not exist."),
        Rule("materialise-when-refresh-pays",
             "Materialise when the reads between consecutive updates repay one refresh: "
             "reads_per_update x (cost of a rewritten query - cost of a query from the copy) "
             "> cost of a refresh. Live data alone is not a reason to rewrite if the refresh "
             "is cheap."),
        Rule("rewrite-when-refresh-does-not-pay",
             "Rewrite when a refresh costs more than the reads it would serve save: few "
             "reads between updates, or a large source to re-materialise. Rarely-updated "
             "data is not a reason to materialise if it is also rarely read."),
    ])


#: The guidelines a mapping-decision scorer reports as violated.
OBDA_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = ("You are an OBDA engineer. Decide how to map the column and how to "
                        "serve the consumer's queries.")


# --------------------------------------------------------------------------- #
# The materialise-or-rewrite MDP
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ServeState:
    """Where we are in the workload, and whether the materialisation is fresh."""

    index: int
    fresh: bool

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"t{self.index}{'+' if self.fresh else '-'}"


class MaterialisationMDP:
    """Serve a workload of queries and updates: materialise, or rewrite?

    The workload is a known sequence of ``'q'`` (a query to answer) and ``'u'``
    (an update to the source). An update makes any materialisation **stale**.

    | | |
    |---|---|
    | **S** | position in the workload, and whether the copy is fresh |
    | **A** | on a query: serve by rewriting, serve from the copy, or refresh then serve |
    | **T** | deterministic |
    | **R** | ``+1`` for a **correct** answer, minus the cost of serving it |

    Serving from a stale copy is the *cheapest* action and earns nothing,
    because the answer is wrong — staleness is priced as lost reward, not as
    latency. This is §8.2's trade-off with numbers attached.
    """

    def __init__(self, workload: str = "qquqqquq", cost_rewrite: float = 0.30,
                 cost_materialised: float = 0.05, cost_refresh: float = 0.50,
                 gamma: float = 1.0):
        self.workload = workload
        self.cost_rewrite = cost_rewrite
        self.cost_materialised = cost_materialised
        self.cost_refresh = cost_refresh
        self.gamma = gamma

    @classmethod
    def for_workload(cls, reads_per_update: int, refresh_queries: float, cycles: int = 2,
                     **costs) -> "MaterialisationMDP":
        """A periodic workload: ``reads_per_update`` queries then one update, ``cycles`` times.

        The refresh is priced in rewritten-query units, as the requests state it.
        """
        cost_rewrite = costs.pop("cost_rewrite", PLATFORM_COSTS["rewrite"])
        cost_mat = costs.pop("cost_materialised", PLATFORM_COSTS["materialised"])
        return cls(workload_string(reads_per_update, cycles), cost_rewrite=cost_rewrite,
                   cost_materialised=cost_mat,
                   cost_refresh=refresh_queries * cost_rewrite, **costs)

    def initial_state(self) -> ServeState:
        return ServeState(0, False)

    def is_terminal(self, state: ServeState) -> bool:
        return state.index >= len(self.workload)

    def states(self):
        # Latest first: value iteration then converges in a single sweep.
        return [ServeState(i, f)
                for i in range(len(self.workload), -1, -1)
                for f in (False, True)]

    def actions(self, state: ServeState):
        if self.is_terminal(state):
            return []
        if self.workload[state.index] == "u":
            return ["apply-update"]
        return ["serve:rewrite", "serve:materialised", "serve:refresh-first"]

    def transition(self, state: ServeState, action: str):
        nxt_index = state.index + 1
        if action == "apply-update":
            # An update invalidates any materialised copy.
            return [(1.0, ServeState(nxt_index, False), 0.0)]
        if action == "serve:rewrite":
            return [(1.0, ServeState(nxt_index, state.fresh), 1.0 - self.cost_rewrite)]
        if action == "serve:materialised":
            correct = 1.0 if state.fresh else 0.0
            return [(1.0, ServeState(nxt_index, state.fresh),
                     correct - self.cost_materialised)]
        # refresh, then serve from the fresh copy
        reward = 1.0 - self.cost_refresh - self.cost_materialised
        return [(1.0, ServeState(nxt_index, True), reward)]

    def step(self, state: ServeState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)

    def describe(self, state: ServeState, action: str) -> str:
        event = "update" if self.workload[state.index] == "u" else "query"
        return f"[{state.index}] {event:6s} fresh={state.fresh!s:5s} -> {action}"


def workload_string(reads_per_update: int, cycles: int = 2) -> str:
    """``reads_per_update`` queries followed by one update, repeated ``cycles`` times."""
    return ("q" * int(reads_per_update) + "u") * cycles


def optimal_strategy(reads_per_update: int, refresh_queries: float, cycles: int = 2) -> dict:
    """Solve the request's MDP and summarise the optimal policy.

    ``strategy`` is ``"materialise"`` when the optimal policy answers most
    queries from the copy (refreshing when needed), else ``"rewrite"``. This is
    how every gold strategy label is produced.
    """
    from oe_course import mdp

    M = MaterialisationMDP.for_workload(reads_per_update, refresh_queries, cycles)
    V, pi = mdp.value_iteration(M)
    episode = mdp.run_episode(M, mdp.greedy_policy(pi), max_steps=len(M.workload) + 1)
    served = [a for a in episode.actions if a.startswith("serve:")]
    from_copy = sum(a != "serve:rewrite" for a in served)
    share = from_copy / len(served) if served else 0.0
    return {"strategy": "materialise" if share > 0.5 else "rewrite",
            "share_from_copy": round(share, 3), "value": round(V[M.initial_state()], 4),
            "refreshes": episode.actions.count("serve:refresh-first")}


def validate_gold(verbose: bool = False) -> dict:
    """Recompute every gold label with the chapter's own engines, and assert it.

    * mapping shape and target class: from the catalogue's foreign keys;
    * the gold mapping is *connected*: every IRI object is a typed instance of
      the target class, and the literal mappings produce no IRIs;
    * strategy: from the MDP, and far from the break-even point (no ties);
    * the split is balanced on both decisions.
    """
    conn = build_trust_database()
    classes = class_graph(conn)
    fks = foreign_keys(conn)
    rows = build_dataset()
    counts: dict = {}
    for ex in rows:
        req = next(r for r in REQUESTS if r.id == ex.id)
        pmap = gold_property_map(req, conn)
        profile = object_profile(conn, pmap, classes)
        assert profile["triples"] > 0, ex.id
        if ex.gold_object_kind == "iri":
            assert (req.table, req.object_column) in fks, ex.id
            assert profile["typed_as"] == {ex.gold_target_class: profile["triples"]}, ex.id
        else:
            assert profile["literals"] == profile["triples"], ex.id
        break_even = (req.refresh_queries * PLATFORM_COSTS["rewrite"]
                      / (PLATFORM_COSTS["rewrite"] - PLATFORM_COSTS["materialised"]))
        closed_form = "materialise" if req.reads_per_update > break_even else "rewrite"
        assert closed_form == ex.gold_strategy, ex.id
        ratio = req.reads_per_update / break_even
        assert ratio >= 1.5 or ratio <= 0.67, f"{ex.id} is too close to break-even"
        key = (ex.split, ex.gold_object_kind, ex.gold_strategy)
        counts[key] = counts.get(key, 0) + 1
        if verbose:
            print(f"{ex.id:24s} {ex.split:5s} {ex.gold_object_kind:7s} "
                  f"{ex.gold_target_class:9s} {ex.gold_strategy:11s} r={req.reads_per_update:>3} "
                  f"break-even={break_even:5.1f}")
    assert all(v == 2 for v in counts.values()) and len(counts) == 12, counts
    ids = [ex.id for ex in rows]
    assert len(ids) == len(set(ids)) == 24
    return {"items": len(rows), "cells": counts}


# --------------------------------------------------------------------------- #
# The design-review agent's tools (Part D)
# --------------------------------------------------------------------------- #
@dataclass
class TrustWorkspace:
    """What the design-review agent can see: the source database and its call log."""

    conn: object = None
    log: object = None
    _classes: object = field(default=None, repr=False)

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.conn = self.conn if self.conn is not None else build_trust_database()
        self.log = self.log or ToolCallLog()

    @property
    def classes(self):
        if self._classes is None:
            self._classes = class_graph(self.conn)
        return self._classes


def build_trust_tools(ws: TrustWorkspace):
    """Tools: read the schema, list the class maps, try a mapping, price a strategy."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def inspect_schema() -> str:
        """Return the source schema: every table's columns and its DECLARED foreign keys.

        Whether a column is a declared foreign key decides whether it maps to an IRI.
        """
        out = {}
        for (table,) in ws.conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            columns = [{"name": r[1], "type": r[2], "primary_key": bool(r[5])}
                       for r in ws.conn.execute(f"PRAGMA table_info({table})")]
            keys = [{"column": r[3], "references": f"{r[2]}.{r[4]}"}
                    for r in ws.conn.execute(f"PRAGMA foreign_key_list({table})")]
            out[table] = {"columns": columns, "foreign_keys": keys}
        return json.dumps(out)

    def list_classes() -> str:
        """List the mapped classes: name, source table, key column and IRI template."""
        return json.dumps([{"class": n, "table": c.table, "key": c.id_column,
                            "iri_template": c.template} for n, c in CLASS_MAPS.items()])

    def check_mapping(table: str, subject_column: str, object_column: str,
                      object_kind: str, target_class: str = "none") -> str:
        """Materialise ONE candidate property map and report where its objects land.

        object_kind is 'iri' or 'literal'; for 'iri' give the target_class whose IRI
        template builds the object. Returns the triple count, sample objects, and
        how many objects are typed instances of each class (connected), literals, or
        dangling IRIs. A foreign key must land entirely on instances of the class it
        references; an attribute should produce literals.
        """
        kind = object_kind.strip().lower()
        if kind not in {"iri", "literal"}:
            raise ValueError("object_kind must be 'iri' or 'literal'")
        template = None
        if kind == "iri":
            if target_class not in CLASS_MAPS:
                raise ValueError(f"unknown class {target_class!r}; see list_classes")
            template = CLASS_MAPS[target_class].template
        subject = CLASS_MAPS[subject_class(ws.conn, table, subject_column)].template
        pmap = ch8.PropertyMap(MED + "candidate", table, subject_column, object_column,
                               subject, template)
        profile = object_profile(ws.conn, pmap, ws.classes)
        sample = sorted({o for _, _, o in property_triples(ws.conn, pmap)})[:3]
        return json.dumps({**profile, "sample_objects": sample})

    def price_strategy(reads_per_update: int, refresh_cost_in_queries: float) -> str:
        """Solve the materialise-or-rewrite MDP for a periodic workload.

        reads_per_update: reads between consecutive source updates;
        refresh_cost_in_queries: one full refresh, in units of one rewritten query.
        Returns the optimal strategy, the share of queries served from the copy and
        the break-even number of reads per update.
        """
        reads = max(1, int(round(reads_per_update)))
        result = optimal_strategy(reads, float(refresh_cost_in_queries))
        result["break_even_reads"] = round(
            refresh_cost_in_queries * PLATFORM_COSTS["rewrite"]
            / (PLATFORM_COSTS["rewrite"] - PLATFORM_COSTS["materialised"]), 2)
        return json.dumps(result)

    impls = [inspect_schema, list_classes, check_mapping, price_strategy]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]
