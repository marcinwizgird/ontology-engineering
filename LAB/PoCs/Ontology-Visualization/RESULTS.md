# Ontology visualization PoC: results

**Date:** 2026-10-20
**Machine:** one Windows 11 workstation
**Scope:** the algorithm level of Munzner's nested model only, plus functional tests. The
studies at the idiom, domain and assisted levels in [PLAN.md](PLAN.md) have **not** been
run, so nothing here shows that the view helps reviewers. It shows that the view is fast,
correct and bounded.

Raw data: `artifacts/bench_extract.json` and `artifacts/bench_browser.json`. The latter
holds 3 runs with the median per scene, plus the raw runs.

## 1. Pre-declared thresholds

The thresholds were written into PLAN.md before any benchmark ran.

| ID | Measure | Threshold | Result | Verdict |
|---|---|---|---|---|
| B1 | `viz.neighbourhood` via `Platform.call`, FIBO, default view (hops 2, cap 40), 30 seeds | median < 50 ms, p95 < 150 ms | median **1.5 ms**, p95 **2.0 ms** | pass |
| B2 | Same at cap 1,000 (hops 8, hub guard off) | median < 500 ms | median **23 ms**, p95 25 ms (payload 2.5 MB) | pass |
| B3 | Index over all of FIBO (3,081 classes, 7,374 typed edges) | < 5 s | **2.5 s**, including materialising the stable and staged views; 0.7 s for the index alone | pass |
| B4 | Frame rate, labelled FIBO ego view ≤ 300 nodes, scripted pan/zoom | median ≥ 30 fps | mean **118–120 fps**, p5 ≥ 93 | pass |
| B5 | Selection latency ≤ 300 nodes | p95 < 100 ms | p95 **≤ 12 ms** | pass |
| B6 | Data-to-first-paint incl. dagre layout, ≤ 300 nodes | < 1 s | **43 ms at 100 nodes; 1.42 s at 300 nodes** (dagre takes 1.34 s; that scene is a hub neighbourhood with 1,211 edges) | **fail at 300** |
| B7 | Where labelled Canvas stops being interactive (synthetic) | report only | 2,000 nodes: mean 92 fps, p5 35. **5,000 nodes: mean 45 fps, p5 13.** 10,000 nodes: mean 5 fps | WebGL trigger ≈ **5k nodes** |

Every scene, as the median of 3 headless Chrome 154 runs:

| Scene | Nodes | Edges | Layout | First paint | fps mean (range) | fps p5 | Select p50 / p95 | Heap |
|---|---|---|---|---|---|---|---|---|
| FIBO ego, cap 50 | 50 | 49 | dagre 12 ms | 24 ms | 120 (120–120) | 114 | 8 / 9 ms | 9 MB |
| FIBO ego, cap 100 | 100 | 99 | dagre 30 ms | 43 ms | 120 (120–121) | 114 | 8 / 10 ms | 9 MB |
| FIBO ego, cap 300 | 300 | 1,211 | dagre 1,339 ms | 1,424 ms | 118 (114–121) | 93 | 8 / 12 ms | 35 MB |
| FIBO ego, cap 1,000 | 1,000 | 2,652 | dagre 4,956 ms | 5,136 ms | 93 (87–94) | 47 | 21 / 28 ms | 83 MB |
| synthetic 2,000 | 2,000 | 2,999 | preset | 275 ms | 92 (90–93) | 35 | 27 / 33 ms | 91 MB |
| synthetic 5,000 | 5,000 | 7,498 | preset | 662 ms | 45 (35–46) | 13 | 9 / 16 ms | 116 MB |
| synthetic 10,000 | 10,000 | 14,998 | preset | 5,560 ms | 5 (5–5) | 2 | 139 / 199 ms | 300 MB |

**Caveats.**
* Headless Chrome is not capped at the display refresh rate, so fps above 60 means
  headroom, not visible smoothness.
* No GPU flag was set, so rendering may be software-only.
* The results come from one machine with 3 runs.
* The FIBO scenes grow outwards from the biggest hub (`RegisteredSecurity`, degree 226).
  This is a worst case for edge density.
* The synthetic graphs use preset positions, so they measure rendering, not layout.

**What B6 means.** Rendering is cheap at ontology-view sizes; the bottleneck is the
layered layout. The default cap of 40 stays well inside the budget (50 nodes take 24 ms
in total). Three ways to fix views of 300 nodes or more, for Phase 1 or 3:
1. run dagre in a Web Worker so the UI never blocks;
2. lay the view out on the server once per revision and send preset positions;
3. switch to fCoSE for dense scenes.

## 2. Functional results

All 15 offline tests pass: `python -m pytest tests -q`, about 5 s, FIBO included. They show:

* **Bounded views.**
  * The cap holds and every view stays connected.
  * A hub with 50 children is guarded and held back until the user confirms the expansion.
  * The DOI ordering is deterministic.
* **Honest notation.**
  * Restrictions become tagged edges: `some`, `only`, `min 1`, unions as one edge per
    member marked `[or]`.
  * The conjuncts of a definition are drawn as necessary conditions, marked `≡`.
  * Complements and union equivalences become Manchester-text badges, and data
    restrictions become attributes.
* **Overlays checked against real staged commits** from a machine principal:
  * The new class and its edge are `staged_add`, and the removed axiom is `staged_del`.
  * The touched class is `modified` and links to the commit and its agent.
  * After the commits are accepted, all of these become `asserted`.
* **Inference shown without noise.** Only *new direct* superclasses appear. The overlay
  reduces owlrl's closure transitively and drops edges that an asserted equivalence
  already implies. In the demo, the naive view drew Car→Automobile, ElectricCar→Automobile,
  Automobile→Vehicle and others; after the fix, only the union-derived edges
  Car→MotorVehicle and Truck→MotorVehicle remain.
* **Coverage by competency questions.** CQs are linked to the classes their SPARQL names.
  The overlay also says which failing CQs the staged commits would fix:
  `cq_Truck_Engine` fails now and passes once the commits are accepted.
* **Governance.**
  * All five `viz.*` operations are reads under `rdf` and are listed by
    `GET /operations`.
  * An unbound principal gets `AuthorizationError`.
  * The HTTP layer maps an unknown principal to 401 and bad arguments to 422.
* **One contract.** The Ontology-Playground model accepts the payload unchanged
  (`Ontology.from_dict`).
* **Static artifact.** The SVG is deterministic and well-formed. State is never shown by
  colour alone (`+`, `−`, `~`, `inferred`, a severity letter).

## 3. Findings from FIBO (new evidence)

* **17% of FIBO's restriction edges are `min 0`.** That is 400 of 2,410. A `min 0`
  restriction is a tautology: FIBO uses it to document expected properties. Drawn as
  constraints, these edges dominated the `Loan` view. As an `optional` kind that is off by
  default, the 40-node view became readable (screenshots in `artifacts/`). This is a
  notation decision VOWL and Chowlk do not make.
* **10% of FIBO classes carry axioms that no edge can show.** That is 317 of 3,081:
  nested restrictions, complements, union equivalences. They appear as badges with
  Manchester text in the side panel. This is the honest trade-off the report predicted:
  the view looks less complete than WebVOWL demos and says so.
* **The hub guard is necessary, not optional.** The maximum degree is 226. Without the
  guard, any view that touches `RegisteredSecurity`, `MonetaryAmount` or `ExplicitDate`
  fills the cap with siblings.
* **The findings overlay is noisy on FIBO.**
  * ICV reports 29,332 findings, mostly `no label in en` and `no language tag`, because
    FIBO's labels carry no language tag.
  * As a result, nearly every node shows `⚠M`.
  * Phase 2 needs per-check filtering, or a project-level suppression of accepted
    findings, before this overlay is useful on imported ontologies.
* **The reasoning overlay depends on classification having run.** FIBO is not classified
  in the PoC (owlrl over 132k triples was not attempted), so the FIBO views show no
  inferred edges.

## 4. Observations about SIP itself (for the backlog, not fixed here)

| # | Observation | Where |
|---|---|---|
| S1 | When a project is created with `validation=True`, its own `governance.createProject` commit by `system` is *staged* and appears in `validation.pending` until someone accepts it | `platform.create_project` + `ChangeTracker.commit` |
| S2 | `reasoning.classify(staged=True)` returns a preview with `revision = 0`: it builds a fresh `ReasonerManager` without the tracker's revision, so previews cannot be told apart by revision | `platform.classify_op` |
| S3 | `io.loadRDF` needs `rdf` C, so an *ontologist* cannot load RDF (a project manager can) | the role definitions |
| S4 | No operation returns the staged inferred graph or a class-level neighbourhood. `viz.neighbourhood` fills the gap by reading `ctx.preview` inside an operation, which is what Phase 1 would formalise | — |

## 5. Not yet shown

* That reviewers find staged-commit problems faster or more accurately with the overlays
  than with `browse.classTree` plus the pending list. This needs the idiom-level study.
* Behaviour on SKOS-heavy projects. `broader` is supported and tested only through the
  index.
* Layout stability across FIBO releases. Layouts are not yet stored as IRI-keyed
  artifacts.
