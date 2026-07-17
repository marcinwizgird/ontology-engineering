"""Connection settings for the two backends, read once from infra/*/.env.

Every other module takes a settings object (or a client built from one) instead of
re-reading the environment, so there is a single, testable place where a host, port,
or password is resolved. Both settings classes mirror the defaults their
docker-compose.yml applies when no .env is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# .../Ontology Engineering/src/Ontology Modeler/ontology_modeler/config.py
#   parents[0]=ontology_modeler [1]=Ontology Modeler [2]=src [3]=repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

INFRA = REPO_ROOT / "infra"


def read_env(compose_dir: Path) -> dict[str, str]:
    """Parse a docker-compose .env file into a dict (missing file -> empty)."""
    env: dict[str, str] = {}
    env_file = compose_dir / ".env"
    if not env_file.exists():
        return env
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("\"'")
    return env


@dataclass(frozen=True)
class FusekiSettings:
    """How to reach the Fuseki dataset."""

    base_url: str = "http://localhost:3030"
    dataset: str = "ontology"
    user: str = "admin"
    password: str = "admin"

    @classmethod
    def from_env(cls, **overrides) -> "FusekiSettings":
        env = read_env(INFRA / "fuseki")
        base = f"http://localhost:{env.get('FUSEKI_PORT', '3030')}"
        values = dict(
            base_url=base,
            dataset="ontology",
            user="admin",
            password=env.get("FUSEKI_ADMIN_PASSWORD", "admin"),
        )
        values.update({k: v for k, v in overrides.items() if v is not None})
        # A caller-supplied base_url wins over the env-derived one.
        values["base_url"] = values["base_url"].rstrip("/")
        return cls(**values)

    @property
    def sparql_endpoint(self) -> str:
        return f"{self.base_url}/{self.dataset}/sparql"

    @property
    def update_endpoint(self) -> str:
        return f"{self.base_url}/{self.dataset}/update"

    @property
    def gsp_endpoint(self) -> str:
        return f"{self.base_url}/{self.dataset}/data"

    @property
    def ping_endpoint(self) -> str:
        return f"{self.base_url}/$/ping"


@dataclass(frozen=True)
class FalkorSettings:
    """How to reach the FalkorDB graph."""

    host: str = "localhost"
    port: int = 6379
    graph_name: str = "ontology"
    password: str | None = None

    @classmethod
    def from_env(cls, **overrides) -> "FalkorSettings":
        env = read_env(INFRA / "falkordb")
        values = dict(
            host="localhost",
            port=int(env.get("FALKORDB_PORT", "6379")),
            graph_name=env.get("FALKORDB_GRAPH", "ontology"),
            password=env.get("FALKORDB_PASSWORD") or None,
        )
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)
