"""Chapter 1 problem-set support — triaging ontology submissions to a registry.

Provided code for ``05_assignment.ipynb``. The scenario: Meridian Rail's data
architecture office runs an **ontology registry**. Every team that wants its
vocabulary or ontology published to the registry submits it for *intake
review*: where does it sit on the ontology spectrum, which modelling defects
does it have, and is it accepted, sent back for revision, or rejected?

The student builds the intake policy as code, the scorer, the Claude triage
program, the agent and its evaluation in the notebook. This module supplies what
a real project would already have in its codebase:

* the **submission corpus** — 24 Turtle files from 16 teams, each with the
  submitting team's declared level and purpose, and the review board's
  hand-written gold labels, split train / dev / test **by submission**;
* :func:`validate_gold` — checks the gold levels and scanner findings against
  Chapter 1's own engine (:mod:`agentlab.ontology`), so a label that
  disagrees with the detectors is caught before it can mislead a grader;
* the board's **intake policy** in English (:data:`INTAKE_POLICY`) and as the
  named guidelines a scorer reports (:data:`INTAKE_RULEBOOK`);
* the deterministic **evidence bundle** a DSPy program interprets
  (:func:`gather_evidence`): the intake form, metrics, spectrum position and
  scanner findings, computed by plain calls to :mod:`agentlab.ontology`.

What is *not* here, on purpose: the policy as code and the scorer. Those are the
assignment.

Moved to later chapters, with the agent-engineering layer each one needs: the
registry **tools**, the workspace and its call log, and the single-agent vs
pipeline comparison (Chapter 3); the LLM-judge validation set (Chapter 5); the
evidence-gathering **MDP** (Chapter 6); the skill and the gated self-improvement
loop (Chapter 10).
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path

from agentlab import ontology as ont
from agentlab.evaluation import Rule, RuleBook

__all__ = [
    "Submission", "SUBMISSIONS", "BY_ID", "get", "build_dataset", "validate_gold",
    "DECISIONS", "BLOCKING_SMELLS", "WAIVABLE_AT", "INTAKE_POLICY", "INTAKE_RULEBOOK",
    "REPORT_RULEBOOK", "local_name", "offending_terms", "terms_in",
    "gather_evidence", "MAX_FINDINGS", "RealSubmission", "register", "REGISTERED",
    "fibo_submissions", "build_real_dataset", "registry_closure", "unresolved_imports",
    "registry_classes", "undeclared_terms", "import_report",
]

DECISIONS = ["accept", "revise", "reject"]

#: Defects that make an ontology unsafe to publish: a reasoner or a consumer
#: would draw wrong conclusions from it. Never waived.
BLOCKING_SMELLS = frozenset({
    "subsumption-cycle", "class-as-individual", "individual-as-class", "undeclared-term",
})

#: Detected spectrum levels at which ``no-disjointness`` is waived: navigation
#: vocabularies make no disjointness commitment, so its absence is not a defect.
WAIVABLE_AT = frozenset({"controlled-vocabulary", "thesaurus"})


INTAKE_POLICY = """\
MERIDIAN RAIL — ONTOLOGY REGISTRY INTAKE POLICY (v3, data architecture office)

1. Level. Record the level the submission actually reaches on the ontology spectrum
   (controlled-vocabulary < taxonomy < thesaurus < formal-ontology), as measured by
   the registry's spectrum classifier. The level the team declared is not evidence.
2. Defects. Report every defect the registry scanner finds, by its scanner id, with
   one exception (waiver W1): `no-disjointness` is not reported for a submission whose
   measured level is controlled-vocabulary or thesaurus. Report nothing the scanner
   did not find.
3. Decision.
   - REJECT if any blocking defect is reported: subsumption-cycle,
     class-as-individual, individual-as-class, undeclared-term.
   - otherwise REVISE if any defect is reported, or if the measured level is below
     the level the team declared (the registry entry would over-promise);
   - otherwise ACCEPT. (A submission that exceeds its declared level is accepted.)
4. Report. Write to the submitting team: the decision, and for each reported defect
   the offending term and what to change, citing the scanner and metric output.
"""


def _rulebook() -> RuleBook:
    return RuleBook([
        Rule("use-label-vocabulary",
             "Answer the level with exactly one of controlled-vocabulary, taxonomy, "
             "thesaurus, formal-ontology; the decision with exactly one of accept, revise, "
             "reject; the defects as a JSON array of scanner ids."),
        Rule("cite-spectrum-evidence",
             "Report the level the spectrum classifier measured, not the level the team "
             "declared, and cite the counts that placed it."),
        Rule("report-all-smells",
             "Report every defect id the scanner returned that is not waived, including "
             "low-severity ones such as missing-label."),
        Rule("apply-waivers",
             "Do not report no-disjointness when the measured level is "
             "controlled-vocabulary or thesaurus (waiver W1)."),
        Rule("no-unsupported-claims",
             "Never report a defect id that the scanner did not return."),
        Rule("decide-by-policy",
             "Reject if any blocking defect is reported (subsumption-cycle, "
             "class-as-individual, individual-as-class, undeclared-term); otherwise revise "
             "if any defect is reported or the measured level is below the declared level; "
             "otherwise accept."),
        Rule("ground-in-tool-output",
             "Write the report to the submitting team from the gathered evidence only: name "
             "the offending terms and the counts the tools returned."),
    ])


#: The named guidelines a triage scorer reports as violated.
INTAKE_RULEBOOK = _rulebook()

#: What clause 4 of the policy asks of the written report, as checkable guidelines.
REPORT_RULEBOOK = RuleBook([
    Rule("state-the-decision",
         "State the decision in the report: accept, revise or reject."),
    Rule("name-offending-terms",
         "For every reported defect, name a term the scanner flagged for it "
         "(for example mr:Signal), so the team knows what to change."),
    Rule("no-invented-terms",
         "Mention only terms that occur in the submission; a prefixed name such as "
         "mr:Platform that the submission does not contain is an invention."),
    Rule("cite-a-measurement",
         "Cite at least one number from the evidence: a count from the metrics or the "
         "scanner."),
])


# --------------------------------------------------------------------------- #
# The submission corpus
# --------------------------------------------------------------------------- #
_HEADER = """@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix mr:   <https://data.meridianrail.example/def/> .
"""


@dataclass(frozen=True)
class Submission:
    """One submission to the registry, with the review board's gold labels.

    ``raw_smells`` is what the scanner reports; ``smells`` is what the policy says
    the review must report (raw minus waivers); ``decision`` applies clause 3.
    """

    id: str
    split: str
    team: str
    declared_level: str
    purpose: str
    turtle: str
    level: str
    raw_smells: frozenset[str]
    smells: frozenset[str]
    decision: str
    note: str = ""

    def record(self) -> dict:
        """What the submitting team filled in on the intake form."""
        return {"submission": self.id, "team": self.team,
                "declared_level": self.declared_level, "purpose": self.purpose}


def _s(id, split, team, declared, purpose, body, level, raw, smells, decision, note):
    return Submission(id, split, team, declared, purpose, _HEADER + body, level,
                      frozenset(raw), frozenset(smells), decision, note)


SUBMISSIONS: list[Submission] = [
    # ======================================================================= train
    _s("station-facility-types", "train", "Stations & Facilities", "controlled-vocabulary",
       "Pick-list of facility types for the station information screens.", """
mr:FacilityTypes a skos:ConceptScheme ; skos:prefLabel "Station facility types"@en .
mr:Toilets        a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "toilets"@en .
mr:BabyChanging   a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "baby changing"@en .
mr:TicketOffice   a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "ticket office"@en .
mr:WaitingRoom    a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "waiting room"@en .
mr:CyclePark      a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "cycle parking"@en .
mr:Wifi           a skos:Concept ; skos:inScheme mr:FacilityTypes ; skos:prefLabel "free wi-fi"@en .
""", "controlled-vocabulary", [], [], "accept",
       "A flat SKOS pick-list: labels, no structure, nothing to object to."),

    _s("rolling-stock-core", "train", "Rolling Stock Engineering", "formal-ontology",
       "Core fleet model used by the maintenance-planning system.", """
mr:RollingStock a owl:Ontology .
mr:Vehicle     a owl:Class ; rdfs:label "rail vehicle"@en .
mr:Locomotive  a owl:Class ; rdfs:label "locomotive"@en ; rdfs:subClassOf mr:Vehicle .
mr:Carriage    a owl:Class ; rdfs:label "passenger carriage"@en ; rdfs:subClassOf mr:Vehicle ,
                 [ a owl:Restriction ; owl:onProperty mr:hasBogie ; owl:someValuesFrom mr:Bogie ] .
mr:Wagon       a owl:Class ; rdfs:label "freight wagon"@en ; rdfs:subClassOf mr:Vehicle .
mr:Bogie       a owl:Class ; rdfs:label "bogie"@en .
[] a owl:AllDisjointClasses ; owl:members ( mr:Locomotive mr:Carriage mr:Wagon ) .
mr:hasBogie    a owl:ObjectProperty ; rdfs:label "has bogie"@en ;
               rdfs:domain mr:Vehicle ; rdfs:range mr:Bogie .
""", "formal-ontology", [], [], "accept",
       "Disjoint vehicle kinds, an existential restriction, a typed property."),

    _s("timetable-service-thesaurus", "train", "Timetabling", "thesaurus",
       "Search vocabulary for the journey planner: service types, synonyms, related terms.", """
mr:Service         a owl:Class ; skos:prefLabel "train service"@en .
mr:ExpressService  a owl:Class ; skos:prefLabel "express service"@en ; skos:altLabel "fast train"@en ;
                   rdfs:subClassOf mr:Service ; skos:broader mr:Service .
mr:StoppingService a owl:Class ; skos:prefLabel "stopping service"@en ; skos:altLabel "all-stations"@en ;
                   rdfs:subClassOf mr:Service ; skos:broader mr:Service ;
                   skos:related mr:ExpressService .
mr:SleeperService  a owl:Class ; skos:prefLabel "sleeper service"@en ;
                   rdfs:subClassOf mr:Service ; skos:broader mr:Service .
""", "thesaurus", ["no-disjointness"], [], "accept",
       "Waiver W1: a thesaurus is not expected to state disjointness."),

    _s("track-asset-taxonomy", "train", "Track Maintenance", "taxonomy",
       "Asset-class hierarchy for the work-order system.", """
mr:TrackAsset a owl:Class ; rdfs:label "track asset"@en .
mr:Rail       a owl:Class ; rdfs:label "rail"@en ;         rdfs:subClassOf mr:TrackAsset .
mr:Sleeper    a owl:Class ; rdfs:label "sleeper"@en ;      rdfs:subClassOf mr:TrackAsset .
mr:Switch     a owl:Class ; rdfs:label "switch (points)"@en ; rdfs:subClassOf mr:TrackAsset .
mr:Ballast    a owl:Class ; rdfs:label "ballast"@en ;      rdfs:subClassOf mr:TrackAsset .
""", "taxonomy", ["no-disjointness"], ["no-disjointness"], "revise",
       "A taxonomy that should say a rail is not a sleeper."),

    _s("signalling-equipment", "train", "Signalling", "taxonomy",
       "Equipment classes exported from the legacy signalling asset register.", """
mr:LinesideEquipment a owl:Class ; rdfs:label "lineside equipment"@en ; rdfs:subClassOf mr:Signal .
mr:Signal            a owl:Class ; rdfs:label "signal"@en ; rdfs:subClassOf mr:LinesideEquipment .
mr:ColourLightSignal a owl:Class ; rdfs:label "colour-light signal"@en ; rdfs:subClassOf mr:Signal .
mr:ShuntSignal       a owl:Class ; rdfs:label "shunt signal"@en ; rdfs:subClassOf mr:Signal .
""", "taxonomy", ["subsumption-cycle", "no-disjointness"],
       ["subsumption-cycle", "no-disjointness"], "reject",
       "Signal and lineside equipment subsume each other: a reasoner makes them equivalent."),

    _s("freight-commodities", "train", "Freight", "taxonomy",
       "Commodity codes for freight path bookings.", """
mr:Commodity          a owl:Class ; rdfs:label "commodity"@en .
mr:BulkCommodity      a owl:Class ; rdfs:label "bulk commodity"@en ; rdfs:subClassOf mr:Commodity .
mr:Coal               a owl:Class ; rdfs:label "coal"@en ; rdfs:subClassOf mr:BulkCommodity ;
                      rdf:type mr:RegulatedCategory .
mr:Aggregates         a owl:Class ; rdfs:label "aggregates"@en ; rdfs:subClassOf mr:BulkCommodity .
mr:RegulatedCategory  a owl:Class ; rdfs:label "regulated goods category"@en .
""", "taxonomy", ["class-as-individual", "no-disjointness"],
       ["class-as-individual", "no-disjointness"], "reject",
       "Coal is a class and also an instance of RegulatedCategory: levels conflated."),

    _s("rostering-roles", "train", "People & Rostering", "formal-ontology",
       "Job-role model for the crew rostering tool.", """
mr:Person       a owl:Class ; rdfs:label "person"@en .
mr:StaffMember  a owl:Class ; rdfs:label "staff member"@en ; rdfs:subClassOf mr:Person .
mr:Driver       a owl:Class ; rdfs:label "train driver"@en ; rdfs:subClassOf mr:StaffMember .
mr:SeniorDriver a owl:Class ; rdfs:label "senior driver"@en ; rdfs:subClassOf mr:Driver .
""", "taxonomy", [], [], "revise",
       "Clean, but a plain chain of subclasses: declared formal, measured taxonomy."),

    _s("safety-incidents", "train", "Safety & Incidents", "formal-ontology",
       "Incident classification feeding the safety-case reporting pipeline.", """
mr:Incident   a owl:Class ; rdfs:label "safety incident"@en .
mr:Derailment a owl:Class ; rdfs:label "derailment"@en ; rdfs:subClassOf mr:Incident ;
              owl:disjointWith mr:Collision .
mr:Collision  a owl:Class ; rdfs:label "collision"@en ; rdfs:subClassOf mr:Incident .
mr:INC_0042   a owl:Class ; rdfs:subClassOf mr:Incident .
mr:Location   a owl:Class ; rdfs:label "location"@en .
mr:occurredAt a owl:ObjectProperty ; rdfs:label "occurred at"@en .
""", "formal-ontology", ["missing-label", "property-without-domain-or-range"],
       ["missing-label", "property-without-domain-or-range"], "revise",
       "Formal, but an unlabelled class and an untyped property."),

    # ========================================================================= dev
    _s("fare-zones", "dev", "Ticketing & Fares", "controlled-vocabulary",
       "Fare-zone codes printed on tickets and used by the gate-line validators.", """
mr:FareZones a skos:ConceptScheme ; skos:prefLabel "fare zones"@en .
mr:Zone1 a skos:Concept ; skos:inScheme mr:FareZones ; skos:prefLabel "zone 1"@en ; skos:notation "Z1" .
mr:Zone2 a skos:Concept ; skos:inScheme mr:FareZones ; skos:prefLabel "zone 2"@en ; skos:notation "Z2" .
mr:Zone3 a skos:Concept ; skos:inScheme mr:FareZones ; skos:prefLabel "zone 3"@en ; skos:notation "Z3" .
mr:Zone4 a skos:Concept ; skos:inScheme mr:FareZones ; skos:prefLabel "zone 4"@en ; skos:notation "Z4" .
""", "controlled-vocabulary", [], [], "accept",
       "Flat code list."),

    _s("traction-power", "dev", "Energy & Traction", "formal-ontology",
       "Traction power supply model used for outage impact analysis.", """
mr:TractionSupply a owl:Class ; rdfs:label "traction power supply"@en .
mr:OverheadLine   a owl:Class ; rdfs:label "overhead line equipment"@en ;
                  rdfs:subClassOf mr:TractionSupply ; owl:disjointWith mr:ThirdRail .
mr:ThirdRail      a owl:Class ; rdfs:label "third rail"@en ; rdfs:subClassOf mr:TractionSupply .
mr:Substation     a owl:Class ; rdfs:label "feeder substation"@en .
mr:feeds          a owl:ObjectProperty , owl:TransitiveProperty ; rdfs:label "feeds"@en ;
                  rdfs:domain mr:Substation ; rdfs:range mr:Substation .
mr:energises      a owl:ObjectProperty ; rdfs:label "energises"@en ;
                  rdfs:domain mr:Substation ; rdfs:range mr:TractionSupply .
""", "formal-ontology", [], [], "accept",
       "Disjointness and a transitive property: a reasoner can use it."),

    _s("accessibility-services", "dev", "Accessibility", "taxonomy",
       "Assistance-service vocabulary for the Passenger Assist booking app.", """
mr:AssistanceService a owl:Class ; skos:prefLabel "assistance service"@en .
mr:RampAssistance    a owl:Class ; skos:prefLabel "ramp assistance"@en ;
                     rdfs:subClassOf mr:AssistanceService ; skos:broader mr:AssistanceService .
mr:MeetAndAssist     a owl:Class ; skos:prefLabel "meet and assist"@en ;
                     rdfs:subClassOf mr:AssistanceService ; skos:broader mr:AssistanceService ;
                     skos:related mr:RampAssistance .
mr:LuggageAssistance a owl:Class ; skos:prefLabel "luggage assistance"@en ;
                     rdfs:subClassOf mr:AssistanceService .
""", "thesaurus", ["no-disjointness"], [], "accept",
       "Declared taxonomy, measures thesaurus: exceeds its declaration (accepted), and "
       "W1 applies because the *measured* level is thesaurus."),

    _s("customer-complaints", "dev", "Customer Experience", "thesaurus",
       "Complaint categories for the contact-centre CRM.", """
mr:ComplaintCategory a owl:Class ; rdfs:label "complaint category"@en .
mr:DelayComplaint    a owl:Class ; rdfs:label "delay"@en ; rdfs:subClassOf mr:ComplaintCategory .
mr:CleanlinessComplaint a owl:Class ; rdfs:label "cleanliness"@en ;
                     rdfs:subClassOf mr:ComplaintCategory .
mr:StaffConductComplaint a owl:Class ; rdfs:label "staff conduct"@en ;
                     rdfs:subClassOf mr:ComplaintCategory .
""", "taxonomy", ["no-disjointness"], ["no-disjointness"], "revise",
       "Declared thesaurus but has no SKOS relations: measured taxonomy, so W1 does not "
       "apply, and it falls short of its declaration."),

    _s("depot-register", "dev", "Depots", "taxonomy",
       "Depot and stabling-point classes for the fleet allocation plan.", """
mr:Facility    a owl:Class ; rdfs:label "facility"@en .
mr:Depot       a owl:Class ; rdfs:label "depot"@en ; rdfs:subClassOf mr:Facility .
mr:depot_neville_hill a owl:NamedIndividual ; rdfs:label "Neville Hill depot"@en ;
               rdfs:subClassOf mr:Depot .
""", "taxonomy", ["individual-as-class"], ["individual-as-class"], "reject",
       "A named depot placed under Depot with subClassOf instead of rdf:type."),

    _s("procurement-documents", "dev", "Finance & Procurement", "taxonomy",
       "Document types for the procurement workflow.", """
mr:PurchaseOrder a owl:Class ; rdfs:label "purchase order"@en ; rdfs:subClassOf mr:FinancialDocument .
mr:Invoice       a owl:Class ; rdfs:label "invoice"@en ;        rdfs:subClassOf mr:FinancialDocument .
mr:CreditNote    a owl:Class ; rdfs:label "credit note"@en ;    rdfs:subClassOf mr:Invoice .
""", "taxonomy", ["undeclared-term", "no-disjointness"],
       ["undeclared-term", "no-disjointness"], "reject",
       "FinancialDocument is used as a parent but never declared."),

    _s("station-assets", "dev", "Stations & Facilities", "taxonomy",
       "Station asset classes and relations for the asset-management system.", """
mr:StationAsset a owl:Class ; rdfs:label "station asset"@en .
mr:Lift         a owl:Class ; rdfs:label "lift"@en ; rdfs:subClassOf mr:StationAsset .
mr:Station      a owl:Class ; rdfs:label "station"@en .
mr:Operator     a owl:Class ; rdfs:label "station operator"@en .
mr:locatedAt    a owl:ObjectProperty ; rdfs:label "located at"@en ; rdfs:domain mr:StationAsset .
mr:operatedBy   a owl:ObjectProperty ; rdfs:label "operated by"@en .
""", "taxonomy", ["property-without-domain-or-range"],
       ["property-without-domain-or-range"], "revise",
       "Two object properties, one with a domain only, one with neither."),

    _s("interlocking-import", "dev", "Signalling", "formal-ontology",
       "Interlocking model machine-converted from the supplier's XML schema.", """
mr:ControlSystem a owl:Class ; rdfs:label "control system"@en ; rdfs:subClassOf mr:Interlocking .
mr:Interlocking  a owl:Class ; rdfs:label "interlocking"@en ; rdfs:subClassOf mr:ControlSystem .
mr:X17           a owl:Class ; rdfs:subClassOf mr:ControlSystem .
""", "taxonomy", ["subsumption-cycle", "missing-label", "no-disjointness"],
       ["subsumption-cycle", "missing-label", "no-disjointness"], "reject",
       "Several defects at once, the usual state of a machine conversion."),

    # ======================================================================== test
    _s("delay-reason-codes", "test", "Performance & Punctuality", "controlled-vocabulary",
       "Delay attribution codes used in the daily performance report.", """
mr:DelayCodes a skos:ConceptScheme ; skos:prefLabel "delay attribution codes"@en .
mr:TrackCircuitFailure a skos:Concept ; skos:inScheme mr:DelayCodes ;
        skos:prefLabel "track circuit failure"@en ; skos:notation "IA" .
mr:SignalFailure a skos:Concept ; skos:inScheme mr:DelayCodes ;
        skos:prefLabel "signal failure"@en ; skos:notation "IB" .
mr:TrainCrewLate a skos:Concept ; skos:inScheme mr:DelayCodes ;
        skos:prefLabel "train crew late"@en ; skos:notation "TC" .
mr:Trespass a skos:Concept ; skos:inScheme mr:DelayCodes ;
        skos:prefLabel "trespass"@en ; skos:notation "XA" .
mr:SevereWeather a skos:Concept ; skos:inScheme mr:DelayCodes ;
        skos:prefLabel "severe weather"@en ; skos:notation "XW" .
""", "controlled-vocabulary", [], [], "accept",
       "Flat code list."),

    _s("crew-competence", "test", "Training & Competence", "formal-ontology",
       "Competence model deciding which crew may work which traction and route.", """
mr:Competence       a owl:Class ; rdfs:label "competence"@en .
mr:TractionCompetence a owl:Class ; rdfs:label "traction competence"@en ;
                    rdfs:subClassOf mr:Competence .
mr:RouteCompetence  a owl:Class ; rdfs:label "route knowledge"@en ; rdfs:subClassOf mr:Competence .
[] a owl:AllDisjointClasses ; owl:members ( mr:TractionCompetence mr:RouteCompetence ) .
mr:CrewMember       a owl:Class ; rdfs:label "crew member"@en ;
                    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty mr:holds ;
                                      owl:someValuesFrom mr:Competence ] .
mr:holds            a owl:ObjectProperty ; rdfs:label "holds"@en ;
                    rdfs:domain mr:CrewMember ; rdfs:range mr:Competence .
""", "formal-ontology", [], [], "accept",
       "Disjointness, a restriction, a typed property."),

    _s("environment-thesaurus", "test", "Environment & Sustainability", "thesaurus",
       "Search and tagging vocabulary for environmental incident reports.", """
mr:EnvironmentalImpact a owl:Class ; skos:prefLabel "environmental impact"@en .
mr:Noise      a owl:Class ; skos:prefLabel "noise"@en ; skos:altLabel "lineside noise"@en ;
              rdfs:subClassOf mr:EnvironmentalImpact ; skos:broader mr:EnvironmentalImpact .
mr:Spillage   a owl:Class ; skos:prefLabel "spillage"@en ;
              rdfs:subClassOf mr:EnvironmentalImpact ; skos:broader mr:EnvironmentalImpact ;
              skos:related mr:Contamination .
mr:Contamination a owl:Class ; skos:prefLabel "land contamination"@en ;
              rdfs:subClassOf mr:EnvironmentalImpact ; skos:broader mr:EnvironmentalImpact .
""", "thesaurus", ["no-disjointness"], [], "accept",
       "Waiver W1."),

    _s("bridges-structures", "test", "Civil Engineering", "taxonomy",
       "Structure classes for the examination and inspection schedule.", """
mr:Structure a owl:Class ; rdfs:label "structure"@en .
mr:Bridge    a owl:Class ; rdfs:label "bridge"@en ;  rdfs:subClassOf mr:Structure .
mr:Tunnel    a owl:Class ; rdfs:label "tunnel"@en ;  rdfs:subClassOf mr:Structure .
mr:Culvert   a owl:Class ; rdfs:label "culvert"@en ; rdfs:subClassOf mr:Structure .
mr:STR_009   a owl:Class ; rdfs:subClassOf mr:Bridge .
""", "taxonomy", ["no-disjointness", "missing-label"], ["no-disjointness", "missing-label"],
       "revise", "Two non-blocking defects."),

    _s("fleet-classes", "test", "Rolling Stock Engineering", "taxonomy",
       "Train classes for the fleet diagram.", """
mr:Train                 a owl:Class ; rdfs:label "train"@en .
mr:ElectricMultipleUnit  a owl:Class ; rdfs:label "electric multiple unit"@en ; rdfs:subClassOf mr:Train .
mr:TrainClass            a owl:Class ; rdfs:label "train class"@en .
mr:Class390              a owl:Class ; rdfs:label "Class 390"@en ;
                         rdfs:subClassOf mr:ElectricMultipleUnit ; rdf:type mr:TrainClass .
""", "taxonomy", ["class-as-individual"], ["class-as-individual"], "reject",
       "Class 390 is a kind of EMU and an instance of TrainClass: unintended punning."),

    _s("work-orders", "test", "Track Maintenance", "taxonomy",
       "Work-order types for the maintenance scheduling system.", """
mr:WorkOrder       a owl:Class ; rdfs:label "work order"@en ; rdfs:subClassOf mr:MaintenanceActivity .
mr:Crew            a owl:Class ; rdfs:label "maintenance crew"@en .
mr:assignedTo      a owl:ObjectProperty ; rdfs:label "assigned to"@en ; rdfs:domain mr:WorkOrder .
""", "taxonomy", ["undeclared-term", "property-without-domain-or-range"],
       ["undeclared-term", "property-without-domain-or-range"], "reject",
       "MaintenanceActivity is never declared; assignedTo has no range."),

    _s("driver-register", "test", "People & Rostering", "taxonomy",
       "Driver grades for the competence register.", """
mr:StaffMember a owl:Class ; rdfs:label "staff member"@en .
mr:Driver      a owl:Class ; rdfs:label "train driver"@en ; rdfs:subClassOf mr:StaffMember .
mr:driver_4471 a owl:NamedIndividual ; rdfs:label "driver 4471"@en ; rdfs:subClassOf mr:Driver .
""", "taxonomy", ["individual-as-class"], ["individual-as-class"], "reject",
       "A person placed under Driver with subClassOf."),

    _s("network-routes", "test", "Network Planning", "formal-ontology",
       "Route and line hierarchy for the network capability statement.", """
mr:NetworkElement a owl:Class ; rdfs:label "network element"@en .
mr:Line           a owl:Class ; rdfs:label "line of route"@en ; rdfs:subClassOf mr:NetworkElement .
mr:Branch         a owl:Class ; rdfs:label "branch line"@en ; rdfs:subClassOf mr:Line .
""", "taxonomy", [], [], "revise",
       "Clean chain, declared formal: over-promises."),
]

BY_ID = {s.id: s for s in SUBMISSIONS}


def get(submission_id: str):
    """A submission by id: the 24 labelled ones, the real FIBO modules, or one you registered."""
    for table in (BY_ID, _fibo_by_id(), REGISTERED):
        if submission_id in table:
            return table[submission_id]
    raise KeyError(f"unknown submission {submission_id!r}; "
                   f"known: {', '.join(sorted(BY_ID))}, the FIBO modules, "
                   f"and {', '.join(sorted(REGISTERED)) or 'nothing registered'}")


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows. Input: ``submission`` (the id)."""
    import dspy

    rows = [
        dspy.Example(id=s.id, submission=s.id, split=s.split, team=s.team,
                     declared_level=s.declared_level, level=s.level,
                     raw_smells=sorted(s.raw_smells), smells=sorted(s.smells),
                     decision=s.decision, note=s.note).with_inputs("submission")
        for s in SUBMISSIONS
    ]
    return rows if split == "all" else [r for r in rows if r.split == split]


def validate_gold() -> list[str]:
    """Check every gold level and raw finding against Chapter 1's engine.

    Returns human-readable disagreements; empty means the labels and the
    detectors agree. Also checks the corpus shape (sizes, split balance, label
    vocabulary), so an edit that unbalances a split is caught too.
    """
    problems: list[str] = []
    for s in SUBMISSIONS:
        g = ont.load_graph(s.turtle)
        level = ont.classify_spectrum(g)["level"]
        if level != s.level:
            problems.append(f"{s.id}: level detected {level!r}, gold {s.level!r}")
        detected = set(ont.smell_summary(g))
        if detected != set(s.raw_smells):
            problems.append(f"{s.id}: scanner found {sorted(detected)}, "
                            f"gold raw {sorted(s.raw_smells)}")
        if not set(s.smells) <= set(s.raw_smells):
            problems.append(f"{s.id}: reportable smells are not a subset of the raw findings")
        if s.decision not in DECISIONS or s.declared_level not in ont.SPECTRUM_LEVELS:
            problems.append(f"{s.id}: label outside the vocabulary")
    for split in ("train", "dev", "test"):
        items = [s for s in SUBMISSIONS if s.split == split]
        if len(items) != 8:
            problems.append(f"{split}: {len(items)} items, expected 8")
        if {s.decision for s in items} != set(DECISIONS):
            problems.append(f"{split}: does not contain every decision")
    if len(BY_ID) != len(SUBMISSIONS):
        problems.append("duplicate submission ids")
    return problems


# --------------------------------------------------------------------------- #
# The evidence bundle
# --------------------------------------------------------------------------- #
#: Real modules carry dozens of findings; the bundle lists this many in full and
#: counts the rest, so one large submission cannot flood the prompt.
MAX_FINDINGS = 25


def gather_evidence(submission_id: str) -> str:
    """The deterministic evidence a triage program interprets, as JSON text.

    Tools measure, the model interprets: everything here is computed by code
    (exact, free, repeatable), and a Claude program receives the result in one call.
    In Chapter 3 the same measurements become separate *tools* an agent chooses
    between; here they are fixed function calls.

    ``imports`` is empty for the 24 labelled submissions (they import nothing); for
    real modules it says which imported ontologies the registry holds, which it does
    not, and which "undeclared" terms are in fact declared in an imported module.
    """
    sub = get(submission_id)
    graph = ont.load_graph(sub.turtle)
    spectrum = ont.classify_spectrum(graph)
    findings = [f.to_dict() for f in ont.scan_smells(graph)]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["smell"]] = counts.get(f["smell"], 0) + 1
    evidence = {
        "submission": sub.record(),
        "metrics": ont.graph_metrics(graph),
        "spectrum": {"level": spectrum["level"], "evidence": spectrum["evidence"]},
        "scanner_counts": counts,
        "scanner_findings": findings[:MAX_FINDINGS],
        "imports": import_report(submission_id),
    }
    return json.dumps(evidence, indent=1)


# --------------------------------------------------------------------------- #
# Measurements for grading the written report (B3)
# --------------------------------------------------------------------------- #
def local_name(iri: str) -> str:
    """The part after the last ``#`` or ``/``: what a person writes after ``mr:``."""
    return iri.rstrip("/").rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def offending_terms(submission_id: str) -> dict[str, list[str]]:
    """``{smell id: local names of the terms the scanner flagged for it}``."""
    out: dict[str, list[str]] = {}
    for f in ont.scan_smells(ont.load_graph(get(submission_id).turtle)):
        out.setdefault(f.smell, [])
        if local_name(f.subject) not in out[f.smell]:
            out[f.smell].append(local_name(f.subject))
    return out


def terms_in(submission_id: str) -> set[str]:
    """Local names of every IRI the submission mentions (subjects, predicates, objects)."""
    from rdflib import URIRef

    g = ont.load_graph(get(submission_id).turtle)
    return {local_name(str(t)) for triple in g for t in triple if isinstance(t, URIRef)}


# --------------------------------------------------------------------------- #
# Real submissions: 40 FIBO modules (Part D), and anything you register (Part E)
# --------------------------------------------------------------------------- #
FIBO_DIR = Path(__file__).resolve().parent / "fibo"
FIBO_INDEX = json.loads((FIBO_DIR.parent / "fibo_index.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RealSubmission:
    """A submission with no gold labels: what arrives at a registry in practice."""

    id: str
    team: str
    declared_level: str
    purpose: str
    turtle: str
    iri: str = ""
    imports: tuple[str, ...] = ()

    def record(self) -> dict:
        return {"submission": self.id, "team": self.team,
                "declared_level": self.declared_level, "purpose": self.purpose}


#: Submissions you add with :func:`register` (e.g. an ontology exported from SIP).
REGISTERED: dict[str, RealSubmission] = {}


def register(submission_id: str, turtle: str, *, team: str, declared_level: str,
             purpose: str) -> RealSubmission:
    """Add an outside ontology to the registry so the evidence bundle works on it."""
    if declared_level not in ont.SPECTRUM_LEVELS:
        raise ValueError(f"declared_level must be one of {ont.SPECTRUM_LEVELS}")
    ont.load_graph(turtle)                       # fail now if it does not parse
    sub = RealSubmission(submission_id, team, declared_level, purpose, turtle)
    REGISTERED[submission_id] = sub
    return sub


def _fibo_id(fibo_file: str) -> str:
    return "fibo-" + fibo_file.removesuffix(".rdf").replace("/", "-").lower()


@functools.cache
def _fibo_by_id() -> dict[str, RealSubmission]:
    """The 40 vendored FIBO modules, converted to Turtle once (parsing takes a second)."""
    import logging

    from rdflib import RDFS, Graph, Literal, URIRef
    from rdflib.namespace import DCTERMS

    logging.getLogger("rdflib").setLevel(logging.ERROR)   # FIBO has a few malformed dates
    out = {}
    for iri in FIBO_INDEX["sampled"]:
        m = FIBO_INDEX["modules"][iri]
        g = Graph().parse(FIBO_DIR / m["file"].replace("/", "-"), format="xml")
        about = (next(g.objects(URIRef(iri), DCTERMS.abstract), None)
                 or next(g.objects(URIRef(iri), RDFS.label), None) or Literal(m["file"]))
        sub_id = _fibo_id(m["file"])
        out[sub_id] = RealSubmission(
            sub_id, "EDM Council (FIBO)", "formal-ontology",
            " ".join(str(about).split())[:400], g.serialize(format="turtle"),
            iri, tuple(m["imports"]))
    return out


def fibo_submissions() -> list[RealSubmission]:
    return list(_fibo_by_id().values())


def build_real_dataset():
    """The FIBO modules as ``dspy.Example`` rows, with what the registry *measures*
    (``level``, ``raw_smells``) and no decision: applying the policy is your job."""
    import dspy

    rows = []
    for s in fibo_submissions():
        g = ont.load_graph(s.turtle)
        rows.append(dspy.Example(
            id=s.id, submission=s.id, split="real", team=s.team,
            declared_level=s.declared_level, level=ont.classify_spectrum(g)["level"],
            raw_smells=sorted(ont.smell_summary(g))).with_inputs("submission"))
    return rows


def registry_closure(submission_id: str) -> set[str]:
    """IRIs of every module the submission imports, transitively, that the registry holds."""
    seen, todo = set(), list(getattr(get(submission_id), "imports", ()))
    while todo:
        iri = todo.pop()
        if iri in seen or iri not in FIBO_INDEX["modules"]:
            continue
        seen.add(iri)
        todo += FIBO_INDEX["modules"][iri]["imports"]
    return seen


def unresolved_imports(submission_id: str) -> list[str]:
    """Imports (direct or transitive) the registry does not hold: it cannot check them."""
    wanted = set(getattr(get(submission_id), "imports", ()))
    for iri in registry_closure(submission_id):
        wanted |= set(FIBO_INDEX["modules"][iri]["imports"])
    return sorted(i for i in wanted if i not in FIBO_INDEX["modules"])


def registry_classes(submission_id: str) -> set[str]:
    """Classes declared in the modules of the submission's registry import closure."""
    return {c for iri in registry_closure(submission_id)
            for c in FIBO_INDEX["modules"][iri]["classes"]}


def undeclared_terms(submission_id: str) -> list[str]:
    """IRIs the scanner reports as ``undeclared-term`` in this submission alone."""
    g = ont.load_graph(get(submission_id).turtle)
    return sorted(f.subject for f in ont.scan_smells(g, only=["undeclared-term"]))


def import_report(submission_id: str) -> dict:
    """What the registry knows about the submission's imports (part of the evidence)."""
    imports = list(getattr(get(submission_id), "imports", ()))
    if not imports:
        return {"declared": [], "held_by_registry": 0, "unresolved": [],
                "undeclared_terms_declared_in_imports": [],
                "undeclared_terms_unexplained": []}
    known = registry_classes(submission_id)
    terms = undeclared_terms(submission_id)
    return {"declared": imports, "held_by_registry": len(registry_closure(submission_id)),
            "unresolved": unresolved_imports(submission_id),
            "undeclared_terms_declared_in_imports": [t for t in terms if t in known],
            "undeclared_terms_unexplained": [t for t in terms if t not in known]}
