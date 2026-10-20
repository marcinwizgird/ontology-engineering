"""Curated local knowledge (knowledge arm K4): what FIBO does not say about *this* data.

FIBO defines concepts; it does not define this database's codes, which classes carry a
business measure, or how a business phrase maps onto a path. That knowledge is curated
by the data owner. Here it was written by the PoC engineer from the schema, the data
profile and domain knowledge — **after** having seen FIBEN's gold SQL, so it may carry
benchmark knowledge; the knowledge ablation (with and without this glossary) measures
its contribution, and the transfer set (no glossary authored from its gold) bounds it.

Every entry names ontology terms (local names in the ``fiben:`` namespace) so it can be
checked against the ontology and rendered into prompts.
"""

from __future__ import annotations

GLOSSARY: list[dict] = [
    # ---- business synonyms: everyday words the formal labels lack ----------------
    {"term": "stock / stocks / share / shares / equity security / security", "kind": "synonym",
     "means": "ListedSecurity", "uses": ["ListedSecurity"]},
    {"term": "company / companies / firm / corporation / issuer / business", "kind": "synonym",
     "means": "Corporation", "uses": ["Corporation"]},
    {"term": "customer / client / investor / account holder / person / people / someone / individual", "kind": "synonym",
     "means": "Person (in a role: account owner, manager, contract party)", "uses": ["Person"]},
    {"term": "account / brokerage account / portfolio", "kind": "synonym",
     "means": "FinancialServiceAccount", "uses": ["FinancialServiceAccount"]},
    {"term": "trade / trades / transaction / order", "kind": "synonym",
     "means": "SecuritiesTransaction", "uses": ["SecuritiesTransaction"]},
    {"term": "position / holding / holdings / owns shares", "kind": "synonym",
     "means": "Holding", "uses": ["Holding"]},
    {"term": "nationality / citizen", "kind": "synonym", "means": "hasCitizenship -> Country",
     "uses": ["hasCitizenship", "Country"]},
    {"term": "live / lives / state / city / located", "kind": "synonym",
     "means": "PostalAddress hasState / hasCity", "uses": ["PostalAddress", "hasState", "hasCity"]},
    {"term": "name of a company / company name", "kind": "synonym", "means": "hasLegalName",
     "uses": ["hasLegalName"]},
    {"term": "name of a person / full name", "kind": "synonym", "means": "hasPersonName",
     "uses": ["hasPersonName"]},
    {"term": "date / when", "kind": "synonym", "means": "hasSettlementDate (trades), hasListingDate (stocks)",
     "uses": ["hasSettlementDate", "hasListingDate"]},
    {"term": "price / value / worth", "kind": "synonym", "means": "MonetaryAmount hasAmount",
     "uses": ["MonetaryAmount", "hasAmount"]},
    {"term": "job / role / title / works", "kind": "synonym", "means": "Contract hasTitle / hasPosition",
     "uses": ["Contract", "hasTitle", "hasPosition"]},
    # ---- codes and enumerations -------------------------------------------------
    {"term": "buy / purchase / bought", "kind": "code",
     "means": 'SecuritiesTransaction with hasType = "1"', "uses": ["SecuritiesTransaction", "hasType"]},
    {"term": "sell / sale / sold", "kind": "code",
     "means": 'SecuritiesTransaction with hasType = "2"', "uses": ["SecuritiesTransaction", "hasType"]},
    {"term": "annual / yearly figure", "kind": "code",
     "means": 'ElementOfFinancialStatement with applicablePeriod = "yearly"',
     "uses": ["ElementOfFinancialStatement", "applicablePeriod"]},
    {"term": "quarterly figure", "kind": "code",
     "means": 'ElementOfFinancialStatement with applicablePeriod = "quarterly"; quarter in hasMetricEndQuarter ("Q1".."Q4")',
     "uses": ["ElementOfFinancialStatement", "applicablePeriod", "hasMetricEndQuarter"]},
    {"term": "annual report / quarterly report", "kind": "code",
     "means": 'hasDocumentType "10-K" (annual) or "10-Q" (quarterly)', "uses": ["hasDocumentType"]},
    {"term": "stock exchange / market", "kind": "code",
     "means": 'FinancialMarket, hasName one of "NYSE", "NASDAQ", "AMEX"', "uses": ["FinancialMarket", "hasName"]},
    {"term": "officer / director", "kind": "code",
     "means": 'Contract.hasPosition "Officer" or "Director"; job title in Contract.hasTitle (e.g. "CHIEF EXECUTIVE OFFICER")',
     "uses": ["Contract", "hasPosition", "hasTitle"]},
    # ---- measures: which class carries a business figure ------------------------
    {"term": "revenue / sales", "kind": "measure",
     "means": "Revenue element (a subclass of ElementOfFinancialStatement); the amount is hasMetricValue, the year hasMetricYearFiscal",
     "uses": ["Revenue", "hasMetricValue", "hasMetricYearFiscal"]},
    {"term": "net income / profit / earnings", "kind": "measure",
     "means": "ComprehensiveIncome element; amount in hasMetricValue", "uses": ["ComprehensiveIncome", "hasMetricValue"]},
    {"term": "loss", "kind": "measure", "means": "Loss element; amount in hasMetricValue", "uses": ["Loss", "hasMetricValue"]},
    {"term": "assets", "kind": "measure", "means": "Asset element; amount in hasMetricValue", "uses": ["Asset", "hasMetricValue"]},
    {"term": "liabilities", "kind": "measure", "means": "Liability element; amount in hasMetricValue", "uses": ["Liability", "hasMetricValue"]},
    {"term": "equity", "kind": "measure", "means": "Equity element; amount in hasMetricValue", "uses": ["Equity", "hasMetricValue"]},
    {"term": "expenses / costs", "kind": "measure", "means": "Expense element; amount in hasMetricValue", "uses": ["Expense", "hasMetricValue"]},
    {"term": "earnings per share / EPS", "kind": "measure",
     "means": "DistributionToOwner element (EarningsPerShareBasic); amount in hasMetricValue",
     "uses": ["DistributionToOwner", "hasMetricValue"]},
    {"term": "last traded value / stock price", "kind": "measure",
     "means": "ListedSecurity hasLastTradedValue -> MonetaryAmount hasAmount", "uses": ["ListedSecurity", "hasLastTradedValue", "MonetaryAmount", "hasAmount"]},
    {"term": "transaction price", "kind": "measure",
     "means": "SecuritiesTransaction hasPrice -> MonetaryAmount hasAmount", "uses": ["SecuritiesTransaction", "hasPrice", "MonetaryAmount", "hasAmount"]},
    {"term": "number of shares", "kind": "measure",
     "means": "hasCount on Holding (shares held) or on SecuritiesTransaction (shares traded)", "uses": ["Holding", "SecuritiesTransaction", "hasCount"]},
    # ---- paths: how a business phrase is realised -------------------------------
    {"term": "financial figures of a company", "kind": "path",
     "means": "ElementOfFinancialStatement isMemberOf FinancialReport (through ElementsOfFinancialReport) ; FinancialReport isProvidedBy Corporation",
     "uses": ["ElementOfFinancialStatement", "ElementsOfFinancialReport", "isMemberOf", "FinancialReport", "isProvidedBy", "Corporation"]},
    {"term": "customer / investor / account owner / account holder", "kind": "path",
     "means": "FinancialServiceAccount isOwnedBy Person", "uses": ["FinancialServiceAccount", "isOwnedBy", "Person"]},
    {"term": "account manager / broker", "kind": "path",
     "means": "FinancialServiceAccount isManagedBy Person", "uses": ["FinancialServiceAccount", "isManagedBy", "Person"]},
    {"term": "holdings of a customer", "kind": "path",
     "means": "Holding isHeldBy FinancialServiceAccount ; Holding refersTo ListedSecurity", "uses": ["Holding", "isHeldBy", "refersTo", "ListedSecurity"]},
    {"term": "trades of a customer", "kind": "path",
     "means": "SecuritiesTransaction isFacilitatedBy FinancialServiceAccount ; refersTo ListedSecurity ; hasSettlementDate",
     "uses": ["SecuritiesTransaction", "isFacilitatedBy", "refersTo", "hasSettlementDate"]},
    {"term": "issuer of a stock", "kind": "path",
     "means": "Security isProvidedBy Corporation (a ListedSecurity is a Security)", "uses": ["Security", "isProvidedBy", "Corporation", "ListedSecurity"]},
    {"term": "works for / employee of a company", "kind": "path",
     "means": "Contract hasContractParty ContractParty (a Person) ; Contract isManagedBy Corporation",
     "uses": ["Contract", "hasContractParty", "ContractParty", "isManagedBy", "Corporation"]},
    {"term": "industry of a company", "kind": "path",
     "means": "Corporation isClassifiedBy IndustrySectorClassifier (hasFormalName = industry division, hasDescription = SIC description)",
     "uses": ["Corporation", "isClassifiedBy", "IndustrySectorClassifier", "hasFormalName"]},
    {"term": "where someone lives / address", "kind": "path",
     "means": "Address isIndexTo AutonomousAgent (a Person or Corporation) ; Address postalAddress PostalAddress (hasCity, hasState)",
     "uses": ["Address", "isIndexTo", "postalAddress", "PostalAddress", "hasState", "hasCity"]},
    {"term": "country of incorporation / citizenship", "kind": "path",
     "means": "Corporation isDomiciledIn Country ; Person hasCitizenship Country ; Country hasName",
     "uses": ["Corporation", "isDomiciledIn", "Person", "hasCitizenship", "Country"]},
]
