"""Chapter 6 problem-set support — untangling a museum catalogue's single ``partOf``.

Provided code for ``04_assignment.ipynb``. The student builds the scorer, the
Claude classifier and the chaining agent in the notebook; this module supplies
what the museum's data team would already have in its codebase:

* the **argument categories and relation menus** the migration uses, taken from
  Chapter 6's toolkit (:mod:`ch06_toolkit`) — the museum's adopted convention;
* the **catalogue corpus** — 24 legacy "part of" entries, labelled with the
  categories of both arguments, split train / dev / test by item and balanced
  so every split holds every relation exactly once. Every gold relation is
  re-derived with :func:`ch06_toolkit.classify_partwhole` when the dataset is
  built, so a label that disagrees with the chapter's procedure cannot load;
* the **guidelines** a classification scorer reports (:data:`PARTWHOLE_RULEBOOK`);
* the **typed catalogue links** (:data:`CATALOGUE_LINKS`), the questions the
  collections search answers wrongly today (:data:`CHAIN_QUERIES`), and the
  agent's tools over them (:func:`build_catalogue_tools`);
* **category diagnosis as an MDP** (:class:`CategoryDiagnosisMDP`) — stochastic
  answers, a question cost, and an optional prior over categories. Solving it
  derives a foundational ontology's decision tree from a cost model.

Why the chapter's taxonomy is the grader: English says "part of" for at least
eight different relations, only some of which are parthood and fewer still
transitive. Once the categories of the two arguments are known, the relation
follows almost mechanically — so the labels can be *checked*, not argued.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import ch06_toolkit as ch6

__all__ = [
    "ARGUMENT_CATEGORIES", "category_menu", "relation_menu", "RELATION_IDS",
    "CatalogueItem", "CATALOGUE_ITEMS", "build_dataset",
    "RULE_FOR_RELATION", "PARTWHOLE_RULEBOOK", "BASELINE_INSTRUCTION",
    "CATALOGUE_LINKS", "CHAIN_QUERIES", "CatalogueWorkspace", "build_catalogue_tools",
    "DiagnosisState", "CategoryDiagnosisMDP", "CATALOGUE_CLASS_PRIOR", "CURATOR_MINUTES",
]


# --------------------------------------------------------------------------- #
# The menus the classifier answers from
# --------------------------------------------------------------------------- #
#: The categories an argument of a "part of" statement can have, as the
#: part-whole procedure (:func:`ch06_toolkit.classify_partwhole`) uses them.
#: ``process`` stands for any perdurant — anything that happens.
ARGUMENT_CATEGORIES: dict[str, str] = {
    "physical-object": "a bounded, countable thing with spatial parts (a clock, a teacup, a person)",
    "amount-of-matter": "stuff named by a mass noun (bronze, linseed oil, a paint batch)",
    "collection": "a group whose members play no structural role (a hoard, a tea service, a herbarium)",
    "process": "something that happens or unfolds in time (a loan, a treatment, a cleaning step)",
    "region": "a spatial region or zone (a wing, a gallery zone, a storage area)",
}

#: The relation ids of the target schema, in the toolkit's order.
RELATION_IDS: list[str] = [r.id for r in ch6.PART_WHOLE_RELATIONS]


def category_menu() -> str:
    """The category ids the classifier may use, one per line with a gloss."""
    return "\n".join(f"{cid}: {gloss}" for cid, gloss in ARGUMENT_CATEGORIES.items())


def relation_menu() -> str:
    """The typed relations of the target schema, as the migration team lists them.

    Deliberately *not* included: which relations are parthood and which are
    transitive. That is the chapter's knowledge, and what the classifier is
    being evaluated on.
    """
    return "\n".join(f"{r.id}: e.g. {r.example}" for r in ch6.PART_WHOLE_RELATIONS)


# --------------------------------------------------------------------------- #
# The labelled catalogue sample
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CatalogueItem:
    """One legacy catalogue entry that used the single ``partOf`` field."""

    id: str
    split: str
    statement: str
    part_category: str
    whole_category: str
    relation: str               # the expected relation, re-derived and asserted on load
    separable: bool = False     # only matters for physical-object in physical-object


#: 24 entries, three per relation, one of each relation per split. Every entry is
#: phrased with "part of", because that is what the legacy field forced
#: cataloguers to write — the English is uniform and the relations are not.
CATALOGUE_ITEMS: list[CatalogueItem] = [
    # --- component-of: a functional, integral piece ------------------------
    CatalogueItem("pendulum-clock", "train",
                  "The pendulum is part of the longcase clock (OBJ-1904.12).",
                  "physical-object", "physical-object", "component-of"),
    CatalogueItem("lid-teapot", "dev",
                  "The lid is part of the Meissen teapot (OBJ-1951.3).",
                  "physical-object", "physical-object", "component-of"),
    CatalogueItem("lockplate-musket", "test",
                  "The lock plate is part of the flintlock musket (ARM-0212).",
                  "physical-object", "physical-object", "component-of"),
    # --- member-of: the whole is a collection ------------------------------
    CatalogueItem("teacup-service", "train",
                  "The teacup is part of the 1745 Meissen tea service (ENS-12).",
                  "physical-object", "collection", "member-of"),
    CatalogueItem("coin-hoard", "dev",
                  "The silver penny is part of the Aldermoor coin hoard (NUM-H3).",
                  "physical-object", "collection", "member-of"),
    CatalogueItem("sheet-herbarium", "test",
                  "Herbarium sheet 88 is part of the Banks botanical collection (NH-BOT-1).",
                  "physical-object", "collection", "member-of"),
    # --- sub-quantity-of: stuff within stuff --------------------------------
    CatalogueItem("oil-paint", "train",
                  "The linseed oil is part of the retouching paint mixed for OBJ-1922.7.",
                  "amount-of-matter", "amount-of-matter", "sub-quantity-of"),
    CatalogueItem("ethanol-solvent", "dev",
                  "The ethanol is part of the studio's cleaning-solvent mix.",
                  "amount-of-matter", "amount-of-matter", "sub-quantity-of"),
    CatalogueItem("resin-stock", "test",
                  "The resin drawn for this treatment is part of the Paraloid B-72 stock in "
                  "Store C.",
                  "amount-of-matter", "amount-of-matter", "sub-quantity-of"),
    # --- constituted-of: the stuff an object is made of (NOT parthood) ----
    CatalogueItem("bronze-cast", "train",
                  "The bronze is part of the cast of The Thinker (OBJ-1922.7).",
                  "amount-of-matter", "physical-object", "constituted-of"),
    CatalogueItem("marble-bust", "dev",
                  "The marble is part of the portrait bust of Lady Aldermoor (OBJ-1880.2).",
                  "amount-of-matter", "physical-object", "constituted-of"),
    CatalogueItem("silver-salver", "test",
                  "The silver is part of the Georgian salver (MET-0441).",
                  "amount-of-matter", "physical-object", "constituted-of"),
    # --- participates-in: an object taking part in a happening (NOT parthood)
    CatalogueItem("painting-loan", "train",
                  "The Dutch interior painting (PNT-0077) is part of the 2026 loan to Amsterdam.",
                  "physical-object", "process", "participates-in"),
    CatalogueItem("tapestry-cleaning", "dev",
                  "The Flemish tapestry (TEX-0019) is part of the 2025 wet-cleaning campaign.",
                  "physical-object", "process", "participates-in"),
    CatalogueItem("courier-transfer", "test",
                  "The museum courier is part of the crate transfer to Tokyo.",
                  "physical-object", "process", "participates-in"),
    # --- contained-in: removable contents (NOT parthood) --------------------
    CatalogueItem("letters-box", "train",
                  "The bundle of letters is part of the contents of archive box AB-117.",
                  "physical-object", "physical-object", "contained-in", separable=True),
    CatalogueItem("cat-case", "dev",
                  "The mummified cat is part of the contents of display case 7.",
                  "physical-object", "physical-object", "contained-in", separable=True),
    CatalogueItem("silica-crate", "test",
                  "The silica-gel sachet is part of the contents of packing crate 31.",
                  "physical-object", "physical-object", "contained-in", separable=True),
    # --- located-in: position in a spatial region (NOT parthood) ------------
    CatalogueItem("cast-eastwing", "train",
                  "The plaster cast of the Rosetta Stone is part of the East Wing.",
                  "physical-object", "region", "located-in"),
    CatalogueItem("totem-garden", "dev",
                  "The carved totem pole is part of the sculpture-garden zone.",
                  "physical-object", "region", "located-in"),
    CatalogueItem("timbers-store", "test",
                  "The shipwreck timbers are part of Store Area B.",
                  "physical-object", "region", "located-in"),
    # --- involved-in: a step of a larger happening --------------------------
    CatalogueItem("cleaning-treatment", "train",
                  "Surface cleaning is part of the conservation treatment of OBJ-1922.7.",
                  "process", "process", "involved-in"),
    CatalogueItem("conditioncheck-loan", "dev",
                  "Condition checking is part of the 2026 loan to Amsterdam.",
                  "process", "process", "involved-in"),
    CatalogueItem("photography-accession", "test",
                  "Photographing the object is part of the accessioning of ACC-2026-014.",
                  "process", "process", "involved-in"),
]


def build_dataset(split: str = "all"):
    """The catalogue sample as ``dspy.Example`` rows.

    Inputs: ``statement``, ``categories`` (menu), ``relations`` (menu).
    Gold: ``part_category``, ``whole_category``, ``separable``, ``gold_relation``,
    ``gold_parthood``. Each gold relation is recomputed with the chapter's
    procedure and must agree with the label, so the corpus cannot drift.
    """
    import dspy

    categories, relations = category_menu(), relation_menu()
    rows = []
    for item in CATALOGUE_ITEMS:
        derived = ch6.classify_partwhole(item.part_category, item.whole_category, item.separable)
        if derived != item.relation:
            raise ValueError(f"{item.id}: label {item.relation!r} but the procedure "
                             f"gives {derived!r}")
        rows.append(dspy.Example(
            id=item.id, split=item.split, statement=item.statement,
            categories=categories, relations=relations,
            part_category=item.part_category, whole_category=item.whole_category,
            separable=item.separable, gold_relation=item.relation,
            gold_parthood=ch6.relation_by_id(item.relation).parthood,
        ).with_inputs("statement", "categories", "relations"))
    return rows if split == "all" else [r for r in rows if r.split == split]


# --------------------------------------------------------------------------- #
# Guidelines a classification scorer can report
# --------------------------------------------------------------------------- #
#: Which guideline a wrong answer violates, keyed by the *correct* relation.
RULE_FOR_RELATION: dict[str, str] = {
    "component-of": "component-for-integral-parts",
    "member-of": "member-for-collections",
    "sub-quantity-of": "subquantity-for-amounts",
    "involved-in": "involvement-for-processes",
    "constituted-of": "constitution-not-parthood",
    "participates-in": "participation-not-parthood",
    "contained-in": "containment-not-parthood",
    "located-in": "location-not-parthood",
}


def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("use-the-menus",
             "Answer every field with an id exactly as listed in the menus (category ids, "
             "relation ids) and is_parthood with true or false -- no prose, no new ids."),
        Rule("identify-categories-first",
             "Decide the category of the part and of the whole before choosing a relation: "
             "stuff named by a mass noun is amount-of-matter, a group is a collection, "
             "anything that happens is a process, a zone or area is a region."),
        Rule("component-for-integral-parts",
             "When a physical object is a functional, integral piece of another (a pendulum "
             "of a clock), the relation is component-of, and it is parthood."),
        Rule("member-for-collections",
             "When the whole is a collection (a hoard, a tea service, a herbarium), the "
             "relation is member-of, not component-of; members play no structural role."),
        Rule("subquantity-for-amounts",
             "When both part and whole are amounts of matter (mass nouns), the relation is "
             "sub-quantity-of; it is parthood and it is transitive."),
        Rule("involvement-for-processes",
             "When both part and whole are processes (a step of a treatment), the relation "
             "is involved-in; it is parthood and it is transitive."),
        Rule("constitution-not-parthood",
             "When an amount of matter makes up an object (the bronze of a cast), the "
             "relation is constituted-of and it is NOT parthood."),
        Rule("participation-not-parthood",
             "When an object takes part in something that happens (a painting in a loan), "
             "the relation is participates-in and it is NOT parthood."),
        Rule("containment-not-parthood",
             "When the part is removable contents of a container (letters in a box, an "
             "object in a display case), the relation is contained-in and it is NOT parthood."),
        Rule("location-not-parthood",
             "When the whole is a spatial region (a wing, a zone, a store area), the relation "
             "is located-in and it is NOT parthood."),
        Rule("check-genuine-parthood",
             "Decide separately whether the relation is genuine parthood, and keep the answer "
             "consistent with the relation named: constitution, participation, containment "
             "and location are not parthood."),
    ])


#: The guidelines a part-whole classification scorer reports as violated.
PARTWHOLE_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are an ontology engineer migrating a museum catalogue. Say which part-whole "
    "relation the catalogue statement expresses."
)


# --------------------------------------------------------------------------- #
# The typed catalogue graph and the search questions (Parts A and D)
# --------------------------------------------------------------------------- #
#: (part, relation, whole): legacy ``partOf`` links, now typed. The direction is
#: the legacy one — the child was catalogued "part of" the parent — and the
#: relation says what that "part of" really was. Every child has one parent, so
#: the graph is a forest and each item has a unique path upwards.
CATALOGUE_LINKS: list[tuple[str, str, str]] = [
    ("linseed-oil", "sub-quantity-of", "retouching-paint"),
    ("retouching-paint", "sub-quantity-of", "studio-paint-batch"),
    ("studio-paint-batch", "sub-quantity-of", "conservation-paint-stock"),
    ("bronze", "constituted-of", "thinker-cast"),
    ("thinker-cast", "located-in", "sculpture-hall"),
    ("sculpture-hall", "located-in", "east-wing"),
    ("pendulum", "component-of", "longcase-clock"),
    ("longcase-clock", "member-of", "clock-collection"),
    ("teacup", "member-of", "meissen-tea-service"),
    ("meissen-tea-service", "contained-in", "display-case-7"),
    ("display-case-7", "located-in", "east-wing"),
    ("surface-cleaning", "involved-in", "varnish-removal"),
    ("varnish-removal", "involved-in", "conservation-treatment"),
    ("dutch-interior", "participates-in", "loan-2026"),
    ("condition-check", "involved-in", "loan-2026"),
]

#: (id, part, whole, question, gold). Gold is "yes" when genuine parthood between
#: part and whole follows from the typed links, "no" otherwise. The collections
#: search, which treats every link as one transitive partOf, answers "yes" to all.
CHAIN_QUERIES: list[tuple[str, str, str, str, str]] = [
    ("oil-stock", "linseed-oil", "conservation-paint-stock",
     "Is the linseed oil part of the conservation paint stock?", "yes"),
    ("paint-stock", "retouching-paint", "conservation-paint-stock",
     "Is the retouching paint part of the conservation paint stock?", "yes"),
    ("cleaning-treatment", "surface-cleaning", "conservation-treatment",
     "Is surface cleaning part of the conservation treatment?", "yes"),
    ("check-loan", "condition-check", "loan-2026",
     "Is the condition check part of the 2026 loan?", "yes"),
    ("pendulum-collection", "pendulum", "clock-collection",
     "Is the pendulum part of the clock collection?", "no"),
    ("bronze-wing", "bronze", "east-wing",
     "Is the bronze part of the East Wing?", "no"),
    ("teacup-case", "teacup", "display-case-7",
     "Is the teacup part of display case 7?", "no"),
    ("painting-loan", "dutch-interior", "loan-2026",
     "Is the Dutch interior painting part of the 2026 loan?", "no"),
]


@dataclass
class CatalogueWorkspace:
    """What the chaining agent can see: the typed links, and its call log."""

    links: list[tuple[str, str, str]] = field(default_factory=lambda: list(CATALOGUE_LINKS))
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()

    def parent(self, item: str):
        """The (relation, whole) link above ``item``, or None at a root."""
        return next(((r, w) for p, r, w in self.links if p == item), None)

    def upward(self, item: str) -> list[dict]:
        """The typed links from ``item`` up to its root, in order."""
        path, seen = [], {item}
        current = item
        while (link := self.parent(current)) is not None:
            relation, whole = link
            path.append({"part": current, "relation": relation, "whole": whole})
            if whole in seen:           # defensive: the provided graph is acyclic
                break
            seen.add(whole)
            current = whole
        return path


def build_catalogue_tools(ws: CatalogueWorkspace):
    """The chaining agent's tools: trace links, read the taxonomy, check a chain."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def trace_upward(item: str) -> str:
        """List the typed catalogue links from an item up to its top-level whole.

        Returns the path in order, e.g. [{"part": "a", "relation": "member-of",
        "whole": "b"}, {"part": "b", ...}]. An empty list means the item has no
        parent (or is unknown -- check the spelling of the id).
        """
        return json.dumps({"item": item, "path": ws.upward(item.strip())})

    def part_whole_relations() -> str:
        """List the part-whole relations with their logical properties.

        For each relation: whether it is genuine parthood, whether it is transitive,
        what it relates, and a test question. Several relations English calls
        'part of' are NOT parthood.
        """
        return json.dumps([
            {"id": r.id, "parthood": r.parthood, "transitive": r.transitive,
             "part": r.part_category, "whole": r.whole_category,
             "example": r.example, "test": r.test}
            for r in ch6.PART_WHOLE_RELATIONS
        ])

    def check_chaining(first: str, second: str) -> str:
        """Decide whether 'a first b' and 'b second c' license parthood between a and c.

        Pass two relation ids, e.g. first='component-of', second='member-of'. Call it
        for every consecutive pair on a path before claiming parthood across it; a
        valid chain of R with R yields R again, so longer paths are checked pairwise.
        """
        first, second = first.strip(), second.strip()
        if first not in RELATION_IDS or second not in RELATION_IDS:
            return json.dumps({"error": "unknown relation id", "valid_ids": RELATION_IDS})
        return json.dumps(ch6.can_chain(first, second))

    impls = [trace_upward, part_whole_relations, check_chaining]
    return [tool(instrument(fn, fn.__name__, ws.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Category diagnosis as an MDP (Part D)
# --------------------------------------------------------------------------- #
#: How often each foundational category turns up among the classes the museum's
#: catalogue adds in a year (estimated from the 2025 schema-change log): mostly
#: objects, then qualities (condition, colour), materials and happenings.
CATALOGUE_CLASS_PRIOR: dict[str, float] = {
    "physical-object": 0.52,
    "quality": 0.14,
    "amount-of-matter": 0.12,
    "process": 0.08,
    "event": 0.06,
    "feature": 0.05,
    "abstract": 0.03,
}


#: Median curator minutes to answer each decision question reliably for a new
#: class (timed in the 2025 cataloguing workshops). "Does it happen?" is
#: answered at a glance; "must it inhere in something else?" starts arguments.
CURATOR_MINUTES: dict[str, float] = {
    "happens": 0.5,
    "spatial": 1.0,
    "mass": 1.0,
    "dependent": 4.0,
    "telic": 2.0,
}


@dataclass(frozen=True)
class DiagnosisState:
    """The candidate categories still consistent with the answers so far."""

    candidates: frozenset[str]
    committed: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        return "{" + ",".join(sorted(c.split("-")[0] for c in self.candidates)) + "}" + (
            "!" if self.committed else "")


class CategoryDiagnosisMDP:
    """Align a class to a foundational category by asking as few questions as possible.

    | | |
    |---|---|
    | **S** | the set of categories still consistent with the answers |
    | **A** | ask a question that actually splits the set, or commit |
    | **T** | **stochastic** — the answer is not known until it is asked; the |
    |       | probability of each answer is the prior mass of the categories giving it |
    | **R** | −cost of the question asked (``question_cost``: one number, or a |
    |       | per-question table); on commit, the probability of being |
    |       | right when committing to the most probable remaining category |

    With the default uniform prior, committing with ``k`` candidates left is right
    with probability ``1/k``. Value iteration yields an optimal question *order*
    — which is what a foundational ontology's decision tree is.
    """

    def __init__(self, question_cost: float | dict[str, float] = 0.05, gamma: float = 1.0,
                 categories: dict | None = None,
                 questions: tuple[str, ...] | None = None,
                 prior: dict[str, float] | None = None):
        self.categories = categories or {c.id: ch6.category_answers(c.id) for c in ch6.CATEGORIES}
        self.questions = tuple(questions) if questions is not None else tuple(ch6.DECISION_QUESTIONS)
        unknown = [q for q in self.questions if q not in ch6.DECISION_QUESTIONS]
        if unknown:
            raise ValueError(f"unknown decision questions {unknown}")
        prior = prior or {c: 1.0 for c in self.categories}
        if set(prior) != set(self.categories) or min(prior.values()) <= 0:
            raise ValueError("prior must give every category a positive weight")
        total = sum(prior.values())
        self.prior = {c: w / total for c, w in prior.items()}
        if isinstance(question_cost, dict):
            missing = [q for q in self.questions if q not in question_cost]
            if missing:
                raise ValueError(f"no cost given for questions {missing}")
        self.question_cost = question_cost
        self.gamma = gamma
        self._states: list[DiagnosisState] | None = None

    # -- helpers -------------------------------------------------------------
    def cost_of(self, question: str) -> float:
        """The price of asking one question (a flat cost, or a per-question table)."""
        if isinstance(self.question_cost, dict):
            return float(self.question_cost[question])
        return float(self.question_cost)

    def mass(self, candidates) -> float:
        return sum(self.prior[c] for c in candidates)

    def commit_accuracy(self, candidates) -> float:
        """P(right) when committing to the most probable remaining category."""
        return max(self.prior[c] for c in candidates) / self.mass(candidates)

    def best_guess(self, candidates) -> str:
        return max(sorted(candidates), key=lambda c: self.prior[c])

    def _split(self, candidates: frozenset[str], question: str):
        yes = frozenset(c for c in candidates if self.categories[c][question])
        no = frozenset(c for c in candidates if not self.categories[c][question])
        return yes, no

    # -- MDP interface -------------------------------------------------------
    def initial_state(self) -> DiagnosisState:
        return DiagnosisState(frozenset(self.categories))

    def is_terminal(self, state: DiagnosisState) -> bool:
        return state.committed

    def states(self) -> list[DiagnosisState]:
        """Only *reachable* candidate sets — the full power set is never visited."""
        if self._states is not None:
            return self._states
        reachable = {frozenset(self.categories)}
        frontier = [frozenset(self.categories)]
        while frontier:
            current = frontier.pop()
            for question in self.questions:
                for part in self._split(current, question):
                    if part and part != current and part not in reachable:
                        reachable.add(part)
                        frontier.append(part)
        self._states = [DiagnosisState(s, c) for s in reachable for c in (False, True)]
        return self._states

    def actions(self, state: DiagnosisState) -> list[str]:
        if state.committed:
            return []
        useful = [f"ask:{q}" for q in self.questions
                  if all(part for part in self._split(state.candidates, q))]
        return useful + ["commit"]

    def transition(self, state: DiagnosisState, action: str):
        if action == "commit":
            return [(1.0, DiagnosisState(state.candidates, True),
                     self.commit_accuracy(state.candidates))]
        question = action.split(":", 1)[1]
        yes, no = self._split(state.candidates, question)
        total = self.mass(state.candidates)
        return [(self.mass(part) / total, DiagnosisState(part, False), -self.cost_of(question))
                for part in (yes, no) if part]

    def step(self, state: DiagnosisState, action: str):
        import random

        outcomes = self.transition(state, action)
        roll, cumulative = random.random(), 0.0
        for p, nxt, reward in outcomes:
            cumulative += p
            if roll <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        p, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)

    # -- reading the policy --------------------------------------------------
    def decision_tree(self, policy: dict, state: DiagnosisState | None = None,
                      depth: int = 0) -> list[str]:
        """Render the optimal policy as the decision tree it really is."""
        state = state or self.initial_state()
        action = policy.get(state)
        indent = "  " * depth
        if action is None or action == "commit":
            guess = self.best_guess(state.candidates)
            rest = sorted(state.candidates - {guess})
            return [f"{indent}-> {guess}" + (f"   (also possible: {rest})" if rest else "")]
        question = action.split(":", 1)[1]
        yes, no = self._split(state.candidates, question)
        lines = [f"{indent}{question}? ({ch6.DECISION_QUESTIONS[question]})"]
        for label, part in (("yes", yes), ("no", no)):
            if part:
                lines.append(f"{indent}  {label}:")
                lines += self.decision_tree(policy, DiagnosisState(part, False), depth + 2)
        return lines
