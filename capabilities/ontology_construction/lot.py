"""The LOT (Linked Open Terms) methodology — four iterative sprints.

From the source report: LOT is "a lightweight, agile alternative optimized for
modern software industry standards", adapting CI/CD philosophies to ontology
engineering and organising development into four iterative sprints —
**requirements specification, implementation, publication, maintenance**.

Three of the report's specifics are implemented rather than described:

* **CQs are the centre of the requirements sprint.** They "define the functional
  scope of the ontology by articulating the exact natural language queries the
  final system must be able to answer". :func:`step_lot_requirements` refuses to
  close the sprint without them.
* **Chowlk-style visual conceptualisation.** The report notes that domain
  experts sketch conceptualisations as UML, "which are then automatically
  translated into OWL". :func:`parse_chowlk` accepts a compact textual UML and
  produces the same artifacts, so the conceptual model is a real input rather
  than a diagram nobody can execute.
* **Publication means content negotiation.** The sprint "mandates that the
  ontology is accessible via standard web protocols (content negotiation) both
  as human-readable documentation (HTML) and machine-readable code (RDF/XML,
  Turtle) via its namespace URI". :func:`step_lot_publication` produces both
  representations and the negotiation table, and fails if the namespace is not
  dereferenceable-shaped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .state import (
    AttributeEdge,
    CompetencyQuestion,
    ConstructionState,
    RelationEdge,
    Requirement,
    TaxonomyEdge,
)

__all__ = [
    "SPRINTS", "ConceptualModel", "parse_chowlk",
    "step_lot_requirements", "step_lot_implementation",
    "step_lot_publication", "step_lot_maintenance",
]

#: The four LOT sprints, in order.
SPRINTS: tuple[str, ...] = ("requirements", "implementation", "publication",
                            "maintenance")


# --------------------------------------------------------------------------- #
# Chowlk-style conceptual model
# --------------------------------------------------------------------------- #
@dataclass
class ConceptualModel:
    """A UML-ish sketch: classes, generalisations, associations, attributes."""

    classes: list[str] = field(default_factory=list)
    generalisations: list[tuple[str, str]] = field(default_factory=list)  # (child, parent)
    associations: list[tuple[str, str, str]] = field(default_factory=list)  # (a, role, b)
    attributes: list[tuple[str, str, str]] = field(default_factory=list)  # (cls, attr, datatype)

    def summary(self) -> str:
        return (f"{len(self.classes)} classes, {len(self.generalisations)} "
                f"generalisations, {len(self.associations)} associations, "
                f"{len(self.attributes)} attributes")


_GEN = re.compile(r"^\s*(?P<child>[\w \-]+?)\s*(?:--\|>|<\|--|isa|:>)\s*(?P<parent>[\w \-]+?)\s*$", re.I)
_ASSOC = re.compile(r"^\s*(?P<a>[\w \-]+?)\s*--\s*(?P<role>[\w ]+?)\s*-->\s*(?P<b>[\w \-]+?)\s*$")
_ATTR = re.compile(r"^\s*(?P<cls>[\w \-]+?)\s*\.\s*(?P<attr>[\w ]+?)\s*:\s*(?P<dt>[\w:]+)\s*$")
_CLS = re.compile(r"^\s*class\s+(?P<name>[\w \-]+?)\s*$", re.I)


def parse_chowlk(sketch: str) -> ConceptualModel:
    """Parse a compact textual UML sketch into a :class:`ConceptualModel`.

    Grammar, one statement per line::

        class Loan
        Mortgage --|> Loan                 # generalisation
        Loan -- issued by --> Bank         # association
        Loan.principal : xsd:decimal       # attribute

    Deliberately tiny. The point is that the conceptualisation a domain expert
    produces is machine-readable and therefore testable, which is what the
    report credits Chowlk with — bridging "the semantic gap between domain
    experts defining the use cases and the technical systems processing the
    logical axioms".
    """
    model = ConceptualModel()
    seen: set[str] = set()

    def remember(name: str) -> str:
        name = name.strip()
        if name and name.lower() not in {s.lower() for s in seen}:
            seen.add(name)
            model.classes.append(name)
        return name

    for raw in sketch.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _CLS.match(line)
        if m:
            remember(m.group("name"))
            continue
        m = _ATTR.match(line)
        if m:
            cls = remember(m.group("cls"))
            model.attributes.append((cls, m.group("attr").strip(),
                                     m.group("dt").strip()))
            continue
        m = _ASSOC.match(line)
        if m:
            a, b = remember(m.group("a")), remember(m.group("b"))
            model.associations.append((a, m.group("role").strip(), b))
            continue
        m = _GEN.match(line)
        if m:
            child, parent = remember(m.group("child")), remember(m.group("parent"))
            model.generalisations.append((child, parent))
            continue
    return model


# --------------------------------------------------------------------------- #
# Sprint 1 — ontology requirements specification
# --------------------------------------------------------------------------- #
def step_lot_requirements(state: ConstructionState, *,
                          require_cqs: bool = True) -> ConstructionState:
    """Sprint 1: purpose, scope, users, and the competency questions.

    Fails the sprint when there are no CQs. That is not pedantry: the report
    makes CQs the definition of functional scope, and everything downstream —
    Themis validation, the completeness criterion, NeOn's restructuring pass —
    measures against them. A LOT project without CQs has no acceptance test.
    """
    ok = True
    problems: list[str] = []

    if not state.purpose:
        state.purpose = (f"Provide a shared conceptualisation of "
                         f"{state.domain or 'the domain'} for the stated use cases.")
    if not state.scope:
        state.scope = "; ".join(state.use_cases[:3]) or "unspecified"
    if not state.intended_users:
        state.intended_users = ["domain expert", "application developer"]

    if not state.requirements:
        for i, uc in enumerate(state.use_cases, start=1):
            state.requirements.append(Requirement(
                id=f"R{i:02d}", text=uc.strip(),
                priority="MUST" if i == 1 else "SHOULD", source="LOT sprint 1"))
    if not state.requirements:
        ok = False
        problems.append("no requirements: nothing to build against")

    if require_cqs and not state.competency_questions:
        ok = False
        problems.append("no competency questions: functional scope undefined")

    state.record(
        "lot.requirements", ok,
        (f"purpose set, scope={state.scope[:60]!r}, "
         f"{len(state.requirements)} requirements, "
         f"{len(state.competency_questions)} CQs")
        if ok else "; ".join(problems))
    return state


# --------------------------------------------------------------------------- #
# Sprint 2 — implementation
# --------------------------------------------------------------------------- #
def step_lot_implementation(state: ConstructionState, *,
                            conceptual_model: ConceptualModel | str | None = None,
                            ) -> ConstructionState:
    """Sprint 2: turn the conceptual model and learned artifacts into OWL.

    Two inputs are merged, deliberately in this order:

    1. the **conceptual model** — what a domain expert asserted, highest trust;
    2. the **learned artifacts** — what ontology learning proposed, lower trust.

    Learned content never overwrites an expert assertion; where they conflict
    the expert wins and the conflict is recorded. That ordering is the whole
    reason a hybrid pipeline is safer than an autonomous one.
    """
    onto = state.ontology
    if isinstance(conceptual_model, str):
        conceptual_model = parse_chowlk(conceptual_model)

    expert_subclass: set[tuple[str, str]] = set()
    if conceptual_model is not None:
        for cls in conceptual_model.classes:
            onto.add_class(cls, label=cls)
        for child, parent in conceptual_model.generalisations:
            onto.add_subclass(child, parent)
            expert_subclass.add((child, parent))
        for a, role, b in conceptual_model.associations:
            onto.add_class(a)
            onto.add_class(b)
            onto.object_properties.append(RelationEdge(
                domain=a, predicate=role, range=b, score=1.0,
                provenance="LOT:conceptual model"))
        for cls, attr, dt in conceptual_model.attributes:
            onto.add_class(cls)
            onto.datatype_properties.append(AttributeEdge(
                domain=cls, predicate=attr, datatype=dt,
                provenance="LOT:conceptual model"))

    # Reconcile case-variant names onto one canonical form. The expert wrote
    # `Loan`; the learner and the ODP produced `loan`. They are the same
    # concept, and keeping both is how a hybrid pipeline manufactures OOPS! P02
    # (synonyms as classes) and P19 (multiple domains) out of nothing.
    #
    # Two subtleties, both learned from this going wrong:
    #   * `onto.classes` is a *set*, so `{c.lower(): c for c in onto.classes}`
    #     picks a winner in arbitrary iteration order — the same input could
    #     canonicalise to `Loan` on one run and `loan` on the next.
    #   * duplicates already in the draft (added by an earlier step, e.g. an
    #     ODP) must be collapsed too, not merely avoided going forward.
    expert_names = list(conceptual_model.classes) if conceptual_model else []
    canon = _build_canon(onto, expert_names)
    _collapse_case_variants(onto, canon)

    def canonical(term: str) -> str:
        return canon.setdefault(term.lower(), term)

    conflicts = 0
    for term in state.accepted_terms():
        name = canonical(term.label)
        onto.add_class(name, label=name)
    for edge in state.accepted_taxonomy():
        child, parent = canonical(edge.child), canonical(edge.parent)
        if (parent, child) in expert_subclass:
            conflicts += 1                       # expert says the opposite direction
            continue
        if child == parent:
            continue
        onto.add_subclass(child, parent)
    for rel in state.accepted_relations():
        domain, rng = canonical(rel.domain), canonical(rel.range)
        if any(r.domain == domain and r.range == rng
               and r.provenance.startswith("LOT:") for r in onto.object_properties):
            continue
        onto.object_properties.append(
            RelationEdge(domain=domain, predicate=rel.predicate, range=rng,
                         score=rel.score, provenance=rel.provenance,
                         accepted=rel.accepted))

    state.record("lot.implementation", True,
                 f"{onto.summary()}"
                 + (f"; {conflicts} learned edge(s) overruled by the "
                    "conceptual model" if conflicts else ""))
    return state



# --------------------------------------------------------------------------- #
# Case reconciliation
# --------------------------------------------------------------------------- #
def _build_canon(onto, preferred: list[str]) -> dict[str, str]:
    """Map ``lower(name) -> canonical name``, deterministically.

    Precedence: a name the domain expert wrote in the conceptual model wins;
    otherwise the lexicographically first spelling, so the result does not
    depend on set iteration order.
    """
    canon: dict[str, str] = {}
    for name in sorted(onto.classes):
        canon.setdefault(name.lower(), name)
    for name in preferred:                     # expert naming overrides
        canon[name.lower()] = name
    return canon


def _collapse_case_variants(onto, canon: dict[str, str]) -> int:
    """Rewrite the draft so only canonical spellings remain. Returns #merged."""
    def c(name: str) -> str:
        return canon.get(name.lower(), name)

    before = len(onto.classes)
    onto.classes = {c(x) for x in onto.classes}
    onto.subclass_of = {(c(a), c(b)) for a, b in onto.subclass_of if c(a) != c(b)}
    onto.equivalences = {(c(a), c(b)) for a, b in onto.equivalences}
    onto.disjointness = {(c(a), c(b)) for a, b in onto.disjointness}
    onto.reused = {c(k): v for k, v in onto.reused.items()}

    merged_labels: dict[str, dict[str, str]] = {}
    for name, labels in onto.labels.items():
        merged_labels.setdefault(c(name), {}).update(labels)
    onto.labels = merged_labels
    onto.definitions = {c(k): v for k, v in onto.definitions.items()}

    seen_rel: set[tuple[str, str, str]] = set()
    rels = []
    for r in onto.object_properties:
        r.domain, r.range = c(r.domain), c(r.range)
        key = (r.domain, r.predicate.lower(), r.range)
        if key in seen_rel:
            continue
        seen_rel.add(key)
        rels.append(r)
    onto.object_properties = rels

    seen_attr: set[tuple[str, str]] = set()
    attrs = []
    for a in onto.datatype_properties:
        a.domain = c(a.domain)
        key = (a.domain, a.predicate.lower())
        if key in seen_attr:
            continue
        seen_attr.add(key)
        attrs.append(a)
    onto.datatype_properties = attrs
    return before - len(onto.classes)


# --------------------------------------------------------------------------- #
# Sprint 3 — publication
# --------------------------------------------------------------------------- #
def step_lot_publication(state: ConstructionState, *,
                         license: str = "http://creativecommons.org/licenses/by/4.0/",
                         ) -> ConstructionState:
    """Sprint 3: human-readable documentation plus machine-readable code.

    Produces the content-negotiation table the report requires and the two
    representations behind it. Fails when the namespace IRI is not
    dereferenceable-shaped, because an ontology nobody can resolve is not
    published in LOT's sense.
    """
    onto = state.ontology
    if license and not onto.license:
        onto.license = license

    iri = onto.iri
    dereferenceable = iri.startswith(("http://", "https://"))

    negotiation = {
        "text/html": f"{iri.rstrip('#/')}/index.html",
        "text/turtle": f"{iri.rstrip('#/')}/ontology.ttl",
        "application/rdf+xml": f"{iri.rstrip('#/')}/ontology.rdf",
    }
    state.reports["publication"] = {
        "namespace": iri,
        "dereferenceable": dereferenceable,
        "content_negotiation": negotiation,
        "license": onto.license,
        "documentation": _documentation(state),
        "turtle_bytes": len(onto.to_turtle().encode("utf-8")),
    }
    state.record("lot.publication", dereferenceable,
                 f"{len(negotiation)} representations at {iri}"
                 if dereferenceable else
                 f"namespace {iri!r} is not an http(s) IRI — not dereferenceable")
    return state


def _documentation(state: ConstructionState) -> str:
    """A Widoco/pyLODE-shaped human-readable summary."""
    onto = state.ontology
    lines = [f"# {state.domain or 'Ontology'}", "",
             f"**Namespace:** `{onto.iri}`  ",
             f"**Licence:** {onto.license or 'unspecified'}", "",
             "## Purpose", state.purpose or "_unspecified_", "",
             "## Scope", state.scope or "_unspecified_", "",
             "## Intended users", ", ".join(state.intended_users) or "_unspecified_", ""]
    if state.competency_questions:
        lines += ["## Competency questions", ""]
        themis = {t["cq"]: t["passed"]
                  for t in state.reports.get("themis", {}).get("tests", [])}
        for cq in state.competency_questions:
            mark = {True: "PASS", False: "FAIL"}.get(themis.get(cq.id), "untested")
            lines.append(f"- `{cq.id}` {cq.text} — **{mark}**")
        lines.append("")
    lines += ["## Classes", ""]
    for cls in sorted(onto.classes):
        parents = sorted(p for c, p in onto.subclass_of if c == cls)
        definition = onto.definitions.get(cls, "")
        bullet = f"- **{cls}**"
        if parents:
            bullet += f" ⊑ {', '.join(parents)}"
        if definition:
            bullet += f" — {definition}"
        lines.append(bullet)
    lines.append("")
    if onto.object_properties:
        lines += ["## Object properties", ""]
        seen: set[str] = set()
        for r in onto.object_properties:
            key = onto.property_name(r.predicate)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- **{key}**: {r.domain} → {r.range}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Sprint 4 — maintenance
# --------------------------------------------------------------------------- #
def step_lot_maintenance(state: ConstructionState, *,
                         new_requirements: Iterable[str] = (),
                         ) -> ConstructionState:
    """Sprint 4: accept new requirements as issues and re-open the loop.

    The report: maintenance "occurs through continuous iterations where domain
    experts can propose new requirements or improvements via issue tracking
    systems (like GitHub Actions), integrating seamlessly into CI/CD pipelines".
    Each new requirement becomes an issue *and* a requirement, so the next
    iteration's CQ coverage is measured against the widened scope rather than
    the original one.
    """
    issues = list(state.reports.get("issues", []))
    start = len(state.requirements)
    for i, text in enumerate(new_requirements, start=start + 1):
        req = Requirement(id=f"R{i:02d}", text=text.strip(), priority="SHOULD",
                          source="LOT sprint 4 (issue)")
        state.requirements.append(req)
        issues.append({"id": f"ISSUE-{len(issues) + 1:03d}",
                       "requirement": req.id, "text": req.text,
                       "status": "open"})
    state.reports["issues"] = issues

    themis = state.reports.get("themis", {})
    coverage = themis.get("coverage")
    drift = [t for t in themis.get("tests", []) if not t["passed"]]
    state.reports["maintenance"] = {
        "open_issues": sum(1 for i in issues if i["status"] == "open"),
        "cq_coverage": coverage,
        "regressed_cqs": [t["cq"] for t in drift],
    }
    state.record(
        "lot.maintenance", not drift,
        f"{len(state.requirements) - start} new requirement(s), "
        f"{len(issues)} issue(s); "
        + (f"{len(drift)} CQ(s) failing: {[t['cq'] for t in drift]}"
           if drift else "no CQ regressions"))
    return state
