"""LlmGateway: the only egress for ontology content to a language model (OVA-P02).

* **Off by default.** The assistant runs on the deterministic offline simulator unless the
  operator sets ``OVA_ASSISTANT_MODEL`` (e.g. ``claude-opus-5-5``). An API key in the
  environment is not consent to spend it.
* **Budget.** At most ``OVA_ASSISTANT_MAX_CALLS`` model calls per review session
  (default 60); past it, the assistant falls back to the simulator for that session.
* **Payload log.** Every call records model, size and usage (not the content) so cost
  and egress are auditable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

DEFAULT_MODEL = "claude-opus-5-5"
ALLOWED_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")


@dataclass
class LlmGateway:
    model_id: str | None = None
    max_calls: int = 60
    calls: int = 0
    log: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0})

    @classmethod
    def from_env(cls) -> "LlmGateway":
        choice = os.environ.get("OVA_ASSISTANT_MODEL", "simulated").strip()
        model = None if choice in ("", "simulated", "off") else choice
        if model is not None and model not in ALLOWED_MODELS:
            raise ValueError(f"OVA_ASSISTANT_MODEL={model!r} is not on the allow-list {ALLOWED_MODELS}")
        return cls(model_id=model, max_calls=int(os.environ.get("OVA_ASSISTANT_MAX_CALLS", "60")))

    @property
    def live(self) -> bool:
        return self.model_id is not None

    def allow(self) -> bool:
        return self.live and self.calls < self.max_calls

    def record(self, model: str, request_chars: int, usage, stop_reason: str) -> None:
        self.calls += 1
        for k in self.usage:
            self.usage[k] += getattr(usage, k, 0) or 0
        self.log.append({"at": time.time(), "model": model, "request_chars": request_chars,
                         "stop_reason": stop_reason,
                         "input_tokens": getattr(usage, "input_tokens", 0),
                         "output_tokens": getattr(usage, "output_tokens", 0)})

    def status(self) -> dict:
        return {"mode": "live" if self.live else "offline",
                "model": self.model_id or "simulated", "calls": self.calls,
                "max_calls": self.max_calls, "usage": dict(self.usage)}
