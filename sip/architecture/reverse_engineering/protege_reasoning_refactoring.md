> **Working notes — source-level reverse engineering.** Produced on 2026-10-04 by reading the source checkouts listed in [`../REVERSE_ENGINEERING.md`](../REVERSE_ENGINEERING.md) §1. Paths are relative to those checkouts. These notes are evidence for the port, not normative design; where the port deliberately deviates, `REVERSE_ENGINEERING.md` says so.

# Protégé Desktop: reverse engineering of reasoning, explanation, refactoring, usage/delete, extension architecture and import/export

Source: `refs/protege` (HEAD `bf03cccc`, 1,499 `.java` files). Target: a Python port built on rdflib and owlrl.

**Path abbreviations** (all relative to the repo root):
- `OWL/` = `protege-editor-owl/src/main/java/org/protege/editor/owl/`
- `CORE/` = `protege-editor-core/src/main/java/org/protege/editor/core/`
- `OWL-PX` = `protege-editor-owl/src/main/resources/plugin.xml`
- `CORE-PX` = `protege-editor-core/src/main/resources/plugin.xml`

**Key framing.** Protégé contains no reasoner of its own and no justification algorithm of its own. Three kinds of logic live outside the repo:
- the reasoners (HermiT, ELK and others, installed as plugins);
- the explanation workbench, i.e. owlexplanation;
- the OWLAPI utilities: `OWLEntityRenamer`, `OWLEntityURIConverter`, `InferredOntologyGenerator` and `Inferred*AxiomGenerator`, `SplitSubClassAxioms`, `AmalgamateSubClassAxioms`, `CoerceConstantsIntoDataPropertyRange`, `OWLObjectDuplicator`, `OWLProfile`.

The repo holds the *orchestration*: the state machine, preferences, change-list generators, UI wiring and plugin points. Where the semantics come from the OWLAPI, this report says so and gives the behaviour you need to port it.

**Storage model assumed for the Python port.** Each ontology is an rdflib `Graph`, or a named graph in a `Dataset`. An "axiom view" (`AxiomIndex`) parses triples into frozen dataclass axioms (`SubClassOf(sub, sup)`, `EquivalentClasses(frozenset)` and so on) and serialises them back. Every refactoring below is written as a **change list** `[AddAxiom(ont, ax) | RemoveAxiom(ont, ax) | AddImport | RemoveImport | AddOntologyAnnotation | RemoveOntologyAnnotation | SetOntologyID]`. A single `ModelManager.apply_changes(changes)` translates the list to triple adds and removes, records it for undo (the history agent's scope), and fires change events. **Invariant kept throughout Protégé: refactorings never mutate directly. They always build a full change list first and then apply it in one batch (one undo unit).**

---

## 0. Counts (from source)

| Item | Count | Source |
|---|---|---|
| Declared extension points | **24** (core 12, owl 12) | `<extension-point>` in CORE-PX and OWL-PX |
| Of those, declared without a schema | `io_listener`, `repository`, `ExtraReasonerMenuAction` (loaded only in `OWL/model/OWLWorkspace.java`), `searchmanager`; and no `.exsd` schema files are shipped at all | |
| `<extension>` contributions | **221** (core 30, owl 191) | |
| `EditorKitMenuAction` contributions | 127 (core 25, owl 102) | |
| `ViewComponent` contributions | 51 | OWL-PX |
| `WorkspaceTab` contributions | 7 | OWL-PX |
| Refactor-menu items (`org.protege.editor.owl.menu.Refactor/…`) | 13 | OWL-PX |
| Reasoner states (`ReasonerStatus`) | 6 | |
| `OptionalInferenceTask` (displayed-inference toggles) | 19 | `ReasonerPreferences` |
| Inferred axiom generators offered in "Export inferred axioms" | 12 (6 on by default) | `ExportInferredOntologyPanel` |
| Frame sections that override `refillInferred()` | 20 (plus the base class) | `OWL/ui/frame/**` |
| Move-axioms kits | 4 | OWL-PX `moveaxiomskit` |
| Save formats offered | 8 in the combo box, plus N-Triples by extension only | `OWL/ui/OntologyFormatPanel.java`, `OWL/ui/Extensions.java` |
| Bundled reasoners in the repo | 1 ("None" = `NoOpReasonerInfo`) | OWL-PX |
| Bundled explanation services in the repo | 0 (only the plugin point) | |

---

## 1. Reasoning integration

### 1.1 Classes

| Class | Role |
|---|---|
| `OWL/model/inference/OWLReasonerManager.java` (interface) | `getCurrentReasoner()`, `getReasonerStatus()`, `classifyAsynchronously(Set<InferenceType>)`, `killCurrentReasoner()`, `killCurrentClassification()`, `setCurrentReasonerFactoryId(id)`, `getInstalledReasonerFactories()`, `getReasonerPreferences()`, `addReasonerFilter(ReasonerFilter)` |
| `OWL/model/inference/OWLReasonerManagerImpl.java` | The implementation. Holds a **`Map<OWLOntology, OWLReasoner> reasonerMap`**, so there is one reasoner per *active (root) ontology*. Also holds a `runningReasoner`, the flag `classificationInProgress`, and a non-buffering change listener |
| `ProtegeOWLReasonerInfo` / `AbstractProtegeOWLReasonerInfo` | Plugin instance. Provides `getReasonerFactory()`, `getRecommendedBuffering()` (BUFFERING or NON_BUFFERING), `getConfiguration(monitor)` (default `SimpleConfiguration(monitor)`), and `setup(manager,id,name)` |
| `ProtegeOWLReasonerPlugin`, `…PluginJPFImpl`, `…PluginLoader` | Load the extension point `org.protege.editor.owl.inference_reasonerfactory`. The plugin param `name` gives the display name, and the extension unique id gives the reasoner id |
| `NoOpReasoner`, `NoOpReasonerFactory`, `NoOpReasonerInfo` | Null object: id `org.protege.editor.owl.NoOpReasoner`, display name "None", NON_BUFFERING. It is consistent, every class is satisfiable, equivalents are `{self}`, and all node sets are empty |
| `ReasonerStatus.java` | Enum of 6 states, each with `isEnableInitialization/Synchronization/Stop` and tooltips |
| `ReasonerPreferences`, `PrecomputedInferencePreferences`, `DisplayedInferencePreferences` | Preferences (§1.4) |
| `ReasonerUtilities.java` | `createReasoner(ont, info, monitor)` switches on buffering. `warnUserIfReasonerIsNotConfigured` holds the status-specific messages |
| `VacuousAxiomVisitor.java` | Filters out trivial inferred axioms (§1.7) |
| `ReasonerFilter` | `OWLOntology getFilteredOntology(OWLOntology)`. Applied to the root ontology before the reasoner is created. There are **no in-repo callers**; it is a plugin hook. Filters are cleared after each run |
| `DefaultOWLReasonerExceptionHandler`, `OWL/model/UIReasonerExceptionHandler.java` | `UIReasonerExceptionHandler` shows the root-cause class name and message |
| `ReasonerDiedException` | Thrown by `getReasonerStatus()` if the reasoner itself throws. The manager kills the reasoner first |
| UI: `OWL/ui/inference/PrecomputeAction.java` (used for both "Start reasoner" and "Synchronize reasoner"), `StopReasonerAction`, `ExplainInconsistentOntologyAction`, `ConfigureReasonerAction`, `ReasonerProgressUI`, `PrecomputePreferencesPanel`, `DisplayedInferencesPreferencePanel` | |
| Menu assembly: `OWL/model/OWLWorkspace.java#rebuildReasonerMenu` | Builds: Start / Synchronize / Stop / Explain inconsistent ontology / Configure… / [ExtraReasonerMenuAction plugins] / one radio item per reasoner, sorted by `ReasonerInfoComparator`. A registry listener adds reasoners hot-plugged at runtime |

### 1.2 ReasonerStatus state machine

| State | Init enabled | Sync enabled | Stop enabled | Status-bar text |
|---|---|---|---|---|
| NO_REASONER_FACTORY_CHOSEN | no | no | no | "No Reasoner set…" |
| REASONER_NOT_INITIALIZED | **yes** | no | no | "To use the reasoner click Reasoner > Start reasoner" |
| INITIALIZATION_IN_PROGRESS | no | no | no | "Reasoner Initialization in Progress" |
| INITIALIZED | no | no | yes | "Reasoner active" |
| INCONSISTENT | no | no | yes | "Reasoner active but the ontology is inconsistent" |
| OUT_OF_SYNC | no | **yes** | yes | "Reasoner state out of sync with active ontology" |

The state is **derived**, never stored (`OWLReasonerManagerImpl.getReasonerStatus`):

```
def get_status():
  with lock:
    if classification_in_progress: return INITIALIZATION_IN_PROGRESS
    if current_info.factory is NoOpFactory: return NO_REASONER_FACTORY_CHOSEN
    r = get_current_reasoner()           # creates a NoOpReasoner for the active ontology if absent
    try:
      if r is NoOp: return REASONER_NOT_INITIALIZED
      if not r.is_consistent(): return INCONSISTENT
      return INITIALIZED if not r.pending_changes() else OUT_OF_SYNC
    except Exception as t:
      kill_current_reasoner(); raise ReasonerDied(t)
```

The UI overlays one extra rule (`OWLWorkspace.updateReasonerStatus(changesInProgress)`):
- If the ontology changed (any `ImportChange` or `OWLAxiomChange`, including annotation axioms), and the status is INITIALIZED or INCONSISTENT, and the reasoner's buffering mode is BUFFERING, then the **display** shows OUT_OF_SYNC.
- "Explain inconsistent ontology" is enabled only when the status is INCONSISTENT.
- Ctrl/Cmd+R is bound to whichever of Start or Synchronize is enabled.

**Events fired** (`OWLModelManager.fireEvent`): `ABOUT_TO_CLASSIFY`, `ONTOLOGY_CLASSIFIED`, `REASONER_CHANGED`. Inferred hierarchy providers listen for `REASONER_CHANGED`, `ACTIVE_ONTOLOGY_CHANGED`, `ONTOLOGY_CLASSIFIED` and `ONTOLOGY_RELOADED`, and respond with `fireHierarchyChanged()`. `PrecomputeAction` listens for `ONTOLOGY_CLASSIFIED` and brings the views `InferredOWLClassHierarchy` and `OWLInferredSuperClassHierarchy` to the front.

### 1.3 Classify / synchronise algorithm (`classifyAsynchronously` + `ClassificationRunner`)

```
def classify_async(precompute: set[InferenceType]) -> bool:
  if current_info is NoOpInfo: return True                      # no-op
  ont = model.active_ontology
  with lock:
    if classification_in_progress: return False                 # UI offers "Interrupt Current Reasoning Task"
    running = reasoner_map.get(ont)
    reasoner_map[ont] = NoOpReasoner(ont)                       # views see "nothing" during the run
    classification_in_progress = True
  fire(ABOUT_TO_CLASSIFY)
  Thread(run, args=(ont, precompute, current_info)).start()     # uncaught -> exception_handler unless status==NOT_INITIALIZED
  return True

def run(ont, precompute, info):
  inconsistent = changed = False
  try:
    # ensure_running_reasoner_initialized
    if running is NoOp: running = None
    if running and running.pending_changes():
        if running.buffering in (None, NON_BUFFERING): running.dispose(); running = None
        else: running.flush()                                  # BUFFERING: incremental sync
    if running is None:
        running = info.factory.create(apply_filters(ont), buffering=info.recommended_buffering, monitor)
        changed = True
    if running:
        todo = precompute & running.precomputable_types()
        if todo: running.precompute_inferences(todo)
  except ReasonerInterrupted:
    changed = True; bad = running; running = None; bad.dispose()   # result: REASONER_NOT_INITIALIZED
  except InconsistentOntology:
    inconsistent = True
  finally:
    reasoner_filters.clear()
    with lock: reasoner_map[ont] = running; running = None; classification_in_progress = False
    if changed: later(fire, REASONER_CHANGED)
    fire_on_ui(ONTOLOGY_CLASSIFIED)
    if inconsistent: InconsistentOntologyManager.explain()     # pops the "Help for inconsistent ontologies" dialog
    monitor.reset()
```

Notes:
- **"Start reasoner" and "Synchronize reasoner" are the same action** (`PrecomputeAction`). Which one is enabled depends only on the status. Synchronize on a BUFFERING reasoner calls `flush()`. On a NON_BUFFERING reasoner with pending changes, it disposes the reasoner and creates a new one.
- **Non-buffering listener** (`nonBufferingOntologyChangeListener`). It acts only when the reasoner is not a NoOp and its mode is NON_BUFFERING. A change counts as relevant unless one of these holds:
  - it is an `AnnotationChange` (ontology annotation);
  - it is a `SetOntologyID`;
  - it is an axiom change whose axiom is non-logical;
  - its ontology is not in the active ontology's imports closure.

  On the first relevant change it schedules `fire(ONTOLOGY_CLASSIFIED)` on the UI thread, but only if the status is still INITIALIZED. The non-buffering reasoner is assumed to have applied the change itself.
- **Stop reasoner** (`StopReasonerAction`) calls `killCurrentReasoner()`. That disposes the reasoner and sets the map entry to `None`, so the next `get_current_reasoner()` creates a NoOp. It then fires `REASONER_CHANGED`.
- **Interrupt** (`killCurrentClassification`) calls `runningReasoner.interrupt()`. The reasoner must throw `ReasonerInterruptedException`.
- **Switching reasoner** (`setCurrentReasonerFactoryId`):
  - if the id equals the current one, return;
  - persist `DEFAULT_REASONER_ID`, **dispose all reasoners in the map**, set the new info, and fire `REASONER_CHANGED`;
  - if the id is unknown, persist the NoOp id.
- **Per-ontology map.** Changing the active ontology shows that ontology's reasoner state. A reasoner started for ontology A remains when you switch to B and back.

**Python translation** (`sip.reasoning`):
```
class ReasonerStatus(Enum): ...  # 6 members with enable_init/enable_sync/enable_stop properties
class ReasonerInfo(Protocol): id; name; recommended_buffering: Literal["buffering","non_buffering"]; create(graph_view, monitor) -> Reasoner
class Reasoner(Protocol):
    root: OntologyRef; buffering; pending_changes() -> list[Change]; flush(); interrupt(); dispose()
    precomputable_types() -> set[InferenceType]; precompute(types)
    is_consistent(); is_satisfiable(ce); unsatisfiable_classes() -> Node
    sub_classes(c, direct) -> NodeSet; super_classes(c, direct); equivalent_classes(c)
    instances(c, direct); types(i, direct); object_property_values(i,p); data_property_values(i,p)
    sub/super/equivalent/inverse_object_properties; sub/super/equivalent_data_properties; disjoint_classes(c)
    same_individuals(i); is_entailed(axiom)
class NoOpReasoner(Reasoner)
class OwlRlReasoner(Reasoner):      # owlrl.DeductiveClosure(OWLRL_Semantics) on a copy of the imports-closure graph
class RdfsReasoner(Reasoner):       # owlrl RDFS_Semantics
class ReasonerManager:              # reasoner_map: dict[ont_iri, Reasoner|None]; classify_async(types) using concurrent.futures
```

Implementation hints for `OwlRlReasoner`:
1. Take a buffering snapshot: copy the union graph of the imports closure, then run `DeductiveClosure(OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g)`.
2. Record pending changes by subscribing to `ModelManager` change events after the snapshot. `flush()` re-expands; owlrl is not incremental, so this is a full recompute.
3. `sub_classes(c, direct)`:
   - read `rdfs:subClassOf` from the closure;
   - compute equivalence nodes as the strongly connected components of the subClassOf graph, plus `owl:equivalentClass`;
   - direct = transitive reduction over the node DAG.
4. Unsatisfiable classes in OWL RL: any class C with `C rdfs:subClassOf owl:Nothing` in the closure, or C disjoint with a superclass of itself. owlrl does not infer `owl:Nothing` subsumption in all cases. Add your own check: a class is unsatisfiable if it has two superclasses D1 and D2 with `D1 owl:disjointWith D2`, or if it has `owl:complementOf` its own superclass.
5. Inconsistency: owlrl reports clashes (for example an individual in two disjoint classes, or a `differentFrom`/`sameAs` clash) as error triples added to the graph. **Verify the exact error namespace and predicate in the installed owlrl version.** Treat any such triple as `is_consistent() == False`.
6. `precomputable_types()` = {CLASS_HIERARCHY, CLASS_ASSERTIONS, OBJECT_PROPERTY_HIERARCHY, DATA_PROPERTY_HIERARCHY, OBJECT_PROPERTY_ASSERTIONS, DATA_PROPERTY_ASSERTIONS, SAME_INDIVIDUAL, DISJOINT_CLASSES}. All are produced in one closure pass.

### 1.4 Preferences: which InferenceTypes get precomputed

`ReasonerPreferences` (preference set `INFERENCE_PREFS_SET`, key `DEFAULT_REASONER_ID`, default `org.protege.editor.owl.NoOpReasoner`) combines two parts:
- **Precomputed** (`PrecomputedInferencePreferences`): `required` and `disallowed` sets of InferenceType, plus a `requested: Map<InferenceType, Set<requestorId>>`.
  - Effective set = `{t | t ∈ required or requested[t] non-empty} − disallowed`.
  - Persisted per type as `Require_<TYPE>` and `Disallow_<TYPE>` booleans.
  - Plugins call `requestPrecomputedInferences(requestor, types)`, which is replace semantics for that requestor.
- **Displayed** (`DisplayedInferencePreferences`): the master switch `SHOW_INFERENCES` (status-bar checkbox "Show Inferences", default true) and one boolean per `OptionalInferenceTask`. On load and save, the enabled tasks' *suggested InferenceType*s are registered as requestor `"Displayed Inference Preferences"`. **So enabling a displayed inference automatically triggers precomputation of its type.**
  - `executeTask(task, runnable)` runs only if `showInferences && enabled(task)`.
  - It swallows `UnsupportedOperationException` (the reasoner does not support the query).
  - It measures time per task (`getAverageTimeInTask` is shown in the preferences panel).

The 19 OptionalInferenceTasks, with their defaults and suggested types:

| Task | Default | Suggests |
|---|---|---|
| SHOW_CLASS_UNSATISFIABILITY | on | CLASS_HIERARCHY |
| SHOW_INFERRED_EQUIVALENT_CLASSES | on | CLASS_HIERARCHY |
| SHOW_INFERRED_SUPER_CLASSES | on | CLASS_HIERARCHY |
| SHOW_INFERED_CLASS_MEMBERS (sic) | on | CLASS_ASSERTIONS |
| SHOW_INFERRED_DISJOINT_CLASSES | off | CLASS_HIERARCHY |
| SHOW_OBJECT_PROPERTY_UNSATISFIABILITY | on | OBJECT_PROPERTY_HIERARCHY |
| SHOW_INFERRED_OBJECT_PROPERTY_DOMAINS | off | CLASS_HIERARCHY |
| SHOW_INFERRED_OBJECT_PROPERTY_RANGES | off | CLASS_HIERARCHY |
| SHOW_INFERRED_EQUIVALENT_OBJECT_PROPERTIES | on | OBJECT_PROPERTY_HIERARCHY |
| SHOW_INFERRED_SUPER_OBJECT_PROPERTIES | on | OBJECT_PROPERTY_HIERARCHY |
| SHOW_INFERRED_INVERSE_PROPERTIES | on | OBJECT_PROPERTY_HIERARCHY |
| SHOW_INFERRED_DATATYPE_PROPERTY_DOMAINS | off | CLASS_HIERARCHY |
| SHOW_INFERRED_EQUIVALENT_DATATYPE_PROPERTIES | on | DATA_PROPERTY_HIERARCHY |
| SHOW_INFERRED_SUPER_DATATYPE_PROPERTIES | on | DATA_PROPERTY_HIERARCHY |
| SHOW_INFERRED_TYPES | on | CLASS_ASSERTIONS |
| SHOW_INFERRED_OBJECT_PROPERTY_ASSERTIONS | on | OBJECT_PROPERTY_ASSERTIONS |
| SHOW_INFERRED_DATA_PROPERTY_ASSERTIONS | off | DATA_PROPERTY_ASSERTIONS |
| SHOW_INFERRED_SAMEAS_INDIVIDUAL_ASSERTIONS | on | SAME_INDIVIDUAL |

Default effective precompute set: {CLASS_HIERARCHY, CLASS_ASSERTIONS, OBJECT_PROPERTY_HIERARCHY, DATA_PROPERTY_HIERARCHY, OBJECT_PROPERTY_ASSERTIONS, SAME_INDIVIDUAL}.

Python: `sip.reasoning.prefs.ReasonerPreferences` (a dataclass persisted to the platform settings store, see §5.4), with `effective_precompute()` and `run_if_enabled(task, fn)`.

### 1.5 Inferred hierarchy providers

All of them read `ReasonerManager.current_reasoner` lazily on every call, so nothing is cached. When the reasoner is a NoOp they degrade to empty or trivial results.

**`OWL/model/hierarchy/cls/InferredOWLClassHierarchyProvider.java`**
```
roots() = {owl:Thing}
children(X):
  if not R.is_consistent(): return {}
  subs = R.sub_classes(X, direct=True).flatten()
  if X == Thing and R.unsatisfiable_classes() is not a singleton {Nothing}: subs.add(Nothing)
  elif X == Nothing: subs |= R.unsatisfiable_classes() - {Nothing}   # unsat classes hang under Nothing
  else: subs.discard(Nothing); subs = {c in subs | R.is_satisfiable(c)}
  return subs
parents(X): if inconsistent: {}; if X==Nothing: {Thing}; if not R.is_satisfiable(X): {Nothing}
            else R.super_classes(X, direct=True).flatten() - {X}
descendants(X)/ancestors(X): R.sub/super_classes(X, direct=False).flatten()  (empty if inconsistent)
equivalents(X): {} if inconsistent or X unsat else R.equivalent_classes(X) - {X}
```
Invariants:
- Unsatisfiable classes appear **only** under `owl:Nothing`, and Nothing appears under Thing only when unsatisfiable classes exist.
- An inconsistent ontology shows an empty tree under Thing.

**`OWL/model/hierarchy/cls/InferredSuperClassHierarchyProvider.java`** is an inverted tree: "children" are direct superclasses and "parents" are direct subclasses. The reasoner is injected with `setReasoner`. It returns empty for an unsatisfiable class.

**`OWL/model/hierarchy/property/InferredObjectPropertyHierarchyProvider.java`** extends the asserted provider, so roots are asserted. Children are direct sub-properties minus self and minus `owl:bottomObjectProperty`, keeping named properties only. Parents are direct super-properties minus self. Equivalents are named equivalents minus self. Empty if inconsistent. Exceptions are logged and treated as empty.

**`OWL/model/hierarchy/IndividualsByInferredTypeHierarchyProvider.java`**: on `setReasoner`, for every class in the imports closure's signature it computes `getInstances(cls, direct=True)`. Classes with no instances are skipped. Roots are those classes, and children are their instances.

**There is no inferred data-property hierarchy provider in the repo.** Only the asserted provider exists (see `OWLHierarchyManagerImpl`).

Inferred views (OWL-PX ViewComponent ids): `InferredOWLClassHierarchy`, `OWLInferredSuperClassHierarchy`, `InferredObjectPropertyTree`, `OWLIndividualsByInferredType`, `OWLInferredMembersList`, `InferredAxioms` ("Classification results").

Python: `sip.reasoning.hierarchy.InferredClassHierarchy(manager)`, `InferredSuperClassHierarchy`, `InferredObjectPropertyHierarchy`, `IndividualsByInferredType`. They share one `HierarchyProvider` protocol with the asserted providers (the other agent's scope).

### 1.6 Inferred rows in frames (the "yellow" rows)

`OWL/ui/frame/AbstractOWLFrameSection.setRootObject`:
1. For each active ontology, call `refill(ont)` (asserted rows; the section remembers the `added` objects).
2. Call `refillInferred()`. `InconsistentOntologyException` is logged and the rest is ignored.
3. Sort the rows.

Inferred rows have `ontology == null`. `addInferredRowIfNontrivial(row)` drops rows whose axiom is vacuous (§1.7). There are 20 subclass overrides. Representative algorithms:
- **Superclasses** (`cls/OWLSubClassAxiomFrameSection`): skip if inconsistent or the root is unsatisfiable. Then, under `executeTask(SHOW_INFERRED_SUPER_CLASSES)`: for each node in `super_classes(root, direct=True)` and each class D in the node not already asserted, add `SubClassOf(root, D)`.
- **Equivalent classes** (`cls/OWLEquivalentClassesAxiomFrameSection`, task SHOW_INFERRED_EQUIVALENT_CLASSES): if the root is unsatisfiable (and is not Nothing), add the row `EquivalentClasses(root, owl:Nothing)`. This is how **unsatisfiable classes display** in the class description. Otherwise add `EquivalentClasses(root, E)` for each reasoner equivalent not already asserted.
- **Types** (`individual/OWLClassAssertionAxiomTypeFrameSection`, SHOW_INFERRED_TYPES): for named individuals, add `ClassAssertion(T, ind)` for each direct type T not already asserted.
- Others follow the same pattern: members, disjoints, sub/equivalent/inverse/domain/range of properties, object and data property assertions, same individuals.
- **"Classification results" view** (`OWL/ui/frame/InferredAxiomsFrameSection.refillInferred`):
  1. For each unsatisfiable class except Nothing, add the row `SubClassOf(C, owl:Nothing)`.
  2. Run the OWLAPI `InferredOntologyGenerator` with SubClass, ClassAssertion, SubObjectProperty and SubDataProperty generators into a scratch ontology.
  3. Show every generated axiom that is **not contained in any active ontology** and is non-trivial.

**Unsatisfiable-class display elsewhere.** `OWL/ui/renderer/OWLCellRenderer` (when `highlightUnsatisfiableClasses`, under SHOW_CLASS_UNSATISFIABILITY) paints a class token red if the ontology is inconsistent or the class is unsatisfiable. `ProtegeTreeNodeRenderer.isSatisfiable` does the same in trees, and `OWLObjectStyledStringRenderer` does the same in styled strings.

Python: `sip.reasoning.inferred_rows.inferred_superclass_rows(cls)` and similar functions. Each returns `[(axiom, None)]`, filtered by `is_vacuous` and already-asserted checks.

### 1.7 VacuousAxiomVisitor (`OWL/model/inference/VacuousAxiomVisitor.java`)

This is used by the frames and by the inferred-ontology export. An axiom is **vacuous** if any of these holds:
- `SubClassOf(_, owl:Thing)` or `SubClassOf(owl:Nothing, _)`
- `DisjointClasses` with exactly 2 operands, one of them `owl:Nothing`
- object or data property domain is `owl:Thing`
- object property range is `owl:Thing`, or data property range is `rdfs:Literal` (the top datatype)
- disjoint properties with exactly 2 operands, one of them the bottom property
- `SubObjectPropertyOf(_, topObjectProperty)` or `SubObjectPropertyOf(bottomObjectProperty, _)`, and the same for data properties
- `ClassAssertion(owl:Thing, _)`
- an object property assertion on `topObjectProperty`, or a data property assertion on `topDataProperty`
- **any non-logical axiom**: Declaration, AnnotationAssertion, SubAnnotationPropertyOf, AnnotationPropertyDomain, AnnotationPropertyRange

`involvesInverseSquared(ax)` is true for `EquivalentObjectProperties` with exactly 2 operands where one is named and one is an inverse, i.e. `p ≡ inverse(q)`. It is also true for `InverseObjectProperties` where exactly one side is anonymous (`inverse(inverse(p))` artefacts). Both are dropped.

Python: `sip.reasoning.vacuous.is_vacuous(ax) -> bool` and `involves_inverse_squared(ax) -> bool`.

### 1.8 Inconsistency handling

- The reasoner throws `InconsistentOntologyException` during precompute. The run sets `inconsistencyFound`, installs the reasoner anyway (so the status becomes INCONSISTENT), and calls `InconsistentOntologyManager.get(mm).explain()`.
- `OWL/ui/explanation/io/InconsistentOntologyManager.java` is an **EditorKitHook** (OWL-PX `EditorKitHook` id `InconsistentOntologyManager`). It stores itself in the model manager with `put(InconsistentOntologyManager.class, this)`. `explain()`:
  1. Shows `IntroductoryPanel`, which lists the plugins from extension point `org.protege.editor.owl.inconsistentOntologyExplanation` and preselects the last one used.
  2. On "Explain", it instantiates the selected plugin and calls `initialise()`, then `setup(editorKit)`, then `explain(activeOntology)`.
  3. It keeps the instance so it can be disposed later.
- The menu item "Explain inconsistent ontology" (`ExplainInconsistentOntologyAction`) calls the same `explain()`, and is enabled only in the INCONSISTENT state.
- All frame and hierarchy code guards with `if not R.is_consistent(): return empty`.

Python: `sip.explain.inconsistency.InconsistencyExplainer` registry (entry-point group `sip.inconsistent_ontology_explanation`). The default implementation calls the justification engine (§2) with entailment `⊤ ⊑ ⊥` (inconsistency).

---

## 2. Explanation

### 2.1 In-repo framework (orchestration only)

| Class | Function |
|---|---|
| `OWL/ui/explanation/ExplanationService.java` (abstract `ProtegePluginInstance`) | `setup(editorKit, pluginId, name)`, `initialise()`, **`hasExplanation(OWLAxiom)`**, **`explain(OWLAxiom) -> ExplanationResult`** |
| `ExplanationResult` | A `JPanel` with `dispose()`. The service owns the rendering |
| `ExplanationPlugin` / `ExplanationPluginLoader` | Extension point `org.protege.editor.owl.explanation` |
| `ExplanationManager` (created per editor kit in `OWLEditorKit` ctor: `modelManager.setExplanationManager(new ExplanationManager(this))`) | See `reload()` below |
| `ExplanationDialog` | If exactly one service applies, uses it directly. Otherwise shows a combo box whose initial selection is `prefs.defaultExplanationService` when `useLastExplanationService` (default true). A change of selection persists the new default, disposes the old result and calls `explain` again |
| `ExplanationPreferences` | Set `EXPLANATION_PREFS_SET`. Keys `PREFERRED_PLUGIN_ID`, `USE_LAST_EXPLANATION_SERVICE`, `EXPLANATION_SERVICES_LIST`, `DISABLED_EXPLANATION_SERVICES` |
| `ExplanationPreferencesGeneralPanel`, `SortedPluginsTableModel`, CORE `ui/explanationpreferences/*` | The preferences UI, plus extension point `explanationpreferencespanel` |
| Trigger: `OWL/ui/framelist/OWLFrameList.java` | Shows the "?" button for a row if `hasExplanation(row.getAxiom())`, and on click calls `handleExplain(frame, ax)` |

`ExplanationManager.reload()` works as follows:
1. Load all plugins, call `initialise()` on each, and key them by plugin id in a TreeMap.
2. Order them first by the persisted `explanationServicesList`, then append any new ones sorted by id.
3. Persist the list.
4. `enabledServices` = the ordered list minus `disabledExplanationServices`.

Its query methods:
- `getTeachers(ax)` = the enabled services for which `hasExplanation(ax)` is true.
- `handleExplain` opens a non-modal resizable dialog titled `"Explanation for " + rendering(ax)`.

Python (`sip.explain`):
```
class ExplanationService(Protocol): id: str; name: str; has_explanation(ax) -> bool; explain(ax) -> ExplanationResult
@dataclass class ExplanationResult: entailment; justifications: list[frozenset[Axiom]]; complete: bool; laconic: bool=False
class ExplanationManager: services ordered by prefs; enabled(); teachers(ax); explain(ax, service_id=None)
```
In a web or headless platform, `ExplanationResult` is data, not a panel. `JustificationFormatting` belongs to the external workbench; for rendering, see §2.4.

### 2.2 Black-box justification (port of owlexplanation; not in this repo)

The standard Protégé explanation plugin is "Explanation Workbench", built on `owlexplanation`. It is a **black-box, reasoner-agnostic** algorithm. Definitions:
- O is the set of (logical) axioms.
- η is the entailment.
- `entailed(S)` is true iff the reasoner, run over S alone, entails η.

**Entailment checks:**
- For `SubClassOf(C, D)`: check that `C ⊓ ¬D` is unsatisfiable in S. Equivalently, add a fresh individual `a : C ⊓ ¬D` and test consistency.
- For `ClassAssertion(C, a)`: `a : ¬C` must be inconsistent.
- For `EquivalentClasses`: entail both directions.
- For inconsistency: `not consistent(S)`.
- With owlrl (RL only) you cannot express `¬D` in general. Use **direct closure lookup** instead: materialise S and check that the triple `(C rdfs:subClassOf D)` is present, or `(a rdf:type C)`, or the error triple for inconsistency. Results are then complete only with respect to OWL RL.

**Step 0, module extraction.** Every justification lies inside the syntactic-locality ⊥-module (BOT) or ⊤⊥* (STAR) module of `sig(η)`. Compute the module M first and use it as O. Pseudo-code for a ⊥-locality module, approximate but safe:
```
def bot_module(axioms, seed_sig):
  sig = set(seed_sig); M = set(); changed = True
  while changed:
    changed = False
    for ax in axioms - M:
      if not is_bot_local(ax, sig):      # ax is non-local w.r.t. sig
        M.add(ax); sig |= signature(ax); changed = True
  return M
# is_bot_local(ax, sig): replace every entity not in sig by ⊥ (classes/properties); ax is local iff it becomes a tautology.
#  e.g. SubClassOf(C,D) is ⊥-local iff C is ⊥-equivalent under the substitution (C's top-level atom not in sig, an
#  intersection with a non-sig conjunct, an existential on a non-sig property, ...). Declarations and annotations are always local.
```
If you implement `is_bot_local` incompletely, err toward "non-local", i.e. include the axiom. That keeps the module sound, only larger.

**Step 1, single justification by expand-contract:**
```
def compute_one_justification(O, eta, entailed):
    # --- Expansion: grow S until entailed(S) ---
    S = set(); sig = signature(eta)
    # (a) structural expansion: axioms whose signature overlaps the current signature, breadth-first
    frontier = [ax for ax in O if signature(ax) & sig]
    while not entailed(S):
        if not frontier:                      # structural expansion exhausted -> fall back to everything
            S = set(O)
            if not entailed(S): return None   # eta not entailed at all
            break
        # add in growing batches (owlexplanation increases batch size, ~x1.25..x2, to limit checks)
        batch, frontier = take(frontier, k := max(1, int(len(S)*0.25)) or 1)
        S |= set(batch); sig |= union(signature(a) for a in batch)
        frontier += [ax for ax in O - S if signature(ax) & sig and ax not in frontier]
    # --- Contraction: remove until minimal ---
    # (b) sliding-window "fast pruning" (window w = e.g. 10): try dropping blocks of axioms
    S = list(S); w = min(10, len(S))
    while w > 1:
        i = 0
        while i < len(S):
            window = S[i:i+w]; candidate = S[:i] + S[i+w:]
            if entailed(set(candidate)): S = candidate        # whole window was irrelevant
            else: i += w
        w //= 2
    # (c) final linear pass (guarantees minimality)
    for ax in list(S):
        T = set(S) - {ax}
        if entailed(T): S = list(T)
    return frozenset(S)
```
Alternative contraction: divide and conquer (QuickXplain), with fewer checks for small justifications:
```
def qx(B, D, C):                       # B background kept, C candidates; returns minimal subset of C
    if D and entailed(B): return set()
    if len(C) == 1: return set(C)
    C1, C2 = split(C)
    D2 = qx(B | C1, C1, C2)
    D1 = qx(B | D2, D2, C1)
    return D1 | D2
justification = qx(set(), set(), list(S))  # call only when entailed(S)
```

**Step 2, all justifications by Reiter's Hitting-Set Tree (HST)**, with the standard optimisations: justification reuse, early path termination, and closed-path subsumption.
```
def all_justifications(O, eta, entailed, limit=None, time_budget=None):
    J0 = compute_one_justification(O, eta, entailed)
    if J0 is None: return [], True
    justs = [J0]; closed_paths = []          # hitting sets found (sets of removed axioms)
    explored = set()                         # frozenset(path) already expanded
    queue = deque([(frozenset(), J0)])       # BFS gives shortest-first hitting sets
    while queue:
        if limit and len(justs) >= limit: return justs, False
        path, J = queue.popleft()
        for ax in sorted(J, key=stable_order):          # deterministic ordering
            new_path = path | {ax}
            if new_path in explored: continue
            explored.add(new_path)
            if any(cp <= new_path for cp in closed_paths): continue   # early path termination
            # reuse: a known justification disjoint from the path is still a justification of O - new_path
            reuse = next((Jk for Jk in justs if not (Jk & new_path)), None)
            if reuse is not None:
                queue.append((new_path, reuse)); continue
            O2 = O - new_path
            if not entailed(O2):
                closed_paths.append(new_path); continue           # new_path is a hitting set
            Jn = compute_one_justification(O2, eta, entailed)
            justs.append(Jn); queue.append((new_path, Jn))
    return justs, True                                             # complete
```
Invariants:
1. Every node label is a justification of `O − path`.
2. A path that leads to non-entailment is a minimal-candidate hitting set.
3. The search terminates because paths grow strictly and O is finite.
4. Completeness holds iff the tree was fully expanded (no limit reached).

Cost is dominated by `entailed()` calls. **Cache them** with a dict keyed by `frozenset(axioms)`, and incrementally reuse the closure when you can.

**Laconic or precise justifications** (optional, an owlexplanation feature): split axioms into their weakest parts. For example, `A ⊑ B ⊓ C` becomes `A ⊑ B` and `A ⊑ C`, and `A ⊑ ∃r.(B ⊓ C)` yields `A ⊑ ∃r.B`. Recompute justifications over the split set and map the results back to source axioms. For a first port, use **`SplitSubClassAxioms`-style splitting** (§3.10) as the "laconic-lite" variant.

**Inconsistent ontologies:** η = "inconsistent" (`entailed(S) := not consistent(S)`). The module trick does not apply (seed signature is empty), so use the full ABox+TBox, or the ⊤⊥* module of the signature of all ABox individuals.

**Python modules:** `sip.explain.blackbox.single_justification(...)`, `sip.explain.hst.all_justifications(...)`, `sip.explain.modules.bot_module(...)`, `sip.explain.entailment.OwlRlEntailmentChecker(graph_builder)`. The last one builds a temporary rdflib Graph from an axiom subset with `AxiomIndex.serialize(axioms)`, expands it with owlrl, checks for the target triple, and memoises by `frozenset`.

### 2.3 Which axioms get the "?" button

In the workbench, `hasExplanation(ax)` returns true for logical axioms when a reasoner is active. Protégé itself only asks the services. For the port, return true when `ax.is_logical` and the reasoner state is INITIALIZED or INCONSISTENT. That covers both asserted rows (explaining why an asserted axiom is entailed, which trivially includes itself) and inferred rows.

### 2.4 Formatting justifications (workbench behaviour to replicate)

Order each justification's axioms as a derivation tree:
1. The root is the axiom(s) whose LHS contains the entailment's subject.
2. Children are the axioms whose LHS entity appears in the parent's RHS signature (indent one level).
3. Remaining axioms (property axioms, ABox) come last.

Also show:
- per-justification popularity: the number of justifications containing the axiom;
- for each axiom, the ontology it is asserted in.

Python: `sip.explain.format.order_justification(J, eta) -> list[tuple[depth, Axiom]]`.

---

## 3. Refactoring and editing actions

### 3.1 Complete enumeration of refactoring and logical-editing menu actions

These come from OWL-PX. Menu paths are slot-ordered, and ids are prefixed `org.protege.editor.owl.`.

**Refactor menu (13 items):**

| Menu label | Id | Class (`OWL/ui/action/…` unless noted) |
|---|---|---|
| Rename entity... | menu.RenameEntity | `RenameEntityAction` |
| Rename multiple entities... | menu.RenameEntitiesBySearchAndReplace | `RenameEntitiesBySearchAndReplaceAction` (+ `OWL/ui/rename/RenameEntitiesPanel`) |
| Change ontology IRI... | menu.ChangeOntologyURI | `ChangeOntologyIRI` |
| Convert entity IRIs to labels... | menu.ConvertEntityURIsToLabels | `ConvertEntityURIsToLabels` (+ `OWL/model/refactor/ontology/ConvertEntityURIsToIdentifierPattern`) |
| Convert property assertion on class/individual puns to annotations | menu.ChangePropertyAssertionPunsToAnnotations | `ConvertAssertionsOnPunsToAnnotations` |
| Coerce data property values into property range | menu.CoerceDataPropertyValuesIntoPropertyRange | `CoerceDataPropertyValuesIntoPropertyRangeAction` (OWLAPI `CoerceConstantsIntoDataPropertyRange`) |
| Split subclass axioms | menu.SplitSubClassAxioms | `SplitSubClassAxiomsAction` (OWLAPI `SplitSubClassAxioms`) |
| Amalgamate subclass axioms | menu.AmalgamateSubClassAxioms | `AmalgamateSuperClassesAction` (OWLAPI `AmalgamateSubClassAxioms`) |
| Split disjoint classes into pairwise disjoints | menu.SplitDisjointClasses | `SplitDisjointClassesAction` |
| Amalgamate disjoint classes into larger disjoint sets | menu.AmalgamateDisjointClassesAction | `AmalgamateDisjointClassesAction` |
| Convert qualified min cardinality 1 to someValuesFrom | menu.ConvertMinOneToSomeValuesFromAction | `ConvertMinOneToSomeValuesFromAction` |
| Copy/move/delete axioms ... | menu.MoveAxiomsToOntologyAction | `MoveAxiomsToOntologyAction` (+ `OWL/ui/ontology/wizard/move/MoveAxiomsWizard`) |
| Merge ontologies... | menu.MergeOntologies | `MergeOntologiesAction` (+ `OWL/ui/ontology/wizard/merge/*`, `OWL/model/refactor/ontology/OntologyMerger`) |

**Edit menu (logical edits and refactorings):**

| Label | Class |
|---|---|
| Delete... | `DeleteAction` (delegates to the view's deleter, §4.2) |
| Duplicate selected class... | `DuplicateSelectedClassAction` |
| Convert to primitive class | `ConvertToPrimitiveClassAction` |
| Convert to defined class | `ConvertToDefinedClassAction` |
| Make primitive siblings disjoint | `MakePrimitiveSiblingsDisjoint` |
| Make all individuals different | `MakeAllIndividualsDifferent` (+ `OWL/model/refactor/AllDifferentCreator`) |
| Make instances different | `MakeInstancesOfClassDifferentIndividualsAction` |
| Add covering axiom | `AddCoveringAxiomAction` |
| Remove local disjoint classes axioms... | `RemoveLocalDisjointAxiomsAction` |
| Remove all disjoint classes axioms... | `RemoveAllDisjointAxiomsAction` |
| Deprecate entity... | `OWL/ui/deprecation/DeprecateSelectedEntityAction` → `OWL/model/deprecation/EntityDeprecator` |
| Merge into entity... | `OWL/ui/merge/MergeEntitiesAction` → `OWL/model/merge/MergeEntitiesChangeListGenerator` |
| Create new / Create child / Create sibling | `CreateNewObjectAction`, `CreateNewChildAction`, `CreateNewSiblingAction` |
| Cut / Copy / Paste / Copy sub-hierarchy as tab-indented text | `CutAction`, `CopyAction`, `PasteAction`, `CopySubHierarchyToClipboardAction` |

**Tools menu:**
- Usage... (`ShowUsageAction`)
- Create class / object property / data property hierarchy... (`CreateSubClassHierarchyAction`, `CreateSubObjectPropertyHierarchyAction`, `CreateSubDataPropertyHierarchyAction`, all using `OWL/model/hierarchy/tabbed/*`)

**File menu:**
- Gather ontologies... (`GatherOntologiesAction`)
- Export inferred axioms as ontology... (`OWL/ui/action/export/inferred/ExportInferredOntologyAction`)
- Reload (`ReloadActiveOntologyAction`)

**Context menus** (asserted class, object property, data property, annotation property and individual hierarchies; entity banner): Change IRI (Rename) (`RenameEntityAction`), Merge into..., Deprecate..., Add subclasses / sub-properties..., Duplicate class..., Convert to primitive / defined, Remove disjoint classes axioms for subclasses..., Make primitive siblings disjoint, Copy IRI / OBO Id / display name / Markdown.

**Frame-list popup:** "Create closure axiom" (`OWL/ui/framelist/CreateClosureAxiomAction`).

**Implicit in a view:** changing the ontology IRI in the Ontology header view (`OWL/ui/view/ontology/OWLOntologyAnnotationViewComponent`) triggers `EntityIRIUpdaterOntologyChangeStrategy`, "rename entities as well as ontology?" (§3.4).

**Not present** as discrete actions in this repo: "split ontology" (it is done with Copy/move axioms into a new ontology), "create/convert property chain" (only the editor `OWL/ui/editor/OWLObjectPropertyChainEditor` and the frame section `OWLPropertyChainAxiomFrameSection`), and "copy/move ontology" (only Gather ontologies plus Save as). Property chains are edited as plain `SubPropertyChainOf` axioms. `OWL/ui/clsdescriptioneditor/OWLPropertyChainChecker` parses a list of object property names separated by `o`.

### 3.2 Rename entity / Change IRI (`RenameEntityAction`, `RenameEntityPanel`)

**UI and input:**
- The text field shows the short name, computed by `IriSplitter`. When "Show full IRI" is checked (sticky static), it shows the full IRI.
- The new IRI is `base + text.trim().replace(" ", "_")`, where `base = URLDecode(iri)[0 : len − len(shortName)]`. If the full IRI is shown, the text is used as is. A `URISyntaxException` aborts with `None`.
- The checkbox **"Change all types of entity with this IRI"** (`AUTO_RENAME_PUNS`, application preference, default false) chooses between:
  - `OWLEntityRenamer.changeIRI(IRI old, IRI new)`, which renames **every pun**: class, individual, property and so on sharing the IRI;
  - `OWLEntityRenamer.changeIRI(OWLEntity e, IRI new)`, which renames only that typed entity.
- Scope is **all loaded ontologies** (`getOntologies()`, not only active ones). Afterwards the action selects the new entity of the same type.

**OWLAPI `OWLEntityRenamer` semantics** (what to port):
```
def change_iri_entity(onts, entity, new_iri):            # typed (no puns)
    changes = []
    for o in onts:
        axs = o.referencing_axioms(entity, imports=EXCLUDED)            # axioms with entity in signature
        axs |= o.annotation_assertions(subject=entity.iri)              # subject is the IRI
        # OWLAPI also treats annotation assertions whose *value* is the IRI as referencing (via duplicator)
        for ax in axs:
            new = duplicate(ax, entity_map={entity: new_iri})           # rewrite only that typed entity
            # NB duplicator also rewrites the IRI when it appears as annotation subject/value
            changes += [RemoveAxiom(o, ax), AddAxiom(o, new)]
    return changes

def change_iri_iri(onts, old, new):                       # all puns
    for o in onts:
        axs = union(o.referencing_axioms(e) for e in o.entities_in_signature(old)) | o.annotation_assertions(old)
        # rewrite with iri_map {old: new} -> every occurrence of the IRI (entities, annotation subjects, IRI values)
        ...
def change_iri_map(onts, {entity: new_iri})               # bulk (used by multi-rename and ontology-IRI cascade)
```
Edge cases:
- The rename of an entity that already exists at the target IRI is a **merge by renaming**. Axioms coalesce, because sets deduplicate. This is how "Merge entities" works (§3.6).
- Axioms in imported but read-only ontologies are also rewritten if those ontologies are loaded.
- Ontology annotations whose value is the IRI are *not* touched by `OWLEntityRenamer` (only axioms are).

**Python (rdflib makes this simpler):**
```
def rename_iri(dataset, old: URIRef, new: URIRef, graphs, typed: Optional[EntityType]=None) -> list[Change]
```
- Puns mode: rewrite every triple in each graph where `s == old`, `p == old` or `o == old`. Bnode-rooted axiom structures are rewritten in place, because the triples that mention `old` are replaced individually.
- Typed mode: only rewrite triples inside axioms whose parsed axiom references `entity(typed, old)`, plus the declaration `old rdf:type owl:Class` (for that type) and annotation assertions with subject `old`. Leave other-type usages untouched. This must go through `AxiomIndex`, because a raw triple cannot tell punned usages apart.

### 3.3 Rename multiple entities (`RenameEntitiesPanel`)

**Building the candidate list:**
1. `nsMap` maps each *namespace* to entities. Namespace = `iri[0 : iri.lastIndexOf(shortForm)]`, where `shortForm` = `IRI.getRemainder()`, or else the last path segment, or else the whole IRI. It is built over the signature of all loaded ontologies.
2. The Find and Replace combos are editable. The Find combo is prefilled with the namespaces, and a 1 s debounce applies.
3. Matches:
   - if `find ∈ nsMap`, the matches are `nsMap[find]`, and **prefix mode** gives `new = replace + iri[len(find):]`;
   - otherwise, **regex mode** matches entities whose IRI fully matches `.*find.*`, and gives `new = iri.replaceAll(find, replace)` (Java regex; note that the map is computed over *all* entities in the signature).
4. A result must be an absolute URI, or it goes into `errorMap`. Error entries are shown with strikethrough.
5. The dialog is valid iff Find and Replace are non-empty, at least one entity is checked, and there are no errors.

**Apply:** `OWLEntityRenamer.changeIRI(Map<entity,newIRI>)` over the checked entities only, in all loaded ontologies.

Python: `sip.refactor.rename.bulk_rename(prefix=None, regex=None, replacement, entities_filter) -> (mapping, errors, changes)`. Use Python `re` with the Java-style `$1` translated to `\1`.

### 3.4 Change ontology IRI (`ChangeOntologyIRI`) and cascading entity rename

`ChangeOntologyIRI.getChanges(ont, newId)`:
```
changes = [SetOntologyID(ont, new_id)]
if not new_id.anonymous and new_id != old_id:
  for o in all_loaded_ontologies:
    for decl in o.imports:
      if decl.iri == old_id.version_iri:  changes += [RemoveImport(o,decl), AddImport(o, new_id.default_document_iri)]
      elif decl.iri == old_id.ontology_iri: changes += [RemoveImport(o,decl), AddImport(o, new_id.ontology_iri)]
```
(`default_document_iri` = the version IRI if present, else the ontology IRI.) Entities are **not** renamed by this menu action.

The **Ontology header view** offers a cascade when the IRI is edited there (`OWLOntologyAnnotationViewComponent.handlePossibleOntologyIdUpdate`), using `OWL/model/refactor/ontology/EntityIRIUpdaterOntologyChangeStrategy`:
```
if from/to both non-anonymous and differ:
  fromBase = str(from.ontology_iri); toBase = str(to.ontology_iri)     # NB: no '#' or '/' appended
  for entities in [obj props, data props, ann props, classes, individuals, datatypes] of THIS ontology (imports excluded):
     if len(iri) > len(fromBase) and iri.startswith(fromBase): map[e] = toBase + iri[len(fromBase):]
  if map and user confirms "Rename entities as well as ontology?": apply OWLEntityRenamer(map) on {ontology} only
```
Edge cases:
- This is a pure string-prefix test. An ontology `http://x/onto` also captures `http://x/ontology2#A`. The port should require the remainder to begin with `#` or `/`, or flag such cases.
- Only the edited ontology is rewritten. Importing ontologies keep their old references.

Python: `sip.refactor.ontology_iri.change_ontology_iri(ont, new_id, cascade_entities: bool) -> list[Change]`.

### 3.5 Convert entity IRIs to labels (`ConvertEntityURIsToLabels`, `ConvertEntityURIsToIdentifierPattern`)

This is the "names to auto-IDs" migration.

```
label_props = renderer prefs annotation IRIs (ordered), lang map per prop
sfp = AnnotationValueShortFormProvider(label_props, langs, fallback = "")         # empty if no label
id_gen = OWLEntityIRIRegenerator (CustomOWLEntityFactory with isFragmentAutoGenerated forced True)
iri_map = {}
for e in signature(all loaded onts) - {owl:Thing}:
    lbl = sfp(e)                                  # "" when the entity has no label
    # refactorWhenLabelPresent: iri ends with lbl AND the char before it is '#' or '/'
    # with lbl == "" this is "iri ends with '#' or '/'"?  -> in practice the condition is true when the
    # label equals the IRI fragment (or the entity has no label: the char at len-1 must be '#'/'/', normally false)
    if iri.endswith(lbl) and iri[len(iri)-1-len(lbl)] in "#/":
        iri_map[e] = id_gen.generate(e)           # base = iri minus remainder; fragment = auto-id per "New entities" prefs
changes = []
for e, new in iri_map.items():
    onts = OntologyImportsWalker.lowest_ontologies_referencing(e)     # leaves of the import DAG among ontologies containing e
    if len(onts) > 1: onts = resolver(e, onts)    # ask user, or "add to all" -> onts unchanged
    if onts: label = AnnotationAssertion(pref_label_prop or rdfs:label, new, Literal(fragmentRendering(e), lang=first pref lang or None))
             changes += [AddAxiom(o, label) for o in onts]
    else: log "cannot determine target"           # note: the IRI is still converted below
changes += OWLEntityURIConverter(all loaded onts, strategy=lambda e: iri_map.get(e, e.iri)).get_changes()
apply(changes)
```
`OntologyImportsWalker.getLowestOntologiesToContainReference`:
- referencing = the ontologies whose signature contains e;
- leaves = referencing minus every ancestor (importer) of any member, but only while more than one leaf remains.
- Note: the code uses `hp.getAncestors` of `OWLOntologyHierarchyProvider`, where "ancestors" means *importers*.

Edge cases:
- Built-in entities keep their IRI (`generateNewIRI` returns the same IRI).
- `fragmentRenderer` is `OWLEntityRendererImpl`, i.e. the IRI short form. **The new label is the old fragment, not the old label.**
- In practice, entities that already have a label different from their fragment are skipped.

Python: `sip.refactor.ids.convert_names_to_ids(id_policy, label_prop=RDFS.label, lang=None, resolver=...)`. Reuse the platform's new-entity IRI policy (UUID, numeric counter with prefix, or the like).

### 3.6 Merge entities (`MergeEntitiesAction`, `MergeEntitiesChangeListGenerator`, `MergeStrategy`)

The UI always passes `MergeStrategy.DELETE_SOURCE_ENTITY`. Root = active ontology; scope = its **imports closure**. The change list is generated in this order:
```
1 replaceUsage:   for src in sources: OWLEntityRenamer(closure).changeIRI(src.iri, target.iri)   # pun-wide IRI rename
2 replaceLabels:  for o in closure, src: for ax in o.annotation_assertions(src.iri) where prop in {rdfs:label, skos:prefLabel}:
                     Remove(o, AnnotationAssertion(target.iri, ax.annotation, ax.annotations))   # the renamed copy from step 1
                     Add(o, AnnotationAssertion(target.iri, Annotation(P_alt, ax.value, ax.annotation.annotations), ax.annotations))
                   P_alt = oboInOwl:hasRelatedSynonym if target IRI is an OBO IRI else skos:altLabel
3 replaceId (only if target is OBO IRI): for oboInOwl:id assertions on src:
                     Remove(o, <same assertion re-subjected to target>); Add(o, <obo:hasAlternativeId with that value on target>)
4 deprecateSourceEntities: skipped for DELETE_SOURCE_ENTITY;
                     otherwise Add(root, AnnotationAssertion(owl:deprecated, src.iri, true))
```
Invariants and edge cases:
- Steps 2 and 3 are computed **before** any change is applied (on the source IRI), but they remove the target-subject copies that step 1 *will* create. **Order matters.** In the port, compute the list fully and then apply it sequentially.
- If the target already carried an *identical* label assertion, step 2 also removes the target's own label. This is a latent quirk; keep it or guard it.
- Because the rename is pun-wide, a class merged into a class also merges a same-IRI individual.
- The enum value `DEPRECATE_TARGET_ENTITY` actually deprecates the *source*. The name is misleading.
- The selection moves to the target.

Python: `sip.refactor.merge.merge_entities(root, sources, target, strategy) -> list[Change]`.

### 3.7 Move / copy / delete axioms (split ontology) (`MoveAxiomsWizard`, `MoveType`, kits)

Wizard steps: Select kit, then the kit's configuration panels, then Select action (COPY, MOVE or DELETE), then the target (existing ontology or new ontology: ID, physical location and format pages), then Finish.

`applyChanges()`:
```
target = None
if type in (COPY, MOVE):
   target = existing ontology by ID if manager contains it
            else a brand-new EditorKit (new window) and its fresh active ontology
for ax in kit.get_axioms(source_ontologies):          # source = ALL loaded ontologies by default
    for o in sources:
        if o.contains(ax):
            if type in (DELETE, MOVE): RemoveAxiom(o, ax)
            if type in (COPY, MOVE):   AddAxiom(target, ax)
target_editor_kit.model_manager.apply(changes)        # NB: in the "new ontology" case the removals are applied through
                                                      # the *new* kit's manager -> port: apply removes to the source manager
```
Kits (extension point `moveaxiomskit`, 4 implementations under `OWL/ui/ontology/wizard/move/`):

| Kit | Axiom selection |
|---|---|
| `byreference/MoveAxiomsByReferenceKit` "Axioms by reference" | For the selected entities: `referencing_axioms(e)` ∪ `annotation_assertions(subject=e.iri)` |
| `bydefinition/MoveAxiomsByDefinitionKit` "Axioms by definition" | For the selected entities: `o.getAxioms(e)` (defining axioms: for a class, SubClassOf with e on the left, EquivalentClasses, DisjointClasses, DisjointUnion; for properties, characteristics/domain/range/sub/equivalent/disjoint/inverse; for an individual, class and property assertions about it) ∪ declarations of e ∪ annotation assertions on e.iri |
| `bytype/MoveAxiomsByTypeKit` "Axioms by type" | The union of `o.getAxioms(type)` for the selected `AxiomType`s (the panel lists class, object property, data property and individual axiom types) |
| `byprofile/MoveAxiomsByProfileKit` "Axioms by profile" | All axioms of the sources, **minus** the axioms of every `OWLProfileViolation` reported by the chosen profile (OWL 2, OWL 2 DL or OWL 2 EL). This gives the in-profile fragment |

"Split ontology" in Python means: `move_axioms(kit_selection, MOVE, new_ontology)`, plus an `AddImport` from the source to the new ontology if the user wants a modular split. Protégé does not add that import automatically.

Python: `sip.refactor.move.MoveKit` protocol with `select(sources) -> set[Axiom]`, implementations `ByReference`, `ByDefinition`, `ByType`, `ByProfile`, and `move_axioms(selection, mode, sources, target) -> list[Change]`. A profile check needs an OWL 2 DL/EL/QL/RL profile checker; write a structural one over the axiom view.

### 3.8 Merge ontologies (`MergeOntologiesAction`, `MergeOntologiesWizard`, `OntologyMerger`)

Wizard pages: SelectOntologiesPage (multi-select), MergeTypePage ("Merge into new ontology", the default, or "Merge into existing ontology"). The new-ontology path continues to OntologyIDPanel, PhysicalLocationPanel and OntologyFormatPage, and the target is created with `createNewOntology(id, location)` and the chosen format. The existing-ontology path goes to SelectTargetOntologyPage.

```
def merge_ontologies(sources, target):
  for o in sources - {target}:
     Add every axiom of o to target                    # all axioms incl. declarations & annotations
     Add every ontology annotation of o to target
     if target.id not anonymous:
        for decl in o.imports:
           if manager.imported_ontology(decl) in sources: continue        # internal imports dropped
           if decl.iri != target.default_document_iri: AddImport(target, decl)
           else: warn "would import itself"
```
Invariants: the sources are **not removed or modified**. Prefixes and format are not merged (other than the format the user chose for a new target).

Python: `sip.refactor.merge_ontologies(sources, target) -> list[Change]`. With rdflib this is a graph union plus `owl:imports` handling. Skip the source's `owl:Ontology` header triples except annotations, and rewrite the ontology-annotation subject to the target IRI.

### 3.9 Convert to defined / primitive class

**Convert to defined class** (`ConvertToDefinedClassAction`):
```
ops = set(); ch = []
for o in active_ontologies:
   for ax in o.subclass_axioms_for_subclass(C): ch.append(Remove(o, ax)); ops.add(ax.super)
if not ops: return
eq = ops.pop() if len(ops)==1 else ObjectIntersectionOf(ops)
ch.append(Add(active_ontology, EquivalentClasses({C, eq})))       # always into the ACTIVE ontology
```
Edge cases:
- Axiom annotations on the removed SubClassOf axioms are lost.
- GCIs are untouched.
- Existing EquivalentClasses axioms are kept, so the class may end up with several definitions.

**Convert to primitive class** (`ConvertToPrimitiveClassAction`):
```
for o in active_ontologies:
  for ax in o.equivalent_classes_axioms(C):
     Remove(o, ax)
     for d in ax.operands - {C}:
        if d is ObjectIntersectionOf: for op in d.operands: Add(o, SubClassOf(C, op))     # same ontology as the source axiom
        else: Add(o, SubClassOf(C, d))
```
This also converts `C ≡ D` with a named D into `C ⊑ D`. For an n-ary equivalence `{C, D, E}`, it yields `C ⊑ D` and `C ⊑ E`, losing `D ≡ E`.

### 3.10 Split / amalgamate subclass axioms (OWLAPI utilities)

- **SplitSubClassAxioms** (`OWLAPI org.semanticweb.owlapi.util.SplitSubClassAxioms`, over the active ontologies): for each `SubClassOf(C, D)` where D is an `ObjectIntersectionOf` (conjuncts flattened recursively), if it yields more than one conjunct, remove the original and add `SubClassOf(C, Di)` for each conjunct, in the same ontology.
- **AmalgamateSubClassAxioms** (over **all loaded** ontologies): for each ontology and each named class C with more than one `SubClassOf(C, ·)` axiom in that ontology, remove them all and add `SubClassOf(C, ObjectIntersectionOf(all supers))`. Axiom annotations are not preserved. GCIs (anonymous LHS) are untouched.

Python: `sip.refactor.subclass.split_subclass_axioms(onts)` and `amalgamate_subclass_axioms(onts)`.

### 3.11 Split / amalgamate disjoint classes

**Split** (`SplitDisjointClassesAction`, active ontologies): every `DisjointClasses` with more than 2 operands becomes all C(n,2) pairwise `DisjointClasses(a, b)` in the same ontology. Annotations are dropped.

**Amalgamate** (`AmalgamateDisjointClassesAction.CliqueFinder`, per active ontology): a greedy clique merge.
```
edges = undirected graph: a~b for every pair co-occurring in any DisjointClasses axiom of this ontology
cliques = list(original operand sets)            # order = HashSet iteration order (non-deterministic!)
result = set(); skip = set()
for i, g in enumerate(cliques):
    if i in skip: continue
    g1 = set(g)
    for j in range(i+1, len(cliques)):
        if j not in skip and all(v in g1 or all(edge(v,u) for u in g1) for v in cliques[j]):
            g1 |= cliques[j]; skip.add(j)
    result.add(frozenset(g1))
for s in result: new = DisjointClasses(s); if new in old: old.remove(new) else Add(new)
for ax in old: Remove(ax)
```
Port note: sort the cliques deterministically, for example by (−size, sorted IRIs), to get reproducible output.

### 3.12 Make primitive siblings disjoint, covering axiom, all-different

- **Make primitive siblings disjoint** (`MakePrimitiveSiblingsDisjoint`):
  - siblings = the union of asserted `children(p)` for every asserted parent p of C (so C itself is included);
  - remove every sibling that is *defined* (has an `EquivalentClasses` axiom) in any active ontology;
  - if more than one remains, add `DisjointClasses(remaining)` to the active ontology.
  - There is no dedup against existing disjointness.
- **Hierarchy creation wizard variant** (`OWL/model/hierarchy/tabbed/MakeSiblingsDisjointChangeGenerator`): for each parent in the created parent→children map, take `children ∪ existing_children`, filter with `isNotDefinedIn(activeOntologies)`, and add one `DisjointClasses` if at least 2 remain. It works the same for properties with `DisjointObjectProperties` and `DisjointDataProperties`.
  - The tab-indented hierarchy itself is parsed by `TabIndentedHierarchyParser`.
  - `CreateHierarchyChangeGenerator` creates the entities and `SubClassOf(child, parent)` axioms, with no axiom when the parent is `owl:Thing`.
- **Add covering axiom** (`AddCoveringAxiomAction`): enabled iff the asserted class has more than one child. It adds `SubClassOf(C, ObjectUnionOf(children))` to the active ontology.
- **Make all individuals different** (`AllDifferentCreator`): all individuals in the signatures of the active ontologies, *including anonymous ones*, go into one `DifferentIndividuals(…)` in the active ontology.
- **Make instances different** (`MakeInstancesOfClassDifferentIndividualsAction`):
  - inds = the named individuals with an *asserted* `ClassAssertion(C, i)` in the active ontologies;
  - optionally, after a dialog, remove the existing `DifferentIndividuals` axioms in the active ontology whose individuals are all within inds;
  - add `DifferentIndividuals(inds)`.
- **Remove local disjoint axioms** (`RemoveLocalDisjointAxiomsAction`): for every asserted child D of C, remove every `DisjointClasses` axiom that contains D. The scope is the active ontology, or all active ontologies if the user answers Yes to "include imported".
- **Remove all disjoint axioms**: removes every `DisjointClasses` axiom in that scope. It is enabled only if the active ontology is mutable and some axiom exists.

### 3.13 Create closure axiom (`OWL/ui/framelist/CreateClosureAxiomAction`, `OWL/model/util/ClosureAxiomFactory`)

1. Select rows (SubClassOf or EquivalentClasses) in a class frame.
2. Collect the properties to close: the named object properties found in the top-level or intersection-nested `∃p.F`, `≥n p.F`, `=n p.F` and `p value a` of the selected axioms' superclass (or equivalent operands).
3. For each property p:
   ```
   fillers = set(); visited = set()
   visit(C):                                     # inherited: walk asserted supers and equivalents recursively
       if C in visited: return; visited.add(C)
       for e in asserted_superclasses(C, active_onts) ∪ asserted_equivalents(C, active_onts): visit_ce(e)
   visit_ce(ObjectIntersectionOf ops): for op: visit_ce(op)
   visit_ce(∃p.F):   if F != Thing: fillers.add(F)          # override in ClosureAxiomFactory (no flattening)
   visit_ce(≥n p.F | =n p.F) with n>0: if F != Thing: fillers.add(F)
   visit_ce(p value a): fillers.add(ObjectOneOf({a}))         # from ObjectSomeValuesFromFillerExtractor
   visit_ce(named D): visit(D)
   closure = None if not fillers else ∀p.(F if |fillers|==1 else ObjectUnionOf(fillers))
   if closure and SubClassOf(C, closure) not in active_ontology: Add(active_ontology, SubClassOf(C, closure))
   ```
Edge cases:
- The inheritance means the closure covers the fillers of superclasses too (this is OWL-tutorial behaviour).
- Inverse properties are ignored.
- Existing ∀ restrictions are not replaced; a new one is added.

### 3.14 Convert qualified min-1 to someValuesFrom (`ConvertMinOneToSomeValuesFromAction`)

For every logical axiom in the active ontologies, deep-copy it with a duplicator that rewrites `ObjectMinCardinality(1, p, F)` to `∃p.F`, and `DataMinCardinality(1, p, F)` (qualified) to `∃p.F`. If the copy differs from the original, remove the original and add the copy in the same ontology. Unqualified `≥1 p` (filler `Thing` or `rdfs:Literal`) is untouched.

Python: `sip.refactor.rewrite.map_class_expressions(fn)` is a generic CE-rewriter over the axiom view. Many refactorings can reuse it.

### 3.15 Convert property assertions on puns to annotations (`ConvertAssertionsOnPunsToAnnotations`)

```
for i in named individuals of all loaded onts where some ont has a CLASS with the same IRI (a class/individual pun):
   for o: for ax in o.data_property_assertions(subject=i):
        Remove(o, ax); Add(o, AnnotationAssertion(AnnotationProperty(ax.property.iri), i.iri, ax.literal)); props.add(ax.property)
   for o: Remove declarations of i (as individual) and ClassAssertion(·, i)
   for p in props (accumulated): for o: Remove Declaration(DataProperty p) and all axioms *defining* p (o.getAxioms(p))
apply
```
Only *data* property assertions are converted, despite the menu label. Object property assertions on puns are left in place.

### 3.16 Coerce data property values into range (OWLAPI `CoerceConstantsIntoDataPropertyRange`)

For each data property with a declared **datatype** range, rewrite every `DataPropertyAssertion(p, i, "lex"^^T)` whose datatype is not the range into `"lex"^^Range`. It also covers data has-value restrictions. All loaded ontologies are in scope. The lexical form is preserved and not validated, so the port should validate with `rdflib.Literal(lex, datatype=R)` and report ill-typed values.

### 3.17 Duplicate class (`DuplicateSelectedClassAction`)

1. Create a new class through the entity-creation panel. This applies the declaration changes and the new-entity annotation preferences.
2. Set `iriMap = {old: new}`.
3. For each active ontology, take every `o.getAxioms(C)` (defining axioms), keep the logical ones, and **exclude DisjointClasses**. Duplicate each with the IRI replacement and add it to the same ontology, or to the active ontology if "duplicate into active ontology" is set.
4. If "duplicate annotations" is set, copy each annotation assertion on C whose value is a **literal**. When rendering by label, skip the properties used for labels, and skip literals equal to the current display name.

### 3.18 Deprecate entity (`OWL/model/deprecation/EntityDeprecator`, profiles in `protege-desktop/src/main/resources/conf/deprecation/{basic,go,obi}.yaml`)

The change list is generated in this order. "Home ontology" is chosen by `HomeOntologySupplier`, typically the ontology where the entity is declared or else the active one.
1. **switchUsage**: if a replacement entity is given, for every *logical* axiom referencing E whose *subject* (`AxiomSubjectProvider`) is not E, remove the axiom and add a duplicate with E replaced by the replacement.
2. **removeLogicalDefinition** (profile flag), through `OWL/model/util/DefinitionExtractor`:
   - class: remove SubClassOf with E on the left and EquivalentClasses. For each `DisjointClasses` containing E, remove it and re-add the operands minus E if more than 1 remain. *Bug:* HasKey and DisjointUnion removals are created but **not added** to the list.
   - object property: remove sub/equivalent/characteristic/domain/range axioms, and disjoint-property axioms. *Bug:* the replacement disjoint axiom is added as a **RemoveAxiom** instead of an AddAxiom.
   - data properties, individuals, datatypes and annotation properties: nothing.
3. **removeAnnotationAssertions** (flag): remove the annotation assertions on E whose property is not in `preservedAnnotationAssertionPropertyIris`. Note that rdfs:label is not in the preserved list by default but is relabelled in step 7. Port: exclude rdfs:label explicitly, as the YAML comment says.
4. Add `owl:deprecated true` to home.
5. Add the textual reason (property `textualReasonAnnotationPropertyIri`, xsd:string) to home.
6. Add the deprecation code, if both the profile and the user supply one.
7. **relabel**: rewrite rdfs:label values to `prefix + " " + value`. If the prefix ends with `_` or `-`, no space is added.
8. Prefix the preserved annotation values the same way (`annotationValuePrefix`).
9. Add `replacedBy` (an IRI-valued annotation) to home if there is a replacement.
10. Add one annotation per alternate entity, using `alternateEntityAnnotationPropertyIri`.
11. **reparent**: optionally add `SubClassOf(E, deprecatedClassParent)` and the analogues for properties and individuals.

Python: `sip.refactor.deprecate.deprecate(entity, profile: DeprecationProfile, replacement=None, alternates=(), reason="", code=None)`. Load the profiles from YAML with the same keys.

---

## 4. Usage, find usage, delete

### 4.1 Usage view (`OWL/ui/usage/UsageByEntityTreeModel.java`, `UsageTree`, `UsagePanel`, `UsageFilter`, `UsagePreferences`; views `OWL*UsageViewComponent`; Tools > Usage... = `ShowUsageAction`, which opens the type-specific usage view in the bottom results pane)

**Collecting usages:**
```
usage_count = 0; by_entity = SortedMap(entity -> set(axioms)); other = set()
for o in active_ontologies:                       # imports closure by default selection strategy
   axs  = o.referencing_axioms(E)                 # E in signature
   axs += o.referencing_axioms(E.iri)             # IRI-based refs (annotation subjects/values, puns)
   axs += [ax for ax in o.annotation_assertions if ax.value == E.iri]
   for ax in axs: sort(ax)                         # visitor below, increments usage_count per "add"
tree: root "Found N uses of <E>", one node per *describing entity* (the axiom's subject), leaves = axioms, plus "Other"
```

**`AxiomSorter`**, which assigns each axiom to its *subject entity*:

| Axiom | Grouped under |
|---|---|
| SubClassOf | the named sub. An anonymous sub (GCI) goes to Other. With `filterNamedSubsSupers`, skip it when sub or sup == E |
| EquivalentClasses, DisjointClasses | each named operand. If none is named, Other. `filterDisjoints` suppresses the disjoint ones |
| DisjointUnion | its class (filterable) |
| ClassAssertion, Object/Data/Negative property assertions | the named subject individual |
| Same/DifferentIndividuals | each named individual. *Note: `filterDifferent` exists but is never checked* |
| property axioms (domain, range, characteristics, sub, equivalent, inverse, disjoint, chain → super property) | the property (the inverse is unwrapped) |
| Declaration | its entity |
| DatatypeDefinition | the datatype |
| AnnotationAssertion with an IRI subject | **every** entity type of that IRI found in any active ontology's signature (so puns get multiple groups) |
| SubAnnotationPropertyOf, AnnotationPropertyDomain, AnnotationPropertyRange | the property |
| HasKey, SWRL rules | **ignored** (not shown) |

`filterSelf` drops the group whose entity == E. Filters are persisted as booleans `filter.self`, `filter.class.subs`, `filter.class.disjoints` and `filter.individual.different`.

Known quirks you do not need to replicate:
- `usageCount` double counts an axiom found by both the entity search and the IRI search.
- `additionalAxioms` is never cleared on refresh.

Python:
```
def usage(entity, onts, filters) -> UsageReport(groups: dict[Entity, set[Axiom]], other: set[Axiom], count: int)
```
On an rdflib store a fast path is `graph.triples((E, None, None))` ∪ `(None, E, None)` ∪ `(None, None, E)`, then lift each triple to its enclosing axiom via `AxiomIndex.axiom_of_triple`. Deduplicate before counting.

### 4.2 Delete entity: what gets removed

There are two code paths.

**(a) Hierarchy views** (classes, object properties, data properties, annotation properties, individuals): `OWL/ui/action/OWLObjectHierarchyDeleter.performDeletion()`.
- Confirmation dialog: "Delete X? All references to X will be removed from the active ontologies".
- If asserted descendants exist, the dialog adds a radio choice: "Delete X only" or "Delete X and asserted descendant <plural>". The choice is remembered (prefs `delete.preferences`: `delete.confirm.always`, `delete.confirm.descendants`, `delete.descendants`), along with an "Always show this confirmation" checkbox.
- With descendants, the set to delete becomes `selected ∪ hierarchy.descendants(each)`.
- It then calls `OWLEntityDeleter.deleteEntities(set, modelManager)`.

**`OWL/model/util/OWLEntityDeleter`**, over **all loaded ontologies** (`getOntologies()`; the dialog text says "active", but the code uses all):
```
for o in all_loaded_ontologies:
   rs = ReferenceFinder.get_reference_set(entities, o)
   changes += [RemoveAxiom(o, ax) for ax in rs.axioms] + [RemoveOntologyAnnotation(o, a) for a in rs.ontology_annotations]
apply(changes)  # one batch
```

**`OWL/model/util/ReferenceFinder.getReferenceSet(entities, o)`:**
- axioms = ∪ `o.referencing_axioms(e, imports=EXCLUDED)`. Every axiom with e in its signature counts, *including declarations and axioms where e is nested deep in a class expression*.
- In addition, every `AnnotationAssertion` in o whose **subject** IRI ∈ entityIRIs, or whose **value** IRI ∈ entityIRIs.
- Ontology annotations whose value IRI ∈ entityIRIs, or whose **property** ∈ entities (deleting an annotation property also strips ontology annotations that use it).

Semantics to note:
- Deleting a class removes *entire* axioms that mention it. `A ⊑ ∃r.(B ⊓ C)` is removed completely when B is deleted; it is not rewritten. No "pruning" or replacement with ⊤ takes place.
- IRI-level matching means that deleting a class also removes annotation assertions about a same-IRI individual (pun), but the individual's logical axioms survive.
- Anonymous individuals are not cascaded.

**(b) `DeleteEntityAction`** (entity banner and other places): it first checks whether the entity has any non-declaration referencing axiom in any loaded ontology. If yes, it offers [Delete | View usage | Cancel]; if not, a plain yes/no confirmation. It then deletes the same way.

The legacy **`OWL/model/util/OWLObjectRemover`** has the same semantics per single ontology. It removes referencing axioms, annotation assertions with the IRI as subject, annotation assertions with the IRI as value, and ontology annotations with the IRI as value. For an annotation property it also removes ontology annotations using the property. For an anonymous individual it removes referencing axioms plus annotation assertions where the individual is subject or value.

Python:
```
def delete_entities(entities, onts=all_loaded, include_descendants=False, hierarchy=None) -> list[Change]
```
On rdflib:
1. For each entity IRI, find every axiom (via `AxiomIndex`) whose signature contains it. This includes bnode-structured class expressions: remove the *whole* axiom, i.e. all triples of its bnode tree, plus any reification or `owl:Axiom` annotation triples.
2. Remove `(E, ?, ?)` annotation triples and `(?, annProp, E)` annotation triples.
3. Remove ontology-header annotations with value E, or with property E.
4. **Never leave orphan bnode lists.** This is the main RDF-level invariant.

---

## 5. Extension architecture

### 5.1 Plugin platform

- Runtime: **Apache Felix OSGi**, configured in `protege-desktop/src/main/felix/conf/config.xml`, plus the **Eclipse Equinox extension registry** (`org.eclipse.equinox.registry`). Each bundle ships a `plugin.xml`. Bundles come from `bundles/` and `plugins/`, and the auto-update is `CORE/update/*`.
- `CORE/plugin/PluginUtilities` holds the `IExtensionRegistry` and the bundle context.
- `CORE/plugin/AbstractPluginLoader<E>(pluginId, extensionPointId)`. `getPlugins()` filters the extensions of `pluginId.extensionPointId` through a `PluginExtensionMatcher`, then calls `createInstance(IExtension)`, which wraps the extension in a "plugin descriptor".
  - `AbstractProtegePlugin.newInstance()` uses `ExtensionInstantiator`: it loads the `class` attribute from the contributing bundle and calls the no-arg constructor.
  - Properties are read with `PluginProperties.getParameterValue(ext, key, default)` from the `<name value=…/>` style child elements.
- `CORE/plugin/AbstractApplicationPluginLoader` is the same, with pluginId `org.protege.editor.core.application`.
- `EditorKitExtensionMatcher` matches extensions whose `editorKitId` parameter is `"any"` or equals the current kit's id (`OWLEditorKit.ID = org.protege.editor.owl.OWLEditorKitFactory`). This is how menu actions, tabs and views get scoped to an editor-kit type.
- Every plugin instance implements `ProtegePluginInstance { initialise(); dispose(); }`.
- Runtime hot-plug: for example, `OWLWorkspace.addReasonerListener` registers an `IRegistryEventListener` on the reasoner extension point and rebuilds the Reasoner menu when bundles are added.

### 5.2 Application lifecycle

`CORE/ProtegeApplication.java`, an OSGi `BundleActivator`:
1. `start(ctx)` binds logging and waits for `FrameworkEvent.STARTED`, then calls `reallyStart`.
2. `reallyStart` runs: `displayPlatform()`, then `initApplication()` (PluginUtilities.initialise(ctx), loadDefaults, look and feel, uncaught-exception handler, command-line URIs, recent editor kits), then the macOS hooks, then `ProtegeManager.getInstance().initialise(this)`, then `startApplication()`.
   - `startApplication()` calls `createAndSetupDefaultEditorKit(uri)` for each command-line URI, or once with no URI, and then runs `checkForUpdates()` (once a day, if enabled).
3. `stop(ctx)` disposes the bookmarks, saves and disposes the recent editor kits, then disposes PluginUtilities and ProtegeManager.

**`CORE/ProtegeManager`:**
- `initialise` loads the `EditorKitFactory` plugins and runs `setupRepositories()` (the `OntologyRepositoryFactory` plugins).
- `createAndSetupNewEditorKit(factory[, uri])` calls `factory.createEditorKit()`, then `handleNewRequest()` or `handleLoadFrom(uri)`. On success it calls `EditorKitManager.addEditorKit` (one window per kit); on failure it disposes the kit.

**`EditorKitFactory`** (`getId`, `canLoad(URI)`, `createEditorKit()`, `isValidDescriptor`), extension point `EditorKitFactory`. Only `OWLEditorKitFactory` exists.

**`EditorKit`**: `getId`, `getWorkspace`, `getModelManager`, a `put/get(key, Disposable)` service locator, `handleNewRequest`, `handleLoadRequest`, `handleLoadFrom(uri)`, `handleLoadRecentRequest`, `handleSave`, `handleSaveAs`, `hasModifiedDocument`.

**`OWLEditorKit` constructor order** (`OWL/OWLEditorKit.java`):
1. `new OWLModelManagerImpl()`, which creates the `OWLReasonerManagerImpl` (loads reasoner plugins and the default reasoner id);
2. `new OWLWorkspace().setup(this)`;
3. `Initializers.loadEditorKitHooks(this)`: for each `EditorKitHook` plugin, `newInstance().initialise()`, then `editorKit.put(pluginId, hook)`. This is where `InconsistentOntologyManager` registers itself;
4. `SearchManagerSelector`;
5. the ontology change listener;
6. `ExplanationManager`;
7. the missing-import and load-error handlers;
8. the IO listener plugins;
9. registering the kit as an OSGi service;
10. `workspace.initialise()`, which builds the menus from `EditorKitMenuAction`, the tabs from `WorkspaceTab`, the views from `ViewComponent` and the toolbar from `ToolBarAction`, plus the reasoner menu and status bar.

**`CORE/ui/workspace/Workspace`** (abstract `JComponent`): `setup(editorKit)`, `initialise()`, `getViewManager()`, `showResultsView(id, replace, BOTTOM|LEFT)`, `getStatusArea()`, `save()` (the layout), `dispose()`. `OWLWorkspace` adds the selection model, the reasoner status, the active-ontology combo and the entity display providers.

### 5.3 All extension points (24 declared)

Fully qualified as `<bundle>.<id>`: core is `org.protege.editor.core.application`, OWL is `org.protege.editor.owl`.

| # | Bundle | Id | Purpose / instance type |
|---|---|---|---|
| 1 | core | `EditorKitFactory` | Editor-kit factories, i.e. document types (`OWLEditorKitFactory`) |
| 2 | core | `WorkspaceTab` | Tabs (id, label, index, default layout XML); 7 contributed |
| 3 | core | `ViewComponent` | Dockable views (label, category, navigates, class); 51 contributed |
| 4 | core | `ViewAction` | Actions on a view's own toolbar or popup (`ViewActionPluginJPFImpl`) |
| 5 | core | `EditorKitMenuAction` | Menu bar and context-menu items. `path` = `parentId/SlotX-Y`; bracketed parents such as `[AssertedClassHierarchy]` or `[EntityBanner]` are popup menus. Attributes: `name`, `toolTip`, `accelerator`, `editorKitId`, `class` (`ProtegeAction`); a menu without a class is a submenu; 127 contributed |
| 6 | core | `ToolBarAction` | Main toolbar actions |
| 7 | core | `preferencespanel` | Panels in File > Preferences (11 contributed) |
| 8 | core | `explanationpreferencespanel` | Sub-panels in the "Explanations" preferences tab |
| 9 | core | `EditorKitHook` | Objects created per editor kit before the UI (`EditorKitHook.initialise`), stored with `kit.put(id, …)` |
| 10 | core | `OntologyRepositoryFactory` | Remote ontology repositories (TONES repository contributed) |
| 11 | core | `OntologyLoader` | Custom loaders for documents |
| 12 | core | `OtherStartupActions` | Extra actions on the welcome dialog (Check for plugins, Reset preferences) |
| 13 | owl | `inference_reasonerfactory` | **Reasoners** (`ProtegeOWLReasonerInfo`; param `name`) |
| 14 | owl | `inference_preferences` | Tabs in Reasoner preferences ("Displayed inferences", "Initialization") |
| 15 | owl | `explanation` | **Explanation services** (`ExplanationService`) |
| 16 | owl | `inconsistentOntologyExplanation` | **Inconsistent-ontology explainers** (`InconsistentOntologyPluginInstance`) |
| 17 | owl | `ui_renderer_entitycolorprovider` | Entity colour providers (tree and renderer colours) |
| 18 | owl | `moveaxiomskit` | Axiom-selection kits for the Copy/move/delete wizard (4 contributed) |
| 19 | owl | `io_listener` | Before and after load/save hooks (`IOListener`) |
| 20 | owl | `ui_editor_description` | Class-expression editor tabs (expression editor, class hierarchy, object restriction creator, data restriction creator) |
| 21 | owl | `repository` | Catalog / ontology library entry managers (FolderGroupManager, ImportByNameManager, UriEntryManager) |
| 22 | owl | `entity_renderer` | Entity renderers: short name, prefixed name, annotation value, prefixed annotation value |
| 23 | owl | `ExtraReasonerMenuAction` | Extra items in the Reasoner menu (loaded by `OWLWorkspace.ExtraReasonerMenuActionPluginLoader`; params name, toolTip, accelerator) |
| 24 | owl | `searchmanager` | Search backends (DefaultSearchManager) |

There is no separate plugin point for frames or frame sections, for `OWLEntityDisplayProvider`, or for hierarchy providers. Those are wired in code.

**Python translation of the plugin system** (`sip.plugins`):
- Use `importlib.metadata.entry_points(group="sip.<point>")` with the same point names: `sip.reasoner`, `sip.explanation`, `sip.inconsistent_ontology_explanation`, `sip.move_axioms_kit`, `sip.io_listener`, `sip.entity_renderer`, `sip.search_manager`, `sip.editor_hook`, `sip.menu_action`, `sip.view`, `sip.preferences_panel`, `sip.ontology_repository`.
- A `PluginDescriptor(id, name, params: dict, factory)` mirrors `AbstractProtegePlugin`.
- A `PluginLoader(point, matcher)` mirrors `AbstractPluginLoader`.
- `editor_kit_id` matching mirrors `EditorKitExtensionMatcher`.
- Lifecycle protocol: `initialise()` / `dispose()`.
- Hot reload: a `PluginRegistry.on_added(point, callback)`.

### 5.4 Preferences mechanism

`CORE/prefs/PreferencesManager` (singleton) is backed by `JavaBackedPreferencesManagerImpl`, which uses `java.util.prefs`:
- the node path is `userRoot/PROTEGE_PREFERENCES/<setId>/<preferencesId>`;
- `getApplicationPreferences(Class|id)` uses `setId = "application_preferences"` and `prefsId = class name`;
- `getPreferencesForSet(setId, Class|id)` is the general form;
- the `Preferences` API offers typed getters and setters: `getString`, `getBoolean`, `getInt`, `getStringList` (a list stored as a child node);
- `resetPreferencesToFactorySettings()` removes the root node, and is reachable from the startup action "Reset Protege preferences…".

Sets used in this scope: `INFERENCE_PREFS_SET` (reasoner and displayed/precompute), `EXPLANATION_PREFS_SET`, `application_preferences/RenameEntityPanel` (`AUTO_RENAME_PUNS`), `delete.preferences`, `DuplicateSelectedClassAction` (`DUPLICATE_ANNOTATIONS_KEY`, `DUPLICATE_INTO_ACTIVE_ONTOLOGY_KEY`), and the usage filters.

Python: `sip.prefs.Preferences(set_id, prefs_id)` backed by a TOML or JSON file, or a DB table keyed `(set_id, prefs_id, key)`. Typed accessors, with `reset()`.

---

## 6. Import / export

### 6.1 Formats

`OWL/ui/OntologyFormatPanel.java` offers, in combo order: RDF/XML (the default), Turtle, OWL/XML, OWL Functional Syntax, Manchester OWL Syntax, OBO, LaTeX (export only) and JSON-LD.
- Choosing Manchester asks for confirmation: "can lose information such as GCI's and annotations of undeclared entities".
- `OWL/ui/Extensions.java` maps extensions to formats: `.rdf`/`.xml` RDF/XML; `.ttl`/`.turtle` Turtle; `.owx`/`.xml`/`.owl` OWL/XML; `.ofn` Functional; `.omn` Manchester; `.obo` OBO; `.tex` LaTeX; `.jsonld` JSON-LD; N-Triples. Unknown formats default to `.owl`.
- `OWL/model/DocumentFormatMapper` maps RioTurtle to the native Turtle format and keeps the prefixes.
- Parsing is done by the OWLAPI, which auto-detects all of these plus the Rio formats.
- OBO import and export use the OWLAPI OBO parser, with `OboUtilities` for OBO-ID rendering and copying.

Python with rdflib covers RDF/XML, Turtle, N-Triples, N-Quads, TriG, JSON-LD and N3 natively. OWL/XML, Functional and Manchester need custom writers over the axiom view; Functional syntax is the easiest and most valuable to write first. For OBO, use `fastobo`/`pronto` or a converter, or treat it as out of scope. LaTeX output is a simple Functional-like pretty-printer. Keep the Manchester warning.

### 6.2 Export inferred axioms as ontology (`OWL/ui/action/export/inferred/*`)

**Guard:** the reasoner status must be INITIALIZED or OUT_OF_SYNC. Otherwise the action shows the status-specific warning. An inconsistent ontology is refused.

**Wizard pages:**
1. Select axioms (`ExportInferredOntologyPanel`): one checkbox per generator.
2. "Include annotations" and "Include asserted logical axioms" (both unchecked by default).
3. Ontology ID (`ExportInferredOntologyIDPanel`).
4. Physical location.
5. Format.

**The 12 generators:**

| Generator (OWLAPI unless noted) | Default | InferenceType precomputed |
|---|---|---|
| InferredSubClassAxiomGenerator | **on** | CLASS_HIERARCHY |
| InferredEquivalentClassAxiomGenerator | **on** | CLASS_HIERARCHY |
| InferredSubObjectPropertyAxiomGenerator | **on** | OBJECT_PROPERTY_HIERARCHY |
| InferredSubDataPropertyAxiomGenerator | **on** | DATA_PROPERTY_HIERARCHY |
| InferredEquivalentObjectPropertyAxiomGenerator | **on** | OBJECT_PROPERTY_HIERARCHY |
| InferredEquivalentDataPropertiesAxiomGenerator | **on** | DATA_PROPERTY_HIERARCHY |
| InferredObjectPropertyCharacteristicAxiomGenerator | off | (none) |
| InferredDataPropertyCharacteristicAxiomGenerator | off | (none) |
| InferredInverseObjectPropertiesAxiomGenerator | off | OBJECT_PROPERTY_HIERARCHY |
| InferredClassAssertionAxiomGenerator | off | CLASS_ASSERTIONS |
| InferredPropertyAssertionGenerator | off, "expensive" | OBJECT_PROPERTY_ASSERTIONS, DATA_PROPERTY_ASSERTIONS |
| **`InferredDisjointClassesAxiomGenerator`** (in-repo) | off, "expensive" | DISJOINT_CLASSES |

Each generator is wrapped in `MonitoredInferredAxiomGenerator`, which reports progress per generator.

**Export task** (runs on a background thread, with a cancellable `ProgressMonitor`):
```
precompute = union(InferenceType of each selected generator)
R = current reasoner; if R.pending_changes(): R.flush()
todo = (precompute ∩ R.precomputable) − {t | R.is_precomputed(t)}; R.precompute(todo)
out = new OWLOntology(new_id) in a fresh manager
InferredOntologyGenerator(R, generators).fill(out)      # for each generator: for each entity in signature(root imports closure) add axioms
remove from out every axiom that is vacuous or inverse-squared (§1.7)
if include_annotations:   for o in R.root.imports_closure: add o's ontology annotations and ALL AnnotationAssertion axioms
if include_asserted:      for o in closure: for ax in o.logical_axioms:
                              if ax is annotated and out contains ax.without_annotations: remove the bare copy
                              add ax
save(out, format, location)
```

**Generator semantics** (OWLAPI; the port needs them). For each entity of the given type in the closure signature:
- SubClass: if C is satisfiable, `SubClassOf(C, D)` for each direct super D (named, flattened); otherwise `SubClassOf(C, owl:Nothing)`.
- EquivalentClass: if `|equivalents(C)| > 1`, emit `EquivalentClasses(node)`. Unsatisfiable classes yield `EquivalentClasses(C, owl:Nothing)`.
- SubObjectProperty / SubDataProperty: direct named super-properties.
- EquivalentObject/DataProperty: an equivalence node with more than one member.
- InverseObjectProperties: `InverseObjectProperties(p, q)` for each named q in `inverse_object_properties(p)`.
- ObjectPropertyCharacteristic: for each p, entailment tests for Functional, InverseFunctional, Symmetric, Asymmetric, Reflexive, Irreflexive and Transitive. Each is emitted if `R.is_entailed(<characteristic>(p))` (or the equivalent satisfiability test).
- DataPropertyCharacteristic: Functional.
- ClassAssertion: for each class C, `ClassAssertion(C, i)` for i in `instances(C, direct=False)`.
- PropertyAssertion: for each named individual i and each object property p, `ObjectPropertyAssertion(p, i, j)` for `j ∈ object_property_values(i, p)`. Likewise for data properties and their literals.
- DisjointClasses (Protégé's own generator): `DisjointClasses(C, D)` for each `D ∈ R.disjoint_classes(C).flatten()`. This produces symmetric duplicates, which set semantics fold, and it includes `owl:Nothing`, which the vacuous filter removes.

Python: `sip.reasoning.export.export_inferred(reasoner, generators: list[Generator], new_iri, include_annotations=False, include_asserted=False) -> Graph`, with `Generator` protocol `generate(reasoner, entities) -> Iterable[Axiom]` and one class per row above. With owlrl, materialise once and then select the generators' axioms from the closure, keeping only direct relations through the transitive reduction.

### 6.3 Merge ontologies wizard

See §3.8. Wizard class: `OWL/ui/ontology/wizard/merge/MergeOntologiesWizard` (pages SelectOntologies, MergeType, OntologyID, PhysicalLocation, OntologyFormat, SelectTarget). Its title is the copy-pasted "Create ontology wizard".

### 6.4 Gather ontologies (`OWL/ui/action/GatherOntologiesAction`)

"Copy ontology/closure to a folder": for each ontology chosen in `GatherOntologiesPanel` (typically the imports closure), save it to `<folder>/<original file name>`. The original name falls back to a UUID plus `.owl` when the document IRI has no path. The format is the chosen one (the panel offers RDF/XML, OWL/XML or Functional) or else the ontology's current format (default RDF/XML). One `OntologySaver` batch is used. Python: `sip.io.gather(onts, folder, fmt=None)`.

### 6.5 Other in-scope I/O notes

- Change ontology IRI also rewrites the importers' `owl:imports` (§3.4).
- **Imports wizard** (`OWL/ui/ontology/imports/wizard/*`): import from a local file, a URL, an already-loaded ontology or the library. It anticipates the ontology ID, then adds `AddImport` (plus a catalog entry, `OWL/model/library/*`).
- Missing-import resolution (`OWL/ui/ontology/imports/missing/*`) asks the user for a file and optionally copies it into the root ontology folder.

---

## 7. Proposed Python package layout (summary)

```
sip/
  plugins/        registry.py (entry points, descriptors, editor-kit matcher), lifecycle.py
  prefs/          store.py (set_id/prefs_id/key), reasoner_prefs.py, explanation_prefs.py
  reasoning/      status.py (ReasonerStatus), manager.py (ReasonerManager + ClassificationRunner),
                  reasoners/{noop.py, owlrl_reasoner.py, rdfs_reasoner.py}, prefs.py (OptionalInferenceTask),
                  hierarchy.py (Inferred* providers), inferred_rows.py, vacuous.py, export.py (generators)
  explain/        service.py (ExplanationService/Manager), entailment.py (OwlRlEntailmentChecker + cache),
                  modules.py (bot/star locality), blackbox.py (expand/contract), hst.py (Reiter HST),
                  laconic.py (optional), format.py, inconsistency.py
  refactor/       rename.py (single/bulk/puns), ontology_iri.py, ids.py (names->ids), merge_entities.py,
                  merge_ontologies.py, move.py (+ kits), class_defs.py (defined/primitive), subclass.py (split/amalgamate),
                  disjoint.py (split/amalgamate/siblings/remove), closure.py, cardinality.py (min1->some),
                  puns.py, coerce.py, duplicate.py, deprecate.py (+ YAML profiles), individuals.py (all-different)
  usage/          usage.py (UsageReport + AxiomSorter), delete.py (ReferenceFinder + EntityDeleter)
  io/             formats.py, gather.py, imports.py
```
Shared primitives are required by everything above:
- `AxiomIndex` (triples to axioms and back, with `referencing_axioms(entity)`, `axioms_for_subject`, `annotation_assertions(subject|value)`, `signature`);
- `Change` types and `ModelManager.apply_changes`;
- `ClassExpressionRewriter` (the duplicator equivalent: `map_entities`, `map_iris`, `map_ce`).

## 8. Bugs and quirks found (decide whether to replicate)

1. `ClassDefinitionExtractor.generateChangesToRemoveDefinitionFromOntology`: the HasKey and DisjointUnion `RemoveAxiom` objects are created but never added, so a deprecation does not remove them.
2. `ObjectPropertyDefinitionExtractor.getChangesToRemoveDefinition`: the residual DisjointObjectProperties axiom is added as a `RemoveAxiom` instead of an `AddAxiom`.
3. `EntityIRIUpdaterOntologyChangeStrategy`: a pure string-prefix match without a separator check, so it over-captures.
4. `MoveAxiomsWizard.applyChanges`: for a MOVE into a new editor kit, all changes, including the removals from the source, go through the new kit's model manager.
5. `MergeEntitiesChangeListGenerator.replaceLabels` removes `AnnotationAssertion(target, label)`. If the target already had an identical label, that label is lost too. `MergeStrategy.DEPRECATE_TARGET_ENTITY` actually deprecates the sources.
6. `UsageByEntityTreeModel`: `UsageFilter.filterDifferent` is unused; usages are double counted when the entity search and the IRI search overlap; `additionalAxioms` is never cleared; HasKey and SWRL usages are hidden.
7. `OWLEntityDeleter` scopes to *all loaded* ontologies, while the dialog text says "active ontologies".
8. `AmalgamateDisjointClassesAction` output depends on HashSet order, so it is non-deterministic.
9. `ConvertAssertionsOnPunsToAnnotations` handles only data property assertions.
10. `OptionalInferenceTask.SHOW_INFERED_CLASS_MEMBERS` is misspelled, and the persisted key uses the misspelling. Keep it for compatibility if you import Protégé preferences.
11. `ReasonerFilter` has no in-repo producer, and filters are cleared after every classification run.
