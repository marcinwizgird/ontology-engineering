# %% [markdown]
# # Chapter 2 — First-Order Logic and Reasoning
# ### Notebook 1 · Syntax and semantics
#
# *Book reference: Section 2.1*
#
# Syntax says which strings are formulas. Semantics says what makes one **true**. The gap between them is where every modelling error in this course lives, so we make both executable and then look into the gap.

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
CHECK = Grader('Chapter 2 · Notebook 1 exercises')
import _answers     # reference results the checks compare with

# %% [markdown]
# ## 1. Syntax: a formula is a tree, not a string
#
# The ASCII syntax used throughout: `forall`, `exists`, `~` `&` `|` `->` `<->`, predicates as `Name(arg)`. Arguments starting with a **lower-case** letter are variables; **upper-case** are constants.
#
# Precedence, loosest to tightest: `<->`, `->`, `|`, `&`, then `~` and quantifiers.

# %%
examples = [
    'Human(Socrates)',
    'forall x (Human(x) -> Mortal(x))',
    'exists x (Student(x) & Enrolled(x))',
    'forall x exists y Teaches(x, y)',
    '~exists x (Plant(x) & Animal(x))',
]
for text in examples:
    f = fol.parse(text)
    print(f'{text:42s} -> {type(f).__name__:8s} preds={fol.predicates(f)}')

# %% [markdown]
# Parsing is not a formality — it is where an ambiguity in the English is forced to become a decision. Note that `to_string(parse(s))` round-trips, with the implicit precedence made explicit as brackets:

# %%
for text in examples:
    print(f'{text:42s} -> {fol.to_string(fol.parse(text))}')

# %% [markdown]
# ## 2. Semantics: a model is a choice, and truth is relative to it
#
# A model fixes three things: a **domain**, an **extension** for each predicate, and a **denotation** for each constant. Nothing else. Build one by hand:

# %%
m = fol.Model(
    domain=('socrates', 'zeus'),
    extensions={'Human': frozenset({('socrates',)}),
                'Mortal': frozenset({('socrates',)})},
    constants={'Socrates': 'socrates'},
)
print(m.describe())

# %%
for text in ['Human(Socrates)', 'Mortal(Socrates)',
             'forall x (Human(x) -> Mortal(x))',
             'forall x (Human(x) & Mortal(x))',
             'exists x ~Human(x)']:
    print(f'{fol.evaluate(fol.parse(text), m)!s:6s} {text}')

# %% [markdown]
# > Look at rows 3 and 4. `forall x (Human(x) -> Mortal(x))` is **true** here, and `forall x (Human(x) & Mortal(x))` is **false** — because Zeus is in the domain and is not human. Those two formulas are the same English sentence to a careless reader ('all humans are mortal'), and this model is the proof that they are not the same claim. Notebook 2 turns that observation into a tool.

# %% [markdown]
# ## 3. Enumerating models
#
# For a finite domain the space of interpretations is finite, so we can count. This makes 'satisfiable', 'valid' and 'entails' concrete — and immediately shows why we cannot do this for long.

# %%
f = fol.parse('forall x (P(x) -> Q(x))')
models = list(fol.models_of_size([f], 2))
true_in = [m for m in models if fol.evaluate(f, m)]
print(f'{len(models)} interpretations over a 2-element domain; '
      f'the formula is true in {len(true_in)} of them')
print('\none where it is FALSE:')
print(next(m for m in models if not fol.evaluate(f, m)).describe())

# %%
rows = []
for arity, name in [(1, 'one unary P'), (2, 'one binary R')]:
    for size in (1, 2, 3):
        rows.append({'signature': name, 'domain size': size,
                     'interpretations': 2 ** (size ** arity)})
print(pd.DataFrame(rows).to_string(index=False))
print('\nDoubly exponential in arity. This is why model enumeration is a\n'
      'teaching instrument, not a reasoning strategy -- and why Chapter 3\n'
      'gives up expressivity to get tractable reasoning back.')

# %% [markdown]
# ### Exercise 1.1 — Separate two readings with a model
#
# Find a model in which `exists x (Student(x) & Enrolled(x))` is **false** but `exists x (Student(x) -> Enrolled(x))` is **true**. Explain in one sentence why this makes the second a bad translation of 'some student is enrolled'.

# %% [markdown]
# > **Hint.** A one-element domain is enough. Try a world with no students in it.

# %% assignment
witness = None   # TODO: a fol.Model where the conjunctive reading is false
                 #       and the implicative reading is true

# %% solution
conj = fol.parse('exists x (Student(x) & Enrolled(x))')
impl = fol.parse('exists x (Student(x) -> Enrolled(x))')
witness = next(m for m in fol.models_of_size([conj, impl], 1)
               if not fol.evaluate(conj, m) and fol.evaluate(impl, m))
print(witness.describe())
print('\nconjunctive reading:', fol.evaluate(conj, witness))
print('implicative reading:', fol.evaluate(impl, witness))
assert not fol.evaluate(conj, witness) and fol.evaluate(impl, witness)
print('\nWith nobody a student, the implication is vacuously true of everything,\n'
      'so the implicative version is satisfied by a world containing no students\n'
      'at all. It therefore asserts almost nothing, and is never the right\n'
      'translation of an existential claim.')

# %%
# Check for Exercise 1.1 -- tests the names your code defines.
with CHECK.check('1.1', points=1):
    conj = fol.parse("exists x (Student(x) & Enrolled(x))")
    impl = fol.parse("exists x (Student(x) -> Enrolled(x))")
    assert isinstance(witness, fol.Model)
    assert not fol.evaluate(conj, witness) and fol.evaluate(impl, witness)

# %% [markdown]
# ### Exercise 1.2 — Count the models
#
# For `exists x (P(x) & ~Q(x))` over a 2-element domain, count how many interpretations satisfy it, and express that as a fraction of all interpretations.

# %% assignment
n_models = None       # TODO: interpretations of the formula's vocabulary over 2 elements
n_satisfying = None   # TODO: how many of them satisfy it

# %% solution
f = fol.parse('exists x (P(x) & ~Q(x))')
models = list(fol.models_of_size([f], 2))
sat = [m for m in models if fol.evaluate(f, m)]
print(f'{len(sat)} / {len(models)} interpretations satisfy it '
      f'({len(sat)/len(models):.1%})')
assert len(models) == 16 and len(sat) == 7
print('\n16 = 2^2 choices for P times 2^2 for Q. The formula is the negation of\n'
      'forall x (P(x) -> Q(x)), which holds in 9 of the 16 -- so this one holds\n'
      'in the remaining 7. Counting models is a way to *check* a claimed\n'
      'equivalence, not just to satisfy curiosity.')
n_models, n_satisfying = len(models), len(sat)

# %%
# Check for Exercise 1.2 -- tests the names your code defines.
with CHECK.check('1.2', points=1):
    assert (n_models, n_satisfying) == _answers.CH2_1_2

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['1.1', '1.2'])

# %% solution
CHECK.assert_all_passed(['1.1', '1.2'])
