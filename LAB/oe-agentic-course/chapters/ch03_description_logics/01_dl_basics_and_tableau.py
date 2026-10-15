# %% [markdown]
# # Chapter 3 — Description Logics
# ### Notebook 1 · Concepts, models, and a tableau you can read
#
# *Book reference: Section 3.1*
#
# A description logic has three moving parts: concepts, roles, and an interpretation. The reasoning algorithm — the tableau — is the part that turns those definitions into answers, and it is short enough to read in full.

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
CHECK = Grader('Chapter 3 · Notebook 1 exercises')

# %% [markdown]
# ## 1. The concept language
#
# Concepts are built from atomic concepts and roles:
#
# | DL notation | Toolkit | Meaning |
# |---|---|---|
# | `A` | `A('A')` | atomic concept |
# | `C ⊓ D` | `dl.And(C, D)` | conjunction |
# | `C ⊔ D` | `dl.Or(C, D)` | disjunction |
# | `¬C` | `dl.Not(C)` | complement |
# | `∃r.C` | `dl.Exists('r', C)` | existential restriction |
# | `∀r.C` | `dl.ForAll('r', C)` | universal restriction |
# | `⊤` / `⊥` | `dl.Top` / `dl.Bottom` | top / bottom |
#
# **ALC** is exactly this set. Everything in §3.2 is ALC plus something.

# %%
vegetarian = dl.And(A('Person'), dl.ForAll('eats', dl.Not(A('Meat'))))
print('Vegetarian ==', dl.to_string(vegetarian))

giraffe = dl.And(A('Herbivore'), dl.Exists('eats', A('Leaf')))
print('Giraffe    <=', dl.to_string(giraffe))

# %% [markdown]
# ### Negation normal form
#
# The tableau needs negation pushed down to atoms. The rewriting rules are the De Morgan laws plus the quantifier duals `¬∃r.C ≡ ∀r.¬C` and `¬∀r.C ≡ ∃r.¬C` — the same duality you met in Chapter 2.

# %%
for c in [dl.Not(dl.And(A('A'), A('B'))),
          dl.Not(dl.Exists('r', A('A'))),
          dl.Not(dl.ForAll('r', dl.Not(A('A'))))]:
    print(f'{dl.to_string(c):34s} -> {dl.to_string(dl.nnf(c))}')

# %% [markdown]
# ## 2. The tableau: build a model, or fail trying
#
# To decide whether `C` is satisfiable, a tableau **tries to build a model of it**. It keeps a set of concepts (a *label*) for each individual and applies rules:
#
# | Rule | Action |
# |---|---|
# | ⊓ | `C ⊓ D` in the label → add both `C` and `D` |
# | ⊔ | `C ⊔ D` in the label → **branch**: try `C`, else try `D` |
# | ∃ | `∃r.C` → create a fresh `r`-successor labelled `{C}` … |
# | ∀ | … plus every `D` where `∀r.D` is in the current label |
# | clash | `A` and `¬A` both present → this branch fails |
#
# `C` is satisfiable iff **some** branch saturates without a clash. Watch it work:

# %%
result = dl.satisfiable(
    dl.And(dl.Exists('r', A('A')), dl.ForAll('r', dl.Not(A('A')))), trace=True)
print(result.summary(), '\n')
for line in result.trace:
    print(' ', line)

# %%
sat = dl.satisfiable(dl.And(dl.Exists('r', A('A')), dl.ForAll('r', A('B'))), trace=True)
print(sat.summary(), '\n')
for line in sat.trace:
    print(' ', line)
print('\nThe successor gets {A, B} -- consistent, so a model exists.')

# %% [markdown]
# ## 3. Blocking: why cyclic axioms terminate
#
# Now the axiom `Node ⊑ ∃next.Node`. Every node demands a successor, which demands a successor, forever. A naive tableau does not terminate.
#
# **Blocking** is the fix: if a node's label is a subset of an ancestor's, we stop expanding — the ancestor's part of the model can be reused (formally, the model is folded into a cycle). This single idea is what makes DL reasoning terminate on cyclic TBoxes.

# %%
tbox = dl.TBox().add(A('Node'), dl.Exists('next', A('Node')))
result = dl.satisfiable(A('Node'), tbox, trace=True)
print(result.summary(), '\n')
for line in result.trace:
    print(' ', line)
assert result.satisfiable and result.max_depth < 5
print('\nWithout blocking this would recurse forever; with it, depth stays tiny.')

# %% [markdown]
# ## 4. TBox internalisation
#
# A general axiom `C ⊑ D` must hold at **every** individual, so the tableau adds `¬C ⊔ D` to every label. Note what that costs: each axiom becomes a disjunction, and disjunctions are exactly the branching rule. **A TBox is expensive because every axiom is another branch point.**

# %%
tbox = dl.TBox()
tbox.add(A('Dog'), A('Mammal'))
tbox.add(A('Mammal'), A('Animal'))
print('internalised form (added to every node):')
for c in tbox.internalised():
    print('  ', dl.to_string(c))

# %% [markdown]
# ### Exercise 1.1 — Predict, then check
#
# For each concept, predict satisfiable or not **before** running it, then check. Explain any prediction you got wrong.

# %% [markdown]
# > **Hint.** `forall` makes no existence claim. What if there are no successors?

# %% assignment
candidates = {
    'A and not A': dl.And(A('A'), dl.Not(A('A'))),
    'A or not A': dl.Or(A('A'), dl.Not(A('A'))),
    'exists r.Top and forall r.Bottom': dl.And(dl.Exists('r', dl.Top),
                                              dl.ForAll('r', dl.Bottom)),
    'forall r.Bottom': dl.ForAll('r', dl.Bottom),
}
predictions = {}   # TODO: write your prediction (True = satisfiable) for each name FIRST
verdicts = {}      # TODO: then the tableau's verdict for each name (dl.satisfiable)

# %% solution
candidates = {
    'A and not A': (dl.And(A('A'), dl.Not(A('A'))), False),
    'A or not A': (dl.Or(A('A'), dl.Not(A('A'))), True),
    'exists r.Top and forall r.Bottom': (dl.And(dl.Exists('r', dl.Top),
                                               dl.ForAll('r', dl.Bottom)), False),
    'forall r.Bottom': (dl.ForAll('r', dl.Bottom), True),
}
for name, (c, expected) in candidates.items():
    got = dl.satisfiable(c).satisfiable
    print(f'  {name:36s} {got}  (expected {expected})')
    assert got == expected
print('\nThe last one is the trap: forall r.Bottom is satisfiable by an individual\n'
      'with NO r-successors at all. A universal restriction says nothing about\n'
      'existence -- it constrains only the successors that happen to exist.')
predictions = {name: expected for name, (_, expected) in candidates.items()}
verdicts = {name: dl.satisfiable(c).satisfiable for name, (c, _) in candidates.items()}

# %%
# Check for Exercise 1.1 -- tests the names your code defines.
with CHECK.check('1.1', points=1):
    assert set(predictions) == set(verdicts) == {
        'A and not A', 'A or not A', 'exists r.Top and forall r.Bottom', 'forall r.Bottom'}
    assert verdicts == {'A and not A': False, 'A or not A': True,
                        'exists r.Top and forall r.Bottom': False, 'forall r.Bottom': True}
    wrong = [n for n in verdicts if predictions[n] != verdicts[n]]
    print("predictions you got wrong:", wrong or "none")

# %% [markdown]
# ### Exercise 1.2 — Force the tableau deeper
#
# Write a concept whose tableau reaches depth 3, and confirm it with `max_depth`.

# %% assignment
deep = None    # TODO: a satisfiable concept whose tableau reaches depth 3

# %% solution
c = dl.Exists('r', dl.Exists('r', dl.Exists('r', A('Goal'))))
result = dl.satisfiable(c)
print(dl.to_string(c))
print(result.summary())
assert result.satisfiable and result.max_depth == 3
print('\nEach nested existential creates one more individual. Depth is driven by\n'
      'quantifier nesting -- which is why the *shape* of your axioms, not just\n'
      'their number, determines reasoning cost.')
deep = c

# %%
# Check for Exercise 1.2 -- tests the names your code defines.
with CHECK.check('1.2', points=1):
    r = dl.satisfiable(deep)
    assert r.satisfiable and r.max_depth == 3, r.summary()

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['1.1', '1.2'])
