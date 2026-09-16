# Ontology Construction Processes

Prototype implementations of the ontology-creation processes and measurement
strategies in
[`docs/Ontology Definition/Ontology Construction Approaches and Metrics.pdf`](../docs/Ontology%20Definition/)
— *"Strategic Ontology Engineering in the Era of Generative AI: Frameworks,
Applications, and Measurement Strategies"*.

```bash
python -m pytest ontology_construction -q     # 72 passed
python ontology_construction/demo.py          # end-to-end walkthrough
```

Runs **offline and deterministically**. The LLM is an injectable `Extractor`
whose default is rule-based — the same convention `bottomup_ontology/` uses — so
the processes, gates and metrics are testable with no API key. Swap in
`LLMExtractor` for real work; nothing else changes, which is the point.

---

## What the report describes, and what is implemented

| Report section | Module | Implemented |
|---|---|---|
| **NeOn** — nine scenarios for ontology *networks* | `neon.py` | All 9 scenarios as data; a selector that reports which the available resources justify; step functions for scenarios 1, 2, 3, 7, 8, 9 |
| **LOT** — four iterative sprints | `lot.py` | Requirements (CQ-gated) · implementation (Chowlk-style UML → OWL) · publication (content negotiation + docs) · maintenance (issues + CQ regression) |
| **LLMs4OL** — three OL subtasks | `llms4ol.py` | Term typing · taxonomy discovery · non-taxonomic relations; AbA vs single-shot prompting; the O(n²) relation bound made explicit |
| **NeOn-GPT** — hybrid gated pipeline | `pipeline.py` | 11 lifecycle stages, each followed by deterministic gates that pass / repair / reject |
| **OntoAxiom, cohesion, structural, five criteria** | `metrics.py` | Per-axiom-type P/R/F1 with macro *and* micro; semantic internal cohesion; attribute richness, C/R ratio, equivalence ratio; the five criteria scored **from evidence** |
| **OOPS!, Themis, SHACL vs OWL** | `validation.py` | 15 OOPS! pitfalls by real catalogue ID; Themis CQ testing via lexico-syntactic patterns; CWA shape validation and an OWA/CWA contrast |
| **CI/CD drift gate** | `pipeline.py` | The four stages: syntax → OOPS! → Themis → SHACL |

Processes compose as `networkx` DiGraphs of step classes and as agent tools,
exactly as in `bottomup_ontology/`:

```python
import ontology_construction as oc

state = oc.ConstructionState(domain="lending", documents=[...], use_cases=[...])
state = oc.run_workflow(oc.build_hybrid_workflow(), state)   # NeOn-GPT, gated
print(oc.DriftGate().run(state))
```

`configure_workflow(process=...)` builds `neon` · `lot` · `llms4ol` · `hybrid` ·
`validation`. `tool_specs()` and `ToolRegistry` expose every step to an agent —
which is how the Ontology Builder's authoring copilot (`OB.AGT.03`) can *drive*
these processes rather than reimplement them.

---

## The three decisions that carry the design

### 1. Gates are the product, not the generation

The report's central practical claim is one sentence:

> "the outputs at each stage of the NeOn-GPT pipeline undergo automated syntax
> validation, consistency checks, and error resolution using external
> deterministic tools before proceeding to the next step."

So every generative stage is followed by gates that can **pass**, **repair** or
**reject**, and every decision is recorded on the state — the boundedness is
auditable afterwards, not asserted.

| Gate | Answers | On failure |
|---|---|---|
| `vocabulary_gate` | are both endpoints terms we actually extracted? | reject — this is the anti-hallucination gate |
| `grounding_gate` | do the endpoints co-occur in the corpus? | reject |
| `acyclicity_gate` | is the taxonomy acyclic? (OOPS! P06) | repair: drop the weakest edge, and **count it** |
| `syntax_gate` | does it serialise, re-parse, and use well-formed IRIs? | reject |
| `consistency_gate` | any critical pitfalls? | reject |

Demo section 5, verbatim:

```
before gates: [('mortgage','loan'), ('loan','derivative')] [('loan','orbits','saturn')]
vocabulary_gate    rejected=2  2 edge(s) referenced unknown terms
surviving:    [('mortgage','loan')] []
```

Repairs are counted deliberately. A pipeline that repairs constantly is visibly
untrustworthy, and hiding that behind a clean output is how the "60–80% time
reduction" the report cites turns into rework.

### 2. Metrics report where they are weak

The report records that axiom scores vary enormously — "for subclass axioms, the
well-known FOAF ontology achieves a score of 0.642, while the music ontology
scores only 0.218". A single aggregate F1 hides exactly that. So the scorecard
is per axiom type, reports **macro and micro**, and names the weakest type:

```
class          P=0.56 R=1.00 F1=0.71  (support 5)
subclass       P=1.00 R=1.00 F1=1.00  (support 2)
disjointness   P=0.00 R=0.00 F1=0.00  (support 1)
macro-F1 0.452 | micro-F1 0.629 | weakest: disjointness (0.00)
```

Micro-F1 of 0.63 alone would have read as adequate. It is dominated by classes
and subclasses; disjointness has collapsed entirely, which is what you needed to
know.

The five criteria are scored **from evidence already on the state** — a CQ that
passed, a pitfall that fired, a definition that exists — and each carries the
evidence string that produced it. A criteria score with nothing behind it is an
opinion.

### 3. OWA and CWA are shown diverging, not described

The report's architectural point is that OWL cannot be the data gatekeeper,
because under the Open World Assumption a missing fact "merely means the fact is
currently unknown". `compare_owa_cwa()` runs both over one dataset:

```python
shapes = [Shape("Loan", required_properties=("principal",))]
compare_owa_cwa([{"id": "L1", "type": "Loan"}], shapes)
# owa_rejections: 0   — OWL infers an unnamed filler rather than failing
# cwa_rejections: 1   — SHACL rejects it
# gatekeeper:     "SHACL/CWA"
```

`_shapes_from_draft()` derives shapes from declared domains — PoolParty's
OWL→SHACL transform in miniature, which the report notes happens "without manual
intervention".

---

## Five bugs this prototype found in itself

Written down because they are the failure modes of hybrid pipelines generally,
and each now has a regression test.

1. **Case-variant duplication.** The expert wrote `Loan`; an ODP and the learner
   produced `loan`. Merging them as two classes manufactured OOPS! **P02** and
   **P19** out of nothing — a *critical* pitfall caused entirely by the
   integration, not by either input. Fixed by canonicalising onto the name a
   human chose.
2. **Non-deterministic canonicalisation.** `OntologyDraft.classes` is a `set`,
   so `{c.lower(): c for c in classes}` picked a winner in arbitrary iteration
   order — the same input canonicalised to `Loan` on one run and `loan` on the
   next. Fixed by sorting, with expert names taking precedence.
3. **Stopword stripping applied to model output.** `_norm` dropped stopwords
   from terms an *extractor returned*, so a model answering `"a"` or
   `"act of god"` had its answer silently rewritten — corrupting the very output
   the gates exist to judge. Split into `_norm` (light) and `_norm_candidate`
   (used only for generated n-grams).
4. **A stemmer manufacturing non-words.** `causes → caus`. The `-es` rule now
   fires only after a sibilant stem (`classes → class`, `boxes → box`).
5. **A lenient syntax gate.** rdflib *warns* about an IRI containing spaces and
   parses anyway, so a gate that only caught parse errors passed a graph that
   could not be serialised again. IRIs are now checked explicitly — otherwise it
   is a parse attempt, not a syntax gate.

---

## Scope and limitations

**The extractors are stand-ins, not NLP.** `HeuristicExtractor` uses Hearst
patterns, head-noun composition and relation cue words. It is faithful to the
*structure* of the three LLMs4OL subtasks, not their accuracy — the same
contract `bottomup_ontology` states. It will miss relations no cue word covers
and propose n-grams that are not concepts. That is what the gates, the
`neon.restructure` pruning pass and the metrics are for.

**15 of 40+ OOPS! pitfalls.** The implemented ones are those detectable from the
draft without a reasoner or a lexical resource: P02, P03, P04, P06, P08, P10,
P11, P13, P19, P22, P24, P25, P30, P32, P41. Severities follow the source
report, which names P03 and cyclic hierarchies (P06) as typical *critical*
issues.

**Themis patterns are a starter set.** Six lexico-syntactic patterns —
subsumption, relation, attribute, enumeration, existence, count. A CQ matching
none is reported as **unformalised**, never silently passed: an untestable
requirement is a gap in the ORSD, not a success.

**The shape validator is not SHACL.** It implements `sh:minCount` and
`sh:datatype` over plain dicts to make the OWA/CWA contrast executable without a
dependency. Use `pySHACL` in production; the `Shape` model maps onto it
directly.

**Scenarios 4, 5 and 6 have no dedicated step.** They are re-engineering and
merging variants of scenario 3, and implementing them meaningfully needs the
alignment machinery specified as `OB.MAP.*` in
[`architecture/ontology_builder/`](../architecture/ontology_builder/). They are
modelled in `SCENARIOS` and reported by the selector, so the gap is visible
rather than silent.

---

## Relationship to the rest of the repository

* **`bottomup_ontology/`** — the Keet Ch. 7 text→ontology pipeline. Same design
  contract (step classes as networkx nodes, one function per step, agent tools).
  That package covers the *linguistic* pipeline; this one covers the
  *methodological* processes around it.
* **`ontology_engineering_capabilities/`** — these processes realise `T.DA.1`
  (conceptualisation), `T.DA.2` (formalisation), `T.DA.4` (bottom-up learning),
  `T.DA.5` (design patterns), `B.SE.2` (competency questions), `T.QV.1`–`T.QV.4`
  (validation, testing, metrics, evaluation) and `T.OO.3` (CI/CD).
* **`architecture/ontology_builder/`** — the Builder's `OB.QLT.03` (competency
  questions as executable tests) is the gap this package fills; `OB.AGT.03`
  (authoring copilot) and `OB.AGT.06` (CQ agent) drive these steps through
  `tools.py`; `OB.S2R.02` is `bottomup_ontology` feeding the same staging model.
* **`architecture/ontology_assistant/EVALUATION.md`** — the CQ gold-set and
  metric harness this package's `metrics.py` is compatible with.
