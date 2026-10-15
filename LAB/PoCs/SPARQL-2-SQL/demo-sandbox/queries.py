"""The four FIBO acceptance queries (spec section 5 refers to "Queries 1-4" without listing
them; these are the PoC's definition, chosen to cover the features a VKG compiler must get
right). Each entry: id, title, SPARQL, the base tables the SQL must touch, and what it tests.
"""

PREFIXES = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX fibo-be-le-cb: <https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/>
PREFIX fibo-be-le-lp: <https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/LegalPersons/>
PREFIX fibo-fbc-fct-mkt: <https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/Markets/>
PREFIX fibo-fbc-pas-caa: <https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/>
PREFIX fibo-sec-sec-iss: <https://spec.edmcouncil.org/fibo/ontology/SEC/Securities/SecuritiesIssuance/>
PREFIX fibo-sec-eq-eq: <https://spec.edmcouncil.org/fibo/ontology/SEC/Equities/EquityInstruments/>
PREFIX fibo-sec-dbt-bnd: <https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/>
PREFIX fro-sec: <http://finregont.com/fro/sec/SEC_Filings.ttl#>
PREFIX ex-fibo: <https://example.org/fibo-vkg/voc#>
"""

QUERIES = [
    {
        "id": "Q1",
        "title": "Listed shares traded on NYSE, with issuer and last price",
        "tests": "4-way join through two object properties; constant filter on a data property",
        "sparql": PREFIXES + """
SELECT ?ticker ?issuerName ?price WHERE {
  ?share a fibo-sec-eq-eq:ListedShare ;
         ex-fibo:tickerSymbol ?ticker ;
         ex-fibo:lastPrice ?price ;
         ex-fibo:issuedBy ?issuer ;
         ex-fibo:listedOn ?exchange .
  ?issuer ex-fibo:legalName ?issuerName .
  ?exchange ex-fibo:exchangeSymbol "NYSE" .
}
ORDER BY ?ticker""",
        "tables": {"STOCK", "SECURITY", "COMPANY", "EXCHANGE"},
    },
    {
        "id": "Q2",
        "title": "Every customer's holdings (Customer is inferred from Retail/Corporate subclasses)",
        "tests": "OWL 2 QL reasoning: rdfs:subClassOf expands Customer into both mapping views",
        "sparql": PREFIXES + """
SELECT ?customerName ?accountNumber ?ticker ?quantity WHERE {
  ?customer a fibo-fbc-pas-caa:Customer ;
            ex-fibo:customerName ?customerName ;
            ex-fibo:hasAccount ?account .
  ?account ex-fibo:accountNumber ?accountNumber ;
           ex-fibo:hasHolding ?holding .
  ?holding ex-fibo:holdsSecurity ?security ;
           ex-fibo:holdingQuantity ?quantity .
  ?security ex-fibo:tickerSymbol ?ticker .
}
ORDER BY ?customerName ?ticker""",
        "tables": {"CUSTOMER", "ACCOUNT", "HOLDING", "SECURITY"},
    },
    {
        "id": "Q3",
        "title": "All securities with optional bond and equity attributes",
        "tests": "OPTIONAL -> LEFT JOIN; class hierarchy (ListedShare, Bond are Securities)",
        "sparql": PREFIXES + """
SELECT ?ticker ?name ?coupon ?rating ?pe WHERE {
  ?security a fibo-sec-sec-iss:Security ;
            ex-fibo:tickerSymbol ?ticker ;
            ex-fibo:securityName ?name .
  OPTIONAL { ?security ex-fibo:couponRate ?coupon ; ex-fibo:creditRating ?rating . }
  OPTIONAL { ?security ex-fibo:peRatio ?pe . }
}
ORDER BY ?ticker ?name""",
        "tables": {"SECURITY", "BOND", "STOCK"},
    },
    {
        "id": "Q4",
        "title": "Total revenue and net income per company since fiscal 2022",
        "tests": "GROUP BY + SUM aggregates, numeric FILTER, ORDER BY DESC on an aggregate",
        "sparql": PREFIXES + """
SELECT ?company (SUM(?revenue) AS ?totalRevenue) (SUM(?netIncome) AS ?totalNetIncome) WHERE {
  ?report a fro-sec:FinancialReport ;
          fro-sec:reportedBy ?corp ;
          fro-sec:fiscalYear ?year ;
          fro-sec:revenueUSD ?revenue ;
          fro-sec:netIncomeUSD ?netIncome .
  ?corp ex-fibo:legalName ?company .
  FILTER (?year >= 2022)
}
GROUP BY ?company
ORDER BY DESC(?totalRevenue)""",
        "tables": {"FIN_REPORT", "COMPANY"},
    },
]

BY_ID = {q["id"]: q for q in QUERIES}
