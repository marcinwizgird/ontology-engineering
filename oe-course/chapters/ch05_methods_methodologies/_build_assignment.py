"""Build the Chapter 5 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch05_methods_methodologies/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 5 — Methods and Methodologies",
    title="An automated first-pass ontology design review",
    coverage=("Keet §5.1 (methodologies: METHONTOLOGY, On-To-Knowledge, DILIGENT, NeOn, "
              "SAMOD; competency questions), §5.2 (ontology quality, OntoClean "
              "meta-properties and taxonomy constraints); course notebooks 01–03 of this "
              "chapter, and the Chapter 3 tableau. Tools: DSPy + GEPA, LangChain agents, "
              "the Chapter 5 methodology recommender and OntoClean checker, value "
              "iteration."),
    scenario="""
    **Lattice & Loom** is an ontology consultancy. Every quarter its **design review
    board** reads client submissions before any modelling work is quoted: a one-paragraph
    project brief, and the draft top-level taxonomy from the client's modelling workshop
    together with the workshop's **meta-property tag sheet** (rigidity, identity, unity,
    dependence for every class). For each submission the board answers two questions:

    * *Which methodology should this project follow?* (§5.1) — decided from the signals
      in the brief, not from habit;
    * *Which subsumptions in the draft are ontologically wrong?* (§5.2) — OntoClean
      breaches such as a role placed above a kind (`Organisation <= Customer`) or an
      object filed under the stuff it is made of (`Statue <= Clay`).

    The second question is the reason the board exists. Every draft that reaches it has
    already passed the client's DL reasoner: the taxonomies are **consistent**, and a
    reasoner will never flag them. Dr Tomasz Lindqvist, head of quality, wants a Claude-based
    **first-pass auditor** that drafts the board's verdict for each submission. Your brief:

    1. **Show the gap.** Demonstrate on the review corpus that a logical reasoner sees none
       of these errors — and that it *propagates* them — and find where the keyword-based
       methodology recommender used to label the corpus stops being trustworthy.
    2. **Build the grader first**: a parser for the auditor's output and a diagnostic
       scorer whose feedback names the breached constraint.
    3. **Build and optimise the auditor** with DSPy and GEPA — train/dev/test by
       submission, a fixed budget, the cost of every run, and the run-to-run noise.
    4. **Ship an audit agent** and measure what its tools buy it, and **plan the client
       projects** as an MDP with prerequisites: when are evaluation and reuse worth their
       cost?

    The corpus (24 submissions from 24 clients, split 8/8/8 by submission, every
    split containing every methodology and every OntoClean phenomenon), the tag sheet,
    the reasoner wiring, the agent's tools and the planning MDP are provided in
    `ch05_agentic.py`. Every gold label is re-derived by the chapter's own engines when
    the module is imported.
    """,
    effort="10–12 hours",
    api_budget="≈ $6–13 estimated on `claude-opus-5` for a full run (≈ 170 DSPy calls and "
               "16 agent episodes; GEPA and the agent runs are the largest lines). Nothing "
               "here has been measured — your cost lines are the measurement. Re-running "
               "unchanged cells is free: DSPy caches identical requests.",
)

ps.setup("""
import re, time
import dspy
import numpy as np
import pandas as pd
import ch05_toolkit as ch5
import ch05_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
ALL = train + dev + test
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
pd.DataFrame([{"split": ex.split, "item": ex.id, "client": ex.organisation,
               "methodology": ex.gold_methodology, "violations": len(ex.gold_violations)}
              for ex in ALL])
""")

ps.md("""
One submission, as the auditor will see it (`brief`, `taxonomy`, `meta_properties`) and
with its gold labels:
""")
ps.code("""
ex = train[0]
print("CLIENT   :", ex.organisation)
print("BRIEF    :", ex.brief, "\\n")
print("TAXONOMY :\\n" + ex.taxonomy, "\\n")
print("TAG SHEET:\\n" + ex.meta_properties, "\\n")
print("GOLD     :", ex.gold_methodology, ex.gold_violations)
for d in ex.gold_detail:
    print("   ", d["constraint"], "--", d["detail"])
""")

# =========================================================================== #
ps.part("A", "Consistency is not correctness; signals are not judgement", """
Two claims underpin the whole review. First, the errors the board looks for are
invisible to a logical reasoner. Second, the gold methodology labels — produced by
`ch5.recommend_methodology` and then reviewed — are only as good as the recommender's
signals. Test both before you let a model near the corpus. Part A calls no model, so it
may look at all 24 submissions.
""")

ps.problem("A1", "What the reasoner sees — and what it spreads", 10, """
For every submission, load its taxonomy into the Chapter 3 tableau (`A.dl_tbox`,
`A.reasoner_report`, `A.dl.classify`) and build a DataFrame `a1` with one row per
submission and columns:

* `item`, `split`;
* `consistent` — every class in the taxonomy is satisfiable;
* `violating_axioms` — how many axioms `A.taxonomy_violations` flags;
* `entailed` — how many subsumptions between the taxonomy's named classes the
  reasoner entails (`A.dl.classify` over the taxonomy's classes);
* `propagated` — how many of those entailed subsumptions hold **only because of** the
  violating axioms (they disappear when you remove them) **and are not themselves
  asserted**.

Then answer in writing: (a) why can no DL reasoner, however complete, flag these axioms
— what kind of statement is "`Customer` is anti-rigid", and why does it not fit into a
TBox of atomic subsumptions? (b) Take one submission with `propagated > 0` and say
concretely what a downstream SPARQL query over that ontology would get wrong.
""", auto_points=6)
ps.todo(
    stub="""
    def taxonomy_classes(pairs):
        return sorted({c for pair in pairs for c in pair})

    # TODO: one row per submission in ALL
    a1 = None
    """,
    solution="""
    def taxonomy_classes(pairs):
        return sorted({c for pair in pairs for c in pair})

    rows = []
    for ex in ALL:
        pairs = A.parse_taxonomy(ex.taxonomy)
        names = taxonomy_classes(pairs)
        bad = set(ex.gold_violations)
        entailed = set(A.dl.classify(names, A.dl_tbox(pairs)))
        without = set(A.dl.classify(names, A.dl_tbox(
            [p for p in pairs if A.format_axiom(*p) not in bad])))
        asserted = set(pairs)
        rows.append({
            "item": ex.id, "split": ex.split,
            "consistent": A.reasoner_report(pairs)["consistent"],
            "violating_axioms": len({v["axiom"] for v in A.taxonomy_violations(pairs)}),
            "entailed": len(entailed),
            "propagated": len((entailed - without) - asserted),
        })
    a1 = pd.DataFrame(rows)
    print(f"consistent: {a1.consistent.sum()}/{len(a1)};  "
          f"violating axioms: {a1.violating_axioms.sum()};  "
          f"subsumptions propagated from them: {a1.propagated.sum()}")
    a1
    """)
ps.check("A1", """
assert isinstance(a1, pd.DataFrame) and len(a1) == len(ALL) == 24
assert {"item", "split", "consistent", "violating_axioms", "entailed", "propagated"} <= set(a1.columns)
assert a1["consistent"].all(), "every submission is logically consistent"
_r = a1.set_index("item")
for _ex in ALL:
    assert _r.loc[_ex.id, "violating_axioms"] == len(_ex.gold_violations), _ex.id
    assert _r.loc[_ex.id, "entailed"] >= len(A.parse_taxonomy(_ex.taxonomy)), _ex.id
assert _r.loc["port-cargo", "propagated"] == 1          # Container <= PhysicalObject
assert _r.loc["civic-archives", "propagated"] == 2      # Castle <= Building, Castle <= PhysicalObject
assert _r.loc["law-firm-pilot", "propagated"] == 2
assert (_r.loc[_r.violating_axioms == 0, "propagated"] == 0).all()
""")
ps.written("""
(a) All 24 taxonomies are consistent: with only atomic subsumptions and no negation or
disjointness, *every* class is satisfiable — the empty extension is always available — so
there is nothing for a tableau to close. More fundamentally, the meta-properties are not
statements about individuals in one model. "`Customer` is anti-rigid" says that *every*
instance of Customer *could* cease to be one while continuing to exist: a modal
claim quantifying over possible worlds (or over time), i.e. a statement about the
**class**, not about its members. A DL TBox is interpreted in a single, static model and
has no vocabulary for "necessarily" or "could stop being"; OntoClean's constraints are
second-order conditions on how such classes may be arranged. They can be *encoded* (e.g.
tagging classes in a meta-ontology, or a punned OWL layer as in Welty's OntoClean-in-OWL),
but then the reasoner is checking our encoding of the tag sheet, not discovering the
error from the taxonomy.

(b) *port-cargo*: `Container <= Cargo` together with `Cargo <= PhysicalObject` is all a
reasoner needs to classify every container as cargo. A customs query "list all cargo
currently in the yard" (`?x a :Cargo`) returns every empty container stacked on the
quay, and any rule that fires on cargo (duties, manifests) fires on them too. The
reasoner does not merely tolerate the bad axiom, it **amplifies** it: the 22
propagated subsumptions across the corpus are inferences nobody asserted and nobody will
review. (Similarly *civic-archives*: `Castle <= Ruin` makes every intact castle a ruin,
and a heritage-at-risk report would list them all.)
""")

ps.problem("A2", "Where the methodology recommender stops being trustworthy", 10, """
The corpus's gold methodology is whatever `ch5.recommend_methodology` returns — it counts
signal phrases in the brief — **after** human review: every brief was written and
checked so that the recommender's answer is also the expert's answer.

(a) Write at least three short, realistic briefs on which the recommender is **wrong** by
expert judgement. Store them in `adversarial`, a list of dicts with keys `brief`,
`expert` (a methodology id) and `kind` (your one-word name for the failure — e.g.
`"negation"`); use at least two different kinds.

(b) Build `a2`: one row per corpus submission with columns `item`, `split`, `gold`,
`runner_up` (second-ranked id) and `margin` (top score minus runner-up score).

(c) In writing: given (a), how can the review board justify using the recommender to
label the corpus, and what does (b) tell you about how fragile each label is? When a
live Claude run disagrees with a gold label, what is your procedure — and why is
"optimise the auditor until it agrees" the wrong one?
""", auto_points=5)
ps.todo(
    stub="""
    adversarial = [
        # {"brief": "...", "expert": "samod", "kind": "..."},
    ]
    a2 = None     # TODO (b)
    """,
    solution="""
    adversarial = [
        {"brief": "No existing ontologies, thesauri or databases fit our domain, and none "
                  "will be reused; one in-house team builds it over the full lifecycle.",
         "expert": "methontology", "kind": "negation"},
        {"brief": "Our team wants a test-driven, sprint-based process that delivers the "
                  "model in short cycles.",
         "expert": "samod", "kind": "paraphrase"},
        {"brief": "One hospital team starts it, but clinicians on forty wards will each "
                  "extend the ontology for their specialty and keep changing it; it must "
                  "tolerate divergent local versions.",
         "expert": "diligent", "kind": "paraphrase"},
        {"brief": "We already proved the business case last year in a knowledge management "
                  "pilot; now we need a production ontology, and the only thing that "
                  "matters is fast agile delivery.",
         "expert": "samod", "kind": "stale-signal"},
    ]
    for a in adversarial:
        r = ch5.recommend_methodology(a["brief"])
        print(f"{a['kind']:13s} recommender={r['recommended']:16s} expert={a['expert']:13s} {r['reason']}")

    rows = []
    for ex in ALL:
        ranking = ch5.recommend_methodology(ex.brief)["ranking"]
        rows.append({"item": ex.id, "split": ex.split, "gold": ex.gold_methodology,
                     "runner_up": ranking[1]["id"],
                     "margin": ranking[0]["score"] - ranking[1]["score"]})
    a2 = pd.DataFrame(rows)
    a2.sort_values("margin").head(6)
    """)
ps.check("A2", """
assert isinstance(adversarial, list) and len(adversarial) >= 3
assert len({a["kind"] for a in adversarial}) >= 2, "use at least two kinds of failure"
for _a in adversarial:
    assert _a["expert"] in A.METHODOLOGY_IDS, _a
    assert ch5.recommend_methodology(_a["brief"])["recommended"] != _a["expert"], \\
        f"the recommender gets this one right: {_a['brief'][:60]}"
assert isinstance(a2, pd.DataFrame) and len(a2) == 24
assert {"item", "split", "gold", "runner_up", "margin"} <= set(a2.columns)
assert (a2["margin"] >= 1).all() and (a2["gold"] != a2["runner_up"]).all()
_m = a2.set_index("item")["margin"]
assert _m["citizen-app"] == 2 and _m["port-cargo"] == 4 and _m["carrow-estate"] == 2
""")
ps.written("""
(a) shows the recommender is a bag-of-phrases counter: it cannot read negation ("none
will be reused" still scores `reuse`), misses paraphrases and hyphenation
(`test-driven` ≠ `test driven`; "forty wards … keep changing it" is DILIGENT's situation
without DILIGENT's words), and counts signals that describe the *past* ("we already
proved the business case") as if they were requirements; ties are broken alphabetically.

It is still defensible as a *labelling* tool because it is transparent and was used
under review: every corpus brief was written to state its situation in the catalogue's
own terms, and every label was checked by a person. (b) quantifies how much slack there
is: every margin is ≥ 1, but five labels have a margin of only 2 — four because the brief
carries a deliberate distractor signal (*pharmacy-network*, *citizen-app* "fed by the
council's databases", *genomics-samples*, *calder-shipyard*) and *carrow-estate* because
it states only two signals. Those are the labels to re-read first, and the items where a live model is most likely to
disagree.

Procedure when Claude disagrees with gold: read the brief and Claude's justification
**before** counting it as an error. If Claude is right, the gold label is wrong — fix
the label (and record the change), do not tune the program. Optimising "until it agrees"
turns a gold-label bug into a learned behaviour (the instruction would learn to count
keywords) and inflates the score on exactly the items where the grader is least
trustworthy. On this corpus a disagreement is most likely a model error, because the
briefs were written to be unambiguous; that is what the curation bought.
""")

# =========================================================================== #
ps.part("B", "Build the grader and the auditor", """
The guidelines a scorer can report are in `A.AUDIT_RULEBOOK` — ids plus the sentence
GEPA's reflection step will read:
""")
ps.code("""
for rule in A.AUDIT_RULEBOOK:
    print(f"{rule.id:30s} {rule.description[:90]}")
""")

ps.problem("B1", "Parse what the auditor says", 8, """
Models format answers in many ways; a grader must be strict about *meaning* and lenient
about *notation*. Implement:

* `normalise_axiom(text) -> str | None` — accept `Sub <= Super`, `Sub ⊑ Super`,
  `Sub subClassOf Super`, `Sub rdfs:subClassOf Super` and `Sub is-a Super` (keywords
  case-insensitive, whitespace and surrounding quotes/backticks ignored; class names are
  identifiers `[A-Za-z][A-Za-z0-9_]*`) and return the canonical `"Sub <= Super"`; else
  `None`.
* `parse_violations(value) -> list[str] | None` — `value` is a list, or a string holding a
  JSON array (possibly inside a code fence). Items are axiom strings or objects with an
  `"axiom"` key. `""`, `"none"` and `"[]"` mean no violations (`[]`). Return the
  canonical axioms, de-duplicated in order; return `None` (unparseable) for `None`, for a
  string that is not a JSON array, or if **any** item is not an axiom.
* `methodology_id(text) -> str | None` — map a methodology as written (`"NeOn"`,
  `"On-To-Knowledge"`, `"The NeOn methodology"`) to its catalogue id: compare
  case-insensitively with non-alphanumerics removed against every id and name in
  `ch5.METHODOLOGIES`; failing an exact match, accept the answer if **exactly one**
  catalogue key occurs in it; else `None`.
""", auto_points=5)
ps.todo(
    stub="""
    def normalise_axiom(text) -> str | None:
        # TODO
        raise NotImplementedError

    def parse_violations(value) -> list[str] | None:
        # TODO
        raise NotImplementedError

    def methodology_id(text) -> str | None:
        # TODO
        raise NotImplementedError
    """,
    solution="""
    _NAME = r"([A-Za-z][A-Za-z0-9_]*)"
    _SEP = r"(?:<=|⊑|rdfs:subClassOf\\b|subClassOf\\b|is[-_]a\\b)"
    _AXIOM = re.compile(rf"^{_NAME}\\s*{_SEP}\\s*{_NAME}$", re.IGNORECASE)

    def normalise_axiom(text) -> str | None:
        if not isinstance(text, str):
            return None
        m = _AXIOM.match(text.strip().strip("'\\"`").strip())
        return f"{m.group(1)} <= {m.group(2)}" if m else None

    def parse_violations(value) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            fence = re.match(r"^```[A-Za-z]*\\s*(.*?)\\s*```$", text, re.DOTALL)
            if fence:
                text = fence.group(1).strip()
            if text.lower() in {"", "none", "[]"}:
                return []
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return None
        if not isinstance(value, (list, tuple)):
            return None
        out = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("axiom")
            axiom = normalise_axiom(item)
            if axiom is None:
                return None
            if axiom not in out:
                out.append(axiom)
        return out

    def _key(text) -> str:
        return re.sub(r"[^a-z0-9]", "", str(text).lower())

    _CATALOGUE = {**{_key(m.id): m.id for m in ch5.METHODOLOGIES},
                  **{_key(m.name): m.id for m in ch5.METHODOLOGIES}}

    def methodology_id(text) -> str | None:
        key = _key(text or "")
        if not key:
            return None
        if key in _CATALOGUE:
            return _CATALOGUE[key]
        hits = {mid for k, mid in _CATALOGUE.items() if k in key}
        return hits.pop() if len(hits) == 1 else None
    """)
ps.check("B1", """
assert normalise_axiom("Person <= Student") == "Person <= Student"
assert normalise_axiom("  `Person ⊑ Student` ") == "Person <= Student"
assert normalise_axiom("Statue rdfs:subClassOf Clay") == "Statue <= Clay"
assert normalise_axiom("Statue SUBCLASSOF Clay") == "Statue <= Clay"
assert normalise_axiom("Pet is-a Animal") == "Pet <= Animal"
assert normalise_axiom("Person is a kind of Student") is None
assert parse_violations('["Person <= Student"]') == ["Person <= Student"]
assert parse_violations('```json\\n["Person ⊑ Student", "Statue subClassOf Clay"]\\n```') == \\
    ["Person <= Student", "Statue <= Clay"]
assert parse_violations('[{"axiom": "Person rdfs:subClassOf Pet", "constraint": "x"}]') == ["Person <= Pet"]
assert parse_violations(["Person <= Student", "Person<=Student"]) == ["Person <= Student"]
assert parse_violations("[]") == [] and parse_violations("none") == [] and parse_violations("") == []
assert parse_violations("Person <= Student") is None
assert parse_violations('["Person <= Student", "looks fine"]') is None
assert parse_violations(None) is None and parse_violations('{"axiom": "A <= B"}') is None
assert methodology_id("NeOn") == "neon" and methodology_id("  METHONTOLOGY ") == "methontology"
assert methodology_id("On-To-Knowledge") == "on-to-knowledge" == methodology_id("on to knowledge")
assert methodology_id("The NeOn methodology") == "neon" and methodology_id("SAMOD (agile)") == "samod"
assert methodology_id("NeOn or DILIGENT") is None and methodology_id("waterfall") is None
assert methodology_id("") is None and methodology_id(None) is None
""")

ps.problem("B2", "A diagnostic audit scorer", 12, """
Implement `audit_scorer(gold, pred) -> ev.ScoreReport`, where `gold` is a dataset row and
`pred` has `methodology` and `violations`. Score `0.4 × methodology_ok + 0.6 ×
violation_F1` (the taxonomy carries more weight: it is the part a reasoner cannot do).

| situation | effect | `violated` |
|---|---|---|
| `methodology_id(pred.methodology)` is `None` | methodology 0 | `emit-structured-audit` **and** `choose-<gold>` |
| a catalogue id, but not gold | methodology 0 | `choose-<gold>` |
| `parse_violations(...)` is `None` | F1 = 0; no further taxonomy diagnosis | `emit-structured-audit` |
| a gold violation not reported | lowers F1 | `apply-ontoclean-constraints` |
| a **sound** axiom of the taxonomy reported | lowers F1 | `only-report-real-violations` |
| an axiom that is **not in the taxonomy** reported (e.g. reversed) | lowers F1 | `only-audit-given-axioms` |

F1 is `ev.set_f1(reported, gold.gold_violations)` (a clean taxonomy answered `[]` scores
F1 = 1). `violated` lists each id at most once. The `notes` are what GEPA reads, so make
them specific: for a missed axiom, the checker's `detail` and `constraint` from
`gold.gold_detail`; for a sound axiom reported, both classes' tags from `A.TAG_SHEET`
and why no constraint applies; for a wrong methodology, the answer, the gold id and the
brief's decisive signals.
""", auto_points=9)
ps.todo(
    stub="""
    W_METHOD, W_VIOLATIONS = 0.4, 0.6

    def tags(name: str) -> str:
        t = A.TAG_SHEET[name]
        return f"{t.rigidity} {t.identity} {t.unity} {t.dependence}"

    def audit_scorer(gold, pred) -> ev.ScoreReport:
        # TODO
        raise NotImplementedError
    """,
    solution="""
    W_METHOD, W_VIOLATIONS = 0.4, 0.6

    def tags(name: str) -> str:
        t = A.TAG_SHEET[name]
        return f"{t.rigidity} {t.identity} {t.unity} {t.dependence}"

    def audit_scorer(gold, pred) -> ev.ScoreReport:
        notes, violated = [], []

        answered = getattr(pred, "methodology", None)
        method = methodology_id(answered)
        if method is None:
            violated.append("emit-structured-audit")
            notes.append(f"Methodology {answered!r} is not a catalogue id "
                         f"({', '.join(A.METHODOLOGY_IDS)}).")
        method_ok = method == gold.gold_methodology
        if not method_ok:
            signals = ch5.recommend_methodology(gold.brief)["reason"]
            notes.append(f"Methodology: answered {method or answered!r}, expected "
                         f"{gold.gold_methodology!r}; the brief's decisive signals: {signals}.")
            violated.append(f"choose-{gold.gold_methodology}")

        found = parse_violations(getattr(pred, "violations", None))
        if found is None:
            f1 = 0.0
            violated.append("emit-structured-audit")
            notes.append("Violations must be a JSON array of axioms copied from the "
                         "taxonomy, e.g. [\\"Person <= Student\\"], or [] for none.")
        else:
            given = {A.format_axiom(*p) for p in A.parse_taxonomy(gold.taxonomy)}
            gold_set = set(gold.gold_violations)
            f1 = ev.set_f1(found, gold_set)[2]
            missed = gold_set - set(found)
            sound = [a for a in found if a in given and a not in gold_set]
            invented = [a for a in found if a not in given]
            if missed:
                violated.append("apply-ontoclean-constraints")
                for d in gold.gold_detail:
                    if d["axiom"] in missed:
                        notes.append(f"Missed {d['axiom']}: {d['detail']} "
                                     f"[{d['constraint']}]. It is logically consistent; "
                                     f"the tag sheet, not a reasoner, shows the error.")
            if sound:
                violated.append("only-report-real-violations")
                for a in sound:
                    sub, sup = a.split(" <= ")
                    notes.append(f"{a} is sound: {sup} ({tags(sup)}) may subsume "
                                 f"{sub} ({tags(sub)}); no constraint is breached.")
            if invented:
                violated.append("only-audit-given-axioms")
                notes.append(f"Not in the submitted taxonomy (report axioms exactly as "
                             f"given): {invented}.")

        score = W_METHOD * method_ok + W_VIOLATIONS * f1
        notes.append(f"methodology_ok={int(method_ok)} violation_f1={f1:.2f}")
        return ev.ScoreReport(score, notes, list(dict.fromkeys(violated)))
    """)
ps.check("B2", """
gold = next(ex for ex in dev if ex.id == "carrow-estate")      # methontology; Door <= Doorway
clean = next(ex for ex in dev if ex.id == "warehouse-robotics")  # samod; no violations
P = lambda m, v: dspy.Prediction(methodology=m, violations=v)
cases = [
    (gold, P("METHONTOLOGY", '["Door <= Doorway"]'), 1.0, set()),
    (gold, P("methontology", '["Door ⊑ Doorway"]'), 1.0, set()),
    (gold, P("NeOn", '["Door <= Doorway"]'), 0.6, {"choose-methontology"}),
    (gold, P("waterfall", '["Door <= Doorway"]'), 0.6, {"emit-structured-audit", "choose-methontology"}),
    (gold, P("methontology", "[]"), 0.4, {"apply-ontoclean-constraints"}),
    (gold, P("methontology", '["Door <= Doorway", "Tenant <= Person"]'), 0.4 + 0.6 * 2 / 3,
     {"only-report-real-violations"}),
    (gold, P("methontology", '["Doorway <= Door"]'), 0.4,
     {"only-audit-given-axioms", "apply-ontoclean-constraints"}),
    (gold, P("methontology", "Door <= Doorway"), 0.4, {"emit-structured-audit"}),
    (gold, P("fake", None), 0.0, {"emit-structured-audit", "choose-methontology"}),
    (clean, P("SAMOD", "[]"), 1.0, set()),
    (clean, P("samod", '["Operator <= Person"]'), 0.4, {"only-report-real-violations"}),
]
for g, p, score, violated in cases:
    r = audit_scorer(g, p)
    assert abs(r.score - score) < 1e-6, (p, r.score, score)
    assert set(r.violated) == violated and len(r.violated) == len(set(r.violated)), (p, r.violated)
    assert all(v in A.AUDIT_RULEBOOK for v in r.violated)
missed = audit_scorer(gold, P("methontology", "[]"))
assert any("dependent-cannot-subsume-independent" in n for n in missed.notes), "name the constraint"
sound = audit_scorer(gold, P("methontology", '["Door <= Doorway", "Tenant <= Person"]'))
assert any("Tenant" in n and "+D" in n for n in sound.notes), "explain why the axiom is sound"
""")

ps.problem("B3", "The auditor as a DSPy program", 6, """
Write a signature `AuditSubmission` with inputs `brief`, `taxonomy`, `meta_properties`
and outputs `methodology`, `violations` and a one-sentence `justification`, and a
factory `AuditProgram(instruction)` returning a `dspy.Module` with a single
`dspy.Predict` whose instruction is `instruction`. The field descriptions are part of
the prompt (manual marks): say what format `violations` must take. Configure Claude and
run the program once on `train[0]`.
""", auto_points=3)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    # TODO: class AuditSubmission(dspy.Signature): ...
    # TODO: def AuditProgram(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: AuditProgram()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = A.BASELINE_INSTRUCTION

    class AuditSubmission(dspy.Signature):
        \"\"\"Draft the design-review verdict for one ontology project submission.\"\"\"

        brief: str = dspy.InputField(desc="the client's project brief")
        taxonomy: str = dspy.InputField(
            desc="the draft taxonomy, one subsumption 'Sub <= Super' per line")
        meta_properties: str = dspy.InputField(
            desc="the workshop tag sheet: 'Class: rigidity identity unity dependence', "
                 "e.g. 'Student: ~R -I -U +D'")
        methodology: str = dspy.OutputField(
            desc="one id: methontology, on-to-knowledge, diligent, neon or samod")
        violations: str = dspy.OutputField(
            desc='JSON array of the offending axioms copied exactly from the taxonomy, '
                 'e.g. ["Person <= Student"]; [] if there are none')
        justification: str = dspy.OutputField(desc="one sentence for the client")

    def AuditProgram(instruction: str = BASELINE_INSTRUCTION):
        class _Auditor(dspy.Module):
            def __init__(self):
                super().__init__()
                self.audit = dspy.Predict(AuditSubmission.with_instructions(instruction))

            def forward(self, brief: str, taxonomy: str, meta_properties: str):
                return self.audit(brief=brief, taxonomy=taxonomy,
                                  meta_properties=meta_properties)

        return _Auditor()

    lm = llm.configure_dspy()
    smoke = AuditProgram()(**train[0].inputs())
    print(smoke.methodology, "|", smoke.violations, "|", smoke.justification)
    """)
ps.check("B3", """
assert set(AuditSubmission.input_fields) == {"brief", "taxonomy", "meta_properties"}
assert {"methodology", "violations"} <= set(AuditSubmission.output_fields)
_program = AuditProgram("custom instruction")
assert len(list(_program.named_predictors())) == 1
assert opt.instruction_of(_program) == "custom instruction"
assert isinstance(smoke.methodology, str)
""")

ps.problem("B4", "Baseline on the development split, with its cost", 8, """
Evaluate the baseline program on `dev` with `ev.evaluate_dataset`, inside `llm.meter(lm)`.
Store the result in `baseline_dev` and the cost in `baseline_dev_cost`; show the per-item
rows.

Then write an **error analysis**: for each non-perfect item, which guideline was violated
and why you think Claude did it. Keep three kinds of failure apart — format (the
contract), methodology (reading the brief), and OntoClean (reading the tag sheet) — and
say which one the scorer's weights make most expensive.
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(AuditProgram(), dev, audit_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    pd.DataFrame(baseline_dev["rows"])
    """)
ps.check("B4", """
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
The answer to hand in is the analysis of *your* run; what a strong model typically does
with the bare baseline instruction:

* **Format** is the most likely loss: prose or a bulleted list instead of a JSON array,
  axioms paraphrased ("Door should not be under Doorway"), or the methodology written as
  a sentence. Each costs the whole 0.6 or 0.4 through `emit-structured-audit` — the
  cheapest thing to fix (state the contract) and the most expensive to leave.
* **Methodology** errors cluster on briefs with a secondary signal: *citizen-app*
  (SAMOD, but "fed by the council's databases" invites NeOn) and occasionally the
  On-To-Knowledge briefs, where a model may prefer METHONTOLOGY as "the" methodology.
* **OntoClean**: with the tag sheet in the input Claude usually applies the rigidity and
  unity constraints; the one most often missed is the dependence-only breach
  (*carrow-estate* `Door <= Doorway`, *pennine-libraries* `Novel <= Translation`),
  because nothing about the names sounds wrong. Over-reporting happens too — flagging
  `Tenant <= Person` "because roles are problematic", i.e. matching the pattern
  *role + kind* without checking the direction.

Cost: 8 calls, typically a few tens of cents with thinking; this is the unit price of
every later comparison.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
GEPA rewrites the instruction by reflecting on the scorer's feedback. It can only learn
a guideline that the training data gives the program a chance to break, it overfits
small training sets, and every metric call is billed. The rules: **optimise on `train`,
select on `dev`, report on `test`** — with a cost and a noise estimate next to every
number.
""")

ps.problem("C1", "Which guidelines can the training data teach?", 7, """
A guideline only appears in GEPA's feedback if some training answer *can* violate it.
Implement `can_violate(rule_id, ex) -> bool`: is there **some** answer to `ex` for which
your `audit_scorer` would report `rule_id`? Then:

1. Build `c1`: a DataFrame indexed by rule id (every rule in `A.AUDIT_RULEBOOK`) with
   columns `train`, `dev`, `test` — the number of items in each split on which the rule
   can be violated.
2. Build `ablated_train`: `train` with every **sound** axiom removed from each taxonomy
   (and `meta_properties` restricted to the classes that remain), dropping items left
   with no axioms. Add its counts as a column `ablated_train`.

In writing: predict what GEPA would learn from `ablated_train` and what would happen on
`test`. Why is this the dangerous kind of data change? State the general principle.
""", auto_points=5)
ps.todo(
    stub="""
    def can_violate(rule_id: str, ex) -> bool:
        # TODO
        raise NotImplementedError

    c1 = None              # TODO (1)
    ablated_train = None   # TODO (2), then add the column to c1
    """,
    solution="""
    def sound_axioms(ex) -> list[str]:
        return [A.format_axiom(*p) for p in A.parse_taxonomy(ex.taxonomy)
                if A.format_axiom(*p) not in ex.gold_violations]

    def can_violate(rule_id: str, ex) -> bool:
        if rule_id in {"emit-structured-audit", "only-audit-given-axioms"}:
            return True                    # any answer can break the format or invent
        if rule_id.startswith("choose-"):
            return rule_id == f"choose-{ex.gold_methodology}"
        if rule_id == "apply-ontoclean-constraints":
            return bool(ex.gold_violations)
        if rule_id == "only-report-real-violations":
            return bool(sound_axioms(ex))
        raise KeyError(rule_id)

    def counts(rows):
        return [sum(can_violate(rule.id, ex) for ex in rows) for rule in A.AUDIT_RULEBOOK]

    c1 = pd.DataFrame({"train": counts(train), "dev": counts(dev), "test": counts(test)},
                      index=A.AUDIT_RULEBOOK.ids)

    ablated_train = []
    for ex in train:
        keep = [p for p in A.parse_taxonomy(ex.taxonomy)
                if A.format_axiom(*p) in ex.gold_violations]
        if not keep:
            continue
        ablated_train.append(ex.copy(
            taxonomy="\\n".join(A.format_axiom(*p) for p in keep),
            meta_properties=A.meta_properties_text(keep),
        ).with_inputs("brief", "taxonomy", "meta_properties"))
    c1["ablated_train"] = counts(ablated_train)
    c1
    """)
ps.check("C1", """
assert isinstance(c1, pd.DataFrame) and set(c1.index) == set(A.AUDIT_RULEBOOK.ids)
assert {"train", "dev", "test", "ablated_train"} <= set(c1.columns)
for _split, _rows in [("train", train), ("dev", dev), ("test", test)]:
    assert c1.loc["apply-ontoclean-constraints", _split] == sum(bool(e.gold_violations) for e in _rows)
    for _m in A.METHODOLOGY_IDS:
        assert c1.loc[f"choose-{_m}", _split] == sum(e.gold_methodology == _m for e in _rows)
    assert c1.loc["emit-structured-audit", _split] == len(_rows)
assert c1.loc["only-report-real-violations", "train"] == 8
assert c1.loc["only-report-real-violations", "ablated_train"] == 0
assert len(ablated_train) == 7 and all(e.gold_violations for e in ablated_train)
assert all(set(e.inputs().keys()) == {"brief", "taxonomy", "meta_properties"} for e in ablated_train)
for _e in ablated_train:
    _pairs = A.parse_taxonomy(_e.taxonomy)
    assert {A.format_axiom(*p) for p in _pairs} == set(_e.gold_violations)
    assert set(_e.meta_properties.split("\\n")) == set(A.meta_properties_text(_pairs).split("\\n"))
    # no answer on an ablated item can be marked as over-reporting
    _all = dspy.Prediction(methodology=_e.gold_methodology, violations=[A.format_axiom(*p) for p in _pairs])
    assert "only-report-real-violations" not in audit_scorer(_e, _all).violated
""")
ps.written("""
On the full training split every guideline is teachable: every methodology appears, 7 of
8 taxonomies contain a violation and all 8 contain a sound axiom. After the ablation,
`only-report-real-violations` can be violated on **zero** training items: every axiom
left is a real violation, so "flag everything" scores perfectly. GEPA would be rewarded
for — and could well write down — an instruction like "report every subsumption that
involves a role, phase or material", and dev/test (which still contain sound axioms: see
the `dev`/`test` columns) would reveal an auditor that cries wolf on `Student <= Person`.

It is dangerous because nothing looks broken: the training score goes *up*, the
optimiser converges, and the only symptom is lower precision on held-out data — which you
see only if the held-out data contains the phenomenon. (The ablation also drops the
clean *northline-rail* submission, the only training item whose right answer is `[]`.)
Principle: **a failure mode your training data makes impossible is one the optimiser
cannot learn to avoid; a failure mode your evaluation data makes impossible is one you
will ship.** Balance splits by phenomenon, and check teachability before paying for
optimisation.
""")

ps.problem("C2", "A budgeted GEPA run, reported on test", 12, """
1. Build the GEPA feedback metric from your scorer and `A.AUDIT_RULEBOOK`, and a separate
   reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Save the tuned instruction to `config.artifacts_dir() / "ch05_audit_instruction.txt"`.
4. Add the **hand-written guidelines** contender,
   `A.AUDIT_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)`, and evaluate baseline,
   guidelines and GEPA-tuned on **`test`**, each inside its own `llm.meter`. Build `c2`
   with columns `program` (`"baseline"`, `"guidelines"`, `"gepa"`), `test_mean`,
   `violations`, `eval_usd`, `optimisation_usd` (GEPA's cost for `"gepa"`, 0 otherwise)
   and `instruction_chars`.

In writing: read the instruction diff. Which guidelines did GEPA put into words, which did
it miss (compare with `c1`), and did it add anything that only fits the eight training
clients? Which program would you deploy, and what would change your mind?
""", auto_points=5)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    instruction_path = config.artifacts_dir() / "ch05_audit_instruction.txt"
    guidelines_instruction = A.AUDIT_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), save, c2
    c2 = None
    """,
    solution="""
    GEPA_BUDGET = 60
    instruction_path = config.artifacts_dir() / "ch05_audit_instruction.txt"
    guidelines_instruction = A.AUDIT_RULEBOOK.as_guidelines(BASELINE_INSTRUCTION)

    gepa_metric = ev.make_gepa_metric(audit_scorer, A.AUDIT_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(AuditProgram(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    print("GEPA cost:", gepa_cost)

    contenders = {"baseline": AuditProgram(),
                  "guidelines": AuditProgram(guidelines_instruction),
                  "gepa": tuned}
    rows, test_results = [], {}
    for name, program in contenders.items():
        with llm.meter(lm) as cost:
            result = ev.evaluate_dataset(program, test, audit_scorer)
        test_results[name] = result
        rows.append({"program": name, "test_mean": result["mean_score"],
                     "violations": result["violations"], "eval_usd": cost["usd"],
                     "optimisation_usd": gepa_cost["usd"] if name == "gepa" else 0.0,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    print(opt.OptimisationResult(tuned, test_results["baseline"], test_results["gepa"],
                                 opt.instruction_of(contenders["baseline"]),
                                 opt.instruction_of(tuned)).report())
    c2
    """)
ps.check("C2", """
_ids = lambda rows: {ex.id for ex in rows}
assert not (_ids(test) & (_ids(train) | _ids(dev))), "the test split must be untouched"
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 100
assert isinstance(c2, pd.DataFrame) and set(c2["program"]) == {"baseline", "guidelines", "gepa"}
assert {"test_mean", "violations", "eval_usd", "optimisation_usd", "instruction_chars"} <= set(c2.columns)
assert c2.set_index("program").loc[["baseline", "guidelines"], "optimisation_usd"].eq(0).all()
assert c2["test_mean"].between(0, 1).all()
""")
ps.written("""
Your diff will differ in wording; what to look for:

* **Made explicit.** The output contract (catalogue id; JSON array copied verbatim;
  `[]` when clean) is almost always learned, because `emit-structured-audit` fires on
  every malformed answer. The three OntoClean constraints usually appear, often
  rephrased as a procedure ("for each axiom, look up both classes' tags…"), and the
  methodology signals of whichever briefs the baseline got wrong.
* **Missed.** Only guidelines that fired on the reflection minibatches can be learned. A
  `choose-*` rule for a methodology the baseline already got right on train never
  appears in feedback, so it is absent from the instruction even though `c1` shows it
  was *teachable*: teachable is necessary, not sufficient.
* **Over-fitting.** Sentences naming training classes or clients ("Container is not
  Cargo", "for port projects choose NeOn") are memorised; they cost tokens on every call
  and do nothing on test, where the classes and clients are new — that is why the corpus
  is split by submission.

Deployment: the hand-written guidelines typically recover most of GEPA's gain at zero
optimisation cost, because the guidelines *are* the knowledge the feedback conveys.
Deploy the cheapest program whose test mean is within the noise of the best (C3) —
usually the guidelines — and pay for GEPA again when the error analysis shows failures
the guidelines do not cover (e.g. a new client domain). A longer instruction is paid on
every call, forever. A test delta ≈ 0 is a legitimate result, not a failure to report.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 8, """
Eight test items at temperature 1.0: one item changes a mean by up to 0.125. With caching
**disabled** (`fresh = llm.dspy_lm(cache=False)` and `with dspy.context(lm=fresh): ...`),
run the baseline and the GEPA-tuned programs on `test` three times each, inside
`llm.meter(fresh)` (store as `c3_cost`); store the mean scores in
`runs = {"baseline": [..3..], "gepa": [..3..]}`.

Set `verdict_c3` to `"significant"` if `|mean_gepa − mean_baseline| > 2 ·
max(sd_gepa, sd_baseline)` (sample standard deviations), else `"not significant"`. In
writing: what does this say about the C2 table, and what would a credible evaluation of
the auditor need?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs inside llm.meter(fresh) as c3_cost, then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    import statistics as st

    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(AuditProgram(), test, audit_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, audit_scorer)["mean_score"])
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
assert {"calls", "usd"} <= set(c3_cost) and c3_cost["calls"] >= 2 * 3 * len(test)
_mean = {k: _st.mean(v) for k, v in runs.items()}
_sd = {k: _st.stdev(v) for k, v in runs.items()}
assert verdict_c3 == ("significant" if abs(_mean["gepa"] - _mean["baseline"]) > 2 * max(_sd.values())
                      else "not significant")
""")
ps.written("""
Three runs is a crude noise estimate, but enough to stop over-claiming. If one program's
run-to-run spread is as large as the gap between programs, the C2 delta is not evidence.
Note a subtlety of this scorer: with a mostly deterministic task a strong model's sd can
come out as 0 on three runs, which makes *any* delta "significant" by the 2·sd rule —
another reason three runs are not enough and the rule is only a screen.

A credible evaluation needs (i) more submissions — eight items resolve differences of
roughly ±0.1 at best; (ii) repeated runs reported as mean ± sd, or a paired bootstrap
over items; (iii) the same items and sampling settings for both programs; (iv) the cost
of each run; and (v) a per-component breakdown (methodology accuracy vs violation F1),
because the two halves fail for different reasons. The honest sentence: "GEPA changed
the mean test score by X ± Y over 3 runs of 8 submissions, at a cost of $Z."
""")

# =========================================================================== #
ps.part("D", "An audit agent, and planning the project", """
The agent audits one submission at a time with tools (`A.build_audit_tools`): the
methodology catalogue, the tag-sheet lookup, the OntoClean constraints, a **logical
consistency check** (the Chapter 3 tableau) — and, optionally, the two *engines* that
decide the gold labels: the methodology recommender and the OntoClean taxonomy checker.
The agent receives the brief and the taxonomy (`ws.task()`), not the tag sheet: it must
look tags up.
""")
ps.code("""
_ws = A.AuditWorkspace(A.AUDIT_CASES[0])
for t in A.build_audit_tools(_ws, include_engines=True):
    print(f"{t.name:22s} {t.description.splitlines()[0][:80]}")
print()
print(_ws.task())
""")

ps.problem("D1", "What do the tools buy the agent?", 10, """
1. Write `AUDITOR_PROMPT`: the agent must look up the tags of **every** class, check
   **every** axiom against the constraints, not treat logical consistency as evidence of
   correctness, and end with a JSON object
   `{"methodology": "<id>", "violations": ["Sub <= Super", ...], "justification": "..."}`.
2. Write `parse_audit(text) -> dspy.Prediction` returning `methodology` and `violations`
   from the **last** JSON object in the text that has a `"methodology"` key (it may be in
   a code fence, surrounded by prose, and contain nested objects), or
   `dspy.Prediction(methodology="", violations=None)` when there is none.
3. For each **test** submission and each toolset — `"engines"` (`include_engines=True`)
   and `"lookup-only"` (`include_engines=False`) — build a fresh `A.AuditWorkspace(case)`,
   its tools, an agent (`agents.build_agent(ws, system_prompt=..., tools=...)`), run it on
   `ws.task()`, and score `parse_audit(run.answer)` with your `audit_scorer`. Collect `d1`
   with columns `id`, `toolset`, `answer`, `score`, `violated`, `tool_calls`,
   `used_reasoner` (did it call `check_consistency`?), `used_engines` (did it call
   `recommend_methodology` or `check_taxonomy`?) and `usd_estimate`
   (`llm.chat_usage(run.messages)`).

In writing: compare the toolsets (mean score with n, cost per submission) and examine
every error. Did the agent call the reasoner, and did "consistent" ever mislead it? With
the engines available the task reduces to calling two tools — what, then, does the agent
add, and which toolset would you let draft verdicts for the board?
""", auto_points=4)
ps.todo(
    stub="""
    AUDITOR_PROMPT = \"\"\"TODO\"\"\"

    def parse_audit(text: str) -> dspy.Prediction:
        # TODO
        raise NotImplementedError

    d1 = None   # TODO: 2 toolsets x the test split
    """,
    solution="""
    AUDITOR_PROMPT = \"\"\"\\
    You are the first-pass auditor for Lattice & Loom's ontology design review board.
    For the submission you are given, produce two verdicts.

    1. Methodology. Call list_methodologies and choose the one whose situation the brief
       describes (reuse of existing resources -> neon; distributed, many contributors,
       evolving -> diligent; agile, iterative, test driven -> samod; business case or
       knowledge management pilot first -> on-to-knowledge; a greenfield, single-team,
       full-lifecycle build -> methontology). If a recommender tool is available, use it
       and check its matched signals against the brief.
    2. Taxonomy. For EVERY class, look up its tags with ontoclean_tags. For EVERY axiom
       'Sub <= Super' apply the constraints (list_constraints): Super ~R and Sub +R;
       Super ~U and Sub +U; Super +D and Sub -D are breaches. If a taxonomy checker tool
       is available, run it and reconcile its output with your own check. A logical
       consistency check does NOT show an axiom is correct: every draft is consistent.
       Report only axioms that appear in the taxonomy, copied exactly.

    End your reply with one JSON object and nothing after it:
    {"methodology": "<catalogue id>", "violations": ["Sub <= Super", ...],
     "justification": "<one sentence for the client>"}
    \"\"\"

    def parse_audit(text: str) -> dspy.Prediction:
        text = text or ""
        decoder, found = json.JSONDecoder(), None
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "methodology" in obj:
                found = obj
        if found is None:
            return dspy.Prediction(methodology="", violations=None)
        return dspy.Prediction(methodology=str(found.get("methodology") or ""),
                               violations=found.get("violations"))

    CASES = {c.id: c for c in A.AUDIT_CASES}
    rows = []
    for toolset in ("engines", "lookup-only"):
        for ex in test:
            ws = A.AuditWorkspace(CASES[ex.id])
            agent, _ = agents.build_agent(
                ws, system_prompt=AUDITOR_PROMPT,
                tools=A.build_audit_tools(ws, include_engines=(toolset == "engines")))
            run = agents.run_agent(agent, ws, ws.task())
            report = audit_scorer(ex, parse_audit(run.answer))
            names = ws.log.names()
            rows.append({"id": ex.id, "toolset": toolset, "answer": run.answer,
                         "score": report.score, "violated": report.violated,
                         "tool_calls": len(names),
                         "used_reasoner": "check_consistency" in names,
                         "used_engines": bool({"recommend_methodology", "check_taxonomy"} & set(names)),
                         "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(d1.groupby("toolset").agg(n=("score", "size"), mean=("score", "mean"),
                                    usd=("usd_estimate", "sum"), calls=("tool_calls", "mean")))
    d1.drop(columns="answer")
    """)
ps.check("D1", """
_p = parse_audit('Checked.\\n```json\\n{"methodology": "NeOn", "violations": ["Pump <= Borehole"]}\\n```')
assert methodology_id(_p.methodology) == "neon" and parse_violations(_p.violations) == ["Pump <= Borehole"]
_p = parse_audit('{"note": 1} then {"methodology": "samod", "violations": [{"axiom": "Person <= Child"}], "justification": "x"}')
assert _p.methodology == "samod" and parse_violations(_p.violations) == ["Person <= Child"]
_p = parse_audit('{"methodology": "diligent", "violations": []} {"methodology": "neon", "violations": []}')
assert _p.methodology == "neon"
for _bad in ["I recommend SAMOD.", "{}", "", '{"verdict": "yes"}']:
    _p = parse_audit(_bad)
    assert _p.methodology == "" and _p.violations is None, _bad
assert isinstance(d1, pd.DataFrame) and len(d1) == 2 * len(test)
assert set(d1["toolset"]) == {"engines", "lookup-only"}
assert {"id", "toolset", "answer", "score", "violated", "tool_calls", "used_reasoner",
        "used_engines", "usd_estimate"} <= set(d1.columns)
assert not d1.loc[d1.toolset == "lookup-only", "used_engines"].any(), "lookup-only has no engines"
_gold = {ex.id: ex for ex in test}
for _, _row in d1.iterrows():
    assert abs(audit_scorer(_gold[_row.id], parse_audit(_row.answer)).score - _row.score) < 1e-9
""")
ps.written("""
Expect (your run is the answer): with the engines, Claude calls `recommend_methodology`
and `check_taxonomy` and transcribes them, scoring at or near 1.0 on most of the 8
submissions — report it as "k/8", with its cost (several model turns per submission,
typically $0.1–0.4 each at opus-5 prices). Lookup-only is the real test of the
prompt: the agent must fetch 3–6 tags and apply three constraints per axiom. Typical
errors there are the dependence-only breach (*tarn-water* `Pump <= Borehole`) and
over-reporting a role under a kind; *law-firm-pilot* (two violations) and
*calder-shipyard* (two different constraints) are the hardest. The agent may call
`check_consistency`; it always answers "consistent", and an agent that reads that as
"no violations" fails exactly the submissions the board exists for — report whether yours
did.

With engines the agent adds little to the *labels* (they are the engines' output) but
still adds (i) the reconciliation — noticing when the recommender's matched signals are
stale or negated (Part A2), (ii) a justification the client can read, and (iii) an
explicit trace. The board should let the **engines** toolset draft verdicts, because its
labels are reproducible and its errors are the engines' known errors; the lookup-only
score is the measure of how much to trust the agent on a submission whose classes are
*not* yet on the tag sheet — where no engine can help.
""")

ps.problem("D2", "Planning the project: when are evaluation and reuse worth it?", 9, """
`A.MethodologyPlanMDP` plans a development project over `ch5.DEVELOPMENT_STEPS`: a step
is available only once its prerequisites are complete, each step costs its effort, and
`ship` pays the **measured** competency-question coverage of the partial AWO
(`A.measured_coverage`). Hooks: `coverage_fn(done)` and `cost_fn(done, action)`.

1. Solve it with `mdp.value_iteration`, roll out the greedy policy, and store `plan` (the
   list of actions), `v_star` (the value of the initial state) and `reachable` — the
   number of *unshipped* states reachable from the start (of the 128 subsets of steps).
2. **Evaluation.** Suppose shipping without `evaluation` delivers only `(1 − q)` of the
   coverage (defects found later). Derive, on paper, the `q*` above which the optimal
   plan evaluates, implement `evaluation_threshold(eval_cost, coverage)`, and verify it:
   sweep `q` over `np.linspace(0, 0.3, 31)` and record `d2_eval` (columns `q`,
   `evaluates`).
3. **Reuse (NeOn).** Suppose that once `reuse_search` is done, `taxonomy` and `axioms`
   cost `(1 − d)` of their listed cost. Derive `d*`, implement
   `reuse_threshold(search_cost, discountable_cost)`, and verify it with a sweep over
   `np.linspace(0, 0.8, 17)` recorded in `d2_reuse` (columns `discount`, `searches`).

In writing: what does `reachable` say about what a methodology is? What do the two
thresholds say about the steps real teams skip, and whose fault is it when an agent (or a
team) optimising a measured objective skips evaluation?
""", auto_points=6)
ps.todo(
    stub="""
    M = A.MethodologyPlanMDP()
    plan, v_star, reachable = None, None, None        # TODO (1)

    def evaluation_threshold(eval_cost: float, coverage: float) -> float:
        # TODO (2)
        raise NotImplementedError

    def reuse_threshold(search_cost: float, discountable_cost: float) -> float:
        # TODO (3)
        raise NotImplementedError

    d2_eval, d2_reuse = None, None                    # TODO (2), (3)
    """,
    solution="""
    M = A.MethodologyPlanMDP()
    V, pi = mdp.value_iteration(M)
    s0 = M.initial_state()
    episode = mdp.run_episode(M, mdp.greedy_policy(pi))
    plan, v_star = episode.actions, V[s0]
    for t in episode.transitions:
        print(f"  {str(t.state):9s} {t.action:22s} r={t.reward:+.3f}")

    seen, frontier = {s0}, [s0]
    while frontier:
        s = frontier.pop()
        for a in M.actions(s):
            if a == "ship":
                continue
            nxt = M.step(s, a)[0]
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    reachable = len(seen)
    print(f"V* = {v_star:.3f};  reachable project states: {reachable} of {2 ** len(M.names)}")
    print("skipped:", [s for s in M.names if s not in plan])

    def evaluation_threshold(eval_cost: float, coverage: float) -> float:
        # evaluate: coverage - eval_cost ; skip: (1 - q) * coverage  =>  evaluate iff q > eval_cost / coverage
        return eval_cost / coverage

    def reuse_threshold(search_cost: float, discountable_cost: float) -> float:
        # search: -search_cost - (1 - d) * C ; don't: -C  =>  search iff d > search_cost / C
        return search_cost / discountable_cost

    rows = []
    for q in np.linspace(0, 0.3, 31):
        Mq = A.MethodologyPlanMDP(coverage_fn=lambda done, q=q: A.measured_coverage(done)
                                  * (1.0 if "evaluation" in done else 1.0 - q))
        ep = mdp.run_episode(Mq, mdp.greedy_policy(mdp.value_iteration(Mq)[1]))
        rows.append({"q": round(float(q), 3), "evaluates": "evaluation" in ep.actions})
    d2_eval = pd.DataFrame(rows)

    STEPS = ch5.DEVELOPMENT_STEPS
    rows = []
    for d in np.linspace(0, 0.8, 17):
        def cost_fn(done, action, d=d):
            base = STEPS[action]["cost"]
            if "reuse_search" in done and action in ("taxonomy", "axioms"):
                return base * (1.0 - d)
            return base
        Md = A.MethodologyPlanMDP(cost_fn=cost_fn)
        ep = mdp.run_episode(Md, mdp.greedy_policy(mdp.value_iteration(Md)[1]))
        rows.append({"discount": round(float(d), 3), "searches": "reuse_search" in ep.actions})
    d2_reuse = pd.DataFrame(rows)

    q_star = evaluation_threshold(STEPS["evaluation"]["cost"], 1.0)
    d_star = reuse_threshold(STEPS["reuse_search"]["cost"],
                             STEPS["taxonomy"]["cost"] + STEPS["axioms"]["cost"])
    print(f"q* = {q_star:.3f}: first q that evaluates =",
          d2_eval[d2_eval.evaluates].q.min())
    print(f"d* = {d_star:.3f}: first d that searches  =",
          d2_reuse[d2_reuse.searches].discount.min())
    """)
ps.check("D2", """
assert abs(v_star - 0.25) < 1e-9, "coverage 1.0 minus 0.75 of effort"
assert plan[-1] == "ship"
assert set(plan[:-1]) == {"requirements", "competency_questions", "taxonomy", "axioms", "instances"}
_done = set()
for _a in plan[:-1]:
    assert all(r in _done for r in ch5.DEVELOPMENT_STEPS[_a]["requires"]), f"{_a} before its prerequisites"
    _done.add(_a)
assert reachable == 21
assert abs(evaluation_threshold(0.10, 1.0) - 0.10) < 1e-9 and abs(evaluation_threshold(0.10, 0.5) - 0.20) < 1e-9
assert abs(reuse_threshold(0.15, 0.45) - 1 / 3) < 1e-9
_q = evaluation_threshold(0.10, 1.0)
_clear = d2_eval[(d2_eval.q - _q).abs() > 0.015]
assert len(_clear) >= 25 and (_clear.evaluates == (_clear.q > _q)).all(), "sweep disagrees with q*"
_d = reuse_threshold(0.15, 0.45)
_clear = d2_reuse[(d2_reuse.discount - _d).abs() > 0.03]
assert len(_clear) >= 15 and (_clear.searches == (_clear.discount > _d)).all(), "sweep disagrees with d*"
""")
ps.written("""
**Plan.** requirements → competency questions → taxonomy → axioms → instances → ship,
V* = 1.0 − 0.75 = 0.25. It skips `reuse_search` and `evaluation`: under this reward
neither unlocks a competency question, so both are pure cost.

**Reachable = 21 of 128.** Precedence rules out 107 of the 128 combinations of
completed steps (you cannot hold axioms without a taxonomy, or a taxonomy without
competency questions). That is what a methodology *is*, stated as structure: not a
list of activities — every methodology in §5.1 has roughly the same activities — but
a constraint on the order in which the project's state may evolve. The methodologies
disagree about which orders they allow.

**Evaluation.** Evaluating pays `coverage − c_E`, skipping pays `(1 − q)·coverage`, so
evaluate iff `q > c_E / coverage = 0.10`: if unevaluated ontologies lose more than a
tenth of their value to defects found later, evaluation pays. The sweep flips at 0.10.
**Reuse.** Searching pays `−c_S − (1 − d)·(c_T + c_A)` against `−(c_T + c_A)`, so search
iff `d > c_S/(c_T + c_A) = 0.15/0.45 = 1/3`: NeOn's claim as an inequality — reuse is
worth looking for only if what you find displaces a third of the modelling work.

When a planner (or a team) skips evaluation, the planner is right and the **reward
model** is wrong: the measured objective (CQ coverage at ship time) does not credit what
evaluation buys. The fix is to measure what you care about — the `q` term, estimated
from defect data — not to hard-code "always evaluate" into the policy. The same holds for
the agents in this course: an agent that skips a check its reward does not price is
optimising correctly against a bad objective, which is why the D1 prompt and the scorer
make unverified claims costly.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
