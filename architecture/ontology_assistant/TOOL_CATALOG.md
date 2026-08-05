# Tool Catalog

Every capability the Ontology Assistant Agent exposes to its own orchestrator — and, through
the service API, to other agents. Following the project convention, each tool is a plain
function with a typed signature, individually testable, reusable as a networkx node in a
pipeline graph, and callable as an agentic function tool.

Tools are grouped by trust level, which mirrors the governing principle:
**Falkor tools propose (never quoted); Fuseki tools prove (citable).**

---

## 1. Falkor tools — fast, approximate, never cited

| Tool | Signature | Purpose |
|---|---|---|
| `vector_search` | `(text: str, k: int = 10, module: str \| None = None, kind: str \| None = None) -> list[Match]` | Semantic kNN over concept-profile embeddings. `Match = {iri, score, name, module}` |
| `lexical_search` | `(text: str, k: int = 10, module: str \| None = None) -> list[Match]` | Full-text match over `name` / `alt_labels`. Beats vectors on acronyms and exact jargon |
| `neighborhood` | `(iri: str, hops: int = 1, edge_types: list[str] \| None = None) -> Subgraph` | k-hop candidate expansion |
| `path_between` | `(a: str, b: str, max_len: int = 4) -> list[Path]` | `shortestPath` between anchors; hops must be Fuseki-verified before use |
| `ancestry` | `(iri: str, stop_at_stable: bool = True) -> list[Match]` | Walk up to a definition-bearing superclass |
| `descendants` | `(iri: str, max_depth: int = 2) -> list[Match]` | Subtree preview (counts, not exhaustive lists) |
| `central_concepts` | `(module: str, n: int = 10) -> list[Match]` | Structural prior for anchoring and for Module Digests |
| `similar_to` | `(iri: str, k: int = 10) -> list[Match]` | "What else is like this" — embedding neighbours, not taxonomic siblings |

All Falkor tools return `Match` objects carrying `iri` only as a *pointer*. Labels and
definitions returned here are for the agent's internal reasoning; the user-facing copies must
come from `concept_card`.

---

## 2. Fuseki tools — authoritative, citable

| Tool | Signature | Purpose |
|---|---|---|
| `concept_card` | `(iri: str, include_neighbours: bool = True) -> ConceptCard` | **The backbone function.** CBD + bnode/restriction unfolding + closure flags + provenance + mappings |
| `triples_for` | `(iris: list[str], tiers: list[int] = [1,2,3,4]) -> list[Quad]` | Batched hydration workhorse; the source of every citation |
| `resolve_label` | `(text: str, exact: bool = True) -> list[Match]` | Authoritative label → IRI lookup (backs anchoring method (a)) |
| `ask_entailment` | `(s: str, p: str, o: str) -> {holds, mode: asserted\|inferred\|unknown, witness}` | `ASK` against asserted graphs, then the materialised closure graph |
| `differentiate` | `(a: str, b: str) -> {shared[], only_a[], only_b[]}` | Axiom-set diff for disambiguation questions |
| `verify_path` | `(path: Path) -> {verified: bool, hops[]}` | Confirms each Falkor-suggested hop exists as a real triple |
| `mappings_for` | `(iri: str, direction: both\|in\|out = "both") -> list[Mapping]` | Cross-ontology matches from the mapping named graph |
| `provenance_for` | `(iri: str) -> Provenance` | Named graph, ontology IRI, version, import chain |
| `module_inventory` | `(graph_iri: str) -> Inventory` | Classes, properties, restriction counts, roots and leaves |
| `sparql` | `(query: str, limit: int = 500) -> Rows` | Guarded escape hatch — see §4 |

### Reuse from `StructureExplorer`

`src/Ontology Modeler/ontology_modeler/structure.py` already implements much of the
structural/statistical intent class and should be wrapped rather than reimplemented:
`list_ontologies`, `classes`, `object_properties`, `data_properties`, `skos_relations`,
`skos_relation_summary`, `superclasses`, `subclasses`, `roots_and_leaves`,
`cross_ontology_subclass_edges`, `property_domain_range`, `cross_ontology_object_properties`,
`dependency_matrix`.

That covers "how many classes in FND", "what does this import", "which ontologies link to
which" with zero new query-writing.

---

## 3. Synthesis and orchestration tools

| Tool | Signature | Purpose |
|---|---|---|
| `extract_intent` | `(question: str, history: list) -> IntentSpec` | Stage 1 of the funnel |
| `anchor_terms` | `(spec: IntentSpec) -> list[Anchor]` | Runs the three anchoring methods in parallel, fuses by RRF |
| `build_evidence` | `(anchors, spec) -> EvidenceBundle` | Stages 3–5: expand, hydrate, rank, budget |
| `verbalize` | `(axioms: list[Axiom]) -> str` | Deterministic CNL templates; no LLM |
| `module_digest` | `(graph_iri: str, refresh: bool = False) -> ModuleDigest` | Cached; regenerates on demand |
| `synthesize_cqs` | `(graph_iri: str, n: int = 5) -> list[str]` | Competency questions the module can answer (F5) |
| `example_queries` | `(intent: IntentSpec, anchors: list[Anchor]) -> list[Query]` | Runnable SPARQL/Cypher the user can copy (F5) |
| `gap_report` | `(spec: IntentSpec, anchors: list[Anchor]) -> GapReport` | Nearest neighbours + absence statement + extension point |
| `check_grounding` | `(answer: Answer) -> CritiqueResult` | The Grounding Critic's tool surface |

`verbalize` deserves its own template registry, one entry per axiom pattern:

```
some(p, f)        → "Every {C} must have at least one {f} that it {p}."
all(p, f)         → "Anything a {C} {p} must be a {f}."
exactly(n, p, f)  → "Every {C} has exactly {n} {f}."
min(n, p, f)      → "Every {C} has at least {n} {f}."
disjointWith(D)   → "Nothing can be both a {C} and a {D}."
equivalentTo(D)   → "{C} and {D} mean the same thing."
```

---

## 4. Guardrails

The assistant is a **read-only** component operating against a canonical store. Guardrails
are functional requirements, not operational polish.

### Access

- **Dedicated read-only Fuseki credentials.** The assistant must not be able to reach
  `diff.py`'s `GraphSynchronizer`, the Graph Store PUT/POST endpoints, or SPARQL Update.
  A comprehension agent with write access to the canonical store is an incident waiting to
  happen.
- **Separate process** from the Playground API, which legitimately holds write credentials.
- FalkorDB speaks the Redis wire protocol (arbitrary command execution) and `infra/falkordb/
  docker-compose.yml` binds it to loopback with no auth by default. The assistant must use a
  restricted client and must never interpolate user text into a Cypher command name.

### Query safety

| Control | Rule |
|---|---|
| Timeouts | Fuseki 10 s hard, Falkor 2 s hard |
| Forced limits | Inject `LIMIT` into every generated `SELECT`; default 500 |
| No unbounded DESCRIBE | `DESCRIBE` only with an explicit IRI list; never over a graph |
| Cypher injection | Relationship types validated against `^[A-Z][A-Z0-9_]*$` (as `lpg/load.py` already does); all values bound as parameters |
| SPARQL injection | IRIs bound via `VALUES`, never string-concatenated |
| Per-turn budget | Max 12 tool calls, max 25k tokens of retrieved evidence |
| Update verbs | `INSERT`, `DELETE`, `DROP`, `LOAD`, `CLEAR` rejected at the tool boundary regardless of credentials |

### Output safety

- Every IRI in an answer must resolve in Fuseki — checked mechanically by the critic.
- No claim sourced from Falkor alone.
- Inferred statements always labelled as inferred, with the closure graph named.
- Where the answer relies on a lossy path suggestion, say so in `caveats[]`.

---

## 5. Function-tool packaging

Consistent with the `bottomup_ontology` convention, each tool should be:

1. A pure `state -> state` function where practical, so it can be a node in a networkx
   pipeline graph and replayed deterministically in tests.
2. Annotated with a JSON schema for direct exposure as an LLM function tool.
3. Independently unit-testable against a small fixture dataset (a two-module FIBO subset)
   without a live store, plus an integration test against the running stacks.
4. Exposed over HTTP with the same names and shapes, so an external agent's transcript and
   the internal orchestrator's transcript are directly comparable.
