# %% [markdown]
# # Chapter 2 — First-Order Logic and Reasoning
# ### Notebook 2 · Reasoning: entailment, countermodels, proofs
#
# *Book reference: Section 2.2*
#
# Three ways to establish a logical fact — enumerate models, exhibit a countermodel, or derive a proof — and one honest account of what each of them cannot do.

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
CHECK = Grader('Chapter 2 · Notebook 2 exercises')
import _answers     # reference results the checks compare with

# %% [markdown]
# ## 1. Entailment, and the countermodel that refutes it
#
# `premises ⊨ conclusion` means: *every* model of the premises is a model of the conclusion. To refute it you need exactly one **countermodel** — a model where the premises hold and the conclusion fails.
#
# A countermodel is the most useful object in this chapter: it converts "I think your axiom is wrong" into "here is a world your axiom permits that you did not intend".

# %%
premises = [fol.parse('forall x (Human(x) -> Mortal(x))'), fol.parse('Human(Socrates)')]
holds, cm = fol.entails(premises, fol.parse('Mortal(Socrates)'), max_size=3)
print('Socrates is mortal      ->', holds)
holds2, cm2 = fol.entails(premises, fol.parse('Mortal(Plato)'), max_size=3)
print('Plato is mortal         ->', holds2)
print('\ncountermodel:')
print(cm2.describe())

# %% [markdown]
# The countermodel is exactly the objection a careful reviewer would raise: nothing said Plato was human. Note the model is *minimal* — one element — because the search tries small domains first.

# %% [markdown]
# ## 2. The three formalisation mistakes, each with its countermodel
#
# These are the errors Chapter 2 exists to prevent. Each is shown here not as a rule to memorise but as a **difference a machine can witness**.

# %%
for pitfall in fol.QUANTIFIER_PITFALLS:
    wrong, right = fol.parse(pitfall['wrong']), fol.parse(pitfall['right'])
    cm = (fol.find_countermodel([right], wrong, 2)
          or fol.find_countermodel([wrong], right, 2))
    print('=' * 68)
    print(f"[{pitfall['id']}]")
    print(f"  wrong: {pitfall['wrong']}")
    print(f"  right: {pitfall['right']}")
    print(f"  why  : {pitfall['why']}")
    if cm:
        print('  a model where the two disagree:')
        for line in cm.describe().splitlines():
            print('    ', line)

# %% [markdown]
# > **The quantifier-order case deserves a second look.** `forall x exists y Teaches(x,y)` says everyone teaches *something*; `exists y forall x Teaches(x,y)` says there is one thing *everyone* teaches. The countermodel `T = {(e0,e0), (e1,e1)}` is a world where each person teaches only themselves — the first is true, the second false. Entailment runs one way only, and the toolkit will confirm it:

# %%
fa_ex = fol.parse('forall x exists y T(x, y)')
ex_fa = fol.parse('exists y forall x T(x, y)')
print('forall-exists |= exists-forall :', fol.entails([fa_ex], ex_fa, 2)[0])
print('exists-forall |= forall-exists :', fol.entails([ex_fa], fa_ex, 2)[0])

# %% [markdown]
# ## 3. Proof by resolution
#
# Model checking answers *whether*; a proof shows *why*. To prove `Γ ⊨ φ` by refutation: assume `¬φ`, convert everything to clauses, and derive the empty clause.
#
# Our prover works on the **ground** fragment: quantifiers are first expanded over a finite set of constants, then propositional resolution runs. That is a real limitation, stated plainly — no unification, so this is not FOL resolution. It is enough to make the mechanism visible, which is the goal.

# %%
consts = ['Socrates']
clauses = []
for f in premises + [fol.Not(fol.parse('Mortal(Socrates)'))]:
    grounded = fol.ground(f, consts)
    cs = fol.to_cnf_clauses(grounded)
    print(f'{fol.to_string(f):45s} -> {[sorted(c) for c in cs]}')
    clauses += cs

# %%
refuted, steps, trace = fol.resolution_refutation(clauses)
print('refuted (i.e. the conclusion follows):', refuted, f'in {steps} steps\n')
for a, b, r in trace:
    print(f'  {sorted(a)}\n  + {sorted(b)}\n  => {sorted(r) or "EMPTY CLAUSE"}\n')

# %%
# A conclusion that does not follow yields no refutation.
clauses2 = []
for f in premises + [fol.Not(fol.parse('Mortal(Plato)'))]:
    clauses2 += fol.to_cnf_clauses(fol.ground(f, ['Socrates', 'Plato']))
print('Plato refuted?', fol.resolution_refutation(clauses2)[0])

# %% [markdown]
# ## 4. Where this all stops working
#
# Everything above terminates. FOL validity is **undecidable**, so something must have been given up — and it is important to know exactly what.
#
# `entails(..., max_size=n)` searches domains up to size `n`. It can only ever tell you *no countermodel of that size exists*. Here is a formula that is genuinely satisfiable — over the natural numbers with `R` as `<` — but has **no finite model at all**:

# %%
infinite_only = fol.parse(
    '(forall x exists y R(x,y)) & (forall x ~R(x,x)) & '
    '(forall x forall y forall z ((R(x,y) & R(y,z)) -> R(x,z)))')
print('irreflexive + transitive + every element has an R-successor\n')
for n in (1, 2, 3, 4):
    sat, _ = fol.is_satisfiable(infinite_only, max_size=n)
    print(f'  satisfiable in a domain of size <= {n}? {sat}')
print('\nOur tool says "no" at every size we can afford to check. The truth is\n'
      '"yes, but only in an infinite model" -- take the natural numbers with\n'
      'R as <. A finite-model checker cannot distinguish "unsatisfiable" from\n'
      '"needs an infinite model", and no terminating procedure can.')

# %% [markdown]
# > **The lesson that carries into Chapter 3.** You cannot have full FOL expressivity, decidable reasoning, and termination guarantees at once. Chapter 3 makes the trade explicit by *restricting the language* — description logics are fragments of FOL chosen precisely so that reasoning terminates. Everything you meet there is a consequence of the wall you just hit.

# %% [markdown]
# ### Exercise 2.1 — Prove a chain by resolution
#
# Given `every dog is a mammal`, `every mammal is an animal`, and `Rex is a dog`, prove `Rex is an animal` by resolution and print the proof.

# %% assignment
refuted, steps, trace = None, None, None   # TODO: fol.resolution_refutation(...)

# %% solution
prem = [fol.parse('forall x (Dog(x) -> Mammal(x))'),
        fol.parse('forall x (Mammal(x) -> Animal(x))'),
        fol.parse('Dog(Rex)')]
goal = fol.parse('Animal(Rex)')
cl = []
for f in prem + [fol.Not(goal)]:
    cl += fol.to_cnf_clauses(fol.ground(f, ['Rex']))
refuted, steps, trace = fol.resolution_refutation(cl)
print('proved:', refuted, f'({steps} resolution steps)')
for a, b, r in trace:
    print(f'  {sorted(a)} + {sorted(b)} => {sorted(r) or "EMPTY"}')
assert refuted
assert fol.entails(prem, goal, 3)[0]   # agrees with model checking

# %%
# Check for Exercise 2.1 -- tests the names your code defines.
with CHECK.check('2.1', points=1):
    assert refuted is True, "the negated goal must be refuted"
    assert trace and not trace[-1][2], "the proof ends in the empty clause"

# %% [markdown]
# ### Exercise 2.2 — How big must a countermodel be?
#
# `forall x exists y R(x,y)` does not entail `exists y forall x R(x,y)`. Find the **smallest** domain size for which a countermodel exists, and explain why no smaller one works.

# %% [markdown]
# > **Hint.** Increase `max_size` until a countermodel appears.

# %% assignment
smallest_size = None   # TODO: the smallest domain size with a countermodel

# %% solution
prem = fol.parse('forall x exists y R(x, y)')
conc = fol.parse('exists y forall x R(x, y)')
for size in (1, 2, 3):
    holds, cm = fol.entails([prem], conc, max_size=size)
    print(f'searching domains up to {size}: entails={holds}')
    if cm:
        print('  smallest countermodel:')
        for line in cm.describe().splitlines():
            print('    ', line)
        break
assert fol.entails([prem], conc, max_size=1)[0], 'size 1 finds no countermodel'
assert not fol.entails([prem], conc, max_size=2)[0], 'size 2 does'
print('\nOn a one-element domain the only candidate for y is that element, so\n'
      '"everyone has some R" and "something is R-ed by everyone" coincide. You\n'
      'need two elements before the choice of y can depend on x -- which is\n'
      'exactly what quantifier order expresses.')
smallest_size = next(n for n in (1, 2, 3) if not fol.entails([prem], conc, max_size=n)[0])

# %%
# Check for Exercise 2.2 -- tests the names your code defines.
with CHECK.check('2.2', points=1):
    assert smallest_size == _answers.CH2_2_2

# %% [markdown]
# ### Exercise 2.3 — Make the tool give a wrong answer
#
# Construct premises and a conclusion where `entails(..., max_size=2)` reports `True` but the entailment does **not** hold in general. Explain the gap.

# %% [markdown]
# > **Hint.** If the premises themselves have no small model, every conclusion looks entailed.

# %% assignment
prem = []           # TODO: a list of formulas
conclusion = None   # TODO: a formula that entails() wrongly reports as entailed at max_size=2

# %% solution
# 'R is a strict order in which everything has a successor' has no model of
# size <= 2, so ANY conclusion is vacuously 'entailed' at that search depth.
prem = [fol.parse('(forall x exists y R(x,y)) & (forall x ~R(x,x)) & '
                  '(forall x forall y forall z ((R(x,y) & R(y,z)) -> R(x,z)))')]
absurd = fol.parse('forall x ~R(x, x) & forall x R(x, x)')   # a contradiction
print('entails a contradiction at max_size=2?', fol.entails(prem, absurd, 2)[0])
assert fol.entails(prem, absurd, 2)[0]
print('\nThe premises have no model of size <= 2, so the search finds no\n'
      'countermodel and reports True -- vacuously. The premises ARE satisfiable\n'
      '(over the naturals with R as <), so the entailment is false in general.\n'
      'Reading "True" as "valid" here would be a serious error: the tool only\n'
      'ever says "I found no countermodel this small".')
conclusion = absurd

# %%
# Check for Exercise 2.3 -- tests the names your code defines.
with CHECK.check('2.3', points=1):
    assert fol.entails(prem, conclusion, 2)[0], "the tool must report True at max_size=2"
    premises_small_model = any(
        all(fol.evaluate(p, m) for p in prem)
        for size in (1, 2) for m in fol.models_of_size(prem + [conclusion], size))
    assert not premises_small_model or not fol.entails(prem, conclusion, 3)[0], \
        "show the gap: no small model of the premises, or a countermodel at size 3"

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['2.1', '2.2', '2.3'])

# %% solution
CHECK.assert_all_passed(['2.1', '2.2', '2.3'])
