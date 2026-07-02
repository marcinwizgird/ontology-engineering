"""Data carriers for the bottom-up ontology development workflow.

The workflow described in Keet, *Ontology Repository* (2nd ed.), Chapter 7,
Figure 7.7 ("Overview of the component tasks in the pipeline from text to
candidate classes, object properties, and basic constraints for an ontology")
turns an *unstructured text* corpus into an *ontology*.  Every step in that
pipeline reads from and writes to a single, shared :class:`WorkflowState`
object, and the final artifact is an :class:`Ontology`.

Keeping all intermediate artifacts on one state object means each step is a
pure ``state -> state`` function, which is exactly the shape needed to expose
the steps as *function tools* in an agentic system (see ``tools.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --------------------------------------------------------------------------- #
# Linguistic / intermediate artifacts
# --------------------------------------------------------------------------- #
@dataclass
class Token:
    """A single token after the *text cleaning* step (Fig. 7.7).

    Carries the surface form, its lemma (lemmatisation) and a coarse
    part-of-speech tag (PoS tagging).  ``doc_id``/``sent_id`` let later steps
    reason about co-occurrence inside a sentence.
    """

    surface: str
    lemma: str
    pos: str  # coarse PoS: NOUN, PROPN, VERB, ADJ, DET, ADP, OTHER
    doc_id: int = 0
    sent_id: int = 0


@dataclass
class CandidateTerm:
    """A multi-word or single-word term proposed as a candidate class."""

    term: str
    frequency: int = 0
    score: float = 0.0  # ranking score (e.g. C/NC-value style)
    accepted: bool = True  # may be toggled by the human-in-the-loop step


@dataclass
class Relation:
    """A candidate object property: ``subject --predicate--> object``."""

    subject: str
    predicate: str
    object: str
    support: int = 1
    accepted: bool = True

    def as_triple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


# --------------------------------------------------------------------------- #
# The ontology artifact (the workflow output)
# --------------------------------------------------------------------------- #
@dataclass
class Ontology:
    """A lightweight ontology artifact produced by the pipeline.

    This is deliberately notation-agnostic; ``to_turtle`` renders a minimal
    OWL/RDF serialisation without requiring ``rdflib`` so the package stays
    dependency-light.
    """

    iri: str = "http://example.org/onto#"
    classes: set[str] = field(default_factory=set)
    subclass_of: set[tuple[str, str]] = field(default_factory=set)  # (sub, super)
    object_properties: list[Relation] = field(default_factory=list)
    axioms: list[str] = field(default_factory=list)  # human-readable DL/NL axioms

    # -- mutation helpers ---------------------------------------------------- #
    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def add_subclass(self, sub: str, sup: str) -> None:
        self.classes.add(sub)
        self.classes.add(sup)
        self.subclass_of.add((sub, sup))

    def add_object_property(self, rel: Relation) -> None:
        self.classes.add(rel.subject)
        self.classes.add(rel.object)
        self.object_properties.append(rel)

    # -- serialisation ------------------------------------------------------- #
    @staticmethod
    def _ident(label: str) -> str:
        """Turn a natural-language label into a CamelCase OWL identifier."""
        parts = [p for p in label.replace("-", " ").split() if p]
        return "".join(p[:1].upper() + p[1:] for p in parts) or "Thing"

    @staticmethod
    def _prop_ident(label: str) -> str:
        parts = [p for p in label.replace("-", " ").split() if p]
        if not parts:
            return "relatedTo"
        head = parts[0].lower()
        tail = "".join(p[:1].upper() + p[1:] for p in parts[1:])
        return head + tail

    def to_turtle(self) -> str:
        """Render a minimal Turtle/OWL serialisation of the ontology."""
        lines = [
            "@prefix : <%s> ." % self.iri,
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "",
        ]
        for cls in sorted(self.classes):
            cid = self._ident(cls)
            lines.append(f':{cid} a owl:Class ; rdfs:label "{cls}" .')
        if self.subclass_of:
            lines.append("")
        for sub, sup in sorted(self.subclass_of):
            lines.append(f":{self._ident(sub)} rdfs:subClassOf :{self._ident(sup)} .")
        if self.object_properties:
            lines.append("")
        seen_props: set[str] = set()
        for rel in self.object_properties:
            pid = self._prop_ident(rel.predicate)
            if pid not in seen_props:
                lines.append(
                    f":{pid} a owl:ObjectProperty ; "
                    f"rdfs:domain :{self._ident(rel.subject)} ; "
                    f"rdfs:range :{self._ident(rel.object)} ."
                )
                seen_props.add(pid)
        return "\n".join(lines) + "\n"

    def summary(self) -> dict[str, int]:
        return {
            "classes": len(self.classes),
            "subclass_axioms": len(self.subclass_of),
            "object_properties": len(self.object_properties),
            "other_axioms": len(self.axioms),
        }


# --------------------------------------------------------------------------- #
# Shared workflow state
# --------------------------------------------------------------------------- #
@dataclass
class WorkflowState:
    """Mutable context threaded through every workflow step.

    Each pipeline step consumes some fields and populates others, so the order
    imposed by the workflow graph (``workflow.py``) matters.
    """

    # --- inputs ---
    documents: list[str] = field(default_factory=list)  # the unstructured corpus
    background_corpus: list[str] = field(default_factory=list)  # for contrastive analysis
    gold_classes: set[str] = field(default_factory=set)  # for gold-standard evaluation
    gold_relations: set[tuple[str, str, str]] = field(default_factory=set)
    # An optional human approver callback used by the human-in-the-loop step.
    # Signature: (kind, item_label) -> bool  (True == keep the candidate).
    human_approver: Optional[Callable[[str, str], bool]] = None

    # --- intermediate artifacts (filled by steps) ---
    tokens: list[Token] = field(default_factory=list)
    term_scores: dict[str, float] = field(default_factory=dict)
    cooccurrence: dict[tuple[str, str], int] = field(default_factory=dict)
    candidate_terms: list[CandidateTerm] = field(default_factory=list)
    candidate_relations: list[Relation] = field(default_factory=list)

    # --- output ---
    ontology: Ontology = field(default_factory=Ontology)
    evaluation: dict[str, Any] = field(default_factory=dict)

    # --- bookkeeping ---
    config: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        """Append a human-readable trace entry (handy in the notebooks)."""
        self.log.append(message)

    def accepted_terms(self) -> list[CandidateTerm]:
        return [t for t in self.candidate_terms if t.accepted]

    def accepted_relations(self) -> list[Relation]:
        return [r for r in self.candidate_relations if r.accepted]
