"""META: ontology-level metadata and licensing."""

from __future__ import annotations

from rdflib.namespace import DC, DCTERMS, OWL, RDFS

from .. import vocab as V
from ..registry import CheckContext, detector, finding

ACCEPTED = {
    "dcterms:title": (DCTERMS.title, DC.title),
    "dcterms:description": (DCTERMS.description, DC.description, RDFS.comment),
    "dcterms:creator": (DCTERMS.creator, DC.creator),
    "dcterms:license": (DCTERMS.license, V.CC.license, V.SCHEMA.license),
    "owl:versionIRI": (OWL.versionIRI, OWL.versionInfo),
    "owl:versionInfo": (OWL.versionInfo, OWL.versionIRI),
}
"""Each required item and the properties that satisfy it."""


@detector("META-01")
def missing_metadata(ctx: CheckContext):
    g = ctx.graph
    required = ctx.param("META-01", "required", ["dcterms:title", "dcterms:license", "owl:versionIRI"])
    nodes = V.ontology_nodes(g)
    if not nodes:
        return [finding("META-01", ctx.load.source if ctx.load else "document",
                        "No ontology header, so none of the required metadata can be stated: "
                        + ", ".join(required) + ".",
                        evidence={"missing": list(required)},
                        fix_hint="Add an owl:Ontology header carrying " + ", ".join(required) + ".")]
    out = []
    for node in nodes:
        missing = [item for item in required
                   if not any((node, p, None) in g for p in ACCEPTED.get(item, ()))]
        if missing:
            out.append(finding("META-01", node, "The ontology header lacks " + ", ".join(missing) + ".",
                               evidence={"missing": missing, "required": list(required)},
                               fix_hint="Add the missing header annotations; a licence is what "
                                        "lets others legally reuse the ontology."))
    return out
