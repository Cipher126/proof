from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proof.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("currency = upper(currency) AND length(currency) = 3", name="ck_account_currency"),
        UniqueConstraint("tenant_id", "id", name="uq_account_tenant_id"),
        UniqueConstraint("tenant_id", "name", "currency", name="uq_account_name_currency"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ += (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )


class JournalTransaction(Base):
    __tablename__ = "journal_transactions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'posted')", name="ck_journal_status"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["reverses_id"], ["journal_transactions.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "id", name="uq_journal_tenant_id"),
        UniqueConstraint("tenant_id", "reference", name="uq_journal_reference"),
        UniqueConstraint("reverses_id", name="uq_journal_single_reversal"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reference: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entries: Mapped[list["JournalEntry"]] = relationship(
        back_populates="journal", order_by="JournalEntry.position", lazy="selectin"
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("amount_minor <> 0", name="ck_entry_nonzero"),
        CheckConstraint("position >= 0", name="ck_entry_position"),
        CheckConstraint("currency = upper(currency) AND length(currency) = 3", name="ck_entry_currency"),
        ForeignKeyConstraint(
            ["tenant_id", "journal_id"],
            ["journal_transactions.tenant_id", "journal_transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "account_id"], ["accounts.tenant_id", "accounts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("journal_id", "position", name="uq_entry_journal_position"),
        Index("ix_entries_account_created", "tenant_id", "account_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    journal_id: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    journal: Mapped[JournalTransaction] = relationship(back_populates="entries")
