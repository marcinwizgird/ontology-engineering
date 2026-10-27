"""Structural slice tags per gold query (specification §4.4), derived from the gold SPARQL
and the schema, never from a model's output.

* ``hierarchy`` — ``superclass-union`` when a variable's most specific class has
  subclasses (Ontop unfolds it into a union of tables), else ``leaf``. The gold SPARQL
  also types a variable with every ancestor (``?x a Revenue . ?x a
  ElementOfFinancialStatement``); those redundant ancestors do not count;
* ``nesting``   — FIBEN's query type (non-nested, type-a, type-j, type-ja, type-n);
* ``hops``      — object-property triples in the query: ``0-1``, ``2`` or ``3+``;
* ``fan_trap``  — ``1:N-risk`` when the query sums, averages or counts (non-distinct) a
  value or an entity whose owner sits on the *one* side of a join, so joining to the
  *many* side can duplicate it; else ``functional``. A FIBEN object property is a foreign
  key on the subject's table, so ``?s p ?o`` is N:1 from ``?s`` to ``?o``: ``?o`` is the
  one side. MIN, MAX and COUNT(DISTINCT) are immune to duplicated rows.

Queries without an accepted gold SPARQL (outside the compiler ceiling) get ``unknown``
for the SPARQL-derived dimensions.

    python -m nl2q.evalkit.slices      # writes artifacts/eval/slices.json
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache

from .. import paths, schema, vkg_build

DIMENSIONS = ("hierarchy", "nesting", "hops", "fan_trap")
_TYPE = re.compile(r"(\?\w+)\s+a\s+fiben:(\w+)")
_TRIPLE = re.compile(r"(\?\w+)\s+fiben:(\w+)\s+(\?\w+)")
_AGG = re.compile(r"\b(?:COUNT|SUM|AVG)\s*\(\s*(\?\w+)", re.I)   # DISTINCT does not match


@lru_cache(maxsize=1)
def _schema_facts() -> tuple[set[str], set[str], dict[str, set[str]]]:
    """(classes that have subclasses, object-property local names, class -> its ancestors)."""
    s = schema.load()
    parent = {vkg_build.class_name(c): vkg_build.class_name(p) for c, p in s.subclass_edges}
    ancestors: dict[str, set[str]] = {}
    for c in parent:
        a, x = set(), c
        while x in parent:
            x = parent[x]
            a.add(x)
        ancestors[c] = a
    objects = {vkg_build.prop_name(f.column) for f in s.relation_fks}
    return set(parent.values()), objects, ancestors


def _most_specific(classes: set[str], ancestors: dict[str, set[str]]) -> set[str]:
    redundant = set().union(*(ancestors.get(c, set()) for c in classes))
    return classes - redundant


def tag(sparql: str | None, query_type: str) -> dict[str, str]:
    if not sparql:
        return {"hierarchy": "unknown", "nesting": query_type, "hops": "unknown", "fan_trap": "unknown"}
    supers, objects, ancestors = _schema_facts()
    types: dict[str, set[str]] = {}
    for var, cls in _TYPE.findall(sparql):
        types.setdefault(var, set()).add(cls)
    specific = set().union(*(_most_specific(c, ancestors) for c in types.values()))
    triples = _TRIPLE.findall(sparql)
    links = [(s, p, o) for s, p, o in triples if p in objects]
    one_side = {o for _, _, o in links}                        # referenced by some N:1 edge
    owner = {o: s for s, p, o in triples if p not in objects}  # value variable -> its subject
    risk = any(owner.get(v, v) in one_side for v in _AGG.findall(sparql)) if links else False
    hops = len(links)
    return {
        "hierarchy": "superclass-union" if specific & supers else "leaf",
        "nesting": query_type,
        "hops": "0-1" if hops <= 1 else "2" if hops == 2 else "3+",
        "fan_trap": "1:N-risk" if risk else "functional",
    }


@lru_cache(maxsize=1)
def by_sql_id() -> dict[int, dict[str, str]]:
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    return {r["sql_id"]: tag(r.get("sparql") if r.get("strict") else None, r["query_type"]) for r in rows}


def write() -> dict:
    tags = by_sql_id()
    out_dir = paths.ARTIFACTS / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "slices.json").write_text(json.dumps({str(k): v for k, v in sorted(tags.items())}, indent=1),
                                         encoding="utf-8")
    return {d: dict(Counter(t[d] for t in tags.values())) for d in DIMENSIONS}


if __name__ == "__main__":
    print(json.dumps(write(), indent=1))
