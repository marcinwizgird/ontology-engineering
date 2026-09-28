"""Build the Chapter 8 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch08_linking_data/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 8 — Linking Ontologies to Data",
    title="Mapping and serving a hospital trust's clinical data with Claude",
    coverage=("Keet §8.1 (the data–ontology gap, mappings), §8.2 (materialisation / ETL), "
              "§8.3 (query rewriting, OBDA); course notebooks 01–03 of this chapter. Tools: "
              "the Chapter 8 mapping engine (R2RML-style class and property maps, a "
              "materialiser and a SPARQL-to-SQL rewriter), DSPy + GEPA, LangChain agents, "
              "value iteration."),
    scenario="""
    Northgate Regional Health Trust is putting an ontology in front of its clinical
    database (wards, beds, staff, patients, admissions, transfers, diagnoses, drugs,
    prescriptions, lab results — 11 tables). Teams across the Trust file **integration
    requests**: *"expose `transfer.from_ward` as `med:fromWard` for the patient-flow
    alerting service"*. Every request needs two decisions, and the data-platform lead
    wants both made the same way every time:

    * **the mapping shape** — does the column become an **IRI** (and of which class) or
      a **literal**? Get it wrong and nothing fails: the graph is silently disconnected,
      and the bed board reports an empty cardiology ward;
    * **the execution strategy** — **materialise** the mapped graph (and refresh it after
      updates) or **rewrite** each query into SQL against the live source? Get it wrong
      and the service is either needlessly slow, or it serves stale answers.

    You are the ontology engineer on the platform team. Your brief:

    1. **Make the silent failure loud.** Measure what a wrong mapping does, and build
       the two detectors the CI will run: a schema-aware lint and a two-path agreement
       test.
    2. **Build the grader, then a Claude mapping designer.** Decisions are graded by
       *executing* them — the proposed mapping's triples against the reviewed mapping's,
       the proposed strategy against the MDP's optimal policy — never by string match.
       Improve the designer with GEPA, and report on a **held-out test split** with the
       cost and the run-to-run noise.
    3. **Ship a design-review agent** that inspects the schema, *tries* its mapping, prices
       the strategy with the MDP, and only then answers.
    4. **Price staleness.** Derive when materialising pays, and show what an agent does
       when staleness is left out of its reward.

    The Trust schema and extract, the class maps, the reviewed production mappings and
    the 24 integration requests (split 8/8/8 by item, two of each *shape × strategy*
    combination per split) are provided in `ch08_agentic.py`. Every gold label is
    recomputed from the schema's foreign keys and the MDP when the notebook starts.
    """,
    effort="10–12 hours",
    api_budget="≈ $6–12 estimated on `claude-opus-5` for a full run (≈ 170 DSPy calls plus "
               "8 agent episodes; GEPA and the C3 noise runs are the largest lines). Nothing "
               "in this estimate was measured — record your own figures in the cost cells. "
               "Re-running unchanged cells is free: DSPy caches identical requests.",
)

ps.setup("""
import dataclasses, time
import dspy
import numpy as np
import pandas as pd
import ch08_toolkit as ch8
import ch08_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

print(A.validate_gold())                     # every gold label recomputed from schema + MDP
train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
EXAMPLES = {ex.id: ex for ex in train + dev + test}
conn = A.build_trust_database()
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
pd.crosstab([pd.Series([e.split for e in EXAMPLES.values()], name="split")],
            [pd.Series([e.gold_object_kind for e in EXAMPLES.values()], name="shape"),
             pd.Series([e.gold_strategy for e in EXAMPLES.values()], name="strategy")])
""")

ps.md("""
One dataset row, as the designer will see it (`request`, `workload`, `schema` are the
inputs; the `gold_*` fields are the labels):
""")
ps.code("""
ex = EXAMPLES["fromward-flow"]
print(ex.request, "\\n")
print(ex.workload, "\\n")
print({k: ex[k] for k in ["gold_object_kind", "gold_target_class", "gold_strategy",
                          "reads_per_update", "refresh_queries"]})
""")

# =========================================================================== #
ps.part("A", "The silent failure, and the detectors that make it loud", """
`A.TRUST_MAPPINGS` is the reviewed production mapping: ten class maps and one property
map per request. Its foreign-key properties are IRIs built from the *referenced* table's
class template; everything else is a literal.
""")
ps.code("""
TEMPLATE_CLASS = {c.template: name for name, c in A.CLASS_MAPS.items()}
RANGE = {ex.predicate: ex.gold_target_class for ex in EXAMPLES.values()}  # the ontology's rdfs:range ('none' = datatype property)
FK_MAPS = [p for p in A.TRUST_MAPPINGS["properties"] if p.object_template is not None]
full_graph = ch8.materialise(conn, A.TRUST_MAPPINGS)
print(len(full_graph), "triples;", len(FK_MAPS), "object properties,",
      len(A.TRUST_MAPPINGS["properties"]) - len(FK_MAPS), "datatype properties")
pd.DataFrame(ch8.mapping_report(A.TRUST_MAPPINGS)).tail(8)
""")

ps.problem("A1", "Measure the damage a literal does", 10, """
Write `probe_query(pmap, target_class) -> ch8.ConjunctiveQuery`: a query that *uses* the
property. For an object property (`target_class` a key of `A.CLASS_MAPS`) it selects
`?s` such that `?s <predicate> ?o` **and** `?o` is an instance of the target class; for a
datatype property (`target_class == "none"`) it selects `?s` and `?o` from the one
property atom.

Then, for **every** foreign-key property map in `FK_MAPS`, break it — the same map with
`object_template=None` (`dataclasses.replace`) swapped into an otherwise unchanged copy
of `A.TRUST_MAPPINGS` — and build `a1` with one row per property and columns
`property` (local name), `triples_correct`, `triples_broken` (size of the full
materialised graph), `materialised_correct`, `materialised_broken`, `rewritten_broken`
(answer counts of the probe query, target = the property's range), and `agree_broken`
(do materialisation and rewriting give identical answers under the broken mapping?).

In writing: why does nothing — the mapper, the triple store, SPARQL, SQL — raise an
error? Where in the Trust would this bug first be *noticed*, and by whom?
""", auto_points=6)
ps.todo(
    stub="""
    def probe_query(pmap, target_class: str) -> ch8.ConjunctiveQuery:
        # TODO
        raise NotImplementedError

    def swap(mappings, new_pmap):
        \"\"\"A copy of `mappings` with the property map of the same predicate replaced.\"\"\"
        # TODO
        raise NotImplementedError

    a1 = None   # TODO: one row per foreign-key property map
    """,
    solution="""
    def probe_query(pmap, target_class: str) -> ch8.ConjunctiveQuery:
        if target_class == "none":
            return ch8.ConjunctiveQuery(select=["s", "o"],
                                        property_atoms=[("s", pmap.predicate, "o")])
        return ch8.ConjunctiveQuery(
            select=["s"],
            class_atoms=[("o", A.CLASS_MAPS[target_class].rdf_class)],
            property_atoms=[("s", pmap.predicate, "o")])

    def swap(mappings, new_pmap):
        \"\"\"A copy of `mappings` with the property map of the same predicate replaced.\"\"\"
        return {"classes": list(mappings["classes"]),
                "properties": [new_pmap if p.predicate == new_pmap.predicate else p
                               for p in mappings["properties"]]}

    rows = []
    for pmap in FK_MAPS:
        target = TEMPLATE_CLASS[pmap.object_template]
        broken = swap(A.TRUST_MAPPINGS, dataclasses.replace(pmap, object_template=None))
        broken_graph = ch8.materialise(conn, broken)
        q = probe_query(pmap, target)
        mat_ok = ch8.answers_via_materialisation(conn, q, graph=full_graph)
        mat_bad = ch8.answers_via_materialisation(conn, q, graph=broken_graph)
        rw_bad = ch8.answers_via_rewriting(conn, q, broken)
        rows.append({"property": pmap.predicate.split("#")[-1],
                     "triples_correct": len(full_graph), "triples_broken": len(broken_graph),
                     "materialised_correct": len(mat_ok), "materialised_broken": len(mat_bad),
                     "rewritten_broken": len(rw_bad), "agree_broken": mat_bad == rw_bad})
    a1 = pd.DataFrame(rows)
    a1
    """)
ps.check("A1", """
assert isinstance(a1, pd.DataFrame) and len(a1) == len(FK_MAPS) == 12
assert set(a1["property"]) == {p.predicate.split("#")[-1] for p in FK_MAPS}
assert (a1.triples_broken == a1.triples_correct).all(), "the broken graph has as many triples"
assert (a1.materialised_correct > 0).all() and (a1.materialised_broken == 0).all()
assert (a1.rewritten_broken == a1.materialised_correct).all()
assert (~a1.agree_broken.astype(bool)).all()
# The probe must be a faithful query: on the CORRECT mapping both paths agree, for all 24 properties.
for p in A.TRUST_MAPPINGS["properties"]:
    q = probe_query(p, RANGE[p.predicate.split("#")[-1]])
    left = ch8.answers_via_materialisation(conn, q, graph=full_graph)
    assert left and left == ch8.answers_via_rewriting(conn, q, A.TRUST_MAPPINGS), p.predicate
""")
ps.written("""
Every component does exactly what it was told. The mapper was told to emit a literal and
emitted one; `"1"` is a perfectly valid RDF literal, so the triple store accepts it; the
SPARQL query asks for `?o a med:Ward`, and no literal is ever a Ward, so it correctly
returns *nothing*. The triple count is identical (a literal replaces an IRI one for one),
so volume checks and load logs look normal. Rewriting is unaffected — it joins on the raw
column values (`patient.ward_id = ward.id`) and never looks at the object template —
which is precisely why the two paths disagree and why agreement is a detector.

The bug is first *noticed* downstream, as an empty or too-small answer that looks like a
fact: the bed board shows no patients in cardiology, a cohort query finds no cardiac
patients, the controlled-drugs trail has no prescribers. The person who notices is a
clinician or analyst who knows the answer is implausible — weeks later, after decisions
may have been taken on the empty result. An empty answer is the most dangerous kind of
wrong answer, because "no results" is a legitimate answer.
""")

ps.problem("A2", "Two detectors, and what each one misses", 10, """
(a) Write `lint_mapping(conn, mappings) -> list[dict]`, a schema-aware lint returning one
`{"property": <local name>, "issue": ...}` per defective property map, where `issue` is

* `"fk-as-literal"` — the object column is a **declared** foreign key (`A.foreign_keys`)
  but the object is a literal;
* `"wrong-target"` — a declared foreign key whose IRI template is not the template of
  the referenced table's class (`A.class_for_table`, `A.CLASS_MAPS`);
* `"attribute-as-iri"` — not a foreign key, but mapped to an IRI.

(b) Three realistic defects are provided below. For each, build `a2` with columns
`defect`, `lint_issues` (the issues your lint reports), `agreement_detects` (do the two
execution paths disagree on your A1 probe query, written against the property's
**ontology range** `RANGE`?) and `connected_share` (share of the property's objects that
are typed instances of its range, from `A.object_profile`; 0 for a datatype property).

In writing: which detector catches which defect, and why? Name one defect *neither*
catches, and say what would. Which of the two would you make a blocking CI check?
""", auto_points=5)
ps.code("""
by_name = {p.predicate.split("#")[-1]: p for p in A.TRUST_MAPPINGS["properties"]}
DEFECTS = {
    # a foreign key mapped as a literal (A1's bug)
    "fk-as-literal": dataclasses.replace(by_name["inWard"], object_template=None),
    # a plain attribute given an IRI template: 'cardiology' becomes a resource
    "attribute-as-iri": dataclasses.replace(by_name["speciality"],
                                            object_template=A.CLASS_MAPS["Ward"].template),
    # the right idea, the wrong table: ward ids turned into Bed IRIs (bed 1..3 exist!)
    "wrong-target": dataclasses.replace(by_name["inWard"],
                                        object_template=A.CLASS_MAPS["Bed"].template),
}
""")
ps.todo(
    stub="""
    def lint_mapping(conn, mappings) -> list[dict]:
        # TODO (a)
        raise NotImplementedError

    a2 = None   # TODO (b): one row per defect in DEFECTS
    """,
    solution="""
    def lint_mapping(conn, mappings) -> list[dict]:
        fks = A.foreign_keys(conn)
        issues = []
        for p in mappings["properties"]:
            name = p.predicate.split("#")[-1]
            ref = fks.get((p.table, p.object_column))
            if ref is None:
                if p.object_template is not None:
                    issues.append({"property": name, "issue": "attribute-as-iri"})
            elif p.object_template is None:
                issues.append({"property": name, "issue": "fk-as-literal"})
            elif p.object_template != A.CLASS_MAPS[A.class_for_table(ref[0])].template:
                issues.append({"property": name, "issue": "wrong-target"})
        return issues

    classes = A.class_graph(conn)
    rows = []
    for defect, pmap in DEFECTS.items():
        mappings = swap(A.TRUST_MAPPINGS, pmap)
        name = pmap.predicate.split("#")[-1]
        q = probe_query(pmap, RANGE[name])
        left = ch8.answers_via_materialisation(conn, q, mappings)
        right = ch8.answers_via_rewriting(conn, q, mappings)
        profile = A.object_profile(conn, pmap, classes)
        typed = profile["typed_as"].get(RANGE[name], 0)
        rows.append({"defect": defect,
                     "lint_issues": [i["issue"] for i in lint_mapping(conn, mappings)],
                     "agreement_detects": left != right,
                     "connected_share": typed / profile["triples"]})
    a2 = pd.DataFrame(rows)
    a2
    """)
ps.check("A2", """
assert lint_mapping(conn, A.TRUST_MAPPINGS) == [], "the reviewed mapping must lint clean"
# Foreign keys without an _id suffix, and TEXT foreign keys, must be caught too.
for name in ["fromWard", "prescribedBy", "hasDisorder", "prescribes"]:
    bad = swap(A.TRUST_MAPPINGS, dataclasses.replace(by_name[name], object_template=None))
    assert lint_mapping(conn, bad) == [{"property": name, "issue": "fk-as-literal"}], name
assert isinstance(a2, pd.DataFrame) and set(a2["defect"]) == set(DEFECTS)
got = a2.set_index("defect")
for defect in DEFECTS:
    assert list(got.loc[defect, "lint_issues"]) == [defect], defect
assert bool(got.loc["fk-as-literal", "agreement_detects"])
assert bool(got.loc["wrong-target", "agreement_detects"])
assert not bool(got.loc["attribute-as-iri", "agreement_detects"])
assert (got["connected_share"] == 0).all()
""")
ps.written("""
**Lint** reads the catalogue's declared foreign keys, so it catches all three defects,
including the ones a name-based heuristic misses (`from_ward`, `prescriber` have no
`_id`; `diagnosis.code` and `prescription.drug_code` are TEXT). **Agreement** runs the
same ontology-level query through both paths. Rewriting joins on raw column values and
ignores object templates, so any defect that breaks the *materialised* join but not the
SQL join shows up: fk-as-literal (0 vs 6 rows) and wrong-target (Bed IRIs are not Wards:
0 vs 6). It is blind to attribute-as-iri, because for a datatype-property probe both paths
render the same string (`…/ward/cardiology`) — they agree on the wrong answer. Note also
that wrong-target *does not dangle*: bed ids 1–3 exist, so the graph confidently says
Ada is "in" bed 1. A connectivity check against the declared range (`connected_share`)
flags it; a dangling-IRI check would not.

**Neither** catches an *undeclared* foreign key (a legacy column that references another
table by convention, with no `REFERENCES` clause): the lint has nothing to read, and a
probe written against a literal-ranged property agrees on both paths. What catches it is
the ontology itself: a SHACL shape (`sh:class med:Ward` / `sh:nodeKind sh:IRI` on
`med:inWard`, `sh:datatype` on datatype properties) validated over the materialised
graph, or a data-profiling check that the column's values are a subset of another table's
key.

Make the **lint** blocking — it is deterministic, instant, and needs no data — and run
agreement + SHACL on a fixture extract as a second gate, because they also test the
rewriter, the templates, and the ontology's ranges together.
""")

# =========================================================================== #
ps.part("B", "Build the grader, then the Claude mapping designer", """
The guidelines a scorer can report are in `A.OBDA_RULEBOOK` — ids plus the sentence
GEPA's reflection step will read:
""")
ps.code("""
for rule in A.OBDA_RULEBOOK:
    print(f"{rule.id:34s} {rule.description[:84]}")
""")

ps.problem("B1", "A grader that executes the decision", 14, """
Implement `obda_scorer(gold, pred) -> ev.ScoreReport`. `pred` has string fields
`object_kind`, `target_class`, `strategy`. Normalise each (strip whitespace, quotes and
a trailing full stop; lower-case; accept the US spelling `materialize`; match class
names case-insensitively). Then:

| stage | outcome | score | `violated` |
|---|---|---|---|
| contract | `object_kind` ∉ {iri, literal} or `strategy` ∉ {materialise, rewrite} | 0.0 overall | `["answer-in-the-contract"]` |
| mapping (0.5) | `iri` with a `target_class` that is not a key of `A.CLASS_MAPS` | +0 | `answer-in-the-contract` |
| | the predicted property map produces **exactly** the gold map's triples (`A.property_triples`) | +0.5 | — |
| | gold is an IRI, predicted a literal | +0 | `iri-for-foreign-keys` |
| | gold is a literal, predicted an IRI | +0 | `literal-for-attributes` |
| | both IRIs, wrong class | +0 | `reference-the-right-table` |
| strategy (0.5) | equals `gold.gold_strategy` | +0.5 | — |
| | gold materialise, got rewrite / gold rewrite, got materialise | +0 | `materialise-when-refresh-pays` / `rewrite-when-refresh-does-not-pay` |

Mapping violations come before strategy violations. Build the predicted property map
from the gold one (`A.gold_property_map(A.REQUEST_BY_ID[gold.id], conn)`) with only the
object template changed; for a literal the target class is ignored. The `notes` are what
GEPA reads — make them *evidence*, not verdicts: for a foreign key mapped to a literal,
say how many links now join to nothing (use the word **disconnected**); for a wrong
class, where the objects landed (`A.object_profile`); for a strategy error, the
**break-even** number of reads per update against the workload's actual number.
""", auto_points=12)
ps.todo(
    stub="""
    SCORER_CONN = A.build_trust_database()
    MAPPING_RULES = {"answer-in-the-contract", "iri-for-foreign-keys",
                     "reference-the-right-table", "literal-for-attributes"}

    def _norm(value) -> str:
        return str(value or "").strip().strip("'\\"`").rstrip(".").strip().lower()

    def obda_scorer(gold, pred) -> ev.ScoreReport:
        kind = _norm(getattr(pred, "object_kind", ""))
        strategy = _norm(getattr(pred, "strategy", ""))
        target = _norm(getattr(pred, "target_class", ""))
        gold_map = A.gold_property_map(A.REQUEST_BY_ID[gold.id], SCORER_CONN)
        # TODO: contract stage, mapping half, strategy half (see the table)
        raise NotImplementedError
    """,
    solution="""
    SCORER_CONN = A.build_trust_database()
    SCORER_CLASSES = A.class_graph(SCORER_CONN)
    MAPPING_RULES = {"answer-in-the-contract", "iri-for-foreign-keys",
                     "reference-the-right-table", "literal-for-attributes"}
    CLASS_BY_LOWER = {name.lower(): name for name in A.CLASS_MAPS}

    def _norm(value) -> str:
        return str(value or "").strip().strip("'\\"`").rstrip(".").strip().lower()

    def break_even(refresh_queries, c_rw=A.PLATFORM_COSTS["rewrite"],
                   c_mat=A.PLATFORM_COSTS["materialised"]):
        return refresh_queries * c_rw / (c_rw - c_mat)

    def obda_scorer(gold, pred) -> ev.ScoreReport:
        kind = _norm(getattr(pred, "object_kind", ""))
        strategy = _norm(getattr(pred, "strategy", ""))
        target = _norm(getattr(pred, "target_class", ""))
        gold_map = A.gold_property_map(A.REQUEST_BY_ID[gold.id], SCORER_CONN)
        strategy = "materialise" if strategy == "materialize" else strategy
        if kind not in {"iri", "literal"} or strategy not in {"materialise", "rewrite"}:
            return ev.ScoreReport(0.0, [f"Unusable answer: object_kind={kind!r}, "
                                        f"strategy={strategy!r}. Answer with the exact labels."],
                                  ["answer-in-the-contract"])
        notes, violated, score = [], [], 0.0
        column = f"{gold.table}.{gold.object_column}"

        # -- mapping half: execute the proposed map and compare triples -------------
        if kind == "iri" and target not in CLASS_BY_LOWER:
            notes.append(f"target_class {target!r} is not a mapped class; choose one of "
                         f"{sorted(A.CLASS_MAPS)}.")
            violated.append("answer-in-the-contract")
        else:
            template = None if kind == "literal" else A.CLASS_MAPS[CLASS_BY_LOWER[target]].template
            pred_map = dataclasses.replace(gold_map, object_template=template)
            if A.property_triples(SCORER_CONN, pred_map) == A.property_triples(SCORER_CONN, gold_map):
                score += 0.5
                notes.append(f"Mapping of {column} reproduces the reviewed triples.")
            else:
                profile = A.object_profile(SCORER_CONN, pred_map, SCORER_CLASSES)
                n = profile["triples"]
                if gold.gold_object_kind == "iri" and kind == "literal":
                    violated.append("iri-for-foreign-keys")
                    notes.append(f"{column} is a declared foreign key to the "
                                 f"{gold.gold_target_class} table, but was mapped to a literal: "
                                 f"{profile['literals']} of {n} links are now plain values that "
                                 f"join to no {gold.gold_target_class}; the graph is silently "
                                 f"disconnected and every query through med:{gold.predicate} "
                                 f"returns nothing.")
                elif gold.gold_object_kind == "literal":
                    violated.append("literal-for-attributes")
                    notes.append(f"{column} has no REFERENCES clause; it holds values. As IRIs, "
                                 f"{profile['dangling']} of {n} objects dangle (no such resource) "
                                 f"and {sum(profile['typed_as'].values())} collide with unrelated "
                                 f"instances {profile['typed_as']}.")
                else:
                    violated.append("reference-the-right-table")
                    notes.append(f"{column} references the {gold.gold_target_class} table, but "
                                 f"its IRIs were built as {CLASS_BY_LOWER[target]}: objects land "
                                 f"on {profile['typed_as'] or 'no instances'}, "
                                 f"{profile['dangling']} of {n} dangle.")

        # -- strategy half: against the MDP's optimal policy ---------------------
        be = break_even(gold.refresh_queries)
        if strategy == gold.gold_strategy:
            score += 0.5
        else:
            violated.append("materialise-when-refresh-pays" if gold.gold_strategy == "materialise"
                            else "rewrite-when-refresh-does-not-pay")
            notes.append(f"Strategy {strategy!r} is not optimal: with a refresh costing "
                         f"{gold.refresh_queries:g} rewritten queries the break-even is "
                         f"{be:.1f} reads per update, and this workload has "
                         f"{gold.reads_per_update}; the MDP's optimal policy is "
                         f"{gold.gold_strategy!r}.")
        return ev.ScoreReport(score, notes, violated)
    """)
ps.check("B1", """
P = lambda k, t, s: dspy.Prediction(object_kind=k, target_class=t, strategy=s)
fk = EXAMPLES["fromward-flow"]          # transfer.from_ward -> Ward; rewrite
attr = EXAMPLES["nhsnumber-mpi"]        # patient.nhs_number -> literal; materialise
cases = [
    (fk, P("iri", "Ward", "rewrite"), 1.0, []),
    (fk, P(" IRI.", "ward", "Rewrite"), 1.0, []),
    (fk, P("iri", "Ward", "materialise"), 0.5, ["rewrite-when-refresh-does-not-pay"]),
    (fk, P("literal", "none", "rewrite"), 0.5, ["iri-for-foreign-keys"]),
    (fk, P("iri", "Transfer", "rewrite"), 0.5, ["reference-the-right-table"]),
    (fk, P("literal", "none", "materialise"), 0.0,
     ["iri-for-foreign-keys", "rewrite-when-refresh-does-not-pay"]),
    (fk, P("iri", "Hospital", "rewrite"), 0.5, ["answer-in-the-contract"]),
    (fk, P("a foreign key", "Ward", "rewrite"), 0.0, ["answer-in-the-contract"]),
    (fk, P("iri", "Ward", ""), 0.0, ["answer-in-the-contract"]),
    (attr, P("literal", "none", "materialise"), 1.0, []),
    (attr, P("literal", "Patient", "materialize"), 1.0, []),
    (attr, P("iri", "Patient", "materialise"), 0.5, ["literal-for-attributes"]),
    (attr, P("literal", "none", "rewrite"), 0.5, ["materialise-when-refresh-pays"]),
    (EXAMPLES["hasdisorder-cohort"], P("literal", "none", "materialise"), 0.5,
     ["iri-for-foreign-keys"]),
]
for gold, pred, score, violated in cases:
    r = obda_scorer(gold, pred)
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (gold.id, pred, r.score, r.violated)
    assert all(v in A.OBDA_RULEBOOK for v in r.violated)
r = obda_scorer(fk, P("literal", "none", "materialise"))
assert any("disconnected" in n for n in r.notes), "say that the graph is disconnected"
assert any("break-even" in n for n in r.notes), "give the break-even number of reads"
# Gold answers score 1.0 on every item.
for ex in EXAMPLES.values():
    assert obda_scorer(ex, P(ex.gold_object_kind, ex.gold_target_class, ex.gold_strategy)).score == 1.0
""")

ps.problem("B2", "The mapping designer as a DSPy program", 7, """
Write a signature `MappingDecision` with inputs `request`, `workload` and `schema`, and
outputs `object_kind`, `target_class`, `strategy` and `justification`; and a factory
`OBDADesigner(instruction)` returning a `dspy.Module` with a single `dspy.Predict` whose
instruction is `instruction`. The field descriptions are part of the prompt — state the
allowed labels in them (manual marks). Configure Claude and run the program once on
`train[0]`.
""", auto_points=4)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    # TODO: class MappingDecision(dspy.Signature): ...
    # TODO: def OBDADesigner(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: OBDADesigner()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    class MappingDecision(dspy.Signature):
        \"\"\"Decide how one source column is mapped into the ontology and how its consumer is served.\"\"\"

        request: str = dspy.InputField(desc="the integration request: column, property, subject, consumer")
        workload: str = dspy.InputField(
            desc="how often the consumer reads versus how often the source changes, and costs")
        schema: str = dspy.InputField(desc="the source database DDL, with REFERENCES clauses")
        object_kind: str = dspy.OutputField(desc="exactly 'iri' or 'literal'")
        target_class: str = dspy.OutputField(
            desc="for an IRI, the class of the referenced rows (Ward, Bed, Staff, Patient, "
                 "Admission, Transfer, Disorder, Drug, Prescription, LabResult); 'none' for a literal")
        strategy: str = dspy.OutputField(desc="exactly 'materialise' or 'rewrite'")
        justification: str = dspy.OutputField(desc="one or two sentences citing the schema and the numbers")

    def OBDADesigner(instruction: str = BASELINE_INSTRUCTION):
        class _Designer(dspy.Module):
            def __init__(self):
                super().__init__()
                self.decide = dspy.Predict(MappingDecision.with_instructions(instruction))

            def forward(self, request: str, workload: str, schema: str):
                return self.decide(request=request, workload=workload, schema=schema)

        return _Designer()

    lm = llm.configure_dspy()
    smoke = OBDADesigner()(**train[0].inputs())
    print(train[0].id, "->", smoke.object_kind, smoke.target_class, smoke.strategy)
    print(smoke.justification)
    """)
ps.check("B2", """
assert set(MappingDecision.input_fields) == {"request", "workload", "schema"}
assert {"object_kind", "target_class", "strategy"} <= set(MappingDecision.output_fields)
program = OBDADesigner("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert all(isinstance(getattr(smoke, f), str) for f in ["object_kind", "target_class", "strategy"])
""")

ps.problem("B3", "Baseline on dev — which decision is it getting wrong?", 9, """
The score mixes two independent decisions, so a mean alone cannot tell you what to fix.
Write `dimension_accuracy(result) -> {"mapping": float, "strategy": float}` from the
per-row `violated` lists of an `ev.evaluate_dataset` result (a row's mapping is right
iff it violates none of `MAPPING_RULES`; its strategy is right iff it violates neither
strategy rule nor `answer-in-the-contract`).

Evaluate the baseline on `dev` inside `llm.meter(lm)`; store `baseline_dev`,
`baseline_dev_cost` and `baseline_dims`. Then write an **error analysis**: for each
non-perfect item, which guideline, and *why* you think Claude chose as it did. Did it
follow the rule of thumb "live data → rewrite" where the numbers said otherwise?
""", auto_points=3)
ps.todo(
    stub="""
    def dimension_accuracy(result) -> dict:
        # TODO
        raise NotImplementedError

    # TODO: baseline_dev, baseline_dev_cost, baseline_dims
    """,
    solution="""
    STRATEGY_RULES = {"answer-in-the-contract", "materialise-when-refresh-pays",
                      "rewrite-when-refresh-does-not-pay"}

    def dimension_accuracy(result) -> dict:
        rows = result["rows"]
        mapping_ok = [not (set(r["violated"]) & MAPPING_RULES) for r in rows]
        strategy_ok = [not (set(r["violated"]) & STRATEGY_RULES) for r in rows]
        return {"mapping": sum(mapping_ok) / len(rows), "strategy": sum(strategy_ok) / len(rows)}

    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(OBDADesigner(), dev, obda_scorer)
    baseline_dims = dimension_accuracy(baseline_dev)
    print("mean:", baseline_dev["mean_score"], " by decision:", baseline_dims)
    print("violations:", baseline_dev["violations"], "\\ncost:", baseline_dev_cost)
    pd.DataFrame(baseline_dev["rows"])
    """)
ps.check("B3", """
fake = {"rows": [{"item": "a", "score": 1.0, "violated": []},
                 {"item": "b", "score": 0.5, "violated": ["iri-for-foreign-keys"]},
                 {"item": "c", "score": 0.5, "violated": ["materialise-when-refresh-pays"]},
                 {"item": "d", "score": 0.0, "violated": ["answer-in-the-contract"]}]}
assert dimension_accuracy(fake) == {"mapping": 0.5, "strategy": 0.5}
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert baseline_dims == dimension_accuracy(baseline_dev)
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
The answer to hand in is the analysis of *your* run; a typical baseline shows two very
different error profiles.

* **Mapping shape — mostly right, with named traps.** Claude reads `REFERENCES` clauses
  well, so plain `*_id` foreign keys are usually IRIs. The errors cluster where names
  mislead: `referring_gp` *sounds* like a reference to a person (it is free text, no
  `REFERENCES` → literal), and occasionally a class is inferred from the column name
  rather than the referenced table. These are reading errors, fixable by an instruction
  that says "the REFERENCES clause decides, not the name".
* **Strategy — the rule of thumb.** Without the break-even rule the model tends to map
  "live / as it happens" to *rewrite* and "research / history / monthly" to
  *materialise*. On dev that is right for most items but wrong exactly on the trap
  items: the *nurse-rota planner* (cheap refresh, many reads → materialise) is usually
  fine, but the *retrospective research extract* (rarely updated **and** rarely read,
  huge refresh → rewrite) is typically materialised. That is a genuine economic error,
  not a format error: the numbers were in the input and were not used.
* **Contract** errors (`Materialize the graph`, `IRI (Ward)`) should be rare but are
  possible; the scorer's normalisation absorbs case and spelling, not prose.

Cost: 8 calls, on the order of $0.2–0.4 at the estimated per-call price — the unit price
of every later comparison.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
**Optimise on `train`, select on `dev`, report on `test`** — and put a cost and a noise
estimate next to every number. Every metric call is a billed request.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 12, """
1. Build the GEPA feedback metric from your scorer and `A.OBDA_RULEBOOK`, and a separate
   reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare the baseline and the tuned program on **`test`** with `opt.compare` (store as
   `c1`), print `c1.report()`, and report `dimension_accuracy` before and after.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch08_obda_designer_instruction.txt"`.

In writing: read the instruction diff. Which guidelines did GEPA write down, which did it
miss — and was each missed guideline ever *violated* on train? Did it write the
break-even rule as a rule, or memorise training workloads?
""", auto_points=6)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch08_obda_designer_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(obda_scorer, A.OBDA_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(OBDADesigner(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(OBDADesigner(), tuned, test, obda_scorer)
    print(c1.report())
    print("\\nby decision, before:", dimension_accuracy(c1.before),
          " after:", dimension_accuracy(c1.after))
    print("GEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch08_obda_designer_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
ids = lambda rows: {ex.id for ex in rows}
assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test)
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 200
""")
ps.written("""
What to look for (the wording of your run will differ):

* **Written down.** A good run states the output contract, "a declared REFERENCES clause
  makes an IRI of the referenced table's class, whatever the column is called", and some
  form of the break-even rule — ideally *as a formula over the workload's numbers*
  ("materialise when reads per update × 0.25 exceeds the refresh cost × 0.30"). These come
  straight from the scorer's notes, which carry the break-even number on every strategy
  error.
* **Missed — and why.** A guideline appears only if its failure appeared in the training
  feedback. If Claude never mapped an attribute to an IRI on train, `literal-for-attributes`
  gets no feedback and cannot be learnt; that is not a GEPA failure, it is an absence of
  evidence. Check the train violation histogram before blaming the optimiser — and
  check whether the *test* split needs the missing rule (here: `referring_gp`-style
  attributes, `unit-archive`-style rarely-read-and-huge workloads).
* **Memorised.** Lines like "for bed-management workloads, materialise" or lists of the
  training columns are overfitting to eight items: they cost tokens on every call and
  generalise only by accident.

A test delta near zero, or negative, is a legitimate result to report with its cost.
""")

ps.problem("C2", "Three programs, two decisions, one table", 8, """
Add the **hand-written guidelines** —
`A.OBDA_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)` — as a third contender. Evaluate
baseline, guidelines and GEPA-tuned on `test`, each inside its own `llm.meter`, and build
`c2` with columns `program` (`"baseline"`, `"guidelines"`, `"gepa"`), `test_mean`,
`mapping_acc`, `strategy_acc`, `violations`, `eval_usd`, `optimisation_usd` (the GEPA
cost for `"gepa"`, 0 otherwise) and `instruction_chars`.

In writing: which would you deploy for the platform team, and what would change your
mind?
""", auto_points=3)
ps.todo(
    stub="""
    guidelines_instruction = A.OBDA_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    c2 = None    # TODO
    """,
    solution="""
    guidelines_instruction = A.OBDA_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    contenders = {"baseline": OBDADesigner(),
                  "guidelines": OBDADesigner(guidelines_instruction),
                  "gepa": tuned}
    rows = []
    for name, program in contenders.items():
        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, test, obda_scorer)
        dims = dimension_accuracy(result)
        rows.append({"program": name, "test_mean": result["mean_score"],
                     "mapping_acc": dims["mapping"], "strategy_acc": dims["strategy"],
                     "violations": result["violations"], "eval_usd": cost["usd"],
                     "optimisation_usd": gepa_cost["usd"] if name == "gepa" else 0.0,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    c2
    """)
ps.check("C2", """
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "guidelines", "gepa"}
assert {"test_mean", "mapping_acc", "strategy_acc", "violations", "eval_usd",
        "optimisation_usd", "instruction_chars"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines"], "optimisation_usd"].eq(0).all()
assert c2[["mapping_acc", "strategy_acc"]].apply(lambda s: s.between(0, 1)).all().all()
""")
ps.written("""
Expect the guidelines to close most of the *strategy* gap at zero optimisation cost:
the break-even rule is the knowledge, and once it is written down the model applies it
to the numbers in the workload. Mapping accuracy is usually already high, so the
per-decision columns matter more than the mean — a program that improves strategy
while regressing one mapping item has traded a slow service for a silently
disconnected one, which is the worse failure.

Deploy the cheapest program whose test score is within noise (C3) of the best — usually
the guidelines. Change your mind if GEPA's gain survives the noise estimate *and* is on
the mapping decision (the silent one), or if new request types (e.g. many-to-many link
tables) produce failures the rulebook does not cover. Either way, do not rely on the
model for the mapping shape alone: the A2 lint decides that deterministically, and the
model's role there is to explain, not to decide.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 8, """
Eight test items at temperature 1.0: one item is 0.0625 of mean score per half-decision.
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)` and
`with dspy.context(lm=fresh): ...`), run the baseline and the GEPA-tuned programs on
`test` three times each; store the mean scores in `runs = {"baseline": [..3..], "gepa":
[..3..]}` and the spend in `c3_cost`.

Set `verdict_c3` to `"significant"` if `|mean_gepa - mean_baseline| > 2 * max(sd_gepa,
sd_baseline)` (sample standard deviations), else `"not significant"`. In writing: what
does this say about C1, and what would a credible evaluation of this system need?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs (inside llm.meter(fresh) as c3_cost), then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    import statistics as st

    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(OBDADesigner(), test, obda_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, obda_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
import statistics as _st
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
assert {"calls", "usd"} <= set(c3_cost)
_m = {k: _st.mean(v) for k, v in runs.items()}
_s = {k: _st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
""")
ps.written("""
Three runs is a crude noise estimate, but it stops over-claiming. If one program's
run-to-run spread is as large as the gap between programs, the C1 delta is not evidence.
Note the degenerate case: if both programs are perfectly stable (sd = 0), *any* non-zero
delta is "significant" by this rule — the rule is a screen, not a test. A credible
evaluation needs more items (8 test items resolve differences of about ±0.1), repeated
runs reported as mean ± sd or a paired bootstrap over items, both decisions reported
separately, and the cost of each run. The honest sentence is "GEPA changed the mean test
score by X ± Y over 3 runs of 8 items, at a cost of $Z" — not "GEPA improved accuracy".
""")

# =========================================================================== #
ps.part("D", "A design-review agent, and the price of staleness", """
The agent gets four tools over the Trust database: `inspect_schema` (tables, columns,
declared foreign keys), `list_classes` (class maps and IRI templates), `check_mapping`
(materialise one candidate property map and report where its objects land: typed
instances, literals, dangling IRIs) and `price_strategy` (solve the materialise-or-
rewrite MDP for a workload's numbers). A design that has not been *tried* is a guess.
""")
ps.code("""
ws_demo = A.TrustWorkspace()
demo_tools = {t.name: t for t in A.build_trust_tools(ws_demo)}
print(demo_tools["check_mapping"].invoke({"table": "transfer", "subject_column": "id",
      "object_column": "from_ward", "object_kind": "literal"}))
print(demo_tools["check_mapping"].invoke({"table": "transfer", "subject_column": "id",
      "object_column": "from_ward", "object_kind": "iri", "target_class": "Ward"}))
print(demo_tools["price_strategy"].invoke({"reads_per_update": 1, "refresh_cost_in_queries": 5}))
print(ws_demo.log.names())
""")

ps.problem("D1", "Build and evaluate the design-review agent", 12, """
1. Write `REVIEW_PROMPT`, the agent's system prompt. It must make the agent inspect the
   schema, **try its mapping with `check_mapping`** and accept it only if every object
   lands on the intended class (or is a literal, for an attribute), extract the
   workload's numbers and **price the strategy with `price_strategy`**, and end with a
   JSON object `{"object_kind": ..., "target_class": ..., "strategy": ..., "verified":
   true|false}`.
2. Write `parse_decision(text) -> dict | None`: the last JSON object in the text (code
   fences and surrounding prose allowed) that has `object_kind` and `strategy`, returned
   as `{"object_kind", "target_class", "strategy"}` strings (`target_class` defaults to
   `"none"`); `None` if there is none.
3. For every **test** request, build a fresh `A.TrustWorkspace()`, its tools, an agent
   (`agents.build_agent(ws, system_prompt=..., tools=...)`), and run it on
   `ex.request + "\\n\\nWorkload: " + ex.workload`. Collect `d1` with columns `id`,
   `object_kind`, `target_class`, `strategy` (parsed, `None` when unparseable), `score`
   (your `obda_scorer`; 0 when unparseable), `checked_mapping`, `priced` (did the log
   contain those tool calls?), `tool_calls`, `usd_estimate` (`llm.chat_usage`).

In writing: report the mean score with its n and the cost per request; compare with the
DSPy designer on the same test items; examine every error. Why is `check_mapping` worth
more than a sentence in the prompt?
""", auto_points=5)
ps.todo(
    stub="""
    REVIEW_PROMPT = \"\"\"TODO\"\"\"

    def parse_decision(text: str) -> dict | None:
        # TODO
        raise NotImplementedError

    d1 = None   # TODO: run the agent on every test request
    """,
    solution="""
    import re

    REVIEW_PROMPT = \"\"\"\\
    You are the design reviewer for Northgate Regional Health Trust's ontology-based data
    access platform. For one integration request you decide (1) how the source column is
    mapped and (2) how the consumer's queries are served. Use your tools; do not guess.

    Mapping:
    1. inspect_schema. If the column is a DECLARED foreign key (it has a REFERENCES clause),
       it maps to an IRI of the class whose table it references (list_classes gives the
       table of each class), whatever the column is called. Otherwise it is a literal.
    2. check_mapping with your candidate. Accept an IRI only if every object is typed as
       the intended class (typed_as covers all triples, dangling = 0); accept a literal
       only for a column that is not a foreign key. If the check contradicts you, revise.

    Strategy:
    3. Read the workload: reads between consecutive updates, and the refresh cost in
       rewritten-query units. Call price_strategy with those numbers and adopt its result.

    End your reply with one JSON object and nothing after it:
    {"object_kind": "iri" | "literal", "target_class": "<Class>" | "none",
     "strategy": "materialise" | "rewrite", "verified": true | false}
    \"\"\"

    def parse_decision(text: str) -> dict | None:
        for blob in reversed(re.findall(r"\\{[^{}]*\\}", text or "")):
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "object_kind" in data and "strategy" in data:
                return {"object_kind": str(data["object_kind"]),
                        "target_class": str(data.get("target_class") or "none"),
                        "strategy": str(data["strategy"])}
        return None

    rows = []
    for ex in test:
        ws = A.TrustWorkspace()
        agent, _ = agents.build_agent(ws, system_prompt=REVIEW_PROMPT,
                                      tools=A.build_trust_tools(ws))
        run = agents.run_agent(agent, ws, ex.request + "\\n\\nWorkload: " + ex.workload)
        decision = parse_decision(run.answer)
        score = obda_scorer(ex, dspy.Prediction(**decision)).score if decision else 0.0
        names = ws.log.names()
        rows.append({"id": ex.id, **(decision or {"object_kind": None, "target_class": None,
                                                  "strategy": None}),
                     "score": score, "checked_mapping": "check_mapping" in names,
                     "priced": "price_strategy" in names, "tool_calls": len(names),
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(f"mean score {d1.score.mean():.3f} on n={len(d1)}; "
          f"cost ≈ ${d1.usd_estimate.sum():.3f} total, ${d1.usd_estimate.mean():.3f}/request")
    d1
    """)
ps.check("D1", """
assert parse_decision('{"object_kind": "iri", "target_class": "Ward", "strategy": "rewrite", "verified": true}') \\
    == {"object_kind": "iri", "target_class": "Ward", "strategy": "rewrite"}
assert parse_decision('Checked.\\n```json\\n{"object_kind": "literal", "strategy": "materialise"}\\n```') \\
    == {"object_kind": "literal", "target_class": "none", "strategy": "materialise"}
assert parse_decision('{"triples": 6} then {"object_kind": "iri", "target_class": "Staff", '
                      '"strategy": "rewrite"}')["target_class"] == "Staff"
assert parse_decision('I would map it as an IRI.') is None
assert parse_decision('{"verdict": "yes"}') is None
assert isinstance(d1, pd.DataFrame) and list(d1["id"]) == [ex.id for ex in test]
assert {"id", "object_kind", "target_class", "strategy", "score", "checked_mapping", "priced",
        "tool_calls", "usd_estimate"} <= set(d1.columns)
for ex, row in zip(test, d1.to_dict("records")):
    if row["object_kind"] is None:
        assert row["score"] == 0.0
    else:
        pred = dspy.Prediction(object_kind=row["object_kind"], target_class=row["target_class"],
                               strategy=row["strategy"])
        assert abs(row["score"] - obda_scorer(ex, pred).score) < 1e-9, ex.id
""")
ps.written("""
With this procedure the agent typically gets both decisions right on most or all eight
test items (report it as "mean 0.9x on n = 8", not as a percentage of anything larger),
with 4–7 tool calls per request and a cost several times the DSPy designer's per item —
it reads the whole schema and makes several turns. Where it errs, look at the log: an
error with `checked_mapping == False` is a skipped verification (tighten the prompt); an
error *after* a check means the agent misread the check's output, which is rarer.

Why the tool beats the prompt: the rule "foreign keys become IRIs" is advice, and advice
is followed unevenly — especially on `to_ward`-style names or TEXT keys. `check_mapping`
turns the rule into an observation: *six literals, zero typed Ward instances* is not
open to interpretation. It needs no gold answer, it keeps working when the prompt is
rewritten or the model is swapped, and it would equally catch a human's mistake. The same
holds for `price_strategy`: the model's job shrinks to extracting two numbers from prose,
which it does reliably; the economics are computed, not recalled. The remaining risk is
extraction (e.g. reading "about 18 reads between two reassignments" as 1), which is why
the tool's inputs belong in the audit log.
""")

ps.problem("D2", "When does materialising pay — and what if staleness were free?", 10, """
`A.MaterialisationMDP.for_workload(r, N)` builds a periodic workload — `r` queries, then
one update, twice — with a refresh priced at `N` rewritten queries (serving costs:
rewrite 0.30, from the copy 0.05; a correct answer earns 1; a stale answer earns 0).

1. Derive, on paper, the break-even reads per update `r*` above which refreshing and
   serving from the copy beats rewriting, as a function of `N` and the two serving costs;
   implement it as `breakeven_reads(N, cost_rewrite=0.30, cost_materialised=0.05)`.
2. Verify it: for `N` in `[1, 3, 6]` and `r` in `1..12`, solve the MDP with
   `mdp.value_iteration`, roll out the greedy policy, and record in `d2` (columns
   `refresh_queries`, `reads_per_update`, `share_from_copy`, `materialises`) whether
   the optimal policy serves most queries from the copy.
3. Write `LatencyOnlyMDP`, a subclass whose reward ignores staleness (a stale copy's
   answer earns `1 - cost_materialised` like a fresh one). On the default workload
   `"qquqqquq"`, count the queries the optimal policy answers from a **stale** copy under
   each reward: `stale_latency_only` and `stale_priced`.

In writing: interpret `r*` for the Trust's requests, and name two things the MDP leaves
out that a platform team would have to add before trusting it for a real SLA.
""", auto_points=6)
ps.code("""
M = A.MaterialisationMDP()            # workload 'qquqqquq', refresh 0.50
V, pi = mdp.value_iteration(M)
state = M.initial_state()
while not M.is_terminal(state):
    print("  " + M.describe(state, pi[state]))
    state = M.transition(state, pi[state])[0][1]
print(f"V*(s0) = {V[M.initial_state()]:.3f}")
""")
ps.todo(
    stub="""
    def breakeven_reads(N: float, cost_rewrite: float = 0.30,
                        cost_materialised: float = 0.05) -> float:
        # TODO (1)
        raise NotImplementedError

    d2 = None                     # TODO (2)

    class LatencyOnlyMDP(A.MaterialisationMDP):
        pass                      # TODO (3)

    stale_latency_only = None     # TODO (3)
    stale_priced = None
    """,
    solution="""
    def breakeven_reads(N: float, cost_rewrite: float = 0.30,
                        cost_materialised: float = 0.05) -> float:
        # per cycle: rewrite r*(1 - c_rw)  vs  refresh + copy  r*(1 - c_mat) - N*c_rw
        # => materialise iff r * (c_rw - c_mat) > N * c_rw
        return N * cost_rewrite / (cost_rewrite - cost_materialised)

    def served_from_copy(M, policy_table):
        episode = mdp.run_episode(M, mdp.greedy_policy(policy_table), max_steps=len(M.workload) + 1)
        served = [a for a in episode.actions if a.startswith("serve:")]
        return sum(a != "serve:rewrite" for a in served) / len(served), episode

    rows = []
    for N in [1, 3, 6]:
        for r in range(1, 13):
            Mr = A.MaterialisationMDP.for_workload(r, N)
            _, pir = mdp.value_iteration(Mr)
            share, _ = served_from_copy(Mr, pir)
            rows.append({"refresh_queries": N, "reads_per_update": r,
                         "share_from_copy": round(share, 3), "materialises": share > 0.5})
    d2 = pd.DataFrame(rows)
    print({N: round(breakeven_reads(N), 2) for N in [1, 3, 6]})
    print(d2.pivot(index="reads_per_update", columns="refresh_queries", values="materialises").T)

    class LatencyOnlyMDP(A.MaterialisationMDP):
        \"\"\"Rewards speed and ignores correctness -- a latency-only dashboard SLA.\"\"\"

        def transition(self, state, action):
            if action == "serve:materialised":
                return [(1.0, A.ServeState(state.index + 1, state.fresh),
                         1.0 - self.cost_materialised)]
            return super().transition(state, action)

    def stale_serves(M):
        _, table = mdp.value_iteration(M)
        episode = mdp.run_episode(M, mdp.greedy_policy(table), max_steps=len(M.workload) + 1)
        return sum(t.action == "serve:materialised" and not t.state.fresh
                   for t in episode.transitions)

    stale_latency_only = stale_serves(LatencyOnlyMDP("qquqqquq"))
    stale_priced = stale_serves(A.MaterialisationMDP("qquqqquq"))
    print("stale answers -- latency-only reward:", stale_latency_only, "| priced:", stale_priced)
    """)
ps.check("D2", """
assert abs(breakeven_reads(2) - 2.4) < 1e-9 and abs(breakeven_reads(4, 0.5, 0.1) - 5.0) < 1e-9
assert isinstance(d2, pd.DataFrame) and set(d2["refresh_queries"]) == {1, 3, 6}
assert set(d2["reads_per_update"]) == set(range(1, 13))
for _, row in d2.iterrows():
    r_star = breakeven_reads(row.refresh_queries)
    if abs(row.reads_per_update - r_star) > 0.25:
        assert bool(row.materialises) == (row.reads_per_update > r_star), dict(row)
assert issubclass(LatencyOnlyMDP, A.MaterialisationMDP)
_s = A.ServeState(0, False)
assert abs(LatencyOnlyMDP("q").transition(_s, "serve:materialised")[0][2] - 0.95) < 1e-9
assert stale_priced == 0 and stale_latency_only == 6
""")
ps.written("""
Per update cycle, rewriting earns `r(1 − c_rw)`; refreshing once and serving from the
copy earns `r(1 − c_mat) − N·c_rw`. Materialising pays iff `r(c_rw − c_mat) > N·c_rw`,
i.e. `r* = N·c_rw / (c_rw − c_mat) = 1.2 N` with the Trust's costs — the sweep flips at
1.2, 3.6 and 7.2. So the decision is a *ratio* of reads per update to refresh size, not
"live vs static": the control-room dashboard (18 reads per change, refresh ≈ 2) should
materialise despite being live, and the lab-archive search (4 reads per monthly load,
refresh ≈ 40) should rewrite despite being nearly static.

With staleness free, the optimal policy serves **all six** queries from a copy that is
never refreshed — every answer wrong, every answer fast. It is optimal for the reward it
was given; the lesson is that an SLA on latency alone *pays* for stale answers, so
correctness must be in the objective.

Before trusting this for a real SLA the team would add: (i) **refresh latency on the
critical path** — here a refresh is instantaneous, whereas a real re-materialisation
takes minutes to hours, during which queries are either blocked or stale; (ii)
**stochastic, bursty updates** instead of a known periodic sequence (the policy becomes
a threshold on expected reads before the next update); and (iii) **incremental
maintenance** and **staleness tolerance** (a dashboard that accepts 15-minute-old data
earns partial reward for a slightly stale answer), both of which move `r*`.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
