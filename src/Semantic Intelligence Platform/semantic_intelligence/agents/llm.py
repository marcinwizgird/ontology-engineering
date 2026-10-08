"""Language-model providers for the agent layer.

One narrow contract — :meth:`LanguageModel.complete_json` — because every agent
in the platform needs the same thing from a model: a JSON object conforming to a
schema that a deterministic stage will then check. Free text never reaches the
store; it reaches a validator.

* :class:`ClaudeModel` — Anthropic Messages API with structured outputs
  (``output_config.format`` = JSON schema), adaptive thinking, an explicit effort
  level, top-level prompt caching (the system prompt and schema are stable per
  agent, so repeated calls hit the cache), and server-side refusal fallback.
* :class:`SimulatedModel` — deterministic and offline. Each agent registers a
  rule-based *simulator* for its task, so ``python -m semantic_intelligence`` and
  the test-suite run without a key and without cost (the same convention as
  ``langextract_ontology.SimulatedOntologyModel`` and ``oe_course``).

Usage accounting is kept on the model object; agents copy it into the evidence
record of every proposal, so the cost of a proposal is auditable next to it.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

DEFAULT_MODEL = "claude-opus-5-5"

__all__ = ["LanguageModel", "ClaudeModel", "SimulatedModel", "ModelRefusal",
           "default_model", "DEFAULT_MODEL"]


class ModelRefusal(RuntimeError):
    """The model (and its fallback chain) declined the request."""


class LanguageModel(Protocol):
    model_id: str
    usage: dict[str, int]

    def complete_json(self, task: str, system: str, prompt: str,
                      schema: dict[str, Any]) -> dict[str, Any]: ...


def prompt_hash(system: str, prompt: str) -> str:
    return hashlib.sha256((system + "\x00" + prompt).encode("utf-8")).hexdigest()[:16]


@dataclass
class ClaudeModel:
    """Claude through the official ``anthropic`` SDK."""

    model_id: str = DEFAULT_MODEL
    effort: str = "high"
    max_tokens: int = 16000
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "calls": 0})

    def __post_init__(self) -> None:
        import anthropic  # imported lazily: offline runs never need the SDK
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()

    def complete_json(self, task: str, system: str, prompt: str,
                      schema: dict[str, Any]) -> dict[str, Any]:
        response = self._client.beta.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": schema}},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            # passed through extra_body: SDK releases before the parameter existed
            # (this environment has anthropic 0.96) reject it as a keyword argument
            extra_body={"fallbacks": "default"},
        )
        u = response.usage
        self.usage["calls"] += 1
        self.usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
        self.usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        self.usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ModelRefusal(f"{task}: refused ({getattr(details, 'category', None)})")
        if response.stop_reason == "max_tokens":
            raise RuntimeError(f"{task}: output truncated at max_tokens={self.max_tokens}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError(f"{task}: no text block in response")
        return json.loads(text)


Simulator = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass
class SimulatedModel:
    """Deterministic offline model: ``task`` → registered simulator(prompt, schema)."""

    model_id: str = "simulated"
    simulators: dict[str, Simulator] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=lambda: {"calls": 0})
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def register(self, task: str, fn: Simulator) -> None:
        self.simulators[task] = fn

    def complete_json(self, task: str, system: str, prompt: str,
                      schema: dict[str, Any]) -> dict[str, Any]:
        fn = self.simulators.get(task)
        if fn is None:
            raise KeyError(f"SimulatedModel has no simulator for task {task!r}; "
                           f"known: {sorted(self.simulators)}")
        self.usage["calls"] += 1
        out = fn(prompt, schema)
        self.transcript.append({"task": task, "prompt_hash": prompt_hash(system, prompt),
                                "output": out})
        return out


def default_model() -> LanguageModel:
    """Offline unless asked: ``SIP_MODEL`` unset/``simulated`` → simulators;
    ``SIP_MODEL=claude-opus-5-5`` (or ``auto`` with credentials) → Claude.

    Live mode is an explicit opt-in because every call is billed; the presence of an
    API key in the environment is not consent to spend it.
    """
    choice = os.environ.get("SIP_MODEL", "simulated")
    if choice == "auto":
        choice = DEFAULT_MODEL if os.environ.get("ANTHROPIC_API_KEY") else "simulated"
    if choice in ("", "simulated"):
        from .simulators import simulated_model
        return simulated_model()
    return ClaudeModel(model_id=choice)
