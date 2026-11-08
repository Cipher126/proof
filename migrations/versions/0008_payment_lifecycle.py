"""Add deferred payment states and immutable transition records."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_transfer_status", "transfers", type_="check")
    op.alter_column("transfers", "journal_id", nullable=True)
    op.alter_column("transfers", "completed_at", nullable=True)
    op.add_column("transfers", sa.Column("description", sa.String(500), nullable=False, server_default="Transfer"))
    op.add_column("transfers", sa.Column("hold_expires_at", sa.DateTime(timezone=True)))
    op.add_column("transfers", sa.Column("refunded_minor", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_transfer_status", "transfers",
        "status IN ('created','authorized','submitted','succeeded','failed','cancelled','expired','reversed')")
    op.create_check_constraint("ck_transfer_posting_shape", "transfers", """
        ((status IN ('succeeded', 'reversed')) = (journal_id IS NOT NULL))
        AND ((status IN ('succeeded', 'failed', 'cancelled', 'expired', 'reversed')) = (completed_at IS NOT NULL))
    """)
    op.create_check_constraint("ck_transfer_refund_total", "transfers", """
        refunded_minor >= 0 AND refunded_minor <= amount_minor
        AND ((status = 'reversed') = (refunded_minor = amount_minor))
    """)
    op.create_index("ix_transfers_holds", "transfers", ["tenant_id", "source_account_id", "hold_expires_at"],
                    postgresql_where=sa.text("status IN ('authorized','submitted')"))
    op.create_table(
        "payment_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("transfer_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=False),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("fee_minor", sa.BigInteger(), nullable=False),
        sa.Column("journal_id", sa.Uuid()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "transfer_id"], ["transfers.tenant_id", "transfers.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "journal_id"], ["journal_transactions.tenant_id", "journal_transactions.id"]),
    )
    op.create_index("ix_payment_changes_transfer_id", "payment_changes", ["transfer_id"])
    op.execute("""
        CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON payment_changes
          FOR EACH ROW EXECUTE FUNCTION proof_reject_evidence_mutation()
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM payment_changes) OR EXISTS
             (SELECT 1 FROM transfers WHERE status <> 'succeeded') THEN
            RAISE EXCEPTION 'cannot downgrade after lifecycle writes';
          END IF;
        END $$
    """)
    op.drop_table("payment_changes")
    op.drop_index("ix_transfers_holds", table_name="transfers")
    for name in ("ck_transfer_refund_total", "ck_transfer_posting_shape", "ck_transfer_status"):
        op.drop_constraint(name, "transfers", type_="check")
    for name in ("refunded_minor", "hold_expires_at", "description"):
        op.drop_column("transfers", name)
    op.alter_column("transfers", "journal_id", nullable=False)
    op.alter_column("transfers", "completed_at", nullable=False)
    op.create_check_constraint("ck_transfer_status", "transfers", "status = 'succeeded'")
