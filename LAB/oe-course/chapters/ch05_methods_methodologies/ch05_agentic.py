"""Chapter 5 problem-set support — auditing ontology projects, and planning the work.

Provided code for ``04_assignment.ipynb``. The student builds the output parser,
the audit scorer, the Claude auditor and the audit agent in the notebook; this
module supplies what a real review office would already have in its codebase:

* the **design-review corpus** — 24 client submissions to an ontology design
  review, each a project brief plus a draft taxonomy and the meta-property tag
  sheet from the client's modelling workshop, with a fixed train / dev / test
  split by submission;
* the **meta-property tag sheet** (:data:`TAG_SHEET`) and the OntoClean check
  over it (:func:`taxonomy_violations`), built on the Chapter 5 toolkit;
* the **Chapter 3 tableau** wired to a taxonomy (:func:`dl_tbox`,
  :func:`reasoner_report`), so the notebook can show what a logical reasoner
  does — and does not — see;
* the **guidelines** an audit scorer reports (:data:`AUDIT_RULEBOOK`);
* the **audit agent's tools** (:func:`build_audit_tools`);
* **project planning as an MDP with prerequisites** (:class:`MethodologyPlanMDP`).

What makes this chapter's task distinctive is the class of error involved. Every
draft taxonomy in the corpus is *logically consistent* — the Chapter 3 reasoner
finds every class satisfiable. The mistakes are **ontological** (a role placed
above a kind, an object filed under the stuff it is made of), and catching them
needs meta-properties, not a tableau. An auditor that only knows how to call a
reasoner will report every submission as clean.

Every gold label is recomputed at import time by the chapter's own engines
(:func:`ch05_toolkit.recommend_methodology` and the OntoClean checker) and
compared with the label the corpus states, so the data and the engines cannot
drift apart.
"""

from __future__ import annotations

import functools
import itertools
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import ch05_toolkit as ch5

_CH03 = Path(__file__).resolve().parent.parent / "ch03_description_logics"
if str(_CH03) not in sys.path:
    sys.path.insert(0, str(_CH03))
import ch03_toolkit as dl  # noqa: E402

__all__ = [
    "TAG_SHEET", "METHODOLOGY_IDS", "AuditCase", "AUDIT_CASES", "build_dataset",
    "parse_taxonomy", "format_axiom", "taxonomy_violations", "meta_properties_text",
    "dl_tbox", "reasoner_report", "AUDIT_RULEBOOK", "BASELINE_INSTRUCTION",
    "AuditWorkspace", "build_audit_tools", "measured_coverage", "PlanState",
    "MethodologyPlanMDP", "dl",
]


# --------------------------------------------------------------------------- #
# The meta-property tag sheet
# --------------------------------------------------------------------------- #
_MP = ch5.MetaProperties
_KIND = _MP("+R", "+I", "+U", "-D")          # rigid, identity-supplying wholes
_MATTER = _MP("+R", "-I", "~U", "-D")        # amounts of stuff: no unity
_ROLE = _MP("~R", "-I", "-U", "+D")          # roles: anti-rigid, depend on a relatum
_PHASE = _MP("~R", "+I", "-U", "-D")         # phases: anti-rigid, but independent
_DEPENDENT = _MP("+R", "+I", "+U", "+D")     # rigid, but existentially dependent

#: Meta-properties for every class that appears in the corpus, as agreed in the
#: clients' modelling workshops. Extends the Chapter 5 toolkit's table (whose
#: entries are kept unchanged) with the corpus's domain classes.
TAG_SHEET: dict[str, ch5.MetaProperties] = {
    **ch5.ONTOCLEAN_TAGS,
    # upper level
    "Artefact": _KIND, "LegalAgent": _MP("+R", "-I", "-U", "-D"),
    "Work": _MP("+R", "+I", "-U", "-D"),
    # kinds
    "Organisation": _KIND, "Plant": _KIND, "Building": _KIND, "Vessel": _KIND,
    "Container": _KIND, "Sculpture": _KIND, "Tablet": _KIND, "Blade": _KIND,
    "Turbine": _KIND, "Tree": _KIND, "Robot": _KIND, "Pallet": _KIND, "Coin": _KIND,
    "Sweater": _KIND, "Hull": _KIND, "Pump": _KIND, "Door": _KIND, "Bale": _KIND,
    "Beam": _KIND, "Bridge": _KIND, "Vehicle": _KIND, "Castle": _KIND,
    "Novel": _MP("+R", "+I", "-U", "-D"),
    # amounts of matter
    "Bronze": _MATTER, "Flour": _MATTER, "Straw": _MATTER, "Steel": _MATTER,
    "Composite": _MATTER, "Silver": _MATTER, "Wool": _MATTER, "Water": _MATTER,
    # roles
    "Customer": _ROLE, "Patient": _ROLE, "Supplier": _ROLE, "Tenant": _ROLE,
    "Passenger": _ROLE, "Borrower": _ROLE, "Resident": _ROLE, "Donor": _ROLE,
    "Contractor": _ROLE, "Cargo": _ROLE, "Exhibit": _ROLE, "Operator": _ROLE,
    # phases
    "Adult": _PHASE, "Child": _PHASE, "Ruin": _PHASE, "Seedling": _PHASE, "Wreck": _PHASE,
    # rigid but dependent
    "Doorway": _DEPENDENT, "Inscription": _DEPENDENT, "Borehole": _DEPENDENT,
    "Translation": _MP("+R", "+I", "-U", "+D"),
}

METHODOLOGY_IDS: tuple[str, ...] = tuple(m.id for m in ch5.METHODOLOGIES)


# --------------------------------------------------------------------------- #
# The design-review corpus
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditCase:
    """One submission to the design review: who, the brief, the draft taxonomy.

    ``methodology`` and ``violations`` are the stated gold labels; both are
    re-derived by the Chapter 5 engines when the module is imported.
    """

    id: str
    split: str
    organisation: str
    brief: str
    axioms: tuple[tuple[str, str], ...]
    methodology: str
    violations: tuple[str, ...]


def _c(id, split, organisation, brief, axioms, methodology, violations=()):
    return AuditCase(id, split, organisation, " ".join(brief.split()),
                     tuple(axioms), methodology, tuple(violations))


#: 24 submissions, split 8 / 8 / 8 by submission. Each split contains every
#: methodology, every OntoClean phenomenon (role above a kind; phase above a
#: kind; object under its matter; independent under dependent), at least one
#: clean taxonomy, and a sound axiom in almost every taxonomy so an auditor can
#: over-report. Several briefs carry a weaker distractor signal on purpose.
AUDIT_CASES: list[AuditCase] = [
    # --- train ----------------------------------------------------------------
    _c("port-cargo", "train", "Port of Kestrel (logistics authority)",
       """The Port of Kestrel wants a cargo ontology for its customs pipeline. Most
       of the vocabulary already exists: we must reuse the UN code lists, two
       existing ontologies for transport events and the port's operational
       databases. The result will be one module in a networked set of port
       ontologies.""",
       [("Container", "Cargo"), ("Cargo", "PhysicalObject"), ("Vessel", "PhysicalObject")],
       "neon", ["Container <= Cargo"]),
    _c("civic-archives", "train", "Twelve municipal archives (regional heritage partnership)",
       """Twelve municipal archives will co-edit a shared place-and-heritage ontology.
       Editing is decentralised: each archive adapts the shared model locally, many
       contributors propose changes, and the model will keep evolving as archives
       join.""",
       [("Castle", "Ruin"), ("Ruin", "Building"), ("Building", "PhysicalObject")],
       "diligent", ["Castle <= Ruin"]),
    _c("ledgerly-fraud", "train", "Ledgerly (payments start-up)",
       """Ledgerly needs a small ontology for its fraud-rules engine. The team works
       in two-week sprints and wants an agile, test driven process: every sprint
       ships a tested module and the model grows in small increments.""",
       [("Customer", "LegalAgent"), ("Organisation", "Customer"), ("Person", "LegalAgent")],
       "samod", ["Organisation <= Customer"]),
    _c("grain-coop", "train", "Midlands Grain Cooperative",
       """The cooperative is considering a knowledge management portal for agronomy
       advice. Nothing is funded yet: the board wants the business case first, with
       an application driven pilot on one crop before any wider modelling.""",
       [("Bale", "Straw"), ("Straw", "AmountOfMatter"), ("Bale", "PhysicalObject")],
       "on-to-knowledge", ["Bale <= Straw"]),
    _c("aldersgate-museum", "train", "Aldersgate Museum of Science",
       """The museum is building its first collections ontology from scratch. There
       are no usable legacy assets; a single team of two curators and one engineer
       will own it through the full lifecycle, from specification to
       maintenance.""",
       [("Sculpture", "Bronze"), ("Tablet", "Inscription"), ("Exhibit", "Artefact"),
        ("Sculpture", "Artefact")],
       "methontology", ["Sculpture <= Bronze", "Tablet <= Inscription"]),
    _c("northline-rail", "train", "Northline Rail (infrastructure manager)",
       """Northline wants an asset-maintenance ontology. Rather than start over, the
       team will reuse a published ontology for linear infrastructure and
       re-engineer non-ontological resources: the maintenance thesauri and two
       work-order databases.""",
       [("Beam", "PhysicalObject"), ("Steel", "AmountOfMatter"), ("Bridge", "PhysicalObject")],
       "neon", []),
    _c("pharmacy-network", "train", "Regional hospital pharmacies",
       """A distributed group of hospital pharmacies will maintain a shared
       adverse-event ontology and will reuse a drug thesaurus where possible. Many
       contributors in different organisations will edit it, and it is expected
       to keep evolving as new drugs are approved.""",
       [("Person", "Patient"), ("Donor", "Person"), ("Adult", "Person")],
       "diligent", ["Person <= Patient"]),
    _c("quillo-curriculum", "train", "Quillo (ed-tech company)",
       """Quillo wants a curriculum ontology behind its tutoring app for adult
       learners. The product team insists on an iterative, test driven workflow:
       competency questions become tests first, and the model is extended in small
       increments.""",
       [("Student", "Person"), ("Person", "Adult"), ("Employee", "Person")],
       "samod", ["Person <= Adult"]),
    # --- dev ------------------------------------------------------------------
    _c("pennine-libraries", "dev", "Pennine Libraries Consortium",
       """The consortium will publish a linked catalogue. Its value is reuse: it must
       align with existing ontologies for bibliographic data and convert the
       subject thesauri the member libraries already maintain.""",
       [("Novel", "Translation"), ("Translation", "Work"), ("Novel", "Work"),
        ("Borrower", "Person")],
       "neon", ["Novel <= Translation"]),
    _c("brightwater-turbines", "dev", "Brightwater Energy",
       """Brightwater is modelling turbine components for a new asset register.
       Nothing like it exists in the company, so it is a greenfield build by a
       single team, who will run the full lifecycle themselves.""",
       [("Blade", "Composite"), ("Composite", "AmountOfMatter"), ("Turbine", "PhysicalObject")],
       "methontology", ["Blade <= Composite"]),
    _c("open-biodiversity", "dev", "Open biodiversity-observation community",
       """An open observation ontology maintained by volunteer naturalists and
       research groups on four continents: decentralised governance, many
       contributors, and a vocabulary that is evolving with the taxonomic
       literature.""",
       [("Tree", "Seedling"), ("Seedling", "Plant"), ("Pet", "Animal")],
       "diligent", ["Tree <= Seedling"]),
    _c("harrow-claims", "dev", "Harrow Mutual (insurer)",
       """Harrow Mutual wants to know whether an ontology can improve claims handling
       at all. The steering group asked for the business case first and a small,
       application driven proof of value inside its knowledge management
       programme.""",
       [("Organisation", "Supplier"), ("Supplier", "LegalAgent"), ("Person", "LegalAgent")],
       "on-to-knowledge", ["Organisation <= Supplier"]),
    _c("warehouse-robotics", "dev", "Cobalt Robotics (warehouse automation)",
       """A warehouse-robotics team needs a task ontology for its planner. They run
       an agile process with weekly releases and want test driven, iterative
       modelling with competency questions as automated tests.""",
       [("Robot", "PhysicalObject"), ("Operator", "Person"), ("Pallet", "PhysicalObject")],
       "samod", []),
    _c("carrow-estate", "dev", "Duchy of Carrow estate office",
       """The estate office will build a property-register ontology from scratch; a
       single team will own specification, conceptualisation, implementation and
       maintenance.""",
       [("Door", "Doorway"), ("Tenant", "Person"), ("Doorway", "Entity"),
        ("Building", "PhysicalObject")],
       "methontology", ["Door <= Doorway"]),
    _c("veldra-customs", "dev", "Veldra Border Data Unit",
       """The unit needs a goods-classification ontology built by reuse: the tariff
       thesauri, product databases and existing ontologies for trade must be
       re-engineered and aligned rather than rewritten.""",
       [("Coin", "Silver"), ("Silver", "AmountOfMatter"), ("Container", "PhysicalObject")],
       "neon", ["Coin <= Silver"]),
    _c("citizen-app", "dev", "Ashby City Council digital team",
       """The council's digital team is building a service ontology for its citizen
       app, fed by the council's databases. It works in small increments, with an
       agile backlog and test driven acceptance of every modelling change.""",
       [("Person", "Resident"), ("Passenger", "Person"), ("Vehicle", "PhysicalObject")],
       "samod", ["Person <= Resident"]),
    # --- test -----------------------------------------------------------------
    _c("tessera-3d", "test", "Tessera Studio (3D heritage scanning)",
       """Tessera is creating an ontology for its archive of 3D-scanned sculpture. It
       is a greenfield project with no prior models; a single team will run it end
       to end, from scratch.""",
       [("Statue", "Clay"), ("Statue", "Artefact"), ("Clay", "AmountOfMatter")],
       "methontology", ["Statue <= Clay"]),
    _c("trials-network", "test", "Seven research hospitals (clinical-trials group)",
       """Seven research hospitals will jointly curate a clinical-trials ontology.
       Curation is distributed and decentralised, and the ontology is expected to
       keep evolving with each protocol amendment.""",
       [("Person", "Donor"), ("Patient", "Person"), ("Employee", "Person")],
       "diligent", ["Person <= Donor"]),
    _c("brindle-suppliers", "test", "Brindle & Co. (retailer)",
       """Brindle wants to test whether an ontology helps its knowledge management
       around suppliers. Management insists on the business case first; the first
       phase is an application driven pilot for one product line.""",
       [("Sweater", "Wool"), ("Organisation", "LegalAgent"), ("Supplier", "LegalAgent")],
       "on-to-knowledge", ["Sweater <= Wool"]),
    _c("genomics-samples", "test", "Helix genomics lab",
       """The lab wants a sample-tracking ontology developed the way it develops
       software: agile, iterative, in small increments, with every competency
       question written as a test before modelling. Sample metadata comes from its
       existing databases.""",
       [("Person", "Child"), ("Donor", "Person"), ("Adult", "Person")],
       "samod", ["Person <= Child"]),
    _c("tarn-water", "test", "Tarn Valley Water (utility)",
       """Tarn Valley Water wants an asset ontology assembled mostly by reuse of
       existing ontologies for sensors and infrastructure, plus its GIS databases
       and maintenance thesauri.""",
       [("Pump", "Borehole"), ("Pump", "PhysicalObject"), ("Water", "AmountOfMatter")],
       "neon", ["Pump <= Borehole"]),
    _c("fenland-wildlife", "test", "Fenland Wildlife Trust",
       """The trust is building a species-and-sites ontology with many contributors
       — volunteer recorders, reserve managers and partner charities — in a
       decentralised, evolving effort.""",
       [("Pet", "Animal"), ("Animal", "PhysicalObject"), ("Tree", "Plant")],
       "diligent", []),
    _c("law-firm-pilot", "test", "Marlow Keane LLP (law firm)",
       """The firm's innovation group wants to see whether a contracts ontology pays
       off. The partners want the business case first, measured on an application
       driven pilot, before any firm-wide knowledge management rollout.""",
       [("Person", "Contractor"), ("Organisation", "Customer"), ("Customer", "LegalAgent"),
        ("Contractor", "LegalAgent")],
       "on-to-knowledge", ["Organisation <= Customer", "Person <= Contractor"]),
    _c("calder-shipyard", "test", "Calder Shipyard",
       """Calder needs a vessel-construction ontology. It is a from scratch effort by a
       single team that will also maintain it, covering the full lifecycle of the
       model, although the yard's supplier base is distributed.""",
       [("Hull", "Steel"), ("Vessel", "Wreck"), ("Hull", "PhysicalObject")],
       "methontology", ["Hull <= Steel", "Vessel <= Wreck"]),
]


# --------------------------------------------------------------------------- #
# Taxonomy helpers and the OntoClean check
# --------------------------------------------------------------------------- #
def format_axiom(sub: str, sup: str) -> str:
    return f"{sub} <= {sup}"


def parse_taxonomy(text: str) -> list[tuple[str, str]]:
    """Read the corpus's own input format: one ``Sub <= Super`` per line."""
    pairs = []
    for line in (text or "").splitlines():
        if "<=" in line:
            sub, sup = line.split("<=", 1)
            pairs.append((sub.strip(), sup.strip()))
    return pairs


def taxonomy_violations(pairs) -> list[dict]:
    """OntoClean breaches in a taxonomy, judged against :data:`TAG_SHEET`."""
    return ch5.ontoclean_violations(list(pairs), TAG_SHEET)


def _classes(pairs) -> list[str]:
    return sorted({c for pair in pairs for c in pair})


def meta_properties_text(pairs) -> str:
    """The tag sheet rows for the classes in one taxonomy, one class per line."""
    lines = []
    for name in _classes(pairs):
        t = TAG_SHEET[name]
        lines.append(f"{name}: {t.rigidity} {t.identity} {t.unity} {t.dependence}")
    return "\n".join(lines)


def _validate() -> None:
    ids = [c.id for c in AUDIT_CASES]
    assert len(ids) == len(set(ids)) == 24
    for case in AUDIT_CASES:
        assert case.split in {"train", "dev", "test"}
        for name in _classes(case.axioms):
            assert name in TAG_SHEET, f"{case.id}: untagged class {name}"
        rec = ch5.recommend_methodology(case.brief)
        ranking = rec["ranking"]
        assert rec["recommended"] == case.methodology, (case.id, rec["recommended"])
        assert ranking[0]["score"] > ranking[1]["score"], f"{case.id}: methodology tie"
        found = sorted({v["axiom"] for v in taxonomy_violations(case.axioms)})
        assert found == sorted(case.violations), (case.id, found)
    for split in ("train", "dev", "test"):
        rows = [c for c in AUDIT_CASES if c.split == split]
        assert len(rows) == 8
        assert {c.methodology for c in rows} == set(METHODOLOGY_IDS), split
        assert any(not c.violations for c in rows), f"{split}: needs a clean taxonomy"
        constraints = {v["constraint"] for c in rows for v in taxonomy_violations(c.axioms)}
        assert constraints == {"anti-rigid-cannot-subsume-rigid",
                               "anti-unity-cannot-subsume-unity",
                               "dependent-cannot-subsume-independent"}, split


_validate()


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows.

    Inputs: ``brief``, ``taxonomy`` (one ``Sub <= Super`` per line) and
    ``meta_properties`` (the tag sheet rows for the taxonomy's classes). Gold:
    ``gold_methodology``, ``gold_violations`` (sorted offending axioms) and
    ``gold_detail`` (the checker's findings, constraint by constraint).
    """
    import dspy

    rows = []
    for case in AUDIT_CASES:
        if split != "all" and case.split != split:
            continue
        detail = taxonomy_violations(case.axioms)
        rows.append(dspy.Example(
            id=case.id, split=case.split, organisation=case.organisation,
            brief=case.brief,
            taxonomy="\n".join(format_axiom(s, p) for s, p in case.axioms),
            meta_properties=meta_properties_text(case.axioms),
            gold_methodology=case.methodology,
            gold_violations=sorted({v["axiom"] for v in detail}),
            gold_detail=detail,
        ).with_inputs("brief", "taxonomy", "meta_properties"))
    return rows


# --------------------------------------------------------------------------- #
# What a logical reasoner sees (Chapter 3 tableau)
# --------------------------------------------------------------------------- #
def dl_tbox(pairs) -> "dl.TBox":
    """The taxonomy as a Chapter 3 TBox of atomic subsumptions."""
    tbox = dl.TBox()
    for sub, sup in pairs:
        tbox.add(dl.Atomic(sub), dl.Atomic(sup))
    return tbox


def reasoner_report(pairs) -> dict:
    """Satisfiability of every class in the taxonomy, by the Chapter 3 tableau."""
    tbox = dl_tbox(pairs)
    unsat = [name for name in _classes(pairs)
             if not dl.satisfiable(dl.Atomic(name), tbox).satisfiable]
    return {"consistent": not unsat, "unsatisfiable_classes": unsat,
            "classes": len(_classes(pairs)), "axioms": len(list(pairs))}


# --------------------------------------------------------------------------- #
# Guidelines the audit scorer reports
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("emit-structured-audit",
             "Answer with a methodology id from the catalogue (methontology, "
             "on-to-knowledge, diligent, neon, samod) and a JSON array of offending "
             "axioms written exactly as in the taxonomy, e.g. [\"Person <= Student\"]; "
             "use [] when there are none."),
        Rule("choose-methontology",
             "When the brief describes a greenfield build from scratch by a single team "
             "over the full lifecycle, choose METHONTOLOGY."),
        Rule("choose-neon",
             "When the brief is about reusing existing ontologies, thesauri, databases "
             "or other non-ontological resources, choose NeOn: reuse is its distinctive "
             "contribution."),
        Rule("choose-diligent",
             "When the brief describes a distributed, decentralised or evolving effort "
             "with many contributors, choose DILIGENT."),
        Rule("choose-samod",
             "When the brief asks for agile, iterative or test-driven development in "
             "small increments, choose SAMOD."),
        Rule("choose-on-to-knowledge",
             "When the brief leads with a business case, a feasibility question or a "
             "knowledge management pilot, choose On-To-Knowledge."),
        Rule("apply-ontoclean-constraints",
             "Check every subsumption against the tag sheet: an anti-rigid class (~R) "
             "cannot subsume a rigid one (+R), an anti-unity class (~U) cannot subsume "
             "one with unity (+U), and a dependent class (+D) cannot subsume an "
             "independent one (-D). Logical consistency does not make an axiom correct."),
        Rule("only-report-real-violations",
             "Report an axiom only when a named constraint is actually breached; a role "
             "or phase *under* a kind, or matter under AmountOfMatter, is sound."),
        Rule("only-audit-given-axioms",
             "Report only axioms that appear in the submitted taxonomy, in their given "
             "direction; do not report repairs, inferred subsumptions or reversed axioms."),
    ])


#: The guidelines an audit scorer reports as violated.
AUDIT_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are auditing an ontology project for a design review. Recommend a "
    "methodology and review the taxonomy."
)


# --------------------------------------------------------------------------- #
# Agent tools
# --------------------------------------------------------------------------- #
@dataclass
class AuditWorkspace:
    """What the audit agent can see for one submission, plus its call log."""

    case: AuditCase
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()

    @property
    def taxonomy(self) -> str:
        return "\n".join(format_axiom(s, p) for s, p in self.case.axioms)

    def task(self) -> str:
        """The user message the agent receives."""
        return (f"Design-review submission from {self.case.organisation}.\n\n"
                f"Project brief:\n{self.case.brief}\n\n"
                f"Draft taxonomy (one subsumption per line):\n{self.taxonomy}")


def build_audit_tools(ws: AuditWorkspace, include_engines: bool = True):
    """The audit agent's tools.

    Always: the methodology catalogue, the tag-sheet lookup, the OntoClean
    constraints, and a logical consistency check (the Chapter 3 tableau). With
    ``include_engines``: also the two engines that decide the gold labels —
    the methodology recommender and the OntoClean taxonomy checker.
    """
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def list_methodologies() -> str:
        """List the methodologies with the project signals each one fits.

        Call this before recommending one, so the choice is made from the brief
        rather than from familiarity.
        """
        return json.dumps(ch5.methodology_table())

    def ontoclean_tags(class_name: str) -> str:
        """Look up a class's OntoClean meta-properties (rigidity, identity, unity,
        dependence) on the review's tag sheet."""
        tags = TAG_SHEET.get(class_name)
        if tags is None:
            return json.dumps({"class": class_name, "known": False})
        return json.dumps({"class": class_name, "known": True, "rigidity": tags.rigidity,
                           "identity": tags.identity, "unity": tags.unity,
                           "dependence": tags.dependence})

    def list_constraints() -> str:
        """Explain the OntoClean taxonomy constraints and why each one matters."""
        return json.dumps(ch5.ONTOCLEAN_CONSTRAINTS)

    def check_consistency(axioms: str) -> str:
        """Run a description-logic reasoner (tableau) on subsumption axioms
        ('Sub <= Super', one per line): is every class satisfiable?"""
        return json.dumps(reasoner_report(parse_taxonomy(axioms)))

    def recommend_methodology(brief: str) -> str:
        """Score every methodology against a project brief and rank them, showing
        the signals that matched."""
        return json.dumps(ch5.recommend_methodology(brief))

    def check_taxonomy(axioms: str) -> str:
        """Check subsumption axioms ('Sub <= Super', one per line) against the
        OntoClean constraints, using the review's tag sheet."""
        return json.dumps(taxonomy_violations(parse_taxonomy(axioms)))

    impls = [list_methodologies, ontoclean_tags, list_constraints, check_consistency]
    if include_engines:
        impls += [recommend_methodology, check_taxonomy]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Planning MDP with prerequisites
# --------------------------------------------------------------------------- #
#: The development steps that add triples to the ontology; coverage depends on
#: nothing else, which is what makes it cheap to memoise.
_BUILD_TIERS = frozenset({"taxonomy", "axioms", "instances"})


@functools.lru_cache(maxsize=None)
def _coverage_of_tiers(tiers: frozenset) -> float:
    return ch5.coverage_for_steps(tiers)


def measured_coverage(done) -> float:
    """Measured AWO competency-question coverage after the steps in ``done``.

    Same value as :func:`ch05_toolkit.coverage_for_steps`, memoised on the steps
    that actually build the ontology — so a parameter sweep over many MDPs runs
    eight SPARQL measurements in total, not eight per state per MDP.
    """
    return _coverage_of_tiers(frozenset(done) & _BUILD_TIERS)


_SHORT = {"requirements": "Q", "competency_questions": "C", "reuse_search": "U",
          "taxonomy": "T", "axioms": "A", "instances": "I", "evaluation": "E"}


@dataclass(frozen=True)
class PlanState:
    """Which development steps are done, and whether the project has shipped."""

    done: frozenset[str]
    shipped: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        short = "".join(code if name in self.done else "." for name, code in _SHORT.items())
        return short + ("!" if self.shipped else "")


class MethodologyPlanMDP:
    """Plan an ontology development project under precedence constraints.

    | S | which development steps are done, and whether we shipped |
    | A | perform a step **whose prerequisites are complete**, or ``ship`` |
    | T | deterministic |
    | R | minus the step's effort; on ``ship``, the *measured* CQ coverage |

    Every earlier MDP in the course had all actions available at all times. Here
    an action is unavailable until its prerequisites are complete — which is
    exactly what a methodology asserts.

    Hooks for modelling experiments:

    * ``coverage_fn(done) -> float`` — the ship reward (default: measured AWO
      competency-question coverage, :func:`measured_coverage`);
    * ``cost_fn(done, action) -> float`` — the effort of ``action`` taken when
      the steps in ``done`` are complete (default: the step's listed cost).
    """

    def __init__(self, steps: dict | None = None, gamma: float = 1.0,
                 coverage_fn=None, cost_fn=None):
        self.steps = steps or ch5.DEVELOPMENT_STEPS
        self.names = sorted(self.steps)
        self.gamma = gamma
        self.coverage_fn = coverage_fn or measured_coverage
        self.cost_fn = cost_fn or (lambda done, action: self.steps[action]["cost"])
        self._cache: dict[frozenset, float] = {}

    def initial_state(self) -> PlanState:
        return PlanState(frozenset())

    def is_terminal(self, state: PlanState) -> bool:
        return state.shipped

    def states(self) -> list[PlanState]:
        out = []
        for r in range(len(self.names) + 1):
            for combo in itertools.combinations(self.names, r):
                done = frozenset(combo)
                out.append(PlanState(done, False))
                out.append(PlanState(done, True))
        return out

    def actions(self, state: PlanState) -> list[str]:
        if state.shipped:
            return []
        available = [
            name for name in self.names
            if name not in state.done
            and all(req in state.done for req in self.steps[name]["requires"])
        ]
        return available + ["ship"]

    def coverage(self, done: frozenset) -> float:
        if done not in self._cache:
            self._cache[done] = self.coverage_fn(done)
        return self._cache[done]

    def transition(self, state: PlanState, action: str):
        if action == "ship":
            return [(1.0, PlanState(state.done, True), self.coverage(state.done))]
        cost = self.cost_fn(state.done, action)
        return [(1.0, PlanState(state.done | {action}, False), -cost)]

    def step(self, state: PlanState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)
