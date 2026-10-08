# Reproducing the enrichment in Protégé

The Python pipeline (`owlrl`, OWL RL profile) and Protégé (HermiT / ELK, OWL DL)
agree on every inference used here, because the axioms all live in the shared
OWL 2 fragment: `rdfs:subClassOf`, `owl:equivalentClass`, existential
(`someValuesFrom`) restrictions, and `owl:disjointWith`.

The file **`output/protege_reasoning_ready.ttl`** (or `.rdf`) is the *exact same
merged graph* the Python reasoner consumes:

```
FIBO excerpt  +  HBIM-as-OWL (SKOS lifted)  +  OWL bridge axioms (from SKOS mappings)
```

So loading it and starting a reasoner reproduces the Python results.

> Why a pre-merged file? Protégé's DL reasoners do **not** interpret
> `skos:exactMatch` / `skos:closeMatch` as OWL axioms. The pipeline's *bridge*
> step converts those SKOS mappings into `owl:equivalentClass` / `rdfs:subClassOf`
> first, and bakes them into this file — so Protégé sees the same logic Python did.

## Steps

1. **Open** `output/protege_reasoning_ready.rdf` (recommended for Protégé) or the
   `.ttl` — *File ▸ Open*.
2. **Pick a reasoner** — *Reasoner ▸ HermiT* (or ELK). Then *Reasoner ▸ Start
   reasoner*.
3. **Scenario 3 — Subsumption enrichment.** In the *Class hierarchy (inferred)*
   tab, select `hbim:CurrentAccount`. Under **Inferred**, its ancestors now
   include `caa:DemandDepositAccount → caa:TransactionDepositAccount →
   caa:DepositAccount → caa:InvestmentOrDepositAccount → caa:Account`, plus
   `fse:BankingProduct → fpas:FinancialProduct → fpas:FinancialProductOrService`.
   None of these were asserted on the HBIM concept.
4. **Scenario 4 — Relationship enrichment.** With `hbim:CurrentAccount` selected,
   open the *Description* view: the inherited anonymous superclasses show the
   FIBO restrictions `isHeldBy some AccountHolder`, `isIdentifiedBy some
   AccountIdentifier`, `isProvidedBy some DepositoryInstitution`.
5. **Scenario 6 — Instance classification.** In the *Individuals* tab select
   `hbim:acct-GB29NWBK60161331926819`; its inferred types include
   `caa:DemandDepositAccount`, `caa:DepositAccount`, `caa:Account`,
   `fse:BankingProduct`, … (matching the Python "Scenario 6" output).
6. **Scenario 7 — Validation.** To reproduce the caught error, add one axiom in
   Protégé: on `hbim:CurrentAccount` add superclass
   `caa:NonTransactionDepositAccount`, then re-run the reasoner. HermiT reports
   the ontology **inconsistent** (the sample individual is forced into the two
   `owl:disjointWith` classes `TransactionDepositAccount` /
   `NonTransactionDepositAccount`). Remove the axiom to restore consistency.

## Cross-check against Python

| Scenario | Python (`run_enrichment.py`) | Protégé (HermiT/ELK) |
|----------|------------------------------|----------------------|
| 3 Subsumption | "SCENARIO 3" inferred ancestors | inferred class hierarchy |
| 4 Relationships | "SCENARIO 4" inherited restrictions | Description / inherited anonymous superclasses |
| 6 Instances | "SCENARIO 6" inferred types | inferred individual types |
| 7 Validation | "SCENARIO 7" disjointness clash | reasoner reports inconsistency |

The full machine-readable closure Python computed is in
`output/inferred_closure.ttl` if you want to diff it against Protégé's inferences
(*File ▸ Export inferred axioms* in Protégé).
