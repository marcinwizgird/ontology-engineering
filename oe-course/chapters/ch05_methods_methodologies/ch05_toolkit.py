"""Chapter 5 toolkit — methodologies, competency questions, and OntoClean.

Chapter 5 is the one students most often read as folklore: a parade of named
methodologies and some advice about quality. This module makes all three of its
threads executable and checkable.

* **Methodologies** (§5.1) become a catalogue with *selection criteria*, so
  "which methodology?" is answered from the project brief rather than from
  habit.
* **Competency questions** become **SPARQL queries**. A CQ is answerable exactly
  when its query returns a non-empty answer over the ontology — which turns the
  vaguest artefact in ontology engineering into a pass/fail test and a coverage
  percentage.
* **OntoClean** (§5.2) becomes a constraint checker. Tag classes with rigidity,
  identity, unity and dependence; the taxonomy constraints then find subsumption
  axioms that are *ontologically* wrong even though they are logically
  consistent — a class of error no reasoner in Chapters 3–4 can catch.

That last point is the chapter's real argument: consistency is not correctness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "METHODOLOGIES", "recommend_methodology", "methodology_table",
    "CompetencyQuestion", "AWO_CQS", "check_cq", "cq_coverage",
    "MetaProperties", "ONTOCLEAN_TAGS", "TAXONOMY", "ontoclean_violations",
    "ONTOCLEAN_CONSTRAINTS", "DEVELOPMENT_STEPS",
]


# --------------------------------------------------------------------------- #
# §5.1  Methodologies
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Methodology:
    """One named methodology, with the situation it was designed for."""

    id: str
    name: str
    phases: tuple[str, ...]
    fits_when: tuple[str, ...]
    note: str


#: Deliberately small and opinionated. Each `fits_when` entry is a *signal to
#: look for in a project brief*, which is what makes selection checkable rather
#: than a matter of taste.
METHODOLOGIES = [
    Methodology(
        "methontology", "METHONTOLOGY",
        ("specification", "knowledge acquisition", "conceptualisation",
         "formalisation", "implementation", "maintenance"),
        ("greenfield", "single team", "full lifecycle", "from scratch"),
        "The classic full-lifecycle method: build one ontology, carefully, from nothing.",
    ),
    Methodology(
        "on-to-knowledge", "On-To-Knowledge",
        ("feasibility study", "kickoff", "refinement", "evaluation", "maintenance"),
        ("knowledge management", "business case first", "application driven"),
        "Starts from a feasibility study, so it fits when the business case is not yet proven.",
    ),
    Methodology(
        "diligent", "DILIGENT",
        ("build", "local adaptation", "analysis", "revision", "local update"),
        ("distributed", "many contributors", "evolving", "decentralised"),
        "Built for ontologies that many parties edit and that drift over time.",
    ),
    Methodology(
        "neon", "NeOn",
        ("scenario selection", "reuse ontological resources",
         "reuse non-ontological resources", "re-engineering", "alignment", "evaluation"),
        ("reuse", "existing ontologies", "non-ontological resources",
         "thesauri", "databases", "networked"),
        "Scenario-based: its distinctive contribution is *reuse* of existing resources.",
    ),
    Methodology(
        "samod", "SAMOD",
        ("collect requirements", "build modelet", "merge", "test", "refactor"),
        ("agile", "iterative", "test driven", "small increments"),
        "Agile and test-first: each iteration produces a tested 'modelet'.",
    ),
]

_BY_ID = {m.id: m for m in METHODOLOGIES}


def recommend_methodology(brief: str) -> dict:
    """Score every methodology against a project brief and return the best fit.

    The scoring is transparent on purpose — it returns the signals that matched,
    so a student can argue with the recommendation instead of accepting it.
    """
    lowered = (brief or "").lower()
    scored = []
    for m in METHODOLOGIES:
        hits = [signal for signal in m.fits_when if signal in lowered]
        scored.append({"id": m.id, "name": m.name, "score": len(hits), "matched": hits})
    scored.sort(key=lambda row: (-row["score"], row["id"]))
    best = scored[0]
    return {
        "recommended": best["id"] if best["score"] else "methontology",
        "reason": best["matched"] or ["no distinctive signal; defaulting to the "
                                      "full-lifecycle method"],
        "ranking": scored,
    }


def methodology_table() -> list[dict]:
    return [
        {"id": m.id, "name": m.name, "phases": len(m.phases),
         "fits when": ", ".join(m.fits_when)}
        for m in METHODOLOGIES
    ]


# --------------------------------------------------------------------------- #
# Competency questions as executable tests
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompetencyQuestion:
    """A requirement, and the query that decides whether it is met.

    The `sparql` field is what makes a CQ an *engineering artefact* rather than a
    wish: it either returns rows over the ontology, or it does not.
    """

    id: str
    question: str
    sparql: str
    #: Which development step must be complete before this CQ can pass.
    requires: str = "taxonomy"


#: Competency questions for the African Wildlife Ontology (Chapters 1 and 4).
AWO_CQS = [
    CompetencyQuestion(
        "cq1", "Which animals are herbivores?",
        "SELECT ?c WHERE { ?c rdfs:subClassOf awo:Herbivore }", "taxonomy"),
    CompetencyQuestion(
        "cq2", "What does a giraffe eat?",
        """SELECT ?filler WHERE {
             awo:Giraffe rdfs:subClassOf ?r .
             ?r a owl:Restriction ; owl:onProperty awo:eats ; ?p ?filler .
             FILTER(?p != rdf:type && ?p != owl:onProperty)
           }""", "axioms"),
    CompetencyQuestion(
        "cq3", "Which classes are plants?",
        "SELECT ?c WHERE { ?c rdfs:subClassOf awo:Plant }", "taxonomy"),
    CompetencyQuestion(
        "cq4", "Which properties relate an animal to what it eats?",
        "SELECT ?p WHERE { ?p rdfs:domain awo:Animal }", "axioms"),
    CompetencyQuestion(
        "cq5", "Are plants and animals disjoint?",
        "SELECT ?a ?b WHERE { ?a owl:disjointWith ?b }", "axioms"),
    CompetencyQuestion(
        "cq6", "Which individuals are recorded?",
        "SELECT ?i WHERE { ?i a owl:NamedIndividual }", "instances"),
]


def check_cq(cq: CompetencyQuestion, store) -> dict:
    """Run one competency question. Answerable iff the query returns rows."""
    try:
        rows = store.select(cq.sparql)
    except Exception as exc:                       # a malformed CQ is a failed CQ
        return {"id": cq.id, "answerable": False, "rows": 0, "error": str(exc)}
    return {"id": cq.id, "question": cq.question, "answerable": bool(rows), "rows": len(rows)}


def cq_coverage(cqs: Iterable[CompetencyQuestion], store) -> dict:
    """Coverage = the fraction of competency questions the ontology can answer.

    This single number is the closest thing ontology engineering has to a test
    suite pass rate, and Chapter 5's methodologies are all, in effect, different
    strategies for raising it.
    """
    results = [check_cq(cq, store) for cq in cqs]
    answered = sum(1 for r in results if r["answerable"])
    return {
        "coverage": round(answered / len(results), 3) if results else 0.0,
        "answered": answered,
        "total": len(results),
        "results": results,
    }


# --------------------------------------------------------------------------- #
# §5.2  OntoClean
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MetaProperties:
    """OntoClean meta-properties for one class.

    ``rigidity``  ``+R`` essential to every instance · ``~R`` anti-rigid (essential
                  to none) · ``-R`` non-rigid
    ``identity``  ``+I`` carries an identity criterion · ``-I`` does not
    ``unity``     ``+U`` all instances are wholes · ``~U`` anti-unity · ``-U`` no unity
    ``dependence`` ``+D`` externally dependent · ``-D`` independent
    """

    rigidity: str
    identity: str = "-I"
    unity: str = "-U"
    dependence: str = "-D"


#: Tags for a small taxonomy. Roles (Student, Employee, Pet) are the classic
#: anti-rigid cases: nothing is *essentially* a student.
ONTOCLEAN_TAGS = {
    "Entity":       MetaProperties("+R", "-I", "-U", "-D"),
    "PhysicalObject": MetaProperties("+R", "+I", "+U", "-D"),
    "Person":       MetaProperties("+R", "+I", "+U", "-D"),
    "Animal":       MetaProperties("+R", "+I", "+U", "-D"),
    "Student":      MetaProperties("~R", "-I", "-U", "+D"),
    "Employee":     MetaProperties("~R", "-I", "-U", "+D"),
    "Pet":          MetaProperties("~R", "-I", "-U", "+D"),
    "AmountOfMatter": MetaProperties("+R", "-I", "~U", "-D"),
    "Clay":         MetaProperties("+R", "-I", "~U", "-D"),
    "Statue":       MetaProperties("+R", "+I", "+U", "-D"),
}

#: A taxonomy to audit: ``(subclass, superclass)`` pairs. Three of these are
#: ontologically wrong while remaining perfectly consistent to a DL reasoner.
TAXONOMY = [
    ("Person", "Entity"),
    ("Animal", "Entity"),
    ("PhysicalObject", "Entity"),
    ("Student", "Person"),          # fine: anti-rigid under rigid
    ("Person", "Student"),          # WRONG: anti-rigid cannot subsume rigid
    ("Employee", "Person"),         # fine
    ("Statue", "Clay"),             # WRONG: anti-unity cannot subsume unity
    ("Person", "Pet"),              # WRONG: dependent cannot subsume independent
]

ONTOCLEAN_CONSTRAINTS = [
    {
        "id": "anti-rigid-cannot-subsume-rigid",
        "statement": "An anti-rigid property (~R) cannot subsume a rigid one (+R).",
        "why": "If every person were essentially a student, nobody could ever graduate "
               "while remaining the same person.",
    },
    {
        "id": "anti-unity-cannot-subsume-unity",
        "statement": "A property with anti-unity (~U) cannot subsume one with unity (+U).",
        "why": "A statue is a whole; an amount of clay is not. Making the statue a kind of "
               "clay loses exactly the property that makes it a statue.",
    },
    {
        "id": "dependent-cannot-subsume-independent",
        "statement": "An externally dependent property (+D) cannot subsume an "
                     "independent one (-D).",
        "why": "Being a pet depends on an owner; being a person does not. A person is not "
               "a kind of pet.",
    },
    {
        "id": "incompatible-identity",
        "statement": "Properties with incompatible identity criteria cannot subsume "
                     "one another.",
        "why": "If the criteria for 'same X' and 'same Y' disagree, no instance can "
               "satisfy both.",
    },
]


def ontoclean_violations(taxonomy: Iterable[tuple[str, str]] | None = None,
                         tags: dict[str, MetaProperties] | None = None) -> list[dict]:
    """Find subsumption axioms that break an OntoClean constraint.

    Note what this catches that Chapters 3–4 cannot: every axiom here is
    logically consistent. A DL reasoner is perfectly happy with
    ``Person ⊑ Student``. OntoClean rejects it on *ontological* grounds — which
    is why §5.2 exists as a separate topic from §3.3.
    """
    taxonomy = TAXONOMY if taxonomy is None else list(taxonomy)
    tags = ONTOCLEAN_TAGS if tags is None else tags
    out = []
    for sub, sup in taxonomy:
        if sub not in tags or sup not in tags:
            continue
        child, parent = tags[sub], tags[sup]
        if parent.rigidity == "~R" and child.rigidity == "+R":
            out.append({
                "constraint": "anti-rigid-cannot-subsume-rigid",
                "axiom": f"{sub} <= {sup}",
                "detail": f"{sup} is anti-rigid (~R) but {sub} is rigid (+R)",
            })
        if parent.unity == "~U" and child.unity == "+U":
            out.append({
                "constraint": "anti-unity-cannot-subsume-unity",
                "axiom": f"{sub} <= {sup}",
                "detail": f"{sup} has anti-unity (~U) but {sub} has unity (+U)",
            })
        if parent.dependence == "+D" and child.dependence == "-D":
            out.append({
                "constraint": "dependent-cannot-subsume-independent",
                "axiom": f"{sub} <= {sup}",
                "detail": f"{sup} is dependent (+D) but {sub} is independent (-D)",
            })
    return out


# --------------------------------------------------------------------------- #
# Development steps, with prerequisites — the material for the chapter's MDP
# --------------------------------------------------------------------------- #
#: Each step: what it costs, what it needs first, and which CQ tier it unlocks.
#:
#: The prerequisites are the point. Chapter 5's methodologies disagree about
#: *order*, not about which activities exist, so the planning problem is about
#: precedence — and skipping a step does not merely cost quality, it makes later
#: steps unavailable.
DEVELOPMENT_STEPS = {
    "requirements":  {"cost": 0.10, "requires": (),                          "unlocks": ()},
    "competency_questions": {"cost": 0.10, "requires": ("requirements",),    "unlocks": ()},
    "reuse_search":  {"cost": 0.15, "requires": ("requirements",),           "unlocks": ()},
    "taxonomy":      {"cost": 0.20, "requires": ("competency_questions",),   "unlocks": ("taxonomy",)},
    "axioms":        {"cost": 0.25, "requires": ("taxonomy",),               "unlocks": ("axioms",)},
    "instances":     {"cost": 0.10, "requires": ("taxonomy",),               "unlocks": ("instances",)},
    "evaluation":    {"cost": 0.10, "requires": ("competency_questions", "taxonomy"), "unlocks": ()},
}


# --------------------------------------------------------------------------- #
# Building the ontology up in stages, so coverage can be *measured*
# --------------------------------------------------------------------------- #
#: Which triples belong to each development tier of the AWO.
def ontology_at_stage(completed: Iterable[str]):
    """The AWO restricted to what the completed development steps produced.

    Rather than *stipulating* that "doing the axioms step raises coverage",
    this builds the partial ontology and lets :func:`cq_coverage` measure it.
    The MDP in the agentic lab is then rewarded by a real measurement.
    """
    from rdflib import OWL, RDF, RDFS, Graph
    from oe_course import ontology as ont
    from oe_course.data import corpus

    completed = set(completed)
    full = ont.load_graph(corpus.get("awo").turtle)
    staged = Graph()
    for prefix, namespace in full.namespaces():
        staged.bind(prefix, namespace)

    individuals = set(full.subjects(RDF.type, OWL.NamedIndividual))
    restrictions = set(full.subjects(RDF.type, OWL.Restriction))
    axiom_predicates = {RDFS.domain, RDFS.range, OWL.disjointWith,
                        OWL.inverseOf, OWL.unionOf}

    def tier(s, p, o) -> str:
        """Which development step would have produced this triple."""
        if s in individuals:
            return "instances"
        if s in restrictions or o in restrictions or p in axiom_predicates:
            return "axioms"
        if p in (RDF.type, RDFS.label, RDFS.comment, RDFS.subClassOf):
            return "taxonomy"
        return "axioms"          # anything else is a further commitment

    for triple in full:
        if tier(*triple) in completed:
            staged.add(triple)
    return staged


def coverage_for_steps(completed: Iterable[str]) -> float:
    """Measured competency-question coverage after a set of development steps."""
    from oe_course.sparql import SparqlStore

    graph = ontology_at_stage(completed)
    store = SparqlStore(graph=graph)
    return cq_coverage(AWO_CQS, store)["coverage"]
