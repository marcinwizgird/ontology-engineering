"""Build the Chapter 3 problem set: 05_assignment.ipynb + 05_solutions.ipynb.

Run from anywhere:  python chapters/ch03_description_logics/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 3 — Description Logics",
    title="Reviewing rail-ontology change requests with a reasoner and Claude",
    coverage=("Keet §3.1 (ALC, the tableau), §3.2 (the DL naming scheme and what each "
              "letter costs), §3.3 (reasoning services by reduction to satisfiability); "
              "course notebooks 01–04 of this chapter. Tools: DSPy + GEPA, skills and the "
              "self-improvement loop, LangChain agents, value iteration on a stochastic MDP, "
              "and the Chapter 3 tableau reasoner."),
    scenario="""
    **Meridian Rail**, a (fictional) railway infrastructure manager, keeps its asset
    information in a modular OWL ontology. Discipline teams — track, signalling,
    structures, power, stations — submit new modules as pull requests to the
    **Ontology Change Board**, which applies two gates before a module is merged:

    * **Expressivity.** The nightly classification job runs a lightweight reasoner.
      A module that needs transitive roles, a role hierarchy, inverse roles or number
      restrictions must be routed to the heavyweight reasoner job instead, so every
      request must state the **description logic the module needs** — ALC, S, ALCHIQ, …
    * **The reviewer's question.** Each request carries one question from the
      discipline lead — *"is every level-crossing barrier a safety-critical asset?"* —
      which is a **subsumption** query against the module. The board wants a verified
      answer, not an opinion.

    The board has asked you, the ontology engineer, to automate the review:

    1. **Understand the tools you already have.** A cheap *told-subsumption* heuristic
       and the Chapter 3 tableau. The tableau is a **free, always-right oracle** on
       this corpus — which makes this the one chapter where a deployed system can
       label its own failures with no human in the loop. Find out exactly where
       "always right" stops.
    2. **Build the grader and a Claude reviewer**, measure it on a development split.
    3. **Optimise it honestly** with GEPA (train / dev / held-out test, cost, noise),
       then let it **improve itself on unlabelled production traffic** that the
       oracle labels.
    4. **Ship a review agent** that calls the reasoner instead of guessing, and
       **price the reasoner**: CI minutes are budgeted, so decide — per request — when
       the expensive, sound check is worth it over the cheap heuristic.

    The corpus (24 labelled modules, split 8/8/8 by item — one per phenomenon per
    split, four "subsumed" and four "not subsumed" in every split — plus 6 unlabelled
    field requests), the review guidelines, the agent's tools and the budget MDP are
    provided in `ch03_agentic.py`.
    """,
    effort="10–12 hours",
    api_budget="≈ $6–15 estimated on `claude-opus-5` for a full run (≈ 270 DSPy calls at "
               "roughly $0.02–0.05 each, plus 8 agent episodes at ≈ $0.10–0.25 each; GEPA and "
               "the self-improvement rounds are the largest lines). Nothing in this estimate "
               "has been measured — your cost lines are. Re-running unchanged cells is free: "
               "DSPy caches identical requests.",
)

ps.setup("""
import re, statistics as st
import dspy
import numpy as np
import pandas as pd
import ch03_toolkit as dl
import ch03_agentic as AG
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents
from oe_course.skills import Skill
from oe_course.selfimprove import SelfImprovingSkill

A = dl.Atomic
train, dev, test = AG.build_dataset("train"), AG.build_dataset("dev"), AG.build_dataset("test")
CERTIFIED = AG.validate_gold()          # every label re-derived by the engine (< 1 s)
print(f"train {len(train)} / dev {len(dev)} / test {len(test)} / field {len(AG.FIELD_CASES)}")
""")

ps.md("""
### The corpus

Every row is one change request. `kb` is what the reviewer (human or Claude) sees — the
module's axioms and role facts, rendered *without* naming the logic — and `query` is the
discipline lead's question. The gold labels were written by hand and then re-derived by
`AG.validate_gold()`, which also tells you **how** each verdict is certified.
""")
ps.code("""
overview = pd.DataFrame([{"id": ex.id, "split": ex.split, "phenomenon": ex.phenomenon,
                          "gold_dl": ex.gold_dl, "subsumed": ex.gold_subsumption,
                          "certified by": CERTIFIED[ex.id]} for ex in train + dev + test])
print(overview.groupby("split").subsumed.agg(["count", "sum"]).rename(columns={"sum": "n_subsumed"}))
overview
""")
ps.code("""
ex = dev[0]
print(ex.kb, "\\n")
print(ex.query)
""")

# =========================================================================== #
ps.part("A", "The cheap heuristic, the free oracle, and where it stops being right", """
Before anything touches a model, understand the two answers you can already compute for
free: a structural heuristic, and the tableau.
""")

ps.problem("A1", "A told-subsumption heuristic, and a dataset that can punish it", 10, """
Reviewers' first instinct is to *read the hierarchy*: follow the asserted superclasses
upwards and see whether the queried class turns up. Implement that as
`told_subsumes(tbox, sub, sup) -> bool`:

* `sub` is told-subsumed by itself;
* for an axiom whose **left side is atomic** `X`, every **atomic conjunct** of the right
  side (flatten nested `dl.And`) is a told superclass of `X`; anything else on the right
  (`exists`, `forall`, `or`, `not`, number restrictions) is ignored;
* an **equivalence** `X == Y` with *both* sides atomic works in both directions;
* take the transitive closure.

Then build `a1`, one row per labelled item (train + dev + test), with columns `id`,
`split`, `phenomenon`, `gold`, `told` (your heuristic's verdict), `heuristic_correct` and
`risk_class` (`AG.risk_class(tbox)`), and `a1_acc`: indexed by split, with columns
`heuristic` (your heuristic's accuracy) and `always_subsumed` (the accuracy of the trivial
strategy *"always answer subsumed"*).

In writing: (i) the heuristic can only err in one direction — which, and why? (ii) The
old version of this corpus had almost only "subsumed" questions. What would *"always
answer subsumed"* have scored there, and what would that have meant for an optimiser whose
feedback includes the guideline `use-the-reasoner`?
""", auto_points=5)
ps.todo(
    stub="""
    def told_subsumes(tbox: dl.TBox, sub: str, sup: str) -> bool:
        # TODO
        raise NotImplementedError

    a1 = None        # TODO: one row per labelled item
    a1_acc = None    # TODO: per split: heuristic accuracy, always-subsumed accuracy
    """,
    solution="""
    def _atomic_conjuncts(c) -> set[str]:
        if isinstance(c, dl.Atomic):
            return {c.name}
        if isinstance(c, dl.And):
            return _atomic_conjuncts(c.left) | _atomic_conjuncts(c.right)
        return set()

    def told_subsumes(tbox: dl.TBox, sub: str, sup: str) -> bool:
        edges: dict[str, set[str]] = {}
        for ax in tbox.axioms:
            if isinstance(ax.left, dl.Atomic):
                edges.setdefault(ax.left.name, set()).update(_atomic_conjuncts(ax.right))
            if ax.equivalence and isinstance(ax.right, dl.Atomic) and isinstance(ax.left, dl.Atomic):
                edges.setdefault(ax.right.name, set()).add(ax.left.name)
        seen, stack = {sub}, [sub]
        while stack:
            for nxt in edges.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return sup in seen

    rows = []
    for ex in train + dev + test:
        tbox = AG.case(ex.id).tbox()
        told = told_subsumes(tbox, ex.sub, ex.sup)
        rows.append({"id": ex.id, "split": ex.split, "phenomenon": ex.phenomenon,
                     "gold": ex.gold_subsumption, "told": told,
                     "heuristic_correct": told == ex.gold_subsumption,
                     "risk_class": AG.risk_class(tbox)})
    a1 = pd.DataFrame(rows)
    a1_acc = (a1.assign(heuristic=a1.heuristic_correct, always_subsumed=a1.gold)
                .groupby("split")[["heuristic", "always_subsumed"]].mean())
    print(a1_acc)
    a1
    """)
ps.check("A1", """
T = dl.TBox()
T.add(A("X"), dl.And(A("Y"), dl.And(A("Z"), dl.Exists("r", A("W")))))
T.add(A("Z"), A("P"))
T.add(A("P"), A("Q"), equivalence=True)
T.add(A("K"), dl.And(A("X"), A("Y")), equivalence=True)
assert told_subsumes(T, "X", "X") and told_subsumes(T, "X", "Z") and told_subsumes(T, "X", "Q")
assert told_subsumes(T, "Q", "P"), "an atomic equivalence works both ways"
assert not told_subsumes(T, "X", "W") and not told_subsumes(T, "Y", "X")
assert not told_subsumes(T, "X", "K"), "a complex definition is not a told superclass"
for c in AG.CASES + AG.FIELD_CASES:          # a told subsumption is always a real one
    t = c.tbox()
    if told_subsumes(t, c.sub, c.sup):
        assert dl.subsumes(A(c.sub), A(c.sup), t), f"{c.id}: heuristic is unsound"
assert isinstance(a1, pd.DataFrame) and len(a1) == 24
assert {"id", "split", "phenomenon", "gold", "told", "heuristic_correct", "risk_class"} <= set(a1.columns)
assert (a1.heuristic_correct == (a1.told == a1.gold)).all()
assert set(a1_acc.index) == {"train", "dev", "test"}
assert np.allclose(a1_acc["always_subsumed"], 0.5)
assert np.allclose(a1_acc["heuristic"], a1.groupby("split").heuristic_correct.mean()[a1_acc.index])
""")
ps.written("""
**(i) One-sided errors.** Every told superclass is a genuine consequence (an asserted
`X ⊑ … ⊓ Y ⊓ …` entails `X ⊑ Y`, and entailment is transitive), so when the heuristic
says *subsumed* it is right — the check above confirms it on all 30 modules. It fails only
by saying *not subsumed* when the subsumption holds for a reason the hierarchy does not
show: through the **right-hand side of a definition** (`barrier-safety-critical`,
`viaduct-critical`, the inverse-role definitions) or **vacuously**, because the subject
class is unsatisfiable (`automated-manual-crossing`). It is sound but incomplete — and
its errors sit exactly on the inferences that make a reasoner worth having.

On this corpus it scores 5/8 on every split (it gets all four negatives and the told
chain, and misses the definition, inverse-definition and unsatisfiable-subject items);
"always subsumed" scores 4/8.

**(ii) Why balance matters.** On an all-"subsumed" corpus, *always subsumed* scores
100 % on the verdict. The scorer then never reports `use-the-reasoner`, so the feedback
GEPA reads never mentions it and the optimiser has no reason to write it into the
instruction — the tuned reviewer would say "true" to everything and fail silently on the
first negative request in production. A dataset can only teach a rule that some item
punishes; that is why every split here has four negatives, spread over four phenomena.
""")

ps.problem("A2", "Where the free oracle stops being right", 10, """
The tableau decides **ALC**. It *names* S, H, I, N and Q but reasons as if transitivity,
sub-roles, inverses and number restrictions were not there — so it reasons over a
*weaker* theory than the module states.

(a) Build `blind_spot = (tbox, sub, sup)`: a small rail module with a **role hierarchy or
a transitive role** in which `sub ⊑ sup` **is** entailed but `dl.subsumes` says it is
not. Then build `compiled`: a copy of the module plus one or more ALC axioms that the role
box licenses (see `AG.rbox_licensed` for the three accepted schemata), after which the
tableau finds the subsumption.

(b) `AG.validate_gold()` certifies "not subsumed" on the non-ALC modules with
countermodels (`AG.CERTIFICATES`). Write your own certificate `my_certificate` — an
`AG.Interpretation` — for a **pure-ALC** "not subsumed" item of your choice
(`cert_case`, one not in `AG.CERTIFICATES`), and confirm it with `AG.is_countermodel`.

(c) In writing: in which direction is the tableau's verdict trustworthy on *any* module
of this corpus, and why? What does (a) mean for a system that labels its own training
data with this oracle? What would you run in production instead?
""", auto_points=4)
ps.todo(
    stub="""
    blind_spot = None       # TODO (a): (tbox, sub, sup)
    compiled = None         # TODO (a): the module plus RBox-licensed ALC axioms

    cert_case = "..."       # TODO (b)
    my_certificate = None   # TODO (b): AG.Interpretation(domain=..., concepts=..., roles=...)
    """,
    solution="""
    blind = dl.TBox()
    blind.add(A("MaintenanceDepot"), dl.Exists("maintains", A("Signal")))
    blind.add(A("SignalOwner"), dl.Exists("isResponsibleFor", A("Signal")), equivalence=True)
    blind.role_hierarchy.append(("maintains", "isResponsibleFor"))
    blind_spot = (blind, "MaintenanceDepot", "SignalOwner")

    compiled = dl.TBox(list(blind.axioms), set(blind.transitive_roles), list(blind.role_hierarchy))
    compiled.axioms.append(dl.Axiom(dl.Exists("maintains", A("Signal")),
                                    dl.Exists("isResponsibleFor", A("Signal"))))
    print("tableau on the module      :", dl.subsumes(A("MaintenanceDepot"), A("SignalOwner"), blind))
    print("tableau on the compiled one:", dl.subsumes(A("MaintenanceDepot"), A("SignalOwner"), compiled))

    # drainage-culvert: a drainage asset that drains nothing satisfies 'drains only
    # watercourses' vacuously, and is not a culvert (which must drain some watercourse).
    cert_case = "drainage-culvert"
    my_certificate = AG.Interpretation(domain={"d"},
                                       concepts={"DrainageAsset": {"d"}, "Asset": {"d"}},
                                       roles={})
    c = AG.case(cert_case)
    print("countermodel?", AG.is_countermodel(c.tbox(), c.sub, c.sup, my_certificate))
    """)
ps.check("A2", """
t, sub, sup = blind_spot
assert t.role_hierarchy or t.transitive_roles, "the blind spot needs an RBox feature"
assert not dl.subsumes(A(sub), A(sup), t), "the tableau must miss it"
assert dl.subsumes(A(sub), A(sup), compiled), "the compiled module must expose it"
extra = [ax for ax in compiled.axioms if ax not in t.axioms]
assert extra and all(ax in compiled.axioms for ax in t.axioms)
assert all(AG.rbox_licensed(ax, t) for ax in extra), "only RBox-licensed axioms may be added"
c = AG.case(cert_case)
assert c.gold_subsumed is False and cert_case not in AG.CERTIFICATES
assert AG.is_countermodel(c.tbox(), c.sub, c.sup, my_certificate)
""")
ps.written("""
**Which direction is safe.** Treating transitivity, sub-roles, inverses and number
restrictions as absent (or opaque) only *removes* constraints, so every model of the real
module is also a model of what the tableau reasons over. If `C ⊓ ¬D` has no model even
in the weaker theory, it has none in the real one: a **"subsumed"** verdict is sound on
every module. A **"not subsumed"** verdict is only as good as the tableau's completeness —
guaranteed for pure ALC, not otherwise. Part (a) is the counterexample: the tableau builds
a `maintains`-successor that is a `Signal` but never adds the `isResponsibleFor` edge the
sub-role axiom demands, so it reports a "model" that is not a model. That is why
`validate_gold` asks for a countermodel on exactly the non-ALC negatives, and why a
countermodel is the right certificate: it is a finite object anyone can check.

**Consequence for self-labelling.** An oracle that is right on this corpus is not an
oracle that is right. A self-improving system that trusts every tableau "no" on SH/SHIQ
modules would *train itself into the reasoner's blind spot*: the optimiser would learn to
answer "not subsumed" on sub-role questions where the correct answer is "subsumed", and
the promotion gate — scored by the same oracle — would reward it. The labeller must
therefore say when it is **certified** (Problem C3) and discard the rest.

**In production** the board would run a complete reasoner for the logic in question —
HermiT, Pellet or Konclude for SHOIQ/SROIQ, ELK for the EL modules — and keep the
countermodel/justification as the artefact of each verdict. The tableau in this chapter is
a teaching reasoner; the naming skill of §3.2 is what tells you when it is no longer
enough.
""")

# =========================================================================== #
ps.part("B", "Build the grader and the Claude reviewer", """
The guidelines the scorer can report — ids plus the sentence GEPA's reflection reads —
are in `AG.DL_RULEBOOK`:
""")
ps.code("""
for rule in AG.DL_RULEBOOK:
    print(f"{rule.id:38s} {rule.description[:80]}")
""")

ps.problem("B1", "A diagnostic review scorer", 14, """
Implement `dl_scorer(gold, pred) -> ev.ScoreReport`. `gold` is a dataset row
(`gold_dl`, `gold_subsumption`, `constructors`, `sub_satisfiable`, `sub`, `sup`); `pred`
has string fields `dl` and `subsumption`. The score is **0.5 for the name + 0.5 for the
verdict**.

**Name.** Normalise (strip, upper-case, remove spaces, drop a trailing `(D)`) and parse
against the standard order `^(ALC|S)(H?)(O?)(I?)([QNF]?)$`. Full marks only when the
parsed letters equal gold's. When wrong, report every rule that applies:

| situation | violated |
|---|---|
| does not parse (prose, wrong letter order, …) | `name-the-logic-exactly` |
| base differs (ALC vs S) | `s-for-transitive` |
| H / I needed but missing | `h-for-role-hierarchy` / `i-for-inverse` |
| gold has Q or N and the answer's number letter differs | `q-for-qualified-number` |
| a letter (H, O, I, or a number letter) that gold does not have | `no-unused-letters` |
| wrong, but none of the above applies | `name-the-logic-exactly` |

**Verdict.** Accept `true/yes/subsumed/entailed` and `false/no/not subsumed/not entailed`
(case-insensitive, surrounding punctuation ignored). Anything else earns 0 and
`answer-true-or-false`. A wrong verdict earns 0 and `use-the-reasoner`, plus
`unsatisfiable-subsumed-by-everything` when gold is *subsumed* because the subject class
is unsatisfiable.

The notes must say what was wrong **and why** — for a wrong name, the correct name and
the constructors the module uses. That text is what GEPA reads.
""", auto_points=11)
ps.todo(
    stub="""
    DL_PATTERN = re.compile(r"^(ALC|S)(H?)(O?)(I?)([QNF]?)$")

    def parse_dl(text) -> dict | None:
        # TODO: normalise, then match DL_PATTERN; return the letters, or None
        raise NotImplementedError

    def dl_scorer(gold, pred) -> ev.ScoreReport:
        # TODO
        raise NotImplementedError
    """,
    solution=r"""
    DL_PATTERN = re.compile(r"^(ALC|S)(H?)(O?)(I?)([QNF]?)$")
    TRUE_WORDS = {"true", "yes", "subsumed", "entailed"}
    FALSE_WORDS = {"false", "no", "not subsumed", "not entailed"}

    def parse_dl(text) -> dict | None:
        t = str(text or "").strip().upper().replace(" ", "")
        t = re.sub(r"\(D\)$", "", t)
        m = DL_PATTERN.match(t)
        if not m:
            return None
        return {"base": m.group(1), "H": bool(m.group(2)), "O": bool(m.group(3)),
                "I": bool(m.group(4)), "num": m.group(5)}

    def parse_verdict(value) -> bool | None:
        t = str(value if value is not None else "").strip().lower().strip(" .!`'\"")
        if t in TRUE_WORDS:
            return True
        if t in FALSE_WORDS:
            return False
        return None

    def name_rules(expected: str, answered: str) -> list[str]:
        e, g = parse_dl(expected), parse_dl(answered)
        if g is None:
            return ["name-the-logic-exactly"]
        out = []
        if e["base"] != g["base"]:
            out.append("s-for-transitive")
        if e["H"] and not g["H"]:
            out.append("h-for-role-hierarchy")
        if e["I"] and not g["I"]:
            out.append("i-for-inverse")
        if e["num"] in ("Q", "N") and g["num"] != e["num"]:
            out.append("q-for-qualified-number")
        if ((g["H"] and not e["H"]) or (g["O"] and not e["O"]) or (g["I"] and not e["I"])
                or (g["num"] and not e["num"])):
            out.append("no-unused-letters")
        return out or ["name-the-logic-exactly"]

    def dl_scorer(gold, pred) -> ev.ScoreReport:
        answered_dl = str(getattr(pred, "dl", "") or "").strip()
        notes, violated = [], []

        parsed = parse_dl(answered_dl)
        name_ok = parsed is not None and parsed == parse_dl(gold.gold_dl)
        if not name_ok:
            notes.append(f"DL name wrong: answered {answered_dl!r}; the module uses "
                         f"{', '.join(gold.constructors)}, so it needs {gold.gold_dl}.")
            violated += name_rules(gold.gold_dl, answered_dl)

        verdict = parse_verdict(getattr(pred, "subsumption", None))
        truth = bool(gold.gold_subsumption)
        verdict_ok = verdict is not None and verdict == truth
        if verdict is None:
            notes.append(f"Unreadable verdict {getattr(pred, 'subsumption', None)!r}: "
                         f"answer exactly true or false.")
            violated.append("answer-true-or-false")
        elif not verdict_ok:
            reason = (f"{gold.sub} and not {gold.sup} is "
                      f"{'unsatisfiable' if truth else 'satisfiable'} under the module")
            notes.append(f"Verdict wrong: answered {verdict}, the reasoner says {truth} "
                         f"({reason}).")
            violated.append("use-the-reasoner")
            if truth and not gold.sub_satisfiable:
                notes.append(f"{gold.sub} is unsatisfiable, so it is subsumed by every class.")
                violated.append("unsatisfiable-subsumed-by-everything")

        notes.append(f"name_ok={int(name_ok)} verdict_ok={int(verdict_ok)}")
        return ev.ScoreReport(0.5 * name_ok + 0.5 * verdict_ok, notes,
                              list(dict.fromkeys(violated)))
    """)
ps.check("B1", """
by_id = {ex.id: ex for ex in train + dev + test}
P = lambda d, s: dspy.Prediction(dl=d, subsumption=s)
cases = [
    ("interlocking-control-centre", "SHIQ", "false", 1.0, []),
    ("interlocking-control-centre", " shiq(D) ", "False.", 1.0, []),
    ("interlocking-control-centre", "ALCHIQ", "no", 0.5, ["s-for-transitive"]),
    ("interlocking-control-centre", "SHIN", "false", 0.5, ["q-for-qualified-number"]),
    ("interlocking-control-centre", "SIQ", "false", 0.5, ["h-for-role-hierarchy"]),
    ("interlocking-control-centre", "SHOIQ", "false", 0.5, ["no-unused-letters"]),
    ("interlocking-control-centre", "The logic is SHIQ", "false", 0.5, ["name-the-logic-exactly"]),
    ("interlocking-control-centre", "SHIQ", "true", 0.5, ["use-the-reasoner"]),
    ("interlocking-control-centre", "SHQ", "probably", 0.0, ["i-for-inverse", "answer-true-or-false"]),
    ("bay-platform-low-use", "ALCQ", "false", 0.5, ["q-for-qualified-number"]),
    ("bay-platform-low-use", "ALC", "false", 0.5, ["q-for-qualified-number"]),
    ("barrier-safety-critical", "ALCN", "true", 0.5, ["no-unused-letters"]),
    ("barrier-safety-critical", "S", "yes", 0.5, ["s-for-transitive"]),
    ("automated-manual-crossing", "ALC", "false", 0.5,
     ["use-the-reasoner", "unsatisfiable-subsumed-by-everything"]),
    ("drainage-culvert", "ALC", "true", 0.5, ["use-the-reasoner"]),
]
for item, d, s, score, violated in cases:
    r = dl_scorer(by_id[item], P(d, s))
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (item, d, s, r.score, r.violated)
    assert all(v in AG.DL_RULEBOOK for v in r.violated)
wrong = dl_scorer(by_id["interlocking-control-centre"], P("ALCHIQ", "false"))
assert any("SHIQ" in n and "transitive" in n for n in wrong.notes), "say the right name and why"
""")

ps.problem("B2", "The reviewer as a DSPy program", 7, """
Write a signature `ModuleReview` with inputs `kb` and `query` and outputs
`justification`, `dl` and `subsumption` (all strings), and a factory
`DLReviewer(instruction)` returning a `dspy.Module` with a single `dspy.Predict` whose
instruction is `instruction`. The field descriptions are part of the prompt — write them
for a colleague who has never seen this notation (manual marks), and say in a sentence why
you put the output fields in the order you did. Configure Claude and run it once on
`train[0]`.
""", auto_points=4)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = ("You review ontology modules for a railway. Say which description "
                            "logic the module needs and answer the subsumption question.")

    # TODO: class ModuleReview(dspy.Signature): ...
    # TODO: def DLReviewer(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: DLReviewer()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = ("You review ontology modules for a railway. Say which description "
                            "logic the module needs and answer the subsumption question.")

    class ModuleReview(dspy.Signature):
        \"\"\"Name the description logic an ontology module needs and answer a subsumption question about it.\"\"\"

        kb: str = dspy.InputField(
            desc="the module, one axiom per line: 'C <= D' is subclass, 'C == D' is "
                 "equivalence; 'exists r.C', 'forall r.C', '>=n r.C', '<=n r.C' (a '.Top' "
                 "filler means unqualified); 'r-' is the inverse of role r; transitive roles and the role hierarchy follow")
        query: str = dspy.InputField(desc="the reviewer's question and its formal form")
        justification: str = dspy.OutputField(
            desc="two or three sentences: which constructors fix the logic's name, and "
                 "which axioms decide the subsumption")
        dl: str = dspy.OutputField(desc="the DL name only, standard letter order, e.g. ALC, S, ALCHIQ, SHIN")
        subsumption: str = dspy.OutputField(desc="exactly 'true' or 'false'")

    def DLReviewer(instruction: str = BASELINE_INSTRUCTION):
        class _Reviewer(dspy.Module):
            def __init__(self):
                super().__init__()
                self.review = dspy.Predict(ModuleReview.with_instructions(instruction))

            def forward(self, kb: str, query: str):
                return self.review(kb=kb, query=query)

        return _Reviewer()

    lm = llm.configure_dspy()
    smoke = DLReviewer()(**train[0].inputs())
    print(train[0].id, "->", smoke.dl, "/", smoke.subsumption)
    print(smoke.justification)
    """)
ps.check("B2", """
assert set(ModuleReview.input_fields) == {"kb", "query"}
assert {"dl", "subsumption", "justification"} <= set(ModuleReview.output_fields)
program = DLReviewer("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.dl, str) and isinstance(smoke.subsumption, str)
""")
ps.written("""
The justification comes **first** so the model writes down the constructors and the
deciding axioms *before* it commits to a name and a verdict — a cheap, explicit
chain-of-thought that also gives the error analysis something to read. The descriptions
spell out the notation (`<=`, `==`, `r-`, `>=n r.C`) because the naming task depends on
noticing exactly those tokens, and fix the output contract (bare name, bare `true/false`)
that the scorer parses.
""")

ps.problem("B3", "Baseline on the development split, with its cost", 8, """
Evaluate the baseline reviewer on `dev` with `ev.evaluate_dataset`, inside
`llm.meter(lm)`. Store the result in `baseline_dev` and the cost in `baseline_dev_cost`,
and build `b3`: the per-item rows joined with each item's `phenomenon` and `gold_dl`.

Then write a short **error analysis** separating the two halves of the task: which
*naming* rules were broken and on which phenomena, and which *verdicts* were wrong — and
for those, was it a definition, an inverse, or the unsatisfiable subject? Which of the two
halves could a tool fix completely, and which needs the model to reason?
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: baseline_dev = ..., baseline_dev_cost = ..., b3 = ...
    """,
    solution="""
    with llm.meter(lm) as baseline_dev_cost:
        baseline_dev = ev.evaluate_dataset(DLReviewer(), dev, dl_scorer)
    print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
    print("cost:", baseline_dev_cost)
    meta = pd.DataFrame([{"item": ex.id, "phenomenon": ex.phenomenon, "gold_dl": ex.gold_dl}
                         for ex in dev])
    b3 = pd.DataFrame(baseline_dev["rows"]).merge(meta, on="item")
    b3
    """)
ps.check("B3", """
assert baseline_dev["n"] == len(dev) == 8
assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
assert 0.0 <= baseline_dev["mean_score"] <= 1.0
assert {"calls", "usd"} <= set(baseline_dev_cost)
assert isinstance(b3, pd.DataFrame) and len(b3) == 8 and {"phenomenon", "score"} <= set(b3.columns)
""")
ps.written("""
The analysis to hand in is of *your* run; a typical baseline looks like this.

* **Naming.** A strong model usually gets ALC and S, and loses points on the letters that
  live *outside* the axiom text or in one token: `H` from the role-hierarchy line
  (`substation-feeder` answered `S`), `I` from a single `r-` (`switch-monitored` answered
  `S` or `ALCI` instead of `SI`), and the **N/Q** distinction (`bay-platform-low-use` is
  `<=2 servedBy.Top`, an unqualified restriction — N, not Q). It also over-claims: "SHIN" for a module with
  no transitive role, or appending `(D)`. These are *rule* errors — `dl_expressivity`
  would fix all of them, which is the argument for giving the agent that tool (Part D).
* **Verdicts.** The negatives are rarely wrong. The failures cluster on the inferences
  the told-hierarchy heuristic also misses: subsumption *through the right-hand side of a
  definition*, and the **unsatisfiable subject** (`permissive-stop-signal`), where the
  natural-language question ("is a permissive stop signal a level crossing?") sounds
  absurd and the model answers `false`, while the logic says `true`, vacuously. These
  need reasoning; a model that "reasons by eye" makes exactly the errors of A1.

Cost: 8 calls — a few tens of cents at most; this is the unit price for every later
comparison.
""")

# =========================================================================== #
ps.part("C", "Optimise honestly — then let the oracle label the training data", """
GEPA rewrites the instruction by reflecting on the scorer's feedback. The rules: **optimise
on `train`, select on `dev`, report on `test`**, and put a cost and a noise estimate next
to every number. Then use the chapter's distinctive asset — an oracle that labels for free
— to improve the reviewer from unlabelled traffic, behind a promotion gate.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 12, """
1. Build the GEPA feedback metric from your scorer and `AG.DL_RULEBOOK`, and a separate
   reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
3. Compare baseline and tuned on **`test`** with `opt.compare` (store as `c1`) and print
   `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch03_module_reviewer_instruction.txt"`.

In writing: read the instruction diff. Which guidelines did GEPA put into words? Did it
learn to *follow definitions* and to treat an unsatisfiable subject as subsumed — or only
the letter rules? Did it add anything that only fits the eight training modules?
""", auto_points=6)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch03_module_reviewer_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(dl_scorer, AG.DL_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(DLReviewer(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(DLReviewer(), tuned, test, dl_scorer)
    print(c1.report())
    print("\\nGEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch03_module_reviewer_instruction.txt"
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
Your wording will differ; look for three things.

* **Letter rules.** These are the easiest for GEPA: the feedback names the rule, the
  correct name and the constructors, so a good run writes "S if any role is transitive",
  "H for a sub-role declaration", "I for `r-`", "Q if the restriction has a filler, N if
  not", and "standard order, no (D)". Only rules some *training* item violated appear:
  train has an ALCH, an ALCI, an ALCQ and a SHIQ module, but no N — so if the tuned prompt
  never mentions N, the dev/test N item (`bay-platform-low-use` is in dev) shows it.
* **Reasoning rules.** `use-the-reasoner` and `unsatisfiable-subsumed-by-everything`
  appear only if a training verdict failed. A DSPy program has no reasoner tool, so the
  best GEPA can do is write the *procedure* down ("expand defined classes on the right,
  check whether the subject is contradictory first") — an instruction, not a guarantee.
  Whether it transfers is exactly what the test score measures.
* **Over-fitting.** Sentences naming training classes ("interlockings are never control
  centres") are memorised answers; they cost tokens on every call and are wrong on the
  next module.

A test delta of ±1 item (±0.06) is inside the noise (C2); report it as such.
""")

ps.problem("C2", "Is the difference bigger than the noise?", 7, """
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, `with dspy.context(lm=fresh):`),
run the baseline and the tuned reviewers on `test` three times each, inside
`llm.meter(fresh)`; store mean scores in `runs = {"baseline": [...], "gepa": [...]}`.
Set `verdict_c2` to `"significant"` if `|mean_gepa − mean_baseline| > 2·max(sd_gepa,
sd_baseline)`, else `"not significant"`.

In writing: what does this say about the C1 number, and what would a credible evaluation
of the reviewer need?
""", auto_points=4)
ps.todo(
    stub="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    # TODO: fill runs (inside llm.meter(fresh) -> c2_cost), then compute verdict_c2
    verdict_c2 = None
    """,
    solution="""
    fresh = llm.dspy_lm(cache=False)
    runs = {"baseline": [], "gepa": []}
    with llm.meter(fresh) as c2_cost, dspy.context(lm=fresh):
        for _ in range(3):
            runs["baseline"].append(ev.evaluate_dataset(DLReviewer(), test, dl_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, dl_scorer)["mean_score"])
    stats = {k: (st.mean(v), st.stdev(v)) for k, v in runs.items()}
    delta = stats["gepa"][0] - stats["baseline"][0]
    verdict_c2 = ("significant" if abs(delta) > 2 * max(stats["gepa"][1], stats["baseline"][1])
                  else "not significant")
    print(stats, f"delta={delta:+.3f}", verdict_c2, c2_cost)
    """)
ps.check("C2", """
assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
_m = {k: st.mean(v) for k, v in runs.items()}
_s = {k: st.stdev(v) for k, v in runs.items()}
_expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
             else "not significant")
assert verdict_c2 == _expected
assert {"calls", "usd"} <= set(c2_cost)
""")
ps.written("""
Scores move in steps of 1/16 (half an item) on 8 test items, and at temperature 1.0 the
same program can differ by one or two steps between runs. If the within-program spread is
as large as the gap, the C1 delta is not evidence. A zero spread (identical runs) is also
a finding — usually that the answers are near-deterministic for this task — but three
runs cannot distinguish "no noise" from "little noise".

A credible evaluation needs more items (the free oracle makes that cheap: every new
module is labelled for nothing — only the *authoring* of realistic modules costs), a
paired comparison on the same items with repeated runs (mean ± sd or a paired bootstrap),
the two sub-scores reported separately (naming and verdict fail for different reasons),
and the cost of each run. The honest sentence is "GEPA changed the mean test score by
X ± Y over 3 runs of 8 modules, at $Z" — not "GEPA improved the reviewer by X".
""")

ps.problem("C3", "Self-improvement with a free oracle — and a certificate", 12, """
In production the requests arrive **unlabelled** (`AG.field_requests()` — no gold
fields). The tableau can label them, so the reviewer can learn from its own failures with
no human in the loop. Do it, but only with labels you can trust.

1. Implement `self_label(request, tbox=None) -> dspy.Example`. Use **only the engine**
   (never a stored label): the module is `tbox` or `AG.case(request.id).tbox()`. Return a
   new example with the request's fields plus `gold_dl`, `gold_subsumption`,
   `constructors`, `sub_satisfiable`, `labelled_by="tableau"` and `certified`: true when
   the verdict is *subsumed*, or the module is pure ALC (`AG.ALC_CONSTRUCTORS`), or a
   countermodel in `AG.CERTIFICATES` checks out. Keep `kb` and `query` as the inputs.
2. Label the field requests; keep the certified ones as `trusted`.
3. Wrap the reviewer as a `Skill` (name, description, `build=DLReviewer`,
   `scorer=dl_scorer`, `dataset=dev`, the baseline instruction), evaluate it, and build a
   `SelfImprovingSkill` with `holdout=dev`, a GEPA optimiser with `max_metric_calls=30`
   and `min_gain=0.05`. Inside `llm.meter(lm, reflect)` (store `c3_cost`): run it on
   `trusted`, run **one** improvement round, then a **control round** with the optimiser
   replaced by the identity (`sis.optimise = lambda program, trainset: program`).
4. Print `sis.report()` and `skill.card()`; save the skill to
   `config.artifacts_dir() / "ch03_rail_module_reviewer_skill.json"` as `skill_path`.

In writing: what exactly did the oracle remove from the usual self-improvement problem,
and what did it *not* remove? What did the control round show, and could it ever have
been promoted?
""", auto_points=6)
ps.todo(
    stub="""
    def self_label(request, tbox: dl.TBox | None = None) -> dspy.Example:
        # TODO
        raise NotImplementedError

    labelled_field = None   # TODO
    trusted = None          # TODO
    skill = None            # TODO
    sis = None              # TODO: one GEPA round, then the identity control round
    skill_path = config.artifacts_dir() / "ch03_rail_module_reviewer_skill.json"
    """,
    solution="""
    def self_label(request, tbox: dl.TBox | None = None) -> dspy.Example:
        t = tbox if tbox is not None else AG.case(request.id).tbox()
        subsumed = dl.subsumes(A(request.sub), A(request.sup), t)
        used = dl.constructors_used(t)
        if subsumed or used <= AG.ALC_CONSTRUCTORS:
            certified = True
        else:
            cert = AG.CERTIFICATES.get(request.id)
            certified = cert is not None and AG.is_countermodel(t, request.sub, request.sup, cert)
        return dspy.Example(
            id=request.id, split=getattr(request, "split", "field"),
            kb=request.kb, query=request.query, sub=request.sub, sup=request.sup,
            gold_dl=dl.dl_name(t), gold_subsumption=subsumed, constructors=sorted(used),
            sub_satisfiable=dl.satisfiable(A(request.sub), t).satisfiable,
            labelled_by="tableau", certified=certified,
        ).with_inputs("kb", "query")

    labelled_field = [self_label(r) for r in AG.field_requests()]
    trusted = [ex for ex in labelled_field if ex.certified]
    print(pd.DataFrame([{"id": e.id, "dl": e.gold_dl, "subsumed": e.gold_subsumption,
                         "certified": e.certified} for e in labelled_field]))

    skill = Skill(
        name="rail-module-reviewer",
        description="Name the DL a rail-ontology module needs and answer the reviewer's "
                    "subsumption question.",
        build=DLReviewer, scorer=dl_scorer, dataset=dev,
        instruction=BASELINE_INSTRUCTION, tools=[])
    sis = SelfImprovingSkill(
        skill, holdout=dev,
        optimise=lambda program, trainset: opt.run_gepa(
            program, trainset, gepa_metric, max_metric_calls=30, reflection_lm=reflect),
        min_gain=0.05)
    with llm.meter(lm, reflect) as c3_cost:
        skill.evaluate()
        sis.run_all(trusted)
        print(sis.improve())
        sis.optimise = lambda program, trainset: program      # control: change nothing
        print(sis.improve())
    print(sis.report(), "\\n")
    print(skill.card())
    print("cost:", c3_cost)
    skill_path = skill.save(config.artifacts_dir() / "ch03_rail_module_reviewer_skill.json")
    """)
ps.check("C3", """
for ex in train + dev + test:          # the labeller must reproduce every gold label from the module
    bare = dspy.Example(id=ex.id, kb=ex.kb, query=ex.query, sub=ex.sub, sup=ex.sup).with_inputs("kb", "query")
    lab = self_label(bare)
    assert (lab.gold_dl, lab.gold_subsumption, lab.sub_satisfiable) == \\
        (ex.gold_dl, ex.gold_subsumption, ex.sub_satisfiable), ex.id
    assert lab.certified and lab.labelled_by == "tableau" and set(lab.inputs().keys()) == {"kb", "query"}
_t, _sub, _sup = blind_spot
_blind = dspy.Example(id="a2-blind-spot", kb=AG.describe_kb(_t), query="?", sub=_sub,
                      sup=_sup).with_inputs("kb", "query")
assert self_label(_blind, tbox=_t).certified is False, "an uncertified 'no' must not be trusted"
assert len(labelled_field) == len(AG.field_requests())
assert all(not hasattr(r, "gold_dl") or r.gold_dl is None for r in AG.field_requests())
assert len(sis.experience) == len(trusted)
assert all(e.gold.labelled_by == "tableau" and e.gold.certified for e in sis.experience.episodes)
assert {e.id for e in sis.holdout} == {e.id for e in dev}, "the gate reads dev, never test"
assert len(sis.rounds) == 2
for r in sis.rounds:
    assert r.promoted == ((r.after - r.before) >= sis.min_gain), f"round {r.round_index}"
assert skill.version == 1 + sum(r.promoted for r in sis.rounds)
assert skill_path.is_file() and {"calls", "usd"} <= set(c3_cost)
""")
ps.written("""
**What the oracle removed:** the *labelling* bottleneck. Every field request became a
training example at zero marginal cost and zero annotator time, with a verdict that is
provably right where it is certified — the step that makes self-improvement impractical in
Chapters 1 and 4 (where gold needs a human) simply disappears. The certificate matters:
on SH/SHIQ modules a tableau "no" is not a label (A2), and `self_label` discards it
instead of training the reviewer into the reasoner's blind spot. On this field set all six
are certified; on real traffic some would not be.

**What it did not remove:** (i) *selection bias* — the loop learns only from the failure
modes that the six field requests happen to exhibit; (ii) *over-fitting* — GEPA sees at
most six mined examples; (iii) *holdout reuse* — every round is judged on the same eight
dev modules, so repeated gating slowly fits the gate itself; the test split stays untouched
for exactly that reason; (iv) *noise* — with 8 holdout items and `min_gain=0.05`, a lucky
+1 item can pass the gate (C2 shows how large the run-to-run spread is).

**The control round** changes nothing, so its before/after are the same instruction on the
same holdout. With DSPy's cache on, the two evaluations replay identical requests, the gain
is exactly 0 and the gate rejects it — the gate works. **Without** the cache (or with a
`min_gain` below the noise), an identical instruction could be "promoted" on sampling noise
alone. That is the argument for a margin tied to measured noise, and for recording
rejected rounds: a loop that never rejects anything is drifting, not improving.
""")

# =========================================================================== #
ps.part("D", "A review agent, and the price of soundness", """
The agent gets the reasoner as tools. `check_subsumption` is the *expensive, sound* call —
in production each one is a reasoner job on the integrated ontology, billed in CI minutes.
""")
ps.code("""
ws_demo = AG.ReviewWorkspace("viaduct-critical")
demo_tools = {t.name: t for t in AG.build_review_tools(ws_demo)}
for name, t in demo_tools.items():
    print(f"{name:22s} {t.description.splitlines()[0]}")
print()
print(demo_tools["dl_expressivity"].invoke({}))
print(demo_tools["check_subsumption"].invoke({"sub": "Viaduct", "sup": "CriticalStructure"}))
print("trajectory:", ws_demo.log.names())
""")

ps.problem("D1", "Build and evaluate the review agent", 10, """
1. Write `REVIEW_PROMPT`, the agent's system prompt. It must make the agent inspect the
   module, name the logic from the constructors, check whether the subject class is
   satisfiable, **call `check_subsumption` before answering**, and end with a JSON object
   `{"dl": "...", "subsumed": true | false, "evidence": [...]}`.
2. Write `parse_review(text) -> dict` returning `{"dl": str, "subsumption": "true" |
   "false" | "unparseable"}` from the agent's final text (the JSON may be fenced or
   surrounded by prose; take the last object that has a `subsumed` key).
3. For every **test** item: a fresh `AG.ReviewWorkspace(ex.id)`, its tools, an agent
   (`agents.build_agent(ws, system_prompt=..., tools=...)`), one run on `ex.query`. Collect
   `d1` with columns `id`, `gold_dl`, `gold`, `predicted_dl`, `predicted`, `score` (your
   `dl_scorer` on the parsed answer), `reasoner_calls` (number of `check_subsumption`
   calls), `tool_calls` and `usd_estimate` (`llm.chat_usage(run.messages)`).

In writing: compare the agent with the tuned DSPy reviewer on the same test items — score
**and** cost per request. Which half of the task did the tools fix? Where did the agent
still go wrong, and was it the agent or the reasoner?
""", auto_points=5)
ps.todo(
    stub="""
    REVIEW_PROMPT = \"\"\"TODO\"\"\"

    def parse_review(text: str) -> dict:
        # TODO
        raise NotImplementedError

    d1 = None    # TODO: run the agent on every test item
    """,
    solution=r"""
    REVIEW_PROMPT = '''\
    You are the automated reviewer for Meridian Rail's Ontology Change Board. Each request
    is one ontology module and one question: is class SUB subsumed by class SUP?

    Procedure:
    1. show_module, then dl_expressivity. Name the logic from the constructors it reports
       (standard order: ALC or S, then H, O, I, then Q/N/F). Never guess letters.
    2. check_satisfiability on SUB. If SUB is unsatisfiable it is subsumed by every class;
       say so in the evidence -- it is a modelling error the board must see.
    3. check_subsumption(SUB, SUP). Never answer the subsumption question without it.
    4. Answer from the tool results only.

    End your reply with one JSON object and nothing after it:
    {"dl": "<name>", "subsumed": true or false, "evidence": ["tool results you relied on"]}
    '''

    def parse_review(text: str) -> dict:
        for blob in reversed(re.findall(r"\{[^{}]*\}", text or "")):
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or "subsumed" not in obj:
                continue
            value = obj["subsumed"]
            if isinstance(value, bool):
                verdict = str(value).lower()
            else:
                verdict = str(value).strip().lower()
                verdict = verdict if verdict in {"true", "false"} else "unparseable"
            return {"dl": str(obj.get("dl", "") or "").strip(), "subsumption": verdict}
        return {"dl": "", "subsumption": "unparseable"}

    rows = []
    for ex in test:
        ws = AG.ReviewWorkspace(ex.id)
        agent, _ = agents.build_agent(ws, system_prompt=REVIEW_PROMPT,
                                      tools=AG.build_review_tools(ws))
        run = agents.run_agent(agent, ws, ex.query)
        parsed = parse_review(run.answer)
        names = ws.log.names()
        rows.append({"id": ex.id, "gold_dl": ex.gold_dl, "gold": ex.gold_subsumption,
                     "predicted_dl": parsed["dl"], "predicted": parsed["subsumption"],
                     "score": dl_scorer(ex, dspy.Prediction(**parsed)).score,
                     "reasoner_calls": names.count("check_subsumption"),
                     "tool_calls": len(names),
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(f"mean score {d1.score.mean():.3f} on n={len(d1)}; "
          f"cost ≈ ${d1.usd_estimate.sum():.3f} total, "
          f"{d1.reasoner_calls.sum()} reasoner calls")
    d1
    """)
ps.check("D1", """
assert parse_review('{"dl": "SHIQ", "subsumed": false, "evidence": []}') == {"dl": "SHIQ", "subsumption": "false"}
assert parse_review('Done.\\n```json\\n{"dl": "ALC", "subsumed": true, "evidence": ["x"]}\\n```')["subsumption"] == "true"
assert parse_review('{"note": 1} and then {"dl": "S", "subsumed": "False", "evidence": []}') == {"dl": "S", "subsumption": "false"}
assert parse_review("It is subsumed.")["subsumption"] == "unparseable"
assert isinstance(d1, pd.DataFrame) and list(d1["id"]) == [ex.id for ex in test]
assert {"id", "gold_dl", "gold", "predicted_dl", "predicted", "score", "reasoner_calls",
        "tool_calls", "usd_estimate"} <= set(d1.columns)
assert set(d1["predicted"]) <= {"true", "false", "unparseable"}
by_id = {ex.id: ex for ex in test}
for _, row in d1.iterrows():
    expected = dl_scorer(by_id[row["id"]],
                         dspy.Prediction(dl=row["predicted_dl"], subsumption=row["predicted"])).score
    assert abs(row["score"] - expected) < 1e-9, row["id"]
""")
ps.written("""
Expect the agent to be near-perfect on this split (report it as "k/8", with the cost),
and several times more expensive per request than the DSPy reviewer: each episode is
4–6 model turns carrying the tool results, against one call.

* **The tools fixed naming completely** — `dl_expressivity` *computes* the name, so the
  letter rules GEPA had to learn in C1 become irrelevant once the agent calls it. The
  residual naming errors are the agent paraphrasing the tool ("SHIQ(D)", "ALC + H").
* **The tools fixed the verdicts on this corpus** because the reasoner is right on every
  test module — including `electrified-low-bridge`, where the agent should report the
  unsatisfiable subject, and the three non-ALC negatives, which the tableau happens to get
  right (the certificates in `AG.CERTIFICATES` are why we *know* it did). On a blind-spot
  module like A2's, an obedient agent would faithfully repeat the tableau's wrong "no":
  the error would be the reasoner's, and no prompt could fix it.
* A row with `reasoner_calls == 0` and a correct verdict is luck, not competence: the
  contract says to call `check_subsumption`, and the MDP in D2 is the principled version of
  the question "when may it skip the call?".
""")

ps.problem("D2", "Pricing the reasoner: a budgeted, stochastic MDP", 10, """
The board caps reasoner jobs per batch. For each queued request the bot may **guess** with
the told-subsumption heuristic (free, right with probability `p`) or **reason** (always
right, reward `1 − c`, one unit of budget). `AG.ReasoningBudgetMDP` has exactly these
**stochastic** transitions.

1. **Estimate `p` from data.** When the heuristic says *subsumed* it is certain (A1), so
   `p = 1`. Otherwise `p` depends on the module's observable `AG.risk_class`: estimate
   `p_hat[class]` on **train + dev** as the fraction of heuristic-"no" items whose gold is
   *not subsumed*. Build `queue`, the `p` of each **test** item in order.
2. Solve `M = AG.ReasoningBudgetMDP(queue, reasoner_cost=COST, budget=BUDGET)` with
   `mdp.value_iteration`, and get `plan = M.optimal_plan(pi)`.
3. Derive the closed form and implement `rule_value(p, c, B)`: the optimal expected
   return. Verify it against value iteration on a sweep of costs and budgets, recorded in
   `d2` (columns `cost`, `budget`, `v_star`, `rule`, `reasoner_calls`).
4. The transitions are stochastic: check `V*` by Monte-Carlo (`mdp.policy_value`, 3000
   episodes) for the optimal policy and for *always guess*. Then compute `realised`: the
   return the optimal plan actually earns on the 8 test items, using the heuristic's real
   correctness.

In writing: state the decision rule; explain why "always call the reasoner" is not
optimal even with an unlimited budget; and compare `V*` with `realised`.
""", auto_points=6)
ps.todo(
    stub="""
    COST, BUDGET = 0.25, 3

    p_hat = None          # TODO (1): {risk_class: p}
    queue = None          # TODO (1): one p per test item

    def rule_value(p: list[float], c: float, B: int) -> float:
        # TODO (3)
        raise NotImplementedError

    d2 = None             # TODO (3)
    mc_optimal = mc_guess = realised = None   # TODO (4)
    """,
    solution="""
    COST, BUDGET = 0.25, 3

    def told_on(ex) -> bool:
        return told_subsumes(AG.case(ex.id).tbox(), ex.sub, ex.sup)

    pools: dict[str, list[bool]] = {}
    for ex in train + dev:
        if not told_on(ex):
            cls = AG.risk_class(AG.case(ex.id).tbox())
            pools.setdefault(cls, []).append(not ex.gold_subsumption)
    p_hat = {cls: sum(v) / len(v) for cls, v in pools.items()}
    queue = [1.0 if told_on(ex) else p_hat[AG.risk_class(AG.case(ex.id).tbox())] for ex in test]
    print("p_hat:", {k: round(v, 3) for k, v in p_hat.items()})
    print("queue:", [round(p, 3) for p in queue])

    M = AG.ReasoningBudgetMDP(queue, reasoner_cost=COST, budget=BUDGET)
    V, pi = mdp.value_iteration(M)
    plan = M.optimal_plan(pi)
    print(f"V*(s0) = {V[M.initial_state()]:.3f}; plan:", plan)

    def rule_value(p: list[float], c: float, B: int) -> float:
        # guessing earns p_i; reasoning earns 1 - c. Spend the budget on the largest
        # positive gains (1 - c) - p_i, i.e. on the least reliable guesses.
        gains = sorted(((1 - c) - pi_ for pi_ in p if (1 - c) > pi_), reverse=True)
        return sum(p) + sum(gains[:B])

    rows = []
    for c in [0.0, 0.1, 0.25, 0.4, 0.6, 0.8]:
        for B in [0, 1, 2, 3, len(queue)]:
            Mc = AG.ReasoningBudgetMDP(queue, reasoner_cost=c, budget=B)
            Vc, pic = mdp.value_iteration(Mc)
            rows.append({"cost": c, "budget": B, "v_star": Vc[Mc.initial_state()],
                         "rule": rule_value(queue, c, B),
                         "reasoner_calls": Mc.optimal_plan(pic).count("reason")})
    d2 = pd.DataFrame(rows)

    M.rng.seed(0)
    mc_optimal = mdp.policy_value(M, mdp.greedy_policy(pi), episodes=3000)
    mc_guess = mdp.policy_value(M, lambda state, actions: "guess", episodes=3000)
    realised = sum((1 - COST) if a == "reason" else float(told_on(ex) == ex.gold_subsumption)
                   for a, ex in zip(plan, test))
    print(f"V* {V[M.initial_state()]:.3f}  MC optimal {mc_optimal:.3f}  "
          f"always guess: expected {sum(queue):.3f}, MC {mc_guess:.3f}  realised {realised:.3f}")
    d2.pivot(index="cost", columns="budget", values="reasoner_calls")
    """)
ps.check("D2", """
_pools = {}
for ex in train + dev:
    t = AG.case(ex.id).tbox()
    if not told_subsumes(t, ex.sub, ex.sup):
        _pools.setdefault(AG.risk_class(t), []).append(not ex.gold_subsumption)
assert set(p_hat) == set(_pools)
assert all(abs(p_hat[k] - sum(v) / len(v)) < 1e-9 for k, v in _pools.items())
assert len(queue) == len(test) and all(0.0 <= p <= 1.0 for p in queue)
assert abs(rule_value([0.9, 0.5, 0.95, 0.6], 0.2, 2) - 3.45) < 1e-9
assert abs(rule_value([0.9], 0.2, 1) - 0.9) < 1e-9 and abs(rule_value([0.3], 0.5, 0) - 0.3) < 1e-9
assert abs(V[M.initial_state()] - rule_value(queue, COST, BUDGET)) < 1e-6
assert isinstance(d2, pd.DataFrame) and len(d2) >= 20 and d2["budget"].nunique() >= 4
assert ((d2.v_star - d2.rule).abs() < 1e-6).all(), "value iteration and the closed form disagree"
for _, r in d2.iterrows():
    worth = sum(1 for p in queue if (1 - r.cost) > p)
    assert r.reasoner_calls == min(r.budget, worth), (r.cost, r.budget)
assert abs(mc_optimal - V[M.initial_state()]) < 0.15 and abs(mc_guess - sum(queue)) < 0.15
assert 0.0 <= realised <= len(test)
""")
ps.written("""
**Decision rule.** Guessing query *i* is worth `p_i` in expectation; reasoning is worth
`1 − c`. Queries are independent except through the budget, so the optimum is: compute the
gain `(1 − c) − p_i` of each query, and reason on the `B` queries with the largest positive
gains — the least reliable guesses — and guess on the rest. Value iteration never saw this
rule; it recovers it exactly on every row of the sweep, and the Monte-Carlo returns match
`V*` to sampling error, which is what "expected return of a stochastic MDP" means.

With the corpus estimates (`p ≈ 0.64` for modules with definitions, `≈ 0.33` for modules
with negation, `1` for told queries) and `c = 0.25`, every non-told query is worth
reasoning (0.75 > 0.64), the budget of 3 goes first to the negation module
(`electrified-low-bridge`) and then to two of the definition modules; the told query
(`dropper-asset`) is never sent to the reasoner.

**Why not always reason?** Because soundness has a price: once `c > 1 − p_i` the expected
loss from a wrong guess (`1 − p_i`) is smaller than the price of certainty, and the optimal
policy guesses even with budget to spare (the `c = 0.4` and `c = 0.8` rows). For the told
queries `p = 1`, so reasoning is *never* worth anything. "Always be sound" is optimal only
when errors are priced far above reasoner time — which is a statement about the reward,
and for a safety-critical rail asset the board may well set it that way (i.e. make a wrong
verdict cost much more than 1).

**Expected vs realised.** With `c = 0.25` and `B = 3` the numbers are deterministic:
`V* ≈ 5.80` against `≈ 5.15` for always guessing, and Monte-Carlo agrees with both to within
sampling error. But `V*` averages over the heuristic's error *rate*; `realised` is one draw
on eight actual requests. The six definition-class queries are tied at `p ≈ 0.64`, value
iteration breaks the tie by queue position and reasons on `plain-line-detection` and
`depot-major` — two items the heuristic actually gets right — while guessing on
`rail-break-urgent` and `tunnel-managed`, where it is wrong. So `realised = 5.25 < V*`:
the policy is optimal *for the information it has*, and the class-level `p` cannot tell a
true definition-mediated subsumption from a false one. The fix is a sharper observable
feature (one that separates those items before reasoning), a larger estimation set, or a
bigger budget — not a different solver.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "05"):
        print("wrote", path.name)
