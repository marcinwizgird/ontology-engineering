"""Optimising agent programs with DSPy — GEPA, and the honest way to report it.

GEPA (Genetic-Pareto) improves a DSPy program by *reflecting on textual
feedback*: it runs the program, reads what the metric said went wrong, proposes
a revised instruction, and keeps candidates on the Pareto front across the
training set. It is only as good as the feedback its metric produces, which is
why :mod:`oe_course.evaluation` insists every scorer explains itself.

This module supplies the runner and — just as importantly — the reporting.
:func:`compare` shows the before/after score *and* the violation histogram *and*
the instruction diff, because "the number went up" is not a finding. A rise you
cannot attribute to a specific instruction change is usually noise or leakage.

Guardrails worth stating to students
------------------------------------
* Optimise on ``trainset``, report on a held-out ``valset``. GEPA will happily
  overfit six examples.
* ``max_metric_calls`` is the real cost dial; with a live model each call is a
  billed request.
* An optimised instruction is a *learned artefact*. Save it, diff it, review it —
  it is as much a part of the system as the code.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Callable

from oe_course import config

__all__ = ["run_gepa", "compare", "instruction_of", "set_instruction", "OptimisationResult"]


def instruction_of(program) -> str:
    """The current instruction text of a single-predictor DSPy program."""
    predictors = list(program.named_predictors())
    if not predictors:
        return ""
    return predictors[0][1].signature.instructions


def all_instructions(program) -> dict[str, str]:
    return {name: p.signature.instructions for name, p in program.named_predictors()}


def set_instruction(program, text: str):
    """Overwrite the instruction of every predictor (used to build baselines)."""
    for _, predictor in program.named_predictors():
        predictor.signature = predictor.signature.with_instructions(text)
    return program


@dataclass
class OptimisationResult:
    program: Any
    before: dict
    after: dict
    instruction_before: str
    instruction_after: str

    @property
    def delta(self) -> float:
        return round(self.after["mean_score"] - self.before["mean_score"], 4)

    def instruction_diff(self) -> str:
        return "\n".join(
            difflib.unified_diff(
                self.instruction_before.splitlines(),
                self.instruction_after.splitlines(),
                fromfile="instruction (before)",
                tofile="instruction (after)",
                lineterm="",
            )
        )

    def report(self) -> str:
        lines = [
            f"mean score  {self.before['mean_score']:.3f}  ->  {self.after['mean_score']:.3f}"
            f"   (delta {self.delta:+.3f})",
            f"violations  {self.before['violations']}",
            f"        ->  {self.after['violations']}",
            "",
            "instruction diff:",
            self.instruction_diff() or "(unchanged)",
        ]
        return "\n".join(lines)


def run_gepa(
    program,
    trainset,
    metric,
    *,
    valset=None,
    reflection_lm=None,
    auto: str | None = None,
    max_metric_calls: int | None = 60,
    reflection_minibatch_size: int = 2,
    **kwargs,
):
    """Compile ``program`` with GEPA and return the optimised program.

    ``metric`` must be a GEPA feedback metric — see
    :func:`oe_course.evaluation.make_gepa_metric`. A plain float metric will
    "work" and optimise far worse, because every reflection step then sees only
    "this trajectory got a score of X".
    """
    import dspy

    if reflection_lm is None:
        from oe_course.llm import reflection_lm as default_reflection_lm

        reflection_lm = default_reflection_lm()

    gepa = dspy.GEPA(
        metric=metric,
        auto=auto,
        max_metric_calls=None if auto else max_metric_calls,
        reflection_lm=reflection_lm,
        reflection_minibatch_size=reflection_minibatch_size,
        **kwargs,
    )
    return gepa.compile(program, trainset=trainset, valset=valset or trainset)


def compare(before_program, after_program, dataset, scorer) -> OptimisationResult:
    """Evaluate two programs on the same data and package the comparison."""
    from oe_course.evaluation import evaluate_dataset

    return OptimisationResult(
        program=after_program,
        before=evaluate_dataset(before_program, dataset, scorer),
        after=evaluate_dataset(after_program, dataset, scorer),
        instruction_before=instruction_of(before_program),
        instruction_after=instruction_of(after_program),
    )
