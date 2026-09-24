"""LLM clients for the course — Anthropic, through LangChain and through DSPy.

``chat_model()``
    A LangChain ``ChatAnthropic``. Supports ``bind_tools``, so the LangChain /
    LangGraph agents in :mod:`oe_course.agents` run a real tool-calling loop.

``dspy_lm()`` / ``configure_dspy()`` / ``reflection_lm()``
    DSPy ``LM`` objects routed through LiteLLM to Anthropic. The reflection LM is
    the one GEPA uses to *propose* instructions; it is kept separate so an
    assignment can price the two roles independently.

Every call is billed. Two helpers make that visible rather than a surprise at
the end of the month: :func:`spend` totals a DSPy LM's history, and
:func:`chat_usage` totals the ``usage_metadata`` of a LangChain transcript. The
assignments ask for a cost line next to every score, because a score without
its cost is not an engineering result.

DSPy caches identical requests on disk by default, so re-running a notebook
cell with unchanged prompts is free. Clear the cache (or change the prompt) when
you want a fresh sample.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable

from oe_course import config

__all__ = [
    "chat_model", "dspy_lm", "configure_dspy", "reflection_lm",
    "spend", "meter", "chat_usage", "PRICES_PER_MTOK", "estimate_cost",
]

#: USD per million tokens (input, output), first-party API list prices.
#: Used only for *estimates* of LangChain runs; DSPy runs report LiteLLM's cost.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def _bare(model: str) -> str:
    return model.split("/", 1)[-1]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """List-price estimate in USD; ``nan`` for a model not in the table."""
    prices = PRICES_PER_MTOK.get(_bare(model))
    if prices is None:
        return float("nan")
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


# --------------------------------------------------------------------------- #
# DSPy side
# --------------------------------------------------------------------------- #
def dspy_lm(model: str | None = None, **kwargs):
    """A DSPy LM on Anthropic.

    temperature=1.0 is the accepted default on claude-opus-5; DSPy's usual 0.0
    would be rejected as a non-default sampling parameter.
    """
    import dspy

    config.require_credentials()
    params = {"temperature": 1.0, "max_tokens": config.MAX_TOKENS}
    params.update(kwargs)
    return dspy.LM(model or config.DSPY_MODEL, **params)


def configure_dspy(model: str | None = None, **kwargs):
    """Install an Anthropic LM as the DSPy default and return it."""
    import dspy

    lm = dspy_lm(model, **kwargs)
    dspy.configure(lm=lm)
    return lm


def reflection_lm(model: str | None = None, **kwargs):
    """The LM GEPA uses to propose instructions (distinct from the task LM)."""
    return dspy_lm(model or config.REFLECTION_MODEL, **kwargs)


def spend(*lms, since: list[int] | None = None) -> dict:
    """Total calls, tokens and USD across the history of one or more DSPy LMs.

    Cached responses are replayed from disk and cost nothing; LiteLLM reports
    their cost as zero, so the total is what you were actually billed.
    ``since`` gives, per LM, the history length to start counting from (see
    :func:`meter`).
    """
    calls = input_tokens = output_tokens = 0
    cost = 0.0
    for k, lm in enumerate(lms):
        history = getattr(lm, "history", []) or []
        start = since[k] if since else 0
        for entry in history[start:]:
            calls += 1
            usage = entry.get("usage") or {}
            input_tokens += int(usage.get("prompt_tokens", 0) or 0)
            output_tokens += int(usage.get("completion_tokens", 0) or 0)
            cost += float(entry.get("cost") or 0.0)
    return {"calls": calls, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "usd": round(cost, 4)}


@contextmanager
def meter(*lms):
    """Measure the spend of one block of work::

        with llm.meter(task_lm, reflection_lm) as cost:
            tuned = opt.run_gepa(...)
        print(cost)        # {'calls': ..., 'input_tokens': ..., 'usd': ...}
    """
    start = [len(getattr(lm, "history", []) or []) for lm in lms]
    result: dict = {}
    try:
        yield result
    finally:
        result.update(spend(*lms, since=start))


# --------------------------------------------------------------------------- #
# LangChain side
# --------------------------------------------------------------------------- #
def chat_model(**kwargs):
    """The LangChain chat model: ``ChatAnthropic`` on the course model."""
    from langchain_anthropic import ChatAnthropic

    config.require_credentials()
    params: dict[str, Any] = {"model": config.CHAT_MODEL, "max_tokens": config.MAX_TOKENS}
    params.update(kwargs)
    return ChatAnthropic(**params)


def chat_usage(messages: Iterable, model: str | None = None) -> dict:
    """Sum the token usage of the AI messages in a LangChain transcript."""
    input_tokens = output_tokens = turns = 0
    for message in messages:
        meta = getattr(message, "usage_metadata", None)
        if not meta:
            continue
        turns += 1
        input_tokens += int(meta.get("input_tokens", 0) or 0)
        output_tokens += int(meta.get("output_tokens", 0) or 0)
    model = model or config.CHAT_MODEL
    return {"model_turns": turns, "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "usd_estimate": round(estimate_cost(model, input_tokens, output_tokens), 4)}
