"""Generate all capability-model artifacts into ./artifacts/.

Run:  python -m ontology_engineering_capabilities.build_artifacts
  or: python ontology_engineering_capabilities/build_artifacts.py
"""
from __future__ import annotations

import os

# Allow running as a plain script (python build_artifacts.py)
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ontology_engineering_capabilities import generators as G
    from ontology_engineering_capabilities import capability_model as M
else:
    from . import generators as G
    from . import capability_model as M

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts")


def main() -> None:
    os.makedirs(ART, exist_ok=True)
    problems = M.validate_model()
    if problems:
        raise SystemExit(f"model invalid: {problems}")
    print(f"model OK: {len(M.CAPABILITIES)} capabilities, {len(M.CATEGORIES)} categories")

    def write(name: str, text: str) -> None:
        path = os.path.join(ART, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  wrote {os.path.relpath(path, HERE)} ({len(text):,} bytes)")

    write(os.path.join("..", "REQUIREMENTS.md"), G.to_requirements_markdown())
    write("capability_taxonomy.mmd", G.to_mermaid_taxonomy())
    write("capability_ontology.mmd", G.to_mermaid_ontology())
    write("capability_archimate.svg", G.to_archimate_svg())
    write("capability_ontology.ttl", G.to_turtle())

    svg_png = G.draw_archimate_png(os.path.join(ART, "capability_archimate.png"))
    print(f"  wrote {os.path.relpath(svg_png, HERE)}")

    png = G.draw_ontology_networkx(os.path.join(ART, "capability_ontology.png"))
    print(f"  wrote {os.path.relpath(png, HERE)}")

    print("done.")


if __name__ == "__main__":
    main()
