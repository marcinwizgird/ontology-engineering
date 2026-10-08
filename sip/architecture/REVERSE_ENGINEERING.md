# Reverse engineering Protégé and VocBench 3 — synthesis and translation map

This document records what was read, what each tool's architecture actually is, and how
every mechanism was translated into the Python package
[`sip/semantic_intelligence`](../semantic_intelligence).
The source-level notes behind it, about 4,200 lines with file paths and pseudo-code, are in
[`reverse_engineering/`](reverse_engineering/):

| Notes | Scope |
|---|---|
| [`protege_core.md`](reverse_engineering/protege_core.md) | Model manager, imports/catalog, change & undo, hierarchy providers, rendering, finder/search, Manchester parsing and autocomplete, entity creation, metrics, frames, workspace |
| [`protege_reasoning_refactoring.md`](reverse_engineering/protege_reasoning_refactoring.md) | Reasoner manager and status, inferred hierarchies, explanation (incl. the owlexplanation algorithm), every refactoring action, usage/delete, the 24 extension points, import/export |
| [`st_governance.md`](reverse_engineering/st_governance.md) | Change-tracking SAIL, history, validation, undo, blacklist, projects/ACL/locks, users/roles/capabilities, the authorization algorithm, settings scopes, URI generation, metadata registry, service inventory |
| [`st_content.md`](reverse_engineering/st_content.md) | Resource view, SKOS/SKOS-XL/OntoLex, classes/properties/individuals, Refactor, ICV (all checks and fixes), Search, import/export pipeline, alignment, custom forms, SPARQL, the VocBench client |

---

## 1. Sources

| Tool | Obtained from | Version | Size |
|---|---|---|---|
| Protégé Desktop | `github.com/protegeproject/protege` (shallow clone) | commit `bf03ccc`, built on OWL API 4.5.29 | 1,908 files |
| VocBench 3 client (Angular) | `bitbucket.org/art-uniroma2/vocbench3` (public) | `HEAD` of 2026-10-04 | 1,589 files |
| Semantic Turkey server (Java) | **Maven Central source jars**, group `it.uniroma2.art.semanticturkey` | 15.1.3 | `st-core-framework` (892 Java files), `st-core-services` (255), `st-changetracking-sail` (25), `st-metadata-registry-core` (43), `st-metadata-registry-services` (80), plus 14 extension jars (search strategies, RDF transformers, lifter, exporter, loaders, deployers, URI generators, CODA converters) |

**The Semantic Turkey route matters.** The earlier Ontology Builder design (2026-08-31)
recorded that the server repository `bitbucket.org/art-uniroma2/semanticturkey` asks for
credentials, so its contract had to be recovered from the client alone. That is still
true of the git repository. However, every Semantic Turkey module is published to Maven
Central **with a `-sources.jar`**, so this time the server code itself was read. Several
findings below (the nine roles verbatim, the three-step commit, per-fix ICV
capabilities, the SPARQL guards) could not have been recovered from the client.

The OWL API and owlexplanation are not in the Protégé repository. Where Protégé delegates
to them (axiom model, renaming, justifications), the behaviour was ported from their
documented algorithms, and the notes say which parts were read and which were not.

---

## 2. What the two tools are, architecturally

### 2.1 Protégé Desktop: an axiom editor on top of an OSGi plugin platform

```
OWLEditorKit ── OWLModelManagerImpl ── OWLOntologyManager (OWL API)
                 ├─ HistoryManagerImpl        undo/redo of change lists
                 ├─ OntologyCatalogManager    XML catalogs, import resolution
                 ├─ OWLHierarchyManager       asserted/inferred providers (lazy)
                 ├─ OWLEntityRenderer + rendering cache (name → entity index)
                 ├─ OWLReasonerManagerImpl    one reasoner per active ontology
                 └─ listeners: OWLModelManagerListener (11 event types)
OWLWorkspace ── 7 tabs · 51 views · 127 menu actions · 24 extension points (221 contributions)
```

* **The unit of editing is the axiom.** Views never touch RDF. They build `OWLAxiom`s
  and call `applyChanges([AddAxiom, RemoveAxiom…])`. Each batch is minimised (an add and
  a remove of the same axiom cancel) and becomes one undo entry.
* **Rendering and parsing are coupled.** Manchester expressions are parsed by
  *displayed name*. The renderer and the name→entity index rebuild together on every
  change, so a label can be typed back in.
* **Autocompletion is driven by parse errors.** The text up to the caret is parsed, and
  the `ParserException` lists the expected keywords and the entity kinds that may come
  next.
* **Reasoning is orchestration only.** The repository's only bundled reasoner is "None".
  The status is *derived* on every call (six states) and never stored.
* **Extensibility is OSGi.** Tabs, views, reasoners, renderers, explanation services
  and menu actions are all extension points.

### 2.2 VocBench 3 / Semantic Turkey: governed, triple-level, multi-user

```
Angular client (61 service wrappers, jsprolog for client-side permission checks)
        │ REST
Semantic Turkey (Spring, 69 service classes, 995 @STServiceOperation methods)
  ├─ @PreAuthorize("@auth.isAuthorized('rdf(concept)', 'C')") on every operation
  ├─ STAuthorizationEvaluator → tuProlog over roles/*.pl  (9 predefined roles)
  ├─ ChangeTrackerSail (RDF4J) intercepts every write ──► support repo: history, validation
  ├─ validation: staging-add-graph/<g>, staging-remove-graph/<g> in the data repo
  ├─ settings: sys / proj / usr / pu / pg scopes, layered merge
  └─ extension points: URI generators, search strategies, loaders, lifters,
     transformers, exporters, deployers, collaboration backends, rendering engines
```

* **The unit of editing is the triple.** The SAIL records the *effective* delta of each
  transaction as a `cl:Commit` with `cl:Quadruple`s. The commit protocol has three steps:
  write the record with no status, commit the data (deleting the record if that fails),
  then mark the record `committed`.
* **The workflow lives in the graph layout.** A triple in `staging-add-graph` *is* a
  proposal. Accepting applies it; rejecting erases it and leaves no history trace.
* **Authorization is declarative.** It is a capability term plus CRUDV letters per
  operation, a role per project binding, and languages on the binding.
* **Everything is RDF**, including history and metadata.

### 2.3 What neither has

Neither tool has competency questions as executable tests, an end-to-end lifecycle, or
agents. Both have pieces of the "safe agent" story without having agents:
* VocBench has machine accounts and a validation queue.
* Protégé has explanations, so a repair can be justified.

The Semantic Intelligence Platform adds the agent layer *on top of* those two
mechanisms instead of beside them.

---

## 3. Translation map

Fidelity is one of three values:
* **faithful**: same semantics, and tests pin them;
* **adapted**: same intent, with the mechanism changed for Python, Fuseki or safety, and the reason stated;
* **new**: no counterpart in either tool.

### 3.1 Protégé → Python

| Protégé / OWL API | Python | Fidelity | Notes |
|---|---|---|---|
| `OWLAxiom`, `OWLClassExpression` (OWL API structural model) | `owl/model.py`: `Axiom`, `And/Or/Not/Some/Only/HasValue/HasSelf/Card/OneOf`, data ranges | adapted | RDF stays canonical, and the axiom view is derived using the OWL 2 *Mapping to RDF* reverse mapping. Symmetric axioms are sets, as in the OWL API. Measured on FIBO: 3,090/3,090 anonymous class expressions read |
| `AddAxiom`/`RemoveAxiom` | `axiom_triples(ax)` (add, fresh bnodes) / `axiom_triples(ax, graph)` (remove, exact incl. blank-node closure) | adapted | Removal is found by structural comparison, because blank-node labels are arbitrary |
| `HistoryManagerImpl` undo/redo | `core/changes.py` `ChangeTracker.undo/redo` | adapted | Per principal, and each undo/redo is itself a commit. Protégé's stacks are in-memory and lost on restart |
| change-list minimisation | `ChangeTracker._effective` | faithful | Add+remove cancel. Only effective changes are recorded (the SAIL does the same) |
| `ManchesterOWLSyntaxParser` + `OWLExpressionChecker` | `owl/manchester.py` `parse`, `check`, `ManchesterError(expected=…)` | adapted | Recursive descent over the W3C Note grammar (class expressions, data ranges with facets, `inverse`, `Self`, qualified cardinalities, `that`). The error carries the expected keywords and entity kinds at the *furthest* failure point |
| `AutoCompleter` | `manchester.complete` | faithful | Parse up to the caret, read the expected set, offer keywords then entities |
| `ManchesterOWLSyntaxObjectRenderer` | `manchester.render` | adapted | Precedence-aware. **Lossless:** an ambiguous label is rendered as its prefixed name or IRI (see §4) |
| `OWLEntityAnnotationValueRenderer` / prefix / fragment renderers | `owl/rendering.py` `ShortFormProvider(mode=label\|prefixed\|fragment)` | faithful | The annotation-property order wins over language order. The quoting rules are the same |
| `OWLEntityFinder` | `ShortFormProvider.resolve/find` | adapted | Undeclared entities are typed from usage, as the OWL API's lax RDF consumer does |
| `AssertedClassHierarchyProvider` | `owl/hierarchy.py` `ClassHierarchy` | faithful | Named conjuncts of equivalent intersections are parents. Equivalents are not each other's parents. Thing roots, cycle-tolerant, `paths_to_root` |
| Object/data/annotation property hierarchy providers | `PropertyHierarchy` | faithful | |
| `InferredOWLClassHierarchyProvider` | `reasoning/reasoner.py` `InferredClassHierarchy` | faithful | Transitive reduction. Unsatisfiable classes go under `owl:Nothing` |
| `OWLClassDescriptionFrame` (8 sections) / property frames | `owl/frames.py` `class_frame`, `property_frame` | faithful | Inferred ("yellow") rows when a classification exists |
| `EntityCreationPreferences`, `CustomOWLEntityFactory` | `governance/urigen.py` `EntityCreationPreferences` | adapted | Name-as-fragment or auto-ID (UUID / iterative). The iterative generator **raises** on overflow; Protégé silently truncates |
| `MetricsPanel` (43 metrics, 6 tables) | `quality/metrics.py` | faithful | Plus a DL-expressivity *hint* (Protégé's is commented out) |
| `OWLReasonerManagerImpl`, `ReasonerStatus` (6 states, derived) | `ReasonerManager.status` | faithful | "Out of sync" compares the classified revision with the tracker revision |
| Reasoner plugins (HermiT, ELK, …) | `Backend` protocol: `OwlRlBackend`, `RdfsBackend`, `HermitBackend` (only if a JVM is present) | adapted | Pure Python RL/RDFS by default. **Every result carries its profile** |
| Unsatisfiable classes | `ReasonerManager._unsatisfiable` | adapted | Canary individuals under RL: one closure for all classes, then one per candidate |
| `ExplanationManager` + owlexplanation | `reasoning/explanation.py` | faithful (algorithm) | Module → expand-contract → Reiter hitting-set tree with justification reuse and early termination. The oracle is RL, and the result says so |
| `OWLEntityRenamer.changeIRI(IRI,IRI)` | `owl/refactor.py` `rename_iri` | faithful | Pun-wide. Renaming onto an existing IRI merges |
| `MergeEntitiesChangeListGenerator` | `merge_entities` | adapted | Source labels become `skos:altLabel`. The target's identical label is **kept** (Protégé drops it) |
| `OWLEntityDeleter` / `ReferenceFinder` | `delete_entities` | faithful + | Whole axioms are removed, and so are annotations as subject or value. **No orphan blank-node structures**, an invariant the OWL API gets for free and RDF does not |
| Convert to defined / primitive, make primitive siblings disjoint, covering axiom, create closure axiom, split/amalgamate subclass axioms, split disjoint classes, move/copy/delete axioms, deprecate | `refactor.*` | faithful | Amalgamation is deterministic (Protégé's depends on HashSet order) |
| Change ontology IRI cascade | `replace_base_uri` | adapted | Moves an IRI only at a namespace boundary (Protégé used raw `startsWith`) |
| OSGi extension points | registries: `OPERATIONS`, `icv.REGISTRY`, `TRANSFORMERS`, `ReasonerManager.backends`, agents | adapted | Pythonic registries. Entry-point discovery is the next step |
| 7 tabs / 51 views | operations in the `browse.*`, `owl.*`, `refactor.*`, `reasoning.*` families + perspectives (QR-USA-01) | adapted | The UI is a client of the operation API, not part of the core |

### 3.2 VocBench 3 / Semantic Turkey → Python

| Semantic Turkey / VocBench | Python | Fidelity | Notes |
|---|---|---|---|
| `ChangeTrackerConnection` (SAIL interception) | `core/store.py` (one write method) + `core/changes.py` `ChangeTracker._write` | adapted | Fuseki has no interception point, so the store has a single `apply` and only the tracker calls it. `tests/test_architecture.py` enforces this |
| `CHANGELOG` vocabulary (`cl:Commit`, `cl:Quadruple`, `cl:addedStatement`, …) | `core/namespaces.py` `CL`, `_commit_quads` | faithful | Same namespace and terms. Content and history are written in **one** request (ST uses three steps over two repositories) |
| Validation: `staging-add-graph/`, `staging-remove-graph/` | `ProjectLayout.staging_add/staging_del`, `commit(stage)`, `accept`, `reject` | faithful + | Reject erases the commit (ST semantics). Accept **detects conflicts**: a staged removal whose triple has already gone is refused |
| Machine accounts | `Principal(is_machine=True, on_behalf_of=…)` | adapted | A machine **must** name a human. Machine writes are **always** staged, and machines can never exercise `V` |
| `Undo` (author's last change) | `ChangeTracker.undo` | adapted | ST deletes the tip commit; here an undo is an inverse commit, so history stays append-only |
| `roles/*.pl` (9 roles) | `governance/capabilities.py` `DEFAULT_ROLES` | **faithful, verbatim** | Visitor, lurker, validator, lexicographer, mapper, thesaurus-editor, ontologist, rdfgeek, projectmanager, plus five SIP agent roles without `V` |
| Prolog capability rules (tuProlog / jsprolog) | `CapabilitySet.satisfies` | faithful | No Prolog: one predicate per clause, wildcard unification, the `rdf(sparql,support)` cut. Promoted from the 52-test `spike_crudv` |
| `STAuthorizationEvaluator.isAuthorized` | `governance/registry.py` `PolicyDecisionPoint.authorize` | faithful + | ACL → read-only → admin → **machine-V strip** → roles → languages (binding ∩ project) → `rdf(graph)` U for writes outside main |
| `ProjectACL`, `AccessLevel R/RW/EXT`, `LockLevel W/R/NO` | `ProjectACL`, `resolve_accessibility`, `resolve_locking` | faithful | |
| `@PreAuthorize` on 755 operations | `@operation(capability=…, crudv=…)`, 66 operations | adapted | The capability catalogue is data. An operation without one fails the build (QR-SEC-01) |
| `SPARQL.executeUpdate` = `rdf(sparql)` U, `evaluateQuery` = `rdf(sparql, core)` R | `sparql.update`, `sparql.query` | faithful | The update runs on a scratch copy, is diffed, and is committed as a change set, so even SPARQL Update is in the history |
| `STPropertiesManager` scopes sys/proj/usr/pu/pg | `governance/settings.py` | faithful | Merge order: system default → user default → project default → group → PU |
| `NativeTemplateBasedURIGenerator` + CODA `randIdGen` | `TemplateURIGenerator` | faithful | `c_${rand()}`, `xl_${lexicalForm.language}_${rand()}`, the 8 random codes, `${}` escaping vs `$${}` raw, 5 attempts |
| `SKOS` service (43 ops) | `skos/skos.py` `SkosService` | faithful | Hierarchy path = broader ∪ ^narrower + sub-properties, excluding broadMatch/narrowMatch. Top concepts with a scheme are **declared** ones. Label clash checks, prefLabel demotion, `deleteConcept` refuses while narrowers exist |
| `SKOSXL` service + `Refactor.SKOStoSKOSXL/SKOSXLtoSKOS` | `SkosService` (lexicalization `skosxl`), `to_skosxl`, `to_skos` | faithful | |
| `ResourceView` (29 sections, 17 role templates, tripleScope) | `owl/frames.py` `resource_view` | faithful | Each statement is consumed once. Sub-properties are followed. Scope is local / staged / del_staged / imported / inferred |
| `ICV` (27 checks, 11 fixes) | `quality/icv.py` (23 ported checks, 6 of the 11 fixes, + 5 logical checks; fixes are change sets) | faithful + | **Per-fix capabilities** as in ST (`rdf(concept, taxonomy)` C …). Not ported: GraphDB-only rule checks (replaced by the reasoner), and HTTP-based broken-alignment checks |
| `Search.searchResource` (regex strategy) | `search/search.py` | faithful | Same modes. Fuzzy is the ST one-edit neighbourhood (substitution or one extra char, **no deletion**) |
| `Alignment` service, `AlignmentUtils.suggestPropertiesForRelation` | `alignment/alignment.py` | faithful | The relation × role → property table verbatim. Reversal. `applyValidation` writes to the **mappings** graph |
| MAPLE / remote matchers | `lexical_match` + `AlignmentAgent` | adapted | A local lexical matcher plus agent adjudication. The remote MAPLE API remains an extension point |
| Loader → lifter → transformer → exporter → deployer; 8 RDF transformers | `io/pipeline.py` `TRANSFORMERS` (8), `run_pipeline`, `export` | faithful | Transformers run on a working copy, never on the project |
| Sheet2RDF / CODA PEARL | `kg/lifting.py` `TableMapping` | adapted | A column→property mapping with IRI templates and lexical validation, without the PEARL language |
| Custom forms (PEARL), OntoLex (46 ops), metadata registry (53 ops), collaboration (Jira) | — | not yet | Explicitly later. See ARCHITECTURE_DESCRIPTION §9 |

---

## 4. Defects found in the sources, and not reproduced

| Tool | Defect (from the notes) | Port behaviour |
|---|---|---|
| Protégé | Renaming an ontology IRI cascades by raw string prefix (`http://x/onto` also catches `http://x/ontology#A`) | Namespace-boundary match |
| Protégé | Merging entities removes the target's own label when it is identical to a source label | Target label kept |
| Protégé | Amalgamate disjoint classes depends on HashSet iteration order | Deterministic |
| Protégé | Iterative ID generator truncates digits over the configured width | Raises |
| Protégé | An ambiguous rendered name resolves to the most-used entity, so an edited axiom can silently change meaning | Ambiguous names are rendered prefixed or as an IRI, which makes rendering lossless |
| Protégé | Whole-word search regex malformed (`(:?` for `(?:`) | Not applicable (ST search modes ported) |
| Protégé | Deprecation never removes HasKey / DisjointUnion axioms | All logical axioms referencing the entity are removed |
| Semantic Turkey | `replaceBaseURI` never moves the working graph (TODO in source) | Not applicable (graph IRIs are layout-managed) |
| Semantic Turkey | Removing an intersection/union list leaves nested blank nodes behind | `delete_entities` removes the owning structure, and a test asserts no orphan bnodes |
| Semantic Turkey | `getInverseOfHierachicalProp` takes only the first `owl:inverseOf` | All sub-properties of broader/narrower are followed |

---

## 5. Measured on real data

The local FIBO checkout: 290 files, 131,893 triples. These numbers are pinned by
`tests/test_corpus_fibo.py`.

| Measure | Result |
|---|---|
| Axiom view | 90,976 axioms extracted in 0.4 s |
| Anonymous class expressions read | 3,090 / 3,090 |
| Manchester render → parse identity, all anonymous superclass expressions | **3,050 / 3,062 (99.6 %)** |
| Class hierarchy | 3,073 classes, 189 roots, 0 cycles |

The 0.4 % residue comes from FIBO using OMG Commons terms whose declarations are not in
the local checkout. Without them, a filler such as `CombinedDateTime` cannot be told
apart as a class or a datatype. Protégé would refuse these too, because its parser needs
declared entities.

Two improvements came directly out of this probe:
* lax typing of undeclared entities;
* the lossless ambiguous-name rendering.

It also caught a defect in the axiom view: a restriction with an `xsd:` filler on an
undeclared property was read as an object restriction.
