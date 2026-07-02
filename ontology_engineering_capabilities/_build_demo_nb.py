"""Generator for demo.ipynb (capability model walk-through)."""
from __future__ import annotations
import os
import nbformat as nbf
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

HERE = os.path.dirname(os.path.abspath(__file__))

BOOT = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath('..'))  # import the package\n"
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import ontology_engineering_capabilities as oec\n"
    "print('capabilities:', len(oec.CAPABILITIES), '| categories:', len(oec.CATEGORIES))\n"
    "print('model issues :', oec.validate_model() or 'none')"
)

cells = [
    new_markdown_cell(
        "# Ontology Repository — Capability Model demo\n\n"
        "Loads the capability model (business & technology capabilities, arranged as a "
        "taxonomy + ontology, mapped to the **EKGF EKG Maturity Model**) and exercises "
        "every generator: Mermaid, ArchiMate SVG, RDF/Turtle and the networkx ontology "
        "visualisation."
    ),
    new_code_cell(BOOT),
    new_markdown_cell("## 1 · Requirements table (a slice)"),
    new_code_cell(
        "import pandas as pd\n"
        "df = pd.DataFrame([{\n"
        "    'id': c.id, 'domain': c.domain, 'category': oec.CATEGORY_BY_ID[c.category].name,\n"
        "    'capability': c.name, 'pillar': c.ekgf_pillar, 'level': c.maturity_level,\n"
        "    'requirement': c.requirement,\n"
        "} for c in oec.CAPABILITIES])\n"
        "print('shape:', df.shape)\n"
        "df.head(12)"
    ),
    new_code_cell(
        "# capabilities per EKGF maturity level\n"
        "df.groupby('level').size().rename('count').to_frame()"
    ),
    new_markdown_cell("## 2 · Taxonomy graph (networkx)"),
    new_code_cell(
        "tax = oec.build_taxonomy_graph()\n"
        "import networkx as nx\n"
        "print('nodes:', tax.number_of_nodes(), 'edges:', tax.number_of_edges())\n"
        "print('is tree (DAG):', nx.is_directed_acyclic_graph(tax))"
    ),
    new_markdown_cell("## 3 · Mermaid diagrams\nSource renders on GitHub / mermaid.live / VS Code."),
    new_code_cell(
        "mmd = oec.to_mermaid_taxonomy()\n"
        "print(mmd[:700], '\\n...')"
    ),
    new_markdown_cell("## 4 · ArchiMate capability map (SVG + raster preview)"),
    new_code_cell(
        "svg = oec.to_archimate_svg()\n"
        "open('artifacts/_demo_map.svg', 'w', encoding='utf-8').write(svg)\n"
        "png = oec.draw_archimate_png('artifacts/_demo_map.png')\n"
        "print('SVG bytes:', len(svg), '| raster:', png)\n"
        "from IPython.display import Image, SVG, display\n"
        "display(Image(filename=png))"
    ),
    new_markdown_cell("## 5 · Capability ontology visualisation (networkx)"),
    new_code_cell(
        "from IPython.display import Image, display\n"
        "p = oec.draw_ontology_networkx('artifacts/_demo_onto.png')\n"
        "display(Image(filename=p))"
    ),
    new_markdown_cell("## 6 · RDF / OWL / SKOS export and SPARQL"),
    new_code_cell(
        "import rdflib\n"
        "g = rdflib.Graph(); g.parse(data=oec.to_turtle(), format='turtle')\n"
        "print('triples:', len(g))\n"
        "q = '''\n"
        "PREFIX oec: <https://example.org/oec#>\n"
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
        "PREFIX ekgf: <https://maturity.ekgf.org/def#>\n"
        "SELECT ?label ?lvl WHERE {\n"
        "  ?c a oec:TechnologyCapability ; skos:prefLabel ?label ;\n"
        "     oec:targetMaturityLevel ?L . ?L oec:levelNumber ?lvl .\n"
        "  FILTER(?lvl >= 4)\n"
        "} ORDER BY DESC(?lvl) ?label'''\n"
        "for row in g.query(q):\n"
        "    print(f'  L{row.lvl}  {row.label}')"
    ),
    new_markdown_cell(
        "## 7 · Regenerate every artifact\n"
        "`python ontology_engineering_capabilities/build_artifacts.py` writes the full set "
        "into `artifacts/` and the requirements doc to `../REQUIREMENTS.md`."
    ),
]

nb = new_notebook(cells=cells)
nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
path = os.path.join(HERE, "demo.ipynb")
nbf.write(nb, path)
print("wrote", path)
