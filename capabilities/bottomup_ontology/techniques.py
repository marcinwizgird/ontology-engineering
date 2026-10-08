"""Lightweight, dependency-free implementations of the *techniques* attached to
each pipeline stage in Keet (2nd ed.), Chapter 7, Figure 7.7.

The book lists, per stage, a menu of techniques (statistical, linguistic,
logic-programming, evaluation).  Full implementations would need spaCy/NLTK,
gensim, WordNet, etc.; here we provide small but genuine heuristic versions so
the whole pipeline runs anywhere with only the standard library.  The function
boundaries mirror the book's technique names so the mapping is explicit.

Stage → techniques (Fig. 7.7):
  * Text cleaning      : PoS tagging, parsing, lemmatisation
  * Pre-processing     : C/NC-value, contrastive analysis (domain relevance &
                         coverage), co-occurrence analysis, LSA, clustering
  * Term extraction    : term composition, formal concept analysis,
                         hierarchical clustering, association-rule mining
  * Relation extraction: syntactic analysis, subcategorisation frames, seed words
  * Axiom finding      : dependency analysis, lexico-syntactic patterns, ILP
  * Evaluation         : gold-standard comparison, application use case,
                         data-driven assessment, human judgements
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Iterable

from .state import CandidateTerm, Relation, Token

# --------------------------------------------------------------------------- #
# Small linguistic resources (kept tiny on purpose)
# --------------------------------------------------------------------------- #
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "as", "is", "are", "was", "were", "be", "been", "being", "by", "at",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "we", "you", "he", "she", "from", "into", "than", "then", "so", "such",
    "can", "may", "will", "would", "should", "could", "have", "has", "had",
    "not", "no", "do", "does", "did", "which", "who", "whom", "whose", "also",
}
DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those", "some", "any", "each",
    "many", "much", "several", "few", "all", "most", "every", "no",
}
PREPOSITIONS = {"of", "in", "on", "for", "with", "as", "by", "at", "from", "into", "to"}
# Linking/relational verbs treated as predicate seed words (Fig. 7.7: "use of
# seed words" / subcategorisation frames).  Kept small but covering the common
# relational/action verbs so the heuristic chunker does not absorb them into
# noun phrases.
SEED_VERBS = {
    "has", "have", "contains", "contain", "includes", "include", "plays",
    "play", "uses", "use", "produces", "produce", "requires", "require",
    "is", "are", "eats", "eat", "owns", "own", "consists", "consist",
    "trains", "train", "lives", "live", "belongs", "belong", "makes", "make",
    "gives", "give", "relates", "relate", "occurs", "occur", "assigns",
    "assign", "located", "supervises", "supervise", "teaches", "teach",
    "works", "work", "writes", "write", "manages", "manage",
}
# Hearst-style lexico-syntactic patterns for IS-A / subsumption axioms.
_HEARST_PATTERNS = [
    re.compile(r"(?P<sup>[\w\s]+?)\s+such as\s+(?P<sub>[\w\s,]+)", re.I),
    re.compile(r"(?P<sup>[\w\s]+?)\s+including\s+(?P<sub>[\w\s,]+)", re.I),
    re.compile(r"(?P<sup>[\w\s]+?)\s+especially\s+(?P<sub>[\w\s,]+)", re.I),
    re.compile(r"(?P<sub>[\w\s]+?)\s+(?:is|are)\s+(?:a|an)\s+(?P<sup>[\w\s]+)", re.I),
]


# --------------------------------------------------------------------------- #
# Stage 1 — Text cleaning  (PoS tagging, parsing, lemmatisation)
# --------------------------------------------------------------------------- #
def split_sentences(text: str) -> list[str]:
    """Naive sentence splitter."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def lemmatize(word: str) -> str:
    """A crude rule-based lemmatiser (handles the common English plurals)."""
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("es") and w[-3] in "sxz":
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def pos_tag(word: str, is_sentence_start: bool = False) -> str:
    """Heuristic coarse PoS tagger.

    Real pipelines use a trained tagger; this rule set is enough to drive term
    and relation extraction in the demo.
    """
    lw = word.lower()
    if lw in DETERMINERS:
        return "DET"
    if lw in PREPOSITIONS:
        return "ADP"
    if lw in SEED_VERBS or lw.endswith("ing"):
        return "VERB"
    if lw.endswith("ed") and len(lw) > 4:
        return "VERB"
    if lw.endswith(("ous", "ive", "al", "ic", "able", "ible")):
        return "ADJ"
    if word[:1].isupper() and not is_sentence_start:
        return "PROPN"
    if lw in STOPWORDS:
        return "OTHER"
    return "NOUN"


def clean_and_tag(documents: Iterable[str]) -> list[Token]:
    """Tokenise, lemmatise and PoS-tag a corpus → list of :class:`Token`."""
    tokens: list[Token] = []
    for doc_id, doc in enumerate(documents):
        for sent_id, sentence in enumerate(split_sentences(doc)):
            words = re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)
            for pos_idx, word in enumerate(words):
                tokens.append(
                    Token(
                        surface=word,
                        lemma=lemmatize(word),
                        pos=pos_tag(word, is_sentence_start=(pos_idx == 0)),
                        doc_id=doc_id,
                        sent_id=sent_id,
                    )
                )
    return tokens


# --------------------------------------------------------------------------- #
# Stage 2 — Pre-processing  (contrastive analysis, co-occurrence, ...)
# --------------------------------------------------------------------------- #
def term_frequencies(tokens: list[Token]) -> Counter:
    """Content-word (noun/proper-noun) lemma frequencies."""
    return Counter(t.lemma for t in tokens if t.pos in ("NOUN", "PROPN") and t.lemma not in STOPWORDS)


def contrastive_relevance(
    tokens: list[Token], background: list[str]
) -> dict[str, float]:
    """Domain *relevance* via contrastive analysis (Fig. 7.7).

    Score = domain term frequency weighted by how much rarer the term is in a
    general/background corpus.  Falls back to plain TF when no background is
    supplied.
    """
    fg = term_frequencies(tokens)
    if not fg:
        return {}
    if not background:
        total = sum(fg.values())
        return {term: count / total for term, count in fg.items()}
    bg = term_frequencies(clean_and_tag(background))
    bg_total = sum(bg.values()) or 1
    fg_total = sum(fg.values()) or 1
    scores: dict[str, float] = {}
    for term, count in fg.items():
        p_fg = count / fg_total
        p_bg = bg.get(term, 0) / bg_total
        # higher when frequent in domain and rare in background
        scores[term] = p_fg * math.log((p_fg + 1e-9) / (p_bg + 1e-9) + 1.0)
    return scores


def cooccurrence_counts(tokens: list[Token]) -> dict[tuple[str, str], int]:
    """Sentence-level co-occurrence of content-word lemmas."""
    by_sent: dict[tuple[int, int], list[str]] = defaultdict(list)
    for t in tokens:
        if t.pos in ("NOUN", "PROPN") and t.lemma not in STOPWORDS:
            by_sent[(t.doc_id, t.sent_id)].append(t.lemma)
    counts: Counter = Counter()
    for lemmas in by_sent.values():
        uniq = sorted(set(lemmas))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                counts[(uniq[i], uniq[j])] += 1
    return dict(counts)


# --------------------------------------------------------------------------- #
# Stage 3 — Term (concept) extraction  (C/NC-value, term composition, ...)
# --------------------------------------------------------------------------- #
def extract_candidate_terms(
    tokens: list[Token], relevance: dict[str, float], min_frequency: int = 1
) -> list[CandidateTerm]:
    """Extract single- and multi-word candidate terms.

    Multi-word terms are noun phrases harvested by grouping adjacent
    ADJ*/NOUN+ runs (a poor man's *term composition* / C-value).  Each term's
    score blends frequency, phrase length and the contrastive relevance of its
    head noun.
    """
    # noun-phrase chunking on lemmas
    phrases: Counter = Counter()
    current: list[Token] = []

    def flush() -> None:
        nouny = [t for t in current if t.pos in ("NOUN", "PROPN", "ADJ")]
        if nouny and any(t.pos in ("NOUN", "PROPN") for t in nouny):
            phrase = " ".join(t.lemma for t in nouny)
            phrases[phrase] += 1

    last = None
    for t in tokens:
        same_sent = last is not None and (t.doc_id, t.sent_id) == (last.doc_id, last.sent_id)
        if t.pos in ("NOUN", "PROPN", "ADJ") and (same_sent or not current):
            current.append(t)
        else:
            flush()
            current = [t] if t.pos in ("NOUN", "PROPN", "ADJ") else []
        last = t
    flush()

    candidates: list[CandidateTerm] = []
    for phrase, freq in phrases.items():
        if freq < min_frequency:
            continue
        length = len(phrase.split())
        head = phrase.split()[-1]
        rel = relevance.get(head, relevance.get(phrase, 0.0))
        # C-value flavour: longer, frequent, relevant phrases score higher
        score = freq * (1.0 + math.log(length + 1)) * (1.0 + rel)
        candidates.append(CandidateTerm(term=phrase, frequency=freq, score=round(score, 4)))
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def composition_subclasses(terms: list[str]) -> list[tuple[str, str]]:
    """*Term composition*: a multi-word term is a subclass of its head noun.

    e.g. "rugby player" ⊑ "player"  (cf. Example 7.1 in the book).
    """
    term_set = set(terms)
    pairs: list[tuple[str, str]] = []
    for term in terms:
        words = term.split()
        if len(words) > 1:
            head = words[-1]
            if head in term_set and head != term:
                pairs.append((term, head))
    return pairs


# --------------------------------------------------------------------------- #
# Stage 4 — Relation extraction  (syntactic analysis, seed words, ...)
# --------------------------------------------------------------------------- #
def extract_relations(
    tokens: list[Token], known_terms: set[str]
) -> list[Relation]:
    """Subject-verb-object extraction restricted to known candidate terms.

    Implements the "use of seed words" + "subcategorisation frames" idea: scan
    each sentence for ``NOUN (seed-VERB) NOUN`` patterns and emit an object
    property.
    """
    by_sent: dict[tuple[int, int], list[Token]] = defaultdict(list)
    for t in tokens:
        by_sent[(t.doc_id, t.sent_id)].append(t)

    rels: Counter = Counter()
    for sent_tokens in by_sent.values():
        for i, tok in enumerate(sent_tokens):
            if tok.pos != "VERB" or tok.lemma not in SEED_VERBS:
                continue
            subj = _nearest_noun(sent_tokens, i, direction=-1, known=known_terms)
            obj = _nearest_noun(sent_tokens, i, direction=+1, known=known_terms)
            if subj and obj and subj != obj:
                rels[(subj, tok.lemma, obj)] += 1
    return [
        Relation(subject=s, predicate=p, object=o, support=c)
        for (s, p, o), c in rels.items()
    ]


def _nearest_noun(
    sent_tokens: list[Token], idx: int, direction: int, known: set[str]
) -> str | None:
    """Walk left/right from a verb to the closest noun that is a known term."""
    j = idx + direction
    while 0 <= j < len(sent_tokens):
        tok = sent_tokens[j]
        if tok.pos in ("NOUN", "PROPN"):
            if not known or tok.lemma in known:
                return tok.lemma
        j += direction
    return None


# --------------------------------------------------------------------------- #
# Stage 5 — Axiom finding  (lexico-syntactic patterns, dependency analysis)
# --------------------------------------------------------------------------- #
def hearst_subclass_axioms(documents: Iterable[str]) -> list[tuple[str, str]]:
    """Find subsumption (subclass) axioms via lexico-syntactic (Hearst) patterns.

    Returns (sub, super) pairs, e.g. "animal such as dog" → (dog, animal).
    """
    pairs: list[tuple[str, str]] = []
    for doc in documents:
        for sentence in split_sentences(doc):
            for pat in _HEARST_PATTERNS:
                for m in pat.finditer(sentence):
                    sup = _norm(m.group("sup"))
                    for sub in re.split(r",|\band\b", m.group("sub")):
                        sub = _norm(sub)
                        if sub and sup and sub != sup and len(sub.split()) <= 4:
                            pairs.append((sub, sup))
    # de-duplicate, keep order
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _norm(span: str) -> str:
    """Lemma-normalise the head words of a captured noun phrase span."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", span.lower())
    words = [w for w in words if w not in STOPWORDS]
    if not words:
        return ""
    # keep last up-to-2 words and lemmatise the head
    tail = words[-2:]
    tail[-1] = lemmatize(tail[-1])
    return " ".join(tail)


# --------------------------------------------------------------------------- #
# Stage 6 — Evaluation  (gold-standard comparison, data-driven assessment)
# --------------------------------------------------------------------------- #
def prf(found: set, gold: set) -> dict[str, float]:
    """Precision / recall / F1 of a found set against a gold set."""
    if not gold:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "support": 0}
    tp = len(found & gold)
    precision = tp / len(found) if found else 0.0
    recall = tp / len(gold)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "tp": tp,
        "support": len(gold),
    }
