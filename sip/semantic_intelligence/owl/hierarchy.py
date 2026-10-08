"""Hierarchy providers — Protégé's ``OWLObjectHierarchyProvider`` family.

``AssertedClassHierarchyProvider`` (protege-editor-owl,
``org.protege.editor.owl.model.hierarchy``) defines the *asserted* class tree:

* the parents of ``C`` are the named classes ``D`` with ``SubClassOf(C, D)``, plus
  the **named conjuncts** of any intersection ``C`` is declared *equivalent* to
  (``C ≡ D ⊓ ∃r.E`` puts ``C`` under ``D``) — this is why a defined class shows up
  in the tree beneath its genus rather than floating at the root;
* a class with no named parent is a child of ``owl:Thing``;
* equivalent named classes are shown as one node in the tree, not as each other's
  parent;
* cycles (``A ⊑ B ⊑ A``) are tolerated: traversal carries a visited set.

``InferredOWLClassHierarchyProvider`` is the same interface over a reasoner; here
it is the same class built over the *inferred* graph (``main ∪ inferred``), see
``reasoning.manager``.

Property trees work the same way over ``rdfs:subPropertyOf`` with
``owl:topObjectProperty`` / ``owl:topDataProperty`` as roots, as in
``OWLObjectPropertyHierarchyProvider``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Iterator

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from .model import And, UnsupportedConstruct, parse_ce


class ClassHierarchy:
    ROOT = OWL.Thing

    def __init__(self, graph: Graph, *, use_equivalent_conjuncts: bool = True) -> None:
        self.graph = graph
        self.use_equivalent_conjuncts = use_equivalent_conjuncts
        self.rebuild()

    def rebuild(self) -> None:
        g = self.graph
        self._parents: dict[URIRef, set[URIRef]] = defaultdict(set)
        self._children: dict[URIRef, set[URIRef]] = defaultdict(set)
        self._equiv: dict[URIRef, set[URIRef]] = defaultdict(set)
        classes: set[URIRef] = {c for t in (OWL.Class, RDFS.Class)
                                for c in g.subjects(RDF.type, t) if isinstance(c, URIRef)}
        for s, o in g.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef):
                classes.add(s)
                if isinstance(o, URIRef):
                    classes.add(o)
                    if o != s:
                        self._parents[s].add(o)
        for s, o in g.subject_objects(OWL.equivalentClass):
            for a, b in ((s, o), (o, s)):
                if not isinstance(a, URIRef):
                    continue
                classes.add(a)
                if isinstance(b, URIRef):
                    if a != b:
                        self._equiv[a].add(b)
                elif self.use_equivalent_conjuncts:
                    try:
                        ce = parse_ce(g, b)
                    except UnsupportedConstruct:
                        continue
                    if isinstance(ce, And):
                        for op in ce.operands:
                            if isinstance(op, URIRef) and op != a:
                                self._parents[a].add(op)
                                classes.add(op)
        classes.discard(OWL.Thing)
        classes.discard(OWL.Nothing)
        self.classes = classes
        for c in classes:
            ps = {p for p in self._parents.get(c, set()) if p != OWL.Thing}
            # equivalents share parents; a parent that is merely equivalent is not one
            ps -= self._equiv.get(c, set())
            if not ps:
                ps = {OWL.Thing}
            self._parents[c] = ps
            for p in ps:
                self._children[p].add(c)

    # -- the provider interface -------------------------------------------- #
    def roots(self) -> list[URIRef]:
        return sorted(self._children.get(OWL.Thing, set()))

    def parents(self, c: URIRef) -> list[URIRef]:
        return sorted(self._parents.get(c, set()))

    def children(self, c: URIRef) -> list[URIRef]:
        return sorted(self._children.get(c, set()))

    def equivalents(self, c: URIRef) -> list[URIRef]:
        return sorted(self._equiv.get(c, set()))

    def ancestors(self, c: URIRef) -> set[URIRef]:
        return self._closure(c, self._parents)

    def descendants(self, c: URIRef) -> set[URIRef]:
        return self._closure(c, self._children)

    @staticmethod
    def _closure(c, edges) -> set[URIRef]:
        out: set[URIRef] = set()
        stack = list(edges.get(c, ()))
        while stack:
            n = stack.pop()
            if n in out:
                continue
            out.add(n)
            stack.extend(edges.get(n, ()))
        out.discard(c)
        return out

    def paths_to_root(self, c: URIRef, limit: int = 20) -> list[list[URIRef]]:
        """Every path from *c* up to ``owl:Thing`` (``getPathsToRoot`` — used to
        reveal a search hit in the tree)."""
        out: list[list[URIRef]] = []

        def walk(n: URIRef, path: list[URIRef]) -> None:
            if len(out) >= limit:
                return
            if n == OWL.Thing:
                out.append(list(reversed(path + [n])))
                return
            for p in self.parents(n):
                if p not in path:
                    walk(p, path + [n])
        walk(c, [])
        return out

    def cycles(self) -> list[list[URIRef]]:
        """Subclass cycles — reported by the quality layer, tolerated here."""
        seen, out = set(), []
        for c in self.classes:
            if c in seen:
                continue
            if c in self.ancestors(c) or any(c in self.ancestors(p) for p in self.parents(c)):
                cyc = sorted({c} | {a for a in self.ancestors(c) if c in self.ancestors(a)})
                seen.update(cyc)
                out.append(cyc)
        return out

    def instances(self, c: URIRef, *, direct: bool = True) -> list[URIRef]:
        classes = {c} if direct else {c} | self.descendants(c)
        return sorted({i for k in classes for i in self.graph.subjects(RDF.type, k)
                       if isinstance(i, URIRef)})

    def tree(self, root: URIRef | None = None, depth: int = 50) -> dict:
        """Nested ``{iri: {child: …}}`` — for notebooks and the API."""
        root = root or OWL.Thing

        def build(n, d, seen):
            if d == 0 or n in seen:
                return {}
            return {ch: build(ch, d - 1, seen | {n}) for ch in self.children(n)}
        return {root: build(root, depth, frozenset())}


class PropertyHierarchy:
    """Object / data / annotation property trees."""

    TOPS = {"object": OWL.topObjectProperty, "data": OWL.topDataProperty,
            "annotation": None}
    TYPES = {"object": (OWL.ObjectProperty, OWL.TransitiveProperty, OWL.SymmetricProperty,
                        OWL.InverseFunctionalProperty, OWL.AsymmetricProperty,
                        OWL.ReflexiveProperty, OWL.IrreflexiveProperty),
             "data": (OWL.DatatypeProperty,),
             "annotation": (OWL.AnnotationProperty,)}

    def __init__(self, graph: Graph, kind: str = "object") -> None:
        if kind not in self.TYPES:
            raise ValueError(f"kind must be one of {sorted(self.TYPES)}")
        self.graph, self.kind = graph, kind
        self.rebuild()

    def rebuild(self) -> None:
        g = self.graph
        props = {p for t in self.TYPES[self.kind] for p in g.subjects(RDF.type, t)
                 if isinstance(p, URIRef)}
        top = self.TOPS[self.kind]
        self._parents: dict[URIRef, set[URIRef]] = defaultdict(set)
        self._children: dict[URIRef, set[URIRef]] = defaultdict(set)
        for s, o in g.subject_objects(RDFS.subPropertyOf):
            if s in props and isinstance(o, URIRef) and o != s:
                self._parents[s].add(o)
        self.properties = props - {top}
        for p in self.properties:
            ps = self._parents.get(p) or {top}
            self._parents[p] = ps
            for q in ps:
                self._children[q].add(p)

    def roots(self) -> list[URIRef]:
        return sorted(x for x in self._children.get(self.TOPS[self.kind], set()) if x)

    def parents(self, p: URIRef) -> list[URIRef]:
        return sorted(x for x in self._parents.get(p, set()) if x)

    def children(self, p: URIRef) -> list[URIRef]:
        return sorted(self._children.get(p, set()))


def individuals_by_type(graph: Graph) -> dict[URIRef, list[URIRef]]:
    """Protégé's *Individuals by class* view."""
    out: dict[URIRef, list[URIRef]] = defaultdict(list)
    for i, t in graph.subject_objects(RDF.type):
        if isinstance(i, URIRef) and isinstance(t, URIRef) and t not in (
                OWL.NamedIndividual, OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                OWL.AnnotationProperty, OWL.Ontology, RDFS.Class, RDF.Property):
            if (t, RDF.type, OWL.Class) in graph or (t, RDF.type, RDFS.Class) in graph:
                out[t].append(i)
    return {k: sorted(v) for k, v in out.items()}
