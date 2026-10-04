"""SKOS and SKOS-XL — Semantic Turkey's ``SKOS`` (43 ops) and ``SKOSXL`` (13 ops)
services, as reads over a graph and change-set generators.

Semantics kept from the source (``SVC/SKOS.java``, ``SVC/SKOSXL.java``):

* **Hierarchy path** = ``skos:broader`` ∪ ``^skos:narrower`` plus their
  sub-properties, *excluding* ``skos:broadMatch``/``skos:narrowMatch``
  (``preparePropPathForHierarchicalForQuery``). ``skos:broaderTransitive`` is a
  *super*-property of broader and is therefore not followed.
* **Top concepts with a scheme** are the *explicitly declared* ones
  (``skos:topConceptOf`` / ``^skos:hasTopConcept``), not "concepts without a
  broader". Without a scheme, a top concept is a typed concept with no typed broader.
* ``more`` = the node has a narrower (restricted to the schemes when given).
* ``createConcept``: pref-label clash (same prefLabel + language on another concept
  sharing a scheme) and pref/alt clash checks; ``skos:topConceptOf`` for each
  scheme **only if** no broader is given.
* ``setPrefLabel`` **demotes** an existing prefLabel in the same language to
  altLabel (one prefLabel per language, SKOS S14).
* ``removeBroaderConcept`` removes both directions (broader and inverse narrower).
* ``deleteConcept`` refuses while the concept has narrower concepts and cascades
  owned SKOS-XL labels.
* SKOS-XL ``setPrefLabel`` moves existing same-language xl prefLabels to
  ``skosxl:altLabel``; ``removeXLabel`` destroys the reified label entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ..core.changes import ChangeSet
from ..core.namespaces import SKOSXL


class LabelClash(ValueError):
    """``PrefPrefLabelClashException`` / ``PrefAltLabelClashException``."""


class PreconditionFailed(ValueError):
    """e.g. ``ConceptWithNarrowerConceptsException``."""


def _sub_props(g: Graph, prop: URIRef, exclude: set[URIRef]) -> set[URIRef]:
    out, stack = {prop}, [prop]
    while stack:
        p = stack.pop()
        for s in g.subjects(RDFS.subPropertyOf, p):
            if isinstance(s, URIRef) and s not in out and s not in exclude:
                out.add(s)
                stack.append(s)
    return out


def _sub_classes(g: Graph, cls: URIRef) -> set[URIRef]:
    out, stack = {cls}, [cls]
    while stack:
        c = stack.pop()
        for s in g.subjects(RDFS.subClassOf, c):
            if isinstance(s, URIRef) and s not in out:
                out.add(s)
                stack.append(s)
    return out


@dataclass
class TreeNode:
    iri: URIRef
    more: bool
    label: str | None = None


class SkosService:
    def __init__(self, graph: Graph, *, lexicalization: str = "skos",
                 include_sub_properties: bool = True) -> None:
        if lexicalization not in ("skos", "skosxl"):
            raise ValueError("lexicalization is 'skos' or 'skosxl'")
        self.g = graph
        self.lexicalization = lexicalization
        self.include_sub_properties = include_sub_properties

    # ------------------------------------------------------------------ #
    # the hierarchy relation
    # ------------------------------------------------------------------ #
    def _broader_props(self) -> set[URIRef]:
        if not self.include_sub_properties:
            return {SKOS.broader}
        return _sub_props(self.g, SKOS.broader, {SKOS.broadMatch})

    def _narrower_props(self) -> set[URIRef]:
        if not self.include_sub_properties:
            return {SKOS.narrower}
        return _sub_props(self.g, SKOS.narrower, {SKOS.narrowMatch})

    def broaders(self, c: URIRef) -> set[URIRef]:
        out = {o for p in self._broader_props() for o in self.g.objects(c, p)}
        out |= {s for p in self._narrower_props() for s in self.g.subjects(p, c)}
        return {x for x in out if isinstance(x, URIRef)}

    def narrowers(self, c: URIRef) -> set[URIRef]:
        out = {s for p in self._broader_props() for s in self.g.subjects(p, c)}
        out |= {o for p in self._narrower_props() for o in self.g.objects(c, p)}
        return {x for x in out if isinstance(x, URIRef)}

    def concepts(self) -> set[URIRef]:
        return {c for k in _sub_classes(self.g, SKOS.Concept)
                for c in self.g.subjects(RDF.type, k) if isinstance(c, URIRef)}

    def schemes(self) -> list[URIRef]:
        return sorted({s for k in _sub_classes(self.g, SKOS.ConceptScheme)
                       for s in self.g.subjects(RDF.type, k) if isinstance(s, URIRef)})

    def in_scheme(self, c: URIRef) -> set[URIRef]:
        props = _sub_props(self.g, SKOS.inScheme, set())
        out = {o for p in props for o in self.g.objects(c, p)}
        out |= set(self.g.objects(c, SKOS.topConceptOf))
        out |= set(self.g.subjects(SKOS.hasTopConcept, c))
        return {x for x in out if isinstance(x, URIRef)}

    def _in_schemes(self, c: URIRef, schemes: Iterable[URIRef] | None, mode: str) -> bool:
        if not schemes:
            return True
        mine, want = self.in_scheme(c), set(schemes)
        return want <= mine if mode == "and" else bool(want & mine)

    def _deprecated(self, c: URIRef) -> bool:
        return (c, OWL.deprecated, Literal(True)) in self.g

    # ------------------------------------------------------------------ #
    # tree reads
    # ------------------------------------------------------------------ #
    def top_concepts(self, schemes: Iterable[URIRef] | None = None, mode: str = "or",
                     include_deprecated: bool = True) -> list[TreeNode]:
        schemes = list(schemes or [])
        concepts = self.concepts()
        if schemes:
            def declared(c, s):
                return (c, SKOS.topConceptOf, s) in self.g or (s, SKOS.hasTopConcept, c) in self.g
            if mode == "and":
                tops = {c for c in concepts if all(declared(c, s) for s in schemes)}
            else:
                tops = {c for c in concepts if any(declared(c, s) for s in schemes)}
        else:
            tops = {c for c in concepts if not (self.broaders(c) & concepts)}
        if not include_deprecated:
            tops = {c for c in tops if not self._deprecated(c)}
        return [self._node(c, schemes, mode) for c in sorted(tops)]

    def narrower_concepts(self, c: URIRef, schemes: Iterable[URIRef] | None = None,
                          mode: str = "or", include_deprecated: bool = True) -> list[TreeNode]:
        schemes = list(schemes or [])
        concepts = self.concepts()
        out = {n for n in self.narrowers(c) if n in concepts
               and self._in_schemes(n, schemes, mode)}
        if not include_deprecated:
            out = {n for n in out if not self._deprecated(n)}
        return [self._node(n, schemes, mode) for n in sorted(out)]

    def _node(self, c, schemes, mode) -> TreeNode:
        more = any(self._in_schemes(n, schemes, mode) for n in self.narrowers(c))
        return TreeNode(c, more, self.pref_label(c))

    def path_from_root(self, c: URIRef, schemes: Iterable[URIRef] | None = None,
                       mode: str = "or") -> list[list[URIRef]]:
        """``Search.getPathFromRoot`` for concepts: every path from a top concept."""
        tops = {n.iri for n in self.top_concepts(schemes, mode)}
        out: list[list[URIRef]] = []

        def walk(n, path):
            if n in tops:
                out.append(list(reversed(path + [n])))
            for b in self.broaders(n):
                if b not in path:
                    walk(b, path + [n])
        walk(c, [])
        return out

    # ------------------------------------------------------------------ #
    # labels
    # ------------------------------------------------------------------ #
    def pref_label(self, c: URIRef, lang: str = "en") -> str | None:
        labels = self.labels(c, "pref")
        for l in labels:
            if (l.language or "") == lang:
                return str(l)
        return str(labels[0]) if labels else None

    def labels(self, c: URIRef, kind: str = "pref") -> list[Literal]:
        p = {"pref": "prefLabel", "alt": "altLabel", "hidden": "hiddenLabel"}[kind]
        if self.lexicalization == "skos":
            return [o for o in self.g.objects(c, SKOS[p]) if isinstance(o, Literal)]
        return [lf for xl in self.g.objects(c, SKOSXL[p])
                for lf in self.g.objects(xl, SKOSXL.literalForm) if isinstance(lf, Literal)]

    def _same_role(self, role_cls: URIRef) -> set[URIRef]:
        return {c for k in _sub_classes(self.g, role_cls)
                for c in self.g.subjects(RDF.type, k) if isinstance(c, URIRef)}

    def check_pref_label(self, resource: URIRef | None, label: Literal,
                         schemes: Iterable[URIRef] = (), role_cls: URIRef = SKOS.Concept,
                         check_alt: bool = True) -> None:
        """``checkIfAddPrefLabelIsPossible`` + ``checkIfPrefAltLabelClash``."""
        schemes = set(schemes)
        for other in self._same_role(role_cls):
            if other == resource:
                continue
            if role_cls == SKOS.Concept and schemes and not (self.in_scheme(other) & schemes):
                continue
            if label in self.labels(other, "pref"):
                raise LabelClash(f"prefLabel {label!r} already used by {other}")
            if check_alt and label in self.labels(other, "alt"):
                raise LabelClash(f"prefLabel {label!r} is an altLabel of {other}")

    # ------------------------------------------------------------------ #
    # writes (change sets)
    # ------------------------------------------------------------------ #
    def create_concept(self, iri: URIRef, label: Literal | None, schemes: Iterable[URIRef],
                       graph: URIRef, *, broader: URIRef | None = None,
                       concept_cls: URIRef = SKOS.Concept,
                       mint_xlabel: Callable[[], URIRef] | None = None,
                       check_labels: bool = True) -> ChangeSet:
        schemes = list(schemes)
        if (iri, None, None) in self.g:
            raise PreconditionFailed(f"{iri} already exists")
        cs = ChangeSet("skos.createConcept", {"concept": str(iri), "label": str(label) if label
                                              else None, "broader": str(broader) if broader
                                              else None}, graph)
        if label is not None:
            if check_labels:
                self.check_pref_label(None, label, schemes)
            self._add_label(cs, iri, "pref", label, mint_xlabel)
        cs.add(iri, RDF.type, concept_cls)
        for s in schemes:
            cs.add(iri, SKOS.inScheme, s)
        if broader is not None:
            cs.add(iri, SKOS.broader, broader)
        else:
            for s in schemes:
                cs.add(iri, SKOS.topConceptOf, s)
        return cs

    def create_scheme(self, iri: URIRef, label: Literal | None, graph: URIRef,
                      mint_xlabel: Callable[[], URIRef] | None = None) -> ChangeSet:
        cs = ChangeSet("skos.createConceptScheme", {"scheme": str(iri)}, graph)
        if label is not None:
            self.check_pref_label(None, label, role_cls=SKOS.ConceptScheme)
            self._add_label(cs, iri, "pref", label, mint_xlabel)
        cs.add(iri, RDF.type, SKOS.ConceptScheme)
        return cs

    def _add_label(self, cs: ChangeSet, r: URIRef, kind: str, label: Literal,
                   mint_xlabel: Callable[[], URIRef] | None) -> None:
        p = {"pref": "prefLabel", "alt": "altLabel", "hidden": "hiddenLabel"}[kind]
        if self.lexicalization == "skos":
            cs.add(r, SKOS[p], label)
        else:
            xl = mint_xlabel() if mint_xlabel else BNode()
            cs.add(r, SKOSXL[p], xl)
            cs.add(xl, RDF.type, SKOSXL.Label)
            cs.add(xl, SKOSXL.literalForm, label)

    def set_pref_label(self, c: URIRef, label: Literal, graph: URIRef,
                       mint_xlabel: Callable[[], URIRef] | None = None,
                       check: bool = True) -> ChangeSet:
        cs = ChangeSet("skos.setPrefLabel", {"resource": str(c), "label": str(label),
                                             "lang": label.language}, graph)
        if check:
            self.check_pref_label(c, label, self.in_scheme(c))
        lang = (label.language or "").lower()
        if self.lexicalization == "skos":
            for old in list(self.g.objects(c, SKOS.prefLabel)):
                if isinstance(old, Literal) and (old.language or "").lower() == lang:
                    if old == label:
                        return cs
                    cs.remove(c, SKOS.prefLabel, old)
                    cs.add(c, SKOS.altLabel, old)          # demotion
        else:
            for xl in list(self.g.objects(c, SKOSXL.prefLabel)):
                for lf in self.g.objects(xl, SKOSXL.literalForm):
                    if isinstance(lf, Literal) and (lf.language or "").lower() == lang:
                        cs.remove(c, SKOSXL.prefLabel, xl)
                        cs.add(c, SKOSXL.altLabel, xl)
        self._add_label(cs, c, "pref", label, mint_xlabel)
        return cs

    def add_alt_label(self, c: URIRef, label: Literal, graph: URIRef,
                      mint_xlabel: Callable[[], URIRef] | None = None) -> ChangeSet:
        if label in self.labels(c, "pref"):
            raise LabelClash(f"altLabel {label!r} equals a prefLabel of {c}")
        cs = ChangeSet("skos.addAltLabel", {"resource": str(c), "label": str(label)}, graph)
        self._add_label(cs, c, "alt", label, mint_xlabel)
        return cs

    def add_broader(self, c: URIRef, broader: URIRef, graph: URIRef,
                    add_inverse: bool = False) -> ChangeSet:
        if c == broader or c in self._ancestors(broader):
            raise PreconditionFailed(f"{broader} is {c} or one of its descendants: cycle")
        cs = ChangeSet("skos.addBroaderConcept", {"concept": str(c), "broader": str(broader)},
                       graph)
        cs.add(c, SKOS.broader, broader)
        if add_inverse:
            cs.add(broader, SKOS.narrower, c)
        return cs

    def _ancestors(self, c: URIRef) -> set[URIRef]:
        out, stack = set(), [c]
        while stack:
            n = stack.pop()
            for b in self.broaders(n):
                if b not in out:
                    out.add(b)
                    stack.append(b)
        return out

    def remove_broader(self, c: URIRef, broader: URIRef, graph: URIRef) -> ChangeSet:
        cs = ChangeSet("skos.removeBroaderConcept", {"concept": str(c),
                                                     "broader": str(broader)}, graph)
        for p in self._broader_props():
            if (c, p, broader) in self.g:
                cs.remove(c, p, broader)
        for p in self._narrower_props():
            if (broader, p, c) in self.g:
                cs.remove(broader, p, c)
        return cs

    def add_top_concept(self, c: URIRef, scheme: URIRef, graph: URIRef) -> ChangeSet:
        return ChangeSet("skos.addTopConcept", {"concept": str(c), "scheme": str(scheme)},
                         graph).add(c, SKOS.topConceptOf, scheme)

    def delete_concept(self, c: URIRef, graph: URIRef) -> ChangeSet:
        if self.narrowers(c):
            raise PreconditionFailed(f"{c} has narrower concepts; delete or move them first")
        cs = ChangeSet("skos.deleteConcept", {"concept": str(c)}, graph)
        owned = [o for p in (SKOSXL.prefLabel, SKOSXL.altLabel, SKOSXL.hiddenLabel)
                 for o in self.g.objects(c, p)]
        for n in [c] + owned:
            cs.remove_all(self.g.triples((n, None, None)))
            cs.remove_all(self.g.triples((None, None, n)))
        return cs

    # ------------------------------------------------------------------ #
    # collections
    # ------------------------------------------------------------------ #
    def create_collection(self, iri: URIRef, label: Literal | None, graph: URIRef,
                          ordered: bool = False, members: Iterable[URIRef] = ()) -> ChangeSet:
        cs = ChangeSet("skos.createCollection", {"collection": str(iri),
                                                 "ordered": ordered}, graph)
        cs.add(iri, RDF.type, SKOS.OrderedCollection if ordered else SKOS.Collection)
        if label is not None:
            self._add_label(cs, iri, "pref", label, None)
        members = list(members)
        if ordered:
            head = _list_triples(members, cs)
            cs.add(iri, SKOS.memberList, head)
        else:
            for m in members:
                cs.add(iri, SKOS.member, m)
        return cs

    def ordered_members(self, coll: URIRef) -> list[URIRef]:
        head = self.g.value(coll, SKOS.memberList)
        return list(Collection(self.g, head)) if head is not None else []

    # ------------------------------------------------------------------ #
    # SKOS <-> SKOS-XL (Refactor.SKOStoSKOSXL / SKOSXLtoSKOS)
    # ------------------------------------------------------------------ #
    def to_skosxl(self, graph: URIRef, mint_xlabel: Callable[[str, Literal], URIRef]
                  ) -> ChangeSet:
        cs = ChangeSet("refactor.SKOStoSKOSXL", {}, graph)
        for kind in ("prefLabel", "altLabel", "hiddenLabel"):
            for s, o in list(self.g.subject_objects(SKOS[kind])):
                if not isinstance(o, Literal):
                    continue
                xl = mint_xlabel(kind, o)
                cs.remove(s, SKOS[kind], o)
                cs.add(s, SKOSXL[kind], xl)
                cs.add(xl, RDF.type, SKOSXL.Label)
                cs.add(xl, SKOSXL.literalForm, o)
        return cs

    def to_skos(self, graph: URIRef) -> ChangeSet:
        cs = ChangeSet("refactor.SKOSXLtoSKOS", {}, graph)
        for kind in ("prefLabel", "altLabel", "hiddenLabel"):
            for s, xl in list(self.g.subject_objects(SKOSXL[kind])):
                for lf in self.g.objects(xl, SKOSXL.literalForm):
                    cs.add(s, SKOS[kind], lf)
                cs.remove(s, SKOSXL[kind], xl)
                cs.remove_all(self.g.triples((xl, None, None)))
                cs.remove_all(t for t in self.g.triples((None, None, xl))
                              if t != (s, SKOSXL[kind], xl))
        return cs


def _list_triples(items: list, cs: ChangeSet):
    if not items:
        return RDF.nil
    nodes = [BNode() for _ in items]
    for i, (n, it) in enumerate(zip(nodes, items)):
        cs.add(n, RDF.first, it)
        cs.add(n, RDF.rest, nodes[i + 1] if i + 1 < len(nodes) else RDF.nil)
    return nodes[0]
