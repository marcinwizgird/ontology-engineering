"""Function tools: the action surface an agent acts through, and the log of what it did.

Chapter 3 · the first chapter whose problem set gives Claude *tools*: the review agent
calls the chapter's tableau instead of judging subsumption by eye. Two ideas from the
original ``oe_course.tools`` arrive here; the third (the registry toolset bound to a
SPARQL workspace, ``ToolContext`` / ``build_toolset``) arrives with Chapter 1's
registry agent when that part returns.

**Every call is logged.** :class:`ToolCallLog` records name, arguments, latency and
result size. The log *is* the agent's trajectory: it is how a problem set counts
reasoner calls, and (Chapter 6) how an episode is charged against a reward.

**Tools are bound to a workspace, not to globals.** A chapter writes plain Python
functions closed over its own workspace object (e.g. the module under review) and
turns them into tools with :func:`make_tools`. Two agents, two workspaces, no shared
state — which is what makes an agent run reproducible.

``instrument`` is the seam every toolset shares: it wraps a function so each
invocation lands in the log, and turns exceptions into an ``ERROR: ...`` string the
model can read instead of a crash.
"""

from __future__ import annotations

import functools
import json
import time
from dataclasses import dataclass, field
from typing import Callable

INTRODUCED_IN = 3

__all__ = ["ToolCall", "ToolCallLog", "instrument", "make_tools"]


@dataclass
class ToolCall:
    name: str
    args: dict
    ok: bool
    seconds: float
    result_chars: int
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "ok": self.ok,
            "seconds": round(self.seconds, 4),
            "result_chars": self.result_chars,
            "error": self.error,
        }


@dataclass
class ToolCallLog:
    """An append-only record of what an agent did."""

    calls: list[ToolCall] = field(default_factory=list)

    def record(self, call: ToolCall) -> None:
        self.calls.append(call)

    def reset(self) -> None:
        self.calls.clear()

    def names(self) -> list[str]:
        return [c.name for c in self.calls]

    def cost(self, per_call: float = 1.0, per_second: float = 0.0) -> float:
        """A simple, explicit cost model — the reward's negative term."""
        return sum(per_call + per_second * c.seconds for c in self.calls)

    def summary(self) -> dict:
        return {
            "n_calls": len(self.calls),
            "distinct_tools": sorted({c.name for c in self.calls}),
            "failures": sum(1 for c in self.calls if not c.ok),
            "seconds": round(sum(c.seconds for c in self.calls), 3),
        }

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self.calls]


def instrument(fn: Callable, name: str, log: ToolCallLog) -> Callable:
    """Wrap a tool implementation so every invocation lands in the log.

    ``functools.wraps`` matters here: LangChain infers each tool's argument
    schema via ``inspect.signature``, which follows ``__wrapped__``. Without it
    every tool would advertise ``(*args, **kwargs)`` and the model would have
    nothing to fill in.
    """

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        started = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # surfaced to the agent as an error string
            log.record(
                ToolCall(name, kwargs or {"args": args}, False,
                         time.perf_counter() - started, 0, str(exc))
            )
            return f"ERROR: {exc}"
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        log.record(
            ToolCall(name, kwargs or {"args": list(args)}, True,
                     time.perf_counter() - started, len(text))
        )
        return text

    return wrapped


def make_tools(impls: list[Callable], log: ToolCallLog) -> list:
    """LangChain tools from plain functions, each one logged.

    The function's name is the tool's name and its docstring is the description the
    model reads, so write the docstring as *when to call this*, not only what it does:
    the trigger condition is what drives correct tool selection.
    """
    from langchain_core.tools import tool

    return [tool(instrument(fn, fn.__name__, log)) for fn in impls]
