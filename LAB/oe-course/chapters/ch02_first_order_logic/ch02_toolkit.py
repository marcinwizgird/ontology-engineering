"""Chapter 2 toolkit — first-order logic you can actually execute.

Keet's Chapter 2 gives FOL syntax, Tarskian semantics, and reasoning. Read
passively, all three are inert. Here each becomes a running artefact:

* **syntax** — a parser from ASCII notation to an abstract syntax tree, so a
  formula is an object you can inspect rather than a picture in a book;
* **semantics** — an evaluator over finite interpretations, so "M ⊨ φ" is a
  function call;
* **reasoning** — finite-model entailment checking that returns an explicit
  **countermodel** when entailment fails, plus ground resolution so students see
  a proof procedure rather than only a truth table.

The deliberate limitation: reasoning is over **finite domains**. FOL validity is
undecidable, so any tool that always terminates is doing something weaker. Saying
which weaker thing — and where it breaks — is part of the chapter.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

__all__ = [
    "Atom", "Not", "And", "Or", "Implies", "Iff", "ForAll", "Exists",
    "parse", "to_string", "free_vars", "predicates", "constants_in",
    "Model", "evaluate", "models_of_size", "entails", "find_countermodel",
    "is_valid", "is_satisfiable", "ground", "to_cnf_clauses", "resolve",
    "resolution_refutation", "QUANTIFIER_PITFALLS",
]


# --------------------------------------------------------------------------- #
# Abstract syntax
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Atom:
    pred: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Not:
    sub: object


@dataclass(frozen=True)
class And:
    left: object
    right: object


@dataclass(frozen=True)
class Or:
    left: object
    right: object


@dataclass(frozen=True)
class Implies:
    left: object
    right: object


@dataclass(frozen=True)
class Iff:
    left: object
    right: object


@dataclass(frozen=True)
class ForAll:
    var: str
    body: object


@dataclass(frozen=True)
class Exists:
    var: str
    body: object


# --------------------------------------------------------------------------- #
# Parser:  forall x (Human(x) -> Mortal(x))
# --------------------------------------------------------------------------- #
_TOKEN = re.compile(
    r"\s*(?:(<->|->|&|\||~|\(|\)|,)|([A-Za-z_][A-Za-z0-9_]*))"
)


def _tokenize(text: str) -> list[str]:
    tokens, pos = [], 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"cannot tokenise at position {pos}: {text[pos:pos+12]!r}")
        tokens.append(match.group(1) or match.group(2))
        pos = match.end()
    return tokens


class _Parser:
    """Recursive descent. Precedence (loosest first): <-> , -> , | , & , ~/quantifiers."""

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def eat(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of formula")
        if expected and token != expected:
            raise ValueError(f"expected {expected!r}, found {token!r}")
        self.i += 1
        return token

    def parse(self):
        formula = self.iff()
        if self.peek() is not None:
            raise ValueError(f"trailing input at {self.peek()!r}")
        return formula

    def iff(self):
        left = self.implies()
        while self.peek() == "<->":
            self.eat("<->")
            left = Iff(left, self.implies())
        return left

    def implies(self):
        left = self.disjunction()
        if self.peek() == "->":            # right-associative
            self.eat("->")
            return Implies(left, self.implies())
        return left

    def disjunction(self):
        left = self.conjunction()
        while self.peek() == "|":
            self.eat("|")
            left = Or(left, self.conjunction())
        return left

    def conjunction(self):
        left = self.unary()
        while self.peek() == "&":
            self.eat("&")
            left = And(left, self.unary())
        return left

    def unary(self):
        token = self.peek()
        if token == "~":
            self.eat("~")
            return Not(self.unary())
        if token in {"forall", "exists"}:
            self.eat()
            var = self.eat()
            body = self.unary()
            return ForAll(var, body) if token == "forall" else Exists(var, body)
        if token == "(":
            self.eat("(")
            inner = self.iff()
            self.eat(")")
            return inner
        return self.atom()

    def atom(self):
        name = self.eat()
        if not name[0].isalpha():
            raise ValueError(f"expected a predicate name, found {name!r}")
        args: list[str] = []
        if self.peek() == "(":
            self.eat("(")
            while True:
                args.append(self.eat())
                if self.peek() == ",":
                    self.eat(",")
                    continue
                break
            self.eat(")")
        return Atom(name, tuple(args))


def parse(text: str):
    """Parse ASCII FOL. ``forall``/``exists``, ``~ & | -> <->``.

    >>> parse("forall x (Human(x) -> Mortal(x))")
    ForAll(var='x', body=Implies(...))
    """
    return _Parser(_tokenize(text)).parse()


def to_string(formula) -> str:
    """Render a formula back to the ASCII syntax (round-trips through parse)."""
    match formula:
        case Atom(pred, args):
            return f"{pred}({', '.join(args)})" if args else pred
        case Not(sub):
            return f"~{to_string(sub)}"
        case And(left, right):
            return f"({to_string(left)} & {to_string(right)})"
        case Or(left, right):
            return f"({to_string(left)} | {to_string(right)})"
        case Implies(left, right):
            return f"({to_string(left)} -> {to_string(right)})"
        case Iff(left, right):
            return f"({to_string(left)} <-> {to_string(right)})"
        case ForAll(var, body):
            return f"forall {var} {to_string(body)}"
        case Exists(var, body):
            return f"exists {var} {to_string(body)}"
    raise TypeError(f"not a formula: {formula!r}")


def free_vars(formula, bound: frozenset[str] = frozenset()) -> set[str]:
    match formula:
        case Atom(_, args):
            return {a for a in args if a not in bound and a[0].islower()}
        case Not(sub):
            return free_vars(sub, bound)
        case And(l, r) | Or(l, r) | Implies(l, r) | Iff(l, r):
            return free_vars(l, bound) | free_vars(r, bound)
        case ForAll(var, body) | Exists(var, body):
            return free_vars(body, bound | {var})
    raise TypeError(f"not a formula: {formula!r}")


def predicates(formula) -> dict[str, int]:
    """``{predicate_name: arity}`` occurring in the formula."""
    out: dict[str, int] = {}

    def walk(f):
        match f:
            case Atom(pred, args):
                out[pred] = len(args)
            case Not(sub):
                walk(sub)
            case And(l, r) | Or(l, r) | Implies(l, r) | Iff(l, r):
                walk(l), walk(r)
            case ForAll(_, body) | Exists(_, body):
                walk(body)
    walk(formula)
    return out


def constants_in(formula) -> set[str]:
    """Uppercase-initial arguments are constants; lowercase are variables."""
    out: set[str] = set()

    def walk(f):
        match f:
            case Atom(_, args):
                out.update(a for a in args if a[0].isupper())
            case Not(sub):
                walk(sub)
            case And(l, r) | Or(l, r) | Implies(l, r) | Iff(l, r):
                walk(l), walk(r)
            case ForAll(_, body) | Exists(_, body):
                walk(body)
    walk(formula)
    return out


# --------------------------------------------------------------------------- #
# Semantics
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Model:
    """A finite interpretation: a domain, predicate extensions, constant denotations."""

    domain: tuple[str, ...]
    extensions: dict[str, frozenset[tuple[str, ...]]]
    constants: dict[str, str]

    def describe(self) -> str:
        lines = [f"domain = {{{', '.join(self.domain)}}}"]
        for name, value in sorted(self.constants.items()):
            lines.append(f"{name} = {value}")
        for pred, tuples in sorted(self.extensions.items()):
            if not tuples:
                rendered = "{}"
            else:
                rendered = "{" + ", ".join(
                    ("(" + ",".join(t) + ")") if len(t) > 1 else t[0]
                    for t in sorted(tuples)
                ) + "}"
            lines.append(f"{pred} = {rendered}")
        return "\n".join(lines)


def evaluate(formula, model: Model, assignment: dict[str, str] | None = None) -> bool:
    """Tarskian satisfaction: is ``formula`` true in ``model``?"""
    assignment = assignment or {}

    def term(name: str) -> str:
        if name in assignment:
            return assignment[name]
        if name in model.constants:
            return model.constants[name]
        raise ValueError(f"unbound term {name!r}")

    match formula:
        case Atom(pred, args):
            return tuple(term(a) for a in args) in model.extensions.get(pred, frozenset())
        case Not(sub):
            return not evaluate(sub, model, assignment)
        case And(l, r):
            return evaluate(l, model, assignment) and evaluate(r, model, assignment)
        case Or(l, r):
            return evaluate(l, model, assignment) or evaluate(r, model, assignment)
        case Implies(l, r):
            return (not evaluate(l, model, assignment)) or evaluate(r, model, assignment)
        case Iff(l, r):
            return evaluate(l, model, assignment) == evaluate(r, model, assignment)
        case ForAll(var, body):
            return all(
                evaluate(body, model, {**assignment, var: d}) for d in model.domain
            )
        case Exists(var, body):
            return any(
                evaluate(body, model, {**assignment, var: d}) for d in model.domain
            )
    raise TypeError(f"not a formula: {formula!r}")


def models_of_size(
    formulas: Iterable, size: int, extra_constants: Iterable[str] = ()
) -> Iterator[Model]:
    """Enumerate every interpretation over a domain of ``size`` elements.

    This is brute force, and deliberately so: it makes the *semantics* concrete
    (a model is a choice of extension for each predicate) and it makes the cost
    of that concreteness visible — the count is doubly exponential in arity.
    """
    formulas = list(formulas)
    signature: dict[str, int] = {}
    consts: set[str] = set(extra_constants)
    for f in formulas:
        signature.update(predicates(f))
        consts |= constants_in(f)

    domain = tuple(f"e{i}" for i in range(size))
    pred_names = sorted(signature)
    tuple_space = {p: list(itertools.product(domain, repeat=signature[p])) for p in pred_names}
    const_names = sorted(consts)

    ext_choices = [
        list(itertools.chain.from_iterable(
            itertools.combinations(tuple_space[p], r) for r in range(len(tuple_space[p]) + 1)
        ))
        for p in pred_names
    ]
    for exts in itertools.product(*ext_choices) if pred_names else [()]:
        extensions = {p: frozenset(e) for p, e in zip(pred_names, exts)}
        for values in itertools.product(domain, repeat=len(const_names)):
            yield Model(domain, extensions, dict(zip(const_names, values)))


def entails(premises: Iterable, conclusion, max_size: int = 3) -> tuple[bool, Model | None]:
    """Does ``premises`` entail ``conclusion`` over all domains up to ``max_size``?

    Returns ``(holds, countermodel)``. ``holds=True`` means *no countermodel of
    that size was found* — **not** that the entailment is valid in general. FOL
    validity is undecidable; this procedure always terminates, so it must be
    weaker. Exercise 2.3 makes the gap bite.
    """
    premises = list(premises)
    for size in range(1, max_size + 1):
        for model in models_of_size(premises + [conclusion], size):
            if all(evaluate(p, model) for p in premises) and not evaluate(conclusion, model):
                return False, model
    return True, None


def find_countermodel(premises: Iterable, conclusion, max_size: int = 3) -> Model | None:
    return entails(premises, conclusion, max_size)[1]


def is_valid(formula, max_size: int = 3) -> tuple[bool, Model | None]:
    return entails([], formula, max_size)


def is_satisfiable(formula, max_size: int = 3) -> tuple[bool, Model | None]:
    """Is there a model of size <= ``max_size`` satisfying the formula?"""
    for size in range(1, max_size + 1):
        for model in models_of_size([formula], size):
            if evaluate(formula, model):
                return True, model
    return False, None


# --------------------------------------------------------------------------- #
# Reasoning by resolution (over the ground fragment)
# --------------------------------------------------------------------------- #
def ground(formula, constants: list[str]):
    """Replace quantifiers by finite conjunctions/disjunctions over ``constants``.

    Sound and complete *for that finite domain*, which is what makes the
    resolution demo honest: it is propositional resolution on ground clauses,
    not FOL resolution with unification.
    """
    def subst(f, var, value):
        match f:
            case Atom(pred, args):
                return Atom(pred, tuple(value if a == var else a for a in args))
            case Not(sub):
                return Not(subst(sub, var, value))
            case And(l, r):
                return And(subst(l, var, value), subst(r, var, value))
            case Or(l, r):
                return Or(subst(l, var, value), subst(r, var, value))
            case Implies(l, r):
                return Implies(subst(l, var, value), subst(r, var, value))
            case Iff(l, r):
                return Iff(subst(l, var, value), subst(r, var, value))
            case ForAll(v, body):
                return f if v == var else ForAll(v, subst(body, var, value))
            case Exists(v, body):
                return f if v == var else Exists(v, subst(body, var, value))
        raise TypeError(f"not a formula: {f!r}")

    match formula:
        case Atom(_, _):
            return formula
        case Not(sub):
            return Not(ground(sub, constants))
        case And(l, r):
            return And(ground(l, constants), ground(r, constants))
        case Or(l, r):
            return Or(ground(l, constants), ground(r, constants))
        case Implies(l, r):
            return Implies(ground(l, constants), ground(r, constants))
        case Iff(l, r):
            return Iff(ground(l, constants), ground(r, constants))
        case ForAll(var, body):
            parts = [ground(subst(body, var, c), constants) for c in constants]
            return _fold(parts, And)
        case Exists(var, body):
            parts = [ground(subst(body, var, c), constants) for c in constants]
            return _fold(parts, Or)
    raise TypeError(f"not a formula: {formula!r}")


def _fold(parts: list, op):
    if not parts:
        raise ValueError("empty quantifier domain")
    result = parts[0]
    for part in parts[1:]:
        result = op(result, part)
    return result


def _nnf(formula):
    match formula:
        case Implies(l, r):
            return _nnf(Or(Not(l), r))
        case Iff(l, r):
            return _nnf(And(Implies(l, r), Implies(r, l)))
        case Not(Not(sub)):
            return _nnf(sub)
        case Not(And(l, r)):
            return _nnf(Or(Not(l), Not(r)))
        case Not(Or(l, r)):
            return _nnf(And(Not(l), Not(r)))
        case Not(Implies(l, r)):
            return _nnf(And(l, Not(r)))
        case Not(Iff(l, r)):
            return _nnf(Or(And(l, Not(r)), And(Not(l), r)))
        case And(l, r):
            return And(_nnf(l), _nnf(r))
        case Or(l, r):
            return Or(_nnf(l), _nnf(r))
        case Not(Atom(_, _)) | Atom(_, _):
            return formula
    raise TypeError(f"cannot convert to NNF (is it ground?): {formula!r}")


def _literal(formula) -> str:
    match formula:
        case Atom(pred, args):
            return f"{pred}({','.join(args)})" if args else pred
        case Not(Atom(pred, args)):
            return "~" + (f"{pred}({','.join(args)})" if args else pred)
    raise TypeError(f"not a literal: {formula!r}")


def to_cnf_clauses(formula) -> list[frozenset[str]]:
    """Ground formula -> a set of clauses, each a set of literal strings."""
    def distribute(f) -> list[frozenset[str]]:
        match f:
            case And(l, r):
                return distribute(l) + distribute(r)
            case Or(l, r):
                return [a | b for a in distribute(l) for b in distribute(r)]
            case _:
                return [frozenset({_literal(f)})]

    clauses = distribute(_nnf(formula))
    # drop tautologies (a clause containing both L and ~L)
    return [c for c in clauses if not any(("~" + lit) in c for lit in c if not lit.startswith("~"))]


def resolve(c1: frozenset[str], c2: frozenset[str]) -> list[frozenset[str]]:
    """All resolvents of two clauses."""
    out = []
    for lit in c1:
        complement = lit[1:] if lit.startswith("~") else "~" + lit
        if complement in c2:
            resolvent = (c1 - {lit}) | (c2 - {complement})
            if not any(("~" + l) in resolvent for l in resolvent if not l.startswith("~")):
                out.append(resolvent)
    return out


def resolution_refutation(clauses: list[frozenset[str]], max_steps: int = 500):
    """Try to derive the empty clause. Returns ``(refuted, steps, trace)``.

    The trace is the sequence of resolution steps — the *proof*, which is the
    artefact Chapter 2 is really about. A verdict with no proof is an assertion.
    """
    known = {frozenset(c) for c in clauses}
    trace: list[tuple[frozenset[str], frozenset[str], frozenset[str]]] = []
    steps = 0
    frontier = list(known)
    while steps < max_steps:
        new: set[frozenset[str]] = set()
        for a, b in itertools.combinations(frontier, 2):
            for resolvent in resolve(a, b):
                steps += 1
                if resolvent not in known:
                    trace.append((a, b, resolvent))
                    if not resolvent:
                        return True, steps, trace
                    new.add(resolvent)
                if steps >= max_steps:
                    return False, steps, trace
        if not new:
            return False, steps, trace
        known |= new
        frontier = list(known)
    return False, steps, trace


# --------------------------------------------------------------------------- #
# The three mistakes Chapter 2 exists to prevent
# --------------------------------------------------------------------------- #
#: Ids here are the *same vocabulary* the Chapter 2 rulebook and metric use
#: (``ch02_agentic``). Keeping one set of names means "the metric complained
#: about X" and "the instruction now mentions X" refer to the same X — the
#: property the whole GEPA loop depends on.
QUANTIFIER_PITFALLS = [
    {
        "id": "universal-uses-implication",
        "wrong": "forall x (Student(x) & Enrolled(x))",
        "right": "forall x (Student(x) -> Enrolled(x))",
        "why": "The conjunctive reading says *everything in the domain* is a student. "
               "Universal restriction is always material implication.",
    },
    {
        "id": "existential-uses-conjunction",
        "wrong": "exists x (Student(x) -> Enrolled(x))",
        "right": "exists x (Student(x) & Enrolled(x))",
        "why": "An existential with implication is satisfied by any non-student, so it "
               "asserts almost nothing. Existential restriction is always conjunction.",
    },
    {
        "id": "quantifier-order-matters",
        "wrong": "exists y forall x Teaches(x, y)",
        "right": "forall x exists y Teaches(x, y)",
        "why": "Swapping the quantifiers changes 'everyone teaches something' into "
               "'there is one thing everyone teaches'. The second entails the first, "
               "never the reverse.",
    },
    {
        "id": "negation-scope",
        "wrong": "~forall x (Plant(x) -> Animal(x))",
        "right": "forall x (Plant(x) -> ~Animal(x))",
        "why": "'No X is Y' negates the consequent inside the universal; negating the "
               "whole formula only says *not all* X are Y, which is far weaker.",
    },
]
