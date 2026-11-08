from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from proof.db import Base
from proof.ledger.models import utcnow

TRANSFER_STATES = "'created', 'authorized', 'submitted', 'succeeded', 'failed', 'cancelled', 'expired', 'reversed'"
POSTING_SHAPE = """((status IN ('succeeded', 'reversed')) = (journal_id IS NOT NULL))
AND ((status IN ('succeeded', 'failed', 'cancelled', 'expired', 'reversed')) = (completed_at IS NOT NULL))"""


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed')", name="ck_idempotency_status"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "operation", "key", name="uq_idempotency_command"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    operation: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
    response_status: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_transfer_positive_amount"),
        CheckConstraint(f"status IN ({TRANSFER_STATES})", name="ck_transfer_status"),
        CheckConstraint(POSTING_SHAPE, name="ck_transfer_posting_shape"),
        CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= amount_minor "
            "AND ((status = 'reversed') = (refunded_minor = amount_minor))",
            name="ck_transfer_refund_total",
        ),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["tenant_id", "source_account_id"],
            ["accounts.tenant_id", "accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "destination_account_id"],
            ["accounts.tenant_id", "accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "journal_id"],
            ["journal_transactions.tenant_id", "journal_transactions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_transfer_tenant_id"),
        UniqueConstraint("tenant_id", "client_reference", name="uq_transfer_client_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    client_reference: Mapped[str] = mapped_column(String(160))
    source_account_id: Mapped[uuid.UUID] = mapped_column()
    destination_account_id: Mapped[uuid.UUID] = mapped_column()
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), default="succeeded")
    journal_id: Mapped[uuid.UUID | None] = mapped_column()
    description: Mapped[str] = mapped_column(String(500), default="Transfer")
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentChange(Base):
    __tablename__ = "payment_changes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "transfer_id"], ["transfers.tenant_id", "transfers.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "journal_id"], ["journal_transactions.tenant_id", "journal_transactions.id"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    transfer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(24))
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    fee_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    journal_id: Mapped[uuid.UUID | None] = mapped_column()
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
