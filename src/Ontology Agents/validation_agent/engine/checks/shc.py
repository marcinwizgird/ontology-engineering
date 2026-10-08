"""SHC: closed-world conformance against supplied shapes and the house-rule pack."""

from __future__ import annotations

from .. import shacl
from .. import vocab as V
from ..registry import CheckContext, detector, finding


def _needs_shapes(ctx: CheckContext) -> str | None:
    return None if ctx.shapes is not None else "no shapes graph was supplied"


def _needs_house_rules(ctx: CheckContext) -> str | None:
    return None if ctx.house_rules is not None else "the policy names no house-rule pack"


def _findings(check_id: str, results, hint: str):
    out = []
    for r in results:
        path = f" on {V.local_name(r.path)}" if r.path else ""
        msg = r.message or f"{r.component} violated"
        out.append(finding(
            check_id, r.focus, f"{V.local_name(r.focus)}{path}: {msg}",
            related=[x for x in (r.path,) if x and not x.startswith("_:")],
            evidence={"shape": r.shape, "component": r.component, "path": r.path,
                      "value": r.value, "sh_severity": r.sh_severity},
            severity=shacl.severity_for(r), fix_hint=hint))
    return out


@detector("SHC-02", requires=_needs_shapes)
def data_non_conformant(ctx: CheckContext):
    _, results = ctx.memo("shacl:supplied", lambda: shacl.validate(ctx.graph, ctx.shapes))
    return _findings("SHC-02", results,
                     "Add or correct the value the shape requires, or fix the shape if the "
                     "data is right (SHACL reads missing values as missing: closed world).")


@detector("SHC-08", requires=_needs_house_rules)
def house_rule_violation(ctx: CheckContext):
    _, results = ctx.memo("shacl:house", lambda: shacl.validate(ctx.graph, ctx.house_rules))
    return _findings("SHC-08", results,
                     "Bring the entity in line with the organisation's modelling policy "
                     "(the house-rule pack named by the policy).")
