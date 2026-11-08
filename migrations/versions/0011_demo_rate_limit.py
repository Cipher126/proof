"""Store bounded per-client sandbox admission counters."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_admission_buckets",
        sa.Column("bucket", sa.BigInteger(), primary_key=True),
        sa.Column("client_hash", sa.String(64), primary_key=True),
        sa.Column("starts", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("demo_admission_buckets")
