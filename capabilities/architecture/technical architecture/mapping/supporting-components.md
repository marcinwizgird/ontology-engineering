# Supporting Components — Proposal (the remaining technology stack)

**Audience:** infrastructure / platform engineering team.
**Scope:** the technology components **beyond FalkorDB and Fuseki** needed to operate the Ontology Engineering platform at **EKGF Level 2 — Extensible Platform** on **GKE/GCP**.
**Normative requirements:** `TR.CN.*` (GKE platform) and `TR.SP.*` (supporting), see `../REQUIREMENTS_CATALOG.md`.

This is a **proposal** (recommended technologies + rationale), not a mandate; substitutions are fine where the requirements are still met.

---

## 0. The dual-store picture (why a sync component is mandatory)

```
        Authoring / CI-CD                         Consumers (viz, docs, apps, GraphRAG)
              │ commit                                   ▲          ▲
              ▼                                          │ SPARQL   │ Cypher/vector
   ┌────────────────────┐   RDF Delta change log   ┌─────────────┐ ┌──────────────┐
   │  Fuseki (TDB2)      │ ───────────────────────▶ │ Projection/ │ │  FalkorDB    │
   │  CANONICAL RDF/OWL  │                          │ Sync svc    │▶│  LPG proj.   │
   └────────────────────┘                          └─────────────┘ └──────────────┘
```

Fuseki is canonical; FalkorDB is a derived projection. **`TR.SP.01` (RDF↔LPG projection & sync) is mandatory** — without it the two stores silently diverge.

## 1. Component proposal (by GCP layer)

| # | Concern | Recommended on GCP/GKE | Realises / supports | Req |
|---|---|---|---|---|
| 1 | **GKE foundation** | Private, VPC-native, **regional** GKE; segregated node pools (mem-optimised / general / batch); Workload Identity | hosts everything | `TR.CN.01–03` |
| 2 | **Secrets & keys** | **Secret Manager** + External Secrets Operator (or CSI driver); CMEK | `TS.SEC` | `TR.CN.04` |
| 3 | **Ingress / API gateway** | **Gateway API** + Cloud Load Balancing + managed TLS + **Cloud Armor** (WAF) | `TS.GW` | `TR.CN.07` |
| 4 | **Identity / SSO** | **Cloud IAM** + **Identity-Aware Proxy** / Identity Platform (OIDC) | `TS.IAM` | `TR.SP.04` |
| 5 | **Observability** | **Managed Service for Prometheus** + Cloud Logging + Cloud Trace + Grafana | `TS.OBS` | `TR.CN.09` |
| 6 | **Object storage** | **Cloud Storage (GCS)** — dual-region, versioned, lifecycle | `TS.OBJ` | `TR.SP.03` |
| 7 | **Source control** | **Cloud Source Repositories** / GitHub Enterprise | `TS.SCM` → `C.REPO` | `T.OO.2` |
| 8 | **CI/CD (OntoOps)** | **Cloud Build** / GitHub Actions running **ROBOT**, **pySHACL**, CQ tests | `TS.CICD` → `C.REPO`, `C.RVE` | `TR.SP.02` |
| 9 | **RDF↔LPG projection/sync** | Custom service consuming **RDF Delta**; RDF→property-graph mapping; reconcile job | `TS.SYNC` → `C.KGS` | `TR.SP.01` |
| 10 | **Reasoning/validation compute** | Kubernetes **Jobs** on a batch pool: ROBOT, HermiT/ELK (where licensed), pySHACL | `C.RVE` | `TR.SP.05` |
| 11 | **Authoring** | WebProtégé / Protégé desktop; or VS Code + ROBOT in CI | `C.AUTH` | `T.DA.2/3` |
| 12 | **Vocabulary / glossary** | **VocBench** / Skosmos (publish); glossary via egeria / Collibra | `C.VOCAB`, `C.GLOSS` | `T.DA.6`, `B.SE.4` |
| 13 | **Visualisation** | WebVOWL / Ontodia served on **Cloud Run** behind SSO | `C.VIZ` | `T.AC.2` |
| 14 | **Documentation portal** | **Widoco/pyLODE** → static site on **GCS + CDN** / Cloud Run | `C.DOC` | `T.AC.3` |
| 15 | **Container & chart registry** | **Artifact Registry** + vulnerability scanning + Binary Authorization | supply chain | `TR.CN.06` |
| 16 | **GraphRAG / embeddings** *(forward-looking)* | Embedding service populating FalkorDB **vector index**; isolated | `C.KGS` | `TR.SP.07` (`T.AC.6`, L5) |

## 2. Networking & isolation (`TR.CN.01`, `TR.CN.07`)

- Single **VPC**, regional GKE, **private nodes**, authorized networks for the control plane.
- **default-deny NetworkPolicy**; explicit allow-lists: gateway→readers, sync→stores, CI→stores, exporters→Prometheus.
- The graph/triple endpoints are **never** internet-exposed; only the gateway (with IAP + Cloud Armor) is.
- Namespaces per environment (`dev`/`test`/`prod`) with **ResourceQuota** and **LimitRange**.

## 3. Identity & access (`TR.SP.04`, `TR.CN.03`)

- **Human access:** enterprise OIDC SSO via IAP/Identity Platform; RBAC roles (reader / editor / steward / admin) mapped to endpoints (read vs SPARQL-update vs admin).
- **Workload access:** **Workload Identity** — each workload's KSA bound to a least-privilege GSA (e.g. only the Fuseki backup job's GSA can write the Fuseki backup bucket).
- No exported SA keys anywhere.

## 4. OntoOps CI/CD pipeline (`TR.SP.02`)

Pipeline stages (Git push → release):

1. **Lint/parse** ontology (ROBOT report).
2. **Validate** — SHACL (pySHACL) + structural checks.
3. **Test** — competency-question SPARQL tests (`T.QV.2`) against an ephemeral Fuseki.
4. **Reason** (optional) — ROBOT reason / HermiT consistency (`T.RI.1`).
5. **Release** — version, tag, write artefact to GCS (`T.OO.2`).
6. **Deploy** — load the named graph into Fuseki (writer).
7. **Project** — trigger `TS.SYNC` to refresh the FalkorDB projection.
8. **Publish** — regenerate docs (Widoco) to the docs site.

Runs on Cloud Build / GitHub Actions; reasoning/validation as batch Jobs (`TR.SP.05`).

## 5. Backup / DR posture (platform-wide)

| Asset | Backup | Store | Owner req |
|---|---|---|---|
| Fuseki TDB2 (canonical) | `/$/backup` + snapshots | dual-region GCS | `TR.SK.09` |
| FalkorDB (projection) | RDB/AOF **or** re-project | dual-region GCS | `TR.PG.12` |
| Ontology releases | pipeline artefact | versioned GCS | `TR.SP.03` |
| Cluster/workload state | **Backup for GKE** + GitOps repo | GCS / Git | `TR.CN.08` |

## 6. Environment & sizing summary

| Environment | FalkorDB tier | Fuseki tier | Notes |
|---|---|---|---|
| dev | Dev | Dev | single replica; relaxed SLOs; ephemeral |
| test | Standard | Standard | HA enabled; CI target; prod-like |
| prod | Standard→Large | Standard→Large | full HA, backups, alerts, SLOs |

## 7. Phasing (suggested)

1. **Foundation:** GKE, node pools, Workload Identity, Secret Manager, Artifact Registry, observability, gateway.
2. **Canonical store:** Fuseki (writer + backups + auth).
3. **Projection:** FalkorDB + RDF Delta + sync service.
4. **OntoOps:** Git + CI/CD + reasoning/validation Jobs.
5. **Consumption:** viz + docs + SSO; then GraphRAG (forward-looking).

## 8. Decisions for the platform owner

- **FalkorDB HA mechanism:** Redis **Sentinel** vs **KubeBlocks** operator (recommend KubeBlocks for managed Day-2 ops).
- **FalkorDB DR:** restore-from-GCS vs **re-projection** as the primary path.
- **Fuseki read scaling:** RDF Delta replicas vs scheduled backup/restore copies.
- **SSO front door:** IAP vs in-cluster OIDC proxy for Fuseki and the user-facing tools.
