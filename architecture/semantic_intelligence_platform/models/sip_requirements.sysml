/*
 * Semantic Intelligence Platform -- requirements.
 * SysML v2 textual notation.
 *
 * FR-* are functional requirements, grouped by lifecycle area. Each carries the
 * @Provenance of the behaviour it asks for (Protege, VocBench 3 / Semantic Turkey, or new).
 * QR-* are quality requirements; each carries the @Perspective that drives it.
 * Satisfaction (`satisfy ... by`) is declared in SipFunctional; verification
 * (`verify`) in SipVerification. tools/sysml_check.py fails the build when a requirement
 * is unsatisfied or unverified.
 */

package SipRequirements {

    private import ScalarValues::*;
    private import SipViewpoints::*;
    private import SipContext::*;

    // ================================================================== //
    // Lifecycle and agents
    // ================================================================== //

    requirement def <'FR-LC-01'> LifecycleOrchestration {
        doc /* SIP shall carry a knowledge project through the stages Scope, Acquire, Model,
             * Validate, Review, Populate, Reason, Publish and Consume, recording the state of
             * each stage and requiring an explicit human gate decision to leave Review and
             * Publish. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "NeOn/METHONTOLOGY lifecycle"; }
    }
    requirement def <'FR-LC-02'> CompetencyQuestionTests {
        doc /* SIP shall store competency questions with an executable SPARQL formulation and an
             * expected-answer predicate, and run them as a regression suite on every release
             * candidate. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "Gruninger & Fox CQs; Keet ch.5"; }
    }
    requirement def <'FR-AG-01'> StageAssistance {
        doc /* Every lifecycle stage shall have at least one assisting agent that proposes work
             * products for that stage. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "agent layer"; }
    }
    requirement def <'FR-AG-02'> ProposalsViaStaging {
        doc /* Agent writes shall be recorded as staged commits carrying an evidence record
             * (sources, model id, prompt hash, confidence, cost), regardless of the project's
             * validation setting. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "ChangeTrackerConnection validation mode"; }
    }
    requirement def <'FR-AG-03'> GroundedExtraction {
        doc /* Every assertion extracted from a document shall carry a verbatim quote and
             * character offsets into the source, or be rejected by the extraction critic. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "langextract_ontology"; }
    }
    requirement def <'FR-AG-04'> ReviewAssistance {
        doc /* A steward agent shall summarise each pending commit -- what changes, which checks
             * it breaks or fixes, its evidence -- and recommend, never decide. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "VocBench validation queue"; }
    }

    // ================================================================== //
    // Governance (VocBench 3 / Semantic Turkey)
    // ================================================================== //

    requirement def <'FR-GOV-01'> Projects {
        doc /* Projects with a model type (RDFS, OWL, SKOS, SKOS-XL, OntoLex), a lexicalization
             * model, base URI, default namespace, validation and history switches, and scoped
             * settings. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "ProjectManager.createProject"; }
    }
    requirement def <'FR-GOV-02'> CapabilityAuthorization {
        doc /* Role-based CRUDV capabilities over resource roles and scopes (VocBench's
             * capability language), with language restrictions on project-user bindings. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "VocBench3"; sourceArtefact = "AuthorizationEvaluator.ts; STAuthorizationEvaluator"; }
    }
    requirement def <'FR-GOV-03'> MachinePrincipals {
        doc /* Agents and services act under their own machine identities, bound to projects and
             * roles exactly like users, with an on-behalf-of chain to a human. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "VocBench3"; sourceArtefact = "Machines service"; }
    }

    // ================================================================== //
    // Change management
    // ================================================================== //

    requirement def <'FR-CHG-01'> CompleteChangeTracking {
        doc /* Every write -- form edit, axiom edit, SPARQL Update, import, agent proposal -- passes
             * one write path that records the effective delta as a cl:Commit with quadruples. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "st-changetracking-sail"; }
    }
    requirement def <'FR-CHG-02'> ValidationWorkflow {
        doc /* With validation enabled, changes go to staging-add/staging-remove graphs; a V-holder
             * accepts (apply) or rejects (erase, no history trace). */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "Validation service; VALIDATION vocabulary"; }
    }
    requirement def <'FR-CHG-03'> UndoRedo {
        doc /* Per-principal undo and redo of committed changes, persisted as commits. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "HistoryManagerImpl"; }
    }
    requirement def <'FR-CHG-04'> HistoryQuery {
        doc /* History filterable by principal, operation, resource and time, with per-commit delta. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "History service"; }
    }

    // ================================================================== //
    // Ontology authoring (Protege)
    // ================================================================== //

    requirement def <'FR-AUT-01'> AxiomLevelEditing {
        doc /* An OWL 2 structural axiom view over RDF; add and remove axioms (including those whose
             * class expressions are blank-node structures) exactly. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLModelManager.applyChanges; OWL API"; }
    }
    requirement def <'FR-AUT-02'> ManchesterSyntax {
        doc /* Parse, render and auto-complete Manchester OWL class expressions using the project's
             * entity renderings (labels, prefixed names or IRIs). */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLExpressionChecker; AutoCompleter"; }
    }
    requirement def <'FR-AUT-03'> EntityCreation {
        doc /* Create classes, properties and individuals with configurable IRI generation
             * (name-as-fragment, auto-ID, template) and label creation. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "CustomOWLEntityFactory; EntityCreationPreferences"; }
    }
    requirement def <'FR-AUT-04'> DescriptionFrames {
        doc /* Class, property and individual description frames, and the typed resource-view
             * sections with per-value scope (local, staged, imported, inferred). */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege+SemanticTurkey"; sourceArtefact = "OWLClassDescriptionFrame; ResourceView service"; }
    }
    requirement def <'FR-AUT-05'> Hierarchies {
        doc /* Asserted and inferred class and property hierarchies with roots, children, paths to
             * root, and SKOS concept trees. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "AssertedClassHierarchyProvider"; }
    }
    requirement def <'FR-AUT-06'> Refactoring {
        doc /* Rename/change IRI, replace base URI, merge entities, move axioms between graphs,
             * delete entity with usage clean-up, convert to defined class, add closure axiom,
             * make sibling classes disjoint. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege+SemanticTurkey"; sourceArtefact = "OWLEntityRenamer; Refactor service"; }
    }
    requirement def <'FR-AUT-07'> UsageAndMetrics {
        doc /* Entity usage lookup and ontology metrics (counts per axiom type, DL expressivity hint). */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "UsageView; OntologyMetrics"; }
    }

    // ================================================================== //
    // Vocabulary (VocBench)
    // ================================================================== //

    requirement def <'FR-VOC-01'> SkosManagement {
        doc /* Concept schemes, top concepts, broader/narrower trees, collections (ordered and
             * unordered), notes and mappings. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "SKOS service"; }
    }
    requirement def <'FR-VOC-02'> SkosXlLabels {
        doc /* Reified SKOS-XL labels and conversion between SKOS and SKOS-XL lexicalization. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "SKOSXL service; Refactor.SKOStoSKOSXL"; }
    }

    // ================================================================== //
    // Reasoning (Protege)
    // ================================================================== //

    requirement def <'FR-RSN-01'> ReasonerManagement {
        doc /* Pluggable reasoners with a status machine (no reasoner, out of sync, classifying,
             * classified, inconsistent) and a declared OWL profile. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "OWLReasonerManagerImpl; ReasonerStatus"; }
    }
    requirement def <'FR-RSN-02'> InferenceResults {
        doc /* Inferred hierarchy, unsatisfiable classes, consistency, and materialised inferred
             * axioms in a separate graph. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "InferredOWLClassHierarchyProvider; InferredAxiomGenerator"; }
    }
    requirement def <'FR-RSN-03'> Explanation {
        doc /* Minimal justifications for an entailment or an unsatisfiable class. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "Protege"; sourceArtefact = "ExplanationManager; black-box justification"; }
    }

    // ================================================================== //
    // Quality
    // ================================================================== //

    requirement def <'FR-QA-01'> IntegrityChecks {
        doc /* The Semantic Turkey ICV checks (dangling concepts, cyclic hierarchies, missing labels,
             * conflicting labels, ...) each with its fix operation. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "ICV service"; }
    }
    requirement def <'FR-QA-02'> ReleaseGate {
        doc /* A release candidate passes only if it is consistent, has no blocker ICV finding and
             * its competency-question suite passes. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "quality gate"; }
    }

    // ================================================================== //
    // Acquisition, KG construction, alignment, search, publication
    // ================================================================== //

    requirement def <'FR-ACQ-01'> SourceIngestion {
        doc /* Register documents and tabular sources as project sources with stable ids and hashes. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "InputOutput; Sheet2RDF"; }
    }
    requirement def <'FR-KG-01'> TabularLifting {
        doc /* Map tabular sources to the ontology (column -> property, row -> typed individual, IRI
             * template) and lift them into the KG graph through the write path. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "Sheet2RDF / CODA PEARL"; }
    }
    requirement def <'FR-KG-02'> EntityResolution {
        doc /* Detect duplicate individuals across sources and propose owl:sameAs or merges. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "new"; sourceArtefact = "entity resolution"; }
    }
    requirement def <'FR-ALN-01'> Alignment {
        doc /* Generate candidate correspondences, load/save Alignment API format, validate cells,
             * and apply accepted cells as mapping triples in the mappings graph. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "Alignment service; MAPLE"; }
    }
    requirement def <'FR-SRC-01'> Search {
        doc /* Search by label/local name/IRI/notes with startsWith/contains/endsWith/exact/fuzzy
             * modes and language filters; guarded SPARQL query and update. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey+Protege"; sourceArtefact = "Search service; OWLEntityFinder"; }
    }
    requirement def <'FR-PUB-01'> Publication {
        doc /* Export in RDF serialisations with optional filtering transformers, versioned
             * releases, and DCAT/VoID dataset metadata. */
        subject sip : SemanticIntelligencePlatform;
        @Provenance { sourceTool = "SemanticTurkey"; sourceArtefact = "Export service; MetadataRegistry"; }
    }

    // ================================================================== //
    // Quality requirements (perspective-driven)
    // ================================================================== //

    requirement def <'QR-SEC-01'> EveryOperationGuarded {
        doc /* Every service operation declares the capability it requires; an unguarded operation
             * fails the build. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::security; }
    }
    requirement def <'QR-SEC-02'> AgentsNeverValidate {
        doc /* No machine principal can hold or exercise the V capability; machine writes are always
             * staged. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::security; }
    }
    requirement def <'QR-SEC-03'> LlmDataPolicy {
        doc /* Project content is sent to an LLM provider only if the project's AI policy allows it;
             * the policy is checked per call and the decision logged. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::security; }
    }
    requirement def <'QR-PRF-01'> InteractiveLatency {
        doc /* p95 latency of a single-entity edit (validate, apply, record history) under 500 ms on a
             * 1M-triple project. */
        subject sip : SemanticIntelligencePlatform;
        attribute p95LatencyMs : Real = 500.0;
        @Perspective { kind = PerspectiveKind::performanceScalability; }
    }
    requirement def <'QR-PRF-02'> CorpusScale {
        doc /* Browse and edit FIBO (production) and EuroVoc-scale thesauri without loading the full
             * closure into the client. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::performanceScalability; }
    }
    requirement def <'QR-AVL-01'> RecoveryObjectives {
        doc /* RPO 15 minutes, RTO 1 hour for the canonical store; history and content restore
             * together. */
        subject sip : SemanticIntelligencePlatform;
        attribute rpoMinutes : Real = 15.0;
        attribute rtoMinutes : Real = 60.0;
        @Perspective { kind = PerspectiveKind::availabilityResilience; }
    }
    requirement def <'QR-AVL-02'> LlmIndependence {
        doc /* Every lifecycle stage remains completable by humans when the LLM provider is
             * unavailable; agents degrade, the platform does not. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::availabilityResilience; }
    }
    requirement def <'QR-EVO-01'> ExtensionPoints {
        doc /* Reasoners, matchers, extractors, URI generators, ICV checks, exporters and agents are
             * registered through extension points, not code changes. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::evolution; }
    }
    requirement def <'QR-EVO-02'> HistoryCompatibility {
        doc /* The history graph uses Semantic Turkey's CHANGELOG vocabulary unchanged. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::evolution; }
    }
    requirement def <'QR-I18N-01'> Multilinguality {
        doc /* Renderings follow an ordered language preference; bindings may restrict editing to
             * languages. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::internationalisation; }
    }
    requirement def <'QR-ACC-01'> AccessibleUi {
        doc /* The workbench UI conforms to WCAG 2.2 AA. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::accessibility; }
    }
    requirement def <'QR-REG-01'> AiContentTransparency {
        doc /* AI-generated content is marked as such in history and in exported provenance;
             * audit records are retained for the configured period. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::regulation; }
    }
    requirement def <'QR-LOC-01'> InferenceResidency {
        doc /* The LLM inference region and provider are configurable per deployment. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::location; }
    }
    requirement def <'QR-USA-01'> RolePerspectives {
        doc /* Role-specific workspaces (ontology, thesaurus, KG, review, agent) over one model. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::usability; }
    }
    requirement def <'QR-DEV-01'> PythonCore {
        doc /* The core runs in pure Python (rdflib, owlrl); JVM components are optional sidecars. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::developmentResource; }
    }
    requirement def <'QR-AIT-01'> Grounding {
        doc /* Every agent proposal cites the evidence it rests on (source span, triples, check
             * result); ungrounded proposals are discarded by a deterministic critic. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::aiTrustworthiness; }
    }
    requirement def <'QR-AIT-02'> BoundedAutonomy {
        doc /* Agent runs have token and step budgets, a kill switch, and cannot exceed the
             * capabilities of their machine principal. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::aiTrustworthiness; }
    }
    requirement def <'QR-AIT-03'> MeasuredAssistance {
        doc /* Per agent: proposal count, acceptance rate, check delta and cost are measured and
             * reported. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::aiTrustworthiness; }
    }
    requirement def <'QR-AIT-04'> ProfileHonesty {
        doc /* Every entailment and explanation states the reasoner and OWL profile that produced it;
             * RL results are never presented as DL results. */
        subject sip : SemanticIntelligencePlatform;
        @Perspective { kind = PerspectiveKind::aiTrustworthiness; }
    }
}
