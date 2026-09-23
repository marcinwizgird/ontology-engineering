"""Chapter 6 toolkit — foundational ontologies and part-whole relations.

Chapter 5 ended on an error OntoClean could find but not fix: `Statue ⊑ Clay` is
wrong, and the right answer — *a statue is **constituted of** clay* — needs a
relation that subsumption cannot express. Chapter 6 supplies the vocabulary.

Two halves, both made executable here:

* **§6.1 foundational ontologies.** A DOLCE-style category tree, plus the
  *decision questions* that place a domain class in it. Alignment stops being
  taste and becomes a short interrogation with a defensible answer.
* **§6.2 part-whole relations.** The Keet/Winston taxonomy as data: which
  relations are genuine parthood, which are transitive, and what each one
  relates. Then the payoff — :func:`can_chain` decides when two part-whole
  statements may be composed, which is where almost every real modelling error
  in this area comes from.

The recurring lesson: "part of" in English is at least seven different
relations, and they have different logical properties. Collapsing them is how
you end up proving that a musician's hand is part of an orchestra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "CATEGORIES", "DECISION_QUESTIONS", "category_answers", "identify_category",
    "PART_WHOLE_RELATIONS", "relation_by_id", "classify_partwhole",
    "can_chain", "CHAINING_EXAMPLES", "BFO_COMPARISON",
]


# --------------------------------------------------------------------------- #
# §6.1  Foundational categories (DOLCE-flavoured, simplified)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Category:
    id: str
    name: str
    branch: str
    gloss: str
    examples: tuple[str, ...]


#: A deliberately small DOLCE-style tree: enough to make alignment decisions
#: real, small enough that the decision procedure is enumerable.
CATEGORIES = [
    Category("physical-object", "Physical Object", "Endurant",
             "A bounded, countable thing that exists in time and has spatial parts.",
             ("a giraffe", "a statue", "a car")),
    Category("amount-of-matter", "Amount of Matter", "Endurant",
             "Stuff: any part of it is described by the same term (mass noun).",
             ("clay", "water", "gold")),
    Category("feature", "Feature", "Endurant",
             "A dependent part or place of a host object.",
             ("a hole", "a bump", "a surface")),
    Category("quality", "Quality", "Quality",
             "An aspect that inheres in a bearer and cannot exist alone.",
             ("the colour of a leaf", "a mass", "a temperature")),
    Category("event", "Event", "Perdurant",
             "Something that happens and has a natural culmination.",
             ("a hunt that succeeds", "an arrival", "a birth")),
    Category("process", "Process", "Perdurant",
             "Something that goes on without a built-in endpoint.",
             ("grazing", "running", "digestion")),
    Category("abstract", "Abstract Entity", "Abstract",
             "Outside space and time, and not dependent on a bearer.",
             ("the number seven", "a set", "a proposition")),
]

_CATEGORY_BY_ID = {c.id: c for c in CATEGORIES}

#: The questions a modeller actually asks when placing a class. Each is a yes/no
#: test with a defensible answer for every category, which is what lets the
#: agentic lab turn alignment into a decision-tree MDP.
DECISION_QUESTIONS = {
    "happens": "Does it happen or unfold in time, rather than merely exist through time?",
    "spatial": "Does it have a location in space?",
    "mass": "Is any part of it describable by the same term (is it a mass noun)?",
    "dependent": "Must it inhere in, or belong to, some other entity to exist?",
    "telic": "Does it have a natural endpoint or culmination?",
}

#: Ground truth: how each category answers each question.
_ANSWERS = {
    #                    happens spatial  mass  dependent telic
    "physical-object":  (False,  True,   False, False,    False),
    "amount-of-matter": (False,  True,   True,  False,    False),
    "feature":          (False,  True,   False, True,     False),
    "quality":          (False,  False,  False, True,     False),
    "event":            (True,   True,   False, False,    True),
    "process":          (True,   True,   False, False,    False),
    "abstract":         (False,  False,  False, False,    False),
}
_QUESTION_ORDER = ("happens", "spatial", "mass", "dependent", "telic")


def category_answers(category_id: str) -> dict[str, bool]:
    """How one category answers every decision question."""
    return dict(zip(_QUESTION_ORDER, _ANSWERS[category_id]))


def identify_category(answers: dict[str, bool]) -> list[str]:
    """Which categories are consistent with a (possibly partial) set of answers."""
    out = []
    for category_id in _ANSWERS:
        truth = category_answers(category_id)
        if all(truth[q] == a for q, a in answers.items() if q in truth):
            out.append(category_id)
    return out


#: How the same distinctions are drawn in BFO — the other foundational ontology
#: students will meet. Included because the *choice* between them is a real
#: project decision, and the vocabularies do not line up one-to-one.
BFO_COMPARISON = [
    {"dolce": "Physical Object", "bfo": "Material Entity (Object)",
     "note": "closest match"},
    {"dolce": "Amount of Matter", "bfo": "Material Entity (Object Aggregate / portion)",
     "note": "BFO has no dedicated amount-of-matter category"},
    {"dolce": "Feature", "bfo": "Immaterial Entity (Site) / Continuant Fiat Boundary",
     "note": "holes are sites in BFO"},
    {"dolce": "Quality", "bfo": "Specifically Dependent Continuant (Quality)",
     "note": "close match"},
    {"dolce": "Event", "bfo": "Process (with a process boundary)",
     "note": "BFO folds events into processes"},
    {"dolce": "Process", "bfo": "Process", "note": "close match"},
    {"dolce": "Abstract Entity", "bfo": "(none - BFO is realist)",
     "note": "BFO deliberately excludes abstracta"},
]


# --------------------------------------------------------------------------- #
# §6.2  The part-whole taxonomy
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PartWholeRelation:
    """One relation from the part-whole taxonomy, with its logical properties.

    ``parthood`` marks *genuine mereological parthood*. Several relations that
    English calls "part of" are not parthood at all — containment and
    constitution being the two that cause the most damage.
    """

    id: str
    name: str
    parthood: bool
    transitive: bool
    part_category: str
    whole_category: str
    example: str
    test: str


PART_WHOLE_RELATIONS = [
    PartWholeRelation(
        "component-of", "component of", True, False,
        "physical-object", "physical-object",
        "a wheel is a component of a car",
        "Is the part a separable, functional piece of a structured whole?",
    ),
    PartWholeRelation(
        "member-of", "member of", True, False,
        "physical-object", "collection",
        "a musician is a member of an orchestra",
        "Is the whole a collection whose parts play no structural role?",
    ),
    PartWholeRelation(
        "sub-quantity-of", "sub-quantity of", True, True,
        "amount-of-matter", "amount-of-matter",
        "the alcohol is a sub-quantity of the wine",
        "Are both part and whole amounts of stuff (mass nouns)?",
    ),
    PartWholeRelation(
        "involved-in", "involved in", True, True,
        "process", "process",
        "chewing is involved in eating",
        "Are both part and whole things that happen?",
    ),
    PartWholeRelation(
        "participates-in", "participates in", False, False,
        "physical-object", "process",
        "a lion participates in a hunt",
        "Is an enduring thing taking part in something that happens?",
    ),
    PartWholeRelation(
        "constituted-of", "constituted of", False, False,
        "amount-of-matter", "physical-object",
        "a statue is constituted of clay",
        "Is the whole made of the stuff, without being a kind of it?",
    ),
    PartWholeRelation(
        "contained-in", "contained in", False, False,
        "physical-object", "physical-object",
        "the coffee is contained in the cup",
        "Could the part be removed and the whole be unchanged?",
    ),
    PartWholeRelation(
        "located-in", "located in", False, True,
        "physical-object", "region",
        "the giraffe is located in the reserve",
        "Is this a spatial position rather than composition?",
    ),
]

_RELATION_BY_ID = {r.id: r for r in PART_WHOLE_RELATIONS}


def relation_by_id(relation_id: str) -> PartWholeRelation:
    return _RELATION_BY_ID[relation_id]


def classify_partwhole(part_category: str, whole_category: str,
                       separable: bool | None = None) -> str:
    """Pick the part-whole relation from the categories of the two arguments.

    This is Keet's decision procedure in code. The categories do almost all the
    work — which is precisely the argument for §6.1: you cannot choose the right
    part-whole relation until you know what kind of things you are relating.

    ``separable`` distinguishes containment from componenthood when both
    arguments are physical objects: a removable content is *contained in*, a
    functional piece is a *component of*.
    """
    part, whole = part_category, whole_category

    if whole == "collection":
        return "member-of"
    if part == "amount-of-matter" and whole == "amount-of-matter":
        return "sub-quantity-of"
    if part == "amount-of-matter" and whole == "physical-object":
        return "constituted-of"
    if part in ("process", "event") and whole in ("process", "event"):
        return "involved-in"
    if part in ("physical-object", "amount-of-matter") and whole in ("process", "event"):
        return "participates-in"
    if whole == "region":
        return "located-in"
    if part == "physical-object" and whole == "physical-object":
        if separable:
            return "contained-in"
        return "component-of"
    return "component-of"


# --------------------------------------------------------------------------- #
# Chaining — where the real errors are
# --------------------------------------------------------------------------- #
def can_chain(first: str, second: str) -> dict:
    """May ``a R1 b`` and ``b R2 c`` be composed into a part-whole claim about ``a`` and ``c``?

    Three ways it can fail, and all three occur in published ontologies:

    1. one of the relations is **not parthood** at all (containment,
       constitution, participation);
    2. the two relations **differ**, so there is no single transitive relation
       to appeal to;
    3. the relation is parthood but **not transitive** (componenthood,
       membership).
    """
    r1, r2 = _RELATION_BY_ID[first], _RELATION_BY_ID[second]

    if not r1.parthood or not r2.parthood:
        offender = r1 if not r1.parthood else r2
        return {
            "valid": False,
            "reason": f"{offender.name!r} is not genuine parthood, so nothing about "
                      f"parthood follows from it",
        }
    if r1.id != r2.id:
        return {
            "valid": False,
            "reason": f"{r1.name!r} and {r2.name!r} are different relations; transitivity "
                      f"is a property of one relation, not of 'part of' in general",
        }
    if not r1.transitive:
        return {
            "valid": False,
            "reason": f"{r1.name!r} is parthood but is not transitive",
        }
    return {"valid": True, "reason": f"{r1.name!r} is parthood and transitive"}


#: Worked chaining cases, including the classic counterexamples.
CHAINING_EXAMPLES = [
    {
        "id": "hand-musician-orchestra",
        "story": "A hand is a component of a musician; a musician is a member of an "
                 "orchestra. Is the hand part of the orchestra?",
        "first": "component-of", "second": "member-of", "expected": False,
    },
    {
        "id": "alcohol-wine-cellar",
        "story": "The alcohol is a sub-quantity of the wine; the wine is a sub-quantity of "
                 "the cellar's stock. Is the alcohol a sub-quantity of the stock?",
        "first": "sub-quantity-of", "second": "sub-quantity-of", "expected": True,
    },
    {
        "id": "chewing-eating-dining",
        "story": "Chewing is involved in eating; eating is involved in dining. Is chewing "
                 "involved in dining?",
        "first": "involved-in", "second": "involved-in", "expected": True,
    },
    {
        "id": "coffee-cup-kitchen",
        "story": "The coffee is contained in the cup; the cup is contained in the kitchen. "
                 "Is the coffee part of the kitchen?",
        "first": "contained-in", "second": "contained-in", "expected": False,
    },
    {
        "id": "clay-statue-exhibit",
        "story": "The statue is constituted of clay; the statue is a component of the "
                 "exhibit. Is the clay a component of the exhibit?",
        "first": "constituted-of", "second": "component-of", "expected": False,
    },
    {
        "id": "wheel-car-fleet",
        "story": "A wheel is a component of a car; a car is a member of a fleet. Is the "
                 "wheel part of the fleet?",
        "first": "component-of", "second": "member-of", "expected": False,
    },
]
