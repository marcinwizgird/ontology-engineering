"""Executable architecture rules — the Development viewpoint, enforced on the real code.

* layering: a module imports only modules of the same or a lower layer
  (SipDevelopment::codebase), and agents never import ``core.changes``/``core.store``
  (guarantee 2 of SipFunctional, at code level);
* single write path: ``Store.apply`` is called only in ``core/changes.py``
  (guarantee 1 / FR-CHG-01);
* the SysML model check passes (references resolve, every requirement satisfied and
  verified, every named test exists).
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parents[2]
LAYER = {"core": 0, "governance": 1, "owl": 2, "skos": 2, "reasoning": 2, "quality": 2,
         "search": 2, "alignment": 2, "io": 2, "kg": 2, "platform": 3, "demo": 5,
         "agents": 4, "api": 5, "tests": 6, "__init__": 0, "__main__": 6}


def _module_of(path: Path) -> str:
    rel = path.relative_to(PKG).parts
    return rel[0].removesuffix(".py")


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:                      # relative import inside the package
                base = list(path.relative_to(PKG).parts[:-1])
                up = node.level - 1
                base = base[:len(base) - up] if up else base
                target = base + (node.module.split(".") if node.module else [])
                yield ".".join(target), node.lineno
            elif node.module and node.module.startswith("semantic_intelligence"):
                yield node.module.split(".", 1)[1] if "." in node.module else "", node.lineno


def test_layering():
    problems = []
    for f in PKG.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        src = _module_of(f)
        for target, line in _imports(f):
            if not target:
                continue
            head = target.split(".")[0]
            if head not in LAYER:
                continue
            if LAYER[head] > LAYER[src]:
                problems.append(f"{f.relative_to(PKG)}:{line} ({src}, layer {LAYER[src]}) "
                                f"imports {target} (layer {LAYER[head]})")
            if src == "agents" and target.startswith(("core.changes", "core.store")):
                problems.append(f"{f.relative_to(PKG)}:{line}: agents must not import {target}")
    assert not problems, "\n".join(problems)


def test_single_write_path():
    offenders = []
    for f in PKG.rglob("*.py"):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        rel = f.relative_to(PKG).as_posix()
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bstore\.apply\(", line) and rel != "core/changes.py":
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_models_check():
    tool = REPO / "architecture" / "semantic_intelligence_platform" / "tools" / "sysml_check.py"
    r = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "problems: 0" in r.stdout
