"""Building agents: one loop, or an explicitly decomposed pipeline.

Two constructions, because the course argues about the choice between them.

:func:`build_agent` is the single ReAct-style loop — one model, one tool belt,
one prompt. It is the right default: fewer moving parts, and the model decides
the order of work.

:func:`build_pipeline` is **functional decomposition** — plan, act, then
criticise, as separate LangGraph nodes with separate prompts. It costs more and
constrains the model, and it buys three things worth having: each stage can be
evaluated (and optimised) on its own, the critic stage catches unsupported
claims that a single loop happily emits, and the trajectory is legible.

The lab has students measure the trade rather than take a position on faith:
same task, same tools, same metric, compare score *and* tool cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from oe_course.llm import chat_model
from oe_course.tools import ToolContext, build_toolset

__all__ = ["AgentRun", "build_agent", "run_agent", "message_text", "build_pipeline",
           "TRIAGE_SYSTEM_PROMPT"]


TRIAGE_SYSTEM_PROMPT = """\
You are an ontology engineer triaging a submitted artefact.

Procedure:
1. Load the artefact by name.
2. Gather evidence with the analysis tools before forming any opinion.
3. Answer with the artefact's spectrum level, using exactly one of:
   controlled-vocabulary, taxonomy, thesaurus, formal-ontology.
4. List every defect the scanner reported, by its exact identifier.
5. Justify both with the numbers you actually observed.

Never report a defect the scanner did not return.
"""


@dataclass
class AgentRun:
    """One episode: the final answer plus everything it cost."""

    answer: str
    messages: list = field(default_factory=list)
    context: ToolContext | None = None

    @property
    def log(self):
        return self.context.log if self.context else None

    def summary(self) -> dict:
        out = {"answer_chars": len(self.answer), "turns": len(self.messages)}
        if self.log:
            out.update(self.log.summary())
        return out


def build_agent(ctx: ToolContext | None = None, *, system_prompt: str = TRIAGE_SYSTEM_PROMPT,
                model=None, tools: list | None = None):
    """A tool-calling agent over the ontology toolset.

    Returns ``(agent, ctx)``; keep ``ctx`` — its call log is the episode record
    the MDP and the cost model both read.
    """
    from langchain.agents import create_agent

    ctx = ctx or ToolContext()
    tools = tools if tools is not None else build_toolset(ctx)
    agent = create_agent(model or chat_model(), tools, system_prompt=system_prompt)
    return agent, ctx


def run_agent(agent, ctx: ToolContext, task: str, *, recursion_limit: int = 25) -> AgentRun:
    """Run one episode and package the result."""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": recursion_limit},
    )
    messages = result.get("messages", [])
    answer = ""
    for message in reversed(messages):
        if getattr(message, "type", "") != "ai":
            continue
        answer = message_text(message)
        if answer:
            break
    return AgentRun(answer=answer, messages=messages, context=ctx)


def message_text(message) -> str:
    """The visible text of a chat message.

    Claude's replies can be a list of content blocks (thinking, text, tool use);
    only the ``text`` blocks are the answer.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(p for p in parts if p).strip()


# --------------------------------------------------------------------------- #
# Functional decomposition: plan -> act -> criticise
# --------------------------------------------------------------------------- #
def build_pipeline(ctx: ToolContext | None = None, *, model=None):
    """A three-stage LangGraph pipeline over the same tools.

    Stages are separate so each can be prompted, evaluated and optimised
    independently — the practical reason to decompose at all.
    """
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    ctx = ctx or ToolContext()
    tools = {t.name: t for t in build_toolset(ctx)}
    llm = model or chat_model()

    class State(TypedDict, total=False):
        task: str
        artefact: str
        plan: list
        evidence: dict
        draft: dict
        critique: str
        answer: dict

    def plan(state: State) -> State:
        """Decide which evidence this artefact needs (cheap, deterministic here)."""
        return {"plan": ["graph_metrics", "spectrum_position", "scan_smells"]}

    def act(state: State) -> State:
        tools["load_artefact"].invoke({"name": state["artefact"]})
        evidence = {}
        for step in state.get("plan", []):
            evidence[step] = json.loads(tools[step].invoke({}))
        return {"evidence": evidence}

    def draft(state: State) -> State:
        evidence = state["evidence"]
        return {
            "draft": {
                "level": evidence["spectrum_position"]["level"],
                "smells": sorted(
                    {f["smell"] for f in evidence["scan_smells"]}
                ),
                "justification": "; ".join(evidence["spectrum_position"]["evidence"]),
            }
        }

    def critique(state: State) -> State:
        """Reject claims the gathered evidence does not support.

        This is the stage that earns the decomposition: it is a *verification*
        step with access to the raw tool output, so a hallucinated defect id
        cannot survive it.
        """
        found = {f["smell"] for f in state["evidence"]["scan_smells"]}
        claimed = set(state["draft"]["smells"])
        unsupported = sorted(claimed - found)
        answer = dict(state["draft"])
        answer["smells"] = sorted(claimed & found)
        note = (
            f"dropped unsupported claims: {unsupported}" if unsupported else "all claims supported"
        )
        return {"critique": note, "answer": answer}

    graph = StateGraph(State)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("draft", draft)
    graph.add_node("critique", critique)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "draft")
    graph.add_edge("draft", "critique")
    graph.add_edge("critique", END)
    return graph.compile(), ctx
