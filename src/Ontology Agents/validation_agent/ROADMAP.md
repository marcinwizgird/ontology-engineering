# Ontology Validation Agent: Staged Development

The normative model is [`models/ova_development.sysml`](models/ova_development.sysml).
Its `state def DevelopmentProgramme` moves between stages only when a **measured** guard
holds. There are no date-driven transitions. Each stage produces what the next one
stands on:

```
S0 spec ─► S1 deterministic tool ─► S2 evaluation data ─► S3 agent + DSPy ─► S4 self-evolution
             (control, critic,        (gold labels by        (held-out gain        (gated, additive,
              reward)                  construction)          > noise)              reversible)
                                                                  ▲                     │
                                                                  └──── gateRegression ─┘
        R1 deterministic product ──────────► R2 agentic ──────────► R3 self-evolving
        (after S1c)                           (after S3)              (after S4)
```

Each release must pass `ReleaseReadinessCase` (V-REL). The cross-cutting productisation
track that gets each release there is described at the end of this document.

---

## S0: Specification (this commit)

| deliverable | file |
|---|---|
| Requirements, use cases, stakeholders | `models/ova_requirements.sysml` |
| Logical architecture, behaviour, trust constraints | `models/ova_architecture.sysml` |
| Stages, datasets, optimisation, evolution | `models/ova_development.sysml` |
| 131-check catalogue (source of truth) | `spec/check_catalogue.py` → `CHECK_CATALOGUE.md` |
| Specification and architecture | `SPECIFICATION.md`, `ARCHITECTURE.md` |

**Exit guard `catalogueValidated`:** `python spec/build_docs.py` exits 0. The checks:
unique ids; every non-info, non-human check names a mutation operator; adjudicated checks
are capped below blocker; every requirement is satisfied or verified. **Status: met.**

---

## S1: Deterministic tool

The goal is a complete, offline, deterministic validator. No LLM is involved, and the
stage stands on its own as a useful product (CLI, CI gate, MCP tools).

### S1a: MVP and reference conformance (26 checks marked `S1a`)

1. `workspace.py`, `engine/loader.py`, `engine/profile.py` (port `classify_spectrum`),
   `engine/registry.py` (load the catalogue, filter by profile).
2. Detectors for the `S1a` checks: SYN-01/02/03/06, DECL-01..04, DL-02/08, RSN-01/02/08
   (owlrl + probe individuals), SHC-02/08, HIER-01/02/05/08, PROP-01, LEX-01/02,
   SKOS-05, META-01, METRIC-01/02.
3. `engine/policy.py` with the policy packs `registry-default-v1` and `ci-lenient-v1`.
   `engine/report.py` outputs JSON and Markdown.
4. `tools/belt.py` (the tools from §8 of the specification) and `cli.py`
   (`validate`, `gate`).
5. Fixtures: `tests/fixtures/<check_id>/{positive,negative,near_miss}.ttl` for every
   S1a check.

6. **Reference Conformance Suite** in CI. It has four parts: the W3C SHACL Core test
   cases; the W3C OWL 2 RL consistency and inconsistency cases; a first golden corpus of
   about 30 real ontologies with expected findings signed off by a curator; and a
   differential harness against ROBOT `report`, HermiT and qSKOS.

**Exit guard `referenceConformant` (V-S1a, OVA-E03):** 100 % on the applicable W3C cases.
Golden corpus recall and precision both 1.0 for S1a checks. Every oracle disagreement
triaged and recorded. Every S1a fixture passes. Two runs give identical finding sets.

### S1b: Full catalogue (101 checks marked `S1b`)

1. The remaining structural families: DECL, DL, HIER, PHIER, PROP, SKOS, META, ABOX, CQ
   (port `run_themis`), EVO (asserted diff), METRIC.
2. `engine/shacl.py`: supplied shapes, SHACL-for-SHACL, `TboxShapeDeriver` (SHC-03), the
   house pack, SHC-04..09.
3. Candidate generators for the adjudicated checks (`status=candidate`, no LLM yet):
   cue lexicons, head-noun extraction, genus-differentia comparison.
4. Fuseki and Playground sources, RDF report output, `mcp_server.py`.
5. Performance: indexing of SPARQL-heavy families, batched probes. Profile on FIBO.

**Exit guard `fixturesGreen` (V-S1b):** all fixtures pass (positive fires, negative and
near-miss do not). Determinism test passes. FIBO deterministic run ≤ 600 s (OVA-Q02).
Every check has a reference page with a worked example, generated from the catalogue
(`docs/checks/<id>.md`).

### S1c: Reasoning depth (4 checks marked `S1c`, plus the DL backend)

1. `engine/axioms.py` (axiom view with stable ids and signatures) and
   `engine/modules.py` (⊥, ⊤ and STAR syntactic locality modules), differentially tested
   against ROBOT `extract --method STAR`.
2. `engine/justify.py`: expand-shrink **inside the STAR module** of the entailment's
   signature, a hitting-set tree for further justifications, memoised;
   `engine/rootcause.py`: root and derived classification, clustering.
3. The optional `dl` backend (owlready2 + HermiT; Pellet is excluded under OVA-P04)
   behind a Java probe. RSN-07, EVO-02/03 (entailed diff).
4. HIER-07 inherited-restriction analysis is cross-checked against the reasoner on every
   fixture.

**Exit guard `justificationsMinimal` (V-S1c):** every justification on the fixture and
mutant sets is minimal, i.e. removing any one of its axioms removes the entailment.
Justifications found inside the module equal the full-ontology ones on a sampled set.
p95 ≤ 30 s per root on FIBO (OVA-Q05). Root clustering reduces the findings-to-causes
ratio on multi-fault fixtures as expected.

**Risks:** RL incompleteness on TBox-only ontologies (mitigated by probe individuals and
RSN-08); justification cost on large modules (mitigated by computing them only for roots
and with a budget); owlready2 world isolation (use one `World()` per workspace).

---

## S2: Evaluation datasets

The goal is gold labels for every check and every LLM role. Where possible they are
labels **by construction**, so the corpus can grow without people labelling it.

### 2.1 Seed ontologies (`SeedOntology`)

| source | why | notes |
|---|---|---|
| FIBO modules (vendored in `Ontology Repository/FIBO`) | real, large, OWL 2 DL, rich annotations | known to LLMs, so scrambled variants are needed |
| gist, QUDT, schema.org, selected OBO Foundry ontologies | widely deployed enterprise and scientific vocabularies; varied styles and profiles | licence check per source |
| Design-partner ontologies | the real target distribution | only under the partner's data agreement; never in shared splits without consent |
| Public SKOS schemes (e.g. small EuroVoc / UNESCO extracts) | SKOS family coverage | licence check |
| Synthetic seeds per profile (vocabulary, taxonomy, thesaurus, formal, ABox+shapes) | coverage of every `applies` profile | generated, then certified |

**Certification:** run S1 on each seed and record its existing findings as the
`certifiedBaseline`. A curator signs off that baseline. From then on, any finding outside
the baseline on a mutant is attributed to the mutation.

### 2.2 Mutants (`MutantSet`): gold labels by construction

* One **mutation operator** per catalogue `mutation` name (116 distinct operators today), in
  `evaluation/mutations.py`: `graph -> (graph', {check_ids, focus}) | None`. Each
  operator is seeded, checks its own applicability, and is minimal (one conceptual edit).
* **Single-fault** mutants: every applicable (operator, seed, site) up to a cap per seed.
* **Multi-fault** mutants: 2–5 operators per mutant. Interacting faults (e.g.
  `disjoint-child-parent` + `add-second-parent`) are labelled through the engine, because
  root-cause gold comes from the operator provenance.
* **Near-miss** mutants: edits that resemble defects but are policy-legal (declared
  punning, a waived disjointness, declared multi-axis classification). These measure
  precision.
* **IRI-scrambled** twins: local names and labels permuted consistently. The gap between
  a twin's score and the original's measures how much the LLM relies on remembering
  famous ontologies rather than reading them.
* **Repair gold:** the inverse of each mutation is one valid repair. Since repair is
  scored by the engine, gold is needed only to measure minimality.

**Kill rate** (OVA-E01): for each deterministic check, the share of its operator's mutants
on which it fires. The target is **1.0**. A surviving mutant is either a detector bug or
an operator bug, and both get fixed in S2.

### 2.3 Human-labelled sets

| set | content | protocol | size target |
|---|---|---|---|
| `AdjudicationSet` | candidates from the 16 LLM-adjudicated checks, on real seeds and mutants | two experts label independently, a third resolves; κ reported per check | ≥ 60 per check (≈ 1 000) |
| `ReportLabelSet` | reports rated on a rubric (correctness, actionability, grounding, tone) | two raters; used only to validate the judge | ≥ 60 reports |
| `RealDefectSet` | defects mined from public ontology version histories: commits whose diff removes a finding | pre-commit = input, the commit = gold repair | ≥ 100 cases |
| `RegressionCorpus` | golden corpus + accepted production cases (with consent), curator-signed verdicts | verdicts may only change with a policy version change | grows with every escaped defect |

### 2.4 Splits and cards

* **Grouped by seed** (no seed appears in two splits), stratified by family and profile.
* Splits: `train` (optimiser), `dev` (selection and noise), `test` (reported once per
  release), `holdout-gate` (read only by the S4 gate; never mined, never reported).
* `DatasetCard`: version, SHA-256 per split, counts by check, family and profile, known
  bias (for example over-representation of FIBO), and licences.

**Exit guard `datasetsFrozen` (V-S2):** kill rate 1.0 for every deterministic check.
Zero non-baseline findings on certified seeds (OVA-E02). κ ≥ 0.7 on `AdjudicationSet`
(checks below that are demoted to `human`). Splits hashed and cards published.

---

## S3: Agentic system and DSPy optimisation

The goal is LLM modules that measurably add value over the S1 control on the fields only
they can produce (adjudication, explanation, repair, report). Value is measured on a
held-out split, priced, and must beat the noise.

### 3.1 Build (baseline)

1. `agent/signatures.py`: one DSPy `Signature` per module (§7 of the specification).
   Typed outputs: adjudication labels from a fixed vocabulary, patches as triple lists.
2. `agent/programs.py`: `dspy.Module`s. Tools are called in code ("tools measure, the
   model interprets"). One predictor per module. All LLM traffic goes through
   `agent/gateway.py` (OVA-P02).
3. `agent/critic.py`: overrides decidable fields and records corrections.
   `agent/judge.py`: rubric judge. `agent/investigator.py`: bounded LangChain agent over
   the tool belt.
4. `evaluation/scorer.py` + `rulebook.py` (§10 of the specification). Notes say what was
   expected, field by field.
5. Hand-written baseline instructions, measured on `dev` with `llm.meter` cost.

**Guard `judgeValidated`:** judge vs `ReportLabelSet` agreement and κ ≥ 0.6. If it fails,
the judge is not used as a metric. Report optimisation then falls back to grounding and
critic-correction metrics.

### 3.2 Optimise (per module, `action def OptimiseModule`)

| module | metric (feedback text for GEPA) | optimisers | notes |
|---|---|---|---|
| FindingAdjudicator | F1 vs `AdjudicationSet`; notes name the cue that misled | GEPA, MIPROv2, BootstrapFewShot | the largest volume, so cost-sensitive (Haiku) |
| RepairProposer | engine-verified repair score, charged per attempt; notes list surviving targets and new findings | verifier-driven retry loop first (pass@1 → pass@3 baseline), then GEPA on the inner predictor | gold-free, so it can train on unlimited mutants |
| RootCauseExplainer | validated judge + grounding (named axioms ⊆ justification) | GEPA | — |
| ReportWriter | validated judge + grounding + critic corrections | GEPA | — |
| CheckPlanner | `quality − λ·cost`; regret vs MDP V\* | GEPA or a policy table | may end up deterministic if the MDP's optimal policy is simple |

For each module:

* **Budgeted runs.** `max_metric_calls` is fixed in advance and cost is metered.
* A **blind-metric ablation** (score only, no notes) prices the value of the feedback.
* A **noise study**: ≥ 3 uncached repeats of the baseline and of the best candidate on
  `dev`. The spread sets `min_gain` for S4.
* A **held-out report** on `test`: n, mean, spread, USD, before vs after, and the
  instruction diff saved under `artifacts/`.
* **Model routing**: re-run the winning program on the cheaper model, and keep it if the
  score stays within the noise.

### 3.3 Architecture comparison (V-S3)

On `test`, with the same scorer: **agent** (Investigator doing everything) vs **program**
vs **program + critic**. Columns: score, cost, tool calls, critic corrections, time. The
default architecture is confirmed or changed on this evidence.

**Exit guard `gainExceedsNoise` (V-S3, OVA-E04, OVA-Q03):** the optimised system beats
the deterministic-only control on adjudication F1 and repair score by more than the
measured spread. Mean cost ≤ $0.25 per submission. Zero uncorrected critic deviations in
published reports. Skill cards saved for every module.

---

## S4: Self-evolution

The goal is a system that gets better from use without drifting, and that grows its
deterministic core from confirmed experience.

### 4.1 Signals

* **Expert feedback** through `FeedbackPort`: confirm or dismiss each finding, accept or
  reject each repair, "missed defect" reports with a focus IRI.
* **Critic corrections** (the model disagreed with the engine).
* **Verifier rejections** (repairs that failed `verify_patch`).
* **Cost and latency** per run.

These are stored as `Episode`s in the tenant's `ExperienceBuffer`. Cross-tenant learning
uses only the opt-in shared pool (OVA-P01).

### 4.2 The loop (`action def EvolveRound`)

```
mine (cluster failures by rule id × check id)
  → propose  (instruction/demos via GEPA · threshold recalibration · house shape · new check + operator)
  → sandbox  (new checks: precision on certified seeds, recall on confirmed cases, runtime, kill rate)
  → gate     (holdout-gate gain ≥ min_gain; regression suite: RegressionCorpus verdicts unchanged, fixtures, kill rate)
  → approve  (curator, for checks and house shapes: diff + evidence pack)
  → promote  (version bump, skill card, previous version kept)
  → monitor  (critic corrections, dismissal rate, cost; auto-rollback on breach)
```

### 4.3 Check synthesis: graduating judgement into rules

When experts repeatedly confirm a defect class that no deterministic check catches
("missed defect" reports clustering on one pattern), synthesis proceeds as follows:

1. **Split** the confirmed examples into a synthesis part and a held-out part.
2. **Write the detector.** Synthesise a candidate SPARQL or SHACL detector from the
   synthesis part.
3. **Write the operator separately.** In a separate call, from the defect description
   only (no access to the detector, and preferably by a different model), synthesise the
   **mutation operator** and the fixtures (positive, negative, near-miss).
4. **Sandbox both.** Run the non-circular validation of SPECIFICATION §11 (OVA-E07):
   * held-out recall;
   * blind expert confirmation of sampled mutants;
   * non-vacuous, localised `VersionDiffer` diffs, plus a change in the entailment closure
     for semantic families;
   * specificity against certified seeds and against other operators' mutants;
   * only after all of these, kill rate.
5. **Curator review** of the detector **and** of the operator's logic and sample diffs.

The candidate enters the catalogue with a new id in family `X-` (experimental) only after
the sandbox, the gate and the review. From then on it is deterministic: the LLM judgement
has been distilled into a rule, and it is subject to the S2 kill-rate regime like every
other check.

### 4.4 Guards

* `min_gain` is taken from the S3 noise study. It is not chosen.
* A **no-op control** candidate is proposed every 5 rounds and must be rejected. A
  promoted no-op halts evolution.
* **Immutable core** (OVA-E06): existing checks, the critic, the policy function, the
  scorer and the gate cannot be modified by promotion. Proposals that touch them are
  rejected structurally.
* **Data hygiene:** failures are mined from `train` and production experience, the gate
  reads only `holdout-gate`, and `test` is reported once per release.
* **Rollback:** each promotion is one version step and keeps its predecessor.
  `monitor` rolls back automatically when the critic-correction or dismissal rate
  breaches its threshold.

**Exit guard (V-S4):** replaying K rounds on recorded experience shows ≥ 1 promotion with
a held-out gain, 0 promoted no-op controls, 0 core mutations, a **planted colluding pair**
(a deliberately wrong check plus an operator that injects exactly what it matches) rejected, and
every injected regression caught by the gate. When the guard `gateRegression` fires, the programme
returns to S3 for re-optimisation.

---

## Milestone summary

| stage | key artefact | measured exit | depends on |
|---|---|---|---|
| S0 | catalogue + SysML | `build_docs.py` exit 0 | — |
| S1a | MVP engine + CLI | Reference Conformance Suite green | S0 |
| S1b | full catalogue, SHACL, MCP | fixtures green, FIBO ≤ 600 s | S1a |
| S1c | justifications, DL backend | justifications minimal | S1b |
| S2 | mutants, labelled sets, cards | kill rate 1.0, κ ≥ 0.7, splits frozen | S1c |
| S3 | DSPy modules, critic, judge | held-out gain > noise, ≤ $0.25 per submission | S2 |
| S4 | gated evolution, check synthesis | no-op rejected, core immutable, gain on holdout | S3 |
| R1 | deterministic product (library, CLI, REST, MCP, container) | V-REL | S1c |
| R2 | agentic tier | V-REL + V-S3 | S3 |
| R3 | self-evolving tier | V-REL + V-S4 | S4 |

---

## Productisation track (cross-cutting)

| item | lands by | notes |
|---|---|---|
| `service/` REST API (OpenAPI), async jobs, webhooks, idempotency | R1 | CLI and MCP become thin clients |
| `TenantContext`, partitioned run store | R1 | required before the first external tenant |
| `engine/guards.py`: XXE-safe parsing, import allow-list, size/time limits | R1 | security test pack in V-REL |
| SBOM + licence scan in CI; strip owlready2's bundled Pellet; legal review | R1 | no AGPL in the distribution |
| OpenTelemetry traces and metrics; audit log; SLO dashboards | R1 | SLOs published per plan |
| Store pushdown to Fuseki; module-partitioned reasoning | R1 → R2 | target ≥ 10M triples |
| `LlmGateway`: allow-list, zero retention, redaction, budgets, payload log | R2 | LLM tier is opt-in per tenant |
| Per-tenant skill versions and experience buffer; opt-in shared pool | R3 | — |
| User guide, policy-authoring guide, generated check reference, API reference | each release | generated from the catalogue and the OpenAPI spec |

