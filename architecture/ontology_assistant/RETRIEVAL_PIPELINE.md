# Retrieval Pipeline

How the Ontology Assistant Agent turns a natural-language question into a cited
[Evidence Bundle](FUNCTIONAL_DESIGN.md#42-evidence-bundle--what-retrieval-returns-what-an-answer-cites).
This is the heart of capability **F2 (Locate)** and the input to **F3/F4**.

---

## 1. The funnel

```
  question
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 1. INTENT + TERM EXTRACTION                                    (LLM)     │
 │    → {intent, terms[], scope_hints[], modality}                          │
 │    "institutions that manage deposit accounts"                           │
 │    → terms: [institution, manage, deposit account]                       │
 └───┬──────────────────────────────────────────────────────────────────────┘
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 2. ANCHORING — three methods in parallel, fused by reciprocal rank       │
 │    a. exact / near-exact label + altLabel match ............ Fuseki / FT │
 │    b. vector kNN over concept profiles ........................ Falkor   │
 │    c. structural priors (centrality, abstraction level) ....... Falkor   │
 │    → anchors: DepositoryInstitution 0.91, DepositAccount 0.88, …         │
 └───┬──────────────────────────────────────────────────────────────────────┘
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 3. EXPANSION — cheap graph work                                (Falkor)  │
 │    k-hop neighbourhood · ancestry to a stable superclass ·               │
 │    shortestPath between anchor pairs · sibling set                       │
 │    → candidate IRI set (~30–80)                                          │
 └───┬──────────────────────────────────────────────────────────────────────┘
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 4. HYDRATION — authoritative read                              (Fuseki)  │
 │    CBD per candidate · restriction/bnode unfolding · closure lookup ·    │
 │    named-graph provenance · mapping graph lookup                         │
 │    → real quads, the only citable material                               │
 └───┬──────────────────────────────────────────────────────────────────────┘
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 5. RANK & BUDGET                                                         │
 │    score = anchor_proximity × predicate_tier × definition_presence       │
 │            × scope_match × novelty ;  prune to token budget              │
 └───┬──────────────────────────────────────────────────────────────────────┘
     │
 ┌───▼──────────────────────────────────────────────────────────────────────┐
 │ 6. VERBALISE + CITE                                                      │
 │    CNL templates per axiom pattern; LLM joins the seams; every           │
 │    factual sentence carries triple ids                                   │
 └──────────────────────────────────────────────────────────────────────────┘
```

Stages 2–4 are the load-bearing ones. Stages 1 and 6 are LLM work; 2, 3, 5 are mostly
deterministic; 4 is entirely deterministic.

---

## 2. Stage detail

### 2.1 Intent and term extraction

A single structured LLM call returning:

```json
{
  "intent": "discovery",
  "terms": ["institution", "deposit account"],
  "relations": ["manage"],
  "scope_hints": ["FIBO", "FBC"],
  "modality": "existence",
  "followup_of": null
}
```

Separating **terms** (candidate concepts) from **relations** (candidate properties) matters:
they are matched against different node/edge populations and mixing them pollutes anchoring.
`scope_hints` become module filters in stages 2–4, which is the difference between searching
162 graphs and searching three.

### 2.2 Anchoring — why all three methods

No single method is adequate:

| Method | Strong at | Blind to |
|---|---|---|
| **Exact/lexical** | jargon, acronyms (`LEI`, `CUSIP`), official labels | paraphrase, business slang |
| **Vector kNN** | paraphrase, synonymy, "savings account" → `SavingsAccount` | exact acronyms; only as good as the embedding (see [STORE_PREREQUISITES.md](STORE_PREREQUISITES.md#1-the-default-embedder-is-not-semantic)) |
| **Structural prior** | choosing the *right abstraction level* among 40 label matches | nothing on its own — it is a re-ranker |

Fuse with **reciprocal rank fusion** (`score = Σ 1/(k + rank_i)`, k≈60) rather than
weighted-sum of incomparable scores. RRF is robust to one method being miscalibrated, which
matters while the embedder is still provisional.

**On the structural prior.** Asked "what is an account", the right anchor is the abstract
FIBO `Account`, not the dozens of leaf subclasses whose labels also contain "account". Prefer
concepts with high subclass in-degree, a present `skos:definition`, and shallow depth —
unless the question itself is specific ("*savings* account"), in which case term specificity
should push the other way. Encode this as an explicit re-rank feature, not as prompt advice.

### 2.3 Expansion

Purely in Falkor, purely as candidate generation. Four moves:

- **Neighbourhood** — 1–2 hops from each anchor over `SUBCLASS_OF` and object-property edges.
- **Ancestry** — walk up to a "stable" superclass (one with a definition and many children);
  this is what lets the agent say *what kind of thing* the anchor is.
- **Path** — `shortestPath` between anchor pairs. This is the machinery behind relationship
  questions ("how does Account relate to LegalEntity?").
- **Siblings** — for disambiguation and "what else is like this".

Cap the candidate set (~80). Beyond that, hydration cost dominates and ranking quality falls.

> Expansion quality is currently limited: Falkor holds only `domain`/`range`-derived
> object-property edges, so the connections FIBO expresses through `owl:Restriction` are
> invisible to pathfinding. See [STORE_PREREQUISITES.md](STORE_PREREQUISITES.md#5-restrictions-are-not-projected-at-all).

### 2.4 Hydration

The authoritative step. For each candidate IRI, from Fuseki:

1. **CBD** (concise bounded description), following blank nodes so restriction axioms come
   back whole.
2. **Restriction normalisation** — `[owl:onProperty p ; owl:someValuesFrom f]` →
   `{quantifier: "some", property: p, filler: f}`, ready for the verbaliser.
3. **Closure lookup** — is each `subClassOf` asserted here or materialised in the inferred
   named graph? Flag it.
4. **Provenance** — which named graph, which ontology IRI, which version, imported by whom.
5. **Mappings** — `skos:exactMatch` / `closeMatch` into the organisational ontologies, from
   the separate mapping named graph.

Batch this: one `VALUES`-driven query per concern across all candidates, not one query per
candidate. Roughly five round trips regardless of candidate count.

### 2.5 Ranking and budgeting

Not all triples are worth context. Score by **predicate tier** first:

| Tier | Predicates | Weight |
|---|---|---|
| 1 — Definitional | `skos:definition`, `rdfs:comment`, `rdfs:isDefinedBy`, `skos:prefLabel` | highest |
| 2 — Taxonomic | `rdfs:subClassOf` (named), `owl:equivalentClass`, `skos:broader` | high |
| 3 — Restriction | unfolded `owl:Restriction` axioms | high (this is where FIBO's meaning lives) |
| 4 — Relational | object/datatype property domain-range | medium |
| 5 — Lexical | `skos:altLabel`, `rdfs:label` on neighbours | low |
| 6 — Housekeeping | `rdf:type owl:Class`, `owl:imports`, annotations on annotations | drop unless asked |

Final score multiplies tier weight by anchor proximity (hop distance), scope match (does it
sit in a hinted module?), and novelty (penalise near-duplicate triples across sibling
concepts). Prune to a token budget — target ~4–6k tokens of evidence for a normal turn.

Tier 6 is typically 40–60% of raw CBD volume. Dropping it before the LLM sees anything is the
single biggest context saving available.

### 2.6 Verbalisation and citation

See [FUNCTIONAL_DESIGN.md §5.3](FUNCTIONAL_DESIGN.md#53-verbalisation-is-a-function-not-an-agent).
Every factual sentence emitted must reference triple ids from the bundle. The orchestrator
drafts against the bundle only — it never has the raw store in context, which makes
hallucinated IRIs structurally unlikely and mechanically detectable.

---

## 3. Intent taxonomy and routing table

This table is effectively the agent's dispatch specification.

| Intent | Example | Route | Primary store |
|---|---|---|---|
| **Definition** | "What is a Depository Institution?" | anchor → Concept Card | Fuseki |
| **Discovery / existence** | "Do we have concepts for institutions that manage deposit accounts?" | full funnel; abstain if coverage low | both |
| **Disambiguation** | "Customer vs Client vs Counterparty?" | multi-anchor → common ancestor (Falkor) → *differentiating* axioms (Fuseki diff) | both |
| **Relationship / path** | "How does an Account relate to a Legal Entity?" | `shortestPath` → verify every hop in Fuseki → verbalise chain | both |
| **Structural / statistical** | "How many classes in FND? What imports it?" | direct aggregate — mostly already in `StructureExplorer` | Fuseki |
| **Entailment** | "Is every SavingsAccount a DepositAccount?" | `ASK` over closure graph; report asserted vs inferred + witness | Fuseki |
| **Utilization** | "What can I use this module for?" | Module Digest + CQ synthesis + generated example queries | cache/Fuseki |
| **Coverage / gap** | "Do we cover trade settlement?" | weak anchoring *is* the answer: nearest neighbours + explicit gap + extension point | both |
| **Mapping** | "What in FIBO matches our HBIM 'Asset'?" | org anchor → mapping named graph → FIBO target → side-by-side cards | Fuseki |
| **Provenance** | "Where does that definition come from?" | named graph → module → import chain → version IRI | Fuseki |
| **Follow-up** | "And its subclasses?" | reuse prior anchors from conversation state; skip stages 1–2 | Fuseki |

Two routes deserve emphasis:

**Disambiguation** is a *diff*, not two lookups. Users asking "what's the difference" want the
differentiating axioms surfaced, with the shared ancestry collapsed to one line. Compute
`shared / only_a / only_b` over the hydrated axiom sets and lead with the differences.

**Coverage/gap** must never silently degrade into a top-k dump. If the best anchor scores
below threshold, the agent's job changes: report what *is* nearby, state plainly that the
requested concept is absent, and name the plausible extension point.

---

## 4. Latency budget

| Stage | Target | Notes |
|---|---|---|
| 1 Intent + terms | < 600 ms | one small structured LLM call |
| 2 Anchoring | < 200 ms | three parallel queries; Falkor is sub-ms, Fuseki FT is the tail |
| 3 Expansion | < 100 ms | Falkor's strength |
| 4 Hydration | < 800 ms | ~5 batched SPARQL round trips |
| 5 Rank/budget | < 50 ms | pure Python |
| 6 Draft + verbalise | < 2.5 s | streaming to the user |
| Grounding critic | < 1.5 s | overlaps streaming; blocks only final commit |
| **Total** | **< 5 s** | cached digests and follow-ups: < 2 s |

---

## 5. Coverage and abstention

The pipeline computes coverage explicitly:

```
coverage = matched_terms / total_terms,  weakest_anchor_score
```

Policy:

| Condition | Behaviour |
|---|---|
| all terms matched, min score high | answer normally |
| some terms unmatched | answer on what matched, **name the unmatched terms explicitly** |
| best score below floor | switch to gap intent: nearest neighbours + "not covered" + extension point |
| nothing above floor | abstain: "I found nothing in the loaded ontologies about X." Offer scope check ("are you expecting a module that isn't loaded?") |

Abstention rate on deliberately out-of-scope questions is a tracked metric — see
[EVALUATION.md](EVALUATION.md#4-abstention-and-honesty). An assistant that never abstains is
not being helpful; it is being confidently wrong at a measurable rate.
