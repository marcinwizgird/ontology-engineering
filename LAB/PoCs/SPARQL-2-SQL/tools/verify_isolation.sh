#!/usr/bin/env bash
# DoD 1-4 inside the isolated compilation plane:
#  1. no database runs anywhere in the project, and the demo sandbox is stopped;
#  2. compile-net is internal: no container on it can reach the internet;
#  3. the verifier (on compile-net only) runs the full suite against the deployed compiler:
#     compilation, DuckDB execution (its own fixture), oracle comparison, P95 latency.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
docker compose -f docker-compose.yml -f docker-compose.demo.yml stop demo-sandbox >/dev/null 2>&1 || true
docker compose up -d --build ontop-sidecar sparql2sql-service
NET="$(docker compose ps -q sparql2sql-service | xargs docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
echo "compiler networks: $NET"
echo "running database / sandbox containers (expect none):"
docker ps --format '{{.Image}}' | grep -Ei 'postgres|duckdb|demo-sandbox|mysql|oracle' || echo "  none"
echo -n "egress from compile-net (expect blocked): "
if docker run --rm --network fibo-sparql2sql_compile-net curlimages/curl:8.10.1 -s -m 5 https://example.org >/dev/null 2>&1; then
  echo "REACHABLE -- isolation FAILED"; exit 1; else echo "blocked"; fi
for i in $(seq 1 60); do   # the sidecar needs a few seconds to load the ontology
  docker run --rm --network fibo-sparql2sql_compile-net curlimages/curl:8.10.1 -s -m 2 \
    http://sparql2sql-service:8000/health | grep -q '"ontop_sidecar":true' && break; sleep 1
done
docker compose --profile verify run --rm --build verifier
