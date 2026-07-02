# Architecture — Level-2 Application Architecture

Logical **application architecture** (ArchiMate application layer) providing the
application **services** that support the **14 capabilities at EKGF maturity
Level 2 — "Extensible Platform"** of the
[Ontology Engineering Capability Model](../ontology_engineering_capabilities).

It is the answer to: *"which application services and components do we need to
operate the ontology practice as a reusable platform (L2)?"*

## Contents

| File | Purpose |
|---|---|
| `app_architecture_model.py` | The model: 6 application domains, 14 application services (one per L2 capability), 10 application components, 12 data objects, and ArchiMate relations. Validates that every served capability is really Level 2. |
| `app_arch_generators.py` | Shared layout + ArchiMate **SVG**, matplotlib **PNG** twin, **Mermaid** view, and the architecture **documentation** generator. |
| `build_architecture.py` | Regenerates all artifacts into `artifacts/` and writes `ARCHITECTURE.md`. |
| `ARCHITECTURE.md` | The generated architecture description (mappings, catalogues, rationale, scope). |
| `artifacts/app_architecture.svg` | **ArchiMate application architecture diagram** (4 layers × 6 domains). |
| `artifacts/app_architecture.png` | Raster twin of the diagram. |
| `artifacts/app_architecture.mmd` | Mermaid view of the same model. |

## The diagram

Four ArchiMate layers, six application domains (columns):

```
Capabilities (L2)      ▲ served by
Application Services   ▲ realized by
Application Components ⋯ accesses
Data Objects
```

* **Serving** — service → capability, component → component (internal wiring).
* **Realization** — component → service.
* **Access** — component ⟷ data object (read/write).

Domains: **MOD** Modelling & Authoring · **VOC** Vocabulary & Glossary ·
**RVT** Reasoning, Validation & Testing · **KGP** Knowledge Graph Platform ·
**ACP** Access & Publishing · **ENB** Enterprise Enablement.

## Regenerate

```bash
python architecture/build_architecture.py
```

The model imports the capability definitions from
`ontology_engineering_capabilities`, so the architecture stays in sync and the
build fails if a service is wired to a non-Level-2 capability.

## Scope

Limited to Level 2 ("Extensible Platform"). Level-1 prerequisites
(conceptualisation, competency questions) are assumed; L3–L5 capabilities
(CI/CD, federation, observability, LLM augmentation, entitlements) are out of
scope and would extend this architecture. Technology candidates listed per
component are illustrative, not prescriptive.
