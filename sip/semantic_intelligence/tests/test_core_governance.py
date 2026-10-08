"""Core (store, change tracking, staging, undo) and governance (roles, PDP, settings, IRIs)."""

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from semantic_intelligence.core.changes import ChangeSet, ChangeTracker, ConflictError, ValidationError
from semantic_intelligence.core.layout import ProjectLayout
from semantic_intelligence.core.namespaces import CL
from semantic_intelligence.core.principal import Principal
from semantic_intelligence.core.store import FusekiStore, InMemoryStore
from semantic_intelligence.governance.capabilities import role_grants
from semantic_intelligence.governance.registry import (AccessLevel, LockLevel, PolicyDecisionPoint,
                                                        ProjectACL, ProjectConfig, Registry)
from semantic_intelligence.governance.settings import SettingsStore
from semantic_intelligence.governance.urigen import EntityCreationPreferences, TemplateURIGenerator

A, B = URIRef("http://ex/A"), URIRef("http://ex/B")
ALICE, BOT, VAL = Principal("alice"), Principal("bot", is_machine=True, on_behalf_of="alice"), Principal("val")


@pytest.fixture
def tracker():
    st = InMemoryStore()
    return ChangeTracker(st, ProjectLayout("p1"))


def test_effective_delta_and_noop(tracker):
    L = tracker.layout
    c = tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), ALICE)
    assert c.status == "committed" and len(c.additions) == 1
    assert tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), ALICE) is None
    # add + remove of the same quad cancels
    cs = ChangeSet("x", {}, L.main).add(B, RDF.type, OWL.Class).remove(B, RDF.type, OWL.Class)
    assert tracker.commit(cs, ALICE) is None


def test_history_uses_semantic_turkey_changelog(tracker):
    L = tracker.layout
    c = tracker.commit(ChangeSet("createClass", {"iri": str(A)}, L.main).add(A, RDF.type, OWL.Class), ALICE)
    h = tracker.store.graph(L.history)
    assert (c.iri, RDF.type, CL.Commit) in h
    quads = list(h.objects(c.iri, CL.addedStatement))
    assert len(quads) == 1 and (quads[0], CL.subject, A) in h and (quads[0], CL.context, L.main) in h


def test_machine_writes_are_always_staged(tracker):
    L = tracker.layout
    c = tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), BOT)
    assert c.status == "staged"
    assert tracker.store.size(L.main) == 0 and tracker.store.size(L.staging_add(L.main)) == 1
    assert tracker.triple_status(A, RDF.type, OWL.Class) == "staged-add"
    assert (A, RDF.type, OWL.Class) in tracker.view(staged=True)


def test_accept_and_reject(tracker):
    L = tracker.layout
    c = tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), BOT)
    tracker.accept(c.id, VAL)
    assert tracker.store.size(L.main) == 1 and tracker.store.size(L.staging_add(L.main)) == 0
    assert tracker.get(c.id).status == "accepted" and tracker.get(c.id).validated_by == "val"
    with pytest.raises(ValidationError):
        tracker.accept(c.id, VAL)
    r = tracker.commit(ChangeSet("x", {}, L.main).remove(A, RDF.type, OWL.Class), BOT)
    assert tracker.triple_status(A, RDF.type, OWL.Class) == "staged-del"
    n_hist = tracker.store.size(L.history)
    tracker.reject(r.id, VAL)
    # reject leaves no trace: content unchanged, staging empty, history record gone
    assert tracker.store.size(L.main) == 1 and tracker.store.size(L.staging_del(L.main)) == 0
    assert r.id not in {x.id for x in tracker.commits} and tracker.store.size(L.history) < n_hist


def test_accept_detects_conflict(tracker):
    L = tracker.layout
    tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), ALICE)
    staged = tracker.commit(ChangeSet("rm", {}, L.main).remove(A, RDF.type, OWL.Class), BOT)
    tracker.commit(ChangeSet("rm", {}, L.main).remove(A, RDF.type, OWL.Class), ALICE)
    with pytest.raises(ConflictError):
        tracker.accept(staged.id, VAL)


def test_undo_redo_are_commits(tracker):
    L = tracker.layout
    tracker.commit(ChangeSet("x", {}, L.main).add(A, RDF.type, OWL.Class), ALICE)
    u = tracker.undo(ALICE)
    assert u.operation == "undo" and tracker.store.size(L.main) == 0
    assert tracker.can_redo(ALICE)
    tracker.redo(ALICE)
    assert tracker.store.size(L.main) == 1
    # a new edit clears the redo stack (Protégé semantics)
    tracker.undo(ALICE)
    tracker.commit(ChangeSet("y", {}, L.main).add(B, RDF.type, OWL.Class), ALICE)
    assert not tracker.can_redo(ALICE)
    assert tracker.undo(BOT) is None                    # nothing of bot's to undo


def test_derived_graph_write_refuses_content(tracker):
    with pytest.raises(PermissionError):
        tracker.replace_derived(tracker.layout.main, [])
    assert tracker.replace_derived(tracker.layout.inferred, [(A, RDF.type, OWL.Class)]) == 1


def test_fuseki_update_text_handles_blank_nodes():
    from rdflib import BNode
    b, g = BNode("r1"), URIRef("urn:g")
    text = FusekiStore.update_text([(A, RDFS.subClassOf, b, g)], [(b, OWL.onProperty, A, g), (A, RDF.type, OWL.Class, g)])
    assert "DELETE DATA" in text and "?b_r1" in text and "INSERT DATA" in text and "_:r1" in text


# ------------------------------------------------------------------ roles
GOALS = ['auth(rdf(cls), "C")', 'auth(rdf(concept), "C")', 'auth(rdf(concept), "R")',
         'auth(rdf(concept,lexicalization), "C")', 'auth(rdf(cls), "V")',
         'auth(rdf(sparql,support), "R")', 'auth(rdf(resource,alignment), "C")']
EXPECTED = {
    "lurker": [0, 0, 1, 0, 0, 0, 0], "ontologist": [1, 1, 1, 1, 1, 0, 1],
    "thesaurus-editor": [0, 1, 1, 1, 0, 0, 0], "validator": [0, 0, 1, 0, 1, 0, 0],
    "lexicographer": [0, 0, 1, 1, 0, 0, 0], "mapper": [0, 0, 1, 0, 0, 0, 1],
    "projectmanager": [1, 1, 1, 1, 1, 1, 1], "rdfgeek": [1, 1, 1, 1, 1, 0, 1],
    "agent-ontology-copilot": [1, 1, 1, 1, 0, 0, 1],
}


@pytest.mark.parametrize("role", sorted(EXPECTED))
def test_semantic_turkey_role_matrix(role):
    g = role_grants(role)
    assert [int(g.authorize(x)) for x in GOALS] == EXPECTED[role]


def _pdp(**cfg):
    reg = Registry()
    reg.add_project(ProjectConfig("p", "http://ex/p", languages=("en", "fr"), **cfg))
    for p in (ALICE, BOT, VAL, Principal("terminologist"), Principal("root", is_admin=True)):
        reg.add_principal(p)
    reg.bind("alice", "p", ["ontologist"])
    reg.bind("bot", "p", ["projectmanager"])            # even a PM role cannot give a machine V
    reg.bind("val", "p", ["validator"])
    reg.bind("terminologist", "p", ["lexicographer"], languages=["fr"])
    return PolicyDecisionPoint(reg), reg


def test_pdp_rules():
    pdp, reg = _pdp()
    assert pdp.authorize(ALICE, "p", "rdf(cls)", "C")
    assert not pdp.authorize(BOT, "p", "rdf", "V")                       # QR-SEC-02
    assert pdp.authorize(BOT, "p", "rdf(cls)", "C")
    t = reg.principal("terminologist")
    assert pdp.authorize(t, "p", "rdf(concept, lexicalization)", "C", languages=["fr"])
    assert not pdp.authorize(t, "p", "rdf(concept, lexicalization)", "C", languages=["en"])
    assert not pdp.authorize(ALICE, "p", "rdf(cls)", "C", languages=["de"])   # not a project lang
    assert pdp.authorize(reg.principal("root"), "p", "rdf", "CRUDV")
    assert not pdp.authorize(Principal("stranger"), "p", "rdf", "R")


def test_pdp_read_only_and_acl():
    pdp, reg = _pdp(read_only=True)
    assert not pdp.authorize(reg.principal("root"), "p", "rdf(cls)", "C")   # read-only beats admin
    acl = ProjectACL(entries={"SYSTEM": AccessLevel.RW, "other": AccessLevel.R})
    assert acl.is_accessible_from("other", AccessLevel.R)
    assert not acl.is_accessible_from("other", AccessLevel.RW)
    assert not acl.is_accessible_from("nobody", AccessLevel.R)
    acl.universal = AccessLevel.R
    assert acl.is_accessible_from("nobody", AccessLevel.R)
    acl.lock_level = LockLevel.NO
    assert not acl.is_accessible_from("other", AccessLevel.R, LockLevel.W)


def test_machine_needs_on_behalf_of():
    with pytest.raises(ValueError):
        Registry().add_principal(Principal("orphan", is_machine=True))


def test_settings_scope_merge():
    s = SettingsStore()
    s.store("rendering", "sys", {"lang": "en", "mode": "label"}, default_of="pu")
    s.store("rendering", "proj", {"lang": "fr"}, project="p", default_of="pu")
    s.store("rendering", "pg", {"mode": "prefixed"}, project="p", group="g")
    s.store("rendering", "pu", {"extra": 1}, project="p", user="u")
    assert s.get("rendering", "pu", project="p", user="u", group="g") == {
        "lang": "fr", "mode": "prefixed", "extra": 1}
    assert s.get("rendering", "pu", project="p", user="u") == {"lang": "fr", "mode": "label", "extra": 1}


def test_template_uri_generator():
    gen = TemplateURIGenerator("http://ex/", rand_code="DIGIT", rand_len=4)
    iri = gen.generate("concept", {}, lambda i: False)
    assert str(iri).startswith("http://ex/c_") and len(str(iri)) == len("http://ex/c_") + 4
    xl = gen.generate("xLabel", {"lexicalForm": Literal("Car", lang="en")}, lambda i: False)
    assert str(xl).startswith("http://ex/xl_en_")
    fixed = TemplateURIGenerator("http://ex/", templates={"concept": "fixed"})
    with pytest.raises(ValueError, match="random part"):
        fixed.generate("concept", {}, lambda i: True)


def test_entity_creation_preferences():
    prefs = EntityCreationPreferences(base="http://ex/onto")
    assert str(prefs.mint("Red Wine", "class", lambda i: False)) == "http://ex/onto#Red_Wine"
    with pytest.raises(ValueError):
        prefs.mint("Red Wine", "class", lambda i: True)
    it = EntityCreationPreferences(base="http://ex/onto", mode="auto-id", auto_id="iterative",
                                   iterative_digits=2, iterative_start=99)
    assert str(it.mint("x", "class", lambda i: False)).endswith("class_99")
    with pytest.raises(ValueError, match="exceeds"):
        it.mint("x", "class", lambda i: False)                         # Protégé truncated; we refuse
