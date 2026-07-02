# Ontology → Labeled Property Graph (LPG) Converter

A production-grade, modular ETL pipeline that converts general RDF foundational
ontologies into a **schema-level Meta-Graph in FalkorDB**. Implemented per the
specification in `docs/LPG Ontology Coverter/LPG Ontology Converter.md`.

It recursively loads an ontology and its `owl:imports` closure, transforms the
schema into a `networkx.MultiDiGraph` **Intermediate Representation (IR)**, and
ingests the IR into FalkorDB with idempotent, parameterised, batched Cypher.

> **MVP scope (per spec):** schema only — no business-data instances — and
> complex OWL restrictions (blank nodes) are ignored entirely.

## Architecture — Strategy Pattern (Extract / Transform / Load)

| Stage | Class | Responsibility |
|-------|-------|----------------|
| **Extract** | `RecursiveOntologyLoader` | Parse RDF; follow `owl:imports` recursively into one shared `rdflib.Graph`; seed the IR with `(:Ontology)` nodes and `[:IMPORTS]` edges; carry namespace bindings across merges for readable QNames. |
| **Transform** | `UniversalOntologyConverter` | Walk the unified graph and populate the IR with schema nodes and edges. |
| **Load** | `FalkorDBExporter` | `MERGE` the IR into FalkorDB via `UNWIND`-batched, parameterised Cypher. Falls back to a **dry-run** (logs Cypher) when FalkorDB is unavailable. |

### Mapping rules implemented

**Nodes** (`rdf:type` → label): `owl:Class`→`(:OWLClass)`,
`owl:ObjectProperty`→`(:ObjectProperty)`, `owl:DatatypeProperty`→`(:DatatypeProperty)`,
`owl:AnnotationProperty`→`(:AnnotationProperty)`. Blank nodes are skipped.

**Node properties:** every `Literal` on a node (e.g. `rdfs:label`, `skos:definition`)
is stored as a string with a Cypher-safe key (`skos:definition` → `skos_definition`).
Multiple values for one key are joined with ` | `.

**Edges:** `rdfs:subClassOf`→`[:SUBCLASS_OF]`, `rdfs:subPropertyOf`→`[:SUBPROPERTY_OF]`,
`rdfs:domain`→`[:HAS_DOMAIN]` (Property→Class), `rdfs:range`→`[:HAS_RANGE]` (Property→Class).

**Lineage:** `rdfs:isDefinedBy`→`(SchemaNode)-[:DEFINED_IN]->(:Ontology)`, connecting
schema to the root ontology nodes created by the loader.

## Run the demo

```bash
pip install -r requirements.txt
python ontology_to_lpg.py
```

The demo points at `sample/root_ontology.rdf`, which `owl:imports` the bundled
`sample/imported_ontology.rdf` (redirected to the local file so it runs **offline**).
Expected IR:

```
IR node labels: {AnnotationProperty: 1, DatatypeProperty: 1, OWLClass: 5,
                 ObjectProperty: 2, Ontology: 2, Resource: 1}
IR edge types : {DEFINED_IN: 9, HAS_DOMAIN: 3, HAS_RANGE: 3,
                 IMPORTS: 1, SUBCLASS_OF: 4, SUBPROPERTY_OF: 1}
```

(`Resource` is a stub node for `xsd:integer`, the range of a datatype property —
edge endpoints that were never typed as schema get a minimal `(:Resource)` node so
Cypher `MATCH` always resolves.)

### Loading into a real FalkorDB

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

With the server up, `ontology_to_lpg.py` connects automatically (`localhost:6379`,
graph `ontology_meta`) and executes the `MERGE`/`UNWIND` statements instead of
logging them. Re-running is safe — all writes are idempotent.

### Converting a real ontology (e.g. FIBO)

```python
from ontology_to_lpg import build_pipeline
build_pipeline("https://spec.edmcouncil.org/fibo/ontology/FND/AboutFND/",
               uri_to_location=None)   # let rdflib fetch owl:imports over the network
```

Drop the `uri_to_location` resolver to fetch imports live; the loader tolerates
unreachable imports (logs a warning and continues).

## Visualization notebooks (load & visualise, no LPG export)

`notebooks/` contains Jupyter notebooks that reuse the loader + converter but
**stop before the FalkorDB step** — they build the NetworkX meta-graph IR and
visualise it with `matplotlib`:

| Notebook | What it does |
|----------|--------------|
| `01_visualize_fibo_foundational.ipynb` | Loads **one** FIBO Foundational ontology (`FND/Parties/Parties.rdf`) and visualises its schema meta-graph. |
| `02_visualize_two_ontologies.ipynb` | Loads **two separate** ontologies — FIBO Foundational (`FND/Parties`) and FIBO Persons & Accounts (`FBC/ProductsAndServices/ClientsAndAccounts.rdf`) — and visualises them individually and combined, coloured by source ontology. |

Shared logic (loading, summarising, drawing, composing) lives in
`notebooks/nb_helpers.py`; `notebooks/_build_notebooks.py` regenerates the
`.ipynb` files. The notebooks load each ontology with `follow_imports=False` for
clean, offline, single-module views (references to imported classes appear as
grey `Resource` stubs). Two small, backward-compatible additions to the pipeline
support them: `RecursiveOntologyLoader(follow_imports=...)` and the
`build_local_catalog()` utility (maps ontology IRIs → local files for offline
`owl:imports` resolution).

```bash
pip install -r requirements.txt      # plus: jupyterlab, matplotlib, pandas
cd notebooks && jupyter lab          # run 01 then 02
```

## Files

```
Ontology Converter/
├── ontology_to_lpg.py          # the complete, self-contained pipeline
├── requirements.txt
├── README.md
├── sample/
│   ├── root_ontology.rdf       # domain ontology (imports the foundational one)
│   └── imported_ontology.rdf   # foundational ontology
└── notebooks/
    ├── nb_helpers.py           # shared load / summarise / draw helpers
    ├── _build_notebooks.py     # regenerates the notebooks
    ├── 01_visualize_fibo_foundational.ipynb
    └── 02_visualize_two_ontologies.ipynb
```
