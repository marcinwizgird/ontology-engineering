"""PolicyEngine: the verdict is a pure function of findings, measured profile and policy.

    verdict(findings, measured, declared, policy) -> accept | revise | reject

(SPECIFICATION.md s.6.2). Precedence is reject > revise > accept, encoded as ordered
checks. Waivers are keyed on the *measured* level. An ``adjudicatedTrue`` finding counts
at most as ``major``, so model judgement alone can never reject (OVA-T03).
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .model import Finding
from .profile import spectrum_rank

POLICY_DIR = Path(__file__).resolve().parent.parent / "policy"
SEVERITY_RANK = {"blocker": 0, "major": 1, "minor": 2, "info": 3}
VERDICTS = ("accept", "revise", "reject")


@dataclass
class Waiver:
    id: str
    check: str
    when: dict
    reason: str

    def matches(self, f: Finding, measured_level: str, applies: list[str]) -> bool:
        if f.check_id != self.check:
            return False
        w = self.when
        if "measured_level" in w and measured_level not in _as_list(w["measured_level"]):
            return False
        if "profile" in w and not set(_as_list(w["profile"])) & set(applies):
            return False
        if "namespace" in w and not any(f.focus.startswith(ns) for ns in _as_list(w["namespace"])):
            return False
        return True


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


@dataclass
class Policy:
    name: str
    version: int
    description: str = ""
    severity_overrides: dict[str, str] = field(default_factory=dict)
    cap_non_blockers_at: str | None = None
    waivers: list[Waiver] = field(default_factory=list)
    params: dict[str, dict] = field(default_factory=dict)
    disabled_checks: list[str] = field(default_factory=list)
    house_rules: str | None = None

    @property
    def id(self) -> str:
        return f"{self.name}-v{self.version}"

    def house_rules_path(self) -> Path | None:
        return POLICY_DIR / self.house_rules if self.house_rules else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


def load_policy(name_or_path: str = "registry-default-v1") -> Policy:
    p = Path(name_or_path)
    if not p.suffix:
        p = POLICY_DIR / f"{name_or_path}.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    waivers = [Waiver(**w) for w in data.pop("waivers", []) or []]
    return Policy(waivers=waivers, **data)


def available_policies() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.yaml"))


def effective_severity(f: Finding, policy: Policy) -> str:
    sev = policy.severity_overrides.get(f.check_id, f.severity)
    if policy.cap_non_blockers_at and sev != "blocker" and \
            SEVERITY_RANK[sev] < SEVERITY_RANK[policy.cap_non_blockers_at]:
        sev = policy.cap_non_blockers_at
    if f.status == "adjudicatedTrue" and sev == "blocker":
        sev = "major"                              # adjudication cap, OVA-T03
    return sev


@dataclass
class Decision:
    verdict: str
    reasons: list[str]
    reportable: list[str]
    waived: list[dict]
    counts: dict[str, int]
    policy: str

    def to_dict(self) -> dict:
        return asdict(self)


def apply_policy(findings: list[Finding], measured_level: str, declared_level: str | None,
                 applies: list[str], policy: Policy) -> tuple[list[Finding], Decision]:
    """Return the findings with effective severity and waiver status, and the decision.
    The input list is not modified (the function is pure and idempotent)."""
    out: list[Finding] = []
    waived: list[dict] = []
    for f in findings:
        g = copy.deepcopy(f)
        g.severity = effective_severity(f, policy)
        if g.status in ("confirmed", "adjudicatedTrue"):
            w = next((w for w in policy.waivers if w.matches(g, measured_level, applies)), None)
            if w is not None:
                g.status = "waived"
                g.evidence = {**g.evidence, "waiver": w.id, "waiver_reason": w.reason}
                waived.append({"finding_id": g.finding_id, "check_id": g.check_id,
                               "waiver": w.id, "reason": w.reason})
        out.append(g)
    reportable = [f for f in out if f.status in ("confirmed", "adjudicatedTrue")]
    counts = {s: sum(1 for f in reportable if f.severity == s) for s in SEVERITY_RANK}
    blockers = sorted({f.check_id for f in reportable
                       if f.severity == "blocker" and f.status == "confirmed"})
    revisable = sorted({f.check_id for f in reportable if f.severity in ("blocker", "major", "minor")})
    below_declared = declared_level is not None and \
        spectrum_rank(measured_level) < spectrum_rank(declared_level)
    reasons: list[str] = []
    if blockers:
        verdict = "reject"
        reasons.append(f"{counts['blocker']} confirmed blocker finding(s): {', '.join(blockers)}")
    elif revisable or below_declared:
        verdict = "revise"
        if revisable:
            reasons.append(f"{counts['major']} major and {counts['minor']} minor finding(s): "
                           f"{', '.join(revisable)}")
        if below_declared:
            reasons.append(f"measured level {measured_level} is below the declared {declared_level}")
    else:
        verdict = "accept"
        reasons.append("no blocker, major or minor finding remains after waivers")
    if waived:
        reasons.append(f"{len(waived)} finding(s) waived by policy {policy.id}")
    return out, Decision(verdict, reasons, [f.finding_id for f in reportable], waived, counts, policy.id)
