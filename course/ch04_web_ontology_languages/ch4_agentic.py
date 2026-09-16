"""Chapter 4 agentic lab — axiomatisation under OWL 2 profile constraints.

Chapter 1's agent *assessed* an artefact. This one *builds* one: it turns a
natural-language requirement into an OWL axiom that (a) entails what the
requirement demands and (b) stays inside a requested OWL 2 profile.

Two things make it a genuinely different exercise from Chapter 1, not a reskin:

* **The MDP is a construction problem, not an evidence-gathering one.**
  :class:`AxiomConstructionMDP`'s actions *change the artefact*, so the state is
  the partial ontology and the reward is entailment coverage minus profile
  violations. Chapter 1's actions only bought information.
* **The rules the instruction must convey are Chapter 4's actual content** — the
  existential/universal distinction, is-a versus instance-of, and the profile
  restrictions from §4.2.

Scope note: the profile table here is the same *teaching-grade* simplification
as ``ch4_toolkit.classify_profile`` — enough to make the trade-offs real and
gradeable, not a substitute for a conformance validator. Where it simplifies,
it says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

import rdflib
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef

EX = Namespace("http://example.org/ch4#")

__all__ = [
    "Axiom",
    "AXIOM_OPERATORS",
    "PROFILE_TABLE",
    "profiles_allowing",
    "axiom_to_graph",
    "entails_subclass",
    "REQUIREMENTS",
    "build_dataset",
    "axiom_scorer",
    "AXIOM_RULEBOOK",
    "axiom_responder",
    "AxiomSignature",
    "AxiomProgram",
    "BASELINE_INSTRUCTION",
    "AxiomConstructionMDP",
]


# --------------------------------------------------------------------------- #
# The axiom vocabulary the agent may emit
# --------------------------------------------------------------------------- #
#: A deliberately tiny axiom language. Constraining the output space is what
#: makes the task gradeable *and* what makes profile checking decidable by a
#: lookup table rather than a validator.
AXIOM_OPERATORS = ("subclassof", "some", "only", "type")


@dataclass(frozen=True)
class Axiom:
    """``subject (operator) [property] filler`` — one OWL axiom, structurally.

    ``subclassof``  Subject SubClassOf Filler
    ``some``        Subject SubClassOf property some Filler
    ``only``        Subject SubClassOf property only Filler
    ``type``        Subject rdf:type Filler  (an *instance* assertion)
    """

    subject: str
    operator: str
    filler: str
    property: str = ""

    def normalised(self) -> tuple:
        return (
            self.subject.strip(),
            self.operator.strip().lower(),
            self.property.strip(),
            self.filler.strip(),
        )

    def __str__(self) -> str:
        if self.operator == "subclassof":
            return f"{self.subject} SubClassOf {self.filler}"
        if self.operator == "type":
            return f"{self.subject} Type {self.filler}"
        return f"{self.subject} SubClassOf ({self.property} {self.operator} {self.filler})"

    @classmethod
    def parse(cls, value) -> "Axiom | None":
        """Accept a dict, a JSON object, or ``None``."""
        if isinstance(value, Axiom):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return None
        if not isinstance(value, dict):
            return None
        return cls(
            subject=str(value.get("subject", "")),
            operator=str(value.get("operator", "")).lower(),
            filler=str(value.get("filler", "")),
            property=str(value.get("property", "")),
        )


# --------------------------------------------------------------------------- #
# Profiles (§4.2) — simplified, and honest about it
# --------------------------------------------------------------------------- #
#: Which OWL 2 profiles admit each operator, in the *subclass* position we use.
#:
#: * EL has existential restrictions but **no universal restrictions** — this is
#:   the constraint the lab turns into a rule the agent must learn.
#: * QL forbids existential restrictions in the subclass position.
#: * RL admits all three shapes used here.
PROFILE_TABLE = {
    "subclassof": {"EL", "QL", "RL"},
    "type": {"EL", "QL", "RL"},
    "some": {"EL", "RL"},
    "only": {"RL"},
}


def profiles_allowing(axiom: Axiom) -> set[str]:
    return PROFILE_TABLE.get(axiom.operator, set())


def in_profile(axiom: Axiom, profile: str) -> bool:
    return profile.upper() in profiles_allowing(axiom)


# --------------------------------------------------------------------------- #
# Compiling an axiom to RDF, and checking entailment
# --------------------------------------------------------------------------- #
def axiom_to_graph(axiom: Axiom, graph: Graph | None = None) -> Graph:
    """Compile the structural axiom into real OWL triples."""
    g = graph if graph is not None else Graph()
    subject = EX[axiom.subject]
    filler = EX[axiom.filler]
    g.add((subject, RDF.type, OWL.Class))
    g.add((filler, RDF.type, OWL.Class))

    if axiom.operator == "subclassof":
        g.add((subject, RDFS.subClassOf, filler))
    elif axiom.operator == "type":
        g.add((subject, RDF.type, filler))
    elif axiom.operator in {"some", "only"}:
        prop = EX[axiom.property]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        restriction = rdflib.BNode()
        g.add((restriction, RDF.type, OWL.Restriction))
        g.add((restriction, OWL.onProperty, prop))
        g.add(
            (
                restriction,
                OWL.someValuesFrom if axiom.operator == "some" else OWL.allValuesFrom,
                filler,
            )
        )
        g.add((subject, RDFS.subClassOf, restriction))
    return g


def entails_subclass(axioms: Iterable[Axiom], sub: str, sup: str) -> bool:
    """Does the axiom set entail ``sub SubClassOf sup`` under OWL 2 RL?"""
    import owlrl

    g = Graph()
    for a in axioms:
        axiom_to_graph(a, g)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    return (EX[sub], RDFS.subClassOf, EX[sup]) in g


# --------------------------------------------------------------------------- #
# The dataset: requirements in English, with gold axioms
# --------------------------------------------------------------------------- #
#: Each requirement pins one Chapter-4 modelling decision. ``profile`` is the
#: profile the requirement must stay inside — which is what makes ``only``
#: sometimes the *wrong* answer even when it is the faithful reading.
REQUIREMENTS = [
    {
        "id": "giraffe-isa",
        "text": "Every giraffe is a herbivore.",
        "profile": "EL",
        "axiom": Axiom("Giraffe", "subclassof", "Herbivore"),
    },
    {
        "id": "lion-eats-some",
        "text": "Every lion eats at least one herbivore.",
        "profile": "EL",
        "axiom": Axiom("Lion", "some", "Herbivore", "eats"),
    },
    {
        "id": "giraffe-eats-only",
        "text": "Giraffes eat nothing but leaves.",
        "profile": "RL",
        "axiom": Axiom("Giraffe", "only", "Leaf", "eats"),
    },
    {
        "id": "impala-isa",
        "text": "Every impala is a herbivore.",
        "profile": "QL",
        "axiom": Axiom("Impala", "subclassof", "Herbivore"),
    },
    {
        "id": "warthog-eats-some",
        "text": "A warthog eats some plant.",
        "profile": "RL",
        "axiom": Axiom("Warthog", "some", "Plant", "eats"),
    },
    {
        "id": "simba-instance",
        "text": "Simba is a lion.",
        "profile": "EL",
        "axiom": Axiom("Simba", "type", "Lion"),
    },
    {
        "id": "carnivore-eats-only",
        "text": "A carnivore eats only animals.",
        "profile": "RL",
        "axiom": Axiom("Carnivore", "only", "Animal", "eats"),
    },
    {
        "id": "tree-isa",
        "text": "Every tree is a plant.",
        "profile": "EL",
        "axiom": Axiom("Tree", "subclassof", "Plant"),
    },
    {
        "id": "branch-part-some",
        "text": "Every branch is part of at least one tree.",
        "profile": "EL",
        "axiom": Axiom("Branch", "some", "Tree", "isPartOf"),
    },
    {
        "id": "rockdassie-isa",
        "text": "A rock dassie is a herbivore.",
        "profile": "QL",
        "axiom": Axiom("RockDassie", "subclassof", "Herbivore"),
    },
]


def build_dataset(split: str = "all"):
    """Requirements as ``dspy.Example`` objects, split by requirement."""
    import dspy

    examples = [
        dspy.Example(
            requirement=r["text"],
            profile=r["profile"],
            gold_axiom=r["axiom"],
            requirement_id=r["id"],
        ).with_inputs("requirement", "profile")
        for r in REQUIREMENTS
    ]
    if split == "train":
        return examples[:6]
    if split == "dev":
        return examples[6:]
    return examples


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def axiom_scorer(gold, pred):
    """Half the mark for the right axiom, half for staying inside the profile.

    Splitting the score this way is the point of the exercise: a faithful
    translation that violates the requested profile is only half right, and the
    feedback has to say *which* half failed or the optimiser cannot act on it.
    """
    from oe_course.evaluation import ScoreReport

    gold_axiom: Axiom = gold.gold_axiom
    profile = gold.profile
    predicted = Axiom.parse(getattr(pred, "axiom", None))

    notes: list[str] = []
    violated: list[str] = []

    if predicted is None:
        return ScoreReport(0.0, ["No parseable axiom was produced."], ["emit-structured-axiom"])

    correct = predicted.normalised() == gold_axiom.normalised()
    if not correct:
        notes.append(f"Axiom wrong: produced {predicted}, expected {gold_axiom}.")
        if gold_axiom.operator == "subclassof" and predicted.operator == "type":
            violated.append("isa-is-subclassof")
        elif gold_axiom.operator == "some" and predicted.operator == "only":
            violated.append("some-for-existential")
        elif gold_axiom.operator == "only" and predicted.operator == "some":
            violated.append("only-for-universal")
        else:
            violated.append("emit-structured-axiom")

    profile_ok = in_profile(predicted, profile)
    if not profile_ok:
        notes.append(
            f"Axiom uses '{predicted.operator}', which is outside OWL 2 {profile} "
            f"(allowed there: {sorted(k for k, v in PROFILE_TABLE.items() if profile in v)})."
        )
        violated.append("respect-profile")

    score = 0.5 * float(correct) + 0.5 * float(profile_ok)
    notes.append(f"axiom_correct={int(correct)} profile_ok={int(profile_ok)}")
    return ScoreReport(score, notes, list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# The rulebook and the offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule(
                "isa-is-subclassof",
                "Translate 'every X is a Y' / 'an X is a Y' as a SubClassOf axiom between "
                "two classes; use rdf:type only for a named individual.",
            ),
            Rule(
                "some-for-existential",
                "Translate 'at least one', 'some', or a bare plural object as an existential "
                "restriction (someValuesFrom), never a universal one.",
            ),
            Rule(
                "only-for-universal",
                "Translate 'only', 'nothing but', or 'exclusively' as a universal restriction "
                "(allValuesFrom).",
            ),
            Rule(
                "respect-profile",
                "Check the requested OWL 2 profile before answering: EL has no universal "
                "restrictions and QL has no existential restrictions in the subclass position.",
            ),
            Rule(
                "emit-structured-axiom",
                "Answer with a JSON object holding subject, operator, property and filler; "
                "operator must be one of subclassof, some, only, type.",
            ),
        ]
    )


AXIOM_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are an ontology engineer. Turn the requirement into an OWL axiom."
)

_STOPWORDS = {"a", "an", "the", "every", "some", "at", "least", "one", "nothing", "but",
              "only", "is", "are", "eats", "eat", "of", "part", "exclusively"}


def _terms(text: str) -> list[str]:
    cleaned = text.rstrip(".").replace(",", " ")
    return [w for w in cleaned.split() if w.lower() not in _STOPWORDS]


def axiom_responder(inputs: dict, active: set[str]) -> dict:
    """Simulate a model that starts naive and improves as rules arrive.

    Un-instructed it makes the three errors Chapter 4 is written to prevent:
    it uses rdf:type for is-a, reads a bare plural as universal, and ignores the
    profile entirely.
    """
    requirement = inputs.get("requirement", "")
    profile = (inputs.get("profile", "") or "RL").strip().upper()
    lowered = requirement.lower()
    words = _terms(requirement)

    subject = words[0].capitalize() if words else "Thing"
    filler = words[-1].capitalize() if len(words) > 1 else "Thing"
    # crude singularisation, enough for the fixture vocabulary
    for suffix in ("ves", "s"):
        if filler.endswith(suffix) and len(filler) > 3:
            filler = "Leaf" if filler == "Leaves" else filler[: -len(suffix)]
            break
    if subject.endswith("s") and len(subject) > 3:
        subject = subject[:-1]
    if "rock dassie" in lowered:
        subject = "RockDassie"

    is_instance = subject and subject[0].isupper() and subject in {"Simba"}
    universal = any(w in lowered for w in ("only", "nothing but", "exclusively"))
    existential = any(w in lowered for w in ("at least one", "some", "leaves", "plant"))
    prop = "isPartOf" if "part of" in lowered else ("eats" if "eat" in lowered else "")

    # --- decide the operator ------------------------------------------------
    if is_instance:
        operator = "type"
    elif prop:
        if universal:
            operator = "only" if "only-for-universal" in active else "some"
        else:
            operator = "some" if "some-for-existential" in active else "only"
    else:
        operator = "subclassof" if "isa-is-subclassof" in active else "type"

    # --- profile awareness --------------------------------------------------
    if "respect-profile" in active and operator in PROFILE_TABLE:
        if profile not in PROFILE_TABLE[operator]:
            # Fall back to the most expressive shape the profile does allow.
            for candidate in ("some", "subclassof"):
                if profile in PROFILE_TABLE[candidate]:
                    operator = candidate
                    break

    axiom = {"subject": subject, "operator": operator, "property": prop, "filler": filler}
    if "emit-structured-axiom" not in active and operator not in AXIOM_OPERATORS:
        return {"axiom": f"{subject} {operator} {filler}", "rationale": "best guess"}
    return {
        "axiom": json.dumps(axiom),
        "rationale": f"Read as operator '{operator}' targeting OWL 2 {profile}.",
    }


# --------------------------------------------------------------------------- #
# The DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def AxiomSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _AxiomSignature(dspy.Signature):
            """Turn a requirement into an OWL axiom for a target profile."""

            requirement: str = dspy.InputField(desc="the requirement in English")
            profile: str = dspy.InputField(desc="the OWL 2 profile to stay inside (EL, QL or RL)")
            axiom: str = dspy.OutputField(
                desc='JSON: {"subject":..., "operator":..., "property":..., "filler":...}'
            )
            rationale: str = dspy.OutputField(desc="one sentence on the reading chosen")

        _SIG = _AxiomSignature
    return _SIG


def AxiomProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _AxiomProgram(dspy.Module):
        def __init__(self):
            super().__init__()
            self.translate = dspy.Predict(AxiomSignature())
            if instruction:
                self.translate.signature = self.translate.signature.with_instructions(instruction)

        def forward(self, requirement: str, profile: str):
            return self.translate(requirement=requirement, profile=profile)

    return _AxiomProgram()


# --------------------------------------------------------------------------- #
# A construction MDP — the actions change the artefact
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BuildState:
    """The partial ontology: which candidate axioms have been asserted."""

    asserted: frozenset[int]
    submitted: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{{{','.join(str(i) for i in sorted(self.asserted)) or '-'}}}" + (
            "!" if self.submitted else ""
        )


class AxiomConstructionMDP:
    """Choose which axioms to assert so the required entailments hold.

    Unlike Chapter 1's evidence MDP, an action here **changes the ontology**.
    The reward is entailment coverage minus a penalty for each axiom that leaves
    the requested profile, minus the cost of asserting anything at all — a
    direct encoding of "say what you need, in the profile you promised".
    """

    def __init__(
        self,
        candidates: list[Axiom],
        required_entailments: list[tuple[str, str]],
        profile: str = "EL",
        step_cost: float = 0.05,
        profile_penalty: float = 0.5,
        gamma: float = 1.0,
    ):
        self.candidates = candidates
        self.required = required_entailments
        self.profile = profile.upper()
        self.step_cost = step_cost
        self.profile_penalty = profile_penalty
        self.gamma = gamma

    def initial_state(self) -> BuildState:
        return BuildState(frozenset())

    def is_terminal(self, state: BuildState) -> bool:
        return state.submitted

    def states(self) -> list[BuildState]:
        out = []
        for mask in range(1 << len(self.candidates)):
            chosen = frozenset(i for i in range(len(self.candidates)) if mask & (1 << i))
            out.append(BuildState(chosen, False))
            out.append(BuildState(chosen, True))
        return out

    def actions(self, state: BuildState) -> list[str]:
        if state.submitted:
            return []
        return [f"assert:{i}" for i in range(len(self.candidates))
                if i not in state.asserted] + ["submit"]

    def quality(self, asserted: frozenset[int]) -> float:
        chosen = [self.candidates[i] for i in asserted]
        if not self.required:
            return 0.0
        covered = sum(1 for sub, sup in self.required if entails_subclass(chosen, sub, sup))
        coverage = covered / len(self.required)
        violations = sum(1 for a in chosen if not in_profile(a, self.profile))
        return coverage - self.profile_penalty * violations

    def transition(self, state: BuildState, action: str):
        if action == "submit":
            return [(1.0, BuildState(state.asserted, True), self.quality(state.asserted))]
        index = int(action.split(":")[1])
        return [(1.0, BuildState(state.asserted | {index}, False), -self.step_cost)]

    def step(self, state: BuildState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)
