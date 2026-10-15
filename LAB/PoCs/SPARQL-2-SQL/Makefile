# FIBO VKG SPARQL-to-SQL PoC. Needs Docker (Ontop runs in containers; no local Java).
.PHONY: metadata sidecar-dev seed test up verify demo down

metadata:      ## regenerate vkg-artifacts/db-metadata.json (throwaway PostgreSQL, build time only)
	bash tools/extract_db_metadata.sh

sidecar-dev:   ## offline sidecar on a published port, for local development and tests
	docker build -q -t fibo-ontop-sidecar ontop-sidecar
	-docker rm -f ontop-sidecar-dev
	MSYS_NO_PATHCONV=1 docker run -d --name ontop-sidecar-dev -p 18080:8080 -v "$(CURDIR)/vkg-artifacts:/opt/ontop/input:ro" fibo-ontop-sidecar

seed:          ## build demo-sandbox/fiben_demo.duckdb
	python demo-sandbox/seed_duckdb.py

test:          ## pytest, in-process compiler against sidecar-dev
	cd compiler-service && python -m pytest tests -q -s

up:            ## compilation plane only (internal network)
	docker compose up -d --build

verify:        ## DoD 1-4 from inside the isolated network
	bash tools/verify_isolation.sh

demo:          ## + Streamlit sandbox on http://localhost:8501
	docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build

down:
	docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile verify down
