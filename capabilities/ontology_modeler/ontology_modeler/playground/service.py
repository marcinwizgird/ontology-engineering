"""PlaygroundService -- load/save orchestration between Fuseki and the editable projection.

load(graph_uri):   fetch the full named graph -> project -> envelope for the browser.
save(graph_uri, edited): fetch the full graph AGAIN (the current base), re-project it, merge the
    edited projection onto it, and sync the result via the blank-node-aware GraphSynchronizer.

Re-fetching on save keeps the service stateless (no per-session provenance to hold) and makes
the write diff against whatever is CURRENTLY in Fuseki, so a concurrent change is reconciled
rather than clobbered.

A preservation guard runs before any write: the delta between the current graph and the merged
graph must touch only the editable surface (a fixed set of predicates/types) and never a blank
node. If anything else would change, the save is refused -- a second line of defence behind the
merge itself, so a projection/merge bug can never silently delete restrictions, imports, or
individuals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from rdflib import Graph, RDF, RDFS, OWL, BNode
from rdflib.namespace import SKOS, DCTERMS

from ..fuseki import FusekiClient
from ..diff import GraphSynchronizer
from .model import Ontology
from .project import project, MAPPING_PREDS

# The only predicates/types a save is ever allowed to add or remove.
SURFACE_PREDS = {
    RDFS.label, SKOS.prefLabel, RDFS.comment, SKOS.definition, DCTERMS.description,
    DCTERMS.title, RDFS.domain, RDFS.range, RDFS.subClassOf, SKOS.broader, SKOS.narrower,
} | set(MAPPING_PREDS.keys())
SURFACE_TYPES = {OWL.Class, SKOS.Concept, OWL.DatatypeProperty, OWL.ObjectProperty}


class PreservationError(RuntimeError):
    """A save was refused because it would change triples outside the editable surface."""

    def __init__(self, violations: list):
        self.violations = violations
        preview = "; ".join(f"{s} {p} {o}" for s, p, o in violations[:5])
        super().__init__(f"save would change {len(violations)} non-editable triple(s): {preview}")


def _on_surface(triple) -> bool:
    s, p, o = triple
    if isinstance(s, BNode) or isinstance(o, BNode):
        return False
    if p == RDF.type:
        return o in SURFACE_TYPES
    return p in SURFACE_PREDS


def guard(base: Graph, merged: Graph) -> list:
    """Triples in the base<->merged delta that fall OUTSIDE the editable surface (empty = safe)."""
    delta = (set(merged) - set(base)) | (set(base) - set(merged))
    return [t for t in delta if not _on_surface(t)]


@dataclass
class SaveResult:
    graph_uri: str
    method: str            # 'incremental' | 'put' | 'incremental+put-fallback' | 'noop'
    added: int
    removed: int
    applied: bool
    verified: Optional[bool]
    base_triples: int
    merged_triples: int
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "graphUri": self.graph_uri, "method": self.method,
            "added": self.added, "removed": self.removed,
            "applied": self.applied, "verified": self.verified,
            "baseTriples": self.base_triples, "mergedTriples": self.merged_triples,
            "dryRun": self.dry_run,
        }


class PlaygroundService:
    """Stateless bridge between Fuseki named graphs and Playground's editable projection."""

    def __init__(self, client: Optional[FusekiClient] = None):
        self.client = client or FusekiClient()

    # -- discovery ----------------------------------------------------------- #

    def list_ontologies(self) -> list[dict[str, Any]]:
        """Named graphs that hold at least one owl:Class or skos:Concept, with node counts."""
        rows = self.client.select("""
            SELECT ?g (SAMPLE(?ont) AS ?ontology) (COUNT(DISTINCT ?n) AS ?nodes) WHERE {
              GRAPH ?g {
                { ?n a owl:Class } UNION { ?n a skos:Concept }
                OPTIONAL { ?ont a owl:Ontology }
              }
            } GROUP BY ?g ORDER BY ?g
        """)
        return [{"graphUri": r["g"], "ontologyIri": r.get("ontology"),
                 "nodeCount": int(r["nodes"])} for r in rows]

    # -- load ---------------------------------------------------------------- #

    def load(self, graph_uri: str) -> dict[str, Any]:
        base = self.client.get_graph(graph_uri)
        return project(base, graph_uri).envelope()

    # -- save ---------------------------------------------------------------- #

    def save(self, graph_uri: str, edited: dict[str, Any] | Ontology,
             dry_run: bool = False) -> SaveResult:
        edited_ont = edited if isinstance(edited, Ontology) else Ontology.from_dict(edited)

        base = self.client.get_graph(graph_uri)           # current, full, untouched
        proj = project(base, graph_uri)
        from .merge import merge                           # local import: avoid cycle at import time
        merged = merge(base, proj, edited_ont)

        violations = guard(base, merged)
        if violations:
            raise PreservationError(violations)

        added = len(set(merged) - set(base))
        removed = len(set(base) - set(merged))

        if added == 0 and removed == 0:
            return SaveResult(graph_uri, "noop", 0, 0, False, True,
                              len(base), len(merged), dry_run)
        if dry_run:
            return SaveResult(graph_uri, "dry-run", added, removed, False, None,
                              len(base), len(merged), dry_run)

        sync = GraphSynchronizer(self.client).sync(graph_uri, merged, old_graph=base)
        return SaveResult(graph_uri, sync.method, added, removed, sync.applied,
                          sync.verified, len(base), len(merged), dry_run)
