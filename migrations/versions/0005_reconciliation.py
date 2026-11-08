"""Add statement evidence, reconciliation findings, and audited resolution.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(160), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_table(
        "statement_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("raw_evidence", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "provider", "content_hash", name="uq_statement_content"),
    )
    op.create_index("ix_statement_imports_tenant_id", "statement_imports", ["tenant_id"])
    op.create_table(
        "statement_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("statement_import_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("provider_reference", sa.String(160), nullable=False),
        sa.Column("client_reference", sa.String(160), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider_status", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["statement_import_id"], ["statement_imports.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("statement_import_id", "line_number", name="uq_statement_line_number"),
    )
    op.create_index("ix_statement_lines_tenant_id", "statement_lines", ["tenant_id"])
    op.create_index("ix_statement_line_reference", "statement_lines", ["tenant_id", "client_reference"])
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("statement_import_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('running', 'completed')", name="ck_reconciliation_run_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["statement_import_id"], ["statement_imports.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("statement_import_id", name="uq_reconciliation_statement"),
    )
    op.create_index("ix_reconciliation_runs_tenant_id", "reconciliation_runs", ["tenant_id"])
    op.create_table(
        "reconciliation_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("statement_line_id", sa.Uuid()),
        sa.Column("transfer_id", sa.Uuid()),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("expected", sa.JSON()),
        sa.Column("actual", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(160)),
        sa.Column("resolution", sa.String(80)),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("adjustment_journal_id", sa.Uuid()),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_reconciliation_finding_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["reconciliation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["statement_line_id"], ["statement_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transfer_id"], ["transfers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["adjustment_journal_id"], ["journal_transactions.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_reconciliation_findings_tenant_id", "reconciliation_findings", ["tenant_id"])
    op.create_index("ix_reconciliation_open", "reconciliation_findings", ["tenant_id", "status", "kind"])


def downgrade() -> None:
    op.drop_table("reconciliation_findings")
    op.drop_table("reconciliation_runs")
    op.drop_table("statement_lines")
    op.drop_table("statement_imports")
    op.drop_table("audit_events")
