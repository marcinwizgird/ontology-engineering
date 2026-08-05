# Ontology Assistant Agent — Functional Design

Design set for the **Ontology Assistant Agent (OAA)**: a read-only, conversational and
tool-callable agent that helps people *comprehend* the ontologies held in this platform,
*locate* the concepts and triples relevant to a question, *answer* questions about what the
ontology asserts, *explain* why with citations, and understand *how the ontology can be used*.

**Status:** functional design (brainstorm-grade, pre-implementation). No code yet.
**Scope assumption:** FIBO module definitions are loaded in **both** stores — Apache Fuseki
(canonical RDF/OWL, ~162 named graphs) and FalkorDB (derived property-graph projection).

## Document set

| Doc | Covers |
|---|---|
| [FUNCTIONAL_DESIGN.md](FUNCTIONAL_DESIGN.md) | Scope, the five capabilities, the governing store-split principle, the artifact object model, agent topology |
| [RETRIEVAL_PIPELINE.md](RETRIEVAL_PIPELINE.md) | The six-stage retrieval funnel, intent taxonomy, routing table, ranking and budgeting |
| [TOOL_CATALOG.md](TOOL_CATALOG.md) | Every agent tool with signature and backing store, plus guardrails |
| [STORE_PREREQUISITES.md](STORE_PREREQUISITES.md) | What must change in the Fuseki and FalkorDB projections before the agent can work well |
| [EVALUATION.md](EVALUATION.md) | Competency-question gold set, retrieval and faithfulness metrics, test harness |
| [ROADMAP.md](ROADMAP.md) | Phasing P0–P5 and the open decisions to settle first |

## The one-paragraph version

The OAA sits over a polyglot semantic layer. **FalkorDB proposes** — fuzzy, ranked,
sub-millisecond suggestions of *which concepts might be relevant*. **Fuseki proves** — the
exact, cite-able axioms that actually justify an answer. Because the property-graph
projection preserves only ~18–23% of a FIBO module's triples, no assertion ever reaches the
user unless it was read from Fuseki; Falkor output is a routing hint, never evidence. Around
that split sit a hybrid retrieval funnel (lexical + vector + structural anchoring, graph
expansion, authoritative hydration, informativeness ranking), four durable artifacts
(Concept Card, Evidence Bundle, Module Digest, Answer), a deterministic verbaliser, and a
grounding critic that rejects any sentence not traceable to a retrieved triple.

## Relationship to the existing specification

`docs/Ontology Assistant Agent/ontology-assistant-specification.md` (TD-OAA-2026-V1) is the
prior art. Roughly half of it specifies a different product — Ontop, R2RML mappings,
text-to-SQL compilation, SMQ intermediate representations, SQL guardrails — i.e. a *data
access* layer over instance data. This design set covers only the **ontology comprehension
and retrieval** agent. Carried forward from v1: the polyglot store split (§2), the
verbalisation function (§3.4), and the context-hygiene guidance (§6). Deferred to a separate
"Semantic Access Layer" design: §4.2 and most of §5. See
[ROADMAP.md](ROADMAP.md#p5--deferred-semantic-access-layer).

## Grounding in the existing codebase

This design reuses, and does not duplicate, what is already built:

- `src/Ontology Modeler/ontology_modeler/fuseki.py` — `FusekiClient` (SPARQL + Graph Store).
- `src/Ontology Modeler/ontology_modeler/structure.py` — `StructureExplorer`, ~15 structural
  queries that already answer the whole "structural / statistical" intent class.
- `src/Ontology Modeler/ontology_modeler/lpg/` — the RDF→LPG converter that populates
  FalkorDB (`extract` → `transform` → `embed` → `load`).
- `src/Ontology Modeler/ontology_modeler/playground/` — the unified OWL+SKOS projection and
  safe merge write-back; `project.py` is the closest existing analogue to the projection
  upgrades this design needs.
- `infra/fuseki/` and `infra/falkordb/` — local stacks (`docker compose up -d`).

The assistant is **read-only** and must never reach `diff.py`'s `GraphSynchronizer`.
