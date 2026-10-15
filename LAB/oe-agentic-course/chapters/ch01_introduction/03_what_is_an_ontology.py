# %% [markdown]
# # Chapter 1 — Introduction
# ### Notebook 3 · What *is* an ontology, and what makes one bad?
#
# *Book reference: Sections 1.3.1–1.3.3*
#
# The book plays 'the definition game' and then sorts ontologies into good, not-so-good and bad. We make both operational — and find that the definitions genuinely disagree about real files.

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
CHECK = Grader('Chapter 1 · Notebook 3 exercises')

# %% [markdown]
# ## 1. The definition game, played with a scorecard
#
# Section 1.3.1 lists competing definitions of *ontology*. Rather than choosing a favourite, encode each as a **testable predicate** over an artefact's metrics and apply all of them to the whole corpus. Where they disagree is where the field's arguments actually live.

# %%
for d in ch1.DEFINITIONS:
    print(f"{d['id']:22s} {d['gloss']}")
    print(f"{'':22s} operationalised as: {d['reads_as']}\n")

# %%
graphs = {a.name: ont.load_graph(a.turtle) for a in corpus.CORPUS}
scorecard = pd.DataFrame(ch1.definition_scorecard(graphs)).set_index('artefact')
scorecard

# %%
disputed = scorecard[scorecard.nunique(axis=1) > 1]
print('Artefacts the definitions DISAGREE about:\n')
print(disputed.to_string())
print('\nEach disputed row is a real argument: under Gruber it is an ontology,\n'
      'under Guarino it is not. Neither side is being careless.')

# %% [markdown]
# > **Exam-style question.** `colours-vocab` counts as an ontology under Gruber-1993 and under no other definition. Is Gruber's definition too weak, or are the others too strong? Your answer should say what *work* you need the definition to do — which is the only basis on which the question can be settled.

# %% [markdown]
# ## 2. Good, not-so-good and bad ontologies (§1.3.3)
#
# The book's quality discussion becomes a **defect scanner**. Each detector is syntactic and explainable: it names the term that triggered it, so a finding can always be checked by hand. That is a hard requirement — a quality tool nobody can audit will be ignored the first time it is wrong.

# %%
for s in ont.SMELLS:
    print(f'{s.id}\n    {s.title}\n    why it matters: {s.why}\n')

# %%
rows = []
for art in corpus.CORPUS:
    counts = ont.smell_summary(ont.load_graph(art.turtle))
    rows.append({'artefact': art.name, 'defects': sum(counts.values()), **counts})
pd.DataFrame(rows).fillna(0).set_index('artefact').astype(int)

# %% [markdown]
# ### Reading a finding
#
# Every finding carries the evidence that produced it.

# %%
for f in ont.scan_smells(ont.load_graph(corpus.get('legacy-import').turtle)):
    print(f'[{f.smell}]')
    print(f'  subject: {f.subject}')
    print(f'  detail : {f.detail}\n')

# %% [markdown]
# ### Where the scanner is deliberately conservative
#
# `staff-instance-confusion` has no sibling classes, so `no-disjointness` does **not** fire — there is nothing yet to be disjoint from. A detector that fired anyway would be technically defensible and practically useless, because engineers switch off tools that cry wolf. Precision is a design goal, not an accident.

# %%
g = ont.load_graph(corpus.get('staff-instance-confusion').turtle)
print('findings:', [f.smell for f in ont.scan_smells(g)])
print('gold labels:', sorted(corpus.get('staff-instance-confusion').gold_smells))

# %% [markdown]
# ### Exercise 3.1 — Write a new detector
#
# Add a detector for the **lonely child** defect: a class with exactly one direct subclass. It is a taxonomy smell — a partition into one part usually means either a missing sibling or a redundant level. Register it and run it over the corpus.

# %% [markdown]
# > **Hint.** Count direct `rdfs:subClassOf` children per parent; report parents with exactly one.

# %% assignment
from agentlab.ontology import Finding, Smell
def detect_lonely_child(g):
    # TODO: return a list of Finding("lonely-child", <parent IRI>, <detail>)
    return []

# %% solution
from collections import defaultdict
from rdflib import RDFS, URIRef
from agentlab.ontology import Finding, Smell

def detect_lonely_child(g):
    children = defaultdict(list)
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            children[o].append(s)
    return [
        Finding('lonely-child', str(parent),
                f'exactly one direct subclass ({str(kids[0]).split(chr(35))[-1]}); '
                'a one-part partition is usually a missing sibling or a redundant level')
        for parent, kids in sorted(children.items(), key=lambda kv: str(kv[0]))
        if len(kids) == 1
    ]

lonely = Smell('lonely-child', 'Class with a single subclass',
               'A partition into one part carries no information and often marks an '
               'unfinished model.', detect_lonely_child)

hits = {a.name: len(detect_lonely_child(ont.load_graph(a.turtle))) for a in corpus.CORPUS}
print({k: v for k, v in hits.items() if v})
assert hits['animals-taxonomy'] == 1, 'Bird has exactly one subclass (Penguin)'
print('\nRegistering it would change the gold labels, so verify_corpus() would now\n'
      'fail -- correctly. Adding a detector is a breaking change to a graded rubric.')

# %%
# Check for Exercise 3.1 -- tests the names your code defines.
with CHECK.check('3.1', points=1):
    counts = {a.name: len(detect_lonely_child(ont.load_graph(a.turtle))) for a in corpus.CORPUS}
    assert counts["animals-taxonomy"] == 1, "Bird has exactly one subclass (Penguin)"
    assert counts["colours-vocab"] == 0, "no hierarchy, no lonely child"
    found = detect_lonely_child(ont.load_graph(corpus.get("animals-taxonomy").turtle))
    assert found[0].smell == "lonely-child" and found[0].subject.endswith("Bird")

# %% [markdown]
# ### Exercise 3.2 — Repair a broken ontology
#
# Take `broken-cycle` and repair it so the scanner reports **no** defects, without deleting classes. State which real-world claim each repair encodes.

# %% assignment
g = ont.load_graph(corpus.get("broken-cycle").turtle)
print("before:", ont.smell_summary(g))
# TODO: repair g so the scanner reports no defects, without deleting classes

# %% solution
from rdflib import OWL, RDFS, URIRef
EX = 'http://example.org/oe/'
g = ont.load_graph(corpus.get('broken-cycle').turtle)
print('before:', ont.smell_summary(g))

# Repair 1: break the cycle. Vehicle is the general concept, Car the specific one,
# so the axiom 'Vehicle SubClassOf Car' is the wrong one and must go.
g.remove((URIRef(EX + 'Vehicle'), RDFS.subClassOf, URIRef(EX + 'Car')))

# Repair 2: commit to Car and Lorry being different kinds of thing.
g.add((URIRef(EX + 'Car'), OWL.disjointWith, URIRef(EX + 'Lorry')))

print('after: ', ont.smell_summary(g))
assert ont.smell_summary(g) == {}
print('level now:', ont.classify_spectrum(g)['level'])
print('\nRepair 1 asserts a direction of generality; repair 2 asserts that no\n'
      'single vehicle is both a car and a lorry. Both are claims about the world\n'
      'that a domain expert must sign off -- the tool can find the defect, but it\n'
      'cannot decide which axiom was the wrong one.')

# %%
# Check for Exercise 3.2 -- tests the names your code defines.
with CHECK.check('3.2', points=1):
    from rdflib import OWL, RDF
    before = ont.load_graph(corpus.get("broken-cycle").turtle)
    assert ont.smell_summary(g) == {}, ont.smell_summary(g)
    assert set(g.subjects(RDF.type, OWL.Class)) == set(before.subjects(RDF.type, OWL.Class)), \
        "do not delete or add classes"

# %% [markdown]
# ### Exercise checks
#
# Each exercise's check tests the names *your* code defines; a failing check is recorded, not raised, so the notebook runs to the end. The worked solutions are in the `_solutions` notebook next to this one.

# %%
_ = CHECK.summary(['3.1', '3.2'])

# %% solution
CHECK.assert_all_passed(['3.1', '3.2'])
