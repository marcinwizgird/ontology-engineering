"""
Generator for the Ontology Mapping notebooks.

Run this to (re)create the four pipeline notebooks under ./notebooks:
    01_extract_collibra.ipynb
    02_map_to_fibo.ipynb
    03_build_hbim.ipynb
    04_reason_hbim.ipynb

Each notebook is artifact-driven: it reads the file produced by the previous
step (under ../output) so notebooks can be run individually or in order.
The only shared code is ../src/common.py (paths + FIBO/HBIM namespaces).
"""
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent


def md(text):
    return nbf.v4.new_markdown_cell(text.strip("\n"))


def code(text):
    return nbf.v4.new_code_cell(text.strip("\n"))


def notebook(*cells):
    nb = nbf.v4.new_notebook()
    nb.cells = list(cells)
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    return nb


# Common setup cell reused by every notebook -------------------------------
SETUP = """
import sys, json
from pathlib import Path

# Make ../src importable so we can reuse the shared paths + namespaces.
SRC = Path.cwd().parent / "src"
sys.path.insert(0, str(SRC))
from common import (COLLIBRA_EXPORT, EXTRACTED_FILE, MAPPING_FILE,
                    HBIM_TTL, HBIM_INFERRED_TTL, FIBO_EXCERPT, OUTPUT_DIR,
                    PREFIXES, bind_all,
                    CAA, FPAS, FSE, REL, CMNS_ID, CMNS_ORG, HBIM)
import pandas as pd
pd.set_option("display.max_colwidth", 60)
print("Project root:", SRC.parent)
"""


# ==========================================================================
# 01 - EXTRACT
# ==========================================================================
nb01 = notebook(
    md("""
# 01 · Extract from the Collibra `Account` global data category

This notebook reads the Collibra business-glossary export of the **`Account`
global data category** and pulls out the three things we need:

1. **Business Terms** – assets of type *Business Term*
2. **Preferred Business-Term Attributes** – the *Preferred Term* attributes of each term
3. **Business-Term Relations** – relations between terms and to the data category

It writes `output/account_terms_extracted.json`, consumed by notebook **02**.
"""),
    code(SETUP),
    md("## Load the Collibra export"),
    code("""
with open(COLLIBRA_EXPORT, encoding="utf-8") as fh:
    export = json.load(fh)

category = export["dataCategory"]
print(f"Data category : {category['name']}  (scope={category['scope']})")
print(f"Community      : {export['community']['name']}")
print(f"Domain        : {export['domain']['name']}")
print(f"Assets        : {len(export['assets'])}   Relations: {len(export['relations'])}")
"""),
    md("## 1) Business terms"),
    code("""
business_terms = [a for a in export["assets"] if a["assetType"] == "Business Term"]
pd.DataFrame([{"id": t["id"], "name": t["name"], "status": t["status"]}
             for t in business_terms])
"""),
    md("""
## 2) Preferred business-term attributes

Collibra stores a `Preferred Term` flag plus the preferred label, acronym and
synonyms. We surface those here – they drive which terms become first-class HBIM
classes later (preferred) versus `skos:altLabel` synonyms (non-preferred).
"""),
    code("""
preferred_attributes = {}
for term in business_terms:
    attrs = term.get("attributes", {})
    preferred_attributes[term["id"]] = {
        "name": term["name"],
        "is_preferred": bool(attrs.get("Preferred Term", False)),
        "preferred_label": attrs.get("Preferred Term Label"),
        "acronym": attrs.get("Acronym"),
        "synonyms": attrs.get("Synonym", []),
        "definition": attrs.get("Definition"),
        "status": term.get("status"),
    }

df_pref = pd.DataFrame.from_dict(preferred_attributes, orient="index")
df_pref["synonyms"] = df_pref["synonyms"].apply(lambda s: ", ".join(s) if s else "")
df_pref[["name", "is_preferred", "preferred_label", "acronym", "synonyms"]]
"""),
    md("## 3) Business-term relations"),
    code("""
id_to_name = {a["id"]: a["name"] for a in export["assets"]}
id_to_name[category["id"]] = category["name"] + " (Data Category)"

relations = [{
    "source_id": r["source"], "source": id_to_name.get(r["source"], r["source"]),
    "type": r["type"],
    "target_id": r["target"], "target": id_to_name.get(r["target"], r["target"]),
} for r in export["relations"]]

pd.DataFrame(relations)[["source", "type", "target"]]
"""),
    md("## Persist the extraction for the next step"),
    code("""
extracted = {
    "category": category,
    "business_terms": business_terms,
    "preferred_attributes": preferred_attributes,
    "relations": relations,
}
with open(EXTRACTED_FILE, "w", encoding="utf-8") as fh:
    json.dump(extracted, fh, indent=2)
print("[written]", EXTRACTED_FILE)
"""),
)


# ==========================================================================
# 02 - MAP TO FIBO
# ==========================================================================
nb02 = notebook(
    md("""
# 02 · Map the Collibra terms to the FIBO Product & Account ontology

We align each extracted business term to a **FIBO** class and each relation type
to a **FIBO** object property. The mapping records the alignment strength so the
HBIM builder (notebook 03) knows which axiom to emit:

| kind | axiom |
|------|-------|
| `exact`    | `owl:equivalentClass` |
| `narrower` | `rdfs:subClassOf` |
| `close`    | `skos:closeMatch` |

Reads `output/account_terms_extracted.json`, writes
`output/collibra_to_fibo_mapping.json`.
"""),
    code(SETUP),
    code("""
with open(EXTRACTED_FILE, encoding="utf-8") as fh:
    extracted = json.load(fh)
pref = extracted["preferred_attributes"]
print("Loaded", len(extracted["business_terms"]), "business terms")
"""),
    md("""
## The curated alignment

This is the human-curated alignment a data architect produces when reconciling
the bank glossary with FIBO, expressed as data so the pipeline stays automated.
"""),
    code("""
def C(curie):
    prefix, local = curie.split(":")
    return str(PREFIXES[prefix]) + local

# Business term -> FIBO class
TERM_TO_FIBO = {
    "bt-account":            {"fibo": "caa:Account",                      "kind": "exact"},
    "bt-deposit-account":    {"fibo": "caa:DepositAccount",               "kind": "exact"},
    "bt-current-account":    {"fibo": "caa:DemandDepositAccount",         "kind": "narrower"},
    "bt-savings-account":    {"fibo": "caa:NonTransactionDepositAccount", "kind": "narrower"},
    "bt-account-holder":     {"fibo": "caa:AccountHolder",                "kind": "exact"},
    "bt-account-identifier": {"fibo": "caa:AccountIdentifier",            "kind": "exact"},
    "bt-account-balance":    {"fibo": "caa:Account",                      "kind": "close"},
    "bt-checking-account":   {"fibo": "caa:DemandDepositAccount",         "kind": "close"},
}

# Collibra relation type -> FIBO object property
RELATION_TO_FIBO = {
    "is held by":       "rel:isHeldBy",
    "is identified by": "cmns-id:isIdentifiedBy",
}
"""),
    md("## Business term → FIBO class"),
    code("""
term_mappings = []
for term in extracted["business_terms"]:
    tid = term["id"]
    m = TERM_TO_FIBO.get(tid)
    if not m:
        continue
    term_mappings.append({
        "collibra_id": tid,
        "business_term": term["name"],
        "preferred_label": pref[tid]["preferred_label"] or term["name"],
        "is_preferred": pref[tid]["is_preferred"],
        "fibo_curie": m["fibo"],
        "fibo_iri": C(m["fibo"]),
        "mapping_kind": m["kind"],
    })

pd.DataFrame(term_mappings)[["business_term", "is_preferred", "mapping_kind", "fibo_curie"]]
"""),
    md("## Relation type → FIBO property"),
    code("""
relation_mappings = []
for r in extracted["relations"]:
    prop = RELATION_TO_FIBO.get(r["type"])
    if prop:
        relation_mappings.append({
            "collibra_relation": r["type"],
            "source": r["source_id"], "target": r["target_id"],
            "fibo_property_curie": prop, "fibo_property_iri": C(prop),
        })

pd.DataFrame(relation_mappings)[["collibra_relation", "source", "target", "fibo_property_curie"]]
"""),
    md("## Persist the mapping"),
    code("""
mapping = {
    "category": extracted["category"]["name"],
    "term_mappings": term_mappings,
    "relation_mappings": relation_mappings,
}
with open(MAPPING_FILE, "w", encoding="utf-8") as fh:
    json.dump(mapping, fh, indent=2)
print("[written]", MAPPING_FILE)
"""),
)


# ==========================================================================
# 03 - BUILD HBIM
# ==========================================================================
nb03 = notebook(
    md("""
# 03 · Build the HBIM `Account` subject area (aligned to FIBO)

HBIM = the bank's **Harmonised Business Information Model**. We turn the mapped
terms into an OWL ontology whose classes are linked to FIBO via
`owl:equivalentClass` / `rdfs:subClassOf` / `skos:closeMatch`. Preferred-term
attributes become `skos:prefLabel` / `skos:altLabel` / `skos:definition`, mapped
relations become OWL restrictions reusing FIBO properties, and one sample
individual is added so notebook 04 can infer instance-level facts.

Reads the extraction + mapping, writes `output/hbim_account.ttl`.
"""),
    code(SETUP),
    code("""
from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef, BNode
from rdflib.namespace import SKOS

with open(EXTRACTED_FILE, encoding="utf-8") as fh:
    extracted = json.load(fh)
with open(MAPPING_FILE, encoding="utf-8") as fh:
    mapping = json.load(fh)

pref = extracted["preferred_attributes"]
by_id = {m["collibra_id"]: m for m in mapping["term_mappings"]}
"""),
    md("## Helpers"),
    code("""
def slug(name):
    "'Current Account' -> 'CurrentAccount'"
    return "".join(w.capitalize() for w in name.replace("-", " ").split())

def restriction(g, cls, prop, filler):
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, prop))
    g.add((r, OWL.someValuesFrom, filler))
    g.add((cls, RDFS.subClassOf, r))
"""),
    md("## Build the graph"),
    code("""
g = bind_all(Graph()); g.bind("skos", SKOS)
onto = URIRef("https://example.org/hbim/account")
g.add((onto, RDF.type, OWL.Ontology))
g.add((onto, RDFS.label, Literal("HBIM - Account subject area (aligned to FIBO)")))

hbim_class_for = {}
for term in extracted["business_terms"]:
    tid = term["id"]; p = pref[tid]
    if not p["is_preferred"]:          # non-preferred synonyms folded in below
        continue
    cls = HBIM[slug(p["preferred_label"] or term["name"])]
    hbim_class_for[tid] = cls
    g.add((cls, RDF.type, OWL.Class))
    g.add((cls, SKOS.prefLabel, Literal(p["preferred_label"] or term["name"], lang="en")))
    if p["definition"]:
        g.add((cls, SKOS.definition, Literal(p["definition"], lang="en")))
    if p["acronym"]:
        g.add((cls, SKOS.altLabel, Literal(p["acronym"], lang="en")))
    for syn in p["synonyms"]:
        g.add((cls, SKOS.altLabel, Literal(syn, lang="en")))

    m = by_id.get(tid)
    if m:
        fibo = URIRef(m["fibo_iri"]); kind = m["mapping_kind"]
        if kind == "exact":
            g.add((cls, OWL.equivalentClass, fibo))
        elif kind == "narrower":
            g.add((cls, RDFS.subClassOf, fibo))
        else:
            g.add((cls, SKOS.closeMatch, fibo))

# fold non-preferred synonyms onto their preferred class as altLabels
for r in extracted["relations"]:
    if r["type"] == "is synonym of":
        pc = hbim_class_for.get(r["source_id"])
        other = next((a for a in extracted["business_terms"] if a["id"] == r["target_id"]), None)
        if pc is not None and other is not None:
            g.add((pc, SKOS.altLabel, Literal(other["name"], lang="en")))

# relation axioms (reuse FIBO object properties)
acct = hbim_class_for.get("bt-account")
if acct and "bt-account-holder" in hbim_class_for:
    restriction(g, acct, REL.isHeldBy, hbim_class_for["bt-account-holder"])
if acct and "bt-account-identifier" in hbim_class_for:
    restriction(g, acct, CMNS_ID.isIdentifiedBy, hbim_class_for["bt-account-identifier"])

# sample individual -> instance-level inferences in notebook 04
inst = HBIM["account-GB29NWBK60161331926819"]
g.add((inst, RDF.type, hbim_class_for["bt-current-account"]))
g.add((inst, RDFS.label, Literal("Customer current account GB29 NWBK ...6819")))

print(f"{len(set(g.subjects(RDF.type, OWL.Class)))} classes, {len(g)} triples")
"""),
    md("## Serialize and preview the HBIM ontology"),
    code("""
g.serialize(destination=HBIM_TTL, format="turtle")
print("[written]", HBIM_TTL, "\\n")
print(g.serialize(format="turtle"))
"""),
)


# ==========================================================================
# 04 - REASON
# ==========================================================================
nb04 = notebook(
    md("""
# 04 · FIBO-based reasoning over HBIM

We merge the **FIBO excerpt** with the **HBIM** Account subject area and run an
**OWL RL** reasoner (`owlrl`). Because HBIM is aligned to FIBO, the FIBO axioms
flow into HBIM and the reasoner derives facts never stated in HBIM:

- **A.** class-level inferences – new superclasses for HBIM classes
- **B.** instance-level inferences – new types for HBIM individuals
- **C.** how this *improves* HBIM (enrich, completeness rules, equivalence bridges)
- **C.4** a consistency check that uses FIBO disjointness to catch a bad mapping

Reads the FIBO excerpt + `output/hbim_account.ttl`; writes
`output/hbim_account_inferred.ttl`.
"""),
    code(SETUP),
    code("""
from rdflib import Graph, RDF, RDFS, OWL, URIRef, BNode
from rdflib.namespace import SKOS
from owlrl import DeductiveClosure, OWLRL_Semantics

def is_reportable(node):
    return isinstance(node, URIRef) and any(
        str(node).startswith(str(ns)) for ns in (CAA, FPAS, FSE, HBIM))

def q(g, node):
    try:
        return g.qname(node)
    except Exception:
        return str(node)

# asserted = FIBO excerpt + HBIM
asserted = bind_all(Graph()); asserted.bind("skos", SKOS)
asserted.parse(FIBO_EXCERPT, format="turtle")
asserted.parse(HBIM_TTL, format="turtle")
print("Asserted triples:", len(asserted))
"""),
    md("## Run the OWL RL closure"),
    code("""
inferred = Graph()
for t in asserted:
    inferred.add(t)
DeductiveClosure(OWLRL_Semantics).expand(inferred)
bind_all(inferred); inferred.bind("skos", SKOS)
new = inferred - asserted
print(f"After reasoning: {len(inferred)} triples  (+{len(new)} inferred)")
"""),
    md("## A) Class-level inferences — new superclasses for HBIM classes"),
    code("""
hbim_classes = sorted({s for s in inferred.subjects(RDF.type, OWL.Class)
                       if str(s).startswith(str(HBIM))}, key=str)
rows = []
for cls in hbim_classes:
    for s in inferred.objects(cls, RDFS.subClassOf):
        if is_reportable(s) and s != cls and not str(s).startswith(str(HBIM)) \
           and (cls, RDFS.subClassOf, s) in new:
            rows.append({"hbim_class": q(inferred, cls),
                         "inferred_superclass": q(inferred, s)})
pd.DataFrame(rows).sort_values(["hbim_class", "inferred_superclass"]).reset_index(drop=True)
"""),
    md("## B) Instance-level inferences — new types for the sample account"),
    code("""
individuals = sorted({s for s in inferred.subjects(RDF.type, None)
                      if str(s).startswith(str(HBIM)) and "account-" in str(s)}, key=str)
rows = []
for ind in individuals:
    for t in inferred.objects(ind, RDF.type):
        if is_reportable(t):
            rows.append({"individual": q(inferred, ind),
                         "type": q(inferred, t),
                         "inferred": (ind, RDF.type, t) in new})
pd.DataFrame(rows).sort_values(["individual", "type"]).reset_index(drop=True)
"""),
    md("## Visualise the inferred class hierarchy"),
    code("""
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

# Subclass edges (child -> parent) among named reportable classes.
DG = nx.DiGraph()
DG.add_nodes_from(q(inferred, c) for c in hbim_classes)
for s, o in inferred.subject_objects(RDFS.subClassOf):
    if is_reportable(s) and is_reportable(o) and s != o:
        DG.add_edge(q(inferred, s), q(inferred, o))

# equivalentClass makes A<->B mutually subClassOf -> cycles. Condense each
# strongly-connected (equivalent) group into one node so the layout is a DAG.
cond = nx.condensation(DG)              # DAG of SCCs; node attr 'members'
def label(scc):
    members = sorted(cond.nodes[scc]["members"])
    hb = [m for m in members if m.startswith("hbim:")]
    return "\\n= ".join(hb + [m for m in members if not m.startswith("hbim:")])

# layered positions: superclasses on top, subclasses below
depth = {}
for d, layer in enumerate(nx.topological_generations(cond)):
    for n in layer:
        depth[n] = d
maxd = max(depth.values()) if depth else 0
bylvl = defaultdict(list)
for n, d in depth.items():
    bylvl[d].append(n)
pos = {}
for d, nodes in bylvl.items():
    for i, n in enumerate(sorted(nodes)):
        pos[n] = (i - (len(nodes) - 1) / 2, maxd - d)

labels = {n: label(n) for n in cond.nodes}
colors = ["#cde7ff" if "hbim:" in labels[n] else "#ffe7c2" for n in cond.nodes]
plt.figure(figsize=(13, 8))
nx.draw(cond, pos, labels=labels, node_color=colors, node_size=3000,
        font_size=8, edgecolors="#444", arrows=True, arrowstyle="-|>")
plt.title("Inferred class hierarchy  (blue = HBIM, orange = FIBO; '=' marks equivalent classes)")
plt.axis("off"); plt.tight_layout(); plt.show()
"""),
    md("""
## C) How FIBO reasoning improves HBIM

### 1. Enrich HBIM with inferred classifications
"""),
    code("""
ca = HBIM["CurrentAccount"]
if (ca, RDFS.subClassOf, FPAS.FinancialProduct) in inferred:
    print(f"FIBO proves {q(inferred, ca)} is a fpas:FinancialProduct,")
    print("although HBIM only stated it was a kind of demand-deposit account.")
    print("=> Add it to the HBIM Product subject area and reuse FIBO product governance.")
"""),
    md("### 2. Completeness rules from inherited FIBO restrictions"),
    code("""
def inherited_restrictions(g, cls):
    found = {}
    for sup in set(g.objects(cls, RDFS.subClassOf)) | {cls}:
        for r in g.objects(sup, RDFS.subClassOf):
            if (r, RDF.type, OWL.Restriction) in g:
                prop = next(g.objects(r, OWL.onProperty), None)
                filler = next(g.objects(r, OWL.someValuesFrom), None)
                if prop is not None and filler is not None and is_reportable(filler):
                    # prefer the FIBO filler over its HBIM twin
                    if prop not in found or not str(filler).startswith(str(HBIM)):
                        found[prop] = filler
    return found

rows = [{"every": q(inferred, ca), "must link via": q(inferred, p), "to": q(inferred, f)}
        for p, f in inherited_restrictions(inferred, ca).items()]
print("=> Turn these into HBIM data-quality checks (mandatory attributes).")
pd.DataFrame(rows)
"""),
    md("### 3. Equivalent-class bridges keep HBIM and FIBO in lock-step"),
    code("""
rows = [{"hbim": q(inferred, s), "owl:equivalentClass": q(inferred, o)}
        for s, o in inferred.subject_objects(OWL.equivalentClass)
        if str(s).startswith(str(HBIM)) and is_reportable(o)
        and s != o and not str(o).startswith(str(HBIM))]
pd.DataFrame(sorted(rows, key=lambda r: r["hbim"]))
"""),
    md("""
## C.4) Consistency check — FIBO disjointness validates HBIM

We inject a modelling error: map the (transactional) *Current Account* **also**
to `NonTransactionDepositAccount`. FIBO declares the two disjoint, so the sample
individual is forced into two disjoint classes — a clash the reasoner detects.
"""),
    code("""
bad = bind_all(Graph()); bad.bind("skos", SKOS)
for t in asserted:
    bad.add(t)
bad.add((ca, RDFS.subClassOf, CAA.NonTransactionDepositAccount))   # the mistake
DeductiveClosure(OWLRL_Semantics).expand(bad)

def disjoint_clashes(g):
    clashes = []
    pairs = {frozenset(p) for p in g.subject_objects(OWL.disjointWith)}
    for pair in pairs:
        a, b = tuple(pair)
        ma = set(g.subjects(RDF.type, a)) | set(g.subjects(RDFS.subClassOf, a))
        mb = set(g.subjects(RDF.type, b)) | set(g.subjects(RDFS.subClassOf, b))
        for n in (ma & mb):
            if n in (a, b) or n == OWL.Nothing or isinstance(n, BNode):
                continue
            clashes.append((n, a, b))
    return clashes

clashes = disjoint_clashes(bad)
if clashes:
    print("[INCONSISTENT] FIBO reasoning rejected the bad mapping:")
    for n, a, b in clashes:
        print(f"  {q(bad, n)} forced into disjoint {q(bad, a)} and {q(bad, b)}")
    print("\\n=> HBIM mapping error caught automatically: 'Current Account' is a")
    print("   transaction account and must NOT map to NonTransactionDepositAccount.")
else:
    print("no clash detected")
"""),
    md("## Persist the inferred graph"),
    code("""
inferred.serialize(destination=HBIM_INFERRED_TTL, format="turtle")
print("[written]", HBIM_INFERRED_TTL)
"""),
)


# ==========================================================================
if __name__ == "__main__":
    targets = {
        "01_extract_collibra.ipynb": nb01,
        "02_map_to_fibo.ipynb": nb02,
        "03_build_hbim.ipynb": nb03,
        "04_reason_hbim.ipynb": nb04,
    }
    for name, nb in targets.items():
        path = HERE / name
        nbf.write(nb, path)
        print("[written]", path)
