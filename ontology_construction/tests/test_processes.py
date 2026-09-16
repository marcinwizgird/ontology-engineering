"""Tests for the ontology-construction process prototypes.

Run:  python -m pytest ontology_construction -q

Everything here runs offline and deterministically — the LLM is an injected
:class:`Extractor`, and the tests that need a *specific* model behaviour use a
stub that emits exactly the output under test (including hallucinated output,
which is the point of the gate tests).
"""

from __future__ import annotations

import pytest

import ontology_construction as oc
from ontology_construction.llms4ol import HeuristicExtractor
from ontology_construction.validation import Severity

CORPUS = [
    "A mortgage is a kind of loan. A loan is issued by a bank. "
    "Loans such as mortgages and overdrafts are offered to customers. "
    "A bank owns a portfolio. A loan requires collateral."
]


# --------------------------------------------------------------------------- #
# Fixtures and stubs
# --------------------------------------------------------------------------- #
@pytest.fixture
def state() -> oc.ConstructionState:
    return oc.ConstructionState(
        domain="lending",
        documents=list(CORPUS),
        use_cases=["What kinds of loan are there? Is a mortgage a loan?"],
    )


class StubExtractor:
    """Emits exactly what a test needs — including invented content."""

    name = "stub"

    def __init__(self, terms=(), taxonomy=(), relations=()):
        self._terms = list(terms)
        self._taxonomy = list(taxonomy)
        self._relations = list(relations)

    def type_terms(self, documents):
        return [oc.CandidateTerm(label=t, type_label="Entity", score=1.0,
                                 provenance="stub") for t in self._terms]

    def discover_taxonomy(self, terms, documents):
        return [oc.TaxonomyEdge(c, p, s, "stub") for c, p, s in self._taxonomy]

    def extract_relations(self, pairs, documents):
        return [oc.RelationEdge(d, p, r, 1.0, "stub") for d, p, r in self._relations]


# =========================================================================== #
# NeOn — nine scenarios
# =========================================================================== #
def test_all_nine_neon_scenarios_are_modelled():
    assert len(oc.SCENARIOS) == 9
    assert [s.id for s in oc.SCENARIOS] == list(range(1, 10))
    assert oc.SCENARIO_BY_ID[9].name.startswith("Localizing")


def test_scenario_1_is_the_fallback_when_nothing_can_be_reused(state):
    chosen = oc.select_scenarios(state)
    assert [s.id for s in chosen] == [1], "no resources -> build from scratch"


def test_scenarios_are_selected_from_available_resources(state):
    state.non_ontological_resources = ["term: a definition"]
    state.ontological_resources = ["http://example.org/x"]
    state.design_patterns = ["p: a - r -> b"]
    state.target_languages = ["en", "pl"]
    ids = {s.id for s in oc.select_scenarios(state)}
    assert {2, 3, 7, 9} <= ids
    assert 1 in ids, "a use case still justifies specification"


def test_scenario_2_lifts_terms_and_keeps_definitions(state):
    state.non_ontological_resources = [
        "collateral: an asset pledged against a loan\ncovenant: a contractual promise"]
    oc.step_reengineer_non_ontological(state)
    labels = {t.label for t in state.candidate_terms}
    assert {"collateral", "covenant"} <= labels
    assert "asset pledged" in state.ontology.definitions["collateral"]


def test_scenario_3_records_provenance_for_reused_terms(state):
    state.ontological_resources = [
        "https://spec.edmcouncil.org/fibo/ontology#terms=LegalEntity,Loan"]
    oc.step_reuse_ontological(state)
    assert state.ontology.imports == ["https://spec.edmcouncil.org/fibo/ontology"]
    assert state.ontology.reused["Loan"].endswith("/ontology")


def test_scenario_7_expands_a_design_pattern(state):
    state.design_patterns = ["participation: bank - issues -> loan"]
    oc.step_apply_design_patterns(state)
    rels = {(r.domain, r.predicate, r.range) for r in state.ontology.object_properties}
    assert ("bank", "issues", "loan") in rels
    assert "loan" in state.ontology.classes and ">loan" not in state.ontology.classes


def test_scenario_8_prunes_classes_no_requirement_reaches(state):
    state.competency_questions = [oc.CompetencyQuestion("CQ01", "What is a loan?")]
    state.ontology.add_class("loan")
    state.ontology.add_class("unrelated widget")
    oc.step_restructure(state)
    assert "loan" in state.ontology.classes
    assert "unrelated widget" not in state.ontology.classes


def test_scenario_9_reports_localisation_gaps_rather_than_inventing_labels(state):
    state.target_languages = ["en", "pl"]
    state.ontology.add_class("loan")
    oc.step_localize(state)
    assert state.ontology.labels["loan"]["en"] == "loan"
    assert "pl" not in state.ontology.labels["loan"], "must not fabricate a translation"
    assert state.reports["localization_gaps"]["loan"] == ["pl"]


# =========================================================================== #
# LOT — four sprints
# =========================================================================== #
def test_lot_has_four_sprints():
    assert oc.SPRINTS == ("requirements", "implementation", "publication",
                          "maintenance")


def test_lot_requirements_fails_without_competency_questions(state):
    oc.step_lot_requirements(state)
    rec = state.stages[-1]
    assert not rec.ok
    assert "competency questions" in rec.detail


def test_lot_requirements_passes_once_cqs_exist(state):
    state.competency_questions = [oc.CompetencyQuestion("CQ01", "What is a loan?")]
    oc.step_lot_requirements(state)
    assert state.stages[-1].ok
    assert state.purpose and state.scope and state.intended_users


def test_chowlk_parses_a_uml_sketch():
    model = oc.parse_chowlk("""
        class Loan
        Mortgage --|> Loan
        Loan -- issued by --> Bank
        Loan.principal : xsd:decimal
    """)
    assert set(model.classes) >= {"Loan", "Mortgage", "Bank"}
    assert ("Mortgage", "Loan") in model.generalisations
    assert ("Loan", "issued by", "Bank") in model.associations
    assert ("Loan", "principal", "xsd:decimal") in model.attributes


def test_conceptual_model_overrules_a_contradicting_learned_edge(state):
    """The expert asserted Mortgage < Loan; learning proposed the reverse."""
    state.taxonomy_edges = [oc.TaxonomyEdge("Loan", "Mortgage", 0.9, "learned")]
    oc.step_lot_implementation(state, conceptual_model="Mortgage --|> Loan")
    assert ("Mortgage", "Loan") in state.ontology.subclass_of
    assert ("Loan", "Mortgage") not in state.ontology.subclass_of
    assert "overruled" in state.stages[-1].detail


def test_publication_produces_content_negotiation_and_documentation(state):
    state.ontology.add_class("loan", label="loan")
    oc.step_lot_publication(state)
    pub = state.reports["publication"]
    assert pub["dereferenceable"]
    assert set(pub["content_negotiation"]) == {
        "text/html", "text/turtle", "application/rdf+xml"}
    assert pub["license"]
    assert "## Classes" in pub["documentation"]


def test_publication_fails_on_a_non_dereferenceable_namespace(state):
    state.ontology.iri = "urn:local:onto#"
    oc.step_lot_publication(state)
    assert not state.stages[-1].ok
    assert "dereferenceable" in state.stages[-1].detail


def test_maintenance_opens_issues_and_flags_cq_regressions(state):
    state.reports["themis"] = {"coverage": 0.5, "tests": [
        {"cq": "CQ01", "passed": True}, {"cq": "CQ02", "passed": False}]}
    oc.step_lot_maintenance(state, new_requirements=["Support syndicated loans"])
    assert state.reports["issues"][0]["status"] == "open"
    assert state.reports["maintenance"]["regressed_cqs"] == ["CQ02"]
    assert not state.stages[-1].ok


# =========================================================================== #
# LLMs4OL — three subtasks
# =========================================================================== #
def test_task_a_types_terms(state):
    oc.step_term_typing(state)
    labels = {t.label for t in state.candidate_terms}
    assert "loan" in labels and "bank" in labels
    assert all(t.type_label for t in state.candidate_terms)


def test_task_a_does_not_truncate_words_mid_token(state):
    oc.step_term_typing(state)
    labels = {t.label for t in state.candidate_terms}
    assert not any(l.endswith(" ar") for l in labels), labels


def test_task_b_finds_hearst_and_head_noun_hierarchies(state):
    oc.step_term_typing(state)
    oc.step_taxonomy_discovery(state)
    pairs = {e.as_pair() for e in state.taxonomy_edges}
    assert ("mortgage", "loan") in pairs, pairs


def test_task_c_extracts_a_cued_relation(state):
    oc.step_term_typing(state)
    oc.step_relation_extraction(state)
    triples = {r.as_triple() for r in state.relation_edges}
    assert any(p == "requires" for _, p, _ in triples), triples


def test_relation_extraction_bounds_the_quadratic_blow_up(state):
    oc.step_term_typing(state)
    oc.step_relation_extraction(state, max_pairs=10)
    budget = state.reports["relation_budget"]
    assert budget["evaluated_pairs"] <= 10
    assert budget["evaluated_pairs"] < budget["theoretical_pairs"]
    assert budget["reduction"] > 0


def test_candidate_pairs_reports_truncation_rather_than_hiding_it():
    terms = [f"t{i}" for i in range(20)]
    docs = [" ".join(terms)]
    pairs, budget = oc.candidate_pairs(terms, docs, max_pairs=5)
    assert len(pairs) == 5
    assert budget["truncated"] > 0


def test_prompting_strategies_are_both_available():
    assert oc.PromptingStrategy.AXIOM_BY_AXIOM != oc.PromptingStrategy.SINGLE_SHOT
    calls: list[str] = []
    aba = oc.LLMExtractor(complete=lambda p: (calls.append(p), "NO")[1],
                          strategy=oc.PromptingStrategy.AXIOM_BY_AXIOM)
    aba.discover_taxonomy(["a", "b"], ["text"])
    assert len(calls) == 2, "AbA queries each ordered pair separately"

    calls.clear()
    single = oc.LLMExtractor(complete=lambda p: (calls.append(p), "a | b")[1],
                             strategy=oc.PromptingStrategy.SINGLE_SHOT)
    edges = single.discover_taxonomy(["a", "b"], ["text"])
    assert len(calls) == 1 and [e.as_pair() for e in edges] == [("a", "b")]


def test_llm_extractor_enforces_a_call_budget():
    ex = oc.LLMExtractor(complete=lambda p: "YES", max_calls=1)
    with pytest.raises(RuntimeError, match="budget"):
        ex.discover_taxonomy(["a", "b", "c"], ["text"])


# =========================================================================== #
# The gates — the report's central claim, made executable
# =========================================================================== #
def test_vocabulary_gate_rejects_hallucinated_endpoints(state):
    """"Structurally plausible but factually incorrect triples" must not pass."""
    stub = StubExtractor(terms=["loan", "bank"],
                         taxonomy=[("loan", "financial instrument", 0.9)])
    oc.step_term_typing(state, extractor=stub)
    oc.step_taxonomy_discovery(state, extractor=stub)
    result = oc.vocabulary_gate(state)
    assert not result.ok and result.rejected == 1
    assert not state.taxonomy_edges[0].accepted


def test_grounding_gate_rejects_relations_absent_from_the_corpus(state):
    stub = StubExtractor(terms=["loan", "bank"],
                         relations=[("loan", "orbits", "saturn")])
    oc.step_term_typing(state, extractor=stub)
    state.relation_edges = [oc.RelationEdge("loan", "orbits", "saturn", 1.0, "stub")]
    result = oc.grounding_gate(state)
    assert not result.ok and result.rejected == 1


def test_acyclicity_gate_repairs_by_dropping_the_weakest_edge(state):
    state.taxonomy_edges = [
        oc.TaxonomyEdge("a", "b", 0.9, "s"),
        oc.TaxonomyEdge("b", "c", 0.9, "s"),
        oc.TaxonomyEdge("c", "a", 0.2, "s"),      # weakest — closes the cycle
    ]
    result = oc.acyclicity_gate(state)
    assert result.rejected == 1
    dropped = [e for e in state.taxonomy_edges if not e.accepted]
    assert [e.as_pair() for e in dropped] == [("c", "a")]
    assert oc.acyclicity_gate(state).detail == "acyclic"


def test_syntax_gate_catches_an_unserialisable_draft(state):
    state.ontology.add_class("ok")
    assert oc.syntax_gate(state).ok
    state.ontology.imports.append("not a valid iri with spaces")
    assert not oc.syntax_gate(state).ok


def test_consistency_gate_blocks_critical_pitfalls(state):
    state.ontology.add_subclass("a", "b")
    state.ontology.add_subclass("b", "a")          # P06 cycle -> critical
    result = oc.consistency_gate(state)
    assert not result.ok and "P06" in result.detail


# =========================================================================== #
# NeOn-GPT pipeline
# =========================================================================== #
def test_pipeline_runs_end_to_end_and_records_every_gate(state):
    state = oc.NeOnGPTPipeline(strict=False).run(state)
    gated = [s for s in state.stages if s.gate]
    assert gated, "gates must be recorded, not merely run"
    assert state.ontology.classes
    assert state.reports["pipeline"]["stages_run"] >= 5


def test_strict_pipeline_halts_at_the_first_gate_failure(state):
    stub = StubExtractor(terms=["loan"], taxonomy=[("loan", "invented", 0.9)])
    strict = oc.NeOnGPTPipeline(extractor=stub, strict=True).run(state)
    assert strict.reports["pipeline"]["gate_failures"]
    stages_after = [s.stage for s in strict.stages]
    assert not any("formalise" in s for s in stages_after), \
        "strict mode must not continue past a failed gate"


def test_non_strict_pipeline_collects_every_failure(state):
    stub = StubExtractor(terms=["loan"], taxonomy=[("loan", "invented", 0.9)])
    loose = oc.NeOnGPTPipeline(extractor=stub, strict=False).run(state)
    assert loose.reports["pipeline"]["stages_run"] > 5


# =========================================================================== #
# OOPS! — pitfall scanning
# =========================================================================== #
def test_p03_is_relation_is_critical(state):
    state.ontology.add_class("mortgage")
    state.ontology.add_class("loan")
    state.ontology.object_properties.append(
        oc.RelationEdge("mortgage", "is", "loan", 1.0, "x"))
    report = oc.scan_pitfalls(state.ontology)
    p03 = [p for p in report.pitfalls if p.code == "P03"]
    assert p03 and p03[0].severity == Severity.CRITICAL
    assert report.blocks_release


def test_p06_cycles_are_critical(state):
    state.ontology.add_subclass("a", "b")
    state.ontology.add_subclass("b", "a")
    report = oc.scan_pitfalls(state.ontology)
    assert any(p.code == "P06" and p.severity == Severity.CRITICAL
               for p in report.pitfalls)


def test_p19_multiple_domains_detected(state):
    state.ontology.object_properties += [
        oc.RelationEdge("loan", "issuedBy", "bank", 1.0, "x"),
        oc.RelationEdge("bond", "issuedBy", "bank", 1.0, "x"),
    ]
    assert any(p.code == "P19" for p in oc.scan_pitfalls(state.ontology).pitfalls)


def test_p04_unconnected_and_p41_no_licence(state):
    state.ontology.add_class("floating")
    codes = {p.code for p in oc.scan_pitfalls(state.ontology).pitfalls}
    assert {"P04", "P41"} <= codes


def test_a_clean_ontology_does_not_block_release(state):
    o = state.ontology
    o.license = "CC-BY-4.0"
    o.add_class("loan", label="loan", definition="a sum lent at interest")
    o.add_class("mortgage", label="mortgage", definition="a loan secured on property")
    o.add_subclass("mortgage", "loan")
    report = oc.scan_pitfalls(o)
    assert report.critical == 0 and not report.blocks_release


# =========================================================================== #
# Themis — competency-question testing
# =========================================================================== #
def test_cq_is_classified_by_lexico_syntactic_pattern():
    cq = oc.CompetencyQuestion("CQ01", "Is a mortgage a loan?")
    test = oc.formalise_cq(cq)
    assert test.pattern == "subsumption"
    assert cq.is_formalised


def test_an_unformalisable_cq_is_reported_not_silently_passed():
    cq = oc.CompetencyQuestion("CQ01", "Please make the ontology good.")
    test = oc.formalise_cq(cq)
    assert test.pattern == "unmatched" and not test.passed


def test_themis_fails_when_the_ontology_cannot_answer(state):
    state.competency_questions = [
        oc.CompetencyQuestion("CQ01", "Is a mortgage a loan?")]
    state.ontology.add_class("mortgage")
    state.ontology.add_class("loan")           # no subsumption asserted
    report = oc.run_themis(state)
    assert report.failed == 1
    assert "no subsumption path" in report.tests[0].detail


def test_themis_passes_once_the_axiom_exists(state):
    state.competency_questions = [
        oc.CompetencyQuestion("CQ01", "Is a mortgage a loan?")]
    state.ontology.add_subclass("mortgage", "loan")
    report = oc.run_themis(state)
    assert report.passed == 1 and report.coverage == 1.0


def test_themis_follows_a_transitive_subsumption_chain(state):
    state.competency_questions = [
        oc.CompetencyQuestion("CQ01", "Is a mortgage a financial instrument?")]
    state.ontology.add_subclass("mortgage", "loan")
    state.ontology.add_subclass("loan", "financial instrument")
    assert oc.run_themis(state).passed == 1


# =========================================================================== #
# CWA vs OWA
# =========================================================================== #
def test_shape_validation_rejects_a_missing_required_property():
    shapes = [oc.Shape("Loan", required_properties=("principal",))]
    violations = oc.validate_shapes([{"id": "L1", "type": "Loan"}], shapes)
    assert len(violations) == 1 and violations[0].constraint == "sh:minCount"


def test_shape_validation_checks_datatypes():
    shapes = [oc.Shape("Loan", ("principal",), {"principal": "xsd:decimal"})]
    ok = oc.validate_shapes([{"id": "L1", "type": "Loan", "principal": 10.0}], shapes)
    bad = oc.validate_shapes([{"id": "L2", "type": "Loan", "principal": "ten"}], shapes)
    assert not ok and len(bad) == 1 and bad[0].constraint == "sh:datatype"


def test_owa_and_cwa_diverge_on_the_same_data():
    """The report's core architectural point, demonstrated on one dataset."""
    shapes = [oc.Shape("Loan", required_properties=("principal",))]
    result = oc.compare_owa_cwa([{"id": "L1", "type": "Loan"}], shapes)
    assert result["owa_rejections"] == 0, "OWL treats the gap as unknown, not false"
    assert result["cwa_rejections"] == 1, "SHACL rejects it"
    assert result["gatekeeper"] == "SHACL/CWA"


# =========================================================================== #
# Metrics
# =========================================================================== #
def test_prf_arithmetic():
    prf = oc.axiom_prf("subclass", {("a", "b"), ("c", "d")}, {("a", "b"), ("e", "f")})
    assert prf.precision == 0.5 and prf.recall == 0.5 and prf.f1 == 0.5
    assert prf.support == 2


def test_scorecard_surfaces_the_weakest_axiom_type():
    """A strong subclass score must not hide a collapsed disjointness score."""
    gold = oc.OntologyDraft()
    gold.classes = {"a", "b"}
    gold.subclass_of = {("a", "b")}
    gold.disjointness = {("a", "c")}

    draft = oc.OntologyDraft()
    draft.classes = {"a", "b"}
    draft.subclass_of = {("a", "b")}          # perfect
    draft.disjointness = set()                # missed entirely

    card = oc.score_axioms(draft, gold)
    d = card.as_dict()
    assert d["weakest_axiom_type"] == "disjointness"
    assert d["weakest_f1"] == 0.0
    assert card.macro_f1 < 1.0


def test_semantic_internal_cohesion_is_higher_for_a_coherent_cluster():
    coherent = oc.semantic_internal_cohesion(["mortgage loan", "mortgage lending",
                                              "mortgage loans"])
    incoherent = oc.semantic_internal_cohesion(["mortgage", "photosynthesis",
                                                "quaternion"])
    assert coherent > incoherent


def test_cohesion_of_a_singleton_is_zero_not_one():
    assert oc.semantic_internal_cohesion(["only"]) == 0.0


def test_structural_metrics_name_the_shape_of_the_model():
    draft = oc.OntologyDraft()
    for c in "abcdefghij":
        draft.add_class(c)
    draft.add_subclass("a", "b")
    metrics = oc.structural_metrics(draft)
    assert metrics.relations == 0
    assert metrics.verdict.startswith("purely taxonomic")
    assert metrics.orphan_classes == 8


def test_criteria_scorecard_carries_evidence(state):
    state.competency_questions = [oc.CompetencyQuestion("CQ01", "What is a loan?")]
    state.ontology.add_class("loan", label="loan", definition="a sum lent")
    oc.step_run_themis(state)
    oc.step_scan_pitfalls(state)
    card = oc.criteria_scorecard(state)
    assert set(card.scores) == {"completeness", "conciseness", "consistency",
                                "correctness", "clarity"}
    assert all(card.evidence[k] for k in card.scores)
    assert 0.0 <= card.overall <= 1.0


def test_conciseness_penalises_a_redundant_subclass_axiom():
    draft = oc.OntologyDraft()
    draft.add_subclass("a", "b")
    draft.add_subclass("b", "c")
    lean = oc.ConstructionState(ontology=draft)
    score_lean = oc.criteria_scorecard(lean).scores["conciseness"]

    draft2 = oc.OntologyDraft()
    draft2.add_subclass("a", "b")
    draft2.add_subclass("b", "c")
    draft2.add_subclass("a", "c")          # implied by transitivity
    redundant = oc.ConstructionState(ontology=draft2)
    assert oc.criteria_scorecard(redundant).scores["conciseness"] < score_lean


# =========================================================================== #
# CI/CD drift gate
# =========================================================================== #
def test_drift_gate_runs_the_four_stages_in_order(state):
    state.competency_questions = [
        oc.CompetencyQuestion("CQ01", "Is a mortgage a loan?")]
    state.ontology.add_subclass("mortgage", "loan")
    state.ontology.license = "CC-BY-4.0"
    report = oc.DriftGate(fail_fast=False).run(state)
    names = [n for n, _, _ in report.stages]
    assert names == ["1. syntax check", "2. structural scan (OOPS!)",
                     "3. functional testing (Themis)", "4. data validation (SHACL)"]


def test_drift_gate_fails_fast_on_a_critical_pitfall(state):
    state.ontology.add_subclass("a", "b")
    state.ontology.add_subclass("b", "a")           # P06
    report = oc.DriftGate(fail_fast=True).run(state)
    assert not report.passed
    assert report.first_failure[0] == "2. structural scan (OOPS!)"
    assert len(report.stages) == 2, "must stop rather than run Themis"


def test_drift_gate_catches_a_cq_regression(state):
    state.competency_questions = [
        oc.CompetencyQuestion("CQ01", "Is a mortgage a loan?")]
    state.ontology.add_class("mortgage")
    state.ontology.add_class("loan")                # axiom removed -> drift
    state.ontology.license = "CC-BY-4.0"
    report = oc.DriftGate(fail_fast=True).run(state)
    assert not report.passed
    assert report.first_failure[0] == "3. functional testing (Themis)"


# =========================================================================== #
# Workflow graphs and agent tools
# =========================================================================== #
@pytest.mark.parametrize("process", ["neon", "lot", "llms4ol", "hybrid", "validation"])
def test_every_process_builds_a_runnable_dag(process, state):
    import networkx as nx
    graph = oc.configure_workflow(process=process)
    assert nx.is_directed_acyclic_graph(graph)
    assert graph.number_of_nodes() >= 4
    assert oc.describe(graph).startswith(graph.graph["name"])


def test_steps_are_networkx_nodes_and_hashable_by_id():
    graph = oc.build_lot_workflow()
    node = next(iter(graph.nodes))
    assert isinstance(node, oc.ProcessStep)
    assert hash(node) == hash(node.step_id)


def test_optional_steps_can_be_added_and_removed():
    graph = oc.build_lot_workflow(include_maintenance=False)
    assert not any(n.step_id == "lot.maintenance" for n in graph.nodes)
    grown = oc.add_optional_step(graph, "lot.maintenance", after="lot.publication")
    assert any(n.step_id == "lot.maintenance" for n in grown.nodes)
    shrunk = oc.remove_optional_step(grown, "lot.maintenance")
    assert not any(n.step_id == "lot.maintenance" for n in shrunk.nodes)


def test_mandatory_steps_cannot_be_removed():
    graph = oc.build_lot_workflow()
    with pytest.raises(ValueError, match="mandatory"):
        oc.remove_optional_step(graph, "lot.implementation")


def test_running_a_workflow_produces_a_valid_ontology(state):
    state = oc.run_workflow(oc.build_hybrid_workflow(), state)
    assert state.failed_stages == []
    graph = state.ontology.to_rdflib()
    assert len(graph) > 10


def test_tool_specs_cover_every_step():
    specs = oc.tool_specs()
    assert len(specs) == len(oc.ALL_STEPS)
    assert all("name" in s and "input_schema" in s for s in specs)
    gated = [s for s in specs if "deterministic gates" in s["description"]]
    assert gated, "gates must be advertised to the agent"


def test_tool_registry_drives_steps_in_an_agent_chosen_order(state):
    reg = oc.ToolRegistry(state=state)
    reg.invoke("llms4ol_term_typing")
    reg.invoke("llms4ol.taxonomy_discovery")
    reg.invoke("lot.implementation")
    assert reg.state.ontology.classes
    assert [c[0] for c in reg.calls][:2] == ["llms4ol.term_typing",
                                             "llms4ol.taxonomy_discovery"]
    assert "lot.implementation" in reg.transcript()


def test_unknown_tool_name_raises():
    with pytest.raises(KeyError, match="unknown tool"):
        oc.ToolRegistry().invoke("does.not.exist")


def test_case_variants_are_collapsed_onto_the_expert_naming(state):
    """The expert wrote `Loan`; an ODP and the learner produced `loan`.

    Keeping both manufactures OOPS! P02 and P19 out of nothing, so the merge
    collapses them onto the name a human chose.
    """
    state.ontology.add_class("loan")                     # e.g. from an ODP
    state.taxonomy_edges = [oc.TaxonomyEdge("mortgage", "loan", 0.9, "learned")]
    state.candidate_terms = [oc.CandidateTerm("mortgage"), oc.CandidateTerm("loan")]
    oc.step_lot_implementation(state, conceptual_model="class Loan")
    assert "Loan" in state.ontology.classes
    assert "loan" not in state.ontology.classes
    assert ("Mortgage", "Loan") not in state.ontology.subclass_of  # learner casing kept
    assert ("mortgage", "Loan") in state.ontology.subclass_of


def test_case_collapse_is_deterministic_across_runs():
    """`OntologyDraft.classes` is a set; the canonical name must not depend on
    its iteration order."""
    results = set()
    for _ in range(8):
        st = oc.ConstructionState(documents=CORPUS)
        st.ontology.add_class("loan")
        st.candidate_terms = [oc.CandidateTerm("loan")]
        oc.step_lot_implementation(st, conceptual_model="class Loan")
        results.add(tuple(sorted(st.ontology.classes)))
    assert len(results) == 1, f"non-deterministic canonicalisation: {results}"


def test_case_collapse_removes_the_duplicate_domain_pitfall(state):
    state.ontology.add_class("loan")
    state.ontology.object_properties.append(
        oc.RelationEdge("loan", "requires", "collateral", 1.0, "odp"))
    state.candidate_terms = [oc.CandidateTerm("loan"), oc.CandidateTerm("collateral")]
    state.relation_edges = [
        oc.RelationEdge("loan", "requires", "collateral", 0.8, "learned")]
    oc.step_lot_implementation(
        state, conceptual_model="Loan -- requires --> Collateral")
    codes = {p.code for p in oc.scan_pitfalls(state.ontology).pitfalls}
    assert "P19" not in codes, "case variants must not present as multiple domains"


def test_hearst_recovers_every_hyponym_in_a_such_as_list(state):
    """`Loans such as mortgages and overdrafts are offered to customers.`

    The pattern cannot know where the noun phrase ends, so the second hyponym
    used to be lost to the trailing clause.
    """
    oc.step_term_typing(state)
    oc.step_taxonomy_discovery(state)
    pairs = {e.as_pair() for e in state.accepted_taxonomy()}
    assert ("mortgage", "loan") in pairs
    assert ("overdraft", "loan") in pairs, pairs


def test_stemmer_does_not_manufacture_non_words():
    from ontology_construction.llms4ol import _singular
    assert _singular("causes") == "cause"      # not "caus"
    assert _singular("classes") == "class"
    assert _singular("boxes") == "box"
    assert _singular("policies") == "policy"
