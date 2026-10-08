"""Generate the Chapter 3 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 3 — Description Logics"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch03_toolkit as dl
import pandas as pd
A = dl.Atomic
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 3",
        "Chapter 2 ended at a wall: first-order logic is undecidable, so no "
        "terminating procedure can be complete for it. Description logics are "
        "the engineering response — **fragments of FOL chosen so that reasoning "
        "terminates**. In this chapter you build the reasoner that makes that "
        "claim true.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | a working DL environment |\n"
            "| 1 | `01_dl_basics_and_tableau` | 3.1 | **an ALC tableau reasoner**, with blocking |\n"
            "| 2 | `02_important_dls` | 3.2 | a DL namer, and the measured cost of expressivity |\n"
            "| 3 | `03_reasoning_services` | 3.3 | satisfiability, subsumption, classification |\n"
            "| 4 | `04_exercises` | 3.4 | autograded answers |\n"
            "| 5 | `05_assignment` / `05_solutions` | — | problem set: a Claude reviewer for ontology change requests, self-labelled by the tableau, and a budgeted reasoner |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Read and write DL concept expressions, and say what each constructor "
                    "costs you.",
                    "Run — and explain — a **tableau**: why `∃r.A ⊓ ∀r.¬A` is unsatisfiable, "
                    "step by step.",
                    "Explain why **blocking** is what makes cyclic axioms terminate.",
                    "Name the DL a knowledge base actually needs, and predict the reasoning "
                    "complexity you just signed up for.",
                    "Derive every reasoning service from concept satisfiability.",
                    "Build an agent that decides *when a sound reasoner is worth its cost*.",
                ]
            )
        ),
        md(
            "## The engine\n\n"
            "`ch03_toolkit` is a self-contained DL implementation: concept AST, negation "
            "normal form, expressivity analysis, and a tableau reasoner for **ALC** with TBox "
            "internalisation and subset blocking. No external reasoner, no Java.\n\n"
            "> **Scope, stated up front.** The tableau decides ALC. Number restrictions, "
            "inverses and transitive roles are *analysed* by the DL namer but **not reasoned "
            "over** — implementing SHIQ is a research-grade exercise, not a notebook. Every "
            "place this matters, the notebooks say so."
        ),
        md("### Sanity check: the smallest interesting unsatisfiability"),
        code(
            "c = dl.And(dl.Exists('r', A('A')), dl.ForAll('r', dl.Not(A('A'))))\n"
            "print('concept   :', dl.to_string(c))\n"
            "result = dl.satisfiable(c)\n"
            "print('verdict   :', result.summary())\n"
            "assert not result.satisfiable\n"
            "print('\\nIt demands an r-successor that is an A, while insisting every\\n'\n"
            "      'r-successor is not an A. No model can satisfy both.')"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Concepts, models, and a tableau you can read",
        "Section 3.1",
        "A description logic has three moving parts: concepts, roles, and an "
        "interpretation. The reasoning algorithm — the tableau — is the part "
        "that turns those definitions into answers, and it is short enough to "
        "read in full.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The concept language\n\n"
            "Concepts are built from atomic concepts and roles:\n\n"
            "| DL notation | Toolkit | Meaning |\n|---|---|---|\n"
            "| `A` | `A('A')` | atomic concept |\n"
            "| `C ⊓ D` | `dl.And(C, D)` | conjunction |\n"
            "| `C ⊔ D` | `dl.Or(C, D)` | disjunction |\n"
            "| `¬C` | `dl.Not(C)` | complement |\n"
            "| `∃r.C` | `dl.Exists('r', C)` | existential restriction |\n"
            "| `∀r.C` | `dl.ForAll('r', C)` | universal restriction |\n"
            "| `⊤` / `⊥` | `dl.Top` / `dl.Bottom` | top / bottom |\n\n"
            "**ALC** is exactly this set. Everything in §3.2 is ALC plus something."
        ),
        code(
            "vegetarian = dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat'))))\n"
            "print('Vegetarian ==', dl.to_string(vegetarian))\n\n"
            "giraffe = dl.And(A('Herbivore'), dl.Exists('eats', A('Leaf')))\n"
            "print('Giraffe    <=', dl.to_string(giraffe))"
        ),
        md(
            "### Negation normal form\n\n"
            "The tableau needs negation pushed down to atoms. The rewriting rules are the De "
            "Morgan laws plus the quantifier duals `¬∃r.C ≡ ∀r.¬C` and `¬∀r.C ≡ ∃r.¬C` — the "
            "same duality you met in Chapter 2."
        ),
        code(
            "for c in [dl.Not(dl.And(A('A'), A('B'))),\n"
            "          dl.Not(dl.Exists('r', A('A'))),\n"
            "          dl.Not(dl.ForAll('r', dl.Not(A('A'))))]:\n"
            "    print(f'{dl.to_string(c):34s} -> {dl.to_string(dl.nnf(c))}')"
        ),
        md(
            "## 2. The tableau: build a model, or fail trying\n\n"
            "To decide whether `C` is satisfiable, a tableau **tries to build a model of it**. "
            "It keeps a set of concepts (a *label*) for each individual and applies rules:\n\n"
            "| Rule | Action |\n|---|---|\n"
            "| ⊓ | `C ⊓ D` in the label → add both `C` and `D` |\n"
            "| ⊔ | `C ⊔ D` in the label → **branch**: try `C`, else try `D` |\n"
            "| ∃ | `∃r.C` → create a fresh `r`-successor labelled `{C}` … |\n"
            "| ∀ | … plus every `D` where `∀r.D` is in the current label |\n"
            "| clash | `A` and `¬A` both present → this branch fails |\n\n"
            "`C` is satisfiable iff **some** branch saturates without a clash. Watch it work:"
        ),
        code(
            "result = dl.satisfiable(\n"
            "    dl.And(dl.Exists('r', A('A')), dl.ForAll('r', dl.Not(A('A')))), trace=True)\n"
            "print(result.summary(), '\\n')\n"
            "for line in result.trace:\n"
            "    print(' ', line)"
        ),
        code(
            "sat = dl.satisfiable(dl.And(dl.Exists('r', A('A')), dl.ForAll('r', A('B'))), trace=True)\n"
            "print(sat.summary(), '\\n')\n"
            "for line in sat.trace:\n"
            "    print(' ', line)\n"
            "print('\\nThe successor gets {A, B} -- consistent, so a model exists.')"
        ),
        md(
            "## 3. Blocking: why cyclic axioms terminate\n\n"
            "Now the axiom `Node ⊑ ∃next.Node`. Every node demands a successor, which demands "
            "a successor, forever. A naive tableau does not terminate.\n\n"
            "**Blocking** is the fix: if a node's label is a subset of an ancestor's, we stop "
            "expanding — the ancestor's part of the model can be reused (formally, the model "
            "is folded into a cycle). This single idea is what makes DL reasoning terminate on "
            "cyclic TBoxes."
        ),
        code(
            "tbox = dl.TBox().add(A('Node'), dl.Exists('next', A('Node')))\n"
            "result = dl.satisfiable(A('Node'), tbox, trace=True)\n"
            "print(result.summary(), '\\n')\n"
            "for line in result.trace:\n"
            "    print(' ', line)\n"
            "assert result.satisfiable and result.max_depth < 5\n"
            "print('\\nWithout blocking this would recurse forever; with it, depth stays tiny.')"
        ),
        md(
            "## 4. TBox internalisation\n\n"
            "A general axiom `C ⊑ D` must hold at **every** individual, so the tableau adds "
            "`¬C ⊔ D` to every label. Note what that costs: each axiom becomes a disjunction, "
            "and disjunctions are exactly the branching rule. **A TBox is expensive because "
            "every axiom is another branch point.**"
        ),
        code(
            "tbox = dl.TBox()\n"
            "tbox.add(A('Dog'), A('Mammal'))\n"
            "tbox.add(A('Mammal'), A('Animal'))\n"
            "print('internalised form (added to every node):')\n"
            "for c in tbox.internalised():\n"
            "    print('  ', dl.to_string(c))"
        ),
    ]
    cells += exercise(
        "1.1",
        "Predict, then check",
        "For each concept, predict satisfiable or not **before** running it, then check. "
        "Explain any prediction you got wrong.",
        "candidates = {\n"
        "    'A and not A': dl.And(A('A'), dl.Not(A('A'))),\n"
        "    'A or not A': dl.Or(A('A'), dl.Not(A('A'))),\n"
        "    'exists r.Top and forall r.Bottom': dl.And(dl.Exists('r', dl.Top),\n"
        "                                              dl.ForAll('r', dl.Bottom)),\n"
        "    'forall r.Bottom': dl.ForAll('r', dl.Bottom),\n"
        "}\n"
        "# YOUR CODE HERE: predict, then run dl.satisfiable on each\n",
        "candidates = {\n"
        "    'A and not A': (dl.And(A('A'), dl.Not(A('A'))), False),\n"
        "    'A or not A': (dl.Or(A('A'), dl.Not(A('A'))), True),\n"
        "    'exists r.Top and forall r.Bottom': (dl.And(dl.Exists('r', dl.Top),\n"
        "                                               dl.ForAll('r', dl.Bottom)), False),\n"
        "    'forall r.Bottom': (dl.ForAll('r', dl.Bottom), True),\n"
        "}\n"
        "for name, (c, expected) in candidates.items():\n"
        "    got = dl.satisfiable(c).satisfiable\n"
        "    print(f'  {name:36s} {got}  (expected {expected})')\n"
        "    assert got == expected\n"
        "print('\\nThe last one is the trap: forall r.Bottom is satisfiable by an individual\\n'\n"
        "      'with NO r-successors at all. A universal restriction says nothing about\\n'\n"
        "      'existence -- it constrains only the successors that happen to exist.')",
        hint="`forall` makes no existence claim. What if there are no successors?",
    )
    cells += exercise(
        "1.2",
        "Force the tableau deeper",
        "Write a concept whose tableau reaches depth 3, and confirm it with `max_depth`.",
        "# YOUR CODE HERE\n",
        "c = dl.Exists('r', dl.Exists('r', dl.Exists('r', A('Goal'))))\n"
        "result = dl.satisfiable(c)\n"
        "print(dl.to_string(c))\n"
        "print(result.summary())\n"
        "assert result.satisfiable and result.max_depth == 3\n"
        "print('\\nEach nested existential creates one more individual. Depth is driven by\\n'\n"
        "      'quantifier nesting -- which is why the *shape* of your axioms, not just\\n'\n"
        "      'their number, determines reasoning cost.')",
    )
    return save(cells, HERE / "01_dl_basics_and_tableau.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Which DL am I in, and what does it cost?",
        "Section 3.2",
        "The alphabet soup — ALC, S, SHIQ, SROIQ — is not naming for its own "
        "sake. Each letter is a constructor you added, and each constructor "
        "moves you up a complexity class. Here you compute both halves.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The letters\n\n"
            "Each letter names a constructor. Read this as a **price list**:"
        ),
        code(
            "for letter, meaning in dl.DL_LETTERS.items():\n"
            "    print(f'  {letter:4s} {meaning}')"
        ),
        md(
            "## 2. Naming a knowledge base automatically\n\n"
            "`dl_name` inspects what a TBox actually uses and reports the logic. The rule: "
            "start from **ALC**, or **S** if any role is transitive, then append a letter per "
            "extra constructor.\n\n"
            "This is a skill worth automating precisely because it is easy to get wrong by "
            "eye — one inverse role buried in one axiom changes the logic, and with it the "
            "reasoner you need."
        ),
        code(
            "def show(label, build):\n"
            "    t = dl.TBox(); build(t)\n"
            "    print(f'  {label:30s} -> {dl.dl_name(t):8s} '\n"
            "          f'({\", \".join(sorted(dl.constructors_used(t)))})')\n\n"
            "show('plain ALC', lambda t: t.add(A('A'), dl.And(A('B'), dl.Not(A('C')))))\n"
            "show('+ transitive role', lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),\n"
            "                                     t.transitive_roles.add('r')))\n"
            "show('+ role hierarchy', lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),\n"
            "                                    t.role_hierarchy.append(('r', 's'))))\n"
            "show('+ inverse role', lambda t: t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))))\n"
            "show('+ unqualified number', lambda t: t.add(A('A'), dl.AtLeast(2, 'r')))\n"
            "show('+ qualified number', lambda t: t.add(A('A'), dl.AtLeast(2, 'r', A('B'))))"
        ),
        code(
            "def kitchen_sink(t):\n"
            "    t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B')))\n"
            "    t.add(A('B'), dl.AtLeast(2, 'r', A('C')))\n"
            "    t.transitive_roles.add('r')\n"
            "    t.role_hierarchy.append(('r', 's'))\n"
            "    t.nominals.add('bob')\n\n"
            "t = dl.TBox(); kitchen_sink(t)\n"
            "print('everything at once ->', dl.dl_name(t))\n"
            "print('\\nS + H + O + I + Q. Adding a nominal and an inverse to an otherwise\\n'\n"
            "      'ordinary ontology is how projects end up in SHOIQ without noticing.')"
        ),
        md(
            "> **The N vs Q distinction is worth pausing on.** `>=2 r` (unqualified) is **N**; "
            "`>=2 r.Book` (qualified) is **Q**. It looks like a detail. It is not: Q is "
            "strictly harder, and the difference between `at least two parts` and `at least "
            "two parts that are books` is exactly the kind of modelling choice made casually "
            "in an afternoon."
        ),
        md(
            "## 3. What expressivity costs\n\n"
            "Complexity of concept satisfiability **with respect to a general TBox**, from the "
            "DL literature (Ch. 3.2 and Appendix A):"
        ),
        code(
            "complexity = pd.DataFrame([\n"
            "    {'logic': 'EL',      'satisfiability wrt TBox': 'PTIME-complete',  'note': 'OWL 2 EL'},\n"
            "    {'logic': 'DL-Lite', 'satisfiability wrt TBox': 'PTIME (AC0 data)', 'note': 'OWL 2 QL'},\n"
            "    {'logic': 'ALC',     'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'the baseline'},\n"
            "    {'logic': 'S',       'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'ALC + transitive'},\n"
            "    {'logic': 'SHIQ',    'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'OWL Lite-ish'},\n"
            "    {'logic': 'SHOIQ',   'satisfiability wrt TBox': 'NExpTime-complete', 'note': 'OWL DL'},\n"
            "    {'logic': 'SROIQ',   'satisfiability wrt TBox': 'N2ExpTime-complete', 'note': 'OWL 2 DL'},\n"
            "])\n"
            "print(complexity.to_string(index=False))"
        ),
        md(
            "Those are worst-case bounds, and worst cases are rare in practice — which is why "
            "SROIQ reasoners are usable at all. But the bound tells you what you are exposed "
            "to. Now let's *measure* the branching that produces it."
        ),
        md(
            "## 4. Measuring the exponential\n\n"
            "Disjunction is the branching rule, and branching is where the exponential lives. "
            "Below, `n` independent disjunctions are combined with a contradiction that only "
            "shows up in a **successor** — so every branch must be explored before the tableau "
            "can report failure."
        ),
        code(
            "def blowup(n):\n"
            "    parts = [dl.Or(A(f'A{i}'), A(f'B{i}')) for i in range(n)]\n"
            "    parts += [dl.Exists('r', dl.Top), dl.ForAll('r', dl.Bottom)]\n"
            "    c = parts[0]\n"
            "    for p in parts[1:]:\n"
            "        c = dl.And(c, p)\n"
            "    return c\n\n"
            "rows = []\n"
            "for n in range(0, 8):\n"
            "    r = dl.satisfiable(blowup(n))\n"
            "    rows.append({'disjunctions': n, 'satisfiable': r.satisfiable,\n"
            "                 'branch points': r.branches, 'rule applications': r.steps,\n"
            "                 '2^n - 1': 2 ** n - 1})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "assert all(row['branch points'] == row['2^n - 1'] for row in rows)"
        ),
        md(
            "> **Exactly `2ⁿ − 1`.** That is the ExpTime bound, on your screen, for a concept "
            "you could write on one line. Note the asymmetry: a *satisfiable* concept stops at "
            "the first successful branch, so the blow-up bites hardest when you are trying to "
            "prove something **unsatisfiable** — which is precisely what subsumption checking "
            "does (Notebook 3)."
        ),
    ]
    cells += exercise(
        "2.1",
        "Name three real knowledge bases",
        "For each TBox below, predict the DL name, then check. One of them is more expressive "
        "than it looks.",
        "# YOUR CODE HERE\n",
        "def kb_a(t):\n"
        "    t.add(A('Vegetarian'), dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat')))))\n\n"
        "def kb_b(t):\n"
        "    t.add(A('Branch'), dl.Exists('isPartOf', A('Tree')))\n"
        "    t.transitive_roles.add('isPartOf')\n\n"
        "def kb_c(t):\n"
        "    t.add(A('Manager'), dl.AtLeast(2, 'supervises', A('Employee')))\n"
        "    t.add(A('Employee'), dl.Exists(dl.Inverse('supervises'), A('Manager')))\n"
        "    t.transitive_roles.add('supervises')\n"
        "    t.role_hierarchy.append(('supervises', 'worksWith'))\n\n"
        "expected = {'kb_a': 'ALC', 'kb_b': 'S', 'kb_c': 'SHIQ'}\n"
        "for name, build in [('kb_a', kb_a), ('kb_b', kb_b), ('kb_c', kb_c)]:\n"
        "    t = dl.TBox(); build(t)\n"
        "    got = dl.dl_name(t)\n"
        "    print(f'  {name}: {got:8s} (expected {expected[name]})')\n"
        "    assert got == expected[name]\n"
        "print('\\nkb_b is the surprise: a single transitive role turns ALC into S. Nothing\\n'\n"
        "      'in the axiom text looks different -- the expressivity is in the role box.')",
    )
    cells += exercise(
        "2.2",
        "Find the cheapest fix",
        "`kb_c` above is SHIQ. Remove the **single** declaration that drops it furthest down "
        "the alphabet, and say what modelling power you gave up.",
        "# YOUR CODE HERE\n",
        "def build(t, inverse=True, transitive=True, hierarchy=True, qualified=True):\n"
        "    t.add(A('Manager'), dl.AtLeast(2, 'supervises', A('Employee')) if qualified\n"
        "          else dl.AtLeast(2, 'supervises'))\n"
        "    if inverse:\n"
        "        t.add(A('Employee'), dl.Exists(dl.Inverse('supervises'), A('Manager')))\n"
        "    else:\n"
        "        t.add(A('Employee'), dl.Exists('supervisedBy', A('Manager')))\n"
        "    if transitive:\n"
        "        t.transitive_roles.add('supervises')\n"
        "    if hierarchy:\n"
        "        t.role_hierarchy.append(('supervises', 'worksWith'))\n\n"
        "rows = []\n"
        "for drop in ['nothing', 'inverse', 'transitive', 'hierarchy', 'qualified']:\n"
        "    t = dl.TBox()\n"
        "    build(t, inverse=drop != 'inverse', transitive=drop != 'transitive',\n"
        "          hierarchy=drop != 'hierarchy', qualified=drop != 'qualified')\n"
        "    rows.append({'dropped': drop, 'dl': dl.dl_name(t)})\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "print('\\nDropping the inverse role gives SHQ; dropping transitivity gives ALCHIQ.\\n'\n"
        "      'Neither is free: the inverse role was expressing supervisedBy without a\\n'\n"
        "      'second role to keep in sync, and transitivity was giving management chains\\n'\n"
        "      'for nothing. \"Cheapest\" is a modelling judgement, not a lookup -- which is\\n'\n"
        "      'why this decision belongs to an engineer and not to a tool.')",
    )
    return save(cells, HERE / "02_important_dls.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Reasoning services",
        "Section 3.3",
        "Ontology tools advertise several reasoning services. There is really "
        "only one — concept satisfiability — and everything else is a reduction "
        "to it. Seeing those reductions is the point of this notebook.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. One service, several names\n\n"
            "| Service | Reduces to |\n|---|---|\n"
            "| `C` is satisfiable | *(the primitive)* |\n"
            "| `C ⊑ D` (subsumption) | `C ⊓ ¬D` is **un**satisfiable |\n"
            "| `C ≡ D` (equivalence) | `C ⊑ D` and `D ⊑ C` |\n"
            "| `C`, `D` disjoint | `C ⊓ D` is unsatisfiable |\n"
            "| KB is consistent | `⊤` is satisfiable wrt the TBox |\n"
            "| classification | subsumption for every pair |\n\n"
            "This is why a DL reasoner is one algorithm and not six."
        ),
        code(
            "tbox = dl.TBox()\n"
            "tbox.add(A('Dog'), A('Mammal'))\n"
            "tbox.add(A('Mammal'), A('Animal'))\n\n"
            "print('Dog <= Animal :', dl.subsumes(A('Dog'), A('Animal'), tbox))\n"
            "print('Animal <= Dog :', dl.subsumes(A('Animal'), A('Dog'), tbox))\n"
            "print()\n"
            "print('...because Dog and not Animal is',\n"
            "      'unsatisfiable' if not dl.satisfiable(dl.And(A('Dog'), dl.Not(A('Animal'))),\n"
            "                                           tbox).satisfiable else 'satisfiable')"
        ),
        md(
            "## 2. Classification: the service you are really buying\n\n"
            "Classification computes the **inferred** hierarchy — subsumptions nobody asserted. "
            "This is what makes an ontology more than a data model."
        ),
        code(
            "wildlife = dl.wildlife_tbox()\n"
            "print('asserted axioms:')\n"
            "for ax in wildlife.axioms:\n"
            "    print('  ', ax)"
        ),
        code(
            "names = ['Animal', 'Plant', 'Leaf', 'Herbivore', 'Carnivore', 'Giraffe', 'Lion']\n"
            "inferred = dl.classify(names, wildlife)\n"
            "asserted = {(dl.to_string(ax.left), dl.to_string(ax.right)) for ax in wildlife.axioms}\n"
            "print('inferred subsumptions (those NOT asserted verbatim are the payoff):')\n"
            "for sub, sup in inferred:\n"
            "    mark = '   ' if (sub, sup) in asserted else ' * '\n"
            "    print(f'{mark}{sub} <= {sup}')\n"
            "print('\\n* = derived by the reasoner, not written down by anyone.')"
        ),
        md(
            "## 3. Finding a modelling error the reasoner can see\n\n"
            "The classic result from Chapter 1's integration lab, now in DL form. A `Giraffe` "
            "is a `Herbivore` (eats only plants) that eats some `Leaf`. A `Carnivore` eats "
            "only `Animal`s. `Leaf ⊑ Plant` and `Plant ⊑ ¬Animal`. So:"
        ),
        code(
            "both = dl.And(A('Giraffe'), A('Carnivore'))\n"
            "result = dl.satisfiable(both, wildlife)\n"
            "print('Giraffe and Carnivore :', result.summary())\n"
            "assert not result.satisfiable\n"
            "print('\\nThe class is UNSATISFIABLE: nothing can be both. Note that no human\\n'\n"
            "      'wrote a disjointness axiom between Giraffe and Carnivore -- it follows\\n'\n"
            "      'from what they eat. That is the reasoner earning its keep: it found a\\n'\n"
            "      'consequence of axioms written days apart by different people.')"
        ),
        code(
            "print('the trace that establishes it:')\n"
            "for line in dl.satisfiable(both, wildlife, trace=True).trace[:14]:\n"
            "    print(' ', line)"
        ),
        md(
            "> **An unsatisfiable class is always a bug.** It means the class can have no "
            "instances — so either an axiom is wrong, or the class should never have been "
            "created. Protégé shows these in red for good reason. Chapter 5 makes finding "
            "them part of a methodology."
        ),
    ]
    cells += exercise(
        "3.1",
        "Derive disjointness you never asserted",
        "Extend the wildlife TBox so that `Lion` and `Herbivore` become provably disjoint "
        "**without** writing a disjointness axiom between them. Explain which axioms did the "
        "work.",
        "# YOUR CODE HERE\n",
        "t = dl.wildlife_tbox()\n"
        "print('before:', dl.satisfiable(dl.And(A('Lion'), A('Herbivore')), t).satisfiable)\n\n"
        "# A Lion eats some Herbivore; a Herbivore eats only Plants; so if a Lion were a\n"
        "# Herbivore, the Herbivore it eats would have to be a Plant. Make that impossible:\n"
        "t.add(A('Herbivore'), A('Animal'))          # already implied, stated for clarity\n"
        "t.add(A('Animal'), dl.Not(A('Plant')))      # the missing commitment\n\n"
        "after = dl.satisfiable(dl.And(A('Lion'), A('Herbivore')), t)\n"
        "print('after :', after.satisfiable)\n"
        "assert not after.satisfiable\n"
        "print('\\nThe work was done by Animal <= not Plant. Everything else was already\\n'\n"
        "      'there; the ontology simply had not committed to animals and plants being\\n'\n"
        "      'different kinds of thing. One axiom, and a whole family of errors becomes\\n'\n"
        "      'machine-detectable -- the Chapter 1 no-disjointness smell, from the inside.')",
        hint="What stops the Herbivore that a Lion eats from being a Plant?",
    )
    cells += exercise(
        "3.2",
        "Build an unsatisfiable class on purpose",
        "Write a TBox with an unsatisfiable named concept whose unsatisfiability needs at "
        "least two axioms to derive, and confirm the reasoner finds it.",
        "# YOUR CODE HERE\n",
        "t = dl.TBox()\n"
        "t.add(A('Teetotaller'), dl.ForAll('drinks', dl.Not(A('Alcohol'))))\n"
        "t.add(A('WineLover'), dl.Exists('drinks', A('Wine')))\n"
        "t.add(A('Wine'), A('Alcohol'))\n"
        "t.add(A('SoberSommelier'), dl.And(A('Teetotaller'), A('WineLover')))\n\n"
        "result = dl.satisfiable(A('SoberSommelier'), t)\n"
        "print('SoberSommelier:', result.summary())\n"
        "assert not result.satisfiable\n"
        "# ...and no single axiom is enough on its own:\n"
        "partial = dl.TBox()\n"
        "partial.add(A('Teetotaller'), dl.ForAll('drinks', dl.Not(A('Alcohol'))))\n"
        "partial.add(A('SoberSommelier'), A('Teetotaller'))\n"
        "assert dl.satisfiable(A('SoberSommelier'), partial).satisfiable\n"
        "print('\\nThree axioms cooperate: the universal restriction, the existential, and\\n'\n"
        "      'the Wine <= Alcohol link. Remove any one and the class becomes satisfiable.\\n'\n"
        "      'This is why unsatisfiability is hard to debug by eye -- the cause is\\n'\n"
        "      'distributed across axioms nobody reads together.')",
    )
    return save(cells, HERE / "03_reasoning_services.ipynb")


# --------------------------------------------------------------------------- #
def nb04():
    cells = header(
        CHAPTER,
        "Notebook 4 · Exercises",
        "Section 3.4",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Translate English into DL",
        "Express each statement as a DL axiom and verify the intended entailment holds.",
        "# YOUR CODE HERE\n",
        "t = dl.TBox()\n"
        "# 'A vegetarian is a person that eats no meat.'\n"
        "t.add(A('Vegetarian'), dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat')))), True)\n"
        "# 'A vegan is a vegetarian that eats no dairy.'\n"
        "t.add(A('Vegan'), dl.And(A('Vegetarian'), dl.ForAll('eats', dl.Not(A('Dairy')))), True)\n"
        "# 'Steak is meat.'\n"
        "t.add(A('Steak'), A('Meat'))\n\n"
        "print('Vegan <= Vegetarian      :', dl.subsumes(A('Vegan'), A('Vegetarian'), t))\n"
        "print('Vegetarian <= Vegan      :', dl.subsumes(A('Vegetarian'), A('Vegan'), t))\n"
        "print('Vegetarian eating steak? :',\n"
        "      dl.satisfiable(dl.And(A('Vegetarian'), dl.Exists('eats', A('Steak'))), t).satisfiable)\n"
        "assert dl.subsumes(A('Vegan'), A('Vegetarian'), t)\n"
        "assert not dl.subsumes(A('Vegetarian'), A('Vegan'), t)\n"
        "assert not dl.satisfiable(dl.And(A('Vegetarian'),\n"
        "                                 dl.Exists('eats', A('Steak'))), t).satisfiable\n"
        "print('\\nSubsumption runs one way only -- the same asymmetry as Chapter 2\\'s\\n'\n"
        "      'quantifier order, and just as easy to assert backwards.')",
    )
    cells += exercise(
        "R2",
        "Name the logic for five knowledge bases",
        "Report the DL for each, and rank them by worst-case reasoning complexity.",
        "# YOUR CODE HERE\n",
        "builders = {\n"
        "    'plain':      lambda t: t.add(A('A'), A('B')),\n"
        "    'negation':   lambda t: t.add(A('A'), dl.Not(A('B'))),\n"
        "    'transitive': lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),\n"
        "                             t.transitive_roles.add('r')),\n"
        "    'inverse+num': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),\n"
        "                              t.add(A('B'), dl.AtLeast(2, 'r', A('C')))),\n"
        "    'everything': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),\n"
        "                             t.add(A('B'), dl.AtLeast(2, 'r', A('C'))),\n"
        "                             t.transitive_roles.add('r'),\n"
        "                             t.role_hierarchy.append(('r', 's')),\n"
        "                             t.nominals.add('bob')),\n"
        "}\n"
        "rows = []\n"
        "for name, build in builders.items():\n"
        "    t = dl.TBox(); build(t)\n"
        "    rows.append({'kb': name, 'dl': dl.dl_name(t)})\n"
        "import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))\n"
        "assert dl.dl_name(_t1 := (lambda: (t1 := dl.TBox(), builders['transitive'](t1))[0])()) == 'S'\n"
        "print('\\nRanking by worst case: ALC = S = SHIQ (ExpTime) < SHOIQ (NExpTime).\\n'\n"
        "      'Note ALC and SHIQ share a complexity class -- expressivity and complexity\\n'\n"
        "      'do not increase in lockstep, which is exactly why the letters are worth\\n'\n"
        "      'knowing rather than guessing.')",
    )
    cells += exercise(
        "R3",
        "Explain an unsatisfiability to a colleague",
        "Take the unsatisfiable `Giraffe ⊓ Carnivore`, and produce the shortest chain of "
        "axioms that explains it — the *justification*, in DL terms.",
        "# YOUR CODE HERE\n",
        "w = dl.wildlife_tbox()\n"
        "target = dl.And(A('Giraffe'), A('Carnivore'))\n"
        "assert not dl.satisfiable(target, w).satisfiable\n\n"
        "# A justification is a minimal subset of axioms that still entails the problem.\n"
        "import itertools\n"
        "axioms = w.axioms\n"
        "justification = None\n"
        "for size in range(1, len(axioms) + 1):\n"
        "    for subset in itertools.combinations(axioms, size):\n"
        "        t = dl.TBox(list(subset))\n"
        "        if not dl.satisfiable(target, t).satisfiable:\n"
        "            justification = subset\n"
        "            break\n"
        "    if justification:\n"
        "        break\n\n"
        "print(f'minimal justification ({len(justification)} of {len(axioms)} axioms):')\n"
        "for ax in justification:\n"
        "    print('  ', ax)\n"
        "assert justification and len(justification) < len(axioms)\n"
        "print('\\nThis is what a debugging tool should show you -- not \"unsatisfiable\",\\n'\n"
        "      'but the smallest set of axioms you must change. Computing it by brute\\n'\n"
        "      'force over subsets is exponential; real tools are cleverer, but the\\n'\n"
        "      'definition is exactly this.')",
        hint="Search subsets of the axioms from smallest upward, keeping the first that "
        "still makes the concept unsatisfiable.",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You have a reasoner, you can name the logic you are in, and you can explain an "
            "unsatisfiability with a minimal justification. The problem set (`05_assignment`) "
            "asks the question a practising engineer actually faces: reasoning is **sound but "
            "expensive** — when is it worth calling?"
        )
    ]
    return save(cells, HERE / "04_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03, nb04):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
