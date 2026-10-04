"""Refactoring — Protégé's *Refactor* and *Edit* menus plus Semantic Turkey's
``Refactor`` service, as change-set generators.

Every function reads a graph and returns a :class:`~..core.changes.ChangeSet`;
nothing here writes. The caller commits it through the change tracker, so a
refactoring is one commit, undoable in one step, and — when an agent proposes it —
one staged proposal a validator sees as a unit.

Sources (see ``REVERSE_ENGINEERING.md`` §Refactoring for the full enumeration):

=====================================  =========================================
function                               origin
=====================================  =========================================
``rename_iri``                         Protégé ``OWLEntityRenamer.changeIRI(IRI, IRI)``
                                       (pun-wide) = ST ``Refactor.changeResourceURI``
``replace_base_uri``                   ST ``Refactor.replaceBaseURI``; Protégé
                                       *Change ontology IRI* cascade
``merge_entities``                     Protégé ``MergeEntitiesChangeListGenerator``
``delete_entities``                    Protégé ``OWLEntityDeleter``/``ReferenceFinder``
``convert_to_defined``/``…primitive``  Protégé ``ConvertToDefined/PrimitiveClassAction``
``split_subclass_axioms``              OWLAPI ``SplitSubClassAxioms``
``amalgamate_subclass_axioms``         OWLAPI ``AmalgamateSubClassAxioms``
``split_disjoint_classes``             Protégé ``SplitDisjointClassesAction``
``make_primitive_siblings_disjoint``   Protégé ``MakePrimitiveSiblingsDisjoint``
``add_covering_axiom``                 Protégé ``AddCoveringAxiomAction``
``create_closure_axiom``               Protégé ``ClosureAxiomFactory``
``move_axioms``                        Protégé ``MoveAxiomsWizard`` (move/copy/delete)
``deprecate``                          Protégé ``EntityDeprecator`` (basic profile)
=====================================  =========================================

Quirks found in Protégé and deliberately **not** reproduced:
merging no longer deletes a target label identical to a source label; the
ontology-IRI cascade renames by namespace boundary, not by raw string prefix;
amalgamation output is deterministic.
"""

from __future__ import annotations

from typing import Iterable

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..core.changes import ChangeSet
from .hierarchy import ClassHierarchy
from .model import (And, Axiom, Card, HasValue, OneOf, Only, Or, Some, axiom_signature,
                    axiom_triples, axioms, bnode_closure, parse_ce)


def _cs(op: str, graph: URIRef, **params) -> ChangeSet:
    return ChangeSet(op, {k: str(v) if isinstance(v, URIRef) else v
                          for k, v in params.items()}, graph)


def _remove_axiom(cs: ChangeSet, g: Graph, ax: Axiom) -> None:
    cs.remove_all(axiom_triples(ax, g))


def _add_axiom(cs: ChangeSet, ax: Axiom) -> None:
    cs.add_all(axiom_triples(ax))

# --------------------------------------------------------------------------- #
# IRIs
# --------------------------------------------------------------------------- #


def rename_iri(g: Graph, old: URIRef, new: URIRef, graph: URIRef) -> ChangeSet:
    """Rewrite every triple mentioning *old* (any position). Renaming onto an
    existing IRI merges the two — triple sets deduplicate, as OWLAPI axiom sets do."""
    if old == new:
        raise ValueError("old and new IRI are the same")
    cs = _cs("refactor.renameIRI", graph, old=old, new=new)
    for s, p, o in set(g.triples((old, None, None))) | set(g.triples((None, old, None))) \
            | set(g.triples((None, None, old))):
        cs.remove(s, p, o)
        cs.add(new if s == old else s, new if p == old else p, new if o == old else o)
    return cs


def replace_base_uri(g: Graph, old_base: str, new_base: str, graph: URIRef) -> ChangeSet:
    """Move every IRI in namespace *old_base* to *new_base*.

    Protégé's cascade used ``startsWith`` on the raw string, so ``http://x/onto``
    also caught ``http://x/ontology#A``. Here an IRI is moved only if the remainder
    after *old_base* starts at a namespace boundary (old_base ends in ``#``/``/`` or
    the remainder starts with one)."""
    cs = _cs("refactor.replaceBaseURI", graph, old=old_base, new=new_base)

    def mv(t):
        if isinstance(t, URIRef):
            s = str(t)
            if s.startswith(old_base):
                rest = s[len(old_base):]
                if old_base.endswith(("#", "/")) or rest == "" or rest[0] in "#/":
                    return URIRef(new_base + rest)
        return t
    for tr in g:
        nt = tuple(mv(x) for x in tr)
        if nt != tr:
            cs.remove(*tr)
            cs.add(*nt)
    return cs


def merge_entities(g: Graph, sources: Iterable[URIRef], target: URIRef, graph: URIRef,
                   *, label_properties=(RDFS.label, SKOS.prefLabel),
                   alt_property: URIRef = SKOS.altLabel) -> ChangeSet:
    """``MergeStrategy.DELETE_SOURCE_ENTITY``: pun-wide rename of each source onto the
    target; the sources' preferred labels become ``skos:altLabel`` of the target."""
    cs = _cs("refactor.mergeEntities", graph, target=target,
             sources=[str(s) for s in sources])
    target_labels = {(p, o) for p in label_properties for o in g.objects(target, p)}
    for src in sources:
        sub = rename_iri(g, src, target, graph)
        for q in sub.removals:
            cs.remove(*q[:3])
        for s, p, o, _ in sub.additions:
            if s == target and p in label_properties and (p, o) not in target_labels:
                cs.add(target, alt_property, o)       # label of a merged-away source
            elif s == target and p in label_properties:
                continue                               # identical label: keep target's own
            else:
                cs.add(s, p, o)
    return cs


def deprecate(g: Graph, entity: URIRef, graph: URIRef, *, replaced_by: URIRef | None = None,
              reason: str | None = None) -> ChangeSet:
    """Protégé's *basic* deprecation profile: ``owl:deprecated true``, optional
    ``dcterms:isReplacedBy``, a reason comment, and logical axioms removed (the
    entity stops participating in inference but its annotations remain)."""
    cs = _cs("refactor.deprecate", graph, entity=entity)
    cs.add(entity, OWL.deprecated, Literal(True))
    if replaced_by is not None:
        cs.add(entity, URIRef("http://purl.org/dc/terms/isReplacedBy"), replaced_by)
    if reason:
        cs.add(entity, RDFS.comment, Literal(f"DEPRECATED: {reason}", lang="en"))
    for ax in axioms(g, include_annotations=False, include_declarations=False):
        if entity in axiom_signature(ax):
            _remove_axiom(cs, g, ax)
    return cs

# --------------------------------------------------------------------------- #
# Deletion and usage
# --------------------------------------------------------------------------- #


def usage(g: Graph, entity: URIRef) -> list[Axiom]:
    """Protégé *Usage* view: every axiom whose signature contains *entity*,
    grouped by the caller (the frame renderer groups by subject)."""
    return [ax for ax in axioms(g) if entity in axiom_signature(ax)
            or (ax.kind == "AnnotationAssertion" and entity in ax.args)]


def delete_entities(g: Graph, entities: Iterable[URIRef], graph: URIRef, *,
                    include_descendants: bool = False) -> ChangeSet:
    """``OWLEntityDeleter``: remove *whole* axioms that mention the entity (no
    pruning of class expressions), annotation assertions with the entity as subject
    or value, and — the RDF-level invariant Protégé gets for free from the OWL API —
    never leave an orphan blank-node structure."""
    targets = set(entities)
    if include_descendants:
        h = ClassHierarchy(g)
        for e in list(targets):
            targets |= h.descendants(e)
    cs = _cs("refactor.deleteEntities", graph, entities=sorted(map(str, targets)))
    removed: set = set()
    for ax in axioms(g):
        if axiom_signature(ax) & targets or (ax.kind == "AnnotationAssertion"
                                             and set(ax.args[1:]) & targets):
            for t in axiom_triples(ax, g):
                removed.add(t)
    for e in targets:
        for t in set(g.triples((e, None, None))) | set(g.triples((None, None, e))) \
                | set(g.triples((None, e, None))):
            removed.add(t)
            for n in (t[0], t[2]):
                if isinstance(n, BNode):
                    removed |= _owning_structure(g, n)
    cs.remove_all(sorted(removed, key=str))
    return cs


def _owning_structure(g: Graph, bnode: BNode) -> set:
    """The topmost anonymous structure containing *bnode* and its closure."""
    root, seen = bnode, set()
    while True:
        parents = [s for s, _ in g.subject_predicates(root) if isinstance(s, BNode)]
        if not parents or root in seen:
            break
        seen.add(root)
        root = parents[0]
    out = bnode_closure(g, root)
    out |= set(g.triples((None, None, root)))
    return out

# --------------------------------------------------------------------------- #
# Class-level logical refactorings
# --------------------------------------------------------------------------- #


def _named_subclass_axioms(g: Graph, c: URIRef) -> list[Axiom]:
    return [a for a in axioms(g, include_annotations=False, include_declarations=False)
            if a.kind == "SubClassOf" and a.args[0] == c]


def convert_to_defined(g: Graph, c: URIRef, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.convertToDefinedClass", graph, cls=c)
    subs = _named_subclass_axioms(g, c)
    if not subs:
        return cs
    for a in subs:
        _remove_axiom(cs, g, a)
    sups = tuple(sorted({a.args[1] for a in subs}, key=repr))
    _add_axiom(cs, Axiom("EquivalentClasses", (c, sups[0] if len(sups) == 1 else And(sups))))
    return cs


def convert_to_primitive(g: Graph, c: URIRef, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.convertToPrimitiveClass", graph, cls=c)
    for a in axioms(g, include_annotations=False, include_declarations=False):
        if a.kind == "EquivalentClasses" and c in a.args:
            _remove_axiom(cs, g, a)
            for d in a.args:
                if d == c:
                    continue
                for op in (d.operands if isinstance(d, And) else (d,)):
                    _add_axiom(cs, Axiom("SubClassOf", (c, op)))
    return cs


def _flatten_and(ce) -> list:
    if isinstance(ce, And):
        out = []
        for op in ce.operands:
            out.extend(_flatten_and(op))
        return out
    return [ce]


def split_subclass_axioms(g: Graph, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.splitSubClassAxioms", graph)
    for a in axioms(g, include_annotations=False, include_declarations=False):
        if a.kind == "SubClassOf" and isinstance(a.args[1], And):
            parts = _flatten_and(a.args[1])
            if len(parts) > 1:
                _remove_axiom(cs, g, a)
                for p in parts:
                    _add_axiom(cs, Axiom("SubClassOf", (a.args[0], p)))
    return cs


def amalgamate_subclass_axioms(g: Graph, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.amalgamateSubClassAxioms", graph)
    by: dict[URIRef, list[Axiom]] = {}
    for a in axioms(g, include_annotations=False, include_declarations=False):
        if a.kind == "SubClassOf" and isinstance(a.args[0], URIRef):
            by.setdefault(a.args[0], []).append(a)
    for c, axs in sorted(by.items()):
        if len(axs) > 1:
            for a in axs:
                _remove_axiom(cs, g, a)
            _add_axiom(cs, Axiom("SubClassOf", (c, And(tuple(sorted(
                (a.args[1] for a in axs), key=repr))))))
    return cs


def split_disjoint_classes(g: Graph, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.splitDisjointClasses", graph)
    for a in axioms(g, include_annotations=False, include_declarations=False):
        if a.kind == "DisjointClasses" and len(a.args) > 2:
            _remove_axiom(cs, g, a)
            ops = a.args
            for i in range(len(ops)):
                for j in range(i + 1, len(ops)):
                    _add_axiom(cs, Axiom("DisjointClasses", (ops[i], ops[j])))
    return cs


def make_primitive_siblings_disjoint(g: Graph, c: URIRef, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.makePrimitiveSiblingsDisjoint", graph, cls=c)
    h = ClassHierarchy(g)
    sibs = {s for p in h.parents(c) for s in h.children(p)}
    defined = {x for x in sibs if (x, OWL.equivalentClass, None) in g
               or (None, OWL.equivalentClass, x) in g}
    rest = tuple(sorted(sibs - defined))
    if len(rest) > 1:
        existing = {a for a in axioms(g, include_annotations=False,
                                      include_declarations=False)
                    if a.kind == "DisjointClasses"}
        new = Axiom("DisjointClasses", rest)
        if new not in existing:
            _add_axiom(cs, new)
    return cs


def add_covering_axiom(g: Graph, c: URIRef, graph: URIRef) -> ChangeSet:
    cs = _cs("refactor.addCoveringAxiom", graph, cls=c)
    kids = ClassHierarchy(g).children(c)
    if len(kids) > 1:
        _add_axiom(cs, Axiom("SubClassOf", (c, Or(tuple(kids)))))
    return cs


def create_closure_axiom(g: Graph, c: URIRef, graph: URIRef,
                         properties: Iterable[URIRef] | None = None) -> ChangeSet:
    """``ClosureAxiomFactory``: for each object property ``p`` used existentially on
    ``c`` (inherited through asserted superclasses), add ``c ⊑ ∀p.(F1 ⊔ … ⊔ Fn)``."""
    cs = _cs("refactor.createClosureAxiom", graph, cls=c)
    sup_axioms = [a for a in axioms(g, include_annotations=False, include_declarations=False)
                  if a.kind in ("SubClassOf", "EquivalentClasses")]

    def supers_of(x):
        out = []
        for a in sup_axioms:
            if a.kind == "SubClassOf" and a.args[0] == x:
                out.append(a.args[1])
            elif a.kind == "EquivalentClasses" and x in a.args:
                out.extend(y for y in a.args if y != x)
        return out

    fillers: dict[URIRef, set] = {}
    seen: set = set()

    def visit(x):
        if x in seen:
            return
        seen.add(x)
        for e in supers_of(x):
            visit_ce(e)

    def visit_ce(e):
        if isinstance(e, And):
            for op in e.operands:
                visit_ce(op)
        elif isinstance(e, Some) and isinstance(e.prop, URIRef) and not e.data:
            if e.filler != OWL.Thing:
                fillers.setdefault(e.prop, set()).add(e.filler)
        elif isinstance(e, Card) and e.kind in ("min", "exactly") and e.n > 0 \
                and isinstance(e.prop, URIRef) and not e.data:
            if e.filler not in (None, OWL.Thing):
                fillers.setdefault(e.prop, set()).add(e.filler)
        elif isinstance(e, HasValue) and isinstance(e.prop, URIRef) and not e.data:
            fillers.setdefault(e.prop, set()).add(OneOf((e.value,)))
        elif isinstance(e, URIRef):
            visit(e)

    visit(c)
    wanted = set(properties) if properties is not None else set(fillers)
    existing = set(sup_axioms)
    for p in sorted(wanted & set(fillers)):
        fs = tuple(sorted(fillers[p], key=repr))
        ax = Axiom("SubClassOf", (c, Only(p, fs[0] if len(fs) == 1 else Or(fs))))
        if ax not in existing:
            _add_axiom(cs, ax)
    return cs


def move_axioms(g: Graph, selected: Iterable[Axiom], source: URIRef, target: URIRef,
                mode: str = "move") -> ChangeSet:
    """``MoveAxiomsWizard``: ``move`` | ``copy`` | ``delete`` axioms between graphs
    (main ↔ a module graph). Also how Protégé "splits" an ontology."""
    if mode not in ("move", "copy", "delete"):
        raise ValueError("mode is move | copy | delete")
    cs = _cs(f"refactor.{mode}Axioms", source, source=source, target=target)
    for ax in selected:
        existing = axiom_triples(ax, g)
        if not existing:
            raise ValueError(f"axiom not found in source: {ax}")
        if mode in ("move", "delete"):
            cs.remove_all(existing, graph=source)
        if mode in ("move", "copy"):
            # re-emit with fresh blank nodes in the target graph
            cs.add_all(axiom_triples(ax), graph=target)
    return cs
