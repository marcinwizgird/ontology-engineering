"""Construction processes as ``networkx`` graphs of step classes.

Same contract as :mod:`bottomup_ontology.workflow`:

* every step is a **class** (:class:`ProcessStep`), and an *instance* of that
  class is what is stored as a **networkx node**;
* every step corresponds to the invocation of exactly **one function**, bound as
  ``self.func`` and invoked through :meth:`ProcessStep.run`;
* the graph is executed in topological order over one shared
  :class:`~ontology_construction.state.ConstructionState`.

Three processes are provided, plus a composite:

``build_neon_workflow``      the NeOn lifecycle, scenario-driven
``build_lot_workflow``       the four LOT sprints
``build_llms4ol_workflow``   the three ontology-learning subtasks
``build_hybrid_workflow``    NeOn-GPT: learning stages with deterministic gates
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import networkx as nx

from . import llms4ol, lot, metrics, neon, validation
from .pipeline import (
    acyclicity_gate,
    consistency_gate,
    grounding_gate,
    syntax_gate,
    vocabulary_gate,
)
from .state import ConstructionState

__all__ = [
    "ProcessStep", "ALL_STEPS", "STEP_BY_ID",
    "build_neon_workflow", "build_lot_workflow", "build_llms4ol_workflow",
    "build_hybrid_workflow", "build_validation_workflow",
    "run_workflow", "configure_workflow", "add_optional_step",
    "remove_optional_step", "describe",
]


# --------------------------------------------------------------------------- #
# The step node
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class ProcessStep:
    """One step of a construction process — a hashable networkx node."""

    step_id: str
    name: str
    func: Callable[..., ConstructionState]
    process: str                       # NeOn | LOT | LLMs4OL | Validation | Metrics
    mandatory: bool = True
    description: str = ""
    #: JSON-schema-ish description of the step's tunable parameters.
    parameters: dict[str, Any] = field(default_factory=dict)
    #: Deterministic gates run after this step (the NeOn-GPT contract).
    gates: tuple[Callable[[ConstructionState], Any], ...] = ()

    def run(self, state: ConstructionState, **kwargs: Any) -> ConstructionState:
        state = self.func(state, **kwargs)
        for gate in self.gates:
            result = gate(state)
            state.record(self.step_id, result.ok, result.detail,
                         gate=gate.__name__, repaired=result.repaired,
                         rejected=result.rejected)
        return state

    # Identity is the step id, so an instance can be a graph node.
    def __hash__(self) -> int:
        return hash(self.step_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ProcessStep) and other.step_id == self.step_id

    def __repr__(self) -> str:  # pragma: no cover - display only
        flag = "" if self.mandatory else " (optional)"
        return f"<{self.process}:{self.step_id}{flag}>"


# --------------------------------------------------------------------------- #
# The catalogue
# --------------------------------------------------------------------------- #
def _steps() -> list[ProcessStep]:
    return [
        # -- NeOn ----------------------------------------------------------- #
        ProcessStep("neon.select_scenarios", "Select NeOn scenarios",
                    neon.step_select_scenarios, "NeOn",
                    description="Decide which of the nine scenarios the available "
                                "resources justify."),
        ProcessStep("neon.specify_requirements", "Specify requirements (ORSD)",
                    neon.step_specify_requirements, "NeOn",
                    description="Scenario 1 — use cases to requirements and CQs."),
        ProcessStep("neon.reengineer_nor", "Re-engineer non-ontological resources",
                    neon.step_reengineer_non_ontological, "NeOn", mandatory=False,
                    description="Scenario 2 — lift terms out of glossaries and corpora."),
        ProcessStep("neon.reuse_ontological", "Reuse ontological resources",
                    neon.step_reuse_ontological, "NeOn", mandatory=False,
                    description="Scenario 3 — import external ontologies with provenance."),
        ProcessStep("neon.apply_odps", "Apply ontology design patterns",
                    neon.step_apply_design_patterns, "NeOn", mandatory=False,
                    description="Scenario 7 — instantiate proven modelling patterns."),
        ProcessStep("neon.restructure", "Restructure (prune to the ORSD)",
                    neon.step_restructure, "NeOn", mandatory=False,
                    description="Scenario 8 — drop classes no requirement reaches."),
        ProcessStep("neon.localize", "Localise",
                    neon.step_localize, "NeOn", mandatory=False,
                    description="Scenario 9 — multilingual labels; reports gaps."),

        # -- LLMs4OL -------------------------------------------------------- #
        ProcessStep("llms4ol.term_typing", "Term extraction and typing",
                    llms4ol.step_term_typing, "LLMs4OL",
                    description="Task A — concepts and their semantic types.",
                    parameters={"max_terms": {"type": "integer",
                                              "description": "cap on terms kept"}}),
        ProcessStep("llms4ol.taxonomy_discovery", "Taxonomy discovery",
                    llms4ol.step_taxonomy_discovery, "LLMs4OL",
                    description="Task B — induce the is-a backbone.",
                    parameters={"min_score": {"type": "number",
                                              "description": "confidence floor"}},
                    gates=(vocabulary_gate, acyclicity_gate)),
        ProcessStep("llms4ol.relation_extraction", "Non-taxonomic relations",
                    llms4ol.step_relation_extraction, "LLMs4OL",
                    description="Task C — domain predicates, with the O(n^2) bound "
                                "made explicit.",
                    parameters={"max_pairs": {"type": "integer",
                                              "description": "candidate-pair budget"}},
                    gates=(vocabulary_gate, grounding_gate)),

        # -- LOT ------------------------------------------------------------ #
        ProcessStep("lot.requirements", "LOT sprint 1 — requirements",
                    lot.step_lot_requirements, "LOT",
                    description="Purpose, scope, users and competency questions.",
                    parameters={"require_cqs": {"type": "boolean",
                                                "description": "fail without CQs"}}),
        ProcessStep("lot.implementation", "LOT sprint 2 — implementation",
                    lot.step_lot_implementation, "LOT",
                    description="Conceptual model plus learned artifacts into OWL.",
                    gates=(syntax_gate, consistency_gate)),
        ProcessStep("lot.publication", "LOT sprint 3 — publication",
                    lot.step_lot_publication, "LOT",
                    description="Content negotiation, documentation, licence."),
        ProcessStep("lot.maintenance", "LOT sprint 4 — maintenance",
                    lot.step_lot_maintenance, "LOT", mandatory=False,
                    description="New requirements as issues; CQ regression check."),

        # -- Validation and metrics ------------------------------------------ #
        ProcessStep("themis.formalise", "Formalise competency questions",
                    validation.step_formalise_cqs, "Validation",
                    description="Lexico-syntactic patterns to test expressions."),
        ProcessStep("oops.scan", "Scan for pitfalls (OOPS!)",
                    validation.step_scan_pitfalls, "Validation",
                    description="Structural, functional and usability pitfalls."),
        ProcessStep("themis.run", "Run competency-question tests (Themis)",
                    validation.step_run_themis, "Validation",
                    description="Behaviour-driven functional validation."),
        ProcessStep("shacl.validate", "Validate instance data (SHACL, CWA)",
                    validation.step_validate_shapes, "Validation", mandatory=False,
                    description="Closed-world shape validation; contrasts with OWA."),
        ProcessStep("metrics.measure", "Measure",
                    metrics.step_measure, "Metrics",
                    description="OntoAxiom P/R/F1, cohesion, structural metrics, "
                                "and the five criteria."),
    ]


ALL_STEPS: list[ProcessStep] = _steps()
STEP_BY_ID: dict[str, ProcessStep] = {s.step_id: s for s in ALL_STEPS}


def _fresh(step_id: str) -> ProcessStep:
    """A new instance each time, so two graphs never share node objects."""
    template = STEP_BY_ID[step_id]
    return ProcessStep(template.step_id, template.name, template.func,
                       template.process, template.mandatory, template.description,
                       dict(template.parameters), template.gates)


def _chain(step_ids: list[str], name: str) -> nx.DiGraph:
    graph = nx.DiGraph(name=name)
    nodes = [_fresh(sid) for sid in step_ids]
    for node in nodes:
        graph.add_node(node, step_id=node.step_id, process=node.process)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a, b)
    return graph


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def build_neon_workflow(*, include_optional: bool = True) -> nx.DiGraph:
    """The NeOn lifecycle: select scenarios, then run the ones that apply."""
    ids = ["neon.select_scenarios", "neon.specify_requirements"]
    if include_optional:
        ids += ["neon.reuse_ontological", "neon.reengineer_nor", "neon.apply_odps"]
    ids += ["lot.implementation"]
    if include_optional:
        ids += ["neon.restructure", "neon.localize"]
    ids += ["oops.scan", "metrics.measure"]
    return _chain(ids, "NeOn")


def build_lot_workflow(*, include_maintenance: bool = True) -> nx.DiGraph:
    """The four LOT sprints, with validation folded into publication."""
    ids = ["lot.requirements", "themis.formalise", "lot.implementation",
           "oops.scan", "themis.run", "lot.publication", "metrics.measure"]
    if include_maintenance:
        ids.append("lot.maintenance")
    return _chain(ids, "LOT")


def build_llms4ol_workflow() -> nx.DiGraph:
    """The three ontology-learning subtasks, in dependency order."""
    return _chain(["llms4ol.term_typing", "llms4ol.taxonomy_discovery",
                   "llms4ol.relation_extraction", "lot.implementation",
                   "metrics.measure"], "LLMs4OL")


def build_hybrid_workflow() -> nx.DiGraph:
    """NeOn-GPT: the NeOn lifecycle with learning stages and gates between them."""
    return _chain([
        "neon.select_scenarios",
        "neon.specify_requirements",
        "themis.formalise",
        "neon.reuse_ontological",
        "neon.reengineer_nor",
        "llms4ol.term_typing",
        "llms4ol.taxonomy_discovery",
        "llms4ol.relation_extraction",
        "neon.apply_odps",
        "lot.implementation",
        "neon.restructure",
        "neon.localize",
        "oops.scan",
        "themis.run",
        "shacl.validate",
        "lot.publication",
        "metrics.measure",
    ], "NeOn-GPT")


def build_validation_workflow() -> nx.DiGraph:
    """The CI/CD drift gate as a graph: syntax, OOPS!, Themis, SHACL."""
    return _chain(["themis.formalise", "oops.scan", "themis.run",
                   "shacl.validate"], "DriftGate")


def configure_workflow(*, process: str = "hybrid", **kwargs: Any) -> nx.DiGraph:
    """Build a workflow by name — the configuration entry point."""
    builders = {
        "neon": build_neon_workflow,
        "lot": build_lot_workflow,
        "llms4ol": build_llms4ol_workflow,
        "hybrid": build_hybrid_workflow,
        "validation": build_validation_workflow,
    }
    try:
        builder = builders[process]
    except KeyError:
        raise KeyError(f"unknown process {process!r}; "
                       f"known: {sorted(builders)}") from None
    return builder(**kwargs)


# --------------------------------------------------------------------------- #
# Graph surgery
# --------------------------------------------------------------------------- #
def add_optional_step(graph: nx.DiGraph, step_id: str, *,
                      after: Optional[str] = None) -> nx.DiGraph:
    """Return a copy of *graph* with *step_id* spliced in after *after*."""
    if step_id not in STEP_BY_ID:
        raise KeyError(f"unknown step {step_id!r}")
    out = graph.copy()
    if any(n.step_id == step_id for n in out.nodes):
        return out
    node = _fresh(step_id)
    order = list(nx.topological_sort(out))
    anchor = next((n for n in order if n.step_id == after), order[-1] if order else None)
    out.add_node(node, step_id=node.step_id, process=node.process)
    if anchor is not None:
        successors = list(out.successors(anchor))
        out.add_edge(anchor, node)
        for succ in successors:
            out.remove_edge(anchor, succ)
            out.add_edge(node, succ)
    return out


def remove_optional_step(graph: nx.DiGraph, step_id: str) -> nx.DiGraph:
    """Return a copy of *graph* without *step_id*, re-wiring around it."""
    out = graph.copy()
    node = next((n for n in out.nodes if n.step_id == step_id), None)
    if node is None:
        return out
    if node.mandatory:
        raise ValueError(f"{step_id!r} is mandatory and cannot be removed")
    for pred in list(out.predecessors(node)):
        for succ in list(out.successors(node)):
            out.add_edge(pred, succ)
    out.remove_node(node)
    return out


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def run_workflow(graph: nx.DiGraph, state: ConstructionState, *,
                 params: Optional[dict[str, dict[str, Any]]] = None,
                 strict: bool = False) -> ConstructionState:
    """Execute *graph* in topological order over *state*.

    ``strict`` stops at the first failed step or gate — CI behaviour. The
    default collects every failure, which is more useful interactively.
    """
    params = params or {}
    for node in nx.topological_sort(graph):
        kwargs = params.get(node.step_id, {})
        try:
            state = node.run(state, **kwargs)
        except Exception as exc:                   # noqa: BLE001 - report, don't crash
            state.record(node.step_id, False,
                         f"raised {type(exc).__name__}: {exc}")
            if strict:
                break
            continue
        if strict and state.stages and not state.stages[-1].ok:
            break
    return state


def describe(graph: nx.DiGraph) -> str:
    """A readable rendering of the process — handy in notebooks and logs."""
    lines = [f"{graph.graph.get('name', 'workflow')}: "
             f"{graph.number_of_nodes()} steps, {graph.number_of_edges()} edges"]
    for node in nx.topological_sort(graph):
        gates = ", ".join(g.__name__ for g in node.gates)
        flag = " " if node.mandatory else "?"
        lines.append(f"  {flag} {node.step_id:34s} [{node.process}]"
                     + (f"  gates: {gates}" if gates else ""))
    return "\n".join(lines)
