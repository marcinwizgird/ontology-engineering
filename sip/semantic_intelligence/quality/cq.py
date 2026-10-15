"""Competency questions as executable tests, and the release gate.

Neither Protégé nor VocBench has this; it is the platform's answer to "how do we
know the ontology does what it was built for?" (Grüninger & Fox; Keet ch. 5).

A :class:`CompetencyQuestion` holds the natural-language question, a SPARQL
formulation, and an *expectation* — one of ``non-empty``, ``empty``,
``count>=N``, ``contains:<IRI>`` or ``ask:true|false``. CQs are stored as RDF in
the project's ``cq`` graph (``sip:CompetencyQuestion``) so they are versioned with
the ontology.

Each CQ has a priority, as in NeOn's ORSD: ``must``, ``should`` or ``may``. The
release gate (FR-QA-02) requires that the ontology is consistent under the selected
profile, that there is no ``blocker`` finding, and that every ``must`` CQ passes; a
failing ``should`` or ``may`` CQ is reported as a warning.

A passing CQ is only evidence if it *could* have failed. :func:`discrimination`
checks that (FR-QA-03): a CQ that also passes on an empty graph is **vacuous**
(the classic case is ``?x rdfs:subClassOf* :B``, whose zero-length path binds
``:B`` itself), and one that still passes once every triple mentioning its own
terms is removed is **insensitive** — it does not test the terms it names. Both are
reported as release-gate warnings, never as failures: the CQ may be badly written,
or the question may genuinely be answerable without the ontology.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.plugins.sparql import prepareQuery

from ..core.namespaces import SIP

PRIORITIES = ("must", "should", "may")
EXPECTATION = re.compile(r"non-empty|empty|count>=\d+|ask:(true|false)|contains:.+")


@dataclass
class CompetencyQuestion:
    id: str
    question: str
    sparql: str
    expectation: str = "non-empty"
    stage: str = "scope"
    source: str | None = None
    priority: str = "must"

    @property
    def iri(self) -> URIRef:
        return URIRef(f"urn:sip:cq:{self.id}")

    def triples(self):
        s = self.iri
        yield (s, RDF.type, SIP.CompetencyQuestion)
        yield (s, RDFS.label, Literal(self.question, lang="en"))
        yield (s, SIP.sparql, Literal(self.sparql))
        yield (s, SIP.expectation, Literal(self.expectation))
        yield (s, SIP.priority, Literal(self.priority))
        if self.source:
            yield (s, SIP.derivedFrom, Literal(self.source))

    @classmethod
    def from_graph(cls, g: Graph) -> list["CompetencyQuestion"]:
        out = []
        for s in g.subjects(RDF.type, SIP.CompetencyQuestion):
            src = g.value(s, SIP.derivedFrom)
            out.append(cls(str(s).rsplit(":", 1)[-1], str(g.value(s, RDFS.label)),
                           str(g.value(s, SIP.sparql)), str(g.value(s, SIP.expectation)
                                                            or "non-empty"),
                           source=str(src) if src is not None else None,
                           priority=str(g.value(s, SIP.priority) or "must")))
        return sorted(out, key=lambda c: c.id)


def problems(cq: CompetencyQuestion, namespaces: dict[str, str] | None = None) -> list[str]:
    """What stops *cq* from being an executable test (empty list: nothing)."""
    out = []
    if not EXPECTATION.fullmatch(cq.expectation.strip()):
        out.append(f"bad expectation {cq.expectation!r}")
    if cq.priority not in PRIORITIES:
        out.append(f"priority is one of {' | '.join(PRIORITIES)}, not {cq.priority!r}")
    try:
        prepareQuery(cq.sparql, initNs=namespaces or {})
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        out.append(f"SPARQL does not parse: {exc}")
    return out


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


#: vocabularies a CQ may use without "naming a term" of the ontology
_BUILTIN = (str(RDF), str(RDFS), str(OWL), str(XSD), str(SIP))
NEGATIVE = re.compile(r"empty|ask:false")


def terms(cq: CompetencyQuestion) -> set[URIRef]:
    """The ontology IRIs a CQ's SPARQL names (built-in vocabularies excluded)."""
    found: set[URIRef] = set()

    def walk(x, depth=0) -> None:
        if depth > 60:
            return
        if isinstance(x, URIRef):
            if not str(x).startswith(_BUILTIN):
                found.add(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v, depth + 1)
        elif hasattr(x, "__dict__") and type(x).__module__.startswith("rdflib.paths"):
            for v in vars(x).values():
                walk(v, depth + 1)

    try:
        walk(prepareQuery(cq.sparql).algebra)
    except Exception:  # noqa: BLE001 - an unparsable CQ names nothing
        return set()
    return found


def discrimination(cq: CompetencyQuestion, g: Graph) -> dict:
    """Could this CQ have failed? One of ``discriminating``, ``vacuous``,
    ``insensitive``, ``failing``, ``negative`` (an ``empty``/``ask:false`` CQ — passing
    on an empty graph is what it is for, so the empty-graph test does not apply) or
    ``error``."""
    here = run_cq(cq, g)
    named = sorted(str(t) for t in terms(cq))
    out = {"id": cq.id, "passed": here.passed, "terms": named}
    if here.detail.startswith("query error"):
        return {**out, "status": "error", "detail": here.detail}
    if not here.passed:
        return {**out, "status": "failing", "detail": here.detail}
    if NEGATIVE.fullmatch(cq.expectation.strip()):
        return {**out, "status": "negative", "detail": "negative test; not assessed"}
    if run_cq(cq, Graph()).passed:
        return {**out, "status": "vacuous", "detail": "also passes on an empty graph"}
    if named:
        mentioned = set(map(URIRef, named))
        ablated = Graph()
        for t in g:
            if not mentioned.intersection(t):
                ablated.add(t)
        if run_cq(cq, ablated).passed:
            return {**out, "status": "insensitive",
                    "detail": "still passes with every triple naming its terms removed"}
    return {**out, "status": "discriminating", "detail": here.detail}


@dataclass
class GateReport:
    passed: bool
    consistent: bool | None
    profile: str | None
    blockers: int
    cq_results: list[CqResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "consistent": self.consistent, "profile": self.profile,
                "blockers": self.blockers, "reasons": self.reasons, "warnings": self.warnings,
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
    priority = {c.id: c.priority for c in cqs}
    failed = [r.id for r in results if not r.passed and priority[r.id] == "must"]
    if failed:
        reasons.append(f"competency questions failing: {', '.join(failed)}")
    soft = [f"{r.id} ({priority[r.id]})" for r in results
            if not r.passed and priority[r.id] != "must"]
    warnings = [f"competency questions failing: {', '.join(soft)}"] if soft else []
    hollow = [f"{c.id} ({d['status']})" for c in cqs if priority[c.id] == "must"
              and (d := discrimination(c, graph))["status"] in ("vacuous", "insensitive")]
    if hollow:
        warnings.append(f"competency questions that test nothing: {', '.join(hollow)}")
    return GateReport(not reasons, consistent,
                      classification.profile if classification else None, blockers,
                      results, reasons, warnings)
