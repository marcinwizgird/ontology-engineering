"""Playground workbench: a Fuseki-backed editing surface for OWL + SKOS ontologies.

Bridges Microsoft Ontology-Playground's narrow entity/relationship model to rich RDF held
in Fuseki, so a graph can be loaded, edited visually, and propagated back WITHOUT losing the
~80-93% of triples Playground never sees.

The load path projects a full named graph to Playground's model (project.py); the save path
merges the edited projection onto a copy of the untouched base graph (merge.py) and syncs it
via the existing blank-node-aware GraphSynchronizer (diff.py). Everything the projection did
not surface is carried through byte-for-byte.
"""
from __future__ import annotations

from .model import Ontology, EntityType, Property, Relationship, RelationshipAttribute
from .project import Projection, project
from .merge import merge

__all__ = [
    "Ontology", "EntityType", "Property", "Relationship", "RelationshipAttribute",
    "Projection", "project", "merge",
]
