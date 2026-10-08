# Apache Jena Fuseki on GKE — Technical Requirements & Design

**Audience:** infrastructure / platform engineering team provisioning the semantic knowledge-graph store.
**Scope:** Apache Jena **Fuseki** (TDB2) as the **canonical RDF/OWL triplestore and SPARQL endpoint** of the Ontology Engineering platform, on **GKE**. EKGF maturity **Level 2 — Extensible Platform**.
**Normative requirements:** `TR.SK.01–10` (see `../REQUIREMENTS_CATALOG.md`).

---

## 1. Role in the architecture

Fuseki realises the **RDF Triplestore & SPARQL Service** (`TS.RDF`) and is the **canonical** half of the dual-store behind `C.KGS`. It is the system of record for OWL ontologies, SKOS vocabularies, SHACL shapes and instance triples; FalkorDB is a derived property-graph projection (see `falkordb-gke.md`).

Consumers: `C.AUTH` (load/commit ontologies), `C.RVE` (read for reasoning/validation), `C.VOCAB`, `C.DOC`, `C.VIZ`, and the projection/sync service `TR.SP.01`.

## 2. Platform characteristics that drive the requirements

Fuseki is a **JVM** SPARQL 1.1 server, here backed by **TDB2**:

- **TDB2 is single-writer (MRSW).** Multiple readers, **one** writer; a TDB2 database directory must be accessed by **exactly one JVM** at a time or it corrupts (`TR.SK.02`). This is the single most important operational constraint.
- **Memory-mapped files.** TDB2 maps its files into the OS page cache (64-bit only). Performance depends on **RAM left to the OS for the cache**, *not* on a big JVM heap — an oversized `-Xmx` actually *hurts* (`TR.SK.01`).
- **Online compaction.** TDB2 reclaims space by writing a fresh copy → needs free disk headroom (`TR.SK.03`).
- **Declarative datasets.** TDB2 datasets are defined by an **assembler** `config.ttl`; the UI cannot create them (`TR.SK.04`).
- **Not natively clustered.** HA is **active/standby** writer + read replicas fed by **RDF Delta** change logs (`TR.SK.05`).

## 3. Memory model — `TR.SK.01` (the key gotcha)

```
pod memory limit  ─┬─ JVM heap (-Xmx, G1GC)         e.g. 4–8 GiB
                   ├─ JVM non-heap (metaspace, threads, direct)  ~1 GiB
                   └─ HEADROOM for OS page cache (TDB2 mmap)  ← keep this LARGE
```

Rule of thumb: heap **2–8 GiB** is plenty for most datasets; give the pod **2–4× the heap** as total memory so the OS can cache the TDB2 files. Do **not** set `-Xmx` to most of the pod memory.

## 4. Sizing tiers (validate by load test)

| Tier | Dataset (triples) | `-Xmx` heap | Pod memory limit | vCPU | TDB2 PVC |
|---|---|---|---|---|---|
| Dev | ≤ 10 M | 2 GiB | 6 GiB | 1 / 2 | 10 GiB pd-ssd |
| Standard | ≤ 200 M | 4 GiB | 16 GiB | 2 / 4 | 60 GiB pd-ssd |
| Large | ≤ 1 B | 8 GiB | 48 GiB | 4 / 8 | 300 GiB pd-ssd/hyperdisk |

> TDB2 PVC ≥ **2×** the live database to allow online compaction (`TR.SK.03`); **ReadWriteOnce**, single attach (`TR.SK.02`). JVM: G1GC, container-aware (`-XX:MaxRAMPercentage` *or* explicit `-Xmx`).

## 5. Topology (HA) — `TR.SK.05`

```
                 ┌────────────── GKE regional cluster ──────────────┐
 writes ───▶ Gateway ─▶  Fuseki WRITER (active, 1 replica)  ─┐        │
                          └ standby writer (scaled 0→1 on failover)   │
                                       │ RDF Delta change log         │
 reads  ───▶ Gateway ─▶  Fuseki READER replicas (N, RO) ◀────┘        │
                 └───────────────────────────────────────────────────┘
```

- **One active writer** StatefulSet (replicas=1) on its own TDB2 PVC. A **warm standby** (separate StatefulSet scaled 0, or PDB-protected) is promoted on failure; ensure the old writer is fully stopped before the new one attaches (fencing) to honour single-writer.
- **Read replicas:** stateless Fuseki pods serving RO datasets kept current via **RDF Delta** (or periodic backup/restore sync). Scale horizontally for query load.
- **PodDisruptionBudget** + zone anti-affinity. Writer and standby in different zones.

## 6. Configuration — `TR.SK.04`

- **`FUSEKI_BASE`** on the persistent volume; **assembler `config.ttl`** (mounted from a versioned ConfigMap) defines each TDB2 dataset and its endpoints.
- One **named graph per ontology/release** (`TR.SK.10`); optional **Jena text (Lucene)** index for label search; optional **RDFS/OWL entailment** regime per dataset.
- **Query/update timeouts** (`fuseki:queryTimeout`) and result limits set per endpoint (`TR.SK.06`).
- Separate **read**, **update** and **admin (`/$/`)** endpoints so they can be authorised independently (`TR.SK.07`).

Example assembler skeleton is in `../deploy/fuseki/config-tdb2.ttl`.

## 7. Security — `TR.SK.07`

- **AuthN/Z:** Apache **Shiro** (`shiro.ini`) for built-in users/roles, and/or front Fuseki with an **OIDC proxy / Cloud IAP** for enterprise SSO (`TR.SP.04`). Update + admin endpoints require elevated roles; anonymous read only if explicitly intended.
- **TLS** terminated at the Gateway (`TR.CN.07`); Fuseki itself `ClusterIP` + default-deny `NetworkPolicy`; **no public IP**.
- **Pod hardening:** non-root, read-only root FS (writable data mount only), dropped capabilities.
- Credentials/keys from **Secret Manager** (`TR.CN.04`).

## 8. Observability — `TR.SK.08`

- Enable the Fuseki **Prometheus metrics** endpoint (`/$/metrics`) + JVM/GC metrics → Managed Prometheus.
- **Dashboards:** heap usage & GC pause time, request rate, SPARQL query latency (p50/p99), error rate (4xx/5xx), active transactions, dataset size on disk.
- **Alerts:** sustained heap > 85 %, GC pause spikes, 5xx rate, disk free < 25 % (compaction risk), writer down.

## 9. Backup & DR — `TR.SK.09`

- **Consistent backups:** scheduled `tdb2.tdbbackup` or the Fuseki **`/$/backup`** admin endpoint (transactionally consistent) to a **dual-region GCS** bucket; complemented by periodic **online compaction**.
- Volume snapshots (`TR.CN.05`) as a fast local recovery path.
- **Restore runbook** tested and dated; restore to a fresh PVC then attach a single writer.
- **Targets (proposed):** RPO ≤ 1 h (or per-release for ontology data); RTO ≤ 1 h. Because Fuseki is **canonical**, its DR objectives are stricter than FalkorDB's.

## 10. SLOs (proposed)

| SLO | Target |
|---|---|
| Read (SPARQL query) availability | 99.9 % monthly |
| p99 typical SPARQL query latency | ≤ 200 ms at Standard tier |
| Writer failover (standby promotion) | ≤ 5 min |
| Backup success rate | 100 % (alert on miss) |

## 11. Acceptance criteria (Definition of Done)

1. Single active writer enforced; PVC is **ReadWriteOnce**; no two JVMs touch one TDB2 dir (`TR.SK.02`).
2. Heap bounded and pod memory leaves page-cache headroom; verified via RSS-vs-heap dashboard (`TR.SK.01`).
3. Datasets defined by version-controlled `config.ttl`; survive restart with endpoints/timeouts intact (`TR.SK.04`).
4. Unauthenticated **SPARQL Update**/admin is denied; TLS enforced; no public exposure (`TR.SK.07`).
5. Read replica serves queries from an **RDF Delta** feed; standby promotion demonstrated (`TR.SK.05`).
6. Online **compaction** runs with sufficient disk headroom (`TR.SK.03`).
7. A **`/$/backup`** is taken to GCS and **restored** in a dated test (`TR.SK.09`).
8. Metrics dashboards live; a synthetic heap/error alert fires (`TR.SK.08`).

## 12. Notes

- If write throughput or dataset size outgrows a single TDB2 writer, evaluate sharding by domain (multiple datasets/servers) or a commercial RDF store; this is **beyond L2**.
- Keep the FalkorDB projection (`TR.SP.01`) downstream of the **writer's** RDF Delta feed so the property graph tracks the canonical graph.

See `../deploy/fuseki/` for a starter StatefulSet + assembler config.
