# Spike — VocBench 3's CRUDV capability algebra in Python

**Answer: yes, and it needs no Prolog engine and no dependencies.**
This directory is a working, tested port. It is the reference implementation for
`ontology_builder.governance.capabilities` (feature `OB.GOV.02`).

```bash
python -m pytest architecture/ontology_builder/spike_crudv -q
# 52 passed
```

| | |
|---|---|
| Implementation | `capabilities.py` — 520 lines, standard library only |
| Tests | `test_capabilities.py` — 52 tests |
| Warm decision | ~12 µs |
| Full decision path (parse → read-only check → admin → language → PDP) | ~16 µs |
| Dependency VocBench ships to do this in the browser | jsprolog |

---

## Why no Prolog engine is needed

VocBench evaluates authorization as Prolog because its policy is *written* as
Prolog — a `tbox` string in `AuthorizationEvaluator.ts`, parsed by tuProlog on
the server and jsprolog in the browser. But the policy it expresses is not a
general logic program:

* **fixed rule set** — the clauses are hard-coded in the source, not
  user-supplied. Only the *facts* (`capability/2`) vary per user.
* **bounded depth** — no clause is more than one derivation step from a
  `capability/2` fact. `chk_capability(rdf(_), C) :- chk_capability(rdf, C)` is
  the deepest chain, and it terminates immediately.
* **ground terms** — every argument is an atom or a one-argument atom like
  `lexicalization("en,fr")`. There are no free variables to bind and no
  structures to build.
* **no negation, no arithmetic, no recursion** — `subset/2` and `member/2` are
  list helpers that Python's `frozenset` and `<=` replace outright.

So each Prolog clause becomes one Python predicate, and `chk_capability` becomes
an ordered `any(...)` over them. The full derivation lives in
`CapabilitySet._derived_grants`, transcribed clause by clause with the original
Prolog quoted above each block.

---

## The three things that are easy to get wrong

Each has a dedicated test, and each was verified by mutation — breaking the rule
in a scratch copy and confirming the suite fails.

### 1. The CRUDV subset test runs on the *request*

```prolog
resolveCRUDV(CRUDVRequest, CRUDV) :- char_subset(CRUDVRequest, CRUDV).
```

Requested letters ⊆ granted letters. Invert it and a `"R"` grant satisfies a
`"CRUD"` request — every reader becomes an editor.

> Mutation `want <= c.ops` → `c.ops <= want`: **22 of 52 tests fail.**

### 2. `rdf(sparql, support)` is cut

```prolog
chk_capability(rdf(sparql,support), CRUDV) :-
    !, capability(rdf(sparql,support), CRUDV).
```

The `!` stops backtracking into the general rules, so a blanket `rdf` grant does
**not** confer SPARQL-endpoint access — it has to be granted explicitly. Drop
the cut and every power role silently gains raw endpoint access.

> Mutation removing the cut: **2 tests fail**, including
> `test_rdf_geek_has_sparql_support_and_others_do_not`.

### 3. `covered/2` is directional

```prolog
covered(objectProperty, property).
covered(Role, Role).
```

A grant on `property` covers `objectProperty`; a grant on `objectProperty` does
**not** cover `property`. Same for `skosOrderedCollection` → `skosCollection`.
Make it symmetric and a narrow grant silently widens.

> Mutation making it symmetric: **2 tests fail.**

A fourth, less dangerous but just as easy to miss: **grants themselves may
contain wildcards.** `capability(rdf(_,_), "R")` is a *fact* in the Prolog
database, so unification lets it satisfy any two-argument `rdf` goal. A port
that only walks the rule heads and forgets that stored grants unify too will
give the Lurker role nothing at all.

---

## What is modelled

| Prolog | Python |
|---|---|
| `auth/2` | `authorize()` / `CapabilitySet.authorize()` |
| `chk_capability/2` (all 24 clauses) | `CapabilitySet._derived_grants()` |
| `resolveCRUDV/2`, `char_subset/2`, `subset/2`, `member/2` | `frozenset.__le__` |
| `resolveLANG/2` | `_lang_ok()` |
| `covered/2` | `covered()` |
| `role/1` (18 facts) | `ROLES` |
| `vocabulary/2` (7 facts) | `VOCABULARY` |
| `capability/2` facts | `CapabilitySet.capabilities` |
| Term unification | `match()` |
| `authCache` | `CapabilitySet._cache` |

Plus the surrounding policy from `isGaolAuthorized`, which is *not* in the
Prolog and is just as load-bearing:

1. a **read-only project** blocks `C`/`U`/`D` on `rdf` goals — for everyone,
   administrators included;
2. anonymous subjects are denied;
3. administrators bypass the algebra entirely;
4. the **ProjectUserBinding's language list** is checked against the value's
   language tag *before* the capability check — this is where "may edit French
   labels only" is actually enforced;
5. `%resource_role%` is substituted from the resource being acted on, and it is
   an error for a goal to need it without one.

---

## Design choices where the port deviates deliberately

**One grant must carry every requested letter.** Prolog binds a single `CRUDV`
per solution, so `auth(rdf(xLabel), "CD")` needs one grant with both letters —
not a `C` grant plus an unrelated `D` grant. We keep that. Relaxing it would
quietly compose permissions their author never combined.
See `test_multi_letter_request_needs_one_grant_carrying_all_letters`.

**The client gets the grant set, not the engine.** VocBench ships jsprolog to
the browser and re-evaluates the same goals there. Instead, serialise the
resolved `CapabilitySet` for the current (user, project) and evaluate
`satisfies()` client-side — the same ~40 lines of matching logic in TypeScript,
no second policy engine, no chance of the two drifting.

**Roles are data.** `DEFAULT_ROLES` holds the eight VocBench roles as capability
expression strings. A Project Manager creating a ninth role writes the same
strings; nothing is compiled in. Role inheritance (WebProtégé's contribution) is
a resolution step over role names before the union — `role_grants()` already
takes several names and unions them.

---

## What is not here

* **Role inheritance resolution** — trivial (transitive closure over a parent
  map before `role_grants`), left out to keep the spike focused on the algebra.
* **Persistence** — grants live in `urn:ob:gov:users` per
  `../GOVERNANCE_FOUNDATION.md` §3.1; this spike takes them as strings.
* **The `@guarded` decorator and the unguarded-endpoint test** — those are
  `OB.GOV.11`, and they consume this module rather than being part of it.
* **`pm`/`um`/`sys`/`customService`/`invokableReporter` specific rules** — these
  areas have no roll-up clauses in VocBench's TBox beyond direct unification,
  which the generic path already handles. `rbac` and `cform` do have the
  bare-area roll-up, and it is implemented.
