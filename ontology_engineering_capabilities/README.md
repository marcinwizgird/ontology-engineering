# Ontology Engineering Capability Model

Comprehensive **requirements for an ontology-engineering practice**, expressed
as **business** and **technology capabilities**, arranged as a **taxonomy** and
an **ontology**, and each mapped to a pillar and target maturity level of the
**EKGF Enterprise Knowledge Graph Maturity Model (EKG/MM v1.0)**.

> The Gemini share link in the request could not be retrieved automatically (it
> resolves to a Google sign-in shell rather than public content). The model is
> grounded in the public EKGF maturity model + ontology-engineering practice;
> paste the conversation text and the model can be extended to fold it in.

## What's here

| File | Purpose |
|---|---|
| `capability_model.py` | The model: 44 capabilities × 10 categories × 2 domains, each with EKGF pillar, target level (1–5), requirement statement and `dependsOn`/`supports`/`governedBy` relations. |
| `generators.py` | networkx graphs, Mermaid, ArchiMate SVG, RDF/OWL/SKOS Turtle, matplotlib visualisations, requirements doc. |
| `build_artifacts.py` | Regenerates every artifact into `artifacts/`. |
| `REQUIREMENTS.md` | The generated, comprehensive requirements document. |
| `demo.ipynb` | Interactive walk-through (load model, visualise, export). |

### Generated artifacts (`artifacts/`)

| Artifact | Description |
|---|---|
| `capability_archimate.svg` | **ArchiMate capability map** — capability elements grouped into domain swimlanes & category groups; fill colour = target EKGF maturity level. |
| `capability_archimate.png` | Raster twin of the ArchiMate map. |
| `capability_taxonomy.mmd` | **Mermaid** flowchart of the taxonomy (domain → category → capability, annotated with EKGF level). |
| `capability_ontology.mmd` | **Mermaid** flowchart of the ontology relations (`dependsOn`/`supports`/`governedBy`). |
| `capability_ontology.ttl` | **RDF/OWL/SKOS** serialisation (OWL classes + SKOS taxonomy + EKGF level/pillar mappings). |
| `capability_ontology.png` | **networkx** visualisation: x-axis = EKGF maturity level, Business vs Technology bands, typed edges. |

## The model at a glance

* **Domains:** Business · Technology
* **Business categories:** Strategy & Governance · Stakeholder & Domain Engagement
  · Value & Performance · Capability & Talent
* **Technology categories:** Development & Authoring · Integration & Alignment
  · Reasoning & Inference · Quality/Validation/Verification · Ontology Operations
  · Access/Consumption/Visualization
* **EKGF levels:** L1 EKG Initiation → L2 Extensible Platform → L3 Enterprise Ready
  → L4 Strategic Asset → L5 Operational Ecosystem

## Usage

```bash
pip install -r ../requirements.txt          # networkx, matplotlib, rdflib, ...
python ontology_engineering_capabilities/build_artifacts.py
```

```python
import ontology_engineering_capabilities as oec

oec.validate_model()                 # [] == consistent
g = oec.build_ontology_graph()       # networkx MultiDiGraph
print(oec.to_turtle()[:500])         # RDF/OWL/SKOS
open("map.svg", "w").write(oec.to_archimate_svg())
oec.draw_ontology_networkx("onto.png")
```

The two Mermaid files render directly on GitHub, in VS Code, or at
<https://mermaid.live>. The SVG opens in any browser.

## Mapping to the EKGF maturity model

Every capability carries an `ekgf_pillar` (Business · Organization · Data ·
Technology) and a `maturity_level` (1–5). The ArchiMate map colours capabilities
by level, and `REQUIREMENTS.md` includes a **maturity roadmap** that lists the
capabilities expected at each EKGF level — usable directly as an assessment /
target-operating-model checklist.
