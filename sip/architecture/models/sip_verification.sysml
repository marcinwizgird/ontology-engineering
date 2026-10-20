/*
 * Semantic Intelligence Platform -- verification.
 * SysML v2 textual notation.
 *
 * Each verification def names the executable test(s) in
 * sip/semantic_intelligence/tests that discharge it
 * (attribute `test`). tools/sysml_check.py checks that every requirement is verified and
 * that every named test exists in the test-suite.
 */

package SipVerification {

    private import ScalarValues::*;
    private import SipRequirements::*;
    private import SipContext::*;

    verification def <'V-01'> VerifyStagingAndValidation {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_accept_and_reject test_core_governance.py::test_machine_writes_are_always_staged test_platform_agents.py::test_machine_proposals_need_a_human_validator";
        objective {
            verify requirement : ValidationWorkflow;
            verify requirement : ProposalsViaStaging;
            verify requirement : AgentsNeverValidate;
        }
    }
    verification def <'V-02'> VerifyChangeTracking {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_effective_delta_and_noop test_core_governance.py::test_history_uses_semantic_turkey_changelog test_platform_agents.py::test_sparql_update_goes_through_history";
        objective {
            verify requirement : CompleteChangeTracking;
            verify requirement : HistoryCompatibility;
            verify requirement : HistoryQuery;
        }
    }
    verification def <'V-03'> VerifyUndoRedo {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_undo_redo_are_commits";
        objective { verify requirement : UndoRedo; }
    }
    verification def <'V-04'> VerifyAuthorization {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_semantic_turkey_role_matrix test_core_governance.py::test_pdp_rules test_core_governance.py::test_pdp_read_only_and_acl test_platform_agents.py::test_every_operation_is_guarded_and_staged";
        objective {
            verify requirement : CapabilityAuthorization;
            verify requirement : EveryOperationGuarded;
            verify requirement : Multilinguality;
        }
    }
    verification def <'V-05'> VerifyGovernance {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_machine_needs_on_behalf_of test_core_governance.py::test_settings_scope_merge test_platform_agents.py::test_enable_agents_requires_rbac";
        objective {
            verify requirement : Projects;
            verify requirement : MachinePrincipals;
        }
    }
    verification def <'V-06'> VerifyAxiomsAndManchester {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_owl.py::test_axiom_view_reads_restrictions test_owl.py::test_axiom_removal_is_exact test_owl.py::test_manchester_roundtrip test_owl.py::test_manchester_errors_carry_expected_sets test_owl.py::test_manchester_completion test_platform_agents.py::test_authoring_flow_and_validator_roles";
        objective {
            verify requirement : AxiomLevelEditing;
            verify requirement : ManchesterSyntax;
        }
    }
    verification def <'V-07'> VerifyEntityCreation {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_core_governance.py::test_template_uri_generator test_core_governance.py::test_entity_creation_preferences";
        objective { verify requirement : EntityCreation; }
    }
    verification def <'V-08'> VerifyBrowsing {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_owl.py::test_class_hierarchy_uses_equivalent_conjuncts test_owl.py::test_class_frame_sections test_owl.py::test_resource_view_scopes test_owl.py::test_rendering_language_and_quoting test_platform_agents.py::test_workbench_and_its_endpoints";
        objective {
            verify requirement : Hierarchies;
            verify requirement : DescriptionFrames;
            verify requirement : RolePerspectives;
        }
    }
    verification def <'V-09'> VerifyRefactoring {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_owl.py::test_rename_merge_delete test_owl.py::test_convert_defined_primitive_closure_siblings test_owl.py::test_render_axiom";
        objective {
            verify requirement : Refactoring;
            verify requirement : UsageAndMetrics;
        }
    }
    verification def <'V-10'> VerifyReasoning {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_owl.py::test_reasoner_status_and_unsat test_owl.py::test_justifications";
        objective {
            verify requirement : ReasonerManagement;
            verify requirement : InferenceResults;
            verify requirement : Explanation;
            verify requirement : ProfileHonesty;
            verify requirement : PythonCore;
        }
    }
    verification def <'V-11'> VerifySkos {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vocbench.py::test_top_concepts_are_declared_with_scheme test_vocbench.py::test_create_concept_and_label_rules test_vocbench.py::test_skosxl_conversion_roundtrip";
        objective {
            verify requirement : SkosManagement;
            verify requirement : SkosXlLabels;
        }
    }
    verification def <'V-12'> VerifyQuality {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vocbench.py::test_icv_checks_and_fixes test_platform_agents.py::test_end_to_end_demo test_platform_agents.py::test_quality_agent_explains_and_repairs_unsatisfiable_class test_platform_agents.py::test_thesaurus_project_and_per_fix_capabilities";
        objective {
            verify requirement : IntegrityChecks;
            verify requirement : ReleaseGate;
            verify requirement : CompetencyQuestionTests;
        }
    }
    verification def <'V-13'> VerifySearchAlignmentIo {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vocbench.py::test_search_modes test_vocbench.py::test_alignment_relation_table_and_apply test_vocbench.py::test_lexical_matcher test_vocbench.py::test_transformers_and_export";
        objective {
            verify requirement : Search;
            verify requirement : Alignment;
            verify requirement : Publication;
            verify requirement : ExtensionPoints;
        }
    }
    verification def <'V-14'> VerifyKgConstruction {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vocbench.py::test_tabular_lifting_and_resolution test_platform_agents.py::test_end_to_end_demo";
        objective {
            verify requirement : SourceIngestion;
            verify requirement : TabularLifting;
            verify requirement : EntityResolution;
            verify requirement : CorpusScale;
        }
    }
    verification def <'V-15'> VerifyAgents {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_platform_agents.py::test_critic_rejects_ungrounded_extraction test_platform_agents.py::test_modeling_critic_rejects_unsatisfiable_proposal test_platform_agents.py::test_ai_policy_degrades_and_kill_switch test_platform_agents.py::test_end_to_end_demo";
        objective {
            verify requirement : GroundedExtraction;
            verify requirement : Grounding;
            verify requirement : BoundedAutonomy;
            verify requirement : LlmDataPolicy;
            verify requirement : LlmIndependence;
            verify requirement : StageAssistance;
            verify requirement : ReviewAssistance;
            verify requirement : MeasuredAssistance;
            verify requirement : AiContentTransparency;
        }
    }
    verification def <'V-16'> VerifyLifecycle {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_platform_agents.py::test_end_to_end_demo test_platform_agents.py::test_machine_proposals_need_a_human_validator";
        objective { verify requirement : LifecycleOrchestration; }
    }
    verification def <'V-17'> VerifyArchitectureRules {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_architecture.py::test_layering test_architecture.py::test_single_write_path test_architecture.py::test_models_check";
        objective { verify requirement : EveryOperationGuarded; }
    }
    verification def <'V-19'> VerifyScope {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_scope.py::test_specification_fields_replace_and_are_guarded test_scope.py::test_exit_criteria test_scope.py::test_reuse_candidates_are_void_datasets test_scope.py::test_cq_priority_and_release_gate test_scope.py::test_export_is_a_neon_orsd test_scope.py::test_project_templates_seed_the_scope_stage test_scope.py::test_requirements_agent_builds_a_grounded_orsd test_scope.py::test_requirements_critic_rejects_ungrounded_items";
        objective {
            verify requirement : RequirementsSpecification;
            verify requirement : ReuseCandidates;
            verify requirement : ScopeExitCriteria;
            verify requirement : ProjectTemplates;
            verify requirement : CompetencyQuestionTests;
            verify requirement : ReleaseGate;
        }
    }
    verification def <'V-20'> VerifyValidateSemantics {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_validate_semantics.py::test_cq_discrimination_finds_tests_that_cannot_fail test_validate_semantics.py::test_release_gate_warns_about_a_must_cq_that_tests_nothing test_validate_semantics.py::test_verbalisation_and_seeded_mutants test_validate_semantics.py::test_calibration_scores_a_verifier test_validate_semantics.py::test_semantic_critic_flags_a_wrong_axiom_with_measured_precision test_validate_semantics.py::test_semantic_critic_hides_which_statements_are_mutants test_validate_semantics.py::test_semantic_critic_degrades_without_model_permission test_validate_semantics.py::test_validate_stage_reports_cq_checks_and_semantic_verdicts";
        objective {
            verify requirement : DiscriminatingCompetencyQuestions;
            verify requirement : SemanticAxiomVerification;
        }
    }
    verification def <'V-21'> VerifyVirtualKnowledgeGraph {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vkg.py::test_register_and_introspect test_vkg.py::test_non_select_sql_is_rejected test_vkg.py::test_suggest_tables_fks_and_subclass_tables test_vkg.py::test_add_remove_commit_stage_and_undo test_vkg.py::test_only_mapping_capable_roles_edit_maps test_vkg.py::test_export_import_roundtrip test_vkg.py::test_validate_catches_mapping_errors test_vkg.py::test_impact_and_rename_keep_mappings_consistent test_vkg.py::test_r2rml_model_roundtrip_and_file_sources";
        objective { verify requirement : R2rmlMappingAuthoring; }
    }
    verification def <'V-22'> VerifyVirtualGraphQuery {
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "test_vkg.py::test_query_data_follows_ontology_edits test_vkg.py::test_preview_with_provenance";
        objective { verify requirement : VirtualGraphQuery; }
    }
    verification def <'V-18'> VerifyDeploymentBench {
        doc /* Not executable in this repository: measured on the GKE environment. Recorded so
             * the gap is visible rather than implied away. */
        subject sip : SemanticIntelligencePlatform;
        attribute test : String = "manual:bench-edit-latency-1M manual:restore-drill manual:wcag-audit manual:region-config";
        objective {
            verify requirement : InteractiveLatency;
            verify requirement : RecoveryObjectives;
            verify requirement : AccessibleUi;
            verify requirement : InferenceResidency;
        }
    }
}
