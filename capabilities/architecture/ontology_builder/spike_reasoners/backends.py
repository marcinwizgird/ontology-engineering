"""A multi-reasoner framework: capabilities, sessions, and honest answers.

Reference implementation for `ontology_builder.reasoning` (features OB.RSN.01–04
and OB.EXT.05). The design is lifted from the only one of the three reference
platforms that has a real pluggable-reasoner architecture — Protégé Desktop's
`org.protege.editor.owl.model.inference` package — with one addition it makes
only implicitly.

**What Protégé gets right and we copy.**

* `ProtegeOWLReasonerInfo` is a *factory plus configuration*, not a reasoner. The
  plugin contract returns an `OWLReasonerFactory`; the bound instance is a
  separate object with its own lifecycle. We split `ReasonerBackend` (cheap,
  singleton, describes itself) from `ReasonerSession` (expensive, bound to a
  graph, must be closed).
* `ReasonerStatus` has six states, including `OUT_OF_SYNC` and `INCONSISTENT` —
  the manager always knows whether the reasoner is stale relative to the
  ontology. Staleness is a first-class state, not a boolean.
* `ReasonerDiedException` and `OWLReasonerExceptionHandler` exist because
  reasoners genuinely crash, hang and run out of memory. A framework that
  assumes success is wrong.
* `BufferingMode getRecommendedBuffering()` — the reasoner *declares* how it
  wants changes fed to it. A capability declaration, not a caller assumption.
* `ReasonerPreferences` toggles 18 separate inference types, because computing
  all of them is expensive and not every reasoner supports every one.

**What Protégé leaves implicit and we make explicit.** Protégé assumes every
plugged-in reasoner is a sound and complete OWL 2 DL reasoner, so it never has
to say *which* semantics produced an answer. We cannot assume that: our cheapest
backend is OWL 2 RL, which is deliberately incomplete for DL. So every answer
carries the profile it was computed under and whether the ontology actually fell
inside that backend's completeness envelope. See :class:`Answer`.

That single field is what makes a multi-reasoner setup safe rather than
confusing: "no, `Foo` is not unsatisfiable" means something very different from
an RL reasoner than from HermiT, and the caller must be able to tell.
"""

from __future__ import annotations

import abc
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.term import Node

__all__ = [
    "Profile", "ReasonerCapabilities", "Availability", "Answer", "Justification",
    "ReasonerBackend", "ReasonerSession", "ReasonerError", "ReasonerUnavailable",
    "RDFSBackend", "OWLRLBackend", "SidecarBackend",
]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class Profile:
    """OWL 2 profiles, ordered by expressive strength for our purposes."""

    RDFS = "RDFS"
    RL = "RL"
    EL = "EL"
    QL = "QL"
    DL = "DL"
    FULL = "FULL"

    ORDER = (RDFS, RL, QL, EL, DL, FULL)

    @classmethod
    def stronger(cls, a: str, b: str) -> bool:
        return cls.ORDER.index(a) > cls.ORDER.index(b)


#: The operations a backend may support. Deliberately small — this is the
#: contract the rest of the platform codes against, so growing it is expensive.
OPERATIONS = frozenset({
    "consistency",     # is the ontology consistent?
    "satisfiability",  # which named classes are unsatisfiable?
    "classify",        # inferred subsumption hierarchy
    "realise",         # most specific types of individuals
    "entails",         # does this triple follow?
    "materialise",     # produce the entailed closure as a graph
    "explain",         # justifications for an entailment
})


class ReasonerError(RuntimeError):
    """A reasoner failed — crashed, timed out, or ran out of memory.

    Protégé's `ReasonerDiedException`. Never let this escape as a generic
    exception: the router needs to distinguish "this backend died" (try the
    next one) from "the answer is no".
    """


class ReasonerUnavailable(ReasonerError):
    """The backend cannot run here — missing runtime, missing sidecar, no licence."""


# --------------------------------------------------------------------------- #
# Declarations
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReasonerCapabilities:
    """What a backend can do, declared rather than discovered by failure."""

    id: str
    name: str
    #: The strongest profile for which this backend is sound **and complete**.
    complete_for: str
    #: Operations from :data:`OPERATIONS`.
    operations: frozenset[str]
    #: Can it accept incremental changes, or must a session be rebuilt?
    incremental: bool
    #: "polynomial" | "exponential" — drives timeout budgeting and routing.
    cost_class: str
    #: "in-process" | "sidecar"
    execution: str
    #: External runtimes needed, e.g. ("java",). Checked by :meth:`available`.
    requires: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        bad = self.operations - OPERATIONS
        if bad:
            raise ValueError(f"{self.id}: unknown operations {sorted(bad)}")
        if self.complete_for not in Profile.ORDER:
            raise ValueError(f"{self.id}: unknown profile {self.complete_for!r}")

    def supports(self, operation: str) -> bool:
        return operation in self.operations


@dataclass(frozen=True)
class Availability:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class Justification:
    """A minimal set of axioms entailing a conclusion."""

    axioms: tuple[tuple[Node, Node, Node], ...]
    backend: str


@dataclass(frozen=True)
class Answer:
    """A reasoner result that knows how much it is worth.

    ``complete`` is the load-bearing field. ``Answer(value=False,
    complete=False)`` means *this backend found no entailment, but the ontology
    uses constructs it is incomplete for* — which is not the same as "no".
    Never render an incomplete negative as a definite one.
    """

    value: Any
    backend: str
    profile: str
    complete: bool
    elapsed_ms: float
    caveat: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.value)

    @property
    def is_definite(self) -> bool:
        """True when the answer can be stated without qualification."""
        return self.complete or bool(self.value)

    def describe(self) -> str:
        base = f"{self.value!r} [{self.backend}, {self.profile}]"
        if self.complete:
            return base
        return f"{base} (incomplete: {self.caveat or 'ontology exceeds profile'})"


# --------------------------------------------------------------------------- #
# The two-level contract
# --------------------------------------------------------------------------- #
class ReasonerSession(abc.ABC):
    """A reasoner bound to one graph. Expensive to create; always close it.

    Mirrors an OWL API `OWLReasoner` instance. Sessions are the unit of caching
    in a sidecar: keyed by (project, revision), warmed once, queried many times.
    """

    def __init__(self, backend: "ReasonerBackend", graph: Graph,
                 completeness: tuple[bool, str]) -> None:
        self.backend = backend
        self.graph = graph
        self._complete, self._caveat = completeness
        self._closed = False

    # -- helpers used by subclasses ---------------------------------------- #
    def _answer(self, value: Any, started: float) -> Answer:
        return Answer(
            value=value,
            backend=self.backend.capabilities.id,
            profile=self.backend.capabilities.complete_for,
            complete=self._complete,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            caveat=None if self._complete else self._caveat,
        )

    def _require(self, operation: str) -> None:
        if self._closed:
            raise ReasonerError(f"{self.backend.capabilities.id}: session is closed")
        if not self.backend.capabilities.supports(operation):
            raise ReasonerError(
                f"{self.backend.capabilities.id} does not support {operation!r}; "
                f"it supports {sorted(self.backend.capabilities.operations)}")

    # -- the operations ----------------------------------------------------- #
    @abc.abstractmethod
    def materialise(self) -> Answer: ...

    def entails(self, s: Node, p: Node, o: Node) -> Answer:
        self._require("entails")
        started = time.perf_counter()
        closure: Graph = self.materialise().value
        return self._answer((s, p, o) in closure, started)

    def subclasses(self, cls: URIRef, direct: bool = False) -> Answer:
        self._require("classify")
        started = time.perf_counter()
        closure: Graph = self.materialise().value
        subs = {s for s in closure.subjects(RDFS.subClassOf, cls)
                if isinstance(s, URIRef) and s != cls}
        if direct:
            indirect = {x for sub in subs
                        for x in closure.subjects(RDFS.subClassOf, sub)
                        if x != sub}
            subs -= indirect
        return self._answer(subs, started)

    def unsatisfiable(self) -> Answer:
        self._require("satisfiability")
        started = time.perf_counter()
        closure: Graph = self.materialise().value
        unsat = {c for c in closure.subjects(RDFS.subClassOf, OWL.Nothing)
                 if isinstance(c, URIRef) and c != OWL.Nothing}
        return self._answer(unsat, started)

    def consistent(self) -> Answer:
        self._require("consistency")
        started = time.perf_counter()
        closure: Graph = self.materialise().value
        ok = (OWL.Thing, RDFS.subClassOf, OWL.Nothing) not in closure
        return self._answer(ok, started)

    def explain(self, s: Node, p: Node, o: Node) -> Answer:
        self._require("explain")
        raise ReasonerError(
            f"{self.backend.capabilities.id} declares 'explain' but does not "
            "implement it")

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "ReasonerSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class ReasonerBackend(abc.ABC):
    """A reasoner implementation. Cheap, stateless, describes itself.

    Mirrors Protégé's `ProtegeOWLReasonerInfo`: it is the *factory*, not the
    reasoner. Registered by entry point (`ontology_builder.reasoners`) so a new
    backend is an installable package, not a code change — see OB.EXT.01.
    """

    capabilities: ReasonerCapabilities

    def available(self) -> Availability:
        """Can this backend run in this deployment right now?

        Checked before routing, so a missing JVM degrades gracefully instead of
        raising from inside a request.
        """
        for req in self.capabilities.requires:
            if shutil.which(req) is None:
                return Availability(
                    False,
                    f"required runtime {req!r} is not on PATH")
        return Availability(True)

    def completeness_for(self, graph: Graph) -> tuple[bool, str]:
        """Is *graph* inside this backend's completeness envelope?

        Overridden by profile-aware backends. The default is optimistic only for
        DL-complete backends.
        """
        from profile_check import outside_profile  # local import: see module docs
        offending = outside_profile(graph, self.capabilities.complete_for)
        if not offending:
            return True, ""
        top = ", ".join(f"{k} x{v}" for k, v in sorted(
            offending.items(), key=lambda kv: -kv[1])[:4])
        total = sum(offending.values())
        return False, (f"{total} axioms outside OWL 2 "
                       f"{self.capabilities.complete_for}: {top}")

    @abc.abstractmethod
    def _session(self, graph: Graph, completeness: tuple[bool, str],
                 timeout_s: float) -> ReasonerSession: ...

    def session(self, graph: Graph, *, timeout_s: float = 60.0) -> ReasonerSession:
        avail = self.available()
        if not avail:
            raise ReasonerUnavailable(
                f"{self.capabilities.id}: {avail.reason}")
        return self._session(graph, self.completeness_for(graph), timeout_s)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} {self.capabilities.id}>"


# --------------------------------------------------------------------------- #
# Backend 1 — RDFS only. The weakest useful backend.
# --------------------------------------------------------------------------- #
class _RDFSSession(ReasonerSession):
    def __init__(self, backend: ReasonerBackend, graph: Graph,
                 completeness: tuple[bool, str]) -> None:
        super().__init__(backend, graph, completeness)
        self._closure: Optional[Graph] = None

    def materialise(self) -> Answer:
        self._require("materialise")
        started = time.perf_counter()
        if self._closure is None:
            import owlrl
            g = Graph()
            for t in self.graph:
                g.add(t)
            owlrl.RDFSClosure.RDFS_Semantics(g, False, False, False).closure()
            self._closure = g
        return self._answer(self._closure, started)


class RDFSBackend(ReasonerBackend):
    capabilities = ReasonerCapabilities(
        id="rdfs",
        name="RDFS entailment (owlrl)",
        complete_for=Profile.RDFS,
        operations=frozenset({"classify", "entails", "materialise"}),
        incremental=False,
        cost_class="polynomial",
        execution="in-process",
        notes="Subclass/subproperty/domain/range closure only. Cannot detect "
              "unsatisfiability or inconsistency — it has no notion of either, "
              "which is why those operations are absent rather than returning "
              "a misleading 'no'.",
    )

    def _session(self, graph: Graph, completeness: tuple[bool, str],
                 timeout_s: float) -> ReasonerSession:
        return _RDFSSession(self, graph, completeness)


# --------------------------------------------------------------------------- #
# Backend 2 — OWL 2 RL in process. The workhorse.
# --------------------------------------------------------------------------- #
class _OWLRLSession(ReasonerSession):
    def __init__(self, backend: ReasonerBackend, graph: Graph,
                 completeness: tuple[bool, str]) -> None:
        super().__init__(backend, graph, completeness)
        self._closure: Optional[Graph] = None

    def materialise(self) -> Answer:
        self._require("materialise")
        started = time.perf_counter()
        if self._closure is None:
            import owlrl
            g = Graph()
            for t in self.graph:
                g.add(t)
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
            self._closure = g
        return self._answer(self._closure, started)


class OWLRLBackend(ReasonerBackend):
    capabilities = ReasonerCapabilities(
        id="owlrl",
        name="OWL 2 RL (owlrl)",
        complete_for=Profile.RL,
        operations=frozenset({
            "classify", "entails", "materialise", "satisfiability", "consistency",
        }),
        incremental=False,
        cost_class="polynomial",
        execution="in-process",
        notes="Rule-based, forward-chaining, total materialisation. Sound for "
              "OWL 2 DL but INCOMPLETE: it will miss entailments that depend on "
              "min/exact cardinality, allValuesFrom in subclass position, or "
              "disjunctive reasoning. A negative answer from this backend is "
              "not a proof of non-entailment.",
    )

    def _session(self, graph: Graph, completeness: tuple[bool, str],
                 timeout_s: float) -> ReasonerSession:
        return _OWLRLSession(self, graph, completeness)


# --------------------------------------------------------------------------- #
# Backend 3 — the JVM sidecar. Declares itself; unavailable without a runtime.
# --------------------------------------------------------------------------- #
class _SidecarSession(ReasonerSession):
    """Placeholder body — the real one POSTs to the sidecar and caches by
    (project, revision). Present so the contract is exercised by tests even in
    a deployment with no JVM."""

    def materialise(self) -> Answer:  # pragma: no cover - needs a live sidecar
        raise ReasonerUnavailable(
            "sidecar session created without a reachable sidecar")


class SidecarBackend(ReasonerBackend):
    """HermiT / ELK behind the OWL API, over HTTP.

    Declared here so the framework is honest about what it *would* provide and
    so the router's degradation path is exercised in environments without a
    JVM — which is the current state of this workstation.
    """

    def __init__(self, reasoner: str = "hermit",
                 base_url: str = "http://127.0.0.1:8081") -> None:
        self.base_url = base_url
        el = reasoner == "elk"
        self.capabilities = ReasonerCapabilities(
            id=f"sidecar:{reasoner}",
            name=f"{'ELK' if el else 'HermiT'} via the OWL API sidecar",
            complete_for=Profile.EL if el else Profile.DL,
            operations=frozenset({
                "classify", "entails", "materialise", "satisfiability",
                "consistency", "realise",
            }) | (frozenset() if el else frozenset({"explain"})),
            incremental=True,
            cost_class="polynomial" if el else "exponential",
            execution="sidecar",
            requires=("java",),
            notes=("ELK: EL profile only, always terminates, orders of magnitude "
                   "faster — the fallback when HermiT times out."
                   if el else
                   "Full OWL 2 DL with justifications via OWL Explanation. The "
                   "only path to T.RI.4. Tableau reasoning can blow up: enforce "
                   "a wall-clock budget and degrade to ELK."),
        )

    def _session(self, graph: Graph, completeness: tuple[bool, str],
                 timeout_s: float) -> ReasonerSession:
        return _SidecarSession(self, graph, completeness)
