"""Transformation strategy: RDF extract -> NetworkX MultiDiGraph (the IR) + concept profiles.

The intermediate representation is a networkx.MultiDiGraph. Class records become nodes
keyed by IRI with the :Class label and spec-2.1 properties; taxonomy and object-property
edges become directed edges. Keeping an in-memory IR decouples extraction from loading:
the same graph can be exported to FalkorDB, serialised, inspected, or diffed.

Concept profiles (spec 5.1) live here because they need the taxonomy the IR already holds.
"""

from __future__ import annotations

import networkx as nx

from ..rdf import local_name
from .extract import ClassRecord, TaxonomyEdge, PropertyEdge

NO_DEFINITION = "No definition available."   # spec 4.1 non-null default


class MetaGraphBuilder:
    """Builds and holds the LPG intermediate representation as a MultiDiGraph."""

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_classes(self, classes: list[ClassRecord]) -> int:
        """Merge class nodes. Returns rows processed (duplicate IRIs collapse to one node)."""
        for c in classes:
            self.graph.add_node(
                c.iri, label="Class", iri=c.iri, short_name=c.short_name,
                name=c.name or c.short_name,               # spec 4.1 COALESCE(name, short_name)
                definition=c.definition or NO_DEFINITION,
                alt_labels=list(c.alt_labels),
            )
        return len(classes)

    def add_taxonomy(self, edges: list[TaxonomyEdge]) -> int:
        added = 0
        for e in edges:
            # Only link classes we captured; a subClassOf pointing at an unextracted or
            # anonymous superclass is skipped (the loader's Cypher MATCHes both ends too).
            if e.sub_iri in self.graph and e.super_iri in self.graph:
                self.graph.add_edge(e.sub_iri, e.super_iri, key="SUBCLASS_OF", type="SUBCLASS_OF")
                added += 1
        return added

    def add_object_properties(self, edges: list[PropertyEdge]) -> int:
        added = 0
        for e in edges:
            if e.domain_iri in self.graph and e.range_iri in self.graph:
                self.graph.add_edge(
                    e.domain_iri, e.range_iri, key=e.prop_iri,
                    type=e.rel_type, iri=e.prop_iri,
                    name=e.name or local_name(e.prop_iri),
                    definition=e.definition or NO_DEFINITION,
                )
                added += 1
        return added

    def superclasses(self, iri: str) -> list[str]:
        """Direct superclass IRIs (SUBCLASS_OF out-edges)."""
        return [v for _, v, k in self.graph.out_edges(iri, keys=True) if k == "SUBCLASS_OF"]

    def stats(self) -> dict:
        sub = sum(1 for *_, k in self.graph.edges(keys=True) if k == "SUBCLASS_OF")
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "subclass_edges": sub,
            "object_property_edges": self.graph.number_of_edges() - sub,
        }


def concept_profile(builder: MetaGraphBuilder, iri: str) -> str:
    """The Concept Profile Document for a class (spec 5.1) -- rich text for embedding.

    "Class: {name}. Synonyms: {alts}. Definition: {def}. Superclasses: {supers}." Empty
    sections are omitted so the sentence stays natural for the encoder.
    """
    node = builder.graph.nodes[iri]
    parts = [f"Class: {node['name']}."]

    alts = node.get("alt_labels") or []
    if alts:
        parts.append(f"Synonyms: {', '.join(alts)}.")

    definition = node.get("definition")
    if definition and definition != NO_DEFINITION:
        parts.append(f"Definition: {definition}" + ("" if definition.endswith(".") else "."))

    sup_names = sorted({builder.graph.nodes[s]["name"] for s in builder.superclasses(iri)
                        if s in builder.graph})
    if sup_names:
        parts.append(f"Superclasses: {', '.join(sup_names)}.")

    return " ".join(parts)
