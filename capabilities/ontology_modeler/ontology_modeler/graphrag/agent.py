"""The LangChain agent that answers questions over the projected ontology.

    from ontology_modeler.graphrag import build_agent
    agent = build_agent(graph_name="fibo")
    print(ask(agent, "What is a demand deposit account and how does it differ from a CD?"))

The agent is deliberately thin. All of the engineering is in the tools and in the system
prompt's grounding rules; the loop itself is stock `create_agent`. That split matters:
the tools are testable without a model (see `selftest`), so a bad answer can be traced to
either retrieval or generation rather than to an indivisible blob.

The grounding rules are the part worth reading. An ontology-backed agent's failure mode
is not inventing a fact out of nothing -- it is answering from the model's own knowledge
of finance while *appearing* to answer from FIBO, which is worse, because the citation
makes it look checked. Hence: no claim without a tool result behind it, IRIs on every
class mentioned, and an explicit "the ontology does not say" rather than a helpful guess.
"""

from __future__ import annotations

import os

from ..config import FalkorSettings
from .retriever import GraphRagRetriever
from .tools import build_tools

DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """\
You answer questions about a formal ontology that has been projected into a property \
graph. You have tools that read that graph. You have no other source of truth.

How to work:

1. Call `ontology_overview` once at the start of a session, before writing any Cypher. \
The relationship types in this graph come from the ontology's own property names; \
guessing them yields empty results that look like absence of fact.
2. Find the classes the question is about with `search_concepts`. Do not assume a class \
exists because the concept is familiar -- check.
3. Read them with `get_concept`. Use `get_ancestors` to say what kind of thing something \
is, `find_path` for how two things relate, `get_neighbourhood` for surrounding context, \
and `query_graph` only for counting, filtering and aggregation the others cannot express.

Grounding rules, which override any instinct to be helpful:

* Every factual claim in your answer must come from a tool result in this conversation. \
You know a great deal about finance; that knowledge is not evidence about what THIS \
ontology says, and must not be presented as if it were.
* Cite the IRI of every class you mention, in angle brackets, the first time it appears.
* Quote definitions from the ontology rather than paraphrasing them, and mark any \
paraphrase as yours.
* When the graph does not contain something, say so plainly -- "FIBO does not define X" \
or "no path within 5 hops" -- and stop. Do not fill the gap from background knowledge, \
and do not soften the gap into a maybe.
* Distinguish what is asserted from what you inferred. If you concluded something by \
reading two facts together, say which two.
* A class marked `external: true` is a placeholder for a class defined outside the loaded \
files. Report it as a reference, not as a definition.

Answer in prose. Be brief. Lead with the answer, then the evidence.\
"""


def build_agent(graph_name: str | None = None, model: str | None = None,
                retriever: GraphRagRetriever | None = None,
                system_prompt: str = SYSTEM_PROMPT):
    """Build the agent. Requires ANTHROPIC_API_KEY for the default model."""
    from langchain.agents import create_agent

    r = retriever or GraphRagRetriever(FalkorSettings.from_env(graph_name=graph_name))
    return create_agent(
        model or os.environ.get("ONTOLOGY_AGENT_MODEL", DEFAULT_MODEL),
        tools=build_tools(r),
        system_prompt=system_prompt,
        name="ontology-graphrag-agent",
    )


def ask(agent, question: str, max_iterations: int = 12) -> str:
    """Ask one question and return the final answer text."""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        {"recursion_limit": max_iterations * 2},
    )
    return result["messages"][-1].content


def trace(agent, question: str, max_iterations: int = 12) -> list[dict]:
    """Ask, and return the tool calls the agent made alongside the answer.

    The point of an ontology-grounded agent is that its evidence is inspectable; this is
    the function that makes it so. Use it in evaluation to check that the answer's claims
    actually appear in the retrieved records.
    """
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        {"recursion_limit": max_iterations * 2},
    )
    steps = []
    for message in result["messages"]:
        for call in getattr(message, "tool_calls", None) or []:
            steps.append({"tool": call["name"], "args": call["args"]})
        if getattr(message, "name", None) and getattr(message, "type", "") == "tool":
            steps.append({"tool_result_for": message.name,
                          "content": str(message.content)[:1200]})
    steps.append({"answer": result["messages"][-1].content})
    return steps


def selftest(graph_name: str | None = None, term: str = "deposit account") -> dict:
    """Exercise every tool against the live graph without calling a model.

    Retrieval and generation fail in different ways and want different fixes; this
    separates them. If the agent's answers are wrong but this passes, the problem is the
    prompt, not the graph.
    """
    r = GraphRagRetriever(FalkorSettings.from_env(graph_name=graph_name))
    tools = {t.name: t for t in build_tools(r)}
    out: dict[str, object] = {}

    overview = tools["ontology_overview"].invoke({})
    out["ontology_overview"] = {
        "classes": overview["node_labels"]["Class"],
        "modules": overview["node_labels"]["Module"],
        "relationship_types": len(overview["top_relationship_types"]),
    }

    search = tools["search_concepts"].invoke({"query": term, "k": 5})
    out["search_concepts"] = [(c["name"], c["found_by"]) for c in search["candidates"]]

    concept = tools["get_concept"].invoke({"term": term})
    out["get_concept"] = {"name": concept.get("name"), "iri": concept.get("iri"),
                          "subclasses": len(concept.get("subclasses", [])),
                          "relations_out": len(concept.get("relations_out", []))}

    out["get_ancestors"] = [a["name"] for a in
                            tools["get_ancestors"].invoke({"term": term}).get("ancestors", [])]
    out["get_neighbourhood"] = tools["get_neighbourhood"].invoke(
        {"term": term, "hops": 1}).get("triple_count")
    out["query_graph"] = tools["query_graph"].invoke(
        {"cypher": "MATCH (c:Class) WHERE c.external = false RETURN count(c) AS n"})
    out["write_refused"] = tools["query_graph"].invoke(
        {"cypher": "MATCH (c:Class) SET c.name = 'x' RETURN c"})
    return out
