# Technical Architecture — Ontology Engineering platform

Technology-layer (ArchiMate) architecture and **technical requirements** for the
infrastructure teams provisioning the technology components that realise the
**Level-2 (Extensible Platform)** application architecture
([`../`](../ARCHITECTURE.md)) and the
[capability model](../../ontology_engineering_capabilities).

Organised as **two separate layers**:

1. **Technology-agnostic requirements** — *what* any conforming product must
   provide (no vendor or cloud-product names).
2. **Technology mappings** — *how* **FalkorDB** and **Apache Jena Fuseki**, on
   **GCP/GKE**, satisfy each agnostic requirement.

> **Dual-store design.** The `C.KGS` component is realised by **both** a canonical
> **semantic knowledge graph** (Property Graph Platform → FalkorDB is a *derived
> projection*) and the canonical **semantic graph** (Semantic Knowledge Graph
> Platform → Fuseki). A projection/sync service (`TR.SP.01`) keeps them consistent.

## Layer 1 — agnostic requirements

| File | What |
|---|---|
| `REQUIREMENTS_CATALOG.md` | **Technology-agnostic** requirements (39), grouped by platform category, with rationale + verification. *Generated.* |
| `TRACEABILITY.md` | Capability ↔ application component ↔ technology service ↔ requirement. *Generated.* |

| Agnostic category | Reqs | IDs |
|---|---|---|
| **Property Graph Platform** | 13 | `TR.PG.01–13` |
| **Semantic Knowledge Graph Platform** | 10 | `TR.SK.01–10` |
| **Cloud-Native Platform** | 9 | `TR.CN.01–09` |
| **Platform Services** | 7 | `TR.SP.01–07` |

Priorities (RFC-2119): 25 MUST, 11 SHOULD, 3 MAY.

## Layer 2 — technology mappings (GCP context)

| File | Maps |
|---|---|
| `mapping/MAPPING_FALKORDB_GCP.md` | `TR.PG.*` → **FalkorDB** on GCP. *Generated.* |
| `mapping/MAPPING_FUSEKI_GCP.md` | `TR.SK.*` → **Fuseki** on GCP. *Generated.* |
| `mapping/MAPPING_PLATFORM_GCP.md` | `TR.CN.*` + `TR.SP.*` → **GCP** services (shared by both stores). *Generated.* |
| `mapping/falkordb-gke.md` | FalkorDB deep design narrative (sizing, HA topology, config params, security, observability, backup/DR, SLOs, acceptance). |
| `mapping/fuseki-gke.md` | Fuseki deep design narrative (memory/mmap model, single-writer HA, assembler config, backup/DR, SLOs, acceptance). |
| `mapping/supporting-components.md` | Proposal for the remaining components on GCP. |

## Other contents

| Path | What |
|---|---|
| `artifacts/technology_architecture.svg` / `.png` | ArchiMate **technology architecture** diagram (the GCP deployment/realisation view). *Generated.* |
| `deploy/` | Starter, illustrative Helm values / K8s manifests for FalkorDB and Fuseki. |
| `tech_architecture_model.py` | Single source: agnostic `REQUIREMENTS` + `MAPPINGS` + technology elements. |
| `tech_arch_generators.py`, `build_tech_architecture.py` | Generators + build driver. |

## Regenerate

```bash
python "architecture/technical architecture/build_tech_architecture.py"
```

Writes the agnostic catalogue, the three mapping documents, the traceability and
the diagram from `tech_architecture_model.py` — so the agnostic requirements and
their FalkorDB/Fuseki/GCP mappings never drift. The deep design narratives under
`mapping/` and the `deploy/` artifacts are hand-authored and reference the IDs.

## How the pieces relate

```
capability model  ──▶  L2 application architecture  ──▶  agnostic tech requirements  ──▶  FalkorDB / Fuseki / GCP mappings
(…_capabilities)            (architecture/)              (REQUIREMENTS_CATALOG.md)            (mapping/)
```

## Scope

Targets EKGF **Level 2**. Forward-looking items (GraphRAG/embeddings `TR.PG.13`/`TR.SP.07`,
write-sharding, federation) are flagged and deferred to L3–L5. The agnostic
requirements are vendor-neutral; the mappings name concrete products and GCP
services.
