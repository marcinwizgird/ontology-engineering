/*
 * Semantic Intelligence Platform -- PERSPECTIVES (Rozanski & Woods) and the views.
 * SysML v2 textual notation.
 *
 * A perspective cuts across views. Each is modelled as a requirement group (its quality
 * requirements as sub-requirements) carrying @Perspective, plus the tactics applied, each
 * a part def carrying @Tactic and naming the functional element that realises it. The
 * seven views at the end satisfy the seven viewpoints of SipViewpoints and expose the
 * packages that render them.
 */

package SipPerspectives {

    private import ScalarValues::*;
    private import SipViewpoints::*;
    private import SipRequirements::*;
    private import SipContext::*;

    // ------------------------------------------------------------------ //
    // Perspectives as requirement groups
    // ------------------------------------------------------------------ //

    requirement def SecurityPerspective {
        @Perspective { kind = PerspectiveKind::security; }
        doc /* Principals, policies, enforcement, audit. Applied to: Functional (PDP in the
             * call path), Information (governance as RDF, history), Deployment (secrets),
             * Operational (incident response). */
        subject sip : SemanticIntelligencePlatform;
        requirement guarded : EveryOperationGuarded;
        requirement noAgentValidation : AgentsNeverValidate;
        requirement llmPolicy : LlmDataPolicy;
    }
    requirement def PerformanceScalabilityPerspective {
        @Perspective { kind = PerspectiveKind::performanceScalability; }
        subject sip : SemanticIntelligencePlatform;
        requirement latency : InteractiveLatency;
        requirement scale : CorpusScale;
    }
    requirement def AvailabilityResiliencePerspective {
        @Perspective { kind = PerspectiveKind::availabilityResilience; }
        subject sip : SemanticIntelligencePlatform;
        requirement recovery : RecoveryObjectives;
        requirement llmIndependence : LlmIndependence;
    }
    requirement def EvolutionPerspective {
        @Perspective { kind = PerspectiveKind::evolution; }
        subject sip : SemanticIntelligencePlatform;
        requirement extension : ExtensionPoints;
        requirement history : HistoryCompatibility;
    }
    requirement def InternationalisationPerspective {
        @Perspective { kind = PerspectiveKind::internationalisation; }
        subject sip : SemanticIntelligencePlatform;
        requirement multilingual : Multilinguality;
    }
    requirement def AccessibilityPerspective {
        @Perspective { kind = PerspectiveKind::accessibility; }
        subject sip : SemanticIntelligencePlatform;
        requirement ui : AccessibleUi;
    }
    requirement def RegulationPerspective {
        @Perspective { kind = PerspectiveKind::regulation; }
        subject sip : SemanticIntelligencePlatform;
        requirement transparency : AiContentTransparency;
    }
    requirement def LocationPerspective {
        @Perspective { kind = PerspectiveKind::location; }
        subject sip : SemanticIntelligencePlatform;
        requirement residency : InferenceResidency;
    }
    requirement def UsabilityPerspective {
        @Perspective { kind = PerspectiveKind::usability; }
        subject sip : SemanticIntelligencePlatform;
        requirement perspectives : RolePerspectives;
    }
    requirement def DevelopmentResourcePerspective {
        @Perspective { kind = PerspectiveKind::developmentResource; }
        subject sip : SemanticIntelligencePlatform;
        requirement python : PythonCore;
    }
    requirement def AiTrustworthinessPerspective {
        @Perspective { kind = PerspectiveKind::aiTrustworthiness; }
        doc /* The custom perspective of an agent-assisted system: bounded autonomy,
             * grounding, human oversight, measured usefulness, profile honesty. */
        subject sip : SemanticIntelligencePlatform;
        requirement grounding : Grounding;
        requirement autonomy : BoundedAutonomy;
        requirement measured : MeasuredAssistance;
        requirement honesty : ProfileHonesty;
        requirement oversight : AgentsNeverValidate;
        requirement staging : ProposalsViaStaging;
    }

    // ------------------------------------------------------------------ //
    // Tactics
    // ------------------------------------------------------------------ //

    part def DeclarativeAuthorization {
        @Tactic { perspective = PerspectiveKind::security;
                  rationale = "capability declared on every operation; unguarded = build failure"; }
        attribute realisedBy : String = "OperationRegistry";
    }
    part def MachinePrincipalsForAgents {
        @Tactic { perspective = PerspectiveKind::security;
                  rationale = "agents are principals with on_behalf_of; PDP strips V"; }
        attribute realisedBy : String = "PolicyDecisionPoint";
    }
    part def PolicyCheckBeforeModelCall {
        @Tactic { perspective = PerspectiveKind::security;
                  rationale = "AiPolicy evaluated and logged per call"; }
        attribute realisedBy : String = "AgentRuntime";
    }
    part def SingleWritePath {
        @Tactic { perspective = PerspectiveKind::availabilityResilience;
                  rationale = "content + history in one transaction; restore is consistent"; }
        attribute realisedBy : String = "ChangeTracker";
    }
    part def SingleWriterCoordinator {
        @Tactic { perspective = PerspectiveKind::performanceScalability;
                  rationale = "TDB2 single-writer designed for, not discovered"; }
        attribute realisedBy : String = "WriteCoordinator";
    }
    part def ReasoningOffWritePath {
        @Tactic { perspective = PerspectiveKind::performanceScalability;
                  rationale = "classify in memory, swap derived graph in one short transaction"; }
        attribute realisedBy : String = "ReasoningService";
    }
    part def GracefulAgentDegradation {
        @Tactic { perspective = PerspectiveKind::availabilityResilience;
                  rationale = "model failure -> run degraded, no proposals; humans continue"; }
        attribute realisedBy : String = "AgentRuntime";
    }
    part def ExtensionRegistries {
        @Tactic { perspective = PerspectiveKind::evolution;
                  rationale = "operations, ICV checks, transformers, reasoner backends, agents are registries"; }
        attribute realisedBy : String = "OperationRegistry";
    }
    part def VocabularyCompatibility {
        @Tactic { perspective = PerspectiveKind::evolution;
                  rationale = "Semantic Turkey CHANGELOG/VALIDATION terms and the nine ST roles kept verbatim"; }
        attribute realisedBy : String = "ChangeTracker";
    }
    part def DeterministicCritics {
        @Tactic { perspective = PerspectiveKind::aiTrustworthiness;
                  rationale = "verbatim-quote, Manchester, reasoner, mapping and SPARQL critics gate every proposal"; }
        attribute realisedBy : String = "SpecialistAgent";
    }
    part def StagedProposalsWithEvidence {
        @Tactic { perspective = PerspectiveKind::aiTrustworthiness;
                  rationale = "machine writes always staged; evidence on the commit"; }
        attribute realisedBy : String = "ChangeTracker";
    }
    part def ProfileLabelledResults {
        @Tactic { perspective = PerspectiveKind::aiTrustworthiness;
                  rationale = "every classification/explanation carries backend + profile"; }
        attribute realisedBy : String = "ReasoningService";
    }
    part def OfflineSimulators {
        @Tactic { perspective = PerspectiveKind::developmentResource;
                  rationale = "same schemas and critics offline; tests free and deterministic"; }
        attribute realisedBy : String = "LlmGateway";
    }

    // ------------------------------------------------------------------ //
    // Views -- one per Rozanski & Woods viewpoint
    // ------------------------------------------------------------------ //

    view def ContextView { satisfy requirement : ContextViewpoint; expose SipContext::*; }
    view def FunctionalView { satisfy requirement : FunctionalViewpoint; expose SipFunctional::*; }
    view def InformationView { satisfy requirement : InformationViewpoint; expose SipInformation::*; }
    view def ConcurrencyView { satisfy requirement : ConcurrencyViewpoint; expose SipDeployment::*; }
    view def DevelopmentView { satisfy requirement : DevelopmentViewpoint; expose SipDevelopment::*; }
    view def DeploymentView { satisfy requirement : DeploymentViewpoint; expose SipDeployment::*; }
    view def OperationalView { satisfy requirement : OperationalViewpoint; expose SipDeployment::*; }
}
