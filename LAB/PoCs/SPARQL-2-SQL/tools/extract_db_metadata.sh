#!/usr/bin/env bash
# Regenerate vkg-artifacts/db-metadata.json: start a throwaway PostgreSQL with the 10-table
# DDL, let Ontop extract the PK/FK/column metadata, then remove everything. Build time only.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
NET=fiben-meta-net
docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f fiben-pg >/dev/null 2>&1 || true
docker run -d --name fiben-pg --network "$NET" -e POSTGRES_USER=fiben -e POSTGRES_PASSWORD=fiben \
  -e POSTGRES_DB=fiben -v "$PWD/demo-sandbox/ddl:/docker-entrypoint-initdb.d:ro" postgres:16-alpine >/dev/null
for i in $(seq 1 60); do
  docker exec fiben-pg pg_isready -U fiben -d fiben >/dev/null 2>&1 && \
  docker exec fiben-pg psql -U fiben -d fiben -tAc 'select count(*) from "PUBLIC"."FIN_REPORT"' >/dev/null 2>&1 && break
  sleep 1
done
docker run --rm --network "$NET" -v "$PWD/vkg-artifacts:/opt/ontop/input" \
  -v "$PWD/vkg-artifacts/jdbc:/opt/ontop/jdbc" ontop/ontop:latest \
  ontop extract-db-metadata -p /opt/ontop/input/extract.properties -o /opt/ontop/input/db-metadata.json
docker rm -f fiben-pg >/dev/null
docker network rm "$NET" >/dev/null
echo "wrote vkg-artifacts/db-metadata.json"
