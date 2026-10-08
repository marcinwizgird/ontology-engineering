"""METRIC: the measured position on the spectrum and the size/expressivity profile."""

from __future__ import annotations

from .. import vocab as V
from ..profile import spectrum_rank
from ..registry import CheckContext, detector, finding


def _focus(ctx: CheckContext):
    return (V.ontology_nodes(ctx.graph) or [ctx.load.source if ctx.load else "document"])[0]


@detector("METRIC-01")
def spectrum_mismatch(ctx: CheckContext):
    p = ctx.profile
    if p.declared_level is None or spectrum_rank(p.spectrum_level) >= spectrum_rank(p.declared_level):
        return []
    return [finding("METRIC-01", _focus(ctx),
                    f"Declared as a {p.declared_level}, but measured as a {p.spectrum_level}.",
                    evidence={"declared": p.declared_level, "measured": p.spectrum_level,
                              "evidence": p.spectrum_evidence},
                    fix_hint="Either add the structure the declared level promises (e.g. "
                             "restrictions, disjointness for a formal ontology) or declare "
                             "the level the artefact actually has.")]


@detector("METRIC-02")
def size_and_expressivity(ctx: CheckContext):
    c = ctx.profile.counts
    return [finding("METRIC-02", _focus(ctx),
                    f"{c['classes']} classes, {c['object_properties']} object and "
                    f"{c['datatype_properties']} datatype properties, {c['individuals']} "
                    f"individuals, {c['logical_axioms']} logical axioms; expressivity "
                    f"{ctx.profile.expressivity}; measured level {ctx.profile.spectrum_level}.",
                    evidence={"counts": c, "expressivity": ctx.profile.expressivity},
                    fix_hint="Information only.")]
