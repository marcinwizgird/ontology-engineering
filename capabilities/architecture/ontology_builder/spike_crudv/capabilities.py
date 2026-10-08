"""VocBench 3's CRUDV capability algebra, in dependency-free Python.

This is a **working port** of the authorization policy that VocBench 3 evaluates
as Prolog (tuProlog on the server, jsprolog in the browser). It is the reference
implementation for ``ontology_builder.governance.capabilities`` — see
``../GOVERNANCE_FOUNDATION.md`` §2.1.

Source of the semantics: ``vocbench3/src/app/utils/AuthorizationEvaluator.ts``,
the ``tbox`` and ``jsPrologSupport`` string constants, transcribed rule by rule.
The original::

    auth(TOPIC, CRUDVRequest) :-
        chk_capability(TOPIC, CRUDV),
        resolveCRUDV(CRUDVRequest, CRUDV).

    resolveCRUDV(Request, Granted) :- char_subset(Request, Granted).
    covered(Subj, resource)      :- role(Subj).
    covered(objectProperty, property).            % … and the other three
    covered(skosOrderedCollection, skosCollection).
    covered(Role, Role).

**Why this does not need a Prolog engine.** The policy is a fixed, non-recursive
rule set over ground terms with a bounded depth of two. There is no unbounded
search, no backtracking over an open database, and no rule whose head is derived
by another rule more than one level down. Every rule becomes one Python
predicate; ``chk_capability`` becomes an ordered ``any(...)`` over them. The
whole thing is ~200 lines and runs in microseconds without the 300 KB jsprolog
dependency that VocBench ships to the browser.

Three behaviours are load-bearing and easy to lose in a naive port; each has a
test in ``test_capabilities.py``:

1. **Grants may contain wildcards.** ``capability(rdf(_,_), "R")`` is a fact in
   the database, so Prolog unification lets it satisfy *any* two-argument ``rdf``
   goal. A port that only walks the rules and forgets that grants unify too will
   silently deny the Lurker everything.
2. **``rdf(sparql, support)`` is cut.** The original rule ends with ``!``, so a
   broad ``rdf`` grant does **not** confer SPARQL-endpoint access. Dropping the
   cut widens the policy.
3. **CRUDV is a subset test on the *request*.** ``resolveCRUDV`` asks whether the
   requested letters are a subset of the granted ones — not the other way round.
   Inverting it turns "may read" into "may do everything".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "Term", "parse_term", "Capability", "parse_capability", "CapabilitySet",
    "Subject", "Decision", "DEFAULT_ROLES",
]

OPS = "CRUDV"  # Create · Retrieve · Update · Delete · Validate


# --------------------------------------------------------------------------- #
# Terms
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Term:
    """A ground (or wildcard) term: ``rdf``, ``rdf(cls)``, ``rdf(cls, taxonomy)``,
    ``rdf(concept, lexicalization("en,fr"))``.

    ``functor == "_"`` is the Prolog anonymous variable and matches anything.
    """

    functor: str
    args: tuple["Term", ...] = ()

    @property
    def arity(self) -> int:
        return len(self.args)

    @property
    def is_wildcard(self) -> bool:
        return self.functor == "_"

    def __str__(self) -> str:
        if not self.args:
            return self.functor
        return f"{self.functor}({', '.join(str(a) for a in self.args)})"


_TOKEN = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*|"[^"]*"|[(),])')


def parse_term(text: str) -> Term:
    """Parse ``rdf(concept, lexicalization("en,fr"))`` into a :class:`Term`.

    Quoted strings become atoms with the quotes stripped, which is how the
    language-coverage argument is carried.
    """
    pos = 0

    def tok() -> str | None:
        nonlocal pos
        m = _TOKEN.match(text, pos)
        if not m:
            return None
        pos = m.end()
        return m.group(1)

    def peek() -> str | None:
        m = _TOKEN.match(text, pos)
        return m.group(1) if m else None

    def term() -> Term:
        name = tok()
        if name is None:
            raise ValueError(f"unexpected end of term in {text!r}")
        if name.startswith('"'):
            return Term(name[1:-1])
        if peek() != "(":
            return Term(name)
        tok()  # consume "("
        args = [term()]
        while peek() == ",":
            tok()
            args.append(term())
        if tok() != ")":
            raise ValueError(f"unbalanced parentheses in {text!r}")
        return Term(name, tuple(args))

    t = term()
    if text[pos:].strip().rstrip("."):
        raise ValueError(f"trailing input {text[pos:]!r} in {text!r}")
    return t


def match(a: Term, b: Term) -> bool:
    """Prolog-style unification restricted to ground terms plus ``_``.

    Symmetric on purpose: wildcards occur both in the rule heads (goal side) and
    in stored grants such as ``capability(rdf(_,_), "R")``.
    """
    if a.is_wildcard or b.is_wildcard:
        return True
    return (a.functor == b.functor
            and a.arity == b.arity
            and all(match(x, y) for x, y in zip(a.args, b.args)))


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Capability:
    """A granted capability: a topic term plus the operations allowed on it."""

    topic: Term
    ops: frozenset[str]

    def __post_init__(self) -> None:
        bad = self.ops - set(OPS)
        if bad:
            raise ValueError(f"unknown operations {sorted(bad)}; expected {OPS}")

    def __str__(self) -> str:
        order = "".join(o for o in OPS if o in self.ops)
        return f'capability({self.topic}, "{order}")'


_CAP = re.compile(r'^\s*(?:capability|auth)\(\s*(.+?)\s*,\s*"([CRUDV]*)"\s*\)\s*\.?\s*$')


def parse_capability(text: str) -> Capability:
    """Parse ``capability(rdf(concept), "CRUD")`` — VocBench's own wire format.

    ``auth(...)`` is accepted too, so an action goal from
    ``AuthorizationEvaluator.actionAuthGoalMap`` can be parsed with the same
    function and used as a *request*.
    """
    m = _CAP.match(text)
    if not m:
        raise ValueError(f"not a capability expression: {text!r}")
    return Capability(parse_term(m.group(1)), frozenset(m.group(2)))


# --------------------------------------------------------------------------- #
# The policy — one Python predicate per Prolog clause
# --------------------------------------------------------------------------- #

#: ``role/1`` — the subjects a grant on ``resource`` covers.
ROLES: frozenset[str] = frozenset({
    "cls", "individual", "property", "objectProperty", "datatypeProperty",
    "annotationProperty", "ontologyProperty", "ontology", "dataRange",
    "concept", "conceptScheme", "xLabel", "skosCollection",
    "skosOrderedCollection", "ontolexForm", "ontolexLexicalEntry",
    "limeLexicon", "decompComponent",
})

#: ``vocabulary/2`` — subject → the vocabulary a blanket grant can cover it with.
VOCABULARY: dict[str, str] = {
    "concept": "skos", "conceptScheme": "skos", "skosCollection": "skos",
    "ontolexForm": "ontolex", "ontolexLexicalEntry": "ontolex",
    "limeLexicon": "ontolex", "decompComponent": "ontolex",
}

#: ``covered/2`` specialisations, beyond reflexivity and the ``resource`` rule.
SPECIALISES: dict[str, str] = {
    "objectProperty": "property",
    "datatypeProperty": "property",
    "annotationProperty": "property",
    "ontologyProperty": "property",
    "skosOrderedCollection": "skosCollection",
}

#: Subjects a bare ``rdf(lexicalization)`` grant covers directly.
LEXICAL_SUBJECTS: frozenset[str] = frozenset({
    "xLabel", "ontolexForm", "ontolexLexicalEntry", "limeLexicon",
})


def covered(subject: Term, available: Term) -> bool:
    """``covered/2``: is *subject* covered by a grant written for *available*?"""
    if available.is_wildcard or subject.is_wildcard:
        return True
    if match(subject, available):                      # covered(Role, Role).
        return True
    if available.functor == "resource" and not available.args:
        return subject.functor in ROLES                # covered(Subj, resource) :- role(Subj).
    return SPECIALISES.get(subject.functor) == available.functor


def _langs(term: Term) -> set[str]:
    """``lexicalization("en,fr")`` → ``{"en", "fr"}``; bare form → ``set()``."""
    if not term.args:
        return set()
    return {p.strip() for p in term.args[0].functor.split(",") if p.strip()}


def _lang_ok(requested: Term, granted: Term) -> bool:
    """``resolveLANG/2``: requested languages must be a subset of the coverage."""
    req, cov = _langs(requested), _langs(granted)
    if not cov:      # a grant with no language restriction covers every language
        return True
    return req <= cov


@dataclass
class CapabilitySet:
    """A resolved set of grants, with the derivation rules of ``chk_capability``."""

    capabilities: tuple[Capability, ...] = ()
    _cache: dict[tuple[str, str], bool] = field(default_factory=dict, repr=False)

    @classmethod
    def parse(cls, expressions: Iterable[str]) -> "CapabilitySet":
        return cls(tuple(parse_capability(e) for e in expressions))

    def __or__(self, other: "CapabilitySet") -> "CapabilitySet":
        """Union — how a user's several roles combine into one grant set."""
        return CapabilitySet(self.capabilities + other.capabilities)

    # -- the rules ---------------------------------------------------------- #
    def _grants_for(self, topic: Term) -> list[Capability]:
        """Grants whose stored topic unifies with *topic* (rule 1: direct)."""
        return [c for c in self.capabilities if match(topic, c.topic)]

    def _derived_grants(self, goal: Term) -> list[Capability]:
        """Every grant that satisfies *goal* through some ``chk_capability`` clause."""
        area = goal.functor
        out: list[Capability] = []

        # chk_capability(rdf(sparql,support), C) :- !, capability(rdf(sparql,support), C).
        # The cut: only an exact grant confers it. No broader rdf grant applies.
        if (area == "rdf" and goal.arity == 2
                and goal.args[0].functor == "sparql"
                and goal.args[1].functor == "support"):
            return [c for c in self.capabilities
                    if c.topic.functor == "rdf" and c.topic.arity == 2
                    and c.topic.args[0].functor == "sparql"
                    and c.topic.args[1].functor == "support"]

        # chk_capability(TOPIC, C) :- capability(TOPIC, C).
        out += self._grants_for(goal)

        # chk_capability(rdf(_), C)   :- chk_capability(rdf, C).
        # chk_capability(rdf(_,_), C) :- chk_capability(rdf, C).
        # (and the same shape for rbac/1,2 and cform/1,2)
        if goal.arity in (1, 2) and area in ("rdf", "rbac", "cform"):
            out += self._grants_for(Term(area))

        if area == "rdf" and goal.arity in (1, 2):
            subject = goal.args[0]
            scope = goal.args[1] if goal.arity == 2 else None

            # chk_capability(rdf(Subject[,Scope]), C) :-
            #     capability(rdf(AvailableSubject[,Scope]), C), covered(Subject, AvailableSubject).
            for c in self.capabilities:
                if c.topic.functor != "rdf" or c.topic.arity != goal.arity:
                    continue
                if not covered(subject, c.topic.args[0]):
                    continue
                if scope is not None and not match(scope, c.topic.args[1]):
                    continue
                out.append(c)

            # chk_capability(rdf(SKOSELEMENT[,_]), C) :-
            #     capability(rdf(skos), C), vocabulary(SKOSELEMENT, skos).
            vocab = VOCABULARY.get(subject.functor)
            if vocab:
                out += [c for c in self.capabilities
                        if c.topic.functor == "rdf" and c.topic.arity == 1
                        and c.topic.args[0].functor == vocab]

            # Lexicalization roll-ups.
            if scope is not None and scope.functor == "lexicalization":
                # rdf(Subject, lexicalization(LANG)) <- rdf(Available, lexicalization(COV))
                for c in self.capabilities:
                    if (c.topic.functor == "rdf" and c.topic.arity == 2
                            and c.topic.args[1].functor == "lexicalization"
                            and covered(subject, c.topic.args[0])
                            and _lang_ok(scope, c.topic.args[1])):
                        out.append(c)
                # rdf(_, lexicalization(LANG)) <- rdf(lexicalization(COV))
                for c in self.capabilities:
                    if (c.topic.functor == "rdf" and c.topic.arity == 1
                            and c.topic.args[0].functor == "lexicalization"
                            and _lang_ok(scope, c.topic.args[0])):
                        out.append(c)

            # rdf(xLabel(LANG)[,_]) <- rdf(lexicalization(COV))
            if subject.functor == "xLabel":
                for c in self.capabilities:
                    if (c.topic.functor == "rdf" and c.topic.arity == 1
                            and c.topic.args[0].functor == "lexicalization"
                            and _lang_ok(subject, c.topic.args[0])):
                        out.append(c)

            # rdf(xLabel|ontolexForm|ontolexLexicalEntry|limeLexicon [,_])
            #     <- rdf(lexicalization)
            if subject.functor in LEXICAL_SUBJECTS:
                out += [c for c in self.capabilities
                        if c.topic.functor == "rdf" and c.topic.arity == 1
                        and c.topic.args[0].functor == "lexicalization"
                        and not c.topic.args[0].args]

            # rdf(_, notes) <- rdf(notes)
            if scope is not None and scope.functor == "notes":
                out += [c for c in self.capabilities
                        if c.topic.functor == "rdf" and c.topic.arity == 1
                        and c.topic.args[0].functor == "notes"]

        return out

    # -- the entry point ---------------------------------------------------- #
    def satisfies(self, goal: Term, ops: str | Iterable[str]) -> bool:
        """``auth(goal, ops)`` — are *all* requested operations granted?

        Mirrors ``resolveCRUDV(Request, Granted) :- char_subset(Request, Granted)``
        with one deliberate strengthening: VocBench requires a *single* grant to
        carry every requested letter, because Prolog binds one ``CRUDV`` per
        solution. We keep that, because relaxing it would let ``"CD"`` be
        satisfied by a ``C`` grant plus an unrelated ``D`` grant on a different
        topic — which is not what the author of the role intended.
        """
        want = frozenset(ops)
        if not want:
            raise ValueError("no operations requested")
        key = (str(goal), "".join(sorted(want)))
        hit = self._cache.get(key)
        if hit is None:
            hit = any(want <= c.ops for c in self._derived_grants(goal))
            self._cache[key] = hit
        return hit

    def authorize(self, expression: str) -> bool:
        """``satisfies`` from a VocBench goal string, e.g. ``auth(rdf(cls), "C")``."""
        req = parse_capability(expression)
        return self.satisfies(req.topic, req.ops)


# --------------------------------------------------------------------------- #
# Subject, project state and the full decision
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Subject:
    """The principal a decision is made for — a person or a machine account."""

    id: str
    is_admin: bool = False
    #: Grants resolved from the subject's roles for the project in question.
    grants: CapabilitySet = field(default_factory=CapabilitySet)
    #: Languages from the ProjectUserBinding; empty tuple == unrestricted.
    languages: tuple[str, ...] = ()
    is_machine: bool = False


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


def authorize(subject: Subject,
              goal: str,
              *,
              resource_role: str | None = None,
              value_language: str | None = None,
              project_read_only: bool = False) -> Decision:
    """The full policy, in the order ``AuthorizationEvaluator.isGaolAuthorized`` applies it.

    1. read-only project blocks C/U/D on ``rdf`` goals — for everyone, admins included;
    2. anonymous subjects are denied;
    3. admins are allowed;
    4. the ProjectUserBinding's language list is checked against the value's tag;
    5. ``%resource_role%`` is substituted;
    6. the capability algebra decides.
    """
    req = parse_capability(goal.replace("%resource_role%", resource_role or "_"))

    if project_read_only and req.topic.functor == "rdf" and (req.ops & set("CUD")):
        return Decision(False, "project is read-only")

    if not subject.id:
        return Decision(False, "no authenticated subject")

    if subject.is_admin:
        return Decision(True, "administrator")

    if value_language and subject.languages:
        if value_language.lower() not in {l.lower() for l in subject.languages}:
            return Decision(
                False,
                f"binding restricts editing to {list(subject.languages)}; "
                f"value is tagged {value_language!r}")

    if "%resource_role%" in goal and resource_role is None:
        raise ValueError(
            "goal depends on the resource role, but no resource_role was given")

    if subject.grants.satisfies(req.topic, req.ops):
        return Decision(True, f"granted by {req.topic}")
    return Decision(False, f"no grant satisfies {req}")


# --------------------------------------------------------------------------- #
# The eight default roles, as data
# --------------------------------------------------------------------------- #
DEFAULT_ROLES: dict[str, tuple[str, ...]] = {
    # Project-local administrator.
    "ProjectManager": (
        'capability(rdf(_,_), "CRUDV")', 'capability(rdf(_), "CRUDV")',
        'capability(rdf, "CRUDV")',
        'capability(pm(project,_), "CRUD")', 'capability(rbac(_,_), "CRUD")',
        'capability(um(user,_), "CRUD")', 'capability(cform, "CRUD")',
        'capability(customService(_,_), "CRUD")',
        'capability(invokableReporter(_,_), "CRUD")',
    ),
    # Axiom-level OWL editing.
    "OntologyEditor": (
        'capability(rdf(cls,_), "CRUD")', 'capability(rdf(cls), "CRUD")',
        'capability(rdf(property,_), "CRUD")', 'capability(rdf(property), "CRUD")',
        'capability(rdf(individual,_), "CRUD")', 'capability(rdf(individual), "CRUD")',
        'capability(rdf(datatype,_), "CRUD")', 'capability(rdf(datatype), "CRUD")',
        'capability(rdf(dataRange), "CRUD")',
        'capability(rdf(import), "CRUD")', 'capability(rdf(code), "R")',
        'capability(rdf(resource,_), "R")', 'capability(rdf(resource), "R")',
    ),
    # SKOS work, deliberately without OWL axiom capabilities.
    "ThesaurusEditor": (
        'capability(rdf(skos), "CRUD")',
        'capability(rdf(concept,_), "CRUD")', 'capability(rdf(conceptScheme,_), "CRUD")',
        'capability(rdf(skosCollection,_), "CRUD")',
        'capability(rdf(xLabel), "CRUD")', 'capability(rdf(xLabel,_), "CRUD")',
        'capability(rdf(notes), "CRUD")', 'capability(rdf(lexicalization), "CRUD")',
        'capability(rdf(resource,_), "R")', 'capability(rdf(resource), "R")',
        'capability(rdf(code), "R")',
    ),
    # Labels only. Language restriction lives on the binding, not the role.
    "Lexicographer": (
        'capability(rdf(lexicalization), "CRUD")',
        'capability(rdf(_,notes), "CRUD")',
        'capability(rdf(resource,_), "R")', 'capability(rdf(resource), "R")',
        'capability(rdf(code), "R")',
    ),
    # Alignment only.
    "Mapper": (
        'capability(rdf(resource,alignment), "CRUD")',
        'capability(rdf(_,alignment), "CRUD")',
        'capability(rdf(resource,_), "R")', 'capability(rdf(resource), "R")',
        'capability(rdf(code), "R")',
    ),
    # Reads everything, validates everything, changes nothing directly.
    "Validator": (
        'capability(rdf(_,_), "RV")', 'capability(rdf(_), "RV")',
        'capability(rdf, "RV")', 'capability(rdf(code), "RV")',
    ),
    # The SPARQL power user.
    "RDFGeek": (
        'capability(rdf(_,_), "CRUD")', 'capability(rdf(_), "CRUD")',
        'capability(rdf, "CRUD")',
        'capability(rdf(sparql,support), "CRUD")',
        'capability(customService(_,_), "CRUD")',
        'capability(invokableReporter(_,_), "CRUD")',
    ),
    # Read-only.
    "Lurker": (
        'capability(rdf(_,_), "R")', 'capability(rdf(_), "R")', 'capability(rdf, "R")',
    ),
}


def role_grants(*role_names: str) -> CapabilitySet:
    """Resolve one or more default role names into a single grant set."""
    exprs: list[str] = []
    for name in role_names:
        try:
            exprs.extend(DEFAULT_ROLES[name])
        except KeyError:
            raise KeyError(f"unknown role {name!r}; "
                           f"known: {sorted(DEFAULT_ROLES)}") from None
    return CapabilitySet.parse(exprs)
