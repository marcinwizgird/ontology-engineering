# %% [markdown]
# # Chapter 3 — Description Logics
# ### Notebook 4 · Exercises
#
# *Book reference: Section 3.4*
#
# The book's exercises, executable. Assertions are the marking scheme.

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
CHECK = Grader('Chapter 3 · Notebook 4 exercises')

# %% [markdown]
# ### Exercise R1 — Translate English into DL
#
# Express each statement as a DL axiom and verify the intended entailment holds.

# %% assignment
t_r1 = dl.TBox()
# TODO: 'A vegetarian is a person that eats no meat.'
#       'A vegan is a vegetarian that eats no dairy.'
#       'Steak is meat.'
# Use the class names Vegetarian, Person, Meat, Vegan, Dairy, Steak and the role eats.

# %% solution
t = dl.TBox()
# 'A vegetarian is a person that eats no meat.'
t.add(A('Vegetarian'), dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat')))), True)
# 'A vegan is a vegetarian that eats no dairy.'
t.add(A('Vegan'), dl.And(A('Vegetarian'), dl.ForAll('eats', dl.Not(A('Dairy')))), True)
# 'Steak is meat.'
t.add(A('Steak'), A('Meat'))

print('Vegan <= Vegetarian      :', dl.subsumes(A('Vegan'), A('Vegetarian'), t))
print('Vegetarian <= Vegan      :', dl.subsumes(A('Vegetarian'), A('Vegan'), t))
print('Vegetarian eating steak? :',
      dl.satisfiable(dl.And(A('Vegetarian'), dl.Exists('eats', A('Steak'))), t).satisfiable)
assert dl.subsumes(A('Vegan'), A('Vegetarian'), t)
assert not dl.subsumes(A('Vegetarian'), A('Vegan'), t)
assert not dl.satisfiable(dl.And(A('Vegetarian'),
                                 dl.Exists('eats', A('Steak'))), t).satisfiable
print('\nSubsumption runs one way only -- the same asymmetry as Chapter 2\'s\n'
      'quantifier order, and just as easy to assert backwards.')
t_r1 = t

# %%
# Check for Exercise R1 -- tests the names your code defines.
with CHECK.check('R1', points=1):
    assert dl.subsumes(A('Vegan'), A('Vegetarian'), t_r1)
    assert not dl.subsumes(A('Vegetarian'), A('Vegan'), t_r1)
    assert not dl.satisfiable(dl.And(A('Vegetarian'), dl.Exists('eats', A('Steak'))), t_r1).satisfiable
    assert dl.satisfiable(A('Vegan'), t_r1).satisfiable

# %% [markdown]
# ### Exercise R2 — Name the logic for five knowledge bases
#
# Report the DL for each, and rank them by worst-case reasoning complexity.

# %% assignment
builders = {
    'plain':      lambda t: t.add(A('A'), A('B')),
    'negation':   lambda t: t.add(A('A'), dl.Not(A('B'))),
    'transitive': lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),
                             t.transitive_roles.add('r')),
    'inverse+num': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),
                              t.add(A('B'), dl.AtLeast(2, 'r', A('C')))),
    'everything': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),
                             t.add(A('B'), dl.AtLeast(2, 'r', A('C'))),
                             t.transitive_roles.add('r'),
                             t.role_hierarchy.append(('r', 's')),
                             t.nominals.add('bob')),
}
names_r2 = {}   # TODO: kb -> its DL name

# %% solution
builders = {
    'plain':      lambda t: t.add(A('A'), A('B')),
    'negation':   lambda t: t.add(A('A'), dl.Not(A('B'))),
    'transitive': lambda t: (t.add(A('A'), dl.Exists('r', A('B'))),
                             t.transitive_roles.add('r')),
    'inverse+num': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),
                              t.add(A('B'), dl.AtLeast(2, 'r', A('C')))),
    'everything': lambda t: (t.add(A('A'), dl.Exists(dl.Inverse('r'), A('B'))),
                             t.add(A('B'), dl.AtLeast(2, 'r', A('C'))),
                             t.transitive_roles.add('r'),
                             t.role_hierarchy.append(('r', 's')),
                             t.nominals.add('bob')),
}
rows = []
for name, build in builders.items():
    t = dl.TBox(); build(t)
    rows.append({'kb': name, 'dl': dl.dl_name(t)})
import pandas as pd; print(pd.DataFrame(rows).to_string(index=False))
assert dl.dl_name(_t1 := (lambda: (t1 := dl.TBox(), builders['transitive'](t1))[0])()) == 'S'
print('\nRanking by worst case: ALC = S = SHIQ (ExpTime) < SHOIQ (NExpTime).\n'
      'Note ALC and SHIQ share a complexity class -- expressivity and complexity\n'
      'do not increase in lockstep, which is exactly why the letters are worth\n'
      'knowing rather than guessing.')
names_r2 = {row['kb']: row['dl'] for row in rows}

# %%
# Check for Exercise R2 -- tests the names your code defines.
with CHECK.check('R2', points=1):
    assert names_r2 == {'plain': 'ALC', 'negation': 'ALC', 'transitive': 'S',
                        'inverse+num': 'ALCIQ', 'everything': 'SHOIQ'}

# %% [markdown]
# ### Exercise R3 — Explain an unsatisfiability to a colleague
#
# Take the unsatisfiable `Giraffe ⊓ Carnivore`, and produce the shortest chain of axioms that explains it — the *justification*, in DL terms.

# %% [markdown]
# > **Hint.** Search subsets of the axioms from smallest upward, keeping the first that still makes the concept unsatisfiable.

# %% assignment
w = dl.wildlife_tbox()
target = dl.And(A('Giraffe'), A('Carnivore'))
justification = None   # TODO: a smallest subset of w.axioms that still makes target unsatisfiable

# %% solution
w = dl.wildlife_tbox()
target = dl.And(A('Giraffe'), A('Carnivore'))
assert not dl.satisfiable(target, w).satisfiable

# A justification is a minimal subset of axioms that still entails the problem.
import itertools
axioms = w.axioms
justification = None
for size in range(1, len(axioms) + 1):
    for subset in itertools.combinations(axioms, size):
        t = dl.TBox(list(subset))
        if not dl.satisfiable(target, t).satisfiable:
            justification = subset
            break
    if justification:
        break

print(f'minimal justification ({len(justification)} of {len(axioms)} axioms):')
for ax in justification:
    print('  ', ax)
assert justification and len(justification) < len(axioms)
print('\nThis is what a debugging tool should show you -- not "unsatisfiable",\n'
      'but the smallest set of axioms you must change. Computing it by brute\n'
      'force over subsets is exponential; real tools are cleverer, but the\n'
      'definition is exactly this.')

# %%
# Check for Exercise R3 -- tests the names your code defines.
with CHECK.check('R3', points=1):
    just = list(justification)
    assert all(ax in w.axioms for ax in just)
    assert not dl.satisfiable(target, dl.TBox(just)).satisfiable, "the subset must still entail it"
    assert len(just) == 4, f"{len(just)} axioms: the smallest justification has 4"

# %% [markdown]
# ## Where this leaves you
#
# You have a reasoner, you can name the logic you are in, and you can explain an unsatisfiability with a minimal justification. The problem set (`05_assignment`) puts Claude next to that reasoner and asks the questions a practising engineer actually faces: when should the verdict come from the model and when from the reasoner, what does the model still contribute once a sound checker exists, and is a model that scores well on the Pizza ontology reasoning — or remembering?

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['R1', 'R2', 'R3'])
