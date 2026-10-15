"""Evaluation: rulebooks, score reports, deterministic metrics, dataset runs.

Chapter 1 · the problem set grades a Claude program, so the course needs a metric
and a way to run a program over a dataset. Two more kinds of metric from the
original course arrive later, where they are first used: the **GEPA feedback
metric** in Chapter 2 (``agentlab.optimize``) and the **LLM-as-judge** in Chapter 5.

An agent you cannot score is an agent you cannot improve, so the course treats
the metric as a first-class engineering artefact rather than an afterthought.

**Deterministic metrics** (:func:`set_f1`, :func:`exact_match`) compare a
program's claims against gold labels. Cheap, reproducible, and the only sound
basis for a regression test. Their weakness: they cannot judge *prose*.

**Score reports with named violations.** A scorer returns a :class:`ScoreReport`:
the number, the ids of the guidelines the answer broke (from the task's
:class:`RuleBook`) and notes saying what was expected. In Chapter 1 those notes
drive *your* error analysis; in Chapter 2 the same notes become the feedback GEPA
reads to rewrite an instruction.

:func:`evaluate_dataset` runs a program over a dataset and returns the mean, the
per-item rows and the **violation histogram**: which rules break most often.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence


INTRODUCED_IN = 1

__all__ = ["Rule", "RuleBook", "ScoreReport", "set_f1", "exact_match", "parse_label_list",
           "make_metric", "evaluate_dataset"]


# --------------------------------------------------------------------------- #
# Guidelines a scorer can report as violated
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Rule:
    """One named guideline of a task, written the way feedback should state it.

    ``id``          stable slug the scorer puts in :attr:`ScoreReport.violated`;
    ``description`` what to do instead — the sentence GEPA's reflection reads.
    """

    id: str
    description: str

    def feedback_line(self) -> str:
        return f"VIOLATED GUIDELINE {self.id}: {self.description}"


class RuleBook:
    """The named guidelines of one task, shared by its scorer and its feedback."""

    def __init__(self, rules: Iterable[Rule]):
        self._rules: dict[str, Rule] = {r.id: r for r in rules}

    def __iter__(self):
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __getitem__(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def __contains__(self, rule_id: str) -> bool:
        return rule_id in self._rules

    @property
    def ids(self) -> list[str]:
        return list(self._rules)

    def as_guidelines(self, preamble: str = "") -> str:
        """The guidelines written out as an instruction — a hand-written baseline."""
        body = "\n".join(f"- {r.description}" for r in self._rules.values())
        return f"{preamble}\n{body}".strip()


# --------------------------------------------------------------------------- #
# The unit every scorer returns
# --------------------------------------------------------------------------- #
@dataclass
class ScoreReport:
    """A score, a human-readable diagnosis, and the rules that were violated.

    ``violated`` is what makes the report usable by GEPA: each id names a rule
    in the task's :class:`RuleBook`, and the feedback text spells out the fix so
    the reflection step has something concrete to write down.
    """

    score: float
    notes: list[str] = field(default_factory=list)
    violated: list[str] = field(default_factory=list)

    def feedback(self, rulebook=None) -> str:
        lines = list(self.notes)
        if rulebook is not None:
            for rule_id in self.violated:
                if rule_id in rulebook:
                    lines.append(rulebook[rule_id].feedback_line())
                else:
                    lines.append(f"VIOLATED GUIDELINE {rule_id}")
        lines.append(f"Score: {self.score:.3f}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Deterministic primitives
# --------------------------------------------------------------------------- #
def set_f1(predicted: Iterable[str], gold: Iterable[str]) -> tuple[float, float, float]:
    """Precision, recall and F1 over two sets of labels."""
    p_set, g_set = set(predicted), set(gold)
    if not p_set and not g_set:
        return 1.0, 1.0, 1.0
    tp = len(p_set & g_set)
    precision = tp / len(p_set) if p_set else 0.0
    recall = tp / len(g_set) if g_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def exact_match(predicted: str, gold: str) -> float:
    return 1.0 if str(predicted).strip().lower() == str(gold).strip().lower() else 0.0


def parse_label_list(value) -> list[str]:
    """Accept a list, a JSON array, or a comma/space separated string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text or text.lower() in {"none", "[]", "-"}:
        return []
    if text.startswith("["):
        try:
            return [str(v).strip() for v in json.loads(text)]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.replace(",", " ").split() if part.strip()]


# --------------------------------------------------------------------------- #
# Metric adapters
# --------------------------------------------------------------------------- #
def make_metric(scorer: Callable[..., ScoreReport]):
    """A plain float metric, for ``dspy.Evaluate`` and regression tests."""

    def metric(gold, pred, trace=None, **_):
        return scorer(gold, pred).score

    return metric


def _example_id(example) -> str:
    """A stable label for a dataset row, whatever the task calls its key."""
    for field_name in ("artefact", "requirement_id", "id", "name"):
        value = getattr(example, field_name, None)
        if value:
            return str(value)
    return "?"


def evaluate_dataset(program, dataset, scorer: Callable[..., ScoreReport]) -> dict:
    """Run a program over a dataset and aggregate scores and violations.

    Returned alongside the mean is the *violation histogram* — which rules the
    program breaks most often. That histogram is how students decide what to
    optimise next, and it is the honest answer to "why did the score move?".
    """
    scores, violations, rows = [], {}, []
    for ex in dataset:
        pred = program(**ex.inputs())
        report = scorer(ex, pred)
        scores.append(report.score)
        for v in report.violated:
            violations[v] = violations.get(v, 0) + 1
        rows.append(
            {
                "item": _example_id(ex),
                "score": round(report.score, 3),
                "violated": report.violated,
            }
        )
    mean = sum(scores) / len(scores) if scores else 0.0
    return {
        "mean_score": round(mean, 4),
        "n": len(scores),
        "violations": dict(sorted(violations.items(), key=lambda kv: -kv[1])),
        "rows": rows,
    }
