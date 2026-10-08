"""The layered review process as data: the steps the web UI walks a reviewer through.

The layers follow docs/ONTOLOGY_REVIEW_AND_VALIDATION.md ("Recommended layered review").
Layers 1-4 are automated and can block a release; layer 5 (AI-assisted triage) and
layer 6 (expert review) handle judgement and never change the verdict; the verdict is
applied by policy from the findings.

Reviewer input (marks on findings, checklist answers, sign-offs) is recorded in a
:class:`ReviewRecord` next to the run. It is evidence for the curator and the audit
trail, not an input to :func:`engine.policy.apply_policy`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .engine.policy import SEVERITY_RANK
from .engine.registry import CHECKS, describe

STEPS: list[dict] = [
    {
        "id": "intake", "n": 0, "title": "Submission and profile", "kind": "intake",
        "families": [],
        "purpose": "What was submitted and what it measurably is: size, formality level, "
                   "OWL 2 profiles and expressivity. The measured level, not the declared "
                   "one, decides which waivers apply.",
        "questions": ["What kind of artefact is this?",
                      "Why is the measured level different from the declared one?",
                      "Which checks will not run, and why?"],
    },
    {
        "id": "structure", "n": 1, "title": "Structure and syntax", "kind": "automated",
        "families": ["SYN", "DECL", "DL"],
        "purpose": "Is the file readable, is every term declared, is the standard "
                   "vocabulary spelled correctly, and are the OWL 2 DL restrictions respected?",
        "benefit": "Cheap and certain. A typo in owl: or rdfs: silently drops an axiom; this "
                   "layer catches it before anything else runs.",
        "limit": "Says nothing about whether the model is logically coherent or correct.",
        "questions": ["Why is this a blocker?", "How do I fix the first finding?",
                      "What does DECL-04 look for?"],
    },
    {
        "id": "reasoning", "n": 2, "title": "Logical reasoning", "kind": "automated",
        "families": ["RSN"],
        "purpose": "Does the model contradict itself, and can every class have members? "
                   "OWL 2 RL closure with a probe individual per class.",
        "benefit": "Findings are proofs, not opinions, so they can safely block a release.",
        "limit": "Checks consistency, not correctness. Open world: a missing value is not "
                 "an error here. Outside OWL 2 RL the built-in reasoner is incomplete (RSN-08).",
        "questions": ["Why is this class unsatisfiable?", "What is a root versus a derived "
                      "unsatisfiable class?", "Is a clean result here a guarantee?"],
    },
    {
        "id": "shacl", "n": 3, "title": "SHACL rules", "kind": "automated",
        "families": ["SHC"],
        "purpose": "Closed-world rules: the publisher's shapes for its data (SHC-02) and the "
                   "organisation's house rules for the ontology itself (SHC-08).",
        "benefit": "Catches exactly what reasoning cannot: missing or malformed values.",
        "limit": "Only checks what someone wrote a rule for; rules can be stale or wrong.",
        "questions": ["Which house rules are violated most?", "Why does SHACL report this when "
                      "the reasoner did not?", "How do I fix this violation?"],
    },
    {
        "id": "custom", "n": 4, "title": "Custom checks", "kind": "automated",
        "families": ["HIER", "PHIER", "PROP", "LEX", "SKOS", "META", "ABOX", "EVO", "CQ",
                     "MOD", "METRIC"],
        "purpose": "Design and housekeeping defects that are logically valid but costly: "
                   "hierarchy shape, property commitments, labels and definitions, SKOS "
                   "integrity, header metadata, spectrum position.",
        "benefit": "Encodes the organisation's standards; cheap enough to run on every change.",
        "limit": "Thresholds are conventions; heuristic checks need triage.",
        "questions": ["Which entities have the most findings?", "Why does missing sibling "
                      "disjointness matter?", "Which findings would a waiver remove?"],
    },
    {
        "id": "triage", "n": 5, "title": "AI-assisted triage", "kind": "triage",
        "families": [],
        "purpose": "Turn the raw findings into a short, explained list. The assistant explains "
                   "and suggests fixes; you mark each finding agreed, disputed or unsure. "
                   "Marks are recorded for the curator; they do not change the verdict.",
        "questions": ["Which three fixes remove the most findings?", "Explain the blockers in "
                      "plain words.", "Which findings look like deliberate modelling choices?"],
    },
    {
        "id": "expert", "n": 6, "title": "Expert review", "kind": "expert",
        "families": [],
        "purpose": "Business fit, and the judgement calls automation cannot make: is this the "
                   "right model of the domain? Disputed findings from triage land here.",
        "questions": ["Show me the top of the class hierarchy.", "Which classes have no "
                      "definition?", "What would a waiver for a disputed finding need?"],
    },
    {
        "id": "verdict", "n": 7, "title": "Verdict", "kind": "verdict",
        "families": [],
        "purpose": "Accept, revise or reject, applied by policy from the findings, never by "
                   "AI alone. Record your sign-off and download the report.",
        "questions": ["Why is the verdict what it is?", "What is the shortest path to accept?",
                      "What would change under ci-lenient-v1?"],
    },
]
STEP_BY_ID = {s["id"]: s for s in STEPS}

EXPERT_CHECKLIST = [
    {"id": "EX-1", "question": "Do the top-level classes match how the business divides its domain?"},
    {"id": "EX-2", "question": "Are the labels the terms the business actually uses?"},
    {"id": "EX-3", "question": "Can a domain expert understand every definition without the modeller?"},
    {"id": "EX-4", "question": "Is anything in scope missing, or anything out of scope included?"},
    {"id": "EX-5", "question": "Are the subclass links genuine 'kind of' relations (not part-of or role)?"},
    {"id": "EX-6", "question": "Are the disputed findings from triage resolved or justified?"},
]
MARKS = ("agree", "dispute", "unsure")
CHECKLIST_ANSWERS = ("yes", "no", "partly", "n/a")
FINAL_DECISIONS = ("endorse", "escalate")


def step_of_check(check_id: str) -> str:
    fam = CHECKS[check_id].family
    return next((s["id"] for s in STEPS if fam in s["families"]), "custom")


@dataclass
class ReviewRecord:
    marks: dict[str, dict] = field(default_factory=dict)        # finding_id -> {mark, comment}
    checklist: dict[str, dict] = field(default_factory=dict)    # EX-n -> {answer, comment}
    signoffs: dict[str, dict] = field(default_factory=dict)     # step -> {status, note, at}
    final: dict | None = None                                   # {reviewer, decision, note, at}

    def to_dict(self) -> dict:
        return asdict(self)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Assessments: what each step shows
# --------------------------------------------------------------------------- #
def _finding_view(ws, f) -> dict:
    d = f.to_dict()
    d["title"] = CHECKS[f.check_id].title
    d["step"] = step_of_check(f.check_id)
    d["focus_label"] = _label(ws, f.focus)
    return d


def _label(ws, iri: str) -> str:
    from rdflib import URIRef
    from .engine.vocab import label, local_name
    if ws.graph is None or not iri.startswith(("http", "urn", "file")):
        return local_name(iri)
    return label(ws.graph, URIRef(iri))


def _status(findings: list, runs: list) -> str:
    live = [f for f in findings if f["status"] in ("confirmed", "adjudicatedTrue")]
    if any(f["severity"] == "blocker" for f in live):
        return "blocked"
    if any(f["severity"] in ("major", "minor") for f in live):
        return "attention"
    if runs and all(r["status"] in ("skipped", "not-applicable") for r in runs):
        return "not-run"
    return "clear"


def automated_assessment(ws, step: dict) -> dict:
    fams = set(step["families"])
    runs = []
    for cid, run in ws.runs.items():
        if CHECKS[cid].family in fams:
            c = describe(cid)
            runs.append({**run.to_dict(), "title": c["title"], "severity": c["severity"],
                         "family": c["family"], "detects": c["detects"]})
    findings = [_finding_view(ws, f) for f in ws.findings if CHECKS[f.check_id].family in fams]
    findings.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], f["finding_id"]))
    return {"checks": runs, "findings": findings, "status": _status(findings, runs),
            "counts": {s: sum(1 for f in findings if f["severity"] == s
                              and f["status"] != "waived") for s in SEVERITY_RANK},
            "waived": sum(1 for f in findings if f["status"] == "waived")}


def triage_assessment(ws, record: ReviewRecord) -> dict:
    live = [_finding_view(ws, f) for f in ws.findings
            if f.status in ("confirmed", "adjudicatedTrue") and f.severity != "info"]
    groups: dict[str, list] = defaultdict(list)
    for f in live:
        groups[f["focus"]].append(f)
    clusters = []
    for focus, fs in groups.items():
        fs.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], f["finding_id"]))
        clusters.append({"focus": focus, "focus_label": fs[0]["focus_label"],
                         "worst": fs[0]["severity"], "findings": fs,
                         "checks": sorted({f["check_id"] for f in fs})})
    clusters.sort(key=lambda c: (SEVERITY_RANK[c["worst"]], -len(c["findings"]), c["focus"]))
    marked = {k: v for k, v in record.marks.items() if ws.finding(k)}
    return {"clusters": clusters, "total": len(live), "entities": len(clusters),
            "marked": len(marked), "marks": marked,
            "by_mark": {m: sum(1 for v in marked.values() if v.get("mark") == m) for m in MARKS},
            "status": "clear" if not live else
            ("done" if len(marked) >= len(live) else "attention")}


def expert_assessment(ws, record: ReviewRecord) -> dict:
    disputed = [_finding_view(ws, ws.finding(fid)) | {"review": m}
                for fid, m in sorted(record.marks.items())
                if m.get("mark") in ("dispute", "unsure") and ws.finding(fid)]
    human = [describe(cid) for cid in ws.runs if CHECKS[cid].adjudication != "none"]
    answered = sum(1 for q in EXPERT_CHECKLIST if q["id"] in record.checklist)
    return {"checklist": [q | {"answer": record.checklist.get(q["id"])} for q in EXPERT_CHECKLIST],
            "disputed": disputed, "judgement_checks": human, "answered": answered,
            "status": "done" if answered == len(EXPERT_CHECKLIST) else "attention"}


def intake_assessment(ws) -> dict:
    p = ws.profile
    runs = [r.to_dict() for r in ws.runs.values()]
    return {"load": ws.load.summary(),
            "shapes": ws.shapes_load.summary() if ws.shapes_load else None,
            "profile": p.to_dict() if p else None,
            "policy": ws.policy.to_dict(), "versions": ws.versions, "run_id": ws.run_id,
            "run_counts": {s: sum(1 for r in runs if r["status"] == s)
                           for s in ("passed", "failed", "info", "skipped", "not-applicable")},
            "not_run": [r | {"title": CHECKS[r["check_id"]].title} for r in runs
                        if r["status"] in ("skipped", "not-applicable")],
            "status": "blocked" if not ws.load.loaded else "clear"}


def verdict_assessment(ws, record: ReviewRecord) -> dict:
    d = ws.decision
    return {"decision": d.to_dict(), "record": record.to_dict(),
            "waived": [_finding_view(ws, f) for f in ws.findings if f.status == "waived"],
            "status": {"accept": "clear", "revise": "attention", "reject": "blocked"}[d.verdict]}


def assess(ws, step_id: str, record: ReviewRecord) -> dict:
    step = STEP_BY_ID[step_id]
    kind = step["kind"]
    if kind == "intake":
        body = intake_assessment(ws)
    elif kind == "automated":
        body = automated_assessment(ws, step)
    elif kind == "triage":
        body = triage_assessment(ws, record)
    elif kind == "expert":
        body = expert_assessment(ws, record)
    else:
        body = verdict_assessment(ws, record)
    return {"step": step, "signoff": record.signoffs.get(step_id), **body}


def overview(ws, record: ReviewRecord) -> list[dict]:
    return [{"id": s["id"], "n": s["n"], "title": s["title"], "kind": s["kind"],
             "status": assess(ws, s["id"], record)["status"],
             "signed": s["id"] in record.signoffs} for s in STEPS]
