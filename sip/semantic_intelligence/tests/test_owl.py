"""Protégé translation: axiom view, Manchester syntax, hierarchies, frames, refactoring,
reasoning and justifications."""

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from semantic_intelligence.owl import manchester, refactor
from semantic_intelligence.owl.frames import class_frame, render_axiom, resource_view
from semantic_intelligence.owl.hierarchy import ClassHierarchy, PropertyHierarchy
from semantic_intelligence.owl.model import (And, Axiom, Card, Not, Only, Some, axiom_triples,
                                             axioms, ce_triples, parse_ce, triples_to_graph)
from semantic_intelligence.owl.rendering import ShortFormProvider, quote
from semantic_intelligence.reasoning.explanation import Entailment, explain
from semantic_intelligence.reasoning.reasoner import ReasonerManager, ReasonerStatus

EX = Namespace("http://ex.org/")
TTL = """@prefix : <http://ex.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:Vehicle a owl:Class . :Car a owl:Class ; rdfs:label "Car"@en ; rdfs:subClassOf :Vehicle .
:Wheel a owl:Class ; rdfs:label "Wheel"@en, "Roue"@fr . :Engine a owl:Class ; rdfs:label "Combustion engine"@en .
:hasPart a owl:ObjectProperty ; rdfs:label "has part"@en . :hasWheel a owl:ObjectProperty ; rdfs:subPropertyOf :hasPart .
:weight a owl:DatatypeProperty . :red a owl:NamedIndividual .
:Car rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :hasWheel ; owl:qualifiedCardinality "4"^^xsd:nonNegativeInteger ; owl:onClass :Wheel ] .
:SportsCar a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( :Car [ a owl:Restriction ; owl:onProperty :hasPart ; owl:someValuesFrom :Engine ] ) ] .
"""


@pytest.fixture
def g():
    return Graph().parse(data=TTL, format="turtle")


def test_axiom_view_reads_restrictions(g):
    kinds = {a.kind for a in axioms(g)}
    assert {"SubClassOf", "EquivalentClasses", "Declaration", "SubPropertyOf",
            "AnnotationAssertion"} <= kinds
    card = [a for a in axioms(g) if a.kind == "SubClassOf" and isinstance(a.args[1], Card)][0]
    assert card.args[1] == Card("exactly", 4, EX.hasWheel, EX.Wheel)


def test_axiom_removal_is_exact(g):
    ax = Axiom("SubClassOf", (EX.Car, Card("exactly", 4, EX.hasWheel, EX.Wheel)))
    triples = axiom_triples(ax, g)
    assert len(triples) == 5                 # subClassOf + 4 restriction triples
    for t in triples:
        g.remove(t)
    assert not [t for t in g if isinstance(t[0], BNode) and (None, None, t[0]) not in g
                and t[0] not in {s for s in g.subjects(OWL.intersectionOf, None)}]


def test_symmetric_axioms_are_sets():
    assert Axiom("EquivalentClasses", (EX.A, EX.B)) == Axiom("EquivalentClasses", (EX.B, EX.A))


@pytest.mark.parametrize("text", [
    "'has part' some Wheel and hasPart exactly 4 Wheel",
    "Car and ('has part' some 'Combustion engine' or not (hasPart value red))",
    "weight some xsd:decimal[>= 10, < 2000.5]", "inverse (hasPart) only Car",
    "hasPart min 2", "{red}", "weight value 12", "Car that hasPart some Wheel",
    "hasPart some (Wheel or Engine)", "not Car"])
def test_manchester_roundtrip(g, text):
    sfp = ShortFormProvider(g)
    ce = manchester.parse(text, sfp)
    assert manchester.parse(manchester.render(ce, sfp), sfp) == ce
    out = []
    root = ce_triples(ce, out)
    assert parse_ce(triples_to_graph(out + list(g)), root) == ce


def test_manchester_errors_carry_expected_sets(g):
    sfp = ShortFormProvider(g)
    with pytest.raises(manchester.ManchesterError) as e:
        manchester.parse("hasPart sme Wheel", sfp)
    assert {"some", "only", "min"} <= e.value.expected
    err = manchester.check("Car and", sfp)
    assert err.class_name_expected and err.object_property_name_expected


def test_manchester_completion(g):
    sfp = ShortFormProvider(g)
    word, props = manchester.complete("hasPart so", 10, sfp)
    assert word == "so" and [p.text for p in props] == ["some"]
    _, props = manchester.complete("hasPart some W", 14, sfp)
    assert "Wheel" in [p.text for p in props]


def test_rendering_language_and_quoting(g):
    sfp = ShortFormProvider(g, languages=("fr", "en"))
    assert sfp.render(EX.Wheel) == "Roue"
    assert quote("has part") == "'has part'" and quote("Car") == "Car" and quote("and") == "'and'"
    assert sfp.resolve("'has part'") == [EX.hasPart]
    assert EX.Engine in sfp.find("comb")


def test_class_hierarchy_uses_equivalent_conjuncts(g):
    h = ClassHierarchy(g)
    assert EX.SportsCar in h.children(EX.Car)          # defined class under its genus
    assert EX.Vehicle in h.roots() and EX.Car not in h.roots()
    assert h.paths_to_root(EX.SportsCar) == [[OWL.Thing, EX.Vehicle, EX.Car, EX.SportsCar]]
    p = PropertyHierarchy(g, "object")
    assert p.children(EX.hasPart) == [EX.hasWheel] and EX.hasPart in p.roots()


def test_class_frame_sections(g):
    f = class_frame(g, EX.SportsCar, ShortFormProvider(g))
    assert f["Equivalent To"][0]["text"] == "Car and 'has part' some 'Combustion engine'"
    f2 = class_frame(g, EX.Car, ShortFormProvider(g))
    assert any("exactly 4" in r["text"] for r in f2["SubClass Of"])


def test_resource_view_scopes(g):
    staged = Graph()
    staged.add((EX.Car, RDFS.comment, Literal("proposed")))
    dele = Graph()
    dele.add((EX.Car, RDFS.label, Literal("Car", lang="en")))
    v = resource_view(EX.Car, {"local": g, "staged": staged, "del_staged": dele},
                      ShortFormProvider(g)).as_dict()
    assert v["role"] == "cls" and list(v["sections"]) == ["types", "classaxioms", "lexicalizations", "properties"]
    scopes = {x["value"]: x["scope"] for sec in v["sections"].values() for x in sec}
    assert scopes["proposed"] == "staged" and scopes["Car"] == "del_staged"


# ------------------------------------------------------------------ refactoring
def test_rename_merge_delete(g):
    cs = refactor.rename_iri(g, EX.Wheel, EX.Tyre, URIRef("urn:g"))
    assert all(EX.Wheel not in q[:3] for q in cs.additions) and len(cs.removals) == len(cs.additions)
    g.add((EX.Auto, RDF.type, OWL.Class))
    g.add((EX.Auto, RDFS.label, Literal("Auto", lang="en")))
    m = refactor.merge_entities(g, [EX.Auto], EX.Car, URIRef("urn:g"))
    adds = {q[:3] for q in m.additions}
    assert (EX.Car, SKOS.altLabel, Literal("Auto", lang="en")) in adds
    d = refactor.delete_entities(g, [EX.Engine], URIRef("urn:g"))
    h = g + Graph()
    for q in d.removals:
        h.remove(q[:3])
    assert (EX.Engine, None, None) not in h and (None, None, EX.Engine) not in h
    orphans = [b for b in set(h.subjects()) if isinstance(b, BNode) and (None, None, b) not in h]
    assert not orphans                       # no orphan blank-node structure left behind


def test_convert_defined_primitive_closure_siblings(g):
    G = URIRef("urn:g")
    cs = refactor.convert_to_defined(g, EX.Car, G)
    assert any(q[1] == OWL.equivalentClass for q in cs.additions)
    cs2 = refactor.convert_to_primitive(g, EX.SportsCar, G)
    assert {q[2] for q in cs2.additions if q[1] == RDFS.subClassOf and q[0] == EX.SportsCar} >= {EX.Car}
    g2 = Graph().parse(data=TTL, format="turtle")
    g2.add((EX.Car, RDFS.subClassOf, BNode("x")))
    cl = refactor.create_closure_axiom(g, EX.SportsCar, G)
    assert any(q[1] == OWL.allValuesFrom for q in cl.additions)
    g.add((EX.Truck, RDF.type, OWL.Class))
    g.add((EX.Truck, RDFS.subClassOf, EX.Vehicle))
    sib = refactor.make_primitive_siblings_disjoint(g, EX.Car, G)
    assert any(q[2] == OWL.AllDisjointClasses or q[1] == OWL.disjointWith for q in sib.additions)


def test_render_axiom(g):
    sfp = ShortFormProvider(g)
    assert render_axiom(Axiom("SubClassOf", (EX.Car, Some(EX.hasPart, EX.Wheel))), sfp) == \
        "Car SubClassOf 'has part' some Wheel"


# ------------------------------------------------------------------ reasoning
INCOH = TTL + """
:Plant a owl:Class . :Vehicle owl:disjointWith :Plant . :Triffid a owl:Class ; rdfs:subClassOf :Car, :Plant .
:rex a :Car ; :hasPart :e1 . :e1 a :Engine .
"""


def test_reasoner_status_and_unsat():
    g = Graph().parse(data=INCOH, format="turtle")
    rev = {"n": 0}
    rm = ReasonerManager(revision=lambda: rev["n"])
    assert rm.status == ReasonerStatus.REASONER_NOT_INITIALIZED
    c = rm.classify(g)
    assert rm.status == ReasonerStatus.INITIALIZED and c.profile == "OWL2-RL"
    assert c.unsatisfiable == [EX.Triffid]
    assert EX.Triffid in c.hierarchy.children(OWL.Nothing)
    assert (EX.rex, RDF.type, EX.SportsCar) in c.inferred          # RL handles the intersection
    rev["n"] = 1
    assert rm.status == ReasonerStatus.OUT_OF_SYNC
    g.add((EX.t1, RDF.type, EX.Triffid))
    rm.classify(g)
    assert rm.status == ReasonerStatus.INCONSISTENT


def test_justifications():
    g = Graph().parse(data=INCOH, format="turtle")
    r = explain(g, Entailment("unsatisfiable", EX.Triffid))
    assert r.complete and len(r.justifications) == 1 and r.profile == "OWL2-RL"
    kinds = sorted(a.kind for a in r.justifications[0])
    assert kinds == ["DisjointClasses", "SubClassOf", "SubClassOf", "SubClassOf"]
    g.add((EX.Car, RDFS.subClassOf, EX.Wheel))
    g.add((EX.Wheel, RDFS.subClassOf, EX.Vehicle))
    r2 = explain(g, Entailment("subclass", EX.SportsCar, EX.Vehicle))
    assert len(r2.justifications) == 2 and r2.complete      # via Car→Vehicle and Car→Wheel→Vehicle
