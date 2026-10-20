"""Grounding: question -> mentions -> candidates -> ranked trees.

Mentions come from the LLM (program module M1) or, offline, from :func:`rule_mentions`:
quoted strings and capitalised spans are value candidates; n-grams (1-4 words) are
looked up in the value index (exact/prefix matches win) and the term index.

:func:`ground` assembles candidates per mention (classes, properties, values), re-ranks
combinations on the query graph and returns a :class:`GroundingResult` — the context the
planner (M2) chooses from. It also checks the FIBO tier: a mention whose best match is a
FIBO term that is *not mapped* becomes an explained-refusal hint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import rerank, retrieval
from .querygraph import load as load_graph

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&.'\-]*")


@dataclass
class MentionSpec:
    text: str
    kind: str = "concept"        # concept | value | any


@dataclass
class GroundingResult:
    question: str
    mentions: list[rerank.Mention]
    trees: list[rerank.Grounding]
    values: list[retrieval.ValueHit]
    unmapped_hints: list[str] = field(default_factory=list)

    @property
    def best(self) -> rerank.Grounding | None:
        return self.trees[0] if self.trees and self.trees[0].connected else None

    def concepts(self) -> set[str]:
        out = set()
        for t in self.trees[:1]:
            out |= set(t.classes)
            for c in t.choice:
                out.add(c.local)
                if c.cls:
                    out.add(c.cls)
            for s, p, o in t.tree:
                out |= {s, p, o}
        return out


def rule_mentions(question: str, max_n: int = 4) -> list[MentionSpec]:
    """Offline mention extraction: values first (longest exact/prefix match), then
    concept n-grams over the remaining words."""
    q = question.strip()
    out: list[MentionSpec] = []
    used: set[int] = set()
    words = _WORD.findall(q)
    vi = retrieval.value_index()
    # 1) quoted strings
    for m in re.finditer(r"['\"]([^'\"]{2,})['\"]", q):
        out.append(MentionSpec(m.group(1), "value"))
    # 2) longest value spans
    for n in range(min(max_n, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            if any(j in used for j in range(i, i + n)):
                continue
            span = " ".join(words[i:i + n])
            if words[i].lower() in retrieval.STOP or words[i + n - 1].lower() in retrieval.STOP:
                continue
            if n == 1 and not (span[0].isupper() or span.isdigit()):
                continue
            hits = vi.link(span, 1)
            if hits and hits[0].score >= 0.9:
                out.append(MentionSpec(span, "value"))
                used |= set(range(i, i + n))
    # 3) concept n-grams over the rest (keep content words)
    rest = [w for j, w in enumerate(words) if j not in used and w.lower() not in retrieval.STOP
            and not re.fullmatch(r"\d+(\.\d+)?", w)]
    ti = retrieval.term_index()
    i = 0
    while i < len(rest):
        taken = False
        for n in (3, 2):
            if i + n <= len(rest):
                span = " ".join(rest[i:i + n])
                h = ti.search(span, 1, mode="bm25")
                if h and h[0].score > 6.0:
                    out.append(MentionSpec(span, "concept"))
                    i += n
                    taken = True
                    break
        if not taken:
            out.append(MentionSpec(rest[i], "concept"))
            i += 1
    return out


def candidates(spec: MentionSpec, k: int = 3, level: int = 4, mode: str = "hybrid") -> rerank.Mention:
    cands: list[rerank.Candidate] = []
    if spec.kind in ("value", "any"):
        for r_, h in enumerate(retrieval.value_index().link(spec.text, k)):
            cands.append(rerank.Candidate("value", h.prop, h.score / (1 + 0.1 * r_), h.cls, h.value))
    if spec.kind in ("concept", "any") or not cands:
        for r_, h in enumerate(retrieval.term_index(level).search(spec.text, k, mode=mode)):
            cands.append(rerank.Candidate(h.kind, h.local, 1.0 / (1 + r_)))
    return rerank.Mention(spec.text, cands)


def fibo_hint(spec: MentionSpec) -> str | None:
    """A mention whose best overall match is an unmapped FIBO term (explained refusal)."""
    both = retrieval.term_index(4, ("mapped", "fibo")).search(spec.text, 1, mode="bm25")
    if both and both[0].tier == "fibo" and both[0].score > 8.0:
        mapped = retrieval.term_index(4).search(spec.text, 1, mode="bm25")
        if not mapped or mapped[0].score < 0.5 * both[0].score:
            return f'"{spec.text}" matches FIBO\'s "{both[0].label}", which this data does not map'
    return None


def path_hints(question: str, level: int = 4) -> tuple[set[str], list[dict]]:
    """Curated path knowledge (K4): glossary entries whose phrases occur in the question
    name the terms of the intended route; their edges get a discount in re-ranking."""
    if level < 4:
        return set(), []
    from .knowledge import load as load_pack
    qt = set(retrieval.tokens(question))
    hits, terms = [], set()
    for g in load_pack().glossary:
        phrases = [p.strip() for p in g["term"].split("/")]
        if any(set(retrieval.tokens(p)) and set(retrieval.tokens(p)) <= qt for p in phrases):
            hits.append(g)
            if g["kind"] in ("path", "measure"):
                terms |= set(g["uses"])
    return terms, hits


def ground(question: str, specs: list[MentionSpec] | None = None, *, k: int = 3,
           level: int = 4, mode: str = "hybrid", scorer: str = "steiner",
           lam: float = 0.25, top: int = 5) -> GroundingResult:
    specs = specs if specs is not None else rule_mentions(question)
    mentions = [candidates(s, k, level, mode) for s in specs]
    mentions = [m for m in mentions if m.candidates]
    discount, _ = path_hints(question, level)
    trees = rerank.rank(mentions, lam=lam, k=k, top=top, scorer=scorer, graph=load_graph(),
                        discount=discount)
    vals = [c for m in mentions for c in m.candidates if c.kind == "value"]
    hints = [h for s in specs if (h := fibo_hint(s))]
    return GroundingResult(question, mentions, trees,
                           [retrieval.ValueHit(c.value, c.cls, c.local, c.text, 0) for c in vals],
                           hints)
