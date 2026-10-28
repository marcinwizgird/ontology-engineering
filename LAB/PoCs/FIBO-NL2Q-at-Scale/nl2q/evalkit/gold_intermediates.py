"""Gate 2 oracles extracted from the accepted gold SPARQL (specification §5, Gate 2).

For every gold query the compiler accepts (219 of 237):

* ``gold_tier1_iris`` - the mapped terms (classes and properties) the query uses;
* ``gold_subgraph_edges`` - ``(subject class, object property, object class)`` for every
  triple between two typed variables;
* ``gold_filter_values`` - ``(value, class, property)`` for every literal a FILTER compares
  a property value with. String values are what value linking must find; numbers and
  dates are kept with ``kind`` so they can be reported apart.

The C1 oracle (mention spans) cannot be derived from SPARQL. Until the questions are
span-annotated, ``partial_mentions`` substitutes the filter values found verbatim in the
question text, and is labelled *partial*.

    python -m nl2q.evalkit.gold_intermediates      # writes artifacts/eval/gate2/gold_intermediates.json
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache

from .. import gold, paths

OUT = paths.ARTIFACTS / "eval" / "gate2" / "gold_intermediates.json"

_TYPE = re.compile(r"(\?\w+)\s+a\s+fiben:(\w+)")
_TRIPLE = re.compile(r"(\?\w+)\s+fiben:(\w+)\s+(\?\w+)")
_TERM = re.compile(r"fiben:(\w+)")
# FILTER((?v = "x")) / FILTER((?v >= "2017-01-01T00:00:00"^^xsd:dateTime)) / FILTER((?v > 5))
_CMP = re.compile(r'(\?\w+)\s*(=|!=|<=|>=|<|>)\s*("(?:[^"\\]|\\.)*"(?:\^\^[\w:]+)?|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)')
_IN = re.compile(r"(\?\w+)\s+IN\s*\(([^)]*)\)")


def _literal(tok: str) -> tuple[str, str]:
    if tok.startswith('"'):
        m = re.match(r'"((?:[^"\\]|\\.)*)"(?:\^\^([\w:]+))?', tok)
        v, dt = m.group(1).replace('\\"', '"'), m.group(2) or ""
        return v, "date" if "date" in dt.lower() else "string"
    return tok, "number"


def extract(sparql: str) -> dict:
    types: dict[str, set[str]] = defaultdict(set)
    for v, c in _TYPE.findall(sparql):
        types[v].add(c)
    terms = set(_TERM.findall(sparql))
    edges, owner = set(), {}
    for s, p, o in _TRIPLE.findall(sparql):
        if o in types:
            edges |= {(cs, p, co) for cs in types.get(s, ()) for co in types[o]}
        else:
            owner[o] = (s, p)                      # ?o is the value of property p of ?s
    values = []
    pairs = [(v, op, t) for v, op, t in _CMP.findall(sparql)]
    pairs += [(v, "in", t.strip()) for v, body in _IN.findall(sparql) for t in body.split(",") if t.strip()]
    for var, op, tok in pairs:
        if var not in owner:
            continue
        s, p = owner[var]
        val, kind = _literal(tok)
        for c in sorted(types.get(s, {""})):
            values.append({"value": val, "cls": c, "prop": p, "op": op, "kind": kind})
    uniq = {(d["value"], d["cls"], d["prop"], d["op"]): d for d in values}
    return {"gold_tier1_iris": sorted(terms),
            "gold_classes": sorted({c for cs in types.values() for c in cs}),
            "gold_subgraph_edges": sorted(edges),
            "gold_filter_values": list(uniq.values())}


def partial_mentions(question: str, item: dict) -> list[str]:
    """Value spans present verbatim (case-insensitive) in the question: the partial C1 oracle."""
    q = question.lower()
    return sorted({d["value"] for d in item["gold_filter_values"]
                   if d["kind"] == "string" and len(d["value"]) > 1 and d["value"].lower() in q})


def build() -> dict:
    rows = json.loads((paths.GOLD_DIR / "gold_sparql.json").read_text(encoding="utf-8"))
    items = {str(r["sql_id"]): extract(r["sparql"]) for r in rows if r.get("strict")}
    questions = {}
    for q in gold.questions():
        it = items.get(str(q.sql_id))
        if it is not None:
            questions[str(q.qid)] = {"sql_id": q.sql_id, "partial_mentions": partial_mentions(q.question, it)}
    out = {"source": "artifacts/gold/gold_sparql.json (strict = accepted by the suite ceiling)",
           "c1_oracle": "partial: value spans found verbatim in the question; no human span annotation yet",
           "queries": items, "questions": questions}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    if not OUT.exists():
        return build()
    return json.loads(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    o = build()
    qs = o["queries"].values()
    print(f"{len(o['queries'])} gold queries; "
          f"{sum(len(q['gold_subgraph_edges']) for q in qs)} edges; "
          f"{sum(len(q['gold_filter_values']) for q in qs)} filter values; "
          f"{sum(bool(q['partial_mentions']) for q in o['questions'].values())} of {len(o['questions'])} "
          f"questions have a verbatim value span")
