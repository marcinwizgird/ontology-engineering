/*
 * Semantic Intelligence Platform -- CONTEXT VIEWPOINT.
 * SysML v2 textual notation.
 *
 * The system of interest, the people and systems around it, the interfaces it exposes
 * and consumes, and the use cases that cross the boundary. The context is deliberately
 * small: everything an LLM provider sees passes one port (llm), everything a consumer
 * sees passes two (api, sparql), and the canonical store is reached only through the
 * platform -- there is no back door into Fuseki for editors or agents.
 */

package SipContext {

    private import ScalarValues::*;
    private import SipViewpoints::*;

    // ------------------------------------------------------------------ //
    // Interfaces at the boundary
    // ------------------------------------------------------------------ //

    port def OperationApiPort {
        doc /* REST/JSON: POST /projects/{p}/ops/{operation}; GET /operations (generated
             * client); agent run/stop endpoints. Every call names a principal. */
        attribute principal : String;
        attribute operation : String;
    }
    port def SparqlEndpointPort {
        doc /* Read-only SPARQL 1.1 over released graphs (consumers, GraphRAG). */
        attribute dataset : String;
    }
    port def LlmPort {
        doc /* Anthropic Messages API: structured JSON outputs, adaptive thinking, prompt
             * caching, refusal fallback. Data leaves only if the project AI policy allows. */
        attribute modelId : String;
        attribute inferenceGeo : String[0..1];
    }
    port def GraphStorePort {
        doc /* SPARQL 1.1 Update + Graph Store Protocol to Apache Jena Fuseki (TDB2). */
        attribute endpoint : String;
    }
    port def PropertyGraphPort {
        doc /* openCypher writes of the derived LPG projection to FalkorDB. */
        attribute graphName : String;
    }
    port def IdentityPort {
        doc /* OIDC: tokens to principals. */
        attribute issuer : String;
    }
    port def SourcePort {
        doc /* Documents, spreadsheets, RDF dumps and external ontologies (FIBO, ...). */
        attribute uri : String;
        attribute mediaType : String;
    }

    // ------------------------------------------------------------------ //
    // The system of interest (black box)
    // ------------------------------------------------------------------ //

    part def SemanticIntelligencePlatform {
        doc /* End-to-end, agent-assisted ontology and knowledge-graph construction: the
             * union of Protege's OWL authoring and reasoning and VocBench 3's governed,
             * collaborative vocabulary management, rebuilt in Python, with an agent layer
             * that assists every lifecycle stage under the same governance as humans. */
        port api : OperationApiPort;
        port sparql : SparqlEndpointPort;
        port llm : ~LlmPort;
        port store : ~GraphStorePort;
        port lpg : ~PropertyGraphPort;
        port identity : ~IdentityPort;
        port sources : ~SourcePort;
    }

    // ------------------------------------------------------------------ //
    // External entities
    // ------------------------------------------------------------------ //

    part def HumanUser { attribute role : String; }
    part def LlmProvider { port llm : LlmPort; doc /* Claude via the Anthropic API. */ }
    part def CanonicalStore { port gsp : GraphStorePort; doc /* Apache Jena Fuseki / TDB2. */ }
    part def PropertyGraphStore { port bolt : PropertyGraphPort; doc /* FalkorDB. */ }
    part def IdentityProvider { port oidc : IdentityPort; }
    part def SourceSystems { port out : SourcePort;
        doc /* Document repositories, spreadsheets, data catalogues, ontology registries. */ }
    part def ConsumerApplications { port q : ~SparqlEndpointPort;
        doc /* Analytics, GraphRAG assistants, downstream services. */ }
    part def LegacyTools {
        doc /* Protege Desktop and VocBench 3 remain usable on exported artefacts: OWL files
             * for Protege, CHANGELOG-compatible history and SKOS for VocBench. */
    }

    // ------------------------------------------------------------------ //
    // Context
    // ------------------------------------------------------------------ //

    part context {
        part sip : SemanticIntelligencePlatform;
        part people : HumanUser[1..*];
        part llmProvider : LlmProvider;
        part fuseki : CanonicalStore;
        part falkor : PropertyGraphStore;
        part idp : IdentityProvider;
        part sourceSystems : SourceSystems;
        part consumers : ConsumerApplications[0..*];
        part legacy : LegacyTools[0..1];

        connect sip.llm to llmProvider.llm;
        connect sip.store to fuseki.gsp;
        connect sip.lpg to falkor.bolt;
        connect sip.identity to idp.oidc;
        connect sip.sources to sourceSystems.out;
        connect consumers.q to sip.sparql;
    }

    // ------------------------------------------------------------------ //
    // Use cases across the boundary
    // ------------------------------------------------------------------ //

    use case def ScopeProject {
        doc /* Brief -> competency questions with executable tests (RequirementsAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor pm : ProjectManager;
        actor expert : DomainExpert;
    }
    use case def AcquireKnowledge {
        doc /* Register sources; grounded extraction of candidates (ExtractionAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor kge : KnowledgeGraphEngineer;
    }
    use case def AuthorOntology {
        doc /* Protege-class OWL authoring: classes, properties, Manchester axioms, frames,
             * refactoring; copilot proposals (ModelingCopilot). */
        subject sip : SemanticIntelligencePlatform;
        actor oe : OntologyEngineer;
    }
    use case def ManageVocabulary {
        doc /* VocBench-class SKOS/SKOS-XL editing; multilingual labels (VocabularyAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor term : Terminologist;
    }
    use case def AlignOntologies {
        doc /* Candidate correspondences, cell validation, mappings graph (AlignmentAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor oe : OntologyEngineer;
    }
    use case def AssureQuality {
        doc /* ICV, reasoning, explanations, CQ tests, repairs (QualityAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor oe : OntologyEngineer;
        actor val : Validator;
    }
    use case def ReviewChanges {
        doc /* Validation queue with steward summaries; accept/reject is human. */
        subject sip : SemanticIntelligencePlatform;
        actor val : Validator;
    }
    use case def PopulateGraph {
        doc /* Tabular lifting, entity resolution, LPG projection (KnowledgeGraphBuilder). */
        subject sip : SemanticIntelligencePlatform;
        actor kge : KnowledgeGraphEngineer;
    }
    use case def PublishRelease {
        doc /* Release gate, export, dataset metadata. */
        subject sip : SemanticIntelligencePlatform;
        actor pm : ProjectManager;
    }
    use case def ConsumeKnowledge {
        doc /* Grounded Q&A and SPARQL over released graphs (AssistantAgent). */
        subject sip : SemanticIntelligencePlatform;
        actor kc : KnowledgeConsumer;
    }
    use case def GovernPlatform {
        doc /* Projects, roles, bindings, AI policy, agent enablement. */
        subject sip : SemanticIntelligencePlatform;
        actor pm : ProjectManager;
        actor op : PlatformOperator;
    }

    use case def ConstructKnowledgeEndToEnd {
        doc /* The E2E use case: every stage, with human gates at review and publish. */
        subject sip : SemanticIntelligencePlatform;
        actor pm : ProjectManager;
        include use case scope : ScopeProject;
        include use case acquire : AcquireKnowledge;
        include use case author : AuthorOntology;
        include use case vocabulary : ManageVocabulary;
        include use case align : AlignOntologies;
        include use case quality : AssureQuality;
        include use case review : ReviewChanges;
        include use case populate : PopulateGraph;
        include use case publish : PublishRelease;
        include use case consume : ConsumeKnowledge;
    }
}
