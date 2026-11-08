"""Add signed provider evidence and recoverable outbox state.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("last_error", sa.Text()))
    op.add_column("outbox_events", sa.Column("dead_lettered_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_transfer_tenant_id", "transfers", ["tenant_id", "id"])
    op.create_table(
        "provider_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("provider_transfer_id", sa.String(160), nullable=False),
        sa.Column("client_reference", sa.String(160), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider_status", sa.String(40), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("transfer_id", sa.Uuid()),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["transfers.tenant_id", "transfers.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "provider", "event_id", name="uq_provider_event_identity"),
    )
    op.create_index("ix_provider_events_tenant_id", "provider_events", ["tenant_id"])
    op.create_index(
        "ix_provider_event_transfer",
        "provider_events",
        ["tenant_id", "transfer_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_table("provider_events")
    op.drop_constraint("uq_transfer_tenant_id", "transfers", type_="unique")
    op.drop_column("outbox_events", "dead_lettered_at")
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "next_attempt_at")
