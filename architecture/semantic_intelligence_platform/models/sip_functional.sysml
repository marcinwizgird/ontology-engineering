/*
 * Semantic Intelligence Platform -- FUNCTIONAL VIEWPOINT.
 * SysML v2 textual notation.
 *
 * Functional elements, one per Python package of src/Semantic Intelligence Platform/
 * semantic_intelligence, each with the @Provenance of the Protege / VocBench behaviour it
 * re-implements. Two structural guarantees are encoded as connections, not prose:
 *
 *   1. Only the ChangeTracker is connected to the QuadStore's write port. Every other
 *      element reads; nobody else can write (FR-CHG-01, "one write path").
 *   2. Agents are connected to the OperationRegistry and the LlmGateway -- and to nothing
 *      else. An agent cannot reach the tracker, the store or the PDP except as a caller
 *      of a guarded operation (QR-SEC-02, QR-AIT-02).
 */

package SipFunctional {

    private import ScalarValues::*;
    private import SipViewpoints::*;
    private import SipContext::*;
    private import SipRequirements::*;

    // ------------------------------------------------------------------ //
    // Ports and interfaces between functional elements
    // ------------------------------------------------------------------ //

    port def OperationCallPort {
        doc /* call(principal, project, operation, **kwargs) -> result | Commit */
        attribute operation : String;
    }
    port def AuthorizePort {
        doc /* authorize(principal, project, capability, crudv, languages) -> Decision */
        attribute capability : String;
        attribute crudv : String;
    }
    port def CommitPort {
        doc /* commit(ChangeSet, principal) -> Commit; accept/reject/undo/redo */
        attribute operation : String;
    }
    port def QuadWritePort {
        doc /* apply(additions, removals): the ONLY write method of the store */
    }
    port def QuadReadPort {
        doc /* graph(iri), graphs(), contains(quad), query(sparql) -- read-only views */
    }
    port def ModelCallPort {
        doc /* complete_json(task, system, prompt, schema) -> JSON object */
        attribute task : String;
    }
    port def EventPort {
        doc /* publish/subscribe: CHANGES_COMMITTED, CHANGES_STAGED, ONTOLOGY_CLASSIFIED ... */
    }

    interface def OperationCall { end client : ~OperationCallPort; end server : OperationCallPort; }
    interface def Authorization { end client : ~AuthorizePort; end server : AuthorizePort; }
    interface def CommitInterface { end client : ~CommitPort; end server : CommitPort; }
    interface def QuadWrite { end writer : ~QuadWritePort; end store : QuadWritePort; }
    interface def QuadRead { end reader : ~QuadReadPort; end store : QuadReadPort; }
    interface def ModelCall { end agent : ~ModelCallPort; end gateway : ModelCallPort; }

    // ------------------------------------------------------------------ //
    // Functional elements
    // ------------------------------------------------------------------ //

    part def ApiEdge {
        doc /* FastAPI: one route per operation, discovery, agent endpoints (api/app.py). */
        port inbound : OperationApiPort;
        port out : ~OperationCallPort;
    }
    part def OperationRegistry {
        doc /* The typed operation surface (platform.py): 66 operations, each declaring
             * capability, CRUDV, lifecycle stage and write flag -- Semantic Turkey's
             * @PreAuthorize made data. call() authorises, runs, and commits change sets. */
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "@STServiceOperation + @PreAuthorize"; }
        port calls : OperationCallPort;
        port pdp : ~AuthorizePort;
        port commits : ~CommitPort;
        port reads : ~QuadReadPort;
    }
    part def PolicyDecisionPoint {
        doc /* STAuthorizationEvaluator.isAuthorized port + CRUDV algebra (no Prolog):
             * ACL, read-only, admin, machine-V strip, roles, languages, graph check. */
        @Provenance { sourceTool = "SemanticTurkey+VocBench3"; sourceArtefact = "STAuthorizationEvaluator; AuthorizationEvaluator.ts; roles/*.pl"; }
        port decide : AuthorizePort;
    }
    part def GovernanceRegistry {
        doc /* Principals (users, machines), projects, ACLs, bindings, groups, scoped
             * settings (sys/proj/usr/pu/pg), URI generators, AI policy. */
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "ProjectManager; UsersManager; STPropertiesManager; NativeTemplateBasedURIGenerator"; }
    }
    part def ChangeTracker {
        doc /* The one write path (core/changes.py): effective delta, CHANGELOG commits,
             * staging graphs, accept/reject with conflict detection, per-principal
             * undo/redo as commits, derived-graph replacement. */
        @Provenance { sourceTool = "SemanticTurkey+Protege"; sourceArtefact = "ChangeTrackerConnection; HistoryManagerImpl"; }
        port commits : CommitPort;
        port write : ~QuadWritePort;
        port events : EventPort;
    }
    part def QuadStore {
        doc /* InMemoryStore (rdflib Dataset) | FusekiStore (SPARQL Update + GSP). */
        port write : QuadWritePort;
        port read : QuadReadPort;
        port fuseki : ~GraphStorePort;
    }
    part def OwlAuthoring {
        doc /* OWL 2 axiom view over RDF, Manchester parse/render/complete, entity
             * rendering and finding, hierarchy providers, frames, refactorings. */
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLModelManager; ManchesterOWLSyntaxParser; AssertedClassHierarchyProvider; OWLClassDescriptionFrame; OWLEntityRenamer"; }
        port reads : ~QuadReadPort;
    }
    part def VocabularyManager {
        doc /* SKOS + SKOS-XL services: trees, schemes, collections, label rules, conversions. */
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "SVC/SKOS.java; SVC/SKOSXL.java; Refactor"; }
        port reads : ~QuadReadPort;
    }
    part def ReasoningService {
        doc /* ReasonerManager (derived status, pluggable profiles: RDFS, OWL2-RL, OWL2-DL via
             * optional JVM), inferred hierarchy, unsatisfiable classes, black-box
             * justifications (expand-contract + Reiter HST). */
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLReasonerManagerImpl; ExplanationManager; owlexplanation"; }
        port reads : ~QuadReadPort;
    }
    part def QualityService {
        doc /* ICV (23 of the 27 ST checks, 6 of the 11 fixes) + 5 logical checks, metrics (43), CQ tests, release gate. */
        @Provenance { sourceTool = "SemanticTurkey+Protege+new"; sourceArtefact = "SVC/ICV.java; MetricsPanel; CQ suite"; }
        port reads : ~QuadReadPort;
    }
    part def SearchService {
        @Provenance { sourceTool = "SemanticTurkey+Protege"; sourceArtefact = "Search.searchResource; OWLEntityFinder"; }
        port reads : ~QuadReadPort;
    }
    part def AlignmentService {
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "SVC/Alignment.java; AlignmentUtils; MAPLE"; }
        port reads : ~QuadReadPort;
    }
    part def IoPipeline {
        doc /* lifters, 8 transformers, exporters (ST loader->lifter->transformer->exporter). */
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "InputOutput; Export; rdf-transformers"; }
    }
    part def KgConstruction {
        doc /* tabular lifting (Sheet2RDF role), entity resolution, LPG projection. */
        @Provenance { sourceTool = "SemanticTurkey+new"; sourceArtefact = "Sheet2RDF/CODA"; }
        port lpg : ~PropertyGraphPort;
    }
    part def EventBus {
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLModelManagerListener; EventType"; }
        port bus : ~EventPort;
    }

    // -- the agent layer -------------------------------------------------- //

    part def LlmGateway {
        doc /* ClaudeModel (structured outputs, adaptive thinking, caching, fallback) or
             * SimulatedModel (offline, deterministic). */
        port serve : ModelCallPort;
        port provider : ~LlmPort;
    }
    abstract part def SpecialistAgent {
        doc /* plan -> propose (model, JSON schema) -> criticise (deterministic) -> submit
             * (guarded operation, staged, with evidence). A machine principal. */
        attribute stage : String;
        attribute roles : String[1..*];
        port tools : ~OperationCallPort;
        port model : ~ModelCallPort;
    }
    part def RequirementsAgent :> SpecialistAgent { doc /* scope: CQs + SPARQL tests */ }
    part def ExtractionAgent :> SpecialistAgent { doc /* acquire: grounded candidates */ }
    part def ModelingCopilot :> SpecialistAgent { doc /* model: Manchester axioms, reasoner critic */ }
    part def VocabularyAgent :> SpecialistAgent { doc /* model: missing labels */ }
    part def AlignmentAgent :> SpecialistAgent { doc /* model: correspondences */ }
    part def QualityAgent :> SpecialistAgent { doc /* validate: fixes, repairs */ }
    part def StewardAgent :> SpecialistAgent { doc /* review: summaries, never decides */ }
    part def KnowledgeGraphBuilder :> SpecialistAgent { doc /* populate: mapping, lifting, sameAs */ }
    part def AssistantAgent :> SpecialistAgent { doc /* consume: grounded Q&A */ }

    part def AgentRuntime {
        doc /* runs, budgets, kill switch, AI-policy log, per-agent metrics. */
    }
    part def LifecycleConductor {
        doc /* drives scope..consume, stops at the human gates review and publish. */
        port tools : ~OperationCallPort;
    }

    // ------------------------------------------------------------------ //
    // White box
    // ------------------------------------------------------------------ //

    part def SipSystem :> SemanticIntelligencePlatform {
        part edge : ApiEdge;
        part registry : OperationRegistry;
        part pdp : PolicyDecisionPoint;
        part governance : GovernanceRegistry;
        part tracker : ChangeTracker;
        part store : QuadStore;
        part authoring : OwlAuthoring;
        part vocabulary : VocabularyManager;
        part reasoning : ReasoningService;
        part quality : QualityService;
        part search : SearchService;
        part alignment : AlignmentService;
        part io : IoPipeline;
        part kg : KgConstruction;
        part events : EventBus;
        part gateway : LlmGateway;
        part runtime : AgentRuntime;
        part conductor : LifecycleConductor;
        part requirementsAgent : RequirementsAgent;
        part extractionAgent : ExtractionAgent;
        part modelingCopilot : ModelingCopilot;
        part vocabularyAgent : VocabularyAgent;
        part alignmentAgent : AlignmentAgent;
        part qualityAgent : QualityAgent;
        part stewardAgent : StewardAgent;
        part kgBuilder : KnowledgeGraphBuilder;
        part assistant : AssistantAgent;

        interface edgeToRegistry : OperationCall connect edge.out to registry.calls;
        interface authz : Authorization connect registry.pdp to pdp.decide;
        interface commit : CommitInterface connect registry.commits to tracker.commits;
        // guarantee 1: the tracker is the only writer
        interface onlyWriter : QuadWrite connect tracker.write to store.write;
        interface registryReads : QuadRead connect registry.reads to store.read;
        interface authoringReads : QuadRead connect authoring.reads to store.read;
        interface vocabularyReads : QuadRead connect vocabulary.reads to store.read;
        interface reasoningReads : QuadRead connect reasoning.reads to store.read;
        interface qualityReads : QuadRead connect quality.reads to store.read;
        interface searchReads : QuadRead connect search.reads to store.read;
        interface alignmentReads : QuadRead connect alignment.reads to store.read;
        // guarantee 2: agents reach the platform only through guarded operations
        interface requirementsTools : OperationCall connect requirementsAgent.tools to registry.calls;
        interface extractionTools : OperationCall connect extractionAgent.tools to registry.calls;
        interface modelingTools : OperationCall connect modelingCopilot.tools to registry.calls;
        interface vocabularyTools : OperationCall connect vocabularyAgent.tools to registry.calls;
        interface alignmentTools : OperationCall connect alignmentAgent.tools to registry.calls;
        interface qualityTools : OperationCall connect qualityAgent.tools to registry.calls;
        interface stewardTools : OperationCall connect stewardAgent.tools to registry.calls;
        interface kgTools : OperationCall connect kgBuilder.tools to registry.calls;
        interface assistantTools : OperationCall connect assistant.tools to registry.calls;
        interface conductorTools : OperationCall connect conductor.tools to registry.calls;
        interface requirementsModel : ModelCall connect requirementsAgent.model to gateway.serve;
        interface extractionModel : ModelCall connect extractionAgent.model to gateway.serve;
        interface modelingModel : ModelCall connect modelingCopilot.model to gateway.serve;
        interface vocabularyModel : ModelCall connect vocabularyAgent.model to gateway.serve;
        interface alignmentModel : ModelCall connect alignmentAgent.model to gateway.serve;
        interface qualityModel : ModelCall connect qualityAgent.model to gateway.serve;
        interface stewardModel : ModelCall connect stewardAgent.model to gateway.serve;
        interface kgModel : ModelCall connect kgBuilder.model to gateway.serve;
        interface assistantModel : ModelCall connect assistant.model to gateway.serve;
    }

    part sip : SipSystem {
        // ---------------- functional requirements ---------------- //
        satisfy requirement : LifecycleOrchestration by sip.conductor;
        satisfy requirement : CompetencyQuestionTests by sip.quality;
        satisfy requirement : StageAssistance by sip.runtime;
        satisfy requirement : ProposalsViaStaging by sip.tracker;
        satisfy requirement : GroundedExtraction by sip.extractionAgent;
        satisfy requirement : ReviewAssistance by sip.stewardAgent;
        satisfy requirement : Projects by sip.governance;
        satisfy requirement : CapabilityAuthorization by sip.pdp;
        satisfy requirement : MachinePrincipals by sip.governance;
        satisfy requirement : CompleteChangeTracking by sip.tracker;
        satisfy requirement : ValidationWorkflow by sip.tracker;
        satisfy requirement : UndoRedo by sip.tracker;
        satisfy requirement : HistoryQuery by sip.tracker;
        satisfy requirement : AxiomLevelEditing by sip.authoring;
        satisfy requirement : ManchesterSyntax by sip.authoring;
        satisfy requirement : EntityCreation by sip.governance;
        satisfy requirement : DescriptionFrames by sip.authoring;
        satisfy requirement : Hierarchies by sip.authoring;
        satisfy requirement : Refactoring by sip.authoring;
        satisfy requirement : UsageAndMetrics by sip.quality;
        satisfy requirement : SkosManagement by sip.vocabulary;
        satisfy requirement : SkosXlLabels by sip.vocabulary;
        satisfy requirement : ReasonerManagement by sip.reasoning;
        satisfy requirement : InferenceResults by sip.reasoning;
        satisfy requirement : Explanation by sip.reasoning;
        satisfy requirement : IntegrityChecks by sip.quality;
        satisfy requirement : ReleaseGate by sip.quality;
        satisfy requirement : SourceIngestion by sip.io;
        satisfy requirement : TabularLifting by sip.kg;
        satisfy requirement : EntityResolution by sip.kg;
        satisfy requirement : Alignment by sip.alignment;
        satisfy requirement : Search by sip.search;
        satisfy requirement : Publication by sip.io;
        // ---------------- quality requirements ------------------- //
        satisfy requirement : EveryOperationGuarded by sip.registry;
        satisfy requirement : AgentsNeverValidate by sip.pdp;
        satisfy requirement : LlmDataPolicy by sip.runtime;
        satisfy requirement : InteractiveLatency by sip.tracker;
        satisfy requirement : CorpusScale by sip.store;
        satisfy requirement : RecoveryObjectives by sip.store;
        satisfy requirement : LlmIndependence by sip.runtime;
        satisfy requirement : ExtensionPoints by sip.registry;
        satisfy requirement : HistoryCompatibility by sip.tracker;
        satisfy requirement : Multilinguality by sip.authoring;
        satisfy requirement : AccessibleUi by sip.edge;
        satisfy requirement : AiContentTransparency by sip.tracker;
        satisfy requirement : InferenceResidency by sip.gateway;
        satisfy requirement : RolePerspectives by sip.edge;
        satisfy requirement : PythonCore by sip.reasoning;
        satisfy requirement : Grounding by sip.runtime;
        satisfy requirement : BoundedAutonomy by sip.runtime;
        satisfy requirement : MeasuredAssistance by sip.runtime;
        satisfy requirement : ProfileHonesty by sip.reasoning;
    }
}
