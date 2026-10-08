"""DL: OWL 2 DL global restrictions and the profile report."""

from __future__ import annotations

from rdflib import URIRef
from rdflib.namespace import OWL, RDF

from .. import vocab as V
from ..registry import CheckContext, detector, finding


@detector("DL-02")
def class_used_as_individual(ctx: CheckContext):
    g = ctx.graph
    classes = set(V.declared_classes(g))
    punned = set(g.subjects(RDF.type, OWL.NamedIndividual))
    annotation = set(g.subjects(RDF.type, OWL.AnnotationProperty))
    out = []
    for c in sorted(classes - punned, key=str):
        uses = []
        for t in g.objects(c, RDF.type):
            if t not in V.META_TYPES and not V.is_builtin(t):
                uses.append(f"<{c}> rdf:type <{t}>")
        for p, o in g.predicate_objects(c):
            if p not in V.SCHEMA_PREDICATES and p not in annotation and not V.is_builtin(p):
                uses.append(f"<{c}> <{p}> {o.n3()}")
        for s, p in g.subject_predicates(c):
            if p not in V.SCHEMA_PREDICATES and p not in annotation and not V.is_builtin(p):
                uses.append(f"{s.n3()} <{p}> <{c}>")
        if uses:
            out.append(finding(
                "DL-02", c, f"Class {V.local_name(c)} is used as an individual without a "
                "declared punning intent.",
                evidence={"triples": sorted(uses)[:5]},
                fix_hint="If the class really is also an individual (metamodelling), declare "
                         "it owl:NamedIndividual as well; otherwise create a separate "
                         "individual or use an annotation property for the link."))
    return out


@detector("DL-08")
def profile_report(ctx: CheckContext):
    profiles = ctx.profile.owl_profiles
    nodes = V.ontology_nodes(ctx.graph)
    focus = nodes[0] if nodes and isinstance(nodes[0], URIRef) else (ctx.load.source if ctx.load else "document")
    parts = []
    for name in ("EL", "QL", "RL"):
        p = profiles[name]
        parts.append(f"OWL 2 {name}: " + ("yes" if p["in_profile"] else f"no, first excluded by {p['first_violation']}"))
    return [finding("DL-08", focus, "Profile report. " + "; ".join(parts) + ".",
                    evidence={"profiles": profiles, "expressivity": ctx.profile.expressivity},
                    fix_hint="Information only. Outside OWL 2 RL, the built-in RL reasoner is "
                             "incomplete (see RSN-08).")]
