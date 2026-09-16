# The Governance Foundation

*Project management and governance over Apache Jena Fuseki — the load-bearing
layer everything else in the Ontology Builder stands on.*

> **A note on the brief.** The request named "project management and governance
> capabilities **from Fuseki**". Fuseki itself has none: it is a SPARQL server
> with datasets, named graphs, an assembler configuration and a thin shiro-based
> access filter. It has no concept of a project, a user, a role, an editorial
> workflow or a change history. Those concepts come from **VocBench 3 /
> Semantic Turkey**, which is the only one of the three reference platforms that
> treats them as first-class. This document therefore reads the brief as:
> **implement VocBench-class project management and governance, with Fuseki as
> the canonical store underneath.** Every design decision below follows from
> that reading; if the intent was narrower — Fuseki's own dataset/endpoint
> administration only — say so and §3 collapses to a much smaller piece of work.

---

## 1. Why this is the foundation and not a later feature

Three of the extracted features are the substrate of the entire product, and
retrofitting any of them is a rewrite rather than an addition:

| Feature | Why it cannot be deferred |
|---|---|
| **OB.PRJ.01** Project registry | Every other API call is scoped by project. Introducing the scope later means touching every endpoint, every graph name, every UI route. |
| **OB.GOV.02** Capability expression language | Authorization decisions must be *declared next to the operation*. Bolting a policy engine onto 700 unguarded endpoints afterwards is how systems end up with holes. |
| **OB.CHG.01** Triple-level change interception | If any write path can reach the store without going through the change tracker, history is not a record — it is a sample. VocBench learned this between v2 (operation-typed history, incomplete) and v3 (triple-level, complete). |

Everything else — authoring, reasoning, alignment, agents — is additive on top
of these three. That is why the roadmap spends **P0 and P1 entirely** on them
and does not ship a class editor until P2.

---

## 2. The four governance mechanisms worth porting

Read from source, these are the mechanisms that make VocBench a *governed*
editor rather than a multi-user one.

### 2.1 The capability expression language

VocBench does not enumerate permissions. It defines a grammar:

```
auth( <area>( <subject> [, <scope>] ), "<CRUDV>" )
```

* **areas** — `rdf` · `pm` (project management) · `rbac` · `um` (user management)
  · `cform` (custom forms) · `customService` · `invokableReporter` · `sys`
* **subjects** — for `rdf`: `cls`, `individual`, `concept`, `conceptScheme`,
  `objectProperty`, `datatypeProperty`, `annotationProperty`, `xLabel`,
  `ontolexLexicalEntry`, `limeLexicon`, `skosCollection`, `resource`, `import`,
  `dataset`, `code`, `datatype`, `alignment`, … (the `RDFResourceRolesEnum`,
  22 values)
* **scopes** — `taxonomy`, `instances`, `values`, `lexicalization`, `definitions`,
  `alignment`, `metadata`, `formRepresentations`, `constituents`, `subterms`, …
* **operations** — `C` `R` `U` `D` plus **`V` = validate**

Measured in `AuthorizationEvaluator.ts`: **330 distinct guarded actions**, of
which 155 are `rdf(...)`, 17 `pm(...)`, 12 `cform(...)`, 7 each for `sys`,
`invokableReporter` and `customService`, 2 `rbac(...)`.

A special token `%resource_role%` is substituted at evaluation time with the
*role of the resource being acted on*, so a single declaration
`auth(rdf(%resource_role%), "U")` covers "may update whatever kind of thing
this is" — the mechanism that keeps the policy from exploding combinatorially.

VocBench evaluates these as Prolog facts, on the server (tuProlog) **and** in
the browser (jsprolog), so the UI shows only what the user can actually do.

> **Port decision — validated by a working spike.** Adopt the grammar; **do
> not** adopt the dual Prolog runtime. A complete, tested Python port lives in
> [`spike_crudv/`](spike_crudv/): 520 lines, standard library only, 52 tests,
> ~16 µs per full decision. It transcribes all 24 `chk_capability` clauses,
> `covered/2`, `resolveCRUDV/2`, `resolveLANG/2`, the `role/1` and
> `vocabulary/2` fact tables, and the surrounding read-only / admin / language
> checks from `isGaolAuthorized`. Three subtleties it pins down with mutation-
> verified tests: the CRUDV subset test runs on the **request** (inverting it
> turns every reader into an editor), `rdf(sparql,support)` is **cut** (so a
> blanket `rdf` grant must not confer endpoint access), and `covered/2` is
> **directional**. See [`spike_crudv/README.md`](spike_crudv/README.md).
>
> In Python, a capability is a small frozen dataclass
> `Capability(area, subject, scope, ops)` with a `matches()` implementing the
> same subsumption rules (a grant of `rdf(resource)` subsumes `rdf(cls)`;
> `"CRUD"` subsumes `"R"`; an unbound scope subsumes any scope). Evaluation is
> a set-membership test over the user's resolved grant set, memoised per
> (user, project). The **client receives the resolved grant set as data** —
> not the engine — and evaluates the same `matches()` in ~40 lines of
> TypeScript. This removes VocBench's most awkward piece of duplication while
> keeping the expressiveness that makes it worth copying.

WebProtégé's model (53 flat `BuiltInCapability` constants such as
`CREATE_CLASS`, `EDIT_ONTOLOGY_ANNOTATIONS`, `REVERT_CHANGES`) is strictly
weaker — no CRUD algebra, no resource-role binding, no validate operation. Its
one advantage is **role inheritance** (`BuiltInRole(parentRole, actions...)`),
which VocBench lacks. Take both: VocBench's grammar, WebProtégé's inheritance.

### 2.2 The role → binding → project chain

```
User ──┬─ ProjectUserBinding(project, roles[], group, groupLimitations, languages[])
       └─ system roles
Role ──── capabilities[]  (+ parent roles)
Project ─ ACL: consumers[] × AccessLevel{R,RW,EXT}, LockLevel{R,W,NO}, universal level
```

Three details that are easy to miss and expensive to omit:

1. **`languages[]` on the binding.** This is what makes "this terminologist may
   edit only the French labels" enforceable rather than aspirational. The
   check happens at the *value* level in the resource view, not at the
   operation level.
2. **`groupLimitations` + `ProjectGroupBinding.ownedSchemes`.** A group owns a
   set of SKOS schemes; a limited member may only edit inside them. This is how
   a 40-editor thesaurus stays coherent.
3. **Project-to-project ACLs.** A project grants *other projects* access at
   `R` / `RW` / `EXT`. Cross-ontology alignment (mapping your ontology to FIBO)
   is a permission-by-delegation, not an ambient right. Without this,
   OB.MAP.\* has no security model.

### 2.3 Change tracking, staging graphs and validation

This is the mechanism that turns "multi-user editor" into "controlled
publication environment", and it is entirely expressible in named graphs.

VocBench: every write is intercepted at the triple level by an RDF4J SAIL
extension; additions and removals go to a **support repository** with
provenance; when the project has validation enabled, "previews" of them go to
**`staging-add-graph`** and **`staging-delete-graph`** in the main repository.

The main graph therefore always holds *stable* content and needs no status
flag. A concept whose `rdf:type skos:Concept` assertion is still in
staging-add *is* a proposed concept — the workflow is the graph layout, not a
property. A user holding **`V`** accepts (apply to main, keep in history) or
rejects (delete from staging, leave **no** history trace — "rejecting an
operation should be like the operation was never performed").

**On Fuseki this ports almost unchanged**, because Fuseki's native unit is the
named graph. What does *not* port is the SAIL hook: Fuseki has no interception
point. The change tracker must therefore be a **write-path invariant** rather
than a store feature — see §3.3.

### 2.4 Declarative service authorization

VocBench annotates each service method with the capability it needs, whether it
reads or writes, and its preconditions (§4.15 of the SWJ paper). Two
consequences worth reproducing:

* The **capability catalogue is derived from the endpoint registry**, so it can
  never drift from what the code actually enforces.
* A new service that forgets its annotation is *visible* — you can enumerate
  unguarded endpoints mechanically.

In Python this is a decorator plus a test:

```python
@guarded(capability="rdf(cls)", ops="C", writes=True)
async def create_class(...): ...
```

```python
def test_every_endpoint_is_guarded():
    unguarded = [r for r in app.routes if not getattr(r.endpoint, "_capability", None)]
    assert not unguarded, unguarded
```

That test failing the build is the difference between a governed platform and a
platform with a governance module.

---

## 3. The Fuseki realisation

### 3.1 Named-graph layout

One Fuseki/TDB2 dataset per environment. Per project `p`, a reserved IRI
namespace:

| Graph | Purpose | Written by |
|---|---|---|
| `urn:ob:p:{p}:main` | Stable, validated content | validation accept, or direct edit when validation is off |
| `urn:ob:p:{p}:staging-add` | Proposed additions | every edit under validation |
| `urn:ob:p:{p}:staging-del` | Proposed deletions | every edit under validation |
| `urn:ob:p:{p}:imports:{iri}` | Materialised import closure, one graph per imported ontology | import manager |
| `urn:ob:p:{p}:inferred` | Materialised entailments, with a freshness stamp | reasoner (OB.RSN.02) |
| `urn:ob:p:{p}:shapes` | SHACL shapes | shapes editor |
| `urn:ob:p:{p}:mappings` | Cross-ontology alignments | alignment editor (OB.MAP.06) |
| `urn:ob:p:{p}:metadata` | DCAT/VoID/ADMS dataset description | metadata editor |
| `urn:ob:gov:projects` | Project registry, settings, facets, ACLs | governance service |
| `urn:ob:gov:users` | Users, groups, roles, capabilities, bindings | governance service |
| `urn:ob:hist:{p}` | Commit provenance and triple deltas | change tracker |

Two consequences of this layout are worth stating plainly:

* **Governance is itself RDF** (VocBench's R15, "Everything's RDF"). Who may do
  what, and who changed what, is queryable with the same SPARQL as the content.
  This is deliberately chosen over WebProtégé's MongoDB: it makes the audit
  trail a first-class graph, versionable and exportable by the same machinery
  as the ontologies.
* **A read is a union.** Loading a resource under validation means reading
  `main ∪ staging-add ∖ staging-del`, tagging each triple with which graph it
  came from so the UI can render proposals distinctly (VocBench renders staged
  triples green and italic). This is a `GRAPH ?g` pattern plus a post-pass, not
  a special store mode.

### 3.2 The single-writer constraint

TDB2 is single-writer. The technical requirements catalogue
(`architecture/technical architecture/REQUIREMENTS_CATALOG.md`, `TR.SK.*`)
already records this. The Builder must therefore:

* serialise all writes for a dataset through **one coordinator process**
  (a write queue per dataset, not per project — TDB2's lock is dataset-wide);
* make every logical edit **one** SPARQL Update transaction containing the
  content delta *and* its provenance write, so history can never diverge from
  content;
* keep long operations (reasoning, bulk import, alignment runs) **off** the
  write path — they compute into a scratch graph and swap it in with a single
  short transaction.

This is the main architectural difference from VocBench, whose RDF4J/GraphDB
backends allow concurrent writers. It is not a limitation in practice at
ontology-editing write rates, but it must be designed for rather than
discovered.

### 3.3 The change-tracking invariant

Because Fuseki offers no interception point, the invariant is enforced in the
application:

> **No code path may write to the store except through `ChangeSet.apply()`.**

`ChangeSet` computes `(additions, removals)` against the current state, routes
them to `main` or to the staging graphs depending on project configuration,
writes the commit record to `urn:ob:hist:{p}`, and applies everything in one
transaction. The `sparql/executeUpdate` endpoint is not an exception — it
parses the update, executes it into a scratch graph, diffs, and feeds the
result through the same `ChangeSet`. That is precisely VocBench's R6+R9
requirement ("under-the-hood modification **while keeping a complete
history**") and it is the reason its history is trustworthy.

Enforcement, not documentation:

* the low-level `FusekiClient` write methods are private to
  `ontology_builder.changes`;
* a lint/test asserts no module outside that package imports them;
* `guard()` from the existing playground service — already live-verified against
  the 133k-triple dataset — runs before every apply, so a lossy projection can
  never overwrite content it never saw.

### 3.4 What we reuse, unchanged

| Existing asset | Role in the governance foundation |
|---|---|
| `ontology_modeler/fuseki.py` — `FusekiClient` | SPARQL + Graph Store protocol client |
| `ontology_modeler/diff.py` — `GraphSynchronizer` | Blank-node-aware delta application with isomorphism verification and PUT fallback |
| `ontology_modeler/playground/service.py` — `guard()` | Blocks illegal deletes; refuses to apply a change set that drops triples the editing surface never saw |
| `ontology_modeler/playground/merge.py`, `project.py` | Unified OWL+SKOS projection and safe merge write-back |
| `ontology_modeler/structure.py` — `StructureExplorer` | ~15 structural queries; the basis of hierarchy paging and quality metrics |
| `infra/fuseki/`, `deploy/fuseki/config-tdb2.ttl` | The dataset itself, plus the assembler where the Lucene text index for OB.SRCH.01 is declared |

The playground work is not a prototype to be replaced — it is the write-safety
core of the Builder, already verified end-to-end against a live Fuseki.

---

## 4. Default role set

Ship VocBench's eight roles, reconciled with WebProtégé's ladder. Roles are
data, not code; these are the seeds that a Project Manager then edits.

| Role | Level | Capability sketch |
|---|---|---|
| **Administrator** | system | everything, including `rbac(_,_) CRUD` and `pm(project,_) CRUD` |
| **Project Manager** | project | everything within the project: `pm(project,_) CRUD`, `rdf(_,_) CRUD`, `cform(_,_) CRUD`, user assignment |
| **Ontology Editor** | project | `rdf(cls…) CRUD`, `rdf(objectProperty…) CRUD`, `rdf(cls,taxonomy) CRUD` — axiom-level editing |
| **Thesaurus Editor** | project | `rdf(concept…) CRUD`, `rdf(conceptScheme…) CRUD`, `rdf(skosCollection…) CRUD`; **no** OWL axiom capabilities |
| **Lexicographer / Terminologist** | project | `rdf(%resource_role%, lexicalization) CRUD`, `rdf(xLabel) CRUD`; **language-restricted via the binding** |
| **Mapper** | project | `rdf(resource, alignment) CRUD` only |
| **Validator** | project | `rdf(_,_) RV` — read everything, validate everything, change nothing directly |
| **RDF Geek** | project | full `rdf` CRUD plus `customService` and `invokableReporter` — the SPARQL power user |
| **Lurker** | project | `rdf(_,_) R` |

Layered on top, WebProtégé's inheritance ladder for the *sharing* dimension
(OB.GOV.08): `CanView ⊂ CanComment ⊂ CanEdit ⊂ CanManage`. Sharing grants are
the low-ceremony path ("share this project with Anna as Editor"); roles are the
governed path. Both resolve into the same grant set at the PDP.

---

## 5. Agents are principals

The single most important consequence of building governance first: **the
agentic layer needs no separate trust model.**

* Each agent is a **machine account** (OB.GOV.12 — VocBench's `Machines`
  service, 9 operations) with its own project bindings and roles.
* An authoring agent gets editor capabilities **without `V`**. Its output
  therefore lands in `staging-add` and requires a human validator to accept.
  This is not a policy we invent for AI — it is the same workflow a junior
  terminologist is subject to.
* Every agent write is attributed to the machine account in the commit
  provenance (OB.CHG.02), so "which of these 4,000 axioms did the copilot
  propose, and who accepted them" is a SPARQL query.
* An agent that must never write (the Ontology Assistant, OB.AGT.02) gets a
  read-only account, and the read-only-ness is enforced by the PDP, not by
  reviewing the agent's prompt.

If governance were built after the agents, none of this would be available and
we would be inventing a bespoke approval mechanism for LLM output. Built first,
it is free.

---

## 6. Acceptance criteria for the foundation

P0 and P1 are done when all of these hold:

1. A project can be created, configured, opened, closed, shared and deleted
   through the typed API and the React UI, with its graphs materialised in
   Fuseki under the layout in §3.1.
2. `pytest` proves that **no** FastAPI route lacks a `@guarded` declaration.
3. The eight default roles exist as data; a Project Manager can create a ninth
   through the role editor without a deployment.
4. A user bound with `languages=["fr"]` is refused an English label edit by the
   server, *and* is not shown the control by the client — from the same grant
   set.
5. With validation enabled, an edit by an Ontology Editor appears in
   `staging-add`, is visible as *proposed* in the UI, and does not appear in an
   export of the main graph.
6. A Validator accepts it; it moves to `main`; the commit appears in history
   with actor, operation, parameters, timestamps and affected resources.
7. A Validator rejects a second edit; it vanishes from staging and leaves **no**
   history entry.
8. A raw `SPARQL UPDATE` issued through the console produces a history entry
   with the correct triple delta — proving the invariant in §3.3.
9. Killing the coordinator mid-write leaves the dataset consistent: either the
   content delta and its provenance are both present, or neither is.
10. A restore from backup reproduces content, governance and history together,
    because they are graphs in the same dataset.

Criteria 5–8 are the ones that distinguish this from a CRUD app over a
triplestore. They should be automated tests, not a demo script.
