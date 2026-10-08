"""Build the Chapter 6 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch06_topdown_development/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 6 — Top-down Ontology Development",
    title="Untangling a museum catalogue's single partOf with Claude",
    coverage=("Keet §6.1 (foundational ontologies, aligning a domain class by decision "
              "questions), §6.2 (the part-whole taxonomy, parthood versus its impostors, "
              "transitivity and chaining); course notebooks 01–03 of this chapter. Tools: "
              "DSPy + GEPA, LangChain agents, the Chapter 6 toolkit (`classify_partwhole`, "
              "`can_chain`) and a diagnostic-questioning MDP."),
    scenario="""
    The **Aldermoor Museum of Art and Industry** is migrating its collections catalogue
    (≈ 41,000 records) into a knowledge graph. The legacy system had exactly one
    relationship field, `partOf`, and cataloguers used it for everything: the pendulum
    of a clock, a coin in a hoard, the bronze of a cast, a painting on loan, letters in
    an archive box, a totem pole in the sculpture garden. The public collections search
    treats `partOf` as transitive, and it shows: *"What is part of the East Wing?"*
    lists the bronze of *The Thinker*, and the insurance export counts a pendulum as an
    item of the clock collection.

    The Head of Collections Information has asked you, the ontology engineer, to type
    every legacy link with the right part-whole relation. The data office has adopted
    the Chapter 6 taxonomy (`ch06_toolkit.PART_WHOLE_RELATIONS`) as the museum's
    **modelling convention**: which relations count as parthood and which are
    transitive is decided by that table, and that is what "correct" means below. Your
    brief:

    1. **Measure the damage** a single transitive `partOf` does, and find where the
       chapter's own decision procedure runs out.
    2. **Build the grader first**, then a **Claude classifier** that reads a legacy
       entry and returns the categories of both arguments, the relation, and whether it
       is genuine parthood. Measure it on a development split; improve it with GEPA;
       report on a **held-out test split**, with cost and run-to-run noise, next to
       hand-written guidelines and a design that lets the taxonomy decide.
    3. **Ship a chaining agent** that answers the search team's *"is X part of Y?"*
       questions with checked chains, never with the old transitive shortcut.
    4. **Plan the curator interview** for new classes: model category alignment as a
       stochastic diagnostic-questioning MDP, derive the decision tree from a cost
       model, and find out what it takes for DOLCE's tree to come out on top.

    The labelled sample (24 legacy entries, split 8/8/8 by item, every split holding
    each of the eight relations once), the menus, the typed catalogue links, the search
    questions and the MDP are provided in `ch06_agentic.py`.
    """,
    effort="10–12 hours",
    api_budget="≈ $5–12 estimated on `claude-opus-5` for a full run (≈ 180 DSPy calls at "
               "≈ $0.02–0.05 each, GEPA being the largest line, plus 8 agent runs at "
               "≈ $0.10–0.25 each). Nothing here was measured on a live run. Re-running "
               "unchanged cells is free — DSPy caches identical requests (except in C3, "
               "which disables the cache on purpose).",
)

ps.setup("""
import re, time
import dspy
import numpy as np
import pandas as pd
import ch06_toolkit as ch6
import ch06_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
pd.DataFrame([{"id": ex.id, "split": ex.split, "statement": ex.statement,
               "part": ex.part_category, "whole": ex.whole_category,
               "relation": ex.gold_relation, "parthood": ex.gold_parthood}
              for ex in train + dev + test])
""")
ps.code("""
print("The museum's convention (Chapter 6 toolkit):")
pd.DataFrame([{"relation": r.id, "parthood": r.parthood, "transitive": r.transitive,
               "part": r.part_category, "whole": r.whole_category}
              for r in ch6.PART_WHOLE_RELATIONS])
""")

# =========================================================================== #
ps.part("A", "What one transitive partOf costs, and where the procedure runs out", """
The legacy links, now typed, are in `A.CATALOGUE_LINKS` as `(part, relation, whole)`
triples, in the legacy direction (the child was catalogued "part of" the parent). The
live search computes the transitive closure of `partOf` over all of them.
""")
ps.code("""
pd.DataFrame(A.CATALOGUE_LINKS, columns=["part", "relation", "whole"])
""")

ps.problem("A1", "Every spurious answer the search gives", 10, """
1. Implement `naive_closure(links) -> set[(part, whole)]`: the transitive closure the
   search computes, ignoring the relation column.
2. Implement `sound_closure(links) -> set[(part, relation, whole)]`: the links plus
   every triple derivable by composing `a R1 b` and `b R2 c` into `a R1 c` **only
   when `ch6.can_chain(R1, R2)["valid"]`** (a valid chain has `R1 == R2`), repeated to
   a fixpoint.
3. Build `a1`, one row per pair the search returns that the sound closure does not,
   with columns `part`, `whole`, `path` (the relations along the path, e.g. from
   `A.CatalogueWorkspace().upward(part)`), and `reason` (the `can_chain` reason for the
   first pair on the path that fails).

Then answer in writing: (a) which of these errors would you expect to do the most
harm, and to whom? (b) `located-in` is transitive in the table, yet `can_chain`
refuses `located-in` + `located-in` — is "the Thinker cast is in the East Wing"
therefore false? (c) A colleague proposes to fix the OWL model by declaring
`componentOf`, `memberOf`, … as sub-properties of one transitive `partOf`. Would the
search stop listing the pendulum under the clock collection?
""", auto_points=6)
ps.todo(
    stub="""
    def naive_closure(links):
        # TODO
        raise NotImplementedError

    def sound_closure(links):
        # TODO
        raise NotImplementedError

    naive = sound = a1 = None      # TODO
    """,
    solution="""
    def naive_closure(links):
        pairs = {(a, c) for a, _, c in links}
        while True:
            new = {(a, d) for a, b in pairs for c, d in pairs if b == c} - pairs
            if not new:
                return pairs
            pairs |= new

    def sound_closure(links):
        triples = set(links)
        while True:
            new = {(a, r1, d) for a, r1, b in triples for c, r2, d in triples
                   if b == c and ch6.can_chain(r1, r2)["valid"]} - triples
            if not new:
                return triples
            triples |= new

    naive = naive_closure(A.CATALOGUE_LINKS)
    sound = sound_closure(A.CATALOGUE_LINKS)
    ws = A.CatalogueWorkspace()
    rows = []
    for part, whole in sorted(naive - {(a, c) for a, _, c in sound}):
        path = []
        for link in ws.upward(part):
            path.append(link["relation"])
            if link["whole"] == whole:
                break
        # fold the path pairwise: R + R -> R when valid, else stop at the first failure
        current, reason = path[0], None
        for nxt in path[1:]:
            verdict = ch6.can_chain(current, nxt)
            if not verdict["valid"]:
                reason = verdict["reason"]
                break
        rows.append({"part": part, "whole": whole, "path": path, "reason": reason})
    a1 = pd.DataFrame(rows)
    print(f"search returns {len(naive)} pairs; {len(sound)} typed facts are sound; "
          f"{len(a1)} answers are spurious")
    a1
    """)
ps.check("A1", """
toy = [("a", "involved-in", "b"), ("b", "involved-in", "c"), ("c", "involved-in", "d"),
       ("x", "component-of", "y"), ("y", "component-of", "z")]
assert naive_closure(toy) == {("a", "b"), ("b", "c"), ("c", "d"), ("a", "c"), ("b", "d"),
                              ("a", "d"), ("x", "y"), ("y", "z"), ("x", "z")}
assert sound_closure(toy) == set(toy) | {("a", "involved-in", "c"), ("b", "involved-in", "d"),
                                         ("a", "involved-in", "d")}
assert len(naive) == 26 and len(sound) == 19
assert set(zip(a1["part"], a1["whole"])) == {
    ("bronze", "sculpture-hall"), ("bronze", "east-wing"), ("thinker-cast", "east-wing"),
    ("pendulum", "clock-collection"), ("teacup", "display-case-7"),
    ("teacup", "east-wing"), ("meissen-tea-service", "east-wing")}
assert a1["reason"].map(lambda r: isinstance(r, str) and len(r) > 0).all()
# the sound closure must agree with the search team's gold answers
for qid, part, whole, _, gold in A.CHAIN_QUERIES:
    got = any(a == part and c == whole and ch6.relation_by_id(r).parthood for a, r, c in sound)
    assert ("yes" if got else "no") == gold, qid
""")
ps.written("""
**(a) Harm.** The seven spurious answers fall into three kinds. *Material leaking into
places* (bronze in the sculpture hall and the East Wing) pollutes the public search and
any "what is in gallery X" count — embarrassing, but visible. *Collection membership
from componenthood* (the pendulum as an item of the clock collection) is the costly one:
the insurance export and the loans register count objects by collection membership, so
a component becomes an insured, loanable item with its own valuation line. *Contents
becoming parts* (the teacup as part of display case 7, and via the case, of the East
Wing) breaks provenance and movement records: when the case is moved or deaccessioned,
a parthood-based rule would move or dispose of its contents with it.

**(b) No — it is true, but it is not parthood.** The cast *is* in the East Wing: the
sculpture hall is in the East Wing, and location in nested regions composes.
`can_chain` answers a narrower question, "does *parthood* follow?", and location is not
parthood in the museum's convention. The right model keeps a separate
`locatedIn` property, declared transitive in its own right, so the search can answer
"what is located in the East Wing?" soundly, and never lets that answer feed a parthood
query.

**(c) No.** A sub-property does not inherit transitivity, but the super-property still
receives every assertion: `componentOf(pendulum, clock)` gives `partOf(pendulum,
clock)`, `memberOf(clock, collection)` gives `partOf(clock, collection)`, and the
transitive `partOf` then yields `partOf(pendulum, collection)` — the same wrong answer,
now with more ceremony. The repair is to declare only the genuinely transitive parthood
relations (`subQuantityOf`, `involvedIn`) transitive, keep the non-parthood relations
(constitution, participation, containment, location) out of any parthood hierarchy, and
not introduce a transitive umbrella `partOf` at all.
""")

ps.problem("A2", "Where the categories stop deciding", 8, """
Chapter 6 claims the relation "follows almost mechanically" from the categories of part
and whole. Test the claim on the procedure itself. For every ordered pair of categories
in `A.ARGUMENT_CATEGORIES` and both values of `separable`, record what
`ch6.classify_partwhole` returns. Build `a2` (50 rows) with columns `part`, `whole`,
`separable`, `relation`, `parthood`, and `fallback` — `True` when the procedure returns
`component-of` although the pair is **not** (`physical-object`, `physical-object`),
i.e. it fell through to its default. Also set `separable_matters` to the set of
`(part, whole)` pairs whose answer changes with `separable`.

In writing: pick **three** fallback or otherwise suspicious rows (look at every row with
`whole == "collection"` too). For each, give a realistic museum catalogue sentence that
lands there, say what the right modelling is, and say what the migration should do with
such entries (the classifier will meet them in the real 41,000 records).
""", auto_points=4)
ps.todo(
    stub="""
    a2 = None                  # TODO: 50 rows
    separable_matters = None   # TODO: a set of (part, whole) pairs
    """,
    solution="""
    rows = []
    for part in A.ARGUMENT_CATEGORIES:
        for whole in A.ARGUMENT_CATEGORIES:
            for separable in (False, True):
                relation = ch6.classify_partwhole(part, whole, separable)
                rows.append({
                    "part": part, "whole": whole, "separable": separable,
                    "relation": relation,
                    "parthood": ch6.relation_by_id(relation).parthood,
                    "fallback": relation == "component-of"
                                and (part, whole) != ("physical-object", "physical-object"),
                })
    a2 = pd.DataFrame(rows)
    by_pair = a2.groupby(["part", "whole"])["relation"].nunique()
    separable_matters = set(by_pair[by_pair > 1].index)
    print("separable matters for:", separable_matters)
    print("fallback pairs:", sorted(set(zip(a2[a2.fallback].part, a2[a2.fallback].whole))))
    a2[a2.fallback | (a2.whole == "collection")].drop_duplicates(["part", "whole"])
    """)
ps.check("A2", """
assert isinstance(a2, pd.DataFrame) and len(a2) == 50
assert {"part", "whole", "separable", "relation", "parthood", "fallback"} <= set(a2.columns)
for _, row in a2.iterrows():
    assert row.relation == ch6.classify_partwhole(row.part, row.whole, row.separable)
assert separable_matters == {("physical-object", "physical-object")}
assert set(zip(a2[a2.fallback].part, a2[a2.fallback].whole)) == {
    ("physical-object", "amount-of-matter"), ("collection", "physical-object"),
    ("collection", "amount-of-matter"), ("collection", "process"),
    ("process", "physical-object"), ("process", "amount-of-matter"),
    ("region", "physical-object"), ("region", "amount-of-matter"), ("region", "process")}
""")
ps.written("""
The procedure is decisive on the eight "home" pairs and silently wrong outside them:
nine pairs fall through to `component-of` (parthood!), and every pair whose whole is a
collection becomes `member-of`, whatever the part is. Three that the migration will
meet:

* **`collection` part of `process` → falls back to component-of.** *"The Meissen tea
  service is part of the 2026 loan."* The right relation is participation (a collection
  participating in a loan), which the procedure only allows for objects and matter.
  Treat as `participates-in`, not parthood; the procedure should widen its participant
  categories.
* **`region` part of `physical-object` → falls back to component-of.** *"The lower-left
  quadrant is part of the altarpiece"* (a conservation-report region). This is spatial
  parthood of a region *of* an object — arguably genuine parthood, but not a component
  (a component is a separable, functional piece). The taxonomy has no relation for it;
  the migration should route such entries to a human and record the gap.
* **`collection` part of `collection` → member-of.** *"The Meissen service is part of
  the ceramics collection."* A sub-collection is not a member of its super-collection in
  the way an object is; treating it as membership makes counts of "items in the
  ceramics collection" include whole services as single items. It needs a
  sub-collection relation or an explicit counting rule.

(Other valid picks: `process` part of `physical-object`, *"cleaning is part of the
statue"*, which is not a part-whole statement at all — the legacy entry records a
treatment *of* the object; `physical-object` part of `amount-of-matter`, *"the fly is
part of the amber"*, which is containment/embedding, not componenthood.)

For the migration: the classifier's answers must be checked against the pair — any
answer whose categories land on a fallback or suspicious row goes to a review queue
rather than into the graph. The 24-item sample deliberately contains none of these
cases, so **no score measured in this problem set says anything about them**; that
limitation belongs in the report.
""")

# =========================================================================== #
ps.part("B", "Build the grader and the classifier", """
The classifier reads one legacy entry and returns four fields: `part_category` and
`whole_category` (ids from `A.category_menu()`), `relation` (an id from
`A.relation_menu()`) and `is_parthood` (`true`/`false`). The guidelines a scorer can
report are in `A.PARTWHOLE_RULEBOOK`; `A.RULE_FOR_RELATION` names, for each *correct*
relation, the guideline a wrong answer violated.
""")
ps.code("""
for rule in A.PARTWHOLE_RULEBOOK:
    print(f"{rule.id:30s} {rule.description[:88]}")
print()
print(A.category_menu()); print(); print(A.relation_menu())
""")

ps.problem("B1", "A diagnostic scorer that separates naming from parthood", 14, """
Implement `norm_id(text) -> str` (lower-case, strip surrounding whitespace, quotes,
backticks and a trailing full stop, and turn runs of spaces/underscores into single
hyphens, so `"Amount of Matter"` → `"amount-of-matter"`) and
`partwhole_scorer(gold, pred) -> ev.ScoreReport`:

| stage | outcome | score | `violated` |
|---|---|---|---|
| format | a category not in `A.ARGUMENT_CATEGORIES`, a relation not in `A.RELATION_IDS`, or `is_parthood` not one of true/false/yes/no (after `norm_id`) | 0.0 | `["use-the-menus"]` |
| content | otherwise: `0.1·part_ok + 0.1·whole_ok + 0.4·relation_ok + 0.4·parthood_ok` | — | in this order: `"identify-categories-first"` if either category is wrong; `A.RULE_FOR_RELATION[gold.gold_relation]` if the relation is wrong; `"check-genuine-parthood"` if the parthood verdict is wrong |

The notes are what GEPA reads, so make them useful: when the relation is wrong, include
the correct relation's **test question** (`ch6.relation_by_id(...).test`); when the
answer contradicts itself — the relation it named has a parthood flag different from its
own `is_parthood` — say so with the word **"contradicts"**.

Why weight parthood as heavily as the relation name? Because only the parthood verdict
decides what may be *inferred* downstream (Problem A1); a wrong name with the right
verdict is a tidy-up, a wrong verdict is a wrong search result.
""", auto_points=12)
ps.todo(
    stub="""
    def norm_id(text) -> str:
        # TODO
        raise NotImplementedError

    PARTHOOD_WORDS = {"true": True, "yes": True, "false": False, "no": False}

    def partwhole_scorer(gold, pred) -> ev.ScoreReport:
        part = norm_id(getattr(pred, "part_category", ""))
        whole = norm_id(getattr(pred, "whole_category", ""))
        relation = norm_id(getattr(pred, "relation", ""))
        parthood = norm_id(getattr(pred, "is_parthood", ""))
        # TODO: the two stages from the table
        raise NotImplementedError
    """,
    solution="""
    def norm_id(text) -> str:
        text = str(text if text is not None else "").strip().rstrip(".").strip()
        text = text.strip("`'\\"").strip().lower()
        return re.sub(r"[\\s_]+", "-", text)

    PARTHOOD_WORDS = {"true": True, "yes": True, "false": False, "no": False}

    def partwhole_scorer(gold, pred) -> ev.ScoreReport:
        part = norm_id(getattr(pred, "part_category", ""))
        whole = norm_id(getattr(pred, "whole_category", ""))
        relation = norm_id(getattr(pred, "relation", ""))
        parthood = norm_id(getattr(pred, "is_parthood", ""))

        bad = [f"{name}={value!r}" for name, value, ok in [
            ("part_category", part, part in A.ARGUMENT_CATEGORIES),
            ("whole_category", whole, whole in A.ARGUMENT_CATEGORIES),
            ("relation", relation, relation in A.RELATION_IDS),
            ("is_parthood", parthood, parthood in PARTHOOD_WORDS)] if not ok]
        if bad:
            return ev.ScoreReport(0.0, [f"Not in the menus: {', '.join(bad)}. Answer with "
                                        f"the listed ids only, and true or false."],
                                  ["use-the-menus"])

        said_parthood = PARTHOOD_WORDS[parthood]
        part_ok, whole_ok = part == gold.part_category, whole == gold.whole_category
        relation_ok = relation == gold.gold_relation
        parthood_ok = said_parthood == bool(gold.gold_parthood)
        notes, violated = [], []
        if not (part_ok and whole_ok):
            notes.append(f"Categories: answered part={part}, whole={whole}; correct is "
                         f"part={gold.part_category}, whole={gold.whole_category}.")
            violated.append("identify-categories-first")
        if not relation_ok:
            correct = ch6.relation_by_id(gold.gold_relation)
            notes.append(f"Relation: answered {relation}, correct is {correct.id} "
                         f"(test: {correct.test})")
            violated.append(A.RULE_FOR_RELATION[gold.gold_relation])
        if not parthood_ok:
            notes.append(f"Parthood: answered {said_parthood}, correct is "
                         f"{bool(gold.gold_parthood)}. Not every 'part of' is parthood.")
            violated.append("check-genuine-parthood")
        if ch6.relation_by_id(relation).parthood != said_parthood:
            notes.append(f"The answer contradicts itself: {relation} is "
                         f"{'' if ch6.relation_by_id(relation).parthood else 'not '}parthood, "
                         f"but is_parthood={said_parthood}.")
        score = 0.1 * part_ok + 0.1 * whole_ok + 0.4 * relation_ok + 0.4 * parthood_ok
        return ev.ScoreReport(round(score, 4), notes, violated)
    """)
ps.check("B1", """
assert norm_id("Amount of Matter") == "amount-of-matter"
assert norm_id(" `constituted_of`. ") == "constituted-of"
marble = next(ex for ex in dev if ex.id == "marble-bust")
hoard = next(ex for ex in dev if ex.id == "coin-hoard")
P = lambda p, w, r, h: dspy.Prediction(part_category=p, whole_category=w, relation=r, is_parthood=h)
cases = [
    (marble, P("amount-of-matter", "physical-object", "constituted-of", "false"), 1.0, []),
    (marble, P("Amount of Matter", "physical_object", " Constituted-Of ", "No"), 1.0, []),
    (marble, P("amount-of-matter", "physical-object", "component-of", "true"), 0.2,
     ["constitution-not-parthood", "check-genuine-parthood"]),
    (marble, P("amount-of-matter", "physical-object", "constituted-of", "true"), 0.6,
     ["check-genuine-parthood"]),
    (marble, P("physical-object", "physical-object", "constituted-of", "false"), 0.9,
     ["identify-categories-first"]),
    (marble, P("amount-of-matter", "physical-object", "part-of", "true"), 0.0, ["use-the-menus"]),
    (marble, P("amount-of-matter", "physical-object", "constituted-of", "maybe"), 0.0,
     ["use-the-menus"]),
    (marble, P("stuff", "physical-object", "constituted-of", "false"), 0.0, ["use-the-menus"]),
    (marble, P("", "", "", ""), 0.0, ["use-the-menus"]),
    (hoard, P("physical-object", "physical-object", "component-of", "true"), 0.5,
     ["identify-categories-first", "member-for-collections"]),
    (hoard, P("physical-object", "collection", "member-of", "false"), 0.6,
     ["check-genuine-parthood"]),
]
for gold, pred, score, violated in cases:
    r = partwhole_scorer(gold, pred)
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (gold.id, pred, r.score, r.violated)
    assert all(v in A.PARTWHOLE_RULEBOOK for v in r.violated)
wrong = partwhole_scorer(marble, cases[2][1])
assert ch6.relation_by_id("constituted-of").test in "\\n".join(wrong.notes), "name the test question"
assert any("contradicts" in n for n in partwhole_scorer(marble, cases[3][1]).notes)
assert not any("contradicts" in n for n in partwhole_scorer(marble, cases[0][1]).notes)
""")

ps.problem("B2", "The classifier as a DSPy program", 7, """
Write a signature `PartWholeClassification` with inputs `statement`, `categories`,
`relations` and outputs `part_category`, `whole_category`, `relation`, `is_parthood`,
and a factory `PartWholeClassifier(instruction)` returning a `dspy.Module` with a single
`dspy.Predict` whose instruction is `instruction`. The field descriptions are part of the
prompt — write them as you would brief a new cataloguer (manual marks). Configure Claude
and run the program once on `train[0]`.
""", auto_points=4)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    # TODO: class PartWholeClassification(dspy.Signature): ...
    # TODO: def PartWholeClassifier(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: PartWholeClassifier()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    class PartWholeClassification(dspy.Signature):
        \"\"\"Type one legacy 'part of' entry from a museum catalogue.\"\"\"

        statement: str = dspy.InputField(desc="one legacy catalogue entry that says 'X is part of Y'")
        categories: str = dspy.InputField(desc="the category ids you may use, one per line: id: gloss")
        relations: str = dspy.InputField(desc="the relation ids you may use, one per line: id: example")
        part_category: str = dspy.OutputField(desc="the category id of X, exactly as listed")
        whole_category: str = dspy.OutputField(desc="the category id of Y, exactly as listed")
        relation: str = dspy.OutputField(desc="the relation id, exactly as listed, e.g. member-of")
        is_parthood: str = dspy.OutputField(
            desc="true or false: is this relation genuine parthood (not constitution, "
                 "participation, containment or location)?")

    def PartWholeClassifier(instruction: str = BASELINE_INSTRUCTION):
        class _Classifier(dspy.Module):
            def __init__(self):
                super().__init__()
                self.classify = dspy.Predict(
                    PartWholeClassification.with_instructions(instruction))

            def forward(self, statement: str, categories: str, relations: str):
                return self.classify(statement=statement, categories=categories,
                                     relations=relations)

        return _Classifier()

    lm = llm.configure_dspy()
    smoke = PartWholeClassifier()(**train[0].inputs())
    print(train[0].statement, "->", smoke.part_category, "/", smoke.whole_category, "/",
          smoke.relation, "/", smoke.is_parthood)
    """)
ps.check("B2", """
assert set(PartWholeClassification.input_fields) == {"statement", "categories", "relations"}
assert {"part_category", "whole_category", "relation", "is_parthood"} <= set(
    PartWholeClassification.output_fields)
program = PartWholeClassifier("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert all(isinstance(getattr(smoke, f), str) and getattr(smoke, f).strip()
           for f in ("part_category", "whole_category", "relation", "is_parthood"))
""")

ps.problem("B3", "Baseline on the development split, with its cost", 9, """
Evaluate the baseline program on `dev` with `ev.evaluate_dataset`, inside
`llm.meter(lm)`. Store the result in `baseline_dev` and the cost in `baseline_dev_cost`,
and show the per-item rows **with the model's four answers next to gold** (re-run the
program on each item — DSPy's cache makes that free).

Then write an **error analysis** of *your* run: for each non-perfect item, which
guideline was violated and why you think Claude answered as it did. Separate three
kinds: format problems, genuine modelling errors, and **disagreements with the museum's
convention** (answers a published taxonomy would defend). They call for different fixes.
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(PartWholeClassifier(), dev, partwhole_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    rows = []
    for ex, row in zip(dev, baseline_dev["rows"]):
        p = PartWholeClassifier()(**ex.inputs())          # cached: no new call
        rows.append({**row, "answer": f"{p.part_category} / {p.whole_category} / "
                                      f"{p.relation} / {p.is_parthood}",
                     "gold": f"{ex.part_category} / {ex.whole_category} / "
                             f"{ex.gold_relation} / {ex.gold_parthood}"})
    pd.DataFrame(rows)
    """)
ps.check("B3", """
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
The analysis to hand in is of *your* run; what a live run is likely to show:

* **Format** (score 0.0, `use-the-menus`): the relation written as a phrase
  ("constituted of", which `norm_id` rescues) or as a new id (`part-of`,
  `spatial-part-of`, `located-within`), or `is_parthood` answered with a sentence.
  Fixed by stating the output contract, not by teaching mereology.
* **Genuine modelling errors**: *cat-case* is the likeliest — "part of the contents of
  display case 7" read as component-of, or the case treated as a region
  (located-in); *totem-garden* may be typed contained-in because a garden has
  boundaries; *coin-hoard* occasionally becomes component-of if the hoard is read as
  one object. These are category errors first (`identify-categories-first`), and the
  relation follows from them — exactly the chapter's claim.
* **Disagreements with the convention**: a model that knows the literature may say
  `member-of` is *not* parthood, or that `located-in` and `contained-in` *are*
  (spatial) parthood — Keet & Artale's own taxonomy, for instance, separates
  mereological parthood (including spatial containment and location) from meronymic
  relations such as membership and constitution. These answers are defensible; they
  are wrong only relative to the museum's adopted table. The fix is to *state the
  convention* in the instruction, not to hope the model guesses it.

If the baseline is near 1.0 on dev, say so: eight items resolve differences of about
±0.06 per item, and a strong model may already type most of them correctly. Cost:
8 calls, in the order of $0.2–0.4 — the unit price for every later comparison.
""")

# =========================================================================== #
ps.part("C", "Optimise honestly — and let the taxonomy compete", """
The rules for this part: **optimise on `train`, select on `dev`, report on `test`** —
and put a cost and a noise estimate next to every number.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 10, """
1. Build the GEPA feedback metric from your scorer and `A.PARTWHOLE_RULEBOOK`, and a
   separate reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare baseline and tuned on **`test`** with `opt.compare` (store as `c1`) and print
   `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch06_partwhole_instruction.txt"`.

In writing: read the instruction diff. Which guidelines did GEPA put into words, which
did it miss, did it state the museum's parthood convention, and did it memorise any
training entry?
""", auto_points=5)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch06_partwhole_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(partwhole_scorer, A.PARTWHOLE_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(PartWholeClassifier(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(PartWholeClassifier(), tuned, test, partwhole_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch06_partwhole_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
ids = lambda rows: {ex.id for ex in rows}
assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test)
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 100
""")
ps.written("""
What to look for in the diff (your wording will differ):

* **Made explicit:** the output contract (ids only, `true`/`false`), "decide the two
  categories first", and the parthood flags for whichever relations the baseline got
  wrong on `train` — typically "constitution, containment, location and participation
  are not parthood". These come straight from the `VIOLATED GUIDELINE` lines and the
  relation test questions in the notes.
* **Missed:** GEPA can only learn from failures it sees. If Claude typed every
  `member-of` item on `train` correctly, the membership convention never appears in
  feedback and will be absent from the instruction, even though a test item needs it.
  With one item per relation per split, *each* rule is exercised by exactly one
  training item — a thin signal.
* **Memorised:** sentences naming training entries ("the linseed oil…", "archive box
  AB-117") are over-fitting; they cost tokens on every call and do nothing on test.

A test delta of ≈ 0 is a legitimate finding when the baseline is already near ceiling;
report it as such, with C3's noise estimate beside it.
""")

ps.problem("C2", "Four designs, one table: who decides the relation?", 9, """
Add two contenders to baseline and GEPA:

* **guidelines** — `PartWholeClassifier(A.PARTWHOLE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION))`;
* **taxonomy** — Claude answers *only* the categories and whether the part is removable
  contents (`separable`), and the chapter's procedure decides the rest. Implement
  `complete_from_categories(part, whole, separable) -> dspy.Prediction` (normalise with
  `norm_id`; if both categories are in the menu, `relation = ch6.classify_partwhole(...)`
  and `is_parthood` from the taxonomy as `"true"`/`"false"`; otherwise `relation=""`,
  `is_parthood=""`), and a program `TaxonomyBackedClassifier()` with a single
  `dspy.Predict` over a signature with inputs `statement`, `categories` and outputs
  `part_category`, `whole_category`, `separable`, whose `forward` returns
  `complete_from_categories(...)`.

Evaluate all four on `test`, each inside its own `llm.meter`, and build `c2` with columns
`program` (`"baseline"`, `"guidelines"`, `"gepa"`, `"taxonomy"`), `test_mean`,
`violations`, `eval_usd`, `optimisation_usd` (GEPA's cost for `"gepa"`, else 0) and
`instruction_chars`.

In writing: which design would you deploy for the 41,000-record migration, and what
would change your mind? Consider score, cost per record, what happens when the
convention changes, and the A2 gaps.
""", auto_points=3)
ps.todo(
    stub="""
    guidelines_instruction = A.PARTWHOLE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)

    def complete_from_categories(part, whole, separable) -> dspy.Prediction:
        # TODO
        raise NotImplementedError

    # TODO: class ArgumentCategories(dspy.Signature) and def TaxonomyBackedClassifier()
    c2 = None    # TODO
    """,
    solution="""
    guidelines_instruction = A.PARTWHOLE_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)

    def complete_from_categories(part, whole, separable) -> dspy.Prediction:
        part, whole = norm_id(part), norm_id(whole)
        removable = PARTHOOD_WORDS.get(norm_id(separable), False)
        if part in A.ARGUMENT_CATEGORIES and whole in A.ARGUMENT_CATEGORIES:
            relation = ch6.classify_partwhole(part, whole, removable)
            parthood = str(ch6.relation_by_id(relation).parthood).lower()
        else:
            relation, parthood = "", ""
        return dspy.Prediction(part_category=part, whole_category=whole,
                               relation=relation, is_parthood=parthood)

    class ArgumentCategories(dspy.Signature):
        \"\"\"Give the categories of the two arguments of a legacy 'part of' entry.\"\"\"

        statement: str = dspy.InputField(desc="one legacy catalogue entry that says 'X is part of Y'")
        categories: str = dspy.InputField(desc="the category ids you may use, one per line: id: gloss")
        part_category: str = dspy.OutputField(desc="the category id of X, exactly as listed")
        whole_category: str = dspy.OutputField(desc="the category id of Y, exactly as listed")
        separable: str = dspy.OutputField(
            desc="true if X is removable contents of Y (letters in a box), else false")

    def TaxonomyBackedClassifier(instruction: str = "Categorise both arguments of the "
                                 "catalogue statement."):
        class _TaxonomyBacked(dspy.Module):
            def __init__(self):
                super().__init__()
                self.categorise = dspy.Predict(ArgumentCategories.with_instructions(instruction))

            def forward(self, statement: str, categories: str, relations: str = ""):
                p = self.categorise(statement=statement, categories=categories)
                return complete_from_categories(p.part_category, p.whole_category, p.separable)

        return _TaxonomyBacked()

    contenders = {"baseline": PartWholeClassifier(),
                  "guidelines": PartWholeClassifier(guidelines_instruction),
                  "gepa": tuned,
                  "taxonomy": TaxonomyBackedClassifier()}
    rows = []
    for name, program in contenders.items():
        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, test, partwhole_scorer)
        rows.append({"program": name, "test_mean": result["mean_score"],
                     "violations": result["violations"], "eval_usd": cost["usd"],
                     "optimisation_usd": gepa_cost["usd"] if name == "gepa" else 0.0,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    c2
    """)
ps.check("C2", """
p = complete_from_categories("Amount of Matter", "physical_object", "false")
assert (p.relation, p.is_parthood) == ("constituted-of", "false")
p = complete_from_categories("physical-object", "physical-object", "yes")
assert (p.relation, p.is_parthood) == ("contained-in", "false")
p = complete_from_categories("physical-object", "collection", "no")
assert (p.relation, p.is_parthood) == ("member-of", "true")
assert complete_from_categories("stuff", "region", "no").relation == ""
assert partwhole_scorer(next(ex for ex in test if ex.id == "silver-salver"),
                        complete_from_categories("amount-of-matter", "physical-object", "no")).score == 1.0
program = TaxonomyBackedClassifier()
assert len(list(program.named_predictors())) == 1
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "guidelines", "gepa", "taxonomy"}
assert {"test_mean", "violations", "eval_usd", "optimisation_usd", "instruction_chars"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines", "taxonomy"], "optimisation_usd"].eq(0).all()
""")
ps.written("""
The taxonomy-backed design has the strongest engineering case, whatever the eight-item
scores say: it asks Claude only for what needs judgement (what *kind* of thing each
argument is, and whether the part is removable contents), and it makes the answer
**incapable of contradicting the convention** — a `constituted-of` answer can never
come with `is_parthood = true`. When the data office revises the table (say, to adopt
Keet & Artale's flags), the taxonomy design changes with one data edit, while the
prompt-based designs need re-writing, re-optimising and re-evaluating. Its errors are
category errors, which are the ones a curator can review quickly.

What would change my mind: (i) if its test score is clearly *below* the prompt designs
beyond the C3 noise — that would mean the category step itself is the hard part and the
full relation context helps Claude categorise; (ii) the A2 gaps — for fallback pairs it
returns `component-of` confidently, so it needs the review-queue rule from A2, whereas an
end-to-end model might at least hedge. Among the prompt designs, the hand-written
guidelines usually recover most of GEPA's gain at zero optimisation cost; GEPA pays only
if its instruction fixes failures the guidelines do not anticipate. At 41,000 records,
instruction length is paid 41,000 times — put `instruction_chars` × records next to the
score before deciding.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 7, """
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, used via
`dspy.context(lm=fresh)`), run the GEPA-tuned and the taxonomy-backed programs on `test`
three times each, inside `llm.meter(fresh)` (store as `c3_cost`); record the mean
scores in `runs = {"gepa": [..3..], "taxonomy": [..3..]}`.

Set `verdict_c3` to `"significant"` if `|mean_taxonomy − mean_gepa| > 2 ·
max(sd_gepa, sd_taxonomy)` (sample standard deviations), else `"not significant"`. In
writing: what does this say about your C2 decision, and what would a credible
evaluation of the migration classifier need before it runs on 41,000 records?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"gepa": [], "taxonomy": []}
    # TODO: fill runs (inside llm.meter(fresh) as c3_cost), then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    import statistics as st

    fresh = llm.dspy_lm(cache=False)
    runs = {"gepa": [], "taxonomy": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, partwhole_scorer)["mean_score"])
            runs["taxonomy"].append(
                ev.evaluate_dataset(TaxonomyBackedClassifier(), test, partwhole_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["taxonomy"][0] - stats["gepa"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["taxonomy"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
import statistics as _st
assert set(runs) == {"gepa", "taxonomy"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
assert {"calls", "usd"} <= set(c3_cost)
_m = {k: _st.mean(v) for k, v in runs.items()}
_s = {k: _st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["taxonomy"] - _m["gepa"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
""")
ps.written("""
Two things can happen and both are informative. If the spread is zero or tiny for both
programs (quite possible: at this difficulty Claude may answer the same way every time),
the rule's "2 × sd" collapses and even a one-item difference reads as *significant* — a
reminder that a noise estimate from 3 runs on 8 items is itself noisy, and that a zero
sd is not proof of determinism. If the spread is a few hundredths, it is as large as the
difference between designs and the C2 ranking is not evidence either way — then decide
on the engineering grounds (convention changes, contradictions impossible by
construction), not on the score.

A credible evaluation before the 41,000-record run needs: many more labelled entries,
drawn from the real catalogue rather than written to be clean, *including* the A2 fallback
cases; per-relation and per-category results rather than one mean; repeated runs reported
as mean ± sd or with a paired bootstrap over items; an estimate of cost per 1,000 records;
and a review-queue policy with a measured precision (how many queued entries were really
wrong). The honest sentence for this problem set is "on 8 held-out entries, design X
scored m ± s over 3 runs at $c per run" — not "design X is more accurate".
""")

# =========================================================================== #
ps.part("D", "A chaining agent, and the curator interview as an MDP", """
Two deliverables for the search and cataloguing teams. First, an agent that answers
*"is X part of Y?"* over the typed links, with every chain checked by the chapter's
`can_chain`. Second, a plan for aligning *new* catalogue classes to a foundational
category by asking a curator yes/no questions — modelled as a stochastic MDP whose
optimal policy is a decision tree.
""")
ps.code("""
ws_demo = A.CatalogueWorkspace()
tools_demo = {t.name: t for t in A.build_catalogue_tools(ws_demo)}
print(tools_demo["trace_upward"].invoke({"item": "pendulum"}))
print(tools_demo["check_chaining"].invoke({"first": "component-of", "second": "member-of"}))
print("tool calls logged:", ws_demo.log.names())
pd.DataFrame([{"id": q, "question": text, "part": p, "whole": w, "gold": g}
              for q, p, w, text, g in A.CHAIN_QUERIES])
""")

ps.problem("D1", "Build and evaluate the chaining agent", 12, """
1. Write `CHAINING_PROMPT`, the agent's system prompt. The agent must trace the path
   from the part upwards with its tools, answer *no* if the whole is not on the path,
   decide a single link from the relation's parthood flag, check **every consecutive
   pair** of a longer path with `check_chaining`, and end with a JSON object
   `{"verdict": "yes" | "no", "relations": [...the relations on the path...], "reason": "..."}`.
2. Write `parse_answer(text) -> dict` returning `{"verdict": ..., "relations": [...]}`
   from the agent's final text (the JSON may be fenced or surrounded by prose; use the
   last object that has a `verdict`); the verdict is `"yes"`, `"no"` or `"unparseable"`,
   and `relations` is a list of `norm_id`-ed strings (empty if absent).
3. For every query in `A.CHAIN_QUERIES`, build a fresh `A.CatalogueWorkspace()`, its
   tools, an agent (`agents.build_agent(ws, system_prompt=..., tools=...)`), run it on
   the question followed by the two catalogue ids, and collect `d1` with columns `id`,
   `gold`, `predicted`, `correct`, `relations`, `path_ok` (the reported relations equal
   the true path from part to whole), `tool_calls`, `chain_checks` (number of
   `check_chaining` calls) and `usd_estimate` (`llm.chat_usage(run.messages)`).

In writing: report accuracy with its sample size and the cost per question, and examine
every error, every `path_ok == False` and every multi-link query answered without a
chain check. Then the uncomfortable question: once the links are typed, does this task
need an LLM at all?
""", auto_points=5)
ps.todo(
    stub="""
    CHAINING_PROMPT = \"\"\"TODO\"\"\"

    def parse_answer(text: str) -> dict:
        # TODO
        raise NotImplementedError

    d1 = None   # TODO: run the agent on every query
    """,
    solution="""
    CHAINING_PROMPT = \"\"\"\\
    You answer questions of the form "is X part of Y?" for the Aldermoor Museum's
    collections search, using only the typed catalogue links, which you read with your
    tools. "Part of" means genuine parthood as defined by the part_whole_relations tool.

    Procedure:
    1. Call trace_upward on X. If Y does not appear as a whole on the path, the answer
       is "no".
    2. Keep the links from X up to Y. If there is one link, the answer is "yes" exactly
       when that relation is parthood (read part_whole_relations).
    3. If there are several links, call check_chaining on the first two relations; if
       valid, the result is the same relation, so check it against the next relation,
       and so on. The answer is "yes" only if every check is valid.
    Never assume "part of" is transitive; the tools decide.

    End your reply with a JSON object and nothing after it:
    {"verdict": "yes" | "no", "relations": ["relations on the path from X to Y"], "reason": "one sentence"}
    \"\"\"

    def parse_answer(text: str) -> dict:
        for blob in reversed(re.findall(r"\\{[^{}]*\\}", text or "")):
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or "verdict" not in data:
                continue
            verdict = norm_id(data.get("verdict"))
            relations = data.get("relations") or []
            return {"verdict": verdict if verdict in {"yes", "no"} else "unparseable",
                    "relations": [norm_id(r) for r in relations]
                                 if isinstance(relations, list) else []}
        return {"verdict": "unparseable", "relations": []}

    def true_path(part, whole):
        path = []
        for link in A.CatalogueWorkspace().upward(part):
            path.append(link["relation"])
            if link["whole"] == whole:
                return path
        return []

    rows = []
    for qid, part, whole, question, gold in A.CHAIN_QUERIES:
        ws = A.CatalogueWorkspace()
        agent, _ = agents.build_agent(ws, system_prompt=CHAINING_PROMPT,
                                      tools=A.build_catalogue_tools(ws))
        run = agents.run_agent(agent, ws, f"{question} Catalogue ids: part = {part!r}, "
                                          f"whole = {whole!r}.")
        answer = parse_answer(run.answer)
        names = ws.log.names()
        rows.append({"id": qid, "gold": gold, "predicted": answer["verdict"],
                     "correct": answer["verdict"] == gold, "relations": answer["relations"],
                     "path_ok": answer["relations"] == true_path(part, whole),
                     "tool_calls": len(names), "chain_checks": names.count("check_chaining"),
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(f"accuracy {d1.correct.mean():.2f} on n={len(d1)}; "
          f"cost ≈ ${d1.usd_estimate.sum():.3f} total")
    d1
    """)
ps.check("D1", """
assert parse_answer('{"verdict": "yes", "relations": ["sub-quantity-of", "sub-quantity-of"], '
                    '"reason": "x"}') == {"verdict": "yes",
                                          "relations": ["sub-quantity-of", "sub-quantity-of"]}
assert parse_answer('Checked.\\n```json\\n{"verdict": "No", "relations": ["Component of", '
                    '"member_of"], "reason": "x"}\\n```') == {
    "verdict": "no", "relations": ["component-of", "member-of"]}
assert parse_answer('prose {"note": 1} then {"verdict": "yes"}')["verdict"] == "yes"
assert parse_answer('{"verdict": "maybe", "relations": []}')["verdict"] == "unparseable"
assert parse_answer("I think yes.") == {"verdict": "unparseable", "relations": []}
assert isinstance(d1, pd.DataFrame) and len(d1) == len(A.CHAIN_QUERIES)
assert {"id", "gold", "predicted", "correct", "relations", "path_ok", "tool_calls",
        "chain_checks", "usd_estimate"} <= set(d1.columns)
assert set(d1["predicted"]) <= {"yes", "no", "unparseable"}
assert (d1["correct"] == (d1["predicted"] == d1["gold"])).all()
_ws = A.CatalogueWorkspace()
for (qid, part, whole, _, _), (_, row) in zip(A.CHAIN_QUERIES, d1.iterrows()):
    path = []
    for link in _ws.upward(part):
        path.append(link["relation"])
        if link["whole"] == whole:
            break
    assert row["path_ok"] == (list(row["relations"]) == path), qid
""")
ps.written("""
With the procedure above Claude should answer most or all of the eight correctly (report
it as "k/8", not a percentage), with 3–6 tool calls and roughly $0.10–0.25 per question
at opus-5 list prices — *estimate*, check your `usd_estimate` column. The instructive
cases:

* **painting-loan** (one link, `participates-in`) is the one `check_chaining` cannot
  decide: there is no pair to check. The agent must read the parthood flag from
  `part_whole_relations`; an agent that pattern-matches "part of the loan" says *yes*.
* **oil-stock** needs two chain checks (three `sub-quantity-of` links). A single check
  followed by "and so on" is a guess that happened to be right; `chain_checks` shows it.
* **bronze-wing** fails at the first pair (constitution is not parthood); an agent
  that reports the verdict without the path (`path_ok == False`) has given the search
  team nothing to audit.

The uncomfortable answer: once the links are typed, **no** — the verdict is A1's
`sound_closure`, a deterministic computation that is free, instant and always right
under the convention. The agent earns its cost only where the input is language (a
curator's free-text question, a new untyped entry) and in explaining the verdict; the
verdict itself should come from the closure, with the agent's explanation checked
against it. That is the chapter's lesson in engineering form: encode the distinction in
a tool or a table, not in a prompt.
""")

ps.problem("D2", "Deriving the decision tree — and testing the claim", 8, """
`A.CategoryDiagnosisMDP` aligns a new class to one of seven DOLCE-style categories. The
state is the set of categories still consistent with the curator's answers; the actions
ask a decision question that splits the set, or commit; the answer is **stochastic**
(probability = prior mass of the categories giving it); each question costs
`question_cost`, and committing earns the probability of being right.

1. Solve the uniform-prior MDP at `question_cost=0.05` with `mdp.value_iteration`; print
   the tree (`M.decision_tree(pi)`). Compute the Q-value of every action at the root in
   `root_q` (`{action: value}`) and set `tied_first` to the sorted list of questions
   whose root Q-value is within `1e-9` of the best. Implement `expected_questions(M,
   policy)` — the exact expected number of questions the policy asks (recurse over the
   tree; do not simulate).
2. A colleague argues: "under a uniform prior one question raises accuracy by at most
   1/7, so a curator should never be asked once a question costs ≥ 1/7". Derive the
   actual threshold `c*` above which committing blind beats the full tree, as a function
   of the number of categories `k` and the expected number of questions `q` of the full
   tree; implement it as `blind_threshold(q, k)`.
3. Verify: sweep `question_cost` over `np.linspace(0, 0.5, 51)` and record in `d2`
   (columns `question_cost`, `value`, `questions_in_tree`, `root_action`).

In writing: why is the colleague wrong? And what does `tied_first` do to the claim that
the MDP "derives DOLCE's decision tree"?
""", auto_points=4)
ps.todo(
    stub="""
    M = A.CategoryDiagnosisMDP(question_cost=0.05)
    # TODO (1): V, pi, root_q, tied_first, expected_questions

    def blind_threshold(q: float, k: int) -> float:
        # TODO (2)
        raise NotImplementedError

    d2 = None     # TODO (3)
    """,
    solution="""
    M = A.CategoryDiagnosisMDP(question_cost=0.05)
    V, pi = mdp.value_iteration(M)
    s0 = M.initial_state()

    def q_value(M, V, state, action):
        return sum(p * (r + M.gamma * V[ns]) for p, ns, r in M.transition(state, action))

    root_q = {a: q_value(M, V, s0, a) for a in M.actions(s0)}
    best = max(root_q.values())
    tied_first = sorted(a.split(":", 1)[1] for a, v in root_q.items()
                        if a != "commit" and abs(v - best) < 1e-9)
    for line in M.decision_tree(pi):
        print(line)

    def expected_questions(M, policy, state=None):
        state = state or M.initial_state()
        action = policy.get(state, "commit")
        if action == "commit":
            return 0.0
        return 1.0 + sum(p * expected_questions(M, policy, ns)
                         for p, ns, _ in M.transition(state, action))

    def blind_threshold(q: float, k: int) -> float:
        # full tree: accuracy 1, cost c*q  vs  blind: accuracy 1/k  =>  c* = (1 - 1/k) / q
        return (1 - 1 / k) / q

    rows = []
    for c in np.linspace(0, 0.5, 51):
        Mc = A.CategoryDiagnosisMDP(question_cost=float(c))
        Vc, pic = mdp.value_iteration(Mc)
        rows.append({"question_cost": round(float(c), 3), "value": round(Vc[Mc.initial_state()], 4),
                     "questions_in_tree": sum("?" in line for line in Mc.decision_tree(pic)),
                     "root_action": pic[Mc.initial_state()]})
    d2 = pd.DataFrame(rows)
    q = expected_questions(M, pi)
    print(f"V*(s0)={V[s0]:.4f}  root Q={ {a: round(v, 4) for a, v in root_q.items()} }")
    print(f"tied at the root: {tied_first};  E[questions]={q:.3f};  c*={blind_threshold(q, 7):.4f}")
    d2[(d2.question_cost >= 0.25) & (d2.question_cost <= 0.32)]
    """)
ps.check("D2", """
assert abs(V[M.initial_state()] - 0.85) < 1e-9
assert set(root_q) == set(M.actions(M.initial_state()))
assert tied_first == ["dependent", "happens", "spatial"]
assert abs(expected_questions(M, pi) - 3.0) < 1e-9
assert abs(blind_threshold(3, 7) - 2 / 7) < 1e-12 and abs(blind_threshold(2, 4) - 0.375) < 1e-12
assert isinstance(d2, pd.DataFrame) and len(d2) == 51
c_star = blind_threshold(expected_questions(M, pi), 7)
below, above = d2[d2.question_cost < c_star - 0.005], d2[d2.question_cost > c_star + 0.005]
assert (below.questions_in_tree == 6).all() and (below.root_action != "commit").all()
assert (above.questions_in_tree == 0).all() and (above.root_action == "commit").all()
""")
ps.written("""
**The threshold.** The full tree always ends with one category, so it earns accuracy 1
at expected cost `c·q`; committing blind earns `1/k`. Hence `c* = (1 − 1/k)/q`, and with
`k = 7`, `q = 3` that is `2/7 ≈ 0.286` — the sweep flips between 0.28 and 0.29, from a
six-question tree straight to "ask nothing". The colleague's `1/7` is the *myopic* value
of one question: it ignores that the first answer is what makes the next questions
worth asking. The value of a question includes the option value of the questions it
enables. (Under a uniform prior, every question that splits a set adds exactly `1/7` of
accuracy wherever it is asked, but costs `c` weighted by the probability of reaching it;
the whole tree is worth asking up to `2/7`, and no partial tree ever wins here.)

**The tie.** At the root, `happens`, `spatial` and `dependent` have *identical* Q-values
(0.85): each leads to a tree with three expected questions. The tree printed with
`happens` first — DOLCE's endurant/perdurant split — only because `happens` is listed
first and `max` keeps the first maximiser. So under a uniform prior and a flat cost, the
cost model does **not** derive DOLCE's tree; it derives a *set* of equally good trees of
which DOLCE's is one. Claiming more would be reading a tie-break as a discovery. Problem
D3 asks what extra information makes the endurant/perdurant question the unique best
start.
""")

ps.problem("D3", "The museum's interview plan: prior, curator minutes, and a missing question", 6, """
The museum's new classes are not uniform over categories (`A.CATALOGUE_CLASS_PRIOR`),
and its curators do not find all questions equally easy (`A.CURATOR_MINUTES`, median
minutes per reliable answer). Value one curator minute at `RATE = 0.01` (a hundredth of a
correct alignment).

1. Implement `evaluate_tree(M, policy, minutes) -> (accuracy, expected_minutes)`, exact
   by recursion, where `minutes` gives the curator minutes of each question.
2. Build four settings, each solved with value iteration: `"textbook"` (uniform prior,
   flat cost 0.05), `"museum-flat"` (museum prior, flat cost 0.05), `"museum-timed"`
   (museum prior, cost `RATE · minutes` per question) and `"museum-timed-no-happens"`
   (as museum-timed, but the `happens` question is not available). Evaluate **every
   setting's policy under the museum-timed MDP where possible** — i.e. the real prior —
   except `"museum-timed-no-happens"`, which is evaluated in its own MDP. Build `d3`
   (index: setting) with columns `root_question`, `accuracy`, `expected_minutes`, `value`
   (V*(s0) of the setting's own MDP).
3. Set `inseparable` to the set of categories that no remaining question can tell apart
   once `happens` is removed.

In writing: which interview plan would you give the cataloguers, and what does this
say about *why* foundational ontologies start with the endurant/perdurant distinction?
What does the MDP still leave out?
""", auto_points=3)
ps.todo(
    stub="""
    RATE = 0.01

    def evaluate_tree(M, policy, minutes, state=None):
        # TODO (1)
        raise NotImplementedError

    d3 = None           # TODO (2)
    inseparable = None  # TODO (3)
    """,
    solution="""
    RATE = 0.01

    def evaluate_tree(M, policy, minutes, state=None):
        state = state or M.initial_state()
        action = policy.get(state, "commit")
        if action == "commit":
            return M.commit_accuracy(state.candidates), 0.0
        question = action.split(":", 1)[1]
        accuracy, spent = 0.0, minutes[question]
        for p, ns, _ in M.transition(state, action):
            a, m = evaluate_tree(M, policy, minutes, ns)
            accuracy += p * a
            spent += p * m
        return accuracy, spent

    timed_cost = {q: RATE * m for q, m in A.CURATOR_MINUTES.items()}
    reduced = tuple(q for q in A.CURATOR_MINUTES if q != "happens")
    settings = {
        "textbook": A.CategoryDiagnosisMDP(0.05),
        "museum-flat": A.CategoryDiagnosisMDP(0.05, prior=A.CATALOGUE_CLASS_PRIOR),
        "museum-timed": A.CategoryDiagnosisMDP(timed_cost, prior=A.CATALOGUE_CLASS_PRIOR),
        "museum-timed-no-happens": A.CategoryDiagnosisMDP(
            {q: timed_cost[q] for q in reduced}, questions=reduced,
            prior=A.CATALOGUE_CLASS_PRIOR),
    }
    real = settings["museum-timed"]
    rows, policies = {}, {}
    for name, Ms in settings.items():
        Vs, pis = mdp.value_iteration(Ms)
        policies[name] = pis
        judge = Ms if name == "museum-timed-no-happens" else real
        accuracy, spent = evaluate_tree(judge, pis, A.CURATOR_MINUTES)
        rows[name] = {"root_question": pis[Ms.initial_state()].split(":", 1)[-1],
                      "accuracy": round(accuracy, 4), "expected_minutes": round(spent, 3),
                      "value": round(Vs[Ms.initial_state()], 4)}
    d3 = pd.DataFrame.from_dict(rows, orient="index")

    answers = {c.id: tuple(ch6.category_answers(c.id)[q] for q in reduced) for c in ch6.CATEGORIES}
    inseparable = {c for c in answers if list(answers.values()).count(answers[c]) > 1}
    print("indistinguishable without 'happens':", inseparable)
    print("\\nthe museum-timed plan:")
    for line in real.decision_tree(policies["museum-timed"]):
        print(line)
    d3
    """)
ps.check("D3", """
assert isinstance(d3, pd.DataFrame)
assert set(d3.index) == {"textbook", "museum-flat", "museum-timed", "museum-timed-no-happens"}
assert {"root_question", "accuracy", "expected_minutes", "value"} <= set(d3.columns)
assert d3.loc["museum-flat", "root_question"] == "dependent"
assert d3.loc["museum-timed", "root_question"] == "happens"
assert abs(d3.loc["museum-timed", "value"]
           - (d3.loc["museum-timed", "accuracy"] - RATE * d3.loc["museum-timed", "expected_minutes"])) < 1e-3
assert d3.loc["museum-timed", "expected_minutes"] < d3.loc["museum-flat", "expected_minutes"]
assert d3.loc["museum-timed-no-happens", "value"] < d3.loc["museum-timed", "value"]
assert d3.loc["museum-timed-no-happens", "accuracy"] < 1.0
assert inseparable == {"physical-object", "process"}
_Mt = A.CategoryDiagnosisMDP({q: RATE * m for q, m in A.CURATOR_MINUTES.items()},
                             prior=A.CATALOGUE_CLASS_PRIOR)
_acc, _min = evaluate_tree(_Mt, {}, A.CURATOR_MINUTES)
assert abs(_acc - 0.52) < 1e-9 and _min == 0.0, "an empty policy commits at once"
""")
ps.written("""
**The plan.** Give the cataloguers the *museum-timed* tree: `happens?` first, then
`telic?` for happenings, and for things `spatial?` → `mass?` → `dependent?`. It
identifies every category (accuracy 1.0) for about 5.3 curator minutes per new class,
against about 6.1 minutes for the tree that is optimal under a flat cost, which starts
with `dependent?` — the question curators take longest to answer and argue most about.
It coincides with the textbook tree, which under the museum's prior is therefore not just
one of several optima but the best plan once time is counted.

**Why the endurant/perdurant split comes first.** Not because it is the most informative
question — under the museum's prior `dependent?` is marginally more informative, and under
a uniform prior three questions tie — but because it is informative *and cheap and
reliable to answer*. The MDP makes that argument explicit: the canonical order is optimal
for a cost model that prices the curator's effort, and nothing in the category structure
alone singles it out. Removing `happens` shows the other side: no remaining question
separates a process from a physical object (both are spatial, non-mass, independent,
atelic), so the best plan must *guess* between them — it commits to physical-object and
loses the 8 % of classes that are processes (accuracy ≈ 0.92), besides asking more.

**What the MDP leaves out.** Answers are assumed noise-free; in practice `dependent?` is
answered inconsistently, which a POMDP or a per-question error rate would penalise
further. The prior is an estimate from one year's schema log. Categories missing from the
seven-leaf tree (collection, region — see A2) cannot be reached at all, whatever the plan.
And the reward values every mis-alignment equally, while in the catalogue mistaking a
process for an object (it then acquires parts, a location, a valuation) is far worse
than confusing a feature with an object.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
