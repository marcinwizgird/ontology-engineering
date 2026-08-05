# Roadmap and Open Decisions

---

## Phasing

Each phase is independently useful and independently demonstrable. The ordering is driven by
dependency, not by ambition: P0 ships value against today's stores, P1 removes the quality
ceiling, and only then does conversational machinery pay off.

### P0 — Read-only foundation (works against today's stores)

Delivers **F1** immediately, with no projection changes and no agent loop.

- Read-only Fuseki credentials + a thin `assistant` package wrapping `FusekiClient`.
- `concept_card()` — the backbone function: CBD, bnode/restriction unfolding, closure flags,
  provenance, mappings.
- `verbalize()` — the CNL template registry for the ~15 axiom shapes FIBO actually uses.
- `module_digest()` generator, template-first, run as an offline batch over the loaded graphs.
- `assistant:` named graph for digests ([gap 9](STORE_PREREQUISITES.md#9-no-assistant-named-graph)).
- Wrap `StructureExplorer` as tools — the structural/statistical intent class is done for free.

*Exit criterion:* a browsable set of module digests, and `concept_card()` producing a readable
card for any FIBO IRI, verified against the CQ gold set's definition-intent slice.

### P1 — Projection upgrades (removes the quality ceiling)

Everything in [STORE_PREREQUISITES.md](STORE_PREREQUISITES.md), sequenced:

1. Embedder swap + richer concept profile + datatype properties + full-text index
   (gaps 1, 2, 6, 7) — one converter pass.
2. Named-graph/module provenance and `:Module` nodes (gap 3).
3. Unified OWL+SKOS projection, reusing `playground/project.py` (gap 4).
4. Restriction shadow edges (gap 5).
5. Closure edges + freshness contract (gaps 8, 10).

*Exit criterion:* anchor recall@10 measured before and after each step, per
[EVALUATION.md §2](EVALUATION.md#2-retrieval-metrics). Step 1 alone should move it visibly.

### P2 — The retrieval funnel and the agent loop

Delivers **F2, F3, F4**.

- Stages 1–6 of the funnel, as separate composable tools.
- Evidence Bundle as a typed, versioned schema.
- Orchestrator with plan → act → check.
- Grounding Critic subagent + the three hard gates.
- Service: chat endpoint + typed tool API, separate process from the Playground API.

*Exit criterion:* hard gates at zero, citation coverage ≥ 0.98, full CQ scorecard produced.

### P3 — Reasoning-backed intents

- `ask_entailment` over the materialised closure, with asserted-vs-inferred reporting and
  stale-closure downgrade.
- `differentiate()` for disambiguation questions.
- Path questions with per-hop Fuseki verification.

### P4 — Utilization (F5)

- `synthesize_cqs()` per module.
- `example_queries()` — runnable SPARQL/Cypher generation, validated by execution.
- `gap_report()` as a first-class answer shape.
- Mapping-aware cross-ontology answers (org ↔ FIBO), which depend on P1 step 3.

### P5 — Deferred: Semantic Access Layer

The Ontop / R2RML / text-to-SQL half of TD-OAA-2026-V1
(`docs/Ontology Assistant Agent/ontology-assistant-specification.md` §4.2 and §5). This is a
different product with different risk (it touches production databases and needs SQL
guardrails). It should consume the OAA's Evidence Bundle contract rather than reimplementing
retrieval — which is a good reason to freeze that contract in P2.

---

## What to start with

Two items, because everything else depends on them:

1. **`concept_card()` against Fuseki.** One function, no agent, no projection change. It is
   the backbone of F1, F3, and F4, and it is testable in isolation against the FIBO modules
   already loaded.
2. **Swap the embedder and enrich the concept profile**
   ([gaps 1–2](STORE_PREREQUISITES.md#1-the-default-embedder-is-not-semantic)). Small change,
   sets the retrieval quality ceiling for the entire system, and its effect is directly
   measurable via anchor recall.

---

## Open decisions

These change the design materially and are worth settling before P1.

### D1 — Embedding model

| Option | For | Against |
|---|---|---|
| Local `all-MiniLM-L6-v2` (already wired in `lpg/embed.py`) | offline, free, no network dependency, reproducible | adds torch; middling on financial jargon |
| API embedder | markedly better on domain jargon; larger dimensions | network dependency, per-index cost, reproducibility caveats |

Sets the retrieval quality ceiling. Recommendation: start local to establish the measured
baseline, then A/B against an API embedder using anchor recall on the CQ gold set — the
harness makes this a cheap comparison rather than a matter of opinion.

### D2 — Surface: chat only, or a tool API too?

If other agents (the Enricher, a future access layer) will call the assistant, the Evidence
Bundle must be a stable typed contract from day one, and tools need HTTP parity with their
internal signatures. Recommendation: build the typed API first and treat chat as its first
client — it costs little early and is expensive to retrofit.

### D3 — Hosting

Extend `ontology_modeler.playground.api`, or a separate `ontology_assistant` service?
Recommendation: **separate**, because the read-only-credentials requirement is otherwise
unenforceable in-process.

### D4 — Digest generation strategy

Template-generated from structure, or LLM-written per module? 162 modules makes full LLM
generation a real (if one-time) cost, and templates give consistency and testability.
Recommendation: template-first for all modules, LLM polish for the ~20 actually in active use.

### D5 — Verbalisation depth

Do we invest in `ontolex-lemon` lexicons for grammatical agreement, or accept label-based
templates? Recommendation: label-based templates now; lexicons only if verbalisation quality
shows up as a complaint in the §5 rubric. Do not block P0 on lexicon availability.

### D6 — Conversation memory

Per-turn stateless, or persist anchors and successful trajectories across sessions? Persisted
trajectories (the "semantic memory" pattern from the v1 spec §6.2) help repeat users and
provide usage analytics for ontology maintenance — but add a store and a privacy surface.
Recommendation: session-scoped anchors in P2; persistent trajectories only once there is real
usage to learn from.
