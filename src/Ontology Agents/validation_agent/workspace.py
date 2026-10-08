"""ValidationWorkspace: one run, one tenant context.

Every tool in the belt and every assistant turn is bound to one workspace, so concurrent
sessions cannot see or overwrite each other's state (constraint ``SessionIsolation``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph

from . import ENGINE_VERSION
from .engine.loader import LoadResult, load_bytes, load_path
from .engine.model import CheckRun, Finding
from .engine.policy import Decision, Policy, load_policy
from .engine.profile import MeasuredProfile
from .engine.registry import CATALOGUE_VERSION, CheckContext


@dataclass
class ValidationWorkspace:
    load: LoadResult
    policy: Policy
    declared_level: str | None = None
    shapes_load: LoadResult | None = None
    tenant: str = "local"
    stage: str = "S1a"
    profile: MeasuredProfile | None = None
    findings: list[Finding] = field(default_factory=list)
    runs: dict[str, CheckRun] = field(default_factory=dict)
    decision: Decision | None = None
    ctx: CheckContext | None = None
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    millis: int = 0

    @property
    def graph(self) -> Graph | None:
        return self.load.graph

    @property
    def shapes(self) -> Graph | None:
        return self.shapes_load.graph if self.shapes_load else None

    @property
    def run_id(self) -> str:
        """Idempotency key: the same content, shapes, declared level and policy give the
        same run id (OVA-P05)."""
        key = "|".join([self.load.hash, self.shapes_load.hash if self.shapes_load else "",
                        self.declared_level or "", self.policy.id, ENGINE_VERSION])
        return "run-" + hashlib.sha256(key.encode()).hexdigest()[:12]

    @property
    def versions(self) -> dict[str, str]:
        return {"engine": ENGINE_VERSION, "catalogue": CATALOGUE_VERSION,
                "policy": self.policy.id, "stage": self.stage}

    def finding(self, finding_id: str) -> Finding | None:
        return next((f for f in self.findings if f.finding_id == finding_id), None)

    @classmethod
    def from_bytes(cls, data: bytes, name: str, *, declared_level: str | None = None,
                   policy: str | Policy = "registry-default-v1",
                   shapes: bytes | None = None, shapes_name: str = "shapes.ttl",
                   tenant: str = "local") -> "ValidationWorkspace":
        pol = policy if isinstance(policy, Policy) else load_policy(policy)
        return cls(load=load_bytes(data, name), policy=pol, declared_level=declared_level,
                   shapes_load=load_bytes(shapes, shapes_name) if shapes else None,
                   tenant=tenant)

    @classmethod
    def from_path(cls, path, *, declared_level: str | None = None,
                  policy: str | Policy = "registry-default-v1", shapes_path=None,
                  tenant: str = "local") -> "ValidationWorkspace":
        pol = policy if isinstance(policy, Policy) else load_policy(policy)
        return cls(load=load_path(path), policy=pol, declared_level=declared_level,
                   shapes_load=load_path(shapes_path) if shapes_path else None, tenant=tenant)
