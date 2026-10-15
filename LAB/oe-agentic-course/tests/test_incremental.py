"""The course's build rule: code is introduced chapter by chapter, never ahead of time.

* every ``agentlab`` module declares ``INTRODUCED_IN`` and a docstring;
* an ``agentlab`` module imports only modules introduced in the same or an earlier
  chapter;
* chapter N (its modules and notebook sources) imports only ``agentlab`` modules
  introduced in chapters <= N, and nothing from another chapter's folder;
* nothing in the course imports the original framework (``oe_course``);
* every notebook source has its built notebook(s) next to it.
"""

import ast
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "agentlab"
CHAPTERS = sorted((ROOT / "chapters").glob("ch[0-9][0-9]_*"))


def introduced() -> dict[str, int]:
    out = {}
    for f in PKG.glob("*.py"):
        mod = importlib.import_module("agentlab" if f.stem == "__init__" else f"agentlab.{f.stem}")
        out[f.stem] = mod.INTRODUCED_IN
    return out


def imports(path: Path) -> list[str]:
    """Every module name a file imports (``from agentlab import x`` counts as agentlab.x)."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            if node.module == "agentlab":
                names += [f"agentlab.{a.name}" for a in node.names
                          if (PKG / f"{a.name}.py").exists()]
    return names


def agentlab_deps(path: Path) -> set[str]:
    return {n.split(".")[1] for n in imports(path) if n.startswith("agentlab.")}


def test_every_module_declares_its_chapter_and_purpose():
    for name, chapter in introduced().items():
        assert isinstance(chapter, int) and chapter >= 1, name
        mod = importlib.import_module("agentlab" if name == "__init__" else f"agentlab.{name}")
        assert (mod.__doc__ or "").strip(), f"agentlab.{name} has no docstring"
        if name != "__init__":
            assert f"Chapter {chapter}" in mod.__doc__, \
                f"agentlab.{name}'s docstring must say why Chapter {chapter} needs it"


def test_modules_never_import_ahead():
    ch = introduced()
    problems = [f"agentlab.{f.stem} (ch{ch[f.stem]}) imports agentlab.{d} (ch{ch[d]})"
                for f in PKG.glob("*.py") for d in agentlab_deps(f) if ch.get(d, 0) > ch[f.stem]]
    assert not problems, "\n".join(problems)


def is_revisit(path: Path) -> bool:
    """A file that brings a later layer back to an earlier chapter's task: the support
    module ``chNN_revisit.py``, or a problem set whose setup cell says ``# revisits:``."""
    return path.stem.endswith("_revisit") or "\n# revisits:" in path.read_text(encoding="utf-8")


def test_chapters_only_use_what_has_been_introduced():
    """No agentlab module from a later chapter, and no other chapter's modules — except
    that a revisit file may import an *earlier* chapter's modules (never a later one's)."""
    ch = introduced()
    other = {folder.name: {f.stem for f in folder.glob("*.py")} for folder in CHAPTERS}
    owner = {stem: int(name[2:4]) for name, stems in other.items() for stem in stems}
    problems = []
    for folder in CHAPTERS:
        n = int(folder.name[2:4])
        foreign = set().union(*(v for k, v in other.items() if k != folder.name)) - other[folder.name]
        for f in folder.glob("*.py"):
            for d in agentlab_deps(f):
                if ch.get(d, 99) > n:
                    problems.append(f"{folder.name}/{f.name} uses agentlab.{d} (ch{ch.get(d)})")
            for name in imports(f):
                top = name.split(".")[0]
                if top not in foreign:
                    continue
                if is_revisit(f) and owner[top] < n:
                    continue
                problems.append(f"{folder.name}/{f.name} imports another chapter's {name}")
    assert not problems, "\n".join(problems)


def test_revisits_only_reach_back():
    """The exception above is real but narrow: at least one revisit exists, and every
    revisit names only earlier chapters."""
    revisits = [f for folder in CHAPTERS for f in folder.glob("*.py") if is_revisit(f)]
    assert revisits
    for f in revisits:
        n = int(f.parent.name[2:4])
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("# revisits:"):
                named = [int(c.strip()[2:4]) for c in line.split(":", 1)[1].split(",")]
                assert all(c < n for c in named), (f.name, line)


def test_the_original_framework_is_not_used():
    hits = [str(f.relative_to(ROOT)) for f in [*PKG.glob("*.py"), *ROOT.glob("chapters/*/*.py")]
            if any(name.split(".")[0] == "oe_course" for name in imports(f))]
    assert not hits, f"still importing oe_course: {hits}"


def test_every_notebook_source_is_built():
    missing = []
    for src in ROOT.glob("chapters/*/[0-9][0-9]_*.py"):
        if src.stem.endswith("_problem_set"):
            n = src.stem.split("_", 1)[0]
            outs = [src.with_name(f"{n}_assignment.ipynb"), src.with_name(f"{n}_solutions.ipynb")]
        elif "# %% solution" in src.read_text(encoding="utf-8"):
            outs = [src.with_suffix(".ipynb"), src.with_name(f"{src.stem}_solutions.ipynb")]
        else:
            outs = [src.with_suffix(".ipynb")]
        missing += [str(o.relative_to(ROOT)) for o in outs if not o.exists()]
    assert not missing, f"run python tools/build_notebooks.py: {missing}"


def test_problem_sets_have_matching_stubs_and_solutions():
    for src in ROOT.glob("chapters/*/[0-9][0-9]_problem_set.py"):
        cells = re.split(r"^(?=# %%)", src.read_text(encoding="utf-8"), flags=re.M)
        stubs = [c for c in cells if c.startswith("# %% assignment\n")]
        solutions = [c for c in cells if c.startswith("# %% solution\n")]
        assert len(stubs) + 1 == len(solutions), src.name      # +1: the final assert cell
        assert all("raise NotImplementedError" in c for c in stubs), src.name


def test_book_exercises_hide_their_solutions():
    """Every book exercise: a starter for you, a solution in the _solutions notebook, and a
    shared check on the names your code defines."""
    for src in ROOT.glob("chapters/*/0[1-4]_*.py"):
        if src.stem.endswith("_problem_set"):
            continue
        text = src.read_text(encoding="utf-8")
        exercises = re.findall(r"^# ### Exercise (\S+) —", text, re.M)
        if not exercises:
            continue
        assert "<summary>Solution" not in text, f"{src.name}: a solution is still inline"
        checks = re.findall(r"with CHECK\.check\('([^']+)'", text)
        assert checks == exercises, (src.name, exercises, checks)
