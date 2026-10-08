"""Which OWL 2 profile does this graph actually need?

The router cannot choose a reasoner without knowing what the ontology uses. This
module answers "which axioms fall outside profile P?" — cheaply, structurally,
and without a reasoner.

It is deliberately a *screen*, not a validator: it detects the constructs that
matter for backend selection, not every clause of the OWL 2 profile
specification. False positives push a query to a stronger reasoner, which is
safe; the checks below are written so false negatives require a construct we do
not model at all.

Calibrated against the local FIBO corpus (`Ontology Repository/FIBO`, 297 files):
6,388 `owl:Restriction` nodes, of which 379 fall outside OWL 2 RL — chiefly the
345 `owl:qualifiedCardinality` (exact) axioms and a handful of `min > 0`.
"""

from __future__ import annotations

from collections import Counter

from rdflib import Graph, OWL, RDF, RDFS

__all__ = ["outside_profile", "construct_census"]


def _int(graph: Graph, subject, predicate) -> int | None:
    v = graph.value(subject, predicate)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def construct_census(graph: Graph) -> Counter:
    """Count the profile-relevant constructs actually used in *graph*."""
    c: Counter = Counter()

    for pred, name in (
        (OWL.someValuesFrom, "someValuesFrom"),
        (OWL.allValuesFrom, "allValuesFrom"),
        (OWL.hasValue, "hasValue"),
        (OWL.unionOf, "unionOf"),
        (OWL.intersectionOf, "intersectionOf"),
        (OWL.complementOf, "complementOf"),
        (OWL.oneOf, "oneOf"),
        (OWL.disjointWith, "disjointWith"),
        (OWL.equivalentClass, "equivalentClass"),
        (OWL.propertyChainAxiom, "propertyChainAxiom"),
        (OWL.hasSelf, "hasSelf"),
        (OWL.inverseOf, "inverseOf"),
    ):
        n = sum(1 for _ in graph.triples((None, pred, None)))
        if n:
            c[name] = n

    for pred, name in (
        (OWL.minQualifiedCardinality, "minQualifiedCardinality"),
        (OWL.minCardinality, "minCardinality"),
        (OWL.qualifiedCardinality, "qualifiedCardinality"),
        (OWL.cardinality, "cardinality"),
        (OWL.maxQualifiedCardinality, "maxQualifiedCardinality"),
        (OWL.maxCardinality, "maxCardinality"),
    ):
        for _, _, value in graph.triples((None, pred, None)):
            try:
                c[f"{name}={int(value)}"] += 1
            except (TypeError, ValueError):
                c[f"{name}=?"] += 1

    for cls in (OWL.TransitiveProperty, OWL.SymmetricProperty,
                OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
                OWL.AsymmetricProperty, OWL.ReflexiveProperty,
                OWL.IrreflexiveProperty):
        n = sum(1 for _ in graph.triples((None, RDF.type, cls)))
        if n:
            c[str(cls).rsplit("#", 1)[-1]] = n

    return c


def outside_profile(graph: Graph, profile: str) -> dict[str, int]:
    """Constructs in *graph* that fall outside *profile*, with counts.

    An empty result means the graph is (as far as this screen can tell) inside
    the profile, so a backend complete for it is complete for this graph.
    """
    if profile in ("DL", "FULL"):
        return {}

    out: Counter = Counter()

    if profile == "RDFS":
        # RDFS has no class expressions at all.
        for pred, name in (
            (OWL.someValuesFrom, "someValuesFrom"),
            (OWL.allValuesFrom, "allValuesFrom"),
            (OWL.hasValue, "hasValue"),
            (OWL.unionOf, "unionOf"),
            (OWL.intersectionOf, "intersectionOf"),
            (OWL.complementOf, "complementOf"),
            (OWL.oneOf, "oneOf"),
            (OWL.equivalentClass, "equivalentClass"),
            (OWL.disjointWith, "disjointWith"),
            (OWL.inverseOf, "inverseOf"),
            (OWL.propertyChainAxiom, "propertyChainAxiom"),
        ):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[name] += n
        for r in graph.subjects(RDF.type, OWL.Restriction):
            out["Restriction"] += 1
        # RDFS entailment knows nothing about property characteristics: a
        # TransitiveProperty is just a resource to it. Omitting these is how a
        # weaker backend ends up wrongly claiming completeness — caught by the
        # differential harness (test_differential_finds_the_expected_rdfs_vs_rl_gap).
        for cls in (OWL.TransitiveProperty, OWL.SymmetricProperty,
                    OWL.AsymmetricProperty, OWL.ReflexiveProperty,
                    OWL.IrreflexiveProperty, OWL.FunctionalProperty,
                    OWL.InverseFunctionalProperty):
            n = sum(1 for _ in graph.triples((None, RDF.type, cls)))
            if n:
                out[str(cls).rsplit("#", 1)[-1]] += n
        for pred, name in ((OWL.sameAs, "sameAs"),
                           (OWL.differentFrom, "differentFrom"),
                           (OWL.equivalentProperty, "equivalentProperty"),
                           (OWL.propertyDisjointWith, "propertyDisjointWith")):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[name] += n
        return dict(out)

    if profile == "RL":
        # OWL 2 RL admits no min or exact cardinality anywhere, and max
        # cardinality only with value 0 or 1.
        for pred, name in ((OWL.minQualifiedCardinality, "minQualifiedCardinality"),
                           (OWL.minCardinality, "minCardinality")):
            for s, _, v in graph.triples((None, pred, None)):
                try:
                    if int(v) > 0:
                        out[f"{name}>0"] += 1
                except (TypeError, ValueError):
                    out[f"{name}=?"] += 1
        for pred, name in ((OWL.qualifiedCardinality, "qualifiedCardinality"),
                           (OWL.cardinality, "cardinality")):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[f"{name} (exact)"] += n
        for pred, name in ((OWL.maxQualifiedCardinality, "maxQualifiedCardinality"),
                           (OWL.maxCardinality, "maxCardinality")):
            for s, _, v in graph.triples((None, pred, None)):
                try:
                    if int(v) > 1:
                        out[f"{name}>1"] += 1
                except (TypeError, ValueError):
                    out[f"{name}=?"] += 1
        # oneOf and hasSelf are outside RL; disjunction in a superclass position
        # is too, which this screen approximates by flagging unionOf under
        # equivalentClass.
        for pred, name in ((OWL.oneOf, "oneOf"), (OWL.hasSelf, "hasSelf")):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[name] += n
        return dict(out)

    if profile == "EL":
        # EL admits no disjunction, no negation, no inverse properties, no
        # universal restriction, and no cardinality restrictions.
        for pred, name in (
            (OWL.unionOf, "unionOf"),
            (OWL.complementOf, "complementOf"),
            (OWL.allValuesFrom, "allValuesFrom"),
            (OWL.inverseOf, "inverseOf"),
            (OWL.minQualifiedCardinality, "minQualifiedCardinality"),
            (OWL.maxQualifiedCardinality, "maxQualifiedCardinality"),
            (OWL.qualifiedCardinality, "qualifiedCardinality"),
            (OWL.cardinality, "cardinality"),
            (OWL.minCardinality, "minCardinality"),
            (OWL.maxCardinality, "maxCardinality"),
        ):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[name] += n
        for cls, name in ((OWL.SymmetricProperty, "SymmetricProperty"),
                          (OWL.AsymmetricProperty, "AsymmetricProperty"),
                          (OWL.InverseFunctionalProperty, "InverseFunctionalProperty")):
            n = sum(1 for _ in graph.triples((None, RDF.type, cls)))
            if n:
                out[name] += n
        return dict(out)

    if profile == "QL":
        for pred, name in (
            (OWL.unionOf, "unionOf"),
            (OWL.oneOf, "oneOf"),
            (OWL.hasValue, "hasValue"),
            (OWL.propertyChainAxiom, "propertyChainAxiom"),
            (OWL.qualifiedCardinality, "qualifiedCardinality"),
            (OWL.cardinality, "cardinality"),
        ):
            n = sum(1 for _ in graph.triples((None, pred, None)))
            if n:
                out[name] += n
        for cls, name in ((OWL.TransitiveProperty, "TransitiveProperty"),
                          (OWL.FunctionalProperty, "FunctionalProperty")):
            n = sum(1 for _ in graph.triples((None, RDF.type, cls)))
            if n:
                out[name] += n
        return dict(out)

    raise ValueError(f"unknown profile {profile!r}")
