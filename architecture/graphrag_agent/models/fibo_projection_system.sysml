/*
 * FIBO -> Labeled Property Graph: system architecture.
 * SysML v2 (KerML textual notation).
 *
 * Companion to ontology_projection.sysml, and deliberately a different kind of model.
 * That one defines pi : Ontology -> PropertyGraph as a *function* -- domain, codomain,
 * and the invariants that make a run of it correct. This one defines the *system* that
 * executes pi against FIBO specifically: its context, its components and the interfaces
 * between them, where each component is deployed, what varies, and which verification
 * case discharges which requirement.
 *
 * The numbers in `FiboCharacterisation` are measured from a real run over the vendored
 * FIBO release, not targets. They are in the model because they are the facts that drove
 * the architecture -- particularly the restriction-to-domain/range ratio, which is the
 * reason AxiomUnfolder exists as a component at all.
 */

package FiboProjectionSystem {

    import ScalarValues::*;
    import OntologyProjection::*;

    // ====================================================================== //
    // 1. Requirements
    // ====================================================================== //

    requirement def <'R1'> AxiomFidelity {
        doc /* Every named class, every subClassOf between named classes, and every
             * restriction whose filler resolves to a named class must appear in the
             * property graph. "Appear" means an edge, not a dropped row logged at DEBUG. */
        subject source : Ontology;
        attribute unfoldedAxioms : Integer;
        attribute landedEdges    : Integer;
        require constraint { landedEdges == unfoldedAxioms }
    }

    requirement def <'R2'> CitationTraceability {
        doc /* Every graph node carries the unchanged IRI of the ontology entity it came
             * from. Everything downstream -- citation, verification, round-tripping a
             * correction back to the RDF -- rests on this one property. */
        subject graph : PropertyGraph;
    }

    requirement def <'R3'> Repeatability {
        doc /* Re-projecting an unchanged source leaves the graph byte-identical in shape:
             * same node count, same edge count, same types. MERGE semantics throughout. */
        subject graph : PropertyGraph;
    }

    requirement def <'R4'> OfflineOperation {
        doc /* A projection of the vendored FIBO release completes with no network access.
             * FIBO imports OMG Commons, which is not vendored; the system must degrade to
             * flagged placeholders rather than fail or silently truncate the taxonomy. */
        subject system : FiboProjectionSystemDef;
    }

    requirement def <'R5'> Retrievability {
        doc /* The loaded graph supports both semantic and lexical lookup over classes,
             * and exact lookup by IRI. Hybrid retrieval is a requirement on the *store*,
             * not only on the retriever: the indexes have to exist for it to be possible. */
        subject graph : PropertyGraph;
    }

    requirement def <'R6'> BulkThroughput {
        doc /* The full FIBO release projects in minutes on a developer machine, because a
             * projection nobody re-runs is a projection that silently goes stale. */
        subject system : FiboProjectionSystemDef;
        attribute measuredSeconds : Real;
        attribute budgetSeconds   : Real default 300.0;
        require constraint { measuredSeconds <= budgetSeconds }
    }

    requirement def <'R7'> SourceIndependence {
        doc /* The same pipeline projects from a triplestore or from a directory of files.
             * Only the Extraction component differs. */
        subject system : FiboProjectionSystemDef;
    }

    requirement def <'R8'> InjectionSafety {
        doc /* A Cypher relationship type cannot be parameterised, so it is interpolated
             * into the query string -- which makes ontology-supplied property names an
             * injection surface. Every interpolated token is sanitised at extraction and
             * re-validated at load against ^[A-Z][A-Z0-9_]*$; every value stays bound. */
        subject system : FiboProjectionSystemDef;
    }

    requirement def <'R9'> EmbeddingCoherence {
        doc /* The encoder that produced the indexed vectors is persisted with the graph
             * and is the one used to encode queries. A different fitted basis puts the
             * query in a different space and returns plausible, meaningless neighbours --
             * a failure with no visible symptom. */
        subject system : FiboProjectionSystemDef;
    }

    // ====================================================================== //
    // 2. System context
    // ====================================================================== //

    part def OntologyEngineer {
        doc /* Runs the projection and reads its report. The only human in the loop. */
    }

    part def FiboRepository {
        doc /* The vendored EDM Council release: 299 RDF/XML files in a module tree.
             * Read-only to this system. */
        attribute releasePath : String;
        attribute fileCount   : Integer;
    }

    part def CommonsRegistry {
        doc /* OMG Commons, referenced by FIBO's owl:imports and not vendored. Reachable
             * only when --follow-imports is set; absent by default, which is what R4
             * forces the system to tolerate. */
        attribute reachable : Boolean default false;
    }

    part def FusekiDataset {
        doc /* The alternative source. Present in the context because R7 says the system
             * must accept either, not because FIBO is projected through it. */
    }

    part def FalkorDbInstance {
        doc /* The target store. Redis wire protocol, loopback-bound. */
        attribute host      : String default "localhost";
        attribute port      : Integer default 6379;
        attribute graphName : String default "fibo";
    }

    part def ArtifactStore {
        doc /* Filesystem location holding the fitted encoder. The physical realisation of
             * R9: the artifact is what keeps encoder and index in step across processes. */
        attribute path : String;
    }

    part def SystemContext {
        part engineer : OntologyEngineer;
        part fibo     : FiboRepository;
        part commons  : CommonsRegistry;
        part fuseki   : FusekiDataset;
        part falkor   : FalkorDbInstance;
        part artifacts: ArtifactStore;
        part system   : FiboProjectionSystemDef;
    }

    // ====================================================================== //
    // 3. Interfaces
    // ====================================================================== //

    port def RdfFilePort      { attribute rootPaths : String[1..*]; }
    port def SparqlPort       { attribute endpoint : String; }
    port def CypherPort       { attribute statement : String; }
    port def ArtifactPort     { attribute artifactPath : String; }
    port def ControlPort      { attribute options : ProjectionOptions; }
    port def ReportPort       { attribute report : ProjectionReport; }

    interface def RdfSourceInterface {
        doc /* Whatever supplies TBox records. Two realisations; see the variation point. */
        end provider : RdfFilePort;
        end consumer : RdfFilePort;
    }

    interface def GraphWriteInterface {
        doc /* Parameterised, UNWIND-batched Cypher. The only channel that mutates the
             * store, which is what makes R8 checkable in one place. */
        end writer : CypherPort;
        end store  : CypherPort;
    }

    interface def ArtifactInterface {
        end producer : ArtifactPort;
        end consumer : ArtifactPort;
    }

    attribute def ProjectionOptions {
        attribute graphName      : String default "fibo";
        attribute clearFirst     : Boolean default true;
        attribute embed          : Boolean default true;
        attribute encoderKind    : String default "tfidf";
        attribute followImports  : Boolean default false;
        attribute includeExternal: Boolean default true;
        attribute dryRun         : Boolean default false;
    }

    attribute def ProjectionReport {
        attribute filesParsed    : Integer;
        attribute filesFailed    : Integer;
        attribute triples        : Integer;
        attribute classes        : Integer;
        attribute externalClasses: Integer;
        attribute modules        : Integer;
        attribute subclassEdges  : Integer;
        attribute propertyEdges  : Integer;
        attribute restrictionEdges : Integer;
        attribute unfolded       : Integer;
        attribute landed         : Integer;
        attribute embeddingsSet  : Integer;
        attribute elapsedSeconds : Real;
    }

    // ====================================================================== //
    // 4. Structure
    // ====================================================================== //

    part def FiboProjectionSystemDef {
        doc /* Eight components on one pipeline, plus a controller. The decomposition
             * follows the pipeline stages rather than the source layout, so a stage can
             * be replaced without disturbing its neighbours -- which is what makes the
             * two source adapters and the three encoders interchangeable. */

        port control : ControlPort;
        port report  : ReportPort;
        port toSource : RdfFilePort;
        port toStore  : CypherPort;
        port toArtifacts : ArtifactPort;

        part controller  : ProjectionController;
        part adapter     : SourceAdapter;
        part reader      : TboxReader;
        part unfolder    : AxiomUnfolder;
        part builder     : MetaGraphBuilderComponent;
        part composer    : ProfileComposer;
        part encoder     : VectorEncoder;
        part loader      : GraphLoader;
        part indexer     : IndexManager;
        part artifactMgr : EncoderArtifactManager;

        // The pipeline. Written as connections rather than left implicit, because the
        // order is load-bearing: modules before classes before restrictions, or the
        // loader's two-endpoint MATCH drops edges (see V1 / the AxiomCoverage defect).
        connect adapter.records   to reader.records;
        connect reader.classes    to builder.classes;
        connect reader.expressions to unfolder.expressions;
        connect unfolder.edges    to builder.restrictionEdges;
        connect builder.ir        to composer.ir;
        connect composer.profiles to encoder.profiles;
        connect builder.ir        to loader.ir;
        connect encoder.vectors   to loader.vectors;
        connect loader.graph      to indexer.graph;
        connect encoder.fitted    to artifactMgr.encoder;
    }

    part def ProjectionController {
        doc /* Sequences the stages, owns the run's options, and assembles the report.
             * Realised by LpgConverter plus the `project` CLI subcommand. It is the only
             * component that knows the stage order, so the order is stated once. */
        port control : ControlPort;
        port report  : ReportPort;
    }

    part def SourceAdapter {
        doc /* Turns a source location into a parsed RDF graph plus per-file provenance.
             * The file adapter parses one file at a time and keeps the file boundary,
             * because an owl:Ontology-per-file is how module membership is recoverable at
             * all -- a union graph in a triplestore has already lost it. */
        port source : RdfFilePort;
        attribute parsedFiles  : Integer;
        attribute failedFiles  : Integer;
        attribute tolerateMalformedLiterals : Boolean default true;
    }

    part def TboxReader {
        doc /* Reads named classes, the subClassOf taxonomy, object properties with named
             * domain and range, and owl:Ontology module records. Also materialises
             * referenced-but-undeclared classes as external stubs -- see ExternalStubbing. */
        attribute declaredClasses  : Integer;
        attribute referencedClasses : Integer;
    }

    part def AxiomUnfolder {
        doc /* THE FIBO-SPECIFIC COMPONENT, and the reason this architecture differs from
             * a generic RDF-to-LPG converter.
             *
             * FIBO expresses relations as anonymous owl:Restriction superclasses --
             * `C subClassOf (p some D)` -- rather than as rdfs:domain/rdfs:range. Measured
             * over the vendored release: 2,721 restriction edges against 560 domain/range
             * edges, a ratio near five to one; in the FBC module alone, 642 against 37.
             * A converter that reads only named triples therefore produces a taxonomy
             * with almost no lateral structure: a tree, not a graph, and nothing useful
             * to traverse.
             *
             * Walks subClassOf and equivalentClass into blank-node class expressions,
             * descends unions and intersections to a bounded depth, and emits one edge per
             * (source, property, quantifier, named filler). */
        attribute maxExpressionDepth : Integer default 4;
        attribute maxFillerDepth     : Integer default 3;
        attribute quantifiersHandled : String[1..*] default
            ("some", "only", "value", "exactly", "min", "max");
        attribute unfolded : Integer;
        attribute landed   : Integer;
    }

    part def MetaGraphBuilderComponent {
        doc /* Holds the intermediate representation: a NetworkX MultiDiGraph with an edge
             * `kind` discriminator (taxonomy / objectProperty / restriction / definedIn).
             *
             * The IR is not incidental. It decouples reading from writing, so the
             * projection can be inspected, counted and diffed with no database in the
             * loop -- which is what makes `--dry-run` meaningful and what let the
             * unfolded-versus-landed defect be found by counting rather than by noticing
             * a wrong answer months later. */
        attribute nodes : Integer;
        attribute edges : Integer;
    }

    part def ProfileComposer {
        doc /* Builds one Concept Profile Document per class: name, synonyms, definition,
             * superclasses, restriction-derived relations, module.
             *
             * The relations clause is the part that matters for FIBO. Without it, sibling
             * classes differ only in their name and a boilerplate definition, and every
             * agreement in the ontology encodes to nearly the same point -- so the vector
             * index ranks by wording rather than by meaning. */
        attribute includeRelations : Boolean default true;
        attribute maxRelations     : Integer default 12;
    }

    part def VectorEncoder {
        doc /* Concept profile -> vector. Fitted encoders must be fitted before use and
             * persisted after; stateless ones simply have nothing to persist. */
        attribute kind      : String;
        attribute dimension : Integer;
        attribute fitted    : Boolean;
    }

    part def GraphLoader {
        doc /* IR -> Cypher. MERGE throughout. Dispatches on the IR's edge `kind`, so a
             * new edge kind added upstream cannot fall through into the wrong loader.
             *
             * Discriminating properties belong in the MERGE *pattern*, not in a following
             * SET. `via` and `quantifier` are both pattern properties for this reason:
             * with `via` left out, a domain/range MERGE matches and overwrites the
             * restriction edge of the same property between the same two classes, and the
             * restriction loader then recreates it on the next run. See V3. */
        attribute batchSize : Integer default 1000;
        attribute relTypePattern : String default "^[A-Z][A-Z0-9_]*$";
    }

    part def IndexManager {
        doc /* Declares the three index families the retrieval layer needs. The vector
             * index requires the store's native vecf32 type: a plain float array is
             * accepted, stored, and then invisible to the vector query procedure -- a
             * silent half-failure, so the conversion is not optional. */
        attribute vectorDimension  : Integer default 256;
        attribute similarity       : String default "cosine";
        attribute fulltextFields   : String[1..*] default ("name", "definition", "alt_text");
        attribute lookupFields     : String[1..*] default ("iri");
    }

    part def EncoderArtifactManager {
        doc /* Persists and reloads the fitted encoder, keyed by graph name. The physical
             * discharge of R9. */
        port artifact : ArtifactPort;
        attribute artifactPath : String;
        attribute sizeBytes    : Integer;
    }

    // ====================================================================== //
    // 5. Variation points
    // ====================================================================== //

    part def ExtractionVariant;
    variation part extractionStrategy : ExtractionVariant {
        doc /* R7. Only this stage differs between sources -- and only the file variant can
             * supply restrictions and module provenance, because both need structure that
             * a union graph behind a SPARQL endpoint has already discarded. */
        variant part fileExtraction  : ExtractionVariant {
            attribute seesRestrictions : Boolean default true;
            attribute seesModules      : Boolean default true;
        }
        variant part sparqlExtraction : ExtractionVariant {
            attribute seesRestrictions : Boolean default false;
            attribute seesModules      : Boolean default false;
        }
    }

    part def EncoderVariant;
    variation part encoderStrategy : EncoderVariant {
        doc /* All three satisfy the same port. The default is fitted on the projected
             * ontology itself: for a single closed vocabulary the corpus *is* the domain,
             * so co-occurrence within FIBO carries more signal than general English --
             * and it costs no model download. */
        variant part tfidfSvd : EncoderVariant {
            attribute kind : String default "tfidf";
            attribute dimension : Integer default 256;
            attribute fitted : Boolean default true;
            attribute requiresArtifact : Boolean default true;
        }
        variant part hashing : EncoderVariant {
            attribute kind : String default "hash";
            attribute fitted : Boolean default false;
            doc /* Deterministic, not semantic. Exercises the plumbing; do not retrieve with it. */
        }
        variant part sentenceTransformer : EncoderVariant {
            attribute kind : String default "sentence-transformers";
            attribute dimension : Integer default 384;
            attribute fitted : Boolean default false;
            doc /* Real paraphrase handling, at the cost of a torch install. */
        }
    }

    // ====================================================================== //
    // 6. Behaviour
    // ====================================================================== //

    action def RunProjection {
        in  options : ProjectionOptions;
        out report  : ProjectionReport;

        action parseSource        { out records : ExtractionRecords; }
        action readTbox           { in records : ExtractionRecords; out classes : NamedClass[0..*]; }
        action stubExternals      { doc /* Materialise referenced-but-undeclared classes. */ }
        action unfoldRestrictions { out edges : RestrictionAxiom[0..*]; }
        action buildIr            { out ir : IntermediateRepresentation; }
        action composeProfiles    { out profiles : ConceptProfile[0..*]; }
        action fitAndEncode       { out vectors : EmbeddingVector[0..*]; }
        action persistEncoder     { doc /* Before load, so a load failure cannot orphan the index. */ }
        action loadGraph          { in ir : IntermediateRepresentation; }
        action declareIndexes     { }
        action verifyRun          { out report : ProjectionReport; }

        // stubExternals precedes unfoldRestrictions on purpose: the loader MATCHes both
        // endpoints, so a filler with no node is an edge that never lands.
        first parseSource then readTbox then stubExternals then unfoldRestrictions
            then buildIr then composeProfiles then fitAndEncode then persistEncoder
            then loadGraph then declareIndexes then verifyRun;
    }

    state def ProjectionRun {
        doc /* A run is a transaction in intent though not in the store: `clearFirst`
             * drops the graph before loading, so a failure between Loading and Indexed
             * leaves a graph that is present but unindexed. Verified is the only state in
             * which the graph should be served. */
        entry; then Idle;

        state Idle;
        state Parsing;
        state Building;
        state Encoding;
        state Loading;
        state Indexing;
        state Verified;
        state Failed;

        transition Idle     then Parsing   accept options : ProjectionOptions;
        transition Parsing  then Building;
        transition Building then Encoding  if options.embed;
        transition Building then Loading   if not options.embed;
        transition Encoding then Loading;
        transition Loading  then Indexing;
        transition Indexing then Verified  if landed == unfolded;
        transition Indexing then Failed    if landed != unfolded;
        transition Parsing  then Failed;
    }

    // ====================================================================== //
    // 7. Allocation to the implementation
    // ====================================================================== //

    package Allocation {
        doc /* Logical component -> the module that realises it. Kept in the model so the
             * two can be checked against each other when either moves. */

        allocate ProjectionController      to "ontology_modeler/lpg/converter.py :: LpgConverter";
        allocate SourceAdapter             to "ontology_modeler/lpg/rdf_source.py :: RdfFileExtractor.load";
        allocate TboxReader                to "ontology_modeler/lpg/rdf_source.py :: classes/taxonomy/object_properties";
        allocate AxiomUnfolder             to "ontology_modeler/lpg/rdf_source.py :: restrictions";
        allocate MetaGraphBuilderComponent to "ontology_modeler/lpg/transform.py :: MetaGraphBuilder";
        allocate ProfileComposer           to "ontology_modeler/lpg/transform.py :: concept_profile";
        allocate VectorEncoder             to "ontology_modeler/lpg/embed.py :: TfidfSvdEmbedder";
        allocate GraphLoader               to "ontology_modeler/lpg/load.py :: FalkorDBExporter";
        allocate IndexManager              to "ontology_modeler/lpg/load.py :: create_*_index";
        allocate EncoderArtifactManager    to "ontology_modeler/lpg/embed.py :: save_embedder/load_embedder";

        allocate FalkorDbInstance          to "infra/falkordb/docker-compose.yml";
        allocate FusekiDataset             to "infra/fuseki/docker-compose.yml";
        allocate ArtifactStore             to "src/Ontology Modeler/artifacts/<graph>.embedder.pkl";
        allocate FiboRepository            to "Ontology Repository/FIBO/fibo";
    }

    // ====================================================================== //
    // 8. FIBO characterisation -- measured, not targeted
    // ====================================================================== //

    part def FiboCharacterisation {
        doc /* One full run over the vendored release. These are the numbers the
             * architecture was shaped by; re-measure them when FIBO is upgraded. */

        attribute filesParsed      : Integer default 299;
        attribute filesFailed      : Integer default 0;
        attribute triples          : Integer default 132939;

        attribute classes          : Integer default 3258;
        attribute externalClasses  : Integer default 253;
        attribute modules          : Integer default 299;

        attribute subclassEdges    : Integer default 4212;
        attribute definedInEdges   : Integer default 3005;
        attribute restrictionEdges : Integer default 2721;
        attribute propertyEdges    : Integer default 560;
        attribute totalEdges       : Integer default 10498;

        attribute relationshipTypes : Integer default 906;
            doc /* One Cypher type per object property. This is an architectural fact with
                 * a downstream cost: an untyped MATCH ()-[r]->() makes the store union 906
                 * edge sets and time out, while the same counts taken per type return in
                 * about two seconds. Any component summarising the graph must enumerate
                 * types rather than scan edges. */

        attribute embeddedProfiles : Integer default 3005;
        attribute vectorDimension  : Integer default 256;
        attribute elapsedSeconds   : Real default 118.0;

        attribute restrictionToPropertyRatio : Real default 4.86;
            doc /* The single number that justifies AxiomUnfolder. */
    }

    // ====================================================================== //
    // 9. Verification
    // ====================================================================== //

    verification def <'V1'> VerifyAxiomCoverage {
        doc /* Compare the unfolder's emitted count with the builder's landed count; they
             * must be equal. DEFECT FOUND: the first implementation unfolded 642
             * restrictions in the FBC module and landed 431. The loader MATCHes both
             * endpoints, and roughly a third of FIBO's restrictions target OMG Commons
             * classes that the offline release never declares. Materialising them as
             * flagged external stubs took coverage to 642/642 and raised domain/range
             * edges from 23 to 37. Nothing looked wrong before the fix. */
        subject run : ProjectionReport;
    }

    verification def <'V2'> VerifyQuantifierDistinction {
        doc /* `p some D` and `p only D` between the same pair must remain two edges.
             * Checked by grouping restriction edges on (source, property, target) and
             * asserting no group silently lost a quantifier.
             *
             * EXECUTED, and vacuous on this corpus: FIBO contains no (source, property,
             * target) triple carrying two different quantifiers, so the case passes
             * without exercising the mechanism. It is kept because the guarantee is a
             * property of the loader rather than of FIBO, and the next ontology projected
             * through it may well rely on the distinction. */
        subject graph : PropertyGraph;
    }

    verification def <'V3'> VerifyIdempotence {
        doc /* Load the same IR three times without clearing; node and edge counts must not
             * move. DEFECT FOUND: edges grew 10,498 -> 10,794 on the second load. The
             * domain/range MERGE pattern omitted `via`, so it matched and rewrote the
             * restriction edge of the same property between the same two classes; the
             * restriction loader then found nothing with via='restriction' and created a
             * fresh edge, and the pair oscillated on every run. Putting `via` in the MERGE
             * pattern fixed it; three consecutive loads are now stable. */
        subject graph : PropertyGraph;
    }

    verification def <'V4'> VerifyOfflineRun {
        doc /* Project with followImports = false and no network; expect 0 failed files and
             * a connected taxonomy with flagged external roots. */
        subject system : FiboProjectionSystemDef;
    }

    verification def <'V5'> VerifyIndexesOperational {
        doc /* After a run, the store reports a VECTOR index on :Class(embedding) with the
             * declared dimension, FULLTEXT on the three text fields, and RANGE on the IRIs,
             * all OPERATIONAL -- and a known term returns itself from both. */
        subject graph : PropertyGraph;
    }

    verification def <'V6'> VerifyRelTypeSanitisation {
        doc /* Every interpolated relationship token matches ^[A-Z][A-Z0-9_]*$, and a
             * hand-crafted property name containing Cypher syntax is refused at load
             * rather than executed. */
        subject system : FiboProjectionSystemDef;
    }

    verification def <'V7'> VerifyEncoderCoherence {
        doc /* The artifact written by a run reloads and reports the dimension the vector
             * index declares (256 == 256, confirmed).
             *
             * Exact self-retrieval is the stronger check and it does NOT hold: querying
             * the vector index with a class's own name returns that class at rank 1 in
             * only 1 case of 3 spot-checked, and 60.8% across a 120-name sample. That is a
             * property of the encoder, not a defect in the artifact plumbing -- TF-IDF/SVD
             * places a short name near its whole sibling family, so 'credit default swap'
             * returns 'multi-name credit default swap' first. Hybrid anchoring is the
             * architectural response; see GraphRagAgent::AnchorRecall. */
        subject system : FiboProjectionSystemDef;
    }

    // ====================================================================== //
    // 10. Traceability
    // ====================================================================== //

    part fiboProjectionSystem : FiboProjectionSystemDef {

        satisfy requirement <'R1'> AxiomFidelity        by unfolder, builder, reader;
        satisfy requirement <'R2'> CitationTraceability by loader;
        satisfy requirement <'R3'> Repeatability        by loader;
        satisfy requirement <'R4'> OfflineOperation     by adapter, reader;
        satisfy requirement <'R5'> Retrievability       by indexer;
        satisfy requirement <'R6'> BulkThroughput       by controller;
        satisfy requirement <'R7'> SourceIndependence   by adapter;
        satisfy requirement <'R8'> InjectionSafety      by loader;
        satisfy requirement <'R9'> EmbeddingCoherence   by artifactMgr, encoder;

        verify requirement <'R1'> by <'V1'>, <'V2'>;
        verify requirement <'R3'> by <'V3'>;
        verify requirement <'R4'> by <'V4'>;
        verify requirement <'R5'> by <'V5'>;
        verify requirement <'R8'> by <'V6'>;
        verify requirement <'R9'> by <'V7'>;

        // Inherited from the function model: the projection this system executes is the
        // same pi, so its invariants hold here too rather than being restated.
        assert constraint iriPreservation : OntologyProjection::IriPreservation;
        assert constraint axiomCoverage   : OntologyProjection::AxiomCoverage;
        assert constraint idempotence     : OntologyProjection::Idempotence;
        assert constraint externalHonesty : OntologyProjection::ExternalHonesty;
    }
}
