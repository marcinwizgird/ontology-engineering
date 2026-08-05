# Ontology Assistant Agent — Functional Design

## 1. Purpose and scope

The Ontology Assistant Agent (OAA) makes the platform's ontologies **legible and usable** to
people who are not ontologists, and **callable** by other agents. It operates over the
ontologies themselves — the TBox, its vocabularies, its mappings, its inferred closure. It
does not query instance data and does not compile SQL.

### In scope

- Explaining what an ontology, module, or concept means and covers.
- Finding the concepts, definitions, and triples most relevant to a natural-language question.
- Answering questions about what the ontology asserts or entails, with citations.
- Explaining *why* an answer holds, and where the statement came from.
- Advising how the ontology could be applied — what questions it can answer, how to query it,
  and where it falls short.

### Out of scope (for this design)

- Text-to-SQL / Ontop / R2RML virtualisation over relational sources.
- Editing, authoring, or writing back to the ontology. The Modeler and Playground own that.
- ABox / instance-data question answering.

### Non-functional intent

Read-only. Cite-or-abstain. Deterministic where determinism is cheap (structure,
verbalisation) and probabilistic only where it must be (term matching, prose). Every
capability usable both as chat and as a typed function call by another agent.

---

## 2. The five functional capabilities

| # | Capability | Representative user question | Definition of done |
|---|---|---|---|
| **F1** | **Comprehend** | "What is FIBO FBC/PAS/CAA about? What does this module give me?" | A digest a business analyst reads without RDF literacy: purpose, top concepts, key relationships, size, dependencies |
| **F2** | **Locate** | "Find everything about deposit-taking institutions." | The right IRIs and the right triples, ranked, scoped, with nothing invented |
| **F3** | **Answer** | "Is every SavingsAccount a DepositAccount?" | A claim backed by a citation to an axiom that actually exists |
| **F4** | **Explain** | "Why? Where does that definition come from?" | Verbalised axiom chain + named-graph and module provenance + asserted-vs-inferred flag |
| **F5** | **Utilize** | "What can I do with this? How would I query it? What's missing?" | Competency questions the ontology can answer, runnable example queries, an honest gap report |

**F5 is the differentiator.** Most ontology assistants stop at F1–F4 and leave the user
holding a well-explained artifact they still cannot apply. F5 is also comparatively cheap: it
is mostly precomputation over structure, plus templated query generation.

**Gap reporting is a first-class outcome, not an error path.** "FIBO does not appear to model
trade settlement at the level you need; the nearest concepts are A and B; the natural
extension point is C" is frequently the most valuable answer the agent can give. The
retrieval pipeline is therefore designed to *measure its own coverage* (see
[RETRIEVAL_PIPELINE.md](RETRIEVAL_PIPELINE.md#5-coverage-and-abstention)) rather than always
returning its top-k regardless of quality.

---

## 3. Governing principle: **Falkor proposes, Fuseki proves**

This is not a stylistic preference. It follows from a measured property of the current
projection: the property-graph replica preserves roughly **18–23% of a FIBO module's
triples**. The remainder is `rdfs:subClassOf` onto anonymous classes, `owl:Restriction`
axioms, SKOS annotations, and imports — precisely the content that carries FIBO's meaning.

Therefore:

| Store | Role | Answers | Trust |
|---|---|---|---|
| **FalkorDB** | Contextual routing layer | *Which concepts are probably relevant?* Which are near each other? What's the shortest path? | Approximate, disposable, **never quoted** |
| **Apache Fuseki** | Formal semantic core | *What is actually asserted or entailed?* With what provenance? | Authoritative, cite-able, **the only source of user-facing claims** |

> **Hard rule.** No triple, label, definition, or axiom reaches the user unless it was read
> from Fuseki in this turn. Falkor output is a set of candidate IRIs and structural hints.

This single rule eliminates the most likely failure mode of the whole system: answering an
axiom-level question confidently from a lossy projection. It also makes the failure mode
*testable* — every IRI in an answer must resolve in Fuseki, which is a cheap assertion.

A secondary consequence: Falkor may be rebuilt, re-embedded, or wiped at any time without
affecting correctness, only latency and recall. That keeps the projection free to evolve.

---

## 4. Artifact object model

Define the artifacts first; the tools, prompts, and API contracts fall out of them.

### 4.1 Concept Card — the atomic unit of comprehension

One per IRI, assembled from Fuseki only. This is the backbone of F1, F3, and F4, and the
single highest-leverage function to build first.

```
ConceptCard
  iri
  prefLabel, altLabels[]                 rdfs:label, skos:altLabel, skos:prefLabel
  definition                             skos:definition | rdfs:comment | rdfs:isDefinedBy
  kind                                   owl:Class | skos:Concept | ObjectProperty | DatatypeProperty
  parents[]        {iri, label, inferred: bool}
  children[]       {iri, label, inferred: bool}
  siblings[]       {iri, label}
  properties_out[] {property, range, cardinality, source: domain|restriction}
  properties_in[]  {property, domain}
  restrictions[]   {verbalised, raw_axiom_ref, quantifier, onProperty, filler}
  provenance       {named_graph, module, ontology_iri, version_iri, imported_by[]}
  mappings[]       {predicate: exactMatch|closeMatch|broadMatch, target, target_ontology}
  neighbours[]     {iri, label, via_edge, distance}      // Falkor-suggested, Fuseki-verified
```

Two design notes:

- `restrictions[]` requires **bnode unfolding**. A FIBO class's meaning typically lives in
  `?c rdfs:subClassOf [ owl:onProperty ?p ; owl:someValuesFrom ?f ]`. A naive CBD gets the
  bnode but not a usable structure; the card builder must walk and normalise it into
  `{quantifier, onProperty, filler}` triples the verbaliser can consume.
- Every parent/child carries an `inferred` flag, resolved against the materialised closure
  named graph. Conflating asserted and inferred is a correctness bug, not a nicety.

### 4.2 Evidence Bundle — what retrieval returns, what an answer cites

```
EvidenceBundle
  question
  intent                                  see RETRIEVAL_PIPELINE.md §3
  anchors[]      {iri, matched_term, method: exact|lexical|vector|structural, score}
  triples[]      {id, s, p, o, graph, tier}     // quads read from Fuseki
  paths[]        {hops[{s,p,o,graph}], length, verified: bool}
  cards[]        ConceptCard                     // hydrated for top anchors
  coverage       {terms_total, terms_matched, weakest_score}
  budget         {triples_considered, triples_kept, tokens_estimate}
```

The bundle is the **stable typed contract** between the OAA and any caller — chat UI, the
Enricher, a future access-layer agent. Design it as a schema on day one; it is the thing that
outlives the prompt engineering.

Every triple carries an `id` so answer sentences can cite `[t17]` and the critic can verify
the citation mechanically.

### 4.3 Module Digest — precomputed comprehension (F1)

One per named graph, generated offline and stored back into an `assistant:digests` named
graph so the knowledge graph remains self-describing.

```
ModuleDigest
  graph_iri, ontology_iri, module_code        e.g. FIBO FBC/FunctionalEntities
  purpose            3 sentences, plain business English
  top_classes[]      by structural centrality, with one-line glosses
  key_properties[]   the relationships that carry the module's meaning
  stats              {classes, object_props, datatype_props, restrictions, triples}
  dependencies       {imports[], imported_by[]}
  competency_questions[]   5 questions this module can answer
  example_queries[]        3 worked SPARQL queries with expected shape
  known_gaps[]             what a user might expect here and not find
  generated_at, generator_version
```

Generating 162 of these is a one-time batch job, cheap to refresh, and immediately delivers
F1 without any conversational machinery.

### 4.4 Answer — the response contract

```
Answer
  prose                 with inline citation markers [t17], [t23]
  claims[]              {sentence, triple_ids[], confidence}
  evidence              EvidenceBundle
  coverage_statement    "3 of 4 of your terms matched concepts in scope."
  caveats[]             lossy-projection notes, inferred-vs-asserted, scope limits
  followups[]           suggested next questions
```

**Uncited factual sentences are a lint failure, not a style issue.** The Grounding Critic
(§5.2) enforces this before the answer is returned.

---

## 5. Agent topology

The prior specification proposed four cooperating agents (Orchestrator, Graph Explorer,
SPARQL, Verbalisation). That split buys little here and costs latency plus context copies:
the "Graph Explorer" and "SPARQL" agents are thin wrappers over deterministic tools, and
verbalisation is not a reasoning task at all. Recommended topology:

```
                        ┌──────────────────────────────┐
     user / caller ───► │      Orchestrator Agent      │
                        │   plan → act → check loop    │
                        └──┬────────────┬───────────┬──┘
                           │            │           │
             Falkor tools ─┘            │           └─ Fuseki tools
             (propose)                  │              (prove)
                                        ▼
                        ┌──────────────────────────────┐
                        │  Verbaliser (pure function)  │
                        │   CNL templates, no LLM      │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │  Grounding Critic (subagent) │
                        │  adversarial: does every     │
                        │  claim match a real triple?  │
                        └──────────────────────────────┘
```

### 5.1 Orchestrator

One agent holding the full tool catalog, running plan → act → check. Responsibilities:
intent classification, term extraction, tool sequencing, budget enforcement, assembling the
Evidence Bundle, drafting prose. It maintains conversational state (previously anchored IRIs
become priors for follow-up questions — "and what about its subclasses?").

### 5.2 Grounding Critic — the one subagent worth having

Runs after drafting, before returning. Its only job, framed adversarially: *try to refute
this answer*. Checks:

1. Every IRI mentioned exists in Fuseki (mechanical, zero-tolerance).
2. Every factual sentence carries at least one triple citation.
3. Each cited triple, read literally, supports the sentence it is attached to.
4. No asserted/inferred conflation; no Falkor-only claim.
5. Coverage statement matches the actual anchor scores.

Failures return to the orchestrator with a reason, one retry, then degrade to a
partial answer with explicit caveats. This is the difference between a demo and something a
data-governance team will trust.

### 5.3 Verbalisation is a function, not an agent

FIBO uses a small, closed set of axiom patterns — in practice ~15 shapes cover the vast
majority (`∃p.C`, `∀p.C`, `=n p.C`, `≥n p.C`, intersection of restrictions, disjointness,
equivalence, property chains, etc.). A deterministic CNL template engine beats an LLM on
accuracy, cost, latency, and testability. Use the LLM only to stitch verbalised fragments
into a paragraph, never to read the axiom.

```
?c rdfs:subClassOf [ owl:onProperty :hasLegalName ; owl:someValuesFrom :LegalName ]
→ "Every Legal Entity must have at least one legal name."
```

Where an `ontolex-lemon` lexicon exists, use it for grammatical agreement (pluralisation,
case). Where it does not, fall back on label-based templates — do not block on lexicons.

### 5.4 When to fan out

Multi-agent parallelism is justified only for **offline batch jobs**: generating all 162
Module Digests, synthesising competency questions across modules, or running a full CQ
regression sweep. Interactive turns stay single-orchestrator.

---

## 6. Deployment shape

- **Separate service** from the Playground API. The assistant runs with **read-only Fuseki
  credentials**; the Playground service holds write credentials via `GraphSynchronizer`.
  Sharing a process makes that separation unenforceable.
- Reuses `FusekiClient`, `StructureExplorer`, and `config.py` as libraries.
- Exposes both a chat endpoint and a typed tool API returning Evidence Bundles, so the
  Enricher and other agents can call it as a service.
- Stateless per turn except for a conversation store of prior anchors and the digest/
  verbalisation caches.

See [TOOL_CATALOG.md](TOOL_CATALOG.md#4-guardrails) for the full guardrail set.
