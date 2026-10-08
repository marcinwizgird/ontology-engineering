"""PROP: domains, ranges and characteristics."""

from __future__ import annotations

from rdflib.namespace import RDFS

from .. import vocab as V
from ..registry import CheckContext, detector, finding


@detector("PROP-01")
def missing_domain_or_range(ctx: CheckContext):
    g, out = ctx.graph, []
    props = sorted(set(V.object_properties(g)) | set(V.datatype_properties(g)), key=str)
    for p in props:
        if V.is_builtin(p):
            continue
        missing = [name for name, pred in (("domain", RDFS.domain), ("range", RDFS.range))
                   if (p, pred, None) not in g]
        if missing:
            out.append(finding(
                "PROP-01", p, f"Property {V.local_name(p)} has no {' and no '.join(missing)}.",
                evidence={"missing": missing},
                fix_hint="State the most specific domain and range that hold for every use; "
                         "without them, readers and tools cannot tell what the property links."))
    return out
