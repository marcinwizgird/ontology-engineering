"""Finding and check-run records (SPECIFICATION.md s.6.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

FINDING_STATUSES = ("candidate", "adjudicatedTrue", "adjudicatedFalse", "unsure",
                    "confirmed", "waived")

RUN_STATUSES = ("passed", "failed", "info", "skipped", "not-applicable")
"""``passed``: the check ran and found nothing; ``failed``: it ran and found something;
``info``: it ran and reported information only (DL-08, METRIC-02, RSN-08);
``skipped``: a prerequisite failed (never read as passed); ``not-applicable``: the
measured profile is outside the check's ``applies``."""


@dataclass
class Finding:
    check_id: str
    severity: str
    focus: str
    message: str
    related: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    fix_hint: str = ""
    status: str = "confirmed"
    finding_id: str = ""
    justification: list[str] = field(default_factory=list)
    root_cause: str | None = None
    adjudication: dict[str, Any] | None = None
    engine: dict[str, str] = field(default_factory=dict)

    def sort_key(self) -> tuple:
        return (self.check_id, self.focus, tuple(self.related), self.message)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # finding_id first, as in the specification's schema
        return {"finding_id": d.pop("finding_id"), **d}


@dataclass
class CheckRun:
    check_id: str
    status: str
    reason: str = ""
    findings: int = 0
    millis: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
