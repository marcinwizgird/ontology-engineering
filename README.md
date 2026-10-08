# Semantic Intelligence Platform

This repository builds the **Semantic Intelligence Platform (SIP)**: an end-to-end,
agent-assisted platform that carries an ontology and its knowledge graph from the first
brief to a published, queried release.

```
scope → acquire → model → validate → review ║ populate → reason → publish ║ consume
```

An agent assists every stage, and a human decides at the two gates (`║`). SIP
reverse-engineers Protégé Desktop (OWL 2 authoring and reasoning) and VocBench 3 /
Semantic Turkey (governance, change tracking, SKOS) into Python. It is specified in
SysML v2 using the Rozanski & Woods viewpoints.

## Layout

| directory | contents |
|---|---|
| [`sip/`](sip/README.md) | **The platform.** `semantic_intelligence/` is the Python package; `architecture/` holds the architecture description and SysML v2 models. |
| [`capabilities/`](capabilities/CAPABILITY_MAP.md) | Everything else that was built here, mapped as a **potential SIP capability**: the Ontology Validation Agent, Ontology Modeler, Converter, Enricher, bottom-up and grounded extraction, construction processes, the capability model, and earlier architecture design sets. |
| [`LAB/`](LAB/README.md) | The **knowledge base** SIP is constructed from: the Ontology Engineering course (`LAB/oe-course`), with each chapter mapped to the SIP stage it informs. |
| [`knowledge/`](knowledge/) | Source documents: Keet's *Ontology Engineering*, the requirements report, the converter and assistant specifications. |
| [`Ontology Repository/`](Ontology%20Repository/) | Ontology corpora (FIBO), used as test data. |
| [`infra/`](infra/) | Docker Compose for Apache Jena Fuseki and FalkorDB. |

## Quick start

```bash
pip install -r requirements.txt
cd sip
PYTHONPATH=. python -m pytest semantic_intelligence/tests -q   # offline test suite
PYTHONPATH=. python -m semantic_intelligence                   # end-to-end demo
python architecture/tools/sysml_check.py                       # check the SysML models
```

The default is offline: agents run on deterministic simulators. Live Claude agents are an
explicit opt-in (`SIP_MODEL=claude-opus-5-5`, needs `ANTHROPIC_API_KEY`).

## Where to read next

* [`sip/architecture/ARCHITECTURE_DESCRIPTION.md`](sip/architecture/ARCHITECTURE_DESCRIPTION.md):
  stakeholders, concerns, principles, scenarios and every viewpoint.
* [`capabilities/CAPABILITY_MAP.md`](capabilities/CAPABILITY_MAP.md): each capability with its
  SIP stage, its SIP functional element, and its integration status.
* [`LAB/README.md`](LAB/README.md): how the course chapters feed SIP.
