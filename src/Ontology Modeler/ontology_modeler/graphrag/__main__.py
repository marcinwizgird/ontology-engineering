"""CLI for the GraphRAG layer.

    python -m ontology_modeler.graphrag [--graph-name fibo] selftest [--term "deposit account"]
    python -m ontology_modeler.graphrag [--graph-name fibo] search "deposit account"
    python -m ontology_modeler.graphrag [--graph-name fibo] card "demand deposit account"
    python -m ontology_modeler.graphrag [--graph-name fibo] ask [--trace] "question"

`selftest`, `search` and `card` need no API key -- they exercise the retrieval funnel
alone. Only `ask` runs a model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ..config import FalkorSettings
from .agent import ask as ask_agent, build_agent, selftest, trace
from .retriever import GraphRagRetriever


def _retriever(args) -> GraphRagRetriever:
    return GraphRagRetriever(FalkorSettings.from_env(graph_name=args.graph_name))


def _cmd_selftest(args) -> int:
    print(json.dumps(selftest(args.graph_name, args.term), indent=2, default=str))
    return 0


def _cmd_search(args) -> int:
    for anchor in _retriever(args).anchor(" ".join(args.query), k=args.k):
        print(f"  {anchor.score:.5f}  [{anchor.found_by:8}]  {anchor.name}\n"
              f"             {anchor.iri}")
    return 0


def _cmd_card(args) -> int:
    card = _retriever(args).concept_card(" ".join(args.term))
    if card is None:
        print("no match", file=sys.stderr)
        return 1
    print(card.to_text())
    return 0


def _cmd_ask(args) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set. The retrieval tools work without it:\n"
              "       python -m ontology_modeler.graphrag --graph-name "
              f"{args.graph_name or 'ontology'} selftest", file=sys.stderr)
        return 1
    agent = build_agent(graph_name=args.graph_name, model=args.model)
    question = " ".join(args.question)
    if args.trace:
        for step in trace(agent, question):
            print(json.dumps(step, indent=2, default=str))
        return 0
    print(ask_agent(agent, question))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ontology_modeler.graphrag",
                                     description="GraphRAG over a projected ontology.")
    parser.add_argument("--graph-name", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p_self = sub.add_parser("selftest", help="exercise every tool; no model needed")
    p_self.add_argument("--term", default="deposit account")
    p_self.set_defaults(func=_cmd_selftest)

    p_search = sub.add_parser("search", help="hybrid anchor search")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("-k", type=int, default=8)
    p_search.set_defaults(func=_cmd_search)

    p_card = sub.add_parser("card", help="print one concept card")
    p_card.add_argument("term", nargs="+")
    p_card.set_defaults(func=_cmd_card)

    p_ask = sub.add_parser("ask", help="ask the agent (needs ANTHROPIC_API_KEY)")
    p_ask.add_argument("question", nargs="+")
    p_ask.add_argument("--model", default=None)
    p_ask.add_argument("--trace", action="store_true", help="show the tool calls too")
    p_ask.set_defaults(func=_cmd_ask)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
