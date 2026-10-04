"""Justifications — the Explanation Workbench algorithm, in Python.

Protégé's repository contains only the orchestration (``ExplanationManager``,
the ``ExplanationService`` plugin point). The algorithm lives in the external
``owlexplanation`` library and is *black-box*: it needs nothing from the reasoner
except "does this axiom set entail η?". That is exactly what makes it portable to
a pure-Python stack:

1. **Module extraction** — a justification lies inside the syntactic-locality
   module of ``sig(η)``. Here a conservative *signature-reachability* module is
   used (an axiom joins when it shares a symbol with the growing signature),
   which is a superset of the ⊥-module: sound, only larger.
2. **Expand–contract** for one justification: grow a subset until it entails η,
   then shrink — sliding-window pruning with halving windows, then a final linear
   pass that guarantees minimality.
3. **Reiter's hitting-set tree** for all justifications, with justification reuse,
   early path termination and closed-path subsumption.

Entailment oracle: the axiom subset is serialised to RDF, a *canary* individual
of type ``C`` is added for ``SubClassOf(C, D)``, the configured reasoner computes
the closure and the oracle looks for ``canary rdf:type D`` (or an inconsistency,
from which everything follows). Calls are memoised by ``frozenset``.

Every explanation states the profile of the oracle that produced it. An OWL RL
justification is a justification *with respect to the RL closure*: if the RL
reasoner cannot see an entailment, no justification is found, and the result says
``complete_for = OWL2-RL`` rather than "not entailed".
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ..owl.model import Axiom, axiom_signature, axiom_triples, axioms
from .reasoner import Backend, OwlRlBackend

CANARY = URIRef("urn:sip:canary:explanation")


@dataclass
class Entailment:
    kind: str                    # "subclass" | "type" | "inconsistent" | "unsatisfiable"
    sub: URIRef | None = None
    sup: URIRef | None = None

    def signature(self) -> set[URIRef]:
        return {x for x in (self.sub, self.sup) if isinstance(x, URIRef)} - {OWL.Thing,
                                                                           OWL.Nothing}

    def __str__(self) -> str:
        if self.kind == "subclass":
            return f"SubClassOf({self.sub}, {self.sup})"
        if self.kind == "type":
            return f"ClassAssertion({self.sup}, {self.sub})"
        if self.kind == "unsatisfiable":
            return f"SubClassOf({self.sub}, owl:Nothing)"
        return "Inconsistent"


@dataclass
class Oracle:
    """``entailed(S)`` with memoisation."""

    eta: Entailment
    background: list[tuple]           # declaration triples, always present
    backend: Backend = field(default_factory=OwlRlBackend)
    calls: int = 0
    _memo: dict[frozenset, bool] = field(default_factory=dict)

    def __call__(self, subset: Iterable[Axiom]) -> bool:
        key = frozenset(subset)
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        self.calls += 1
        g = Graph()
        for t in self.background:
            g.add(t)
        for ax in key:
            for t in axiom_triples(ax):
                g.add(t)
        e = self.eta
        if e.kind in ("subclass", "unsatisfiable"):
            g.add((CANARY, RDF.type, e.sub))
        closed, errors = self.backend.closure(g)
        if errors:
            ok = True                   # ex falso: every entailment holds
        elif e.kind == "subclass":
            ok = (CANARY, RDF.type, e.sup) in closed
        elif e.kind == "type":
            ok = (e.sub, RDF.type, e.sup) in closed
        else:                           # inconsistent / unsatisfiable need an error
            ok = False
        self._memo[key] = ok
        return ok


def module(all_axioms: list[Axiom], seed: set[URIRef]) -> list[Axiom]:
    """Signature-reachability module (a superset of the ⊥-locality module)."""
    if not seed:
        return list(all_axioms)
    sig, out, changed = set(seed), [], True
    remaining = list(all_axioms)
    while changed:
        changed = False
        keep = []
        for ax in remaining:
            s = axiom_signature(ax)
            if s & sig:
                out.append(ax)
                sig |= s
                changed = True
            else:
                keep.append(ax)
        remaining = keep
    return out


def single_justification(O: list[Axiom], entailed: Callable[[Iterable[Axiom]], bool],
                         seed: set[URIRef]) -> frozenset[Axiom] | None:
    """Expand–contract."""
    if not entailed(O):
        return None
    # expansion: breadth-first over signature overlap, growing batches
    S: list[Axiom] = []
    sig = set(seed)
    pool = list(O)
    while not entailed(S):
        frontier = [a for a in pool if axiom_signature(a) & sig] or pool
        if not frontier:
            S = list(O)
            break
        k = max(1, len(S) // 4)
        batch, pool = frontier[:k], [a for a in pool if a not in frontier[:k]]
        S.extend(batch)
        for a in batch:
            sig |= axiom_signature(a)
    # contraction: sliding window, halving
    w = min(10, len(S))
    while w > 1:
        i = 0
        while i < len(S):
            cand = S[:i] + S[i + w:]
            if entailed(cand):
                S = cand
            else:
                i += w
        w //= 2
    # final linear pass — minimality
    for a in list(S):
        T = [x for x in S if x != a]
        if entailed(T):
            S = T
    return frozenset(S)


@dataclass
class ExplanationResult:
    entailment: str
    justifications: list[list[Axiom]]
    complete: bool
    profile: str
    oracle_calls: int

    def as_dict(self) -> dict:
        return {"entailment": self.entailment, "complete": self.complete,
                "profile": self.profile, "oracle_calls": self.oracle_calls,
                "justifications": [[str(a) for a in j] for j in self.justifications]}


def all_justifications(O: list[Axiom], entailed, seed: set[URIRef], limit: int = 10
                       ) -> tuple[list[frozenset[Axiom]], bool]:
    """Reiter's hitting-set tree (BFS ⇒ shortest hitting sets first)."""
    J0 = single_justification(O, entailed, seed)
    if J0 is None:
        return [], True
    justs = [J0]
    closed: list[frozenset] = []
    explored: set[frozenset] = set()
    queue = deque([(frozenset(), J0)])
    while queue:
        if len(justs) >= limit:
            return justs, False
        path, J = queue.popleft()
        for ax in sorted(J, key=str):
            new_path = path | {ax}
            if new_path in explored:
                continue
            explored.add(new_path)
            if any(cp <= new_path for cp in closed):
                continue                                     # early path termination
            reuse = next((Jk for Jk in justs if not (Jk & new_path)), None)
            if reuse is not None:
                queue.append((new_path, reuse))              # justification reuse
                continue
            O2 = [a for a in O if a not in new_path]
            Jn = single_justification(O2, entailed, seed)
            if Jn is None:
                closed.append(new_path)                      # a hitting set
                continue
            justs.append(Jn)
            queue.append((new_path, Jn))
    return justs, True


def explain(graph: Graph, eta: Entailment, *, backend: Backend | None = None,
            limit: int = 10) -> ExplanationResult:
    """Justify *eta* over the logical axioms of *graph*."""
    backend = backend or OwlRlBackend()
    logical = [a for a in axioms(graph, include_annotations=False, include_declarations=False)]
    background = [t for t in graph.triples((None, RDF.type, None))
                  if isinstance(t[0], URIRef) and t[2] in (
                      OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                      OWL.AnnotationProperty, OWL.NamedIndividual)]
    if eta.kind == "unsatisfiable":
        eta_o = Entailment("unsatisfiable", eta.sub)
        oracle = _UnsatOracle(eta_o, background, backend)
    elif eta.kind == "inconsistent":
        oracle = _UnsatOracle(eta, background, backend)
    else:
        oracle = Oracle(eta, background, backend)
    seed = eta.signature()
    O = module(logical, seed)
    justs, complete = all_justifications(O, oracle, seed, limit=limit)
    return ExplanationResult(str(eta), [sorted(j, key=str) for j in justs], complete,
                             backend.profile, oracle.calls)


class _UnsatOracle(Oracle):
    """Unsatisfiability / inconsistency: entailed iff the closure reports an error."""

    def __call__(self, subset):
        key = frozenset(subset)
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        self.calls += 1
        g = Graph()
        for t in self.background:
            g.add(t)
        for ax in key:
            for t in axiom_triples(ax):
                g.add(t)
        if self.eta.kind == "unsatisfiable":
            g.add((CANARY, RDF.type, self.eta.sub))
        _, errors = self.backend.closure(g)
        self._memo[key] = bool(errors)
        return self._memo[key]
