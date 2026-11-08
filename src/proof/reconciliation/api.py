from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.ledger.api import active_tenant
from proof.reconciliation import service
from proof.reconciliation.schemas import (
    FindingRead,
    FindingResolutionCreate,
    ReconciliationRunRead,
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
)
def import_statement(
    tenant_id: uuid.UUID,
    payload: StatementImportCreate,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> StatementImportResponse:
    statement, duplicate = service.import_statement(session, tenant_id, payload)
    return StatementImportResponse(
        statement=StatementImportRead.model_validate(statement), duplicate=duplicate
    )


@router.post(
    "/tenants/{tenant_id}/settlements/statements/{statement_id}/reconcile",
    response_model=ReconciliationRunRead,
)
def reconcile_statement(
    tenant_id: uuid.UUID,
    statement_id: uuid.UUID,
    session: DbSession,
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> ReconciliationRunRead:
    run, findings = service.reconcile_statement(session, tenant_id, statement_id)
    result = ReconciliationRunRead.model_validate(run)
    return result.model_copy(
        update={"findings": [FindingRead.model_validate(finding) for finding in findings]}
    )


@router.post(
    "/tenants/{tenant_id}/reconciliation/findings/{finding_id}/resolve",
    response_model=FindingRead,
)
def resolve_finding(
    tenant_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingResolutionCreate,
    session: DbSession,
    operator_id: Annotated[str, Header(alias="X-Operator-ID")],
    _: Annotated[uuid.UUID, Depends(active_tenant)],
) -> FindingRead:
    return FindingRead.model_validate(
        service.resolve_finding(session, tenant_id, finding_id, operator_id, payload)
    )
