"""The NeOn methodology — nine scenarios for building ontology *networks*.

From the source report: NeOn "aims at building ontology networks rather than
isolated models", with a scenario-based architecture supporting reuse,
collaborative development and dynamic evolution. The defining characteristic is
its emphasis on *integration and reuse*, decomposing network development into
solvable subproblems.

This module models the nine scenarios as data — each declaring the inputs it
needs and the artifacts it produces — plus a selector that reads the available
resources off the state and reports which scenarios actually apply. That
selector is the useful part: NeOn's own guidance is "pick the scenarios your
starting conditions justify", and getting that wrong is the most common way a
NeOn-branded project ends up doing scenario 1 by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .state import (
    CandidateTerm,
    CompetencyQuestion,
    ConstructionState,
    Requirement,
    TaxonomyEdge,
)

__all__ = ["NeOnScenario", "SCENARIOS", "SCENARIO_BY_ID", "select_scenarios",
           "step_select_scenarios", "step_specify_requirements",
           "step_reengineer_non_ontological", "step_reuse_ontological",
           "step_apply_design_patterns", "step_restructure", "step_localize"]


@dataclass(frozen=True)
class NeOnScenario:
    """One of the nine NeOn scenarios."""

    id: int
    name: str
    description: str
    #: Attribute of :class:`ConstructionState` that must be non-empty to apply.
    requires: tuple[str, ...]
    produces: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"S{self.id}"

    def applies_to(self, state: ConstructionState) -> bool:
        return all(getattr(state, attr, None) for attr in self.requires)


SCENARIOS: list[NeOnScenario] = [
    NeOnScenario(
        1, "From specification to implementation",
        "The ontology network is developed from scratch, without reusing "
        "existing resources. Requires detailed requirements specification and "
        "scheduling.",
        requires=("use_cases",), produces=("requirements", "competency_questions")),
    NeOnScenario(
        2, "Reusing and re-engineering non-ontological resources",
        "Domain experts decide which NORs (text corpora, databases, "
        "spreadsheets, glossaries) can be reused and transformed into "
        "ontologies.",
        requires=("non_ontological_resources",), produces=("candidate_terms",)),
    NeOnScenario(
        3, "Reusing ontological resources",
        "Existing ontologies, ontology modules or individual statements are "
        "used as building blocks for the network.",
        requires=("ontological_resources",), produces=("ontology.reused", "ontology.imports")),
    NeOnScenario(
        4, "Reusing and re-engineering ontological resources",
        "Existing models are not only imported but structurally adapted to the "
        "new use case.",
        requires=("ontological_resources",), produces=("ontology.subclass_of",)),
    NeOnScenario(
        5, "Reusing and merging ontological resources",
        "Several ontological resources in the same domain are selected and "
        "merged into a new, consolidated resource.",
        requires=("ontological_resources",), produces=("ontology.equivalences",)),
    NeOnScenario(
        6, "Reusing, merging and re-engineering",
        "An extension of scenario 5 in which the merged resources undergo "
        "additional structural transformation.",
        requires=("ontological_resources",), produces=("ontology.subclass_of",)),
    NeOnScenario(
        7, "Reusing ontology design patterns",
        "Developers access repositories to leverage proven design patterns for "
        "modelling complex situations.",
        requires=("design_patterns",), produces=("ontology.classes", "ontology.object_properties")),
    NeOnScenario(
        8, "Restructuring ontological resources",
        "Existing models are modularised, pruned, extended or specialised to be "
        "optimally integrated into the new network.",
        requires=("ontological_resources",), produces=("ontology.classes",)),
    NeOnScenario(
        9, "Localizing ontological resources",
        "The ontology is adapted to other languages and cultures, creating "
        "multilingual knowledge representation.",
        requires=("target_languages",), produces=("ontology.labels",)),
]

SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}


def select_scenarios(state: ConstructionState) -> list[NeOnScenario]:
    """Which scenarios the available resources actually justify.

    Scenario 1 is the fallback: if nothing is available to reuse, the network is
    built from scratch — which NeOn treats as a distinct, more expensive path
    rather than the default.
    """
    reuse = [s for s in SCENARIOS if s.id != 1 and s.applies_to(state)]
    if reuse:
        # Scenario 1 still applies when there is a use case to specify against.
        head = [SCENARIO_BY_ID[1]] if SCENARIO_BY_ID[1].applies_to(state) else []
        return head + reuse
    return [SCENARIO_BY_ID[1]]


# --------------------------------------------------------------------------- #
# Step functions — one function per step, reusable as agent tools
# --------------------------------------------------------------------------- #
def step_select_scenarios(state: ConstructionState) -> ConstructionState:
    """Decide which NeOn scenarios this project is actually running."""
    chosen = select_scenarios(state)
    state.scenarios = [s.key for s in chosen]
    state.record(
        "neon.select_scenarios", True,
        f"{len(chosen)} applicable: " + ", ".join(f"{s.key} {s.name}" for s in chosen))
    return state


def step_specify_requirements(state: ConstructionState) -> ConstructionState:
    """Scenario 1 — turn use cases into an ORSD with competency questions.

    Requirements are derived one per use case; CQs are lifted from any
    interrogative sentence in the use-case text. Deliberately mechanical: the
    point of the prototype is the *process shape*, and an LLM can be swapped in
    behind the same signature (see :mod:`ontology_construction.llms4ol`).
    """
    if not state.requirements:
        for i, uc in enumerate(state.use_cases, start=1):
            state.requirements.append(Requirement(
                id=f"R{i:02d}",
                text=uc.strip(),
                priority="MUST" if i == 1 else "SHOULD",
                source="use case",
            ))
    n_before = len(state.competency_questions)
    seen = {c.text.lower() for c in state.competency_questions}
    counter = n_before
    for req in state.requirements:
        for sentence in _sentences(req.text):
            if not sentence.endswith("?"):
                continue
            if sentence.lower() in seen:
                continue
            counter += 1
            seen.add(sentence.lower())
            state.competency_questions.append(CompetencyQuestion(
                id=f"CQ{counter:02d}", text=sentence, requirement_id=req.id))
    state.record(
        "neon.specify_requirements", bool(state.requirements),
        f"{len(state.requirements)} requirements, "
        f"{len(state.competency_questions) - n_before} new CQs")
    return state


def step_reengineer_non_ontological(state: ConstructionState) -> ConstructionState:
    """Scenario 2 — lift terms out of NORs (glossaries, corpora, schemas).

    A NOR entry of the form ``"Term: definition"`` becomes a candidate class
    with its definition preserved; anything else is treated as free text and
    left to the ontology-learning steps.
    """
    added = 0
    known = {t.label.lower() for t in state.candidate_terms}
    for nor in state.non_ontological_resources:
        for line in nor.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            label, _, definition = line.partition(":")
            label, definition = label.strip(), definition.strip()
            if not label or label.lower() in known:
                continue
            known.add(label.lower())
            state.candidate_terms.append(CandidateTerm(
                label=label, type_label="Class", score=1.0,
                provenance="NeOn:S2 non-ontological resource"))
            if definition:
                state.ontology.definitions[label] = definition
            added += 1
    state.record("neon.reengineer_nor", True,
                 f"{added} terms lifted from {len(state.non_ontological_resources)} NORs")
    return state


def step_reuse_ontological(state: ConstructionState) -> ConstructionState:
    """Scenario 3 — import external ontologies and record what came from where.

    Recording provenance per reused term is what later lets the conciseness and
    equivalence metrics distinguish "we reused FIBO's LegalEntity" from "we
    reinvented it".
    """
    for res in state.ontological_resources:
        iri, _, terms = res.partition("#terms=")
        iri = iri.strip()
        if iri and iri not in state.ontology.imports:
            state.ontology.imports.append(iri)
        for term in filter(None, (t.strip() for t in terms.split(","))):
            state.ontology.add_class(term)
            state.ontology.reused[term] = iri
    state.record("neon.reuse_ontological", True,
                 f"{len(state.ontology.imports)} imports, "
                 f"{len(state.ontology.reused)} reused terms")
    return state


def step_apply_design_patterns(state: ConstructionState) -> ConstructionState:
    """Scenario 7 — instantiate ontology design patterns.

    Patterns are given as ``"name: A -relation-> B"`` and expand into the
    classes and object property they imply. Real ODP repositories carry far
    more (axioms, competency questions, provenance); the shape is the same.
    """
    import re

    from .state import RelationEdge

    # `A - predicate -> B`, tolerating `A -predicate-> B` and extra spacing.
    triple_re = re.compile(r"^\s*(?P<domain>[^-<>]+?)\s*-+\s*(?P<pred>[^-<>]+?)\s*-*>\s*"
                           r"(?P<range>[^-<>]+?)\s*$")
    applied = 0
    for pattern in state.design_patterns:
        name, _, body = pattern.partition(":")
        for triple in body.split(";"):
            m = triple_re.match(triple)
            if not m:
                continue
            domain = m.group("domain").strip()
            predicate = m.group("pred").strip()
            rng = m.group("range").strip()
            if not (domain and predicate and rng):
                continue
            state.ontology.add_class(domain)
            state.ontology.add_class(rng)
            state.ontology.object_properties.append(RelationEdge(
                domain=domain, predicate=predicate, range=rng,
                score=1.0, provenance=f"NeOn:S7 ODP {name.strip()}"))
            applied += 1
    state.record("neon.apply_odps", True,
                 f"{applied} pattern relations from {len(state.design_patterns)} ODPs")
    return state


def step_restructure(state: ConstructionState) -> ConstructionState:
    """Scenario 8 — prune classes that no competency question can reach.

    NeOn's restructuring activity is modularise / prune / extend / specialise.
    Pruning is the one with a testable criterion: a class no CQ mentions and
    nothing else depends on is scope creep, and the ORSD is the arbiter.
    """
    if not state.competency_questions:
        state.record("neon.restructure", True, "skipped: no CQs to prune against")
        return state
    corpus = " ".join(c.text.lower() for c in state.competency_questions)
    corpus += " " + " ".join(r.text.lower() for r in state.requirements)
    connected = {c for c, _ in state.ontology.subclass_of}
    connected |= {p for _, p in state.ontology.subclass_of}
    connected |= {r.domain for r in state.ontology.object_properties}
    connected |= {r.range for r in state.ontology.object_properties}
    connected |= set(state.ontology.reused)

    pruned = {c for c in state.ontology.classes
              if c.lower() not in corpus and c not in connected}
    state.ontology.classes -= pruned
    state.record("neon.restructure", True,
                 f"pruned {len(pruned)} classes unreachable from the ORSD"
                 + (f": {sorted(pruned)}" if pruned else ""))
    return state


def step_localize(state: ConstructionState) -> ConstructionState:
    """Scenario 9 — add multilingual labels.

    Without a translation resource the honest behaviour is to *record the gap*
    rather than invent labels: every class gets an English label, and the
    missing target-language labels are reported as work to do. Fabricating them
    would be exactly the hallucination the source report warns about.
    """
    onto = state.ontology
    missing: dict[str, list[str]] = {}
    for cls in sorted(onto.classes):
        labels = onto.labels.setdefault(cls, {})
        labels.setdefault("en", cls)
        gaps = [lang for lang in state.target_languages
                if lang != "en" and lang not in labels]
        if gaps:
            missing[cls] = gaps
    state.reports["localization_gaps"] = missing
    state.record(
        "neon.localize", True,
        f"{len(onto.classes)} classes labelled in en; "
        f"{len(missing)} awaiting {sorted(set(state.target_languages) - {'en'})}")
    return state


# --------------------------------------------------------------------------- #
def _sentences(text: str) -> list[str]:
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in ".?!":
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out
