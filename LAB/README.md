# LAB: the knowledge base behind the Semantic Intelligence Platform

`LAB/` holds learning and experimentation material. It is not part of the product, but
the [Semantic Intelligence Platform](../sip/) is constructed from it: the theory that
defines what each SIP stage must do, executable engines that prototype a check or a
reasoner, and problem sets that become evaluation datasets.

| item | what it is |
|---|---|
| [`oe-course/`](oe-course/README.md) | A practice-first graduate course on Keet, *An Introduction to Ontology Engineering* (2nd ed.): executable chapter notebooks, an engine per chapter, and an agentic problem set per chapter (LangChain/LangGraph, MDP formulation, DSPy GEPA). Runs offline. |
| `oe-course.zip` | Archived snapshot of the course. |

Source texts (Keet's book, requirements reports, specifications) are in
[`../knowledge/`](../knowledge/).

## How the course feeds SIP

Each chapter is mapped to the SIP lifecycle stage it informs and to the SIP functional
element or [capability](../capabilities/CAPABILITY_MAP.md) that implements it.

```
scope → acquire → model → validate → review ║ populate → reason → publish ║ consume
```

| chapter | engine / problem set | SIP stage | SIP element or capability |
|---|---|---|---|
| 1. Introduction | ontology-registry submission triage | validate, review | QualityService; the Ontology Validation Agent started from this problem set |
| 2. First-order logic | FOL model checker, resolution prover; formalising an access policy | reason | ReasoningService (semantics); PolicyDecisionPoint (policies as logic) |
| 3. Description logics | ALC tableau reasoner; reviewing rail-ontology change requests | reason, review | ReasoningService (justifications); the EVO checks of the validation agent |
| 4. Web Ontology Languages | OWL 2 profile checking; axiomatising inside OWL 2 profiles | model, reason | OwlAuthoring, ReasoningService; maturity levels M1–M5 of the validation agent |
| 5. Methods and methodologies | OntoClean checker; automated first-pass design review | scope, validate | LifecycleConductor; QualityService; `ontology_construction` |
| 6. Top-down development | part-whole taxonomy and chaining checker; untangling `partOf` | model | OwlAuthoring (foundational-ontology alignment) |
| 7. Bottom-up development | Fig. 7.7 pipeline (in `capabilities/`) | acquire | ExtractionAgent; `bottomup_ontology`, `langextract_ontology` |
| 8. Linking ontologies to data | mappings, materialisation, query rewriting; serving clinical data | populate, consume | KgConstruction; AssistantAgent; `ontology_converter` |
| 9. Natural languages | verbalisation, multilingual review sheets | model, review | VocabularyAgent; StewardAgent summaries |
| 10. Rough, temporal, fuzzy | choosing and pricing a formalism | scope | Out of scope for SIP v0.1; input to future extensions |

## Running the course

```bash
cd LAB/oe-course
pip install -r requirements.txt
jupyter lab chapters/
```

The course is self-contained: it imports only its own `oe_course` package, so moving it
here did not change how it runs.
