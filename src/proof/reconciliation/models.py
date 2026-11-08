from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from proof.db import Base
from proof.ledger.models import utcnow


class StatementImport(Base):
    __tablename__ = "statement_imports"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "provider", "content_hash", name="uq_statement_content"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(240))
    content_hash: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)
    raw_evidence: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StatementLine(Base):
    __tablename__ = "statement_lines"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["statement_import_id"], ["statement_imports.id"], ondelete="RESTRICT"),
        UniqueConstraint("statement_import_id", "line_number", name="uq_statement_line_number"),
        Index("ix_statement_line_reference", "tenant_id", "client_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    statement_import_id: Mapped[uuid.UUID] = mapped_column()
    line_number: Mapped[int] = mapped_column(Integer)
    provider_reference: Mapped[str] = mapped_column(String(160))
    client_reference: Mapped[str] = mapped_column(String(160))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    provider_status: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_data: Mapped[dict] = mapped_column(JSON)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed')", name="ck_reconciliation_run_status"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["statement_import_id"], ["statement_imports.id"], ondelete="RESTRICT"),
        UniqueConstraint("statement_import_id", name="uq_reconciliation_statement"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    statement_import_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReconciliationFinding(Base):
    __tablename__ = "reconciliation_findings"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="ck_reconciliation_finding_status"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["run_id"], ["reconciliation_runs.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["statement_line_id"], ["statement_lines.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["transfer_id"], ["transfers.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["adjustment_journal_id"], ["journal_transactions.id"], ondelete="RESTRICT"),
        Index("ix_reconciliation_open", "tenant_id", "status", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    run_id: Mapped[uuid.UUID] = mapped_column()
    statement_line_id: Mapped[uuid.UUID | None] = mapped_column()
    transfer_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="open")
    explanation: Mapped[str] = mapped_column(Text)
    expected: Mapped[dict | None] = mapped_column(JSON)
    actual: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolution: Mapped[str | None] = mapped_column(String(80))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    adjustment_journal_id: Mapped[uuid.UUID | None] = mapped_column()
