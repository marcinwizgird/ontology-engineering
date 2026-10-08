/*
 * Semantic Intelligence Platform -- CONCURRENCY, DEPLOYMENT and OPERATIONAL viewpoints.
 * SysML v2 textual notation.
 *
 * Concurrency: one write coordinator per dataset (TDB2 is single-writer; the platform
 * serialises writes rather than discovering the constraint), stateless API workers,
 * a separate agent-worker pool so a slow model call never holds a request thread, and
 * reasoning off the write path (classify into memory, swap the derived graph in one
 * short transaction).
 *
 * Deployment: GKE. Fuseki and FalkorDB as StatefulSets on persistent disks, the API and
 * the agent workers as Deployments, an optional JVM reasoner sidecar for OWL 2 DL.
 */

package SipDeployment {

    private import ScalarValues::*;
    private import SipFunctional::*;
    private import SipContext::*;

    // ------------------------------------------------------------------ //
    // Concurrency
    // ------------------------------------------------------------------ //

    part def ProcessGroup {
        attribute replicas : Integer;
        attribute stateful : Boolean;
    }
    part def ApiWorkerPool :> ProcessGroup {
        doc /* uvicorn workers; stateless; horizontally scaled. */
    }
    part def WriteCoordinator :> ProcessGroup {
        doc /* Exactly one per dataset. Owns the ChangeTracker lock; every commit, accept,
             * reject, undo and derived-graph swap is one SPARQL Update request = one TDB2
             * transaction (content delta + history record together). */
    }
    part def AgentWorkerPool :> ProcessGroup {
        doc /* Runs agent loops; model calls are slow and billed; bounded concurrency per
             * project and per model quota. */
    }
    part def ReasonerWorkerPool :> ProcessGroup {
        doc /* owlrl closures and justification searches; CPU-bound; never on the write path. */
    }
    part def ProjectionSync :> ProcessGroup {
        doc /* Subscribes to CHANGES_COMMITTED/ACCEPTED; refreshes the FalkorDB projection. */
    }

    constraint def SingleWriterPerDataset {
        doc /* replicas(WriteCoordinator) == 1 for each Fuseki dataset. */
        in coordinator : WriteCoordinator;
        coordinator.replicas == 1
    }

    state def WriteCoordinatorState {
        entry; then idle;
        state idle;
        state applying;
        state verifying;
        transition receive first idle then applying;
        transition applied first applying then verifying;
        transition done first verifying then idle;
        transition failed first applying then idle;
    }

    // ------------------------------------------------------------------ //
    // Deployment (GKE)
    // ------------------------------------------------------------------ //

    part def ExecutionNode {
        attribute kind : String;              // Deployment | StatefulSet | ManagedService | External
        attribute cpu : String;
        attribute memory : String;
    }
    part def SipApiNode :> ExecutionNode { doc /* Deployment, HPA 2..10 */ }
    part def SipWriterNode :> ExecutionNode { doc /* Deployment, replicas = 1, PodDisruptionBudget */ }
    part def SipAgentNode :> ExecutionNode { doc /* Deployment, HPA on queue depth */ }
    part def ReasonerSidecarNode :> ExecutionNode { doc /* optional JVM: HermiT/ELK for OWL 2 DL */ }
    part def FusekiNode :> ExecutionNode { doc /* StatefulSet, TDB2 on pd-ssd, Lucene text index */ }
    part def FalkorNode :> ExecutionNode { doc /* StatefulSet, Redis module, AOF on pd-ssd */ }
    part def SecretStore :> ExecutionNode { doc /* GCP Secret Manager: API keys, OIDC secrets */ }
    part def ObservabilityNode :> ExecutionNode { doc /* Cloud Logging/Monitoring, OpenTelemetry */ }
    part def AnthropicApi :> ExecutionNode { doc /* External: Messages API, region per policy */ }

    part def GkeCluster {
        part api : SipApiNode;
        part writer : SipWriterNode;
        part agents : SipAgentNode;
        part reasonerSidecar : ReasonerSidecarNode[0..1];
        part fuseki : FusekiNode;
        part falkor : FalkorNode;
        part secrets : SecretStore;
        part observability : ObservabilityNode;
    }

    part deployment {
        part cluster : GkeCluster;
        part anthropic : AnthropicApi;
        part system : SipSystem;

        allocate system.edge to cluster.api;
        allocate system.registry to cluster.api;
        allocate system.pdp to cluster.api;
        allocate system.governance to cluster.api;
        allocate system.authoring to cluster.api;
        allocate system.vocabulary to cluster.api;
        allocate system.search to cluster.api;
        allocate system.tracker to cluster.writer;
        allocate system.store to cluster.fuseki;
        allocate system.reasoning to cluster.agents;
        allocate system.quality to cluster.agents;
        allocate system.alignment to cluster.agents;
        allocate system.io to cluster.agents;
        allocate system.kg to cluster.agents;
        allocate system.runtime to cluster.agents;
        allocate system.conductor to cluster.agents;
        allocate system.gateway to cluster.agents;
        allocate system.events to cluster.writer;
    }

    // ------------------------------------------------------------------ //
    // Operational viewpoint
    // ------------------------------------------------------------------ //

    action def Install {
        doc /* helm install: Fuseki dataset with assembler (TDB2 + text index), FalkorDB,
             * secrets, API/writer/agent Deployments; bootstrap admin; smoke = demo flow. */
    }
    action def BackupRestore {
        doc /* Fuseki /$/backup every 15 min (RPO) to GCS; restore = dataset swap; history
             * and content restore together because they are one dataset (QR-AVL-01). */
    }
    action def Migrate {
        doc /* Import a VocBench 3 project: content graphs + history (CHANGELOG terms kept),
             * roles mapped 1:1 (same nine roles). Import a Protege project: OWL files +
             * catalog-v001.xml -> imports graphs. */
    }
    action def Monitor {
        doc /* SLOs: edit p95 < 500 ms; commit failure rate; staging queue age; agent
             * acceptance rate; LLM spend per project; reasoner duration. */
    }
    action def ControlLlmSpend {
        doc /* per-project token/step budgets (AiPolicy); kill switch per run; daily spend
             * alert; switch SIP_MODEL to 'simulated' to stop all billing instantly. */
    }
    action def RespondToAgentIncident {
        doc /* stop run -> bulk-reject its staged commits by evidence.run -> disable agent in
             * AiPolicy -> review metrics. Nothing to roll back: agents never wrote content. */
    }
}
