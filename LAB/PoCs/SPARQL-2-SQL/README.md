# FIBO VKG SPARQL-to-SQL compiler: PoC and feasibility report

Implements `SPARQL-2-SQL PoC.md` to find out whether the design is technically feasible.

**Verdict: feasible, with one architectural change.** FIBO SPARQL compiles offline into SQL for four dialects. The compiled SQL runs unmodified on DuckDB and returns the same rows as an independent SPARQL evaluation. Warm P95 latency is 4.5–5.5 ms against a 20 ms target. The change: Ontop's stock `/ontop/reformulate` endpoint opens a database connection even to reformulate, so the "no database connection" requirement can't be met with it. A 200-line sidecar that calls Ontop's reformulator directly (same Ontop 5.5.0 jars) meets it.

All results below were measured on 2026-10-14/15 (Windows 11, Docker Desktop 29.6, Ontop 5.5.0, sqlglot 30.22, DuckDB 1.5.6).

## Definition of Done

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | `POST /v1/compile` works with no database and no network | **met** | `make verify`. The sidecar and compiler sit only on `compile-net` (`internal: true`). No database or sandbox container is running. Egress from the network times out. The full suite passes from inside it. |
| 2 | P95 warm compile latency < 20 ms (Q1–Q4) | **met: 4.5 / 4.7 / 4.8 / 5.5 ms** | Deployed service, 50 calls per query after 5 warm-ups. Ontop itself takes ~1 ms of that. |
| 3 | DuckDB SQL runs with zero modifications | **met** | Every query is executed verbatim on the DuckDB fixture. |
| 4 | pytest: compile, `sqlglot.parse_one`, join count, execute | **met, and extended** | `compiler-service/tests/test_fibo_compilation.py`, 12 tests. Beyond the spec, each query's rows are compared with an **oracle**: the DuckDB data materialised to RDF through the same R2RML mapping, reasoned over with the TBox's subclass axioms, and queried with rdflib. Matching rows mean the meaning is preserved, not just the syntax. |

The spec refers to "Queries 1–4" but never defines them. They are defined in `compiler-service/app/queries.py`:

| Query | What it covers | Tables (joins) |
|---|---|---|
| Q1 | NYSE-listed shares, issuer, price: 4-way join, constant filter | STOCK, SECURITY, COMPANY, EXCHANGE (3) |
| Q2 | Customer holdings: `Customer` is inferred from the Retail and Corporate subclasses (OWL 2 QL reasoning) | CUSTOMER, ACCOUNT, HOLDING, SECURITY (3) |
| Q3 | All securities, `OPTIONAL` bond and equity attributes (LEFT JOIN) | SECURITY, BOND, STOCK (2) |
| Q4 | Revenue and net income per company since 2022: `SUM`, `GROUP BY`, numeric `FILTER`, `ORDER BY DESC` aggregate | FIN_REPORT, COMPANY (1) |

## Findings

1. **The stock Ontop endpoint can't compile offline.** `ontop/ontop:5.5.0` serves `/ontop/reformulate` only in `--dev` mode, and only after opening a JDBC connection: `UnknownHostException` when no database is reachable, even with `--db-metadata` and `--lazy`. `ontop-sidecar/src/OfflineReformulator.java` instead drives `QueryReformulator` directly from the ontology, the mapping and `db-metadata.json`. It never opens a connection, and it runs on the official image's jars. **This is the one change to the spec's architecture.**
2. **Ontop's SQL is not yet the answer.** The native query returns raw columns; Ontop builds IRIs and RDF literals in Java afterwards. The compiler therefore rewrites the SELECT list, using the term structure the sidecar returns:
   - IRI templates become SQL concatenation;
   - literals become their typed columns;
   - SPARQL `CONCAT` becomes `||`.

   `WHERE`, `GROUP BY` and `ORDER BY` are left exactly as Ontop wrote them. Terms outside that set are rejected with HTTP 422 rather than mistranslated.
3. **Spec defects fixed:**
   - The Turtle in the spec is markdown-mangled (`[iri](iri)`) and doesn't parse; it's repaired in `vkg-artifacts/`.
   - The R2RML templates used unquoted `{COMP_ID}`. PostgreSQL lower-cases unquoted names, so Ontop rejected the mapping ("placeholder HOLDING_ID does not occur in source query"); the templates now use `{"COMP_ID"}`.
   - `db-metadata.json` was only referenced, never given. It is now **extracted by Ontop** from a throwaway PostgreSQL loaded with the DDL (`make metadata`, build time only).
4. **A cross-dialect precision bug, caught and fixed.** Ontop writes `CAST(x AS DECIMAL)`, which is unbounded in PostgreSQL, but:
   - **Snowflake:** it means `NUMBER(38,0)`, so fractions are silently dropped;
   - **DuckDB:** it means `DECIMAL(18,3)`, which overflows above ~10^15.

   The compiler pins `DECIMAL(38,6)`, and a test checks every dialect. **sqlglot transpiles syntax; it does not guarantee numeric semantics. Every dialect needs a check like this.**
5. **Latency traps:**
   - POSTing to the JDK HTTP server stalled ~50 ms on a delayed ACK; the compiler now sends a single-write GET.
   - rdflib's SPARQL parser costs ~16 ms per query, almost the whole budget. Validation is memoised by query text. With a cold cache, P95 is 15–44 ms, so **a never-seen query can miss the 20 ms SLA** unless validation moves to Ontop's own (RDF4J) parser.
   - Cold start: the sidecar loads in ~1.5 s, and the first compile after start took ~170 ms (JVM warm-up).
6. **Coverage beyond Q1–Q4** (`python tools/probe_coverage.py`). Each probe query was compiled, executed on DuckDB and compared with the oracle:
   - **Matched the oracle:** returning IRIs, multi-level subclass reasoning, `DISTINCT`, `LIMIT`/`OFFSET`, `COUNT`, `UNION`, regex `FILTER`, `FILTER NOT EXISTS`, `MINUS`, `BIND` + `CONCAT`, `VALUES`, sequence property paths, and an unbound predicate (`?s ?p ?o`).
   - **The one disagreement is the oracle's error:** for a subquery with `GROUP BY`, the SQL is correct. rdflib evaluates the subquery against the outer bindings and adds two rows with an empty total.

   Full table: `tools/coverage.md`.
7. **Not demonstrated:**
   - Queries that Ontop can't push into one SQL statement (it would return several native queries) are rejected with 422; none of the probes hit this.
   - Only OWL 2 QL reasoning is covered, which is Ontop's scope.
   - Snowflake and BigQuery output is checked by re-parsing with sqlglot, **not executed on those engines**.
   - The demo data is **illustrative**, not the IBM FIBEN benchmark (see `demo-sandbox/seed_duckdb.py`). FIBEN's published schema is wider than the spec's 10-table slice. Company names, CIK and SIC codes and tickers are real; prices and fiscal figures are rounded approximations.

## R2RML mapping specification

The mapping is specified declaratively in `vkg-artifacts/mapping-spec.yaml`, and
`fiben-mappings.r2rml.ttl` is generated from it. **Edit the spec, not the Turtle.**

* **Spec.** The spec declares entities (IRI path and key), then triples maps. Each map has a table, a subject entity and a class, plus literal properties (column, datatype) and links (`ref` to another entity).
* **Conventions.** The generator applies them, so they can't be broken by hand:
  * one subject template per entity, keyed by its table's primary key;
  * every identifier and placeholder is double-quoted;
  * a `filter` becomes an `rr:sqlQuery` view that selects exactly the columns the map uses (subclass by filter, e.g. `RetailCustomer`);
  * a relationship stored as a foreign key on the other table becomes a class-less link map.
* **Generator.** `tools/build_mappings.py` validates the spec's structure and renders the Turtle. `--check` fails if the committed Turtle is stale. The first build reproduced the hand-written mapping byte for byte.
* **Conformance.** `tools/check_mappings.py` checks any R2RML graph against `db-metadata.json` and the TBox with 12 rules:

  | rule | checks |
  |---|---|
  | M01 | the logical table resolves to one table in the metadata |
  | M02 | every referenced column exists, and is selected by an `rr:sqlQuery` |
  | M03 | identifiers and template placeholders are quoted |
  | M04 | a typed subject is keyed by a unique key of its table |
  | M05 | an IRI used outside its typing table follows a foreign key to that table's key |
  | M06 | every IRI template family is typed by some map |
  | M07 | classes and predicates are declared in the TBox |
  | M08 | template objects use object properties; column objects use datatype properties |
  | M09 | the literal datatype matches the TBox range and the column's SQL type |
  | M10 | subjects and objects are compatible with `rdfs:domain` / `rdfs:range` |
  | M11 | subject columns are NOT NULL (warning) |
  | M12 | coverage: unmapped tables and columns (info, `--coverage`) |

  Results:
  * **This PoC's mapping:** 0 errors and 0 warnings. Coverage lists 15 columns the spec's §2 names but the mapping doesn't use yet, e.g. `COUNTRY_INC`, `MATURITY_DATE`, `TRADE_DATE`, `TOTAL_ASSETS_USD`.
  * **The 152-table mapping generated by the FIBO NL2Q PoC** (`../FIBO-NL2Q-at-Scale/artifacts/ontop/`): also clean, in 0.6 s (152 maps, 222 predicate-object maps, 24 foreign-key links).
* **Tests.** `compiler-service/tests/test_mappings.py` has 23 offline tests:
  * the Turtle is current;
  * the mapping conforms;
  * each rule fires on a defect introduced in the spec or by a hand edit of the Turtle, including the unquoted-placeholder defect this PoC first hit;
  * the generator rejects malformed specs.

  They run in `make verify` too.

```bash
make mappings          # python tools/build_mappings.py
make check-mappings    # --check, then the conformance report with coverage
```

## Layout

```
SPARQL-2-SQL/
├── SPARQL-2-SQL PoC.md            the specification
├── NL2SPARQL-ASSESSMENT.md        next layer: NL -> SPARQL, critical assessment, design, evaluation plan
├── docker-compose.yml             compilation plane: sidecar + compiler on an internal network (+ verifier)
├── docker-compose.demo.yml        overlay: Streamlit sandbox + DuckDB, compiler API on :8000
├── Makefile
├── vkg-artifacts/                 fibo-subset.ttl, mapping-spec.yaml (R2RML source of truth),
│   │                              fiben-mappings.r2rml.ttl (generated), db-metadata.json (extracted),
│   │                              ontop.properties (offline), extract.properties (build only)
│   └── jdbc/                      PostgreSQL JDBC driver (only for `make metadata`)
├── ontop-sidecar/                 OfflineReformulator.java + Dockerfile (Ontop 5.5.0 jars)
├── compiler-service/
│   ├── app/                       main.py (FastAPI), compiler.py, models.py, queries.py (Q1–Q4)
│   └── tests/                     test_fibo_compilation.py, oracle.py, test_mappings.py
├── demo-sandbox/                  ddl/, seed_duckdb.py, ui.py, queries.py (copy, drift-tested)
└── tools/                         build_mappings.py, check_mappings.py, extract_db_metadata.sh,
                                   verify_isolation.sh, probe_coverage.py
```

## Running it

Needs Docker; Ontop runs in containers, so no local Java is required. Local Python needs `fastapi`, `uvicorn`, `sqlglot`, `rdflib`, `duckdb`, `pytest`.

```bash
make verify        # DoD 1-4 inside the isolated network (builds everything)
make demo          # + sandbox: http://localhost:8501, API docs: http://localhost:8000/docs
make sidecar-dev   # sidecar on localhost:18080 for local work, then:
make test          # pytest in-process (the latency SLA is asserted only in `make verify`)
python tools/probe_coverage.py
make down
```

```bash
curl -s localhost:8000/v1/compile -H 'Content-Type: application/json' \
  -d '{"sparql": "PREFIX ex-fibo: <https://example.org/fibo-vkg/voc#> SELECT ?n WHERE { ?c ex-fibo:legalName ?n }", "target_dialect": "snowflake"}'
```
