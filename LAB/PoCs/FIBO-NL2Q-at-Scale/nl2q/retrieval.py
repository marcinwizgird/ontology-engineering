"""Candidate generation for grounding: phrase -> ranked ontology terms and data values.

Retrievers (compared in the H1 experiment):

* ``bm25`` — Okapi BM25 over word tokens of the term text (labels, synonyms,
  abbreviations, definitions — depending on the knowledge level);
* ``tfidf`` — character 3–5-gram TF-IDF cosine (robust to inflection and spelling; the
  offline stand-in for dense embeddings — swap in a sentence encoder when available);
* ``hybrid`` — reciprocal-rank fusion of both.

Values are linked separately (exact / prefix / token match over the value index) because a
literal is grounded to a (class, property) pair, not to a term.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from . import knowledge

_TOK = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "for", "in", "on", "to", "by", "and", "or", "is", "are", "was",
        "were", "be", "has", "have", "had", "with", "what", "which", "who", "whom", "show", "me",
        "list", "give", "find", "get", "all", "how", "many", "much", "do", "does", "did", "that",
        "those", "these", "their", "its", "it", "from", "at", "as", "than", "more", "less", "tell"}


def tokens(s: str) -> list[str]:
    out = []
    for t in _TOK.findall(s.lower()):
        if t in STOP:
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


@dataclass
class Hit:
    local: str
    kind: str
    tier: str
    score: float
    label: str = ""


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(map(len, docs)) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in docs]
        self.inv: dict[str, list[int]] = defaultdict(list)
        for i, d in enumerate(docs):
            for t in set(d):
                self.inv[t].append(i)

    def scores(self, q: list[str]) -> dict[int, float]:
        out: dict[int, float] = defaultdict(float)
        for t in set(q):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.inv[t]:
                f = self.tf[i][t]
                dl = len(self.docs[i])
                out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
        return out


class TermIndex:
    def __init__(self, level: int = 4, tiers: tuple[str, ...] = ("mapped",),
                 enrich: tuple[str, ...] | None = None, glossary: str | None = None):
        pack = knowledge.load(enrich=enrich, glossary=glossary)
        self.docs = [t for t in pack.terms if t.tier in tiers]
        # K4: curated glossary phrases are added to the terms they use
        gloss: dict[str, list[str]] = defaultdict(list)
        if level >= 4:
            for g in pack.glossary:
                for u in g["uses"]:
                    gloss[u].append(g["term"].replace("/", " "))
        self.gloss = gloss
        # the label is repeated so it outweighs a long definition
        texts = [(f"{t.label} {t.label} {t.text(level)} " + " ".join(gloss.get(t.local, [])) * 2)
                 if level > 0 else t.local for t in self.docs]
        self.bm25 = BM25([tokens(re.sub(r"([a-z])([A-Z])", r"\1 \2", x)) for x in texts])
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self.lab = [re.sub(r"([a-z])([A-Z])", r"\1 \2", t.label or t.local).lower() +
                    (" " + " ".join(t.synonyms).lower() if level >= 2 else "") +
                    (" " + " ".join(gloss.get(t.local, [])).lower()) for t in self.docs]
        self.mat = self.vec.fit_transform(self.lab)

    def _hits(self, ranked: list[tuple[int, float]], k: int) -> list[Hit]:
        return [Hit(self.docs[i].local, self.docs[i].kind, self.docs[i].tier, round(s, 4),
                    self.docs[i].label) for i, s in ranked[:k]]

    def search(self, phrase: str, k: int = 5, mode: str = "hybrid",
               kinds: tuple[str, ...] | None = None) -> list[Hit]:
        allowed = [i for i, d in enumerate(self.docs) if kinds is None or d.kind in kinds]
        allowed_set = set(allowed)
        bm = {i: s for i, s in self.bm25.scores(tokens(phrase)).items() if i in allowed_set}
        r_bm = sorted(bm.items(), key=lambda x: -x[1])
        if mode == "bm25":
            return self._hits(r_bm, k)
        q = self.vec.transform([phrase.lower()])
        sims = (self.mat @ q.T).toarray().ravel()
        r_tf = sorted(((i, float(sims[i])) for i in allowed if sims[i] > 0), key=lambda x: -x[1])
        if mode == "tfidf":
            return self._hits(r_tf, k)
        fused: dict[int, float] = defaultdict(float)
        for r in (r_bm, r_tf):
            for rank, (i, _) in enumerate(r[:50]):
                fused[i] += 1.0 / (60 + rank)
        return self._hits(sorted(fused.items(), key=lambda x: -x[1]), k)


def term_index(level: int = 4, tiers: tuple[str, ...] = ("mapped",),
               enrich: tuple[str, ...] | None = None, glossary: str | None = None) -> TermIndex:
    return _term_index(level, tiers, knowledge.ENRICH if enrich is None else tuple(enrich),
                       glossary or knowledge.GLOSSARY)


@lru_cache(maxsize=16)
def _term_index(level: int, tiers: tuple[str, ...], enrich: tuple[str, ...], glossary: str) -> TermIndex:
    return TermIndex(level, tiers, enrich, glossary)


# ----------------------------------------------------------------------------- #
@dataclass
class ValueHit:
    value: str
    cls: str
    prop: str
    score: float
    count: int


class ValueIndex:
    def __init__(self):
        self.entries = knowledge.load().values
        self.exact: dict[str, list[int]] = defaultdict(list)
        self.tok: dict[str, list[int]] = defaultdict(list)
        for i, e in enumerate(self.entries):
            self.exact[e.value.lower()].append(i)
            for t in set(tokens(e.value)):
                self.tok[t].append(i)

    def link(self, phrase: str, k: int = 5) -> list[ValueHit]:
        p = phrase.strip().strip("'\"").lower()
        scored: dict[int, float] = {}
        for i in self.exact.get(p, []):
            scored[i] = 1.0
        qt = set(tokens(p))
        if qt:
            cand: Counter = Counter()
            for t in qt:
                lst = self.tok.get(t, [])
                if len(lst) > 3000:                  # very common token: weak evidence
                    continue
                cand.update(lst)
            for i, c in cand.items():
                et = set(tokens(self.entries[i].value))
                j = c / len(qt | et)
                if self.entries[i].value.lower().startswith(p):
                    j = max(j, 0.9)
                scored[i] = max(scored.get(i, 0.0), round(j, 3))
        best = sorted(scored.items(), key=lambda x: (-x[1], -self.entries[x[0]].count))[:k]
        return [ValueHit(self.entries[i].value, self.entries[i].cls, self.entries[i].prop, s,
                         self.entries[i].count) for i, s in best if s >= 0.34]


@lru_cache(maxsize=1)
def value_index() -> ValueIndex:
    return ValueIndex()
