"""Skills: a capability packaged with the thing that proves it works.

A "skill" in this course is not a prompt. It is a **versioned bundle** of four
things that must travel together:

* an *instruction* (the part an optimiser rewrites),
* the *tools* the instruction assumes exist,
* an *evaluation dataset*, and
* a *metric*.

Splitting them is the standard way agent systems rot: a prompt gets edited, the
dataset that justified it is somewhere else, and nobody can say whether the
change helped. Bundling them makes a skill something you can version, diff,
regression-test, and — in :mod:`oe_course.selfimprove` — improve automatically
with a promotion gate.

:meth:`Skill.card` prints the *skill card*: what it does, how well, measured on
what, at which version. Students are asked to produce one for every agent they
build; an agent with no card is an agent with no claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

__all__ = ["Skill", "SkillRegistry", "SkillVersion"]


@dataclass
class SkillVersion:
    """One instruction, with the score it earned and when."""

    version: int
    instruction: str
    score: float | None = None
    dataset: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "instruction": self.instruction,
            "score": self.score,
            "dataset": self.dataset,
            "created_at": self.created_at,
            "note": self.note,
        }


@dataclass
class Skill:
    """A named capability plus everything needed to verify it.

    Parameters
    ----------
    build:
        ``build(instruction) -> program``. A factory, not a program: promoting a
        new instruction must produce a *fresh* program, or the old state leaks
        into the measurement.
    scorer:
        ``scorer(gold, pred) -> ScoreReport``.
    dataset:
        The held-out examples the skill's claim is measured on.
    """

    name: str
    description: str
    build: Callable[[str], Any]
    scorer: Callable[..., Any]
    dataset: list
    instruction: str
    tools: list[str] = field(default_factory=list)
    history: list[SkillVersion] = field(default_factory=list)

    def __post_init__(self):
        if not self.history:
            self.history.append(
                SkillVersion(1, self.instruction, note="initial instruction")
            )

    # -- lifecycle ----------------------------------------------------------
    @property
    def version(self) -> int:
        return self.history[-1].version

    def program(self):
        """A fresh program built from the current instruction."""
        return self.build(self.instruction)

    def evaluate(self, dataset: list | None = None) -> dict:
        """Score the current instruction; records the result on the version."""
        from oe_course.evaluation import evaluate_dataset

        data = dataset if dataset is not None else self.dataset
        result = evaluate_dataset(self.program(), data, self.scorer)
        self.history[-1].score = result["mean_score"]
        self.history[-1].dataset = f"{len(data)} examples"
        return result

    def promote(self, instruction: str, score: float | None = None, note: str = "") -> SkillVersion:
        """Record a new instruction as the current version."""
        entry = SkillVersion(self.version + 1, instruction, score=score, note=note)
        self.history.append(entry)
        self.instruction = instruction
        return entry

    def rollback(self) -> SkillVersion:
        """Return to the previous version — the escape hatch a promotion gate needs."""
        if len(self.history) < 2:
            raise ValueError("no earlier version to roll back to")
        self.history.pop()
        self.instruction = self.history[-1].instruction
        return self.history[-1]

    # -- reporting ----------------------------------------------------------
    def card(self) -> str:
        """The skill card: the claim, the evidence, and the version."""
        latest = self.history[-1]
        score = "not measured" if latest.score is None else f"{latest.score:.3f}"
        lines = [
            f"SKILL  {self.name}  (v{self.version})",
            f"       {self.description}",
            f"tools  {', '.join(self.tools) or '(none declared)'}",
            f"score  {score} on {latest.dataset or f'{len(self.dataset)} examples'}",
            "history:",
        ]
        for entry in self.history:
            mark = "*" if entry.version == self.version else " "
            shown = "  -  " if entry.score is None else f" {entry.score:.3f} "
            lines.append(f"  {mark} v{entry.version}{shown}{entry.note}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "instruction": self.instruction,
            "history": [h.to_dict() for h in self.history],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    def load_instruction(self, path: str | Path) -> str:
        """Restore a saved instruction (the learned artefact) into this skill."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.instruction = data["instruction"]
        self.history = [SkillVersion(**h) for h in data["history"]]
        return self.instruction


class SkillRegistry:
    """A tiny registry so agents can look skills up by name."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> Skill:
        self._skills[skill.name] = skill
        return skill

    def get(self, name: str) -> Skill:
        return self._skills[name]

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def names(self) -> list[str]:
        return sorted(self._skills)

    def cards(self) -> str:
        return "\n\n".join(s.card() for s in self._skills.values())
