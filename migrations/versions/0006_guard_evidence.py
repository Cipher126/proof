"""Close direct-insert ledger bypasses and preserve evidence.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

EVIDENCE_TABLES = ("provider_events", "statement_imports", "statement_lines", "audit_events")


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION proof_require_draft_insert() RETURNS trigger AS $$
    BEGIN
      IF NEW.status <> 'draft' THEN
        RAISE EXCEPTION 'journals must start in draft' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_require_draft_insert BEFORE INSERT ON journal_transactions
      FOR EACH ROW EXECUTE FUNCTION proof_require_draft_insert();

    CREATE FUNCTION proof_guard_entry_write() RETURNS trigger AS $$
    DECLARE parent_id uuid; parent_status text;
    BEGIN
      IF TG_OP = 'UPDATE' AND (NEW.journal_id, NEW.tenant_id)
        IS DISTINCT FROM (OLD.journal_id, OLD.tenant_id) THEN
        RAISE EXCEPTION 'cannot move a journal entry' USING ERRCODE = '23514';
      END IF;
      parent_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.journal_id ELSE NEW.journal_id END;
      SELECT status INTO parent_status FROM journal_transactions WHERE id = parent_id FOR UPDATE;
      IF parent_status = 'posted' THEN
        RAISE EXCEPTION 'posted journal entries are immutable' USING ERRCODE = '23514';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    DROP TRIGGER trg_immutable_entry ON journal_entries;
    CREATE TRIGGER trg_immutable_entry BEFORE INSERT OR UPDATE OR DELETE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION proof_guard_entry_write();

    CREATE FUNCTION proof_reject_evidence_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'evidence is append-only' USING ERRCODE = '23514';
    END; $$ LANGUAGE plpgsql;
    """)
    for table in EVIDENCE_TABLES:
        op.execute(f"""
        CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON {table}
          FOR EACH ROW EXECUTE FUNCTION proof_reject_evidence_mutation();
        """)


def downgrade() -> None:
    for table in EVIDENCE_TABLES:
        op.execute(f"DROP TRIGGER trg_append_only ON {table}")
    op.execute("""
    DROP FUNCTION proof_reject_evidence_mutation();
    DROP TRIGGER trg_require_draft_insert ON journal_transactions;
    DROP FUNCTION proof_require_draft_insert();
    DROP TRIGGER trg_immutable_entry ON journal_entries;
    DROP FUNCTION proof_guard_entry_write();
    CREATE TRIGGER trg_immutable_entry BEFORE UPDATE OR DELETE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION proof_prevent_posted_mutation();
    """)
