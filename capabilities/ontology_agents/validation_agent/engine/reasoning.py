"""ReasoningEngine, ``rl`` backend: owlrl OWL 2 RL closure plus probe individuals.

* **Consistency (RSN-01).** The closure of the asserted graph is searched for clashes:
  a member of ``owl:Nothing``, an individual in two disjoint or complementary classes,
  ``sameAs`` together with ``differentFrom``, and owlrl's own inconsistency messages
  (lexical-form errors are left to SYN-03).
* **Satisfiability (RSN-02).** RL closure alone says nothing about a class with no
  members. For each named class ``C`` a fresh probe individual ``urn:ova:probe:<hash(C)>``
  is asserted to be a ``C`` in a copy of the graph; all probes go into one closure
  (probes share no property links, so they do not interact) and a clash on a probe makes
  its class unsatisfiable. Probe IRIs are seeded by the class IRI, so runs are
  deterministic.
* **Root and derived.** S1a uses the structural rule: an unsatisfiable class is
  *derived* when one of its inferred named superclasses is itself unsatisfiable and not
  equivalent to it, otherwise it is a *root*. S1c replaces this with justifications.
* **Completeness (RSN-08).** Outside OWL 2 RL a clean result does not establish
  satisfiability, and the result says so.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from itertools import combinations

import owlrl
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from . import vocab as V

ERROR_MESSAGE = URIRef("http://www.daml.org/2002/03/agents/agent-ont#ErrorMessage")
ERROR_TEXT = URIRef("http://www.daml.org/2002/03/agents/agent-ont#error")
PROBE_NS = "urn:ova:probe:"


@dataclass
class Clash:
    individual: str
    reason: str
    classes: list[str] = field(default_factory=list)


@dataclass
class ReasoningResult:
    backend: str
    consistent: bool
    clashes: list[Clash]
    unsatisfiable: list[dict]
    inferred_equivalences: list[list[str]]
    complete: bool
    incompleteness: str | None
    probes: int
    millis: int

    def to_dict(self) -> dict:
        return asdict(self)


def probe_iri(cls) -> URIRef:
    return URIRef(PROBE_NS + hashlib.sha1(str(cls).encode("utf-8")).hexdigest()[:16])


def closure(g: Graph) -> Graph:
    c = Graph()
    for t in g:
        c.add(t)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(c)
    return c


def _disjoint_pairs(c: Graph) -> set[frozenset]:
    pairs = set()
    for a, b in c.subject_objects(OWL.disjointWith):
        if a != b:
            pairs.add(frozenset((a, b)))
    for a, b in c.subject_objects(OWL.complementOf):
        pairs.add(frozenset((a, b)))
    for node in c.subjects(RDF.type, OWL.AllDisjointClasses):
        members = V.rdf_list(c, c.value(node, OWL.members))
        pairs |= {frozenset(p) for p in combinations(members, 2)}
    for owner, head in c.subject_objects(OWL.disjointUnionOf):
        pairs |= {frozenset(p) for p in combinations(V.rdf_list(c, head), 2)}
    return pairs


def _clash(c: Graph, x, pairs: set[frozenset]) -> Clash | None:
    types = set(c.objects(x, RDF.type))
    if OWL.Nothing in types:
        return Clash(str(x), "member of owl:Nothing", [str(OWL.Nothing)])
    hits = sorted((sorted(map(str, p)) for p in pairs if p <= types))
    if hits:
        a, b = hits[0]
        return Clash(str(x), f"member of disjoint classes {V.local_name(a)} and {V.local_name(b)}", [a, b])
    same = set(c.objects(x, OWL.sameAs))
    different = set(c.objects(x, OWL.differentFrom)) | set(c.subjects(OWL.differentFrom, x))
    if x in different:
        return Clash(str(x), "owl:differentFrom itself", [])
    both = sorted(map(str, same & different))
    if both:
        return Clash(str(x), f"owl:sameAs and owl:differentFrom {V.local_name(both[0])}", [])
    return None


def _owlrl_errors(c: Graph) -> list[str]:
    msgs = []
    for e in c.subjects(RDF.type, ERROR_MESSAGE):
        for text in c.objects(e, ERROR_TEXT):
            if "Lexical value" not in str(text):
                msgs.append(str(text))
    return sorted(msgs)


def reason(g: Graph, rl_in_profile: bool = True, classes: list | None = None) -> ReasoningResult:
    t0 = time.perf_counter()
    base = closure(g)
    pairs = _disjoint_pairs(base)
    subjects = sorted({s for s, o in base.subject_objects(RDF.type)
                       if isinstance(s, URIRef) and o not in V.META_TYPES}, key=str)
    clashes = [cl for x in subjects if (cl := _clash(base, x, pairs))]
    for msg in _owlrl_errors(base):
        if not any(cl.individual in msg for cl in clashes):
            clashes.append(Clash("", msg))
    consistent = not clashes
    unsat: list[dict] = []
    equivalences: list[list[str]] = []
    probes = 0
    if consistent:
        classes = classes if classes is not None else [
            c for c in V.declared_classes(g) if not V.is_builtin(c)]
        probe_of = {c: probe_iri(c) for c in classes}
        probes = len(probe_of)
        pg = Graph()
        for t in g:
            pg.add(t)
        for c, p in probe_of.items():
            pg.add((p, RDF.type, c))
        pc = closure(pg)
        pairs = _disjoint_pairs(pc)
        errors = _owlrl_errors(pc)
        status = {}
        for c, p in probe_of.items():
            cl = _clash(pc, p, pairs)
            if cl is None:
                text = next((m for m in errors if str(p) in m), None)
                cl = Clash(str(p), text) if text else None
            status[c] = cl
        supers = {c: {t for t in pc.objects(p, RDF.type) if isinstance(t, URIRef)
                      and t in probe_of and t != c} for c, p in probe_of.items()}
        bad = {c for c, cl in status.items() if cl is not None}
        for c in sorted(bad, key=str):
            via = sorted(str(d) for d in supers[c] if d in bad and c not in supers[d])
            unsat.append({"class": str(c), "root": not via, "via": via,
                          "reason": status[c].reason, "clash_classes": status[c].classes})
        seen = set()
        for a in sorted(set(probe_of) - bad, key=str):
            for b in sorted(supers[a], key=str):
                if b not in bad and a in supers.get(b, ()) and frozenset((a, b)) not in seen:
                    seen.add(frozenset((a, b)))
                    asserted = (a, OWL.equivalentClass, b) in g or (b, OWL.equivalentClass, a) in g
                    if not asserted:
                        equivalences.append(sorted((str(a), str(b))))
    complete = rl_in_profile
    return ReasoningResult(
        backend="rl", consistent=consistent, clashes=clashes, unsatisfiable=unsat,
        inferred_equivalences=sorted(equivalences), complete=complete,
        incompleteness=None if complete else
        "the ontology is outside OWL 2 RL and only the RL reasoner ran",
        probes=probes, millis=int((time.perf_counter() - t0) * 1000))
