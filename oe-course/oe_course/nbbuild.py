"""Helpers for generating the course notebooks from Python source.

The notebooks are *build artefacts*: each chapter has a ``_build_notebooks.py``
that emits them. Authoring in Python rather than editing ``.ipynb`` by hand
keeps the diffs reviewable, keeps prose and code in one place, and makes a
whole-course change (a renamed API, a new setup cell) a one-line edit instead of
a hunt through JSON.

The exercise helpers encode the course's format: every exercise states the task,
gives a runnable starter, and ships an *executable* solution whose assertions
are the grading criteria. An exercise whose solution does not assert anything is
not an exercise — it is a suggestion.

``oe_course.assignment`` builds each chapter's problem set on top of these
helpers: one authored cell sequence, saved as an assignment notebook and a
solutions notebook. Import it from its own module.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

__all__ = ["md", "code", "save", "SETUP_CELL", "header", "exercise", "learning_outcomes"]



#: Standard first code cell: puts the repo root on the path and reports the environment.
SETUP_CELL = """\
import sys, os, json, textwrap
from pathlib import Path

# Make the repo root importable no matter where Jupyter was started.
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate))
        break

import oe_course
print(json.dumps(oe_course.describe_environment(), indent=1))\
"""


def md(text: str):
    return new_markdown_cell(text)


def code(text: str):
    return new_code_cell(text)


def save(cells: list, path: str | Path) -> Path:
    """Write cells to a notebook with a python3 kernelspec."""
    nb = new_notebook(cells=cells)
    nb.metadata.kernelspec = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    nb.metadata.language_info = {"name": "python"}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, str(path))
    return path


def header(chapter: str, notebook_title: str, book_section: str, blurb: str) -> list:
    """The standard opening: title, provenance, and a setup cell."""
    return [
        md(
            f"# {chapter}\n"
            f"### {notebook_title}\n\n"
            f"*Book reference: {book_section}*\n\n"
            f"{blurb}"
        ),
        code(SETUP_CELL),
    ]


def learning_outcomes(items: list[str]) -> str:
    body = "\n".join(f"{i}. {text}" for i, text in enumerate(items, 1))
    return f"**By the end of this notebook you can:**\n\n{body}"


def exercise(
    number: str,
    title: str,
    task: str,
    starter: str,
    solution: str,
    *,
    hint: str = "",
) -> list:
    """One exercise: task, starter cell, then a runnable, asserting solution."""
    cells = [md(f"### Exercise {number} — {title}\n\n{task}")]
    if hint:
        cells.append(md(f"> **Hint.** {hint}"))
    cells.append(code(starter))
    cells.append(md(f"<details>\n<summary>Solution {number}</summary>\n\n"
                    f"Run the cell below to check your answer against the reference "
                    f"implementation. The assertions are the grading criteria.\n\n</details>"))
    cells.append(code(solution))
    return cells
