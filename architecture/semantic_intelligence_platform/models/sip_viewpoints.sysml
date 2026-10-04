/*
 * Semantic Intelligence Platform (SIP) -- stakeholders, concerns, viewpoints, perspectives.
 * SysML v2 textual notation.
 *
 * This package is the Rozanski & Woods architecture-description frame expressed in
 * SysML v2's own ISO 42010 machinery: stakeholders are part defs, concerns are
 * `concern def`s that name their stakeholders, each of the seven R&W viewpoints is a
 * `viewpoint def` that frames concerns, and each view (in the other packages) is a
 * `view def` that satisfies its viewpoint. Perspectives are not a SysML v2 concept;
 * they are modelled as a `metadata def` applied to quality requirements and to the
 * tactics that realise them, so "which requirements does the Security perspective
 * drive, and which design elements answer them" is a model query, not prose.
 */

package SipViewpoints {

    private import ScalarValues::*;

    // ------------------------------------------------------------------ //
    // 1. Stakeholders (R&W stakeholder classes, instantiated for SIP)
    // ------------------------------------------------------------------ //

    abstract part def Stakeholder {
        attribute rwClass : StakeholderClass;
        attribute involvement : String;
    }

    enum def StakeholderClass {
        enum acquirer; enum assessor; enum communicator; enum developer; enum maintainer;
        enum productionEngineer; enum supplier; enum supportStaff; enum systemAdministrator;
        enum tester; enum user;
    }

    part def OntologyEngineer :> Stakeholder {
        doc /* Authors and refactors OWL ontologies: axioms, class expressions, reasoning,
             * explanations. The Protege power user. */
    }
    part def KnowledgeGraphEngineer :> Stakeholder {
        doc /* Builds and operates instance graphs: lifting from sources, entity resolution,
             * population, projection to the property graph. */
    }
    part def Terminologist :> Stakeholder {
        doc /* Maintains SKOS thesauri, labels and definitions, often for one language only.
             * The VocBench power user. */
    }
    part def DomainExpert :> Stakeholder {
        doc /* Supplies and checks knowledge; answers competency questions; does not read RDF. */
    }
    part def Validator :> Stakeholder {
        doc /* Holds the V capability: accepts or rejects staged changes, human or agent-made. */
    }
    part def ProjectManager :> Stakeholder {
        doc /* Owns a project: members, roles, validation policy, release cadence. */
    }
    part def KnowledgeConsumer :> Stakeholder {
        doc /* Downstream applications, analysts and GraphRAG agents that query released
             * ontologies and graphs. */
    }
    part def PlatformOperator :> Stakeholder {
        doc /* Runs SIP on GKE: Fuseki, FalkorDB, workers, LLM quota, backups. */
    }
    part def PlatformDeveloper :> Stakeholder {
        doc /* Builds and maintains SIP and its extensions. */
    }
    part def SecurityOfficer :> Stakeholder {
        doc /* Assessor for access control, data protection and AI-use policy. */
    }
    part def AiGovernanceBoard :> Stakeholder {
        doc /* Assessor for agent autonomy, model risk and auditability of AI contributions. */
    }
    part def Sponsor :> Stakeholder {
        doc /* Acquirer: funds the platform, judges it by time-to-ontology and reuse. */
    }

    // ------------------------------------------------------------------ //
    // 2. Concerns
    // ------------------------------------------------------------------ //

    concern def EndToEndLifecycle {
        doc /* Can one platform carry a knowledge asset from scoping to published, queried
             * graph without exporting between tools? */
        stakeholder sponsor : Sponsor;
        stakeholder oe : OntologyEngineer;
        stakeholder kge : KnowledgeGraphEngineer;
    }
    concern def AuthoringExpressiveness {
        doc /* Full OWL 2 authoring: class expressions, property characteristics, GCIs,
             * refactoring, Manchester syntax with completion -- Protege parity. */
        stakeholder oe : OntologyEngineer;
    }
    concern def VocabularyManagement {
        doc /* SKOS/SKOS-XL concepts, schemes, collections, multilingual labels -- VocBench parity. */
        stakeholder term : Terminologist;
    }
    concern def ControlledPublication {
        doc /* Nothing reaches stable content without the project's validation policy. */
        stakeholder val : Validator;
        stakeholder pm : ProjectManager;
    }
    concern def CompleteHistory {
        doc /* Every change -- human, agent, SPARQL Update, bulk import -- is in the history,
             * attributable, and reversible. */
        stakeholder pm : ProjectManager;
        stakeholder sec : SecurityOfficer;
    }
    concern def AgentSafety {
        doc /* Agents cannot widen their own authority, cannot validate, and every agent
             * claim is grounded in evidence a human can inspect. */
        stakeholder aib : AiGovernanceBoard;
        stakeholder val : Validator;
    }
    concern def AgentUsefulness {
        doc /* Agents measurably shorten each lifecycle stage; their proposals are accepted
             * at a rate worth the review effort. */
        stakeholder sponsor : Sponsor;
        stakeholder de : DomainExpert;
    }
    concern def LogicalCorrectness {
        doc /* Inconsistency and unsatisfiable classes are detected, explained, and never
             * silently published; every entailment states which reasoner profile produced it. */
        stakeholder oe : OntologyEngineer;
        stakeholder kc : KnowledgeConsumer;
    }
    concern def DataQuality {
        doc /* Integrity checks, shapes and competency-question tests gate releases. */
        stakeholder val : Validator;
        stakeholder kc : KnowledgeConsumer;
    }
    concern def AccessControl {
        doc /* Fine-grained CRUDV capabilities per resource role, scope and language. */
        stakeholder sec : SecurityOfficer;
        stakeholder pm : ProjectManager;
    }
    concern def Interoperability {
        doc /* Standard formats in and out (RDF/OWL/SKOS/EDOAL/SHACL/DCAT); history readable
             * by VocBench tooling; ontologies loadable in Protege. */
        stakeholder kc : KnowledgeConsumer;
        stakeholder oe : OntologyEngineer;
    }
    concern def ScaleAndLatency {
        doc /* FIBO/EuroVoc-scale artefacts; interactive edits under a second. */
        stakeholder oe : OntologyEngineer;
        stakeholder op : PlatformOperator;
    }
    concern def Operability {
        doc /* Install, back up, restore, upgrade, monitor, and control LLM spend. */
        stakeholder op : PlatformOperator;
    }
    concern def Extensibility {
        doc /* New reasoners, matchers, extractors, URI generators, exporters and agents plug in
             * without forking the core -- the role OSGi plays in Protege. */
        stakeholder dev : PlatformDeveloper;
    }
    concern def Maintainability {
        doc /* A Python codebase with enforced layering and executable architecture checks. */
        stakeholder dev : PlatformDeveloper;
    }

    // ------------------------------------------------------------------ //
    // 3. The seven Rozanski & Woods viewpoints
    // ------------------------------------------------------------------ //

    viewpoint def ContextViewpoint {
        doc /* Relationships, dependencies and interactions between SIP and its environment:
             * people, systems, external services. */
        frame concern lifecycle : EndToEndLifecycle;
        frame concern interop : Interoperability;
    }
    viewpoint def FunctionalViewpoint {
        doc /* Functional elements, their responsibilities, interfaces and primary interactions. */
        frame concern authoring : AuthoringExpressiveness;
        frame concern vocab : VocabularyManagement;
        frame concern lifecycle : EndToEndLifecycle;
        frame concern ext : Extensibility;
    }
    viewpoint def InformationViewpoint {
        doc /* How SIP stores, manipulates, manages and distributes information: the named-graph
             * layout, the change model, proposals and evidence, ownership and lifecycle. */
        frame concern history : CompleteHistory;
        frame concern pub : ControlledPublication;
        frame concern quality : DataQuality;
    }
    viewpoint def ConcurrencyViewpoint {
        doc /* Processes, threads and their coordination: the single-writer coordinator, agent
             * workers, reasoning jobs, and the state machines that serialise them. */
        frame concern scale : ScaleAndLatency;
        frame concern history : CompleteHistory;
    }
    viewpoint def DevelopmentViewpoint {
        doc /* Module structure, layering rules, common processing, codeline and test strategy. */
        frame concern maint : Maintainability;
        frame concern ext : Extensibility;
    }
    viewpoint def DeploymentViewpoint {
        doc /* Runtime platform, nodes, network, third-party software and their allocation. */
        frame concern scale : ScaleAndLatency;
        frame concern ops : Operability;
    }
    viewpoint def OperationalViewpoint {
        doc /* Installation, migration, monitoring, backup/restore, configuration, LLM cost
             * control and support. */
        frame concern ops : Operability;
        frame concern safety : AgentSafety;
    }

    // ------------------------------------------------------------------ //
    // 4. Perspectives -- applied as metadata to requirements and tactics
    // ------------------------------------------------------------------ //

    enum def PerspectiveKind {
        enum security; enum performanceScalability; enum availabilityResilience;
        enum evolution; enum accessibility; enum internationalisation; enum location;
        enum regulation; enum usability; enum developmentResource;
        /* Custom perspective (R&W permit them): the qualities specific to an agent-assisted
         * system -- bounded autonomy, grounding, human oversight, evaluation, cost. */
        enum aiTrustworthiness;
    }

    metadata def Perspective {
        doc /* Marks a quality requirement or a tactic as belonging to a perspective. */
        attribute kind : PerspectiveKind;
    }

    metadata def Tactic {
        doc /* A design decision applied to satisfy a perspective's requirements. */
        attribute perspective : PerspectiveKind;
        attribute rationale : String;
    }

    metadata def Provenance {
        doc /* Where a functional element's behaviour was reverse-engineered from. */
        attribute sourceTool : String;      // Protege | VocBench3 | SemanticTurkey | new
        attribute sourceArtefact : String;  // class / service / file the behaviour came from
    }
}
