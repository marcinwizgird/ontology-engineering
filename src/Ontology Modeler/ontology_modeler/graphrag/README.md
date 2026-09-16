# graphrag — GraphRAG over a projected ontology

Retrieval and an agent over the FalkorDB projection produced by [`../lpg`](../lpg).
Modelled in SysML at [`architecture/graphrag_agent`](../../../../architecture/graphrag_agent).

```
question ──▶ anchor (vector ⊕ full-text) ──▶ concept cards / traversal ──▶ grounded answer
                        │                            │                          │
                  every hit has an IRI      every record has an IRI      every claim cites one
```

## Run it

```bash
cd infra/falkordb && docker compose up -d          # FalkorDB on 127.0.0.1:6379

cd "src/Ontology Modeler"
python -m ontology_modeler -v project --graph-name fibo --clear --embed \
    "../../Ontology Repository/FIBO/fibo"          # ~2 min for all of FIBO

python -m ontology_modeler.graphrag --graph-name fibo selftest
python -m ontology_modeler.graphrag --graph-name fibo search "credit default swap"
python -m ontology_modeler.graphrag --graph-name fibo card "demand deposit account"
python -m ontology_modeler.graphrag --graph-name fibo ask --trace "…"   # needs ANTHROPIC_API_KEY
```

`selftest`, `search` and `card` need no API key. That is deliberate: retrieval and
generation fail in different ways and want different fixes, so the retrieval half has to
be exercisable without a model in the loop.

## What FIBO projects to

299 files, 132,939 triples, ~2 minutes:

| | count |
|---|---:|
| `:Class` nodes | 3,258 (253 external stubs) |
| `:Module` nodes | 299 |
| `[:SUBCLASS_OF]` | 4,212 |
| `[:DEFINED_IN]` | 3,005 |
| restriction edges | 2,721 |
| domain/range edges | 560 |
| distinct relationship types | 906 |
| embedded concept profiles | 3,005 (256-d) |

**Restrictions outnumber domain/range edges roughly five to one.** FIBO states its
relations as anonymous `owl:Restriction` superclasses, so a converter that reads only
named triples gets a taxonomy with almost no cross-links. Unfolding them is what makes
the projection traversable at all.

**906 relationship types** — one per object property — has a practical consequence the
agent has to be told about: `MATCH ()-[r]->() RETURN type(r), count(r)` makes FalkorDB
union 906 edge sets and times out, while the same counts taken one type at a time finish
in about two seconds. `ontology_overview` does the latter, reports only the most common
types, and says explicitly that the list is partial.

## The retrieval funnel

| Stage | Tool | Notes |
|---|---|---|
| orient | `ontology_overview` | Mandatory first call. Cached per retriever. |
| anchor | `search_concepts` | Vector ⊕ full-text, reciprocal-rank fusion (k = 60) |
| read | `get_concept` | Definition, synonyms, module, super/sub, relations both ways |
| traverse | `get_ancestors`, `find_path`, `get_neighbourhood` | |
| escape hatch | `query_graph` | Read-only Cypher, guarded, 15 s timeout |

### Why hybrid anchoring

The two rankers fail on opposite inputs, and the failure that matters is an **anchor
miss** — a model that finds nothing tends to answer from its own knowledge rather than
report the gap, which is the exact behaviour the ontology is supposed to prevent.

Measured over 120 exact FIBO class names (seed 7):

| Mode | recall@1 | recall@5 |
|---|---:|---:|
| Vector only | 60.8% | 83.3% |
| Full-text only | 70.8% | 90.8% |
| **Hybrid (RRF, k=60)** | **81.7%** | **94.2%** |

Each ranker alone misses roughly one name in three at rank 1, and they miss *different*
ones:

```
"LEI"                                   → LEI registered entity, legal entity identifier
                                          registry …                        [both]
"agreement where one party lends
 money to another"                      → repurchase agreement, derivative master
                                          agreement, bilateral agreement …  [vector only]
"credit default swap"   vector alone    → multi-name credit default swap    [wrong rank 1]
                        hybrid          → credit default swap               [both]
```

`found_by: "both"` is the strong signal: semantic and lexical agree.

Re-measure this whenever the encoder or the profile template changes — it is the ceiling
on everything downstream.

### Grounding

The system prompt in [`agent.py`](agent.py) carries the rules; the interesting one is
structural rather than textual. The model has no path to the store except through the
retriever, so it cannot fetch a fact it then fails to cite. What the prompt adds is the
part that is *not* structurally enforceable: no claim without a tool result behind it, an
IRI on every class named, and an explicit "FIBO does not define X" instead of a helpful
guess.

`trace()` returns the tool calls beside the answer, so grounding can be measured against
the evidence actually retrieved rather than asserted.

## Honest limits

- **The default embedder is TF-IDF + SVD**, fitted on FIBO's own concept profiles. It is
  deterministic, CPU-only, needs no download, and beats character hashing by a wide
  margin on this corpus. It is still latent semantic indexing: it captures co-occurrence
  within FIBO, not general paraphrase. `--embedder sentence-transformers` swaps in a real
  encoder at the cost of a torch install; the interface is the same and the fitted model
  is persisted either way.
- **The fitted embedder is ~70 MB** (`artifacts/fibo.embedder.pkl`) and must stay in step
  with the graph. A query embedded by a differently-fitted basis lands in a different
  space and the scores come back plausible but meaningless — which is why the artifact is
  written automatically by `--embed` and loaded by graph name.
- **`external: true` nodes are placeholders**, not definitions. FIBO's upper classes live
  in OMG Commons, which is not vendored here. They are materialised so the taxonomy and
  the restrictions stay connected, excluded from ranked results, and reported by the
  agent as references. `--follow-imports` fetches the real ones over the network.
- **Datatype properties are not projected.** Only classes, modules, and object-property /
  restriction relations. Questions about attributes cannot be answered from this graph.
- **No reasoner runs.** The projection is the asserted TBox. Inferred subsumption is not
  present, so "is X a kind of Y" is answered over asserted edges only.

## Files

| File | Role |
|---|---|
| `retriever.py` | The funnel — anchoring, cards, traversal, guarded Cypher |
| `tools.py` | One LangChain tool per stage; docstrings are what the model reads |
| `agent.py` | `create_agent` wiring, the grounding prompt, `trace()`, `selftest()` |
| `__main__.py` | `selftest` / `search` / `card` / `ask` |
