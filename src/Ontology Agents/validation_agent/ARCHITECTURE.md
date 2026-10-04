# Ontology Validation Agent: Architecture

The normative model is [`models/ova_architecture.sysml`](models/ova_architecture.sysml)
(SysML v2, package `OvaArchitecture`). This document is the reading guide for it. When
the two disagree, the model is correct and this file is out of date.

| model file | package | contents |
|---|---|---|
| [`ova_requirements.sysml`](models/ova_requirements.sysml) | `OvaRequirements` | 5 stakeholders, 6 use cases, 35 requirements (F functional, T trust boundary, Q quality, E evaluation/evolution, P productisation) |
| [`ova_architecture.sysml`](models/ova_architecture.sysml) | `OvaArchitecture` | system boundary and ports, platform services (tenancy, jobs, LLM gateway, security, telemetry, audit, store pushdown), 14 engine parts, 14 tools, 7 DSPy modules, critic, information model, `ValidateOntology` action, `ValidationRun` state machine, 5 trust constraints, `satisfy` and `allocate` |
| [`ova_development.sysml`](models/ova_development.sysml) | `OvaDevelopment` | stage machine S0–S4 with measured guards, Reference Conformance Suite, fixtures, evaluation corpus, scorer and rulebook, `OptimiseModule`, `EvolveRound`, promotion gate, release train, 7 verification cases (incl. V-REL release readiness) |

The models use the SysML v2 textual subset that the repo's reader
(`architecture/graphrag_agent/sysml_model.py`) understands, so the diagram tooling there
applies. `spec/build_docs.py` parses all three files and checks the traceability.

## 1. Structural view

```
                         ┌────────────────────── OntologyValidationAgent ───────────────────────┐
 submission ──► port ──► │ InterfaceLayer (REST API · CLI · MCP · Fuseki · Playground)          │
                         │ PlatformServices (tenancy · jobs · LLM gateway · guards · audit)     │
 policy     ──► port ──► │        │                                                             │
                         │        ▼                                                             │
                         │   Orchestrator ── fixed DAG (validate/gate/diff/repair)              │
                         │        │          bounded loop (investigate)                         │
                         │        ▼                                                             │
                         │ ValidationWorkspace (asserted · closure · inferred · shapes ·        │
                         │                      baseline · ToolCallLog · FindingStore)          │
                         │        ▲                                                             │
                         │        │ read-only, logged                                           │
                         │   ToolBelt (14 narrow tools) ◄──────────────┐                        │
                         │        │                                     │ tool calls only       │
                         │        ▼                                     │                       │
                         │ ┌─ ValidationEngine (deterministic) ─┐   ┌─ AgenticLayer (DSPy) ─┐   │
                         │ │ Loader · Profiler · CheckRegistry  │   │ CheckPlanner          │   │
                         │ │ Structural · Reasoning · SHACL     │   │ FindingAdjudicator    │   │
                         │ │ Lexical · Differ · Justifier       │   │ RootCauseExplainer    │   │
                         │ │ RootCause · Aggregator             │   │ RepairProposer        │   │
                         │ │ PolicyEngine · RepairVerifier      │   │ ReportWriter          │   │
                         │ │ ReportBuilder                      │   │ Investigator · Judge  │   │
                         │ └────────────────┬───────────────────┘   └──────────┬────────────┘   │
                         │                  │ findings, verdict                │ draft         │
                         │                  ▼                                  ▼               │
                         │                 Critic (deterministic: overrides decidable fields)   │
                         │                  │                                                   │
 report     ◄── port ◄── │            ReportBuilder ──► RunStore (runs · experience · skills)   │
 feedback   ──► port ──► │                                         ▲                            │
                         └─────────────────────────────────────────┼────────────────────────────┘
                                                                   │ offline
                                                          EvolveRound + PromotionGate
```

**Trust boundary.** The engine is upstream of the boundary and the model is downstream.
The `LanguageModel` part has `mayAssertFindings = false`, and in the model the only port
from cognition to the report is `Critic.fromCognition → Critic.toReport`. The five
constraints on the `ova` instance (`CriticDominance`, `FindingsFromCatalogueOnly`,
`AdjudicatedCannotReject`, `RepairsVerified`, `Determinism`) are counters measured on
every evaluation run, and each must be 0.

## 2. Behavioural view

`action def ValidateOntology` is the default pipeline:

```
load → profile → plan → runChecks → analyse → adjudicate → decide → interpret → criticise → publish
                  ▲                                         │
          CheckPlanner (additive)                PolicyEngine (pure)
```

`decide` runs **before** `interpret`. The verdict is fixed before any prose exists, so
the writer explains a decision and does not make one. `adjudicate` is the only LLM step
whose output feeds `decide`, and the adjudication cap bounds its effect.

`state def ValidationRun` gives the run lifecycle and the guards (`parseError`,
`planIncludesReasoning`, `adjudicationEnabled`). `action def ProposeVerifiedRepair` is
the propose → verify loop. Its `verify` step is the engine's `RepairVerifier`, never the
model.

## 3. Key design decisions

### 3.1 Pipeline with a critic by default; an agent loop only for investigation

In `validate` mode the order of work does not depend
on intermediate results: every applicable family runs. A fixed pipeline is therefore
cheaper, reproducible and auditable. The **Investigator** (a bounded tool-calling loop,
at most 20 steps) is used only for open questions ("why is X unsatisfiable, and what did
the author probably mean?"), where the next tool call genuinely depends on the last
result. S3 measures all three variants (agent, program, program+critic) on the same
scorer before this decision is final.

### 3.2 "Candidates are deterministic, labels may be learned"

Judgement checks (is-a overload, synonyms, OntoClean, genus-differentia) are split in
two. A deterministic **candidate generator**, versioned in the catalogue, produces
candidates. An **adjudicator** labels them. This keeps recall measurable by mutation (S2)
and keeps precision optimisable by DSPy (S3). It also means the model cannot invent a
finding (OVA-T02), and it gives S4 a path to *graduate* recurring confirmed judgements
into new deterministic checks.

### 3.3 The planner as an evidence-pricing MDP

Most evidence is cheap: SPARQL and graph checks take milliseconds. A few kinds are
expensive: DL reasoning on FIBO-scale ontologies, justifications, and LLM adjudication
of hundreds of candidates. Formally this is an MDP: states are the evidence held, actions are
`buy(evidence)` or `submit`, and the reward is `quality − λ·cost`. The deterministic
default plan is always safe. The planner's role is to decide when the DL backend or more
justifications are worth paying for. Regret against V\* on the dev split is the planner's
metric.

### 3.4 Repair as a verifiable reward

`RepairProposer` outputs patches as axioms to add and remove. `verify_patch` applies a
patch to a copy and re-runs the affected families (within the patch's locality module)
plus a semantic diff. The resulting score (§10 of the specification) needs no gold label,
which makes repair the module best suited to DSPy optimisation and to self-evolution.

**Verifier-driven retry.** When none of the k patches passes, the attempt is not
abandoned. The verifier's diagnostics (targets still present, new findings, entailment
loss) go back to the proposer as a `prior_attempts` input, and it retries up to
`maxAttempts` (default 3). DSPy 3 no longer has `dspy.Assert` or `dspy.Suggest`, so the
loop is a small custom module around the predictor. `dspy.Refine` with the repair score
as `reward_fn` is the simpler alternative, but it feeds back generated advice rather than
the engine's own diagnostics. The order of work matters:

1. Measure the bare predictor (pass@1).
2. Measure it with the loop (pass@3). This is the stronger baseline.
3. Run GEPA on the inner predictor's instruction, with the loop in place and a metric
   that charges for attempts, so that GEPA improves first-attempt quality instead of
   leaning on retries.

### 3.5 Locality modules as the unit of expensive work

Expensive operations never run over the whole ontology. `ModuleExtractor` produces the
STAR module for a signature, and three consumers rely on it:

* `JustificationEngine` runs expand-shrink inside the module of an entailment's signature;
* `RepairVerifier` re-checks only the module of the patch's signature;
* `StorePushdown` partitions DL reasoning on large ontologies by module.

The module is lossless for justifications, and it is the reason OVA-Q05 (p95 ≤ 30 s per
root on FIBO) is achievable.

### 3.6 MCP: session-scoped workspaces and role-scoped profiles

The MCP servers are stateless. Each session binds its own `ValidationWorkspace`, keyed
by `(tenant, run)`, and tools are grouped into four profiles (`readonlyInspect`,
`validate`, `diagnose`, `repair`). Each profile is deployed as its own endpoint and
scaled independently. That gives least privilege and fault isolation, and the expensive
`diagnose` tools can be capacity-limited without starving `validate`. The design does
**not** use one MCP server per DSPy module, because OVA's own modules call the tool belt
in-process. Running them through per-agent servers would add network hops without adding
isolation, since state collisions are already ruled out by workspace scoping
(`SessionIsolation`), not by the number of servers.

### 3.7 Reuse and integration

| reused | from | for |
|---|---|---|
| Fuseki client, Playground projection | `src/Ontology Modeler/ontology_modeler/{fuseki,playground}` | `fuseki://` and `playground://` sources; RDF report write-back |
| SysML subset reader | `architecture/graphrag_agent/sysml_model.py` | model validation and diagrams |

Everything else (spectrum classifier, pitfall detectors, CQ runner, skill versioning,
experience buffer, GEPA wrappers, cost meters) is implemented inside OVA. That gives the
product one owner, one test suite and one licence position (OVA-P04). It does not depend
on prototype code.

**Consumers.** The Ontology Modeler calls `gate` before an upload is committed. The
Playground safe-merge calls `validate` on the merged projection before write-back. The
GraphRAG agent's projection refuses a `reject` version. The Ontology Builder's
validation workflow (`OB.CHG.04`, staging graphs) uses OVA as its validator.

## 4. Planned module layout (allocation)

```
src/Ontology Agents/validation_agent/
  spec/            check_catalogue.py · build_docs.py                         (S0, this commit)
  models/          *.sysml                                                    (S0, this commit)
  engine/          loader · profile · registry · reasoning · shacl · justify ·
                   rootcause · policy · repair · diff · report
  engine/checks/   syn · decl · dl · hier · phier · prop · lex · skos · meta ·
                   abox · evo · cq · mod · metric   (one module per family)
  engine/          ... · guards (XXE/SSRF/limits/SPARQL guard) · pushdown (Fuseki execution)
  policy/          registry-default-v1.yaml · ci-lenient-v1.yaml · house_rules.ttl
  workspace.py     ValidationWorkspace (one run, one tenant context)
  service/         api (OpenAPI) · jobs · tenancy · telemetry (OTel) · audit
  tools/belt.py    LangChain StructuredTools + TOOL_TO_EVIDENCE
  agent/           signatures · programs · critic · judge · investigator · planner_mdp · orchestrator · gateway
  evaluation/      mutations · seeds · datasets · scorer · rulebook · cards
  evolution/       experience · gate · check_synthesis · monitor
  tests/           fixtures/<check_id>/{positive,negative,near_miss}.ttl · test_*.py
  docs/            user guide · check reference (generated) · policy authoring · API reference
  deploy/          Dockerfile · helm chart · SBOM
  cli.py · mcp_server.py · __main__.py
```

Each pipeline step is a `state -> state` function and a node in a networkx DAG, and each
step is also exposed as an agentic tool. The engine package has no dependency on the
service, agent or evolution packages, so it can ship alone as the R1 library.

## 5. Model routing (defaults, tuned in S3)

| module | default | why |
|---|---|---|
| CheckPlanner, FindingAdjudicator | `claude-haiku-4-5` | high volume, short context, a classification task |
| RootCauseExplainer, RepairProposer, ReportWriter, Investigator | `claude-sonnet-5` | reasoning over justifications; quality matters more than volume |
| GEPA reflection LM | `claude-opus-5-5` | few calls, large leverage |
| ReportJudge | a different model family member than the writer | reduces self-preference bias; validated by κ |

## 6. Failure modes the architecture is built against

| failure | defence |
|---|---|
| The model "finds" a defect that is not there | `FindingsFromCatalogueOnly`; the critic strips ungrounded entities |
| The model talks the verdict up or down | `decide` before `interpret`; `CriticDominance` |
| A heuristic false positive rejects a submission | Adjudication cap (OVA-T03) |
| A clean RL result is read as "satisfiable" | RSN-08 completeness notice |
| One cause produces 40 findings and drowns the reviewer | Root-cause clustering over justifications |
| A plausible but broken repair | `RepairsVerified`; `verify_patch` is the only acceptance route; verifier diagnostics drive the retry |
| Justification search blows the budget on a large ontology | STAR module first; expand-shrink only inside it (OVA-Q05) |
| Two concurrent sessions overwrite each other's state | Session-scoped workspaces (`SessionIsolation`); stateless MCP servers |
| A synthesised check and its own operator validate each other | `IndependentEvidence`: held-out recall, independent operator, blind confirmation, non-vacuous diffs, curator review of both |
| The optimiser overfits the eval set | Splits grouped by seed; the gate holdout is never mined; test reported once |
| Self-evolution drifts while reporting progress | `min_gain` from the noise study; no-op control; immutable core; auto-rollback |
| The LLM recognises FIBO and answers from memory | IRI-scrambled mutant variants in S2 measure this |
| Customer ontology content leaks to an LLM provider | LLM tier off by default; `LlmGateway` as the only egress, with redaction, allow-list, zero retention and payload log |
| A hostile upload (XXE, SSRF via `owl:imports`, giant file) | `SecurityGuards`: safe parsers, imports off/allow-listed, size and time limits |
| A tenant's feedback biases another tenant's model | Partitioned experience and skill versions; shared pool only on opt-in |
| A verdict is disputed months later | `AuditLog` replays the exact versions and reproduces the report |
