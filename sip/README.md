# `semantic_intelligence`: the Semantic Intelligence Platform in Python

This package is Protégé's OWL authoring and reasoning plus VocBench 3's governance and
vocabulary management, translated into Python and joined by an agent layer that assists
every lifecycle stage. The architecture, written in SysML v2 using the Rozanski & Woods
method, is in
[`sip/architecture/`](architecture/).

```bash
cd "sip"
PYTHONPATH=. python -m pytest semantic_intelligence/tests -q     # 103 tests, offline
PYTHONPATH=. python -m semantic_intelligence                     # the E2E demo
PYTHONPATH=. uvicorn semantic_intelligence.api.app:app           # REST API + workbench at /ui
```

Requirements: `rdflib`, `owlrl`, `fastapi` (API), `anthropic` (live agents only), and
optionally `owlready2` + Java (OWL 2 DL).

## Using it

```python
from semantic_intelligence.platform import Platform
from semantic_intelligence.core.principal import Principal

P = Platform()                                    # in-memory; FusekiStore(client) for Fuseki
P.registry.add_principal(Principal("admin", is_admin=True))
P.registry.add_principal(Principal("ann"))
P.call("admin", None, "governance.createProject", name="cars", base_uri="https://ex.org/cars")
P.call("admin", "cars", "governance.bind", principal="ann", roles=["ontologist"])

P.call("ann", "cars", "owl.createClass", name="Car")
P.call("ann", "cars", "owl.createClass", name="Wheel")
P.call("ann", "cars", "owl.createProperty", name="hasPart", label="has part")
P.call("ann", "cars", "owl.addAxiom", subject="Car", kind="SubClassOf",
       expression="'has part' exactly 4 Wheel")          # Manchester, by label
P.call("ann", "cars", "owl.complete", text="hasPart some W")   # Protégé-style completion
P.call("ann", "cars", "reasoning.classify")              # OWL2-RL, profile-labelled
P.call("ann", "cars", "quality.runChecks")               # Semantic Turkey ICV + logical
P.call("ann", "cars", "history.undo")                    # Protégé undo, kept as a commit
```

Virtual knowledge graph (R2RML, Ontop's role). Map a relational database onto the
ontology, then query the data while you edit the ontology:

```python
P.call("ann", "cars", "mapping.registerDatabase", source_id="fleet", path="fleet.sqlite")
P.call("ann", "cars", "mapping.suggest", source_id="fleet")       # scored proposals, no writes
P.call("ann", "cars", "mapping.addTriplesMap", source_id="fleet", map={
    "id": "CarMap", "table": "cars",
    "subject": {"template": "https://ex.org/cars/data/car/{id}", "classes": ["Car"]},
    "predicateObjects": [{"predicate": "hasPart", "template": "https://ex.org/cars/data/wheel/{wheel_id}"}]})
P.call("ann", "cars", "mapping.validate")                         # vs the staged ontology + schema
P.call("ann", "cars", "mapping.queryData", query="SELECT ?c WHERE { ?c a <https://ex.org/cars#Car> }")
```

Maps are commits on the `mappings` graph: history and undo apply, and an agent's maps
are staged. `refactor.renameIRI` updates them in the same commit. `mapping.queryData`
reads the staged ontology with RDFS entailment, so a new `rdfs:subClassOf` changes the
answers without re-mapping. `mapping.export` / `mapping.import` exchange R2RML Turtle
with Ontop (`LAB/PoCs/SPARQL-2-SQL`).

Agents:

```python
from semantic_intelligence.agents.orchestrator import Conductor
C = Conductor(P)                 # offline simulators unless SIP_MODEL=claude-opus-5-5
C.enable_agents("cars", by="pm")  # needs rbac C; creates <agent>@cars machine principals
C.run("cars", "pm", brief=..., documents={...}, tables={...})   # stops at the review gate
```

Every operation (92, listed by `GET /operations` or `platform.describe_operations()`)
declares the VocBench capability it needs. `Platform.call` is the only entry point.
Writes become commits; when the caller is an agent, a commit is staged until a validator
accepts it.

| Package | Translates |
|---|---|
| `core/` | Semantic Turkey change-tracking SAIL, history and validation; Protégé HistoryManager |
| `governance/` | ST roles, CRUDV capabilities, `isAuthorized`, ACL/locks, settings scopes, URI generators; Protégé entity creation |
| `owl/` | OWL API structural model over RDF, Manchester syntax, renderers, hierarchy providers, frames, ST resource view, refactorings |
| `skos/` | ST SKOS and SKOS-XL services |
| `reasoning/` | Protégé reasoner manager and status; owlexplanation justifications |
| `scope/` | new: NeOn requirements specification, reuse candidates (ST metadata registry), pre-glossary, scope exit criteria |
| `quality/` | ST ICV, Protégé metrics, competency-question tests, release gate |
| `search/`, `alignment/`, `io/`, `kg/` | ST search, alignment, import/export transformers; Sheet2RDF-style lifting, entity resolution, LPG projection |
| `vkg/` | Ontop / W3C R2RML: read-only relational sources (sqlite3; DuckDB optional), R2RML maps in the `mappings` graph, suggestions, static checks, previews, SPARQL over mapped data + the staged ontology |
| `agents/` | new: LLM gateway, agent runtime, 9 specialist agents, simulators, lifecycle conductor |
| `api/` | FastAPI edge over the operation registry |
