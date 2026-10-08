# Ontology extraction with LangExtract — prototype

[LangExtract](https://github.com/google/langextract) is Google's span-grounded
extraction library: prompt + few-shot examples + document → structured findings
that each carry the **character interval of the source text they came from**.

This package uses that property for bottom-up ontology development:

```
text  ──▶  grounded extractions  ──▶  OWL where every axiom cites its sentence
```

and plugs the result into the existing `bottomup_ontology` workflow (Keet,
*Ontology Engineering* 2nd ed., Fig. 7.7).

## Why grounding, and not "ask an LLM for Turtle"

An LLM will happily emit a plausible ontology. Nobody can review it: there is no
way to ask *what in the text made you say this?* — which is precisely the
question the human-in-the-loop step of Fig. 7.7 exists to ask.

Here every asserted axiom is reified as an `owl:Axiom` (the OWL 2 way to
annotate an axiom rather than an entity) carrying its justification:

```turtle
:BoilerFeedPump rdfs:subClassOf :CentrifugalPump .

[] a owl:Axiom ;
    owl:annotatedSource :BoilerFeedPump ;
    owl:annotatedProperty rdfs:subClassOf ;
    owl:annotatedTarget :CentrifugalPump ;
    prov:wasQuotedFrom <.../source/maintenance-notes> ;
    lxo:exactQuote "Boiler feed pumps and slurry pumps are types of centrifugal pump" ;
    lxo:charStart 173 ; lxo:charEnd 237 ;
    lxo:alignment "match_exact" ;
    lxo:extractedBy "claude-opus-5" .
```

`owl.provenance_of(graph, subject, predicate)` answers the review question
directly, and the annotations are plain RDF, so they survive into Fuseki and are
queryable with SPARQL alongside the ontology itself.

## Quickstart

```bash
python -m langextract_ontology                       # offline simulator, free
python -m langextract_ontology --model claude-opus-5 # needs ANTHROPIC_API_KEY
python -m langextract_ontology.tests                 # 43 offline checks
```

```python
from langextract_ontology import extract_ontology, to_turtle, provenance_of

result = extract_ontology(open("notes.txt").read(), model_id="claude-opus-5")
print(result.summary())            # counts + how much of it is grounded
print(result.provenance_table())   # assertion vs. quote vs. span, row by row
print(to_turtle(result))
```

## Layout

| module        | role |
|---------------|------|
| `schema.py`   | **what** to extract: six extraction classes, the prompt, the few-shot examples |
| `providers.py`| an Anthropic provider for LangExtract (it ships none), plus the offline simulator |
| `extract.py`  | the call, and the grounded result objects (`OntologyExtraction`, `GroundedItem`) |
| `owl.py`      | rendering to OWL/RDF with per-axiom provenance |
| `pipeline.py` | drop-in replacements for three `bottomup_ontology` steps |
| `demo.py`     | the end-to-end example above |
| `tests.py`    | offline functional tests |

### The extraction schema

Six extraction classes — `class`, `subsumption`, `object_property`,
`data_property`, `individual`, `axiom` — cover what Fig. 7.7 asks for. The
design rule that makes it work:

> the **span** (`extraction_text`) is a literal quote — it is *evidence*;
> the **payload** (`attributes`) is the normalised ontology commitment.

A paraphrased span cannot be aligned back to the document, which throws away the
only thing LangExtract offers over a plain LLM call.

### Workflow integration

`pipeline.py` reuses the *same* `step_id` values as `bottomup_ontology`, so the
LangExtract steps drop straight into the Fig. 7.7 DAG:

```python
from langextract_ontology.pipeline import build_langextract_workflow
from bottomup_ontology import run_workflow
from bottomup_ontology.state import WorkflowState

graph = build_langextract_workflow()            # same 7 nodes, 3 swapped
state = run_workflow(graph, WorkflowState(documents=[text]))
```

Text cleaning, pre-processing and evaluation keep their original heuristic
implementations, so the two technique families are directly comparable on the
same corpus and the same evaluation step. One LLM call serves all three swapped
steps: term extraction runs it and caches the result on `state.config`.

## Models

`model_id` selects the backend:

| value | backend |
|---|---|
| `None` / `"auto"` | Claude if credentials exist, else the simulator |
| `"simulated"` | offline rule-based simulator — free, deterministic |
| `"claude-*"` | Anthropic Messages API (`providers.AnthropicLanguageModel`) |
| `"gemini-*"`, `"gpt-*"`, an Ollama tag | LangExtract's own built-in providers |

LangExtract ships providers for Gemini, OpenAI and Ollama but **not** for
Claude, so `AnthropicLanguageModel` implements the `BaseLanguageModel` contract
and registers itself for `claude-*` / `anthropic-*` model ids. It defaults to
`claude-opus-5` with adaptive thinking at `medium` effort, and parallelises the
per-chunk requests.

### The offline simulator is a simulator

With no key, extraction falls back to `SimulatedOntologyModel` — lexico-syntactic
patterns (copular definitions, "types of", "such as", cardinality and
disjointness phrasings, a small relational-verb lexicon) dressed up in the same
JSON envelope a real model returns. It exists so the whole pipeline — chunking,
inference, resolution, span alignment, OWL rendering, the workflow graph — runs
deterministically at zero cost, matching the repository convention that
everything works offline.

**Its recall on real prose is poor by construction, and its numbers say nothing
about Claude.** Use it to exercise and test the plumbing; set a key to judge
extraction quality.

## Known limitations

- **Short quotes ground ambiguously.** LangExtract re-aligns each quote against
  the document, so a one-word `class` quote like `"pump"` snaps to the *first*
  occurrence and reports `match_fuzzy`. The strong provenance is on the
  sentence-length spans — subsumptions, axioms, data properties. Read
  `lxo:alignment` before trusting a span.
- **No entity resolution across documents.** Two documents saying "pump" produce
  one IRI by label match alone; no synonymy, no disambiguation.
- **No consistency checking.** The renderer will happily assert a subsumption
  and a disjointness that contradict each other. Run a reasoner over the output
  (`owlrl` works — `tests.py` does exactly this) before believing it.
- **Cost scales with `max_char_buffer` and `extraction_passes`.** Each pass is a
  full re-read of the corpus; `extraction_passes=2` doubles the bill to raise
  recall.

## Next steps worth taking

1. Feed the generated Turtle into the Fuseki store in `infra/fuseki` and query
   the provenance alongside the ontology.
2. Add a gold-standard corpus and use the existing `step_evaluation` to score
   LangExtract against the heuristic pipeline on the same text — the graph is
   already built to make that a one-line swap.
3. Route the human-in-the-loop step through `provenance_of`, so a reviewer sees
   the quote next to every candidate axiom.
