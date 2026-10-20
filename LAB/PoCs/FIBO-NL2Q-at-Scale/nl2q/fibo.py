"""Full FIBO as the grounding search space.

Loads every FIBO RDF/XML module once (≈300 files) and caches the merged graph as
N-Triples. Exposes the lexical knowledge used for grounding and alignment:

* classes and properties with labels, ``skos:definition``, ``cmns-av:explanatoryNote``,
  synonyms and abbreviations;
* ``rdfs:subClassOf`` (named superclasses) and **restriction edges**: for
  ``C ⊑ ∃p.D`` / ``C ⊑ ∀p.D`` / qualified cardinalities, the allowed edge ``C -p-> D``.
  FIBO states most of its structure this way (≈3.2k restrictions vs ≈0.8k
  ``rdfs:domain``), so a domain/range-only view sees a fraction of it.
"""

from __future__ import annotations

import pickle
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from rdflib import BNode, Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from . import paths

CMNS_AV = Namespace("https://www.omg.org/spec/Commons/AnnotationVocabulary/")
TEXT_PROPS = {
    "label": [RDFS.label, SKOS.prefLabel],
    "definition": [SKOS.definition],
    "note": [CMNS_AV.explanatoryNote, SKOS.scopeNote, RDFS.comment],
    "synonym": [CMNS_AV.synonym, SKOS.altLabel],
    "abbreviation": [CMNS_AV.abbreviation],
}


@dataclass
class Term:
    iri: str
    kind: str                                  # class | object | datatype
    label: str = ""
    definition: str = ""
    note: str = ""
    synonyms: list[str] = field(default_factory=list)
    abbreviations: list[str] = field(default_factory=list)

    @property
    def local(self) -> str:
        return re.split(r"[/#]", self.iri.rstrip("/#"))[-1]


@dataclass
class Fibo:
    terms: dict[str, Term]
    subclass: dict[str, set[str]]             # class -> named superclasses
    edges: list[tuple[str, str, str]]         # (class, property, class) allowed by axioms
    domain: dict[str, set[str]]
    range: dict[str, set[str]]

    def text(self, iri: str) -> str:
        t = self.terms.get(iri)
        if t is None:
            return ""
        return " ".join(x for x in [t.label, " ".join(t.synonyms), " ".join(t.abbreviations),
                                    t.definition, t.note] if x)


def _first(g: Graph, s, props) -> str:
    for p in props:
        for o in g.objects(s, p):
            if getattr(o, "language", None) in (None, "en", "en-US"):
                return str(o)
    return ""


def _all(g: Graph, s, props) -> list[str]:
    return sorted({str(o) for p in props for o in g.objects(s, p)})


def parse_graph() -> Graph:
    g = Graph()
    files = sorted(p for p in paths.FIBO_DIR.rglob("*.rdf") if "etc" not in p.parts)
    for f in files:
        try:
            g.parse(f, format="xml")
        except Exception as exc:  # noqa: BLE001 - a broken module must not stop the load
            print(f"skip {f.name}: {exc}")
    return g


def _restriction_edges(g: Graph) -> list[tuple[str, str, str]]:
    out = []
    for c, r in g.subject_objects(RDFS.subClassOf):
        if not isinstance(r, BNode) or not isinstance(c, URIRef):
            continue
        p = g.value(r, OWL.onProperty)
        if not isinstance(p, URIRef):
            continue
        for filler_prop in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass):
            d = g.value(r, filler_prop)
            if isinstance(d, URIRef) and (d, RDF.type, OWL.Class) in g:
                out.append((str(c), str(p), str(d)))
    return out


def build() -> Fibo:
    g = parse_graph()
    terms: dict[str, Term] = {}
    for kind, typ in (("class", OWL.Class), ("object", OWL.ObjectProperty),
                      ("datatype", OWL.DatatypeProperty)):
        for s in g.subjects(RDF.type, typ):
            if not isinstance(s, URIRef):
                continue
            terms[str(s)] = Term(str(s), kind, _first(g, s, TEXT_PROPS["label"]),
                                 _first(g, s, TEXT_PROPS["definition"]),
                                 _first(g, s, TEXT_PROPS["note"]),
                                 _all(g, s, TEXT_PROPS["synonym"]),
                                 _all(g, s, TEXT_PROPS["abbreviation"]))
    sub: dict[str, set[str]] = defaultdict(set)
    for c, d in g.subject_objects(RDFS.subClassOf):
        if isinstance(c, URIRef) and isinstance(d, URIRef):
            sub[str(c)].add(str(d))
    dom, rng = defaultdict(set), defaultdict(set)
    for p, c in g.subject_objects(RDFS.domain):
        if isinstance(c, URIRef):
            dom[str(p)].add(str(c))
    for p, c in g.subject_objects(RDFS.range):
        if isinstance(c, URIRef):
            rng[str(p)].add(str(c))
    return Fibo(terms, dict(sub), _restriction_edges(g), dict(dom), dict(rng))


@lru_cache(maxsize=1)
def load() -> Fibo:
    cache = paths.CACHE / "fibo.pkl"
    if cache.exists():
        with cache.open("rb") as fh:
            return pickle.load(fh)
    t0 = time.time()
    f = build()
    paths.CACHE.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as fh:
        pickle.dump(f, fh)
    print(f"FIBO: {len(f.terms)} terms, {len(f.edges)} restriction edges ({time.time() - t0:.0f}s)")
    return f


def squash(s: str) -> str:
    """Case- and separator-insensitive key: 'Listed Security' / 'ListedSecurity' /
    'LISTEDSECURITY' -> 'listedsecurity'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache(maxsize=1)
def squash_index() -> dict[str, list[str]]:
    """squash(label | local name | synonym) -> IRIs."""
    f = load()
    idx: dict[str, list[str]] = defaultdict(list)
    for t in f.terms.values():
        for key in {squash(t.local), squash(t.label), *map(squash, t.synonyms)}:
            if key and t.iri not in idx[key]:
                idx[key].append(t.iri)
    return dict(idx)


@lru_cache(maxsize=1)
def vocabulary() -> dict[str, int]:
    """Word frequencies from FIBO labels and local names: the dictionary for segmenting
    FIBEN's upper-case identifiers."""
    f = load()
    freq: dict[str, int] = defaultdict(int)
    for t in f.terms.values():
        words = re.findall(r"[A-Za-z][a-z]+|[A-Z]+(?![a-z])", t.local) + re.findall(r"[A-Za-z]+", t.label)
        for w in words:
            freq[w.lower()] += 1
    return dict(freq)
