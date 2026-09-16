"""Chapter 2 agentic lab — formalisation, and proof search as an MDP.

The task: turn an English statement into a first-order formula. What makes it a
*good* teaching task for agents is that the metric can be **semantic rather than
textual**. Two formulas are scored equal when they have the same models up to a
finite size — so `forall x (P(x) -> Q(x))` and `~exists x (P(x) & ~Q(x))` both
earn full marks, and no amount of superficial string similarity earns any.

That is unusual and worth dwelling on: most LLM evaluation is stuck with string
overlap or a judge because the task has no decision procedure. Here Chapter 2's
own semantics *is* the grader.

The MDP is proof search: states are sets of derived clauses, actions are
resolution steps, and the reward pays for a correct verdict minus the cost of
getting there. Solving it exactly shows the shortest proof — and how fast the
state space grows.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass

import ch02_toolkit as fol

__all__ = [
    "TRANSLATION_TASKS", "build_dataset", "translation_scorer",
    "FOL_RULEBOOK", "fol_responder", "FormalisationProgram", "BASELINE_INSTRUCTION",
    "equivalent", "diagnose", "build_toolset", "Ch2Context", "ProofSearchMDP",
]


# --------------------------------------------------------------------------- #
# Semantic comparison — the grader
# --------------------------------------------------------------------------- #
def equivalent(a, b, max_size: int = 2) -> bool:
    """Do two formulas have the same models up to ``max_size``?

    Two-way finite entailment. Not full logical equivalence (undecidable), but
    sound in the direction that matters for grading: a *difference* found is a
    real difference, witnessed by an explicit model.
    """
    return fol.entails([a], b, max_size)[0] and fol.entails([b], a, max_size)[0]


def diagnose(predicted, gold) -> str | None:
    """Name the classic mistake, when the shape of the error is recognisable.

    Returning a *named* pitfall rather than "wrong" is what lets the GEPA metric
    tell the optimiser something it can act on.
    """
    match (predicted, gold):
        # 'No X is Y' first. Negating the whole universal is a *scope* error, and
        # naming it that way matters: told only "use implication", the author
        # would fix nothing here.
        case (fol.Not(fol.ForAll(_, _)), fol.ForAll(_, fol.Implies(_, fol.Not(_)))):
            return "negation-scope"
        case (fol.ForAll(_, fol.And(_, _)), fol.ForAll(_, fol.Implies(_, _))):
            return "universal-uses-implication"
        case (fol.Exists(_, fol.Implies(_, _)), fol.Exists(_, fol.And(_, _))):
            return "existential-uses-conjunction"
        case (fol.Exists(_, fol.ForAll(_, _)), fol.ForAll(_, fol.Exists(_, _))):
            return "quantifier-order-matters"
        case (fol.ForAll(_, fol.Exists(_, _)), fol.Exists(_, fol.ForAll(_, _))):
            return "quantifier-order-matters"
    return None


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
#: Each item targets one formalisation decision from §2.1.
TRANSLATION_TASKS = [
    ("every-human-mortal", "Every human is mortal.",
     "forall x (Human(x) -> Mortal(x))"),
    ("some-student-enrolled", "Some student is enrolled.",
     "exists x (Student(x) & Enrolled(x))"),
    ("all-giraffes-herbivores", "All giraffes are herbivores.",
     "forall x (Giraffe(x) -> Herbivore(x))"),
    ("some-lion-hungry", "Some lion is hungry.",
     "exists x (Lion(x) & Hungry(x))"),
    ("everyone-teaches-something", "Everyone teaches something.",
     "forall x exists y Teaches(x, y)"),
    ("no-plant-animal", "No plant is an animal.",
     "forall x (Plant(x) -> ~Animal(x))"),
    ("every-branch-part-tree", "Every branch is part of some tree.",
     "forall x (Branch(x) -> exists y (Tree(y) & PartOf(x, y)))"),
    ("some-carnivore-eats-impala", "Some carnivore eats an impala.",
     "exists x (Carnivore(x) & exists y (Impala(y) & Eats(x, y)))"),
    ("all-trees-plants", "All trees are plants.",
     "forall x (Tree(x) -> Plant(x))"),
    ("someone-teaches-everything", "There is someone who teaches everything.",
     "exists x forall y Teaches(x, y)"),
]


def build_dataset(split: str = "all"):
    import dspy

    examples = [
        dspy.Example(statement=text, gold_formula=formula, id=task_id).with_inputs("statement")
        for task_id, text, formula in TRANSLATION_TASKS
    ]
    if split == "train":
        return examples[:6]
    if split == "dev":
        return examples[6:]
    return examples


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
#: Partial credit for a well-formed but wrong formula. The staging matters: it
#: gives the optimiser a gradient to climb in two steps (first *be parseable*,
#: then *be right*) instead of a flat zero that names no direction.
WELLFORMED_CREDIT = 0.25


def translation_scorer(gold, pred):
    """Score a formalisation semantically, and name the mistake when it is classic."""
    from oe_course.evaluation import ScoreReport

    text = str(getattr(pred, "formula", "") or "").strip()
    gold_formula = fol.parse(gold.gold_formula)

    if not text:
        return ScoreReport(0.0, ["No formula produced."], ["emit-parseable-formula"])
    try:
        predicted = fol.parse(text)
    except ValueError as exc:
        return ScoreReport(
            0.0,
            [f"Formula does not parse ({exc}). Answer with the formula alone, in ASCII "
             f"FOL such as 'forall x (P(x) -> Q(x))' -- no surrounding prose."],
            ["emit-parseable-formula"],
        )

    if equivalent(predicted, gold_formula):
        return ScoreReport(1.0, [f"Semantically equivalent to {gold.gold_formula}."], [])

    notes = [
        f"Well-formed, but not equivalent to the intended reading.",
        f"  produced: {fol.to_string(predicted)}",
        f"  intended: {gold.gold_formula}",
    ]
    violated: list[str] = []
    pitfall = diagnose(predicted, gold_formula)
    if pitfall:
        violated.append(pitfall)
        entry = next((p for p in fol.QUANTIFIER_PITFALLS if p["id"] == pitfall), None)
        if entry:
            notes.append(f"  this is the '{pitfall}' error: {entry['why']}")
    else:
        violated.append("match-the-intended-reading")

    countermodel = fol.find_countermodel([predicted], gold_formula, max_size=2) or \
        fol.find_countermodel([gold_formula], predicted, max_size=2)
    if countermodel:
        notes.append("  witnessed by this model, where the two readings differ:")
        notes += [f"    {line}" for line in countermodel.describe().splitlines()]
    return ScoreReport(WELLFORMED_CREDIT, notes, violated)


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("universal-uses-implication",
                 "Translate 'every/all X is Y' as forall x (X(x) -> Y(x)); a conjunction "
                 "under a universal claims every object in the domain is an X."),
            Rule("existential-uses-conjunction",
                 "Translate 'some X is Y' as exists x (X(x) & Y(x)); an implication under "
                 "an existential is satisfied by any non-X and asserts almost nothing."),
            Rule("quantifier-order-matters",
                 "Keep the quantifier order of the English: 'everyone R something' is "
                 "forall x exists y, never exists y forall x."),
            Rule("negation-scope",
                 "Translate 'no X is Y' as forall x (X(x) -> ~Y(x)), putting the negation "
                 "inside the scope of the universal."),
            Rule("emit-parseable-formula",
                 "Answer with a formula in the ASCII syntax: forall/exists, ~ & | -> <->, "
                 "predicates as Name(arg). Nothing else."),
        ]
    )


FOL_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = "Translate the statement into first-order logic."

_UNIVERSAL = ("every", "all ", "each ")
_EXISTENTIAL = ("some", "there is", "a ", "an ")


def fol_responder(inputs: dict, active: set[str]) -> dict:
    """A weak formaliser that makes exactly the mistakes §2.1 warns about."""
    statement = (inputs.get("statement", "") or "").strip()
    lowered = statement.lower()

    task = next((t for t in TRANSLATION_TASKS if t[1].lower() == lowered), None)
    if task is None:
        return {"formula": "", "reading": "unrecognised statement"}
    gold = fol.parse(task[2])

    formula = gold
    # Introduce the classic errors unless the instruction rules them out.
    match gold:
        case fol.ForAll(var, fol.Implies(left, right)):
            if isinstance(right, fol.Not) and "negation-scope" not in active:
                # 'no X is Y' misread as 'not all X are Y'
                formula = fol.Not(fol.ForAll(var, fol.Implies(left, right.sub)))
            elif not isinstance(right, fol.Not) and "universal-uses-implication" not in active:
                formula = fol.ForAll(var, fol.And(left, right))
        case fol.Exists(var, fol.And(left, right)):
            if "existential-uses-conjunction" not in active:
                formula = fol.Exists(var, fol.Implies(left, right))
        case fol.ForAll(v1, fol.Exists(v2, body)):
            if "quantifier-order-matters" not in active:
                formula = fol.Exists(v2, fol.ForAll(v1, body))
        case fol.Exists(v1, fol.ForAll(v2, body)):
            if "quantifier-order-matters" not in active:
                formula = fol.ForAll(v2, fol.Exists(v1, body))

    rendered = fol.to_string(formula)
    if "emit-parseable-formula" not in active:
        rendered = f"The formula is: {rendered}."   # unparseable prose wrapper
    return {"formula": rendered, "reading": f"Read as {fol.to_string(formula)}."}


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def FormalisationSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _FormalisationSignature(dspy.Signature):
            """Translate an English statement into first-order logic."""

            statement: str = dspy.InputField(desc="a statement in English")
            formula: str = dspy.OutputField(desc="the formula in ASCII FOL syntax")
            reading: str = dspy.OutputField(desc="one sentence on the reading chosen")

        _SIG = _FormalisationSignature
    return _SIG


def FormalisationProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.translate = dspy.Predict(FormalisationSignature())
            if instruction:
                self.translate.signature = self.translate.signature.with_instructions(instruction)

        def forward(self, statement: str):
            return self.translate(statement=statement)

    return _Program()


# --------------------------------------------------------------------------- #
# Function tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch2Context:
    """Workspace for the Chapter 2 agent: the formulas asserted so far."""

    premises: list = None
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.premises = self.premises or []
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch2Context):
    """Tools for reasoning about formulas — parse, model-check, refute, prove."""
    from langchain_core.tools import tool

    from oe_course.tools import _instrument

    def parse_formula(text: str) -> str:
        """Check that a formula parses, and report its predicates and free variables.

        Call this before asserting or reasoning with any formula you wrote.
        """
        f = fol.parse(text)
        return json.dumps(
            {"ok": True, "normalised": fol.to_string(f),
             "predicates": fol.predicates(f), "free_vars": sorted(fol.free_vars(f))}
        )

    def assert_premise(text: str) -> str:
        """Add a formula to the working premise set."""
        ctx.premises.append(fol.parse(text))
        return json.dumps({"premises": [fol.to_string(p) for p in ctx.premises]})

    def check_entailment(conclusion: str, max_size: int = 3) -> str:
        """Do the asserted premises entail this conclusion over small finite models?

        Call this to test a claim. If entailment fails you get an explicit
        countermodel, which is the evidence you should report.
        """
        holds, countermodel = fol.entails(ctx.premises, fol.parse(conclusion), max_size)
        return json.dumps(
            {"entails": holds,
             "countermodel": countermodel.describe() if countermodel else None,
             "searched_domains_up_to": max_size}
        )

    def find_countermodel(premise: str, conclusion: str, max_size: int = 3) -> str:
        """Search for a model making `premise` true and `conclusion` false.

        Use this to show that a proposed formalisation is *not* equivalent to
        another one.
        """
        model = fol.find_countermodel([fol.parse(premise)], fol.parse(conclusion), max_size)
        return json.dumps({"countermodel": model.describe() if model else None})

    def prove(conclusion: str, constants: str = "") -> str:
        """Attempt a ground resolution refutation of premises + negated conclusion.

        `constants` is a comma-separated list naming the finite domain. Returns
        the proof trace when it succeeds -- report the proof, not just the verdict.
        """
        names = [c.strip() for c in constants.split(",") if c.strip()]
        goal = fol.parse(conclusion)
        if not names:
            names = sorted(
                set().union(*[fol.constants_in(p) for p in ctx.premises] or [set()])
                | fol.constants_in(goal)
            ) or ["a"]
        clauses = []
        for f in ctx.premises + [fol.Not(goal)]:
            clauses += fol.to_cnf_clauses(fol.ground(f, names))
        refuted, steps, trace = fol.resolution_refutation(clauses)
        return json.dumps(
            {"proved": refuted, "resolution_steps": steps, "domain": names,
             "trace": [[sorted(a), sorted(b), sorted(r)] for a, b, r in trace[:12]]}
        )

    def list_pitfalls() -> str:
        """List the classic formalisation mistakes and how to avoid each one."""
        return json.dumps(fol.QUANTIFIER_PITFALLS)

    impls = [parse_formula, assert_premise, check_entailment,
             find_countermodel, prove, list_pitfalls]
    return [tool(_instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Proof search as an MDP
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProofState:
    """Which clauses have been derived, and whether a verdict has been given."""

    derived: frozenset[int]
    finished: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        return "{" + ",".join(str(i) for i in sorted(self.derived)) + "}" + ("!" if self.finished else "")


class ProofSearchMDP:
    """Resolution proof search over a fixed, pre-computed clause universe.

    Chapter 1's MDP bought information and Chapter 4's built an artefact. This
    one *searches*: actions derive new clauses, and the agent must decide when it
    has seen enough to commit to a verdict.

    The clause universe is the resolution closure, capped — which is itself the
    lesson. Proof search is only enumerable here because the problem is tiny; the
    same construction on a real knowledge base is exactly the intractability
    §2.2 warns about.
    """

    def __init__(self, base_clauses, entailed: bool, step_cost: float = 0.05,
                 wrong_verdict_penalty: float = 1.0, cap: int = 10, gamma: float = 1.0):
        self.universe = self._closure(base_clauses, cap)
        self.base = frozenset(self.universe.index(c) for c in base_clauses)
        self.empty_index = next(
            (i for i, c in enumerate(self.universe) if not c), None
        )
        self.entailed = entailed
        self.step_cost = step_cost
        self.wrong_verdict_penalty = wrong_verdict_penalty
        self.gamma = gamma

    @staticmethod
    def _closure(base_clauses, cap: int) -> list[frozenset[str]]:
        universe = list(dict.fromkeys(frozenset(c) for c in base_clauses))
        changed = True
        while changed and len(universe) < cap:
            changed = False
            for a, b in itertools.combinations(list(universe), 2):
                for r in fol.resolve(a, b):
                    if r not in universe:
                        universe.append(r)
                        changed = True
                        if len(universe) >= cap:
                            break
                if len(universe) >= cap:
                    break
        return universe

    def initial_state(self) -> ProofState:
        return ProofState(self.base)

    def is_terminal(self, state: ProofState) -> bool:
        return state.finished

    def states(self) -> list[ProofState]:
        indices = [i for i in range(len(self.universe)) if i not in self.base]
        out = []
        for r in range(len(indices) + 1):
            for combo in itertools.combinations(indices, r):
                derived = self.base | frozenset(combo)
                out.append(ProofState(derived, False))
                out.append(ProofState(derived, True))
        return out

    def _available_resolutions(self, state: ProofState) -> list[int]:
        present = [self.universe[i] for i in state.derived]
        new = set()
        for a, b in itertools.combinations(present, 2):
            for r in fol.resolve(a, b):
                if r in self.universe:
                    index = self.universe.index(r)
                    if index not in state.derived:
                        new.add(index)
        return sorted(new)

    def actions(self, state: ProofState) -> list[str]:
        if state.finished:
            return []
        return [f"derive:{i}" for i in self._available_resolutions(state)] + [
            "claim:entailed", "claim:not-entailed"
        ]

    def transition(self, state: ProofState, action: str):
        if action.startswith("claim:"):
            claimed = action == "claim:entailed"
            # A claim of entailment is only justified once the empty clause is derived.
            justified = (self.empty_index in state.derived) if claimed else True
            correct = (claimed == self.entailed) and justified
            reward = 1.0 if correct else -self.wrong_verdict_penalty
            return [(1.0, ProofState(state.derived, True), reward)]
        index = int(action.split(":")[1])
        return [(1.0, ProofState(state.derived | {index}, False), -self.step_cost)]

    def step(self, state: ProofState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)

    def describe_action(self, action: str) -> str:
        if action.startswith("claim:"):
            return action
        clause = self.universe[int(action.split(":")[1])]
        return "derive " + ("EMPTY" if not clause else "{" + ", ".join(sorted(clause)) + "}")
