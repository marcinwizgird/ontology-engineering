"""
Generator for the FIBO visualization notebooks.

Creates:
    01_visualize_fibo_foundational.ipynb   -- load + visualise ONE ontology (no LPG)
    02_visualize_two_ontologies.ipynb       -- load + visualise TWO separate ontologies

Both reuse ontology_to_lpg.py (loader + converter) via nb_helpers.py and stop
before the FalkorDB load step.
"""
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent


def md(t): return nbf.v4.new_markdown_cell(t.strip("\n"))
def code(t): return nbf.v4.new_code_cell(t.strip("\n"))


def notebook(*cells):
    nb = nbf.v4.new_notebook()
    nb.cells = list(cells)
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    return nb


SETUP = """
%matplotlib inline
import nb_helpers as h        # local module; wires in ../ontology_to_lpg.py
import pandas as pd

FIBO = h.find_fibo_root()
print("FIBO clone:", FIBO)
"""


# ==========================================================================
# 01 - ONE ONTOLOGY (FIBO Foundational), no LPG
# ==========================================================================
nb01 = notebook(
    md("""
# 01 · Load & visualise a FIBO **Foundational** ontology — *without* the LPG load

This notebook reuses the ETL classes from **`ontology_to_lpg.py`**
(`RecursiveOntologyLoader` → `UniversalOntologyConverter`) to build the NetworkX
**meta-graph IR**, but deliberately **stops before `FalkorDBExporter`** — we only
*load* and *visualise* the schema; nothing is written to FalkorDB.

**Ontology:** `FND/Parties/Parties.rdf` — a core *Foundational* (FND) module
(Party, Party-in-Role, roles and relations) that most of FIBO builds on.

We load it with **`follow_imports=False`**, so we visualise this module's *own*
declared schema. Classes it references but does not define (e.g. imported
super-classes) appear as light-grey **`Resource`** stubs.
"""),
    code(SETUP),
    code("""
parties_file = FIBO / "FND" / "Parties" / "Parties.rdf"
ir = h.load_ontology_ir(parties_file, follow_imports=False)
print(f"IR: {ir.number_of_nodes()} nodes, {ir.number_of_edges()} edges")
"""),
    md("## Schema summary\n\nNode labels and edge types produced by the converter:"),
    code("""
summary = h.summarize_ir(ir)
display(summary["labels"])
display(summary["edges"])
"""),
    md("### The schema nodes (classes & properties defined here)"),
    code("""
summary["nodes"][summary["nodes"].label != "Resource"].reset_index(drop=True)
"""),
    md("""
## Visualise the meta-graph

Nodes are coloured by their LPG label (`OWLClass`, `ObjectProperty`, …) and edges
by relationship type (`SUBCLASS_OF`, `HAS_DOMAIN`, `HAS_RANGE`, `SUBPROPERTY_OF`).
"""),
    code("""
h.draw_meta_graph(ir, "FIBO FND · Parties — ontology meta-graph (schema only)",
                  color_by="label", figsize=(14, 10))
"""),
    md("""
## Notes

* **No LPG export.** We never instantiate `FalkorDBExporter`; this is purely a
  load-and-look workflow on the in-memory NetworkX IR.
* **No `DEFINED_IN` edges.** FIBO does not use `rdfs:isDefinedBy`, so the lineage
  edges the converter *can* produce are absent here; the `(:Ontology)` node
  therefore stands on its own. Module membership is instead evident from the
  namespace prefix of each QName (`fibo-fnd-pty-pty:` …).
* **`Resource` stubs** are classes/properties referenced but not defined in this
  file (they live in imported modules). To resolve them, load with
  `follow_imports=True` and a local catalog:

  ```python
  from ontology_to_lpg import build_local_catalog
  catalog = build_local_catalog(FIBO)   # slow: parses the whole clone once
  ir_full = h.load_ontology_ir(parties_file, follow_imports=True,
                               uri_to_location=catalog)
  ```
"""),
)


# ==========================================================================
# 02 - TWO SEPARATE ONTOLOGIES
# ==========================================================================
nb02 = notebook(
    md("""
# 02 · Load & visualise **two separate** FIBO ontologies

Same load→transform pipeline as notebook 01 (no LPG export), but here we load
**two** ontologies and visualise them both — individually and combined:

| # | Ontology | File | Role |
|---|----------|------|------|
| 1 | FIBO **Foundational** | `FND/Parties/Parties.rdf` | foundational parties/roles |
| 2 | FIBO **Persons & Accounts** | `FBC/ProductsAndServices/ClientsAndAccounts.rdf` | accounts and their holders (persons/organizations = clients) |

Each is loaded independently (`follow_imports=False`) into its own IR, then merged
with `compose_named`, which tags every node with its **source** ontology — and
marks any node shared by both as **`shared`** (the cross-references that bridge the
two otherwise-separate modules).
"""),
    code(SETUP),
    code("""
found_file = FIBO / "FND" / "Parties" / "Parties.rdf"
acct_file  = FIBO / "FBC" / "ProductsAndServices" / "ClientsAndAccounts.rdf"

ir_found = h.load_ontology_ir(found_file, follow_imports=False)
ir_acct  = h.load_ontology_ir(acct_file,  follow_imports=False)

print(f"Foundational (Parties):        {ir_found.number_of_nodes():3d} nodes, "
      f"{ir_found.number_of_edges():3d} edges")
print(f"Persons & Accounts (Clients…): {ir_acct.number_of_nodes():3d} nodes, "
      f"{ir_acct.number_of_edges():3d} edges")
"""),
    md("## Per-ontology label counts"),
    code("""
a = h.summarize_ir(ir_found)["labels"].rename(columns={"count": "Foundational"})
b = h.summarize_ir(ir_acct)["labels"].rename(columns={"count": "Persons&Accounts"})
a.merge(b, on="node_label", how="outer").fillna(0)
"""),
    md("## Ontology 1 — FIBO Foundational (Parties)"),
    code("""
h.draw_meta_graph(ir_found, "Ontology 1 · FND Parties (foundational)",
                  color_by="label", figsize=(13, 9))
"""),
    md("""
## Ontology 2 — FIBO Persons & Accounts (Clients & Accounts)

This module is large (51 classes), so we visualise its **class taxonomy** — the
`OWLClass` nodes and their `SUBCLASS_OF` edges — for readability.
"""),
    code("""
acct_taxonomy = h.filter_ir(ir_acct, keep_labels={"OWLClass"},
                            keep_edge_types={"SUBCLASS_OF"})
print(f"Class taxonomy: {acct_taxonomy.number_of_nodes()} classes, "
      f"{acct_taxonomy.number_of_edges()} subclass edges")
h.draw_meta_graph(acct_taxonomy, "Ontology 2 · Clients & Accounts — class taxonomy",
                  color_by="label", figsize=(16, 12), node_size=650, font_size=7)
"""),
    md("""
## Combined view — coloured by source ontology

Both ontologies in one graph. Blue = Foundational, orange = Persons & Accounts,
red = **shared** nodes (referenced by both). We drop each side's private
`Resource` import-stubs but keep the shared ones, so the bridge between the two
modules stays visible.
"""),
    code("""
combined = h.compose_named({
    "FND: Parties": ir_found,
    "FBC: ClientsAndAccounts": ir_acct,
})
from collections import Counter
print("nodes by source:", dict(Counter(d.get("source") for _, d in combined.nodes(data=True))))

# keep typed schema nodes + any shared node (drop private import stubs)
keep = [n for n, d in combined.nodes(data=True)
        if d.get("source") == "shared"
        or h.primary_label(d) in {"OWLClass", "ObjectProperty", "DatatypeProperty"}]
view = combined.subgraph(keep).copy()

src_colors = {"FND: Parties": "#4C78A8",
              "FBC: ClientsAndAccounts": "#F58518",
              "shared": "#E45756"}
h.draw_meta_graph(view, "Two separate FIBO ontologies — coloured by source",
                  color_by="source", source_colors=src_colors,
                  figsize=(16, 12), node_size=600, font_size=7)
"""),
    md("### Shared nodes — the cross-references bridging the two ontologies"),
    code("""
shared = [{"qname": d.get("qname"), "label": h.primary_label(d)}
          for n, d in combined.nodes(data=True) if d.get("source") == "shared"]
pd.DataFrame(shared)
"""),
    md("""
## Takeaways

* The pipeline loads **multiple ontologies** into independent IRs and merges them,
  attributing every schema element to its **source** ontology.
* Loaded on their own (imports not followed), *Parties* and *Clients & Accounts*
  form two largely **separate clusters** — they connect only through a few shared
  foundational references (see the table above). Following `owl:imports` with a
  local catalog would materialise the full dependency web between them.
* As in notebook 01, **nothing is written to FalkorDB** — this is load + visualise
  only. Running `FalkorDBExporter(combined)` would ingest exactly this merged graph.
"""),
)


if __name__ == "__main__":
    for name, nb in {
        "01_visualize_fibo_foundational.ipynb": nb01,
        "02_visualize_two_ontologies.ipynb": nb02,
    }.items():
        nbf.write(nb, HERE / name)
        print("[written]", HERE / name)
