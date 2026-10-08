"""Competency questions as executable tests, and the release gate.

Neither Protégé nor VocBench has this; it is the platform's answer to "how do we
know the ontology does what it was built for?" (Grüninger & Fox; Keet ch. 5).

A :class:`CompetencyQuestion` holds the natural-language question, a SPARQL
formulation, and an *expectation* — one of ``non-empty``, ``empty``,
``count>=N``, ``contains:<IRI>`` or ``ask:true|false``. CQs are stored as RDF in
the project's ``cq`` graph (``sip:CompetencyQuestion``) so they are versioned with
the ontology. The release gate (FR-QA-02) requires: the ontology is consistent
under the selected profile, no ``blocker`` finding, and every CQ passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from ..core.namespaces import SIP


@dataclass
class CompetencyQuestion:
    id: str
    question: str
    sparql: str
    expectation: str = "non-empty"
    stage: str = "scope"
    source: str | None = None

    @property
    def iri(self) -> URIRef:
        return URIRef(f"urn:sip:cq:{self.id}")

    def triples(self):
        s = self.iri
        yield (s, RDF.type, SIP.CompetencyQuestion)
        yield (s, RDFS.label, Literal(self.question, lang="en"))
        yield (s, SIP.sparql, Literal(self.sparql))
        yield (s, SIP.expectation, Literal(self.expectation))
        if self.source:
            yield (s, SIP.derivedFrom, Literal(self.source))

    @classmethod
    def from_graph(cls, g: Graph) -> list["CompetencyQuestion"]:
        out = []
        for s in g.subjects(RDF.type, SIP.CompetencyQuestion):
            out.append(cls(str(s).rsplit(":", 1)[-1], str(g.value(s, RDFS.label)),
                           str(g.value(s, SIP.sparql)), str(g.value(s, SIP.expectation)
                                                            or "non-empty")))
        return sorted(out, key=lambda c: c.id)


@dataclass
class CqResult:
    id: str
    passed: bool
    detail: str
    rows: int = 0


def run_cq(cq: CompetencyQuestion, g: Graph) -> CqResult:
    try:
        res = g.query(cq.sparql)
    except Exception as exc:  # noqa: BLE001 - a malformed CQ is a failing CQ
        return CqResult(cq.id, False, f"query error: {exc}")
    exp = cq.expectation.strip()
    if res.type == "ASK":
        want = exp.split(":", 1)[1].strip().lower() == "true" if exp.startswith("ask:") else True
        return CqResult(cq.id, bool(res.askAnswer) == want, f"ASK -> {res.askAnswer}")
    rows = list(res)
    n = len(rows)
    if exp == "non-empty":
        ok = n > 0
    elif exp == "empty":
        ok = n == 0
    elif m := re.fullmatch(r"count>=(\d+)", exp):
        ok = n >= int(m.group(1))
    elif exp.startswith("contains:"):
        target = exp.split(":", 1)[1].strip()
        ok = any(str(v) == target for r in rows for v in r)
    else:
        return CqResult(cq.id, False, f"unknown expectation {exp!r}", n)
    return CqResult(cq.id, ok, f"{n} row(s); expected {exp}", n)


@dataclass
class GateReport:
    passed: bool
    consistent: bool | None
    profile: str | None
    blockers: int
    cq_results: list[CqResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "consistent": self.consistent, "profile": self.profile,
                "blockers": self.blockers, "reasons": self.reasons,
                "cq": [r.__dict__ for r in self.cq_results]}


def release_gate(findings, classification, cqs: list[CompetencyQuestion],
                 graph: Graph) -> GateReport:
    reasons = []
    consistent = None if classification is None else classification.consistent
    if classification is None:
        reasons.append("not classified")
    elif not classification.consistent:
        reasons.append(f"inconsistent under {classification.profile}")
    blockers = sum(1 for f in findings if f.severity == "blocker")
    if blockers:
        reasons.append(f"{blockers} blocker finding(s)")
    results = [run_cq(c, graph) for c in cqs]
    failed = [r.id for r in results if not r.passed]
    if failed:
        reasons.append(f"competency questions failing: {', '.join(failed)}")
    return GateReport(not reasons, consistent,
                      classification.profile if classification else None, blockers,
                      results, reasons)
