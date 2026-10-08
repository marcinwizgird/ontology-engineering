/*
 * Ontology -> Labeled Property Graph projection.
 * SysML v2 (KerML textual notation).
 *
 * Models the projection as what it is: a *function* with a declared domain, a declared
 * codomain, and a set of constraints that say when a run of it is correct. The
 * implementation is ontology_modeler.lpg; every part below names the module that
 * realises it, so the model and the code can be checked against each other.
 *
 * The reason to model this in SysML rather than draw it: the interesting content is not
 * the box-and-arrow flow, which is obvious, but the *invariants* -- what must be true of
 * the output for the projection to be trustworthy. Those are `assert constraint`s here,
 * and they are exactly what a test suite should check.
 */

package OntologyProjection {

    import ScalarValues::*;

    // ---------------------------------------------------------------------- //
    // 1. The domain: what an ontology is, for the purpose of projecting it
    // ---------------------------------------------------------------------- //

    part def Ontology {
        doc /* An RDF/OWL TBox. The source may be a triplestore or a directory of files;
             * the projection does not care, which is why Extraction is a strategy. */
        attribute iri : String;
        part namedClasses : NamedClass[0..*];
        part properties   : ObjectProperty[0..*];
        part axioms       : Axiom[0..*];
        part modules      : OntologyModule[0..*];
    }

    part def NamedClass {
        attribute iri        : String;
        attribute label      : String[0..1];
        attribute definition : String[0..1];
        attribute altLabels  : String[0..*];
        attribute declared   : Boolean;
            doc /* False when the class is only referenced -- FIBO's OMG Commons parents.
                 * Carried through to the LPG as `external` so retrieval can exclude
                 * placeholders from ranked results. */
    }

    part def ObjectProperty {
        attribute iri    : String;
        attribute label  : String[0..1];
        part domain : NamedClass[0..1];
        part range  : NamedClass[0..1];
    }

    abstract part def Axiom;

    part def SubClassOfAxiom :> Axiom {
        part sub   : NamedClass;
        part super : NamedClass;
    }

    part def RestrictionAxiom :> Axiom {
        doc /* `C subClassOf (p some D)`. Anonymous in RDF -- a blank node -- and therefore
             * invisible to any projection that reads only named triples. In FIBO these
             * outnumber declared domain/range pairs roughly five to one, so dropping them
             * yields a taxonomy with almost no cross-links. */
        part onClass     : NamedClass;
        part onProperty  : ObjectProperty;
        part filler      : NamedClass;
        attribute quantifier  : QuantifierKind;
        attribute cardinality : Integer[0..1];
        attribute origin      : AxiomOrigin;
    }

    enum def QuantifierKind { some; only; value; exactly; min; max; }
    enum def AxiomOrigin    { subClassOf; equivalentClass; }

    part def OntologyModule {
        attribute iri  : String;
        attribute name : String;
        attribute path : String[0..1];
    }

    // ---------------------------------------------------------------------- //
    // 2. The codomain: what a labeled property graph is
    // ---------------------------------------------------------------------- //

    part def PropertyGraph {
        attribute graphName : String;
        part classNodes  : ClassNode[0..*];
        part moduleNodes : ModuleNode[0..*];
        part edges       : GraphEdge[0..*];
        part indexes     : GraphIndex[0..*];
    }

    part def ClassNode {
        attribute iri        : String;   // the join key back to RDF, and the citation
        attribute name       : String;
        attribute shortName  : String;
        attribute definition : String;
        attribute altLabels  : String[0..*];
        attribute external   : Boolean;
        attribute moduleIri  : String[0..1];
        attribute embedding  : Real[0..*];
    }

    part def ModuleNode {
        attribute iri  : String;
        attribute name : String;
        attribute path : String[0..1];
    }

    part def GraphEdge {
        attribute relType    : String;   // upper SNAKE_CASE, Cypher-legal
        attribute kind       : EdgeKind;
        attribute via        : String[0..1];
        attribute quantifier : String[0..1];
        part source : ClassNode;
        part target : ClassNode;
    }

    enum def EdgeKind { taxonomy; objectProperty; restriction; definedIn; }

    part def GraphIndex {
        attribute label    : String;
        attribute fields   : String[1..*];
        attribute indexKind : IndexKind;
    }

    enum def IndexKind { range; vector; fulltext; }

    // ---------------------------------------------------------------------- //
    // 3. The projection function
    // ---------------------------------------------------------------------- //

    part def ProjectionFunction {
        doc /* pi : Ontology -> PropertyGraph, realised by ontology_modeler.lpg.converter
             * .LpgConverter. Four stages behind four strategy interfaces, so the source
             * (Fuseki or files) and the encoder (TF-IDF/SVD, hashing, sentence encoder)
             * vary without the rest of the pipeline changing. */

        part extraction     : ExtractionStrategy;      // lpg/extract.py, lpg/rdf_source.py
        part transformation : TransformationStrategy;  // lpg/transform.py
        part embedding      : EmbeddingStrategy;       // lpg/embed.py
        part loading        : LoadingStrategy;         // lpg/load.py
    }

    abstract part def ExtractionStrategy {
        doc /* Ontology -> extraction records. Two realisations: TboxExtractor (SPARQL over
             * Fuseki) and RdfFileExtractor (rdflib over a directory). Only the second can
             * see restrictions and module provenance, because both need the blank-node
             * structure and the file boundary that SPARQL over a union graph has lost. */
    }
    part def SparqlExtraction :> ExtractionStrategy;
    part def FileExtraction   :> ExtractionStrategy;

    abstract part def TransformationStrategy {
        doc /* Records -> a NetworkX MultiDiGraph intermediate representation, plus one
             * Concept Profile Document per class. The IR exists so the projection can be
             * inspected, diffed and tested without a database in the loop. */
    }

    abstract part def EmbeddingStrategy {
        doc /* Concept profile -> vector. A fitted strategy (TF-IDF/SVD) must be persisted
             * with the graph: a query embedded by a differently-fitted basis lands in a
             * different space, and the neighbour scores come back meaningless rather than
             * visibly wrong. See constraint embedderProvenance. */
        attribute dimension : Integer;
        attribute fitted    : Boolean;
    }

    abstract part def LoadingStrategy {
        doc /* IR -> Cypher. MERGE throughout, so re-projection updates in place. */
    }

    // ---------------------------------------------------------------------- //
    // 4. Behaviour
    // ---------------------------------------------------------------------- //

    action def Project {
        in  source : Ontology;
        out graph  : PropertyGraph;

        action extract {
            doc /* Classes, taxonomy, object properties, restrictions, modules. */
            in  source : Ontology;
            out records : ExtractionRecords;
        }

        action transform {
            doc /* Build the IR. Modules first: a DEFINED_IN edge needs both endpoints to
                 * exist. Classes before restrictions, for the same reason. */
            in  records : ExtractionRecords;
            out ir : IntermediateRepresentation;
        }

        action profile {
            doc /* Name, synonyms, definition, superclasses, restriction-derived relations,
                 * module. The relations clause is what separates sibling classes; without
                 * it every agreement in FIBO embeds to roughly the same point. */
            in  ir : IntermediateRepresentation;
            out profiles : ConceptProfile[0..*];
        }

        action embed {
            in  profiles : ConceptProfile[0..*];
            out vectors : EmbeddingVector[0..*];
        }

        action load {
            in  ir : IntermediateRepresentation;
            in  vectors : EmbeddingVector[0..*];
            out graph : PropertyGraph;
        }

        action index {
            doc /* Range on :Class(iri) and :Module(iri); vector on :Class(embedding);
                 * full-text on name, definition, alt_text. The vector index needs the
                 * native vecf32 type -- a plain float array is stored happily and is then
                 * invisible to db.idx.vector.queryNodes. */
            in  graph : PropertyGraph;
            out indexed : PropertyGraph;
        }

        flow extract.records    to transform.records;
        flow transform.ir       to profile.ir;
        flow profile.profiles   to embed.profiles;
        flow transform.ir       to load.ir;
        flow embed.vectors      to load.vectors;
        flow load.graph         to index.graph;
    }

    part def ExtractionRecords;
    part def IntermediateRepresentation;
    part def ConceptProfile     { attribute text : String; }
    part def EmbeddingVector    { attribute values : Real[1..*]; }

    // ---------------------------------------------------------------------- //
    // 5. Correctness constraints -- the part worth modelling
    // ---------------------------------------------------------------------- //

    constraint def IriPreservation {
        doc /* Every class node's IRI is the IRI of the class it came from, unchanged.
             * This is the whole basis of citation: an answer names an IRI, and that IRI
             * resolves in the source ontology. Any renaming scheme breaks verifiability. */
        in source : Ontology;
        in graph  : PropertyGraph;
    }

    constraint def AxiomCoverage {
        doc /* Every subClassOf and every restriction between two named classes appears as
             * an edge. Measured, not assumed: the converter logs unfolded-versus-landed
             * and the two must be equal. They were not, until referenced-but-undeclared
             * classes were materialised as external stubs -- before that a third of FIBO's
             * restrictions were silently dropped at load time, because the loader MATCHes
             * both endpoints. */
        in source : Ontology;
        in graph  : PropertyGraph;
        attribute unfolded : Integer;
        attribute landed   : Integer;
        assert constraint { landed == unfolded }
    }

    constraint def QuantifierDistinction {
        doc /* `p some D` and `p only D` are different axioms and must not collapse into
             * one edge. The quantifier is therefore part of the MERGE pattern, not a
             * property set afterwards. */
        in graph : PropertyGraph;
    }

    constraint def Idempotence {
        doc /* pi(pi(O)) == pi(O): re-projecting updates in place. MERGE everywhere. */
        in graph : PropertyGraph;
    }

    constraint def EmbedderProvenance {
        doc /* The embedder that produced the indexed vectors is persisted with the graph
             * and is the one used to embed queries. Violating this degrades retrieval
             * silently -- scores stay in range and rankings stay plausible. */
        in graph : PropertyGraph;
        attribute embedderArtifact : String;
        assert constraint { embedderArtifact != "" }
    }

    constraint def ExternalHonesty {
        doc /* A class referenced but not declared is present, reachable, and flagged --
             * never presented as defined. Retrieval excludes flagged nodes from ranked
             * results by default; the agent reports them as references. */
        in graph : PropertyGraph;
    }

    part projection : ProjectionFunction {
        assert constraint iriPreservation     : IriPreservation;
        assert constraint axiomCoverage       : AxiomCoverage;
        assert constraint quantifierDistinct  : QuantifierDistinction;
        assert constraint idempotent          : Idempotence;
        assert constraint embedderProvenance  : EmbedderProvenance;
        assert constraint externalHonesty     : ExternalHonesty;
    }
}
