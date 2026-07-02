# Technical Requirements Catalogue (technology-agnostic)

**Vendor- and cloud-product-neutral** technical requirements for the Ontology Engineering technology platform at **EKGF maturity Level 2 — “Extensible Platform”**. They state *what* any conforming product must provide; the concrete realisation for **FalkorDB** and **Apache Jena Fuseki** on **GCP** is given separately in the `mapping/` documents.

**Totals:** 39 requirements — Property Graph Platform: 13, Semantic Knowledge Graph Platform: 10, Cloud-Native Platform: 9, Platform Services: 7  ·  priorities — MUST: 25, SHOULD: 11, MAY: 3.

Priority follows RFC-2119 (**MUST** = mandatory, **SHOULD** = strongly recommended, **MAY** = optional/forward-looking). ID prefixes: `TR.PG` property graph · `TR.SK` semantic knowledge graph · `TR.CN` cloud-native platform · `TR.SP` platform services.

| Agnostic category | Mapped to (GCP context) |
|---|---|
| Property Graph Platform (`TR.PG.*`) | **FalkorDB** — `mapping/MAPPING_FALKORDB_GCP.md` |
| Semantic Knowledge Graph Platform (`TR.SK.*`) | **Fuseki** — `mapping/MAPPING_FUSEKI_GCP.md` |
| Cloud-Native Platform + Platform Services (`TR.CN.*`, `TR.SP.*`) | **GCP** — `mapping/MAPPING_PLATFORM_GCP.md` |

## Property Graph Platform (13 requirements)

### TR.PG.01 · Workload resource isolation  `[MUST]`

**Area:** Compute  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** The property-graph platform SHALL run on dedicated compute sized to the engine's resource profile (a memory-resident engine requires RAM-proportional nodes) and SHALL be isolated from antagonistic or bursty workloads via scheduling controls.

**Rationale.** Graph engines — especially in-memory ones — are sensitive to noisy-neighbour memory/CPU pressure.

**Verification.** Show the dedicated compute pool, scheduling isolation (affinity/taints) and a noisy-neighbour test.

### TR.PG.02 · Tunable concurrency  `[SHOULD]`

**Area:** Compute  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.1

**Requirement.** The platform SHALL expose configurable maximum concurrent-query and intra-query parallelism settings, alignable to the allocated CPU.

**Rationale.** Concurrency and per-query parallelism must be bounded to the pod's CPU to avoid contention.

**Verification.** Show the concurrency settings and a concurrency load test.

### TR.PG.03 · Capacity sizing & guaranteed resources  `[MUST]`

**Area:** Memory  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** Memory and CPU SHALL be sized to hold the active graph plus query working set plus maintenance headroom (including snapshot copy-on-write for in-memory engines), and the resources SHALL be guaranteed (non-burstable).

**Rationale.** An undersized in-memory engine fails under load; burstable resources cause eviction/OOM.

**Verification.** Capacity model + an OOM-free soak test at target size; resources requests==limits.

### TR.PG.04 · No silent data loss under pressure  `[MUST]`

**Area:** Memory  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform MUST NOT evict or drop graph data under resource pressure; it SHALL reject or queue work instead.

**Rationale.** A graph store must never silently lose data.

**Verification.** Attempt to over-fill and confirm errors/back-pressure, not data loss.

### TR.PG.05 · Durable, low-RPO persistence  `[MUST]`

**Area:** Storage & Persistence  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL persist to SSD-class durable storage with both point-in-time snapshots and a continuous append/write-ahead log (or equivalent), with capacity for log growth and rewrite/compaction.

**Rationale.** Snapshots give fast restart; a continuous log gives a low RPO.

**Verification.** Show the persistence config and a kill-restart that recovers recent writes.

### TR.PG.06 · Declarative, reproducible configuration  `[MUST]`

**Area:** Configuration  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** All engine configuration SHALL be declarative and version-controlled and SHALL survive a restart; runtime-only mutations SHALL NOT be relied upon for durable configuration.

**Rationale.** Reproducible, GitOps-managed configuration is required for reliable operations.

**Verification.** Config under version control; a restart preserves it.

### TR.PG.07 · Automatic-failover high availability  `[MUST]`

**Area:** Availability & HA  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** The platform SHALL provide redundant instances across failure domains with automatic failover within the agreed RTO and a disruption budget.

**Rationale.** Single-instance graph stores are a single point of failure.

**Verification.** Demonstrate instance-loss failover within RTO; show the disruption budget.

### TR.PG.08 · Read scale-out  `[SHOULD]`

**Area:** Scalability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.1

**Requirement.** Read-heavy traffic SHALL be horizontally scalable via read replicas, with replication lag monitored and alerted.

**Rationale.** Read replicas absorb query load without affecting the write path.

**Verification.** Show read routing to replicas and a replication-lag alert.

### TR.PG.09 · Query resource guard-rails  `[MUST]`

**Area:** Scalability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.1

**Requirement.** Per-query memory, runtime, result-set size and concurrency/backlog SHALL be bounded so a single query cannot exhaust the instance.

**Rationale.** Unbounded graph queries can OOM or stall the engine.

**Verification.** Submit a pathological query and confirm it is aborted, not the server.

### TR.PG.10 · Authenticated, encrypted, non-public access  `[MUST]`

**Area:** Security  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL enforce authentication, TLS in transit, network segmentation and a hardened runtime (non-root, read-only root filesystem, least capabilities), and SHALL NOT be publicly exposed.

**Rationale.** The store holds enterprise knowledge and must not be open or unauthenticated.

**Verification.** No public exposure; auth + TLS enforced; pod security context reviewed.

### TR.PG.11 · Telemetry, slow-query insight & alerting  `[MUST]`

**Area:** Observability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.5

**Requirement.** The platform SHALL export throughput, latency, memory, replication-lag and slow-query metrics to the monitoring stack with dashboards and alerts.

**Rationale.** In-memory engines need early warning on memory and lag.

**Verification.** Dashboards exist; a synthetic memory/lag alert fires.

### TR.PG.12 · Off-platform backup & DR  `[MUST]`

**Area:** Backup & DR  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL take scheduled backups to durable, off-platform object storage with a tested restore meeting the agreed RPO/RTO; where the store is a rebuildable projection, re-derivation from the canonical store is an acceptable recovery path.

**Rationale.** Local persistence is not a backup; off-platform copies survive cluster/zone loss.

**Verification.** Show the backup job, a restore (or re-derivation), and a dated DR test.

### TR.PG.13 · Hybrid vector + graph retrieval (forward-looking)  `[MAY]`

**Area:** Data Management  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.6

**Requirement.** The platform SHOULD be able to store and query vector embeddings alongside the graph to support retrieval-augmented generation.

**Rationale.** Co-locating vectors with the graph enables hybrid semantic + structural retrieval.

**Verification.** Create a vector index and run a similarity query.

## Semantic Knowledge Graph Platform (10 requirements)

### TR.SK.01 · Engine-aware memory partitioning  `[MUST]`

**Area:** Memory  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** Process memory SHALL be partitioned per the storage engine's caching model so the working set is cached without starving the engine (e.g. leave OS page-cache headroom for memory-mapped engines; bound managed heaps).

**Rationale.** Mis-tuned memory (oversized heap vs page cache) is the most common cause of poor query performance in semantic stores.

**Verification.** Show the memory split and a resident-set-vs-heap dashboard; query-latency under load.

### TR.SK.02 · Safe concurrency / write model  `[MUST]`

**Area:** Compute  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL enforce its storage engine's concurrency model (e.g. single-writer / multiple-reader) and SHALL prevent unsafe concurrent access that risks data corruption.

**Rationale.** Violating a single-writer model corrupts the database.

**Verification.** Show the enforced write topology and single-attach storage.

### TR.SK.03 · Durable storage with maintenance headroom  `[MUST]`

**Area:** Storage & Persistence  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL use SSD-class durable storage sized for data growth plus compaction / maintenance overhead, with snapshots.

**Rationale.** Compaction/maintenance writes a fresh copy; insufficient headroom blocks it.

**Verification.** Show storage sizing and a successful compaction/maintenance run.

### TR.SK.04 · Declarative dataset & endpoint configuration  `[MUST]`

**Area:** Configuration  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** Datasets, query endpoints, indexes and query limits SHALL be defined declaratively and version-controlled, reproducible across restarts.

**Rationale.** Declarative, GitOps-able configuration is reproducible and auditable.

**Verification.** Config in version control; endpoints/limits intact after restart.

### TR.SK.05 · Writer redundancy & read replication  `[SHOULD]`

**Area:** Availability & HA  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** The platform SHALL provide writer redundancy within the engine's model (active/standby or clustered) plus read replicas kept current via change-data replication.

**Rationale.** Single-writer engines still need writer failover and read scale-out.

**Verification.** Demonstrate standby promotion and a replica serving from a change feed.

### TR.SK.06 · Query tier scalability & limits  `[SHOULD]`

**Area:** Scalability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.1

**Requirement.** The read/query tier SHALL be horizontally scalable and SHALL enforce query timeouts and result-size limits.

**Rationale.** Query answering must scale with data and be protected from runaway queries.

**Verification.** Load test the read tier; confirm a long query times out.

### TR.SK.07 · Endpoint-segregated authentication & authorization  `[MUST]`

**Area:** Security  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** Read, write/update and admin interfaces SHALL be separately authenticated and authorized; TLS SHALL be enforced; the platform SHALL NOT be publicly exposed and SHALL run hardened (non-root).

**Rationale.** Unprotected update/admin interfaces allow data tampering.

**Verification.** Unauthenticated update is denied; TLS enforced; no public exposure.

### TR.SK.08 · Telemetry & alerting  `[MUST]`

**Area:** Observability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.5

**Requirement.** The platform SHALL export query latency, request/error rates, engine memory/GC and storage-size metrics to the monitoring stack with dashboards and alerts.

**Rationale.** Engine memory/GC and query latency are the primary health signals.

**Verification.** Dashboards exist; a synthetic alert fires.

### TR.SK.09 · Consistent backup & DR  `[MUST]`

**Area:** Backup & DR  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** The platform SHALL take transactionally consistent backups to durable, off-platform object storage with a tested restore; as the canonical system of record it SHALL meet a stricter RPO/RTO than derived stores.

**Rationale.** Backups of the canonical store must be consistent and well-protected.

**Verification.** Show a consistent backup, a restore and a dated DR test.

### TR.SK.10 · Semantic data-management features  `[SHOULD]`

**Area:** Data Management  ·  **Supports components:** C.KGS, C.DOC  ·  **Capabilities:** T.AC.1, T.DA.2

**Requirement.** The platform SHALL isolate data per ontology/dataset (e.g. named graphs), SHOULD provide full-text/label indexing, and MAY support entailment/reasoning regimes per dataset.

**Rationale.** Dataset isolation, search and entailment underpin ontology use cases.

**Verification.** Show dataset isolation, a text query and an entailment-dependent query.

## Cloud-Native Platform (9 requirements)

### TR.CN.01 · Private, multi-zone managed Kubernetes  `[MUST]`

**Area:** Networking  ·  **Supports components:** C.KGS  ·  **Capabilities:** —

**Requirement.** The platform SHALL run on a private, network-isolated, multi-zone managed Kubernetes service with restricted control-plane access and a default-deny network policy.

**Rationale.** Private multi-zone clusters reduce attack surface and survive zone failure.

**Verification.** Show private cluster config and default-deny NetworkPolicies.

### TR.CN.02 · Workload-segregated, autoscaling compute pools  `[MUST]`

**Area:** Compute  ·  **Supports components:** C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL  ·  **Capabilities:** —

**Requirement.** Separate autoscaling compute pools SHALL be provided per workload profile (memory-optimised, general-purpose and batch) with scheduling labels/taints.

**Rationale.** Different workloads have different resource shapes and isolation needs.

**Verification.** Show the pools, autoscaling bounds and labels/taints.

### TR.CN.03 · Keyless workload identity & least privilege  `[MUST]`

**Area:** Identity & Access  ·  **Supports components:** C.KGS, C.REPO  ·  **Capabilities:** —

**Requirement.** Workloads SHALL obtain cloud permissions via federated workload identity (no long-lived keys), with least-privilege access per workload.

**Rationale.** Keyless identity removes long-lived secret risk and enables least privilege.

**Verification.** Show identity federation bindings and per-workload least-privilege policy.

### TR.CN.04 · Centralized secret & key management  `[MUST]`

**Area:** Secrets  ·  **Supports components:** C.KGS, C.RVE, C.REPO  ·  **Capabilities:** —

**Requirement.** Secrets and keys SHALL come from a managed secret store surfaced into the cluster; plaintext secrets MUST NOT live in manifests or images.

**Rationale.** Centralised, rotated secrets reduce credential sprawl and leakage.

**Verification.** Show the secret integration; no plaintext secrets in manifests.

### TR.CN.05 · SSD storage class + volume snapshots  `[SHOULD]`

**Area:** Storage & Persistence  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1

**Requirement.** Stateful workloads SHALL use an SSD-class dynamic storage class with a volume-snapshot capability and a retain policy for data volumes.

**Rationale.** Latency-sensitive stores need SSD; snapshots add a fast recovery path.

**Verification.** Show the storage/snapshot classes and a successful snapshot.

### TR.CN.06 · Supply-chain assurance  `[SHOULD]`

**Area:** Security  ·  **Supports components:** —  ·  **Capabilities:** —

**Requirement.** Container images SHALL come from a trusted registry, be vulnerability-scanned, signed and admission-controlled, and be pinned by digest.

**Rationale.** Prevents unverified or vulnerable images from running.

**Verification.** Show signing/scanning/admission policy and an admission denial of an unsigned image.

### TR.CN.07 · Managed ingress with TLS & WAF  `[MUST]`

**Area:** Networking  ·  **Supports components:** C.KGS, C.VIZ, C.DOC  ·  **Capabilities:** T.AC.1

**Requirement.** All access SHALL traverse a managed ingress/load-balancer with TLS and a web application firewall; data/graph endpoints SHALL NOT be directly internet-exposed.

**Rationale.** Central ingress provides TLS, WAF and consistent routing/authz.

**Verification.** Show ingress, TLS and WAF policy; stores are not internet-reachable.

### TR.CN.08 · GitOps, environment isolation & cluster backup  `[SHOULD]`

**Area:** Operations  ·  **Supports components:** C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL  ·  **Capabilities:** —

**Requirement.** Cluster and workload configuration SHALL be delivered declaratively via GitOps across isolated environments with resource quotas, and cluster state SHALL be backed up.

**Rationale.** Declarative, audited, reproducible operations with environment isolation.

**Verification.** Show the GitOps repo, namespace quotas and a cluster-state backup plan.

### TR.CN.09 · Unified observability with SLOs  `[MUST]`

**Area:** Observability  ·  **Supports components:** C.AUTH, C.VOCAB, C.GLOSS, C.RVE, C.KGS, C.REPO, C.VIZ, C.DOC, C.FUND, C.SKILL  ·  **Capabilities:** T.OO.5

**Requirement.** A unified metrics/logs/traces stack SHALL collect telemetry for all components with SLO dashboards and an on-call alert-routing policy.

**Rationale.** A single pane of glass is required to operate to SLOs.

**Verification.** Show dashboards, SLOs and alert routing.

## Platform Services (7 requirements)

### TR.SP.01 · Canonical → projection synchronization  `[MUST]`

**Area:** Data Management  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.OO.1, T.AC.1

**Requirement.** A synchronisation service SHALL keep the derived property-graph projection consistent with the canonical semantic graph via a change-data feed, with a documented mapping and a reconciliation/repair job.

**Rationale.** The dual-store design needs a defined, auditable sync so the projection never silently diverges from the canonical semantics.

**Verification.** Show the mapping; a canonical change appears in the projection within SLA.

### TR.SP.02 · Automated ontology delivery (OntoOps)  `[SHOULD]`

**Area:** Operations  ·  **Supports components:** C.REPO, C.RVE  ·  **Capabilities:** T.OO.2, T.QV.1, T.QV.2

**Requirement.** An automated pipeline SHALL build, validate (constraint + competency-question tests) and release ontologies from source control, then deploy them to the stores.

**Rationale.** Automated, tested releases are the L2 'extensible platform' way of working.

**Verification.** Show a pipeline run that validates and deploys an ontology change.

### TR.SP.03 · Durable artifact / object storage  `[MUST]`

**Area:** Storage & Persistence  ·  **Supports components:** C.REPO, C.DOC  ·  **Capabilities:** T.OO.2, T.AC.3

**Requirement.** Durable object storage SHALL hold ontology releases, published documentation and store backups, with versioning, lifecycle and multi-region resilience.

**Rationale.** Central durable artefact storage underpins releases, docs and DR.

**Verification.** Show the storage layout, lifecycle and versioning policies.

### TR.SP.04 · Enterprise SSO for human-facing tools  `[SHOULD]`

**Area:** Identity & Access  ·  **Supports components:** C.AUTH, C.VOCAB, C.GLOSS, C.VIZ, C.DOC  ·  **Capabilities:** —

**Requirement.** Human-facing components SHALL authenticate via enterprise OIDC SSO with role-based access.

**Rationale.** Consistent SSO and RBAC across the toolchain is required for governance.

**Verification.** Show OIDC integration and an RBAC denial.

### TR.SP.05 · Isolated reasoning / validation compute  `[SHOULD]`

**Area:** Operations  ·  **Supports components:** C.RVE  ·  **Capabilities:** T.RI.1, T.QV.1, T.QV.2

**Requirement.** Reasoning/validation workloads SHALL run as ephemeral, resource-bounded batch jobs isolated from the online stores.

**Rationale.** Reasoning is bursty and resource-heavy; isolating it protects the online stores.

**Verification.** Show a batch job and a completed validation run.

### TR.SP.06 · Stateless visualization & documentation hosting  `[MAY]`

**Area:** Operations  ·  **Supports components:** C.VIZ, C.DOC  ·  **Capabilities:** T.AC.2, T.AC.3

**Requirement.** Visualisation and generated documentation SHALL be served as stateless workloads / static sites behind the gateway and SSO.

**Rationale.** A read-mostly, stateless presentation tier decouples consumers from the stores.

**Verification.** Show the hosted viz and docs endpoints behind SSO.

### TR.SP.07 · Embedding / GraphRAG enablement (forward-looking)  `[MAY]`

**Area:** Scalability  ·  **Supports components:** C.KGS  ·  **Capabilities:** T.AC.6

**Requirement.** An optional, isolated embedding/GraphRAG service MAY populate the property-graph vector index to ground AI features without affecting core store SLOs.

**Rationale.** Prepares the L5 'LLM/AI augmentation' capability without compromising L2 stability.

**Verification.** Show an isolated deployment populating a vector index.
