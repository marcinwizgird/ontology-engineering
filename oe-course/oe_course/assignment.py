"""Build a chapter's problem set as two notebooks — assignment and solutions — from one source.

A problem set is authored once, as a single sequence of cells, with a
:class:`ProblemSet`. Cells marked for one variant (a TODO stub, a worked
solution, a model answer) are filtered into their notebook; everything else —
the brief, the setup, the provided code, the checks — appears in both, so the
two versions cannot drift apart.

The format follows the course's problem-set convention:

* a header stating the scenario, level, total points, effort **and API budget**;
* lettered parts (``Part A — ...``) of numbered problems (``A1. Title (8 pts)``);
* code problems ship a ``# TODO`` stub ending in ``raise NotImplementedError``
  in the assignment and the worked implementation in the solutions;
* written problems get a *"Your answer"* cell in the assignment and a
  *"Solution."* cell in the solutions;
* auto-graded problems end in a ``with GRADER.check("A1", points=...)`` cell —
  the marking scheme, identical in both variants;
* a grading rubric and a final self-test close the notebook.

Only the solutions notebook is expected to run clean end to end (it asserts
every check passed). An assignment notebook stops at its first stub, by design.
"""

from __future__ import annotations

import copy
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .nbbuild import code, md, save

__all__ = ["ProblemSet", "STUDENT", "SOLUTION", "VARIANT_KEY", "ASSIGNMENT_SETUP"]

STUDENT = "student"
SOLUTION = "solution"

#: Cell-metadata key marking a cell as belonging to one variant only.
VARIANT_KEY = "oe_variant"

STUB_SENTINEL = "raise NotImplementedError"

#: First code cell of every problem set: path setup, environment, grader.
ASSIGNMENT_SETUP = """\
import sys, json, logging
from pathlib import Path

# Make the course root and this chapter importable no matter where Jupyter started.
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate))
        break
sys.path.insert(0, str(here))

import oe_course
from oe_course import config
from oe_course.grading import Grader

print(json.dumps(oe_course.describe_environment(), indent=1))
config.require_credentials()          # this problem set calls the live Anthropic API
logging.getLogger("dspy").setLevel(logging.WARNING)
GRADER = Grader({title!r})\
"""


def _only(cell, which: str):
    cell.metadata[VARIANT_KEY] = which
    return cell


@dataclass
class _Problem:
    pid: str
    title: str
    points: float
    auto_points: float = 0.0
    part: str = ""


@dataclass
class ProblemSet:
    """One chapter's problem set, authored once and saved as two notebooks.

    Parameters
    ----------
    chapter:   e.g. ``"Chapter 2 — First-Order Logic and Reasoning"``
    title:     the problem set's own title (the scenario), e.g.
               ``"Formalising a compliance policy with Claude"``
    coverage:  markdown — which book sections and course notebooks it exercises
    scenario:  markdown — the real-world brief the student is working to
    effort:    e.g. ``"8–10 hours"``
    api_budget: e.g. ``"≈ $3–6 on claude-opus-5 (solutions run: ≈ $4)"``
    """

    chapter: str
    title: str
    coverage: str
    scenario: str
    effort: str
    api_budget: str
    level: str = ("Graduate (practice-first). Combines conceptual analysis with building, "
                  "measuring and optimising a real Claude-backed agent.")
    submission: str = ""
    cells: list = field(default_factory=list)
    problems: list[_Problem] = field(default_factory=list)
    _part: str = ""

    # -- authoring ------------------------------------------------------------
    def setup(self, extra: str = "") -> None:
        """The setup cell (always first), plus chapter-specific imports."""
        src = ASSIGNMENT_SETUP.format(title=f"{self.chapter} — {self.title}")
        if extra.strip():
            src += "\n\n" + textwrap.dedent(extra).strip()
        self.cells.append(code(src))

    def md(self, text: str) -> None:
        """Shared markdown (both variants)."""
        self.cells.append(md(textwrap.dedent(text).strip()))

    def code(self, src: str) -> None:
        """Shared, provided code (both variants) — worked examples, data, helpers."""
        self.cells.append(code(textwrap.dedent(src).strip()))

    def part(self, letter: str, title: str, intro: str = "") -> None:
        self._part = letter
        text = f"---\n\n## Part {letter} — {title}"
        if intro.strip():
            text += "\n\n" + textwrap.dedent(intro).strip()
        self.cells.append(md(text))

    def problem(self, pid: str, title: str, points: float, brief: str, *,
                auto_points: float = 0.0) -> None:
        """Open a problem: the heading and brief. ``auto_points`` of ``points`` are
        earned by the check cell; the rest are marked by hand against the rubric."""
        if any(p.pid == pid for p in self.problems):
            raise ValueError(f"duplicate problem id {pid}")
        if auto_points > points:
            raise ValueError(f"{pid}: auto_points {auto_points} > points {points}")
        self.problems.append(_Problem(pid, title, points, auto_points, self._part))
        self.cells.append(md(f"### {pid}. {title} ({points:g} pts)\n\n"
                             + textwrap.dedent(brief).strip()))

    def todo(self, stub: str, solution: str) -> None:
        """A code cell the student completes: stub in one variant, solution in the other."""
        stub = textwrap.dedent(stub).strip()
        if STUB_SENTINEL not in stub:
            stub += f"\n\n{STUB_SENTINEL}"
        self.cells.append(_only(code(stub), STUDENT))
        self.cells.append(_only(code(textwrap.dedent(solution).strip()), SOLUTION))

    def written(self, answer: str, prompt: str = "Your answer") -> None:
        """A written answer: an empty answer cell, or the model answer."""
        self.cells.append(_only(md(f"**{prompt}:**\n\n*(Write your answer here.)*"), STUDENT))
        self.cells.append(_only(md("**Solution.**\n\n" + textwrap.dedent(answer).strip()),
                                SOLUTION))

    def check(self, pid: str, source: str) -> None:
        """The marking-scheme cell for a problem's auto-graded points."""
        problem = next((p for p in self.problems if p.pid == pid), None)
        if problem is None:
            raise ValueError(f"check for unknown problem {pid}")
        if problem.auto_points <= 0:
            raise ValueError(f"{pid} has no auto_points; give the problem some or drop the check")
        body = textwrap.indent(textwrap.dedent(source).strip(), "    ")
        self.cells.append(code(
            f"# Marking scheme for {pid} -- do not edit.\n"
            f"with GRADER.check({pid!r}, points={problem.auto_points:g}):\n{body}"))

    # -- derived sections -----------------------------------------------------
    @property
    def total_points(self) -> float:
        return sum(p.points for p in self.problems)

    @property
    def auto_ids(self) -> list[str]:
        return [p.pid for p in self.problems if p.auto_points > 0]

    def _header(self, which: str, counterpart: str) -> list:
        auto = sum(p.auto_points for p in self.problems)
        parts: dict[str, float] = {}
        for p in self.problems:
            parts[p.part] = parts.get(p.part, 0) + p.points
        split = " / ".join(f"Part {k} {v:g}" for k, v in parts.items())
        variant = ("" if which == STUDENT else " — Solutions")
        lines = [
            f"# Problem Set: {self.title}{variant}",
            f"### {self.chapter}",
            "",
            f"**Topic coverage:** {self.coverage}",
            "",
            f"**Level:** {self.level}",
            "",
            f"**Total points:** {self.total_points:g} ({split}); {auto:g} pts are "
            f"auto-graded by the check cells, the rest are marked by hand against the "
            f"rubric. **Estimated effort:** {self.effort}.",
            "",
            f"**API budget:** {self.api_budget} Every model call in this notebook is a "
            f"billed request to Anthropic; the cost lines the problems ask for are part "
            f"of the answer.",
            "",
            "## The brief",
            "",
            textwrap.dedent(self.scenario).strip(),
            "",
        ]
        if which == STUDENT:
            lines += [
                "## Submission requirements",
                "",
                textwrap.dedent(self.submission).strip() or (
                    "1. **This notebook, executed top to bottom**, with every `TODO` "
                    "implemented and every *Your answer* cell written.\n"
                    "2. **The artefacts it saves** under `course/artifacts/` "
                    "(optimised instructions, run logs) — they are evidence, not "
                    "by-products.\n"
                    "3. **Honest reporting.** A number without its split, its sample "
                    "size and its cost earns no credit. Report the runs you did, "
                    "including the ones that did not improve anything."),
                "",
                "The check cells are the marking scheme for the auto-graded points; do "
                "not edit them. The final self-test prints your auto-graded subtotal.",
                "",
                f"> Solutions: `{counterpart}` — do not open it until you have attempted "
                f"every problem.",
            ]
        else:
            lines += [
                f"> This is the **instructor solutions** notebook. It runs clean end to "
                f"end against the live API and ends by asserting that every check "
                f"passed. Student version: `{counterpart}`.",
                "",
                "> Answers produced by a live model vary between runs. The model answers "
                "below describe what a good submission shows; the check cells test "
                "properties that hold for any competent run, not recorded outputs.",
            ]
        return [md("\n".join(lines))]

    def _rubric(self) -> list:
        rows = ["| Part | Problem | Auto | Manual | Pts |", "|---|---|---|---|---|"]
        for p in self.problems:
            rows.append(f"| {p.part} | {p.pid} {p.title} | {p.auto_points:g} | "
                        f"{p.points - p.auto_points:g} | {p.points:g} |")
        rows.append(f"| **Total** | | | | **{self.total_points:g}** |")
        return [md("---\n\n## Grading rubric\n\n" + "\n".join(rows) +
                   "\n\n*Manual* points are for the written answers and for the quality of "
                   "the engineering evidence (splits, sample sizes, cost, honest "
                   "negative results).")]

    def _self_test(self) -> list:
        cells = [
            md("---\n\n## Self-test\n\nRe-run this cell after finishing. It lists every "
               "auto-graded problem and whether its check passed."),
            code(f"AUTO_GRADED = {self.auto_ids!r}\n_ = GRADER.summary(AUTO_GRADED)"),
        ]
        cells.append(_only(code("GRADER.assert_all_passed(AUTO_GRADED)"), SOLUTION))
        return cells

    # -- output -----------------------------------------------------------------
    def save(self, directory: str | Path, number: str) -> tuple[Path, Path]:
        """Write ``{number}_assignment.ipynb`` and ``{number}_solutions.ipynb``."""
        directory = Path(directory)
        student_path = directory / f"{number}_assignment.ipynb"
        solution_path = directory / f"{number}_solutions.ipynb"
        body = self.cells + self._rubric() + self._self_test()
        student = save(self._header(STUDENT, solution_path.name) + _filter(body, STUDENT),
                       student_path)
        solution = save(self._header(SOLUTION, student_path.name) + _filter(body, SOLUTION),
                        solution_path)
        return student, solution


def _filter(cells: list, which: str) -> list:
    out = []
    for cell in cells:
        variant = cell.get("metadata", {}).get(VARIANT_KEY)
        if variant is None or variant == which:
            clone = copy.deepcopy(cell)
            clone.metadata.pop(VARIANT_KEY, None)
            out.append(clone)
    return out
