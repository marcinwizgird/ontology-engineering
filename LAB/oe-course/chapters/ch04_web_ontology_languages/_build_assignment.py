"""Build the Chapter 4 problem set: 05_assignment.ipynb + 05_solutions.ipynb.

Run from anywhere:  python chapters/ch04_web_ontology_languages/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 4 — The Web Ontology Languages",
    title="Axiomatising a conservancy's monitoring ontology inside OWL 2 profiles",
    coverage=("Keet §4.1 (OWL; Example 4.1, the African Wildlife Ontology), §4.2 (OWL 2 "
              "features; Example 4.2 and the simple-property restriction; §4.2.2 the EL / QL "
              "/ RL profiles); course notebooks 01–04 of this chapter. Tools: rdflib, the "
              "owlrl OWL 2 RL reasoner, owlready2, DSPy + GEPA, LangChain agents, value "
              "iteration."),
    scenario="""
    The **Mopane Ridge Conservancy** (a private game reserve) runs a wildlife-monitoring
    programme on top of an ontology that extends the African Wildlife Ontology of
    Example 4.1. The ontology is deployed as **three modules**, each consumed by a system
    that supports exactly one OWL 2 profile:

    | module | profile | consumer |
    |---|---|---|
    | species taxonomy | **EL** | classified nightly by an EL reasoner, because it must scale to the regional species list |
    | sightings access | **QL** | ontology-based data access over the camera-trap database — queries are rewritten into SQL |
    | field-report rules | **RL** | forward-chaining validation of ranger reports inside the triple store |

    The ecology team writes requirements in English ("Giraffes eat nothing but leaves",
    "A sighting is recorded by at most one camera trap"). Each one is tagged with the
    module it belongs to. Some cannot be said in that module's profile — and the
    programme's rule is that such a requirement is **escalated** to the ontology owner,
    never quietly replaced by something that fits. You are the ontology engineer. Your
    brief:

    1. **Understand the constraint.** Show why a metric that scores "right axiom" and
       "right profile" separately rewards silent substitution, and find the global OWL 2
       restriction that no per-axiom check can see.
    2. **Build the grader, then a Claude axiomatiser** that emits axioms in a fixed JSON
       language over the ontology's signature, with *escalate* as a legitimate answer.
    3. **Optimise honestly** with GEPA: train / dev / test, a budget, the cost, and the
       run-to-run noise.
    4. **Ship a module-building agent** whose actions change the artefact, grade the
       modules it builds, and use the **construction MDP** to decide how an agent should be
       rewarded when the profile makes the requirement impossible.

    The signature, the axiom language and its compiler to OWL, the profile table, the
    requirements corpus (24 requirements, split 8/8/8 by item, two escalations per split),
    entailment probes, the module workspace and its tools, and the construction MDP are
    provided in `ch4_agentic.py`.
    """,
    effort="10–12 hours",
    api_budget="≈ $5–12 estimated (not measured) on `claude-opus-5` for a full run: ≈ 170 "
               "DSPy calls at ≈ $0.02–0.05 each (GEPA with a 60-call budget is the largest "
               "line) plus three agent episodes at roughly $0.3–1 each. Re-running unchanged "
               "cells is free — DSPy caches identical requests — except the `cache=False` "
               "runs of C3.",
)

ps.setup("""
import dspy
import numpy as np
import pandas as pd
import ch4_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

train, dev, test = (A.build_dataset(s) for s in ("train", "dev", "test"))
EXAMPLES = {ex.id: ex for ex in train + dev + test}
GOLD_TABLE = pd.DataFrame(A.validate_gold())      # every gold label checked with rdflib/owlrl/owlready2
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
# The test gold lives in the module; do not study it while you tune.
GOLD_TABLE[GOLD_TABLE.split != "test"]
""")

ps.md("""
The axiom language the axiomatiser must answer in, and the OWL 2 profile table for it
(named class on the left-hand side; from the W3C *OWL 2 Profiles* specification):
""")
ps.code("""
print(A.AXIOM_FORMAT)
print()
print(A.profile_table_text())
""")
ps.code("""
# Every axiom compiles to real OWL 2 triples, and graph_profiles reads the profile off the RDF.
ax = A.Axiom.parse('{"operator": "only", "subject": "Giraffe", "property": "eats", "filler": "Leaf"}')
g = A.axiom_to_graph(ax)
print(ax, "->", sorted(A.graph_profiles(g)))
print(g.serialize(format="turtle"))
""")

# =========================================================================== #
ps.part("A", "Profiles as constraints", """
Before any model is involved, decide what a good answer *is* when the faithful axiom
and the module's profile disagree — and find the constraint a per-axiom check misses.
""")

ps.problem("A1", "What a split metric rewards: silent substitution", 10, """
The previous version of this project scored an axiom as **half for the right axiom,
half for staying in profile**:
`split_score = 0.5 * [equivalent to the faithful axiom] + 0.5 * [allowed in the target
profile]`, with 0.0 for anything that does not parse or is not an axiom (it had no
notion of escalating).

1. Implement `split_score(example, axiom_json) -> float`.
2. Take the four **escalation items of train and dev** (`ex.gold_axiom.operator ==
   "escalate"`). For each, write a `substitute`: an axiom in the signature that **is**
   allowed in the target profile but is **not** equivalent to the faithful axiom — the
   kind of thing a model eager to comply might produce. Store them in
   `substitutes = {item_id: Axiom}`.
3. Build `a1` with one row per (item, candidate) for the candidates `"faithful"`
   (`ex.faithful_axiom`), `"substitute"` and `"escalate"` (`A.Axiom("escalate")`), and
   columns `item`, `profile`, `candidate`, `axiom` (its string form), `in_profile`,
   `split_score` and `probe_passes` — `A.probe_holds([axiom], ex.probe)`, or `None`
   when the item has no probe.

In writing: (a) for each of EL, QL and RL, *why* does the profile forbid the construct
your items need — what would the consuming system lose? (b) Which of the three
candidates is most dangerous in production, which does `split_score` prefer, and what
does the `probe_passes` column suggest as a better basis for a reward?
""", auto_points=5)
ps.todo(
    stub="""
    def split_score(example, axiom_json) -> float:
        # TODO
        raise NotImplementedError

    substitutes = {
        # "item-id": A.Axiom(...),
    }
    a1 = None      # TODO
    """,
    solution="""
    def split_score(example, axiom_json) -> float:
        try:
            ax = A.Axiom.parse(axiom_json)
        except A.AxiomFormatError:
            return 0.0
        if ax.operator == "escalate":
            return 0.0
        return (0.5 * A.equivalent(ax, example.faithful_axiom)
                + 0.5 * A.in_profile(ax, example.profile))

    escalation_items = [ex for ex in train + dev if ex.gold_axiom.operator == "escalate"]
    substitutes = {
        "carnivores-eat-only-animals": A.Axiom("some", "Carnivore", "eats", "Animal"),
        "one-trap-per-sighting": A.Axiom("some", "Sighting", "recordedBy", "CameraTrap"),
        "warthogs-eat-some-grass": A.Axiom("only", "Warthog", "eats", "Grass"),
        "one-collar-each": A.Axiom("domain", property="wearsCollar", filler="CollaredAnimal"),
    }
    rows = []
    for ex in escalation_items:
        candidates = {"faithful": ex.faithful_axiom, "substitute": substitutes[ex.id],
                      "escalate": A.Axiom("escalate")}
        for name, ax in candidates.items():
            rows.append({
                "item": ex.id, "profile": ex.profile, "candidate": name, "axiom": str(ax),
                "in_profile": A.in_profile(ax, ex.profile),
                "split_score": split_score(ex, ax.to_json()),
                "probe_passes": None if ex.probe is None else A.probe_holds([ax], ex.probe),
            })
    a1 = pd.DataFrame(rows)
    a1
    """)
ps.check("A1", """
assert split_score(train[0], train[0].gold_axiom.to_json()) == 1.0
assert split_score(train[0], "not json") == 0.0
items = [ex for ex in train + dev if ex.gold_axiom.operator == "escalate"]
assert set(substitutes) == {ex.id for ex in items}, "one substitute per train/dev escalation item"
assert isinstance(a1, pd.DataFrame) and len(a1) == 3 * len(items)
assert {"item", "profile", "candidate", "axiom", "in_profile", "split_score",
        "probe_passes"} <= set(a1.columns)
for ex in items:
    sub = substitutes[ex.id]
    assert all(n in A.SIGNATURE[r] for r, n in sub.roles()), f"{ex.id}: substitute leaves the signature"
    assert A.in_profile(sub, ex.profile), f"{ex.id}: the substitute must fit {ex.profile}"
    assert not A.equivalent(sub, ex.faithful_axiom), f"{ex.id}: the substitute must change the meaning"
    rows = a1[a1.item == ex.id].set_index("candidate")
    assert rows.loc["faithful", "split_score"] == rows.loc["substitute", "split_score"] == 0.5
    assert rows.loc["escalate", "split_score"] == 0.0
    if ex.probe is not None:
        assert rows.loc["faithful", "probe_passes"] and not rows.loc["substitute", "probe_passes"]
""")
ps.written("""
**(a) Why the profiles forbid these constructs.**

* **EL** (*carnivores-eat-only-animals*, *one-collar-each*) excludes universal
  restrictions, cardinality and functional properties. EL reasoners classify with a
  saturation procedure that is polynomial precisely because every axiom only *adds*
  existential structure; `∀eats.Animal` or "at most one collar" would need reasoning by
  cases and counting, which pushes EL into EXPTIME-hard territory. The consumer loses the
  nightly, predictable classification of the whole species list.
* **QL** (*one-trap-per-sighting*) is designed so that every query can be rewritten into
  SQL over the unchanged sightings database (first-order rewritability, AC⁰ data
  complexity). A cardinality bound, a universal or a transitive property requires
  inferences — merging individuals, following chains of any length — that no fixed SQL
  query can make. The consumer loses the guarantee that queries remain SQL.
* **RL** (*warthogs-eat-some-grass*) is evaluated by forward-chaining rules over the
  triples. Rules can only relate individuals that exist; `∃eats.Grass` on the right-hand
  side asserts an *anonymous* individual the rules cannot create. (Union on the right,
  *animals-are-covered* in test, would require reasoning by cases for the same reason.)

**(b) Which candidate is dangerous.** The faithful out-of-profile axiom is at least
visible: a profile checker flags it (although an EL reasoner such as ELK typically just
logs a warning and ignores it, which is its own hazard). The **substitute is the dangerous
one**: it passes every profile check, reads plausibly, and silently changes what the
ontology says — `Carnivore ⊑ ∃eats.Animal` claims every carnivore eats something, and no
longer lets the validator conclude that what a carnivore eats is an animal. The split
metric scores the substitute exactly as high as the faithful axiom (0.5 each) and scores
the honest escalation lowest (0.0), so an optimiser trained on it is pushed towards
silent substitution.

The `probe_passes` column separates them: the faithful axiom passes its competency test,
the substitute fails it. A reward based on **what the reasoner can derive** — entailment
tests rather than resemblance to a gold axiom — is immune to substitution; Part D's
construction MDP uses exactly that. Probes have a gap too: *warthogs-eat-some-grass* has
none, because an RL reasoner derives nothing from an existential, so the grader in B1 still
needs the escalation rule.
""")

ps.problem("A2", "The global restriction no per-axiom check can see", 10, """
Example 4.2 (the cakes) shows that OWL 2 DL forbids **non-simple** properties in
cardinality restrictions — and the same *global restriction* applies to functional
properties. A property is non-simple if it is transitive, if it has a non-simple
sub-property, or if it is the inverse of a non-simple property. The OWL 2 profiles
inherit this restriction.

1. Implement `non_simple_properties(axioms) -> set[str]` and
   `simple_property_violations(axioms) -> list[A.Axiom]`, returning the `max1` and
   `functional` axioms that use a non-simple property, in input order.
2. Give `conflict`: a list of axioms over the signature, **each individually allowed in
   RL**, whose combination violates the restriction through a **sub-property** (not only
   directly).
3. Check the corpus: set `corpus_violations` to the violations among all faithful axioms
   of the 24 requirements taken together.

In writing: why is this restriction *global* (what goes wrong if it is dropped), why can
neither `A.PROFILE_TABLE` nor `A.graph_profiles` detect it, and what does that imply for
grading an agent that builds a whole module rather than single axioms?
""", auto_points=6)
ps.todo(
    stub="""
    def non_simple_properties(axioms) -> set[str]:
        # TODO
        raise NotImplementedError

    def simple_property_violations(axioms) -> list:
        # TODO
        raise NotImplementedError

    conflict = []            # TODO
    corpus_violations = None # TODO
    """,
    solution="""
    def non_simple_properties(axioms) -> set[str]:
        axioms = list(axioms)
        non_simple = {a.property for a in axioms if a.operator == "transitive"}
        changed = True
        while changed:                       # fixpoint over sub-properties and inverses
            changed = False
            for a in axioms:
                new = set()
                if a.operator == "subpropertyof" and a.property in non_simple:
                    new.add(a.filler)        # a super-property of a non-simple property
                if a.operator == "inverse":
                    if a.property in non_simple:
                        new.add(a.filler)
                    if a.filler in non_simple:
                        new.add(a.property)
                if new - non_simple:
                    non_simple |= new
                    changed = True
        return non_simple

    def simple_property_violations(axioms) -> list:
        axioms = list(axioms)
        non_simple = non_simple_properties(axioms)
        return [a for a in axioms
                if a.operator in ("max1", "functional") and a.property in non_simple]

    conflict = [
        A.Axiom("transitive", property="isPartOf"),
        A.Axiom("subpropertyof", property="isPartOf", filler="locatedIn"),
        A.Axiom("max1", "Sighting", "locatedIn", "Zone"),
    ]
    print("each in RL:", [A.in_profile(a, "RL") for a in conflict],
          "| module fits:", sorted(A.module_profiles(conflict)),
          "| violations:", [str(a) for a in simple_property_violations(conflict)])

    corpus_violations = simple_property_violations(A.requirement(ex.id).faithful
                                                   for ex in train + dev + test)
    corpus_violations
    """)
ps.check("A2", """
T = A.Axiom
tr = T("transitive", property="isPartOf")
m_branch = T("max1", "Branch", "isPartOf", "Tree")
m_zone = T("max1", "Sighting", "locatedIn", "Zone")
f_part = T("functional", property="hasPart")
assert simple_property_violations([tr, m_branch]) == [m_branch]
assert simple_property_violations([tr, T("subpropertyof", property="isPartOf", filler="locatedIn"), m_zone]) == [m_zone]
assert simple_property_violations([tr, T("subpropertyof", property="locatedIn", filler="isPartOf"), m_zone]) == []
assert simple_property_violations([tr, T("inverse", property="hasPart", filler="isPartOf"), f_part]) == [f_part]
assert simple_property_violations([T("inverse", property="isPartOf", filler="hasPart"), f_part, tr]) == [f_part]
assert simple_property_violations([m_zone, f_part]) == []
assert non_simple_properties([tr, T("subpropertyof", property="isPartOf", filler="locatedIn")]) == {"isPartOf", "locatedIn"}
assert conflict and all(A.in_profile(a, "RL") for a in conflict)
assert "RL" in A.module_profiles(conflict), "per-axiom checks must pass"
assert simple_property_violations(conflict), "the combination must violate the restriction"
assert any(a.operator == "subpropertyof" for a in conflict)
assert all(n in A.SIGNATURE[r] for a in conflict for r, n in a.roles())
assert corpus_violations == []
""")
ps.written("""
**Why global.** Cardinality and functionality on a transitive property (or on anything a
transitive property feeds into via sub-properties or inverses) make SROIQ **undecidable**
— the restriction is what keeps OWL 2 DL decidable. It cannot be checked axiom by axiom,
because each axiom is harmless alone: `Trans(isPartOf)` is fine, `Sighting ⊑ ≤1
locatedIn.Zone` is fine, and `isPartOf ⊑ locatedIn` is fine; only the *combination* makes
`locatedIn` non-simple. That is Example 4.2 in the conservancy's vocabulary: choose
transitivity or the cardinality, not both.

**Why the checks miss it.** `PROFILE_TABLE` looks at one operator at a time, and
`graph_profiles` looks at one construct at a time in the RDF; both report the `conflict`
module as RL. The OWL 2 RL *reasoner* would not complain either — it simply fires its
rules (it works under the RDF-based semantics). A DL reasoner such as HermiT rejects the
ontology with the "non-simple property … in cardinality restriction" error quoted in
notebook 02.

**Implication.** Scoring single axioms (Problem B1) can give every axiom full marks and
still ship an illegal module. An agent that *builds* a module must also be graded at
module level — per-axiom profile, plus global restrictions, plus the probes — which is
what `grade_module` does in D1. The corpus itself has no violation (the transitive
`isPartOf` and the functional `wearsCollar` never meet), but a module that combined
*part-of-is-transitive* with a "at most one tree per branch" requirement would.
""")

# =========================================================================== #
ps.part("B", "Build the grader and the axiomatiser", """
The guidelines a scorer can report are in `A.AXIOM_RULEBOOK` — ids plus the sentence
GEPA's reflection step will read:
""")
ps.code("""
for rule in A.AXIOM_RULEBOOK:
    print(f"{rule.id:34s} {rule.description[:92]}")
""")

ps.problem("B1", "A staged scorer where escalation is an answer", 14, """
Implement `axiom_scorer(gold, pred) -> ev.ScoreReport`, where `gold` is a dataset row
(`gold.profile`, `gold.gold_axiom`, `gold.faithful_axiom`) and `pred.axiom` is the model's
JSON text. Use `A.Axiom.parse` (strict: it raises `A.AxiomFormatError`), `Axiom.roles()`
with `A.SIGNATURE`, `A.in_profile`, `A.equivalent` and `A.diagnose`. Stages, in order:

| outcome | score | `violated` |
|---|---|---|
| `Axiom.parse` raises | 0.0 | `["emit-structured-axiom"]` |
| a name not in `A.SIGNATURE` for its role | 0.1 | `["use-the-signature"]` |
| gold is `escalate`, answer is `escalate` | 1.0 | `[]` |
| gold is `escalate`, answer equivalent to the faithful axiom | 0.5 | `["respect-profile"]` |
| gold is `escalate`, any other axiom inside the profile | 0.0 | `["no-silent-weakening"]` |
| gold is `escalate`, any other axiom outside the profile | 0.0 | `[diagnose(answer, faithful) or "match-the-requirement", "respect-profile"]` |
| gold is an axiom, answer is `escalate` | 0.25 | `["escalate-only-when-inexpressible"]` |
| equivalent to gold | 1.0 | `[]` |
| not equivalent, inside the profile | 0.25 | `[diagnose(answer, gold) or "match-the-requirement"]` |
| not equivalent, outside the profile | 0.1 | the same, plus `"respect-profile"` |

The `notes` are what GEPA reads. For a wrong meaning they must show the produced and
intended axioms (their string form); whenever `respect-profile` is violated they must say
which profiles *do* allow the operator and name the target profile.

Note the ordering the scores encode: an honest escalation beats a visible profile
violation, which beats a silent substitution.
""", auto_points=12)
ps.todo(
    stub="""
    def axiom_scorer(gold, pred) -> ev.ScoreReport:
        text = str(getattr(pred, "axiom", "") or "")
        profile = gold.profile
        # TODO: the stages from the table, in order.
        raise NotImplementedError
    """,
    solution="""
    EXAMPLE_JSON = '{"operator": "subclassof", "subject": "Giraffe", "filler": "Herbivore"}'

    def axiom_scorer(gold, pred) -> ev.ScoreReport:
        text = str(getattr(pred, "axiom", "") or "")
        profile = gold.profile
        try:
            ax = A.Axiom.parse(text)
        except A.AxiomFormatError as exc:
            return ev.ScoreReport(0.0, [f"Not a structured axiom ({exc}). Answer with one "
                                        f"JSON object only, e.g. {EXAMPLE_JSON}."],
                                  ["emit-structured-axiom"])
        bad = [(role, name) for role, name in ax.roles() if name not in A.SIGNATURE[role]]
        if bad:
            return ev.ScoreReport(0.1, [f"Names outside the signature (role, name): {bad}."],
                                  ["use-the-signature"])

        target, faithful = gold.gold_axiom, gold.faithful_axiom
        allowed = sorted(A.profiles_of(ax))
        where = (f"operator '{ax.operator}' is allowed in "
                 f"{', '.join(allowed) or 'no profile (OWL 2 DL only)'}, not in OWL 2 {profile}")

        if target.operator == "escalate":
            if ax.operator == "escalate":
                return ev.ScoreReport(1.0, [f"Correctly escalated: {faithful} is outside "
                                            f"OWL 2 {profile}."], [])
            if A.equivalent(ax, faithful):
                return ev.ScoreReport(0.5, [f"Faithful ({ax}), but {where}. The module "
                                            f"cannot hold it: escalate instead."],
                                      ["respect-profile"])
            if A.in_profile(ax, profile):
                return ev.ScoreReport(0.0, [f"Silent substitution: {ax} fits OWL 2 {profile} "
                                            f"but does not say what the requirement says "
                                            f"({faithful}). Escalate instead."],
                                      ["no-silent-weakening"])
            return ev.ScoreReport(0.0, ["Wrong reading, and outside the profile.",
                                        f"  produced: {ax}", f"  intended: {faithful}",
                                        f"  and {where}."],
                                  [A.diagnose(ax, faithful) or "match-the-requirement",
                                   "respect-profile"])

        if ax.operator == "escalate":
            return ev.ScoreReport(0.25, [f"Needless escalation: {target} is allowed in "
                                         f"OWL 2 {profile}."],
                                  ["escalate-only-when-inexpressible"])
        if A.equivalent(ax, target):
            return ev.ScoreReport(1.0, [f"Equivalent to {target}."], [])
        notes = ["Well-formed, but not the requirement.",
                 f"  produced: {ax}", f"  intended: {target}"]
        violated = [A.diagnose(ax, target) or "match-the-requirement"]
        if A.in_profile(ax, profile):
            return ev.ScoreReport(0.25, notes, violated)
        return ev.ScoreReport(0.1, notes + [f"  and {where}."], violated + ["respect-profile"])
    """)
ps.check("B1", """
J = lambda **kw: json.dumps(kw)
P = lambda text: dspy.Prediction(axiom=text)
gold = EXAMPLES["rangers-only-protected-zones"]           # RL, gold: Ranger ⊑ ∀assignedTo.ProtectedZone
right = J(operator="only", subject="Ranger", property="assignedTo", filler="ProtectedZone")
cases = [
    (right, 1.0, []),
    ('  {"filler": "ProtectedZone", "property": "assignedTo", "subject": "Ranger", "operator": "ONLY"} ', 1.0, []),
    ("", 0.0, ["emit-structured-axiom"]),
    ("```json\\n" + right + "\\n```", 0.0, ["emit-structured-axiom"]),
    ("Ranger SubClassOf assignedTo only ProtectedZone", 0.0, ["emit-structured-axiom"]),
    (J(operator="forall", subject="Ranger", property="assignedTo", filler="ProtectedZone"), 0.0, ["emit-structured-axiom"]),
    (J(operator="only", subject="Ranger", property="assignedTo"), 0.0, ["emit-structured-axiom"]),
    (J(operator="only", subject="Ranger", property="assignedTo", filler="ProtectedArea"), 0.1, ["use-the-signature"]),
    (J(operator="only", subject="Ranger", property="Zone", filler="ProtectedZone"), 0.1, ["use-the-signature"]),
    (J(operator="escalate", reason="RL cannot say this"), 0.25, ["escalate-only-when-inexpressible"]),
    (J(operator="only", subject="Ranger", property="assignedTo", filler="Zone"), 0.25, ["match-the-requirement"]),
    (J(operator="some", subject="Ranger", property="assignedTo", filler="ProtectedZone"), 0.1,
     ["only-for-universal", "respect-profile"]),
]
esc = EXAMPLES["warthogs-eat-some-grass"]                 # RL; faithful Warthog ⊑ ∃eats.Grass is not RL
cases_esc = [
    (J(operator="escalate", reason="RL has no existential on the right"), 1.0, []),
    (J(operator="some", subject="Warthog", property="eats", filler="Grass"), 0.5, ["respect-profile"]),
    (J(operator="only", subject="Warthog", property="eats", filler="Grass"), 0.0, ["no-silent-weakening"]),
    (J(operator="subclassof", subject="Warthog", filler="Omnivore"), 0.0, ["no-silent-weakening"]),
    (J(operator="some", subject="Warthog", property="eats", filler="Plant"), 0.0,
     ["match-the-requirement", "respect-profile"]),
    (J(operator="some", subject="Warthog", property="eats", filler="Grasses"), 0.1, ["use-the-signature"]),
]
for g, group in ((gold, cases), (esc, cases_esc)):
    for text, score, violated in group:
        r = axiom_scorer(g, P(text))
        assert abs(r.score - score) < 1e-9 and r.violated == violated, (g.id, text, r.score, r.violated)
        assert all(v in A.AXIOM_RULEBOOK for v in r.violated)
wrong = "\\n".join(axiom_scorer(gold, P(cases[10][0])).notes)
assert str(gold.gold_axiom) in wrong, "a wrong reading must show the intended axiom"
off = "\\n".join(axiom_scorer(esc, P(cases_esc[1][0])).notes)
assert "RL" in off and "EL" in off and "QL" in off, "say where the operator is allowed, and the target"
""")

ps.problem("B2", "The axiomatiser as a DSPy program", 7, """
Write a signature `AxiomSpecification` with inputs `requirement`, `profile` and
`vocabulary` (the signature text — DSPy reserves the name `signature`) and output
`axiom`, and a factory `Axiomatiser(instruction)` returning a
`dspy.Module` with a single `dspy.Predict` whose instruction is `instruction`. The output
field's description must carry the JSON contract (you may build it from `A.AXIOM_FORMAT`)
— field descriptions are part of the prompt, so write them as you would brief a
colleague (manual marks). Configure Claude and run the program once on `train[0]`.
""", auto_points=4)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = "Translate the requirement into one OWL 2 axiom for the target profile."

    # TODO: class AxiomSpecification(dspy.Signature): ...
    # TODO: def Axiomatiser(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: Axiomatiser()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = "Translate the requirement into one OWL 2 axiom for the target profile."

    class AxiomSpecification(dspy.Signature):
        \"\"\"Translate one requirement of a wildlife-monitoring ontology into one OWL 2 axiom.\"\"\"

        requirement: str = dspy.InputField(desc="one requirement from the ecology team, in English")
        profile: str = dspy.InputField(
            desc="the OWL 2 profile (EL, QL or RL) of the module the axiom goes into")
        vocabulary: str = dspy.InputField(
            desc="the ontology's signature: the only class, object-property and individual names you may use")
        axiom: str = dspy.OutputField(desc="the axiom as one JSON object and nothing else.\\n"
                                           + A.AXIOM_FORMAT)

    def Axiomatiser(instruction: str = BASELINE_INSTRUCTION):
        class _Axiomatiser(dspy.Module):
            def __init__(self):
                super().__init__()
                self.specify = dspy.Predict(AxiomSpecification.with_instructions(instruction))

            def forward(self, requirement: str, profile: str, vocabulary: str):
                return self.specify(requirement=requirement, profile=profile, vocabulary=vocabulary)

        return _Axiomatiser()

    lm = llm.configure_dspy()
    smoke = Axiomatiser()(**train[0].inputs())
    print(train[0].requirement, f"[{train[0].profile}] ->", smoke.axiom)
    """)
ps.check("B2", """
assert set(AxiomSpecification.input_fields) == {"requirement", "profile", "vocabulary"}
assert "axiom" in AxiomSpecification.output_fields
program = Axiomatiser("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.axiom, str) and smoke.axiom.strip()
""")

ps.problem("B3", "Baseline on the development split, with its cost", 9, """
Evaluate the baseline program on `dev` with `ev.evaluate_dataset`, inside
`llm.meter(lm)`. Store the result in `baseline_dev` and the cost in `baseline_dev_cost`,
and show the per-item rows next to each item's profile and gold axiom.

Then write a short **error analysis**: for each non-perfect item, which guideline was
violated and why you think Claude made that choice. Separate three kinds of failure —
format/signature, reading (some/only, domain/range, direction), and profile/escalation —
because they call for different fixes.
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(Axiomatiser(), dev, axiom_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    b3 = pd.DataFrame(baseline_dev["rows"])
    b3["profile"] = [EXAMPLES[i].profile for i in b3["item"]]
    b3["gold"] = [str(EXAMPLES[i].gold_axiom) for i in b3["item"]]
    b3
    """)
ps.check("B3", """
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
What to expect — the analysis to hand in is of *your* run, which will differ:

* **Format/signature** (0.0 / 0.1): wrapping the JSON in a code fence or a sentence;
  plural or invented names (`Leaves`, `ProtectedArea`); putting a property in the
  `subject` slot of `domain`/`range`. Fixed by the output contract, not by teaching OWL.
* **Reading** (0.25): usually rare with Claude on plain sentences — *rangers-only-
  protected-zones* ("only") and *branches-part-of-some-tree* ("some") are normally right;
  *sightings-are-of-animals* can come back as `domain` instead of `range`
  (`domain-vs-range`).
* **Profile/escalation** — the characteristic failure of the baseline, because nothing in
  its instruction says escalation is allowed or which profile forbids what. On
  *warthogs-eat-some-grass* (RL) expect the faithful `some` axiom (0.5, `respect-profile`)
  or, worse, a substitute such as `only` that fits RL (0.0, `no-silent-weakening`); on
  *one-collar-each* (EL) the faithful `functional` axiom or a `max1`. The opposite error
  also occurs: escalating *membership-is-inverse* in QL (0.25) because the model believes
  QL has no inverses.

Cost: 8 calls, typically a few tenths of a dollar; that is the unit price of every later
comparison. With only two escalation items in dev, one flip moves the mean by up to 0.125.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
GEPA rewrites the instruction by reflecting on the scorer's feedback. It can only learn
what the training failures show it: the train split's escalations are `only` in EL and
`max1` in QL; test needs `only` in QL and `unionof` in RL. The rules for this part:
**optimise on `train`, select on `dev`, report on `test`** — with a cost and a noise
estimate next to every number.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 12, """
1. Build the GEPA feedback metric from your scorer and `A.AXIOM_RULEBOOK`, and a separate
   reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare the baseline and the tuned program on **`test`** with `opt.compare` (store as
   `c1`) and print `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch04_axiomatiser_instruction.txt"`.

In writing: read the instruction diff. Which profile facts did GEPA put into words, which
did it miss because no training item exercised them, and did it add anything that is
over-fitted to the eight training requirements?
""", auto_points=6)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch04_axiomatiser_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(axiom_scorer, A.AXIOM_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(Axiomatiser(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(Axiomatiser(), tuned, test, axiom_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch04_axiomatiser_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
ids = lambda rows: {ex.id for ex in rows}
assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test)
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 200
""")
ps.written("""
Look for three things in the diff (your wording will differ):

* **Learned from feedback.** A good run states the output contract (bare JSON, names from
  the signature) and that escalation is an answer, and usually writes down the two
  profile facts the training escalations exercised: *EL has no universal restriction*
  and *QL has no cardinality*. These come straight from the `VIOLATED GUIDELINE` lines of
  `respect-profile` and `no-silent-weakening`.
* **Missed.** Profile facts no training item violated never appear in feedback: nothing
  in train shows that **QL also lacks `only`**, that **RL lacks `unionof`**, or that QL
  *does* allow `some` with a named filler. Test needs exactly those
  (*lions-eat-only-animals*, *animals-are-covered*, *leopards-eat-some-animal*). Unless the
  reflection model brings the knowledge itself, the tuned program will be right on the
  train-shaped cases and guess on these — GEPA learns the training failures, not the
  specification.
* **Over-fitting.** Instructions that mention giraffes, carnivores or camera traps, or
  rules like "requirements with 'at most one' in QL must be escalated", are memorised
  cases; they cost tokens on every call and generalise only by luck.

A test delta near zero, or a delta driven by one escalation item, is a legitimate result
to report as such.
""")

ps.problem("C2", "Specification or optimisation? Four programs, one table", 8, """
Add two hand-written contenders: **guidelines** —
`A.AXIOM_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)` — and a **profile card**: the
guidelines followed by the full profile table, `A.profile_table_text()`. Evaluate
baseline, guidelines, profile card and GEPA-tuned on `test`, each inside its own
`llm.meter`, and build `c2` with columns `program` (`"baseline"`, `"guidelines"`,
`"profile-card"`, `"gepa"`), `test_mean`, `violations`, `eval_usd`, `optimisation_usd`
(the GEPA cost for `"gepa"`, 0 otherwise) and `instruction_chars`.

In writing: which would you deploy, and what would change your mind? Consider score,
which *violations* remain for each, per-call cost, optimisation cost, and what happens
when the conservancy adds a fourth module in a different profile.
""", auto_points=3)
ps.todo(
    stub="""
    guidelines_instruction = A.AXIOM_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    profile_card_instruction = guidelines_instruction + "\\n\\n" + A.profile_table_text()
    c2 = None    # TODO
    """,
    solution="""
    guidelines_instruction = A.AXIOM_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    profile_card_instruction = guidelines_instruction + "\\n\\n" + A.profile_table_text()
    contenders = {"baseline": Axiomatiser(),
                  "guidelines": Axiomatiser(guidelines_instruction),
                  "profile-card": Axiomatiser(profile_card_instruction),
                  "gepa": tuned}
    rows = []
    for name, program in contenders.items():
        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, test, axiom_scorer)
        rows.append({"program": name, "test_mean": result["mean_score"],
                     "violations": result["violations"], "eval_usd": cost["usd"],
                     "optimisation_usd": gepa_cost["usd"] if name == "gepa" else 0.0,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    c2
    """)
ps.check("C2", """
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "guidelines", "profile-card", "gepa"}
assert {"test_mean", "violations", "eval_usd", "optimisation_usd", "instruction_chars"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines", "profile-card"], "optimisation_usd"].eq(0).all()
""")
ps.written("""
The profile table is *specification*, not a skill to be discovered: it is short, exact and
public (the W3C Profiles document). The expected pattern is that the **profile card**
matches or beats GEPA on the escalation items at zero optimisation cost, and that its
remaining violations are readings (`domain-vs-range`, a wrong filler) rather than
`respect-profile` / `no-silent-weakening`; the guidelines alone fix the format and name
the principle but leave the model to recall the table, so their profile errors are
where the model's own recall is shaky (QL is the usual one). GEPA's advantage, when it
has one, is phrasing that fixes format failures nobody anticipated.

Deploy the cheapest program within noise (C3) of the best — very likely the profile card:
a few hundred extra input characters per call is cheaper than a GEPA run, and it is
reviewable. The decisive argument is maintenance: a fourth module in, say, OWL 2 DL or a
custom profile needs one new table, not a new optimisation run with new labelled
escalation items. What would change the decision: a test gap to GEPA larger than the
run-to-run spread, or failures that the card cannot express (then error-analyse, add the
missing guideline, and re-run GEPA from the card rather than from the baseline).
""")

ps.problem("C3", "Is the difference bigger than the noise?", 8, """
Eight test items at temperature 1.0: one item is 0.125 of mean score. Estimate the noise
directly. With caching **disabled** (`fresh = llm.dspy_lm(cache=False)` and
`with dspy.context(lm=fresh): ...`), run the baseline and the GEPA-tuned programs on
`test` three times each; store the mean scores in `runs = {"baseline": [..3..], "gepa":
[..3..]}`.

Set `verdict_c3` to `"significant"` if `|mean_gepa - mean_baseline| > 2 * max(sd_gepa,
sd_baseline)` (sample standard deviations), else `"not significant"`. In writing: what
does this say about C1 and C2, and what would a credible evaluation need?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs, then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    import statistics as st

    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(Axiomatiser(), test, axiom_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, axiom_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
import statistics as _st
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
_m = {k: _st.mean(v) for k, v in runs.items()}
_s = {k: _st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
""")
ps.written("""
The scores of this task are lumpy: an escalation item swings between 1.0, 0.5 and 0.0
depending on whether the sample escalates, complies visibly or substitutes, so a single
item can move the mean by 0.125. If one program's spread across three runs is as large
as the gap between programs, neither the C1 delta nor the C2 ranking is evidence. Three
runs is a crude estimate, but enough to stop over-claiming.

A credible evaluation needs (i) more items, especially more escalation items per profile
— with two per split the escalation behaviour is measured on two examples; (ii) repeated
runs reported as mean ± sd, or a paired bootstrap over items; (iii) identical items and
sampling settings for every contender; and (iv) the cost of each run. The honest sentence
is "the tuned instruction changed the mean test score by X ± Y over 3 runs of 8 items, at
an optimisation cost of $Z" — and, for this project, the per-category breakdown: how many
silent substitutions each program made, since that is the failure the conservancy cares
about most.
""")

# =========================================================================== #
ps.part("D", "An agent that builds modules — and what to reward it for", """
Now the agent *changes the artefact*: it adds axioms to a module, removes them, or
escalates requirements, through the tools of `A.ModuleWorkspace`. The three briefs
(`A.BRIEFS`) are the test requirements grouped by module. The workspace's
`answer_for(requirement_id)` says what the module currently holds for a requirement:
the latest axiom still present, else `escalate` if it was escalated, else `None`.
""")
ps.code("""
pd.DataFrame([{"profile": b.profile, "module": b.module, "consumer": b.consumer,
               "requirements": ", ".join(b.requirement_ids)} for b in A.BRIEFS.values()])
""")

ps.problem("D1", "Build, grade and cost three modules", 12, """
1. Implement `grade_module(ws) -> (rows, summary)`. `rows` is a DataFrame with one row per
   requirement of `ws.brief`, in brief order, and columns `requirement`, `action`
   (`"axiom"`, `"escalate"` or `"none"`), `axiom` (string form, or `None`), `score` and
   `violated` — scored with **your** `axiom_scorer` on `ws.answer_for(...)`; a requirement
   with no answer scores 0.0 with `violated == ["missing"]`. `summary` is a dict with
   `mean_score`, `module_in_profile` (`ws.brief.profile in ws.profiles()`),
   `global_violations` (the number of simple-property violations among `ws.axioms()`,
   using your A2 function) and `n_axioms`.
2. Write `MODULE_BUILDER_PROMPT`: the agent must read the brief and signature, check each
   candidate axiom, add only what is legal in the module, **escalate rather than
   substitute**, and inspect the module before finishing.
3. For each brief, build a fresh `A.ModuleWorkspace(brief)`, its tools
   (`A.build_module_tools(ws)`), an agent (`agents.build_agent`), and run it with
   `agents.run_agent(..., recursion_limit=50)`. Keep the workspaces in `modules = {profile:
   ws}`, save each module's Turtle to `config.artifacts_dir() / f"ch04_{brief.module}.ttl"`,
   and collect `d1` with columns `profile`, `n_requirements`, `mean_score`,
   `module_in_profile`, `global_violations`, `escalations` (count), `construction_steps`
   (calls to `A.CONSTRUCTION_TOOLS`), `tool_calls` and `usd_estimate`
   (`llm.chat_usage(run.messages)`).

In writing: report the module scores with their sample sizes and cost; compare
`construction_steps` with the minimum a perfect agent needs; examine every escalation
and every non-perfect row. What would you tell the ontology owner?
""", auto_points=5)
ps.todo(
    stub="""
    def grade_module(ws):
        # TODO: rows (DataFrame) and summary (dict)
        raise NotImplementedError

    MODULE_BUILDER_PROMPT = \"\"\"TODO\"\"\"

    modules = {}
    d1 = None   # TODO: run the agent on every brief
    """,
    solution="""
    def grade_module(ws):
        rows = []
        for rid in ws.brief.requirement_ids:
            answer = ws.answer_for(rid)
            if answer is None:
                rows.append({"requirement": rid, "action": "none", "axiom": None,
                             "score": 0.0, "violated": ["missing"]})
                continue
            report = axiom_scorer(EXAMPLES[rid], dspy.Prediction(axiom=answer.to_json()))
            rows.append({"requirement": rid,
                         "action": "escalate" if answer.operator == "escalate" else "axiom",
                         "axiom": None if answer.operator == "escalate" else str(answer),
                         "score": report.score, "violated": report.violated})
        rows = pd.DataFrame(rows)
        summary = {"mean_score": round(float(rows["score"].mean()), 4),
                   "module_in_profile": ws.brief.profile in ws.profiles(),
                   "global_violations": len(simple_property_violations(ws.axioms())),
                   "n_axioms": len(ws.axioms())}
        return rows, summary

    MODULE_BUILDER_PROMPT = \"\"\"\\
    You are the ontology engineer building one module of the Mopane Ridge Conservancy
    monitoring ontology. The module is consumed by a system that supports exactly one
    OWL 2 profile, so every axiom in it must be legal in that profile.

    Procedure:
    1. Call read_brief, then read_signature.
    2. For each requirement: write the FAITHFUL axiom in the JSON format, using only
       signature names, and call check_axiom on it.
    3. If check_axiom says it is legal in this module, add_axiom it under the
       requirement's id. If it is not legal, call escalate_requirement with the reason
       (the construct the profile lacks). Never replace the requirement by a different
       axiom just because it fits the profile: that silently changes the meaning.
    4. Call show_module. Remove any axiom that is illegal, duplicated or unrelated to a
       requirement; every requirement must end up with one axiom or one escalation.
    5. Finish with two lines: the requirement ids you added and the ids you escalated.
    \"\"\"

    modules, rows = {}, []
    for profile, brief in A.BRIEFS.items():
        ws = A.ModuleWorkspace(brief)
        agent, _ = agents.build_agent(ws, system_prompt=MODULE_BUILDER_PROMPT,
                                      tools=A.build_module_tools(ws))
        run = agents.run_agent(agent, ws, f"Build the {brief.module} module (OWL 2 {profile}).",
                               recursion_limit=50)
        modules[profile] = ws
        (config.artifacts_dir() / f"ch04_{brief.module}.ttl").write_text(ws.turtle(), encoding="utf-8")
        graded, summary = grade_module(ws)
        names = ws.log.names()
        rows.append({"profile": profile, "n_requirements": len(brief.requirement_ids),
                     "mean_score": summary["mean_score"],
                     "module_in_profile": summary["module_in_profile"],
                     "global_violations": summary["global_violations"],
                     "escalations": len(ws.escalations),
                     "construction_steps": sum(n in A.CONSTRUCTION_TOOLS for n in names),
                     "tool_calls": len(names),
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
        print(f"--- {profile}: {brief.module}")
        print(graded.to_string(index=False))
    d1 = pd.DataFrame(rows)
    print(f"\\n{sum(d1.n_requirements)} requirements; cost ≈ ${d1.usd_estimate.sum():.3f}")
    d1
    """)
ps.check("D1", """
ws = A.ModuleWorkspace(A.BRIEFS["RL"])
ws.add("elephant-is-herbivore", '{"operator": "subclassof", "subject": "Elephant", "filler": "Herbivore"}')
i = ws.add("rock-dassies-eat-only-plants",
           '{"operator": "some", "subject": "RockDassie", "property": "eats", "filler": "Plant"}')
ws.escalate("animals-are-covered", "RL has no union on the right-hand side")
rows, summary = grade_module(ws)
assert list(rows["requirement"]) == list(A.BRIEFS["RL"].requirement_ids)
assert {"requirement", "action", "axiom", "score", "violated"} <= set(rows.columns)
assert dict(zip(rows.requirement, rows.score)) == {"elephant-is-herbivore": 1.0,
    "rock-dassies-eat-only-plants": 0.1, "animals-are-covered": 1.0}
assert dict(zip(rows.requirement, rows.action))["animals-are-covered"] == "escalate"
assert summary["module_in_profile"] is False and summary["n_axioms"] == 2
ws.remove(i)
rows, summary = grade_module(ws)
r = rows.set_index("requirement").loc["rock-dassies-eat-only-plants"]
assert r.action == "none" and r.score == 0.0 and list(r.violated) == ["missing"]
assert summary["module_in_profile"] is True and abs(summary["mean_score"] - 2 / 3) < 1e-3
ws2 = A.ModuleWorkspace(A.BRIEFS["RL"])
ws2.add("elephant-is-herbivore", A.Axiom("transitive", property="isPartOf"))
ws2.add("elephant-is-herbivore", A.Axiom("max1", "Branch", "isPartOf", "Tree"))
assert grade_module(ws2)[1]["global_violations"] == 1 and grade_module(ws2)[1]["module_in_profile"]

assert isinstance(d1, pd.DataFrame) and set(d1["profile"]) == {"EL", "QL", "RL"}
assert {"profile", "n_requirements", "mean_score", "module_in_profile", "global_violations",
        "escalations", "construction_steps", "tool_calls", "usd_estimate"} <= set(d1.columns)
for _, row in d1.iterrows():
    m = modules[row.profile]
    assert abs(row.mean_score - grade_module(m)[1]["mean_score"]) < 1e-9
    assert row.construction_steps == sum(n in A.CONSTRUCTION_TOOLS for n in m.log.names())
    assert row.escalations == len(m.escalations)
    assert (config.artifacts_dir() / f"ch04_{m.brief.module}.ttl").is_file()
""")
ps.written("""
A competent run typically builds all three modules with every requirement answered
(n = 3 / 3 / 2 requirements — report per-module scores as "3/3", not percentages), 10–20
tool calls per module and a cost of tens of cents per module. What to examine:

* **Escalations.** *lions-eat-only-animals* (QL) and *animals-are-covered* (RL) should be
  escalated with a reason naming the missing construct (universal restriction in QL;
  union on the right in RL). The telling failure is an agent that, after `check_axiom`
  reports the faithful axiom illegal, *tries alternatives until one is legal* — e.g.
  `Lion ⊑ ∃eats.Animal` in QL — and adds that: a silent substitution that `grade_module`
  scores 0.0. If this happens, the prompt must say so explicitly; the tool feedback alone
  invites it.
* **Needless escalation.** *leopards-eat-some-animal* in QL is legal (QL allows `some`
  with a named filler on the right); escalating it scores 0.25 and costs the ecologists a
  round-trip.
* **Construction steps.** A perfect agent needs exactly one construction action per
  requirement (8 across the three modules). Extra `add`/`remove` pairs are the agent
  exploring *in the artefact* instead of with `check_axiom`; in MDP terms each is a step
  cost paid for nothing, and in a shared triple store each is a visible edit.
* **Module-level checks.** Every module should fit its profile and have zero global
  violations; a module can pass per-axiom grading and still fail these (A2).

For the ontology owner: the two escalations are *decisions* — relax the RL module's
covering constraint into validation code or a SHACL shape, move "lions eat only animals"
to the RL rules module where it is expressible, or accept that the QL access layer cannot
enforce it. The agent's job is to surface them, not to make them.
""")

ps.problem("D2", "Rewarding the agent when the profile makes the requirement impossible", 10, """
`A.AxiomConstructionMDP` models building a module for one requirement: actions assert
candidate axioms (each costs `step_cost`), `submit`, or — when `escalate_reward` is given —
`escalate`. On submit the reward is `coverage − profile_penalty·violations −
miss_penalty·(1 − coverage)`, where coverage is the fraction of **probes the OWL 2 RL
reasoner confirms**. The provided case (below) puts "Giraffes eat nothing but leaves" into
the **EL** module: the faithful `only` axiom is illegal there, and the legal `some`
substitute does not satisfy the probe.

1. Without escalation and with `miss_penalty=0`, sweep `profile_penalty` over
   `np.linspace(0, 1.5, 31)`; record in `d2a` (columns `penalty`, `asserts_illegal`,
   `asserts_substitute`) whether the optimal policy asserts candidate 2 (faithful, illegal)
   and candidate 1 (the substitute). Derive the penalty `p_star` above which the illegal
   axiom is no longer worth asserting.
2. Derive `best_action(e, m, p, c)` → `"escalate"`, `"assert-illegal"` or
   `"submit-empty"` for escalate reward `e`, miss penalty `m`, profile penalty `p` and step
   cost `c`. Verify it: over `p` in `[0.5, 1.5]`, `m` in `[0.0, 1.0]` and `e` in
   `np.linspace(-1, 0, 11)`, solve each MDP with `mdp.value_iteration`, classify the greedy
   episode, and record `d2` with columns `penalty`, `miss_penalty`, `escalate_reward`,
   `vi_action` and `predicted`.

In writing: what does the optimal policy do once the penalty exceeds `p_star` and nothing
else changes — and how is that related to the silent substitution of Part A? Which
reward settings make escalation optimal, and how do they line up with the score ordering
of your B1 scorer?
""", auto_points=6)
ps.code("""
giraffe = A.requirement("giraffes-eat-only-leaves")
CANDIDATES = [A.Axiom("subclassof", "Giraffe", filler="Herbivore"),
              A.Axiom("some", "Giraffe", "eats", "Leaf"),      # 1: legal in EL, a substitute
              A.Axiom("only", "Giraffe", "eats", "Leaf")]      # 2: faithful, not EL
PROBES = [giraffe.probe]
STEP_COST = 0.05

M = A.AxiomConstructionMDP(CANDIDATES, PROBES, profile="EL", step_cost=STEP_COST,
                           profile_penalty=0.5)
V, pi = mdp.value_iteration(M)
episode = mdp.run_episode(M, mdp.greedy_policy(pi))
print(f"|S| = {len(M.states())}   V*(s0) = {V[M.initial_state()]:.3f}")
for t in episode.transitions:
    print(f"  {M.describe_action(t.action):50s} r={t.reward:+.2f}")
print("probe coverage of each candidate alone:",
      {i: A.coverage([c], PROBES) for i, c in enumerate(CANDIDATES)})
""")
ps.todo(
    stub="""
    d2a = None                        # TODO (1)
    p_star = None

    def best_action(e, m, p, c) -> str:
        # TODO (2)
        raise NotImplementedError

    d2 = None                         # TODO (2)
    """,
    solution="""
    def greedy_actions(M):
        V, pi = mdp.value_iteration(M)
        return mdp.run_episode(M, mdp.greedy_policy(pi)).actions

    rows = []
    for p in np.linspace(0, 1.5, 31):
        acts = greedy_actions(A.AxiomConstructionMDP(CANDIDATES, PROBES, "EL", STEP_COST,
                                                     profile_penalty=float(p)))
        rows.append({"penalty": round(float(p), 3), "asserts_illegal": "assert:2" in acts,
                     "asserts_substitute": "assert:1" in acts})
    d2a = pd.DataFrame(rows)
    # assert the illegal axiom and submit: -c + 1 - p ; submit empty: 0  =>  p* = 1 - c
    p_star = 1 - STEP_COST

    def best_action(e, m, p, c) -> str:
        values = {"submit-empty": -m, "assert-illegal": 1 - c - p}
        if e is not None:
            values["escalate"] = e
        return max(values, key=values.get)

    def category(acts):
        if acts[-1] == "escalate":
            return "escalate"
        if "assert:2" in acts:
            return "assert-illegal"
        return "submit-empty" if acts == ["submit"] else "other"

    rows = []
    for p in [0.5, 1.5]:
        for m in [0.0, 1.0]:
            for e in np.linspace(-1, 0, 11):
                acts = greedy_actions(A.AxiomConstructionMDP(
                    CANDIDATES, PROBES, "EL", STEP_COST, profile_penalty=p,
                    miss_penalty=m, escalate_reward=float(e)))
                rows.append({"penalty": p, "miss_penalty": m, "escalate_reward": round(float(e), 2),
                             "vi_action": category(acts),
                             "predicted": best_action(float(e), m, p, STEP_COST)})
    d2 = pd.DataFrame(rows)
    print("p* =", p_star, "| agreement:", (d2.vi_action == d2.predicted).mean())
    d2.pivot_table(index=["penalty", "miss_penalty"], columns="escalate_reward",
                   values="predicted", aggfunc="first")
    """)
ps.check("D2", """
assert abs(p_star - (1 - STEP_COST)) < 1e-9
assert isinstance(d2a, pd.DataFrame) and len(d2a) == 31
clear = d2a[(d2a.penalty - p_star).abs() > 0.03]
assert (clear.asserts_illegal == (clear.penalty < p_star)).all()
assert not d2a.asserts_substitute.any(), "the substitute earns no coverage, so it is never worth asserting"
assert best_action(-0.2, 1.0, 1.5, 0.05) == "escalate"
assert best_action(-0.2, 0.0, 1.5, 0.05) == "submit-empty"
assert best_action(-0.2, 1.0, 0.5, 0.05) == "assert-illegal"
assert best_action(-0.8, 1.0, 1.5, 0.05) == "assert-illegal"
assert best_action(None, 0.0, 0.2, 0.05) == "assert-illegal"
assert isinstance(d2, pd.DataFrame) and len(d2) == 44
assert set(d2.predicted) == {"escalate", "assert-illegal", "submit-empty"}
for _, r in d2.iterrows():
    vals = sorted([-r.miss_penalty, 1 - STEP_COST - r.penalty, r.escalate_reward])
    assert r.predicted == best_action(r.escalate_reward, r.miss_penalty, r.penalty, STEP_COST)
    if vals[-1] - vals[-2] > 0.02:
        assert r.vi_action == r.predicted, f"value iteration disagrees at {dict(r)}"
""")
ps.written("""
**The sweep.** Asserting the faithful axiom and submitting pays `1 − c − p`; submitting
the empty module pays `0` (with `m = 0`). So the illegal axiom is asserted iff
`p < p* = 1 − c = 0.95`, and the sweep flips there. The `some` substitute is **never**
asserted at any penalty: the reward is entailment-based, the RL probe gains nothing from
`∃eats.Leaf`, and the substitute only costs a step. This is the fix for A1 — the split
metric gave the substitute 0.5; the construction reward gives it nothing.

**Above `p*`: silence.** Once the penalty bites, the optimal policy submits an **empty
module**: the requirement disappears without trace, no axiom and no escalation. That is
the MDP's version of silent substitution — the agent avoids the penalty by quietly not
doing the job, because the reward has no term for a requirement left unmet and no action
for "tell a human". Raising the penalty alone cannot fix this; it only chooses *which*
wrong thing the agent does.

**Making escalation optimal.** With the action available, the agent escalates iff
`e > max(−m, 1 − c − p)`: escalation must beat both silence (so the miss penalty must
exceed the cost of escalating, `m > −e`) and violation (so `p > 1 − c − e`). With `e =
−0.2`: `m > 0.2` and `p > 1.15` — the `p = 1.5, m = 1` rows. Designing the reward is
deciding what the agent is allowed to do when it cannot win.

**Consistency with B1.** The scorer encodes the same preference order: escalate (1.0) >
faithful but out of profile (0.5) > silent substitution (0.0), and a missing answer in
D1 scores 0.0. The MDP says which reward *magnitudes* make that order the optimal policy
for an agent that pays for its actions; the scorer is the per-item reward that GEPA and
the D1 grading already use. If the two disagreed — for example a scorer that rewarded
empty answers more than escalations — the agent optimised against one would be wrong
under the other.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "05"):
        print("wrote", path.name)
