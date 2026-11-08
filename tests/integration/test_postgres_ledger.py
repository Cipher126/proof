from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker
from fastapi import Response

from proof.config import settings
from proof.demo import DEMO_ADMISSION_LOCK, run_canonical_scenario
from proof.ledger import service
from proof.ledger.schemas import JournalCreate
from proof.errors import ProofError
from proof.messaging.models import OutboxEvent
from proof.messaging.service import dispatch_batch
from proof.payments import service as payment_service
from proof.payments.models import IdempotencyRecord, Transfer
from proof.payments.schemas import TransferCreate
from datetime import datetime, timedelta, timezone

pytestmark = pytest.mark.integration
SessionLocal = sessionmaker(expire_on_commit=False)


@pytest.fixture(scope="module", autouse=True)
def isolated_schema():
    schema = f"proof_test_{uuid.uuid4().hex}"
    admin = create_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        SessionLocal.configure(bind=engine)
        yield
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture(autouse=True)
def clean_database(isolated_schema):
    with SessionLocal.begin() as session:
        session.execute(
            text(
                "TRUNCATE demo_credentials, audit_events, reconciliation_findings, reconciliation_runs, "
                "statement_lines, statement_imports, provider_events, outbox_events, "
                "idempotency_records, transfers, "
                "journal_entries, journal_transactions, accounts, tenants"
            )
        )


def _ledger_fixture():
    with SessionLocal() as session:
        tenant = service.create_tenant(session, "PostgreSQL verification")
        left = service.create_account(session, tenant.id, "Clearing", "NGN")
        right = service.create_account(session, tenant.id, "Merchant payable", "NGN")
        return tenant.id, left.id, right.id


def test_demo_admission_lock_is_shared_across_postgres_connections() -> None:
    with SessionLocal.begin() as owner:
        owner.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DEMO_ADMISSION_LOCK})
        with SessionLocal() as contender, pytest.raises(ProofError) as error:
            run_canonical_scenario(Response(), contender)
        assert error.value.code == "demo_busy"
    with SessionLocal() as contender:
        scenario = run_canonical_scenario(Response(), contender)
        assert scenario.transfer_replayed and scenario.provider_duplicate


def test_database_rejects_unbalanced_posting() -> None:
    tenant_id, left_id, right_id = _ledger_fixture()
    journal_id = uuid.uuid4()
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO journal_transactions
                  (id, tenant_id, reference, description, status, created_at)
                VALUES (:id, :tenant_id, 'direct/unbalanced', 'must fail', 'draft', now())
                """
            ),
            {"id": journal_id, "tenant_id": tenant_id},
        )
        session.execute(
            text(
                """
                INSERT INTO journal_entries
                  (id, tenant_id, journal_id, account_id, position, amount_minor, currency, created_at)
                VALUES
                  (:e1, :tenant_id, :journal_id, :left_id, 0, -100, 'NGN', now()),
                  (:e2, :tenant_id, :journal_id, :right_id, 1, 99, 'NGN', now())
                """
            ),
            {
                "e1": uuid.uuid4(),
                "e2": uuid.uuid4(),
                "tenant_id": tenant_id,
                "journal_id": journal_id,
                "left_id": left_id,
                "right_id": right_id,
            },
        )
        with pytest.raises(DBAPIError, match="not balanced"):
            session.execute(
                text("UPDATE journal_transactions SET status = 'posted' WHERE id = :id"),
                {"id": journal_id},
            )
            session.flush()


def test_cannot_insert_a_journal_already_posted() -> None:
    tenant_id, _, _ = _ledger_fixture()
    with SessionLocal() as session, pytest.raises(DBAPIError, match="must start in draft"):
        session.execute(
            text("""
                INSERT INTO journal_transactions
                  (id, tenant_id, reference, description, status, created_at, posted_at)
                VALUES (:id, :tenant_id, 'direct/posted', 'invalid', 'posted', now(), now())
            """),
            {"id": uuid.uuid4(), "tenant_id": tenant_id},
        )


def test_posted_entries_are_immutable_and_reversal_is_balanced() -> None:
    tenant_id, left_id, right_id = _ledger_fixture()
    with SessionLocal() as session:
        original = service.post_journal(
            session,
            tenant_id,
            JournalCreate(
                reference="direct/original",
                description="Original posting",
                entries=[
                    {"account_id": left_id, "amount_minor": -500},
                    {"account_id": right_id, "amount_minor": 500},
                ],
            ),
        )
        reversal = service.reverse_journal(
            session, tenant_id, original.id, "direct/reversal", "Operator correction"
        )
        assert reversal.reverses_id == original.id
        assert sum(entry.amount_minor for entry in reversal.entries) == 0

    with SessionLocal() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                text("UPDATE journal_entries SET amount_minor = 1 WHERE journal_id = :id"),
                {"id": original.id},
            )
            session.flush()

    with SessionLocal() as session, pytest.raises(DBAPIError, match="immutable"):
        session.execute(
            text("""
                INSERT INTO journal_entries
                  (id, tenant_id, journal_id, account_id, position, amount_minor, currency, created_at)
                VALUES (:id, :tenant_id, :journal_id, :account_id, 2, 100, 'NGN', now())
            """),
            {"id": uuid.uuid4(), "tenant_id": tenant_id, "journal_id": original.id,
             "account_id": left_id},
        )


def test_concurrent_transfers_cannot_overspend_and_emit_once() -> None:
    with SessionLocal() as session:
        tenant = service.create_tenant(session, "Concurrency verification")
        system = service.create_account(session, tenant.id, "System", "NGN", True)
        source = service.create_account(session, tenant.id, "Protected source", "NGN")
        destination_a = service.create_account(session, tenant.id, "Destination A", "NGN")
        destination_b = service.create_account(session, tenant.id, "Destination B", "NGN")
        service.post_journal(
            session,
            tenant.id,
            JournalCreate(
                reference="concurrency/funding",
                description="Fictional opening funds",
                entries=[
                    {"account_id": system.id, "amount_minor": -100},
                    {"account_id": source.id, "amount_minor": 100},
                ],
            ),
        )
        tenant_id = tenant.id
        source_id = source.id
        destination_ids = [destination_a.id, destination_b.id]

    def attempt(index: int) -> str:
        with SessionLocal() as session:
            try:
                payment_service.create_transfer(
                    session,
                    tenant_id,
                    f"concurrency-key-{index}",
                    TransferCreate(
                        client_reference=f"concurrency-transfer-{index}",
                        source_account_id=source_id,
                        destination_account_id=destination_ids[index],
                        amount_minor=80,
                        description="Competing transfer",
                    ),
                )
                return "succeeded"
            except ProofError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(attempt, [0, 1]))

    assert outcomes == ["insufficient_funds", "succeeded"]
    with SessionLocal() as session:
        _, balance = service.account_balance(session, tenant_id, source_id)
        assert balance == 20
        assert session.query(Transfer).count() == 1
        assert session.query(OutboxEvent).count() == 1
        assert session.query(IdempotencyRecord).count() == 1


def test_racing_retries_resolve_to_one_transfer() -> None:
    with SessionLocal() as session:
        tenant = service.create_tenant(session, "Idempotency race verification")
        system = service.create_account(session, tenant.id, "System", "NGN", True)
        source = service.create_account(session, tenant.id, "Source", "NGN")
        destination = service.create_account(session, tenant.id, "Destination", "NGN")
        service.post_journal(
            session,
            tenant.id,
            JournalCreate(
                reference="idempotency/funding",
                description="Fictional opening funds",
                entries=[
                    {"account_id": system.id, "amount_minor": -100},
                    {"account_id": source.id, "amount_minor": 100},
                ],
            ),
        )
        tenant_id = tenant.id
        source_id = source.id
        destination_id = destination.id

    command = TransferCreate(
        client_reference="same-command",
        source_account_id=source_id,
        destination_account_id=destination_id,
        amount_minor=50,
        description="The same retried command",
    )

    def attempt(_: int) -> tuple[str, bool]:
        with SessionLocal() as session:
            transfer, replayed = payment_service.create_transfer(
                session, tenant_id, "same-idempotency-key", command
            )
            return str(transfer.id), replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, [0, 1]))

    assert outcomes[0][0] == outcomes[1][0]
    assert sorted(replayed for _, replayed in outcomes) == [False, True]
    with SessionLocal() as session:
        _, balance = service.account_balance(session, tenant_id, source_id)
        assert balance == 50
        assert session.query(Transfer).count() == 1
        assert session.query(OutboxEvent).count() == 1
        assert session.query(IdempotencyRecord).count() == 1


def test_outbox_worker_retries_and_dead_letters_deterministically() -> None:
    with SessionLocal() as session:
        tenant = service.create_tenant(session, "Outbox verification")
        system = service.create_account(session, tenant.id, "System", "NGN", True)
        source = service.create_account(session, tenant.id, "Source", "NGN")
        destination = service.create_account(session, tenant.id, "Destination", "NGN")
        service.post_journal(
            session,
            tenant.id,
            JournalCreate(
                reference="outbox/funding",
                description="Fictional opening funds",
                entries=[
                    {"account_id": system.id, "amount_minor": -100},
                    {"account_id": source.id, "amount_minor": 100},
                ],
            ),
        )
        payment_service.create_transfer(
            session,
            tenant.id,
            "outbox-idempotency-key",
            TransferCreate(
                client_reference="outbox-transfer",
                source_account_id=source.id,
                destination_account_id=destination.id,
                amount_minor=40,
                description="Outbox failure demonstration",
            ),
        )

    start = datetime.now(timezone.utc)
    for offset in (0, 5, 20):
        with SessionLocal() as session:
            result = dispatch_batch(
                session,
                now=start + timedelta(seconds=offset),
                fail_event_types={"transfer.succeeded"},
                max_attempts=3,
            )
            assert result["failed"] == 1

    with SessionLocal() as session:
        event = session.scalar(select(OutboxEvent))
        assert event is not None
        assert event.attempts == 3
        assert event.published_at is None
        assert event.dead_lettered_at is not None
        assert event.last_error == "injected demo delivery failure"
        assert dispatch_batch(session, now=start + timedelta(seconds=60))["processed"] == 0


def test_outbox_worker_publishes_an_event_exactly_once() -> None:
    with SessionLocal() as session:
        tenant = service.create_tenant(session, "Outbox success verification")
        event = OutboxEvent(
            tenant_id=tenant.id,
            aggregate_type="verification",
            aggregate_id=uuid.uuid4(),
            event_type="verification.succeeded",
            payload={"fictional": True},
        )
        session.add(event)
        session.commit()
        event_id = event.id

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        first = dispatch_batch(session, now=now)
        assert first == {"processed": 1, "published": 1, "failed": 0, "dead_lettered": 0}
    with SessionLocal() as session:
        second = dispatch_batch(session, now=now + timedelta(seconds=30))
        assert second["processed"] == 0
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        assert event.attempts == 1
        assert event.published_at == now
