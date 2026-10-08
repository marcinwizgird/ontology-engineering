"""LEX: can a domain expert read and review it?"""

from __future__ import annotations

from rdflib import Literal

from .. import vocab as V
from ..registry import CheckContext, detector, finding


def _has_text(g, term, predicates) -> bool:
    return any(isinstance(o, Literal) and str(o).strip()
               for p in predicates for o in g.objects(term, p))


def _own_entities(g):
    return [t for t in sorted(set(V.declared_classes(g)) | set(V.declared_properties(g)), key=str)
            if not V.is_builtin(t)]


@detector("LEX-01")
def missing_label(ctx: CheckContext):
    g, out = ctx.graph, []
    for t in _own_entities(g):
        if not _has_text(g, t, V.LABEL_PROPERTIES):
            kind = "Class" if t in set(V.declared_classes(g)) else "Property"
            out.append(finding("LEX-01", t, f"{kind} {V.local_name(t)} has no rdfs:label or "
                               "skos:prefLabel.",
                               fix_hint="Add a human-readable label (with a language tag, "
                                        "e.g. @en)."))
    return out


@detector("LEX-02")
def missing_definition(ctx: CheckContext):
    g, out = ctx.graph, []
    for c in V.declared_classes(g):
        if V.is_builtin(c):
            continue
        if not _has_text(g, c, V.DEFINITION_PROPERTIES):
            out.append(finding("LEX-02", c, f"Class {V.local_name(c)} has no definition "
                               "(skos:definition, IAO:0000115 or rdfs:comment).",
                               fix_hint="Add a genus-differentia definition: "
                                        "'A <parent> that <distinguishing feature>'."))
    return out
