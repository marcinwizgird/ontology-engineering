"""The Playground data model, in Python, with a unified node/edge `kind`.

These dataclasses mirror Ontology-Playground's TypeScript interfaces (`src/data/ontology.ts`)
so `to_dict()` is a JSON object the app's store ingests, and `from_dict()` accepts what it
sends back. Two additions carry the OWL/SKOS distinction the base app lacks:

  * EntityType.kind   -- 'class' (owl:Class) or 'concept' (skos:Concept). Drives node icon/
    colour in the frontend adapter; on save the server re-derives it from the base graph, so
    it never has to survive a lossy client round-trip.
  * Relationship.kind -- 'subClassOf' | 'broader' | 'narrower' | 'mapping' | 'objectProperty'.

Fidelity notes:
  * `Property` has NO id -- an entity attribute is keyed by (owning node, name); datatype-
    property IRIs cannot round-trip through the UI, so the merge re-keys them by name.
  * `EntityType.id` and `Relationship.id` DO round-trip and hold the real IRI (classes,
    concepts, object properties) or a deterministic endpoint key (subClassOf/broader/mapping
    edges, which are bare triples with no identity beyond their endpoints).
  * `cardinality`, `icon`, `color` are presentation-only; the merge never writes them back.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

PROPERTY_TYPES = ("string", "integer", "decimal", "double", "date", "datetime", "boolean", "enum")
CARDINALITIES = ("one-to-one", "one-to-many", "many-to-one", "many-to-many")
NODE_KINDS = ("class", "concept")
EDGE_KINDS = ("subClassOf", "broader", "narrower", "mapping", "objectProperty")


@dataclass
class Property:
    """A datatype attribute shown under a node. No id: keyed by (owner node, name)."""

    name: str
    type: str = "string"
    isIdentifier: Optional[bool] = None
    unit: Optional[str] = None
    values: Optional[list[str]] = None
    description: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.isIdentifier is not None:
            d["isIdentifier"] = self.isIdentifier
        if self.unit is not None:
            d["unit"] = self.unit
        if self.values is not None:
            d["values"] = self.values
        if self.description is not None:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Property":
        return cls(
            name=d["name"], type=d.get("type", "string"),
            isIdentifier=d.get("isIdentifier"), unit=d.get("unit"),
            values=d.get("values"), description=d.get("description"),
        )


@dataclass
class RelationshipAttribute:
    name: str
    type: str = "string"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RelationshipAttribute":
        return cls(name=d["name"], type=d.get("type", "string"))


@dataclass
class Relationship:
    """An edge. `id` is a property IRI (objectProperty) or an endpoint key (triple edges)."""

    id: str
    name: str
    from_: str
    to: str
    kind: str = "objectProperty"
    cardinality: str = "many-to-many"
    description: Optional[str] = None
    attributes: Optional[list[RelationshipAttribute]] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "name": self.name,
            "from": self.from_, "to": self.to,   # 'from' is a Python keyword; JSON key is 'from'
            "kind": self.kind, "cardinality": self.cardinality,
        }
        if self.description is not None:
            d["description"] = self.description
        if self.attributes is not None:
            d["attributes"] = [a.to_dict() for a in self.attributes]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Relationship":
        attrs = d.get("attributes")
        return cls(
            id=d["id"], name=d["name"], from_=d["from"], to=d["to"],
            kind=d.get("kind", "objectProperty"),
            cardinality=d.get("cardinality", "many-to-many"),
            description=d.get("description"),
            attributes=[RelationshipAttribute.from_dict(a) for a in attrs] if attrs else None,
        )


@dataclass
class EntityType:
    """A node: a named owl:Class (kind='class') or skos:Concept (kind='concept')."""

    id: str
    name: str
    description: str = ""
    properties: list[Property] = field(default_factory=list)
    kind: str = "class"
    icon: str = "Circle"
    color: str = "#6366f1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "properties": [p.to_dict() for p in self.properties],
            "kind": self.kind, "icon": self.icon, "color": self.color,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EntityType":
        return cls(
            id=d["id"], name=d["name"], description=d.get("description", ""),
            properties=[Property.from_dict(p) for p in d.get("properties", [])],
            kind=d.get("kind", "class"),
            icon=d.get("icon", "Circle"), color=d.get("color", "#6366f1"),
        )


@dataclass
class Ontology:
    """The whole editable projection: Playground's `Ontology` object, OWL+SKOS unified."""

    name: str
    description: str = ""
    entityTypes: list[EntityType] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "entityTypes": [e.to_dict() for e in self.entityTypes],
            "relationships": [r.to_dict() for r in self.relationships],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ontology":
        return cls(
            name=d.get("name", ""), description=d.get("description", ""),
            entityTypes=[EntityType.from_dict(e) for e in d.get("entityTypes", [])],
            relationships=[Relationship.from_dict(r) for r in d.get("relationships", [])],
        )
