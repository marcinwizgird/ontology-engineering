# Ontology Builder — Development Roadmap

Nine phases, from an empty repository to a governed, agentic ontology
development platform. Each phase is independently demonstrable and independently
useful; the ordering is driven by dependency, not by ambition.

**Scale.** 141 catalogued features (see
[FEATURE_EXTRACTION.md](FEATURE_EXTRACTION.md)), realising 42 of the 44
capabilities in the capability model.

| Phase | Theme | Features | of which MUST | Cumulative |
|---|---|---:|---:|---:|
| **P0** | Governance Core | 27 | 19 | 27 |
| **P1** | Change Spine | 8 | 5 | 35 |
| **P2** | Authoring Core | 30 | 25 | 65 |
| **P3** | Quality Gate | 11 | 7 | 76 |
| **P4** | Extension & IO Framework | 18 | 6 | 94 |
| **P5** | Collaboration & Release | 17 | 4 | 111 |
| **P6** | Alignment & Metadata | 17 | 3 | 128 |
| **P7** | Agentic Layer | 11 | 6 | 139 |
| **P8** | Scale-out | 2 | 0 | 141 |

**EKGF trajectory.** P0–P4 complete the Level-2 *Extensible Platform* target of
the existing application architecture. P5–P6 reach Level 3 *Enterprise Ready*.
P7–P8 reach Levels 4–5.

---

## Sequencing rationale

Three questions decide the order, and only three:

1. **What cannot be retrofitted?** Project scoping, the authorization
   declaration on every endpoint, and the single write path. Hence P0–P1
   before any editing feature.
2. **What is the smallest thing a real user can use?** A governed SKOS/OWL
   editor over Fuseki with search and history. That is P2, and it is the first
   release worth putting in front of a domain expert.
3. **What makes the agents trustworthy rather than merely impressive?** The
   staging workflow (P1), the quality gate (P3) and machine identities (P0).
   All three precede P7 deliberately — an authoring agent shipped before them
   is an unreviewable liability.

A tempting alternative — build the editor first, add governance later — is what
VocBench 2 did, and rewriting it was the reason VocBench 3 exists.

---

## P0 · Governance Core

*Projects, identity, capabilities, the named-graph layout, the typed API.*
**27 features · 19 MUST.** See
[GOVERNANCE_FOUNDATION.md](GOVERNANCE_FOUNDATION.md) for the design.

### Workstreams

**W0.1 — Store layout and coordinator** (`store/`)
`layout.py` as the single source of truth for graph IRIs; `coordinator.py` with
one write queue per dataset; backup/restore procedure; Lucene text index
declared in the TDB2 assembler.
→ OB.STO.01, OB.STO.02, OB.STO.06

**W0.2 — Capability engine** (`governance/capabilities.py`, `pdp.py`)
Parse and evaluate `auth(area(subject[,scope]), "CRUDV")`; subsumption rules;
`%resource_role%` substitution; resolved-grant-set computation with per
(user, project) memoisation; invalidation on `PermissionsChangedEvent`.
→ OB.GOV.02, OB.GOV.10, OB.GOV.13

**W0.3 — Identity** (`governance/users.py`, `groups.py`, `bindings.py`,
`sharing.py`, `machines.py`, `auth.py`)
Accounts and registration lifecycle; groups with owned schemes; project–user
bindings carrying roles, group, `groupLimitations` and `languages`; per-person
sharing grants; **machine accounts**; local auth plus an OIDC provider.
→ OB.GOV.01, OB.GOV.06, OB.GOV.07, OB.GOV.08, OB.GOV.09, OB.GOV.12

**W0.4 — Roles** (`governance/roles.py`)
Role model with inheritance; the eight default roles as seed data; the role
editor API (create, clone, add/update/remove capability, export/import).
→ OB.GOV.03, OB.GOV.04, OB.GOV.05

**W0.5 — Projects** (`projects/`)
Registry and lifecycle; model + lexicalization-model profile; scoped settings;
ACL and lock levels; visibility and startup policy; facets and the facet index;
templates; multilingual labels; trash.
→ OB.PRJ.01–OB.PRJ.09

**W0.6 — API foundation** (`api/`, `governance/decorators.py`,
`extensions/settings.py`)
FastAPI app; `@guarded`; `ProjectContext` dependency; OpenAPI emission; the
scoped settings/configuration substrate; the build-breaking test that no route
is unguarded.
→ OB.SPQ.04, OB.GOV.11, OB.EXT.02

**W0.7 — UI skeleton**
React shell, generated client, login, project list in list *and* facet mode,
project creation wizard, settings, ACL matrix, sharing dialog, user/role/group
administration.
→ contributes to OB.UIX.01–03

### Exit criteria

Criteria 1–4 and 9–10 of
[GOVERNANCE_FOUNDATION.md §6](GOVERNANCE_FOUNDATION.md#6-acceptance-criteria-for-the-foundation).
Concretely: a project is created and shared through the UI; its graphs exist in
Fuseki under the documented layout; a language-restricted binding is enforced on
both sides from one grant set; `pytest` proves every route is guarded; a
machine account can authenticate and is refused a capability it lacks.

### Risks

*Over-engineering the capability grammar.* Implement subsumption for the cases
the 330 extracted goals actually use; do not build a general datalog engine.
*Under-testing the coordinator.* Write the crash-consistency test (criterion 9)
in this phase, not later.

---

## P1 · Change Spine

*Triple-level tracking, provenance, staging graphs, the validation workflow.*
**8 features · 5 MUST.**

### Workstreams

**W1.1 — ChangeSet** (`changes/changeset.py`, `tracker.py`, `guard.py`)
Delta computation; routing to `main` or staging by project configuration;
one-transaction apply with provenance; `guard()` pre-flight lifted from the
existing playground service; the enforcement that no module outside `changes/`
touches the store's write methods.
→ OB.CHG.01, OB.CHG.08

**W1.2 — Provenance and history** (`changes/provenance.py`)
Commit records (actor, operation, parameters, start/end, created/modified/
deleted); paged, filterable history API; commit delta with truncation.
→ OB.CHG.02, OB.CHG.03

**W1.3 — Validation workflow** (`changes/validation.py`)
Staging-graph read assembler with source tagging; the staged-change queue;
accept (apply to main, keep history) and reject (erase, no history); the `V`
capability check; blacklisting.
→ OB.CHG.04, OB.CHG.07

**W1.4 — Undo and revert** (`changes/undo.py`)
Per-user undo; reverse-apply of a historical commit.
→ OB.CHG.05, OB.CHG.06

**W1.5 — UI**
Validation queue with diff preview; history browser with filters and delta view;
"proposed" rendering treatment (the green-italic convention) wired into the
value renderer contract that P2 will consume.

### Exit criteria

Criteria 5–8 of the governance acceptance list, as automated tests. In
particular: **a raw SPARQL Update through the console produces a correct history
entry.** That single test is the proof that the invariant holds.

### Risks

*The three-graph read path.* Build one assembler, test it exhaustively, and
forbid ad-hoc graph reads in feature code — a subtly wrong union is invisible
until an export is wrong.

---

## P2 · Authoring Core

*The first release a domain expert can use.* **30 features · 25 MUST.**

### Workstreams

**W2.1 — Extension registry** (`extensions/registry.py`)
Entry-point discovery, typed configuration, the six scopes. Ships here — before
its consumers — because URI generation and rendering depend on it.
→ OB.EXT.01

**W2.2 — Identity of things** (`authoring/urigen.py`, `rendering.py`)
IRI minting strategies (label-derived, UUID, OBO numeric with per-user ranges,
prefix/suffix settings, whitespace treatment); display-string computation with
language preference order and a URI/qname toggle.
→ OB.EDT.08, OB.EDT.09

**W2.3 — OWL authoring** (`authoring/owl/`)
Classes and taxonomy; class expression axioms; properties across all four kinds
with domains, ranges, chains and characteristics; individuals and assertions;
datatypes with facets; deprecation.
→ OB.EDT.01, OB.EDT.02, OB.EDT.04, OB.EDT.05, OB.EDT.06, OB.VER.05

**W2.4 — Class expressions** (`authoring/manchester.py`, `owl/restrictions.py`)
The **renderer** (RDF → Manchester string) plus a **structured restriction
builder** (property · quantifier · filler, with a live preview). Deliberately
*not* the parser: measured on the local FIBO corpus, 91.2% of the 6,388
restrictions have a named filler and need no free-text syntax. The renderer is
required to browse FIBO at all — without it, two thirds of FIBO's semantic
content renders as blank nodes.
→ OB.EDT.03, OB.EDT.15  ·  parser deferred to P6 as OB.EDT.14

**W2.5 — SKOS authoring** (`authoring/skos/`)
Concepts, schemes, top concepts, bulk scheme membership; collections and
ordered collections; pref/alt/hidden labels and notes; SKOS-XL reified labels;
sub-property-qualified relations; the terminologist view.
→ OB.SKO.01–OB.SKO.05

**W2.6 — Generic and bulk editing** (`authoring/triples.py`, `bulk.py`,
`refactor.py`)
Full triple-level inspection and editing including blank nodes; bulk annotation
edits as one reviewable change set; rename, merge, base-URI replace,
SKOS↔SKOS-XL, split/amalgamate axioms, move axioms between ontologies.
→ OB.EDT.07, OB.EDT.10, OB.EDT.11

**W2.7 — Imports and prefixes** (`metadata/imports.py`)
Ontology header and annotations; prefix declarations; base URI and default
namespace; import closure from web/local/mirror.
→ OB.EDT.12

**W2.8 — Browsing** (`browse/`)
Model-driven structure panels; paged, lazily-expanded hierarchies with
path-from-root; **the resource view** with its ~30 typed sections and
per-section CRUD authorization.
→ OB.BRW.01, OB.BRW.02, OB.BRW.03

**W2.9 — Search** (`search/`)
Lucene-backed resource search with mode/language/scheme/role filters; instance
search; path-from-root for reveal-in-tree; SPARQL fallback.
→ OB.SRCH.01

**W2.10 — SPARQL console** (`sparql/console.py`)
Query and update with prefix completion and result download — with update
routed through `ChangeSet`.
→ OB.SPQ.01

**W2.11 — UI**
Shell, virtualised trees and lists, the resource view with its section
renderers, editor widgets (Manchester, Turtle, SPARQL, language-tagged
literals, pickers), permission-aware rendering, generated API client.
→ OB.UIX.01–OB.UIX.05

### Exit criteria

A domain expert creates a SKOS thesaurus and an OWL ontology end to end:
authoring, browsing, searching, editing labels in their own language, with every
change appearing in history and — where validation is on — in the review queue.
Round-trip fidelity test: load a FIBO module, edit one label through the UI,
save, and assert **zero** unintended triple changes (the test the
Ontology-Playground surface failed).

### Risks

*The resource view balloons.* It is 30
sections × 4 CRUD operations; build the section contract once and generate the
rest.

---

## P3 · Quality Gate

*Reasoning, constraints, integrity checks, competency-question tests.*
**11 features · 7 MUST.**

### Workstreams

**W3.1 — Reasoning** (`reasoning/`)
The multi-reasoner framework — capability declarations, the profile screen, the
per-operation routing policy, explicit degradation and the differential harness
(prototyped in [`spike_reasoners/`](spike_reasoners/)); owlrl (OWL 2 RL) and
Fuseki-rules implementations;
materialisation into the `inferred` graph with a freshness stamp; asserted-vs-
inferred rendering throughout; trivial-inference toggle.
→ OB.RSN.01, OB.RSN.02, OB.RSN.05, OB.BRW.04

**W3.2 — Explanation** (`reasoning/explain.py`)
Justification for an inferred axiom or an inconsistency. Within OWL 2 RL this is
rule-provenance tracking, which is tractable; true DL justification (OWL
Explanation over HermiT/ELK) arrives with the sidecar in P6. **State the profile
in the UI** so a user never mistakes an RL explanation for a DL one.
→ OB.RSN.03

**W3.3 — Constraints** (`quality/shacl.py`, `reasoning/rules.py`)
SHACL shapes graph, on-demand and on-commit validation, report model; rule
management seeded from the existing `reasoning_patterns.yaml`.
→ OB.QLT.01, OB.RSN.04

**W3.4 — Integrity constraint validation** (`quality/icv.py`)
The 38 checks extracted from VocBench, **each with its remediation operation**:
dangling concepts, hierarchical cycles and redundancies, multiple prefLabels per
language, overlapped and conflicting labels, no-scheme concepts, top concepts
with broaders, extra spaces, invalid URIs, missing definitions, broken
alignments, dangling xLabels.
→ OB.QLT.02

**W3.5 — Competency-question tests** (`quality/cq_tests.py`)
CQ as a first-class artifact: text, SPARQL realisation, expected result shape,
owner, linked requirement. Runs as a suite on every change. **None of the three
reference tools has this** — it is where the merged product exceeds them.
→ OB.QLT.03

**W3.6 — Metrics and the gate** (`quality/metrics.py`, `gate.py`)
DL expressivity, axiom counts, label completeness per language, coverage; a
configurable commit policy that blocks or routes to validation on breach.
→ OB.QLT.04, OB.QLT.05

**W3.7 — UI**
ICV dashboard with one-click fixes; SHACL report; CQ suite with pass/fail
history; inferred-axiom toggles and explanation panels.

### Exit criteria

A commit that introduces an unsatisfiable class, a SHACL violation, a dangling
concept or a failing CQ is blocked or routed to validation according to project
policy — and the editor is shown *why*, with a fix where one exists.

---

## P4 · Extension & IO Framework

*The plumbing that lets the platform grow without forking.*
**18 features · 6 MUST.**

### Workstreams

**W4.1 — IO extension points** (`io/`)
Loaders (stream- and repository-targeting), RDF lifters, RDF transformer
chains, reformatting exporters, deployers — each a registered factory with
stored, reusable, shareable configurations. Named-graph selection on export.
→ OB.IO.01–OB.IO.06

**W4.2 — Store and search extensions**
Repository configuration templates, remote repository registration, credential
management; pluggable search strategy; data preloading with profiling.
→ OB.STO.03, OB.STO.05, OB.SRCH.02, OB.SRCH.03

**W4.3 — Forms** (`forms/`)
WebProtégé's descriptor model (form → fields → controls: text, choice, grid,
sub-form, collection) with OWL property binding and a change generator;
form collections and type mappings; import/export between projects; validation
and broken-form detection; the SPARQL-CONSTRUCT escape hatch.
→ OB.FRM.01, OB.FRM.02, OB.FRM.04

**W4.4 — Metadata patterns and custom trees**
Resource-metadata patterns (creator/created/modified stamping) with a shareable
library; custom trees over arbitrary properties; ontology mirror.
→ OB.MDR.04, OB.BRW.06, OB.EDT.13

**W4.5 — Stored queries** (`sparql/stored.py`)
Save, scope, share and parameterise queries; pipe graph results through
transformer chains.
→ OB.SPQ.02

**W4.6 — Auto-generated configuration UI**
JSON-Schema → React form renderer, so a new extension needs no front-end work.
This is what keeps the React layer from bottlenecking backend extensibility.
→ OB.EXT.03

### Exit criteria

A third party adds a new deployer and a new URI generator **without modifying
Builder code** — installed as a package, discovered by entry point, configured
through an auto-generated form.

---

## P5 · Collaboration & Release

*Making it a team platform and a publishing platform.*
**17 features · 4 MUST.**

### Workstreams

**W5.1 — Collaboration** (`collaboration/`)
`CollaborationBackend` extension point with **GitHub Issues** and **Jira**
implementations plus a minimal built-in tracker; issues bound to resources and
surfaced in the resource view; threaded comments with resolved/open status;
watches on resources and branches; scheduled notification digests with
time-zone handling; Slack/webhook targets.
→ OB.COL.01–OB.COL.04

**W5.2 — Versioning** (`versions/`)
Tagged snapshots; editable forks; time machine, global and per-resource;
release packaging through deployer chains; version diffing.
→ OB.VER.01–OB.VER.04, OB.IO.07

**W5.3 — Publishing** (`io/docs.py`)
Documentation generation per release (pyLODE/Widoco-class) and a published
portal — the second gap common to all three reference tools.
→ OB.IO.08

**W5.4 — Editorial workflow surface**
Entity tags with criteria-based assignment; project dashboard and portfolio
metrics; resource-view section customisation; perspectives and saved layouts;
UI localisation and branding.
→ OB.MDR.05, OB.PRJ.10, OB.BRW.07, OB.BRW.08, OB.UIX.06, OB.UIX.07, OB.BRW.05

### Exit criteria

A release is cut, documented, published and announced; a reviewer watching a
branch receives a digest; an issue raised on a concept is visible from that
concept's resource view.

---

## P6 · Alignment & Metadata

*Connecting to the wider ecosystem.* **17 features · 3 MUST.**

### Workstreams

**W6.1 — Alignment** (`alignment/`)
Interactive cross-project alignment under the ACL grant; the alignment
validation queue (accept/reject individually, all-above-threshold,
all-under-threshold) with projection onto real mapping properties; EDOAL
correspondences with relation, measure and status; remote matcher registration
and task management; MAPLE-style matching-problem profiling; mappings written
to their own named graph.
→ OB.MAP.01–OB.MAP.06

**W6.2 — Metadata and catalogs** (`metadata/`)
DCAT / DCAT-AP / ADMS / VoID / LIME dataset description with computed
statistics; the metadata registry (catalog records, versions, distributions,
endpoints, linksets); external catalog connectors for search-and-import.
→ OB.MDR.01–OB.MDR.03

**W6.3 — OWL API sidecar** (`services/owl-sidecar`, `ontology_builder.sidecar`)
One stateless JVM service behind Python interfaces: Manchester
parse/render/complete via OWL API; DL classification and justifications via
HermiT/ELK plus OWL Explanation; optionally ROBOT for release operations. Pin
the OWL API version. Per-project entity dictionary cached in the sidecar and
invalidated by change events, so completion is not an N+1 round trip.
→ OB.EXT.05, OB.EDT.14, and the DL tier of OB.RSN.01 / OB.RSN.03

**W6.4 — Lifting and reporting**
Spreadsheet/DB lifting with header mapping and triple preview; custom views;
custom services; invokable reporters; OntoLex lexicon support if in scope.
→ OB.S2R.01, OB.FRM.03, OB.SPQ.03, OB.QLT.06, OB.LEX.01, OB.LEX.02

### Exit criteria

An in-house ontology is aligned to FIBO through the validation queue; the
mappings live in their own graph; the dataset publishes a DCAT-AP description;
the platform can discover and import an ontology from an external catalog.

---

## P7 · Agentic Layer

*The reason for building the rest of it first.* **11 features · 6 MUST.**

Every agent here is a client of the typed API, running under a machine identity,
subject to the PDP, writing only to staging.

### Workstreams

**W7.1 — Tool surface and identities**
Typed agent tools over the API with declared read/write intent and required
capability; machine accounts, attribution in commit provenance, audit views.
→ OB.AGT.01, OB.AGT.09

**W7.2 — Assistant** (read-only)
Implement `../ontology_assistant/` as specified — the retrieval funnel, the
Concept Card / Evidence Bundle / Module Digest / Answer artifacts, the
deterministic verbaliser, the grounding critic and its hard gates. Requires the
FalkorDB projection.
→ OB.AGT.02, OB.STO.04

**W7.3 — Authoring copilot**
Drafts classes, properties, labels, definitions and axioms from a brief or a
competency question, into staging, with justifications. Reuses the Enricher
pipeline and the forms engine.
→ OB.AGT.03

**W7.4 — Quality, alignment and CQ agents**
Remediation agent over the 38 ICV checks and their fixes; matcher agent behind
the remote-alignment interface; competency-question agent that elicits CQs and
synthesises their SPARQL tests.
→ OB.AGT.04, OB.AGT.05, OB.AGT.06

**W7.5 — Steward agent and evaluation**
Stale-proposal and stewardship-gap surfacing against the capability model's
target maturity; the evaluation harness in CI for every agent.
→ OB.AGT.07, OB.AGT.08

**W7.6 — Bottom-up pipeline integration**
`bottomup_ontology/` wired in as a lifting source whose candidates land in
staging.
→ OB.S2R.02

### Exit criteria

The copilot proposes 100 axioms from a domain brief; a human validator accepts
or rejects each; the acceptance rate, the ICV delta and the CQ-coverage delta
are all measured by the harness; every proposal is attributed to the machine
account and every assistant claim carries a citation. **No agent holds `V`.**

---

## P8 · Scale-out

*Hardening.* **2 catalogued features, plus non-functional work.*

* Git repository synchronisation with axiom-level change tracking (OB.COL.05) —
  the bridge from versioning (`T.OO.2`) to OntoOps CI/CD (`T.OO.3`).
* UI extension slots via module federation (OB.EXT.04) — the thing VocBench
  could not do.
* Sidecar hardening — horizontal scaling, warm pools, per-request memory and
  timeout budgets for pathological ontologies.
* Federation and virtualisation (`T.OO.4`), observability and monitoring
  (`T.OO.5`) per the technical requirements catalogue.
* Multi-tenant hardening, performance work at EuroVoc/FIBO scale.

---

## Cross-cutting practices

Adopted from what already works in this repository.

| Practice | Why |
|---|---|
| Dependency-light core | networkx + stdlib + rdflib in the core; heavy deps behind interfaces |
| Steps and services as agent tools | every service function individually testable and callable by an agent, as in `bottomup_ontology/tools.py` |
| Notebooks executed headless as functional tests | `jupyter nbconvert --execute` in CI, per existing convention |
| Generated documentation | `build_docs.py` regenerates the feature and capability documents; the model is the source of truth |
| Model validation in CI | `feature_model.validate_model()` must return empty |
| ASCII in console output | Windows console is cp1252 (`PYTHONIOENCODING=utf-8` where needed) |

---

## Decisions already taken

Recorded so they are not relitigated.

| # | Decision | Rationale |
|---|---|---|
| D1 | **Capability grammar from VocBench, role inheritance from WebProtégé** | VB3's CRUDV algebra with resource-role binding is strictly more expressive; WP's inheriting roles are the one place WP is better |
| D2 | **Governance stored as RDF in Fuseki, not in a document store** | auditable and queryable with the same SPARQL as the content; VocBench's R15 vindicated |
| D3 | **Forms: WebProtégé's descriptor model, not PEARL/CODA** | portable to Python/React without importing a triplification runtime; SPARQL-CONSTRUCT covers the expressive gap |
| D4 | **Generated TypeScript client, not hand-written services** | the single clearest lesson from reading VocBench's 60 mirrored service classes |
| D5 | **Permission evaluated client-side from a server-sent grant set** | same UX as VocBench's client-side Prolog, without a second policy engine |
| D6 | **OWL 2 RL in-process in P3; DL classification and justifications via the sidecar in P6, behind one `ReasonerBackend` interface** | ships reasoning in P3 with no Java dependency; true DL has no Python implementation at all, so the sidecar is the only path to `T.RI.4` |
| D7 | **Manchester *rendering* in Python in P2; *parsing* via a JVM sidecar in P6 — not a Lark grammar** | measured: 91.2% of FIBO's 6,388 restrictions have a named filler, so the structured builder covers them and the renderer (~150 lines) is the only urgent half. For the rest, wrapping OWL API's `ManchesterOWLSyntaxFramesParser` is 6 lines and its `ParserException` yields completion follow-sets for free; a grammar would mean rebuilding that machinery by hand |
| D8 | **Agents never hold `V` and never write to `main`** | makes agent output reviewable by the workflow that already exists for humans |
| D9 | **The playground write-safety core is reused, not replaced** | `guard()`, `GraphSynchronizer` and the projection/merge code are already live-verified against a 133k-triple dataset |
| D10 | **Funding (`B.SG.4`) and value-case (`B.VP.1`) stay out of scope** | realised by enterprise systems; the Builder feeds them signals |
| D11 | **One JVM sidecar (`OB.EXT.05`), pulled forward from P8 to P6** | it serves two unrelated gaps — Manchester parsing/completion and DL classification with justifications. Neither has a Python implementation. Judged against Manchester alone a sidecar looks expensive; judged against both, the marginal cost of the second use is near zero. WebProtégé set the precedent with `webprotege-robot-service` |

---

## Open decisions

Worth settling before the phase in which they bite.

**O1 — OntoLex scope (bites at P6).** VocBench's OntoLex service is 46
operations, the single largest in the platform, and is only valuable to
organisations building multilingual lexical resources. Include, defer, or drop?
*Recommendation: defer to P6 and gate on a real use case.*

**O2 — Built-in issue tracker or connector-only (bites at P5).** Both reference
platforms concluded "connect to what the organisation already uses". A minimal
built-in tracker is still needed for deployments with no Jira/GitHub.
*Recommendation: connector-first, with a deliberately thin built-in fallback.*

**O3 — Identity provider (bites at P0).** Keycloak (WebProtégé's choice, brings
its own admin UI and user management service) versus a lighter OIDC client
against whatever the organisation runs.
*Recommendation: OIDC client interface in P0, Keycloak as the reference
deployment, no hard dependency.*

**O4 — Where the FalkorDB projection sits (bites at P7).** The Assistant needs
it; nothing before P7 does. Building it early gives the graph view (OB.BRW.05)
better performance but adds an operational component to maintain from P5.
*Recommendation: build in P7 with the Assistant, keep the P5 graph view on
Fuseki queries.*

**O5 — Multi-tenancy model (bites at P0, expensive later).** One Fuseki dataset
per environment with project-scoped graphs (simple, one write lock) versus one
dataset per project (parallel writes, more operational surface).
*Recommendation: one dataset per environment initially — but make
`store/layout.py` the only place that knows, so the decision is reversible.*

**O6 — Reasoning profile disclosure (bites at P3).** RL entailments and DL
entailments differ in ways that matter to an ontologist. How prominently must
the active profile be shown?
*Recommendation: profile badge on every inferred-axiom rendering, and in the
explanation panel header. Cheap, and it prevents a whole class of misplaced
trust.*
