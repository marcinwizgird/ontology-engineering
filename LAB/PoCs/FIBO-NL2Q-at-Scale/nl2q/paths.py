"""Filesystem locations. Everything derived lives under ``artifacts/`` (versioned, small)
or ``data/`` and ``runs/`` (git-ignored, large or per-run)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]

RAW = ROOT / "data" / "raw" / "fiben"
FIBEN_DDL = RAW / "FIBEN.sql"
FIBEN_QUERIES = RAW / "FIBEN_Queries.json"
FIBEN_CSV = RAW / "data"
DB = Path(os.environ.get("NL2Q_DB", ROOT / "data" / "fiben_vkg.duckdb"))

FIBO_DIR = REPO / "Ontology Repository" / "FIBO" / "fibo"
CACHE = ROOT / ".cache"

ARTIFACTS = ROOT / "artifacts"
ONTOP_DIR = ARTIFACTS / "ontop"              # mounted into the FIBEN Ontop sidecar
ONTOLOGY_TTL = ONTOP_DIR / "fiben-ontology.ttl"
MAPPING_TTL = ONTOP_DIR / "fiben-mapping.r2rml.ttl"
DB_METADATA = ONTOP_DIR / "db-metadata.json"
GOLD_DIR = ARTIFACTS / "gold"
KNOWLEDGE_DIR = ARTIFACTS / "knowledge"

RUNS = ROOT / "runs"

# the verified SPARQL -> SQL compiler of the first PoC (imported, not copied)
COMPILER_APP = ROOT.parent / "SPARQL-2-SQL" / "compiler-service"
SIDECAR_URL = os.environ.get("NL2Q_SIDECAR_URL", "http://localhost:18081")

SCHEMA = "FIBEN"
