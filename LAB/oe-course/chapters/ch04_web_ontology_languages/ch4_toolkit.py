"""Python toolkit for Chapter 4 — *The Web Ontology Languages* (Keet, 2nd ed.).

Every example, code snippet and table from the chapter is reproduced here as a
runnable Python artefact, built on:

* **owlready2** — Pythonic OWL: classes, properties, restrictions, serialisation
  (no Java needed for *building* and *saving* ontologies);
* **rdflib** — RDF graphs, multiple serialisations, SPARQL;
* **owlrl** — a pure-Python OWL 2 RL reasoner used for the inference demos (the
  book runs HermiT/Pellet in Protégé, which require Java; OWL 2 RL reasoning in
  pure Python lets the notebooks *run the reasoner* anywhere).

The notebooks import from this module so the prose stays clean and the code is
reusable.  Functions that build an ontology use an **isolated** ``owlready2``
``World`` so cells can run repeatedly without name clashes.
"""

from __future__ import annotations

from textwrap import dedent

import owlready2 as owl2
from owlready2 import (
    Thing, ObjectProperty, DataProperty, FunctionalProperty,
    InverseFunctionalProperty, TransitiveProperty, SymmetricProperty,
    AsymmetricProperty, ReflexiveProperty, IrreflexiveProperty,
    World, Not,
)


def new_world() -> World:
    """A fresh, isolated owlready2 world (so notebook cells are repeatable)."""
    return World()


# ===========================================================================
# 4.1.1  How to design an ontology language  (Figure 4.1, the 7 steps)
# ===========================================================================
LANGUAGE_DESIGN_PROCESS: list[dict] = [
    {"step": 1, "name": "Clarification of Scope and Purpose",
     "tasks": ["1a. Determine scope, benefits",
               "1b. Long-term perspective",
               "1c. Economics, feasibility"]},
    {"step": 2, "name": "Analysis of General Requirements",
     "tasks": ["2a. Determine requirements for modelling and reasoning",
               "2b. Use case scenarios",
               "2c. Assign priorities"]},
    {"step": 3, "name": "Ontological Analysis",
     "tasks": ["3a. Assess ontological commitments for the language",
               "3b. Consider performance trade-offs on features and reasoning"]},
    {"step": 4, "name": "Language Specification",
     "tasks": ["4a. Specify syntax and semantics",
               "4b. Describe glossary and documentation",
               "4c. Define metamodel"]},
    {"step": 5, "name": "Design of Notation for Modeller",
     "tasks": ["5a. Create graphical notation / sample diagrams or controlled natural language",
               "5b. Evaluate notation"]},
    {"step": 6, "name": "Development of Modelling Tool",
     "tasks": ["6a. Create computer-processable format",
               "6b. Create diagrams/CNL and evaluate notation",
               "6c. Associate with automated reasoner"]},
    {"step": 7, "name": "Evaluation and Refinement",
     "tasks": ["7a. Define test cases, validate and verify",
               "7b. Check against requirements",
               "7c. Analyse effect of use against current practice"]},
]

OWL_DESIGN_GOALS = [
    "Shareable", "Change over time", "Interoperability", "Inconsistency detection",
    "Balancing expressivity and complexity", "Ease of use",
    "Compatible with existing standards", "Internationalisation",
]

# 4.1.2  Main differentiating features of OWL vs plain DLs
OWL_VS_DL = [
    "OWL uses IRI references as names (e.g. .../UniOnto.owl#Student); IRIs can be abbreviated.",
    "Ontologies are documents (RDF/XML) with owl:imports to import one ontology into another.",
    "OWL files can carry metadata (version info, creators, ...).",
    "RDF/XSD datatypes are added for ranges of data properties (string, integer, ...).",
    "Terminology: DL concept -> class, DL role -> object property, plus data property for attributes.",
]


# ===========================================================================
# 4.1.3  OWL family, first version (the three OWL 1 species)
# ===========================================================================
OWL1_SPECIES = {
    "OWL Lite": {
        "dl": "SHIF(D)",
        "is_dl": True,
        "notes": "Classification hierarchy + simple constraints; "
                 "unqualified (0/1) number restrictions.",
        "features": ["Named classes (A)", "Named properties (P)", "Individuals C(o)",
                     "Property values P(o,a)", "Intersection (C ⊓ D)", "Union (C ⊔ D)",
                     "Negation (¬C)", "Existential ∃P.C", "Universal ∀P.C",
                     "Unqualified (0/1) number restrictions"],
    },
    "OWL DL": {
        "dl": "SHOIN(D)",
        "is_dl": True,
        "notes": "'Maximal' expressiveness while keeping decidability (the 2004 sweet spot).",
        "features": ["All OWL Lite features", "Arbitrary number restrictions (0 ≤ n)",
                     "Property value (∃P.{o})", "Enumeration {o1,...,on}"],
    },
    "OWL Full": {
        "dl": "— (not a DL)",
        "is_dl": False,
        "notes": "Very high expressiveness, RDF syntactic freedom, meta-classes, "
                 "self-modifying; loses decidability. NOT a Description Logic.",
        "features": ["Meta-classes", "Classes as instances", "Full RDF freedom"],
    },
}


# ===========================================================================
# Tables 4.1 / 4.2  — OWL constructs & axioms, DL notation, examples
#   Each row is also *built for real* with owlready2 (see build_construct_demo).
# ===========================================================================
def table_4_1_constructs():
    """Table 4.1: OWL class constructs ↔ DL notation ↔ example (pandas)."""
    import pandas as pd
    rows = [
        ("intersectionOf", "C₁ ⊓ … ⊓ Cₙ", "Human ⊓ Male"),
        ("unionOf", "C₁ ⊔ … ⊔ Cₙ", "Doctor ⊔ Lawyer"),
        ("complementOf", "¬C", "¬Male"),
        ("oneOf", "{o₁, …, oₙ}", "{giselle, juan}"),
        ("allValuesFrom", "∀P.C", "∀hasChild.Doctor"),
        ("someValuesFrom", "∃P.C", "∃hasChild.Lawyer"),
        ("value", "∃P.{o}", "∃citizenOf.{RSA}"),
        ("minCardinality", "≥ nP", "≥ 2 hasChild"),
        ("maxCardinality", "≤ nP", "≤ 6 enrolledIn"),
    ]
    return pd.DataFrame(rows, columns=["OWL construct", "DL notation", "Example"])


def table_4_2_axioms():
    """Table 4.2: OWL axioms ↔ DL notation ↔ example (pandas)."""
    import pandas as pd
    rows = [
        ("SubClassOf", "C₁ ⊑ C₂", "Human ⊑ Animal ⊓ Biped"),
        ("EquivalentClasses", "C₁ ≡ … ≡ Cₙ", "Man ≡ Human ⊓ Male"),
        ("SubPropertyOf", "P₁ ⊑ P₂", "hasDaughter ⊑ hasChild"),
        ("EquivalentProperties", "P₁ ≡ … ≡ Pₙ", "cost ≡ price"),
        ("SameIndividual", "o₁ = … = oₙ", "Comrade_Marx = K_Marx"),
        ("DisjointClasses", "Cᵢ ⊑ ¬Cⱼ", "Male ⊑ ¬Female"),
        ("DifferentIndividuals", "oᵢ ≠ oⱼ", "Thabo ≠ Andile"),
        ("inverseOf", "P₁ ≡ P₂⁻", "hasChild ≡ hasParent⁻"),
        ("transitiveProperty", "P⁺ ⊑ P", "Trans(ancestor)"),
        ("symmetricProperty", "P ≡ P⁻", "Sym(connectedTo)"),
        ("functionalProperty", "⊤ ⊑ ≤1P", "⊤ ⊑ ≤1 hasPresident"),
        ("inverseFunctionalProperty", "⊤ ⊑ ≤1P⁻", "⊤ ⊑ ≤1 hasIDNo⁻"),
    ]
    return pd.DataFrame(rows, columns=["OWL axiom", "DL notation", "Example"])


def build_construct_demo():
    """Build the Table 4.1/4.2 examples *for real* with owlready2.

    Returns the ontology so the notebook can serialise/inspect it.
    """
    w = new_world()
    onto = w.get_ontology("http://example.org/constructs#")
    with onto:
        class Human(Thing): pass
        class Male(Thing): pass
        class Female(Thing): pass
        class Animal(Thing): pass
        class Biped(Thing): pass
        class Doctor(Thing): pass
        class Lawyer(Thing): pass
        class hasChild(ObjectProperty): pass
        class enrolledIn(ObjectProperty): pass
        class citizenOf(ObjectProperty): pass

        # intersectionOf:  Man ≡ Human ⊓ Male
        class Man(Thing):
            equivalent_to = [Human & Male]
        # unionOf:  Doctor ⊔ Lawyer
        class Professional(Thing):
            equivalent_to = [Doctor | Lawyer]
        # complementOf:  ¬Male  -> NonMale ≡ ¬Male
        class NonMale(Thing):
            equivalent_to = [Not(Male)]
        # someValuesFrom / allValuesFrom / min / max
        class ParentOfDoctor(Thing):
            equivalent_to = [hasChild.some(Doctor)]
        class AllKidsDoctors(Thing):
            equivalent_to = [hasChild.only(Doctor)]
        class HasTwoChildren(Thing):
            equivalent_to = [hasChild.min(2)]
        # DisjointClasses: Male ⊑ ¬Female
        owl2.AllDisjoint([Male, Female])
        # SubClassOf: Human ⊑ Animal ⊓ Biped
        Human.is_a.append(Animal & Biped)
    return onto


# ===========================================================================
# Example 4.1 — The African Wildlife Ontology (AWO)
# ===========================================================================
def build_awo(level: int = 1):
    """Build the African Wildlife Ontology (Example 4.1).

    level=0 : the basic tutorial ontology (giraffe eats only leaves, etc.)
    level=1 : extended with proper parthood and more animals/plants and the
              herbivore/carnivore/omnivore definitions.
    Returns an owlready2 ontology in an isolated world.
    """
    w = new_world()
    onto = w.get_ontology("http://www.meteck.org/teaching/ontologies/AfricanWildlifeOntology#")
    with onto:
        class Animal(Thing): pass
        class Plant(Thing): pass

        class eats(ObjectProperty): pass
        class is_part_of(ObjectProperty): pass
        class has_part(ObjectProperty):
            inverse_property = is_part_of

        # plant parts
        class PlantPart(Thing): pass
        class Leaf(PlantPart): pass
        class Twig(PlantPart): pass
        class Root(PlantPart): pass

        # animals
        class Herbivore(Animal):
            # eats only plants or plant parts
            equivalent_to = [Animal & eats.only(Plant | PlantPart)]
        class Carnivore(Animal):
            equivalent_to = [Animal & eats.some(Animal)]

        class Giraffe(Herbivore):
            # giraffes eat only leaves
            is_a = [eats.only(Leaf)]
            comment = ["Giraffes are herbivores, and they eat only leaves."]
        class Lion(Carnivore):
            is_a = [eats.some(Herbivore)]
        class Plant_with_parts(Plant): pass

    if level >= 1:
        with onto:
            class Omnivore(onto.Animal):
                equivalent_to = [onto.Animal
                                 & onto.eats.some(onto.Animal)
                                 & onto.eats.some(onto.Plant | onto.PlantPart)]
            class Impala(onto.Herbivore): pass
            class Warthog(onto.Omnivore): pass
            class RockDassie(onto.Herbivore): pass
            class Branch(onto.PlantPart): pass
            # parthood: a leaf is part of a plant
            onto.Leaf.is_a.append(onto.is_part_of.some(onto.Plant))
    return onto


def awo_giraffe_owl_snippet(onto=None) -> str:
    """Return the RDF/XML for the Giraffe class (the Python twin of Listing 4.1)."""
    import tempfile, os, re
    if onto is None:
        onto = build_awo(level=0)
    path = os.path.join(tempfile.gettempdir(), "awo_snippet.owl")
    onto.save(file=path, format="rdfxml")
    xml = open(path, encoding="utf-8").read()
    # extract the Giraffe class block for a focused, Listing-4.1-style snippet
    m = re.search(r'(<owl:Class[^>]*Giraffe.*?</owl:Class>)', xml, re.S)
    return m.group(1) if m else xml


# ===========================================================================
# 4.2.1  New OWL 2 features (qualified cardinality, R-box, property chains)
# ===========================================================================
def build_owl2_features():
    """Demonstrate the headline OWL 2 (SROIQ) features with owlready2."""
    w = new_world()
    onto = w.get_ontology("http://example.org/owl2feat#")
    with onto:
        class Thing_(Thing): pass
        class Wheel(Thing): pass
        class Component(Thing): pass
        class Door(Thing): pass
        class hasComponent(ObjectProperty): pass
        class hasPart(ObjectProperty): pass

        # Qualified cardinality: Bicycle ⊑ ≥2 hasComponent.Wheel  (the Q in SROIQ)
        class Bicycle(Thing):
            is_a = [hasComponent.min(2, Wheel)]
        # Local reflexivity ∃knows.Self
        class knows(ObjectProperty): pass
        class Narcissist(Thing):
            is_a = [knows.has_self()]
        # Irreflexive proper parthood
        class properPartOf(ObjectProperty, IrreflexiveProperty, AsymmetricProperty): pass
        # Property chain: hasMother ∘ hasSister ⊑ hasAunt
        class hasMother(ObjectProperty): pass
        class hasSister(ObjectProperty): pass
        class hasAunt(ObjectProperty):
            pass
        hasAunt.property_chain = []  # placeholder; set below via PropertyChain
        try:
            from owlready2 import PropertyChain
            hasAunt.property_chain.append(PropertyChain([hasMother, hasSister]))
        except Exception:
            pass
    return onto


OWL2_NEW_FEATURES = {
    "Qualified cardinality restrictions": "≥ nR.C, ≤ nR.C, = nR.C — e.g. Bicycle ⊑ ≥2 hasComponent.Wheel (the Q in SROIQ).",
    "Local reflexivity (Self)": "∃R.Self — e.g. ∃knows.Self for a Narcissist (ObjectHasSelf).",
    "Global reflexivity": "Ref(R) — everything is connected to itself.",
    "Irreflexivity": "Irr(R) — proper parthood: nothing is a proper part of itself.",
    "Asymmetry": "Asym(R) — Asym(parentOf): if John is parent of Divesh, Divesh is not parent of John.",
    "Property chains": "R ∘ S ⊑ R — e.g. childOf ∘ childOf ⊑ grandchildOf (the R in SROIQ).",
}

# Features usable only on *simple* object properties (no transitive/chained sub-properties)
SIMPLE_ONLY_FEATURES = [
    "ObjectMinCardinality", "ObjectMaxCardinality", "ObjectExactCardinality",
    "ObjectHasSelf", "FunctionalObjectProperty", "InverseFunctionalObjectProperty",
    "IrreflexiveObjectProperty", "AsymmetricObjectProperty", "DisjointObjectProperties",
]


def cakes_allergies_demo():
    """Example 4.2 — the 'simple object property' trade-off (cakes & allergies).

    Builds two facets:
      * transitive hasPart so that cake⊑∃hasPart.butter and butter⊑∃hasPart.milk
        entails cake has ingredient milk (shown via the OWL 2 RL reasoner);
      * a qualified cardinality on the SAME property (regular cake = exactly 4
        ingredients), which is illegal because a *non-simple* (transitive)
        property may not carry a cardinality restriction.
    Returns a dict describing the conflict and the inferred 'milk' triple.
    """
    from rdflib import Graph, Namespace, RDF, RDFS, OWL, BNode, Literal
    EX = Namespace("http://example.org/cake#")
    g = Graph(); g.bind("ex", EX); g.bind("owl", OWL)
    # transitive hasPart
    g.add((EX.hasPart, RDF.type, OWL.TransitiveProperty))
    g.add((EX.hasPart, RDF.type, OWL.ObjectProperty))
    # individuals: cake -hasPart-> butter -hasPart-> milk
    g.add((EX.cake1, RDF.type, EX.Cake))
    g.add((EX.cake1, EX.hasPart, EX.butter1))
    g.add((EX.butter1, EX.hasPart, EX.milk1))
    before = len(g)
    import owlrl
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    inferred_milk = (EX.cake1, EX.hasPart, EX.milk1) in g
    return {
        "transitive_inference": f"cake1 hasPart milk1 inferred = {inferred_milk}",
        "triples_before_after": (before, len(g)),
        "conflict": ("A DL reasoner rejects asserting BOTH "
                     "TransitiveObjectProperty(hasPart) AND "
                     "ObjectExactCardinality(4 hasPart Ingredient): a *non-simple* "
                     "(transitive) property may not appear in a cardinality restriction. "
                     "You must choose transitivity OR the qualified cardinality, not both."),
        "reasoner_error": ("Non-simple property '<ex#hasPart>' or its inverse appears in "
                           "the cardinality restriction "
                           "'ObjectMaxCardinality(4 <ex#hasPart> <ex#Ingredient>)'."),
        "simple_only_features": SIMPLE_ONLY_FEATURES,
    }


# ===========================================================================
# 4.2.2  OWL 2 Profiles  (EL / QL / RL) + a lightweight feature checker
# ===========================================================================
OWL2_PROFILES = {
    "OWL 2 EL": {"dl": "EL++", "complexity": "PTime-complete",
                 "purpose": "Large, relatively simple type-level (TBox) ontologies, e.g. SNOMED CT."},
    "OWL 2 QL": {"dl": "DL-Lite_R", "complexity": "NLogSpace / AC0 (data)",
                 "purpose": "Query answering over large amounts of data (OBDA), DB-like performance."},
    "OWL 2 RL": {"dl": "DLP / pD*", "complexity": "PTime-complete",
                 "purpose": "Rules + data as RDF triples; scalable forward-chaining reasoning."},
}


def classify_profile(onto) -> dict:
    """A *heuristic* OWL-species feature checker (a tiny stand-in for the
    'OWL Classifier' mentioned in the chapter).

    Flags constructs that push an ontology out of the lightweight profiles.
    Not a substitute for a real profile validator, but illustrates the idea.
    """
    g = onto.world.as_rdflib_graph()
    from rdflib import OWL, RDF, RDFS
    counts = {
        "union (⊔)": len(list(g.triples((None, OWL.unionOf, None)))),
        "complement (¬)": len(list(g.triples((None, OWL.complementOf, None)))),
        "allValuesFrom (∀)": len(list(g.triples((None, OWL.allValuesFrom, None)))),
        "cardinality": (len(list(g.triples((None, OWL.minQualifiedCardinality, None))))
                        + len(list(g.triples((None, OWL.maxQualifiedCardinality, None))))
                        + len(list(g.triples((None, OWL.qualifiedCardinality, None))))
                        + len(list(g.triples((None, OWL.minCardinality, None))))
                        + len(list(g.triples((None, OWL.maxCardinality, None))))),
        "someValuesFrom (∃)": len(list(g.triples((None, OWL.someValuesFrom, None)))),
        "oneOf": len(list(g.triples((None, OWL.oneOf, None)))),
    }
    verdict = []
    if counts["union (⊔)"] or counts["complement (¬)"] or counts["allValuesFrom (∀)"]:
        verdict.append("Out of OWL 2 EL (EL++ has no ⊔, ¬, ∀).")
    if counts["cardinality"]:
        verdict.append("Out of OWL 2 EL/QL (no cardinality there).")
    if counts["someValuesFrom (∃)"] and counts["allValuesFrom (∀)"]:
        verdict.append("∃ on LHS / ∀ anywhere narrows the profile.")
    if not verdict:
        verdict.append("Looks compatible with the lightweight profiles (heuristic).")
    return {"feature_counts": counts, "verdict": verdict}


# ===========================================================================
# 4.2.3  OWL 2 syntaxes — FirstYearCourse ⊑ ∀isTaughtBy.Professor
#         (Listings 4.2 RDF/XML, 4.3 OWL/XML, 4.4 functional, 4.5-4.7 Manchester)
# ===========================================================================
def firstyearcourse_ontology():
    """Build  FirstYearCourse ⊑ ∀isTaughtBy.Professor  (Eq. 4.1)."""
    w = new_world()
    onto = w.get_ontology("http://www.yourpa.ge/ontologies/exUni.owl#")
    with onto:
        class Professor(Thing): pass
        class isTaughtBy(ObjectProperty): pass
        class FirstYearCourse(Thing):
            is_a = [isTaughtBy.only(Professor)]
    return onto


def render_syntaxes(onto=None) -> dict[str, str]:
    """Render the FirstYearCourse axiom in the chapter's syntaxes.

    RDF/XML and Turtle are produced *for real* (owlready2 + rdflib); the
    functional-style, OWL/XML and Manchester renderings are faithful textual
    twins of Listings 4.3, 4.4 and 4.5-4.7.
    """
    import tempfile, os
    if onto is None:
        onto = firstyearcourse_ontology()
    path = os.path.join(tempfile.gettempdir(), "fyc.owl")
    onto.save(file=path, format="rdfxml")
    rdfxml = open(path, encoding="utf-8").read()
    turtle = onto.world.as_rdflib_graph().serialize(format="turtle")

    functional = dedent("""\
        Declaration(Class(:FirstYearCourse))
        SubClassOf(:FirstYearCourse owl:Thing)
        SubClassOf(:FirstYearCourse ObjectAllValuesFrom(:isTaughtBy :Professor))""")
    owlxml = dedent("""\
        <SubClassOf>
          <Class IRI="#FirstYearCourse"/>
          <ObjectAllValuesFrom>
            <ObjectProperty IRI="#isTaughtBy"/>
            <Class IRI="#Professor"/>
          </ObjectAllValuesFrom>
        </SubClassOf>""")
    manchester_long = dedent("""\
        Class: <http://www.yourpa.ge/ontologies/exUni.owl#FirstYearCourse>
        SubClassOf:
            owl:Thing,
            <http://www.yourpa.ge/ontologies/exUni.owl#isTaughtBy> only
                <http://www.yourpa.ge/ontologies/exUni.owl#Professor>""")
    manchester_short = dedent("""\
        Class: FirstYearCourse
        SubClassOf:
            owl:Thing,
            isTaughtBy only Professor""")
    manchester_min = "FirstYearCourse SubClassOf isTaughtBy only Professor"
    dl = "FirstYearCourse ⊑ ∀isTaughtBy.Professor"
    return {
        "DL (Eq. 4.1)": dl,
        "RDF/XML (Listing 4.2, required)": rdfxml,
        "Turtle": turtle,
        "OWL/XML (Listing 4.3)": owlxml,
        "Functional-style (Listing 4.4)": functional,
        "Manchester long (Listing 4.5)": manchester_long,
        "Manchester short (Listing 4.6)": manchester_short,
        "Manchester minimal (Listing 4.7)": manchester_min,
    }


# ===========================================================================
# 4.2.4  Complexity of OWL species (Table 4.3)  +  4.4 feature table (Table 4.4)
# ===========================================================================
def complexity_table_4_3():
    import pandas as pd
    rows = [
        ("OWL 2 (RDF-based sem.)", "Undecidable", "Undecidable", "Undecidable", "Undecidable"),
        ("OWL 2 (Direct sem.)", "2NEXPTIME-complete", "Decidable (NP-Hard)", "N/A", "2NEXPTIME-complete"),
        ("OWL 2 EL", "PTIME-complete", "PTIME-complete", "NP-complete (CQ)", "PSPACE-complete (CQ)"),
        ("OWL 2 QL", "NLogSpace-complete", "AC0", "NP-complete (CQ)", "NP-complete (CQ)"),
        ("OWL 2 RL", "PTIME-complete", "PTIME-complete", "NP-complete (CQ)", "NP-complete (CQ)"),
        ("OWL DL (OWL 1)", "NEXPTIME-complete", "Decidable (NP-Hard)", "N/A", "NEXPTIME-complete"),
    ]
    return pd.DataFrame(rows, columns=["Language", "Taxonomic", "Data", "Query", "Combined"])


def feature_table_4_4():
    """Table 4.4 partial feature comparison (the values printed in the book;
    '.' marks cells the reader is asked to complete in Exercise 4.1)."""
    import pandas as pd
    cols = ["Feature", "OWL1 Lite", "OWL1 DL", "OWL2 DL", "OWL2 EL", "OWL2 QL", "OWL2 RL"]
    rows = [
        ("Role hierarchy", "+", "+", "+", ".", "+", "."),
        ("N-ary roles (n≥2)", "–", "–", "–", ".", "?", "."),
        ("Role chaining", "–", "–", "+", ".", "–", "."),
        ("Role acyclicity", "–", "–", "–", ".", "–", "."),
        ("Symmetry", "+", "+", "+", ".", "+", "."),
        ("Role values", "–", "–", "–", ".", "–", "."),
        ("Qualified number restrictions", "–", "–", "+", ".", "–", "."),
        ("One-of, enumerated classes", "?", "+", "+", ".", "–", "."),
        ("Functional dependency", "+", "+", "+", ".", "?", "."),
        ("Covering constraint over concepts", "?", "+", "+", ".", "–", "."),
        ("Complement of concepts", "?", "+", "+", ".", "+", "."),
        ("Complement of roles", "–", "–", "+", ".", "+", "."),
        ("Concept identification", "–", "–", "–", ".", "–", "."),
        ("Range typing", "–", "+", "+", ".", "+", "."),
        ("Reflexivity", "–", "–", "+", ".", "–", "."),
        ("Antisymmetry", "–", "–", "–", ".", "–", "."),
        ("Transitivity", "+", "+", "+", ".", "–", "."),
        ("Asymmetry", "?", "?", "+", "–", "+", "+"),
        ("Irreflexivity", "–", "–", "+", ".", "–", "."),
    ]
    return pd.DataFrame(rows, columns=cols)


# ===========================================================================
# 4.3  OWL in context — Semantic Web layer cake, Common Logic, DOL
# ===========================================================================
SEMANTIC_WEB_LAYERS = [
    ("URI / Unicode", "Identification & characters"),
    ("XML", "Surface syntax (no semantics)"),
    ("RDF", "Data model: relations between things"),
    ("RDFS / SHACL", "Schema / shapes & constraints"),
    ("SPARQL / RIF / SWRL / R2RML", "Query, rules, RDB-to-RDF"),
    ("OWL", "Ontology language: knowledge & reasoning"),
    ("Applications", "User-facing systems"),
]

COMMON_LOGIC = {
    "name": "Common Logic (CL), ISO-standardised",
    "family": "First-order logic family with a common abstract syntax, model-theoretic semantics, XML.",
    "dialects": ["CLIF (Common Logic Interchange Format, textual)",
                 "CGIF (Conceptual Graph Interchange Format, diagrams)",
                 "XCL (eXtended Common Logic Markup Language, XML)"],
    "design_goals": ["Common interlingua for varied KR notations",
                     "Syntactically as unconstrained as possible",
                     "Semantically as simple/conventional as possible",
                     "Full FOL with equality, at least",
                     "Web-savvy, up-to-date",
                     "Historical origins in KIF"],
}

DOL = {
    "name": "Distributed Ontology, Model and Specification Language (DOL)",
    "standard": "OMG standard (2016)",
    "idea": ("A unified metalanguage to combine ontologies in different logics; put axioms that "
             "violate OWL 2 DL restrictions in a linked module and reason over the combined theory."),
    "theory": "Uses institutions to tie logics together (interoperability across logics).",
    "tools": ["Heterogeneous Tool Set (Hets)", "OntoHub repository"],
}


def draw_semantic_web_layercake(path: str = "artifacts/semantic_web_layercake.png"):
    """Render the Semantic Web 'layer cake' (Figure 4.4) with matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    layers = SEMANTIC_WEB_LAYERS
    fig, ax = plt.subplots(figsize=(9, 6))
    n = len(layers)
    colors = ["#ECEFF1", "#CFD8DC", "#B0BEC5", "#90CAF9", "#64B5F6", "#FFB74D", "#A5D6A7"]
    for i, (name, desc) in enumerate(layers):
        y = i
        ax.add_patch(FancyBboxPatch((0.5, y + 0.1), 9, 0.8,
                     boxstyle="round,pad=0.02,rounding_size=0.08",
                     facecolor=colors[i % len(colors)], edgecolor="#37474F"))
        ax.text(1.0, y + 0.5, name, fontsize=12, fontweight="bold", va="center")
        ax.text(5.2, y + 0.5, desc, fontsize=9.5, color="#37474F", va="center")
    ax.text(0.5, n + 0.4, "Semantic Web 'layer cake' (Figure 4.4)",
            fontsize=14, fontweight="bold")
    ax.set_xlim(0, 10); ax.set_ylim(0, n + 1); ax.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


# ===========================================================================
# Reasoning helpers (pure-Python OWL 2 RL via owlrl)
# ===========================================================================
def reason_owlrl(onto_or_graph, semantics: str = "rdfs_owl"):
    """Run the pure-Python OWL 2 RL / RDFS reasoner; return (graph, before, after, new).

    Accepts an owlready2 ontology or an rdflib Graph.
    """
    import owlrl
    from rdflib import Graph
    if isinstance(onto_or_graph, Graph):
        g = onto_or_graph
    else:
        # materialise the owlready2 world into an independent rdflib graph
        src = onto_or_graph.world.as_rdflib_graph()
        g = Graph()
        for t in src:
            g.add(t)
    before = set(g)
    if semantics == "rdfs":
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
    else:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    after = set(g)
    return g, len(before), len(after), (after - before)


def dl_render(cls) -> str:
    """Render an owlready2 class's superclass axioms in DL-ish notation
    (a Python twin of the 'DL axiom renderer' Protégé plug-in, Exercise 4.4)."""
    parts = []
    for sup in cls.is_a:
        parts.append(f"{cls.name} ⊑ {_dl(sup)}")
    for eq in getattr(cls, "equivalent_to", []):
        parts.append(f"{cls.name} ≡ {_dl(eq)}")
    return "\n".join(parts) if parts else f"{cls.name} ⊑ ⊤"


def _dl(expr) -> str:
    """Best-effort DL rendering of an owlready2 class expression."""
    import owlready2 as o
    if isinstance(expr, o.ThingClass):
        return expr.name
    if isinstance(expr, o.Restriction):
        prop = expr.property.name
        t = expr.type  # owlready2 restriction type code
        val = getattr(expr, "value", None)
        if t == o.SOME:
            return f"∃{prop}.{_dl(val)}"
        if t == o.ONLY:
            return f"∀{prop}.{_dl(val)}"
        if t in (o.MIN, o.MAX, o.EXACTLY):
            sym = {o.MIN: "≥", o.MAX: "≤", o.EXACTLY: "="}[t]
            card = getattr(expr, "cardinality", "n")
            filler = _dl(val) if val is not None else "⊤"
            return f"{sym}{card} {prop}.{filler}"
        if t == o.VALUE:
            return f"∃{prop}.{{{val}}}"
        return f"{prop}?"
    if isinstance(expr, o.And):
        return "(" + " ⊓ ".join(_dl(c) for c in expr.Classes) + ")"
    if isinstance(expr, o.Or):
        return "(" + " ⊔ ".join(_dl(c) for c in expr.Classes) + ")"
    if isinstance(expr, o.Not):
        return f"¬{_dl(expr.Class)}"
    return str(expr)


if __name__ == "__main__":
    # self-test
    print("language design steps:", len(LANGUAGE_DESIGN_PROCESS))
    print("OWL1 species:", list(OWL1_SPECIES))
    print("table 4.1 rows:", len(table_4_1_constructs()))
    print("table 4.2 rows:", len(table_4_2_axioms()))
    awo = build_awo(1)
    print("AWO classes:", len(list(awo.classes())))
    fyc = firstyearcourse_ontology()
    print("FYC DL render:", dl_render(fyc.FirstYearCourse))
    syn = render_syntaxes(fyc)
    print("syntaxes:", list(syn))
    cd = build_construct_demo()
    print("construct demo classes:", len(list(cd.classes())))
    feat = build_owl2_features()
    print("owl2 feature classes:", [c.name for c in feat.classes()])
    cake = cakes_allergies_demo()
    print("cake:", cake["transitive_inference"])
    prof = classify_profile(build_awo(1))
    print("profile verdict:", prof["verdict"])
    g, b, a, new = reason_owlrl(build_awo(1))
    print(f"owlrl AWO: {b} -> {a} (+{len(new)})")
    print("complexity rows:", len(complexity_table_4_3()), "| feature rows:", len(feature_table_4_4()))
    print("SELF-TEST OK")
