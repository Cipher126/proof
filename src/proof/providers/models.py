from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from proof.db import Base
from proof.ledger.models import utcnow


class ProviderEvent(Base):
    __tablename__ = "provider_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["transfers.tenant_id", "transfers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "provider", "event_id", name="uq_provider_event_identity"),
        Index("ix_provider_event_transfer", "tenant_id", "transfer_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(80))
    event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(120))
    provider_transfer_id: Mapped[str] = mapped_column(String(160))
    client_reference: Mapped[str] = mapped_column(String(160))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    provider_status: Mapped[str] = mapped_column(String(40))
    payload_hash: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict] = mapped_column(JSON)
    classification: Mapped[str] = mapped_column(String(40))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column()
    provider_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
