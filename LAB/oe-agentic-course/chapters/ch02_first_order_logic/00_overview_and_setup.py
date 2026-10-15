# %% [markdown]
# # Chapter 2 — First-Order Logic and Reasoning
# ### Notebook 0 · Overview and setup
#
# *Book reference: Keet, *Ontology Engineering* (2nd ed.), Ch. 2*
#
# Chapter 2 is the logical foundation the rest of the book stands on. Read passively it is a page of symbols. Here every piece of it is a running program: formulas are objects, models are data, and **M ⊨ φ** is a function call.

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

# %% [markdown]
# ## Notebooks in this chapter
#
# | # | Notebook | Book section | What you build |
# |---|---|---|---|
# | 0 | `00_overview_and_setup` | — | a working FOL engine |
# | 1 | `01_syntax_and_semantics` | 2.1 | a parser, and Tarskian satisfaction as code |
# | 2 | `02_reasoning` | 2.2 | entailment, countermodels, resolution proofs — and the decidability wall |
# | 3 | `03_exercises` | 2.3 | autograded answers |
# | 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude policy formaliser, graded *semantically*, optimised with GEPA |

# %% [markdown]
# **By the end of this notebook you can:**
#
# 1. Read and write FOL, and check your reading against a machine rather than against your intuition.
# 2. Construct a **countermodel** to show that two formalisations differ — the single most useful skill in this chapter.
# 3. Run a resolution refutation and read the resulting **proof**.
# 4. State precisely what finite model checking can and cannot decide.
# 5. Build a Claude program that formalises English, grade it by semantics rather than string matching, and improve it with GEPA.

# %% [markdown]
# ## The engine
#
# `ch02_toolkit` is ~400 lines of pure Python: a tokeniser, a recursive-descent parser, an evaluator, a finite-model enumerator, and a resolution prover. No external solver. You can read all of it, and you should — the point of this chapter is that none of this is magic.

# %%
f = fol.parse('forall x (Human(x) -> Mortal(x))')
print('AST      :', f)
print('rendered :', fol.to_string(f))
print('signature:', fol.predicates(f))

# %% [markdown]
# ## The code this chapter adds
#
# The chapter's subject, the FOL engine, is `ch02_toolkit.py` in this folder. The problem set's support (the policy corpus, the semantic comparison, the guidelines) is `ch02_agentic.py`.
#
# `agentlab` gains one module, for the chapter's new agent-engineering layer: **optimisation**. Chapter 1 could only measure a Claude program; Chapter 2 improves one.
#
# | module | what it is for |
# |---|---|
# | `agentlab.optimize` | `make_gepa_metric` (a Chapter 1 `ScoreReport` turned into the score-plus-feedback GEPA reads), `run_gepa`, `compare` (before/after with the instruction diff), `instruction_of` / `set_instruction` |
#
# Everything from Chapter 1 is unchanged: the scorer you write still returns `ev.ScoreReport`, `llm.meter` still prices every block, and `ev.evaluate_dataset` still runs the evaluations.

# %%
from agentlab import optimize as opt
for row in agentlab.catalogue(up_to_chapter=2):
    new = "   <- new in Chapter 2" if row["chapter"] == 2 else ""
    print(f"ch{row['chapter']}  {row['module']:22} {row['lines']:4} lines  {row['purpose']}{new}")

# %% [markdown]
# GEPA reads text, not numbers: the metric has to say *what* went wrong. `make_gepa_metric` is the whole adapter, and it is short.

# %%
agentlab.show(opt.make_gepa_metric)

# %% [markdown]
# `run_gepa` is a thin wrapper over `dspy.GEPA`; the parameters that matter are the budget (`max_metric_calls`, each a billed program run), the reflection LM (the model that rewrites the instruction), and the two datasets (learn from `trainset`, choose on `valset`).

# %%
agentlab.show(opt.run_gepa)

# %% [markdown]
# ### Sanity check: the oldest argument in logic

# %%
premises = [fol.parse('forall x (Human(x) -> Mortal(x))'),
            fol.parse('Human(Socrates)')]
conclusion = fol.parse('Mortal(Socrates)')
holds, countermodel = fol.entails(premises, conclusion, max_size=3)
print('entails:', holds, '| countermodel:', countermodel)
assert holds and countermodel is None
