# Ontology Engineering Requirements — Capability Model

Comprehensive requirements for an **ontology-engineering practice**, expressed as **business** and **technology capabilities**, arranged as a **taxonomy** and an **ontology**, and mapped to the **EKGF Enterprise Knowledge Graph Maturity Model (EKG/MM v1.0)**.

**Totals:** 44 capabilities across 10 categories and 2 domains.

## EKGF maturity levels

| Level | Name | Meaning (EKG/MM) |
|---|---|---|
| L1 | EKG Initiation | Just starting / piloting an Enterprise Knowledge Graph. |
| L2 | Extensible Platform | EKG implemented; building out capabilities and integrations. |
| L3 | Enterprise Ready | EKG fully implemented with org-wide processes and infrastructure. |
| L4 | Strategic Asset | EKG used as a key strategic asset driving innovation and decisions. |
| L5 | Operational Ecosystem | EKG fully integrated into operations as part of the wider ecosystem. |

## Requirements by domain → category

### Business capabilities

#### BSG · Ontology Strategy & Governance

*Direction-setting, policy, funding and oversight of the ontology practice.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| B.SG.1 | **Ontology Vision & Strategy** | The practice shall maintain an explicit ontology vision and strategy aligned to business goals. | Business | L1 EKG Initiation | — |
| B.SG.2 | **Ontology Governance & Stewardship** | The practice shall establish governance bodies and assign stewards for every ontology asset. | Data | L3 Enterprise Ready | B.SG.1 |
| B.SG.3 | **Policy, Standards & Conventions Management** | The practice shall publish and enforce ontology modelling standards and naming conventions. | Data | L3 Enterprise Ready | B.SG.2 |
| B.SG.4 | **Funding & Investment Management** | The practice shall secure sustained funding tied to the ontology roadmap and value case. | Organization | L2 Extensible Platform | B.SG.1 |
| B.SG.5 | **Ontology Risk & Compliance Management** | The practice shall identify and mitigate risks arising from ontology content and its use. | Data | L4 Strategic Asset | B.SG.2, B.SG.3 |

#### BSE · Stakeholder & Domain Engagement

*Capturing intent and knowledge from domain experts and consumers.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| B.SE.1 | **Domain Knowledge Elicitation** | The practice shall systematically elicit and record domain knowledge from subject-matter experts. | Business | L1 EKG Initiation | B.SG.1 |
| B.SE.2 | **Competency Question Management** | The practice shall define and maintain competency questions that scope and validate the ontology. | Business | L1 EKG Initiation | B.SE.1 |
| B.SE.3 | **Use-Case & Requirements Management** | The practice shall manage prioritised, traceable ontology requirements linked to use cases. | Organization | L1 EKG Initiation | B.SE.2 |
| B.SE.4 | **Business Glossary & Terminology Management** | The practice shall maintain an authoritative business glossary reconciled with the ontology. | Data | L2 Extensible Platform | B.SE.1 |

#### BVP · Value & Performance Management

*Justifying, measuring and driving adoption of the ontology.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| B.VP.1 | **Value Case & Benefits Realization** | The practice shall quantify and track the realised business value of ontology investments. | Business | L4 Strategic Asset | B.SG.4, B.SE.3 |
| B.VP.2 | **Performance Measurement (KPIs)** | The practice shall measure ontology performance against defined KPIs and report them. | Business | L4 Strategic Asset | B.VP.1 |
| B.VP.3 | **Adoption & Change Management** | The practice shall actively manage adoption and change for ontology-based ways of working. | Organization | L3 Enterprise Ready | B.SE.3 |

#### BCT · Capability & Talent Development

*People, skills and ecosystem collaboration that sustain the practice.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| B.CT.1 | **Skills & Talent Management** | The practice shall build and retain the ontology-engineering skills needed by the roadmap. | Organization | L2 Extensible Platform | B.SG.1 |
| B.CT.2 | **Knowledge Sharing & Community of Practice** | The practice shall operate a community of practice that shares ontology assets and lessons. | Organization | L3 Enterprise Ready | B.CT.1 |
| B.CT.3 | **Ecosystem & Standards Collaboration** | The practice shall collaborate with external standards ecosystems and adopt shared vocabularies. | Organization | L5 Operational Ecosystem | B.CT.2 |

### Technology capabilities

#### TDA · Ontology Development & Authoring

*Conceptualising and formalising ontologies and vocabularies.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.DA.1 | **Ontology Conceptualization & Modelling** | The capability shall produce a conceptual model satisfying the competency questions. | Data | L1 EKG Initiation | B.SE.2 |
| T.DA.2 | **Ontology Formalization (OWL/RDFS/SKOS)** | The capability shall formalise the conceptual model in a standard ontology language. | Data | L2 Extensible Platform | T.DA.1 |
| T.DA.3 | **Foundational / Top-down Ontology Reuse** | The capability shall reuse foundational ontologies where they improve interoperability. | Data | L2 Extensible Platform | T.DA.1 |
| T.DA.4 | **Bottom-up Ontology Learning** | The capability shall extract candidate ontology content from existing data and text sources. | Data | L3 Enterprise Ready | T.DA.1, T.IA.3 |
| T.DA.5 | **Ontology Design Pattern (ODP) Management** | The capability shall maintain and apply a catalogue of ontology design patterns. | Data | L3 Enterprise Ready | T.DA.2 |
| T.DA.6 | **Vocabulary & Controlled-Term Management** | The capability shall manage controlled vocabularies and thesauri reconciled with the ontology. | Data | L2 Extensible Platform | B.SE.4 |

#### TIA · Ontology Integration & Alignment

*Connecting ontologies and data into a coherent semantic layer.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.IA.1 | **Ontology Mapping & Alignment** | The capability shall create and maintain mappings that align internal and external ontologies. | Data | L3 Enterprise Ready | T.DA.2 |
| T.IA.2 | **Modularization & Import Management** | The capability shall organise ontologies into versioned, importable modules. | Data | L3 Enterprise Ready | T.DA.2 |
| T.IA.3 | **Semantic Data Integration** | The capability shall integrate heterogeneous source data through the ontology. | Technology | L3 Enterprise Ready | T.DA.2, T.IA.1 |
| T.IA.4 | **Identity Resolution & Entity Reconciliation** | The capability shall reconcile co-referent entities to stable identifiers. | Technology | L3 Enterprise Ready | T.IA.3 |

#### TRI · Reasoning & Inference

*Deriving and explaining new knowledge from the ontology.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.RI.1 | **Logical Consistency & Reasoning** | The capability shall verify logical consistency and classify the ontology with a reasoner. | Technology | L2 Extensible Platform | T.DA.2 |
| T.RI.2 | **Inferencing & Materialization** | The capability shall compute entailments and make inferred knowledge available to consumers. | Technology | L3 Enterprise Ready | T.RI.1, T.IA.3 |
| T.RI.3 | **Rule & Constraint Management (SHACL/SWRL)** | The capability shall manage and execute rules that augment the ontology with domain logic. | Technology | L3 Enterprise Ready | T.DA.2 |
| T.RI.4 | **Inference Explainability** | The capability shall provide human-readable justifications for inferred results. | Technology | L4 Strategic Asset | T.RI.2 |

#### TQV · Quality, Validation & Verification

*Ensuring the ontology is correct, consistent and fit for purpose.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.QV.1 | **Ontology Validation (SHACL/constraints)** | The capability shall validate ontology and data against declared constraints. | Data | L2 Extensible Platform | T.DA.2, T.RI.3 |
| T.QV.2 | **Ontology Testing (Competency-Question tests)** | The capability shall test the ontology against its competency questions on every change. | Data | L2 Extensible Platform | B.SE.2, T.DA.2 |
| T.QV.3 | **Quality Assurance & Metrics** | The capability shall measure ontology quality (coverage, cohesion, conciseness) continuously. | Data | L3 Enterprise Ready | T.QV.1 |
| T.QV.4 | **Verification & Evaluation (gold standard)** | The capability shall evaluate the ontology against gold standards and application use cases. | Data | L3 Enterprise Ready | T.QV.2, T.QV.3 |

#### TOO · Ontology Operations (OntoOps)

*Storing, versioning, releasing and operating ontologies at scale.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.OO.1 | **Triplestore & Ontology Storage** | The capability shall store ontologies and instance data in a managed, backed-up triplestore. | Technology | L2 Extensible Platform | T.DA.2 |
| T.OO.2 | **Versioning & Release Management** | The capability shall version, release and deprecate ontologies under change control. | Data | L2 Extensible Platform | T.OO.1 |
| T.OO.3 | **Ontology CI/CD (OntoOps / DataOps)** | The capability shall automate build, test and deployment of ontology releases. | Technology | L4 Strategic Asset | T.OO.2, T.QV.2, T.QV.1 |
| T.OO.4 | **Federation & Virtualization** | The capability shall enable federated, virtualised access across distributed knowledge graphs. | Technology | L5 Operational Ecosystem | T.IA.3, T.OO.1 |
| T.OO.5 | **Observability & Monitoring** | The capability shall monitor the health, performance and drift of ontology services. | Technology | L4 Strategic Asset | T.OO.1 |

#### TAC · Access, Consumption & Visualization

*Publishing, querying, exploring and exploiting the ontology.*

| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |
|----|------------|-------------|-------------|--------------|------------|
| T.AC.1 | **Search & Query (SPARQL)** | The capability shall provide standards-based query access (SPARQL) to the knowledge graph. | Technology | L2 Extensible Platform | T.OO.1 |
| T.AC.2 | **Visualization & Exploration** | The capability shall offer visual exploration of ontology structure and content. | Technology | L2 Extensible Platform | T.AC.1 |
| T.AC.3 | **Documentation & Publishing** | The capability shall publish up-to-date, human-readable documentation for every ontology. | Technology | L2 Extensible Platform | T.DA.2 |
| T.AC.4 | **Ontology-based Access, APIs & Entitlements** | The capability shall expose governed, entitlement-aware access to ontology-based data services. | Technology | L3 Enterprise Ready | T.AC.1, T.IA.3 |
| T.AC.5 | **Multilingual & Localization Support** | The capability shall support multilingual labels and locale-aware consumption of the ontology. | Technology | L4 Strategic Asset | T.DA.6 |
| T.AC.6 | **LLM / AI Augmentation** | The capability shall use the ontology to ground AI/LLM services and accelerate authoring. | Technology | L5 Operational Ecosystem | T.RI.2, T.AC.1 |

## Maturity roadmap (capabilities grouped by target EKGF level)

- **L1 EKG Initiation** (5): B.SG.1 Ontology Vision & Strategy, B.SE.1 Domain Knowledge Elicitation, B.SE.2 Competency Question Management, B.SE.3 Use-Case & Requirements Management, T.DA.1 Ontology Conceptualization & Modelling
- **L2 Extensible Platform** (14): B.SG.4 Funding & Investment Management, B.SE.4 Business Glossary & Terminology Management, B.CT.1 Skills & Talent Management, T.DA.2 Ontology Formalization (OWL/RDFS/SKOS), T.DA.3 Foundational / Top-down Ontology Reuse, T.DA.6 Vocabulary & Controlled-Term Management, T.RI.1 Logical Consistency & Reasoning, T.QV.1 Ontology Validation (SHACL/constraints), T.QV.2 Ontology Testing (Competency-Question tests), T.OO.1 Triplestore & Ontology Storage, T.OO.2 Versioning & Release Management, T.AC.1 Search & Query (SPARQL), T.AC.2 Visualization & Exploration, T.AC.3 Documentation & Publishing
- **L3 Enterprise Ready** (15): B.SG.2 Ontology Governance & Stewardship, B.SG.3 Policy, Standards & Conventions Management, B.VP.3 Adoption & Change Management, B.CT.2 Knowledge Sharing & Community of Practice, T.DA.4 Bottom-up Ontology Learning, T.DA.5 Ontology Design Pattern (ODP) Management, T.IA.1 Ontology Mapping & Alignment, T.IA.2 Modularization & Import Management, T.IA.3 Semantic Data Integration, T.IA.4 Identity Resolution & Entity Reconciliation, T.RI.2 Inferencing & Materialization, T.RI.3 Rule & Constraint Management (SHACL/SWRL), T.QV.3 Quality Assurance & Metrics, T.QV.4 Verification & Evaluation (gold standard), T.AC.4 Ontology-based Access, APIs & Entitlements
- **L4 Strategic Asset** (7): B.SG.5 Ontology Risk & Compliance Management, B.VP.1 Value Case & Benefits Realization, B.VP.2 Performance Measurement (KPIs), T.RI.4 Inference Explainability, T.OO.3 Ontology CI/CD (OntoOps / DataOps), T.OO.5 Observability & Monitoring, T.AC.5 Multilingual & Localization Support
- **L5 Operational Ecosystem** (3): B.CT.3 Ecosystem & Standards Collaboration, T.OO.4 Federation & Virtualization, T.AC.6 LLM / AI Augmentation

## Ontology relations

Beyond the broader/narrower taxonomy, capabilities are linked by typed relations:

- `dependsOn` — a capability requires another to be effective (transitive).
- `enables` — inverse of `dependsOn`.
- `supports` — a technology capability supports a business capability/outcome.
- `governedBy` — a capability is governed by a governance capability.

| Capability | dependsOn | supports | governedBy |
|---|---|---|---|
| B.SG.2 Ontology Governance & Stewardship | B.SG.1 | — | — |
| B.SG.3 Policy, Standards & Conventions Management | B.SG.2 | — | — |
| B.SG.4 Funding & Investment Management | B.SG.1 | — | — |
| B.SG.5 Ontology Risk & Compliance Management | B.SG.2, B.SG.3 | — | — |
| B.SE.1 Domain Knowledge Elicitation | B.SG.1 | — | — |
| B.SE.2 Competency Question Management | B.SE.1 | — | — |
| B.SE.3 Use-Case & Requirements Management | B.SE.2 | — | — |
| B.SE.4 Business Glossary & Terminology Management | B.SE.1 | — | — |
| B.VP.1 Value Case & Benefits Realization | B.SG.4, B.SE.3 | — | — |
| B.VP.2 Performance Measurement (KPIs) | B.VP.1 | — | — |
| B.VP.3 Adoption & Change Management | B.SE.3 | — | — |
| B.CT.1 Skills & Talent Management | B.SG.1 | — | — |
| B.CT.2 Knowledge Sharing & Community of Practice | B.CT.1 | — | — |
| B.CT.3 Ecosystem & Standards Collaboration | B.CT.2 | — | — |
| T.DA.1 Ontology Conceptualization & Modelling | B.SE.2 | B.SE.2 | B.SG.3 |
| T.DA.2 Ontology Formalization (OWL/RDFS/SKOS) | T.DA.1 | — | B.SG.3 |
| T.DA.3 Foundational / Top-down Ontology Reuse | T.DA.1 | — | B.SG.3 |
| T.DA.4 Bottom-up Ontology Learning | T.DA.1, T.IA.3 | B.SE.1 | B.SG.3 |
| T.DA.5 Ontology Design Pattern (ODP) Management | T.DA.2 | — | B.SG.3 |
| T.DA.6 Vocabulary & Controlled-Term Management | B.SE.4 | B.SE.4 | B.SG.3 |
| T.IA.1 Ontology Mapping & Alignment | T.DA.2 | — | B.SG.2 |
| T.IA.2 Modularization & Import Management | T.DA.2 | — | — |
| T.IA.3 Semantic Data Integration | T.DA.2, T.IA.1 | B.VP.1 | — |
| T.IA.4 Identity Resolution & Entity Reconciliation | T.IA.3 | — | — |
| T.RI.1 Logical Consistency & Reasoning | T.DA.2 | — | — |
| T.RI.2 Inferencing & Materialization | T.RI.1, T.IA.3 | B.VP.1 | — |
| T.RI.3 Rule & Constraint Management (SHACL/SWRL) | T.DA.2 | — | — |
| T.RI.4 Inference Explainability | T.RI.2 | B.SG.5 | — |
| T.QV.1 Ontology Validation (SHACL/constraints) | T.DA.2, T.RI.3 | — | B.SG.3 |
| T.QV.2 Ontology Testing (Competency-Question tests) | B.SE.2, T.DA.2 | B.SE.2 | — |
| T.QV.3 Quality Assurance & Metrics | T.QV.1 | B.VP.2 | — |
| T.QV.4 Verification & Evaluation (gold standard) | T.QV.2, T.QV.3 | B.VP.2 | — |
| T.OO.1 Triplestore & Ontology Storage | T.DA.2 | — | — |
| T.OO.2 Versioning & Release Management | T.OO.1 | — | B.SG.2 |
| T.OO.3 Ontology CI/CD (OntoOps / DataOps) | T.OO.2, T.QV.2, T.QV.1 | — | — |
| T.OO.4 Federation & Virtualization | T.IA.3, T.OO.1 | — | — |
| T.OO.5 Observability & Monitoring | T.OO.1 | B.VP.2 | — |
| T.AC.1 Search & Query (SPARQL) | T.OO.1 | B.SE.2 | — |
| T.AC.2 Visualization & Exploration | T.AC.1 | B.SE.1 | — |
| T.AC.3 Documentation & Publishing | T.DA.2 | B.VP.3 | — |
| T.AC.4 Ontology-based Access, APIs & Entitlements | T.AC.1, T.IA.3 | — | B.SG.5 |
| T.AC.5 Multilingual & Localization Support | T.DA.6 | — | — |
| T.AC.6 LLM / AI Augmentation | T.RI.2, T.AC.1 | B.VP.1 | — |

## Artifacts

- `artifacts/capability_taxonomy.mmd` — Mermaid taxonomy (domain→category→capability, with EKGF level).
- `artifacts/capability_ontology.mmd` — Mermaid ontology-relations diagram.
- `artifacts/capability_archimate.svg` — ArchiMate capability map (SVG, maturity heat-map).
- `artifacts/capability_archimate.png` — raster twin of the ArchiMate map.
- `artifacts/capability_ontology.ttl` — RDF/OWL/SKOS serialisation (rdflib).
- `artifacts/capability_ontology.png` — networkx visualisation of the capability ontology.
