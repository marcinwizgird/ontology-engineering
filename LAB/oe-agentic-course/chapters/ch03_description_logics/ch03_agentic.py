"""Chapter 3 problem-set support — reviewing ontology change requests with a DL reasoner.

Provided code for ``05_assignment.ipynb``. The student builds the heuristic, the
grader, the Claude reviewer, the review agent and the pipeline with a reasoner critic
in the notebook; this module supplies what a real project would already have:

* the **change-request corpus** — 24 modules of Meridian Rail's asset ontology,
  each with a reviewer's subsumption question, a fixed train / dev / test split
  by item (balanced by phenomenon and by verdict), and 6 *unlabelled* field
  requests;
* **gold validation** (:func:`validate_gold`) — every stored label is re-derived
  with the Chapter 3 engine, and every "not subsumed" verdict the ALC tableau
  cannot certify on its own carries an explicit **countermodel** checked under
  the full SHOIQ semantics (:class:`Interpretation`, :func:`is_countermodel`);
* the **guidelines** a review scorer reports (:data:`DL_RULEBOOK`);
* the review agent's **tools** (:func:`build_review_tools`, on ``agentlab.tools``);
* the **contamination twins** (:data:`PIZZA_ITEMS`, :func:`contamination_dataset`): five
  questions about the Pizza ontology every model has read, each in three variants --
  *famous* (the tutorial's names and axioms), *renamed* (the same axioms, names that
  carry no world knowledge) and *counterfactual* (the tutorial's names, one axiom
  changed so the memorised answer is wrong);
* **SIP's fleet ontology** as review modules (:data:`FLEET_CASES`): a private,
  never-published ontology, for the transfer test.

Two ideas make this chapter different from the others.

**The oracle is free and (on this corpus) always right.** The tableau settles
every question in the dataset, so labels cost nothing: a deployed reviewer can
label its own failures with no human in the loop. The caveat is the chapter's
own: the tableau decides **ALC**. Transitivity, role hierarchies, inverses and
number restrictions are *named* by :func:`ch03_toolkit.dl_name` but not reasoned
over, so the tableau is sound for "subsumed" and only conditionally complete for
"not subsumed" — which is exactly why the non-ALC negative labels carry
certificates.

**A famous benchmark measures memory as well as reasoning.** A model that has read the
Pizza tutorial can answer its questions without reading the axioms. The counterfactual
variant separates the two: its axioms say the opposite of what the model remembers.

The original problem set also priced the reasoner with a **budgeted, stochastic MDP**
and let the reviewer **improve itself** on oracle-labelled traffic. Those parts need
layers this course introduces later (MDPs in Chapter 6, skills and gated
self-improvement in Chapter 10) and return there; ``FIELD_CASES`` stays here because
the gold validation covers it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

import ch03_toolkit as dl

__all__ = [
    "Case", "CASES", "FIELD_CASES", "case", "describe_kb", "build_dataset",
    "field_requests", "DL_RULEBOOK", "Interpretation", "is_countermodel",
    "CERTIFICATES", "ALC_CONSTRUCTORS", "validate_gold", "rbox_licensed", "risk_class",
    "ReviewWorkspace", "build_review_tools", "PIZZA_ITEMS", "VARIANTS", "rename_tbox",
    "contamination_dataset", "FLEET_CASES", "fleet_dataset",
]

A = dl.Atomic
E = dl.Exists
F = dl.ForAll
N = dl.Not
Inv = dl.Inverse


def _and(*parts):
    out = parts[0]
    for p in parts[1:]:
        out = dl.And(out, p)
    return out


# --------------------------------------------------------------------------- #
# The corpus: ontology modules submitted for review
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Case:
    """One change request: an ontology module plus the reviewer's question.

    ``build`` returns a fresh :class:`ch03_toolkit.TBox` each call (TBoxes are
    mutable). ``gold_dl`` / ``gold_subsumed`` are the *stored* labels; they are
    re-derived by :func:`validate_gold` and never trusted on their own.
    ``phenomenon`` is the balancing stratum: each appears once per split.
    """

    id: str
    split: str
    phenomenon: str
    request: str
    build: Callable[[], dl.TBox]
    sub: str
    sup: str
    gold_dl: str | None = None
    gold_subsumed: bool | None = None

    def tbox(self) -> dl.TBox:
        return self.build()


def _tb(*axioms, transitive=(), hierarchy=(), equiv=()):
    """Helper: a TBox from (left, right) pairs; ``equiv`` lists equivalence pairs."""
    def build():
        t = dl.TBox()
        for left, right in equiv:
            t.add(left, right, equivalence=True)
        for left, right in axioms:
            t.add(left, right)
        t.transitive_roles.update(transitive)
        t.role_hierarchy.extend(hierarchy)
        return t
    return build


# Phenomena (one item per split each):
#   inferred-definition   ALC, subsumption holds only through a defined class      (true)
#   universal-trap        ALC, "only" read as "some", or the converse direction    (false)
#   transitive-told       S, a told chain in a module with a transitive role      (true)
#   role-hierarchy        H, a sub-role read in the wrong direction                (false)
#   inverse-definition    I, holds through a definition over an inverse role      (true)
#   number-restriction    N/Q, "at least 2" is not "at least 3"                    (false)
#   unsatisfiable-subject ALC, the subject class is unsatisfiable -> vacuous       (true)
#   expressive-combo      SHIQ-family module, plausible but not entailed            (false)
CASES: list[Case] = [
    # ============================== train ================================= #
    Case("barrier-safety-critical", "train", "inferred-definition",
         "Signalling asks: is every level-crossing barrier a safety-critical asset?",
         _tb((A("LevelCrossingBarrier"), _and(A("Asset"), E("protects", A("LevelCrossing")))),
             (A("LevelCrossing"), A("Crossing")),
             equiv=[(A("SafetyCriticalAsset"), _and(A("Asset"), E("protects", A("Crossing"))))]),
         "LevelCrossingBarrier", "SafetyCriticalAsset", "ALC", True),
    Case("drainage-culvert", "train", "universal-trap",
         "Drainage asks: is every drainage asset a culvert?",
         _tb((A("DrainageAsset"), _and(A("Asset"), F("drains", A("Watercourse")))),
             equiv=[(A("Culvert"), _and(A("Asset"), E("drains", A("Watercourse"))))]),
         "DrainageAsset", "Culvert", "ALC", False),
    Case("fishplate-component", "train", "transitive-told",
         "Track asks: is a fishplate a track component?",
         _tb((A("Fishplate"), A("RailJoint")),
             (A("RailJoint"), A("TrackComponent")),
             (A("TrackComponent"), E("partOf", A("TrackSection"))),
             transitive=["partOf"]),
         "Fishplate", "TrackComponent", "S", True),
    Case("depot-signal-maintainer", "train", "role-hierarchy",
         "Maintenance asks: is every maintenance depot a signal maintainer?",
         _tb((A("MaintenanceDepot"), E("isResponsibleFor", A("Signal"))),
             hierarchy=[("maintains", "isResponsibleFor")],
             equiv=[(A("SignalMaintainer"), E("maintains", A("Signal")))]),
         "MaintenanceDepot", "SignalMaintainer", "ALCH", False),
    Case("bridge-inspected", "train", "inverse-definition",
         "Structures asks: does the module make every bridge an inspected asset?",
         _tb((A("Bridge"), _and(A("Asset"), E(Inv("inspects"), A("AnnualInspection")))),
             (A("AnnualInspection"), A("Inspection")),
             equiv=[(A("InspectedAsset"), _and(A("Asset"), E(Inv("inspects"), A("Inspection"))))]),
         "Bridge", "InspectedAsset", "ALCI", True),
    Case("double-slip-heavy", "train", "number-restriction",
         "Track asks: is a double-slip switch a heavy switch?",
         _tb((A("DoubleSlip"), _and(A("Switch"), dl.AtLeast(2, "hasPart", A("PointsMotor")))),
             equiv=[(A("HeavySwitch"), _and(A("Switch"), dl.AtLeast(3, "hasPart", A("PointsMotor"))))]),
         "DoubleSlip", "HeavySwitch", "ALCQ", False),
    Case("automated-manual-crossing", "train", "unsatisfiable-subject",
         "Data quality asks: is an automated-manual crossing a bridge? (the class came from a merge)",
         _tb((A("UnmannedCrossing"), _and(A("LevelCrossing"), F("staffedBy", N(A("Person"))))),
             (A("ManualCrossing"), _and(A("LevelCrossing"), E("staffedBy", A("CrossingKeeper")))),
             (A("CrossingKeeper"), A("Person")),
             (A("AutomatedManualCrossing"), _and(A("UnmannedCrossing"), A("ManualCrossing")))),
         "AutomatedManualCrossing", "Bridge", "ALC", True),
    Case("interlocking-control-centre", "train", "expressive-combo",
         "Signalling asks: is every interlocking a control centre?",
         _tb((A("Interlocking"), dl.AtLeast(2, "controls", A("Signal"))),
             (A("Signal"), E(Inv("controls"), A("Interlocking"))),
             transitive=["supervises"], hierarchy=[("controls", "supervises")],
             equiv=[(A("ControlCentre"), E("supervises", A("Interlocking")))]),
         "Interlocking", "ControlCentre", "SHIQ", False),
    # =============================== dev ================================== #
    Case("viaduct-critical", "dev", "inferred-definition",
         "Structures asks: is every viaduct a critical structure?",
         _tb((A("Viaduct"), _and(A("Bridge"), E("carries", A("MainLine")))),
             (A("Bridge"), A("Structure")),
             (A("MainLine"), A("Railway")),
             equiv=[(A("CriticalStructure"), _and(A("Structure"), E("carries", A("Railway"))))]),
         "Viaduct", "CriticalStructure", "ALC", True),
    Case("clearance-habitat", "dev", "universal-trap",
         "Environment asks: is every vegetation-clearance zone a protected habitat?",
         _tb((A("ProtectedHabitat"), _and(A("Zone"), F("contains", N(A("InvasiveSpecies"))))),
             equiv=[(A("ClearanceZone"), _and(A("Zone"), E("contains", A("InvasiveSpecies"))))]),
         "ClearanceZone", "ProtectedHabitat", "ALC", False),
    Case("tunnel-ring-civil", "dev", "transitive-told",
         "Structures asks: is a tunnel ring a civil asset?",
         _tb((A("TunnelRing"), A("TunnelLining")),
             (A("TunnelLining"), _and(A("CivilAsset"), E("partOf", A("Tunnel")))),
             transitive=["partOf"]),
         "TunnelRing", "CivilAsset", "S", True),
    Case("substation-feeder", "dev", "role-hierarchy",
         "Power asks: is every substation a feeder station?",
         _tb((A("Substation"), E("feeds", A("OverheadLine"))),
             transitive=["connectedTo"], hierarchy=[("feeds", "connectedTo")],
             equiv=[(A("FeederStation"), E("feeds", A("Substation")))]),
         "Substation", "FeederStation", "SH", False),
    Case("switch-monitored", "dev", "inverse-definition",
         "Remote condition monitoring asks: is every switch a monitored asset?",
         _tb((A("Switch"), _and(A("TrackAsset"), E(Inv("mountedOn"), A("HeatSensor")))),
             (A("HeatSensor"), A("Sensor")),
             (A("TrackAsset"), _and(A("Asset"), E("partOf", A("Route")))),
             transitive=["partOf"],
             equiv=[(A("MonitoredAsset"), _and(A("Asset"), E(Inv("mountedOn"), A("Sensor"))))]),
         "Switch", "MonitoredAsset", "SI", True),
    Case("bay-platform-low-use", "dev", "number-restriction",
         "Stations asks: is every bay platform a low-use platform?",
         _tb((A("BayPlatform"), _and(A("Platform"), dl.AtMost(2, "servedBy"))),
             equiv=[(A("LowUsePlatform"), _and(A("Platform"), dl.AtMost(1, "servedBy")))]),
         "BayPlatform", "LowUsePlatform", "ALCN", False),
    Case("permissive-stop-signal", "dev", "unsatisfiable-subject",
         "Data quality asks: is a permissive stop signal a level crossing?",
         _tb((A("StopSignal"), _and(A("Signal"), F("shows", A("RedAspect")))),
             (A("ProceedSignal"), _and(A("Signal"), E("shows", A("GreenAspect")))),
             (A("GreenAspect"), N(A("RedAspect"))),
             (A("PermissiveStopSignal"), _and(A("StopSignal"), A("ProceedSignal")))),
         "PermissiveStopSignal", "LevelCrossing", "ALC", True),
    Case("junction-route", "dev", "expressive-combo",
         "Network asks: is every junction a route?",
         _tb((A("Junction"), dl.AtLeast(3, Inv("partOf"))),
             transitive=["partOf"], hierarchy=[("partOf", "locatedIn")],
             equiv=[(A("Route"), E(Inv("partOf"), A("Junction")))]),
         "Junction", "Route", "SHIN", False),
    # =============================== test ================================= #
    Case("rail-break-urgent", "test", "inferred-definition",
         "Maintenance planning asks: is every rail-break repair an urgent renewal?",
         _tb((A("RailBreakRepair"), _and(A("MaintenanceTask"), E("targets", A("BrokenRail")))),
             (A("BrokenRail"), _and(A("Rail"), A("CrackedAsset"))),
             equiv=[(A("UrgentRenewal"), _and(A("MaintenanceTask"), E("targets", A("DefectiveAsset")))),
                    (A("DefectiveAsset"), dl.Or(A("CrackedAsset"), A("WornAsset")))]),
         "RailBreakRepair", "UrgentRenewal", "ALC", True),
    Case("possession-safe-window", "test", "universal-trap",
         "Possession planning asks: is every possession a safe work window?",
         _tb((A("Possession"), _and(A("WorkWindow"), F("authorisedBy", A("Controller")))),
             equiv=[(A("SafeWorkWindow"), _and(A("WorkWindow"), E("authorisedBy", A("Controller"))))]),
         "Possession", "SafeWorkWindow", "ALC", False),
    Case("dropper-asset", "test", "transitive-told",
         "Electrification asks: is a dropper an asset?",
         _tb((A("Dropper"), A("CatenaryComponent")),
             (A("CatenaryComponent"), _and(A("ElectrificationAsset"), E("partOf", A("OverheadLine")))),
             (A("ElectrificationAsset"), A("Asset")),
             transitive=["partOf"]),
         "Dropper", "Asset", "S", True),
    Case("patroller-inspector", "test", "role-hierarchy",
         "Drainage asks: is every patroller a culvert inspector?",
         _tb((A("Patroller"), E("visits", A("Culvert"))),
             hierarchy=[("inspects", "visits")],
             equiv=[(A("CulvertInspector"), E("inspects", A("Culvert")))]),
         "Patroller", "CulvertInspector", "ALCH", False),
    Case("tunnel-managed", "test", "inverse-definition",
         "Asset management asks: is every tunnel a managed asset?",
         _tb((A("Tunnel"), _and(A("CivilAsset"), E(Inv("manages"), A("StructuresTeam")))),
             (A("CivilAsset"), A("Asset")),
             (A("StructuresTeam"), A("Team")),
             equiv=[(A("ManagedAsset"), _and(A("Asset"), E(Inv("manages"), A("Team"))))]),
         "Tunnel", "ManagedAsset", "ALCI", True),
    Case("plain-line-detection", "test", "number-restriction",
         "Train detection asks: is every plain-line section fully detected?",
         _tb((A("PlainLineSection"), _and(A("TrackSection"), dl.AtLeast(1, "hasPart", A("AxleCounter")))),
             equiv=[(A("FullyDetectedSection"),
                     _and(A("TrackSection"), dl.AtLeast(2, "hasPart", A("AxleCounter"))))]),
         "PlainLineSection", "FullyDetectedSection", "ALCQ", False),
    Case("electrified-low-bridge", "test", "unsatisfiable-subject",
         "Data quality asks: is an electrified low bridge a tunnel?",
         _tb((A("LowBridge"), _and(A("Bridge"), F("spans", N(A("ElectrifiedLine"))))),
             (A("ElectrifiedCrossing"), _and(A("Bridge"), E("spans", A("MainLine")))),
             (A("MainLine"), A("ElectrifiedLine")),
             (A("ElectrifiedLowBridge"), _and(A("LowBridge"), A("ElectrifiedCrossing")))),
         "ElectrifiedLowBridge", "Tunnel", "ALC", True),
    Case("depot-major", "test", "expressive-combo",
         "Fleet asks: is every depot a major depot?",
         _tb((A("Depot"), dl.AtLeast(2, Inv("stabledAt"), A("Train"))),
             (A("Train"), E("assignedTo", A("Depot"))),
             hierarchy=[("stabledAt", "assignedTo")],
             equiv=[(A("MajorDepot"), _and(A("Depot"), dl.AtLeast(3, Inv("stabledAt"), A("Train"))))]),
         "Depot", "MajorDepot", "ALCHIQ", False),
]

#: Requests that arrive in production with **no label** — the self-labelling pool.
FIELD_CASES: list[Case] = [
    Case("town-crossing-risk", "field", "inferred-definition",
         "Level crossings asks: is every town crossing a high-risk crossing?",
         _tb((A("TownCrossing"), _and(A("LevelCrossing"), E("nearTo", A("PrimarySchool")))),
             (A("PrimarySchool"), A("School")),
             equiv=[(A("HighRiskCrossing"), _and(A("LevelCrossing"), E("nearTo", A("School"))))]),
         "TownCrossing", "HighRiskCrossing"),
    Case("footbridge-rail-bridge", "field", "universal-trap",
         "Structures asks: is every footbridge a rail bridge?",
         _tb((A("Footbridge"), _and(A("Bridge"), F("carries", A("Pedestrian")))),
             equiv=[(A("RailBridge"), _and(A("Bridge"), E("carries", A("Train"))))]),
         "Footbridge", "RailBridge"),
    Case("major-station-staffed", "field", "inverse-definition",
         "Stations asks: is every major station a staffed station?",
         _tb((A("MajorStation"), _and(A("Station"), E(Inv("worksAt"), A("StationManager")))),
             (A("StationManager"), A("Employee")),
             equiv=[(A("StaffedStation"), _and(A("Station"), E(Inv("worksAt"), A("Employee"))))]),
         "MajorStation", "StaffedStation"),
    Case("underbridge-twin-track", "field", "number-restriction",
         "Structures asks: is every underbridge a twin-track bridge?",
         _tb((A("Underbridge"), _and(A("Bridge"), dl.AtLeast(1, "carries", A("Track")))),
             equiv=[(A("TwinTrackBridge"), _and(A("Bridge"), dl.AtLeast(2, "carries", A("Track"))))]),
         "Underbridge", "TwinTrackBridge"),
    Case("hybrid-corridor", "field", "unsatisfiable-subject",
         "Data quality asks: is a hybrid corridor a depot?",
         _tb((A("DieselOnlyRoute"), _and(A("Route"), F("servedBy", N(A("ElectricTrain"))))),
             (A("ElectrifiedRoute"), _and(A("Route"), E("servedBy", A("EMU")))),
             (A("EMU"), A("ElectricTrain")),
             (A("HybridCorridor"), _and(A("DieselOnlyRoute"), A("ElectrifiedRoute")))),
         "HybridCorridor", "Depot"),
    Case("sleeper-track", "field", "role-hierarchy",
         "Track asks: is a sleeper a track?",
         _tb((A("Sleeper"), A("TrackComponent")),
             (A("TrackComponent"), E("partOf", A("Track"))),
             transitive=["partOf"], hierarchy=[("partOf", "locatedIn")]),
         "Sleeper", "Track"),
]

_BY_ID = {c.id: c for c in CASES + FIELD_CASES}


def case(case_id: str) -> Case:
    """Look a case (labelled or field) up by id."""
    return _BY_ID[case_id]


def describe_kb(tbox: dl.TBox) -> str:
    """A neutral, textual rendering of a module — the reviewer's input.

    Deliberately *syntactic*: it states the axioms and role facts without naming
    the logic, so the naming task is not given away in the prompt.
    """
    lines = [f"axiom: {ax}" for ax in tbox.axioms]
    if tbox.transitive_roles:
        lines.append(f"transitive roles: {sorted(tbox.transitive_roles)}")
    if tbox.role_hierarchy:
        lines.append("role hierarchy: "
                     + ", ".join(f"{a} sub-role of {b}" for a, b in tbox.role_hierarchy))
    if tbox.functional_roles:
        lines.append(f"functional roles: {sorted(tbox.functional_roles)}")
    if tbox.nominals:
        lines.append(f"nominals: {sorted(tbox.nominals)}")
    return "\n".join(lines)


def _query_text(c: Case) -> str:
    return f"{c.request}  Formally: is {c.sub} subsumed by {c.sup}?"


def build_dataset(split: str = "all"):
    """The labelled corpus as ``dspy.Example`` rows (inputs: ``kb``, ``query``).

    Gold fields: ``gold_dl``, ``gold_subsumption`` (bool), plus ``constructors``
    and ``sub_satisfiable`` for diagnostics. ``split`` is ``train``, ``dev``,
    ``test`` or ``all``; the split is fixed by item, never random.
    """
    import dspy

    rows = []
    for c in CASES:
        if split not in ("all", c.split):
            continue
        t = c.tbox()
        rows.append(dspy.Example(
            id=c.id, split=c.split, phenomenon=c.phenomenon,
            kb=describe_kb(t), query=_query_text(c), sub=c.sub, sup=c.sup,
            gold_dl=c.gold_dl, gold_subsumption=bool(c.gold_subsumed),
            constructors=sorted(dl.constructors_used(t)),
            sub_satisfiable=dl.satisfiable(A(c.sub), t).satisfiable,
        ).with_inputs("kb", "query"))
    return rows


def field_requests():
    """Unlabelled production requests: the same inputs, **no gold fields**."""
    import dspy

    return [dspy.Example(id=c.id, split="field", kb=describe_kb(c.tbox()),
                         query=_query_text(c), sub=c.sub, sup=c.sup).with_inputs("kb", "query")
            for c in FIELD_CASES]


# --------------------------------------------------------------------------- #
# Guidelines a review scorer can report
# --------------------------------------------------------------------------- #
def _rulebook():
    from agentlab.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("s-for-transitive",
             "Start the name from S, not ALC, exactly when some role is declared "
             "transitive: S abbreviates ALC plus transitive roles."),
        Rule("h-for-role-hierarchy",
             "Add H exactly when the module declares a sub-role (role hierarchy) axiom."),
        Rule("i-for-inverse",
             "Add I exactly when some role is used inverted (written r-)."),
        Rule("q-for-qualified-number",
             "Use Q for number restrictions with a filler class (>=n r.C, <=n r.C) and N "
             "only for unqualified ones (>=n r.Top); never both."),
        Rule("no-unused-letters",
             "Do not add letters for constructors the module does not use: claiming more "
             "expressivity than needed sends the module to a heavier reasoner for nothing."),
        Rule("name-the-logic-exactly",
             "Report the name in the standard order -- base (ALC or S), then H, O, I, then "
             "Q/N/F -- e.g. ALCHIQ or SHIN, with no prose and no '(D)' suffix."),
        Rule("answer-true-or-false",
             "Answer the subsumption question with exactly 'true' or 'false'."),
        Rule("use-the-reasoner",
             "Never judge subsumption from the shape of the axioms. C is subsumed by D "
             "exactly when C and not D is unsatisfiable: follow definitions (==) on the "
             "right-hand side, and remember that 'only' (forall) never implies 'some'."),
        Rule("unsatisfiable-subsumed-by-everything",
             "If the subject class is unsatisfiable (its definition is contradictory) it is "
             "subsumed by every class: answer true, and flag the class as a modelling error."),
    ])


#: The guidelines a review scorer reports as violated.
DL_RULEBOOK = _rulebook()


# --------------------------------------------------------------------------- #
# Full-semantics interpretations: certificates for "not subsumed"
# --------------------------------------------------------------------------- #
@dataclass
class Interpretation:
    """A finite interpretation: a domain, concept extensions, role extensions.

    Concepts and roles not listed are empty. This evaluates the *full* concept
    language of the toolkit — inverses and (qualified) number restrictions
    included — which the ALC tableau does not.
    """

    domain: set
    concepts: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)

    def pairs(self, role) -> set:
        if isinstance(role, dl.Inverse):
            return {(b, a) for a, b in self.roles.get(role.role, set())}
        return set(self.roles.get(role, set()))

    def successors(self, x, role) -> set:
        return {b for a, b in self.pairs(role) if a == x}

    def ext(self, c) -> set:
        """The extension of a concept."""
        match c:
            case dl._Top():
                return set(self.domain)
            case dl._Bottom():
                return set()
            case dl.Atomic(name):
                return set(self.concepts.get(name, set())) & set(self.domain)
            case dl.Not(sub):
                return set(self.domain) - self.ext(sub)
            case dl.And(left, right):
                return self.ext(left) & self.ext(right)
            case dl.Or(left, right):
                return self.ext(left) | self.ext(right)
            case dl.Exists(role, filler):
                f = self.ext(filler)
                return {x for x in self.domain if self.successors(x, role) & f}
            case dl.ForAll(role, filler):
                f = self.ext(filler)
                return {x for x in self.domain if self.successors(x, role) <= f}
            case dl.AtLeast(n, role, filler):
                f = self.ext(filler)
                return {x for x in self.domain if len(self.successors(x, role) & f) >= n}
            case dl.AtMost(n, role, filler):
                f = self.ext(filler)
                return {x for x in self.domain if len(self.successors(x, role) & f) <= n}
        raise TypeError(f"not a concept: {c!r}")

    def violations(self, tbox: dl.TBox) -> list[str]:
        """Every axiom or role fact of ``tbox`` this interpretation breaks."""
        out = []
        for ax in tbox.axioms:
            left, right = self.ext(ax.left), self.ext(ax.right)
            if not left <= right:
                out.append(f"{ax}: {sorted(map(str, left - right))} in left, not right")
            if ax.equivalence and not right <= left:
                out.append(f"{ax}: {sorted(map(str, right - left))} in right, not left")
        for r in tbox.transitive_roles:
            rel = self.pairs(r)
            missing = {(a, d) for a, b in rel for c, d in rel if b == c} - rel
            if missing:
                out.append(f"transitive {r}: missing {sorted(missing)}")
        for r, s in tbox.role_hierarchy:
            if not self.pairs(r) <= self.pairs(s):
                out.append(f"{r} sub-role of {s}: {sorted(self.pairs(r) - self.pairs(s))} missing")
        return out

    def is_model_of(self, tbox: dl.TBox) -> bool:
        return not self.violations(tbox)


def is_countermodel(tbox: dl.TBox, sub: str, sup: str, interp: Interpretation) -> bool:
    """Does ``interp`` satisfy the module **and** put an instance of ``sub`` outside ``sup``?

    If so, ``sub ⊑ sup`` is certainly *not* entailed, under the full semantics.
    """
    return interp.is_model_of(tbox) and bool(interp.ext(A(sub)) - interp.ext(A(sup)))


def _I(domain, concepts, roles=None):
    return Interpretation(set(domain), {k: set(v) for k, v in concepts.items()},
                          {k: set(v) for k, v in (roles or {}).items()})


#: Countermodels for the "not subsumed" labels of **non-ALC** modules. The ALC
#: tableau cannot certify these on its own (it ignores the non-ALC constructors),
#: so each one is witnessed by a finite model checked under the full semantics.
CERTIFICATES: dict[str, Interpretation] = {
    "depot-signal-maintainer": _I({"d", "s"}, {"MaintenanceDepot": {"d"}, "Signal": {"s"}},
                                  {"isResponsibleFor": {("d", "s")}}),
    "double-slip-heavy": _I({"d", "m1", "m2"},
                            {"DoubleSlip": {"d"}, "Switch": {"d"}, "PointsMotor": {"m1", "m2"}},
                            {"hasPart": {("d", "m1"), ("d", "m2")}}),
    "interlocking-control-centre": _I(
        {"i", "s1", "s2"}, {"Interlocking": {"i"}, "Signal": {"s1", "s2"}},
        {"controls": {("i", "s1"), ("i", "s2")}, "supervises": {("i", "s1"), ("i", "s2")}}),
    "substation-feeder": _I({"s", "o"}, {"Substation": {"s"}, "OverheadLine": {"o"}},
                            {"feeds": {("s", "o")}, "connectedTo": {("s", "o")}}),
    "bay-platform-low-use": _I({"b", "t1", "t2"}, {"BayPlatform": {"b"}, "Platform": {"b"}},
                               {"servedBy": {("b", "t1"), ("b", "t2")}}),
    "junction-route": _I({"j", "a", "b", "c"}, {"Junction": {"j"}},
                         {"partOf": {("a", "j"), ("b", "j"), ("c", "j")},
                          "locatedIn": {("a", "j"), ("b", "j"), ("c", "j")}}),
    "patroller-inspector": _I({"p", "c"}, {"Patroller": {"p"}, "Culvert": {"c"}},
                              {"visits": {("p", "c")}}),
    "plain-line-detection": _I({"s", "a"},
                               {"PlainLineSection": {"s"}, "TrackSection": {"s"},
                                "AxleCounter": {"a"}},
                               {"hasPart": {("s", "a")}}),
    "depot-major": _I({"d", "t1", "t2"}, {"Depot": {"d"}, "Train": {"t1", "t2"}},
                      {"stabledAt": {("t1", "d"), ("t2", "d")},
                       "assignedTo": {("t1", "d"), ("t2", "d")}}),
    "underbridge-twin-track": _I({"u", "k"}, {"Underbridge": {"u"}, "Bridge": {"u"},
                                              "Track": {"k"}},
                                 {"carries": {("u", "k")}}),
    "sleeper-track": _I({"s", "t"}, {"Sleeper": {"s"}, "TrackComponent": {"s"}, "Track": {"t"}},
                        {"partOf": {("s", "t")}, "locatedIn": {("s", "t")}}),
}

ALC_CONSTRUCTORS = {"negation-atomic", "negation-full", "conjunction", "disjunction",
                     "existential", "qualified-existential", "universal"}


def validate_gold() -> dict[str, str]:
    """Re-derive every label with the engine; return how each verdict is certified.

    * the DL name must equal :func:`ch03_toolkit.dl_name`;
    * "subsumed" is certified by the tableau alone — it reasons over a weakening
      of the module (non-ALC constructors treated as opaque), so a subsumption it
      finds holds in the full logic too;
    * "not subsumed" is certified by the tableau when the module is pure ALC (the
      tableau is complete there), and otherwise by a countermodel in
      :data:`CERTIFICATES` checked under the full semantics.

    Field cases have no stored label; their tableau verdicts are certified the
    same way. Raises ``AssertionError`` on any disagreement.
    """
    how = {}
    for c in CASES + FIELD_CASES:
        t = c.tbox()
        verdict = dl.subsumes(A(c.sub), A(c.sup), t)
        if c.gold_dl is not None:
            assert dl.dl_name(t) == c.gold_dl, (c.id, dl.dl_name(t), c.gold_dl)
            assert verdict == c.gold_subsumed, (c.id, verdict, c.gold_subsumed)
        if verdict:
            how[c.id] = "subsumed: tableau (sound)"
        elif dl.constructors_used(t) <= ALC_CONSTRUCTORS:
            how[c.id] = "not subsumed: tableau (complete for ALC)"
        else:
            assert c.id in CERTIFICATES, f"{c.id}: non-ALC negative without a certificate"
            cert = CERTIFICATES[c.id]
            assert is_countermodel(t, c.sub, c.sup, cert), (c.id, cert.violations(t))
            how[c.id] = "not subsumed: countermodel (full semantics)"
    return how


# --------------------------------------------------------------------------- #
# What the role box licenses (for the "blind spot" problem)
# --------------------------------------------------------------------------- #
def rbox_licensed(axiom: dl.Axiom, tbox: dl.TBox) -> bool:
    """Is ``axiom`` a valid consequence of the module's role box alone?

    Accepts the three schemata that compile role facts into ALC axioms:

    * ``exists r.C <= exists s.C``   for a declared sub-role ``r`` of ``s``;
    * ``forall s.C <= forall r.C``   for a declared sub-role ``r`` of ``s``;
    * ``forall r.C <= forall r.(forall r.C)``  for a transitive ``r``.
    """
    if axiom.equivalence:
        return False
    left, right = axiom.left, axiom.right
    for r, s in tbox.role_hierarchy:
        if left == dl.Exists(r, getattr(left, "filler", None)) and right == dl.Exists(s, left.filler):
            return True
        if left == dl.ForAll(s, getattr(left, "filler", None)) and right == dl.ForAll(r, left.filler):
            return True
    for r in tbox.transitive_roles:
        if (isinstance(left, dl.ForAll) and left.role == r
                and right == dl.ForAll(r, dl.ForAll(r, left.filler))):
            return True
    return False


def risk_class(tbox: dl.TBox) -> str:
    """An *observable* feature of a module, for estimating heuristic reliability.

    ``negation`` if any axiom negates a class (contradictions become possible),
    else ``definitions`` if any axiom is an equivalence (subsumptions can arise
    through a definition's right-hand side), else ``plain``.
    """
    used = dl.constructors_used(tbox)
    if used & {"negation-atomic", "negation-full"}:
        return "negation"
    if any(ax.equivalence for ax in tbox.axioms):
        return "definitions"
    return "plain"


# --------------------------------------------------------------------------- #
# Agent tools (Part D)
# --------------------------------------------------------------------------- #
@dataclass
class ReviewWorkspace:
    """The module under review, and the agent's call log."""

    case_id: str
    tbox: dl.TBox = None
    log: object = None

    def __post_init__(self):
        from agentlab.tools import ToolCallLog

        self.tbox = self.tbox if self.tbox is not None else case(self.case_id).tbox()
        self.log = self.log or ToolCallLog()


def build_review_tools(ws: ReviewWorkspace):
    """The review agent's tools. ``check_subsumption`` is the expensive, sound one."""
    from agentlab.tools import make_tools

    def show_module() -> str:
        """Show the module under review: its axioms and role facts."""
        return describe_kb(ws.tbox)

    def dl_expressivity() -> str:
        """Report which DL constructors the module uses, and the DL name they imply.

        Call this before naming the logic -- the constructors, not your impression
        of the axioms, decide the name.
        """
        return json.dumps({"dl": dl.dl_name(ws.tbox),
                           "constructors": sorted(dl.constructors_used(ws.tbox))})

    def check_satisfiability(concept: str) -> str:
        """Can the named class have any instances at all under the module?

        An unsatisfiable class is a modelling error, and is subsumed by every class.
        """
        result = dl.satisfiable(A(concept), ws.tbox)
        return json.dumps({"concept": concept, "satisfiable": result.satisfiable,
                           "steps": result.steps})

    def check_subsumption(sub: str, sup: str) -> str:
        """Run the tableau reasoner: does the module entail that `sub` is subsumed by `sup`?

        Sound for ALC modules and sound for 'subsumed' in general; ignores
        transitivity, role hierarchies, inverses and number restrictions when
        searching for a counterexample. Call it instead of judging by eye.
        """
        result = dl.satisfiable(dl.And(A(sub), dl.Not(A(sup))), ws.tbox)
        return json.dumps({"sub": sub, "sup": sup, "subsumed": not result.satisfiable,
                           "steps": result.steps, "branches": result.branches})

    def tableau_trace(sub: str, sup: str) -> str:
        """The tableau expansion for `sub and not sup` -- the proof behind a verdict."""
        result = dl.satisfiable(dl.And(A(sub), dl.Not(A(sup))), ws.tbox, trace=True)
        return json.dumps({"subsumed": not result.satisfiable, "trace": result.trace[:25]})

    impls = [show_module, dl_expressivity, check_satisfiability, check_subsumption,
             tableau_trace]
    return make_tools(impls, ws.log)


# --------------------------------------------------------------------------- #
# Contamination twins (Part E): the Pizza ontology, three ways
# --------------------------------------------------------------------------- #
#: Each item: id, the famous module, the counterfactual edit, sub, sup, and the request.
#: The famous modules transcribe the Manchester Pizza tutorial (Horridge et al.) in
#: miniature; every verdict is re-derived by the tableau, and every module is pure ALC,
#: so every "not subsumed" is certified by completeness.

#: Each module holds only the axioms its question needs: a full Pizza TBox internalised
#: at every tableau node would exceed the teaching reasoner's step budget.

def _not_meat_or_fish(t: dl.TBox, cls: str) -> None:
    t.add(A(cls), _and(N(A("MeatTopping")), N(A("FishTopping"))))


def _vegetarian_pizza(t: dl.TBox) -> None:
    t.add(A("VegetarianPizza"),
          _and(A("Pizza"), F("hasTopping", N(dl.Or(A("MeatTopping"), A("FishTopping"))))),
          equivalence=True)


def _american_hot(jalapeno_hot: bool = True):
    def build():
        t = dl.TBox()
        t.add(A("SpicyTopping"), _and(A("PizzaTopping"), E("hasSpiciness", A("Hot"))),
              equivalence=True)
        t.add(A("SpicyPizza"), _and(A("Pizza"), E("hasTopping", A("SpicyTopping"))),
              equivalence=True)
        t.add(A("JalapenoPepperTopping"),
              _and(A("PizzaTopping"), E("hasSpiciness", A("Hot" if jalapeno_hot else "Mild"))))
        t.add(A("Mild"), N(A("Hot")))
        t.add(A("AmericanHot"), _and(A("Pizza"), E("hasTopping", A("MozzarellaTopping")),
                                     E("hasTopping", A("JalapenoPepperTopping"))))
        return t
    return build


def _margherita_vegetarian(closure: bool = True):
    def build():
        t = dl.TBox()
        t.add(A("MozzarellaTopping"), A("CheeseTopping"))
        t.add(A("TomatoTopping"), A("VegetableTopping"))
        _not_meat_or_fish(t, "CheeseTopping")
        _not_meat_or_fish(t, "VegetableTopping")
        _vegetarian_pizza(t)
        t.add(A("Margherita"), _and(A("Pizza"), E("hasTopping", A("MozzarellaTopping")),
                                    E("hasTopping", A("TomatoTopping"))))
        if closure:      # the tutorial's closure axiom: these toppings and no others
            t.add(A("Margherita"),
                  F("hasTopping", dl.Or(A("MozzarellaTopping"), A("TomatoTopping"))))
        return t
    return build


def _margherita_cheesy(mozzarella_is_cheese: bool = True):
    def build():
        t = dl.TBox()
        t.add(A("MozzarellaTopping"),
              A("CheeseTopping" if mozzarella_is_cheese else "VegetableTopping"))
        t.add(A("TomatoTopping"), A("VegetableTopping"))
        t.add(A("CheesyPizza"), _and(A("Pizza"), E("hasTopping", A("CheeseTopping"))),
              equivalence=True)
        t.add(A("Margherita"), _and(A("Pizza"), E("hasTopping", A("MozzarellaTopping")),
                                    E("hasTopping", A("TomatoTopping"))))
        return t
    return build


def _napoletana_vegetarian(anchovy_is_fish: bool = True):
    def build():
        t = dl.TBox()
        t.add(A("MozzarellaTopping"), A("CheeseTopping"))
        t.add(A("AnchoviesTopping"),
              A("FishTopping" if anchovy_is_fish else "VegetableTopping"))
        _not_meat_or_fish(t, "CheeseTopping")
        _not_meat_or_fish(t, "VegetableTopping")
        _vegetarian_pizza(t)
        t.add(A("Napoletana"), _and(A("Pizza"), E("hasTopping", A("MozzarellaTopping")),
                                    E("hasTopping", A("AnchoviesTopping"))))
        t.add(A("Napoletana"),
              F("hasTopping", dl.Or(A("MozzarellaTopping"), A("AnchoviesTopping"))))
        return t
    return build


def _ice_cream(domain: bool = True):
    def build():
        t = dl.TBox()
        t.add(A("IceCream"), E("hasTopping", A("FruitTopping")))
        if domain:       # the tutorial's domain axiom: hasTopping has domain Pizza
            t.add(E("hasTopping", dl.Top), A("Pizza"))
        return t
    return build


#: (id, request, sub, sup, famous module, counterfactual module)
PIZZA_ITEMS = [
    ("american-hot-spicy", "is an American Hot a spicy pizza?", "AmericanHot", "SpicyPizza",
     _american_hot(), _american_hot(jalapeno_hot=False)),
    ("margherita-vegetarian", "is a Margherita a vegetarian pizza?", "Margherita",
     "VegetarianPizza", _margherita_vegetarian(), _margherita_vegetarian(closure=False)),
    ("margherita-cheesy", "is a Margherita a cheesy pizza?", "Margherita", "CheesyPizza",
     _margherita_cheesy(), _margherita_cheesy(mozzarella_is_cheese=False)),
    ("napoletana-vegetarian", "is a Napoletana a vegetarian pizza?", "Napoletana",
     "VegetarianPizza", _napoletana_vegetarian(), _napoletana_vegetarian(anchovy_is_fish=False)),
    ("ice-cream-pizza", "is ice cream a pizza?", "IceCream", "Pizza",
     _ice_cream(), _ice_cream(domain=False)),
]

VARIANTS = ("famous", "renamed", "counterfactual")

#: Names that carry no world knowledge (same axioms, nothing to remember).
RENAME = {
    "Pizza": "Vorn", "PizzaTopping": "Larm", "CheeseTopping": "Quib", "VegetableTopping": "Sesk",
    "MeatTopping": "Drolt", "FishTopping": "Mesp", "MozzarellaTopping": "Tavik",
    "TomatoTopping": "Ponel", "AnchoviesTopping": "Grusk", "VegetarianPizza": "Ulvorn",
    "CheesyPizza": "Quivorn", "Margherita": "Belsa", "SpicyTopping": "Harrel",
    "SpicyPizza": "Harvorn", "JalapenoPepperTopping": "Zintel", "Hot": "Fesk", "Mild": "Omb",
    "AmericanHot": "Corvel", "Napoletana": "Ristane", "IceCream": "Wemmock",
    "FruitTopping": "Pallid", "hasTopping": "hasLarm", "hasSpiciness": "hasFesk",
}


def rename_concept(c, names: dict):
    """The concept with every class and role renamed (unknown names kept)."""
    role = lambda r: (dl.Inverse(names.get(r.role, r.role)) if isinstance(r, dl.Inverse)
                      else names.get(r, r))
    match c:
        case dl.Atomic(name):
            return dl.Atomic(names.get(name, name))
        case dl.Not(sub):
            return dl.Not(rename_concept(sub, names))
        case dl.And(left, right):
            return dl.And(rename_concept(left, names), rename_concept(right, names))
        case dl.Or(left, right):
            return dl.Or(rename_concept(left, names), rename_concept(right, names))
        case dl.Exists(r, filler):
            return dl.Exists(role(r), rename_concept(filler, names))
        case dl.ForAll(r, filler):
            return dl.ForAll(role(r), rename_concept(filler, names))
        case dl.AtLeast(n, r, filler):
            return dl.AtLeast(n, role(r), rename_concept(filler, names))
        case dl.AtMost(n, r, filler):
            return dl.AtMost(n, role(r), rename_concept(filler, names))
    return c                      # Top, Bottom


def rename_tbox(tbox: dl.TBox, names: dict = RENAME) -> dl.TBox:
    """A copy of ``tbox`` with every name replaced: same structure, nothing to remember."""
    out = dl.TBox()
    for ax in tbox.axioms:
        out.add(rename_concept(ax.left, names), rename_concept(ax.right, names),
                ax.equivalence)
    out.transitive_roles = {names.get(r, r) for r in tbox.transitive_roles}
    out.role_hierarchy = [(names.get(a, a), names.get(b, b)) for a, b in tbox.role_hierarchy]
    return out


def contamination_tbox(item_id: str, variant: str) -> tuple[dl.TBox, str, str, str]:
    """``(tbox, sub, sup, request)`` for one item in one variant."""
    item = next(i for i in PIZZA_ITEMS if i[0] == item_id)
    _, request, sub, sup, famous, counter = item
    if variant == "counterfactual":
        return counter(), sub, sup, f"Menu data asks: {request}"
    t = famous()
    if variant == "famous":
        return t, sub, sup, f"Menu data asks: {request}"
    return (rename_tbox(t), RENAME[sub], RENAME[sup],
            f"Catalogue data asks: is every {RENAME[sub]} a {RENAME[sup]}?")


def contamination_dataset():
    """15 rows (5 items x 3 variants); gold is the tableau's verdict on *that* module.

    Every module is pure ALC, so every verdict -- "not subsumed" included -- is
    certified by the tableau's completeness. Rows carry ``variant`` and ``item``.
    """
    import dspy

    rows = []
    for item_id, *_ in PIZZA_ITEMS:
        for variant in VARIANTS:
            t, sub, sup, request = contamination_tbox(item_id, variant)
            assert dl.constructors_used(t) <= ALC_CONSTRUCTORS, (item_id, variant)
            rows.append(dspy.Example(
                id=f"{item_id}/{variant}", item=item_id, variant=variant, split="pizza",
                phenomenon="contamination", kb=describe_kb(t),
                query=f"{request}  Formally: is {sub} subsumed by {sup}?", sub=sub, sup=sup,
                gold_dl=dl.dl_name(t), gold_subsumption=dl.subsumes(A(sub), A(sup), t),
                constructors=sorted(dl.constructors_used(t)),
                sub_satisfiable=dl.satisfiable(A(sub), t).satisfiable,
            ).with_inputs("kb", "query"))
    return rows


# --------------------------------------------------------------------------- #
# SIP's fleet ontology as review modules (Part E2)
# --------------------------------------------------------------------------- #
#: Transcribed from the fleet ontology SIP's demo builds (``sip/semantic_intelligence/
#: demo.py``): vehicles, engines, wheels, manufacturers. Never published, so no model
#: has read it; the questions are the ones SIP's validate stage would ask.
FLEET_CASES: list[Case] = [
    Case("fleet-car-motorised", "fleet", "inferred-definition",
         "Fleet asks: is every car a motorised vehicle?",
         _tb((A("Car"), A("Vehicle")),
             (A("Vehicle"), E("hasEngine", A("Engine"))),
             equiv=[(A("MotorisedVehicle"), _and(A("Vehicle"), E("hasEngine", A("Engine"))))]),
         "Car", "MotorisedVehicle"),
    Case("fleet-truck-diesel-open", "fleet", "universal-trap",
         "Fleet asks: is every truck a diesel vehicle?",
         _tb((A("Truck"), _and(A("Vehicle"), F("hasEngine", A("DieselEngine")))),
             equiv=[(A("DieselVehicle"), _and(A("Vehicle"), E("hasEngine", A("DieselEngine"))))]),
         "Truck", "DieselVehicle"),
    Case("fleet-truck-diesel-closed", "fleet", "inferred-definition",
         "Fleet asks: is every truck a diesel vehicle? (vehicles must have an engine)",
         _tb((A("Truck"), _and(A("Vehicle"), F("hasEngine", A("DieselEngine")))),
             (A("Vehicle"), E("hasEngine", A("Engine"))),
             equiv=[(A("DieselVehicle"), _and(A("Vehicle"), E("hasEngine", A("DieselEngine"))))]),
         "Truck", "DieselVehicle"),
    Case("fleet-hybrid-unsat", "fleet", "unsatisfiable-subject",
         "Data quality asks: is a hybrid fleet vehicle a manufacturer? (the class came from a merge)",
         _tb((A("ElectricVehicle"), _and(A("Vehicle"), F("hasEngine", N(A("DieselEngine"))))),
             (A("HybridFleetVehicle"), _and(A("ElectricVehicle"), A("DieselVehicle"))),
             equiv=[(A("DieselVehicle"), _and(A("Vehicle"), E("hasEngine", A("DieselEngine"))))]),
         "HybridFleetVehicle", "Manufacturer"),
    Case("fleet-alloy-wheel-part", "fleet", "transitive-told",
         "Fleet asks: is an alloy wheel a vehicle part?",
         _tb((A("AlloyWheel"), A("Wheel")),
             (A("Wheel"), A("VehiclePart")),
             (A("VehiclePart"), E("partOf", A("Vehicle"))),
             transitive=["partOf"]),
         "AlloyWheel", "VehiclePart"),
    Case("fleet-manufacturer-supplier", "fleet", "universal-trap",
         "Procurement asks: is every manufacturer a supplier?",
         _tb((A("Manufacturer"), _and(A("Organisation"), E("makes", A("Vehicle")))),
             equiv=[(A("Supplier"), _and(A("Organisation"), E("supplies", A("Vehicle"))))]),
         "Manufacturer", "Supplier"),
    Case("fleet-truck-car", "fleet", "sibling",
         "Fleet asks: is every truck a car?",
         _tb((A("Car"), A("Vehicle")), (A("Truck"), A("Vehicle"))),
         "Truck", "Car"),
]
_BY_ID.update({c.id: c for c in FLEET_CASES})


def fleet_dataset():
    """SIP's fleet modules as rows; gold is re-derived by the tableau, as for the corpus.

    Every fleet module is ALC or S, and every "not subsumed" verdict is on a pure-ALC
    module, so the tableau certifies each label (checked here, not assumed).
    """
    import dspy

    rows = []
    for c in FLEET_CASES:
        t = c.tbox()
        verdict = dl.subsumes(A(c.sub), A(c.sup), t)
        assert verdict or dl.constructors_used(t) <= ALC_CONSTRUCTORS, c.id
        rows.append(dspy.Example(
            id=c.id, split="fleet", phenomenon=c.phenomenon, kb=describe_kb(t),
            query=_query_text(c), sub=c.sub, sup=c.sup, gold_dl=dl.dl_name(t),
            gold_subsumption=verdict, constructors=sorted(dl.constructors_used(t)),
            sub_satisfiable=dl.satisfiable(A(c.sub), t).satisfiable,
        ).with_inputs("kb", "query"))
    return rows
