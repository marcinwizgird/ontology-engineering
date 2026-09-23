"""Chapter 6 agentic lab — choosing the right part-whole relation, and asking well.

The agent's task is the one §6.2 is written to prevent: English says "part of"
for at least seven different relations, and an agent that collapses them will
cheerfully derive that a musician's hand is part of an orchestra.

The MDP is new again — a **diagnostic decision tree**. To align a class to a
foundational category the agent asks yes/no questions, each costing something,
and commits when further questioning is not worth the price. Solving it exactly
does something rather satisfying: it **derives DOLCE's decision tree** from a
reward function, instead of taking it on authority. Transitions are stochastic,
because the agent does not know the answer before it asks.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import ch06_toolkit as ch6

__all__ = [
    "PARTWHOLE_CASES", "build_dataset", "partwhole_scorer", "PARTWHOLE_RULEBOOK",
    "partwhole_responder", "PartWholeProgram", "BASELINE_INSTRUCTION",
    "build_toolset", "Ch6Context", "CategoryDiagnosisMDP",
]


# --------------------------------------------------------------------------- #
# Dataset: English statements, with the categories of the two arguments
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PartWholeCase:
    id: str
    statement: str
    part_category: str
    whole_category: str
    separable: bool = False


#: Sixteen statements spanning the taxonomy. Every one is phrased with the words
#: "part of", which is the trap: the English is uniform and the underlying
#: relations are not.
#:
#: The cases are listed as **adjacent pairs of the same relation**, because the
#: split alternates. Every relation therefore appears in both train and dev — a
#: relation seen only in dev could never be learned, and would quietly cap the
#: held-out score (see Chapter 5, Exercise 4.1, for that failure in isolation).
PARTWHOLE_CASES = [
    PartWholeCase("wheel-car", "A wheel is part of a car.",
                  "physical-object", "physical-object"),
    PartWholeCase("door-house", "A door is part of a house.",
                  "physical-object", "physical-object"),

    PartWholeCase("tree-forest", "A tree is part of a forest.",
                  "physical-object", "collection"),
    PartWholeCase("musician-orchestra", "A musician is part of an orchestra.",
                  "physical-object", "collection"),

    PartWholeCase("alcohol-wine", "The alcohol is part of the wine.",
                  "amount-of-matter", "amount-of-matter"),
    PartWholeCase("water-solution", "The water is part of the solution.",
                  "amount-of-matter", "amount-of-matter"),

    PartWholeCase("gold-ring", "The gold is part of the ring.",
                  "amount-of-matter", "physical-object"),
    PartWholeCase("clay-statue", "The clay is part of the statue.",
                  "amount-of-matter", "physical-object"),

    PartWholeCase("lion-hunt", "The lion is part of the hunt.",
                  "physical-object", "process"),
    PartWholeCase("surgeon-operation", "The surgeon is part of the operation.",
                  "physical-object", "process"),

    PartWholeCase("coffee-cup", "The coffee is part of the cup's contents.",
                  "physical-object", "physical-object", separable=True),
    PartWholeCase("letter-envelope", "The letter is part of the envelope's contents.",
                  "physical-object", "physical-object", separable=True),

    PartWholeCase("chewing-eating", "Chewing is part of eating.",
                  "process", "process"),
    PartWholeCase("breathing-singing", "Breathing is part of singing.",
                  "process", "process"),

    PartWholeCase("giraffe-reserve", "The giraffe is part of the reserve.",
                  "physical-object", "region"),
    PartWholeCase("village-valley", "The village is part of the valley.",
                  "physical-object", "region"),
]


def build_dataset(split: str = "all"):
    """Each example: an English statement plus the two categories, with gold answers."""
    import dspy

    examples = []
    for case in PARTWHOLE_CASES:
        relation_id = ch6.classify_partwhole(
            case.part_category, case.whole_category, case.separable)
        relation = ch6.relation_by_id(relation_id)
        examples.append(
            dspy.Example(
                statement=case.statement,
                part_category=case.part_category,
                whole_category=case.whole_category,
                gold_relation=relation_id,
                gold_parthood=relation.parthood,
                id=case.id,
            ).with_inputs("statement", "part_category", "whole_category")
        )
    # Stratified so both halves see parthood and non-parthood cases.
    if split == "train":
        return examples[0::2]
    if split == "dev":
        return examples[1::2]
    return examples


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def partwhole_scorer(gold, pred):
    """Half for naming the relation, half for the parthood verdict.

    The split matters: an agent can pick a plausible relation name and still get
    the logically consequential question — *is this parthood at all?* — wrong.
    Only the second half affects what may be inferred downstream.
    """
    from oe_course.evaluation import ScoreReport

    predicted_relation = str(getattr(pred, "relation", "") or "").strip().lower()
    raw = str(getattr(pred, "is_parthood", "") or "").strip().lower()
    predicted_parthood = raw in {"true", "yes", "y", "1"}

    notes, violated = [], []

    relation_ok = predicted_relation == gold.gold_relation
    if not relation_ok:
        notes.append(
            f"Relation wrong: answered {predicted_relation!r}, correct is "
            f"{gold.gold_relation!r} for a {gold.part_category} in a {gold.whole_category}."
        )
        violated.append({
            "member-of": "member-for-collections",
            "sub-quantity-of": "subquantity-for-amounts",
            "constituted-of": "constitution-not-parthood",
            "participates-in": "participation-not-parthood",
            "contained-in": "containment-not-parthood",
            "located-in": "location-not-parthood",
            "involved-in": "involvement-for-processes",
        }.get(gold.gold_relation, "name-the-relation"))

    parthood_ok = predicted_parthood == bool(gold.gold_parthood)
    if not parthood_ok:
        notes.append(
            f"Parthood verdict wrong: answered {predicted_parthood}, correct is "
            f"{bool(gold.gold_parthood)}. Not every 'part of' in English is parthood."
        )
        violated.append("check-genuine-parthood")

    notes.append(f"relation_ok={int(relation_ok)} parthood_ok={int(parthood_ok)}")
    return ScoreReport(0.5 * relation_ok + 0.5 * parthood_ok, notes,
                       list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("member-for-collections",
                 "When the whole is a collection (an orchestra, a forest, a fleet), the "
                 "relation is member-of, not component-of; members play no structural role."),
            Rule("subquantity-for-amounts",
                 "When both part and whole are amounts of matter (mass nouns), the relation "
                 "is sub-quantity-of, and it is transitive."),
            Rule("constitution-not-parthood",
                 "When an amount of matter makes up an object, the relation is "
                 "constituted-of and it is NOT parthood: the statue is not a kind of clay "
                 "nor a part of it."),
            Rule("participation-not-parthood",
                 "When an enduring object takes part in something that happens, the relation "
                 "is participates-in and it is NOT parthood."),
            Rule("containment-not-parthood",
                 "When the part could be removed leaving the whole unchanged, the relation "
                 "is contained-in and it is NOT parthood."),
            Rule("location-not-parthood",
                 "When the whole is a spatial region, the relation is located-in and it is "
                 "NOT parthood."),
            Rule("involvement-for-processes",
                 "When both part and whole are processes, the relation is involved-in, and "
                 "it is transitive parthood."),
            Rule("check-genuine-parthood",
                 "Decide separately whether the relation is genuine mereological parthood; "
                 "containment, constitution, location and participation are not."),
        ]
    )


PARTWHOLE_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are an ontology engineer. Say which part-whole relation the statement "
    "expresses."
)

#: Which rule licenses each relation. Without it, the simulator falls back to the
#: naive answer — component-of, and "yes it is parthood" — which is exactly what
#: an ontology with a single `partOf` property asserts.
_RULE_FOR_RELATION = {
    "member-of": "member-for-collections",
    "sub-quantity-of": "subquantity-for-amounts",
    "constituted-of": "constitution-not-parthood",
    "participates-in": "participation-not-parthood",
    "contained-in": "containment-not-parthood",
    "located-in": "location-not-parthood",
    "involved-in": "involvement-for-processes",
}


def partwhole_responder(inputs: dict, active: set[str]) -> dict:
    """Simulate the single-`partOf`-property modeller, improving rule by rule."""
    part = (inputs.get("part_category", "") or "").strip()
    whole = (inputs.get("whole_category", "") or "").strip()
    statement = (inputs.get("statement", "") or "")

    # 'contents' is the textual cue that the part is separable.
    separable = "contents" in statement.lower()
    correct = ch6.classify_partwhole(part, whole, separable)
    needed = _RULE_FOR_RELATION.get(correct)

    relation = correct if (needed is None or needed in active) else "component-of"

    if "check-genuine-parthood" in active:
        parthood = ch6.relation_by_id(relation).parthood
    else:
        parthood = True          # the naive default: everything is parthood

    return {
        "relation": relation,
        "is_parthood": str(parthood).lower(),
        "justification": f"A {part} in a {whole} is related by {relation}.",
    }


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def PartWholeSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _PartWholeSignature(dspy.Signature):
            """Identify which part-whole relation a statement expresses."""

            statement: str = dspy.InputField(desc="an English part-whole statement")
            part_category: str = dspy.InputField(desc="the foundational category of the part")
            whole_category: str = dspy.InputField(desc="the foundational category of the whole")
            relation: str = dspy.OutputField(desc="the relation id, e.g. component-of")
            is_parthood: str = dspy.OutputField(
                desc="true or false: is this genuine mereological parthood?")
            justification: str = dspy.OutputField(desc="one sentence")

        _SIG = _PartWholeSignature
    return _SIG


def PartWholeProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.classify = dspy.Predict(PartWholeSignature())
            if instruction:
                self.classify.signature = self.classify.signature.with_instructions(instruction)

        def forward(self, statement: str, part_category: str, whole_category: str):
            return self.classify(statement=statement, part_category=part_category,
                                 whole_category=whole_category)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch6Context:
    answers: dict = None
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.answers = self.answers if self.answers is not None else {}
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch6Context):
    import json

    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def foundational_categories() -> str:
        """List the foundational categories with glosses and examples.

        Call this before aligning a class: the part-whole relation follows from
        the categories, so getting the categories right comes first.
        """
        return json.dumps([
            {"id": c.id, "name": c.name, "branch": c.branch,
             "gloss": c.gloss, "examples": list(c.examples)}
            for c in ch6.CATEGORIES
        ])

    def ask_decision_question(question: str, answer: str) -> str:
        """Record an answer to a foundational-category decision question.

        Valid questions: happens, spatial, mass, dependent, telic. Returns the
        categories still consistent with everything answered so far.
        """
        if question not in ch6.DECISION_QUESTIONS:
            return json.dumps({"error": f"unknown question {question!r}",
                               "valid": sorted(ch6.DECISION_QUESTIONS)})
        ctx.answers[question] = str(answer).strip().lower() in {"true", "yes", "y", "1"}
        remaining = ch6.identify_category(ctx.answers)
        return json.dumps({"answers": ctx.answers, "candidates": remaining})

    def list_decision_questions() -> str:
        """The decision questions used to place a class in a foundational category."""
        return json.dumps(ch6.DECISION_QUESTIONS)

    def part_whole_relations() -> str:
        """List the part-whole relations, with which are parthood and which transitive.

        Call this whenever asked about a 'part of' statement: several of these
        relations are not parthood, and treating them alike is the error this
        chapter is about.
        """
        return json.dumps([
            {"id": r.id, "name": r.name, "parthood": r.parthood,
             "transitive": r.transitive, "part": r.part_category,
             "whole": r.whole_category, "example": r.example, "test": r.test}
            for r in ch6.PART_WHOLE_RELATIONS
        ])

    def classify_relation(part_category: str, whole_category: str,
                          separable: str = "false") -> str:
        """Pick the part-whole relation from the categories of part and whole."""
        sep = str(separable).strip().lower() in {"true", "yes", "y", "1"}
        relation_id = ch6.classify_partwhole(part_category, whole_category, sep)
        r = ch6.relation_by_id(relation_id)
        return json.dumps({"relation": relation_id, "parthood": r.parthood,
                           "transitive": r.transitive, "example": r.example})

    def check_chaining(first: str, second: str) -> str:
        """Decide whether two part-whole statements may be composed.

        Call this before inferring a part-whole fact from two others: most
        part-whole relations are NOT transitive and may not be chained.
        """
        return json.dumps(ch6.can_chain(first, second))

    impls = [foundational_categories, list_decision_questions, ask_decision_question,
             part_whole_relations, classify_relation, check_chaining]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# A diagnostic MDP: derive the decision tree instead of memorising it
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiagnosisState:
    """The candidate categories still consistent with the answers so far."""

    candidates: frozenset[str]
    committed: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        return "{" + ",".join(sorted(c.split("-")[0] for c in self.candidates)) + "}" + (
            "!" if self.committed else "")


class CategoryDiagnosisMDP:
    """Align a class to a foundational category by asking as few questions as possible.

    | | |
    |---|---|
    | **S** | the set of categories still consistent with the answers |
    | **A** | ask a question that actually splits the set, or commit |
    | **T** | **stochastic** — the answer is not known until it is asked |
    | **R** | −cost per question; on commit, the probability of being right |

    Committing with `k` candidates left is right with probability `1/k` under a
    uniform prior, so the agent trades questions against accuracy. Value
    iteration then produces an optimal question *order* — which is what a
    foundational ontology's decision tree is.
    """

    def __init__(self, question_cost: float = 0.05, gamma: float = 1.0,
                 categories: dict | None = None,
                 questions: tuple[str, ...] | None = None):
        self.categories = categories or {
            c.id: ch6.category_answers(c.id) for c in ch6.CATEGORIES
        }
        self.questions = questions or tuple(ch6.DECISION_QUESTIONS)
        self.question_cost = question_cost
        self.gamma = gamma
        self._states: list[DiagnosisState] | None = None

    def initial_state(self) -> DiagnosisState:
        return DiagnosisState(frozenset(self.categories))

    def is_terminal(self, state: DiagnosisState) -> bool:
        return state.committed

    def _split(self, candidates: frozenset[str], question: str):
        yes = frozenset(c for c in candidates if self.categories[c][question])
        no = frozenset(c for c in candidates if not self.categories[c][question])
        return yes, no

    def states(self) -> list[DiagnosisState]:
        """Only *reachable* candidate sets — the full power set is never visited."""
        if self._states is not None:
            return self._states
        reachable = {frozenset(self.categories)}
        frontier = [frozenset(self.categories)]
        while frontier:
            current = frontier.pop()
            for question in self.questions:
                for part in self._split(current, question):
                    if part and part != current and part not in reachable:
                        reachable.add(part)
                        frontier.append(part)
        self._states = [DiagnosisState(s, c) for s in reachable for c in (False, True)]
        return self._states

    def actions(self, state: DiagnosisState) -> list[str]:
        if state.committed:
            return []
        useful = [
            f"ask:{q}" for q in self.questions
            if all(part for part in self._split(state.candidates, q))
        ]
        return useful + ["commit"]

    def transition(self, state: DiagnosisState, action: str):
        if action == "commit":
            accuracy = 1.0 / len(state.candidates)
            return [(1.0, DiagnosisState(state.candidates, True), accuracy)]
        question = action.split(":", 1)[1]
        yes, no = self._split(state.candidates, question)
        total = len(state.candidates)
        out = []
        for part in (yes, no):
            if part:
                out.append((len(part) / total,
                            DiagnosisState(part, False),
                            -self.question_cost))
        return out

    def step(self, state: DiagnosisState, action: str):
        import random

        outcomes = self.transition(state, action)
        roll, cumulative = random.random(), 0.0
        for p, nxt, reward in outcomes:
            cumulative += p
            if roll <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        p, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)

    def decision_tree(self, policy: dict, state: DiagnosisState | None = None,
                      depth: int = 0) -> list[str]:
        """Render the optimal policy as the decision tree it really is."""
        state = state or self.initial_state()
        action = policy.get(state)
        indent = "  " * depth
        if action is None or action == "commit":
            return [f"{indent}-> {sorted(state.candidates)}"]
        question = action.split(":", 1)[1]
        yes, no = self._split(state.candidates, question)
        lines = [f"{indent}{question}? ({ch6.DECISION_QUESTIONS[question]})"]
        for label, part in (("yes", yes), ("no", no)):
            if part:
                lines.append(f"{indent}  {label}:")
                lines += self.decision_tree(policy, DiagnosisState(part, False), depth + 2)
        return lines
