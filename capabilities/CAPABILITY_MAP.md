# Capability Map: what each module offers the Semantic Intelligence Platform

Everything in `capabilities/` is a **potential capability of the
[Semantic Intelligence Platform (SIP)](../sip/)**. Each entry is mapped to the SIP lifecycle
stage it serves, the SIP functional element that would host it, and how far it is
integrated today.

```
scope → acquire → model → validate → review ║ populate → reason → publish ║ consume
```

**Relation to SIP:**

| status | meaning |
|---|---|
| **absorbed** | SIP re-implements the design; the module stays as the reference or spike |
| **reused** | SIP code calls it, or SIP's architecture adopts it directly |
| **candidate** | built and working on its own, and not yet wired into SIP |
| **reference** | a design or model that SIP's architecture builds on, with no runtime link |

## By module

| capability | location | what it provides | SIP stage(s) | SIP element | status | next integration step |
|---|---|---|---|---|---|---|
| **Ontology Validation Agent** | [`ontology_agents/validation_agent`](ontology_agents/validation_agent/) | 131 checks in 16 families: reasoning, SHACL, custom checks; root causes, verified repairs, policy verdict. Each check is mapped to a SIP stage and a modelling-maturity level ([catalogue](ontology_agents/validation_agent/CHECK_CATALOGUE.md)) | validate (critic at acquire, model, populate) | QualityService; agent critics | candidate | Serve `quality.runChecks` from the OVA engine; use `SIP_STAGE_OF` as the critic set per agent and `MATURITY_OF` to select the policy |
| **Ontology Modeler** | [`ontology_modeler`](ontology_modeler/) | Fuseki client, upload, structure queries, graph diff, RDF→LPG projection, GraphRAG, Playground editing bridge | model, publish, consume | QuadStore, ChangeTracker, KgConstruction | **reused** (Fuseki client by duck typing in `core/store.py`; the bnode-closure diff technique) | Use `lpg/` and `graphrag/` behind the publish and consume stages; Playground as a lightweight edit surface |
| **Ontology Converter** | [`ontology_converter`](ontology_converter/) | Production RDF → labelled-property-graph ETL into FalkorDB, `owl:imports` closure, idempotent batched Cypher | publish, consume | KgConstruction (projection) | candidate (`kg/lifting.py` names it as the production projector) | Call it from a publish step to project the released graph into FalkorDB |
| **Ontology Enricher** | [`ontology_enricher`](ontology_enricher/) | HBIM ↔ FIBO mapping with SKOS, reasoning-pattern catalogue, inferred-closure write-back, Protégé-reproducible | model (alignment), reason | Alignment, ReasoningService | candidate | Import `catalog/reasoning_patterns.yaml` as reasoning recipes; route its mappings through the AlignmentAgent |
| **Bottom-up pipeline** | [`bottomup_ontology`](bottomup_ontology/) + [`bottomup_notebooks`](bottomup_notebooks/) | Keet Fig. 7.7 text→ontology pipeline as a networkx graph of steps, each one an agent tool | acquire | ExtractionAgent | reference | Expose the steps as ExtractionAgent tools ahead of the LLM call |
| **Grounded extraction** | [`langextract_ontology`](langextract_ontology/) | LangExtract with span-grounded quotes, so every axiom cites its sentence; Claude provider | acquire | ExtractionAgent, LlmGateway | **absorbed** (SIP's verbatim-quote critic and provenance requirement) | Fix its offline test (see below), then offer it as an extraction backend |
| **Ontology construction processes** | [`ontology_construction`](ontology_construction/) | NeOn, LOT and LLMs4OL processes plus construction metrics | scope, acquire, validate | LifecycleConductor, QualityService (metrics) | candidate | Use LOT/NeOn as stage plans in the conductor; add the metrics to `quality` |
| **Capability model** | [`ontology_engineering_capabilities`](ontology_engineering_capabilities/) | Ontology-engineering capabilities as a taxonomy and ontology, each mapped to an EKGF maturity pillar and level | all (requirements baseline) | — | reference | Trace SIP requirements to capabilities; align EKGF levels with the OVA M1–M5 ladder |
| **Ontology Builder design** | [`architecture/ontology_builder`](architecture/ontology_builder/) | 138 features from VocBench 3, WebProtégé and Protégé; governance foundation; CRUDV and reasoner spikes | model, validate, review | GovernanceRegistry, PolicyDecisionPoint, ReasoningService | **absorbed** (SIP implements its governance foundation; `spike_crudv` became `governance/capabilities.py`) | Keep for traceability; reconcile the remaining features in SIP §14 |
| **Ontology Assistant design** | [`architecture/ontology_assistant`](architecture/ontology_assistant/) | Read-only conversational agent over Fuseki + FalkorDB: tool catalogue, retrieval pipeline, evaluation | consume | AssistantAgent | **reused** (SIP adopts the read-only assistant design) | Implement the tool catalogue against SIP read operations |
| **Projection & GraphRAG models** | [`architecture/graphrag_agent`](architecture/graphrag_agent/) | SysML v2 models of the OWL→LPG projection, the FIBO projection system and the GraphRAG agent; the SysML subset reader | publish, consume | KgConstruction, AssistantAgent | reference (OVA's `build_docs.py` uses its `sysml_model.py`) | Fold the projection constraints into SIP's verification view |
| **Level-2 application architecture** | [`architecture/`](architecture/) (`ARCHITECTURE.md`) | ArchiMate application layer for the EKGF L2 platform: 10 components, 14 services | all | — | reference (predecessor platform view; the SIP AD is the current one) | Map its components to SIP functional elements |
| **Technical architecture** | [`architecture/technical architecture`](architecture/technical%20architecture/) | 39 vendor-neutral technology requirements and their FalkorDB / Fuseki / GCP mappings | deployment (all) | Deployment viewpoint | **reused** (referenced from SIP's deployment view) | Keep in step with `sip_deployment.sysml` |

## By SIP stage

| stage | SIP agent | capabilities that feed it |
|---|---|---|
| scope | RequirementsAgent | ontology_construction (NeOn/LOT requirements), capability model |
| acquire | ExtractionAgent | bottomup_ontology, langextract_ontology, ontology_construction (LLMs4OL) |
| model | ModelingCopilot, VocabularyAgent, AlignmentAgent | ontology_builder (features), ontology_modeler (Playground), ontology_enricher (mappings) |
| validate | QualityAgent | validation_agent, ontology_construction (metrics) |
| review | StewardAgent | validation_agent (EVO and human-adjudicated checks), ontology_builder (governance) |
| populate | KnowledgeGraphBuilder | validation_agent (ABOX and SHACL checks) |
| reason | classification | ontology_enricher (reasoning patterns), ontology_builder (`spike_reasoners`) |
| publish | — | ontology_converter, ontology_modeler (`lpg/`), graphrag_agent models |
| consume | AssistantAgent | ontology_assistant design, ontology_modeler (`graphrag/`) |

## Supporting assets outside `capabilities/`

| asset | location | role for SIP |
|---|---|---|
| Knowledge base | [`../LAB/oe-course`](../LAB/oe-course/README.md) | The course SIP is built from: theory, worked notebooks and agentic labs per chapter (see [`../LAB/README.md`](../LAB/README.md)) |
| Reference documents | [`../knowledge`](../knowledge/) | Keet's book, requirements report, converter and assistant specifications |
| FIBO corpus | [`../Ontology Repository`](../Ontology%20Repository/) | Large real-world test corpus (`sip/semantic_intelligence/tests/test_corpus_fibo.py`) |
| Infrastructure | [`../infra`](../infra/) | Docker Compose for Fuseki and FalkorDB |

## Running the capabilities

Packages that were at the repository root (`bottomup_ontology`, `langextract_ontology`,
`ontology_construction`, `ontology_engineering_capabilities`, `architecture`) import one
another, so run them with `capabilities/` as the working directory:

```bash
cd capabilities
python -m pytest ontology_construction/tests architecture/ontology_builder/spike_crudv architecture/ontology_builder/spike_reasoners -q
python architecture/build_architecture.py
cd ontology_agents   && python -m pytest validation_agent/tests -q
cd ontology_modeler  && python -m pytest ontology_modeler/playground/tests -q
```

**Known issues from before the restructure:**
* `python -m langextract_ontology.tests` fails to import `SimulatedOntologyModel` from
  `providers.py`.
* `ontology_modeler/playground/tests` has 2 setup errors.
