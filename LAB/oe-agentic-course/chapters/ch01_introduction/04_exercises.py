# %% [markdown]
# # Chapter 1 — Introduction
# ### Notebook 4 · Exercises
#
# *Book reference: Section 1.5*
#
# The book's review questions and exercises, recast as executable tasks. Every solution asserts — the assertions *are* the marking scheme.

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
CHECK = Grader('Chapter 1 · Notebook 4 exercises')

# %% [markdown]
# ## Review questions (§1.5)
#
# The book asks these in prose. Answer each by producing evidence from the corpus, not by recalling a definition.

# %% [markdown]
# ### Exercise R1 — What distinguishes a taxonomy from an ontology?
#
# Produce two artefacts from the corpus that differ *only* in this respect, and the single metric that separates them.

# %% assignment
taxonomy_artefact = None    # TODO: a corpus artefact name
ontology_artefact = None    # TODO: a corpus artefact name
separating_metric = None    # TODO: a key of ont.graph_metrics(...)

# %% solution
tax = ont.load_graph(corpus.get('animals-taxonomy').turtle)
onto = ont.load_graph(corpus.get('awo').turtle)
mt, mo = ont.graph_metrics(tax), ont.graph_metrics(onto)

print(f"{'metric':28s}{'taxonomy':>10s}{'ontology':>10s}")
for k in ['classes', 'subclass_axioms', 'restrictions',
          'disjointness_axioms', 'property_characteristics']:
    print(f'{k:28s}{mt[k]:>10d}{mo[k]:>10d}')

assert mt['subclass_axioms'] > 0 and mo['subclass_axioms'] > 0
assert mt['restrictions'] == 0 and mo['restrictions'] > 0
print('\nBoth have a hierarchy. Only one constrains what its terms may mean.\n'
      'The separating metric is restrictions (axioms beyond subsumption).')
taxonomy_artefact, ontology_artefact, separating_metric = "animals-taxonomy", "awo", "restrictions"

# %%
# Check for Exercise R1 -- tests the names your code defines.
with CHECK.check('R1', points=1):
    levels = {a.name: a.gold_level for a in corpus.CORPUS}
    assert levels[taxonomy_artefact] == "taxonomy" and levels[ontology_artefact] == "formal-ontology"
    mt = ont.graph_metrics(ont.load_graph(corpus.get(taxonomy_artefact).turtle))
    mo = ont.graph_metrics(ont.load_graph(corpus.get(ontology_artefact).turtle))
    assert mt["subclass_axioms"] > 0 and mo["subclass_axioms"] > 0, "both need a hierarchy"
    assert mt[separating_metric] == 0 < mo[separating_metric], "the metric must separate them"

# %% [markdown]
# ### Exercise R2 — Give an example where an ontology changes a query answer
#
# Show a query returning nothing on raw data and something correct after entailment. Report the recall difference numerically.

# %% assignment
recall_before = None   # TODO: recall of the cardiac query on the raw union
recall_after = None    # TODO: recall after alignment + entailment

# %% solution
before = len({p for p, _ in ch1.cardiac_patients(ch1.naive_union())})
after = len({p for p, _ in ch1.cardiac_patients(ch1.integrated(reason=True))})
print(f'cardiac patients found -- raw union: {before}, integrated+reasoned: {after}')
assert before == 0 and after == 4
print(f'recall {before/4:.2f} -> {after/4:.2f}')
recall_before, recall_after = before / 4, after / 4

# %%
# Check for Exercise R2 -- tests the names your code defines.
with CHECK.check('R2', points=1):
    assert recall_before == 0.0 and recall_after == 1.0

# %% [markdown]
# ### Exercise R3 — Name three properties of a 'good' ontology and test them
#
# Choose three properties that are checkable, and evaluate the AWO against them.

# %% assignment
awo = ont.load_graph(corpus.get("awo").turtle)
checks = {}    # TODO: {"<a checkable property of a good ontology>": bool, ...} for the AWO

# %% solution
awo = ont.load_graph(corpus.get('awo').turtle)
m = ont.graph_metrics(awo)
checks = {
    'every class is documented (labelled)':
        not any(f.smell == 'missing-label' for f in ont.scan_smells(awo)),
    'properties carry domain and range':
        not any(f.smell == 'property-without-domain-or-range'
                for f in ont.scan_smells(awo)),
    'the hierarchy is acyclic':
        not any(f.smell == 'subsumption-cycle' for f in ont.scan_smells(awo)),
}
for name, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
assert all(checks.values())
print('\nNote what is NOT checkable this way: whether the ontology is *true*,\n'
      'or useful for its purpose. Those need a domain expert and a use case.')

# %%
# Check for Exercise R3 -- tests the names your code defines.
with CHECK.check('R3', points=1):
    assert len(checks) >= 3, "name at least three properties"
    assert all(isinstance(v, bool) for v in checks.values())
    assert all(checks.values()), "the AWO is the clean positive control: every check should pass"

# %% [markdown]
# ## Exercises (§1.5)

# %% [markdown]
# ### Exercise E1 — Classify an unseen artefact
#
# Write Turtle for a small artefact of your own that lands on **thesaurus** — not taxonomy, not formal ontology — and prove it.

# %% assignment
my_ttl = '''
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/mine#> .
# TODO: a small artefact that lands on "thesaurus"
'''

# %% solution
my_ttl = '''
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/mine#> .

ex:Instrument a owl:Class ; rdfs:label "instrument"@en .
ex:Strings    a owl:Class ; rdfs:label "strings"@en ;
              rdfs:subClassOf ex:Instrument ; skos:broader ex:Instrument .
ex:Violin     a owl:Class ; rdfs:label "violin"@en ;
              rdfs:subClassOf ex:Strings ; skos:related ex:Viola .
ex:Viola      a owl:Class ; rdfs:label "viola"@en ;
              rdfs:subClassOf ex:Strings ; skos:related ex:Violin .
'''
g = ont.load_graph(my_ttl)
result = ont.classify_spectrum(g)
print(result['level'])
for e in result['evidence']:
    print('  -', e)
assert result['level'] == 'thesaurus'
print('\nTo stay a thesaurus it must have SKOS relations and NO restrictions,\n'
      'disjointness or property characteristics. Adding one owl:disjointWith\n'
      'would reclassify it immediately.')

# %%
# Check for Exercise E1 -- tests the names your code defines.
with CHECK.check('E1', points=1):
    assert ont.classify_spectrum(ont.load_graph(my_ttl))["level"] == "thesaurus"

# %% [markdown]
# ### Exercise E2 — Build a defect that no current detector catches
#
# Construct a small ontology that is clearly badly modelled but that `scan_smells` reports as clean. This is an exercise in the **limits** of automated quality checks.

# %% [markdown]
# > **Hint.** Think about a relation that is *not* subsumption being modelled as subsumption.

# %% assignment
sneaky = """
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://example.org/sneaky#> .
# TODO: a badly modelled ontology the scanner reports as clean
"""

# %% solution
sneaky = '''
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://example.org/sneaky#> .

# Modelling a part-whole relation as subsumption: a wheel is NOT a kind of car.
ex:Car   a owl:Class ; rdfs:label "car"@en .
ex:Wheel a owl:Class ; rdfs:label "wheel"@en ; rdfs:subClassOf ex:Car .
ex:Door  a owl:Class ; rdfs:label "door"@en ; rdfs:subClassOf ex:Car .
ex:Car owl:disjointWith ex:Person .
ex:Person a owl:Class ; rdfs:label "person"@en .
'''
g = ont.load_graph(sneaky)
print('scanner says:', ont.smell_summary(g) or 'clean')
assert ont.smell_summary(g) == {}
print('\nYet Wheel SubClassOf Car asserts that every wheel IS a car -- the classic\n'
      'is-a / part-of confusion (Keet Ch. 6.2). No syntactic detector catches it,\n'
      'because syntactically it is a perfectly ordinary subsumption axiom.\n'
      'Catching it needs either a foundational ontology or a human. That is the\n'
      'honest boundary of the tooling in this chapter.')

# %%
# Check for Exercise E2 -- tests the names your code defines.
with CHECK.check('E2', points=1):
    from rdflib import RDFS
    g_sneaky = ont.load_graph(sneaky)
    assert ont.smell_summary(g_sneaky) == {}, "the scanner must report it clean"
    assert any(g_sneaky.triples((None, RDFS.subClassOf, None))), \
        "model something: at least one subsumption axiom"
    # Whether it is *badly* modelled is your written argument, marked by hand.

# %% [markdown]
# ## Where this chapter leaves you
#
# You can now measure what an artefact is, show what it is worth, and detect a class of defects automatically — *and* you have seen exactly where automation stops (Exercise E2). Notebook 5 asks the next question: can an **agent** do this triage, and how would you know whether it does it well?

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['R1', 'R2', 'R3', 'E1', 'E2'])

# %% solution
CHECK.assert_all_passed(['R1', 'R2', 'R3', 'E1', 'E2'])
