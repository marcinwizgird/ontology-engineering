"""A typed TBox edge index over an rdflib graph.

Every named class (and SKOS concept) is a node. Axioms become typed edges where a
diagram can show them honestly, following Chowlk's convention of tagging restrictions
on the edge instead of drawing blank-node vertices:

==================  ===================================================  ===============
kind                source axiom                                         drawn as
==================  ===================================================  ===============
subClassOf          ``C ⊑ D`` (and ``C ≡ D ⊓ …`` operands, via ``≡``)     solid arrow
equivalentClass     ``C ≡ D`` with D named                               double line
restriction         ``C ⊑ ∃p.D`` / ``∀p.D`` / ``≥n p.D`` (n > 0) …      tagged arrow
optional            ``C ⊑ ≥0 p.D``: a tautology FIBO uses to document     off by default
                    expected properties; no logical constraint
objectProperty      ``p`` with named ``rdfs:domain`` C and ``rdfs:range`` D  labelled arrow
disjointWith        ``C ⊓ D ⊑ ⊥`` (pairwise)                             dotted, off by default
broader             ``skos:broader`` (``skos:narrower`` flipped)         solid arrow
==================  ===================================================  ===============

Anything more nested (unions outside a filler, complements, nested restrictions,
``oneOf``) is not forced into a picture: it becomes a *badge* on the node whose text is
the Manchester rendering (the OWLGrEd lesson). Data restrictions become attributes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from . import _paths  # noqa: F401
from semantic_intelligence.owl import manchester
from semantic_intelligence.owl.model import (And, Card, HasSelf, HasValue, Inverse, Only, Or,
                                             Some, UnsupportedConstruct, parse_ce)
from semantic_intelligence.owl.rendering import ShortFormProvider, local_name

EDGE_KINDS = ("subClassOf", "equivalentClass", "restriction", "optional", "objectProperty",
              "disjointWith", "broader")
DEFAULT_KINDS = ("subClassOf", "equivalentClass", "restriction", "objectProperty", "broader")
_BUILTIN = (str(OWL), str(RDFS), str(RDF), "http://www.w3.org/2001/XMLSchema#")
_SKIP = {OWL.Thing, OWL.Nothing, RDFS.Resource}


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str
    label: str = ""          # property label (restriction / objectProperty)
    tag: str = ""            # some | only | min 1 | exactly 1 | ...
    prop: str = ""           # property IRI
    via: str = ""            # "" | "≡" (from a definition) | "or" (union filler)

    @property
    def key(self) -> tuple[str, ...]:
        return (self.source, self.kind, self.prop, self.tag, self.target)

    @property
    def id(self) -> str:
        return "|".join(self.key)

    @property
    def text(self) -> str:
        if self.kind in ("restriction", "optional"):
            return f"{self.label} ({self.tag})" + (" [or]" if self.via == "or" else "")
        return self.label or self.kind


@dataclass
class Node:
    iri: str
    label: str
    kind: str = "class"                  # class | concept
    module: str = ""                     # the IRI's namespace
    description: str = ""
    attributes: list[str] = field(default_factory=list)
    complex: list[str] = field(default_factory=list)
    defined: bool = False
    instances: int = 0
    deprecated: bool = False


def namespace(iri: str) -> str:
    i = max(iri.rfind("#"), iri.rfind("/"))
    return iri[:i + 1] if i > 0 else iri


def module_label(ns: str) -> str:
    parts = [p for p in ns.rstrip("/#").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else ns)


def _text(g: Graph, s, preds, langs=("en", "")) -> str:
    best: dict[str, str] = {}
    for p in preds:
        for o in g.objects(s, p):
            if isinstance(o, Literal):
                best.setdefault(o.language or "", str(o))
        for lang in langs:
            if lang in best:
                return best[lang]
    return next(iter(best.values()), "")


class OntologyIndex:
    """Nodes, typed edges and an undirected adjacency over one graph."""

    def __init__(self, g: Graph, languages: tuple[str, ...] = ("en", "")) -> None:
        self.graph = g
        self.languages = languages
        self.sfp = ShortFormProvider(g)
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple, Edge] = {}
        self.adj: dict[str, list[tuple[str, Edge]]] = defaultdict(list)
        self._build()

    # ------------------------------------------------------------------ #
    def _named(self, x) -> bool:
        return isinstance(x, URIRef) and x not in _SKIP and not str(x).startswith(_BUILTIN)

    def _node(self, iri: URIRef, kind: str = "class") -> Node:
        n = self.nodes.get(str(iri))
        if n is None:
            g = self.graph
            n = Node(str(iri), _text(g, iri, (RDFS.label, SKOS.prefLabel), self.languages)
                     or local_name(str(iri)), kind, namespace(str(iri)),
                     _text(g, iri, (SKOS.definition, RDFS.comment), self.languages)[:400],
                     deprecated=(iri, OWL.deprecated, Literal(True)) in g)
            self.nodes[str(iri)] = n
        return n

    def _edge(self, e: Edge) -> None:
        if e.source == e.target or e.key in self.edges:
            return
        self.edges[e.key] = e

    def _plabel(self, p) -> str:
        if isinstance(p, Inverse):
            return "inverse " + self._plabel(p.prop)
        return _text(self.graph, p, (RDFS.label,), self.languages) or local_name(str(p))

    def _manchester(self, ce) -> str:
        try:
            return manchester.render(ce, self.sfp)
        except Exception:  # noqa: BLE001 - a badge must never break the index
            return repr(ce)

    def _build(self) -> None:
        g = self.graph
        classes: set[URIRef] = set()
        for t in (OWL.Class, RDFS.Class):
            classes |= {c for c in g.subjects(RDF.type, t) if self._named(c)}
        for s, o in g.subject_objects(RDFS.subClassOf):
            classes |= {x for x in (s, o) if self._named(x)}
        for c in sorted(classes):
            self._node(c)
        for c in {c for c in g.subjects(RDF.type, SKOS.Concept) if self._named(c)}:
            self._node(c, "concept")

        for c in sorted(classes):
            for o in g.objects(c, RDFS.subClassOf):
                self._axiom(c, o, equivalent=False)
            for o in g.objects(c, OWL.equivalentClass):
                self._axiom(c, o, equivalent=True)
            for o in g.objects(c, OWL.disjointWith):
                if self._named(o):
                    self._node(o)
                    self._edge(Edge(str(c), str(o), "disjointWith"))

        for p in sorted(set(g.subjects(RDF.type, OWL.ObjectProperty))):
            doms = [d for d in g.objects(p, RDFS.domain) if self._named(d)]
            rans = [r for r in g.objects(p, RDFS.range) if self._named(r)]
            for d in doms:
                for r in rans:
                    self._node(d), self._node(r)
                    self._edge(Edge(str(d), str(r), "objectProperty", self._plabel(p),
                                    prop=str(p)))

        for s, o in g.subject_objects(SKOS.broader):
            if self._named(s) and self._named(o):
                self._node(s, "concept"), self._node(o, "concept")
                self._edge(Edge(str(s), str(o), "broader"))
        for s, o in g.subject_objects(SKOS.narrower):
            if self._named(s) and self._named(o):
                self._node(s, "concept"), self._node(o, "concept")
                self._edge(Edge(str(o), str(s), "broader"))

        for i, t in g.subject_objects(RDF.type):
            n = self.nodes.get(str(t))
            if n is not None and isinstance(i, URIRef) and t not in (OWL.Class, RDFS.Class):
                n.instances += 1

        for e in self.edges.values():
            self.adj[e.source].append((e.target, e))
            self.adj[e.target].append((e.source, e))
        self.max_degree = max((len(v) for v in self.adj.values()), default=1)

    # ------------------------------------------------------------------ #
    def _axiom(self, c: URIRef, o, equivalent: bool) -> None:
        node = self.nodes[str(c)]
        if isinstance(o, URIRef):
            if self._named(o):
                self._node(o)
                self._edge(Edge(str(c), str(o), "equivalentClass" if equivalent
                                else "subClassOf"))
            return
        if not isinstance(o, BNode):
            return
        try:
            ce = parse_ce(self.graph, o)
        except UnsupportedConstruct as exc:
            node.complex.append(f"unsupported: {exc}")
            return
        if equivalent:
            node.defined = True
        via = "≡" if equivalent else ""
        if isinstance(ce, And):
            for op in ce.operands:
                if not self._part(c, op, via):
                    node.complex.append(("EquivalentTo: " if equivalent else "SubClassOf: ")
                                        + self._manchester(op))
        elif not self._part(c, ce, via):
            node.complex.append(("EquivalentTo: " if equivalent else "SubClassOf: ")
                                + self._manchester(ce))

    def _part(self, c: URIRef, ce, via: str) -> bool:
        """Draw one conjunct as an edge or attribute; False means 'too complex: badge it'."""
        node = self.nodes[str(c)]
        if isinstance(ce, URIRef):
            if self._named(ce):
                self._node(ce)
                self._edge(Edge(str(c), str(ce), "subClassOf", via=via))
            return True
        if isinstance(ce, (Some, Only, Card)):
            tag = ("some" if isinstance(ce, Some) else "only" if isinstance(ce, Only)
                   else f"{ce.kind} {ce.n}")
            filler = ce.filler
            if ce.data or filler is None or (isinstance(ce, Card) and filler is None):
                node.attributes.append(self._manchester(ce))
                return True
            pl, pi = self._plabel(ce.prop), str(ce.prop.prop if isinstance(ce.prop, Inverse)
                                                else ce.prop)
            if isinstance(filler, URIRef):
                if not self._named(filler):
                    node.attributes.append(self._manchester(ce))
                    return True
                self._node(filler)
                kind = "optional" if isinstance(ce, Card) and ce.kind == "min" and ce.n == 0                     else "restriction"
                self._edge(Edge(str(c), str(filler), kind, pl, tag, pi, via))
                return True
            if isinstance(filler, Or) and all(isinstance(x, URIRef) for x in filler.operands):
                for x in filler.operands:
                    if self._named(x):
                        self._node(x)
                        self._edge(Edge(str(c), str(x), "restriction", pl, tag, pi, "or"))
                return True
            return False
        if isinstance(ce, (HasValue, HasSelf)):
            node.attributes.append(self._manchester(ce))
            return True
        return False

    # ------------------------------------------------------------------ #
    def neighbours(self, iri: str, kinds=DEFAULT_KINDS) -> list[tuple[str, Edge]]:
        return [(m, e) for m, e in self.adj.get(iri, ()) if e.kind in kinds]

    def degree(self, iri: str, kinds=DEFAULT_KINDS) -> int:
        return len({m for m, _ in self.neighbours(iri, kinds)})

    def api(self, iri: str) -> float:
        """A-priori interest in [0, 1]: log-scaled degree (van Ham & Perer's API term)."""
        return math.log1p(len(self.adj.get(iri, ()))) / math.log1p(max(self.max_degree, 1))

    def search(self, text: str, limit: int = 20) -> list[Node]:
        t = text.strip().lower()
        if not t:
            return []
        hits = []
        for n in self.nodes.values():
            lab, ln = n.label.lower(), local_name(n.iri).lower()
            if t in lab or t in ln:
                rank = 0 if t in (lab, ln) else 1 if lab.startswith(t) or ln.startswith(t) else 2
                hits.append((rank, len(lab), lab, n))
        return [h[-1] for h in sorted(hits, key=lambda h: h[:3])[:limit]]

    def stats(self) -> dict:
        by_kind: dict[str, int] = defaultdict(int)
        for e in self.edges.values():
            by_kind[e.kind] += 1
        return {"nodes": len(self.nodes), "edges": len(self.edges),
                "edges_by_kind": dict(sorted(by_kind.items())),
                "badged_nodes": sum(1 for n in self.nodes.values() if n.complex),
                "max_degree": self.max_degree}
