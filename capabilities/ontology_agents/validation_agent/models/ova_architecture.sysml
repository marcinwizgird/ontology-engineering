/*
 * Ontology Validation Agent (OVA) -- logical architecture.
 * SysML v2 (textual notation).
 *
 * The design claim this model encodes: "tools measure, the model interprets". The
 * deterministic engine is the only source of findings
 * and the only author of the verdict. The language model plans the run, adjudicates
 * heuristic candidates, explains root causes, proposes repairs and writes the report --
 * and each of those outputs passes back through a deterministic stage (critic, repair
 * verifier) before anyone sees it. The ports below make that structural: the model has
 * no path to the report that bypasses the critic.
 */

package OvaArchitecture {

    import ScalarValues::*;
    import OvaRequirements::*;

    // ---------------------------------------------------------------------- //
    // 1. System boundary
    // ---------------------------------------------------------------------- //

    part def OntologyValidationAgent {
        part platform     : PlatformServices;
        part interfaces   : InterfaceLayer;
        part orchestrator : Orchestrator;
        part workspace    : ValidationWorkspace;
        part toolbelt     : ToolBelt;
        part engine       : ValidationEngine;
        part cognition    : AgenticLayer;
        part critic       : Critic;
        part store        : RunStore;

        port submission : SubmissionPort;
        port policy     : PolicyPort;
        port report     : ReportPort;
        port feedback   : FeedbackPort;
    }

    port def SubmissionPort {
        attribute source      : String;     // file path | fuseki://dataset/graph | playground://project
        attribute declared    : String;     // declared spectrum level / profile
        attribute baseline    : String[0..1];
        attribute shapes      : String[0..*];
        attribute cqs         : String[0..*];
        attribute mode        : RunMode;
    }
    port def PolicyPort {
        attribute policyVersion : String;
        attribute severityOverrides : String[0..*];
        attribute waivers       : String[0..*];
        attribute housePack     : String[0..1];
    }
    port def ReportPort {
        attribute verdict    : Verdict;
        attribute jsonReport : String;
        attribute rdfReport  : String;
        attribute markdown   : String;
    }
    port def FeedbackPort {
        doc /* Expert confirm/dismiss on findings and repair accept/reject. The only input
             * the self-evolution loop learns from in production. */
        attribute findingId : String;
        attribute label     : String;
    }

    enum def RunMode { validate; gate; investigate; repair; diff; }
    enum def Verdict { accept; revise; reject; }
    enum def Severity { blocker; major; minor; info; }
    enum def FindingStatus { confirmed; candidate; adjudicatedTrue; adjudicatedFalse; waived; }

    // ---------------------------------------------------------------------- //
    // 2. Interface layer
    // ---------------------------------------------------------------------- //

    part def InterfaceLayer {
        part api        : RestApi;
        part cli        : Cli;
        part mcpServer  : McpServer;
        part fuseki     : FusekiConnector;
        part playground : PlaygroundConnector;
    }
    part def RestApi {
        doc /* Versioned OpenAPI service. POST /runs (idempotent by content hash + policy
             * version) returns a job; GET /runs/{id} returns status and report; webhooks on
             * completion. CLI and MCP are thin clients of the same service layer. */
        attribute apiVersion    : String;
        attribute reportSchema  : String;   // semver
    }
    part def Cli {
        doc /* `python -m validation_agent validate|gate|diff|repair|investigate`. `gate`
             * exits 0/1/2 for accept/revise/reject so CI can consume it. */
    }
    part def McpServer {
        doc /* External tool interface for other agents (Ontology Modeler, GraphRAG agent,
             * Claude Code). Stateless and horizontally scaled; every MCP session is bound
             * to its own ValidationWorkspace (keyed by tenant + run id), so concurrent
             * sessions cannot collide. Deployed as separate endpoints per ToolProfile
             * (least privilege) rather than one server exposing everything. OVA's own DSPy
             * modules call the ToolBelt in-process and do not go through MCP. */
        attribute sessionScopedWorkspace : Boolean default true;
    }
    enum def ToolProfile {
        doc /* readonlyInspect: load, profile, describe, hierarchy, sparql, catalogue.
             * validate: + runFamily, runCheck, reason, shacl, applyPolicy.
             * diagnose: + justify, rootCause (expensive tools, budgeted).
             * repair: + verifyPatch. Each DSPy module and each external client gets the
             * smallest profile it needs: CheckPlanner readonlyInspect; Investigator
             * diagnose; RepairProposer repair. */
        readonlyInspect; validate; diagnose; repair;
    }
    part def FusekiConnector {
        doc /* Reuses ontology_modeler.fuseki to read a named graph and, on explicit
             * approval, write the RDF report to urn:ova:run:<id>. Never writes the
             * ontology graph. */
    }
    part def PlaygroundConnector {
        doc /* Reuses ontology_modeler.playground projections so Playground edits can be
             * validated before the safe-merge write-back. */
    }


    // ---------------------------------------------------------------------- //
    // 2b. Platform services (commercial operation)
    // ---------------------------------------------------------------------- //

    part def PlatformServices {
        part tenancy   : TenantContext;
        part jobs      : JobQueue;
        part gateway   : LlmGateway;
        part guards    : SecurityGuards;
        part telemetry : Observability;
        part audit     : AuditLog;
        part pushdown  : StorePushdown;
    }
    part def TenantContext {
        doc /* Carried by every request and every workspace. Partitions run store, experience
             * buffer, policies and skill versions. Cross-tenant learning only via an
             * explicit opt-in shared pool. */
        attribute tenantId        : String;
        attribute llmEnabled      : Boolean default false;
        attribute sharedLearning  : Boolean default false;
    }
    part def JobQueue {
        doc /* Asynchronous runs on horizontally scaled stateless workers; per-tenant
             * concurrency and budget quotas. */
    }
    part def LlmGateway {
        doc /* The ONLY egress for ontology content. Provider allow-list, zero-retention
             * endpoints, redaction mode (opaque IRIs; labels only for entities in the
             * current candidate), per-run token/USD budget, payload log. A denied call
             * degrades the step to its deterministic template, never fails the run. */
        attribute redaction : Boolean default true;
        attribute maxUsdPerRun : Real;
    }
    part def SecurityGuards {
        doc /* XXE-safe parsers, import fetching off by default (allow-list when on), size /
             * triple / time limits, SPARQL guard, LLM-produced patches and queries parsed
             * and validated as untrusted input before use. */
    }
    part def Observability {
        doc /* OpenTelemetry: one span per family, tool call and LLM call; metrics for
             * latency, findings by check, critic corrections, cost, errors; SLO alerts. */
    }
    part def AuditLog {
        doc /* Append-only record per run and per promotion: submitter, versions (engine,
             * catalogue, policy, skills, models), approvals. Sufficient to reproduce a
             * report byte-for-byte. */
    }
    part def StorePushdown {
        doc /* For large graphs: SPARQL-based families executed in Fuseki rather than in
             * memory; reasoning partitioned by module (locality-based modules). */
        attribute inMemoryTripleLimit : Integer default 2000000;
    }

    // ---------------------------------------------------------------------- //
    // 3. Workspace and tool belt
    // ---------------------------------------------------------------------- //

    part def ValidationWorkspace {
        doc /* The state ONE run works on, inside one tenant context. Isolation, one
             * trajectory per run, reproducibility: a fresh workspace starts empty. */
        attribute asserted     : String;   // rdflib Graph of the submission
        attribute importsClosure : String;
        attribute inferred     : String;   // reasoner closure, computed lazily, cached
        attribute shapesGraph  : String[0..1];
        attribute baselineGraph : String[0..1];
        attribute contentHash  : String;
        part callLog  : ToolCallLog;
        part findings : FindingStore;
    }
    part def ToolCallLog {
        doc /* name, args, ok, seconds, result_chars, error -- the trajectory. Read by the
             * cost report, the MDP replay and the experience buffer. */
    }
    part def FindingStore {
        part items : Finding[0..*];
    }

    part def ToolBelt {
        doc /* Narrow, read-only, logged tools. Descriptions say WHEN to call. JSON in/out;
             * errors as "ERROR: ..." text. */
        part load        : LoadOntologyTool;
        part profile     : ProfileTool;
        part runFamily   : RunCheckFamilyTool;
        part runCheck    : RunCheckTool;
        part reason      : ReasonTool;
        part shacl       : ShaclTool;
        part justify     : JustifyTool;
        part rootCause   : RootCauseTool;
        part describe    : DescribeEntityTool;
        part hierarchy   : HierarchyNeighbourhoodTool;
        part sparql      : SparqlSelectTool;
        part verifyPatch : VerifyPatchTool;
        part catalogue   : CheckCatalogueTool;
        part policyTool  : ApplyPolicyTool;
    }
    abstract part def EngineTool {
        attribute readOnly : Boolean default true;
        attribute logged   : Boolean default true;
        attribute costClass : CostClass;
    }
    enum def CostClass { cheap; moderate; expensive; }

    part def LoadOntologyTool          :> EngineTool;
    part def ProfileTool               :> EngineTool {
        doc /* Spectrum level, OWL 2 profile, DL expressivity, size. Call first: the planner
             * chooses families and reasoner from it. */
    }
    part def RunCheckFamilyTool        :> EngineTool;
    part def RunCheckTool              :> EngineTool;
    part def ReasonTool                :> EngineTool {
        doc /* backend = rl | dl. DL is costClass expensive and Java-gated. */
    }
    part def ShaclTool                 :> EngineTool;
    part def JustifyTool               :> EngineTool {
        doc /* Minimal justification for one entailment. Expensive: call per root cause,
             * not per finding. */
    }
    part def RootCauseTool             :> EngineTool;
    part def DescribeEntityTool        :> EngineTool;
    part def HierarchyNeighbourhoodTool :> EngineTool;
    part def SparqlSelectTool          :> EngineTool {
        doc /* Guarded: SELECT/ASK only, LIMIT injected, no SERVICE. */
    }
    part def VerifyPatchTool           :> EngineTool {
        doc /* Applies a patch to a COPY of the workspace graph and re-runs the affected
             * checks plus a semantic diff. The only route by which a repair is accepted. */
    }
    part def CheckCatalogueTool        :> EngineTool;
    part def ApplyPolicyTool           :> EngineTool;

    // ---------------------------------------------------------------------- //
    // 4. Deterministic validation engine
    // ---------------------------------------------------------------------- //

    part def ValidationEngine {
        doc /* Pure Python, offline, deterministic. Satisfies every decidable requirement. */
        part loader     : Loader;
        part profiler   : Profiler;
        part registry   : CheckRegistry;
        part structural : StructuralChecker;
        part reasoning  : ReasoningEngine;
        part shaclEng   : ShaclEngine;
        part lexical    : LexicalChecker;
        part differ     : VersionDiffer;
        part axioms     : AxiomIndex;
        part modules    : ModuleExtractor;
        part justifier  : JustificationEngine;
        part rootCause  : RootCauseAnalyser;
        part aggregator : FindingAggregator;
        part policy     : PolicyEngine;
        part repairVerifier : RepairVerifier;
        part reporter   : ReportBuilder;
    }

    part def Loader {
        doc /* Parse, sniff format, resolve imports via an XML catalogue / local mirror,
             * normalise blank nodes, hash. Produces SYN-* and DECL-07 findings itself. */
    }
    part def Profiler {
        doc /* Spectrum classifier (vocabulary -> taxonomy -> thesaurus -> formal ontology), OWL 2 profile membership, expressivity
             * letters, size metrics. METRIC-* and DL-08. */
    }
    part def CheckRegistry {
        doc /* Loads spec/check_catalogue.py; maps check id -> detector; filters by profile
             * and policy; versioned as catalogueVersion. Additive-only at runtime. */
        attribute catalogueVersion : String;
    }
    part def StructuralChecker {
        doc /* SPARQL and networkx detectors: DECL, DL, HIER, PHIER, PROP, SKOS, META, ABOX,
             * CQ execution. Most of the catalogue. */
    }
    part def ReasoningEngine {
        doc /* RSN-* and the reasoner-backed HIER/PHIER/ABOX checks. */
        variation part backend : ReasonerBackend {
            variant part rl : Owl2RlBackend;
            variant part dl : Owl2DlBackend;
        }
        attribute timeoutSeconds : Integer default 120;
    }
    part def ReasonerBackend {
        attribute complete : Boolean;
    }
    part def Owl2RlBackend :> ReasonerBackend {
        doc /* owlrl DeductiveClosure(OWLRL_Semantics). Always available. Sound; complete only
             * for OWL 2 RL ontologies -- RSN-08 says so in the report otherwise. Unsat
             * detection via rdfs:subClassOf owl:Nothing and owl:Nothing membership. */
    }
    part def Owl2DlBackend :> ReasonerBackend {
        doc /* owlready2 sync_reasoner (HermiT) or sync_reasoner_pellet. Requires Java;
             * selected by the planner when expressivity is outside RL and budget allows. */
    }
    part def ShaclEngine {
        doc /* pyshacl. Three graphs: supplied shapes, TBox-derived CWA shapes, house-rule
             * pack. Maps sh:ValidationResult -> Finding with SHC-* ids. */
        part shapeDeriver : TboxShapeDeriver;
    }
    part def TboxShapeDeriver {
        doc /* domain/range -> sh:class, functional -> sh:maxCount 1, cardinality ->
             * min/maxCount, someValuesFrom -> qualified minCount 1. */
    }
    part def LexicalChecker {
        doc /* Deterministic candidate generators for LEX-*, MOD-*, HIER-16/17/22, PROP-06:
             * tokenisation, head-noun extraction, lemma rules, cue lexicons. Emits
             * status=candidate when the check is adjudicated. */
    }
    part def VersionDiffer {
        doc /* Asserted and entailed diff against a baseline: EVO-*, META-04. */
    }
    part def AxiomIndex {
        doc /* Axiom-level view of the triple graph (OWL 2 mapping to structural axioms,
             * each with a stable id, its signature and its source triples). Locality,
             * justifications, repairs and reports all address axioms, not triples. */
    }
    part def ModuleExtractor {
        doc /* Syntactic locality-based modules: bottom-, top- and STAR-modules (iterated
             * bottom/top to a fixpoint) for a signature. For an entailment over signature S,
             * every justification lies inside the module for S, so the module is a lossless
             * search space -- typically dozens of axioms instead of hundreds of thousands.
             * Also used by RepairVerifier (re-check only the patch's module) and by
             * StorePushdown (module-partitioned reasoning). Differentially tested against
             * ROBOT extract --method STAR. */
        attribute defaultType : String default "STAR";
    }
    part def JustificationEngine {
        doc /* Pipeline per root entailment: (1) signature of the entailment (class C for
             * C subClassOf Nothing; the clash individuals and their types for
             * inconsistency); (2) ModuleExtractor -> STAR module M; (3) black-box
             * expand-shrink over M only, RL backend (DL when available); (4) further
             * justifications by hitting-set tree over M, up to maxJustifications. Memoised
             * by (module hash, entailment). Reasoner-independent, and bounded by module
             * size rather than ontology size. */
        attribute maxJustifications : Integer default 3;
        attribute maxModuleAxioms   : Integer default 5000;
    }
    part def RootCauseAnalyser {
        doc /* Root vs derived unsatisfiable classes; groups findings sharing a
             * justification axiom into one RootCause. Turns 40 findings into 2 causes. */
    }
    part def FindingAggregator {
        doc /* De-duplicates (HIER-05 + RSN-02 on the same class), attaches justifications,
             * applies status lifecycle candidate -> adjudicated* -> waived. */
    }
    part def PolicyEngine {
        doc /* Pure function verdict(findings, measured, declared, policy). Waivers keyed on
             * measured level (W1). Precedence reject > revise > accept. Applies the
             * adjudication cap. Identical code serves the critic and the MDP reward. */
        attribute policyVersion : String;
    }
    part def RepairVerifier {
        doc /* Apply patch to copy -> re-run affected families -> diff findings and
             * entailments -> RepairVerdict (fixes, regressions, entailment loss). */
    }
    part def ReportBuilder {
        doc /* JSON (schema in SPECIFICATION.md), RDF (sh:ValidationReport + ova: + PROV-O),
             * Markdown. The Markdown prose slot is filled by the ReportWriter or a template. */
    }

    // ---------------------------------------------------------------------- //
    // 5. Agentic layer (DSPy modules)
    // ---------------------------------------------------------------------- //

    part def AgenticLayer {
        doc /* Each part is one DSPy module with one signature whose instruction is an
             * optimisable, versioned parameter (a Skill). */
        part model        : LanguageModel[1..*];
        part planner      : CheckPlanner;
        part adjudicator  : FindingAdjudicator;
        part explainer    : RootCauseExplainer;
        part repairer     : RepairProposer;
        part writer       : ReportWriter;
        part investigator : Investigator;
        part judge        : ReportJudge;
    }

    part def LanguageModel {
        doc /* Interprets and writes. mayAssertFindings is false by construction: it has no
             * port into the FindingStore except through the critic. */
        attribute modelId           : String;
        attribute mayAssertFindings : Boolean default false;
        attribute egressOnlyViaGateway : Boolean default true;
    }
    abstract part def SkillModule {
        attribute skillName    : String;
        attribute skillVersion : Integer;
        attribute defaultModel : String;
    }
    part def CheckPlanner :> SkillModule {
        doc /* profile + purpose + budget -> families, reasoner backend, justification
             * budget. An MDP over evidence costs: which expensive evidence is worth
             * buying. A deterministic default plan always exists; the planner may
             * only ADD families or upgrade the backend, never drop a policy-required one. */
        attribute defaultModel : String default "claude-haiku-4-5";
    }
    part def FindingAdjudicator :> SkillModule {
        doc /* (candidate, entity card, neighbourhood) -> label {true, false, unsure},
             * confidence, rationale. Batched per check. 'unsure' routes to a human. */
        attribute defaultModel : String default "claude-haiku-4-5";
    }
    part def RootCauseExplainer :> SkillModule {
        doc /* (root cause, justification axioms in Manchester syntax) -> plain-language
             * explanation naming the conflicting modelling decisions. */
        attribute defaultModel : String default "claude-sonnet-5";
    }
    part def RepairProposer :> SkillModule {
        doc /* (root cause, justification, policy, prior attempts) -> up to k candidate
             * patches, each a set of axioms to add/remove with intent. Wrapped in a
             * verifier-driven refinement loop: every candidate goes to VerifyPatch; if none
             * passes, the verifier's diagnostics (targets still present, new findings,
             * entailment loss) are fed back as prior_attempts and the proposer retries, up
             * to maxAttempts. DSPy 3 has no dspy.Assert/Suggest; the loop is a custom
             * module (dspy.Refine with the repair score as reward_fn is the simpler
             * variant, but it feeds back generated advice, not the engine's diagnostics).
             * Only verified patches are reported, ranked by fewest axioms changed. GEPA
             * later optimises the inner predictor's instruction; the metric charges for
             * attempts. */
        attribute defaultModel : String default "claude-sonnet-5";
        attribute k : Integer default 3;
        attribute maxAttempts : Integer default 3;
    }
    part def ReportWriter :> SkillModule {
        doc /* Critic-checked structured result -> report prose. Grounded: every entity named
             * must appear in a finding. */
        attribute defaultModel : String default "claude-sonnet-5";
    }
    part def Investigator :> SkillModule {
        doc /* Bounded tool-calling loop over the read-only ToolBelt for open questions.
             * Used only where the order of work depends on intermediate results. */
        attribute maxSteps : Integer default 20;
        attribute defaultModel : String default "claude-sonnet-5";
    }
    part def ReportJudge :> SkillModule {
        doc /* LLM-as-judge for report quality. Validated against human labels (agreement,
             * Cohen's kappa) before its scores are used for optimisation. */
        attribute minKappa : Real default 0.6;
    }

    part def Critic {
        doc /* Deterministic verification stage between cognition and the report. Overrides
             * any model statement about a decidable field (finding set, severity, profile,
             * verdict), strips entities not in the evidence from prose, records one
             * human-readable correction per override. Its correction count is a metric. */
        port fromCognition : CognitionOutputPort;
        port toReport      : CheckedResultPort;
    }
    port def CognitionOutputPort { attribute payload : String; }
    port def CheckedResultPort   { attribute payload : String; attribute corrections : String[0..*]; }

    part def Orchestrator {
        doc /* Fixed pipeline by default (networkx DAG of steps, each state -> state, each
             * also exposed as a tool -- project convention). The Investigator loop is a
             * separate mode, not the default path. */
        attribute mode : RunMode;
    }

    part def RunStore {
        doc /* Run records (report + log + versions), the experience buffer, skill versions,
             * evaluation runs. Files under artifacts/; optionally a Fuseki graph. */
    }

    // ---------------------------------------------------------------------- //
    // 6. Information model
    // ---------------------------------------------------------------------- //

    part def Finding {
        attribute findingId  : String;
        attribute checkId    : String;
        attribute severity   : Severity;
        attribute status     : FindingStatus;
        attribute focus      : String;          // IRI
        attribute related    : String[0..*];    // IRIs
        attribute message    : String;
        attribute evidence   : String;          // triples / rows, serialised
        attribute justification : String[0..*]; // axiom ids
        attribute rootCause  : String[0..1];
        attribute adjudication : String[0..1];  // label, confidence, rationale, skill version
        attribute fixHint    : String[0..1];
    }
    part def RootCause {
        attribute rootId    : String;
        attribute axioms    : String[1..*];
        attribute findings  : String[1..*];
    }
    part def RepairProposal {
        attribute addTriples    : String[0..*];
        attribute removeTriples : String[0..*];
        attribute intent        : String;
        attribute verified      : Boolean;
        attribute fixes         : String[0..*];
        attribute regressions   : String[0..*];
    }

    // ---------------------------------------------------------------------- //
    // 7. Behaviour: the validate pipeline
    // ---------------------------------------------------------------------- //

    action def ValidateOntology {
        in  submission : SubmissionPort;
        in  policy     : PolicyPort;
        out report     : ReportPort;

        action load      { out ws : ValidationWorkspace; }
        action profile   { in ws : ValidationWorkspace; out prof : String; }
        action plan      {
            doc /* Deterministic default plan from profile + policy; optionally refined by
                 * the CheckPlanner (additive only). */
            in prof : String; out plan : String;
        }
        action runChecks {
            doc /* Families in dependency order: SYN -> DECL -> DL -> structural -> RSN ->
                 * SHC -> LEX/MOD candidates -> EVO -> CQ. SYN-01 short-circuits. */
            in plan : String; out raw : Finding[0..*];
        }
        action analyse   {
            doc /* Justifications for roots, root-cause clustering, de-duplication. */
            in raw : Finding[0..*]; out analysed : Finding[0..*];
        }
        action adjudicate {
            doc /* LLM labels candidates (if enabled by policy); unsure -> human queue. */
            in analysed : Finding[0..*]; out labelled : Finding[0..*];
        }
        action decide    {
            doc /* PolicyEngine.verdict -- pure. */
            in labelled : Finding[0..*]; out verdict : Verdict;
        }
        action interpret {
            doc /* Explainer + RepairProposer (+ VerifyPatch) + ReportWriter. */
            in labelled : Finding[0..*]; in verdict : Verdict; out draft : String;
        }
        action criticise {
            doc /* Critic: overrides decidable fields, records corrections. */
            in draft : String; out checked : String;
        }
        action publish   { in checked : String; out report : ReportPort; }

        first load then profile then plan then runChecks then analyse
            then adjudicate then decide then interpret then criticise then publish;

        flow load.ws          to profile.ws;
        flow profile.prof     to plan.prof;
        flow plan.plan        to runChecks.plan;
        flow runChecks.raw    to analyse.raw;
        flow analyse.analysed to adjudicate.analysed;
        flow adjudicate.labelled to decide.labelled;
        flow adjudicate.labelled to interpret.labelled;
        flow decide.verdict   to interpret.verdict;
        flow interpret.draft  to criticise.draft;
        flow criticise.checked to publish.checked;
    }

    action def ProposeVerifiedRepair {
        in  cause    : RootCause;
        out accepted : RepairProposal[0..*];
        action propose  { in cause : RootCause; in feedback : String[0..*]; out candidates : RepairProposal[0..*]; }
        action verify   { in candidates : RepairProposal[0..*]; out accepted : RepairProposal[0..*]; out diagnostics : String[0..*]; }
        action feedBack {
            doc /* If accepted is empty and attempts < maxAttempts: diagnostics -> propose.
                 * Otherwise stop; an exhausted loop reports "no verified repair" with the
                 * last diagnostics, never an unverified patch. */
            in diagnostics : String[0..*]; out feedback : String[0..*];
        }
        first propose then verify then feedBack;
        flow propose.candidates to verify.candidates;
        flow verify.diagnostics to feedBack.diagnostics;
        flow feedBack.feedback  to propose.feedback;
    }

    state def ValidationRun {
        state Idle;
        state Loading;
        state Profiling;
        state Checking;
        state Reasoning;
        state Analysing;
        state Adjudicating;
        state Interpreting;
        state Criticising;
        state Reported;
        state Failed;

        transition Idle         then Loading      accept request : SubmissionPort;
        transition Loading      then Failed       if parseError;
        transition Loading      then Profiling;
        transition Profiling    then Checking;
        transition Checking     then Reasoning    if planIncludesReasoning;
        transition Checking     then Analysing    if not planIncludesReasoning;
        transition Reasoning    then Analysing;
        transition Analysing    then Adjudicating if adjudicationEnabled;
        transition Analysing    then Interpreting if not adjudicationEnabled;
        transition Adjudicating then Interpreting;
        transition Interpreting then Criticising;
        transition Criticising  then Reported;
    }

    // ---------------------------------------------------------------------- //
    // 8. Constraints (the trust boundary as checkable statements)
    // ---------------------------------------------------------------------- //

    constraint def CriticDominance {
        doc /* For every decidable field f: report.f == engine.f. Measured as
             * "critic corrections" on the eval set; the constraint is that published
             * reports carry zero uncorrected deviations. */
        attribute uncorrectedDeviations : Integer;
        assert constraint { uncorrectedDeviations == 0 }
    }
    constraint def FindingsFromCatalogueOnly {
        attribute findingsWithoutCheckId : Integer;
        assert constraint { findingsWithoutCheckId == 0 }
    }
    constraint def AdjudicatedCannotReject {
        attribute rejectsRestingOnAdjudication : Integer;
        assert constraint { rejectsRestingOnAdjudication == 0 }
    }
    constraint def RepairsVerified {
        attribute shownUnverifiedRepairs : Integer;
        assert constraint { shownUnverifiedRepairs == 0 }
    }
    constraint def SessionIsolation {
        doc /* No two concurrent runs or MCP sessions share a workspace; every tool call is
             * attributable to exactly one (tenant, run). */
        attribute sharedWorkspaces : Integer;
        assert constraint { sharedWorkspaces == 0 }
    }
    constraint def Determinism {
        doc /* Two runs of the engine on identical (content hash, policy, catalogue) give
             * identical finding sets. */
        attribute findingSetDiff : Integer;
        assert constraint { findingSetDiff == 0 }
    }

    // ---------------------------------------------------------------------- //
    // 9. Instance, satisfaction and allocation
    // ---------------------------------------------------------------------- //

    part ova : OntologyValidationAgent {
        assert constraint criticDominance : CriticDominance;
        assert constraint catalogueOnly   : FindingsFromCatalogueOnly;
        assert constraint adjudicationCap : AdjudicatedCannotReject;
        assert constraint repairsVerified : RepairsVerified;
        assert constraint determinism     : Determinism;
        assert constraint isolation       : SessionIsolation;
    }

    satisfy requirement <'OVA-F01'> MultiSourceIntake      by ova.engine.loader, ova.interfaces.fuseki, ova.interfaces.playground;
    satisfy requirement <'OVA-F02'> CatalogueDrivenChecks  by ova.engine.registry;
    satisfy requirement <'OVA-F03'> ReasoningValidation    by ova.engine.reasoning;
    satisfy requirement <'OVA-F04'> ShaclValidation        by ova.engine.shaclEng;
    satisfy requirement <'OVA-F05'> HierarchyValidation    by ova.engine.structural, ova.engine.reasoning, ova.cognition.adjudicator;
    satisfy requirement <'OVA-F06'> Justifications         by ova.engine.modules, ova.engine.justifier, ova.engine.rootCause;
    satisfy requirement <'OVA-Q05'> JustificationThroughput by ova.engine.modules, ova.engine.justifier, ova.engine.axioms;
    satisfy requirement <'OVA-F07'> PolicyVerdict          by ova.engine.policy;
    satisfy requirement <'OVA-F08'> StructuredReport       by ova.engine.reporter;
    satisfy requirement <'OVA-F09'> VerifiedRepairs        by ova.cognition.repairer, ova.engine.repairVerifier;
    satisfy requirement <'OVA-F10'> VersionDiff            by ova.engine.differ;
    satisfy requirement <'OVA-F11'> ToolExposure           by ova.toolbelt, ova.interfaces.mcpServer;
    satisfy requirement <'OVA-T01'> DeterministicVerdict   by ova.critic, ova.engine.policy;
    satisfy requirement <'OVA-T02'> NoUnverifiedFinding    by ova.critic, ova.engine.registry;
    satisfy requirement <'OVA-T03'> AdjudicationCap        by ova.engine.policy;
    satisfy requirement <'OVA-T04'> ReadOnlyTools          by ova.toolbelt, ova.engine.repairVerifier;
    satisfy requirement <'OVA-T05'> Provenance             by ova.engine.reporter, ova.store;
    satisfy requirement <'OVA-Q01'> DependencyLight        by ova.engine;
    satisfy requirement <'OVA-Q04'> Explainability         by ova.engine.justifier, ova.cognition.explainer;
    satisfy requirement <'OVA-P01'> TenantIsolation        by ova.platform.tenancy, ova.store;
    satisfy requirement <'OVA-P02'> LlmDataGovernance      by ova.platform.gateway;
    satisfy requirement <'OVA-P03'> SecureIngestion        by ova.platform.guards, ova.engine.loader;
    satisfy requirement <'OVA-P05'> ServiceInterface       by ova.interfaces.api, ova.platform.jobs;
    satisfy requirement <'OVA-P06'> Observability          by ova.platform.telemetry;
    satisfy requirement <'OVA-P07'> AuditTrail             by ova.platform.audit;
    satisfy requirement <'OVA-P08'> Scalability            by ova.platform.pushdown, ova.platform.jobs;

    allocate Loader              to "validation_agent/engine/loader.py";
    allocate Profiler            to "validation_agent/engine/profile.py";
    allocate CheckRegistry       to "validation_agent/engine/registry.py";
    allocate StructuralChecker   to "validation_agent/engine/checks/*.py";
    allocate ReasoningEngine     to "validation_agent/engine/reasoning.py";
    allocate ShaclEngine         to "validation_agent/engine/shacl.py";
    allocate LexicalChecker      to "validation_agent/engine/checks/lexical.py";
    allocate VersionDiffer       to "validation_agent/engine/diff.py";
    allocate AxiomIndex          to "validation_agent/engine/axioms.py";
    allocate ModuleExtractor     to "validation_agent/engine/modules.py";
    allocate JustificationEngine to "validation_agent/engine/justify.py";
    allocate RootCauseAnalyser   to "validation_agent/engine/rootcause.py";
    allocate PolicyEngine        to "validation_agent/engine/policy.py";
    allocate RepairVerifier      to "validation_agent/engine/repair.py";
    allocate ReportBuilder       to "validation_agent/engine/report.py";
    allocate ValidationWorkspace to "validation_agent/workspace.py";
    allocate ToolBelt            to "validation_agent/tools/belt.py";
    allocate AgenticLayer        to "validation_agent/agent/programs.py";
    allocate Critic              to "validation_agent/agent/critic.py";
    allocate Orchestrator        to "validation_agent/agent/orchestrator.py";
    allocate McpServer           to "validation_agent/mcp_server.py";
    allocate Cli                 to "validation_agent/cli.py";
    allocate RestApi             to "validation_agent/service/api.py";
    allocate JobQueue            to "validation_agent/service/jobs.py";
    allocate TenantContext       to "validation_agent/service/tenancy.py";
    allocate LlmGateway          to "validation_agent/agent/gateway.py";
    allocate SecurityGuards      to "validation_agent/engine/guards.py";
    allocate Observability       to "validation_agent/service/telemetry.py";
    allocate AuditLog            to "validation_agent/service/audit.py";
    allocate StorePushdown       to "validation_agent/engine/pushdown.py";
}
