"""FastAPI proxy exposing the PlaygroundService to the browser.

Endpoints (all JSON):
    GET  /health                      -> {status, fuseki}
    GET  /ontologies                  -> [{graphUri, ontologyIri, nodeCount}, ...]
    GET  /ontology?graph=<uri>        -> {graphUri, ontologyIri, baseNs, ontology}
    PUT  /ontology?graph=<uri>        -> save; body is the edited `ontology` object
         &dryRun=true                    (build+guard the diff, report it, write nothing)

Fuseki credentials live here, server-side; the browser only ever talks to this proxy, which
also settles CORS. Run it with:

    PLAYGROUND_ORIGINS=http://localhost:5173 \
    python -m ontology_modeler.playground.api            # uvicorn on :8080

Override Fuseki with the usual --fuseki-base/--dataset env or FusekiSettings.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from ..fuseki import FusekiClient
from .service import PlaygroundService, PreservationError


def create_app(service: PlaygroundService | None = None) -> FastAPI:
    service = service or PlaygroundService()
    app = FastAPI(title="Ontology Modeler -- Playground bridge", version="1.0")

    origins = os.environ.get("PLAYGROUND_ORIGINS", "http://localhost:5173,http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_methods=["GET", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "fuseki": service.client.is_up()}

    @app.get("/ontologies")
    def ontologies() -> list[dict[str, Any]]:
        try:
            return service.list_ontologies()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Fuseki query failed: {exc}") from exc

    @app.get("/ontology")
    def load(graph: str = Query(..., description="named-graph URI")) -> dict[str, Any]:
        try:
            return service.load(graph)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"load failed: {exc}") from exc

    @app.put("/ontology")
    async def save(request: Request,
                   graph: str = Query(..., description="named-graph URI"),
                   dryRun: bool = Query(False)) -> dict[str, Any]:
        body = await request.json()
        # accept either the bare ontology object or the load envelope {..., "ontology": {...}}
        edited = body.get("ontology", body) if isinstance(body, dict) else body
        try:
            return service.save(graph, edited, dry_run=dryRun).to_dict()
        except PreservationError as exc:
            raise HTTPException(status_code=409, detail={
                "error": "preservation-guard",
                "message": str(exc),
                "violations": [f"{s} {p} {o}" for s, p, o in exc.violations[:20]],
            }) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"save failed: {exc}") from exc

    return app


def main() -> None:
    import uvicorn
    client = FusekiClient()
    if not client.is_up():
        print(f"warning: Fuseki not answering at {client.settings.base_url} "
              f"(start it: cd infra/fuseki && docker compose up -d)")
    uvicorn.run(create_app(PlaygroundService(client)),
                host=os.environ.get("PLAYGROUND_HOST", "127.0.0.1"),
                port=int(os.environ.get("PLAYGROUND_PORT", "8080")))


if __name__ == "__main__":
    main()
