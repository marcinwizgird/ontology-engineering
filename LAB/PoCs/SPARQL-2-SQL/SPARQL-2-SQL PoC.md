# Engineering Implementation Specification: FIBO VKG Offline SPARQL-to-SQL Compiler & Demo Environment

**Document Version:** 1.0 (Engineering Handover)  
**Architecture Pattern:** Stateless Python Compiler Microservice (`FastAPI` + `sqlglot`) + Offline Ontop VKG Sidecar (`/ontop/reformulate`) + Isolated DuckDB Demo Sandbox.

---

## 1. Architectural Overview & System Boundaries

To prove that the **SPARQL-to-SQL Compiler Microservice** operates with **zero runtime database connection**, the PoC strictly separates the **Compilation Plane** from the **Demo Execution Sandbox**:

1. **Compilation Plane (Stateless Production Candidate):**
   * **`ontop-sidecar`:** Loads the FIBO OWL 2 QL ontology subset, W3C R2RML mappings, and static `db-metadata.json`. Exposes `/ontop/reformulate` internally on port `8080`. It has **no network route or credentials** to any database.
   * **`sparql2sql-service` (Python FastAPI):** Validates SPARQL 1.1 syntax via `rdflib`, calls `ontop-sidecar` to unfold the query into PostgreSQL-dialect relational algebra, uses `sqlglot` to transpile the resulting SQL into the requested target dialect (`postgres`, `snowflake`, `bigquery`, `duckdb`), and returns the compiled SQL string in under 15 ms.
2. **Demo Verification Plane (Optional UI / Stakeholder Sandbox):**
   * **`demo-sandbox` (Streamlit + Embedded DuckDB):** Pre-loaded with CSV data from the **IBM FIBEN Benchmark**. Sends a FIBO SPARQL query to `sparql2sql-service`, displays the generated SQL, and allows stakeholders to click **"Execute Compiled SQL on Sample Data"** to verify real rows (*Alphabet Inc.*, *JPMorgan Chase*, *NYSE* holdings, SEC filings).

---

## 2. Selected 10-Table FIBEN Subset & FIBO Alignment

| # | FIBEN Relational Table | Primary Key | Foreign Keys | Mapped FIBO / FRO Class | Key Populated Columns |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | `PUBLIC.COMPANY` | `COMP_ID` | — | `fibo-be-le-cb:Corporation` | `COMP_NAME`, `CIK_CODE`, `SIC_CODE`, `COUNTRY_INC` |
| 2 | `PUBLIC.EXCHANGE` | `EXCH_ID` | — | `fibo-fbc-fct-mkt:Exchange` | `EXCH_SYMBOL` (*NYSE*, *NASDAQ*), `EXCH_NAME`, `COUNTRY` |
| 3 | `PUBLIC.SECURITY` | `SEC_ID` | `ISSUER_COMP_ID` -> `COMPANY`, `EXCH_ID` -> `EXCHANGE` | `fibo-sec-sec-iss:Security` | `SYMBOL`, `SEC_NAME`, `SEC_TYPE` (`STOCK`, `BOND`), `LAST_PRICE` |
| 4 | `PUBLIC.STOCK` | `SEC_ID` | `SEC_ID` -> `SECURITY` | `fibo-sec-eq-eq:ListedShare` | `SHARES_OUTSTANDING`, `DIVIDEND_YIELD`, `PE_RATIO` |
| 5 | `PUBLIC.BOND` | `SEC_ID` | `SEC_ID` -> `SECURITY` | `fibo-sec-dbt-bnd:Bond` | `COUPON_RATE`, `MATURITY_DATE`, `CREDIT_RATING` |
| 6 | `PUBLIC.CUSTOMER` | `CUST_ID` | — | `fibo-fbc-pas-caa:Customer` | `FULL_NAME`, `CUST_TYPE` (`RETAIL`, `CORP`), `TAX_ID`, `DOMICILE` |
| 7 | `PUBLIC.ACCOUNT` | `ACC_ID` | `CUST_ID` -> `CUSTOMER` | `fibo-fbc-pas-caa:InvestmentAccount` | `ACC_NUMBER`, `ACC_STATUS`, `CURRENCY`, `CASH_BALANCE` |
| 8 | `PUBLIC.HOLDING` | `HOLDING_ID` | `ACC_ID` -> `ACCOUNT`, `SEC_ID` -> `SECURITY` | `fibo-sec-sec-ast:PortfolioHolding` | `QUANTITY`, `PURCHASE_PRICE`, `VALUATION_DATE` |
| 9 | `PUBLIC.TRADE_ORDER` | `ORDER_ID` | `ACC_ID` -> `ACCOUNT`, `SEC_ID` -> `SECURITY` | `fibo-fbc-pas-fpas:TradeOrder` | `ORDER_TYPE` (`BUY`, `SELL`), `ORDER_QTY`, `LIMIT_PRICE`, `TRADE_DATE` |
| 10 | `PUBLIC.FIN_REPORT` | `REPORT_ID` | `COMP_ID` -> `COMPANY` | `fro-sec:FinancialReport` | `FISCAL_YEAR`, `FISCAL_PERIOD`, `REVENUE_USD`, `NET_INCOME_USD`, `TOTAL_ASSETS_USD` |

---

## 3. Repository Structure

```text
fibo-sparql2sql-poc/
├── docker-compose.yml
├── Makefile
├── vkg-artifacts/
│   ├── fibo-subset.ttl           # OWL 2 QL TBox (FIBO BE, SEC, FBC + FRO)
│   ├── fiben-mappings.r2rml.ttl  # W3C R2RML Mappings for the 10 tables
│   ├── db-metadata.json          # Static PK/FK & column metadata for Ontop
│   └── ontop.properties          # Offline PostgreSQL dialect configuration
├── compiler-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI endpoints (/v1/compile, /health)
│   │   ├── compiler.py           # Ontop sidecar client + sqlglot AST transpiler
│   │   └── models.py             # Pydantic request/response schemas
│   └── tests/
│       └── test_fibo_compilation.py
└── demo-sandbox/
    ├── Dockerfile
    ├── ddl/
    │   └── fiben_10_tables.sql   # DDL for the 10-table slice
    ├── seed_duckdb.py            # Extracts FIBEN CSVs / seeds realistic rows
    └── ui.py                     # Streamlit side-by-side SPARQL -> SQL -> Data UI
```

---

## 4. Static VKG Artifacts Specification

### 4.1 FIBO OWL 2 QL TBox (`vkg-artifacts/fibo-subset.ttl`)

```turtle
@prefix rdf: [http://www.w3.org/1999/02/22-rdf-syntax-ns#](http://www.w3.org/1999/02/22-rdf-syntax-ns#) .
@prefix rdfs: [http://www.w3.org/2000/01/rdf-schema#](http://www.w3.org/2000/01/rdf-schema#) .
@prefix owl: [http://www.w3.org/2002/07/owl#](http://www.w3.org/2002/07/owl#) .
@prefix xsd: [http://www.w3.org/2001/XMLSchema#](http://www.w3.org/2001/XMLSchema#) .

@prefix fibo-be-le-lp: [https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/LegalPersons/](https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/LegalPersons/) .
@prefix fibo-be-le-cb: [https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/](https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/) .
@prefix fibo-fbc-fct-mkt: [https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/Markets/](https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/Markets/) .
@prefix fibo-fbc-pas-caa: [https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/](https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/) .
@prefix fibo-fbc-pas-fpas: [https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/](https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/) .
@prefix fibo-sec-sec-iss: [https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecuritiesIssuance/](https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecuritiesIssuance/) .
@prefix fibo-sec-sec-ast: [https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecurityAssets/](https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecurityAssets/) .
@prefix fibo-sec-eq-eq: [https://spec.edmcouncil.org/fibo/ontology/SEC/Equities/EquityInstruments/](https://spec.edmcouncil.org/fibo/ontology/SEC/Equities/EquityInstruments/) .
@prefix fibo-sec-dbt-bnd: [https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/](https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/) .
@prefix fro-sec: [http://finregont.com/fro/sec/SEC_Filings.ttl#](http://finregont.com/fro/sec/SEC_Filings.ttl#) .
@prefix ex-fibo: [https://example.org/fibo-vkg/voc#](https://example.org/fibo-vkg/voc#) .

[https://example.org/fibo-vkg/ontology](https://example.org/fibo-vkg/ontology) a owl:Ontology .

fibo-be-le-lp:LegalPerson a owl:Class .
fibo-be-le-cb:Corporation a owl:Class ; rdfs:subClassOf fibo-be-le-lp:LegalPerson .

fibo-fbc-pas-caa:Customer a owl:Class .
ex-fibo:RetailCustomer a owl:Class ; rdfs:subClassOf fibo-fbc-pas-caa:Customer .
ex-fibo:CorporateCustomer a owl:Class ; rdfs:subClassOf fibo-fbc-pas-caa:Customer .

fibo-sec-sec-iss:Security a owl:Class .
fibo-sec-eq-eq:ListedShare a owl:Class ; rdfs:subClassOf fibo-sec-sec-iss:Security .
fibo-sec-dbt-bnd:Bond a owl:Class ; rdfs:subClassOf fibo-sec-sec-iss:Security .

fibo-fbc-fct-mkt:Exchange a owl:Class .
fibo-fbc-pas-caa:InvestmentAccount a owl:Class .
fibo-sec-sec-ast:PortfolioHolding a owl:Class .
fibo-fbc-pas-fpas:TradeOrder a owl:Class .
fro-sec:FinancialReport a owl:Class .

ex-fibo:issuedBy a owl:ObjectProperty ; rdfs:domain fibo-sec-sec-iss:Security ; rdfs:range fibo-be-le-cb:Corporation .
ex-fibo:listedOn a owl:ObjectProperty ; rdfs:domain fibo-sec-sec-iss:Security ; rdfs:range fibo-fbc-fct-mkt:Exchange .
ex-fibo:hasAccount a owl:ObjectProperty ; rdfs:domain fibo-fbc-pas-caa:Customer ; rdfs:range fibo-fbc-pas-caa:InvestmentAccount .
ex-fibo:hasHolding a owl:ObjectProperty ; rdfs:domain fibo-fbc-pas-caa:InvestmentAccount ; rdfs:range fibo-sec-sec-ast:PortfolioHolding .
ex-fibo:holdsSecurity a owl:ObjectProperty ; rdfs:domain fibo-sec-sec-ast:PortfolioHolding ; rdfs:range fibo-sec-sec-iss:Security .
ex-fibo:hasTradeOrder a owl:ObjectProperty ; rdfs:domain fibo-fbc-pas-caa:InvestmentAccount ; rdfs:range fibo-fbc-pas-fpas:TradeOrder .
ex-fibo:ordersSecurity a owl:ObjectProperty ; rdfs:domain fibo-fbc-pas-fpas:TradeOrder ; rdfs:range fibo-sec-sec-iss:Security .
fro-sec:reportedBy a owl:ObjectProperty ; rdfs:domain fro-sec:FinancialReport ; rdfs:range fibo-be-le-cb:Corporation .

ex-fibo:legalName a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:cikCode a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:sicCode a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:exchangeSymbol a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:tickerSymbol a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:securityName a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:lastPrice a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:peRatio a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:dividendYield a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:couponRate a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:creditRating a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:customerName a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:domicileCountry a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:accountNumber a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:cashBalance a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:holdingQuantity a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:purchasePrice a owl:DatatypeProperty ; rdfs:range xsd:decimal .
ex-fibo:orderType a owl:DatatypeProperty ; rdfs:range xsd:string .
ex-fibo:orderQuantity a owl:DatatypeProperty ; rdfs:range xsd:decimal .
fro-sec:fiscalYear a owl:DatatypeProperty ; rdfs:range xsd:integer .
fro-sec:revenueUSD a owl:DatatypeProperty ; rdfs:range xsd:decimal .
fro-sec:netIncomeUSD a owl:DatatypeProperty ; rdfs:range xsd:decimal .
```

### 4.2 W3C R2RML Mapping Specification (`vkg-artifacts/fiben-mappings.r2rml.ttl`)

```turtle
@prefix rr: [http://www.w3.org/ns/r2rml#](http://www.w3.org/ns/r2rml#) .
@prefix xsd: [http://www.w3.org/2001/XMLSchema#](http://www.w3.org/2001/XMLSchema#) .
@prefix fibo-be-le-cb: [https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/](https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/) .
@prefix fibo-fbc-fct-mkt: [https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/Markets/](https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/Markets/) .
@prefix fibo-fbc-pas-caa: [https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/](https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/) .
@prefix fibo-fbc-pas-fpas: [https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/](https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/) .
@prefix fibo-sec-sec-iss: [https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecuritiesIssuance/](https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecuritiesIssuance/) .
@prefix fibo-sec-sec-ast: [https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecurityAssets/](https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecurityAssets/) .
@prefix fibo-sec-eq-eq: [https://spec.edmcouncil.org/fibo/ontology/SEC/Equities/EquityInstruments/](https://spec.edmcouncil.org/fibo/ontology/SEC/Equities/EquityInstruments/) .
@prefix fibo-sec-dbt-bnd: [https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/](https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/) .
@prefix fro-sec: [http://finregont.com/fro/sec/SEC_Filings.ttl#](http://finregont.com/fro/sec/SEC_Filings.ttl#) .
@prefix ex-fibo: [https://example.org/fibo-vkg/voc#](https://example.org/fibo-vkg/voc#) .

<#CompanyMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"COMPANY\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/company/](https://example.org/fibo-vkg/data/company/){COMP_ID}" ; rr:class fibo-be-le-cb:Corporation ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:legalName ; rr:objectMap [ rr:column "\"COMP_NAME\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:cikCode ; rr:objectMap [ rr:column "\"CIK_CODE\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:sicCode ; rr:objectMap [ rr:column "\"SIC_CODE\"" ] ] .

<#ExchangeMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"EXCHANGE\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/exchange/](https://example.org/fibo-vkg/data/exchange/){EXCH_ID}" ; rr:class fibo-fbc-fct-mkt:Exchange ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:exchangeSymbol ; rr:objectMap [ rr:column "\"EXCH_SYMBOL\"" ] ] .

<#SecurityMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"SECURITY\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/security/](https://example.org/fibo-vkg/data/security/){SEC_ID}" ; rr:class fibo-sec-sec-iss:Security ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:tickerSymbol ; rr:objectMap [ rr:column "\"SYMBOL\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:securityName ; rr:objectMap [ rr:column "\"SEC_NAME\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:lastPrice ; rr:objectMap [ rr:column "\"LAST_PRICE\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:issuedBy ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/company/](https://example.org/fibo-vkg/data/company/){ISSUER_COMP_ID}" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:listedOn ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/exchange/](https://example.org/fibo-vkg/data/exchange/){EXCH_ID}" ] ] .

<#StockMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"STOCK\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/security/](https://example.org/fibo-vkg/data/security/){SEC_ID}" ; rr:class fibo-sec-eq-eq:ListedShare ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:peRatio ; rr:objectMap [ rr:column "\"PE_RATIO\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:dividendYield ; rr:objectMap [ rr:column "\"DIVIDEND_YIELD\"" ; rr:datatype xsd:decimal ] ] .

<#BondMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"BOND\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/security/](https://example.org/fibo-vkg/data/security/){SEC_ID}" ; rr:class fibo-sec-dbt-bnd:Bond ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:couponRate ; rr:objectMap [ rr:column "\"COUPON_RATE\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:creditRating ; rr:objectMap [ rr:column "\"CREDIT_RATING\"" ] ] .

<#RetailCustomerMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:sqlQuery "SELECT \"CUST_ID\", \"FULL_NAME\", \"DOMICILE\" FROM \"PUBLIC\".\"CUSTOMER\" WHERE \"CUST_TYPE\" = 'RETAIL'" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/customer/](https://example.org/fibo-vkg/data/customer/){CUST_ID}" ; rr:class ex-fibo:RetailCustomer ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:customerName ; rr:objectMap [ rr:column "\"FULL_NAME\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:domicileCountry ; rr:objectMap [ rr:column "\"DOMICILE\"" ] ] .

<#CorporateCustomerMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:sqlQuery "SELECT \"CUST_ID\", \"FULL_NAME\", \"DOMICILE\" FROM \"PUBLIC\".\"CUSTOMER\" WHERE \"CUST_TYPE\" = 'CORP'" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/customer/](https://example.org/fibo-vkg/data/customer/){CUST_ID}" ; rr:class ex-fibo:CorporateCustomer ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:customerName ; rr:objectMap [ rr:column "\"FULL_NAME\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:domicileCountry ; rr:objectMap [ rr:column "\"DOMICILE\"" ] ] .

<#AccountMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"ACCOUNT\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/account/](https://example.org/fibo-vkg/data/account/){ACC_ID}" ; rr:class fibo-fbc-pas-caa:InvestmentAccount ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:accountNumber ; rr:objectMap [ rr:column "\"ACC_NUMBER\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:cashBalance ; rr:objectMap [ rr:column "\"CASH_BALANCE\"" ; rr:datatype xsd:decimal ] ] .

<#CustomerAccountLink> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"ACCOUNT\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/customer/](https://example.org/fibo-vkg/data/customer/){CUST_ID}" ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:hasAccount ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/account/](https://example.org/fibo-vkg/data/account/){ACC_ID}" ] ] .

<#HoldingMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"HOLDING\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/holding/](https://example.org/fibo-vkg/data/holding/){HOLDING_ID}" ; rr:class fibo-sec-sec-ast:PortfolioHolding ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:holdingQuantity ; rr:objectMap [ rr:column "\"QUANTITY\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:purchasePrice ; rr:objectMap [ rr:column "\"PURCHASE_PRICE\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:holdsSecurity ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/security/](https://example.org/fibo-vkg/data/security/){SEC_ID}" ] ] .

<#AccountHoldingLink> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"HOLDING\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/account/](https://example.org/fibo-vkg/data/account/){ACC_ID}" ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:hasHolding ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/holding/](https://example.org/fibo-vkg/data/holding/){HOLDING_ID}" ] ] .

<#TradeOrderMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"TRADE_ORDER\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/order/](https://example.org/fibo-vkg/data/order/){ORDER_ID}" ; rr:class fibo-fbc-pas-fpas:TradeOrder ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:orderType ; rr:objectMap [ rr:column "\"ORDER_TYPE\"" ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:orderQuantity ; rr:objectMap [ rr:column "\"ORDER_QTY\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:ordersSecurity ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/security/](https://example.org/fibo-vkg/data/security/){SEC_ID}" ] ] .

<#AccountOrderLink> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"TRADE_ORDER\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/account/](https://example.org/fibo-vkg/data/account/){ACC_ID}" ] ;
    rr:predicateObjectMap [ rr:predicate ex-fibo:hasTradeOrder ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/order/](https://example.org/fibo-vkg/data/order/){ORDER_ID}" ] ] .

<#FinancialReportMapping> a rr:TriplesMap ;
    rr:logicalTable [ rr:tableName "\"PUBLIC\".\"FIN_REPORT\"" ] ;
    rr:subjectMap [ rr:template "[https://example.org/fibo-vkg/data/report/](https://example.org/fibo-vkg/data/report/){REPORT_ID}" ; rr:class fro-sec:FinancialReport ] ;
    rr:predicateObjectMap [ rr:predicate fro-sec:fiscalYear ; rr:objectMap [ rr:column "\"FISCAL_YEAR\"" ; rr:datatype xsd:integer ] ] ;
    rr:predicateObjectMap [ rr:predicate fro-sec:revenueUSD ; rr:objectMap [ rr:column "\"REVENUE_USD\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate fro-sec:netIncomeUSD ; rr:objectMap [ rr:column "\"NET_INCOME_USD\"" ; rr:datatype xsd:decimal ] ] ;
    rr:predicateObjectMap [ rr:predicate fro-sec:reportedBy ; rr:objectMap [ rr:template "[https://example.org/fibo-vkg/data/company/](https://example.org/fibo-vkg/data/company/){COMP_ID}" ] ] .
```

### 4.3 Static Relational Metadata (`vkg-artifacts/db-metadata.json`)
Refer to the full JSON payload in Section 4.3 of the specification for `PUBLIC.COMPANY`, `PUBLIC.EXCHANGE`, `PUBLIC.SECURITY`, `PUBLIC.STOCK`, `PUBLIC.BOND`, `PUBLIC.CUSTOMER`, `PUBLIC.ACCOUNT`, `PUBLIC.HOLDING`, `PUBLIC.TRADE_ORDER`, and `PUBLIC.FIN_REPORT`.

---

## 5. Implementation Checklist & Definition of Done (DoD)

1. **Network Isolation Verification:** Disable external network access on `ontop-sidecar` and `sparql2sql-service` to verify that `POST /v1/compile` succeeds when `demo-sandbox` (DuckDB) is completely stopped.
2. **Latency SLA:** P95 compilation latency for Queries 1–4 must be under 20 ms on warm requests.
3. **Dialect Compatibility Check:** Passing `"target_dialect": "duckdb"` in `POST /v1/compile` must produce SQL that executes with zero syntax modifications against `fiben_demo.duckdb`.
4. **Automated CI Test:** `pytest` suite runs all 4 SPARQL queries against the compiler endpoint, parses the returned SQL via `sqlglot.parse_one()`, asserts the expected table join count, and executes the compiled SQL against the DuckDB fixture.