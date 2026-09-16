"""Ontology extraction with LangExtract — a prototype.

`LangExtract <https://github.com/google/langextract>`_ is a span-grounded
information-extraction library: you give it a prompt, a handful of few-shot
examples, and a document, and it returns structured findings that each carry
the character interval of the source text they came from.

This package uses it for bottom-up ontology development:

    text  ->  grounded extractions  ->  OWL with per-axiom provenance

and wires the result into the existing ``bottomup_ontology`` workflow.

    >>> from langextract_ontology import extract_ontology, to_turtle
    >>> result = extract_ontology("A pump is a device.")   # doctest: +SKIP
    >>> print(to_turtle(result))                           # doctest: +SKIP

Modules
-------
``schema``    what to extract: extraction classes, prompt, few-shot examples.
``providers`` the Claude provider for LangExtract (it ships none).
``extract``   the call, and the grounded result objects.
``owl``       rendering to OWL, annotating every axiom with its source quote.
``pipeline``  drop-in replacements for three ``bottomup_ontology`` steps.
``demo``      a runnable end-to-end example (``python -m langextract_ontology``).

Every extraction is a real model call
-------------------------------------
``model_id`` defaults to ``claude-opus-5`` and needs a credential
(``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``, an ``ant auth login``
profile, or a repo-root ``.env``).  There is no offline stand-in: a missing
credential raises :class:`~langextract_ontology.providers.MissingCredentialError`.
``"gemini-*"``, ``"gpt-*"`` and Ollama tags route to LangExtract's own
providers.
"""

from __future__ import annotations

from .extract import GroundedItem, OntologyExtraction, extract_ontology
from .owl import LXO, provenance_of, to_graph, to_turtle
from .providers import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicLanguageModel,
    MissingCredentialError,
    anthropic_available,
    resolve_model,
)
from .schema import (
    AXIOM,
    CLASS,
    DATA_PROPERTY,
    EXAMPLES,
    EXTRACTION_CLASSES,
    INDIVIDUAL,
    OBJECT_PROPERTY,
    PROMPT_DESCRIPTION,
    SUBSUMPTION,
)

__version__ = "0.1.0"

__all__ = [
    # extraction
    "extract_ontology", "OntologyExtraction", "GroundedItem",
    # rendering
    "to_graph", "to_turtle", "provenance_of", "LXO",
    # models
    "AnthropicLanguageModel", "resolve_model", "anthropic_available",
    "MissingCredentialError", "DEFAULT_ANTHROPIC_MODEL",
    # schema
    "PROMPT_DESCRIPTION", "EXAMPLES", "EXTRACTION_CLASSES",
    "CLASS", "SUBSUMPTION", "OBJECT_PROPERTY", "DATA_PROPERTY",
    "INDIVIDUAL", "AXIOM",
]
