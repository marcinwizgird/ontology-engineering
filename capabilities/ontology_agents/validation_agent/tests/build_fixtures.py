"""Write ``tests/fixtures/<check_id>/{positive,negative,near_miss}.ttl`` for every S1a check.

    python tests/build_fixtures.py

* ``positive``: the check must fire.
* ``negative``: a clean variant; the check must not fire.
* ``near_miss``: looks like the defect but is legal; the check must not fire (measures
  precision).

Optional header comments steer the run: ``# declared: <level>`` sets the declared level,
``# shapes: shapes.ttl`` names a shapes file in the same directory. Info-only checks with
no mutation operator (DL-08, METRIC-02) have a positive fixture only.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent / "fixtures"

P = """@prefix ex: <https://example.org/fx#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
<https://example.org/fx> a owl:Ontology .
"""
C2 = "ex:A a owl:Class .\nex:B a owl:Class .\n"

FIXTURES: dict[str, dict[str, str]] = {
    "SYN-01": {
        "positive": P + "ex:A a owl:Class ;\n    rdfs:subClassOf ex:B\n",   # truncated statement
        "negative": P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "near_miss": P + C2 + "ex:A rdfs:comment \"a statement ending in a dot. \" .\n",
    },
    "SYN-02": {
        "positive": P + "<https://example.org/fx#Rail Vehicle> a owl:Class .\n",
        "negative": P + "ex:RailVehicle a owl:Class .\n",
        "near_miss": P + "@base <https://example.org/fx/> .\n<RailVehicle> a owl:Class .\n"
                         "<https://example.org/fx#Rail%20Vehicle> a owl:Class .\n",
    },
    "SYN-03": {
        "positive": P + "ex:p a owl:DatatypeProperty .\nex:x ex:p \"abc\"^^xsd:integer .\n",
        "negative": P + "ex:p a owl:DatatypeProperty .\nex:x ex:p \"42\"^^xsd:integer .\n",
        "near_miss": P + "ex:p a owl:DatatypeProperty .\nex:x ex:p \"abc\" ; ex:p \"+042\"^^xsd:integer .\n",
    },
    "SYN-06": {
        "positive": P + C2 + "ex:p a owl:ObjectProperty .\n"
                    "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:someValuesFrom ex:B ] .\n",
        "negative": P + C2 + "ex:p a owl:ObjectProperty .\n"
                    "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] .\n",
        "near_miss": P + C2 + "ex:p a owl:ObjectProperty .\n"
                     "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;\n"
                     "    owl:maxQualifiedCardinality \"1\"^^xsd:nonNegativeInteger ; owl:onClass ex:B ] .\n",
    },
    "DECL-01": {
        "positive": P + "ex:A a owl:Class ; rdfs:subClassOf ex:Undeclared .\n",
        "negative": P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "near_miss": P + "ex:A a owl:Class ; rdfs:subClassOf ex:B .\nex:B a rdfs:Class .\n"
                         "ex:c a skos:Concept .\nex:A rdfs:subClassOf owl:Thing .\n",
    },
    "DECL-02": {
        "positive": P + C2 + "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:undeclared ; owl:someValuesFrom ex:B ] .\n",
        "negative": P + C2 + "ex:p a owl:ObjectProperty .\n"
                    "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] .\n",
        "near_miss": P + C2 + "ex:t a owl:TransitiveProperty .\nex:note a owl:AnnotationProperty .\n"
                     "ex:A ex:note \"x\" ; skos:prefLabel \"a\"@en ; dcterms:source ex:B .\n"
                     "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:t ; owl:someValuesFrom ex:B ] .\n",
    },
    "DECL-03": {
        "positive": P.replace("<https://example.org/fx> a owl:Ontology .\n", "") + C2,
        "negative": P + C2,
        "near_miss": P + C2 + "<https://example.org/fx> owl:imports <https://example.org/other> .\n",
    },
    "DECL-04": {
        "positive": P + "ex:A a owl:class .\n",
        "negative": P + "ex:A a owl:Class .\n",
        "near_miss": P + "ex:A a owl:Class ; rdfs:label \"owl:class\" .\nex:l a rdf:List ; rdf:_1 ex:A .\n",
    },
    "DL-02": {
        "positive": P + C2 + "ex:p a owl:ObjectProperty .\nex:x ex:p ex:A .\n",
        "negative": P + C2 + "ex:p a owl:ObjectProperty .\nex:x ex:p ex:y .\n",
        "near_miss": P + C2 + "ex:p a owl:ObjectProperty .\nex:A a owl:NamedIndividual .\nex:x ex:p ex:A .\n"
                     "ex:B rdfs:seeAlso ex:A .\n",
    },
    "DL-08": {
        "positive": P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
    },
    "RSN-01": {
        "positive": P + C2 + "ex:A owl:disjointWith ex:B .\nex:x a ex:A , ex:B .\n",
        "negative": P + C2 + "ex:A owl:disjointWith ex:B .\nex:x a ex:A .\nex:y a ex:B .\n",
        "near_miss": P + C2 + "ex:C a owl:Class ; rdfs:subClassOf ex:A , ex:B .\nex:x a ex:A , ex:B .\n",
    },
    "RSN-02": {
        "positive": P + C2 + "ex:B rdfs:subClassOf ex:A .\nex:A owl:disjointWith ex:B .\n",
        "negative": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C rdfs:subClassOf ex:A .\n"
                    "ex:B owl:disjointWith ex:C .\n",
        "near_miss": P + C2 + "ex:C a owl:Class .\nex:A owl:disjointWith ex:B .\n"
                     "ex:C rdfs:subClassOf [ a owl:Class ; owl:unionOf ( ex:A ex:B ) ] .\n",
    },
    "RSN-08": {
        "positive": P + C2 + "ex:p a owl:ObjectProperty .\n"
                    "ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] .\n",
        "negative": P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "near_miss": P + C2 + "ex:p a owl:ObjectProperty .\n"
                     "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] rdfs:subClassOf ex:A .\n",
    },
    "SHC-02": {
        "positive": "# shapes: shapes.ttl\n" + P + C2 + "ex:x a ex:A .\n",
        "negative": "# shapes: shapes.ttl\n" + P + C2 + "ex:p a owl:DatatypeProperty .\nex:x a ex:A ; ex:p \"v\" .\n",
        "near_miss": "# shapes: shapes.ttl\n" + P + C2 + "ex:p a owl:DatatypeProperty .\nex:y a ex:B .\n",
    },
    "SHC-08": {
        "positive": P + "ex:A a owl:Class ; skos:definition \"An a.\"@en .\n",
        "negative": P + "ex:A a owl:Class ; rdfs:label \"a\"@en ; skos:definition \"An a.\"@en .\n",
        "near_miss": P + "ex:A a owl:Class ; rdfs:label \"a\"@en , \"ein A\"@de ; skos:definition \"An a.\"@en .\n"
                         "[] a owl:Class ; owl:unionOf ( ex:A ) .\n",
    },
    "HIER-01": {
        "positive": P + C2 + "ex:A rdfs:subClassOf ex:B .\nex:B rdfs:subClassOf ex:A .\n",
        "negative": P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "near_miss": P + C2 + "ex:A rdfs:subClassOf ex:A .\nex:A owl:equivalentClass ex:B .\n",
    },
    "HIER-02": {
        "positive": P + C2 + "ex:fido a ex:A .\nex:fido rdfs:subClassOf ex:B .\n",
        "negative": P + C2 + "ex:fido a ex:A .\nex:A rdfs:subClassOf ex:B .\n",
        "near_miss": P + C2 + "ex:C a owl:Class ; rdfs:subClassOf ex:B .\nex:fido a ex:C .\n",
    },
    "HIER-05": {
        "positive": P + C2 + "ex:C a owl:Class .\nex:C rdfs:subClassOf ex:B .\nex:B rdfs:subClassOf ex:A .\n"
                    "ex:C owl:disjointWith ex:A .\n",
        "negative": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C rdfs:subClassOf ex:A .\n"
                    "ex:B owl:disjointWith ex:C .\n",
        "near_miss": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C owl:disjointWith ex:A .\n"
                     "[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:C ) .\n",
    },
    "HIER-08": {
        "positive": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C rdfs:subClassOf ex:A .\n",
        "negative": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C rdfs:subClassOf ex:A .\n"
                    "[] a owl:AllDisjointClasses ; owl:members ( ex:B ex:C ) .\n",
        "near_miss": P + C2 + "ex:C a owl:Class .\nex:B rdfs:subClassOf ex:A .\nex:C rdfs:subClassOf ex:B .\n",
    },
    "PROP-01": {
        "positive": P + C2 + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A .\n",
        "negative": P + C2 + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A ; rdfs:range ex:B .\n",
        "near_miss": P + C2 + "ex:note a owl:AnnotationProperty .\n"
                     "ex:d a owl:DatatypeProperty ; rdfs:domain ex:A ; rdfs:range xsd:string .\n",
    },
    "LEX-01": {
        "positive": P + "ex:A a owl:Class .\n",
        "negative": P + "ex:A a owl:Class ; rdfs:label \"a\"@en .\n",
        "near_miss": P + "ex:A a owl:Class ; skos:prefLabel \"a\"@en .\nex:A rdfs:subClassOf owl:Thing .\n",
    },
    "LEX-02": {
        "positive": P + "ex:A a owl:Class ; rdfs:label \"a\"@en .\n",
        "negative": P + "ex:A a owl:Class ; rdfs:label \"a\"@en ; skos:definition \"An a.\"@en .\n",
        "near_miss": P + "ex:A a owl:Class ; rdfs:comment \"An a.\"@en .\n"
                         "ex:p a owl:ObjectProperty .\n",
    },
    "SKOS-05": {
        "positive": P + "ex:a a skos:Concept ; skos:broader ex:b .\nex:b a skos:Concept ; skos:broader ex:a .\n",
        "negative": P + "ex:a a skos:Concept ; skos:broader ex:b .\nex:b a skos:Concept .\n",
        "near_miss": P + "ex:a a skos:Concept ; skos:broader ex:b ; skos:related ex:b .\n"
                         "ex:b a skos:Concept ; skos:narrower ex:a ; skos:related ex:a .\n",
    },
    "META-01": {
        "positive": P + C2,
        "negative": P + C2 + "<https://example.org/fx> dcterms:title \"Fx\"@en ;\n"
                    "    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;\n"
                    "    owl:versionIRI <https://example.org/fx/1.0> .\n",
        "near_miss": P + C2 + "<https://example.org/fx> <http://purl.org/dc/elements/1.1/title> \"Fx\" ;\n"
                     "    <http://creativecommons.org/ns#license> <https://creativecommons.org/licenses/by/4.0/> ;\n"
                     "    owl:versionInfo \"1.0\" .\n",
    },
    "METRIC-01": {
        "positive": "# declared: formal-ontology\n" + P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "negative": "# declared: taxonomy\n" + P + C2 + "ex:A rdfs:subClassOf ex:B .\n",
        "near_miss": "# declared: taxonomy\n" + P + C2 + "ex:A rdfs:subClassOf ex:B .\nex:A owl:disjointWith ex:C .\n"
                     "ex:C a owl:Class .\n",
    },
    "METRIC-02": {
        "positive": P + C2,
    },
}

SHAPES = {
    "SHC-02": """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/fx#> .
ex:AShape a sh:NodeShape ; sh:targetClass ex:A ;
    sh:property [ sh:path ex:p ; sh:minCount 1 ] .
""",
}


def build() -> int:
    n = 0
    for cid, variants in FIXTURES.items():
        d = HERE / cid
        d.mkdir(parents=True, exist_ok=True)
        for name, text in variants.items():
            (d / f"{name}.ttl").write_text(text, encoding="utf-8")
            n += 1
        if cid in SHAPES:
            (d / "shapes.ttl").write_text(SHAPES[cid], encoding="utf-8")
    return n


if __name__ == "__main__":
    print(f"wrote {build()} fixtures under {HERE}")
