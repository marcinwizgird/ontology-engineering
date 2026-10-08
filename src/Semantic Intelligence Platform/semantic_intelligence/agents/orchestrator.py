"""The lifecycle conductor — E2E agent assistance with human gates (FR-LC-01).

Drives a project through

    scope → acquire → model → validate → review ║ populate → reason → publish ║ consume

where ``║`` is a **human gate**. The conductor runs the assisting agents of each
stage, records stage states through ``lifecycle.setStage``, and stops at a gate
with the stage in ``awaiting-gate``; only a human principal can close review or
publish (enforced by the operation, not by the conductor). ``resume`` continues
after the gate.

Agents are enabled per project by a human holding ``rbac`` C (a project manager):
each gets a machine principal ``<agent>@<project>`` acting on that human's
behalf, bound to the agent's roles — so the audit trail always shows *which*
agent did something and *for whom*.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.principal import Principal
from .base import AgentRuntime
from .llm import LanguageModel, default_model
from .specialists import (AlignmentAgent, AssistantAgent, ExtractionAgent,
                          KnowledgeGraphBuilder, ModelingCopilot, QualityAgent,
                          RequirementsAgent, StewardAgent, VocabularyAgent)

GATES = {"review", "publish"}


@dataclass
class StageReport:
    stage: str
    state: str
    runs: list[dict] = field(default_factory=list)
    output: dict = field(default_factory=dict)


class Conductor:
    def __init__(self, platform, model: LanguageModel | None = None) -> None:
        self.platform = platform
        self.runtime = AgentRuntime(platform, model or default_model())
        self.agents: dict[tuple[str, str], object] = {}

    # -- enabling agents ---------------------------------------------------- #
    def enable_agents(self, project: str, by: Principal | str) -> list[str]:
        human = self.platform.registry.principal(by) if isinstance(by, str) else by
        if human.is_machine:
            raise PermissionError("agents are enabled by a human")
        self.platform.pdp.require(human, project, "rbac", "C")
        out = []
        for cls in (RequirementsAgent, ExtractionAgent, ModelingCopilot, VocabularyAgent,
                    AlignmentAgent, QualityAgent, StewardAgent, KnowledgeGraphBuilder,
                    AssistantAgent):
            pid = f"{cls.name}@{project}"
            reg = self.platform.registry
            p = reg.principals.get(pid) or reg.add_principal(
                Principal(pid, f"{cls.name} agent", is_machine=True, on_behalf_of=human.id))
            self.platform.call(human, project, "governance.bind", principal=pid,
                               roles=list(cls.roles))
            self.agents[(project, cls.name)] = cls(self.runtime, p)
            out.append(pid)
        return out

    def agent(self, project: str, name: str):
        try:
            return self.agents[(project, name)]
        except KeyError:
            raise KeyError(f"agent {name!r} not enabled on {project!r}") from None

    def _stage(self, project: str, who: Principal, stage: str, state: str, note: str = ""):
        self.platform.call(who, project, "lifecycle.setStage", stage=stage, state=state,
                           note=note)

    # -- the run ------------------------------------------------------------ #
    def run(self, project: str, human: Principal | str, *, brief: str = "",
            documents: dict[str, str] | None = None, tables: dict[str, str] | None = None,
            align_with: str | None = None, model_classes: list[str] | None = None
            ) -> list[StageReport]:
        """Scope → review gate. Returns one report per stage."""
        human = self.platform.registry.principal(human) if isinstance(human, str) else human
        reports: list[StageReport] = []
        conductor = self.agent(project, "steward").principal   # read-only identity

        def stage(name, fn):
            self._stage(project, conductor, name, "in-progress")
            rep = StageReport(name, "in-progress")
            fn(rep)
            rep.state = "awaiting-gate" if name in GATES else "done"
            self._stage(project, conductor, name, rep.state)
            reports.append(rep)

        def scope(rep):
            if brief:
                r = self.agent(project, "requirements").run(project, brief)
                rep.runs.append(r.summary())
                rep.output = r.output or {}

        def acquire(rep):
            for sid, text in (documents or {}).items():
                self.platform.call(human, project, "acquire.registerSource", source_id=sid,
                                   kind="document", content=text)
                rep.runs.append(self.agent(project, "extraction").run(project, sid).summary())
            for sid, text in (tables or {}).items():
                self.platform.call(human, project, "acquire.registerSource", source_id=sid,
                                   kind="table", content=text)

        def model(rep):
            evidence = "\n".join((documents or {}).values())
            for cls in model_classes or []:
                rep.runs.append(self.agent(project, "modeling").run(
                    project, cls, evidence).summary())
            rep.runs.append(self.agent(project, "vocabulary").run(project).summary())
            if align_with:
                rep.runs.append(self.agent(project, "alignment").run(
                    project, target_project=align_with).summary())

        def validate(rep):
            r = self.agent(project, "quality").run(project)
            rep.runs.append(r.summary())
            rep.output = r.output or {}

        def review(rep):
            r = self.agent(project, "steward").run(project)
            rep.runs.append(r.summary())
            rep.output = {"reviews": r.output}

        for name, fn in (("scope", scope), ("acquire", acquire), ("model", model),
                         ("validate", validate), ("review", review)):
            stage(name, fn)
        return reports

    def resume(self, project: str, human: Principal | str, *,
               questions: list[str] | None = None) -> list[StageReport]:
        """After the review gate: populate → reason → publish gate → consume."""
        human = self.platform.registry.principal(human) if isinstance(human, str) else human
        ctx = self.platform.projects[project]
        if ctx.lifecycle.get("review") != "done":
            raise PermissionError("the review gate is still open; a human must close it "
                                  "(lifecycle.setStage review done)")
        reports: list[StageReport] = []
        conductor = self.agent(project, "steward").principal

        def stage(name, fn):
            self._stage(project, conductor, name, "in-progress")
            rep = StageReport(name, "in-progress")
            fn(rep)
            rep.state = "awaiting-gate" if name in GATES else "done"
            self._stage(project, conductor, name, rep.state)
            reports.append(rep)

        def populate(rep):
            for sid, src in ctx.sources.items():
                if src["kind"] == "table":
                    rep.runs.append(self.agent(project, "kg-builder").run(project, sid)
                                    .summary())

        def reason(rep):
            rep.output = self.platform.call(human, project, "reasoning.classify")

        def publish(rep):
            rep.output = self.platform.call(human, project, "quality.releaseGate")

        for name, fn in (("populate", populate), ("reason", reason), ("publish", publish)):
            stage(name, fn)
        if questions:
            rep = StageReport("consume", "in-progress")
            for q in questions:
                r = self.agent(project, "assistant").run(project, q)
                rep.runs.append(r.summary())
                rep.output.setdefault("answers", []).append({"question": q, **(r.output or {})})
            rep.state = "done"
            reports.append(rep)
        return reports
