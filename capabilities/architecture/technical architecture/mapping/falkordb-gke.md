# FalkorDB on GKE — Technical Requirements & Design

**Audience:** infrastructure / platform engineering team provisioning the property-graph platform.
**Scope:** FalkorDB as the **property-graph engine** of the Ontology Engineering platform, deployed on **Google Kubernetes Engine (GKE)**. EKGF maturity **Level 2 — Extensible Platform**.
**Normative requirements:** `TR.PG.01–13` (see `../REQUIREMENTS_CATALOG.md`). This document is the engineering design that *satisfies* them; the catalogue is the source of truth for the "shall" statements.

---

## 1. Role in the architecture

FalkorDB realises the **Property-Graph Service** (`TS.PG`) and is one half of the dual-store back-end behind the `C.KGS` *Knowledge Graph Store & Query Engine* application component:

| Store | Model | Role | Canonical? |
|---|---|---|---|
| **Apache Jena Fuseki** | RDF / OWL (triples) | Semantic source of truth, SPARQL, OWL semantics | **Yes** |
| **FalkorDB** | Labelled property graph (LPG) | High-performance traversal, graph analytics, GraphRAG/vector | No — a *projection* |

FalkorDB holds a **property-graph projection** of the canonical RDF graph (kept current by the projection/sync service, `TR.SP.01`). Treat FalkorDB as a rebuildable read-optimised store: this relaxes its DR objectives (it can be re-projected from Fuseki) but it still needs persistence and HA for availability.

## 2. Platform characteristics that drive the requirements

FalkorDB is a **Redis module** (successor to RedisGraph). Key properties the infra team must design around:

- **In-memory engine.** The whole graph lives in RAM (Redis keyspace); disk is for persistence only. Memory is the primary capacity dimension (`TR.PG.03`).
- **GraphBLAS / sparse linear algebra.** Graph operations use sparse matrices; matrix resizing is governed by `NODE_CREATION_BUFFER`. Per-query parallelism uses OpenMP (`OMP_THREAD_COUNT`); concurrent-query parallelism uses a thread pool (`THREAD_COUNT`).
- **Single-primary replication.** One primary takes writes (`GRAPH.QUERY`); replicas serve reads (`GRAPH.RO_QUERY`) and lag asynchronously. Failover needs **Redis Sentinel** or the **KubeBlocks** operator (`TR.PG.07`).
- **Persistence = RDB + AOF.** Same as Redis: point-in-time RDB snapshots and an append-only file. `GRAPH.CONFIG SET` changes are **not** persisted across restart (`TR.PG.06`).
- **Vector index.** Native vector indexing enables hybrid graph + similarity retrieval for GraphRAG (`TR.PG.13`).

## 3. Sizing tiers (starting points — validate by load test)

Memory = (resident graph) + (query working set) + ≥30 % headroom for GraphBLAS matrices, `NODE_CREATION_BUFFER`, and **RDB fork copy-on-write** (a save can transiently double dirty pages).

| Tier | Graph size (nodes+edges) | Pod memory (req=lim) | vCPU (req/lim) | `THREAD_COUNT` | Persistence PVC | Node machine |
|---|---|---|---|---|---|---|
| Dev | ≤ 5 M | 4 GiB | 1 / 2 | 2 | 10 GiB pd-ssd | shared n2-standard |
| Standard | ≤ 50 M | 16 GiB | 4 / 6 | 6 | 50 GiB pd-ssd | n2-highmem-4 |
| Large | ≤ 250 M | 64 GiB | 8 / 12 | 12 | 200 GiB hyperdisk | n2-highmem-8 / m1 |

> Persistence PVC ≥ **3×** the RDB size to absorb AOF growth + AOF rewrite + a spare RDB (`TR.PG.05`). Set `requests = limits` for **Guaranteed** QoS (`TR.PG.03`).

## 4. Topology (HA) — `TR.PG.07`

```
            ┌──────────────── GKE regional cluster (3 zones) ─────────────────┐
            │  ns: knowledge-graph                                            │
 clients ──▶│  Service (ClusterIP, RO)  ──▶ replica-0 (zone-b)  GRAPH.RO_QUERY │
            │  Service (ClusterIP, RW)  ──▶ primary  (zone-a)  GRAPH.QUERY      │
            │                               └─async repl──▶ replica-1 (zone-c)  │
            │  Sentinel x3 (one per zone) ── monitor + auto-failover            │
            └─────────────────────────────────────────────────────────────────┘
```

- **StatefulSet** (or Bitnami Redis chart / KubeBlocks `Cluster`) — 1 primary + ≥1 replica.
- **Redis Sentinel ≥ 3** (quorum 2), one per zone, OR **KubeBlocks** operator for managed failover + Day-2 ops.
- **`topologySpreadConstraints`** across zones; **PodDisruptionBudget** `minAvailable: 1` for replicas.
- Clients use a Sentinel-aware driver (or KubeBlocks-provided service) so they follow primary failover; route reads to the RO service.

## 5. Configuration baseline — `TR.PG.06`, `TR.PG.09`

Set **load-time** parameters via the module load args / ConfigMap (GitOps-managed). Reference values:

| Parameter | Reference value | Why |
|---|---|---|
| `THREAD_COUNT` | = allocatable vCPUs | concurrent query capacity |
| `OMP_THREAD_COUNT` | 1–2 (online) | bound per-query CPU so one query can't starve others |
| `CACHE_SIZE` | 50–100 | query-plan cache for repeated queries |
| `NODE_CREATION_BUFFER` | 16384 (raise for bulk load) | fewer matrix resizes during ingest |
| `QUERY_MEM_CAPACITY` | e.g. 2–4 GiB (bytes) | kill runaway queries before OOM |
| `TIMEOUT_MAX` / `TIMEOUT_DEFAULT` | e.g. 30000 / 10000 ms | bound runtime (0 = unlimited — do not use online) |
| `RESULTSET_SIZE` | e.g. 100000 | bound result payloads |
| `MAX_QUEUED_QUERIES` | e.g. 256 | shed load instead of unbounded backlog |
| Redis `maxmemory-policy` | `noeviction` | **never** evict graph keys (`TR.PG.04`) |
| Redis `appendonly` / `appendfsync` | `yes` / `everysec` | durability with bounded fsync cost |

> `GRAPH.CONFIG SET` at runtime is **not persisted** — bake all of the above into args/ConfigMap so a pod restart is reproducible.

## 6. Security — `TR.PG.10`, `TR.CN.06`

- **AuthN:** Redis ACL users / `requirepass`, credentials from **Secret Manager** via External Secrets (`TR.CN.04`). No default/blank password.
- **In transit:** TLS enabled (Redis TLS); Bolt port disabled (`BOLT_PORT = -1`) unless required and then TLS-secured.
- **Network:** `ClusterIP` only + default-deny `NetworkPolicy` allowing only the sync service, RO clients and Sentinel. **No public IP / LoadBalancer.**
- **Pod hardening:** non-root UID, `readOnlyRootFilesystem: true` (writable only for data/AOF mount), drop capabilities, seccomp `RuntimeDefault`.
- **Supply chain:** image pinned by **digest** from Artifact Registry, vulnerability-scanned; with the Bitnami Redis chart set `global.security.allowInsecureImages: true` and load the module via `extraFlags`.

## 7. Observability — `TR.PG.11`

- Export Redis `INFO` + `GRAPH.INFO` via a Redis exporter sidecar to **Google Managed Service for Prometheus**.
- **Dashboards:** used memory vs maxmemory, ops/sec, p50/p99 query latency, slow-query log, replication lag, connected clients, keyspace size.
- **Alerts:** `used_memory > 80 %` of limit, replication lag > N s, primary down / failover event, AOF rewrite failures, rejected queries (`MAX_QUEUED_QUERIES`).

## 8. Backup & DR — `TR.PG.12`

- **Scheduled backups:** CronJob copies RDB (+ AOF) — or runs `GRAPH.COPY` / dump — to a **dual-region GCS** bucket with object versioning and lifecycle.
- **Lower DR tier acceptable:** because FalkorDB is a *projection* of Fuseki, an alternative recovery path is **re-projection** from the canonical RDF graph (`TR.SP.01`) — document which path is primary.
- **Restore runbook:** restore from GCS **or** re-project; both tested on a schedule and dated.
- **Targets (proposed):** RPO ≤ 15 min (AOF) or "since last RDF release" (re-projection); RTO ≤ 30 min.

## 9. SLOs (proposed)

| SLO | Target |
|---|---|
| Availability (RO query path) | 99.9 % monthly |
| p99 point/traversal read latency | ≤ 50 ms at Standard tier |
| Failover time (primary loss) | ≤ 30 s to RW recovery |
| Projection freshness vs Fuseki | ≤ 5 min (`TR.SP.01`) |

## 10. Acceptance criteria (Definition of Done for the infra team)

1. Primary + ≥1 replica across ≥2 zones; **killing the primary** recovers writes within RTO (`TR.PG.07`).
2. Pod restart **preserves data** and **configuration** (AOF/RDB + ConfigMap) (`TR.PG.05/06`).
3. A pathological query is **aborted by guard-rails**, not the server (`TR.PG.09`).
4. No public exposure; auth + TLS enforced; pod runs non-root (`TR.PG.10`).
5. Dashboards live and a **synthetic memory/lag alert** fires (`TR.PG.11`).
6. A backup is taken and **restored** (or re-projected) in a dated test (`TR.PG.12`).
7. Image pinned by digest and vulnerability-scanned (`TR.CN.06`).

## 11. Out of scope at L2 (future)

- **Write sharding** via Redis Cluster (only if a single primary's memory/write ceiling is exceeded).
- **GraphRAG/embedding** population pipeline (`TR.PG.13`, `TR.SP.07`) — capability `T.AC.6`, EKGF L5.

See `../deploy/falkordb/` for starter Helm values.
