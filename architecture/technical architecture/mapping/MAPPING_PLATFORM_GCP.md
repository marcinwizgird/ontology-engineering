# Mapping — Cloud-Native & Platform-Services requirements → GCP

How **GCP/GKE** services satisfy the shared, store-agnostic platform requirements that **both** FalkorDB and Fuseki depend on. See also `supporting-components.md`.

Maps **16** technology-agnostic requirements (see `../REQUIREMENTS_CATALOG.md`) to their concrete realisation. **`[priority]`** is carried from the agnostic requirement.

## Cloud-Native Platform

### TR.CN.01 · Private, multi-zone managed Kubernetes  `[MUST]`

**Agnostic requirement.** The platform SHALL run on a private, network-isolated, multi-zone managed Kubernetes service with restricted control-plane access and a default-deny network policy.

**GCP realisation.** Private, VPC-native, regional GKE.

**GCP-context specifics.** Private nodes, authorized control-plane networks, default-deny NetworkPolicy.

### TR.CN.02 · Workload-segregated, autoscaling compute pools  `[MUST]`

**Agnostic requirement.** Separate autoscaling compute pools SHALL be provided per workload profile (memory-optimised, general-purpose and batch) with scheduling labels/taints.

**GCP realisation.** Segregated GKE node pools per workload profile.

**GCP-context specifics.** Pools: memory-optimised (FalkorDB), general-purpose (Fuseki/services), batch (reasoning); cluster autoscaler; labels/taints.

### TR.CN.03 · Keyless workload identity & least privilege  `[MUST]`

**Agnostic requirement.** Workloads SHALL obtain cloud permissions via federated workload identity (no long-lived keys), with least-privilege access per workload.

**GCP realisation.** GKE Workload Identity, no exported SA keys.

**GCP-context specifics.** KSA↔GSA bindings; least-privilege IAM (e.g. only backup pods write their GCS bucket).

### TR.CN.04 · Centralized secret & key management  `[MUST]`

**Agnostic requirement.** Secrets and keys SHALL come from a managed secret store surfaced into the cluster; plaintext secrets MUST NOT live in manifests or images.

**GCP realisation.** Secret Manager surfaced via External Secrets / CSI.

**GCP-context specifics.** ExternalSecret / Secret Manager CSI; CMEK; no plaintext in manifests.

### TR.CN.05 · SSD storage class + volume snapshots  `[SHOULD]`

**Agnostic requirement.** Stateful workloads SHALL use an SSD-class dynamic storage class with a volume-snapshot capability and a retain policy for data volumes.

**GCP realisation.** SSD storage classes + volume snapshots.

**GCP-context specifics.** StorageClass premium-rwo (pd-ssd/hyperdisk); VolumeSnapshotClass; reclaimPolicy Retain.

### TR.CN.06 · Supply-chain assurance  `[SHOULD]`

**Agnostic requirement.** Container images SHALL come from a trusted registry, be vulnerability-scanned, signed and admission-controlled, and be pinned by digest.

**GCP realisation.** Artifact Registry + scanning + Binary Authorization.

**GCP-context specifics.** Images pinned by digest; vulnerability scanning; signed-image admission in prod namespaces.

### TR.CN.07 · Managed ingress with TLS & WAF  `[MUST]`

**Agnostic requirement.** All access SHALL traverse a managed ingress/load-balancer with TLS and a web application firewall; data/graph endpoints SHALL NOT be directly internet-exposed.

**GCP realisation.** Gateway API + Cloud Load Balancing + managed TLS + Cloud Armor.

**GCP-context specifics.** HTTPRoute + managed certs + Cloud Armor WAF; graph/SPARQL endpoints internal only.

### TR.CN.08 · GitOps, environment isolation & cluster backup  `[SHOULD]`

**Agnostic requirement.** Cluster and workload configuration SHALL be delivered declaratively via GitOps across isolated environments with resource quotas, and cluster state SHALL be backed up.

**GCP realisation.** GitOps + environment namespaces + Backup for GKE.

**GCP-context specifics.** Config Sync/Argo CD; dev/test/prod namespaces with ResourceQuota/LimitRange; Backup for GKE.

### TR.CN.09 · Unified observability with SLOs  `[MUST]`

**Agnostic requirement.** A unified metrics/logs/traces stack SHALL collect telemetry for all components with SLO dashboards and an on-call alert-routing policy.

**GCP realisation.** Managed Service for Prometheus + Cloud Logging/Trace + Grafana.

**GCP-context specifics.** Single observability stack; SLO dashboards; on-call alert routing.

## Platform Services

### TR.SP.01 · Canonical → projection synchronization  `[MUST]`

**Agnostic requirement.** A synchronisation service SHALL keep the derived property-graph projection consistent with the canonical semantic graph via a change-data feed, with a documented mapping and a reconciliation/repair job.

**GCP realisation.** An RDF Delta change feed drives a projection/sync service that maps the canonical RDF graph into the FalkorDB property graph, with a reconciliation job.

**GCP-context specifics.** RDF Delta → sync service (RDF→LPG mapping) → FalkorDB; nightly reconcile Job; freshness ≤5min.

### TR.SP.02 · Automated ontology delivery (OntoOps)  `[SHOULD]`

**Agnostic requirement.** An automated pipeline SHALL build, validate (constraint + competency-question tests) and release ontologies from source control, then deploy them to the stores.

**GCP realisation.** OntoOps pipeline on Cloud Build / GitHub Actions: ROBOT + pySHACL + competency-question tests, release to GCS, deploy to Fuseki, trigger FalkorDB projection.

**GCP-context specifics.** Cloud Build triggers; ephemeral Fuseki for CQ tests; deploy named graph; invoke TS.SYNC.

### TR.SP.03 · Durable artifact / object storage  `[MUST]`

**Agnostic requirement.** Durable object storage SHALL hold ontology releases, published documentation and store backups, with versioning, lifecycle and multi-region resilience.

**GCP realisation.** GCS buckets for releases, docs and backups.

**GCP-context specifics.** Dual-region buckets; object versioning; lifecycle; per-purpose IAM.

### TR.SP.04 · Enterprise SSO for human-facing tools  `[SHOULD]`

**Agnostic requirement.** Human-facing components SHALL authenticate via enterprise OIDC SSO with role-based access.

**GCP realisation.** Enterprise OIDC SSO via IAP / Identity Platform + RBAC.

**GCP-context specifics.** IAP in front of human-facing tools; roles reader/editor/steward/admin.

### TR.SP.05 · Isolated reasoning / validation compute  `[SHOULD]`

**Agnostic requirement.** Reasoning/validation workloads SHALL run as ephemeral, resource-bounded batch jobs isolated from the online stores.

**GCP realisation.** Kubernetes Jobs on a batch node pool for reasoning/validation.

**GCP-context specifics.** ROBOT/HermiT-ELK (where licensed)/pySHACL as bounded Jobs; results back to stores.

### TR.SP.06 · Stateless visualization & documentation hosting  `[MAY]`

**Agnostic requirement.** Visualisation and generated documentation SHALL be served as stateless workloads / static sites behind the gateway and SSO.

**GCP realisation.** Viz (WebVOWL/Ontodia) and docs (Widoco/pyLODE) on Cloud Run / GCS+CDN.

**GCP-context specifics.** Stateless services behind Gateway + IAP; docs as static site on GCS+CDN.

### TR.SP.07 · Embedding / GraphRAG enablement (forward-looking)  `[MAY]`

**Agnostic requirement.** An optional, isolated embedding/GraphRAG service MAY populate the property-graph vector index to ground AI features without affecting core store SLOs.

**GCP realisation.** Optional embedding/GraphRAG service populating the FalkorDB vector index.

**GCP-context specifics.** Isolated Deployment; writes vector index; does not share FalkorDB SLO budget.
