# Semantic Intelligence Platform: architecture

This folder holds the architecture of the Semantic Intelligence Platform (SIP). The
platform builds ontologies and knowledge graphs end to end, with agent assistance at
every stage. Its design and code come from **reverse-engineering Protégé Desktop and
VocBench 3 / Semantic Turkey** and translating them into Python. The architecture is
described with **SysML v2** models and the **Rozanski & Woods** method (viewpoints and
perspectives).

| Document | What it is |
|---|---|
| [ARCHITECTURE_DESCRIPTION.md](ARCHITECTURE_DESCRIPTION.md) | **The architecture description.** It covers stakeholders and concerns, principles, scenarios, the seven views (Context, Functional, Information, Concurrency, Development, Deployment, Operational), eleven perspectives (including a custom *AI Trustworthiness* perspective), ADRs and open issues |
| [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) | What was read and how. It explains how each tool is built, gives the **Java → Python translation map** with a fidelity rating per mechanism, lists the defects found and not copied, and reports measurements on FIBO |
| [`reverse_engineering/`](reverse_engineering/) | About 4,200 lines of source-level notes (paths, pseudo-code, counts) behind the translation |
| [`models/`](models/) | **SysML v2 textual models**, 10 packages, about 2,000 lines (listed below) |
| [`tools/sysml_check.py`](tools/sysml_check.py) | Model checker and generator: checks references, completeness and the structural guarantees, and writes the traceability table and diagrams |
| [`generated/TRACEABILITY.md`](generated/TRACEABILITY.md) | 52 requirements, each traced to the element that satisfies it and the case that verifies it (generated) |
| [`generated/diagrams/`](generated/diagrams/) | 11 Mermaid diagrams generated from the models |

The SysML packages:

| Package | Contents |
|---|---|
| `sip_viewpoints` | stakeholders, concerns, the 7 R&W viewpoints, perspective/tactic/provenance metadata |
| `sip_requirements` | 33 functional + 19 quality requirements |
| `sip_context` | context viewpoint: system, external entities, ports, use cases |
| `sip_functional` | functional viewpoint: elements, interfaces, white box, `satisfy` links |
| `sip_information` | information viewpoint: graph layout, items, lifecycles |
| `sip_behaviour` | E2E process, guarded call, agent loop, reasoner status |
| `sip_deployment` | concurrency, deployment and operational viewpoints, allocations |
| `sip_development` | development viewpoint: modules, layering |
| `sip_perspectives` | 11 perspectives as requirement groups, 13 tactics, the 7 views |
| `sip_verification` | 18 verification cases bound to named tests |

The implementation is in
[`sip/`](../).

## Run it

```bash
# the model check (also runs inside the test-suite)
python sip/architecture/tools/sysml_check.py --write

# the implementation: 74 tests, offline, about 10 s
cd "sip"
PYTHONPATH=. python -m pytest semantic_intelligence/tests -q

# the end-to-end scenario S1: brief + document + table -> gated release -> grounded Q&A
PYTHONPATH=. python -m semantic_intelligence.demo
```

## The design in brief

* **Protégé contributes** the axiom-level OWL authoring model:
  - a Manchester parser, renderer and completer (Python, 99.6% exact round-trip on FIBO);
  - hierarchy providers, description frames and every refactoring;
  - a derived reasoner status;
  - black-box justifications.
* **VocBench / Semantic Turkey contributes** the governed, triple-level spine:
  - the nine roles, the CRUDV capability algebra and the authorization algorithm, verbatim;
  - complete change tracking in the CHANGELOG vocabulary, with staged validation;
  - SKOS/SKOS-XL, the resource view, ICV with fixes, search, alignment and the
    transformer pipeline.
* **New in SIP:**
  - an end-to-end lifecycle with two human gates, and competency questions as
    executable tests;
  - nine stage agents, each a fixed *plan → propose → criticise → submit* loop.
    Agents run as **machine principals**: their writes are always staged with evidence,
    they can never validate, and they reach the platform only through the same guarded
    operations as people. The SysML model checker and the test-suite both verify this.
