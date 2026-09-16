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
            "| 4 | `04_agentic_lab` | — | an auditor agent + a **planning MDP with prerequisites** |\n"
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
            "so far. Notebook 4 hands all of it to an agent — and asks what happens when the "
            "reward model for a *plan* is subtly wrong."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
def nb04():
    cells = header(
        CHAPTER,
        "Notebook 4 · Agentic lab — auditing, and planning under prerequisites",
        "Extends §5.1–5.2",
        "An auditor agent that recommends a methodology and finds OntoClean "
        "violations, plus the course's first **planning MDP**: actions with "
        "prerequisites, rewarded by measured competency-question coverage.",
    )
    cells += [
        code(BOOT),
        code(
            "import ch05_agentic as AG\n"
            "from oe_course import evaluation as ev, llm, mdp, optimize as opt\n"
            "import oe_course\n"
            "print(json.dumps(oe_course.describe_environment(), indent=1))"
        ),
        md(
            learning_outcomes(
                [
                    "Build an agent for a task where **a reasoner is useless** — the errors "
                    "are ontological, not logical.",
                    "Plan a project as an MDP with **precedence constraints**, where skipping "
                    "a step makes later steps unavailable.",
                    "Diagnose a **second-order** optimisation failure: a rule that only "
                    "becomes visible after another rule is learned.",
                    "Recognise a reward model that rewards the wrong plan — and fix it.",
                ]
            )
        ),
        md("> **Prerequisite:** the Chapter 1 agentic lab."),
        # --- 1 ---
        md(
            "## 1. Tools\n\n"
            "Note what is *not* here: a reasoner. Every taxonomy in this lab is consistent, "
            "so a tableau would return \"fine\" on all of them. The tools an agent needs here "
            "are meta-property lookups and constraint checks."
        ),
        code(
            "ctx = AG.Ch5Context()\n"
            "tools = {t.name: t for t in AG.build_toolset(ctx)}\n"
            "for name, t in tools.items():\n"
            "    print(f'{name:30s} {list(t.args_schema.model_json_schema().get(\"properties\", {}))}')\n"
            "    print(f'{\"\":30s} {t.description.splitlines()[0]}')"
        ),
        code(
            "print(tools['ontoclean_tags'].invoke({'class_name': 'Student'}))\n"
            "print(tools['ontoclean_tags'].invoke({'class_name': 'Person'}))\n"
            "print()\n"
            "print(tools['check_taxonomy'].invoke({'axioms': 'Person <= Student\\nStudent <= Person'}))\n"
            "print('\\ntrajectory:', ctx.log.names())"
        ),
        md(
            "### The tools also drive a project\n\n"
            "`perform_step` refuses to run a step whose prerequisites are missing — the same "
            "precedence structure the MDP formalises below."
        ),
        code(
            "ctx2 = AG.Ch5Context()\n"
            "t2 = {t.name: t for t in AG.build_toolset(ctx2)}\n"
            "print('try axioms first :', t2['perform_step'].invoke({'step': 'axioms'}))\n"
            "for step in ['requirements', 'competency_questions', 'taxonomy', 'axioms']:\n"
            "    print(f'{step:22s}', t2['perform_step'].invoke({'step': step}))"
        ),
        # --- 2 ---
        md(
            "## 2. The dataset\n\n"
            "Ten cases, each a brief plus a taxonomy. The two halves are independent so the "
            "metric can say *which* half an agent is failing. The split is stratified so both "
            "halves cover all five methodologies and both clean and violating taxonomies."
        ),
        code(
            "all_cases = AG.build_dataset('all')\n"
            "print(pd.DataFrame([{'id': e.id, 'methodology': e.gold_methodology,\n"
            "                     'violations': len(e.gold_violations)} for e in all_cases]\n"
            "                   ).to_string(index=False))\n"
            "train, dev = AG.build_dataset('train'), AG.build_dataset('dev')\n"
            "print('\\ntrain methodologies:', sorted({e.gold_methodology for e in train}))\n"
            "print('dev   methodologies:', sorted({e.gold_methodology for e in dev}))"
        ),
        code(
            "example = dev[0]\n"
            "print('brief   :', example.brief)\n"
            "print('taxonomy:')\n"
            "print('  ' + example.taxonomy.replace('\\n', '\\n  '))\n"
            "print('gold    :', example.gold_methodology, '|', example.gold_violations)"
        ),
        # --- 3 ---
        md(
            "## 3. Baseline and GEPA\n\n"
            "The un-instructed agent does what an inexperienced engineer does: names "
            "METHONTOLOGY because it is the one everyone has heard of, and reports no "
            "violations because the axioms all look fine — which, logically, they are."
        ),
        code(
            "lm = llm.configure_dspy(AG.AUDIT_RULEBOOK, AG.audit_responder)\n"
            "baseline = AG.AuditProgram()\n"
            "pred = baseline(**example.inputs())\n"
            "print('recommended:', pred.methodology, '| violations:', pred.violations)\n"
            "report = AG.audit_scorer(example, pred)\n"
            "print('score      :', report.score)\n"
            "for n in report.notes:\n"
            "    print('   ', n)"
        ),
        code(
            "before = ev.evaluate_dataset(baseline, dev, AG.audit_scorer)\n"
            "print('BEFORE:', before['mean_score'])\n"
            "print('violations:', before['violations'])"
        ),
        code(
            "gepa_metric = ev.make_gepa_metric(AG.audit_scorer, AG.AUDIT_RULEBOOK)\n"
            "reflect = llm.reflection_lm(AG.AUDIT_RULEBOOK, AG.audit_responder)\n"
            "tuned = opt.run_gepa(baseline, train, gepa_metric, valset=train,\n"
            "                     max_metric_calls=90, reflection_lm=reflect)\n"
            "result = opt.compare(AG.AuditProgram(), tuned, dev, AG.audit_scorer)\n"
            "print(result.report())"
        ),
        md(
            "## 4. A rule is learnable only if the data lets the agent break it\n\n"
            "All six rules were discovered here. That is worth examining, because one of them "
            "very nearly could not have been.\n\n"
            "`only-report-real-violations` punishes flagging a **sound** axiom as a violation. "
            "An agent can only commit that error if a sound axiom is present to be "
            "mis-flagged. Two of the training taxonomies deliberately mix a violating axiom "
            "with a sound one for exactly this reason — and if they did not, the rule would "
            "be unlearnable no matter how large the budget."
        ),
        code(
            "found = AG.AUDIT_RULEBOOK.active_in(result.instruction_after)\n"
            "print('rules discovered:', sorted(found))\n"
            "print('rules missed    :', sorted(set(AG.AUDIT_RULEBOOK.ids) - found) or 'none')\n"
            "print()\n"
            "for e in train:\n"
            "    axioms = e.taxonomy.splitlines()\n"
            "    sound = [a for a in axioms if a.strip() not in e.gold_violations]\n"
            "    print(f'  {e.id:22s} {len(axioms)} axioms, {len(sound)} sound '\n"
            "          f'-> over-reporting {\"possible\" if sound and e.gold_violations else \"impossible\"}')"
        ),
        md(
            "> **The general principle**, which is easy to state and easy to forget:\n\n"
            "> *A failure mode your evaluation data makes impossible is a failure mode your "
            "agent will keep in production.*\n\n"
            "Exercise 4.1 removes the sound axioms and shows the rule disappearing."
        ),
        # --- 5 ---
        md(
            "## 5. Planning as an MDP with prerequisites\n\n"
            "Every earlier MDP made all actions available at all times. This one does not:\n\n"
            "| | |\n|---|---|\n"
            "| **S** | which development steps are done, and whether we shipped |\n"
            "| **A** | perform a step **whose prerequisites are complete**, or ship |\n"
            "| **T** | deterministic |\n"
            "| **R** | −effort per step; on ship, the **measured** CQ coverage |\n\n"
            "Precedence is the structural claim every methodology in §5.1 makes. Here it is "
            "enforced by the action set, and the reward comes from the coverage table you "
            "built in Notebook 1 — not from a stipulated number."
        ),
        code(
            "M = AG.MethodologyPlanMDP()\n"
            "print(f'|S| = {len(M.states())}')\n"
            "s0 = M.initial_state()\n"
            "print('actions available at the start:', M.actions(s0))\n"
            "print('\\nNote what is NOT available: you cannot start with axioms or evaluation.')"
        ),
        code(
            "V, pi = mdp.value_iteration(M)\n"
            "print(f'V*(s0) = {V[s0]:.3f}\\n')\n"
            "ep = mdp.run_episode(M, mdp.greedy_policy(pi))\n"
            "for t in ep.transitions:\n"
            "    print(f'  {str(t.state):10s} {t.action:22s} r={t.reward:+.2f}')\n"
            "print(f'\\noptimal plan: {\" -> \".join(ep.actions)}')\n"
            "print(f'return = {ep.discounted_return():.3f} '\n"
            "      f'(coverage 1.0 minus {round(1.0 - ep.discounted_return(), 2)} of effort)')"
        ),
        md(
            "> **Now look at what the optimal plan skips.** It never does `reuse_search`, and "
            "— more uncomfortably — it never does `evaluation`. Both cost effort and neither "
            "unlocks a competency question, so under *this* reward they are pure loss.\n\n"
            "That is not a bug in the solver. It is a **bug in the reward model**, and it is "
            "the same bug that makes real teams skip evaluation under deadline pressure: the "
            "measured objective does not credit it. Exercise 4.2 asks you to fix the reward "
            "rather than the plan."
        ),
        code(
            "skipped = [s for s in M.names if s not in ep.actions]\n"
            "print('steps the optimal plan skips:', skipped)\n"
            "for s in skipped:\n"
            "    spec = ch5.DEVELOPMENT_STEPS[s]\n"
            "    print(f'  {s:16s} cost={spec[\"cost\"]:.2f} unlocks={spec[\"unlocks\"] or \"(nothing)\"}')"
        ),
    ]
    cells += exercise(
        "4.1",
        "Make a rule unlearnable",
        "Strip every **sound** axiom out of the training taxonomies, so over-reporting becomes "
        "impossible on that data. Re-run GEPA and show `only-report-real-violations` is no "
        "longer discovered — even though the dev set still punishes it.",
        "# YOUR CODE HERE\n",
        "import dspy\n"
        "ablated = []\n"
        "for e in train:\n"
        "    keep = [a for a in e.taxonomy.splitlines() if a.strip() in e.gold_violations]\n"
        "    ablated.append(dspy.Example(\n"
        "        brief=e.brief, taxonomy='\\n'.join(keep) or e.taxonomy,\n"
        "        gold_methodology=e.gold_methodology, gold_violations=e.gold_violations,\n"
        "        id=e.id).with_inputs('brief', 'taxonomy'))\n\n"
        "print('ablated training taxonomies (violations only):')\n"
        "for e in ablated:\n"
        "    print(f'  {e.id:22s} {e.taxonomy.splitlines()}')\n\n"
        "tuned_ablated = opt.run_gepa(AG.AuditProgram(), ablated, gepa_metric, valset=ablated,\n"
        "                             max_metric_calls=90, reflection_lm=reflect)\n"
        "res_ablated = opt.compare(AG.AuditProgram(), tuned_ablated, dev, AG.audit_scorer)\n"
        "found_ablated = AG.AUDIT_RULEBOOK.active_in(res_ablated.instruction_after)\n\n"
        "print('\\nfull train    -> dev', result.after['mean_score'],\n"
        "      '| rules', len(AG.AUDIT_RULEBOOK.active_in(result.instruction_after)))\n"
        "print('ablated train -> dev', res_ablated.after['mean_score'],\n"
        "      '| rules', len(found_ablated))\n"
        "print('over-reporting rule learned?', 'only-report-real-violations' in found_ablated)\n"
        "assert 'only-report-real-violations' not in found_ablated\n"
        "print('\\nThe rule vanished. Nothing about the agent, the metric or the budget\\n'\n"
        "      'changed -- only the data. Two axioms removed from a training set silently\\n'\n"
        "      'removed a capability, and the only symptom is a dev score 0.03 lower.\\n'\n"
        "      'In production the symptom would be an auditor that cries wolf.')",
        hint="Keep only the axioms that appear in `gold_violations`.",
    )
    cells += exercise(
        "4.2",
        "Fix the reward so evaluation is worth doing",
        "The optimal plan skips `evaluation`. Change the reward so that skipping it is "
        "penalised — for example, because unevaluated ontologies ship with defects — and show "
        "the optimal plan changing.",
        "# YOUR CODE HERE\n",
        "def coverage_with_evaluation(done):\n"
        "    \"\"\"Shipping without evaluation loses a fifth of the delivered value.\n\n"
        "    The justification is empirical, not moral: unevaluated ontologies ship with\n"
        "    defects that cost more to fix later than the evaluation would have cost.\n"
        "    \"\"\"\n"
        "    base = ch5.coverage_for_steps(done)\n"
        "    return base if 'evaluation' in done else base * 0.8\n\n"
        "M2 = AG.MethodologyPlanMDP(coverage_fn=coverage_with_evaluation)\n"
        "V2, pi2 = mdp.value_iteration(M2)\n"
        "ep2 = mdp.run_episode(M2, mdp.greedy_policy(pi2))\n"
        "print('new optimal plan:', ' -> '.join(ep2.actions))\n"
        "print(f\"V* = {V2[M2.initial_state()]:.3f} (was {V[s0]:.3f})\")\n"
        "assert 'evaluation' in ep2.actions\n"
        "print('\\nEvaluation now pays for itself: 20 per cent of 1.0 coverage is 0.20, and the\\n'\n"
        "      'step costs 0.10. Nothing about the planner changed -- only what we told\\n'\n"
        "      'it to value. If your agents keep skipping something you care about, the\\n'\n"
        "      'first place to look is the reward, not the policy.')",
        hint="Pass a custom `coverage_fn` to `MethodologyPlanMDP`.",
    )
    cells += exercise(
        "4.3",
        "Make reuse worth searching for",
        "`reuse_search` is also skipped. Model the NeOn claim — that reuse *reduces the cost* "
        "of building the taxonomy and axioms — and find the discount at which searching for "
        "reusable resources becomes optimal.",
        "# YOUR CODE HERE\n",
        "import copy\n"
        "rows = []\n"
        "for discount in [0.0, 0.2, 0.4, 0.6]:\n"
        "    steps = copy.deepcopy(ch5.DEVELOPMENT_STEPS)\n"
        "    # Modelling choice: reuse cannot make a step free, only cheaper.\n"
        "    steps['taxonomy'] = dict(steps['taxonomy'],\n"
        "                             requires=('competency_questions',))\n"
        "    class ReuseMDP(AG.MethodologyPlanMDP):\n"
        "        def transition(self, state, action):\n"
        "            if action == 'ship':\n"
        "                return [(1.0, type(state)(state.done, True), self.coverage(state.done))]\n"
        "            cost = self.steps[action]['cost']\n"
        "            if 'reuse_search' in state.done and action in ('taxonomy', 'axioms'):\n"
        "                cost *= (1 - discount)\n"
        "            return [(1.0, type(state)(state.done | {action}, False), -cost)]\n"
        "    Mr = ReuseMDP(steps)\n"
        "    Vr, pir = mdp.value_iteration(Mr)\n"
        "    epr = mdp.run_episode(Mr, mdp.greedy_policy(pir))\n"
        "    rows.append({'discount': discount, 'V*': round(Vr[Mr.initial_state()], 3),\n"
        "                 'searches for reuse': 'reuse_search' in epr.actions})\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "print('\\nreuse_search costs 0.15 and can save at most discount x 0.45 (the cost of\\n'\n"
        "      'taxonomy + axioms), so it pays from roughly a third onwards. That is NeOn\\n'\n"
        "      'stated as an inequality: reuse is worth the search only when the resources\\n'\n"
        "      'you find genuinely displace work you would otherwise do.')",
    )
    cells += [
        md(
            "## Chapter 5 in the course arc\n\n"
            "| | Ch. 1 | Ch. 2 | Ch. 3 | Ch. 4 | Ch. 5 |\n|---|---|---|---|---|---|\n"
            "| MDP | gather evidence | search a proof | budgeted, stochastic | construct | **plan under prerequisites** |\n"
            "| grader | labels + judge | decision procedure | free oracle | labels + profiles | measured CQ coverage |\n"
            "| what a reasoner buys you | nothing | — | everything | everything | **nothing** |\n\n"
            "Chapter 5's contribution: the errors that matter most are often the ones your "
            "tooling cannot see. A reasoner amplifies whatever you assert — including your "
            "mistakes — so a methodology and a meta-property checker are not bureaucracy, "
            "they are the only defence against a whole class of bug.\n\n"
            "Chapter 6 takes the repair that OntoClean could not express (`Statue <= Clay` is "
            "*constitution*, not subsumption) and gives you the vocabulary for it."
        )
    ]
    return save(cells, HERE / "04_agentic_lab.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03, nb04):
        print("wrote", build().name)
