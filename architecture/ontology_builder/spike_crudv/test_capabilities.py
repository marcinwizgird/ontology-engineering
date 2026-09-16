"""Tests for the Python port of VocBench 3's CRUDV capability algebra.

Goals marked *(VB3)* are copied verbatim out of
``vocbench3/src/app/utils/AuthorizationEvaluator.ts``'s ``actionAuthGoalMap``,
so the port is checked against real policy input rather than invented examples.

Run:  python -m pytest architecture/ontology_builder/spike_crudv -q
"""

from __future__ import annotations

import pytest

from capabilities import (
    Capability,
    CapabilitySet,
    Subject,
    Term,
    authorize,
    covered,
    parse_capability,
    parse_term,
    role_grants,
)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, expected", [
    ("rdf", "rdf"),
    ("rdf(cls)", "rdf(cls)"),
    ("rdf(cls, taxonomy)", "rdf(cls, taxonomy)"),
    ("rdf(_,_)", "rdf(_, _)"),
    ('rdf(concept, lexicalization("en,fr"))', "rdf(concept, lexicalization(en,fr))"),
    ("pm(project, collaboration)", "pm(project, collaboration)"),
])
def test_parse_term_roundtrip(text, expected):
    assert str(parse_term(text)) == expected


def test_parse_capability():
    c = parse_capability('capability(rdf(concept, taxonomy), "CRUD")')
    assert str(c.topic) == "rdf(concept, taxonomy)"
    assert c.ops == frozenset("CRUD")


def test_parse_auth_goal_uses_same_grammar():
    """An action goal is parsed by the same function — it is just a request."""
    c = parse_capability('auth(rdf(cls, taxonomy), "C").')
    assert str(c.topic) == "rdf(cls, taxonomy)"
    assert c.ops == frozenset("C")


def test_rejects_unknown_operation():
    with pytest.raises(ValueError):
        Capability(parse_term("rdf"), frozenset("X"))


# --------------------------------------------------------------------------- #
# covered/2 — the subject subsumption lattice
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("subject, available, expected", [
    ("cls", "resource", True),               # covered(Subj, resource) :- role(Subj).
    ("concept", "resource", True),
    ("objectProperty", "property", True),    # covered(objectProperty, property).
    ("datatypeProperty", "property", True),
    ("annotationProperty", "property", True),
    ("ontologyProperty", "property", True),
    ("skosOrderedCollection", "skosCollection", True),
    ("cls", "cls", True),                    # covered(Role, Role).
    ("property", "objectProperty", False),   # not symmetric
    ("cls", "concept", False),
    ("skosCollection", "skosOrderedCollection", False),
    ("sparql", "resource", False),           # sparql is not a role/1 fact
])
def test_covered(subject, available, expected):
    assert covered(parse_term(subject), parse_term(available)) is expected


# --------------------------------------------------------------------------- #
# resolveCRUDV — the direction of the subset test
# --------------------------------------------------------------------------- #
def test_requested_ops_must_be_subset_of_granted():
    caps = CapabilitySet.parse(['capability(rdf(cls), "CRUD")'])
    assert caps.authorize('auth(rdf(cls), "R")')
    assert caps.authorize('auth(rdf(cls), "CRUD")')
    assert not caps.authorize('auth(rdf(cls), "V")')       # V not granted
    assert not caps.authorize('auth(rdf(cls), "CRUDV")')


def test_a_read_grant_does_not_confer_write():
    """The inversion bug: if the subset test were the wrong way round, a
    ``"R"`` grant would satisfy a ``"CRUD"`` request."""
    caps = CapabilitySet.parse(['capability(rdf(cls), "R")'])
    assert caps.authorize('auth(rdf(cls), "R")')
    assert not caps.authorize('auth(rdf(cls), "C")')
    assert not caps.authorize('auth(rdf(cls), "CRUD")')


def test_multi_letter_request_needs_one_grant_carrying_all_letters():
    """(VB3) `refactorMoveXLabelToResource` asks for "CD" in a single goal."""
    split = CapabilitySet.parse([
        'capability(rdf(xLabel), "C")',
        'capability(rdf(xLabel), "D")',
    ])
    together = CapabilitySet.parse(['capability(rdf(xLabel), "CD")'])
    assert not split.authorize('auth(rdf(xLabel), "CD")')
    assert together.authorize('auth(rdf(xLabel), "CD")')


# --------------------------------------------------------------------------- #
# Wildcard grants — the easiest thing to get wrong
# --------------------------------------------------------------------------- #
def test_wildcard_grant_unifies_with_specific_goal():
    """`capability(rdf(_,_), "R")` is a *fact*; Prolog unification makes it
    satisfy any two-argument rdf goal. Forget this and the Lurker gets nothing."""
    caps = CapabilitySet.parse(['capability(rdf(_,_), "R")'])
    assert caps.authorize('auth(rdf(cls, taxonomy), "R")')
    assert caps.authorize('auth(rdf(concept, lexicalization), "R")')


def test_bare_area_grant_covers_arity_one_and_two():
    """chk_capability(rdf(_), C) :- chk_capability(rdf, C)."""
    caps = CapabilitySet.parse(['capability(rdf, "CRUD")'])
    assert caps.authorize('auth(rdf(cls), "C")')
    assert caps.authorize('auth(rdf(cls, taxonomy), "D")')


def test_rbac_and_cform_have_the_same_rollup():
    assert CapabilitySet.parse(['capability(rbac, "CRUD")']).authorize(
        'auth(rbac(user, capability), "CRUD")')
    assert CapabilitySet.parse(['capability(cform, "CRUD")']).authorize(
        'auth(cform(formCollection, form), "C")')


# --------------------------------------------------------------------------- #
# The sparql/support cut
# --------------------------------------------------------------------------- #
def test_sparql_support_is_cut_and_needs_an_exact_grant():
    """chk_capability(rdf(sparql,support), C) :- !, capability(rdf(sparql,support), C).

    The cut means a blanket rdf grant must NOT confer SPARQL-endpoint access.
    Dropping it silently widens the policy for every power role.
    """
    broad = CapabilitySet.parse([
        'capability(rdf, "CRUD")',
        'capability(rdf(_,_), "CRUD")',
        'capability(rdf(resource,_), "CRUD")',
    ])
    assert broad.authorize('auth(rdf(cls, taxonomy), "CRUD")')
    assert not broad.authorize('auth(rdf(sparql, support), "R")')

    exact = CapabilitySet.parse(['capability(rdf(sparql,support), "CRUD")'])
    assert exact.authorize('auth(rdf(sparql, support), "R")')


# --------------------------------------------------------------------------- #
# Vocabulary roll-ups
# --------------------------------------------------------------------------- #
def test_skos_blanket_grant_covers_skos_elements():
    caps = CapabilitySet.parse(['capability(rdf(skos), "CRUD")'])
    assert caps.authorize('auth(rdf(concept), "C")')
    assert caps.authorize('auth(rdf(conceptScheme, taxonomy), "U")')
    assert caps.authorize('auth(rdf(skosCollection), "D")')
    assert not caps.authorize('auth(rdf(cls), "C")')          # OWL is not SKOS
    assert not caps.authorize('auth(rdf(ontolexLexicalEntry), "C")')


def test_ontolex_blanket_grant_covers_ontolex_elements():
    caps = CapabilitySet.parse(['capability(rdf(ontolex), "CRUD")'])
    assert caps.authorize('auth(rdf(ontolexLexicalEntry), "C")')
    assert caps.authorize('auth(rdf(limeLexicon, values), "U")')
    assert not caps.authorize('auth(rdf(concept), "C")')


def test_lexicalization_grant_covers_label_bearing_subjects():
    caps = CapabilitySet.parse(['capability(rdf(lexicalization), "CRUD")'])
    assert caps.authorize('auth(rdf(xLabel), "C")')
    assert caps.authorize('auth(rdf(ontolexForm), "U")')
    assert caps.authorize('auth(rdf(concept, lexicalization), "C")')
    assert not caps.authorize('auth(rdf(cls, taxonomy), "C")')


def test_notes_rollup():
    caps = CapabilitySet.parse(['capability(rdf(notes), "CRUD")'])
    assert caps.authorize('auth(rdf(concept, notes), "C")')
    assert not caps.authorize('auth(rdf(concept, taxonomy), "C")')


# --------------------------------------------------------------------------- #
# Language coverage — resolveLANG/2
# --------------------------------------------------------------------------- #
def test_language_scoped_lexicalization_grant():
    caps = CapabilitySet.parse(['capability(rdf(lexicalization("en,fr")), "CRUD")'])
    assert caps.authorize('auth(rdf(concept, lexicalization("en")), "C")')
    assert caps.authorize('auth(rdf(concept, lexicalization("en,fr")), "U")')
    assert not caps.authorize('auth(rdf(concept, lexicalization("de")), "C")')
    assert not caps.authorize('auth(rdf(concept, lexicalization("en,de")), "C")')


def test_unrestricted_lexicalization_grant_covers_any_language():
    caps = CapabilitySet.parse(['capability(rdf(lexicalization), "CRUD")'])
    assert caps.authorize('auth(rdf(concept, lexicalization("zu")), "C")')


# --------------------------------------------------------------------------- #
# The eight default roles, against real VB3 goals
# --------------------------------------------------------------------------- #
def test_lurker_reads_everything_and_writes_nothing():
    g = role_grants("Lurker")
    assert g.authorize('auth(rdf(cls), "R")')                       # (VB3) classesRead
    assert g.authorize('auth(rdf(concept, taxonomy), "R")')         # (VB3) skosGetConceptTaxonomy
    assert not g.authorize('auth(rdf(cls), "C")')                   # (VB3) classesCreateClass
    assert not g.authorize('auth(rdf(concept), "D")')
    assert not g.authorize('auth(rdf(code), "V")')                  # (VB3) validation


def test_validator_can_validate_but_not_edit():
    g = role_grants("Validator")
    assert g.authorize('auth(rdf(code), "V")')                      # (VB3) validation
    assert g.authorize('auth(rdf(cls), "R")')
    assert not g.authorize('auth(rdf(cls), "C")')
    assert not g.authorize('auth(rdf(concept), "U")')


def test_thesaurus_editor_edits_skos_but_not_owl_axioms():
    g = role_grants("ThesaurusEditor")
    assert g.authorize('auth(rdf(concept), "C")')                   # (VB3) skosCreateConcept
    assert g.authorize('auth(rdf(concept, taxonomy), "C")')         # (VB3) skosAddBroaderConcept
    assert g.authorize('auth(rdf(conceptScheme), "C")')
    assert g.authorize('auth(rdf(xLabel), "C")')
    assert not g.authorize('auth(rdf(cls), "C")')                   # (VB3) classesCreateClass
    assert not g.authorize('auth(rdf(cls, taxonomy), "C")')         # (VB3) classesCreateClassAxiom
    assert not g.authorize('auth(rdf(code), "V")')                  # cannot validate


def test_ontology_editor_edits_owl_but_not_thesaurus_structures():
    g = role_grants("OntologyEditor")
    assert g.authorize('auth(rdf(cls), "C")')                       # (VB3) classesCreateClass
    assert g.authorize('auth(rdf(cls, taxonomy), "C")')             # (VB3) classesCreateClassAxiom
    assert g.authorize('auth(rdf(individual), "C")')                # (VB3) classesCreateIndividual
    assert g.authorize('auth(rdf(objectProperty), "C")')            # via covered/2 -> property
    assert g.authorize('auth(rdf(datatypeProperty, taxonomy), "R")')
    assert g.authorize('auth(rdf(import), "C")')                    # (VB3) metadataAddImport
    assert not g.authorize('auth(rdf(concept), "C")')
    assert not g.authorize('auth(rdf(code), "V")')


def test_mapper_only_maps():
    g = role_grants("Mapper")
    assert g.authorize('auth(rdf(resource, alignment), "CUD")')     # (VB3) alignmentApplyAlignment
    assert g.authorize('auth(rdf(concept, alignment), "C")')        # (VB3) alignmentAddAlignment
    assert g.authorize('auth(rdf(resource, alignment), "R")')       # (VB3) alignmentLoadAlignment
    assert not g.authorize('auth(rdf(cls), "C")')
    assert not g.authorize('auth(rdf(concept, taxonomy), "C")')


def test_project_manager_can_do_project_and_role_administration():
    g = role_grants("ProjectManager")
    assert g.authorize('auth(pm(project,_), "CRUD")')               # (VB3) administrationProjectManagement
    assert g.authorize('auth(pm(project, group), "CU")')            # (VB3) administrationUserGroupManagement
    assert g.authorize('auth(pm(project, collaboration), "CRUD")')  # (VB3) collaboration
    assert g.authorize('auth(rbac(user,_), "CRUD")')                # (VB3) administrationUserRoleManagement
    assert g.authorize('auth(cform(form, mapping), "C")')           # (VB3) customFormCreateFormMapping
    assert g.authorize('auth(rdf(cls), "CRUDV")')


def test_rdf_geek_has_sparql_support_and_others_do_not():
    assert role_grants("RDFGeek").authorize('auth(rdf(sparql, support), "CRUD")')
    for role in ("OntologyEditor", "ThesaurusEditor", "Lurker", "Validator"):
        assert not role_grants(role).authorize('auth(rdf(sparql, support), "R")'), role


def test_roles_compose_by_union():
    """A user bound with two roles gets the union of their grants."""
    g = role_grants("Lexicographer", "Mapper")
    assert g.authorize('auth(rdf(xLabel), "C")')
    assert g.authorize('auth(rdf(resource, alignment), "CUD")')
    assert not g.authorize('auth(rdf(cls), "C")')


# --------------------------------------------------------------------------- #
# The full decision path
# --------------------------------------------------------------------------- #
def _lexicographer(langs=()):
    return Subject("anna", grants=role_grants("Lexicographer"), languages=langs)


def test_resource_role_substitution():
    """(VB3) resourcesUpdateTripleValue is 'auth(rdf(%resource_role%, values), "U")'."""
    s = Subject("kim", grants=role_grants("ThesaurusEditor"))
    assert authorize(s, 'auth(rdf(%resource_role%, values), "U")',
                     resource_role="concept")
    assert not authorize(s, 'auth(rdf(%resource_role%, values), "U")',
                         resource_role="cls")


def test_resource_role_goal_without_a_resource_is_an_error():
    s = Subject("kim", grants=role_grants("ThesaurusEditor"))
    with pytest.raises(ValueError):
        authorize(s, 'auth(rdf(%resource_role%), "U")')


def test_language_restriction_from_the_binding():
    """The ProjectUserBinding's language list, not the role, is the enforcement point."""
    anna = _lexicographer(langs=("fr",))
    goal = 'auth(rdf(%resource_role%, lexicalization), "U")'
    assert authorize(anna, goal, resource_role="concept", value_language="fr")
    d = authorize(anna, goal, resource_role="concept", value_language="en")
    assert not d and "restricts editing" in d.reason


def test_unrestricted_binding_allows_any_language():
    anna = _lexicographer(langs=())
    assert authorize(anna, 'auth(rdf(%resource_role%, lexicalization), "U")',
                     resource_role="concept", value_language="en")


def test_read_only_project_blocks_writes_for_everyone_including_admins():
    admin = Subject("root", is_admin=True)
    assert authorize(admin, 'auth(rdf(cls), "C")')
    d = authorize(admin, 'auth(rdf(cls), "C")', project_read_only=True)
    assert not d and "read-only" in d.reason
    # …but reads and non-rdf areas still work
    assert authorize(admin, 'auth(rdf(cls), "R")', project_read_only=True)
    assert authorize(admin, 'auth(pm(project,_), "CRUD")', project_read_only=True)


def test_anonymous_is_denied():
    assert not authorize(Subject(""), 'auth(rdf(cls), "R")')


def test_admin_bypasses_the_algebra():
    assert authorize(Subject("root", is_admin=True), 'auth(rdf(sparql, support), "CRUDV")')


def test_decision_carries_a_reason():
    d = authorize(_lexicographer(), 'auth(rdf(cls), "C")')
    assert not d
    assert "no grant satisfies" in d.reason


# --------------------------------------------------------------------------- #
# The agent invariant from GOVERNANCE_FOUNDATION §5
# --------------------------------------------------------------------------- #
def test_agent_gets_editor_rights_but_never_validate():
    """An authoring agent is a machine account with editor grants minus V, so
    its output must pass through a human validator."""
    agent_grants = CapabilitySet.parse([
        g.replace('"CRUD"', '"CRU"')            # no D, no V
        for g in _THESAURUS_EDITOR_WRITE_GRANTS
    ])
    copilot = Subject("agent:copilot", grants=agent_grants, is_machine=True)
    assert authorize(copilot, 'auth(rdf(concept), "C")')
    assert authorize(copilot, 'auth(rdf(concept, lexicalization), "U")')
    assert not authorize(copilot, 'auth(rdf(code), "V")')
    assert not authorize(copilot, 'auth(rdf(concept), "D")')


_THESAURUS_EDITOR_WRITE_GRANTS = (
    'capability(rdf(skos), "CRUD")',
    'capability(rdf(concept,_), "CRUD")',
    'capability(rdf(lexicalization), "CRUD")',
)


# --------------------------------------------------------------------------- #
# Caching does not change answers
# --------------------------------------------------------------------------- #
def test_cache_is_transparent():
    g = role_grants("ThesaurusEditor")
    first = g.authorize('auth(rdf(concept), "C")')
    assert g._cache
    assert g.authorize('auth(rdf(concept), "C")') is first
