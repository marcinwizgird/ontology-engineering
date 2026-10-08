> **Working notes — source-level reverse engineering.** Produced on 2026-10-04 by reading the source checkouts listed in [`../REVERSE_ENGINEERING.md`](../REVERSE_ENGINEERING.md) §1. Paths are relative to those checkouts. These notes are evidence for the port, not normative design; where the port deliberately deviates, `REVERSE_ENGINEERING.md` says so.

# Protégé Desktop: OWL editor core, reverse-engineered for a Python/rdflib port

**Source:** `refs/protege` at commit `bf03cccc` (Sep 2026). It depends on OWLAPI **4.5.29** (`pom.xml`: `owlapi-osgidistribution`) and `org.protege.xmlcatalog`.
**Module roots:** `protege-editor-core/` (generic workspace/plugin framework) and `protege-editor-owl/` (everything OWL).
Unless stated otherwise, paths are relative to `protege-editor-owl/src/main/java/`, abbreviated as `o.p.e.o` = `org/protege/editor/owl`.

**Scope:** model manager, I/O and catalog, change and undo, hierarchies, rendering, find/search, Manchester parsing and autocomplete, entity creation, metrics, frames, workspace/plugin.xml. Reasoning, refactoring and explanation are out of scope.

**Conventions for the Python proposal.** The package is `sip.owlcore` ("Semantic Intelligence Platform").
- Storage is one `rdflib.Graph` per ontology document, held in a `Dataset` keyed by ontology IRI.
- An `AxiomView` layer extracts structural OWL 2 axioms from the triples, following the OWL 2 RDF mapping, and serialises them back. It keeps these indexes:
  - `by_type`: `AxiomType -> set[Axiom]`
  - `referencing`: `entity -> set[Axiom]`, the equivalent of OWLAPI `getReferencingAxioms`
  - `by_subject`: the equivalent of `getAxioms(OWLClass)`, i.e. axioms "about" the class
  - `signature`: `IRI -> set[EntityType]`
- Axioms are frozen dataclasses, so they are hashable and can be stored in sets, as OWLAPI does.

---

## 0. Architectural overview

```
OWLEditorKit ──owns──> OWLModelManagerImpl (ModelManager) ──owns──> OWLOntologyManager (OWLAPI, concurrent)
   │                       ├─ HistoryManagerImpl (undo/redo)          ├─ ontologies, formats, documentIRIs
   │                       ├─ OntologyCatalogManager (XML catalogs)   └─ change listeners (fan-out)
   │                       ├─ UserResolvedIRIMapper / MissingImportHandler
   │                       ├─ OWLHierarchyManagerImpl (lazy providers)
   │                       ├─ OWLModelManagerEntityRenderer (plugin)  + OWLEntityRenderingCacheImpl (name→entity index)
   │                       ├─ OWLObjectRendererImpl (Manchester)      + OWLObjectRenderingCache (LRU 50)
   │                       ├─ OWLEntityFinderImpl (wildcard/regex over rendering index)
   │                       ├─ ManchesterOWLExpressionCheckerFactory (parsers)
   │                       ├─ CustomOWLEntityFactory (IRI generation + label/metadata axioms)
   │                       ├─ DeprecationCache, ActiveOntologyIdRangesPolicyManager
   │                       └─ OntologySelectionStrategy (active set = imports closure by default)
   └─ OWLWorkspace (tabs/views from plugin.xml, selection model, frames)
```

Change flow:
1. A UI component builds a `List<OWLOntologyChange>`.
2. `OWLModelManager.applyChanges(list)` optionally rewrites it through the `AnonymousDefinedClassManager`, then runs `ChangeListMinimizer`, then calls `OWLOntologyManager.applyChanges`.
3. OWLAPI fires `ontologiesChanged(changes)` to every listener, in registration order.

`OWLModelManagerImpl` is registered first, in its constructor. It updates the deprecation cache, logs the changes to the history and maintains the dirty set. After it, the entity rendering cache, entity renderer, hierarchy providers, frame sections, metrics, search and so on update themselves.

---

## 1. OWLModelManager / OWLModelManagerImpl

**Files**

| Class | Path |
|---|---|
| `OWLModelManager` (interface, ~70 methods) | `o.p.e.o/model/OWLModelManager.java` |
| `OWLModelManagerImpl` (962 lines; `extends AbstractModelManager implements OWLModelManager, OWLEntityRendererListener, OWLOntologyChangeListener, OWLOntologyLoaderListener, IOListenerManager`) | `o.p.e.o/model/OWLModelManagerImpl.java` |
| Loading | `model/io/OntologyLoader.java` |
| Saving | `model/io/OntologySaver.java` |
| Reload | `model/OntologyReloader.java` |
| IRI mappers | `model/io/UserResolvedIRIMapper.java`, `model/io/WebConnectionIRIMapper.java`, `model/io/AutoMappedRepositoryIRIMapper.java`, `model/MissingImportHandlerImpl.java` |
| Catalog | `model/library/OntologyCatalogManager.java`, `model/library/folder/FolderGroupManager.java`, `model/library/folder/XmlBaseAlgorithm.java`, `model/library/folder/OntologyNameAlgorithm.java` (used by `ImportByNameManager`), `model/library/UriEntryManager.java` |
| Active-set strategies (4) | `model/selection/ontologies/{ImportsClosure,Active,AllLoaded,VisibilityManager}OntologySelectionStrategy.java` |
| Format fix-up | `model/DocumentFormatMapper.java`, `model/DocumentFormatUpdater.java` (maps `RioTurtleDocumentFormat` to `TurtleDocumentFormat` and copies the prefixes) |
| Save formats | `ui/OntologyFormatPanel.java` |
| Save orchestration | `OWLEditorKit.handleSave()` / `handleSaveAs()` |

### 1.1 State held by the manager

- `manager: OWLOntologyManager`, created by `OWLManager.createConcurrentOWLOntologyManager()`
- `activeOntology: OWLOntology`
- `activeOntologies: Set<OWLOntology>`, a cache of `activeOntologiesStrategy.getOntologies()`
- `activeOntologiesStrategy`, default `ImportsClosureOntologySelectionStrategy`, which returns `manager.getImportsClosure(active)`
- `dirtyOntologies: Set<OWLOntologyID>`. This is keyed by ID, not by object, which is why a `SetOntologyID` change needs special handling.
- `ontologyCatalogManager`, `userResolvedIRIMapper(new MissingImportHandlerImpl())`. The UI replaces the handler with one that prompts the user.
- Listener lists: `modelManagerChangeListeners` (`OWLModelManagerListener`) and `ioListeners` (`IOListener`: beforeLoad, afterLoad, beforeSave, afterSave).
- Caches: `owlEntityRenderingCache`, `owlObjectRenderingCache` (LRU of 50), `deprecationCache`.
- A key/value store inherited from `AbstractModelManager` (`get(key)` / `put(key, obj)`). It holds lazy singletons: `OWLHierarchyManager`, `OWLObjectComparator`, `OWLExpressionUserCache`, `OntologySourcesManager`, and the `AnonymousDefinedClassManager` if one is installed.

### 1.2 Loading algorithm

The entry point is `loadOntologyFromPhysicalURI(URI)`, which delegates to `OntologyLoader.loadOntology()`. OWLAPI parses on a single background thread while the EDT shows a progress dialog.

```
load(document_uri):
  userResolvedIRIMapper.reset()
  loadingManager = fresh concurrent manager (addAxiom intercepted -> memory check)
  loadingManager.iriMappers = [userResolvedIRIMapper, WebConnectionIRIMapper(), AutoMappedRepositoryIRIMapper(catalogMgr, document_uri)]
  config.missingImportHandlingStrategy = SILENT              # missing imports don't abort the load
  root = loadingManager.loadOntologyFromOntologyDocument(IRIDocumentSource(document_uri), config)
  already = {}
  for o in loadingManager.ontologies:                        # root + whole imports closure
      if o not in modelManager.ontologies:
          fireBeforeLoad(o.id, document_uri)
          mainManager.copyOntology(o, OntologyCopy.MOVE)     # moves axioms, format, doc IRI
          fireAfterLoad(o.id, document_uri)
      else: already.add(o)                                   # NOT replaced -> warning dialog
  setActiveOntology(root); fireEvent(ONTOLOGY_LOADED)
  if root.id not anonymous: mainManager.iriMappers.add(SimpleIRIMapper(root.defaultDocumentIRI, document_uri))
  for o in root.importsClosure: DocumentFormatUpdater.updateFormat(o)   # RioTurtle→Turtle
  later (EDT): idRangesPolicyManager.reload(); refreshRenderer()
```

**IRI mapper resolution** (each mapper is `getDocumentIRI(ontologyIRI) -> IRI | null`).

1. `AutoMappedRepositoryIRIMapper`
   - If the root document is a `file:` URI, it first calls `catalogMgr.addFolder(parentDir(root))`.
   - **Side effect:** `addFolder` calls `ensureCatalogExists`, which **creates `catalog-v001.xml` in that folder** if none exists, auto-populated by the entry managers.
   - It then returns `catalogMgr.getRedirectForUri(iri)`. That is the first redirect found across all local catalogs, resolved with `CatalogUtilities.getRedirect` (OASIS XML Catalog semantics: `uri name=` exact entries, `rewriteURI` prefixes, `group` recursion, `nextCatalog`; implemented in the external `org.protege.xmlcatalog` library, not in this repo).
2. `WebConnectionIRIMapper`
   - For `http`/`https` it sends a `HEAD` request (20 s timeout, gzip accepted). On 200, 301, 302 or 303 it returns the IRI unchanged; otherwise it returns null.
   - For other schemes (for example `file:`) it opens a stream and returns the IRI if that succeeds.
3. `UserResolvedIRIMapper`
   - Memoises answers in a `Map<IRI, URI>` and asks the `MissingImportHandler` otherwise.
   - The default `MissingImportHandlerImpl` returns the IRI itself. In the GUI it is replaced by a dialog that lets the user pick a file; the pick is recorded in the catalog via `OntologyCatalogManager.addUserImportResolution`, which inserts a `UriEntry` with id "User Entered Import Resolution" at index 0 and saves the catalog.

> **Effective consult order.** OWLAPI's `PriorityCollection` puts mappers added later in front, so the catalog is consulted first, then the web check, then the user handler. Protégé relies on this. The repo does not state it explicitly; it is implied by `MissingImportHandlerImpl` always returning non-null, so the user handler must come last. The port should implement an explicit ordered chain: `[catalog, web, user_fallback]`.

**Catalog auto-population** (`FolderGroupManager`)
- It is a `GroupEntry` whose id is a property string, `"Folder Repository" + directory=…, recursive=true, AutoUpdate=…, version=2`.
- `update(entry)`:
  1. Retain existing `uri` entries whose `Timestamp` is at least the file's `lastModified`.
  2. Recursively scan the folder: skip hidden files, keep only files with OWL extensions (`UIHelper.OWL_EXTENSIONS`), and stop after 1000 non-ontology files.
  3. For each new or changed file, run each `Algorithm`. `XmlBaseAlgorithm` reads the **`xml:base`** of the first element with SAX. `ImportByNameManager` uses `OntologyNameAlgorithm`, which loads the file and suggests its **ontology IRI and version IRI**.
  4. If a web location was already found in a parent directory, the entry is written with a "shadowed" scheme prefix instead (`CatalogEntryManager.SHADOWED_SCHEME`), so it is ignored.
- A corrupt catalog is renamed to `catalog-backup-N.xml` and rebuilt.
- The repo has 3 catalog entry managers, all registered against the `repository` extension point: `FolderGroupManager`, `ImportByNameManager`, `UriEntryManager`.

### 1.3 Active ontology

`setActiveOntology(ont, force)`:

```
if not force and ont == current: return
activeOntology = ont
activeOntologies = strategy.getOntologies()
deprecationCache.rebuild(activeOntologies)
entityRenderer.ontologiesChanged(); entityRenderingCache.rebuild(); objectRenderingCache.clear()
fireEvent(ACTIVE_ONTOLOGY_CHANGED)       # → OWLHierarchyManagerImpl.rebuildAsNecessary() → provider.setOntologies(activeOntologies)
```

Strategies (4):

| Strategy | Display name | Returns |
|---|---|---|
| ImportsClosure (default) | "Show the imports closure of the active ontology" | the imports closure of the active ontology |
| Active | "Show only the active ontology" | `{active}` |
| AllLoaded | "Show all loaded ontologies" | every loaded ontology |
| VisibilityManager | "Show user selected ontologies..." | the user's selection |

Changing the strategy calls `setActiveOntology(active, true)` and then fires `ONTOLOGY_VISIBILITY_CHANGED`.

Further rules:
- `removeOntology(ont)` refuses to remove the active ontology or the only loaded one. Otherwise it removes `ont` from the active and dirty sets, removes it from the manager, and calls `setActiveOntology(active, force=true)`.
- `createNewOntology(id, physicalURI)` adds a `SimpleIRIMapper(defaultDocIRI → physicalURI)`, creates the ontology, makes it active, calls `catalogMgr.addFolder(parent)` if that directory exists, and fires `ONTOLOGY_CREATED`.
- `isMutable(ontology)` always returns `true`. This is deliberate, per the source comment: ontologies loaded from the web are also editable.

### 1.4 Dirty tracking

The relevant code is `ontologiesChanged(changes)` (the OWLAPI listener):

```
if empty: return
deprecationCache.handleOntologyChanges(changes, activeOntologies)
historyManager.logChanges(changes)
refreshActive = False
for ch in changes:
    if ch is SetOntologyID: dirty.remove(ch.originalOntologyID)
    dirty.add(ch.ontology.ontologyID)
    if ch.isImportChange(): refreshActive = True       # AddImport / RemoveImport
if refreshActive: setActiveOntology(active, force=True)   # imports closure may have changed
```

- `setClean(o)` is called by `save()` and `reload()`.
- `getDirtyOntologies()` lazily drops IDs that no longer exist in the manager.
- `isChangedEntity(e)` always returns `false`. It is a stub.

### 1.5 Saving

`save(ont)`:

```
documentURI = manager.getOntologyDocumentIRI(ont)
fireBeforeSave
format = manager.getOntologyFormat(ont) or RDFXMLDocumentFormat()
# NOTE: addMissingTypes deliberately NOT used (would produce OWL Full / corrupt data)
OntologySaver: if scheme == file: write to temp file then FileUtils.copyFile(temp, dest)  (atomic-ish), else ontology.saveOntology(format, iri)
manager.setOntologyDocumentIRI(ont, documentIRI)
dirty.remove(ont.id); fireEvent(ONTOLOGY_SAVED); fireAfterSave
```

`OWLEditorKit.handleSave()`:
1. Ontologies whose document IRI is not `file:`, including the active ontology when it has a non-file IRI, go through **Save As**.
2. Every other dirty ontology is saved in place.
3. Errors are collected per ontology and shown together at the end.

`handleSaveAs(ont)`:
1. Show the format dialog.
2. If both the old and new formats are prefix formats, copy the prefixes across.
3. Pick a file; if it has no extension, append the format's first extension.
4. Set the format and the document IRI, then save.

**Save formats offered: 8** (`OntologyFormatPanel`): RDF/XML, Turtle, OWL/XML, OWL Functional Syntax, Manchester Syntax, OBO, LaTeX, JSON-LD. The legacy `save()` with no argument (deprecated) saves every dirty ontology.

### 1.6 Reload (`OntologyReloader`)

1. Build a scratch manager that uses the same IRI mappers.
2. For every other loaded ontology, create a stub in the scratch manager containing **only its declaration axioms**, so that imports resolve cheaply and punning or type information is available.
3. Re-parse the document.
4. Compute a **patch** (`generateChangesToTransferContent`):
   - Add or remove imports by set difference.
   - Add or remove ontology annotations by set difference.
   - Add or remove axioms by set difference.
   - Add a `SetOntologyID` if the ID differs.
5. Apply the patch to the live ontology. Because the patch goes through the normal change path, **a reload is undoable**: it is logged to the history.
6. `rebuildActiveOntologiesCache`, `refreshRenderer`, `setClean`, then fire `ONTOLOGY_RELOADED`.

### 1.7 Python translation

```python
# sip/owlcore/model_manager.py
class ModelManager:
    def __init__(self, store: OntologyStore, prefs: Prefs):
        self.store = store                      # {onto_iri: OntologyDoc(graph, axioms: AxiomView, fmt, doc_uri, prefixes)}
        self.history = HistoryManager(self)
        self.catalog = CatalogManager()
        self.iri_resolver = IRIResolverChain([CatalogMapper(self.catalog), WebHeadMapper(timeout=20), UserResolvedMapper(handler)])
        self.active: OntologyDoc | None = None
        self.active_set: set[OntologyDoc] = set()
        self.selection_strategy = imports_closure_strategy
        self.dirty: set[OntologyID] = set()
        self.events = EventBus()                # model events (EventType) + change events (list[Change])
        self.renderer = make_renderer(prefs)    # plugin registry
        self.render_index = EntityRenderingIndex(self)
        self.hierarchies = HierarchyManager(self)
        self.entity_factory = EntityFactory(self, prefs)
        self.deprecation = DeprecationCache()
    def load(self, uri) -> OntologyDoc: ...        # §1.2; resolve owl:imports recursively via iri_resolver; never replace already-loaded
    def set_active(self, doc, force=False): ...    # §1.3
    def apply_changes(self, changes: list[Change]): # §2
        changes = minimise(changes)
        if not changes: return
        for ch in changes: ch.apply(self.store)     # mutates rdflib graph via AxiomView.add/remove (triples)
        self._on_changed(changes)                   # history.log, dirty, deprecation, then events.emit("changes", changes)
    def save(self, doc, fmt=None, path=None): ...   # temp file + os.replace; rdflib formats: xml, turtle, json-ld, (ofn/omn/owx via custom writer)
    def reload(self, doc): ...                      # parse to temp graph, diff axioms/imports/annots/id, apply as normal changes
```

Edge cases to keep:
- Imports change: recompute the active set and fire `ACTIVE_ONTOLOGY_CHANGED`.
- `SetOntologyID`: move the dirty flag from the old ID to the new one.
- Loading something that is already loaded: skip it and warn.
- Loading a `file:` document: register its folder catalog, creating one if absent. This should be configurable, because writing files as a side effect is surprising.

---

## 2. Change application and history

**Files**

| Class | Path |
|---|---|
| Minimizer | `o.p.e.o/model/ChangeListMinimizer.java` |
| History | `model/history/HistoryManager.java`, `HistoryManagerImpl.java` (185 lines), `ReverseChangeGenerator.java`, `UndoManagerListener.java` |
| Events | `model/event/EventType.java`, `OWLModelManagerChangeEvent.java`, `OWLModelManagerListener.java` |

### 2.1 Change types (OWLAPI)

There are 8 change kinds: `AddAxiom`, `RemoveAxiom`, `AddImport`, `RemoveImport`, `AddOntologyAnnotation`, `RemoveOntologyAnnotation`, `SetOntologyID`, plus the abstract axiom-change base. Each change carries its target `ontology`.

### 2.2 ChangeListMinimizer (exact algorithm)

```
toAdd, toRemove = Multimap<Ontology, Axiom>, Multimap<Ontology, Axiom>
pass 1: for ch in changes:
   if AddAxiom:    if not toRemove[ont].remove(ax): toAdd[ont].add(ax)      # add cancels a pending remove
   if RemoveAxiom: if not toAdd[ont].remove(ax):    toRemove[ont].add(ax)
pass 2 (preserve original order, dedupe):
   for ch in changes:
      AddAxiom    → emit iff ax in toAdd[ont];    then toAdd[ont].remove(ax)
      RemoveAxiom → emit iff ax in toRemove[ont]; then toRemove[ont].remove(ax)
      other       → emit always (imports, annotations, id are NOT minimised)
```

Note that it does **not** check whether the axiom is already present: OWLAPI simply ignores a redundant add. The port should drop no-op changes before logging them, otherwise undoing them later would delete real content.

### 2.3 HistoryManagerImpl

- Data: `undoStack: Stack<List<Change>>`, `redoStack: Stack<List<Change>>`, `typeOfChangeInProgress ∈ {NORMAL, UNDOING, REDOING}`.
- **One stack entry = one `applyChanges` batch**, as received in `ontologiesChanged`.

```
logChanges(changes):                  # called from ModelManager.ontologiesChanged
  NORMAL:   redoStack.clear(); undoStack.push(copy(changes))    # (switch fall-through into REDOING)
  REDOING:  undoStack.push(copy(changes))
  UNDOING:  redoStack.push(reverse(changes))                   # reverse of the reversed = original order
  fireStateChanged()

undo(): if undoStack: state=UNDOING; manager.applyChanges(reverse(undoStack.pop())); finally state=NORMAL
redo(): if redoStack: state=REDOING; manager.applyChanges(redoStack.pop());          finally state=NORMAL

reverse(changes): result = []; for ch in changes: result.insert(0, inverse(ch))   # reversed order
inverse: AddAxiom↔RemoveAxiom, AddImport↔RemoveImport, AddOntologyAnnotation↔RemoveOntologyAnnotation,
         SetOntologyID(o, new) → SetOntologyID(o, originalOntologyID)
```

Invariants and edge cases:
- `undo` and `redo` call **`OWLOntologyManager.applyChanges` directly**, not `ModelManager.applyChanges`. That bypasses minimisation and the ADC rewrite, but still goes through the listener, which is how the history entry gets re-logged.
- Exceptions during undo or redo are logged and swallowed. The popped batch is then lost.
- There is no depth limit.
- `clear()` empties both stacks.
- `getLoggedChanges()` returns a copy of the undo stack and is used by the "changes" views.
- Reloads and loads are not logged: loading uses `copyOntology(MOVE)`, which produces no change events. Reload patches **are** logged.

### 2.4 Model events

`EventType` has **11 values**:

| Group | Values |
|---|---|
| Ontology lifecycle | `ONTOLOGY_CREATED`, `ONTOLOGY_LOADED`, `ONTOLOGY_RELOADED`, `ONTOLOGY_SAVED` |
| Active set | `ACTIVE_ONTOLOGY_CHANGED`, `ONTOLOGY_VISIBILITY_CHANGED` |
| Rendering | `ENTITY_RENDERER_CHANGED`, `ENTITY_RENDERING_CHANGED` |
| Reasoning | `REASONER_CHANGED`, `ABOUT_TO_CLASSIFY`, `ONTOLOGY_CLASSIFIED` |

- `fireEvent(type)` runs on the Swing EDT (via `invokeLater` if called from another thread).
- It iterates over a copy of the listener list. **A listener that throws is detached.**
- `renderingChanged(entity)`, the renderer callback, updates the rendering cache for that entity, clears the object rendering cache and fires `ENTITY_RENDERING_CHANGED` synchronously.

### 2.5 Renderer refresh

`refreshRenderer()`:
1. Dispose the current renderer.
2. Create a new one from `OWLRendererPreferences.getRendererPlugin()`, falling back to `OWLEntityRendererImpl`.
3. `loadRenderer()`: add the listener, call `setup(mm)` and `initialise()`, `rebuildEntityIndices()`, then fire `ENTITY_RENDERER_CHANGED`.

It runs after every load and every reload.

### 2.6 Python

```python
# sip/owlcore/changes.py
@dataclass(frozen=True) class AddAxiom: onto: IRI; axiom: Axiom
@dataclass(frozen=True) class RemoveAxiom: ...
@dataclass(frozen=True) class AddImport / RemoveImport / AddOntologyAnnotation / RemoveOntologyAnnotation
@dataclass(frozen=True) class SetOntologyID: onto: IRI; new_id: OntologyID; original_id: OntologyID
def inverse(ch) -> Change: ...
def minimise(changes) -> list[Change]: ...          # exact port of §2.2, plus: drop adds of present axioms / removes of absent ones
# sip/owlcore/history.py
class HistoryManager:
    undo_stack: list[list[Change]]; redo_stack: list[list[Change]]; mode: Literal["normal","undoing","redoing"]
    def log(self, batch): ...                        # §2.3
    def undo(self): self.mode="undoing"; try: self.mm._apply_raw(reverse(self.undo_stack.pop())) finally: self.mode="normal"
```

Ordering matters. An rdflib triple-level change has to be derived per axiom by the `AxiomView`, for example `axiom_to_triples(ax)` including reified annotations. A RemoveAxiom must delete **only the triples that are not shared with other axioms**: blank-node class expressions are owned by a single axiom, but `rdf:type` declarations can be shared. Keep a per-axiom triple ownership map.

---

## 3. Hierarchy providers

**Files** (`o.p.e.o/model/hierarchy/`)

| Class | Notes |
|---|---|
| `OWLObjectHierarchyProvider` | interface |
| `AbstractOWLObjectHierarchyProvider` | ancestors, descendants, paths, filter, events |
| `AssertedClassHierarchyProvider` | 392 lines |
| `AbstractOWLPropertyHierarchyProvider` | base for property providers |
| `OWLObjectPropertyHierarchyProvider`, `OWLDataPropertyHierarchyProvider`, `OWLAnnotationPropertyHierarchyProvider` | |
| `IndividualsByTypeHierarchyProvider` | |
| `OWLOntologyHierarchyProvider` | imports tree |
| `AssertedSuperClassHierarchyProvider` | inverse view |
| `OWLHierarchyManagerImpl` | 7 lazy providers |
| `ClassHierarchyPreferences` | |

Helpers live in `org/protege/owlapi/inference/cls/` (`ParentClassExtractor`, `ChildClassExtractor`, `NamedClassExtractor`, `NamedConjunctChecker`) and in `org/protege/owlapi/inference/orphan/` (`TerminalElementFinder`, `EquivalenceRelation`, `Path`, `Relation`).

### 3.1 Interface

```
setOntologies(Set<Ontology>)   getRoots()   getChildren(n) (= filter(getUnfilteredChildren(n)))
getParents(n)   getDescendants(n)   getAncestors(n)   getEquivalents(n)   getPathsToRoot(n)
containsReference(n)   add/removeListener (nodeChanged(n), hierarchyChanged())   setFilter(Predicate) / clearFilter()
getRelationship(parent, child) / getDisplayedRelationships()   (class hierarchy only: "relationships" display)
```

### 3.2 Generic algorithms (`AbstractOWLObjectHierarchyProvider`)

```
ancestors(x):   res={}; rec(x): for p in parents(x): if p not in res: res.add(p); rec(p)    # cycle-safe; x ∈ ancestors(x) iff x is on a cycle
descendants(x): same with getChildren (filtered!)
pathsToRoot(x): if x in roots: {[x]}; else ∪ over parents p not yet processed: (paths(p) with x appended)   # processed set is shared across branches → not all paths in DAGs with shared ancestors
filter: default true; the hierarchy views set filter = not deprecated when "Display deprecated entities" is off
listener exceptions: listener removed AND RuntimeException rethrown
```

### 3.3 AssertedClassHierarchyProvider: the exact semantics

**State**
- `ontologies` (the active set)
- `roots`: normally `{owl:Thing}`. With "Display from ontology roots" switched on, it is the set of classes named by an ontology annotation `IAO_0000700` ("has ontology root", `http://purl.obolibrary.org/obo/IAO_0000700`) whose value is an IRI declared as a class in that ontology.
- `rootFinder: TerminalElementFinder<OWLClass>` over the relation `R(c) = parents(c) − roots`.
- `displayFromOntologyRoots`

**Parents** (`getParents(c)`)

```
if c in roots: return {}
if c ∈ rootFinder.terminalElements and not displayFromOntologyRoots: return roots     # orphan → under owl:Thing
res = {}
for ont in ontologies:
  for ax in ont.getAxioms(c, EXCLUDED):            # OWLAPI "axioms about c": SubClassOf(c, X), EquivalentClasses(c, …), DisjointClasses(c,…), DisjointUnion(c,…)
     ParentClassExtractor.visit(ax):
        SubClassOf(c, Sup):              NamedClassExtractor(Sup)
        EquivalentClasses(c, E1..En):    for Ei != c: NamedClassExtractor(Ei)
        (all other axiom types ignored)
NamedClassExtractor(CE): CE is a named class → {CE};  CE = ObjectIntersectionOf(ops) → ∪ NamedClassExtractor(op)  (recursive)
                         anything else (union, restriction, complement, ...) → {}
```

So `A ⊑ B ⊓ ∃r.C` gives parent B, and `A ≡ B ⊓ ∃r.C` also gives parent B. `A ≡ B` gives parent B and also makes B's parents include A, which forms a cycle. `owl:Thing` as a superclass extracts `owl:Thing` itself.

**Children** (`getUnfilteredChildren(p)`)

```
if p in roots:
    res = (rootFinder.terminalElements if not displayFromOntologyRoots else {}) ∪ extractChildren(p);  res.remove(p)
else: res = extractChildren(p)

extractChildren(p):
  results = {}
  for ont in ontologies: for ax in ont.getReferencingAxioms(p) if ax.isLogical:  ChildClassExtractor(p).visit(ax)
    SubClassOf(Sub, Sup): Sub anonymous → skip
        if NamedConjunctChecker.containsConjunct(p, Sup): results += Sub          # p is Sup, or a (nested) conjunct of Sup
        elif relationships≠∅: for conj in Sup.asConjunctSet(): if conj = ObjectSomeValuesFrom(r named ∈ relationships, filler == p):
                 results += Sub; child2rel[Sub] = r; break (first match)
    EquivalentClasses(E1..En): requires ≥1 named operand
        candidates = {Ei | not containsConjunct(p, Ei)}
        found = ∃ Ei anonymous with containsConjunct(p, Ei)     # p must occur as a conjunct of an ANONYMOUS operand
        if found: results += ∪ NamedClassExtractor(Ei) for Ei in candidates
  # equivalence "synonyms": for each child cls, every named class in an all-named EquivalentClasses(cls, X…) is added too
  for ont, cls in results: for EquivalentClasses ax of cls with no anonymous operand: results += (operands − cls)
```

The asymmetry is worth noting. `A ≡ B` (both named) does **not** make A a child of B through the EquivalentClasses visitor, because `found` requires an anonymous operand. A and B only reach each other through `getParents`, and as synonyms of some other child. **The view shows named-equivalent classes as siblings under each other's parents**, while `getEquivalents(c)` returns the named operands of the EquivalentClasses axioms on `c`.

**Implicit roots and cycles** (`TerminalElementFinder`)
- A class is terminal when, after a DFS over `R`, every element `R(x)` relates it to is equivalent to `x`, i.e. `x` is in the same strongly connected component as each of them.
- Terminal elements become the children of `owl:Thing`. That covers:
  1. classes with no named parents, the orphans
  2. classes whose parents are only `owl:Thing`, because roots are subtracted from R
  3. top-level cycles: every member of a cycle with no exit becomes a child of Thing

```
findTerminalElements(candidates): clear(); for x in candidates: build(x, path=None); finish()
build(x, path):
  if x in done: return
  if path contains x: equivalence.merge(path.loop(x)); return        # cycle detected → merge SCC members
  rel = R(x)
  if rel empty: terminal.add(x); done.add(x); return
  newPath = Path(path, x)
  for y in rel: build(y, newPath)
  if all(equivalence.equivalent(x, y) for y in rel): terminal.add(x)  # all exits stay within x's cycle
  done.add(x)
```

`rebuildImplicitRoots()` appends terminal elements for **every class in the signature** of each ontology in the active set.

**Incremental update** (`handleChanges(changes)`)
1. Filter to axiom changes on ontologies in the active set.
2. Collect `possibleTerminal`: every class in the signature of a changed axiom that is not a root. Classes removed and no longer referenced anywhere go into `notInOntologies` instead.
3. `rootFinder.findTerminalElements(possibleTerminal ∪ oldTerminal − notInOntologies)`.
4. Fire `nodeChanged` for:
   - all roots
   - every class in the signature of a changed axiom
   - every class that entered or left the terminal set

The provider keeps no parent/child cache: **every query re-scans the axioms**, which is cheap thanks to the OWLAPI indexes.

**Display relationships** (`setDisplayedRelationships(props)`): in addition to the subclass edges, `SubClassOf(Sub, … ⊓ ∃r.P ⊓ …)` with `r ∈ props` makes Sub a child of P labelled `r` (as in the OBO "part_of" view). `getRelationship(parent, child)` returns `r`, or empty for `owl:Thing` parents.

**`containsReference(c)`**: `c` is in the class signature of some ontology in the active set.

### 3.4 Property hierarchies (`AbstractOWLPropertyHierarchyProvider`)

Object and data properties.
- Root is `owl:topObjectProperty` or `owl:topDataProperty`.
- The ontology set is a `FakeSet`, a list-backed set that keeps insertion order.

```
parents(p): if p == root: {}
            res = named super-properties from SubObjectPropertyOf(p, Q) / SubDataPropertyOf over all ontologies (EntitySearcher.getSuperProperties)
            if res empty and p is in some signature: res = {root}            # inverse-of handled by visiting the inner property
children(root) = subPropertiesOfRoot (cached set)
children(p) = {s | SubPropertyOf(s, p), s named, p... and s ∉ ancestors(s)}     # cycle members are NOT shown as children…
isSubPropertyOfRoot(p): p≠root and ((parents(p) empty or root ∈ parents(p)) and p referenced) or p ∈ ancestors(p)   # …they are shown under root
rebuildRoots: subPropertiesOfRoot = {p ∈ signature(ont) | isSubPropertyOfRoot(p)}
equivalents(p): {a ∈ ancestors(p) | p ∈ ancestors(a)}  (cycle mates) ∪ named EquivalentObjectProperties/EquivalentDataProperties partners − {p}
handleChanges: for each property in a changed axiom's signature: recompute membership in subPropertiesOfRoot; cycle members (and their cycle mates) added to root's children; fire nodeChanged(prop) and nodeChanged(root)
```

Unlike classes, **EquivalentProperties axioms do not create parent edges**. They only feed `getEquivalents`. Property chains (`SubPropertyChainOf`) are not hierarchy edges either: `getSubProperties` uses `getObjectSubPropertyAxiomsForSuperProperty`, which returns only `SubObjectPropertyOf`.

**Annotation properties** (`OWLAnnotationPropertyHierarchyProvider`)
- There is no single root: `roots` is the set of properties with no `SubAnnotationPropertyOf` parent that are referenced or **built in**, plus any cycle members.
- **All built-in annotation property IRIs are always roots**: `OWLRDFVocabulary.BUILT_IN_ANNOTATION_PROPERTY_IRIS`, i.e. rdfs:label, comment, seeAlso, isDefinedBy, owl:deprecated, versionInfo, priorVersion, backwardCompatibleWith, incompatibleWith.
- Parents come from `SubAnnotationPropertyOf` only. Children are sub-properties whose own ancestors do not contain them.
- Incremental updates react to `SubAnnotationPropertyOf` axioms and annotation property declarations.
- Quirk: the first `setOntologies` uses **all loaded ontologies** (`mngr.getOntologies()`), but rebuilds after `ACTIVE_ONTOLOGY_CHANGED` use the active set.

### 3.5 Individuals by type (`IndividualsByTypeHierarchyProvider`)

This is a two-level forest. The node type is `OWLObject`, which can be a class or an individual.

```
rebuild: classes = {C named | ClassAssertion(C, i) for i ∈ named individuals of signature}
         untyped = {named individuals in signature with no named-class assertion}
         (individuals whose only types are anonymous expressions also count as untyped.
          The code adds i to `typed` only for named types; an anonymous-only ClassAssertion
          therefore leaves i untyped.)
roots = classes ∪ untyped
children(C ∈ classes) = {named i | ClassAssertion(C, i)};  children(other) = {}
parents(i) = {named C | ClassAssertion(C, i)};  parents(class) = {}
incremental: AddAxiom ClassAssertion(C named) → classes.add(C); RemoveAxiom → if children(C) empty: classes.remove(C);
             individuals in any changed axiom's signature are re-checked for untyped membership (typed ⇔ any ClassAssertion, even anonymous)
```

Edge: `rebuild` uses "has a named type" while the incremental path uses "has any ClassAssertion". They disagree for individuals with only anonymous types. The port should use the first definition consistently.

### 3.6 Other providers

- `OWLOntologyHierarchyProvider`: an imports tree over every loaded ontology. Parent → children are the direct imports; roots are the ontologies nobody imports. It is rebuilt on LOADED, RELOADED and CREATED.
- `AssertedSuperClassHierarchyProvider`: the inverted class hierarchy, used by the "Superclass hierarchy" view. Its children are the class provider's parents.
- `OWLHierarchyManagerImpl` creates 7 providers lazily: asserted class, inferred class, asserted object property, inferred object property, data property, annotation property, individuals by type. It calls `setOntologies(activeOntologies)` on `ACTIVE_ONTOLOGY_CHANGED` and `ONTOLOGY_RELOADED`. There is no inferred data-property provider.

### 3.7 Python

```python
# sip/owlcore/hierarchy/base.py
class HierarchyProvider(Protocol[N]):
    def set_ontologies(self, docs): ...; def roots(self) -> set[N]; def parents(self, n) -> set[N]; def children(self, n) -> set[N]
    def ancestors(self, n); def descendants(self, n); def equivalents(self, n); def paths_to_root(self, n); def contains_reference(self, n)
    filter: Callable[[N], bool] = lambda n: True
# sip/owlcore/hierarchy/classes.py
class AssertedClassHierarchy(HierarchyProvider[IRI]):
    def _named_conjuncts(self, ce) -> set[IRI]          # NamedClassExtractor: IRI → {IRI}; ObjectIntersectionOf → union; else ∅
    def _contains_conjunct(self, cls, ce) -> bool        # NamedConjunctChecker
    def parents(self, c): ...                            # §3.3 using axioms.subclass_of_by_sub[c], axioms.equivalent_by_class[c]
    def _extract_children(self, p): ...                  # uses axioms.referencing[p] (logical only)
    def _terminal_elements(self, candidates): ...        # port TerminalElementFinder; or use networkx SCC condensation: terminal ⇔ SCC has no out-edges in R
```

A practical simplification is possible: build a directed graph `c → parents(c) − roots` over the class signature, condense its strongly connected components (Tarjan or `networkx.condensation`), and take as terminal every member of an SCC with out-degree 0. This is equivalent to `TerminalElementFinder` and O(V+E).

Axioms come from `AxiomView`, so for example `SubClassOf(c, X)` comes from the triples `(c, rdfs:subClassOf, X)` with `X` an IRI or a bnode class expression. `owl:intersectionOf` lists must be parsed recursively. Also handle `rdfs:subClassOf owl:Thing`, and properties typed only via `rdf:type owl:ObjectProperty` count as being in the signature.

---

## 4. Entity rendering, finding and search

### 4.1 Renderer plugins

There are 4, registered against the `entity_renderer` extension point. Interface `ui/renderer/OWLModelManagerEntityRenderer`; base class `ui/renderer/AbstractOWLEntityRenderer` (`render(entity) = render(entity.getIRI())`, `processChanges` hook, `fireRenderingChanged(entity)`).

| Plugin id | Label | Class |
|---|---|---|
| OWLEntityRenderer | "Render by entity IRI short name (Id)" | `ui/renderer/OWLEntityRendererImpl` |
| OWLEntityPrefixedNameRenderer | "Render by prefixed name" | `ui/prefix/OWLEntityPrefixedNameRenderer` |
| OWLEntityAnnotationValueRenderer (**default**, `OWLRendererPreferences.DEFAULT_RENDERER_CLASS_NAME`) | "Render by annotation property (e.g., rdfs:label, skos:prefLabel)" | `ui/renderer/OWLEntityAnnotationValueRenderer` |
| PrefixedOWLEntityAnnotationValueRenderer | "Render by prefixed annotation property" | `ui/renderer/PrefixedOWLEntityAnnotationValueRenderer` |

`OWLEntityQNameRenderer` is deprecated and not registered.

**`OWLEntityRendererImpl.render(iri)`** (IRI short name):

```
1. wellKnown[iri] (all OWLRDFVocabulary, OWL2Datatype, DublinCoreVocabulary → prefixed names, e.g. owl:Thing, xsd:string, dc:creator)
2. for ns in Namespaces.values() (OWLAPI enum of well-known namespaces: owl, rdf, rdfs, xsd, xml, skos, dc, dcterms, foaf, swrl…, obo…):
       if iri startswith ns.prefixIRI: return ns.prefixName + ":" + rest          # NOTE: before fragment extraction!
3. s after last '#' → escape(s)       (index != -1)
4. s after last '/' → escape(s)
5. escape(iri.toQuotedString())  i.e. "<...>"
```

Edge: an IRI ending in `#` or `/` renders as the empty string, because step 3 or 4 returns `""`. The port should fall through to the next rule instead.

**Escaping** (`RenderingEscapeUtils.getEscapedRendering`):
1. Replace `\` with `\\`, `'` with `\'` and `"` with `\"`.
2. If the *original* contains any of ``space \ , < > = ^ @ { } [ ] ( )``, wrap the result in single quotes.

`unescape` reverses this. Manchester syntax needs the quoting because labels with spaces must be written `'my class'`.

**`OWLEntityAnnotationValueRenderer`**, the label renderer:
- Preferences come from `OWLRendererPreferences`.
  - Annotation IRIs default to `[rdfs:label, skos:prefLabel]`.
  - The language list defaults to `[locale.lang, locale.lang-COUNTRY, "" (no lang), "en"]`, with `""` appended if it is missing. The same list applies to every annotation IRI.
  - Storage is a string list `"<iri>, <lang1>, !, ..."`, where `!` means no language.
- Delegates to `AnnotationValueShortFormProvider(ontologies = active set, alternate = PrefixAwareShortFormProvider(fallback OWLEntityRendererImpl), alternateIRI = SimpleIRIShortFormProvider)`:

```
for prop in annotationProperties (in order):
   best=None; bestIdx=∞
   for ont in activeOntologies: for ax in AnnotationAssertion(subject = entity.IRI):
       if bestIdx > 0 and ax.property == prop:
          value is literal:  if langs empty: best=value; bestIdx=0
                             else idx = langs.indexOf(value.lang)  ('' for plain/untyped literals)
                                  if 0 <= idx < bestIdx: best=value; bestIdx=idx
          value is IRI:      best = iri  (no language ranking; last IRI wins unless a literal with idx 0 already won)
   if best: return render(best)  (literal → lexical form; IRI → SimpleIRIShortFormProvider)
return alternate.shortForm(entity)   # PrefixAwareShortFormProvider: longest matching prefix among
                                     #   (OWL/RDF/RDFS/XSD + well-known + ALL loaded ontologies' format prefixes) else IRI short name
```

The result is escaped.
- Literals whose language is not in the list are ignored, so a label `"x"@fr` is skipped when the list is `[en, ""]`.
- **Property order dominates language order**: an `rdfs:label` in any listed language beats any `skos:prefLabel`.
- `processChanges`: for every added or removed `AnnotationAssertion` on a watched property with an IRI subject, fire `renderingChanged` for the IRI interpreted as each of the 5 entity types.
- `render(IRI)` interprets the IRI as an `OWLClass`, but annotation lookup is by IRI, so the type is irrelevant.

**`PrefixedOWLEntityAnnotationValueRenderer`**: takes the label short form and prepends the prefix name of the first prefix-map entry (merged map) that the IRI starts with, unless the short form already starts with it. The default prefix `:` is not prepended. Example: `obo:'part of'`.

**`OWLEntityPrefixedNameRenderer`**: `PrefixedNameRenderer.getPrefixedNameOrQuotedIri`, where the prefixes are the merged ontology prefixes plus owl/rdf/rdfs/xsd plus well-known ones. **Prefix matching is longest-first** (an `ImmutableSortedMap` ordered by prefix length descending). The local part is not validated.

`PrefixUtilities.getPrefixOWLOntologyFormat(mm)` merges the prefixes of all ontologies, active first (`ActiveOntologyComparator`). A prefix name or namespace that is already taken is skipped.

### 4.2 Rendering cache and entity index (`model/cache/OWLEntityRenderingCacheImpl`)

- Six multimaps `String -> [Entity]`, one per entity type, plus `entityRenderingMap: Entity -> String`.
- `rebuild()` adds:
  - owl:Thing/Nothing, the top and bottom object and data properties
  - every entity in the signature of **all loaded ontologies**
  - the built-in annotation properties and the DublinCore properties
  - the known datatypes of the active set
- Change handling: for every entity in the signature of an axiom change, call `updateRendering(e)`. That always removes the old rendering and re-adds it if `e` is still in the signature of some active ontology.
- **Name collision resolution** (`getFirstEntityOrNull`): with one candidate, return it. With several, pick the one with the maximum `(definitionCount, referenceCount)` in the active ontology, where definitionCount = `EntitySearcher.getReferencingAxioms(e, active)` (axioms whose subject is `e`) and referenceCount = `active.getReferencingAxioms(e)`.
- `ModelManager.getRendering(obj)`:
  - entity: cached rendering, else `renderer.render`
  - other objects: the `OWLObjectRenderingCache` LRU (50 entries, cleared on every model event and every change); for class expressions the user's own typed string (`OWLExpressionUserCache`) takes precedence, but that cache is disabled by default.
- **Disambiguated rendering** (`getDisabmiguatedRendering`): if several entities share a rendering, append ` (OBO:ID)` when the IRI is an OBO-style IRI, otherwise ` (prefix:local)` from the well-known and OWL prefixes. It is used in frame rows.
- The comparator `OWLObjectRenderingComparator` compares renderings with quotes stripped, case-insensitively, and breaks ties with `OWLObject.compareTo`.

### 4.3 OWLEntityFinder (`model/find/OWLEntityFinderImpl`, `OWLEntityFinderPreferences`)

- **Exact lookup**: `getOWLClass(rendering)` and the like. The rendering is stripped of surrounding quotes and re-escaped, then looked up in the per-type multimap; collisions are resolved as in §4.2. `getOWLEntity` tries the types in the order class, object property, data property, individual, datatype, annotation property. `getOWLEntities(rendering)` returns every type.
- **Matching** (`getMatchingOWLClasses(match, fullRegExp, flags = CASE_INSENSITIVE)`):

```
if match == "": {}
if fullRegExp: p = compile(match, flags); return {entity(r) | r in renderings(type), p.search(r)}       # find(), not full match
wildcard mode:
   "*"             → all entities of type in active ontologies (datatypes: known datatypes)
   "*foo*" / "*foo"→ contains("foo")
   "foo*" / "foo"  → startswith("foo") or startswith("'foo")          # prefix match by default!
   compare lower-cased; blank remainder → {}
```

  `OWLIndividual.class` is used in `getAllEntities` but `OWLNamedIndividual` elsewhere, so `"*"` returns no individuals. That is a latent bug; do not port it.
- **Preferences** (key `org.protege.editor.owl.finder`):

| Setting | Default |
|---|---|
| `USE_REGULAR_EXPRESSIONS` | false |
| `SEARCH_DELAY_KEY` | 500 ms |
| `CASE_SENSITIVE_KEY` | false |
| `WHOLE_WORDS_KEY` | false |
| `IGNORE_WHITE_SPACE_KEY` | true |
| `SHOW_DEPRECATED` | true |

- `getEntities(IRI)`: every entity type that the IRI has in the active set (punning aware).

### 4.4 Search (`model/search/*`, `ui/search/SearchPanel`)

- `DefaultSearchManager` is the only `searchmanager` plugin.
- Categories (`SearchCategory`, 4): `DISPLAY_NAME`, `IRI`, `ANNOTATION_VALUE`, `LOGICAL_AXIOM`.
- `SearchMetadata(category, groupDescription, subject, subjectRendering, searchString)` comes from 6 importers in `model/search/importer/`:

| Importer | Produces |
|---|---|
| `DisplayNameSearchMetadataImporter` | the rendering |
| `EntityIRISearchMetadataImporter` | the IRI string |
| `EntityAnnotationValueSearchMetadataImporter` | one record per annotation on the entity, rendered with Manchester styling; group = annotation property rendering |
| `LogicalAxiomRenderingSearchMetadataImporter` | each logical axiom's rendering; group = axiom type name; subject = the axiom subject |
| `AxiomAnnotationSearchMetadataImporter` | axiom annotations |
| `OntologyAnnotationSearchMetadataImporter` | ontology annotations |

- The index is a flat `List<SearchMetadata>`, rebuilt lazily. It is marked stale on any ontology change and on `ACTIVE_ONTOLOGY_CHANGED`, `ENTITY_RENDERER_CHANGED` and `ENTITY_RENDERING_CHANGED`.
- Query compilation (`SearchPanel.createSearchRequest`):

```
flags = DOTALL | (caseSensitive ? 0 : CASE_INSENSITIVE)
for token in query.split(/\s+/):
   if isOboId(token) ("GO:0001"): pat = token.replace(":", "(?::|_)")
   elif useRegex: pat = token (ignoreWhiteSpace → ' ' → \s+)
   else: pat = quote(token) (ignoreWhiteSpace → join(quote(parts), "\s+"))
   if wholeWords: pat = "\b(:?" + pat + ")\b"
patterns.append(compile(pat, flags))
match(record): AND over patterns, each searched with find() on searchString; record per-pattern (start,end)
```

  Patterns are matched independently, and the `startIndex` variable is only used for the guard `startIndex >= len`. The `(:?` is a typo for `(?:`.
- Searches run on a single-thread executor and are cancellable: a newer search ID aborts the running one. Progress is reported per percent.

### 4.5 Python

```python
# sip/owlcore/render/escape.py      escape(s), unescape(s)        (exact port)
# sip/owlcore/render/renderers.py
class IRIShortNameRenderer:  render(iri)                           # §4.1 rules 1-5 (fix empty-fragment case)
class PrefixedNameRenderer: __init__(prefix_map) sorted by len desc; render(iri) -> "p:local" | "<iri>"
class LabelRenderer: __init__(props=[RDFS.label, SKOS.prefLabel], langs=[loc, loc_CC, "", "en"]); render(iri, docs)  # §4.1
class PrefixedLabelRenderer(LabelRenderer)
# sip/owlcore/render/index.py
class EntityRenderingIndex: by_type: dict[EntityType, dict[str, list[IRI]]]; rendering: dict[(IRI,EntityType), str]
    def rebuild(); def update(entity); def lookup(rendering, etype) -> IRI | None  # collision: max(def_count, ref_count) in active
    def disambiguated(entity) -> str
# sip/owlcore/find.py
class EntityFinder: match(pattern, etype=None, regex=False, case_sensitive=False) -> set[Entity]   # §4.3 semantics (prefix-by-default)
# sip/owlcore/search.py
class SearchIndex: records: list[SearchRecord]; stale: bool; def query(text, opts) -> list[SearchResult]   # §4.4
```

For large ontologies use a sorted list of lower-cased renderings plus `bisect` for prefix lookups (autocomplete), and a trigram index for the contains and regex modes.

---

## 5. Manchester OWL syntax: parsing, rendering, autocompletion

**Files**

| Class | Path |
|---|---|
| Factory | `o.p.e.o/ui/clsdescriptioneditor/ManchesterOWLExpressionCheckerFactory.java`, implementing `OWLExpressionCheckerFactory` |
| Checkers (8 kinds) | `OWLClassExpressionChecker`, `OWLClassExpressionSetChecker`, `OWLClassAxiomChecker`, `OWLPropertyChainChecker`, `SWRLRuleChecker`, `OWLPropertySetChecker`, `OWLObjectPropertySetChecker`, `OWLDataRangeChecker` |
| Interface | `OWLExpressionChecker<O>`: `check(text)` and `createObject(text)` |
| Entity checker | `model/parser/ProtegeOWLEntityChecker.java`, which maps names to entities through `OWLEntityFinder` |
| Exceptions | `model/parser/ParserUtil.java`, `model/classexpression/OWLExpressionParserException.java` |
| Editor and autocomplete | `ui/clsdescriptioneditor/ExpressionEditor.java` (a `JTextPane` that re-checks 120 ms after typing stops; `ExpressionEditorPreferences.CHECK_DELAY_KEY`), `OWLAutoCompleter.java`, `AutoCompleterMatcherImpl.java`, `OWLExpressionHistoryCompleter.java` |
| Renderer | `ui/renderer/OWLObjectRendererImpl.java`, which wraps OWLAPI `ManchesterOWLSyntaxObjectRenderer` (`PatchedManchesterOWLSyntaxObjectRenderer`) |

### 5.1 Parsing

Each checker builds a new `ManchesterOWLSyntaxParserImpl(OWLOntologyLoaderConfiguration::new, dataFactory)` and sets the entity checker to `ProtegeOWLEntityChecker(entityFinder)`, so **names are resolved by display rendering** (the label or short name, escaped with quotes) and not by IRI. It then calls one of:

| Checker | Parser method |
|---|---|
| Class expression | `parseClassExpression(text)`; empty text yields null |
| Class expression set | `parseClassExpressionList()`, comma-separated |
| Class axiom | `parseAxiom()`; must be `C SubClassOf D`, `C EquivalentTo D` or `C DisjointWith D`, otherwise a synthetic exception with class, object property and data property expected |
| Property chain | `parseObjectPropertyChain()` (`p o q`) |
| Others | SWRL rules, property sets, data ranges |

`ParserException` is converted to `OWLExpressionParserException(msg, start, end, classExpected, objPropExpected, dataPropExpected, individualExpected, datatypeExpected, annotPropExpected, expectedKeywords)`, where `end = start + len(currentToken)` and `end = start` at `<EOF>`. The **expectation flags plus the keyword set are the API that drives autocompletion and error highlighting.**

### 5.2 Rendering

- `OWLObjectRendererImpl.render(obj)` runs the OWLAPI Manchester renderer with a `ShortFormProvider` that delegates to `mm.getRendering(entity)`. That provider is the entity renderer described above, so renderings are labels.
- Bare IRIs, such as annotation values or subjects, go through `entityRenderer.render(iri)`.
- SWRL variables render as `?` + short name; SWRL built-ins use their `swrlb:` short form.
- An ontology renders as the short form of its default document IRI, its ID if anonymous, or "Anonymous Ontology".
- Preferences: `USE_THAT_KEYWORD` (false), `HIGHLIGHT_KEY_WORDS` (true), `RENDER_DOMAIN_AXIOMS_AS_GCIS`, font name and size.

### 5.3 Autocompletion (`OWLAutoCompleter`)

- **Triggers**: Ctrl+Space or Tab (Tab is consumed). Esc hides the popup, Enter accepts the selection, Up and Down move it, Left and Right hide the popup.
- Popup: 350×300, at most `DEFAULT_MAX_ENTRIES = 100` entries.
- Word delimiters: space, `\n`, `[`, `]`, `{`, `}`, `(`, `)`, `,`, `^`.
- **Algorithm**:

```
caret = selectionStart if selection else caretPos
wordIndex = escapedWordIndex() ?? unbrokenWordIndex()   # inside an unclosed '…' → index of the opening quote; else scan back to delimiter
prefixText = text[0:wordIndex] + "+**"                    # force a parse error at the completion point ("p min 2 **" would parse)
try checker.check(prefixText) except E:
    word = text[wordIndex:caret]
    ents = AutoCompleterMatcherImpl.getMatches(word + "*",   # wildcard prefix match via EntityFinder (regex OFF)
              E.classExpected, E.objPropExpected, E.dataPropExpected, E.individualExpected, E.datatypeExpected, E.annotPropExpected)
           → TreeSet sorted by OWLObjectRenderingComparator
    kws = [k for k in E.expectedKeywords if k.lower().startswith(word.lower())]
    matches = kws + ents                                   # keywords first
if len(matches) == 1: insert immediately; elif >1: show popup
insertWord(w): delete selection; delete text[wordIndex:caret]; insert w (entity → mm.getRendering(e), already quoted if needed)
```

### 5.4 Python

Implement a hand-written recursive-descent Manchester parser (`sip/owlcore/manchester/parser.py`) that yields:
- the AST: `ClassExpression` dataclasses `ObjectIntersectionOf`, `ObjectUnionOf`, `ObjectComplementOf`, `ObjectSomeValuesFrom`, `ObjectAllValuesFrom`, `ObjectHasValue`, `ObjectMin/Max/ExactCardinality`, `ObjectOneOf`, `ObjectHasSelf`, plus the Data* variants and data ranges with facets;
- on failure, `ParseError(pos, end, expected_kinds: set[EntityType], expected_keywords: set[str], message)`.

Precedence is low to high: `or`, `and`, `not`, then restrictions (`some`, `only`, `value`, `min`, `max`, `exactly`, `Self`). Atoms are a name, `(…)`, `{…}` or a datatype restriction `xsd:int[>= 1]`. An inverse property is written `inverse p`.

Name resolution uses a callback `resolve(name, kind) -> IRI | None` backed by the `EntityRenderingIndex`. Accept quoted `'…'` names, prefixed names, full `<IRI>`s and plain short names.

```python
class ManchesterChecker:          # check(text) / create(text) for kinds: class_expr, class_expr_list, class_axiom, prop_chain, data_range, prop_set
class AutoCompleter:              # complete(text, caret) -> list[Suggestion]; same "+**" trick, keyword-first ordering, cap 100
class ManchesterRenderer:         # render(axiom|ce, short_form=renderer)
```

To mirror Protégé exactly, an alternative is to call OWLAPI through JPype (`owlready2` has no Manchester parser with expectation sets).

---

## 6. Entity creation

**Files** (`o.p.e.o/model/entity/`)

| Class | Notes |
|---|---|
| `OWLEntityFactory` | interface: `createOWLClass(shortName, baseIRI)`, the same for the other 5 types, `createOWLEntity(type, shortName, base)`, `preview(...)` |
| `CustomOWLEntityFactory` | the only implementation |
| `EntityCreationPreferences` | |
| `AutoIDGenerator`, `AbstractIDGenerator` | |
| `UniqueIdGenerator` | default |
| `IterativeAutoIDGenerator` | |
| `RandomProlong` | |
| `Revertable` | |
| `LabelDescriptor` | implemented by `MatchRendererLabelDescriptor` (default) and `CustomLabelDescriptor` |
| `OWLEntityCreationSet` | (entity, changes) |
| `EntityCreationMetadataProvider` and friends | `model/annotation/*`: created-by and creation-date annotations |
| ID-range policies | `model/idrange/*` |

### 6.1 Preferences

Key set `org.protege.editor.owl.entity.creation`.

| Key | Default | Meaning |
|---|---|---|
| `DEFAULT_BASE_URI` | `http://example.invalid/ontologies/ont.owl#` | base when "use default base" is on or the active ontology is anonymous |
| `USE_DEFAULT_BASE_URI` | false | else the base is the active ontology IRI |
| `DEFAULT_URI_SEPARATOR` | `#` | appended if the base does not end in `#` or `/` |
| `USE_AUTO_ID_FOR_FRAGMENT` | false | **false = name-as-fragment, true = auto-ID** |
| `NAME_LABEL_GENERATE` | false | add a label holding the user-typed name |
| `NAME_LABEL_URI` / `NAME_LABEL_LANG` | null | used by `CustomLabelDescriptor` |
| `ID_LABEL_GENERATE` | false | add a label holding the generated ID |
| `AUTO_ID_GENERATOR_CLASS` | `UniqueIdGenerator` | or `IterativeAutoIDGenerator` (UI radio buttons); `RandomProlong` also exists |
| `AUTO_ID_PREFIX` | `[type]_` | macros `[type]` → `OWLClass`, `OWLObjectProperty`, … (Java simple class name); `[user]` → `user.name` |
| `AUTO_ID_SUFFIX` | `""` | |
| `AUTO_ID_SIZE` | 20 | zero-padded digit count, iterative only |
| `AUTO_ID_START` / `AUTO_ID_END` | 0 / -1 (no limit) | |
| `SAVE_AUTO_ID_START` | false | persist the next ID after each allocation |
| `POLICY_RANGE_NAME`, `AUTO_ID_START_FOR_POLICY_<name>` | `""` | per-ID-range-policy counters |
| `IGNORE_RANGE_POLICIES` | false | |
| `LABEL_DESCRIPTOR` | `MatchRendererLabelDescriptor` | label property and language = **first renderer annotation IRI and first renderer language** (rdfs:label with the locale language by default) |

### 6.2 Algorithm (`CustomOWLEntityFactory.createOWLEntity`)

```
generateName(type, shortName, base):
  if base is None: base = defaultBase if (useDefaultBase or active.id anonymous) else active.ontologyIRI
  if autoIdFragment:
      tried = {}
      loop: id = generator.next(type); iri = createIRI(id, base)
            if iri in tried: raise AutoIDException("ran out of new ids")
            tried.add(iri)
            while iri used by ANY entity type in ANY loaded ontology        # "don't pun unnecessarily"
  else:
      iri = createIRI(shortName, base)
      if iri already used by an entity OF THE SAME TYPE in the active set: raise OWLEntityCreationException("Entity already exists")
      if generateIdLabel: id = generator.next(type)                     # id used only as label
  return (iri, id, shortName)

createIRI(fragment, base): fragment = fragment.replace(" ", "_"); b = str(base).replace(" ", "_")
                           if not b.endswith(("#","/")): b += separator;  return IRI(b + fragment)  (java.net.URI validates)

getChanges(entity, name):
  if generateIdLabel and id:      AddAxiom(active, AnnotationAssertion(labelProp, entity.iri, Literal(id, labelLang)))
  if generateNameLabel and short: AddAxiom(active, AnnotationAssertion(labelProp, entity.iri, Literal(shortName, labelLang)))
  AddAxiom(active, Declaration(entity))
  + metadata: if createdBy enabled: AnnotationAssertion(createdByProp, iri, username|ORCID)
              if creationDate enabled: AnnotationAssertion(dateProp, iri, formatted now)
```

The caller then applies the creation set's changes together with any structural axiom (for example `SubClassOf(new, parent)` for "Add subclass"), so the whole creation is a single undo step.

Name-as-fragment examples:
- `"My Class"` becomes `…#My_Class`. With label generation off, the renderer shows "My_Class".
- With the auto-ID default, a new class gets an IRI like `…#OWLClass_6f1c…` (`UniqueIdGenerator`, see below), and its label is the typed name if `NAME_LABEL_GENERATE` is on.

ID generators:
- **`UniqueIdGenerator`**: `prefix + UUID.randomUUID().replace("-", "_") + suffix`. The UUID is pre-drawn so that a preview shows the next ID; checkpoint and revert are no-ops, so a preview "consumes" nothing, but the next real call does use the pre-drawn ID.
- **`IterativeAutoIDGenerator`**:
  - Counter starts at `getPolicyAutoIDStart()`.
  - Each call: if the preference start changed, reset to it. If `end != -1` and `id > end`, raise. If saving is on, persist `id + 1`. Return `prefix + zeroPad(id, digits) + suffix`, then increment.
  - `checkpoint` and `revert` keep a stack, so `preview()` does not consume an ID.
  - `NumberFormat` with min = max integer digits = `digits`: a value with more digits is **truncated to the low-order digits**. That is an edge case; the port should raise instead.
- **`RandomProlong`**: random pronounceable ID, `prefix + Util.randomProlong() + suffix`.
- `preview(type, shortName, base)` calls `checkpoint()`, `createOWLEntity`, then `revert()`. The New Entity dialog uses it to show the IRI live.

**ID-range policies**:
- When the active ontology's folder contains `<name>-idranges.owl` (`ActiveOntologyIdRangesPolicyManager`), `IdPolicyEntityCreationPreferencesUpdater` rewrites the preferences.
- The policy uses the OBO IAO vocabulary:

| Property | IRI |
|---|---|
| `ID_DIGIT_COUNT` | IAO_0000596 |
| `ID_RANGE_ALLOCATED_TO` | IAO_0000597 |
| `ID_POLICY_FOR` | IAO_0000598 |
| `ID_PREFIX` | IAO_0000599 |

- The ID prefix must match `(.+)([/#:])([A-Za-z0-9]+(_[A-Za-z0-9]+)*)_$`. The groups become base IRI, separator and auto-ID prefix (for example `http://purl.obolibrary.org/obo/` + `/` + `GO_`).
- It then sets: use default base on, auto-ID on, name label on, label property `rdfs:label`, ID label off, suffix empty.
- The numeric range is taken from the datatype definition allocated to the current user name (case-insensitive match), using the facets `>=` / `<=`. If the user has no range, it prompts. `POLICY_RANGE_NAME` is set to `"<policyFor>_<start>"`.

### 6.3 Python

```python
# sip/owlcore/entity/prefs.py   @dataclass EntityCreationPrefs (all keys above, same defaults)
# sip/owlcore/entity/idgen.py
class UUIDGen: next(etype) -> f"{prefix}{uuid4()!s}".replace("-", "_") ...  # note: replace only on uuid part
class IterativeGen: next(etype); checkpoint(); revert()        # raise on overflow beyond `digits`
def expand_macros(s, etype, user) -> str                         # [type] → "OWLClass" | "OWLObjectProperty" | ...
# sip/owlcore/entity/factory.py
class EntityFactory:
    def create(self, etype, short_name: str, base: str | None = None) -> CreationSet   # returns (iri, [AddAxiom...])
    def preview(self, etype, short_name, base=None) -> CreationSet
```

The triples emitted are:
- `(iri rdf:type owl:Class|owl:ObjectProperty|owl:DatatypeProperty|owl:AnnotationProperty|owl:NamedIndividual|rdfs:Datatype)`
- an optional `(iri rdfs:label "name"@lang)`
- optional metadata triples such as `dcterms:creator` and `dcterms:created`, whose properties are configurable

---

## 7. Metrics and description frames

### 7.1 Ontology metrics

The view is `OWLOntologyMetricsView` ("Ontology metrics") → `ui/metrics/AxiomMetricsViewComponent` → `ui/metrics/MetricsPanel.java`. The metric classes are mostly OWLAPI `org.semanticweb.owlapi.metrics.*`. Local helper classes exist in `ui/metrics/*` (`ClassCountMetric`, `ImportsClosure*CountMetric`, `DLExpressivityMetric`, `ReferencedAnnotationPropertyCount`, …), but **only `ReferencedAnnotationPropertyCount` is wired into the panel.**

- Every metric runs with `setImportsClosureUsed(true)` on the **active ontology**, so all counts are over the imports closure.
- Values are invalidated on any change or model event and recomputed lazily.
- Right-clicking an axiom-count row offers "Show axioms"; right-clicking a table offers "Copy metrics to clipboard" (CSV).

**43 metrics in 6 tables:**

| Table | Metrics |
|---|---|
| **Metrics** (8) | Axiom count; Logical axiom count; Declaration axioms (AxiomTypeMetric DECLARATION); Class count (referenced); Object property count; Data property count; Individual count; Annotation property count. *(DL expressivity is commented out: "temporarily removed due to OWL API upgrade")* |
| **Class axioms** (5) | SubClassOf; EquivalentClasses; DisjointClasses; GCI count; Hidden GCI count |
| **Object property axioms** (14) | SubObjectPropertyOf; EquivalentObjectProperties; InverseObjectProperties; DisjointObjectProperties; Functional; InverseFunctional; Transitive; Symmetric; Asymmetric; Reflexive; Irreflexive; ObjectPropertyDomain; ObjectPropertyRange; SubPropertyChainOf |
| **Data property axioms** (6) | SubDataPropertyOf; EquivalentDataProperties; DisjointDataProperties; FunctionalDataProperty; DataPropertyDomain; DataPropertyRange |
| **Individual axioms** (7) | ClassAssertion; ObjectPropertyAssertion; DataPropertyAssertion; NegativeObjectPropertyAssertion; NegativeDataPropertyAssertion; SameIndividual; DifferentIndividuals |
| **Annotation axioms** (3) | AnnotationAssertion; AnnotationPropertyDomain; AnnotationPropertyRangeOf |

Definitions, per OWLAPI 4:
- **AxiomCount**: all axioms over the closure, including declarations and annotation assertions.
- **LogicalAxiomCount**: logical axioms only.
- **Referenced X count**: the size of the union of signatures across the closure.
- **GCICount**: the size of `ontology.getGeneralClassAxioms()`, i.e. SubClassOf with an anonymous LHS, plus Equivalent and Disjoint class axioms with no named operand.
- **HiddenGCICount**: the number of named classes `C` that have **both** an `EquivalentClasses(C, …)` axiom **and** a `SubClassOf(C, …)` axiom. A defined class with extra necessary conditions acts as a hidden GCI.
- **AxiomTypeMetric** wrappers count axioms of one type; their row name is `AxiomType.getName()`.

Python: `sip/owlcore/metrics.py` → `compute_metrics(doc, include_imports=True) -> dict[str, dict[str, int]]`, a direct count over the `AxiomView` indexes with the same 6 groups and labels.

### 7.2 Frame model

| Piece | Path |
|---|---|
| Frame | `ui/frame/AbstractOWLFrame` (a list of sections, keyed by a root object) |
| Section | `ui/frame/AbstractOWLFrameSection<R, A extends OWLAxiom, E>` |
| Row | `ui/frame/AbstractOWLFrameSectionRow` |

Section lifecycle:

```
setRootObject(R root):
  rows.clear(); clear()
  for ont in activeOntologies: refill(ont)            # asserted rows (row.ontology = ont → editable/deletable)
  try refillInferred()                                 # rows with ontology=None (inferred, read-only, shown in yellow), only if reasoner prefs enable that OptionalInferenceTask
  sort rows by getRowComparator(); fireContentChanged()
on ontology change: for axiom changes visit axiom; if isResettingChange(change) → reset() (full refill)
add (+ button): editor → handleEditingFinished(objects):
  for obj: ax = createAxiom(obj); ont = FreshAxiomLocationStrategy.locate(ax)    # default ACTIVE_ONTOLOGY; alt SUBJECT_DEFINING_ONTOLOGY (topologically sorted closure, ontology that defines the subject)
  mm.applyChanges([AddAxiom(ont, ax) ...])                                         # one undo step
edit row: [RemoveAxiom(row.ont, old), AddAxiom(row.ont, new.withAnnotations(old.annotations))]; inferred rows: AddAxiom(active, new)   # "assert inferred"
delete row: [RemoveAxiom(row.ont, row.axiom)]  (only if row.ontology ≠ None)
inferred rows skipped if vacuous (VacuousAxiomVisitor) or involve inverse(inverse(p))
```

### 7.3 Class description frame (`ui/frame/cls/OWLClassDescriptionFrame`)

It has 8 sections, in this order:

| # | Label (row label) | Class | Asserted rows (`refill(ont)`) | `createAxiom(obj)` | Inferred (`refillInferred`) | Resetting change |
|---|---|---|---|---|---|---|
| 1 | **Equivalent To** (Equivalent class) | `OWLEquivalentClassesAxiomFrameSection` | `ont.getEquivalentClassesAxioms(C)`; one row per axiom (n-ary kept whole) | `EquivalentClasses(C, obj)` | if unsatisfiable: `C ≡ owl:Nothing`; else `reasoner.getEquivalentClasses(C)` minus already shown | Equivalent axiom containing C |
| 2 | **SubClass Of** (Superclass) | `OWLSubClassAxiomFrameSection` | `ont.getSubClassAxiomsForSubClass(C)` | `SubClassOf(C, obj)` | direct inferred superclasses (`getSuperClasses(C, true)`) not already asserted, non-trivial; skipped if inconsistent or C unsatisfiable | SubClassOf with sub == C |
| 3 | **General class axioms** | `OWLClassGeneralClassAxiomFrameSection` | `ont.getGeneralClassAxioms()` whose signature contains the selected class | (Manchester class axiom editor) | none | a GCI SubClassOf, or Equivalent/Disjoint not containing C, whose signature mentions C |
| 4 | **SubClass Of (Anonymous Ancestor)** (Anonymous Ancestor Class) | `InheritedAnonymousClassesFrameSection` | for each asserted ancestor A ≠ C (`classHierarchy.getAncestors(C)`): every `SubClassOf(A, anon)` and **every** `EquivalentClasses(A, …)` axiom; the row shows A as context. Read-only (`canAdd = false`) | n/a | for reasoner super-classes not processed yet: `SubClassOf(C, anon)` from their anonymous superclasses or equivalents, searched over the imports closure | any SubClassOf or Equivalent change |
| 5 | **Instances** (Type assertion) | `OWLClassAssertionAxiomMembersSection` | `ont.getClassAssertionAxioms(C)` | `ClassAssertion(C, ind)` | `reasoner.getInstances(C, direct)` minus asserted | ClassAssertion with CE == C |
| 6 | **Target for Key** (Key) | `OWLKeySection` | `ont.getHasKeyAxioms(C)` | `HasKey(C, props)` | none | HasKey with CE == C |
| 7 | **Disjoint With** | `OWLDisjointClassesAxiomFrameSection` | `ont.getDisjointClassesAxioms(C)`; one row per axiom, showing the other operands | `DisjointClasses({C} ∪ set)` | `getSubClasses(not C, direct=true)` minus shown, non-trivial | Disjoint axiom containing C |
| 8 | **Disjoint Union Of** | `OWLDisjointUnionAxiomFrameSection` | `ont.getDisjointUnionAxioms(C)` | `DisjointUnion(C, set)`; editor result must have at least 2 classes | none | DisjointUnion with class == C |

The "Annotations" section is not in the Description frame. It lives in a separate view, `OWLClassAnnotations`, built on `OWLAnnotationsFrame` → `OWLAnnotationFrameSection` ("Annotations"). The combined `OWLEntityFrame`, used by the "Manchester syntax entity rendering" view, has class sections in this order: Annotations, Equivalent To, SubClass Of, Disjoint With, Disjoint Union Of.

### 7.4 Property, individual and datatype frames

| Frame (path `ui/frame/…`) | Sections in order (label) |
|---|---|
| `objectproperty/OWLObjectPropertyDescriptionFrame` (7) | Equivalent To · SubProperty Of · Inverse Of · Domains (intersection) · Ranges (intersection) · Disjoint With · SuperProperty Of (Chain) |
| `dataproperty/OWLDataPropertyDescriptionFrame` (5) | Equivalent To · SubProperty Of · Domains (intersection) · Ranges · Disjoint With |
| `annotationproperty/OWLAnnotationPropertyDescriptionFrame` (3) | Domains (intersection) · Range (intersection) · Superproperties |
| `individual/OWLIndividualFrame` ("Description" view, 3) | Types · Same Individual As · Different Individuals |
| `individual/OWLIndividualPropertyAssertionsFrame` ("Property assertions" view, 4) | Object property assertions · Data property assertions · Negative object property assertions · Negative data property assertions |
| `datatype/OWLDatatypeDescriptionFrame` (1) | Datatype Definitions |
| `OWLAnnotationsFrame` (1) | Annotations (the entity's annotation assertions) |
| `OWLGeneralClassAxiomsFrame` (1) | General class axioms (all GCIs; Active Ontology tab) |
| `SWRLRulesFrame`, `InferredAxiomsFrame`, `AxiomListFrame` | Rules · Inferred axioms · Axioms |
| `ontology/OWLOntologyFrame` | only Inferred axioms; the annotation and import sections are commented out, and the ontology header is a separate view |

Property characteristics are **not frame sections**. They are checkbox views:
- `OWLObjectPropertyCharacteristics`: 7 checkboxes, Functional, Inverse functional, Transitive, Symmetric, Asymmetric, Reflexive, Irreflexive. Each toggle adds or removes the single characteristic axiom in the active ontology.
- `OWLDataPropertyCharacteristics`: Functional only.

The domain and range sections (`property/AbstractPropertyDomainFrameSection`, `…RangeFrameSection`) list asserted domain or range axioms. With a reasoner they add inferred direct domains and ranges (the reasoner's `getObjectPropertyDomains(p, true)`) that are not already shown.

### 7.5 Python

```python
# sip/owlcore/frames.py
@dataclass class FrameRow: section: str; axiom: Axiom; onto: IRI | None; context: IRI | None  # onto None ⇒ inferred/read-only
@dataclass class FrameSection: key: str; label: str; row_label: str; can_add: bool
    fill: Callable[[IRI, AxiomView], list[FrameRow]]; create_axiom: Callable[[IRI, Any], Axiom] | None
    resets_on: Callable[[Change, IRI], bool]
CLASS_FRAME = [equivalent_to, subclass_of, general_class_axioms, anonymous_ancestors, instances, target_for_key, disjoint_with, disjoint_union_of]
OBJECT_PROPERTY_FRAME = [...7], DATA_PROPERTY_FRAME = [...5], ANNOTATION_PROPERTY_FRAME=[...3], INDIVIDUAL_FRAME=[types, same_as, different_from], INDIVIDUAL_ASSERTIONS_FRAME=[...4]
def build_frame(entity, frame_spec, docs, reasoner=None) -> list[tuple[FrameSection, list[FrameRow]]]
def edit_row(row, new_axiom) -> list[Change]      # remove+add in row.onto, carry annotations
def add_to_section(section, entity, obj, location="active") -> list[Change]
```

This maps directly onto a JSON API for a web frame editor. The front-end posts Manchester text, which the server parses and turns into a change list.

---

## 8. Workspace structure, plugin.xml and extension points

### 8.1 Counts (from source)

| | `protege-editor-core/src/main/resources/plugin.xml` | `protege-editor-owl/src/main/resources/plugin.xml` |
|---|---|---|
| Lines | 304 | 1898 |
| `<extension>` elements | 29 | 186 |
| `<extension-point>` declarations | **12** | **12** |
| Menu actions (`EditorKitMenuAction`) | 25 | 103 |
| Workspace tabs | 0 | **7** active, plus 1 commented out (SPARQL, index Z) |
| View components | 0 | **51** |
| Preference panels | 3 | 8 (plus 1 explanation and 2 inference preference panels) |

### 8.2 Extension points: 24 in total

**Core** (`org.protege.editor.core.application.*`, 12):
- `EditorKitFactory`
- `WorkspaceTab`
- `ViewComponent`
- `ViewAction`
- `EditorKitMenuAction`
- `ToolBarAction`
- `preferencespanel`
- `explanationpreferencespanel`
- `EditorKitHook`
- `OntologyRepositoryFactory`
- `OntologyLoader`
- `OtherStartupActions`

**OWL** (`org.protege.editor.owl.*`, 12):
- `inference_reasonerfactory`
- `inference_preferences`
- `explanation`
- `inconsistentOntologyExplanation`
- `ui_renderer_entitycolorprovider`
- `moveaxiomskit`
- `io_listener`
- `ui_editor_description` (class-expression editor tabs)
- `repository` (catalog entry managers)
- `entity_renderer`
- `ExtraReasonerMenuAction`
- `searchmanager`

Registrations of the main OWL points in this repo:

| Point | Count | Registrations |
|---|---|---|
| `entity_renderer` | 4 | §4.1 |
| `ui_editor_description` | 4 | A "Class expression editor" (Manchester text), B "Class hierarchy" (pick a named class), C "Object restriction creator", D "Data restriction creator" |
| `moveaxiomskit` | 4 | by reference, by type, by profile, by definition |
| `repository` | 3 | `FolderGroupManager`, `ImportByNameManager`, `UriEntryManager` |
| `searchmanager` | 1 | `DefaultSearchManager` |
| `inference_reasonerfactory` | 1 | `NoOpReasoner` |
| `EditorKitFactory` | 1 | `OWLEditorKitFactory` |
| `EditorKitHook` | 1 | `InconsistentOntologyManager` |
| `OntologyRepositoryFactory` | 1 | TONES |

Each class-expression editor plugin also has an `editorKitId` and axiom-type filters, so the editor dialog shows tabs A–D for SubClassOf and EquivalentTo.

### 8.3 Tabs (7) and their default layouts (`resources/viewconfig-*.xml`)

| Index | Tab id | Label | Default views (layout file) |
|---|---|---|---|
| A | OWLOntologyTab | Active ontology | Ontology header, Ontology metrics, Imported ontologies, Ontology prefixes, General class axioms |
| B | OWLEntitesTab | Entities | Class hierarchy, Object property hierarchy, Data property hierarchy, Annotation property hierarchy, Datatypes, Individuals, Selected entity (card view) |
| C | OWLClassesTab | Classes | Class hierarchy, Class hierarchy (inferred) · Annotations, Usage · Description |
| D | OWLObjectPropertiesTab | Object properties | Object property hierarchy · Annotations, Usage · Characteristics, Description |
| E | OWLDataPropertiesTab | Data properties | Data property hierarchy · Annotations, Usage · Characteristics, Description |
| F | OWLAnnotationsPropertiesTab | Annotation properties | Annotation property hierarchy · Annotations, Usage · Description |
| G | OWLIndividualsTab | Individuals by class | Class hierarchy · Direct instances, Direct instances (inferred) · Annotations, Usage · Description, Property assertions |

Every tab class is `OWLWorkspaceViewsTab`; the layout is a split tree (`VSNode`, `HSNode`, `CNode`). For example, Classes is a vertical split 0.3/0.7, with the hierarchy on the left and a horizontal split 0.375/0.625 on the right holding Annotations+Usage and Description. `viewconfig-explanationtab.xml` also exists for the explanation workspace.

### 8.4 View components: 51, by category

- **Class (`@org.protege.classcategory`, 8):** Class hierarchy; Class hierarchy (inferred); Superclass hierarchy; Superclass hierarchy (inferred); Annotations; Description; General class axioms; Usage.
- **Object property (7):** Object property hierarchy; Object property hierarchy (inferred); Annotations; Description; Domains and ranges; Characteristics; Usage.
- **Data property (6):** Data property hierarchy; Description; Annotations; Domains and ranges; Characteristics; Usage.
- **Individual (9):** Individuals (list); Individuals by type; Individuals by type (inferred); Direct instances; Direct instances (inferred); Annotations; Description; Property assertions; Usage.
- **Annotation property (4):** Annotation property hierarchy; Annotations; Description; Usage.
- **Datatype (4):** Datatypes; Annotations; Description; Usage.
- **Ontology (`@org.protege.ontologycategory`, 10):** Ontology header; Ontology prefixes; Ontology metrics; Imported ontologies; Rules (SWRL); Classification results (inferred axioms); RDF/XML rendering; OWL/XML rendering; Manchester syntax rendering; OWL functional syntax rendering.
- **Uncategorised (3):** Selected entity (card); Axiom annotations; Manchester syntax entity rendering.

The `navigates` property marks views that drive the selection, such as the hierarchies, individual lists, Description views and the Manchester frame view.

### 8.5 Menus (from `EditorKitMenuAction`, core + OWL)

- **File (13):** New, Open, Open recent, Open from URL, Gather ontologies, Export inferred axioms, Reload, Edit ontology catalog file, Loaded ontology sources, Close, Save, Save as, Check for plugins.
- **Edit (23):** Undo, Redo, Find, Find in view, Cut, Copy, Copy sub-hierarchy as tab-indented text, Paste, Duplicate class, Create new, Create child, Create sibling, Convert to primitive, Convert to defined, Make primitive siblings disjoint, Make all individuals different, Make instances different, Add covering axiom, Remove local disjoints, Remove all disjoints, Deprecate, Merge into entity, Delete.
- **View (16 OWL items):**
  - renderer choice: IRI short name, prefixed name, rdfs:label, annotation property, custom
  - display toggles: axiom annotations inline, datatypes on annotation values, thumbnails, deprecated entities, relationships in hierarchy, display from ontology roots, breadcrumb trail
  - active-set strategies: active ontology only, imports closure, all loaded
  - Expand all
- **Window (11, core):** views, tabs, create/delete/export/import custom tabs, store layout, reset tab, log.
- **Refactor (13)** and **Tools (4):** Usage, Create class / object property / data property hierarchy (tab-indented text → hierarchy, `model/hierarchy/tabbed/*`).
- Context menus: asserted class hierarchy (18), entity banner (6), object property hierarchy (3), data property hierarchy (3), annotation property hierarchy (2), individuals (2).

### 8.6 Python/web mapping

- Keep a declarative registry, `sip/workspace/registry.py`, with `register_view(id, label, category, component, navigates=False)` and `register_tab(id, label, index, layout)`.
- Express the 7 default layouts as JSON split trees.
- Model the extension points as Python entry-point groups:
  - `sip.renderers`
  - `sip.class_expression_editors`
  - `sip.search_importers`
  - `sip.catalog_entry_managers`
  - `sip.io_listeners`
  - `sip.reasoners`
  - `sip.views`
  - `sip.tabs`
  - `sip.menu_actions`
  - `sip.preferences_panels`
- The selection model ("last selected class, property, individual") is a per-session store that views subscribe to.

---

## 9. Porting checklist (highest-value invariants)

1. **One user action = one change batch = one undo entry.** Minimise the batch, then log it after it is applied, and undo with the inverse batch in reversed order (§2).
2. **Class hierarchy semantics.**
   - Parents are the named superclasses plus the named conjuncts of intersections, from SubClassOf **and** EquivalentClasses.
   - Children are the inverse, but an equivalence edge needs an *anonymous* operand containing the parent as a conjunct.
   - Classes with no non-root parents, and top-level cycles, are terminal elements and go under owl:Thing.
   - Named-equivalent classes appear as synonyms (§3.3).
3. **Property hierarchy.** Only SubPropertyOf creates edges. Cycle members are shown under the top property, and equivalents are cycle mates plus explicit equivalents. All built-in annotation properties are always roots (§3.4).
4. **Rendering.** The default renderer is labels: rdfs:label, then skos:prefLabel, with the language list `[locale, locale-CC, "", en]`; property order wins over language order. Fall back to the longest matching prefix, then the IRI fragment. Quote with `'…'` when the name contains a space or `,<>=^@{}[]()\` (§4.1).
5. **Name → entity resolution goes through the rendering index**, which is what Manchester parsing uses. Collisions resolve to the entity most used in the active ontology (§4.2).
6. **Autocomplete.** Parse `text[:word] + "+**"`, read the expected kinds and keywords from the error, and prefix-match entities with the wildcard finder. Keywords come first; the list is capped at 100 (§5.3).
7. **Entity IRIs.** Base is the active ontology IRI, or the default `http://example.invalid/ontologies/ont.owl#`; separator `#`. Name-as-fragment replaces spaces with `_`; auto-ID defaults to `[type]_` + UUID. Optionally add an `rdfs:label@<first renderer lang>` and creator/date metadata. A duplicate name of the same type is an error, and auto-IDs avoid **any** existing IRI (§6).
8. **Imports resolution.** Order is catalog (with auto-generated `catalog-v001.xml` from the `xml:base` of the folder's files and their ontology IRIs), then an HTTP HEAD check, then asking the user. Missing imports are silent. Already-loaded ontologies are never replaced (§1.2).
9. **Save.** Keep the format the ontology was loaded with, defaulting to RDF/XML. Non-`file:` ontologies need Save As. Write to a temp file and then copy (§1.5).
10. **Metrics.** 43 counts in 6 groups over the imports closure, including GCI and hidden-GCI counts (§7.1).
