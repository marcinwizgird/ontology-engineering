# CLAUDE.md

## Purpose: the Semantic Intelligence Platform (SIP)

This repository builds the **Semantic Intelligence Platform (SIP)**: an end-to-end,
agent-assisted platform that carries an ontology and its knowledge graph from the first
brief to a published, queried release.

```
scope → acquire → model → validate → review ║ populate → reason → publish ║ consume
```

* **What it is.** SIP takes Protégé Desktop's OWL 2 authoring and reasoning and VocBench 3 /
  Semantic Turkey's governance, change tracking and SKOS, translates them into Python, and
  adds an agent layer. The result is one platform.
* **How it works.** A specialist agent assists each lifecycle stage. A human decides at
  the two gates (`║`): the review gate before population, and the release gate before
  publishing. Agent writes are staged commits until a validator accepts them.
* **How it is specified.** SysML v2 models plus a Rozanski & Woods architecture
  description (stakeholders, concerns, viewpoints, perspectives).
* **Storage.** Apache Jena Fuseki holds the canonical RDF/OWL. FalkorDB holds a derived
  property-graph projection used for GraphRAG and queries.

**SIP is the product.** Every other module in the repo is a *potential SIP capability*,
and the OE course is the *knowledge base* SIP is constructed from. When deciding where
work goes or what to prioritise, ask what it contributes to SIP.

## Layout

| directory | contents |
|---|---|
| `sip/` | The platform. `semantic_intelligence/` is the Python package; `architecture/` holds the architecture description and SysML v2 models (`ARCHITECTURE_DESCRIPTION.md`). |
| `capabilities/` | Everything else, as potential SIP capabilities. Each one has a row in `capabilities/CAPABILITY_MAP.md`: stage, SIP element, status (absorbed / reused / candidate / reference) and next step. |
| `LAB/oe-course` | The Ontology Engineering course (Keet, 2nd ed.), the knowledge base. `LAB/README.md` maps each chapter to a SIP stage. It is self-contained and imports only `oe_course`. |
| `LAB/oe-agentic-course` | The agentic track: the original course content ported so code grows per chapter in `agentlab/` (each module has `INTRODUCED_IN`; never import ahead, enforced by `tests/test_incremental.py`). Notebook sources are percent-format `NN_*.py`; problem sets are one `NN_problem_set.py` with `assignment`/`solution` cell tags. Regenerate `.ipynb` with `python tools/build_notebooks.py`. |
| `knowledge/` | Source documents: Keet's book, the requirements report, specifications. |
| `Ontology Repository/` | Ontology corpora (FIBO), used as test data. |
| `infra/` | Docker Compose for Fuseki and FalkorDB. |

**Where new work goes:**
* Platform code and architecture go under `sip/`.
* Anything else goes under `capabilities/`, and gets a row in `CAPABILITY_MAP.md` in the same change.
* Course material goes under `LAB/`.

## Commands

```bash
# SIP: run from sip/
cd sip
PYTHONPATH=. python -m pytest semantic_intelligence/tests -q   # offline suite (103 tests)
PYTHONPATH=. python -m semantic_intelligence                   # end-to-end demo
python architecture/tools/sysml_check.py                       # SysML v2 structural check

# Capabilities: the former root packages import each other, so run them from capabilities/
cd capabilities
python -m pytest ontology_construction/tests -q
cd ontology_agents && python -m pytest validation_agent/tests -q   # 107 tests
```

Known pre-existing failures: `langextract_ontology.tests` raises an ImportError for
`SimulatedOntologyModel`, and `ontology_modeler/playground/tests` has 2 setup errors.

## Rules

* **Offline by default.** Agents run on deterministic simulators. Live Claude agents are
  opt-in (`SIP_MODEL=claude-opus-5-5`). `ANTHROPIC_API_KEY` is set in this environment, so
  **ask before any live or billed run**.
* **Generated docs are not edited by hand.** The Ontology Validation Agent's
  `CHECK_CATALOGUE.md` is generated from `spec/check_catalogue.py` (131 checks, 16
  families, maturity M1–M5, SIP stage) by `python spec/build_docs.py`. The same applies to
  other `build_*.py` / `_build_*.py` outputs: edit the source model, then regenerate.
* `Platform.call` is SIP's only entry point. Every operation declares the VocBench
  capability it needs, and SIP uses Semantic Turkey's nine roles verbatim.
* Keep the core dependency-light (stdlib, rdflib, owlrl, networkx). Executed notebooks
  serve as functional tests.
* `syside` needs a licence key, so the SysML models are validated with the in-repo checker
  instead.
* The Ontology Modeler's Fuseki graph URNs are derived from repo-relative paths. After
  moving files, reload Fuseki (`infra/fuseki/scripts/load.ps1`).

## Environment (Windows)

* The console is cp1252: avoid non-ASCII in `print`, or set `PYTHONIOENCODING=utf-8`.
* Some directory names contain spaces (`capabilities/architecture/technical architecture`,
  `Ontology Repository`). Quote those paths, and import those modules as top-level, not as
  subpackages.
* No Java and no native cairo, so HermiT/Pellet and SVG rasterisation are unavailable.
  Use owlrl (OWL 2 RL) and verify SVGs structurally.
