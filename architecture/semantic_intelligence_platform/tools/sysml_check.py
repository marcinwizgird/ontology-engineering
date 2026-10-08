"""Structural checker, traceability generator and diagram generator for the SIP models.

Run::

    python architecture/semantic_intelligence_platform/tools/sysml_check.py          # check
    python architecture/semantic_intelligence_platform/tools/sysml_check.py --write  # + generate

Why a checker of our own: the reference SysML v2 implementations are the OMG pilot
(Java/Eclipse) and Sensmetry's SysIDE (``pip install syside``), which requires a licence
key. This script does not replace a SysML v2 parser; it checks what an architecture
description most needs to stay honest:

1. syntax hygiene — balanced braces/parentheses per file, one top-level package;
2. **reference resolution** — every type after ``:``/``:>``/``~``, every ``satisfy``,
   ``verify``, ``frame concern``, ``stakeholder``, ``include use case``, ``expose`` and
   metadata usage names a definition that exists (or a ScalarValues type);
3. **completeness** — every requirement is satisfied by a white-box element *and*
   verified by a verification case; every viewpoint has a view; every concern is framed
   by a viewpoint; every stakeholder appears in a concern; every perspective kind is
   used by a requirement;
4. **test binding** — every test a verification case names exists in the test-suite;
5. **structural guarantees** — in ``SipSystem`` the only connection to ``store.write``
   comes from the tracker, and agents connect to nothing but the registry and gateway.

``--write`` regenerates ``generated/TRACEABILITY.md`` and the Mermaid diagrams in
``generated/diagrams/``; the build fails rather than writing from a broken model.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS = ROOT / "models"
GEN = ROOT / "generated"
REPO = ROOT.parent.parent
TESTS = REPO / "src" / "Semantic Intelligence Platform" / "semantic_intelligence" / "tests"

LIBRARY = {"String", "Integer", "Real", "Boolean", "Natural", "ScalarValues"}
DEF_RE = re.compile(
    r"\b(?:abstract\s+)?(part|port|interface|item|attribute|enum|requirement|verification|"
    r"concern|viewpoint|view|use\s+case|action|state|constraint|metadata|allocation|"
    r"connection|occurrence)\s+def\s+(?:<'([^']+)'>\s+)?(\w+)")


@dataclass
class Def:
    kind: str
    name: str
    ident: str | None
    package: str
    file: str
    body: str = ""
    doc: str = ""


@dataclass
class Model:
    defs: dict[str, Def] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)      # file -> code (no comments)
    raw: dict[str, str] = field(default_factory=dict)


def strip(text: str) -> str:
    """Remove strings' contents, block comments and line comments (keep newlines)."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text[i] == '"':
            j = text.find('"', i + 1)
            j = n if j < 0 else j + 1
            out.append('""')
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def body_of(code: str, start: int) -> str:
    """Text of the {...} block starting at or after *start* ('' for ';' declarations)."""
    i = start
    while i < len(code) and code[i] not in "{;":
        i += 1
    if i >= len(code) or code[i] == ";":
        return ""
    depth, j = 0, i
    while j < len(code):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return code[i + 1:j]
        j += 1
    return code[i + 1:]


def load() -> Model:
    m = Model()
    for f in sorted(MODELS.glob("*.sysml")):
        raw = f.read_text(encoding="utf-8")
        code = strip(raw)
        m.raw[f.name], m.texts[f.name] = raw, code
        for a, b in ("{}", "()", "[]"):
            if code.count(a) != code.count(b):
                m.problems.append(f"{f.name}: unbalanced {a}{b} "
                                  f"({code.count(a)} vs {code.count(b)})")
        pk = re.findall(r"^package\s+(\w+)", code, re.M)
        if len(pk) != 1:
            m.problems.append(f"{f.name}: expected one top-level package, found {pk}")
            continue
        for d in DEF_RE.finditer(code):
            kind, ident, name = re.sub(r"\s+", " ", d.group(1)), d.group(2), d.group(3)
            if name in m.defs:
                m.problems.append(f"{f.name}: duplicate definition {name} "
                                  f"(also in {m.defs[name].file})")
            m.defs[name] = Def(kind, name, ident, pk[0], f.name, body_of(code, d.end()))
        for d in re.finditer(r"\b(?:requirement|verification)\s+def\s+(?:<'[^']+'>\s+)?(\w+)"
                             r"\s*\{\s*(?:@\w+\s*\{[^}]*\}\s*)?doc\s*/\*(.*?)\*/", raw, re.S):
            if d.group(1) in m.defs:
                m.defs[d.group(1)].doc = re.sub(r"\s*\*\s*", " ", d.group(2)).strip()
    return m


def usages(code: str) -> dict[str, str]:
    """name -> type for `part x : T`, `port x : T`, ... usages."""
    out = {}
    for u in re.finditer(r"\b(?:part|port|item|action|state|requirement|attribute|ref)\s+"
                         r"(\w+)\s*:\s*~?(\w+)", code):
        out[u.group(1)] = u.group(2)
    return out


def check(m: Model) -> dict:
    defs = m.defs
    all_code = "\n".join(m.texts.values())
    enum_literals = defaultdict(set)
    for d in defs.values():
        if d.kind == "enum":
            enum_literals[d.name] = set(re.findall(r"\benum\s+(\w+)", d.body))

    def known(name: str) -> bool:
        return name in defs or name in LIBRARY

    # -- 2. reference resolution -------------------------------------------- #
    for f, code in m.texts.items():
        for r in re.finditer(r"(?<![:\w]):\s*~?([A-Z]\w*)(?:\s*\[|\s*;|\s*\{|\s*=|\s+by|\s+connect|\s*,|\s*$)",
                             code, re.M):
            if not known(r.group(1)):
                m.problems.append(f"{f}: unresolved type {r.group(1)}")
        for r in re.finditer(r":>\s*(\w+)", code):
            if r.group(0).startswith(":>>"):
                continue
            if not known(r.group(1)):
                m.problems.append(f"{f}: unresolved supertype {r.group(1)}")
        for r in re.finditer(r"@(\w+)", code):
            if r.group(1) not in defs or defs[r.group(1)].kind != "metadata":
                m.problems.append(f"{f}: unknown metadata @{r.group(1)}")
        for r in re.finditer(r"(\w+)::(\w+)", code):
            enum, lit = r.group(1), r.group(2)
            if enum in enum_literals and lit not in enum_literals[enum]:
                m.problems.append(f"{f}: {enum} has no literal {lit}")
        for r in re.finditer(r"expose\s+(\w+)::", code):
            if r.group(1) not in {re.findall(r'^package\s+(\w+)', c, re.M)[0]
                                  for c in m.texts.values()}:
                m.problems.append(f"{f}: expose of unknown package {r.group(1)}")
    # -- 3. completeness ------------------------------------------------------ #
    reqs = {n: d for n, d in defs.items() if d.kind == "requirement"
            and (d.ident or "").startswith(("FR-", "QR-"))}
    satisfied: dict[str, list[str]] = defaultdict(list)
    for r in re.finditer(r"satisfy\s+requirement\s*:\s*(\w+)\s+by\s+([\w.]+)", all_code):
        if r.group(1) not in reqs:
            m.problems.append(f"satisfy of unknown requirement {r.group(1)}")
        satisfied[r.group(1)].append(r.group(2))
    verified: dict[str, list[str]] = defaultdict(list)
    tests_named: dict[str, list[str]] = {}
    for n, d in defs.items():
        if d.kind != "verification":
            continue
        for r in re.finditer(r"verify\s+requirement\s*:\s*(\w+)", d.body):
            if r.group(1) not in reqs:
                m.problems.append(f"{n}: verifies unknown requirement {r.group(1)}")
            verified[r.group(1)].append(d.ident or n)
        t = re.search(rf"verification\s+def\s+<'{re.escape(d.ident or '')}'>\s+{n}.*?"
                      r'attribute\s+test\s*:\s*String\s*=\s*"([^"]+)"', m.raw[d.file], re.S)
        tests_named[d.ident or n] = t.group(1).split() if t else []
    for n in reqs:
        if not satisfied.get(n):
            m.problems.append(f"requirement {reqs[n].ident} {n} is not satisfied by any element")
        if not verified.get(n):
            m.problems.append(f"requirement {reqs[n].ident} {n} is not verified")
    sysdef = defs.get("SipSystem")
    sys_parts = usages(sysdef.body) if sysdef else {}
    for n, by in satisfied.items():
        for path in by:
            head = path.split(".")[-1]
            if head not in sys_parts:
                m.problems.append(f"satisfy {n} by {path}: no part {head!r} in SipSystem")
    viewpoints = {n for n, d in defs.items() if d.kind == "viewpoint"}
    views = {n: re.findall(r"satisfy\s+requirement\s*:\s*(\w+)", d.body)
             for n, d in defs.items() if d.kind == "view"}
    for vp in viewpoints:
        if not any(vp in sats for sats in views.values()):
            m.problems.append(f"viewpoint {vp} has no view")
    concerns = {n for n, d in defs.items() if d.kind == "concern"}
    framed = set(re.findall(r"frame\s+concern\s+\w+\s*:\s*(\w+)", all_code))
    for c in concerns - framed:
        m.problems.append(f"concern {c} is framed by no viewpoint")
    stakeholders = {n for n, d in defs.items() if d.kind == "part" and
                    re.search(rf"part\s+def\s+{n}\s*:>\s*Stakeholder", all_code)}
    in_concerns = set(re.findall(r"stakeholder\s+\w+\s*:\s*(\w+)", all_code))
    for s in stakeholders - in_concerns:
        m.problems.append(f"stakeholder {s} appears in no concern")
    used_kinds = set(re.findall(r"PerspectiveKind::(\w+)", m.texts.get("sip_requirements.sysml", "")))
    for k in enum_literals.get("PerspectiveKind", set()) - used_kinds:
        m.problems.append(f"perspective {k} drives no requirement")
    # -- 4. test binding ------------------------------------------------------- #
    existing = set()
    for tf in TESTS.glob("test_*.py"):
        for fn in re.findall(r"^def\s+(test_\w+)", tf.read_text(encoding="utf-8"), re.M):
            existing.add(f"{tf.name}::{fn}")
    for v, names in tests_named.items():
        for t in names:
            if t.startswith("manual:"):
                continue
            if t not in existing:
                m.problems.append(f"{v}: test {t} does not exist")
    # -- 5. structural guarantees ------------------------------------------- #
    if sysdef:
        conns = re.findall(r"connect\s+([\w.]+)\s+to\s+([\w.]+)", sysdef.body)
        writers = [a for a, b in conns if b == "store.write"]
        if writers != ["tracker.write"]:
            m.problems.append(f"guarantee 1 violated: writers to store.write = {writers}")
        agent_parts = {p for p, t in sys_parts.items() if defs.get(t) and
                       re.search(rf"part\s+def\s+{t}\s*:>\s*SpecialistAgent", all_code)}
        for a, b in conns:
            if a.split(".")[0] in agent_parts and b.split(".")[0] not in ("registry", "gateway"):
                m.problems.append(f"guarantee 2 violated: agent {a} connected to {b}")
    return {"requirements": reqs, "satisfied": satisfied, "verified": verified,
            "tests": tests_named, "defs": defs}


# --------------------------------------------------------------------------- #
# generation
# --------------------------------------------------------------------------- #

def traceability(m: Model, res: dict) -> str:
    reqs = res["requirements"]
    raw_req = m.raw["sip_requirements.sysml"]

    def attr(name, key):
        blk = re.search(rf"requirement\s+def\s+<'[^']+'>\s+{name}\s*\{{(.*?)\n    \}}", raw_req, re.S)
        if not blk:
            return ""
        a = re.search(rf'{key}\s*=\s*(?:"([^"]*)"|PerspectiveKind::(\w+))', blk.group(1))
        return (a.group(1) or a.group(2)) if a else ""
    lines = ["# Requirements traceability (generated)", "",
             "Generated by `tools/sysml_check.py --write` from `models/*.sysml`. Do not edit.", "",
             "| ID | Requirement | Origin / perspective | Satisfied by | Verified by |",
             "|---|---|---|---|---|"]
    for n, d in sorted(reqs.items(), key=lambda kv: kv[1].ident):
        origin = attr(n, "sourceTool")
        if origin:
            art = attr(n, "sourceArtefact")
            origin = f"{origin} — `{art}`" if art else origin
        else:
            origin = f"*{attr(n, 'kind')}*"
        sat = ", ".join(sorted({p.split('.')[-1] for p in res["satisfied"][n]}))
        ver = ", ".join(sorted(set(res["verified"][n])))
        lines.append(f"| {d.ident} | **{n}** — {d.doc[:140]}{'…' if len(d.doc) > 140 else ''} "
                     f"| {origin} | {sat} | {ver} |")
    lines += ["", "## Verification cases → tests", "", "| Case | Tests |", "|---|---|"]
    for v, ts in sorted(res["tests"].items()):
        lines.append(f"| {v} | " + "<br>".join(f"`{t}`" for t in ts) + " |")
    return "\n".join(lines) + "\n"


def mermaid(m: Model) -> dict[str, str]:
    out = {}
    defs = m.defs
    # context
    ctx = re.search(r"part\s+context\s*\{(.*?)\n    \}", m.texts["sip_context.sysml"], re.S).group(1)
    lines = ["flowchart LR"]
    for name, t in usages(ctx).items():
        shape = f'{name}(["{name}<br/><small>{t}</small>"])' if name != "sip" else \
            f'{name}[["Semantic Intelligence Platform"]]'
        lines.append(f"  {shape}")
    for a, b in re.findall(r"connect\s+([\w.]+)\s+to\s+([\w.]+)", ctx):
        lines.append(f"  {a.split('.')[0]} -- {a.split('.')[-1]} --- {b.split('.')[0]}")
    out["context"] = "\n".join(lines)
    # functional white box
    body = defs["SipSystem"].body
    parts = usages(body)
    lines = ["flowchart TB"]
    groups = {"edge": "Edge", "registry": "Core", "pdp": "Core", "tracker": "Core",
              "store": "Core", "governance": "Core", "events": "Core"}
    for p, t in parts.items():
        if t.endswith("Agent") or t in ("ModelingCopilot", "KnowledgeGraphBuilder"):
            groups[p] = "Agents"
        elif p in ("gateway", "runtime", "conductor"):
            groups[p] = "Agents"
        else:
            groups.setdefault(p, "Services")
    for g in ("Edge", "Core", "Services", "Agents"):
        lines.append(f"  subgraph {g}")
        for p, t in parts.items():
            if groups[p] == g:
                lines.append(f'    {p}["{t}"]')
        lines.append("  end")
    for name, a, b in re.findall(r"interface\s+(\w+)\s*:\s*\w+\s+connect\s+([\w.]+)\s+to\s+([\w.]+)", body):
        style = "==>" if b == "store.write" else "-->"
        lines.append(f"  {a.split('.')[0]} {style}|{b.split('.')[-1]}| {b.split('.')[0]}")
    out["functional"] = "\n".join(lines)
    # E2E action
    act = defs["ConstructKnowledge"].body
    lines = ["flowchart LR"]
    for a, b in re.findall(r"first\s+(\w+)\s+then\s+(\w+)", act):
        fa = f'{a}{{{{"{a}"}}}}' if a.endswith("Gate") else a
        fb = f'{b}{{{{"{b}"}}}}' if b.endswith("Gate") else b
        lines.append(f"  {fa} --> {fb}")
    out["e2e"] = "\n".join(lines)
    loop = defs["AgentLoop"].body
    out["agent_loop"] = "flowchart LR\n" + "\n".join(
        f"  {a} --> {b}" for a, b in re.findall(r"first\s+(\w+)\s+then\s+(\w+)", loop))
    for st in ("CommitLifecycle", "ProposalLifecycle", "StageLifecycle", "ReasonerStatus",
               "WriteCoordinatorState"):
        b = defs[st].body
        lines = ["stateDiagram-v2"]
        first = re.search(r"entry;\s*then\s+(\w+)", b)
        if first:
            lines.append(f"  [*] --> {first.group(1)}")
        for name, a, c in re.findall(r"transition\s+(\w+)\s+first\s+(\w+)\s+then\s+(\w+)", b):
            lines.append(f"  {a} --> {c} : {name}")
        out[f"stm_{st}"] = "\n".join(lines)
    # deployment allocation
    dep = re.search(r"part\s+deployment\s*\{(.*?)\n    \}", m.texts["sip_deployment.sysml"], re.S).group(1)
    lines = ["flowchart LR"]
    nodes = sorted({b.split(".")[-1] for _, b in re.findall(r"allocate\s+([\w.]+)\s+to\s+([\w.]+)", dep)})
    for n in nodes:
        lines.append(f'  subgraph {n}_node["{n}"]')
        for a, b in re.findall(r"allocate\s+([\w.]+)\s+to\s+([\w.]+)", dep):
            if b.split(".")[-1] == n:
                lines.append(f"    {a.split('.')[-1]}")
        lines.append("  end")
    out["deployment"] = "\n".join(lines)
    # viewpoints -> concerns -> stakeholders
    lines = ["flowchart LR"]
    for n, d in defs.items():
        if d.kind == "viewpoint":
            for c in re.findall(r"frame\s+concern\s+\w+\s*:\s*(\w+)", d.body):
                lines.append(f"  {n}[/{n}/] --> {c}([{c}])")
    out["viewpoints"] = "\n".join(lines)
    return out


def main(argv: list[str]) -> int:
    m = load()
    res = check(m)
    kinds = defaultdict(int)
    for d in m.defs.values():
        kinds[d.kind] += 1
    print(f"models: {len(m.texts)} files, {len(m.defs)} definitions "
          f"({', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))})")
    print(f"requirements: {len(res['requirements'])}, satisfied: {len(res['satisfied'])}, "
          f"verified: {len(res['verified'])}")
    for p in m.problems:
        print("PROBLEM:", p)
    print(f"problems: {len(m.problems)}")
    if m.problems:
        return 1
    if "--write" in argv:
        (GEN / "diagrams").mkdir(parents=True, exist_ok=True)
        (GEN / "TRACEABILITY.md").write_text(traceability(m, res), encoding="utf-8")
        for name, text in mermaid(m).items():
            (GEN / "diagrams" / f"{name}.mmd").write_text(text + "\n", encoding="utf-8")
        print(f"wrote {GEN / 'TRACEABILITY.md'} and {len(mermaid(m))} diagrams")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
