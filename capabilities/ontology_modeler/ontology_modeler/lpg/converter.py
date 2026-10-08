"""LpgConverter -- wire Extraction -> Transformation -> (Embedding) -> Loading.

    # from a live Fuseki dataset
    conv = LpgConverter(client, falkor_settings)
    stats = conv.run(clear=True, embed=True)

    # from RDF files on disk, no triplestore involved
    conv = LpgConverter(extractor=RdfFileExtractor([fibo_dir]), falkor=falkor_settings)
    stats = conv.run(clear=True, embed=True)

The extractor is the only thing that differs between the two. Everything downstream --
the NetworkX IR, the concept profiles, the embeddings, the Cypher -- is shared.
"""

from __future__ import annotations

import logging

from ..config import FalkorSettings
from ..fuseki import FusekiClient
from .extract import TboxExtractor
from .transform import MetaGraphBuilder, concept_profile
from .embed import get_embedder, save_embedder
from .load import FalkorDBExporter

log = logging.getLogger("ontology_modeler.lpg")


class LpgConverter:
    """End-to-end RDF-to-LPG conversion pipeline."""

    def __init__(self, client: FusekiClient | None = None,
                 falkor: FalkorSettings | None = None,
                 extractor=None):
        self.falkor = falkor or FalkorSettings.from_env()
        if extractor is not None:
            self.client = client
            self.extractor = extractor
        else:
            self.client = client or FusekiClient()
            self.extractor = TboxExtractor(self.client)
        self.builder = MetaGraphBuilder()
        self.embedder = None      # set by build_embeddings; see save_embedder

    # -- stages -------------------------------------------------------------- #

    def extract_transform(self) -> dict:
        """Pull from the source and build the NetworkX IR. No FalkorDB needed.

        The optional stages -- modules, restrictions -- are asked for by capability rather
        than by type, so an extractor that cannot supply them still works unchanged.
        """
        self.extractor.ping()

        # Modules first: a DEFINED_IN edge needs both endpoints to exist in the IR.
        if hasattr(self.extractor, "module_records"):
            self.builder.add_modules(self.extractor.module_records())

        classes = self.extractor.classes()
        taxonomy = self.extractor.taxonomy()
        props = self.extractor.object_properties()
        log.info("extracted %d classes, %d subclass, %d object-property rows",
                 len(classes), len(taxonomy), len(props))

        self.builder.add_classes(classes)
        self.builder.add_taxonomy(taxonomy)
        self.builder.add_object_properties(props)

        if hasattr(self.extractor, "restrictions"):
            restrictions = self.extractor.restrictions()
            added = self.builder.add_restrictions(restrictions)
            log.info("unfolded %d restriction(s), %d landed between named classes",
                     len(restrictions), added)
        if hasattr(self.extractor, "defined_in"):
            self.builder.add_defined_in(self.extractor.defined_in())

        stats = self.builder.stats()
        log.info("IR: %d nodes (%d classes, %d external) / %d edges "
                 "(%d subclass, %d property, %d restriction)",
                 stats["nodes"], stats["classes"], stats["external_classes"],
                 stats["edges"], stats["subclass_edges"],
                 stats["object_property_edges"], stats["restriction_edges"])
        return stats

    def profiles(self) -> dict[str, str]:
        """Concept Profile Document per non-external class (spec 5.1).

        External stubs are skipped: they carry an IRI and a derived name and nothing else,
        so their profiles are near-identical and would crowd the vector index.
        """
        return {iri: concept_profile(self.builder, iri)
                for iri, d in self.builder.class_nodes() if not d.get("external")}

    def build_embeddings(self, kind: str = "tfidf") -> dict[str, list[float]]:
        """Generate a concept profile per class and embed it (spec Section 5)."""
        embedder = get_embedder(kind)
        docs = self.profiles()
        if hasattr(embedder, "fit"):
            embedder.fit(list(docs.values()))
        self.embedder = embedder
        log.info("embedding %d concept profiles with %s (dim=%d)",
                 len(docs), type(embedder).__name__, embedder.dim)
        return {iri: embedder.encode(text) for iri, text in docs.items()}

    def save_embedder(self, path=None):
        """Persist the fitted embedder so the retriever can embed queries in the same space."""
        from ..config import embedder_path
        if self.embedder is None:
            raise RuntimeError("no embedder to save; call build_embeddings() first")
        return save_embedder(self.embedder, path or embedder_path(self.falkor.graph_name))

    def load(self, clear: bool = False, embeddings: dict | None = None) -> dict:
        """Ingest the IR (and optional embeddings) into FalkorDB."""
        exporter = FalkorDBExporter(self.falkor)
        exporter.ping()
        if clear:
            log.info("clearing FalkorDB graph '%s'", self.falkor.graph_name)
            exporter.clear()

        nm = exporter.load_modules(self.builder.graph)
        nc = exporter.load_classes(self.builder.graph)
        exporter.create_lookup_indexes()
        nt = exporter.load_taxonomy(self.builder.graph)
        nd = exporter.load_defined_in(self.builder.graph)
        npr = exporter.load_object_properties(self.builder.graph)
        nr = exporter.load_restrictions(self.builder.graph)

        ne = 0
        if embeddings:
            ne = exporter.load_embeddings(embeddings)
            dim = len(next(iter(embeddings.values())))
            created = exporter.create_vector_index(dim)
            log.info("set %d embeddings (dim=%d); vector index %s", ne, dim,
                     "created" if created else "already present")
        fulltext = exporter.create_fulltext_index()
        log.info("full-text index %s", "created" if fulltext else "already present")

        return {"nodes": exporter.count_nodes(), "edges": exporter.count_edges(),
                "modules_merged": nm, "classes_merged": nc, "taxonomy_merged": nt,
                "defined_in_merged": nd, "properties_merged": npr,
                "restrictions_merged": nr, "embeddings_set": ne}

    def run(self, clear: bool = True, embed: bool = False, embedder: str = "tfidf") -> dict:
        """Full pipeline. Returns {'ir': ..., 'loaded': ...}."""
        ir_stats = self.extract_transform()
        embeddings = self.build_embeddings(embedder) if embed else None
        return {"ir": ir_stats, "loaded": self.load(clear=clear, embeddings=embeddings)}
