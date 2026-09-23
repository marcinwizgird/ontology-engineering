"""Chapter 10 toolkit — time, vagueness, and granularity, each made computable.

Chapter 10 collects three kinds of imperfection that a crisp ontology cannot
express, and the three different formalisms that handle them. They are usually
taught as three unrelated topics; the thing that unites them is a single trade —
**expressivity is never free** — and this module makes each of them concrete
enough to price.

* **§10.1 time.** Allen's interval algebra: thirteen relations between two
  intervals, a composition table, and a consistency check. The composition table
  here is *derived by enumeration* rather than copied from the literature, so it
  can be checked rather than trusted.
* **§10.2 vagueness.** Fuzzy membership, t-norms, and a degree of subsumption:
  "tall" has no boundary, and pretending it does is a modelling error.
* **§10.2 granularity.** Rough sets: when your attributes cannot tell two objects
  apart, some sets are only describable by an upper and a lower approximation.

The chapter's agent task is choosing between them, and its MDP prices the search
that a constraint solver performs.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

__all__ = [
    "ALLEN_RELATIONS", "ALLEN_NAMES", "relation_between", "compose",
    "composition_table", "Network", "path_consistent",
    "trapezoid", "triangular", "FUZZY_SETS", "membership",
    "fuzzy_and", "fuzzy_or", "subsumption_degree", "alpha_cut",
    "InformationSystem", "SAMPLE_SYSTEM", "REQUIREMENTS",
]


# --------------------------------------------------------------------------- #
# §10.1  Allen's interval algebra
# --------------------------------------------------------------------------- #
#: The thirteen jointly exhaustive, pairwise disjoint relations between two
#: intervals. ``eq`` is its own inverse; the rest come in pairs.
ALLEN_RELATIONS = (
    "b", "bi", "m", "mi", "o", "oi", "s", "si", "d", "di", "f", "fi", "eq",
)

ALLEN_NAMES = {
    "b": "before", "bi": "after",
    "m": "meets", "mi": "met-by",
    "o": "overlaps", "oi": "overlapped-by",
    "s": "starts", "si": "started-by",
    "d": "during", "di": "contains",
    "f": "finishes", "fi": "finished-by",
    "eq": "equals",
}


def relation_between(a: tuple[int, int], b: tuple[int, int]) -> str:
    """The single Allen relation holding between two concrete intervals.

    Intervals are half-open ``(start, end)`` with ``start < end``. Exactly one
    of the thirteen relations holds between any two — that is what "jointly
    exhaustive and pairwise disjoint" means, and :func:`_check_jepd` verifies it.
    """
    a1, a2 = a
    b1, b2 = b
    if a2 < b1:
        return "b"
    if a2 == b1:
        return "m"
    if b2 < a1:
        return "bi"
    if b2 == a1:
        return "mi"
    if a1 == b1 and a2 == b2:
        return "eq"
    if a1 == b1:
        return "s" if a2 < b2 else "si"
    if a2 == b2:
        return "f" if a1 > b1 else "fi"
    if a1 < b1 and b2 < a2:
        return "di"
    if b1 < a1 and a2 < b2:
        return "d"
    if a1 < b1 < a2 < b2:
        return "o"
    return "oi"


def _intervals(limit: int = 6):
    return [(s, e) for s in range(limit) for e in range(s + 1, limit + 1)]


_COMPOSITION: dict[tuple[str, str], frozenset] | None = None


def composition_table(limit: int = 5) -> dict:
    """Derive the composition table by enumerating concrete intervals.

    ``compose(r1, r2)`` is the set of relations that can hold between A and C
    given ``r1(A, B)`` and ``r2(B, C)``. Rather than copying Allen's published
    13x13 table, this *computes* it: try every triple of small intervals and
    record which combinations actually occur. Slower, and checkable — which for
    a table with 169 entries is the better trade.
    """
    global _COMPOSITION
    if _COMPOSITION is not None:
        return _COMPOSITION

    table: dict = {}
    intervals = _intervals(limit)
    for a, b, c in itertools.product(intervals, repeat=3):
        key = (relation_between(a, b), relation_between(b, c))
        table.setdefault(key, set()).add(relation_between(a, c))
    _COMPOSITION = {k: frozenset(v) for k, v in table.items()}
    return _COMPOSITION


def compose(first: str, second: str) -> frozenset:
    """Which relations may hold between A and C, given ``first(A,B)``, ``second(B,C)``."""
    return composition_table().get((first, second), frozenset(ALLEN_RELATIONS))


def compose_sets(left: frozenset, right: frozenset) -> frozenset:
    """Composition lifted to sets of possible relations."""
    out: set = set()
    for a in left:
        for b in right:
            out |= compose(a, b)
    return frozenset(out)


# --------------------------------------------------------------------------- #
# Temporal constraint networks
# --------------------------------------------------------------------------- #
@dataclass
class Network:
    """A constraint network over named intervals.

    ``labels[(i, j)]`` is the set of relations still considered possible between
    ``i`` and ``j``. Reasoning means *narrowing* those sets; an empty set means
    the network is inconsistent.
    """

    nodes: tuple
    labels: dict

    @classmethod
    def complete(cls, nodes, constraints=None):
        labels = {}
        for i, j in itertools.combinations(nodes, 2):
            labels[(i, j)] = frozenset(ALLEN_RELATIONS)
        for (i, j), relations in (constraints or {}).items():
            labels[cls._key(i, j)] = frozenset(
                relations if cls._ordered(i, j) else [inverse(r) for r in relations])
        return cls(tuple(nodes), labels)

    @staticmethod
    def _ordered(i, j) -> bool:
        return i < j

    @staticmethod
    def _key(i, j):
        return (i, j) if i < j else (j, i)

    def get(self, i, j) -> frozenset:
        key = self._key(i, j)
        label = self.labels[key]
        return label if (i, j) == key else frozenset(inverse(r) for r in label)

    def set(self, i, j, relations: frozenset) -> None:
        key = self._key(i, j)
        self.labels[key] = (relations if (i, j) == key
                            else frozenset(inverse(r) for r in relations))

    def inconsistent(self) -> bool:
        return any(not label for label in self.labels.values())

    def summary(self) -> list[dict]:
        return [{"pair": f"{i}-{j}", "possible": len(label),
                 "relations": " ".join(sorted(label)) if len(label) <= 4 else "..."}
                for (i, j), label in sorted(self.labels.items())]


_INVERSE = {
    "b": "bi", "bi": "b", "m": "mi", "mi": "m", "o": "oi", "oi": "o",
    "s": "si", "si": "s", "d": "di", "di": "d", "f": "fi", "fi": "f", "eq": "eq",
}


def inverse(relation: str) -> str:
    return _INVERSE[relation]


def path_consistent(network: Network, max_rounds: int = 20) -> dict:
    """Narrow every pair by composing through every third interval.

    Path consistency is **sound but incomplete** for the full algebra: it can
    prove inconsistency but a path-consistent network is not guaranteed to be
    satisfiable. Saying so is part of the lesson — this is the same
    expressivity/decidability bargain as Chapters 2 and 3, in a different guise.
    """
    rounds = 0
    changed = True
    while changed and rounds < max_rounds:
        changed = False
        rounds += 1
        for i, j, k in itertools.permutations(network.nodes, 3):
            current = network.get(i, k)
            implied = compose_sets(network.get(i, j), network.get(j, k))
            narrowed = current & implied
            if narrowed != current:
                network.set(i, k, narrowed)
                changed = True
                if not narrowed:
                    return {"consistent": False, "rounds": rounds,
                            "empty_pair": f"{i}-{k}"}
    return {"consistent": not network.inconsistent(), "rounds": rounds,
            "empty_pair": None}


# --------------------------------------------------------------------------- #
# §10.2  Fuzzy sets
# --------------------------------------------------------------------------- #
def trapezoid(a: float, b: float, c: float, d: float):
    """A trapezoidal membership function: 0 below a, 1 on [b, c], 0 above d."""
    def membership_fn(x: float) -> float:
        if x <= a or x >= d:
            return 0.0
        if b <= x <= c:
            return 1.0
        if x < b:
            return (x - a) / (b - a)
        return (d - x) / (d - c)
    return membership_fn


def triangular(a: float, peak: float, c: float):
    return trapezoid(a, peak, peak, c)


#: Vague predicates over adult height in centimetres. There is no height at
#: which "tall" switches on; insisting on one is the modelling error §10.2 is
#: about.
FUZZY_SETS = {
    "short": trapezoid(0, 0, 155, 168),
    "average": trapezoid(158, 168, 178, 188),
    "tall": trapezoid(175, 190, 250, 250),
}


def membership(set_name: str, value: float) -> float:
    return round(FUZZY_SETS[set_name](value), 4)


def fuzzy_and(x: float, y: float, norm: str = "min") -> float:
    """A t-norm. ``min`` is Goedel; ``product`` is the other common choice."""
    return round(min(x, y) if norm == "min" else x * y, 4)


def fuzzy_or(x: float, y: float, norm: str = "min") -> float:
    return round(max(x, y) if norm == "min" else x + y - x * y, 4)


def alpha_cut(set_name: str, alpha: float, values) -> list:
    """The crisp set of values whose membership is at least ``alpha``.

    An alpha-cut is how a fuzzy concept is turned back into a crisp one — and
    choosing alpha is exactly the arbitrary decision fuzzification was meant to
    avoid, so it should be made explicitly rather than by accident.
    """
    return [v for v in values if FUZZY_SETS[set_name](v) >= alpha]


def subsumption_degree(sub: str, sup: str, values) -> float:
    """Degree to which one fuzzy concept is subsumed by another.

    Uses the Goedel implication and takes the infimum over the domain, which is
    the standard fuzzy reading of "every A is a B": the *worst* case decides.
    """
    degrees = []
    for value in values:
        a = FUZZY_SETS[sub](value)
        b = FUZZY_SETS[sup](value)
        degrees.append(1.0 if a <= b else b)
    return round(min(degrees), 4) if degrees else 1.0


# --------------------------------------------------------------------------- #
# §10.2  Rough sets
# --------------------------------------------------------------------------- #
@dataclass
class InformationSystem:
    """Objects described by attributes — the setting for rough set theory.

    If two objects agree on every attribute you record, no amount of reasoning
    will separate them. Rough sets take that seriously: a target set gets a
    **lower** approximation (certainly in) and an **upper** one (possibly in),
    and the gap between them is your ignorance made explicit.
    """

    objects: dict          # name -> {attribute: value}

    def attributes(self) -> list:
        return sorted({a for values in self.objects.values() for a in values})

    def indiscernibility(self, attributes=None) -> list:
        """Equivalence classes of objects that the chosen attributes cannot separate."""
        attributes = list(attributes) if attributes else self.attributes()
        buckets: dict = {}
        for name, values in self.objects.items():
            key = tuple(values.get(a) for a in attributes)
            buckets.setdefault(key, []).append(name)
        return [sorted(group) for _, group in sorted(buckets.items(), key=lambda kv: str(kv[0]))]

    def lower_approximation(self, target, attributes=None) -> list:
        target = set(target)
        return sorted(o for group in self.indiscernibility(attributes)
                      if set(group) <= target for o in group)

    def upper_approximation(self, target, attributes=None) -> list:
        target = set(target)
        return sorted(o for group in self.indiscernibility(attributes)
                      if set(group) & target for o in group)

    def boundary(self, target, attributes=None) -> list:
        lower = set(self.lower_approximation(target, attributes))
        return sorted(set(self.upper_approximation(target, attributes)) - lower)

    def accuracy(self, target, attributes=None) -> float:
        """|lower| / |upper| — 1.0 when the set is exactly describable."""
        lower = self.lower_approximation(target, attributes)
        upper = self.upper_approximation(target, attributes)
        return round(len(lower) / len(upper), 4) if upper else 1.0


#: Patients described by two coarse attributes. Note p3 and p4 are
#: indiscernible: identical on every recorded attribute, different outcomes.
SAMPLE_SYSTEM = InformationSystem({
    "p1": {"fever": "high", "cough": "yes"},
    "p2": {"fever": "high", "cough": "yes"},
    "p3": {"fever": "low", "cough": "no"},
    "p4": {"fever": "low", "cough": "no"},
    "p5": {"fever": "high", "cough": "no"},
    "p6": {"fever": "normal", "cough": "yes"},
})


# --------------------------------------------------------------------------- #
# Requirements the agent must classify
# --------------------------------------------------------------------------- #
#: Each requirement is imperfect in exactly one way, and each way needs a
#: different formalism. Getting this wrong is not a stylistic error: a crisp
#: threshold on a vague predicate produces confident nonsense at the boundary.
REQUIREMENTS = [
    ("meeting-before-lunch", "The meeting must finish before lunch begins.", "temporal"),
    ("overlapping-shifts", "The two shifts overlap in the afternoon.", "temporal"),
    ("tall-patient", "Flag patients who are tall.", "fuzzy"),
    ("warm-room", "Alert when the room is warm.", "fuzzy"),
    ("same-symptoms", "Two patients with identical recorded symptoms had different "
                      "outcomes; classify the risk group.", "rough"),
    ("coarse-attributes", "The available attributes cannot distinguish some cases from "
                          "each other.", "rough"),
    ("patient-id", "Every patient has exactly one hospital number.", "crisp"),
    ("ward-capacity", "A ward holds at most twenty beds.", "crisp"),
    ("treatment-during", "The treatment happens during the admission.", "temporal"),
    ("elderly-patient", "Prioritise elderly patients.", "fuzzy"),
    ("indiscernible-records", "Records that agree on every field must be treated as one "
                              "granule.", "rough"),
    ("bed-number", "Each bed has a unique integer identifier.", "crisp"),
]
