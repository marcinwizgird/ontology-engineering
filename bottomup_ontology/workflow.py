"""Build, configure and execute the bottom-up ontology workflow as a
``networkx`` directed graph.

* The workflow is a :class:`networkx.DiGraph`.
* Each **node is a** :class:`~bottomup_ontology.steps.WorkflowStep` **instance**
  (a class instance, as required), and edges encode execution order /
  data-flow dependencies.
* Mandatory steps are always present; optional steps (axiom finding,
  human-in-the-loop) are switched on/off by the *configuration* functions.
* :func:`run_workflow` topologically sorts the graph and invokes each node's
  single function via :meth:`WorkflowStep.run`.
"""

from __future__ import annotations

from typing import Any, Iterable

import networkx as nx

from .state import WorkflowState
from .steps import PIPELINE_ORDER, STEP_CLASSES, WorkflowStep

# Special source/sink markers (kept as string nodes so they are easy to spot).
SOURCE = "Unstructured text"
SINK = "Ontology"

# Dependencies between steps (predecessor -> step). Used both to wire edges and
# to keep the graph valid when optional steps are removed.
_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "text_cleaning": (),
    "preprocessing": ("text_cleaning",),
    "term_extraction": ("preprocessing",),
    "relation_extraction": ("term_extraction",),
    "axiom_finding": ("relation_extraction",),
    "human_in_the_loop": ("axiom_finding",),  # falls back to relation_extraction if axiom_finding absent
    "evaluation": ("human_in_the_loop",),  # falls back to nearest present predecessor
}


# --------------------------------------------------------------------------- #
# Step instantiation
# --------------------------------------------------------------------------- #
def make_step(step_id: str, **params: Any) -> WorkflowStep:
    """Instantiate a step class by id, with optional default parameters."""
    if step_id not in STEP_CLASSES:
        raise KeyError(f"unknown step id: {step_id!r}. Known: {sorted(STEP_CLASSES)}")
    return STEP_CLASSES[step_id](**params)


def mandatory_step_ids() -> list[str]:
    return [sid for sid, cls in STEP_CLASSES.items() if cls.mandatory]


def optional_step_ids() -> list[str]:
    return [sid for sid, cls in STEP_CLASSES.items() if not cls.mandatory]


# --------------------------------------------------------------------------- #
# Graph construction / configuration
# --------------------------------------------------------------------------- #
def configure_workflow(
    include_axiom_finding: bool = True,
    include_human_in_the_loop: bool = True,
    step_params: dict[str, dict[str, Any]] | None = None,
) -> nx.DiGraph:
    """Build a workflow graph with the chosen *optional* steps switched on.

    Mandatory steps (text cleaning, pre-processing, term extraction, relation
    extraction, evaluation) are always included.  The two optional steps —
    *axiom finding* and *human-in-the-loop evaluation* — are toggled here.

    Parameters
    ----------
    include_axiom_finding, include_human_in_the_loop:
        Toggle the optional steps.
    step_params:
        Per-step default parameters, e.g. ``{"term_extraction": {"top_k": 20}}``.
    """
    step_params = step_params or {}
    selected = list(mandatory_step_ids_in_order())
    if include_axiom_finding:
        selected = _insert_in_order(selected, "axiom_finding")
    if include_human_in_the_loop:
        selected = _insert_in_order(selected, "human_in_the_loop")

    steps = [make_step(sid, **step_params.get(sid, {})) for sid in selected]
    return build_graph(steps)


def build_default_workflow(**step_params: dict[str, Any]) -> nx.DiGraph:
    """The recommended full pipeline: every step enabled (Fig. 7.7)."""
    return configure_workflow(
        include_axiom_finding=True,
        include_human_in_the_loop=True,
        step_params=step_params or None,
    )


def build_minimal_workflow(step_params: dict[str, dict[str, Any]] | None = None) -> nx.DiGraph:
    """The smallest valid pipeline: mandatory steps only."""
    return configure_workflow(
        include_axiom_finding=False,
        include_human_in_the_loop=False,
        step_params=step_params,
    )


def build_graph(steps: Iterable[WorkflowStep]) -> nx.DiGraph:
    """Wire a list of step instances into a DiGraph (+ SOURCE/SINK markers)."""
    steps = list(steps)
    present = {s.step_id: s for s in steps}
    g = nx.DiGraph(name="bottom-up-ontology-development")

    g.add_node(SOURCE, kind="io", label=SOURCE)
    g.add_node(SINK, kind="io", label=SINK)

    for step in steps:
        g.add_node(
            step,
            kind="step",
            step_id=step.step_id,
            label=step.label,
            mandatory=step.mandatory,
            techniques=list(step.techniques),
            category=step.category,
        )

    ordered_present = [sid for sid in PIPELINE_ORDER if sid in present]
    # connect SOURCE -> first step, last step -> SINK
    if ordered_present:
        g.add_edge(SOURCE, present[ordered_present[0]], relation="provides")
        g.add_edge(present[ordered_present[-1]], SINK, relation="produces")

    # connect each step to its nearest present predecessor
    for idx, sid in enumerate(ordered_present):
        if idx == 0:
            continue
        prev = present[ordered_present[idx - 1]]
        g.add_edge(prev, present[sid], relation="then")

    # the human-in-the-loop step also feeds the evaluation step explicitly
    if "human_in_the_loop" in present and "evaluation" in present:
        g.add_edge(present["human_in_the_loop"], present["evaluation"], relation="verifies")

    return g


# --------------------------------------------------------------------------- #
# Dynamic (de)activation of optional steps on an existing graph
# --------------------------------------------------------------------------- #
def add_optional_step(graph: nx.DiGraph, step_id: str, **params: Any) -> nx.DiGraph:
    """Insert an optional step into an existing graph at its canonical position.

    Returns a *new* graph (the input is left untouched) so notebooks can show
    before/after.
    """
    cls = STEP_CLASSES.get(step_id)
    if cls is None:
        raise KeyError(f"unknown step id: {step_id!r}")
    if cls.mandatory:
        raise ValueError(f"{step_id!r} is mandatory and always present")
    current = current_step_ids(graph)
    if step_id in current:
        return graph.copy()
    new_ids = _insert_in_order(current, step_id)
    return _rebuild(graph, new_ids, {step_id: params})


def remove_optional_step(graph: nx.DiGraph, step_id: str) -> nx.DiGraph:
    """Remove an optional step, re-wiring around it.  Returns a new graph."""
    cls = STEP_CLASSES.get(step_id)
    if cls is None:
        raise KeyError(f"unknown step id: {step_id!r}")
    if cls.mandatory:
        raise ValueError(f"cannot remove mandatory step {step_id!r}")
    new_ids = [sid for sid in current_step_ids(graph) if sid != step_id]
    return _rebuild(graph, new_ids, {})


def current_step_ids(graph: nx.DiGraph) -> list[str]:
    """Step ids present in the graph, in canonical pipeline order."""
    present = {n.step_id for n in graph.nodes if isinstance(n, WorkflowStep)}
    return [sid for sid in PIPELINE_ORDER if sid in present]


def _rebuild(graph: nx.DiGraph, step_ids: list[str], extra_params: dict) -> nx.DiGraph:
    # preserve existing default_params where possible
    existing = {n.step_id: n for n in graph.nodes if isinstance(n, WorkflowStep)}
    steps = []
    for sid in step_ids:
        params = extra_params.get(sid)
        if params is not None:
            steps.append(make_step(sid, **params))
        elif sid in existing:
            steps.append(make_step(sid, **existing[sid].default_params))
        else:
            steps.append(make_step(sid))
    return build_graph(steps)


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def run_workflow(
    graph: nx.DiGraph,
    state: WorkflowState,
    step_params: dict[str, dict[str, Any]] | None = None,
    verbose: bool = False,
) -> WorkflowState:
    """Execute the workflow by topological order, invoking each node's function.

    Each :class:`WorkflowStep` node is executed via its single ``run`` call,
    which dispatches to the underlying step function.  IO marker nodes
    (``SOURCE``/``SINK``) are skipped.
    """
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("workflow graph must be a DAG")
    step_params = step_params or {}
    for node in nx.topological_sort(graph):
        if not isinstance(node, WorkflowStep):
            continue
        params = step_params.get(node.step_id, {})
        if verbose:
            print(f">> running {node.step_id} ...")
        state = node.run(state, **params)
        if verbose and state.log:
            print(f"   {state.log[-1]}")
    return state


def execution_plan(graph: nx.DiGraph) -> list[str]:
    """Return the ordered list of step ids that ``run_workflow`` will execute."""
    return [n.step_id for n in nx.topological_sort(graph) if isinstance(n, WorkflowStep)]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def mandatory_step_ids_in_order() -> list[str]:
    mand = set(mandatory_step_ids())
    return [sid for sid in PIPELINE_ORDER if sid in mand]


def _insert_in_order(step_ids: list[str], new_id: str) -> list[str]:
    """Insert ``new_id`` into ``step_ids`` respecting :data:`PIPELINE_ORDER`."""
    target = list(step_ids)
    if new_id in target:
        return target
    rank = {sid: i for i, sid in enumerate(PIPELINE_ORDER)}
    target.append(new_id)
    target.sort(key=lambda s: rank[s])
    return target
