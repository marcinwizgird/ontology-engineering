"""Generate the Chapter 5 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 5 — Methods and Methodologies"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch05_toolkit as ch5
from oe_course.sparql import SparqlStore
from oe_course.data import corpus
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 5",
        "Chapter 5 is the one most easily read as folklore — a parade of named "
        "methodologies and some advice about quality. This chapter makes all of "
        "it executable: methodologies become selection criteria, competency "
        "questions become **SPARQL tests**, and quality becomes a **constraint "
        "checker** that finds errors no reasoner in Chapters 3–4 can see.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | environment check |\n"
            "| 1 | `01_methodologies` | 5.1 | methodology selection + **competency questions as tests** |\n"
            "| 2 | `02_ontology_quality` | 5.2 | an **OntoClean** constraint checker |\n"
            "| 3 | `03_exercises` | 5.3 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude **design-review auditor** (methodology + OntoClean), an audit agent, and a **planning MDP with prerequisites** |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Choose a methodology **from the project brief**, and defend the choice "
                    "with the signals that drove it.",
                    "Turn a competency question into a SPARQL test, and report **coverage** "
                    "as a number.",
                    "Apply the OntoClean meta-properties and find subsumptions that are "
                    "ontologically wrong yet logically consistent.",
                    "Plan a development project as an MDP with **precedence constraints**, "
                    "and notice when the reward model rewards the wrong plan.",
                ]
            )
        ),
        md(
            "## The chapter's central claim\n\n"
            "> **Consistency is not correctness.**\n\n"
            "Chapters 3 and 4 gave you a reasoner. A reasoner tells you whether your axioms "
            "*can* all be true together. It cannot tell you whether they say what you meant. "
            "`Person ⊑ Student` is perfectly consistent and completely wrong, and §5.2 is "
            "about the second kind of error."
        ),
        md("### Sanity check: the African Wildlife Ontology answers its competency questions"),
        code(
            "store = SparqlStore.in_memory(corpus.get('awo').turtle)\n"
            "coverage = ch5.cq_coverage(ch5.AWO_CQS, store)\n"
            "print(f\"coverage {coverage['coverage']} \"\n"
            "      f\"({coverage['answered']}/{coverage['total']} questions answerable)\")\n"
            "assert coverage['coverage'] == 1.0"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Methodologies, and competency questions that actually run",
        "Section 5.1",
        "Two halves. First: choosing a methodology is a decision with inputs, "
        "not a matter of taste. Second: the competency question — ontology "
        "engineering's vaguest artefact — becomes a pass/fail test.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The catalogue\n\n"
            "Each methodology was designed for a *situation*. The `fits when` column is the "
            "part that matters: it lists signals to look for in a project brief."
        ),
        code("print(pd.DataFrame(ch5.methodology_table()).to_string(index=False))"),
        code(
            "for m in ch5.METHODOLOGIES:\n"
            "    print(f'{m.name}')\n"
            "    print(f'   phases: {\" -> \".join(m.phases)}')\n"
            "    print(f'   {m.note}\\n')"
        ),
        md(
            "## 2. Selecting from a brief\n\n"
            "`recommend_methodology` scores each candidate against the brief and **returns "
            "the signals that matched**, so you can argue with it. A recommender that will "
            "not show its evidence is just an opinion with a UI."
        ),
        code(
            "briefs = [\n"
            "    'We must reuse existing ontologies and a legacy thesaurus for a networked project.',\n"
            "    'Greenfield build from scratch by a single team, full lifecycle.',\n"
            "    'A distributed consortium with many contributors, evolving over years.',\n"
            "    'We want an agile, test driven, iterative approach in small increments.',\n"
            "    'Knowledge management pilot; the business case first, application driven.',\n"
            "]\n"
            "for brief in briefs:\n"
            "    r = ch5.recommend_methodology(brief)\n"
            "    print(f\"{r['recommended']:16s} <- matched {r['reason']}\")\n"
            "    print(f\"{'':16s}    {brief}\\n\")"
        ),
        code(
            "r = ch5.recommend_methodology('We need an ontology.')\n"
            "print('vague brief ->', r['recommended'])\n"
            "print('reason      :', r['reason'])\n"
            "print('\\nA brief with no distinguishing signal gets the default. That is the\\n'\n"
            "      'honest answer -- and a hint that the brief needs more work before the\\n'\n"
            "      'methodology question can be answered at all.')"
        ),
        md(
            "## 3. Competency questions as executable tests\n\n"
            "A competency question states what the ontology must be able to answer. Written "
            "as prose it is unfalsifiable. Written as **SPARQL** it is a test: it either "
            "returns rows or it does not."
        ),
        code(
            "for cq in ch5.AWO_CQS:\n"
            "    print(f'[{cq.id}] {cq.question}')\n"
            "    print(f'      needs: {cq.requires}')\n"
            "    print('      ' + ' '.join(cq.sparql.split())[:100] + '\\n')"
        ),
        code(
            "store = SparqlStore.in_memory(corpus.get('awo').turtle)\n"
            "coverage = ch5.cq_coverage(ch5.AWO_CQS, store)\n"
            "print(pd.DataFrame(coverage['results']).to_string(index=False))\n"
            "print(f\"\\ncoverage = {coverage['coverage']}\")"
        ),
        md(
            "## 4. Coverage rises as the ontology is built\n\n"
            "Here is the number that makes methodologies comparable. `ontology_at_stage` "
            "rebuilds the AWO from only the triples a given development step would have "
            "produced, and coverage is then **measured**, not asserted."
        ),
        code(
            "stages = [set(), {'taxonomy'}, {'taxonomy', 'axioms'},\n"
            "          {'taxonomy', 'axioms', 'instances'}]\n"
            "rows = []\n"
            "for done in stages:\n"
            "    graph = ch5.ontology_at_stage(done)\n"
            "    rows.append({'steps completed': ', '.join(sorted(done)) or '(nothing)',\n"
            "                 'triples': len(graph),\n"
            "                 'CQ coverage': ch5.coverage_for_steps(done)})\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        md(
            "> **Read the middle rows.** A taxonomy alone answers a third of the questions. "
            "Adding axioms takes it to five sixths — the axioms earn more coverage than the "
            "taxonomy did, which is the quantitative version of Chapter 1's argument that "
            "vocabulary without axioms is a word list. Instances add the last question and "
            "nothing else.\n\n"
            "This table is what the Chapter 5 MDP is rewarded by."
        ),
    ]
    cells += exercise(
        "1.1",
        "Write a competency question the AWO fails",
        "Add a CQ that the finished AWO **cannot** answer, and show coverage dropping below "
        "1.0. Then say what would have to be added to the ontology to satisfy it.",
        "# YOUR CODE HERE\n",
        "extra = ch5.CompetencyQuestion(\n"
        "    'cq7', 'Which animals are endangered?',\n"
        "    'SELECT ?a WHERE { ?a rdfs:subClassOf awo:EndangeredSpecies }', 'axioms')\n"
        "store = SparqlStore.in_memory(corpus.get('awo').turtle)\n"
        "result = ch5.cq_coverage(list(ch5.AWO_CQS) + [extra], store)\n"
        "print(f\"coverage now {result['coverage']} ({result['answered']}/{result['total']})\")\n"
        "assert result['coverage'] < 1.0\n"
        "print('\\nThe AWO has no conservation-status vocabulary at all, so no query can\\n'\n"
        "      'answer this. Satisfying it means a new class and new axioms -- i.e. the\\n'\n"
        "      'CQ has just generated a requirement. That is what CQs are FOR: they are\\n'\n"
        "      'requirements written in a form that can fail.')",
        hint="Ask about something the ontology has no vocabulary for.",
    )
    cells += exercise(
        "1.2",
        "Which step buys the most coverage per unit of effort?",
        "Using `DEVELOPMENT_STEPS` costs and measured coverage, compute the coverage gained "
        "per unit cost for `taxonomy`, `axioms` and `instances`. Which is the best buy?",
        "# YOUR CODE HERE\n",
        "base = {'taxonomy'}\n"
        "rows = []\n"
        "for step, prior in [('taxonomy', set()),\n"
        "                    ('axioms', {'taxonomy'}),\n"
        "                    ('instances', {'taxonomy'})]:\n"
        "    before = ch5.coverage_for_steps(prior)\n"
        "    after = ch5.coverage_for_steps(prior | {step})\n"
        "    cost = ch5.DEVELOPMENT_STEPS[step]['cost']\n"
        "    rows.append({'step': step, 'coverage before': before, 'coverage after': after,\n"
        "                 'gain': round(after - before, 3), 'cost': cost,\n"
        "                 'gain per cost': round((after - before) / cost, 2)})\n"
        "df = pd.DataFrame(rows)\n"
        "print(df.to_string(index=False))\n"
        "best = df.loc[df['gain per cost'].idxmax(), 'step']\n"
        "print(f'\\nbest buy: {best}')\n"
        "assert best == 'axioms'\n"
        "print('Axioms cost the most and still win on value per unit effort. The cheap\\n'\n"
        "      'step (instances) is the worst buy -- which is the opposite of what a team\\n'\n"
        "      'under deadline pressure usually does.')",
    )
    return save(cells, HERE / "01_methodologies.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Ontology quality: OntoClean",
        "Section 5.2",
        "A reasoner checks consistency. OntoClean checks whether your taxonomy "
        "makes ontological sense. The gap between those two is where most real "
        "modelling errors live — and every example in this notebook is "
        "**consistent**.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. Meta-properties\n\n"
            "OntoClean tags each class with four meta-properties:\n\n"
            "| Meta-property | Values | Reading |\n|---|---|---|\n"
            "| **rigidity** | `+R` / `~R` / `-R` | is the property essential to its instances? |\n"
            "| **identity** | `+I` / `-I` | does it carry a criterion for 'the same one'? |\n"
            "| **unity** | `+U` / `~U` / `-U` | are its instances wholes? |\n"
            "| **dependence** | `+D` / `-D` | does it depend on something external? |\n\n"
            "The key one is **rigidity**. `Person` is rigid: nothing stops being a person "
            "while continuing to exist. `Student` is **anti-rigid**: every student can stop "
            "being one. That difference is invisible to a DL reasoner and decisive here."
        ),
        code(
            "rows = [{'class': name, 'rigidity': t.rigidity, 'identity': t.identity,\n"
            "         'unity': t.unity, 'dependence': t.dependence}\n"
            "        for name, t in ch5.ONTOCLEAN_TAGS.items()]\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        md(
            "## 2. The taxonomy constraints\n\n"
            "The meta-properties constrain what may subsume what:"
        ),
        code(
            "for c in ch5.ONTOCLEAN_CONSTRAINTS:\n"
            "    print(f\"[{c['id']}]\")\n"
            "    print(f\"  {c['statement']}\")\n"
            "    print(f\"  why: {c['why']}\\n\")"
        ),
        md(
            "## 3. Auditing a taxonomy\n\n"
            "Here is a small taxonomy. Read it first and try to spot the errors by eye — "
            "then run the checker."
        ),
        code(
            "for sub, sup in ch5.TAXONOMY:\n"
            "    print(f'  {sub} <= {sup}')"
        ),
        code(
            "violations = ch5.ontoclean_violations()\n"
            "for v in violations:\n"
            "    print(f\"[{v['constraint']}]\")\n"
            "    print(f\"  axiom : {v['axiom']}\")\n"
            "    print(f\"  detail: {v['detail']}\\n\")\n"
            "print(f'{len({v[\"axiom\"] for v in violations})} offending axioms, '\n"
            "      f'{len(violations)} constraint breaches')"
        ),
        md(
            "> Note `Person <= Student` breaches **two** constraints at once (rigidity *and* "
            "dependence). Real modelling errors usually violate several principles — which is "
            "why they feel wrong long before you can say why."
        ),
        md(
            "## 4. The point: a reasoner sees nothing wrong\n\n"
            "Every axiom above is logically consistent. Let's prove it with the Chapter 3 "
            "tableau — the same reasoner that caught `Giraffe ⊓ Carnivore` without complaint "
            "here."
        ),
        code(
            "sys.path.insert(0, str(Path.cwd().parent / 'ch03_description_logics'))\n"
            "import ch03_toolkit as dl\n\n"
            "tbox = dl.TBox()\n"
            "for sub, sup in ch5.TAXONOMY:\n"
            "    tbox.add(dl.Atomic(sub), dl.Atomic(sup))\n\n"
            "for name in ['Person', 'Student', 'Statue', 'Pet']:\n"
            "    ok = dl.satisfiable(dl.Atomic(name), tbox).satisfiable\n"
            "    print(f'  {name:10s} satisfiable: {ok}')\n"
            "print('\\nEvery class is satisfiable and the KB is consistent. The reasoner has\\n'\n"
            "      'no complaint. The errors are real all the same -- they are about what\\n'\n"
            "      'the classes MEAN, and meaning is not a logical property.')"
        ),
        code(
            "print('what the reasoner infers from Person <= Student:')\n"
            "print('  Person <= Person? ', dl.subsumes(dl.Atomic('Person'), dl.Atomic('Person'), tbox))\n"
            "print('  Person <= Entity? ', dl.subsumes(dl.Atomic('Person'), dl.Atomic('Entity'), tbox))\n"
            "print('\\nIt cheerfully propagates the bad axiom. A reasoner amplifies whatever\\n'\n"
            "      'you assert -- including your mistakes. That is the argument for §5.2\\n'\n"
            "      'existing as a separate activity from §3.3.')"
        ),
    ]
    cells += exercise(
        "2.1",
        "Tag a new class and predict the violation",
        "`Patient` is a role: nothing is essentially a patient. Tag it, add `Person <= Patient` "
        "to the taxonomy, and confirm the checker flags it. Then add `Patient <= Person` "
        "instead and confirm it does not.",
        "# YOUR CODE HERE\n",
        "tags = dict(ch5.ONTOCLEAN_TAGS)\n"
        "tags['Patient'] = ch5.MetaProperties('~R', '-I', '-U', '+D')\n\n"
        "wrong = ch5.ontoclean_violations([('Person', 'Patient')], tags)\n"
        "right = ch5.ontoclean_violations([('Patient', 'Person')], tags)\n"
        "print('Person <= Patient ->', [v['constraint'] for v in wrong])\n"
        "print('Patient <= Person ->', [v['constraint'] for v in right] or 'no violation')\n"
        "assert wrong and not right\n"
        "print('\\nThe direction is everything. A role may be subsumed BY a rigid class;\\n'\n"
        "      'it may never subsume one. Every taxonomy that puts a role above a natural\\n'\n"
        "      'kind has this bug, and it is one of the most common real-world errors.')",
        hint="Roles are anti-rigid (`~R`) and externally dependent (`+D`).",
    )
    cells += exercise(
        "2.2",
        "Repair the taxonomy",
        "Fix all three offending axioms in `TAXONOMY` without deleting any class, and confirm "
        "the checker reports nothing. State the modelling claim each repair makes.",
        "# YOUR CODE HERE\n",
        "repaired = [\n"
        "    ('Person', 'Entity'),\n"
        "    ('Animal', 'Entity'),\n"
        "    ('PhysicalObject', 'Entity'),\n"
        "    ('Student', 'Person'),        # was Person <= Student: direction reversed\n"
        "    ('Employee', 'Person'),\n"
        "    ('Statue', 'PhysicalObject'), # was Statue <= Clay: constitution, not subsumption\n"
        "    ('Pet', 'Animal'),            # was Person <= Pet: a pet is a role on an animal\n"
        "]\n"
        "print('violations after repair:', ch5.ontoclean_violations(repaired) or 'none')\n"
        "assert ch5.ontoclean_violations(repaired) == []\n"
        "print('\\nEach repair is a claim:\\n'\n"
        "      '  1. students are a kind of person, not the reverse;\\n'\n"
        "      '  2. a statue is CONSTITUTED OF clay, not a KIND OF clay -- constitution\\n'\n"
        "      '     is a different relation, which is exactly Chapter 6 material;\\n'\n"
        "      '  3. being a pet is a role an animal plays.\\n'\n"
        "      'Note that repair 2 could not be expressed as subsumption at all. OntoClean\\n'\n"
        "      'found the error; fixing it needed a richer relation vocabulary.')",
    )
    return save(cells, HERE / "02_ontology_quality.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 5.3",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Match methodologies to projects",
        "For each of four project descriptions, recommend a methodology and justify it with "
        "the matched signals.",
        "# YOUR CODE HERE\n",
        "projects = {\n"
        "    'A hospital wants to integrate two legacy databases and an existing thesaurus.':\n"
        "        'neon',\n"
        "    'A university lab is building a new ontology from scratch, single team, full lifecycle.':\n"
        "        'methontology',\n"
        "    'Twenty labs across Europe will jointly edit an evolving, decentralised ontology.':\n"
        "        'diligent',\n"
        "    'A startup wants small increments with a test driven, agile, iterative process.':\n"
        "        'samod',\n"
        "}\n"
        "for brief, expected in projects.items():\n"
        "    r = ch5.recommend_methodology(brief)\n"
        "    print(f\"{r['recommended']:16s} (expected {expected:16s}) <- {r['reason']}\")\n"
        "    assert r['recommended'] == expected\n"
        "print('\\nNote the recommender reads SIGNALS, not domains. \"Hospital\" is\\n'\n"
        "      'irrelevant; \"existing thesaurus\" is decisive.')",
    )
    cells += exercise(
        "R2",
        "Turn three requirements into competency questions",
        "Write SPARQL for three requirements over the AWO, and report the coverage.",
        "# YOUR CODE HERE\n",
        "mine = [\n"
        "    ch5.CompetencyQuestion('m1', 'Which classes are carnivores?',\n"
        "                           'SELECT ?c WHERE { ?c rdfs:subClassOf awo:Carnivore }'),\n"
        "    ch5.CompetencyQuestion('m2', 'Which object properties exist?',\n"
        "                           'SELECT ?p WHERE { ?p a owl:ObjectProperty }'),\n"
        "    ch5.CompetencyQuestion('m3', 'Which properties are transitive?',\n"
        "                           'SELECT ?p WHERE { ?p a owl:TransitiveProperty }'),\n"
        "]\n"
        "store = SparqlStore.in_memory(corpus.get('awo').turtle)\n"
        "result = ch5.cq_coverage(mine, store)\n"
        "print(pd.DataFrame(result['results']).to_string(index=False))\n"
        "print(f\"coverage {result['coverage']}\")\n"
        "assert result['coverage'] == 1.0",
    )
    cells += exercise(
        "R3",
        "Find the OntoClean error in a realistic taxonomy",
        "Audit this plausible-looking taxonomy and explain the error in terms a domain "
        "expert would accept.",
        "taxonomy = [('Customer', 'Person'), ('Person', 'Customer'), ('Person', 'Agent')]\n"
        "# YOUR CODE HERE\n",
        "tags = dict(ch5.ONTOCLEAN_TAGS)\n"
        "tags['Customer'] = ch5.MetaProperties('~R', '-I', '-U', '+D')\n"
        "tags['Agent'] = ch5.MetaProperties('+R', '+I', '+U', '-D')\n\n"
        "taxonomy = [('Customer', 'Person'), ('Person', 'Customer'), ('Person', 'Agent')]\n"
        "violations = ch5.ontoclean_violations(taxonomy, tags)\n"
        "for v in violations:\n"
        "    print(f\"[{v['constraint']}] {v['axiom']}: {v['detail']}\")\n"
        "assert any(v['axiom'] == 'Person <= Customer' for v in violations)\n"
        "print('\\nFor a domain expert: \"every person is a customer\" would mean a person\\n'\n"
        "      'stops being a person the moment they stop buying from us. The taxonomy\\n'\n"
        "      'says something about our database that is not true about the world -- the\\n'\n"
        "      'classic mistake of modelling the application instead of the domain.')",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You can select a methodology from evidence, express requirements as tests that "
            "can fail, and detect a class of error that survives every reasoner in the course "
            "so far. The problem set (`04_assignment`) hands all of it to Claude — and asks "
            "what happens when the reward model for a *plan* is subtly wrong."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
