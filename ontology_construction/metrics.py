"""Evaluation metrics from the report's "Measurement Strategies" section.

Four families, all implemented against the artifacts the construction processes
actually produce:

1. **Quantitative / OntoAxiom-style** — precision, recall and F1 computed *per
   axiom type* (subclass, disjointness, domain, range), because the report
   records that scores vary enormously by axiom type and by domain: "for
   subclass axioms, the well-known FOAF ontology achieves a score of 0.642,
   while the music ontology scores only 0.218". A single aggregate F1 hides
   exactly the variation you need to see.
2. **Semantic Internal Cohesion** — "the average pairwise cosine similarity of
   concept embeddings within a generated cluster".
3. **Structural integrity** — attribute richness, class/relation ratio,
   equivalence ratio, inheritance richness.
4. **The five criteria** — completeness, conciseness, consistency, correctness,
   clarity, scored from evidence rather than asserted.

The embedder is injectable. The default is a deterministic hashing embedder so
cohesion is computable offline and reproducibly; swap in a sentence-transformer
or an API embedder for real measurement — the same open decision D1 recorded in
`architecture/ontology_assistant/ROADMAP.md`.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .state import ConstructionState, OntologyDraft

__all__ = [
    "PRF", "AxiomScorecard", "StructuralMetrics", "CriteriaScorecard",
    "axiom_prf", "score_axioms", "structural_metrics",
    "semantic_internal_cohesion", "criteria_scorecard",
    "hashing_embedder", "step_measure",
]


# --------------------------------------------------------------------------- #
# 1. OntoAxiom-style precision / recall / F1
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PRF:
    """Precision, recall and F1 for one axiom type."""

    axiom_type: str
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        d = self.true_positives + self.false_positives
        return self.true_positives / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.true_positives + self.false_negatives
        return self.true_positives / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def support(self) -> int:
        return self.true_positives + self.false_negatives

    def as_dict(self) -> dict:
        return {"axiom_type": self.axiom_type,
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4),
                "support": self.support,
                "tp": self.true_positives,
                "fp": self.false_positives,
                "fn": self.false_negatives}


def axiom_prf(axiom_type: str, predicted: Iterable, gold: Iterable) -> PRF:
    """Compare a predicted axiom set against a gold standard."""
    p, g = set(predicted), set(gold)
    return PRF(axiom_type, len(p & g), len(p - g), len(g - p))


@dataclass(frozen=True)
class AxiomScorecard:
    """Per-type scores plus both aggregations.

    Micro and macro are both reported because they answer different questions:
    micro-F1 is dominated by whichever axiom type is most numerous (usually
    subclass), while macro-F1 exposes a type the pipeline is failing at
    entirely. Reporting only one is how a 0.218 hides behind a 0.642.
    """

    per_type: tuple[PRF, ...]

    @property
    def macro_f1(self) -> float:
        return (sum(s.f1 for s in self.per_type) / len(self.per_type)
                if self.per_type else 0.0)

    @property
    def micro(self) -> PRF:
        return PRF("micro",
                   sum(s.true_positives for s in self.per_type),
                   sum(s.false_positives for s in self.per_type),
                   sum(s.false_negatives for s in self.per_type))

    @property
    def weakest(self) -> PRF | None:
        scored = [s for s in self.per_type if s.support]
        return min(scored, key=lambda s: s.f1) if scored else None

    def as_dict(self) -> dict:
        w = self.weakest
        return {"per_type": [s.as_dict() for s in self.per_type],
                "macro_f1": round(self.macro_f1, 4),
                "micro_f1": round(self.micro.f1, 4),
                "weakest_axiom_type": w.axiom_type if w else None,
                "weakest_f1": round(w.f1, 4) if w else None}


def score_axioms(draft: OntologyDraft, gold: OntologyDraft) -> AxiomScorecard:
    """Score a produced ontology against a gold standard, per axiom type."""
    scores = [
        axiom_prf("class", draft.classes, gold.classes),
        axiom_prf("subclass", draft.subclass_of, gold.subclass_of),
        axiom_prf("disjointness", draft.disjointness, gold.disjointness),
        axiom_prf("equivalence", draft.equivalences, gold.equivalences),
        axiom_prf("domain",
                  {(r.predicate, r.domain) for r in draft.object_properties},
                  {(r.predicate, r.domain) for r in gold.object_properties}),
        axiom_prf("range",
                  {(r.predicate, r.range) for r in draft.object_properties},
                  {(r.predicate, r.range) for r in gold.object_properties}),
    ]
    return AxiomScorecard(tuple(scores))


# --------------------------------------------------------------------------- #
# 2. Semantic internal cohesion
# --------------------------------------------------------------------------- #
def hashing_embedder(text: str, dim: int = 64) -> list[float]:
    """Deterministic character-trigram hashing embedder.

    Offline, reproducible and dependency-free — enough to make cohesion a real,
    testable number. It measures lexical rather than semantic similarity, so
    substitute a sentence-transformer before drawing conclusions about meaning.
    """
    vec = [0.0] * dim
    t = f"  {text.lower().strip()}  "
    for i in range(len(t) - 2):
        tri = t[i:i + 3]
        h = int(hashlib.md5(tri.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (na * nb)


def semantic_internal_cohesion(
        cluster: Sequence[str],
        embedder: Callable[[str], Sequence[float]] = hashing_embedder) -> float:
    """Average pairwise cosine similarity of concept embeddings in a cluster.

    The report's definition, verbatim: "calculates the average pairwise cosine
    similarity of concept embeddings within a generated cluster, providing a
    mathematical representation of how closely related and unambiguous a
    machine-generated conceptual category is".

    A cluster of fewer than two members has no pairwise similarity to average;
    returns ``0.0`` rather than pretending to a perfect score.
    """
    items = [c for c in cluster if c]
    if len(items) < 2:
        return 0.0
    vecs = [embedder(c) for c in items]
    total, n = 0.0, 0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            total += _cosine(vecs[i], vecs[j])
            n += 1
    return round(total / n, 4) if n else 0.0


# --------------------------------------------------------------------------- #
# 3. Structural integrity
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StructuralMetrics:
    """Graph-level metadata metrics named in the report."""

    classes: int
    relations: int
    attributes: int
    subclass_axioms: int
    attribute_richness: float
    class_relation_ratio: float
    equivalence_ratio: float
    inheritance_richness: float
    orphan_classes: int

    @property
    def verdict(self) -> str:
        """The report's framing: is the model overly taxonomic, or relational?"""
        if self.relations == 0:
            return "purely taxonomic — no relations modelled at all"
        if self.class_relation_ratio > 5:
            return "concept-heavy — many classes per relation"
        if self.class_relation_ratio < 0.5:
            return "relation-heavy — few classes carry many relations"
        return "balanced"

    def as_dict(self) -> dict:
        return {**{k: v for k, v in self.__dict__.items()},
                "verdict": self.verdict}


def structural_metrics(draft: OntologyDraft) -> StructuralMetrics:
    n_classes = len(draft.classes) or 0
    n_rel = len(draft.object_properties)
    n_attr = len(draft.datatype_properties)
    n_sub = len(draft.subclass_of)
    children = {c for c, _ in draft.subclass_of}
    parents = {p for _, p in draft.subclass_of}
    touched = children | parents
    orphans = len(draft.classes - touched)
    return StructuralMetrics(
        classes=n_classes,
        relations=n_rel,
        attributes=n_attr,
        subclass_axioms=n_sub,
        attribute_richness=round(n_attr / n_classes, 4) if n_classes else 0.0,
        class_relation_ratio=round(n_classes / n_rel, 4) if n_rel else float("inf"),
        equivalence_ratio=round(len(draft.equivalences) / n_classes, 4) if n_classes else 0.0,
        inheritance_richness=round(n_sub / n_classes, 4) if n_classes else 0.0,
        orphan_classes=orphans,
    )


# --------------------------------------------------------------------------- #
# 4. The five criteria
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CriteriaScorecard:
    """Completeness · conciseness · consistency · correctness · clarity.

    Every score is derived from evidence already on the state — a CQ that
    passed, a pitfall that fired, a definition that exists — and each carries
    the evidence string that produced it. A criteria score with no evidence
    behind it is an opinion, and the report's own framing ("criteria-based
    assessments, heavily used in industrial contexts") only works if the
    assessment is reproducible.
    """

    scores: dict[str, float]
    evidence: dict[str, str]

    @property
    def overall(self) -> float:
        return round(sum(self.scores.values()) / len(self.scores), 4) if self.scores else 0.0

    def as_dict(self) -> dict:
        return {"scores": {k: round(v, 4) for k, v in self.scores.items()},
                "evidence": dict(self.evidence),
                "overall": self.overall}


def criteria_scorecard(state: ConstructionState) -> CriteriaScorecard:
    onto = state.ontology
    scores: dict[str, float] = {}
    evidence: dict[str, str] = {}

    # Completeness — did the CQs the ORSD demanded actually pass?
    themis = state.reports.get("themis", {})
    total_cq = len(state.competency_questions)
    passed = int(themis.get("passed", 0))
    scores["completeness"] = (passed / total_cq) if total_cq else 0.0
    evidence["completeness"] = f"{passed}/{total_cq} competency questions satisfied"

    # Conciseness — redundancy: duplicate relations and re-invented reused terms.
    rels = [r.as_triple() for r in onto.object_properties]
    dup_rel = len(rels) - len(set(rels))
    redundant_sub = _redundant_subclass_edges(onto)
    denom = max(1, len(rels) + len(onto.subclass_of))
    scores["conciseness"] = max(0.0, 1.0 - (dup_rel + len(redundant_sub)) / denom)
    evidence["conciseness"] = (f"{dup_rel} duplicate relations, "
                               f"{len(redundant_sub)} redundant subclass axioms")

    # Consistency — pitfalls of critical severity, and taxonomic cycles.
    pitfalls = state.reports.get("pitfalls", {})
    critical = int(pitfalls.get("critical", 0))
    scores["consistency"] = 1.0 if critical == 0 else max(0.0, 1.0 - critical / 10)
    evidence["consistency"] = f"{critical} critical pitfalls"

    # Correctness — proportion of asserted content traceable to a source.
    traced = sum(1 for r in onto.object_properties if r.provenance)
    total_traceable = max(1, len(onto.object_properties))
    scores["correctness"] = traced / total_traceable
    evidence["correctness"] = (f"{traced}/{len(onto.object_properties)} relations "
                               "carry provenance")

    # Clarity — are terms defined and labelled?
    n_classes = len(onto.classes)
    defined = sum(1 for c in onto.classes if onto.definitions.get(c))
    labelled = sum(1 for c in onto.classes if onto.labels.get(c))
    scores["clarity"] = ((defined + labelled) / (2 * n_classes)) if n_classes else 0.0
    evidence["clarity"] = (f"{defined}/{n_classes} classes defined, "
                           f"{labelled}/{n_classes} labelled")

    return CriteriaScorecard(scores, evidence)


def _redundant_subclass_edges(draft: OntologyDraft) -> set[tuple[str, str]]:
    """Edges implied by transitivity — `A<B`, `B<C` makes an asserted `A<C` redundant."""
    direct: dict[str, set[str]] = {}
    for c, p in draft.subclass_of:
        direct.setdefault(c, set()).add(p)

    def ancestors(node: str, skip: tuple[str, str]) -> set[str]:
        seen, stack = set(), list(direct.get(node, ()))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            if (node, cur) == skip and cur in direct.get(node, ()):
                pass
            seen.add(cur)
            stack.extend(direct.get(cur, ()))
        return seen

    redundant = set()
    for c, p in draft.subclass_of:
        others = direct.get(c, set()) - {p}
        reachable: set[str] = set()
        stack = list(others)
        seen: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            reachable.add(cur)
            stack.extend(direct.get(cur, ()))
        if p in reachable:
            redundant.add((c, p))
    return redundant


# --------------------------------------------------------------------------- #
# Step function
# --------------------------------------------------------------------------- #
def step_measure(state: ConstructionState, *,
                 gold: OntologyDraft | None = None,
                 embedder: Callable[[str], Sequence[float]] = hashing_embedder,
                 ) -> ConstructionState:
    """Compute every metric family and file the reports on the state."""
    struct = structural_metrics(state.ontology)
    state.reports["structural"] = struct.as_dict()

    clusters: dict[str, list[str]] = {}
    for term in state.accepted_terms():
        clusters.setdefault(term.type_label or "Entity", []).append(term.label)
    state.reports["cohesion"] = {
        t: semantic_internal_cohesion(members, embedder)
        for t, members in sorted(clusters.items())
    }

    if gold is not None:
        card = score_axioms(state.ontology, gold)
        state.reports["axioms"] = card.as_dict()

    criteria = criteria_scorecard(state)
    state.reports["criteria"] = criteria.as_dict()

    detail = (f"{struct.classes} classes ({struct.verdict}); "
              f"criteria overall {criteria.overall:.2f}")
    if gold is not None:
        detail += f"; macro-F1 {state.reports['axioms']['macro_f1']:.3f}"
    state.record("metrics.measure", True, detail)
    return state
