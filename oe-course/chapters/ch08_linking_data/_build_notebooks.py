"""Generate the Chapter 8 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 8 — Linking Ontologies to Data"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch08_toolkit as ch8
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 8",
        "Every chapter so far has assumed the data was already in the "
        "ontology's vocabulary. It never is. Chapter 8 is about the gap: the "
        "data sits in a relational database that has never heard of your "
        "classes, and the questions are asked in terms that exist only in your "
        "ontology.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | environment check |\n"
            "| 1 | `01_mappings_and_materialisation` | 8.1–8.2 | R2RML-style mappings + an ETL pipeline |\n"
            "| 2 | `02_query_rewriting` | 8.3 | **a query rewriter** — SPARQL to SQL |\n"
            "| 3 | `03_exercises` | 8.4 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude mapping designer graded by *executing* its mappings, a design-review agent, and the **materialise-or-rewrite MDP** |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Write mappings from a relational schema to an ontology, and say why a "
                    "foreign key must become an IRI.",
                    "Implement **both** OBDA strategies and check they agree — the property "
                    "that makes the approach trustworthy.",
                    "Read the SQL a conjunctive query rewrites to, and explain where the "
                    "ontology went.",
                    "Price the materialise-vs-rewrite decision, including the cost of "
                    "**staleness**.",
                ]
            )
        ),
        md(
            "## The two strategies\n\n"
            "| | materialisation | query rewriting |\n|---|---|---|\n"
            "| when | run the mapping once, up front | translate each query at run time |\n"
            "| stores | a copy of everything, as triples | nothing |\n"
            "| query cost | low | a join per atom |\n"
            "| freshness | **stale between refreshes** | always current |\n"
            "| §8.2 calls it | ETL / warehousing | virtual / on-the-fly |\n\n"
            "Both are implemented in `ch08_toolkit` over the *same* mappings, and Notebook 2 "
            "checks that they return identical answers. Once that holds, the choice is an "
            "engineering trade rather than a matter of taste — and the problem set (Notebook 4) prices it."
        ),
        md("### Sanity check: a real database, a real graph"),
        code(
            "conn = ch8.build_database()\n"
            "counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]\n"
            "          for t in ['ward', 'patient', 'diagnosis', 'code_lookup']}\n"
            "print('source rows:', counts)\n"
            "graph = ch8.materialise(conn)\n"
            "print('materialised triples:', len(graph))\n"
            "assert len(graph) > 30"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Mappings and materialisation",
        "Sections 8.1–8.2",
        "A mapping says how rows become triples. It is a small artefact with "
        "one very sharp edge: the difference between an IRI and a literal "
        "decides whether your graph is connected or quietly in pieces.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The source knows nothing about your ontology\n\n"
            "A hospital database, of the kind §8.1 is written about. Note what it does *not* "
            "contain: any notion of a `Patient` class, a `Disorder`, or a category like "
            "'cardiac'. Those live only in the ontology."
        ),
        code("print(ch8.SCHEMA_SQL)"),
        code(
            "conn = ch8.build_database()\n"
            "for table in ['ward', 'patient', 'diagnosis', 'code_lookup']:\n"
            "    rows = conn.execute(f'SELECT * FROM {table}').fetchall()\n"
            "    names = [d[0] for d in conn.execute(f'SELECT * FROM {table}').description]\n"
            "    print(f'-- {table} --')\n"
            "    print(pd.DataFrame(rows, columns=names).to_string(index=False))\n"
            "    print()"
        ),
        md(
            "## 2. The mappings\n\n"
            "Two kinds, following R2RML:\n\n"
            "* a **class map** turns each row of a table into an instance, with an IRI built "
            "from the primary key;\n"
            "* a **property map** turns a pair of columns into a triple. Its object is either "
            "an **IRI** (when the column references another table) or a **literal** (when it "
            "holds a plain value)."
        ),
        code("print(pd.DataFrame(ch8.mapping_report()).to_string(index=False))"),
        code(
            "patient_map = ch8.PATIENT\n"
            "print('class map :', patient_map.rdf_class.split('#')[-1])\n"
            "print('  table   :', patient_map.table)\n"
            "print('  IRI for row id=101 ->', patient_map.iri(101))\n\n"
            "inward = ch8.MAPPINGS['properties'][0]\n"
            "print('\\nproperty map:', inward.predicate.split('#')[-1])\n"
            "print('  ', f'{inward.table}.{inward.subject_column}',\n"
            "      '->', f'{inward.table}.{inward.object_column}')\n"
            "print('  object is an IRI:', inward.object_template is not None)"
        ),
        md(
            "## 3. Materialising\n\n"
            "Run every mapping, collect triples. This is the ETL answer: pay the "
            "transformation once."
        ),
        code(
            "graph = ch8.materialise(conn)\n"
            "print(f'{len(graph)} triples\\n')\n"
            "print(graph.serialize(format='turtle')[:900])"
        ),
        code(
            "from rdflib import URIRef\n"
            "patient101 = URIRef('http://example.org/data/patient/101')\n"
            "print('everything the graph knows about patient 101:')\n"
            "for p, o in graph.predicate_objects(patient101):\n"
            "    print(f'  {p.split(\"#\")[-1].split(\"/\")[-1]:14s} {o}')"
        ),
        md(
            "## 4. The sharp edge: IRI or literal?\n\n"
            "`patient.ward_id` is a foreign key. Mapped to an **IRI** it links the patient to "
            "the ward *resource*. Mapped to a **literal** it produces the number `1` — true, "
            "useless, and silent. Watch what breaks."
        ),
        code(
            "import copy\n"
            "broken = {'classes': ch8.MAPPINGS['classes'],\n"
            "          'properties': [ch8.PropertyMap(p.predicate, p.table, p.subject_column,\n"
            "                                         p.object_column, p.subject_template,\n"
            "                                         None if p.predicate.endswith('inWard')\n"
            "                                         else p.object_template)\n"
            "                         for p in ch8.MAPPINGS['properties']]}\n"
            "broken_graph = ch8.materialise(conn, broken)\n"
            "print('triples, correct mapping:', len(graph))\n"
            "print('triples, broken mapping :', len(broken_graph))\n"
            "print('\\nSame count. Nothing failed, nothing warned.')"
        ),
        code(
            "query = ch8.QUERIES['patients-in-cardiology']\n"
            "good = ch8.answers_via_materialisation(conn, query, graph=graph)\n"
            "bad = ch8.answers_via_materialisation(conn, query, mappings=broken)\n"
            "print('patients in cardiology, correct mapping:', len(good))\n"
            "print('patients in cardiology, broken mapping :', len(bad))\n"
            "assert len(good) == 3 and len(bad) == 0\n"
            "print('\\nThe join through ward_id can never match, because one side is a\\n'\n"
            "      'resource and the other is the number 1. The query returns nothing and\\n'\n"
            "      'no component reports an error. This is the most common OBDA bug and it\\n'\n"
            "      'is invisible to every check except actually running a query.')"
        ),
    ]
    cells += exercise(
        "1.1",
        "Map a new column",
        "The `patient` table has a `name` column. Add a property map producing "
        "`med:patientName` as a **literal**, materialise, and confirm the new triples appear.",
        "# YOUR CODE HERE\n",
        "extra = ch8.PropertyMap(ch8.MED + 'patientName', 'patient', 'id', 'name',\n"
        "                        'http://example.org/data/patient/{}', None)\n"
        "mappings = {'classes': ch8.MAPPINGS['classes'],\n"
        "            'properties': ch8.MAPPINGS['properties'] + [extra]}\n"
        "extended = ch8.materialise(conn, mappings)\n"
        "print('triples before:', len(graph), '-> after:', len(extended))\n"
        "assert len(extended) == len(graph) + 5\n"
        "rows = extended.query('''PREFIX med: <http://example.org/med#>\n"
        "    SELECT ?p ?n WHERE { ?p med:patientName ?n }''')\n"
        "for row in sorted(str(r[1]) for r in rows):\n"
        "    print('  ', row)\n"
        "print('\\nFive patients, five literals. A name is an attribute, not a reference,\\n'\n"
        "      'so a literal is right here -- the opposite call from ward_id.')",
        hint="`object_template=None` makes the object a literal.",
    )
    cells += exercise(
        "1.2",
        "Measure what materialisation costs",
        "Materialisation trades storage for query speed. Grow the database and measure how "
        "the triple count scales against the row count.",
        "# YOUR CODE HERE\n",
        "rows = []\n"
        "for n_patients in [5, 50, 500]:\n"
        "    data = {k: list(v) for k, v in ch8.SAMPLE_ROWS.items()}\n"
        "    data['patient'] = [(100 + i, f'P{i}', (i % 3) + 1) for i in range(n_patients)]\n"
        "    data['diagnosis'] = [(100 + i, ['I21', 'I50', 'J45'][i % 3])\n"
        "                         for i in range(n_patients)]\n"
        "    c = ch8.build_database(data)\n"
        "    g = ch8.materialise(c)\n"
        "    source_rows = sum(len(v) for v in data.values())\n"
        "    rows.append({'patients': n_patients, 'source rows': source_rows,\n"
        "                 'triples': len(g),\n"
        "                 'triples per row': round(len(g) / source_rows, 2)})\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "print('\\nRoughly linear, at about three triples per source row. That is the\\n'\n"
        "      'storage bill for materialisation -- and it must be paid again, in full,\\n'\n"
        "      'every time the source changes enough to matter.')",
    )
    return save(cells, HERE / "01_mappings_and_materialisation.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Query rewriting",
        "Section 8.3",
        "The other strategy: never build the graph. Translate the *query* "
        "instead, and let the database do what databases are good at. This is "
        "the notebook where the ontology disappears at run time.",
    )
    cells += [
        code(BOOT),
        code("conn = ch8.build_database()"),
        md(
            "## 1. A query in the ontology's vocabulary\n\n"
            "The queries are **conjunctive**: class atoms, property atoms and equality "
            "filters. That restriction is not for teaching convenience — rewriting is only "
            "*possible* for fragments like this, which is precisely why OWL 2 QL exists "
            "(Chapter 4 §4.2) and why §8.3 insists on a rewriting-friendly profile."
        ),
        code(
            "query = ch8.QUERIES['cardiac-patients-in-cardiology']\n"
            "print('atoms:')\n"
            "for s, p, o in query.property_atoms:\n"
            "    print(f'  ?{s} {p.split(\"#\")[-1]} ?{o}')\n"
            "print('filters:', query.filters)\n"
            "print('\\nas SPARQL:')\n"
            "print(ch8.to_sparql(query))"
        ),
        md(
            "## 2. The rewriting\n\n"
            "Each atom becomes the table its mapping names; a variable occurring in two "
            "atoms becomes a **join**; the IRI templates are rebuilt with string "
            "concatenation in the SELECT."
        ),
        code("print(ch8.to_sql(query))"),
        md(
            "> **Look at what is not there.** No ontology, no triples, no reasoner — just a "
            "four-table join over the original schema. The ontology was a *compile-time* "
            "artefact: it decided which joins to write, and then it went away. That is the "
            "central idea of §8.3, and the reason rewriting scales to sources far too large "
            "to materialise."
        ),
        md(
            "## 3. The property that makes OBDA trustworthy\n\n"
            "Two completely different execution paths. They must agree — and if they do not, "
            "the mapping is wrong. This check is cheap and it is the only one that catches "
            "the IRI/literal bug from Notebook 1."
        ),
        code(
            "graph = ch8.materialise(conn)\n"
            "rows = []\n"
            "for name, q in ch8.QUERIES.items():\n"
            "    left = ch8.answers_via_materialisation(conn, q, graph=graph)\n"
            "    right = ch8.answers_via_rewriting(conn, q)\n"
            "    rows.append({'query': name, 'materialised': len(left),\n"
            "                 'rewritten': len(right), 'agree': left == right})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "assert all(r['agree'] for r in rows)"
        ),
        code(
            "answers = ch8.answers_via_rewriting(conn, ch8.QUERIES['cardiac-patients-in-cardiology'])\n"
            "print('cardiac patients in a cardiology ward:')\n"
            "for row in answers:\n"
            "    print('  ', row['p'])"
        ),
        md(
            "## 4. Where the two strategies stop agreeing\n\n"
            "They agree only while the materialisation is **fresh**. Update the source and "
            "one of them starts lying — without changing its behaviour in any visible way."
        ),
        code(
            "stale_graph = ch8.materialise(conn)         # snapshot taken now\n"
            "conn.execute(\"INSERT INTO patient VALUES (106, 'Fatima', 1)\")\n"
            "conn.execute(\"INSERT INTO diagnosis VALUES (106, 'I21')\")\n"
            "conn.commit()\n"
            "print('a new cardiac patient was just admitted to a cardiology ward\\n')\n\n"
            "q = ch8.QUERIES['cardiac-patients-in-cardiology']\n"
            "stale = ch8.answers_via_materialisation(conn, q, graph=stale_graph)\n"
            "live = ch8.answers_via_rewriting(conn, q)\n"
            "print('stale materialisation says:', len(stale), 'patients')\n"
            "print('query rewriting says      :', len(live), 'patients')\n"
            "assert len(live) == len(stale) + 1"
        ),
        code(
            "print('missing from the stale answer:',\n"
            "      [r['p'] for r in live if r not in stale])\n"
            "print('\\nThe stale copy did not error, slow down, or warn. It returned a\\n'\n"
            "      'confident, well-formed, WRONG answer -- and in this scenario the\\n'\n"
            "      'missing row is a patient having a heart attack. Staleness is not a\\n'\n"
            "      'performance characteristic; it is a correctness one, which is why the\\n'\n"
            "      'MDP in the problem set prices it as lost reward rather than added latency.')"
        ),
        code(
            "refreshed = ch8.materialise(conn)\n"
            "print('after re-materialising, the two agree again:',\n"
            "      ch8.answers_via_materialisation(conn, q, graph=refreshed) == live)"
        ),
    ]
    cells += exercise(
        "2.1",
        "Rewrite a query you write yourself",
        "Write a conjunctive query for *wards that contain at least one respiratory patient*, "
        "and confirm both strategies agree.",
        "# YOUR CODE HERE\n",
        "q = ch8.ConjunctiveQuery(\n"
        "    select=['w'],\n"
        "    property_atoms=[('p', ch8.MED + 'inWard', 'w'),\n"
        "                    ('p', ch8.MED + 'hasDisorder', 'd'),\n"
        "                    ('d', ch8.MED + 'category', 'cat')],\n"
        "    filters=[('cat', 'respiratory')])\n"
        "print(ch8.to_sql(q))\n"
        "left = ch8.answers_via_materialisation(conn, q)\n"
        "right = ch8.answers_via_rewriting(conn, q)\n"
        "print('\\nmaterialised:', left)\n"
        "print('rewritten   :', right)\n"
        "assert left == right and len(right) >= 1\n"
        "print('\\nNote the variable ?p appears in two atoms and becomes a join; ?w is\\n'\n"
        "      'projected through the ward IRI template.')",
        hint="Three atoms, joined through the patient variable.",
    )
    cells += exercise(
        "2.2",
        "Break a mapping and let the agreement check catch it",
        "Corrupt one mapping so the two strategies disagree, and show the comparison "
        "detecting it. Explain why this check is worth running in CI.",
        "# YOUR CODE HERE\n",
        "wrong_table = [\n"
        "    ch8.PropertyMap(p.predicate, p.table, p.subject_column, p.object_column,\n"
        "                    p.subject_template,\n"
        "                    None if p.predicate.endswith('hasDisorder') else p.object_template)\n"
        "    for p in ch8.MAPPINGS['properties']]\n"
        "broken = {'classes': ch8.MAPPINGS['classes'], 'properties': wrong_table}\n\n"
        "q = ch8.QUERIES['patients-with-cardiac-disorder']\n"
        "left = ch8.answers_via_materialisation(conn, q, mappings=broken)\n"
        "right = ch8.answers_via_rewriting(conn, q, mappings=broken)\n"
        "print('materialised:', len(left), 'rows')\n"
        "print('rewritten   :', len(right), 'rows')\n"
        "print('agree?', left == right)\n"
        "assert left != right\n"
        "print('\\nThe two paths now disagree, so the bug is detectable without a gold\\n'\n"
        "      'answer, without a domain expert, and without anyone noticing the graph\\n'\n"
        "      'looked odd. That is exactly what makes it a CI check: it needs no oracle\\n'\n"
        "      'beyond the mapping itself.')",
    )
    return save(cells, HERE / "02_query_rewriting.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 8.4",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT), code("conn = ch8.build_database()")]
    cells += exercise(
        "R1",
        "Explain where the ontology goes at run time",
        "Show, for one query, the SPARQL, the SQL, and the fact that both give the same "
        "answer. Then state in one sentence what role the ontology played.",
        "# YOUR CODE HERE\n",
        "q = ch8.QUERIES['patients-in-cardiology']\n"
        "print('SPARQL over the materialised graph:'); print(ch8.to_sparql(q))\n"
        "print('\\nSQL over the original source:'); print(ch8.to_sql(q))\n"
        "left = ch8.answers_via_materialisation(conn, q)\n"
        "right = ch8.answers_via_rewriting(conn, q)\n"
        "print('\\nsame answers:', left == right, f'({len(left)} rows)')\n"
        "assert left == right\n"
        "print('\\nUnder rewriting the ontology is a COMPILE-TIME artefact: it decided\\n'\n"
        "      'which tables to join and which columns to compare, then vanished. No\\n'\n"
        "      'ontology, no triples and no reasoner exist while the query runs.')",
    )
    cells += exercise(
        "R2",
        "Decide the strategy for three workloads",
        "For each workload, choose materialise or rewrite and justify it in terms of "
        "freshness and query cost.",
        "# YOUR CODE HERE\n",
        "workloads = [\n"
        "    ('nightly report over a frozen snapshot, thousands of reads', 'materialise'),\n"
        "    ('live clinical alerting over a transactional database', 'rewrite'),\n"
        "    ('published reference data, never updated, heavily queried', 'materialise'),\n"
        "]\n"
        "for description, expected in workloads:\n"
        "    volatile = any(w in description for w in ('live', 'transactional'))\n"
        "    choice = 'rewrite' if volatile else 'materialise'\n"
        "    print(f'{choice:12s} (expected {expected:12s}) <- {description}')\n"
        "    assert choice == expected\n"
        "print('\\nThe question is never \"which is better\". It is: how often does the\\n'\n"
        "      'source change relative to how often it is queried, and what does a stale\\n'\n"
        "      'answer cost you?')",
    )
    cells += exercise(
        "R3",
        "Quantify the staleness window",
        "Take a snapshot, apply a series of updates, and plot how wrong the stale copy "
        "becomes as updates accumulate.",
        "# YOUR CODE HERE\n",
        "fresh_conn = ch8.build_database()\n"
        "snapshot = ch8.materialise(fresh_conn)\n"
        "q = ch8.QUERIES['patients-with-cardiac-disorder']\n"
        "rows = []\n"
        "for i in range(4):\n"
        "    stale = ch8.answers_via_materialisation(fresh_conn, q, graph=snapshot)\n"
        "    live = ch8.answers_via_rewriting(fresh_conn, q)\n"
        "    missing = len(live) - len(stale)\n"
        "    rows.append({'updates applied': i, 'stale answer': len(stale),\n"
        "                 'true answer': len(live), 'rows missed': missing})\n"
        "    pid = 200 + i\n"
        "    fresh_conn.execute('INSERT INTO patient VALUES (?, ?, 1)', (pid, f'New{i}'))\n"
        "    fresh_conn.execute(\"INSERT INTO diagnosis VALUES (?, 'I21')\", (pid,))\n"
        "    fresh_conn.commit()\n"
        "import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))\n"
        "assert rows[-1]['rows missed'] == 3\n"
        "print('\\nError grows monotonically with time since refresh, and nothing in the\\n'\n"
        "      'system reports it. A refresh schedule is therefore a CORRECTNESS budget,\\n'\n"
        "      'not a maintenance chore.')",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You can map a schema to an ontology, run the result two ways, and detect the "
            "bug that neither path reports on its own. The problem set (Notebook 4) turns the strategy choice "
            "into a decision problem where staleness is priced as lost reward."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
