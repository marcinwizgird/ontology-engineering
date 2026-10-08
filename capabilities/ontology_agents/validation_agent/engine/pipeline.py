"""The deterministic pipeline (SPECIFICATION.md s.5.1), S1a subset:

    load -> profile -> SYN -> DECL -> DL -> RSN -> SHC -> HIER/PROP/LEX/SKOS/META/METRIC
         -> aggregate -> policy

SYN-01 short-circuits the run. A check whose prerequisite failed is reported as
``skipped`` with the reason, never as passed. A detector that crashes is also reported as
``skipped`` (with the error), so a crash is never read as a pass.
"""

from __future__ import annotations

import time

from rdflib import Graph

from . import registry
from .model import CheckRun
from .policy import apply_policy
from .profile import measure
from .registry import CHECKS, CheckContext


def _house_rules(ws) -> Graph | None:
    path = ws.policy.house_rules_path()
    if path is None or not path.exists():
        return None
    g = Graph()
    g.parse(path, format="turtle")
    return g


def run(ws):
    """Run every implemented check of ``ws.stage`` and apply the policy. Returns ``ws``."""
    t0 = time.perf_counter()
    ids = registry.implemented(ws.stage)
    ws.runs, raw = {}, []
    if not ws.load.loaded:
        raw = registry.DETECTORS["SYN-01"](CheckContext(graph=Graph(), profile=None, load=ws.load))
        ws.runs["SYN-01"] = CheckRun("SYN-01", "failed", findings=len(raw))
        for cid in ids:
            if cid != "SYN-01":
                ws.runs[cid] = CheckRun(cid, "skipped", "the document does not parse (SYN-01)")
        ws.profile = None
    else:
        shapes_ok = ws.shapes_load is not None and ws.shapes_load.loaded
        ws.profile = measure(ws.graph, ws.declared_level, shapes=shapes_ok)
        ctx = CheckContext(graph=ws.graph, profile=ws.profile, params=ws.policy.params,
                           shapes=ws.shapes if shapes_ok else None,
                           house_rules=_house_rules(ws), load=ws.load)
        ws.ctx = ctx
        if ws.shapes_load is not None and not ws.shapes_load.loaded:
            ws.profile.notes.append(f"the shapes graph does not parse: {ws.shapes_load.error}")
        for cid in ids:
            check = CHECKS[cid]
            if cid in ws.policy.disabled_checks:
                ws.runs[cid] = CheckRun(cid, "skipped", f"disabled by policy {ws.policy.id}")
                continue
            if "all" not in check.applies and not set(check.applies) & set(ws.profile.applies):
                ws.runs[cid] = CheckRun(cid, "not-applicable",
                                        f"applies to {', '.join(check.applies)}; measured "
                                        f"profile is {', '.join(ws.profile.applies)}")
                continue
            prereq = registry.PREREQUISITES.get(cid)
            reason = prereq(ctx) if prereq else None
            if reason:
                ws.runs[cid] = CheckRun(cid, "skipped", reason)
                continue
            t1 = time.perf_counter()
            try:
                found = registry.DETECTORS[cid](ctx)
            except Exception as exc:  # a crash is never a pass
                ws.runs[cid] = CheckRun(cid, "skipped", f"detector error: {type(exc).__name__}: {exc}")
                continue
            ms = int((time.perf_counter() - t1) * 1000)
            status = "passed" if not found else                 "info" if all(f.severity == "info" for f in found) else "failed"
            ws.runs[cid] = CheckRun(cid, status, findings=len(found), millis=ms)
            raw.extend(found)
    raw.sort(key=lambda f: (ids.index(f.check_id), f.sort_key()))
    for i, f in enumerate(raw, 1):
        f.finding_id = f"f-{i:04d}"
        f.engine = {**f.engine, "version": ws.versions["engine"]}
    measured = ws.profile.spectrum_level if ws.profile else "controlled-vocabulary"
    applies = ws.profile.applies if ws.profile else []
    ws.findings, ws.decision = apply_policy(raw, measured, ws.declared_level, applies, ws.policy)
    ws.millis = int((time.perf_counter() - t0) * 1000)
    return ws

