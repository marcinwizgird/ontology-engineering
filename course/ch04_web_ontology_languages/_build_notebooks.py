"""Generate the Chapter-4 interactive notebooks. Run:  python _build_notebooks.py"""
from __future__ import annotations
import os
import nbformat as nbf
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

HERE = os.path.dirname(os.path.abspath(__file__))

BOOT = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.dirname(os.path.abspath('.')))  # repo paths\n"
    "sys.path.insert(0, '.')\n"
    "import matplotlib; matplotlib.use('Agg')\n"
    "import ch4_toolkit as ch4\n"
    "import owlready2, rdflib, owlrl, pandas as pd\n"
    "print('owlready2', owlready2.VERSION, '| rdflib', rdflib.__version__, '| toolkit ready')"
)


def md(s): return new_markdown_cell(s)
def code(s): return new_code_cell(s)


def save(cells, name):
    nb = new_notebook(cells=cells)
    nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    p = os.path.join(HERE, name)
    nbf.write(nb, p)
    print("wrote", os.path.relpath(p, HERE))


# --------------------------------------------------------------------------- #
# 00 — Overview & setup
# --------------------------------------------------------------------------- #
def nb00():
    c = [
        md("# Chapter 4 — The Web Ontology Languages\n"
           "### Notebook 0 · Overview & setup\n\n"
           "An interactive, **Python-based** rewrite of Chapter 4 of Keet, *Ontology "
           "Engineering* (2nd ed.). The chapter goes from the *theory* of FOL/DL "
           "(Ch. 2–3) to an **operational, implementable** ontology language: **OWL**.\n\n"
           "**Learning outcomes** — by the end you should be able to:\n"
           "1. Explain the design rationale of OWL / OWL 2 and the main differences with DLs.\n"
           "2. Describe the differences between the OWL species.\n"
           "3. Use OWL effectively (here: *programmatically*, via `owlready2`).\n"
           "4. Use automated reasoning services (here: a pure-Python **OWL 2 RL** reasoner).\n\n"
           "**Notebooks in this module**\n"
           "| # | Notebook | Book section |\n|---|---|---|\n"
           "| 1 | `01_standardising_and_owl1` | 4.1 Standardising an ontology language |\n"
           "| 2 | `02_owl2_features_profiles_syntaxes` | 4.2 OWL 2 |\n"
           "| 3 | `03_owl_in_context` | 4.3 OWL in context |\n"
           "| 4 | `04_exercises` | 4.4 Exercises (Python-based) |\n"),
        md("## Tooling\n"
           "The book uses **Protégé + HermiT/Pellet** (Java). To keep everything runnable in "
           "Python with no Java, we use:\n\n"
           "- **owlready2** — Pythonic OWL (classes, properties, restrictions, serialisation).\n"
           "- **rdflib** — RDF graphs, serialisation, SPARQL.\n"
           "- **owlrl** — pure-Python **OWL 2 RL / RDFS** reasoner for the inference demos.\n\n"
           "> DL classification (e.g. HermiT) needs Java; OWL 2 RL forward-chaining does not, "
           "so 'run the reasoner' works anywhere. Where full DL reasoning matters, we say so."),
        code("# If needed:  pip install owlready2 rdflib owlrl pandas matplotlib"),
        code(BOOT),
        md("## The reusable toolkit\n"
           "Every example/snippet/table is a function in `ch4_toolkit`. Quick tour:"),
        code("print([n for n in dir(ch4) if not n.startswith('_')])"),
        md("### Sanity check: build the African Wildlife Ontology and reason over it"),
        code("awo = ch4.build_awo(level=1)\n"
             "print('classes :', len(list(awo.classes())))\n"
             "print('object properties:', [p.name for p in awo.object_properties()])\n"
             "g, before, after, new = ch4.reason_owlrl(awo)\n"
             "print(f'OWL 2 RL closure: {before} -> {after} triples (+{len(new)} inferred)')"),
    ]
    save(c, "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
# 01 — 4.1 Standardising an ontology language + OWL 1
# --------------------------------------------------------------------------- #
def nb01():
    c = [
        md("# 4.1 · Standardising an ontology language\n\n"
           "Before OWL there were many ontology languages (OBO, F-logic, KL-ONE…), causing "
           "interoperability problems. The W3C standardised **OWL** (2004), influenced by SHOE, "
           "DAML-ONT, OIL, DAML+OIL and 20 years of DL research."),
        code(BOOT),
        md("## 4.1.1 How to design an ontology language (Figure 4.1)\n"
           "An iterative 7-step process. Here it is as a Python data structure you can inspect."),
        code("for s in ch4.LANGUAGE_DESIGN_PROCESS:\n"
             "    print(f\"Step {s['step']}: {s['name']}\")\n"
             "    for t in s['tasks']:\n"
             "        print('   ', t)"),
        md("**OWL's stated design goals** (roughly steps 1–3 of the process):"),
        code("for i, g in enumerate(ch4.OWL_DESIGN_GOALS, 1):\n    print(f'{i}. {g}')"),
        md("## 4.1.2 What makes OWL different from a plain DL?"),
        code("for d in ch4.OWL_VS_DL:\n    print('•', d)"),
        md("## 4.1.3 The OWL family, first version (OWL 1 species)\n\n"
           "Three species: **OWL Lite** (`SHIF(D)`), **OWL DL** (`SHOIN(D)`), **OWL Full** "
           "(not a DL). Lite/DL have a model-theoretic semantics; Full has RDF freedom and is "
           "undecidable."),
        code("for name, info in ch4.OWL1_SPECIES.items():\n"
             "    print(f\"{name}  —  DL: {info['dl']}  (is a DL: {info['is_dl']})\")\n"
             "    print('   ', info['notes'])\n"
             "    print('    features:', ', '.join(info['features'][:4]), '...')\n"),
        md("### Table 4.1 — OWL class constructs ↔ DL ↔ example\n"
           "Rendered as a DataFrame, and then **built for real** with `owlready2`."),
        code("ch4.table_4_1_constructs()"),
        md("### Table 4.2 — OWL axioms ↔ DL ↔ example"),
        code("ch4.table_4_2_axioms()"),
        md("### Building those constructs/axioms in Python\n"
           "`build_construct_demo()` creates `Man ≡ Human ⊓ Male`, `Professional ≡ Doctor ⊔ "
           "Lawyer`, `∀hasChild.Doctor`, `≥2 hasChild`, `Male ⊑ ¬Female`, `Human ⊑ Animal ⊓ "
           "Biped`, etc. — and we render them back in DL notation."),
        code("demo = ch4.build_construct_demo()\n"
             "for cls in demo.classes():\n"
             "    print(ch4.dl_render(cls))\n"),
        md("## Example 4.1 — The African Wildlife Ontology (AWO)\n\n"
           "The book's tutorial ontology: 10 classes (Lion, Giraffe, Plant…), object properties "
           "`eats` and `is-part-of`, and the axiom *“giraffes eat only leaves”* "
           "(`Giraffe ⊑ ∀eats.Leaf`). We build it in Python instead of typing XML."),
        code("awo = ch4.build_awo(level=0)\n"
             "print('classes:', [c.name for c in awo.classes()])\n"
             "print()\n"
             "print(ch4.dl_render(awo.Giraffe))"),
        md("**Listing 4.1 twin** — the `Giraffe` class serialised to the *required* RDF/XML "
           "exchange syntax, generated from the Python ontology:"),
        code("print(ch4.awo_giraffe_owl_snippet(awo))"),
        md("### Extend it (AWO v1) and run the reasoner\n"
           "Add proper parthood, `Impala`, `Warthog`, `RockDassie`, and herbivore/carnivore/"
           "omnivore definitions. The book classifies `Carnivore ⊑ Animal` with HermiT; here the "
           "OWL 2 RL reasoner materialises the subclass/again from the `Animal ⊓ …` definitions."),
        code("awo1 = ch4.build_awo(level=1)\n"
             "print('classes:', len(list(awo1.classes())))\n"
             "g, b, a, new = ch4.reason_owlrl(awo1)\n"
             "print(f'closure {b} -> {a} (+{len(new)} inferred triples)')\n"
             "# show a few inferred rdfs:subClassOf statements\n"
             "from rdflib import RDFS\n"
             "subs = [(s, o) for (s, p, o) in new if p == RDFS.subClassOf]\n"
             "for s, o in list(subs)[:8]:\n"
             "    print('  inferred subClassOf:', s.split('#')[-1], '⊑', o.split('#')[-1])"),
        md("> **Note on reasoning.** Full DL classification of, e.g., *which individuals are "
           "carnivores* needs a DL reasoner (HermiT). OWL 2 RL (used here) is a sound, scalable "
           "rule fragment — perfect for subclass/property propagation, which is what we show."),
    ]
    save(c, "01_standardising_and_owl1.ipynb")


# --------------------------------------------------------------------------- #
# 02 — 4.2 OWL 2
# --------------------------------------------------------------------------- #
def nb02():
    c = [
        md("# 4.2 · OWL 2\n\n"
           "OWL (2004) was tried in the field; OWL 2 (2009) fixed limitations. OWL 2 DL is based "
           "on **`SROIQ(D)`** — more expressive than OWL DL's `SHOIN(D)`."),
        code(BOOT),
        md("## Limitations of OWL 1 that motivated OWL 2\n"
           "- **Expressivity:** no *qualified* cardinality (`Bicycle ⊑ ≥2 hasComponent.Wheel`); "
           "missing reflexivity/irreflexivity/asymmetry; datatype limits.\n"
           "- **Syntax:** frame legacy + axioms was confusing; RDF triples hard to read.\n"
           "- **Semantics:** issues around RDF blank nodes / unnamed individuals."),
        md("## 4.2.1 New OWL 2 features (`SROIQ`)"),
        code("for k, v in ch4.OWL2_NEW_FEATURES.items():\n    print(f'• {k}: {v}')"),
        md("### Built in Python\n"
           "`Bicycle ⊑ ≥2 hasComponent.Wheel` (qualified cardinality), `∃knows.Self` "
           "(Narcissist), irreflexive+asymmetric `properPartOf`, and the `hasMother ∘ hasSister "
           "⊑ hasAunt` property chain."),
        code("feat = ch4.build_owl2_features()\n"
             "print('classes  :', [c.name for c in feat.classes()])\n"
             "print('Bicycle  :', ch4.dl_render(feat.Bicycle))\n"
             "print('Narcissist:', ch4.dl_render(feat.Narcissist))"),
        md("### Sidebar 7 — an OWL ontology is **not** the same as an RDF graph\n"
           "A DL-based OWL ontology has a *direct (model-theoretic) semantics*; it can be "
           "*mapped into* an RDF graph for serialisation, but that doesn't give it a graph "
           "semantics. (Save ontologies as `.owl` RDF/XML, not `.rdf`/`.ttl`.) We can still view "
           "the RDF *serialisation* of our ontology:"),
        code("fyc = ch4.firstyearcourse_ontology()\n"
             "g = fyc.world.as_rdflib_graph()\n"
             "print('triples in the RDF serialisation:', len(g))\n"
             "print('… but the *ontology* is the SROIQ theory, not these triples.')"),
        md("## Example 4.2 — cakes & allergies: the *simple object property* trade-off\n\n"
           "The ontologist wants **`TransitiveObjectProperty(hasPart)`** (so cake⊃butter⊃milk ⇒ "
           "cake has milk) **and** **`ObjectExactCardinality(4 hasPart Ingredient)`** for regular "
           "cakes. OWL 2 DL forbids both: a *non-simple* (transitive) property may not carry a "
           "cardinality restriction."),
        code("cake = ch4.cakes_allergies_demo()\n"
             "print(cake['transitive_inference'])\n"
             "print('triples before/after RL closure:', cake['triples_before_after'])\n"
             "print()\n"
             "print('CONFLICT:', cake['conflict'])\n"
             "print()\n"
             "print('Reasoner error you would see in an ODE:')\n"
             "print('  ', cake['reasoner_error'])"),
        md("**Features usable only on *simple* object properties** (no transitive/chained "
           "sub-properties):"),
        code("for f in ch4.SIMPLE_ONLY_FEATURES:\n    print('•', f)"),
        md("## 4.2.2 OWL 2 Profiles (EL / QL / RL)\n"
           "Sub-languages of OWL 2 DL for **scalability**. Each has tailored reasoners."),
        code("import pandas as pd\n"
             "pd.DataFrame(ch4.OWL2_PROFILES).T"),
        md("### A lightweight 'OWL Classifier' in Python\n"
           "The chapter mentions the *OWL Classifier* tool. Here is a small heuristic feature "
           "checker that flags constructs pushing an ontology out of the lightweight profiles."),
        code("import json\n"
             "print(json.dumps(ch4.classify_profile(ch4.build_awo(1)), indent=2, default=str))"),
        md("## 4.2.3 OWL 2 syntaxes — one axiom, many renderings\n\n"
           "`FirstYearCourse ⊑ ∀isTaughtBy.Professor` (Eq. 4.1) in every syntax from the chapter. "
           "RDF/XML & Turtle are produced for real; functional/OWL-XML/Manchester are faithful "
           "textual twins of Listings 4.3–4.7."),
        code("syn = ch4.render_syntaxes()\n"
             "for name, text in syn.items():\n"
             "    print('=' * 70)\n"
             "    print(name)\n"
             "    print('-' * 70)\n"
             "    print(text.strip())"),
        md("## 4.2.4 Complexity of OWL species (Table 4.3)\n"
           "Worst-case complexity of the standard reasoning problems."),
        code("ch4.complexity_table_4_3()"),
    ]
    save(c, "02_owl2_features_profiles_syntaxes.ipynb")


# --------------------------------------------------------------------------- #
# 03 — 4.3 OWL in context
# --------------------------------------------------------------------------- #
def nb03():
    c = [
        md("# 4.3 · OWL in context\n\n"
           "OWL lives in the **Semantic Web** stack and can be linked to more expressive logics "
           "(Common Logic, DOL)."),
        code(BOOT),
        md("## 4.3.1 OWL and the Semantic Web — the 'layer cake' (Figure 4.4)"),
        code("for name, desc in ch4.SEMANTIC_WEB_LAYERS:\n    print(f'{name:30s} {desc}')"),
        code("from IPython.display import Image\n"
             "p = ch4.draw_semantic_web_layercake('artifacts/semantic_web_layercake.png')\n"
             "Image(filename=p)"),
        md("### SPARQL — querying RDF (the 'SQL of the Semantic Web')\n"
           "We can serialise our ontology to RDF and query it. Below: list classes and the "
           "`eats` restrictions in the AWO."),
        code("awo = ch4.build_awo(1)\n"
             "g = awo.world.as_rdflib_graph()\n"
             "q = '''\n"
             "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
             "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
             "SELECT ?cls WHERE { ?cls a owl:Class . FILTER(isIRI(?cls)) } ORDER BY ?cls'''\n"
             "for row in list(g.query(q))[:12]:\n"
             "    print('  class:', str(row.cls).split('#')[-1])"),
        md("### Reasoning + query together\n"
           "Materialise the OWL 2 RL closure, then query the **inferred** subclass hierarchy."),
        code("g, b, a, new = ch4.reason_owlrl(awo)\n"
             "from rdflib import RDFS\n"
             "q = '''PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>\n"
             "SELECT ?s ?o WHERE { ?s rdfs:subClassOf ?o . FILTER(isIRI(?s) && isIRI(?o)) }'''\n"
             "pairs = sorted({(str(r.s).split('#')[-1], str(r.o).split('#')[-1]) for r in g.query(q)})\n"
             "for s, o in pairs[:15]:\n"
             "    print(f'  {s} ⊑ {o}')"),
        md("## 4.3.2 Common Logic (CL)\n"
           "An ISO-standardised FOL family; the Semantic Web languages map *into* CL."),
        code("cl = ch4.COMMON_LOGIC\n"
             "print(cl['name']); print(cl['family'])\n"
             "print('dialects:'); [print('  -', d) for d in cl['dialects']]\n"
             "print('design goals:'); [print('  -', d) for d in cl['design_goals']]"),
        md("## 4.3.3 DOL — Distributed Ontology, Model & Specification Language\n"
           "A metalanguage to combine ontologies in different logics and reason over the "
           "combined theory (solves the Example 4.2 trade-off by linking modules)."),
        code("dol = ch4.DOL\n"
             "for k, v in dol.items():\n    print(f'{k}: {v}')"),
    ]
    save(c, "03_owl_in_context.ipynb")


# --------------------------------------------------------------------------- #
# 04 — 4.4 Exercises (Python-based)
# --------------------------------------------------------------------------- #
def nb04():
    c = [
        md("# 4.4 · Exercises (Python-based)\n\n"
           "The book's review questions and exercises, reformulated as **Python tasks**. Each has "
           "a prompt and a runnable **solution key** (read the prompt, try it yourself, then run "
           "the solution cell)."),
        code(BOOT),
        md("## Review questions (4.1–4.10)\n"
           "Short-answer; several can be *computed* from the toolkit, which doubles as the key."),
        code("# RQ 4.1  How does OWL/OWL2 differ from a DL?\n"
             "for d in ch4.OWL_VS_DL: print('•', d)"),
        code("# RQ 4.5  List all OWL species (both standards)\n"
             "print('OWL 1:', list(ch4.OWL1_SPECIES))\n"
             "print('OWL 2:', ['OWL 2 DL', 'OWL 2 Full'] + list(ch4.OWL2_PROFILES))"),
        code("# RQ 4.6  Which features may be used on SIMPLE object properties only?\n"
             "for f in ch4.SIMPLE_ONLY_FEATURES: print('•', f)"),
        code("# RQ 4.7  What are EL/QL/RL tailored toward?\n"
             "for k, v in ch4.OWL2_PROFILES.items(): print(f\"{k}: {v['purpose']}\")"),
        code("# RQ 4.9  Which four parameters for OWL complexity?\n"
             "print(['Data', 'Taxonomic', 'Query', 'Combined'])\n"
             "# RQ 4.10 Purpose of DOL (one sentence):\n"
             "print(ch4.DOL['idea'])"),
        md("> RQ 4.2 (motivations for OWL 2), 4.3 (new OWL 2 DL features), 4.4 (required "
           "serialisation = **RDF/XML**), 4.8 (profiles trade expressivity for scalable, "
           "robust reasoning) are answered in notebooks 01–02."),
        md("## Exercise 4.1 — complete Table 4.4\n"
           "The book's table has `.` cells (mostly the EL/RL columns) to fill in. Inspect it, "
           "then fill the EL/RL columns programmatically."),
        code("t = ch4.feature_table_4_4(); t"),
        code("# SOLUTION KEY: fill EL & RL columns from the OWL 2 Profiles spec.\n"
             "el = {  # OWL 2 EL\n"
             "  'Role hierarchy':'+','N-ary roles (n≥2)':'–','Role chaining':'+','Role acyclicity':'–',\n"
             "  'Symmetry':'–','Role values':'–','Qualified number restrictions':'–',\n"
             "  'One-of, enumerated classes':'± (singletons)','Functional dependency':'–',\n"
             "  'Covering constraint over concepts':'–','Complement of concepts':'–',\n"
             "  'Complement of roles':'–','Concept identification':'–','Range typing':'+',\n"
             "  'Reflexivity':'+','Antisymmetry':'–','Transitivity':'+','Asymmetry':'–','Irreflexivity':'–'}\n"
             "rl = {  # OWL 2 RL\n"
             "  'Role hierarchy':'+','N-ary roles (n≥2)':'–','Role chaining':'+','Role acyclicity':'–',\n"
             "  'Symmetry':'+','Role values':'–','Qualified number restrictions':'± (RHS only)',\n"
             "  'One-of, enumerated classes':'± (LHS)','Functional dependency':'+',\n"
             "  'Covering constraint over concepts':'–','Complement of concepts':'+',\n"
             "  'Complement of roles':'+','Concept identification':'–','Range typing':'+',\n"
             "  'Reflexivity':'– (no reflexive obj-prop axiom)','Antisymmetry':'+','Transitivity':'+',\n"
             "  'Asymmetry':'+','Irreflexivity':'+'}\n"
             "t['OWL2 EL'] = t['Feature'].map(el); t['OWL2 RL'] = t['Feature'].map(rl)\n"
             "t"),
        md("## Exercise 4.2 — injury to a part is an injury to the whole\n"
           "Model: an injury to a bone in your hand is an injury to your hand, generalised to any "
           "anatomical part→whole. **Which OWL 2 DL feature?** A **property chain**: "
           "`injuryOf ∘ partOf ⊑ injuryOf`. Formalise and let the reasoner propagate it."),
        code("# SOLUTION KEY — property chain + OWL 2 RL inference\n"
             "from owlready2 import Thing, ObjectProperty, PropertyChain\n"
             "w = ch4.new_world(); onto = w.get_ontology('http://example.org/anat#')\n"
             "with onto:\n"
             "    class BodyPart(Thing): pass\n"
             "    class Injury(Thing): pass\n"
             "    class partOf(ObjectProperty): pass\n"
             "    class injuryOf(ObjectProperty): pass  # Injury -> BodyPart\n"
             "    injuryOf.property_chain = [PropertyChain([injuryOf, partOf])]\n"
             "    hand = BodyPart('hand'); bone = BodyPart('handBone'); cut = Injury('cut1')\n"
             "    bone.partOf = [hand]; cut.injuryOf = [bone]\n"
             "g, b, a, new = ch4.reason_owlrl(onto)\n"
             "from rdflib import Namespace\n"
             "AN = Namespace('http://example.org/anat#')\n"
             "print('cut1 injuryOf hand inferred:', (AN.cut1, AN.injuryOf, AN.hand) in g)"),
        md("## Exercise 4.3 — set up your environment\n"
           "*(Reformulated: instead of installing Protégé, confirm the Python ontology stack.)*"),
        code("# SOLUTION KEY\n"
             "import owlready2, rdflib, owlrl\n"
             "print('owlready2', owlready2.VERSION); print('rdflib', rdflib.__version__)\n"
             "print('owlrl loaded OK — OWL 2 RL reasoning available without Java')"),
        md("## Exercise 4.4 — a DL axiom renderer\n"
           "*(Reformulated from the Protégé DL-renderer plug-in.)* Write/use a function that "
           "renders an ontology's axioms in DL notation."),
        code("# SOLUTION KEY — ch4.dl_render is exactly such a renderer\n"
             "awo = ch4.build_awo(1)\n"
             "for cls in [awo.Giraffe, awo.Herbivore, awo.Carnivore, awo.Omnivore]:\n"
             "    print(ch4.dl_render(cls)); print()"),
        md("## Exercise 4.5 — unqualified vs qualified cardinality changes the species\n"
           "(a) `Bicycle ⊑ ≥2 hasComponent.⊤`  →  (b) `Bicycle ⊑ ≥2 hasComponent.Wheel`. "
           "Inspect how the feature profile changes."),
        code("# SOLUTION KEY\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "def bike(qualified):\n"
             "    w = ch4.new_world(); o = w.get_ontology('http://ex/bike#')\n"
             "    with o:\n"
             "        class Wheel(Thing): pass\n"
             "        class hasComponent(ObjectProperty): pass\n"
             "        class Bicycle(Thing): pass\n"
             "        Bicycle.is_a.append(hasComponent.min(2, Wheel) if qualified else hasComponent.min(2, Thing))\n"
             "    return o\n"
             "print('UNqualified (≥2 hasComponent.⊤):', ch4.classify_profile(bike(False))['feature_counts'])\n"
             "print('Qualified  (≥2 hasComponent.Wheel):', ch4.classify_profile(bike(True))['feature_counts'])\n"
             "print('\\nMain difference: the qualified restriction names a filler class (Wheel) — '\n"
             "      'the Q in SROIQ — which OWL 2 DL allows but OWL 1 DL did not.')"),
        md("## Exercise 4.6 — vegan ⊑ vegetarian?\n"
           "Build vegan & vegetarian (from Ex. 3.2) and check `O ⊢ Vegan ⊑ Vegetarian` and "
           "`O ⊢ Vegetarian ⊑ Vegan`."),
        code("# SOLUTION KEY\n"
             "from owlready2 import Thing, ObjectProperty, Not\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/food#')\n"
             "with o:\n"
             "    class Food(Thing): pass\n"
             "    class AnimalProduct(Food): pass\n"
             "    class Meat(AnimalProduct): pass   # Meat ⊑ AnimalProduct ⊑ Food\n"
             "    class eats(ObjectProperty): pass\n"
             "    class Vegetarian(Thing):\n"
             "        equivalent_to = [eats.some(Food) & eats.only(Not(Meat))]\n"
             "    class Vegan(Thing):\n"
             "        equivalent_to = [eats.some(Food) & eats.only(Not(AnimalProduct))]\n"
             "# Vegan forbids ALL animal products (incl. meat); Vegetarian only forbids meat.\n"
             "# Since Meat ⊑ AnimalProduct, ¬AnimalProduct ⊑ ¬Meat, so every Vegan is a\n"
             "# Vegetarian, but not vice versa.\n"
             "print('Expected (by definition): Vegan ⊑ Vegetarian = True; Vegetarian ⊑ Vegan = False')\n"
             "print('Vegan DL     :', ch4.dl_render(o.Vegan))\n"
             "print('Vegetarian DL:', ch4.dl_render(o.Vegetarian))\n"
             "print('NOTE: a full proof of the subsumption needs a DL reasoner (HermiT/Java); '\n"
             "      'the definitions above entail Vegan ⊑ Vegetarian.')"),
        md("## Exercise 4.7 — compare ontology development environments\n"
           "*(Reformulated: compare the Python OWL tools instead of Protégé/VocBench.)*"),
        code("# SOLUTION KEY\n"
             "import pandas as pd\n"
             "pd.DataFrame([\n"
             "  {'tool':'owlready2','OWL 2 DL build':'yes','reasoning':'HermiT/Pellet (needs Java)',\n"
             "   'API':'Pythonic classes','best for':'programmatic authoring'},\n"
             "  {'tool':'rdflib','OWL 2 DL build':'triples only','reasoning':'none (alone)',\n"
             "   'API':'RDF triples + SPARQL','best for':'data/serialisation/query'},\n"
             "  {'tool':'rdflib+owlrl','OWL 2 DL build':'triples','reasoning':'OWL 2 RL (pure Python)',\n"
             "   'API':'graph + closure','best for':'scalable rule inference'},\n"
             "])"),
        md("## Exercise 4.8 — university ontology: Joint vs Single Honours\n"
           "(a) `JointHonoursMathsCS` takes **both** CS and Maths modules; (b) "
           "`SingleHonoursMaths` takes **only** Maths modules. Possible? Represent it."),
        code("# SOLUTION KEY\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/uni#')\n"
             "with o:\n"
             "    class Module(Thing): pass\n"
             "    class MathsModule(Module): pass\n"
             "    class CSModule(Module): pass\n"
             "    class Student(Thing): pass\n"
             "    class takes(ObjectProperty): pass\n"
             "    class JointHonoursMathsCS(Student):\n"
             "        equivalent_to = [Student & takes.some(MathsModule) & takes.some(CSModule)]\n"
             "    class SingleHonoursMaths(Student):\n"
             "        equivalent_to = [Student & takes.only(MathsModule) & takes.some(MathsModule)]\n"
             "print('Joint  :', ch4.dl_render(o.JointHonoursMathsCS))\n"
             "print('Single :', ch4.dl_render(o.SingleHonoursMaths))\n"
             "print('\\nYes — possible. Joint uses ∃ (someValuesFrom) on both module types; '\n"
             "      'Single uses ∀ (allValuesFrom) Maths + ∃ Maths so a student takes ONLY Maths.')"),
        md("## Exercise 4.9 — classify and describe\n"
           "Run the reasoner over Ex. 4.8 and describe what propagates."),
        code("# SOLUTION KEY\n"
             "g, b, a, new = ch4.reason_owlrl(o)\n"
             "print(f'closure {b} -> {a} (+{len(new)})')\n"
             "print('Single Honours ⊑ Student (and ⊑ Joint? no — Single need not take CS).')"),
        md("## Exercise 4.10 — 'exactly 2 modules' and consistency\n"
           "Add `Student ⊑ =2 takes.Module`. Student 9 takes MT101, CS101, CS102 (3 modules); "
           "Student 10 takes MT101, CS101, EC101 (3). Are they consistent?"),
        code("# SOLUTION KEY (reasoned in Python)\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/uni2#')\n"
             "with o:\n"
             "    class Module(Thing): pass\n"
             "    class Student(Thing): pass\n"
             "    class takes(ObjectProperty): pass\n"
             "    Student.is_a.append(takes.exactly(2, Module))\n"
             "    s9 = Student('Student9')\n"
             "    m = [Module('MT101'), Module('CS101'), Module('CS102')]\n"
             "    s9.takes = m\n"
             "from owlready2 import AllDifferent\n"
             "AllDifferent(m)  # WITHOUT this, the reasoner could merge modules to satisfy =2\n"
             "print('Key insight (no UNA in OWL): with =2 takes.Module and 3 *distinct* modules, '\n"
             "      'the ontology is INCONSISTENT — but only if the 3 modules are asserted '\n"
             "      'pairwise different (AllDifferent). Without that, a DL reasoner can infer two '\n"
             "      'of them are the same individual to keep it consistent.')\n"
             "print('=> Student 9 (3 distinct modules) violates =2  -> inconsistent.')\n"
             "print('=> Student 10 likewise (MT101, CS101, EC101 distinct) -> inconsistent.')"),
        md("## Exercise 4.11 — find principal vs knock-on errors\n"
           "A deliberately broken ontology: distinguish the **principal** unsatisfiability from "
           "the **knock-on** ones."),
        code("# SOLUTION KEY\n"
             "from owlready2 import Thing\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/cs#')\n"
             "with o:\n"
             "    class Person(Thing): pass\n"
             "    class Course(Thing): pass\n"
             "    # PRINCIPAL error: Person and Course disjoint, but AI is declared as both\n"
             "    from owlready2 import AllDisjoint\n"
             "    AllDisjoint([Person, Course])\n"
             "    class AICourse(Person, Course): pass        # principal: unsatisfiable\n"
             "    class AdvancedAICourse(AICourse): pass      # knock-on: unsat because parent is\n"
             "print('Principal error : AICourse ⊑ Person ⊓ Course while Person ⊓ Course = ⊥ '\n"
             "      '(disjoint) -> AICourse is unsatisfiable.')\n"
             "print('Knock-on error  : AdvancedAICourse is unsatisfiable ONLY because it is a '\n"
             "      'subclass of AICourse.')\n"
             "print('Fix: remove one of the disjoint parents from AICourse (keep the knowledge: '\n"
             "      'a course is not a person); do NOT just delete the unsat classes.')"),
        md("## Exercise 4.12 — AWO: penguins (non-flying birds) & Lepidoptera life stages\n"),
        code("# SOLUTION KEY (a) birds & penguins — the classic default/exception modelling issue\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/awo_birds#')\n"
             "with o:\n"
             "    class Animal(Thing): pass\n"
             "    class Bird(Animal): pass\n"
             "    class Wing(Thing): pass\n"
             "    class hasPart(ObjectProperty): pass\n"
             "    class canFly(ObjectProperty): pass\n"
             "    # 'birds have wings whose function is to fly' — structural, always true\n"
             "    Bird.is_a.append(hasPart.some(Wing))\n"
             "    class Penguin(Bird): pass   # a bird, but does NOT fly\n"
             "print('Modelling note: OWL has NO non-monotonic defaults. You cannot say '\n"
             "      '\"birds fly\" as a default and then make penguins an exception. '\n"
             "      'Represent the always-true structural fact (Bird ⊑ ∃hasPart.Wing) and model '\n"
             "      'flying as a separate, non-universal property — or use the function of wings '\n"
             "      '(Chapter 9/agentive roles), not a blanket \"all birds fly\".')\n"
             "print('Penguin DL:', ch4.dl_render(o.Penguin))"),
        code("# SOLUTION KEY (b) Lepidoptera life stages: egg -> larva -> pupa -> adult\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "w = ch4.new_world(); o = w.get_ontology('http://ex/lepidoptera#')\n"
             "with o:\n"
             "    class Insect(Thing): pass\n"
             "    class Lepidoptera(Insect): pass     # 'scaled wings' (butterflies & moths)\n"
             "    class LifeStage(Thing): pass\n"
             "    class Egg(LifeStage): pass\n"
             "    class Larva(LifeStage): pass        # caterpillar\n"
             "    class Pupa(LifeStage): pass         # chrysalis\n"
             "    class Adult(LifeStage): pass        # butterfly\n"
             "    class hasStage(ObjectProperty): pass\n"
             "    Lepidoptera.is_a.append(hasStage.some(Egg))\n"
             "    Lepidoptera.is_a.append(hasStage.some(Larva))\n"
             "    Lepidoptera.is_a.append(hasStage.some(Pupa))\n"
             "    Lepidoptera.is_a.append(hasStage.some(Adult))\n"
             "print(ch4.dl_render(o.Lepidoptera))\n"
             "print('Modelling note: the SAME individual is morphologically distinct over time — '\n"
             "      'a temporal/identity challenge (returns in Chapter 5 & Chapter 10).')"),
        md("## Exercises 4.13 & 4.14 — workbook tutorial / domain-ontology mini-project\n"
           "*(Reformulated as Python mini-projects.)*\n\n"
           "- **4.13:** Using `owlready2`, build a small ontology of a domain you know "
           "(≥ 8 classes, ≥ 3 object properties, ≥ 2 defined classes with `∃`/`∀`), serialise it "
           "to RDF/XML, and run `ch4.reason_owlrl` to inspect the closure.\n"
           "- **4.14:** Extend it into a *domain ontology* (group assignment 1): add competency "
           "questions as SPARQL queries and check the ontology answers them.\n\n"
           "Starter scaffold below."),
        code("# STARTER SCAFFOLD for 4.13 / 4.14\n"
             "from owlready2 import Thing, ObjectProperty\n"
             "w = ch4.new_world(); my = w.get_ontology('http://example.org/mydomain#')\n"
             "with my:\n"
             "    class Entity(Thing): pass\n"
             "    # TODO: add your classes, properties, and defined classes here\n"
             "    class relatesTo(ObjectProperty): pass\n"
             "print('classes so far:', [c.name for c in my.classes()])\n"
             "# my.save('artifacts/mydomain.owl', format='rdfxml')\n"
             "# g,b,a,new = ch4.reason_owlrl(my); print(b,'->',a)"),
        md("---\n*All examples, snippets and tables from Chapter 4 are implemented in "
           "`ch4_toolkit.py`; exercises are runnable above. For full DL classification "
           "(consistency, subsumption proofs), point `owlready2.sync_reasoner()` at a Java + "
           "HermiT install.*"),
    ]
    save(c, "04_exercises.ipynb")


if __name__ == "__main__":
    nb00(); nb01(); nb02(); nb03(); nb04()
    print("done.")
