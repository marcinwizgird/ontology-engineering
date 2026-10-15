"""HTTP edge — FastAPI over the operation registry.

Every platform operation is exposed as ``POST /projects/{project}/ops/{operation}``
with its keyword arguments as the JSON body, plus discovery (``GET /operations``)
so a generated client — or an MCP/tool-use adapter — never hand-mirrors the
server (the lesson of VocBench's 60 hand-written Angular service classes).

Authentication here is a development stub: the principal is taken from the
``X-SIP-Principal`` header and must exist in the registry. Production replaces
:func:`principal` with OIDC token validation; nothing else changes, because
authorisation happens in ``Platform.call``, not here.

The workbench (``/ui``, ``workbench.html``) is a single static page over this same
API; it adds no server-side logic of its own.

Run::

    PYTHONPATH="sip" uvicorn semantic_intelligence.api.app:app
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from ..agents.orchestrator import Conductor
from ..core.principal import Principal
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

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/ui")

    @app.get("/ui", include_in_schema=False)
    def workbench():
        """The workbench: one static page that calls this API (no build step)."""
        return HTMLResponse((Path(__file__).parent / "workbench.html").read_text(
            encoding="utf-8"))

    @app.get("/health")
    def health():
        return {"status": "ok", "projects": sorted(P.projects), "operations": len(OPERATIONS)}

    @app.get("/operations")
    def operations():
        return describe_operations()

    # -- principals (VocBench UsersManager, development form) --------------- #
    @app.get("/principals")
    def principals(who=Depends(principal)):
        return [{"id": p.id, "display_name": p.display_name, "is_admin": p.is_admin,
                 "is_machine": p.is_machine, "on_behalf_of": p.on_behalf_of}
                for p in sorted(P.registry.principals.values(), key=lambda p: p.id)]

    @app.post("/principals")
    def add_principal(body: dict = Body(...), who=Depends(principal)):
        def go():
            if not who.is_admin or who.is_machine:
                raise AuthorizationError("registering users requires an administrator")
            pid = str(body.get("id", "")).strip()
            if not pid:
                raise ValueError("a principal needs an id")
            if pid in P.registry.principals:
                raise ValueError(f"principal {pid!r} exists")
            p = P.registry.add_principal(Principal(pid, body.get("display_name", "")))
            return {"id": p.id}
        return _run(go)

    @app.get("/templates")
    def templates(who=Depends(principal)):
        return _run(lambda: P.call(who, None, "governance.listTemplates"))

    @app.get("/projects/{project}/members")
    def members(project: str, who=Depends(principal)):
        def go():
            P.pdp.require(who, project, "rdf", "R")
            return [{"principal": b.principal, "roles": list(b.roles),
                     "languages": list(b.languages)}
                    for (pid, proj), b in sorted(P.registry.bindings.items()) if proj == project]
        return _run(go)

    @app.get("/projects/{project}/agents")
    def agents(project: str, who=Depends(principal)):
        def go():
            P.pdp.require(who, project, "rdf", "R")
            return [{"agent": a.name, "stage": a.stage, "principal": a.principal.id,
                     "on_behalf_of": a.principal.on_behalf_of}
                    for (proj, _), a in C.agents.items() if proj == project]
        return _run(go)

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
            return {"summary": r.summary(), "output": r.output,
                    "proposals": [{"operation": p.operation, "arguments": p.arguments,
                                   "critic": p.critic, "commit": p.commit, "error": p.error,
                                   "quote": p.evidence.get("quote")} for p in r.proposals]}
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
