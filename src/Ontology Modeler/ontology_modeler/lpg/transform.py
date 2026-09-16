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
                # Only the file extractor knows these; the SPARQL one leaves the defaults.
                external=bool(getattr(c, "external", False)),
                module_iri=getattr(c, "module_iri", None),
            )
        return len(classes)

    def add_taxonomy(self, edges: list[TaxonomyEdge]) -> int:
        added = 0
        for e in edges:
            # Only link classes we captured; a subClassOf pointing at an unextracted or
            # anonymous superclass is skipped (the loader's Cypher MATCHes both ends too).
            if e.sub_iri in self.graph and e.super_iri in self.graph:
                self.graph.add_edge(e.sub_iri, e.super_iri, key="SUBCLASS_OF",
                                    type="SUBCLASS_OF", kind="taxonomy")
                added += 1
        return added

    def add_object_properties(self, edges: list[PropertyEdge]) -> int:
        added = 0
        for e in edges:
            if e.domain_iri in self.graph and e.range_iri in self.graph:
                self.graph.add_edge(
                    e.domain_iri, e.range_iri, key=e.prop_iri,
                    type=e.rel_type, iri=e.prop_iri, kind="object_property",
                    name=e.name or local_name(e.prop_iri),
                    definition=e.definition or NO_DEFINITION,
                )
                added += 1
        return added

    def add_restrictions(self, edges) -> int:
        """Add restriction shadow edges between named classes.

        The edge key carries the quantifier as well as the property, so
        `hasPart some Wheel` and `hasPart only Wheel` stay two distinct edges rather than
        one silently overwriting the other.
        """
        added = 0
        for e in edges:
            if e.source_iri not in self.graph or e.target_iri not in self.graph:
                continue
            self.graph.add_edge(
                e.source_iri, e.target_iri, key=f"{e.prop_iri}|{e.quantifier}",
                type=e.rel_type, iri=e.prop_iri, kind="restriction",
                name=e.name or local_name(e.prop_iri),
                quantifier=e.quantifier, cardinality=e.cardinality, origin=e.origin,
                definition=NO_DEFINITION,
            )
            added += 1
        return added

    def add_modules(self, modules) -> int:
        for m in modules:
            self.graph.add_node(m.iri, label="Module", iri=m.iri, name=m.name,
                                path=m.path, abstract=m.abstract or "")
        return len(modules)

    def add_defined_in(self, links) -> int:
        added = 0
        for link in links:
            if link.class_iri in self.graph and link.module_iri in self.graph:
                self.graph.add_edge(link.class_iri, link.module_iri, key="DEFINED_IN",
                                    type="DEFINED_IN", kind="defined_in")
                added += 1
        return added

    # -- read helpers --------------------------------------------------------- #

    def class_nodes(self):
        """(iri, data) for :Class nodes only -- :Module nodes share the same graph."""
        return [(n, d) for n, d in self.graph.nodes(data=True) if d.get("label") == "Class"]

    def relations(self, iri: str) -> list[tuple[str, str, str]]:
        """Outgoing non-taxonomy edges as (property name, quantifier, target name)."""
        out = []
        for _, target, data in self.graph.out_edges(iri, data=True):
            if data.get("kind") not in ("restriction", "object_property"):
                continue
            if target not in self.graph:
                continue
            out.append((data.get("name") or "", data.get("quantifier") or "some",
                        self.graph.nodes[target].get("name", target)))
        return out

    def superclasses(self, iri: str) -> list[str]:
        """Direct superclass IRIs (SUBCLASS_OF out-edges)."""
        return [v for _, v, k in self.graph.out_edges(iri, keys=True) if k == "SUBCLASS_OF"]

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for *_, data in self.graph.edges(data=True):
            kind = data.get("kind", "object_property")
            counts[kind] = counts.get(kind, 0) + 1
        classes = sum(1 for _, d in self.graph.nodes(data=True) if d.get("label") == "Class")
        return {
            "nodes": self.graph.number_of_nodes(),
            "classes": classes,
            "external_classes": sum(1 for _, d in self.graph.nodes(data=True)
                                    if d.get("label") == "Class" and d.get("external")),
            "modules": self.graph.number_of_nodes() - classes,
            "edges": self.graph.number_of_edges(),
            "subclass_edges": counts.get("taxonomy", 0),
            "object_property_edges": counts.get("object_property", 0),
            "restriction_edges": counts.get("restriction", 0),
            "defined_in_edges": counts.get("defined_in", 0),
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

    # Restriction-derived relations. For FIBO this is most of what distinguishes one
    # class from its siblings -- a profile without it embeds "x is a kind of agreement"
    # and little else, and every agreement then looks alike to the retriever.
    relations = builder.relations(iri)
    if relations:
        phrases = sorted({f"{name} {quantifier} {target}"
                          for name, quantifier, target in relations})
        parts.append(f"Relations: {'; '.join(phrases[:12])}.")

    module_iri = node.get("module_iri")
    if module_iri and module_iri in builder.graph:
        parts.append(f"Module: {builder.graph.nodes[module_iri].get('name')}.")

    return " ".join(parts)
