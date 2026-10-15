"""Tool-calling agents: one loop over a tool belt, and what an episode cost.

Chapter 3 · the review agent of the problem set calls the chapter's reasoner as a
tool. Until now every Claude call in the course was a DSPy program (one prompt, one
structured answer); an agent is a *loop*: the model decides which tool to call, reads
the result, and decides again, until it answers.

:func:`build_agent` is the single ReAct-style loop of the original course: one model,
one tool belt, one system prompt (LangChain's ``create_agent``). :func:`run_agent` runs
one episode and keeps every message, because the transcript is the evidence: which
tools were called, in what order, and what the episode cost (:func:`chat_usage`).

The original module also had a fixed, three-stage LangGraph pipeline (plan → act →
criticise) over the Chapter 1 registry tools. Chapter 3's problem set builds its own
pipeline with a critic, over the reasoner, so the comparison the original made —
a loop that chooses its tools versus a fixed procedure with a verification stage —
is made on this chapter's task.

The chat model is ``ChatAnthropic`` on the course's task model (the LangChain side of
the original ``llm`` module, which arrives here because agents are its only user).
Every turn of an agent episode is a billed request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from agentlab import llm
from agentlab.tools import ToolCallLog

INTRODUCED_IN = 3

__all__ = ["CHAT_MODEL", "chat_model", "chat_usage", "AgentRun", "build_agent", "run_agent",
           "message_text"]

#: The LangChain model id: the DSPy task model without LiteLLM's provider prefix.
CHAT_MODEL = os.environ.get("OE_COURSE_CHAT_MODEL",
                            llm.DSPY_MODEL.split("/", 1)[-1])


def chat_model(**kwargs):
    """The LangChain chat model: ``ChatAnthropic`` on the course model."""
    from langchain_anthropic import ChatAnthropic

    llm.require_credentials()
    params: dict[str, Any] = {"model": CHAT_MODEL, "max_tokens": llm.MAX_TOKENS}
    params.update(kwargs)
    return ChatAnthropic(**params)


def chat_usage(messages: Iterable, model: str | None = None) -> dict:
    """Sum the token usage of the AI messages in a LangChain transcript, and price it."""
    input_tokens = output_tokens = turns = 0
    for message in messages:
        meta = getattr(message, "usage_metadata", None)
        if not meta:
            continue
        turns += 1
        input_tokens += int(meta.get("input_tokens", 0) or 0)
        output_tokens += int(meta.get("output_tokens", 0) or 0)
    model = (model or CHAT_MODEL).split("/", 1)[-1]
    price_in, price_out = llm.PRICES_PER_MTOK.get(model, (0.0, 0.0))
    usd = (input_tokens * price_in + output_tokens * price_out) / 1e6
    return {"model_turns": turns, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "usd_estimate": round(usd, 4)}


@dataclass
class AgentRun:
    """One episode: the final answer plus everything it cost."""

    answer: str
    messages: list = field(default_factory=list)
    log: ToolCallLog | None = None

    def summary(self) -> dict:
        out = {"answer_chars": len(self.answer), "turns": len(self.messages)}
        if self.log:
            out.update(self.log.summary())
        return out


def build_agent(tools: list, *, system_prompt: str, model=None):
    """A tool-calling agent over ``tools`` (a list of LangChain tools)."""
    from langchain.agents import create_agent

    return create_agent(model or chat_model(), tools, system_prompt=system_prompt)


def run_agent(agent, task: str, *, log: ToolCallLog | None = None,
              recursion_limit: int = 25) -> AgentRun:
    """Run one episode and package the result; ``log`` is the toolset's call log."""
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
    return AgentRun(answer=answer, messages=messages, log=log)


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
