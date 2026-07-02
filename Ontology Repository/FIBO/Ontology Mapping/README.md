# Ontology Mapping — Collibra → FIBO → HBIM, with FIBO-based reasoning

A worked, runnable example that takes the **`Account` global data category** from
Collibra, maps it to the **FIBO Product & Account ontology**, builds an aligned
**HBIM** (*Harmonised Business Information Model*) **Account subject area**, and
then runs an **OWL reasoner over FIBO** to infer new facts about the HBIM classes
and to improve HBIM.

```
Collibra (Account data category)         FIBO (Product & Account ontology)
   business terms                                 caa:Account
   preferred-term attributes        map           caa:DepositAccount
   business-term relations         ───────►        caa:DemandDepositAccount …
        │                                                  │
        ▼ build                                            │ align (equivalent / subClassOf)
   HBIM Account subject area  ◄───────────────────────────┘
        │
        ▼  reason (OWL RL)
   NEW inferred facts about HBIM classes  +  improvement / validation findings
```

## What each step does

The pipeline is delivered as four **Jupyter notebooks** under `notebooks/`. Each is
*artifact-driven*: it reads the file produced by the previous step (under `output/`),
so a notebook can be run on its own or the four can be run in order.

| Step | Notebook | Output |
|------|----------|--------|
| 1. Extract | `notebooks/01_extract_collibra.ipynb` | `output/account_terms_extracted.json` — business terms, **preferred-term attributes**, business-term relations from the Collibra export. |
| 2. Map | `notebooks/02_map_to_fibo.ipynb` | `output/collibra_to_fibo_mapping.json` — each term → a FIBO class (exact / narrower / close), each relation → a FIBO property. |
| 3. Build HBIM | `notebooks/03_build_hbim.ipynb` | `output/hbim_account.ttl` — the HBIM Account subject area as OWL, aligned to FIBO. |
| 4. Reason | `notebooks/04_reason_hbim.ipynb` | `output/hbim_account_inferred.ttl` + inferred facts, an inferred-hierarchy plot, and HBIM-improvement findings. |

Run the notebooks:

```bash
pip install -r requirements.txt
cd notebooks
jupyter lab        # open and run 01 → 04 interactively
```

Or execute them head-less, in order:

```bash
cd notebooks
for nb in 01_extract_collibra 02_map_to_fibo 03_build_hbim 04_reason_hbim; do
    jupyter nbconvert --to notebook --execute --inplace "$nb.ipynb"
done
```

> The notebooks import only `src/common.py` (shared paths + FIBO/HBIM namespaces).
> `notebooks/_build_notebooks.py` regenerates the four `.ipynb` files from source if needed.

## Inputs

- **`data/collibra_account_export.json`** — a simulated Collibra *Output Module / REST*
  export of the `Account` **global data category**: 8 business terms, their
  attributes (Definition, **Preferred Term**, Preferred Term Label, Acronym,
  Synonyms, Status, Steward) and 16 relations (`is classified by`, `groups`,
  `is broader than`, `is synonym of`, `has attribute`, `is identified by`,
  `is held by`). Swap this file for a real Collibra API pull to use live data.
- **`fibo_excerpt/fibo_account_product_excerpt.ttl`** — a small, self-contained
  excerpt of FIBO using the **real canonical FIBO IRIs and axioms**, transcribed
  from `FBC/ProductsAndServices/ClientsAndAccounts.rdf`,
  `…/FinancialProductsAndServices.rdf` and `FBC/FunctionalEntities/…`. We use an
  excerpt (rather than importing all of FIBO + its `owl:imports`) so the reasoner
  runs in seconds and every inference is easy to trace. Because the IRIs are real,
  the HBIM model is aligned to real FIBO.

## The mapping (step 2)

| Collibra business term | Preferred? | Mapping | FIBO class |
|---|---|---|---|
| Account | yes | exact (`equivalentClass`) | `caa:Account` |
| Deposit Account | yes | exact | `caa:DepositAccount` |
| Current Account | yes | narrower (`subClassOf`) | `caa:DemandDepositAccount` |
| Savings Account | yes | narrower | `caa:NonTransactionDepositAccount` |
| Account Holder | yes | exact | `caa:AccountHolder` |
| Account Identifier | yes | exact | `caa:AccountIdentifier` |
| Account Balance | yes | close (`skos:closeMatch`) | `caa:Account` |
| Checking Account | no | close | `caa:DemandDepositAccount` |

Non-preferred synonyms (e.g. *Checking Account*) are folded onto the preferred
class as `skos:altLabel`. Relations map to FIBO object properties
(`is held by` → `rel:isHeldBy`, `is identified by` → `cmns-id:isIdentifiedBy`).

## The reasoning (step 4)

The HBIM graph is merged with the FIBO excerpt and an **OWL RL** closure is
computed with [`owlrl`](https://github.com/RDFLib/OWL-RL). Because HBIM is aligned
to FIBO, the FIBO axioms flow into HBIM and produce facts never stated in HBIM:

**A. Class-level** — e.g. HBIM only said *Current Account ⊑ DemandDepositAccount*,
but FIBO derives:
`hbim:CurrentAccount ⊑ caa:TransactionDepositAccount ⊑ caa:DepositAccount ⊑
caa:InvestmentOrDepositAccount ⊑ caa:Account` **and** `⊑ fse:BankingProduct ⊑
fpas:FinancialProduct ⊑ fpas:FinancialProductOrService`.

**B. Instance-level** — the sample individual `hbim:account-GB29NWBK…`, typed only
as a `hbim:CurrentAccount`, is inferred to also be a `DepositAccount`,
`BankingProduct`, `FinancialProduct` and `caa:Account`.

**C. How this improves HBIM**
1. **Enrich** — FIBO proves *Current Account* is a `FinancialProduct`, so it can be
   added to the HBIM Product subject area and reuse FIBO product governance.
2. **Completeness rules** — inherited FIBO `someValuesFrom` restrictions become
   HBIM data-quality checks: every current account must be *held by* an
   `AccountHolder`, *identified by* an `AccountIdentifier`, and *provided by* a
   `DepositoryInstitution`.
3. **Equivalence bridges** — `owl:equivalentClass` links keep HBIM and FIBO
   instances mutually classified.
4. **Validation** — a deliberately bad mapping (Current Account also →
   `NonTransactionDepositAccount`) is **rejected automatically**: FIBO declares
   transaction and non-transaction deposit accounts `owl:disjointWith`, so the
   reasoner flags the clash. This catches HBIM modelling errors before they ship.

## Files

```
Ontology Mapping/
├── README.md
├── requirements.txt
├── data/
│   └── collibra_account_export.json      # Collibra 'Account' data category export
├── fibo_excerpt/
│   └── fibo_account_product_excerpt.ttl  # real FIBO IRIs/axioms (Account + Product)
├── src/
│   └── common.py                         # shared paths + FIBO/HBIM namespaces
├── notebooks/
│   ├── 01_extract_collibra.ipynb
│   ├── 02_map_to_fibo.ipynb
│   ├── 03_build_hbim.ipynb
│   ├── 04_reason_hbim.ipynb
│   └── _build_notebooks.py               # regenerates the .ipynb files
└── output/                               # generated artifacts
    ├── account_terms_extracted.json
    ├── collibra_to_fibo_mapping.json
    ├── hbim_account.ttl
    └── hbim_account_inferred.ttl
```

> **Note on HBIM / reasoner.** *HBIM* here means a bank's internal *Harmonised
> Business Information Model*; rename the `hbim:` namespace in `common.py` to suit
> your environment. The example uses the OWL RL profile (`owlrl`) because it is
> pure-Python and needs no external server; for full OWL DL classification you can
> point the same `hbim_account.ttl` + FIBO at an HermiT/ELK reasoner via `owlready2`
> or a Java toolchain.
