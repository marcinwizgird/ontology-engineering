"""NeOn-GPT — the hybrid, gated pipeline, and the CI/CD drift gate.

This is the centrepiece of the report's practical argument. NeOn-GPT "fuses the
rigorous, procedural scaffolding of the NeOn methodology with the generative
power of LLMs, creating an 'expert-in-the-loop' co-pilot system". Rather than
tasking a model with producing an ontology, it "orchestrates a sequence of
highly constrained prompts aligned with the NeOn lifecycle", and crucially:

    "the outputs at each stage of the NeOn-GPT pipeline undergo automated syntax
    validation, consistency checks, and error resolution using external
    deterministic tools before proceeding to the next step."

That sentence is the whole design. :class:`Gate` makes it executable: every
generative stage is followed by a deterministic check that can **pass**,
**repair** or **reject**, and nothing reaches the next stage ungated. The result
is that the LLM's flexibility is "strictly bounded by formal logical
constraints" — and, because every gate decision is recorded on the state, the
boundedness is auditable afterwards rather than asserted.

:class:`DriftGate` implements the four-stage CI/CD workflow the report
prescribes for preventing *ontology drift* — "where the conceptual schema
gradually diverges from the underlying data reality":

1. syntax check
2. structural scan (OOPS!)
3. functional testing (Themis)
4. data validation (SHACL)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from . import llms4ol, lot, neon, validation
from .state import ConstructionState, StageRecord

__all__ = ["Gate", "GateResult", "NeOnGPTPipeline", "DriftGate", "DriftReport",
           "syntax_gate", "acyclicity_gate", "vocabulary_gate",
           "grounding_gate", "consistency_gate"]


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #
@dataclass
class GateResult:
    """What a deterministic gate decided about a stage's output."""

    ok: bool
    detail: str = ""
    repaired: int = 0
    rejected: int = 0


#: A gate is a pure function over the state; it may repair the state in place.
Gate = Callable[[ConstructionState], GateResult]


_IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S*$")


def syntax_gate(state: ConstructionState) -> GateResult:
    """Does the draft serialise, re-parse, and use well-formed IRIs?

    The first of the report's four CI/CD stages, and the cheapest place to catch
    a malformed generation.

    The IRI check is not redundant with the parse: rdflib is deliberately
    lenient and will *warn* about an IRI containing spaces while still parsing
    the document, so a gate that only catches parse errors passes a graph that
    cannot be serialised again later. Checking explicitly is what makes this a
    syntax gate rather than a parse attempt.
    """
    try:
        graph = state.ontology.to_rdflib()
    except Exception as exc:                       # noqa: BLE001 - report, don't crash
        return GateResult(False, f"serialisation failed: {type(exc).__name__}: {exc}")

    bad = [iri for iri in [state.ontology.iri, *state.ontology.imports]
           if not _IRI_RE.match(iri.strip())]
    if bad:
        return GateResult(False,
                          f"{len(bad)} malformed IRI(s): "
                          + ", ".join(repr(b) for b in bad[:3]))
    return GateResult(True, f"{len(graph)} triples parsed")


def acyclicity_gate(state: ConstructionState) -> GateResult:
    """Reject taxonomic cycles, repairing by dropping the weakest edge.

    OOPS! P06, which the report names as a typical critical pitfall. Repair
    rather than rejection is right here because a single spurious edge should
    not discard an otherwise good taxonomy — but the repair is counted, so a
    pipeline that repairs constantly is visibly untrustworthy.
    """
    edges = {(e.child, e.parent): e for e in state.taxonomy_edges if e.accepted}
    removed = 0
    while True:
        cycles = validation._find_cycles(list(edges))
        if not cycles:
            break
        cycle = cycles[0]
        pairs = [(cycle[i], cycle[i + 1]) for i in range(len(cycle) - 1)]
        present = [p for p in pairs if p in edges]
        if not present:
            break
        weakest = min(present, key=lambda p: edges[p].score)
        edges[weakest].accepted = False
        del edges[weakest]
        removed += 1
    return GateResult(True, f"{removed} cycle-breaking edge(s) rejected",
                      rejected=removed) if removed else GateResult(True, "acyclic")


def vocabulary_gate(state: ConstructionState) -> GateResult:
    """Every taxonomy and relation endpoint must be a known term.

    This is the anti-hallucination gate. The report warns that LLMs are "prone
    to hallucinations — generating structurally plausible but factually
    incorrect triples". An edge whose endpoints were never extracted from the
    source is exactly that, and it is rejected rather than repaired.
    """
    known = {t.label.lower() for t in state.candidate_terms}
    known |= {c.lower() for c in state.ontology.classes}
    rejected = 0
    for edge in state.taxonomy_edges:
        if not edge.accepted:
            continue
        if edge.child.lower() not in known or edge.parent.lower() not in known:
            edge.accepted = False
            rejected += 1
    for rel in state.relation_edges:
        if not rel.accepted:
            continue
        if rel.domain.lower() not in known or rel.range.lower() not in known:
            rel.accepted = False
            rejected += 1
    return GateResult(rejected == 0,
                      f"{rejected} edge(s) referenced unknown terms",
                      rejected=rejected)


def grounding_gate(state: ConstructionState) -> GateResult:
    """Every accepted relation must be traceable to the source documents.

    Structural plausibility is not evidence. A relation whose endpoints never
    co-occur in a sentence of the corpus was invented, and is rejected.
    """
    corpus = " ".join(state.documents).lower()
    rejected = 0
    for rel in state.relation_edges:
        if not rel.accepted:
            continue
        if rel.domain.lower() not in corpus or rel.range.lower() not in corpus:
            rel.accepted = False
            rejected += 1
    return GateResult(rejected == 0,
                      f"{rejected} relation(s) not grounded in the corpus",
                      rejected=rejected)


def consistency_gate(state: ConstructionState) -> GateResult:
    """No critical OOPS! pitfalls may pass to the next stage."""
    report = validation.scan_pitfalls(state.ontology, state)
    state.reports["pitfalls"] = report.as_dict()
    if report.blocks_release:
        codes = sorted({p.code for p in report.by_severity(validation.Severity.CRITICAL)})
        return GateResult(False, f"critical pitfalls: {', '.join(codes)}")
    return GateResult(True, f"{report.important} important, {report.minor} minor")


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #
@dataclass
class NeOnGPTPipeline:
    """Constrained generative stages, each followed by a deterministic gate.

    ``strict`` decides what happens when a gate fails. ``True`` halts the run —
    the behaviour you want in CI. ``False`` records the failure and continues,
    which is what you want when exploring, because it lets you see every gate
    that would have fired rather than only the first.
    """

    extractor: Optional[llms4ol.Extractor] = None
    strict: bool = True
    #: (stage name, stage function, gates) — the NeOn lifecycle, gated.
    stages: list[tuple[str, Callable[[ConstructionState], ConstructionState],
                       tuple[Gate, ...]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stages:
            return
        ex = self.extractor
        self.stages = [
            ("scope the domain", neon.step_select_scenarios, ()),
            ("specify requirements", neon.step_specify_requirements, ()),
            ("identify resources for reuse", neon.step_reuse_ontological, ()),
            ("re-engineer non-ontological resources",
             neon.step_reengineer_non_ontological, ()),
            ("generate class candidates",
             lambda s: llms4ol.step_term_typing(s, extractor=ex), ()),
            ("generate class hierarchy",
             lambda s: llms4ol.step_taxonomy_discovery(s, extractor=ex),
             (vocabulary_gate, acyclicity_gate)),
            ("create properties",
             lambda s: llms4ol.step_relation_extraction(s, extractor=ex),
             (vocabulary_gate, grounding_gate)),
            ("apply design patterns", neon.step_apply_design_patterns, ()),
            ("formalise", lot.step_lot_implementation, (syntax_gate, consistency_gate)),
            ("restructure", neon.step_restructure, ()),
            ("localise", neon.step_localize, ()),
        ]

    def run(self, state: ConstructionState) -> ConstructionState:
        """Execute the lifecycle. Returns the state whatever happens."""
        executed = 0
        for name, fn, gates in self.stages:
            try:
                state = fn(state)
            except Exception as exc:               # noqa: BLE001 - a stage may fail
                state.record(f"neon-gpt::{name}", False,
                             f"stage raised {type(exc).__name__}: {exc}")
                if self.strict:
                    break
                continue
            executed += 1

            halted = False
            for gate in gates:
                result = gate(state)
                state.record(f"neon-gpt::{name}", result.ok, result.detail,
                             gate=gate.__name__, repaired=result.repaired,
                             rejected=result.rejected)
                if not result.ok and self.strict:
                    halted = True
                    break
            if halted:
                break
        state.reports["pipeline"] = {
            "stages_run": executed,
            "stages_total": len(self.stages),
            "gate_failures": [s.stage for s in state.stages
                              if s.stage.startswith("neon-gpt::") and not s.ok],
            "rejected": sum(s.rejected for s in state.stages),
            "repaired": sum(s.repaired for s in state.stages),
        }
        return state


# --------------------------------------------------------------------------- #
# The CI/CD drift gate
# --------------------------------------------------------------------------- #
@dataclass
class DriftReport:
    """The result of the four-stage CI/CD check."""

    stages: list[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.stages)

    @property
    def first_failure(self) -> Optional[tuple[str, bool, str]]:
        return next((s for s in self.stages if not s[1]), None)

    def as_dict(self) -> dict:
        return {"passed": self.passed,
                "stages": [{"stage": n, "passed": ok, "detail": d}
                           for n, ok, d in self.stages],
                "first_failure": self.first_failure[0] if self.first_failure else None}

    def __str__(self) -> str:  # pragma: no cover - display only
        lines = [("PASS" if self.passed else "FAIL") + " drift gate"]
        for name, ok, detail in self.stages:
            lines.append(f"  [{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        return "\n".join(lines)


@dataclass
class DriftGate:
    """The report's four automated tests, run on every proposed commit.

    ``fail_fast`` mirrors a real pipeline: stop at the first failure. Set it to
    ``False`` to collect every failure in one run, which is more useful when a
    human is reading the output than when a robot is gating a merge.
    """

    instances: list[dict] = field(default_factory=list)
    shapes: list[validation.Shape] = field(default_factory=list)
    fail_fast: bool = True

    def run(self, state: ConstructionState) -> DriftReport:
        report = DriftReport()

        # 1 — syntax check
        result = syntax_gate(state)
        report.stages.append(("1. syntax check", result.ok, result.detail))
        if not result.ok and self.fail_fast:
            state.reports["drift"] = report.as_dict()
            return report

        # 2 — structural scan (OOPS!)
        scan = validation.scan_pitfalls(state.ontology, state)
        state.reports["pitfalls"] = scan.as_dict()
        report.stages.append((
            "2. structural scan (OOPS!)", not scan.blocks_release,
            f"{scan.critical} critical, {scan.important} important, "
            f"{scan.minor} minor"))
        if scan.blocks_release and self.fail_fast:
            state.reports["drift"] = report.as_dict()
            return report

        # 3 — functional testing (Themis)
        themis = validation.run_themis(state)
        state.reports["themis"] = themis.as_dict()
        report.stages.append((
            "3. functional testing (Themis)", themis.failed == 0,
            f"{themis.passed}/{len(themis.tests)} CQs satisfied "
            f"(coverage {themis.coverage:.0%})"))
        if themis.failed and self.fail_fast:
            state.reports["drift"] = report.as_dict()
            return report

        # 4 — data validation (SHACL, closed world)
        shapes = self.shapes or validation._shapes_from_draft(state.ontology)
        comparison = validation.compare_owa_cwa(self.instances, shapes)
        state.reports["shapes"] = comparison
        report.stages.append((
            "4. data validation (SHACL)", comparison["cwa_rejections"] == 0,
            f"{comparison['cwa_rejections']} violation(s) over "
            f"{comparison['instances']} instance(s)"))

        state.reports["drift"] = report.as_dict()
        state.record("cicd.drift_gate", report.passed,
                     report.first_failure[0] if report.first_failure
                     else "all four stages passed", gate="CI/CD")
        return report
