# %% [markdown]
# # Chapter 3 — Description Logics
# ### Notebook 2 · Which DL am I in, and what does it cost?
#
# *Book reference: Section 3.2*
#
# The alphabet soup — ALC, S, SHIQ, SROIQ — is not naming for its own sake. Each letter is a constructor you added, and each constructor moves you up a complexity class. Here you compute both halves.

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
import ch03_toolkit as dl
import pandas as pd
A = dl.Atomic
logging.getLogger("dspy").setLevel(logging.WARNING)
from agentlab.grading import Grader
CHECK = Grader('Chapter 3 · Notebook 2 exercises')

# %% [markdown]
# ## 1. The letters
#
# Each letter names a constructor. Read this as a **price list**:

# %%
for letter, meaning in dl.DL_LETTERS.items():
    print(f'  {letter:4s} {meaning}')

# %% [markdown]
# ## 2. Naming a knowledge base automatically
#
# `dl_name` inspects what a TBox actually uses and reports the logic. The rule: start from **ALC**, or **S** if any role is transitive, then append a letter per extra constructor.
#
# This is a skill worth automating precisely because it is easy to get wrong by eye — one inverse role buried in one axiom changes the logic, and with it the reasoner you need.

# %%
def show(label, build):
    t = dl.TBox(); build(t)
    print(f'  {label:30s} -> {dl.dl_name(t):8s} '
          f'({", ".join(sorted(dl.constructors_used(t)))})')

show('plain ALC', lambda t: t.add(A('A'), dl.And(A('B'), dl.Not(A('C')))))
show('+ transitive role', lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),
                                     t.transitive_roles.add('r')))
show('+ role hierarchy', lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),
                                    t.role_hierarchy.append(('r', 's'))))
show('+ inverse role', lambda t: t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))))
show('+ unqualified number', lambda t: t.add(A('A'), dl.AtLeast(2, 'r')))
show('+ qualified number', lambda t: t.add(A('A'), dl.AtLeast(2, 'r', A('B'))))

# %%
def kitchen_sink(t):
    t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B')))
    t.add(A('B'), dl.AtLeast(2, 'r', A('C')))
    t.transitive_roles.add('r')
    t.role_hierarchy.append(('r', 's'))
    t.nominals.add('bob')

t = dl.TBox(); kitchen_sink(t)
print('everything at once ->', dl.dl_name(t))
print('\nS + H + O + I + Q. Adding a nominal and an inverse to an otherwise\n'
      'ordinary ontology is how projects end up in SHOIQ without noticing.')

# %% [markdown]
# > **The N vs Q distinction is worth pausing on.** `>=2 r` (unqualified) is **N**; `>=2 r.Book` (qualified) is **Q**. It looks like a detail. It is not: Q is strictly harder, and the difference between `at least two parts` and `at least two parts that are books` is exactly the kind of modelling choice made casually in an afternoon.

# %% [markdown]
# ## 3. What expressivity costs
#
# Complexity of concept satisfiability **with respect to a general TBox**, from the DL literature (Ch. 3.2 and Appendix A):

# %%
complexity = pd.DataFrame([
    {'logic': 'EL',      'satisfiability wrt TBox': 'PTIME-complete',  'note': 'OWL 2 EL'},
    {'logic': 'DL-Lite', 'satisfiability wrt TBox': 'PTIME (AC0 data)', 'note': 'OWL 2 QL'},
    {'logic': 'ALC',     'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'the baseline'},
    {'logic': 'S',       'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'ALC + transitive'},
    {'logic': 'SHIQ',    'satisfiability wrt TBox': 'ExpTime-complete', 'note': 'OWL Lite-ish'},
    {'logic': 'SHOIQ',   'satisfiability wrt TBox': 'NExpTime-complete', 'note': 'OWL DL'},
    {'logic': 'SROIQ',   'satisfiability wrt TBox': 'N2ExpTime-complete', 'note': 'OWL 2 DL'},
])
print(complexity.to_string(index=False))

# %% [markdown]
# Those are worst-case bounds, and worst cases are rare in practice — which is why SROIQ reasoners are usable at all. But the bound tells you what you are exposed to. Now let's *measure* the branching that produces it.

# %% [markdown]
# ## 4. Measuring the exponential
#
# Disjunction is the branching rule, and branching is where the exponential lives. Below, `n` independent disjunctions are combined with a contradiction that only shows up in a **successor** — so every branch must be explored before the tableau can report failure.

# %%
def blowup(n):
    parts = [dl.Or(A(f'A{i}'), A(f'B{i}')) for i in range(n)]
    parts += [dl.Exists('r', dl.Top), dl.ForAll('r', dl.Bottom)]
    c = parts[0]
    for p in parts[1:]:
        c = dl.And(c, p)
    return c

rows = []
for n in range(0, 8):
    r = dl.satisfiable(blowup(n))
    rows.append({'disjunctions': n, 'satisfiable': r.satisfiable,
                 'branch points': r.branches, 'rule applications': r.steps,
                 '2^n - 1': 2 ** n - 1})
print(pd.DataFrame(rows).to_string(index=False))
assert all(row['branch points'] == row['2^n - 1'] for row in rows)

# %% [markdown]
# > **Exactly `2ⁿ − 1`.** That is the ExpTime bound, on your screen, for a concept you could write on one line. Note the asymmetry: a *satisfiable* concept stops at the first successful branch, so the blow-up bites hardest when you are trying to prove something **unsatisfiable** — which is precisely what subsumption checking does (Notebook 3).

# %% [markdown]
# ### Exercise 2.1 — Name three real knowledge bases
#
# For each TBox below, predict the DL name, then check. One of them is more expressive than it looks.

# %% assignment
def kb_a(t):
    t.add(A('Vegetarian'), dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat')))))

def kb_b(t):
    t.add(A('Branch'), dl.Exists('isPartOf', A('Tree')))
    t.transitive_roles.add('isPartOf')

def kb_c(t):
    t.add(A('Manager'), dl.AtLeast(2, 'supervises', A('Employee')))
    t.add(A('Employee'), dl.Exists(dl.Inverse('supervises'), A('Manager')))
    t.transitive_roles.add('supervises')
    t.role_hierarchy.append(('supervises', 'worksWith'))

predicted = {}   # TODO: 'kb_a' / 'kb_b' / 'kb_c' -> the DL name you predict, BEFORE running dl.dl_name

# %% solution
def kb_a(t):
    t.add(A('Vegetarian'), dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat')))))

def kb_b(t):
    t.add(A('Branch'), dl.Exists('isPartOf', A('Tree')))
    t.transitive_roles.add('isPartOf')

def kb_c(t):
    t.add(A('Manager'), dl.AtLeast(2, 'supervises', A('Employee')))
    t.add(A('Employee'), dl.Exists(dl.Inverse('supervises'), A('Manager')))
    t.transitive_roles.add('supervises')
    t.role_hierarchy.append(('supervises', 'worksWith'))

expected = {'kb_a': 'ALC', 'kb_b': 'S', 'kb_c': 'SHIQ'}
for name, build in [('kb_a', kb_a), ('kb_b', kb_b), ('kb_c', kb_c)]:
    t = dl.TBox(); build(t)
    got = dl.dl_name(t)
    print(f'  {name}: {got:8s} (expected {expected[name]})')
    assert got == expected[name]
print('\nkb_b is the surprise: a single transitive role turns ALC into S. Nothing\n'
      'in the axiom text looks different -- the expressivity is in the role box.')
predicted = dict(expected)

# %%
# Check for Exercise 2.1 -- tests the names your code defines.
with CHECK.check('2.1', points=1):
    actual = {}
    for name, build in [('kb_a', kb_a), ('kb_b', kb_b), ('kb_c', kb_c)]:
        t = dl.TBox(); build(t); actual[name] = dl.dl_name(t)
    assert set(predicted) == {'kb_a', 'kb_b', 'kb_c'}
    assert predicted == actual, f"predicted {predicted}, the namer says {actual}"

# %% [markdown]
# ### Exercise 2.2 — Find the cheapest fix
#
# `kb_c` above is SHIQ. Remove the **single** declaration that drops it furthest down the alphabet, and say what modelling power you gave up.

# %% assignment
names_22 = {}   # TODO: for 'nothing', 'inverse', 'transitive', 'hierarchy', 'qualified':
                # the DL name of kb_c with that single declaration dropped

# %% solution
def build(t, inverse=True, transitive=True, hierarchy=True, qualified=True):
    t.add(A('Manager'), dl.AtLeast(2, 'supervises', A('Employee')) if qualified
          else dl.AtLeast(2, 'supervises'))
    if inverse:
        t.add(A('Employee'), dl.Exists(dl.Inverse('supervises'), A('Manager')))
    else:
        t.add(A('Employee'), dl.Exists('supervisedBy', A('Manager')))
    if transitive:
        t.transitive_roles.add('supervises')
    if hierarchy:
        t.role_hierarchy.append(('supervises', 'worksWith'))

rows = []
for drop in ['nothing', 'inverse', 'transitive', 'hierarchy', 'qualified']:
    t = dl.TBox()
    build(t, inverse=drop != 'inverse', transitive=drop != 'transitive',
          hierarchy=drop != 'hierarchy', qualified=drop != 'qualified')
    rows.append({'dropped': drop, 'dl': dl.dl_name(t)})
print(pd.DataFrame(rows).to_string(index=False))
print('\nDropping the inverse role gives SHQ; dropping transitivity gives ALCHIQ.\n'
      'Neither is free: the inverse role was expressing supervisedBy without a\n'
      'second role to keep in sync, and transitivity was giving management chains\n'
      'for nothing. "Cheapest" is a modelling judgement, not a lookup -- which is\n'
      'why this decision belongs to an engineer and not to a tool.')
names_22 = {r['dropped']: r['dl'] for r in rows}

# %%
# Check for Exercise 2.2 -- tests the names your code defines.
with CHECK.check('2.2', points=1):
    assert names_22 == {'nothing': 'SHIQ', 'inverse': 'SHQ', 'transitive': 'ALCHIQ',
                        'hierarchy': 'SIQ', 'qualified': 'SHIN'}

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['2.1', '2.2'])
