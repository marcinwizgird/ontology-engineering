# %% [markdown]
# # Chapter 1 — Introduction
# ### Notebook 2 · What is an ontology actually good for?
#
# *Book reference: Section 1.2 (data and information system integration)*
#
# The textbook argues that ontologies help with integration. Arguments are cheap. Here we build two hospitals that genuinely cannot answer a question, add an ontology, and watch recall go from **0.0 to 1.0**.

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
sys.path.insert(0, str(Path.cwd()))          # so ch01_toolkit imports
import ch01_toolkit as ch1
from agentlab import ontology as ont
import corpus
import pandas as pd
pd.set_option("display.width", 120)
from agentlab.grading import Grader
CHECK = Grader('Chapter 1 · Notebook 2 exercises')

# %% [markdown]
# ## 1. The scenario
#
# Two hospitals record the same clinical reality with no vocabulary in common:
#
# | | Hospital A | Hospital B |
# |---|---|---|
# | patient class | `a:Patient` | `b:Client` |
# | link to disorder | `a:hasDiagnosis` | `b:condition` |
# | a heart attack is | `a:dx_I21` (ICD code) | `b:cond_heartattack` (free text) |
#
# The question we must answer across both: **which patients have a cardiac disorder?** Note that no source system has the concept 'cardiac disorder' at all.

# %%
print(ch1.HOSPITAL_A.split('#')[0] and ch1.HOSPITAL_A[ch1.HOSPITAL_A.index('a:pat001'):][:400])

# %%
print(ch1.HOSPITAL_B[ch1.HOSPITAL_B.index('b:person77'):][:400])

# %% [markdown]
# ## 2. Attempt one: put it all in one graph
#
# The reflex solution — dump both sources into one store and query it. This is the 'data lake' answer, and it is the control condition for our experiment.

# %%
lake = ch1.naive_union()
print(f'{len(lake)} triples from both hospitals')
print('cardiac patients found:', ch1.cardiac_patients(lake))
print('\nZero. The query asks about med:CardiacDisorder, a concept that exists\n'
      'in neither source. Co-location is not integration.')

# %% [markdown]
# ## 3. Attempt two: add the shared ontology and an alignment
#
# Now we introduce the missing piece — a small shared ontology, plus an **alignment** saying how each source's vocabulary maps into it. Note how small the alignment is relative to the payoff.

# %%
print(ch1.ALIGNMENT[ch1.ALIGNMENT.index('a:Patient'):])

# %%
aligned = ch1.integrated(reason=False)
print(f'{len(aligned)} triples (sources + ontology + alignment)')
print('cardiac patients found:', ch1.cardiac_patients(aligned))
print('\nStill zero -- and this is the step everyone gets wrong.')

# %% [markdown]
# > **The key insight of this notebook.** Writing the axioms down changes the *graph*; it does not change the *answers*. The alignment says `a:Patient ⊑ med:Patient`, but nothing has yet concluded that `a:pat001` **is** a `med:Patient`. Integration = alignment **+** entailment. Miss the second half and you have an expensive documentation exercise.

# %% [markdown]
# ## 4. Attempt three: run the reasoner

# %%
full = ch1.integrated(reason=True)
print(f'{len(full)} triples after OWL 2 RL materialisation')
for patient, disorder in ch1.cardiac_patients(full):
    print('  ', patient.split('#')[-1], '->', disorder.split('#')[-1])

# %%
report = ch1.integration_report()
pd.DataFrame(report['rows'])

# %% [markdown]
# Two things to notice, both of which matter in practice:
#
# 1. **Recall goes 0.0 → 0.0 → 1.0.** The value is entirely in the final step.
# 2. **Triples go 33 → 69 → 314.** Materialisation is not free. It trades storage and write-time for query-time simplicity — the classic choice you will meet again in Chapter 8 as *materialisation vs. query rewriting*.
#
# Also note the answer spans **both** hospitals and includes a patient whose record says only 'cardiomyopathy' — a term that never appears in the question.

# %% [markdown]
# ### Exercise 2.1 — Onboard a third hospital
#
# Hospital C arrives with yet another schema: `c:Subject` linked by `c:ails` to `c:ail_mi`, labelled 'MI'. Write the alignment triples that bring it into the integrated view, and show that the cardiac query now returns **five** patients.

# %% [markdown]
# > **Hint.** Three triples: one for the class, one for the property, one typing the ailment.

# %% assignment
HOSPITAL_C = ch1._PREFIXES + '''
@prefix c: <http://example.org/hospitalC#> .
c:subj01 a c:Subject ; c:ails c:ail_mi .
c:ail_mi a c:Ailment ; rdfs:label "MI"@en .
'''
ALIGNMENT_C = None   # TODO: Turtle text (use ch1._PREFIXES + the c: prefix) mapping hospital C

# %% solution
HOSPITAL_C = ch1._PREFIXES + '''
@prefix c: <http://example.org/hospitalC#> .
c:subj01 a c:Subject ; c:ails c:ail_mi .
c:ail_mi a c:Ailment ; rdfs:label "MI"@en .
'''
ALIGNMENT_C = ch1._PREFIXES + '''
@prefix c: <http://example.org/hospitalC#> .
c:Subject rdfs:subClassOf med:Patient .
c:ails rdfs:subPropertyOf med:hasDisorder .
c:ail_mi a med:MyocardialInfarction .
'''

import owlrl
g = ch1.integrated(reason=False)
g.parse(data=HOSPITAL_C, format='turtle')
g.parse(data=ALIGNMENT_C, format='turtle')
owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)

found = ch1.cardiac_patients(g)
patients = {p for p, _ in found}
print(f'{len(patients)} cardiac patients across three hospitals:')
for p in sorted(patients):
    print('  ', p.split('#')[-1])
assert len(patients) == 5
print('\nThree alignment triples were enough. The shared ontology did not change:\n'
      'that is the property that makes this approach scale to the nth source.')

# %%
# Check for Exercise 2.1 -- tests the names your code defines.
with CHECK.check('2.1', points=1):
    import owlrl
    from rdflib import Graph
    g3 = ch1.integrated(reason=False)
    g3.parse(data=HOSPITAL_C, format="turtle")
    g3.parse(data=ALIGNMENT_C, format="turtle")
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g3)
    assert len({p for p, _ in ch1.cardiac_patients(g3)}) == 5, "five cardiac patients expected"
    added = len(Graph().parse(data=ALIGNMENT_C, format="turtle"))
    assert added <= 4, f"{added} alignment triples: three are enough"

# %% [markdown]
# ### Exercise 2.2 — Use an ontology to *find an error*
#
# Section 1.2.2 claims ontologies help with more than integration. Demonstrate error detection: declare `med:CardiacDisorder` and `med:Asthma` disjoint, assert that `a:dx_J45` (asthma) is also a cardiac disorder, and write a SPARQL query that finds the individual violating disjointness.

# %% assignment
bad = None             # TODO: the integrated graph plus the disjointness and the wrong typing
conflict_query = ""    # TODO: SPARQL that finds individuals typed with two disjoint classes

# %% solution
from rdflib import Graph
bad = ch1.integrated(reason=False)
bad.parse(data=ch1._PREFIXES + '''
med:CardiacDisorder owl:disjointWith med:Asthma .
a:dx_J45 a med:CardiacDisorder .
''', format='turtle')

conflict_query = '''
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?individual ?c1 ?c2 WHERE {
  ?c1 owl:disjointWith ?c2 .
  ?individual a ?c1 ; a ?c2 .
}'''
violations = list(bad.query(conflict_query))
for row in violations:
    print('VIOLATION:', str(row[0]).split('#')[-1],
          'is both', str(row[1]).split('#')[-1], 'and', str(row[2]).split('#')[-1])
assert violations, 'the disjointness violation should be detectable'
print('\nWithout the disjointness axiom this data is merely wrong.\n'
      'With it, the error is *detectable by machine* -- which is the entire\n'
      'argument for paying the cost of writing axioms down.')

# %%
# Check for Exercise 2.2 -- tests the names your code defines.
with CHECK.check('2.2', points=1):
    violations = list(bad.query(conflict_query))
    assert violations, "the query must find the violating individual"
    assert any(str(row[0]).endswith("dx_J45") for row in violations), "a:dx_J45 is the violation"

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['2.1', '2.2'])

# %% solution
CHECK.assert_all_passed(['2.1', '2.2'])
