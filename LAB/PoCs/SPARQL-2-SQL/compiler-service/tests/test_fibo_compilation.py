"""DoD item 4 (and 2, 3): compile the four FIBO queries through the API, check the SQL
structurally with sqlglot, execute it on the DuckDB fixture, and compare the rows with an
independent SPARQL answer over the materialised knowledge graph (tests/oracle.py).

Targets, in order of preference:
* ``COMPILER_URL`` set  -> the deployed compiler (docker compose; see tools/verify_isolation.sh);
* otherwise             -> the FastAPI app in-process, talking to the sidecar at
  ``ONTOP_SIDECAR_URL`` (default http://localhost:18080, `make sidecar-dev`).
The suite is skipped, with the reason, when neither is reachable.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
import sqlglot
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "demo-sandbox"))

from app.queries import QUERIES  # noqa: E402
import oracle  # noqa: E402
import seed_duckdb  # noqa: E402

COMPILER_URL = os.environ.get("COMPILER_URL")


class _Client:
    def __init__(self):
        if COMPILER_URL:
            self.mode = f"http {COMPILER_URL}"
        else:
            from fastapi.testclient import TestClient
            from app.main import app
            self.tc = TestClient(app)
            self.mode = "in-process"

    def post(self, payload: dict) -> tuple[int, dict]:
        if COMPILER_URL:
            req = urllib.request.Request(COMPILER_URL.rstrip("/") + "/v1/compile",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as e:
                return e.code, json.load(e)
        r = self.tc.post("/v1/compile", json=payload)
        return r.status_code, r.json()

    def health(self) -> dict:
        if COMPILER_URL:
            with urllib.request.urlopen(COMPILER_URL.rstrip("/") + "/health", timeout=10) as r:
                return json.load(r)
        return self.tc.get("/health").json()


@pytest.fixture(scope="session")
def client():
    c = _Client()
    try:
        ok = c.health().get("ontop_sidecar")
    except OSError as exc:
        pytest.skip(f"compiler not reachable ({c.mode}): {exc}")
    if not ok:
        pytest.skip(f"Ontop sidecar not reachable from the compiler ({c.mode}); run `make sidecar-dev`")
    return c


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    path = seed_duckdb.seed(tmp_path_factory.mktemp("duck") / "fiben_demo.duckdb")
    con = duckdb.connect(str(path), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def kg(db):
    return oracle.reason(oracle.materialise(db))


def _norm(rows):
    return [tuple(Decimal(str(v)) if isinstance(v, (int, float, Decimal)) else v for v in r)
            for r in rows]


@pytest.mark.parametrize("q", QUERIES, ids=[q["id"] for q in QUERIES])
def test_query_compiles_executes_and_matches_the_oracle(client, db, kg, q):
    status, body = client.post({"sparql": q["sparql"], "target_dialect": "duckdb"})
    assert status == 200, body
    tree = sqlglot.parse_one(body["sql"], read="duckdb")
    tables = [t for t in tree.find_all(exp.Table) if t.name]
    assert {t.name for t in tables} == q["tables"], body["sql"]
    assert len(tables) - 1 == len(q["tables"]) - 1 == body["join_count"]
    assert body["projection"] == [c.alias_or_name for c in tree.expressions]
    got = _norm(db.execute(body["sql"]).fetchall())              # DoD 3: zero modifications
    expected = _norm(oracle.answer(kg, q["sparql"]))
    assert got, "the query must return rows on the fixture"
    assert got == expected


@pytest.mark.parametrize("dialect", ["postgres", "snowflake", "bigquery", "duckdb"])
def test_every_dialect_round_trips_through_sqlglot(client, dialect):
    for q in QUERIES:
        status, body = client.post({"sparql": q["sparql"], "target_dialect": dialect})
        assert status == 200 and body["target_dialect"] == dialect
        reparsed = sqlglot.parse_one(body["sql"], read=dialect)
        assert {t.name for t in reparsed.find_all(exp.Table) if t.name} == q["tables"]


def test_aggregates_keep_their_fractions_in_every_dialect(client):
    """Ontop's bare CAST(.. AS DECIMAL) means NUMBER(38,0) in Snowflake: pinned to (38, 6)."""
    for dialect in ("snowflake", "bigquery", "duckdb", "postgres"):
        _, body = client.post({"sparql": QUERIES[3]["sparql"], "target_dialect": dialect})
        casts = list(sqlglot.parse_one(body["sql"], read=dialect).find_all(exp.Cast))
        assert casts, body["sql"]
        if dialect == "bigquery":       # BigQuery NUMERIC is always NUMERIC(38, 9)
            assert all("NUMERIC" in c.to.sql(dialect="bigquery") for c in casts), body["sql"]
        else:
            assert all(c.to.expressions for c in casts), (dialect, body["sql"])


def test_invalid_and_unsupported_requests(client):
    status, body = client.post({"sparql": "SELECT ?x WHERE { ?x a }", "target_dialect": "duckdb"})
    assert status == 400 and body["stage"] == "validate"
    status, body = client.post({"sparql": "ASK { ?x ?p ?o }", "target_dialect": "duckdb"})
    assert status == 400 and "SELECT" in body["detail"]
    status, body = client.post({"sparql": QUERIES[0]["sparql"], "target_dialect": "oracle"})
    assert status == 422          # pydantic rejects an unknown dialect


def test_p95_warm_latency_under_20ms(client):
    """DoD 2: P95 of warm end-to-end compile calls, per query (50 calls after 5 warm-ups)."""
    report = {}
    for q in QUERIES:
        payload = {"sparql": q["sparql"], "target_dialect": "duckdb"}
        for _ in range(5):
            client.post(payload)
        samples = []
        for _ in range(50):
            t = time.perf_counter()
            status, _ = client.post(payload)
            samples.append((time.perf_counter() - t) * 1e3)
            assert status == 200
        report[q["id"]] = round(statistics.quantiles(samples, n=20)[18], 2)
    print(f"\nP95 warm compile latency ({client.mode}): {report} ms")
    if not COMPILER_URL:
        # in-process mode reaches the sidecar through Docker Desktop's port forwarder, not
        # the container network the service runs on: report, but judge the SLA deployed
        pytest.skip(f"SLA is asserted against the deployed service (make verify); "
                    f"in-process P95 {report}")
    assert all(v < 20 for v in report.values()), report


def test_demo_sandbox_ships_the_same_queries():
    """The sandbox container carries its own copy of app/queries.py; they must not drift."""
    demo = ROOT.parent / "demo-sandbox" / "queries.py"
    if not demo.exists():
        pytest.skip("demo-sandbox not present in this image")
    assert demo.read_text(encoding="utf-8") == (ROOT / "app" / "queries.py").read_text(encoding="utf-8")
