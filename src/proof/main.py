from __future__ import annotations

import logging
import os
import json
import re
import uuid
from time import perf_counter
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from opentelemetry import propagate, trace
from prometheus_client import CONTENT_TYPE_LATEST

from proof.config import settings
from proof.db import SessionLocal
from proof.errors import ProofError
from proof.ledger.api import router as ledger_router
from proof.payments.api import router as payments_router
from proof.providers.api import router as providers_router
from proof.operations.api import router as operations_router
from proof.operations import telemetry
from proof.reconciliation.api import router as reconciliation_router
from proof.demo import router as demo_router, tenant_router as demo_tenant_router

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("proof")
telemetry.configure_tracing("proof-api")
tracer = trace.get_tracer(__name__)
READY_SCHEMA_REVISIONS = frozenset({"0011", "0012"})

app = FastAPI(
    title="Proof API",
    version="0.1.0",
    description="Fictional payment ledger and reconciliation platform. No real money is processed.",
)
app.include_router(ledger_router)
app.include_router(payments_router)
app.include_router(providers_router)
app.include_router(operations_router)
app.include_router(reconciliation_router)
app.include_router(demo_router)
app.include_router(demo_tenant_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", supplied) else str(uuid.uuid4())
    request.state.request_id = request_id
    started = perf_counter()
    status = 500
    with tracer.start_as_current_span(
        "proof.request", context=propagate.extract(request.headers), kind=trace.SpanKind.SERVER,
    ) as span:
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            span.set_attribute("http.route", route)
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("http.response.status_code", status)
            telemetry.REQUESTS.labels(route, request.method, str(status)).inc()
            telemetry.LATENCY.labels(route).observe(perf_counter() - started)
            if status >= 500:
                span.set_status(trace.StatusCode.ERROR)
            logger.info(json.dumps({"event": "http.completed", "request_id": request_id,
                                    "route": route, "method": request.method, "status": status}))
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(ProofError)
async def proof_error_handler(request: Request, exc: ProofError) -> JSONResponse:
    telemetry.ERRORS.labels(exc.code).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": request.state.request_id}},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.info("database constraint rejected request request_id=%s", request.state.request_id)
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "constraint_conflict",
                "message": "the request conflicts with an existing or protected record",
                "request_id": request.state.request_id,
            }
        },
    )


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready", tags=["operations"], responses={503: {"description": "Database or schema unavailable"}})
def ready() -> dict[str, str]:
    credentials = "operator_credentials" if settings.environment == "operations" else "demo_credentials"
    try:
        with SessionLocal() as session:
            revisions = session.execute(text(f"""
                SELECT version_num,
                       EXISTS (SELECT 1 FROM tenants),
                       EXISTS (SELECT 1 FROM journal_transactions),
                       EXISTS (SELECT 1 FROM transfers),
                       EXISTS (SELECT 1 FROM {credentials})
                FROM alembic_version
            """)).scalars().all()
    except OperationalError:
        raise ProofError("database_unavailable", "database is unavailable", 503) from None
    except ProgrammingError:
        raise ProofError("database_schema_unavailable", "required database schema is unavailable", 503) from None
    if len(revisions) != 1 or revisions[0] not in READY_SCHEMA_REVISIONS:
        raise ProofError("database_schema_unavailable", "required database schema is unavailable", 503)
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if os.getenv("PROOF_METRICS_ENABLED") != "1":
        raise ProofError("not_found", "endpoint was not found", 404)
    with SessionLocal() as session:
        return Response(telemetry.scrape(session), headers={"Content-Type": CONTENT_TYPE_LATEST})


def run() -> None:
    uvicorn.run("proof.main:app", host="127.0.0.1", port=8000, reload=False)


dashboard = Path(os.getenv(
    "PROOF_DASHBOARD_DIR",
    str(Path(__file__).resolve().parents[2] / "dashboard" / "dist"),
))
if dashboard.exists():
    app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")
