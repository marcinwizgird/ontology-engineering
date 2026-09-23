"""Build an agentic lab as two notebooks — student and solution — from one source.

A lab is authored once, as a single sequence of cells. `task` marks the student stub as
belonging to one variant and the worked implementation to the other; `save_assignment`
writes both notebooks by filtering that sequence. Everything not marked — the prose, the
setup, the worked examples, the checks — appears in both, so the two versions cannot
drift: there is one authored artefact and two views of it.

Keeping the checks in **both** variants is the point of the design. In the solution
notebook they pass, which proves the reference implementation actually satisfies the
marking scheme. In the student notebook they fail until the task is done, which is what
makes them a marking scheme rather than a suggestion.

One consequence worth knowing before wiring this into CI: only the `_solution` notebooks
execute clean. A student notebook is *supposed* to raise `NotImplementedError`.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

from .nbbuild import code, md, save

__all__ = ["task", "save_assignment", "assignment_banner", "split_solution",
           "STUDENT", "SOLUTION", "VARIANT_KEY"]

STUDENT = "student"
SOLUTION = "solution"

#: Cell-metadata key marking a cell as belonging to one variant only.
VARIANT_KEY = "oe_variant"

STUB_SENTINEL = "raise NotImplementedError"


def _only(cell, which: str):
    """Mark a cell as appearing in one variant only."""
    cell.metadata[VARIANT_KEY] = which
    return cell


def split_solution(solution: str) -> tuple[str, str]:
    """Separate a worked solution into its implementation and its assertions.

    Only *top-level* asserts are lifted. An assert nested inside a loop or a function is
    part of how that code works, and pulling it out into a later cell would either break
    it or quietly stop checking anything — so those stay where the author put them.

    This exists because the course's exercises already ship implementation and assertions
    in one cell. The assertions were always the marking scheme; the two-variant build just
    needs them in a cell of their own, and deriving that mechanically means a converted
    exercise marks exactly what its author intended.
    """
    try:
        tree = ast.parse(solution)
    except SyntaxError:
        return solution, ""          # a fragment, not a module: leave it alone

    assert_lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.Assert):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                assert_lines.add(line)

    lines = solution.splitlines()
    implementation = [l for i, l in enumerate(lines, 1) if i not in assert_lines]
    checks = [l for i, l in enumerate(lines, 1) if i in assert_lines]
    return "\n".join(implementation).rstrip(), "\n".join(checks).rstrip()


def task(
    number: str,
    title: str,
    brief: str,
    stub: str,
    solution: str,
    *,
    checks: str | None = None,
    hint: str = "",
) -> list:
    """One graded task: the brief, a student stub, the worked solution, and the checks.

    The stub goes only to the student notebook and the solution only to the solution
    notebook. `checks` is what actually marks the work, so a task without them is only a
    suggestion — the same rule `nbbuild.exercise` follows.

    Call it with the same arguments as `nbbuild.exercise` and it does the right thing:
    the assertions are lifted out of the solution into their own cell, and the stub gets
    a `NotImplementedError` to replace. Pass `checks` explicitly when the solution has no
    top-level assertions of its own.
    """
    if checks is None:
        solution, checks = split_solution(solution)
    if not checks.strip():
        raise ValueError(
            f"task {number} ({title!r}) has no checks: its solution contains no top-level "
            f"assertions, so nothing would mark the student's work. Pass checks= "
            f"explicitly.")
    if STUB_SENTINEL not in stub:
        # The student must have something to replace. Appending it here rather than
        # demanding it in every call site keeps a converted exercise a one-word change.
        stub = stub.rstrip() + f"\n\n{STUB_SENTINEL}\n"

    cells = [md(f"### Task {number} — {title}\n\n{brief}")]
    if hint:
        cells.append(md(f"> **Hint.** {hint}"))
    cells.append(_only(code(stub), STUDENT))
    cells.append(_only(code(solution), SOLUTION))
    if checks:
        cells.append(md(
            f"**Checks for Task {number}.** These assertions are the marking scheme. "
            f"They run in both variants — here they pass once your implementation is "
            f"right."))
        cells.append(code(checks))
    return cells


def assignment_banner(which: str, lab_title: str, task_count: int,
                      counterpart: str) -> list:
    """The opening cell: which variant this is, and what the reader is meant to do."""
    plural = "s" if task_count != 1 else ""
    if which == STUDENT:
        body = (
            f"# 📝 Assignment — {lab_title}\n\n"
            f"This is the **student** notebook. It contains {task_count} graded "
            f"task{plural}.\n\n"
            f"Work top to bottom. Where you meet a **Task**, replace the "
            f"`NotImplementedError` with your implementation and run the checks cell that "
            f"follows. **The assertions in the checks cells are the marking scheme** — "
            f"when they all pass, the assignment is complete.\n\n"
            f"Cells outside the tasks are worked examples. Read and run them: they build "
            f"what the tasks need.\n\n"
            f"> Worked solutions: [`{counterpart}`]({counterpart})"
        )
    else:
        body = (
            f"# ✅ Solutions — {lab_title}\n\n"
            f"This is the **solution** notebook: the same lab with all {task_count} "
            f"task{plural} worked. It runs clean end to end, which is what proves the "
            f"reference implementations satisfy the marking scheme.\n\n"
            f"> Student version: [`{counterpart}`]({counterpart})"
        )
    return [md(body)]


def _filter(cells: list, which: str) -> list:
    """The cells belonging to one variant, with the variant marker stripped."""
    out = []
    for cell in cells:
        variant = cell.get("metadata", {}).get(VARIANT_KEY)
        if variant is None or variant == which:
            clone = copy.deepcopy(cell)
            clone.metadata.pop(VARIANT_KEY, None)
            out.append(clone)
    return out


def count_tasks(cells: list) -> int:
    """How many tasks a cell sequence carries, counted from the student stubs."""
    return sum(1 for c in cells
               if c.get("metadata", {}).get(VARIANT_KEY) == STUDENT
               and c.get("cell_type") == "code"
               and STUB_SENTINEL in c.get("source", ""))


def save_assignment(cells: list, path: str | Path, *, lab_title: str,
                    task_count: int | None = None) -> tuple[Path, Path]:
    """Write the student notebook and its `_solution` sibling from one cell list.

    `task_count` defaults to the number of stubs actually present, so the banner cannot
    claim a different number of tasks from the one the notebook contains.
    """
    path = Path(path)
    if task_count is None:
        task_count = count_tasks(cells)
    solution_path = path.with_name(f"{path.stem}_solution{path.suffix}")

    student = save(
        assignment_banner(STUDENT, lab_title, task_count, solution_path.name)
        + _filter(cells, STUDENT), path)
    solution = save(
        assignment_banner(SOLUTION, lab_title, task_count, path.name)
        + _filter(cells, SOLUTION), solution_path)
    return student, solution
