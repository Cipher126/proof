"""Index the posted transfer window used in reconciliation."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_index(
        "ix_transfers_posted_window", "transfers", ["tenant_id", "completed_at"],
        postgresql_where=sa.text("journal_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_transfers_posted_window", table_name="transfers")
