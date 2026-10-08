"""Agent runtime — the part of the platform neither Protégé nor VocBench has.

The design is *workflow-shaped*, not free-roaming: each agent is a fixed
``plan → propose (model) → criticise (deterministic) → submit (platform)`` loop.
The model is consulted only for the judgement step and must answer in a JSON
schema; a deterministic **critic** decides what survives; survivors are submitted
through :meth:`Platform.call` under the agent's own *machine principal*, which the
change tracker always stages. Consequences, each a requirement:

* an agent can do nothing its machine principal's roles do not allow, and can
  never validate (QR-SEC-02, QR-AIT-02) — the PDP enforces it, not the agent;
* every proposal is a staged commit carrying an **evidence** record: sources and
  spans, model id, prompt hash, critic verdicts, cost (FR-AG-02, QR-AIT-01, QR-REG-01);
* the project's AI policy is checked before every model call and the decision is
  logged (QR-SEC-03); budgets and a kill switch bound every run (QR-AIT-02);
* when the model is unavailable the agent degrades to "no proposals" and the
  stage stays completable by hand (QR-AVL-02).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..core.principal import Principal
from ..governance.registry import AuthorizationError
from .llm import LanguageModel, ModelRefusal, prompt_hash


class BudgetExceeded(RuntimeError):
    pass


class RunStopped(RuntimeError):
    pass


@dataclass
class Proposal:
    operation: str
    arguments: dict
    rationale: str
    evidence: dict = field(default_factory=dict)
    confidence: float = 0.5
    critic: list[str] = field(default_factory=list)     # verdicts; empty == passed
    commit: str | None = None
    error: str | None = None

    @property
    def accepted_by_critic(self) -> bool:
        return not self.critic


@dataclass
class AgentRun:
    id: str
    agent: str
    project: str
    principal: str
    started: float
    status: str = "running"            # running | done | stopped | failed | degraded
    steps: int = 0
    model_calls: int = 0
    proposals: list[Proposal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    output: Any = None

    def summary(self) -> dict:
        sub = [p for p in self.proposals if p.commit]
        return {"run": self.id, "agent": self.agent, "project": self.project,
                "status": self.status, "steps": self.steps, "model_calls": self.model_calls,
                "proposed": len(self.proposals), "submitted": len(sub),
                "rejected_by_critic": sum(1 for p in self.proposals if p.critic),
                "errors": sum(1 for p in self.proposals if p.error), "notes": self.notes[-10:]}


class AgentRuntime:
    """Owns runs, budgets, the kill switch and the per-agent metrics (QR-AIT-03)."""

    def __init__(self, platform, model: LanguageModel) -> None:
        self.platform = platform
        self.model = model
        self.runs: dict[str, AgentRun] = {}
        self._stopped: set[str] = set()
        self.policy_log: list[dict] = []

    def stop(self, run_id: str) -> None:
        self._stopped.add(run_id)

    def metrics(self, project: str | None = None) -> dict[str, dict]:
        """Per agent: proposals, submitted, accepted/rejected by humans, cost."""
        out: dict[str, dict] = {}
        for r in self.runs.values():
            if project and r.project != project:
                continue
            m = out.setdefault(r.agent, {"runs": 0, "proposed": 0, "submitted": 0,
                                         "critic_rejected": 0, "accepted": 0,
                                         "rejected_by_validator": 0, "pending": 0,
                                         "model_calls": 0})
            m["runs"] += 1
            m["model_calls"] += r.model_calls
            for p in r.proposals:
                m["proposed"] += 1
                m["critic_rejected"] += bool(p.critic)
                if p.commit:
                    m["submitted"] += 1
                    ctx = self.platform.projects[r.project]
                    c = ctx.tracker._commits.get(p.commit)
                    if c is None:
                        m["rejected_by_validator"] += 1
                    elif c.status == "staged":
                        m["pending"] += 1
                    else:
                        m["accepted"] += 1
        for m in out.values():
            decided = m["accepted"] + m["rejected_by_validator"]
            m["acceptance_rate"] = round(m["accepted"] / decided, 3) if decided else None
        return out


class Agent:
    """Base class. Subclasses set ``name``, ``stage``, ``roles`` and implement ``run``."""

    name: str = "agent"
    stage: str = "model"
    roles: tuple[str, ...] = ("agent-reader",)
    description: str = ""
    system_prompt: str = ""

    def __init__(self, runtime: AgentRuntime, principal: Principal) -> None:
        self.rt = runtime
        self.principal = principal

    @property
    def platform(self):
        return self.rt.platform

    # -- run lifecycle ---------------------------------------------------- #
    def start(self, project: str) -> AgentRun:
        run = AgentRun(uuid.uuid4().hex[:12], self.name, project, self.principal.id,
                       time.time())
        self.rt.runs[run.id] = run
        return run

    def _check(self, run: AgentRun) -> None:
        if run.id in self.rt._stopped:
            run.status = "stopped"
            raise RunStopped(run.id)
        pol = self.platform.projects[run.project].config.ai_policy
        if run.steps >= pol.max_steps_per_run:
            raise BudgetExceeded(f"step budget {pol.max_steps_per_run} exhausted")
        run.steps += 1

    def ask(self, run: AgentRun, task: str, prompt: str, schema: dict) -> dict | None:
        """One model call, after the AI-policy check. ``None`` = degraded."""
        self._check(run)
        pol = self.platform.projects[run.project].config.ai_policy
        allowed = pol.llm_allowed and pol.agent_enabled(self.name)
        self.rt.policy_log.append({"run": run.id, "agent": self.name, "task": task,
                                   "allowed": allowed, "model": self.rt.model.model_id})
        if not allowed:
            run.notes.append(f"AI policy forbids model use for {self.name}; degraded")
            run.status = "degraded"
            return None
        usage = getattr(self.rt.model, "usage", {})
        if usage.get("input_tokens", 0) + usage.get("output_tokens", 0) > pol.max_tokens_per_run \
                and self.rt.model.model_id != "simulated":
            raise BudgetExceeded("token budget exhausted")
        try:
            out = self.rt.model.complete_json(task, self.system_prompt, prompt, schema)
        except (ModelRefusal, RuntimeError, KeyError, ConnectionError) as exc:
            run.notes.append(f"model unavailable for {task}: {exc}; degraded")
            run.status = "degraded"
            return None
        run.model_calls += 1
        run._last_prompt_hash = prompt_hash(self.system_prompt, prompt)  # type: ignore[attr-defined]
        return out

    def submit(self, run: AgentRun, p: Proposal) -> Proposal:
        """Critic-approved proposal → staged commit with evidence."""
        run.proposals.append(p)
        if p.critic:
            return p
        self._check(run)
        evidence = {"agent": self.name, "run": run.id, "model": self.rt.model.model_id,
                    "prompt_hash": getattr(run, "_last_prompt_hash", None),
                    "confidence": p.confidence, "rationale": p.rationale,
                    "on_behalf_of": self.principal.on_behalf_of, "ai_generated": True,
                    **p.evidence}
        try:
            c = self.platform.call(self.principal, run.project, p.operation,
                                   _evidence=evidence, **p.arguments)
            p.commit = getattr(c, "id", None)
            if p.commit is None:
                p.error = "no-op (nothing to change)"
        except (AuthorizationError, ValueError, KeyError) as exc:
            p.error = f"{type(exc).__name__}: {exc}"
        return p

    def read(self, run: AgentRun, op: str, **kw):
        """Reads go through the platform too (and its PDP)."""
        return self.platform.call(self.principal, run.project, op, **kw)

    def finish(self, run: AgentRun, output: Any = None) -> AgentRun:
        if run.status == "running":
            run.status = "done"
        run.output = output
        return run

    def run(self, project: str, **inputs) -> AgentRun:  # pragma: no cover - abstract
        raise NotImplementedError
