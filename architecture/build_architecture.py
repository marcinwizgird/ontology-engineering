"""Generate the Level-2 application architecture artifacts into ./artifacts/.

Run:  python architecture/build_architecture.py
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from architecture import app_arch_generators as G
from architecture import app_architecture_model as M

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts")


def main() -> None:
    os.makedirs(ART, exist_ok=True)
    problems = M.validate_model()
    if problems:
        raise SystemExit(f"model invalid: {problems}")
    print(f"model OK: {len(M.SERVICES)} services, {len(M.COMPONENTS)} components, "
          f"{len(M.DATA_OBJECTS)} data objects, "
          f"{len(M.supported_capability_ids())} L2 capabilities supported")

    def write(name: str, text: str) -> None:
        path = os.path.join(ART, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  wrote {os.path.relpath(path, HERE)} ({len(text):,} bytes)")

    write(os.path.join("..", "ARCHITECTURE.md"), G.to_architecture_markdown())
    write("app_architecture.svg", G.to_archimate_svg())
    write("app_architecture.mmd", G.to_mermaid())
    png = G.draw_archimate_png(os.path.join(ART, "app_architecture.png"))
    print(f"  wrote {os.path.relpath(png, HERE)}")
    print("done.")


if __name__ == "__main__":
    main()
