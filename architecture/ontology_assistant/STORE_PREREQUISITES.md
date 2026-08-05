# Store Prerequisites

What must change in the two stores before the Ontology Assistant Agent can work well. These
are the real blockers — the agent design is straightforward; the projection is where the
quality ceiling is set.

All references are to the current code in
`src/Ontology Modeler/ontology_modeler/`.

---

## Summary

| # | Gap | Store | Blocks | Effort |
|---|---|---|---|---|
| 1 | Default embedder is not semantic | Falkor | F2 entirely | S |
| 2 | Concept profile too thin | Falkor | F2 precision | S |
| 3 | No named-graph / module provenance | Falkor | scoping, F4, digests | M |
| 4 | `skos:Concept` not projected | Falkor | all org-ontology questions | M |
| 5 | Restrictions not projected | Falkor | F2 recall, path finding | L |
| 6 | Datatype properties dropped | Falkor | "what attributes does X have" | S |
| 7 | No full-text index | Falkor | acronym/jargon anchoring | S |
| 8 | Inferred closure not projected | Falkor | asserted-vs-inferred | M |
| 9 | No `assistant:` named graph | Fuseki | digest/CQ/log persistence | S |
| 10 | Closure graph freshness unverified | Fuseki | F3 entailment answers | M |

---

## FalkorDB projection

### 1. The default embedder is not semantic

`lpg/embed.py` ships two implementations, and `LpgConverter.run()` defaults to
`embedder="hash"` — `HashingEmbedder`, a deterministic character-n-gram hashing scheme. Its
own docstring is explicit: *"NOT semantic, but stable, fast, needs no model download, and is
enough to exercise the vector-index plumbing end to end."*

That is exactly right as scaffolding and exactly wrong for this agent. Character n-grams will
not connect "institution" to `DepositoryInstitution` by meaning — only by surface overlap.
Since capability F2 *is* "find what's relevant to my question", the whole system's quality
ceiling sits on this line.

**Fix:** switch the default to `SentenceTransformerEmbedder` (already written, wraps
`all-MiniLM-L6-v2`, 384-d), or an API embedder. Keep `HashingEmbedder` as the offline-test
fallback so unit tests stay dependency-free. Re-index after switching — dimension and
semantics both change.

**Decision needed:** local sentence-transformers (free, offline, adds torch) vs. an API
embedder (better on financial jargon, adds a network dependency). See
[ROADMAP.md](ROADMAP.md#open-decisions).

### 2. Concept profiles are too thin

`concept_profile()` in `lpg/transform.py` feeds the embedder. For disambiguating among 162
modules, a profile should carry:

```
prefLabel · altLabels · definition · direct parent chain (2–3 levels)
· key property names (domain-side) · module code
```

Names alone are ambiguous across FIBO — several modules define similarly-named concepts at
different abstraction levels. The parent chain is what separates them in vector space.

### 3. No named-graph or module provenance on nodes

`lpg/extract.py` runs all three queries **unqualified over the union default graph** — its
docstring says so directly: *"All unqualified over the union default graph, so the whole
loaded TBox is seen as one."*

Consequence: a `:Class` node in Falkor has `iri`, `short_name`, `name`, `definition`,
`alt_labels` (see `MERGE_CLASSES` in `lpg/load.py`) and **no idea which of the 162 named
graphs it came from**. That blocks:

- scoping a search to a module (`scope_hints` in the retrieval funnel become inert),
- provenance in answers (F4),
- per-module digests and central-concept computation (F1),
- module-filtered vector search.

**Fix:** add `GRAPH ?g` to the extraction queries, carry `graph_iri` and a derived
`module_code` onto every node, and add `:Module` nodes with `DEFINED_IN` edges so module-level
traversal is native. This is the highest-value structural change after the embedder.

### 4. `skos:Concept` is not projected

`QUERY_CLASSES` matches `?class rdf:type owl:Class` only. The organisational ontologies in
this workspace (HBIM, the capability model) are **SKOS-based** — a `skos:Concept` is not an
`owl:Class` and is therefore entirely invisible to Falkor. Measured survival of those files
through a class-only projection is around 6.5%, with several pure-SKOS files at 100% loss.

So today the assistant could answer FIBO questions and would be blind to the user's own
ontologies — including every mapping question, which is one of the most valuable intents.

**Fix:** unified projection — `owl:Class` **and** `skos:Concept` become nodes (with a `kind`
property); `rdfs:subClassOf`, `skos:broader`, `skos:related`, and `skos:*Match` become typed
edges. This mirrors the unified projection decision already made and implemented for the
Playground in `playground/project.py`; reuse that logic rather than writing a second one.

### 5. Restrictions are not projected at all

`QUERY_PROPERTIES` requires `?property rdfs:domain ?domain` and `?property rdfs:range ?range`
with both `isIRI`. FIBO, however, expresses most of its actual semantics through
`owl:Restriction` axioms on anonymous classes:

```turtle
:DepositoryInstitution rdfs:subClassOf
    [ a owl:Restriction ;
      owl:onProperty :provides ;
      owl:someValuesFrom :DepositAccount ] .
```

There is no `rdfs:domain`/`rdfs:range` pair to extract here, so this connection simply does
not exist in the property graph. Pathfinding between `DepositoryInstitution` and
`DepositAccount` — the flagship example in the prior specification — would find nothing.

Also note `QUERY_TAXONOMY` filters `isIRI(?superClass)`, correctly dropping bnode
superclasses; combined with the above, the anonymous-class layer is wholly absent.

**Fix:** project **restriction shadow edges**. For each `C rdfs:subClassOf [onProperty p ;
someValuesFrom/allValuesFrom/cardinality f]`, create `(C)-[:P {derived: true, quantifier:
"some", axiom_ref: <bnode-id-or-hash>}]->(f)`. Flag them `derived: true` so the agent knows
these are navigational shadows, and keep `axiom_ref` so hydration can fetch the real axiom
from Fuseki. This restores recall for expansion and pathfinding without pretending the
projection is lossless.

### 6. Datatype properties are dropped

Only `owl:ObjectProperty` is extracted. "What attributes does an Account have?" is a top-five
user question and currently unanswerable from Falkor.

**Fix:** project datatype properties as `:Attribute` nodes (or as a list property on the
class), with datatype and definition.

### 7. No full-text index

`lpg/load.py` creates a vector index (`create_vector_index`, using `vecf32()` so
`db.idx.vector.queryNodes` can see the embeddings) but no full-text index. Vector search is
weak precisely where ontology users are strong: acronyms and exact official terms (`LEI`,
`CUSIP`, `ISIN`, exact FIBO labels).

**Fix:** add a FalkorDB full-text index on `name` and `alt_labels`; fuse with vector results
by reciprocal rank as described in
[RETRIEVAL_PIPELINE.md §2.2](RETRIEVAL_PIPELINE.md#22-anchoring--why-all-three-methods).

### 8. Inferred closure is not projected

The Enricher already produces materialised closures (`inferred_closure.ttl`). Falkor holds
only asserted `SUBCLASS_OF` edges, so it cannot distinguish "stated" from "derived".

**Fix:** load closure edges as `SUBCLASS_OF {inferred: true}`. Keeps ancestry walks complete
while preserving the distinction the answer must report.

---

## Fuseki side

### 9. No `assistant:` named graph

The agent produces durable artifacts — Module Digests, the competency-question library,
verbalisation caches, query logs, feedback. Writing these into a dedicated
`assistant:` named graph keeps the knowledge graph self-describing and makes the digests
themselves queryable.

**Caveat:** this is the one place the assistant needs write access. Resolve it by having the
**offline digest generator** (a separate batch job with its own credentials) do the writing —
the interactive agent stays strictly read-only.

### 10. Closure graph freshness is unverified

F3 entailment answers (`ask_entailment`) are only as good as the materialised closure. There
is currently no freshness contract: if a module is updated and the closure is not
re-materialised, the agent will confidently return stale entailments.

**Fix:** stamp the closure graph with `generated_at` and the source-graph versions it covers;
have `ask_entailment` compare against the current source versions and downgrade its answer to
`mode: "unknown"` with a caveat when the closure is stale.

### 11. Optional: label index / materialised lexical view

`resolve_label` over 133k triples with `FILTER regex` will be the slowest step in anchoring.
A materialised `label → IRI` view (or Fuseki's text index, if enabled) brings method (a)
inside the 200 ms anchoring budget.

---

## Sequencing

Gaps **1, 2, 6, 7** are small and independent — do them together in one converter pass.
Gap **3** is the highest-value structural change and should land next; **4** and **5** follow
and can reuse `playground/project.py`. Gaps **8** and **10** pair naturally with whatever
reasoning phase materialises the closure. Gap **9** is a prerequisite for the P0 digest
generator.
