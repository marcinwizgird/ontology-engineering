"""Chapter 2 problem-set support — formalising an access policy, and checking it.

Provided code for ``04_assignment.ipynb``. The student builds the grader, the
Claude formaliser and the compliance agent in the notebook; this module supplies
what a real project would already have in its codebase:

* the **policy corpus** — English policy statements, a fixed predicate
  vocabulary, gold formulas, and a train / dev / test split by item;
* **semantic comparison** (:func:`equivalent`) and **mistake naming**
  (:func:`diagnose`) on top of Chapter 2's model checker;
* the **guidelines** a formalisation scorer reports (:data:`POLICY_RULEBOOK`);
* a **compliance knowledge base** and a ground entailment checker
  (:func:`ground_entails`, a small DPLL solver) for the agent's tools;
* **proof search as an MDP** (:class:`ProofSearchMDP`).

Why the grader is unusual and worth dwelling on: most LLM evaluation is stuck
with string overlap or a judge because the task has no decision procedure.
Formalisation has one — two formulas mean the same thing when they have the same
models — so Chapter 2's own semantics *is* the grader.
"""

from __future__ import annotations

import functools
import itertools
import json
from dataclasses import dataclass, field

import ch02_toolkit as fol

__all__ = [
    "VOCABULARY", "vocabulary_text", "POLICY_ITEMS", "build_dataset",
    "equivalent", "diagnose", "model_space_bits", "POLICY_RULEBOOK",
    "POLICY_KB", "FACTS", "COMPLIANCE_QUERIES", "ground_entails", "verdict",
    "PolicyWorkspace", "build_policy_tools", "ProofSearchMDP",
]


# --------------------------------------------------------------------------- #
# The vocabulary the formaliser must use
# --------------------------------------------------------------------------- #
#: predicate -> (arity, gloss). The gold formulas use exactly these names.
VOCABULARY: dict[str, tuple[int, str]] = {
    "Clinician": (1, "x is a clinician"),
    "Nurse": (1, "x is a nurse"),
    "Employee": (1, "x is an employee of the hospital"),
    "Contractor": (1, "x is a contractor"),
    "Auditor": (1, "x is an auditor"),
    "External": (1, "x is external to the hospital"),
    "Patient": (1, "x is a patient"),
    "Consented": (1, "x (a patient) has given research consent"),
    "Record": (1, "x is a health record"),
    "Sensitive": (1, "x (a record) is marked sensitive"),
    "Treats": (2, "x treats y"),
    "About": (2, "record x is about patient y"),
    "CanAccess": (2, "x can access record y"),
    "Supervises": (2, "x supervises y"),
}


def vocabulary_text() -> str:
    """The vocabulary as the formaliser sees it: one predicate per line."""
    lines = []
    for name, (arity, gloss) in VOCABULARY.items():
        args = "x" if arity == 1 else "x, y"
        lines.append(f"{name}({args}): {gloss}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The policy corpus
# --------------------------------------------------------------------------- #
#: (id, split, statement, gold formula). Split is fixed by item and balanced by
#: phenomenon, so no split can be solved by memorising a sibling item.
POLICY_ITEMS: list[tuple[str, str, str, str]] = [
    # --- train ---------------------------------------------------------------
    ("clinicians-are-employees", "train", "Every clinician is an employee.",
     "forall x (Clinician(x) -> Employee(x))"),
    ("some-auditor-external", "train", "Some auditor is external.",
     "exists x (Auditor(x) & External(x))"),
    ("no-contractor-clinician", "train", "No contractor is a clinician.",
     "forall x (Contractor(x) -> ~Clinician(x))"),
    ("records-about-patients", "train", "Every record is about some patient.",
     "forall x (Record(x) -> exists y (Patient(y) & About(x, y)))"),
    ("someone-supervises-all-nurses", "train", "There is someone who supervises every nurse.",
     "exists x forall y (Nurse(y) -> Supervises(x, y))"),
    ("only-clinicians-access", "train", "Only clinicians can access records.",
     "forall x forall y ((Record(y) & CanAccess(x, y)) -> Clinician(x))"),
    ("not-all-employees-clinicians", "train", "Not every employee is a clinician.",
     "~forall x (Employee(x) -> Clinician(x))"),
    ("no-self-treatment", "train", "No clinician treats themselves.",
     "forall x (Clinician(x) -> ~Treats(x, x))"),
    # --- dev -----------------------------------------------------------------
    ("nurses-are-clinicians", "dev", "All nurses are clinicians.",
     "forall x (Nurse(x) -> Clinician(x))"),
    ("some-record-sensitive", "dev", "Some records are sensitive.",
     "exists x (Record(x) & Sensitive(x))"),
    ("contractors-no-access", "dev", "Contractors cannot access any record.",
     "forall x (Contractor(x) -> ~exists y (Record(y) & CanAccess(x, y)))"),
    ("clinicians-treat-someone", "dev", "Every clinician treats some patient.",
     "forall x (Clinician(x) -> exists y (Patient(y) & Treats(x, y)))"),
    ("every-nurse-supervised", "dev", "Every nurse is supervised by someone.",
     "forall y (Nurse(y) -> exists x Supervises(x, y))"),
    ("auditor-external-or-employee", "dev", "Every auditor is either external or an employee.",
     "forall x (Auditor(x) -> (External(x) | Employee(x)))"),
    ("some-nurse-treats-nobody", "dev", "Some nurse treats no patient.",
     "exists x (Nurse(x) & ~exists y (Patient(y) & Treats(x, y)))"),
    ("supervisors-of-nurses-clinicians", "dev", "Anyone who supervises a nurse is a clinician.",
     "forall x forall y ((Supervises(x, y) & Nurse(y)) -> Clinician(x))"),
    # --- test ----------------------------------------------------------------
    ("contractors-not-employees", "test", "No contractor is an employee.",
     "forall x (Contractor(x) -> ~Employee(x))"),
    ("some-patient-consented", "test", "At least one patient has given research consent.",
     "exists x (Patient(x) & Consented(x))"),
    ("external-auditors-no-sensitive", "test",
     "No external auditor can access a sensitive record.",
     "forall x ((Auditor(x) & External(x)) -> ~exists y (Record(y) & Sensitive(y) & CanAccess(x, y)))"),
    ("patients-have-records", "test", "Every patient has at least one record about them.",
     "forall y (Patient(y) -> exists x (Record(x) & About(x, y)))"),
    ("one-clinician-treats-all", "test", "Some clinician treats every patient.",
     "exists x (Clinician(x) & forall y (Patient(y) -> Treats(x, y)))"),
    ("only-consented-sensitive", "test",
     "Sensitive records exist only about patients who have consented.",
     "forall x forall y ((Record(x) & Sensitive(x) & About(x, y)) -> Consented(y))"),
    ("auditor-external-iff-not-employee", "test",
     "An auditor is external exactly when they are not an employee.",
     "forall x (Auditor(x) -> (External(x) <-> ~Employee(x)))"),
    ("every-patient-treated", "test", "Every patient is treated by some clinician.",
     "forall y (Patient(y) -> exists x (Clinician(x) & Treats(x, y)))"),
]


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows (inputs: statement, vocabulary)."""
    import dspy

    vocab = vocabulary_text()
    rows = [
        dspy.Example(id=item_id, split=item_split, statement=text, vocabulary=vocab,
                     gold_formula=formula).with_inputs("statement", "vocabulary")
        for item_id, item_split, text, formula in POLICY_ITEMS
    ]
    return rows if split == "all" else [r for r in rows if r.split == split]


# --------------------------------------------------------------------------- #
# Semantic comparison — the grader's core
# --------------------------------------------------------------------------- #
def model_space_bits(formulas, size: int) -> int:
    """How many ground atoms a model of this size must decide.

    The number of models the checker enumerates is ``2 ** bits`` — which is why
    the grader refuses (rather than hangs on) a formula with too big a signature.
    """
    signature: dict[str, int] = {}
    for f in formulas:
        signature.update(fol.predicates(f))
    return sum(size ** arity for arity in signature.values())


@functools.lru_cache(maxsize=4096)
def _equivalent_cached(a_text: str, b_text: str, max_size: int) -> bool:
    a, b = fol.parse(a_text), fol.parse(b_text)
    return fol.entails([a], b, max_size)[0] and fol.entails([b], a, max_size)[0]


def equivalent(a, b, max_size: int = 2) -> bool:
    """Do two closed formulas have the same models on every domain up to ``max_size``?

    Two-way finite entailment. Not full logical equivalence (undecidable), but
    sound in the direction that matters for grading: a *difference* found is a
    real difference, witnessed by an explicit model. Memoised on the normalised
    text, because an optimiser grades the same answer many times.
    """
    return _equivalent_cached(fol.to_string(a), fol.to_string(b), max_size)


def diagnose(predicted, gold) -> str | None:
    """Name the classic mistake, when the shape of the error is recognisable.

    Returning a *named* pitfall rather than "wrong" is what lets a GEPA metric
    tell the optimiser something it can act on.
    """
    match (predicted, gold):
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


def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("emit-parseable-formula",
             "Answer with one formula in the ASCII syntax -- forall/exists, ~ & | -> <->, "
             "predicates written Name(arg, ...) -- and nothing else: no prose, no "
             "Unicode symbols, no code fences."),
        Rule("close-every-variable",
             "Bind every variable with a quantifier; a free variable leaves the "
             "statement without a truth value."),
        Rule("use-the-vocabulary",
             "Use only the predicates listed in the vocabulary, with exactly the "
             "listed arity and argument order; do not invent synonyms."),
        Rule("universal-uses-implication",
             "Translate 'every/all X is Y' as forall x (X(x) -> Y(x)); a conjunction "
             "under a universal claims everything in the domain is an X."),
        Rule("existential-uses-conjunction",
             "Translate 'some X is Y' as exists x (X(x) & Y(x)); an implication under "
             "an existential is satisfied by any non-X and asserts almost nothing."),
        Rule("quantifier-order-matters",
             "Keep the quantifier order of the English: 'everyone R something' is "
             "forall x exists y, 'someone R everything' is exists x forall y."),
        Rule("negation-scope",
             "Translate 'no X is Y' as forall x (X(x) -> ~Y(x)), with the negation "
             "inside the universal; 'not every X is Y' negates the whole universal."),
        Rule("match-the-intended-reading",
             "Check the formula against the English: direction of 'only', what is "
             "required versus permitted, and which argument plays which role."),
    ])


#: The guidelines a formalisation scorer reports as violated.
POLICY_RULEBOOK = _rulebook()


# --------------------------------------------------------------------------- #
# The compliance knowledge base (Part D)
# --------------------------------------------------------------------------- #
#: The policy the checker enforces (already formalised and reviewed).
POLICY_KB: list[tuple[str, str]] = [
    ("nurses-are-clinicians", "forall x (Nurse(x) -> Clinician(x))"),
    ("clinicians-are-employees", "forall x (Clinician(x) -> Employee(x))"),
    ("contractors-no-access",
     "forall x (Contractor(x) -> ~exists y (Record(y) & CanAccess(x, y)))"),
    ("treating-clinician-access",
     "forall x forall y forall z ((Clinician(x) & Treats(x, y) & About(z, y)) -> CanAccess(x, z))"),
    ("only-clinicians-access",
     "forall x forall y ((Record(y) & CanAccess(x, y)) -> Clinician(x))"),
    ("external-auditors-no-sensitive",
     "forall x ((Auditor(x) & External(x)) -> ~exists y (Record(y) & Sensitive(y) & CanAccess(x, y)))"),
]

#: Ground facts about the hospital on the day of the audit (closed domain).
FACTS: list[str] = [
    "Nurse(Ana)", "Treats(Ana, Pia)", "Patient(Pia)", "Record(R1)", "About(R1, Pia)",
    "Clinician(Ben)", "Patient(Ole)", "Record(R2)", "About(R2, Ole)", "Sensitive(R2)",
    "Contractor(Cal)", "Auditor(Dee)", "External(Dee)",
]

#: (id, question, conclusion to test, gold verdict). Gold verdicts are recomputed
#: with :func:`verdict` in the notebook, and asserted there, so they cannot drift.
#: Constants start with an upper-case letter (Chapter 2's syntax); variables do not.
COMPLIANCE_QUERIES: list[tuple[str, str, str, str]] = [
    ("ana-r1", "May Ana read record R1?", "CanAccess(Ana, R1)", "yes"),
    ("ana-employee", "Is Ana an employee?", "Employee(Ana)", "yes"),
    ("cal-r1", "May Cal read record R1?", "CanAccess(Cal, R1)", "no"),
    ("dee-r2", "May Dee read record R2?", "CanAccess(Dee, R2)", "no"),
    ("ben-r2", "May Ben read record R2?", "CanAccess(Ben, R2)", "undetermined"),
    ("dee-r1", "May Dee read record R1?", "CanAccess(Dee, R1)", "undetermined"),
]


def _constants(formulas) -> list[str]:
    names: set[str] = set()
    for f in formulas:
        names |= fol.constants_in(f)
    return sorted(names)


def _dpll(clauses: list[frozenset[str]], assignment: dict[str, bool]) -> dict[str, bool] | None:
    """Tiny DPLL: a satisfying assignment of literal strings, or None."""
    clauses = [c for c in clauses]
    while True:
        simplified = []
        unit = None
        for clause in clauses:
            if any(_lit_value(l, assignment) is True for l in clause):
                continue
            rest = frozenset(l for l in clause if _lit_value(l, assignment) is None)
            if not rest:
                return None
            if len(rest) == 1 and unit is None:
                unit = next(iter(rest))
            simplified.append(rest)
        clauses = simplified
        if not clauses:
            return assignment
        if unit is None:
            break
        atom, value = (unit[1:], False) if unit.startswith("~") else (unit, True)
        assignment = {**assignment, atom: value}
    literal = next(iter(clauses[0]))
    atom = literal.lstrip("~")
    for value in (True, False):
        result = _dpll(clauses, {**assignment, atom: value})
        if result is not None:
            return result
    return None


def _lit_value(literal: str, assignment: dict[str, bool]):
    atom = literal.lstrip("~")
    if atom not in assignment:
        return None
    return assignment[atom] != literal.startswith("~")


def ground_entails(premises, conclusion) -> tuple[bool, dict[str, bool] | None]:
    """Does the policy entail ``conclusion`` when the domain is the named individuals?

    The closed-domain assumption (only the constants mentioned exist) turns FOL
    entailment into propositional satisfiability, which DPLL decides. Returns
    ``(entailed, counterexample)``: when not entailed, the counterexample is a
    world consistent with the premises in which the conclusion is false.
    """
    premises = list(premises)
    names = _constants(premises + [conclusion]) or ["a"]
    clauses: list[frozenset[str]] = []
    for f in premises + [fol.Not(conclusion)]:
        clauses += fol.to_cnf_clauses(fol.ground(f, names))
    model = _dpll(clauses, {})
    return model is None, model


def verdict(premises, conclusion) -> str:
    """'yes' if entailed, 'no' if its negation is entailed, else 'undetermined'."""
    if ground_entails(premises, conclusion)[0]:
        return "yes"
    if ground_entails(premises, fol.Not(conclusion))[0]:
        return "no"
    return "undetermined"


# --------------------------------------------------------------------------- #
# Agent tools (Part D)
# --------------------------------------------------------------------------- #
@dataclass
class PolicyWorkspace:
    """What the compliance agent can see: the policy, the facts, and its call log."""

    policy: list[tuple[str, str]] = field(default_factory=lambda: list(POLICY_KB))
    facts: list[str] = field(default_factory=lambda: list(FACTS))
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()

    def premises(self) -> list:
        return [fol.parse(f) for _, f in self.policy] + [fol.parse(f) for f in self.facts]


def build_policy_tools(ws: PolicyWorkspace):
    """The compliance agent's tools: read the policy, read the facts, check a claim."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def read_policy() -> str:
        """List the formalised access policy: one (id, formula) pair per rule."""
        return json.dumps([{"id": i, "formula": f} for i, f in ws.policy])

    def read_facts() -> str:
        """List the ground facts about named people, patients and records."""
        return json.dumps(ws.facts)

    def check_entailment(conclusion: str) -> str:
        """Decide whether policy + facts entail a closed formula over the named individuals.

        Use the policy's predicate names and the capitalised constants from the facts,
        e.g. 'CanAccess(Ana, R1)' or '~CanAccess(Cal, R1)'. Returns entailed=true/false and, when false, a
        counterexample world. To answer a yes/no question, check the claim AND its
        negation: neither entailed means the policy does not settle the question.
        """
        entailed, model = ground_entails(ws.premises(), fol.parse(conclusion))
        counter = None
        if model is not None:
            counter = {k: v for k, v in sorted(model.items()) if "(" in k}
        return json.dumps({"conclusion": conclusion, "entailed": entailed,
                           "counterexample": counter})

    impls = [read_policy, read_facts, check_entailment]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Proof search as an MDP (Part D)
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

    States are sets of derived clauses; actions derive a resolvent or claim a
    verdict. Claiming entailment is rewarded only once the empty clause has been
    derived — the reward pays for *proving*, not for guessing right. Each
    derivation costs ``step_cost``; a wrong or unjustified verdict costs
    ``wrong_verdict_penalty``.

    The clause universe is the resolution closure, capped — which is itself the
    lesson: proof search is only enumerable here because the problem is tiny.
    """

    def __init__(self, base_clauses, entailed: bool, step_cost: float = 0.05,
                 wrong_verdict_penalty: float = 1.0, cap: int = 10, gamma: float = 1.0):
        self.universe = self._closure(base_clauses, cap)
        self.base = frozenset(self.universe.index(frozenset(c)) for c in base_clauses)
        self.empty_index = next((i for i, c in enumerate(self.universe) if not c), None)
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
            "claim:entailed", "claim:not-entailed"]

    def transition(self, state: ProofState, action: str):
        if action.startswith("claim:"):
            claimed = action == "claim:entailed"
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
