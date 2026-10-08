"""Run the extraction and hold the grounded result.

The value LangExtract adds over "ask an LLM for some Turtle" is that every
finding keeps a character interval into the source document.  This module
preserves that: :class:`GroundedItem` is one extraction plus its span, and
:class:`OntologyExtraction` is the whole document's worth of them, which
:mod:`langextract_ontology.owl` turns into OWL where each axiom is annotated
with the sentence that justifies it.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Any, Iterable

import langextract as lx

from . import providers, schema as S


# --------------------------------------------------------------------------- #
# Grounded artifacts
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class GroundedItem:
    """One extraction, with the span of source text that licensed it."""

    kind: str  # one of schema.EXTRACTION_CLASSES
    quote: str  # the verbatim source text
    attributes: dict[str, str]
    start: int | None = None  # character offsets into the source document
    end: int | None = None
    alignment: str = "unknown"  # match_exact / match_fuzzy / match_greater / ...

    @property
    def grounded(self) -> bool:
        """True when the quote was aligned back to a span in the document."""
        return self.start is not None and self.end is not None

    def attr(self, key: str, default: str = "") -> str:
        value = self.attributes.get(key, default)
        if isinstance(value, list):  # LangExtract allows list-valued attributes
            return ", ".join(str(v) for v in value)
        return str(value) if value is not None else default

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "quote": self.quote,
            "attributes": dict(self.attributes),
            "start": self.start,
            "end": self.end,
            "alignment": self.alignment,
        }


@dataclasses.dataclass
class OntologyExtraction:
    """Everything LangExtract found in one document."""

    document_id: str
    source_text: str
    items: list[GroundedItem] = dataclasses.field(default_factory=list)
    model_name: str = "unknown"
    #: Token usage of the run that produced this, when the provider reports it.
    usage: dict[str, int] = dataclasses.field(default_factory=dict)

    # -- views by extraction class ------------------------------------------ #
    def of(self, kind: str) -> list[GroundedItem]:
        return [i for i in self.items if i.kind == kind]

    def classes(self) -> list[GroundedItem]:
        return self.of(S.CLASS)

    def subsumptions(self) -> list[GroundedItem]:
        return self.of(S.SUBSUMPTION)

    def object_properties(self) -> list[GroundedItem]:
        return self.of(S.OBJECT_PROPERTY)

    def data_properties(self) -> list[GroundedItem]:
        return self.of(S.DATA_PROPERTY)

    def individuals(self) -> list[GroundedItem]:
        return self.of(S.INDIVIDUAL)

    def axioms(self) -> list[GroundedItem]:
        return self.of(S.AXIOM)

    # -- derived vocabulary -------------------------------------------------- #
    def class_labels(self) -> list[str]:
        """Every class label mentioned anywhere, including as a domain/range.

        A class the model only named as the range of a relation is still a
        class; collecting them here is what keeps the OWL output closed.
        """
        labels: dict[str, None] = {}

        def add(label: str) -> None:
            label = label.strip().lower()
            if label:
                labels.setdefault(label, None)

        for item in self.items:
            if item.kind == S.CLASS:
                add(item.attr("label") or item.quote)
            elif item.kind == S.SUBSUMPTION:
                add(item.attr("subclass"))
                add(item.attr("superclass"))
            elif item.kind in (S.OBJECT_PROPERTY, S.DATA_PROPERTY):
                add(item.attr("domain"))
                if item.kind == S.OBJECT_PROPERTY:
                    add(item.attr("range"))
            elif item.kind == S.INDIVIDUAL:
                add(item.attr("type"))
            elif item.kind == S.AXIOM:
                add(item.attr("subject"))
                add(item.attr("filler"))
        return sorted(labels)

    # -- reporting ----------------------------------------------------------- #
    def summary(self) -> dict[str, Any]:
        grounded = sum(1 for i in self.items if i.grounded)
        exact = sum(1 for i in self.items if i.alignment == "match_exact")
        return {
            "model": self.model_name,
            "extractions": len(self.items),
            "grounded": grounded,
            "grounded_ratio": round(grounded / len(self.items), 3) if self.items else 0.0,
            "exact_spans": exact,
            "classes": len(self.class_labels()),
            "subsumptions": len(self.subsumptions()),
            "object_properties": len(self.object_properties()),
            "data_properties": len(self.data_properties()),
            "individuals": len(self.individuals()),
            "axioms": len(self.axioms()),
        }

    def provenance_table(self) -> list[dict[str, Any]]:
        """Flat rows of ``what was asserted`` vs ``what the text said``."""
        rows = []
        for item in self.items:
            rows.append(
                {
                    "kind": item.kind,
                    "assertion": _assertion_of(item),
                    "quote": item.quote,
                    "span": f"{item.start}-{item.end}" if item.grounded else "-",
                    "alignment": item.alignment,
                }
            )
        return rows

    def to_json(self, path: str | pathlib.Path | None = None) -> str:
        payload = {
            "document_id": self.document_id,
            "model": self.model_name,
            "usage": self.usage,
            "summary": self.summary(),
            "items": [i.as_dict() for i in self.items],
        }
        text = json.dumps(payload, indent=2)
        if path is not None:
            pathlib.Path(path).write_text(text, encoding="utf-8")
        return text


def _assertion_of(item: GroundedItem) -> str:
    """A one-line, human-readable rendering of what the extraction asserts."""
    if item.kind == S.CLASS:
        return f"Class({item.attr('label') or item.quote})"
    if item.kind == S.SUBSUMPTION:
        return f"{item.attr('subclass')} SubClassOf {item.attr('superclass')}"
    if item.kind == S.OBJECT_PROPERTY:
        return f"{item.attr('property')}: {item.attr('domain')} -> {item.attr('range')}"
    if item.kind == S.DATA_PROPERTY:
        return f"{item.attr('property')}: {item.attr('domain')} -> {item.attr('datatype')}"
    if item.kind == S.INDIVIDUAL:
        return f"{item.attr('label')} : {item.attr('type')}"
    if item.kind == S.AXIOM:
        return item.attr("expression") or f"{item.attr('axiom_type')}({item.attr('subject')})"
    return item.quote


# --------------------------------------------------------------------------- #
# The extraction call
# --------------------------------------------------------------------------- #
def extract_ontology(
    text: str,
    *,
    model_id: str | None = None,
    model: Any = None,
    document_id: str = "doc-1",
    max_char_buffer: int = 1200,
    extraction_passes: int = 1,
    max_workers: int = 4,
    additional_context: str | None = None,
    model_kwargs: dict[str, Any] | None = None,
    **extract_kwargs: Any,
) -> OntologyExtraction:
    """Extract grounded ontology commitments from ``text``.

    Parameters
    ----------
    model_id:
        ``None``/``"auto"``/``"claude-*"`` uses the Anthropic provider in
        ``providers.py`` (default ``claude-opus-5``); any other id
        (``gemini-*``, ``gpt-*``, an Ollama tag) is handed to LangExtract's own
        provider registry.  A missing credential raises rather than degrading
        to anything that is not a real model.
    model:
        A ready-made LangExtract model instance, bypassing ``model_id``.
    extraction_passes:
        More than one pass re-runs the extraction and merges the findings —
        LangExtract's recall lever for long documents.  Costs one full pass
        per increment.
    additional_context:
        Domain notes prepended to every chunk's prompt, e.g. a competency
        question or an upper-ontology commitment to respect.
    """
    if model is None:
        model = providers.resolve_model(model_id, **(model_kwargs or {}))

    call: dict[str, Any] = {
        "text_or_documents": text,
        "prompt_description": S.PROMPT_DESCRIPTION,
        "examples": S.EXAMPLES,
        "max_char_buffer": max_char_buffer,
        "extraction_passes": extraction_passes,
        "max_workers": max_workers,
        "additional_context": additional_context,
        "show_progress": False,
    }
    if model is not None:
        # A caller-supplied model is already configured; asking LangExtract to
        # also apply schema constraints just raises a warning.
        call["model"] = model
        call["use_schema_constraints"] = False
        model_name = getattr(model, "model_id", None) or getattr(
            model, "name", type(model).__name__
        )
    else:
        call["model_id"] = model_id
        model_name = str(model_id)
    call.update(extract_kwargs)

    annotated = lx.extract(**call)
    if isinstance(annotated, list):  # only when passed several Documents
        annotated = annotated[0]

    return OntologyExtraction(
        document_id=document_id,
        source_text=text,
        items=list(_to_items(annotated.extractions or [])),
        model_name=model_name,
        usage=dict(getattr(model, "usage", {}) or {}),
    )


def _to_items(extractions: Iterable[Any]) -> Iterable[GroundedItem]:
    for e in extractions:
        if e.extraction_class not in S.EXTRACTION_CLASSES:
            continue  # a model may invent a class; ignore what we cannot render
        interval = e.char_interval
        status = e.alignment_status
        yield GroundedItem(
            kind=e.extraction_class,
            quote=e.extraction_text,
            attributes=dict(e.attributes or {}),
            start=getattr(interval, "start_pos", None) if interval else None,
            end=getattr(interval, "end_pos", None) if interval else None,
            alignment=getattr(status, "value", str(status)) if status else "unaligned",
        )
