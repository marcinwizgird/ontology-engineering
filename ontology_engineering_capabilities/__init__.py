"""Ontology Repository Capability Model.

Comprehensive ontology-engineering *requirements* expressed as business and
technology capabilities, arranged as a taxonomy and an ontology, and mapped to
the EKGF EKG Maturity Model.
"""
from __future__ import annotations

from .capability_model import (
    CAPABILITIES,
    CAPABILITY_BY_ID,
    CATEGORIES,
    CATEGORY_BY_ID,
    DOMAINS,
    EKGF_LEVELS,
    EKGF_PILLARS,
    Capability,
    Category,
    capabilities_in,
    categories_in,
    validate_model,
)
from .generators import (
    build_ontology_graph,
    build_taxonomy_graph,
    draw_archimate_png,
    draw_ontology_networkx,
    to_archimate_svg,
    to_mermaid_ontology,
    to_mermaid_taxonomy,
    to_requirements_markdown,
    to_turtle,
)

__version__ = "0.1.0"

__all__ = [
    "CAPABILITIES", "CAPABILITY_BY_ID", "CATEGORIES", "CATEGORY_BY_ID",
    "DOMAINS", "EKGF_LEVELS", "EKGF_PILLARS", "Capability", "Category",
    "capabilities_in", "categories_in", "validate_model",
    "build_taxonomy_graph", "build_ontology_graph", "draw_ontology_networkx",
    "draw_archimate_png", "to_archimate_svg", "to_mermaid_taxonomy",
    "to_mermaid_ontology", "to_turtle", "to_requirements_markdown",
]
