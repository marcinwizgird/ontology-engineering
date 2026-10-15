"""Coverage probe: SPARQL features beyond Queries 1-4, each compiled, executed on DuckDB and
compared with the oracle (R2RML materialisation + subclass reasoning + rdflib).

    python tools/probe_coverage.py            # needs `make sidecar-dev`
Writes tools/coverage.md and prints the table.
"""

from __future__ import annotations

import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "compiler-service"), str(ROOT / "compiler-service" / "tests"),
                str(ROOT / "demo-sandbox")]

import duckdb  # noqa: E402

import oracle  # noqa: E402
import seed_duckdb  # noqa: E402
from app.compiler import CompileError, compile_sparql  # noqa: E402
from app.queries import PREFIXES  # noqa: E402

P = PREFIXES
PROBES = [
    ("IRI in the result", "SELECT ?issuer ?name WHERE { ?issuer a fibo-be-le-cb:Corporation ; ex-fibo:legalName ?name } ORDER BY ?name"),
    ("superclass of a superclass (LegalPerson)", "SELECT ?name WHERE { ?x a fibo-be-le-lp:LegalPerson ; ex-fibo:legalName ?name } ORDER BY ?name"),
    ("DISTINCT", "SELECT DISTINCT ?type WHERE { ?c a fibo-fbc-pas-caa:Customer ; ex-fibo:domicileCountry ?type } ORDER BY ?type"),
    ("LIMIT / OFFSET", "SELECT ?t WHERE { ?s ex-fibo:tickerSymbol ?t } ORDER BY ?t LIMIT 3 OFFSET 2"),
    ("COUNT + GROUP BY", "SELECT ?ex (COUNT(?s) AS ?n) WHERE { ?s ex-fibo:listedOn ?e . ?e ex-fibo:exchangeSymbol ?ex } GROUP BY ?ex ORDER BY ?ex"),
    ("UNION", "SELECT ?t WHERE { { ?s a fibo-sec-dbt-bnd:Bond } UNION { ?s a fibo-sec-eq-eq:ListedShare ; ex-fibo:peRatio ?pe FILTER(?pe > 30) } ?s ex-fibo:tickerSymbol ?t } ORDER BY ?t"),
    ("FILTER regex", 'SELECT ?n WHERE { ?c ex-fibo:legalName ?n FILTER(REGEX(?n, "^J")) } ORDER BY ?n'),
    ("FILTER NOT EXISTS", "SELECT ?t WHERE { ?s ex-fibo:tickerSymbol ?t FILTER NOT EXISTS { ?h ex-fibo:holdsSecurity ?s } } ORDER BY ?t"),
    ("MINUS", "SELECT ?t WHERE { ?s ex-fibo:tickerSymbol ?t MINUS { ?s a fibo-sec-dbt-bnd:Bond } } ORDER BY ?t"),
    ("BIND + CONCAT", 'SELECT ?label WHERE { ?s ex-fibo:tickerSymbol ?t ; ex-fibo:lastPrice ?p BIND(CONCAT(?t, ":", STR(?p)) AS ?label) } ORDER BY ?label'),
    ("VALUES", 'SELECT ?n WHERE { VALUES ?t { "JPM" "GS" } ?s ex-fibo:tickerSymbol ?t ; ex-fibo:issuedBy ?c . ?c ex-fibo:legalName ?n } ORDER BY ?n'),
    ("property path (/)", "SELECT ?t WHERE { ?acc ex-fibo:hasHolding/ex-fibo:holdsSecurity/ex-fibo:tickerSymbol ?t } ORDER BY ?t"),
    ("subquery", "SELECT ?n ?total WHERE { ?c ex-fibo:legalName ?n { SELECT ?c (SUM(?r) AS ?total) WHERE { ?f fro-sec:reportedBy ?c ; fro-sec:revenueUSD ?r } GROUP BY ?c } } ORDER BY DESC(?total)"),
    ("unbound predicate (?p)", "SELECT ?p WHERE { ?s ?p ?o . ?s a fibo-sec-dbt-bnd:Bond } ORDER BY ?p"),
]


#: Disagreements investigated and found to be the oracle's fault, not the compiler's.
KNOWN_ORACLE_ERRORS = {
    "subquery": "the SQL is right: GROUP BY ?c yields only the 6 companies with reports; "
                "rdflib evaluates the subquery correlated with the outer ?c and adds 2 rows "
                "with an unbound total",
}


def _norm(rows):
    return sorted((tuple(Decimal(str(v)) if isinstance(v, (int, float, Decimal)) else v for v in r)
                   for r in rows), key=repr)


def main() -> None:
    db = seed_duckdb.seed(Path(tempfile.mkdtemp()) / "probe.duckdb")
    con = duckdb.connect(str(db), read_only=True)
    kg = oracle.reason(oracle.materialise(con))
    lines = ["| feature | compiles | runs on DuckDB | matches oracle | note |", "|---|---|---|---|---|"]
    for name, body in PROBES:
        q = P + body
        try:
            c = compile_sparql(q, "duckdb")
        except CompileError as exc:
            lines.append(f"| {name} | no | - | - | {exc.stage}: {str(exc)[:110]} |")
            continue
        try:
            got = _norm(con.execute(c.sql).fetchall())
        except duckdb.Error as exc:
            lines.append(f"| {name} | yes | **no** | - | {str(exc).splitlines()[0][:110]} |")
            continue
        exp = _norm(oracle.answer(kg, q))
        ok = got == exp
        note = f"{len(got)} rows" if ok else f"SQL {len(got)} rows vs oracle {len(exp)}"
        if name in KNOWN_ORACLE_ERRORS and not ok:
            note += f" -- {KNOWN_ORACLE_ERRORS[name]}"
        lines.append(f"| {name} | yes | yes | {'yes' if ok else '**no**'} | {note} |")
    table = "\n".join(lines)
    (ROOT / "tools" / "coverage.md").write_text(table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
