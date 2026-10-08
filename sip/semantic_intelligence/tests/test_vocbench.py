"""VocBench / Semantic Turkey translation: SKOS, ICV, search, alignment, I/O, KG lifting."""

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from semantic_intelligence.alignment.alignment import (Alignment, Cell, InvalidAlignmentRelation,
                                                       lexical_match, suggest_properties)
from semantic_intelligence.core.namespaces import SKOSXL
from semantic_intelligence.io.pipeline import TRANSFORMERS, export, run_pipeline
from semantic_intelligence.kg.lifting import ColumnMap, TableMapping, lift_table, project_lpg, resolve_entities
from semantic_intelligence.quality import icv
from semantic_intelligence.search.search import search_resource
from semantic_intelligence.skos.skos import LabelClash, PreconditionFailed, SkosService

EX = Namespace("http://ex.org/")
G = URIRef("urn:g")
THES = """@prefix : <http://ex.org/> . @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
:S a skos:ConceptScheme ; skos:prefLabel "Scheme"@en .
:animal a skos:Concept ; skos:prefLabel "animal"@en ; skos:inScheme :S ; skos:topConceptOf :S .
:mammal a skos:Concept ; skos:prefLabel "mammal"@en ; skos:inScheme :S ; skos:broader :animal .
:dog a skos:Concept ; skos:prefLabel "dog"@en ; skos:altLabel "hound"@en ; skos:inScheme :S ; skos:broader :mammal, :animal .
:cat a skos:Concept ; skos:prefLabel " cat"@en ; skos:inScheme :S .
:loose a skos:Concept ; skos:prefLabel "loose"@en .
:fish a skos:Concept ; skos:inScheme :S ; skos:topConceptOf :S ; skos:broader :animal .
"""


@pytest.fixture
def thes():
    return Graph().parse(data=THES, format="turtle")


def test_top_concepts_are_declared_with_scheme(thes):
    s = SkosService(thes)
    assert [n.iri for n in s.top_concepts([EX.S])] == [EX.animal, EX.fish]
    no_scheme = {n.iri for n in s.top_concepts()}
    assert EX.loose in no_scheme and EX.cat in no_scheme and EX.dog not in no_scheme
    kids = s.narrower_concepts(EX.animal)
    assert [n.iri for n in kids] == [EX.dog, EX.fish, EX.mammal]
    assert s.path_from_root(EX.dog, [EX.S]) == [[EX.animal, EX.dog], [EX.animal, EX.mammal, EX.dog]]


def test_create_concept_and_label_rules(thes):
    s = SkosService(thes)
    with pytest.raises(LabelClash):
        s.create_concept(EX.dog2, Literal("dog", lang="en"), [EX.S], G)
    with pytest.raises(LabelClash):                 # pref/alt clash
        s.create_concept(EX.hound, Literal("hound", lang="en"), [EX.S], G)
    cs = s.create_concept(EX.wolf, Literal("wolf", lang="en"), [EX.S], G, broader=EX.mammal)
    adds = {q[:3] for q in cs.additions}
    assert (EX.wolf, SKOS.broader, EX.mammal) in adds and (EX.wolf, SKOS.topConceptOf, EX.S) not in adds
    cs = s.set_pref_label(EX.dog, Literal("domestic dog", lang="en"), G)
    assert (EX.dog, SKOS.altLabel, Literal("dog", lang="en")) in {q[:3] for q in cs.additions}
    with pytest.raises(PreconditionFailed):
        s.delete_concept(EX.mammal, G)
    with pytest.raises(PreconditionFailed):
        s.add_broader(EX.animal, EX.dog, G)          # cycle


def test_skosxl_conversion_roundtrip(thes):
    s = SkosService(thes)
    n = iter(range(100))
    cs = s.to_skosxl(G, lambda k, l: URIRef(f"http://ex.org/xl{next(n)}"))
    g2 = thes + Graph()
    for q in cs.removals:
        g2.remove(q[:3])
    for q in cs.additions:
        g2.add(q[:3])
    assert not list(g2.subject_objects(SKOS.prefLabel)) and list(g2.subject_objects(SKOSXL.prefLabel))
    xl = SkosService(g2, lexicalization="skosxl")
    assert xl.pref_label(EX.dog) == "dog"
    back = xl.to_skos(G)
    for q in back.removals:
        g2.remove(q[:3])
    for q in back.additions:
        g2.add(q[:3])
    assert set(g2.objects(EX.dog, SKOS.prefLabel)) == {Literal("dog", lang="en")}


def test_icv_checks_and_fixes(thes):
    ctx = icv.Context(thes, "skos", "skos", ("en",), G)
    found = {f.check: f for f in icv.run_checks(ctx)}
    assert {"listDanglingConcepts", "listTopConceptsWithBroader", "listConceptsWithNoScheme",
            "listConceptsHierarchicalRedundancies", "listResourcesWithExtraSpacesInLabel",
            "listResourcesWithNoSKOSPrefLabel"} <= set(found)
    assert found["listDanglingConcepts"].resource == str(EX.cat)
    fix = icv.REGISTRY["listConceptsHierarchicalRedundancies"].fix(ctx)
    assert {q[:3] for q in fix.removals} == {(EX.dog, SKOS.broader, EX.animal)}
    trim = icv.REGISTRY["listResourcesWithExtraSpacesInLabel"].fix(ctx)
    assert (EX.cat, SKOS.prefLabel, Literal("cat", lang="en")) in {q[:3] for q in trim.additions}
    g = Graph()
    g.add((EX.a, SKOS.broader, EX.b)); g.add((EX.b, SKOS.broader, EX.a))
    for x in (EX.a, EX.b):
        g.add((x, RDF.type, SKOS.Concept))
    cyc = icv.run_checks(icv.Context(g, "skos", "skos"), ["listConceptsHierarchicalCycles"])
    assert cyc and cyc[0].severity == "blocker"


def test_search_modes(thes):
    hits = lambda t, m: {h.resource for h in search_resource(thes, t, mode=m, lexicalization="skos")}
    assert hits("ma", "startsWith") == {str(EX.mammal)}
    assert hits("AL", "contains") >= {str(EX.animal), str(EX.mammal)}
    assert hits("dog", "exact") == {str(EX.dog)}
    assert hits("dug", "fuzzy") == {str(EX.dog)}          # one substitution
    assert str(EX.dog) in hits("do", "fuzzy")             # value has one extra trailing char
    assert hits("dogs", "fuzzy") == set()                 # ST's fuzzy has no deletions
    assert hits("hound", "exact") == {str(EX.dog)}        # altLabel is a lexicalization
    with pytest.raises(ValueError):
        search_resource(thes, "x", use_lexicalizations=False)


def test_alignment_relation_table_and_apply():
    assert suggest_properties("concept", "=")[0] == SKOS.exactMatch
    assert suggest_properties("cls", "<")[0] == RDFS.subClassOf
    with pytest.raises(InvalidAlignmentRelation):
        suggest_properties("cls", ">")
    al = Alignment("http://a", "http://b", [Cell(EX.a, URIRef("http://b/x"), 0.9, "="),
                                           Cell(EX.c, URIRef("http://b/y"), 0.4, ">")])
    al.accept(al.cells[0], lambda e: "cls")
    al.accept(al.cells[1], lambda e: "cls")
    assert al.cells[0].status == "accepted" and al.cells[1].status == "error"
    cs, rep = al.apply_validation(G, Graph(), lambda e: "cls")
    assert [q[:3] for q in cs.additions] == [(EX.a, OWL.equivalentClass, URIRef("http://b/x"))]
    back = Alignment.parse(al.to_graph().serialize(format="xml"), "xml")
    assert len(back.cells) == 2 and back.reverse().cells[1].relation == "<"


def test_lexical_matcher():
    l, r = Graph(), Graph()
    l.add((EX.Car, RDFS.label, Literal("Motor car"))); l.add((EX.Car, RDF.type, OWL.Class))
    r.add((URIRef("http://b/Car"), RDFS.label, Literal("motor car")))
    cells = lexical_match(l, r, [EX.Car], [URIRef("http://b/Car")])
    assert cells and cells[0].measure == 1.0


def test_transformers_and_export(thes):
    assert len(TRANSFORMERS) == 8
    out = run_pipeline(thes, [{"filter": {"factoryId": "PropertyNormalizerTransformer",
                                          "configuration": {"normalizingProperty": str(RDFS.label),
                                                            "propertiesBeingNormalized": [str(SKOS.prefLabel)]}}}])
    assert not list(out.subject_objects(SKOS.prefLabel)) and list(out.subject_objects(RDFS.label))
    assert list(thes.subject_objects(SKOS.prefLabel))          # the project copy is untouched
    assert "Scheme" in export(thes, "turtle")
    with pytest.raises(KeyError):
        run_pipeline(thes, [{"filter": {"factoryId": "Nope"}}])


def test_tabular_lifting_and_resolution():
    onto = Graph()
    onto.add((EX.Org, RDF.type, OWL.Class)); onto.add((EX.founded, RDF.type, OWL.DatatypeProperty))
    m = TableMapping(str(EX.Org), "http://ex.org/kg/{id}",
                     [ColumnMap("year", str(EX.founded), "data", str(XSD.integer))], "name")
    triples, warn = lift_table("id,name,year\no1,Acme Inc,1990\no2,ACME,1990\no3,Zeta,nineteen\n", m, onto)
    kg = Graph()
    for t in triples:
        kg.add(t)
    assert (URIRef("http://ex.org/kg/o1"), EX.founded, Literal("1990", datatype=XSD.integer)) in kg
    assert len(warn) == 1 and "nineteen" in warn[0]
    dups = resolve_entities(kg, key_properties=[EX.founded])
    assert [(d.a, d.b) for d in dups] == [(URIRef("http://ex.org/kg/o1"), URIRef("http://ex.org/kg/o2"))]
    bad = TableMapping(str(EX.Nope), "http://ex.org/kg/{missing}")
    with pytest.raises(ValueError, match="unknown column"):
        lift_table("id\n1\n", bad, onto)
    lpg = project_lpg(kg, onto)
    assert len(lpg["nodes"]) == 3 and lpg["nodes"][0]["labels"] == ["Org"]
