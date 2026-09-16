"""Prototype implementations of the ontology-construction processes.

Implements the processes and measurement strategies described in
``docs/Ontology Definition/Ontology Construction Approaches and Metrics.pdf``
("Strategic Ontology Engineering in the Era of Generative AI"):

============  =============================================================
Module        Process
============  =============================================================
``neon``      The **NeOn** methodology — nine scenarios for ontology networks
``lot``       The **LOT** methodology — four iterative sprints, CQ-driven
``llms4ol``   The **LLMs4OL** paradigm — three ontology-learning subtasks
``pipeline``  **NeOn-GPT** — constrained generation with deterministic gates,
              plus the four-stage CI/CD drift gate
``metrics``   OntoAxiom-style P/R/F1, cohesion, structural, five criteria
``validation``OOPS!-style pitfalls, Themis CQ tests, CWA shape validation
============  =============================================================

Everything runs **offline and deterministically** by default: the LLM is an
injectable :class:`~ontology_construction.llms4ol.Extractor` whose default
implementation is rule-based, following the convention set by
:mod:`bottomup_ontology`. Swap in
:class:`~ontology_construction.llms4ol.LLMExtractor` for real work — the gates
and metrics are unchanged, which is the point.

Quickstart::

    import ontology_construction as oc

    state = oc.ConstructionState(
        domain="lending",
        documents=["A mortgage is a kind of loan. A loan is issued by a bank."],
        use_cases=["What kinds of loan are there?"],
    )
    graph = oc.build_hybrid_workflow()      # NeOn-GPT, gated
    state = oc.run_workflow(graph, state)

    print(state.summary())
    print(state.ontology.to_turtle())
    print(oc.DriftGate().run(state))
"""

from __future__ import annotations

from .llms4ol import (
    Extractor,
    HeuristicExtractor,
    LLMExtractor,
    PromptingStrategy,
    candidate_pairs,
    step_relation_extraction,
    step_taxonomy_discovery,
    step_term_typing,
)
from .lot import (
    SPRINTS,
    ConceptualModel,
    parse_chowlk,
    step_lot_implementation,
    step_lot_maintenance,
    step_lot_publication,
    step_lot_requirements,
)
from .metrics import (
    AxiomScorecard,
    CriteriaScorecard,
    PRF,
    StructuralMetrics,
    axiom_prf,
    criteria_scorecard,
    hashing_embedder,
    score_axioms,
    semantic_internal_cohesion,
    step_measure,
    structural_metrics,
)
from .neon import (
    SCENARIOS,
    SCENARIO_BY_ID,
    NeOnScenario,
    select_scenarios,
    step_apply_design_patterns,
    step_localize,
    step_reengineer_non_ontological,
    step_restructure,
    step_reuse_ontological,
    step_select_scenarios,
    step_specify_requirements,
)
from .pipeline import (
    DriftGate,
    DriftReport,
    Gate,
    GateResult,
    NeOnGPTPipeline,
    acyclicity_gate,
    consistency_gate,
    grounding_gate,
    syntax_gate,
    vocabulary_gate,
)
from .state import (
    AttributeEdge,
    CandidateTerm,
    CompetencyQuestion,
    ConstructionState,
    OntologyDraft,
    RelationEdge,
    Requirement,
    StageRecord,
    TaxonomyEdge,
)
from .tools import ToolRegistry, tool_specs
from .validation import (
    LEXICO_SYNTACTIC_PATTERNS,
    CQTest,
    Pitfall,
    PitfallReport,
    Severity,
    Shape,
    ShapeViolation,
    ThemisReport,
    compare_owa_cwa,
    formalise_cq,
    run_themis,
    scan_pitfalls,
    step_formalise_cqs,
    step_run_themis,
    step_scan_pitfalls,
    step_validate_shapes,
    validate_shapes,
)
from .workflow import (
    ALL_STEPS,
    STEP_BY_ID,
    ProcessStep,
    add_optional_step,
    build_hybrid_workflow,
    build_llms4ol_workflow,
    build_lot_workflow,
    build_neon_workflow,
    build_validation_workflow,
    configure_workflow,
    describe,
    remove_optional_step,
    run_workflow,
)

__all__ = [
    # state
    "ConstructionState", "OntologyDraft", "Requirement", "CompetencyQuestion",
    "CandidateTerm", "TaxonomyEdge", "RelationEdge", "AttributeEdge", "StageRecord",
    # NeOn
    "NeOnScenario", "SCENARIOS", "SCENARIO_BY_ID", "select_scenarios",
    "step_select_scenarios", "step_specify_requirements",
    "step_reengineer_non_ontological", "step_reuse_ontological",
    "step_apply_design_patterns", "step_restructure", "step_localize",
    # LOT
    "SPRINTS", "ConceptualModel", "parse_chowlk", "step_lot_requirements",
    "step_lot_implementation", "step_lot_publication", "step_lot_maintenance",
    # LLMs4OL
    "Extractor", "HeuristicExtractor", "LLMExtractor", "PromptingStrategy",
    "candidate_pairs", "step_term_typing", "step_taxonomy_discovery",
    "step_relation_extraction",
    # pipeline
    "NeOnGPTPipeline", "Gate", "GateResult", "DriftGate", "DriftReport",
    "syntax_gate", "acyclicity_gate", "vocabulary_gate", "grounding_gate",
    "consistency_gate",
    # validation
    "Severity", "Pitfall", "PitfallReport", "scan_pitfalls", "Shape",
    "ShapeViolation", "validate_shapes", "compare_owa_cwa", "CQTest",
    "ThemisReport", "formalise_cq", "run_themis", "LEXICO_SYNTACTIC_PATTERNS",
    "step_scan_pitfalls", "step_formalise_cqs", "step_run_themis",
    "step_validate_shapes",
    # metrics
    "PRF", "AxiomScorecard", "StructuralMetrics", "CriteriaScorecard",
    "axiom_prf", "score_axioms", "structural_metrics",
    "semantic_internal_cohesion", "criteria_scorecard", "hashing_embedder",
    "step_measure",
    # workflow + tools
    "ProcessStep", "ALL_STEPS", "STEP_BY_ID", "build_neon_workflow",
    "build_lot_workflow", "build_llms4ol_workflow", "build_hybrid_workflow",
    "build_validation_workflow", "configure_workflow", "run_workflow",
    "add_optional_step", "remove_optional_step", "describe",
    "tool_specs", "ToolRegistry",
]

__version__ = "0.1.0"
