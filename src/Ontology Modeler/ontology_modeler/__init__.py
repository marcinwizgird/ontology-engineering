"""Ontology Modeler -- a single component for managing an ontology across Fuseki and FalkorDB.

Everything composes over one shared FusekiClient:

    from ontology_modeler import OntologyModeler
    om = OntologyModeler()                          # settings from infra/*/.env

    om.uploader.upload_paths(["Ontology Repository/FIBO/fibo"], clear=True)   # load RDF
    om.structure.classes(ontology=IRI)                                        # explore
    om.sync.sync(graph_uri, new_graph)                                        # incremental update
    om.lpg_converter().run(clear=True, embed=True)                            # replicate to FalkorDB

Or use any piece directly with your own FusekiClient:

    client = FusekiClient(FusekiSettings.from_env())
    StructureExplorer(client).list_ontologies()

Modules: config (settings), rdf (files + IRI naming), fuseki (the client), upload, diff,
structure, lpg (the RDF-to-LPG subpackage).
"""

from __future__ import annotations

from .config import FusekiSettings, FalkorSettings, REPO_ROOT
from .fuseki import FusekiClient, FusekiError
from .rdf import CONTENT_TYPES, graph_uri, iter_rdf_files, content_type_for, local_name, short_name, rel_type_of
from .upload import Uploader, AsyncUploader, UploadResult
from .diff import OntologyDiffer, GraphSynchronizer, UpdatePlan, SyncResult
from .structure import StructureExplorer
from .lpg import (
    TboxExtractor, MetaGraphBuilder, concept_profile,
    Embedder, HashingEmbedder, SentenceTransformerEmbedder, get_embedder,
    FalkorDBExporter, LpgConverter,
)

__all__ = [
    "OntologyModeler",
    # config / client
    "FusekiSettings", "FalkorSettings", "REPO_ROOT", "FusekiClient", "FusekiError",
    # rdf helpers
    "CONTENT_TYPES", "graph_uri", "iter_rdf_files", "content_type_for",
    "local_name", "short_name", "rel_type_of",
    # upload
    "Uploader", "AsyncUploader", "UploadResult",
    # diff
    "OntologyDiffer", "GraphSynchronizer", "UpdatePlan", "SyncResult",
    # structure
    "StructureExplorer",
    # lpg
    "TboxExtractor", "MetaGraphBuilder", "concept_profile",
    "Embedder", "HashingEmbedder", "SentenceTransformerEmbedder", "get_embedder",
    "FalkorDBExporter", "LpgConverter",
]


class OntologyModeler:
    """Facade wiring every capability over one shared FusekiClient.

    Args:
        fuseki: a FusekiClient, a FusekiSettings, or None (settings from .env).
        falkor: a FalkorSettings, or None (settings from .env).
    """

    def __init__(self, fuseki: "FusekiClient | FusekiSettings | None" = None,
                 falkor: "FalkorSettings | None" = None):
        self.fuseki = fuseki if isinstance(fuseki, FusekiClient) else FusekiClient(fuseki)
        self.falkor = falkor or FalkorSettings.from_env()

        self.uploader = Uploader(self.fuseki)
        self.async_uploader = AsyncUploader(self.fuseki)
        self.sync = GraphSynchronizer(self.fuseki)
        self.structure = StructureExplorer(self.fuseki)

    def lpg_converter(self) -> LpgConverter:
        """A fresh RDF-to-LPG converter sharing this component's connections."""
        return LpgConverter(self.fuseki, self.falkor)

    def is_up(self) -> bool:
        return self.fuseki.is_up()
