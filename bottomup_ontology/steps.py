"""Workflow steps for the bottom-up (text-to-ontology) pipeline.

Design contract (matches the task requirements):

* **Every workflow step is a class** (subclass of :class:`WorkflowStep`).  An
  instance of such a class is what gets stored *as a networkx node* in
  ``workflow.py``.
* **Every step corresponds to the invocation of exactly one function** — the
  module-level ``step_*`` function bound to the class as ``self.func`` and
  invoked through :meth:`WorkflowStep.run`.  Those functions take a shared
  :class:`~bottomup_ontology.state.WorkflowState`, mutate it, and return it, so
  they can be reused directly as **function tools** in an agentic system
  (see ``tools.py``).
* Each step declares whether it is **mandatory** or **optional**, the
  Figure 7.7 **techniques** it represents, and a JSON-schema of its tunable
  **parameters** (used for tool exposure).

Pipeline order (Fig. 7.7):
    text cleaning → pre-processing → term extraction → relation extraction
    → axiom finding (opt) → human-in-the-loop (opt) → evaluation → Ontology
"""

from __future__ import annotations

from typing import Any, Callable

from . import techniques as T
from .state import CandidateTerm, Relation, WorkflowState


# --------------------------------------------------------------------------- #
# Step functions  (one per step — reusable as agentic function tools)
# --------------------------------------------------------------------------- #
def step_text_cleaning(state: WorkflowState) -> WorkflowState:
    """Clean, PoS-tag and lemmatise the corpus (Fig. 7.7: *Text cleaning*)."""
    state.tokens = T.clean_and_tag(state.documents)
    state.note(f"text_cleaning: produced {len(state.tokens)} tokens")
    return state


def step_preprocessing(state: WorkflowState) -> WorkflowState:
    """Contrastive relevance + co-occurrence analysis (Fig. 7.7: *Pre-processing*)."""
    if not state.tokens:
        state.tokens = T.clean_and_tag(state.documents)
    state.term_scores = T.contrastive_relevance(state.tokens, state.background_corpus)
    state.cooccurrence = T.cooccurrence_counts(state.tokens)
    state.note(
        f"preprocessing: scored {len(state.term_scores)} terms, "
        f"{len(state.cooccurrence)} co-occurrence pairs"
    )
    return state


def step_term_extraction(
    state: WorkflowState, min_frequency: int = 1, top_k: int | None = None
) -> WorkflowState:
    """Extract candidate classes and term-composition subclasses.

    Fig. 7.7: *Term (concept) extraction* (term composition / C-value flavour).
    Populates ``state.candidate_terms`` and seeds ``state.ontology`` with
    classes + ``head``-based subclass axioms.
    """
    if not state.tokens:
        state.tokens = T.clean_and_tag(state.documents)
    if not state.term_scores:
        state.term_scores = T.contrastive_relevance(state.tokens, state.background_corpus)
    candidates = T.extract_candidate_terms(state.tokens, state.term_scores, min_frequency)
    if top_k is not None:
        candidates = candidates[:top_k]
    state.candidate_terms = candidates

    for c in candidates:
        state.ontology.add_class(c.term)
    for sub, sup in T.composition_subclasses([c.term for c in candidates]):
        state.ontology.add_subclass(sub, sup)
    state.note(
        f"term_extraction: {len(candidates)} candidate classes, "
        f"{len(state.ontology.subclass_of)} composition subclass axioms"
    )
    return state


def step_relation_extraction(state: WorkflowState) -> WorkflowState:
    """Extract object-property candidates (Fig. 7.7: *Relation extraction*)."""
    known = {c.term for c in state.candidate_terms}
    # also allow single-word heads of multiword terms as relation endpoints
    known |= {c.term.split()[-1] for c in state.candidate_terms}
    rels = T.extract_relations(state.tokens, known)
    state.candidate_relations = rels
    for r in rels:
        state.ontology.add_object_property(r)
    state.note(f"relation_extraction: {len(rels)} candidate object properties")
    return state


def step_axiom_finding(state: WorkflowState) -> WorkflowState:
    """Find subsumption axioms via lexico-syntactic patterns (Fig. 7.7: *Axiom finding*)."""
    pairs = T.hearst_subclass_axioms(state.documents)
    added = 0
    for sub, sup in pairs:
        if (sub, sup) not in state.ontology.subclass_of:
            state.ontology.add_subclass(sub, sup)
            state.ontology.axioms.append(f"{sub} ⊑ {sup}  (lexico-syntactic pattern)")
            added += 1
    state.note(f"axiom_finding: {added} subclass axioms from Hearst patterns")
    return state


def step_human_in_the_loop(state: WorkflowState) -> WorkflowState:
    """Human verification of candidates (Fig. 7.7: *Human-in-the-loop evaluation*).

    Uses ``state.human_approver(kind, label) -> bool``; when no approver is
    configured every candidate is accepted (i.e. the step is a no-op gate).
    Rejected classes/properties are pruned from the ontology.
    """
    approver: Callable[[str, str], bool] | None = state.human_approver
    if approver is None:
        state.note("human_in_the_loop: no approver set — all candidates accepted")
        return state

    kept_classes = {c for c in state.ontology.classes if approver("class", c)}
    rejected = state.ontology.classes - kept_classes
    state.ontology.classes = kept_classes
    state.ontology.subclass_of = {
        (a, b) for (a, b) in state.ontology.subclass_of if a in kept_classes and b in kept_classes
    }
    kept_props = []
    for r in state.ontology.object_properties:
        if r.subject in kept_classes and r.object in kept_classes and approver(
            "property", f"{r.subject} {r.predicate} {r.object}"
        ):
            kept_props.append(r)
    state.ontology.object_properties = kept_props
    for c in state.candidate_terms:
        c.accepted = c.term in kept_classes
    state.note(
        f"human_in_the_loop: rejected {len(rejected)} classes, "
        f"kept {len(kept_props)} object properties"
    )
    return state


def step_evaluation(state: WorkflowState) -> WorkflowState:
    """Evaluate the ontology (Fig. 7.7: *Evaluation*).

    * gold-standard comparison (precision/recall/F1) when gold sets are given;
    * data-driven assessment (coverage of corpus content words) always.
    """
    found_classes = {c.lower() for c in state.ontology.classes}
    found_rels = {(r.subject, r.predicate, r.object) for r in state.ontology.object_properties}

    evaluation: dict[str, Any] = {"ontology": state.ontology.summary()}
    if state.gold_classes:
        gold = {g.lower() for g in state.gold_classes}
        evaluation["class_prf"] = T.prf(found_classes, gold)
    if state.gold_relations:
        evaluation["relation_prf"] = T.prf(found_rels, state.gold_relations)

    # data-driven assessment: how much of the corpus vocabulary is covered
    corpus_terms = set(T.term_frequencies(state.tokens))
    onto_heads = {c.split()[-1].lower() for c in state.ontology.classes}
    coverage = len(corpus_terms & onto_heads) / len(corpus_terms) if corpus_terms else 0.0
    evaluation["data_driven"] = {"vocab_coverage": round(coverage, 3)}

    state.evaluation = evaluation
    state.note(f"evaluation: {evaluation}")
    return state


# --------------------------------------------------------------------------- #
# Step classes  (the networkx nodes)
# --------------------------------------------------------------------------- #
class WorkflowStep:
    """Base class for a pipeline step; instances are used as networkx nodes.

    A step bundles its identity, book-aligned metadata, mandatory/optional
    flag, a tool-parameter JSON-schema, and the single callable it invokes.
    """

    step_id: str = "step"
    label: str = "Step"
    description: str = ""
    mandatory: bool = True
    techniques: tuple[str, ...] = ()
    category: str = ""  # legend category in Fig. 7.7
    parameters: dict[str, Any] = {}  # JSON-schema "properties" for tool exposure
    func: Callable[..., WorkflowState]

    def __init__(self, **default_params: Any) -> None:
        # per-instance overrides of the tunable parameters
        self.default_params = default_params

    # The step *is* the invocation of one function ------------------------- #
    def run(self, state: WorkflowState, **params: Any) -> WorkflowState:
        merged = {**self.default_params, **params}
        return type(self).func(state, **merged)

    # Make the instance a stable, hashable networkx node ------------------- #
    def __hash__(self) -> int:
        return hash(self.step_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WorkflowStep) and other.step_id == self.step_id

    def __repr__(self) -> str:
        kind = "mandatory" if self.mandatory else "optional"
        return f"<{type(self).__name__} '{self.step_id}' ({kind})>"

    # Tool-spec helper (full schema assembled in tools.py) ----------------- #
    def tool_name(self) -> str:
        return self.func.__name__


class TextCleaningStep(WorkflowStep):
    step_id = "text_cleaning"
    label = "Text cleaning"
    description = "Tokenise, PoS-tag, parse and lemmatise the unstructured text."
    mandatory = True
    techniques = ("PoS tagging", "parsing", "lemmatisation")
    category = "Linguistic"
    func = staticmethod(step_text_cleaning)


class PreProcessingStep(WorkflowStep):
    step_id = "preprocessing"
    label = "Pre-processing"
    description = (
        "Statistical pre-processing: contrastive analysis (domain relevance "
        "and coverage) plus co-occurrence analysis."
    )
    mandatory = True
    techniques = (
        "C/NC-value",
        "contrastive analysis",
        "co-occurrence analysis",
        "latent semantic analysis",
        "clustering",
    )
    category = "Statistical"
    func = staticmethod(step_preprocessing)


class TermExtractionStep(WorkflowStep):
    step_id = "term_extraction"
    label = "Term (concept) extraction"
    description = "Extract candidate classes and term-composition subclass axioms."
    mandatory = True
    techniques = (
        "term composition",
        "formal concept analysis",
        "hierarchical clustering",
        "association-rule mining",
    )
    category = "Statistical/Logic"
    parameters = {
        "min_frequency": {
            "type": "integer",
            "minimum": 1,
            "default": 1,
            "description": "Minimum corpus frequency for a term to be kept.",
        },
        "top_k": {
            "type": ["integer", "null"],
            "default": None,
            "description": "Keep only the top-k highest scoring terms (null = all).",
        },
    }
    func = staticmethod(step_term_extraction)


class RelationExtractionStep(WorkflowStep):
    step_id = "relation_extraction"
    label = "Relation extraction"
    description = "Extract object-property candidates between known terms."
    mandatory = True
    techniques = ("syntactic analysis", "subcategorisation frames", "use of seed words")
    category = "Linguistic"
    func = staticmethod(step_relation_extraction)


class AxiomFindingStep(WorkflowStep):
    step_id = "axiom_finding"
    label = "Axiom finding"
    description = "Derive subsumption axioms via lexico-syntactic (Hearst) patterns."
    mandatory = False  # optional in the pipeline
    techniques = (
        "dependency analysis",
        "lexico-syntactic patterns",
        "inductive logic programming",
    )
    category = "Logic/Linguistic"
    func = staticmethod(step_axiom_finding)


class HumanInTheLoopStep(WorkflowStep):
    step_id = "human_in_the_loop"
    label = "Human-in-the-loop evaluation"
    description = "Domain-expert verification/pruning of candidate classes and properties."
    mandatory = False  # optional but strongly recommended
    techniques = ("human judgements",)
    category = "Evaluation"
    func = staticmethod(step_human_in_the_loop)


class EvaluationStep(WorkflowStep):
    step_id = "evaluation"
    label = "Evaluation"
    description = "Gold-standard comparison and data-driven assessment of the ontology."
    mandatory = True
    techniques = (
        "gold-standard comparison",
        "application use case",
        "data-driven assessment",
        "human judgements",
    )
    category = "Evaluation"
    func = staticmethod(step_evaluation)


# Registry of every known step class, keyed by step_id.
STEP_CLASSES: dict[str, type[WorkflowStep]] = {
    cls.step_id: cls
    for cls in (
        TextCleaningStep,
        PreProcessingStep,
        TermExtractionStep,
        RelationExtractionStep,
        AxiomFindingStep,
        HumanInTheLoopStep,
        EvaluationStep,
    )
}

# Canonical execution order of the full pipeline (Fig. 7.7).
PIPELINE_ORDER: tuple[str, ...] = (
    "text_cleaning",
    "preprocessing",
    "term_extraction",
    "relation_extraction",
    "axiom_finding",
    "human_in_the_loop",
    "evaluation",
)
