# Catalog of Reasoning Patterns for Ontology Augmentation

Reusable reasoning patterns that use a mapping from a **local ontology** (HBIM)
to a **reference ontology** (FIBO) to augment the local one: derive its inheritance
hierarchy, find the **correct parents** for its concepts, and discover **missing
concepts** and **missing object/data properties**.

Every pattern declares a **persistence policy** — how much of its output is safe to
write back automatically:

| Policy | Meaning | Written to |
|--------|---------|-----------|
| **MATERIALISE** | sound entailment, safe to add to the ontology | `output/hbim_derived.ttl` |
| **PROPOSE** | a change that needs steward review | `output/hbim_candidates.ttl` |
| **REPORT** | surfaced for information only | report / console |

Prerequisite for all patterns: HBIM concepts are mapped to FIBO with **SKOS mapping
properties** (`exact/close/broad/narrowMatch`) that are **bridged to OWL**
(`owl:equivalentClass` / `rdfs:subClassOf`) so a DL/OWL-RL reasoner can propagate
FIBO axioms into HBIM. See the parent project (`../README.md`) for the bridge.

Run the whole catalog:

```bash
cd ../src && python run_patterns.py
```

Machine-readable index: [`reasoning_patterns.yaml`](reasoning_patterns.yaml).

---

## Catalog at a glance

| # | Pattern | Augments | Reasoning used | Persistence |
|---|---------|----------|----------------|-------------|
| **P1** | Ancestry derivation | inheritance hierarchy | subclass transitivity + equivalence | MATERIALISE |
| **P2** | Correct parent (existing) | correct parents | direct FIBO superclass of the anchor | PROPOSE |
| **P3** | Missing intermediate concepts | missing concepts | subclass topology vs. covered set | PROPOSE |
| **P4** | Missing narrower concepts | missing concepts | subclass topology + property ranges | PROPOSE |
| **P5** | Missing object properties | missing relationships | property inheritance (restrictions/domain) | PROPOSE |
| **P6** | Missing data properties | missing attributes | property inheritance (restrictions/domain) | PROPOSE |
| **P7** | Parent assignment (discovered) | correct parents for new concepts | nearest ancestor in covered ∪ missing | PROPOSE |
| **P8** | Parent validation | correctness | disjointness → inconsistency | REPORT |

---

## P1 · Ancestry derivation  *(MATERIALISE)*

**Intent.** Give every mapped HBIM concept the full inheritance chain FIBO implies.

**Mechanism.** `rdfs:subClassOf` transitivity over the mapping bridge, plus
`owl:equivalentClass`. **Persist** because it is a sound entailment; written as
`rdfs:subClassOf` + `skos:broaderTransitive` to each FIBO ancestor.

**Example (from the run).**
```
hbim:CurrentAccount ⊑* caa:DemandDepositAccount, caa:TransactionDepositAccount,
    caa:DepositAccount, caa:InvestmentOrDepositAccount, caa:Account,
    fse:BankingProduct, fpas:FinancialProduct, fpas:FinancialProductOrService
```

## P2 · Correct parent for existing concepts  *(PROPOSE)*

**Intent.** The glossary often parents everything under one bland node. FIBO knows
the *precise* parent.

**Mechanism.** Take the concept's FIBO anchor and read its **direct** FIBO
superclass; if that class isn't yet in HBIM it becomes a proposed concept (P3).
Compare with the asserted `skos:broader`; emit `hbim:suggestedBroader` when they differ.

**Example.**
```
hbim:CurrentAccount    current: FinancialAccount   FIBO says: TransactionDepositAccount (propose)
hbim:SavingsAccount    current: FinancialAccount   FIBO says: NonTransactionDepositAccount (propose)
hbim:TermDepositAccount current: FinancialAccount  FIBO says: DepositAccount (propose)
```

## P3 · Missing intermediate concepts  *(PROPOSE)*

**Intent.** Discover the concepts HBIM skipped — the classes FIBO places *between*
two HBIM concepts (or above them).

**Mechanism.** An uncovered FIBO class with a mapped **descendant** and a mapped
**ancestor** is a missing *intermediate*; one with only mapped descendants is a
missing *higher-level* concept. Emitted as candidate `skos:Concept`s (+ `closeMatch`
+ definition copied from FIBO).

**Example.**
```
+ hbim:DepositAccount               (intermediate)   parent → hbim:BankingProduct
+ hbim:TransactionDepositAccount    (intermediate)   parent → hbim:DepositAccount
+ hbim:NonTransactionDepositAccount (intermediate)   parent → hbim:DepositAccount
+ hbim:BankingProduct               (higher-level)   parent → hbim:FinancialProduct
+ hbim:FinancialProduct             (higher-level)   parent → hbim:FinancialProductOrService
```

## P4 · Missing narrower concepts  *(PROPOSE)*

**Intent.** Find coverage gaps — FIBO subclasses of a mapped concept, and classes
referenced only through a relationship, that HBIM never modelled.

**Mechanism.** Uncovered FIBO classes that are subclasses of a mapped concept, plus
uncovered object-property **value types**.

**Example.**
```
+ hbim:BrokerageAccount        parent → hbim:InvestmentAccount
+ hbim:CustomerAccount         parent → hbim:FinancialAccount
+ hbim:LoanOrCreditAccount     parent → hbim:FinancialAccount
+ hbim:DepositoryInstitution   parent → hbim:BusinessAsset   (referenced by isProvidedBy)
```

## P5 · Missing object properties  *(PROPOSE)*

**Intent.** Supply the relationships the glossary never captured.

**Mechanism.** FIBO object properties attached to a mapped/candidate class via a
`someValuesFrom` restriction or `rdfs:domain`, attributed **once** to the most general
owning concept (subclasses inherit). Proposed as `owl:ObjectProperty` with domain/range.

**Example.**
```
hbim:FinancialAccount  needs  rel:isHeldBy          → some caa:AccountHolder
hbim:FinancialAccount  needs  cmns-id:isIdentifiedBy → some caa:AccountIdentifier
hbim:BankingProduct    needs  cmns-org:isProvidedBy  → some fse:DepositoryInstitution
```

## P6 · Missing data properties  *(PROPOSE)*

**Intent.** Same as P5, for datatype attributes.

**Example.**
```
hbim:FinancialAccount  needs  fibod:hasAccountOpeningDate : xsd:date
```

## P7 · Parent assignment for discovered concepts  *(PROPOSE)*

**Intent.** Every concept P3/P4 discovers needs to be *placed*, and some existing
concepts should be **re-parented** under the newly discovered ones.

**Mechanism.** A concept's parent is the nearest ancestor among *all* classes that
will exist after augmentation (covered ∪ proposed). Existing concepts whose nearest
such ancestor is a new concept get a re-parent suggestion.

**Example.**
```
hbim:NonTransactionDepositAccount ⊑ hbim:DepositAccount   re-parent: hbim:SavingsAccount
hbim:TransactionDepositAccount    ⊑ hbim:DepositAccount   re-parent: hbim:CurrentAccount
```
→ i.e. add `DepositAccount` → {`Transaction…`, `NonTransaction…`}, then move
`CurrentAccount` and `SavingsAccount` under the correct branch (which FIBO keeps
`owl:disjointWith`).

## P8 · Parent validation  *(REPORT)*

**Intent.** Guard against wrong parents.

**Mechanism.** FIBO `owl:disjointWith` makes an impossible placement inconsistent.

**Example.**
```
place hbim:CurrentAccount under caa:NonTransactionDepositAccount
  → REJECTED: CurrentAccount would be in disjoint
    caa:TransactionDepositAccount & caa:NonTransactionDepositAccount
```

---

## Applying the outputs

1. **Ancestry (P1)** is materialised into `hbim_derived.ttl` — load it back to give
   HBIM its FIBO-aligned hierarchy immediately.
2. **Everything else (P2–P7)** lands in `hbim_candidates.ttl` as SKOS/OWL proposals
   (new `skos:Concept`s with parents + definitions, `hbim:suggestedBroader`
   re-parenting hints, and proposed `owl:Object/DatatypeProperty`s). A steward
   reviews and promotes them.
3. **P8** gates the promotions — no proposal that violates FIBO disjointness is kept.

Both files are ordinary Turtle: open them (and the reasoning input from the parent
project) in Protégé to review the proposals with a DL reasoner. See `../PROTEGE.md`.

## Extending the catalog

Add a pattern by (a) appending an entry to `reasoning_patterns.yaml` and this file,
and (b) adding a `pN_*` method to `ReasoningPatternCatalog` in `../src/patterns.py`
that reads `self.e.inferred` and returns rows. Candidate write-back goes in
`persist_candidates`. Ideas not yet implemented: property **characteristics**
propagation (inverse/transitive/functional), **instance-driven** concept discovery
(ABox → TBox), and **equivalent-concept detection** across two local ontologies.
