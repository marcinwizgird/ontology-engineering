"""HTTP edge — FastAPI over the operation registry.

Every platform operation is exposed as ``POST /projects/{project}/ops/{operation}``
with its keyword arguments as the JSON body, plus discovery (``GET /operations``)
so a generated client — or an MCP/tool-use adapter — never hand-mirrors the
server (the lesson of VocBench's 60 hand-written Angular service classes).

Authentication here is a development stub: the principal is taken from the
``X-SIP-Principal`` header and must exist in the registry. Production replaces
:func:`principal` with OIDC token validation; nothing else changes, because
authorisation happens in ``Platform.call``, not here.

Run::

    PYTHONPATH="src/Semantic Intelligence Platform" uvicorn semantic_intelligence.api.app:app
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException

from ..agents.orchestrator import Conductor
from ..governance.registry import AuthorizationError
from ..platform import OPERATIONS, Platform, describe_operations


def create_app(platform: Platform | None = None, conductor: Conductor | None = None) -> FastAPI:
    P = platform or Platform()
    C = conductor or Conductor(P)
    app = FastAPI(title="Semantic Intelligence Platform", version="0.1.0",
                  description="Agent-assisted ontology and knowledge-graph construction.")
    app.state.platform, app.state.conductor = P, C

    def principal(x_sip_principal: str = Header(...)):
        try:
            return P.registry.principal(x_sip_principal)
        except KeyError:
            raise HTTPException(401, f"unknown principal {x_sip_principal!r}") from None

    def _run(fn):
        try:
            return fn()
        except AuthorizationError as e:
            raise HTTPException(403, str(e)) from None
        except KeyError as e:
            raise HTTPException(404, str(e)) from None
        except (ValueError, PermissionError) as e:
            raise HTTPException(422, str(e)) from None

    def _jsonable(result: Any):
        if hasattr(result, "summary") and hasattr(result, "revision"):
            return {"commit": result.id, "revision": result.revision, "status": result.status,
                    "added": len(result.additions), "removed": len(result.removals)}
        return result

    @app.get("/health")
    def health():
        return {"status": "ok", "projects": sorted(P.projects), "operations": len(OPERATIONS)}

    @app.get("/operations")
    def operations():
        return describe_operations()

    @app.post("/projects")
    def create_project(body: dict = Body(...), who=Depends(principal)):
        return _run(lambda: P.call(who, None, "governance.createProject", **body))

    @app.post("/projects/{project}/ops/{op}")
    def call(project: str, op: str, body: dict = Body(default={}), who=Depends(principal)):
        if op not in OPERATIONS:
            raise HTTPException(404, f"unknown operation {op!r}")
        return _run(lambda: _jsonable(P.call(who, project, op, **body)))

    @app.post("/projects/{project}/agents/enable")
    def enable(project: str, who=Depends(principal)):
        return _run(lambda: {"agents": C.enable_agents(project, who)})

    @app.post("/projects/{project}/agents/{agent}/run")
    def run_agent(project: str, agent: str, body: dict = Body(default={}),
                  who=Depends(principal)):
        def go():
            a = C.agent(project, agent)
            if a.principal.on_behalf_of != who.id and not who.is_admin:
                raise AuthorizationError("agents run only for the human that enabled them")
            r = a.run(project, **body)
            return {"summary": r.summary(), "output": r.output}
        return _run(go)

    @app.post("/agents/runs/{run_id}/stop")
    def stop(run_id: str, who=Depends(principal)):
        C.runtime.stop(run_id)
        return {"stopped": run_id}

    @app.get("/projects/{project}/agents/metrics")
    def agent_metrics(project: str, who=Depends(principal)):
        return _run(lambda: (P.pdp.require(who, project, "rdf", "R"),
                             C.runtime.metrics(project))[1])

    return app


app = create_app()
