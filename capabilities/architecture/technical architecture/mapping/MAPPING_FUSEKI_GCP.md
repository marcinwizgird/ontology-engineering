# Mapping — Semantic-Knowledge-Graph requirements → Fuseki on GCP

How **Apache Jena Fuseki**, deployed on **GKE/GCP**, satisfies each technology-agnostic *Semantic Knowledge Graph Platform* requirement. See also the design narrative in `fuseki-gke.md`.

Maps **10** technology-agnostic requirements (see `../REQUIREMENTS_CATALOG.md`) to their concrete realisation. **`[priority]`** is carried from the agnostic requirement.

## Semantic Knowledge Graph Platform

### TR.SK.01 · Engine-aware memory partitioning  `[MUST]`

**Agnostic requirement.** Process memory SHALL be partitioned per the storage engine's caching model so the working set is cached without starving the engine (e.g. leave OS page-cache headroom for memory-mapped engines; bound managed heaps).

**Fuseki realisation.** Fuseki (TDB2) uses memory-mapped files, so the JVM heap is bounded and the pod memory limit is set well above the heap to leave OS page-cache headroom.

**GCP-context specifics.** JAVA_OPTIONS -Xmx4–8g -XX:+UseG1GC; pod memory limit 2–4× heap (e.g. heap 4Gi / pod 16Gi).

### TR.SK.02 · Safe concurrency / write model  `[MUST]`

**Agnostic requirement.** The platform SHALL enforce its storage engine's concurrency model (e.g. single-writer / multiple-reader) and SHALL prevent unsafe concurrent access that risks data corruption.

**Fuseki realisation.** TDB2 is single-writer / multiple-reader on a 64-bit JVM; exactly one JVM attaches a TDB2 directory, enforced by a single-writer StatefulSet on a ReadWriteOnce volume.

**GCP-context specifics.** StatefulSet replicas=1 (writer); PVC accessModes [ReadWriteOnce]; standby fenced before attach.

### TR.SK.03 · Durable storage with maintenance headroom  `[MUST]`

**Agnostic requirement.** The platform SHALL use SSD-class durable storage sized for data growth plus compaction / maintenance overhead, with snapshots.

**Fuseki realisation.** TDB2 lives on an SSD PVC sized ≥2× the live DB to allow online compaction; volume snapshots enabled.

**GCP-context specifics.** storageClass premium-rwo; PVC ≥2× DB; VolumeSnapshotClass; tdb2 compaction.

### TR.SK.04 · Declarative dataset & endpoint configuration  `[MUST]`

**Agnostic requirement.** Datasets, query endpoints, indexes and query limits SHALL be defined declaratively and version-controlled, reproducible across restarts.

**Fuseki realisation.** Datasets/endpoints/indexes/timeouts are defined by a version-controlled assembler config on a persistent FUSEKI_BASE.

**GCP-context specifics.** config.ttl (tdb2:DatasetTDB2) from ConfigMap; FUSEKI_BASE on PVC; fuseki:queryTimeout; split query/update/admin endpoints.

### TR.SK.05 · Writer redundancy & read replication  `[SHOULD]`

**Agnostic requirement.** The platform SHALL provide writer redundancy within the engine's model (active/standby or clustered) plus read replicas kept current via change-data replication.

**Fuseki realisation.** A single active writer with a warm standby, plus read replicas kept current by RDF Delta change logs.

**GCP-context specifics.** Writer StatefulSet + standby (scaled 0→1 on failover, fenced); RDF Delta feed → read-only Fuseki replicas; PDB + zone anti-affinity.

### TR.SK.06 · Query tier scalability & limits  `[SHOULD]`

**Agnostic requirement.** The read/query tier SHALL be horizontally scalable and SHALL enforce query timeouts and result-size limits.

**Fuseki realisation.** Stateless read-only Fuseki replicas behind the gateway scale query load; query timeouts and result limits are enforced.

**GCP-context specifics.** RO replica Deployment behind Gateway; fuseki:queryTimeout '30000,60000'; result limits.

### TR.SK.07 · Endpoint-segregated authentication & authorization  `[MUST]`

**Agnostic requirement.** Read, write/update and admin interfaces SHALL be separately authenticated and authorized; TLS SHALL be enforced; the platform SHALL NOT be publicly exposed and SHALL run hardened (non-root).

**Fuseki realisation.** AuthN/Z via Apache Shiro and/or an OIDC proxy / IAP; read vs update vs admin endpoints are separated; TLS at the gateway; ClusterIP only.

**GCP-context specifics.** shiro.ini roles and/or IAP; endpoints sparql(read)/update/$(admin); Gateway TLS; ClusterIP + NetworkPolicy; non-root.

### TR.SK.08 · Telemetry & alerting  `[MUST]`

**Agnostic requirement.** The platform SHALL export query latency, request/error rates, engine memory/GC and storage-size metrics to the monitoring stack with dashboards and alerts.

**Fuseki realisation.** Fuseki Prometheus endpoint + JVM/GC metrics to Managed Prometheus with dashboards and alerts.

**GCP-context specifics.** /$/metrics scraped; dashboards heap/GC, query latency, 5xx; alerts on heap>85%, error spikes, disk<25%.

### TR.SK.09 · Consistent backup & DR  `[MUST]`

**Agnostic requirement.** The platform SHALL take transactionally consistent backups to durable, off-platform object storage with a tested restore; as the canonical system of record it SHALL meet a stricter RPO/RTO than derived stores.

**Fuseki realisation.** Transactionally consistent backups via tdb2.tdbbackup or the /$/backup endpoint to dual-region GCS; stricter RPO/RTO as the canonical store.

**GCP-context specifics.** Scheduled /$/backup → GCS dual-region (versioned); restore-to-fresh-PVC runbook; RPO≤1h.

### TR.SK.10 · Semantic data-management features  `[SHOULD]`

**Agnostic requirement.** The platform SHALL isolate data per ontology/dataset (e.g. named graphs), SHOULD provide full-text/label indexing, and MAY support entailment/reasoning regimes per dataset.

**Fuseki realisation.** One named graph per ontology/release; optional Jena text (Lucene) index; optional RDFS/OWL entailment via the assembler.

**GCP-context specifics.** Named graphs; text:TextIndexLucene on rdfs:label; entailment regime per dataset in config.ttl.
