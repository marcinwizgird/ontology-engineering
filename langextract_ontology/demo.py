"""End-to-end demonstration: text -> grounded extractions -> OWL -> workflow.

Run it with::

    python -m langextract_ontology                 # offline simulator, free
    python -m langextract_ontology --model claude-opus-5
    python -m langextract_ontology --model gemini-2.5-flash

Output is ASCII only: the Windows console in this workspace is cp1252.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from rdflib.namespace import RDFS

from . import owl
from .extract import extract_ontology

#: A small maintenance-engineering corpus, written to exercise every
#: extraction class: definitions, coordinated subsumption, relations, a data
#: property, a cardinality constraint, a disjointness, and an individual.
CORPUS = """\
A centrifugal pump is a rotodynamic pump that moves fluid through a piping system.
Rotating equipment such as pumps, compressors and turbines requires condition monitoring.
Boiler feed pumps and slurry pumps are types of centrifugal pump.
Every pump must have exactly one impeller.
Each pump has a serial number recorded as text.
A maintenance engineer supervises the overhaul of a pump.
No pump is a valve.
P-101 is a centrifugal pump.
"""

ARTIFACTS = pathlib.Path(__file__).parent / "artifacts"


def _rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def run(model_id: str | None, write: bool = True) -> int:
    _rule("1. Corpus")
    print(CORPUS)

    _rule("2. Grounded extraction")
    result = extract_ontology(CORPUS, model_id=model_id, document_id="maintenance-notes")
    for key, value in result.summary().items():
        print(f"  {key:<16} {value}")

    _rule("3. What was asserted, and what licensed it")
    print(f"  {'kind':<16} {'assertion':<52} {'span':<10} alignment")
    for row in result.provenance_table():
        print(
            f"  {row['kind']:<16} {row['assertion'][:52]:<52} "
            f"{row['span']:<10} {row['alignment']}"
        )

    _rule("4. OWL with per-axiom provenance")
    graph = owl.to_graph(result)
    turtle = graph.serialize(format="turtle")
    print(f"  {len(graph)} triples; first 20 lines:")
    for line in turtle.splitlines()[:20]:
        print(f"  | {line}")

    _rule("5. Auditing one axiom: why is a boiler feed pump a centrifugal pump?")
    subject = owl.OwlBuilder(result).ns[owl.class_ident("boiler feed pump")]
    justifications = owl.provenance_of(graph, subject, RDFS.subClassOf)
    if justifications:
        for row in justifications:
            print(f"  target : {row['target']}")
            print(f"  quote  : \"{row['quote']}\"")
            print(f"  span   : {row['start']}-{row['end']}  ({row['alignment']})")
            print(f"  model  : {row['model']}")
    else:
        print("  (the extractor did not assert it for this run)")

    _rule("6. The same extraction inside the Fig. 7.7 workflow")
    from bottomup_ontology import run_workflow
    from bottomup_ontology.state import WorkflowState

    from .pipeline import build_langextract_workflow

    graph_wf = build_langextract_workflow(
        step_params={"term_extraction": {"model_id": model_id}}
    )
    state = WorkflowState(documents=[CORPUS], config={"document_id": "maintenance-notes"})
    state = run_workflow(graph_wf, state)
    print("  plan:", " -> ".join(n.step_id for n in graph_wf.nodes if hasattr(n, "step_id")))
    for entry in state.log:
        print(f"  {entry}")
    print(f"  ontology: {state.ontology.summary()}")

    if write:
        ARTIFACTS.mkdir(exist_ok=True)
        (ARTIFACTS / "maintenance.ttl").write_text(turtle, encoding="utf-8")
        result.to_json(ARTIFACTS / "maintenance_extractions.json")
        print()
        print(f"  wrote {ARTIFACTS / 'maintenance.ttl'}")
        print(f"  wrote {ARTIFACTS / 'maintenance_extractions.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model",
        default="simulated",
        help=(
            "Model id: 'simulated' (default, offline and free), 'auto', "
            "'claude-opus-5', 'gemini-2.5-flash', 'gpt-4o', an Ollama tag."
        ),
    )
    parser.add_argument("--no-write", action="store_true", help="do not write artifacts")
    args = parser.parse_args(argv)
    return run(args.model, write=not args.no_write)


if __name__ == "__main__":
    sys.exit(main())
