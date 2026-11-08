from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from proof.config import settings
from proof.db import SessionLocal
from proof.demo import DEMO_ADMISSION_LOCK
from proof.identity import DemoCredential, OperatorCredential

# These are fixed SQL identifiers. Values are always bound parameters.
_TABLES_IN_DELETE_ORDER = (
    "demo_credentials", "audit_events", "reconciliation_findings",
    "reconciliation_runs", "statement_lines", "statement_imports", "provider_events",
    "outbox_events", "idempotency_records", "payment_changes", "transfers",
    "journal_entries", "journal_transactions", "accounts",
)
_PROTECTED = {
    "audit_events": "trg_append_only",
    "statement_lines": "trg_append_only", "statement_imports": "trg_append_only",
    "provider_events": "trg_append_only", "payment_changes": "trg_append_only",
    "journal_entries": "trg_immutable_entry", "journal_transactions": "trg_immutable_journal",
}


def prune_expired_demo_tenants(session: Session, *, apply: bool = False, limit: int = 20) -> int:
    if session.get_bind().dialect.name != "postgresql" or settings.environment != "sandbox":
        raise RuntimeError("retention requires a PostgreSQL sandbox database")
    if not 1 <= limit <= 100:
        raise ValueError("retention batch size must be between 1 and 100")
    if apply and os.getenv("PROOF_DEMO_RETENTION_ENABLED") != "1":
        raise RuntimeError("retention writes require PROOF_DEMO_RETENTION_ENABLED=1")
    with session.begin():
        if apply:
            session.execute(text("SET LOCAL lock_timeout = '3s'"))
            if not session.scalar(select(func.pg_try_advisory_xact_lock(DEMO_ADMISSION_LOCK))):
                return 0
            # Exclude concurrent credential issuance while selecting eligible tenants.
            session.execute(text("LOCK TABLE operator_credentials IN SHARE MODE"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        candidates = session.scalars(select(DemoCredential.tenant_id).where(
            DemoCredential.expires_at < cutoff,
            ~select(OperatorCredential.id).where(
                OperatorCredential.tenant_id == DemoCredential.tenant_id
            ).exists(),
        ).order_by(DemoCredential.expires_at, DemoCredential.id).limit(limit)).all()
        if not apply or not candidates:
            return len(candidates)
        for table, trigger in _PROTECTED.items():
            session.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        for tenant_id in candidates:
            for table in _TABLES_IN_DELETE_ORDER:
                session.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tenant"), {"tenant": tenant_id})
            session.execute(text("DELETE FROM tenants WHERE id = :tenant"), {"tenant": tenant_id})
        for table, trigger in _PROTECTED.items():
            session.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))
        return len(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune expired anonymous tenants from a dedicated sandbox")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if args.loop and not args.apply:
        parser.error("--loop requires --apply")
    while True:
        with SessionLocal() as session:
            count = prune_expired_demo_tenants(session, apply=args.apply)
        print(json.dumps({"event": "demo.retention", "applied": args.apply, "tenants": count}), flush=True)
        if not args.loop:
            return
        time.sleep(600)


if __name__ == "__main__":
    main()
