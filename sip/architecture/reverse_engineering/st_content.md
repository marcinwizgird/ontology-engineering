> **Working notes — source-level reverse engineering.** Produced on 2026-10-04 by reading the source checkouts listed in [`../REVERSE_ENGINEERING.md`](../REVERSE_ENGINEERING.md) §1. Paths are relative to those checkouts. These notes are evidence for the port, not normative design; where the port deliberately deviates, `REVERSE_ENGINEERING.md` says so.

# Semantic Turkey / VocBench 3 — Content & Knowledge-Editing Services (reverse-engineering report)

Source base: ST **15.1.3** sources jars (Maven Central), extracted under
`scratchpad/refs/semanticturkey/{st-core-framework,st-core-services}`, plus extension sources jars I
downloaded into `scratchpad/refs/semanticturkey/ext/` (the local `st-core-extensions.jar` is a 404 HTML
page, not a jar): `st-regex-search-strategy`, `st-graphdb-search-strategy`, eight `*-rdf-transformer`s,
`st-rdf-deserializing-lifter`, `st-rdf-serializing-exporter`, `st-http-loader`,
`st-graph-store-http-deployer`, `st-edoal-stdflat-transformer` (all 15.1.3).
Client: `scratchpad/refs/vocbench3/src/app`.

Abbreviations: `SVC = st-core-services/it/uniroma2/art/semanticturkey/services/core`,
`FW = st-core-framework/it/uniroma2/art/semanticturkey`, `WG` = working graph (project base-URI graph),
`QB` = `QueryBuilder` (FW `data/access` / `services` support), `nature` = ST's packed resource
classification (see §1.4).

Operation counts (`@STServiceOperation`, counted per file): SKOS 43, SKOSXL 13, Classes 17, Properties 43,
Individuals 3, Resources 17, Refactor 7, ICV 38, Search 14, InputOutput 6, Export 4, Alignment 23,
EDOAL 12, MAPLE 4, CustomForms 30, SPARQL 5, Datatypes 13, ManchesterHandler 10, OntoLexLemon 46, XKOS 5.

---------------------------------------------------------------------------------------------------

## 0. Cross-cutting conventions (needed for every port)

| Convention | Source | Port rule |
|---|---|---|
| Every write goes to `getWorkingGraph()` (= project base-URI named graph). Deletes are also **restricted to WG** (`GRAPH ?g {..}` with `?g := WG` or `conn.remove(model, WG)`). Imported graphs are read-only. | all write ops | `store.add(triples, graph=wg)`, `store.remove(triples, graph=wg)`; never touch other graphs |
| Reads are over the union of all graphs (default dataset = all contexts), `includeInferred=false` unless stated. | QB default | rdflib `ConjunctiveGraph`/`Dataset(default_union=True)`; Fuseki `?default-graph-uri` unset + `tdb:unionDefaultGraph` |
| `@LocallyDefined` param validator: resource must exist in the project (`hasStatement(res,?,?)` or default namespace). `@NotLocallyDefined`: must **not** exist (used on `newX` IRIs). | FW `constraints` | `validators.locally_defined(res)` decorator |
| `@Modified/@Created/@Deleted(role=..)` feed `ResourceLevelChangeMetadataSupport` → history/metadata (dct:modified, dct:created). | all writes | emit a `ChangeEvent(created/modified/deleted, res, role)` |
| Writes collect `modelAdditions`/`modelRemovals` then `conn.add(add, WG); conn.remove(rem, WG)` — order: add first, then remove, in one transaction (change-tracking SAIL records the diff). | SKOS, Classes,... | `with store.transaction(): add(); remove()` (if a triple is in both, it ends removed — keep ordering) |
| Lexicalization model of project: `RDFS` (rdfs:label), `SKOS` (skos:*Label), `SKOSXL` (skosxl:*Label→xl:Label→literalForm), `OntoLex` (ontolex:isDenotedBy). Many ops branch on it. | `Project.*_LEXICALIZATION_MODEL` | `project.lex_model: Literal["rdfs","skos","skosxl","ontolex"]` |
| Results are `AnnotatedValue` = `{value, attributes: {show, role, nature, qname, explicit, more, ...}}`, produced by `QB.processRendering()/processQName()/processRole()` and the nature SPARQL fragment. | FW `services/AnnotatedValue` | `@dataclass AnnotatedValue(value, attrs: dict)` |
| New IRIs come from the URI generator extension (`generateIRI(role, args)`; roles concept, conceptScheme, skosCollection, xLabel, xNote, ontolexLexicalEntry...; args label, schemes, lexicalizedResource, lexicalForm, lexicalizationProperty, noteProperty). Default = native template generator (`${rand()}` style). | `URIGenerator` | `UriGenerator.generate(role, **args)`; default template `{ns}c_{uuid8}` / `{ns}xl_{lang}_{uuid8}` |

---------------------------------------------------------------------------------------------------

## 1. Resource View (`SVC/ResourceView.java`, `SVC/resourceview/**`)

### 1.1 Files
- `ResourceView.java` (1706 lines): ops `getResourceView`, `getResourceViewAtTime`, `getLexicalizationProperties`.
- `resourceview/StatementConsumerProvider.java`: registry of **29 factory section consumers** + per-project templates.
- `resourceview/AbstractStatementConsumer.java`: show/role/nature/qname/tripleScope helpers.
- `resourceview/AbstractPropertyMatchingStatementConsumer.java`: the generic section algorithm.
- `resourceview/LazySectionStatementConsumer.java` (only `collections` is lazy).
- `resourceview/consumers/*.java` (31 files incl. `PropertyFacetsSection`/serializer).
- Templates (section order per role): `FW/properties/it.uniroma2.art.semanticturkey.settings.core.SemanticTurkeyCoreSettingsManager/project-settings-defaults.props` (YAML, key `resourceView.templates`), overridable per project, plus `resourceView.customSections: {name: {matchedProperties: [...]}}`.
- Nature/tripleScope: `FW/data/nature/NatureRecognitionOrchestrator.java`, `TripleScopes.java`.
- Resource position: `FW/data/access/ResourceLocator.java`.

### 1.2 Section consumers (name → matched properties, behaviour options)
Defaults of `BehaviorOptions`: rootProperties=HIDE, collection=IGNORE, subproperties=INCLUDE,
renderingEngine=INCLUDE, noRootProperties=MATCH_EVERYTHING.

| # | section key | class | matched props | non-default options |
|---|---|---|---|---|
| 1 | types | TypesStatementConsumer | rdf:type | |
| 2 | classaxioms | ClassAxiomsStatementConsumer | owl:equivalentClass, rdfs:subClassOf, owl:disjointWith, owl:complementOf, owl:intersectionOf, owl:oneOf, owl:unionOf | rootProps=SHOW |
| 3 | datatypeDefinitions | DatatypeDefinitions… | owl:equivalentClass | |
| 4 | lexicalizations | Lexicalizations… | rdfs:label, skos:prefLabel/altLabel/hiddenLabel, skosxl:prefLabel/altLabel/hiddenLabel, ontolex:isDenotedBy | rootProps=SHOW |
| 5 | broaders | Broaders… | skos:broader | |
| 6 | equivalentProperties | EquivalentProperty… | owl:equivalentProperty | |
| 7 | disjointProperties | PropertyDisjointWith… | owl:propertyDisjointWith | |
| 8 | superproperties | SubPropertyOf… | rdfs:subPropertyOf | |
| 9 | subPropertyChains | PropertyChain… | owl:propertyChainAxiom | collection=ALWAYS_ASSUME_COLLECTION, rendering=EXCLUDE |
| 10 | facets | PropertyFacets… (custom, not property-matching) | rdf:type (+subprops) for 7 characteristics + owl:inverseOf | see below |
| 11 | domains | Domains… | rdfs:domain | |
| 12 | ranges | Ranges… | rdfs:range | |
| 13 | imports | OntologyImports… | owl:imports | subproperties=EXCLUDE |
| 14 | properties | OtherProperties… | ∅ → matches **everything not yet processed** | |
| 15 | topconceptof | TopConceptOf… | skos:topConceptOf | |
| 16 | schemes | InScheme… | skos:inScheme | |
| 17 | members | SKOSCollectionMembers… | skos:member | |
| 18 | membersOrdered | SKOSOrderedCollectionMembers… | skos:memberList | ALWAYS_ASSUME_COLLECTION |
| 19 | labelRelations | LabelRelations… | skosxl:labelRelation | |
| 20 | notes | SKOSNotes… | skos:note | |
| 21 | lexicalForms | LexicalForms… | ontolex:lexicalForm | rootProps=SHOW_IF_INFORMATIVE |
| 22 | lexicalSenses | LexicalSenses… | ontolex:sense | |
| 23 | denotations | Denotations… | ontolex:denotes | |
| 24 | evokedLexicalConcepts | EvokedLexicalConcepts | ontolex:evokes | |
| 25 | subterms | Subterms… | decomp:subterm | |
| 26 | constituents | Constituents… | decomp:constituent | sorts by decomp position, else by show |
| 27 | formRepresentations | FormRepresentations… | ontolex:representation | |
| 28 | rdfsMembers | RDFSMembers… | rdfs:member + every `rdf:_N` predicate present | rootProps=HIDE; numeric sort of `rdf:_N`; empty section kept only for lexical entries |
| 29 | collections | MemberOfSKOSCollection… (Lazy) | — | returns empty `LazySection`; client calls `SKOS.getCollectionsForConcept` |

Because subproperties are INCLUDEd, e.g. `skos:definition` (⊑ skos:note) lands in **notes**, and
`skos:exactMatch` would land in **properties** (not a subproperty of broader). Order matters: a statement
consumed by an earlier section (`processedStatements`) is not repeated in `properties` (always last).

**Facets section** (`PropertyFacetsStatementConsumer`): for each of 7 characteristic classes
(owl:SymmetricProperty "symmetric", AsymmetricProperty, FunctionalProperty, InverseFunctionalProperty,
ReflexiveProperty, IrreflexiveProperty, TransitiveProperty) output `{name, value: bool, explicit}` where
value = some `?res typingProp facetClass` exists (typingProp = rdf:type ∪ its subproperties);
explicitness from the facet statements' graphs, or if absent from the property's nature graph. Plus an
inner `inverseOf` matcher (owl:inverseOf, keeps empty group).

### 1.3 Templates per role (defaults, 17 roles; order = display order)
```
cls:                 types, classaxioms, lexicalizations, properties
dataRange:           types, datatypeDefinitions, lexicalizations, properties
concept:             types, topconceptof, schemes, broaders, lexicalizations, notes, collections, properties
property|objectProperty: types, equivalentProperties, superproperties, subPropertyChains, facets,
                     disjointProperties, domains, ranges, lexicalizations, properties
datatypeProperty:    same minus subPropertyChains
annotationProperty|ontologyProperty: types, superproperties, domains, ranges, lexicalizations, properties
conceptScheme:       types, lexicalizations, notes, collections, properties
ontology:            types, lexicalizations, imports, properties
skosCollection:      types, lexicalizations, notes, members, collections, properties
skosOrderedCollection: types, lexicalizations, notes, membersOrdered, collections, properties
individual:          types, lexicalizations, properties
xLabel:              types, labelRelations, notes, properties
ontolexLexicalEntry: types, lexicalForms, subterms, constituents, rdfsMembers, lexicalSenses,
                     denotations, evokedLexicalConcepts, properties
ontolexForm:         types, formRepresentations, properties
ontolexLexicalSense: types, properties
```
Template lookup (`getTemplateForResourceRole`): for property roles try objectProperty → datatypeProperty
→ ontologyProperty → annotationProperty (each only if `subsumes`) → property; otherwise exact role;
fallback individual template; ultimate fallback `[properties]`. Unknown section names are silently
skipped; custom sections are `AbstractPropertyMatchingStatementConsumer(name, matchedProperties,
noRootProps=MATCH_NOTHING)`.

### 1.4 `getResourceView(resource, resourcePosition?, includeInferred=false, ignorePropertyExclusions=false)` algorithm
1. **Locate** (`ResourceLocator.locateResource`): BNode → local; IRI → local if its namespace equals
   the project default ns (`getNamespace("")`) or it is subject of any explicit triple; else look up the
   Metadata Registry (master dataset, core dataset, current version, LOD dataset for the IRI) → `local:<otherProject>`
   if colocated & accessible, `remote:<dataset>` if accessible, else `unknown`. Serialized as
   `local:proj`, `remote:<datasetIRI>`, `unknown`.
2. **Access method**: `LocalProjectAccessMethod` ("local"), `SPARQLAccessMethod` ("sparql" or
   "sparql-degraded" when endpoint declares `NO_AGGREGATION`), `DerefenciationAccessMethod`
   ("dereferenciation": HTTP GET with content negotiation, null context moved to a graph named after the resource).
3. **Retrieve statements (local)**:
   ```sparql
   SELECT ?g ?s ?p ?o ?g2 ?s2 ?p2 ?o2 {
     GRAPH ?g { ?s ?p ?o . FILTER(?p NOT IN (lime:entry)) }        # ?s bound to resource
     OPTIONAL { ?o rdf:rest* ?s2 FILTER(isBLANK(?o))
                GRAPH ?g2 { ?s2 ?p2 ?o2 . FILTER(?p2 NOT IN (lime:entry)) } }
   }  # includeInferred=false
   ```
   i.e. explicit outgoing triples with graph, plus one level of bnode expansion (and RDF list spines).
   Then `DESCRIBE ?x` (with `includeInferred` as requested); every DESCRIBE triple not already present
   is added in the pseudo-graph **`http://semanticturkey/inference-graph`**; `lime:entry` triples are
   excluded and counted into `excludedObjectsCount` (exclusion disabled by `ignorePropertyExclusions`).
4. `subjectResourceEditable = local && model.contains(resource, ?, ?, WG)` → `resource.explicit`.
5. Copy repository namespaces into the model (for qnames).
6. **Subject/objects info** (one query, GROUP BY ?resource ?predicate):
   objects reachable from `<res> ?predicate ?tmp . ?tmp (rdf:rest*/rdf:first)* ?resource` ∪ the subject
   itself, non-literal; computes per resource `nature` (fragment below), rendering (`show` via project
   rendering engine), `qname`, `literalForm` (for xLabels), OntoLex renderings (lexical entry/form/lexicon/decomp component).
7. **Predicate info**: for predicates ∪ special props of the template:
   `SELECT ?resource (GROUP_CONCAT(DISTINCT STR(?specialProp)) AS ?attr_parents) nature… WHERE {
   VALUES ?resource {...} VALUES ?specialProp {...} OPTIONAL { ?resource rdfs:subPropertyOf* ?specialProp } }`
   → builds `propertyModel` (`p rdfs:subPropertyOf root`), used to route statements to sections.
   Predicate `show` = `prefix:local` or full IRI.
8. **Run consumers** in template order, sharing `processedStatements`.
9. Response: `{"resource": ResourceSection(annotated subject with resourcePosition, explicit,
   excludedObjectsCount, accessMethod, nature, show, qname), "<section>": PredicateObjectsList | LazySection | PropertyFacetsSection, ...}`.

`PredicateObjectsList` = `{predicate → AnnotatedValue<IRI>(show, nature/role, hasCustomRange,
customViewModel?, rootProperties?)} × {predicate → [AnnotatedValue objects]}`. For each object:
`explicit = currentProject && WG ∈ graphs`, `graphs = "g1,g2"` (null→"MAINGRAPH"), `tripleScope`.
Empty predicate groups are dropped (except facets/inverseOf); an empty section is still emitted (except
rdfsMembers for non-lexical-entries).

### 1.5 tripleScope (`NatureRecognitionOrchestrator.computeTripleScopeFromGraphs(graphs, WG)`)
Enum `TripleScopes = {local, staged, del_staged, imported, inferred}`. Start `inferred`; for each graph g:
- g == WG → `local` (unless already `del_staged` because of WG's remove-graph)
- g is a validation **add** graph (`VALIDATION.isAddGraph`) → `staged` if not local/del_staged
- g is a validation **remove** graph → `del_staged` if scope≠local or it's WG's remove graph (sticky)
- g ≠ INFERENCE_GRAPH (any other named graph, i.e. imported ontology / support graph) → `imported` if still inferred
- g == INFERENCE_GRAPH → remains `inferred`.
Empty graph set ⇒ error. Python:
```python
def triple_scope(graphs, wg):
    scope, del_in_wg = "inferred", False
    for g in graphs:
        if g == wg:
            if scope != "del_staged" or not del_in_wg: scope = "local"
        elif is_add_graph(g):
            if scope not in ("local", "del_staged"): scope = "staged"
        elif is_remove_graph(g):
            rm_wg = is_remove_graph_for(g, wg)
            if scope != "local" or rm_wg:
                scope = "del_staged"; del_in_wg |= rm_wg
        elif g != INFERENCE_GRAPH and scope == "inferred":
            scope = "imported"
    return scope
```

### 1.6 nature / role (`NatureRecognitionOrchestrator.getNatureSPARQL{Select,Where}Part`)
SELECT part: `(GROUP_CONCAT(DISTINCT CONCAT(STR(?rt),",",STR(?go),",",STR(?dep)); separator="|_|") AS ?attr_nature)`
→ string `"role,graphIRI,deprecated|_|role,graph,deprecated…"` (one triple per typing graph).
WHERE part (for `?r`):
```sparql
OPTIONAL { VALUES ?st {(rdfs:Datatype)} GRAPH ?go { ?r a ?st } }
OPTIONAL { VALUES ?st { decomp:Component vartrans:TranslationSet lime:Lexicon ontolex:LexicalEntry
                        ontolex:Form skos:Concept rdfs:Class skosxl:Label skos:ConceptScheme
                        skos:OrderedCollection owl:Ontology owl:ObjectProperty owl:DatatypeProperty
                        owl:AnnotationProperty owl:OntologyProperty }
           ?t rdfs:subClassOf* ?st  GRAPH ?go { ?r a ?t } }
OPTIONAL { VALUES ?st {(skos:Collection)(rdf:Property)} GRAPH ?go { ?r a ?st } }
OPTIONAL { GRAPH ?go { ?r a ?st } }
BIND(IF(!BOUND(?st),"individual", IF(?st=decomp:Component,"decompComponent", ... ,
     IF(?st=owl:Class||rdfs:Class,"cls", IF(?st=rdfs:Datatype,"dataRange","individual")))) AS ?rt)
OPTIONAL { BIND(IF(EXISTS{?r owl:deprecated true} || EXISTS{?r a owl:DeprecatedClass}
                || EXISTS{?r a owl:DeprecatedProperty},"true","false") AS ?dep) }
```
Note subclasses only expand for the 2nd group (so a subclass of skos:Collection is NOT a collection, but
a subclass of skos:Concept is a concept). Server-side role of the subject = first comma-field of nature
(`STServiceAdapter.getRoleFromNature`). Role enum (21): undetermined, cls, individual, property,
objectProperty, datatypeProperty, annotationProperty, ontologyProperty, ontology, dataRange, concept,
conceptScheme, xLabel, skosCollection, skosOrderedCollection, limeLexicon, ontolexLexicalEntry,
ontolexForm, ontolexLexicalSense, decompComponent, vartransTranslationSet.
Subsumption: property ⊒ {object,datatype,annotation,ontology}Property; skosCollection ⊒ skosOrderedCollection; cls ⊒ dataRange.

Python: `nature.py: compute_nature(store, res) -> list[NatureEntry(role, graph, deprecated)]`; implement
in Python over rdflib rather than with the 21-deep nested IF (equivalent decision table, priority order
as listed in the IF chain).

### 1.7 show / rendering (`AbstractStatementConsumer.addShowViaDedicatedOrGenericRendering`)
Priority: ontolex lexical-entry rendering → lime lexicon rendering → ontolex form rendering → xLabel
`skosxl:literalForm` (also sets `lang`) → decomp component rendering → custom-view property-chain preview
(`predattr_creShow`) → `computeShow`:
- BNode typed rdfs:Class/owl:Class/owl:Restriction/rdfs:Datatype → **Manchester expression**
  (`ManchesterSyntaxUtils.getManchExprFromBNode`, outer parens stripped), `show_interpretation=descr`
  (or "unknown OWL axiom");
- BNode list (rdf:List/first/rest) → `"[a, b, c]"` (`list`);
- BNode with owl:inverseOf → `"INVERSE p"` (`ope`);
- IRI with rendering-engine `show` → that (`rendering_or_id`);
- else `prefix:local` or full IRI; bnode `_:id` (`id`).
Rendering engine (`FW/extension/impl/rendering/BaseRenderingEngine.java`): per project lexicalization
model collects labels filtered to the accepted languages (`languages` setting, default `*`), output
`"lbl1 (en), lbl2 (it)"` in the language-priority order; optional template with variables `v_*`.

### 1.8 Time machine (`getResourceViewAtTime(IRI, date)`)
Reconstructs a past state into an in-memory repo: (1) fetch HEAD triples of resource + first-level
objects + DESCRIBE of bnodes; (2) iteratively query the history graph in the support repo
(`cl:Commit prov:startedAtTime > date; prov:generated ?delta; ?delta cl:addedStatement|cl:removedStatement ?st`)
and **undo** in reverse time order (added→remove, removed→add), expanding newly discovered objects/bnodes
(cap 50 iterations); (3) same for type closure (rdf:type/rdfs:subClassOf*) and predicate closure
(rdfs:subPropertyOf*); (4) rebuild rendering chain (rdfs:label | skos:prefLabel | skosxl:prefLabel/literalForm);
(5) run normal `getResourceView` against the temp repo. Only for MAIN shard. (History schema is the
other agent's scope.)

### 1.9 Python translation
```
sip/resource_view/
  locator.py        ResourceLocator.locate(project, res) -> Position(kind, project|dataset)
  access.py         LocalAccess(store).retrieve(res, include_inferred) -> quads (inferred → INFERENCE_GRAPH)
                    SparqlAccess(endpoint), DerefAccess(httpx+rdflib.parse)
  nature.py         compute_nature(), role_from_nature(), triple_scope()
  render.py         show_for(value, ctx), manchester.render_bnode()
  sections.py       class PropertyMatchingSection(name, roots, opts); FacetsSection; LazySection
  templates.py      DEFAULT_TEMPLATES (YAML above), resolve_template(role, project_settings)
  service.py        get_resource_view(res, position=None, include_inferred=False) -> dict
```
Key invariant: compute `property_model` (subPropertyOf* to roots) once; dispatch statements to the first
section whose roots subsume the predicate; leftover → `properties`.

---------------------------------------------------------------------------------------------------

## 2. SKOS, SKOS-XL, OntoLex

### 2.1 SKOS service (`SVC/SKOS.java`, 3067 lines, 43 ops)
Read: getTopConcepts, countTopConcepts, getNarrowerConcepts, getBroaderConcepts, getAllSchemes,
getSchemesMatrixPerConcept, getCollectionsForConcept, getRootCollections, getNestedCollections,
getSuperCollections, getAltLabels, isSchemeEmpty (+ test op failingReadServiceContainingUpdate).
Write: createConcept, createConceptScheme, setPrefLabel, addAltLabel, addHiddenLabel, addBroaderConcept,
addConceptToScheme, addMultipleConceptsToScheme, addTopConcept, addToCollection,
addFirstToOrderedCollection, addInPositionToOrderedCollection, addLastToOrderedCollection,
removeConceptFromScheme, removeTopConcept, removePrefLabel, removeAltLabel, removeBroaderConcept,
removeHiddenLabel, deleteConceptScheme, deleteConcept, createCollection, deleteCollection,
deleteOrderedCollection, removeFromCollection, removeFromOrderedCollection, addNote, removeNote,
updateNote, updateNoteProperty.

#### Hierarchy property resolution (shared by tree ops)
- `getHierachicalProps(broaderProps, narrowerProps)`: if both empty → `[skos:broader]`, else broaderProps.
- `getInverseOfHierachicalProp(b, n)`: if narrowerProps given → them; else query
  `?broaderProp owl:inverseOf|^owl:inverseOf ?inverseProp` for broaderProps (default skos:broader) and
  take **only the first** result (skos:broader→skos:narrower comes from the SKOS schema loaded as support/import).
- `preparePropPathForHierarchicalForQuery(b, inv, includeSubProperties)`: if includeSubProperties,
  expand `?sub rdfs:subPropertyOf* b` for each (excluding **skos:broadMatch**) and same for inverse
  (excluding **skos:narrowMatch**); path = `<b1>|<b2>|^<n1>|^<n2>` (note broaderTransitive is a
  *super*property of broader so it is NOT included; subproperties of broader would be).
- `combinePathWithVarOrIri(x, y, path, transitive)` → `x (path) [*] y .` where x is narrower side.

#### getTopConcepts(schemes?, schemeFilter=or|and, broaderProps?, narrowerProps?, includeSubProperties=true, includeDeprecated=true, sortKey?)
`?conceptSubClass` = all `?c rdfs:subClassOf* skos:Concept` (pre-queried, VALUES).
- with schemes:
  ```sparql
  SELECT ?resource ?attr_more ?attr_sortKey <nature> WHERE {
    VALUES ?conceptSubClass {...}  ?resource a ?conceptSubClass .
    [FILTER NOT EXISTS {?resource owl:deprecated true}]
    ?subPropTopConcept1 rdfs:subPropertyOf* skos:topConceptOf .
    ?subPropTopConcept1_inv rdfs:subPropertyOf* skos:hasTopConcept .
    { ?resource ?subPropTopConcept1 <S1> } UNION { <S1> ?subPropTopConcept1_inv ?resource }  # OR: UNION over schemes; AND: one group per scheme
    OPTIONAL { BIND(EXISTS { ?aNarrowerConcept (PATH) ?resource .
                             ?subPropInScheme2 rdfs:subPropertyOf* skos:inScheme .
                             {?aNarrowerConcept ?subPropInScheme2 <S1>} UNION ... } AS ?attr_more) }
    OPTIONAL { ?resource <sortKey> ?attr_sortKey }
    <nature where> } GROUP BY ?resource ?attr_more ?attr_sortKey
  ```
  **Top concept = explicitly declared** topConceptOf/hasTopConcept (not "has no broader").
- without schemes: top = concept with no broader **that is itself typed**:
  `FILTER NOT EXISTS { ?resource (PATH) ?aNarrowerConcept . ?aNarrowerConcept a ?o }`;
  `more = EXISTS { ?x (PATH) ?resource }`.
- `countTopConcepts`: same with `COUNT(DISTINCT ?resource)` (client "safeToGo" guard, default limit 1000).

#### getNarrowerConcepts(concept, ...)
`?resource (PATH) <concept> . ?resource a ?cs . ?cs rdfs:subClassOf* skos:Concept` (+ deprecated filter);
with schemes: narrower must be `inScheme` (subproperty-aware) one/all of the schemes (OR/AND);
`attr_more` = has a narrower (restricted to schemes if given). `getBroaderConcepts` symmetric
(`?concept (PATH) ?resource`). Results: `processRendering` + `processQName`.

Python: `skos/tree.py`:
```python
def hierarchy_path(store, broader=None, narrower=None, include_sub=True) -> str
def top_concepts(store, schemes=None, mode="or", ..., include_deprecated=True) -> list[AV]
def narrower(store, concept, schemes=None, mode="or", ...) -> list[AV]
```

#### Schemes / matrix
- `getAllSchemes`: `?resource a ?c . ?c rdfs:subClassOf* skos:ConceptScheme`.
- `getSchemesMatrixPerConcept(concept)`: each scheme + `attr_inScheme = EXISTS{?scheme skos:hasTopConcept|^skos:topConceptOf|^skos:inScheme ?concept}`.
- `isSchemeEmpty`: ASK in WG `{?res ?p ?scheme . ?p subPropertyOf* inScheme} UNION {?scheme ?p ?res . ?p subPropertyOf* hasTopConcept}`.

#### createConcept(newConcept?, label?, broaderConcept?, conceptSchemes[], conceptCls?, customFormValue?, checkExistingAltLabel=true, broaderProp?, checkExistingPrefLabel=true, addInverseOfBroaderProp=false)
1. `newConcept ??= generateIRI(concept, {label, schemes})`.
2. If label: `checkAndCreateLexicalization` by lex model:
   - SKOS: `checkIfAddPrefLabelIsPossible` = `SELECT ?resource { ?resource a ?t . ?t rdfs:subClassOf* skos:Concept . ?resource skos:prefLabel "lbl"@l . [?p subPropertyOf* inScheme . ?resource ?p ?scheme FILTER(?scheme IN schemes)] } LIMIT 1` → `PrefPrefLabelClashException`; `checkIfPrefAltLabelClash` = ASK same type & `skos:altLabel "lbl"@l` → `PrefAltLabelClashException`.
   - SKOSXL: same checks via `skosxl:prefLabel/literalForm`; generate xLabel IRI (`generateXLabelIRI(res, label, skosxl:prefLabel)`).
   - RDFS/OntoLex: no checks.
3. If customFormValue: run CF constructor (§9) with StandardForm `{type, label, labelLang | xLabel, lexicalForm, labelLang}` → may replace IRI and add triples.
4. Lexicalization triples: RDFS/OntoLex → `rdfs:label`; SKOS → `skos:prefLabel`; SKOSXL → `res skosxl:prefLabel xl . xl a skosxl:Label ; skosxl:literalForm lbl`.
5. `res a (conceptCls ?? skos:Concept)`; `res skos:inScheme s` for each scheme.
6. If broader: `res broaderProp(default skos:broader) broader` (+ `broader narrowerInverse res` if addInverseOfBroaderProp); **else** `res skos:topConceptOf s` for each scheme.
7. Mark created (concept, xLabel). Add to WG. Return `{role: concept, explicit: true}`.

`createConceptScheme`: analogous (type default skos:ConceptScheme, pref-label clash check with role conceptScheme).

#### setPrefLabel (SKOS)
Checks as above (schemes = all `inScheme` of the concept); **demotes** existing `skos:prefLabel` with the
same language (case-insensitive) in WG to `skos:altLabel`; adds new prefLabel.
`addAltLabel`: `checkIfAddAltLabelIsPossible` (alt label equal to an existing prefLabel of same
resource?) → `AltPrefLabelClashException`. `addHiddenLabel`: no check.

#### addBroaderConcept / removeBroaderConcept
add: `concept broaderProp broader` [+ inverse]. remove: remove `concept b broader` for all broaderPropsToUse
and `broader n concept` for all narrowerPropsToUse (defaults broader/narrower) — **removes both directions**.
`addTopConcept(concept, scheme, topConceptProp=skos:topConceptOf)`; `removeTopConcept` removes
topConceptOf + hasTopConcept; `removeConceptFromScheme` removes topConceptOf, hasTopConcept, inScheme.

#### addMultipleConceptsToScheme(rootConcept?, scheme, inSchemeProp?, includeSubProperties, broaderProps, narrowerProps, filterSchemes?, setTopConcept=true)
SPARQL Update: `INSERT { GRAPH WG { ?concept <inSchemeProp|skos:inScheme> <scheme> } } WHERE { ?cs rdfs:subClassOf* skos:Concept . GRAPH WG { ?concept a ?cs . [?concept (PATH)* <root>] [?concept ?p ?s FILTER(?s IN filterSchemes)] } }`;
top concepts: root (if given & setTopConcept) or every WG concept with no broader → add `topConceptOf scheme`.

#### deleteConcept(concept)
Precondition: `ASK { ?x (PATH-with-subprops, default broader/narrower) ?concept }` → `ConceptWithNarrowerConceptsException`.
Delete in WG: all triples with concept as subject or object, plus for skosxl:pref/alt/hiddenLabel objects
`?o2` all `?o2 ?p ?o` and `?s ?p ?o2` (cascades owned xLabels). `deleteConceptScheme` same cascade, **no**
emptiness precondition (client checks `isSchemeEmpty`).

#### Collections
- `getRootCollections`: collections (type ⊑ skos:Collection) with no `[] skos:member ?c` and no `[] skos:memberList/rdf:rest*/rdf:first ?c`; `attr_more` via CollectionsMoreProcessor (has nested collection members).
- `getNestedCollections(container)`: unordered `?container skos:member ?r` (only if container has no memberList) ∪ ordered `?container skos:memberList ?l . ?l rdf:rest* ?mid . ?mid rdf:rest* ?node . ?node rdf:first ?r`, `?index = COUNT(DISTINCT ?mid)` ORDER BY ?index; only members that are collections.
- `getCollectionsForConcept(concept)` (lazy RV section): collections having concept as `?p ⊑* skos:member` or within a `?p ⊑* skos:memberList` list; returns PredicateObjectsList keyed by member property with graphs/tripleScope.
- `createCollection(collectionType, newCollection?, label?, containingCollection?, collectionCls?, bnodeCreationMode=false, customFormValue?, checkExistingAltLabel)`: IRI or bnode; lexicalization as concepts; if containing collection: unordered → `skos:member`, ordered → append to list.
- `addToCollection`: error if already `skos:member` (`ElementAlreadyContainedInCollectionException`).
- Ordered list ops (all in WG, list nodes typed `rdf:List`):
  - `fixOrderedCollectionIfHasNoMemberList` → insert `coll skos:memberList rdf:nil`.
  - addFirst: new node `[a rdf:List; rdf:first e; rdf:rest oldHead]`, swap memberList.
  - addLast: if empty replace `memberList nil` with node, else walk to last (`rest nil`) and relink.
  - addInPosition(index ≥1): walk index-1 nodes, splice; "not enough elements" error; empty list only pos 1.
  - removeFromOrderedCollection: if head → memberList := rest; else find prev, relink, remove node triples.
- `deleteCollection` precondition: has no member that is a collection (`CollectionWithNestedCollectionsException`); update detaches from parent unordered (skos:member) and parent ordered lists (relinks list), then deletes the collection's triples and its xLabels. `deleteOrderedCollection` also deletes its list nodes.
- Notes: `addNote(resource, predicate⊑skos:note, SpecialValue)` → plain literal or CF-generated reified note (`STServiceAdapter.addValue`); `removeNote` removes triple (+ reified node via CF graph if any); `updateNote`, `updateNoteProperty` (switch predicate).

Python module: `sip/skos/{tree.py, concepts.py, schemes.py, collections.py, labels.py, notes.py}`;
list helpers `rdf_list.py: insert_at(store, head_ref, pos, value)`, `remove_value(...)`.

### 2.2 SKOS-XL service (`SVC/SKOSXL.java`, 13 ops)
`getPrefLabel/getAltLabels/getHiddenLabels(concept, lang="*")`, `setPrefLabel(concept, literal, labelCls?, mode=bnode|uri, checkExistingAltLabel, checkExistingPrefLabel)`,
`addAltLabel`, `addHiddenLabel` (same params), `prefToAtlLabel(concept, xlabel)` [sic], `altToPrefLabel`,
`removePrefLabel/removeAltLabel/removeHiddenLabel(concept, xlabel)`, `changeLabelInfo(xlabel, literal)`,
`updateSKOSXLLexicalizationProperty(subject, property, newProperty, xlabel)`.

- **setPrefLabel** algorithm: clash checks over `skosxl:prefLabel/skosxl:literalForm` (+ alt clash);
  find existing `concept skosxl:prefLabel ?xl . ?xl skosxl:literalForm ?l FILTER(lang(?l)=lang)` →
  move each to `skosxl:altLabel` (prefLabel uniqueness per language); new label = bnode (`mode=bnode`) or
  generated IRI (`generateXLabelIRI(concept, literal, skosxl:prefLabel)`); add
  `concept skosxl:prefLabel xl . xl a (labelCls ?? skosxl:Label) ; skosxl:literalForm literal`.
- **removeXLabel**: `DELETE { GRAPH WG { ?xl ?p1 ?o1 . ?s2 ?p2 ?xl } } WHERE { GRAPH WG { ?concept skosxl:prefLabel ?xl } {GRAPH WG {?xl ?p1 ?o1}} UNION {GRAPH WG {?s2 ?p2 ?xl}} }` — destroys the reified label entirely, incl. incoming labelRelations.
- **changeLabelInfo**: replace literalForm in WG (only if xlabel is referenced).
- Static checks reused by SKOS: `checkIfAddPrefLabelIsPossible`, `checkIfPrefAltLabelClash` (xl versions).

Label conversion between models is in **Refactor** (§4) and in export transformers (§7).

### 2.3 OntoLex/Lime (`SVC/OntoLexLemon.java`, 46 ops — brief)
Ops: createLexicon, getLexicons, deleteLexicon, getLexiconLanguage, add/remove/updateDefinition,
createLexicalEntry, getLexicalEntryLanguage, getLexicalEntriesByAlphabeticIndex,
countLexicalEntriesByAlphabeticIndex, deleteLexicalEntry, getLexicalEntryIndex, getLexicalEntryLexicons,
getLexicalEntrySenses, add/removeSubterm, set/clearLexicalEntryConstituents, setCanonicalForm,
addOtherForm, removeForm, add/update/removeFormRepresentation, getFormLanguage, addLexicalization,
removeLexicalization, removePlainLexicalization, removeReifiedLexicalization, addConceptualization,
removePlainConceptualization, removeConceptualization, removeSense, setReference, addConcept,
removeConcept, get{Lexical,Sense,Conceptual}RelationCategories, createLexicoSemanticRelation,
deleteLexicalRelation, deleteSenseRelation, createTranslationSet, getTranslationSets, deleteTranslationSet.
- `createLexicalEntry(newLE?, cls=ontolex:LexicalEntry, canonicalForm@lang, lexicon)`: lexicon must declare
  `lime:language`; form lang must `langMatches` it; add `LE a cls; ontolex:canonicalForm F; lime:language "xx"^^xsd:language . lexicon lime:entry LE . F a ontolex:Form; ontolex:writtenRep canonicalForm`.
- `addLexicalization(LE, reference, createPlain, createSense, senseCls?, CF?)`: plain = `LE ontolex:denotes ref` (if LE local) and/or `ref ontolex:isDenotedBy LE` (if ref local); sense = new `S a LexicalSense; ontolex:isSenseOf LE; ontolex:reference ref` + `LE ontolex:sense S`, `ref ontolex:isReferenceOf S` where local. Both inverse directions are written when each side is locally defined (cross-project lexicalization).
- Alphabetic index: first 1–2 chars of canonical form writtenRep (`getLexicalEntryIndex`).

---------------------------------------------------------------------------------------------------

## 3. Classes, Properties, Individuals, Resources, Datatypes, ManchesterHandler

### 3.1 Classes (`SVC/Classes.java`, 17 ops)
getSubClasses, getSuperClasses, getClassesInfo, getInstances, getNumberOfInstances, createClass,
deleteClass, createInstance, deleteInstance, addSuperCls, removeSuperCls, add/removeIntersectionOf,
add/removeUnionOf, add/removeOneOf.

**getSubClasses(superClass, numInst=true, includeDeprecated=true)** — three cases:
- `superClass = owl:Thing` (OWL root): all IRIs typed by a metaclass ⊑* rdfs:Class (except rdfs:Datatype), ≠ owl:Thing, ≠ rdfs:Resource, with **no named super-class other than owl:Thing** that is itself a class:
  ```sparql
  ?metaClass rdfs:subClassOf* rdfs:Class . ?resource a ?metaClass . FILTER(isIRI(?resource))
  FILTER(?resource != owl:Thing && ?resource != rdfs:Resource && ?metaClass != rdfs:Datatype)
  FILTER NOT EXISTS { ?resource rdfs:subClassOf ?sup . FILTER(?resource != ?sup)
      FILTER(isIRI(?sup) && ?sup != owl:Thing) ?sup a ?m2 . ?m2 rdfs:subClassOf* rdfs:Class }
  ```
- `superClass = rdfs:Resource` (RDFS root): owl:Thing ∪ classes whose metaclass ⊑* rdfs:Class MINUS ⊑* owl:Class, with no named super ≠ rdfs:Resource.
- otherwise: `?resource rdfs:subClassOf <superClass> FILTER isIRI(?resource)` (direct, explicit+imported).
Processors: `attr_more = ?resource IN (rdfs:Resource, owl:Thing) || EXISTS{?sub rdfs:subClassOf ?resource FILTER(?sub!=?resource && isIRI(?sub))}`;
`attr_numInst = COUNT(?i)` of `?i a ?resource` (direct only); FixedRoleProcessor sets role=cls; rendering, qname.
Client additionally filters subclasses via `ClassTreeFilter.map` (default hides e.g. SKOS/OWL internals) and root is `owl:Thing` (OWL/SKOS/OntoLex) or `rdfs:Resource` (RDFS).

**getInstances(cls, includeNonDirect=false)**: `?resource a ?cls` (or `a/rdfs:subClassOf* ?cls` with `attr_nonDirect`); `attr_directClasses` = group_concat of named direct types (qnamed).
**createClass(newClass?, superClass, classType=owl:Class, CF?)**: `new a classType; rdfs:subClassOf superClass` (superClass mandatory, e.g. owl:Thing). **deleteClass**: precondition `ASK{[] rdfs:subClassOf|rdf:type ?cls}` (no subclasses/instances, explicit only) → `ClassWithSubclassesOrInstancesException`; delete all WG triples with cls as subject or object. **createInstance(new?, cls, CF?)**: `new a cls`; role from cls (concept/scheme/collection/xLabel/individual).
**deleteInstance**: delete subject+object triples in WG (no cascade of bnodes!).
**addIntersectionOf/addUnionOf(cls, clsDescriptions[])**: each description is either `<iri>` or a Manchester expression → parsed to bnode triples; then builds an RDF list (`rdf:type rdf:List` on each node) and `cls owl:intersectionOf|unionOf list`. **addOneOf(cls, individuals[])**. Remove variants walk the list from the given bnode removing `rdf:type rdf:List`, `first`, `rest` and the link (does not delete the nested expression bnodes — leak).

### 3.2 Properties (`SVC/Properties.java`, 43 ops)
Trees: getTopProperties, getTopRDFProperties, getTopObjectProperties, getTopDatatypeProperties,
getTopAnnotationProperties, getTopOntologyProperties, getSubProperties, getSuperProperties,
getFlatProperties(vocabularies?), getPropertiesInfo, getPropertiesLexicalizations, getInverseProperties.
Relevance: getRelevantPropertiesForResource, getRelevantPropertiesForClass, getRelevantDomainClasses,
getRelevantRangeClasses, getRange, areSubPropertiesUsed.
Editing: createProperty, deleteProperty, add/removeEquivalentProperty, add/removePropertyDisjointWith,
add/removeInverseProperty, add/removeSuperProperty, add/removePropertyChainAxiom, add/removePropertyDomain,
add/removePropertyRange, setDataRange, removeDataranges, updateDataranges, addValue(s)ToDatarange,
hasValueInDatarange, removeValueFromDatarange, getDatarangeLiterals.

- **getTopProperties**: `?resource a ?type . {SELECT ?type {?type rdfs:subClassOf* rdf:Property}} FILTER NOT EXISTS {?resource rdfs:subPropertyOf ?sup . ?sup a ?superType} FILTER isIRI(?resource)` — top = no *typed* superproperty. Type-specific variants restrict ?type (owl:ObjectProperty etc.). `attr_more = EXISTS{?x rdfs:subPropertyOf ?resource}`.
- **getSubProperties(p)**: `?resource rdfs:subPropertyOf ?p FILTER isIRI`.
- **getRelevantPropertiesForResource(res)**: `?res rdf:type/rdfs:subClassOf* ?type . {?resource rdfs:domain ?type} UNION {?resource rdfs:domain ?union . ?union owl:unionOf/rdf:rest*/rdf:first ?type} MINUS {?resource rdfs:subPropertyOf ?sup . ?sup rdfs:domain ?type}` → only root properties.
- **getRange(property)** → JSON `{ranges:{type: resource|literal|undetermined, rangeCollection:[iri | {type:"enumeration", values}]}, formCollection?:{...custom forms}}`; ranges = IRI ranges of `property rdfs:subPropertyOf* ?super . ?super rdfs:range ?r` + bnode `rdfs:Datatype owl:oneOf` enumerations; `type`: literal if single range in xsd: or ⊑* rdfs:Literal or typed rdfs:Datatype; else ObjectProperty→resource, DatatypeProperty→literal, no ranges→undetermined, else resource. rdfs:Resource / owl:Thing ranges dropped; sole rdfs:Resource → undetermined. If the property's CF mapping has `replace=true`, ranges are omitted (only the custom form). Used by the client to pick the value editor ("add value" dialog).
- **createProperty(propertyType ∈ {owl:Object/Datatype/Annotation/OntologyProperty, rdf:Property}, newProperty?, superProperty?, CF?)**.
- **deleteProperty**: precondition no `[] rdfs:subPropertyOf ?p` → `PropertyWithSubpropertiesException`; delete subject/object triples in WG.
- **addPropertyAxiomHelper(property, linked, inverse, linkingPredicate)**: inverse=true inserts `property linkingPredicate [a owl:ObjectProperty; owl:inverseOf linked]` (an inverse object property expression); remove helper deletes the triple and, if the object is such a bnode, its triples.
- **addPropertyChainAxiom(property, chainedProperties[≥2] strings)**: each may be `INVERSE p` → build RDF list.
- **setDataRange(property, predicate⊑rdfs:range, literals[])**: `property rdfs:range _:dr . _:dr a rdfs:Datatype; owl:oneOf (lits)`; datarange list ops manipulate the `owl:oneOf` list.

### 3.3 Individuals (`SVC/Individuals.java`, 3 ops)
`getNamedTypes(individual)` (IRI types), `addType(individual, type)`, `removeType(individual, type)` (plain triple add/remove in WG).

### 3.4 Resources (`SVC/Resources.java`, 17 ops) — generic triple editing behind the Resource View
| op | semantics |
|---|---|
| updateTriple (deprecated) / updateTripleValue / updateLexicalization(subject, property, value, newValue) | `DELETE {GRAPH WG {s p v}} INSERT {GRAPH WG {s p nv}} WHERE {BINDs}` (insert even if old absent) |
| updateTriplePredicate(subject, predicate, value, newPredicate) / updateFlatLexicalizationProperty | move value to new predicate (WG) |
| updatePredicateObject(property, value, newValue) | **bulk**: all subjects `?s p v` in WG → `?s p nv` |
| removePredicateObject(property, value) | bulk delete `?s p v` in WG |
| removeValue(subject, property, value) | `remove(s,p,v,WG)` |
| addValue(subject, property, SpecialValue) | plain value or CF-generated graph |
| setDeprecated(resource) | add `owl:deprecated "true"^^xsd:boolean` |
| getResourceDescription(resource) / getResourcesInfo(resources[]) | nature+show+qname (+ OntoLex renderings replacing show) |
| getResourcePosition(s) | ResourceLocator |
| getOutgoingTriples(resource, format) | `CONSTRUCT {?s ?p ?o} WHERE {GRAPH WG {?s ?p ?o}}` with ?s=res, serialized with project prefixes ("source code" editor) |
| updateResourceTriplesDescription(resource, triples, format) | parse (preserve bnode ids), all subjects must equal resource, diff against WG description; refuse if it would delete **all** triples; apply add/remove **bypassing validation** |
| validateIRIList("a:b, <...>") | expand qnames via prefix map, validate IRIs |

### 3.5 Datatypes (`SVC/Datatypes.java`, 13 ops)
createDatatype (`dt a rdfs:Datatype`), deleteDatatype, getDatatypes, getDeclaredDatatypes,
getOWL2DatatypeMap, getRDF11XmlSchemaBuiltinDatatypes, getBuiltinDatatypes,
setDatatypeEnumerationRestrictions(dt, literals) (`dt owl:equivalentClass [a rdfs:Datatype; owl:oneOf (..)]`),
setDatatypeFacetsRestriction(dt, base, {facet→literal}) (`[a rdfs:Datatype; owl:onDatatype base; owl:withRestrictions ([xsd:minInclusive v] ...)]`),
deleteDatatypeRestriction, getRestrictionDescription(bnode), getDatatypeRestrictions().
Language list for lang pickers: project setting `languages` (≈70 defaults: ar … zh, see project-settings-defaults.props).

### 3.6 ManchesterHandler (`SVC/ManchesterHandler.java`, 10 ops; parser in FW `syntax/manchester/owl2` ANTLR grammar `ManchesterOWL2SyntaxParser`)
getAllDLExpression(classIri, usePrefixes, useUppercaseSyntax) → `{equivalentClass:{bnode→expr}, subClassOf:{bnode→expr}}` (**bug**: subClassOf loop iterates the equivalentClass list), getExpression(bnode), isClassAxiom(bnode),
checkExpression(manchExpr, skipSemanticCheck) / checkDatatypeExpression / checkLiteralEnumerationExpression / checkObjectPropertyExpression → `{valid, details:{msg,pos,...}}`,
createRestriction(classIri, exprType ∈ {owl:equivalentClass, rdfs:subClassOf, ...}, manchExpr, skipSemanticCheck): parse → semantic checks (IRIs exist with suitable roles) → bnode triples into WG + `classIri exprType bnode`;
removeExpression(classIri, exprType, bnode): remove link + recursively the bnode structure;
updateExpression(newExpr, bnode): remove old structure, re-generate **reusing the same bnode** as root.
Python: use `owlready2`-free approach: port with a Lark grammar (`sip/owl/manchester.lark`) producing rdflib triples; rendering from bnodes = recursive descent over owl:Restriction/someValuesFrom/allValuesFrom/hasValue/(min|max|)(Qualified)Cardinality/intersectionOf/unionOf/complementOf/oneOf.

---------------------------------------------------------------------------------------------------

## 4. Refactor (`SVC/Refactor.java`, 7 ops)

### 4.1 changeResourceURI(oldResource, newResource)
1. Duplicate check: `ASK { GRAPH WG { {?res ?p ?o} UNION {?s ?res ?o} UNION {?s ?p ?res} } }` with ?res=new → `DuplicatedResourceException` (only WG checked).
2. One update in WG: replace old as subject, predicate, object **and as datatype of literals**
   (`FILTER(datatype(?lit)=old) BIND(STRDT(STR(?lit), new) AS ?newLit)`).
Imported graphs are NOT rewritten (references from other graphs stay dangling). History/metadata
updated by change tracker.
```python
def change_resource_uri(store, wg, old, new):
    if any(store.triples_with(new, graph=wg)): raise Duplicated
    for s,p,o in list(store.quads_in(wg)):
        ns = new if s==old else s; np_ = new if p==old else p
        no = new if o==old else (Literal(o, datatype=new) if isinstance(o,Literal) and o.datatype==old else o)
        if (ns,np_,no)!=(s,p,o): store.remove((s,p,o),wg); store.add((ns,np_,no),wg)
```

### 4.2 replaceBaseURI(sourceBaseURI?=project baseURI, targetBaseURI)
Refuses if validation is enabled and staging add/remove graphs exist. Runs **without validation**:
(a) if source == project baseURI → `OntologyManager.setBaseURI(target)`, `project.setBaseURI(target)`;
(b) rewrite the ontology resource (subject/object string == source);
(c) for all WG triples, any IRI (S, P, O) whose namespace (regex `(^.*(#|/))([^#|^/]*)` → `$1`) equals
source (normalized with trailing `#` if missing) is rewritten to `target + localName`;
(d) rewrite literal datatypes whose IRI starts with source. Note: the WG IRI itself is not changed in
this op ("TODO update working graph") — port should also move quads to the new graph.

### 4.3 migrateDefaultGraphToBaseURIGraph(clearDestinationGraph=false)
`MOVE DEFAULT TO GRAPH <WG>` or `ADD DEFAULT TO GRAPH <WG>; DROP DEFAULT`.

### 4.4 SKOStoSKOSXL(reifyNotes)
For each WG triple `?c (skos:prefLabel|altLabel|hiddenLabel) ?lit`: generate xLabel IRI (`generateIRI(xLabel, {lexicalForm, lexicalizedResource, lexicalizationProperty})`), then
`DELETE DATA {c skos:x lit}; INSERT DATA {c skosxl:x xl . xl a skosxl:Label ; skosxl:literalForm lit}`.
If reifyNotes: for each `?c ?noteP ?lit` with `?noteP ⊑* skos:note`: generate `xNote` IRI,
`DELETE DATA {c noteP lit}; INSERT DATA {c noteP n . n rdf:value lit}` (no type on the note node).
Non-literal values of skos label props would ClassCastException (assumes literals).

### 4.5 SKOSXLtoSKOS(flattenNotes)
Single update: for each `?c skosxl:{pref,alt,hidden}Label ?l . ?l skosxl:literalForm ?lf` insert
`?c skos:{pref,alt,hidden}Label ?lf` and delete **all** triples of `?l` and all triples pointing to `?l`
(labelRelations lost). If flattenNotes: `?c ?p ?n . ?p ⊑* skos:note . ?n rdf:value ?v` → `?c ?p ?v`, delete note node triples.

### 4.6 spawnNewConceptFromLabel(newConcept?, xLabel, oldConcept?, broaderConcept?, conceptSchemes[], CF?)
Read `xLabel skosxl:literalForm` (error `NonExistingLiteralFormForResourceException`); new IRI from label;
add `new a skos:Concept; skosxl:prefLabel xLabel; skos:inScheme S*`; broader given → `skos:broader`, else
`skos:topConceptOf S*`; remove every `?concept ?pred xLabel` where `?concept a skos:Concept` (restricted to
oldConcept if given). (Concept class fixed to skos:Concept.)

### 4.7 moveXLabelToResource(sourceResource, predicate, xLabel, targetResource, force=false)
oldPredicate = predicate linking source→xLabel. If new predicate is skosxl:prefLabel and old isn't:
check no other concept has a prefLabel with the same literalForm (clash unless force). If new predicate is
prefLabel and target already has a prefLabel in the same language: error unless force, in which case the
existing one is demoted to skosxl:altLabel. Then `remove(source oldPred xl)`, `add(target pred xl)`.

Python: `sip/refactor/{rename.py, base_uri.py, lexmodel_migration.py, xlabel_ops.py}`.

---------------------------------------------------------------------------------------------------

## 5. ICV — Integrity Constraint Validation (`SVC/ICV.java`, 3112 lines, 38 ops = 27 checks/reads + 11 fixes)
Client catalogue: `vocbench3/src/app/icv/icvListComponent.ts` (22 UI checks in 3 groups, with
preconditions `model`/`lexicalization`). All read queries go through QB with `processRole/processRendering/processQName` unless noted. `rolesArray` → `rolePartForQuery`:
concept `?r rdf:type/rdfs:subClassOf* skos:Concept`; cls `type ∈ {owl:Class, rdfs:Class}` (via type/subClassOf*);
property `type/subClassOf* ∈ {rdf:Property, owl:Object/Datatype/Annotation/OntologyProperty}`;
conceptScheme; skosCollection `∈ {skos:Collection, skos:OrderedCollection}`; individual `?r a ?t . ?t a owl:Class|rdfs:Class`.

### 5.1 Checks (read)
| # | op (UI name) | model precondition (UI) | logic |
|---|---|---|---|
| 1 | listDanglingConcepts(scheme) (Dangling concepts) | SKOS | `?r a skos:Concept ; skos:inScheme ?scheme . FILTER NOT EXISTS {?r skos:topConceptOf\|^skos:hasTopConcept ?scheme} FILTER NOT EXISTS {?r skos:broader\|^skos:narrower ?b . ?b skos:inScheme ?scheme}` |
| 2 | listDanglingConceptsForAllSchemes | SKOS | same, `?attr_dangScheme` unbound → per scheme |
| 3 | listConceptSchemesWithNoTopConcept (Omitted top concept) | SKOS | `?r a skos:ConceptScheme FILTER NOT EXISTS {{?r skos:hasTopConcept ?t} UNION {?t skos:topConceptOf ?r}}` |
| 4 | listConceptsWithNoScheme | SKOS | `?r a skos:Concept FILTER NOT EXISTS {?r skos:inScheme ?s}` |
| 5 | listTopConceptsWithBroader | SKOS | `?c skos:topConceptOf\|^skos:hasTopConcept ?s . ?c skos:broader\|^skos:narrower ?b . ?b skos:inScheme\|skos:topConceptOf\|^skos:hasTopConcept ?s` → JSON `[{concept, scheme}]`, includeInferred=false |
| 6 | listConceptsRelatedDisjoint | SKOS | `?relP ⊑* skos:related . ?bP ⊑* skos:broaderTransitive . ?c1,?c2 typed ⊑* skos:Concept . ?r ?relP ?c2 . {?r ?bP ?c2} UNION {?c2 ?bP ?r}` (related ∧ hierarchical — violates SKOS S27) |
| 7 | listConceptsExactMatchDisjoint | SKOS | `?r skos:exactMatch ?c2 . {?r broadMatch ?c2} ∪ {?r relatedMatch ?c2} ∪ {?c2 broadMatch ?r} ∪ {?c2 relatedMatch ?r}` |
| 8 | listConceptsHierarchicalRedundancies(sameScheme=true) | SKOS/SKOSXL lex only | `?c (broader\|^narrower) ?b . ?b (broader\|^narrower)+ ?o . FILTER(?b!=?o) ?c (broader\|^narrower) ?o` [all three in same scheme]; returns JSON triples `{subject, predicate(broader\|narrower), object}` |
| 9 | listConceptsHierarchicalCycles | SKOS | `?r a skos:Concept . ?r (broader\|^narrower) ?b . ?b (broader\|^narrower)* ?r` → JSON cycles |
| 10 | listConsistencyViolations (OWL consistency violations) | OWL; **GraphDB only** | read current ruleset (`?state sys:listRulesets ?rs` with sys:currentRuleset), `INSERT DATA {_:b sys:consistencyCheckAgainstRuleset "rs"}`; parse exception text with regex `Consistency check (?<conditionName>.+?) failed:\n(?<inconsistentTriples>.+?)` into `[{conditionName, inconsistentTriples}]` |
| 11 | explain(s,p,o) | GraphDB proof plugin | `?ctx proof:explain (?s ?p ?o); proof:rule ?rule; proof:subject/predicate/object/context` → `{ruleName, premises}` |
| 12 | listResourcesWithNoSKOSPrefLabel | lex SKOS | `{?r a skos:Concept} ∪ ConceptScheme ∪ Collection ∪ OrderedCollection` FILTER NOT EXISTS `skos:prefLabel` |
| 13 | listResourcesWithNoSKOSXLPrefLabel | lex SKOSXL | same with `skosxl:prefLabel` |
| 14 | listResourcesNoLexicalization(roles, languages) (No mandatory label) | any | per lang: `BIND('xx' AS ?lang) FILTER NOT EXISTS {?r <lexProp> ?l FILTER(lang(?l)=?lang)}`, lexProp by model (rdfs:label / skos:prefLabel / skosxl:prefLabel→literalForm); `attr_missingLang` = group_concat |
| 15 | listResourcesWithAltNoPrefLabel(roles) (Only altLabel) | SKOS/SKOSXL | alt label in lang L and no pref label in L; `attr_missingLang` |
| 16 | listResourcesWithNoLanguageTagForLabel(roles) | any | `?r (pref\|alt\|hidden)` (skos or skosxl→literalForm, or rdfs:label) with `lang(?l)=''`; returns attr_xlabel/attr_label |
| 17 | listResourcesWithOverlappedLabels(roles) | any | same literal used under two different lexicalization props of the same resource (e.g. prefLabel = altLabel), skosxl: two distinct xLabels with same literalForm |
| 18 | listResourcesWithSameLabels(roles) (Conflictual labels) | SKOS/SKOSXL | two different resources of the same role (concepts: sharing a scheme via `?p ⊑* inScheme`) with identical prefLabel; two-step: raw query then VALUES re-query for rendering |
| 19 | listResourcesWithExtraSpacesInLabel(roles) | any | `regex(?l,'^ +') \|\| regex(?l,' +$') \|\| regex(?l,'  ')` (leading/trailing/double spaces) |
| 20 | listResourcesWithMorePrefLabelSameLang(roles) (Multiple prefLabel) | SKOS/SKOSXL | ≥2 distinct prefLabels same lang; `attr_duplicateLang` |
| 21 | listDanglingXLabels | SKOSXL | `?sub ⊑* skosxl:Label . ?r a ?sub FILTER NOT EXISTS {?c skosxl:prefLabel\|altLabel\|hiddenLabel ?r}` (3 separate NOT EXISTS) |
| 22 | listResourcesNoDef(roles, languages) | SKOS | per lang: no `skos:definition` literal nor reified `skos:definition/rdf:value` in that lang |
| 23 | listAlignedNamespaces(roles) | any | mapping props = `?p ⊑* skos:mappingRelation ∪ owl:equivalentClass ∪ owl:disjointWith ∪ rdfs:subClassOf ∪ owl:equivalentProperty ∪ rdfs:subPropertyOf ∪ owl:sameAs ∪ owl:differentFrom`; `?r ?p ?r2` (subject restricted by role); namespace = `REPLACE(str(?r2),'[^(#\|/)]+$','')`; count per ns; enriched with possible locations (local projects / remote datasets / dereferenceable) from Metadata Registry |
| 24 | listBrokenAlignments(nsToLocationMap, roles) | SKOS/OWL/RDFS | same mapping triples, object IRI; per ns location: `local:<project>` → query that project `SELECT ?deprecated ?hasType {...}` broken if no type or deprecated; `remote`/`dereference:` → HTTP GET non-200 → broken; JSON `[{subject, predicate, object(+deprecated)}]` |
| 25 | listBrokenDefinitions(roles, property⊑skos:note) | any | `?prop ⊑* property . ?s ?prop ?o FILTER isIRI(?o) FILTER NOT EXISTS {?o ?x ?y}`; then local namespace → broken; external → HTTP GET (5s timeouts) non-200/IOException → broken |
| 26 | listLocalInvalidURIs | any | `?r a ?t FILTER(REGEX(str(?r)," ") \|\| !REGEX(str(?r), RFC3986_REGEX, "i"))` |
| 27 | listResourcesURIWithSpace | any | any IRI in S/P/O position with `regex(str, ' +?')` |

RFC3986 regex used in #26 (verbatim):
`^([a-z0-9+.-]+):(?://(?:((?:[a-z0-9-._~!$&'()*+,;=:]|%[0-9A-F]{2})*)@)?((?:[a-z0-9-._~!$&'()*+,;=]|%[0-9A-F]{2})*)(?::(\d*))?(/(?:[a-z0-9-._~!$&'()*+,;=:@/]|%[0-9A-F]{2})*)?|(/?(?:[a-z0-9-._~!$&'()*+,;=:@]|%[0-9A-F]{2})+(?:[a-z0-9-._~!$&'()*+,;=:@/]|%[0-9A-F]{2})*)?)(?:\?((?:[a-z0-9-._~!$&'()*+,;=:/?@]|%[0-9A-F]{2})*))?(?:#((?:[a-z0-9-._~!$&'()*+,;=:/?@]|%[0-9A-F]{2})*))?`

### 5.2 Fix operations (write; all in WG)
| op | effect |
|---|---|
| setAllDanglingAsTopConcept(scheme) | INSERT `?c skos:topConceptOf ?scheme` for all dangling (query #1) |
| setBroaderForAllDangling(scheme, broader) | INSERT `?c skos:broader <broader>` for all dangling |
| removeAllDanglingFromScheme(scheme) | DELETE `?c skos:inScheme ?scheme` for dangling |
| deleteAllDanglingConcepts(scheme) | DELETE all `?c ?p ?o` and `?s ?p ?c` for concepts in scheme, not top, whose broaders (if any) are not in scheme and that have no narrower in scheme |
| addAllConceptsToScheme(scheme) | INSERT `?c skos:inScheme <scheme>` for concepts with no scheme |
| removeBroadersToConcept(concept, scheme) | for a top concept of scheme: DELETE `?c skos:broader ?b . ?b skos:narrower ?c` where b in scheme |
| removeBroadersToAllConcepts() | same for every top concept with broader (fix of #5 by dropping the broader) |
| removeAllAsTopConceptsWithBroader() | fix #5 the other way: DELETE `?c skos:topConceptOf ?s . ?s skos:hasTopConcept ?c` |
| removeAllHierarchicalRedundancy() | DELETE `?n skos:broader ?b . ?b skos:narrower ?n` where `?n (broader\|^narrower)+ ?m . ?m (broader\|^narrower) ?b`, ?n≠?m |
| deleteAllDanglingXLabel() | DELETE all triples of xLabels not linked by pref/alt/hidden |
| setDanglingXLabel(concept, xlabelPred, xlabel) | attach xlabel; if pred=prefLabel demote existing prefLabel to altLabel |

Python: `sip/icv/checks.py` — a registry `CHECKS: dict[str, Check(name, group, models, lexmodels, query_builder, result_shape)]` and `fixes.py`; GraphDB-only checks (#10, #11) behind `if store.vendor == "graphdb"`; HTTP checks via `httpx` with 5s timeouts and concurrency limit. Recommended extra: offer SHACL equivalents (pySHACL) for #1–#9, #12–#22.

---------------------------------------------------------------------------------------------------

## 6. Search (`SVC/Search.java` 14 ops, `SVC/GlobalSearch.java`, `FW/search/*`, strategies in ext jars)

### 6.1 Ops
createIndexes, updateIndexes (GraphDB Lucene), customSearch(searchParameterizationReference, boundValues),
advancedSearch(searchString, useLexicalizations=true, useLocalName=false, useURI=false, searchMode, useNotes=false, langs?, includeLocales=false, statusFilter, types: [[IRI]], schemes: [[IRI]], outgoingLinks: [(IRI,[Value])], outgoingSearch: [(pred, string, mode)], ingoingLinks, searchInRDFSLabel, searchInSKOSLabel, searchInSKOSXLLabel, searchInOntolex, includeNonDirect),
searchAlignedResources(..., predList, maxNumOfResPerQuery=30), **searchResource**(searchString, rolesArray[], useLexicalizations=true, useLocalName, useURI, searchMode, useNotes=false, schemes?, schemeFilter=or, langs?, includeLocales=false, searchInRDFSLabel/SKOSLabel/SKOSXLLabel/Ontolex=false),
searchStringList (autocomplete strings), searchURIList (autocomplete IRIs, maxNumResults), searchInstancesOfClass,
searchLexicalEntry(lexicons, ...), getPathFromRoot(role, resourceURI, schemes?, schemeFilter, root=owl:Thing, broaderProps, narrowerProps, includeSubProperties) (tree "reveal"), searchPrefix(searchString, mode ∈ contains|startsWith|endsWith) (namespace prefix completion, in-memory), get/storeCustomSearchSettings.

Enums: `SearchMode {startsWith, contains, endsWith, exact, fuzzy, searchSyntax}` (searchSyntax only GraphDB),
`StatusFilter {NOT_DEPRECATED, ONLY_DEPRECATED, UNDER_VALIDATION, UNDER_VALIDATION_FOR_DEPRECATION, ANYTHING}`,
`SearchScope {term, words}`, strategies `REGEX` (`RegexSearchStrategy`) / `GRAPH_DB` (`GraphDBSearchStrategy`) chosen per repository (`STRepositoryInfo.searchStrategy`).

### 6.2 searchResource — Regex strategy (port target)
Validation (`ServiceForSearches.checksPreQuery`): non-empty string; roles ⊆ {cls, concept, conceptScheme, individual, property, skosCollection, dataRange, limeLexicon, ontolexLexicalEntry}; mode required; searchSyntax rejected; at least one of useLexicalizations/useLocalName/useURI/useNotes; useNotes requires useLexicalizations. OntoLex project → searchInRDFSLabel forced true.

Query skeleton:
```sparql
SELECT DISTINCT ?resource ?attr_matchMode (GROUP_CONCAT(DISTINCT ?scheme; separator=",") AS ?attr_schemes) <nature>
WHERE {
  # candidate filter (UNION of wanted roles):
  { ?resource a ?type FILTER(?type = owl:Class || ?type = rdfs:Class) }                       # cls
  UNION { ?resource a ?type . ?type rdfs:subClassOf* rdf:Property }                           # property
  UNION { ?resource a ?type . ?type rdfs:subClassOf* skos:Concept .
          ?resource (skos:inScheme|skos:topConceptOf|^skos:hasTopConcept) <S> ...            # 1 scheme / and / or(FILTER IN)
          | OPTIONAL { ?resource (inScheme|topConceptOf|^hasTopConcept) ?scheme } }           # no schemes
  UNION ... conceptScheme / skosCollection / individual / dataRange / lexicon / lexicalEntry
  # match part, UNION of enabled sources:
  { ?resource a ?type2 . BIND(REPLACE(str(?resource),'^.*(#|/)',"") AS ?localName) <MATCH ?localName> }   # useLocalName
  UNION { ?resource a ?type3 . BIND(str(?resource) AS ?complURI) <MATCH ?complURI> }                    # useURI (startsWith expands qname prefix)
  UNION { ?p ⊑* skos:note . ?resource ?p ?label <MATCH> } UNION { ?resource ?p ?n . ?n rdf:value ?label <MATCH> }  # useNotes
  UNION { ?resource rdfs:label ?label <MATCH> }                                          # if lexModel RDFS or searchInRDFSLabel
  UNION { ?resource (skos:prefLabel|skos:altLabel|skos:hiddenLabel) ?label <MATCH> }     # SKOS
  UNION { ?resource (skosxl:prefLabel|altLabel|hiddenLabel) ?xl . ?xl skosxl:literalForm ?label <MATCH> }  # SKOSXL (+ ?resource skosxl:literalForm for xLabel search)
  UNION { ?resource dct:title ?label } ∪ { ?resource (ontolex:canonicalForm|otherForm)/ontolex:writtenRep ?label }
        ∪ { ?resource (^ontolex:denotes|ontolex:isDenotedBy|^ontolex:evokes|ontolex:isEvokedBy
                       |(ontolex:lexicalizedSense|^ontolex:isLexicalizedSenseOf|^ontolex:reference|ontolex:isReferenceOf)/(^ontolex:sense|ontolex:isSenseOf))
                      /(ontolex:canonicalForm|ontolex:otherForm)/ontolex:writtenRep ?label }      # OntoLex
  <nature where>
} GROUP BY ?resource ?attr_matchMode
```
`<MATCH v>` per mode (value escaped with `Pattern.quote` then `\`→`\\`, `'`→`\'`):
- startsWith `FILTER regex(str(v), '^X', 'i')`; endsWith `'X$'`; contains `'X'`; exact `'^X$'` (all **case-insensitive**);
- fuzzy: one-edit neighbourhood: `.X`, `X.` and `X[0:i] . X[i+1:]` for each i, joined `(^w1$)|(^w2$)|…` (i.e. one substitution, or one extra leading/trailing char — no deletions);
- `BIND('<mode>' AS ?attr_matchMode)`;
- language filter on labels: `FILTER(regex(lang(v),'^en$','i') || ...)`, with `includeLocales` → `'^en'` (matches en-GB).
Then QB: processQName + processRendering. Results are de-duplicated per (resource, matchMode).

GraphDB strategy: same SPARQL plus Lucene FTS pre-filter: indexes `luc:vocbenchLabel` (literal index, `luc:index "literal"`, `luc:include "centre"`, `luc:moleculeSize "0"`) and `luc:vocbenchLocalName` (uri index), created with `luc:createIndex "true"`, refreshed with `luc:updateIndex`; query part `?resource luc:vocbenchLabel "<normalized>*"` before the regex FILTER; `searchSyntax` passes raw Lucene syntax without regex.

### 6.3 searchStringList / searchURIList (completion)
`searchStringList` returns label strings (`?label`) from localName/rdfs:label/skos labels/skosxl literalForm/dct:title/ontolex writtenRep; `searchURIList` returns IRIs matching (startsWith expands `prefix:` via namespaces), `LIMIT maxNumResults`.

### 6.4 advanced search filters (`ServiceForSearches.prepareQueryWithStatusOutgoingIngoing`)
status NOT_DEPRECATED → `FILTER NOT EXISTS {owl:deprecated true ∪ a owl:DeprecatedClass ∪ a owl:DeprecatedProperty}`; ONLY_DEPRECATED → positive; UNDER_VALIDATION → `GRAPH <staging-add-graph(baseURI)> {?resource a ?t}`; ..._FOR_DEPRECATION → deprecation triple in staging add graph. `types` = OR of AND lists (`getResourceshavingTypes`, with sub-types optional), `schemes` same over (inScheme|topConceptOf|^hasTopConcept); outgoing/ingoing links `(?resource p v1|v2)`; outgoingSearch `?resource p ?v` + mode match without index.

### 6.5 getPathFromRoot (used by "reveal in tree")
Concept role: compute top concepts (declared in schemes, OR/AND count-matching, or no-broader); query
edges `?broader ?broaderOfBroader ?isTopConcept` for all `?resource (PATH)* ?broader` restricted to schemes
(`?isTopConcept` when declared top in scheme / has no broader without schemes); then Java builds all paths
from a top concept down to the resource (BFS over edge list). Classes: `rdfs:subClassOf*` up to `root`;
properties: `rdfs:subPropertyOf*`; collections: member/memberList chain. Returns flattened path list of
AnnotatedValues (each path ends with the resource). Python: `networkx`-free BFS over parent map.

Python: `sip/search/{strategy.py (RegexStrategy, FusekiTextStrategy using jena-text `text:query`), modes.py (regex builders, fuzzy), service.py}`. For rdflib in-memory, do matching in Python (casefold + `re`) after candidate SPARQL for speed.

---------------------------------------------------------------------------------------------------

## 7. Import / Export (`SVC/InputOutput.java`, `SVC/Export.java`, `SVC/export/*`, extension points in `FW/extension/extpts/{loader,rdflifter,rdftransformer,reformattingexporter,deployer}`)

### 7.1 Pipeline concepts (extension points)
- **Loader** (`Loader.load(target, dataFormat)`): fetches data from somewhere into a stream (`FormattedResourceTarget`) or directly into a repository (`RepositoryTarget`). Impls: HTTP loader (`st-http-loader`: GET with configurable endpoint/query params/headers/auth), Graph Store HTTP loader, S3, SFTP.
- **RDFLifter** (`lift(formattedResource, format, rdfHandler)`): turns a stream into RDF. Default `RDFDeserializingLifter` (Rio parsers; `FormatCapabilityProvider` lists formats); others: spreadsheet (Sheet2RDF), Zthes, EDOAL deserializer.
- **RDFTransformer** (`transform(sourceConn, workingConn, graphs[])`): in-place RDF→RDF on a working copy. Shipped (8 jars inspected):
  | transformer | config | algorithm |
  |---|---|---|
  | SPARQLRDFTransformer | `filter` (SPARQL Update), `sliced=true` | sliced: run once per graph g with dataset default/defaultRemove/defaultInsert = g; else once with all graphs |
  | PropertyNormalizerTransformer | normalizingProperty, propertiesBeingNormalized{} | `DELETE {GRAPH ?g {?s ?p ?o}} INSERT {GRAPH ?g {?s <norm> ?o}} WHERE {VALUES ?p {...} GRAPH ?g {?s ?p ?o}}` |
  | DeletePropertyValueRDFTransformer | resource, property, value? | `remove(resource, property, value|*, graphs)` |
  | UpdatePropertyValueRDFTransformer | resource, property, value, oldValue? | remove old (or all) + add new |
  | XLabelDereificationRDFTransformer | preserveReifiedLabels | skosxl:*Label/literalForm → skos:*Label; optionally delete xLabels |
  | XNoteDereificationRDFTransformer | preserveReifiedNotes | `?c ?p⊑*skos:note ?n . ?n rdf:value ?v` → `?c ?p ?v` |
  | SchemeExporterTransformer | scheme | delete every concept not in the scheme (incoming refs, xLabels, own triples), then other schemes |
  | EDOAL2StdFlatFormatsTransformer | mappingProperties{}, subject_position entity1/2 | EDOAL cells → flat `e1 mappingProp e2` triples, replacing graph content |
  `FilterUtils.expandGraphs(conn, graphs)`: empty array → all contexts.
- **ReformattingExporter** (`export(conn, graphs, format) → ClosableFormattedResource`): default RDF serializer (Rio formats); others: Zthes, spreadsheet, SDMX, EDOAL serializer.
- **Deployer**: `RepositorySourcedDeployer` (deploy from repo, e.g. Graph Store HTTP deployer: PUT/POST per graph) or `StreamSourcedDeployer` (HTTP, S3, SFTP, OntoPortal, ShowVoc).

`PluginSpecification = {factoryId, configType, configuration(JSON), properties}`; `TransformationPipeline` = JSON array of `TransformationStep {filter: PluginSpecification, graphs: [IRI]?}` (graphs null/empty ⇒ all export graphs).

### 7.2 Export.export(graphs[]="all", filteringPipeline=[], includeInferred=false, outputFormat?, force=false, reformattingExporterSpec?, deployerSpec?)
1. Unless `force`: fail if null-context has triples (`NullGraphNotExportedException`) or any context is a BNode (`UnnamedGraphNotExportedException`).
2. graphs := all IRI contexts if empty.
3. No steps → format and download/deploy directly from the project connection.
4. Steps → copy **entire** repository (`exportStatements(null,null,null,includeInferred)`) into an in-memory repo; for each step i instantiate transformer and `transform(source, working, step2graphs[i])`; then format/deploy from the working copy.
5. `formatAndThenDownloadOrDeploy`: reformatting exporter (or Rio writer for `outputFormat`) → bytes → HTTP download (`Content-Disposition`) or deployer.
Other ops: getNamedGraphs, getOutputFormats, getExportFormats(reformattingExporterID).

### 7.3 InputOutput.loadRDF(inputFile?, baseURI, format?, transitiveImportAllowance, loaderSpec?, rdfLifterSpec?, transformationPipeline=[], validateImplicitly=false, flattenGraphs=false)
- Exactly one of file / loader. Default lifter = RDFDeserializingLifter when no loader.
- If pipeline non-empty: parse into an in-memory temp repo via `NullContextMappingRDFInserter` (null context → WG; `flattenGraphs` forces everything into WG), run transformers over `[WG]`, then copy into the project; else stream directly with `OntologyManager.getRDFHandlerForLoadData(conn, baseURI, WG, flattenGraphs, transitiveImportAllowance, failedImports)` which also processes `owl:imports` according to `TransitiveImportMethodAllowance` {web, webFallbackToMirror, mirror, mirrorFallbackToWeb, nowhere}.
- Format checks: lifter format must match MIME; else guess from MIME then filename.
- `validateImplicitly` (only if validation enabled): loads bypassing validation staging.
- Returns `Collection<OntologyImport>` (imported ontologies + failures).
Other ops: getSupportedFormats(extensionID), getParserFormatForFileName, getWriterFormatForFileName, clearData (drop all project data), getInputRDFFormats.

Python: `sip/io/{loaders.py, lifters.py, transformers.py, exporters.py, deployers.py, pipeline.py}`; `Pipeline.run(src: Dataset, steps) -> Dataset` operating on an rdflib `Dataset` copy; Fuseki: export via GSP `GET /ds/data?graph=` per graph, deploy via GSP `PUT`.

---------------------------------------------------------------------------------------------------

## 8. Alignment validation & generation

### 8.1 Data model (`FW/alignment/AlignmentModel.java`, `Cell.java`, `AlignmentUtils.java`; vocab `Alignment` = `http://knowledgeweb.semanticweb.org/heterogeneity/alignment#`)
Alignment API RDF/XML file loaded into a private in-memory repo, one per **session token** (`modelsMap`).
Alignment: `onto1`, `onto2`, `level`, `xml`, `type`. Cell: `entity1, entity2, measure(float), relation(string), mappingProperty?, status ∈ {accepted, rejected, error}, comment?, creator?`.
Known relations: `=`, `>`, `<`, `%`, `HasInstance`, `InstanceOf`; others = unknown/custom (UI asks a property per relation → `relationPropertyMap`).

### 8.2 Ops (`SVC/Alignment.java`, 23)
searchResources (candidate search in target dataset by lexicalizations of inputRes, per searchMode & lang→lexModel), getMappingCount/getMappings/filterMappings/exportMappings (existing mapping triples to a target namespace prefix, paged, default page size const), getAlignmentFormat, addAlignment(source, predicate, target) (single triple to WG), getMappingProperties(role, allMappingProps), **loadAlignment(file, leftProject?, rightProject?)**, listCells(pageIdx, range, sortBy ∈ entity1/2/measure asc/desc), acceptAlignment(e1, e2, relation, entity1Role?, forcedProperty?, setAsDefault), acceptAllAlignment, acceptAllAbove(threshold), rejectAlignment, rejectAllAlignment, rejectAllUnder(threshold), changeRelation(e1,e2,old,new), changeMappingProperty, **applyValidation(deleteRejected=false)**, applyValidationToEdoal, exportAlignment, getSuggestedProperties(role, relation), closeSession.

Algorithm:
1. **load**: parse; `performProjectsCheck`: onto1/onto2 must match the left/right project base URIs; if reversed (onto2 == current project) call `reverse()` (swap entity1/2, onto1/2, relation `<`↔`>`, HasInstance↔InstanceOf; not allowed with custom relations → `ReversedAlignmentWithCustomRelationsException`). `preProcess` collects relations; response `{onto1, onto2, unknownRelations[]}`.
2. **accept**: property = forcedProperty (optionally saved as default for that relation) or `suggestPropertiesForRelation(role(entity1), relation)[0]` where role via `RoleRecognitionOrchestrator.computeRole(entity1, projectConn)`. On success set `mappingProperty`, `status=accepted`; on `InvalidAlignmentRelationException` set `status=error`, `comment=msg`.
3. **suggestion table** (`AlignmentUtils.suggestPropertiesForRelation`):
   | role \ rel | = | < | > | % | InstanceOf | HasInstance |
   |---|---|---|---|---|---|---|
   | property (any) | owl:equivalentProperty, owl:sameAs | rdfs:subPropertyOf | error | owl:propertyDisjointWith | rdf:type | error |
   | concept | skos:exactMatch, skos:closeMatch | skos:broadMatch | skos:narrowMatch | — | skos:broadMatch, rdf:type | skos:narrowMatch |
   | cls | owl:equivalentClass, owl:sameAs | rdfs:subClassOf | error | owl:disjointWith | rdf:type | error |
   | individual | owl:sameAs | error | error | owl:differentFrom | rdf:type | error |
   (errors: "would require asserting a triple with the target as subject"; fallback to the relation's default property if set.)
4. **reject**: status=rejected. Thresholds: accept/reject all cells with measure ≥ / < threshold.
5. **applyValidation**: add `e1 mappingProperty e2` to WG for all accepted; if deleteRejected, for rejected cells remove existing `e1 p e2` (for every suggested p) present in WG; report `[{entity1, entity2, property, action: Added|Deleted}]`.
6. **applyValidationToEdoal**: write into an EDOAL project's alignment instead.
EDOAL service (`SVC/EDOAL.java`, 12): getAlignedProjects, getAlignments, createCorrespondence(alignment, left, right, relation, measure), setLeft/RightEntity, setRelation, setMeasure, setMappingProperty, deleteCorrespondence, getSuggestedProperties, getCorrespondences(page).

### 8.3 Generation (MAPLE + Remote Alignment Services / "Genoma")
- `SVC/MAPLE.java`: `profileProject()` runs the **LIME profiler** (lexicalization sets, coverage, languages, lexicalization model, `void:uriSpace`) on the project into the Metadata Registry stats graph; `checkProjectMetadataAvailability`; `profileMatchingProblemBetweenProjects(left, right, options)` → `AlignmentScenario` (left/right dataset descriptions, supportDatasets, pairings of lexicalization sets by shared language with scores, synonymizers, refinable task description); `profileSingleResourceMatchProblem(sourceResource, targetPosition)` (used by "resource alignment" dialog to choose target search languages/lexicalization model).
- `SVC/RemoteAlignmentServices.java` (15 ops): HTTP client of a matcher service implementing the MAPLE Alignment Services API: `GET /` (service metadata), `POST /matchers/search` (body = ScenarioDefinition → matchers), `GET /tasks` (list), `POST /tasks` (body `AlignmentPlan {scenarioDefinition, settings?, matcherDefinition?}` → task id), `GET /tasks/{id}/alignment` (Accept application/rdf+xml → loaded as an AlignmentModel = same validation UI), `DELETE /tasks/{id}`; config store for endpoints (+ basic auth) and per-project binding. Genoma is the reference server.

Python: `sip/alignment/{model.py (Cell, Alignment; rdflib-based parse/serialize of Alignment API RDF/XML), relations.py (table above), service.py (session-scoped models), edoal.py, remote.py (httpx client), profiler.py (LIME stats)}`.

---------------------------------------------------------------------------------------------------

## 9. Custom Forms, SPARQL, Datatypes/Lang

### 9.1 Custom forms (`SVC/CustomForms.java`, 30 ops; `FW/customform/*`; executed by **CODA** with **PEARL** rules)
Concepts:
- **CustomForm** (`CustomForm`, two kinds): `graph` (`CustomFormGraph`: PEARL rule producing a sub-graph — used for constructors and for "custom ranges" i.e. reified values) and `node` (`CustomFormNode`: single-value converter). Stored as XML (`<customForm id name type><description/><ref>PEARL</ref></customForm>`) under `projects/<p>/customForms/forms/` and system-level.
- **FormCollection**: `{id, forms[], suggestions[IRI]}` (XML `<formCollection id suggestions="iri,iri"><form id=".."/></formCollection>`).
- **FormsMapping** (FormCollectionMapping): `resource(IRI of property or class) → formCollection, replace: bool`. For a **property** the collection defines custom ranges (value editor); with `replace=true` the standard range editor is suppressed. For a **class** the collection defines **custom constructors** (used by createConcept/createClass/createInstance… `customFormValue`).
- Built-ins: form `it.uniroma2.art.semanticturkey.customform.form.reifiednote`, collection `...collection.note` with suggestions skos:note, changeNote, definition, editorialNote, example, historyNote, scopeNote.
- PEARL example (reified note):
  ```
  rule it.uniroma2...reifiednote id:reifiednote {
    nodes = { resource uri(coda:randIdGen("note", {})) .
              noteLang literal userPrompt/lang .
              noteLit literal(coda:langString($noteLang)) userPrompt/note . }
    graph = { $resource rdf:value $noteLit . } }
  ```
  `userPrompt/<field>` declares form fields (UI derives the form via `getCustomFormRepresentation`/`getForm(codaCore)` → `UserPromptStruct{placeholderId, userPromptName, rdfType uri|literal, datatype, lang, converter, mandatory, annotations}`); `stdForm/<field>` reads the StandardForm (resource, label, labelLang, xLabel, lexicalForm, schemes, lexicon, type) for constructors; annotations from `annDef.pr` (ObjectOneOf, DataOneOf, Role, Range, RangeList, Foreign, Collection, ...).
- Execution (`CustomFormGraph.executePearl`): builds a UIMA CAS annotation with feature structures userPrompt/sessionData/ctxData/stdForm, runs CODA → `UpdateTripleSet{insert, delete}`; the service adds them to WG. `isResourceCreationDelegated` → the PEARL `resource` node generates the IRI (otherwise IRI from caller/URI generator). Entry point placeholder = the node bound to the subject.
Ops: executeURIConverter/executeLiteralConverter, removeReifiedResource(subject, predicate, resource) (deletes via the CF graph pattern), getFormCollection/getAllFormCollections/create/clone/export/import/delete/updateFromCollection, getAllCustomForms, getCustomConstructors(resource), getCustomForm, getCustomFormRepresentation, create/clone/export/import/delete/updateCustomForm, isFormLinkedToCollection, validatePearl(pearl, formType), getCustomFormConfigMap, addFormsMapping(resource, formCollId, replace), removeFormCollectionOfResource, updateReplace, getBrokenCustomForms, updateCustomFormWithAnnotations, inferPearlAnnotations.
Python port: do not port CODA/UIMA; implement a **mini-PEARL** subset: `nodes` (uri(template|uuid), literal(lang|datatype) from `userPrompt/x`, `stdForm/x`), `graph` (triple patterns, OPTIONAL blocks), converters `coda:randIdGen`, `coda:langString`, `coda:datatype`, `coda:default`; module `sip/forms/{model.py, pearl_parser.py (lark), executor.py, registry.py}`; form representation = JSON schema for the UI.

### 9.2 SPARQL (`SVC/SPARQL.java`, 5 ops)
- `evaluateQuery(query, ql=SPARQL, includeInferred=true, bindings{}, maxExecTime=0, defaultGraphs[], namedGraphs[], repository=core|support)`: parse-validate (RDF4J SPARQLParser), prepare on the managed (change-tracked) connection, set inferred flag, bindings, dataset (`SimpleDataset` from default/named graphs; empty = whole repo), max exec time. Output wrapper `{resultType: boolean|tuple|graph, sparql: <SPARQL JSON results>}`; graph results converted to tuple `subj/pred/obj`.
- `executeUpdate(query, ..., defaultInsertGraph?, defaultRemoveGraphs[])`: validate + execute (so edits are tracked/validated like any other write).
- `exportQueryResultAsSpreadsheet` (xlsx/ods), `exportGraphQueryResultAsRdf(format)`, `suggestEndpointsForFederation(query)` (SERVICE suggestions from Metadata Registry).
- The **inferred toggle** maps to `includeInferred`; in Python: rdflib has no reasoning → offer `include_inferred` that queries the union with a materialized `owlrl` closure graph (`urn:sip:inferred`), or Fuseki with an inference dataset; mark such rows `tripleScope=inferred`.

### 9.3 Lang & datatypes
- Languages offered in UI = project setting `languages` (list `{name, tag}`), user can restrict "rendering languages" (`languages` PU setting, `*` = all) used by rendering engines and by value filters.
- `@LanguageTaggedString` params enforce a language tag on labels (pref/alt/hidden/literalForm).
- Datatypes service: §3.5. Client validates lexical forms against XSD regexes (DatatypeValidator) and facets from `getDatatypeRestrictions`.

---------------------------------------------------------------------------------------------------

## 10. VocBench 3 client (`vocbench3/src/app`)

### 10.1 Top-level routes / perspectives (`app-routing.module.ts`, 33 routes + 3 lazy modules)
| Route | Component | Purpose |
|---|---|---|
| /Home | HomeComponent | landing |
| /Projects | ProjectComponent (admin) | project list/open/create |
| **/Data** | DataComponent | main editing perspective: left `structure-tabset` (trees/lists) + right `resource-view-tabset` |
| /Edoal | EdoalComponent | EDOAL correspondence editor (alignment projects) |
| /DocTagging | DoctaggingComponent | document annotation |
| **/Sparql** | SparqlComponent | multi-tab YASGUI editor, parametrized queries (`sparql-tab-parametrized`), stored queries, export results |
| /Vocabularies | MetadataVocabulariesComponent | VoID/DCAT/LIME metadata |
| /Imports | NamespacesAndImportsComponent | prefixes, owl:imports, ontology mirror |
| /MetadataRegistry | MetadataRegistryComponent | dataset catalog (positions for RV/alignment) |
| **/History** | HistoryComponent | commit history (filters) |
| **/Validation** | ValidationComponent | accept/reject staged commits |
| **/AlignmentValidation** | AlignmentValidationComponent | load Alignment API file / remote task, cells table, accept/reject/threshold, apply |
| /Sheet2RDF | Sheet2RdfComponent | spreadsheet → RDF (CODA/PEARL) |
| /Diffing | DiffingComponent | diff between versions/projects |
| /Collaboration | CollaborationComponent | JIRA/Freedcamp issues |
| /CustomForm, /CustomFormView | CustomFormConfigComponent, CustomFormViewPage | CF/FC/mapping editor; custom views |
| /CustomServices | CustomServiceRouterComponent | user-defined SPARQL services |
| /Notifications | NotificationsComponent | watch/notifications |
| /ResourceMetadata | ResourceMetadataComponent | metadata patterns (dct:created etc.) |
| /LoadData, /ExportData | LoadDataComponent, ExportDataComponent | §7 pipelines (loader/lifter/transformers; exporter/deployer, graph selection, filters) |
| /Refactor | RefactorComponent | §4 (SKOS↔SKOSXL, base URI, default-graph migration) |
| /Versioning | VersioningComponent | dumps/versions |
| /Sysconfig, /Profile, /Preferences, /Registration/:firstAccess, /ResetPassword/:token, /UserActions | system & user | |
| /Administration (lazy) | users, roles, groups, project-user bindings | |
| **/Icv (lazy)** | IcvListComponent + 22 child routes | §5: DanglingConcept, NoSchemeConcept, NoTopConceptScheme, TopConceptWithBroader, DisjointRelatedConcept, DisjointExactMatchConcept, HierarchicalRedundancy, HierarchicalCycle, NoLabelResource (SKOS & SKOSXL variants), OnlyAltLabelResource, OverlappedLabelResource, OwlViolations, ConflictualLabelResource, NoLangLabelResource, ExtraSpaceLabelResource, NoMandatoryLabelResource, MutliplePrefLabelResource, DanglingXLabel, NoDefinitionResource, BrokenAlignment, BrokenDefinition, InvalidURI |
| /Selen (lazy) | SELEN module | |

ICV UI groups: Structural (9: dangling concepts, omitted top concept, concept in no scheme, top concept with broader, related-disjoint, exactMatch-disjoint, hierarchical redundancies, cyclic hierarchy [all SKOS]; OWL consistency [OWL]), Label (10: no skos prefLabel [lex SKOS], no skosxl prefLabel [SKOSXL], no mandatory label, only altLabel [SKOS/XL], no lang tag, overlapped, conflictual [SKOS/XL], extra whitespace, multiple prefLabel [SKOS/XL], dangling xLabel [SKOSXL]), Generic (4: no definition [SKOS], broken alignments [SKOS/OWL/RDFS], broken definitions, invalid URI).

### 10.2 Data perspective structures (`structures/**`, `models/DataStructure.ts`)
DataPanels (8 + custom): `cls` (class tree + instance list = `class-individual-tree-panel`), `concept` (concept tree), `conceptScheme` (scheme list), `skosCollection` (collection tree), `property` (property tree), `limeLexicon` (lexicon list), `ontolexLexicalEntry` (lexical-entry list, alphabetic index or search-based), `dataRange` (datatype list), `custom` (custom tree, configurable root/children query; `CustomTrees` service).
Per model (`modelPanelsMap`):
- RDFS: cls, property, dataRange — priority cls, property
- OWL: cls, property, dataRange — priority cls, property
- SKOS: cls, concept, conceptScheme, skosCollection, property, dataRange — priority concept, conceptScheme, skosCollection
- OntoLex: cls, concept, conceptScheme, skosCollection, property, limeLexicon, ontolexLexicalEntry, dataRange — priority limeLexicon, ontolexLexicalEntry, concept, conceptScheme
Panels can be hidden (`hiddenDataPanels` preference) and are filtered by authorization. Lists also: translation-set list (vartrans).
Tree service bindings: class tree → `Classes.getSubClasses(root=owl:Thing|rdfs:Resource, numInst)` + `ClassTreeFilter`; instance list → `Classes.getInstances` (or searchBased mode); concept tree → `SKOS.getTopConcepts/getNarrowerConcepts` with `ConceptTreePreference {baseBroaderProp=skos:broader, broaderProps, narrowerProps, includeSubProps=true, syncInverse=true, visualization hierarchyBased|searchBased, multischemeMode or|and, safeToGoLimit=1000}` (pre-count with `countTopConcepts`); collection tree → `getRootCollections/getNestedCollections`; property tree → `Properties.getTop*Properties/getSubProperties`; scheme list → `getAllSchemes` (+ active-scheme selection driving the concept tree); lexical entries → `OntoLexLemon.getLexicalEntriesByAlphabeticIndex` (indexBased) or search; search bar per panel → `Search.searchResource` with panel role and settings (mode, useLocalName, useURI, useNotes, langs, includeLocales, restrict to active schemes) + advanced/custom search modals; "reveal" → `Search.getPathFromRoot`.

### 10.3 Resource view client (`resource-view/**`, `models/ResourceView.ts`)
`ResViewSection` enum mirrors server keys (31 incl. alignment-specific `alignCellStruct`, `alignRefinement`).
Containers: `resource-view-tabset` (tabbed) / splitted mode; editors: `resource-view-editor` (sections rendered by `section-renderer/impl/*`, value renderers, context menu: rename=`Refactor.changeResourceURI`, deprecate=`Resources.setDeprecated`, delete, spawn concept from xLabel, move xLabel, assert inferred, copy locale), `term-view` (per-language term layout), `lexicographer-view` (OntoLex entry layout), `triple-editor` (source code = `getOutgoingTriples`/`updateResourceTriplesDescription`), `time-machine` (`getResourceViewAtTime`), `ResourceViewType {resourceView, termView, lexicographerView, sourceCode}`. Lazy section (`collections`) is fetched with `SKOS.getCollectionsForConcept`. "Add manually" sections and per-section "add" actions map to the service ops in §2–§3 (types→Individuals.addType, classaxioms→Classes.addSuperCls/Manchester, broaders→SKOS.addBroaderConcept, lexicalizations→SKOS/SKOSXL/Resources by lex model, notes→SKOS.addNote, domains/ranges→Properties.add*, facets→add/remove type, etc.). Inferred values are shown when `includeInferred` toggle (RV settings) is on; styling by `tripleScope` (local=editable, imported=grey, inferred=italic, staged=green, del_staged=red-strike).

### 10.4 Client services
61 Angular service wrappers in `services/` (one per ST service: skos, skosxl, classes, properties, individuals, resources, resource-view, refactor, icv, search, input-output, export, alignment, edoal, maple, remote-alignment, custom-forms, sparql, datatypes, manchester, ontolex-lemon, history, validation, ...). HTTP convention: `GET|POST /semanticturkey/it.uniroma2.art.semanticturkey/st-core-services/<Service>/<operation>?ctx_project=...&ctx_wgraph=...` with NT-serialized RDF params.

---------------------------------------------------------------------------------------------------

## 11. Proposed Python package layout (Semantic Intelligence Platform)
```
sip/
  core/          store.py (Store protocol: RdflibStore(Dataset), FusekiStore(SPARQLWrapper/GSP)),
                 context.py (Project: base_uri, wg, lex_model, model_type, prefixes, languages),
                 annotated.py (AnnotatedValue), nature.py, render.py, uri_gen.py, tx.py (add/remove sets, events)
  resource_view/ (§1)
  skos/          tree.py concepts.py schemes.py collections.py labels.py notes.py xl.py (§2)
  ontolex/       entries.py lexicons.py senses.py
  owl/           classes.py properties.py individuals.py datatypes.py manchester/ (lark grammar + renderer)
  resources.py   generic triple editing (§3.4)
  refactor/      (§4)
  icv/           checks.py fixes.py registry.py (§5)
  search/        modes.py strategy_regex.py strategy_text.py service.py path_from_root.py (§6)
  io/            loaders lifters transformers exporters deployers pipeline (§7)
  alignment/     model.py relations.py service.py edoal.py remote.py profiler.py (§8)
  forms/         pearl_parser.py executor.py registry.py (§9)
  sparql.py      evaluate/update with dataset & inferred toggle (§9.2)
  api/           FastAPI routers mirroring ST service/op names (keeps VocBench-compatible JSON shapes)
```
Porting invariants checklist:
1. Writes only in WG; deletions only in WG; read over union.
2. Pref-label uniqueness per language: setPrefLabel demotes old pref→alt (SKOS & SKOS-XL); clash checks (pref/pref within same scheme & role, pref/alt) are opt-out flags.
3. Top concepts are declared (topConceptOf/hasTopConcept) when a scheme is active; "no broader" otherwise.
4. Hierarchy = broader ∪ inverse(narrower) incl. subproperties, minus broadMatch/narrowMatch; one inverse only (first owl:inverseOf hit).
5. Deletes cascade only through skosxl label links (concepts/schemes/collections) and bnode list nodes; classes/properties require emptiness preconditions.
6. Ordered collections: RDF lists typed rdf:List, `memberList rdf:nil` when empty; positions are 1-based.
7. Resource view: statement dispatch by subPropertyOf* to section roots, first match wins, leftovers in `properties`; tripleScope per §1.5; DESCRIBE extras flagged inferred.
8. Search matching is case-insensitive regex; fuzzy = single-substitution/edge-insertion neighbourhood; lang filter exact or prefix (includeLocales).
9. Alignment relation→property mapping per §8.2 table; rejected cells optionally delete existing mapping triples; errors stored on the cell (status=error).
10. Export never mutates the project: transformers run on an in-memory copy; refuse null/bnode contexts unless forced.
