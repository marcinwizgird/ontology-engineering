"""Chapter 10 agentic lab — picking the formalism, and paying for the search.

Choosing a representation is the decision this chapter is about, and it is one
an agent gets wrong in a characteristic way: it reaches for **crisp** because
crisp is what it has seen most. A crisp threshold on a vague predicate produces
confident nonsense at exactly the boundary where the answer matters.

The agent therefore answers two things per requirement: which formalism, and
what that formalism **costs** in reasoning terms. The second half is the
chapter's thesis in a field — expressivity is never free, and general Allen
network consistency is NP-complete while fuzzy membership and rough
approximation are polynomial.

The MDP is **constraint propagation with early exit**: which triple should the
solver compose next, and when has it seen enough to declare? Declaring
inconsistency is only rewarded once a label has actually been emptied — the same
"prove it, do not guess it" discipline as Chapter 2's proof search, applied to a
different search.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import ch10_toolkit as ch10

__all__ = [
    "build_dataset", "formalism_scorer", "FORMALISM_RULEBOOK", "formalism_responder",
    "FormalismProgram", "BASELINE_INSTRUCTION", "build_toolset", "Ch10Context",
    "PropagationMDP", "EXPRESSIVITY_COST",
]


#: What each formalism costs to reason with. These are not stylistic labels:
#: deciding consistency of a general Allen network is NP-complete, while fuzzy
#: membership and rough approximation are polynomial.
EXPRESSIVITY_COST = {
    "crisp": "none",
    "fuzzy": "low",
    "rough": "low",
    "temporal": "high",
}


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
def build_dataset(split: str = "all"):
    """Requirements, each imperfect in exactly one way."""
    import dspy

    examples = [
        dspy.Example(
            requirement=text,
            gold_formalism=formalism,
            gold_cost=EXPRESSIVITY_COST[formalism],
            id=identifier,
        ).with_inputs("requirement")
        for identifier, text, formalism in ch10.REQUIREMENTS
    ]
    if split == "all":
        return examples

    # Stratify by formalism so both halves see all four.
    groups: dict = {}
    for example in examples:
        groups.setdefault(example.gold_formalism, []).append(example)
    train, dev = [], []
    for key in sorted(groups):
        for index, example in enumerate(groups[key]):
            (train if index % 2 == 0 else dev).append(example)
    return train if split == "train" else dev


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def formalism_scorer(gold, pred):
    """Half for the formalism, half for its reasoning cost."""
    from oe_course.evaluation import ScoreReport

    formalism = str(getattr(pred, "formalism", "") or "").strip().lower()
    cost = str(getattr(pred, "cost", "") or "").strip().lower()

    notes, violated = [], []

    formalism_ok = formalism == gold.gold_formalism
    if not formalism_ok:
        notes.append(
            f"Formalism wrong: answered {formalism!r}, correct is "
            f"{gold.gold_formalism!r} for this requirement."
        )
        violated.append({
            "temporal": "temporal-for-interval-relations",
            "fuzzy": "fuzzy-for-vague-predicates",
            "rough": "rough-for-indiscernible-data",
            "crisp": "crisp-when-boundaries-are-sharp",
        }[gold.gold_formalism])
        if gold.gold_formalism == "fuzzy" and formalism == "crisp":
            notes.append(
                "  A crisp threshold on a vague predicate is confidently wrong exactly "
                "at the boundary, which is where the decision is hard."
            )

    cost_ok = cost == gold.gold_cost
    if not cost_ok:
        notes.append(
            f"Reasoning cost wrong: answered {cost!r}, correct is {gold.gold_cost!r}."
        )
        violated.append("price-the-expressivity")

    notes.append(f"formalism_ok={int(formalism_ok)} cost_ok={int(cost_ok)}")
    return ScoreReport(0.5 * formalism_ok + 0.5 * cost_ok, notes,
                       list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("temporal-for-interval-relations",
                 "When the requirement relates two things that happen over time -- before, "
                 "during, overlapping, meeting -- use an interval temporal formalism."),
            Rule("fuzzy-for-vague-predicates",
                 "When the predicate has no sharp boundary (tall, warm, elderly), use fuzzy "
                 "membership; a crisp threshold is arbitrary exactly where it matters."),
            Rule("rough-for-indiscernible-data",
                 "When the recorded attributes cannot tell some objects apart, use rough "
                 "sets and report a lower and an upper approximation."),
            Rule("crisp-when-boundaries-are-sharp",
                 "When identifiers, counts and exact limits are involved, stay crisp: "
                 "adding machinery you do not need costs reasoning time for nothing."),
            Rule("price-the-expressivity",
                 "State the reasoning cost of the formalism chosen: none for crisp, low for "
                 "fuzzy and rough, high for interval temporal reasoning (deciding "
                 "consistency of a general Allen network is NP-complete)."),
        ]
    )


FORMALISM_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are a knowledge engineer. Choose a representation for the requirement."
)

_SIGNALS = {
    "temporal": ("before", "during", "overlap", "after", "begins", "while",
                 "meets", "finishes", "happens"),
    "fuzzy": ("tall", "warm", "elderly", "young", "large", "roughly", "about"),
    "rough": ("identical", "indiscernible", "cannot distinguish", "granule",
              "agree on every"),
}


def formalism_responder(inputs: dict, active: set[str]) -> dict:
    """A weak engineer whose reflex is 'model it crisply and move on'."""
    text = (inputs.get("requirement", "") or "").lower()

    detected = "crisp"
    for formalism, signals in _SIGNALS.items():
        if any(signal in text for signal in signals):
            detected = formalism
            break

    rule = {
        "temporal": "temporal-for-interval-relations",
        "fuzzy": "fuzzy-for-vague-predicates",
        "rough": "rough-for-indiscernible-data",
        "crisp": "crisp-when-boundaries-are-sharp",
    }[detected]
    # Crisp is the default answer, so it is right by accident when it is right.
    formalism = detected if (detected == "crisp" or rule in active) else "crisp"

    if "price-the-expressivity" in active:
        cost = EXPRESSIVITY_COST[formalism]
    else:
        cost = "none"          # the naive answer: reasoning is assumed free

    return {
        "formalism": formalism,
        "cost": cost,
        "justification": f"Chose {formalism} with {cost} reasoning cost.",
    }


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def FormalismSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _FormalismSignature(dspy.Signature):
            """Choose a representation for a requirement, and price it."""

            requirement: str = dspy.InputField(desc="the requirement in English")
            formalism: str = dspy.OutputField(desc="crisp, temporal, fuzzy or rough")
            cost: str = dspy.OutputField(desc="reasoning cost: none, low or high")
            justification: str = dspy.OutputField(desc="one sentence")

        _SIG = _FormalismSignature
    return _SIG


def FormalismProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.choose = dspy.Predict(FormalismSignature())
            if instruction:
                self.choose.signature = self.choose.signature.with_instructions(instruction)

        def forward(self, requirement: str):
            return self.choose(requirement=requirement)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch10Context:
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch10Context):
    import json

    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def allen_relations() -> str:
        """The thirteen interval relations, with their names.

        Call this when a requirement relates two things that happen over time.
        """
        return json.dumps(ch10.ALLEN_NAMES)

    def relation_between(a_start: int, a_end: int, b_start: int, b_end: int) -> str:
        """The Allen relation holding between two concrete intervals."""
        relation = ch10.relation_between((a_start, a_end), (b_start, b_end))
        return json.dumps({"relation": relation, "name": ch10.ALLEN_NAMES[relation]})

    def check_temporal_consistency(constraints: str) -> str:
        """Check a temporal network for consistency.

        `constraints` is JSON like {"A,B": ["b"], "B,C": ["b"], "A,C": ["bi"]}.
        Call this before asserting a set of temporal facts: humans are very bad
        at spotting cycles in interval constraints.
        """
        try:
            raw = json.loads(constraints)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"could not parse constraints: {exc}"})
        nodes, parsed = set(), {}
        for key, relations in raw.items():
            i, j = [part.strip() for part in key.split(",")]
            nodes.update([i, j])
            parsed[(i, j)] = set(relations)
        network = ch10.Network.complete(tuple(sorted(nodes)), parsed)
        return json.dumps(ch10.path_consistent(network))

    def fuzzy_membership(set_name: str, value: float) -> str:
        """Degree of membership of a value in a vague set (short, average, tall)."""
        if set_name not in ch10.FUZZY_SETS:
            return json.dumps({"error": f"unknown set {set_name!r}",
                               "available": sorted(ch10.FUZZY_SETS)})
        return json.dumps({"set": set_name, "value": value,
                           "membership": ch10.membership(set_name, float(value))})

    def rough_approximation(target: str) -> str:
        """Lower and upper approximations of a set of patients, and the accuracy.

        Call this when the recorded attributes cannot separate some objects: the
        gap between the two approximations is the part you genuinely cannot decide.
        """
        names = [t.strip() for t in target.split(",") if t.strip()]
        system = ch10.SAMPLE_SYSTEM
        return json.dumps({
            "target": names,
            "lower": system.lower_approximation(names),
            "upper": system.upper_approximation(names),
            "boundary": system.boundary(names),
            "accuracy": system.accuracy(names),
        })

    def expressivity_cost(formalism: str) -> str:
        """The reasoning cost of a formalism, with the reason."""
        reasons = {
            "crisp": "standard reasoning; no extra machinery",
            "fuzzy": "membership is pointwise; reasoning stays polynomial",
            "rough": "approximations come from partitioning; polynomial",
            "temporal": "consistency of a general Allen network is NP-complete",
        }
        key = formalism.strip().lower()
        return json.dumps({"formalism": key,
                           "cost": EXPRESSIVITY_COST.get(key, "unknown"),
                           "why": reasons.get(key, "unknown formalism")})

    impls = [allen_relations, relation_between, check_temporal_consistency,
             fuzzy_membership, rough_approximation, expressivity_cost]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Constraint propagation as an MDP
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
    """Decide a temporal network's consistency, choosing what to propagate.

    A constraint solver narrows label sets by composing through a third
    interval. Each composition costs; the agent must decide **which** to do and
    **when to stop**.

    | | |
    |---|---|
    | **S** | the three label sets, and whether a verdict was given |
    | **A** | propagate through A, B or C; or declare consistent / inconsistent |
    | **T** | deterministic — composition is a function |
    | **R** | −cost per propagation; ``+1`` for a **justified** correct verdict |

    As in Chapter 2, "justified" carries the weight: declaring inconsistency is
    only rewarded once a label has actually been emptied. Guessing right earns
    nothing, so the optimal policy has to do the work.
    """

    def __init__(self, ab, bc, ac, consistent: bool,
                 cost: float = 0.05, wrong_penalty: float = 1.0, gamma: float = 1.0,
                 require_check: bool = False):
        self.start = PropagationState(frozenset(ab), frozenset(bc), frozenset(ac))
        self.consistent = consistent
        self.cost = cost
        self.wrong_penalty = wrong_penalty
        self.gamma = gamma
        #: When true, a *consistency* claim must also be earned -- see the note on
        #: the asymmetric reward in the Chapter 10 lab.
        self.require_check = require_check
        self._states = None

    # -- the three propagations ---------------------------------------------
    @staticmethod
    def _narrow(state: PropagationState, via: str) -> PropagationState:
        if via == "B":       # AB o BC narrows AC
            implied = ch10.compose_sets(state.ab, state.bc)
            return PropagationState(state.ab, state.bc, state.ac & implied,
                                    False, True)
        if via == "A":       # BA o AC narrows BC
            ba = frozenset(ch10.inverse(r) for r in state.ab)
            implied = ch10.compose_sets(ba, state.ac)
            return PropagationState(state.ab, state.bc & implied, state.ac,
                                    False, True)
        # via C: AC o CB narrows AB
        cb = frozenset(ch10.inverse(r) for r in state.bc)
        implied = ch10.compose_sets(state.ac, cb)
        return PropagationState(state.ab & implied, state.bc, state.ac,
                                False, True)

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
            # Nothing has been checked yet, so no verdict is justified.
            return propagations or ["declare:inconsistent"]
        return propagations + ["declare:consistent", "declare:inconsistent"]

    def transition(self, state: PropagationState, action: str):
        if action.startswith("declare:"):
            claimed_consistent = action.endswith("consistent") and "inconsistent" not in action
            # An inconsistency claim must be *witnessed* by an empty label.
            justified = (state.checked or not self.require_check
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
