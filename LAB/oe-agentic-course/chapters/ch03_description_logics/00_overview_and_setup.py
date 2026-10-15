# %% [markdown]
# # Chapter 3 — Description Logics
# ### Notebook 0 · Overview and setup
#
# *Book reference: Keet, *Ontology Engineering* (2nd ed.), Ch. 3*
#
# Chapter 2 ended at a wall: first-order logic is undecidable, so no terminating procedure can be complete for it. Description logics are the engineering response — **fragments of FOL chosen so that reasoning terminates**. In this chapter you build the reasoner that makes that claim true.

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
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "agentlab").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch03_toolkit as dl
import pandas as pd
A = dl.Atomic
logging.getLogger("dspy").setLevel(logging.WARNING)

# %% [markdown]
# ## Notebooks in this chapter
#
# | # | Notebook | Book section | What you build |
# |---|---|---|---|
# | 0 | `00_overview_and_setup` | — | a working DL environment |
# | 1 | `01_dl_basics_and_tableau` | 3.1 | **an ALC tableau reasoner**, with blocking |
# | 2 | `02_important_dls` | 3.2 | a DL namer, and the measured cost of expressivity |
# | 3 | `03_reasoning_services` | 3.3 | satisfiability, subsumption, classification |
# | 4 | `04_exercises` | 3.4 | autograded answers |
# | 5 | `05_assignment` / `05_solutions` | — | problem set: a Claude reviewer for ontology change requests, a review agent that calls the tableau, a pipeline in which the reasoner disposes, and a contamination test (Pizza vs. SIP's fleet ontology) |

# %% [markdown]
# **By the end of this notebook you can:**
#
# 1. Read and write DL concept expressions, and say what each constructor costs you.
# 2. Run — and explain — a **tableau**: why `∃r.A ⊓ ∀r.¬A` is unsatisfiable, step by step.
# 3. Explain why **blocking** is what makes cyclic axioms terminate.
# 4. Name the DL a knowledge base actually needs, and predict the reasoning complexity you just signed up for.
# 5. Derive every reasoning service from concept satisfiability.
# 6. Build an agent that calls a sound reasoner instead of guessing — and tell whether a model is reasoning or remembering.

# %% [markdown]
# ## The engine
#
# `ch03_toolkit` is a self-contained DL implementation: concept AST, negation normal form, expressivity analysis, and a tableau reasoner for **ALC** with TBox internalisation and subset blocking. No external reasoner, no Java.
#
# > **Scope, stated up front.** The tableau decides ALC. Number restrictions, inverses and transitive roles are *analysed* by the DL namer but **not reasoned over** — implementing SHIQ is a research-grade exercise, not a notebook. Every place this matters, the notebooks say so.

# %% [markdown]
# ## The code this chapter adds
#
# The chapter's subject, the DL engine, is `ch03_toolkit.py` in this folder. The problem set's support (the change-request corpus with its certified labels, the review guidelines, the agent's tools, the Pizza contamination twins and SIP's fleet modules) is `ch03_agentic.py`.
#
# `agentlab` gains two modules, for the chapter's new agent-engineering layer: **tools and agents**. Chapters 1–2 built Claude *programs*: one prompt in, one structured answer out. An agent is a loop — the model chooses a tool, reads its result, and chooses again — so the course now needs a way to give Claude tools and a record of what it did with them.
#
# | module | what it is for |
# |---|---|
# | `agentlab.tools` | `instrument` (wrap a function so every call is logged, and errors come back as text the model can read), `ToolCallLog` (the trajectory: names, arguments, latency), `make_tools` (plain functions → LangChain tools) |
# | `agentlab.agents` | `chat_model` (Claude through LangChain), `build_agent` / `run_agent` (one tool-calling loop, one episode), `chat_usage` (what the episode cost), `message_text` |
#
# Everything from Chapters 1–2 is unchanged: the review scorer returns `ev.ScoreReport`, `llm.meter` prices every DSPy block, and GEPA still optimises the reviewer's instruction.

# %%
from agentlab import tools, agents
for row in agentlab.catalogue(up_to_chapter=3):
    new = "   <- new in Chapter 3" if row["chapter"] == 3 else ""
    print(f"ch{row['chapter']}  {row['module']:22} {row['lines']:4} lines  {row['purpose']}{new}")

# %% [markdown]
# A tool is an ordinary Python function. `instrument` is the whole difference between a function and a tool an agent can be audited on: it records the call, and turns an exception into a string the model can read and react to.

# %%
agentlab.show(tools.instrument)

# %% [markdown]
# The review agent's tools close over one module under review. You can call them yourself, with no model and no cost — which is how you should test any tool before handing it to an agent.

# %%
import ch03_agentic as AG
ws = AG.ReviewWorkspace("viaduct-critical")
review_tools = {t.name: t for t in AG.build_review_tools(ws)}
print(review_tools["dl_expressivity"].invoke({}))
print(review_tools["check_subsumption"].invoke({"sub": "Viaduct", "sup": "CriticalStructure"}))
print(review_tools["check_subsumption"].invoke({"sub": "Viaduct", "sup": "NoSuchClass"}))
print("trajectory:", ws.log.names())

# %% [markdown]
# `build_agent` hands those tools to Claude with a system prompt; `run_agent` runs one episode and keeps every message, because the transcript is the evidence. Both are short — read them before the problem set uses them.

# %%
agentlab.show(agents.build_agent)
agentlab.show(agents.run_agent)

# %% [markdown]
# ### Sanity check: the smallest interesting unsatisfiability

# %%
c = dl.And(dl.Exists('r', A('A')), dl.ForAll('r', dl.Not(A('A'))))
print('concept   :', dl.to_string(c))
result = dl.satisfiable(c)
print('verdict   :', result.summary())
assert not result.satisfiable
print('\nIt demands an r-successor that is an A, while insisting every\n'
      'r-successor is not an A. No model can satisfy both.')
