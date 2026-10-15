"""Stakeholder sandbox: SPARQL -> compiled SQL -> rows, side by side.

The compiler is called over HTTP exactly as a production client would; the DuckDB file is
local to this container and the compiler never sees it.

    streamlit run ui.py      (COMPILER_URL, DUCKDB_PATH from the environment)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from queries import QUERIES

COMPILER_URL = os.environ.get("COMPILER_URL", "http://localhost:8000")
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", str(Path(__file__).with_name("fiben_demo.duckdb")))


def compile_sparql(sparql: str, dialect: str) -> tuple[int, dict, float]:
    req = urllib.request.Request(f"{COMPILER_URL}/v1/compile",
                                 data=json.dumps({"sparql": sparql, "target_dialect": dialect}).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r), (time.perf_counter() - t) * 1e3
    except urllib.error.HTTPError as e:
        return e.code, json.load(e), (time.perf_counter() - t) * 1e3
    except urllib.error.URLError as e:
        return 503, {"stage": "network", "detail": str(e.reason)}, 0.0


st.set_page_config(page_title="FIBO VKG: SPARQL to SQL", layout="wide")
st.title("FIBO virtual knowledge graph: SPARQL to SQL")
st.caption(f"Compiler: {COMPILER_URL} (no database connection) · Sample data: {Path(DUCKDB_PATH).name} "
           "(illustrative rows; see seed_duckdb.py)")

with st.sidebar:
    choice = st.radio("Query", [f"{q['id']} · {q['title']}" for q in QUERIES] + ["Custom"])
    dialect = st.selectbox("Target dialect", ["duckdb", "postgres", "snowflake", "bigquery"])

preset = next((q for q in QUERIES if choice.startswith(q["id"])), None)
left, right = st.columns(2)
with left:
    st.subheader("SPARQL (FIBO vocabulary)")
    if preset:
        st.caption(f"Tests: {preset['tests']}")
    sparql = st.text_area("query", preset["sparql"] if preset else QUERIES[0]["sparql"],
                          height=420, label_visibility="collapsed")
    go = st.button("Compile", type="primary")

if go or "result" not in st.session_state or st.session_state.get("key") != (sparql, dialect):
    st.session_state.result = compile_sparql(sparql, dialect)
    st.session_state.key = (sparql, dialect)
status, body, wall_ms = st.session_state.result

with right:
    st.subheader(f"Compiled SQL ({dialect})")
    if status != 200:
        st.error(f"{body.get('stage', '?')}: {body.get('detail', body)}")
    else:
        st.code(body["sql"], language="sql")
        t = body["timings_ms"]
        st.caption(f"{wall_ms:.1f} ms round trip · compiler {t['total']:.1f} ms "
                   f"(Ontop {t['ontop_internal']:.2f} ms) · tables: {', '.join(body['tables'])} · "
                   f"joins: {body['join_count']}")
        with st.expander("Ontop's native PostgreSQL unfolding"):
            st.code(body["native_sql"], language="sql")

st.divider()
if status == 200 and st.button("Execute Compiled SQL on Sample Data"):
    sql = body["sql"]
    if dialect != "duckdb":       # run the DuckDB compilation of the same query
        s2, b2, _ = compile_sparql(sparql, "duckdb")
        sql = b2["sql"] if s2 == 200 else sql
        st.info("Executed the DuckDB compilation of the same query (the shown dialect targets another engine).")
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        df = con.execute(sql).fetchdf()
        st.dataframe(df, use_container_width=True)
        st.caption(f"{len(df)} rows")
    except duckdb.Error as exc:
        st.error(f"DuckDB rejected the compiled SQL: {exc}")
    finally:
        con.close()
