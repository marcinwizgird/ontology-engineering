"""Chapter 1 toolkit — the artefacts behind the Chapter 1 notebooks.

Keet's Chapter 1 motivates ontologies with prose about integration and quality.
This module makes that argument *runnable*: two hospitals with incompatible
schemas, an alignment to a shared ontology, a reasoner, and a query whose answer
changes from wrong to right. Students measure the difference rather than being
told about it.

Nothing here needs a network, a database, or Java: the "databases" are RDF
graphs and the reasoner is ``owlrl``'s pure-Python OWL 2 RL implementation.
"""

from __future__ import annotations

import rdflib
from rdflib import Graph

__all__ = [
    "HOSPITAL_A",
    "HOSPITAL_B",
    "SHARED_ONTOLOGY",
    "ALIGNMENT",
    "naive_union",
    "integrated",
    "cardiac_patients",
    "integration_report",
    "DEFINITIONS",
    "definition_scorecard",
]

_PREFIXES = """
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix a:    <http://example.org/hospitalA#> .
@prefix b:    <http://example.org/hospitalB#> .
@prefix med:  <http://example.org/med#> .
"""

# --------------------------------------------------------------------------- #
# Two source systems that disagree about everything except the world
# --------------------------------------------------------------------------- #
#: Hospital A: patients, ICD-ish codes, one row per encounter.
HOSPITAL_A = _PREFIXES + """
a:pat001 a a:Patient ; a:mrn "A-001" ; a:hasDiagnosis a:dx_I21 .
a:pat002 a a:Patient ; a:mrn "A-002" ; a:hasDiagnosis a:dx_J45 .
a:pat003 a a:Patient ; a:mrn "A-003" ; a:hasDiagnosis a:dx_I50 .

a:dx_I21 a a:Diagnosis ; a:code "I21" ; rdfs:label "acute myocardial infarction"@en .
a:dx_J45 a a:Diagnosis ; a:code "J45" ; rdfs:label "asthma"@en .
a:dx_I50 a a:Diagnosis ; a:code "I50" ; rdfs:label "heart failure"@en .
"""

#: Hospital B: "clients", free-text conditions, a different class name.
HOSPITAL_B = _PREFIXES + """
b:person77 a b:Client ; b:ref "B-77" ; b:condition b:cond_heartattack .
b:person78 a b:Client ; b:ref "B-78" ; b:condition b:cond_fracture .
b:person79 a b:Client ; b:ref "B-79" ; b:condition b:cond_cardiomyopathy .

b:cond_heartattack    a b:Condition ; rdfs:label "heart attack"@en .
b:cond_fracture       a b:Condition ; rdfs:label "fractured femur"@en .
b:cond_cardiomyopathy a b:Condition ; rdfs:label "cardiomyopathy"@en .
"""

#: The shared conceptualisation both systems are *about*.
SHARED_ONTOLOGY = _PREFIXES + """
med:Patient   a owl:Class ; rdfs:label "patient"@en .
med:Disorder  a owl:Class ; rdfs:label "disorder"@en .

med:CardiacDisorder a owl:Class ; rdfs:label "cardiac disorder"@en ;
    rdfs:subClassOf med:Disorder .
med:MyocardialInfarction a owl:Class ; rdfs:label "myocardial infarction"@en ;
    rdfs:subClassOf med:CardiacDisorder .
med:HeartFailure a owl:Class ; rdfs:label "heart failure"@en ;
    rdfs:subClassOf med:CardiacDisorder .
med:Cardiomyopathy a owl:Class ; rdfs:label "cardiomyopathy"@en ;
    rdfs:subClassOf med:CardiacDisorder .
med:Asthma a owl:Class ; rdfs:label "asthma"@en ;
    rdfs:subClassOf med:Disorder .
med:Fracture a owl:Class ; rdfs:label "fracture"@en ;
    rdfs:subClassOf med:Disorder .

med:hasDisorder a owl:ObjectProperty ; rdfs:label "has disorder"@en ;
    rdfs:domain med:Patient ; rdfs:range med:Disorder .
"""

#: The alignment: how each source's vocabulary maps into the shared ontology.
#: This is the artefact that does the integration work, and it is *small*.
ALIGNMENT = _PREFIXES + """
a:Patient rdfs:subClassOf med:Patient .
b:Client  rdfs:subClassOf med:Patient .

a:hasDiagnosis rdfs:subPropertyOf med:hasDisorder .
b:condition    rdfs:subPropertyOf med:hasDisorder .

a:dx_I21 a med:MyocardialInfarction .
a:dx_J45 a med:Asthma .
a:dx_I50 a med:HeartFailure .

b:cond_heartattack    a med:MyocardialInfarction .
b:cond_fracture       a med:Fracture .
b:cond_cardiomyopathy a med:Cardiomyopathy .
"""

CARDIAC_QUERY = """
PREFIX med: <http://example.org/med#>
SELECT ?patient ?disorder WHERE {
  ?patient a med:Patient ;
           med:hasDisorder ?disorder .
  ?disorder a med:CardiacDisorder .
}
"""


def naive_union() -> Graph:
    """Both hospitals' data in one graph — the "just put it in a data lake" move."""
    g = Graph()
    g.parse(data=HOSPITAL_A, format="turtle")
    g.parse(data=HOSPITAL_B, format="turtle")
    return g


def integrated(reason: bool = True) -> Graph:
    """Sources + shared ontology + alignment, optionally materialised.

    With ``reason=False`` you can see that the alignment alone is not enough:
    the axioms are present but nothing has drawn the consequences yet.
    """
    g = naive_union()
    g.parse(data=SHARED_ONTOLOGY, format="turtle")
    g.parse(data=ALIGNMENT, format="turtle")
    if reason:
        import owlrl

        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    return g


def cardiac_patients(graph: Graph) -> list[tuple[str, str]]:
    """Answer the competency question: which patients have a cardiac disorder?"""
    return sorted(
        (str(row.patient), str(row.disorder)) for row in graph.query(CARDIAC_QUERY)
    )


def integration_report() -> dict:
    """The three-way comparison the notebook tabulates.

    The point of the middle row: adding the alignment changes the *graph* but
    not the *answers*. Integration is the alignment **plus** the entailment step.
    """
    lake = naive_union()
    aligned = integrated(reason=False)
    full = integrated(reason=True)
    expected = 4  # pat001 (MI), pat003 (heart failure), person77 (MI), person79 (cardiomyopathy)
    rows = []
    for name, g in [
        ("raw union (no ontology)", lake),
        ("+ shared ontology + alignment, no reasoner", aligned),
        ("+ OWL 2 RL entailment", full),
    ]:
        answers = cardiac_patients(g)
        rows.append(
            {
                "configuration": name,
                "triples": len(g),
                "patients_found": len({p for p, _ in answers}),
                "recall": round(len({p for p, _ in answers}) / expected, 2),
            }
        )
    return {"expected_patients": expected, "rows": rows}


# --------------------------------------------------------------------------- #
# Section 1.3.1 — "the definition game", made checkable
# --------------------------------------------------------------------------- #
#: Each historical definition of "ontology", paired with a property you can
#: actually test on an artefact. The exercise is to notice that they disagree:
#: the same file is an ontology under one definition and not under another.
DEFINITIONS = [
    {
        "id": "gruber-1993",
        "gloss": "an explicit specification of a conceptualisation",
        "test": lambda m: m["classes"] > 0 and m["annotations"] > 0,
        "reads_as": "there are named, documented terms",
    },
    {
        "id": "borst-1997",
        "gloss": "a formal specification of a shared conceptualisation",
        "test": lambda m: m["classes"] > 0 and m["logical_axioms"] > 0,
        "reads_as": "the terms carry at least some logical commitment",
    },
    {
        "id": "guarino-1998",
        "gloss": "a logical theory accounting for the intended meaning of a vocabulary",
        "test": lambda m: m["restrictions"] + m["disjointness_axioms"] > 0,
        "reads_as": "meaning is constrained beyond mere subsumption",
    },
    {
        "id": "reasoner-pragmatic",
        "gloss": "something a reasoner can derive non-trivial consequences from",
        "test": lambda m: m["restrictions"] + m["disjointness_axioms"]
        + m["property_characteristics"] > 1,
        "reads_as": "there is enough logic for classification to do work",
    },
]


def definition_scorecard(graphs: dict[str, Graph]) -> list[dict]:
    """Apply every definition to every artefact: who counts as an ontology?"""
    from oe_course.ontology import graph_metrics

    rows = []
    for name, g in graphs.items():
        m = graph_metrics(g)
        row = {"artefact": name}
        row.update({d["id"]: d["test"](m) for d in DEFINITIONS})
        rows.append(row)
    return rows
