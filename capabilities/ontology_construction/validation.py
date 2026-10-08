"""Automated validation — OOPS!-style pitfalls, Themis-style CQ tests, CWA shapes.

Three tools, matching the report's "Automated Validation Tools" section:

* **OOPS! (OntOlogy Pitfall Scanner!)** — "checks *how* the ontology is built",
  cross-referencing the model against a catalogue of over 40 modelling pitfalls,
  categorised Critical / Important / Minor. Fifteen of them are implemented
  here with their real catalogue identifiers; the rest need a reasoner or a
  lexical resource. The report names two explicitly as critical — **P03**
  (creating an "is" relationship instead of ``rdfs:subClassOf``) and cyclic
  class hierarchies (**P06**) — and those severities follow it.
* **Themis** — "verifies *what* the ontology can do", translating natural
  language competency questions into formalised test expressions via
  lexico-syntactic patterns, then executing them. This is Behaviour-Driven
  Development for ontologies, and it is the one check that fails when the
  ontology is well-formed but useless.
* **Shape validation under the Closed World Assumption** — the report's central
  architectural point: OWL's Open World Assumption means a missing fact is
  merely unknown, so an OWL reasoner "might simply infer new facts to resolve
  the discrepancy, rendering OWL ineffective as a strict quality gatekeeper".
  :func:`validate_shapes` demonstrates the CWA alternative directly, and
  :func:`compare_owa_cwa` makes the divergence visible on one dataset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .state import CompetencyQuestion, ConstructionState, OntologyDraft

__all__ = [
    "Severity", "Pitfall", "PitfallReport", "scan_pitfalls",
    "Shape", "ShapeViolation", "validate_shapes", "compare_owa_cwa",
    "CQTest", "ThemisReport", "formalise_cq", "run_themis",
    "step_scan_pitfalls", "step_formalise_cqs", "step_run_themis",
    "step_validate_shapes", "LEXICO_SYNTACTIC_PATTERNS",
]


class Severity:
    CRITICAL = "Critical"
    IMPORTANT = "Important"
    MINOR = "Minor"

    ORDER = (CRITICAL, IMPORTANT, MINOR)


# --------------------------------------------------------------------------- #
# OOPS! — pitfall scanning
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Pitfall:
    """One detected pitfall, with its OOPS! catalogue identifier."""

    code: str
    name: str
    severity: str
    affected: tuple[str, ...]
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.code} [{self.severity}] {self.name}: {self.detail}"


@dataclass
class PitfallReport:
    pitfalls: list[Pitfall] = field(default_factory=list)

    def by_severity(self, severity: str) -> list[Pitfall]:
        return [p for p in self.pitfalls if p.severity == severity]

    @property
    def critical(self) -> int:
        return len(self.by_severity(Severity.CRITICAL))

    @property
    def important(self) -> int:
        return len(self.by_severity(Severity.IMPORTANT))

    @property
    def minor(self) -> int:
        return len(self.by_severity(Severity.MINOR))

    @property
    def blocks_release(self) -> bool:
        return self.critical > 0

    def as_dict(self) -> dict:
        return {
            "critical": self.critical,
            "important": self.important,
            "minor": self.minor,
            "codes": sorted({p.code for p in self.pitfalls}),
            "pitfalls": [
                {"code": p.code, "name": p.name, "severity": p.severity,
                 "affected": list(p.affected), "detail": p.detail}
                for p in sorted(self.pitfalls,
                                key=lambda x: (Severity.ORDER.index(x.severity), x.code))
            ],
        }


def _find_cycles(edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for child, parent in edges:
        graph.setdefault(child, set()).add(parent)
    cycles: list[list[str]] = []
    seen: set[str] = set()

    def walk(node: str, path: list[str], on_path: set[str]) -> None:
        if node in on_path:
            cycles.append(path[path.index(node):] + [node])
            return
        if node in seen:
            return
        on_path.add(node)
        for nxt in graph.get(node, ()):
            walk(nxt, path + [nxt], on_path)
        on_path.discard(node)
        seen.add(node)

    for start in list(graph):
        walk(start, [start], set())
    # de-duplicate rotations of the same cycle
    out, keys = [], set()
    for c in cycles:
        key = tuple(sorted(set(c)))
        if key not in keys:
            keys.add(key)
            out.append(c)
    return out


def _naming_style(name: str) -> str:
    if "_" in name:
        return "snake_case"
    if " " in name:
        return "spaced"
    if name[:1].isupper():
        return "UpperCamelCase"
    return "lowerCamelCase"


def scan_pitfalls(draft: OntologyDraft, state: Optional[ConstructionState] = None
                  ) -> PitfallReport:
    """Fifteen pitfalls from the OOPS! catalogue, by their real identifiers."""
    found: list[Pitfall] = []
    classes = sorted(draft.classes)

    # P03 — "is" relationship instead of rdfs:subClassOf. Report calls this critical.
    bad_is = tuple(sorted(
        f"{r.domain} -{r.predicate}-> {r.range}"
        for r in draft.object_properties
        if r.predicate.strip().lower() in {"is", "isa", "is a", "isA".lower(), "type"}))
    if bad_is:
        found.append(Pitfall(
            "P03", "Creating the relationship 'is' instead of rdfs:subClassOf",
            Severity.CRITICAL, bad_is,
            f"{len(bad_is)} relation(s) encode subsumption as a plain property"))

    # P06 — cycles in the class hierarchy. Report calls this critical.
    cycles = _find_cycles(draft.subclass_of)
    if cycles:
        found.append(Pitfall(
            "P06", "Including cycles in the class hierarchy", Severity.CRITICAL,
            tuple(" -> ".join(c) for c in cycles),
            f"{len(cycles)} cycle(s) detected"))

    # P19 — multiple domains or ranges for the same property.
    dom: dict[str, set[str]] = {}
    rng: dict[str, set[str]] = {}
    for r in draft.object_properties:
        dom.setdefault(r.predicate, set()).add(r.domain)
        rng.setdefault(r.predicate, set()).add(r.range)
    multi = tuple(sorted(
        f"{p} (domains: {sorted(d)})" for p, d in dom.items() if len(d) > 1))
    multi += tuple(sorted(
        f"{p} (ranges: {sorted(x)})" for p, x in rng.items() if len(x) > 1))
    if multi:
        found.append(Pitfall(
            "P19", "Defining multiple domains or ranges in properties",
            Severity.CRITICAL, multi,
            "multiple domains/ranges are intersected by OWL, rarely the intent"))

    # P24 — recursive definition: a class defined in terms of itself.
    recursive = tuple(sorted(
        c for c in classes
        if c in draft.definitions and re.search(rf"\b{re.escape(c)}\b",
                                                draft.definitions[c], re.I)))
    if recursive:
        found.append(Pitfall(
            "P24", "Using recursive definitions", Severity.IMPORTANT, recursive,
            f"{len(recursive)} class(es) whose definition names the class itself"))

    # P25 — a relationship declared inverse to itself.
    self_inverse = tuple(sorted(
        f"{r.predicate}" for r in draft.object_properties
        if r.domain == r.range and r.predicate.lower().endswith("by")
        and any(o.predicate == r.predicate[:-2].lower() and o.domain == r.range
                for o in draft.object_properties)))
    if self_inverse:
        found.append(Pitfall(
            "P25", "Defining a relationship inverse to itself",
            Severity.IMPORTANT, self_inverse, "symmetric-looking inverse pair"))

    # P04 — unconnected ontology elements.
    touched = {c for c, _ in draft.subclass_of} | {p for _, p in draft.subclass_of}
    touched |= {r.domain for r in draft.object_properties}
    touched |= {r.range for r in draft.object_properties}
    touched |= {a.domain for a in draft.datatype_properties}
    orphans = tuple(sorted(set(classes) - touched))
    if orphans:
        found.append(Pitfall(
            "P04", "Creating unconnected ontology elements", Severity.IMPORTANT,
            orphans, f"{len(orphans)} class(es) participate in no axiom"))

    # P08 — missing annotations.
    unannotated = tuple(sorted(
        c for c in classes if not draft.labels.get(c) and not draft.definitions.get(c)))
    if unannotated:
        found.append(Pitfall(
            "P08", "Missing annotations", Severity.MINOR, unannotated,
            f"{len(unannotated)}/{len(classes)} classes lack label and definition"))

    # P10 — missing disjointness.
    siblings: dict[str, set[str]] = {}
    for child, parent in draft.subclass_of:
        siblings.setdefault(parent, set()).add(child)
    undeclared = tuple(sorted(
        f"{parent}: {sorted(kids)}" for parent, kids in siblings.items()
        if len(kids) > 1 and not any(
            (a, b) in draft.disjointness or (b, a) in draft.disjointness
            for a in kids for b in kids if a != b)))
    if undeclared:
        found.append(Pitfall(
            "P10", "Missing disjointness", Severity.IMPORTANT, undeclared,
            f"{len(undeclared)} sibling set(s) with no disjointness declared"))

    # P11 — missing domain or range in properties.
    missing_dr = tuple(sorted(
        r.predicate for r in draft.object_properties if not r.domain or not r.range))
    if missing_dr:
        found.append(Pitfall(
            "P11", "Missing domain or range in properties", Severity.IMPORTANT,
            missing_dr, f"{len(missing_dr)} propertie(s) incompletely typed"))

    # P13 — inverse relationships not explicitly declared.
    preds = {r.predicate for r in draft.object_properties}
    implied_inverse = tuple(sorted(
        p for p in preds
        if (p.lower().endswith("by") and p[:-2].lower() in {q.lower() for q in preds})))
    if implied_inverse:
        found.append(Pitfall(
            "P13", "Inverse relationships not explicitly declared",
            Severity.IMPORTANT, implied_inverse,
            "predicate pairs look inverse but owl:inverseOf is absent"))

    # P02 — synonyms created as separate classes.
    norm: dict[str, list[str]] = {}
    for c in classes:
        norm.setdefault(re.sub(r"[^a-z]", "", c.lower()), []).append(c)
    synonyms = tuple(sorted(" / ".join(v) for v in norm.values() if len(v) > 1))
    if synonyms:
        found.append(Pitfall(
            "P02", "Creating synonyms as classes", Severity.MINOR, synonyms,
            f"{len(synonyms)} group(s) differ only in punctuation or case"))

    # P30 — equivalent classes not explicitly declared.
    reused_pairs = tuple(sorted(
        f"{local} ~ {src}" for local, src in draft.reused.items()
        if local in draft.classes and not any(
            local in pair for pair in draft.equivalences)))
    if reused_pairs and draft.reused:
        found.append(Pitfall(
            "P30", "Equivalent classes not explicitly declared", Severity.IMPORTANT,
            reused_pairs,
            "reused terms are not linked to their source with owl:equivalentClass"))

    # P32 — several classes with the same label.
    by_label: dict[str, list[str]] = {}
    for c in classes:
        for lang, lab in draft.labels.get(c, {}).items():
            by_label.setdefault(f"{lab.lower()}@{lang}", []).append(c)
    dup_labels = tuple(sorted(
        f"{k}: {sorted(v)}" for k, v in by_label.items() if len(v) > 1))
    if dup_labels:
        found.append(Pitfall(
            "P32", "Several classes with the same label", Severity.MINOR,
            dup_labels, f"{len(dup_labels)} label collision(s)"))

    # P22 — inconsistent naming conventions.
    styles = {c: _naming_style(c) for c in classes}
    distinct = set(styles.values())
    if len(distinct) > 1:
        found.append(Pitfall(
            "P22", "Using different naming conventions in the ontology",
            Severity.MINOR, tuple(sorted(distinct)),
            f"{len(distinct)} naming styles across {len(classes)} classes"))

    # P41 — no licence declared.
    if not draft.license:
        found.append(Pitfall(
            "P41", "No license declared", Severity.IMPORTANT, (),
            "an ontology intended for reuse must state its licence"))

    return PitfallReport(found)


# --------------------------------------------------------------------------- #
# Themis — competency-question testing
# --------------------------------------------------------------------------- #
#: Lexico-syntactic patterns mapping CQ shapes to executable test expressions.
LEXICO_SYNTACTIC_PATTERNS: list[tuple[str, str, str]] = [
    ("subsumption", r"^is\s+(?:a|an)?\s*(?P<child>.+?)\s+(?:a|an)\s+(?P<parent>.+?)\s*\?$",
     "ASK { ?c rdfs:subClassOf* ?p }"),
    ("relation", r"^(?:what|which)\s+(?P<range>.+?)\s+(?:is|are)\s+(?P<pred>\w+)\s+(?:by|to|of|for)?\s*(?:a|an|the)?\s*(?P<domain>.+?)\s*\?$",
     "SELECT ?s ?o WHERE { ?s ?p ?o }"),
    ("attribute", r"^what\s+(?:is|are)\s+the\s+(?P<attr>.+?)\s+of\s+(?:a|an|the)?\s*(?P<cls>.+?)\s*\?$",
     "SELECT ?p WHERE { ?p rdfs:domain ?c }"),
    ("enumeration", r"^(?:what|which)\s+(?:kinds?|types?)\s+of\s+(?P<cls>.+?)\s+(?:are there|exist).*\?$",
     "SELECT ?sub WHERE { ?sub rdfs:subClassOf ?c }"),
    ("existence", r"^(?:what|which|who)\s+(?P<cls>.+?)\s*\?$",
     "ASK { ?c a owl:Class }"),
    ("count", r"^how many\s+(?P<cls>.+?)\s+.*\?$",
     "SELECT (COUNT(?x) AS ?n) WHERE { ?x a ?c }"),
]


@dataclass
class CQTest:
    """A competency question compiled into an executable check."""

    cq_id: str
    text: str
    pattern: str
    targets: tuple[str, ...]
    kind: str                     # class | subsumption | relation | attribute
    passed: bool = False
    detail: str = ""


@dataclass
class ThemisReport:
    tests: list[CQTest] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.passed)

    @property
    def failed(self) -> int:
        return len(self.tests) - self.passed

    @property
    def coverage(self) -> float:
        return round(self.passed / len(self.tests), 4) if self.tests else 0.0

    def as_dict(self) -> dict:
        return {"total": len(self.tests), "passed": self.passed,
                "failed": self.failed, "coverage": self.coverage,
                "tests": [{"cq": t.cq_id, "text": t.text, "pattern": t.pattern,
                           "kind": t.kind, "targets": list(t.targets),
                           "passed": t.passed, "detail": t.detail}
                          for t in self.tests]}


_ARTICLES = re.compile(r"^(?:a|an|the)\s+", re.I)


def _clean(term: str) -> str:
    return _ARTICLES.sub("", term.strip().strip("?.,").lower()).strip()


def formalise_cq(cq: CompetencyQuestion) -> CQTest:
    """Classify a CQ by lexico-syntactic pattern and extract what it demands.

    Themis' actual mechanism: translate the natural-language CQ into a formal
    test expression via patterns, then execute it. A CQ that matches no pattern
    is reported as *unformalised* rather than silently passing — an untestable
    requirement is a gap in the ORSD, not a success.
    """
    text = cq.text.strip()
    low = text.lower()
    for name, regex, sparql in LEXICO_SYNTACTIC_PATTERNS:
        m = re.match(regex, low, re.I)
        if not m:
            continue
        groups = {k: _clean(v) for k, v in m.groupdict().items() if v}
        if name == "subsumption":
            targets = (groups.get("child", ""), groups.get("parent", ""))
            kind = "subsumption"
        elif name == "relation":
            targets = (groups.get("domain", ""), groups.get("pred", ""),
                       groups.get("range", ""))
            kind = "relation"
        elif name == "attribute":
            targets = (groups.get("cls", ""), groups.get("attr", ""))
            kind = "attribute"
        else:
            targets = (groups.get("cls", ""),)
            kind = "class"
        cq.pattern = name
        cq.sparql = sparql
        return CQTest(cq.id, text, name, tuple(t for t in targets if t), kind)
    cq.pattern = "unmatched"
    return CQTest(cq.id, text, "unmatched", (), "unknown",
                  detail="no lexico-syntactic pattern matched; CQ not formalisable")


def _known(draft: OntologyDraft, term: str) -> Optional[str]:
    """Resolve a natural-language term to a class in the draft."""
    term = term.strip().lower()
    if not term:
        return None
    for c in draft.classes:
        if c.lower() == term:
            return c
    for c in draft.classes:
        cl = c.lower()
        if cl in term or term in cl:
            return c
    for c, labels in draft.labels.items():
        if any(lab.lower() == term for lab in labels.values()):
            return c
    return None


def run_themis(state: ConstructionState) -> ThemisReport:
    """Execute the formalised CQs against the ontology draft."""
    draft = state.ontology
    ancestors: dict[str, set[str]] = {}
    for child, parent in draft.subclass_of:
        ancestors.setdefault(child, set()).add(parent)

    def reaches(child: str, parent: str) -> bool:
        seen, stack = set(), [child]
        while stack:
            cur = stack.pop()
            if cur == parent and cur != child:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(ancestors.get(cur, ()))
        return parent in ancestors.get(child, set())

    tests: list[CQTest] = []
    for cq in state.competency_questions:
        test = formalise_cq(cq)
        if test.pattern == "unmatched":
            tests.append(test)
            continue
        if test.kind == "subsumption" and len(test.targets) == 2:
            c, p = (_known(draft, test.targets[0]), _known(draft, test.targets[1]))
            test.passed = bool(c and p and reaches(c, p))
            test.detail = (f"{c} subClassOf* {p}" if test.passed
                           else f"no subsumption path {test.targets[0]} -> {test.targets[1]}")
        elif test.kind == "relation" and len(test.targets) == 3:
            d, pred, r = test.targets
            dom, rng = _known(draft, d), _known(draft, r)
            hit = next((x for x in draft.object_properties
                        if (dom is None or x.domain == dom)
                        and (rng is None or x.range == rng)), None)
            test.passed = hit is not None
            test.detail = (f"satisfied by {hit.domain} -{hit.predicate}-> {hit.range}"
                           if hit else f"no relation between {d!r} and {r!r}")
        elif test.kind == "attribute" and test.targets:
            cls = _known(draft, test.targets[0])
            hit = next((a for a in draft.datatype_properties
                        if cls and a.domain == cls), None)
            test.passed = hit is not None
            test.detail = (f"satisfied by {hit.predicate}" if hit
                           else f"no datatype property on {test.targets[0]!r}")
        else:
            cls = _known(draft, test.targets[0]) if test.targets else None
            test.passed = cls is not None
            test.detail = (f"class {cls} present" if cls
                           else f"no class matching {test.targets!r}")
        tests.append(test)
    return ThemisReport(tests)


# --------------------------------------------------------------------------- #
# CWA shape validation, and the OWA/CWA contrast
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Shape:
    """A minimal SHACL-style node shape."""

    target_class: str
    required_properties: tuple[str, ...] = ()
    datatypes: dict[str, str] = field(default_factory=dict)
    min_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ShapeViolation:
    focus_node: str
    shape: str
    constraint: str
    detail: str


def validate_shapes(instances: list[dict], shapes: list[Shape]) -> list[ShapeViolation]:
    """Validate instance data against shapes under the Closed World Assumption.

    Under CWA a missing required property *is* a violation. That is precisely
    what makes SHACL usable as a gatekeeper where OWL is not — see
    :func:`compare_owa_cwa`.
    """
    by_class = {s.target_class: s for s in shapes}
    out: list[ShapeViolation] = []
    for inst in instances:
        cls = inst.get("type")
        shape = by_class.get(cls)
        if shape is None:
            continue
        node = str(inst.get("id", "<anonymous>"))
        for prop in shape.required_properties:
            if prop not in inst or inst[prop] in (None, "", [], {}):
                out.append(ShapeViolation(
                    node, cls, "sh:minCount",
                    f"required property {prop!r} is absent"))
        for prop, expected in shape.datatypes.items():
            if prop in inst and not _datatype_ok(inst[prop], expected):
                out.append(ShapeViolation(
                    node, cls, "sh:datatype",
                    f"{prop!r}={inst[prop]!r} is not {expected}"))
        for prop, minimum in shape.min_counts.items():
            values = inst.get(prop, [])
            n = len(values) if isinstance(values, (list, tuple, set)) else (0 if values in (None, "") else 1)
            if n < minimum:
                out.append(ShapeViolation(
                    node, cls, "sh:minCount",
                    f"{prop!r} has {n} value(s), needs at least {minimum}"))
    return out


def _datatype_ok(value, expected: str) -> bool:
    expected = expected.split(":")[-1]
    if expected in ("integer", "int"):
        return isinstance(value, int) and not isinstance(value, bool)
    if expected in ("decimal", "float", "double"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "date":
        return isinstance(value, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))
    return isinstance(value, str)


def compare_owa_cwa(instances: list[dict], shapes: list[Shape]) -> dict:
    """Show why OWL cannot be the data gatekeeper, on one dataset.

    The report: under the Open World Assumption "the absence of a fact does not
    imply the fact is false; it merely means the fact is currently unknown", so
    an OWL reasoner confronted with data missing a required property "might
    simply infer new facts to resolve the discrepancy" rather than rejecting it.

    Modelled honestly: the OWA column reports what an OWL reasoner would
    *conclude* (nothing is wrong — a value simply exists but is unknown), while
    the CWA column reports what a shape processor *rejects*.
    """
    violations = validate_shapes(instances, shapes)
    missing = [v for v in violations if v.constraint == "sh:minCount"]
    return {
        "instances": len(instances),
        "owa_rejections": 0,
        "owa_conclusion": (
            f"{len(missing)} missing-value case(s) treated as unknown, not false; "
            "an OWL reasoner infers an unnamed filler rather than failing"),
        "cwa_rejections": len(violations),
        "cwa_conclusion": (
            f"{len(violations)} violation(s) rejected: "
            + "; ".join(f"{v.focus_node} {v.constraint} {v.detail}"
                        for v in violations[:5])
            if violations else "all instances conform"),
        "gatekeeper": "SHACL/CWA" if violations else "either",
    }


# --------------------------------------------------------------------------- #
# Step functions
# --------------------------------------------------------------------------- #
def step_scan_pitfalls(state: ConstructionState) -> ConstructionState:
    """Run the OOPS!-style structural scan and file the report."""
    report = scan_pitfalls(state.ontology, state)
    state.reports["pitfalls"] = report.as_dict()
    state.record(
        "oops.scan", not report.blocks_release,
        f"{report.critical} critical, {report.important} important, "
        f"{report.minor} minor "
        f"({', '.join(sorted({p.code for p in report.pitfalls})) or 'none'})",
        gate="OOPS!")
    return state


def step_formalise_cqs(state: ConstructionState) -> ConstructionState:
    """Compile CQs into test expressions via lexico-syntactic patterns."""
    formalised = 0
    for cq in state.competency_questions:
        test = formalise_cq(cq)
        if test.pattern != "unmatched":
            formalised += 1
    total = len(state.competency_questions)
    state.record("themis.formalise", formalised == total,
                 f"{formalised}/{total} CQs matched a lexico-syntactic pattern")
    return state


def step_run_themis(state: ConstructionState) -> ConstructionState:
    """Execute the CQ suite — functional validation."""
    report = run_themis(state)
    state.reports["themis"] = report.as_dict()
    state.record("themis.run", report.failed == 0,
                 f"{report.passed}/{len(report.tests)} CQs satisfied "
                 f"(coverage {report.coverage:.0%})", gate="Themis")
    return state


def step_validate_shapes(state: ConstructionState, *,
                         instances: list[dict] | None = None,
                         shapes: list[Shape] | None = None) -> ConstructionState:
    """Validate sample instance data under CWA, and contrast with OWA."""
    instances = instances or state.reports.get("sample_instances", [])
    shapes = shapes or _shapes_from_draft(state.ontology)
    comparison = compare_owa_cwa(instances, shapes)
    state.reports["shapes"] = comparison
    state.record("shacl.validate", comparison["cwa_rejections"] == 0,
                 f"{comparison['cwa_rejections']} CWA violation(s) over "
                 f"{comparison['instances']} instance(s); OWA would reject "
                 f"{comparison['owa_rejections']}", gate="SHACL")
    return state


def _shapes_from_draft(draft: OntologyDraft) -> list[Shape]:
    """Derive shapes from the schema — PoolParty's OWL→SHACL transform in miniature.

    The report notes that platforms like PoolParty transform OWL definitions
    into SHACL shapes automatically, "facilitating the transition from the
    'Open World' to the 'Closed World' of constraint validation without manual
    intervention". This is the same move: every declared domain becomes a
    required property on that class.
    """
    required: dict[str, list[str]] = {}
    datatypes: dict[str, dict[str, str]] = {}
    for r in draft.object_properties:
        required.setdefault(r.domain, []).append(draft.property_name(r.predicate))
    for a in draft.datatype_properties:
        required.setdefault(a.domain, []).append(draft.property_name(a.predicate))
        datatypes.setdefault(a.domain, {})[draft.property_name(a.predicate)] = a.datatype
    return [Shape(cls, tuple(sorted(set(props))), datatypes.get(cls, {}))
            for cls, props in sorted(required.items())]
