"""Chapter 4 problem-set support — axiomatisation under OWL 2 profile constraints.

Provided code for ``05_assignment.ipynb``. The student builds the grader, the
Claude axiomatiser and the module-building agent in the notebook; this module
supplies what a real project would already have in its codebase:

* the **signature** of the Mopane Ridge Conservancy Monitoring Ontology (an
  extension of Keet's African Wildlife Ontology, Example 4.1) and a small,
  structured **axiom language** that compiles to real OWL 2 triples;
* the **OWL 2 profile table** for that language (§4.2.2) — and an independent,
  RDF-level profile checker (:func:`graph_profiles`) that validates it;
* the **requirements corpus** — ecologists' requirements in English, each bound
  to the profile of the system that will consume it, with gold axioms, a fixed
  train / dev / test split by item, and *escalation* items whose faithful axiom
  the target profile cannot express;
* **entailment probes** — tiny competency tests checked with the OWL 2 RL
  reasoner (owlrl), the chapter's own engine;
* :func:`equivalent` and :func:`diagnose` for grading and naming mistakes, and
  the guidelines a scorer reports (:data:`AXIOM_RULEBOOK`);
* the **module workspace and tools** the builder agent acts through;
* the **construction MDP** (:class:`AxiomConstructionMDP`): unlike an
  evidence-gathering MDP, its actions *change the artefact*, and its reward is
  entailment coverage minus profile violations.

The profile table covers only the axiom shapes of this language, with a named
class on the left-hand side. For those shapes it follows the W3C *OWL 2 Web
Ontology Language Profiles* specification; it is not a general profile
validator (use the OWL API's profile checker for that).
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from typing import Iterable

from rdflib import OWL, RDF, RDFS, XSD, BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

EX = Namespace("http://example.org/mopane-ridge/monitoring#")

__all__ = [
    "EX", "SIGNATURE", "signature_text", "AXIOM_FORMAT", "OPERATORS",
    "Axiom", "AxiomFormatError",
    "PROFILES", "PROFILE_TABLE", "profiles_of", "in_profile", "profile_table_text",
    "axiom_to_graph", "axioms_to_graph", "graph_profiles", "module_profiles",
    "Probe", "probe_holds", "coverage",
    "Requirement", "REQUIREMENTS", "requirement", "build_dataset", "validate_gold",
    "equivalent", "diagnose", "AXIOM_RULEBOOK",
    "Brief", "BRIEFS", "ModuleWorkspace", "build_module_tools", "CONSTRUCTION_TOOLS",
    "BuildState", "AxiomConstructionMDP",
]


# --------------------------------------------------------------------------- #
# The signature the axiomatiser must use
# --------------------------------------------------------------------------- #
#: role -> {name: gloss}. The gold axioms use exactly these names.
SIGNATURE: dict[str, dict[str, str]] = {
    "class": {
        "Animal": "an animal", "Herbivore": "an animal that eats only plants or plant parts",
        "Carnivore": "an animal that eats animals", "Omnivore": "an animal that eats both",
        "Giraffe": "a giraffe", "Lion": "a lion", "Leopard": "a leopard",
        "Impala": "an impala", "Elephant": "an elephant", "Warthog": "a warthog",
        "RockDassie": "a rock dassie (rock hyrax)",
        "CollaredAnimal": "an animal fitted with a GPS collar",
        "Plant": "a plant", "PlantPart": "a part of a plant", "Tree": "a tree",
        "Branch": "a branch", "Twig": "a twig", "Leaf": "a leaf", "Grass": "grass",
        "Sighting": "a recorded observation of an animal",
        "CameraTrap": "a motion-triggered camera", "GpsCollar": "a GPS tracking collar",
        "Ranger": "a field ranger", "Patrol": "a ranger patrol",
        "Zone": "a management zone of the conservancy",
        "ProtectedZone": "a zone closed to vehicles and visitors",
        "Waterhole": "a waterhole",
    },
    "property": {
        "eats": "x eats y", "preysOn": "x preys on (hunts) y",
        "isPartOf": "x is part of y", "hasPart": "x has part y",
        "locatedIn": "x is located in zone y", "recordedBy": "sighting x was recorded by device y",
        "sightingOf": "sighting x is a sighting of y", "wearsCollar": "x wears collar y",
        "assignedTo": "ranger x is assigned to zone y", "hasMember": "patrol x has member y",
        "memberOf": "x is a member of patrol y",
    },
    "individual": {
        "Nala": "a lioness in the monitoring programme", "Kgosi": "an elephant bull",
        "Trap14": "camera trap number 14", "NorthSector": "the northern management zone",
    },
}


def signature_text() -> str:
    """The signature as the axiomatiser sees it: one name per line, grouped by role."""
    lines = []
    for role, heading in (("class", "Classes"), ("property", "Object properties"),
                          ("individual", "Individuals")):
        lines.append(f"{heading}:")
        lines += [f"  {name}: {gloss}" for name, gloss in SIGNATURE[role].items()]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The axiom language
# --------------------------------------------------------------------------- #
#: operator -> (JSON fields it needs, Manchester-style template)
_OPERATORS: dict[str, tuple[tuple[str, ...], str]] = {
    "subclassof": (("subject", "filler"), "{subject} SubClassOf {filler}"),
    "type": (("subject", "filler"), "{subject} Type {filler}"),
    "disjoint": (("subject", "filler"), "{subject} DisjointWith {filler}"),
    "some": (("subject", "property", "filler"), "{subject} SubClassOf {property} some {filler}"),
    "only": (("subject", "property", "filler"), "{subject} SubClassOf {property} only {filler}"),
    "value": (("subject", "property", "filler"), "{subject} SubClassOf {property} value {filler}"),
    "max1": (("subject", "property", "filler"), "{subject} SubClassOf {property} max 1 {filler}"),
    "unionof": (("subject", "filler"), "{subject} SubClassOf {filler}"),
    "domain": (("property", "filler"), "{property} Domain {filler}"),
    "range": (("property", "filler"), "{property} Range {filler}"),
    "transitive": (("property",), "{property} Characteristics Transitive"),
    "functional": (("property",), "{property} Characteristics Functional"),
    "inverse": (("property", "filler"), "{property} InverseOf {filler}"),
    "subpropertyof": (("property", "filler"), "{property} SubPropertyOf {filler}"),
    "escalate": ((), "ESCALATE (not expressible in the target profile)"),
}
OPERATORS: tuple[str, ...] = tuple(_OPERATORS)

#: The output contract, in words — for signatures, prompts and tools.
AXIOM_FORMAT = """\
One JSON object, nothing else. "operator" is one of the operators below; the other
fields are names from the signature.
  {"operator": "subclassof", "subject": C, "filler": D}          C SubClassOf D
  {"operator": "type", "subject": i, "filler": C}                individual i is a C
  {"operator": "disjoint", "subject": C, "filler": D}            no C is a D
  {"operator": "some", "subject": C, "property": p, "filler": D} C SubClassOf p some D
  {"operator": "only", "subject": C, "property": p, "filler": D} C SubClassOf p only D
  {"operator": "value", "subject": C, "property": p, "filler": i}  C SubClassOf p value i
  {"operator": "max1", "subject": C, "property": p, "filler": D} C SubClassOf p max 1 D
  {"operator": "unionof", "subject": C, "filler": [D1, D2, ...]} C SubClassOf D1 or D2 or ...
  {"operator": "domain", "property": p, "filler": C}             p Domain C
  {"operator": "range", "property": p, "filler": C}              p Range C
  {"operator": "transitive", "property": p}                      p is transitive
  {"operator": "functional", "property": p}                      p is functional
  {"operator": "inverse", "property": p, "filler": q}            p InverseOf q
  {"operator": "subpropertyof", "property": p, "filler": q}      p SubPropertyOf q
  {"operator": "escalate", "reason": "..."}                      the target profile cannot express it"""


class AxiomFormatError(ValueError):
    """The text is not one well-formed axiom of the language."""


@dataclass(frozen=True)
class Axiom:
    """One axiom of the language, structurally. ``filler`` is a tuple for ``unionof``."""

    operator: str
    subject: str = ""
    property: str = ""
    filler: str | tuple[str, ...] = ""

    # -- parsing and printing -------------------------------------------------
    @classmethod
    def parse(cls, value) -> "Axiom":
        """Parse a JSON object (text or dict). Strict: raises :class:`AxiomFormatError`.

        No prose, no code fences — the output contract is part of what is graded.
        """
        if isinstance(value, Axiom):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise AxiomFormatError("empty answer")
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AxiomFormatError(f"not a JSON object ({exc.msg})") from None
        if not isinstance(value, dict):
            raise AxiomFormatError("not a JSON object")
        op = str(value.get("operator", "")).strip().lower()
        if op not in _OPERATORS:
            raise AxiomFormatError(f"unknown operator {op!r}; use one of {', '.join(OPERATORS)}")
        needed, _ = _OPERATORS[op]
        fields: dict = {}
        for name in needed:
            raw = value.get(name)
            if op == "unionof" and name == "filler":
                if (not isinstance(raw, list) or len(raw) < 2
                        or not all(isinstance(x, str) and x.strip() for x in raw)):
                    raise AxiomFormatError("unionof needs a list of at least two class names")
                fields[name] = tuple(x.strip() for x in raw)
            else:
                if not isinstance(raw, str) or not raw.strip():
                    raise AxiomFormatError(f"operator {op!r} needs a non-empty {name!r}")
                fields[name] = raw.strip()
        return cls(op, **fields)

    def to_dict(self) -> dict:
        needed, _ = _OPERATORS[self.operator]
        out = {"operator": self.operator}
        for name in needed:
            value = getattr(self, name)
            out[name] = list(value) if isinstance(value, tuple) else value
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self) -> str:
        _, template = _OPERATORS.get(self.operator, ((), "{operator}?"))
        filler = (" or ".join(self.filler) if isinstance(self.filler, tuple) else self.filler)
        return template.format(subject=self.subject, property=self.property,
                               filler=filler, operator=self.operator)

    # -- names -----------------------------------------------------------------
    def roles(self) -> list[tuple[str, str]]:
        """``(role, name)`` for every name the axiom uses; role is class/property/individual."""
        op, s, p, f = self.operator, self.subject, self.property, self.filler
        if op in ("subclassof", "disjoint"):
            return [("class", s), ("class", f)]
        if op == "type":
            return [("individual", s), ("class", f)]
        if op in ("some", "only", "max1"):
            return [("class", s), ("property", p), ("class", f)]
        if op == "value":
            return [("class", s), ("property", p), ("individual", f)]
        if op == "unionof":
            return [("class", s)] + [("class", x) for x in f]
        if op in ("domain", "range"):
            return [("property", p), ("class", f)]
        if op in ("transitive", "functional"):
            return [("property", p)]
        if op in ("inverse", "subpropertyof"):
            return [("property", p), ("property", f)]
        return []

    def key(self) -> tuple:
        """Canonical form: equal keys mean logically equivalent axioms in this language."""
        if self.operator == "disjoint":
            return (self.operator, frozenset((self.subject, self.filler)))
        if self.operator == "inverse":
            return (self.operator, frozenset((self.property, self.filler)))
        if self.operator == "unionof":
            return (self.operator, self.subject, frozenset(self.filler))
        return (self.operator, self.subject, self.property, self.filler)


# --------------------------------------------------------------------------- #
# Profiles (§4.2.2)
# --------------------------------------------------------------------------- #
PROFILES = ("EL", "QL", "RL")

#: Which OWL 2 profiles admit each axiom shape (named class on the left).
#:
#: * EL: existentials and hasValue, transitivity — but no universals, no
#:   cardinality, no functional or inverse properties, no union.
#: * QL: existentials with a named filler on the right, inverses — but no
#:   universals, hasValue, cardinality, transitivity, functionality or union.
#: * RL: universals, hasValue, max 0/1 cardinality, every property characteristic
#:   used here — but no existential on the right (rules cannot invent the
#:   anonymous individual it asserts) and no union on the right.
PROFILE_TABLE: dict[str, frozenset[str]] = {
    "subclassof": frozenset(PROFILES), "type": frozenset(PROFILES),
    "disjoint": frozenset(PROFILES), "domain": frozenset(PROFILES),
    "range": frozenset(PROFILES), "subpropertyof": frozenset(PROFILES),
    "some": frozenset({"EL", "QL"}),
    "only": frozenset({"RL"}),
    "value": frozenset({"EL", "RL"}),
    "max1": frozenset({"RL"}),
    "unionof": frozenset(),
    "transitive": frozenset({"EL", "RL"}),
    "functional": frozenset({"RL"}),
    "inverse": frozenset({"QL", "RL"}),
    "escalate": frozenset(),
}


def profiles_of(axiom: Axiom) -> set[str]:
    """The profiles that admit this axiom (empty for ``escalate`` and ``unionof``)."""
    return set(PROFILE_TABLE.get(axiom.operator, frozenset()))


def in_profile(axiom: Axiom, profile: str) -> bool:
    return profile.strip().upper() in profiles_of(axiom)


def profile_table_text() -> str:
    """The profile table as text — what a 'profile card' in a prompt would say."""
    lines = ["Which OWL 2 profiles allow each operator (named class on the left):"]
    for op in OPERATORS:
        if op == "escalate":
            continue
        allowed = sorted(PROFILE_TABLE[op])
        lines.append(f"  {op:14s} {', '.join(allowed) if allowed else 'none (OWL 2 DL only)'}")
    for profile in PROFILES:
        banned = [op for op in OPERATORS if op != "escalate" and profile not in PROFILE_TABLE[op]]
        lines.append(f"{profile} forbids: {', '.join(banned)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Compiling to OWL 2 (RDF mapping), and the RDF-level profile checker
# --------------------------------------------------------------------------- #
def _declare(g: Graph, axiom: Axiom) -> None:
    kinds = {"class": OWL.Class, "property": OWL.ObjectProperty,
             "individual": OWL.NamedIndividual}
    for role, name in axiom.roles():
        g.add((EX[name], RDF.type, kinds[role]))


def _restriction(g: Graph, prop: str) -> BNode:
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, EX[prop]))
    return r


def axiom_to_graph(axiom: Axiom, graph: Graph | None = None) -> Graph:
    """Compile one axiom to OWL 2 triples (the standard RDF mapping)."""
    g = graph if graph is not None else Graph()
    g.bind("", EX)
    g.bind("owl", OWL)
    op, s, p, f = axiom.operator, axiom.subject, axiom.property, axiom.filler
    if op == "escalate":
        return g
    _declare(g, axiom)
    if op == "subclassof":
        g.add((EX[s], RDFS.subClassOf, EX[f]))
    elif op == "type":
        g.add((EX[s], RDF.type, EX[f]))
    elif op == "disjoint":
        g.add((EX[s], OWL.disjointWith, EX[f]))
    elif op in ("some", "only", "value", "max1"):
        r = _restriction(g, p)
        if op == "some":
            g.add((r, OWL.someValuesFrom, EX[f]))
        elif op == "only":
            g.add((r, OWL.allValuesFrom, EX[f]))
        elif op == "value":
            g.add((r, OWL.hasValue, EX[f]))
        else:
            g.add((r, OWL.maxQualifiedCardinality, Literal(1, datatype=XSD.nonNegativeInteger)))
            g.add((r, OWL.onClass, EX[f]))
        g.add((EX[s], RDFS.subClassOf, r))
    elif op == "unionof":
        u = BNode()
        g.add((u, RDF.type, OWL.Class))
        Collection(g, (lst := BNode()), [EX[x] for x in f])
        g.add((u, OWL.unionOf, lst))
        g.add((EX[s], RDFS.subClassOf, u))
    elif op == "domain":
        g.add((EX[p], RDFS.domain, EX[f]))
    elif op == "range":
        g.add((EX[p], RDFS.range, EX[f]))
    elif op == "transitive":
        g.add((EX[p], RDF.type, OWL.TransitiveProperty))
    elif op == "functional":
        g.add((EX[p], RDF.type, OWL.FunctionalProperty))
    elif op == "inverse":
        g.add((EX[p], OWL.inverseOf, EX[f]))
    elif op == "subpropertyof":
        g.add((EX[p], RDFS.subPropertyOf, EX[f]))
    return g


def axioms_to_graph(axioms: Iterable[Axiom]) -> Graph:
    g = Graph()
    for a in axioms:
        axiom_to_graph(a, g)
    return g


def _superclass_profiles(g: Graph, node) -> set[str]:
    """Profiles admitting ``node`` as a superclass expression (atomic subclass)."""
    if isinstance(node, URIRef):
        return set(PROFILES)
    if (node, OWL.unionOf, None) in g:
        return set()                                  # union on the right: none of the three
    filler = g.value(node, OWL.someValuesFrom)
    if filler is not None:
        return {"EL", "QL"} if isinstance(filler, URIRef) else {"EL"}
    if (node, OWL.allValuesFrom, None) in g:
        return {"RL"}
    if (node, OWL.hasValue, None) in g:
        return {"EL", "RL"}
    for card in (OWL.maxQualifiedCardinality, OWL.maxCardinality):
        n = g.value(node, card)
        if n is not None:
            return {"RL"} if int(n) in (0, 1) else set()
    return set()


def graph_profiles(g: Graph) -> set[str]:
    """Which profiles an RDF graph of axioms fits, read from the triples themselves.

    Independent of :data:`PROFILE_TABLE` on purpose: :func:`validate_gold`
    checks the two agree on every gold axiom, so the table cannot drift from
    the OWL it compiles to. Global restrictions (simple properties) are *not*
    checked here — that is Problem A2.
    """
    allowed = set(PROFILES)
    for _, sup in g.subject_objects(RDFS.subClassOf):
        allowed &= _superclass_profiles(g, sup)
    if any(True for _ in g.subjects(RDF.type, OWL.TransitiveProperty)):
        allowed &= {"EL", "RL"}
    if any(True for _ in g.subjects(RDF.type, OWL.FunctionalProperty)):
        allowed &= {"RL"}
    if any(True for _ in g.subject_objects(OWL.inverseOf)):
        allowed &= {"QL", "RL"}
    return allowed


def module_profiles(axioms: Iterable[Axiom]) -> set[str]:
    """The profiles a whole module fits (per-axiom rules only)."""
    return graph_profiles(axioms_to_graph([a for a in axioms if a.operator != "escalate"]))


# --------------------------------------------------------------------------- #
# Entailment probes — competency tests run with the OWL 2 RL reasoner
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Probe:
    """Assert ``facts``, reason, and check ``expect`` was inferred.

    Triples are written ``"subject predicate object"``; ``a`` is rdf:type and
    ``sameAs`` is owl:sameAs. Probes test what the RL reasoner can *derive*,
    so they exist only for axioms with an instance-level consequence (an
    existential ``some`` has none an RL reasoner can show).
    """

    facts: tuple[str, ...]
    expect: str


def _triple(text: str):
    s, p, o = text.split()
    pred = RDF.type if p == "a" else OWL.sameAs if p == "sameAs" else EX[p]
    return EX[s], pred, EX[o]


@functools.lru_cache(maxsize=4096)
def _probe_holds_cached(axiom_keys: tuple, axioms: tuple, probe: Probe) -> bool:
    import owlrl

    g = axioms_to_graph(axioms)
    for fact in probe.facts:
        g.add(_triple(fact))
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    return _triple(probe.expect) in g


def probe_holds(axioms: Iterable[Axiom], probe: Probe) -> bool:
    """Does the OWL 2 RL closure of ``axioms`` + the probe's facts contain its expectation?"""
    axioms = tuple(sorted({a for a in axioms if a.operator != "escalate"}, key=str))
    return _probe_holds_cached(tuple(a.key() for a in axioms), axioms, probe)


def coverage(axioms: Iterable[Axiom], probes: Iterable[Probe]) -> float:
    """Fraction of the probes the axioms satisfy."""
    probes = list(probes)
    axioms = list(axioms)
    if not probes:
        return 0.0
    return sum(probe_holds(axioms, p) for p in probes) / len(probes)


# --------------------------------------------------------------------------- #
# The requirements corpus
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Requirement:
    """One ecologist's requirement, bound to the profile of the system consuming it.

    ``gold`` is the axiom to produce — or ``Axiom("escalate")`` when the
    faithful reading (``faithful``) is outside ``profile``.
    """

    id: str
    split: str
    profile: str
    text: str
    faithful: Axiom
    probe: Probe | None = None

    @property
    def escalate(self) -> bool:
        return not in_profile(self.faithful, self.profile)

    @property
    def gold(self) -> Axiom:
        return Axiom("escalate") if self.escalate else self.faithful


def _R(id, split, profile, text, faithful, facts=None, expect=None):
    probe = Probe(tuple(facts), expect) if expect else None
    return Requirement(id, split, profile, text, faithful, probe)


A_ = Axiom
#: Fixed split by item, balanced by phenomenon: every split has one subclassof,
#: one type, one some, one only (in RL), property axioms, and two escalations.
REQUIREMENTS: list[Requirement] = [
    # --- train ---------------------------------------------------------------
    _R("giraffe-is-herbivore", "train", "EL", "Every giraffe is a herbivore.",
       A_("subclassof", "Giraffe", filler="Herbivore"), ["g a Giraffe"], "g a Herbivore"),
    _R("nala-is-collared", "train", "QL", "Nala is a collared animal.",
       A_("type", "Nala", filler="CollaredAnimal"), [], "Nala a CollaredAnimal"),
    _R("lions-eat-some-herbivore", "train", "EL", "Every lion eats at least one herbivore.",
       A_("some", "Lion", "eats", "Herbivore")),
    _R("giraffes-eat-only-leaves", "train", "RL", "Giraffes eat nothing but leaves.",
       A_("only", "Giraffe", "eats", "Leaf"), ["g a Giraffe", "g eats x"], "x a Leaf"),
    _R("part-of-is-transitive", "train", "EL",
       "A part of a part of something is itself a part of that thing.",
       A_("transitive", property="isPartOf"), ["a isPartOf b", "b isPartOf c"], "a isPartOf c"),
    _R("herbivores-are-not-carnivores", "train", "QL", "No herbivore is a carnivore.",
       A_("disjoint", "Herbivore", filler="Carnivore")),
    _R("carnivores-eat-only-animals", "train", "EL", "Carnivores eat only animals.",
       A_("only", "Carnivore", "eats", "Animal"), ["c a Carnivore", "c eats y"], "y a Animal"),
    _R("one-trap-per-sighting", "train", "QL",
       "A sighting is recorded by at most one camera trap.",
       A_("max1", "Sighting", "recordedBy", "CameraTrap"),
       ["s a Sighting", "s recordedBy t1", "s recordedBy t2", "t1 a CameraTrap",
        "t2 a CameraTrap"], "t1 sameAs t2"),
    # --- dev -----------------------------------------------------------------
    _R("impala-is-herbivore", "dev", "QL", "An impala is a herbivore.",
       A_("subclassof", "Impala", filler="Herbivore"), ["i a Impala"], "i a Herbivore"),
    _R("kgosi-is-elephant", "dev", "EL", "Kgosi is an elephant.",
       A_("type", "Kgosi", filler="Elephant"), [], "Kgosi a Elephant"),
    _R("branches-part-of-some-tree", "dev", "EL", "Every branch is part of some tree.",
       A_("some", "Branch", "isPartOf", "Tree")),
    _R("rangers-only-protected-zones", "dev", "RL",
       "Rangers are assigned to protected zones only.",
       A_("only", "Ranger", "assignedTo", "ProtectedZone"),
       ["r a Ranger", "r assignedTo z"], "z a ProtectedZone"),
    _R("sightings-are-of-animals", "dev", "QL",
       "Whatever a sighting is a sighting of is an animal.",
       A_("range", property="sightingOf", filler="Animal"), ["s sightingOf x"], "x a Animal"),
    _R("membership-is-inverse", "dev", "QL",
       "A patrol has a ranger as a member exactly when that ranger is a member of the patrol.",
       A_("inverse", property="hasMember", filler="memberOf"), ["p hasMember r"], "r memberOf p"),
    _R("warthogs-eat-some-grass", "dev", "RL", "Every warthog eats some grass.",
       A_("some", "Warthog", "eats", "Grass")),
    _R("one-collar-each", "dev", "EL", "Nothing wears more than one collar.",
       A_("functional", property="wearsCollar"),
       ["n wearsCollar c1", "n wearsCollar c2"], "c1 sameAs c2"),
    # --- test ----------------------------------------------------------------
    _R("elephant-is-herbivore", "test", "RL", "Every elephant is a herbivore.",
       A_("subclassof", "Elephant", filler="Herbivore"), ["e a Elephant"], "e a Herbivore"),
    _R("trap14-is-camera-trap", "test", "QL", "Trap14 is a camera trap.",
       A_("type", "Trap14", filler="CameraTrap"), [], "Trap14 a CameraTrap"),
    _R("leopards-eat-some-animal", "test", "QL", "Every leopard eats some animal.",
       A_("some", "Leopard", "eats", "Animal")),
    _R("rock-dassies-eat-only-plants", "test", "RL", "Rock dassies eat only plants.",
       A_("only", "RockDassie", "eats", "Plant"), ["d a RockDassie", "d eats x"], "x a Plant"),
    _R("preying-is-eating", "test", "EL", "Preying on an animal is a way of eating it.",
       A_("subpropertyof", property="preysOn", filler="eats"), ["l preysOn z"], "l eats z"),
    _R("waterholes-in-north-sector", "test", "EL",
       "Every waterhole is located in the North Sector.",
       A_("value", "Waterhole", "locatedIn", "NorthSector"),
       ["w a Waterhole"], "w locatedIn NorthSector"),
    _R("lions-eat-only-animals", "test", "QL", "Lions eat only animals.",
       A_("only", "Lion", "eats", "Animal"), ["l a Lion", "l eats y"], "y a Animal"),
    _R("animals-are-covered", "test", "RL",
       "Every animal is a herbivore, a carnivore or an omnivore.",
       A_("unionof", "Animal", filler=("Herbivore", "Carnivore", "Omnivore"))),
]
del A_

_BY_ID = {r.id: r for r in REQUIREMENTS}


def requirement(req_id: str) -> Requirement:
    return _BY_ID[req_id]


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows (inputs: requirement, profile, vocabulary)."""
    import dspy

    sig = signature_text()
    rows = [
        dspy.Example(id=r.id, split=r.split, requirement=r.text, profile=r.profile,
                     vocabulary=sig, gold_axiom=r.gold, faithful_axiom=r.faithful,
                     probe=r.probe).with_inputs("requirement", "profile", "vocabulary")
        for r in REQUIREMENTS
    ]
    return rows if split == "all" else [r for r in rows if r.split == split]


def validate_gold(owlready: bool = True) -> list[dict]:
    """Check every gold label with the chapter's engines; raise on the first problem.

    * every name is in the signature, in its role;
    * the RDF-level checker and the profile table agree on the faithful axiom;
    * the gold is in the target profile — or, for escalation items, the
      faithful axiom provably is not;
    * the probe holds under OWL 2 RL reasoning with the faithful axiom and
      fails on the empty ontology (so it really tests the axiom);
    * the compiled OWL loads in owlready2.
    """
    import io

    rows = []
    for r in REQUIREMENTS:
        ax = r.faithful
        bad = [(role, n) for role, n in ax.roles() if n not in SIGNATURE[role]]
        assert not bad, f"{r.id}: names outside the signature {bad}"
        graph = axiom_to_graph(ax)
        assert graph_profiles(graph) == profiles_of(ax), f"{r.id}: table and RDF disagree"
        assert r.escalate == (r.profile not in graph_profiles(graph)), r.id
        probe_ok = None
        if r.probe is not None:
            probe_ok = probe_holds([ax], r.probe)
            assert probe_ok, f"{r.id}: the faithful axiom fails its own probe"
            assert not probe_holds([], r.probe), f"{r.id}: the probe holds without the axiom"
        if owlready:
            import owlready2

            world = owlready2.World()
            data = graph.serialize(format="xml").encode("utf-8")
            world.get_ontology("http://example.org/mopane-ridge/monitoring").load(
                fileobj=io.BytesIO(data))
        rows.append({"id": r.id, "split": r.split, "profile": r.profile,
                     "gold": str(r.gold), "faithful": str(ax),
                     "allowed_in": "".join(sorted(profiles_of(ax))) or "-",
                     "probe_ok": probe_ok})
    splits = [r.split for r in REQUIREMENTS]
    assert all(splits.count(s) == 8 for s in ("train", "dev", "test"))
    for s in ("train", "dev", "test"):
        assert sum(r.escalate for r in REQUIREMENTS if r.split == s) == 2, s
    return rows


# --------------------------------------------------------------------------- #
# Grading helpers
# --------------------------------------------------------------------------- #
def equivalent(a: Axiom, b: Axiom) -> bool:
    """Same axiom up to the symmetries of the language (disjointness, inverses, union order)."""
    return Axiom.parse(a).key() == Axiom.parse(b).key()


def diagnose(predicted: Axiom, gold: Axiom) -> str | None:
    """Name the classic Chapter-4 mistake when its shape is recognisable, else ``None``."""
    p, g = predicted, gold
    pair = (p.operator, g.operator)
    if pair in {("type", "subclassof"), ("subclassof", "type")} and p.filler == g.filler:
        return "isa-vs-instance"
    same_slot = (p.subject, p.property, p.filler) == (g.subject, g.property, g.filler)
    if pair == ("only", "some") and same_slot:
        return "some-for-existential"
    if pair == ("some", "only") and same_slot:
        return "only-for-universal"
    if pair in {("domain", "range"), ("range", "domain")} and p.property == g.property:
        return "domain-vs-range"
    if p.operator == g.operator == "subclassof" and (p.subject, p.filler) == (g.filler, g.subject):
        return "direction-of-subsumption"
    if (p.operator == g.operator == "subpropertyof"
            and (p.property, p.filler) == (g.filler, g.property)):
        return "direction-of-subsumption"
    return None


def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("emit-structured-axiom",
             "Answer with exactly one JSON object and nothing else -- no prose, no code "
             "fence -- whose operator is one of the listed operators and which has the "
             "fields that operator needs."),
        Rule("use-the-signature",
             "Use only names from the signature, each in its role: classes as subject or "
             "filler of class axioms, object properties in the property slot, individuals "
             "only as the subject of 'type' or the filler of 'value'. No synonyms, no plurals."),
        Rule("isa-vs-instance",
             "'Every X is a Y' and 'an X is a Y' relate two classes: subclassof. Use 'type' "
             "only when the subject is a named individual such as Nala."),
        Rule("some-for-existential",
             "'at least one', 'some' or 'a' after the verb is an existential restriction: "
             "operator 'some'."),
        Rule("only-for-universal",
             "'only', 'nothing but' and 'exclusively' are a universal restriction: operator "
             "'only'. It does not claim that any value exists."),
        Rule("domain-vs-range",
             "'Whatever has p is a C' is the domain of p; 'whatever something p's is a C' "
             "is the range of p."),
        Rule("direction-of-subsumption",
             "The more specific term is the subject: 'preying is a way of eating' is preysOn "
             "subpropertyof eats, 'every giraffe is a herbivore' is Giraffe subclassof "
             "Herbivore."),
        Rule("respect-profile",
             "Check the operator against the target profile before answering. EL has no only, "
             "max1, functional, inverse or unionof; QL has no only, value, max1, transitive, "
             "functional or unionof; RL has no some and no unionof."),
        Rule("no-silent-weakening",
             "When the faithful axiom is outside the target profile, do not substitute a "
             "different axiom that fits: answer {\"operator\": \"escalate\"} with a reason "
             "naming the construct the profile lacks."),
        Rule("escalate-only-when-inexpressible",
             "Escalate only when the faithful axiom's operator is forbidden in the target "
             "profile; every profile allows subclassof, type, disjoint, domain, range and "
             "subpropertyof."),
        Rule("match-the-requirement",
             "Re-read the requirement: the right subject, property and filler, and nothing "
             "added or dropped."),
    ])


#: The guidelines an axiom scorer reports as violated.
AXIOM_RULEBOOK = _rulebook()


# --------------------------------------------------------------------------- #
# Building a module: briefs, workspace, tools (Part D)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Brief:
    """One module of the ontology, the system that consumes it, and its requirements."""

    profile: str
    module: str
    consumer: str
    requirement_ids: tuple[str, ...]


_CONSUMERS = {
    "EL": ("species-taxonomy",
           "the species taxonomy, classified nightly by an OWL 2 EL reasoner (ELK) "
           "because it must scale to the full regional species list"),
    "QL": ("sightings-access",
           "ontology-based data access over the camera-trap sightings database; "
           "queries are rewritten into SQL, which only OWL 2 QL guarantees"),
    "RL": ("field-report-rules",
           "forward-chaining validation of ranger field reports inside the triple "
           "store, which implements the OWL 2 RL rule set"),
}

#: The three modules the builder agent assembles, from the test requirements.
BRIEFS: dict[str, Brief] = {
    p: Brief(p, _CONSUMERS[p][0], _CONSUMERS[p][1],
             tuple(r.id for r in REQUIREMENTS if r.split == "test" and r.profile == p))
    for p in PROFILES
}


@dataclass
class ModuleWorkspace:
    """The module under construction: axioms (tagged by requirement), escalations, log."""

    brief: Brief
    entries: dict = field(default_factory=dict)        # index -> (requirement_id, Axiom)
    escalations: dict = field(default_factory=dict)    # requirement_id -> reason
    log: object = None
    _next: int = 0

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()

    # -- actions that change the artefact ------------------------------------
    def add(self, requirement_id: str, axiom) -> int:
        if requirement_id not in self.brief.requirement_ids:
            raise KeyError(f"{requirement_id!r} is not in this brief")
        axiom = Axiom.parse(axiom)
        if axiom.operator == "escalate":
            raise ValueError("use escalate(), not add(), to escalate a requirement")
        index, self._next = self._next, self._next + 1
        self.entries[index] = (requirement_id, axiom)
        return index

    def remove(self, index: int) -> Axiom:
        return self.entries.pop(int(index))[1]

    def escalate(self, requirement_id: str, reason: str) -> None:
        if requirement_id not in self.brief.requirement_ids:
            raise KeyError(f"{requirement_id!r} is not in this brief")
        self.escalations[requirement_id] = reason

    # -- reading it back -------------------------------------------------------
    def axioms(self) -> list[Axiom]:
        return [ax for _, ax in self.entries.values()]

    def answer_for(self, requirement_id: str) -> Axiom | None:
        """What the module says for one requirement.

        The artefact is what ships: the most recent axiom still in the module
        for that requirement wins; an escalation counts only when no axiom for
        it remains; ``None`` when the requirement was neither met nor escalated.
        """
        mine = [ax for rid, ax in self.entries.values() if rid == requirement_id]
        if mine:
            return mine[-1]
        if requirement_id in self.escalations:
            return Axiom("escalate")
        return None

    def graph(self) -> Graph:
        return axioms_to_graph(self.axioms())

    def profiles(self) -> set[str]:
        return module_profiles(self.axioms())

    def turtle(self) -> str:
        return self.graph().serialize(format="turtle")


#: The tool names that change the artefact — the construction actions.
CONSTRUCTION_TOOLS = ("add_axiom", "remove_axiom", "escalate_requirement")


def build_module_tools(ws: ModuleWorkspace):
    """The builder agent's tools. Three read, one checks, three change the module."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def read_brief() -> str:
        """Read the module brief: its OWL 2 profile, the system that consumes it, and the
        requirements (id and text) the module must satisfy."""
        return json.dumps({
            "module": ws.brief.module, "profile": ws.brief.profile,
            "consumer": ws.brief.consumer,
            "requirements": [{"id": rid, "text": requirement(rid).text}
                             for rid in ws.brief.requirement_ids]})

    def read_signature() -> str:
        """List the classes, object properties and individuals you may use, and the JSON
        axiom format every axiom must follow."""
        return signature_text() + "\n\nAxiom format:\n" + AXIOM_FORMAT

    def check_axiom(axiom_json: str) -> str:
        """Check a candidate axiom WITHOUT adding it: does it parse, are its names in the
        signature, and which OWL 2 profiles allow it (is it legal in this module)?"""
        ax = Axiom.parse(axiom_json)
        bad = [f"{role} {name}" for role, name in ax.roles() if name not in SIGNATURE[role]]
        allowed = sorted(profiles_of(ax))
        return json.dumps({"axiom": str(ax), "signature_errors": bad,
                           "allowed_in_profiles": allowed,
                           "legal_in_this_module": ws.brief.profile in allowed})

    def add_axiom(requirement_id: str, axiom_json: str) -> str:
        """Add an axiom to the module for one requirement. This changes the artefact."""
        index = ws.add(requirement_id, axiom_json)
        ax = ws.entries[index][1]
        legal = in_profile(ax, ws.brief.profile)
        return json.dumps({"added": index, "axiom": str(ax), "legal_in_this_module": legal,
                           "warning": None if legal else
                           f"outside OWL 2 {ws.brief.profile}; remove it or escalate"})

    def remove_axiom(index: int) -> str:
        """Remove the axiom with this index from the module. This changes the artefact."""
        return json.dumps({"removed": index, "axiom": str(ws.remove(index))})

    def escalate_requirement(requirement_id: str, reason: str) -> str:
        """Record that a requirement cannot be expressed in this module's profile, with the
        reason, for the ontology owner to resolve. Use instead of adding an axiom."""
        ws.escalate(requirement_id, reason)
        return json.dumps({"escalated": requirement_id})

    def show_module() -> str:
        """Show the module as it stands: axioms by index and requirement, the profiles the
        whole module fits (checked on its RDF), and the escalations."""
        return json.dumps({
            "axioms": [{"index": i, "requirement": rid, "axiom": str(ax)}
                       for i, (rid, ax) in ws.entries.items()],
            "module_fits_profiles": sorted(ws.profiles()),
            "escalations": ws.escalations})

    impls = [read_brief, read_signature, check_axiom, add_axiom, remove_axiom,
             escalate_requirement, show_module]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# The construction MDP — actions change the artefact
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BuildState:
    """The partial module (asserted candidate indices) and whether the episode ended."""

    asserted: frozenset[int]
    status: str = "open"          # open | submitted | escalated

    def __str__(self) -> str:  # pragma: no cover - display only
        body = ",".join(str(i) for i in sorted(self.asserted)) or "-"
        return f"{{{body}}}" + {"open": "", "submitted": "!", "escalated": "^"}[self.status]


class AxiomConstructionMDP:
    """Choose which candidate axioms to assert so the requirement's probes hold.

    ========  ================================================================
    S         the axioms asserted so far, and whether the module was submitted
              or the requirement escalated
    A         ``assert:i`` for an unasserted candidate, ``submit``, and —
              when ``escalate_reward`` is given — ``escalate``
    T         deterministic
    R         ``-step_cost`` per assertion; on ``submit``:
              ``coverage - profile_penalty * violations - miss_penalty * (1 - coverage)``,
              where coverage is the fraction of probes the OWL 2 RL reasoner
              confirms; on ``escalate``: ``escalate_reward``
    ========  ================================================================

    The reward is *entailment-based*: an axiom earns credit for what the
    reasoner derives from it, not for looking like the gold answer.
    """

    def __init__(self, candidates: list[Axiom], probes: list[Probe], profile: str = "EL",
                 step_cost: float = 0.05, profile_penalty: float = 0.5,
                 miss_penalty: float = 0.0, escalate_reward: float | None = None,
                 gamma: float = 1.0):
        self.candidates = [Axiom.parse(c) for c in candidates]
        self.probes = list(probes)
        self.profile = profile.upper()
        self.step_cost = step_cost
        self.profile_penalty = profile_penalty
        self.miss_penalty = miss_penalty
        self.escalate_reward = escalate_reward
        self.gamma = gamma
        self._quality: dict[frozenset, float] = {}

    def initial_state(self) -> BuildState:
        return BuildState(frozenset())

    def is_terminal(self, state: BuildState) -> bool:
        return state.status != "open"

    def states(self) -> list[BuildState]:
        n = len(self.candidates)
        out = []
        for mask in range(1 << n):
            chosen = frozenset(i for i in range(n) if mask & (1 << i))
            out += [BuildState(chosen, s) for s in ("open", "submitted", "escalated")]
        return out

    def actions(self, state: BuildState) -> list[str]:
        if state.status != "open":
            return []
        acts = [f"assert:{i}" for i in range(len(self.candidates)) if i not in state.asserted]
        acts.append("submit")
        if self.escalate_reward is not None:
            acts.append("escalate")
        return acts

    def quality(self, asserted: frozenset[int]) -> float:
        if asserted not in self._quality:
            chosen = [self.candidates[i] for i in asserted]
            cov = coverage(chosen, self.probes)
            violations = sum(1 for a in chosen if not in_profile(a, self.profile))
            self._quality[asserted] = (cov - self.profile_penalty * violations
                                       - self.miss_penalty * (1 - cov))
        return self._quality[asserted]

    def transition(self, state: BuildState, action: str):
        if action == "submit":
            return [(1.0, BuildState(state.asserted, "submitted"), self.quality(state.asserted))]
        if action == "escalate":
            return [(1.0, BuildState(state.asserted, "escalated"), float(self.escalate_reward))]
        index = int(action.split(":")[1])
        return [(1.0, BuildState(state.asserted | {index}), -self.step_cost)]

    def step(self, state: BuildState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)

    def describe_action(self, action: str) -> str:
        if action.startswith("assert:"):
            return f"assert {self.candidates[int(action.split(':')[1])]}"
        return action


if __name__ == "__main__":
    import time

    t0 = time.perf_counter()
    for row in validate_gold():
        print(f"{row['id']:32s} {row['split']:5s} {row['profile']}  {row['gold']:48s} "
              f"allowed={row['allowed_in']:4s} probe={row['probe_ok']}")
    print(f"gold validated in {time.perf_counter() - t0:.2f}s")
    print(profile_table_text())
