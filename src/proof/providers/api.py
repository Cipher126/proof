from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.errors import ProofError
from proof.identity import TenantAccess, active_tenant, require_development, require_permission
from proof.providers import service
from proof.providers.schemas import (
    DemoProviderEventCreate,
    ProviderEventRead,
    ProviderEventResponse,
)

router = APIRouter(prefix="/v1", tags=["provider evidence"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post(
    "/tenants/{tenant_id}/providers/simulated/webhooks",
    response_model=ProviderEventResponse,
    dependencies=[Depends(require_permission("provider"))],
)
async def receive_simulated_webhook(
    tenant_id: uuid.UUID,
    request: Request,
    session: DbSession,
    event_id: Annotated[str, Header(alias="X-Proof-Event-ID")],
    timestamp: Annotated[str, Header(alias="X-Proof-Timestamp")],
    signature: Annotated[str, Header(alias="X-Proof-Signature")],
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> ProviderEventResponse:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 64 * 1024:
            raise ProofError("provider_payload_too_large", "provider payload exceeds 64 KiB", 413)
        body.extend(chunk)
    event, duplicate = await run_in_threadpool(
        service.ingest_webhook,
        session,
        tenant_id,
        event_id=event_id,
        timestamp=timestamp,
        signature=signature,
        body=bytes(body),
    )
    return ProviderEventResponse(
        event=ProviderEventRead.model_validate(event), duplicate=duplicate
    )


@router.post(
    "/tenants/{tenant_id}/demo/provider-events",
    response_model=ProviderEventResponse,
    dependencies=[Depends(require_development)],
)
def simulate_provider_event(
    tenant_id: uuid.UUID,
    payload: DemoProviderEventCreate,
    session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> ProviderEventResponse:
    event, duplicate = service.build_demo_event(
        session, tenant_id, payload.client_reference, payload.scenario
    )
    return ProviderEventResponse(
        event=ProviderEventRead.model_validate(event), duplicate=duplicate
    )
