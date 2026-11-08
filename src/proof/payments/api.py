from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.identity import TenantAccess, active_tenant, require_permission
from proof.payments import service
from proof.payments.schemas import PaymentAction, PaymentChangeRead, TransferCreate, TransferRead

router = APIRouter(prefix="/v1", tags=["payments"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post(
    "/tenants/{tenant_id}/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("payment"))],
)
def create_transfer(
    tenant_id: uuid.UUID,
    payload: TransferCreate,
    session: DbSession,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> TransferRead:
    transfer, replayed = service.create_transfer(session, tenant_id, idempotency_key, payload)
    response.headers["Idempotent-Replayed"] = "true" if replayed else "false"
    return TransferRead.model_validate(transfer)


@router.get("/tenants/{tenant_id}/transfers/{transfer_id}", response_model=TransferRead,
            dependencies=[Depends(require_permission("read"))])
def get_transfer(
    tenant_id: uuid.UUID,
    transfer_id: uuid.UUID,
    session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> TransferRead:
    return TransferRead.model_validate(service.get_transfer(session, tenant_id, transfer_id))


@router.post(
    "/tenants/{tenant_id}/payment-intents", response_model=TransferRead,
    status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("payment"))],
)
def create_payment_intent(
    tenant_id: uuid.UUID, payload: TransferCreate, session: DbSession, response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> TransferRead:
    transfer, replayed = service.create_transfer(session, tenant_id, idempotency_key, payload, deferred=True)
    response.headers["Idempotent-Replayed"] = str(replayed).lower()
    return TransferRead.model_validate(transfer)


@router.post(
    "/tenants/{tenant_id}/transfers/{transfer_id}/transitions", response_model=PaymentChangeRead,
    status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("payment"))],
)
def change_payment(
    transfer_id: uuid.UUID, payload: PaymentAction, session: DbSession, request: Request, response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    access: Annotated[TenantAccess, Depends(active_tenant)],
) -> PaymentChangeRead:
    change, replayed = service.change_payment(
        session, access.tenant_id, transfer_id, idempotency_key, payload,
        actor=access.audit_actor or "development", request_id=request.state.request_id,
    )
    response.headers["Idempotent-Replayed"] = str(replayed).lower()
    return PaymentChangeRead.model_validate(change)
