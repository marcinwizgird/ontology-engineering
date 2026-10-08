"""Build the Chapter 9 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch09_natural_languages/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 9 — Ontologies and Natural Languages",
    title="Multilingual review sheets for a zoo alliance",
    coverage=("Keet §9.1 (multilingual ontologies, lexicons with morphology), §9.2 "
              "(verbalisation into controlled natural language, and parsing it back); "
              "course notebooks 01–03 of this chapter. Tools: DSPy + GEPA, an LLM judge "
              "validated against human labels, LangChain agents, and best-of-n resampling "
              "as an optimal-stopping MDP."),
    scenario="""
    The **Rhine–Meuse Zoo Alliance** — five zoos in the Netherlands and Germany plus an
    English-speaking partner — keeps one shared animal-husbandry ontology: species,
    diets, enclosures, named animals. Every quarter the **Husbandry Standards
    Committee** has the axioms reviewed by the keepers who work with the animals, each
    in their own language. Keepers do not read OWL, so every axiom is *verbalised*
    into a controlled sentence on a review sheet ("Jedes Okapi lebt in mindestens
    einem Gehege."). A sentence that says something other than the axiom gets a wrong
    rule signed off; a sentence a keeper cannot read gets rewritten by hand, which
    costs the committee about $1.50 of keeper time per sentence.

    You are the ontology engineer asked to replace the translator with a Claude
    verbaliser. Your brief:

    1. **Grade it without a model where you can.** Verbalisation has an inverse: parse
       the sentence back and compare axioms. That round trip is free and exact — and
       it cannot see whether a keeper will accept the sentence. Build the grader from
       both halves, and audit the lexicon the round trip depends on.
    2. **Grade readability with a judge you have validated.** The keepers labelled 22
       sentences. An LLM judge is only allowed onto the review pipeline if it agrees
       with them better than the committee's regex style checks do.
    3. **Build and optimise the verbaliser honestly** — train / dev / test split by
       axiom, a GEPA budget, the cost of every run, run-to-run noise, and one run
       that shows what happens when you optimise the exact half alone.
    4. **Decide when to stop resampling.** Model best-of-n drafting as an
       optimal-stopping MDP, derive the stopping rule, calibrate it with live samples,
       and ship an agent that checks its own drafts before it answers.

    The lexicon (en/nl/de, with morphology), the controlled grammar and its parser,
    the committee's style checks, the corpus (15 axioms × 2 languages = 30 items,
    split 5/5/5 axioms), the keepers' readability panel and the resampling MDP are
    provided in `ch09_agentic.py`.
    """,
    effort="10–12 hours",
    api_budget="≈ $8–16 *estimated* on `claude-opus-5` for a full solutions run "
               "(≈ 330 DSPy calls at ≈ $0.02–0.04 each, plus ≈ $1–2 for ten agent "
               "episodes; the two GEPA runs and the noise study are the largest lines). "
               "Nothing here has been measured — your cost lines are the measurement. "
               "Re-running unchanged cells is free: DSPy caches identical requests, "
               "except where a problem asks for `cache=False`.",
)

ps.setup("""
import re, random, statistics as st
import dspy
import numpy as np
import pandas as pd
import ch09_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

print(A.validate())                                   # every gold artefact re-checked
train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
ALL = {ex.id: ex for ex in train + dev + test}
print(f"train {len(train)} / dev {len(dev)} / test {len(test)} items "
      f"(split by axiom: {len({ex.axiom_id for ex in test})} test axioms)")
print(test[1].axiom, f"[{test[1].language}]")
print(test[1].terms)
""")

# =========================================================================== #
ps.part("A", "The free grader, and what it cannot see", """
`A.round_trip(sentence, axiom, language)` parses a sentence with the controlled
grammar and compares the recovered axiom with the intended one. `A.lint(...)` runs the
committee's regex style checks. Read `A.STYLE_GUIDE` and the docstrings of `parse_cnl`
and `lint` before you start: both are *deliberately* imperfect in the ways real ones are.
""")
ps.code("""
for language, patterns in A.STYLE_GUIDE.items():
    print(language)
    for construct, pattern in patterns.items():
        print(f"   {construct:11s} {pattern}")
ex = ALL["okapi-lives-in-enclosure-de"]
print("\\n", ex.reference, "->", A.round_trip(ex.reference, A.gold_axiom(ex), "de"))
""")

ps.problem("A1", "Faithful is not the same as acceptable", 10, """
For **three** corpus items of your choice (keys of `ALL`, at least two languages), write
two sentences each:

* `"faithful-but-bad"` — round-trips **exactly** to the item's axiom, but a keeper
  would reject it (wrong article, gender, number, case, capitalisation, a leaked
  identifier, a word from the wrong language, …). Not the reference sentence.
* `"fluent-but-unparseable"` — correct, natural language that a keeper would accept
  but the round trip rejects (it does not parse, or parses to another axiom).

Build a DataFrame `a1` with columns `item`, `kind`, `sentence`, `faithful`
(`A.round_trip(...)["faithful"]`) and `lint_issues` (the rule ids `A.lint` reports).
At least one of your faithful-but-bad sentences must pass the lint with **no** issue.

Then answer in writing: (a) why the round trip cannot be the whole metric, and why the
lint cannot be the rest of it; (b) the alliance could hand-write a template verbaliser
instead of using Claude — when is the LLM worth it, and what makes it safe to use here?
""", auto_points=6)
ps.todo(
    stub="""
    candidates = {
        # "item-id": {"faithful-but-bad": "...", "fluent-but-unparseable": "..."},
    }
    # TODO: fill `candidates` for three items, then build the DataFrame `a1`.
    a1 = None
    """,
    solution="""
    candidates = {
        "giraffe-eats-only-leaves-de": {
            "faithful-but-bad": "Jede Giraffe frisst nur Blatt.",          # number; lint misses it
            "fluent-but-unparseable": "Giraffen fressen ausschließlich Blätter.",
        },
        "lion-eats-herbivore-nl": {
            "faithful-but-bad": "Elke leeuw eet ten minste een Herbivore.",   # English identifier
            "fluent-but-unparseable": "Leeuwen eten herbivoren.",
        },
        "plants-not-animals-en": {
            "faithful-but-bad": "No plant is a animal.",                      # article
            "fluent-but-unparseable": "Plants are never animals.",
        },
    }
    rows = []
    for item, pair in candidates.items():
        ex = ALL[item]
        axiom = A.gold_axiom(ex)
        for kind, sentence in pair.items():
            rows.append({"item": item, "kind": kind, "sentence": sentence,
                         "faithful": A.round_trip(sentence, axiom, ex.language)["faithful"],
                         "lint_issues": sorted({i["rule"] for i in A.lint(sentence, axiom, ex.language)})})
    a1 = pd.DataFrame(rows)
    a1
    """)
ps.check("A1", """
assert isinstance(a1, pd.DataFrame) and len(candidates) >= 3
assert {"item", "kind", "sentence", "faithful", "lint_issues"} <= set(a1.columns)
assert len({ALL[i].language for i in candidates}) >= 2, "use at least two languages"
norm = lambda s: re.sub(r"\\s+", " ", s).strip().lower()
for item, pair in candidates.items():
    ex = ALL[item]
    axiom = A.gold_axiom(ex)
    bad, fluent = pair["faithful-but-bad"], pair["fluent-but-unparseable"]
    assert A.round_trip(bad, axiom, ex.language)["faithful"], f"{item}: 'faithful-but-bad' must round-trip"
    assert norm(bad) != norm(ex.reference), f"{item}: do not reuse the reference sentence"
    assert not A.round_trip(fluent, axiom, ex.language)["faithful"], f"{item}: the fluent one round-trips"
for _, row in a1.iterrows():
    ex = ALL[row["item"]]
    assert row["faithful"] == A.round_trip(row["sentence"], A.gold_axiom(ex), ex.language)["faithful"]
clean = [p["faithful-but-bad"] for i, p in candidates.items()
         if not A.lint(p["faithful-but-bad"], A.gold_axiom(ALL[i]), ALL[i].language)]
assert clean, "find a faithful-but-bad sentence that the lint does not flag"
""")
ps.written("""
**(a)** The round trip answers exactly one question — *did the meaning survive?* — and
answers it perfectly: a `True` is a proof that the sentence encodes the axiom under the
grammar, a `False` comes with the axiom it did say. But the review sheet exists to be
*read*, and the grammar is deliberately tolerant of inflection (`Jeder/Jede/Jedes`,
`a/an`, singular or plural) and lenient about unknown words, so "No plant is a animal",
"Jede Giraffe frisst nur Blatt" and even a Dutch sentence with an English noun all score
a perfect round trip. The lint closes part of that gap, but only the part someone wrote a
regex for: in the table, "nur Blatt" (number) passes it, and so would a wrong German case
("mindestens ein Gehege" after *lebt in*) or lower-case German nouns. The lint is a
finite list of known failure modes; keepers reject sentences for reasons nobody listed
yet. A deterministic metric that is exact on meaning and blind on half of presentation is
the right *first* half of a grader, not the whole of it.

**(b)** A template verbaliser is the right tool for a fixed set of constructs in one
language. It stops being cheap as the table grows: every construct × language needs its
determiners, gender, case government, plural and word order encoded, and each new
language (the alliance is talking to a Danish zoo) is a grammar project, not a glossary
(Notebook 2, Exercise 2.1). An LLM carries that morphology for free and handles
constructs nobody templated. What makes it *safe* is precisely the inverse: every Claude
sentence is parsed back before it reaches a keeper, so a sentence that says something
else is caught mechanically, at zero cost, with no gold label. The remaining risk —
unreadable but faithful — is the one the judge in Problem B4 is for.
""")

ps.problem("A2", "Audit the translation agency's delivery", 8, """
The round trip is only as good as the lexicon it parses with. The agency's first Dutch
delivery is `A.NL_DELIVERY_V0`; `A.lexicon_with("nl", A.NL_DELIVERY_V0)` is the lexicon
with it installed.

(a) Implement `audit_lexicon(lexicon, language) -> set[tuple[str, str]]` returning
`(kind, term)` pairs for four kinds of defect, using `A.forms(term, language, lexicon)`:

| kind | meaning |
|---|---|
| `"missing"` | the term has no label in this language |
| `"collision"` | a surface form of the term is also a form of another term (report **both** terms) |
| `"identifier"` | a label looks like a camelCase identifier (`[a-z][A-Z]`) |
| `"template-word"` | a label contains, as a whole word, one of `A.TEMPLATE_WORDS[language]` |

(b) Build `a2`: one row per Dutch sentence in the corpus references and in
`A.READABILITY_PANEL`, with columns `source` (item or panel id), `sentence`,
`faithful_before` (with `A.LEXICON`) and `faithful_after` (with the delivery).

In writing: which defect broke which sentences, and which kind of defect is the most
dangerous in production, and why?
""", auto_points=5)
ps.todo(
    stub="""
    def audit_lexicon(lexicon: dict, language: str) -> set[tuple[str, str]]:
        # TODO (a)
        raise NotImplementedError

    delivery = A.lexicon_with("nl", A.NL_DELIVERY_V0)
    a2 = None       # TODO (b)
    """,
    solution="""
    def audit_lexicon(lexicon: dict, language: str) -> set[tuple[str, str]]:
        issues: set[tuple[str, str]] = set()
        owners: dict[str, set[str]] = {}
        stop = A.TEMPLATE_WORDS.get(language, set())
        for term, entry in lexicon.items():
            data = entry.get(language) or {}
            if not data.get("label"):
                issues.add(("missing", term))
                continue
            if re.search(r"[a-z][A-Z]", data["label"]):
                issues.add(("identifier", term))
            if any(w.lower() in stop for w in re.findall(r"\\w+", data["label"])):
                issues.add(("template-word", term))
            for form in A.forms(term, language, lexicon):
                owners.setdefault(form.lower(), set()).add(term)
        for terms in owners.values():
            if len(terms) > 1:
                issues |= {("collision", t) for t in terms}
        return issues

    delivery = A.lexicon_with("nl", A.NL_DELIVERY_V0)
    print(sorted(audit_lexicon(delivery, "nl")))

    rows = []
    sources = [(f"{aid}-nl", refs["nl"], ax) for aid, _, ax, refs in A.CORPUS if "nl" in refs]
    sources += [(p["id"], p["sentence"], A.AXIOMS[p["axiom_id"]])
                for p in A.READABILITY_PANEL if p["language"] == "nl"]
    for source, sentence, axiom in sources:
        rows.append({"source": source, "sentence": sentence,
                     "faithful_before": A.round_trip(sentence, axiom, "nl")["faithful"],
                     "faithful_after": A.round_trip(sentence, axiom, "nl", delivery)["faithful"]})
    a2 = pd.DataFrame(rows)
    a2[a2.faithful_before != a2.faithful_after]
    """)
ps.check("A2", """
for language in A.LANGUAGES:
    assert audit_lexicon(A.LEXICON, language) == set(), f"false alarm on the reviewed {language} lexicon"
assert audit_lexicon(A.lexicon_with("nl", A.NL_DELIVERY_V0), "nl") == {
    ("missing", "Insectivore"), ("collision", "Enclosure"), ("collision", "Paddock"),
    ("identifier", "caresFor"), ("template-word", "Okapi")}
toy = {"Foo": {"kind": "class", "en": {"label": "only child"}},
       "Bar": {"kind": "class", "en": {"label": "bar", "plural": "bars"}},
       "Baz": {"kind": "class", "en": {"label": "Bars"}}}
assert audit_lexicon(toy, "en") == {("template-word", "Foo"), ("collision", "Bar"), ("collision", "Baz")}
assert isinstance(a2, pd.DataFrame) and len(a2) == 15
assert {"source", "sentence", "faithful_before", "faithful_after"} <= set(a2.columns)
assert a2["faithful_before"].all()
_d = A.lexicon_with("nl", A.NL_DELIVERY_V0)
_ax = {**{f"{aid}-nl": ax for aid, _, ax, refs in A.CORPUS if "nl" in refs},
       **{p["id"]: A.AXIOMS[p["axiom_id"]] for p in A.READABILITY_PANEL}}
for _, row in a2.iterrows():
    assert row["faithful_after"] == A.round_trip(row["sentence"], _ax[row["source"]], "nl", _d)["faithful"]
""")
ps.written("""
Four sentences stop round-tripping: *anteater-is-insectivore* (Insectivore is missing, so
"insecteneter" no longer maps to anything), *keeper-cares-for-animal* (caresFor's label is
the identifier, so the real verb "verzorgt" is unknown), and panel P12 (both "okapi" —
the label is now "een okapi" — and "verblijf", which now resolves to Paddock because two
terms share it). The collision is the subtle one: the parser does not fail, it silently
maps the word to whichever term was registered last, so an Enclosure axiom reads back as
a Paddock axiom.

In production the **missing label** is the most dangerous, because it fails *open*:
`label()` falls back to the identifier, the verbaliser writes "Elke miereneter is een
Insectivore", the lenient parser maps the identifier straight back, and the round trip
reports success on a sentence that is not Dutch (compare P15). Collisions and template
words at least break the round trip loudly; a missing label only shows up in the lint or
in a keeper's complaint. So the audit belongs in the lexicon's CI, before any sentence is
generated — the exact metric is only exact relative to a lexicon someone has checked.
""")

# =========================================================================== #
ps.part("B", "A two-part grader, a Claude verbaliser, and a judge you can trust", """
The guidelines a scorer (or judge) can report are the committee's style guide, as
`A.CNL_RULEBOOK`. Note the last three: no regex in this project can report them.
""")
ps.code("""
for rule in A.CNL_RULEBOOK:
    print(f"{rule.id:26s} {rule.description[:95]}")
""")

ps.problem("B1", "The staged scorer: exact half, style half", 12, """
Implement `verbalisation_scorer(gold, pred) -> ev.ScoreReport`, where `gold` is a dataset
row (use `A.gold_axiom(gold)`, `gold.language`) and `pred.sentence` is the model's
sentence. Stages, in order:

| outcome | score | `violated` |
|---|---|---|
| empty, or `A.parse_cnl` returns `None` | 0.0 | `[f"template-for-{operator}"]` |
| parses, but to a different **construct** | 0.25 | `[f"template-for-{operator}"]` |
| parses to the right construct with different **terms** | 0.25 | `["preserve-the-terms"]` |
| faithful | `0.5 + 0.5 * max(0, 1 - 0.25 * k)` | the `k` distinct rule ids `A.lint` reports, first-seen order |

So a faithful sentence earns the exact half outright, and the style half loses a quarter
per distinct kind of lint issue. Unfaithful sentences earn no style credit — a readable
sentence that says the wrong thing is worse than useless on a review sheet. Put the
recovered axiom in `notes` when it differs (the words "recovered" and the axiom), and the
lint messages when there are any: that text is what GEPA's reflection reads.
""", auto_points=8)
ps.todo(
    stub="""
    def verbalisation_scorer(gold, pred) -> ev.ScoreReport:
        sentence = str(getattr(pred, "sentence", "") or "").strip()
        axiom, language = A.gold_axiom(gold), gold.language
        # TODO: the four stages from the table, in order.
        raise NotImplementedError
    """,
    solution="""
    def verbalisation_scorer(gold, pred) -> ev.ScoreReport:
        sentence = str(getattr(pred, "sentence", "") or "").strip()
        axiom, language = A.gold_axiom(gold), gold.language
        template = f"template-for-{axiom.operator}"
        recovered = A.parse_cnl(sentence, language) if sentence else None
        if recovered is None:
            what = "No sentence produced." if not sentence else (
                f"{sentence!r} is not controlled {language}: it does not parse.")
            return ev.ScoreReport(0.0, [what, f"Intended axiom: {axiom}."], [template])
        if recovered.key() != axiom.key():
            notes = [f"Round trip changed the meaning: intended {axiom}, recovered {recovered}."]
            if recovered.operator != axiom.operator:
                return ev.ScoreReport(0.25, notes, [template])
            return ev.ScoreReport(0.25, notes + ["Right construct, wrong words for the terms."],
                                  ["preserve-the-terms"])
        issues = A.lint(sentence, axiom, language)
        rules = list(dict.fromkeys(i["rule"] for i in issues))
        score = 0.5 + 0.5 * max(0.0, 1 - 0.25 * len(rules))
        notes = [f"Faithful: the round trip recovers {axiom}."]
        notes += [f"Style: {i['message']}" for i in issues]
        return ev.ScoreReport(round(score, 4), notes, rules)
    """)
ps.check("B1", """
P = lambda s: dspy.Prediction(sentence=s)
de, en = ALL["okapi-lives-in-enclosure-de"], ALL["tembo-is-elephant-en"]
cases = [
    (de, "Jedes Okapi lebt in mindestens einem Gehege.", 1.0, []),
    (de, "", 0.0, ["template-for-some"]),
    (de, "Okapis leben in Gehegen.", 0.0, ["template-for-some"]),
    (de, "Jedes Okapi ist ein Gehege.", 0.25, ["template-for-some"]),
    (de, "Jedes Okapi lebt in mindestens einem Stall.", 0.25, ["preserve-the-terms"]),
    (de, "Jedes Okapi lebt in mindestens ein Gehege.", 1.0, []),          # the blind spot
    (de, "Jeder Okapi lebt in mindestens einem Gehege.", 0.875, ["agree-in-gender"]),
    (de, "Jeder Okapi livesIn mindestens einem Gehege.", 0.75,
     ["use-the-lexicon-label", "agree-in-gender"]),
    (en, "Tembo is an elephant.", 1.0, []),
    (en, "Tembo is a elephant.", 0.875, ["correct-article"]),
    (en, "Every tembo is an elephant.", 0.0, ["template-for-type"]),
]
for gold, sentence, score, violated in cases:
    r = verbalisation_scorer(gold, P(sentence))
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (sentence, r.score, r.violated)
    assert all(v in A.CNL_RULEBOOK for v in r.violated)
wrong = verbalisation_scorer(de, P("Jedes Okapi ist ein Gehege."))
assert any("recovered" in n.lower() and "Okapi SubClassOf Enclosure" in n for n in wrong.notes)
for ex in train + dev + test:
    assert verbalisation_scorer(ex, P(ex.reference)).score == 1.0, ex.id
""")

ps.problem("B2", "The verbaliser as a DSPy program", 6, """
Write a signature `Verbalisation` with inputs `axiom`, `language`, `terms` and output
`sentence`, and a factory `Verbaliser(instruction)` returning a `dspy.Module` with a
single `dspy.Predict` whose instruction is `instruction`. The field descriptions are part
of the prompt (manual marks): say what a keeper needs, not what DSPy needs. Do **not**
put the style guide into the signature — the baseline must not know the templates; that
is what Part C optimises. Configure Claude and run the program once on `train[0]`.
""", auto_points=3)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = ("Write the axiom as one sentence in the requested language, "
                            "for a zoo keeper's review sheet.")

    # TODO: class Verbalisation(dspy.Signature): ...
    # TODO: def Verbaliser(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: Verbaliser()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = ("Write the axiom as one sentence in the requested language, "
                            "for a zoo keeper's review sheet.")

    class Verbalisation(dspy.Signature):
        \"\"\"Verbalise one axiom of the alliance's husbandry ontology for keepers.\"\"\"

        axiom: str = dspy.InputField(
            desc="the axiom in Manchester-like syntax, e.g. 'Okapi SubClassOf (livesIn some Enclosure)'")
        language: str = dspy.InputField(desc="language of the review sheet: en, nl or de")
        terms: str = dspy.InputField(
            desc="the approved word for each term in that language, with plural, "
                 "gender or de/het, and the case a German verb takes")
        sentence: str = dspy.OutputField(
            desc="exactly one sentence in the requested language, ending with a full stop, "
                 "and nothing else")

    def Verbaliser(instruction: str = BASELINE_INSTRUCTION):
        class _Verbaliser(dspy.Module):
            def __init__(self):
                super().__init__()
                self.write = dspy.Predict(Verbalisation.with_instructions(instruction))

            def forward(self, axiom: str, language: str, terms: str):
                return self.write(axiom=axiom, language=language, terms=terms)

        return _Verbaliser()

    lm = llm.configure_dspy()
    smoke = Verbaliser()(**train[0].inputs())
    print(train[0].axiom, f"[{train[0].language}] ->", smoke.sentence)
    """)
ps.check("B2", """
assert set(Verbalisation.input_fields) == {"axiom", "language", "terms"}
assert "sentence" in Verbalisation.output_fields
program = Verbaliser("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.sentence, str) and smoke.sentence.strip()
""")

ps.problem("B3", "Baseline on the development split, with its cost", 6, """
Evaluate the baseline on `dev` with `ev.evaluate_dataset` inside `llm.meter(lm)`; store
the result in `baseline_dev` and the cost in `baseline_dev_cost`, and show the per-item
rows **with the sentences** (run the program yourself or re-run — it is cached).

Write a short error analysis: which stage does each non-perfect item fail at (parse,
meaning, style), and is it a language problem or a format problem? Which of the
committee's rules could the scorer *not* have told you about?
""", auto_points=2)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(Verbaliser(), dev, verbalisation_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    _base = Verbaliser()
    pd.DataFrame([{**row, "language": ex.language, "sentence": _base(**ex.inputs()).sentence}
                  for row, ex in zip(baseline_dev["rows"], dev)])
    """)
ps.check("B3", """
assert baseline_dev["n"] == len(dev) == 10
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
Expect a *low* baseline — the instruction never mentions a controlled language, so
Claude writes good natural sentences: "Anteaters are insectivores.", "Okapis leben in
Gehegen.", "Tembo is an elephant." The last one is perfect (the type template *is*
natural English); most of the others fail at the **parse** stage (score 0,
`template-for-*`), because plural generic sentences and "Alle …"/"Ieder …" openings are
outside the grammar. That is a *format* problem, not a language problem: the sentences are
usually excellent Dutch and German, which is exactly the gap between the two halves of the
grader, seen from the other side.

Faithful sentences, when they occur, are typically clean on the lint because the term
sheet gives the right words and genders. What the scorer cannot tell you about is the last
three rules — a wrong German case after *lebt in*, a singular after *nur/alleen/only*,
lower-case German nouns — since no stage reports them; you only see them by reading the
sentences (or with the judge of B4). Report your own run's numbers: n = 10, the mean, the
violation histogram and the cost (≈ 10 calls, well under a dollar).
""")

ps.problem("B4", "Validate a readability judge against the keepers", 12, """
`A.READABILITY_PANEL` holds 22 faithful sentences with the keepers' majority label
(`acceptable`). Before a judge scores anything that matters, it has to agree with them.

1. Write a signature `ReadabilityVerdict` (inputs `sentence`, `language`, `terms`;
   outputs `acceptable: bool` and `problem: str`) and `judge_program =
   dspy.Predict(ReadabilityVerdict)`. Give it the term sheet (`A.term_sheet(axiom,
   language)`), never the human label. Write the instruction as the committee would brief
   a new reviewer. Wrap it as `judge_sentence(sentence, language, axiom) -> bool` (C2
   reuses it).
2. Implement `cohens_kappa(a, b)` for two equal-length boolean sequences
   (κ = (p_o − p_e)/(1 − p_e); return 1.0 when p_e = 1 and the raters agree fully).
3. Run the judge on the panel inside `llm.meter(lm)` (cost in `b4_cost`). Build `b4` with
   columns `id`, `language`, `human`, `judge`, `lint_ok` (no `A.lint` issue) and
   `b4_stats = {"judge": {"accuracy": …, "kappa": …}, "lint": {…}}`, both against
   `human`. Set `judge_trusted = kappa_judge >= 0.6 and kappa_judge > kappa_lint`.

In writing: where does the judge disagree with the keepers — and is it the judge that is
wrong? Would you put this judge into the GEPA metric, into the test report only, or
nowhere, and what would you need first?
""", auto_points=6)
ps.todo(
    stub="""
    # TODO 1: class ReadabilityVerdict(dspy.Signature): ...
    judge_program = None

    def judge_sentence(sentence: str, language: str, axiom) -> bool:
        # TODO 1
        raise NotImplementedError

    def cohens_kappa(a, b) -> float:
        # TODO 2
        raise NotImplementedError

    # TODO 3: b4, b4_stats, b4_cost, judge_trusted
    """,
    solution="""
    class ReadabilityVerdict(dspy.Signature):
        \"\"\"You review sentences for a zoo's keepers. A sentence is acceptable only if
        a native-speaker keeper would sign it off without editing: correct grammar
        (articles, gender, case, number after 'only/alleen/nur'), German nouns
        capitalised, every term in the requested language using the words on the term
        sheet, and no programming identifiers. The sentence must follow the fixed
        controlled pattern; do not penalise the pattern itself, only errors within it.\"\"\"

        sentence: str = dspy.InputField(desc="one sentence from a review sheet")
        language: str = dspy.InputField(desc="en, nl or de")
        terms: str = dspy.InputField(desc="the approved words, with plural, gender/article and case")
        acceptable: bool = dspy.OutputField(desc="true only if a keeper would sign it off unchanged")
        problem: str = dspy.OutputField(desc="the first thing a keeper would correct, or 'none'")

    judge_program = dspy.Predict(ReadabilityVerdict)

    def judge_sentence(sentence: str, language: str, axiom) -> bool:
        return bool(judge_program(sentence=sentence, language=language,
                                  terms=A.term_sheet(axiom, language)).acceptable)

    def cohens_kappa(a, b) -> float:
        a, b = [bool(x) for x in a], [bool(x) for x in b]
        assert len(a) == len(b) and a, "two equal-length, non-empty label lists"
        n = len(a)
        p_o = sum(x == y for x, y in zip(a, b)) / n
        pa, pb = sum(a) / n, sum(b) / n
        p_e = pa * pb + (1 - pa) * (1 - pb)
        if p_e == 1:
            return 1.0 if p_o == 1 else 0.0
        return (p_o - p_e) / (1 - p_e)

    rows = []
    with llm.meter(lm) as b4_cost:
        for p in A.READABILITY_PANEL:
            axiom = A.AXIOMS[p["axiom_id"]]
            rows.append({"id": p["id"], "language": p["language"], "sentence": p["sentence"],
                         "human": p["acceptable"],
                         "judge": judge_sentence(p["sentence"], p["language"], axiom),
                         "lint_ok": not A.lint(p["sentence"], axiom, p["language"])})
    b4 = pd.DataFrame(rows)
    b4_stats = {who: {"accuracy": round(float((b4[col] == b4.human).mean()), 3),
                      "kappa": round(cohens_kappa(b4[col], b4.human), 3)}
                for who, col in (("judge", "judge"), ("lint", "lint_ok"))}
    judge_trusted = (b4_stats["judge"]["kappa"] >= 0.6
                     and b4_stats["judge"]["kappa"] > b4_stats["lint"]["kappa"])
    print(b4_stats, "trusted:", judge_trusted, "cost:", b4_cost)
    b4[b4.judge != b4.human]
    """)
ps.check("B4", """
assert abs(cohens_kappa([1, 1, 0, 0], [1, 0, 0, 0]) - 0.5) < 1e-9
assert abs(cohens_kappa([True, False, True, False], [False, True, False, True]) + 1.0) < 1e-9
assert abs(cohens_kappa([1, 1, 1, 1], [1, 0, 1, 0])) < 1e-9
assert cohens_kappa([1, 0, 1], [1, 0, 1]) == 1.0 and cohens_kappa([1, 1], [1, 1]) == 1.0
assert set(ReadabilityVerdict.input_fields) == {"sentence", "language", "terms"}
assert {"acceptable", "problem"} <= set(ReadabilityVerdict.output_fields)
assert callable(judge_sentence)
assert isinstance(b4, pd.DataFrame) and len(b4) == len(A.READABILITY_PANEL)
assert {"id", "language", "human", "judge", "lint_ok"} <= set(b4.columns)
assert list(b4.human) == [p["acceptable"] for p in A.READABILITY_PANEL], "human column = panel labels"
assert b4.lint_ok.sum() == 17, "lint_ok must be 'A.lint reports nothing'"
for who, col in (("judge", "judge"), ("lint", "lint_ok")):
    assert abs(b4_stats[who]["accuracy"] - (b4[col] == b4.human).mean()) < 1e-3
    assert abs(b4_stats[who]["kappa"] - cohens_kappa(b4[col], b4.human)) < 1e-3
_k = b4_stats["judge"]["kappa"]
assert judge_trusted == (_k >= 0.6 and _k > b4_stats["lint"]["kappa"])
assert {"calls", "usd"} <= set(b4_cost)
""")
ps.written("""
The lint's agreement is fixed and worth knowing by heart: it accepts 17 sentences,
including all five it has no rule for (P18–P22), so accuracy 17/22 ≈ 0.77 and κ ≈ 0.52 —
"moderate", below the 0.6 bar. That number is the case for a judge: a regex that is never
wrong about what it checks still misses half of what keepers reject.

A good live run of this judge (term sheet included) typically lands around κ ≈ 0.7–0.9;
report yours with n = 22. Look at the disagreements rather than the score. Usual patterns:
the judge is **stricter than the keepers** on P12 ("één" with accents, or "leeft in" vs
"verblijft in") or on the construction itself ("Jedes Okapi lebt in mindestens einem
Gehege" reads stiff), and occasionally **lenient** on the German case errors P19/P20,
which are exactly the ones a non-native reviewer also misses. Neither is automatically the
judge's fault: a two-of-three keeper majority is itself noisy, and a disagreement on P12 is
a question for the committee, not a bug.

Twenty-two labels are enough to *reject* a judge, not to certify one: the 95 % interval on
an accuracy of 0.9 at n = 22 is roughly ±0.13, and with only 6–8 sentences per language
you cannot tell whether it is worse at Dutch. So: **not in the GEPA metric** — it would
double the cost of every metric call and the optimiser would learn the judge's
idiosyncrasies (Goodhart on an unvalidated function). **Yes in the test report**, as a
separate column next to the exact score, labelled "judge-estimated acceptability". Before
promoting it further: 50–100 more labels stratified by language and error type, a
per-language κ, a check that it does not favour Claude's own phrasing, and a re-validation
whenever the judge prompt or model changes.
""")

# =========================================================================== #
ps.part("C", "Optimise the verbaliser — and report it honestly", """
Rules for this part: **optimise on `train`, select on `dev`, report on `test`**, and put a
cost and a noise estimate next to every number. The test split holds five axioms that no
language version of has been seen before.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 10, """
1. Build the GEPA metric from your scorer and `A.CNL_RULEBOOK`, and a reflection LM.
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare baseline and tuned on **`test`** with `opt.compare` (store as `c1`).
4. Save the tuned instruction to `config.artifacts_dir() / "ch09_verbaliser_instruction.txt"`.

In writing: read the instruction diff. Which templates and style rules did GEPA write
down, which did it miss — in particular the last three rules of the rulebook — and why?
""", auto_points=5)
ps.todo(
    stub="""
    from oe_course import config
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch09_verbaliser_instruction.txt"
    """,
    solution="""
    from oe_course import config
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(verbalisation_scorer, A.CNL_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(Verbaliser(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(Verbaliser(), tuned, test, verbalisation_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch09_verbaliser_instruction.txt"
    instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")
    """)
ps.check("C1", """
axioms_of = lambda rows: {ex.axiom_id for ex in rows}
assert not (axioms_of(test) & (axioms_of(train) | axioms_of(dev))), "test axioms must be unseen"
assert {r["item"] for r in c1.after["rows"]} == {ex.id for ex in test}, "report on the test split"
assert c1.before["n"] == c1.after["n"] == len(test) == 10
assert instruction_path.is_file()
assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 200
""")
ps.written("""
Expect a large move on this task — from "Anteaters are insectivores." to "Every anteater
is an insectivore." is the whole distance from 0 to 1 — so a good run shows a big test
delta; yours may not, and a small one is a legitimate result to report. In the diff look
for:

* **Templates made explicit.** The `template-for-*` feedback lines carry the exact
  patterns, so the tuned instruction usually states them — often only for the constructs
  and languages train happened to fail on. If train never produced a failing German
  disjointness sentence, "Kein/Keine" may be missing and a test item pays for it.
* **Style rules the scorer reports** (gender, a/an, lexicon labels) appear when some
  train item violated them.
* **The three unreportable rules** (plural after *only*, German case, capitalisation)
  appear only by accident — no metric call ever said "VIOLATED GUIDELINE
  german-case-after-verb", because the scorer cannot see it. GEPA optimises what the
  metric *measures*, not what the style guide *says*. If the diff mentions them, check
  whether it came from the term-sheet wording (the reflection LM reads the inputs too).
* **Over-fitting**: instructions that quote training animals ("for giraffes, use
  Blätter") are memorised and cost tokens on every call.

Put the cost next to the delta: ≈ 60 task calls plus 10–20 reflection calls, a few
dollars. Whether that is cheap depends on Problem D2's exchange rate — at $1.50 per
hand-rewritten sentence it pays for itself within the first review sheet.
""")

ps.problem("C2", "Optimise the exact half alone, and look at what you get", 8, """
1. Implement `fidelity_only(gold, pred) -> ev.ScoreReport`: 1.0 if the round trip is
   faithful, else 0.0 with `violated=[f"template-for-{operator}"]` — no style half.
2. Run GEPA with it (`FIDELITY_BUDGET = 40`, same splits, inside `llm.meter` →
   `fidelity_gepa_cost`); call the result `tuned_fidelity`.
3. On `test`, build `c2` with one row per program (`"gepa"` from C1 and
   `"gepa-fidelity-only"`) and columns `program`, `fidelity`, `full_score`,
   `judge_acceptable` (share of the program's test sentences your B4 judge accepts),
   `eval_usd` and `optimisation_usd`. Generate each program's sentences once and score
   them three ways.

In writing: did optimising the exact half alone cost readability on *your* run? Whatever
the answer, what does this experiment tell you about exact metrics and optimisers?
""", auto_points=3)
ps.todo(
    stub="""
    def fidelity_only(gold, pred) -> ev.ScoreReport:
        # TODO 1
        raise NotImplementedError

    FIDELITY_BUDGET = 40
    # TODO 2: tuned_fidelity, fidelity_gepa_cost
    # TODO 3: c2
    c2 = None
    """,
    solution="""
    def fidelity_only(gold, pred) -> ev.ScoreReport:
        sentence = str(getattr(pred, "sentence", "") or "").strip()
        axiom = A.gold_axiom(gold)
        verdict = A.round_trip(sentence, axiom, gold.language)
        if verdict["faithful"]:
            return ev.ScoreReport(1.0, [f"Faithful: recovers {axiom}."], [])
        return ev.ScoreReport(0.0, [f"Intended {axiom}; recovered {verdict['recovered']}."],
                              [f"template-for-{axiom.operator}"])

    FIDELITY_BUDGET = 40
    with llm.meter(lm, reflect) as fidelity_gepa_cost:
        tuned_fidelity = opt.run_gepa(Verbaliser(), train,
                                      ev.make_gepa_metric(fidelity_only, A.CNL_RULEBOOK),
                                      valset=dev, max_metric_calls=FIDELITY_BUDGET,
                                      reflection_lm=reflect)

    rows = []
    for name, program, opt_cost in [("gepa", tuned, gepa_cost),
                                    ("gepa-fidelity-only", tuned_fidelity, fidelity_gepa_cost)]:
        with llm.meter(lm) as cost:
            preds = [program(**ex.inputs()) for ex in test]
            judged = [judge_sentence(p.sentence, ex.language, A.gold_axiom(ex))
                      for p, ex in zip(preds, test)]
        rows.append({"program": name,
                     "fidelity": st.mean(fidelity_only(ex, p).score for ex, p in zip(test, preds)),
                     "full_score": st.mean(verbalisation_scorer(ex, p).score for ex, p in zip(test, preds)),
                     "judge_acceptable": sum(judged) / len(judged),
                     "eval_usd": cost["usd"], "optimisation_usd": opt_cost["usd"],
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    c2
    """)
ps.check("C2", """
_p = lambda s: dspy.Prediction(sentence=s)
_ex = ALL["giraffe-eats-only-leaves-de"]
r = fidelity_only(_ex, _p("Jeder Giraffe frisst nur Blatt."))           # faithful, unreadable
assert r.score == 1.0 and r.violated == []
r = fidelity_only(_ex, _p("Giraffen fressen Blätter."))
assert r.score == 0.0 and r.violated == ["template-for-only"]
assert fidelity_only(_ex, _p("Jede Giraffe frisst mindestens ein Blatt.")).score == 0.0
assert isinstance(c2, pd.DataFrame) and set(c2["program"]) == {"gepa", "gepa-fidelity-only"}
assert {"fidelity", "full_score", "judge_acceptable", "eval_usd", "optimisation_usd"} <= set(c2.columns)
assert c2[["fidelity", "full_score", "judge_acceptable"]].apply(lambda s: s.between(0, 1)).all().all()
assert {"calls", "usd"} <= set(fidelity_gepa_cost) and FIDELITY_BUDGET <= 200
""")
ps.written("""
Two honest outcomes, and the write-up should say which one you got:

* **The gap shows.** The fidelity-only program matches or beats C1 on `fidelity` but
  scores lower on `full_score` and/or `judge_acceptable` — typically because its
  instruction says "use exactly these patterns" and nothing about gender or
  wrong-language words, and a Dutch sentence with an English noun is perfect by its lights.
* **The gap does not show.** Claude, given a term sheet with genders and plurals, writes
  correct German anyway, and both programs look alike. That does *not* mean the style
  half was unnecessary: the fidelity-only optimiser had **no way to notice** if it had
  been wrong. It was good by luck of the base model, not by measurement — and the next
  model, language or term sheet may not be so kind.

The lesson is the one A1 set up: an exact metric is not wrong, it is *incomplete*, and an
optimiser searches exactly the space the metric leaves unmeasured. Every quantity you care
about must appear somewhere in the objective or in a guard metric reported next to it —
here the full score and the validated judge rate. With n = 10 and one run each, any
difference below ≈ 0.1 is noise (C3).
""")

ps.problem("C3", "Is the difference bigger than the noise?", 6, """
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, `with dspy.context(lm=fresh)`)
run the baseline and the C1 tuned program on `test` three times each; store the mean
scores in `runs = {"baseline": [...], "gepa": [...]}`. Compute each program's mean and
sample standard deviation and set `verdict_c3 = "significant"` if
`|mean_gepa - mean_baseline| > 2 * max(sd_gepa, sd_baseline)`, else `"not significant"`.

In writing: what does this say about C1, and how does a task with an exact grader change
what "noise" means?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs (inside llm.meter(fresh) as c3_cost), then compute verdict_c3
    verdict_c3 = None
    """,
    solution="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c3_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(
                ev.evaluate_dataset(Verbaliser(), test, verbalisation_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, verbalisation_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c3 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c3, c3_cost)
    """)
ps.check("C3", """
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
_m = {k: st.mean(v) for k, v in runs.items()}
_s = {k: st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c3 == _expected
assert {"calls", "usd"} <= set(c3_cost)
""")
ps.written("""
Because the grader is exact, all of the run-to-run spread comes from **sampling** — the
same sentence always gets the same score. So the standard deviation here is a clean
measurement of the verbaliser's own variability, which is exactly the number Part D
needs: if the tuned program's three means are, say, 0.93 ± 0.03, a single draw per item
fails the round trip or the lint now and then, and resampling can fix it for the price of
another call.

If the baseline is near 0.2 and the tuned program near 0.9, the verdict is
"significant" by a wide margin and the C1 claim stands; if your GEPA run barely moved the
mean, three runs will usually say "not significant", and the honest sentence is "GEPA
changed the mean test score by X ± Y over 3 runs of 10 items, at a cost of $Z". Three runs
and ten items remain a crude estimate; a credible report would pair items across runs
(bootstrap over items) and use more axioms per construct.
""")

# =========================================================================== #
ps.part("D", "Knowing when to stop resampling", """
A verbaliser with a free exact check invites best-of-n: draw a sentence, check it, draw
again if it is not good enough. Each draw costs; the question is when to stop.
`A.RevisionMDP(qualities, probabilities, cost, max_attempts, recall)` is that decision:
the state is (attempts spent, quality in hand), the actions are `accept` and `retry`, a
new draft's quality is drawn from `probabilities`. With `recall=True` you keep the best
draft so far (a scorer ranks them); with `recall=False` only the latest.
""")

ps.problem("D1", "Derive the stopping rule", 8, """
1. Implement `expected_gain(q, qualities, probabilities)` = E[max(Q − q, 0)], the
   expected improvement of one more draw over a draft of quality `q` when you keep the
   better of the two.
2. Implement `reservation_policy(M)`: a policy table for every non-terminal state of `M`
   — `retry` at the start, `accept` when no attempts remain, and otherwise `retry` iff
   `expected_gain(q) > M.cost`. Derive on paper why this one-step rule is optimal for
   `recall=True` (hint: can the stopping condition, once met, ever stop holding?).
3. Implement `accept_threshold(M, policy) -> {attempts: lowest quality accepted}`.
   Using the ladder `D1_LADDER` below, build `d1` with columns `recall`, `attempts`,
   `threshold` from the value-iteration policies for `recall=True` and `recall=False`.

In writing: why is the threshold flat with recall and falling without it? Which of the
two describes (i) the DSPy verbaliser with the round trip as scorer, (ii) a keeper who
reviews one draft at a time?
""", auto_points=5)
ps.code("""
# The scorer's quality ladder: unparseable / wrong meaning / faithful with style issues / perfect.
D1_LADDER = dict(qualities=(0.0, 0.25, 0.75, 1.0), probabilities=(0.3, 0.2, 0.3, 0.2),
                 cost=0.02, max_attempts=6)
M = A.RevisionMDP(**D1_LADDER)
V, pi = mdp.value_iteration(M)
print(f"V*(start) = {V[M.initial_state()]:.4f}")
pd.DataFrame(M.thresholds(pi))
""")
ps.todo(
    stub="""
    def expected_gain(q: float, qualities, probabilities) -> float:
        # TODO 1
        raise NotImplementedError

    def reservation_policy(M) -> dict:
        # TODO 2
        raise NotImplementedError

    def accept_threshold(M, policy) -> dict:
        # TODO 3
        raise NotImplementedError

    d1 = None        # TODO 3
    """,
    solution="""
    def expected_gain(q: float, qualities, probabilities) -> float:
        return sum(p * max(x - q, 0.0) for x, p in zip(qualities, probabilities))

    def reservation_policy(M) -> dict:
        policy = {}
        for s in M.states():
            if M.is_terminal(s):
                continue
            if s.quality < 0:
                policy[s] = "retry"
            elif s.attempts >= M.max_attempts:
                policy[s] = "accept"
            else:
                gain = expected_gain(M.qualities[s.quality], M.qualities, M.probabilities)
                policy[s] = "retry" if gain > M.cost else "accept"
        return policy

    def accept_threshold(M, policy) -> dict:
        out = {}
        for attempts in range(1, M.max_attempts + 1):
            accepted = [q for i, q in enumerate(M.qualities)
                        if policy.get(A.DraftState(attempts, i)) == "accept"]
            out[attempts] = min(accepted) if accepted else None
        return out

    rows = []
    for recall in (True, False):
        Mr = A.RevisionMDP(**D1_LADDER, recall=recall)
        _, pr = mdp.value_iteration(Mr)
        for attempts, threshold in accept_threshold(Mr, pr).items():
            rows.append({"recall": recall, "attempts": attempts, "threshold": threshold})
    d1 = pd.DataFrame(rows)
    print({q: round(expected_gain(q, M.qualities, M.probabilities), 3) for q in M.qualities})
    d1.pivot(index="attempts", columns="recall", values="threshold")
    """)
ps.check("D1", """
assert abs(expected_gain(0.7, (0.4, 0.7, 1.0), (0.5, 0.3, 0.2)) - 0.06) < 1e-9
assert expected_gain(1.0, (0.4, 0.7, 1.0), (0.5, 0.3, 0.2)) == 0.0
for cost in np.linspace(0.0, 0.4, 17):
    for ladder in [((0.4, 0.7, 1.0), (0.5, 0.3, 0.2)), (D1_LADDER["qualities"], D1_LADDER["probabilities"])]:
        Mc = A.RevisionMDP(*ladder, cost=float(cost), max_attempts=5)
        _, pc = mdp.value_iteration(Mc)
        rule = reservation_policy(Mc)
        for s, action in pc.items():
            if 0 < s.attempts < Mc.max_attempts:
                g = expected_gain(Mc.qualities[s.quality], *ladder)
                if abs(g - cost) > 1e-6:
                    assert rule[s] == action, (cost, s, rule[s], action)
assert isinstance(d1, pd.DataFrame) and {"recall", "attempts", "threshold"} <= set(d1.columns)
for recall, grp in d1.sort_values("attempts").groupby("recall"):
    Mr = A.RevisionMDP(**D1_LADDER, recall=bool(recall))
    assert dict(zip(grp.attempts, grp.threshold)) == accept_threshold(Mr, mdp.value_iteration(Mr)[1])
    t = list(grp.threshold)
    assert all(a >= b for a, b in zip(t, t[1:])), "thresholds never rise as the budget runs out"
    assert t[-1] == min(D1_LADDER["qualities"]), "the last attempt accepts anything"
_t = d1[d1.recall == True].sort_values("attempts").threshold.tolist()
assert len(set(_t[:-1])) == 1, "with recall the threshold is flat until the cap"
""")
ps.written("""
With recall the problem is **monotone**: holding a draft of quality `q`, one more draw is
worth `g(q) = E[max(Q − q, 0)] − c`. `g` decreases in `q`, and the quality in hand can only
rise, so once `g(q) ≤ c` it stays so for ever — stopping now is at least as good as any
plan that draws again (the one-step look-ahead rule is optimal; the sweep in the check
confirms it state by state). The rule does not mention the number of attempts left, so the
threshold is **flat** at the *reservation quality* `q*` with `E[(Q − q*)+] = c`, until the
cap forces acceptance. Here `g(0.75) = 0.2 × 0.25 = 0.05 > 0.02`, so the policy holds out
for a perfect sentence: retry anything below 1.0 until attempt 6.

Without recall a retry **throws the current draft away**, so the value of continuing is
the value of the remaining budget, `V_{n+1}`, which shrinks as attempts run out; accept
`q` iff `q ≥ V_{n+1}`. The threshold therefore **falls**: 1.0 early, 0.75 from attempt 3,
anything at attempt 6 — the classic secretary-problem shape.

(i) The DSPy verbaliser with a scorer is best-of-n **with recall**: every draft is kept
and ranked by an exact function, so the flat reservation rule applies and "how many
samples?" has a crisp answer: draw until a draft scores ≥ `q*` or the budget ends.
(ii) A keeper reviewing one draft at a time, or any pipeline that overwrites its draft or
cannot score it without a human, is closer to **no recall** — there, early pickiness pays
only if many attempts remain, and it should relax as the deadline nears.
""")

ps.problem("D2", "Calibrate the stopping rule with live samples", 8, """
The ladder in D1 was made up. Measure it.

1. With `fresh = llm.dspy_lm(cache=False)`, draw `K = 4` sentences per **test** item from
   `tuned` inside `llm.meter(fresh)` (cost in `d2_cost`) and score each with your scorer.
   Store `d2_samples` with columns `item`, `draw` (0..K−1), `score`.
2. `ladder` = the sorted distinct scores observed; `probs` = their relative frequencies.
3. `best_of_n` = list of length K: for n = 1..K, the mean over items of the best score
   among the first n draws.
4. Price a draw in quality units: `cost_per_draw = (d2_cost["usd"] / max(d2_cost["calls"], 1))
   / A.REVIEW_COST_USD`. Build `M_live = A.RevisionMDP(ladder, probs, cost_per_draw,
   max_attempts=K)`, solve it, and estimate `expected_draws` (mean number of draws of the
   optimal policy over 2 000 simulated episodes, `random.seed(0)`).

In writing: what does the live ladder look like, what does the rule recommend, and would
you trust `best_of_n` or the MDP more? What is the MDP assuming that your samples may
violate?
""", auto_points=4)
ps.todo(
    stub="""
    K = 4
    fresh = llm.dspy_lm(cache=False)
    # TODO 1-4: d2_samples, d2_cost, ladder, probs, best_of_n, cost_per_draw, M_live, expected_draws
    """,
    solution="""
    K = 4
    fresh = llm.dspy_lm(cache=False)
    rows = []
    with llm.meter(fresh) as d2_cost, dspy.context(lm=fresh):
        for ex in test:
            for draw in range(K):
                pred = tuned(**ex.inputs())
                rows.append({"item": ex.id, "draw": draw, "sentence": pred.sentence,
                             "score": verbalisation_scorer(ex, pred).score})
    d2_samples = pd.DataFrame(rows)

    counts = d2_samples.score.value_counts().sort_index()
    ladder = tuple(float(q) for q in counts.index)
    probs = tuple(float(c) / counts.sum() for c in counts)

    by_item = d2_samples.sort_values("draw").groupby("item").score.apply(list)
    best_of_n = [float(np.mean([max(scores[:n]) for scores in by_item])) for n in range(1, K + 1)]

    cost_per_draw = (d2_cost["usd"] / max(d2_cost["calls"], 1)) / A.REVIEW_COST_USD
    M_live = A.RevisionMDP(ladder, probs, cost=cost_per_draw, max_attempts=K)
    V_live, pi_live = mdp.value_iteration(M_live)
    random.seed(0)
    expected_draws = float(np.mean([len(mdp.run_episode(M_live, mdp.greedy_policy(pi_live))) - 1
                                    for _ in range(2000)]))
    print("ladder", ladder, "probs", [round(p, 3) for p in probs])
    print("best-of-n", [round(b, 3) for b in best_of_n], " cost/draw (quality units)",
          round(cost_per_draw, 4), " expected draws", expected_draws, d2_cost)
    pd.DataFrame(M_live.thresholds(pi_live))
    """)
ps.check("D2", """
assert isinstance(d2_samples, pd.DataFrame) and len(d2_samples) == K * len(test)
assert {"item", "draw", "score"} <= set(d2_samples.columns)
assert set(d2_samples["item"]) == {ex.id for ex in test} and set(d2_samples["draw"]) == set(range(K))
assert list(ladder) == sorted(set(d2_samples["score"]))
assert abs(sum(probs) - 1) < 1e-9 and len(probs) == len(ladder)
for q, p in zip(ladder, probs):
    assert abs(p - (d2_samples.score == q).mean()) < 1e-9
assert len(best_of_n) == K and all(a <= b + 1e-12 for a, b in zip(best_of_n, best_of_n[1:]))
assert abs(best_of_n[0] - d2_samples[d2_samples.draw == 0].score.mean()) < 1e-9
assert {"calls", "usd"} <= set(d2_cost)
assert abs(M_live.cost - (d2_cost["usd"] / max(d2_cost["calls"], 1)) / A.REVIEW_COST_USD) < 1e-12
assert M_live.qualities == tuple(ladder) and M_live.max_attempts == K
assert 1.0 <= expected_draws <= K
""")
ps.written("""
A typical tuned program puts most of its mass on 1.0, some on 0.875 (one style issue) and
a little on 0 or 0.25 — e.g. ladder (0, 0.875, 1.0) with probabilities (0.05, 0.15, 0.8);
yours will differ. A draw costs a few cents, i.e. ≈ 0.01–0.03 quality units at $1.50 per
rewritten sentence, while the expected gain of redrawing a 0.875 sentence is
`0.8 × 0.125 = 0.1`. So the rule says: **retry anything that is not perfect, until the
budget ends** — at API prices, resampling is almost free next to a keeper's time.
`expected_draws` is then ≈ 1/P(perfect) (≈ 1.2–1.5), far below K. The same arithmetic with
a strict latency budget, or a much weaker model, would give a different answer — which is
the point of computing it rather than guessing *n*.

`best_of_n` is the model-free check: if it rises from 0.93 at n = 1 to 0.99 at n = 2 and
stays flat, the second draw earns almost all the gain the MDP predicts. Trust the
empirical curve where it has data and the MDP for decisions it did not sample (other
costs, other K). The MDP assumes draws are **independent and identically distributed
across items**. Both are false: some items (a German *some* with a dative verb) fail
repeatedly while others never fail, so the pooled ladder overstates the value of retrying
easy items and understates it on hard ones. With 40 draws over 10 items the probabilities
are also rough (±0.1). A per-construct ladder, or conditioning on the failure the scorer
reported, is the natural refinement.
""")

ps.problem("D3", "An agent that checks its own drafts", 6, """
Give the job to an agent with the tools `A.build_toolset(ctx)` (`style_guide`,
`lookup_terms`, `check_round_trip`, `lint_sentence`).

1. Write `VERBALISER_PROMPT`: draft, **check the round trip and the lint**, redraft while
   either fails — at most the number of drafts your D2 rule recommends (say how you chose
   it) — and end with a JSON object `{"sentence": "...", "drafts": <int>}`.
2. Write `parse_sentence(text) -> str`: the `sentence` value of the last JSON object in the
   text that has one (code fences and surrounding prose allowed), else `""`.
3. For every **test** item, build a fresh `A.Ch9Context()`, tools and agent, run it, and
   collect `d3` with columns `id`, `language`, `sentence`, `score` (your scorer),
   `round_trip_checks` (number of `check_round_trip` calls), `tool_calls` and
   `usd_estimate` (`llm.chat_usage(run.messages)`).

In writing: compare the agent with the best-of-n program from D2 on score and cost per
sentence. Does its number of round-trip checks follow the stopping rule? What can the agent
check that the D2 loop cannot, and what can neither check?
""", auto_points=3)
ps.todo(
    stub="""
    VERBALISER_PROMPT = "TODO"

    def parse_sentence(text: str) -> str:
        # TODO
        raise NotImplementedError

    d3 = None   # TODO: run the agent on every test item
    """,
    solution="""
    import json

    MAX_DRAFTS = 3      # D2: P(perfect) is high, so 3 drafts leave < 1 % of items unfixed
    VERBALISER_PROMPT = (
        "You verbalise axioms of the Rhine-Meuse Zoo Alliance's husbandry ontology for "
        "keepers' review sheets, in English (en), Dutch (nl) or German (de).\\n\\n"
        "Procedure:\\n"
        "1. Call style_guide(language) and lookup_terms(axiom, language).\\n"
        "2. Draft ONE sentence that follows the style-guide pattern exactly, using the "
        "term sheet's words with the right plural, gender/article and case; capitalise "
        "German nouns.\\n"
        "3. Call check_round_trip and lint_sentence on the draft. If faithful is false or "
        "the lint lists any issue, fix the draft and check again.\\n"
        f"4. Stop at the first draft that passes both checks, or after {MAX_DRAFTS} drafts "
        "(then return the best one).\\n\\n"
        "End your reply with a JSON object and nothing after it:\\n"
        '{"sentence": "<the sentence>", "drafts": <number of drafts checked>}'
    )

    def parse_sentence(text: str) -> str:
        for blob in reversed(re.findall(r"\\{[^{}]*\\}", text or "")):
            try:
                value = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("sentence"), str):
                return value["sentence"].strip()
        return ""

    rows = []
    for ex in test:
        ctx = A.Ch9Context()
        agent, _ = agents.build_agent(ctx, system_prompt=VERBALISER_PROMPT,
                                      tools=A.build_toolset(ctx))
        run = agents.run_agent(agent, ctx, f"Language: {ex.language}\\nAxiom: {ex.axiom}")
        sentence = parse_sentence(run.answer)
        names = ctx.log.names()
        rows.append({"id": ex.id, "language": ex.language, "sentence": sentence,
                     "score": verbalisation_scorer(ex, dspy.Prediction(sentence=sentence)).score,
                     "round_trip_checks": names.count("check_round_trip"),
                     "tool_calls": len(names),
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d3 = pd.DataFrame(rows)
    print(f"mean score {d3.score.mean():.3f} on n={len(d3)}; "
          f"cost ≈ ${d3.usd_estimate.sum():.3f} total, {d3.round_trip_checks.mean():.1f} checks/item")
    d3
    """)
ps.check("D3", """
assert parse_sentence('{"sentence": "Kiara is a lion.", "drafts": 1}') == "Kiara is a lion."
assert parse_sentence('Checked.\\n```json\\n{"sentence": "Jede Giraffe frisst nur Blätter.", "drafts": 2}\\n```') \\
    == "Jede Giraffe frisst nur Blätter."
assert parse_sentence('{"note": 1} then {"sentence": "Elk insect is een dier.", "drafts": 1}') == "Elk insect is een dier."
assert parse_sentence("Every keeper cares for at least one animal.") == ""
assert parse_sentence("{}") == ""
assert isinstance(d3, pd.DataFrame) and len(d3) == len(test)
assert {"id", "language", "sentence", "score", "round_trip_checks", "tool_calls",
        "usd_estimate"} <= set(d3.columns)
assert set(d3["id"]) == {ex.id for ex in test}
assert d3["score"].between(0, 1).all() and (d3["round_trip_checks"] <= d3["tool_calls"]).all()
for _, row in d3.iterrows():
    assert abs(row["score"] - verbalisation_scorer(ALL[row["id"]], dspy.Prediction(sentence=row["sentence"])).score) < 1e-9
""")
ps.written("""
Expect the agent to match or beat best-of-n on the scorer (it sees the lint *messages*, so
its second draft is a targeted repair rather than a fresh roll of the dice) and to cost
several times more per sentence: 4–8 tool calls, each turn re-sending the prompt and the
tool schemas — typically $0.05–0.15 per item versus ≈ $0.03–0.05 for 1–2 DSPy draws.
Report your n = 10 numbers.

On the stopping rule: a well-behaved run shows `round_trip_checks` = 1 on most items and 2
on the few where the first draft failed — the reservation rule ("stop at the first draft
that passes") in action. More checks than drafts that failed means the agent re-checks
passing sentences, i.e. pays for information it already has; a 0 means it answered
without checking, which the prompt must forbid, because an unchecked answer throws away the
one guarantee this task offers for free.

What the agent can do that the D2 loop cannot: **repair** using the check's diagnosis
(which term failed, which gender is expected) instead of resampling blindly. What neither
can check: the three rules outside the lint (plural after *only*, German case,
capitalisation). A draft that passes both tools can still be rejected by a keeper; the
honest pipeline is agent (or best-of-n) for fidelity and lint, the validated judge of B4 as
a flag, and a keeper for anything flagged — with the stopping rule deciding how many draws
to buy before a human is asked.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
