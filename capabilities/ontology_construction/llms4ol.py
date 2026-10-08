"""The LLMs4OL paradigm — ontology learning decomposed into three subtasks.

From the source report, the paradigm subdivides ontology learning into:

===========================================  ==================================
Subtask                                      Analytical focus
===========================================  ==================================
Term extraction & typing                     Identify core domain concepts from
                                             raw text and categorise them into
                                             broader semantic types.
Taxonomy discovery                           Induce ``is-a`` relationships to
                                             build the structural backbone.
Non-taxonomic relation extraction            Identify domain-specific predicates
                                             (``causes``, ``consists of``) that
                                             link concepts.
===========================================  ==================================

Two of the report's empirical findings are implemented here as first-class
mechanisms rather than prose:

* **Axiom-by-Axiom (AbA) prompting beats single-shot generation.** The report
  records that querying the model for discrete axioms "yields significantly
  higher F1 scores than attempting to generate the entire ontology graph in a
  single, direct prompt". :class:`PromptingStrategy` makes the two comparable
  so the claim can be measured on your own data rather than assumed.
* **Quadratic complexity of relation prediction.** Zero-shot edge prediction
  over *n* terms is O(n²) and "computationally unscalable". :func:`candidate_pairs`
  bounds it by co-occurrence, and the budget is reported rather than hidden.

The LLM is injected as an :class:`Extractor`. The default
:class:`HeuristicExtractor` is deterministic, offline and dependency-free — the
same convention :mod:`bottomup_ontology` uses — so the whole pipeline runs and
is testable with no API key. :class:`LLMExtractor` is the drop-in that calls a
real model behind the identical interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol, runtime_checkable

from .state import (
    CandidateTerm,
    ConstructionState,
    RelationEdge,
    TaxonomyEdge,
)

__all__ = [
    "Extractor", "HeuristicExtractor", "LLMExtractor", "PromptingStrategy",
    "candidate_pairs", "step_term_typing", "step_taxonomy_discovery",
    "step_relation_extraction", "TYPE_HINTS", "RELATION_CUES",
]


class PromptingStrategy:
    """How the model is asked. The report finds AbA materially better."""

    AXIOM_BY_AXIOM = "aba"     # one constrained query per candidate axiom
    SINGLE_SHOT = "single"     # one query for the whole graph


# --------------------------------------------------------------------------- #
# The injectable extractor
# --------------------------------------------------------------------------- #
@runtime_checkable
class Extractor(Protocol):
    """What ontology learning needs from a model — nothing more.

    Keeping the surface this small is what lets an LLM, a heuristic, or a
    fine-tuned classifier be swapped without touching the pipeline, and is why
    the validation gates in :mod:`ontology_construction.pipeline` can sit
    between stages regardless of what produced the output.
    """

    name: str

    def type_terms(self, documents: list[str]) -> list[CandidateTerm]: ...

    def discover_taxonomy(self, terms: list[str],
                          documents: list[str]) -> list[TaxonomyEdge]: ...

    def extract_relations(self, pairs: list[tuple[str, str]],
                          documents: list[str]) -> list[RelationEdge]: ...


#: Suffix → semantic type. A crude stand-in for the type inventory a real
#: LLMs4OL run would draw from a target vocabulary.
TYPE_HINTS: dict[str, str] = {
    "ing": "Process", "tion": "Process", "ment": "Process", "ance": "Process",
    "er": "Agent", "or": "Agent", "ist": "Agent", "ant": "Agent",
    "ity": "Quality", "ness": "Quality", "ency": "Quality",
    "ology": "Discipline", "system": "System", "service": "Service",
    "agreement": "Document", "contract": "Document", "report": "Document",
}

#: Lexico-syntactic cues for non-taxonomic relations, with the predicate they
#: license. The report names ``causes`` and ``consists of`` explicitly.
RELATION_CUES: dict[str, str] = {
    "causes": "causes",
    "caused by": "causedBy",
    "consists of": "consistsOf",
    "composed of": "composedOf",
    "part of": "partOf",
    "contains": "contains",
    "requires": "requires",
    "depends on": "dependsOn",
    "issued by": "issuedBy",
    "issues": "issues",
    "owns": "owns",
    "owned by": "ownedBy",
    "governs": "governs",
    "governed by": "governedBy",
    "provides": "provides",
    "uses": "uses",
    "produces": "produces",
    "manages": "manages",
    "held by": "heldBy",
    "holds": "holds",
}

#: Hearst-style patterns for taxonomy discovery.
_HEARST = [
    re.compile(r"(?P<hyper>[\w \-]+?)\s+such as\s+(?P<hypos>[\w ,\-]+)", re.I),
    re.compile(r"(?P<hypos>[\w ,\-]+?)\s+and other\s+(?P<hyper>[\w \-]+)", re.I),
    re.compile(r"(?P<hyper>[\w \-]+?)(?:,)?\s+(?:especially|including)\s+(?P<hypos>[\w ,\-]+)", re.I),
    re.compile(r"(?P<hypo>[\w \-]+?)\s+is a(?:n)?\s+(?:kind|type|form)\s+of\s+(?P<hyper2>[\w \-]+)", re.I),
    re.compile(r"(?P<hypo2>[\w \-]+?)\s+is a(?:n)?\s+(?P<hyper3>[\w \-]+)", re.I),
]

_STOP = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is", "are",
    "was", "were", "be", "been", "that", "which", "with", "by", "as", "at",
    "it", "its", "this", "these", "those", "from", "can", "may", "must",
    "shall", "should", "we", "our", "their", "there", "each", "any", "all",
    "other", "such", "kind", "type", "form", "has", "have", "not", "but",
    "what", "who", "when", "where", "how", "does", "do", "who's", "whose",
}


def _norm(term: str) -> str:
    """Light normalisation — whitespace, surrounding punctuation, case.

    Deliberately does NOT drop stopwords. This is applied to terms an
    *extractor returned*, and a model answering "act of god" or "a" means it;
    silently rewriting its answer would corrupt the very output the gates are
    supposed to judge. Stopword filtering belongs in candidate generation only
    (:func:`_norm_candidate`).
    """
    return re.sub(r"\s+", " ", term.strip(" .,;:—-")).lower()


def _norm_candidate(term: str) -> str:
    """Normalisation *plus* stopword removal, for generated n-grams."""
    words = [w for w in _norm(term).split() if w not in _STOP]
    return " ".join(words)


#: Words that signal a relation, never part of a concept name.
_CUE_WORDS: frozenset[str] = frozenset(
    w for cue in (
        "causes caused consists composed part contains requires depends issued "
        "issues owns owned governs governed provides uses produces manages held "
        "holds offered secure pledged own require cause consist compose contain depend issue govern provide use produce manage hold").split() for w in (cue,))


def _singular(term: str) -> str:
    """Crude de-pluralisation.

    The ``-es`` rule fires only after a sibilant stem (``classes`` -> ``class``,
    ``boxes`` -> ``box``); applying it to ``causes`` would yield ``caus``, which
    is how a naive stemmer manufactures concepts that do not exist.
    """
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith(("sses", "xes", "zes", "ches", "shes")):
        return term[:-2]
    if term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def _longest_known_prefix(phrase: str, known: set[str]) -> str:
    """Trim a Hearst capture back to the longest known term it starts with.

    ``Loans such as mortgages and overdrafts are offered to customers`` yields
    the raw hyponym ``overdrafts are offered to customers``. The pattern cannot
    know where the noun phrase ends, so the vocabulary decides: take the longest
    word-prefix that is an extracted term. Without this the second hyponym of
    every ``such as`` list is silently lost.
    """
    if not known:
        return ""
    words = phrase.split()
    for n in range(len(words), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in known:
            return candidate
        singular = _singular(candidate)
        if singular in known:
            return singular
    return ""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# --------------------------------------------------------------------------- #
# Offline default
# --------------------------------------------------------------------------- #
@dataclass
class HeuristicExtractor:
    """Deterministic, dependency-free stand-in for an LLM.

    Faithful to the *structure* of the three LLMs4OL subtasks, not to their
    accuracy. Its job is to make the pipeline, the validation gates and the
    metrics runnable and testable offline; swap in :class:`LLMExtractor` for
    real work. This mirrors how :mod:`bottomup_ontology` treats its NLP steps.
    """

    name: str = "heuristic"
    min_frequency: int = 1
    max_terms: int = 60

    # -- task A ------------------------------------------------------------- #
    def type_terms(self, documents: list[str]) -> list[CandidateTerm]:
        freq: dict[str, int] = {}
        for doc in documents:
            for sent in _sentences(doc):
                # Split on anything that is not a letter, hyphen or space, then
                # keep whole words only — a character-capped run truncates
                # mid-word and manufactures terms like "overdrafts ar".
                for chunk in re.split(r"[^A-Za-z\- ]+", sent):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    for gram in _ngrams(chunk, 2):
                        t = _singular(_norm_candidate(gram))
                        if len(t) < 3 or " " in t and len(t.split()) > 3:
                            continue
                        if not t or t in _STOP:
                            continue
                        # A relation cue is not part of a concept name; without
                        # this, 2-grams spanning a verb produce non-terms such
                        # as "bank own" and "requires collateral".
                        if any(w in _CUE_WORDS for w in t.split()):
                            continue
                        freq[t] = freq.get(t, 0) + 1
        ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        out: list[CandidateTerm] = []
        total = sum(freq.values()) or 1
        for term, n in ranked:
            if n < self.min_frequency:
                continue
            out.append(CandidateTerm(
                label=term, type_label=self._type_of(term),
                score=round(n / total, 4), provenance=f"{self.name}:term_typing"))
            if len(out) >= self.max_terms:
                break
        return out

    @staticmethod
    def _type_of(term: str) -> str:
        head = term.split()[-1]
        for suffix, type_label in TYPE_HINTS.items():
            if head.endswith(suffix) or head == suffix:
                return type_label
        return "Entity"

    # -- task B ------------------------------------------------------------- #
    def discover_taxonomy(self, terms: list[str],
                          documents: list[str]) -> list[TaxonomyEdge]:
        known = {t.lower() for t in terms}
        edges: dict[tuple[str, str], TaxonomyEdge] = {}

        # (a) lexico-syntactic patterns
        for doc in documents:
            for sent in _sentences(doc):
                for pat in _HEARST:
                    for m in pat.finditer(sent):
                        gd = m.groupdict()
                        hyper = gd.get("hyper") or gd.get("hyper2") or gd.get("hyper3")
                        if not hyper:
                            continue
                        hyper_n = _singular(_norm(hyper))
                        hypos_raw = gd.get("hypos")
                        hypos = ([gd.get("hypo") or gd.get("hypo2")]
                                 if hypos_raw is None else
                                 re.split(r",| and ", hypos_raw))
                        for h in filter(None, hypos):
                            child = _longest_known_prefix(
                                _singular(_norm(h)), known) or _singular(_norm(h))
                            if not child or not hyper_n or child == hyper_n:
                                continue
                            if known and (child not in known or hyper_n not in known):
                                continue
                            key = (child, hyper_n)
                            edges.setdefault(key, TaxonomyEdge(
                                child=child, parent=hyper_n, score=0.9,
                                provenance=f"{self.name}:lexico-syntactic"))

        # (b) head-noun composition: "mortgage loan" is-a "loan"
        for term in terms:
            words = term.split()
            if len(words) < 2:
                continue
            head = words[-1]
            if head in known and head != term:
                edges.setdefault((term, head), TaxonomyEdge(
                    child=term, parent=head, score=0.6,
                    provenance=f"{self.name}:head-noun"))
        return list(edges.values())

    # -- task C ------------------------------------------------------------- #
    def extract_relations(self, pairs: list[tuple[str, str]],
                          documents: list[str]) -> list[RelationEdge]:
        wanted = {(a, b) for a, b in pairs}
        out: dict[tuple[str, str, str], RelationEdge] = {}
        for doc in documents:
            for sent in _sentences(doc):
                low = sent.lower()
                for cue, predicate in RELATION_CUES.items():
                    idx = low.find(f" {cue} ")
                    if idx < 0:
                        continue
                    left, right = low[:idx], low[idx + len(cue) + 2:]
                    for a, b in wanted:
                        if a in left and b in right:
                            key = (a, predicate, b)
                            out.setdefault(key, RelationEdge(
                                domain=a, predicate=predicate, range=b,
                                score=0.8,
                                provenance=f"{self.name}:cue '{cue}'"))
        return list(out.values())


def _ngrams(chunk: str, max_n: int) -> Iterable[str]:
    words = [w for w in chunk.split() if w]
    for n in range(1, max_n + 1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i:i + n])


# --------------------------------------------------------------------------- #
# The LLM drop-in
# --------------------------------------------------------------------------- #
@dataclass
class LLMExtractor:
    """Calls a real model behind the :class:`Extractor` interface.

    ``complete(prompt) -> str`` is the only thing it needs, so any SDK fits.
    Two design points carried over from the report:

    * ``strategy`` selects Axiom-by-Axiom or single-shot prompting, because the
      difference is measurable and AbA reportedly wins.
    * Nothing here trusts the model. Output is parsed defensively and every
      stage is gated downstream by
      :mod:`ontology_construction.validation` — the neuro-symbolic
      orchestration the report attributes to NeOn-GPT.
    """

    complete: Callable[[str], str]
    name: str = "llm"
    strategy: str = PromptingStrategy.AXIOM_BY_AXIOM
    max_calls: int = 200
    calls: int = field(default=0, init=False)

    # -- prompt templates --------------------------------------------------- #
    TERM_PROMPT = (
        "Extract domain concepts from the text and assign each a broad semantic "
        "type.\nReturn one per line as `term | type`. No commentary.\n\nTEXT:\n{text}")
    TAXONOMY_ABA_PROMPT = (
        "Considering only the text below, is `{child}` a subclass of `{parent}`?\n"
        "Answer exactly YES or NO.\n\nTEXT:\n{text}")
    TAXONOMY_SINGLE_PROMPT = (
        "Build the subclass hierarchy over these terms using only the text.\n"
        "Return one per line as `child | parent`. No commentary.\n\n"
        "TERMS: {terms}\n\nTEXT:\n{text}")
    RELATION_PROMPT = (
        "Which relation, if any, does the text state between `{a}` and `{b}`?\n"
        "Answer with a single lowerCamelCase predicate, or NONE.\n\nTEXT:\n{text}")

    def _ask(self, prompt: str) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError(
                f"{self.name}: call budget of {self.max_calls} exhausted — "
                "the report's 'quadratic complexity' warning made concrete")
        self.calls += 1
        return self.complete(prompt)

    def type_terms(self, documents: list[str]) -> list[CandidateTerm]:
        text = "\n".join(documents)[:12000]
        out: list[CandidateTerm] = []
        for line in self._ask(self.TERM_PROMPT.format(text=text)).splitlines():
            if "|" not in line:
                continue
            label, _, type_label = line.partition("|")
            label, type_label = _norm(label), type_label.strip() or "Entity"
            if label:
                out.append(CandidateTerm(label=label, type_label=type_label,
                                         score=1.0,
                                         provenance=f"{self.name}:term_typing"))
        return out

    def discover_taxonomy(self, terms: list[str],
                          documents: list[str]) -> list[TaxonomyEdge]:
        text = "\n".join(documents)[:12000]
        if self.strategy == PromptingStrategy.SINGLE_SHOT:
            reply = self._ask(self.TAXONOMY_SINGLE_PROMPT.format(
                terms=", ".join(terms), text=text))
            out = []
            for line in reply.splitlines():
                if "|" not in line:
                    continue
                child, _, parent = line.partition("|")
                child, parent = _norm(child), _norm(parent)
                if child and parent and child != parent:
                    out.append(TaxonomyEdge(child, parent, 1.0,
                                            f"{self.name}:single-shot"))
            return out
        out = []
        for child in terms:
            for parent in terms:
                if child == parent:
                    continue
                reply = self._ask(self.TAXONOMY_ABA_PROMPT.format(
                    child=child, parent=parent, text=text))
                if reply.strip().upper().startswith("YES"):
                    out.append(TaxonomyEdge(child, parent, 1.0,
                                            f"{self.name}:axiom-by-axiom"))
        return out

    def extract_relations(self, pairs: list[tuple[str, str]],
                          documents: list[str]) -> list[RelationEdge]:
        text = "\n".join(documents)[:12000]
        out = []
        for a, b in pairs:
            reply = self._ask(self.RELATION_PROMPT.format(a=a, b=b, text=text)).strip()
            if reply and reply.upper() != "NONE":
                out.append(RelationEdge(a, reply.split()[0], b, 1.0,
                                        f"{self.name}:relation"))
        return out


# --------------------------------------------------------------------------- #
# Bounding the quadratic blow-up
# --------------------------------------------------------------------------- #
def candidate_pairs(terms: list[str], documents: list[str], *,
                    max_pairs: int = 200) -> tuple[list[tuple[str, str]], dict]:
    """Term pairs worth asking about, plus a report of what the bound cost.

    Zero-shot relation prediction over *n* terms is O(n²); the report calls this
    "computationally unscalable". Restricting candidates to terms that actually
    co-occur in a sentence collapses the space, and returning the budget report
    keeps the truncation visible instead of silent.
    """
    n = len(terms)
    theoretical = n * (n - 1)
    co: dict[tuple[str, str], int] = {}
    for doc in documents:
        for sent in _sentences(doc):
            low = sent.lower()
            present = [t for t in terms if t in low]
            for i, a in enumerate(present):
                for b in present:
                    if a == b:
                        continue
                    co[(a, b)] = co.get((a, b), 0) + 1
    ranked = sorted(co.items(), key=lambda kv: (-kv[1], kv[0]))
    pairs = [p for p, _ in ranked[:max_pairs]]
    report = {
        "terms": n,
        "theoretical_pairs": theoretical,
        "cooccurring_pairs": len(co),
        "evaluated_pairs": len(pairs),
        "truncated": max(0, len(co) - len(pairs)),
        "reduction": (round(1 - len(pairs) / theoretical, 4) if theoretical else 0.0),
    }
    return pairs, report


# --------------------------------------------------------------------------- #
# Step functions
# --------------------------------------------------------------------------- #
def step_term_typing(state: ConstructionState, *,
                     extractor: Extractor | None = None,
                     max_terms: int | None = None) -> ConstructionState:
    """LLMs4OL task A — term extraction and typing."""
    ex = extractor or HeuristicExtractor()
    found = ex.type_terms(state.documents)
    if max_terms is not None:
        found = found[:max_terms]
    known = {t.label for t in state.candidate_terms}
    added = [t for t in found if t.label not in known]
    state.candidate_terms.extend(added)
    state.record("llms4ol.term_typing", bool(state.candidate_terms),
                 f"{len(added)} new terms via {ex.name} "
                 f"({len(state.candidate_terms)} total)")
    return state


def step_taxonomy_discovery(state: ConstructionState, *,
                            extractor: Extractor | None = None,
                            min_score: float = 0.0) -> ConstructionState:
    """LLMs4OL task B — induce the ``is-a`` backbone."""
    ex = extractor or HeuristicExtractor()
    terms = [t.label for t in state.accepted_terms()]
    edges = [e for e in ex.discover_taxonomy(terms, state.documents)
             if e.score >= min_score]
    known = {e.as_pair() for e in state.taxonomy_edges}
    added = [e for e in edges if e.as_pair() not in known]
    state.taxonomy_edges.extend(added)
    state.record("llms4ol.taxonomy_discovery", True,
                 f"{len(added)} subclass edges via {ex.name}")
    return state


def step_relation_extraction(state: ConstructionState, *,
                             extractor: Extractor | None = None,
                             max_pairs: int = 200) -> ConstructionState:
    """LLMs4OL task C — non-taxonomic relations, with the O(n²) bound made explicit."""
    ex = extractor or HeuristicExtractor()
    terms = [t.label for t in state.accepted_terms()]
    pairs, budget = candidate_pairs(terms, state.documents, max_pairs=max_pairs)
    state.reports["relation_budget"] = budget
    edges = ex.extract_relations(pairs, state.documents)
    known = {r.as_triple() for r in state.relation_edges}
    added = [r for r in edges if r.as_triple() not in known]
    state.relation_edges.extend(added)
    state.record(
        "llms4ol.relation_extraction", True,
        f"{len(added)} relations via {ex.name}; evaluated "
        f"{budget['evaluated_pairs']} of {budget['theoretical_pairs']} possible "
        f"pairs ({budget['reduction']:.1%} reduction)")
    return state
