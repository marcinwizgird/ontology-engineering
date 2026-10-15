# %% [markdown] assignment
# # Problem Set: Reviewing rail-ontology change requests with a reasoner and Claude
# ### Chapter 3 — Description Logics
#
# **Topic coverage:** Keet §3.1 (ALC, the tableau), §3.2 (the DL naming scheme and what each letter costs), §3.3 (reasoning services by reduction to satisfiability); course notebooks 01–04 of this chapter. Tools: DSPy and GEPA (Chapters 1–2), **tool-calling agents** through `agentlab.tools` and `agentlab.agents` (new in this chapter), and the Chapter 3 tableau reasoner.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 100 (Part A 20 / Part B 29 / Part C 19 / Part D 20 / Part E 12); 53 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 10–12 hours.
#
# **API budget:** ≈ \$1–3 **estimated, not yet measured** on `claude-sonnet-5-5` (≈ 160 DSPy calls at ≈ \$0.005 each, GEPA's reflection on `claude-opus-5-5`, and 13 agent episodes at a few cents each; GEPA is the largest line). Your cost lines are the measurement. Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# **Meridian Rail**, a (fictional) railway infrastructure manager, keeps its asset
# information in a modular OWL ontology. Discipline teams — track, signalling,
# structures, power, stations — submit new modules as pull requests to the
# **Ontology Change Board**, which applies two gates before a module is merged:
#
# * **Expressivity.** The nightly classification job runs a lightweight reasoner.
#   A module that needs transitive roles, a role hierarchy, inverse roles or number
#   restrictions must be routed to the heavyweight reasoner job instead, so every
#   request must state the **description logic the module needs** — ALC, S, ALCHIQ, …
# * **The reviewer's question.** Each request carries one question from the
#   discipline lead — *"is every level-crossing barrier a safety-critical asset?"* —
#   which is a **subsumption** query against the module. The board wants a verified
#   answer, not an opinion.
#
# The board has asked you, the ontology engineer, to automate the review:
#
# 1. **Understand the tools you already have.** A cheap *told-subsumption* heuristic
#    and the Chapter 3 tableau. The tableau is a **free, always-right oracle** on
#    this corpus — which makes this the one chapter where a deployed system can
#    label its own failures with no human in the loop. Find out exactly where
#    "always right" stops.
# 2. **Build the grader and a Claude reviewer**, measure it on a development split.
# 3. **Optimise it honestly** with GEPA (train / dev / held-out test, cost, noise).
# 4. **Ship a reviewer that cannot guess**: an agent that calls the reasoner, and a
#    pipeline in which the model proposes and the reasoner disposes — with an
#    escalation to a human where the reasoner cannot certify its answer.
# 5. **Check that you measured reasoning, not memory.** Run the reviewer on the Pizza
#    ontology every model has read — famous, renamed, and with the axioms changed —
#    and on an ontology no model has read: the fleet ontology SIP builds.
#
# The corpus (24 labelled modules, split 8/8/8 by item — one per phenomenon per
# split, four "subsumed" and four "not subsumed" in every split — plus 6 unlabelled
# field requests), the review guidelines, the agent's tools, the contamination twins
# and SIP's fleet modules are provided in `ch03_agentic.py`.
#
# > The original brief also **priced the reasoner** with a budgeted, stochastic MDP and
# > let the reviewer **improve itself** on oracle-labelled traffic. They return in
# > Chapter 6 (MDPs) and Chapter 10 (skills and gated self-improvement), the chapters
# > that introduce those layers.
#
# ## Submission requirements
#
# 1. **This notebook, executed top to bottom**, with every `TODO` implemented and every *Your answer* cell written.
# 2. **The artefacts it saves** under `artifacts/` (optimised instructions, run logs) — they are evidence, not by-products.
# 3. **Honest reporting.** A number without its split, its sample size and its cost earns no credit. Report the runs you did, including the ones that did not improve anything.
#
# The check cells are the marking scheme for the auto-graded points; do not edit them. The final self-test prints your auto-graded subtotal.
#
# > Solutions: `05_solutions.ipynb` — do not open it until you have attempted every problem.

# %% [markdown] solution
# # Problem Set: Reviewing rail-ontology change requests with a reasoner and Claude — Solutions
# ### Chapter 3 — Description Logics
#
# **Topic coverage:** Keet §3.1 (ALC, the tableau), §3.2 (the DL naming scheme and what each letter costs), §3.3 (reasoning services by reduction to satisfiability); course notebooks 01–04 of this chapter. Tools: DSPy and GEPA (Chapters 1–2), **tool-calling agents** through `agentlab.tools` and `agentlab.agents` (new in this chapter), and the Chapter 3 tableau reasoner.
#
# **Level:** Graduate (practice-first). Combines conceptual analysis with building, measuring and optimising a real Claude-backed agent.
#
# **Total points:** 100 (Part A 20 / Part B 29 / Part C 19 / Part D 20 / Part E 12); 53 pts are auto-graded by the check cells, the rest are marked by hand against the rubric. **Estimated effort:** 10–12 hours.
#
# **API budget:** ≈ \$1–3 **estimated, not yet measured** on `claude-sonnet-5-5` (≈ 160 DSPy calls at ≈ \$0.005 each, GEPA's reflection on `claude-opus-5-5`, and 13 agent episodes at a few cents each; GEPA is the largest line). Your cost lines are the measurement. Re-running unchanged cells is free: DSPy caches identical requests. Every model call in this notebook is a billed request to Anthropic; the cost lines the problems ask for are part of the answer.
#
# ## The brief
#
# **Meridian Rail**, a (fictional) railway infrastructure manager, keeps its asset
# information in a modular OWL ontology. Discipline teams — track, signalling,
# structures, power, stations — submit new modules as pull requests to the
# **Ontology Change Board**, which applies two gates before a module is merged:
#
# * **Expressivity.** The nightly classification job runs a lightweight reasoner.
#   A module that needs transitive roles, a role hierarchy, inverse roles or number
#   restrictions must be routed to the heavyweight reasoner job instead, so every
#   request must state the **description logic the module needs** — ALC, S, ALCHIQ, …
# * **The reviewer's question.** Each request carries one question from the
#   discipline lead — *"is every level-crossing barrier a safety-critical asset?"* —
#   which is a **subsumption** query against the module. The board wants a verified
#   answer, not an opinion.
#
# The board has asked you, the ontology engineer, to automate the review:
#
# 1. **Understand the tools you already have.** A cheap *told-subsumption* heuristic
#    and the Chapter 3 tableau. The tableau is a **free, always-right oracle** on
#    this corpus — which makes this the one chapter where a deployed system can
#    label its own failures with no human in the loop. Find out exactly where
#    "always right" stops.
# 2. **Build the grader and a Claude reviewer**, measure it on a development split.
# 3. **Optimise it honestly** with GEPA (train / dev / held-out test, cost, noise).
# 4. **Ship a reviewer that cannot guess**: an agent that calls the reasoner, and a
#    pipeline in which the model proposes and the reasoner disposes — with an
#    escalation to a human where the reasoner cannot certify its answer.
# 5. **Check that you measured reasoning, not memory.** Run the reviewer on the Pizza
#    ontology every model has read — famous, renamed, and with the axioms changed —
#    and on an ontology no model has read: the fleet ontology SIP builds.
#
# The corpus (24 labelled modules, split 8/8/8 by item — one per phenomenon per
# split, four "subsumed" and four "not subsumed" in every split — plus 6 unlabelled
# field requests), the review guidelines, the agent's tools, the contamination twins
# and SIP's fleet modules are provided in `ch03_agentic.py`.
#
# > The original brief also **priced the reasoner** with a budgeted, stochastic MDP and
# > let the reviewer **improve itself** on oracle-labelled traffic. They return in
# > Chapter 6 (MDPs) and Chapter 10 (skills and gated self-improvement), the chapters
# > that introduce those layers.
#
# > This is the **instructor solutions** notebook. It runs clean end to end against the live API and ends by asserting that every check passed. Student version: `05_assignment.ipynb`.
#
# > Answers produced by a live model vary between runs. The model answers below describe what a good submission shows; the check cells test properties that hold for any competent run, not recorded outputs.

# %%
import sys, json, logging
from pathlib import Path

# Make the course root (the folder holding agentlab/) and this chapter importable.
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "agentlab").is_dir():
        sys.path.insert(0, str(candidate))
        break
sys.path.insert(0, str(here))

import agentlab
from agentlab import llm
from agentlab.grading import Grader

print(json.dumps(agentlab.describe_environment(), indent=1))
llm.require_credentials()             # this problem set calls the live Anthropic API
logging.getLogger("dspy").setLevel(logging.WARNING)
GRADER = Grader('Chapter 3 — Description Logics — Reviewing rail-ontology change requests with a reasoner and Claude')

import re, statistics as st
import dspy
import numpy as np
import pandas as pd
import ch03_toolkit as dl
import ch03_agentic as AG
from agentlab import evaluation as ev, optimize as opt, agents

A = dl.Atomic
train, dev, test = AG.build_dataset("train"), AG.build_dataset("dev"), AG.build_dataset("test")
CERTIFIED = AG.validate_gold()          # every label re-derived by the engine (a few seconds)
print(f"train {len(train)} / dev {len(dev)} / test {len(test)} / field {len(AG.FIELD_CASES)}")

# %% [markdown]
# ### The corpus
#
# Every row is one change request. `kb` is what the reviewer (human or Claude) sees — the
# module's axioms and role facts, rendered *without* naming the logic — and `query` is the
# discipline lead's question. The gold labels were written by hand and then re-derived by
# `AG.validate_gold()`, which also tells you **how** each verdict is certified.

# %%
overview = pd.DataFrame([{"id": ex.id, "split": ex.split, "phenomenon": ex.phenomenon,
                          "gold_dl": ex.gold_dl, "subsumed": ex.gold_subsumption,
                          "certified by": CERTIFIED[ex.id]} for ex in train + dev + test])
print(overview.groupby("split").subsumed.agg(["count", "sum"]).rename(columns={"sum": "n_subsumed"}))
overview

# %%
ex = dev[0]
print(ex.kb, "\n")
print(ex.query)

# %% [markdown]
# ---
#
# ## Part A — The cheap heuristic, the free oracle, and where it stops being right
#
# Before anything touches a model, understand the two answers you can already compute for
# free: a structural heuristic, and the tableau.

# %% [markdown]
# ### A1. A told-subsumption heuristic, and a dataset that can punish it (10 pts)
#
# Reviewers' first instinct is to *read the hierarchy*: follow the asserted superclasses
# upwards and see whether the queried class turns up. Implement that as
# `told_subsumes(tbox, sub, sup) -> bool`:
#
# * `sub` is told-subsumed by itself;
# * for an axiom whose **left side is atomic** `X`, every **atomic conjunct** of the right
#   side (flatten nested `dl.And`) is a told superclass of `X`; anything else on the right
#   (`exists`, `forall`, `or`, `not`, number restrictions) is ignored;
# * an **equivalence** `X == Y` with *both* sides atomic works in both directions;
# * take the transitive closure.
#
# Then build `a1`, one row per labelled item (train + dev + test), with columns `id`,
# `split`, `phenomenon`, `gold`, `told` (your heuristic's verdict), `heuristic_correct` and
# `risk_class` (`AG.risk_class(tbox)`), and `a1_acc`: indexed by split, with columns
# `heuristic` (your heuristic's accuracy) and `always_subsumed` (the accuracy of the trivial
# strategy *"always answer subsumed"*).
#
# In writing: (i) the heuristic can only err in one direction — which, and why? (ii) The
# old version of this corpus had almost only "subsumed" questions. What would *"always
# answer subsumed"* have scored there, and what would that have meant for an optimiser whose
# feedback includes the guideline `use-the-reasoner`?

# %% assignment
def told_subsumes(tbox: dl.TBox, sub: str, sup: str) -> bool:
    # TODO
    raise NotImplementedError

a1 = None        # TODO: one row per labelled item
a1_acc = None    # TODO: per split: heuristic accuracy, always-subsumed accuracy

# %% solution
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

# %%
# Marking scheme for A1 -- do not edit.
with GRADER.check('A1', points=5):
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

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# **(i) One-sided errors.** Every told superclass is a genuine consequence (an asserted
# `X ⊑ … ⊓ Y ⊓ …` entails `X ⊑ Y`, and entailment is transitive), so when the heuristic
# says *subsumed* it is right — the check above confirms it on all 30 modules. It fails only
# by saying *not subsumed* when the subsumption holds for a reason the hierarchy does not
# show: through the **right-hand side of a definition** (`barrier-safety-critical`,
# `viaduct-critical`, the inverse-role definitions) or **vacuously**, because the subject
# class is unsatisfiable (`automated-manual-crossing`). It is sound but incomplete — and
# its errors sit exactly on the inferences that make a reasoner worth having.
#
# On this corpus it scores 5/8 on every split (it gets all four negatives and the told
# chain, and misses the definition, inverse-definition and unsatisfiable-subject items);
# "always subsumed" scores 4/8.
#
# **(ii) Why balance matters.** On an all-"subsumed" corpus, *always subsumed* scores
# 100 % on the verdict. The scorer then never reports `use-the-reasoner`, so the feedback
# GEPA reads never mentions it and the optimiser has no reason to write it into the
# instruction — the tuned reviewer would say "true" to everything and fail silently on the
# first negative request in production. A dataset can only teach a rule that some item
# punishes; that is why every split here has four negatives, spread over four phenomena.

# %% [markdown]
# ### A2. Where the free oracle stops being right (10 pts)
#
# The tableau decides **ALC**. It *names* S, H, I, N and Q but reasons as if transitivity,
# sub-roles, inverses and number restrictions were not there — so it reasons over a
# *weaker* theory than the module states.
#
# (a) Build `blind_spot = (tbox, sub, sup)`: a small rail module with a **role hierarchy or
# a transitive role** in which `sub ⊑ sup` **is** entailed but `dl.subsumes` says it is
# not. Then build `compiled`: a copy of the module plus one or more ALC axioms that the role
# box licenses (see `AG.rbox_licensed` for the three accepted schemata), after which the
# tableau finds the subsumption.
#
# (b) `AG.validate_gold()` certifies "not subsumed" on the non-ALC modules with
# countermodels (`AG.CERTIFICATES`). Write your own certificate `my_certificate` — an
# `AG.Interpretation` — for a **pure-ALC** "not subsumed" item of your choice
# (`cert_case`, one not in `AG.CERTIFICATES`), and confirm it with `AG.is_countermodel`.
#
# (c) In writing: in which direction is the tableau's verdict trustworthy on *any* module
# of this corpus, and why? What does (a) mean for a system that labels its own training
# data with this oracle? What would you run in production instead?

# %% assignment
blind_spot = None       # TODO (a): (tbox, sub, sup)
compiled = None         # TODO (a): the module plus RBox-licensed ALC axioms

cert_case = "..."       # TODO (b)
my_certificate = None   # TODO (b): AG.Interpretation(domain=..., concepts=..., roles=...)

raise NotImplementedError

# %% solution
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

# %%
# Marking scheme for A2 -- do not edit.
with GRADER.check('A2', points=4):
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

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# **Which direction is safe.** Treating transitivity, sub-roles, inverses and number
# restrictions as absent (or opaque) only *removes* constraints, so every model of the real
# module is also a model of what the tableau reasons over. If `C ⊓ ¬D` has no model even
# in the weaker theory, it has none in the real one: a **"subsumed"** verdict is sound on
# every module. A **"not subsumed"** verdict is only as good as the tableau's completeness —
# guaranteed for pure ALC, not otherwise. Part (a) is the counterexample: the tableau builds
# a `maintains`-successor that is a `Signal` but never adds the `isResponsibleFor` edge the
# sub-role axiom demands, so it reports a "model" that is not a model. That is why
# `validate_gold` asks for a countermodel on exactly the non-ALC negatives, and why a
# countermodel is the right certificate: it is a finite object anyone can check.
#
# **Consequence for self-labelling.** An oracle that is right on this corpus is not an
# oracle that is right. A self-improving system that trusts every tableau "no" on SH/SHIQ
# modules would *train itself into the reasoner's blind spot*: the optimiser would learn to
# answer "not subsumed" on sub-role questions where the correct answer is "subsumed", and
# the promotion gate — scored by the same oracle — would reward it. The labeller must
# therefore say when it is **certified** (Problem D2 here; the self-labelling loop itself
# is Chapter 10's) and discard the rest.
#
# **In production** the board would run a complete reasoner for the logic in question —
# HermiT, Pellet or Konclude for SHOIQ/SROIQ, ELK for the EL modules — and keep the
# countermodel/justification as the artefact of each verdict. The tableau in this chapter is
# a teaching reasoner; the naming skill of §3.2 is what tells you when it is no longer
# enough.

# %% [markdown]
# ---
#
# ## Part B — Build the grader and the Claude reviewer
#
# The guidelines the scorer can report — ids plus the sentence GEPA's reflection reads —
# are in `AG.DL_RULEBOOK`:

# %%
for rule in AG.DL_RULEBOOK:
    print(f"{rule.id:38s} {rule.description[:80]}")

# %% [markdown]
# ### B1. A diagnostic review scorer (14 pts)
#
# Implement `dl_scorer(gold, pred) -> ev.ScoreReport`. `gold` is a dataset row
# (`gold_dl`, `gold_subsumption`, `constructors`, `sub_satisfiable`, `sub`, `sup`); `pred`
# has string fields `dl` and `subsumption`. The score is **0.5 for the name + 0.5 for the
# verdict**.
#
# **Name.** Normalise (strip, upper-case, remove spaces, drop a trailing `(D)`) and parse
# against the standard order `^(ALC|S)(H?)(O?)(I?)([QNF]?)$`. Full marks only when the
# parsed letters equal gold's. When wrong, report every rule that applies:
#
# | situation | violated |
# |---|---|
# | does not parse (prose, wrong letter order, …) | `name-the-logic-exactly` |
# | base differs (ALC vs S) | `s-for-transitive` |
# | H / I needed but missing | `h-for-role-hierarchy` / `i-for-inverse` |
# | gold has Q or N and the answer's number letter differs | `q-for-qualified-number` |
# | a letter (H, O, I, or a number letter) that gold does not have | `no-unused-letters` |
# | wrong, but none of the above applies | `name-the-logic-exactly` |
#
# **Verdict.** Accept `true/yes/subsumed/entailed` and `false/no/not subsumed/not entailed`
# (case-insensitive, surrounding punctuation ignored). Anything else earns 0 and
# `answer-true-or-false`. A wrong verdict earns 0 and `use-the-reasoner`, plus
# `unsatisfiable-subsumed-by-everything` when gold is *subsumed* because the subject class
# is unsatisfiable.
#
# The notes must say what was wrong **and why** — for a wrong name, the correct name and
# the constructors the module uses. That text is what GEPA reads.

# %% assignment
DL_PATTERN = re.compile(r"^(ALC|S)(H?)(O?)(I?)([QNF]?)$")

def parse_dl(text) -> dict | None:
    # TODO: normalise, then match DL_PATTERN; return the letters, or None
    raise NotImplementedError

def dl_scorer(gold, pred) -> ev.ScoreReport:
    # TODO
    raise NotImplementedError

# %% solution
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

# %%
# Marking scheme for B1 -- do not edit.
with GRADER.check('B1', points=11):
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

# %% [markdown]
# ### B2. The reviewer as a DSPy program (7 pts)
#
# Write a signature `ModuleReview` with inputs `kb` and `query` and outputs
# `justification`, `dl` and `subsumption` (all strings), and a factory
# `DLReviewer(instruction)` returning a `dspy.Module` with a single `dspy.Predict` whose
# instruction is `instruction`. The field descriptions are part of the prompt — write them
# for a colleague who has never seen this notation (manual marks), and say in a sentence why
# you put the output fields in the order you did. Configure Claude and run it once on
# `train[0]`.

# %% assignment
BASELINE_INSTRUCTION = ("You review ontology modules for a railway. Say which description "
                        "logic the module needs and answer the subsumption question.")

# TODO: class ModuleReview(dspy.Signature): ...
# TODO: def DLReviewer(instruction=BASELINE_INSTRUCTION): ...

lm = llm.configure_dspy()
smoke = None     # TODO: DLReviewer()(**train[0].inputs())

raise NotImplementedError

# %% solution
BASELINE_INSTRUCTION = ("You review ontology modules for a railway. Say which description "
                        "logic the module needs and answer the subsumption question.")

class ModuleReview(dspy.Signature):
    """Name the description logic an ontology module needs and answer a subsumption question about it."""

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

# %%
# Marking scheme for B2 -- do not edit.
with GRADER.check('B2', points=4):
    assert set(ModuleReview.input_fields) == {"kb", "query"}
    assert {"dl", "subsumption", "justification"} <= set(ModuleReview.output_fields)
    program = DLReviewer("custom instruction")
    assert len(list(program.named_predictors())) == 1
    assert opt.instruction_of(program) == "custom instruction"
    assert isinstance(smoke.dl, str) and isinstance(smoke.subsumption, str)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# The justification comes **first** so the model writes down the constructors and the
# deciding axioms *before* it commits to a name and a verdict — a cheap, explicit
# chain-of-thought that also gives the error analysis something to read. The descriptions
# spell out the notation (`<=`, `==`, `r-`, `>=n r.C`) because the naming task depends on
# noticing exactly those tokens, and fix the output contract (bare name, bare `true/false`)
# that the scorer parses.

# %% [markdown]
# ### B3. Baseline on the development split, with its cost (8 pts)
#
# Evaluate the baseline reviewer on `dev` with `ev.evaluate_dataset`, inside
# `llm.meter(lm)`. Store the result in `baseline_dev` and the cost in `baseline_dev_cost`,
# and build `b3`: the per-item rows joined with each item's `phenomenon` and `gold_dl`.
#
# Then write a short **error analysis** separating the two halves of the task: which
# *naming* rules were broken and on which phenomena, and which *verdicts* were wrong — and
# for those, was it a definition, an inverse, or the unsatisfiable subject? Which of the two
# halves could a tool fix completely, and which needs the model to reason?

# %% assignment
# TODO: baseline_dev = ..., baseline_dev_cost = ..., b3 = ...

raise NotImplementedError

# %% solution
with llm.meter(lm) as baseline_dev_cost:
    baseline_dev = ev.evaluate_dataset(DLReviewer(), dev, dl_scorer)
print("mean:", baseline_dev["mean_score"], " violations:", baseline_dev["violations"])
print("cost:", baseline_dev_cost)
meta = pd.DataFrame([{"item": ex.id, "phenomenon": ex.phenomenon, "gold_dl": ex.gold_dl}
                     for ex in dev])
b3 = pd.DataFrame(baseline_dev["rows"]).merge(meta, on="item")
b3

# %%
# Marking scheme for B3 -- do not edit.
with GRADER.check('B3', points=3):
    assert baseline_dev["n"] == len(dev) == 8
    assert {r["item"] for r in baseline_dev["rows"]} == {ex.id for ex in dev}
    assert 0.0 <= baseline_dev["mean_score"] <= 1.0
    assert {"calls", "usd"} <= set(baseline_dev_cost)
    assert isinstance(b3, pd.DataFrame) and len(b3) == 8 and {"phenomenon", "score"} <= set(b3.columns)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# The analysis to hand in is of *your* run; a typical baseline looks like this.
#
# * **Naming.** A strong model usually gets ALC and S, and loses points on the letters that
#   live *outside* the axiom text or in one token: `H` from the role-hierarchy line
#   (`substation-feeder` answered `S`), `I` from a single `r-` (`switch-monitored` answered
#   `S` or `ALCI` instead of `SI`), and the **N/Q** distinction (`bay-platform-low-use` is
#   `<=2 servedBy.Top`, an unqualified restriction — N, not Q). It also over-claims: "SHIN" for a module with
#   no transitive role, or appending `(D)`. These are *rule* errors — `dl_expressivity`
#   would fix all of them, which is the argument for giving the agent that tool (Part D).
# * **Verdicts.** The negatives are rarely wrong. The failures cluster on the inferences
#   the told-hierarchy heuristic also misses: subsumption *through the right-hand side of a
#   definition*, and the **unsatisfiable subject** (`permissive-stop-signal`), where the
#   natural-language question ("is a permissive stop signal a level crossing?") sounds
#   absurd and the model answers `false`, while the logic says `true`, vacuously. These
#   need reasoning; a model that "reasons by eye" makes exactly the errors of A1.
#
# Cost: 8 calls — a few tens of cents at most; this is the unit price for every later
# comparison.

# %% [markdown]
# ---
#
# ## Part C — Optimise honestly — then let the oracle label the training data
#
# GEPA rewrites the instruction by reflecting on the scorer's feedback. The rules: **optimise
# on `train`, select on `dev`, report on `test`**, and put a cost and a noise estimate next
# to every number. Then use the chapter's distinctive asset — an oracle that labels for free
# — to improve the reviewer from unlabelled traffic, behind a promotion gate.

# %% [markdown]
# ### C1. A budgeted GEPA run with a held-out report (12 pts)
#
# 1. Build the GEPA feedback metric from your scorer and `AG.DL_RULEBOOK`, and a separate
#    reflection LM (`llm.reflection_lm()`).
# 2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
#    inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost`.
# 3. Compare baseline and tuned on **`test`** with `opt.compare` (store as `c1`) and print
#    `c1.report()`.
# 4. Save the tuned instruction to `agentlab.artifacts_dir() /
#    "ch03_module_reviewer_instruction.txt"`.
#
# In writing: read the instruction diff. Which guidelines did GEPA put into words? Did it
# learn to *follow definitions* and to treat an unsatisfiable subject as subsumed — or only
# the letter rules? Did it add anything that only fits the eight training modules?

# %% assignment
GEPA_BUDGET = 60
# TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
instruction_path = agentlab.artifacts_dir() / "ch03_module_reviewer_instruction.txt"

raise NotImplementedError

# %% solution
GEPA_BUDGET = 60
gepa_metric = opt.make_gepa_metric(dl_scorer, AG.DL_RULEBOOK)
reflect = llm.reflection_lm()
with llm.meter(lm, reflect) as gepa_cost:
    tuned = opt.run_gepa(DLReviewer(), train, gepa_metric, valset=dev,
                         max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
c1 = opt.compare(DLReviewer(), tuned, test, dl_scorer)
print(c1.report())
print("\nGEPA cost:", gepa_cost)

instruction_path = agentlab.artifacts_dir() / "ch03_module_reviewer_instruction.txt"
instruction_path.write_text(opt.instruction_of(tuned), encoding="utf-8")

# %%
# Marking scheme for C1 -- do not edit.
with GRADER.check('C1', points=6):
    ids = lambda rows: {ex.id for ex in rows}
    assert not (ids(test) & (ids(train) | ids(dev))), "the test split must be untouched"
    assert {r["item"] for r in c1.after["rows"]} == ids(test), "report on the test split"
    assert c1.before["n"] == c1.after["n"] == len(test)
    assert instruction_path.is_file()
    assert instruction_path.read_text(encoding="utf-8") == opt.instruction_of(tuned)
    assert {"calls", "usd"} <= set(gepa_cost) and GEPA_BUDGET <= 100

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Your wording will differ; look for three things.
#
# * **Letter rules.** These are the easiest for GEPA: the feedback names the rule, the
#   correct name and the constructors, so a good run writes "S if any role is transitive",
#   "H for a sub-role declaration", "I for `r-`", "Q if the restriction has a filler, N if
#   not", and "standard order, no (D)". Only rules some *training* item violated appear:
#   train has an ALCH, an ALCI, an ALCQ and a SHIQ module, but no N — so if the tuned prompt
#   never mentions N, the dev/test N item (`bay-platform-low-use` is in dev) shows it.
# * **Reasoning rules.** `use-the-reasoner` and `unsatisfiable-subsumed-by-everything`
#   appear only if a training verdict failed. A DSPy program has no reasoner tool, so the
#   best GEPA can do is write the *procedure* down ("expand defined classes on the right,
#   check whether the subject is contradictory first") — an instruction, not a guarantee.
#   Whether it transfers is exactly what the test score measures.
# * **Over-fitting.** Sentences naming training classes ("interlockings are never control
#   centres") are memorised answers; they cost tokens on every call and are wrong on the
#   next module.
#
# A test delta of ±1 item (±0.06) is inside the noise (C2); report it as such.

# %% [markdown]
# ### C2. Is the difference bigger than the noise? (7 pts)
#
# With caching **disabled** (`fresh = llm.dspy_lm(cache=False)`, `with dspy.context(lm=fresh):`),
# run the baseline and the tuned reviewers on `test` three times each, inside
# `llm.meter(fresh)`; store mean scores in `runs = {"baseline": [...], "gepa": [...]}`.
# Set `verdict_c2` to `"significant"` if `|mean_gepa − mean_baseline| > 2·max(sd_gepa,
# sd_baseline)`, else `"not significant"`.
#
# In writing: what does this say about the C1 number, and what would a credible evaluation
# of the reviewer need?

# %% assignment
fresh = llm.dspy_lm(cache=False)
runs = {"baseline": [], "gepa": []}
# TODO: fill runs (inside llm.meter(fresh) -> c2_cost), then compute verdict_c2
verdict_c2 = None

raise NotImplementedError

# %% solution
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

# %%
# Marking scheme for C2 -- do not edit.
with GRADER.check('C2', points=4):
    assert set(runs) == {"baseline", "gepa"} and all(len(v) == 3 for v in runs.values())
    assert all(0.0 <= x <= 1.0 for v in runs.values() for x in v)
    _m = {k: st.mean(v) for k, v in runs.items()}
    _s = {k: st.stdev(v) for k, v in runs.items()}
    _expected = ("significant" if abs(_m["gepa"] - _m["baseline"]) > 2 * max(_s.values())
                 else "not significant")
    assert verdict_c2 == _expected
    assert {"calls", "usd"} <= set(c2_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Scores move in steps of 1/16 (half an item) on 8 test items, and at temperature 1.0 the
# same program can differ by one or two steps between runs. If the within-program spread is
# as large as the gap, the C1 delta is not evidence. A zero spread (identical runs) is also
# a finding — usually that the answers are near-deterministic for this task — but three
# runs cannot distinguish "no noise" from "little noise".
#
# A credible evaluation needs more items (the free oracle makes that cheap: every new
# module is labelled for nothing — only the *authoring* of realistic modules costs), a
# paired comparison on the same items with repeated runs (mean ± sd or a paired bootstrap),
# the two sub-scores reported separately (naming and verdict fail for different reasons),
# and the cost of each run. The honest sentence is "GEPA changed the mean test score by
# X ± Y over 3 runs of 8 modules, at $Z" — not "GEPA improved the reviewer by X".

# %% [markdown]
# ---
#
# ## Part D — A reviewer that cannot guess
#
# The agent gets the reasoner as tools (`agentlab.tools` logs every call). `check_subsumption`
# is the *expensive, sound* call — in production each one is a reasoner job on the integrated
# ontology, billed in CI minutes.

# %%
ws_demo = AG.ReviewWorkspace("viaduct-critical")
demo_tools = {t.name: t for t in AG.build_review_tools(ws_demo)}
for name, t in demo_tools.items():
    print(f"{name:22s} {t.description.splitlines()[0]}")
print()
print(demo_tools["dl_expressivity"].invoke({}))
print(demo_tools["check_subsumption"].invoke({"sub": "Viaduct", "sup": "CriticalStructure"}))
print("trajectory:", ws_demo.log.names())

# %% [markdown]
# ### D1. Build and evaluate the review agent (10 pts)
#
# 1. Write `REVIEW_PROMPT`, the agent's system prompt. It must make the agent inspect the
#    module, name the logic from the constructors, check whether the subject class is
#    satisfiable, **call `check_subsumption` before answering**, and end with a JSON object
#    `{"dl": "...", "subsumed": true | false, "evidence": [...]}`.
# 2. Write `parse_review(text) -> dict` returning `{"dl": str, "subsumption": "true" |
#    "false" | "unparseable"}` from the agent's final text (the JSON may be fenced or
#    surrounded by prose; take the last object that has a `subsumed` key).
# 3. For every **test** item: a fresh `AG.ReviewWorkspace(ex.id)`, its tools
#    (`AG.build_review_tools(ws)`), an agent (`agents.build_agent(tools,
#    system_prompt=...)`), one run (`agents.run_agent(agent, ex.query, log=ws.log)`).
#    Collect `d1` with columns `id`, `gold_dl`, `gold`, `predicted_dl`, `predicted`,
#    `score` (your `dl_scorer` on the parsed answer), `reasoner_calls` (number of
#    `check_subsumption` calls), `tool_calls` and `usd_estimate`
#    (`agents.chat_usage(run.messages)`).
#
# In writing: compare the agent with the tuned DSPy reviewer on the same test items — score
# **and** cost per request. Which half of the task did the tools fix? Where did the agent
# still go wrong, and was it the agent or the reasoner?

# %% assignment
REVIEW_PROMPT = """TODO"""

def parse_review(text: str) -> dict:
    # TODO
    raise NotImplementedError

d1 = None    # TODO: run the agent on every test item

# %% solution
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
    agent = agents.build_agent(AG.build_review_tools(ws), system_prompt=REVIEW_PROMPT)
    run = agents.run_agent(agent, ex.query, log=ws.log)
    parsed = parse_review(run.answer)
    names = ws.log.names()
    rows.append({"id": ex.id, "gold_dl": ex.gold_dl, "gold": ex.gold_subsumption,
                 "predicted_dl": parsed["dl"], "predicted": parsed["subsumption"],
                 "score": dl_scorer(ex, dspy.Prediction(**parsed)).score,
                 "reasoner_calls": names.count("check_subsumption"),
                 "tool_calls": len(names),
                 "usd_estimate": agents.chat_usage(run.messages)["usd_estimate"]})
d1 = pd.DataFrame(rows)
print(f"mean score {d1.score.mean():.3f} on n={len(d1)}; "
      f"cost ≈ ${d1.usd_estimate.sum():.3f} total, "
      f"{d1.reasoner_calls.sum()} reasoner calls")
d1

# %%
# Marking scheme for D1 -- do not edit.
with GRADER.check('D1', points=5):
    assert parse_review('{"dl": "SHIQ", "subsumed": false, "evidence": []}') == {"dl": "SHIQ", "subsumption": "false"}
    assert parse_review('Done.\n```json\n{"dl": "ALC", "subsumed": true, "evidence": ["x"]}\n```')["subsumption"] == "true"
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

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Expect the agent to be near-perfect on this split (report it as "k/8", with the cost),
# and several times more expensive per request than the DSPy reviewer: each episode is
# 4–6 model turns carrying the tool results, against one call.
#
# * **The tools fixed naming completely** — `dl_expressivity` *computes* the name, so the
#   letter rules GEPA had to learn in C1 become irrelevant once the agent calls it. The
#   residual naming errors are the agent paraphrasing the tool ("SHIQ(D)", "ALC + H").
# * **The tools fixed the verdicts on this corpus** because the reasoner is right on every
#   test module — including `electrified-low-bridge`, where the agent should report the
#   unsatisfiable subject, and the three non-ALC negatives, which the tableau happens to get
#   right (the certificates in `AG.CERTIFICATES` are why we *know* it did). On a blind-spot
#   module like A2's, an obedient agent would faithfully repeat the tableau's wrong "no":
#   the error would be the reasoner's, and no prompt could fix it.
# * A row with `reasoner_calls == 0` and a correct verdict is luck, not competence: the
#   contract says to call `check_subsumption`. "When may it skip the call?" is a real
#   question — reasoner time is budgeted — and Chapter 6 answers it with an MDP.

# %% [markdown]
# ### D2. The model proposes, the reasoner disposes (10 pts)
#
# The agent of D1 *chooses* to call the reasoner, and a row with `reasoner_calls == 0`
# shows it can choose not to. A **pipeline** makes the check unconditional: the reviewer
# proposes a name, a verdict and a justification; a deterministic **critic** — the engine —
# disposes. This is the pattern the literature on LLMs in ontology engineering converges
# on (an LLM proposes, a symbolic tool checks, a human approves), so build it and measure
# what each part contributes.
#
# 1. Implement `critic(tbox, sub, sup, case_id=None) -> dict` returning `dl` (the engine's
#    name), `subsumed` (the tableau's verdict) and `certified`: true when the verdict is
#    *subsumed*, or the module is pure ALC (`AG.ALC_CONSTRUCTORS`), or `case_id` has a
#    countermodel in `AG.CERTIFICATES` that checks out (A2 told you why).
# 2. Implement `review_with_critic(program, ex, tbox=None) -> dict`. Run `program` on the
#    example; take the module from `tbox` or `AG.case(ex.id).tbox()`; call the critic.
#    Return `dl` (the critic's), `subsumption` (`"true"`/`"false"` from the critic when it
#    is certified, else `"escalate"`), `source` (`"model+reasoner"` when the model's verdict
#    agreed with a certified critic, `"reasoner"` when the critic overrode it,
#    `"escalated"` when it could not certify), `disagreed` (did the model's verdict differ
#    from the reasoner's?), and the model's raw `model_dl`, `model_subsumption` and
#    `justification`.
# 3. Run it with the **tuned** reviewer from C1 on every **test** item, inside
#    `llm.meter(lm)` (store `d2_cost`); collect `d2` with columns `id`, `gold`,
#    `model_subsumption`, `subsumption`, `source`, `disagreed` and `score` (your `dl_scorer`
#    on `dl` and `subsumption`).
# 4. Run it on A2's blind spot as `blind_review` (an example built from
#    `AG.describe_kb(blind_spot[0])`, with `tbox=blind_spot[0]`).
#
# In writing: put the single-pass reviewer (C1, tuned, test), the agent (D1) and the
# pipeline side by side — score, model calls and dollars per request. `disagreed` counts
# the model's verdict errors *without any labels*: what is that worth in production? With
# a sound and complete checker, what is the model still for — and what happens on a module
# where the checker is not complete?

# %% assignment
def critic(tbox: dl.TBox, sub: str, sup: str, case_id: str | None = None) -> dict:
    # TODO
    raise NotImplementedError

def review_with_critic(program, ex, tbox: dl.TBox | None = None) -> dict:
    # TODO
    raise NotImplementedError

d2 = None             # TODO: one row per test item (inside llm.meter(lm) -> d2_cost)
blind_review = None   # TODO: the pipeline on A2's blind spot

# %% solution
def critic(tbox: dl.TBox, sub: str, sup: str, case_id: str | None = None) -> dict:
    subsumed = dl.subsumes(A(sub), A(sup), tbox)
    if subsumed or dl.constructors_used(tbox) <= AG.ALC_CONSTRUCTORS:
        certified = True
    else:
        cert = AG.CERTIFICATES.get(case_id) if case_id else None
        certified = cert is not None and AG.is_countermodel(tbox, sub, sup, cert)
    return {"dl": dl.dl_name(tbox), "subsumed": subsumed, "certified": certified}

def review_with_critic(program, ex, tbox: dl.TBox | None = None) -> dict:
    t = tbox if tbox is not None else AG.case(ex.id).tbox()
    pred = program(kb=ex.kb, query=ex.query)
    model_verdict = parse_verdict(pred.subsumption)
    c = critic(t, ex.sub, ex.sup, getattr(ex, "id", None))
    if not c["certified"]:
        verdict, source = "escalate", "escalated"
    else:
        verdict = "true" if c["subsumed"] else "false"
        source = "model+reasoner" if model_verdict == c["subsumed"] else "reasoner"
    return {"dl": c["dl"], "subsumption": verdict, "source": source,
            "disagreed": model_verdict != c["subsumed"],
            "model_dl": str(pred.dl), "model_subsumption": str(pred.subsumption),
            "justification": str(pred.justification)}

rows = []
with llm.meter(lm) as d2_cost:
    for ex in test:
        r = review_with_critic(tuned, ex)
        rows.append({"id": ex.id, "gold": ex.gold_subsumption,
                     "model_subsumption": r["model_subsumption"],
                     "subsumption": r["subsumption"], "source": r["source"],
                     "disagreed": r["disagreed"],
                     "score": dl_scorer(ex, dspy.Prediction(dl=r["dl"],
                                                            subsumption=r["subsumption"])).score})
d2 = pd.DataFrame(rows)
_bt, _bsub, _bsup = blind_spot
blind_ex = dspy.Example(id="a2-blind-spot", kb=AG.describe_kb(_bt),
                        query=f"Is {_bsub} subsumed by {_bsup}?", sub=_bsub,
                        sup=_bsup).with_inputs("kb", "query")
blind_review = review_with_critic(tuned, blind_ex, tbox=_bt)
print(f"pipeline mean score {d2.score.mean():.3f} on n={len(d2)}; model disagreed with the "
      f"reasoner on {int(d2.disagreed.sum())}; cost {d2_cost}")
print("blind spot ->", blind_review["subsumption"], "| the model said", blind_review["model_subsumption"])
d2

# %%
# Marking scheme for D2 -- do not edit.
with GRADER.check('D2', points=5):
    for ex in test:
        c = critic(AG.case(ex.id).tbox(), ex.sub, ex.sup, ex.id)
        assert c["certified"] and c["dl"] == ex.gold_dl and c["subsumed"] == ex.gold_subsumption, ex.id
    _t, _s, _p = blind_spot
    assert critic(_t, _s, _p)["certified"] is False, "an uncertified 'no' must not be trusted"
    assert blind_review["subsumption"] == "escalate" and blind_review["source"] == "escalated"
    assert isinstance(d2, pd.DataFrame) and list(d2["id"]) == [ex.id for ex in test]
    assert {"id", "gold", "model_subsumption", "subsumption", "source", "disagreed",
            "score"} <= set(d2.columns)
    assert set(d2["source"]) <= {"model+reasoner", "reasoner", "escalated"}
    by_id = {ex.id: ex for ex in test}
    for _, row in d2.iterrows():
        ex = by_id[row["id"]]
        assert row["subsumption"] == str(ex.gold_subsumption).lower(), row["id"]
        assert (row["source"] == "reasoner") == bool(row["disagreed"]), row["id"]
    assert {"calls", "usd"} <= set(d2_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# Your numbers are what count; the shape to expect:
#
# | reviewer | test score | model calls / request | what decides the verdict |
# |---|---|---|---|
# | single pass (C1, tuned) | your C1 number | 1 | the model |
# | agent (D1) | near 1.0 | 4–6 turns | the reasoner, *if* the agent calls it |
# | pipeline (D2) | 1.0 on this split | 1 | the reasoner, always |
#
# On this corpus the pipeline scores 1.0 by construction: the critic computes the name
# and certifies every verdict. That is the point, not a trick. When a sound and complete
# checker exists, the verdict should not come from a model at all; the model's call buys
# the **justification** a reviewer reads, and the **disagreement count** — how often the
# model's own answer was wrong — measured on unlabelled traffic for free. A rising
# disagreement rate is the earliest warning that the modules have drifted from what the
# instruction was tuned on.
#
# The agent reaches the same verdicts at several times the cost and with a failure mode
# the pipeline cannot have: it may answer without calling the tool. Prefer the agent only
# where the procedure is *not* fixed in advance (which tool, how many calls), which is not
# the case here.
#
# The blind spot is why the third outcome exists. There the tableau says "not subsumed"
# and is wrong; a pipeline that always lets the reasoner override would publish a wrong
# verdict *with the authority of a reasoner*. The critic knows it cannot certify a "no" on
# a module with a role hierarchy and no countermodel, so the pipeline escalates to a
# human — whatever the model said. "Propose, check, approve" needs all three parts: the
# check is only as good as its coverage, and the escalation is where its coverage ends.

# %% [markdown]
# ---
#
# ## Part E — Reasoning or remembering?
#
# Every number so far was measured on Meridian Rail's modules, which no model has seen.
# Most published results on LLMs in ontology engineering are measured on ontologies every
# model *has* seen — the Pizza tutorial above all. Part E measures what that does to a
# score, then tests the reviewer on an ontology that was never published: the fleet
# ontology SIP builds in its demo.

# %%
pizza = AG.contamination_dataset()
verdicts = pd.DataFrame([{"item": ex.item, "variant": ex.variant,
                          "subsumed": ex.gold_subsumption} for ex in pizza])
print(verdicts.pivot(index="item", columns="variant", values="subsumed")[list(AG.VARIANTS)])
print()
print(pizza[2].kb)
print(pizza[2].query)

# %% [markdown]
# ### E1. Reasoning or remembering? The Pizza twins (8 pts)
#
# Each of the five questions comes in three variants. **famous**: the tutorial's names and
# axioms (miniaturised). **renamed**: the same axioms with names that carry no world
# knowledge. **counterfactual**: the tutorial's names with *one* axiom changed, so that the
# answer a model remembers is wrong (Margherita without its closure axiom is not provably
# vegetarian; an anchovy reclassified as a vegetable makes the Napoletana vegetarian). All
# fifteen modules are pure ALC, so every gold verdict is certified.
#
# 1. Run the **tuned** reviewer on all fifteen, inside `llm.meter(lm)` (store `e1_cost`), and
#    build `e1` with columns `id`, `item`, `variant`, `gold`, `predicted` (`parse_verdict`
#    on the answer, or `None`) and `verdict_ok`.
# 2. `e1_acc`: verdict accuracy per variant (a Series indexed by variant), and
#    `contamination_gap = e1_acc["renamed"] - e1_acc["counterfactual"]`.
# 3. Run the D1 agent on the five **counterfactual** modules
#    (`AG.ReviewWorkspace(ex.id, tbox=...)` with the module from `AG.contamination_tbox`),
#    and build `e1_agent` with columns `id`, `gold`, `predicted`, `reasoner_calls`.
#
# In writing: what does the gap measure, and what would a 92 % score on the Pizza ontology
# (a published figure for LLM-based restriction verification) tell you about a new
# ontology? Did the agent answer from its tools or from its memory on the counterfactuals?
# What should a benchmark for ontology-engineering assistants contain?

# %% assignment
e1 = None                 # TODO (1), inside llm.meter(lm) -> e1_cost
e1_acc = None             # TODO (2)
contamination_gap = None  # TODO (2)
e1_agent = None           # TODO (3)

raise NotImplementedError

# %% solution
rows = []
with llm.meter(lm) as e1_cost:
    for ex in pizza:
        pred = tuned(kb=ex.kb, query=ex.query)
        verdict = parse_verdict(pred.subsumption)
        rows.append({"id": ex.id, "item": ex.item, "variant": ex.variant,
                     "gold": ex.gold_subsumption, "predicted": verdict,
                     "verdict_ok": verdict == ex.gold_subsumption})
e1 = pd.DataFrame(rows)
e1_acc = e1.groupby("variant").verdict_ok.mean()[list(AG.VARIANTS)]
contamination_gap = e1_acc["renamed"] - e1_acc["counterfactual"]
print(e1_acc.to_string(), f"\ncontamination gap (renamed - counterfactual): {contamination_gap:+.2f}")
print("cost:", e1_cost)

rows = []
for ex in pizza:
    if ex.variant != "counterfactual":
        continue
    t, *_ = AG.contamination_tbox(ex.item, "counterfactual")
    ws = AG.ReviewWorkspace(ex.id, tbox=t)
    agent = agents.build_agent(AG.build_review_tools(ws), system_prompt=REVIEW_PROMPT)
    run = agents.run_agent(agent, ex.query, log=ws.log)
    parsed = parse_review(run.answer)
    rows.append({"id": ex.id, "gold": ex.gold_subsumption,
                 "predicted": {"true": True, "false": False}.get(parsed["subsumption"]),
                 "reasoner_calls": ws.log.names().count("check_subsumption"),
                 "usd_estimate": agents.chat_usage(run.messages)["usd_estimate"]})
e1_agent = pd.DataFrame(rows)
e1_agent

# %%
# Marking scheme for E1 -- do not edit.
with GRADER.check('E1', points=4):
    assert isinstance(e1, pd.DataFrame) and len(e1) == 15
    assert {"id", "item", "variant", "gold", "predicted", "verdict_ok"} <= set(e1.columns)
    assert set(e1["variant"]) == set(AG.VARIANTS)
    gold = {ex.id: ex.gold_subsumption for ex in pizza}
    assert all(row["gold"] == gold[row["id"]] for _, row in e1.iterrows())
    assert (e1.verdict_ok == (e1.predicted == e1.gold)).all()
    assert set(e1_acc.index) == set(AG.VARIANTS)
    assert np.allclose(e1_acc[list(AG.VARIANTS)],
                       e1.groupby("variant").verdict_ok.mean()[list(AG.VARIANTS)])
    assert abs(contamination_gap - (e1_acc["renamed"] - e1_acc["counterfactual"])) < 1e-9
    assert isinstance(e1_agent, pd.DataFrame) and len(e1_agent) == 5
    assert {"id", "gold", "predicted", "reasoner_calls"} <= set(e1_agent.columns)
    assert {"calls", "usd"} <= set(e1_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# **What the gap measures.** The renamed and the counterfactual variants test the same
# skill — derive the verdict from the axioms shown — on equally small ALC modules. The
# renamed one gives memory nothing to work with; the counterfactual one gives memory the
# *wrong* answer. A reviewer that reads the axioms scores the same on both; a positive gap
# is the share of answers that came from what the model remembers about pizzas rather than
# from the module in front of it. Expect the gap to concentrate on the items where the
# remembered answer is also the *commonsense* one (a Margherita is vegetarian; ice cream is
# not a pizza), which is exactly where an open-world reading and a closed-world intuition
# part ways.
#
# **What a Pizza score tells you.** A high famous-variant score is an upper bound mixed with
# memory: on Pizza, a model can be right for the wrong reason, and nothing in the score says
# which. A 92 % on Pizza therefore predicts little about a new domain; the renamed score is
# the better predictor, and a counterfactual score near it is the evidence that the model
# reads the axioms. This is why the course's corpora are invented (Meridian Rail, St.
# Brigid's) and why its transfer tests use SIP's own, unpublished ontology.
#
# **The agent.** With `check_subsumption` available and a prompt that requires it, the agent
# should follow the tool on every counterfactual. Read the rows where it did not call the
# tool, or called it and answered otherwise — that is memory overriding evidence, the most
# dangerous failure an assistant can have, because its answer looks informed.
#
# **A benchmark worth having** contains, per question, an unpublished or renamed variant and
# a counterfactual one; reports the variants separately; certifies its gold with a reasoner
# (as here) rather than with the published ontology's labels; and states its cost.

# %% [markdown]
# ### E2. An ontology no model has read: SIP's fleet (4 pts)
#
# `AG.fleet_dataset()` holds seven review questions over the fleet ontology SIP builds
# (vehicles, engines, wheels, manufacturers), with gold certified by the tableau. Evaluate
# the **baseline** and the **tuned** reviewers on it with `ev.evaluate_dataset`, and run the
# D2 pipeline with the tuned reviewer on every item, all inside `llm.meter(lm)` (store
# `e2_cost`). Store `e2 = {"baseline": <mean score>, "tuned": <mean score>,
# "pipeline_disagreements": <int>}`.
#
# In writing: did the tuning transfer from rail to fleet? SIP's validate stage now has a
# *semantic critic* that asks whether each axiom is **true in the domain**. How is that
# question different from the one this reviewer answers, and which of the two can a
# reasoner settle?

# %% assignment
fleet = AG.fleet_dataset()
e2 = None     # TODO (inside llm.meter(lm) -> e2_cost)

raise NotImplementedError

# %% solution
fleet = AG.fleet_dataset()
with llm.meter(lm) as e2_cost:
    base_fleet = ev.evaluate_dataset(DLReviewer(), fleet, dl_scorer)
    tuned_fleet = ev.evaluate_dataset(tuned, fleet, dl_scorer)
    pipe_fleet = [review_with_critic(tuned, ex) for ex in fleet]
e2 = {"baseline": base_fleet["mean_score"], "tuned": tuned_fleet["mean_score"],
      "pipeline_disagreements": sum(r["disagreed"] for r in pipe_fleet)}
print(e2, e2_cost)
pd.DataFrame(tuned_fleet["rows"])

# %%
# Marking scheme for E2 -- do not edit.
with GRADER.check('E2', points=2):
    assert len(fleet) == 7 and {ex.split for ex in fleet} == {"fleet"}
    assert set(e2) == {"baseline", "tuned", "pipeline_disagreements"}
    assert 0.0 <= e2["baseline"] <= 1.0 and 0.0 <= e2["tuned"] <= 1.0
    assert isinstance(e2["pipeline_disagreements"], (int, np.integer))
    assert 0 <= e2["pipeline_disagreements"] <= len(fleet)
    assert {"calls", "usd"} <= set(e2_cost)

# %% [markdown] assignment
# **Your answer:**
#
# *(Write your answer here.)*

# %% [markdown] solution
# **Solution.**
#
# **Transfer.** The fleet modules use the same phenomena (a definition, a universal trap,
# an unsatisfiable subject from a merge, a transitive part-of chain) in a vocabulary the
# reviewer was not tuned on. If the tuned score holds, the instruction learned *procedure*
# (follow definitions, "only" is not "some", contradictory subjects are subsumed); if it
# drops, it learned rail. With seven items one error is 0.07 of the mean, so report it as a
# signal. The pair `fleet-truck-diesel-open` / `fleet-truck-diesel-closed` is the sharpest
# probe: one extra axiom (every vehicle has an engine) turns "only diesel engines" into
# "some diesel engine", and the verdict flips.
#
# **Two different questions.** This reviewer answers *does the ontology entail X?* — a
# question a reasoner settles, which is why the pipeline can certify it. SIP's semantic
# critic answers *is what the ontology says true of the domain?* ("every vehicle has some
# engine" — what about trailers?). No reasoner can settle that: the axioms are the only
# input a reasoner has. That is why SIP's critic is advisory, mixes seeded wrong axioms into
# every call to measure its own precision and recall, and leaves the decision to a human at
# the review gate, while a check like this one can gate a release on its own.

# %% [markdown]
# ---
#
# ## Grading rubric
#
# | Part | Problem | Auto | Manual | Pts |
# |---|---|---|---|---|
# | A | A1 A told-subsumption heuristic, and a dataset that can punish it | 5 | 5 | 10 |
# | A | A2 Where the free oracle stops being right | 4 | 6 | 10 |
# | B | B1 A diagnostic review scorer | 11 | 3 | 14 |
# | B | B2 The reviewer as a DSPy program | 4 | 3 | 7 |
# | B | B3 Baseline on the development split, with its cost | 3 | 5 | 8 |
# | C | C1 A budgeted GEPA run with a held-out report | 6 | 6 | 12 |
# | C | C2 Is the difference bigger than the noise? | 4 | 3 | 7 |
# | D | D1 Build and evaluate the review agent | 5 | 5 | 10 |
# | D | D2 The model proposes, the reasoner disposes | 5 | 5 | 10 |
# | E | E1 Reasoning or remembering? The Pizza twins | 4 | 4 | 8 |
# | E | E2 An ontology no model has read: SIP's fleet | 2 | 2 | 4 |
# | **Total** | | | | **100** |
#
# *Manual* points are for the written answers and for the quality of the engineering evidence (splits, sample sizes, cost, honest negative results).

# %% [markdown]
# ---
#
# ## Self-test
#
# Re-run this cell after finishing. It lists every auto-graded problem and whether its check passed.

# %%
AUTO_GRADED = ['A1', 'A2', 'B1', 'B2', 'B3', 'C1', 'C2', 'D1', 'D2', 'E1', 'E2']
_ = GRADER.summary(AUTO_GRADED)

# %% solution
GRADER.assert_all_passed(AUTO_GRADED)
