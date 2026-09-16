# Ontology Projection and the GraphRAG Agent — SysML models

Three SysML v2 models and their companion views, covering the path from an OWL ontology
to an agent that answers questions about it without inventing any of them.

| Model | File | What it pins down |
|---|---|---|
| **Projection function** | [`models/ontology_projection.sysml`](models/ontology_projection.sysml) | π : Ontology → PropertyGraph — domain, codomain, four strategies, six correctness constraints |
| **Projection system** | [`models/fibo_projection_system.sysml`](models/fibo_projection_system.sysml) | The *system* that executes π against FIBO — context, components, interfaces, variation, allocation, 9 requirements, 7 verification cases |
| **Agent architecture** | [`models/agent_architecture.sysml`](models/agent_architecture.sysml) | The agent as a system with a trust boundary, and five grounding constraints |

The first is a model of a *function*: what a correct projection is, independent of who
runs it. The second is a model of a *system*: the components that run it against FIBO
specifically, where they are deployed, and how each requirement is discharged. They are
deliberately separate — the invariants outlive any particular implementation of them, and
`fibo_projection_system` inherits rather than restates them.

## Diagrams

Two kinds, and the difference matters.

**Generated SysML diagrams** — `artifacts/diagrams/`, produced by
[`build_diagrams.py`](build_diagrams.py) *from the `.sysml` files themselves*. A hand-drawn
diagram is correct the day it is drawn and quietly stops being correct afterwards, with
nothing to tell you when. These either regenerate or the build fails.

```bash
python architecture/graphrag_agent/build_diagrams.py    # 22 artifacts: SVG + Mermaid
python architecture/graphrag_agent/verify_diagrams.py   # layout check, must report 0 problems
```

| Diagram | Package | SVG | Mermaid |
|---|---|---|---|
| Block Definition | OntologyProjection | `projection_bdd.svg` | `.mmd` |
| Activity — `Project` | OntologyProjection | `projection_act_project.svg` | `.mmd` |
| Block Definition | FiboProjectionSystem | `fibo_system_bdd.svg` | `.mmd` |
| **Requirement** | FiboProjectionSystem | `fibo_system_req.svg` | `.mmd` |
| Internal Block — system | FiboProjectionSystem | `fibo_system_ibd_fibo_projection_system_def.svg` | `.mmd` |
| Internal Block — context | FiboProjectionSystem | `fibo_system_ibd_system_context.svg` | `.mmd` |
| Activity — `RunProjection` | FiboProjectionSystem | `fibo_system_act_run_projection.svg` | `.mmd` |
| State Machine — `ProjectionRun` | FiboProjectionSystem | `fibo_system_stm_projection_run.svg` | `.mmd` |
| Block Definition | GraphRagAgent | `agent_bdd.svg` | `.mmd` |
| Internal Block — agent | GraphRagAgent | `agent_ibd_ontology_agent_system.svg` | `.mmd` |
| Activity — `AnswerQuestion` | GraphRagAgent | `agent_act_answer_question.svg` | `.mmd` |

SVG is hand-rendered by a small layered-layout engine in
[`sysml_diagrams.py`](sysml_diagrams.py) — no Graphviz, no Node, no headless browser, and
the file still opens in five years. Mermaid companions are there for reviewing a change
inline in a diff or an IDE.

**Hand-drawn narrative views** — `artifacts/*.mmd`. These say things the models do not,
because they carry measured numbers and design rationale rather than element structure.
They are maintained by hand and are not regenerated.

| View | File |
|---|---|
| System context — actors, sources, targets | [`artifacts/fibo_system_context.mmd`](artifacts/fibo_system_context.mmd) |
| Pipeline internals + allocation | [`artifacts/fibo_system_ibd.mmd`](artifacts/fibo_system_ibd.mmd) |
| Run states, annotated | [`artifacts/fibo_projection_states.mmd`](artifacts/fibo_projection_states.mmd) |
| Projection function and its invariants | [`artifacts/projection_function.mmd`](artifacts/projection_function.mmd) |
| Agent structure and the trust boundary | [`artifacts/agent_architecture.mmd`](artifacts/agent_architecture.mmd) |
| Retrieval funnel, as a sequence | [`artifacts/retrieval_funnel.mmd`](artifacts/retrieval_funnel.mmd) |

Where a generated diagram and a hand-drawn view disagree, the generated one is right —
it was read out of the model.

### What the layout check covers

`verify_diagrams.py` checks the failures a hand-rolled layout actually produces:
malformed XML, boxes off-canvas, boxes overlapping, compartment text running past its
box, an edge label sitting on an unrelated block, an edge drawn to a node that is not
there, and a canvas too dense to read. It currently reports **0 problems across 11
diagrams**.

It found one real defect: edge labels were being placed at the midpoint between two node
*centres* rather than on the drawn curve, so every edge spanning more than one layer
printed its label on top of whatever box sat in between. Labels now go at the curve's
midpoint, with fallback positions, and are dropped rather than allowed to cover a block —
87% are placed; the rest rely on arrowhead and colour, which carry the relation kind
anyway.

**Not** checked: whether a diagram is well composed. That still needs eyes, and I have
not had them on these — there is no rasteriser or browser available in this environment,
so the verification above is structural only.

## Requirements and verification status

Measured against the vendored FIBO release. **Status is what was actually executed**, not
what the model aspires to.

| Req | | Satisfied by | Verified by | Status |
|---|---|---|---|---|
| R1 | Axiom fidelity | AxiomUnfolder, TboxReader, MetaGraphBuilder | V1, V2 | ✅ 2,721/2,721 landed; V2 vacuous on FIBO |
| R2 | Citation traceability | GraphLoader | — | ✅ by construction (IRI is the MERGE key) |
| R3 | Repeatability | GraphLoader | V3 | ✅ stable over 3 consecutive loads |
| R4 | Offline operation | SourceAdapter, TboxReader | V4 | ✅ 299 parsed, 0 failed, no network |
| R5 | Retrievability | IndexManager | V5 | ✅ VECTOR + FULLTEXT + RANGE all OPERATIONAL |
| R6 | Bulk throughput | ProjectionController | — | ✅ 118 s vs 300 s budget |
| R7 | Source independence | SourceAdapter | — | ⚠️ file path exercised; SPARQL path unchanged but not re-run |
| R8 | Injection safety | GraphLoader | V6 | ✅ `BAD TYPE`, `X]->() DELETE (n) //`, `lower_case`, `""` all refused |
| R9 | Embedding coherence | EncoderArtifactManager, VectorEncoder | V7 | ⚠️ dimension matches (256); exact self-retrieval 60.8% — encoder limit, see below |

Two defects were found *by* the verification cases, both of which degrade silently:

- **V1 — AxiomCoverage.** The first implementation unfolded 642 restrictions in FBC and
  landed 431. The loader `MATCH`es both endpoints, and roughly a third of FIBO's
  restrictions target OMG Commons classes the offline release never declares. Stubbing
  them as flagged external nodes took coverage to 642/642 and raised domain/range edges
  from 23 to 37. Nothing *looked* wrong before the fix.
- **V3 — Idempotence.** Edges grew 10,498 → 10,794 on a second load. The domain/range
  `MERGE` pattern omitted `via`, so it matched and overwrote the restriction edge of the
  same property between the same two classes; the restriction loader then recreated it,
  and the pair oscillated every run. Moving `via` into the MERGE pattern fixed it.

## Anchor quality — why the retriever fuses two rankers

Measured over 120 exact FIBO class names (seed 7):

| Mode | recall@1 | recall@5 |
|---|---:|---:|
| Vector only (TF-IDF/SVD, 256-d) | 60.8% | 83.3% |
| Full-text only (BM25) | 70.8% | 90.8% |
| **Hybrid, reciprocal-rank fusion** | **81.7%** | **94.2%** |

Each ranker alone misses about one name in three at rank 1, and they miss *different*
ones — lexical search fails on paraphrase, latent-semantic search fails on exact
identifiers and returns the sibling family instead (`credit default swap` →
`multi-name credit default swap`). Fusion costs one extra query and recovers most of
both. This is the empirical content behind `GraphRagAgent::AnchorRecall`, and the number
to re-measure whenever the encoder or the profile template changes.

## Why model this in SysML at all

The box-and-arrow content of a projection pipeline is obvious and does not need a
notation. What is not obvious, and what the model exists to carry, is the set of
**invariants that make the output trustworthy** — and those are written as
`assert constraint` blocks rather than prose, because each one corresponds to something a
test can check.

Two of them earned their place by being violated during the build:

- **`AxiomCoverage`** (`landed == unfolded`). The first working projection unfolded 642
  restrictions in FIBO's FBC module and landed 431 of them. The loader `MATCH`es both
  endpoints, and a third of FIBO's restrictions point at OMG Commons classes that are not
  vendored in this repository — so they were dropped in silence. Materialising
  referenced-but-undeclared classes as flagged external stubs took coverage to 642/642.
  Nothing about the graph *looked* wrong before the fix; it just quietly had a third fewer
  cross-links than the ontology asserts.

- **`EmbedderProvenance`**. A TF-IDF/SVD basis fitted at projection time and discarded
  means queries get embedded in a *different* space from the index. Scores stay in range,
  rankings stay plausible, and retrieval is meaningless. The constraint forces the fitted
  embedder to be persisted beside the graph.

Both are failure modes that degrade silently, which is exactly the class of problem worth
writing down formally.

## Model → code

Every part in the model names the module that realises it.

| Model element | Realised by |
|---|---|
| `ExtractionStrategy` / `SparqlExtraction` | `ontology_modeler/lpg/extract.py` |
| `ExtractionStrategy` / `FileExtraction` | `ontology_modeler/lpg/rdf_source.py` |
| `TransformationStrategy` | `ontology_modeler/lpg/transform.py` |
| `EmbeddingStrategy` | `ontology_modeler/lpg/embed.py` |
| `LoadingStrategy` | `ontology_modeler/lpg/load.py` |
| `action def Project` | `ontology_modeler/lpg/converter.py` (`LpgConverter.run`) |
| `SourceAdapter`, `TboxReader`, `AxiomUnfolder` | `ontology_modeler/lpg/rdf_source.py` |
| `EncoderArtifactManager` | `ontology_modeler/lpg/embed.py` (`save_embedder`/`load_embedder`) |
| `IndexManager` | `ontology_modeler/lpg/load.py` (`create_*_index`) |
| `GraphRagRetriever`, `action def AnswerQuestion` | `ontology_modeler/graphrag/retriever.py` |
| `ToolBelt` | `ontology_modeler/graphrag/tools.py` |
| `LanguageModel`, `AgentLoop`, grounding rules | `ontology_modeler/graphrag/agent.py` |

## The design decisions the models encode

**Restrictions are the graph.** FIBO states its relations as anonymous `owl:Restriction`
superclasses, not as `rdfs:domain`/`rdfs:range`. Across the whole of FIBO the projection
yields 2,721 restriction edges against 560 domain/range edges; in the FBC module alone the
ratio is 642 to 37. A converter that reads only named triples produces a taxonomy with
almost no cross-links — technically a graph, useless to traverse. `RestrictionAxiom` is a
first-class part of the domain model for that reason.

**The language model is not a source of facts.** `LanguageModel.mayAssertFacts = false` is
the load-bearing line in the agent model. The risk with an ontology-backed assistant is
not that it invents something from nothing; it is that it answers from its own knowledge
of finance while wearing a citation, which survives review in a way an obvious fabrication
does not. The structural half of the defence is that the model has no port to the store
except through the retriever. The semantic half is not structurally enforceable, which is
why `trace()` exists: it returns the tool calls beside the answer so grounding can be
measured.

**Anchor recall is the system's ceiling.** If the right class is not in the candidate set,
no downstream stage recovers it. `AnchorRecall` is therefore the one quantitative gate in
the model, and the number to re-measure whenever the embedder or the profile template
changes — not end-to-end answer quality, which moves for too many reasons at once.

## Running the thing the models describe

```bash
cd infra/falkordb && docker compose up -d

cd "src/Ontology Modeler"
python -m ontology_modeler -v project --graph-name fibo --clear --embed \
    "../../Ontology Repository/FIBO/fibo"

python -m ontology_modeler.graphrag --graph-name fibo selftest
python -m ontology_modeler.graphrag --graph-name fibo card "demand deposit account"
python -m ontology_modeler.graphrag --graph-name fibo ask --trace "..."   # needs ANTHROPIC_API_KEY
```

See [`src/Ontology Modeler/ontology_modeler/graphrag/README.md`](../../src/Ontology%20Modeler/ontology_modeler/graphrag/README.md)
for measured results and the retrieval design in detail.
