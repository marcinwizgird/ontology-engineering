"""Validate the specification and regenerate CHECK_CATALOGUE.md.

    python build_docs.py

Fails loudly (exit 1) if the catalogue or the SysML models break one of the rules the
specification relies on:

* catalogue: unique ids, known families/methods/severities/stages/profiles, every
  adjudicated check has a deterministic candidate method, every check that can change a
  verdict (severity != info) names a mutation operator, adjudicated checks are capped
  below blocker;
* models: every requirement that is satisfied or verified exists, every requirement is
  satisfied or verified somewhere, every verification case referenced exists.

The SysML files are read with the repo's own subset reader
(architecture/graphrag_agent/sysml_model.py), so the same diagrams tooling applies.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
CAPABILITIES = AGENT.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CAPABILITIES / "architecture" / "graphrag_agent"))

import check_catalogue as cat  # noqa: E402

def validate_catalogue() -> list[str]:
    errors = []
    ids = Counter(c.id for c in cat.CHECKS)
    errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    families = {f.code for f in cat.FAMILIES}
    for c in cat.CHECKS:
        if not c.id.startswith(c.family + "-"):
            errors.append(f"{c.id}: id prefix does not match family {c.family}")
        if c.family not in families:
            errors.append(f"{c.id}: unknown family {c.family}")
        if c.method not in cat.METHODS:
            errors.append(f"{c.id}: unknown method {c.method}")
        if c.severity not in cat.SEVERITIES:
            errors.append(f"{c.id}: unknown severity {c.severity}")
        if c.adjudication not in cat.ADJUDICATION:
            errors.append(f"{c.id}: unknown adjudication {c.adjudication}")
        if c.stage not in cat.STAGES:
            errors.append(f"{c.id}: unknown stage {c.stage}")
        for p in c.applies:
            if p not in cat.PROFILES:
                errors.append(f"{c.id}: unknown profile {p}")
        if c.severity != "info" and not c.mutation and c.adjudication != "human":
            errors.append(f"{c.id}: can change a verdict but has no mutation operator")
        if c.adjudication == "llm" and c.severity == "blocker":
            errors.append(f"{c.id}: adjudicated checks are capped at major (OVA-T03)")
    errors += validate_groupings()
    return errors


def validate_groupings() -> list[str]:
    """Every check has exactly one maturity level and one SIP stage, and both are plausible."""
    errors = []
    ids = {c.id for c in cat.CHECKS}
    for name, mapping, known in (("maturity", cat.MATURITY_OF, cat.MATURITY),
                                 ("SIP stage", cat.SIP_STAGE_OF, cat.SIP_STAGE)):
        errors += [f"{i}: no {name}" for i in sorted(ids - set(mapping))]
        errors += [f"{i}: {name} given for an unknown check" for i in sorted(set(mapping) - ids)]
        errors += [f"{i}: unknown {name} {v}" for i, v in mapping.items() if v not in known]
    if errors:
        return errors
    stages = [s.code for s in cat.SIP_STAGES]
    levels = [m.code for m in cat.MATURITY_LEVELS]
    for c in cat.CHECKS:
        if "abox" in c.applies and stages.index(c.sip_stage) < stages.index("populate"):
            errors.append(f"{c.id}: needs instance data but starts before populate")
        if c.stage == "S1c" and levels.index(c.maturity) < levels.index("M4"):
            errors.append(f"{c.id}: needs a DL reasoner but is enabled below M4")
        if c.adjudication == "human" and c.sip_stage != "review":
            errors.append(f"{c.id}: human-adjudicated checks start at review")
    return errors


def validate_models() -> tuple[list[str], dict]:
    try:
        import sysml_model as sm
    except ImportError:
        return ["capabilities/architecture/graphrag_agent/sysml_model.py not found"], {}
    models = sm.parse_all(AGENT / "models")
    reqs, cases, rels = set(), set(), []
    stats = {}
    for m in models:
        stats[m.path.name] = Counter(e.kind for e in m.root.descendants())
        reqs |= {e.ident for e in m.by_kind("requirement def") if e.ident}
        cases |= {e.ident for e in m.by_kind("verification def") if e.ident}
        rels += m.relations
    errors = []
    satisfied = {r.target for r in rels if r.kind == "satisfy"}
    verified = {r.target for r in rels if r.kind == "verify"}
    for r in rels:
        if r.kind == "satisfy" and r.target not in reqs:
            errors.append(f"satisfy references unknown requirement {r.target}")
        if r.kind == "verify":
            if r.target not in reqs:
                errors.append(f"verify references unknown requirement {r.target}")
            if r.source not in cases:
                errors.append(f"verify references unknown case {r.source}")
    for r in sorted(reqs - satisfied - verified):
        errors.append(f"requirement {r} is neither satisfied nor verified")
    stats["_trace"] = {"requirements": len(reqs), "satisfied": len(satisfied & reqs),
                       "verified": len(verified & reqs), "cases": len(cases)}
    return errors, stats


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _ordered(checks) -> list:
    """Domain track first, then families in catalogue order (simplest constructs first)."""
    tracks = list(cat.TRACKS)
    families = [f.code for f in cat.FAMILIES]
    position = {c.id: i for i, c in enumerate(cat.CHECKS)}
    return sorted(checks, key=lambda c: (tracks.index(c.track), families.index(c.family),
                                         position[c.id]))


def _id_list(checks) -> str:
    return ", ".join(c.id for c in _ordered(checks)) or "--"


def render_maturity() -> list[str]:
    levels = cat.MATURITY_LEVELS
    stages = cat.SIP_STAGES
    at = {m.code: [c for c in cat.CHECKS if c.maturity == m.code] for m in levels}
    out = [
        "", "## Maturity ladder", "",
        "Which checks an organisation should switch on, given how far its **domain ontology "
        "modelling** has progressed. The ladder follows the OWL 2 standards from the "
        "simplest constructs to the most expressive, which is the order in which a modelling "
        "team adopts them: declare terms, arrange them in a taxonomy, relate them with "
        "properties, axiomatise them within a tractable OWL 2 profile, and finally use full "
        "OWL 2 DL with an upper ontology.",
        "",
        "* **Cumulative.** An organisation at M3 runs every M1-M3 check. Running the next "
        "level's checks as advisory shows the work needed to get there.",
        "* **Declared vs measured.** The level an organisation targets is the *declared "
        "level* that METRIC-01 compares the measured spectrum position against, so the "
        "spectrum column is what METRIC-01 expects to measure at that level.",
        "* **Domain ontology first.** Each check also carries a *track*: " +
        "; ".join(f"`{k}` = {v}" for k, v in cat.TRACKS.items()) + ". A rollout that "
        "starts with domain ontology modelling enables the `domain` track of each level "
        "first and adds the other tracks when the platform reaches the matching stage.",
        "",
        "| level | name | OWL 2 / RDF constructs in use | spectrum (METRIC-01) | "
        "organisational practice | exit criterion | new | cumulative |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total = 0
    for m in levels:
        total += len(at[m.code])
        out.append(f"| [{m.code}](#{m.code.lower()}) | **{m.title}** | {m.owl} | {m.spectrum} | "
                   f"{m.practice} | {m.exit} | {len(at[m.code])} | {total} |")

    out += ["", "**Checks by maturity level and SIP stage** (count of checks first enabled at "
            "the level, by the stage where they start; the `domain` column counts the "
            "domain-ontology track).", "",
            "| level | " + " | ".join(s.code for s in stages) + " | all | domain |",
            "|---|" + "---|" * (len(stages) + 2)]
    for m in levels:
        cells = [str(sum(c.sip_stage == s.code for c in at[m.code]) or "") for s in stages]
        domain = sum(c.track == "domain" for c in at[m.code])
        out.append(f"| {m.code} | " + " | ".join(cells) + f" | {len(at[m.code])} | {domain} |")
    out.append("| **all** | " + " | ".join(
        str(sum(c.sip_stage == s.code for c in cat.CHECKS) or "") for s in stages) +
        f" | {len(cat.CHECKS)} | {sum(c.track == 'domain' for c in cat.CHECKS)} |")

    for m in levels:
        out += ["", f"### {m.code}", "",
                f"**{m.title}.** *Constructs:* {m.owl} *Exit:* {m.exit}", "",
                "| id | check | sev. | family | track | SIP stage | gate |",
                "|---|---|---|---|---|---|---|"]
        for c in _ordered(at[m.code]):
            out.append(f"| {c.id} | {_md_escape(c.title)} | {c.severity} | "
                       f"[{c.family}](#{c.family.lower()}) | {c.track} | {c.sip_stage} | "
                       f"{c.gate} |")
    return out


def render_sip_stages() -> list[str]:
    levels = cat.MATURITY_LEVELS
    out = [
        "", "## SIP lifecycle stages", "",
        "Where each check runs in the Semantic Intelligence Platform lifecycle:",
        "",
        "```",
        "scope → acquire → model → validate → review ║ populate → reason → publish ║ consume",
        "```",
        "",
        "A check is placed at the **earliest stage at which it is decidable and actionable**, "
        "so defects are caught by the agent or editor that introduces them, not at the gate. "
        "From that stage on it runs on every later pass. The **gate** that enforces it is "
        "derived: " + "; ".join(f"`{k}` = {v}" for k, v in cat.GATES.items()) + ".",
        "",
        "| stage | acts on findings | role of the checks | start here | running by the end |",
        "|---|---|---|---|---|",
    ]
    running = 0
    for s in cat.SIP_STAGES:
        n = sum(c.sip_stage == s.code for c in cat.CHECKS)
        running += n
        out.append(f"| [{s.code}](#stage-{s.code}) | {s.actor} | {s.role} | {n} | {running} |")
    for s in cat.SIP_STAGES:
        here = [c for c in cat.CHECKS if c.sip_stage == s.code]
        out += ["", f"### stage: {s.code}", "", f"*{s.actor}.* {s.role}", ""]
        if not here:
            continue
        out += ["| level | checks starting here (domain track first) |", "|---|---|"]
        for m in levels:
            ids = [c for c in here if c.maturity == m.code]
            if ids:
                out.append(f"| {m.code} | {_id_list(ids)} |")
    return out


def render_catalogue() -> str:
    checks = cat.CHECKS
    by_family = {f.code: [c for c in checks if c.family == f.code] for f in cat.FAMILIES}
    sev = Counter(c.severity for c in checks)
    meth = Counter(c.method for c in checks)
    adj = Counter(c.adjudication for c in checks)
    stage = Counter(c.stage for c in checks)
    oops = sorted({r for c in checks for r in c.refs if r.startswith("OOPS")},
                  key=lambda r: int(r.rsplit("P", 1)[1]))

    out = [
        "# Check Catalogue",
        "",
        "> Generated by `spec/build_docs.py` from `spec/check_catalogue.py` -- do not edit by hand.",
        "",
        f"**{len(checks)} checks in {len(cat.FAMILIES)} families.** "
        f"Deterministic: {adj['none']} · LLM-adjudicated candidates: {adj['llm']} · "
        f"human-adjudicated: {adj['human']}.",
        "",
        "| severity | count |  | method | count |  | stage | count |",
        "|---|---|---|---|---|---|---|---|",
    ]
    rows = max(len(cat.SEVERITIES), len(cat.METHODS), len(cat.STAGES))
    sevs, meths, stages = list(cat.SEVERITIES), list(cat.METHODS), list(cat.STAGES)
    for i in range(rows):
        s = f"{sevs[i]} | {sev[sevs[i]]}" if i < len(sevs) else " | "
        m = f"{meths[i]} | {meth[meths[i]]}" if i < len(meths) else " | "
        g = f"{stages[i]} | {stage[stages[i]]}" if i < len(stages) else " | "
        out.append(f"| {s} | | {m} | | {g} |")
    out += [
        "",
        "**Legend.** *Method* names the engine that generates findings (or candidates). "
        "*Adj.* = adjudication: `none` (decidable; the critic overrides the model), "
        "`llm` (deterministic candidates, LLM labels true/false positive, severity capped at "
        "major), `human`. *Stage*: " + "; ".join(f"`{k}` {v}" for k, v in cat.STAGES.items()) +
        ". *Mutation* is the S2 fault-injection operator whose mutants the check must kill. "
        "*Mat.* is the lowest [modelling-maturity level](#maturity-ladder) at which the check "
        "is switched on; *SIP stage* is the earliest [Semantic Intelligence Platform "
        "stage](#sip-lifecycle-stages) at which it is decidable and actionable.",
        "",
        f"OOPS! pitfalls covered: {', '.join(oops)}.",
        "",
        "**Contents.** [Families](#families) · [Maturity ladder](#maturity-ladder) · "
        "[SIP lifecycle stages](#sip-lifecycle-stages) · per-family detail: " +
        " · ".join(f"[{f.code}](#{f.code.lower()})" for f in cat.FAMILIES),
        "",
        "## Families",
        "",
        "| code | family | checks | purpose | reference oracles |",
        "|---|---|---|---|---|",
    ]
    for f in cat.FAMILIES:
        out.append(f"| [{f.code}](#{f.code.lower()}) | {f.title} | {len(by_family[f.code])} | "
                   f"{f.purpose} | {', '.join(f.oracles) or '--'} |")
    out += render_maturity()
    out += render_sip_stages()
    for f in cat.FAMILIES:
        out += ["", f"## {f.code}", "", f"**{f.title}.** {f.purpose}", "",
                "| id | check | sev. | method | adj. | applies | stage | mat. | SIP stage | mutation |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for c in by_family[f.code]:
            out.append(f"| {c.id} | **{_md_escape(c.title)}** | {c.severity} | {c.method} | "
                       f"{c.adjudication} | {', '.join(c.applies)} | {c.stage} | "
                       f"{c.maturity} | {c.sip_stage} | {c.mutation or '--'} |")
        out.append("")
        for c in by_family[f.code]:
            extra = []
            if c.refs:
                extra.append("refs: " + "; ".join(c.refs))
            if c.params:
                extra.append("params: " + ", ".join(f"`{k}={v}`" for k, v in c.params.items()))
            tail = f" *({' · '.join(extra)})*" if extra else ""
            out.append(f"- **{c.id}** -- {c.detects} *Why:* {c.rationale}{tail}")
    return "\n".join(out) + "\n"


def main() -> int:
    errors = validate_catalogue()
    model_errors, stats = validate_models()
    errors += model_errors
    (AGENT / "CHECK_CATALOGUE.md").write_text(render_catalogue(), encoding="utf-8")
    print(f"catalogue: {len(cat.CHECKS)} checks, {len(cat.FAMILIES)} families")
    for name, counts in stats.items():
        print(f"  {name}: {dict(counts)}")
    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        return 1
    print("OK -- CHECK_CATALOGUE.md written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
