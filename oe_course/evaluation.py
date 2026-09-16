"""Evaluation datasets and metrics — deterministic, LLM-judged, and GEPA-shaped.

An agent you cannot score is an agent you cannot improve, so the course treats
the metric as a first-class engineering artefact rather than an afterthought.
Three kinds appear, and students build all three:

**Deterministic metrics** (:func:`set_f1`, :func:`triage_scorer`) compare the
agent's claims against gold labels. Cheap, reproducible, and the only sound
basis for a regression test. Their weakness: they cannot judge *prose*.

**LLM-as-judge** (:func:`judge`) scores the qualities a set comparison cannot —
is the justification grounded in evidence the agent actually gathered, or
plausible-sounding fabrication? Offline it degrades to an explicit rubric proxy
(:class:`RubricJudge`), which is stated plainly rather than dressed up as a
model.

**GEPA feedback metrics** (:func:`make_gepa_metric`) return a *score plus a
textual diagnosis*. This is the part people skip and then wonder why
optimisation stalls: GEPA's reflection step can only propose a better
instruction if the metric tells it what went wrong. Every scorer here emits
``MISSING RULE <id>: <what to do instead>`` lines for exactly that reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from oe_course import config

__all__ = [
    "ScoreReport",
    "set_f1",
    "exact_match",
    "answer_set_match",
    "triage_scorer",
    "build_triage_dataset",
    "make_metric",
    "make_gepa_metric",
    "judge",
    "RubricJudge",
    "evaluate_dataset",
]


# --------------------------------------------------------------------------- #
# The unit every scorer returns
# --------------------------------------------------------------------------- #
@dataclass
class ScoreReport:
    """A score, a human-readable diagnosis, and the rules that were violated.

    ``violated`` is what makes the report usable by GEPA: each id names a rule
    in the task's :class:`oe_course.llm.RuleBook`, and the feedback text spells
    out the fix so the reflection step has something concrete to write down.
    """

    score: float
    notes: list[str] = field(default_factory=list)
    violated: list[str] = field(default_factory=list)

    def feedback(self, rulebook=None) -> str:
        lines = list(self.notes)
        if rulebook is not None:
            for rule_id in self.violated:
                try:
                    lines.append(rulebook[rule_id].missing_line())
                except KeyError:
                    lines.append(f"MISSING RULE {rule_id}: (no description registered)")
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


def answer_set_match(predicted_rows: Sequence[dict], gold_rows: Sequence[dict]) -> float:
    """Compare two SPARQL SELECT answer sets, order-insensitively."""
    def norm(rows):
        return {tuple(sorted((k, str(v)) for k, v in row.items())) for row in rows}

    p, g = norm(predicted_rows), norm(gold_rows)
    if not p and not g:
        return 1.0
    return len(p & g) / len(p | g)


# --------------------------------------------------------------------------- #
# The Chapter 1 task: triage an ontology
# --------------------------------------------------------------------------- #
#: Rule ids the triage task can violate. Kept next to the scorer so the metric
#: and the rulebook cannot drift apart.
TRIAGE_RULES = {
    "cite-spectrum-evidence": (
        "State the spectrum level using the exact vocabulary "
        "(controlled-vocabulary, taxonomy, thesaurus, formal-ontology) and back it "
        "with counts from the metrics tool."
    ),
    "report-all-smells": (
        "Report every defect the scanner returns, by its exact id; do not "
        "summarise or silently drop low-severity ones."
    ),
    "no-unsupported-claims": (
        "Do not report a defect id that the scanner did not return."
    ),
    "ground-in-tool-output": (
        "Base the justification only on tool output actually gathered this "
        "episode; run the scanner before claiming an artefact is clean."
    ),
}


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


def triage_scorer(gold, pred) -> ScoreReport:
    """Score a triage answer: half the mark for the level, half for the defects.

    ``gold`` needs ``level`` and ``smells``; ``pred`` needs ``level`` and
    ``smells`` (any of the formats :func:`parse_label_list` accepts).
    """
    gold_level = str(getattr(gold, "level", "")).strip()
    pred_level = str(getattr(pred, "level", "")).strip()
    gold_smells = parse_label_list(getattr(gold, "smells", None))
    pred_smells = parse_label_list(getattr(pred, "smells", None))

    notes: list[str] = []
    violated: list[str] = []

    level_score = exact_match(pred_level, gold_level)
    if level_score < 1.0:
        notes.append(
            f"Spectrum level wrong: answered {pred_level!r}, correct answer {gold_level!r}."
        )
        violated.append("cite-spectrum-evidence")

    precision, recall, f1 = set_f1(pred_smells, gold_smells)
    missed = sorted(set(gold_smells) - set(pred_smells))
    invented = sorted(set(pred_smells) - set(gold_smells))
    if missed:
        notes.append(f"Failed to report these real defects: {missed}.")
        violated.append("report-all-smells")
    if invented:
        notes.append(f"Reported defects that the scanner did not find: {invented}.")
        violated.append("no-unsupported-claims")
    if not pred_smells and gold_smells:
        violated.append("ground-in-tool-output")

    score = 0.5 * level_score + 0.5 * f1
    notes.append(
        f"level={level_score:.0f} smell_precision={precision:.2f} "
        f"smell_recall={recall:.2f} smell_f1={f1:.2f}"
    )
    # de-duplicate while preserving order
    violated = list(dict.fromkeys(violated))
    return ScoreReport(score=score, notes=notes, violated=violated)


def build_triage_dataset(split: str = "all"):
    """The labelled triage dataset as ``dspy.Example`` objects.

    ``split`` is ``"train"`` (first 6), ``"dev"`` (rest) or ``"all"``. The split
    is deliberately by artefact, never by random row: leaking an artefact across
    the split would let an optimiser memorise its answer.
    """
    import dspy

    from oe_course.data import corpus

    examples = [
        dspy.Example(
            artefact=art.name,
            level=art.gold_level,
            smells=sorted(art.gold_smells),
            note=art.note,
        ).with_inputs("artefact")
        for art in corpus.CORPUS
    ]
    if split == "train":
        return examples[:6]
    if split == "dev":
        return examples[6:]
    return examples


# --------------------------------------------------------------------------- #
# Metric adapters
# --------------------------------------------------------------------------- #
def make_metric(scorer: Callable[..., ScoreReport]):
    """A plain float metric, for ``dspy.Evaluate`` and regression tests."""

    def metric(gold, pred, trace=None, **_):
        return scorer(gold, pred).score

    return metric


def make_gepa_metric(scorer: Callable[..., ScoreReport], rulebook=None):
    """A GEPA feedback metric: ``dspy.Prediction(score=..., feedback=...)``.

    GEPA calls this with ``(gold, pred, trace, pred_name, pred_trace)`` and uses
    the feedback string to write a better instruction. The rulebook turns each
    violated rule id into a concrete ``MISSING RULE`` line.
    """
    import dspy

    def metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
        report = scorer(gold, pred)
        return dspy.Prediction(score=report.score, feedback=report.feedback(rulebook))

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


# --------------------------------------------------------------------------- #
# LLM-as-judge
# --------------------------------------------------------------------------- #
@dataclass
class RubricJudge:
    """The offline stand-in for an LLM judge — an explicit, checkable rubric.

    It is *not* pretending to be a model. It scores the three properties the
    course cares about in a written justification, so the judging machinery
    (dataset, aggregation, disagreement analysis) can be exercised offline:

    1. does the report name the correct level?
    2. does it mention each defect it claims, by id?
    3. does it cite numeric evidence rather than asserting?
    """

    def __call__(self, task: str, gold: str, report: str) -> ScoreReport:
        text = (report or "").lower()
        notes, points = [], 0.0

        if gold and gold.lower() in text:
            points += 0.4
        else:
            notes.append(f"Report does not state the expected level {gold!r}.")

        if any(ch.isdigit() for ch in text):
            points += 0.3
        else:
            notes.append("Report cites no numeric evidence from the metrics tool.")

        if "because" in text or "evidence" in text or "found" in text:
            points += 0.3
        else:
            notes.append("Report asserts a conclusion without explaining the reasoning.")

        return ScoreReport(score=round(points, 3), notes=notes)


def judge(task: str, gold: str, report: str) -> ScoreReport:
    """Score a written justification — live LLM judge, or the offline rubric."""
    if config.offline():
        return RubricJudge()(task, gold, report)

    import dspy

    class JudgeJustification(dspy.Signature):
        """Score how well a written ontology review is grounded in evidence.

        Award credit only for claims the report supports with specific numbers
        or named terms. Penalise confident claims with no cited evidence.
        """

        task: str = dspy.InputField(desc="what the agent was asked to do")
        expected: str = dspy.InputField(desc="the ground-truth answer")
        report: str = dspy.InputField(desc="the agent's written justification")
        score: float = dspy.OutputField(desc="a number between 0.0 and 1.0")
        critique: str = dspy.OutputField(desc="one or two sentences on what to fix")

    result = dspy.Predict(JudgeJustification)(task=task, expected=gold, report=report)
    try:
        score = max(0.0, min(1.0, float(result.score)))
    except (TypeError, ValueError):
        score = 0.0
    return ScoreReport(score=score, notes=[str(result.critique)])
