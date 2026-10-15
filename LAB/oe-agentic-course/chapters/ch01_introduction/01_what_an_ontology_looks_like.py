# %% [markdown]
# # Chapter 1 — Introduction
# ### Notebook 1 · What does an ontology look like?
#
# *Book reference: Section 1.1*
#
# The book answers this question with a picture. We answer it with a measurement — and then discover that the measurement forces us to be precise about a word the field uses loosely.

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
CHECK = Grader('Chapter 1 · Notebook 1 exercises')

# %% [markdown]
# ## 1. Vocabulary versus axioms
#
# An ontology has two separable parts, and conflating them is the single most common confusion in this field:
#
# * the **vocabulary** — the named terms (classes, properties, individuals);
# * the **axioms** — the logical statements that constrain what those terms can mean.
#
# A file with 500 classes and no axioms is a *word list with URIs*. Let's look at both parts of the African Wildlife Ontology separately.

# %%
from agentlab.sparql import SparqlStore
store = SparqlStore.in_memory(corpus.get('awo').turtle)
awo = ont.load_graph(corpus.get('awo').turtle)

vocab = store.select('''
  SELECT ?term ?label WHERE { ?term a owl:Class ; rdfs:label ?label }
  ORDER BY ?label''')
print(f'{len(vocab)} named classes')
for row in vocab[:8]:
    print('  ', row['label'], '  <-', row['term'].split('#')[-1])

# %% [markdown]
# Now an **axiom**. `Giraffe` is not merely a term under `Herbivore`; the ontology commits to what giraffes eat. In OWL that commitment is a restriction, which in RDF is a blank node — the reason ontologies are painful to read as raw triples and are normally viewed through a tool.

# %%
q = '''SELECT ?prop ?filler WHERE {
  awo:Giraffe rdfs:subClassOf ?r .
  ?r a owl:Restriction ; owl:onProperty ?prop ; ?kind ?filler .
  FILTER(?kind != rdf:type && ?kind != owl:onProperty)
}'''
for row in store.select(q):
    print('Giraffe SubClassOf', row['prop'].split('#')[-1],
          'only/some', row['filler'].split('#')[-1])

print('\nIn DL notation:  Giraffe ⊑ Herbivore ⊓ ∀eats.Leaf')

# %% [markdown]
# ## 2. The ontology spectrum, as a classifier
#
# The book places artefacts on a spectrum: **controlled vocabulary → taxonomy → thesaurus → formal ontology**. That is usually taught as a diagram to memorise. It is more useful as a *decision procedure*, because writing one forces you to state what actually separates the levels:
#
# | Level | Requires |
# |---|---|
# | controlled-vocabulary | named terms with labels |
# | taxonomy | + a subsumption hierarchy |
# | thesaurus | + associative / lexical relations (SKOS) |
# | formal-ontology | + axioms a reasoner can act on beyond subsumption |
#
# `classify_spectrum` implements exactly that, and — importantly — returns the **evidence** it used. A classifier that will not show its work cannot be argued with.

# %%
rows = []
for art in corpus.CORPUS:
    g = ont.load_graph(art.turtle)
    m = ont.graph_metrics(g)
    rows.append({
        'artefact': art.name,
        'level': ont.classify_spectrum(g)['level'],
        'classes': m['classes'],
        'subclass': m['subclass_axioms'],
        'skos': m['skos_relations'],
        'restrictions': m['restrictions'],
        'disjoint': m['disjointness_axioms'],
        'richness': m['axiom_richness'],
    })
df = pd.DataFrame(rows).sort_values('richness', ascending=False)
df

# %%
res = ont.classify_spectrum(ont.load_graph(corpus.get('food-thesaurus').turtle))
print('food-thesaurus ->', res['level'])
for e in res['evidence']:
    print('   because:', e)

# %% [markdown]
# ## 3. Why `axiom_richness` is the number worth watching
#
# `axiom_richness` = logical axioms per class. It is deliberately crude, and it separates the artefacts that *say something* from the ones that merely *name things*. Watch how it tracks the spectrum level — and note where it doesn't, which is the interesting part.

# %%
print(df[['artefact', 'level', 'richness']].to_string(index=False))
print('\nMean richness by level:')
print(df.groupby('level')['richness'].mean().sort_values().to_string())

# %% [markdown]
# > **Discussion.** `bare-properties` and `animals-taxonomy` are both taxonomies, but their richness differs — domain/range axioms count as logical commitments even when the properties are otherwise unconstrained. Is that the right call? Defend an answer; this is the kind of judgement an ontology engineer is paid for.

# %% [markdown]
# ### Exercise 1.1 — Order the corpus by formality
#
# Without using `classify_spectrum`, rank every artefact in the corpus by how *formal* it is, using only `graph_metrics`. Then compare your ranking with the spectrum labels and identify one artefact where a pure metric ranking disagrees with the categorical label.

# %% [markdown]
# > **Hint.** Reasoner-relevant axioms are restrictions, disjointness and property characteristics — subsumption alone only buys you a taxonomy.

# %% assignment
# Rank every artefact by how formal it is, using only ont.graph_metrics.
ranking = []    # TODO: artefact names, most formal first

# %% solution
ranking = [r['artefact'] for r in sorted(
    ({'artefact': a.name, **ont.graph_metrics(ont.load_graph(a.turtle))}
     for a in corpus.CORPUS),
    key=lambda r: (r['restrictions'] + r['disjointness_axioms']
                   + r['property_characteristics'], r['axiom_richness']),
    reverse=True)]
print('most formal first:', ranking)

levels = {a.name: a.gold_level for a in corpus.CORPUS}
assert ranking[0] == 'awo', 'the AWO carries the most reasoner-relevant axioms'
# The disagreement: a thesaurus outranks some taxonomies on SKOS relations,
# but SKOS relations are *not* reasoner-relevant, so richness ranks it lower.
print('food-thesaurus is labelled', levels['food-thesaurus'],
      'but ranks at position', ranking.index('food-thesaurus') + 1, 'of', len(ranking))

# %%
# Check for Exercise 1.1 -- tests the names your code defines.
with CHECK.check('1.1', points=1):
    names = [a.name for a in corpus.CORPUS]
    assert sorted(ranking) == sorted(names), "rank every artefact exactly once"
    assert ranking[0] == "awo", "the AWO carries the most reasoner-relevant axioms"
    assert ranking.index("animals-taxonomy") < ranking.index("colours-vocab"), \
        "a hierarchy is more formal than a flat list"

# %% [markdown]
# ### Exercise 1.2 — Promote a taxonomy to a formal ontology
#
# `animals-taxonomy` is classified as a taxonomy. Add the **smallest** set of axioms that makes `classify_spectrum` return `formal-ontology`, and explain what real-world claim you just committed to.

# %% assignment
animals = ont.load_graph(corpus.get("animals-taxonomy").turtle)
print("before:", ont.classify_spectrum(animals)["level"])
# TODO: add the smallest set of axioms to `animals` that makes it a formal ontology

# %% solution
from rdflib import OWL, URIRef
EX = 'http://example.org/oe/'
animals = ont.load_graph(corpus.get('animals-taxonomy').turtle)
print('before:', ont.classify_spectrum(animals)['level'])

# One disjointness axiom is enough: it is the cheapest reasoner-relevant commitment.
animals.add((URIRef(EX + 'Mammal'), OWL.disjointWith, URIRef(EX + 'Bird')))

after = ont.classify_spectrum(animals)
print('after: ', after['level'])
assert after['level'] == 'formal-ontology'
print('\nThe commitment: nothing can be both a mammal and a bird. That is a claim\n'
      'about the world which a reasoner will now enforce -- and which will make\n'
      'certain future data *inconsistent* rather than merely odd.')

# %%
# Check for Exercise 1.2 -- tests the names your code defines.
with CHECK.check('1.2', points=1):
    original = ont.load_graph(corpus.get("animals-taxonomy").turtle)
    assert ont.classify_spectrum(animals)["level"] == "formal-ontology"
    assert len(animals) - len(original) <= 2, "add the smallest set of axioms (one or two triples)"

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['1.1', '1.2'])

# %% solution
CHECK.assert_all_passed(['1.1', '1.2'])
