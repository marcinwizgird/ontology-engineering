> **Working notes — source-level reverse engineering.** Produced on 2026-10-04 by reading the source checkouts listed in [`../REVERSE_ENGINEERING.md`](../REVERSE_ENGINEERING.md) §1. Paths are relative to those checkouts. These notes are evidence for the port, not normative design; where the port deliberately deviates, `REVERSE_ENGINEERING.md` says so.

# Semantic Turkey 15.1.3: Governance and the Change Pipeline (reverse-engineering notes)

Scope: change-tracking SAIL, history/validation/undo/blacklist, projects and ACL, users, roles and RBAC, settings, URI generation, metadata registry, collaboration, notifications, and an inventory of service operations.
Sources (scratchpad `refs/`):

- `semanticturkey/st-changetracking-sail` (ChangeTracker SAIL, 4.5 kLOC)
- `semanticturkey/st-core-framework` (Project, RBAC, users, settings, aspects)
- `semanticturkey/st-core-services` (REST services)
- `semanticturkey/st-metadata-registry-{core,services}`
- These were downloaded during this pass, because `st-core-extensions.jar` in refs is a 404 HTML stub: `semanticturkey/st-native-template-based-uri-generator`, `st-coda-uri-generator`, `st-jira-backend`, `st-freedcamp-backend` (sources jars 15.1.3) and `coda/coda-converters` (CODA 2.2.3, which holds `TemplateBasedRandomIdGenerator`).
- `vocbench3/src/app/utils/AuthorizationEvaluator.ts` (client-side mirror of the capability goals)

Path abbreviations: `CT/` = `st-changetracking-sail/it/uniroma2/art/semanticturkey/changetracking/`, `FW/` = `st-core-framework/it/uniroma2/art/semanticturkey/`, `SV/` = `st-core-services/it/uniroma2/art/semanticturkey/services/core/`.

---

## 0. Big picture: how one write flows through ST

```
HTTP POST /semanticturkey/<ext>/<Service>/<op>?ctx_project=P&ctx_wgraph=...
 └─ Spring MVC → service proxy (STServiceAspect)
     ├─ @PreAuthorize("@auth.isAuthorized('rdf(concept)','C')")   (FW/security/STAuthorizationEvaluator)
     ├─ @Write  ==  @Transactional(readOnly=false, rollbackFor=Throwable)  (FW/services/annotations/Write.java)
     ├─ WritabilityCheckerInterceptor    (project not readOnly, shard exists & editable, repo writable)
     ├─ SchemesOwnershipCheckerInterceptor (UsersGroup scheme ownership, @SchemeAssignment/@Modified/@Deleted)
     ├─ RejectedTermsBlacklistingInterceptor (@TermCreation: reject blacklisted labels, attach blacklist template)
     ├─ HistoryMetadataInterceptor       (builds OperationMetadata; beforeCommit writes it to ct:commit-metadata)
     ├─ ResourceLifecycleEventPublisherInterceptor (ResourceCreated/Modified/Deleted → notifications after commit)
     └─ service body → getManagedConnection().add/remove/SPARQL update  (RDF4J RepositoryConnection)
           └─ Repository = SailRepository( [ShaclSail] → [TrivialInferencer] → ChangeTracker → NativeStore/GraphDB… )
                 ChangeTrackerConnection intercepts add/remove/clear/getStatements/evaluate
                 on commit → writes commit record into SUPPORT repository (history or validation graph)
```

Each project has a **core** repository (data: `main` for the main shard, or the shard name) and, when history or validation is on, a **support** repository (`support`) that holds the history, validation and blacklist graphs. The ChangeTracker is configured **inside the core repo's SAIL stack**, and it opens its own connection to the support repo (local via a RepositoryResolver, or remote via `HTTPRepository(serverURL, supportRepoId)`).

---

## 1. Change-tracking SAIL (`st-changetracking-sail`)

### 1.1 Files

| File | Role |
|---|---|
| `CT/sail/ChangeTracker.java` | `NotifyingSailWrapper`. Holds the config (supportRepoId, serverURL, metadataNS, historyGraph, validationGraph, blacklistGraph, include/exclude graphs, flags) and the in-memory `UndoStack`. Forces SERIALIZABLE isolation unless `interactiveNotifications == false`. |
| `CT/sail/ChangeTrackerConnection.java` (1597 lines) | The interceptor: add/remove/clear/getStatements/evaluate/commit/rollback, plus validation, undo and blacklist handling. |
| `CT/sail/StagingArea.java` | Per-transaction net delta: `Set<Statement> added, removed` plus `Model commitMetadata`. |
| `CT/sail/LoggingUpdateHandler.java` | Records the *requested* operations as `QuadPattern`s (null means wildcard) in validation mode. |
| `CT/sail/FlagUpdateHandler.java` | A boolean "transaction wrote something" flag (`readonlyHandler`). |
| `CT/sail/UndoStack.java`, `UndoSource.java` | In-memory undo (MAX_DEPTH=10) plus a visitor over the three undo sources. |
| `CT/sail/NILDecoder.java` | Maps `cl:null` / `sesame:nil` back to `null` (wildcards) when replaying quad patterns. |
| `CT/model/HistoryRepositories.java` | SPARQL helpers: `getTip`, `getAddedStaments`, `getRemovedStaments`, `getParent`, `getCommitUserMetadata`, `cloneValue`. |
| `CT/ChangeTrackerUtilities.checkChangeTrackingOnConnection` | Detects the tracker via `DESCRIBE <ct:SYSINFO?nonce=..> FROM ct:SYSINFO` and checks version, supportRepoId and serverURL. |
| `CT/sail/config/ChangeTrackerConfig/Factory/Schema` | RDF4J SAIL config: `supportRepositoryID, metadataNS, serverURL, historyGraph, includeGraph*, excludeGraph*, interactiveNotifications, historyEnabled, validationEnabled, validationGraph, blacklistingEnabled, blacklistGraph, undoEnabled`. |
| `CT/vocabulary/{CHANGELOG,CHANGETRACKER,VALIDATION,BLACKLIST,PROV}.java` | Vocabularies (listed below). |

### 1.2 Vocabularies (complete term lists)

**CHANGELOG** `cl: <http://semanticturkey.uniroma2.it/ns/changelog#>`
`cl:Quadruple, cl:subject, cl:predicate, cl:object, cl:context, cl:removedStatement, cl:addedStatement, cl:Commit, cl:parentCommit, cl:status, cl:MASTER, cl:tip, cl:null, cl:revisionNumber`. `CHANGELOG.isNull(v)` is true for `cl:null` or `sesame:nil` (legacy).

**CHANGETRACKER** `ct: <http://semanticturkey.uniroma2.it/ns/change-tracker#>`. These are virtual or control contexts and resources:
`ct:staged-additions, ct:staged-removals` (read the current tx delta), `ct:SYSINFO` (DESCRIBE-able virtual resource), `ct:graph-management` (context and resource holding `ct:includeGraph`, `ct:excludeGraph`, `ct:history-graph`, `ct:validation-graph`, `ct:blacklist-graph`), `ct:commit-metadata` (context *and* placeholder IRI for "the commit being created"), `ct:validation` (control context; predicates `ct:accept`, `ct:reject`, `ct:enabled`, plus `rdfs:comment`), `ct:undo` (control context and DESCRIBE-able virtual resource).

**VALIDATION** `val: <http://semanticturkey.uniroma2.it/ns/validation#>`. These are name-mangling prefixes:
- `stagingAddGraph(g)` = `IRI("…validation#staging-add-graph/" + g)`
- `stagingRemoveGraph(g)` = `IRI("…validation#staging-remove-graph/" + g)`
- `clearThroughGraph(g)` = `IRI("…validation#clear-through-graph/" + g)`
- the helpers `isAddGraph`, `isRemoveGraph`, `isAddGraphFor(staging, g)`, `unmangle*`, `isAddGraphSPARQL(var)`.

**STCHANGELOG** `stcl: <http://semanticturkey.uniroma2.it/ns/st-changelog#>` (FW/vocabulary): `stcl:performer, stcl:validator` (prov roles), `stcl:parameters`, `stcl:created, stcl:modified, stcl:deleted`.

**BLACKLIST** `blacklist: <http://semanticturkey.uniroma2.it/ns/blacklist#>`: `BlacklistedTerm, label, lowercasedLabel, concept, facet, template, templateType, parameterBinding, constantBinding, ntTerm`.

**SUPPORT** `<http://semanticturkey.uniroma2.it/ns/support/>`: graphs `support:history`, `support:validation`, `support:blacklist`. The per-project metadataNS is `computeMetadataNS(baseURI) = extendNamespace(baseURI,"metadata")`, and commit and quad IRIs are `metadataNS + UUID`.

PROV terms used: `prov:startedAtTime, prov:endedAtTime, prov:generated, prov:wasGeneratedBy, prov:generatedAtTime, prov:Entity, prov:used, prov:qualifiedAssociation, prov:Association, prov:agent, prov:hadRole`.

### 1.3 History graph data model (support repo, graph `support:history`)

```turtle
cl:MASTER cl:tip <m:c42> .                       # exactly one tip (else commits fail)
<m:c42> a cl:Commit ;
   prov:startedAtTime "…"^^xsd:dateTime ;        # tx begin()
   prov:endedAtTime   "…"^^xsd:dateTime ;
   cl:revisionNumber  42 ;                        # BigInteger, tip+1; first commit = 0
   cl:parentCommit    <m:c41> ;
   cl:status "committed" ;                        # or "triples-unknown" transiently; absent = in-flight
   prov:generated <m:mt42> ;
   # ---- user metadata copied from ct:commit-metadata (OperationMetadata.toRDF) ----
   prov:used <http://semanticturkey.uniroma2.it/services/it.uniroma2.art.semanticturkey/st-core-services/SKOS/createConcept> ;
   stcl:parameters [ a prov:Entity ;
        <…/SKOS/createConcept/param-0-newConcept> "…" ;   # literal string, or cl:null if absent
        <…/SKOS/createConcept/param-1-label> "\"cat\"@en" ] ;
   prov:qualifiedAssociation [ a prov:Association ; prov:agent <user IRI> ; prov:hadRole stcl:performer ] ;
   prov:qualifiedAssociation [ a prov:Association ; prov:agent <validator IRI> ; prov:hadRole stcl:validator ] ;  # only if accepted
   stcl:created <…/c_1a2b3c4d> ; stcl:modified <…> ; stcl:deleted <…> ;
   blacklist:template [ … ] .                    # only for @TermCreation ops in blacklisting projects
<m:mt42> a prov:Entity ; prov:wasGeneratedBy <m:c42> ; prov:generatedAtTime "…" ;
   cl:addedStatement <m:q1> ; cl:removedStatement <m:q2> .
<m:q1> a cl:Quadruple ; cl:subject <s> ; cl:predicate <p> ; cl:object <o> ; cl:context <g> .   # null ctx → cl:null
```

Parameter values are serialized as follows. The raw HTTP request parameter wins. Otherwise the code uses the `@Optional(defaultValue)`, then `toString()` for primitives and wrappers, then `getOriginalFilename()` for multipart files, and `null` → `cl:null`. Parameter IRIs are `operationIRI + "/param-" + index + "-" + name`. The operation IRI is `http://semanticturkey.uniroma2.it/services/<extensionPath>/<ServiceClass>/<method>`.

### 1.4 Validation graph data model (support repo, graph `support:validation`)

The structure is the same, but these are commits **pending validation**:
- there is no `cl:revisionNumber`, `cl:parentCommit` or `cl:MASTER`, and ordering uses `prov:endedAtTime`;
- quads are `QuadPattern`s, the *requested* operations rather than effective deltas, so any position may be `cl:null` (a wildcard removal);
- the user metadata is identical (performer, operation, parameters, blacklist template).

### 1.5 Interception rules (ChangeTrackerConnection)

`addStatement(s,p,o,ctxs…)`:
```
ctxs = list(ctxs)
if ct:validation in ctxs:  handleValidation(s,p,o); drop it
if ct:graph-management in ctxs: connectionLocalGraphManagement.add(s,p,o)  (copy-on-write of sail.graphManagement)
if ct:commit-metadata in ctxs: stagingArea.commitMetadata.add(s,p,o)
if ct:undo in ctxs:        handleUndo(s,p,o); drop it
if original ctxs empty or remaining ctxs non-empty:
    if pendingUndoFor: raise "Could not modify triples because of a pending undo"
    if validationEnabled (connection-local flag):
        validatableOperationHandler.addStatement(...)   # log QuadPattern per ctx
        ctxs = [stagingAddGraph(c) for c in ctxs]       # empty ctxs → NotValidatableOperationException
    else: readonlyHandler.addStatement(...)             # sets "dirty"
    delegate.addStatement(s,p,o,ctxs)
    on exception: readonlyHandler.recordCorruption(); re-raise
```
`removeStatements(s,p,o,ctxs…)` handles `graph-management` and `commit-metadata` the same way. In validation mode it does **not delete**. Instead:
- ground pattern: it adds `(s,p,o)` into `stagingRemoveGraph(c)`;
- non-ground pattern (any of s/p/o null): it reads the matching statements now and copies each into `stagingRemoveGraph(ctx)`, while the logged QuadPattern keeps the wildcards.
- Without validation it behaves as a normal remove plus the dirty flag.

`clear(ctxs…)` in validation mode:
- for `clearThroughGraph(g)`: if validation is currently enabled, clear `stagingAddGraph(g)` (cancel staged additions); otherwise clear `g`;
- for `stagingAddGraph(g)`: drop logged ops for g and clear it;
- for a normal `g`: log `remove(null,null,null,g)` and stage removal copies of all of g's triples;
- `clear()` with no args stages removal of every non-staging context.

`getStatements(..., ctxs)`: virtual contexts are served from memory and unioned with the real store:
- `ct:staged-additions` / `ct:staged-removals` give the current StagingArea sets;
- `ct:graph-management` gives the graph inclusion model;
- `ct:commit-metadata` gives the current metadata;
- `ct:validation` gives `(ct:validation ct:enabled <bool>)`.

`evaluate(DESCRIBE …)` with dataset default graph `ct:SYSINFO` or `ct:undo`: it generates virtual triples for any described IRI starting with that prefix (the nonce trick defeats caching). SYSINFO gives `schema:version`, `supportRepositoryID`, `serverURL`. UNDO gives the commit metadata of the pending undo.

`shouldTrackStatement(st)` is the history filter:
```
ctx = st.context or cl:null
if ctx starts with staging-add-graph/ or staging-remove-graph/: return False
included = (gm has includeGraph ctx) or (gm has includeGraph sesame:wildcard) or (no includeGraph at all)
if not included: return False
return not (gm has excludeGraph ctx or gm has excludeGraph sesame:wildcard)
```
The default config excludes the null context. In RDF4J the null context is where inferred triples live, so this ignores inference.

The SailConnectionListener (installed if history or undo is enabled) calls `stagingArea.stageAddition/stageRemoval` for **effective** changes notified by the underlying SAIL. RDF4J notifies only when a triple actually appears or disappears. StagingArea cancels self-inverse pairs:
```
stageAddition(st): if st in removed: removed.discard(st) else added.add(st)
stageRemoval(st):  if st in added:   added.discard(st)   else removed.add(st)
```

### 1.6 Commit algorithm (pseudo-code, faithful to `commit()`)

```python
def commit(self):
    with sail.lock:                                    # synchronized(sail)
        if not validatable_handler.is_read_only():     # VALIDATION MODE: log requested ops
            with support.connection() as s:
                s.begin()
                c  = iri(metaNS + uuid4()); mt = iri(metaNS + uuid4())
                s.add(c, RDF.type, CL.Commit, VG); s.add(c, PROV.startedAtTime, start_time, VG)
                s.add(c, PROV.endedAtTime, now(), VG); s.add(mt, RDF.type, PROV.Entity, VG)
                s.add(c, PROV.generated, mt, VG); s.add(mt, PROV.wasGeneratedBy, c, VG)
                s.add_all(rewrite(staging.commit_metadata, CT.commit_metadata -> c), VG)
                for qp in validatable_handler.additions: write_quad(mt, CL.addedStatement, qp, VG)   # null -> cl:null
                for qp in validatable_handler.removals:  write_quad(mt, CL.removedStatement, qp, VG)
                s.commit()

    if pending_undo_for:                               # see 1.9
        apply_undo_commit()
    elif readonly_handler.is_read_only():              # nothing (non-validation) written
        delegate.commit()                               # also the path for pure validation-mode txs
    elif not sail.history_enabled:                     # undo-only projects
        with sail.lock:
            try: delegate.commit()
            finally:
                if not staging.is_empty():
                    if sail.undo_stack: sail.undo_stack.push(staging); staging = StagingArea()
                    else: staging.clear()
    elif sail.interactive_notifications is True and staging.is_empty():
        delegate.commit()                               # store notified nothing → nothing to log
    else:
        with sail.lock:
            delegate.prepare()
            with support.connection() as s:            # PHASE 1: write metadata (status unset)
                s.begin()
                tips = s.get(CL.MASTER, CL.tip, None, HG)
                if len(tips) > 1: raise SailException("tip of MASTER is not unique")
                prev = tips[0].object if tips else None
                rev  = (int(s.value(prev, CL.revisionNumber, HG)) + 1) if prev else 0
                c = iri(metaNS + uuid4())
                s.add(c, RDF.type, CL.Commit); s.add(c, PROV.startedAtTime, start); s.add(c, PROV.endedAtTime, end)
                s.add(c, CL.revisionNumber, rev); s.add_all(rewrite(commit_metadata, ct:commit-metadata -> c))
                if staging.is_empty():                  # stores that notify only during commit (GraphDB)
                    triples_unknown = True; s.add(c, CL.status, "triples-unknown")
                else: record_modified_triples(c, s)     # mt entity + cl:Quadruple per stmt
                if prev: s.add(c, CL.parentCommit, prev); s.remove(CL.MASTER, CL.tip, prev)
                s.add(CL.MASTER, CL.tip, c)
                s.commit()
            try:
                delegate.commit()                       # PHASE 2: commit data
            except SailException:
                remove_last_commit(HG, c, prev, triples_unknown, update_tip=True)   # compensate
                raise
            if triples_unknown and staging.is_empty():  # truly nothing changed
                remove_last_commit(HG, c, prev, triples_unknown, True)
            else:                                       # PHASE 3: mark committed
                with support.connection() as s:
                    s.begin()
                    if triples_unknown: record_modified_triples(c, s)   # notifications arrived during commit
                    s.remove(c, CL.status, None, HG); s.add(c, CL.status, "committed", HG)
                    s.commit()
            staging.clear(); readonly_handler.clear(); validatable_handler.clear()

    if pending_validation:                              # accept/reject happened in this tx
        conditional_add_to_blacklist(support, pending_blacklisting, pending_comment)
        remove_last_commit(VG, pending_validation, None, False, False)   # drop the validation record
```

`remove_last_commit(graph, c, prevTip, triplesUnknown, updateTip)` uses SPARQL DELETEs in `graph`. It deletes the quads under `c prov:generated ?mt`, then the `?mt` resource, then `DESCRIBE c` (including bnode closures), and when updateTip is set it restores `cl:MASTER cl:tip prevTip`.

**Invariants / edge cases**
- The core and support repositories are **not** in one distributed transaction. Consistency rests on (a) the global `synchronized(sail)` lock, (b) metadata being written *before* the data commit and compensated on failure, and (c) `cl:status "committed"` as the success marker. A crash between phase 2 and phase 3 leaves a tip without a "committed" status. The status check that would reject later commits is commented out in 15.1.3.
- Revision numbers are dense and monotonic along MASTER. There is only one branch (MASTER).
- With validation enabled, normal writes leave `readonlyHandler` clean, so the history records nothing at write time. History entries for validated changes are created only at **accept** time.
- Namespace changes (`setNamespace`) are flagged only on the readonly handler, and the corresponding `FlagUpdateHandler` methods are commented out, so namespaces are effectively untracked.
- Isolation: `getDefaultIsolationLevel()` upgrades to a SERIALIZABLE-compatible level unless the config sets `interactiveNotifications=false`. `begin(level)` rejects incompatible levels. Concurrent writers are therefore serialized by the underlying store, plus the JVM-wide `synchronized(sail)` around the metadata writes.

### 1.7 Staging for VALIDATION: visibility semantics

- Staged additions are **real quads** in the core repo, in graph `val:staging-add-graph/<g>`.
- Staged removals are **copies** in `val:staging-remove-graph/<g>`. The original triple stays in `<g>` until it is accepted.
- So a SPARQL query over the RDF4J default dataset (the union of all graphs) **sees staged additions and still sees triples staged for removal**. A query that names `GRAPH <g>` sees neither the staged additions nor the effect of the staged removals.
- The UI distinguishes the cases through `FW/data/nature/NatureRecognitionOrchestrator.computeTripleScopeFromGraphs(graphs, wgraph)`, which returns `TripleScopes {local, staged, del_staged, imported, inferred}` with this precedence:
  - wgraph gives `local`;
  - an add-graph gives `staged` (unless already local or del_staged);
  - a remove-graph for the wgraph gives `del_staged` (it overrides local);
  - another graph gives `imported`;
  - nothing gives `inferred`.
- The SPARQL helpers `VALIDATION.isAddGraphSPARQL("?g")` are used in queries such as ResourceView, Search and Refactor to tag or filter.
- `FW/validation/ValidationUtilities`:
  - `executeWithoutValidation(enabled, conn, fn)` writes `(ct:validation ct:enabled false)` into the `ct:validation` context, flushes with a dummy `ASK {}`, runs fn, and then re-enables validation. It is used for data preloading.
  - `getAddGraphIfValidationEnabled` and `getRemoveGraphIfValidatonEnabled` return mangled graph names.
  - `isValidationEnabled(ctx)` is true only for the main shard of a validation project.

### 1.8 Accept / reject algorithm (`handleValidation`)

The service writes `conn.add(ct:validation, ct:accept|ct:reject, "<commitIRI>"literal, ct:validation)`, optionally adds `rdfs:comment` (the reject reason), and then commits.

```python
def handle_validation(pred, obj):
    if pred == CT.enabled: self.validation_enabled = bool(obj); return   # TRUE only if the sail supports it
    try:
        self.validation_enabled = False             # replayed ops go to the real graphs and to history
        with sail.lock:
            if pred == RDFS.comment: self.pending_comment = obj; return
            commit = IRI(str(obj))
            with support.connection() as s:
                s.begin()
                if pred == CT.accept:
                    for q in removed_patterns(s, commit, VG):            # NILDecoder: cl:null -> None
                        self.remove_statements(q.s, q.p, q.o, q.c)        # real delete (wildcards re-evaluated NOW)
                        self.remove_statements(q.s, q.p, q.o, staging_remove_graph(q.c))
                    for q in added_patterns(s, commit, VG):
                        self.add_statement(q.s, q.p, q.o, q.c)
                        self.remove_statements(q.s, q.p, q.o, staging_add_graph(q.c))
                    # carry the original performer/operation/params into the new history commit
                    staging.commit_metadata |= get_commit_user_metadata(s, commit, VG, rewrite_commit=True)
                elif pred == CT.reject:
                    for q in removed_patterns(...): self.remove_statements(..., staging_remove_graph(q.c))
                    for q in added_patterns(...):   self.remove_statements(..., staging_add_graph(q.c))
                    self.pending_blacklisting = commit
                else: raise SailException("Unrecognized operation")
                self.pending_validation = commit
                s.commit()
    finally:
        self.validation_enabled = True
```

On accept, the service first writes the validator association into `ct:commit-metadata`, using `OperationMetadata.setUserIRI(validator, stcl:validator)` with `@OmitHistoryMetadata` so the interceptor doesn't add its own. `getCommitUserMetadata` drops `cl:` predicates and objects (except `cl:null`) and also drops start/end/generated. The resulting history commit therefore has both the performer and the validator, keeps the original `prov:used` and parameters, and gets new timestamps.

After the data commit, `commit()` deletes the validation record (`removeLastCommit(VG, …)`) and, on reject, instantiates the blacklist (1.10).

Edge cases:
- Wildcard removals are re-evaluated at accept time, so they can delete triples added after staging.
- Accept and reject are one commit at a time. VocBench loops on the client side.
- `rejectCurrentUserCommit` checks with an ASK that the caller is an agent of the commit (any role), so users can withdraw their own changes without the `V` capability.

### 1.9 Undo

`Undo.undo()` (SV/Undo.java) does `con.add(bnode, prov:agent, <currentUser>, ct:undo)`, then `DESCRIBE <ct:undo?nonce=…> FROM ct:undo` to obtain the metadata of what is being undone, and returns a `CommitInfo` (operation, params parsed with `^param-(\d+)-(\w+)$`, created/modified/deleted).

`handleUndo(subj, prov:agent, user)` has these preconditions: there were no prior data writes or staged ops in the tx, the predicate is `prov:agent`, the object is an IRI, and no undo is already pending. It picks one of three sources:

| Mode (project flags) | Candidate | Applies now (in the core tx) | On commit |
|---|---|---|---|
| validation enabled | latest `cl:Commit` in VG by `prov:endedAtTime` whose performer = user | removes the staged quads from the staging-remove and staging-add graphs (cancels the pending change) | re-checks that it is still the latest ("Concurrent undo"), commits data, removes the commit from VG |
| history enabled | `cl:MASTER cl:tip ?c` with performer = user | re-adds the removed triples and removes the added ones in the original contexts | re-checks that the tip is unchanged, commits data, `removeLastCommit(HG, c, parent, updateTip=True)`, so **the history is truncated, not appended** |
| neither (undo only) | `sail.undoStack.peek()` with performer = user | inverse of the StagingArea | re-checks the stack tip, commits, pops |

`UndoStack.push(sa)` resets in three cases: the stack is at MAX_DEPTH=10 (`storage.clear()`, so it is a reset rather than a sliding window), the performer differs from the tip's performer (only same-user consecutive undos are possible), or the change has no performer. A mismatched performer raises "The performer of the last operation does not match…".

Note: in history mode only the **last commit globally** can be undone, and only by its author.

### 1.10 Blacklist (rejected-terms) feature

Preconditions: the project has `blacklistingEnabled`, which requires `validationEnabled` (createProject throws otherwise), and a `support:blacklist` graph.

1. **At creation** (`FW/services/aspects/RejectedTermsBlacklistingInterceptor`, applied to the 7 `@TermCreation(label=…, concept=…, facet=…)` operations):
   - It lowercases the label (locale of its language tag) and queries the support repo for `?t a blacklist:BlacklistedTerm; blacklist:lowercasedLabel <lc>`. If one is found it raises `BlacklistForbiddendException("The term … is blacklisted: <comments>")`, unless the `ctx_force=true` context param is set.
   - It writes a **template** into `ct:commit-metadata`:
```turtle
ct:commit-metadata blacklist:template _:t .
_:t blacklist:templateType blacklist:BlacklistedTerm ;
    blacklist:parameterBinding ( blacklist:label   <opIRI/param-i-label> ) ,
                               ( blacklist:concept <opIRI/param-j-concept> ) ;   # optional
    blacklist:constantBinding  ( blacklist:facet "prefLabel" ) .                   # optional
```
2. **At reject** (`conditionalAddToBlacklist`):
   - `DESCRIBE ?x {?commit stcl:parameters|blacklist:template ?x}`
   - creates a fresh bnode item, `a templateType`;
   - for each constantBinding `(p, c)` it adds `item p c`;
   - for each parameterBinding `(p, paramIRI)` it takes the parameter's xsd:string value, **parses it as N-Triples** (`NTriplesUtil.parseValue`), and adds `item p value`;
   - for each `blacklist:label` langString it adds a `lowercasedLabel`;
   - it adds `rdfs:comment` = the reject comment;
   - it writes into the blacklist graph only if a `lowercasedLabel` exists.
3. Service `Blacklist`: `clearBlacklist*` and `downloadBlacklist(format)` (no PreAuthorize yet; a TODO in the code).

### 1.11 Python translation (rdflib / Fuseki)

```
sip/governance/changetracking/
  vocab.py        CL, CT, VAL, STCL, BLACKLIST, SUPPORT namespaces (rdflib.Namespace); staging_add_graph(g) etc.
  delta.py        class StagingArea: added:set[Quad], removed:set[Quad], commit_metadata:Graph; stage_add/stage_remove
  patterns.py     QuadPattern(s,p,o,g) with None wildcard; encode/decode cl:null
  tracker.py      class ChangeTracker(config, core: QuadStore, support: QuadStore)
                  class TrackedTransaction (context manager): add(), remove(pattern), clear(g), sparql_update(),
                      set_commit_metadata(Graph), request_validation(accept|reject, commit, comment), request_undo(agent),
                      commit(), rollback()
  history.py      HistoryRepository(support, HG): tip(), next_revision(), write_commit(), mark_committed(), remove_commit()
  validation.py   ValidationRepository(support, VG): log_pending(), latest_by(agent), patterns(commit)
  undo.py         InMemoryUndoStack(max_depth=10); UndoSource = Literal['validation','history','stack']
  blacklist.py    BlacklistTemplate.from_operation(...); instantiate(template, params, comment) -> Graph; is_blacklisted(label)
  stores.py       QuadStore protocol; RdflibDatasetStore(rdflib.Dataset); FusekiStore(SPARQLUpdateStore + GSP)
```

Implementation guidance:
- **Interception.** rdflib has no SAIL listener, so all writes must go through `TrackedTransaction`. To get **effective** deltas (RDF4J semantics), `add(q)` stages q only if `q not in store`, and `remove(pattern)` first resolves the pattern to concrete quads (`store.quads(pattern)`) and stages the ones that exist.
- **SPARQL updates.** For `DELETE/INSERT … WHERE`, rewrite them as `SELECT` over the WHERE clause, instantiate the templates to concrete quads, then apply them through `add`/`remove`. rdflib's `rdflib.plugins.sparql.parser.parseUpdate` plus `algebra.translateUpdate` gives the templates. For Fuseki, the alternative is to compute the delta with a CONSTRUCT before applying.
- **Atomicity.** With Fuseki, put core and support in **one dataset** with the support graphs as named graphs (for example `urn:sip:support:history`). One `UPDATE` request carrying both the data delta and the commit record is then atomic, which removes the phase-1/2/3 compensation dance. With separate datasets, keep the ST 3-phase protocol and the `status` flag. Serialize commits per project with an `asyncio.Lock`/`threading.Lock` (equivalent to `synchronized(sail)`). Use optimistic concurrency on the tip: `ASK { cl:MASTER cl:tip <expected> }` inside the same update via `DELETE {…} INSERT {…} WHERE { cl:MASTER cl:tip ?t FILTER(?t = <expected>) }`.
- **Validation staging.** Keep ST's graph-mangling scheme exactly, because VocBench's UI semantics depend on it: `staging-add-graph/<g>` and `staging-remove-graph/<g>`.
- **History filter.** `include_graphs`/`exclude_graphs` with a `"*"` wildcard. Exclude the default graph and any inference graph.

---

## 2. History, Validation, Undo, Blacklist services

All of these read the **support** repo directly (`getProject().getRepositoryManager().getRepository("support")`). `SupportRepositoryUtils.obtainHistoryGraph(conn)` reads `ct:graph-management ct:history-graph ?g` through the virtual context.

### 2.1 `SV/History.java` (4 ops, all `@Read`)

| Operation | Auth | Semantics |
|---|---|---|
| `getTimeOfOrigin(resource?)` | `rdf(<typeof resource>)`,R | `min(prov:endedAtTime)` over commits, optionally those touching `resource` as subject (`prov:generated/(cl:addedStatement\|cl:removedStatement)/cl:subject`). Returns ISO zoned time. |
| `getCommitSummary(operationFilter[], performerFilter[], resourceFilter?, validatorFilter[], timeLowerBound?, timeUpperBound?, limit=DEFAULT_PAGE_SIZE, includeObjResourceFilter=false)` | `rdf(code)`,R | `SELECT (MAX(?rev) AS ?tipRevisionNumber) (COUNT(?commit) AS ?commitCount)` with filters. Returns `HistoryPaginationInfo(tipRevisionNumber or -1, pageCount=ceil(count/limit))`. |
| `getCommits(tipRevisionNumber, …filters…, operationSorting=Unordered, timeSorting=Descending, page=0, limit)` | `rdf(code)`,R | Inner SELECT with `FILTER(?revisionNumber <= tip)` (a stable pagination snapshot), ORDER BY, OFFSET page*limit, LIMIT. The outer query adds the optional `prov:used`, the parameters (GROUP_CONCAT `param$value` with `$` and `\` escaping), the performer and the validator. Returns `CommitInfo{commit, operation(+display), operationParameters, user(show="Given Family <email>" or machine clientId), startTime, endTime}`. |
| `getCommitDelta(commit, limit=100)` | `rdf(code)`,R | Added and removed quads (s,p,o,c, with `sesame:nil` mapped to the default graph) ordered by s,p,o,c, fetching limit+1 to compute `additionsTruncated`/`removalsTruncated`. |

The filters are built with `SupportRepositoryUtils.computeInCollectionSPARQLFilter(values, var)` (`FILTER(?var IN (…))`), `computeTimeBoundsSPARQLFilter` (on start/end time) and `computeFilterResourceAsInnerQuery(resource, graph, includeObj)` (commits whose quads have the resource as subject, and optionally as object).

### 2.2 `SV/Validation.java` (7 ops)

| Operation | Auth | Semantics |
|---|---|---|
| `getStagedCommitSummary(opFilter, performerFilter, tLow, tUp, limit, resourceFilter, includeObj)` | `rdf(code)`,V | Over VG: `MAX(endTime)` and count, giving `ValidationPaginationInfo(tipTime, pageCount)`. |
| `getCurrentUserStagedCommitSummary(...)` | none (any user) | The same with performerFilter = the current user. |
| `getCommits(…, page, limit, …)` | `rdf(code)`,V | Pending commits, sorted. Pagination uses `timeUpperBound` (mandatory) as the snapshot. |
| `getCurrentUserCommits(…)` | none | Only the caller's pending commits. |
| `accept(validatableCommit)` POST, `@Write @OmitHistoryMetadata` | `rdf(code)`,V | Writes the validator association into commit-metadata, flushes, then `add(ct:validation, ct:accept, "commit")`. |
| `reject(validatableCommit, comment?)` POST | `rdf(code)`,V | `add(ct:validation, ct:reject, "commit")` plus an optional `rdfs:comment`. |
| `rejectCurrentUserCommit(commit, comment?)` POST | none, but an ASK checks that the caller is an agent of the commit, else `OtherUsersCommitRejectionException` | Withdraws one's own change. |

### 2.3 `SV/Undo.java`: `undo()` POST `@Write` (no PreAuthorize: the performer check is in the SAIL). Returns the undone `CommitInfo`; `commit` is set only when the metadata holder is a real commit IRI.

### 2.4 `SV/Blacklist.java`: `clearBlacklist` (POST, marked @Read) and `downloadBlacklist(format=TURTLE)`.

### 2.5 Python translation
```
sip/services/history.py     HistoryService.get_time_of_origin / get_commit_summary / get_commits / get_commit_delta
sip/services/validation.py  ValidationService.{staged_summary, list_pending, accept, reject, reject_own}
sip/services/undo.py        UndoService.undo(user) -> CommitInfo
dataclasses: CommitInfo, ParameterInfo, CommitDelta, HistoryPaginationInfo(tip_revision, page_count)
query builder: sip/governance/changetracking/queries.py (same filter helpers, parameterised with rdflib initBindings)
```

---

## 3. Projects

### 3.1 Classes

| Class | Key content |
|---|---|
| `FW/project/Project.java` (1378 l.) | Persisted in `<STData>/projects/<name>/project.info` (Java properties). Reserved properties are listed below (3.2). It also holds `ProjectACL acl`, `ShardManager`, `VersionManager`, `OntologyImportSourceManager`, the URI generator and rendering engine plugins, and the `getRepositoryManager()` (an `STLocalRepositoryManager` per project dir). Repository ids are `CORE_REPOSITORY="core"`, `SUPPORT_REPOSITORY="support"`, `MAIN_REPOSITORY="main"` and `MAIN_SHARD="main"`. |
| `AbstractProject`, `CorruptedProject` | A CorruptedProject is listed but not usable. |
| `ProjectConsumer` | `SYSTEM` (the user-facing UI) or another `Project` (projects consume other projects, for example EDOAL left/right datasets or the DocTagging refDataset). |
| `FW/project/ProjectACL.java` | Covered in 3.3. |
| `FW/project/ProjectManager.java` (2166 l.) | Lifecycle: `createProject`, `accessProject`, `disconnectFromProject`, `deleteProject`, `clone/export/importProject`, `getProjectDescription` (without opening), property get/set, `checkAccessibility`, the inner `OpenProjectsHolder` (open projects with `Map<consumer, AccessLevel>` and a `LockStatus(consumer, level)`), and `handleProjectExclusively`. |
| `RepositoryAccess` → `CreateLocal`, `CreateRemote(serverURL,user,pwd)`, `AccessExistingRemote(serverURL,user,pwd)` | Where the core and support repositories live. |
| `RepositoryLocation{local,remote}`, `STRepositoryInfo` (backendType, credentials, searchStrategy), `ShardInfo`/`ShardManager` (multiple core shards; only `main` can have a support repo), `VersionInfo` (dump versions as separate repos), `ProjectVisibility{PUBLIC, AUTHORIZED, PRISTINE}`, `ProjectStatus`, `SHACLSettings`. | |

### 3.2 Project types and models

- **Model** (`model` prop) is one of `RDFS_MODEL` `http://www.w3.org/2000/01/rdf-schema`, `OWL_MODEL` `http://www.w3.org/2002/07/owl`, `SKOS_MODEL` `http://www.w3.org/2004/02/skos/core`, `ONTOLEXLEMON_MODEL` `http://www.w3.org/ns/lemon/ontolex`, `EDOAL_MODEL` `http://ns.inria.org/edoal/1.0/` or `DOC_TAGGING_MODEL` `https://selen.devistar.it/ns/tagging`.
- **Lexicalization model** (`lexicalizationModel`) is RDFS (`rdfs:label`), SKOS (`skos:prefLabel`…), SKOSXL `http://www.w3.org/2008/05/skos-xl` or OntoLex.
- `checkModels` adds one invariant: an OntoLex model requires the OntoLex lexicalization model. EDOAL requires `leftDataset` and `rightDataset` (each granted `R` access to the new project). DocTagging requires `refDataset` (which must be a SKOS project) and `docSet`.
- Only `ProjectType.continousEditing` is used.
- `project.info` reserved props: `name, labels(JSON map lang→label), baseURI, defaultNamespace, model, lexicalizationModel, timeStamp, created_at, openAtStartup, historyEnabled, validationEnabled, blacklistingEnabled, undoEnabled, readOnly, visibility, description, versions, shards, shardDefault, defaultRepositoryLocation, shaclEnabled, trivialInferencerEnabled, ontologyImportSources, plugins.mandatory.urigen.factoryID (default NativeTemplateBasedURIGenerator), plugins.mandatory.urigen.configType, plugins.mandatory.rendering.factoryID (default RDFSRenderingEngine), acl.acl, acl.lockLevel, leftDataset, rightDataset, refDataset, docSet`. Further config lives in `urigen.cfg` and `rendering.cfg`.

### 3.3 Project ACL and locks (exact semantics)

```java
enum AccessLevel { R, RW, EXT }   // resolveAccessibility(req, allowed) = req == allowed || allowed == RW
enum LockLevel   { W, R, NO }     // resolveLocking(req, allowed)    = req == allowed || req == NO || allowed == R
// persisted: acl.acl = "SYSTEM:RW,otherProject:R,*:R"  (default {SYSTEM:RW}); acl.lockLevel default R
```

- `ProjectACL.isAccessibleFrom(consumer, reqAccess, reqLock)` = `(allowsAccessWith(consumer, reqAccess) || isUniversallyAccessible(reqAccess)) && reqLock.isAcceptedBy(lockLevel)`.
- `allowsAccessWith` uses the consumer's ACL entry. If there is no entry and the universal (`*`) level is `EXT`, access is granted when the actor is an admin, when the actor is a non-admin with at least one role in the project's PU binding, or when the actor is any Machine.
- `ProjectManager.checkAccessibility(consumer, project, reqAccess, reqLock)` runs the ACL check and then, if the project is already open, applies these rules:
```
if openLock != NO and reqLock != NO        -> deny "already a lock"
if openLock == R                            -> deny any access          (R lock = exclusive)
if openLock == W and reqAccess == RW        -> deny RW                  (W lock = no other writers)
if openAccess == RW and reqLock != NO       -> deny lock request
if openAccess == R  and reqLock == R        -> deny R lock
```
- `accessProject(consumer, name, access, lock)` performs these steps in order:
  1. throws if the project is in `projectsLockedForAccess` (during delete or clone);
  2. calls `checkAccessibility`;
  3. if the project isn't open yet, `activateProject` opens its repositories;
  4. registers the consumer;
  5. ensures the PU and PG binding folders exist;
  6. fires `afterProjectInitialization` handlers and the `ProjectInitialized` event.
- Projects service ops: `updateAccessLevel/updateProjectAccessLevel/updateUniversalAccessLevel/updateLockLevel/...`, `getAccessStatusMap`.

### 3.4 Project creation (`ProjectManager.createProject`, called by `SV/Projects.createProject` with `@PreAuthorize("@auth.isSuperUser(false)")`)

The parameters are:
- identity and model: `consumer, projectName, model, lexicalizationModel, baseURI, defaultNamespace?`;
- change tracking: `historyEnabled, validationEnabled, blacklistingEnabled=false, undoEnabled=false, trivialInferenceEnabled=false`;
- repositories: `repositoryAccess, coreRepoID?, coreRepoSailConfigurerSpecification` (default `RDF4JRepositoryConfigurer` + `RDF4JNativeSailConfiguration`), `coreBackendType?, supportRepoID?, supportRepoSailConfigurerSpecification, supportBackendType?`;
- plugins: `uriGeneratorSpecification` (default NativeTemplateBasedURIGenerator), `renderingEngineSpecification?, resourceMetadataAssociations?`;
- preloading: `preloadedDataFileName?, preloadedDataFormat?, flattenGraphs, transitiveImportAllowance?`;
- dataset links: `leftDataset?, rightDataset?, refDataset?, docSet?`;
- SHACL: `shaclEnabled, shaclSettings?`;
- access and display: `openAtStartup, universalAccess?, visibility?, label?, description?, facets?`;
- integrations: `appCtx?, mdrRegistration?` (registers the project in the Metadata Registry).

The algorithm:
```
assert not (blacklisting and not validation)
check name, models; mkdir projectDir (fail if exists)
defaultNamespace = defaultNamespace or createDefaultNamespaceFromBaseURI(baseURI)
coreRepoId = "main" if shard == "main" else shard
needSupport = history or validation         (requires main shard)
needChangeTracker = needSupport or undo
if remote: coreRepoID ?= f"{name}-{shard}"; supportRepoID ?= f"{name}-support"
SAIL stack (innermost→outermost): backend → ChangeTracker(metadataNS=baseURI+metadata, undo, supportRepoID,
        history→support:history, validation→support:validation, blacklist→support:blacklist)
        → TrivialInferencer? → ShaclSail?(settings)
CreateRemote: fail if remote repo ids exist; add support then core configs; detect backend type
AccessExistingRemote: fail if repos do not exist; core/support become HTTPRepositoryConfig(url, user, pwd)
prepareProjectFiles(...)  → project.info, plugin configs
project = accessProject(consumer, name, RW, NO)
ensureBasicRepoInitialization(core)           (ontology header, prefixes)
RBACManager.loadRBACProcessor(project)
if preload: executeWithoutValidation(load file; update search index)
EDOAL/DocTagging dataset grants; universalAccess grant; resource-metadata associations
on any failure: rollback (delete dir, delete created remote repos)
```

### 3.5 Facets

`FW/settings/facets/ProjectFacets` is a Settings object with `category`, `organization` and `customFacets` (an STProperties instance whose schema is defined by `CustomProjectFacetsSchemaStore`). Facets are indexed in Lucene (`ProjectFacetsIndexLuceneUtils`) for `getFacetsAndValue`, `retrieveProjects(bagOf)` and `searchAndRetrieveProjectsAndFacets`. Built-in facet values also come from project properties (model, lexModel, history and validation flags, status).

### 3.6 Python translation
```
sip/governance/projects/
  model.py     @dataclass Project(name, base_uri, default_ns, model:Model, lex_model:LexModel, flags:ProjectFlags,
                                  visibility, labels, description, repos:RepoBinding(core, support, shards), plugins)
               Enum Model{RDFS,OWL,SKOS,ONTOLEX,EDOAL,DOC_TAGGING}; Enum LexModel{RDFS,SKOS,SKOSXL,ONTOLEX}
  acl.py       Enum AccessLevel{R,RW,EXT}; Enum LockLevel{W,R,NO}; class ProjectACL(entries: dict[str,AccessLevel], lock)
               accepts_access(req, allowed); accepts_lock(req, allowed); is_accessible_from(consumer, req, lock, actor)
  manager.py   class ProjectManager(store_root): create/access/disconnect/delete/clone/export/import; OpenProjects registry
  storage.py   project.yaml (instead of project.info) + Fuseki dataset provisioning (/$/datasets admin API)
  facets.py    ProjectFacets + whoosh/sqlite FTS index
```

---

## 4. Users, roles, capabilities, authorization

### 4.1 Data model

- **STUser** (`FW/user/STUser.java`, a Spring `UserDetails`) has `iri, givenName, familyName, password(encoded), email, url, avatarUrl, phone, affiliation, address, registrationDate, status:UserStatus{UNVERIFIED,NEW,ACTIVE,INACTIVE}, languageProficiencies, customProps(map IRI→String, user_custom_property_1..4), verificationToken, activationToken, samlLevel`.
  - `isAdmin()` means the IRI is in `CoreSystemSettings.adminList`.
  - `isSuperUser(strict)` means the IRI is in `superUserList` (with strict meaning "and not admin").
  - `isAnonymous()` means `email == SHOWVOC_VISITOR_EMAIL`.
  - Users are stored in `<STData>/users/<encodedIri>/details.ttl` (vocabulary `UserVocabulary`: `http://semanticturkey.uniroma2.it#User`, `…/puvoc#password`, …).
  - Registration: the **first registered user becomes ACTIVE and admin**. Afterwards, if email verification is enabled the user is UNVERIFIED and gets an email with a token (48h expiry); otherwise the user is NEW and the admin activates them.
- **Machine** (`FW/user/Machine.java`) is an API client (`clientId`, `isAdmin`, roles). It cannot belong to groups and skips scheme checks.
- **UsersGroup**: `iri = http://semanticturkey.uniroma2.it/groups/<shortName sanitized to [A-Za-z0-9._-], other runs replaced by '.'>`, plus `shortName, fullName, description, webPage, logoUrl`.
- **Role**: `(name, level ∈ {system, project})`. System roles are in `<STData>/system/roles/role_<name>.pl`; project-local roles are in `<projectDir>/roles/role_<name>.pl`. Machines have role lists.
- **ProjectUserBinding** (PU): `(project, user, roles:Collection<Role>, languages:Collection<String>, group:UsersGroup?, groupLimitation:boolean (puvoc:subjectToGroupLimitations), lastSessionId, lastSessionTimestamp)`. Stored in `<STData>/pu_binding/<project>/<user>/binding.ttl` (`puvoc:Binding, puvoc:role, puvoc:language, puvoc:group, puvoc:user, puvoc:project`).
- **ProjectGroupBinding** (PG): `(project, group, ownedSchemes:Collection<IRI>)` with `puvoc:owned_scheme`.
- `AuthManager.getActorRoles(project, includePublic)` returns the PU roles, plus `visitor` if the project visibility is PUBLIC; for a machine it returns machine.getRoles().

### 4.2 Capability language (Prolog, tuProlog engine)

Files: `FW/rbac/rbac_tbox.pl` (rules), `tuprolog_support.pl` (`char_subset`, `subset`, `split_string`) and `roles/role_*.pl` (facts). `RBACProcessor(roleFile)` loads tbox + support + role theory into one `alice.tuprolog.Prolog` engine. **There is one engine per (project, role)** in `RBACManager.rbacMap`. `authorizes(goal)` returns `engine.solve(goal).isSuccess()`; if the engine halts it is reset and `HarmingGoalException` is raised.

A capability is a Prolog term `area(topic[, scope])` plus a CRUDV string:
- areas: `rdf`, `rbac`, `pm`, `um`, `sys`, `cform`, `invokableReporter`, `customService`;
- `rdf` topics: RDF resource roles (`cls, individual, property, objectProperty, datatypeProperty, annotationProperty, ontologyProperty, ontology, dataRange, concept, conceptScheme, xLabel, xLabel(LANG), skosCollection, ontolexForm, ontolexLexicalEntry, limeLexicon, decompComponent`), the pseudo-topics `resource, skos, ontolex, lexicalization, lexicalization(LANGS), notes, code, import, datatype, dataset, sparql, graph, shacl, vartransTranslationSet`, and so on;
- scopes: `taxonomy, instances, lexicalization, lexicalization(LANGS), alignment, notes, values, definitions, schemes, range, version, lexicalForms, conceptualization, formRepresentations, support` (for sparql) and others;
- CRUDV is a subset of `C R U D V` (V = validate).

**Rule semantics** (`auth(TOPIC, Req) :- chk_capability(TOPIC, Have), char_subset(Req, Have).`). The `chk_capability(T, CRUDV)` expansions are:
1. `rdf(sparql,support)`: exact fact only (cut, no generalization).
2. Exact fact `capability(T, CRUDV)`.
3. `rdf(_)` or `rdf(_,_)` falls back to `capability(rdf, CRUDV)`. This is the general rdf capability, which is why "rdf R" grants read on everything.
4. `rdf(S)` matches `capability(rdf(A))` with `covered(S, A)`; `rdf(S, Scope)` matches `capability(rdf(A, Scope))` with `covered(S, A)`.
5. `rdf(S, lexicalization(L))` matches `capability(rdf(A, lexicalization(Cov)))` with `covered` and `resolveLANG(L, Cov)`. L and Cov are comma-separated lang lists, and every requested lang must be in the coverage.
6. `rdf(E)` or `rdf(E,_)` with E ∈ {concept, conceptScheme, skosCollection} matches `capability(rdf(skos))`; with E ∈ {ontolexForm, ontolexLexicalEntry, limeLexicon, decompComponent} it matches `capability(rdf(ontolex))`.
7. Lexicalization shortcuts:
   - `capability(rdf(lexicalization(Cov)))` grants `rdf(_, lexicalization(L))`, `rdf(xLabel(L))` and `rdf(xLabel(L),_)` (with the lang check);
   - `capability(rdf(lexicalization))` grants `rdf(_,lexicalization(_))`, `rdf(_,lexicalization)`, `rdf(xLabel…)`, `rdf(ontolexForm…)`, `rdf(ontolexLexicalEntry…)` and `rdf(limeLexicon…)`.
8. `rdf(_, notes)` matches `capability(rdf(notes))`.
9. `rbac(_)` or `rbac(_,_)` matches `capability(rbac)`; `cform(_)` or `cform(_,_)` matches `capability(cform)`.
10. `covered(Sub, resource)` holds for every `role(Sub)`. Also `objectProperty|datatypeProperty|annotationProperty|ontologyProperty ⊑ property`, `skosOrderedCollection ⊑ skosCollection`, and `covered(R,R)`.

Note: `pm(...)`, `um(...)`, `sys(...)`, `invokableReporter(...)` and `customService(...)` have **no generalization rules**. They must match a fact by unification, where a fact with `_` unifies with any scope (for example `capability(pm(project,_),"CRUD")`).

### 4.3 Predefined roles (verbatim from `FW/rbac/roles/*.pl`)

| Role | Capabilities |
|---|---|
| **visitor** | `rdf:R`, `sys(metadataRegistry):R` |
| **lurker** | `rdf:R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):R`, `customService(service):R` |
| **validator** | `rdf:RV`, `invokableReporter(reporter):R`, `customService(service):R` |
| **lexicographer** | `rdf(lexicalization):CRUD`, `rdf(notes):CRUD`, `rdf:R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):R`, `customService(service):R` |
| **mapper** | `rdf(resource, alignment):CRUD`, `rdf:R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):R`, `customService(service):R` |
| **thesaurus-editor** | `rdf(skos):CRUD`, `rdf:R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):R`, `customService(service):R` |
| **ontologist** | `rdf(resource):CRUDV`, `rdf(resource,_):CRUDV`, `rdf:R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):R`, `customService(service):R` |
| **rdfgeek** | `rdf:CRUDV`, `sys(metadataRegistry):R`, `invokableReporter(reporter):CRUD`, `invokableReporter(reporter,_):CRUD`, `customService(service):CRUD`, `customService(service,_):CRUD` |
| **projectmanager** | `rdf:CRUDV`, `rdf(sparql,support):R`, `rbac:CRUD`, `pm(project):RUV`, `pm(project,_):CRUD`, `pm(resourceMetadata,_):CRUD`, `cform:CRUD`, `um(user):R`, `sys(metadataRegistry):R`, `invokableReporter(reporter):CRUD`, `invokableReporter(reporter,_):CRUD`, `customService(service):CRUD`, `customService(service,_):CRUD` |

(`RBACManager.DefaultRole` lists these nine. **Admin** is not a role: it is a system-level flag that bypasses Prolog. **SuperUser** is a flag allowing project creation: `isSuperUser(false)`.)

Role administration (SV/Administration): `listRoles, listCapabilities, createRole, deleteRole, exportRole, importRole, cloneRole, addCapabilityToRole, removeCapabilityFromRole, updateCapabilityForRole`. Capabilities are added as strings like `rdf(concept), "CRUD"`, and `RBACManager.setCapabilities` rewrites the `.pl` file.

### 4.4 The authorization check

`@PreAuthorize("@auth.isAuthorized('rdf(' +@auth.typeof(#concept)+ ', lexicalization)', '{lang: ''' +@auth.langof(#literal)+ '''}', 'C')")`
- `@auth.typeof(res)` runs the QueryBuilder `processRole()` to return the RDFResourceRole name (concept, cls, …).
- `@auth.langof(literal | xLabel | SpecialValue)` returns the language tag.

`STAuthorizationEvaluator.isAuthorized(cap, userResp="{}", crudv, project=null)`:
```python
def is_authorized(cap, crudv, user_resp="{}", project_name=None):
    goal = f"auth({cap}, '{crudv}')."
    resp = json5.loads(user_resp)                      # single quotes / unquoted keys allowed
    actor = current_actor()
    if actor is None: return False
    target = project_by_name(project_name) if project_name else ctx_project_or_consumer()
    roles  = actor_roles(actor, target, include_public=True)
    req_access = RW if any(ch != 'R' for ch in crudv) else R
    if not check_acl(req_access, LockLevel.NO):        # consumer ≠ SYSTEM and ≠ project → ProjectManager.checkAccessibility
        return False
    if actor.is_admin(): return True
    ok = any(rbac(target, role).solves(goal) for role in roles)          # OR across roles
    langs = [l for l in as_list(resp.get("lang")) if l != "null"]
    if langs:
        assigned = pu_binding(actor, target).languages if is_user(actor) else []
        proj_langs = [l.tag for l in project_settings(target).languages or []]
        for l in langs:                                # every lang must be assigned AND a project language (case-insens.)
            if not (ci_in(l, assigned) and ci_in(l, proj_langs)): ok = False
    if req_access == RW and term_name(cap) == "rdf" and ctx.wgraph != project.base_uri:
        ok = ok and any(rbac(target, r).solves("auth(rdf(graph), 'U').") for r in roles)   # writing outside main graph
    return ok
```
Other evaluator predicates:
- `isAdmin()`, `isSuperUser(strict)`;
- `isAuthorizedInProject(cap, crudv, projectName)`;
- `isLoggedUser(email|iri)`;
- `isCtxProjectPublic`, `isProjectPublic(id)`;
- `isSettingsActionAuthorized(scope, crud)`:
  - SYSTEM: R needs superuser-or-admin, CUD needs admin;
  - PROJECT: R allowed, CUD needs `pm(project,_)`;
  - PROJECT_GROUP: R allowed, CUD needs `pm(project, group)`;
  - USER and PU: R allowed, CUD needs a non-anonymous user;
- `isDefaultSettingsActionAuthorized(scope, defaultScope, crud)`:
  - user@system: R or admin;
  - pu@project: R needs public visibility or the user bound to the project, CUD needs `pm(project,_)`;
  - pu@user: R allowed, CUD needs non-anonymous;
  - pu@system and project@system: R or admin;
- `isConfigurationActionAuthorized` (R always; CUD needs non-anonymous);
- `isSecretConfigurationActionAuthorized` (L always; SYSTEM needs admin; PROJECT needs admin or `pm(project,_)`);
- `isFileActionAuthorized(dir)`.

Usage statistics across 755 `@PreAuthorize`: `isAdmin()` 148, `sys(metadataRegistry)` 45, `rdf(resource)` 28, `rdf(resource, alignment)` 22, `rdf(property)` 21, `rdf(code)` 19, `rdf(concept)` 16, `rdf(import)` 15, `isSuperUser(false)` 14, and so on.

The client (`vocbench3/src/app/utils/AuthorizationEvaluator.ts`) evaluates the **same Prolog goals** with `jsprolog` against the capabilities returned by `Users.listUserCapabilities`. It maps `VBActionsEnum` to goals, for example `skosCreateTopConcept: 'auth(rdf(concept), "C").'`, `administrationRoleManagement: 'auth(rbac(_,_), "CRUD").'`, `collaboration: 'auth(pm(project, collaboration), "CRUD").'`.

### 4.5 Ownership via groups and schemes

`FW/user/SchemesOwnershipCheckerInterceptor` (advises service methods that have annotated params) applies only when the actor is an STUser, is not an admin, and has a group in the PU binding:
- a `@SchemeAssignment` param (an IRI or a list of IRIs) requires ownership of **all** of them (AND mode);
- a `@Modified` IRI: compute its schemes (a concept via `inScheme`-subproperties, a scheme itself, an xLabel of a concept or scheme, notes, and so on) and require **at least one** owned (OR mode);
- a `@Deleted` IRI: compute its schemes and require **all** owned.
- `ProjectGroupBindingsManager.hasUserOwnershipOfSchemes(actor, project, schemes, or)` returns true for machines, admins, users with no group, and users with `subjectToGroupLimitations=false`. It returns false if the group owns no schemes.
- A violation raises `OperationOnResourceDeniedException.missingSchemeOwnership(group)`.

### 4.6 Python translation (no Prolog dependency)

```
sip/governance/auth/
  terms.py        parse_term("rdf(concept, lexicalization(\"en,it\"))") -> Term(name, args) (tiny recursive-descent parser;
                  atoms, '_' wildcard, quoted strings)
  capability.py   @dataclass Capability(term: Term, crudv: frozenset[str]); Role(name, level, caps: list[Capability])
  engine.py       class CapabilityEngine: chk(term) -> Iterator[frozenset[str]]  implements rules 1-10 of §4.2 with
                  COVERED = {objectProperty:property, ..., skosOrderedCollection:skosCollection}; ROLE_TOPICS set;
                  VOCAB = {concept:skos, ..., limeLexicon:ontolex}; unify(fact_term, req_term) with '_' wildcard;
                  auth(term, req) = any(set(req) <= have for have in chk(term))
  roles/          visitor.yaml ... projectmanager.yaml  (same facts; loader also accepts legacy role_*.pl via regex
                  r'capability\((.+),\s*"([CRUDV]*)"\)\.')
  evaluator.py    AuthorizationEvaluator.is_authorized(cap, crudv, user_resp=None, project=None) – the algorithm of §4.4;
                  typeof(resource) (nature/role query), langof(value)
  decorators.py   @requires("rdf(concept)", "C") / @requires_expr(lambda ctx, **kw: ...) for FastAPI dependencies
  users.py        User, UserStatus, Machine, UsersRepository (TTL or SQLite), password hashing (argon2/bcrypt)
  groups.py       UsersGroup, ProjectGroupBinding(owned_schemes)
  bindings.py     ProjectUserBinding(roles, languages, group, group_limitations); BindingsRepository
  ownership.py    SchemeOwnershipChecker (AND for assigned/deleted, OR for modified)
```
Memoize `auth()` per (role set, goal). The rule set is small enough that a hand-written matcher is exact.

---

## 5. Settings framework, URI generation, CODA

### 5.1 Scopes and storage

`FW/resources/Scope.java`: `PROJECT("proj"), SYSTEM("sys"), USER("usr"), PROJECT_USER("pu"), PROJECT_GROUP("pg")`. `computeScope(project?, user?)` gives sys, usr, proj or pu. A relative reference such as `"proj:mySparqlQuery"` is parsed by `parseReference`.

Interfaces (`FW/extension/settings/`): `SystemSettingsManager<T>`, `ProjectSettingsManager<T>`, `UserSettingsManager<T>`, `PUSettingsManager<T>`, `PGSettingsManager<T>`, all over a `Settings` (STProperties) bean. `SettingsManager` is an IdentifiableComponent whose id is the plugin id. Each scope has a default chain.

Physical layout (`FW/properties/STPropertiesManager.java`, YAML-serialized STProperties with an `@type` key):
```
<STData>/system/plugins/<id>/settings.props                     SYSTEM
<STData>/system/plugins/<id>/user-settings-defaults.props       USER default@system
<STData>/system/plugins/<id>/pu-settings-defaults.props         PU default@system
<STData>/system/plugins/<id>/project-settings-defaults.props    PROJECT default@system
<STData>/projects/<p>/plugins/<id>/settings.props               PROJECT
<STData>/projects/<p>/plugins/<id>/pu-settings-defaults.props   PU default@project
<STData>/users/<enc(user)>/plugins/<id>/settings.props          USER
<STData>/users/<enc(user)>/plugins/<id>/pu-settings-defaults.props  PU default@user
<STData>/pu_binding/<p>/<enc(user)>/plugins/<id>/settings.props PU
<STData>/pg_binding/<p>/<group>/plugins/<id>/settings.props     PG
```
Resolution (`loadSettings(type, files…)`, later files override earlier):
- PU (non-explicit): `system default → user default → project default → [PG for user's group] → PU`. The PG and PU layers apply only to STUsers.
- PROJECT: `project default@system → project`.
- USER: `user default@system → user`.
- SYSTEM: the file only.
- `explicit=true` reads a single file without merging.
- Every store publishes `SettingsUpdated` or `SettingsDefaultsUpdated` events.

Core settings beans (`FW/settings/core/`):
- `CoreSystemSettings{adminList, superUserList, experimentalFeaturesEnabled, showFlags, emailVerification, projectCreation, preload, stDataVersion, mail, showvoc, allowAnonymous, authService, errorReporting, multiverse, projectsSearchGroups, selenSettings, digitalObjectsAnnotationEnabled, selenEnabled, datasetCatalogStatus, externalURL}`
- `CoreProjectSettings{languages, labelClashMode, resourceView, resViewPredLabelMappings, resViewSectionsCustomization, …, timeMachineEnabled, assertInverseOfBroader, wGraphBaseUriMap, …}`
- `CorePUSettings{editingLanguage, filterValueLanguages, activeSchemes, activeLexicon, showDeprecated, …, classTree, conceptTree, resourceView, notificationsStatus, rendering*…}`
- `CoreUserSettings{projectVisualization, favoriteDatasets, …}`
- `CorePGSettings{}` (group-level overrides of PU settings, for example limitations)

Service `SV/Settings.java` (17 ops): `getSettingManagers, getSettingsScopes, getSettings(componentID, scope), getSettingsDefault(componentID, scope, defaultScope), storeSettings, storeSetting(propertyName,value), storeSettingsDefault, storeSettingDefault, getSettingsForProjectAdministration, storeSettingForProjectAdministration, get/storePUSettingsUserDefault, get/storePUSettingsProjectDefault, getStartupSettings, get/setExternalURL`.

Python:
```
sip/governance/settings/scopes.py   Enum Scope(SYSTEM='sys',PROJECT='proj',USER='usr',PROJECT_USER='pu',PROJECT_GROUP='pg')
sip/governance/settings/store.py    SettingsStore(root): path_for(scope, plugin, project?, user?, group?, default_of?)
                                    load(model_cls, scope, ...) -> pydantic model via deep-merge of YAML layers (chain above)
sip/governance/settings/core.py     pydantic models CoreSystemSettings, CoreProjectSettings, CorePUSettings, ...
```

### 5.2 URI generation

- Extension point `FW/extension/extpts/urigen/URIGenerator.generateIRI(STServiceContext, String xRole, Map<String,Value> args)`.
- The xRoles are `concept, conceptScheme, xLabel, xNote, skosCollection, limeLexicon, ontolexLexicalEntry, ontolexForm, ontolexLexicalSense`. The parameter keys are `label, schemes, lexicalForm, lexicalizedResource, lexicalizationProperty, noteProperty, value, annotatedResource, title, canonicalForm, lexicon, entry, writtenRep, formProperty`.
- Services call `STServiceAdapter.generateIRI(xRole, valueMapping)`, which calls `project.getURIGenerator()`.
- `URIGeneratorProjectSettings.defaultXRole = "res"`.

**NativeTemplateBasedURIGenerator** (`st-native-template-based-uri-generator`) wraps CODA's `TemplateBasedRandomIdGenerator` (`coda-converters/.../converters/impl/TemplateBasedRandomIdGenerator.java`). The configuration is a Java `Properties` object (one template per xRole) whose defaults are:
```
concept  = c_${rand()}
xLabel   = xl_${lexicalForm.language}_${rand()}
xNote    = xNote_${rand()}
fallback = ${xRole}_${rand()}
uriRndCodeGenerator = TRUNCUUID8 (project property overrides), uriRndCodeLength = 8
```
`RandCode` values and their algorithms (`getRandomPart`):

| Code | Output |
|---|---|
| DATETIMEMS | `System.currentTimeMillis()` |
| UUID | full UUID4 string |
| TRUNCUUID4 | `uuid[0:4]` |
| TRUNCUUID8 (default) | `uuid[0:8]` |
| TRUNCUUID12 | `uuid[0:13]` (includes the first dash) |
| DIGIT | n chars from `[0-9]` (SecureRandom) |
| XDIGIT | n chars from `[0-9a-f]` |
| ALNUM | n chars from `[0-9a-z]` |

`rand()` syntax: `rand\((?<code>DATETIMEMS|UUID|…)(\s*,\s*(?<len>[1-9]\d*))?\)?`, for example `rand()`, `rand(DIGIT)`, `rand(ALNUM,6)`. The length applies only to DIGIT, XDIGIT and ALNUM.

Algorithm (`produceURI`):
```python
def produce_uri(ctx, x_role, args, max_attempts=5):
    x_role = x_role or ctx.default_x_role or "res"
    for _ in range(max_attempts):
        tpl = props.get(x_role) or DEFAULTS.get(x_role) or props.get("fallback", DEFAULTS["fallback"])
        local = ""
        while tpl:
            if tpl.startswith("${") or tpl.startswith("$${"):
                escaped = not tpl.startswith("$${")           # ${..} is URL-escaped, $${..} is raw
                start = 2 if escaped else 3; end = tpl.index("}")   # ValueError → "Missing closing brace"
                ph = tpl[start:end]
                m = RAND_RE.fullmatch(ph)
                val = random_part(m) if m else placeholder_value(ph, x_role, args)
                if val is None: raise ValueError(f'placeholder "{ph}" not present')
                if escaped: val = quote(re.sub(r"\s+", "_", val.strip()), safe=PATH_SEGMENT_SAFE)
                local += val; tpl = tpl[end+1:]
            else:
                nxt = re.search(r"\$(\$)?\{", tpl); cut = nxt.start() if nxt else len(tpl)
                local += tpl[:cut]; tpl = tpl[cut:]
        iri = URIRef(ctx.default_namespace + local)
        if not resource_exists(iri): return iri                # ASK {{?s ?p ?o} with iri in any position}
    raise ConversionException("Exceeded attempts … template lacks a random part?")
```
`placeholder_value(ph)` follows these rules:
- `xRole` gives the role name;
- otherwise `name([idx])?(.attr)?` is matched with the regex `([a-zA-Z]+)(?:\[([1-9]*\d)\])?(?:\.([a-zA-Z]+))?`;
- `args[name]` is looked up; an `[idx]` parses an xsd:string literal as a Turtle collection `( … )` and picks the item;
- `.attr` calls the method `attr()` or `getAttr()` on the RDF4J Value (for example `.language` gives `getLanguage()`, and an Optional is unwrapped). A missing language returns the string `"null"`.
- In Python, map the attributes to rdflib: `language`→`lit.language or "null"`, `datatype`, `label`→`str(lit)`, `localName`→`split_uri(iri)[1]`, `namespace`.

**CODA URI generator** (`st-coda-uri-generator`, overview only): `CODAURIGenerator` delegates to a CODA converter selected by contract IRI (`CODATemplateBasedURIGeneratorConfiguration` uses `templateBasedRandIdGen`; `CODAAnyURIGeneratorConfiguration` takes any converter IRI) via `CODACore`. CODA as a whole is the "Computer-aided Ontology Development Architecture": PEARL transformation rules mapping UIMA annotations or feature structures (and VocBench Custom Forms) to RDF, with pluggable converters (`coda:randIdGen`, `coda:default`, …). The CODA service in ST has 4 ops, and custom forms (CustomForms, 30 ops) rely on PEARL.

Python: `sip/governance/urigen/{base.py: URIGenerator protocol, native_template.py: TemplateURIGenerator(templates, rnd_code, rnd_len), randcodes.py}`. Use `secrets.choice` for DIGIT, XDIGIT and ALNUM.

---

## 6. Metadata registry, collaboration, notifications (high level)

### 6.1 Metadata Registry (`st-metadata-registry-core`, `-services`)

- `mdr/core/MetadataRegistryBackend` (impl `impl/MetadataRegistryBackendImpl`) is a system-level RDF repository describing datasets with DCAT 3, VoID, LIME and DCTerms. The custom vocabulary `METADATAREGISTRY` (`mdr:`) has these terms:
  - dataset structure: `DatasetArchetype` (abstract dataset), `DatasetRealization`, `MutableDatasetRealization`, `RDFDataset`;
  - linksets: `Linkset`, `LinksetRealization`, `RDFLinkset`, `sourceDataset`, `targetDataset`;
  - changesets: `Changeset`, `ChangesetRealization`, `RDFChangeset`, `prechangeDataset`, `postchangeDataset`;
  - provenance activities: `DatasetArchetypeCreationActivity`, `DatasetRealizationCreationActivity`, `DistributionGeneration`, `DownloadFromCatalog`;
  - identification and dereferencing: `shortName`, `dereferenciationSystem` with `standardDereferenciation` or `noDereferenciation`, `uriSpace`, `locator`;
  - SPARQL: `SPARQLEndpoint`, `sparqlEndpointLimitation`, `SPARQLEndpointLimitation`;
  - deployment: `Deployment`, `deployedDistribution`, `deployment`, `DeploymentToSparqlEndpoint`;
  - other: `lod`, `master`, `versionAtOrigin`, `distributionScheme`, `dataAtOrigin`.
- The API covers:
  - archetypes: `createDatasetArchetype`, `getDatasetAbstractions`, `export/importDatasetAbstractionMetadata`;
  - realizations and versions: `createDatasetRealization`, `getDatasetVersions(…)`;
  - distributions: `addDistribution`, `getDatasetDistributions`, `addSparqlEndpoint`;
  - changesets: `createChangeset(pre, post)`, `createChangesetVersion`, `addChangesetDistributionFile`;
  - deployments: `addDeployment`, `addDeploymentForDistribution`, `addConcreteDataset`;
  - root datasets: `listRootDatasets`, `filterRootDatasets`, `mergeRootDatasets`;
  - LIME: `addEmbeddedLexicalizationSet`, `discoverLexicalizationSets(distribution)` (a LIME profiler), `getComputedLexicalizationModel`;
  - profiling: `getClassPartitions` (VoID), `extractDistributionProfile`;
  - linkset discovery: `listConnectedDatasets`, `findDeployedDistributionForProject(project, shard)`.
- Graph naming per dataset: `<ds>-main`, `<ds>-stats`, `<ds>-sys` (with the `-abs` suffix stripped). `encodeShortName` replaces `[^\w-]+` with `_`.
- Service `mdr/services/MetadataRegistry.java` has 53 ops. Most are guarded by `sys(metadataRegistry)` (all roles have R; writes need admin or superuser).
- `ProjectShardLocator` binds projects to registry datasets, and `mdrRegistration` registers a project at creation.
- Related core services: `DatasetMetadata` (exporters: DCAT, DCAT-AP, ADMS, VoID/LIME, DataID, LOV, MDR; 5 ops), `DatasetCatalogs` (22 ops, external catalog connectors: LOV, BARTOC, OntoPortal, Data.europa.eu, …) and `Metadata` (28 ops, ontology import and prefix management).
- Python: `sip/registry/{model.py (pydantic DCAT/VoID/LIME), backend.py (named graph "urn:sip:mdr" in Fuseki), lime_profiler.py, void_stats.py}`.

### 6.2 Collaboration (issue trackers)

- Extension point `FW/extension/extpts/collaboration/CollaborationBackend` has these methods: `checkPrjConfiguration, getCreateIssueForm, createIssue(resource, form), assignProject(json), createProject(json), assignResourceToIssue(issue, res), removeResourceFromIssue, bind2project(project), listIssuesAssignedToResource(res), listIssues(pageOffset), listProjects, isProjectLinked`.
- Backends are `st-jira-backend` (JiraBackend + ProjectSettings{serverURL, projectKey…} + PUSettings{username, token}) and `st-freedcamp-backend`.
- Issue↔resource links live in the external tracker (labels or fields that carry the resource IRI).
- Service `Collaboration` (15 ops): `getCollaborationSystemStatus, activateCollaboratioOnProject, setCollaborationSystemActive, resetCollaborationOnProject, addPreferencesForCurrentUser, getIssueCreationForm, createIssue, assignProject, createProject, assignResourceToIssue, removeResourceFromIssue, listIssuesAssignedToResource, listIssues, listUsers, listProjects`. Auth is `pm(project, collaboration)` for setup.
- Python: `sip/collab/{base.py: IssueTracker Protocol, jira.py (REST v2/v3), github.py (bonus)}`.

### 6.3 Notifications

- `FW/notification/ResourceChangeNotificationManager`: `@TransactionalEventListener(AFTER_COMMIT) @Async` handlers for `ResourceCreated`, `ResourceModified` and `ResourceDeleted`. The events are published by `ResourceLifecycleEventPublisherInterceptor` from the same `@Created/@Modified/@Deleted` annotations that feed `stcl:created`, `stcl:modified` and `stcl:deleted`.
- Interested users are found in two ways:
  - (a) users **watching** a resource (`Notifications.startWatching(resource)`);
  - (b) users subscribed to (role, action) pairs in their preferences, with `Action ∈ {any, creation, deletion, update}`.
- Delivery depends on `NotificationMode` from PU settings `notificationsStatus` ∈ {`no_notifications`, `in_app_only`, `email_instant`, `email_daily_digest`}:
  - in_app_only and email_daily_digest store a `NotificationRecord(proj, resource, role, action, timestamp)` in a Lucene index (`UserNotificationsAPI`, guarded by a semaphore);
  - email_instant sends an HTML mail.
- The daily digest is scheduled by `scheduleNotificationDigest(cron, timezone)`.
- Service `Notifications` (11 ops): `scheduleNotificationDigest, getAvailableTimeZoneIds, startWatching, stopWatching, listWatching, isWatching, getNotificationPreferences, storeNotificationPreferences, updateNotificationPreferences, listNotifications, clearNotifications`.
- Python: `sip/governance/notify.py` with an event bus (post-commit hook of `TrackedTransaction`), a SQLite table `notifications(user, project, resource, role, action, ts)`, an APScheduler digest and an SMTP sender.

---

## 7. Service inventory (`@STServiceOperation` methods)

There are **942 operations in 69 service classes** in `st-core-services`, plus **53** in `st-metadata-registry-services` (`MetadataRegistry`), for **995** in total. Counts come from `grep -c @STServiceOperation`. Names come from a method-signature scan; GlobalSearch (8) and RemoteAlignmentServices (16) are each missing 1 name in the scan because of multi-line signatures. `*` marks a POST operation (`method = RequestMethod.POST`, typically `@Write`); others are GET (typically `@Read`).

Governance-relevant subtotals:
- History 4, Validation 7, Undo 1, Blacklist 2;
- Projects 67, Users 31, UsersGroups 15, Administration 27;
- Settings 17, Configurations 9, Notifications 11, Collaboration 15;
- MetadataRegistry 53, DatasetMetadata 5, DatasetCatalogs 22.

| Service | #ops | #POST | Operations |
|---|---:|---:|---|
| Administration | 27 | 18 | setAdministrator* removeAdministrator* setSuperUser* removeSuperUser* getDataDir setDataDir* setPreloadProfilerThreshold* testEmailConfig getProjectUserBinding getProjectUserBindingForAdministration getProjectUserBindings addRolesToUser* removeUserFromProject* removeRoleFromUser* updateLanguagesOfUserInProject* listRoles listCapabilities createRole* deleteRole* exportRole importRole* cloneRole* addCapabilityToRole* removeCapabilityFromRole* updateCapabilityForRole* downloadPrivacyStatement clonePUBinding*  |
| Alignment | 23 | 3 | searchResources getMappingCount getMappings filterMappings getAlignmentFormat exportMappings addAlignment getMappingProperties loadAlignment* listCells acceptAlignment acceptAllAlignment acceptAllAbove rejectAlignment rejectAllAlignment rejectAllUnder changeRelation changeMappingProperty applyValidation* applyValidationToEdoal* exportAlignment getSuggestedProperties closeSession  |
| ApiKeys | 4 | 3 | createApiKey* updateApiKey* deleteApiKey* getApiKeys  |
| Blacklist | 2 | 1 | clearBlacklist* downloadBlacklist  |
| CODA | 4 | 2 | isRemoteProvisioningEnabled setRemoteProvisioningEnabled* listConverterContracts validatePearl*  |
| Classes | 17 | 12 | getSubClasses getSuperClasses getClassesInfo getInstances getNumberOfInstances createClass* deleteClass* createInstance* deleteInstance* addSuperCls* removeSuperCls* addIntersectionOf* removeIntersectionOf* addUnionOf* removeUnionOf* addOneOf* removeOneOf*  |
| Collaboration | 15 | 9 | getCollaborationSystemStatus activateCollaboratioOnProject* setCollaborationSystemActive* resetCollaborationOnProject* addPreferencesForCurrentUser* getIssueCreationForm createIssue* assignProject* createProject* assignResourceToIssue* removeResourceFromIssue* listIssuesAssignedToResource listIssues listUsers listProjects  |
| Configurations | 9 | 3 | getConfigurationManagers getConfigurationManager getConfigurationReferences getConfiguration getFactoryConfigurationsMetadata getFactoryConfiguration storeConfiguration* deleteConfiguration* renameConfiguration*  |
| CustomContent | 8 | 6 | getCustomContentSettings getCustomMenu setHomeContent* setNavbarBrandContent* setHideJumbotron* setNavbarContent* seFooterContent* updateCustomMenu*  |
| CustomForms | 30 | 9 | removeReifiedResource* executeURIConverter executeLiteralConverter getFormCollection getAllFormCollections createFormCollection cloneFormCollection exportFormCollection importFormCollection* deleteFormCollection updateFromCollection* getAllCustomForms getCustomConstructors getCustomForm getCustomFormRepresentation createCustomForm* cloneCustomForm exportCustomForm importCustomForm* deleteCustomForm isFormLinkedToCollection updateCustomForm* validatePearl* getCustomFormConfigMap addFormsMapping removeFormCollectionOfResource updateReplace getBrokenCustomForms updateCustomFormWithAnnotations* inferPearlAnnotations*  |
| CustomServices | 14 | 9 | getCustomServiceIdentifiers getCustomServiceId createCustomService* getCustomService updateCustomService* deleteCustomService* getOperationForms addOperationToCustomService* updateOperationInCustomService* removeOperationFromCustomService* reloadCustomService* reloadCustomServices* importCustomService* exportCustomService  |
| CustomTrees | 2 | 0 | getRoots getChildrenResources  |
| CustomViews | 19 | 11 | getViewsIdentifiers createCustomView* updateCustomView* deleteCustomView* getCustomView suggestDynamicVectorCVFromCustomForm suggestAdvSingleValueCVFromCustomForm getValueCandidates listAssociations addAssociation* deleteAssociation* getViewData updateSparqlBasedData* updateSingleValueData* deleteSingleValueData* updateStaticVectorData* updateDynamicVectorData* exportCustomView importCustomView*  |
| DatasetCatalogs | 22 | 10 | getDatasetCatalogSuggestionForm sendDatasetCatalogSuggestionMail* searchDataset describeDataset getLatestVersion getDatasetCatalogSystemSettings getDatasetCatalogSettings getDatasetCatalogSettingsConfiguration setDatasetCatalogSettings* removeDatasetCatalogSettings* addDatasetCatalogSettings* getDatasetCatalogSettingsSchema initFactoryDatasetCatalogSettings* discoverNewDatasets* discoverNewDatasetsFromDatasetCatalog* listDiscoveredDatasets getDiscoveredDatasetsCountMap getVersionAwareDatasetsForUpdate crawlAndStoreNewVersions* crawlAndStoreNewVersionsForDatasetAbstraction* getDatasetVersionCrawlUpdates markVersionUpdateAsIgnored*  |
| DatasetMetadata | 5 | 3 | export* addMetadataToDataset* storeMetadataVocabularySettings* getMetadataVocabularySettings importMetadataVocabulariesFromMetadataRegistry  |
| Datatypes | 13 | 6 | createDatatype* deleteDatatype* getDatatypes getDeclaredDatatypes getOWL2DatatypeMap getRDF11XmlSchemaBuiltinDatatypes getBuiltinDatatypes setDatatypeEnumerationRestrictions* setDatatypeManchesterRestriction* setDatatypeFacetsRestriction* deleteDatatypeRestriction* getRestrictionDescription getDatatypeRestrictions  |
| Diffing | 12 | 7 | runDiffing* getAllTasksInfo deleteTask* getTaskResult storeTaskResult* getDiffingServiceForm getDiffingServices setActiveDiffingService* getActiveDiffingService addDiffingService* updateDiffingService* deleteDiffingService*  |
| DigitalObjectAnnotation | 10 | 5 | annotateDigitalObject* searchDigitalObjects searchObjectsByOrganization getDigitalObjectsCountByOrganization retrieveAdoptingOrganizations retrieveAnnotation deleteDigitalObject* clearData* exportDigitalObjects* importDigitalObjects*  |
| DocTagging | 4 | 1 | getProjectCoordinates tagDocument* listFiles findDocset  |
| Docgen | 2 | 0 | buildOWLDocumentation buildSKOSDocumentation  |
| Download | 17 | 14 | createDistribution* uploadDistribution* addExternalDistribution* deleteDistribution* deleteChangesetDistributionFile* deleteLinksetDistributionFile* createDownload* createAlignmentDownload* createExternalDownload* uploadFile* getAvailableFormats removeDownload* removeExternalDistribution* getDownloadInfoList getFile updateLocalized* updateLocalizedMap*  |
| EDOAL | 12 | 8 | getAlignedProjects createAlignment* getAlignments createCorrespondence* setLeftEntity* setRightEntity* setRelation* setMeasure* setMappingProperty* deleteCorrespondence* getSuggestedProperties getCorrespondences  |
| Export | 4 | 1 | getNamedGraphs getOutputFormats getExportFormats export*  |
| Extensions | 3 | 0 | getExtensionPoints getExtensionPoint getExtensions  |
| GlobalSearch | 8 | 6 | createIndex* clearSpecificIndex* clearAllIndex* deleteAllIndexes* clearIndexForNotExistingProjects* search* translation  |
| Graph | 4 | 0 | getGraphModel expandGraphModelNode expandSubResources expandSuperResources  |
| History | 4 | 0 | getTimeOfOrigin getCommitSummary getCommits getCommitDelta  |
| HttpResolution | 8 | 2 | getContentNegotiationSettings storeContentNegotiationSettings* getUri2ProjectSettings storeUri2ProjectSettings* contentNegotiation rdfProvider getBrowsingInfo getMappedProject  |
| ICV | 38 | 12 | explain listConsistencyViolations listDanglingConcepts listDanglingConceptsForAllSchemes listConceptSchemesWithNoTopConcept listConceptsWithNoScheme listTopConceptsWithBroader listResourcesWithNoSKOSPrefLabel listResourcesWithNoSKOSXLPrefLabel listDanglingXLabels listResourcesWithAltNoPrefLabel listResourcesNoLexicalization listConceptsExactMatchDisjoint listConceptsRelatedDisjoint listResourcesWithMorePrefLabelSameLang listResourcesWithNoLanguageTagForLabel listResourcesWithExtraSpacesInLabel listResourcesWithSameLabels listResourcesWithOverlappedLabels listResourcesNoDef listConceptsHierarchicalCycles listConceptsHierarchicalRedundancies listAlignedNamespaces listBrokenAlignments* listBrokenDefinitions listLocalInvalidURIs listResourcesURIWithSpace setAllDanglingAsTopConcept* setBroaderForAllDangling* removeAllDanglingFromScheme* deleteAllDanglingConcepts* addAllConceptsToScheme* removeBroadersToConcept* removeBroadersToAllConcepts* removeAllAsTopConceptsWithBroader* removeAllHierarchicalRedundancy* deleteAllDanglingXLabel* setDanglingXLabel*  |
| Individuals | 3 | 0 | getNamedTypes addType removeType  |
| InputOutput | 6 | 2 | getSupportedFormats getParserFormatForFileName getWriterFormatForFileName loadRDF* clearData* getInputRDFFormats  |
| InvokableReporters | 14 | 7 | getInvokableReporterForm getConfigurationScopes getInvokableReporterIdentifiers getInvokableReporter deleteInvokableReporter* createInvokableReporter* importInvokableReporter* exportInvokableReporter updateInvokableReporter* addSectionToReporter* updateSectionInReporter* removeSectionFromReporter* compileReport compileAndExportReport  |
| LexicographerView | 2 | 0 | getMorphosyntacticProperties getLexicalEntryView  |
| MAPLE | 4 | 1 | profileProject* checkProjectMetadataAvailability profileMatchingProblemBetweenProjects profileSingleResourceMatchProblem  |
| Machines | 9 | 8 | listMachines createMachine* updateMachineClientID* updateMachineOrganization* addRoleToMachine* updateMachineRoles* removeRoleFromMachine* setAdmin* deleteMachine*  |
| ManchesterHandler | 10 | 3 | getAllDLExpression getExpression isClassAxiom checkExpression checkDatatypeExpression checkLiteralEnumerationExpression checkObjectPropertyExpression createRestriction* removeExpression* updateExpression*  |
| Metadata | 28 | 21 | getBaseURI getDefaultNamespace setDefaultNamespace* getNamespaceMappings expandQName setNSPrefixMapping* changeNSPrefixMapping* removeNSPrefixMapping* getNamedGraphs getImports addFromLocalFile* addFromMirror* addFromWeb* addFromWebToMirror* addFromLocalProject* removeImport* downloadFromWeb* downloadFromWebToMirror* getFromLocalFile* getFromLocalProject* getFromMirror* updateFromWeb* updateFromWebToMirror* updateFromLocalFile* updateFromLocalProject* updateFromMirror* disconnectFromProject* getStats  |
| Multiverse | 4 | 2 | createWorld* listWorlds listAlternativeWorldInfos destroyWorld*  |
| Notifications | 11 | 6 | scheduleNotificationDigest* getAvailableTimeZoneIds startWatching* stopWatching* listWatching isWatching getNotificationPreferences storeNotificationPreferences* updateNotificationPreferences* listNotifications clearNotifications*  |
| OntManager | 3 | 2 | getOntologyMirror deleteOntologyMirrorEntry* updateOntologyMirrorEntry*  |
| OntoLexLemon | 46 | 33 | createLexicon* getLexicons deleteLexicon* getLexiconLanguage addDefinition* removeDefinition* updateDefinition* createLexicalEntry* getLexicalEntryLanguage getLexicalEntriesByAlphabeticIndex countLexicalEntriesByAlphabeticIndex deleteLexicalEntry* getLexicalEntryIndex getLexicalEntryLexicons getLexicalEntrySenses addSubterm* removeSubterm* setLexicalEntryConstituents* clearLexicalEntryConstituents* setCanonicalForm* addOtherForm* removeForm* addFormRepresentation* updateFormRepresentation* removeFormRepresentation* getFormLanguage addLexicalization* removeLexicalization* removePlainLexicalization* removeReifiedLexicalization* addConceptualization* removePlainConceptualization* removeConceptualization* removeSense* setReference* addConcept* removeConcept* getLexicalRelationCategories getSenseRelationCategories getConceptualRelationCategories createLexicoSemanticRelation* deleteLexicalRelation* deleteSenseRelation* createTranslationSet* getTranslationSets deleteTranslationSet*  |
| ProjectTemplates | 5 | 3 | listTemplates createTemplate* getTemplateConfiguration updateTemplate* deleteTemplate*  |
| Projects | 67 | 41 | getContextRepositoryBackend createProject* createEmptySHACLSettingsForm projectExists listProjects isProjectExisting getProjectInfo getAccessStatusMap getAccessStatus updateAccessLevel* updateProjectAccessLevel* updateUniversalAccessLevel* updateUniversalProjectAccessLevel* updateLockLevel* updateProjectLockLevel* setProjectLabels* deleteProject* deleteAllFacetsIndexes* accessProject* accessAllProjects* disconnectFromAllProjects* disconnectFromProject* cloneProject* exportProject* getProjectPropertyMap getProjectPropertyFileContent saveProjectPropertyFileContent* setProjectProperty* setProjectFacets* getProjectFacets getProjectFacetsForm getCustomProjectFacetsSchema setCustomProjectFacetsSchema* getRepositories modifyRepositoryAccessCredentials* batchModifyRepostoryAccessCredentials* preloadDataFromFile* preloadDataFromURL* preloadDataFromCatalog* getFacetsAndValue createFacetIndex* recreateFacetIndexForProject* retrieveProjects* searchAndRetrieveProjectsAndFacets* setBlacklistingEnabled* setSHACLValidationEnabled* isSHACLValidationEnabled setQueryTimeout* getQueryTimeoutValue isQueryEvaluationExceptionForTimeoutEnabled setUndoEnabled* isUndoEnabled setTrivialInferenceEnabled* isTrivialInferenceEnabled setReadOnly* setVisibility* makePublic* makeStaging* isChangeTrackerSetUp setOpenAtStartup* getOpenAtStartup getRenderingEngineConfiguration updateRenderingEngineConfiguration* getURIGeneratorConfiguration updateURIGeneratorConfiguration* listSearchProjectsGroups getProjectShardBackingRepository  |
| Properties | 43 | 21 | getTopProperties getTopRDFProperties getTopObjectProperties getTopDatatypeProperties getTopAnnotationProperties getTopOntologyProperties getFlatProperties getPropertiesInfo getPropertiesLexicalizations* getSubProperties getSuperProperties getRelevantPropertiesForResource getRelevantPropertiesForClass getRelevantDomainClasses getRelevantRangeClasses getRange areSubPropertiesUsed createProperty* deleteProperty* addEquivalentProperty* removeEquivalentProperty* addPropertyDisjointWith* removePropertyDisjointWith* addInverseProperty* removeInverseProperty* addSuperProperty* addPropertyChainAxiom* removePropertyChainAxiom* updatePropertyChainAxiom* removeSuperProperty* addPropertyDomain* removePropertyDomain* addPropertyRange* removePropertyRange* setDataRange* removeDataranges* updateDataranges* addValueToDatarange addValuesToDatarange hasValueInDatarange removeValueFromDatarange getDatarangeLiterals getInverseProperties  |
| Refactor | 7 | 3 | changeResourceURI replaceBaseURI* migrateDefaultGraphToBaseURIGraph SKOStoSKOSXL SKOSXLtoSKOS spawnNewConceptFromLabel* moveXLabelToResource*  |
| RemoteAlignmentServices | 16 | 9 | getServiceMetadata searchMatchers* listTasks downloadAlignment fetchAlignment* createTask* deleteTask* getRemoteAlignmentServices getRemoteAlignmentServiceForm addRemoteAlignmentService* updateRemoteAlignmentService* getDefaultRemoteAlignmentServiceId deleteRemoteAlignmentService* setAlignmentServiceForProject* removeAlignmentServiceForProject*  |
| Repositories | 3 | 3 | getRemoteRepositories* restartRemoteRepository* deleteRemoteRepositories*  |
| ResourceMetadata | 15 | 9 | listAssociations addAssociation* deleteAssociation* getPatternIdentifiers getFactoryPatternIdentifiers getLibraryPatternIdentifiers getPattern createPattern* updatePattern* deletePattern* importPatternFromLibrary* storePatternInLibrary* clonePattern* importPattern* exportPattern  |
| ResourceView | 3 | 0 | getResourceView getResourceViewAtTime getLexicalizationProperties  |
| Resources | 17 | 13 | updateTriple* updateTripleValue* updateLexicalization* updateTriplePredicate* updateFlatLexicalizationProperty* updatePredicateObject* removePredicateObject* removeValue* addValue* setDeprecated* getResourceDescription getResourcesInfo* getResourcePosition getResourcesPosition* getOutgoingTriples updateResourceTriplesDescription* validateIRIList  |
| SHACL | 7 | 5 | loadShapes* exportShapes clearShapes* batchValidation extractCFfromShapeFile* extractCFfromShapesGraph* extractCFfromShapeURL*  |
| SKOS | 43 | 30 | getTopConcepts countTopConcepts getNarrowerConcepts getBroaderConcepts getAllSchemes getSchemesMatrixPerConcept getCollectionsForConcept getRootCollections getNestedCollections getSuperCollections failingReadServiceContainingUpdate createConcept* createConceptScheme* setPrefLabel* addAltLabel* addHiddenLabel* addBroaderConcept* addConceptToScheme* addMultipleConceptsToScheme* addTopConcept* addToCollection* addFirstToOrderedCollection* addInPositionToOrderedCollection* addLastToOrderedCollection* removeConceptFromScheme* removeTopConcept* removePrefLabel* removeAltLabel* getAltLabels removeBroaderConcept* removeHiddenLabel* isSchemeEmpty deleteConceptScheme* deleteConcept* createCollection* deleteCollection* deleteOrderedCollection* removeFromCollection* removeFromOrderedCollection* addNote* removeNote* updateNote* updateNoteProperty*  |
| SKOSXL | 13 | 10 | getPrefLabel getAltLabels getHiddenLabels addAltLabel* addHiddenLabel* prefToAtlLabel* altToPrefLabel* setPrefLabel* removePrefLabel* removeAltLabel* removeHiddenLabel* changeLabelInfo* updateSKOSXLLexicalizationProperty*  |
| SPARQL | 5 | 4 | evaluateQuery* executeUpdate* exportQueryResultAsSpreadsheet* exportGraphQueryResultAsRdf* suggestEndpointsForFederation  |
| Search | 14 | 2 | createIndexes updateIndexes customSearch advancedSearch* searchAlignedResources searchResource searchStringList searchURIList searchInstancesOfClass searchLexicalEntry getPathFromRoot searchPrefix getCustomSearchSettings storeCustomSearchSettings*  |
| Selen | 24 | 11 | getEndpointUrl getSettings storeSettings* getServiceStatus me selfRegister* createUser* listConfigurations listDocsets findDocset createDocset* deleteDocset* updateDocset* hasPathFinderCapability listFiles createDir* deleteFileOrDirectory* createFile* search findPath extractFileContentById downloadFileById docsetFileTagging* fileTagging*  |
| Services | 6 | 0 | getExtensionPaths getServiceClasses getServiceOperations getServiceOperation getServiceOperationAsCustomService getServiceInvocationForm  |
| Settings | 17 | 8 | getSettingManagers getSettingsScopes getSettings getSettingsDefault storeSettings* storeSetting* storeSettingsDefault* storeSettingDefault* getSettingsForProjectAdministration storeSettingForProjectAdministration* getPUSettingsUserDefault storePUSettingUserDefault* getPUSettingsProjectDefault storePUSettingProjectDefault* getStartupSettings getExternalURL setExternalURL*  |
| Sheet2RDF | 38 | 21 | uploadSpreadsheet* uploadDBInfo* getSupportedDBDrivers listSheetNames getHeaders getSheetHeaders getHeaderFromId ignoreHeader* addSimpleGraphApplicationToHeader* addAdvancedGraphApplicationToHeader* updateSimpleGraphApplication* updateAdvancedGraphApplication* updateGraphApplicationDelete* removeGraphApplicationFromHeader* isNodeIdAlreadyUsed addNodeToHeader* updateNodeInHeader* updateRuleSanitization* renameNodeId* removeNodeFromHeader* replicateMultipleHeader* updateSubjectHeader* getTablePreview getPearl savePearl* validateGraphPattern* uploadPearl* getTriplesPreview addTriples exportTriples getPrefixMappings exportSheetStatus exportGlobalStatus importSheetStatus* importGlobalStatus* getDefaultAdvancedGraphApplicationConfigurations getConfiguration closeSession  |
| ShowVoc | 14 | 9 | setAllowAnonymous* testVocbenchConfiguration getContributionReferences submitContribution* rejectContribution* approveStableContribution* approveDevelopmentContribution* approveMetadataContribution* approveDatasetCatalogContribution* loadStableContributionData* loadDevContributionData* searchDataset describeDataset dataDump  |
| Storage | 6 | 4 | list createDirectory* deleteDirectory* createFile* deleteFile* getFile  |
| TripleStore | 14 | 8 | getTripleStoreSettings listInstances createInstance* updateInstance* deleteInstance* listConfigurations getConfigurationDetails createConfiguration* updateConfiguration* deleteConfiguration* getDefaultInstances setDefaultInstance* getDefaultConfigurations setDefaultConfig*  |
| Undo | 1 | 1 | undo*  |
| Users | 31 | 25 | getUser listUsers listUserCapabilities listUsersBoundToProject listProjectsBoundToUser createUser* registerUser* verifyUserEmail* activateRegisteredUser* updateUserGivenName* updateUserFamilyName* updateUserEmail* updateUserPhone* updateUserAddress* updateUserAffiliation* updateUserUrl* updateUserAvatarUrl* updateUserLanguageProficiencies* enableUser* deleteUser* changePassword* forcePassword* forgotPassword* resetPassword* getUserFormFields updateUserFormOptionalFieldVisibility* addUserFormCustomField* updateUserFormCustomField* swapUserFormCustomFields* removeUserFormCustomField* updateUserCustomField*  |
| UsersGroups | 15 | 12 | listGroups getGroup createGroup* updateGroupShortName* updateGroupFullName* updateGroupDescription* updateGroupWebPage* updateGroupLogoUrl* deleteGroup* assignGroupToUser* setGroupLimitationsToUser* removeGroupFromUser* addOwnedSchemeToGroup* removeOwnedSchemeFromGroup* getProjectGroupBinding  |
| Validation | 7 | 3 | getStagedCommitSummary getCurrentUserStagedCommitSummary getCommits getCurrentUserCommits accept* reject* rejectCurrentUserCommit*  |
| Versions | 20 | 12 | listDeploymentConfigurations storeDeploymentConfiguration* deleteDeploymentConfiguration* getDeploymentConfiguration getDeploymentConfigurationParameters listRepositoryConfigurations storeRepositoryConfiguration* deleteRepositoryConfiguration* getRepositoryConfiguration getRepositoryConfigurationParameters getVersionsAndDistributions getVersions createVersionDumpUsingDeployer* createVersionDumpUsingRepository* loadVersionDumpIntoRepository* createEditableFork* loadNewVersion* closeVersion* deleteVersion* deleteShard*  |
| XKOS | 5 | 0 | getCorrespondences getAssociations getSingleAssociation exportAssociations filterAssociations  |
| XMLSchema | 6 | 0 | formatDateTime formatDate formatTime formatDuration formatCurrentLocalDateTime formatCurrentUTCDateTime  |
| MetadataRegistry | 53 | 21 | downloadMetadata createDatasetAbstraction* addLODRealization* deleteDatasetAbstraction* checkShortNameExists getDatasetAbstractions getLocalDeploymentLocation getDatasetVersions getDatasetRealizationsForProject getDatasetDistributions getDatasetChangesetFiles getDatasetCatalogConnector getDeployedDataset getDeployedDatasetVersion getCurrentVersionForProject setAsCurrentVersion* setDatasetRealizationVersion* getAbstractionForDataset findDatasetAbstractionForProject findDeployedDistributionForProject getProjectsForDatasetAbstraction listRootDatasets filterRootDatasets mergeRootDatasets* listConnectedDatasets getDatasetMetadata2 getEmbeddedLexicalizationSets deleteEmbeddedLexicalizationSet* addEmbeddedLexicalizationSet* assessLexicalizationModel* getEmbeddedLinksets getLinksetDistributionFiles getClassPartitions addSparqlEndpoint* deleteDeploymentForDistribution* evaluateQuery* getComputedLexicalizationModel createConcreteDataset* setDereferenciability* setSPARQLEndpointLimitation* removeSPARQLEndpointLimitation* getSPARQLEndpointLimitations getCatalogRecord deleteCatalogRecord* findDataset findDatasets discoverDatasetMetadata discoverDataset* exportDatasetVersionMetadata exportDatasetAbstractionMetadata importDatasetVersionMetadata* importDatasetAbstractionMetadata* bulkSetMainShardsAsNonEditable*  |
| **Total** | **995** | | (942 core + 53 MDR) |

---

## 8. Cross-cutting invariants checklist (for the Python re-implementation)

1. **Every data write goes through the tracker.** No direct store writes from services, because otherwise history, validation and undo silently diverge.
2. **History records effective deltas.** Re-adding an existing triple is not recorded, and add+remove of the same triple in one tx cancels out.
3. **Validation records requested ops**, which can be wildcards, and stages them in mangled graphs. Writes without an explicit graph are rejected in validation mode.
4. **Accept** replays the staged ops against real graphs with validation temporarily off. That produces a normal history commit with the performer and validator, and then deletes the validation record. **Reject** removes the staged quads, optionally blacklists the term, and deletes the record.
5. **One MASTER tip.** Revision = parent+1, and `cl:status "committed"` marks durable success. Undo in history mode truncates the tip.
6. **Undo is author-only and last-only**, and cannot be mixed with other writes in the same tx.
7. **Authorization = ACL(consumer) ∧ (admin ∨ ∃role: goal) ∧ lang-responsibility ∧ (wgraph≠base ⇒ rdf(graph) U) ∧ scheme ownership.**
8. **Settings are layered** (system default → user default → project default → PG → PU), and later layers win per property.
9. **URI generation** is template-based, retries 5 times on collision, and uses the project's default namespace.

## 9. Proposed Python package map (summary)

```
sip/
  governance/
    changetracking/  vocab, delta, patterns, tracker, history, validation, undo, blacklist, stores, queries
    projects/        model, acl, manager, storage, facets
    auth/            terms, capability, engine, roles/*.yaml, evaluator, decorators, users, groups, bindings, ownership
    settings/        scopes, store, core
    urigen/          base, native_template, randcodes
    notify.py
  registry/          model, backend, lime_profiler, void_stats
  collab/            base, jira
  services/          history, validation, undo, blacklist, projects, users, administration, settings, ... (FastAPI routers;
                     path shape /semanticturkey/it.uniroma2.art.semanticturkey/st-core-services/<Service>/<op> kept
                     for VocBench3 client compatibility; ctx_project / ctx_wgraph / ctx_consumer query params)
```

## 10. Open points / caveats

- `ProjectVisibility.PRISTINE`: its exact semantics weren't traced. The services `makePublic`/`makeStaging`/`setVisibility` exist; it is likely the ShowVoc "staging" (not yet public) state.
- The Spring XML wiring that orders the aspects (`*PostProcessor` classes) was not inspected. The order given in section 0 is logical rather than verified.
- `@Read`-annotated `Blacklist.clearBlacklist` is POST without PreAuthorize, which is an upstream TODO.
- GraphDB-specific `triples-unknown` handling is unnecessary when the Python tracker computes deltas itself.
