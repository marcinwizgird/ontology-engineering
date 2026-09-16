"""Shared state and artifacts for the ontology-construction processes.

Implements the artifact vocabulary of *"Strategic Ontology Engineering in the
Era of Generative AI"* (`docs/Ontology Definition/Ontology Construction
Approaches and Metrics.pdf`) — the ORSD, competency questions, candidate terms,
taxonomy and non-taxonomic edges, and the reports produced by validation.

Following the convention established by :mod:`bottomup_ontology`, every process
step is a pure ``state -> state`` function over a single shared state object, so
each one is independently testable, usable as a ``networkx`` node, and callable
as an agentic function tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

__all__ = [
    "Requirement", "CompetencyQuestion", "CandidateTerm", "TaxonomyEdge",
    "RelationEdge", "AttributeEdge", "OntologyDraft", "StageRecord",
    "ConstructionState",
]


# --------------------------------------------------------------------------- #
# Requirements-level artifacts (NeOn "ORSD", LOT sprint 1)
# --------------------------------------------------------------------------- #
@dataclass
class Requirement:
    """One entry of the Ontology Requirements Specification Document."""

    id: str
    text: str
    kind: str = "functional"          # functional | non-functional
    priority: str = "SHOULD"          # MUST | SHOULD | MAY
    source: str = ""                  # use case, stakeholder, regulation


@dataclass
class CompetencyQuestion:
    """A CQ — the unit LOT specifies against and Themis tests against.

    ``pattern`` records which lexico-syntactic pattern classified the question;
    ``sparql`` is the executable form Themis-style validation runs.
    """

    id: str
    text: str
    pattern: str = ""
    sparql: str = ""
    expects: str = "non-empty"        # non-empty | empty | boolean
    requirement_id: str = ""

    @property
    def is_formalised(self) -> bool:
        return bool(self.sparql)


# --------------------------------------------------------------------------- #
# Ontology-learning artifacts (LLMs4OL subtasks)
# --------------------------------------------------------------------------- #
@dataclass
class CandidateTerm:
    """A term with its induced semantic type (LLMs4OL task A: term typing)."""

    label: str
    type_label: str = ""
    score: float = 0.0
    provenance: str = ""
    accepted: bool = True


@dataclass
class TaxonomyEdge:
    """`child rdfs:subClassOf parent` (LLMs4OL task B: taxonomy discovery)."""

    child: str
    parent: str
    score: float = 0.0
    provenance: str = ""
    accepted: bool = True

    def as_pair(self) -> tuple[str, str]:
        return (self.child, self.parent)


@dataclass
class RelationEdge:
    """A non-taxonomic relation (LLMs4OL task C)."""

    domain: str
    predicate: str
    range: str
    score: float = 0.0
    provenance: str = ""
    accepted: bool = True

    def as_triple(self) -> tuple[str, str, str]:
        return (self.domain, self.predicate, self.range)


@dataclass
class AttributeEdge:
    """A datatype property — counted by the attribute-richness metric."""

    domain: str
    predicate: str
    datatype: str = "xsd:string"
    provenance: str = ""


# --------------------------------------------------------------------------- #
# The ontology under construction
# --------------------------------------------------------------------------- #
@dataclass
class OntologyDraft:
    """The evolving ontology. Notation-agnostic; renders to Turtle on demand."""

    iri: str = "http://example.org/onto#"
    prefix: str = "ex"
    classes: set[str] = field(default_factory=set)
    subclass_of: set[tuple[str, str]] = field(default_factory=set)
    object_properties: list[RelationEdge] = field(default_factory=list)
    datatype_properties: list[AttributeEdge] = field(default_factory=list)
    equivalences: set[tuple[str, str]] = field(default_factory=set)
    disjointness: set[tuple[str, str]] = field(default_factory=set)
    labels: dict[str, dict[str, str]] = field(default_factory=dict)   # term -> lang -> label
    definitions: dict[str, str] = field(default_factory=dict)
    imports: list[str] = field(default_factory=list)
    license: str = ""
    #: Terms deliberately reused from an external ontology: term -> source IRI.
    reused: dict[str, str] = field(default_factory=dict)

    # -- helpers ------------------------------------------------------------ #
    def add_class(self, name: str, *, label: str | None = None,
                  lang: str = "en", definition: str | None = None) -> None:
        self.classes.add(name)
        if label:
            self.labels.setdefault(name, {})[lang] = label
        if definition:
            self.definitions[name] = definition

    def add_subclass(self, child: str, parent: str) -> None:
        self.classes.add(child)
        self.classes.add(parent)
        self.subclass_of.add((child, parent))

    def local_name(self, term: str) -> str:
        return "".join(p[:1].upper() + p[1:] for p in term.replace("_", " ").split())

    def property_name(self, predicate: str) -> str:
        parts = predicate.replace("_", " ").split()
        if not parts:
            return "relatedTo"
        return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])

    @property
    def relation_count(self) -> int:
        return len(self.object_properties)

    def summary(self) -> str:
        return (f"{len(self.classes)} classes, {len(self.subclass_of)} subclass axioms, "
                f"{len(self.object_properties)} object properties, "
                f"{len(self.datatype_properties)} datatype properties")

    # -- serialisation ------------------------------------------------------ #
    def to_turtle(self) -> str:
        """Minimal Turtle. Kept dependency-free so the draft is inspectable
        before ``rdflib`` is involved (see :func:`to_rdflib`)."""
        lines = [
            f"@prefix {self.prefix}: <{self.iri}> .",
            "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
            "@prefix dcterms: <http://purl.org/dc/terms/> .",
            "",
            f"<{self.iri.rstrip('#/')}> a owl:Ontology ;",
        ]
        tail = []
        for imp in self.imports:
            tail.append(f"    owl:imports <{imp}> ;")
        if self.license:
            tail.append(f'    dcterms:license "{self.license}" ;')
        if tail:
            lines.extend(tail)
            lines[-1] = lines[-1].rstrip(" ;") + " ."
        else:
            lines[-1] = lines[-1].rstrip(" ;") + " ."
        lines.append("")

        for cls in sorted(self.classes):
            ln = self.local_name(cls)
            body = [f"{self.prefix}:{ln} a owl:Class"]
            for lang, lab in sorted(self.labels.get(cls, {}).items()):
                body.append(f'    rdfs:label "{lab}"@{lang}')
            if cls in self.definitions:
                d = self.definitions[cls].replace('"', "'")
                body.append(f'    skos:definition "{d}"@en')
            for child, parent in sorted(self.subclass_of):
                if child == cls:
                    body.append(f"    rdfs:subClassOf {self.prefix}:{self.local_name(parent)}")
            for a, b in sorted(self.equivalences):
                if a == cls:
                    body.append(f"    owl:equivalentClass {self.prefix}:{self.local_name(b)}")
            for a, b in sorted(self.disjointness):
                if a == cls:
                    body.append(f"    owl:disjointWith {self.prefix}:{self.local_name(b)}")
            lines.append(" ;\n".join(body) + " .")
            lines.append("")

        seen: set[str] = set()
        for rel in self.object_properties:
            pn = self.property_name(rel.predicate)
            if pn in seen:
                continue
            seen.add(pn)
            lines.append(
                f"{self.prefix}:{pn} a owl:ObjectProperty ;\n"
                f"    rdfs:domain {self.prefix}:{self.local_name(rel.domain)} ;\n"
                f"    rdfs:range {self.prefix}:{self.local_name(rel.range)} .")
            lines.append("")

        seen.clear()
        for att in self.datatype_properties:
            pn = self.property_name(att.predicate)
            if pn in seen:
                continue
            seen.add(pn)
            lines.append(
                f"{self.prefix}:{pn} a owl:DatatypeProperty ;\n"
                f"    rdfs:domain {self.prefix}:{self.local_name(att.domain)} ;\n"
                f"    rdfs:range {att.datatype} .")
            lines.append("")
        return "\n".join(lines)

    def to_rdflib(self):
        """Parse :meth:`to_turtle` into an ``rdflib.Graph`` for validation."""
        from rdflib import Graph
        g = Graph()
        g.parse(data=self.to_turtle(), format="turtle")
        return g


# --------------------------------------------------------------------------- #
# Process bookkeeping
# --------------------------------------------------------------------------- #
@dataclass
class StageRecord:
    """One stage of a pipeline run — the audit trail NeOn-GPT depends on.

    The document's central practical claim is that LLM output must pass a
    deterministic gate before the next stage runs. Recording *what the gate
    decided* is what makes the claim checkable after the fact.
    """

    stage: str
    ok: bool
    detail: str = ""
    gate: str = ""
    repaired: int = 0
    rejected: int = 0

    def __str__(self) -> str:  # pragma: no cover - display only
        flag = "ok " if self.ok else "FAIL"
        extra = f" gate={self.gate}" if self.gate else ""
        return f"[{flag}] {self.stage}{extra}: {self.detail}"


@dataclass
class ConstructionState:
    """The shared context every construction step reads and writes."""

    # -- inputs ------------------------------------------------------------- #
    domain: str = ""
    purpose: str = ""
    scope: str = ""
    intended_users: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    #: Non-ontological resources available for re-engineering (NeOn scenario 2).
    non_ontological_resources: list[str] = field(default_factory=list)
    #: Existing ontologies available for reuse (NeOn scenarios 3–6).
    ontological_resources: list[str] = field(default_factory=list)
    #: Ontology design patterns available (NeOn scenario 7).
    design_patterns: list[str] = field(default_factory=list)
    #: Target languages for localisation (NeOn scenario 9).
    target_languages: list[str] = field(default_factory=list)

    # -- requirements ------------------------------------------------------- #
    requirements: list[Requirement] = field(default_factory=list)
    competency_questions: list[CompetencyQuestion] = field(default_factory=list)

    # -- learning artifacts ------------------------------------------------- #
    candidate_terms: list[CandidateTerm] = field(default_factory=list)
    taxonomy_edges: list[TaxonomyEdge] = field(default_factory=list)
    relation_edges: list[RelationEdge] = field(default_factory=list)

    # -- output ------------------------------------------------------------- #
    ontology: OntologyDraft = field(default_factory=OntologyDraft)

    # -- process record ----------------------------------------------------- #
    scenarios: list[str] = field(default_factory=list)
    stages: list[StageRecord] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    reports: dict[str, Any] = field(default_factory=dict)

    # -- helpers ------------------------------------------------------------ #
    def note(self, message: str) -> None:
        self.log.append(message)

    def record(self, stage: str, ok: bool, detail: str = "", *,
               gate: str = "", repaired: int = 0, rejected: int = 0) -> StageRecord:
        rec = StageRecord(stage, ok, detail, gate, repaired, rejected)
        self.stages.append(rec)
        self.log.append(str(rec))
        return rec

    def accepted_terms(self) -> list[CandidateTerm]:
        return [t for t in self.candidate_terms if t.accepted]

    def accepted_taxonomy(self) -> list[TaxonomyEdge]:
        return [e for e in self.taxonomy_edges if e.accepted]

    def accepted_relations(self) -> list[RelationEdge]:
        return [r for r in self.relation_edges if r.accepted]

    def cq(self, cq_id: str) -> Optional[CompetencyQuestion]:
        return next((c for c in self.competency_questions if c.id == cq_id), None)

    @property
    def failed_stages(self) -> list[StageRecord]:
        return [s for s in self.stages if not s.ok]

    def summary(self) -> str:
        return (f"domain={self.domain!r} | {len(self.requirements)} requirements, "
                f"{len(self.competency_questions)} CQs "
                f"({sum(c.is_formalised for c in self.competency_questions)} formalised) | "
                f"{self.ontology.summary()} | "
                f"{len(self.stages)} stages, {len(self.failed_stages)} failed")
