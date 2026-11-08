"""Record settlement closure independently of reconciliation completion."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reconciliation_runs", sa.Column("closed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("reconciliation_runs", "closed_at")
