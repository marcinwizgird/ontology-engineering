# %% [markdown]
# # Chapter 1 — Introduction
# ### Notebook 0 · Overview, setup and the course contract
#
# *Book reference: Keet, *Ontology Engineering* (2nd ed.), Ch. 1*
#
# This course rebuilds Keet's textbook as a **practice-first graduate course**. Every claim the book makes in prose, you will make in code: measure it, test it, and defend it against a grader.

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

# %% [markdown]
# ## How this chapter is organised
#
# | # | Notebook | Book section | What you produce |
# |---|---|---|---|
# | 0 | `00_overview_and_setup` | — | a working environment |
# | 1 | `01_what_an_ontology_looks_like` | 1.1 | a spectrum classifier and its evidence |
# | 2 | `02_why_ontologies_pay_off` | 1.2 | a measured integration result (recall 0 → 1) |
# | 3 | `03_what_is_an_ontology` | 1.3 | a defect scanner and a definition scorecard |
# | 4 | `04_exercises` | 1.5 | autograded answers to the book's exercises |
# | 5 | `05_assignment` / `05_solutions` | — | problem set: a Claude triage program for an ontology registry — the policy as code, a diagnostic scorer, a DSPy program, and an honest evaluation |

# %% [markdown]
# **By the end of this notebook you can:**
#
# 1. Distinguish an ontology from a vocabulary, a taxonomy and a thesaurus **by measurement**, not by assertion.
# 2. Demonstrate the value of an ontology by showing a query whose answer is wrong without one.
# 3. Argue about competing definitions of *ontology* by applying them to real artefacts and finding where they disagree.
# 4. Detect and explain common modelling defects automatically.
# 5. Build and evaluate a Claude program that performs this triage, and say honestly how good it is.

# %% [markdown]
# ## Tooling
#
# | Tool | Role |
# |---|---|
# | **rdflib** | RDF graphs, Turtle, SPARQL |
# | **owlrl** | pure-Python OWL 2 RL reasoner — entailment with no Java |
# | **DSPy** | Claude programs as typed signatures and modules (this chapter's problem set); GEPA optimisation from Chapter 2 |
#
# Later chapters add their own tools when they first need them: LangChain tool-calling agents (Chapter 3), and Apache Jena Fuseki as a live triplestore (Chapter 8).
#
# ### Running against Claude
# The chapter notebooks run locally with no key. Each chapter's **problem set** calls the live Anthropic API: put `ANTHROPIC_API_KEY` in your shell or in `LAB/oe-agentic-course/.env` (copy `.env.example`). Every model call is billed, and every problem set states its estimated budget and asks you to report a cost next to every score.

# %%
sys.path.insert(0, str(Path.cwd()))          # so ch01_toolkit imports
import ch01_toolkit as ch1
from agentlab import ontology as ont
import corpus
import pandas as pd
pd.set_option("display.width", 120)

# %% [markdown]
# ## The code this chapter adds
#
# The course's code lives in one package, `agentlab`, which grows chapter by chapter. Chapter 1 adds five modules. Every later notebook uses them, so read them here once; nothing below is hidden from you.
#
# | module | used in | what it is for |
# |---|---|---|
# | `agentlab.ontology` | Notebooks 1–4, problem set | `graph_metrics`, `classify_spectrum`, and the defect scanner (`scan_smells`, `SMELLS`) |
# | `agentlab.sparql` | Notebook 1, problem set | `SparqlStore`: SPARQL over an in-memory graph, results as plain dicts |
# | `agentlab.llm` | problem set | Claude for DSPy (`configure_dspy`), and `meter` for the cost of every block of work |
# | `agentlab.evaluation` | problem set | `RuleBook`, `ScoreReport`, `set_f1`, `evaluate_dataset` |
# | `agentlab.grading` | problem set | the `GRADER.check(...)` marking cells |
#
# The chapter's own material stays in this folder: `corpus.py` (the labelled artefacts), `ch01_toolkit.py` (the two hospitals and the definition game) and `ch01_agentic.py` (the problem set's registry). `agentlab.show(obj)` prints the source of anything you are unsure about.

# %%
for row in agentlab.catalogue(up_to_chapter=1):
    print(f"ch{row['chapter']}  {row['module']:22} {row['lines']:4} lines  {row['purpose']}")

# %% [markdown]
# The spectrum classifier is the decision procedure Notebook 1 argues about. Read it before you use it: the whole rule is four `if` statements.

# %%
agentlab.show(ont.classify_spectrum)

# %% [markdown]
# Every defect is one small detector function registered in `ont.SMELLS`; this is the whole scanner loop.

# %%
agentlab.show(ont.scan_smells)

# %% [markdown]
# ### Self-test: does the labelled corpus still agree with the detectors?
#
# The course ships eleven small ontologies with **hand-written** gold labels. `verify_corpus()` checks the detectors against those labels. It must print nothing — if it complains, either a detector or a label is wrong, and the exercises downstream are measuring the wrong thing.

# %%
problems = corpus.verify_corpus()
print(problems or 'corpus OK: detectors agree with all hand-written labels')
print(f'{len(corpus.CORPUS)} artefacts:', ', '.join(sorted(corpus.BY_NAME)))

# %% [markdown]
# ### Sanity check: load the African Wildlife Ontology and measure it

# %%
awo = ont.load_graph(corpus.get('awo').turtle)
m = ont.graph_metrics(awo)
print(f"{m['triples']} triples, {m['classes']} classes, "
      f"{m['logical_axioms']} logical axioms, richness {m['axiom_richness']}")
assert m['classes'] > 10 and m['restrictions'] > 0
