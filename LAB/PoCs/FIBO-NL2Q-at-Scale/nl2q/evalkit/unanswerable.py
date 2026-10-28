"""The stratified unanswerable suite ``U1``-``U3`` (specification §4.3), labelled by
construction from the ontology and the data, never from the gold.

* ``U1`` (FIBO-known, unmapped concept): the question names a FIBO class from a module
  FIBEN does not cover (loans, derivatives, indices, corporate actions). Construction:
  the class's IRI is not in the mapped tier, and no word of its label occurs in a mapped
  term's label or a ``Gv1`` glossary phrase, so it is not a synonym in disguise.
* ``U2`` (mapped concepts, unmapped relationship): both classes are mapped and populated
  (VoID), and the inheritance-closed query graph has **no path of two hops or fewer**
  between them. This is stricter than "no edge": a two-hop route could be a legitimate
  reading of "associated with".
* ``U3`` (out-of-range slice): a lookup whose filter value is absent from the data: a
  fiscal year outside the VoID bounds, an unknown ticker, company or person, a settlement
  date with no trades. Every item stores the SQL that proves the value is absent and the
  count it returned (0). Lookups are used, not counts: "how many ... in 2009" has the
  honest answer 0.

The 24 hand-written v1 questions (``artifacts/gold/unanswerable.json``) stay as a legacy
set: half of them trained v1's refusals.

    python -m nl2q.evalkit.unanswerable      # writes artifacts/eval/unanswerable/strata.json
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from functools import lru_cache

import networkx as nx

from .. import fibo, knowledge, paths, querygraph, vkg_build
from ..glossary import GLOSSARY
from ..retrieval import tokens

OUT = paths.ARTIFACTS / "eval" / "unanswerable" / "strata.json"
SEED = 20261027
PER_STRATUM = 50
SPLIT = (("train", 0.4), ("val", 0.2), ("test", 0.4))
U1_MODULES = ("LOAN", "DER", "IND", "CAE")


def _plural(label: str) -> str:
    w = label.rsplit(" ", 1)
    last = w[-1]
    if last.endswith("y") and last[-2:-1] not in "aeiou":
        last = last[:-1] + "ies"
    elif last.endswith("s") and not last.endswith("ss"):
        pass                                   # "equivalents", "liabilities": already plural
    elif last.endswith(("ss", "x", "ch", "sh")):
        last += "es"
    else:
        last += "s"
    return " ".join(w[:-1] + [last])


def _void() -> dict:
    return json.loads((paths.ARTIFACTS / "eval" / "void.json").read_text(encoding="utf-8"))


def _companies(con, n: int, rng) -> list[str]:
    rows = [r[0] for r in con.execute(f'SELECT DISTINCT "HASLEGALNAME" FROM "{paths.SCHEMA}"."CORPORATION" '
                                      f'WHERE "HASLEGALNAME" IS NOT NULL ORDER BY 1').fetchall()]
    return rng.sample(rows, n)


# ----------------------------------------------------------------------------- U1
def u1(rng, companies: list[str]) -> list[dict]:
    pack = knowledge.load(glossary="none")
    known = set()
    for t in pack.mapped():
        known |= set(tokens(t.label or vkg_build.label(t.local)))
        known |= {w for s in t.synonyms for w in tokens(s)}
    for g in GLOSSARY:
        known |= set(tokens(g["term"].replace("/", " ")))
    f = fibo.load()
    pool = []
    for t in f.terms.values():
        m = re.search(r"/ontology/(\w+)/", t.iri)
        if t.kind != "class" or not m or m.group(1) not in U1_MODULES or not t.label:
            continue
        words = tokens(t.label)
        if not 1 <= len(words) <= 4 or set(words) & known or re.search(r"[^A-Za-z \-]", t.label):
            continue
        pool.append(t)
    pool.sort(key=lambda t: t.iri)
    pick = rng.sample(pool, min(PER_STRATUM, len(pool)))
    forms = ["List all {p}.", "How many {p} are there?", "Which {p} does {c} have?",
             "Show the {l} details for {c}."]
    out = []
    for i, t in enumerate(pick):
        lab = t.label.lower()
        q = forms[i % len(forms)].format(p=_plural(lab), l=lab, c=companies[i % len(companies)].rstrip("."))
        out.append({"stratum": "U1", "question": q,
                    "construction": {"fibo_iri": t.iri, "fibo_label": t.label, "mapped": False,
                                     "label_words_in_mapped_vocabulary": [],
                                     "pool_size": len(pool)}})
    return out


# ----------------------------------------------------------------------------- U2
def u2(rng) -> list[dict]:
    v = _void()
    g = querygraph.load()
    pop = sorted(c for c, n in v["classes"].items() if n > 0 and c in g.classes)
    dist = dict(nx.all_pairs_shortest_path_length(g.g.subgraph(pop), cutoff=2))
    pairs = [(a, b) for a in pop for b in pop if a < b and b not in dist.get(a, {})]
    rng.shuffle(pairs)
    used: Counter = Counter()
    pick = []
    for a, b in pairs:
        if used[a] >= 3 or used[b] >= 3:
            continue
        used[a] += 1
        used[b] += 1
        pick.append((a, b) if rng.random() < 0.5 else (b, a))
        if len(pick) == PER_STRATUM:
            break
    forms = ["For each {a}, list the {B} it is linked to.", "Which {B} belong to each {a}?",
             "Show every {a} together with its {b}.", "Which {B} are associated with each {a}?"]
    out = []
    for i, (a, b) in enumerate(pick):
        la, lb = vkg_build.label(a).lower(), vkg_build.label(b).lower()
        q = forms[i % len(forms)].format(a=la, b=lb, B=_plural(lb))
        out.append({"stratum": "U2", "question": q,
                    "construction": {"classes": [a, b], "populated": [v["classes"][a], v["classes"][b]],
                                     "path_within_2_hops": False,
                                     "shortest_path": nx.shortest_path_length(g.g, a, b, weight=None)
                                     if nx.has_path(g.g, a, b) else None}})
    return out


# ----------------------------------------------------------------------------- U3
def _absent(con, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


def u3(rng, con, companies: list[str]) -> list[dict]:
    S = paths.SCHEMA
    v = _void()
    lo, hi = (int(x) for x in v["bounds"]["ElementOfFinancialStatement.hasMetricYearFiscal"])
    years = [y for y in range(lo - 12, hi + 6) if y < lo or y > hi]
    out = []

    def add(q: str, kind: str, value: str, sql: str) -> None:
        n = _absent(con, sql)
        if n == 0:
            out.append({"stratum": "U3", "question": q,
                        "construction": {"kind": kind, "value": value, "evidence_sql": sql, "count": n}})

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    syll = ["vor", "tan", "quel", "mira", "dex", "lun", "zar", "oph", "bren", "kal", "tiv", "nor"]
    firsts = ["Aurelio", "Benedikta", "Casimir", "Desislava", "Evander", "Faustina", "Gwydion", "Hesper"]
    lasts = ["Quarrington", "Vellacott", "Ashgrove", "Thornbury", "Penwarden", "Lyddiard", "Mabbott", "Rendcomb"]
    i = 0
    while len(out) < PER_STRATUM and i < 10 * PER_STRATUM:
        k = i % 5
        c = companies[i % len(companies)].replace("'", "''")
        if k == 0:
            y = rng.choice(years)
            add(f"What was the revenue of {companies[i % len(companies)]} in fiscal year {y}?", "year", str(y),
                f'SELECT count(*) FROM "{S}"."ELEMENTOFFINANCIALSTATEMENT" WHERE "HASMETRICYEARFISCAL" = {y}')
        elif k == 1:
            t = "".join(rng.choice(letters) for _ in range(4))
            add(f"What is the last traded value of the stock with ticker symbol {t}?", "ticker", t,
                f'SELECT (SELECT count(*) FROM "{S}"."LISTEDSECURITY" WHERE upper("HASTICKERSYMBOL") = \'{t}\') + '
                f'(SELECT count(*) FROM "{S}"."CORPORATION" WHERE upper("HASTICKERSYMBOL") = \'{t}\')')
        elif k == 2:
            n = (rng.choice(syll) + rng.choice(syll)).capitalize() + " " + rng.choice(["Holdings", "Dynamics", "Labs"])
            add(f"Who are the officers of {n} Inc.?", "company", n,
                f'SELECT (SELECT count(*) FROM "{S}"."CORPORATION" WHERE "HASLEGALNAME" ILIKE \'%{n}%\') + '
                f'(SELECT count(*) FROM "{S}"."LISTEDSECURITY" WHERE "HASLEGALNAME" ILIKE \'%{n}%\')')
        elif k == 3:
            y = rng.choice([2011, 2012, 2013, 2018, 2019, 2020])
            d = f"{y}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            add(f"List the stock trades settled on {d}.", "settlement-date", d,
                f'SELECT count(*) FROM "{S}"."SECURITIESTRANSACTION" WHERE CAST("HASSETTLEMENTDATE" AS DATE) = DATE \'{d}\'')
        else:
            fn, ln = rng.choice(firsts), rng.choice(lasts)
            add(f"Which stocks does {fn} {ln} hold?", "person", f"{fn} {ln}",
                f'SELECT count(*) FROM "{S}"."PERSON" WHERE "HASFIRSTNAME" = \'{fn}\' AND "HASLASTNAME" = \'{ln}\'')
        i += 1
    del c
    return out


# ----------------------------------------------------------------------------- suite
def build() -> dict:
    from ..load_fiben import connect
    rng = random.Random(SEED)
    con = connect()
    companies = _companies(con, 40, rng)
    items = u1(rng, companies) + u2(rng) + u3(rng, con, companies)
    by: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by[it["stratum"]].append(it)
    for s, lst in by.items():
        order = list(range(len(lst)))
        random.Random(f"{SEED}-{s}").shuffle(order)
        a = round(len(lst) * SPLIT[0][1])
        b = a + round(len(lst) * SPLIT[1][1])
        for rank, j in enumerate(order):
            lst[j]["split"] = "train" if rank < a else "val" if rank < b else "test"
        for n, it in enumerate(lst, 1):
            it["id"] = f"{s}-{n:03d}"
    out = {"note": "Unanswerable questions labelled by construction (specification §4.3). "
                   "Gold outcome: refuse or ask for clarification.",
           "seed": SEED,
           "counts": {s: dict(Counter(i["split"] for i in lst)) for s, lst in sorted(by.items())},
           "items": [{"id": i["id"], **{k: v for k, v in i.items() if k != "id"}} for s in sorted(by) for i in by[s]]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    load.cache_clear()
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    if not OUT.exists():
        return build()
    return json.loads(OUT.read_text(encoding="utf-8"))


def items(split: str) -> list[dict]:
    return [i for i in load()["items"] if split == "all" or i["split"] == split]


if __name__ == "__main__":
    o = build()
    print(json.dumps(o["counts"]))
    for s in ("U1", "U2", "U3"):
        for it in [i for i in o["items"] if i["stratum"] == s][:4]:
            print(f"  {it['id']} [{it['split']}] {it['question']}")
