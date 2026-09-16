"""Plug LangExtract into the existing bottom-up workflow.

``bottomup_ontology`` implements Keet, *Ontology Engineering* (2nd ed.),
Fig. 7.7 with statistical and lexico-syntactic techniques.  The three steps in
the middle of that pipeline — term extraction, relation extraction, axiom
finding — are exactly the ones an LLM extractor can do better, and the ones
LangExtract grounds in source spans.

The steps below are **drop-in replacements**: they keep the same ``step_id``
values, so ``bottomup_ontology.workflow.build_graph`` wires them into the same
DAG positions, ``WorkflowStep.__eq__`` still treats them as the same node, and
text cleaning / pre-processing / evaluation are untouched.  Swapping technique
families is then a one-line change in the graph construction, which is the
comparison the notebooks want to make.

One LLM call serves all three steps: ``step_langextract_terms`` performs the
extraction and caches the grounded result on ``state.config``; the other two
drain that cache.  Running them out of order is safe — each one extracts on
demand if the cache is empty.
"""

from __future__ import annotations

from typing import Any

from bottomup_ontology.state import CandidateTerm, Relation, WorkflowState
from bottomup_ontology.steps import WorkflowStep

from . import owl
from .extract import OntologyExtraction, extract_ontology

#: Key under which the grounded extraction is cached on ``state.config``.
STATE_KEY = "langextract_extraction"


# --------------------------------------------------------------------------- #
# The shared extraction
# --------------------------------------------------------------------------- #
def _extraction(
    state: WorkflowState,
    model_id: str | None = None,
    max_char_buffer: int = 1200,
    extraction_passes: int = 1,
) -> OntologyExtraction:
    """Return the cached extraction, running it once if needed."""
    cached = state.config.get(STATE_KEY)
    if isinstance(cached, OntologyExtraction):
        return cached

    text = "\n\n".join(state.documents)
    result = extract_ontology(
        text,
        model_id=model_id,
        document_id=state.config.get("document_id", "corpus"),
        max_char_buffer=max_char_buffer,
        extraction_passes=extraction_passes,
    )
    state.config[STATE_KEY] = result
    state.note(
        f"langextract: {result.summary()['extractions']} extractions "
        f"({result.summary()['grounded']} grounded) via {result.model_name}"
    )
    return result


# --------------------------------------------------------------------------- #
# Step functions (reusable as agentic tools, like the ones in steps.py)
# --------------------------------------------------------------------------- #
def step_langextract_terms(
    state: WorkflowState,
    model_id: str | None = None,
    max_char_buffer: int = 1200,
    extraction_passes: int = 1,
    min_support: int = 1,
) -> WorkflowState:
    """Candidate classes and subsumption, extracted and span-grounded by an LLM.

    Replaces ``step_term_extraction``.  ``min_support`` keeps only labels the
    extractor mentioned at least that many times, which is the LLM analogue of
    the frequency cut-off in the statistical version of this step.
    """
    result = _extraction(state, model_id, max_char_buffer, extraction_passes)

    support: dict[str, int] = {}
    for label in result.class_labels():
        support[label] = 0
    for item in result.items:
        for value in item.attributes.values():
            key = str(value).strip().lower()
            if key in support:
                support[key] += 1

    state.candidate_terms = [
        CandidateTerm(term=label, frequency=count, score=float(count))
        for label, count in sorted(support.items(), key=lambda kv: (-kv[1], kv[0]))
        if count >= min_support
    ]
    kept = {t.term for t in state.candidate_terms}
    for term in kept:
        state.ontology.add_class(term)

    for item in result.subsumptions():
        sub, sup = item.attr("subclass").lower(), item.attr("superclass").lower()
        if sub and sup and sub != sup and sub in kept and sup in kept:
            state.ontology.add_subclass(sub, sup)

    state.note(
        f"langextract_terms: {len(state.candidate_terms)} candidate classes, "
        f"{len(state.ontology.subclass_of)} subsumption axioms"
    )
    return state


def step_langextract_relations(
    state: WorkflowState,
    model_id: str | None = None,
    max_char_buffer: int = 1200,
    extraction_passes: int = 1,
) -> WorkflowState:
    """Object properties with domain and range, replacing ``step_relation_extraction``."""
    result = _extraction(state, model_id, max_char_buffer, extraction_passes)
    known = {t.term for t in state.candidate_terms} or set(result.class_labels())

    seen: set[tuple[str, str, str]] = set()
    for item in result.object_properties():
        domain = item.attr("domain").lower()
        rng = item.attr("range").lower()
        prop = item.attr("property") or "relatedTo"
        if not domain or not rng or domain not in known or rng not in known:
            continue
        triple = (domain, prop, rng)
        if triple in seen:
            continue
        seen.add(triple)
        relation = Relation(subject=domain, predicate=prop, object=rng)
        state.candidate_relations.append(relation)
        state.ontology.add_object_property(relation)

    state.note(f"langextract_relations: {len(state.candidate_relations)} object properties")
    return state


def step_langextract_axioms(
    state: WorkflowState,
    model_id: str | None = None,
    max_char_buffer: int = 1200,
    extraction_passes: int = 1,
) -> WorkflowState:
    """Constraints, data properties and individuals, replacing ``step_axiom_finding``.

    ``Ontology.axioms`` holds human-readable strings, so each axiom is recorded
    with the quote that licensed it — the full RDF rendering, with the same
    provenance as machine-readable annotations, is in :mod:`langextract_ontology.owl`.
    """
    result = _extraction(state, model_id, max_char_buffer, extraction_passes)

    for item in result.axioms():
        expression = item.attr("expression") or (
            f"{item.attr('axiom_type')}({item.attr('subject')}, {item.attr('filler')})"
        )
        state.ontology.axioms.append(f'{expression}   # "{item.quote}"')
    for item in result.data_properties():
        state.ontology.axioms.append(
            f"{item.attr('property')}: {item.attr('domain')} -> "
            f'{item.attr("datatype")}   # "{item.quote}"'
        )
    for item in result.individuals():
        state.ontology.axioms.append(
            f'{item.attr("label")} : {item.attr("type")}   # "{item.quote}"'
        )

    state.note(f"langextract_axioms: {len(state.ontology.axioms)} axioms recorded")
    return state


# --------------------------------------------------------------------------- #
# Step classes (the networkx nodes)
# --------------------------------------------------------------------------- #
class LangExtractTermStep(WorkflowStep):
    step_id = "term_extraction"  # same id => drop-in replacement in the DAG
    label = "Term (concept) extraction [LangExtract]"
    description = (
        "Extract candidate classes and subsumption axioms with an LLM, keeping "
        "the source span that licensed each one."
    )
    mandatory = True
    techniques = ("LLM extraction", "few-shot prompting", "source grounding")
    category = "Statistical/Logic"
    parameters = {
        "model_id": {
            "type": ["string", "null"],
            "default": None,
            "description": (
                "null/'auto' = Claude if credentials exist else the offline "
                "simulator; 'simulated' forces offline; 'claude-*', 'gemini-*', "
                "'gpt-*' select a provider."
            ),
        },
        "extraction_passes": {
            "type": "integer",
            "minimum": 1,
            "default": 1,
            "description": "Repeat the extraction and merge findings to raise recall.",
        },
        "min_support": {
            "type": "integer",
            "minimum": 0,
            "default": 1,
            "description": "Drop class labels mentioned fewer times than this.",
        },
    }
    func = staticmethod(step_langextract_terms)


class LangExtractRelationStep(WorkflowStep):
    step_id = "relation_extraction"
    label = "Relation extraction [LangExtract]"
    description = "Extract object properties with domain and range from the same LLM pass."
    mandatory = True
    techniques = ("LLM extraction", "source grounding")
    category = "Linguistic"
    parameters = {}
    func = staticmethod(step_langextract_relations)


class LangExtractAxiomStep(WorkflowStep):
    step_id = "axiom_finding"
    label = "Axiom finding [LangExtract]"
    description = (
        "Record disjointness, cardinality and other constraints, plus data "
        "properties and individuals, each with its source quote."
    )
    mandatory = False
    techniques = ("LLM extraction", "lexico-syntactic patterns", "source grounding")
    category = "Logic/Linguistic"
    parameters = {}
    func = staticmethod(step_langextract_axioms)


LANGEXTRACT_STEP_CLASSES: dict[str, type[WorkflowStep]] = {
    cls.step_id: cls
    for cls in (LangExtractTermStep, LangExtractRelationStep, LangExtractAxiomStep)
}


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #
def build_langextract_workflow(
    include_axiom_finding: bool = True,
    include_human_in_the_loop: bool = True,
    step_params: dict[str, dict[str, Any]] | None = None,
):
    """The Fig. 7.7 pipeline with its three extraction steps done by an LLM.

    Text cleaning, pre-processing and evaluation keep their original
    implementations — the first two still produce the tokens the evaluation
    step measures vocabulary coverage against.

    Note that ``workflow.add_optional_step`` / ``remove_optional_step`` rebuild
    from the *default* ``STEP_CLASSES`` registry and would therefore swap the
    LangExtract nodes back out; re-call this function instead.
    """
    from bottomup_ontology import workflow as wf

    step_params = step_params or {}
    selected: list[tuple[str, type[WorkflowStep] | None]] = [
        ("text_cleaning", None),
        ("preprocessing", None),
        ("term_extraction", LangExtractTermStep),
        ("relation_extraction", LangExtractRelationStep),
    ]
    if include_axiom_finding:
        selected.append(("axiom_finding", LangExtractAxiomStep))
    if include_human_in_the_loop:
        selected.append(("human_in_the_loop", None))
    selected.append(("evaluation", None))

    steps = [
        (cls(**step_params.get(sid, {})) if cls else wf.make_step(sid, **step_params.get(sid, {})))
        for sid, cls in selected
    ]
    return wf.build_graph(steps)


def turtle_from_state(state: WorkflowState, base: str = owl.DEFAULT_BASE) -> str:
    """Serialise the grounded extraction cached on ``state`` as OWL Turtle.

    ``Ontology.to_turtle()`` in ``bottomup_ontology`` renders the workflow's own
    lightweight artifact; this renders the richer, provenance-annotated graph.
    """
    result = state.config.get(STATE_KEY)
    if not isinstance(result, OntologyExtraction):
        raise ValueError(
            "no LangExtract result on this state - run the LangExtract steps first"
        )
    return owl.to_turtle(result, base=base)
