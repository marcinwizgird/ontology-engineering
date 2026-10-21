"""The view as JSON: a superset of the Ontology-Playground ``Ontology`` object.

``entityTypes`` and ``relationships`` keep Playground's field names
(``capabilities/ontology_modeler/ontology_modeler/playground/model.py``), so its
``Ontology.from_dict`` accepts the payload. Everything SIP adds sits under a ``sip`` key
on each element, which the Playground ignores:

* entity  ``sip``: dist, doi, module, instances, defined, attributes (Manchester text),
  complex (badged axioms), guarded/hidden (expand-on-demand counts), and the overlays
  (state, commits, findings, unsatisfiable, cq pass/fail);
* relationship ``sip``: tag (some/only/min n …), prop, via (≡ | or | inferred), state,
  inferred.
"""

from __future__ import annotations

from .index import Edge, OntologyIndex, module_label
from .neighbourhood import View

KIND_COLOR = {"class": "#e8eaf6", "concept": "#e0f2f1"}
PLAYGROUND_EDGE = {"subClassOf", "broader", "narrower", "mapping", "objectProperty"}


def _cardinality(e: Edge) -> str:
    if e.kind == "restriction" and e.tag in ("exactly 1", "max 1"):
        return "many-to-one"
    return "many-to-many"


def relationship(e: Edge, ann: dict | None) -> dict:
    return {"id": e.id, "name": e.text, "from": e.source, "to": e.target,
            "kind": e.kind, "cardinality": _cardinality(e),
            "sip": {"tag": e.tag, "prop": e.prop, "via": e.via,
                    "playgroundKind": e.kind in PLAYGROUND_EDGE,
                    **(ann or {"state": "asserted", "inferred": e.via == "inferred"})}}


def to_playground(view: View, index: OntologyIndex, ann: dict | None = None,
                  name: str = "") -> dict:
    ann = ann or {"nodes": {}, "edges": {}, "summary": {}}
    entities = []
    for iri, meta in view.nodes.items():
        n = index.nodes[iri]
        entities.append({
            "id": iri, "name": n.label, "description": n.description, "properties": [],
            "kind": n.kind, "icon": "Circle", "color": KIND_COLOR.get(n.kind, "#eeeeee"),
            "sip": {"seed": iri == view.seed, "dist": meta["dist"], "doi": meta["doi"],
                    "via": meta["via"], "module": n.module,
                    "moduleLabel": module_label(n.module), "instances": n.instances,
                    "defined": n.defined, "deprecated": n.deprecated,
                    "attributes": n.attributes[:12], "attributeCount": len(n.attributes),
                    "complex": n.complex[:6], "complexCount": len(n.complex),
                    "guarded": view.guarded.get(iri), "hidden": view.hidden.get(iri, 0),
                    **ann["nodes"].get(iri, {"state": "asserted"})}})
    rels = [relationship(e, ann["edges"].get(e.id)) for e in view.edges]
    return {
        "name": name or f"Neighbourhood of {index.nodes[view.seed].label}",
        "description": "SIP ontology view (search-first ego graph with overlays)",
        "entityTypes": entities, "relationships": rels,
        "sip": {"seed": view.seed, "params": view.params,
                "stats": {"nodes": len(entities), "edges": len(rels),
                          "candidates": view.candidates, "truncated": view.truncated,
                          "guarded": len(view.guarded), "ms": view.ms},
                "summary": ann.get("summary", {})},
    }
