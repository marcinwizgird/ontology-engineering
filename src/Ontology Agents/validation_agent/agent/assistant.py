"""Ontology Review Assistant: answers questions about the current review step.

It is the S1a form of the specification's *Investigator*: a bounded tool loop over the
read-only tool belt. Its place in the trust boundary:

* it reads the engine's findings and the policy decision; it cannot add, remove or
  re-grade findings, and it cannot change the verdict (OVA-T01, T02);
* every answer passes the grounding critic (:mod:`.critic`); corrections are shown with
  the answer and counted;
* model traffic goes only through the :class:`~.gateway.LlmGateway` (off by default).

Two back ends share one interface:

* :class:`SimulatedBackend` -- deterministic and offline (no key, no cost). It routes the
  question to the right tools by rule and writes the answer from templates and the
  catalogue. It is also the fallback when the gateway refuses a call.
* :class:`ClaudeBackend` -- Claude with a manual tool-use loop over the belt (at most
  ``MAX_TOOL_ROUNDS`` rounds), adaptive thinking, and the stable system prompt and tool
  list first so the prefix is cached across turns.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..engine import vocab as V
from ..engine.policy import SEVERITY_RANK
from ..engine.registry import CHECKS
from ..review import STEP_BY_ID, ReviewRecord, assess
from ..tools.belt import TOOL_SPECS, ToolBelt, anthropic_tools
from .critic import ground
from .gateway import LlmGateway

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You are the Ontology Review Assistant inside the Ontology Validation Agent (OVA). \
A reviewer is walking through a layered ontology review, one step at a time, and asks you \
questions about the assessment shown at the current step.

How OVA works, which bounds what you may say:
- A deterministic engine is the only source of findings. Every finding comes from a \
catalogued check (ids such as HIER-05) and has an id such as f-0007.
- The verdict (accept, revise or reject) is a pure function of the findings, the measured \
profile and the policy. Precedence: any confirmed blocker rejects; any remaining blocker, \
major or minor finding, or a measured level below the declared one, means revise; otherwise \
accept. Waivers are keyed on the measured level.
- You cannot create, remove or re-grade findings, and you cannot change the verdict. If the \
reviewer disagrees with a finding, explain the options: fix the ontology, mark the finding \
disputed in triage for the curator, or propose a policy waiver. Never suggest that a \
finding does not count.
- Reasoning in this stage is OWL 2 RL with probe individuals. Outside RL a clean result is \
not a proof of satisfiability (RSN-08).

How to answer:
- Ground every claim about a specific entity, finding or check in a tool result from this \
conversation. Call describe_entity, get_finding or check_catalogue before explaining \
something you have not yet looked up. Use search_entities to resolve a name into an IRI.
- Cite finding ids, check ids and IRIs exactly as the tools return them; never invent one. \
Write IRIs in backticks.
- When asked how to fix something, propose the smallest concrete change, in Turtle when it \
helps, and say which findings it should remove. Say that the engine re-checks any change \
on the next run; you do not verify repairs yourself.
- Keep to the current step unless asked otherwise. Be concise: a short answer first, then \
the detail a reviewer needs. Use Markdown. Answer in the reviewer's language."""


@dataclass
class AssistantReply:
    answer: str
    step: str
    tool_calls: list[dict] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    model: str = "simulated"
    suggestions: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Context: what the assistant is told about the current step
# --------------------------------------------------------------------------- #
def step_context(ws, step_id: str, record: ReviewRecord, finding_id: str | None = None,
                 limit: int = 40) -> dict:
    a = assess(ws, step_id, record)
    step = a["step"]
    ctx: dict[str, Any] = {"step": {"id": step["id"], "n": step["n"], "title": step["title"],
                                    "purpose": step["purpose"]},
                           "status": a["status"],
                           "verdict": ws.decision.verdict if ws.decision else None,
                           "policy": ws.policy.id,
                           "measured_level": ws.profile.spectrum_level if ws.profile else None,
                           "declared_level": ws.declared_level}
    if step["kind"] == "automated":
        ctx["checks"] = [{"check_id": r["check_id"], "title": r["title"], "status": r["status"],
                          "findings": r["findings"], "reason": r["reason"] or None}
                         for r in a["checks"]]
        ctx["findings"] = [_brief(f) for f in a["findings"][:limit]]
        ctx["findings_total"] = len(a["findings"])
    elif step["kind"] == "triage":
        ctx["clusters"] = [{"focus": c["focus"], "worst": c["worst"], "checks": c["checks"],
                            "finding_ids": [f["finding_id"] for f in c["findings"]]}
                           for c in a["clusters"][:limit]]
        ctx["reviewer_marks"] = record.marks
    elif step["kind"] == "expert":
        ctx["checklist"] = a["checklist"]
        ctx["disputed"] = [_brief(f) for f in a["disputed"]]
    elif step["kind"] == "verdict":
        ctx["decision"] = a["decision"]
    else:
        p = a.get("profile") or {}
        ctx["profile"] = {k: p.get(k) for k in ("spectrum_level", "spectrum_evidence",
                                                "expressivity", "applies", "counts", "notes")}
        ctx["not_run"] = [{"check_id": r["check_id"], "status": r["status"], "reason": r["reason"]}
                          for r in a["not_run"]]
    if finding_id and ws.finding(finding_id):
        ctx["selected_finding"] = _brief(ws.finding(finding_id).to_dict())
    return ctx


def _brief(f: dict) -> dict:
    return {k: f.get(k) for k in ("finding_id", "check_id", "severity", "status", "focus",
                                  "message")}


# --------------------------------------------------------------------------- #
# Offline back end
# --------------------------------------------------------------------------- #
class SimulatedBackend:
    model_id = "simulated"

    def __init__(self, ws, belt: ToolBelt) -> None:
        self.ws = ws
        self.belt = belt
        self.calls: list[dict] = []

    def _tool(self, name: str, **args) -> Any:
        result = self.belt.call(name, args)
        self.calls.append({"tool": name, "args": args,
                           "ok": not (isinstance(result, str) and result.startswith("ERROR"))})
        return result

    def answer(self, step_id: str, question: str, ctx: dict) -> str:
        q = question.lower()
        fid = next(iter(re.findall(r"\bf-\d{4}\b", question)), None) or \
            (ctx.get("selected_finding") or {}).get("finding_id")
        cid = next(iter(re.findall(r"\b[A-Z]{2,6}-\d{2}\b", question)), None)
        if re.search(r"\b(ci-lenient|registry-default|what if|what-if|under another policy)\b", q):
            return self._what_if(q)
        if re.search(r"\b(verdict|accept|reject|shortest path|why .*revise)\b", q):
            return self._verdict(q)
        if fid and re.search(r"\b(fix|repair|change|correct|resolve)\b", q):
            return self._fix(fid)
        if fid:
            return self._explain_finding(fid)
        if cid:
            return self._explain_check(cid)
        if re.search(r"root versus derived|root vs|derived", q):
            return _ROOT_DERIVED
        if re.search(r"guarantee|complete|proof", q) and step_id in ("reasoning", "verdict"):
            return self._completeness()
        if re.search(r"unsatisfiable|contradict|inconsisten|empty class|clash", q):
            return self._reasoning()
        if re.search(r"most findings|which entities|three fixes|remove the most", q):
            return self._hotspots()
        if re.search(r"not run|skipped|did not run|will not run", q):
            return self._not_run()
        if re.search(r"no definition|without definition|definitions", q):
            return self._check_findings("LEX-02")
        if re.search(r"\b(hierarchy|top|parent|children|subclass)", q):
            return self._hierarchy(question)
        if re.search(r"house rule", q):
            return self._check_findings("SHC-08")
        if re.search(r"what (kind|is this)|measured level|declared", q):
            return self._profile()
        entity = self._resolve_entity(question)
        if entity:
            return self._describe(entity)
        if re.search(r"\b(blocker|blocking|plain words|explain)\b", q):
            return self._blockers(step_id, ctx)
        return self._summary(step_id, ctx)

    # ---------------------------------------------------------------- intents
    def _summary(self, step_id: str, ctx: dict) -> str:
        step = STEP_BY_ID[step_id]
        lines = [f"**{step['n']}. {step['title']}**: {step['purpose']}", ""]
        if "findings" in ctx:
            n = ctx["findings_total"]
            ran = [c for c in ctx["checks"] if c["status"] not in ("skipped", "not-applicable")]
            lines.append(f"{len(ran)} of {len(ctx['checks'])} checks ran here and produced "
                         f"{n} finding(s); step status: **{ctx['status']}**.")
            for f in ctx["findings"][:6]:
                lines.append(f"- {f['finding_id']} · {f['check_id']} · {f['severity']}: {f['message']}")
            if n > 6:
                lines.append(f"- … and {n - 6} more")
        elif "clusters" in ctx:
            lines.append(f"{len(ctx['clusters'])} entities carry findings. Start with the top of "
                         "the list: it is sorted by worst severity, then by number of findings.")
        elif "checklist" in ctx:
            lines.append("Answer each checklist question; disputed findings from triage are listed "
                         "for a decision.")
        elif "decision" in ctx:
            d = ctx["decision"]
            lines.append(f"Verdict **{d['verdict']}** under `{d['policy']}`: " + "; ".join(d["reasons"]) + ".")
        lines += ["", "Ask me about a finding id (e.g. *explain f-0001*), a check id, an entity "
                      "name, or *how do I fix f-0001?*"]
        return "\n".join(lines)

    def _explain_finding(self, fid: str) -> str:
        f = self._tool("get_finding", finding_id=fid)
        if isinstance(f, str):
            return f
        c = f["check"]
        lines = [f"**{fid} · {c['id']} {c['title']}** ({f['severity']}, {f['status']})", "",
                 f["message"], "", f"**What the check detects.** {c['detects']}",
                 f"**Why it matters.** {c['rationale']}"]
        ev = f.get("evidence") or {}
        triples = ev.get("triples") or []
        if triples:
            lines += ["", "**Evidence**", "```turtle", *triples[:5], "```"]
        lines += ["", f"**How to fix.** {f['fix_hint']}", "", _severity_effect(f["severity"], f["status"])]
        if f["focus"].startswith(("http", "urn")) and self.ws.graph is not None:
            card = self._tool("describe_entity", iri=f["focus"])
            if isinstance(card, dict) and len(card.get("findings", [])) > 1:
                others = [x["finding_id"] for x in card["findings"] if x["finding_id"] != fid]
                lines.append(f"`{V.local_name(f['focus'])}` also has: {', '.join(others)}.")
        return "\n".join(lines)

    def _fix(self, fid: str) -> str:
        f = self._tool("get_finding", finding_id=fid)
        if isinstance(f, str):
            return f
        lines = [f"**Fixing {fid} ({f['check_id']})**", "", f["fix_hint"]]
        patch = _patch_sketch(self.ws, f)
        if patch:
            lines += ["", "A minimal change that should remove it:", "```turtle", patch, "```"]
        lines += ["", "The engine re-checks the ontology on the next run; I do not verify "
                      "repairs myself (verified repairs arrive in stage S3)."]
        return "\n".join(lines)

    def _explain_check(self, cid: str) -> str:
        c = self._tool("check_catalogue", check_id=cid)
        if isinstance(c, str):
            return c
        run = self.ws.runs.get(cid)
        if run is None:
            status = f"It ships in stage {c['stage']} and did not run here."
        else:
            status = f"In this run: **{run.status}**" + (f" ({run.reason})" if run.reason else "") \
                + f", {run.findings} finding(s)."
        return "\n".join([f"**{c['id']} {c['title']}** · family {c['family_title']} · default "
                          f"severity {c['severity']} · method {c['method']}", "",
                          f"**Detects.** {c['detects']}", f"**Why.** {c['rationale']}",
                          f"**Applies to:** {', '.join(c['applies'])}"
                          + (f" · references: {', '.join(c['refs'])}" if c['refs'] else ""),
                          "", status])

    def _verdict(self, q: str) -> str:
        d = self._tool("apply_policy")
        lines = [f"The verdict is **{d['verdict']}** under `{d['policy']}`.", ""]
        lines += [f"- {r}" for r in d["reasons"]]
        live = [f for f in self.ws.findings if f.status in ("confirmed", "adjudicatedTrue")
                and f.severity != "info"]
        by_check: dict[str, int] = {}
        for f in live:
            by_check[f.check_id] = by_check.get(f.check_id, 0) + 1
        if d["verdict"] != "accept":
            lines += ["", "**Shortest path to accept:** resolve, in this order:"]
            for sev in ("blocker", "major", "minor"):
                ids = sorted({f.check_id for f in live if f.severity == sev})
                if ids:
                    lines.append(f"- {sev}: " + ", ".join(f"{i} ×{by_check[i]}" for i in ids))
            if self.ws.profile and self.ws.declared_level and \
                    "below the declared" in " ".join(d["reasons"]):
                lines.append("- and raise the measured level to the declared one (METRIC-01)")
        lines += ["", "The verdict is computed by policy from the findings; neither I nor the "
                      "triage marks can change it."]
        return "\n".join(lines)

    def _what_if(self, q: str) -> str:
        target = "ci-lenient-v1" if "lenient" in q else "registry-default-v1"
        d = self._tool("apply_policy", policy=target)
        if isinstance(d, str):
            return d
        return "\n".join([f"What-if under `{target}`: the verdict would be **{d['verdict']}**.",
                          "", *[f"- {r}" for r in d["reasons"]], "", d.get("note", "")])

    def _reasoning(self) -> str:
        r = self._tool("reason")
        if isinstance(r, str):
            return r
        if not r["consistent"]:
            return "\n".join(["The ontology is **inconsistent**: it has no model, so every class "
                              "is trivially empty. Clashes:", *[f"- {c['individual'] or '(global)'}: "
                                                               f"{c['reason']}" for c in r["clashes"]]])
        if not r["unsatisfiable"]:
            return ("No class is unsatisfiable under OWL 2 RL with probe individuals." +
                    ("" if r["complete"] else " The ontology is outside RL, so this is not a "
                     "proof (RSN-08)."))
        lines = [f"{len(r['unsatisfiable'])} unsatisfiable class(es):"]
        for u in r["unsatisfiable"]:
            kind = "root" if u["root"] else "derived via " + ", ".join(V.local_name(v) for v in u["via"])
            lines.append(f"- `{u['class']}` ({kind}): a member would be a {u['reason']}")
        lines += ["", "Fix the **root** classes first; derived ones recover with them."]
        return "\n".join(lines)

    def _completeness(self) -> str:
        r = self._tool("reason")
        if isinstance(r, str):
            return r
        if r["complete"]:
            return ("Within the limits of OWL 2 RL, yes: the ontology is inside the RL profile, "
                    "so the RL closure with probe individuals finds the clashes that matter "
                    "here. A clean result still says the model is *consistent*, not that it is "
                    "*correct*.")
        return ("No. " + r["incompleteness"] + ". A clean result does not establish that every "
                "class is satisfiable; the DL backend (HermiT, stage S1c) gives the complete answer.")

    def _hotspots(self) -> str:
        groups: dict[str, list] = {}
        for f in self.ws.findings:
            if f.status in ("confirmed", "adjudicatedTrue") and f.severity != "info":
                groups.setdefault(f.focus, []).append(f)
        ranked = sorted(groups.items(), key=lambda kv: (min(SEVERITY_RANK[f.severity] for f in kv[1]),
                                                        -len(kv[1]), kv[0]))
        if not ranked:
            return "No entity carries a blocker, major or minor finding."
        lines = ["Entities with the most serious and most numerous findings:"]
        for focus, fs in ranked[:5]:
            worst = min(fs, key=lambda f: SEVERITY_RANK[f.severity]).severity
            lines.append(f"- `{V.local_name(focus)}` ({worst}): " +
                         ", ".join(f"{f.finding_id} {f.check_id}" for f in fs))
        top = ranked[0][1]
        lines += ["", f"Fixing `{V.local_name(ranked[0][0])}` first removes {len(top)} finding(s); "
                      "ask *how do I fix " + top[0].finding_id + "?* for a concrete change."]
        return "\n".join(lines)

    def _not_run(self) -> str:
        rows = [r for r in self.ws.runs.values() if r.status in ("skipped", "not-applicable")]
        if not rows:
            return "Every S1a check ran on this submission."
        return "\n".join(["Checks that did not run, and why:", *[
            f"- {r.check_id} {CHECKS[r.check_id].title}: {r.status}: {r.reason}" for r in rows],
            "", "A skipped check is never reported as passed."])

    def _check_findings(self, cid: str) -> str:
        r = self._tool("run_check", check_id=cid)
        if isinstance(r, str):
            return r
        fs = r["findings"]
        if not fs:
            return f"{cid} {CHECKS[cid].title}: **{r['run']['status']}**, no findings."
        return "\n".join([f"{cid} {CHECKS[cid].title}: {len(fs)} finding(s):",
                          *[f"- {f['finding_id']} `{V.local_name(f['focus'])}`: {f['message']}"
                            for f in fs[:15]]] + ([f"- … {len(fs) - 15} more"] if len(fs) > 15 else []))

    def _hierarchy(self, question: str) -> str:
        entity = self._resolve_entity(question)
        if entity:
            h = self._tool("hierarchy_neighbourhood", iri=entity, up=3, down=2)
            if isinstance(h, str):
                return h
            lines = [f"**{h['label']}** (`{entity}`)"]
            for i, level in enumerate(h["ancestors_by_level"], 1):
                lines.append(f"- {'parent' if i == 1 else f'ancestor (level {i})'}: "
                             + (", ".join(V.local_name(x) for x in level) or "—"))
            lines.append("- siblings: " + (", ".join(V.local_name(x) for x in h["siblings"]) or "—"))
            for i, level in enumerate(h["children_by_level"], 1):
                lines.append(f"- {'children' if i == 1 else f'descendants (level {i})'}: "
                             + ", ".join(V.local_name(x) for x in level))
            if h["disjoint_with"]:
                lines.append("- disjoint with: " + ", ".join(V.local_name(x) for x in h["disjoint_with"]))
            return "\n".join(lines)
        rows = self._tool("sparql_select", query=(
            "SELECT ?c (COUNT(?child) AS ?n) WHERE { ?c a owl:Class . FILTER(isIRI(?c)) "
            "FILTER NOT EXISTS { ?c rdfs:subClassOf ?p . FILTER(isIRI(?p) && ?p != owl:Thing) } "
            "OPTIONAL { ?child rdfs:subClassOf ?c } } GROUP BY ?c ORDER BY ?c"))
        if isinstance(rows, str):
            return rows
        return "\n".join(["Top-level classes (no named parent) and their direct subclass count:",
                          *[f"- `{V.local_name(r['c'])}`: {r['n']}" for r in rows["rows"]],
                          "", "Name one of them to see its neighbourhood."])

    def _profile(self) -> str:
        p = self._tool("profile")
        if isinstance(p, str):
            return p
        lines = [f"Measured level: **{p['spectrum_level']}**"
                 + (f"; declared: **{p['declared_level']}**" if p["declared_level"] else
                    "; no level was declared") + ".", ""]
        lines += [f"- {e}" for e in p["spectrum_evidence"]]
        lines += ["", f"Expressivity {p['expressivity']}; OWL 2 profiles: " +
                  ", ".join(f"{k} {'yes' if v['in_profile'] else 'no'}" for k, v in p["owl_profiles"].items()),
                  "", "Waivers are keyed on the measured level, never on the declared one."]
        return "\n".join(lines)

    def _blockers(self, step_id: str, ctx: dict) -> str:
        fs = [f for f in self.ws.findings if f.severity == "blocker" and f.status == "confirmed"]
        if step_id in STEP_BY_ID and STEP_BY_ID[step_id]["families"]:
            fams = set(STEP_BY_ID[step_id]["families"])
            fs = [f for f in fs if CHECKS[f.check_id].family in fams] or fs
        if not fs:
            return "There is no confirmed blocker" + (" in this step." if ctx.get("findings") is not None else ".")
        lines = ["In plain words:"]
        for f in fs[:8]:
            lines.append(f"- **{f.finding_id}** ({f.check_id}): {f.message} "
                         f"*Why it matters:* {CHECKS[f.check_id].rationale}")
        return "\n".join(lines)

    def _resolve_entity(self, question: str) -> str | None:
        if self.ws.graph is None:
            return None
        iri = re.search(r"(?:https?://|urn:)[^\s`'\"<>()]+", question)
        if iri:
            return iri.group(0).rstrip(".,?")
        words = re.findall(r"`([^`]+)`|\"([^\"]+)\"|\b([A-Z][A-Za-z0-9]{2,})\b", question)
        for groups in words:
            w = next(x for x in groups if x)
            if w.upper() == w and re.match(r"[A-Z]+-?\d*$", w):
                continue
            hits = self._tool("search_entities", text=w)
            if isinstance(hits, list) and hits:
                exact = [h for h in hits if V.local_name(h["iri"]).lower() == w.lower()
                         or h["label"].lower() == w.lower()]
                return (exact or hits)[0]["iri"]
        return None

    def _describe(self, iri: str) -> str:
        card = self._tool("describe_entity", iri=iri)
        if isinstance(card, str):
            return card
        lines = [f"**{card['label']}** (`{card['iri']}`)"]
        for key, title in (("types", "types"), ("labels", "labels"), ("definitions", "definition"),
                           ("parents", "parents"), ("children", "children"),
                           ("disjoint_with", "disjoint with"), ("restrictions", "restrictions"),
                           ("domain", "domain"), ("range", "range")):
            if card.get(key):
                vals = card[key]
                shown = [V.local_name(v) if v.startswith(("http", "urn")) else v for v in vals]
                lines.append(f"- {title}: " + "; ".join(shown))
        if card.get("findings"):
            lines += ["", "Findings that mention it:"]
            lines += [f"- {f['finding_id']} {f['check_id']} ({f['severity']}): {f['message']}"
                      for f in card["findings"]]
        return "\n".join(lines)


_ROOT_DERIVED = (
    "A **root** unsatisfiable class is empty because of its *own* axioms (for example, it is "
    "declared disjoint with one of its ancestors). A **derived** one is empty only because it "
    "is a subclass of a root. Fix the roots: the derived classes recover with them. In this "
    "stage the split is structural (inferred superclasses); stage S1c computes it from "
    "minimal justifications.")


def _severity_effect(severity: str, status: str) -> str:
    if status == "waived":
        return "This finding is **waived** by the policy and does not affect the verdict."
    return {"blocker": "As a confirmed **blocker** it makes the verdict *reject* on its own.",
            "major": "As a **major** finding it requires revision before acceptance.",
            "minor": "As a **minor** finding it requires revision before acceptance.",
            "info": "It is **information only** and never changes the verdict."}[severity]


def _patch_sketch(ws, f: dict) -> str | None:
    """A Turtle sketch of the smallest change for the common S1a checks (not verified)."""
    focus, cid, ev = f["focus"], f["check_id"], f.get("evidence") or {}
    n = lambda iri: f"<{iri}>"  # noqa: E731
    if cid == "HIER-05" and f["related"]:
        return f"# remove\n{n(focus)} owl:disjointWith {n(f['related'][0])} .\n" \
               f"# (or the matching owl:AllDisjointClasses member)"
    if cid == "LEX-01":
        return f"{n(focus)} rdfs:label \"{_words(V.local_name(focus))}\"@en ."
    if cid == "LEX-02":
        return f"{n(focus)} skos:definition \"A <parent> that <distinguishing feature>.\"@en ."
    if cid == "PROP-01":
        missing = ev.get("missing", [])
        return "\n".join(f"{n(focus)} rdfs:{m} <Class> ." for m in missing)
    if cid == "DECL-01":
        return f"{n(focus)} a owl:Class ;\n    rdfs:label \"{_words(V.local_name(focus))}\"@en ."
    if cid == "DECL-02":
        return f"{n(focus)} a owl:ObjectProperty .   # or owl:DatatypeProperty"
    if cid == "DECL-04" and ev.get("suggestion"):
        return f"# replace <{focus}> with <{ev['namespace']}{ev['suggestion']}> everywhere"
    if cid == "META-01":
        lines = [f"{n(focus)}"]
        for m in ev.get("missing", []):
            lines.append(f"    {m} \"...\" ;")
        return "\n".join(lines).rstrip(" ;") + " ." if len(lines) > 1 else None
    if cid == "HIER-08":
        members = " ".join(n(r) for r in f["related"])
        return f"[] a owl:AllDisjointClasses ;\n   owl:members ( {members} ) ."
    if cid == "HIER-01" and f["related"]:
        return f"# remove the back edge, e.g.\n{n(f['related'][-1])} rdfs:subClassOf {n(focus)} ."
    return None


def _words(camel: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", camel).replace("_", " ").strip().lower().capitalize()


# --------------------------------------------------------------------------- #
# Claude back end
# --------------------------------------------------------------------------- #
class ClaudeBackend:
    def __init__(self, ws, belt: ToolBelt, gateway: LlmGateway) -> None:
        import anthropic  # lazy: offline runs never import the SDK
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.ws = ws
        self.belt = belt
        self.gateway = gateway
        self.model_id = gateway.model_id
        self.tools = anthropic_tools([t["name"] for t in TOOL_SPECS])
        self.calls: list[dict] = []

    def run(self, history: list[dict]) -> str:
        """Run the tool loop on ``history`` (appended in place); return the final text."""
        for _ in range(MAX_TOOL_ROUNDS):
            if not self.gateway.allow():
                raise BudgetExhausted("the assistant's model-call budget for this session is used up")
            response = self.client.beta.messages.create(
                model=self.model_id,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=self.tools,
                messages=history,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                # passed through extra_body: SDK releases before the parameter existed
                # (anthropic 0.96 here) reject it as a keyword argument
                extra_body={"fallbacks": "default"},
            )
            self.gateway.record(self.model_id, len(json.dumps(history, default=str)),
                                response.usage, response.stop_reason or "")
            history.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return "The model declined to answer this question. The findings and verdict " \
                       "above are unaffected."
            if response.stop_reason == "max_tokens":
                return _text(response) + "\n\n*(answer truncated)*"
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                return _text(response)
            results = []
            for b in uses:
                args = b.input if isinstance(b.input, dict) else {}
                out = self.belt.call_json(b.name, args)
                self.calls.append({"tool": b.name, "args": args, "ok": not out.startswith("ERROR")})
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": out[:20000], "is_error": out.startswith("ERROR")})
            history.append({"role": "user", "content": results})
        return "I stopped after the maximum number of tool rounds. Ask a narrower question."


class BudgetExhausted(RuntimeError):
    pass


def _text(response) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
class ReviewAssistant:
    """One assistant per review session; one conversation per review step."""

    def __init__(self, ws, record: ReviewRecord, gateway: LlmGateway | None = None) -> None:
        self.ws = ws
        self.record = record
        self.gateway = gateway or LlmGateway.from_env()
        self.belt = ToolBelt(ws, actor="assistant")
        self.histories: dict[str, list[dict]] = {}
        self.transcripts: dict[str, list[dict]] = {}
        self.corrections = 0

    def ask(self, step_id: str, question: str, finding_id: str | None = None) -> AssistantReply:
        if step_id not in STEP_BY_ID:
            raise KeyError(step_id)
        question = question.strip()[:4000]
        ctx = step_context(self.ws, step_id, self.record, finding_id)
        model = "simulated"
        usage: dict[str, int] = {}
        if self.gateway.allow():
            history = self.histories.setdefault(step_id, [])
            start = len(history)
            history.append({"role": "user", "content": [{"type": "text", "text":
                            "<assessment>\n" + json.dumps(ctx, ensure_ascii=False, default=str)
                            + "\n</assessment>\n\n" + question}]})
            try:
                backend = ClaudeBackend(self.ws, self.belt, self.gateway)
                answer = backend.run(history)
                model, calls = backend.model_id, backend.calls
                usage = dict(self.gateway.usage)
            except Exception as exc:  # gateway refusal, network, budget: fall back offline
                del history[start:]   # keep the conversation well-formed for the next turn
                sim = SimulatedBackend(self.ws, self.belt)
                answer = sim.answer(step_id, question, ctx) + \
                    f"\n\n*(offline answer: the model call failed: {type(exc).__name__})*"
                calls = sim.calls
        else:
            sim = SimulatedBackend(self.ws, self.belt)
            answer = sim.answer(step_id, question, ctx)
            calls = sim.calls
        corrections = ground(answer, self.ws)
        self.corrections += len(corrections)
        reply = AssistantReply(answer=answer, step=step_id, tool_calls=calls,
                               corrections=corrections, model=model,
                               suggestions=STEP_BY_ID[step_id]["questions"], usage=usage)
        self.transcripts.setdefault(step_id, []).extend([
            {"role": "user", "text": question, "finding_id": finding_id},
            {"role": "assistant", **reply.to_dict()}])
        return reply

    def status(self) -> dict:
        return {**self.gateway.status(), "critic_corrections": self.corrections}


__all__ = ["ReviewAssistant", "AssistantReply", "SYSTEM_PROMPT", "step_context"]
