"""Allow draft mutations while preserving posted immutability.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION proof_prevent_posted_mutation() RETURNS trigger AS $$
        DECLARE journal_status text;
        BEGIN
          IF TG_TABLE_NAME = 'journal_transactions' THEN
            IF OLD.status = 'posted' THEN
              RAISE EXCEPTION 'posted journals are immutable';
            END IF;
          ELSE
            SELECT status INTO journal_status
            FROM journal_transactions WHERE id = OLD.journal_id;
            IF journal_status = 'posted' THEN
              RAISE EXCEPTION 'posted journal entries are immutable';
            END IF;
          END IF;

          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION proof_prevent_posted_mutation() RETURNS trigger AS $$
        DECLARE journal_status text;
        BEGIN
          IF TG_TABLE_NAME = 'journal_transactions' THEN
            IF OLD.status = 'posted' THEN RAISE EXCEPTION 'posted journals are immutable'; END IF;
          ELSE
            SELECT status INTO journal_status FROM journal_transactions WHERE id = OLD.journal_id;
            IF journal_status = 'posted' THEN RAISE EXCEPTION 'posted journal entries are immutable'; END IF;
          END IF;
          RETURN OLD;
        END; $$ LANGUAGE plpgsql;
        """
    )
