> ## 📚 Looking for the course?
> This repository also hosts a **practice-first graduate course** built on Keet,
> *An Introduction to Ontology Engineering* (2nd ed.) — executable notebooks plus a
> per-chapter agentic lab (LangChain/LangGraph tools, MDP formulation, evaluation
> datasets and metrics, DSPy **GEPA** optimisation, self-improving agents).
>
> **Start here: [`oe-course/README.md`](oe-course/README.md)**. Shared framework:
> [`oe-course/oe_course/`](oe-course/oe_course). Part I is complete —
> [Ch. 1 Introduction](oe-course/chapters/ch01_introduction),
> [Ch. 2 First-Order Logic](oe-course/chapters/ch02_first_order_logic),
> [Ch. 3 Description Logics](oe-course/chapters/ch03_description_logics),
> [Ch. 4 Web Ontology Languages](oe-course/chapters/ch04_web_ontology_languages).
> Everything runs offline — no API key, no Docker. The material below (Chapter 7's
> bottom-up pipeline) is one of the course's components.

---

# Bottom-up Ontology Development Workflow

A small, dependency-light implementation of the **bottom-up (text-to-ontology)
workflow** from Keet, *Ontology Engineering* (2nd ed.), **Chapter 7 —
"Bottom-up Ontology Development"**, specifically the pipeline of **Figure 7.7**
("Overview of the component tasks in the pipeline from text to candidate
classes, object properties, and basic constraints for an ontology").

The workflow turns an **unstructured-text corpus** into an **ontology**
(classes, subclass axioms, object properties) through a sequence of steps.

```
Unstructured text
   → Text cleaning             (mandatory)   PoS tagging · parsing · lemmatisation
   → Pre-processing            (mandatory)   contrastive analysis · co-occurrence · C/NC-value
   → Term (concept) extraction (mandatory)   term composition · FCA · clustering · assoc. rules
   → Relation extraction       (mandatory)   syntactic analysis · subcat. frames · seed words
   → Axiom finding             (optional)    lexico-syntactic (Hearst) patterns · dep. analysis · ILP
   → Human-in-the-loop         (optional)    domain-expert verification / pruning
   → Evaluation                (mandatory)   gold-standard comparison · data-driven assessment
→ Ontology
```

## Design (how it maps to the task)

| Requirement | Where |
|---|---|
| Workflow steps defined as **classes** | `bottomup_ontology/steps.py` — `WorkflowStep` subclasses |
| Steps represented as **networkx nodes** | each `WorkflowStep` *instance* is a node (hashable by `step_id`) |
| Workflow defined as a **networkx graph** | `bottomup_ontology/workflow.py` — a `networkx.DiGraph` |
| Each step = invocation of **one function / method** | each step class binds a single `step_*` function, invoked via `WorkflowStep.run` |
| Functions reusable as **agentic function tools** | `bottomup_ontology/tools.py` — `tool_specs()` + `ToolRegistry` |
| Functions to **configure mandatory & optional steps** | `configure_workflow`, `build_minimal_workflow`, `build_default_workflow`, `add_optional_step`, `remove_optional_step` |
| **Jupyter notebooks** for testing functionality | `notebooks/*.ipynb` |

### Package layout

```
bottomup_ontology/
├─ __init__.py      # public API
├─ state.py         # WorkflowState (shared context) + Ontology artifact (to_turtle)
├─ techniques.py    # dependency-free implementations of the Fig. 7.7 techniques
├─ steps.py         # WorkflowStep base + 7 step classes + the 7 step functions
├─ workflow.py      # build/configure the DiGraph + topological executor
└─ tools.py         # JSON tool specs + ToolRegistry for agentic use
notebooks/
├─ 01_build_and_visualize_workflow.ipynb
├─ 02_run_pipeline_end_to_end.ipynb
├─ 03_configure_optional_steps.ipynb
├─ 04_steps_as_agentic_tools.ipynb
└─ _build_notebooks.py   # regenerates the four notebooks
```

## Install

```bash
pip install -r requirements.txt
```

Only **networkx** is required at runtime; matplotlib is used for the notebook
visualisation, and the `nbformat`/`jupyter` packages only to run/regenerate the
notebooks.

## Quickstart

```python
import bottomup_ontology as bo

corpus = [
    "A rugby player plays in a position. Siya Kolisi is a rugby player. A team has many players.",
    "A club has a coach. The coach trains the team. A player belongs to a club.",
    "Mammals such as lions and impalas live in the savanna. A lion eats impala.",
]

g = bo.build_default_workflow()                       # networkx DiGraph
state = bo.WorkflowState(documents=corpus)
state = bo.run_workflow(g, state)                     # topological execution

print(state.ontology.summary())
print(state.ontology.to_turtle())
```

### Configuring mandatory / optional steps

```python
bo.build_minimal_workflow()                           # mandatory steps only
bo.configure_workflow(include_axiom_finding=True,     # toggle the optional ones
                      include_human_in_the_loop=False)
g = bo.add_optional_step(g, "human_in_the_loop")      # returns a re-wired copy
g = bo.remove_optional_step(g, "axiom_finding")
```

### Using steps as agentic function tools

```python
from bottomup_ontology import ToolRegistry, tool_specs

specs = tool_specs()                                  # OpenAI/Anthropic-style JSON
reg = ToolRegistry(bo.WorkflowState(documents=corpus))
reg.invoke("step_text_cleaning")
reg.invoke("step_term_extraction", {"top_k": 8})
# ... the agent chooses the order; the registry keeps one shared ontology state
```

## The notebooks (functional tests)

1. **01 · Build & visualize** — builds the graph, lists the step-class nodes,
   edges, mandatory/optional split, and draws the pipeline.
2. **02 · Run end-to-end** — runs the full pipeline on a sample corpus and shows
   the resulting classes, subclass axioms, object properties, Turtle, and
   evaluation metrics.
3. **03 · Configure optional steps** — minimal vs. full pipelines, add/remove
   optional steps, per-step parameters, and the **human-in-the-loop** gate
   (which lifts class F1 from ~0.76 to ~0.82 by pruning noisy candidates).
4. **04 · Steps as agentic tools** — tool specs, a `ToolRegistry`, a simulated
   agent loop driving the pipeline, and a sketch of wiring into the Anthropic
   SDK tool-use loop.

Run them headless to validate:

```bash
cd notebooks
jupyter nbconvert --to notebook --execute --inplace 0*.ipynb
```

## Scope & limitations

The NLP techniques are **deliberately lightweight, rule-based stand-ins** (a
heuristic PoS tagger, crude lemmatiser, frequency/co-occurrence statistics,
Hearst patterns) so the whole pipeline runs anywhere with only the standard
library + networkx. They are faithful to the *structure* and *technique names*
of Figure 7.7, not production-grade extractors — swap in spaCy/NLTK, gensim,
WordNet/VerbNet, or an LLM behind the same step-function interfaces for real
work. The over-eager Hearst match that yields a spurious `live savanna` class is
left in on purpose: it is exactly the kind of noise the optional
human-in-the-loop step is there to remove.

# ontology-engineering
