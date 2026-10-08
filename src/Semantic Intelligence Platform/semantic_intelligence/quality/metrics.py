"""Ontology metrics — Protégé's *Ontology metrics* view (43 metrics in 6 tables).

Definitions follow OWL API 4 as wired into ``MetricsPanel``: counts over the
axiom view; *GCI count* = SubClassOf with an anonymous left-hand side;
*hidden GCI count* = named classes that have both an ``EquivalentClasses`` and a
``SubClassOf`` axiom. DL expressivity is commented out in Protégé's source; here
an *expressivity hint* is computed from the constructors used (a hint, not a
proof — it inspects syntax, not entailments).
"""

from __future__ import annotations

from collections import Counter

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ..owl.model import (And, Card, HasSelf, HasValue, Inverse, Not, OneOf, Only, Or, Some,
                         axioms)

_GROUPS = {
    "Class axioms": ("SubClassOf", "EquivalentClasses", "DisjointClasses"),
    "Object property axioms": ("SubPropertyOf", "EquivalentProperties", "InverseProperties",
                               "DisjointProperties", "FunctionalProperty",
                               "InverseFunctionalProperty", "TransitiveProperty",
                               "SymmetricProperty", "AsymmetricProperty", "ReflexiveProperty",
                               "IrreflexiveProperty", "PropertyDomain", "PropertyRange",
                               "SubPropertyChainOf"),
    "Data property axioms": ("DataPropertyRange",),
    "Individual axioms": ("ClassAssertion", "ObjectPropertyAssertion", "DataPropertyAssertion",
                          "SameIndividual", "DifferentIndividuals"),
    "Annotation axioms": ("AnnotationAssertion",),
}


def metrics(g: Graph) -> dict[str, dict[str, int]]:
    axs = list(axioms(g))
    kinds = Counter(a.kind for a in axs)
    logical = sum(n for k, n in kinds.items() if k not in ("Declaration", "AnnotationAssertion"))

    def count_type(t):
        return len({s for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)})
    out: dict[str, dict[str, int]] = {"Metrics": {
        "Axiom": len(axs), "Logical axiom count": logical,
        "Declaration axioms count": kinds.get("Declaration", 0),
        "Class count": count_type(OWL.Class),
        "Object property count": count_type(OWL.ObjectProperty),
        "Data property count": count_type(OWL.DatatypeProperty),
        "Individual count": len({a.args[1] for a in axs if a.kind == "ClassAssertion"}
                                | {s for s in g.subjects(RDF.type, OWL.NamedIndividual)}),
        "Annotation property count": count_type(OWL.AnnotationProperty),
    }}
    for group, ks in _GROUPS.items():
        out[group] = {k: kinds.get(k, 0) for k in ks}
    gcis = sum(1 for a in axs if a.kind == "SubClassOf" and not isinstance(a.args[0], URIRef))
    defined = {x for a in axs if a.kind == "EquivalentClasses" for x in a.args
               if isinstance(x, URIRef)}
    primitive = {a.args[0] for a in axs if a.kind == "SubClassOf" and isinstance(a.args[0], URIRef)}
    out["Class axioms"]["GCI count"] = gcis
    out["Class axioms"]["Hidden GCI Count"] = len(defined & primitive)
    out["Metrics"]["DL expressivity (hint)"] = expressivity(axs)  # type: ignore[assignment]
    return out


def expressivity(axs) -> str:
    """Constructor-based DL name hint, e.g. ``ALCHIQ(D)``."""
    flags: set[str] = set()

    def walk(x):
        if isinstance(x, (And,)):
            for y in x.operands:
                walk(y)
        elif isinstance(x, Or):
            flags.add("U")
            for y in x.operands:
                walk(y)
        elif isinstance(x, Not):
            flags.add("C")
            walk(x.operand)
        elif isinstance(x, OneOf):
            flags.add("O")
        elif isinstance(x, (Some, Only)):
            if isinstance(x, Only):
                flags.add("A")
            if isinstance(x.prop, Inverse):
                flags.add("I")
            if x.data:
                flags.add("D")
            else:
                walk(x.filler)
        elif isinstance(x, HasValue):
            flags.add("O")
            if x.data:
                flags.add("D")
        elif isinstance(x, HasSelf):
            flags.add("Self")
        elif isinstance(x, Card):
            flags.add("Q" if x.filler is not None else "N")
            if x.data:
                flags.add("D")
        elif isinstance(x, tuple):
            for y in x:
                walk(y)
    for a in axs:
        k = a.kind
        if k in ("SubClassOf", "EquivalentClasses", "DisjointClasses", "PropertyDomain",
                 "PropertyRange", "ClassAssertion", "DisjointUnion"):
            walk(a.args)
            if k == "DisjointClasses":
                flags.add("C")
        elif k == "SubPropertyOf":
            flags.add("H")
        elif k == "InverseProperties":
            flags.add("I")
        elif k == "TransitiveProperty":
            flags.add("+")
        elif k in ("FunctionalProperty", "InverseFunctionalProperty"):
            flags.add("F")
        elif k == "SubPropertyChainOf":
            flags.add("R")
        elif k == "DataPropertyRange":
            flags.add("D")
    base = "AL" + ("C" if "C" in flags or ("U" in flags and "E" in flags) else "")
    if "U" in flags and "C" not in flags:
        base += "U"
    if "+" in flags:
        base = base.replace("ALC", "S") if base.startswith("ALC") else base + "+"
    name = base
    if "R" in flags:
        name = name.replace("S", "SR") if name.startswith("S") else name + "R"
    elif "H" in flags:
        name += "H"
    for f in ("O", "I"):
        if f in flags:
            name += f
    if "Q" in flags:
        name += "Q"
    elif "N" in flags:
        name += "N"
    elif "F" in flags:
        name += "F"
    if "D" in flags:
        name += "(D)"
    return name
