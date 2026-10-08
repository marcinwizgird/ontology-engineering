"""Chapter 10 problem-set support — choosing a formalism for an ED ontology, and pricing it.

Provided code for ``04_assignment.ipynb``. The scenario: the Emergency Department
of Northfield General Hospital is building a **patient-flow and sepsis
early-warning ontology**. Its clinical-informatics lead has a backlog of
requirements, each imperfect in exactly one way — something that happens over
**time**, a predicate with **no sharp boundary**, data too **coarse** to separate
the cases, or none of these. The student builds the grader, the Claude advisor
and the review agent in the notebook; this module supplies what a real project
would already have:

* the ED's **data** — triage vitals (:data:`VITALS`), the vague predicates the
  clinicians use (:data:`VAGUE_PREDICATES`), the coded triage log
  (:data:`TRIAGE_LOG`) and the registration table (:data:`REGISTRY`);
* the **requirements backlog** (:data:`REQUIREMENTS`, 24 items, 6 per formalism,
  split 8 / 8 / 8 by item) — every item carries a *witness* drawn from that data,
  and :func:`validate_gold` re-derives every gold label from its witness with the
  Chapter 10 engine, so no label rests on anyone's say-so;
* the **price list** (:data:`EXPRESSIVITY_COST`) and the guidelines a scorer
  reports (:data:`FORMALISM_RULEBOOK`);
* the **sepsis-bundle protocol** as an Allen network, a proposed amendment, and a
  network on which path consistency is blind (:data:`PC_BLIND_SPOT`);
* **agent tools** over the engine (:func:`build_review_tools`);
* **constraint propagation as an MDP** (:class:`PropagationMDP`).

The thesis of the chapter, which the scorer has to encode: *expressivity is never
free*. Deciding consistency of a general Allen network is NP-complete; fuzzy
membership and rough approximation are polynomial. An answer that picks the right
formalism but cannot say what it costs is half an answer.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field

import ch10_toolkit as ch10

__all__ = [
    "EXPRESSIVITY_COST", "FORMALISMS", "COST_LEVELS", "FORMALISM_WHY",
    "VAGUE_PREDICATES", "degree", "VITALS", "TRIAGE_LOG", "TRIAGE_TARGETS",
    "REGISTRY", "REGISTRY_TARGETS", "Requirement", "REQUIREMENTS",
    "witness_formalism", "validate_gold", "build_dataset", "requirement_data",
    "FORMALISM_RULEBOOK", "SEPSIS_PROTOCOL", "PROTOCOL_AMENDMENT", "PC_BLIND_SPOT",
    "ReviewWorkspace", "build_review_tools", "PropagationMDP", "MDP_RELATIONS",
]


# --------------------------------------------------------------------------- #
# The price list
# --------------------------------------------------------------------------- #
FORMALISMS = ("crisp", "fuzzy", "rough", "temporal")
COST_LEVELS = ("none", "low", "high")

#: What each formalism costs to reason with. These are not stylistic labels:
#: deciding consistency of a general Allen network is NP-complete, while fuzzy
#: membership and rough approximation are polynomial.
EXPRESSIVITY_COST = {
    "crisp": "none",
    "fuzzy": "low",
    "rough": "low",
    "temporal": "high",
}

#: One sentence per formalism: when it is the right tool.
FORMALISM_WHY = {
    "crisp": "the boundary is sharp by definition (identifiers, legal limits, codes); "
             "extra machinery buys nothing and costs reasoning time",
    "fuzzy": "the predicate is vague -- it has no sharp boundary, so any threshold is "
             "arbitrary exactly where the decision is hard",
    "rough": "the recorded attributes cannot separate some cases, so the target is only "
             "describable by a lower and an upper approximation",
    "temporal": "the requirement relates things that happen over intervals of time "
                "(before, during, overlapping, meeting)",
}


# --------------------------------------------------------------------------- #
# The ED's data
# --------------------------------------------------------------------------- #
#: The vague predicates the ED's clinicians use, as trapezoidal membership
#: functions: name -> (unit, (a, b, c, d)); 0 below a, 1 on [b, c], 0 above d.
VAGUE_PREDICATES: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "high_fever": ("degC", (37.5, 38.5, 50.0, 50.0)),
    "tachycardia": ("beats/min", (90.0, 110.0, 300.0, 300.0)),
    "low_oxygen": ("SpO2 %", (0.0, 0.0, 90.0, 95.0)),
    "elderly": ("years", (60.0, 80.0, 150.0, 150.0)),
    "long_wait": ("minutes", (120.0, 240.0, 100000.0, 100000.0)),
    "overcrowded": ("occupancy %", (85.0, 100.0, 1000.0, 1000.0)),
}


def degree(predicate: str, value: float) -> float:
    """Membership degree of ``value`` in one of the ED's vague predicates."""
    _, (a, b, c, d) = VAGUE_PREDICATES[predicate]
    return round(ch10.trapezoid(a, b, c, d)(float(value)), 4)


#: Triage vitals for twelve ED visits on one evening: visit -> (temp degC, heart rate).
VITALS: dict[str, tuple[float, int]] = {
    "v01": (39.2, 118), "v02": (38.1, 96), "v03": (37.4, 104), "v04": (38.6, 112),
    "v05": (37.9, 88), "v06": (36.8, 72), "v07": (37.2, 80), "v08": (38.4, 101),
    "v09": (38.0, 94), "v10": (37.6, 125), "v11": (36.9, 76), "v12": (39.5, 108),
}

#: The coded triage log for the same visits: what the old triage screen kept.
#: Several visits are identical on every coded field — v01/v02, v04/v05, v06/v07.
TRIAGE_LOG = ch10.InformationSystem({
    "v01": {"acuity": "high", "arrival": "ambulance", "fever": "yes", "age_band": "65+"},
    "v02": {"acuity": "high", "arrival": "ambulance", "fever": "yes", "age_band": "65+"},
    "v03": {"acuity": "high", "arrival": "ambulance", "fever": "no", "age_band": "<65"},
    "v04": {"acuity": "high", "arrival": "walk-in", "fever": "yes", "age_band": "<65"},
    "v05": {"acuity": "high", "arrival": "walk-in", "fever": "yes", "age_band": "<65"},
    "v06": {"acuity": "low", "arrival": "walk-in", "fever": "no", "age_band": "<65"},
    "v07": {"acuity": "low", "arrival": "walk-in", "fever": "no", "age_band": "<65"},
    "v08": {"acuity": "low", "arrival": "ambulance", "fever": "no", "age_band": "65+"},
    "v09": {"acuity": "low", "arrival": "walk-in", "fever": "yes", "age_band": "65+"},
    "v10": {"acuity": "high", "arrival": "ambulance", "fever": "no", "age_band": "65+"},
    "v11": {"acuity": "low", "arrival": "walk-in", "fever": "no", "age_band": "65+"},
    "v12": {"acuity": "low", "arrival": "ambulance", "fever": "yes", "age_band": "<65"},
})

#: Outcomes known from the discharge records (not from the triage screen).
TRIAGE_TARGETS: dict[str, list[str]] = {
    "icu": ["v01", "v03", "v04", "v05", "v10"],
    "sepsis": ["v01", "v04", "v05", "v09", "v12"],
    "readmitted": ["v08", "v09", "v10", "v11"],
    "frequent_attender": ["v06", "v11", "v12"],
    "infection": ["v01", "v02", "v03", "v04", "v05", "v09", "v12"],
    "emergency_surgery": ["v03", "v08", "v10"],
}

#: The registration table: every field is a code or an identifier.
REGISTRY = ch10.InformationSystem({
    "r1": {"mrn": "MRN-1001", "ward": "7", "minor": "no", "penicillin_allergy": "no", "mts": "2"},
    "r2": {"mrn": "MRN-1002", "ward": "7", "minor": "no", "penicillin_allergy": "yes", "mts": "3"},
    "r3": {"mrn": "MRN-1003", "ward": "ICU", "minor": "no", "penicillin_allergy": "no", "mts": "1"},
    "r4": {"mrn": "MRN-1004", "ward": "8", "minor": "yes", "penicillin_allergy": "no", "mts": "4"},
    "r5": {"mrn": "MRN-1005", "ward": "ICU", "minor": "no", "penicillin_allergy": "yes", "mts": "1"},
    "r6": {"mrn": "MRN-1006", "ward": "8", "minor": "yes", "penicillin_allergy": "yes", "mts": "3"},
    "r7": {"mrn": "MRN-1007", "ward": "7", "minor": "no", "penicillin_allergy": "no", "mts": "5"},
    "r8": {"mrn": "MRN-1008", "ward": "8", "minor": "no", "penicillin_allergy": "no", "mts": "2"},
})

REGISTRY_TARGETS: dict[str, list[str]] = {
    "all_patients": ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"],
    "ward_7": ["r1", "r2", "r7"],
    "icu_beds": ["r3", "r5"],
    "minors": ["r4", "r6"],
    "penicillin_allergic": ["r2", "r5", "r6"],
    "immediate_or_very_urgent": ["r1", "r3", "r5", "r8"],
}


# --------------------------------------------------------------------------- #
# The requirements backlog
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Requirement:
    """One backlog item: the English, its fixed split, its gold label, its evidence.

    ``witness`` is the data the stakeholder attached, tagged by kind:

    * ``("allen", constraints, instance)`` — interval constraints between named
      episodes, and one concrete timeline that satisfies them;
    * ``("vague", predicate, observed_values)``;
    * ``("granular", table, attributes, target)`` — a table, the attributes the
      system records, and the set the requirement must describe;
    * ``("exact", table, attributes, target)`` — the same shape, for sets that
      the recorded codes decide exactly.
    """

    id: str
    split: str
    text: str
    formalism: str
    witness: tuple


def _allen(constraints: dict, instance: dict) -> tuple:
    return ("allen", {k: tuple(sorted(v)) for k, v in constraints.items()}, instance)


#: 24 items, 6 per formalism; split fixed by item, 2 per formalism per split.
REQUIREMENTS: list[Requirement] = [
    # --- train ---------------------------------------------------------------
    Requirement("cultures-before-antibiotics", "train",
                "Blood cultures must be taken before the first antibiotic dose is given.",
                "temporal", _allen({("Cultures", "Antibiotics"): {"b", "m"}},
                                   {"Cultures": (0, 2), "Antibiotics": (3, 6)})),
    Requirement("handover-overlap", "train",
                "The nursing handover starts before the day shift ends and runs into the "
                "night shift.",
                "temporal", _allen({("Handover", "DayShift"): {"oi"},
                                    ("Handover", "NightShift"): {"o"},
                                    ("DayShift", "NightShift"): {"m"}},
                                   {"DayShift": (0, 10), "NightShift": (10, 20),
                                    "Handover": (9, 11)})),
    Requirement("fever-escalation", "train",
                "Escalate to the sepsis pathway any patient with a high temperature.",
                "fuzzy", ("vague", "high_fever", [37.2, 37.9, 38.3, 39.1])),
    Requirement("falls-assessment", "train",
                "Offer a falls assessment to elderly patients.",
                "fuzzy", ("vague", "elderly", [58, 66, 72, 84])),
    Requirement("icu-from-triage", "train",
                "From the acuity and arrival mode on the triage screen, identify which "
                "patients went on to need intensive care.",
                "rough", ("granular", "triage_log", ["acuity", "arrival"], "icu")),
    Requirement("frequent-attender", "train",
                "Define the frequent-attender cohort from the registration fields; visits "
                "the system records with identical field values have to be handled as one.",
                "rough", ("granular", "triage_log",
                          ["acuity", "arrival", "fever", "age_band"], "frequent_attender")),
    Requirement("one-mrn", "train",
                "Every patient has exactly one medical record number.",
                "crisp", ("exact", "registry", ["mrn"], "all_patients")),
    Requirement("minor-consent", "train",
                "Patients under 16 need a parent's or guardian's consent before surgery.",
                "crisp", ("exact", "registry", ["minor"], "minors")),
    # --- dev -----------------------------------------------------------------
    Requirement("ct-while-fasting", "dev",
                "A contrast CT may only be scheduled while the patient is fasting.",
                "temporal", _allen({("CT", "Fasting"): {"d", "s", "f", "eq"}},
                                   {"Fasting": (0, 8), "CT": (3, 4)})),
    Requirement("isolation-covers-stay", "dev",
                "A patient with suspected influenza stays in isolation for the whole of "
                "their ward admission.",
                "temporal", _allen({("Admission", "Isolation"): {"d", "s", "f", "eq"}},
                                   {"Isolation": (0, 9), "Admission": (1, 9)})),
    Requirement("long-wait-alert", "dev",
                "Notify the duty manager when a patient has been waiting a long time for a "
                "bed.",
                "fuzzy", ("vague", "long_wait", [90, 150, 200, 300])),
    Requirement("fast-heart-rate", "dev",
                "Flag any patient whose heart rate is fast.",
                "fuzzy", ("vague", "tachycardia", [85, 98, 105, 120])),
    Requirement("sepsis-audit", "dev",
                "For the sepsis audit, decide which past visits were sepsis cases using only "
                "the coded acuity and fever fields; some visits have identical codes but "
                "different discharge diagnoses.",
                "rough", ("granular", "triage_log", ["acuity", "fever"], "sepsis")),
    Requirement("readmission-cohort", "dev",
                "Group patients into a readmission-risk cohort using only the age band and "
                "arrival mode taken at the front desk.",
                "rough", ("granular", "triage_log", ["age_band", "arrival"], "readmitted")),
    Requirement("ward-capacity", "dev",
                "Ward 7 holds at most 24 beds.",
                "crisp", ("exact", "registry", ["ward"], "ward_7")),
    Requirement("penicillin-allergy", "dev",
                "A patient recorded as allergic to penicillin must not be prescribed "
                "penicillin.",
                "crisp", ("exact", "registry", ["penicillin_allergy"], "penicillin_allergic")),
    # --- test ----------------------------------------------------------------
    Requirement("anticoagulation-pause", "test",
                "Anticoagulation is paused before surgery begins and may not resume until "
                "the operation has finished.",
                "temporal", _allen({("Pause", "Surgery"): {"di", "fi"}},
                                   {"Pause": (0, 10), "Surgery": (4, 7)})),
    Requirement("imaging-after-triage", "test",
                "Imaging is requested only after triage has been completed, and must be "
                "reported within the same ED stay.",
                "temporal", _allen({("Triage", "Imaging"): {"b", "m"},
                                    ("Imaging", "Stay"): {"d", "f"},
                                    ("Triage", "Stay"): {"s"}},
                                   {"Stay": (0, 12), "Triage": (0, 2), "Imaging": (4, 7)})),
    Requirement("low-saturation", "test",
                "Prioritise patients whose oxygen saturation is low.",
                "fuzzy", ("vague", "low_oxygen", [88, 92, 94, 97])),
    Requirement("ambulance-diversion", "test",
                "Divert incoming ambulances when the department is overcrowded.",
                "fuzzy", ("vague", "overcrowded", [80, 92, 97, 110])),
    Requirement("infection-from-legacy", "test",
                "The legacy system stores only 'fever: yes/no'; from it, work out which "
                "patients had a clinically significant infection.",
                "rough", ("granular", "triage_log", ["fever"], "infection")),
    Requirement("surgery-from-acuity", "test",
                "Classify which past ED visits ended in emergency surgery, using only the "
                "acuity flag the old triage screen kept.",
                "rough", ("granular", "triage_log", ["acuity"], "emergency_surgery")),
    Requirement("icu-bed-ventilator", "test",
                "Every ICU bed has a ventilator connection point.",
                "crisp", ("exact", "registry", ["ward"], "icu_beds")),
    Requirement("mts-category", "test",
                "Each patient is assigned exactly one of the five Manchester Triage System "
                "categories.",
                "crisp", ("exact", "registry", ["mts"], "immediate_or_very_urgent")),
]

_TABLES = {"triage_log": (TRIAGE_LOG, TRIAGE_TARGETS), "registry": (REGISTRY, REGISTRY_TARGETS)}


def _approximation(table: str, attributes, target: str) -> dict:
    system, targets = _TABLES[table]
    members = targets[target]
    return {"lower": system.lower_approximation(members, attributes),
            "upper": system.upper_approximation(members, attributes),
            "boundary": system.boundary(members, attributes),
            "accuracy": system.accuracy(members, attributes)}


def witness_formalism(req: Requirement) -> str:
    """Re-derive a requirement's formalism from its witness, using the engine.

    * interval constraints: every label is a proper subset of the 13 relations,
      the network is path-consistent, and the attached timeline satisfies every
      constraint (a concrete model — so consistency is *proven*, not assumed);
    * vague predicate: some observed value has a membership strictly between 0
      and 1 — the data sits on the boundary a threshold would cut;
    * table + target: rough iff the boundary region is non-empty (accuracy < 1);
      crisp iff the recorded codes decide membership exactly.
    """
    kind = req.witness[0]
    if kind == "allen":
        _, constraints, instance = req.witness
        nodes = tuple(sorted({n for pair in constraints for n in pair}))
        assert all(0 < len(v) < len(ch10.ALLEN_RELATIONS) for v in constraints.values())
        network = ch10.Network.complete(nodes, {k: set(v) for k, v in constraints.items()})
        assert ch10.path_consistent(network)["consistent"], req.id
        for (i, j), relations in constraints.items():
            assert ch10.relation_between(instance[i], instance[j]) in relations, (req.id, i, j)
        return "temporal"
    if kind == "vague":
        _, predicate, values = req.witness
        degrees = [degree(predicate, v) for v in values]
        return "fuzzy" if any(0.0 < d < 1.0 for d in degrees) else "crisp"
    _, table, attributes, target = req.witness
    return "rough" if _approximation(table, attributes, target)["accuracy"] < 1.0 else "crisp"


def validate_gold() -> dict[str, str]:
    """Assert every gold label equals the formalism its witness demonstrates.

    Also asserts the split is balanced: 2 items per formalism per split.
    Returns ``{id: formalism}``.
    """
    derived = {}
    for req in REQUIREMENTS:
        got = witness_formalism(req)
        assert got == req.formalism, f"{req.id}: witness says {got}, gold says {req.formalism}"
        derived[req.id] = got
    assert len({r.id for r in REQUIREMENTS}) == len(REQUIREMENTS) == 24
    for split in ("train", "dev", "test"):
        for formalism in FORMALISMS:
            n = sum(1 for r in REQUIREMENTS if r.split == split and r.formalism == formalism)
            assert n == 2, (split, formalism, n)
    return derived


def build_dataset(split: str = "all"):
    """The backlog as ``dspy.Example`` rows (input: ``requirement``)."""
    import dspy

    rows = [
        dspy.Example(id=r.id, split=r.split, requirement=r.text,
                     gold_formalism=r.formalism,
                     gold_cost=EXPRESSIVITY_COST[r.formalism]).with_inputs("requirement")
        for r in REQUIREMENTS
    ]
    return rows if split == "all" else [r for r in rows if r.split == split]


def requirement_data(requirement_id: str) -> dict:
    """What the stakeholder attached to a requirement — *without* the gold label.

    Tables and targets look the same whether the answer is rough or crisp: the
    reviewer has to run the approximation to tell.
    """
    req = next(r for r in REQUIREMENTS if r.id == requirement_id)
    kind = req.witness[0]
    out: dict = {"id": req.id, "requirement": req.text}
    if kind == "allen":
        _, constraints, _ = req.witness
        out["proposed_interval_constraints"] = {f"{i},{j}": list(v)
                                                for (i, j), v in constraints.items()}
    elif kind == "vague":
        _, predicate, values = req.witness
        out["measure"] = predicate
        out["unit"] = VAGUE_PREDICATES[predicate][0]
        out["observed_values"] = list(values)
    else:
        _, table, attributes, target = req.witness
        out["table"] = table
        out["recorded_attributes"] = list(attributes)
        out["target_set"] = target
    return out


# --------------------------------------------------------------------------- #
# The guidelines a scorer reports
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("answer-with-a-label",
             "Answer the formalism with exactly one of: crisp, fuzzy, rough, temporal; and "
             "the cost with exactly one of: none, low, high. No prose in those fields."),
        Rule("temporal-for-interval-relations",
             "When the requirement relates things that happen over time -- before, during, "
             "overlapping, meeting, until -- use an interval temporal formalism (Allen)."),
        Rule("fuzzy-for-vague-predicates",
             "When the predicate has no sharp boundary (high temperature, elderly, long "
             "wait, overcrowded), use fuzzy membership; a crisp threshold is arbitrary "
             "exactly where the decision matters."),
        Rule("rough-for-indiscernible-data",
             "When the recorded attributes cannot tell some cases apart (identical codes, "
             "different outcomes; only a coarse field is kept), use rough sets and report a "
             "lower and an upper approximation."),
        Rule("crisp-when-boundaries-are-sharp",
             "When identifiers, codes, legal limits and exact counts are involved, stay "
             "crisp: extra machinery buys nothing and costs reasoning time. A number in the "
             "requirement does not make it vague -- 'under 16' is a legal line."),
        Rule("price-the-expressivity",
             "State the reasoning cost of the formalism: none for crisp, low for fuzzy and "
             "rough (polynomial), high for interval temporal reasoning (consistency of a "
             "general Allen network is NP-complete)."),
    ])


#: The guidelines a formalism scorer reports as violated.
FORMALISM_RULEBOOK = _rulebook()


# --------------------------------------------------------------------------- #
# The sepsis-bundle protocol (Part A) -- as an Allen network
# --------------------------------------------------------------------------- #
#: The ED's written protocol, as constraints between named episodes.
SEPSIS_PROTOCOL: dict[tuple[str, str], set[str]] = {
    ("Triage", "Bundle"): {"s"},             # triage opens the one-hour bundle window
    ("Triage", "Cultures"): {"b", "m"},      # cultures after triage ...
    ("Cultures", "Antibiotics"): {"b", "m"},  # ... and before the first antibiotic dose
    ("Antibiotics", "Bundle"): {"d", "f", "oi"},  # antibiotics start inside the window
    ("Lactate", "Bundle"): {"d", "f"},       # lactate measured within the window
}

#: A proposed amendment from the pharmacy committee: give antibiotics at triage.
PROTOCOL_AMENDMENT: dict[tuple[str, str], set[str]] = {
    ("Triage", "Antibiotics"): {"s", "si", "eq"},
}

#: A four-interval network that path consistency *accepts* but that has no
#: model (checked by exhaustive enumeration of endpoint orders). It is the
#: witness that path consistency is sound for inconsistency but incomplete.
PC_BLIND_SPOT: dict[tuple[str, str], set[str]] = {
    ("A", "B"): {"s", "f"},
    ("A", "C"): {"o", "oi"},
    ("A", "D"): {"b", "bi"},
    ("B", "C"): {"si", "fi"},
    ("B", "D"): {"m", "oi"},
    ("C", "D"): {"b", "mi"},
}


# --------------------------------------------------------------------------- #
# Agent tools (Part D)
# --------------------------------------------------------------------------- #
@dataclass
class ReviewWorkspace:
    """What the requirements-review agent can see: the backlog data and its call log."""

    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()


def build_review_tools(ws: ReviewWorkspace):
    """The review agent's tools: read a requirement's data, and run the engine on it."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def get_requirement(requirement_id: str) -> str:
        """The requirement text and the data the stakeholder attached to it.

        Depending on the requirement this is a set of proposed interval constraints,
        a measure with observed values, or a table, its recorded attributes and a
        target set.
        """
        return json.dumps(requirement_data(requirement_id))

    def check_temporal_consistency(constraints: str) -> str:
        """Path-consistency check of an interval network.

        `constraints` is JSON like {"A,B": ["b", "m"], "B,C": ["d"]} using Allen codes
        b bi m mi o oi s si d di f fi eq. Returns consistent true/false and, when false,
        the pair whose label emptied. Sound for inconsistency, incomplete for consistency.
        """
        raw = json.loads(constraints)
        nodes, parsed = set(), {}
        for key, relations in raw.items():
            i, j = [part.strip() for part in key.split(",")]
            nodes.update([i, j])
            parsed[(i, j)] = set(relations)
        network = ch10.Network.complete(tuple(sorted(nodes)), parsed)
        result = ch10.path_consistent(network)
        result["narrowed"] = network.summary()
        return json.dumps(result)

    def fuzzy_degree(measure: str, value: float) -> str:
        """Membership degree of a value in one of the ED's vague predicates.

        Measures: high_fever, tachycardia, low_oxygen, elderly, long_wait, overcrowded.
        A degree strictly between 0 and 1 means the value sits where a crisp threshold
        would be arbitrary.
        """
        if measure not in VAGUE_PREDICATES:
            return json.dumps({"error": f"unknown measure {measure!r}",
                               "available": sorted(VAGUE_PREDICATES)})
        return json.dumps({"measure": measure, "value": value,
                           "degree": degree(measure, value)})

    def rough_report(table: str, attributes: str, target_set: str) -> str:
        """Lower and upper approximation of a target set, from the recorded attributes.

        `table` is triage_log or registry; `attributes` is comma-separated. An empty
        boundary (accuracy 1.0) means the recorded codes decide membership exactly.
        """
        if table not in _TABLES:
            return json.dumps({"error": f"unknown table {table!r}", "available": sorted(_TABLES)})
        attrs = [a.strip() for a in attributes.split(",") if a.strip()]
        return json.dumps({"table": table, "attributes": attrs, "target_set": target_set,
                           **_approximation(table, attrs, target_set)})

    def expressivity_cost(formalism: str) -> str:
        """The reasoning cost of a formalism (crisp, fuzzy, rough, temporal), with the reason."""
        reasons = {
            "crisp": "standard reasoning; no extra machinery",
            "fuzzy": "membership is pointwise; reasoning stays polynomial",
            "rough": "approximations come from partitioning; polynomial",
            "temporal": "consistency of a general Allen network is NP-complete",
        }
        key = formalism.strip().lower()
        return json.dumps({"formalism": key, "cost": EXPRESSIVITY_COST.get(key, "unknown"),
                           "why": reasons.get(key, "unknown formalism")})

    impls = [get_requirement, check_temporal_consistency, fuzzy_degree, rough_report,
             expressivity_cost]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Constraint propagation as an MDP (Part D)
# --------------------------------------------------------------------------- #
#: A restricted alphabet keeps the reachable state space enumerable. The full
#: thirteen relations behave identically; only the arithmetic gets larger.
MDP_RELATIONS = ("b", "bi", "m", "eq")


@dataclass(frozen=True)
class PropagationState:
    """The current label sets, whether anything was checked, and whether we stopped.

    ``checked`` records that at least one propagation has been performed. It
    matters because propagating an already path-consistent network leaves the
    labels untouched: without this flag the state would not advance, and a
    policy that kept propagating would loop forever.
    """

    ab: frozenset
    bc: frozenset
    ac: frozenset
    done: bool = False
    checked: bool = False

    def empty(self) -> bool:
        return not self.ab or not self.bc or not self.ac

    def __str__(self) -> str:  # pragma: no cover - display only
        def short(label):
            return "".join(sorted(label)) or "!"
        mark = ("+" if self.checked else "") + ("*" if self.done else "")
        return f"{short(self.ab)}/{short(self.bc)}/{short(self.ac)}{mark}"


class PropagationMDP:
    """Decide a three-interval network's consistency, choosing what to propagate.

    A constraint solver narrows label sets by composing through a third
    interval. Each composition costs; the agent must decide **which** to do and
    **when to stop**.

    | | |
    |---|---|
    | **S** | the three label sets, whether any propagation was done, whether a verdict was given |
    | **A** | propagate through A, B or C; or declare consistent / inconsistent |
    | **T** | deterministic — composition is a function |
    | **R** | −``cost`` per propagation; +1 for a **justified** correct verdict, −``wrong_penalty`` otherwise |

    "Justified" carries the weight: declaring inconsistency is only rewarded
    once a label has actually been emptied. With ``require_check=True`` a
    consistency claim must also be earned by at least one propagation.
    """

    def __init__(self, ab, bc, ac, consistent: bool,
                 cost: float = 0.05, wrong_penalty: float = 1.0, gamma: float = 1.0,
                 require_check: bool = False):
        self.start = PropagationState(frozenset(ab), frozenset(bc), frozenset(ac))
        self.consistent = consistent
        self.cost = cost
        self.wrong_penalty = wrong_penalty
        self.gamma = gamma
        self.require_check = require_check
        self._states = None

    @staticmethod
    def _narrow(state: PropagationState, via: str) -> PropagationState:
        if via == "B":       # AB o BC narrows AC
            implied = ch10.compose_sets(state.ab, state.bc)
            return PropagationState(state.ab, state.bc, state.ac & implied, False, True)
        if via == "A":       # BA o AC narrows BC
            ba = frozenset(ch10.inverse(r) for r in state.ab)
            implied = ch10.compose_sets(ba, state.ac)
            return PropagationState(state.ab, state.bc & implied, state.ac, False, True)
        # via C: AC o CB narrows AB
        cb = frozenset(ch10.inverse(r) for r in state.bc)
        implied = ch10.compose_sets(state.ac, cb)
        return PropagationState(state.ab & implied, state.bc, state.ac, False, True)

    def initial_state(self) -> PropagationState:
        return self.start

    def is_terminal(self, state: PropagationState) -> bool:
        return state.done

    def states(self):
        if self._states is not None:
            return self._states
        reachable = {self.start}
        frontier = [self.start]
        while frontier:
            current = frontier.pop()
            if current.empty():
                continue
            for via in ("A", "B", "C"):
                nxt = self._narrow(current, via)
                if nxt not in reachable:
                    reachable.add(nxt)
                    frontier.append(nxt)
        self._states = [PropagationState(s.ab, s.bc, s.ac, done, s.checked)
                        for s in reachable for done in (False, True)]
        return self._states

    def actions(self, state: PropagationState):
        if state.done:
            return []
        propagations = ([f"propagate:{via}" for via in ("A", "B", "C")]
                        if not state.empty() else [])
        if self.require_check and not state.checked:
            # Nothing has been checked yet, so no consistency verdict is justified.
            return propagations or ["declare:inconsistent"]
        return propagations + ["declare:consistent", "declare:inconsistent"]

    def transition(self, state: PropagationState, action: str):
        if action.startswith("declare:"):
            claimed_consistent = action == "declare:consistent"
            # An inconsistency claim must be *witnessed* by an empty label.
            justified = ((state.checked or not self.require_check)
                         if claimed_consistent else state.empty())
            correct = (claimed_consistent == self.consistent) and justified
            reward = 1.0 if correct else -self.wrong_penalty
            return [(1.0, PropagationState(state.ab, state.bc, state.ac, True,
                                           state.checked), reward)]
        nxt = self._narrow(state, action.split(":")[1])
        return [(1.0, nxt, -self.cost)]

    def step(self, state: PropagationState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)
