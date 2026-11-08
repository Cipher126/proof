from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.identity import TenantAccess, active_tenant, require_permission
from proof.ledger import service as ledger_service
from proof.messaging.models import OutboxEvent
from proof.payments import service as payment_service
from proof.payments.models import PaymentChange
from proof.providers.models import ProviderEvent

router = APIRouter(prefix="/v1", tags=["operations"])
DbSession = Annotated[Session, Depends(get_session)]


class TimelineItem(BaseModel):
    occurred_at: str
    kind: str
    summary: str
    data: dict[str, Any]


class TransferTimeline(BaseModel):
    transfer_id: uuid.UUID
    items: list[TimelineItem]


@router.get(
    "/tenants/{tenant_id}/operations/transfers/{transfer_id}/timeline",
    response_model=TransferTimeline,
    dependencies=[Depends(require_permission("read"))],
)
def transfer_timeline(
    tenant_id: uuid.UUID,
    transfer_id: uuid.UUID,
    session: DbSession,
    _: Annotated[TenantAccess, Depends(active_tenant)],
) -> TransferTimeline:
    transfer = payment_service.get_transfer(session, tenant_id, transfer_id)
    outbox = session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.aggregate_type == "transfer",
            OutboxEvent.aggregate_id == transfer.id,
        )
    ).all()
    provider_events = session.scalars(
        select(ProviderEvent).where(
            ProviderEvent.tenant_id == tenant_id,
            ProviderEvent.transfer_id == transfer.id,
        )
    ).all()
    items = [
        TimelineItem(
            occurred_at=transfer.created_at.isoformat(),
            kind="transfer",
            summary="Transfer committed",
            data={"status": transfer.status, "client_reference": transfer.client_reference},
        ),
    ]
    if transfer.journal_id is not None:
        journal = ledger_service.get_journal(session, tenant_id, transfer.journal_id)
        items.append(TimelineItem(
            occurred_at=journal.posted_at.isoformat() if journal.posted_at else journal.created_at.isoformat(),
            kind="journal",
            summary="Balanced journal posted",
            data={
                "journal_id": str(journal.id),
                "entries": [
                    {
                        "account_id": str(entry.account_id),
                        "amount_minor": entry.amount_minor,
                        "currency": entry.currency,
                    }
                    for entry in journal.entries
                ],
            },
        ))
    changes = session.scalars(select(PaymentChange).where(
        PaymentChange.tenant_id == tenant_id, PaymentChange.transfer_id == transfer_id,
    ))
    items.extend(TimelineItem(
        occurred_at=change.created_at.isoformat(),
        kind="payment_transition",
        summary=f"{change.action}: {change.from_status} → {change.to_status}",
        data={"action": change.action, "journal_id": str(change.journal_id) if change.journal_id else None},
    ) for change in changes)
    items.extend(
        TimelineItem(
            occurred_at=event.occurred_at.isoformat(),
            kind="outbox",
            summary="Domain event published" if event.published_at else "Domain event pending",
            data={"event_type": event.event_type, "attempts": event.attempts},
        )
        for event in outbox
    )
    items.extend(
        TimelineItem(
            occurred_at=event.received_at.isoformat(),
            kind="provider_evidence",
            summary=f"Provider evidence {event.classification}",
            data={
                "event_id": event.event_id,
                "provider_status": event.provider_status,
                "classification": event.classification,
            },
        )
        for event in provider_events
    )
    items.sort(key=lambda item: item.occurred_at)
    return TransferTimeline(transfer_id=transfer.id, items=items)
