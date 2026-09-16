"""The retrieval funnel exposed as LangChain tools.

One thin wrapper per retriever stage. The wrappers do three jobs and no more:

* bind a single shared `GraphRagRetriever`, so every tool call hits the same graph and
  the same fitted embedder;
* return JSON-serialisable dicts, never objects, because whatever a tool returns is
  going straight into a model's context;
* keep the IRI on every record. The agent is instructed to cite IRIs, and it can only do
  that if the tools never drop them.

The docstrings are the tool descriptions the model actually reads, so they are written
for that reader: what the tool is for, and when to reach for a different one.
"""

from __future__ import annotations

from dataclasses import asdict

from langchain_core.tools import tool

from ..config import FalkorSettings
from .retriever import GraphRagRetriever


def build_tools(retriever: GraphRagRetriever | None = None,
                graph_name: str | None = None) -> list:
    """Build the tool list bound to one retriever."""
    r = retriever or GraphRagRetriever(FalkorSettings.from_env(graph_name=graph_name))

    @tool
    def ontology_overview() -> dict:
        """Describe the ontology graph: how many classes and modules it holds, which
        relationship types exist and how common each is, and the largest modules.

        Call this FIRST, before writing any Cypher. The relationship types in this graph
        are derived from the ontology's own property names, so guessing them produces
        queries that return nothing.
        """
        return r.schema_summary()

    @tool
    def search_concepts(query: str, k: int = 8) -> dict:
        """Find the classes most relevant to a phrase, using combined semantic and
        keyword search.

        This is the entry point for any question that names a business concept rather
        than an exact class. Returns candidate classes with their IRIs; follow up with
        get_concept for the details of whichever one fits.
        """
        anchors = [asdict(a) for a in r.anchor(query, k=k)]
        return {"query": query, "count": len(anchors), "candidates": anchors}

    @tool
    def get_concept(term: str) -> dict:
        """Get everything the ontology asserts about one class: its definition, synonyms,
        the module that defines it, its superclasses and subclasses, and the relations it
        participates in.

        Accepts a class name or an IRI. This is the tool to use for any "what is X" or
        "how is X defined" question, and its output is what an answer should cite.
        """
        card = r.concept_card(term)
        if card is None:
            return {"error": f"no class matches {term!r}",
                    "hint": "try search_concepts to find the right name first"}
        payload = asdict(card)
        payload["text"] = card.to_text()
        return payload

    @tool
    def get_neighbourhood(term: str, hops: int = 1) -> dict:
        """Get the classes and relationships surrounding one class, out to `hops` steps
        (1 to 3).

        Use this for questions about how a concept sits in its context -- what it connects
        to, what depends on it -- where a single concept card is not enough. Keep hops at
        1 unless the question genuinely spans several steps; the result grows fast.
        """
        return r.neighbourhood(term, hops=hops)

    @tool
    def get_ancestors(term: str) -> dict:
        """Get the subsumption chain above a class -- its superclass, that class's
        superclass, and so on up to the root.

        Use this for "what kind of thing is X", for comparing how two concepts are
        classified, and to check whether one class is a specialisation of another.
        """
        return r.ancestors(term)

    @tool
    def find_path(term_a: str, term_b: str, max_hops: int = 5) -> dict:
        """Find the shortest chain of relationships connecting two classes, if one exists.

        Use this for "how does X relate to Y". A negative result is informative and should
        be reported as such: it means the ontology asserts no connection within that many
        steps, not that no connection exists in the world.
        """
        return r.path_between(term_a, term_b, max_hops=max_hops)

    @tool
    def query_graph(cypher: str) -> dict:
        """Run a read-only Cypher query against the graph, for counting, filtering and
        aggregation that the other tools cannot express.

        The graph has (:Class {iri, name, short_name, definition, alt_labels, external,
        module_iri}) and (:Module {iri, name, path}), joined by [:SUBCLASS_OF] between
        classes, [:DEFINED_IN] from class to module, and one relationship type per
        ontology property carrying {name, quantifier, via}. Call ontology_overview first
        to see the real relationship types. Writes are refused.
        """
        return r.run_cypher(cypher)

    return [ontology_overview, search_concepts, get_concept, get_neighbourhood,
            get_ancestors, find_path, query_graph]
