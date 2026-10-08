# Mapping — Property-Graph requirements → FalkorDB on GCP

How **FalkorDB**, deployed on **GKE/GCP**, satisfies each technology-agnostic *Property Graph Platform* requirement. See also the design narrative in `falkordb-gke.md`.

Maps **13** technology-agnostic requirements (see `../REQUIREMENTS_CATALOG.md`) to their concrete realisation. **`[priority]`** is carried from the agnostic requirement.

## Property Graph Platform

### TR.PG.01 · Workload resource isolation  `[MUST]`

**Agnostic requirement.** The property-graph platform SHALL run on dedicated compute sized to the engine's resource profile (a memory-resident engine requires RAM-proportional nodes) and SHALL be isolated from antagonistic or bursty workloads via scheduling controls.

**FalkorDB realisation.** FalkorDB is an in-memory Redis-module graph engine; it gets a dedicated GKE memory-optimised node pool, isolated by taints/affinity from JVM and batch workloads.

**GCP-context specifics.** GKE node pool n2-highmem/m1; node taint dedicated=falkordb:NoSchedule + tolerations + zone anti-affinity; nodeSelector workload=memory-optimised.

### TR.PG.02 · Tunable concurrency  `[SHOULD]`

**Agnostic requirement.** The platform SHALL expose configurable maximum concurrent-query and intra-query parallelism settings, alignable to the allocated CPU.

**FalkorDB realisation.** Concurrency and per-query parallelism are set as load-time module args.

**GCP-context specifics.** THREAD_COUNT = allocatable vCPUs; OMP_THREAD_COUNT = 1–2 (GraphBLAS/OpenMP) for online query isolation.

### TR.PG.03 · Capacity sizing & guaranteed resources  `[MUST]`

**Agnostic requirement.** Memory and CPU SHALL be sized to hold the active graph plus query working set plus maintenance headroom (including snapshot copy-on-write for in-memory engines), and the resources SHALL be guaranteed (non-burstable).

**FalkorDB realisation.** The whole graph is RAM-resident; pod memory holds graph + working set + ≥30% headroom for GraphBLAS matrices, NODE_CREATION_BUFFER and RDB fork copy-on-write, with Guaranteed QoS.

**GCP-context specifics.** Pod resources requests==limits (e.g. 16Gi/16Gi at Standard tier); capacity model in mapping/falkordb-gke.md.

### TR.PG.04 · No silent data loss under pressure  `[MUST]`

**Agnostic requirement.** The platform MUST NOT evict or drop graph data under resource pressure; it SHALL reject or queue work instead.

**FalkorDB realisation.** Redis eviction is disabled so graph keys are never dropped.

**GCP-context specifics.** redis.conf maxmemory-policy noeviction.

### TR.PG.05 · Durable, low-RPO persistence  `[MUST]`

**Agnostic requirement.** The platform SHALL persist to SSD-class durable storage with both point-in-time snapshots and a continuous append/write-ahead log (or equivalent), with capacity for log growth and rewrite/compaction.

**FalkorDB realisation.** Persistence uses Redis RDB snapshots + AOF on an SSD PVC sized ≥3× the RDB.

**GCP-context specifics.** appendonly yes, appendfsync everysec; RDB save schedule; storageClass premium-rwo (pd-ssd/hyperdisk); PVC ≥ 3× RDB.

### TR.PG.06 · Declarative, reproducible configuration  `[MUST]`

**Agnostic requirement.** All engine configuration SHALL be declarative and version-controlled and SHALL survive a restart; runtime-only mutations SHALL NOT be relied upon for durable configuration.

**FalkorDB realisation.** Load-time parameters are baked into module args / ConfigMap under GitOps; runtime GRAPH.CONFIG SET is NOT persisted and is not relied upon.

**GCP-context specifics.** --loadmodule falkordb.so THREAD_COUNT … in Helm values.extraFlags; managed via Config Sync/Argo.

### TR.PG.07 · Automatic-failover high availability  `[MUST]`

**Agnostic requirement.** The platform SHALL provide redundant instances across failure domains with automatic failover within the agreed RTO and a disruption budget.

**FalkorDB realisation.** One primary + ≥1 replica with automatic failover via Redis Sentinel (≥3) or the KubeBlocks operator, across zones, with a PodDisruptionBudget.

**GCP-context specifics.** Bitnami Redis chart architecture=replication + sentinel.enabled (quorum 2, 3 replicas) OR KubeBlocks Cluster; pdb.minAvailable=1; topologySpreadConstraints by zone.

### TR.PG.08 · Read scale-out  `[SHOULD]`

**Agnostic requirement.** Read-heavy traffic SHALL be horizontally scalable via read replicas, with replication lag monitored and alerted.

**FalkorDB realisation.** Reads are routed to replicas via GRAPH.RO_QUERY; replication lag is monitored.

**GCP-context specifics.** RO ClusterIP service to replicas; INFO replication lag scraped to Managed Prometheus.

### TR.PG.09 · Query resource guard-rails  `[MUST]`

**Agnostic requirement.** Per-query memory, runtime, result-set size and concurrency/backlog SHALL be bounded so a single query cannot exhaust the instance.

**FalkorDB realisation.** Query guard-rails bound memory, runtime, result size and backlog.

**GCP-context specifics.** QUERY_MEM_CAPACITY, TIMEOUT_MAX/TIMEOUT_DEFAULT, RESULTSET_SIZE, MAX_QUEUED_QUERIES (load-time args).

### TR.PG.10 · Authenticated, encrypted, non-public access  `[MUST]`

**Agnostic requirement.** The platform SHALL enforce authentication, TLS in transit, network segmentation and a hardened runtime (non-root, read-only root filesystem, least capabilities), and SHALL NOT be publicly exposed.

**FalkorDB realisation.** Auth via Redis ACL/requirepass from Secret Manager, TLS in transit, ClusterIP + NetworkPolicy (no public IP), non-root + read-only FS, Bolt port disabled.

**GCP-context specifics.** auth.existingSecret (External Secrets); tls.enabled; service.type ClusterIP; networkPolicy; BOLT_PORT -1; securityContext runAsNonRoot/readOnlyRootFilesystem.

### TR.PG.11 · Telemetry, slow-query insight & alerting  `[MUST]`

**Agnostic requirement.** The platform SHALL export throughput, latency, memory, replication-lag and slow-query metrics to the monitoring stack with dashboards and alerts.

**FalkorDB realisation.** Redis/INFO + GRAPH.INFO metrics via a Redis exporter to Managed Prometheus with dashboards and alerts.

**GCP-context specifics.** metrics.enabled + serviceMonitor; alerts on used_memory>80%, replication lag, failover.

### TR.PG.12 · Off-platform backup & DR  `[MUST]`

**Agnostic requirement.** The platform SHALL take scheduled backups to durable, off-platform object storage with a tested restore meeting the agreed RPO/RTO; where the store is a rebuildable projection, re-derivation from the canonical store is an acceptable recovery path.

**FalkorDB realisation.** RDB/AOF (or GRAPH.COPY exports) backed up to dual-region GCS; alternatively re-projected from Fuseki since FalkorDB is a projection.

**GCP-context specifics.** CronJob → GCS dual-region bucket (versioned); restore runbook OR re-run TS.SYNC projection.

### TR.PG.13 · Hybrid vector + graph retrieval (forward-looking)  `[MAY]`

**Agnostic requirement.** The platform SHOULD be able to store and query vector embeddings alongside the graph to support retrieval-augmented generation.

**FalkorDB realisation.** FalkorDB native vector indexing stores embeddings alongside the graph for GraphRAG.

**GCP-context specifics.** Vector index on node/edge properties; populated by the optional embedding service (TR.SP.07).
