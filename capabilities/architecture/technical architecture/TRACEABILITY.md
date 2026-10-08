# Traceability — Capability → Application → Technology → Requirement

## Technology service → application components served

| Technology service | Serves application components |
|---|---|
| TS.PG Property-Graph Service | C.KGS, C.VIZ, C.RVE |
| TS.RDF RDF Triplestore & SPARQL Service | C.KGS, C.RVE, C.AUTH, C.VOCAB, C.DOC, C.VIZ |
| TS.OBJ Object Storage Service | C.REPO, C.DOC |
| TS.SCM Source Control Service | C.REPO |
| TS.CICD CI/CD (OntoOps) Service | C.REPO, C.RVE |
| TS.SYNC Graph Projection & Sync Service | C.KGS |
| TS.IAM Identity & Access Service | C.AUTH, C.VOCAB, C.GLOSS, C.KGS, C.VIZ, C.DOC |
| TS.GW Ingress / API Gateway Service | C.KGS, C.VIZ, C.DOC, C.AUTH, C.VOCAB |
| TS.OBS Observability Service | C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL |
| TS.SEC Secret & Key Management Service | C.KGS, C.RVE, C.REPO |

## Requirement → application components → capabilities

| Req | Platform | Area | Prio | Components | Capabilities |
|---|---|---|---|---|---|
| TR.PG.01 | Property Graph Platform | Compute | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.PG.02 | Property Graph Platform | Compute | SHOULD | C.KGS | T.AC.1 Search & Query (SPARQL) |
| TR.PG.03 | Property Graph Platform | Memory | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.04 | Property Graph Platform | Memory | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.05 | Property Graph Platform | Storage & Persistence | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.06 | Property Graph Platform | Configuration | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.07 | Property Graph Platform | Availability & HA | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.PG.08 | Property Graph Platform | Scalability | SHOULD | C.KGS | T.AC.1 Search & Query (SPARQL) |
| TR.PG.09 | Property Graph Platform | Scalability | MUST | C.KGS | T.AC.1 Search & Query (SPARQL) |
| TR.PG.10 | Property Graph Platform | Security | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.11 | Property Graph Platform | Observability | MUST | C.KGS | T.OO.5 Observability & Monitoring |
| TR.PG.12 | Property Graph Platform | Backup & DR | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.PG.13 | Property Graph Platform | Data Management | MAY | C.KGS | T.AC.6 LLM / AI Augmentation |
| TR.SK.01 | Semantic Knowledge Graph Platform | Memory | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.SK.02 | Semantic Knowledge Graph Platform | Compute | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.SK.03 | Semantic Knowledge Graph Platform | Storage & Persistence | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.SK.04 | Semantic Knowledge Graph Platform | Configuration | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.SK.05 | Semantic Knowledge Graph Platform | Availability & HA | SHOULD | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.SK.06 | Semantic Knowledge Graph Platform | Scalability | SHOULD | C.KGS | T.AC.1 Search & Query (SPARQL) |
| TR.SK.07 | Semantic Knowledge Graph Platform | Security | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.SK.08 | Semantic Knowledge Graph Platform | Observability | MUST | C.KGS | T.OO.5 Observability & Monitoring |
| TR.SK.09 | Semantic Knowledge Graph Platform | Backup & DR | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.SK.10 | Semantic Knowledge Graph Platform | Data Management | SHOULD | C.KGS, C.DOC | T.AC.1 Search & Query (SPARQL), T.DA.2 Ontology Formalization (OWL/RDFS/SKOS) |
| TR.CN.01 | Cloud-Native Platform | Networking | MUST | C.KGS | — |
| TR.CN.02 | Cloud-Native Platform | Compute | MUST | C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL | — |
| TR.CN.03 | Cloud-Native Platform | Identity & Access | MUST | C.KGS, C.REPO | — |
| TR.CN.04 | Cloud-Native Platform | Secrets | MUST | C.KGS, C.RVE, C.REPO | — |
| TR.CN.05 | Cloud-Native Platform | Storage & Persistence | SHOULD | C.KGS | T.OO.1 Triplestore & Ontology Storage |
| TR.CN.06 | Cloud-Native Platform | Security | SHOULD | — | — |
| TR.CN.07 | Cloud-Native Platform | Networking | MUST | C.KGS, C.VIZ, C.DOC | T.AC.1 Search & Query (SPARQL) |
| TR.CN.08 | Cloud-Native Platform | Operations | SHOULD | C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL | — |
| TR.CN.09 | Cloud-Native Platform | Observability | MUST | C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL | T.OO.5 Observability & Monitoring |
| TR.SP.01 | Platform Services | Data Management | MUST | C.KGS | T.OO.1 Triplestore & Ontology Storage, T.AC.1 Search & Query (SPARQL) |
| TR.SP.02 | Platform Services | Operations | SHOULD | C.REPO, C.RVE | T.OO.2 Versioning & Release Management, T.QV.1 Ontology Validation (SHACL/constraints), T.QV.2 Ontology Testing (Competency-Question tests) |
| TR.SP.03 | Platform Services | Storage & Persistence | MUST | C.REPO, C.DOC | T.OO.2 Versioning & Release Management, T.AC.3 Documentation & Publishing |
| TR.SP.04 | Platform Services | Identity & Access | SHOULD | C.AUTH, C.VOCAB, C.GLOSS, C.VIZ, C.DOC | — |
| TR.SP.05 | Platform Services | Operations | SHOULD | C.RVE | T.RI.1 Logical Consistency & Reasoning, T.QV.1 Ontology Validation (SHACL/constraints), T.QV.2 Ontology Testing (Competency-Question tests) |
| TR.SP.06 | Platform Services | Operations | MAY | C.VIZ, C.DOC | T.AC.2 Visualization & Exploration, T.AC.3 Documentation & Publishing |
| TR.SP.07 | Platform Services | Scalability | MAY | C.KGS | T.AC.6 LLM / AI Augmentation |

## Application component → realising technology nodes

| Application component | Technology service(s) | Realising node(s) |
|---|---|---|
| C.AUTH Ontology Authoring Workbench | TS.RDF, TS.IAM, TS.GW, TS.OBS | Apache Jena Fuseki, Cloud IAM + IAP / OIDC, Gateway API + Cloud LB + Cloud Armor, Managed Prometheus + Cloud Ops |
| C.VOCAB Vocabulary & Thesaurus Manager | TS.RDF, TS.IAM, TS.GW, TS.OBS | Apache Jena Fuseki, Cloud IAM + IAP / OIDC, Gateway API + Cloud LB + Cloud Armor, Managed Prometheus + Cloud Ops |
| C.GLOSS Business Glossary Manager | TS.IAM, TS.OBS | Cloud IAM + IAP / OIDC, Managed Prometheus + Cloud Ops |
| C.RVE Reasoning & Validation Engine | TS.PG, TS.RDF, TS.CICD, TS.OBS, TS.SEC | Apache Jena Fuseki, CI/CD (Cloud Build / GitHub Actions), FalkorDB (Redis module), Managed Prometheus + Cloud Ops, Secret Manager + External Secrets |
| C.KGS Knowledge Graph Store & Query Engine | TS.PG, TS.RDF, TS.SYNC, TS.IAM, TS.GW, TS.OBS, TS.SEC | Apache Jena Fuseki, Cloud IAM + IAP / OIDC, FalkorDB (Redis module), Gateway API + Cloud LB + Cloud Armor, Managed Prometheus + Cloud Ops, RDF Delta (change log), Secret Manager + External Secrets |
| C.REPO Ontology Repository & Version Control | TS.OBJ, TS.SCM, TS.CICD, TS.OBS, TS.SEC | CI/CD (Cloud Build / GitHub Actions), Cloud Storage (GCS), Managed Prometheus + Cloud Ops, Secret Manager + External Secrets, Source Control (Git) |
| C.VIZ Ontology Visualization & Exploration | TS.PG, TS.RDF, TS.IAM, TS.GW, TS.OBS | Apache Jena Fuseki, Cloud IAM + IAP / OIDC, FalkorDB (Redis module), Gateway API + Cloud LB + Cloud Armor, Managed Prometheus + Cloud Ops |
| C.DOC Documentation Generator & Portal | TS.RDF, TS.OBJ, TS.IAM, TS.GW, TS.OBS | Apache Jena Fuseki, Cloud IAM + IAP / OIDC, Cloud Storage (GCS), Gateway API + Cloud LB + Cloud Armor, Managed Prometheus + Cloud Ops |
| C.FUND Portfolio & Funding Management | TS.OBS | Managed Prometheus + Cloud Ops |
| C.SKILL Skills & Talent Management | TS.OBS | Managed Prometheus + Cloud Ops |