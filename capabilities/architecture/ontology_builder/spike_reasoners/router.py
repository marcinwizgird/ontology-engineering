"""Routing, degradation and differential testing across several reasoners.

Three pieces, in increasing order of how easy they are to get wrong:

1. :class:`ReasonerRouter` — pick a backend for an (operation, graph) pair from
   a declared policy, skipping backends that are unavailable or that do not
   support the operation, and recording *why* each was skipped.
2. Degradation — when the chosen backend dies or times out, fall to the next and
   say so in the answer. Silent degradation is how a platform ends up asserting
   RL results as if they were DL results.
3. :func:`differential` — run the same query against every available backend and
   report disagreements. This is the part that makes a multi-reasoner setup
   trustworthy rather than merely configurable: a disagreement is either a bug
   in a backend or an incompleteness someone forgot to declare.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from rdflib import Graph
from rdflib.term import Node

from backends import (
    Answer,
    Availability,
    Profile,
    ReasonerBackend,
    ReasonerError,
    ReasonerSession,
    ReasonerUnavailable,
)

__all__ = ["RoutingPolicy", "RoutingTrace", "ReasonerRouter", "differential",
           "Disagreement", "DEFAULT_POLICY"]


@dataclass(frozen=True)
class RoutingPolicy:
    """Preference order per operation, most-preferred first.

    Deliberately *declared* rather than computed. A rule like "always pick the
    most complete available backend" sounds right and is wrong: for
    `materialise` over a large graph you want the cheap polynomial backend even
    though a DL reasoner is available, and for `explain` you want the DL one
    even though it is expensive. The trade-off differs per operation, so the
    policy is per operation.
    """

    order: dict[str, tuple[str, ...]]
    #: Wall-clock budget per operation, seconds.
    budget_s: dict[str, float] = field(default_factory=dict)

    def preference(self, operation: str) -> tuple[str, ...]:
        return self.order.get(operation, ())

    def budget(self, operation: str) -> float:
        return self.budget_s.get(operation, 60.0)


#: Sensible defaults for this platform. `materialise` prefers the cheap backend
#: because it runs over whole projects; `explain` and `satisfiability` prefer the
#: DL backend because an incomplete answer there is close to worthless.
DEFAULT_POLICY = RoutingPolicy(
    order={
        "materialise":    ("owlrl", "sidecar:elk", "sidecar:hermit", "rdfs"),
        "classify":       ("owlrl", "sidecar:elk", "sidecar:hermit", "rdfs"),
        "entails":        ("owlrl", "sidecar:hermit", "sidecar:elk", "rdfs"),
        "consistency":    ("sidecar:hermit", "sidecar:elk", "owlrl"),
        "satisfiability": ("sidecar:hermit", "sidecar:elk", "owlrl"),
        "realise":        ("sidecar:hermit", "sidecar:elk"),
        "explain":        ("sidecar:hermit",),
    },
    budget_s={
        "materialise": 300.0,
        "consistency": 120.0,
        "satisfiability": 120.0,
        "explain": 30.0,
        "entails": 15.0,
    },
)


@dataclass
class RoutingTrace:
    """Why the router chose what it chose. Attach to logs and to agent output."""

    operation: str
    chosen: str | None = None
    skipped: list[tuple[str, str]] = field(default_factory=list)
    degraded_from: list[tuple[str, str]] = field(default_factory=list)

    def explain(self) -> str:
        parts = [f"{self.operation}: chose {self.chosen or 'nothing'}"]
        for bid, why in self.skipped:
            parts.append(f"skipped {bid} ({why})")
        for bid, why in self.degraded_from:
            parts.append(f"degraded from {bid} ({why})")
        return "; ".join(parts)


class ReasonerRouter:
    """Chooses a backend per operation and degrades explicitly on failure."""

    def __init__(self, backends: Sequence[ReasonerBackend],
                 policy: RoutingPolicy = DEFAULT_POLICY) -> None:
        self.backends = {b.capabilities.id: b for b in backends}
        self.policy = policy

    # -- introspection ------------------------------------------------------ #
    def availability(self) -> dict[str, Availability]:
        return {bid: b.available() for bid, b in self.backends.items()}

    def candidates(self, operation: str) -> tuple[list[ReasonerBackend], RoutingTrace]:
        """Ordered, filtered candidate list plus the trace of what was dropped."""
        trace = RoutingTrace(operation=operation)
        out: list[ReasonerBackend] = []
        pref = self.policy.preference(operation)
        ordered = [self.backends[b] for b in pref if b in self.backends]
        # Anything registered but unmentioned by the policy goes last.
        ordered += [b for bid, b in self.backends.items() if bid not in pref]

        for b in ordered:
            caps = b.capabilities
            if not caps.supports(operation):
                trace.skipped.append((caps.id, f"does not support {operation}"))
                continue
            avail = b.available()
            if not avail:
                trace.skipped.append((caps.id, avail.reason))
                continue
            out.append(b)
        return out, trace

    # -- the call ----------------------------------------------------------- #
    def run(self, operation: str, graph: Graph,
            call: Callable[[ReasonerSession], Answer],
            ) -> tuple[Answer, RoutingTrace]:
        """Execute *call* on the best available backend, degrading on failure."""
        candidates, trace = self.candidates(operation)
        if not candidates:
            raise ReasonerUnavailable(
                f"no available backend supports {operation!r}. "
                f"{trace.explain()}")

        budget = self.policy.budget(operation)
        last: Exception | None = None
        for backend in candidates:
            try:
                with backend.session(graph, timeout_s=budget) as session:
                    answer = call(session)
                trace.chosen = backend.capabilities.id
                return answer, trace
            except ReasonerError as exc:
                trace.degraded_from.append((backend.capabilities.id, str(exc)))
                last = exc
        raise ReasonerError(
            f"every candidate for {operation!r} failed. {trace.explain()}") from last

    # -- convenience wrappers ---------------------------------------------- #
    def entails(self, graph: Graph, s: Node, p: Node, o: Node):
        return self.run("entails", graph, lambda ses: ses.entails(s, p, o))

    def unsatisfiable(self, graph: Graph):
        return self.run("satisfiability", graph, lambda ses: ses.unsatisfiable())

    def subclasses(self, graph: Graph, cls, direct: bool = False):
        return self.run("classify", graph, lambda ses: ses.subclasses(cls, direct))

    def materialise(self, graph: Graph):
        return self.run("materialise", graph, lambda ses: ses.materialise())


# --------------------------------------------------------------------------- #
# Differential testing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Disagreement:
    """Two backends returned different answers to the same question."""

    question: str
    answers: dict[str, Any]
    #: Backends whose answer is definite (complete for this graph).
    definite: tuple[str, ...]

    @property
    def is_expected(self) -> bool:
        """True when the disagreement is explained by declared incompleteness.

        A weaker backend saying "no" where a stronger one says "yes" is the
        system working. Two *complete* backends disagreeing is a bug.
        """
        return len(self.definite) <= 1

    def describe(self) -> str:
        rows = ", ".join(f"{b}={v!r}" for b, v in sorted(self.answers.items()))
        tag = "expected (incompleteness)" if self.is_expected else "BUG: complete backends disagree"
        return f"{self.question}: {rows}  [{tag}]"


def differential(backends: Sequence[ReasonerBackend], graph: Graph,
                 questions: Iterable[tuple[str, Callable[[ReasonerSession], Answer]]],
                 ) -> list[Disagreement]:
    """Run every question against every available backend and diff the results.

    Run this in CI over a fixture corpus. It is the only mechanism that catches
    a backend that is quietly wrong, as opposed to quietly incomplete.
    """
    usable = [b for b in backends if b.available()]
    found: list[Disagreement] = []

    for label, call in questions:
        answers: dict[str, Any] = {}
        definite: list[str] = []
        for b in usable:
            bid = b.capabilities.id
            if not b.capabilities.supports(_operation_of(label)):
                continue
            try:
                with b.session(graph) as session:
                    ans = call(session)
            except ReasonerError as exc:
                answers[bid] = f"<error: {exc}>"
                continue
            answers[bid] = _comparable(ans.value)
            if ans.complete:
                definite.append(bid)
        distinct = {repr(v) for v in answers.values()}
        if len(distinct) > 1:
            found.append(Disagreement(label, answers, tuple(definite)))
    return found


def _operation_of(label: str) -> str:
    """`"entails: A rdfs:subClassOf C"` -> `"entails"`."""
    return label.split(":", 1)[0].strip()


def _comparable(value: Any) -> Any:
    if isinstance(value, Graph):
        return f"<graph {len(value)} triples>"
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(str(v) for v in value))
    return value
