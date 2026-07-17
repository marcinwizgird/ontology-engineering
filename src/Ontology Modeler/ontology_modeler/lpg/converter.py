"""LpgConverter -- wire Extraction -> Transformation -> (Embedding) -> Loading.

    conv = LpgConverter(client, falkor_settings)
    stats = conv.run(clear=True, embed=True)
"""

from __future__ import annotations

import logging

from ..config import FalkorSettings
from ..fuseki import FusekiClient
from .extract import TboxExtractor
from .transform import MetaGraphBuilder, concept_profile
from .embed import get_embedder
from .load import FalkorDBExporter

log = logging.getLogger("ontology_modeler.lpg")


class LpgConverter:
    """End-to-end RDF-to-LPG conversion pipeline."""

    def __init__(self, client: FusekiClient | None = None,
                 falkor: FalkorSettings | None = None):
        self.client = client or FusekiClient()
        self.falkor = falkor or FalkorSettings.from_env()
        self.extractor = TboxExtractor(self.client)
        self.builder = MetaGraphBuilder()

    # -- stages -------------------------------------------------------------- #

    def extract_transform(self) -> dict:
        """Pull from Fuseki and build the NetworkX IR. No FalkorDB needed."""
        self.extractor.ping()
        classes = self.extractor.classes()
        taxonomy = self.extractor.taxonomy()
        props = self.extractor.object_properties()
        log.info("extracted %d classes, %d subclass, %d object-property rows",
                 len(classes), len(taxonomy), len(props))

        self.builder.add_classes(classes)
        self.builder.add_taxonomy(taxonomy)
        self.builder.add_object_properties(props)
        stats = self.builder.stats()
        log.info("IR: %d nodes, %d subclass + %d property edges",
                 stats["nodes"], stats["subclass_edges"], stats["object_property_edges"])
        return stats

    def build_embeddings(self, kind: str = "hash") -> dict[str, list[float]]:
        """Generate a concept profile per class and embed it (spec Section 5)."""
        embedder = get_embedder(kind)
        log.info("embedding %d concept profiles with %s (dim=%d)",
                 self.builder.graph.number_of_nodes(), type(embedder).__name__, embedder.dim)
        return {iri: embedder.encode(concept_profile(self.builder, iri))
                for iri, d in self.builder.graph.nodes(data=True) if d.get("label") == "Class"}

    def load(self, clear: bool = False, embeddings: dict | None = None) -> dict:
        """Ingest the IR (and optional embeddings) into FalkorDB."""
        exporter = FalkorDBExporter(self.falkor)
        exporter.ping()
        if clear:
            log.info("clearing FalkorDB graph '%s'", self.falkor.graph_name)
            exporter.clear()
        nc = exporter.load_classes(self.builder.graph)
        nt = exporter.load_taxonomy(self.builder.graph)
        npr = exporter.load_object_properties(self.builder.graph)
        ne = 0
        if embeddings:
            ne = exporter.load_embeddings(embeddings)
            created = exporter.create_vector_index(len(next(iter(embeddings.values()))))
            log.info("set %d embeddings; vector index %s", ne,
                     "created" if created else "already present")
        return {"nodes": exporter.count_nodes(), "edges": exporter.count_edges(),
                "classes_merged": nc, "taxonomy_merged": nt,
                "properties_merged": npr, "embeddings_set": ne}

    def run(self, clear: bool = True, embed: bool = False, embedder: str = "hash") -> dict:
        """Full pipeline. Returns {'ir': ..., 'loaded': ...}."""
        ir_stats = self.extract_transform()
        embeddings = self.build_embeddings(embedder) if embed else None
        return {"ir": ir_stats, "loaded": self.load(clear=clear, embeddings=embeddings)}
