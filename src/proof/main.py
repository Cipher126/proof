from __future__ import annotations

import logging
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from proof.config import settings
from proof.db import SessionLocal
from proof.errors import ProofError
from proof.ledger.api import router as ledger_router

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("proof")

app = FastAPI(
    title="Proof API",
    version="0.1.0",
    description="Fictional payment ledger and reconciliation platform. No real money is processed.",
)
app.include_router(ledger_router)


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
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ready"}


def run() -> None:
    uvicorn.run("proof.main:app", host="127.0.0.1", port=8000, reload=False)
