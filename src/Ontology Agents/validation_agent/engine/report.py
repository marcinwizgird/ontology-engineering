"""ReportBuilder: JSON and Markdown (SPECIFICATION.md s.6.3).

The Markdown follows the specified order: the verdict and why, then findings by
severity, then the waived findings and why they were waived. Every prose slot has a
deterministic template, so ``gate`` mode needs no LLM. (Root causes and verified repairs
arrive with S1c and S3.)
"""

from __future__ import annotations

import json

from rdflib.namespace import OWL

from .policy import SEVERITY_RANK
from .registry import CHECKS
from .vocab import ontology_nodes

REPORT_SCHEMA = "ova-report/0.1"


def to_json(ws, review: dict | None = None, tool_log: list | None = None) -> dict:
    o = ws.graph
    nodes = ontology_nodes(o) if o is not None else []
    iri = str(nodes[0]) if nodes else None
    version_iri = str(o.value(nodes[0], OWL.versionIRI)) if nodes and o.value(nodes[0], OWL.versionIRI) else None
    return {
        "schema": REPORT_SCHEMA,
        "run": {"id": ws.run_id, "tenant": ws.tenant, "stage": ws.stage, "millis": ws.millis},
        "ontology": {"iri": iri, "version_iri": version_iri, "hash": ws.load.hash,
                     "source": ws.load.source, "triples": len(o) if o is not None else 0},
        "profile": ws.profile.to_dict() if ws.profile else None,
        "plan": {cid: r.to_dict() for cid, r in ws.runs.items()},
        "findings": [f.to_dict() for f in ws.findings],
        "root_causes": [],
        "repairs": [],
        "verdict": ws.decision.to_dict(),
        "metrics": ws.profile.counts if ws.profile else {},
        "versions": {**ws.versions, "skills": {}},
        "cost": {"calls": 0, "usd": 0.0},
        "tool_log": tool_log if tool_log is not None else ws.tool_log,
        "review": review,
    }


def dumps(ws, **kw) -> str:
    return json.dumps(to_json(ws, **kw), indent=2, ensure_ascii=False, sort_keys=False)


def to_markdown(ws, review: dict | None = None) -> str:
    d = ws.decision
    lines = [f"# Validation report: {ws.load.source}", "",
             f"**Verdict: {d.verdict.upper()}** under policy `{d.policy}`", ""]
    lines += [f"- {r}" for r in d.reasons]
    lines += ["", f"Run `{ws.run_id}` · engine {ws.versions['engine']} · catalogue "
              f"{ws.versions['catalogue']} · content `{ws.load.hash[:23]}…`", ""]
    if ws.profile:
        p = ws.profile
        profiles = ", ".join(k for k, v in p.owl_profiles.items() if v["in_profile"]) or "none"
        lines += ["## Profile", "",
                  f"- Measured level: **{p.spectrum_level}**"
                  + (f" (declared: {p.declared_level})" if p.declared_level else ""),
                  f"- Expressivity: {p.expressivity}; OWL 2 profiles: {profiles}",
                  f"- {p.counts['classes']} classes, {p.counts['object_properties']} object "
                  f"properties, {p.counts['datatype_properties']} datatype properties, "
                  f"{p.counts['individuals']} individuals, {p.counts['triples']} triples", ""]
    live = [f for f in ws.findings if f.status in ("confirmed", "adjudicatedTrue")]
    lines += ["## Findings", ""]
    if not live:
        lines += ["No findings.", ""]
    for sev in SEVERITY_RANK:
        fs = [f for f in live if f.severity == sev]
        if not fs:
            continue
        lines += [f"### {sev.capitalize()} ({len(fs)})", "",
                  "| id | check | focus | message | fix |", "|---|---|---|---|---|"]
        for f in fs:
            lines.append(f"| {f.finding_id} | {f.check_id} {CHECKS[f.check_id].title} | "
                         f"`{f.focus}` | {_cell(f.message)} | {_cell(f.fix_hint)} |")
        lines.append("")
    waived = [f for f in ws.findings if f.status == "waived"]
    if waived:
        lines += ["## Waived", "", "| id | check | focus | waiver | reason |", "|---|---|---|---|---|"]
        for f in waived:
            lines.append(f"| {f.finding_id} | {f.check_id} | `{f.focus}` | "
                         f"{f.evidence.get('waiver')} | {_cell(f.evidence.get('waiver_reason', ''))} |")
        lines.append("")
    not_run = [r for r in ws.runs.values() if r.status in ("skipped", "not-applicable")]
    if not_run:
        lines += ["## Checks not run", ""]
        lines += [f"- {r.check_id} ({r.status}): {r.reason}" for r in not_run]
        lines.append("")
    if review:
        lines += _review_md(review)
    return "\n".join(lines)


def _review_md(review: dict) -> list[str]:
    out = ["## Review record", "",
           "Reviewer input is evidence for the curator; it does not change the verdict.", ""]
    marks = review.get("marks") or {}
    if marks:
        out += ["| finding | mark | comment |", "|---|---|---|"]
        out += [f"| {fid} | {m.get('mark')} | {_cell(m.get('comment', ''))} |"
                for fid, m in sorted(marks.items())]
        out.append("")
    checklist = review.get("checklist") or {}
    if checklist:
        out += ["**Expert checklist**", ""]
        out += [f"- {qid}: {a.get('answer')}" + (f" ({a.get('comment')})" if a.get("comment") else "")
                for qid, a in sorted(checklist.items())]
        out.append("")
    final = review.get("final")
    if final:
        out += [f"**Sign-off:** {final.get('reviewer')} — {final.get('decision')}"
                + (f": {final.get('note')}" if final.get("note") else "") + f" ({final.get('at')})", ""]
    return out


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
