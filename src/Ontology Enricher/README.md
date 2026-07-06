# Ontology Enricher — enriching HBIM with FIBO

Worked, end-to-end examples of using **FIBO** to enrich an existing
ontology/taxonomy — here **HBIM**, a Collibra-style *Business Assets* taxonomy.
HBIM concepts are mapped to FIBO with **SKOS / RDF properties and annotations**;
a reasoner then propagates FIBO knowledge into HBIM, and the inferred triples are
written back as concrete enrichment. The whole thing runs in **Python** and is
**reproducible in Protégé**.

```
   HBIM taxonomy (SKOS)          FIBO excerpt (real IRIs + axioms)
        │                                   │
        │ 1. LIFT  skos:broader→subClassOf  │
        ▼                                   │
   HBIM as OWL classes                      │
        │ 2. BRIDGE  skos:exact/close/broadMatch → owl:equivalentClass / rdfs:subClassOf
        └──────────────┬────────────────────┘
                       ▼
         merged graph ──3. REASON (OWL RL / HermiT)──▶ inferred closure
                       │
                       ▼ 4. ENRICH
   subsumption · relationships · annotations · instance types · validation
                       │
                       ▼
        hbim_enriched.ttl   +   protege_reasoning_ready.rdf
```

## Run it (Python, end-to-end)

```bash
pip install -r requirements.txt
cd src
python run_enrichment.py
```

This prints all seven scenarios and writes the artifacts under `output/`.

For the visual walkthrough, open **`notebooks/ontology_enrichment_e2e.ipynb`** —
it runs the same pipeline and adds NetworkX diagrams of (1) the original HBIM
taxonomy, (2) the FIBO subset used, (3) the combined mapping + inferred ancestry,
and (4) a focused before/after for `hbim:CurrentAccount`.

## The five enrichment mechanisms (the "several examples")

| # | Scenario | FIBO enriches HBIM by… | Mechanism |
|---|----------|------------------------|-----------|
| 1 | **Taxonomy → ontology lift** | turning a flat SKOS taxonomy into a reasoned class hierarchy | `skos:broader` → `rdfs:subClassOf` |
| 2 | **Cross-standard mapping** | aligning HBIM to a published industry ontology | SKOS `exact`/`close`/`broad`/`narrow`/`relatedMatch` → OWL bridge |
| 3 | **Subsumption enrichment** | inferring missing ancestry (a *Current Account* **is a** deposit account, banking product, financial product) | `rdfs:subClassOf` transitivity + `owl:equivalentClass` |
| 4 | **Relationship enrichment** | supplying relationships the glossary never stated (an account **is held by** a holder, **is provided by** a depository institution) | inherited `someValuesFrom` restrictions |
| 5 | **Annotation enrichment** | filling in missing definitions with real FIBO text | copy `skos:definition` along the mapping |
| 6 | **Instance classification** | reclassifying real business data under FIBO types | `rdf:type` propagation |
| 7 | **Validation / quality** | catching a mis-mapping automatically | `owl:disjointWith` → inconsistency |

## Mapping mechanisms shown (RDF / SKOS / annotations)

`mappings/hbim_to_fibo_mappings.ttl` demonstrates all three requested forms:

* **SKOS mapping properties** — `skos:exactMatch`, `skos:closeMatch`,
  `skos:broadMatch`, `skos:relatedMatch` (the primary alignment).
* **RDF annotation** — `rdfs:seeAlso` pointing to the FIBO IRI.
* **Custom annotation** — `hbim:mappingConfidence` (governance metadata).

The **bridge** turns the reasoning-relevant SKOS mappings into OWL:

| SKOS mapping | Bridged OWL axiom |
|--------------|-------------------|
| `skos:exactMatch` | `owl:equivalentClass` |
| `skos:closeMatch` | `rdfs:subClassOf` (HBIM ⊑ FIBO) |
| `skos:broadMatch` | `rdfs:subClassOf` (FIBO is broader) |
| `skos:narrowMatch` | `rdfs:subClassOf` (FIBO is narrower) |
| `skos:relatedMatch` | *(none — annotation only)* |

## Reproduce in Protégé

See **[PROTEGE.md](PROTEGE.md)**. Open `output/protege_reasoning_ready.rdf`,
start HermiT/ELK, and the inferred class hierarchy, inherited restrictions,
instance types, and (after adding one axiom) the disjointness inconsistency all
match the Python output. The file is the *same merged graph* Python reasons over,
so results are identical — Python (`owlrl`) and Protégé (HermiT) stay in the
shared OWL 2 fragment.

## Files

```
Ontology Enricher/
├── README.md · PROTEGE.md · requirements.txt
├── data/       hbim_business_assets.ttl        # SOURCE: Collibra HBIM SKOS taxonomy
├── fibo/        fibo_enrichment_excerpt.ttl     # FIBO excerpt (real IRIs, axioms, definitions)
├── mappings/    hbim_to_fibo_mappings.ttl       # HBIM→FIBO (SKOS + RDF + annotations)
├── src/
│   ├── common.py                                # paths + namespaces
│   ├── enricher.py                              # engine: lift · bridge · reason · enrich
│   └── run_enrichment.py                        # E2E driver (prints + writes artifacts)
├── notebooks/   ontology_enrichment_e2e.ipynb   # same pipeline, interactive + NetworkX diagrams
│              viz.py                            # NetworkX diagram builders/drawing
└── output/                                      # generated
    ├── hbim_enriched.ttl                        # enriched HBIM (the deliverable)
    ├── protege_reasoning_ready.ttl / .rdf       # open in Protégé + reasoner
    ├── inferred_closure.ttl                     # full deductive closure
    └── enrichment_report.json                   # machine-readable report
```

> **HBIM** = a bank's *Harmonised Business Information Model*; the `hbim:`
> namespace and the excerpt are stand-ins — point the loader at a real Collibra
> export and the full FIBO to scale up. A self-contained FIBO excerpt (real IRIs)
> is used so reasoning runs in seconds and every inference is traceable.
