"""Generate the Chapter 10 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 10 — Rough, Temporal, and Fuzzy Modelling"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch10_toolkit as ch10
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 10",
        "Three kinds of imperfection a crisp ontology cannot express — things "
        "that happen **over time**, predicates with **no sharp boundary**, and "
        "data too **coarse** to separate the cases you care about — and the "
        "three formalisms that handle them.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | environment check |\n"
            "| 1 | `01_temporal` | 10.1 | **Allen's interval algebra**, composition table derived |\n"
            "| 2 | `02_vagueness_and_granularity` | 10.2 | fuzzy membership + rough approximations |\n"
            "| 3 | `03_exercises` | 10.3 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude advisor that "
            "chooses **and prices** the formalism, a review agent, and a **propagation MDP** |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Use the thirteen Allen relations, and **derive** the composition table "
                    "rather than trusting it.",
                    "Detect an inconsistent temporal network, and say why the check is sound "
                    "but incomplete.",
                    "Model a vague predicate with fuzzy membership, and say what an "
                    "alpha-cut costs you.",
                    "Report a set you cannot describe exactly as a lower and an upper "
                    "approximation.",
                    "Choose between the three, and **price** the choice.",
                ]
            )
        ),
        md(
            "## The one idea shared by all three\n\n"
            "> **Expressivity is never free.**\n\n"
            "Each formalism buys the ability to say something a crisp ontology cannot, and "
            "each charges for it. The bill is not rhetorical: deciding consistency of a "
            "general Allen network is **NP-complete**, while fuzzy membership and rough "
            "approximation stay polynomial. The Claude advisor in the Notebook 4 problem "
            "set is scored on getting *both* the choice and its price right."
        ),
        md("### Sanity check: all thirteen relations, and a derived composition table"),
        code(
            "intervals = [(s, e) for s in range(5) for e in range(s + 1, 6)]\n"
            "observed = {ch10.relation_between(a, b) for a in intervals for b in intervals}\n"
            "print(f'{len(observed)} of {len(ch10.ALLEN_RELATIONS)} relations observed')\n"
            "table = ch10.composition_table()\n"
            "print(f'{len(table)} composition entries derived (13 x 13 = 169)')\n"
            "assert len(observed) == 13 and len(table) == 169"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Time: Allen's interval algebra",
        "Section 10.1",
        "Two intervals can stand in exactly thirteen relations. That fact, plus "
        "a composition table, is enough to catch temporal contradictions no "
        "human reviewer would notice.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. The thirteen relations\n\n"
            "Jointly exhaustive and pairwise disjoint: between any two intervals **exactly "
            "one** holds. Six come in inverse pairs, plus `equals`."
        ),
        code(
            "rows = [{'code': code, 'name': name,\n"
            "         'inverse': ch10.inverse(code)} for code, name in ch10.ALLEN_NAMES.items()]\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        code(
            "examples = [((0, 2), (3, 5)), ((0, 3), (3, 5)), ((0, 4), (2, 6)),\n"
            "            ((1, 3), (1, 5)), ((2, 3), (1, 5)), ((3, 5), (1, 5)),\n"
            "            ((1, 4), (1, 4))]\n"
            "for a, b in examples:\n"
            "    r = ch10.relation_between(a, b)\n"
            "    print(f'  A={a}  B={b}   A {ch10.ALLEN_NAMES[r]:14s} B   ({r})')"
        ),
        md(
            "### Verifying 'exactly one'\n\n"
            "The claim is checkable, so let us check it rather than repeat it."
        ),
        code(
            "intervals = [(s, e) for s in range(5) for e in range(s + 1, 6)]\n"
            "seen = {}\n"
            "for a in intervals:\n"
            "    for b in intervals:\n"
            "        seen.setdefault(ch10.relation_between(a, b), 0)\n"
            "        seen[ch10.relation_between(a, b)] += 1\n"
            "print(f'{len(seen)} distinct relations over {len(intervals)**2} interval pairs')\n"
            "print(dict(sorted(seen.items())))\n"
            "assert len(seen) == 13"
        ),
        md(
            "## 2. The composition table, derived\n\n"
            "If `A r₁ B` and `B r₂ C`, which relations can hold between A and C? Allen "
            "published the 13×13 answer; we **compute** it by enumerating concrete intervals "
            "and recording what actually occurs. A table with 169 entries is exactly the kind "
            "of thing worth deriving rather than transcribing."
        ),
        code(
            "for first, second in [('b', 'b'), ('m', 'm'), ('d', 'b'), ('o', 'o'), ('s', 'f')]:\n"
            "    result = sorted(ch10.compose(first, second))\n"
            "    print(f'  {ch10.ALLEN_NAMES[first]:14s} o {ch10.ALLEN_NAMES[second]:14s} '\n"
            "          f'-> {result}')"
        ),
        code(
            "sizes = {}\n"
            "for (first, second), result in ch10.composition_table().items():\n"
            "    sizes[len(result)] = sizes.get(len(result), 0) + 1\n"
            "print('how informative is a composition?')\n"
            "for size, count in sorted(sizes.items()):\n"
            "    print(f'  {count:3d} entries yield {size:2d} possible relation(s)')\n"
            "print('\\nSome compositions pin the answer exactly (before o before = before);\\n'\n"
            "      'others barely constrain it at all. That spread is why temporal\\n'\n"
            "      'reasoning is search rather than lookup.')"
        ),
        md(
            "## 3. Catching a contradiction\n\n"
            "`A before B`, `B before C`, `C before A`. Obvious on three intervals; not obvious "
            "at all on thirty. Path consistency composes through every third interval until "
            "a label set empties."
        ),
        code(
            "network = ch10.Network.complete(('A', 'B', 'C'),\n"
            "                                {('A', 'B'): {'b'}, ('B', 'C'): {'b'},\n"
            "                                 ('A', 'C'): {'bi'}})\n"
            "print('constraints: A before B, B before C, A after C')\n"
            "print('result     :', ch10.path_consistent(network))\n"
            "print('\\nThe A-C label emptied: no assignment of intervals can satisfy all three.')"
        ),
        code(
            "network = ch10.Network.complete(('A', 'B', 'C'),\n"
            "                                {('A', 'B'): {'b'}, ('B', 'C'): {'b'}})\n"
            "result = ch10.path_consistent(network)\n"
            "print('constraints: A before B, B before C  (A-C left open)')\n"
            "print('result     :', result)\n"
            "print('inferred A-C:', sorted(network.get('A', 'C')))\n"
            "print('\\nPropagation did not just check -- it INFERRED. A before C follows,\\n'\n"
            "      'and the label narrowed from thirteen possibilities to one.')"
        ),
        md(
            "> **Sound but incomplete.** Path consistency can *prove* inconsistency, but a "
            "path-consistent network is not guaranteed satisfiable — deciding that in general "
            "is NP-complete. This is the same expressivity/decidability bargain as Chapters 2 "
            "and 3, in temporal clothing, and it is why Notebook 4 prices temporal reasoning "
            "as **high**."
        ),
    ]
    cells += exercise(
        "1.1",
        "Find the inconsistency in a five-interval schedule",
        "Build a network over five intervals containing a cycle, and confirm the checker "
        "finds it. Then remove one constraint and confirm it becomes consistent.",
        "# YOUR CODE HERE\n",
        "constraints = {('A', 'B'): {'b'}, ('B', 'C'): {'b'}, ('C', 'D'): {'b'},\n"
        "               ('D', 'E'): {'b'}, ('E', 'A'): {'b'}}\n"
        "network = ch10.Network.complete(('A', 'B', 'C', 'D', 'E'), constraints)\n"
        "result = ch10.path_consistent(network)\n"
        "print('with the cycle E before A:', result)\n"
        "assert not result['consistent']\n\n"
        "relaxed = dict(constraints); relaxed.pop(('E', 'A'))\n"
        "network2 = ch10.Network.complete(('A', 'B', 'C', 'D', 'E'), relaxed)\n"
        "result2 = ch10.path_consistent(network2)\n"
        "print('without it              :', result2)\n"
        "print('inferred A-E            :', sorted(network2.get('A', 'E')))\n"
        "assert result2['consistent']\n"
        "print('\\nFive intervals is already past the point where a human reviewer would\\n'\n"
        "      'reliably spot the cycle by eye, and real schedules have hundreds.')",
    )
    cells += exercise(
        "1.2",
        "Check a composition against the published table",
        "Allen's table says `during ∘ before = before`. Verify it from the derived table, "
        "and find a composition that yields the **most** possible relations.",
        "# YOUR CODE HERE\n",
        "assert sorted(ch10.compose('d', 'b')) == ['b']\n"
        "print('during o before ->', sorted(ch10.compose('d', 'b')), ' (matches Allen)')\n\n"
        "table = ch10.composition_table()\n"
        "worst = max(table.items(), key=lambda kv: len(kv[1]))\n"
        "(first, second), result = worst\n"
        "print(f'\\nleast informative: {ch10.ALLEN_NAMES[first]} o {ch10.ALLEN_NAMES[second]}'\n"
        "      f' -> {len(result)} of 13 relations')\n"
        "print('  ', sorted(result))\n"
        "assert len(result) >= 9\n"
        "print('\\nSome compositions tell you almost nothing. A solver that propagates\\n'\n"
        "      'those first wastes its budget -- which is exactly what the MDP in\\n'\n"
        "      'Notebook 4 optimises.')",
    )
    return save(cells, HERE / "01_temporal.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Vagueness and granularity",
        "Section 10.2",
        "Two different failures of crispness. **Vagueness**: there is no height "
        "at which 'tall' switches on. **Granularity**: your attributes cannot "
        "tell two objects apart, so some sets are not exactly describable at "
        "all. Different problems, different formalisms.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. Vagueness: fuzzy membership\n\n"
            "A crisp definition of `tall` needs a threshold, and every threshold is "
            "arbitrary at exactly the point where the decision is hard. Fuzzy sets replace "
            "the boundary with a **degree**."
        ),
        code(
            "heights = [150, 160, 165, 170, 175, 180, 185, 190, 200]\n"
            "rows = [{'height': h, **{name: ch10.membership(name, h)\n"
            "                         for name in ch10.FUZZY_SETS}} for h in heights]\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        code(
            "print('A crisp threshold at 180cm:')\n"
            "for h in [179, 180, 181]:\n"
            "    print(f'  {h}cm -> tall={h >= 180}   (fuzzy: {ch10.membership(\"tall\", h)})')\n"
            "print('\\nThe crisp version says two people 2cm apart are in different\\n'\n"
            "      'categories, and two people 20cm apart (181 and 201) are in the same\\n'\n"
            "      'one. The fuzzy version says what everyone actually means.')"
        ),
        md(
            "### Combining degrees\n\n"
            "A **t-norm** generalises conjunction. Two common choices disagree, and the "
            "choice is a modelling decision rather than a detail."
        ),
        code(
            "print(f\"{'x':>5s}{'y':>6s}{'min':>8s}{'product':>10s}\")\n"
            "for x, y in [(1.0, 0.5), (0.8, 0.8), (0.5, 0.5), (0.2, 0.9)]:\n"
            "    print(f'{x:5.1f}{y:6.1f}{ch10.fuzzy_and(x, y):8.2f}'\n"
            "          f'{ch10.fuzzy_and(x, y, \"product\"):10.2f}')\n"
            "print('\\nmin keeps the worst input; product punishes every additional\\n'\n"
            "      'condition. Neither is right in general -- but they give different\\n'\n"
            "      'answers, so the choice has to be made deliberately.')"
        ),
        code(
            "values = list(range(140, 221))\n"
            "print('degree to which every tall person is average:',\n"
            "      ch10.subsumption_degree('tall', 'average', values))\n"
            "print('degree to which every tall person is tall   :',\n"
            "      ch10.subsumption_degree('tall', 'tall', values))\n"
            "print('\\nFuzzy subsumption takes the INFIMUM over the domain: the worst point\\n'\n"
            "      'decides. One tall-but-not-average height is enough to drive the degree\\n'\n"
            "      'to zero -- the fuzzy reading of \"every\" is as demanding as the crisp one.')"
        ),
        md(
            "### Alpha-cuts: back to crisp, deliberately\n\n"
            "Sooner or later something must act. An **alpha-cut** turns a fuzzy set back into "
            "a crisp one — and reintroduces exactly the arbitrary threshold fuzzification was "
            "meant to avoid. The gain is that the choice is now *explicit*."
        ),
        code(
            "for alpha in [0.25, 0.5, 0.75, 1.0]:\n"
            "    cut = ch10.alpha_cut('tall', alpha, values)\n"
            "    print(f'  alpha={alpha}: tall means >= {min(cut)}cm  ({len(cut)} heights)')\n"
            "print('\\nThe threshold did not disappear; it moved somewhere it can be argued\\n'\n"
            "      'about. That is a real improvement over a magic number in a SPARQL\\n'\n"
            "      'filter, and it is the whole practical benefit.')"
        ),
        md(
            "## 2. Granularity: rough sets\n\n"
            "A different problem entirely. Here nothing is vague — the trouble is that your "
            "**attributes cannot separate** some objects."
        ),
        code(
            "system = ch10.SAMPLE_SYSTEM\n"
            "rows = [{'patient': name, **values} for name, values in system.objects.items()]\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "print()\n"
            "print('indiscernibility classes (granules):')\n"
            "for group in system.indiscernibility():\n"
            "    print('  ', group)"
        ),
        md(
            "`p1` and `p2` are identical on every recorded attribute, as are `p3` and `p4`. "
            "No reasoning can separate them — so any set that contains one but not the other "
            "is **not exactly describable**."
        ),
        code(
            "target = ['p1', 'p3', 'p5']\n"
            "print('target set        :', target)\n"
            "print('lower approximation:', system.lower_approximation(target),\n"
            "      ' (certainly in)')\n"
            "print('upper approximation:', system.upper_approximation(target),\n"
            "      ' (possibly in)')\n"
            "print('boundary region    :', system.boundary(target),\n"
            "      ' (cannot decide)')\n"
            "print('accuracy           :', system.accuracy(target))"
        ),
        code(
            "exact = ['p1', 'p2', 'p5']\n"
            "print('a set that respects the granules:', exact)\n"
            "print('  lower   :', system.lower_approximation(exact))\n"
            "print('  upper   :', system.upper_approximation(exact))\n"
            "print('  boundary:', system.boundary(exact) or '(empty)')\n"
            "print('  accuracy:', system.accuracy(exact))\n"
            "assert system.accuracy(exact) == 1.0\n"
            "print('\\nAccuracy 1.0: this set IS exactly describable with the attributes you\\n'\n"
            "      'have. Rough set theory does not add uncertainty -- it MEASURES the\\n'\n"
            "      'uncertainty your data already had.')"
        ),
        md(
            "> **The distinction worth keeping.** Fuzzy handles predicates with no sharp "
            "boundary. Rough handles data too coarse to draw a boundary you already believe "
            "in. Reaching for the wrong one produces a model that answers a question nobody "
            "asked."
        ),
    ]
    cells += exercise(
        "2.1",
        "Show that adding an attribute shrinks the boundary",
        "Add a third attribute that separates `p3` from `p4`, and show the accuracy of a "
        "target set improving.",
        "# YOUR CODE HERE\n",
        "richer = ch10.InformationSystem({\n"
        "    name: dict(values) for name, values in ch10.SAMPLE_SYSTEM.objects.items()})\n"
        "for name, age in [('p1', 'young'), ('p2', 'young'), ('p3', 'young'),\n"
        "                  ('p4', 'old'), ('p5', 'old'), ('p6', 'young')]:\n"
        "    richer.objects[name]['age'] = age\n\n"
        "target = ['p1', 'p3', 'p5']\n"
        "before = ch10.SAMPLE_SYSTEM.accuracy(target)\n"
        "after = richer.accuracy(target)\n"
        "print('granules before:', ch10.SAMPLE_SYSTEM.indiscernibility())\n"
        "print('granules after :', richer.indiscernibility())\n"
        "print(f'\\naccuracy {before} -> {after}')\n"
        "print('boundary before:', ch10.SAMPLE_SYSTEM.boundary(target))\n"
        "print('boundary after :', richer.boundary(target))\n"
        "assert after > before\n"
        "print('\\nOne more attribute split a granule and moved two patients out of the\\n'\n"
        "      'boundary region. Rough set accuracy therefore measures something\\n'\n"
        "      'actionable: it tells you whether collecting another field would help.')",
        hint="Give `p3` and `p4` different values for the new attribute.",
    )
    cells += exercise(
        "2.2",
        "Pick the right formalism for three requirements",
        "For each requirement, say whether it needs fuzzy, rough or crisp modelling, and "
        "defend the choice in one sentence.",
        "# YOUR CODE HERE\n",
        "cases = {\n"
        "    'Alert when the patient has a high fever.': 'fuzzy',\n"
        "    'Two records agreeing on every field must be one case.': 'rough',\n"
        "    'Each admission has exactly one identifier.': 'crisp',\n"
        "}\n"
        "for text, expected in cases.items():\n"
        "    print(f'{expected:8s} <- {text}')\n"
        "print()\n"
        "print('high fever   : \"high\" has no sharp cut-off; a threshold would be')\n"
        "print('               arbitrary at exactly the temperatures clinicians argue about.')\n"
        "print('identical rec: nothing is vague -- the ATTRIBUTES are too coarse, which is')\n"
        "print('               the rough-set situation, not the fuzzy one.')\n"
        "print('identifier   : sharp by construction; extra machinery buys nothing and')\n"
        "print('               costs reasoning time.')\n"
        "assert set(cases.values()) == {'fuzzy', 'rough', 'crisp'}",
    )
    return save(cells, HERE / "02_vagueness_and_granularity.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 10.3",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Name the relation for six interval pairs",
        "Give the Allen relation for each pair, and its inverse.",
        "# YOUR CODE HERE\n",
        "pairs = [((0, 2), (3, 5)), ((0, 3), (3, 6)), ((0, 5), (2, 3)),\n"
        "         ((1, 4), (1, 6)), ((2, 6), (1, 6)), ((1, 4), (1, 4))]\n"
        "rows = []\n"
        "for a, b in pairs:\n"
        "    r = ch10.relation_between(a, b)\n"
        "    back = ch10.relation_between(b, a)\n"
        "    rows.append({'A': str(a), 'B': str(b), 'A r B': ch10.ALLEN_NAMES[r],\n"
        "                 'B r A': ch10.ALLEN_NAMES[back],\n"
        "                 'inverse holds': ch10.inverse(r) == back})\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "assert all(row['inverse holds'] for row in rows)\n"
        "print('\\nThe inverse relation always holds in the other direction -- a property\\n'\n"
        "      'worth testing, since it is easy to get wrong when hand-writing the table.')",
    )
    cells += exercise(
        "R2",
        "Model 'a warm room' three ways",
        "Give a crisp, a fuzzy and an alpha-cut treatment of the same requirement, and say "
        "what each one costs.",
        "# YOUR CODE HERE\n",
        "temperatures = list(range(10, 36))\n"
        "warm = ch10.trapezoid(16, 21, 26, 31)\n"
        "print('crisp (>= 21):', [t for t in temperatures if t >= 21][:6], '...')\n"
        "print('fuzzy degrees:')\n"
        "for t in [18, 20, 22, 26, 30]:\n"
        "    print(f'   {t}C -> {round(warm(t), 3)}')\n"
        "alpha_half = [t for t in temperatures if warm(t) >= 0.5]\n"
        "print('alpha-cut 0.5:', f'{min(alpha_half)}-{max(alpha_half)}C')\n"
        "assert warm(18) < warm(20) < warm(22) == warm(26) == 1.0   # rises, then plateaus\n"
        "print('\\ncrisp     : one number, indefensible at the boundary, free to reason with.')\n"
        "print('fuzzy     : honest about the gradient, needs a t-norm choice to combine.')\n"
        "print('alpha-cut : back to a number, but one you had to state and can defend.')",
    )
    cells += exercise(
        "R3",
        "Report what your data cannot decide",
        "For a target set, produce the report a clinician could act on: what is certain, "
        "what is possible, and what more data would resolve.",
        "# YOUR CODE HERE\n",
        "system = ch10.SAMPLE_SYSTEM\n"
        "target = ['p1', 'p3', 'p5']\n"
        "print('certainly in the group :', system.lower_approximation(target))\n"
        "print('possibly in the group  :', system.upper_approximation(target))\n"
        "print('undecidable from data  :', system.boundary(target))\n"
        "print('accuracy               :', system.accuracy(target))\n"
        "print()\n"
        "for group in system.indiscernibility():\n"
        "    if len(group) > 1 and any(o in target for o in group) \\\n"
        "            and not set(group) <= set(target):\n"
        "        print(f'  {group} are indiscernible but disagree on membership')\n"
        "assert system.accuracy(target) < 1.0\n"
        "print('\\nThat last line is the actionable part: it names the exact pairs whose\\n'\n"
        "      'separation would raise accuracy, which turns \"collect more data\" into a\\n'\n"
        "      'specific request.')",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "Three formalisms, each with a computable core and a known price. Notebook 4 asks "
            "an agent to choose between them — and prices the *search* that temporal "
            "reasoning requires."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
