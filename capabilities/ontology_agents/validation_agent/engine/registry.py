"""CheckRegistry: binds catalogue entries to detector functions.

The catalogue (``spec/check_catalogue.py``) is the source of truth. A detector can only
be registered under an id the catalogue declares, so the engine cannot emit a finding
outside the catalogue (constraint ``FindingsFromCatalogueOnly``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from rdflib import Graph

from ..spec import check_catalogue as catalogue
from .model import Finding

CATALOGUE_VERSION = "2026-10-04"

CHECKS = {c.id: c for c in catalogue.CHECKS}
FAMILIES = {f.code: f for f in catalogue.FAMILIES}
FAMILY_ORDER = [f.code for f in catalogue.FAMILIES]


@dataclass
class CheckContext:
    """What a detector may read. Detectors are pure functions of this context."""

    graph: Graph
    profile: Any                      # engine.profile.MeasuredProfile
    params: dict[str, dict] = field(default_factory=dict)
    shapes: Graph | None = None
    house_rules: Graph | None = None
    load: Any = None                  # engine.loader.LoadResult
    cache: dict[str, Any] = field(default_factory=dict)

    def param(self, check_id: str, name: str, default=None):
        merged = {**CHECKS[check_id].params, **self.params.get(check_id, {})}
        return merged.get(name, default)

    def memo(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]


Detector = Callable[[CheckContext], list[Finding]]
DETECTORS: dict[str, Detector] = {}
PREREQUISITES: dict[str, Callable[[CheckContext], str | None]] = {}


def detector(check_id: str, requires: Callable[[CheckContext], str | None] | None = None):
    """Register ``fn`` as the detector of ``check_id``. ``requires`` returns a skip reason
    when a prerequisite does not hold (e.g. no shapes graph for SHC-02)."""
    if check_id not in CHECKS:
        raise KeyError(f"{check_id} is not in the check catalogue")

    def wrap(fn: Detector) -> Detector:
        DETECTORS[check_id] = fn
        if requires is not None:
            PREREQUISITES[check_id] = requires
        return fn
    return wrap


def finding(check_id: str, focus, message: str, *, related=(), evidence=None,
            fix_hint: str = "", severity: str | None = None) -> Finding:
    """Build a finding with the catalogue's severity and method."""
    c = CHECKS[check_id]
    return Finding(
        check_id=check_id, severity=severity or c.severity, focus=str(focus), message=message,
        related=sorted({str(r) for r in related}), evidence=evidence or {},
        fix_hint=fix_hint, engine={"method": c.method})


def implemented(stage: str = "S1a") -> list[str]:
    """Catalogue ids of ``stage`` (and earlier) that have a detector, in catalogue order."""
    order = ["S1a", "S1b", "S1c"]
    allowed = set(order[: order.index(stage) + 1])
    _load_detectors()
    return [c.id for c in catalogue.CHECKS if c.stage in allowed and c.id in DETECTORS]


def checks_for_families(families) -> list[str]:
    return [cid for cid in implemented("S1c") if CHECKS[cid].family in set(families)]


def describe(check_id: str) -> dict:
    c = CHECKS[check_id]
    return {"id": c.id, "family": c.family, "family_title": FAMILIES[c.family].title,
            "title": c.title, "detects": c.detects, "rationale": c.rationale,
            "method": c.method, "severity": c.severity, "adjudication": c.adjudication,
            "applies": list(c.applies), "refs": list(c.refs), "params": dict(c.params),
            "mutation": c.mutation, "stage": c.stage,
            "maturity": c.maturity, "sip_stage": c.sip_stage, "gate": c.gate,
            "track": c.track,
            "implemented": c.id in DETECTORS}


_loaded = False


def _load_detectors() -> None:
    global _loaded
    if not _loaded:
        from . import checks  # noqa: F401  (registers the detectors)
        _loaded = True
