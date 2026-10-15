"""FastAPI front of the stateless SPARQL -> SQL compiler (no database connection)."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import compiler
from .models import CompileRequest, CompileResponse, ErrorResponse

app = FastAPI(title="FIBO VKG SPARQL-to-SQL compiler", version="0.1.0")


@app.get("/health")
def health() -> dict:
    ok = compiler.sidecar_healthy()
    return {"status": "ok" if ok else "degraded", "ontop_sidecar": ok,
            "database_connection": None}


@app.post("/v1/compile", response_model=CompileResponse,
          responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                     503: {"model": ErrorResponse}})
def compile_endpoint(req: CompileRequest):
    try:
        c = compiler.compile_sparql(req.sparql, req.target_dialect)
    except compiler.CompileError as exc:
        return JSONResponse(status_code=exc.status, content={"stage": exc.stage, "detail": str(exc)})
    return CompileResponse(sql=c.sql, target_dialect=c.dialect, projection=c.projection,
                           native_sql=c.native_sql, tables=c.tables, join_count=c.join_count,
                           timings_ms=c.timings_ms)
