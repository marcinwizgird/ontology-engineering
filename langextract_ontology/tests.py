"""Functional tests. Offline, deterministic, no API key, no network.

Run with::

    python -m langextract_ontology.tests

They exercise the real pipeline end to end against the simulated model, so a
regression in chunking, resolution, span alignment or OWL rendering fails
here rather than in a notebook.
"""

from __future__ import annotations

import json
import sys
import warnings

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS, XSD

from . import owl, schema as S
from .demo import CORPUS
from .extract import extract_ontology
from .providers import SimulatedOntologyModel, resolve_model

warnings.filterwarnings("ignore")

_FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        _FAILURES.append(message)


# --------------------------------------------------------------------------- #
def test_examples_are_verbatim() -> None:
    """LangExtract can only ground quotes it can find; so must the examples."""
    print("few-shot examples")
    for i, example in enumerate(S.EXAMPLES):
        for extraction in example.extractions:
            check(
                extraction.extraction_text in example.text,
                f"example#{i} {extraction.extraction_class!r} quote is verbatim",
            )


def test_simulator_envelope() -> None:
    """The simulator must answer in the JSON envelope LangExtract parses."""
    print("simulator output envelope")
    model = SimulatedOntologyModel()
    prompt = "instructions\n\nQ: A pump is a device that moves fluid.\nA:"
    output = next(iter(model.infer([prompt])))[0].output
    check(output.startswith("```json"), "output is fenced JSON")
    payload = json.loads(output.removeprefix("```json").removesuffix("```"))
    check("extractions" in payload, "envelope has an 'extractions' key")
    kinds = {k for e in payload["extractions"] for k in e if not k.endswith("_attributes")}
    check(kinds <= set(S.EXTRACTION_CLASSES), f"only known extraction classes: {kinds}")


def test_extraction_is_grounded() -> None:
    print("extraction grounding")
    result = extract_ontology(CORPUS, model_id="simulated", document_id="t")
    check(len(result.items) > 10, f"found {len(result.items)} extractions")
    check(
        all(i.grounded for i in result.items),
        "every extraction carries a character interval",
    )
    check(
        all(i.quote in CORPUS for i in result.items),
        "every quote is verbatim source text",
    )
    check(
        all(0 <= i.start < i.end <= len(CORPUS) for i in result.items),
        "every span lies inside the document",
    )
    labels = set(result.class_labels())
    for expected in ("centrifugal pump", "impeller", "valve", "slurry pump"):
        check(expected in labels, f"class {expected!r} was found")
    subsumptions = {(i.attr("subclass"), i.attr("superclass")) for i in result.subsumptions()}
    check(
        ("centrifugal pump", "rotodynamic pump") in subsumptions,
        "copular definition yields a subsumption",
    )
    check(
        ("slurry pump", "centrifugal pump") in subsumptions,
        "coordination yields one subsumption per conjunct",
    )
    return result


def test_owl_rendering(result) -> None:
    print("OWL rendering")
    graph = owl.to_graph(result)
    ns = owl.OwlBuilder(result).ns
    pump, valve = ns["Pump"], ns["Valve"]

    check(
        (ns["CentrifugalPump"], RDFS.subClassOf, ns["RotodynamicPump"]) in graph,
        "subsumption is asserted as rdfs:subClassOf",
    )
    check((pump, OWL.disjointWith, valve) in graph, "disjointness is asserted")
    check(
        (ns["serialNumber"], RDFS.range, XSD.string) in graph,
        "data property carries its xsd range",
    )
    restrictions = list(graph.subjects(OWL.onProperty, ns["hasImpeller"]))
    check(bool(restrictions), "cardinality axiom produced an owl:Restriction")
    if restrictions:
        check(
            (restrictions[0], OWL.qualifiedCardinality, Literal(
                "1", datatype=XSD.nonNegativeInteger)) in graph,
            "the restriction is a qualified cardinality of 1",
        )

    axioms = list(graph.subjects(owl.RDF.type, OWL.Axiom))
    check(bool(axioms), f"{len(axioms)} axioms are reified with provenance")
    check(
        all(graph.value(a, owl.LXO.exactQuote) is not None for a in axioms),
        "every reified axiom carries its source quote",
    )
    check(
        all(graph.value(a, owl.PROV.wasQuotedFrom) is not None for a in axioms),
        "every reified axiom points at the source document",
    )

    justifications = owl.provenance_of(graph, ns["BoilerFeedPump"], RDFS.subClassOf)
    check(bool(justifications), "a subsumption can be traced back to its sentence")
    if justifications:
        check(
            justifications[0]["quote"] in CORPUS,
            "the recovered justification is real source text",
        )
    return graph


def test_reasoner_accepts_it(graph) -> None:
    """A real OWL 2 RL reasoner must consume the output and entail from it."""
    print("OWL 2 RL entailment")
    try:
        import owlrl
    except ImportError:
        print("  skip owlrl not installed")
        return
    expanded = graph
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(expanded)
    base = "https://example.org/onto/"
    check(
        (URIRef(base + "BoilerFeedPump"), RDFS.subClassOf, URIRef(base + "RotodynamicPump"))
        in expanded,
        "subsumption is transitive after reasoning",
    )


def test_workflow_integration() -> None:
    print("bottomup_ontology integration")
    from bottomup_ontology import run_workflow
    from bottomup_ontology.state import WorkflowState
    from bottomup_ontology.workflow import execution_plan

    from .pipeline import LangExtractTermStep, build_langextract_workflow

    graph = build_langextract_workflow(
        step_params={"term_extraction": {"model_id": "simulated"}}
    )
    plan = execution_plan(graph)
    check(
        plan == [
            "text_cleaning", "preprocessing", "term_extraction",
            "relation_extraction", "axiom_finding", "human_in_the_loop",
            "evaluation",
        ],
        f"the LangExtract steps occupy the Fig. 7.7 positions: {plan}",
    )
    node = next(n for n in graph.nodes if getattr(n, "step_id", None) == "term_extraction")
    check(isinstance(node, LangExtractTermStep), "term_extraction is the LangExtract step")

    state = run_workflow(graph, WorkflowState(documents=[CORPUS]))
    summary = state.ontology.summary()
    check(summary["classes"] > 5, f"workflow produced {summary['classes']} classes")
    check(summary["subclass_axioms"] > 2, f"{summary['subclass_axioms']} subclass axioms")
    check(bool(state.ontology.axioms), "constraints were recorded as axioms")
    check("evaluation" in state.evaluation or bool(state.evaluation), "evaluation ran")


def test_model_selection() -> None:
    print("model selection")
    check(
        type(resolve_model("simulated")).__name__ == "SimulatedOntologyModel",
        "'simulated' selects the offline model",
    )
    check(resolve_model("gemini-2.5-flash") is None, "unknown ids defer to LangExtract")
    from langextract.providers import registry

    check(
        registry.resolve("claude-opus-5").__name__ == "AnthropicLanguageModel",
        "claude-* ids resolve to the Anthropic provider",
    )


def main() -> int:
    test_examples_are_verbatim()
    test_simulator_envelope()
    result = test_extraction_is_grounded()
    graph = test_owl_rendering(result)
    test_reasoner_accepts_it(graph)
    test_workflow_integration()
    test_model_selection()

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILED:")
        for message in _FAILURES:
            print(f"  - {message}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
