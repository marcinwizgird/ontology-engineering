"""agentlab: the course's code, grown one chapter at a time.

The original course loaded its whole framework (``oe_course``) from the first cell
of Chapter 1. Here every module declares the chapter that introduces it
(``INTRODUCED_IN``) and why that chapter needs it; nothing in chapter N uses a
module from a later chapter (``tests/test_incremental.py`` enforces it).

=====================  ==  ==================================================
module                 ch  what it provides
=====================  ==  ==================================================
``ontology``            1  graph metrics, the spectrum classifier, the defect scanner
``sparql``              1  one SPARQL API over an in-memory rdflib graph
``llm``                 1  Claude for DSPy, credentials, spend accounting
``evaluation``          1  rulebooks, score reports, deterministic metrics, datasets
``grading``             1  the marking cells of the problem sets
``optimize``            2  GEPA: feedback metrics, the run, before/after reporting
``tools``               3  function tools and the call log (an agent's trajectory)
``agents``              3  tool-calling agents on Claude; episode transcripts and cost
=====================  ==  ==================================================

Helpers for exploring the package from a notebook:

* :func:`catalogue` lists the modules a chapter can use, with their purpose;
* :func:`show` prints the source of any module, class or function.
"""

from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
from pathlib import Path

INTRODUCED_IN = 1

COURSE_ROOT = Path(__file__).resolve().parent.parent


def catalogue(up_to_chapter: int | None = None) -> list[dict]:
    """The modules of ``agentlab``, in the order the course introduces them."""
    rows = []
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        chapter = getattr(module, "INTRODUCED_IN", None)
        if up_to_chapter is not None and (chapter is None or chapter > up_to_chapter):
            continue
        summary = (inspect.getdoc(module) or "").split("\n")[0]
        rows.append({"chapter": chapter, "module": f"agentlab.{info.name}",
                     "lines": len(inspect.getsource(module).splitlines()),
                     "purpose": summary})
    return sorted(rows, key=lambda r: (r["chapter"] or 99, r["module"]))


def show(obj) -> None:
    """Print the source of ``obj`` with line numbers."""
    lines, start = inspect.getsourcelines(obj)
    print(f"# {inspect.getsourcefile(obj)}:{start}")
    for n, line in enumerate(lines, start):
        print(f"{n:4d}  {line}", end="")


def artifacts_dir() -> Path:
    """Where notebooks save what they produce (``artifacts/``, git-ignored)."""
    path = COURSE_ROOT / "artifacts"
    path.mkdir(exist_ok=True)
    return path


def describe_environment() -> dict:
    """The small status dict every setup cell prints."""
    from agentlab import llm

    return {"credentials": "found" if llm.has_credentials() else
            "MISSING - set ANTHROPIC_API_KEY (only the problem sets need it)",
            "task_model": llm.DSPY_MODEL, "reflection_model": llm.REFLECTION_MODEL,
            "artifacts": str(COURSE_ROOT / "artifacts"),
            "python": os.sys.version.split()[0]}
