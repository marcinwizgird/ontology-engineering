"""RSN: what the reasoner says (consistency, satisfiability, completeness)."""

from __future__ import annotations

from .. import vocab as V
from ..reasoning import reason
from ..registry import CheckContext, detector, finding


def reasoning(ctx: CheckContext):
    rl = ctx.profile.owl_profiles["RL"]["in_profile"]
    return ctx.memo("reasoning", lambda: reason(ctx.graph, rl_in_profile=rl))


def _needs_consistency(ctx: CheckContext) -> str | None:
    return None if reasoning(ctx).consistent else \
        "the ontology is inconsistent (RSN-01): every class is trivially unsatisfiable"


@detector("RSN-01")
def inconsistent(ctx: CheckContext):
    r = reasoning(ctx)
    out = []
    for cl in r.clashes:
        focus = cl.individual or (V.ontology_nodes(ctx.graph) or ["document"])[0]
        out.append(finding(
            "RSN-01", focus, "The ontology is inconsistent: " +
            (f"{V.local_name(cl.individual)} is a {cl.reason}." if cl.individual else cl.reason),
            related=cl.classes, evidence={"backend": r.backend, "clash": cl.reason},
            fix_hint="Remove the type assertion that puts the individual into both classes, "
                     "or remove the disjointness if the classes may overlap."))
    return out


@detector("RSN-02", requires=_needs_consistency)
def unsatisfiable(ctx: CheckContext):
    r = reasoning(ctx)
    out = []
    for u in r.unsatisfiable:
        kind = "root" if u["root"] else "derived"
        msg = f"{V.local_name(u['class'])} is unsatisfiable ({kind})"
        if u["root"]:
            msg += f": a member would be a {u['reason']}."
            hint = ("Inspect the disjointness and restrictions that meet in this class; "
                    "usually one axiom is wrong (e.g. a disjointness with an ancestor, HIER-05).")
        else:
            msg += f": it is a subclass of unsatisfiable {', '.join(V.local_name(v) for v in u['via'])}."
            hint = "Fix the root cause in the class it inherits from; this one then recovers."
        out.append(finding("RSN-02", u["class"], msg, related=u["via"] or u["clash_classes"],
                           evidence={"backend": r.backend, "root": u["root"], "via": u["via"],
                                     "clash": u["reason"], "method": "probe individual"},
                           fix_hint=hint))
    return out


@detector("RSN-08")
def incomplete(ctx: CheckContext):
    r = reasoning(ctx)
    if r.complete:
        return []
    first = ctx.profile.owl_profiles["RL"]["first_violation"]
    focus = (V.ontology_nodes(ctx.graph) or [ctx.load.source if ctx.load else "document"])[0]
    return [finding("RSN-08", focus, "Reasoning is incomplete: the ontology is outside OWL 2 RL "
                    f"(first excluded by {first}) and only the RL reasoner ran. A clean result "
                    "does not establish that every class is satisfiable.",
                    evidence={"backend": r.backend, "first_rl_violation": first},
                    fix_hint="Run the DL backend (HermiT, stage S1c) for a complete answer.")]
