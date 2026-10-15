"""Stage 1 (scope): the Ontology Requirements Specification, reuse candidates, the
pre-glossary, and the deterministic exit criteria of the stage.

Neither Protégé nor VocBench has a requirements stage. What SIP keeps here is NeOn's
*Ontology Requirements Specification Document* (Suárez-Figueroa, Gómez-Pérez &
Villazón-Terrazas 2009), the artefact ``capabilities/ontology_construction`` also
models: purpose, scope, implementation language, intended end-users, intended uses,
non-functional requirements, prioritised competency questions (``quality/cq.py``) and
a pre-glossary of terms.

Reuse candidates are described the way Semantic Turkey's metadata registry describes
a dataset (``DatasetMetadata``: ``dcterms:title``, ``void:uriSpace``,
``void:sparqlEndpoint``), plus the two things NeOn asks of a reuse decision: *how* the
resource is reused (import, module, align, reference) and *why*.

Everything is RDF (P3): the specification and the reuse candidates live in the
project's ``metadata`` graph, the pre-glossary next to the CQs in the ``cq`` graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS

from ..core.namespaces import SIP, VOID

__all__ = ["Specification", "ReuseCandidate", "GlossaryTerm", "Criterion", "Readiness",
           "spec_node", "spec_delta", "cq_terms", "readiness", "render_markdown",
           "SPEC_FIELDS", "SPEC_LISTS", "REUSE_MODES"]

#: Single-valued ORSD fields and the list-valued ones, with their predicates.
SPEC_FIELDS = {"purpose": SIP.purpose, "scope": SIP.scope,
               "implementation_language": SIP.implementationLanguage}
SPEC_LISTS = {"intended_users": SIP.intendedUser, "intended_uses": SIP.intendedUse,
              "non_functional": SIP.nonFunctionalRequirement}
#: NeOn reuse decisions: import the whole ontology, extract a module, align to it, or
#: only reference its terms.
REUSE_MODES = ("import", "module", "align", "reference")


def spec_node(project: str) -> URIRef:
    return URIRef(f"urn:sip:p:{project}:orsd")


@dataclass
class Specification:
    purpose: str = ""
    scope: str = ""
    implementation_language: str = ""
    intended_users: list[str] = field(default_factory=list)
    intended_uses: list[str] = field(default_factory=list)
    non_functional: list[str] = field(default_factory=list)

    @classmethod
    def from_graph(cls, g: Graph, node: URIRef) -> "Specification":
        s = cls()
        for name, p in SPEC_FIELDS.items():
            v = g.value(node, p)
            setattr(s, name, str(v) if v is not None else "")
        for name, p in SPEC_LISTS.items():
            setattr(s, name, sorted(str(v) for v in g.objects(node, p)))
        return s

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def spec_delta(g: Graph, node: URIRef, ontology: URIRef,
               values: dict) -> tuple[list[tuple], list[tuple]]:
    """Triples to add and remove so that *node* carries *values*.

    A given field replaces what the specification says for it; a field that is not
    given is left as it is. ``g`` is the view the caller is editing (staged for agents).
    """
    unknown = set(values) - set(SPEC_FIELDS) - set(SPEC_LISTS)
    if unknown:
        raise ValueError(f"unknown specification field(s) {sorted(unknown)}")
    add: list[tuple] = [(node, RDF.type, SIP.RequirementsSpecification),
                        (node, SIP.specifies, ontology)]
    rem: list[tuple] = []
    for name, v in values.items():
        p = SPEC_FIELDS.get(name) or SPEC_LISTS[name]
        new = [v] if name in SPEC_FIELDS else list(v)
        new = [x.strip() for x in new if x and x.strip()]
        old = set(g.objects(node, p))
        want = {Literal(x) for x in new}
        rem += [(node, p, o) for o in old - want]
        add += [(node, p, o) for o in want - old]
    return add, rem


@dataclass
class ReuseCandidate:
    """An ontology or dataset considered for reuse (``void:Dataset``)."""

    iri: str
    title: str
    mode: str = "reference"
    uri_space: str = ""
    rationale: str = ""
    sparql_endpoint: str = ""

    def __post_init__(self) -> None:
        if self.mode not in REUSE_MODES:
            raise ValueError(f"reuse mode is one of {' | '.join(REUSE_MODES)}, "
                             f"not {self.mode!r}")
        if not re.match(r"^(https?|urn):\S+$", self.iri):
            raise ValueError(f"reuse candidate needs an absolute IRI, not {self.iri!r}")
        if not self.title.strip():
            raise ValueError("reuse candidate needs a title")

    def triples(self):
        s = URIRef(self.iri)
        yield (s, RDF.type, VOID.Dataset)
        yield (s, RDF.type, SIP.ReuseCandidate)
        yield (s, DCTERMS.title, Literal(self.title))
        yield (s, SIP.reuseMode, Literal(self.mode))
        if self.uri_space:
            yield (s, VOID.uriSpace, Literal(self.uri_space))
        if self.rationale:
            yield (s, SIP.rationale, Literal(self.rationale))
        if self.sparql_endpoint:
            yield (s, VOID.sparqlEndpoint, URIRef(self.sparql_endpoint))

    @classmethod
    def from_graph(cls, g: Graph) -> list["ReuseCandidate"]:
        out = []
        for s in g.subjects(RDF.type, SIP.ReuseCandidate):
            def v(p):
                x = g.value(s, p)
                return str(x) if x is not None else ""
            out.append(cls(str(s), v(DCTERMS.title) or str(s), v(SIP.reuseMode) or "reference",
                           v(VOID.uriSpace), v(SIP.rationale), v(VOID.sparqlEndpoint)))
        return sorted(out, key=lambda c: c.iri)


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _key(text: str) -> str:
    """Comparison key for a term: case, spacing, camel case and a plural 's' ignored."""
    k = re.sub(r"[^a-z0-9]", "", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).lower())
    return k[:-1] if k.endswith("s") and len(k) > 3 else k


@dataclass
class GlossaryTerm:
    """A pre-glossary entry: a term the requirements use, and where it was found."""

    label: str
    definition: str = ""
    quote: str = ""

    @property
    def iri(self) -> URIRef:
        return URIRef(f"urn:sip:term:{_slug(self.label)}")

    def triples(self):
        s = self.iri
        yield (s, RDF.type, SIP.GlossaryTerm)
        yield (s, RDFS.label, Literal(self.label, lang="en"))
        if self.definition:
            yield (s, SKOS.definition, Literal(self.definition, lang="en"))
        if self.quote:
            yield (s, SIP.quote, Literal(self.quote))

    @classmethod
    def from_graph(cls, g: Graph) -> list["GlossaryTerm"]:
        out = []
        for s in g.subjects(RDF.type, SIP.GlossaryTerm):
            d, q = g.value(s, SKOS.definition), g.value(s, SIP.quote)
            out.append(cls(str(g.value(s, RDFS.label) or s), str(d) if d else "",
                           str(q) if q else ""))
        return sorted(out, key=lambda t: t.label.lower())


def cq_terms(sparql: str, namespace: str) -> set[str]:
    """Local names a CQ's SPARQL uses from the project namespace (``:X`` or ``<ns X>``)."""
    body = re.sub(r"(?im)^\s*PREFIX\s+\S*\s*<[^>]*>\s*$", "", sparql)
    names = set(re.findall(r"(?<![\w:<>/.-]):([A-Za-z_][\w-]*)", body))
    names |= set(re.findall(r"<" + re.escape(namespace) + r"([\w-]+)>", body))
    return names


# --------------------------------------------------------------------------- #
# Exit criteria
# --------------------------------------------------------------------------- #

@dataclass
class Criterion:
    id: str
    required: bool
    ok: bool
    text: str          # what the criterion asks, as a statement
    fix: str = ""      # what to do when it is not met


@dataclass
class Readiness:
    """Whether scope can be closed. ``ready`` looks at the *required* criteria only;
    advisory ones are reported so a reviewer sees what a NeOn ORSD would still lack."""

    criteria: list[Criterion]

    @property
    def ready(self) -> bool:
        return all(c.ok for c in self.criteria if c.required)

    def as_dict(self) -> dict:
        return {"ready": self.ready,
                "missing": [c.fix for c in self.criteria if c.required and not c.ok],
                "advice": [c.fix for c in self.criteria if not c.required and not c.ok],
                "criteria": [c.__dict__ for c in self.criteria]}


def readiness(spec: Specification, cqs: list, glossary: list[GlossaryTerm],
              reuse: list[ReuseCandidate], namespace: str,
              cq_problems: dict[str, list[str]]) -> Readiness:
    """The scope stage's exit criteria (FR-SCP-03).

    *cq_problems* maps CQ id to what makes it non-executable (``quality.cq.problems``),
    so this module needs no SPARQL engine of its own.
    """
    c: list[Criterion] = []

    def crit(cid, required, ok, text, fix, detail=()):
        c.append(Criterion(cid, required, bool(ok), text,
                           fix + (f": {', '.join(detail)}" if detail else "")))

    crit("SCP-01", True, spec.purpose, "the purpose is stated", "state the purpose")
    crit("SCP-02", True, spec.scope, "the scope (the domain covered) is stated",
         "state the scope")
    crit("SCP-03", True, spec.intended_users, "at least one intended end-user is named",
         "name an intended end-user")
    crit("SCP-04", True, spec.intended_uses, "at least one intended use is named",
         "name an intended use")
    must = [q for q in cqs if getattr(q, "priority", "must") == "must"]
    crit("SCP-05", True, must, "at least one competency question has priority 'must'",
         "add a competency question of priority 'must'")
    broken = sorted(k for k, v in cq_problems.items() if v)
    crit("SCP-06", True, not broken, "every competency question is executable",
         "fix the competency questions that cannot run", broken)
    known = {_key(t.label) for t in glossary}
    used = sorted({n for q in cqs for n in cq_terms(q.sparql, namespace)})
    undefined = [n for n in used if _key(n) not in known]
    crit("SCP-07", False, not undefined,
         "every term a competency question uses is in the pre-glossary",
         "add these terms to the pre-glossary", undefined)
    used_keys = {_key(n) for n in used}
    unused = sorted(t.label for t in glossary if _key(t.label) not in used_keys)
    crit("SCP-08", False, not unused, "every pre-glossary term is used by a competency question",
         "write a competency question for these terms, or drop them as out of scope", unused)
    crit("SCP-09", False, spec.non_functional, "non-functional requirements are stated",
         "state the non-functional requirements")
    crit("SCP-10", False, reuse, "ontologies considered for reuse are recorded",
         "record the ontologies considered for reuse")
    seen, dup = set(), []
    for q in cqs:
        k = re.sub(r"\W+", " ", q.question.lower()).strip()
        (dup.append(q.id) if k in seen else seen.add(k))
    crit("SCP-11", False, not dup, "no two competency questions ask the same thing",
         "remove the duplicate competency questions", dup)
    return Readiness(c)


# --------------------------------------------------------------------------- #
# The ORSD as a document
# --------------------------------------------------------------------------- #

def render_markdown(project: str, spec: Specification, cqs: list,
                    glossary: list[GlossaryTerm], reuse: list[ReuseCandidate],
                    ready: Readiness) -> str:
    """The specification in the layout of NeOn's ORSD template."""
    def items(xs):
        return "\n".join(f"* {x}" for x in xs) if xs else "_not stated_"

    lines = [f"# Ontology Requirements Specification: {project}", "",
             f"**Ready to close scope:** {'yes' if ready.ready else 'no'}", "",
             "## 1. Purpose", "", spec.purpose or "_not stated_", "",
             "## 2. Scope", "", spec.scope or "_not stated_", "",
             "## 3. Implementation language", "", spec.implementation_language or "_not stated_",
             "", "## 4. Intended end-users", "", items(spec.intended_users), "",
             "## 5. Intended uses", "", items(spec.intended_uses), "",
             "## 6. Ontology requirements", "", "### a. Non-functional requirements", "",
             items(spec.non_functional), "",
             "### b. Functional requirements: competency questions", ""]
    if cqs:
        lines += ["| id | priority | question | expectation |", "|---|---|---|---|"]
        order = {"must": 0, "should": 1, "may": 2}
        for q in sorted(cqs, key=lambda q: (order.get(q.priority, 3), q.id)):
            lines.append(f"| {q.id} | {q.priority} | {q.question} | `{q.expectation}` |")
    else:
        lines.append("_none_")
    lines += ["", "## 7. Pre-glossary of terms", ""]
    lines += [f"* **{t.label}**" + (f": {t.definition}" if t.definition else "")
              for t in glossary] or ["_none_"]
    lines += ["", "## 8. Reuse candidates", ""]
    if reuse:
        lines += ["| resource | IRI | mode | rationale |", "|---|---|---|---|"]
        lines += [f"| {r.title} | <{r.iri}> | {r.mode} | {r.rationale} |" for r in reuse]
    else:
        lines.append("_none considered_")
    lines += ["", "## Exit criteria", "", "| id | kind | met | criterion |", "|---|---|---|---|"]
    lines += [f"| {c.id} | {'required' if c.required else 'advisory'} | "
              f"{'yes' if c.ok else 'no'} | {c.text} |" for c in ready.criteria]
    return "\n".join(lines) + "\n"
