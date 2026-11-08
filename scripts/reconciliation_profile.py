"""Build and explain a fictional history in the recovery drill's disposable database."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from proof.reconciliation.service import candidate_transfers

HISTORY_SIZE = 40_000
WINDOW_START = datetime(2026, 1, 2, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 1, 3, tzinfo=timezone.utc)


def seed_history(engine: Engine) -> UUID:
    tenant = uuid4()
    params = {"tenant": tenant, "source": uuid4(), "destination": uuid4(), "size": HISTORY_SIZE}
    statements = [
        """INSERT INTO tenants VALUES (:tenant, 'Profile tenant', now())""",
        """INSERT INTO accounts (id, tenant_id, name, currency, allow_negative, created_at)
            VALUES (:source, :tenant, 'Synthetic clearing', 'NGN', true, now()),
                   (:destination, :tenant, 'Synthetic destination', 'NGN', false, now())""",
        """INSERT INTO journal_transactions (id, tenant_id, reference, description, status, created_at)
            SELECT gen_random_uuid(), :tenant, 'profile-' || n, 'Synthetic history', 'draft',
                   '2026-01-01 00:00:00+00'::timestamptz
                   + CASE WHEN n > :size - 8 THEN interval '1 day' ELSE interval '0' END
            FROM generate_series(1, :size) AS n""",
        """INSERT INTO journal_entries (id, tenant_id, journal_id, account_id, position,
                                        amount_minor, currency, created_at)
            SELECT gen_random_uuid(), tenant_id, id,
                   CASE WHEN p = 0 THEN CAST(:source AS uuid) ELSE CAST(:destination AS uuid) END, p,
                   CASE WHEN p = 0 THEN -1 ELSE 1 END, 'NGN', created_at
            FROM journal_transactions CROSS JOIN generate_series(0, 1) AS p
            WHERE tenant_id = :tenant""",
        """UPDATE journal_transactions SET status = 'posted', posted_at = created_at
            WHERE tenant_id = :tenant""",
        """INSERT INTO transfers (id, tenant_id, client_reference, source_account_id,
                                  destination_account_id, amount_minor, currency, status, journal_id,
                                  description, refunded_minor, created_at, completed_at)
            SELECT gen_random_uuid(), tenant_id, reference, :source, :destination, 1, 'NGN',
                   'succeeded', id, 'Synthetic history', 0, created_at, posted_at
            FROM journal_transactions WHERE tenant_id = :tenant""",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement), params)
        connection.execute(text("ANALYZE transfers"))
    return tenant


def explain(engine: Engine, tenant: UUID) -> dict:
    query = candidate_transfers(tenant, ["profile-1"], WINDOW_START, WINDOW_END)
    compiled = query.compile(engine, compile_kwargs={"literal_binds": True})
    with engine.connect() as connection:
        references = sorted(row.client_reference for row in connection.execute(query))
        expected = sorted(["profile-1", *(f"profile-{n}" for n in range(HISTORY_SIZE - 7, HISTORY_SIZE + 1))])
        if references != expected:
            raise RuntimeError("reconciliation candidate set differs from the seeded evidence")
        plans = [
            connection.exec_driver_sql(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled}").scalar_one()[0]
            for _ in range(5)
        ]
    return {
        "references": references,
        "execution_ms": [plan["Execution Time"] for plan in plans],
        "plan": plans[-1]["Plan"],
    }
