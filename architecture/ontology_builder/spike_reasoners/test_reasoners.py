"""Tests for the multi-reasoner framework.

Run:  python -m pytest architecture/ontology_builder/spike_reasoners -q

These run in this workstation's actual condition — `owlrl` present, **no JVM** —
so the sidecar-degradation path is exercised for real rather than mocked.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef

from backends import (
    Answer,
    OWLRLBackend,
    Profile,
    RDFSBackend,
    ReasonerError,
    ReasonerUnavailable,
    SidecarBackend,
)
from profile_check import construct_census, outside_profile
from router import DEFAULT_POLICY, ReasonerRouter, differential

EX = Namespace("http://example.org/")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def rdfs_only() -> Graph:
    """A plain taxonomy — inside every profile."""
    g = Graph()
    g.add((EX.Dog, RDFS.subClassOf, EX.Mammal))
    g.add((EX.Mammal, RDFS.subClassOf, EX.Animal))
    g.add((EX.rex, RDF.type, EX.Dog))
    return g


@pytest.fixture
def rl_safe() -> Graph:
    """Uses OWL constructs, but all inside OWL 2 RL."""
    g = Graph()
    g.add((EX.Dog, RDFS.subClassOf, EX.Mammal))
    g.add((EX.hasParent, RDF.type, OWL.ObjectProperty))
    g.add((EX.hasAncestor, RDF.type, OWL.TransitiveProperty))
    g.add((EX.hasParent, RDFS.subPropertyOf, EX.hasAncestor))
    g.add((EX.a, EX.hasParent, EX.b))
    g.add((EX.b, EX.hasParent, EX.c))
    return g


@pytest.fixture
def fibo_shaped() -> Graph:
    """The shape that actually appears in FIBO: an exact qualified cardinality.

    `owl:qualifiedCardinality` is outside OWL 2 RL — the local FIBO corpus has
    345 of these. This is the fixture that proves the framework notices.
    """
    g = Graph()
    r = URIRef("http://example.org/_restriction")
    g.add((EX.Loan, RDFS.subClassOf, r))
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, EX.hasPrincipal))
    g.add((r, OWL.qualifiedCardinality, Literal(1)))
    g.add((r, OWL.onClass, EX.MonetaryAmount))
    return g


# --------------------------------------------------------------------------- #
# Capability declarations
# --------------------------------------------------------------------------- #
def test_backends_declare_distinct_envelopes():
    rdfs, rl = RDFSBackend(), OWLRLBackend()
    assert rdfs.capabilities.complete_for == Profile.RDFS
    assert rl.capabilities.complete_for == Profile.RL
    assert Profile.stronger(Profile.RL, Profile.RDFS)
    assert Profile.stronger(Profile.DL, Profile.RL)


def test_rdfs_backend_does_not_claim_satisfiability():
    """A backend must not offer an operation it cannot answer meaningfully.

    RDFS has no notion of unsatisfiability, so the operation is *absent* rather
    than returning a misleading 'nothing is unsatisfiable'."""
    assert not RDFSBackend().capabilities.supports("satisfiability")
    assert not RDFSBackend().capabilities.supports("consistency")
    assert OWLRLBackend().capabilities.supports("satisfiability")


def test_only_the_dl_backend_offers_explanations():
    assert SidecarBackend("hermit").capabilities.supports("explain")
    assert not SidecarBackend("elk").capabilities.supports("explain")
    assert not OWLRLBackend().capabilities.supports("explain")
    assert not RDFSBackend().capabilities.supports("explain")


def test_unsupported_operation_raises_rather_than_lying(rdfs_only):
    with RDFSBackend().session(rdfs_only) as s:
        with pytest.raises(ReasonerError, match="does not support"):
            s.unsatisfiable()


def test_capabilities_reject_unknown_operations():
    from backends import ReasonerCapabilities
    with pytest.raises(ValueError, match="unknown operations"):
        ReasonerCapabilities("x", "X", Profile.RL, frozenset({"teleport"}),
                             False, "polynomial", "in-process")


# --------------------------------------------------------------------------- #
# Profile screening
# --------------------------------------------------------------------------- #
def test_plain_taxonomy_is_inside_every_profile(rdfs_only):
    for p in (Profile.RDFS, Profile.RL, Profile.EL, Profile.QL):
        assert outside_profile(rdfs_only, p) == {}, p


def test_exact_cardinality_is_outside_rl(fibo_shaped):
    out = outside_profile(fibo_shaped, Profile.RL)
    assert "qualifiedCardinality (exact)" in out
    assert out["qualifiedCardinality (exact)"] == 1


def test_dl_backend_is_complete_for_everything(fibo_shaped):
    assert outside_profile(fibo_shaped, Profile.DL) == {}


def test_restrictions_are_outside_rdfs(fibo_shaped):
    assert "Restriction" in outside_profile(fibo_shaped, Profile.RDFS)


def test_census_reports_what_is_used(fibo_shaped):
    c = construct_census(fibo_shaped)
    assert c["qualifiedCardinality=1"] == 1


# --------------------------------------------------------------------------- #
# Answers carry their own worth
# --------------------------------------------------------------------------- #
def test_answer_inside_the_envelope_is_complete(rl_safe):
    with OWLRLBackend().session(rl_safe) as s:
        ans = s.entails(EX.a, EX.hasAncestor, EX.c)
    assert ans.value is True
    assert ans.complete
    assert ans.caveat is None
    assert ans.is_definite


def test_answer_outside_the_envelope_is_flagged(fibo_shaped):
    """The key behaviour: an RL backend on FIBO-shaped input says so."""
    with OWLRLBackend().session(fibo_shaped) as s:
        ans = s.entails(EX.Loan, RDFS.subClassOf, EX.Widget)
    assert ans.value is False
    assert not ans.complete
    assert "outside OWL 2 RL" in ans.caveat
    assert "qualifiedCardinality" in ans.caveat
    # A negative from an incomplete backend must not read as definite.
    assert not ans.is_definite
    assert "incomplete" in ans.describe()


def test_a_positive_answer_is_definite_even_when_incomplete(rl_safe, fibo_shaped):
    """Incompleteness only threatens negatives. Soundness means a 'yes' holds."""
    g = rl_safe + fibo_shaped
    with OWLRLBackend().session(g) as s:
        ans = s.entails(EX.a, EX.hasAncestor, EX.c)
    assert ans.value is True and not ans.complete
    assert ans.is_definite            # sound: a derived 'yes' is still a yes


def test_answers_carry_backend_profile_and_timing(rl_safe):
    with OWLRLBackend().session(rl_safe) as s:
        ans = s.materialise()
    assert ans.backend == "owlrl"
    assert ans.profile == Profile.RL
    assert ans.elapsed_ms >= 0.0


# --------------------------------------------------------------------------- #
# Availability and graceful degradation
# --------------------------------------------------------------------------- #
def test_sidecar_is_unavailable_without_a_jvm():
    """This machine has no `java` on PATH — the declared requirement is checked
    up front rather than blowing up inside a request."""
    avail = SidecarBackend("hermit").available()
    assert not avail
    assert "java" in avail.reason


def test_creating_an_unavailable_session_raises_cleanly(rdfs_only):
    with pytest.raises(ReasonerUnavailable, match="java"):
        SidecarBackend("hermit").session(rdfs_only)


def test_router_skips_unavailable_backends_and_says_why(rl_safe):
    router = ReasonerRouter([OWLRLBackend(), RDFSBackend(),
                             SidecarBackend("hermit"), SidecarBackend("elk")])
    cands, trace = router.candidates("materialise")
    ids = [b.capabilities.id for b in cands]
    assert "owlrl" in ids
    assert not any(i.startswith("sidecar") for i in ids)
    skipped = dict(trace.skipped)
    assert "java" in skipped["sidecar:hermit"]


def test_router_respects_the_declared_preference_order(rl_safe):
    router = ReasonerRouter([RDFSBackend(), OWLRLBackend()])
    cands, _ = router.candidates("materialise")
    # policy prefers owlrl over rdfs even though rdfs was registered first
    assert [b.capabilities.id for b in cands] == ["owlrl", "rdfs"]


def test_router_degrades_to_owlrl_when_the_dl_backend_is_absent(fibo_shaped):
    """Satisfiability prefers HermiT; with no JVM it must fall to owlrl **and
    the answer must say it is incomplete**."""
    router = ReasonerRouter([OWLRLBackend(), SidecarBackend("hermit")])
    ans, trace = router.unsatisfiable(fibo_shaped)
    assert trace.chosen == "owlrl"
    assert ("sidecar:hermit", ) in [(k,) for k, _ in trace.skipped]
    assert not ans.complete


def test_router_raises_when_nothing_can_serve_the_operation(rdfs_only):
    router = ReasonerRouter([RDFSBackend(), SidecarBackend("hermit")])
    with pytest.raises(ReasonerUnavailable, match="explain"):
        router.run("explain", rdfs_only, lambda s: s.explain(None, None, None))


def test_trace_is_human_readable(rl_safe):
    router = ReasonerRouter([OWLRLBackend(), SidecarBackend("hermit")])
    _, trace = router.materialise(rl_safe)
    text = trace.explain()
    assert "chose owlrl" in text
    assert "sidecar:hermit" in text


# --------------------------------------------------------------------------- #
# Differential testing — the reason a multi-backend setup is trustworthy
# --------------------------------------------------------------------------- #
def test_backends_agree_where_both_are_complete(rdfs_only):
    """On a plain taxonomy, RDFS and RL are both complete and must agree."""
    questions = [
        ("entails: Dog subClassOf Animal",
         lambda s: s.entails(EX.Dog, RDFS.subClassOf, EX.Animal)),
    ]
    diffs = differential([RDFSBackend(), OWLRLBackend()], rdfs_only, questions)
    assert diffs == [], [d.describe() for d in diffs]


def test_differential_finds_the_expected_rdfs_vs_rl_gap(rl_safe):
    """RDFS cannot chain a transitive property; OWL 2 RL can. The harness must
    surface that as a disagreement and classify it as *expected*, because only
    one of the two backends is complete for this graph."""
    questions = [
        ("entails: a hasAncestor c",
         lambda s: s.entails(EX.a, EX.hasAncestor, EX.c)),
    ]
    diffs = differential([RDFSBackend(), OWLRLBackend()], rl_safe, questions)
    assert len(diffs) == 1
    d = diffs[0]
    assert d.answers["owlrl"] is True
    assert d.answers["rdfs"] is False
    assert d.is_expected                     # explained by declared incompleteness
    assert d.definite == ("owlrl",)          # only RL is complete here
    assert "expected" in d.describe()


def test_a_disagreement_between_two_complete_backends_is_a_bug(rdfs_only):
    """Guard the classifier itself: if two backends are both complete for the
    graph and still disagree, `is_expected` must be False so CI fails."""
    from router import Disagreement
    d = Disagreement("entails: X", {"a": True, "b": False}, definite=("a", "b"))
    assert not d.is_expected
    assert "BUG" in d.describe()


def test_differential_skips_backends_that_lack_the_operation(fibo_shaped):
    questions = [("satisfiability: any", lambda s: s.unsatisfiable())]
    diffs = differential([RDFSBackend(), OWLRLBackend()], fibo_shaped, questions)
    # RDFS does not support satisfiability, so there is only one answer and
    # therefore nothing to disagree about.
    assert diffs == []
