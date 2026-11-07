from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.errors import ProofError
from proof.ledger import service
from proof.ledger.schemas import (
    AccountCreate,
    AccountRead,
    BalanceRead,
    JournalCreate,
    JournalRead,
    TenantCreate,
    TenantRead,
)

router = APIRouter(prefix="/v1", tags=["ledger"])
DbSession = Annotated[Session, Depends(get_session)]


def active_tenant(
    tenant_id: uuid.UUID,
    x_tenant_id: Annotated[uuid.UUID, Header(alias="X-Tenant-ID")],
) -> uuid.UUID:
    if tenant_id != x_tenant_id:
        raise ProofError("tenant_header_mismatch", "X-Tenant-ID must match the route tenant", 403)
    return tenant_id


@router.post("/demo/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, session: DbSession) -> TenantRead:
    return TenantRead.model_validate(service.create_tenant(session, payload.name))


@router.post(
    "/tenants/{tenant_id}/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    tenant_id: uuid.UUID,
    payload: AccountCreate,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> AccountRead:
    return AccountRead.model_validate(
        service.create_account(session, tenant_id, payload.name, payload.currency)
    )


@router.get("/tenants/{tenant_id}/accounts/{account_id}/balance", response_model=BalanceRead)
def get_balance(
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> BalanceRead:
    account, balance = service.account_balance(session, tenant_id, account_id)
    return BalanceRead(account_id=account.id, currency=account.currency, balance_minor=balance)


@router.post(
    "/tenants/{tenant_id}/journals",
    response_model=JournalRead,
    status_code=status.HTTP_201_CREATED,
)
def post_journal(
    tenant_id: uuid.UUID,
    payload: JournalCreate,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> JournalRead:
    return JournalRead.model_validate(service.post_journal(session, tenant_id, payload))


@router.get("/tenants/{tenant_id}/journals/{journal_id}", response_model=JournalRead)
def get_journal(
    tenant_id: uuid.UUID,
    journal_id: uuid.UUID,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> JournalRead:
    return JournalRead.model_validate(service.get_journal(session, tenant_id, journal_id))


class ReversalCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


@router.post(
    "/tenants/{tenant_id}/journals/{journal_id}/reversals",
    response_model=JournalRead,
    status_code=status.HTTP_201_CREATED,
)
def reverse_journal(
    tenant_id: uuid.UUID,
    journal_id: uuid.UUID,
    payload: ReversalCreate,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> JournalRead:
    return JournalRead.model_validate(
        service.reverse_journal(session, tenant_id, journal_id, payload.reference, payload.reason)
    )
