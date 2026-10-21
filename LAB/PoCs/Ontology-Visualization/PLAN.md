# Ontology visualization PoC: plan

**Status (2026-10-20):** Phase 0 (this PoC) implemented, with offline tests and the
algorithm-level benchmarks. Studies at the idiom and domain levels are not yet run.
Evidence base: [`knowledge/Ontology Visualization/reports/Ontology visualization for SIP.md`](../../../knowledge/Ontology%20Visualization/reports/Ontology%20visualization%20for%20SIP.md).

## Question

Can a bounded, overlay-rich TBox ego view built on SIP's operations help a reviewer at the
review gate more than the class tree and the pending-commit list alone, at FIBO scale and
within the budget of a Canvas renderer?

## Design commitments (from the research)

| # | Commitment | Why (report section) |
|---|---|---|
| D1 | **Start from search, not an overview**; expand on demand under a hard cap; hold back hubs behind a confirmation (big-node guard) | Every system that scales does this (van Ham & Perer 2009; Bloom, Siren, Reactodia) |
| D2 | **Restrictions as tagged edges** (`has part (some)`); anything more nested becomes a node badge with Manchester text | No notation draws FIBO's class expressions completely (VOWL gaps); Chowlk and OWLGrEd conventions |
| D3 | **Overlays keyed by IRI from existing SIP data:** staged diff, inferred edges, findings, CQ coverage | The gap no maintained tool fills |
| D4 | **Through `Platform.call` only**: `viz.*` operations registered with SIP's decorator and served by SIP's own FastAPI app | CLAUDE.md rule; makes Phase 1 a move, not a rewrite |
| D5 | **Vendored, all-MIT, no build step**: Cytoscape.js 3.34.4 + cytoscape-dagre 4.0.1 (bundles @dagrejs/dagre) | The workbench runs offline; licence constraints |
| D6 | **Identity is never colour alone**: `+`, `−`, `~`, `inferred`, `⚠B/M/m/i`, `⊥`, CQ `✓/✗` beside every colour; a table view | Accessibility; print |
| D7 | **The class tree stays the baseline**, not a strawman | The evidence favours trees for lookup (Fu et al.) |

## Hypotheses and pre-declared thresholds (algorithm level)

These are conventional HCI targets, not evidence-derived. They were declared before the
benchmarks ran.

| ID | Measure | Threshold | How |
|---|---|---|---|
| B1 | Extraction latency, `viz.neighbourhood` via `Platform.call`, FIBO, default view (hops 2, cap 40) | median < 50 ms, p95 < 150 ms (warm index) | `python -m ontoviz.bench extract` |
| B2 | Extraction at cap 1,000 (reach mode) | median < 500 ms | same |
| B3 | Index build over all of FIBO (~3,000 classes) | < 5 s | same |
| B4 | Interactive frame rate, labelled ego view, ≤ 300 nodes | median ≥ 30 fps during scripted pan/zoom | `python -m ontoviz.bench browser` |
| B5 | Selection latency, ≤ 300 nodes | p95 < 100 ms | same |
| B6 | Data-to-first-paint including dagre layout, ≤ 300 nodes | < 1 s | same |
| B7 | Where Canvas stops being interactive (labelled, synthetic) | report the size where median fps < 30 (no threshold: this sets the Phase 3 WebGL trigger) | same |

## Functional checks (offline tests, `tests/test_ontoviz.py`)

* Cap, connectivity and hub guard hold.
* DOI ordering is deterministic.
* Restriction tags and `optional` (min 0) are correct.
* Complex axioms become badges.
* Staged add, delete and modify are tagged against real staged commits.
* Inferred edges are transitively reduced.
* CQ terms are linked, including "fixed by staged".
* The PDP gates every `viz.*` call.
* The payload is accepted by the Playground's `Ontology.from_dict`.
* The SVG is well-formed and deterministic.
* The HTTP route works.

## Next studies (not run)

| Level | Study | Gate |
|---|---|---|
| Idiom | Formative within-subject study, 8 to 12 participants, comparing three conditions: (a) `browse.classTree` with search plus the pending list, (b) the ego view without overlays, (c) the ego view with overlays. Tasks are stratified: lookup, relationship, overview, seeded-defect detection, staged-commit review. Accuracy is the primary measure; time, SUS and NASA-TLX are secondary. | No loss against (a); gains on the review tasks |
| Domain | Think-aloud sessions with ontology engineers and finance SMEs on review-gate scenarios | Themes recorded |
| Assisted | Trust calibration with seeded wrong agent answers. This needs live models, so **ask before running**. | Before Phase 4 |

## Phases to SIP

0. **This PoC.** Exit when B1–B6 pass and the idiom study shows no loss against the baseline.
1. **Read-only integration.** Move `sip_ops.py`, `index.py`, `neighbourhood.py`,
   `overlays.py`, `contract.py` and `svg.py` into `sip/semantic_intelligence/viz/`. Vendor
   the JS under `api/static/`. Add a Graph tab to `workbench.html`. Update the AD viewpoint
   and the SysML model (FR-VIZ-01..03), and pass `sysml_check.py`.
2. **Review-gate overlays in the workflow.** Accept and reject from the graph context (the
   PoC already does this through `validation.accept`/`reject`). Link selection across the
   pending list, findings and history.
3. **Scale and overview.** A precomputed FIBO module overview per release. An ABox view on
   WebGL (sigma.js or `@falkordb/canvas`) beyond the B7 size. Layouts stored as IRI-keyed
   artifacts.
4. **Assisted and editing.** Natural language turned into a view spec, rendered
   deterministically. Diagram edits emitted only as staged commits.
