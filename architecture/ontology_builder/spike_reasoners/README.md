# Spike — a framework for several reasoners

Working reference implementation for `ontology_builder.reasoning`
(`OB.RSN.01`–`OB.RSN.04`, `OB.EXT.05`).

```bash
python -m pytest architecture/ontology_builder/spike_reasoners -q
# 25 passed
```

| File | Role |
|---|---|
| `backends.py` | `ReasonerCapabilities`, `ReasonerBackend`, `ReasonerSession`, `Answer`; three backends — RDFS, OWL 2 RL, JVM sidecar |
| `profile_check.py` | Which axioms fall outside a given OWL 2 profile — the input to routing |
| `router.py` | `ReasonerRouter` (policy, degradation, trace) and `differential()` |
| `test_reasoners.py` | 25 tests, run in this workstation's real condition: `owlrl` present, **no JVM** |

---

## The five decisions

### 1. Two levels: backend (cheap, describes itself) vs session (expensive, bound)

Straight from Protégé's `ProtegeOWLReasonerInfo`, which returns an
`OWLReasonerFactory` — the plugin contract is a *factory plus configuration*,
never a reasoner instance. The instance has its own lifecycle because
classifying FIBO takes seconds to minutes.

```python
backend  = OWLRLBackend()                 # singleton, registered by entry point
with backend.session(graph) as session:   # expensive; always closed
    session.unsatisfiable()
```

In a sidecar, `ReasonerSession` is what gets cached by `(project, revision)`.

### 2. Capabilities are declared, not discovered by failure

```python
ReasonerCapabilities(
    id="owlrl", complete_for=Profile.RL,
    operations={"classify","entails","materialise","satisfiability","consistency"},
    incremental=False, cost_class="polynomial", execution="in-process")
```

The important consequence: **`RDFSBackend` does not list `satisfiability`.** RDFS
has no notion of an unsatisfiable class, so the operation is *absent* rather
than returning a misleading "nothing is unsatisfiable". Asking for it raises.

Protégé does the same thing in two places — `getRecommendedBuffering()` lets the
reasoner declare how it wants changes fed to it, and `ReasonerPreferences`
toggles 18 separate inference types because not every reasoner supports every
one, and computing all of them is expensive.

### 3. Every answer carries how much it is worth

This is the piece Protégé leaves implicit — it assumes every plugged-in reasoner
is sound *and complete* for OWL 2 DL, so it never has to say which semantics
produced a result. We cannot assume that: the cheap backend is OWL 2 RL, which is
deliberately incomplete.

```python
Answer(value=set(), backend="owlrl", profile="RL",
       complete=False,
       caveat="5 axioms outside OWL 2 RL: qualifiedCardinality (exact) x5")
```

`Answer.is_definite` encodes the asymmetry that actually matters: these backends
are **sound but incomplete**, so a derived *yes* is always trustworthy, while a
*no* from outside the completeness envelope means only "I could not derive it".
Rendering that as a definite "no" is the single most dangerous thing a
multi-reasoner platform can do.

Run against a real FIBO module:

```
module : FBC/DebtAndEquities/Debt.rdf   (1029 triples)

  outside OWL 2 RDFS:  127   Restriction x80, someValuesFrom x37, allValuesFrom x4
  outside OWL 2 RL  :    5   qualifiedCardinality (exact) x5
  outside OWL 2 EL  :   46   minQualifiedCardinality x34, qualifiedCardinality x5
  outside OWL 2 DL  :    0

satisfiability -> owlrl
   set() [owlrl, RL] (incomplete: 5 axioms outside OWL 2 RL: qualifiedCardinality (exact) x5)
```

"No unsatisfiable classes — **but** don't rely on that, five axioms were beyond
me." That sentence is the whole point of the framework.

### 4. Routing policy is per operation, and declared

The tempting rule — "always use the most capable available reasoner" — is wrong.
For `materialise` over a whole project you want the polynomial backend even when
a DL reasoner is available; for `explain` you want the DL one even though it is
exponential. The trade-off differs per operation, so:

```python
DEFAULT_POLICY = RoutingPolicy(order={
    "materialise":    ("owlrl", "sidecar:elk", "sidecar:hermit", "rdfs"),
    "satisfiability": ("sidecar:hermit", "sidecar:elk", "owlrl"),
    "explain":        ("sidecar:hermit",),
}, budget_s={"materialise": 300.0, "explain": 30.0, "entails": 15.0})
```

Availability is checked **before** routing, so a missing runtime degrades
gracefully instead of raising inside a request. On this machine:

```
availability:
  owlrl            OK
  rdfs             OK
  sidecar:hermit   unavailable: required runtime 'java' is not on PATH
  sidecar:elk      unavailable: required runtime 'java' is not on PATH

satisfiability -> chose owlrl; skipped sidecar:hermit (required runtime 'java'
  is not on PATH); skipped sidecar:elk (…); skipped rdfs (does not support
  satisfiability)
```

Every decision is on the `RoutingTrace`. Log it, and attach it to agent output —
an agent that reports an entailment should be able to say which reasoner, under
which profile, and what it fell back from. Protégé's `ReasonerDiedException` and
`ReasonerStatus.OUT_OF_SYNC` exist because reasoners crash, hang and go stale;
`ReasonerError` and the degradation chain are the equivalent here.

### 5. Differential testing is what makes it trustworthy

Run the same question against every available backend and diff:

```python
diffs = differential([RDFSBackend(), OWLRLBackend()], graph, questions)
```

A `Disagreement` classifies itself:

* **expected** — at most one backend was complete for this graph, so a weaker
  one saying "no" where a stronger one says "yes" is the system working;
* **BUG** — two backends that both declared completeness disagree. Fail CI.

**This caught a real bug during the spike.** The RDFS backend claimed
`complete=True` on a graph using `owl:TransitiveProperty`, because
`outside_profile(..., "RDFS")` screened class expressions but had forgotten the
OWL property characteristics. RDFS entailment cannot chain a transitive
property; the harness surfaced the disagreement, the completeness claim was
wrong, and `profile_check.py` now flags all seven characteristic classes plus
`sameAs` / `equivalentProperty` / `propertyDisjointWith`. Without the harness
that would have shipped as a silent, confident wrong answer.

---

## Adding a reasoner

1. Subclass `ReasonerBackend`, declare `ReasonerCapabilities` honestly —
   especially `complete_for`, and *omit* operations you cannot answer
   meaningfully.
2. Implement `_session()` returning a `ReasonerSession`. Override only the
   operations where you beat the default closure-based implementations.
3. Register the entry point (`ontology_builder.reasoners`) — see `OB.EXT.01`.
4. Add it to the routing policy for the operations it should win.
5. Add it to the differential suite. If it disagrees with a complete backend, one
   of you is wrong.

---

## What is deliberately not here

* **Incremental reasoning.** `ReasonerCapabilities.incremental` is declared and
  unused. The real sidecar uses OWL API buffered changes plus `flush()` so small
  edits do not force a reclassify; wiring that to the change spine
  (`OB.CHG.01`) is P6 work.
* **The sidecar body.** `SidecarBackend` declares itself and correctly reports
  unavailable without a JVM — which is what the degradation tests exercise. The
  HTTP client, the `(project, revision)` session cache, memory budgets and the
  ELK-on-timeout fallback are the P6 build.
* **Justifications.** `explain` is declared only by `sidecar:hermit`, and the
  base session raises rather than faking it. There is no Python implementation
  of OWL justification, which is the substance of decision **D11**.
* **A real profile validator.** `profile_check.py` is a *screen*, sized for
  routing decisions. False positives push work to a stronger reasoner, which is
  safe. For a conformance-grade check, shell out to ROBOT.
