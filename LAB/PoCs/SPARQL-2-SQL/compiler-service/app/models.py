"""Request and response schemas of the compiler API."""

from typing import Literal

from pydantic import BaseModel, Field

Dialect = Literal["postgres", "duckdb", "snowflake", "bigquery"]


class CompileRequest(BaseModel):
    sparql: str = Field(..., description="A SPARQL 1.1 SELECT query over the FIBO VKG vocabulary")
    target_dialect: Dialect = "postgres"


class CompileResponse(BaseModel):
    sql: str = Field(..., description="The compiled SQL in the target dialect")
    target_dialect: Dialect
    projection: list[str] = Field(..., description="Output columns, named after the SPARQL variables")
    native_sql: str = Field(..., description="Ontop's PostgreSQL unfolding, before finishing")
    tables: list[str]
    join_count: int = Field(..., description="Base-table references minus one")
    timings_ms: dict[str, float]


class ErrorResponse(BaseModel):
    stage: str
    detail: str
