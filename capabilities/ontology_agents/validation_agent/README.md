# Ontology Validation Agent (OVA)

A validator for OWL, RDFS and SKOS ontologies and SHACL-governed data. A deterministic
engine is the only source of findings and verdicts. Language-model modules adjudicate
heuristic candidates, explain root causes, propose repairs that the engine verifies, and
write the report. It is designed as a commercial product with three tiers: a
deterministic tier that runs on-premises with no API key (R1), an opt-in agentic tier
(R2), and gated self-evolution (R3).

**Status: S0, specification only.** No engine code exists yet; see [ROADMAP.md](ROADMAP.md).

| read | for |
|---|---|
| [SPECIFICATION.md](SPECIFICATION.md) | what OVA does: inputs, engine (reasoning, SHACL, custom checks), finding schema, policy and verdict, tool belt, trust boundary, evaluation and evolution contracts, productisation (tenancy, LLM data governance, security, licensing, API, SLOs) |
| [CHECK_CATALOGUE.md](CHECK_CATALOGUE.md) | all 131 checks in 16 families, also grouped by modelling-maturity level (M1-M5, OWL constructs simplest first) and by SIP lifecycle stage (generated) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | reading guide to the SysML architecture: structure, behaviour, design decisions, reuse, module layout |
| [ROADMAP.md](ROADMAP.md) | stages S1 deterministic tool → S2 evaluation datasets → S3 DSPy → S4 self-evolution, each with a measured exit guard; release train R1–R3 and the productisation track |
| [docs/ONTOLOGY_REVIEW_AND_VALIDATION.md](docs/ONTOLOGY_REVIEW_AND_VALIDATION.md) ([HTML](docs/ONTOLOGY_REVIEW_AND_VALIDATION.html)) | business-friendly overview: validation approaches, their benefits and shortcomings, how they complement each other |
| [models/](models) | SysML v2: `ova_requirements`, `ova_architecture`, `ova_development` |
| [spec/check_catalogue.py](spec/check_catalogue.py) | the check catalogue as code: source of truth for S1 detectors, S2 mutation operators and S3 rulebook ids |

```
python spec/build_docs.py    # validate catalogue + SysML traceability, regenerate CHECK_CATALOGUE.md
```

Three rules hold the design together:

1. **Tools measure, the model interprets.** Every finding comes from a catalogue check,
   and the verdict is a pure function of the findings and the policy. A critic overrides
   any model claim about a decidable field.
2. **Candidates are deterministic, labels may be learned.** Judgement checks (is-a
   overload, OntoClean, synonyms) have deterministic candidate generators. The LLM only
   labels the candidates, and its labels can never cause a reject on their own.
3. **Every check that can fail a submission has a mutation operator.** Recall is
   therefore measured, gold labels exist by construction, and self-evolved checks must
   arrive with an operator of their own.
