/*
 * Ontology Validation Agent (OVA) -- staged development, evaluation and self-evolution.
 * SysML v2 (textual notation).
 *
 * Development is modelled as a state machine whose transitions are guarded by MEASURED
 * exit criteria, not by dates. Each stage produces the artefact the next one stands on:
 *
 *   S1 deterministic tool  -> the control, the critic and the reward
 *   S2 evaluation datasets -> gold labels by construction (mutation) and by people
 *   S3 DSPy optimisation   -> a measured, held-out improvement over the S1 control
 *   S4 self-evolution      -> gated change: instructions, demos, thresholds, new checks
 *
 * The order is deliberate: the deterministic control comes first, the grader before the
 * program, the optimiser after the grader, and the gate after the noise is measured.
 *
 * Releases ride on the stages: R1 (deterministic product, after S1c), R2 (agentic
 * features, after S3), R3 (self-evolving, after S4). Every release must pass
 * ReleaseReadinessCase.
 */

package OvaDevelopment {

    import ScalarValues::*;
    import OvaRequirements::*;
    import OvaArchitecture::*;

    // ---------------------------------------------------------------------- //
    // 1. Stage machine
    // ---------------------------------------------------------------------- //

    state def DevelopmentProgramme {
        state S0_Specification;
        state S1a_DeterministicMvp;
        state S1b_FullCatalogue;
        state S1c_ReasoningDepth;
        state S2_EvaluationData;
        state S3_AgenticBaseline;
        state S3_Optimised;
        state S4_SelfEvolving;

        transition S0_Specification     then S1a_DeterministicMvp if catalogueValidated;
        transition S1a_DeterministicMvp then S1b_FullCatalogue    if referenceConformant;
        transition S1b_FullCatalogue    then S1c_ReasoningDepth   if fixturesGreen;
        transition S1c_ReasoningDepth   then S2_EvaluationData    if justificationsMinimal;
        transition S2_EvaluationData    then S3_AgenticBaseline   if datasetsFrozen;
        transition S3_AgenticBaseline   then S3_Optimised         if judgeValidated;
        transition S3_Optimised         then S4_SelfEvolving      if gainExceedsNoise;
        transition S4_SelfEvolving      then S3_Optimised         if gateRegression;
    }

    // ---------------------------------------------------------------------- //
    // 2. Stage 1 -- deterministic tool
    // ---------------------------------------------------------------------- //

    part def CheckFixture {
        doc /* Per check: a minimal positive graph (must fire), a minimal negative graph
             * (must not fire) and a near-miss (looks like the defect, is not: deliberate
             * punning, waived disjointness, declared multi-axis classification). */
        attribute checkId : String;
        attribute positive : String;
        attribute negative : String;
        attribute nearMiss : String[0..1];
    }

    part def ReferenceConformanceSuite {
        doc /* (a) W3C SHACL Core test cases; (b) W3C OWL 2 test cases (RL profile; DL when
             * the DL backend is on); (c) the golden corpus: real ontologies with expected
             * findings signed off by a curator; (d) the differential corpus: ontologies run
             * through OVA and the family's reference oracles (ROBOT report, HermiT, ELK,
             * qSKOS, OOPS!), disagreements triaged as OVA bug / oracle bug / by design. */
        part golden       : GoldenCorpus;
        part differential : DifferentialCorpus;
    }
    part def GoldenCorpus {
        doc /* Versioned; grows with every escaped defect (a production finding that the
             * engine missed becomes a golden case before the fix is merged). */
    }
    part def DifferentialCorpus;

    verification def <'V-S1a'> ReferenceConformanceCase {
        doc /* Run the Reference Conformance Suite; 100% on W3C cases and the golden corpus;
             * every oracle disagreement has a recorded triage outcome. */
        subject engine : ValidationEngine;
        objective { verify requirement <'OVA-E03'> ReferenceConformance; }
    }
    verification def <'V-S1b'> FixtureSuiteCase {
        doc /* All CheckFixture triples pass; determinism test (two runs, same set); FIBO
             * throughput within budget. */
        subject engine : ValidationEngine;
        objective {
            verify requirement <'OVA-F02'> CatalogueDrivenChecks;
            verify requirement <'OVA-Q02'> Throughput;
        }
    }
    verification def <'V-S1c'> JustificationMinimalityCase {
        doc /* Every justification is minimal: removing any one of its axioms removes the
             * entailment. Module soundness: on sampled entailments, the justifications found
             * inside the STAR module equal those found over the full ontology; modules agree
             * with ROBOT extract --method STAR. Throughput: p95 per root on FIBO within
             * budget. */
        subject engine : ValidationEngine;
        objective {
            verify requirement <'OVA-F06'> Justifications;
            verify requirement <'OVA-Q05'> JustificationThroughput;
        }
    }

    // ---------------------------------------------------------------------- //
    // 3. Stage 2 -- evaluation datasets
    // ---------------------------------------------------------------------- //

    part def EvaluationCorpus {
        part seeds      : SeedOntology[1..*];
        part mutants    : MutantSet;
        part realDefects : RealDefectSet;
        part adjudication : AdjudicationSet;
        part reports    : ReportLabelSet;
        part repairs    : RepairSet;
        part regression : RegressionCorpus;
        attribute splitPolicy : String default "grouped-by-seed";
    }

    part def SeedOntology {
        doc /* A clean-enough starting ontology, CERTIFIED: its existing findings are
             * recorded as a baseline so later diffs measure only injected faults. Sources:
             * FIBO, gist, QUDT, schema.org, selected OBO Foundry ontologies, public
             * SKOS schemes, and design-partner ontologies under their agreements. */
        attribute certifiedBaseline : String;
        attribute licence : String;
    }
    part def MutationOperator {
        doc /* graph -> (graph', label). Named in the catalogue's `mutation` field. Must be
             * applicable-checking (returns None where it cannot apply) and seeded. */
        attribute name      : String;
        attribute targetsCheck : String[1..*];
        attribute seed      : Integer;
    }
    part def MutantSet {
        doc /* Single-fault and multi-fault (2-5 operators) mutants of each seed. Gold labels
             * = the injected check ids plus the certified baseline. Also IRI-scrambled
             * variants (local names and labels permuted consistently) to measure how much
             * an LLM relies on remembering famous ontologies rather than reading them. */
        part operators : MutationOperator[1..*];
        attribute singleFault : Integer;
        attribute multiFault  : Integer;
        attribute scrambled   : Boolean default true;
    }
    part def RealDefectSet {
        doc /* Defects mined from version histories of public ontologies: commits whose diff
             * removes a finding. Pre-commit = input, the commit = gold repair. */
    }
    part def AdjudicationSet {
        doc /* Heuristic candidates (MOD, HIER-09/16/17/21/22, PROP-06, LEX-07/08/10) labelled
             * by two domain experts; disagreements resolved by a third. Reports kappa. */
        attribute minKappa : Real default 0.7;
    }
    part def ReportLabelSet {
        doc /* Reports rated by reviewers on a rubric, used to validate ReportJudge. */
    }
    part def RepairSet {
        doc /* Root causes with one or more accepted repairs (from mutants: the inverse
             * mutation; from history: the fixing commit). Repairs are scored by the engine,
             * so gold is only needed for the 'minimality' comparison. */
    }
    part def RegressionCorpus {
        doc /* Every ontology whose verdict a curator has signed off (golden corpus plus
             * accepted production cases with consent): the regression set whose verdicts
             * must never change without a policy version change. */
    }

    part def DatasetCard {
        attribute version     : String;
        attribute sha256      : String;
        attribute splits      : String;   // train / dev / test / holdout-gate
        attribute counts      : String;
        attribute knownBias   : String;
    }

    verification def <'V-S2'> DatasetFreezeCase {
        doc /* Every non-info check has >= 1 operator and >= 1 applicable seed; kill rate
             * 1.0 for deterministic checks; clean seeds produce no non-baseline finding;
             * splits grouped by seed (no seed in two splits); hashes recorded. */
        subject corpus : EvaluationCorpus;
        objective {
            verify requirement <'OVA-E01'> MutationRecall;
            verify requirement <'OVA-E02'> CleanSeedPrecision;
        }
    }

    // ---------------------------------------------------------------------- //
    // 4. Stage 3 -- agentic system and DSPy optimisation
    // ---------------------------------------------------------------------- //

    part def ValidationRulebook {
        doc /* Named violations the scorer emits (and GEPA reads). Ids: use-label-vocabulary,
             * report-all-findings, no-unsupported-findings, apply-waivers, correct-severity,
             * correct-adjudication, cite-justification, identify-root-cause,
             * repair-verified, repair-minimal, decide-by-policy, ground-in-evidence. */
    }
    part def Scorer {
        doc /* (gold, prediction) -> ScoreReport(score, notes, violated). The notes say what
             * was expected, field by field. Same scorer for baseline, GEPA, agent, MDP. */
        part rulebook : ValidationRulebook;
    }

    part def OptimisationTarget {
        attribute module    : String;
        attribute metric    : String;
        attribute optimiser : String;
        attribute budget    : Integer;   // max_metric_calls
    }

    part def S3Targets {
        part adjudicator : OptimisationTarget {
            doc /* F1 against AdjudicationSet labels; feedback = which cue misled. */
        }
        part explainer   : OptimisationTarget {
            doc /* Judge score (validated) + grounding: every axiom named is in the
                 * justification. */
        }
        part repairer    : OptimisationTarget {
            doc /* Engine-computed and gold-free: fixed targets, no new blocker/major,
                 * minimal axioms changed, entailment loss. A verifiable reward. */
        }
        part planner     : OptimisationTarget {
            doc /* Reward = answer quality - cost of evidence bought; compared with the MDP
                 * optimum V* (regret). */
        }
        part writer      : OptimisationTarget {
            doc /* Validated judge score, grounding, and critic-correction count (lower is
                 * better). */
        }
    }

    action def OptimiseModule {
        in  target  : OptimisationTarget;
        out version : String;

        action baseline   { doc /* Hand-written instruction, measured on dev with cost. */ }
        action validateJudge { doc /* Agreement + kappa on ReportLabelSet before any judge-based metric is used. */ }
        action fewShot    { doc /* BootstrapFewShot / LabeledFewShot from train. */ }
        action instruct   { doc /* GEPA with rulebook feedback; MIPROv2 as the comparison arm. */ }
        action ablate     { doc /* Blind-metric arm (score only, no notes) to price the feedback. */ }
        action noise      { doc /* >= 3 uncached repeats of baseline and best -> run-to-run spread. */ }
        action holdout    { doc /* Report on test: n, mean, spread, USD; adopt only if gain > noise. */ }

        first baseline then validateJudge then fewShot then instruct then ablate then noise then holdout;
    }

    verification def <'V-S3'> HeldOutImprovementCase {
        doc /* Pipeline+critic vs agent loop vs program, same scorer, same test split:
             * score, cost, critic corrections, tool calls. The optimised system must beat
             * the deterministic-only control on the LLM-dependent fields (adjudication,
             * explanation, repair) by more than the measured noise, at <= CostCeiling. */
        subject agent : OntologyValidationAgent;
        objective {
            verify requirement <'OVA-E04'> HonestImprovement;
            verify requirement <'OVA-Q03'> CostCeiling;
            verify requirement <'OVA-T01'> DeterministicVerdict;
        }
    }

    // ---------------------------------------------------------------------- //
    // 5. Stage 4 -- self-evolution
    // ---------------------------------------------------------------------- //

    part def ExperienceBuffer {
        doc /* Episodes from production runs: input hash, prediction, critic corrections,
             * expert feedback (confirm/dismiss), cost. Failures are mined into training
             * examples; the gate holdout is NEVER drawn from here. */
        attribute capacity : Integer default 5000;
    }

    part def EvolvableArtefact {
        attribute kind : EvolutionKind;
        attribute version : Integer;
    }
    enum def EvolutionKind { instruction; demonstrations; threshold; houseShape; checkCandidate; mutationOperator; }

    part def PromotionGate {
        doc /* candidate promoted iff: holdoutScore(candidate) - holdoutScore(current) >=
             * minGain; regression suite (RegressionCorpus verdicts unchanged, fixtures, kill rate) green;
             * cost within ceiling; curator approval for checkCandidate/houseShape. minGain
             * is set from the S3 noise study, not chosen. A no-op control candidate is run
             * every N rounds and must be rejected. */
        attribute minGain : Real;
        attribute controlEveryRounds : Integer default 5;
    }

    action def EvolveRound {
        in  buffer  : ExperienceBuffer;
        out decision : String;

        action mine      { doc /* Cluster failures by violated rule id and check id. */ }
        action propose   {
            doc /* Per cluster: re-optimise instruction/demos (GEPA), recalibrate a threshold,
                 * or -- when experts keep confirming a defect no check catches -- synthesise
                 * a candidate check as SPARQL or SHACL from the confirmed examples. */
        }
        action sandbox   {
            doc /* Candidate checks run in a sandbox: precision on certified seeds (zero new
                 * findings), recall on the HELD-OUT confirmed examples (split before
                 * synthesis), runtime. The mutation operator is synthesised separately
                 * from the defect description, without seeing the check. Its mutants must
                 * show a non-vacuous, localised VersionDiffer diff (and a closure change for
                 * semantic families); a blind sample is confirmed by experts as exhibiting
                 * the defect; and the check must not fire on other operators' mutants
                 * except declared overlaps. Only then does kill rate count -- see
                 * IndependentEvidence. */
        }
        action gate      { doc /* PromotionGate on the holdout. */ }
        action approve   { doc /* Curator review of the check AND its mutation operator (logic, diff samples, evidence pack). */ }
        action promote   { doc /* Version bump; skill card regenerated; previous version kept for rollback. */ }
        action monitor   { doc /* Post-promotion drift: critic corrections, dismissal rate, cost; auto-rollback on breach. */ }

        first mine then propose then sandbox then gate then approve then promote then monitor;
    }

    constraint def EvolutionScope {
        doc /* Additive only: no promoted artefact edits an existing deterministic check,
             * the critic, the policy function, the scorer or the gate. */
        attribute mutationsOfCore : Integer;
        assert constraint { mutationsOfCore == 0 }
    }
    constraint def IndependentEvidence {
        doc /* A promoted synthesised check has evidence that does not come from its own
             * operator: held-out expert-confirmed recall, blind mutant confirmation,
             * non-vacuous diffs, independent operator derivation, operator review. */
        attribute promotedWithoutIndependentEvidence : Integer;
        assert constraint { promotedWithoutIndependentEvidence == 0 }
    }
    constraint def ControlRejected {
        attribute noopPromotions : Integer;
        assert constraint { noopPromotions == 0 }
    }

    verification def <'V-S4'> GatedEvolutionCase {
        doc /* Replay K rounds on recorded experience: count promotions, rejected no-op
             * controls, regressions caught, rollbacks; holdout trend vs S3 version. Plant a
             * colluding pair (a wrong check plus an operator injecting exactly what it
             * matches, kill rate 1.0): the gate must reject it on independent evidence. */
        subject agent : OntologyValidationAgent;
        objective {
            verify requirement <'OVA-E05'> GatedEvolution;
            verify requirement <'OVA-E06'> ImmutableCore;
            verify requirement <'OVA-E07'> NonCircularValidation;
        }
    }

    // ---------------------------------------------------------------------- //
    // 5b. Release readiness (commercial)
    // ---------------------------------------------------------------------- //

    part def ReleaseTrain {
        doc /* R1 deterministic product (gate/validate/diff without LLM) after S1c;
             * R2 agentic features (adjudication, explanation, verified repair) after S3;
             * R3 gated self-evolution after S4. */
        attribute release : String;
    }

    verification def <'V-REL'> ReleaseReadinessCase {
        doc /* Per release: tenant-isolation tests; LLM-off run of every mode; gateway
             * redaction and egress tests; security tests (XXE, SSRF via imports, oversized
             * input, SPARQL injection, malicious patch); SBOM + licence scan with no AGPL
             * in the distribution; API contract tests against the OpenAPI spec; trace and
             * metric presence; audit replay reproduces a report; load test at maxTriples;
             * SLOs measured on the reference workload. */
        subject agent : OntologyValidationAgent;
        objective {
            verify requirement <'OVA-P01'> TenantIsolation;
            verify requirement <'OVA-P02'> LlmDataGovernance;
            verify requirement <'OVA-P03'> SecureIngestion;
            verify requirement <'OVA-P04'> LicenceCompliance;
            verify requirement <'OVA-P05'> ServiceInterface;
            verify requirement <'OVA-P06'> Observability;
            verify requirement <'OVA-P07'> AuditTrail;
            verify requirement <'OVA-P08'> Scalability;
            verify requirement <'OVA-P09'> ServiceLevels;
        }
    }

    // ---------------------------------------------------------------------- //
    // 6. Verification trace (flat form, read by the repo's SysML reader)
    // ---------------------------------------------------------------------- //

    verify requirement <'OVA-E03'> by <'V-S1a'>;
    verify requirement <'OVA-F02'> by <'V-S1b'>;
    verify requirement <'OVA-Q02'> by <'V-S1b'>;
    verify requirement <'OVA-F06'> by <'V-S1c'>;
    verify requirement <'OVA-E01'> by <'V-S2'>;
    verify requirement <'OVA-E02'> by <'V-S2'>;
    verify requirement <'OVA-E04'> by <'V-S3'>;
    verify requirement <'OVA-Q03'> by <'V-S3'>;
    verify requirement <'OVA-T01'> by <'V-S3'>;
    verify requirement <'OVA-E05'> by <'V-S4'>;
    verify requirement <'OVA-E06'> by <'V-S4'>;
    verify requirement <'OVA-E07'> by <'V-S4'>;
    verify requirement <'OVA-Q05'> by <'V-S1c'>;
    verify requirement <'OVA-P01'> by <'V-REL'>;
    verify requirement <'OVA-P02'> by <'V-REL'>;
    verify requirement <'OVA-P03'> by <'V-REL'>;
    verify requirement <'OVA-P04'> by <'V-REL'>;
    verify requirement <'OVA-P05'> by <'V-REL'>;
    verify requirement <'OVA-P06'> by <'V-REL'>;
    verify requirement <'OVA-P07'> by <'V-REL'>;
    verify requirement <'OVA-P08'> by <'V-REL'>;
    verify requirement <'OVA-P09'> by <'V-REL'>;

    part ovaProject {
        exhibit state programme : DevelopmentProgramme;
    }
    part evolution : PromotionGate {
        assert constraint scope   : EvolutionScope;
        assert constraint control : ControlRejected;
        assert constraint independent : IndependentEvidence;
    }
}
