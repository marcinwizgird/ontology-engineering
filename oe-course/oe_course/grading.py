"""Runtime marking for the assignment notebooks.

Every auto-graded problem ends in a cell of the form::

    with GRADER.check("B2", points=6):
        assert ...

The context manager records PASS or FAIL (with the reason) and prints one line.
It does **not** re-raise, so a student can run the whole notebook and see every
result at once; the final self-test cell prints the table and the auto-graded
subtotal. Written answers are marked by hand against the rubric, and the table
says so rather than pretending to grade prose.
"""

from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field

__all__ = ["Grader", "CheckResult"]


@dataclass
class CheckResult:
    problem: str
    points: float
    passed: bool
    reason: str = ""


@dataclass
class Grader:
    """Collects the outcome of every ``check`` cell in one notebook."""

    title: str = ""
    results: dict[str, CheckResult] = field(default_factory=dict)

    @contextmanager
    def check(self, problem: str, points: float):
        try:
            yield
        except NotImplementedError:
            self._record(problem, points, False, "not implemented yet")
        except AssertionError as exc:
            self._record(problem, points, False, str(exc) or _last_line())
        except Exception as exc:  # a crash in the checked code is a failed check
            self._record(problem, points, False, f"{type(exc).__name__}: {exc}")
        else:
            self._record(problem, points, True)

    def _record(self, problem: str, points: float, passed: bool, reason: str = "") -> None:
        self.results[problem] = CheckResult(problem, points, passed, reason)
        mark = "PASS" if passed else "FAIL"
        earned = points if passed else 0
        suffix = f" -- {reason}" if reason else ""
        print(f"[{problem}] {mark}  ({earned:g}/{points:g} auto-graded pts){suffix}")

    # -- reporting ----------------------------------------------------------
    @property
    def earned(self) -> float:
        return sum(r.points for r in self.results.values() if r.passed)

    @property
    def available(self) -> float:
        return sum(r.points for r in self.results.values())

    def all_passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results.values())

    def summary(self, expected: list[str] | None = None) -> str:
        """Print and return the self-test table.

        ``expected`` lists every auto-graded problem id, so a check cell that was
        never run shows up as NOT RUN instead of silently vanishing.
        """
        ids = list(expected or []) + [p for p in self.results if p not in (expected or [])]
        lines = [f"Self-test -- {self.title}".rstrip(" -"), ""]
        for pid in ids:
            r = self.results.get(pid)
            if r is None:
                lines.append(f"  {pid:6s} NOT RUN")
            else:
                status = "PASS" if r.passed else "FAIL"
                lines.append(f"  {pid:6s} {status:4s}  {r.points if r.passed else 0:g}/{r.points:g}"
                             + (f"   {r.reason[:90]}" if r.reason else ""))
        lines += ["", f"Auto-graded subtotal: {self.earned:g} / {self.available:g} pts "
                      "(written answers are marked by hand against the rubric)."]
        text = "\n".join(lines)
        print(text)
        return text

    def assert_all_passed(self, expected: list[str] | None = None) -> None:
        missing = [p for p in (expected or []) if p not in self.results]
        failed = [r.problem for r in self.results.values() if not r.passed]
        assert not missing and not failed, f"not run: {missing}; failed: {failed}"


def _last_line() -> str:
    lines = traceback.format_exc().strip().splitlines()
    return lines[-1] if lines else "assertion failed"
