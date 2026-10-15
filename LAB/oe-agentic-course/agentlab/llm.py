"""Claude for DSPy: credentials, model ids, and what each block of work cost.

Chapter 1 · the problem set builds its first Claude program, so this is where the
course first calls a model. DSPy talks to Anthropic through LiteLLM, so a model is
named ``anthropic/<model-id>``.

``configure_dspy()``
    Install Claude as DSPy's default LM and return it.
``dspy_lm()`` / ``reflection_lm()``
    A separate LM: e.g. uncached (``cache=False``) to measure run-to-run noise, or
    the strong model GEPA uses to *propose* instructions (used from Chapter 2).
``meter(...)`` / ``spend(...)``
    The calls, tokens and dollars spent inside a ``with`` block, read from the LMs'
    own histories. Cached answers cost nothing and are counted as zero.

Every call is billed. DSPy caches identical requests on disk, so re-running a cell
with an unchanged prompt is free. Configuration comes from the environment, or
from ``.env`` at the course root (see ``.env.example``); the shell wins.

The LangChain side of the original ``llm`` module (``chat_model``, ``chat_usage``)
arrives in Chapter 3, in ``agentlab.agents``, with tool-calling agents.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

INTRODUCED_IN = 1

__all__ = ["DSPY_MODEL", "REFLECTION_MODEL", "MAX_TOKENS", "PRICES_PER_MTOK", "has_credentials",
           "require_credentials", "dspy_lm", "configure_dspy", "reflection_lm",
           "spend", "meter"]

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    """Load ``KEY=VALUE`` lines from the course ``.env``; never override the shell."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file()

#: The model that does the task. LiteLLM wants ``provider/model``.
DSPY_MODEL = os.environ.get("OE_COURSE_DSPY_MODEL", "anthropic/claude-sonnet-5-5")
#: GEPA's reflection model proposes new instructions; it should be the strongest one.
REFLECTION_MODEL = os.environ.get("OE_COURSE_REFLECTION_MODEL", "anthropic/claude-opus-5-5")
#: ``max_tokens`` caps thinking *plus* answer, so leave real headroom.
MAX_TOKENS = int(os.environ.get("OE_COURSE_MAX_TOKENS", "16000"))


def has_credentials() -> bool:
    """Is an Anthropic credential visible to the SDK?"""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def require_credentials() -> None:
    """Fail fast, with instructions, before the first billed call."""
    if not has_credentials():
        raise RuntimeError(
            f"No Anthropic credential found. Set ANTHROPIC_API_KEY in your shell, or put it "
            f"in {ENV_FILE} (copy .env.example). The problem sets call the live API.")


def dspy_lm(model: str | None = None, **kwargs):
    """A DSPy LM on Anthropic.

    ``temperature=1.0`` because current Claude models accept only their default
    sampling settings; DSPy's usual 0.0 would be rejected.
    """
    import dspy

    require_credentials()
    params = {"temperature": 1.0, "max_tokens": MAX_TOKENS, **kwargs}
    return dspy.LM(model or DSPY_MODEL, **params)


def configure_dspy(model: str | None = None, **kwargs):
    """Install an Anthropic LM as the DSPy default and return it."""
    import dspy

    lm = dspy_lm(model, **kwargs)
    dspy.configure(lm=lm)
    return lm


def reflection_lm(model: str | None = None, **kwargs):
    """The LM GEPA uses to propose instructions (distinct from the task LM)."""
    return dspy_lm(model or REFLECTION_MODEL, **kwargs)


#: USD per million tokens (input, output), used only when LiteLLM cannot price a call:
#: its bundled price table predates these models, and the online table it downloads at
#: start-up is not always reachable (e.g. from a Jupyter kernel).
PRICES_PER_MTOK = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}


def _entry_cost(entry: dict) -> float:
    """What one history entry was billed. A cache hit replays the original response,
    *including its original cost*, so it is counted as 0 here."""
    if getattr(entry.get("response"), "cache_hit", False):
        return 0.0
    if entry.get("cost"):
        return float(entry["cost"])
    usage = entry.get("usage") or {}
    prices = PRICES_PER_MTOK.get(str(entry.get("model") or "").split("/")[-1])
    if not prices:
        return 0.0
    return (int(usage.get("prompt_tokens", 0) or 0) * prices[0]
            + int(usage.get("completion_tokens", 0) or 0) * prices[1]) / 1_000_000


def spend(*lms, since: list[int] | None = None) -> dict:
    """Total calls, tokens and USD across the history of one or more DSPy LMs.

    Cached responses are replayed from disk and cost nothing, so they count as $0 and
    the total is what you were actually billed. ``since`` gives, per LM, the history
    length to start counting from (see :func:`meter`).
    """
    calls = input_tokens = output_tokens = 0
    cost = 0.0
    for k, lm in enumerate(lms):
        history = getattr(lm, "history", []) or []
        for entry in history[since[k] if since else 0:]:
            usage = entry.get("usage") or {}
            calls += 1
            input_tokens += int(usage.get("prompt_tokens", 0) or 0)
            output_tokens += int(usage.get("completion_tokens", 0) or 0)
            cost += _entry_cost(entry)
    return {"calls": calls, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "usd": round(cost, 4)}


@contextmanager
def meter(*lms):
    """Measure the spend of one block of work::

        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, dev, scorer)
        print(cost)        # {'calls': ..., 'input_tokens': ..., 'usd': ...}
    """
    start = [len(getattr(lm, "history", []) or []) for lm in lms]
    result: dict = {}
    try:
        yield result
    finally:
        result.update(spend(*lms, since=start))
