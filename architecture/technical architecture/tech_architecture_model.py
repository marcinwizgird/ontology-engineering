"""Technical (technology-layer) architecture model for the Ontology Repository
platform — EKGF maturity **Level 2 (Extensible Platform)**.

Two layers, kept deliberately separate:

1. **Technology-agnostic requirements** (``REQUIREMENTS``) for four platform
   categories — *Property Graph Platform*, *Semantic Knowledge Graph Platform*,
   *Cloud-Native Platform* and *Platform Services*. These state *what* any
   conforming product must provide, with **no vendor or cloud-product names**.

2. **Technology mappings** (``MAPPINGS``) that bind each agnostic requirement to
   a concrete realisation — **FalkorDB** (property graph) and **Apache Jena
   Fuseki** (semantic knowledge graph), and the shared **GCP** services — *in the
   context of a GCP/GKE deployment*.

It also defines the ArchiMate technology-layer elements (nodes / system software
/ technology services) realising the Level-2 *application* components from
``architecture/app_architecture_model.py``.

Dual-store context: the ``C.KGS`` component is realised by **both** a canonical
semantic knowledge graph and a derived property-graph projection; a
synchronisation service keeps them consistent.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# make the sibling application-architecture package importable as a script
_ARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_ARCH)
for p in (_ROOT, _ARCH):
    if p not in sys.path:
        sys.path.insert(0, p)

from architecture import app_architecture_model as app  # noqa: E402

TARGET_LEVEL = app.TARGET_LEVEL            # 2
TARGET_LEVEL_NAME = app.TARGET_LEVEL_NAME  # "Extensible Platform"

# Priority vocabulary (RFC-2119 flavoured)
MUST, SHOULD, MAY = "MUST", "SHOULD", "MAY"

AREAS = [
    "Compute", "Memory", "Storage & Persistence", "Networking", "Availability & HA",
    "Scalability", "Security", "Identity & Access", "Secrets", "Observability",
    "Backup & DR", "Configuration", "Data Management", "Operations",
]

# Technology-agnostic platform categories (requirement grouping).
PG = "Property Graph Platform"
SK = "Semantic Knowledge Graph Platform"
CN = "Cloud-Native Platform"
SP = "Platform Services"
PLATFORMS = [PG, SK, CN, SP]

# Concrete technologies used in the mapping layer.
T_FALKOR, T_FUSEKI, T_GCP = "FalkorDB", "Fuseki", "GCP"
# Which technology realises which agnostic platform category.
PLATFORM_TECH = {PG: T_FALKOR, SK: T_FUSEKI, CN: T_GCP, SP: T_GCP}


# --------------------------------------------------------------------------- #
# ArchiMate technology-layer elements (deployment / realisation view)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TechService:
    id: str
    name: str
    description: str
    serves_components: tuple[str, ...]


@dataclass(frozen=True)
class TechNode:
    id: str
    name: str
    kind: str
    group: str
    description: str
    realizes: tuple[str, ...] = ()
    hosted_on: tuple[str, ...] = ()


TECH_SERVICES: list[TechService] = [
    TechService("TS.PG", "Property-Graph Service",
                "OpenCypher property-graph storage, traversal, analytics and vector search.",
                ("C.KGS", "C.VIZ", "C.RVE")),
    TechService("TS.RDF", "RDF Triplestore & SPARQL Service",
                "Canonical RDF/OWL storage with SPARQL 1.1 query/update over HTTP.",
                ("C.KGS", "C.RVE", "C.AUTH", "C.VOCAB", "C.DOC", "C.VIZ")),
    TechService("TS.OBJ", "Object Storage Service",
                "Durable bucket storage for backups, ontology releases and published docs.",
                ("C.REPO", "C.DOC")),
    TechService("TS.SCM", "Source Control Service",
                "Git repositories for ontology source, shapes and pipeline definitions.",
                ("C.REPO",)),
    TechService("TS.CICD", "CI/CD (OntoOps) Service",
                "Automated build/test/release pipelines for ontologies (ROBOT, pySHACL).",
                ("C.REPO", "C.RVE")),
    TechService("TS.SYNC", "Graph Projection & Sync Service",
                "Projects/synchronises the canonical RDF graph into the property graph.",
                ("C.KGS",)),
    TechService("TS.IAM", "Identity & Access Service",
                "OIDC/SSO authentication and authorization for all platform endpoints.",
                ("C.AUTH", "C.VOCAB", "C.GLOSS", "C.KGS", "C.VIZ", "C.DOC")),
    TechService("TS.GW", "Ingress / API Gateway Service",
                "TLS termination, routing and WAF for application and data endpoints.",
                ("C.KGS", "C.VIZ", "C.DOC", "C.AUTH", "C.VOCAB")),
    TechService("TS.OBS", "Observability Service",
                "Metrics, logs, traces, dashboards and alerting for all components.",
                tuple(c.id for c in app.COMPONENTS)),
    TechService("TS.SEC", "Secret & Key Management Service",
                "Central secrets, credentials and encryption keys.",
                ("C.KGS", "C.RVE", "C.REPO")),
]
TECH_SERVICE_BY_ID = {s.id: s for s in TECH_SERVICES}

TECH_NODES: list[TechNode] = [
    TechNode("N.GKE", "GKE Regional Cluster", "platform", "GCP",
             "Private, VPC-native, regional GKE cluster (multi-zone) hosting the platform."),
    TechNode("N.POOL.MEM", "Memory-optimised Node Pool", "node", "GCP",
             "n2-highmem / m1 nodes for the in-memory FalkorDB workload.",
             hosted_on=("N.GKE",)),
    TechNode("N.POOL.GP", "General-purpose Node Pool", "node", "GCP",
             "n2-standard nodes for Fuseki and stateless services.",
             hosted_on=("N.GKE",)),
    TechNode("N.FALKOR", "FalkorDB (Redis module)", "system-software", "KnowledgeGraph",
             "In-memory property-graph engine (GraphBLAS) with RDB/AOF persistence.",
             realizes=("TS.PG",), hosted_on=("N.POOL.MEM",)),
    TechNode("N.FALKOR.PV", "FalkorDB SSD Volume", "storage", "KnowledgeGraph",
             "pd-ssd / hyperdisk PVC holding RDB snapshots and AOF.",
             hosted_on=("N.POOL.MEM",)),
    TechNode("N.SENTINEL", "Redis Sentinel", "system-software", "KnowledgeGraph",
             "Sentinel quorum providing automatic FalkorDB failover.",
             hosted_on=("N.GKE",)),
    TechNode("N.FUSEKI", "Apache Jena Fuseki", "system-software", "KnowledgeGraph",
             "JVM SPARQL server backed by TDB2 (memory-mapped, single-writer).",
             realizes=("TS.RDF",), hosted_on=("N.POOL.GP",)),
    TechNode("N.FUSEKI.PV", "Fuseki TDB2 SSD Volume", "storage", "KnowledgeGraph",
             "pd-ssd PVC holding the TDB2 database (ReadWriteOnce).",
             hosted_on=("N.POOL.GP",)),
    TechNode("N.RDFDELTA", "RDF Delta (change log)", "system-software", "KnowledgeGraph",
             "Replicates TDB2 changes to read replicas / projection pipeline.",
             realizes=("TS.SYNC",), hosted_on=("N.POOL.GP",)),
    TechNode("N.GCS", "Cloud Storage (GCS)", "managed", "GCP",
             "Object storage for backups, releases and published documentation.",
             realizes=("TS.OBJ",)),
    TechNode("N.AR", "Artifact Registry", "managed", "GCP",
             "Container images and Helm charts with vulnerability scanning."),
    TechNode("N.SM", "Secret Manager + External Secrets", "managed", "GCP",
             "Central secret storage surfaced into the cluster.",
             realizes=("TS.SEC",)),
    TechNode("N.IAM", "Cloud IAM + IAP / OIDC", "managed", "GCP",
             "Workload Identity, IAP and OIDC SSO.", realizes=("TS.IAM",)),
    TechNode("N.GW", "Gateway API + Cloud LB + Cloud Armor", "managed", "GCP",
             "Ingress, TLS and WAF.", realizes=("TS.GW",)),
    TechNode("N.OBS", "Managed Prometheus + Cloud Ops", "managed", "GCP",
             "Metrics, logging, tracing, dashboards and alerting.", realizes=("TS.OBS",)),
    TechNode("N.SCM", "Source Control (Git)", "managed", "DevOps",
             "Cloud Source Repositories / GitHub Enterprise.", realizes=("TS.SCM",)),
    TechNode("N.CICD", "CI/CD (Cloud Build / GitHub Actions)", "managed", "DevOps",
             "OntoOps pipelines: build, validate (ROBOT/pySHACL), release, deploy.",
             realizes=("TS.CICD",)),
]
TECH_NODE_BY_ID = {n.id: n for n in TECH_NODES}


# --------------------------------------------------------------------------- #
# Technology-agnostic requirements
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Requirement:
    id: str
    platform: str
    area: str
    title: str
    statement: str
    rationale: str
    verification: str
    priority: str = MUST
    components: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


def R(*a, **k) -> Requirement:
    return Requirement(*a, **k)


REQUIREMENTS: list[Requirement] = [
    # ============ Property Graph Platform (vendor-agnostic) ============== #
    R("TR.PG.01", PG, "Compute", "Workload resource isolation",
      "The property-graph platform SHALL run on dedicated compute sized to the engine's resource "
      "profile (a memory-resident engine requires RAM-proportional nodes) and SHALL be isolated "
      "from antagonistic or bursty workloads via scheduling controls.",
      "Graph engines — especially in-memory ones — are sensitive to noisy-neighbour memory/CPU "
      "pressure.",
      "Show the dedicated compute pool, scheduling isolation (affinity/taints) and a noisy-neighbour test.",
      MUST, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.PG.02", PG, "Compute", "Tunable concurrency",
      "The platform SHALL expose configurable maximum concurrent-query and intra-query parallelism "
      "settings, alignable to the allocated CPU.",
      "Concurrency and per-query parallelism must be bounded to the pod's CPU to avoid contention.",
      "Show the concurrency settings and a concurrency load test.",
      SHOULD, ("C.KGS",), ("T.AC.1",)),
    R("TR.PG.03", PG, "Memory", "Capacity sizing & guaranteed resources",
      "Memory and CPU SHALL be sized to hold the active graph plus query working set plus "
      "maintenance headroom (including snapshot copy-on-write for in-memory engines), and the "
      "resources SHALL be guaranteed (non-burstable).",
      "An undersized in-memory engine fails under load; burstable resources cause eviction/OOM.",
      "Capacity model + an OOM-free soak test at target size; resources requests==limits.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.04", PG, "Memory", "No silent data loss under pressure",
      "The platform MUST NOT evict or drop graph data under resource pressure; it SHALL reject or "
      "queue work instead.",
      "A graph store must never silently lose data.",
      "Attempt to over-fill and confirm errors/back-pressure, not data loss.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.05", PG, "Storage & Persistence", "Durable, low-RPO persistence",
      "The platform SHALL persist to SSD-class durable storage with both point-in-time snapshots and "
      "a continuous append/write-ahead log (or equivalent), with capacity for log growth and "
      "rewrite/compaction.",
      "Snapshots give fast restart; a continuous log gives a low RPO.",
      "Show the persistence config and a kill-restart that recovers recent writes.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.06", PG, "Configuration", "Declarative, reproducible configuration",
      "All engine configuration SHALL be declarative and version-controlled and SHALL survive a "
      "restart; runtime-only mutations SHALL NOT be relied upon for durable configuration.",
      "Reproducible, GitOps-managed configuration is required for reliable operations.",
      "Config under version control; a restart preserves it.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.07", PG, "Availability & HA", "Automatic-failover high availability",
      "The platform SHALL provide redundant instances across failure domains with automatic failover "
      "within the agreed RTO and a disruption budget.",
      "Single-instance graph stores are a single point of failure.",
      "Demonstrate instance-loss failover within RTO; show the disruption budget.",
      MUST, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.PG.08", PG, "Scalability", "Read scale-out",
      "Read-heavy traffic SHALL be horizontally scalable via read replicas, with replication lag "
      "monitored and alerted.",
      "Read replicas absorb query load without affecting the write path.",
      "Show read routing to replicas and a replication-lag alert.",
      SHOULD, ("C.KGS",), ("T.AC.1",)),
    R("TR.PG.09", PG, "Scalability", "Query resource guard-rails",
      "Per-query memory, runtime, result-set size and concurrency/backlog SHALL be bounded so a "
      "single query cannot exhaust the instance.",
      "Unbounded graph queries can OOM or stall the engine.",
      "Submit a pathological query and confirm it is aborted, not the server.",
      MUST, ("C.KGS",), ("T.AC.1",)),
    R("TR.PG.10", PG, "Security", "Authenticated, encrypted, non-public access",
      "The platform SHALL enforce authentication, TLS in transit, network segmentation and a "
      "hardened runtime (non-root, read-only root filesystem, least capabilities), and SHALL NOT be "
      "publicly exposed.",
      "The store holds enterprise knowledge and must not be open or unauthenticated.",
      "No public exposure; auth + TLS enforced; pod security context reviewed.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.11", PG, "Observability", "Telemetry, slow-query insight & alerting",
      "The platform SHALL export throughput, latency, memory, replication-lag and slow-query metrics "
      "to the monitoring stack with dashboards and alerts.",
      "In-memory engines need early warning on memory and lag.",
      "Dashboards exist; a synthetic memory/lag alert fires.",
      MUST, ("C.KGS",), ("T.OO.5",)),
    R("TR.PG.12", PG, "Backup & DR", "Off-platform backup & DR",
      "The platform SHALL take scheduled backups to durable, off-platform object storage with a "
      "tested restore meeting the agreed RPO/RTO; where the store is a rebuildable projection, "
      "re-derivation from the canonical store is an acceptable recovery path.",
      "Local persistence is not a backup; off-platform copies survive cluster/zone loss.",
      "Show the backup job, a restore (or re-derivation), and a dated DR test.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.PG.13", PG, "Data Management", "Hybrid vector + graph retrieval (forward-looking)",
      "The platform SHOULD be able to store and query vector embeddings alongside the graph to "
      "support retrieval-augmented generation.",
      "Co-locating vectors with the graph enables hybrid semantic + structural retrieval.",
      "Create a vector index and run a similarity query.",
      MAY, ("C.KGS",), ("T.AC.6",)),

    # ============ Semantic Knowledge Graph Platform (agnostic) ========== #
    R("TR.SK.01", SK, "Memory", "Engine-aware memory partitioning",
      "Process memory SHALL be partitioned per the storage engine's caching model so the working set "
      "is cached without starving the engine (e.g. leave OS page-cache headroom for memory-mapped "
      "engines; bound managed heaps).",
      "Mis-tuned memory (oversized heap vs page cache) is the most common cause of poor query "
      "performance in semantic stores.",
      "Show the memory split and a resident-set-vs-heap dashboard; query-latency under load.",
      MUST, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.SK.02", SK, "Compute", "Safe concurrency / write model",
      "The platform SHALL enforce its storage engine's concurrency model (e.g. single-writer / "
      "multiple-reader) and SHALL prevent unsafe concurrent access that risks data corruption.",
      "Violating a single-writer model corrupts the database.",
      "Show the enforced write topology and single-attach storage.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.SK.03", SK, "Storage & Persistence", "Durable storage with maintenance headroom",
      "The platform SHALL use SSD-class durable storage sized for data growth plus compaction / "
      "maintenance overhead, with snapshots.",
      "Compaction/maintenance writes a fresh copy; insufficient headroom blocks it.",
      "Show storage sizing and a successful compaction/maintenance run.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.SK.04", SK, "Configuration", "Declarative dataset & endpoint configuration",
      "Datasets, query endpoints, indexes and query limits SHALL be defined declaratively and "
      "version-controlled, reproducible across restarts.",
      "Declarative, GitOps-able configuration is reproducible and auditable.",
      "Config in version control; endpoints/limits intact after restart.",
      MUST, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.SK.05", SK, "Availability & HA", "Writer redundancy & read replication",
      "The platform SHALL provide writer redundancy within the engine's model (active/standby or "
      "clustered) plus read replicas kept current via change-data replication.",
      "Single-writer engines still need writer failover and read scale-out.",
      "Demonstrate standby promotion and a replica serving from a change feed.",
      SHOULD, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.SK.06", SK, "Scalability", "Query tier scalability & limits",
      "The read/query tier SHALL be horizontally scalable and SHALL enforce query timeouts and "
      "result-size limits.",
      "Query answering must scale with data and be protected from runaway queries.",
      "Load test the read tier; confirm a long query times out.",
      SHOULD, ("C.KGS",), ("T.AC.1",)),
    R("TR.SK.07", SK, "Security", "Endpoint-segregated authentication & authorization",
      "Read, write/update and admin interfaces SHALL be separately authenticated and authorized; "
      "TLS SHALL be enforced; the platform SHALL NOT be publicly exposed and SHALL run hardened "
      "(non-root).",
      "Unprotected update/admin interfaces allow data tampering.",
      "Unauthenticated update is denied; TLS enforced; no public exposure.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.SK.08", SK, "Observability", "Telemetry & alerting",
      "The platform SHALL export query latency, request/error rates, engine memory/GC and "
      "storage-size metrics to the monitoring stack with dashboards and alerts.",
      "Engine memory/GC and query latency are the primary health signals.",
      "Dashboards exist; a synthetic alert fires.",
      MUST, ("C.KGS",), ("T.OO.5",)),
    R("TR.SK.09", SK, "Backup & DR", "Consistent backup & DR",
      "The platform SHALL take transactionally consistent backups to durable, off-platform object "
      "storage with a tested restore; as the canonical system of record it SHALL meet a stricter "
      "RPO/RTO than derived stores.",
      "Backups of the canonical store must be consistent and well-protected.",
      "Show a consistent backup, a restore and a dated DR test.",
      MUST, ("C.KGS",), ("T.OO.1",)),
    R("TR.SK.10", SK, "Data Management", "Semantic data-management features",
      "The platform SHALL isolate data per ontology/dataset (e.g. named graphs), SHOULD provide "
      "full-text/label indexing, and MAY support entailment/reasoning regimes per dataset.",
      "Dataset isolation, search and entailment underpin ontology use cases.",
      "Show dataset isolation, a text query and an entailment-dependent query.",
      SHOULD, ("C.KGS", "C.DOC"), ("T.AC.1", "T.DA.2")),

    # ============ Cloud-Native Platform (agnostic) ====================== #
    R("TR.CN.01", CN, "Networking", "Private, multi-zone managed Kubernetes",
      "The platform SHALL run on a private, network-isolated, multi-zone managed Kubernetes service "
      "with restricted control-plane access and a default-deny network policy.",
      "Private multi-zone clusters reduce attack surface and survive zone failure.",
      "Show private cluster config and default-deny NetworkPolicies.",
      MUST, ("C.KGS",), ()),
    R("TR.CN.02", CN, "Compute", "Workload-segregated, autoscaling compute pools",
      "Separate autoscaling compute pools SHALL be provided per workload profile (memory-optimised, "
      "general-purpose and batch) with scheduling labels/taints.",
      "Different workloads have different resource shapes and isolation needs.",
      "Show the pools, autoscaling bounds and labels/taints.",
      MUST, tuple(c.id for c in app.COMPONENTS), ()),
    R("TR.CN.03", CN, "Identity & Access", "Keyless workload identity & least privilege",
      "Workloads SHALL obtain cloud permissions via federated workload identity (no long-lived "
      "keys), with least-privilege access per workload.",
      "Keyless identity removes long-lived secret risk and enables least privilege.",
      "Show identity federation bindings and per-workload least-privilege policy.",
      MUST, ("C.KGS", "C.REPO"), ()),
    R("TR.CN.04", CN, "Secrets", "Centralized secret & key management",
      "Secrets and keys SHALL come from a managed secret store surfaced into the cluster; plaintext "
      "secrets MUST NOT live in manifests or images.",
      "Centralised, rotated secrets reduce credential sprawl and leakage.",
      "Show the secret integration; no plaintext secrets in manifests.",
      MUST, ("C.KGS", "C.RVE", "C.REPO"), ()),
    R("TR.CN.05", CN, "Storage & Persistence", "SSD storage class + volume snapshots",
      "Stateful workloads SHALL use an SSD-class dynamic storage class with a volume-snapshot "
      "capability and a retain policy for data volumes.",
      "Latency-sensitive stores need SSD; snapshots add a fast recovery path.",
      "Show the storage/snapshot classes and a successful snapshot.",
      SHOULD, ("C.KGS",), ("T.OO.1",)),
    R("TR.CN.06", CN, "Security", "Supply-chain assurance",
      "Container images SHALL come from a trusted registry, be vulnerability-scanned, signed and "
      "admission-controlled, and be pinned by digest.",
      "Prevents unverified or vulnerable images from running.",
      "Show signing/scanning/admission policy and an admission denial of an unsigned image.",
      SHOULD, (), ()),
    R("TR.CN.07", CN, "Networking", "Managed ingress with TLS & WAF",
      "All access SHALL traverse a managed ingress/load-balancer with TLS and a web application "
      "firewall; data/graph endpoints SHALL NOT be directly internet-exposed.",
      "Central ingress provides TLS, WAF and consistent routing/authz.",
      "Show ingress, TLS and WAF policy; stores are not internet-reachable.",
      MUST, ("C.KGS", "C.VIZ", "C.DOC"), ("T.AC.1",)),
    R("TR.CN.08", CN, "Operations", "GitOps, environment isolation & cluster backup",
      "Cluster and workload configuration SHALL be delivered declaratively via GitOps across "
      "isolated environments with resource quotas, and cluster state SHALL be backed up.",
      "Declarative, audited, reproducible operations with environment isolation.",
      "Show the GitOps repo, namespace quotas and a cluster-state backup plan.",
      SHOULD, tuple(c.id for c in app.COMPONENTS), ()),
    R("TR.CN.09", CN, "Observability", "Unified observability with SLOs",
      "A unified metrics/logs/traces stack SHALL collect telemetry for all components with SLO "
      "dashboards and an on-call alert-routing policy.",
      "A single pane of glass is required to operate to SLOs.",
      "Show dashboards, SLOs and alert routing.",
      MUST, tuple(c.id for c in app.COMPONENTS), ("T.OO.5",)),

    # ============ Platform Services (agnostic) ========================== #
    R("TR.SP.01", SP, "Data Management", "Canonical → projection synchronization",
      "A synchronisation service SHALL keep the derived property-graph projection consistent with "
      "the canonical semantic graph via a change-data feed, with a documented mapping and a "
      "reconciliation/repair job.",
      "The dual-store design needs a defined, auditable sync so the projection never silently "
      "diverges from the canonical semantics.",
      "Show the mapping; a canonical change appears in the projection within SLA.",
      MUST, ("C.KGS",), ("T.OO.1", "T.AC.1")),
    R("TR.SP.02", SP, "Operations", "Automated ontology delivery (OntoOps)",
      "An automated pipeline SHALL build, validate (constraint + competency-question tests) and "
      "release ontologies from source control, then deploy them to the stores.",
      "Automated, tested releases are the L2 'extensible platform' way of working.",
      "Show a pipeline run that validates and deploys an ontology change.",
      SHOULD, ("C.REPO", "C.RVE"), ("T.OO.2", "T.QV.1", "T.QV.2")),
    R("TR.SP.03", SP, "Storage & Persistence", "Durable artifact / object storage",
      "Durable object storage SHALL hold ontology releases, published documentation and store "
      "backups, with versioning, lifecycle and multi-region resilience.",
      "Central durable artefact storage underpins releases, docs and DR.",
      "Show the storage layout, lifecycle and versioning policies.",
      MUST, ("C.REPO", "C.DOC"), ("T.OO.2", "T.AC.3")),
    R("TR.SP.04", SP, "Identity & Access", "Enterprise SSO for human-facing tools",
      "Human-facing components SHALL authenticate via enterprise OIDC SSO with role-based access.",
      "Consistent SSO and RBAC across the toolchain is required for governance.",
      "Show OIDC integration and an RBAC denial.",
      SHOULD, ("C.AUTH", "C.VOCAB", "C.GLOSS", "C.VIZ", "C.DOC"), ()),
    R("TR.SP.05", SP, "Operations", "Isolated reasoning / validation compute",
      "Reasoning/validation workloads SHALL run as ephemeral, resource-bounded batch jobs isolated "
      "from the online stores.",
      "Reasoning is bursty and resource-heavy; isolating it protects the online stores.",
      "Show a batch job and a completed validation run.",
      SHOULD, ("C.RVE",), ("T.RI.1", "T.QV.1", "T.QV.2")),
    R("TR.SP.06", SP, "Operations", "Stateless visualization & documentation hosting",
      "Visualisation and generated documentation SHALL be served as stateless workloads / static "
      "sites behind the gateway and SSO.",
      "A read-mostly, stateless presentation tier decouples consumers from the stores.",
      "Show the hosted viz and docs endpoints behind SSO.",
      MAY, ("C.VIZ", "C.DOC"), ("T.AC.2", "T.AC.3")),
    R("TR.SP.07", SP, "Scalability", "Embedding / GraphRAG enablement (forward-looking)",
      "An optional, isolated embedding/GraphRAG service MAY populate the property-graph vector index "
      "to ground AI features without affecting core store SLOs.",
      "Prepares the L5 'LLM/AI augmentation' capability without compromising L2 stability.",
      "Show an isolated deployment populating a vector index.",
      MAY, ("C.KGS",), ("T.AC.6",)),
]
REQUIREMENT_BY_ID = {r.id: r for r in REQUIREMENTS}


# --------------------------------------------------------------------------- #
# Technology mappings (the separate, technology-specific layer)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Mapping:
    req_id: str
    technology: str       # T_FALKOR | T_FUSEKI | T_GCP
    realization: str      # how the technology satisfies the agnostic requirement
    specifics: str        # concrete GCP-context config / services / parameters


def M(*a) -> Mapping:
    return Mapping(*a)


MAPPINGS: list[Mapping] = [
    # ---- FalkorDB ↔ Property Graph Platform (on GCP) ---- #
    M("TR.PG.01", T_FALKOR,
      "FalkorDB is an in-memory Redis-module graph engine; it gets a dedicated GKE memory-optimised "
      "node pool, isolated by taints/affinity from JVM and batch workloads.",
      "GKE node pool n2-highmem/m1; node taint dedicated=falkordb:NoSchedule + tolerations + zone "
      "anti-affinity; nodeSelector workload=memory-optimised."),
    M("TR.PG.02", T_FALKOR,
      "Concurrency and per-query parallelism are set as load-time module args.",
      "THREAD_COUNT = allocatable vCPUs; OMP_THREAD_COUNT = 1–2 (GraphBLAS/OpenMP) for online query "
      "isolation."),
    M("TR.PG.03", T_FALKOR,
      "The whole graph is RAM-resident; pod memory holds graph + working set + ≥30% headroom for "
      "GraphBLAS matrices, NODE_CREATION_BUFFER and RDB fork copy-on-write, with Guaranteed QoS.",
      "Pod resources requests==limits (e.g. 16Gi/16Gi at Standard tier); capacity model in "
      "mapping/falkordb-gke.md."),
    M("TR.PG.04", T_FALKOR,
      "Redis eviction is disabled so graph keys are never dropped.",
      "redis.conf maxmemory-policy noeviction."),
    M("TR.PG.05", T_FALKOR,
      "Persistence uses Redis RDB snapshots + AOF on an SSD PVC sized ≥3× the RDB.",
      "appendonly yes, appendfsync everysec; RDB save schedule; storageClass premium-rwo "
      "(pd-ssd/hyperdisk); PVC ≥ 3× RDB."),
    M("TR.PG.06", T_FALKOR,
      "Load-time parameters are baked into module args / ConfigMap under GitOps; runtime "
      "GRAPH.CONFIG SET is NOT persisted and is not relied upon.",
      "--loadmodule falkordb.so THREAD_COUNT … in Helm values.extraFlags; managed via Config "
      "Sync/Argo."),
    M("TR.PG.07", T_FALKOR,
      "One primary + ≥1 replica with automatic failover via Redis Sentinel (≥3) or the KubeBlocks "
      "operator, across zones, with a PodDisruptionBudget.",
      "Bitnami Redis chart architecture=replication + sentinel.enabled (quorum 2, 3 replicas) OR "
      "KubeBlocks Cluster; pdb.minAvailable=1; topologySpreadConstraints by zone."),
    M("TR.PG.08", T_FALKOR,
      "Reads are routed to replicas via GRAPH.RO_QUERY; replication lag is monitored.",
      "RO ClusterIP service to replicas; INFO replication lag scraped to Managed Prometheus."),
    M("TR.PG.09", T_FALKOR,
      "Query guard-rails bound memory, runtime, result size and backlog.",
      "QUERY_MEM_CAPACITY, TIMEOUT_MAX/TIMEOUT_DEFAULT, RESULTSET_SIZE, MAX_QUEUED_QUERIES (load-time "
      "args)."),
    M("TR.PG.10", T_FALKOR,
      "Auth via Redis ACL/requirepass from Secret Manager, TLS in transit, ClusterIP + NetworkPolicy "
      "(no public IP), non-root + read-only FS, Bolt port disabled.",
      "auth.existingSecret (External Secrets); tls.enabled; service.type ClusterIP; networkPolicy; "
      "BOLT_PORT -1; securityContext runAsNonRoot/readOnlyRootFilesystem."),
    M("TR.PG.11", T_FALKOR,
      "Redis/INFO + GRAPH.INFO metrics via a Redis exporter to Managed Prometheus with dashboards "
      "and alerts.",
      "metrics.enabled + serviceMonitor; alerts on used_memory>80%, replication lag, failover."),
    M("TR.PG.12", T_FALKOR,
      "RDB/AOF (or GRAPH.COPY exports) backed up to dual-region GCS; alternatively re-projected from "
      "Fuseki since FalkorDB is a projection.",
      "CronJob → GCS dual-region bucket (versioned); restore runbook OR re-run TS.SYNC projection."),
    M("TR.PG.13", T_FALKOR,
      "FalkorDB native vector indexing stores embeddings alongside the graph for GraphRAG.",
      "Vector index on node/edge properties; populated by the optional embedding service (TR.SP.07)."),

    # ---- Fuseki ↔ Semantic Knowledge Graph Platform (on GCP) ---- #
    M("TR.SK.01", T_FUSEKI,
      "Fuseki (TDB2) uses memory-mapped files, so the JVM heap is bounded and the pod memory limit "
      "is set well above the heap to leave OS page-cache headroom.",
      "JAVA_OPTIONS -Xmx4–8g -XX:+UseG1GC; pod memory limit 2–4× heap (e.g. heap 4Gi / pod 16Gi)."),
    M("TR.SK.02", T_FUSEKI,
      "TDB2 is single-writer / multiple-reader on a 64-bit JVM; exactly one JVM attaches a TDB2 "
      "directory, enforced by a single-writer StatefulSet on a ReadWriteOnce volume.",
      "StatefulSet replicas=1 (writer); PVC accessModes [ReadWriteOnce]; standby fenced before "
      "attach."),
    M("TR.SK.03", T_FUSEKI,
      "TDB2 lives on an SSD PVC sized ≥2× the live DB to allow online compaction; volume snapshots "
      "enabled.",
      "storageClass premium-rwo; PVC ≥2× DB; VolumeSnapshotClass; tdb2 compaction."),
    M("TR.SK.04", T_FUSEKI,
      "Datasets/endpoints/indexes/timeouts are defined by a version-controlled assembler config "
      "on a persistent FUSEKI_BASE.",
      "config.ttl (tdb2:DatasetTDB2) from ConfigMap; FUSEKI_BASE on PVC; fuseki:queryTimeout; split "
      "query/update/admin endpoints."),
    M("TR.SK.05", T_FUSEKI,
      "A single active writer with a warm standby, plus read replicas kept current by RDF Delta "
      "change logs.",
      "Writer StatefulSet + standby (scaled 0→1 on failover, fenced); RDF Delta feed → read-only "
      "Fuseki replicas; PDB + zone anti-affinity."),
    M("TR.SK.06", T_FUSEKI,
      "Stateless read-only Fuseki replicas behind the gateway scale query load; query timeouts and "
      "result limits are enforced.",
      "RO replica Deployment behind Gateway; fuseki:queryTimeout '30000,60000'; result limits."),
    M("TR.SK.07", T_FUSEKI,
      "AuthN/Z via Apache Shiro and/or an OIDC proxy / IAP; read vs update vs admin endpoints are "
      "separated; TLS at the gateway; ClusterIP only.",
      "shiro.ini roles and/or IAP; endpoints sparql(read)/update/$(admin); Gateway TLS; "
      "ClusterIP + NetworkPolicy; non-root."),
    M("TR.SK.08", T_FUSEKI,
      "Fuseki Prometheus endpoint + JVM/GC metrics to Managed Prometheus with dashboards and alerts.",
      "/$/metrics scraped; dashboards heap/GC, query latency, 5xx; alerts on heap>85%, error spikes, "
      "disk<25%."),
    M("TR.SK.09", T_FUSEKI,
      "Transactionally consistent backups via tdb2.tdbbackup or the /$/backup endpoint to dual-region "
      "GCS; stricter RPO/RTO as the canonical store.",
      "Scheduled /$/backup → GCS dual-region (versioned); restore-to-fresh-PVC runbook; RPO≤1h."),
    M("TR.SK.10", T_FUSEKI,
      "One named graph per ontology/release; optional Jena text (Lucene) index; optional RDFS/OWL "
      "entailment via the assembler.",
      "Named graphs; text:TextIndexLucene on rdfs:label; entailment regime per dataset in config.ttl."),

    # ---- GCP ↔ Cloud-Native Platform (shared by both stores) ---- #
    M("TR.CN.01", T_GCP, "Private, VPC-native, regional GKE.",
      "Private nodes, authorized control-plane networks, default-deny NetworkPolicy."),
    M("TR.CN.02", T_GCP, "Segregated GKE node pools per workload profile.",
      "Pools: memory-optimised (FalkorDB), general-purpose (Fuseki/services), batch (reasoning); "
      "cluster autoscaler; labels/taints."),
    M("TR.CN.03", T_GCP, "GKE Workload Identity, no exported SA keys.",
      "KSA↔GSA bindings; least-privilege IAM (e.g. only backup pods write their GCS bucket)."),
    M("TR.CN.04", T_GCP, "Secret Manager surfaced via External Secrets / CSI.",
      "ExternalSecret / Secret Manager CSI; CMEK; no plaintext in manifests."),
    M("TR.CN.05", T_GCP, "SSD storage classes + volume snapshots.",
      "StorageClass premium-rwo (pd-ssd/hyperdisk); VolumeSnapshotClass; reclaimPolicy Retain."),
    M("TR.CN.06", T_GCP, "Artifact Registry + scanning + Binary Authorization.",
      "Images pinned by digest; vulnerability scanning; signed-image admission in prod namespaces."),
    M("TR.CN.07", T_GCP, "Gateway API + Cloud Load Balancing + managed TLS + Cloud Armor.",
      "HTTPRoute + managed certs + Cloud Armor WAF; graph/SPARQL endpoints internal only."),
    M("TR.CN.08", T_GCP, "GitOps + environment namespaces + Backup for GKE.",
      "Config Sync/Argo CD; dev/test/prod namespaces with ResourceQuota/LimitRange; Backup for GKE."),
    M("TR.CN.09", T_GCP, "Managed Service for Prometheus + Cloud Logging/Trace + Grafana.",
      "Single observability stack; SLO dashboards; on-call alert routing."),

    # ---- GCP ↔ Platform Services (shared) ---- #
    M("TR.SP.01", T_GCP,
      "An RDF Delta change feed drives a projection/sync service that maps the canonical RDF graph "
      "into the FalkorDB property graph, with a reconciliation job.",
      "RDF Delta → sync service (RDF→LPG mapping) → FalkorDB; nightly reconcile Job; freshness ≤5min."),
    M("TR.SP.02", T_GCP,
      "OntoOps pipeline on Cloud Build / GitHub Actions: ROBOT + pySHACL + competency-question tests, "
      "release to GCS, deploy to Fuseki, trigger FalkorDB projection.",
      "Cloud Build triggers; ephemeral Fuseki for CQ tests; deploy named graph; invoke TS.SYNC."),
    M("TR.SP.03", T_GCP, "GCS buckets for releases, docs and backups.",
      "Dual-region buckets; object versioning; lifecycle; per-purpose IAM."),
    M("TR.SP.04", T_GCP, "Enterprise OIDC SSO via IAP / Identity Platform + RBAC.",
      "IAP in front of human-facing tools; roles reader/editor/steward/admin."),
    M("TR.SP.05", T_GCP, "Kubernetes Jobs on a batch node pool for reasoning/validation.",
      "ROBOT/HermiT-ELK (where licensed)/pySHACL as bounded Jobs; results back to stores."),
    M("TR.SP.06", T_GCP, "Viz (WebVOWL/Ontodia) and docs (Widoco/pyLODE) on Cloud Run / GCS+CDN.",
      "Stateless services behind Gateway + IAP; docs as static site on GCS+CDN."),
    M("TR.SP.07", T_GCP, "Optional embedding/GraphRAG service populating the FalkorDB vector index.",
      "Isolated Deployment; writes vector index; does not share FalkorDB SLO budget."),
]
MAPPINGS_BY_REQ: dict[str, list[Mapping]] = {}
for _m in MAPPINGS:
    MAPPINGS_BY_REQ.setdefault(_m.req_id, []).append(_m)


# --------------------------------------------------------------------------- #
# Accessors / validation
# --------------------------------------------------------------------------- #
def requirements_for(platform: str) -> list[Requirement]:
    return [r for r in REQUIREMENTS if r.platform == platform]


def mappings_for_tech(tech: str) -> list[Mapping]:
    return [m for m in MAPPINGS if m.technology == tech]


def validate_model() -> list[str]:
    problems: list[str] = []
    comp_ids = {c.id for c in app.COMPONENTS}
    cap_ids = set()
    try:
        from ontology_engineering_capabilities import CAPABILITY_BY_ID
        cap_ids = set(CAPABILITY_BY_ID)
    except Exception:
        pass
    for r in REQUIREMENTS:
        if r.platform not in PLATFORMS:
            problems.append(f"{r.id}: bad platform {r.platform!r}")
        if r.area not in AREAS:
            problems.append(f"{r.id}: bad area {r.area!r}")
        if r.priority not in (MUST, SHOULD, MAY):
            problems.append(f"{r.id}: bad priority {r.priority!r}")
        for c in r.components:
            if c not in comp_ids:
                problems.append(f"{r.id}: unknown component {c!r}")
        if cap_ids:
            for cap in r.capabilities:
                if cap not in cap_ids:
                    problems.append(f"{r.id}: unknown capability {cap!r}")
        # every requirement must have at least one technology mapping
        if r.id not in MAPPINGS_BY_REQ:
            problems.append(f"{r.id}: no technology mapping")
    for m in MAPPINGS:
        if m.req_id not in REQUIREMENT_BY_ID:
            problems.append(f"mapping for unknown requirement {m.req_id!r}")
        if m.technology not in (T_FALKOR, T_FUSEKI, T_GCP):
            problems.append(f"{m.req_id}: bad technology {m.technology!r}")
    # the expected tech per platform category
    for r in REQUIREMENTS:
        want = PLATFORM_TECH[r.platform]
        got = {m.technology for m in MAPPINGS_BY_REQ.get(r.id, [])}
        if want not in got:
            problems.append(f"{r.id}: expected a {want} mapping, got {got or 'none'}")
    for s in TECH_SERVICES:
        for c in s.serves_components:
            if c not in comp_ids:
                problems.append(f"{s.id}: unknown component {c!r}")
    for n in TECH_NODES:
        for sid in n.realizes:
            if sid not in TECH_SERVICE_BY_ID:
                problems.append(f"{n.id}: realizes unknown service {sid!r}")
        for h in n.hosted_on:
            if h not in TECH_NODE_BY_ID:
                problems.append(f"{n.id}: hosted_on unknown node {h!r}")
    return problems


if __name__ == "__main__":
    from collections import Counter
    probs = validate_model()
    print(f"tech services : {len(TECH_SERVICES)}")
    print(f"tech nodes    : {len(TECH_NODES)}")
    print(f"requirements  : {len(REQUIREMENTS)}  {dict(Counter(r.platform for r in REQUIREMENTS))}")
    print(f"by priority   : {dict(Counter(r.priority for r in REQUIREMENTS))}")
    print(f"mappings      : {len(MAPPINGS)}  {dict(Counter(m.technology for m in MAPPINGS))}")
    print(f"problems      : {len(probs)}")
    for p in probs:
        print("  -", p)
