"""Chapter 3 agentic lab — naming the logic, and paying for the reasoner.

Two things distinguish this lab from Chapters 1, 2 and 4.

**The oracle is free and always right.** The tableau reasoner settles every
question in the dataset, so labels cost nothing to produce. That makes this the
cleanest self-improvement setting in the course: the agent can label its own
failures without a human in the loop.

**The MDP is stochastic.** Every earlier MDP had deterministic transitions. Here
the agent chooses, per query, between a cheap heuristic that is *sometimes*
right and an expensive reasoner that is *always* right — under a call budget.
The optimal policy spends the budget where the heuristic is least reliable, and
value iteration finds it exactly. That is the reasoning-cost trade of §3.3,
expressed as a policy rather than a table of complexity classes.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass

import ch03_toolkit as dl

__all__ = [
    "KB_CASES", "build_dataset", "dl_scorer", "DL_RULEBOOK", "dl_responder",
    "DLProgram", "BASELINE_INSTRUCTION", "build_toolset", "Ch3Context",
    "ReasoningBudgetMDP", "describe_kb",
]

A = dl.Atomic


# --------------------------------------------------------------------------- #
# Knowledge bases the agent is asked about
# --------------------------------------------------------------------------- #
def _kb_basic() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Dog"), A("Mammal"))
    t.add(A("Mammal"), A("Animal"))
    return t


def _kb_alc() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Vegetarian"), dl.And(A("Person"), dl.ForAll("eats", dl.Not(A("Meat")))))
    t.add(A("Vegan"), dl.And(A("Vegetarian"), dl.ForAll("eats", dl.Not(A("Dairy")))))
    return t


def _kb_transitive() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Twig"), A("Branch"))
    t.add(A("Branch"), A("TreePart"))
    t.add(A("Branch"), dl.Exists("isPartOf", A("Tree")))
    t.transitive_roles.add("isPartOf")
    return t


def _kb_hierarchy() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Parent"), dl.Exists("hasChild", A("Person")))
    t.role_hierarchy.append(("hasChild", "hasRelative"))
    return t


def _kb_inverse() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Child"), dl.Exists(dl.Inverse("hasChild"), A("Person")))
    return t


def _kb_qualified() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Trilogy"), dl.AtLeast(3, "hasPart", A("Book")))
    return t


def _kb_unqualified() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Overloaded"), A("Busy"))
    t.add(A("Busy"), dl.AtLeast(2, "hasTask"))
    return t


def _kb_wildlife() -> dl.TBox:
    return dl.wildlife_tbox()


def _kb_shiq() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Manager"), dl.AtLeast(2, "supervises", A("Employee")))
    t.add(A("Employee"), dl.Exists(dl.Inverse("supervises"), A("Manager")))
    t.transitive_roles.add("supervises")
    t.role_hierarchy.append(("supervises", "worksWith"))
    return t


def _kb_cyclic() -> dl.TBox:
    t = dl.TBox()
    t.add(A("Head"), A("Node"))
    t.add(A("Node"), dl.Exists("next", A("Node")))
    return t


#: Each case: a TBox, and a subsumption query.
#:
#: The queries are deliberately **balanced between holding and not holding**. An
#: all-true set would let "assume it follows" score full marks, the rule about
#: actually running the reasoner would never be punished, and the optimiser
#: would never learn it. A dataset that cannot punish a mistake cannot teach it.
KB_CASES = [
    ("basic-taxonomy", _kb_basic, ("Dog", "Animal")),            # True
    ("vegetarian-alc", _kb_alc, ("Vegetarian", "Vegan")),        # False
    ("parts-transitive", _kb_transitive, ("Twig", "TreePart")),  # True
    ("family-hierarchy", _kb_hierarchy, ("Parent", "Person")),   # False
    ("child-inverse", _kb_inverse, ("Child", "Person")),         # False
    ("trilogy-qualified", _kb_qualified, ("Trilogy", "Book")),   # False
    ("busy-unqualified", _kb_unqualified, ("Overloaded", "Busy")),  # True
    ("wildlife", _kb_wildlife, ("Giraffe", "Animal")),           # True
    ("supervision-shiq", _kb_shiq, ("Manager", "Employee")),     # False
    ("cyclic-nodes", _kb_cyclic, ("Head", "Node")),              # True
]


def describe_kb(tbox: dl.TBox) -> str:
    """A neutral, textual rendering of a TBox — the agent's input.

    Deliberately *syntactic*: it states the axioms and role facts without naming
    the logic, so the naming task is not given away in the prompt.
    """
    lines = [f"axiom: {ax}" for ax in tbox.axioms]
    if tbox.transitive_roles:
        lines.append(f"transitive roles: {sorted(tbox.transitive_roles)}")
    if tbox.role_hierarchy:
        lines.append(f"role hierarchy: {[f'{a} sub-role of {b}' for a, b in tbox.role_hierarchy]}")
    if tbox.functional_roles:
        lines.append(f"functional roles: {sorted(tbox.functional_roles)}")
    if tbox.nominals:
        lines.append(f"nominals: {sorted(tbox.nominals)}")
    return "\n".join(lines)


def build_dataset(split: str = "all"):
    """Each example: a KB description + a subsumption query, with gold answers."""
    import dspy

    examples = []
    for name, builder, (sub, sup) in KB_CASES:
        tbox = builder()
        examples.append(
            dspy.Example(
                kb=describe_kb(tbox),
                query=f"{sub} subsumed by {sup}?",
                gold_dl=dl.dl_name(tbox),
                gold_subsumption=dl.subsumes(A(sub), A(sup), tbox),
                id=name,
            ).with_inputs("kb", "query")
        )
    # Stratified, not sequential. A first-six/last-four cut would put every
    # transitive and inverse case in train and leave dev almost trivial, so the
    # held-out score would flatter the agent. Alternating keeps both halves
    # covering the constructor range and both verdicts.
    if split == "train":
        return examples[0::2]
    if split == "dev":
        return examples[1::2]
    return examples


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def dl_scorer(gold, pred):
    """Half for naming the logic, half for the entailment verdict."""
    from oe_course.evaluation import ScoreReport

    predicted_dl = str(getattr(pred, "dl", "") or "").strip()
    raw_verdict = str(getattr(pred, "subsumption", "") or "").strip().lower()
    verdict = raw_verdict in {"true", "yes", "y", "1"}

    notes, violated = [], []

    dl_ok = predicted_dl.upper() == gold.gold_dl.upper()
    if not dl_ok:
        notes.append(f"DL name wrong: answered {predicted_dl!r}, correct is {gold.gold_dl!r}.")
        expected, got = gold.gold_dl.upper(), predicted_dl.upper()
        if expected.startswith("S") and got.startswith("ALC"):
            violated.append("s-for-transitive")
        if "H" in expected and "H" not in got:
            violated.append("h-for-role-hierarchy")
        if "I" in expected and "I" not in got:
            violated.append("i-for-inverse")
        if "Q" in expected and "Q" not in got:
            violated.append("q-for-qualified-number")
        if not violated:
            violated.append("name-the-logic-exactly")

    verdict_ok = verdict == bool(gold.gold_subsumption)
    if not verdict_ok:
        notes.append(
            f"Subsumption verdict wrong: answered {verdict}, the reasoner says "
            f"{bool(gold.gold_subsumption)}."
        )
        violated.append("use-the-reasoner")

    notes.append(f"dl_ok={int(dl_ok)} verdict_ok={int(verdict_ok)}")
    return ScoreReport(0.5 * dl_ok + 0.5 * verdict_ok, notes, list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("s-for-transitive",
                 "When any role is transitive the base logic is S, not ALC: S abbreviates "
                 "ALC extended with transitive roles."),
            Rule("h-for-role-hierarchy",
                 "Append H when the knowledge base declares a sub-role axiom."),
            Rule("i-for-inverse",
                 "Append I when any role appears inverted (written r-)."),
            Rule("q-for-qualified-number",
                 "Append Q for number restrictions with a filler concept (>=n r.C); use N "
                 "only for unqualified ones (>=n r)."),
            Rule("use-the-reasoner",
                 "Never guess a subsumption. Run the reasoner: C is subsumed by D exactly "
                 "when C and not D is unsatisfiable."),
        ]
    )


DL_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are a description logic expert. Given the knowledge base, say which "
    "description logic it needs and answer the subsumption query."
)


def _degrade(name: str, active: set[str]) -> str:
    """Turn the correct DL name into the one a partly-instructed model gives."""
    out = name
    if "s-for-transitive" not in active and out.startswith("S"):
        out = "ALC" + out[1:]
    if "h-for-role-hierarchy" not in active:
        out = out.replace("H", "")
    if "i-for-inverse" not in active:
        out = out.replace("I", "")
    if "q-for-qualified-number" not in active:
        out = out.replace("Q", "N")
    return out


def dl_responder(inputs: dict, active: set[str]) -> dict:
    """A weak DL expert that improves as the instruction gets specific."""
    kb_text = inputs.get("kb", "") or ""
    query = inputs.get("query", "") or ""

    case = next(
        (
            (name, builder, pair)
            for name, builder, pair in KB_CASES
            if describe_kb(builder()) == kb_text
        ),
        None,
    )
    if case is None:
        return {"dl": "ALC", "subsumption": "true", "justification": "unrecognised KB"}

    _, builder, (sub, sup) = case
    tbox = builder()
    correct_dl = dl.dl_name(tbox)

    answer_dl = _degrade(correct_dl, active)
    if "use-the-reasoner" in active:
        verdict = dl.subsumes(A(sub), A(sup), tbox)
        justification = f"Checked with the tableau: {sub} and not {sup} is " + (
            "unsatisfiable." if verdict else "satisfiable."
        )
    else:
        # the classic failure: assume the hierarchy says what it looks like
        verdict = True
        justification = "It looks like it follows from the axioms."

    return {"dl": answer_dl, "subsumption": str(verdict).lower(), "justification": justification}


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def DLSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _DLSignature(dspy.Signature):
            """Name the description logic and answer a subsumption query."""

            kb: str = dspy.InputField(desc="the knowledge base axioms and role facts")
            query: str = dspy.InputField(desc="a subsumption question")
            dl: str = dspy.OutputField(desc="the description logic name, e.g. ALC, SHIQ")
            subsumption: str = dspy.OutputField(desc="true or false")
            justification: str = dspy.OutputField(desc="one sentence")

        _SIG = _DLSignature
    return _SIG


def DLProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.answer = dspy.Predict(DLSignature())
            if instruction:
                self.answer.signature = self.answer.signature.with_instructions(instruction)

        def forward(self, kb: str, query: str):
            return self.answer(kb=kb, query=query)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch3Context:
    tbox: dl.TBox = None
    name: str = ""
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.tbox = self.tbox if self.tbox is not None else dl.TBox()
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch3Context):
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    cases = {name: builder for name, builder, _ in KB_CASES}

    def load_kb(name: str) -> str:
        """Load a named knowledge base from the chapter's case set.

        Call this first. Use list_kbs if you do not know the names.
        """
        ctx.tbox = cases[name]()
        ctx.name = name
        return json.dumps({"loaded": name, "axioms": len(ctx.tbox.axioms)})

    def list_kbs() -> str:
        """List the available knowledge base names."""
        return json.dumps(sorted(cases))

    def show_axioms() -> str:
        """Show the loaded knowledge base's axioms and role facts."""
        return describe_kb(ctx.tbox)

    def dl_expressivity() -> str:
        """Report which DL constructors the loaded KB uses, and its DL name.

        Call this before claiming a knowledge base is in a particular logic --
        the constructors, not your impression of the axioms, decide the name.
        """
        return json.dumps(
            {"dl": dl.dl_name(ctx.tbox), "constructors": sorted(dl.constructors_used(ctx.tbox))}
        )

    def check_satisfiability(concept_a: str, concept_b: str = "") -> str:
        """Is `concept_a` (optionally conjoined with `concept_b`) satisfiable?

        Use this to test whether a class can have any instances at all.
        """
        c = A(concept_a) if not concept_b else dl.And(A(concept_a), A(concept_b))
        result = dl.satisfiable(c, ctx.tbox)
        return json.dumps({"satisfiable": result.satisfiable, "steps": result.steps,
                           "branches": result.branches})

    def check_subsumption(sub: str, sup: str) -> str:
        """Does the KB entail that `sub` is subsumed by `sup`?

        Call this instead of reasoning by eye whenever asked whether one class
        falls under another. It runs a tableau, so the answer is sound.
        """
        return json.dumps({"subsumed": dl.subsumes(A(sub), A(sup), ctx.tbox)})

    def tableau_trace(concept_a: str, concept_b: str = "") -> str:
        """Return the tableau expansion trace -- the proof behind a verdict."""
        c = A(concept_a) if not concept_b else dl.And(A(concept_a), A(concept_b))
        result = dl.satisfiable(c, ctx.tbox, trace=True)
        return json.dumps({"satisfiable": result.satisfiable, "trace": result.trace[:25]})

    impls = [load_kb, list_kbs, show_axioms, dl_expressivity,
             check_satisfiability, check_subsumption, tableau_trace]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# A stochastic MDP: when is the reasoner worth calling?
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BudgetState:
    """Which query we are on, and how much of the reasoner budget is spent."""

    index: int
    used: int

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"q{self.index}/used{self.used}"


class ReasoningBudgetMDP:
    """Answer a series of queries: cheap guess, or costly sound reasoning?

    For each query the agent may:

    * **guess** — free, correct with probability ``p_i`` (a structural heuristic
      such as "it is asserted in the hierarchy, so it must follow");
    * **reason** — always correct, costs ``reasoner_cost`` and consumes one unit
      of a limited budget.

    Transitions are genuinely **stochastic**: guessing lands in the same next
    state either way, but the reward is Bernoulli. Value iteration therefore
    computes an *expected* return, and the optimal policy is the one §3.3 argues
    for informally — spend soundness where unsoundness is most likely to bite.

    ``p_i`` is per-query on purpose: a uniform accuracy makes the allocation
    problem trivial and hides the interesting behaviour.
    """

    def __init__(self, heuristic_accuracy: list[float], reasoner_cost: float = 0.2,
                 budget: int = 2, gamma: float = 1.0):
        self.accuracy = list(heuristic_accuracy)
        self.reasoner_cost = reasoner_cost
        self.budget = budget
        self.gamma = gamma

    def initial_state(self) -> BudgetState:
        return BudgetState(0, 0)

    def is_terminal(self, state: BudgetState) -> bool:
        return state.index >= len(self.accuracy)

    def states(self) -> list[BudgetState]:
        return [
            BudgetState(i, u)
            for i in range(len(self.accuracy) + 1)
            for u in range(self.budget + 1)
        ]

    def actions(self, state: BudgetState) -> list[str]:
        if self.is_terminal(state):
            return []
        acts = ["guess"]
        if state.used < self.budget:
            acts.append("reason")
        return acts

    def transition(self, state: BudgetState, action: str):
        i, used = state.index, state.used
        if action == "guess":
            p = self.accuracy[i]
            nxt = BudgetState(i + 1, used)
            # Same successor, different reward: a Bernoulli outcome.
            return [(p, nxt, 1.0), (1.0 - p, nxt, 0.0)]
        return [(1.0, BudgetState(i + 1, used + 1), 1.0 - self.reasoner_cost)]

    def step(self, state: BudgetState, action: str):
        import random

        outcomes = self.transition(state, action)
        roll, cumulative = random.random(), 0.0
        for p, nxt, reward in outcomes:
            cumulative += p
            if roll <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        p, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)

    def optimal_plan(self, policy: dict) -> list[str]:
        """The action the optimal policy takes on each query, budget permitting."""
        plan, state = [], self.initial_state()
        while not self.is_terminal(state):
            action = policy[state]
            plan.append(action)
            state = BudgetState(state.index + 1, state.used + (action == "reason"))
        return plan
