/*
 * Ontology Validation Agent (OVA) -- stakeholders, use cases and requirements.
 * SysML v2 (textual notation).
 *
 * The requirement set separates what is DECIDABLE (findings, severities, verdict) is a requirement on a deterministic
 * engine; what is LANGUAGE or JUDGEMENT (explanation, repair, adjudication of heuristic
 * candidates, the report) is a requirement on the agentic layer -- and every requirement
 * on the agentic layer is stated so that it can be measured against the engine.
 *
 * Requirement ids: OVA-F* functional, OVA-T* trust boundary, OVA-Q* quality/non-functional,
 * OVA-E* evaluation and evolution, OVA-P* productisation (commercial operation). Satisfied in OvaArchitecture, verified in
 * OvaDevelopment.
 */

package OvaRequirements {

    import ScalarValues::*;

    // ---------------------------------------------------------------------- //
    // 1. Stakeholders
    // ---------------------------------------------------------------------- //

    part def OntologyEngineer {
        doc /* Submits an ontology and wants to know what is wrong, why, and the smallest
             * edit that fixes it. Reads the report; applies or rejects repair proposals. */
    }
    part def RegistryCurator {
        doc /* Owns the validation policy (severities, waivers, house rules). Wants the verdict
             * to follow the written policy exactly and wants the agent's claims auditable. */
    }
    part def DomainExpert {
        doc /* Adjudicates heuristic findings (is-a overload, synonyms, OntoClean) and labels
             * evaluation data. Their dismissals are the self-evolution signal. */
    }
    part def PlatformOperator {
        doc /* Runs OVA in CI, behind Fuseki and the Playground; cares about cost, latency,
             * determinism and rollback. */
    }
    part def ConsumingSystem {
        doc /* A pipeline (Ontology Modeler, Converter, Enricher, GraphRAG) that calls OVA as
             * a gate before it depends on an ontology version. */
    }

    // ---------------------------------------------------------------------- //
    // 2. Use cases
    // ---------------------------------------------------------------------- //

    use case def ValidateSubmission {
        doc /* Batch validation of one ontology (file, Fuseki named graph, Playground
             * project) against a policy: findings, root causes, verdict, report. The
             * primary use case and the one every metric is defined on. */
        subject ova;
        actor engineer : OntologyEngineer;
        objective { doc /* A verdict that equals the policy applied to the findings, and a
                         * report an engineer can act on. */ }
    }
    use case def GateRelease {
        doc /* CI / pre-publish gate: validate a candidate version against its baseline,
             * return the verdict as an exit status. No LLM call on the critical path
             * unless the policy enables adjudication. */
        subject ova;
        actor consumer : ConsumingSystem;
    }
    use case def InvestigateFinding {
        doc /* "Why is RailVehicle unsatisfiable?" -- an open question answered by a bounded
             * tool-calling agent over the same read-only tool belt, with justifications as
             * evidence. */
        subject ova;
        actor engineer : OntologyEngineer;
    }
    use case def ProposeRepair {
        doc /* For a finding or root cause: a minimal patch (added/removed triples) that the
             * engine re-validates before it is shown. Never applied automatically. */
        subject ova;
        actor engineer : OntologyEngineer;
    }
    use case def AdjudicateHeuristics {
        doc /* Heuristic candidates (MOD-*, HIER-16/17/21/22, ...) labelled true/false
             * positive by the LLM, then confirmed or dismissed by a domain expert. */
        subject ova;
        actor expert : DomainExpert;
    }
    use case def MaintainPolicy {
        doc /* The curator edits severities, waivers, thresholds and the SHACL house-rule
             * pack, and reviews checks proposed by self-evolution before promotion. */
        subject ova;
        actor curator : RegistryCurator;
    }

    // ---------------------------------------------------------------------- //
    // 3. Functional requirements
    // ---------------------------------------------------------------------- //

    requirement def <'OVA-F01'> MultiSourceIntake {
        doc /* Accept Turtle, RDF/XML, JSON-LD, N-Triples, OWL/XML (via owlready2), a Fuseki
             * dataset + named graph, or a Playground project; resolve owl:imports through a
             * catalogue; record a content hash of the asserted graph. */
    }
    requirement def <'OVA-F02'> CatalogueDrivenChecks {
        doc /* Every check is declared in spec/check_catalogue.py with an id, family, method,
             * default severity and applicability profile. The engine runs exactly the
             * applicable catalogue entries, and nothing that is not in the catalogue. */
        attribute catalogueSize : Integer;
    }
    requirement def <'OVA-F03'> ReasoningValidation {
        doc /* Consistency, class satisfiability, inferred equivalences and unintended
             * entailments via OWL 2 RL (owlrl, always available) and, when Java is present,
             * an OWL 2 DL reasoner. The report states which reasoner ran and whether it is
             * complete for the measured profile (RSN-08). */
    }
    requirement def <'OVA-F04'> ShaclValidation {
        doc /* pyshacl validation of (a) supplied shapes against data, (b) shapes derived
             * from the TBox under the closed-world reading, (c) the house-rule shape pack
             * against the ontology itself; plus SHACL-for-SHACL on supplied shapes. */
    }
    requirement def <'OVA-F05'> HierarchyValidation {
        doc /* The HIER and PHIER families: cycles, redundancy, disjointness structure,
             * inherited-restriction conflicts, shape metrics, normalisation, upper-ontology
             * alignment, and the adjudicated ontological checks (is-a overload, OntoClean). */
    }
    requirement def <'OVA-F06'> Justifications {
        doc /* For every inconsistency, unsatisfiable class and inferred equivalence: at least
             * one minimal justification (axiom set), and a root/derived classification of
             * unsatisfiable classes. Justification search runs inside a syntactic locality
             * module (STAR / bottom) of the entailment's signature, never over the whole
             * ontology: such a module provably contains every justification, so restricting
             * the search loses nothing and bounds its cost. */
    }
    requirement def <'OVA-F07'> PolicyVerdict {
        doc /* A verdict in {accept, revise, reject} computed by a pure function of the
             * findings, the measured profile, the declared profile and the policy version.
             * Ordered: reject > revise > accept. Waivers are keyed on MEASURED level. */
    }
    requirement def <'OVA-F08'> StructuredReport {
        doc /* JSON report + RDF report (sh:ValidationReport extended with ova: terms and a
             * prov:Activity for the run) + Markdown for humans. Every finding carries its
             * check id, focus IRI, evidence and, where computed, justification. */
    }
    requirement def <'OVA-F09'> VerifiedRepairs {
        doc /* A repair proposal is shown only after the engine has applied it to a copy and
             * confirmed: the targeted findings disappear, no new blocker/major appears, and
             * the entailment loss outside the targeted axioms is reported. */
    }
    requirement def <'OVA-F10'> VersionDiff {
        doc /* Given a baseline version: removed/renamed entities, lost and new entailments,
             * deprecation discipline (EVO family). */
    }
    requirement def <'OVA-F11'> ToolExposure {
        doc /* Every engine capability is exposed as a narrow, logged tool (LangChain
             * StructuredTool and MCP), JSON in / JSON out, errors returned as text. Tools
             * are grouped into role-scoped profiles (least privilege); every MCP session is
             * bound to its own workspace, so concurrent runs cannot share state. */
    }

    // ---------------------------------------------------------------------- //
    // 4. Trust-boundary requirements (the LLM's place in the system)
    // ---------------------------------------------------------------------- //

    requirement def <'OVA-T01'> DeterministicVerdict {
        doc /* No language-model output can change a decidable field. The critic overrides
             * any model claim about a deterministic finding, the profile, or the verdict.
             * Re-running the engine on the same input + policy gives the same findings. */
    }
    requirement def <'OVA-T02'> NoUnverifiedFinding {
        doc /* A finding exists only if a catalogue check produced it. The model may label a
             * candidate, cluster findings or explain them; it may not add one. Hypotheses
             * from InvestigateFinding become findings only after being compiled to a SPARQL
             * check and executed by the engine. */
    }
    requirement def <'OVA-T03'> AdjudicationCap {
        doc /* A finding whose status rests on LLM adjudication can raise the verdict to
             * at most "revise", never to "reject". */
        attribute maxAdjudicatedSeverity : String default "major";
    }
    requirement def <'OVA-T04'> ReadOnlyTools {
        doc /* No tool mutates the submitted ontology or the store. Repairs are applied to a
             * workspace copy; write-back is a separate, human-approved action. */
    }
    requirement def <'OVA-T05'> Provenance {
        doc /* Every report records engine version, catalogue version, policy version, skill
             * (prompt) version, model ids, and the tool-call log. */
    }

    // ---------------------------------------------------------------------- //
    // 5. Quality requirements
    // ---------------------------------------------------------------------- //

    requirement def <'OVA-Q01'> DependencyLight {
        doc /* The deterministic core runs on rdflib + owlrl + pyshacl + networkx, offline,
             * with no Java and no API key. DL reasoning and LLM features are optional. */
    }
    requirement def <'OVA-Q02'> Throughput {
        doc /* Deterministic validation of the vendored FIBO release (excluding DL reasoning)
             * within budget on a developer machine. */
        attribute measuredSeconds : Real;
        attribute budgetSeconds   : Real default 600.0;
        require constraint { measuredSeconds <= budgetSeconds }
    }
    requirement def <'OVA-Q03'> CostCeiling {
        doc /* Mean LLM cost per validated submission in "validate" mode on the test split. */
        attribute measuredUsd : Real;
        attribute budgetUsd   : Real default 0.25;
        require constraint { measuredUsd <= budgetUsd }
    }
    requirement def <'OVA-Q05'> JustificationThroughput {
        doc /* Per root cause, justification time on the FIBO reference workload (module
             * extraction + expand-shrink, RL backend). */
        attribute p95Seconds    : Real;
        attribute budgetSeconds : Real default 30.0;
        require constraint { p95Seconds <= budgetSeconds }
    }
    requirement def <'OVA-Q04'> Explainability {
        doc /* Every blocker in a report carries a justification or a structural explanation
             * that names the asserted axioms involved. */
    }

    // ---------------------------------------------------------------------- //
    // 6. Evaluation & evolution requirements
    // ---------------------------------------------------------------------- //

    requirement def <'OVA-E01'> MutationRecall {
        doc /* Each deterministic check detects 100% of the mutants of its operator on every
             * seed ontology where the operator applies (mutation kill rate). */
        attribute killRate : Real;
        require constraint { killRate == 1.0 }
    }
    requirement def <'OVA-E02'> CleanSeedPrecision {
        doc /* On certified seed ontologies, no finding outside the certified baseline
             * (zero new false positives per deterministic check). */
    }
    requirement def <'OVA-E03'> ReferenceConformance {
        doc /* The engine passes the Reference Conformance Suite: (a) the applicable W3C
             * SHACL Core test cases, (b) the OWL 2 RL consistency/inconsistency test cases
             * (and the DL ones when the DL backend is enabled), (c) the curated golden
             * corpus of ontologies with curator-signed expected findings, and (d) agrees
             * with the reference oracles named per family (ROBOT report, HermiT, qSKOS,
             * OOPS!) on the overlapping checks, every disagreement triaged and recorded. */
        attribute w3cPassRate    : Real;
        attribute goldenRecall   : Real;
        attribute goldenPrecision : Real;
        require constraint { w3cPassRate == 1.0 }
        require constraint { goldenRecall == 1.0 and goldenPrecision == 1.0 }
    }
    requirement def <'OVA-E04'> HonestImprovement {
        doc /* An optimised program is reported on a held-out test split the optimiser never
             * saw, with n, cost and run-to-run noise; a gain smaller than the noise is
             * reported as no gain. */
    }
    requirement def <'OVA-E05'> GatedEvolution {
        doc /* A new skill version, threshold or check is promoted only if it beats the
             * current one by min_gain on a holdout disjoint from the data it was mined
             * from, passes the regression suite, and (for checks) is approved by a curator.
             * A no-op control candidate must be rejected. */
    }
    requirement def <'OVA-E07'> NonCircularValidation {
        doc /* A synthesised check and the mutation operator synthesised with it cannot
             * certify each other. Promotion requires evidence that does not depend on the
             * pair: (a) recall on expert-confirmed cases held out from synthesis; (b) blind
             * expert confirmation that a sample of the operator's mutants exhibit the defect;
             * (c) a non-vacuous, localised diff of every mutant (VersionDiffer), and for
             * semantic families a change in the entailment closure; (d) the operator is
             * generated independently of the check (from the defect description, without
             * seeing the check); (e) curator review of the operator's logic as well as the
             * rule's. Kill rate 1.0 is necessary, never sufficient. */
    }
    requirement def <'OVA-E06'> ImmutableCore {
        doc /* Self-evolution may add checks, shapes, demos and instructions; it may not
             * modify or remove an existing deterministic check, the critic, the policy
             * function, the scorer or the gate. */
    }

    // ---------------------------------------------------------------------- //
    // 7. Productisation requirements (commercial operation)
    // ---------------------------------------------------------------------- //

    requirement def <'OVA-P01'> TenantIsolation {
        doc /* Every run executes in a tenant context: workspaces, run store, experience
             * buffer, policies and skill versions are partitioned per tenant. No data,
             * demonstration or learned artefact crosses tenants unless the tenant opts in
             * to a shared improvement pool. */
    }
    requirement def <'OVA-P02'> LlmDataGovernance {
        doc /* LLM features are opt-in per tenant and per policy. Ontology content leaves the
             * process only through the LlmGateway, which enforces: provider allow-list,
             * zero-data-retention endpoints, a redaction mode (opaque IRIs, labels only for
             * the entities in the candidate), per-run token and USD budgets, and a log of
             * exactly what was sent. With LLM features off, every mode still completes. */
    }
    requirement def <'OVA-P03'> SecureIngestion {
        doc /* Parsers run with external-entity resolution disabled (RDF/XML XXE), import
             * fetching is off by default and limited to an allow-list when on (no SSRF),
             * input size/triple/time limits are enforced, SPARQL is guarded (no update, no
             * SERVICE, LIMIT injected), and LLM-produced patches and queries are treated as
             * untrusted input. */
    }
    requirement def <'OVA-P04'> LicenceCompliance {
        doc /* Every distributed dependency has a licence compatible with commercial
             * distribution and is listed in an SBOM. AGPL components (Pellet, Openllet) are
             * excluded from the distribution; owlready2's bundled Pellet jar is stripped.
             * Third-party ontologies used for evaluation are used within their licences. */
    }
    requirement def <'OVA-P05'> ServiceInterface {
        doc /* A versioned REST API (OpenAPI) with asynchronous jobs for long runs, webhooks
             * on completion, idempotent submission by content hash, and a stable,
             * semver-versioned report schema. CLI and MCP are thin clients over the same
             * service layer. */
    }
    requirement def <'OVA-P06'> Observability {
        doc /* OpenTelemetry traces per run (one span per family, tool call and LLM call),
             * metrics (latency, findings by check, critic corrections, cost, error rate)
             * and structured logs; per-tenant dashboards and SLO alerts. */
    }
    requirement def <'OVA-P07'> AuditTrail {
        doc /* An immutable audit record per run and per promotion: who submitted, which
             * versions (engine, catalogue, policy, skills, models) produced the verdict,
             * who approved a policy change or a promoted check. Reports are reproducible
             * from the audit record. */
    }
    requirement def <'OVA-P08'> Scalability {
        doc /* Ontologies beyond in-memory comfort (>= 10M triples) are validated by pushing
             * SPARQL-based families down to the store (Fuseki) and partitioning reasoning
             * by module; runs are horizontally scalable workers behind a job queue. */
        attribute maxTriples : Integer default 10000000;
    }
    requirement def <'OVA-P09'> ServiceLevels {
        doc /* Published SLOs per mode: gate p95 latency for ontologies <= 100k triples,
             * validate p95, availability, and maximum LLM cost per run under each plan. */
        attribute gateP95Seconds : Real default 60.0;
        attribute availability   : Real default 0.995;
    }
}
