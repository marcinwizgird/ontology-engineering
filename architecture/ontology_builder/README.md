# Ontology Builder

The component of the **Knowledge Graph Agentic Platform** that merges the
capabilities of **VocBench 3 / Semantic Turkey**, **WebProtégé** and **Protégé
Desktop** into one governed, agentic ontology development environment —
**Python backend, Python AI agents, React UI, Apache Jena Fuseki as the
canonical store**.

**Status:** design set, pre-implementation. The feature model is executable and
validates; the documents below are generated from it or hand-written against it.

---

## Document set

| Doc | Covers |
|---|---|
| [FEATURE_EXTRACTION.md](FEATURE_EXTRACTION.md) *(generated)* | The 141 features extracted from the three platforms' source code, each with the exact service, handler, enum or extension point it came from |
| [CAPABILITY_MAPPING.md](CAPABILITY_MAPPING.md) *(generated)* | Two-way mapping between features and the Ontology Engineering Capability Model, with EKGF-level coverage analysis |
| [GOVERNANCE_FOUNDATION.md](GOVERNANCE_FOUNDATION.md) | **The crucial piece** — project management and governance over Fuseki: capability grammar, roles/bindings/ACLs, change tracking, staging graphs, the validation workflow, the named-graph layout |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Target architecture: principles, component view, backend package layout, stack choices, the agent layer, the React client, known hard parts |
| [ROADMAP.md](ROADMAP.md) | Nine phases (P0–P8) with workstreams, exit criteria, risks, decisions taken and decisions still open |
| [`feature_model.py`](feature_model.py) | The machine-readable model — source tools, feature areas, 141 features with evidence, capability mapping, phase, priority, target module, reuse and dependencies |
| [`build_docs.py`](build_docs.py) | Regenerates the two generated documents and the Mermaid artifacts |
| [`spike_crudv/`](spike_crudv/) | **Working code** — VocBench's CRUDV capability algebra ported to dependency-free Python, 52 tests passing. The reference implementation for `OB.GOV.02` |
| [`spike_reasoners/`](spike_reasoners/) | **Working code** — the multi-reasoner framework: declared capabilities, profile-aware completeness, per-operation routing with explicit degradation, and a differential harness. 25 tests passing. Reference implementation for `OB.RSN.01`–`04` and `OB.EXT.05` |

---

## The one-paragraph version

VocBench 3 is the only one of the three that treats **projects, roles and
editorial workflow** as first-class; WebProtégé is the only one with a clean
**web sharing model, declarative forms and axiom-level revision history**;
Protégé Desktop is the only one with **deep OWL authoring, DL reasoning with
explanations and serious refactoring**. The Ontology Builder takes VocBench's
governance spine, WebProtégé's forms and role inheritance, and Protégé's
authoring depth — then adds the two things **none** of them has: **competency
questions as executable tests**, and an **agent layer that is safe by
construction** because agents are ordinary principals whose work lands in the
same validation queue a junior editor's does.

---

## What was extracted, and from where

Read from source, not from documentation:

| Platform | Repository | Measured |
|---|---|---|
| **VocBench 3** | `bitbucket.org/art-uniroma2/vocbench3` | 60 service classes · **781 server operations** · **330 guarded actions** across 7 capability areas · 15 extension points · 30 resource-view sections · 38 integrity checks |
| **WebProtégé** | `github.com/protegeproject/webprotege` + ~15 microservice repos | **145 action handlers** · 53 built-in capabilities · 15 inheriting roles · forms descriptor model · entity CRUD kits |
| **Protégé Desktop** | `github.com/protegeproject/protege` | **24 OSGi extension points** · 7 workspace tabs · 51 view components · 132 menu actions |

> The Semantic Turkey **server** repo requires Bitbucket credentials and could
> not be cloned. Its contract was recovered in full from the VocBench 3 client,
> which mirrors it operation by operation, plus the peer-reviewed architecture
> description in the Semantic Web Journal paper. Nothing here rests on
> server-side code that was not observable.

---

## Coverage against the capability model

**42 of 44** capabilities in
[`ontology_engineering_capabilities/`](../../ontology_engineering_capabilities/)
are realised by at least one Builder feature.

| EKGF level | Capabilities | Realised | Every capability has a feature by | Substantially delivered by |
|---|---:|---:|---|---|
| L1 EKG Initiation | 5 | 5 | P4 | P3 |
| L2 Extensible Platform | 14 | 13 | P3 | P4 |
| L3 Enterprise Ready | 15 | 15 | P6 | P6 |
| L4 Strategic Asset | 7 | 6 | P3 | P7 |
| L5 Operational Ecosystem | 3 | 3 | P2 | P8 |

The two columns differ on purpose. "Every capability has a feature by" is
computed from the model — the phase at which the last capability at that level
first acquires *any* realising feature. It runs early because foundational work
touches high-level capabilities: machine accounts (P0) are the first feature
under `T.AC.6` *LLM/AI Augmentation*, but they are not that capability
delivered. "Substantially delivered by" is the judgement call, and it is the
number to plan against.

The two unrealised — `B.SG.4` Funding & Investment Management and `B.VP.1`
Value Case & Benefits Realization — are deliberately out of scope: they belong
to the enterprise's own portfolio and value systems, which the Builder feeds
with project inventory and quality KPIs rather than replacing.

---

## A note on the brief

The request named *"project management and governance capabilities **from
Fuseki**"*. Fuseki has none — it is a SPARQL server with datasets, named graphs
and a thin access filter; it has no concept of a project, a user, a role, an
editorial workflow or a change history. Those concepts come from **VocBench 3 /
Semantic Turkey**. This design therefore reads the brief as *implement
VocBench-class project management and governance, with Fuseki as the canonical
store underneath* — which is what
[GOVERNANCE_FOUNDATION.md](GOVERNANCE_FOUNDATION.md) specifies, and what P0 and
P1 of the roadmap build before any editing feature ships. If the intent was
narrower — Fuseki's own dataset and endpoint administration only — the
governance work collapses to a fraction of its current size; say so and the
plan will be re-cut.

---

## Regenerating

```bash
python architecture/ontology_builder/feature_model.py   # validate (expect: problems 0)
python architecture/ontology_builder/build_docs.py      # regenerate the generated docs
```

`build_docs.py` refuses to write if the model is inconsistent, so a broken
mapping cannot reach the documents.

---

## Relationship to the rest of the repository

* **Requirements** — [`ontology_engineering_capabilities/`](../../ontology_engineering_capabilities/)
* **L2 application architecture** — [`../ARCHITECTURE.md`](../ARCHITECTURE.md);
  the Builder replaces its *technology candidates* ("Protégé", "VocBench") for
  `C.AUTH`, `C.VOCAB`, `C.REPO` and part of `C.RVE` with a build
* **Infrastructure contract** — [`../technical architecture/`](../technical%20architecture/)
  (`TR.SK.*` Fuseki, `TR.PG.*` FalkorDB, `TR.CN.*`/`TR.SP.*` GCP)
* **Read-only agent** — [`../ontology_assistant/`](../ontology_assistant/),
  adopted wholesale as `OB.AGT.02`
* **Write-safety core, reused not replaced** — `src/Ontology Modeler/`
  (`FusekiClient`, `GraphSynchronizer`, `guard()`, projection/merge,
  `StructureExplorer`)
* **Seed pipelines** — `src/Ontology Enricher/` (reasoning patterns, FIBO
  mappings), `src/Ontology Converter/` (RDF→LPG), `bottomup_ontology/`
  (text→ontology, becomes `OB.S2R.02`)
