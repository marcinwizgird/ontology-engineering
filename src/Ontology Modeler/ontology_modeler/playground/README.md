# playground — Fuseki-backed OWL+SKOS editing bridge

Adapts Microsoft **Ontology-Playground** into an editing surface over **Apache Jena Fuseki**:
load a named graph, edit it visually, and propagate changes back **without losing** the triples
Playground's model can't represent (measured: ~80% of a FIBO module, ~90%+ of a SKOS scheme).

## How it stays safe

Playground reads only named `owl:Class` / `owl:DatatypeProperty` / `owl:ObjectProperty` + single
domain/range + `rdfs:label`/`comment`. Everything else — `subClassOf`, `owl:Restriction`, SKOS,
imports, individuals — is invisible to it. So write-back never re-serialises Playground's output.
Instead:

```
load:  Fuseki graph ──project()──▶ unified projection (owl:Class & skos:Concept as nodes,
                                    subClassOf/broader/narrower/mapping/objectProperty as edges)
save:  edited projection ──merge()──▶ a COPY of the full base graph with only the surfaced
                                       fields changed ──GraphSynchronizer.sync()──▶ Fuseki
```

A `guard()` refuses any save whose diff would touch a blank node or a non-editable predicate — a
backstop behind the merge so a bug can never silently delete restrictions or imports.

## Modules

| file | role |
|---|---|
| `model.py`   | Playground's `Ontology` shape in Python, + node/edge `kind` |
| `project.py` | full graph → unified projection (+ exact provenance) |
| `merge.py`   | edited projection → full base graph, surfaced fields only |
| `service.py` | load/save orchestration + preservation guard (reuses `FusekiClient`, `diff.py`) |
| `api.py`     | FastAPI proxy (`/ontologies`, `/ontology` GET/PUT) |
| `frontend/`  | `fusekiSource.ts` client + `INTEGRATION.md` for the React app |
| `tests/`     | `test_roundtrip.py` (projection/merge), `test_service.py` (full save cycle, offline) |

## Run

```bash
cd "src/Ontology Modeler"
python ontology_modeler/playground/tests/test_roundtrip.py   # projection/merge proofs
python ontology_modeler/playground/tests/test_service.py     # full save cycle (no Fuseki needed)

PLAYGROUND_ORIGINS=http://localhost:5173 python -m ontology_modeler.playground.api   # serve :8080
```

See `frontend/INTEGRATION.md` to wire the React app.
