from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.ledger.api import active_tenant
from proof.payments import service
from proof.payments.schemas import TransferCreate, TransferRead

router = APIRouter(prefix="/v1", tags=["payments"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post(
    "/tenants/{tenant_id}/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    tenant_id: uuid.UUID,
    payload: TransferCreate,
    session: DbSession,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> TransferRead:
    transfer, replayed = service.create_transfer(session, tenant_id, idempotency_key, payload)
    response.headers["Idempotent-Replayed"] = "true" if replayed else "false"
    return TransferRead.model_validate(transfer)


@router.get("/tenants/{tenant_id}/transfers/{transfer_id}", response_model=TransferRead)
def get_transfer(
    tenant_id: uuid.UUID,
    transfer_id: uuid.UUID,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> TransferRead:
    return TransferRead.model_validate(service.get_transfer(session, tenant_id, transfer_id))
