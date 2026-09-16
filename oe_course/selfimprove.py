"""Self-improving agents — and the guard rails that keep "self-improving" honest.

The loop is simple to state: run the skill, keep the episodes it got wrong,
re-optimise on those, and adopt the result only if it is genuinely better.

The third clause is the whole discipline. A loop that adopts whatever the
optimiser returns does not improve; it drifts, and it drifts *confidently*,
because the same run that produced the change also produced the evidence for it.
:class:`SelfImprovingSkill` therefore separates three datasets and never lets
them mix:

``experience``
    episodes the deployed skill actually saw. Mined for failures. Never scored
    against for promotion — that is the feedback loop that eats itself.
``train``
    what the optimiser is allowed to look at (seed examples + mined failures).
``holdout``
    untouched by the optimiser, and the *only* thing the promotion gate reads.

Promotion also requires a minimum margin, so noise on a small holdout cannot
ratchet the skill sideways. When the gate rejects a candidate, the skill stays
where it was and the attempt is recorded — a rejected round is a result, not a
failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["Episode", "ExperienceBuffer", "SelfImprovingSkill", "ImprovementRound"]


@dataclass
class Episode:
    """One thing the deployed skill did, and how good it was."""

    inputs: dict
    prediction: Any
    score: float
    violated: list[str] = field(default_factory=list)
    gold: Any = None

    @property
    def failed(self) -> bool:
        return self.score < 1.0


class ExperienceBuffer:
    """Episodic memory: what the skill did in the field."""

    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self.episodes: list[Episode] = []

    def add(self, episode: Episode) -> None:
        self.episodes.append(episode)
        if len(self.episodes) > self.capacity:
            self.episodes = self.episodes[-self.capacity :]

    def __len__(self) -> int:
        return len(self.episodes)

    def failures(self, threshold: float = 1.0) -> list[Episode]:
        return [e for e in self.episodes if e.score < threshold]

    def violation_histogram(self) -> dict[str, int]:
        """Which rules the deployed skill breaks most — the improvement agenda."""
        counts: dict[str, int] = {}
        for episode in self.episodes:
            for v in episode.violated:
                counts[v] = counts.get(v, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def mine_training_examples(self, threshold: float = 1.0) -> list:
        """Turn labelled failures into training examples for the optimiser.

        Only episodes carrying a gold label can be mined. Unlabelled failures
        still inform the violation histogram, but they cannot train anything —
        which is precisely why deployed agents need a labelling path.
        """
        return [e.gold for e in self.failures(threshold) if e.gold is not None]


@dataclass
class ImprovementRound:
    """The record of one improvement attempt, accepted or not."""

    round_index: int
    before: float
    after: float
    promoted: bool
    reason: str
    instruction: str = ""

    def __str__(self) -> str:  # pragma: no cover - display only
        verdict = "PROMOTED" if self.promoted else "rejected"
        return (
            f"round {self.round_index}: holdout {self.before:.3f} -> {self.after:.3f} "
            f"[{verdict}] {self.reason}"
        )


class SelfImprovingSkill:
    """A skill that learns from its own failures, behind a promotion gate.

    Parameters
    ----------
    skill:
        The :class:`oe_course.skills.Skill` being improved.
    holdout:
        Examples the optimiser never sees. The gate reads only these.
    optimise:
        ``optimise(program, trainset) -> program``. Injected so the lab can swap
        GEPA for MIPROv2, or for a no-op control.
    min_gain:
        Required improvement on the holdout before a candidate is adopted.
    """

    def __init__(
        self,
        skill,
        holdout: list,
        optimise: Callable[[Any, list], Any],
        *,
        min_gain: float = 0.01,
        seed_train: list | None = None,
    ):
        self.skill = skill
        self.holdout = holdout
        self.optimise = optimise
        self.min_gain = min_gain
        self.seed_train = list(seed_train or [])
        self.experience = ExperienceBuffer()
        self.rounds: list[ImprovementRound] = []

    # -- deployment ---------------------------------------------------------
    def run(self, example) -> Episode:
        """Serve one request and remember what happened."""
        program = self.skill.program()
        prediction = program(**example.inputs())
        report = self.skill.scorer(example, prediction)
        episode = Episode(
            inputs=example.inputs().toDict() if hasattr(example.inputs(), "toDict") else dict(example.inputs()),
            prediction=prediction,
            score=report.score,
            violated=list(report.violated),
            gold=example,
        )
        self.experience.add(episode)
        return episode

    def run_all(self, examples: list) -> list[Episode]:
        return [self.run(ex) for ex in examples]

    # -- improvement --------------------------------------------------------
    def improve(self) -> ImprovementRound:
        """One improvement round, gated on held-out performance."""
        from oe_course.evaluation import evaluate_dataset
        from oe_course.optimize import instruction_of

        index = len(self.rounds) + 1
        before = evaluate_dataset(self.skill.program(), self.holdout, self.skill.scorer)[
            "mean_score"
        ]

        mined = self.experience.mine_training_examples()
        trainset = self.seed_train + mined
        if not trainset:
            round_record = ImprovementRound(
                index, before, before, False, "no labelled failures to learn from"
            )
            self.rounds.append(round_record)
            return round_record

        candidate = self.optimise(self.skill.program(), trainset)
        candidate_instruction = instruction_of(candidate)

        after = evaluate_dataset(candidate, self.holdout, self.skill.scorer)["mean_score"]
        gain = after - before

        if gain >= self.min_gain:
            self.skill.promote(
                candidate_instruction,
                score=after,
                note=f"round {index}: +{gain:.3f} on holdout, trained on {len(trainset)} examples",
            )
            reason = f"gain {gain:+.3f} >= min_gain {self.min_gain}"
            promoted = True
        else:
            reason = f"gain {gain:+.3f} < min_gain {self.min_gain}; keeping v{self.skill.version}"
            promoted = False

        round_record = ImprovementRound(
            index, before, after, promoted, reason, candidate_instruction
        )
        self.rounds.append(round_record)
        return round_record

    def report(self) -> str:
        lines = [f"self-improvement history for skill {self.skill.name!r}"]
        lines += [f"  {r}" for r in self.rounds] or ["  (no rounds run)"]
        lines.append(f"  experience: {len(self.experience)} episodes, "
                     f"{len(self.experience.failures())} failures")
        hist = self.experience.violation_histogram()
        if hist:
            lines.append(f"  violations: {hist}")
        return "\n".join(lines)
