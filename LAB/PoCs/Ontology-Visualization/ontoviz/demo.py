"""Demo platform: a small *fleet* project in review, and optionally *fibo*.

``fleet`` exercises every overlay through real SIP operations:

* stable content loaded by an ontologist and accepted by a validator;
* individuals in the knowledge graph;
* three commits from a machine principal (``modeler@fleet``) left *staged*: a new class,
  a new restriction and a removed subclass axiom;
* an equivalence that owlrl turns into an inferred superclass, a class made
  unsatisfiable by a disjointness, classes without labels (ICV findings);
* competency questions, one of which only passes once the staged commits are accepted.

``fibo`` loads the local FIBO checkout (290 files, ~132k triples) as stable content,
cached as N-Triples in ``data/`` after the first parse.
"""

from __future__ import annotations

import glob
import logging
import time

from rdflib import Graph

from . import _paths
from . import sip_ops  # noqa: F401  (registers viz.*)
from semantic_intelligence.core.principal import Principal
from semantic_intelligence.platform import Platform

FLEET_NS = "https://ex.org/fleet#"
FLEET = """
@prefix : <https://ex.org/fleet#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

:Vehicle a owl:Class ; rdfs:label "vehicle"@en ;
  rdfs:comment "A machine that transports people or goods."@en ;
  rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :hasPart ; owl:someValuesFrom :Wheel ] ,
                  [ a owl:Restriction ; owl:onProperty :hasManufacturer ;
                    owl:minQualifiedCardinality "1"^^xsd:nonNegativeInteger ;
                    owl:onClass :Manufacturer ] ,
                  [ a owl:Restriction ; owl:onProperty :hasVIN ;
                    owl:cardinality "1"^^xsd:nonNegativeInteger ] .
:Car a owl:Class ; rdfs:label "car"@en ; rdfs:subClassOf :Vehicle ; owl:disjointWith :Truck .
:Truck a owl:Class ; rdfs:label "truck"@en ; rdfs:subClassOf :Vehicle .
:Bicycle a owl:Class ; rdfs:label "bicycle"@en ; rdfs:subClassOf :Vehicle .
:Automobile a owl:Class ; rdfs:label "automobile"@en ; owl:equivalentClass :Car .
:SportsCar a owl:Class ; rdfs:label "sports car"@en ; rdfs:subClassOf :Automobile .
:ElectricCar a owl:Class ; rdfs:label "electric car"@en ;
  rdfs:subClassOf :Car , [ a owl:Restriction ; owl:onProperty :hasPart ;
                           owl:someValuesFrom :Battery ] .
:HybridCar a owl:Class ; rdfs:label "hybrid car"@en ;
  owl:equivalentClass [ owl:intersectionOf ( :Car
      [ a owl:Restriction ; owl:onProperty :hasPart ; owl:someValuesFrom :Engine ]
      [ a owl:Restriction ; owl:onProperty :hasPart ; owl:someValuesFrom :Battery ] ) ] .
:AmphibiousTruckCar a owl:Class ; rdfs:label "amphibious truck car"@en ;
  rdfs:subClassOf :Car , :Truck .
:FleetVehicle a owl:Class ; rdfs:label "fleet vehicle"@en ;
  rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :ownedBy ;
                    owl:someValuesFrom [ owl:unionOf ( :Company :PublicAgency ) ] ] ,
                  [ a owl:Restriction ; owl:onProperty :assignedTo ;
                    owl:someValuesFrom [ owl:complementOf :Bicycle ] ] .
:MotorVehicle a owl:Class ; rdfs:label "motor vehicle"@en ;
  owl:equivalentClass [ owl:unionOf ( :Car :Truck ) ] .
:Part a owl:Class ; rdfs:label "part"@en .
:Wheel a owl:Class ; rdfs:label "wheel"@en ; rdfs:subClassOf :Part .
:Engine a owl:Class ; rdfs:label "engine"@en ; rdfs:subClassOf :Part .
:Battery a owl:Class ; rdfs:subClassOf :Part .
:Organisation a owl:Class ; rdfs:label "organisation"@en .
:Manufacturer a owl:Class ; rdfs:label "manufacturer"@en ; rdfs:subClassOf :Organisation .
:Company a owl:Class ; rdfs:subClassOf :Organisation .
:PublicAgency a owl:Class ; rdfs:label "public agency"@en ; rdfs:subClassOf :Organisation .
:hasPart a owl:ObjectProperty ; rdfs:label "has part"@en ;
  rdfs:domain :Vehicle ; rdfs:range :Part .
:hasManufacturer a owl:ObjectProperty ; rdfs:label "has manufacturer"@en ;
  rdfs:domain :Vehicle ; rdfs:range :Manufacturer .
:ownedBy a owl:ObjectProperty ; rdfs:label "owned by"@en .
:assignedTo a owl:ObjectProperty ; rdfs:label "assigned to"@en .
:hasVIN a owl:DatatypeProperty ; rdfs:label "has VIN"@en ; rdfs:range xsd:string .
"""
FLEET_KG = """
@prefix : <https://ex.org/fleet#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
:tesla a :Manufacturer ; rdfs:label "Tesla"@en .
:volvo a :Manufacturer ; rdfs:label "Volvo"@en .
:car1 a :ElectricCar ; rdfs:label "car 1"@en ; :hasManufacturer :tesla .
:truck7 a :Truck ; rdfs:label "truck 7"@en ; :hasManufacturer :volvo .
"""
PFX = ("PREFIX : <https://ex.org/fleet#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
       "PREFIX owl: <http://www.w3.org/2002/07/owl#> ")
CQS = [
    ("cq_Vehicle_Wheel", "Does every vehicle have some wheel?",
     PFX + "ASK { :Vehicle rdfs:subClassOf ?r . ?r owl:onProperty :hasPart ; "
           "owl:someValuesFrom :Wheel }", "ask:true", "must"),
    ("cq_Manufacturer", "Which manufacturers are there?",
     PFX + "SELECT ?x WHERE { ?x a/rdfs:subClassOf* :Manufacturer }", "non-empty", "must"),
    ("cq_Truck_Engine", "Does every truck have an engine?",
     PFX + "ASK { :Truck rdfs:subClassOf ?r . ?r owl:onProperty :hasPart ; "
           "owl:someValuesFrom :Engine }", "ask:true", "should"),
    ("cq_Scooter", "Which scooters are in the fleet?",
     PFX + "SELECT ?x WHERE { ?x a :Scooter }", "non-empty", "may"),
]
USERS = (("pat", "projectmanager"), ("ann", "ontologist"), ("val", "validator"),
         ("lex", "lexicographer"))


def _platform() -> Platform:
    p = Platform()
    p.registry.add_principal(Principal("admin", is_admin=True))
    for u, _ in USERS:
        p.registry.add_principal(Principal(u))
    return p


def _members(p: Platform, project: str) -> None:
    for u, r in USERS:
        p.call("admin", project, "governance.bind", principal=u, roles=[r])


def add_fleet(p: Platform, staged: bool = True, reason: bool = True) -> None:
    p.call("admin", None, "governance.createProject", name="fleet", base_uri=FLEET_NS,
           validation=True)
    _members(p, "fleet")
    for c in p.call("val", "fleet", "validation.pending"):     # the creation commit
        p.call("val", "fleet", "validation.accept", commit=c["id"])
    for target, data in (("main", FLEET), ("kg", FLEET_KG)):
        c = p.call("pat", "fleet", "io.loadRDF", data=data, target=target)
        p.call("val", "fleet", "validation.accept", commit=c.id)
    for q in CQS:
        c = p.call("ann", "fleet", "quality.addCompetencyQuestion", id=q[0], question=q[1],
                   sparql=q[2], expectation=q[3], priority=q[4])
        p.call("val", "fleet", "validation.accept", commit=c.id)
    if reason:
        p.call("val", "fleet", "reasoning.classify")
    if staged:
        bot = p.registry.add_principal(Principal("modeler@fleet", "modeling copilot",
                                                 is_machine=True, on_behalf_of="pat"))
        p.call("pat", "fleet", "governance.bind", principal=bot.id,
               roles=["agent-ontology-copilot"])
        ev = {"agent": "modeling", "ai_generated": True, "confidence": 0.7}
        p.call(bot, "fleet", "owl.createClass", name="Scooter", parent=FLEET_NS + "Vehicle",
               label="scooter", _evidence=ev)
        p.call(bot, "fleet", "owl.addAxiom", subject=FLEET_NS + "Truck", kind="SubClassOf",
               expression="'has part' some engine", _evidence=ev)
        p.call(bot, "fleet", "owl.removeAxiom", subject=FLEET_NS + "Bicycle",
               kind="SubClassOf", expression="vehicle", _evidence=ev)
        if reason:
            p.call("val", "fleet", "reasoning.classify", staged=True)


def fibo_ntriples(refresh: bool = False) -> str:
    cache = _paths.DATA / "fibo.nt"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    if not _paths.FIBO.exists():
        raise FileNotFoundError(f"FIBO checkout not found at {_paths.FIBO}")
    logging.getLogger("rdflib").setLevel(logging.ERROR)
    g = Graph()
    for f in sorted(glob.glob(str(_paths.FIBO / "**" / "*.rdf"), recursive=True)):
        if "About" in f or "/etc/" in f.replace("\\", "/"):
            continue
        g.parse(f, format="xml")
    nt = g.serialize(format="nt")
    _paths.DATA.mkdir(exist_ok=True)
    cache.write_text(nt, encoding="utf-8")
    return nt


def add_fibo(p: Platform) -> float:
    logging.getLogger("rdflib").setLevel(logging.ERROR)   # FIBO has a few invalid xsd:dateTime
    t = time.perf_counter()
    p.call("admin", None, "governance.createProject", name="fibo",
           base_uri="https://spec.edmcouncil.org/fibo/ontology/", validation=False)
    _members(p, "fibo")
    p.call("pat", "fibo", "io.loadRDF", data=fibo_ntriples(), format="nt")
    return time.perf_counter() - t


def build(fibo: bool = False) -> Platform:
    p = _platform()
    add_fleet(p)
    if fibo:
        add_fibo(p)
    return p
