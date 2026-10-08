"""Build the Chapter 10 problem set: 04_assignment.ipynb + 04_solutions.ipynb.

Run from anywhere:  python chapters/ch10_rough_temporal_fuzzy/_build_assignment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from oe_course.assignment import ProblemSet  # noqa: E402

ps = ProblemSet(
    chapter="Chapter 10 — Rough, Temporal, and Fuzzy Modelling",
    title="Choosing — and pricing — the formalism for an ED ontology with Claude",
    coverage=("Keet §10.1 (temporal: Allen's interval algebra, composition, path "
              "consistency), §10.2 (vagueness: fuzzy membership, t-norms, alpha-cuts; "
              "granularity: rough sets, lower/upper approximation); course notebooks 01–03 "
              "of this chapter. Tools: DSPy + GEPA, LangChain agents, the Chapter 10 "
              "interval, fuzzy and rough-set engine."),
    scenario="""
    The Emergency Department of **Northfield General Hospital** is building a
    patient-flow and sepsis early-warning ontology. Its clinical-informatics lead,
    Dr. Amara Okafor, has a backlog of 24 requirements from clinicians, managers and
    the pharmacy committee. Each is imperfect in exactly one way: it relates things
    that happen **over time**, it uses a predicate with **no sharp boundary** ("a high
    temperature"), it has to be answered from data **too coarse** to separate the
    cases, or it is plain **crisp**. Each needs a different formalism, and each
    formalism has a price: deciding consistency of a general Allen network is
    NP-complete, while fuzzy membership and rough approximation are polynomial.

    You are the ontology engineer. Your brief:

    1. **Justify the labels with the engine.** Before anyone automates the choice,
       show on the ED's own data — the triage vitals, the coded triage log, the
       sepsis-bundle protocol — what each formalism buys and what it costs.
    2. **Build a grader and a Claude advisor** that, given a requirement, names the
       formalism **and** its reasoning cost. An advisor that picks right but cannot
       price the choice will happily hand the ED an NP-complete reasoning problem it
       did not need. Optimise it with GEPA on `train`, select on `dev`, report on a
       held-out `test`, with cost and run-to-run noise.
    3. **Ship a review agent** that looks at the data attached to each requirement
       and runs the engine before it recommends anything.
    4. **Price the search.** Model constraint propagation as an MDP and work out when
       proving (in)consistency is worth what it costs — and what an honest reward for
       "consistent" has to look like.

    The backlog (24 items, 6 per formalism, split 8 / 8 / 8 by item — 2 per formalism
    per split), the ED's data and the protocol are provided in `ch10_agentic.py`; every
    gold label is re-derived from its attached data by `A.validate_gold()`.
    """,
    effort="10–12 hours",
    api_budget="≈ $5–12 **estimated** (not measured) on `claude-opus-5` for a full run: "
               "≈ 200 DSPy calls at roughly $0.02–0.05 each (the two GEPA runs are the "
               "largest lines) plus 8 agent episodes at roughly $0.10–0.25 each. "
               "Re-running unchanged cells is free — DSPy caches identical requests "
               "(except in C3, which disables the cache on purpose).",
)

ps.setup("""
import itertools, random, re, statistics as st, time
import dspy
import numpy as np
import pandas as pd
import ch10_toolkit as ch10
import ch10_agentic as A
from oe_course import evaluation as ev, llm, mdp, optimize as opt, agents

GOLD = A.validate_gold()          # every gold label re-derived from its witness data
train, dev, test = A.build_dataset("train"), A.build_dataset("dev"), A.build_dataset("test")
print(f"train {len(train)} / dev {len(dev)} / test {len(test)}")
pd.DataFrame([{"id": r.id, "split": r.split, "formalism": r.formalism,
               "cost": A.EXPRESSIVITY_COST[r.formalism], "requirement": r.text}
              for r in A.REQUIREMENTS])
""")

# =========================================================================== #
ps.part("A", "What each formalism buys, on the ED's own data", """
Everything in this part is deterministic and free: no model calls. The point is to be
able to *defend* a label for each kind of requirement with the Chapter 10 engine before
you ask Claude to make the choice — and to know what the choice costs.
""")

ps.problem("A1", "A threshold is confidently wrong at the boundary", 9, """
The ED's sepsis screen currently reads "high temperature" as `temp >= 38.0` °C.
Clinicians defend thresholds anywhere between 37.8 and 38.5. The ED's own vague
predicates are in `A.VAGUE_PREDICATES` (trapezoids) and `A.degree(name, value)`; the
evening's triage vitals are in `A.VITALS` (`visit -> (temp, heart_rate)`).

(a) Build `a1`, one row per visit, with columns `visit`, `temp`, `hr`, `fever`
(`A.degree("high_fever", temp)`), `crisp_38` (`temp >= 38.0`), `contested` (the crisp
decision differs between the thresholds 37.8 and 38.5), `sepsis_min` and
`sepsis_product` (the fuzzy conjunction of `fever` and `A.degree("tachycardia", hr)`
under `ch10.fuzzy_and` with the `min` and the `product` t-norm).

(b) Implement `threshold_for_alpha(alpha)`: the temperature `T` such that the
alpha-cut `{t : fever(t) >= alpha}` is exactly `{t : t >= T}`, for `0 < alpha <= 1`.
Read the ramp off `A.VAGUE_PREDICATES["high_fever"]` — do not hard-code it.

(c) In writing: which visits is the crisp rule *confidently wrong* about, and which
visit does *any* fever threshold miss? What does an alpha-cut buy over the crisp rule
if it also ends in a threshold? Which t-norm would you use for "high fever **and**
fast heart rate", and why?
""", auto_points=5)
ps.todo(
    stub="""
    a1 = None                     # TODO (a)

    def threshold_for_alpha(alpha: float) -> float:
        # TODO (b)
        raise NotImplementedError
    """,
    solution="""
    rows = []
    for visit, (temp, hr) in A.VITALS.items():
        fever, tachy = A.degree("high_fever", temp), A.degree("tachycardia", hr)
        rows.append({"visit": visit, "temp": temp, "hr": hr, "fever": fever,
                     "crisp_38": temp >= 38.0,
                     "contested": (temp >= 37.8) != (temp >= 38.5),
                     "sepsis_min": ch10.fuzzy_and(fever, tachy, "min"),
                     "sepsis_product": ch10.fuzzy_and(fever, tachy, "product")})
    a1 = pd.DataFrame(rows)

    def threshold_for_alpha(alpha: float) -> float:
        _, (a, b, _, _) = A.VAGUE_PREDICATES["high_fever"]
        return a + alpha * (b - a)          # the rising edge of the trapezoid, inverted

    print({alpha: round(threshold_for_alpha(alpha), 3) for alpha in (0.25, 0.5, 0.75, 1.0)})
    a1
    """)
ps.check("A1", """
assert isinstance(a1, pd.DataFrame) and len(a1) == len(A.VITALS)
assert {"visit", "temp", "hr", "fever", "crisp_38", "contested",
        "sepsis_min", "sepsis_product"} <= set(a1.columns)
for r in a1.itertuples():
    t, h = A.VITALS[r.visit]
    assert abs(r.fever - A.degree("high_fever", t)) < 1e-9
    assert bool(r.crisp_38) == (t >= 38.0)
    assert bool(r.contested) == ((t >= 37.8) != (t >= 38.5))
    f, g = A.degree("high_fever", t), A.degree("tachycardia", h)
    assert abs(r.sepsis_min - min(f, g)) < 1e-3 and abs(r.sepsis_product - f * g) < 1e-3
contested = a1[a1.contested.astype(bool)]
assert len(contested) > 0 and ((contested.fever > 0) & (contested.fever < 1)).all(), \\
    "every contested visit sits on the fuzzy ramp"
grid = [round(36.0 + 0.05 * i, 2) for i in range(100)]
for alpha in (0.25, 0.5, 0.75, 1.0):
    T = threshold_for_alpha(alpha)
    assert [t for t in grid if A.degree("high_fever", t) >= alpha] == \\
           [t for t in grid if t >= T - 1e-9], f"alpha={alpha}"
""")
ps.written("""
**Confidently wrong.** The contested visits are v05 (37.9 °C), v09 (38.0), v02 (38.1)
and v08 (38.4). The crisp rule gives each a hard yes/no, and moving the threshold
within the range clinicians actually defend flips all four — while their fuzzy degrees
(0.4, 0.5, 0.6, 0.9) say exactly what is true: they are partly febrile. v09 at 38.0 is
"sepsis screen positive" and v05 at 37.9 is "negative", a 0.1 °C difference inside
thermometer error. Meanwhile v01 (39.2) and v12 (39.5), 1.3 °C apart, get the same
label as v09. **The visit no fever threshold helps** is v10: 37.6 °C (fever 0.1) with a
heart rate of 125 (tachycardia 1.0). Any fever-only rule, crisp or fuzzy, ranks v10
near the bottom; the conjunction still does (min 0.1), which is an argument about the
*screen's* design, not the formalism — the ED should look at an "or"/weighted rule too.

**Alpha-cut.** An alpha-cut ends in a threshold (`T = 37.5 + alpha` here), so it does
not remove the decision — it moves it to a place where it is **explicit and
auditable**: "act at membership ≥ 0.5" is a stated policy, derived from one reviewed
membership function, and the same alpha can be applied consistently across all vague
predicates (fever, tachycardia, low saturation). A magic `38.0` in a SPARQL filter is
none of these. The fuzzy degree also survives *upstream* of the cut: ranking, triage
ordering and combination use the degree, and only the final action is cut.

**T-norm.** `min` (Gödel) keeps the weakest sign; `product` multiplies them: v08 goes
from 0.55 to 0.495 and v02 from 0.3 to 0.18 under `product`, while fully-true cases
(v01, v04) are unchanged. `product` penalises every
additional partly-true condition, which is right when the conditions are independent
evidence that must *all* be strong; `min` is right when the conjunction is only as
strong as its weakest link and the ranking should not be dominated by the number of
conditions. For a screening rule whose job is not to miss cases, `min` is the safer
choice (it is never below `product`); either way it must be chosen and documented,
because they give different orderings.
""")

ps.problem("A2", "What the triage screen cannot decide", 8, """
The old triage screen kept four coded fields (`A.TRIAGE_LOG`); the discharge records
say which visits went on to intensive care (`A.TRIAGE_TARGETS["icu"]`).

(a) Build `a2` with one row for **every non-empty subset** of the recorded attributes
and columns `attributes` (a sorted tuple), `n_attributes`, `granules` (number of
indiscernibility classes), `lower`, `upper` (sizes of the approximations), `boundary`
(the list of visits) and `accuracy`.

(b) Set `best_attributes` to the smallest subset reaching the maximum accuracy (ties:
fewest attributes, then the alphabetically first tuple).

(c) In writing: what can the ED say about ICU admission from the triage screen — what
is certain, what is possible, what is undecidable? Is any recorded field redundant?
What would you ask the ED to start recording, and why is this a rough-set problem
rather than a fuzzy one?
""", auto_points=5)
ps.todo(
    stub="""
    a2 = None                 # TODO (a)
    best_attributes = None    # TODO (b)
    """,
    solution="""
    system, target = A.TRIAGE_LOG, A.TRIAGE_TARGETS["icu"]
    rows = []
    for r in range(1, len(system.attributes()) + 1):
        for attrs in itertools.combinations(sorted(system.attributes()), r):
            rows.append({"attributes": attrs, "n_attributes": r,
                         "granules": len(system.indiscernibility(attrs)),
                         "lower": len(system.lower_approximation(target, attrs)),
                         "upper": len(system.upper_approximation(target, attrs)),
                         "boundary": system.boundary(target, attrs),
                         "accuracy": system.accuracy(target, attrs)})
    a2 = pd.DataFrame(rows)
    best = min(rows, key=lambda row: (-row["accuracy"], row["n_attributes"], row["attributes"]))
    best_attributes = best["attributes"]
    print("best:", best_attributes, best["accuracy"], "boundary:", best["boundary"])
    a2.sort_values(["accuracy", "n_attributes"], ascending=[False, True])
    """)
ps.check("A2", """
system, target = A.TRIAGE_LOG, A.TRIAGE_TARGETS["icu"]
assert isinstance(a2, pd.DataFrame) and len(a2) == 2 ** len(system.attributes()) - 1
for r in a2.itertuples():
    attrs = tuple(r.attributes)
    assert attrs == tuple(sorted(attrs)) and r.n_attributes == len(attrs)
    assert abs(r.accuracy - system.accuracy(target, attrs)) < 1e-9
    assert list(r.boundary) == system.boundary(target, attrs)
    assert r.granules == len(system.indiscernibility(attrs))
acc = {tuple(r.attributes): r.accuracy for r in a2.itertuples()}
for s in acc:
    for t in acc:
        if set(s) < set(t):
            assert acc[s] <= acc[t] + 1e-9, "a finer partition can never lose accuracy"
top = max(acc.values())
expected = min((k for k, v in acc.items() if v == top), key=lambda k: (len(k), k))
assert tuple(best_attributes) == expected
""")
ps.written("""
With all four fields, ICU admission is **certain** for v03, v04, v05 and v10 (the lower
approximation), **possible** for v01 and v02 (the boundary), and ruled out for the
rest; accuracy 4/6 ≈ 0.67. v01 and v02 are identical on every recorded field — high
acuity, ambulance, fever, 65+ — and one went to ICU and one did not. No reasoning over
these four fields can separate them; the honest output is "v01/v02: undecidable from
the triage screen", not a guess.

Two different three-field subsets reach the same 0.67 — {acuity, age_band, fever} and
{acuity, arrival, fever} — so with the other three present, either `arrival` or
`age_band` is **redundant** for this target (two reducts). `acuity` is in both and
alone gives 0.0: it is necessary but nowhere near sufficient.

Ask the ED to record a field that separates v01 from v02 at triage — e.g. the first
lactate or the NEWS2 score. Rough-set accuracy makes the request concrete: it names
the exact pair of visits a new field must split, and it can be re-measured after.

It is a rough problem, not a fuzzy one, because nothing here is vague: "went to ICU"
is a sharp fact in the discharge record. The trouble is **granularity** — the
attributes are too coarse to draw a boundary we already believe in. A fuzzy degree
would invent a gradient that is not there; a rough approximation measures the
ignorance the data actually has.
""")

ps.problem("A3", "A protocol, an amendment, and the price of deciding", 11, """
`A.SEPSIS_PROTOCOL` is the ED's sepsis bundle as Allen constraints between episodes
(Triage, Cultures, Antibiotics, Lactate, the one-hour Bundle window). The pharmacy
committee proposes `A.PROTOCOL_AMENDMENT`: start antibiotics *at* triage.

(a) Run `ch10.path_consistent` on the protocol and on protocol + amendment. Print what
the protocol **implies** for the Triage–Antibiotics pair, and set `amendment_conflict`
to the `empty_pair` reported for the amended network.

(b) Path consistency is sound but incomplete. Implement a complete decision procedure
`satisfiable(constraints, nodes=None) -> (bool, explored)`: build the network, run path
consistency, and if every label is a singleton stop (path consistency decides atomic
Allen networks); otherwise pick an undecided pair with the fewest candidate relations,
try each relation in turn on a **copy**, and recurse. `explored` counts the networks
visited (the root included). Do not mutate the caller's constraints.

(c) Show that `A.PC_BLIND_SPOT` is accepted by path consistency and rejected by your
procedure.

(d) Measure the price: for `n` in 3…8 intervals and label sizes `k` in (3, 5, 7), draw
10 random complete networks each (`random.Random(1000 * n + k)`, each label a
`rng.sample(ch10.ALLEN_RELATIONS, k)`), and build `a3` with columns `n`, `k`,
`satisfiable_rate`, `mean_explored`, `max_explored`, `pc_blind` (networks path
consistency accepted but `satisfiable` rejected). Keep the cell under 10 s.

(e) In writing: the price list says temporal reasoning costs **high**, yet path
consistency is only cubic. Reconcile the two using (c) and (d). What should the ED do
about the amendment, and what does a `"consistent": true` from a path-consistency tool
actually license an agent to say?
""", auto_points=5)
ps.todo(
    stub="""
    amendment_conflict = None    # TODO (a)

    def satisfiable(constraints, nodes=None):
        # TODO (b): backtracking over relations + path consistency; return (bool, explored)
        raise NotImplementedError

    a3 = None                    # TODO (d)
    """,
    solution="""
    def network_of(constraints, nodes=None):
        nodes = tuple(sorted(nodes or {n for pair in constraints for n in pair}))
        return ch10.Network.complete(nodes, {k: set(v) for k, v in constraints.items()})

    protocol = network_of(A.SEPSIS_PROTOCOL)
    print("protocol:", ch10.path_consistent(protocol))
    print("  implied Triage-Antibiotics:", sorted(protocol.get("Triage", "Antibiotics")))
    amended = network_of({**A.SEPSIS_PROTOCOL, **A.PROTOCOL_AMENDMENT})
    verdict_amended = ch10.path_consistent(amended)
    print("amended :", verdict_amended)
    amendment_conflict = verdict_amended["empty_pair"]

    def satisfiable(constraints, nodes=None):
        explored = 0

        def search(net):
            nonlocal explored
            explored += 1
            if not ch10.path_consistent(net)["consistent"]:
                return False
            open_pairs = [key for key, label in net.labels.items() if len(label) > 1]
            if not open_pairs:
                return True          # atomic + path-consistent => satisfiable
            key = min(open_pairs, key=lambda k: (len(net.labels[k]), k))
            for relation in sorted(net.labels[key]):
                child = ch10.Network(net.nodes, dict(net.labels))
                child.labels[key] = frozenset([relation])
                if search(child):
                    return True
            return False

        return search(network_of(constraints, nodes)), explored

    print("blind spot: path consistency says",
          ch10.path_consistent(network_of(A.PC_BLIND_SPOT))["consistent"],
          "| satisfiable says", satisfiable(A.PC_BLIND_SPOT))

    rows = []
    t0 = time.perf_counter()
    for n in range(3, 9):
        nodes = tuple(f"I{i}" for i in range(n))
        for k in (3, 5, 7):
            rng = random.Random(1000 * n + k)
            results, blind = [], 0
            for _ in range(10):
                cons = {pair: set(rng.sample(ch10.ALLEN_RELATIONS, k))
                        for pair in itertools.combinations(nodes, 2)}
                sat, explored = satisfiable(cons, nodes)
                pc = ch10.path_consistent(network_of(cons, nodes))["consistent"]
                blind += int(pc and not sat)
                results.append((sat, explored))
            rows.append({"n": n, "k": k,
                         "satisfiable_rate": sum(s for s, _ in results) / 10,
                         "mean_explored": sum(e for _, e in results) / 10,
                         "max_explored": max(e for _, e in results), "pc_blind": blind})
    a3 = pd.DataFrame(rows)
    print(f"{time.perf_counter() - t0:.1f}s")
    a3.pivot(index="n", columns="k", values=["satisfiable_rate", "mean_explored", "max_explored"])
    """)
ps.check("A3", """
_net = lambda c: ch10.Network.complete(tuple(sorted({x for p in c for x in p})),
                                       {k: set(v) for k, v in c.items()})
_amended = {**A.SEPSIS_PROTOCOL, **A.PROTOCOL_AMENDMENT}
assert amendment_conflict == ch10.path_consistent(_net(_amended))["empty_pair"]
assert set(amendment_conflict.split("-")) == {"Antibiotics", "Triage"}
_before = {k: set(v) for k, v in A.SEPSIS_PROTOCOL.items()}
assert satisfiable(A.SEPSIS_PROTOCOL)[0] is True
assert {k: set(v) for k, v in A.SEPSIS_PROTOCOL.items()} == _before, "do not mutate the input"
assert satisfiable(_amended)[0] is False
assert ch10.path_consistent(_net(A.PC_BLIND_SPOT))["consistent"]
assert satisfiable(A.PC_BLIND_SPOT)[0] is False, "the blind spot has no model"
for req in A.REQUIREMENTS:          # every temporal witness has a concrete timeline
    if req.witness[0] == "allen":
        assert satisfiable(req.witness[1])[0] is True, req.id
_rng = random.Random(7)             # atomic networks read off concrete intervals
_iv = {f"I{i}": tuple(sorted(_rng.sample(range(12), 2))) for i in range(5)}
_atomic = {(a, b): {ch10.relation_between(_iv[a], _iv[b])}
           for a, b in itertools.combinations(sorted(_iv), 2)}
assert satisfiable(_atomic) == (True, 1)
assert satisfiable({("A", "B"): {"b"}, ("B", "C"): {"b"}, ("A", "C"): {"bi"}})[0] is False
assert isinstance(a3, pd.DataFrame) and set(a3["n"]) == set(range(3, 9)) and set(a3["k"]) == {3, 5, 7}
assert {"satisfiable_rate", "mean_explored", "max_explored", "pc_blind"} <= set(a3.columns)
assert (a3.mean_explored >= 1).all() and a3.satisfiable_rate.between(0, 1).all()
""")
ps.written("""
**The protocol** is consistent, and propagation *infers* something nobody wrote down:
Triage–Antibiotics narrows to `{b}` — antibiotics can only start strictly after
triage ends, because cultures sit between them — and the cultures are forced *inside*
the bundle window (Bundle–Cultures narrows to `{di}`). **The amendment** ("antibiotics at triage": `s`,
`si` or `eq`) empties exactly that label in one round. The committee's proposal
contradicts "cultures before antibiotics", and the engine says so with a witness (the
emptied pair). The ED must choose: keep cultures-first (and reject the amendment), or
allow antibiotics before cultures in septic shock and *weaken* the cultures constraint
for that case — a clinical decision, surfaced by the tool, not made by it.

**Reconciling "cubic" with "high".** Path consistency is polynomial (O(n³) per round),
but it is only a *filter*: sound for inconsistency, incomplete for consistency. The
blind spot in (c) is a four-interval network it accepts and that has no model. Deciding
consistency of a general (disjunctive) Allen network is NP-complete; the complete
procedure in (b) is backtracking with path consistency at every node, and its cost is
the number of nodes explored. In the table, the typical random instance is cheap
(with `k = 3` most networks from n = 5 up die at the root; with `k = 7` they are all
satisfiable after ~15 nodes at n = 8, for 28 pairs), and `mean_explored` grows with
`n` and `k`; in between (`k = 5`, n = 7–8) sits the mixed region where the search has
to work hardest per instance. The
worst case is exponential in the number of pairs; random instances rarely hit it, which
is why "typical cases were fast" is not a pricing argument. Your run's blind-spot count
is likely 0 — incompleteness is rare on random networks, and that is exactly why it
goes unnoticed in testing.

**What the tool licenses.** `"consistent": true` from path consistency means "no
contradiction was found by local propagation" — not "a schedule exists". An agent may
say "no conflict detected; not proven satisfiable", and must either run the complete
procedure or exhibit a concrete timeline (as every temporal witness in the backlog does)
before it says "consistent". That asymmetry comes back in D2.
""")

# =========================================================================== #
ps.part("B", "Grade the choice and its price, then ask Claude", """
The advisor answers two things per requirement — the formalism and its reasoning cost —
and is graded on both. The guidelines a scorer can report are in `A.FORMALISM_RULEBOOK`:
""")
ps.code("""
for rule in A.FORMALISM_RULEBOOK:
    print(f"{rule.id:34s} {rule.description[:90]}")
print()
print("price list:", A.EXPRESSIVITY_COST)
""")

ps.problem("B1", "A scorer that charges for expressivity", 14, """
Implement `formalism_scorer(gold, pred) -> ev.ScoreReport`, where `gold` is a dataset
row (`gold.gold_formalism`, `gold.gold_cost`) and `pred` has `formalism` and `cost`.
First **normalise** each field: `str`, lower-case, strip whitespace and the characters
`` "'`*.: `` from both ends. Then:

| outcome | score | `violated` |
|---|---|---|
| formalism not one of `A.FORMALISMS` | 0.0 | `["answer-with-a-label"]` |
| right formalism, right cost | 1.0 | `[]` |
| right formalism, cost wrong (or not a cost level) | 0.6 | `["price-the-expressivity"]` |
| wrong formalism, cost = the price of **its own** choice | 0.2 | `[RULE_FOR[gold]]` |
| wrong formalism, cost not the price of its own choice | 0.0 | `[RULE_FOR[gold], "price-the-expressivity"]` |

`RULE_FOR` maps each formalism to its rule (`temporal-for-interval-relations`, …).
`notes` must state what was produced, what was intended and why
(`A.FORMALISM_WHY[gold]`); add a note mentioning the word **threshold** when a fuzzy
requirement was answered *crisp* (the §10.2 failure), and one mentioning
**over-engineer** when a crisp requirement was answered with anything else (paying
reasoning cost for nothing). Those notes are what GEPA will read.

Why grade the cost against the gold formalism's price, and why give 0.2 to a wrong
choice that is at least *priced consistently*? Answer in one paragraph.
""", auto_points=11)
ps.todo(
    stub="""
    RULE_FOR = {}    # TODO: formalism -> rule id

    def normalise(value) -> str:
        # TODO
        raise NotImplementedError

    def formalism_scorer(gold, pred) -> ev.ScoreReport:
        # TODO: the five outcomes from the table, with diagnostic notes
        raise NotImplementedError
    """,
    solution="""
    RULE_FOR = {"temporal": "temporal-for-interval-relations",
                "fuzzy": "fuzzy-for-vague-predicates",
                "rough": "rough-for-indiscernible-data",
                "crisp": "crisp-when-boundaries-are-sharp"}

    def normalise(value) -> str:
        return str(value if value is not None else "").strip().strip("\\"'`*.: ").strip().lower()

    def formalism_scorer(gold, pred) -> ev.ScoreReport:
        formalism = normalise(getattr(pred, "formalism", ""))
        cost = normalise(getattr(pred, "cost", ""))
        want_f, want_c = gold.gold_formalism, gold.gold_cost
        if formalism not in A.FORMALISMS:
            return ev.ScoreReport(0.0, [f"Formalism {formalism!r} is not one of "
                                        f"{', '.join(A.FORMALISMS)}; answer with the label only."],
                                  ["answer-with-a-label"])
        if formalism == want_f:
            if cost == want_c:
                return ev.ScoreReport(1.0, [f"Right: {want_f}, cost {want_c}."], [])
            return ev.ScoreReport(0.6, [f"Right formalism ({want_f}), but cost {cost!r}; "
                                        f"reasoning with {want_f} costs {want_c}."],
                                  ["price-the-expressivity"])
        notes = [f"Formalism wrong: answered {formalism!r}, intended {want_f!r} -- "
                 f"{A.FORMALISM_WHY[want_f]}."]
        if want_f == "fuzzy" and formalism == "crisp":
            notes.append("  A crisp threshold on a vague predicate is confidently wrong "
                         "exactly at the boundary, where the decision is hard.")
        if want_f == "crisp":
            notes.append(f"  Over-engineered: {formalism} costs "
                         f"{A.EXPRESSIVITY_COST[formalism]} reasoning for a sharp requirement "
                         f"that crisp handles at no cost.")
        violated = [RULE_FOR[want_f]]
        if cost == A.EXPRESSIVITY_COST[formalism]:
            notes.append(f"  (Cost {cost!r} is the right price for {formalism}.)")
            return ev.ScoreReport(0.2, notes, violated)
        notes.append(f"  Cost {cost!r} is not even the price of {formalism} "
                     f"({A.EXPRESSIVITY_COST[formalism]}).")
        return ev.ScoreReport(0.0, notes, violated + ["price-the-expressivity"])
    """)
ps.check("B1", """
fuzzy_gold = next(ex for ex in dev if ex.id == "fast-heart-rate")
crisp_gold = next(ex for ex in dev if ex.id == "ward-capacity")
P = lambda f, c: dspy.Prediction(formalism=f, cost=c)
cases = [
    (fuzzy_gold, "fuzzy", "low", 1.0, []),
    (fuzzy_gold, " Fuzzy", "Low.", 1.0, []),
    (fuzzy_gold, "**fuzzy**", "`low`", 1.0, []),
    (fuzzy_gold, "fuzzy", "none", 0.6, ["price-the-expressivity"]),
    (fuzzy_gold, "fuzzy", "cheap", 0.6, ["price-the-expressivity"]),
    (fuzzy_gold, "crisp", "none", 0.2, ["fuzzy-for-vague-predicates"]),
    (fuzzy_gold, "rough", "low", 0.2, ["fuzzy-for-vague-predicates"]),
    (fuzzy_gold, "crisp", "high", 0.0, ["fuzzy-for-vague-predicates", "price-the-expressivity"]),
    (fuzzy_gold, "fuzzy logic", "low", 0.0, ["answer-with-a-label"]),
    (fuzzy_gold, "", "", 0.0, ["answer-with-a-label"]),
    (fuzzy_gold, None, None, 0.0, ["answer-with-a-label"]),
    (crisp_gold, "crisp", "none", 1.0, []),
    (crisp_gold, "temporal", "high", 0.2, ["crisp-when-boundaries-are-sharp"]),
]
for gold, f, c, score, violated in cases:
    r = formalism_scorer(gold, P(f, c))
    assert abs(r.score - score) < 1e-9 and r.violated == violated, (gold.id, f, c, r.score, r.violated)
    assert all(v in A.FORMALISM_RULEBOOK for v in r.violated)
assert set(RULE_FOR) == set(A.FORMALISMS) and all(v in A.FORMALISM_RULEBOOK for v in RULE_FOR.values())
r = formalism_scorer(fuzzy_gold, P("crisp", "none"))
assert any("threshold" in n.lower() for n in r.notes)
assert any("fuzzy" in n for n in r.notes), "say what was intended"
r = formalism_scorer(crisp_gold, P("temporal", "high"))
assert any("over-engineer" in n.lower() for n in r.notes)
""")
ps.written("""
The cost field grades whether the advisor knows **what the ED will pay** for the
recommendation. Graded against the gold formalism's price, a correct cost with a wrong
formalism is not rewarded twice: the price that matters is the price of the model the
ED should build. Graded only against its own choice, the cost field would reward any
internally consistent answer — including "temporal / high" for everything, which is
exactly the over-engineering this chapter warns about.

The 0.2 for a wrong-but-consistently-priced choice is a *gradient*, not a reward for
being wrong: it separates an advisor that has learned the price list (and got one
choice wrong) from one that answers labels at random, so GEPA's feedback can say "your
pricing is fine, your choice is not" and the optimiser does not unlearn the pricing
while fixing the choice. It stays well below the 0.6 for a right choice with a wrong
price, because a wrong formalism is the more expensive error in production.
""")

ps.problem("B2", "The advisor as a DSPy program", 6, """
Write a signature `FormalismChoice` with input `requirement` and outputs `formalism`,
`cost` and `justification`, and a factory `FormalismAdvisor(instruction)` returning a
`dspy.Module` with a single `dspy.Predict` whose instruction is `instruction`. The field
descriptions are part of the prompt (manual marks): say which labels are allowed. Then
configure Claude and run the program once on `train[0]`.
""", auto_points=3)
ps.todo(
    stub="""
    BASELINE_INSTRUCTION = "You are a knowledge engineer. Choose a representation for the requirement, and price it."

    # TODO: class FormalismChoice(dspy.Signature): ...
    # TODO: def FormalismAdvisor(instruction=BASELINE_INSTRUCTION): ...

    lm = llm.configure_dspy()
    smoke = None     # TODO: FormalismAdvisor()(**train[0].inputs())
    """,
    solution="""
    BASELINE_INSTRUCTION = "You are a knowledge engineer. Choose a representation for the requirement, and price it."

    class FormalismChoice(dspy.Signature):
        \"\"\"Choose the formalism an ontology requirement needs, and state its reasoning cost.\"\"\"

        requirement: str = dspy.InputField(desc="one requirement from the ED's backlog, in English")
        formalism: str = dspy.OutputField(
            desc="exactly one label: crisp, fuzzy, rough or temporal")
        cost: str = dspy.OutputField(
            desc="the reasoning cost of that formalism: exactly one of none, low, high")
        justification: str = dspy.OutputField(
            desc="one sentence: which feature of the requirement decides the choice")

    def FormalismAdvisor(instruction: str = BASELINE_INSTRUCTION):
        class _Advisor(dspy.Module):
            def __init__(self):
                super().__init__()
                self.choose = dspy.Predict(FormalismChoice.with_instructions(instruction))

            def forward(self, requirement: str):
                return self.choose(requirement=requirement)

        return _Advisor()

    lm = llm.configure_dspy()
    smoke = FormalismAdvisor()(**train[0].inputs())
    print(train[0].requirement, "->", smoke.formalism, "/", smoke.cost, "|", smoke.justification)
    """)
ps.check("B2", """
assert set(FormalismChoice.input_fields) == {"requirement"}
assert {"formalism", "cost", "justification"} <= set(FormalismChoice.output_fields)
program = FormalismAdvisor("custom instruction")
assert len(list(program.named_predictors())) == 1
assert opt.instruction_of(program) == "custom instruction"
assert isinstance(smoke.formalism, str) and smoke.formalism.strip()
""")

ps.problem("B3", "Baseline on the development split, with a confusion matrix", 8, """
Run the baseline advisor on `dev` inside `llm.meter(lm)` (store the cost in
`baseline_dev_cost`) and collect `b3` with columns `id`, `gold`, `predicted`
(normalised), `cost` (normalised), `score` and `violated` from your scorer. Print the
mean and `pd.crosstab(b3.gold, b3.predicted)`.

Then write the **error analysis**: which confusions occur (crisp ↔ fuzzy on
"under 16" / "at most 24"? rough ↔ fuzzy on "coarse" data?), which items lose only the
price, and whether each error is a *choice* error or a *pricing* error — they call for
different fixes.
""", auto_points=3)
ps.todo(
    stub="""
    # TODO: b3 = ..., baseline_dev_cost = ...
    """,
    solution="""
    rows = []
    with llm.meter(lm) as baseline_dev_cost:
        baseline = FormalismAdvisor()
        for ex in dev:
            pred = baseline(**ex.inputs())
            report = formalism_scorer(ex, pred)
            rows.append({"id": ex.id, "gold": ex.gold_formalism,
                         "predicted": normalise(pred.formalism), "cost": normalise(pred.cost),
                         "score": report.score, "violated": report.violated})
    b3 = pd.DataFrame(rows)
    print(f"dev mean {b3.score.mean():.3f} on n={len(b3)};  cost {baseline_dev_cost}")
    print(pd.crosstab(b3.gold, b3.predicted))
    b3
    """)
ps.check("B3", """
assert isinstance(b3, pd.DataFrame) and len(b3) == len(dev) == 8
assert list(b3["id"]) == [ex.id for ex in dev]
for r, ex in zip(b3.itertuples(), dev):
    again = formalism_scorer(ex, dspy.Prediction(formalism=r.predicted, cost=r.cost))
    assert abs(again.score - r.score) < 1e-9, "score must be the scorer's verdict on the row"
assert {"calls", "usd"} <= set(baseline_dev_cost)
""")
ps.written("""
Describe *your* run; a typical baseline with this weak instruction shows:

* **Temporal and fuzzy** items are usually chosen correctly — "while fasting", "a long
  time", "fast heart rate" are strong cues — but the **cost** field is where the
  baseline bleeds: without the price list it often answers "low" or "medium" for
  temporal, or "none" for fuzzy. These are *pricing* errors (0.6), fixed by stating the
  price list — not by teaching the formalisms.
* **Rough** items are the hardest choice: "identical codes, different diagnoses" is
  sometimes answered *fuzzy* ("uncertain") or *crisp* ("classify"). That is a genuine
  *choice* error: vagueness and granularity are both "uncertainty" in everyday English.
* **Crisp** items with numbers ("at most 24 beds", "allergic") are sometimes
  over-engineered to fuzzy, or the model answers "none" correctly but with a hedging
  justification. Look for over-engineering: it is the error that costs the ED the most
  reasoning time.

Cost: 8 calls, well under a dollar; this is the unit price for every later comparison.
With n = 8 (two per formalism) a single error moves the mean by up to 0.125 — do not
read much into a difference of one item.
""")

# =========================================================================== #
ps.part("C", "Optimise with GEPA — and report it honestly", """
The rules: **optimise on `train`, select on `dev`, report on `test`**, and put a cost and
a noise estimate next to every number.
""")

ps.problem("C1", "A budgeted GEPA run with a held-out report", 10, """
1. Build the GEPA feedback metric from your scorer and `A.FORMALISM_RULEBOOK`, and a
   separate reflection LM (`llm.reflection_lm()`).
2. Run `opt.run_gepa` on `train` with `valset=dev` and `max_metric_calls=GEPA_BUDGET`
   inside `llm.meter(lm, reflect)`; store the cost in `gepa_cost` and the program in
   `tuned`.
3. Compare baseline and tuned on **`test`** with `opt.compare` (store as `c1`) and
   print `c1.report()`.
4. Save the tuned instruction to `config.artifacts_dir() /
   "ch10_formalism_advisor_instruction.txt"`.

In writing: read the instruction diff. Did GEPA write down the price list? Which
guidelines did it *not* learn, and was each of them ever violated on `train`? (A rule
for behaviour the model already has is never learned — that is not a failure.)
""", auto_points=4)
ps.todo(
    stub="""
    GEPA_BUDGET = 60
    # TODO: gepa_metric, reflect, tuned (inside llm.meter -> gepa_cost), c1, save the instruction
    instruction_path = config.artifacts_dir() / "ch10_formalism_advisor_instruction.txt"
    """,
    solution="""
    GEPA_BUDGET = 60
    gepa_metric = ev.make_gepa_metric(formalism_scorer, A.FORMALISM_RULEBOOK)
    reflect = llm.reflection_lm()
    with llm.meter(lm, reflect) as gepa_cost:
        tuned = opt.run_gepa(FormalismAdvisor(), train, gepa_metric, valset=dev,
                             max_metric_calls=GEPA_BUDGET, reflection_lm=reflect)
    c1 = opt.compare(FormalismAdvisor(), tuned, test, formalism_scorer)
    print(c1.report())
    print("GEPA cost:", gepa_cost)

    instruction_path = config.artifacts_dir() / "ch10_formalism_advisor_instruction.txt"
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
Look for three things (your wording will differ):

* **The price list.** Because every pricing error produces a
  `VIOLATED GUIDELINE price-the-expressivity` line that *spells out* none / low / high,
  a good run writes the price list into the instruction almost verbatim. This is the
  single biggest and most reliable gain, and it is a *format/knowledge* fix.
* **Rules not learned.** Rules whose behaviour Claude already has on `train` are never
  violated, so GEPA never sees them — typically `temporal-for-interval-relations` (the
  cues are strong) and often `crisp-when-boundaries-are-sharp`. Check each missing rule
  against the train violation histogram before calling it a failure: a rule that was
  never violated had nothing to teach. It becomes a real gap only if a *test* item
  needs it (e.g. "Each patient is assigned exactly one of the five MTS categories" read
  as vague).
* **Over-fitting.** Phrases that quote training items ("identical field values",
  "under 16") are memorised; they help test only where test reuses the cue.

A test delta near zero, or within the noise of C3, is a legitimate result.
""")

ps.problem("C2", "Score the choice only — and see what it learns about cost", 8, """
Implement `choice_only_scorer(gold, pred)`: 1.0 for the right formalism, else 0.0, with
the same `answer-with-a-label` / `RULE_FOR[gold]` violations as B1 and no cost
component. Run a second GEPA (`max_metric_calls=40`) against it — `blind` — inside
`llm.meter` (`blind_cost`).

Build `c2` with one row per program (`"baseline"`, `"gepa_full"`, `"gepa_choice_only"`)
and columns `test_full` (mean under `formalism_scorer`), `test_choice_only` (mean under
`choice_only_scorer`), `priced_rate` (fraction of test items **without** a
`price-the-expressivity` violation under the full scorer) and `optimisation_usd`.
Evaluating the same program twice costs nothing extra: DSPy serves the second pass from
its cache.

In writing: what did the choice-only optimiser learn about cost, and what does this say
about what a metric has to contain?
""", auto_points=4)
ps.todo(
    stub="""
    def choice_only_scorer(gold, pred) -> ev.ScoreReport:
        # TODO
        raise NotImplementedError

    c2 = None     # TODO
    """,
    solution="""
    def choice_only_scorer(gold, pred) -> ev.ScoreReport:
        formalism = normalise(getattr(pred, "formalism", ""))
        if formalism not in A.FORMALISMS:
            return ev.ScoreReport(0.0, [f"Not a label: {formalism!r}."], ["answer-with-a-label"])
        if formalism == gold.gold_formalism:
            return ev.ScoreReport(1.0, ["Right formalism."], [])
        return ev.ScoreReport(0.0, [f"Answered {formalism!r}, intended {gold.gold_formalism!r} -- "
                                    f"{A.FORMALISM_WHY[gold.gold_formalism]}."],
                              [RULE_FOR[gold.gold_formalism]])

    blind_metric = ev.make_gepa_metric(choice_only_scorer, A.FORMALISM_RULEBOOK)
    with llm.meter(lm, reflect) as blind_cost:
        blind = opt.run_gepa(FormalismAdvisor(), train, blind_metric, valset=dev,
                             max_metric_calls=40, reflection_lm=reflect)

    rows = []
    for name, program, spent in [("baseline", FormalismAdvisor(), 0.0),
                                 ("gepa_full", tuned, gepa_cost["usd"]),
                                 ("gepa_choice_only", blind, blind_cost["usd"])]:
        full = ev.evaluate_dataset(program, test, formalism_scorer)
        choice = ev.evaluate_dataset(program, test, choice_only_scorer)
        priced = sum("price-the-expressivity" not in r["violated"] for r in full["rows"]) / full["n"]
        rows.append({"program": name, "test_full": full["mean_score"],
                     "test_choice_only": choice["mean_score"], "priced_rate": priced,
                     "optimisation_usd": spent,
                     "instruction_chars": len(opt.instruction_of(program))})
    c2 = pd.DataFrame(rows)
    print(opt.instruction_of(blind)[:600])
    c2
    """)
ps.check("C2", """
_g = next(ex for ex in dev if ex.id == "sepsis-audit")
_P = lambda f, c="": dspy.Prediction(formalism=f, cost=c)
assert choice_only_scorer(_g, _P("Rough", "high")).score == 1.0
assert choice_only_scorer(_g, _P("rough")).violated == []
r = choice_only_scorer(_g, _P("fuzzy", "low"))
assert r.score == 0.0 and r.violated == ["rough-for-indiscernible-data"]
assert choice_only_scorer(_g, _P("rough sets")).violated == ["answer-with-a-label"]
assert isinstance(c2, pd.DataFrame)
assert set(c2["program"]) == {"baseline", "gepa_full", "gepa_choice_only"}
assert {"test_full", "test_choice_only", "priced_rate", "optimisation_usd"} <= set(c2.columns)
assert c2.priced_rate.between(0, 1).all() and c2.test_full.between(0, 1).all()
assert c2.set_index("program").loc["baseline", "optimisation_usd"] == 0
""")
ps.written("""
The choice-only metric never produces a `price-the-expressivity` line, so its
feedback contains nothing about cost and GEPA has nothing to write down: the
choice-only instruction typically improves (or keeps) `test_choice_only` while its
`priced_rate` stays at the baseline's level. On the metric it saw it looks as good as
the full run; on the thing the ED actually needs — "what will this cost us to reason
with?" — it learned nothing. If a live run shows the choice-only program pricing well
anyway, that is Claude's prior knowledge (the price list is standard), not the
optimiser: check the instruction text, not just the score.

The lesson generalises: **an optimiser learns exactly what the metric pays for**. If
the cost of the recommendation is part of what makes it good, it has to be in the
score; otherwise an advisor judged only on correctness will buy correctness with
expressivity, and look perfect in the report while doing it. Note also the invoice:
the second GEPA run is roughly two-thirds the cost of the first and the evaluation is
free thanks to caching — optimisation cost belongs in the comparison table.
""")

ps.problem("C3", "Is the difference bigger than the noise?", 6, """
With caching **disabled** (`fresh = llm.dspy_lm(cache=False)` and
`with dspy.context(lm=fresh): ...`), run the baseline and `tuned` on `test` three times
each under `formalism_scorer`; store the means in
`runs = {"baseline": [..3..], "gepa": [..3..]}`, the cost in `c3_cost`, and set
`verdict_c3` to `"significant"` if
`|mean_gepa - mean_baseline| > 2 * max(sd_gepa, sd_baseline)`, else
`"not significant"`. In writing: what does this say about C1, and what would a credible
evaluation need?
""", auto_points=3)
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
                ev.evaluate_dataset(FormalismAdvisor(), test, formalism_scorer)["mean_score"])
            runs["gepa"].append(ev.evaluate_dataset(tuned, test, formalism_scorer)["mean_score"])
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
Two things can happen, and both must be reported as they are. If the price list was the
baseline's main loss, the gap is large (pricing errors cost 0.4 each) and stable, and
the verdict is "significant" even with n = 8 — the improvement is real *and* it is
mostly a format/knowledge fix a hand-written instruction would also get. If the
baseline already priced well, the gap is one item or less and the sd of three runs is
of the same size: "not significant", and C1's delta is not evidence.

Either way, 3 × 8 is a crude estimate (a zero sd from three identical runs does not
mean zero noise). A credible evaluation needs more items per formalism, repeated runs
reported as mean ± sd or a paired bootstrap over items, identical sampling settings for
both programs, and the cost of each run. The sentence for Dr. Okafor: "the tuned
advisor changed the mean test score by X ± Y over 3 runs of 8 items, at $Z" — not
"GEPA improved accuracy by X".
""")

# =========================================================================== #
ps.part("D", "A review agent that runs the engine, and the price of the search", """
The DSPy advisor sees only the English. In practice a requirement arrives with data — a
measure and its observed values, a table and a target set, or proposed interval
constraints — and the right formalism is the one the **data** demonstrates. The review
agent's tools (`A.build_review_tools`) wrap the engine; your job is the agent, its output
contract and its evaluation.
""")
ps.code("""
ws_demo = A.ReviewWorkspace()
demo = {t.name: t for t in A.build_review_tools(ws_demo)}
for name, t in demo.items():
    print(f"{name:28s} {t.description.splitlines()[0]}")
print()
print(demo["get_requirement"].invoke({"requirement_id": "icu-from-triage"}))
print(demo["rough_report"].invoke({"table": "triage_log", "attributes": "acuity,arrival",
                                   "target_set": "icu"}))
print("trajectory:", ws_demo.log.names())
""")

ps.problem("D1", "Build and evaluate the requirements-review agent", 9, """
1. Write `REVIEW_PROMPT`. It must make the agent fetch the requirement's data, run the
   engine tool that tests its hypothesis (`fuzzy_degree` on the observed values,
   `rough_report` on the table — an empty boundary means *crisp* —,
   `check_temporal_consistency` on the constraints), price the choice with
   `expressivity_cost`, and end with a JSON object
   `{"formalism": ..., "cost": ..., "evidence": [...]}`.
2. Write `parse_review(text) -> dict` returning `{"formalism": ..., "cost": ...}`
   (normalised with your `normalise`) from the **last** JSON object in the text that
   has a `formalism` key — it may sit in a code fence or after prose — or
   `{"formalism": "unparseable", "cost": "unparseable"}`.
3. For every **test** requirement, build a fresh `A.ReviewWorkspace()`, its tools, an
   agent (`agents.build_agent(ws, system_prompt=..., tools=...)`) and run it with the
   task `"Review requirement <id>."`. Collect `d1` with columns `id`, `gold`,
   `predicted`, `cost`, `correct` (formalism and cost both right), `tool_calls`,
   `grounded` (the log contains the engine tool for the *predicted* formalism:
   fuzzy → `fuzzy_degree`, rough/crisp → `rough_report`, temporal →
   `check_temporal_consistency`) and `usd_estimate` (`llm.chat_usage(run.messages)`).

In writing: report accuracy with its n and cost per requirement, compare with the
text-only advisor on the same eight items (C1's `c1.after`), and examine every error and
every ungrounded answer. Is the agent worth ~10× the cost per item?
""", auto_points=4)
ps.todo(
    stub="""
    REVIEW_PROMPT = \"\"\"TODO\"\"\"

    def parse_review(text: str) -> dict:
        # TODO
        raise NotImplementedError

    ENGINE_TOOL = {}   # TODO: formalism -> the tool that demonstrates it
    d1 = None          # TODO: run the agent on every test requirement
    """,
    solution="""
    REVIEW_PROMPT = \"\"\"\\
    You review requirements for Northfield General's ED ontology. For the requirement
    you are given, decide which formalism it needs -- crisp, fuzzy, rough or temporal --
    and what that costs to reason with. Decide from the DATA, using the tools:

    1. get_requirement: read the text and the attached data.
    2. Test your hypothesis with the engine:
       - a measure with observed values -> fuzzy_degree on each value; a degree strictly
         between 0 and 1 means the predicate is vague (fuzzy);
       - a table, attributes and target set -> rough_report; a non-empty boundary means
         the data cannot decide membership (rough); an empty boundary means the codes
         decide it exactly (crisp);
       - interval constraints -> check_temporal_consistency (temporal). Path consistency
         is sound but incomplete: report "no conflict detected", not "proven consistent".
    3. expressivity_cost on the formalism you chose.

    End your reply with a JSON object and nothing after it:
    {"formalism": "crisp|fuzzy|rough|temporal", "cost": "none|low|high",
     "evidence": ["the tool results that decided it"]}
    \"\"\"

    def parse_review(text: str) -> dict:
        for blob in reversed(re.findall(r"\\{[^{}]*\\}", text or "")):
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "formalism" in data:
                return {"formalism": normalise(data.get("formalism")),
                        "cost": normalise(data.get("cost"))}
        return {"formalism": "unparseable", "cost": "unparseable"}

    ENGINE_TOOL = {"fuzzy": "fuzzy_degree", "rough": "rough_report", "crisp": "rough_report",
                   "temporal": "check_temporal_consistency"}

    rows = []
    for ex in test:
        ws = A.ReviewWorkspace()
        agent, _ = agents.build_agent(ws, system_prompt=REVIEW_PROMPT,
                                      tools=A.build_review_tools(ws))
        run = agents.run_agent(agent, ws, f"Review requirement {ex.id}.")
        review = parse_review(run.answer)
        names = ws.log.names()
        rows.append({"id": ex.id, "gold": ex.gold_formalism, "predicted": review["formalism"],
                     "cost": review["cost"],
                     "correct": review["formalism"] == ex.gold_formalism
                                and review["cost"] == ex.gold_cost,
                     "tool_calls": len(names),
                     "grounded": ENGINE_TOOL.get(review["formalism"]) in names,
                     "usd_estimate": llm.chat_usage(run.messages)["usd_estimate"]})
    d1 = pd.DataFrame(rows)
    print(f"correct {d1.correct.sum()}/{len(d1)}; grounded {d1.grounded.sum()}/{len(d1)}; "
          f"cost ≈ ${d1.usd_estimate.sum():.3f} total")
    d1
    """)
ps.check("D1", """
assert parse_review('{"formalism": "rough", "cost": "low", "evidence": []}') == {"formalism": "rough", "cost": "low"}
assert parse_review('Checked.\\n```json\\n{"formalism": "Temporal", "cost": "HIGH", "evidence": ["x"]}\\n```')["formalism"] == "temporal"
assert parse_review('{"degree": 0.5} then {"formalism": "fuzzy", "cost": "low"}')["cost"] == "low"
assert parse_review("I think it is crisp.")["formalism"] == "unparseable"
assert ENGINE_TOOL == {"fuzzy": "fuzzy_degree", "rough": "rough_report", "crisp": "rough_report",
                       "temporal": "check_temporal_consistency"}
assert isinstance(d1, pd.DataFrame) and list(d1["id"]) == [ex.id for ex in test]
assert {"id", "gold", "predicted", "cost", "correct", "tool_calls", "grounded",
        "usd_estimate"} <= set(d1.columns)
_gold_cost = {ex.id: ex.gold_cost for ex in test}
assert (d1["correct"] == ((d1["predicted"] == d1["gold"]) &
                          (d1["cost"] == d1["id"].map(_gold_cost)))).all()
assert d1["grounded"].map(lambda v: isinstance(v, (bool, np.bool_))).all()
""")
ps.written("""
Report it as "k/8 correct, g/8 grounded, ≈ $X per requirement" — not as a percentage.
With the procedure above a live run typically gets the temporal and fuzzy items right
with 3–5 tool calls. The instructive items are the **crisp/rough pair**: "Every ICU bed
has a ventilator connection point" and "Classify which past ED visits ended in emergency
surgery" both arrive as *a table and a target*, and only `rough_report` tells them
apart (boundary empty vs. all twelve visits undecidable). The text-only advisor has to
guess from wording; the agent can *see* it. If the agent answers one of them without
calling `rough_report` (grounded = False) and is right, it got lucky — tighten the
prompt, don't celebrate.

Compare with `c1.after["rows"]` on the same items: the agent should match or beat the
advisor on rough/crisp, and tie elsewhere. Its cost is an order of magnitude higher per
item (several model turns with tool results in context vs. one DSPy call). The honest
recommendation: use the cheap text-only advisor for triage of the backlog, and the
agent only where the text is ambiguous and data is attached — or where the answer must
be auditable, because the agent's evidence list is a record of *why*. When the live
model finishes without a JSON block, the row shows "unparseable": count it as wrong and
report it, since the output contract is part of the product.
""")

ps.problem("D2", "The price of the search: propagation as an MDP", 11, """
`A.PropagationMDP` models deciding a three-interval network: propagate through A, B or
C (each costs `cost`) or declare a verdict. A **justified** correct verdict earns +1; a
wrong or unjustified one costs `wrong_penalty`. Declaring *inconsistent* is justified
only once a label has emptied; with `require_check=True`, declaring *consistent* needs
at least one propagation.

The amendment from A3, restricted to Triage (A), Cultures (B), Antibiotics (C), is
provided below as `amended_kwargs`; the protocol's consistent chain as `chain_kwargs`.

1. Write `plan(M) -> (actions, value)`: solve `M` with `mdp.value_iteration`, roll out
   the greedy policy from the initial state, and return the action list and
   `V*(s0)`. Set `k` to the number of propagations in the optimal plan for the
   amendment at `cost=0.05`.
2. Derive the propagation cost `c*` above which the optimal agent stops proving
   inconsistency, as a function of `k` and the penalty `p`; implement
   `threshold(k, p)`. Verify it: for `p` in `[1.0, 2.0]`, sweep `cost` over
   `np.linspace(0.05, 3.0, 30)` and record in `d2` (columns `penalty`, `cost`,
   `proves`) whether the optimal plan propagates and ends in `declare:inconsistent`.
3. On the consistent chain, compare `require_check=False` and `True`: set
   `loose_plan, loose_value, strict_plan, strict_value`.

In writing: interpret `c*` as a solver time budget; explain why the loose reward is a
design flaw rather than a fact about temporal reasoning, and why even
`require_check=True` does not make "consistent" a proof (A3's blind spot). What reward
would?
""", auto_points=6)
ps.code("""
amended_kwargs = dict(ab={"b", "m"}, bc={"b", "m"}, ac={"eq", "s", "si"}, consistent=False)
chain_kwargs = dict(ab={"b"}, bc={"b"}, ac={"b"}, consistent=True)
M_demo = A.PropagationMDP(**amended_kwargs)
print("states:", len(M_demo.states()), " actions at s0:", M_demo.actions(M_demo.initial_state()))
""")
ps.todo(
    stub="""
    def plan(M):
        # TODO (1): (actions, V*(s0))
        raise NotImplementedError

    k = None                      # TODO (1)

    def threshold(k: int, p: float) -> float:
        # TODO (2)
        raise NotImplementedError

    d2 = None                     # TODO (2)
    loose_plan = loose_value = strict_plan = strict_value = None   # TODO (3)
    """,
    solution="""
    def plan(M):
        V, pi = mdp.value_iteration(M)
        episode = mdp.run_episode(M, mdp.greedy_policy(pi))
        return episode.actions, V[M.initial_state()]

    actions, value = plan(A.PropagationMDP(**amended_kwargs, cost=0.05))
    print("amendment:", actions, f"V*={value:.3f}")
    k = sum(a.startswith("propagate") for a in actions)

    def threshold(k: int, p: float) -> float:
        # prove: 1 - k*c ; skip the proof: any verdict is wrong or unjustified -> -p
        # prove iff 1 - k*c > -p  <=>  c < (1 + p) / k
        return (1 + p) / k

    rows = []
    for p in [1.0, 2.0]:
        for c in np.linspace(0.05, 3.0, 30):
            acts, _ = plan(A.PropagationMDP(**amended_kwargs, cost=float(c), wrong_penalty=p))
            rows.append({"penalty": p, "cost": round(float(c), 3),
                         "proves": any(a.startswith("propagate") for a in acts)
                                   and acts[-1] == "declare:inconsistent"})
    d2 = pd.DataFrame(rows)
    print(f"k = {k}; c* =", {p: threshold(k, p) for p in [1.0, 2.0]})
    print(d2.groupby("penalty").apply(lambda g: g[g.proves].cost.max()))

    loose_plan, loose_value = plan(A.PropagationMDP(**chain_kwargs))
    strict_plan, strict_value = plan(A.PropagationMDP(**chain_kwargs, require_check=True))
    print("consistency free to claim :", loose_plan, round(loose_value, 3))
    print("consistency must be earned:", strict_plan, round(strict_value, 3))
    """)
ps.check("D2", """
assert k == 1
assert abs(threshold(1, 1.0) - 2.0) < 1e-9 and abs(threshold(4, 2.0) - 0.75) < 1e-9
assert isinstance(d2, pd.DataFrame) and set(d2["penalty"]) == {1.0, 2.0}
for p, grp in d2.groupby("penalty"):
    c_star = threshold(k, p)
    clear = grp[(grp["cost"] - c_star).abs() > 0.06]
    assert (clear.proves == (clear["cost"] < c_star)).all(), f"sweep disagrees with c* at p={p}"
_M = A.PropagationMDP(**amended_kwargs)
_acts, _v = plan(_M)
assert _acts[-1] == "declare:inconsistent" and abs(_v - (1 - _M.cost)) < 1e-9
assert loose_plan == ["declare:consistent"] and abs(loose_value - 1.0) < 1e-9
assert any(a.startswith("propagate") for a in strict_plan) and strict_plan[-1] == "declare:consistent"
assert abs(strict_value - (1 - 0.05)) < 1e-9 and strict_value < loose_value
""")
ps.written("""
**The threshold.** Proving pays `1 − k·c`; skipping the proof pays `−p` whatever the
agent declares (a "consistent" verdict is wrong, an "inconsistent" one unjustified). So
the agent proves iff `c < (1 + p)/k`: with `k = 1`, `c* = 2` at `p = 1` and `c* = 3` at
`p = 2` (the sweep flips there; at `p = 2` it never stops proving within the range).
Read `c` as the solver's cost per propagation relative to the value of a correct
verdict: when the time budget makes a proof cost more than being wrong, a rational
solver stops proving — and on this network the *default* it then falls back to is
"consistent", the failure mode of a scheduler given too little time. On real protocols
`k` grows with the network (A3's explored counts), so `c*` falls: the penalty for
unverified answers is the design lever, and in a clinical protocol it should be large.

**The asymmetry.** With the loose reward, "consistent" is free (`V* = 1.0` with no
work) while "inconsistent" costs a propagation. That is a property of the reward, not
of temporal reasoning: an agent paid this way prefers the answer that needs no evidence,
and here that answer is "looks fine to me". `require_check=True` lowers the value to
`1 − c` — the honest number, reflecting the work a sound answer requires.

**Still not a proof.** A propagation that empties nothing only shows local
consistency; A3's blind spot is path-consistent and has no model. An honest reward for
"consistent" pays only for a **witness**: a concrete timeline that satisfies every
constraint (as each temporal item in the backlog carries), or a completed search (A3's
`satisfiable`), charged at its real cost — which is exactly why the price list says
temporal reasoning is **high**.
""")

if __name__ == "__main__":
    for path in ps.save(HERE, "04"):
        print("wrote", path.name)
