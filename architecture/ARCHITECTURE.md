# Level-2 Application Architecture — Ontology Engineering

Logical **application architecture** (ArchiMate application layer) that provides the application **services** required to support the **14 capabilities at EKGF maturity Level 2 — “Extensible Platform”** of the Ontology Engineering Capability Model.

> *Extensible Platform* (EKG/MM L2): “the organisation has implemented an Enterprise Knowledge Graph and is starting to build out its capabilities and integrations with other systems and processes.” The architecture below is the minimum coherent set of application services/components to operate the ontology practice as a reusable platform.

**Model integrity:** consistent (0 problems)

## 1. Overview

The architecture is organised into four ArchiMate layers and six application domains:

- **Capabilities (L2)** — the business/technology capabilities being supported.
- **Application Services** — externally visible behaviour; one service per L2 capability.
- **Application Components** — deployable software realising the services.
- **Data Objects** — passive structure the components access.

| Application domain | Purpose | Components |
|---|---|---|
| **MOD · Modelling & Authoring** | Author and formalise ontologies and reuse foundational models. | Ontology Authoring Workbench |
| **VOC · Vocabulary & Glossary** | Manage controlled vocabularies, thesauri and the business glossary. | Vocabulary & Thesaurus Manager, Business Glossary Manager |
| **RVT · Reasoning, Validation & Testing** | Classify, check consistency, validate constraints and run CQ tests. | Reasoning & Validation Engine |
| **KGP · Knowledge Graph Platform** | Store, version, release and query ontologies and their graphs. | Knowledge Graph Store & Query Engine, Ontology Repository & Version Control |
| **ACP · Access & Publishing** | Explore, visualise, document and publish ontologies. | Ontology Visualization & Exploration, Documentation Generator & Portal |
| **ENB · Enterprise Enablement** | Enterprise services that fund and staff the ontology practice. | Portfolio & Funding Management, Skills & Talent Management |

## 2. Capability → Application Service → Component mapping

Each Level-2 capability is served by an application service realised by a component.

| L2 capability | Application service | Realising component | EKGF pillar |
|---|---|---|---|
| T.DA.2 Ontology Formalization (OWL/RDFS/SKOS) | S.AUTH **Ontology Authoring Service** | C.AUTH Ontology Authoring Workbench | Data |
| T.DA.3 Foundational / Top-down Ontology Reuse | S.IMPORT **Foundational Ontology Import Service** | C.AUTH Ontology Authoring Workbench | Data |
| T.DA.6 Vocabulary & Controlled-Term Management | S.VOCAB **Controlled Vocabulary Management Service** | C.VOCAB Vocabulary & Thesaurus Manager | Data |
| B.SE.4 Business Glossary & Terminology Management | S.GLOSS **Business Glossary Service** | C.GLOSS Business Glossary Manager | Data |
| T.RI.1 Logical Consistency & Reasoning | S.REASON **Consistency Reasoning Service** | C.RVE Reasoning & Validation Engine | Technology |
| T.QV.1 Ontology Validation (SHACL/constraints) | S.VALIDATE **Constraint Validation Service** | C.RVE Reasoning & Validation Engine | Data |
| T.QV.2 Ontology Testing (Competency-Question tests) | S.CQTEST **Competency-Question Testing Service** | C.RVE Reasoning & Validation Engine | Data |
| T.OO.1 Triplestore & Ontology Storage | S.STORE **Graph Storage Service** | C.KGS Knowledge Graph Store & Query Engine | Technology |
| T.AC.1 Search & Query (SPARQL) | S.SPARQL **SPARQL Query Service** | C.KGS Knowledge Graph Store & Query Engine | Technology |
| T.OO.2 Versioning & Release Management | S.VERSION **Ontology Versioning & Release Service** | C.REPO Ontology Repository & Version Control | Data |
| T.AC.2 Visualization & Exploration | S.VIZ **Ontology Visualization Service** | C.VIZ Ontology Visualization & Exploration | Technology |
| T.AC.3 Documentation & Publishing | S.DOCS **Documentation Publishing Service** | C.DOC Documentation Generator & Portal | Technology |
| B.SG.4 Funding & Investment Management | S.FUND **Funding & Portfolio Service** | C.FUND Portfolio & Funding Management | Organization |
| B.CT.1 Skills & Talent Management | S.SKILL **Skills & Competency Service** | C.SKILL Skills & Talent Management | Organization |

## 3. Application services (catalogue)

### S.AUTH · Ontology Authoring Service

- **Description:** Create, edit and formalise ontology classes, properties and axioms.
- **Serves capability:** T.DA.2 (Ontology Formalization (OWL/RDFS/SKOS))
- **Realised by:** C.AUTH Ontology Authoring Workbench

### S.IMPORT · Foundational Ontology Import Service

- **Description:** Discover, import and align upper/foundational ontologies and modules.
- **Serves capability:** T.DA.3 (Foundational / Top-down Ontology Reuse)
- **Realised by:** C.AUTH Ontology Authoring Workbench

### S.VOCAB · Controlled Vocabulary Management Service

- **Description:** Curate SKOS vocabularies, thesauri and code lists.
- **Serves capability:** T.DA.6 (Vocabulary & Controlled-Term Management)
- **Realised by:** C.VOCAB Vocabulary & Thesaurus Manager

### S.GLOSS · Business Glossary Service

- **Description:** Maintain business terms reconciled with the ontology.
- **Serves capability:** B.SE.4 (Business Glossary & Terminology Management)
- **Realised by:** C.GLOSS Business Glossary Manager

### S.REASON · Consistency Reasoning Service

- **Description:** Classify the ontology and check logical consistency/satisfiability.
- **Serves capability:** T.RI.1 (Logical Consistency & Reasoning)
- **Realised by:** C.RVE Reasoning & Validation Engine

### S.VALIDATE · Constraint Validation Service

- **Description:** Validate ontology and data against SHACL shapes/constraints.
- **Serves capability:** T.QV.1 (Ontology Validation (SHACL/constraints))
- **Realised by:** C.RVE Reasoning & Validation Engine

### S.CQTEST · Competency-Question Testing Service

- **Description:** Run competency-question test suites on every change.
- **Serves capability:** T.QV.2 (Ontology Testing (Competency-Question tests))
- **Realised by:** C.RVE Reasoning & Validation Engine

### S.STORE · Graph Storage Service

- **Description:** Persist ontologies and instance graphs in a managed store.
- **Serves capability:** T.OO.1 (Triplestore & Ontology Storage)
- **Realised by:** C.KGS Knowledge Graph Store & Query Engine

### S.SPARQL · SPARQL Query Service

- **Description:** Standards-based query access (SPARQL) to the knowledge graph.
- **Serves capability:** T.AC.1 (Search & Query (SPARQL))
- **Realised by:** C.KGS Knowledge Graph Store & Query Engine

### S.VERSION · Ontology Versioning & Release Service

- **Description:** Version, tag, diff and release ontologies under change control.
- **Serves capability:** T.OO.2 (Versioning & Release Management)
- **Realised by:** C.REPO Ontology Repository & Version Control

### S.VIZ · Ontology Visualization Service

- **Description:** Interactive visual exploration of ontology structure and content.
- **Serves capability:** T.AC.2 (Visualization & Exploration)
- **Realised by:** C.VIZ Ontology Visualization & Exploration

### S.DOCS · Documentation Publishing Service

- **Description:** Generate and publish human-readable ontology documentation.
- **Serves capability:** T.AC.3 (Documentation & Publishing)
- **Realised by:** C.DOC Documentation Generator & Portal

### S.FUND · Funding & Portfolio Service

- **Description:** Manage budget, investment and portfolio for the ontology roadmap.
- **Serves capability:** B.SG.4 (Funding & Investment Management)
- **Realised by:** C.FUND Portfolio & Funding Management

### S.SKILL · Skills & Competency Service

- **Description:** Manage ontology-engineering skills, roles and talent.
- **Serves capability:** B.CT.1 (Skills & Talent Management)
- **Realised by:** C.SKILL Skills & Talent Management

## 4. Application components (catalogue)

| ID | Component | Domain | Realises services | Reads | Writes | Uses | Technology candidates |
|---|---|---|---|---|---|---|---|
| C.AUTH | **Ontology Authoring Workbench** | MOD | S.AUTH, S.IMPORT | D.VOC, D.GLO | D.ONT | C.VOCAB, C.RVE, C.KGS | Protégé, TopBraid Composer, VS Code + ROBOT |
| C.VOCAB | **Vocabulary & Thesaurus Manager** | VOC | S.VOCAB | — | D.VOC | C.KGS | VocBench, PoolParty, Skosmos (publish) |
| C.GLOSS | **Business Glossary Manager** | VOC | S.GLOSS | D.VOC | D.GLO | — | Collibra, egeria, Atlan |
| C.RVE | **Reasoning & Validation Engine** | RVT | S.REASON, S.VALIDATE, S.CQTEST | D.ONT, D.GRAPH | D.SHP, D.CQ, D.INF | C.KGS | HermiT/ELK/Pellet, pySHACL/TopBraid SHACL, Themis/OQuaRE |
| C.KGS | **Knowledge Graph Store & Query Engine** | KGP | S.STORE, S.SPARQL | D.ONT | D.GRAPH, D.QRY | — | GraphDB, Stardog, Apache Jena Fuseki, Virtuoso |
| C.REPO | **Ontology Repository & Version Control** | KGP | S.VERSION | D.ONT | D.REL | C.KGS | Git/GitHub/GitLab, ROBOT, OnToology |
| C.VIZ | **Ontology Visualization & Exploration** | ACP | S.VIZ | D.GRAPH, D.ONT | — | C.KGS | WebVOWL, VOWL, yEd/Graphviz, Ontodia |
| C.DOC | **Documentation Generator & Portal** | ACP | S.DOCS | D.ONT | D.DOC | C.REPO | Widoco, pyLODE, Ontospy |
| C.FUND | **Portfolio & Funding Management** | ENB | S.FUND | — | D.FUND | — | Jira Align, ServiceNow SPM, Planview |
| C.SKILL | **Skills & Talent Management** | ENB | S.SKILL | — | D.SKILL | — | Workday, SAP SuccessFactors, Skills matrix |

## 5. Data objects

| ID | Data object | Description | Written by | Read by |
|---|---|---|---|---|
| D.ONT | **OWL Ontology** | The formal ontology (OWL/RDFS) under development. | C.AUTH | C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC |
| D.VOC | **SKOS Vocabulary / Thesaurus** | Controlled vocabularies and thesauri. | C.VOCAB | C.AUTH, C.GLOSS |
| D.GLO | **Business Glossary** | Agreed business terms and definitions. | C.GLOSS | C.AUTH |
| D.SHP | **SHACL Shapes** | Constraint shapes used to validate data and models. | C.RVE | — |
| D.CQ | **Competency-Question Test Suite** | Executable competency-question tests. | C.RVE | — |
| D.GRAPH | **RDF Graph (Triples)** | Stored RDF triples / named graphs. | C.KGS | C.RVE, C.VIZ |
| D.INF | **Inference Result** | Entailments and reasoner classification results. | C.RVE | — |
| D.REL | **Ontology Release / Version** | Versioned, tagged ontology releases. | C.REPO | — |
| D.QRY | **SPARQL Query / Result** | Queries and their result sets. | C.KGS | — |
| D.DOC | **Documentation Site** | Generated human-readable ontology documentation. | C.DOC | — |
| D.FUND | **Funding / Portfolio Record** | Budget, investment and portfolio records. | C.FUND | — |
| D.SKILL | **Skills Profile** | Competency and talent records for the practice. | C.SKILL | — |

## 6. Component cooperation (key dependencies)

`uses` (serving) relations between components — the platform's internal wiring:

- **Ontology Authoring Workbench** uses: Vocabulary & Thesaurus Manager, Reasoning & Validation Engine, Knowledge Graph Store & Query Engine
- **Vocabulary & Thesaurus Manager** uses: Knowledge Graph Store & Query Engine
- **Reasoning & Validation Engine** uses: Knowledge Graph Store & Query Engine
- **Ontology Repository & Version Control** uses: Knowledge Graph Store & Query Engine
- **Ontology Visualization & Exploration** uses: Knowledge Graph Store & Query Engine
- **Documentation Generator & Portal** uses: Ontology Repository & Version Control

## 7. ArchiMate relations used

- **Serving** (service → capability, component → component): the source provides behaviour the target consumes.
- **Realization** (component → service): the component implements the service.
- **Access** (component ⋯ data object): read/write of passive structure.

## 8. Notes & scope

- Scope is deliberately limited to Level 2. Level-1 prerequisites (conceptualisation, competency questions) are assumed available; higher-level capabilities (CI/CD, federation, LLM augmentation, observability) are **out of scope** and would extend this architecture at L3–L5.
- Enterprise-enablement services (funding, skills) are typically realised by existing COTS platforms and are shown for completeness as they support the L2 business capabilities.
- Technology candidates are illustrative, not prescriptive.

## 9. Artifacts

- `artifacts/app_architecture.svg` — ArchiMate application architecture diagram (SVG).
- `artifacts/app_architecture.png` — raster twin of the diagram.
- `artifacts/app_architecture.mmd` — Mermaid view of the same model.
