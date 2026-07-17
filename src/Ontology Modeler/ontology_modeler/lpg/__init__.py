"""RDF-to-LPG conversion: replicate the Fuseki TBox into a FalkorDB property graph.

Implements docs/LPG Ontology Coverter/rdf-to-lpg-converter-specification.md with the
Strategy-Pattern boundaries from the companion brief: Extraction (TboxExtractor, over the
shared FusekiClient), Transformation (MetaGraphBuilder -> a NetworkX IR + concept
profiles), Embedding (pluggable Embedder), and Loading (FalkorDBExporter). LpgConverter
wires them together.

The Redis "schema pruning cache" from Section 6 of the spec is intentionally not built.
"""

from .extract import TboxExtractor, ClassRecord, TaxonomyEdge, PropertyEdge
from .transform import MetaGraphBuilder, concept_profile
from .embed import Embedder, HashingEmbedder, SentenceTransformerEmbedder, get_embedder
from .load import FalkorDBExporter
from .converter import LpgConverter

__all__ = [
    "TboxExtractor", "ClassRecord", "TaxonomyEdge", "PropertyEdge",
    "MetaGraphBuilder", "concept_profile",
    "Embedder", "HashingEmbedder", "SentenceTransformerEmbedder", "get_embedder",
    "FalkorDBExporter", "LpgConverter",
]
