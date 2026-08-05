# Wiring the Fuseki bridge into Ontology-Playground

The Python backend (`ontology_modeler.playground.api`) already does the hard part: projecting a
full Fuseki graph to Playground's model and merging edits back **without losing** the ~80–96% of
triples Playground can't represent. The frontend work is small and additive — no changes to the
existing RDF/XML import/export paths.

## 0. Run the backend

```bash
cd "src/Ontology Modeler"
PLAYGROUND_ORIGINS=http://localhost:5173 python -m ontology_modeler.playground.api   # :8080
```

Point the app at it (Playground `.env`):

```
VITE_ENABLE_FUSEKI=true
VITE_FUSEKI_BRIDGE_URL=http://localhost:8080
```

## 1. Add the client

Copy `fusekiSource.ts` to `src/lib/rdf/fusekiSource.ts`. It exposes
`listOntologies()`, `loadFromFuseki(graphUri)`, `saveToFuseki(graphUri, ontology, {dryRun})`,
and `bridgeHealthy()`.

## 2. Extend the model with `kind` (2 lines)

In `src/data/ontology.ts`:

```ts
export interface EntityType   { /* …existing… */ kind?: 'class' | 'concept'; }
export interface Relationship { /* …existing… */ kind?: 'subClassOf' | 'broader' | 'narrower' | 'mapping' | 'objectProperty'; }
```

These are optional, so nothing else breaks. The server always re-derives `kind` from the base
graph on save, so it does **not** need to survive a lossy client round-trip — it's purely for
rendering.

## 3. Store actions (`src/store/appStore.ts`)

```ts
import { loadFromFuseki, saveToFuseki } from '../lib/rdf/fusekiSource';

loadGraph: async (graphUri: string) => {
  const env = await loadFromFuseki(graphUri);
  set({ ontology: env.ontology, fuseki: { graphUri: env.graphUri, baseNs: env.baseNs } });
},

saveGraph: async ({ dryRun = false } = {}) => {
  const { ontology, fuseki } = get();
  if (!fuseki) throw new Error('no Fuseki graph loaded');
  return saveToFuseki(fuseki.graphUri, ontology, { dryRun });   // catch PreservationError in the UI
},
```

Keep the loaded `graphUri` in state — it's the save target. Because the backend re-fetches and
re-projects on save, you do **not** need to hold the original graph or any provenance client-side.

## 4. UI (minimal)

- **Graph picker**: call `listOntologies()`, show `graphUri` + `nodeCount`, on select → `loadGraph`.
- **Save button**: call `saveGraph()`. Recommended: run `saveGraph({ dryRun: true })` first and
  show "+A / −B triples" so the user confirms before the write.
- **Preservation guard**: `saveToFuseki` throws `PreservationError` (HTTP 409) with `.violations`
  if a write would touch anything outside the editable surface — surface it as a blocking error,
  not a silent failure. In normal use it never fires; it's the backstop.

## 5. Node/edge rendering (`kind`)

Use `kind` for visual distinction in the Cytoscape stylesheet:

| `kind` | element | suggested style |
|---|---|---|
| `class` (node) | entity | solid fill, box icon |
| `concept` (node) | entity | lighter fill, tag icon |
| `subClassOf` (edge) | relationship | solid arrow → parent |
| `broader` / `narrower` (edge) | relationship | dashed arrow (SKOS hierarchy) |
| `mapping` (edge) | relationship | dotted arrow (cross-ontology; target may be a FIBO IRI) |
| `objectProperty` (edge) | relationship | labelled solid arrow |

## What the user can safely edit (round-trips to Fuseki)

Node name/description; add/remove/rename classes and concepts; datatype-property name/type/
description; object-property domain/range/name/description; `subClassOf`, `broader`/`narrower`,
and mapping edges. Everything else in the graph (restrictions, imports, individuals, other
annotations) is **preserved untouched** — visible-but-not-editable is out of scope for Phase 2
and simply passes through.

## Not yet wired (later phases)

- **Phase 3** — a dedicated org↔FIBO mapping mode writing to a separate mapping graph.
- **Phase 4** — a read-only "inferred" overlay from the reasoner.
