# %% [markdown]
# # Chapter 3 — Description Logics
# ### Notebook 3 · Reasoning services
#
# *Book reference: Section 3.3*
#
# Ontology tools advertise several reasoning services. There is really only one — concept satisfiability — and everything else is a reduction to it. Seeing those reductions is the point of this notebook.

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
CHECK = Grader('Chapter 3 · Notebook 3 exercises')

# %% [markdown]
# ## 1. One service, several names
#
# | Service | Reduces to |
# |---|---|
# | `C` is satisfiable | *(the primitive)* |
# | `C ⊑ D` (subsumption) | `C ⊓ ¬D` is **un**satisfiable |
# | `C ≡ D` (equivalence) | `C ⊑ D` and `D ⊑ C` |
# | `C`, `D` disjoint | `C ⊓ D` is unsatisfiable |
# | KB is consistent | `⊤` is satisfiable wrt the TBox |
# | classification | subsumption for every pair |
#
# This is why a DL reasoner is one algorithm and not six.

# %%
tbox = dl.TBox()
tbox.add(A('Dog'), A('Mammal'))
tbox.add(A('Mammal'), A('Animal'))

print('Dog <= Animal :', dl.subsumes(A('Dog'), A('Animal'), tbox))
print('Animal <= Dog :', dl.subsumes(A('Animal'), A('Dog'), tbox))
print()
print('...because Dog and not Animal is',
      'unsatisfiable' if not dl.satisfiable(dl.And(A('Dog'), dl.Not(A('Animal'))),
                                           tbox).satisfiable else 'satisfiable')

# %% [markdown]
# ## 2. Classification: the service you are really buying
#
# Classification computes the **inferred** hierarchy — subsumptions nobody asserted. This is what makes an ontology more than a data model.

# %%
wildlife = dl.wildlife_tbox()
print('asserted axioms:')
for ax in wildlife.axioms:
    print('  ', ax)

# %%
names = ['Animal', 'Plant', 'Leaf', 'Herbivore', 'Carnivore', 'Giraffe', 'Lion']
inferred = dl.classify(names, wildlife)
asserted = {(dl.to_string(ax.left), dl.to_string(ax.right)) for ax in wildlife.axioms}
print('inferred subsumptions (those NOT asserted verbatim are the payoff):')
for sub, sup in inferred:
    mark = '   ' if (sub, sup) in asserted else ' * '
    print(f'{mark}{sub} <= {sup}')
print('\n* = derived by the reasoner, not written down by anyone.')

# %% [markdown]
# ## 3. Finding a modelling error the reasoner can see
#
# The classic result from Chapter 1's integration lab, now in DL form. A `Giraffe` is a `Herbivore` (eats only plants) that eats some `Leaf`. A `Carnivore` eats only `Animal`s. `Leaf ⊑ Plant` and `Plant ⊑ ¬Animal`. So:

# %%
both = dl.And(A('Giraffe'), A('Carnivore'))
result = dl.satisfiable(both, wildlife)
print('Giraffe and Carnivore :', result.summary())
assert not result.satisfiable
print('\nThe class is UNSATISFIABLE: nothing can be both. Note that no human\n'
      'wrote a disjointness axiom between Giraffe and Carnivore -- it follows\n'
      'from what they eat. That is the reasoner earning its keep: it found a\n'
      'consequence of axioms written days apart by different people.')

# %%
print('the trace that establishes it:')
for line in dl.satisfiable(both, wildlife, trace=True).trace[:14]:
    print(' ', line)

# %% [markdown]
# > **An unsatisfiable class is always a bug.** It means the class can have no instances — so either an axiom is wrong, or the class should never have been created. Protégé shows these in red for good reason. Chapter 5 makes finding them part of a methodology.

# %% [markdown]
# ### Exercise 3.1 — Derive disjointness you never asserted
#
# Extend the wildlife TBox so that `Lion` and `Herbivore` become provably disjoint **without** writing a disjointness axiom between them. Explain which axioms did the work.

# %% [markdown]
# > **Hint.** What stops the Herbivore that a Lion eats from being a Plant?

# %% assignment
t31 = dl.wildlife_tbox()
# TODO: add axioms to t31 so that Lion and Herbivore are provably disjoint,
#       without any axiom that mentions both Lion and Herbivore

# %% solution
t = dl.wildlife_tbox()
print('before:', dl.satisfiable(dl.And(A('Lion'), A('Herbivore')), t).satisfiable)

# A Lion eats some Herbivore; a Herbivore eats only Plants; so if a Lion were a
# Herbivore, the Herbivore it eats would have to be a Plant. Make that impossible:
t.add(A('Herbivore'), A('Animal'))          # already implied, stated for clarity
t.add(A('Animal'), dl.Not(A('Plant')))      # the missing commitment

after = dl.satisfiable(dl.And(A('Lion'), A('Herbivore')), t)
print('after :', after.satisfiable)
assert not after.satisfiable
print('\nThe work was done by Animal <= not Plant. Everything else was already\n'
      'there; the ontology simply had not committed to animals and plants being\n'
      'different kinds of thing. One axiom, and a whole family of errors becomes\n'
      'machine-detectable -- the Chapter 1 no-disjointness smell, from the inside.')
t31 = t

# %%
# Check for Exercise 3.1 -- tests the names your code defines.
with CHECK.check('3.1', points=1):
    base = {str(ax) for ax in dl.wildlife_tbox().axioms}
    added = [ax for ax in t31.axioms if str(ax) not in base]
    assert added, "add at least one axiom"
    assert not any('Lion' in str(ax) and 'Herbivore' in str(ax) for ax in added), \
        "no added axiom may mention both Lion and Herbivore"
    assert not dl.satisfiable(dl.And(A('Lion'), A('Herbivore')), t31).satisfiable

# %% [markdown]
# ### Exercise 3.2 — Build an unsatisfiable class on purpose
#
# Write a TBox with an unsatisfiable named concept whose unsatisfiability needs at least two axioms to derive, and confirm the reasoner finds it.

# %% assignment
t32 = dl.TBox()
unsat_class = None   # TODO: the name of a class that is unsatisfiable in t32,
                     # where no single axiom on its own makes it unsatisfiable

# %% solution
t = dl.TBox()
t.add(A('Teetotaller'), dl.ForAll('drinks', dl.Not(A('Alcohol'))))
t.add(A('WineLover'), dl.Exists('drinks', A('Wine')))
t.add(A('Wine'), A('Alcohol'))
t.add(A('SoberSommelier'), dl.And(A('Teetotaller'), A('WineLover')))

result = dl.satisfiable(A('SoberSommelier'), t)
print('SoberSommelier:', result.summary())
assert not result.satisfiable
# ...and no single axiom is enough on its own:
partial = dl.TBox()
partial.add(A('Teetotaller'), dl.ForAll('drinks', dl.Not(A('Alcohol'))))
partial.add(A('SoberSommelier'), A('Teetotaller'))
assert dl.satisfiable(A('SoberSommelier'), partial).satisfiable
print('\nThree axioms cooperate: the universal restriction, the existential, and\n'
      'the Wine <= Alcohol link. Remove any one and the class becomes satisfiable.\n'
      'This is why unsatisfiability is hard to debug by eye -- the cause is\n'
      'distributed across axioms nobody reads together.')
t32, unsat_class = t, 'SoberSommelier'

# %%
# Check for Exercise 3.2 -- tests the names your code defines.
with CHECK.check('3.2', points=1):
    assert not dl.satisfiable(A(unsat_class), t32).satisfiable
    assert all(dl.satisfiable(A(unsat_class), dl.TBox([ax])).satisfiable for ax in t32.axioms), \
        "some single axiom already makes it unsatisfiable: it must need at least two"

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['3.1', '3.2'])
