/*
 * Semantic Intelligence Platform -- INFORMATION VIEWPOINT.
 * SysML v2 textual notation.
 *
 * What the platform stores, where, who owns it, and the lifecycles of the information
 * items that carry governance: commits and agent proposals. "Everything is RDF": content,
 * history, competency questions, mappings and evidence are named graphs in one dataset,
 * so one backup, one SPARQL and one access model cover all of them.
 */

package SipInformation {

    private import ScalarValues::*;
    private import SipViewpoints::*;

    // ------------------------------------------------------------------ //
    // Named-graph layout (core/layout.py is the single source of truth)
    // ------------------------------------------------------------------ //

    enum def GraphRole {
        doc /* Per project p, graph IRI urn:sip:p:{p}:{role}. */
        enum main;            // stable ontology (TBox + vocabulary)
        enum kg;              // stable instance graph (ABox)
        enum stagingAdd;      // {content}:staging-add  -- proposed additions
        enum stagingDel;      // {content}:staging-del  -- proposed removals
        enum imports;         // imports:{sha1(iri)}     -- materialised imports (derived)
        enum inferred;        // reasoner closure minus asserted (derived)
        enum mappings;        // accepted alignment cells
        enum shapes;          // SHACL shapes
        enum metadata;        // DCAT / VoID description
        enum history;         // cl:Commit records (CHANGELOG vocabulary)
        enum cq;              // competency questions + SPARQL tests
        enum evidence;        // agent evidence beyond the commit record
    }

    enum def Writability {
        enum content;         // written only by ChangeTracker.commit / accept
        enum workflow;        // staging graphs, written only by the tracker
        enum derived;         // written only by ChangeTracker.replace_derived; recomputable
        enum system;          // history -- appended in the same transaction as content
    }

    attribute def NamedGraph {
        attribute role : GraphRole;
        attribute writability : Writability;
        attribute owner : String;
        attribute backedUp : Boolean;
    }

    // ------------------------------------------------------------------ //
    // Information items
    // ------------------------------------------------------------------ //

    item def Quad {
        attribute subject : String;
        attribute predicate : String;
        attribute object : String;
        attribute context : String;
    }
    item def ChangeSet {
        doc /* Protege's List<OWLOntologyChange>, at triple level: the unit of an edit. */
        attribute operation : String;
        attribute parameters : String;
        item additions : Quad[0..*];
        item removals : Quad[0..*];
        item evidence : Evidence[0..1];
    }
    item def Commit {
        doc /* cl:Commit with cl:addedStatement/cl:removedStatement cl:Quadruple,
             * prov:startedAtTime/endedAtTime, prov:wasAssociatedWith, cl:parentCommit,
             * cl:revisionNumber, cl:status; sip:operation, sip:validatedBy, sip:evidence. */
        attribute id : String;
        attribute revision : Integer;
        attribute principal : String;
        attribute isMachine : Boolean;
        attribute status : CommitStatus;
        item delta : ChangeSet;
    }
    enum def CommitStatus { enum committed; enum staged; enum accepted; enum undone; }

    item def Evidence {
        doc /* Attached to every agent proposal (FR-AG-02, QR-AIT-01, QR-REG-01). */
        attribute agent : String;
        attribute run : String;
        attribute model : String;
        attribute promptHash : String[0..1];
        attribute confidence : Real;
        attribute rationale : String;
        attribute onBehalfOf : String;
        attribute aiGenerated : Boolean;
        attribute quote : String[0..1];        // verbatim source span
        attribute charStart : Integer[0..1];
        attribute charEnd : Integer[0..1];
        attribute sourceSha256 : String[0..1];
    }
    item def Proposal {
        attribute operation : String;
        attribute arguments : String;
        attribute critic : String[0..*];      // empty == passed
        item evidence : Evidence;
        attribute commit : String[0..1];
    }
    item def CompetencyQuestion {
        attribute id : String;
        attribute question : String;
        attribute sparql : String;
        attribute expectation : String;       // non-empty | empty | count>=N | ask:true | contains:IRI
    }
    item def AlignmentCell {
        attribute entity1 : String;
        attribute entity2 : String;
        attribute measure : Real;
        attribute relation : String;          // = < > % InstanceOf HasInstance
        attribute mappingProperty : String[0..1];
        attribute status : String[0..1];      // accepted | rejected | error
    }
    item def ProjectRecord {
        attribute name : String;
        attribute baseUri : String;
        attribute model : String;             // RDFS | OWL | SKOS | OntoLex
        attribute lexicalization : String;    // RDFS | SKOS | SKOS-XL | OntoLex
        attribute languages : String[1..*];
        attribute validationEnabled : Boolean;
        attribute llmAllowed : Boolean;
    }
    item def Binding {
        attribute principal : String;
        attribute project : String;
        attribute roles : String[0..*];
        attribute languages : String[0..*];
        attribute group : String[0..1];
    }
    item def Source {
        attribute id : String;
        attribute kind : String;              // document | table | rdf
        attribute sha256 : String;
    }

    // ------------------------------------------------------------------ //
    // Lifecycles
    // ------------------------------------------------------------------ //

    state def CommitLifecycle {
        doc /* Human edit without validation: committed. Machine edit, or validation on:
             * staged -> accepted (applied) | rejected (erased, no trace). Undo/redo are
             * new commits; the target flips undone <-> committed. */
        entry; then building;
        state building;
        state committed;
        state staged;
        state accepted;
        state undone;
        state erased;
        transition direct first building then committed;
        transition propose first building then staged;
        transition accept first staged then accepted;
        transition reject first staged then erased;
        transition undoCommitted first committed then undone;
        transition undoAccepted first accepted then undone;
        transition redo first undone then committed;
    }

    state def ProposalLifecycle {
        entry; then proposed;
        state proposed;
        state criticRejected;
        state submitted;
        state pendingReview;
        state acceptedByHuman;
        state rejectedByHuman;
        transition criticFails first proposed then criticRejected;
        transition criticPasses first proposed then submitted;
        transition staged first submitted then pendingReview;
        transition humanAccepts first pendingReview then acceptedByHuman;
        transition humanRejects first pendingReview then rejectedByHuman;
    }

    state def StageLifecycle {
        doc /* Per lifecycle stage (lifecycle.setStage). Gates: review, publish. */
        entry; then notStarted;
        state notStarted;
        state inProgress;
        state awaitingGate;
        state done;
        transition start first notStarted then inProgress;
        transition finish first inProgress then done;
        transition reachGate first inProgress then awaitingGate;
        transition humanCloses first awaitingGate then done;
    }
}
