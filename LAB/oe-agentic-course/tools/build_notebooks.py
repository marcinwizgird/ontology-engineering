"""Turn the notebook sources (``chapters/*/NN_*.py``) into ``.ipynb`` files.

The sources are plain Python in the "percent" format that VS Code, PyCharm and
Jupytext all understand, so a notebook can be read and diffed without Jupyter:

    # %% [markdown]
    # # A heading
    # Some prose.

    # %%
    print("a code cell")

**Problem sets** (``NN_problem_set.py``) are authored once and built twice. A cell
whose marker ends in ``assignment`` or ``solution`` goes into that notebook only;
every other cell (the brief, the provided code, the marking cells) goes into both,
so the two versions cannot drift apart::

    # %% assignment                    -> NN_assignment.ipynb only (a TODO stub)
    # %% solution                      -> NN_solutions.ipynb only (the worked answer)
    # %% [markdown] solution           -> the model answer to a written question

**Book notebooks with exercises** use the same tags: ``NN_name.py`` builds ``NN_name.ipynb``
(your starters, and a check after each exercise that tests *your* names) and
``NN_name_solutions.ipynb`` (the worked solutions, ending with every check passed).

Only files whose name starts with two digits are notebooks; other ``.py`` files in a
chapter (``corpus.py``, ``ch02_toolkit.py`` ...) are that chapter's modules.

    python tools/build_notebooks.py                 # every chapter
    python tools/build_notebooks.py ch02            # chapters whose folder matches
    python tools/build_notebooks.py --execute ch01  # also run them (problem sets call the live API!)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parent.parent
CELL = re.compile(r"^# %%(?P<md> \[markdown\])?(?: (?P<variant>assignment|solution))?\s*$", re.M)


def cells_of(source: str, variant: str | None = None) -> list:
    """Split a percent-format source into cells, keeping only ``variant``'s tagged cells."""
    marks = list(CELL.finditer(source))
    cells = []
    for i, m in enumerate(marks):
        if m.group("variant") and m.group("variant") != variant:
            continue
        body = source[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(source)]
        body = body.strip("\n")
        if m.group("md"):
            text = "\n".join(line[2:] if line.startswith("# ") else line.lstrip("#")
                             for line in body.splitlines())
            cells.append(nbformat.v4.new_markdown_cell(text))
        elif body.strip():
            cells.append(nbformat.v4.new_code_cell(body))
    return cells


def _write(cells: list, out: Path, execute: bool, cwd: Path) -> Path:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3",
                                 "language": "python"}
    nb.cells = cells
    if execute:
        from nbclient import NotebookClient
        NotebookClient(nb, timeout=3600, resources={"metadata": {"path": str(cwd)}}).execute()
    nbformat.write(nb, out)
    return out


def build(path: Path, execute: bool = False) -> list[Path]:
    """Build one source into its notebook(s); returns the files written."""
    source = path.read_text(encoding="utf-8")
    if path.stem.endswith("_problem_set"):
        number = path.stem.split("_", 1)[0]
        return [_write(cells_of(source, "assignment"), path.with_name(f"{number}_assignment.ipynb"),
                       False, path.parent),       # a student notebook stops at its first TODO
                _write(cells_of(source, "solution"), path.with_name(f"{number}_solutions.ipynb"),
                       execute, path.parent)]
    if CELL.search(source) and any(m.group("variant") for m in CELL.finditer(source)):
        return [_write(cells_of(source, "assignment"), path.with_suffix(".ipynb"), execute,
                       path.parent),
                _write(cells_of(source, "solution"), path.with_name(f"{path.stem}_solutions.ipynb"),
                       execute, path.parent)]
    return [_write(cells_of(source), path.with_suffix(".ipynb"), execute, path.parent)]


def sources(selectors: list[str]) -> list[Path]:
    found = sorted(ROOT.glob("chapters/*/[0-9][0-9]_*.py"))
    if selectors:
        found = [p for p in found if any(s in p.parent.name for s in selectors)]
    return found


if __name__ == "__main__":
    args = sys.argv[1:]
    execute = "--execute" in args
    for src in sources([a for a in args if a != "--execute"]):
        for out in build(src, execute):
            print("built", out.relative_to(ROOT))
