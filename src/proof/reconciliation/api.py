from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.errors import ProofError
from proof.identity import TenantAccess, active_tenant, require_permission
from proof.reconciliation import service
from proof.reconciliation.schemas import (
    FindingRead,
    FindingResolutionCreate,
    ReconciliationRunRead,
    SettlementBatchRead,
    SettlementClose,
    StatementImportCreate,
    StatementImportRead,
    StatementImportResponse,
)

router = APIRouter(prefix="/v1", tags=["reconciliation"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post(
    "/tenants/{tenant_id}/settlements/statements",
    response_model=StatementImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("settlement"))],
)
def import_statement(
    tenant_id: uuid.UUID,
    payload: StatementImportCreate,
    session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> StatementImportResponse:
    statement, duplicate = service.import_statement(session, tenant_id, payload)
    return StatementImportResponse(
        statement=StatementImportRead.model_validate(statement), duplicate=duplicate
    )


@router.post(
    "/tenants/{tenant_id}/settlements/statements/{statement_id}/reconcile",
    response_model=ReconciliationRunRead,
    dependencies=[Depends(require_permission("settlement"))],
)
def reconcile_statement(
    tenant_id: uuid.UUID,
    statement_id: uuid.UUID,
    session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> ReconciliationRunRead:
    run, findings = service.reconcile_statement(session, tenant_id, statement_id)
    result = ReconciliationRunRead.model_validate(run)
    return result.model_copy(
        update={"findings": [FindingRead.model_validate(finding) for finding in findings]}
    )


@router.post(
    "/tenants/{tenant_id}/reconciliation/findings/{finding_id}/resolve",
    response_model=FindingRead,
    dependencies=[Depends(require_permission("settlement"))],
)
def resolve_finding(
    tenant_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingResolutionCreate,
    session: DbSession,
    access: Annotated[TenantAccess, Depends(active_tenant)],
    operator_id: Annotated[str | None, Header(alias="X-Operator-ID")] = None,
) -> FindingRead:
    actor = access.audit_actor or operator_id
    if actor is None or not 1 <= len(actor.strip()) <= 160:
        raise ProofError("invalid_operator", "a valid operator identity is required")
    return FindingRead.model_validate(
        service.resolve_finding(session, tenant_id, finding_id, actor, payload)
    )


@router.get("/tenants/{tenant_id}/settlements/batches/{statement_id}", response_model=SettlementBatchRead,
            dependencies=[Depends(require_permission("read"))])
def get_settlement(
    tenant_id: uuid.UUID, statement_id: uuid.UUID, session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> SettlementBatchRead:
    return service.settlement_batch(session, tenant_id, statement_id)


@router.post(
    "/tenants/{tenant_id}/settlements/batches/{statement_id}/close",
    response_model=SettlementBatchRead, dependencies=[Depends(require_permission("settlement"))],
)
def close_settlement(
    tenant_id: uuid.UUID, statement_id: uuid.UUID, payload: SettlementClose, session: DbSession,
    access: Annotated[TenantAccess, Depends(active_tenant)],
) -> SettlementBatchRead:
    return service.settlement_batch(
        session, tenant_id, statement_id, close_reason=payload.reason, actor=access.audit_actor,
    )
