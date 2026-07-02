"""Bottom-up ontology development workflow.

A small, dependency-light implementation of the *text-to-ontology* pipeline
from Keet, *Ontology Repository* (2nd ed.), Chapter 7 ("Bottom-up Ontology
Development"), Figure 7.7.

The pipeline turns an unstructured-text corpus into an ontology through the
stages:

    Unstructured text
        → Text cleaning            (mandatory)
        → Pre-processing           (mandatory)
        → Term (concept) extraction(mandatory)
        → Relation extraction      (mandatory)
        → Axiom finding            (optional)
        → Human-in-the-loop        (optional)
        → Evaluation               (mandatory)
    → Ontology

Each step is a :class:`~bottomup_ontology.steps.WorkflowStep` class instance
used as a node in a ``networkx`` :class:`~networkx.DiGraph`, and each step is
the invocation of a single function that can also be reused as an agentic
function tool.
"""

from __future__ import annotations

from .state import CandidateTerm, Ontology, Relation, Token, WorkflowState
from .steps import (
    PIPELINE_ORDER,
    STEP_CLASSES,
    AxiomFindingStep,
    EvaluationStep,
    HumanInTheLoopStep,
    PreProcessingStep,
    RelationExtractionStep,
    TermExtractionStep,
    TextCleaningStep,
    WorkflowStep,
    step_axiom_finding,
    step_evaluation,
    step_human_in_the_loop,
    step_preprocessing,
    step_relation_extraction,
    step_term_extraction,
    step_text_cleaning,
)
from .tools import ToolRegistry, tool_specs
from .workflow import (
    SINK,
    SOURCE,
    add_optional_step,
    build_default_workflow,
    build_graph,
    build_minimal_workflow,
    configure_workflow,
    current_step_ids,
    execution_plan,
    make_step,
    mandatory_step_ids,
    optional_step_ids,
    remove_optional_step,
    run_workflow,
)

__version__ = "0.1.0"

__all__ = [
    # state / artifacts
    "WorkflowState", "Ontology", "Token", "CandidateTerm", "Relation",
    # steps
    "WorkflowStep", "STEP_CLASSES", "PIPELINE_ORDER",
    "TextCleaningStep", "PreProcessingStep", "TermExtractionStep",
    "RelationExtractionStep", "AxiomFindingStep", "HumanInTheLoopStep",
    "EvaluationStep",
    # step functions (agentic tools)
    "step_text_cleaning", "step_preprocessing", "step_term_extraction",
    "step_relation_extraction", "step_axiom_finding", "step_human_in_the_loop",
    "step_evaluation",
    # workflow graph
    "configure_workflow", "build_default_workflow", "build_minimal_workflow",
    "build_graph", "add_optional_step", "remove_optional_step",
    "current_step_ids", "execution_plan", "make_step",
    "mandatory_step_ids", "optional_step_ids", "run_workflow",
    "SOURCE", "SINK",
    # tools
    "ToolRegistry", "tool_specs",
]
