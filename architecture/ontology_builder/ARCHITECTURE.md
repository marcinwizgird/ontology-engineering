# Ontology Builder — Target Architecture

Python backend · Python AI agents · React UI · Apache Jena Fuseki as the
canonical store.

This is the component that merges VocBench 3, WebProtégé and Protégé Desktop
into the Knowledge Graph Agentic Platform. It supersedes and absorbs
`C.AUTH` (Ontology Authoring Workbench), `C.VOCAB` (Vocabulary & Thesaurus
Manager), `C.REPO` (Ontology Repository & Version Control) and parts of
`C.RVE` (Reasoning & Validation Engine) from
[`architecture/ARCHITECTURE.md`](../ARCHITECTURE.md) — that document listed
"Protégé" and "VocBench" as *technology candidates* for those components; this
one replaces the candidates with a build.

---

## 1. Principles

Five decisions, each traceable to something learned from reading the source.

**P1 · Governance is the substrate, not a module.**
Projects, capabilities and change tracking exist before the first class editor.
See [GOVERNANCE_FOUNDATION.md](GOVERNANCE_FOUNDATION.md).

**P2 · One write path.**
Nothing reaches Fuseki except through `ChangeSet.apply()`. This is the
generalisation of VocBench's SAIL interception to a store that has no
interception point, and it is what makes history complete rather than partial.

**P3 · Everything is RDF, including governance.**
VocBench's R15. Users, roles, bindings, settings, commits and staged proposals
are named graphs in the same dataset as the content — auditable and
back-uppable by the same machinery. (WebProtégé chose MongoDB; we do not.)

**P4 · The typed API is the product; the UI is its first client.**
VocBench hand-wrote 60 Angular service classes mirroring its server. We
generate the TypeScript client from OpenAPI instead. Agents, notebooks, CI and
the React app all call the same contract.

**P5 · Extension points before extensions.**
VocBench's 15 extension points and Protégé's 24 are the reason both survived a
decade of requirements they did not anticipate. The registry ships in P2, before
most of the things that plug into it.

**Corollary — no lossy editing surface.** The round-trip probe recorded in
`playground-fuseki-workbench` showed the Microsoft Ontology-Playground model
preserving only ~18–23% of a FIBO module and ~6.5% of the SKOS-based in-house
ontologies. The resource view (OB.BRW.03) plus generic triple editing
(OB.EDT.07) exist so that no edit ever passes through a model that cannot see
what it is about to overwrite.

---

## 2. Component view

```
┌──────────────────────────────────────────────────────────────────────────┐
│ React SPA  (ontology_builder_ui)                                         │
│  shell · perspectives · structures · resource view · forms · SPARQL      │
│  generated OpenAPI client · permission-aware rendering (grant set)       │
└───────────────▲──────────────────────────────────────────────────────────┘
                │ REST/JSON + SSE (events)
┌───────────────┴──────────────────────────────────────────────────────────┐
│ FastAPI edge  (ontology_builder.api)                                     │
│  @guarded routes · OpenAPI · SSE event stream · file upload/download     │
└───────────────▲──────────────────────────────────────────────────────────┘
                │
┌───────────────┴──────────────────────────────────────────────────────────┐
│ Service layer                                                            │
│                                                                          │
│  governance   projects   changes    versions   authoring   browse        │
│  search       forms      reasoning  quality    io          alignment     │
│  metadata     sparql     collaboration  extensions  lifting              │
│                                                                          │
│  ── every service call passes the PDP; every write builds a ChangeSet ── │
└───────┬──────────────────────────────────────────┬───────────────────────┘
        │                                          │
┌───────▼──────────────────────┐      ┌────────────▼─────────────────────┐
│ Write coordinator            │      │ Agent runtime                    │
│  one queue per dataset       │      │  assistant · copilot · quality   │
│  ChangeSet → 1 transaction   │      │  aligner · CQ · steward          │
│  guard() pre-flight          │      │  machine identities, own PDP     │
└───────┬──────────────────────┘      └────────────┬─────────────────────┘
        │                                          │ tools = the typed API
┌───────▼──────────────────────────────────────────▼───────────────────────┐
│ Apache Jena Fuseki / TDB2   (canonical)     FalkorDB (derived projection)│
│  content · imports · staging · inferred · shapes · mappings · metadata   │
│  governance graphs · history graphs         embeddings · neighbourhoods  │
│  Lucene text index                                                       │
└──────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────────────────┐
│ Sidecars (optional, behind interfaces)                                   │
│  OWL sidecar: OWL API (Manchester) · HermiT/ELK + Explanation · ROBOT    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend

### 3.1 Package layout

```
ontology_builder/
├─ api/                    FastAPI routers, OpenAPI, SSE, dependency wiring
│  ├─ deps.py              current user, current project, PDP dependency
│  └─ routers/             one router per service package
├─ governance/             ← the foundation
│  ├─ capabilities.py      Capability grammar, parsing, subsumption
│  ├─ roles.py             Role, inheritance resolution, defaults
│  ├─ users.py             accounts, registration, custom fields
│  ├─ groups.py            groups, project-group bindings, owned schemes
│  ├─ bindings.py          ProjectUserBinding (roles, group, languages)
│  ├─ sharing.py           per-person VIEW/COMMENT/EDIT/MANAGE grants
│  ├─ machines.py          machine/service accounts (agents, CI)
│  ├─ auth.py              local + OIDC, token → subject
│  ├─ pdp.py               authorize(); resolved grant set; cache; events
│  └─ decorators.py        @guarded — the declarative authorization annotation
├─ projects/               registry, settings, facets, ACL, templates, dashboard
├─ store/                  Fuseki client wrapper, named-graph layout, backup
│  ├─ layout.py            graph IRI algebra — the single source of truth
│  ├─ coordinator.py       per-dataset write queue, transaction boundary
│  └─ projection.py        FalkorDB sync (derived, never authoritative)
├─ changes/                ← the spine
│  ├─ changeset.py         ChangeSet: delta computation, routing, apply
│  ├─ tracker.py           interception invariant, SPARQL-Update diffing
│  ├─ provenance.py        commit records
│  ├─ validation.py        staging graphs, accept/reject, blacklist
│  ├─ guard.py             pre-flight preservation check
│  └─ undo.py
├─ versions/               snapshots, time machine, release, diffing
├─ authoring/
│  ├─ owl/                 classes, properties, individuals, datatypes, axioms
│  ├─ skos/                concepts, schemes, collections, labels, notes
│  ├─ ontolex/             lexicons (P6, optional)
│  ├─ triples.py           generic triple-level editing
│  ├─ manchester.py        render (P2, Python) · parse+complete (P6, sidecar)
│  ├─ urigen.py            IRI minting strategies (extension point)
│  ├─ rendering.py         display-string computation (extension point)
│  └─ refactor.py          rename, merge, split, move axioms, base-URI replace
├─ browse/                 hierarchy paging, resource view assembly, graph view
├─ search/                 Lucene-backed + SPARQL fallback, custom searches
├─ forms/                  descriptors, binding, change generation, validation
├─ reasoning/              backend registry, router, profile screen, materialisation,
│                          explanation, rules  (see spike_reasoners/)
├─ quality/                shacl, icv (38 checks + fixes), cq_tests, metrics, gate
├─ io/                     loaders, lifters, transformers, exporters, deployers
├─ alignment/              interactive, validation queue, EDOAL, remote matchers
├─ metadata/               imports/prefixes, DCAT/VoID, registry, catalogs, tags
├─ sparql/                 guarded console, stored queries, custom services
├─ collaboration/          issues, comments, watches, digests, integrations, git
├─ extensions/             registry, entry points, scoped settings/configurations
├─ lifting/                sheet2rdf-style mapping; bottom-up text pipeline
├─ sidecar/                typed Python client for the JVM OWL sidecar (P6)
└─ agents/                 tools, assistant, copilot, quality, aligner, cq, steward
```

Areas map 1:1 to the `FeatureArea.package` values in
[`feature_model.py`](feature_model.py), so the catalogue and the code stay
aligned.

### 3.2 Stack

| Concern | Choice | Why |
|---|---|---|
| HTTP | **FastAPI** + Uvicorn | OpenAPI generation is the whole point (P4); dependency injection suits the PDP wiring |
| Models | **Pydantic v2** | one schema serves validation, OpenAPI, the generated TS client, and the auto-generated settings forms (OB.EXT.03) |
| RDF | **rdflib** + existing `FusekiClient` | already in use across `ontology_modeler`, `bottomup_ontology`, the Enricher |
| SHACL | **pySHACL** | no sidecar needed |
| RL reasoning | **owlrl** | pure Python OWL 2 RL; already used in the Ch.4 notebooks |
| DL reasoning + justifications | **JVM sidecar** (HermiT/ELK + OWL Explanation), **P6**, behind `ReasonerBackend` | no Python implementation exists at any price; the same sidecar also serves Manchester parsing, which is what makes it worth its operational cost |
| Manchester syntax | **hand-written renderer** in Python (P2); **OWL API via the sidecar** for parsing and completion (P6) | rendering is a recursive walk (~150 lines) and is needed on day one to browse FIBO; parsing is delegated rather than rewritten — `ParserException` gives structured errors *and* completion follow-sets for free — see OB.EDT.03 / OB.EDT.14 / OB.EDT.15 / OB.EXT.05 |
| Search | **Fuseki `text:query`** (Lucene, declared in the TDB2 assembler) | the analogue of VocBench's store-specific `SearchStrategy`; SPARQL FILTER fallback stays for portability |
| Async work | **Celery/RQ** or asyncio tasks | reasoning, bulk import, alignment runs, digests — all off the write path |
| Events | **SSE** from FastAPI | the React client needs change/permission events; WebProtégé uses an event-history service, we start simpler |
| Extensions | **entry points** (`ontology_builder.extensions.*`) | the Pythonic OSGi |
| Agents | **LangGraph** + the Claude API | matches the course/agent conventions already in this repo |

### 3.3 Cross-cutting patterns

**The guarded endpoint.**

```python
@router.post("/projects/{project}/classes")
@guarded(capability="rdf(cls)", ops="C", writes=True)
async def create_class(req: CreateClassRequest,
                       ctx: ProjectContext = Depends(project_ctx)) -> ClassRef:
    async with ctx.changeset("createClass", req.model_dump()) as cs:
        cs.add((req.iri, RDF.type, OWL.Class))
        if req.superclass:
            cs.add((req.iri, RDFS.subClassOf, req.superclass))
    return ClassRef(iri=req.iri)
```

`ctx.changeset(...)` is the only way to write. It opens a commit, collects the
delta, runs `guard()`, routes to `main` or staging depending on
`project.validationEnabled`, writes the provenance, and commits — one
transaction, or none.

**The extension factory.**

```python
class URIGenerator(ExtensionPoint):
    id = "ontology_builder.urigen"
    class Config(BaseModel): ...          # renders itself in the UI
    def generate(self, ctx: MintContext) -> URIRef: ...
```

Registered via entry points; discovered by `extensions.registry`; configured at
SYSTEM / PROJECT / USER / PROJECT_USER / PROJECT_GROUP / FACTORY scope.

**The resource view.** One assembler builds the ~30 typed sections for any
resource, tags every triple with its source graph (main / staging-add /
staging-del / imported / inferred), and attaches the per-section CRUD
authorization computed from the caller's grant set. The client renders; it does
not decide.

---

## 4. Agent layer

Agents are **clients of the same typed API**, running with **machine
identities** (OB.GOV.12) and subject to the **same PDP** as humans.

| Agent | Writes? | Capability profile | Built on |
|---|---|---|---|
| **Assistant** (OB.AGT.02) | no | `rdf(_,_) R` only | the complete design in [`../ontology_assistant/`](../ontology_assistant/) — reuse, do not redesign |
| **Authoring copilot** (OB.AGT.03) | staging only | editor capabilities **without `V`** | Enricher pipeline + forms + staging workflow |
| **Quality remediation** (OB.AGT.04) | staging only | `rdf(_,_) CRU` without `V` | the 38 ICV checks, each of which already carries its fix operation |
| **Alignment** (OB.AGT.05) | mapping graph only | `rdf(resource, alignment) CRU` | registers behind the remote-matcher interface |
| **Competency-question** (OB.AGT.06) | test suite only | `rdf(_,_) R` + CQ store write | assistant retrieval + `synthesize_cqs` |
| **Steward** (OB.AGT.07) | issues only | `rdf(_,_) R` + collaboration write | history, validation queue, capability model |

Three rules, none of them optional:

1. **No agent holds `V`.** Validation is a human act. This is what makes the
   copilot safe to run unattended.
2. **No agent writes to `main`.** Even with validation disabled on a project,
   agent writes are forced through staging.
3. **Every agent answer that asserts something about the ontology cites the
   triple it came from.** The Assistant design already specifies a grounding
   critic and hard gates; the copilot inherits them for its justifications.

The tool surface is the typed API (OB.AGT.01) plus the read-only retrieval tools
already catalogued in
[`../ontology_assistant/TOOL_CATALOG.md`](../ontology_assistant/TOOL_CATALOG.md).
Evaluation is the harness in
[`../ontology_assistant/EVALUATION.md`](../ontology_assistant/EVALUATION.md),
extended with authoring-quality metrics (acceptance rate of proposals, ICV
delta, CQ coverage delta).

---

## 5. React UI

```
ontology_builder_ui/
├─ shell/          routing, project context, layout, perspectives, branding
├─ api/            GENERATED from OpenAPI — never hand-written
├─ auth/           grant-set evaluation, <Can capability="rdf(cls)" ops="C">
├─ features/
│  ├─ projects/    project list (list & facet modes), creation wizard, settings,
│  │               ACL matrix, sharing dialog
│  ├─ governance/  users, groups, roles, capability wizard, bindings
│  ├─ structures/  class/concept/property/collection trees, instance & scheme
│  │               lists, alphabetic index, search bar
│  ├─ resourceView/ the ~30 sections, value renderers, section customisation
│  ├─ termView/    terminologist surface (per-language, RDF-free)
│  ├─ validation/  staged-change queue, accept/reject, diff preview
│  ├─ history/     commit list, filters, delta view, time machine
│  ├─ forms/       form designer + runtime renderer
│  ├─ sparql/      editor, results grid, stored queries
│  ├─ quality/     ICV dashboard with one-click fixes, SHACL report, CQ suite
│  ├─ alignment/   mapping workbench, alignment validation queue
│  ├─ graph/       model/data graph exploration
│  └─ agents/      chat surface, proposal review, agent run history
└─ components/     Tree (virtualised), editors (Manchester/Turtle/SPARQL),
                   SettingsRenderer (JSON-Schema → form), pickers, i18n
```

Choices worth stating:

* **Generated client (OB.UIX.03).** The clearest lesson from reading VocBench:
  60 hand-written service classes mirroring 781 server operations is a
  permanent tax. Generate.
* **Permission as data (OB.UIX.02).** The server sends the resolved grant set;
  the client evaluates `matches()` locally. Same semantics as VocBench's
  client-side Prolog, without a second engine.
* **Virtualisation is mandatory, not an optimisation.** EuroVoc-scale thesauri
  and FIBO-scale ontologies are the target; `react-window`-style windowing plus
  server paging from day one (VocBench's R5).
* **Perspectives (OB.BRW.07).** Taken from WebProtégé and Protégé Desktop, which
  both have it and VocBench does not. It is what lets one deployment serve
  ontologists, terminologists and reviewers without three products.
* **Extension slots (OB.EXT.04).** VocBench explicitly could not do UI plugins
  ("still missing in VB3, due to limitations of the Angular technology"). React
  module federation makes it practical — a place where the merged product beats
  both predecessors.

---

## 6. Where this sits in the platform

| Existing asset | Relationship |
|---|---|
| `ontology_engineering_capabilities/` | The requirements. Every Builder feature maps to ≥1 capability — see [CAPABILITY_MAPPING.md](CAPABILITY_MAPPING.md). |
| `architecture/ARCHITECTURE.md` | The L2 application architecture. The Builder **realises** `S.AUTH`, `S.IMPORT`, `S.VOCAB`, `S.VERSION`, `S.VIZ`, and contributes to `S.REASON`, `S.VALIDATE`, `S.CQTEST`, `S.DOCS`. |
| `architecture/technical architecture/` | The infra contract (`TR.SK.*` for Fuseki, `TR.PG.*` for FalkorDB, `TR.CN.*`/`TR.SP.*` for GCP). The Builder must satisfy it, not restate it. |
| `architecture/ontology_assistant/` | The read-only agent's full design. Becomes OB.AGT.02 verbatim. |
| `src/Ontology Modeler/` | The write-safety core: `FusekiClient`, `GraphSynchronizer`, `guard()`, projection/merge, `StructureExplorer`. Reused, not replaced. |
| `src/Ontology Enricher/` | Reasoning patterns, FIBO mappings, inferred closures. Becomes the seed of `reasoning/` and OB.AGT.03/05. |
| `src/Ontology Converter/` | RDF→LPG conversion. Feeds `store/projection.py` and the graph view. |
| `bottomup_ontology/` | The text→ontology pipeline. Becomes OB.S2R.02, writing into staging. |
| `Ontology Repository/FIBO/` | The corpus everything is tested against. |

**What the Builder does *not* own:** funding/portfolio (`B.SG.4`) and value-case
tracking (`B.VP.1`). Those stay with the enterprise's own systems; the Builder
feeds them project inventory and quality KPIs. See
[CAPABILITY_MAPPING.md §3](CAPABILITY_MAPPING.md).

---

## 7. Known hard parts

Stated up front, because each is a place where an optimistic plan would slip.

| Risk | Assessment | Mitigation |
|---|---|---|
| **Manchester syntax in Python** | No mature parser exists — but the need splits. *Rendering* RDF → Manchester is a recursive walk; *parsing* typed text back needs a grammar **plus** error recovery and completion follow-sets, which is where the effort actually is. Measured on the local FIBO corpus: 6,388 restrictions, **91.2% with a named filler**. | Renderer in Python in P2 (`OB.EDT.03`, required to browse FIBO at all) plus the structured builder (`OB.EDT.15`) covering the 91.2%. Parsing (`OB.EDT.14`) is *delegated* to OWL API through the sidecar in P6, not rewritten. |
| **DL reasoning in Python** | owlrl covers OWL 2 RL, not DL. There is no Python HermiT, and justifications are DL-only — so `T.RI.4` is unreachable in pure Python. | RL + Fuseki rules in P3 behind `ReasonerBackend`; the DL tier arrives in P6 via the sidecar (`OB.EXT.05`), paid for jointly with Manchester parsing. Always show which profile produced a given entailment or explanation. |
| **TDB2 single writer** | Structural, not tunable. | Write coordinator (§3.2 of the governance doc); long jobs compute off-path and swap in. |
| **781 operations is a lot of surface** | VocBench took years and an EU programme. | The phase plan ships ~35% of the surface (P0–P3) as a coherent product; OntoLex (46 ops), Sheet2RDF (31), MetadataRegistry (37) are explicitly late or optional. |
| **Forms: two incompatible designs** | VocBench's PEARL/CODA is more expressive; WebProtégé's descriptor tree is far more portable. | Adopt WebProtégé's model; add a SPARQL-CONSTRUCT escape hatch for what PEARL would have covered. Decided, not deferred. |
| **The staging read path** | Every read under validation is a three-graph union with provenance tagging. Easy to get subtly wrong, and wrong is invisible. | One assembler, heavily tested, used by everything. No ad-hoc graph reads in feature code. |
| **A JVM enters the stack (P6)** | New build toolchain, container, CVE surface and memory footprint; cold start on a keystroke-latency path; entity resolution risks an N+1 round trip. | Stateless service, warm pool, strict per-request memory and timeout budgets, pinned OWL API version, per-project entity dictionary cached in the sidecar and invalidated by change events. Everything behind Python interfaces so the dependency stays removable. |
| **Agent write safety** | An agent with ambient user credentials makes the audit trail a lie. | Machine identities from P0 (OB.GOV.12), enforced by the PDP, tested. |
