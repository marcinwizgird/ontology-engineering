"""Chapter 3 toolkit — description logics, with a real tableau reasoner.

Chapter 2 ended at a wall: full first-order logic is undecidable, so no
terminating procedure can be complete for it. Description logics are the
response — *fragments of FOL chosen so that reasoning terminates*. This module
makes that response concrete:

* **concept syntax** — an AST for ALC and its common extensions;
* **expressivity analysis** — :func:`dl_name` reads a knowledge base and reports
  which DL you are actually in, which is the skill §3.2 is built around;
* **a tableau reasoner** — :func:`satisfiable` decides ALC concept
  satisfiability with respect to a TBox, with **blocking** so that cyclic
  axioms such as ``A ⊑ ∃r.A`` terminate instead of looping forever.

The reasoner is the point. A student who has written a tableau understands why
`∃r.A ⊓ ∀r.¬A` is unsatisfiable in a way that no amount of reading delivers —
and understands where the cost comes from, because the disjunction rule branches
in front of them.

Scope: the tableau covers **ALC** (plus TBox internalisation). Number
restrictions, inverses and transitivity are *analysed* by :func:`dl_name` but not
reasoned over; the notebooks say so wherever it matters.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "Top", "Bottom", "Concept", "Atomic", "Not", "And", "Or", "Exists", "ForAll",
    "AtLeast", "AtMost", "Inverse", "TBox", "Axiom",
    "nnf", "to_string", "constructors_used", "dl_name", "DL_LETTERS",
    "satisfiable", "subsumes", "equivalent_concepts", "classify",
    "TableauResult",
]


# --------------------------------------------------------------------------- #
# Concept language
# --------------------------------------------------------------------------- #
class Concept:
    """Base class so ``isinstance`` checks read well."""

    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)


@dataclass(frozen=True)
class _Top(Concept):
    def __repr__(self):
        return "Top"


@dataclass(frozen=True)
class _Bottom(Concept):
    def __repr__(self):
        return "Bottom"


Top = _Top()
Bottom = _Bottom()


@dataclass(frozen=True)
class Atomic(Concept):
    name: str


@dataclass(frozen=True)
class Not(Concept):
    sub: Concept


@dataclass(frozen=True)
class And(Concept):
    left: Concept
    right: Concept


@dataclass(frozen=True)
class Or(Concept):
    left: Concept
    right: Concept


@dataclass(frozen=True)
class Inverse:
    """The inverse of an atomic role, written ``r-``."""

    role: str

    def __str__(self):
        return f"{self.role}-"


@dataclass(frozen=True)
class Exists(Concept):
    role: object          # str | Inverse
    filler: Concept


@dataclass(frozen=True)
class ForAll(Concept):
    role: object
    filler: Concept


@dataclass(frozen=True)
class AtLeast(Concept):
    n: int
    role: object
    filler: Concept = Top      # Top means an *unqualified* restriction


@dataclass(frozen=True)
class AtMost(Concept):
    n: int
    role: object
    filler: Concept = Top


@dataclass(frozen=True)
class Axiom:
    """``left ⊑ right``, or ``left ≡ right`` when ``equivalence`` is set."""

    left: Concept
    right: Concept
    equivalence: bool = False

    def __str__(self):
        symbol = "==" if self.equivalence else "<="
        return f"{to_string(self.left)} {symbol} {to_string(self.right)}"


@dataclass
class TBox:
    """A set of concept axioms, plus the role box facts §3.2 needs."""

    axioms: list[Axiom] = field(default_factory=list)
    transitive_roles: set[str] = field(default_factory=set)
    role_hierarchy: list[tuple[str, str]] = field(default_factory=list)
    functional_roles: set[str] = field(default_factory=set)
    nominals: set[str] = field(default_factory=set)

    def add(self, left: Concept, right: Concept, equivalence: bool = False) -> "TBox":
        self.axioms.append(Axiom(left, right, equivalence))
        return self

    def concepts(self) -> list[Concept]:
        """Every concept mentioned, for signature analysis."""
        out = []
        for ax in self.axioms:
            out += [ax.left, ax.right]
        return out

    def internalised(self) -> list[Concept]:
        """Each axiom as a concept that must hold at *every* node.

        ``C ⊑ D`` becomes ``¬C ⊔ D``; an equivalence becomes both directions.
        This is TBox internalisation — the standard way a tableau accounts for
        general axioms, and the reason a TBox makes reasoning markedly harder.
        """
        out = []
        for ax in self.axioms:
            out.append(nnf(Or(Not(ax.left), ax.right)))
            if ax.equivalence:
                out.append(nnf(Or(Not(ax.right), ax.left)))
        return out


# --------------------------------------------------------------------------- #
# Rendering and normalisation
# --------------------------------------------------------------------------- #
def to_string(c) -> str:
    match c:
        case _Top():
            return "Top"
        case _Bottom():
            return "Bottom"
        case Atomic(name):
            return name
        case Not(sub):
            return f"not {to_string(sub)}"
        case And(l, r):
            return f"({to_string(l)} and {to_string(r)})"
        case Or(l, r):
            return f"({to_string(l)} or {to_string(r)})"
        case Exists(role, filler):
            return f"exists {role}.{to_string(filler)}"
        case ForAll(role, filler):
            return f"forall {role}.{to_string(filler)}"
        case AtLeast(n, role, filler):
            return f">={n} {role}.{to_string(filler)}"
        case AtMost(n, role, filler):
            return f"<={n} {role}.{to_string(filler)}"
    raise TypeError(f"not a concept: {c!r}")


def nnf(c: Concept) -> Concept:
    """Negation normal form — negation pushed down to atomic concepts."""
    match c:
        case Not(_Top()):
            return Bottom
        case Not(_Bottom()):
            return Top
        case Not(Not(sub)):
            return nnf(sub)
        case Not(And(l, r)):
            return Or(nnf(Not(l)), nnf(Not(r)))
        case Not(Or(l, r)):
            return And(nnf(Not(l)), nnf(Not(r)))
        case Not(Exists(role, filler)):
            return ForAll(role, nnf(Not(filler)))
        case Not(ForAll(role, filler)):
            return Exists(role, nnf(Not(filler)))
        case And(l, r):
            return And(nnf(l), nnf(r))
        case Or(l, r):
            return Or(nnf(l), nnf(r))
        case Exists(role, filler):
            return Exists(role, nnf(filler))
        case ForAll(role, filler):
            return ForAll(role, nnf(filler))
        case AtLeast(n, role, filler):
            return AtLeast(n, role, nnf(filler))
        case AtMost(n, role, filler):
            return AtMost(n, role, nnf(filler))
        case Not(AtLeast(n, role, filler)):
            return AtMost(n - 1, role, nnf(filler))
        case Not(AtMost(n, role, filler)):
            return AtLeast(n + 1, role, nnf(filler))
        case _:
            return c


# --------------------------------------------------------------------------- #
# Expressivity: which DL is this? (§3.2)
# --------------------------------------------------------------------------- #
#: The naming letters, with what each one buys.
DL_LETTERS = {
    "AL": "attributive language: atomic negation, conjunction, universal restriction, "
          "unqualified existential",
    "C": "full concept negation (complement) -- turns AL into ALC",
    "S": "shorthand for ALC extended with transitive roles",
    "H": "role hierarchy (r sub-role of s)",
    "O": "nominals (concepts built from named individuals)",
    "I": "inverse roles",
    "N": "unqualified number restrictions (>=n r)",
    "Q": "qualified number restrictions (>=n r.C)",
    "F": "functional roles",
    "R": "complex role inclusions (role chains)",
}


def constructors_used(tbox: TBox) -> set[str]:
    """Which constructors appear anywhere in the knowledge base."""
    used: set[str] = set()

    def walk(c):
        match c:
            case Not(sub):
                # Negation of a non-atomic concept is full complement.
                used.add("negation-atomic" if isinstance(sub, Atomic) else "negation-full")
                walk(sub)
            case And(l, r):
                used.add("conjunction"); walk(l); walk(r)
            case Or(l, r):
                used.add("disjunction"); walk(l); walk(r)
            case Exists(role, filler):
                used.add("existential")
                if isinstance(role, Inverse):
                    used.add("inverse")
                if filler is not Top:
                    used.add("qualified-existential")
                walk(filler)
            case ForAll(role, filler):
                used.add("universal")
                if isinstance(role, Inverse):
                    used.add("inverse")
                walk(filler)
            case AtLeast(_, role, filler) | AtMost(_, role, filler):
                used.add("qualified-number" if filler is not Top else "number")
                if isinstance(role, Inverse):
                    used.add("inverse")
                walk(filler)

    for c in tbox.concepts():
        walk(c)
    if tbox.transitive_roles:
        used.add("transitive")
    if tbox.role_hierarchy:
        used.add("role-hierarchy")
    if tbox.functional_roles:
        used.add("functional")
    if tbox.nominals:
        used.add("nominals")
    return used


def dl_name(tbox: TBox) -> str:
    """Name the description logic a knowledge base actually needs.

    The rule §3.2 teaches: start from ALC (or **S** when roles are transitive),
    then append a letter for each extra constructor. Getting this right is how
    you predict the reasoning cost you have just signed up for.
    """
    used = constructors_used(tbox)
    base = "S" if "transitive" in used else "ALC"
    name = base
    if "role-hierarchy" in used:
        name += "H"
    if "nominals" in used:
        name += "O"
    if "inverse" in used:
        name += "I"
    if "qualified-number" in used:
        name += "Q"
    elif "number" in used:
        name += "N"
    elif "functional" in used:
        name += "F"
    return name


# --------------------------------------------------------------------------- #
# Tableau reasoner for ALC (with TBox internalisation and blocking)
# --------------------------------------------------------------------------- #
@dataclass
class TableauResult:
    satisfiable: bool
    steps: int
    max_depth: int
    branches: int
    trace: list[str] = field(default_factory=list)

    def summary(self) -> str:
        verdict = "SATISFIABLE" if self.satisfiable else "UNSATISFIABLE"
        return (f"{verdict} after {self.steps} rule applications, "
                f"{self.branches} branch points, max depth {self.max_depth}")


def _clash(label: frozenset) -> tuple[Concept, Concept] | None:
    if Bottom in label:
        return Bottom, Bottom
    for c in label:
        if isinstance(c, Not) and c.sub in label:
            return c.sub, c
    return None


def satisfiable(concept: Concept, tbox: TBox | None = None,
                max_steps: int = 20000, trace: bool = False) -> TableauResult:
    """Is ``concept`` satisfiable with respect to ``tbox``?

    A tableau builds a candidate model. It succeeds when a branch saturates with
    no contradiction; it fails when *every* branch clashes.

    **Blocking** is what makes it terminate: if a node's label is a subset of an
    ancestor's, the ancestor's model can be reused, so we stop expanding. Without
    it, ``A ⊑ ∃r.A`` would generate successors forever.
    """
    tbox = tbox or TBox()
    axioms = tuple(tbox.internalised())
    stats = {"steps": 0, "depth": 0, "branches": 0}
    log: list[str] = []

    def expand(label: frozenset, ancestors: tuple[frozenset, ...], depth: int) -> bool:
        stats["depth"] = max(stats["depth"], depth)
        if stats["steps"] > max_steps:
            raise RuntimeError("tableau exceeded its step budget")

        label = frozenset(label) | set(axioms)

        # --- saturate the propositional rules -----------------------------
        changed = True
        while changed:
            changed = False
            stats["steps"] += 1
            if _clash(label):
                if trace:
                    log.append(f"{'  ' * depth}CLASH in {_render(label)}")
                return False
            for c in list(label):
                if isinstance(c, And) and not {c.left, c.right} <= label:
                    label = label | {c.left, c.right}
                    changed = True
                    if trace:
                        log.append(f"{'  ' * depth}and-rule: {to_string(c)}")
            if changed:
                continue
            # --- disjunction: the branching rule ---------------------------
            for c in list(label):
                if isinstance(c, Or) and not (c.left in label or c.right in label):
                    stats["branches"] += 1
                    if trace:
                        log.append(f"{'  ' * depth}or-rule branches on {to_string(c)}")
                    return (expand(label | {c.left}, ancestors, depth)
                            or expand(label | {c.right}, ancestors, depth))

        if _clash(label):
            return False

        # --- blocking ------------------------------------------------------
        if any(label <= a for a in ancestors):
            if trace:
                log.append(f"{'  ' * depth}BLOCKED (label repeats an ancestor)")
            return True

        # --- existential rule: build successors ----------------------------
        for c in sorted((x for x in label if isinstance(x, Exists)), key=to_string):
            successor = {c.filler} | {
                d.filler for d in label if isinstance(d, ForAll) and d.role == c.role
            }
            if trace:
                log.append(f"{'  ' * depth}exists-rule: new {c.role}-successor "
                           f"{_render(frozenset(successor))}")
            stats["steps"] += 1
            if not expand(frozenset(successor), ancestors + (label,), depth + 1):
                return False
        return True

    ok = expand(frozenset({nnf(concept)}), (), 0)
    return TableauResult(ok, stats["steps"], stats["depth"], stats["branches"], log)


def _render(label: Iterable) -> str:
    return "{" + ", ".join(sorted(to_string(c) for c in label)) + "}"


def subsumes(sub: Concept, sup: Concept, tbox: TBox | None = None) -> bool:
    """Does ``tbox`` entail ``sub ⊑ sup``?

    The standard reduction: subsumption holds exactly when ``sub ⊓ ¬sup`` is
    unsatisfiable. One reasoning service implemented in terms of another — the
    move §3.3 is built on.
    """
    return not satisfiable(And(sub, Not(sup)), tbox).satisfiable


def equivalent_concepts(a: Concept, b: Concept, tbox: TBox | None = None) -> bool:
    return subsumes(a, b, tbox) and subsumes(b, a, tbox)


def classify(names: Iterable[str], tbox: TBox) -> list[tuple[str, str]]:
    """Compute the inferred subsumption hierarchy over named concepts.

    This is *classification*, the reasoning service ontology tools are really
    selling. Only strict, non-trivial subsumptions are returned.
    """
    concepts = {n: Atomic(n) for n in names}
    out = []
    for a, b in itertools.permutations(sorted(concepts), 2):
        if subsumes(concepts[a], concepts[b], tbox):
            # keep it informative: drop it if it follows from an asserted axiom verbatim
            out.append((a, b))
    return out


# --------------------------------------------------------------------------- #
# Worked knowledge bases used by the notebooks
# --------------------------------------------------------------------------- #
def wildlife_tbox() -> TBox:
    """The AWO fragment from Chapter 1/4, expressed in DL."""
    A = Atomic
    tbox = TBox()
    tbox.add(A("Herbivore"), And(A("Animal"), ForAll("eats", A("Plant"))))
    tbox.add(A("Carnivore"), And(A("Animal"), ForAll("eats", A("Animal"))))
    tbox.add(A("Giraffe"), And(A("Herbivore"), Exists("eats", A("Leaf"))))
    tbox.add(A("Lion"), And(A("Carnivore"), Exists("eats", A("Herbivore"))))
    tbox.add(A("Leaf"), A("Plant"))
    tbox.add(A("Plant"), Not(A("Animal")))
    return tbox
