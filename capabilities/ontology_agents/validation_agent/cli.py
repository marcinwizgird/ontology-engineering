"""Command line: ``validate``, ``gate`` and ``ui``.

    python -m validation_agent validate onto.ttl [--shapes s.ttl] [--declared formal-ontology]
                                                 [--policy registry-default-v1] [--json out.json] [--md out.md]
    python -m validation_agent gate onto.ttl [...]     # exit 0 accept, 1 revise, 2 reject
    python -m validation_agent ui [--host 127.0.0.1] [--port 8765]

``gate`` needs no LLM and no network (OVA-Q01).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXIT_CODES = {"accept": 0, "revise": 1, "reject": 2}


def _run(args):
    from .engine import pipeline
    from .workspace import ValidationWorkspace
    ws = ValidationWorkspace.from_path(args.ontology, declared_level=args.declared,
                                       policy=args.policy, shapes_path=args.shapes)
    return pipeline.run(ws)


def _write_reports(ws, args) -> None:
    from .engine import report
    if args.json:
        Path(args.json).write_text(report.dumps(ws), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(report.to_markdown(ws), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m validation_agent",
                                description="Ontology Validation Agent (stage S1a)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("validate", "validate and print the Markdown report"),
                        ("gate", "validate and exit 0/1/2 for accept/revise/reject")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("ontology")
        s.add_argument("--shapes")
        s.add_argument("--declared", choices=["controlled-vocabulary", "taxonomy", "thesaurus",
                                              "formal-ontology"])
        s.add_argument("--policy", default="registry-default-v1")
        s.add_argument("--json", help="write the JSON report here")
        s.add_argument("--md", help="write the Markdown report here")
    u = sub.add_parser("ui", help="start the review web UI")
    u.add_argument("--host", default="127.0.0.1")
    u.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)

    if args.cmd == "ui":
        from .webui.app import serve
        print(f"OVA review UI on http://{args.host}:{args.port}")
        serve(args.host, args.port)
        return 0

    ws = _run(args)
    _write_reports(ws, args)
    if args.cmd == "validate":
        from .engine.report import to_markdown
        out = to_markdown(ws)
        sys.stdout.buffer.write(out.encode("utf-8") + b"\n")
        return 0
    d = ws.decision
    print(f"{d.verdict.upper()} ({d.policy}): " + "; ".join(d.reasons))
    return EXIT_CODES[d.verdict]
