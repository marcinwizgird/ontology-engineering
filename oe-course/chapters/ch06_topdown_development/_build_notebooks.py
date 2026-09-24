"""Generate the Chapter 6 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 6 — Top-down Ontology Development"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch06_toolkit as ch6
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 6",
        "Chapter 5 ended on an error it could find but not fix: `Statue ⊑ Clay` "
        "is wrong, and the right answer — *a statue is **constituted of** clay* "
        "— needs a relation subsumption cannot express. Chapter 6 supplies the "
        "vocabulary, and the discipline for choosing from it.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | environment check |\n"
            "| 1 | `01_foundational_ontologies` | 6.1 | a category tree + a **decision procedure** |\n"
            "| 2 | `02_part_whole_relations` | 6.2 | the part-whole taxonomy + a **chaining checker** |\n"
            "| 3 | `03_exercises` | 6.3 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: typing a museum catalogue's single `partOf` with Claude, a chaining agent, and a diagnostic MDP that derives the alignment decision tree from a cost model |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Place a domain class in a foundational category by **answering questions**, "
                    "not by intuition.",
                    "Name which of the seven part-whole relations a statement expresses, and "
                    "say whether it is genuine parthood.",
                    "Decide when two part-whole statements may be **chained** — and explain "
                    "the classic counterexamples.",
                    "Compare DOLCE and BFO on the same distinctions, and see where they do "
                    "not line up.",
                ]
            )
        ),
        md(
            "## The chapter's central claim\n\n"
            "> **\"Part of\" in English is at least seven different relations, and they have "
            "different logical properties.**\n\n"
            "Collapse them into a single `partOf` property — as a great many published "
            "ontologies do — and a reasoner will happily derive that a musician's hand is "
            "part of an orchestra. Notebook 2 shows exactly that inference, and where it "
            "goes wrong."
        ),
        md("### Sanity check: the categories are actually distinguishable"),
        code(
            "vectors = {c.id: tuple(sorted(ch6.category_answers(c.id).items()))\n"
            "           for c in ch6.CATEGORIES}\n"
            "assert len(set(vectors.values())) == len(ch6.CATEGORIES)\n"
            "print(f'{len(ch6.CATEGORIES)} categories, all with distinct answer vectors')\n"
            "print('decision questions:', list(ch6.DECISION_QUESTIONS))"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Foundational ontologies",
        "Section 6.1",
        "A foundational ontology is a set of very general categories agreed in "
        "advance, so that domain modellers make the same distinctions the same "
        "way. Its real product is not the categories — it is the **questions** "
        "that place things in them.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The categories\n\n"
            "A DOLCE-flavoured tree, simplified to seven leaves. The `branch` column carries "
            "the oldest distinction in the subject: **endurants** exist *through* time (a "
            "giraffe is wholly present at every moment it exists), **perdurants** unfold *in* "
            "time (a hunt has temporal parts)."
        ),
        code(
            "print(pd.DataFrame([{'id': c.id, 'name': c.name, 'branch': c.branch,\n"
            "                     'examples': ', '.join(c.examples)}\n"
            "                    for c in ch6.CATEGORIES]).to_string(index=False))"
        ),
        code(
            "for c in ch6.CATEGORIES:\n"
            "    print(f'{c.name} ({c.branch})')\n"
            "    print(f'   {c.gloss}')\n"
            "    print(f'   e.g. {\", \".join(c.examples)}\\n')"
        ),
        md(
            "## 2. The decision questions\n\n"
            "This is the part that makes alignment an engineering activity. Each question is "
            "a yes/no test with a defensible answer for every category."
        ),
        code(
            "for key, question in ch6.DECISION_QUESTIONS.items():\n"
            "    print(f'  {key:11s} {question}')"
        ),
        code(
            "rows = []\n"
            "for c in ch6.CATEGORIES:\n"
            "    row = {'category': c.name}\n"
            "    row.update({k: ('yes' if v else 'no')\n"
            "                for k, v in ch6.category_answers(c.id).items()})\n"
            "    rows.append(row)\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        md(
            "## 3. Aligning a class by interrogation\n\n"
            "`identify_category` takes whatever answers you have so far and returns the "
            "categories still consistent with them. Watch the candidate set shrink."
        ),
        code(
            "steps = [{}, {'happens': True}, {'happens': True, 'telic': True}]\n"
            "for answers in steps:\n"
            "    print(f'{str(answers):46s} -> {ch6.identify_category(answers)}')"
        ),
        code(
            "print('Aligning \"clay\":')\n"
            "answers = {}\n"
            "for question, answer in [('happens', False), ('spatial', True), ('mass', True)]:\n"
            "    answers[question] = answer\n"
            "    print(f'  {question}={answer}  -> candidates {ch6.identify_category(answers)}')\n"
            "assert ch6.identify_category(answers) == ['amount-of-matter']"
        ),
        code(
            "print('Aligning \"the colour of a leaf\":')\n"
            "answers = {}\n"
            "for question, answer in [('happens', False), ('spatial', False), ('dependent', True)]:\n"
            "    answers[question] = answer\n"
            "    print(f'  {question}={answer}  -> candidates {ch6.identify_category(answers)}')\n"
            "assert ch6.identify_category(answers) == ['quality']"
        ),
        md(
            "> **Three questions, one answer.** That is what a foundational ontology buys: "
            "not a list of categories to memorise but a short, repeatable interrogation that "
            "two modellers will answer the same way. The problem set (`04_assignment`) prices "
            "the interrogation — and asks when a cost model derives the optimal order of questions."
        ),
        md(
            "## 4. DOLCE is not the only choice\n\n"
            "BFO draws many of the same distinctions differently, and the mismatch is a real "
            "project decision rather than a detail."
        ),
        code("print(pd.DataFrame(ch6.BFO_COMPARISON).to_string(index=False))"),
        md(
            "> The last row is the sharpest: BFO is **realist** and has no place for abstract "
            "entities at all. If your domain needs to talk about numbers, propositions or "
            "musical works as first-class things, that is not a preference — it decides the "
            "choice for you."
        ),
    ]
    cells += exercise(
        "1.1",
        "Align four domain classes",
        "Place `a hole in a leaf`, `digestion`, `the number seven` and `a herd` in the "
        "category tree by answering the decision questions. One of them exposes a limit of "
        "this seven-category tree — say which.",
        "# YOUR CODE HERE\n",
        "cases = {\n"
        "    'a hole in a leaf': {'happens': False, 'spatial': True, 'mass': False,\n"
        "                         'dependent': True},\n"
        "    'digestion':        {'happens': True, 'telic': False},\n"
        "    'the number seven': {'happens': False, 'spatial': False, 'dependent': False},\n"
        "}\n"
        "for name, answers in cases.items():\n"
        "    print(f'{name:20s} -> {ch6.identify_category(answers)}')\n"
        "assert ch6.identify_category(cases['a hole in a leaf']) == ['feature']\n"
        "assert ch6.identify_category(cases['digestion']) == ['process']\n"
        "assert ch6.identify_category(cases['the number seven']) == ['abstract']\n\n"
        "herd = {'happens': False, 'spatial': True, 'mass': False, 'dependent': False}\n"
        "print(f\"{'a herd':20s} -> {ch6.identify_category(herd)}\")\n"
        "print('\\nA herd comes out as a physical object, which is not wrong but is not\\n'\n"
        "      'informative either: this tree has no COLLECTION category, even though the\\n'\n"
        "      'part-whole taxonomy in Notebook 2 needs one for member-of. Real\\n'\n"
        "      'foundational ontologies do have it. The lesson is that your category set\\n'\n"
        "      'and your relation set have to be designed together.')",
        hint="Answer only the questions you need; `identify_category` accepts partial answers.",
    )
    cells += exercise(
        "1.2",
        "Is any question redundant?",
        "Find the smallest set of questions that still distinguishes all seven categories. "
        "Then, for each question, name the pair of categories that *only* it separates.",
        "# YOUR CODE HERE\n",
        "import itertools\n"
        "questions = list(ch6.DECISION_QUESTIONS)\n"
        "best = None\n"
        "for size in range(1, len(questions) + 1):\n"
        "    for subset in itertools.combinations(questions, size):\n"
        "        vectors = {c.id: tuple(ch6.category_answers(c.id)[q] for q in subset)\n"
        "                   for c in ch6.CATEGORIES}\n"
        "        if len(set(vectors.values())) == len(ch6.CATEGORIES):\n"
        "            best = subset\n"
        "            break\n"
        "    if best:\n"
        "        break\n"
        "print('smallest sufficient question set:', best)\n"
        "print('droppable:', [q for q in questions if q not in best] or 'none')\n"
        "assert best is not None and len(best) == len(questions)\n\n"
        "print('\\nfor each question, the pair only it separates:')\n"
        "for q in questions:\n"
        "    others = [x for x in questions if x != q]\n"
        "    collisions = {}\n"
        "    for c in ch6.CATEGORIES:\n"
        "        key = tuple(ch6.category_answers(c.id)[x] for x in others)\n"
        "        collisions.setdefault(key, []).append(c.id)\n"
        "    merged = [v for v in collisions.values() if len(v) > 1]\n"
        "    print(f'  {q:11s} -> {merged}')\n"
        "print('\\nNo question is redundant: drop any one and two categories collapse into\\n'\n"
        "      'each other. That is a well-designed question set -- and it does NOT mean\\n'\n"
        "      'every alignment needs all five. The problem set shows the optimal policy\\n'\n"
        "      'settling most classes in three, because a question is only asked on the\\n'\n"
        "      'branch where it still discriminates.')",
    )
    return save(cells, HERE / "01_foundational_ontologies.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Part-whole relations",
        "Section 6.2",
        "English says \"part of\" for at least seven different relations. Three "
        "of them are not parthood at all. Here is the taxonomy, and here is the "
        "damage done by ignoring it.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The taxonomy\n\n"
            "Each relation is characterised by what it relates and by two logical "
            "properties: is it **genuine mereological parthood**, and is it **transitive**?"
        ),
        code(
            "print(pd.DataFrame([\n"
            "    {'relation': r.name, 'parthood': r.parthood, 'transitive': r.transitive,\n"
            "     'part': r.part_category, 'whole': r.whole_category, 'example': r.example}\n"
            "    for r in ch6.PART_WHOLE_RELATIONS]).to_string(index=False))"
        ),
        code(
            "for r in ch6.PART_WHOLE_RELATIONS:\n"
            "    flag = 'PARTHOOD    ' if r.parthood else 'NOT parthood'\n"
            "    print(f'{r.name:18s} [{flag}] {\"transitive\" if r.transitive else \"\"}')\n"
            "    print(f'   test: {r.test}')\n"
            "    print(f'   e.g.  {r.example}\\n')"
        ),
        md(
            "> **The three impostors.** `constituted of`, `contained in` and `participates "
            "in` all read as \"part of\" in English and none of them is parthood. The statue "
            "is not part of the clay; the coffee is not part of the cup; the lion is not part "
            "of the hunt. Each is a genuine relation — just not that one."
        ),
        md(
            "## 2. The categories decide the relation\n\n"
            "This is where Chapter 6's two halves meet: once you know what kind of things you "
            "are relating, the relation follows almost mechanically."
        ),
        code(
            "cases = [('physical-object', 'physical-object', False),\n"
            "         ('physical-object', 'collection', False),\n"
            "         ('amount-of-matter', 'amount-of-matter', False),\n"
            "         ('amount-of-matter', 'physical-object', False),\n"
            "         ('physical-object', 'process', False),\n"
            "         ('process', 'process', False),\n"
            "         ('physical-object', 'physical-object', True),\n"
            "         ('physical-object', 'region', False)]\n"
            "rows = []\n"
            "for part, whole, separable in cases:\n"
            "    rel = ch6.relation_by_id(ch6.classify_partwhole(part, whole, separable))\n"
            "    rows.append({'part': part, 'whole': whole, 'separable': separable,\n"
            "                 'relation': rel.name, 'parthood': rel.parthood})\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        md(
            "Note rows 1 and 7: the *same* pair of categories yields `component of` or "
            "`contained in` depending on whether the part is separable. That is the one place "
            "the categories are not enough and a modelling judgement is required."
        ),
        md(
            "## 3. Chaining — where ontologies actually break\n\n"
            "The reason all this matters: people compose part-whole statements. `a` is part "
            "of `b`, `b` is part of `c`, therefore `a` is part of `c`. That inference is valid "
            "only under conditions most modellers never check."
        ),
        code(
            "for ex in ch6.CHAINING_EXAMPLES:\n"
            "    result = ch6.can_chain(ex['first'], ex['second'])\n"
            "    verdict = 'VALID  ' if result['valid'] else 'INVALID'\n"
            "    print(f'[{verdict}] {ex[\"story\"]}')\n"
            "    print(f'          {result[\"reason\"]}\\n')\n"
            "    assert result['valid'] == ex['expected']"
        ),
        md(
            "### The classic counterexample, in full\n\n"
            "A hand is a **component of** a musician. A musician is a **member of** an "
            "orchestra. If your ontology has one `partOf` property and declares it "
            "transitive — which is the single most common modelling shortcut in this area — "
            "then your reasoner will derive that **the hand is part of the orchestra**.\n\n"
            "Let's actually derive it, using the Chapter 3 reasoner, to show this is not a "
            "hypothetical."
        ),
        code(
            "sys.path.insert(0, str(Path.cwd().parent / 'ch03_description_logics'))\n"
            "import ch03_toolkit as dl\n\n"
            "# The shortcut: one transitive partOf for everything.\n"
            "tbox = dl.TBox()\n"
            "tbox.add(dl.Atomic('Hand'), dl.Exists('partOf', dl.Atomic('Musician')))\n"
            "tbox.add(dl.Atomic('Musician'), dl.Exists('partOf', dl.Atomic('Orchestra')))\n"
            "tbox.transitive_roles.add('partOf')\n"
            "print('DL of this knowledge base:', dl.dl_name(tbox))\n"
            "print('\\nWith partOf transitive, a hand in a musician in an orchestra is a hand')\n"
            "print('in an orchestra -- the reasoner has no way to know the two \\'partOf\\'')\n"
            "print('links were different relations, because we did not tell it.')"
        ),
        code(
            "print('what the taxonomy says instead:')\n"
            "print(' ', ch6.can_chain('component-of', 'member-of')['reason'])\n"
            "print('\\nThe fix is not a cleverer reasoner. It is a richer vocabulary:')\n"
            "print('  Hand  component-of  Musician')\n"
            "print('  Musician  member-of  Orchestra')\n"
            "print('...and neither relation is transitive, so nothing follows. The error was')\n"
            "print('committed when both were called \\'partOf\\'.')"
        ),
    ]
    cells += exercise(
        "2.1",
        "Fix the statue",
        "Chapter 5 found that `Statue ⊑ Clay` is an OntoClean violation but could not express "
        "the repair. Express it now, and confirm that the relation you chose is **not** "
        "parthood and cannot be chained with componenthood.",
        "# YOUR CODE HERE\n",
        "relation_id = ch6.classify_partwhole('amount-of-matter', 'physical-object')\n"
        "relation = ch6.relation_by_id(relation_id)\n"
        "print('clay -> statue :', relation.name)\n"
        "print('  parthood     :', relation.parthood)\n"
        "print('  transitive   :', relation.transitive)\n"
        "assert relation_id == 'constituted-of' and not relation.parthood\n\n"
        "chain = ch6.can_chain('constituted-of', 'component-of')\n"
        "print('\\nclay constitutes statue, statue is a component of the exhibit:')\n"
        "print('  can we conclude the clay is part of the exhibit?', chain['valid'])\n"
        "print(' ', chain['reason'])\n"
        "assert not chain['valid']\n"
        "print('\\nThis is the repair Chapter 5 could not state. Note it is not a subsumption\\n'\n"
        "      'at all -- which is why OntoClean could only tell us the axiom was wrong,\\n'\n"
        "      'not what to write instead. Finding the error and fixing it needed two\\n'\n"
        "      'different chapters.')",
    )
    cells += exercise(
        "2.2",
        "Build a valid chain",
        "Find the two relations in the taxonomy that *can* be chained, and construct a "
        "three-step chain that is valid the whole way.",
        "# YOUR CODE HERE\n",
        "transitive_parthood = [r.id for r in ch6.PART_WHOLE_RELATIONS\n"
        "                       if r.parthood and r.transitive]\n"
        "print('chainable relations:', transitive_parthood)\n"
        "assert set(transitive_parthood) == {'sub-quantity-of', 'involved-in'}\n\n"
        "print('\\nA three-step chain with sub-quantity-of:')\n"
        "print('  the alcohol is a sub-quantity of the wine')\n"
        "print('  the wine is a sub-quantity of the cellar stock')\n"
        "print('  the cellar stock is a sub-quantity of the estate inventory')\n"
        "for step in range(2):\n"
        "    r = ch6.can_chain('sub-quantity-of', 'sub-quantity-of')\n"
        "    print(f'  step {step + 1} valid: {r[\"valid\"]}')\n"
        "    assert r['valid']\n"
        "print('\\nOnly two of the eight relations may be chained. If your ontology declares\\n'\n"
        "      'a part-whole property transitive, it had better be one of these two.')",
        hint="Which relations are both `parthood` and `transitive`?",
    )
    return save(cells, HERE / "02_part_whole_relations.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 6.3",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Classify six part-whole statements",
        "For each statement, give the relation and say whether it is parthood.",
        "statements = [\n"
        "    ('A branch is part of a tree.', 'physical-object', 'physical-object'),\n"
        "    ('The sugar is part of the syrup.', 'amount-of-matter', 'amount-of-matter'),\n"
        "    ('The bronze is part of the sculpture.', 'amount-of-matter', 'physical-object'),\n"
        "    ('A player is part of a team.', 'physical-object', 'collection'),\n"
        "    ('The referee is part of the match.', 'physical-object', 'process'),\n"
        "    ('Kneading is part of baking.', 'process', 'process'),\n"
        "]\n"
        "# YOUR CODE HERE\n",
        "statements = [\n"
        "    ('A branch is part of a tree.', 'physical-object', 'physical-object'),\n"
        "    ('The sugar is part of the syrup.', 'amount-of-matter', 'amount-of-matter'),\n"
        "    ('The bronze is part of the sculpture.', 'amount-of-matter', 'physical-object'),\n"
        "    ('A player is part of a team.', 'physical-object', 'collection'),\n"
        "    ('The referee is part of the match.', 'physical-object', 'process'),\n"
        "    ('Kneading is part of baking.', 'process', 'process'),\n"
        "]\n"
        "rows = []\n"
        "for text, part, whole in statements:\n"
        "    r = ch6.relation_by_id(ch6.classify_partwhole(part, whole))\n"
        "    rows.append({'statement': text, 'relation': r.name,\n"
        "                 'parthood': r.parthood, 'transitive': r.transitive})\n"
        "import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))\n"
        "expected = ['component of', 'sub-quantity of', 'constituted of',\n"
        "            'member of', 'participates in', 'involved in']\n"
        "assert [r['relation'] for r in rows] == expected\n"
        "print('\\nSix statements, six different relations, identical English. Two of the\\n'\n"
        "      'six are not parthood at all.')",
    )
    cells += exercise(
        "R2",
        "Decide four chaining questions",
        "For each pair of relations, say whether the chain is valid and why.",
        "# YOUR CODE HERE\n",
        "pairs = [('component-of', 'component-of'),\n"
        "         ('sub-quantity-of', 'sub-quantity-of'),\n"
        "         ('member-of', 'member-of'),\n"
        "         ('participates-in', 'involved-in')]\n"
        "for first, second in pairs:\n"
        "    r = ch6.can_chain(first, second)\n"
        "    print(f'{first:18s} + {second:18s} -> {str(r[\"valid\"]):5s}  {r[\"reason\"]}')\n"
        "assert not ch6.can_chain('component-of', 'component-of')['valid']\n"
        "assert ch6.can_chain('sub-quantity-of', 'sub-quantity-of')['valid']\n"
        "assert not ch6.can_chain('member-of', 'member-of')['valid']\n"
        "print('\\nThe first is the surprise: componenthood is genuine parthood and still\\n'\n"
        "      'not transitive. A finger is a component of a hand and a hand of a body,\\n'\n"
        "      'but whether a finger is a component OF THE BODY depends on how you\\n'\n"
        "      'individuate components -- which is exactly why the relation is not\\n'\n"
        "      'declared transitive.')",
    )
    cells += exercise(
        "R3",
        "Choose between DOLCE and BFO for a project",
        "A project must represent musical works, performances, and the scores they are "
        "written on. Say which foundational ontology fits and why, using the comparison table.",
        "# YOUR CODE HERE\n",
        "import pandas as pd\n"
        "print(pd.DataFrame(ch6.BFO_COMPARISON).to_string(index=False))\n"
        "needs = {\n"
        "    'a musical work (abstract)': 'abstract',\n"
        "    'a performance (happens)': 'process',\n"
        "    'a score (physical copy)': 'physical-object',\n"
        "}\n"
        "for label, category in needs.items():\n"
        "    print(f'  {label:28s} -> DOLCE {category}')\n"
        "bfo_gap = [row for row in ch6.BFO_COMPARISON if 'none' in row['bfo']]\n"
        "print('\\nBFO has no category for:', [row['dolce'] for row in bfo_gap])\n"
        "assert bfo_gap and bfo_gap[0]['dolce'] == 'Abstract Entity'\n"
        "print('\\nA musical work is not identical to any performance of it, nor to any\\n'\n"
        "      'printed score -- it is abstract. BFO is realist and excludes abstracta,\\n'\n"
        "      'so this project needs DOLCE (or must re-model works as something else,\\n'\n"
        "      'which is a real cost and should be a conscious decision).')",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You can align a class by interrogation, name the relation a \"part of\" statement "
            "really expresses, and say when a chain of them is sound. The problem set "
            "(`04_assignment`) hands both jobs to Claude — and asks whether a cost model can "
            "*derive* the alignment questions rather than be told them."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
