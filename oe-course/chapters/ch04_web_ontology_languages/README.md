# Chapter 4 — The Web Ontology Languages (interactive notebooks)

An interactive, **Python-based** rewrite of Chapter 4 of Keet, *Ontology
Engineering* (2nd ed.). Every **example, code snippet and table** in the chapter
is reproduced as a runnable Python artefact, and the **exercises are
reformulated as Python tasks** with runnable solution keys.

## Why Python (and not Protégé/Java)

The book uses Protégé + HermiT/Pellet, which need Java. To make everything run
anywhere, the notebooks use:

| Tool | Role |
|---|---|
| **owlready2** | Pythonic OWL — classes, properties, restrictions, RDF/XML serialisation (no Java needed to *build* or *save*). |
| **rdflib** | RDF graphs, serialisations (Turtle, RDF/XML…), SPARQL. |
| **owlrl** | Pure-Python **OWL 2 RL / RDFS** reasoner — so "run the reasoner" works without Java. |

> Full DL classification (consistency, subsumption proofs) still needs a DL
> reasoner (HermiT) + Java. Where that matters, the notebooks say so explicitly;
> the OWL 2 RL reasoner covers subclass/property propagation and entailment.

## Notebooks

| # | Notebook | Book section | Highlights |
|---|----------|--------------|-----------|
| 0 | `00_overview_and_setup.ipynb` | — | Learning outcomes, tooling, sanity check (build AWO + reason) |
| 1 | `01_standardising_and_owl1.ipynb` | 4.1 | 7-step language design (Fig 4.1); OWL 1 species; **Tables 4.1/4.2** built for real; **Example 4.1 African Wildlife Ontology** + Listing 4.1 (RDF/XML) |
| 2 | `02_owl2_features_profiles_syntaxes.ipynb` | 4.2 | SROIQ features (qualified cardinality, Self, irreflexive/asymmetric, property chains); **Example 4.2 cakes & the simple-property rule**; profiles EL/QL/RL + a heuristic OWL Classifier; **Listings 4.2–4.7** (one axiom, every syntax); **Table 4.3** complexity |
| 3 | `03_owl_in_context.ipynb` | 4.3 | Semantic Web **layer cake (Fig 4.4)**; SPARQL over the ontology; reason-then-query; Common Logic; **DOL** |
| 4 | `04_exercises.ipynb` | 4.4 | All 10 review questions + 14 exercises as Python (property chains, vegan⊑vegetarian, Joint/Single Honours, =2-modules consistency, principal vs knock-on errors, penguins & Lepidoptera, mini-project scaffold) |
| 5 | `05_assignment.ipynb` / `05_solutions.ipynb` | extends 4.2 | **Problem set** (100 pts, live Claude API): the Mopane Ridge Conservancy's monitoring ontology, deployed as EL / QL / RL modules. Requirement → OWL axiom *inside the module's profile*, with **escalation** when the profile cannot express it; why a faithfulness/profile split metric rewards silent substitution; the simple-property global restriction (Example 4.2); a staged scorer, a DSPy axiomatiser, GEPA reported on a held-out split with cost and noise; a module-building agent whose actions change the artefact; and a **construction MDP** with an entailment-based reward, used to design the reward for escalation |

`ch4_toolkit.py` is the shared module holding every artefact (the notebooks
import it). `ch4_agentic.py` is the problem set's provided code: the signature
and axiom language, its compiler to OWL 2 triples, the profile table and an
RDF-level profile checker, the requirements corpus (24 items, fixed 8/8/8
split, gold validated with rdflib/owlrl/owlready2), OWL 2 RL entailment probes,
the module workspace and agent tools, and the construction MDP. The scorer, the
DSPy program and the agent are for the student to build.
`artifacts/` holds generated files (e.g. the layer-cake PNG, and any `.owl` you
save).

This chapter is part of the wider [course](../README.md); the problem set
builds on the shared framework in [`oe_course/`](../../oe_course) and assumes
Chapter 1's (tools, metrics, MDPs, GEPA).

## Run

```bash
pip install owlready2 rdflib owlrl pandas matplotlib nbformat jupyter
python _build_notebooks.py     # (re)generate notebooks 0-4
python _build_assignment.py    # (re)generate 05_assignment + 05_solutions
jupyter nbconvert --to notebook --execute --inplace 0[0-4]*.ipynb   # run / validate
# or just open them:  jupyter lab
```

Notebooks 0–4 execute end-to-end offline. The problem set calls the live
Anthropic API (set `ANTHROPIC_API_KEY`, or `oe-course/.env`); only
`05_solutions.ipynb` is expected to run clean — the assignment stops at its first
`TODO` by design.

## Mapping: book artefact → Python artefact

| Book | Python (`ch4_toolkit`) |
|---|---|
| Fig 4.1 language design | `LANGUAGE_DESIGN_PROCESS`, `OWL_DESIGN_GOALS` |
| OWL 1 species (SHIF/SHOIN) | `OWL1_SPECIES` |
| Table 4.1 / 4.2 | `table_4_1_constructs()`, `table_4_2_axioms()`, `build_construct_demo()` |
| Example 4.1 AWO + Listing 4.1 | `build_awo()`, `awo_giraffe_owl_snippet()` |
| OWL 2 features | `build_owl2_features()`, `OWL2_NEW_FEATURES`, `SIMPLE_ONLY_FEATURES` |
| Example 4.2 cakes/allergies | `cakes_allergies_demo()` |
| Profiles EL/QL/RL + classifier | `OWL2_PROFILES`, `classify_profile()` |
| Listings 4.2–4.7 (syntaxes) | `firstyearcourse_ontology()`, `render_syntaxes()` |
| Table 4.3 / 4.4 | `complexity_table_4_3()`, `feature_table_4_4()` |
| Fig 4.4 layer cake | `draw_semantic_web_layercake()` |
| Common Logic / DOL | `COMMON_LOGIC`, `DOL` |
| Reasoning, DL renderer | `reason_owlrl()`, `dl_render()` |

## Scope note

Faithful to the chapter's structure and content. The OWL 2 RL reasoner is sound
but does not perform full DL classification; for that, configure
`owlready2.sync_reasoner()` against a local Java + HermiT.
