"""Generate the Chapter 2 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 2 — First-Order Logic and Reasoning"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch02_toolkit as fol
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 2",
        "Chapter 2 is the logical foundation the rest of the book stands on. "
        "Read passively it is a page of symbols. Here every piece of it is a "
        "running program: formulas are objects, models are data, and "
        "**M ⊨ φ** is a function call.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | a working FOL engine |\n"
            "| 1 | `01_syntax_and_semantics` | 2.1 | a parser, and Tarskian satisfaction as code |\n"
            "| 2 | `02_reasoning` | 2.2 | entailment, countermodels, resolution proofs — and the decidability wall |\n"
            "| 3 | `03_exercises` | 2.3 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude policy formaliser, graded *semantically*, and a compliance agent |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Read and write FOL, and check your reading against a machine rather "
                    "than against your intuition.",
                    "Construct a **countermodel** to show that two formalisations differ — "
                    "the single most useful skill in this chapter.",
                    "Run a resolution refutation and read the resulting **proof**.",
                    "State precisely what finite model checking can and cannot decide.",
                    "Build an agent that formalises English, graded by semantics rather "
                    "than string matching.",
                ]
            )
        ),
        md(
            "## The engine\n\n"
            "`ch02_toolkit` is ~400 lines of pure Python: a tokeniser, a recursive-descent "
            "parser, an evaluator, a finite-model enumerator, and a resolution prover. No "
            "external solver. You can read all of it, and you should — the point of this "
            "chapter is that none of this is magic."
        ),
        code(
            "f = fol.parse('forall x (Human(x) -> Mortal(x))')\n"
            "print('AST      :', f)\n"
            "print('rendered :', fol.to_string(f))\n"
            "print('signature:', fol.predicates(f))"
        ),
        md("### Sanity check: the oldest argument in logic"),
        code(
            "premises = [fol.parse('forall x (Human(x) -> Mortal(x))'),\n"
            "            fol.parse('Human(Socrates)')]\n"
            "conclusion = fol.parse('Mortal(Socrates)')\n"
            "holds, countermodel = fol.entails(premises, conclusion, max_size=3)\n"
            "print('entails:', holds, '| countermodel:', countermodel)\n"
            "assert holds and countermodel is None"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Syntax and semantics",
        "Section 2.1",
        "Syntax says which strings are formulas. Semantics says what makes one "
        "**true**. The gap between them is where every modelling error in this "
        "course lives, so we make both executable and then look into the gap.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. Syntax: a formula is a tree, not a string\n\n"
            "The ASCII syntax used throughout: `forall`, `exists`, `~` `&` `|` `->` `<->`, "
            "predicates as `Name(arg)`. Arguments starting with a **lower-case** letter are "
            "variables; **upper-case** are constants.\n\n"
            "Precedence, loosest to tightest: `<->`, `->`, `|`, `&`, then `~` and quantifiers."
        ),
        code(
            "examples = [\n"
            "    'Human(Socrates)',\n"
            "    'forall x (Human(x) -> Mortal(x))',\n"
            "    'exists x (Student(x) & Enrolled(x))',\n"
            "    'forall x exists y Teaches(x, y)',\n"
            "    '~exists x (Plant(x) & Animal(x))',\n"
            "]\n"
            "for text in examples:\n"
            "    f = fol.parse(text)\n"
            "    print(f'{text:42s} -> {type(f).__name__:8s} preds={fol.predicates(f)}')"
        ),
        md(
            "Parsing is not a formality — it is where an ambiguity in the English is forced "
            "to become a decision. Note that `to_string(parse(s))` round-trips, with the "
            "implicit precedence made explicit as brackets:"
        ),
        code(
            "for text in examples:\n"
            "    print(f'{text:42s} -> {fol.to_string(fol.parse(text))}')"
        ),
        md(
            "## 2. Semantics: a model is a choice, and truth is relative to it\n\n"
            "A model fixes three things: a **domain**, an **extension** for each predicate, "
            "and a **denotation** for each constant. Nothing else. Build one by hand:"
        ),
        code(
            "m = fol.Model(\n"
            "    domain=('socrates', 'zeus'),\n"
            "    extensions={'Human': frozenset({('socrates',)}),\n"
            "                'Mortal': frozenset({('socrates',)})},\n"
            "    constants={'Socrates': 'socrates'},\n"
            ")\n"
            "print(m.describe())"
        ),
        code(
            "for text in ['Human(Socrates)', 'Mortal(Socrates)',\n"
            "             'forall x (Human(x) -> Mortal(x))',\n"
            "             'forall x (Human(x) & Mortal(x))',\n"
            "             'exists x ~Human(x)']:\n"
            "    print(f'{fol.evaluate(fol.parse(text), m)!s:6s} {text}')"
        ),
        md(
            "> Look at rows 3 and 4. `forall x (Human(x) -> Mortal(x))` is **true** here, and "
            "`forall x (Human(x) & Mortal(x))` is **false** — because Zeus is in the domain "
            "and is not human. Those two formulas are the same English sentence to a careless "
            "reader ('all humans are mortal'), and this model is the proof that they are not "
            "the same claim. Notebook 2 turns that observation into a tool."
        ),
        md(
            "## 3. Enumerating models\n\n"
            "For a finite domain the space of interpretations is finite, so we can count. "
            "This makes 'satisfiable', 'valid' and 'entails' concrete — and immediately shows "
            "why we cannot do this for long."
        ),
        code(
            "f = fol.parse('forall x (P(x) -> Q(x))')\n"
            "models = list(fol.models_of_size([f], 2))\n"
            "true_in = [m for m in models if fol.evaluate(f, m)]\n"
            "print(f'{len(models)} interpretations over a 2-element domain; '\n"
            "      f'the formula is true in {len(true_in)} of them')\n"
            "print('\\none where it is FALSE:')\n"
            "print(next(m for m in models if not fol.evaluate(f, m)).describe())"
        ),
        code(
            "rows = []\n"
            "for arity, name in [(1, 'one unary P'), (2, 'one binary R')]:\n"
            "    for size in (1, 2, 3):\n"
            "        rows.append({'signature': name, 'domain size': size,\n"
            "                     'interpretations': 2 ** (size ** arity)})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "print('\\nDoubly exponential in arity. This is why model enumeration is a\\n'\n"
            "      'teaching instrument, not a reasoning strategy -- and why Chapter 3\\n'\n"
            "      'gives up expressivity to get tractable reasoning back.')"
        ),
    ]
    cells += exercise(
        "1.1",
        "Separate two readings with a model",
        "Find a model in which `exists x (Student(x) & Enrolled(x))` is **false** but "
        "`exists x (Student(x) -> Enrolled(x))` is **true**. Explain in one sentence why "
        "this makes the second a bad translation of 'some student is enrolled'.",
        "# YOUR CODE HERE\n",
        "conj = fol.parse('exists x (Student(x) & Enrolled(x))')\n"
        "impl = fol.parse('exists x (Student(x) -> Enrolled(x))')\n"
        "witness = next(m for m in fol.models_of_size([conj, impl], 1)\n"
        "               if not fol.evaluate(conj, m) and fol.evaluate(impl, m))\n"
        "print(witness.describe())\n"
        "print('\\nconjunctive reading:', fol.evaluate(conj, witness))\n"
        "print('implicative reading:', fol.evaluate(impl, witness))\n"
        "assert not fol.evaluate(conj, witness) and fol.evaluate(impl, witness)\n"
        "print('\\nWith nobody a student, the implication is vacuously true of everything,\\n'\n"
        "      'so the implicative version is satisfied by a world containing no students\\n'\n"
        "      'at all. It therefore asserts almost nothing, and is never the right\\n'\n"
        "      'translation of an existential claim.')",
        hint="A one-element domain is enough. Try a world with no students in it.",
    )
    cells += exercise(
        "1.2",
        "Count the models",
        "For `exists x (P(x) & ~Q(x))` over a 2-element domain, count how many "
        "interpretations satisfy it, and express that as a fraction of all interpretations.",
        "# YOUR CODE HERE\n",
        "f = fol.parse('exists x (P(x) & ~Q(x))')\n"
        "models = list(fol.models_of_size([f], 2))\n"
        "sat = [m for m in models if fol.evaluate(f, m)]\n"
        "print(f'{len(sat)} / {len(models)} interpretations satisfy it '\n"
        "      f'({len(sat)/len(models):.1%})')\n"
        "assert len(models) == 16 and len(sat) == 7\n"
        "print('\\n16 = 2^2 choices for P times 2^2 for Q. The formula is the negation of\\n'\n"
        "      'forall x (P(x) -> Q(x)), which holds in 9 of the 16 -- so this one holds\\n'\n"
        "      'in the remaining 7. Counting models is a way to *check* a claimed\\n'\n"
        "      'equivalence, not just to satisfy curiosity.')",
    )
    return save(cells, HERE / "01_syntax_and_semantics.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Reasoning: entailment, countermodels, proofs",
        "Section 2.2",
        "Three ways to establish a logical fact — enumerate models, exhibit a "
        "countermodel, or derive a proof — and one honest account of what each "
        "of them cannot do.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. Entailment, and the countermodel that refutes it\n\n"
            "`premises ⊨ conclusion` means: *every* model of the premises is a model of the "
            "conclusion. To refute it you need exactly one **countermodel** — a model where "
            "the premises hold and the conclusion fails.\n\n"
            "A countermodel is the most useful object in this chapter: it converts \"I think "
            "your axiom is wrong\" into \"here is a world your axiom permits that you did not "
            "intend\"."
        ),
        code(
            "premises = [fol.parse('forall x (Human(x) -> Mortal(x))'), fol.parse('Human(Socrates)')]\n"
            "holds, cm = fol.entails(premises, fol.parse('Mortal(Socrates)'), max_size=3)\n"
            "print('Socrates is mortal      ->', holds)\n"
            "holds2, cm2 = fol.entails(premises, fol.parse('Mortal(Plato)'), max_size=3)\n"
            "print('Plato is mortal         ->', holds2)\n"
            "print('\\ncountermodel:')\n"
            "print(cm2.describe())"
        ),
        md(
            "The countermodel is exactly the objection a careful reviewer would raise: nothing "
            "said Plato was human. Note the model is *minimal* — one element — because the "
            "search tries small domains first."
        ),
        md(
            "## 2. The three formalisation mistakes, each with its countermodel\n\n"
            "These are the errors Chapter 2 exists to prevent. Each is shown here not as a "
            "rule to memorise but as a **difference a machine can witness**."
        ),
        code(
            "for pitfall in fol.QUANTIFIER_PITFALLS:\n"
            "    wrong, right = fol.parse(pitfall['wrong']), fol.parse(pitfall['right'])\n"
            "    cm = (fol.find_countermodel([right], wrong, 2)\n"
            "          or fol.find_countermodel([wrong], right, 2))\n"
            "    print('=' * 68)\n"
            "    print(f\"[{pitfall['id']}]\")\n"
            "    print(f\"  wrong: {pitfall['wrong']}\")\n"
            "    print(f\"  right: {pitfall['right']}\")\n"
            "    print(f\"  why  : {pitfall['why']}\")\n"
            "    if cm:\n"
            "        print('  a model where the two disagree:')\n"
            "        for line in cm.describe().splitlines():\n"
            "            print('    ', line)"
        ),
        md(
            "> **The quantifier-order case deserves a second look.** "
            "`forall x exists y Teaches(x,y)` says everyone teaches *something*; "
            "`exists y forall x Teaches(x,y)` says there is one thing *everyone* teaches. "
            "The countermodel `T = {(e0,e0), (e1,e1)}` is a world where each person teaches "
            "only themselves — the first is true, the second false. Entailment runs one way "
            "only, and the toolkit will confirm it:"
        ),
        code(
            "fa_ex = fol.parse('forall x exists y T(x, y)')\n"
            "ex_fa = fol.parse('exists y forall x T(x, y)')\n"
            "print('forall-exists |= exists-forall :', fol.entails([fa_ex], ex_fa, 2)[0])\n"
            "print('exists-forall |= forall-exists :', fol.entails([ex_fa], fa_ex, 2)[0])"
        ),
        md(
            "## 3. Proof by resolution\n\n"
            "Model checking answers *whether*; a proof shows *why*. To prove `Γ ⊨ φ` by "
            "refutation: assume `¬φ`, convert everything to clauses, and derive the empty "
            "clause.\n\n"
            "Our prover works on the **ground** fragment: quantifiers are first expanded over "
            "a finite set of constants, then propositional resolution runs. That is a real "
            "limitation, stated plainly — no unification, so this is not FOL resolution. It is "
            "enough to make the mechanism visible, which is the goal."
        ),
        code(
            "consts = ['Socrates']\n"
            "clauses = []\n"
            "for f in premises + [fol.Not(fol.parse('Mortal(Socrates)'))]:\n"
            "    grounded = fol.ground(f, consts)\n"
            "    cs = fol.to_cnf_clauses(grounded)\n"
            "    print(f'{fol.to_string(f):45s} -> {[sorted(c) for c in cs]}')\n"
            "    clauses += cs"
        ),
        code(
            "refuted, steps, trace = fol.resolution_refutation(clauses)\n"
            "print('refuted (i.e. the conclusion follows):', refuted, f'in {steps} steps\\n')\n"
            "for a, b, r in trace:\n"
            "    print(f'  {sorted(a)}\\n  + {sorted(b)}\\n  => {sorted(r) or \"EMPTY CLAUSE\"}\\n')"
        ),
        code(
            "# A conclusion that does not follow yields no refutation.\n"
            "clauses2 = []\n"
            "for f in premises + [fol.Not(fol.parse('Mortal(Plato)'))]:\n"
            "    clauses2 += fol.to_cnf_clauses(fol.ground(f, ['Socrates', 'Plato']))\n"
            "print('Plato refuted?', fol.resolution_refutation(clauses2)[0])"
        ),
        md(
            "## 4. Where this all stops working\n\n"
            "Everything above terminates. FOL validity is **undecidable**, so something must "
            "have been given up — and it is important to know exactly what.\n\n"
            "`entails(..., max_size=n)` searches domains up to size `n`. It can only ever tell "
            "you *no countermodel of that size exists*. Here is a formula that is genuinely "
            "satisfiable — over the natural numbers with `R` as `<` — but has **no finite "
            "model at all**:"
        ),
        code(
            "infinite_only = fol.parse(\n"
            "    '(forall x exists y R(x,y)) & (forall x ~R(x,x)) & '\n"
            "    '(forall x forall y forall z ((R(x,y) & R(y,z)) -> R(x,z)))')\n"
            "print('irreflexive + transitive + every element has an R-successor\\n')\n"
            "for n in (1, 2, 3, 4):\n"
            "    sat, _ = fol.is_satisfiable(infinite_only, max_size=n)\n"
            "    print(f'  satisfiable in a domain of size <= {n}? {sat}')\n"
            "print('\\nOur tool says \"no\" at every size we can afford to check. The truth is\\n'\n"
            "      '\"yes, but only in an infinite model\" -- take the natural numbers with\\n'\n"
            "      'R as <. A finite-model checker cannot distinguish \"unsatisfiable\" from\\n'\n"
            "      '\"needs an infinite model\", and no terminating procedure can.')"
        ),
        md(
            "> **The lesson that carries into Chapter 3.** You cannot have full FOL "
            "expressivity, decidable reasoning, and termination guarantees at once. Chapter 3 "
            "makes the trade explicit by *restricting the language* — description logics are "
            "fragments of FOL chosen precisely so that reasoning terminates. Everything "
            "you meet there is a consequence of the wall you just hit."
        ),
    ]
    cells += exercise(
        "2.1",
        "Prove a chain by resolution",
        "Given `every dog is a mammal`, `every mammal is an animal`, and `Rex is a dog`, prove "
        "`Rex is an animal` by resolution and print the proof.",
        "# YOUR CODE HERE\n",
        "prem = [fol.parse('forall x (Dog(x) -> Mammal(x))'),\n"
        "        fol.parse('forall x (Mammal(x) -> Animal(x))'),\n"
        "        fol.parse('Dog(Rex)')]\n"
        "goal = fol.parse('Animal(Rex)')\n"
        "cl = []\n"
        "for f in prem + [fol.Not(goal)]:\n"
        "    cl += fol.to_cnf_clauses(fol.ground(f, ['Rex']))\n"
        "refuted, steps, trace = fol.resolution_refutation(cl)\n"
        "print('proved:', refuted, f'({steps} resolution steps)')\n"
        "for a, b, r in trace:\n"
        "    print(f'  {sorted(a)} + {sorted(b)} => {sorted(r) or \"EMPTY\"}')\n"
        "assert refuted\n"
        "assert fol.entails(prem, goal, 3)[0]   # agrees with model checking",
    )
    cells += exercise(
        "2.2",
        "How big must a countermodel be?",
        "`forall x exists y R(x,y)` does not entail `exists y forall x R(x,y)`. Find the "
        "**smallest** domain size for which a countermodel exists, and explain why no smaller "
        "one works.",
        "# YOUR CODE HERE\n",
        "prem = fol.parse('forall x exists y R(x, y)')\n"
        "conc = fol.parse('exists y forall x R(x, y)')\n"
        "for size in (1, 2, 3):\n"
        "    holds, cm = fol.entails([prem], conc, max_size=size)\n"
        "    print(f'searching domains up to {size}: entails={holds}')\n"
        "    if cm:\n"
        "        print('  smallest countermodel:')\n"
        "        for line in cm.describe().splitlines():\n"
        "            print('    ', line)\n"
        "        break\n"
        "assert fol.entails([prem], conc, max_size=1)[0], 'size 1 finds no countermodel'\n"
        "assert not fol.entails([prem], conc, max_size=2)[0], 'size 2 does'\n"
        "print('\\nOn a one-element domain the only candidate for y is that element, so\\n'\n"
        "      '\"everyone has some R\" and \"something is R-ed by everyone\" coincide. You\\n'\n"
        "      'need two elements before the choice of y can depend on x -- which is\\n'\n"
        "      'exactly what quantifier order expresses.')",
        hint="Increase `max_size` until a countermodel appears.",
    )
    cells += exercise(
        "2.3",
        "Make the tool give a wrong answer",
        "Construct premises and a conclusion where `entails(..., max_size=2)` reports `True` "
        "but the entailment does **not** hold in general. Explain the gap.",
        "# YOUR CODE HERE\n",
        "# 'R is a strict order in which everything has a successor' has no model of\n"
        "# size <= 2, so ANY conclusion is vacuously 'entailed' at that search depth.\n"
        "prem = [fol.parse('(forall x exists y R(x,y)) & (forall x ~R(x,x)) & '\n"
        "                  '(forall x forall y forall z ((R(x,y) & R(y,z)) -> R(x,z)))')]\n"
        "absurd = fol.parse('forall x ~R(x, x) & forall x R(x, x)')   # a contradiction\n"
        "print('entails a contradiction at max_size=2?', fol.entails(prem, absurd, 2)[0])\n"
        "assert fol.entails(prem, absurd, 2)[0]\n"
        "print('\\nThe premises have no model of size <= 2, so the search finds no\\n'\n"
        "      'countermodel and reports True -- vacuously. The premises ARE satisfiable\\n'\n"
        "      '(over the naturals with R as <), so the entailment is false in general.\\n'\n"
        "      'Reading \"True\" as \"valid\" here would be a serious error: the tool only\\n'\n"
        "      'ever says \"I found no countermodel this small\".')",
        hint="If the premises themselves have no small model, every conclusion looks entailed.",
    )
    return save(cells, HERE / "02_reasoning.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 2.3",
        "The book's exercises, executable. Every solution asserts; the assertions "
        "are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Formalise five statements",
        "Translate each into FOL and verify your answer is *semantically* equivalent to the "
        "reference (not merely similar as a string).",
        "statements = {\n"
        "    'Every lion is a carnivore.': None,\n"
        "    'Some plant is edible.': None,\n"
        "    'No carnivore is a plant.': None,\n"
        "    'Every animal eats something.': None,\n"
        "    'There is an animal that everything eats.': None,\n"
        "}\n"
        "# YOUR CODE HERE: fill in the formulas as strings\n",
        "def same(a, b, size=2):\n"
        "    fa, fb = fol.parse(a), fol.parse(b)\n"
        "    return fol.entails([fa], fb, size)[0] and fol.entails([fb], fa, size)[0]\n\n"
        "answers = {\n"
        "    'Every lion is a carnivore.': 'forall x (Lion(x) -> Carnivore(x))',\n"
        "    'Some plant is edible.': 'exists x (Plant(x) & Edible(x))',\n"
        "    'No carnivore is a plant.': 'forall x (Carnivore(x) -> ~Plant(x))',\n"
        "    'Every animal eats something.': 'forall x (Animal(x) -> exists y Eats(x, y))',\n"
        "    'There is an animal that everything eats.':\n"
        "        'exists x (Animal(x) & forall y Eats(y, x))',\n"
        "}\n"
        "for english, formula in answers.items():\n"
        "    fol.parse(formula)          # must parse\n"
        "    print(f'{english:45s} {formula}')\n\n"
        "# 'No carnivore is a plant' is symmetric -- check the alternative reading agrees.\n"
        "assert same('forall x (Carnivore(x) -> ~Plant(x))',\n"
        "            '~exists x (Carnivore(x) & Plant(x))')\n"
        "# ...but the two 'eats' sentences are NOT interchangeable.\n"
        "assert not same('forall x (Animal(x) -> exists y Eats(x, y))',\n"
        "                'exists x (Animal(x) & forall y Eats(y, x))')\n"
        "print('\\nNote the last assertion: quantifier order and argument order both\\n'\n"
        "      'matter, and both are easy to get wrong in English.')",
    )
    cells += exercise(
        "R2",
        "Decide three entailments",
        "For each pair, decide whether the first entails the second, and produce a "
        "countermodel whenever it does not.",
        "# YOUR CODE HERE\n",
        "pairs = [\n"
        "    ('forall x (P(x) -> Q(x))', 'forall x (~Q(x) -> ~P(x))'),   # contraposition\n"
        "    ('exists x (P(x) & Q(x))', 'exists x P(x) & exists x Q(x)'),\n"
        "    ('exists x P(x) & exists x Q(x)', 'exists x (P(x) & Q(x))'),\n"
        "]\n"
        "for a, b in pairs:\n"
        "    holds, cm = fol.entails([fol.parse(a)], fol.parse(b), 2)\n"
        "    print(f'{a}\\n  |= {b}\\n  -> {holds}')\n"
        "    if cm:\n"
        "        print('  countermodel: ' + cm.describe().replace(chr(10), '; '))\n"
        "    print()\n"
        "assert fol.entails([fol.parse(pairs[0][0])], fol.parse(pairs[0][1]), 2)[0]\n"
        "assert fol.entails([fol.parse(pairs[1][0])], fol.parse(pairs[1][1]), 2)[0]\n"
        "assert not fol.entails([fol.parse(pairs[2][0])], fol.parse(pairs[2][1]), 2)[0]\n"
        "print('The third fails: separate witnesses for P and Q need not be the same\\n'\n"
        "      'object. This is the same error as reading \"some student is enrolled\"\\n'\n"
        "      'as two independent claims.')",
    )
    cells += exercise(
        "R3",
        "Satisfiable, valid, or neither?",
        "Classify each formula. Remember that validity here means *no countermodel up to the "
        "search size* — say so in your answer.",
        "# YOUR CODE HERE\n",
        "formulas = [\n"
        "    'forall x (P(x) | ~P(x))',\n"
        "    'exists x P(x) -> forall x P(x)',\n"
        "    'forall x P(x) & exists x ~P(x)',\n"
        "]\n"
        "rows = []\n"
        "for text in formulas:\n"
        "    f = fol.parse(text)\n"
        "    sat, _ = fol.is_satisfiable(f, 2)\n"
        "    valid, cm = fol.is_valid(f, 2)\n"
        "    rows.append({'formula': text, 'satisfiable': sat,\n"
        "                 'valid (<=2)': valid,\n"
        "                 'verdict': 'valid' if valid else ('satisfiable' if sat else 'unsatisfiable')})\n"
        "import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))\n"
        "assert fol.is_valid(fol.parse(formulas[0]), 2)[0]\n"
        "assert not fol.is_satisfiable(fol.parse(formulas[2]), 2)[0]\n"
        "print('\\nThe middle one is satisfiable but not valid -- true when P holds of\\n'\n"
        "      'everything or of nothing, false when it holds of some but not all.')",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You can now settle a formalisation dispute with a countermodel instead of an "
            "opinion, and you know precisely how far the tooling can be trusted. Notebook 4 "
            "hands the formalisation job to an agent — and uses the semantics you just built "
            "as the grader."
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
