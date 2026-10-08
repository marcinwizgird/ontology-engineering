/*
 * Semantic Intelligence Platform -- behaviour shared by the Functional and Concurrency
 * viewpoints: the end-to-end construction process, the guarded operation call, the agent
 * loop, and Protege's derived reasoner status.
 */

package SipBehaviour {

    private import ScalarValues::*;
    private import SipInformation::*;

    // ------------------------------------------------------------------ //
    // The guarded operation call (Platform.call)
    // ------------------------------------------------------------------ //

    action def CallOperation {
        doc /* resolve principal -> resolve %resource_role% -> PDP -> run -> commit/stage. */
        in item request : ChangeSet;
        out item result : Commit[0..1];
        action resolvePrincipal;
        action resolveRole;
        action authorize;
        action execute;
        action commitOrStage;
        first resolvePrincipal then resolveRole;
        first resolveRole then authorize;
        first authorize then execute;
        first execute then commitOrStage;
    }

    // ------------------------------------------------------------------ //
    // The agent loop (agents/base.py)
    // ------------------------------------------------------------------ //

    action def AgentLoop {
        doc /* Every agent, every stage: the model only proposes; deterministic stages decide. */
        out item proposals : Proposal[0..*];
        action plan { doc /* read context through guarded read operations */ }
        action checkPolicy { doc /* AI policy, budgets, kill switch -- before any model call */ }
        action propose { doc /* complete_json(task, system, prompt, schema) */ }
        action criticise { doc /* deterministic: quotes verbatim, Manchester parses, reasoner
                                * finds no new unsatisfiability, mapping validates, SPARQL parses */ }
        action submit { doc /* Platform.call as machine principal -> staged commit + evidence */ }
        first plan then checkPolicy;
        first checkPolicy then propose;
        first propose then criticise;
        first criticise then submit;
    }

    // ------------------------------------------------------------------ //
    // End to end
    // ------------------------------------------------------------------ //

    action def ConstructKnowledge {
        doc /* scope -> acquire -> model -> validate -> review || populate -> reason -> publish
             * || consume. '||' = human gate (lifecycle.setStage <gate> done by a human). */
        action scope : AgentLoop { doc /* RequirementsAgent */ }
        action acquire : AgentLoop { doc /* ExtractionAgent per document */ }
        action model : AgentLoop { doc /* ModelingCopilot, VocabularyAgent, AlignmentAgent */ }
        action validate : AgentLoop { doc /* QualityAgent on the staged preview */ }
        action review { doc /* StewardAgent summarises; validators accept/reject */ }
        action reviewGate { doc /* human closes review */ }
        action populate : AgentLoop { doc /* KnowledgeGraphBuilder per table */ }
        action reason { doc /* classify + materialise inferred */ }
        action publish { doc /* release gate: consistent, no blocker, CQs pass */ }
        action publishGate { doc /* human closes publish */ }
        action consume : AgentLoop { doc /* AssistantAgent; feedback opens new scope items */ }
        first scope then acquire;
        first acquire then model;
        first model then validate;
        first validate then review;
        first review then reviewGate;
        first reviewGate then populate;
        first populate then reason;
        first reason then publish;
        first publish then publishGate;
        first publishGate then consume;
    }

    // ------------------------------------------------------------------ //
    // Protege ReasonerStatus -- derived, never stored
    // ------------------------------------------------------------------ //

    state def ReasonerStatus {
        entry; then noReasonerFactoryChosen;
        state noReasonerFactoryChosen;
        state reasonerNotInitialized;
        state initializationInProgress;
        state initialized;
        state inconsistent;
        state outOfSync;
        transition select first noReasonerFactoryChosen then reasonerNotInitialized;
        transition start first reasonerNotInitialized then initializationInProgress;
        transition classifiedOk first initializationInProgress then initialized;
        transition classifiedBad first initializationInProgress then inconsistent;
        transition edit first initialized then outOfSync;
        transition sync first outOfSync then initializationInProgress;
        transition resync first inconsistent then initializationInProgress;
    }
}
