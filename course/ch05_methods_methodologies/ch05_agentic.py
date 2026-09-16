"""Chapter 5 agentic lab — auditing a project, and planning the work.

The agent plays **ontology quality auditor**: given a project brief and a
taxonomy, it recommends a methodology (§5.1) and reports the OntoClean
violations in the taxonomy (§5.2).

What makes this chapter's lab distinctive is the class of error involved. Every
axiom in the audited taxonomy is *logically consistent* — a Chapter 3 reasoner
finds nothing wrong with ``Person ⊑ Student``. The mistakes are **ontological**,
and catching them needs meta-properties, not a tableau. An agent that only knows
how to call a reasoner will score zero here.

The MDP is a **planning problem with prerequisites**: you cannot write axioms
before a taxonomy exists, and you cannot evaluate against competency questions
you never wrote. Skipping a step does not merely cost quality — it makes later
steps unavailable, which is the structural claim every methodology in §5.1 is
really making.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import ch05_toolkit as ch5

__all__ = [
    "AUDIT_CASES", "build_dataset", "audit_scorer", "AUDIT_RULEBOOK",
    "audit_responder", "AuditProgram", "BASELINE_INSTRUCTION",
    "build_toolset", "Ch5Context", "MethodologyPlanMDP",
]


# --------------------------------------------------------------------------- #
# Cases: a brief plus a taxonomy to audit
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditCase:
    id: str
    brief: str
    taxonomy: tuple[tuple[str, str], ...]


#: Each brief carries the signals that identify one methodology; each taxonomy
#: carries zero or more OntoClean violations. The two halves are independent on
#: purpose, so the metric can tell which half an agent is failing.
AUDIT_CASES = [
    AuditCase(
        "reuse-project",
        "We must reuse existing ontologies and a legacy thesaurus for a networked "
        "healthcare project.",
        (("Student", "Person"), ("Person", "Entity")),
    ),
    AuditCase(
        "greenfield-lab",
        "Greenfield build from scratch by a single team, covering the full lifecycle.",
        (("Person", "Student"), ("Person", "Entity")),
    ),
    AuditCase(
        "consortium",
        "A distributed consortium with many contributors, evolving over several years.",
        # A violating axiom *and* a sound one: without a sound axiom present, an
        # agent cannot over-report, and the metric can never punish over-reporting.
        (("Statue", "Clay"), ("Animal", "Entity")),
    ),
    AuditCase(
        "agile-startup",
        "We want an agile, test driven, iterative approach in small increments.",
        (("Employee", "Person"), ("Animal", "Entity")),
    ),
    AuditCase(
        "feasibility-first",
        "Knowledge management pilot; the business case first, application driven.",
        (("Person", "Pet"), ("Student", "Person")),
    ),
    AuditCase(
        "reuse-databases",
        "Re-engineer non-ontological resources: databases and thesauri we already own.",
        (("Person", "Student"), ("Statue", "Clay")),
    ),
    AuditCase(
        "clean-greenfield",
        "From scratch, single team, full lifecycle, no existing assets.",
        (("Student", "Person"), ("Employee", "Person")),
    ),
    AuditCase(
        "evolving-community",
        "Decentralised and evolving, edited by many contributors in different labs.",
        (("Person", "Pet"), ("Statue", "Clay")),
    ),
    AuditCase(
        "sprint-team",
        "Small increments, test driven and iterative; we want an agile cadence.",
        (("Person", "Student"),),
    ),
    AuditCase(
        "pilot-business-case",
        "A knowledge management pilot: prove the business case first, application driven.",
        (("Student", "Person"), ("PhysicalObject", "Entity")),
    ),
]


def build_dataset(split: str = "all"):
    """Each example: brief + taxonomy, with the gold methodology and violations."""
    import dspy

    examples = []
    for case in AUDIT_CASES:
        gold_method = ch5.recommend_methodology(case.brief)["recommended"]
        violations = ch5.ontoclean_violations(case.taxonomy)
        gold_axioms = sorted({v["axiom"] for v in violations})
        examples.append(
            dspy.Example(
                brief=case.brief,
                taxonomy="\n".join(f"{sub} <= {sup}" for sub, sup in case.taxonomy),
                gold_methodology=gold_method,
                gold_violations=gold_axioms,
                id=case.id,
            ).with_inputs("brief", "taxonomy")
        )
    # Stratified: alternate, so both halves see reuse/greenfield/distributed briefs
    # and both clean and violating taxonomies.
    if split == "train":
        return examples[0::2]
    if split == "dev":
        return examples[1::2]
    return examples


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def audit_scorer(gold, pred):
    """Half for the methodology, half for the OntoClean violations found."""
    from oe_course.evaluation import ScoreReport, parse_label_list, set_f1

    predicted_method = str(getattr(pred, "methodology", "") or "").strip().lower()
    predicted_violations = parse_label_list(getattr(pred, "violations", None))
    gold_violations = list(gold.gold_violations)

    notes, violated = [], []

    method_ok = predicted_method == gold.gold_methodology
    if not method_ok:
        notes.append(
            f"Methodology wrong: answered {predicted_method!r}, expected "
            f"{gold.gold_methodology!r} for this brief."
        )
        violated.append(f"choose-{gold.gold_methodology}")

    precision, recall, f1 = set_f1(predicted_violations, gold_violations)
    missed = sorted(set(gold_violations) - set(predicted_violations))
    invented = sorted(set(predicted_violations) - set(gold_violations))
    if missed:
        notes.append(f"Missed OntoClean violations: {missed}.")
        violated.append("apply-ontoclean-constraints")
    if invented:
        notes.append(f"Reported violations that do not breach any constraint: {invented}.")
        violated.append("only-report-real-violations")

    notes.append(f"methodology_ok={int(method_ok)} violation_f1={f1:.2f}")
    return ScoreReport(0.5 * method_ok + 0.5 * f1, notes, list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("choose-neon",
                 "When the brief mentions reusing existing ontologies, thesauri, databases "
                 "or other non-ontological resources, choose NeOn: reuse is its distinctive "
                 "contribution."),
            Rule("choose-diligent",
                 "When the brief describes a distributed, decentralised or evolving effort "
                 "with many contributors, choose DILIGENT."),
            Rule("choose-samod",
                 "When the brief asks for agile, iterative or test-driven development in "
                 "small increments, choose SAMOD."),
            Rule("choose-on-to-knowledge",
                 "When the brief leads with a business case, feasibility or knowledge "
                 "management pilot, choose On-To-Knowledge."),
            Rule("apply-ontoclean-constraints",
                 "Check every subsumption against the OntoClean constraints: an anti-rigid "
                 "class cannot subsume a rigid one, an anti-unity class cannot subsume one "
                 "with unity, and a dependent class cannot subsume an independent one."),
            Rule("only-report-real-violations",
                 "Report a subsumption as a violation only when a named constraint is "
                 "actually breached; a logically consistent axiom is not automatically wrong."),
        ]
    )


AUDIT_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are auditing an ontology project. Recommend a methodology and review the "
    "taxonomy."
)


def audit_responder(inputs: dict, active: set[str]) -> dict:
    """A weak auditor: defaults to the famous methodology, and trusts the taxonomy.

    Un-instructed it does what an inexperienced engineer does — names
    METHONTOLOGY because it is the one everybody has heard of, and reports no
    violations because the axioms "look fine" (they are all consistent).
    """
    brief = inputs.get("brief", "") or ""
    taxonomy_text = inputs.get("taxonomy", "") or ""

    # Parse the taxonomy from the *input*, not from a lookup table. This matters:
    # it lets the notebook ablate the dataset (e.g. remove every sound axiom) and
    # observe the effect on what the optimiser can learn.
    pairs = []
    for line in taxonomy_text.splitlines():
        if "<=" in line:
            sub, sup = line.split("<=", 1)
            pairs.append((sub.strip(), sup.strip()))

    correct_method = ch5.recommend_methodology(brief)["recommended"]
    rule_for = {
        "neon": "choose-neon",
        "diligent": "choose-diligent",
        "samod": "choose-samod",
        "on-to-knowledge": "choose-on-to-knowledge",
    }.get(correct_method)
    # METHONTOLOGY is the default answer, so it is right by accident when it is right.
    methodology = correct_method if (rule_for is None or rule_for in active) else "methontology"

    if "apply-ontoclean-constraints" in active:
        found = sorted({v["axiom"] for v in ch5.ontoclean_violations(pairs)})
    else:
        found = []
    if "only-report-real-violations" not in active and found:
        # over-eager: also flags the first sound axiom. Note this failure is only
        # *possible* when a sound axiom is present to be mis-flagged.
        extra = [f"{sub} <= {sup}" for sub, sup in pairs if f"{sub} <= {sup}" not in found]
        found = found + extra[:1]

    return {
        "methodology": methodology,
        "violations": json.dumps(found),
        "justification": f"Recommended {methodology}; {len(found)} taxonomy issue(s).",
    }


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def AuditSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _AuditSignature(dspy.Signature):
            """Recommend a methodology and audit a taxonomy."""

            brief: str = dspy.InputField(desc="the project brief")
            taxonomy: str = dspy.InputField(desc="subsumption axioms, one per line")
            methodology: str = dspy.OutputField(desc="the methodology id to use")
            violations: str = dspy.OutputField(
                desc='JSON array of the offending axioms, e.g. ["Person <= Student"]')
            justification: str = dspy.OutputField(desc="one sentence")

        _SIG = _AuditSignature
    return _SIG


def AuditProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.audit = dspy.Predict(AuditSignature())
            if instruction:
                self.audit.signature = self.audit.signature.with_instructions(instruction)

        def forward(self, brief: str, taxonomy: str):
            return self.audit(brief=brief, taxonomy=taxonomy)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch5Context:
    completed: set = None
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.completed = self.completed if self.completed is not None else set()
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch5Context):
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def list_methodologies() -> str:
        """List the methodologies with the project signals each one fits.

        Call this before recommending one, so the choice is made from the brief
        rather than from familiarity.
        """
        return json.dumps(ch5.methodology_table())

    def recommend_methodology(brief: str) -> str:
        """Score every methodology against a project brief and rank them."""
        return json.dumps(ch5.recommend_methodology(brief))

    def ontoclean_tags(class_name: str) -> str:
        """Look up a class's OntoClean meta-properties (rigidity, identity, unity, dependence).

        Call this before judging a subsumption: the constraints are stated over
        these meta-properties, not over the class names.
        """
        tags = ch5.ONTOCLEAN_TAGS.get(class_name)
        if tags is None:
            return json.dumps({"class": class_name, "known": False})
        return json.dumps({"class": class_name, "known": True, "rigidity": tags.rigidity,
                           "identity": tags.identity, "unity": tags.unity,
                           "dependence": tags.dependence})

    def check_taxonomy(axioms: str) -> str:
        """Check subsumption axioms ('Sub <= Super', one per line) against OntoClean.

        Call this whenever asked to review a taxonomy for quality. It finds
        errors that are ontologically wrong yet logically consistent, so a DL
        reasoner will not report them.
        """
        pairs = []
        for line in axioms.splitlines():
            if "<=" in line:
                sub, sup = line.split("<=", 1)
                pairs.append((sub.strip(), sup.strip()))
        return json.dumps(ch5.ontoclean_violations(pairs))

    def list_constraints() -> str:
        """Explain the OntoClean taxonomy constraints and why each one matters."""
        return json.dumps(ch5.ONTOCLEAN_CONSTRAINTS)

    def competency_question_coverage() -> str:
        """Measure what fraction of the competency questions the ontology answers,
        given the development steps completed so far."""
        return json.dumps({"completed": sorted(ctx.completed),
                           "coverage": ch5.coverage_for_steps(ctx.completed)})

    def perform_step(step: str) -> str:
        """Perform a development step, if its prerequisites are complete."""
        spec = ch5.DEVELOPMENT_STEPS.get(step)
        if spec is None:
            return json.dumps({"error": f"unknown step {step!r}"})
        missing = [r for r in spec["requires"] if r not in ctx.completed]
        if missing:
            return json.dumps({"error": f"cannot do {step!r} yet", "missing": missing})
        ctx.completed.add(step)
        return json.dumps({"completed": sorted(ctx.completed),
                           "coverage": ch5.coverage_for_steps(ctx.completed)})

    impls = [list_methodologies, recommend_methodology, ontoclean_tags,
             check_taxonomy, list_constraints, competency_question_coverage, perform_step]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Planning MDP with prerequisites
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlanState:
    """Which development steps are done, and whether the project has shipped."""

    done: frozenset[str]
    shipped: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        order = ["requirements", "competency_questions", "reuse_search",
                 "taxonomy", "axioms", "instances", "evaluation"]
        short = "".join(s[0].upper() if s in self.done else "." for s in order)
        return short + ("!" if self.shipped else "")


class MethodologyPlanMDP:
    """Plan an ontology development project under precedence constraints.

    Every earlier MDP in the course had all actions available at all times.
    Here an action is **unavailable until its prerequisites are complete** —
    which is exactly what a methodology asserts. The reward is the *measured*
    competency-question coverage at ship time, minus the effort spent.

    The optimal policy therefore has to discover that the cheap-looking
    shortcut — ship a taxonomy without writing competency questions first — is
    not available at all, and that some steps are worth their cost only because
    they unlock others.
    """

    def __init__(self, steps: dict | None = None, gamma: float = 1.0,
                 coverage_fn=None):
        self.steps = steps or ch5.DEVELOPMENT_STEPS
        self.names = sorted(self.steps)
        self.gamma = gamma
        self.coverage_fn = coverage_fn or ch5.coverage_for_steps
        self._cache: dict[frozenset, float] = {}

    def initial_state(self) -> PlanState:
        return PlanState(frozenset())

    def is_terminal(self, state: PlanState) -> bool:
        return state.shipped

    def states(self) -> list[PlanState]:
        import itertools

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
        cost = self.steps[action]["cost"]
        return [(1.0, PlanState(state.done | {action}, False), -cost)]

    def step(self, state: PlanState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)
