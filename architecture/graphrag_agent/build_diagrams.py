"""Generate the SysML diagram artifacts into ./artifacts/diagrams/.

Run:  python architecture/graphrag_agent/build_diagrams.py

Reads every model in ./models/ and emits, per diagram, an SVG and a Mermaid companion.
The build fails rather than writing a misleading picture: if a model stops containing the
block, action or state a diagram is built from, that is a modelling change that should be
noticed, not silently rendered as an empty canvas.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sysml_diagrams as D
from sysml_model import attach_attributes, parse_all

MODELS = HERE / "models"
OUT = HERE / "artifacts" / "diagrams"

LEGEND = [("block", "block"), ("abstract", "abstract"), ("requirement", "requirement"),
          ("verification", "verification"), ("constraint", "constraint"),
          ("action", "action"), ("state", "state"), ("port", "port")]

# What to draw from which package. Each entry names elements that must exist.
PLAN = {
    "OntologyProjection": {
        "bdd": True,
        "act": ["Project"],
    },
    "FiboProjectionSystem": {
        "bdd": True,
        "req": True,
        "ibd": ["FiboProjectionSystemDef", "SystemContext"],
        "act": ["RunProjection"],
        "stm": ["ProjectionRun"],
    },
    "GraphRagAgent": {
        "bdd": True,
        "ibd": ["OntologyAgentSystem"],
        "act": ["AnswerQuestion"],
    },
}

SLUG = {"OntologyProjection": "projection", "FiboProjectionSystem": "fibo_system",
        "GraphRagAgent": "agent"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    models = {}
    for model in parse_all(MODELS):
        attach_attributes(model)
        models[model.package] = model
    print(f"parsed {len(models)} model(s): {', '.join(sorted(models))}")

    written: list[Path] = []
    problems: list[str] = []

    def write(name: str, text: str) -> None:
        path = OUT / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
        print(f"  {path.relative_to(HERE)}  ({len(text):,} bytes)")

    for package, plan in PLAN.items():
        model = models.get(package)
        if model is None:
            problems.append(f"model package {package} not found in {MODELS}")
            continue
        slug = SLUG[package]
        print(f"\n{package}  ({model.path.name})")

        if plan.get("bdd"):
            nodes, edges = D.bdd(model)
            if not nodes:
                problems.append(f"{package}: BDD has no part defs")
            write(f"{slug}_bdd.svg", D.render_svg(
                nodes, edges, f"{package} — Block Definition Diagram",
                f"{len(nodes)} part definitions · "
                f"{sum(1 for e in edges if e.head == 'closed')} specialisations · "
                f"{sum(1 for e in edges if e.head == 'diamond')} compositions",
                legend=LEGEND[:3]))
            write(f"{slug}_bdd.mmd", D.bdd_mermaid(model))

        if plan.get("req"):
            nodes, edges = D.req(model)
            if not nodes:
                problems.append(f"{package}: requirement diagram is empty")
            requirements = len(model.by_kind("requirement def"))
            verifications = len(model.by_kind("verification def"))
            write(f"{slug}_req.svg", D.render_svg(
                nodes, edges, f"{package} — Requirement Diagram",
                f"{requirements} requirements · {verifications} verification cases · "
                f"{sum(1 for e in edges if e.head == 'satisfy')} satisfy · "
                f"{sum(1 for e in edges if e.head == 'verify')} verify",
                legend=[("requirement", "requirement"),
                        ("verification case", "verification"),
                        ("satisfying part", "block"),
                        ("amber edge = satisfies", "requirement"),
                        ("red edge = verifies", "verification")]))
            write(f"{slug}_req.mmd", D.req_mermaid(model))

        for block in plan.get("ibd", []):
            nodes, edges = D.ibd(model, block)
            if not nodes:
                problems.append(f"{package}: block {block!r} has no parts to draw")
                continue
            write(f"{slug}_ibd_{_snake(block)}.svg", D.render_svg(
                nodes, edges, f"{block} — Internal Block Diagram",
                f"{len(nodes)} parts and ports · {len(edges)} connections",
                legend=[("part", "block"), ("port", "port")]))
            write(f"{slug}_ibd_{_snake(block)}.mmd", D.ibd_mermaid(model, block))

        for action in plan.get("act", []):
            nodes, edges = D.act(model, action)
            if not nodes:
                problems.append(f"{package}: action {action!r} has no sub-actions")
                continue
            write(f"{slug}_act_{_snake(action)}.svg", D.render_svg(
                nodes, edges, f"{action} — Activity Diagram",
                f"{len(nodes)} actions · {len(edges)} successions and flows",
                legend=[("action", "action")]))
            write(f"{slug}_act_{_snake(action)}.mmd", D.act_mermaid(model, action))

        for machine in plan.get("stm", []):
            nodes, edges = D.stm(model, machine)
            if not nodes:
                problems.append(f"{package}: state def {machine!r} has no states")
                continue
            write(f"{slug}_stm_{_snake(machine)}.svg", D.render_svg(
                nodes, edges, f"{machine} — State Machine Diagram",
                f"{len(nodes)} states · {len(edges)} transitions",
                legend=[("state", "state")]))
            write(f"{slug}_stm_{_snake(machine)}.mmd", D.stm_mermaid(model, machine))

    print(f"\nwrote {len(written)} artifact(s) to {OUT.relative_to(HERE.parent.parent)}")
    if problems:
        print("\nPROBLEMS", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    return 0


def _snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
