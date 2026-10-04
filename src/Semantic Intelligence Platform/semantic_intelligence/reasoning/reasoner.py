"""Reasoner management — Protégé's ``OWLReasonerManagerImpl``, over Python backends.

What is ported from Protégé:

* **Pluggable backends** (``ProtegeOWLReasonerInfo`` plugins → :class:`Backend`),
  each declaring the OWL *profile* it is complete for. Protégé ships only the
  "None" reasoner and loads HermiT/ELK/Pellet as plugins; here the bundled
  backends are pure Python — RDFS and OWL 2 RL via ``owlrl`` — and a DL backend
  (owlready2 + HermiT) registers itself only if a JVM is present.
* **ReasonerStatus is derived, never stored** (``getReasonerStatus``): no reasoner,
  not initialised, initialising, initialised, inconsistent, out of sync. "Out of
  sync" is computed from the content revision the last classification saw versus
  the current one — the buffering-reasoner rule of ``OWLWorkspace``.
* **Precompute / classify** → materialise ``main ∪ imports`` into the project's
  ``inferred`` graph (only the triples *not* asserted), plus the inferred class
  hierarchy (``InferredOWLClassHierarchyProvider``), with unsatisfiable classes
  under ``owl:Nothing``.
* **Inconsistency** → status ``INCONSISTENT`` and the reasoner's messages; the
  explanation service (``explanation.py``) justifies it.

What is deliberately *different* (QR-AIT-04, "profile honesty"): every result
carries the backend and profile that produced it. An OWL RL closure is sound but
incomplete for OWL 2 DL; the platform says so rather than presenting RL answers
as DL answers.

Unsatisfiable classes under RL: a class ``C`` is tested by asserting a fresh
*canary* individual of type ``C`` and looking for an inconsistency that mentions
it (``cax-dw``, ``cls-nothing2``, ``cls-com``, ``prp-irp`` …). All canaries are
injected in one closure, candidates are then confirmed one by one, so the cost is
one closure plus one per unsatisfiable class.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Protocol

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ..owl.hierarchy import ClassHierarchy

ERRNS_ERROR = URIRef("http://www.daml.org/2002/03/agents/agent-ont#ErrorMessage")


class ReasonerStatus(str, Enum):
    NO_REASONER_FACTORY_CHOSEN = "No reasoner set"
    REASONER_NOT_INITIALIZED = "Reasoner not started"
    INITIALIZATION_IN_PROGRESS = "Reasoner initialisation in progress"
    INITIALIZED = "Reasoner active"
    INCONSISTENT = "Reasoner active but the ontology is inconsistent"
    OUT_OF_SYNC = "Reasoner state out of sync with active ontology"


class Backend(Protocol):
    name: str
    profile: str

    def available(self) -> bool: ...
    def closure(self, graph: Graph) -> tuple[Graph, list[str]]: ...


def _copy(g: Graph) -> Graph:
    out = Graph()
    for t in g:
        out.add(t)
    for p, n in g.namespaces():
        out.bind(p, n, override=False)
    return out


def _owlrl_errors(g: Graph) -> list[str]:
    import owlrl
    from owlrl.Namespaces import ERRNS
    msgs = []
    for m in list(g.subjects(RDF.type, ERRNS.ErrorMessage)):
        msgs.extend(str(o) for o in g.objects(m, ERRNS.error))
        for t in list(g.triples((m, None, None))):
            g.remove(t)
    return msgs


@dataclass
class OwlRlBackend:
    name: str = "owlrl"
    profile: str = "OWL2-RL"

    def available(self) -> bool:
        try:
            import owlrl  # noqa: F401
            return True
        except ImportError:
            return False

    def closure(self, graph: Graph) -> tuple[Graph, list[str]]:
        import owlrl
        g = _copy(graph)
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
        return g, _owlrl_errors(g)


@dataclass
class RdfsBackend:
    name: str = "rdfs"
    profile: str = "RDFS"

    def available(self) -> bool:
        return OwlRlBackend().available()

    def closure(self, graph: Graph) -> tuple[Graph, list[str]]:
        import owlrl
        g = _copy(graph)
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics, axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
        return g, _owlrl_errors(g)


@dataclass
class HermitBackend:
    """OWL 2 DL via owlready2's bundled HermiT. Needs a JVM; absent → unavailable."""

    name: str = "hermit"
    profile: str = "OWL2-DL"

    def available(self) -> bool:
        try:
            import owlready2  # noqa: F401
        except ImportError:
            return False
        return shutil.which("java") is not None

    def closure(self, graph: Graph) -> tuple[Graph, list[str]]:  # pragma: no cover - needs Java
        import os
        import tempfile

        import owlready2
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "o.owl")
            graph.serialize(path, format="xml")
            world = owlready2.World()
            onto = world.get_ontology("file://" + path.replace("\\", "/")).load()
            errors: list[str] = []
            try:
                with onto:
                    owlready2.sync_reasoner_hermit(world, infer_property_values=True)
            except owlready2.OwlReadyInconsistentOntologyError as e:
                errors.append(f"inconsistent: {e}")
            out = world.as_rdflib_graph()
            g = _copy(graph)
            for t in out:
                g.add(t)
            return g, errors


@dataclass
class Classification:
    backend: str
    profile: str
    revision: int
    seconds: float
    consistent: bool
    messages: list[str]
    inferred: Graph                    # entailed triples NOT asserted
    unsatisfiable: list[URIRef]
    hierarchy: ClassHierarchy

    def provenance(self) -> dict:
        return {"backend": self.backend, "profile": self.profile, "revision": self.revision,
                "complete_for": self.profile, "seconds": round(self.seconds, 3)}


@dataclass
class ReasonerManager:
    """One reasoner per project (Protégé: one per active ontology)."""

    backends: dict[str, Backend] = field(default_factory=lambda: {
        b.name: b for b in (OwlRlBackend(), RdfsBackend(), HermitBackend())})
    current: str | None = "owlrl"
    revision: Callable[[], int] = lambda: 0
    last: Classification | None = None
    _in_progress: bool = False

    # -- status (derived) -------------------------------------------------- #
    @property
    def status(self) -> ReasonerStatus:
        if self._in_progress:
            return ReasonerStatus.INITIALIZATION_IN_PROGRESS
        if self.current is None:
            return ReasonerStatus.NO_REASONER_FACTORY_CHOSEN
        if self.last is None or self.last.backend != self.current:
            return ReasonerStatus.REASONER_NOT_INITIALIZED
        if not self.last.consistent:
            return ReasonerStatus.INCONSISTENT
        if self.last.revision != self.revision():
            return ReasonerStatus.OUT_OF_SYNC
        return ReasonerStatus.INITIALIZED

    def select(self, name: str | None) -> None:
        if name is not None and name not in self.backends:
            raise KeyError(f"unknown reasoner {name!r}; known {sorted(self.backends)}")
        if name is not None and not self.backends[name].available():
            raise RuntimeError(f"reasoner {name!r} is not available in this environment")
        self.current = name

    def available(self) -> dict[str, str]:
        return {n: b.profile for n, b in self.backends.items() if b.available()}

    # -- classify ------------------------------------------------------------ #
    def classify(self, asserted: Graph, *, check_satisfiability: bool = True) -> Classification:
        if self.current is None:
            raise RuntimeError("no reasoner selected")
        backend = self.backends[self.current]
        self._in_progress = True
        t0 = time.perf_counter()
        try:
            closed, errors = backend.closure(asserted)
            inferred = Graph()
            for t in closed:
                if t not in asserted and not _trivial(t):
                    inferred.add(t)
            unsat: list[URIRef] = []
            if check_satisfiability and not errors:
                unsat = self._unsatisfiable(asserted, backend)
            full = Graph()
            for t in closed:
                full.add(t)
            for c in unsat:
                full.add((c, RDFS.subClassOf, OWL.Nothing))
            hierarchy = InferredClassHierarchy(full, unsat)
            self.last = Classification(backend.name, backend.profile, self.revision(),
                                       time.perf_counter() - t0, not errors, errors,
                                       inferred, unsat, hierarchy)
            return self.last
        finally:
            self._in_progress = False

    def _unsatisfiable(self, asserted: Graph, backend: Backend) -> list[URIRef]:
        classes = sorted({c for c in asserted.subjects(RDF.type, OWL.Class)
                          if isinstance(c, URIRef)} - {OWL.Nothing, OWL.Thing})
        if not classes:
            return []

        def canary(c: URIRef) -> URIRef:
            return URIRef(f"urn:sip:canary:{abs(hash(str(c)))}")

        probe = _copy(asserted)
        for c in classes:
            probe.add((canary(c), RDF.type, c))
        _, errors = backend.closure(probe)
        if not errors:
            return []
        text = " ".join(errors)
        candidates = [c for c in classes if str(canary(c)) in text] or classes
        out = []
        for c in candidates:
            single = _copy(asserted)
            single.add((canary(c), RDF.type, c))
            if backend.closure(single)[1]:
                out.append(c)
        return out

    def is_entailed(self, triple, asserted: Graph) -> bool:
        if self.last is None or self.last.revision != self.revision():
            self.classify(asserted, check_satisfiability=False)
        return triple in asserted or triple in self.last.inferred


def _trivial(t) -> bool:
    """Drop entailments nobody wants to see: reflexive subclass/property, owl:Thing
    supertypes, sameAs-self — Protégé's inferred views hide the same ones."""
    s, p, o = t
    if p in (RDFS.subClassOf, OWL.equivalentClass, RDFS.subPropertyOf,
             OWL.equivalentProperty, OWL.sameAs) and s == o:
        return True
    if (p == RDFS.subClassOf and o == OWL.Thing) or (p == RDF.type and o == OWL.Thing):
        return True
    if isinstance(s, BNode) or isinstance(o, BNode):
        return True
    return p == RDF.type and o == RDFS.Resource


class InferredClassHierarchy(ClassHierarchy):
    """Inferred tree: direct parents only (transitive reduction of the closure),
    unsatisfiable classes as children of ``owl:Nothing``."""

    def __init__(self, closed: Graph, unsatisfiable: Iterable[URIRef] = ()) -> None:
        self.unsatisfiable = set(unsatisfiable)
        super().__init__(closed, use_equivalent_conjuncts=False)

    def rebuild(self) -> None:
        super().rebuild()
        # transitive reduction: drop parent p of c if another parent q has p as ancestor
        for c in list(self.classes):
            ps = set(self._parents.get(c, set())) - {c}
            if c in self.unsatisfiable:
                ps = {OWL.Nothing}
            else:
                ps -= self.unsatisfiable
                ps -= {OWL.Nothing}
                reduced = {p for p in ps
                           if not any(q != p and p in self._anc(q) and q not in
                                      self._equiv.get(p, set()) for q in ps)}
                ps = reduced or {OWL.Thing}
            self._parents[c] = ps
        self._children.clear()
        for c in self.classes:
            for p in self._parents[c]:
                self._children.setdefault(p, set()).add(c)

    def _anc(self, c):
        return self._closure(c, self._parents)

    def unsatisfiable_classes(self) -> list[URIRef]:
        return sorted(self.unsatisfiable)
