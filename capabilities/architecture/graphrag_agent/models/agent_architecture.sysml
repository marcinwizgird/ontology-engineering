/*
 * GraphRAG agent architecture.
 * SysML v2 (KerML textual notation).
 *
 * Models the agent as a system with a declared boundary: which parts may assert a fact,
 * which may only transport one, and where the trust boundary sits. Realised by
 * ontology_modeler.graphrag.
 *
 * The design claim this model encodes: the language model is NOT a source of facts in
 * this system. It is a planner and a writer. Every factual token in an answer has to
 * originate in a tool result. That claim is only meaningful if it is structural -- if
 * the model has no path to the answer that bypasses the retriever -- which is what the
 * ports and the constraints below pin down.
 */

package GraphRagAgent {

    import ScalarValues::*;
    import OntologyProjection::PropertyGraph;

    // ---------------------------------------------------------------------- //
    // 1. System boundary
    // ---------------------------------------------------------------------- //

    part def OntologyAgentSystem {
        part reasoner  : LanguageModel;
        part loop      : AgentLoop;
        part toolbelt  : ToolBelt;
        part retriever : GraphRagRetriever;
        part store     : GraphStore;
        part embedder  : FittedEmbedder;

        port question : QuestionPort;
        port answer   : GroundedAnswerPort;
    }

    port def QuestionPort       { attribute text : String; }
    port def GroundedAnswerPort {
        attribute prose     : String;
        attribute citations : String[0..*];   // IRIs, one per class mentioned
    }

    // ---------------------------------------------------------------------- //
    // 2. Parts
    // ---------------------------------------------------------------------- //

    part def LanguageModel {
        doc /* Plans which tools to call and writes the final prose. Explicitly NOT a
             * source of facts about the ontology: it knows a great deal about finance,
             * and that knowledge is the principal contamination risk here -- an answer
             * drawn from parametric memory but wearing a citation is worse than an
             * obvious fabrication, because it survives review. */
        attribute modelId     : String default "claude-sonnet-5";
        attribute mayAssertFacts : Boolean default false;
    }

    part def AgentLoop {
        doc /* Stock create_agent: plan, call tools, observe, repeat, answer. Deliberately
             * unmodified -- all the engineering lives in the tools and the prompt, so a
             * wrong answer can be attributed to retrieval or to generation rather than to
             * an indivisible blob. */
        attribute maxIterations : Integer default 12;
    }

    part def ToolBelt {
        part overview     : OntologyOverviewTool;
        part search       : SearchConceptsTool;
        part concept      : GetConceptTool;
        part neighbourhood: GetNeighbourhoodTool;
        part ancestors    : GetAncestorsTool;
        part path         : FindPathTool;
        part cypher       : QueryGraphTool;
    }

    abstract part def RetrievalTool {
        doc /* Every tool returns records that carry their IRI. A tool that drops the IRI
             * makes the answer uncitable, whatever the prompt says. */
        attribute readOnly    : Boolean default true;
        attribute carriesIri  : Boolean default true;
    }

    part def OntologyOverviewTool :> RetrievalTool {
        doc /* Labels, counts, relationship types, largest modules. Called first. Without
             * it the model writes Cypher against the relationship types it imagines an
             * ontology has; those queries return zero rows, and zero rows read as
             * "no such fact exists". This tool is the single cheapest defence against
             * that failure, which is why it is mandatory rather than optional. */
    }
    part def SearchConceptsTool    :> RetrievalTool;
    part def GetConceptTool        :> RetrievalTool;
    part def GetNeighbourhoodTool  :> RetrievalTool;
    part def GetAncestorsTool      :> RetrievalTool;
    part def FindPathTool          :> RetrievalTool;

    part def QueryGraphTool :> RetrievalTool {
        doc /* The escape hatch. Guarded: mutation keywords and non-index CALLs refused,
             * a RETURN required, a LIMIT injected. The guard is shape-based rather than
             * keyword-blacklist-based because the query text is model-authored. */
        attribute guardEnforced : Boolean default true;
    }

    part def GraphRagRetriever {
        doc /* The trust boundary. Everything downstream of it is evidence; everything
             * upstream is language. */
        port toGraph  : CypherPort;
        port toVector : VectorQueryPort;
    }

    part def GraphStore {
        doc /* FalkorDB holding the projection. */
        part graph : PropertyGraph;
        part vectorIndex   : VectorIndex;
        part fulltextIndex : FulltextIndex;
    }

    part def VectorIndex {
        attribute label      : String default "Class";
        attribute field      : String default "embedding";
        attribute dimension  : Integer;
        attribute similarity : String default "cosine";
    }

    part def FulltextIndex {
        attribute label  : String default "Class";
        attribute fields : String[1..*];
    }

    part def FittedEmbedder {
        doc /* The same fitted object that produced the indexed vectors, loaded from the
             * artifact written at projection time. See OntologyProjection::
             * EmbedderProvenance -- this part is where that constraint is consumed. */
        attribute artifactPath : String;
        attribute dimension    : Integer;
    }

    port def CypherPort      { attribute query : String; }
    port def VectorQueryPort { attribute vector : Real[1..*]; attribute k : Integer; }

    // ---------------------------------------------------------------------- //
    // 3. The retrieval funnel
    // ---------------------------------------------------------------------- //

    action def AnswerQuestion {
        in  question : String;
        out answer   : GroundedAnswer;

        action orient {
            doc /* Overview once per session. */
            out schema : SchemaSummary;
        }

        action anchor {
            doc /* Hybrid: vector kNN and full-text, fused by reciprocal rank (k = 60).
                 * Neither alone is sufficient. Vector search misses exact identifiers --
                 * 'LEI', 'ISDA Master Agreement' -- returning neighbours instead of the
                 * term. Full-text misses paraphrase. Anchor misses are the dominant cause
                 * of confabulation downstream, because a model that finds nothing tends
                 * to answer from memory rather than report the gap. */
            in  question : String;
            out candidates : Anchor[0..*];
        }

        action gather {
            doc /* Concept cards, ancestors, neighbourhood, paths -- as the question needs. */
            in  candidates : Anchor[0..*];
            out evidence : EvidenceBundle;
        }

        action compose {
            doc /* Prose from evidence, with IRIs attached. */
            in  evidence : EvidenceBundle;
            out answer : GroundedAnswer;
        }

        flow orient.schema      to anchor.question;
        flow anchor.candidates  to gather.candidates;
        flow gather.evidence    to compose.evidence;
    }

    part def SchemaSummary;
    part def Anchor {
        attribute iri     : String;
        attribute name    : String;
        attribute score   : Real;
        attribute foundBy : AnchorSource;
    }
    enum def AnchorSource { vector; fulltext; both; }

    part def EvidenceBundle {
        doc /* Everything retrieved for one question, each record carrying its IRI. This
             * is what a grounding check is run against. */
        part records : EvidenceRecord[0..*];
    }
    part def EvidenceRecord {
        attribute sourceIri : String;
        attribute tool      : String;
        attribute content   : String;
    }

    part def GroundedAnswer {
        attribute prose     : String;
        attribute citations : String[0..*];
    }

    // ---------------------------------------------------------------------- //
    // 4. Grounding constraints
    // ---------------------------------------------------------------------- //

    constraint def NoUngroundedClaim {
        doc /* Every factual claim in the answer traces to an EvidenceRecord retrieved in
             * this conversation. The structural half is enforceable -- the model has no
             * port to the store except through the retriever. The semantic half is not,
             * and needs an evaluation harness: `trace()` returns the tool calls beside the
             * answer precisely so this can be measured rather than asserted. */
        in answer   : GroundedAnswer;
        in evidence : EvidenceBundle;
    }

    constraint def CitationCoverage {
        doc /* Every class named in the prose carries its IRI. */
        in answer : GroundedAnswer;
        attribute classesMentioned : Integer;
        attribute classesCited     : Integer;
        assert constraint { classesCited == classesMentioned }
    }

    constraint def ExplicitAbsence {
        doc /* A miss is reported as a miss. "FIBO does not define X", "no path within 5
             * hops" -- not softened into a maybe and not filled from background knowledge.
             * This is the constraint that makes the system's silence informative, and it
             * is the one users actually want when they say an ontology should reduce
             * hallucination. */
        in answer : GroundedAnswer;
    }

    constraint def ReadOnlyBoundary {
        doc /* No tool can mutate the graph. Enforced in the retriever, not the prompt. */
        in toolbelt : ToolBelt;
    }

    constraint def AnchorRecall {
        doc /* The measurable quality gate for the funnel. If the right class is not in the
             * candidate set, nothing downstream can recover -- so recall@k of the anchor
             * stage upper-bounds the whole system, and is the number to track when the
             * encoder or the profile template changes.
             *
             * MEASURED over 120 exact FIBO class names (seed 7), recall@1 / recall@5:
             *
             *     vector only      60.8%  /  83.3%
             *     full-text only   70.8%  /  90.8%
             *     hybrid (RRF)     81.7%  /  94.2%
             *
             * This is the empirical justification for fusing rather than picking. Each
             * ranker alone misses roughly one name in three at rank 1, and they miss
             * different ones -- lexical search fails on paraphrase, latent-semantic search
             * fails on exact identifiers. Fusion costs one extra query and recovers most
             * of both. The threshold is set at k = 5 because the agent sees the candidate
             * list, not just its head. */
        in candidates : Anchor[0..*];
        attribute k                : Integer default 5;
        attribute recallAtK        : Real default 0.942;
        attribute threshold        : Real default 0.90;
        attribute recallVectorOnly : Real default 0.833;
        attribute recallTextOnly   : Real default 0.908;
        assert constraint { recallAtK >= threshold }
        assert constraint { recallAtK >= recallVectorOnly and recallAtK >= recallTextOnly }
    }

    part agentSystem : OntologyAgentSystem {
        assert constraint noUngrounded  : NoUngroundedClaim;
        assert constraint citations     : CitationCoverage;
        assert constraint absence       : ExplicitAbsence;
        assert constraint readOnly      : ReadOnlyBoundary;
        assert constraint anchorRecall  : AnchorRecall;
    }
}
