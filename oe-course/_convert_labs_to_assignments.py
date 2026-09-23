"""One-off: convert each chapter's agentic lab into a student/solution assignment pair.

Run once from `oe-course/`:  python _convert_labs_to_assignments.py

What it changes, per chapter, and nothing else:

* inside the agentic-lab builder function only, `exercise(` becomes `task(` -- the
  existing exercises already state a task, ship a starter and assert their own marking
  scheme, which is exactly what a graded task is;
* the function's closing `save(...)` becomes `save_assignment(...)`, which writes the
  student notebook and its `_solution` sibling;
* the module's import line gains `save_assignment` and `task`.

The exercises in the *other* notebooks of each chapter are left alone: they are worked
examples with a disclosed solution, not assignments, and turning them into stubs would
break the chapter's teaching flow.

Kept in the repository rather than run and deleted so the conversion is reviewable --
this is the commit that explains why the labs suddenly have two variants.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

CHAPTERS = Path(__file__).resolve().parent / "chapters"

LAB_SAVE = re.compile(
    r'return save\(cells, HERE / "(?P<nb>[^"]*agentic_lab\.ipynb)"\)')
IMPORT_LINE = re.compile(r"^from oe_course\.nbbuild import .*$", re.MULTILINE)


def lab_function_span(source: str) -> tuple[int, int] | None:
    """Character span of the function whose body saves an agentic-lab notebook."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        start = offsets[node.lineno - 1]
        end = offsets[node.end_lineno]
        if LAB_SAVE.search(source[start:end]):
            return start, end
    return None


def convert(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    span = lab_function_span(source)
    if span is None:
        return "no agentic-lab builder found"

    start, end = span
    body = source[start:end]

    exercises = body.count("exercise(")
    if exercises == 0:
        return "lab builder has no exercises to convert"
    body = body.replace("cells += exercise(", "cells += task(")

    chapter_match = re.search(r'^CHAPTER = (".*")$', source, re.MULTILINE)
    chapter = ast.literal_eval(chapter_match.group(1)) if chapter_match else path.parent.name

    def replace_save(match: re.Match) -> str:
        return (f'return save_assignment(cells, HERE / "{match.group("nb")}",\n'
                f'                           lab_title="{chapter} — agentic lab")')

    body, saves = LAB_SAVE.subn(replace_save, body)
    source = source[:start] + body + source[end:]

    if "from oe_course.assignment import" not in source:
        def add_import(match: re.Match) -> str:
            return (match.group(0)
                    + "\nfrom oe_course.assignment import save_assignment, task  # noqa: E402")
        source, n = IMPORT_LINE.subn(add_import, source, count=1)
        if n == 0:
            return "could not find the oe_course.nbbuild import line"

    path.write_text(source, encoding="utf-8")
    return f"converted {exercises} exercise(s), {saves} save call(s)"


def main() -> int:
    builders = sorted(CHAPTERS.glob("ch*/_build_notebooks.py"))
    builders += sorted(CHAPTERS.glob("ch*/_build_agentic_lab.py"))
    if not builders:
        print(f"no builders under {CHAPTERS}", file=sys.stderr)
        return 1

    failures = 0
    for builder in builders:
        result = convert(builder)
        marker = "  " if result.startswith("converted") else "! "
        if not result.startswith("converted"):
            failures += 1
        print(f"{marker}{builder.parent.name}/{builder.name:24} {result}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
