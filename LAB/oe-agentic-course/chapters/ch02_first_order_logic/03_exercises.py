# %% [markdown]
# # Chapter 2 — First-Order Logic and Reasoning
# ### Notebook 3 · Exercises
#
# *Book reference: Section 2.3*
#
# The book's exercises, executable. Every solution asserts; the assertions are the marking scheme.

# %%
import sys, os, json, textwrap
from pathlib import Path

# Make the course root (the folder holding agentlab/) and this chapter importable.
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "agentlab").is_dir():
        sys.path.insert(0, str(candidate))
        break
sys.path.insert(0, str(here))

import agentlab
print(json.dumps(agentlab.describe_environment(), indent=1))

# %%
import logging
import ch02_toolkit as fol
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)
from agentlab.grading import Grader
CHECK = Grader('Chapter 2 · Notebook 3 exercises')
import _answers     # reference results the checks compare with

# %% [markdown]
# ### Exercise R1 — Formalise five statements
#
# Translate each into FOL and verify your answer is *semantically* equivalent to the reference (not merely similar as a string).

# %% assignment
statements = {
    'Every lion is a carnivore.': None,
    'Some plant is edible.': None,
    'No carnivore is a plant.': None,
    'Every animal eats something.': None,
    'There is an animal that everything eats.': None,
}
# YOUR CODE HERE: fill in the formulas as strings

# %% solution
def same(a, b, size=2):
    fa, fb = fol.parse(a), fol.parse(b)
    return fol.entails([fa], fb, size)[0] and fol.entails([fb], fa, size)[0]

answers = {
    'Every lion is a carnivore.': 'forall x (Lion(x) -> Carnivore(x))',
    'Some plant is edible.': 'exists x (Plant(x) & Edible(x))',
    'No carnivore is a plant.': 'forall x (Carnivore(x) -> ~Plant(x))',
    'Every animal eats something.': 'forall x (Animal(x) -> exists y Eats(x, y))',
    'There is an animal that everything eats.':
        'exists x (Animal(x) & forall y Eats(y, x))',
}
for english, formula in answers.items():
    fol.parse(formula)          # must parse
    print(f'{english:45s} {formula}')

# 'No carnivore is a plant' is symmetric -- check the alternative reading agrees.
assert same('forall x (Carnivore(x) -> ~Plant(x))',
            '~exists x (Carnivore(x) & Plant(x))')
# ...but the two 'eats' sentences are NOT interchangeable.
assert not same('forall x (Animal(x) -> exists y Eats(x, y))',
                'exists x (Animal(x) & forall y Eats(y, x))')
print('\nNote the last assertion: quantifier order and argument order both\n'
      'matter, and both are easy to get wrong in English.')
statements = answers

# %%
# Check for Exercise R1 -- tests the names your code defines.
with CHECK.check('R1', points=1):
    for english, reference in _answers.CH2_R1.items():
        mine = fol.parse(statements[english])
        ref = fol.parse(reference)
        assert fol.entails([mine], ref, 2)[0] and fol.entails([ref], mine, 2)[0], \
            f"not equivalent to the intended reading: {english}"

# %% [markdown]
# ### Exercise R2 — Decide three entailments
#
# For each pair, decide whether the first entails the second, and produce a countermodel whenever it does not.

# %% assignment
pairs = [
    ("forall x (P(x) -> Q(x))", "forall x (~Q(x) -> ~P(x))"),
    ("exists x (P(x) & Q(x))", "exists x P(x) & exists x Q(x)"),
    ("exists x P(x) & exists x Q(x)", "exists x (P(x) & Q(x))"),
]
verdicts = []   # TODO: one bool per pair: does the first entail the second?

# %% solution
pairs = [
    ('forall x (P(x) -> Q(x))', 'forall x (~Q(x) -> ~P(x))'),   # contraposition
    ('exists x (P(x) & Q(x))', 'exists x P(x) & exists x Q(x)'),
    ('exists x P(x) & exists x Q(x)', 'exists x (P(x) & Q(x))'),
]
for a, b in pairs:
    holds, cm = fol.entails([fol.parse(a)], fol.parse(b), 2)
    print(f'{a}\n  |= {b}\n  -> {holds}')
    if cm:
        print('  countermodel: ' + cm.describe().replace(chr(10), '; '))
    print()
assert fol.entails([fol.parse(pairs[0][0])], fol.parse(pairs[0][1]), 2)[0]
assert fol.entails([fol.parse(pairs[1][0])], fol.parse(pairs[1][1]), 2)[0]
assert not fol.entails([fol.parse(pairs[2][0])], fol.parse(pairs[2][1]), 2)[0]
print('The third fails: separate witnesses for P and Q need not be the same\n'
      'object. This is the same error as reading "some student is enrolled"\n'
      'as two independent claims.')
verdicts = [fol.entails([fol.parse(a)], fol.parse(b), 2)[0] for a, b in pairs]

# %%
# Check for Exercise R2 -- tests the names your code defines.
with CHECK.check('R2', points=1):
    assert verdicts == _answers.CH2_R2

# %% [markdown]
# ### Exercise R3 — Satisfiable, valid, or neither?
#
# Classify each formula. Remember that validity here means *no countermodel up to the search size* — say so in your answer.

# %% assignment
formulas = [
    "forall x (P(x) | ~P(x))",
    "exists x P(x) -> forall x P(x)",
    "forall x P(x) & exists x ~P(x)",
]
verdicts_r3 = []   # TODO: "valid", "satisfiable" or "unsatisfiable" for each (search size 2)

# %% solution
formulas = [
    'forall x (P(x) | ~P(x))',
    'exists x P(x) -> forall x P(x)',
    'forall x P(x) & exists x ~P(x)',
]
rows = []
for text in formulas:
    f = fol.parse(text)
    sat, _ = fol.is_satisfiable(f, 2)
    valid, cm = fol.is_valid(f, 2)
    rows.append({'formula': text, 'satisfiable': sat,
                 'valid (<=2)': valid,
                 'verdict': 'valid' if valid else ('satisfiable' if sat else 'unsatisfiable')})
import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))
assert fol.is_valid(fol.parse(formulas[0]), 2)[0]
assert not fol.is_satisfiable(fol.parse(formulas[2]), 2)[0]
print('\nThe middle one is satisfiable but not valid -- true when P holds of\n'
      'everything or of nothing, false when it holds of some but not all.')
verdicts_r3 = [r["verdict"] for r in rows]

# %%
# Check for Exercise R3 -- tests the names your code defines.
with CHECK.check('R3', points=1):
    assert verdicts_r3 == _answers.CH2_R3

# %% [markdown]
# ## Where this leaves you
#
# You can now settle a formalisation dispute with a countermodel instead of an opinion, and you know precisely how far the tooling can be trusted. Notebook 4 hands the formalisation job to an agent — and uses the semantics you just built as the grader.

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['R1', 'R2', 'R3'])

# %% solution
CHECK.assert_all_passed(['R1', 'R2', 'R3'])
