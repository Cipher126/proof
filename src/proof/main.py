from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from proof.config import settings
from proof.db import SessionLocal
from proof.errors import ProofError
from proof.ledger.api import router as ledger_router
from proof.payments.api import router as payments_router
from proof.providers.api import router as providers_router
from proof.operations.api import router as operations_router
from proof.reconciliation.api import router as reconciliation_router
from proof.demo import router as demo_router, tenant_router as demo_tenant_router

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("proof")

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
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(ProofError)
async def proof_error_handler(request: Request, exc: ProofError) -> JSONResponse:
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


@app.get("/ready", tags=["operations"])
def ready() -> dict[str, str]:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except OperationalError:
        raise ProofError("database_unavailable", "database is unavailable", 503) from None
    return {"status": "ready"}


def run() -> None:
    uvicorn.run("proof.main:app", host="127.0.0.1", port=8000, reload=False)


dashboard = Path(os.getenv(
    "PROOF_DASHBOARD_DIR",
    str(Path(__file__).resolve().parents[2] / "dashboard" / "dist"),
))
if dashboard.exists():
    app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")
