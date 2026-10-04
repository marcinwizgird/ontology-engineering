"""OWL 2 structural model over RDF — the part of the OWL API that Protégé stands on.

Protégé never edits triples; it edits ``OWLAxiom`` objects and lets the OWL API
serialise them (``OWLModelManager.applyChanges`` → ``AddAxiom``/``RemoveAxiom``).
Semantic Turkey is the opposite: everything is triples. The platform keeps RDF as
the canonical form (so the VocBench half of the system, history and staging all
work at triple level) and offers this module as a *derived axiom view*:

* :func:`parse_ce` reads a class expression rooted at an RDF node, following the
  OWL 2 *Mapping to RDF Graphs* (W3C Rec, §3 "Reverse mapping");
* :func:`ce_triples` writes one back as triples (fresh blank nodes);
* :func:`axioms` extracts the logical axioms of a graph as frozen dataclasses;
* :func:`axiom_triples` maps an axiom to the triples that encode it, which is how
  a Protégé-style ``AddAxiom``/``RemoveAxiom`` becomes a triple ``ChangeSet``.

Removing an axiom whose class expression lives on blank nodes means removing the
whole blank-node closure; :func:`axiom_triples` with ``graph=`` returns exactly the
existing triples (closure included) so that removal is exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Union

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

Triple = tuple[Node, Node, Node]

# --------------------------------------------------------------------------- #
# Property expressions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Inverse:
    """``ObjectInverseOf(P)``."""
    prop: URIRef


PropExpr = Union[URIRef, Inverse]

# --------------------------------------------------------------------------- #
# Data ranges
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DatatypeRestriction:
    datatype: URIRef
    facets: tuple[tuple[URIRef, Literal], ...]


@dataclass(frozen=True)
class DataOneOf:
    values: tuple[Literal, ...]


@dataclass(frozen=True)
class DataNary:
    op: str  # "and" | "or"
    operands: tuple["DataRange", ...]


@dataclass(frozen=True)
class DataComplementOf:
    operand: "DataRange"


DataRange = Union[URIRef, DatatypeRestriction, DataOneOf, DataNary, DataComplementOf]

# --------------------------------------------------------------------------- #
# Class expressions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class And:
    operands: tuple["CE", ...]


@dataclass(frozen=True)
class Or:
    operands: tuple["CE", ...]


@dataclass(frozen=True)
class Not:
    operand: "CE"


@dataclass(frozen=True)
class OneOf:
    individuals: tuple[URIRef, ...]


@dataclass(frozen=True)
class Some:
    prop: PropExpr
    filler: "CE | DataRange"
    data: bool = False


@dataclass(frozen=True)
class Only:
    prop: PropExpr
    filler: "CE | DataRange"
    data: bool = False


@dataclass(frozen=True)
class HasValue:
    prop: PropExpr
    value: Node
    data: bool = False


@dataclass(frozen=True)
class HasSelf:
    prop: PropExpr


@dataclass(frozen=True)
class Card:
    """``min``/``max``/``exactly`` with optional qualification."""
    kind: str               # "min" | "max" | "exactly"
    n: int
    prop: PropExpr
    filler: "CE | DataRange | None" = None
    data: bool = False


CE = Union[URIRef, And, Or, Not, OneOf, Some, Only, HasValue, HasSelf, Card]

CARD_PRED = {
    ("min", False): OWL.minCardinality, ("max", False): OWL.maxCardinality,
    ("exactly", False): OWL.cardinality,
    ("min", True): OWL.minQualifiedCardinality, ("max", True): OWL.maxQualifiedCardinality,
    ("exactly", True): OWL.qualifiedCardinality,
}
_PRED_CARD = {v: k for k, v in CARD_PRED.items()}


class UnsupportedConstruct(ValueError):
    """The RDF at a node is not a well-formed OWL 2 class expression."""

# --------------------------------------------------------------------------- #
# RDF -> structural
# --------------------------------------------------------------------------- #


def _list(g: Graph, head: Node) -> list[Node]:
    if head == RDF.nil:
        return []
    return list(Collection(g, head))


def parse_prop(g: Graph, node: Node) -> PropExpr:
    if isinstance(node, URIRef):
        return node
    inv = g.value(node, OWL.inverseOf)
    if isinstance(inv, URIRef):
        return Inverse(inv)
    raise UnsupportedConstruct(f"not a property expression: {node!r}")


def is_data_property(g: Graph, p: PropExpr) -> bool:
    return isinstance(p, URIRef) and (p, RDF.type, OWL.DatatypeProperty) in g


def parse_data_range(g: Graph, node: Node) -> DataRange:
    if isinstance(node, URIRef):
        return node
    on = g.value(node, OWL.onDatatype)
    if on is not None:
        facets = []
        for item in _list(g, g.value(node, OWL.withRestrictions)):
            for p, o in g.predicate_objects(item):
                facets.append((p, o))
        return DatatypeRestriction(on, tuple(facets))
    one = g.value(node, OWL.oneOf)
    if one is not None:
        return DataOneOf(tuple(_list(g, one)))
    for pred, op in ((OWL.intersectionOf, "and"), (OWL.unionOf, "or")):
        lst = g.value(node, pred)
        if lst is not None:
            return DataNary(op, tuple(parse_data_range(g, x) for x in _list(g, lst)))
    comp = g.value(node, OWL.datatypeComplementOf)
    if comp is not None:
        return DataComplementOf(parse_data_range(g, comp))
    raise UnsupportedConstruct(f"not a data range: {node!r}")


def _is_datatype(g: Graph, node: Node) -> bool:
    if isinstance(node, URIRef):
        return (str(node).startswith(str(XSD)) or node == RDFS.Literal
                or (node, RDF.type, RDFS.Datatype) in g)
    return (node, RDF.type, RDFS.Datatype) in g


def parse_ce(g: Graph, node: Node) -> CE:
    """Reverse mapping of OWL 2 (Mapping to RDF, §3.2.4, tables 13-15)."""
    if isinstance(node, URIRef):
        return node
    if (node, RDF.type, OWL.Restriction) in g:
        prop_node = g.value(node, OWL.onProperty)
        if prop_node is None:
            raise UnsupportedConstruct("owl:Restriction without owl:onProperty "
                                       "(owl:onProperties n-ary data restrictions "
                                       "are not supported)")
        prop = parse_prop(g, prop_node)
        data = is_data_property(g, prop)

        def filler(n: Node):
            if data or _is_datatype(g, n):
                return parse_data_range(g, n)
            return parse_ce(g, n)

        if (v := g.value(node, OWL.someValuesFrom)) is not None:
            f = filler(v)
            return Some(prop, f, data or not _is_ce(f))
        if (v := g.value(node, OWL.allValuesFrom)) is not None:
            f = filler(v)
            return Only(prop, f, data or not _is_ce(f))
        if (v := g.value(node, OWL.hasValue)) is not None:
            return HasValue(prop, v, data or isinstance(v, Literal))
        if (v := g.value(node, OWL.hasSelf)) is not None:
            return HasSelf(prop)
        for pred, (kind, qualified) in _PRED_CARD.items():
            if (v := g.value(node, pred)) is not None:
                n = int(v)
                f = None
                if qualified:
                    q = g.value(node, OWL.onClass)
                    if q is not None:
                        f = parse_ce(g, q)
                    else:
                        q = g.value(node, OWL.onDataRange)
                        if q is None:
                            raise UnsupportedConstruct("qualified cardinality "
                                                       "without onClass/onDataRange")
                        f, data = parse_data_range(g, q), True
                return Card(kind, n, prop, f, data)
        raise UnsupportedConstruct(f"restriction {node!r} has no recognised filler")
    for pred, ctor in ((OWL.intersectionOf, And), (OWL.unionOf, Or)):
        lst = g.value(node, pred)
        if lst is not None:
            if _is_datatype(g, node):
                return parse_data_range(g, node)  # type: ignore[return-value]
            return ctor(tuple(parse_ce(g, x) for x in _list(g, lst)))
    if (comp := g.value(node, OWL.complementOf)) is not None:
        return Not(parse_ce(g, comp))
    if (one := g.value(node, OWL.oneOf)) is not None:
        return OneOf(tuple(_list(g, one)))
    raise UnsupportedConstruct(f"blank node {node!r} is not a class expression")


def _is_ce(x) -> bool:
    return isinstance(x, (URIRef, And, Or, Not, OneOf, Some, Only, HasValue, HasSelf, Card))

# --------------------------------------------------------------------------- #
# structural -> RDF
# --------------------------------------------------------------------------- #


def _emit_list(items: list[Node], out: list[Triple]) -> Node:
    if not items:
        return RDF.nil
    head = BNode()
    cur = head
    for i, item in enumerate(items):
        out.append((cur, RDF.first, item))
        nxt = BNode() if i < len(items) - 1 else RDF.nil
        out.append((cur, RDF.rest, nxt))
        cur = nxt  # type: ignore[assignment]
    return head


def prop_triples(p: PropExpr, out: list[Triple]) -> Node:
    if isinstance(p, Inverse):
        b = BNode()
        out.append((b, OWL.inverseOf, p.prop))
        return b
    return p


def data_range_triples(dr: DataRange, out: list[Triple]) -> Node:
    if isinstance(dr, URIRef):
        return dr
    b = BNode()
    out.append((b, RDF.type, RDFS.Datatype))
    if isinstance(dr, DatatypeRestriction):
        out.append((b, OWL.onDatatype, dr.datatype))
        items = []
        for facet, value in dr.facets:
            f = BNode()
            out.append((f, facet, value))
            items.append(f)
        out.append((b, OWL.withRestrictions, _emit_list(items, out)))
    elif isinstance(dr, DataOneOf):
        out.append((b, OWL.oneOf, _emit_list(list(dr.values), out)))
    elif isinstance(dr, DataNary):
        pred = OWL.intersectionOf if dr.op == "and" else OWL.unionOf
        out.append((b, pred, _emit_list([data_range_triples(x, out) for x in dr.operands], out)))
    elif isinstance(dr, DataComplementOf):
        out.append((b, OWL.datatypeComplementOf, data_range_triples(dr.operand, out)))
    return b


def ce_triples(ce: CE, out: list[Triple]) -> Node:
    """Append the triples encoding *ce* to *out*; return its root node."""
    if isinstance(ce, URIRef):
        return ce
    b = BNode()
    if isinstance(ce, (And, Or)):
        out.append((b, RDF.type, OWL.Class))
        pred = OWL.intersectionOf if isinstance(ce, And) else OWL.unionOf
        out.append((b, pred, _emit_list([ce_triples(x, out) for x in ce.operands], out)))
    elif isinstance(ce, Not):
        out.append((b, RDF.type, OWL.Class))
        out.append((b, OWL.complementOf, ce_triples(ce.operand, out)))
    elif isinstance(ce, OneOf):
        out.append((b, RDF.type, OWL.Class))
        out.append((b, OWL.oneOf, _emit_list(list(ce.individuals), out)))
    else:
        out.append((b, RDF.type, OWL.Restriction))
        out.append((b, OWL.onProperty, prop_triples(ce.prop, out)))

        def filler(f) -> Node:
            return data_range_triples(f, out) if ce.data else ce_triples(f, out)

        if isinstance(ce, Some):
            out.append((b, OWL.someValuesFrom, filler(ce.filler)))
        elif isinstance(ce, Only):
            out.append((b, OWL.allValuesFrom, filler(ce.filler)))
        elif isinstance(ce, HasValue):
            out.append((b, OWL.hasValue, ce.value))
        elif isinstance(ce, HasSelf):
            out.append((b, OWL.hasSelf, Literal(True)))
        elif isinstance(ce, Card):
            qualified = ce.filler is not None and ce.filler != OWL.Thing
            out.append((b, CARD_PRED[(ce.kind, qualified)],
                        Literal(ce.n, datatype=XSD.nonNegativeInteger)))
            if qualified:
                out.append((b, OWL.onDataRange if ce.data else OWL.onClass, filler(ce.filler)))
    return b

# --------------------------------------------------------------------------- #
# Axioms
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Axiom:
    kind: str
    args: tuple
    #: Root RDF subject the axiom hangs from — used for exact removal.
    anchor: Node | None = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        # Symmetric axioms are sets in OWL 2: EquivalentClasses(A, B) == (B, A).
        if self.kind in SYMMETRIC:
            object.__setattr__(self, "args", tuple(sorted(set(self.args), key=repr)))

    def __str__(self) -> str:
        return f"{self.kind}({', '.join(map(str, self.args))})"


SYMMETRIC = frozenset({"EquivalentClasses", "DisjointClasses", "EquivalentProperties",
                       "DisjointProperties", "SameIndividual", "DifferentIndividuals"})


CHARACTERISTICS = {
    OWL.FunctionalProperty: "FunctionalProperty",
    OWL.InverseFunctionalProperty: "InverseFunctionalProperty",
    OWL.TransitiveProperty: "TransitiveProperty",
    OWL.SymmetricProperty: "SymmetricProperty",
    OWL.AsymmetricProperty: "AsymmetricProperty",
    OWL.ReflexiveProperty: "ReflexiveProperty",
    OWL.IrreflexiveProperty: "IrreflexiveProperty",
}
DECLARATIONS = {
    OWL.Class: "Class", OWL.ObjectProperty: "ObjectProperty",
    OWL.DatatypeProperty: "DataProperty", OWL.AnnotationProperty: "AnnotationProperty",
    OWL.NamedIndividual: "NamedIndividual", RDFS.Datatype: "Datatype",
}
_SKIP_TYPES = set(DECLARATIONS) | set(CHARACTERISTICS) | {
    OWL.Restriction, OWL.Ontology, RDF.Property, RDFS.Class, OWL.AllDisjointClasses,
    OWL.AllDifferent, OWL.Axiom, OWL.AllDisjointProperties, OWL.NegativePropertyAssertion,
}
_NON_LOGICAL = {RDF.type, RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith,
                RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.inverseOf,
                OWL.propertyChainAxiom, OWL.equivalentProperty, OWL.sameAs,
                OWL.differentFrom, OWL.disjointUnionOf, OWL.hasKey,
                OWL.propertyDisjointWith, OWL.imports, OWL.versionIRI}


def _safe_ce(g: Graph, n: Node):
    try:
        return parse_ce(g, n)
    except UnsupportedConstruct:
        return None


def _is_class_like(g: Graph, n: Node) -> bool:
    return (n, RDF.type, OWL.Class) in g or (n, RDF.type, RDFS.Class) in g \
        or (n, RDF.type, OWL.Restriction) in g


def axioms(g: Graph, *, include_annotations: bool = True,
           include_declarations: bool = True) -> Iterator[Axiom]:
    """Every OWL 2 axiom recoverable from *g* (the "axiom view").

    Anonymous-subject ``rdfs:subClassOf`` triples are emitted as General Class
    Axioms (``SubClassOf(CE, CE)``) — Protégé shows them in their own frame
    section and in the "General class axioms" view.
    """
    for s, o in g.subject_objects(RDFS.subClassOf):
        sub, sup = _safe_ce(g, s), _safe_ce(g, o)
        if sub is not None and sup is not None:
            yield Axiom("SubClassOf", (sub, sup), s)
    seen_eq: set = set()
    for s, o in g.subject_objects(OWL.equivalentClass):
        a, b = _safe_ce(g, s), _safe_ce(g, o)
        if a is None or b is None:
            continue
        key = frozenset((a, b)) if a != b else frozenset((a,))
        if key in seen_eq:
            continue
        seen_eq.add(key)
        yield Axiom("EquivalentClasses", (a, b), s)
    for s, o in g.subject_objects(OWL.disjointWith):
        a, b = _safe_ce(g, s), _safe_ce(g, o)
        if a is not None and b is not None:
            yield Axiom("DisjointClasses", (a, b), s)
    for n in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members = tuple(filter(None, (_safe_ce(g, x)
                                      for x in _list(g, g.value(n, OWL.members)))))
        yield Axiom("DisjointClasses", members, n)
    for s, lst in g.subject_objects(OWL.disjointUnionOf):
        yield Axiom("DisjointUnion", (s, tuple(parse_ce(g, x) for x in _list(g, lst))), s)
    for s, o in g.subject_objects(RDFS.subPropertyOf):
        yield Axiom("SubPropertyOf", (parse_prop(g, s), parse_prop(g, o)), s)
    for s, lst in g.subject_objects(OWL.propertyChainAxiom):
        chain = tuple(parse_prop(g, x) for x in _list(g, lst))
        yield Axiom("SubPropertyChainOf", (chain, s), s)
    for s, o in g.subject_objects(OWL.equivalentProperty):
        yield Axiom("EquivalentProperties", (s, o), s)
    for s, o in g.subject_objects(OWL.propertyDisjointWith):
        yield Axiom("DisjointProperties", (s, o), s)
    for s, o in g.subject_objects(OWL.inverseOf):
        if isinstance(s, URIRef):
            yield Axiom("InverseProperties", (s, o), s)
    for pred, kind in ((RDFS.domain, "PropertyDomain"), (RDFS.range, "PropertyRange")):
        for s, o in g.subject_objects(pred):
            if kind == "PropertyRange" and (is_data_property(g, s) or _is_datatype(g, o)):
                try:
                    yield Axiom("DataPropertyRange", (s, parse_data_range(g, o)), s)
                except UnsupportedConstruct:
                    pass
                continue
            ce = _safe_ce(g, o)
            if ce is not None:
                yield Axiom(kind, (s, ce), s)
    for s, lst in g.subject_objects(OWL.hasKey):
        yield Axiom("HasKey", (parse_ce(g, s), tuple(_list(g, lst))), s)
    for s, t in g.subject_objects(RDF.type):
        if t in CHARACTERISTICS:
            yield Axiom(CHARACTERISTICS[t], (parse_prop(g, s),), s)
        elif t in DECLARATIONS:
            if include_declarations and isinstance(s, URIRef):
                yield Axiom("Declaration", (DECLARATIONS[t], s), s)
        elif t not in _SKIP_TYPES and isinstance(s, URIRef):
            ce = _safe_ce(g, t)
            if ce is not None and not _is_class_like(g, s):
                yield Axiom("ClassAssertion", (ce, s), s)
    for s, o in g.subject_objects(OWL.sameAs):
        yield Axiom("SameIndividual", (s, o), s)
    for s, o in g.subject_objects(OWL.differentFrom):
        yield Axiom("DifferentIndividuals", (s, o), s)
    for n in g.subjects(RDF.type, OWL.AllDifferent):
        lst = g.value(n, OWL.members) or g.value(n, OWL.distinctMembers)
        yield Axiom("DifferentIndividuals", tuple(_list(g, lst)), n)
    # Property assertions between named individuals.
    obj_props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    data_props = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    ann_props = set(g.subjects(RDF.type, OWL.AnnotationProperty))
    for s, p, o in g:
        if not isinstance(s, URIRef) or p in _NON_LOGICAL:
            continue
        if p in obj_props and isinstance(o, URIRef):
            yield Axiom("ObjectPropertyAssertion", (p, s, o), s)
        elif p in data_props and isinstance(o, Literal):
            yield Axiom("DataPropertyAssertion", (p, s, o), s)
        elif include_annotations and (p in ann_props or _is_builtin_annotation(p)):
            yield Axiom("AnnotationAssertion", (p, s, o), s)


_BUILTIN_ANN = {RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.isDefinedBy,
                OWL.deprecated, OWL.versionInfo}


def _is_builtin_annotation(p: Node) -> bool:
    return p in _BUILTIN_ANN or str(p).startswith(("http://www.w3.org/2004/02/skos/core#",
                                                   "http://purl.org/dc/"))


def axiom_triples(ax: Axiom, graph: Graph | None = None) -> list[Triple]:
    """The triples that encode *ax*.

    Without ``graph`` the result uses fresh blank nodes (for **adding**). With
    ``graph`` it returns the matching *existing* triples, including the full
    blank-node closure of anonymous class expressions (for **removing**).
    """
    if graph is not None:
        return _existing(ax, graph)
    out: list[Triple] = []
    k, a = ax.kind, ax.args
    if k == "SubClassOf":
        out.append((ce_triples(a[0], out), RDFS.subClassOf, ce_triples(a[1], out)))
    elif k == "EquivalentClasses":
        nodes = [ce_triples(x, out) for x in a]
        for x in nodes[1:]:
            out.append((nodes[0], OWL.equivalentClass, x))
    elif k == "DisjointClasses":
        if len(a) == 2:
            out.append((ce_triples(a[0], out), OWL.disjointWith, ce_triples(a[1], out)))
        else:
            n = BNode()
            out.append((n, RDF.type, OWL.AllDisjointClasses))
            out.append((n, OWL.members, _emit_list([ce_triples(x, out) for x in a], out)))
    elif k == "DisjointUnion":
        out.append((a[0], OWL.disjointUnionOf,
                    _emit_list([ce_triples(x, out) for x in a[1]], out)))
    elif k == "SubPropertyOf":
        out.append((prop_triples(a[0], out), RDFS.subPropertyOf, prop_triples(a[1], out)))
    elif k == "SubPropertyChainOf":
        out.append((a[1], OWL.propertyChainAxiom,
                    _emit_list([prop_triples(x, out) for x in a[0]], out)))
    elif k == "EquivalentProperties":
        out.append((a[0], OWL.equivalentProperty, a[1]))
    elif k == "DisjointProperties":
        out.append((a[0], OWL.propertyDisjointWith, a[1]))
    elif k == "InverseProperties":
        out.append((a[0], OWL.inverseOf, a[1]))
    elif k == "PropertyDomain":
        out.append((a[0], RDFS.domain, ce_triples(a[1], out)))
    elif k == "PropertyRange":
        out.append((a[0], RDFS.range, ce_triples(a[1], out)))
    elif k == "DataPropertyRange":
        out.append((a[0], RDFS.range, data_range_triples(a[1], out)))
    elif k == "HasKey":
        out.append((ce_triples(a[0], out), OWL.hasKey, _emit_list(list(a[1]), out)))
    elif k in CHARACTERISTICS.values():
        t = next(t for t, n in CHARACTERISTICS.items() if n == k)
        out.append((prop_triples(a[0], out), RDF.type, t))
    elif k == "Declaration":
        t = next(t for t, n in DECLARATIONS.items() if n == a[0])
        out.append((a[1], RDF.type, t))
    elif k == "ClassAssertion":
        out.append((a[1], RDF.type, ce_triples(a[0], out)))
    elif k == "SameIndividual":
        out.append((a[0], OWL.sameAs, a[1]))
    elif k == "DifferentIndividuals":
        if len(a) == 2:
            out.append((a[0], OWL.differentFrom, a[1]))
        else:
            n = BNode()
            out.append((n, RDF.type, OWL.AllDifferent))
            out.append((n, OWL.members, _emit_list(list(a), out)))
    elif k in ("ObjectPropertyAssertion", "DataPropertyAssertion", "AnnotationAssertion"):
        out.append((a[1], a[0], a[2]))
    else:
        raise ValueError(f"unknown axiom kind {k!r}")
    return out


def bnode_closure(g: Graph, root: Node) -> set[Triple]:
    """Every triple reachable from *root* through blank-node objects."""
    out: set[Triple] = set()
    stack = [root] if isinstance(root, BNode) else []
    seen: set[Node] = set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for p, o in g.predicate_objects(n):
            out.add((n, p, o))
            if isinstance(o, BNode):
                stack.append(o)
    return out


_AXIOM_PRED = {
    "SubClassOf": RDFS.subClassOf, "EquivalentClasses": OWL.equivalentClass,
    "DisjointClasses": OWL.disjointWith, "SubPropertyOf": RDFS.subPropertyOf,
    "PropertyDomain": RDFS.domain, "PropertyRange": RDFS.range,
    "DataPropertyRange": RDFS.range, "HasKey": OWL.hasKey,
    "DisjointUnion": OWL.disjointUnionOf, "SubPropertyChainOf": OWL.propertyChainAxiom,
    "ClassAssertion": RDF.type,
}


def _existing(ax: Axiom, g: Graph) -> list[Triple]:
    """Locate the existing triples of *ax* in *g* by structural comparison.

    Each candidate triple of the axiom's predicate is re-read as an axiom on its
    own and compared structurally, so ``SubClassOf(A, hasPart some B)`` finds its
    triple even though the restriction's blank node has an arbitrary label.
    """
    pred = _AXIOM_PRED.get(ax.kind)
    if pred is None and not (ax.kind == "DifferentIndividuals" and len(ax.args) > 2):
        # Ground axioms (no blank nodes): the triples are themselves.
        return [t for t in axiom_triples(ax) if t in g]
    found: set[Triple] = set()
    if pred is not None:
        for s, o in g.subject_objects(pred):
            tmp = triples_to_graph(bnode_closure(g, s) | bnode_closure(g, o) | {(s, pred, o)})
            for t in g.triples((None, RDF.type, None)):
                if isinstance(t[0], URIRef):
                    tmp.add(t)   # declarations decide data-vs-object readings
            if any(c == ax for c in axioms(tmp, include_annotations=False,
                                           include_declarations=False)):
                found.add((s, pred, o))
                found |= bnode_closure(g, s) | bnode_closure(g, o)
    # n-ary forms: owl:AllDisjointClasses / owl:AllDifferent
    nary = {"DisjointClasses": OWL.AllDisjointClasses,
            "DifferentIndividuals": OWL.AllDifferent}.get(ax.kind)
    if nary is not None:
        for n in g.subjects(RDF.type, nary):
            lst = g.value(n, OWL.members) or g.value(n, OWL.distinctMembers)
            members = [_safe_ce(g, x) if ax.kind == "DisjointClasses" else x
                       for x in _list(g, lst)]
            if Axiom(ax.kind, tuple(members)) == ax:
                found |= bnode_closure(g, n)
    return sorted(found, key=str)


def signature(ce) -> set[URIRef]:
    """Named entities used in a class expression / data range / property expression."""
    out: set[URIRef] = set()

    def walk(x) -> None:
        if isinstance(x, URIRef):
            out.add(x)
        elif isinstance(x, Inverse):
            out.add(x.prop)
        elif isinstance(x, (And, Or)):
            for y in x.operands:
                walk(y)
        elif isinstance(x, Not):
            walk(x.operand)
        elif isinstance(x, OneOf):
            out.update(x.individuals)
        elif isinstance(x, (Some, Only)):
            walk(x.prop); walk(x.filler)
        elif isinstance(x, HasValue):
            walk(x.prop)
            if isinstance(x.value, URIRef):
                out.add(x.value)
        elif isinstance(x, HasSelf):
            walk(x.prop)
        elif isinstance(x, Card):
            walk(x.prop)
            if x.filler is not None:
                walk(x.filler)
        elif isinstance(x, DatatypeRestriction):
            out.add(x.datatype)
        elif isinstance(x, DataNary):
            for y in x.operands:
                walk(y)
        elif isinstance(x, DataComplementOf):
            walk(x.operand)
        elif isinstance(x, (tuple, list)):
            for y in x:
                walk(y)
    walk(ce)
    return out


def axiom_signature(ax: Axiom) -> set[URIRef]:
    sig = signature(ax.args)
    sig.discard(OWL.Thing)
    return sig


def triples_to_graph(triples: Iterable[Triple]) -> Graph:
    g = Graph()
    for t in triples:
        g.add(t)
    return g
