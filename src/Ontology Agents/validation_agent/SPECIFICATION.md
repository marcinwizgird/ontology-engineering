# Ontology Validation Agent (OVA): Specification

**Status:** S0 (specification), 2026-10-04 · **Models:** [`models/`](models) (SysML v2) ·
**Checks:** [`CHECK_CATALOGUE.md`](CHECK_CATALOGUE.md) (generated from
[`spec/check_catalogue.py`](spec/check_catalogue.py)) · **Architecture:**
[`ARCHITECTURE.md`](ARCHITECTURE.md) · **Stages:** [`ROADMAP.md`](ROADMAP.md)

## 1. Purpose

OVA answers the question an ontology registry asks at intake, and the question a release
pipeline asks before it depends on a new version:

> *What is wrong with this ontology, why, what is the smallest change that fixes it,
> and, under our written policy, is it accepted, sent back for revision, or rejected?*

It is built for commercial use: ontology registries and data-governance offices,
enterprise knowledge-graph platforms, and CI pipelines of teams that publish ontologies
(FIBO-scale OWL, SKOS thesauri, SHACL-governed data). Its value comes from two things.
Its findings and verdicts are trustworthy enough to block a release automatically, and
its explanations and repairs save expert time. Nine design principles follow:

| # | principle | consequence |
|---|---|---|
| 1 | **The policy is code.** | The verdict is a pure function `verdict(findings, measured, declared, policy)` (§6). Waivers are keyed on the **measured** profile, never on what the publisher claims. |
| 2 | **Deterministic first.** | Release R1 is a complete validator with no LLM. It is the control every LLM feature is measured against, the critic that checks the LLM, and the reward the optimiser uses. |
| 3 | **Narrow, logged tools.** | Each check family is its own tool, so a run's trajectory records exactly which evidence a decision used (§8). |
| 4 | **Diagnostic feedback.** | The scorer emits named rulebook violations plus "expected X, got Y" notes, because an optimiser can only fix what the feedback names (§10). |
| 5 | **Validated judges.** | Any LLM judge is validated against human labels (κ) before its scores are used for anything. |
| 6 | **Gains must beat noise.** | An improvement counts only if it beats the measured run-to-run spread on a held-out split, with its cost reported. |
| 7 | **The model never decides.** | The model does not author findings or verdicts. It labels heuristic candidates, explains, proposes repairs and writes, and a deterministic critic checks all of it (§7). |
| 8 | **Evidence has a price.** | The planner decides which *expensive* evidence (DL reasoning, justifications, adjudication) is worth buying for a submission, against a budget. |
| 9 | **Change is gated.** | Self-evolution promotes an artefact only through a gate whose `min_gain` comes from the measured noise, and a no-op control candidate must be rejected (§11). |

## 2. Scope

**In scope.** Validation of OWL 2 ontologies, RDFS vocabularies, SKOS concept schemes,
and instance data with or without shapes. Reasoning-based, SHACL-based and custom
structural, lexical and ontological checks. Root-cause analysis with justifications.
Verified repair proposals. Version-to-version change validation. Competency-question
tests. Reports for humans, machines (JSON) and the graph (RDF).

**Out of scope.** Editing the ontology (OVA is read-only; see OVA-T04). Ontology
alignment and matching quality (the Ontology Enricher's job). Validating the *truth* of
domain claims beyond what the ontology's own axioms, the policy and the adjudication
questions can decide.

**Users (SysML stakeholders).** Ontology engineer, registry curator, domain expert,
platform operator, consuming system. See `OvaRequirements` §1.

## 3. Use cases and run modes

| mode | use case | LLM on the critical path? | output |
|---|---|---|---|
| `validate` | ValidateSubmission | optional (adjudication, explanation, report prose) | full report |
| `gate` | GateRelease | no, unless the policy enables adjudication | verdict + exit code 0/1/2 |
| `diff` | GateRelease with a baseline | no | EVO findings + semantic diff |
| `repair` | ProposeRepair | yes (proposal); the engine verifies | verified patches |
| `investigate` | InvestigateFinding | yes (bounded tool loop) | answer + evidence + any compiled checks |
| (offline) | AdjudicateHeuristics, MaintainPolicy | — | labels, policy versions |

## 4. Inputs

| input | forms | notes |
|---|---|---|
| ontology | Turtle, RDF/XML, JSON-LD, N-Triples, OWL/XML (via owlready2); `fuseki://<dataset>/<graph>`; `playground://<project>` | imports resolved through an XML catalogue or a local mirror; offline by default |
| declared profile | `controlled-vocabulary`, `taxonomy`, `thesaurus`, `formal-ontology` (formality spectrum), plus `owl-dl` / `owl-el` / `skos` / `rdfs` | from the submission request, or the ontology header |
| policy | `policy/<name>-v<n>.yaml` | severity overrides, waivers, thresholds (`params`), required metadata, owned namespaces, upper ontology, house-rule shape pack |
| shapes | SHACL Turtle files | optional |
| baseline | a previous version (any ontology form) | enables EVO and META-04 |
| competency questions | YAML: `{id, question, sparql, expect}` | enables CQ; Themis-style |
| budget | seconds, USD, max LLM calls | read by the planner |

## 5. Deterministic validation engine

The engine is the system. It runs offline with **rdflib + owlrl + pyshacl + networkx**
(OVA-Q01). The DL reasoner (owlready2 + HermiT/Pellet, needs Java) and every LLM feature
are optional extras.

### 5.1 Pipeline

```
load -> profile -> plan -> SYN -> DECL -> DL -> structural (HIER, PHIER, PROP, SKOS, META, ABOX)
     -> RSN (reasoner) -> SHC (pyshacl) -> LEX/MOD candidates -> EVO (baseline) -> CQ
     -> justify roots -> root-cause clustering -> aggregate -> [adjudicate] -> policy -> report
```

`SYN-01` short-circuits the run. A family whose prerequisites failed (for example DL
checks after a malformed restriction) is reported as `skipped`, with the reason. It is
never reported as passed.

### 5.2 Check families

There are 131 checks in 16 families; [`CHECK_CATALOGUE.md`](CHECK_CATALOGUE.md) lists each
one with its method, severity, applicability, stage, references and mutation operator.
Summary:

| family | what it covers | engines |
|---|---|---|
| SYN | parseability, IRIs, ill-typed literals, language tags, rdf:List and restriction well-formedness | parser, SPARQL |
| DECL | undeclared classes and properties, reserved-vocabulary typos (`owl:class`), namespace hijacking, imports, kind conflicts | SPARQL |
| DL | OWL 2 DL global restrictions (punning, non-simple properties, RBox regularity, datatype map), profile report | SPARQL, graph |
| RSN | consistency, unsatisfiable classes (root and derived), inferred equivalence, unintended domain/range typing, cross-branch subsumption, identity clashes, redundancy, completeness notice, justifications | reasoner |
| SHC | shapes well-formedness, data conformance, **OWL-derived closed-world shapes**, dead shapes, shape/ontology contradictions, **house-rule shape pack** | pyshacl |
| HIER | **inheritance hierarchy**, 23 checks (§5.5) | graph, SPARQL, lexical+LLM |
| PHIER | sub-property cycles, domain/range widening, wrong inverses, chains | graph, SPARQL, reasoner |
| PROP | missing and multiple domains/ranges (intersection trap), range kind, conflicting characteristics, suspicious symmetry and transitivity | SPARQL, lexical+LLM |
| LEX | labels, definitions, duplicates, language tags, naming, circular definitions, genus-differentia | SPARQL, lexical+LLM |
| SKOS | integrity conditions S9, S13, S14, S27, S46, broader cycles, orphans, notations | SPARQL, graph |
| META | header metadata and licence, deprecation discipline | SPARQL, diff |
| ABOX | untyped individuals, disjoint membership, range and functional violations | SPARQL, reasoner |
| EVO | removed or renamed entities, lost or new entailments, semantic diff | diff |
| CQ | competency-question tests, vocabulary gaps, reasoning-dependent answers | SPARQL, reasoner |
| MOD | synonyms as classes, merged concepts, miscellaneous classes, values in names, polysemy | lexical+LLM/human |
| METRIC | spectrum position vs declared level, size and expressivity, components, richness | SPARQL, graph |

### 5.3 Reasoning validation

* **Backends.** `rl` is `owlrl.DeductiveClosure(OWLRL_Semantics)` and is always available.
  `dl` is owlready2 `sync_reasoner()` (HermiT) or `sync_reasoner_pellet()`, Java-gated.
  The planner picks `dl` when the expressivity is outside OWL 2 RL *and* the budget allows.
* **Detection under RL.** Inconsistency is detected when `owl:Nothing` has a member, or
  when owlrl adds its `rdfs:comment` error triples to the closure. An unsatisfiable class
  is detected with a **probe individual**: for each named class `C`, assert a fresh
  individual `_:probe_C a C` in a copy and check for a clash. This catches what pure RL
  closure misses for TBox-only ontologies. Probing is batched (one probe per class in one
  closure). Clashes are attributed per probe, and the batch is bisected when probes
  interact.
* **Completeness honesty (RSN-08).** When the ontology is outside RL and only `rl` ran, the
  report says that a clean result does **not** establish satisfiability.
* **Justifications (RSN-09, S1c).** Expand-shrink run over the whole ontology does not
  scale: on hundreds of thousands of axioms it would exceed the budget by orders of
  magnitude. The engine therefore narrows the search first:
  1. **Axiom view.** `AxiomIndex` maps the triples to OWL 2 structural axioms. Each axiom
     gets a stable id, its signature and its source triples, so locality, justifications,
     repairs and reports all address axioms rather than triples.
  2. **Locality module.** `ModuleExtractor` computes the syntactic **STAR module**
     (⊥- and ⊤-locality iterated to a fixpoint) for the entailment's signature: `{C}` for
     an unsatisfiable `C`, `{A, B}` for an inferred `A ≡ B`, and the clash individuals
     and their types for an inconsistency. Every justification of an entailment over a
     signature lies inside that signature's module, so the search loses nothing. The
     search space typically shrinks from hundreds of thousands of axioms to a few dozen.
  3. **Black-box expand-shrink inside the module.** Grow a subset of the module until the
     entailment holds, then remove axioms one at a time while it still holds. The result
     is minimal by construction and reasoner-independent. Further justifications come
     from a hitting-set tree over the module, up to 3 per *root* entailment, memoised by
     `(module hash, entailment)`.

  Modules are differentially tested against ROBOT `extract --method STAR`. V-S1c also
  checks on sampled entailments that the justifications found inside the module equal
  those found over the full ontology. Modules are reused by `RepairVerifier` (re-check
  only the patch's module) and by store pushdown (module-partitioned reasoning). Budget:
  p95 ≤ 30 s per root on FIBO (OVA-Q05).
* **Root and derived unsatisfiability.** A class is *derived* unsatisfiable when one of its
  justifications contains the unsatisfiability of another named class. The
  `RootCauseAnalyser` groups findings that share justification axioms into one
  `RootCause`, so a reviewer usually sees 2 causes instead of 40 classes.
* **Unintended entailments.** RSN-04 (typing that comes only from a domain or range) and
  RSN-05 (cross-branch inferred subsumption) produce *candidates*, because some inferred
  types are intended. These are adjudicated.

### 5.4 SHACL validation

Three shapes graphs, all run through `pyshacl.validate(..., advanced=True)`:

1. **Supplied shapes** (SHC-02), after SHACL-for-SHACL validation of the shapes
   themselves (SHC-01).
2. **TBox-derived shapes** (SHC-03), produced by `TboxShapeDeriver`. They give the
   closed-world reading of the ontology's own axioms, mapped as follows:

   | OWL axiom | derived shape |
   |---|---|
   | `rdfs:domain D` of `p` | `sh:targetSubjectsOf p ; sh:class D` |
   | `rdfs:range R` (class) | `sh:targetObjectsOf p ; sh:class R` |
   | `rdfs:range xsd:T` | `sh:path p ; sh:datatype xsd:T` |
   | `owl:FunctionalProperty` | `sh:maxCount 1` |
   | `C ⊑ ∃p.D` | on `C`: `sh:path p ; sh:qualifiedValueShape [sh:class D] ; sh:qualifiedMinCount 1` |
   | `C ⊑ ≤n p` / `≥n p` / `=n p` | `sh:maxCount` / `sh:minCount` |
   | `C ⊑ ∀p.D` | `sh:path p ; sh:class D` |

   Each finding reports both readings: what OWL *infers* (open world) and what SHACL
   *rejects* (closed world). This makes the
   open-world/closed-world gap visible to the publisher.
3. **House-rule pack** (SHC-08). These are TBox-level shapes in `policy/house_rules.ttl`
   that state organisation policy as data, for example "every `owl:Class` has an `@en`
   label and a definition". This is the extension point that S4 can add to without
   touching code.

SHC-04/05/06/07 compare shapes with the ontology (dead targets, stale paths, shapes no
model of the ontology can satisfy, coverage gaps). SHC-09 turns a crashing SHACL-SPARQL
constraint into a finding, so that a crash is never read as a pass.

### 5.5 Inheritance hierarchy validation (HIER, PHIER)

The hierarchy is extracted into a networkx `DiGraph` (asserted `rdfs:subClassOf` between
named classes; restrictions are kept as edge annotations) and, after reasoning, into a
second graph for the inferred hierarchy. The checks fall into five groups:

| group | checks | decidable? |
|---|---|---|
| **Integrity** (the hierarchy is a valid partial order of classes) | HIER-01 cycles (Tarjan SCC), HIER-02 individual in subsumption, HIER-03 subclass of a non-class, HIER-19 SKOS/OWL mixing, HIER-23 subclass of a deprecated class, PHIER-01 sub-property cycles, PHIER-06 object/datatype mixing | yes |
| **Satisfiability structure** (explains RSN-02 in the author's terms) | HIER-05 disjoint with an ancestor, HIER-06 subclass of two disjoint classes, HIER-07 inherited restriction conflict (cardinality, ∀/∃ with disjoint fillers), PHIER-02 sub-property widens domain/range, PHIER-03 wrong inverse | yes |
| **Redundancy and normalisation** | HIER-04 not in the transitive reduction, HIER-20 equivalence plus subsumption, HIER-09 asserted polyhierarchy of primitives (Rector normalisation), RSN-07 entailed axioms | yes (HIER-09 is adjudicated for intentional multi-axis classification) |
| **Shape** (thresholds in the policy) | HIER-08 missing sibling disjointness (waiver W1), HIER-10 orphans, HIER-11 single child, HIER-12 depth, HIER-13 fan-out, HIER-14 roots, HIER-15 upper-ontology alignment, METRIC-03 components | yes |
| **Ontological soundness** (judgement) | HIER-16 is-a overload (part-of/role/constitution as subclass), HIER-17 instance modelled as class, HIER-18 OntoClean rigidity, HIER-21 indistinguishable siblings (no differentia), HIER-22 child label does not specialise parent, LEX-10 genus-differentia mismatch, MOD-01 synonyms | candidates are deterministic; labels come from the LLM or a human |

For the soundness group, the lexical candidate generators work on labels and
definitions. They extract the head noun, apply partonomy, role and proper-noun cue
lexicons, and compare the parent's genus with the child's. The adjudicator receives one
**entity card** per candidate: labels, definition, parents, siblings, restrictions, and
the cue that fired.

### 5.6 Determinism contract

Given the same content hash, catalogue version, policy version and engine version, the
engine returns the same finding set. Every algorithm uses a sorted iteration order, has
no wall-clock dependence (timeouts are reported as RSN-08 and never silently truncate
results), and uses seeded probe IRIs. V-S1b checks this by running each fixture twice.

## 6. Findings, severities and the verdict

### 6.1 Finding schema (JSON)

```json
{
  "finding_id": "f-0007",
  "check_id": "HIER-05",
  "severity": "blocker",
  "status": "confirmed",
  "focus": "https://ex.org/rail#Locomotive",
  "related": ["https://ex.org/rail#RailVehicle"],
  "message": "Locomotive is disjoint with its ancestor RailVehicle",
  "evidence": {"triples": ["..."], "rows": []},
  "justification": ["ax-12", "ax-31"],
  "root_cause": "rc-2",
  "adjudication": null,
  "fix_hint": "remove the disjointness or move Locomotive out of the RailVehicle branch",
  "engine": {"method": "graph", "version": "0.1.0"}
}
```

`status` has the lifecycle `candidate -> adjudicatedTrue | adjudicatedFalse | unsure`,
`confirmed` (decidable checks), and `waived` (policy). `adjudication`, when present, is
`{label, confidence, rationale, skill, skill_version, model}`.

### 6.2 Policy (pure function)

```
reportable = [f for f in findings
              if f.status in {confirmed, adjudicatedTrue}
              and not waived(f, measured_level, policy)]

verdict =
  "reject"  if any(f.severity == blocker and f.status == confirmed for f in reportable)
  "revise"  if any(f.severity in {blocker, major, minor} for f in reportable)
            or rank(measured_level) < rank(declared_level)          # METRIC-01
  "accept"  otherwise
```

* **Precedence.** reject > revise > accept, encoded as ordered checks so the precedence
  is explicit.
* **Adjudication cap (OVA-T03).** An `adjudicatedTrue` finding counts at most as `major`,
  so model judgement alone can never reject a submission.
* **Waivers are keyed on the measured level.** The default waiver W1: HIER-08 is
  waived for measured `controlled-vocabulary` and `thesaurus`. A policy may add waivers
  of the form `{check, when: {measured_level|profile|namespace}, reason}`.
* **Severity overrides** and `params` (thresholds) are per policy version. The policy
  version is part of the report's provenance.
* **Policy packs.** OVA ships `registry-default-v1`, a strict profile for governed
  enterprise ontologies, and `ci-lenient-v1`, which caps everything except blockers at
  `minor` while a team adopts the tool. Tenants derive their own policies from these.
  Every policy change is versioned and audited (OVA-P07).

### 6.3 Report

* **JSON:** `{run, ontology{iri, version_iri, hash}, profile, plan, findings[],
  root_causes[], repairs[], verdict, metrics, versions{engine, catalogue, policy,
  skills{}}, cost{calls, usd}, tool_log[]}`.
* **RDF:** an `sh:ValidationReport` whose `sh:result` nodes are extended with `ova:checkId`,
  `ova:rootCause` and `ova:justification`. The run is a `prov:Activity` that
  `prov:used` the ontology hash and the policy version. It can be written to a Fuseki
  named graph `urn:ova:run:<id>` on explicit approval.
* **Markdown:** the verdict and why, then root causes (each with its justification and
  verified repairs), then findings by severity, then the waived findings and why they
  were waived. The prose slots come from the `ReportWriter`. A deterministic template
  exists for every slot, so `gate` mode needs no LLM.

## 7. The agentic layer and the trust boundary

| module (DSPy) | input → output | may change a decidable field? | checked by |
|---|---|---|---|
| CheckPlanner | profile, purpose, budget → families, backend, justification budget | can **add** families or upgrade the backend; cannot drop a policy-required family | registry + policy |
| FindingAdjudicator | candidate + entity card → {true, false, unsure}, confidence, rationale | can only change the `status` of `candidate` findings | adjudication cap; experts |
| RootCauseExplainer | root cause + justification (Manchester syntax) → explanation | no | critic: every entity it names must be in the justification |
| RepairProposer | root cause + justification + policy + prior attempts → ≤ k patches, inside a verifier-driven retry loop (≤ 3 attempts) | no | **RepairVerifier**: the targeted findings disappear, no new blocker or major appears, entailment loss is reported; its diagnostics feed the next attempt |
| ReportWriter | critic-checked result → prose | no | critic grounding; validated judge |
| Investigator | question → answer (bounded tool loop) | no; any hypothesis must be compiled to SPARQL and run by the engine before it becomes a finding | engine |
| ReportJudge | report → score + critique | — | κ against human labels ≥ 0.6 before use |

**Critic.** This is a deterministic stage between cognition and the report. For every
decidable field (finding set, severities, measured profile, verdict) it replaces the
model's value with the engine's and records one correction string per override. It also
strips from the prose any IRI or label that does not appear in the evidence. The
correction count is a tracked metric: in a healthy system it trends to zero, and when it
rises that signals drift.

**What the LLM is for.** It turns judgement
candidates into labels a curator can trust, turns justifications into explanations, finds
small repairs (which the engine then verifies), and writes for a human. Each of these is
evaluated separately (§10).

## 8. Tool belt

Every tool is narrow, read-only and logged. It takes JSON in and returns JSON out. Errors
come back as `"ERROR: ..."` text. Each description says **when** to call the tool. The
same objects are exposed as LangChain `StructuredTool`s and over MCP.

**Isolation and least privilege.** Every tool is bound to one `ValidationWorkspace`, keyed
by `(tenant, run)`. Each MCP session gets its own workspace, and the MCP servers are
stateless and scale horizontally, so concurrent sessions cannot collide (constraint
`SessionIsolation`). OVA's own DSPy modules call the tool belt in-process, not over MCP.
Isolation comes from workspace scoping, not from how many server instances are deployed.
Tools are grouped into **role-scoped profiles**, and each profile is deployable as its
own MCP endpoint:

| profile | tools | given to |
|---|---|---|
| `readonlyInspect` | load, profile, describe_entity, hierarchy_neighbourhood, sparql_*, check_catalogue | CheckPlanner; external read-only agents |
| `validate` | + run_family, run_check, reason, shacl_validate, apply_policy | CI gates, Ontology Modeler |
| `diagnose` | + justify, root_causes (expensive, budgeted) | Investigator, RootCauseExplainer |
| `repair` | + verify_patch | RepairProposer |

| tool | args | returns | cost class |
|---|---|---|---|
| `load_ontology` | `source, declared?, baseline?, shapes?` | `{loaded, triples, hash, imports{resolved, missing}}` | cheap |
| `profile` | — | `{spectrum_level, owl_profiles, expressivity, counts}`. *Call first.* | cheap |
| `check_catalogue` | `family?` | `[{id, title, severity, applies}]` | cheap |
| `run_family` | `family` | findings | cheap–moderate |
| `run_check` | `check_id` | findings | cheap |
| `reason` | `backend=rl\|dl` | `{consistent, unsatisfiable[], inferred_equivalences[], complete}` | moderate / expensive |
| `shacl_validate` | `which=supplied\|derived\|house` | findings | moderate |
| `justify` | `finding_id` | `[[axiom...]]`. *Per root cause, not per finding.* | expensive |
| `root_causes` | — | `[{root_id, axioms, findings}]` | moderate |
| `describe_entity` | `iri` | entity card | cheap |
| `hierarchy_neighbourhood` | `iri, up=2, down=1` | parents, siblings, children, disjointness | cheap |
| `sparql_select` / `sparql_ask` | `query` | rows ≤ 100 / bool (guarded: no update, no SERVICE, LIMIT injected) | cheap |
| `verify_patch` | `add[], remove[]` | `{fixed[], new[], entailment_loss[]}`. *The only route by which a repair is accepted.* | moderate |
| `apply_policy` | — | `{reportable[], verdict, waived[]}` | cheap |

`TOOL_TO_EVIDENCE` maps tools to evidence kinds so the MDP and the scorer
can tell what a trajectory bought.

## 9. Non-functional requirements

| id | requirement | target |
|---|---|---|
| OVA-Q01 | Deterministic core offline, no Java, no API key | hard |
| OVA-Q02 | Vendored FIBO, deterministic families excluding `dl` | ≤ 600 s on a developer machine |
| OVA-Q03 | Mean LLM cost per submission, `validate` mode, test split | ≤ $0.25 |
| OVA-Q04 | Every blocker has a justification or structural explanation | 100 % |
| OVA-Q05 | Justification time per root cause on FIBO (module + expand-shrink, RL) | p95 ≤ 30 s |
| OVA-P09 | Service levels: `gate` p95 for ≤ 100k triples; availability | ≤ 60 s; 99.5 % |
| OVA-P08 | Largest supported ontology (with store pushdown) | ≥ 10M triples |

Productisation requirements (tenancy, LLM data governance, security, licensing, API,
observability, audit) are in §12.

## 10. Evaluation contract

**Scorer.** `(gold, prediction) -> ScoreReport(score, notes, violated)`. The same scorer
serves baselines, GEPA, the agent and the MDP reward. The `validate`-mode score is:

```
score = 0.15 * profile_ok
      + 0.35 * finding_F1        (over (check_id, focus) pairs, gold = engine + labels)
      + 0.15 * adjudication_F1   (over candidate labels)
      + 0.15 * decision_ok
      + 0.10 * root_cause_ok     (clusters match, by adjusted Rand index)
      + 0.10 * repair_score      (engine-verified; see below)
```

**Rulebook** (named violations, in order): `use-label-vocabulary`,
`report-all-findings`, `no-unsupported-findings`, `apply-waivers`, `correct-severity`,
`correct-adjudication`, `cite-justification`, `identify-root-cause`, `repair-verified`,
`repair-minimal`, `decide-by-policy`, `ground-in-evidence`. `apply-waivers` and `no-unsupported-findings` are kept apart because each calls for a
different fix.

**Repair score.** This is computed by the engine and needs no gold label:
`fixed_targets / targets − 0.5 · new_blocker_or_major − 0.1 · axioms_changed_over_min −
0.2 · unintended_entailment_loss`, clipped to [0, 1]. This makes repair a **verifiable
reward**, which is the best kind of objective for an optimiser.

**Reporting rule (OVA-E04).** Every number comes with its split, *n*, cost and
run-to-run spread. A gain smaller than the spread is reported as no gain.

## 11. Self-evolution contract

What may evolve, and the gate each kind of change must pass:

| artefact | proposed by | gate |
|---|---|---|
| module instructions | GEPA over mined failures | holdout gain ≥ `min_gain`, regression suite |
| few-shot demonstrations | bootstrapped from confirmed episodes | same |
| thresholds (`params`) | calibration against expert dismissals | same + curator |
| house-rule shapes | synthesised SHACL from confirmed defects | sandbox precision on certified seeds + curator approval |
| **new checks** | synthesised SPARQL detector **plus** its mutation operator | sandbox (precision on seeds; recall on **held-out** confirmed cases) + independent operator evidence (below) + kill rate 1.0 + curator approval of check **and** operator |
| mutation operators | synthesised **independently** of the check | valid RDF; non-vacuous, localised diff; blind expert confirmation; killed by its target check only |

**Non-circular validation (OVA-E07).** A synthesised check and the operator synthesised
with it could certify each other. A flawed rule plus an operator that injects exactly what
the rule looks for scores kill rate 1.0 and proves nothing. Requiring the operator to
change the entailment closure is necessary but not sufficient: any added axiom changes
the closure, and lexical defects change none. Promotion therefore needs evidence that
does not come from the pair:

1. **Held-out recall.** The expert-confirmed examples behind the proposal are split
   before synthesis. The check must fire on the held-out part, which neither the check
   nor the operator has seen.
2. **Independent derivation.** The operator is generated from the natural-language defect
   description and the confirmed examples, in a separate call that does not see the check
   (and preferably by a different model).
3. **Blind mutant confirmation.** A sample of mutants is shown to experts as entity cards,
   without the check or its name. They must confirm that the defect is present.
4. **Non-vacuous diffs.** `VersionDiffer` shows that every mutant changes the asserted
   axioms locally around the focus entity. For semantic families (RSN, HIER, PHIER, PROP,
   ABOX), the entailment closure must change too.
5. **Specificity.** The check fires on no certified seed and on no other operator's
   mutants, apart from declared overlaps.
6. **Curator review of both.** The curator reviews the operator's logic and sample diffs
   as well as the rule.

Only after 1–6 hold does kill rate count, and kill rate 1.0 alone is never sufficient.
The constraint `IndependentEvidence` must hold for every promotion.

**Immutable core (OVA-E06).** Self-evolution is additive. No promoted artefact may edit or
remove an existing deterministic check, the critic, the policy function, the scorer or
the gate. A **no-op control** candidate is proposed every *N* rounds and must be
rejected. If it is ever promoted, the gate is broken and evolution halts.

## 12. Productisation

Every commercial release (R1 deterministic, R2 agentic, R3 self-evolving; see
[ROADMAP.md](ROADMAP.md)) must pass `ReleaseReadinessCase` (V-REL), which verifies
OVA-P01..P09.

| id | requirement | design |
|---|---|---|
| OVA-P01 | **Tenant isolation** | A `TenantContext` is carried by every request. The run store, experience buffer, policies and skill versions are partitioned per tenant. Cross-tenant learning happens only through an opt-in shared pool. |
| OVA-P02 | **LLM data governance** | LLM features are off by default and opt-in per tenant and per policy. The `LlmGateway` is the only egress for ontology content. It enforces a provider allow-list, zero-retention endpoints, redaction (opaque IRIs; labels only for the entities in the current candidate), per-run token and USD budgets, and a payload log. When a call is denied, the step falls back to its deterministic template, so the run never fails because of it. |
| OVA-P03 | **Secure ingestion** | XXE-safe parsers. Import fetching is off by default and allow-listed when on (prevents SSRF). Size, triple and time limits. The SPARQL guard. LLM-produced patches and queries are parsed and validated as untrusted input. |
| OVA-P04 | **Licence compliance** | SBOM and licence scan in CI. Permissive core: rdflib (BSD-3), owlrl (W3C), pyshacl (Apache-2.0), networkx (BSD-3). owlready2 and HermiT are LGPL-3.0: dynamically linked and unmodified. Pellet and Openllet are AGPL-3.0: **excluded** from the distribution (owlready2's bundled Pellet jar is stripped). ELK (Apache-2.0) is the candidate EL reasoner. *Legal review required before R1.* |
| OVA-P05 | **Service interface** | A versioned REST API (OpenAPI) with asynchronous jobs and webhooks. Submission is idempotent by `(content hash, policy version)`. The report schema is semver-versioned. CLI and MCP are thin clients over the same service layer. |
| OVA-P06 | **Observability** | OpenTelemetry spans per family, tool call and LLM call. Metrics: latency, findings by check, critic corrections, cost, errors. Per-tenant dashboards and SLO alerts. |
| OVA-P07 | **Audit trail** | An append-only record per run and per promotion: submitter; engine, catalogue, policy, skill and model versions; approvals. An audit record is sufficient to reproduce its report. |
| OVA-P08 | **Scalability** | Stateless workers behind a job queue. Above the in-memory limit (2M triples by default), SPARQL families are pushed down to Fuseki and reasoning is partitioned by locality-based modules. The target is ≥ 10M triples. |
| OVA-P09 | **Service levels** | Published SLOs per mode and plan. `gate` p95 ≤ 60 s for ≤ 100k triples. Availability 99.5 %. A maximum LLM cost per run per plan. |

**Packaging.** OVA ships as a Python package (the engine as a library), a container
image (service plus workers), and an MCP server. The deterministic tier needs no API key
and runs fully on-premises, which is often a precondition for regulated customers
(finance, rail, health).

**Quality engineering.** Every check has fixtures: positive, negative and near-miss.
Properties are tested: determinism, and idempotence of the policy function. The Reference
Conformance Suite (§13) runs on every merge. Every escaped defect becomes a golden case
before its fix is merged.

## 13. Traceability

| requirement | satisfied by (`OvaArchitecture`) | verified by (`OvaDevelopment`) |
|---|---|---|
| OVA-F01 intake | Loader, FusekiConnector, PlaygroundConnector | V-S1b fixtures |
| OVA-F02 catalogue-driven | CheckRegistry | V-S1b |
| OVA-F03 reasoning | ReasoningEngine | V-S1a (W3C OWL 2 cases), V-S2 kill rate |
| OVA-F04 SHACL | ShaclEngine | V-S1a (W3C SHACL cases), V-S2 |
| OVA-F05 hierarchy | StructuralChecker, ReasoningEngine, FindingAdjudicator | V-S2, V-S3 |
| OVA-F06 justifications | AxiomIndex, ModuleExtractor, JustificationEngine, RootCauseAnalyser | V-S1c |
| OVA-Q05 justification throughput | ModuleExtractor, JustificationEngine | V-S1c |
| OVA-E07 non-circular validation | — | V-S4 |
| OVA-F07 verdict | PolicyEngine | V-S1a (golden corpus) |
| OVA-F09 verified repairs | RepairProposer + RepairVerifier | V-S3 |
| OVA-T01..T05 trust boundary | Critic, PolicyEngine, ToolBelt, ReportBuilder | V-S3 (critic corrections, constraint counters) |
| OVA-E03 reference conformance | — | V-S1a: W3C SHACL Core, W3C OWL 2, golden corpus, oracle differential |
| OVA-E01..E06 | — | V-S2, V-S3, V-S4 |
| OVA-P01..P09 productisation | PlatformServices (TenantContext, JobQueue, LlmGateway, SecurityGuards, Observability, AuditLog, StorePushdown), RestApi | V-REL |

The **Reference Conformance Suite** has four parts. (a) The applicable W3C SHACL Core
test cases. (b) The W3C OWL 2 test cases: RL always, DL when the DL backend is enabled.
(c) The golden corpus: real ontologies whose expected findings a curator has signed off.
(d) Differential testing against each family's reference oracles (listed in
[`CHECK_CATALOGUE.md`](CHECK_CATALOGUE.md): ROBOT report, HermiT, ELK, qSKOS, OOPS!,
Jena SHACL). Every disagreement is triaged as an OVA bug, an oracle bug, or a deliberate
difference, and the outcome is recorded.

`python spec/build_docs.py` fails if a requirement is neither satisfied nor verified, or
if a trace references an unknown requirement or verification case.

## 14. Open decisions

1. **Default policy packs.** The catalogue's default severities and `registry-default-v1`
   are proposals. They need sign-off from the first design partners' curators.
2. **The upper ontology for HIER-15.** BFO, gist or a customer-supplied upper model,
   configured per tenant. The check is off until one is configured.
3. **The UNA stance for ABOX/RSN-06.** OWL has no unique-name assumption. Each policy must
   say whether distinct IRIs in one namespace are treated as `owl:differentFrom`.
4. **Java in the distribution.** This decides whether the `dl` backend (HermiT) ships in
   the container image or is a separately licensed add-on.
5. **LLM providers and hosting.** Which zero-retention endpoints are on the allow-list
   (first-party API, Bedrock, Vertex), and whether a private deployment is offered for
   the agentic tier.
