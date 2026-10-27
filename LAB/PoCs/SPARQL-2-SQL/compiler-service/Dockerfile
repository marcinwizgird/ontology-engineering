# Build context: the PoC root (docker compose sets it), so the test stage can reach the
# DuckDB seed script and the VKG artifacts the oracle reads.
FROM python:3.12-slim AS runtime
WORKDIR /srv
COPY compiler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY compiler-service/app ./app
ENV ONTOP_SIDECAR_URL=http://ontop-sidecar:8080
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# The CI verifier: the same code plus the test suite, the seed script and the artifacts.
FROM runtime AS test
COPY compiler-service/requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt
COPY compiler-service/tests /poc/compiler-service/tests
COPY compiler-service/app /poc/compiler-service/app
COPY demo-sandbox/seed_duckdb.py demo-sandbox/queries.py /poc/demo-sandbox/
COPY demo-sandbox/ddl /poc/demo-sandbox/ddl
COPY vkg-artifacts/*.ttl vkg-artifacts/mapping-spec.yaml vkg-artifacts/db-metadata.json /poc/vkg-artifacts/
COPY tools/build_mappings.py tools/check_mappings.py /poc/tools/
WORKDIR /poc/compiler-service
CMD ["pytest", "-q", "-s", "tests"]
