"""Create the immutable double-entry ledger.

Revision ID: 0001
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = upper(currency) AND char_length(currency) = 3", name="ck_account_currency"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_account_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", "currency", name="uq_account_name_currency"),
    )
    op.create_table(
        "journal_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reverses_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'posted')", name="ck_journal_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reverses_id"], ["journal_transactions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_journal_tenant_id"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_journal_reference"),
        sa.UniqueConstraint("reverses_id", name="uq_journal_single_reversal"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor <> 0", name="ck_entry_nonzero"),
        sa.CheckConstraint("position >= 0", name="ck_entry_position"),
        sa.CheckConstraint("currency = upper(currency) AND char_length(currency) = 3", name="ck_entry_currency"),
        sa.ForeignKeyConstraint(["tenant_id", "journal_id"], ["journal_transactions.tenant_id", "journal_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "account_id"], ["accounts.tenant_id", "accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("journal_id", "position", name="uq_entry_journal_position"),
    )
    op.create_index("ix_entries_account_created", "journal_entries", ["tenant_id", "account_id", "created_at"])

    op.execute("""
    CREATE FUNCTION proof_validate_posted_journal() RETURNS trigger AS $$
    DECLARE entry_count integer; imbalance_count integer;
    BEGIN
      IF NEW.status = 'posted' AND OLD.status <> 'posted' THEN
        SELECT count(*) INTO entry_count FROM journal_entries WHERE journal_id = NEW.id;
        SELECT count(*) INTO imbalance_count FROM (
          SELECT currency FROM journal_entries WHERE journal_id = NEW.id
          GROUP BY currency HAVING sum(amount_minor) <> 0
        ) imbalances;
        IF entry_count < 2 THEN RAISE EXCEPTION 'posted journal requires at least two entries'; END IF;
        IF imbalance_count > 0 THEN RAISE EXCEPTION 'posted journal is not balanced'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;

    CREATE CONSTRAINT TRIGGER trg_validate_posted_journal
      AFTER UPDATE OF status ON journal_transactions
      DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
      EXECUTE FUNCTION proof_validate_posted_journal();

    CREATE FUNCTION proof_prevent_posted_mutation() RETURNS trigger AS $$
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

    CREATE TRIGGER trg_immutable_journal BEFORE UPDATE OR DELETE ON journal_transactions
      FOR EACH ROW EXECUTE FUNCTION proof_prevent_posted_mutation();
    CREATE TRIGGER trg_immutable_entry BEFORE UPDATE OR DELETE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION proof_prevent_posted_mutation();

    CREATE FUNCTION proof_validate_entry_currency() RETURNS trigger AS $$
    DECLARE account_currency text;
    BEGIN
      SELECT currency INTO account_currency FROM accounts WHERE id = NEW.account_id;
      IF account_currency IS NULL OR account_currency <> NEW.currency THEN
        RAISE EXCEPTION 'entry currency does not match account currency';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_entry_currency BEFORE INSERT OR UPDATE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION proof_validate_entry_currency();
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS proof_validate_entry_currency() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS proof_prevent_posted_mutation() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS proof_validate_posted_journal() CASCADE")
    op.drop_table("journal_entries")
    op.drop_table("journal_transactions")
    op.drop_table("accounts")
    op.drop_table("tenants")
