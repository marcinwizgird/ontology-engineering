"""``Gtrain``: a glossary induced from the train split only (specification §4.5).

The v1 glossary (``Gv1``, ``nl2q.glossary``) was written after reading all gold SQL, so
every result that uses it is *possibly contaminated*. ``Gtrain`` is authored by a
procedure, not a person, so its access is a fact of the code: :func:`induce` receives
train questions and their gold intermediates, and refuses any question outside the train
split. Every entry lists the train query IDs it was derived from.

Induction, per train question and its gold SPARQL terms:

* a gold term is **unexplained** when none of its label words occur in the question;
* the question's remaining content words (minus the label words of the explained terms
  and the filter values found verbatim) are candidate phrases for it, as 1- and 2-grams;
* a phrase becomes a glossary entry for a term when it co-occurs with it in at least
  ``MIN_SUPPORT`` distinct gold queries, in at least ``MIN_PRECISION`` of the train
  queries whose question contains the phrase, and at least ``MIN_LIFT`` times as often as
  the term is unexplained overall. Each phrase keeps its best-supported term and its
  best-supported code.

Codes are induced the same way from string filter values that never occur verbatim
(``hasType = "1"``). The entry kinds follow ``Gv1``: ``synonym`` for classes and
datatype properties, ``path`` for object properties (with the gold edge's end classes,
so re-ranking discounts the route), ``code`` for values.

    python -m nl2q.evalkit.gtrain      # writes artifacts/eval/glossary/gtrain.json
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache

from .. import knowledge, paths, splits, vkg_build
from ..retrieval import tokens
from . import gold_intermediates

OUT = paths.ARTIFACTS / "eval" / "glossary" / "gtrain.json"
MIN_SUPPORT = 3
MIN_PRECISION = 0.6
MIN_LIFT = 1.2
MAX_TERMS_PER_PHRASE = 1
#: words that name the question form (aggregates, comparisons, pronouns, dates), not the data
GENERIC = set("""name number total each every top average count sum highest lowest most least
maximum minimum between after before greater smaller larger over under per any also only same
different other not no year value amount they them this where when since one another having
above below equal higher lower increase increased decrease decreased gone more less than
first last ever whose january february march april may june july august september october
november december quarter day month date""".split())
GENERIC |= set(tokens(" ".join(GENERIC)))           # compare on the stems the questions are cut into


class LeakError(RuntimeError):
    pass


def _label_tokens(local: str) -> set[str]:
    return set(tokens(vkg_build.label(local) if local[:1].isupper() or local.startswith(("has", "is"))
                      else local))


def _grams(words: list[str]) -> set[tuple[str, ...]]:
    out = {(w,) for w in words}
    out |= {(a, b) for a, b in zip(words, words[1:])}
    return out


def induce(questions: list, intermediates: dict) -> dict:
    """``questions``: ``gold.Question`` objects of the train split only."""
    train = set(splits.load()["train"])
    leaked = sorted({q.sql_id for q in questions} - train)
    if leaked:
        raise LeakError(f"Gtrain may read train questions only; got sql_ids {leaked[:10]}")
    kind_of = {t.local: t.kind for t in knowledge.load(glossary="none").mapped()}
    surface: dict[str, Counter] = defaultdict(Counter)
    co: dict[tuple, set[int]] = defaultdict(set)          # (gram, target) -> sql_ids
    df: dict[tuple, set[int]] = defaultdict(set)          # gram -> sql_ids whose question has it
    edges_of: dict[str, set[tuple]] = defaultdict(set)
    for q in questions:
        it = intermediates["queries"].get(str(q.sql_id))
        if it is None:
            continue
        text = q.question.lower()
        verbatim = {d["value"].lower() for d in it["gold_filter_values"] if d["value"].lower() in text}
        for v in verbatim:
            text = text.replace(v, " ")
        words = [w for w in tokens(text) if not w.isdigit() and len(w) > 2 and w not in GENERIC]
        for raw in re.findall(r"[a-z]+", text):
            surface[(tokens(raw) or [raw])[0]][raw] += 1
        qset = set(words)
        explained, targets = set(), []
        for t in it["gold_tier1_iris"]:
            lt = _label_tokens(t)
            if lt & qset:
                explained |= lt
            else:
                targets.append(("term", t))
        for d in it["gold_filter_values"]:
            if d["kind"] == "string" and d["value"].lower() not in verbatim:
                targets.append(("code", d["cls"], d["prop"], d["value"]))
        for s, p, o in it["gold_subgraph_edges"]:
            edges_of[p].add((s, p, o))
        free = [w for w in words if w not in explained]
        grams = _grams(free)
        for g in _grams(words) | grams:
            df[g].add(q.sql_id)
        for tg in targets:
            for g in grams:
                co[(g, tg)].add(q.sql_id)
    n_all = len({q.sql_id for q in questions})
    base: dict[tuple, set[int]] = defaultdict(set)        # target -> sql_ids where it is a target
    for (g, tg), ids in co.items():
        base[tg] |= ids
    keep: dict[tuple, list[tuple]] = defaultdict(list)
    for (g, tg), ids in co.items():
        prec = len(ids) / len(df[g])
        lift = prec / (len(base[tg]) / n_all)
        if len(ids) >= MIN_SUPPORT and prec >= MIN_PRECISION and lift >= MIN_LIFT:
            keep[g].append((len(ids), prec, tg, ids))
    # a bigram adds nothing when one of its words is already kept for the same target
    for g in [g for g in keep if len(g) == 2]:
        best = {c[2] for c in keep[g]}
        if any({c[2] for c in keep.get((w,), [])} & best for w in g):
            del keep[g]
    grouped: dict[tuple, dict] = {}
    for g, cands in keep.items():
        cands.sort(key=lambda x: (-x[0], -x[1], str(x[2])))
        # the best term and, separately, the best code: "bought" names a stock *and* a code
        chosen = [c for c in cands if c[2][0] == "term"][:MAX_TERMS_PER_PHRASE] +                  [c for c in cands if c[2][0] == "code"][:MAX_TERMS_PER_PHRASE]
        for n, prec, tg, ids in chosen:
            phrase = " ".join(surface[w].most_common(1)[0][0] if surface[w] else w for w in g)
            if tg[0] == "code":
                _, cls, prop, val = tg
                key = ("code", cls, prop, val)
                entry = grouped.setdefault(key, {"kind": "code", "means": f'{cls} with {prop} = "{val}"',
                                                 "uses": [cls, prop]})
            else:
                t = tg[1]
                k = kind_of.get(t, "class")
                if k == "object" and edges_of.get(t):
                    s, p, o = sorted(edges_of[t])[0]
                    key = ("path", t)
                    entry = grouped.setdefault(key, {"kind": "path", "means": f"{s} {p} {o}", "uses": [s, p, o]})
                else:
                    key = ("synonym", t)
                    entry = grouped.setdefault(key, {"kind": "synonym", "means": t, "uses": [t]})
            entry.setdefault("phrases", {})[phrase] = {"support": n, "precision": round(prec, 3)}
            entry.setdefault("derived_from", set()).update(ids)
    entries = []
    for key in sorted(grouped, key=str):
        e = grouped[key]
        ph = sorted(e.pop("phrases").items(), key=lambda x: (-x[1]["support"], x[0]))
        entries.append({"term": " / ".join(p for p, _ in ph), **e, "evidence": dict(ph),
                        "derived_from": sorted(e["derived_from"])})
    ids = sorted({q.sql_id for q in questions})
    return {
        "glossary": "Gtrain",
        "author": "nl2q.evalkit.gtrain (automatic induction; no hand edits)",
        "created": date.today().isoformat(),
        "access": {"split": "train", "questions": len(questions), "gold_queries": len(ids),
                   "train_sql_ids_sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest()},
        "parameters": {"min_support": MIN_SUPPORT, "min_precision": MIN_PRECISION, "min_lift": MIN_LIFT,
                       "max_terms_per_phrase": MAX_TERMS_PER_PHRASE},
        "entries": entries,
    }


def build() -> dict:
    out = induce(splits.questions("train"), gold_intermediates.load())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    load.cache_clear()
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    if not OUT.exists():
        return build()
    return json.loads(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    g = build()
    print(f"Gtrain: {len(g['entries'])} entries from {g['access']['gold_queries']} train gold queries; "
          f"kinds {dict(Counter(e['kind'] for e in g['entries']))}")
    for e in g["entries"]:
        print(f"  [{e['kind']}] {e['term']} -> {e['means']}  ({len(e['derived_from'])} queries)")
