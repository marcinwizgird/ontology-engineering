"""Generate ontology_enrichment_e2e.ipynb — the enrichment pipeline, interactive."""
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent


def md(t): return nbf.v4.new_markdown_cell(t.strip("\n"))
def code(t): return nbf.v4.new_code_cell(t.strip("\n"))


nb = nbf.v4.new_notebook()
nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python"}}

nb.cells = [
    md("""
# Enriching HBIM with FIBO — end to end

Interactive version of `src/run_enrichment.py`. We map the **HBIM business-assets
taxonomy** to **FIBO** with SKOS/RDF/annotations, reason, and turn the inferred
triples into concrete HBIM enrichment — the same graph is exported for **Protégé**
(see `PROTEGE.md`).
"""),
    code("""
%matplotlib inline
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent / "src"))
import pandas as pd
from rdflib import RDFS, OWL, URIRef
from rdflib.namespace import SKOS
from enricher import OntologyEnricher, q
from common import HBIM
import viz                     # networkx diagrams

e = OntologyEnricher()
e.lift_skos_to_owl(); e.build_bridge(); e.assemble(); e.reason()
print(f"{len(e.hbim_concepts())} HBIM concepts | asserted {len(e.asserted)} "
      f"-> inferred {len(e.inferred)} (+{len(e.new)})")
"""),
    md("""
## Diagrams · the inputs

Before the numbers, two pictures of what we start with.

### The original, fabricated HBIM taxonomy
A shallow SKOS tree of business assets — `skos:broader` shown as upward edges.
"""),
    code("""
viz.draw_graph(viz.hbim_taxonomy_graph(e),
               "Original HBIM business-assets taxonomy (SKOS)",
               figsize=(13, 8), node_size=2100, font_size=9)
"""),
    md("""
### The subset of FIBO we actually use
The real FIBO class hierarchy (`rdfs:subClassOf`, solid orange) plus the
`someValuesFrom` **restrictions** (dotted) that later become HBIM relationships.
"""),
    code("""
viz.draw_graph(viz.fibo_subset_graph(e),
               "Subset of FIBO utilised (classes + restrictions)",
               figsize=(15, 9), node_size=1700, font_size=8, edge_labels=True, x_gap=2.8)
"""),
    md("## Scenario 1 · Lift the SKOS taxonomy to OWL (`skos:broader` → `rdfs:subClassOf`)"),
    code("""
pd.DataFrame([
    {"concept": q(e.hbim, c),
     "skos:broader → rdfs:subClassOf": ", ".join(q(e.hbim, p) for p in e.hbim.objects(c, SKOS.broader))}
    for c in e.hbim_concepts()
])
"""),
    md("## Scenario 2 · Map HBIM → FIBO (SKOS) and bridge to OWL"),
    code("pd.DataFrame(e.bridge_log)"),
    md("""
## Scenario 3 · Subsumption enrichment

FIBO ancestry inferred for each HBIM concept — knowledge never asserted in the
glossary (e.g. a *Current Account* is a deposit account **and** a financial product).
"""),
    code("""
sub = e.enrich_subsumption()
pd.DataFrame([
    {"concept": k,
     "≡ exact": ", ".join(v["equivalentTo"]),
     "⊑ mapped": ", ".join(v["mapped_parent"]),
     "⊑ INFERRED (new)": ", ".join(v["inferred_ancestors"])}
    for k, v in sub.items()
])
"""),
    md("""
### Diagram · the outcome of mapping + inference

HBIM concepts (blue) are mapped to FIBO (orange) — `exactMatch` as solid green,
`close`/`broadMatch` as dashed green — and the reasoner then lifts each concept
into the FIBO hierarchy: every **red dashed** edge is an *inferred* `rdfs:subClassOf`
that did not exist in the glossary.
"""),
    code("""
viz.draw_graph(viz.mapping_inference_graph(e, sub),
               "HBIM ⟶ FIBO: mapping (green) + inferred ancestry (red)",
               figsize=(17, 11), node_size=1500, font_size=8, x_gap=3.0, y_gap=1.8)
"""),
    md("""
#### Focused view — how one concept gets enriched

The same story for `hbim:CurrentAccount` alone: its glossary parent (grey), the
FIBO class it maps to (green), the FIBO backbone (orange), and everything FIBO now
proves it to be (red dashed).
"""),
    code("""
viz.draw_graph(viz.concept_enrichment_graph(e, sub, "CurrentAccount"),
               "Enrichment of hbim:CurrentAccount (mapping + inference)",
               figsize=(12, 9), node_size=2000, font_size=9, x_gap=2.6)
"""),
    md("## Scenario 4 · Relationship enrichment (inherited FIBO restrictions)"),
    code("""
rows = []
for c in (HBIM.FinancialAccount, HBIM.CurrentAccount, HBIM.SavingsAccount):
    for r in e.enrich_relationships(c):
        rows.append({"concept": q(e.inferred, c), "property": r["property"],
                     "must relate to": f"some {r['value_type']}"})
pd.DataFrame(rows)
"""),
    md("## Scenario 5 · Annotation enrichment (copy real FIBO definitions)"),
    code("""
pd.DataFrame(e.enrich_annotations())
"""),
    md("## Scenario 6 · Instance classification (a real account reclassified via FIBO)"),
    code("""
inst = e.enrich_instances()
pd.DataFrame([
    {"individual": ind, "inferred FIBO type": t, "new": t in info["newly_inferred"]}
    for ind, info in inst.items() for t in info["inferred_fibo_types"]
])
"""),
    md("""
## Scenario 7 · Validation — FIBO disjointness catches an HBIM mapping error

We inject `hbim:CurrentAccount ⊑ caa:NonTransactionDepositAccount` (wrong — a
current account is *transactional*). FIBO declares the two disjoint, so the
reasoner rejects it.
"""),
    code("""
clashes = e.validate_with_disjointness()
pd.DataFrame(clashes) if clashes else "consistent"
"""),
    md("## Write the artifacts (enriched HBIM + Protégé-ready OWL)"),
    code("""
from common import HBIM_ENRICHED, PROTEGE_TTL, PROTEGE_RDF, INFERRED_TTL
enriched = e.build_enriched_hbim(sub, e.enrich_annotations())
enriched.serialize(destination=HBIM_ENRICHED, format="turtle")
e.asserted.serialize(destination=PROTEGE_TTL, format="turtle")
e.asserted.serialize(destination=PROTEGE_RDF, format="xml")
e.inferred.serialize(destination=INFERRED_TTL, format="turtle")
print("wrote enriched HBIM + Protégé bundle. See PROTEGE.md to reproduce in Protégé.")
"""),
    md("""
### The enriched `hbim:CurrentAccount` — before vs after

Below is the enriched concept: original SKOS + the mapping + **materialised FIBO
ancestry** (`rdfs:subClassOf` / `skos:broadMatch`) + a **definition copied from
FIBO** with a provenance note.
"""),
    code("""
ca = HBIM.CurrentAccount
pd.DataFrame([
    {"predicate": enriched.qname(p),
     "object": (enriched.qname(o) if isinstance(o, URIRef) else f'"{str(o)[:70]}"')}
    for p, o in sorted(enriched.predicate_objects(ca), key=lambda x: str(x[0]))
])
"""),
]

nbf.write(nb, HERE / "ontology_enrichment_e2e.ipynb")
print("[written]", HERE / "ontology_enrichment_e2e.ipynb")
