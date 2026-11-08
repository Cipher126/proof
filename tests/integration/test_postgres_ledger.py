from __future__ import annotations

import uuid
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker
from fastapi import Request, Response

from proof.config import settings
from proof.demo import DEMO_ADMISSION_LOCK, adjust_demo_finding, run_canonical_scenario
from proof import maintenance
from proof.identity import DemoCredential, TenantAccess, issue_operator_credential
from proof.ledger.models import Tenant
from proof.reconciliation import service as reconciliation_service
from proof.reconciliation.schemas import StatementImportCreate
from types import SimpleNamespace
from proof.ledger import service
from proof.ledger.schemas import JournalCreate
from proof.errors import ProofError
from proof.messaging.models import OutboxEvent
from proof.messaging.service import dispatch_batch
from proof.messaging.http_sink import HttpSink
from proof.payments import service as payment_service
from proof.payments.models import IdempotencyRecord, Transfer
from proof.payments.schemas import PaymentAction, TransferCreate
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
                "TRUNCATE demo_admission_buckets, demo_credentials, operator_credentials, audit_events, reconciliation_findings, reconciliation_runs, "
                "statement_lines, statement_imports, provider_events, outbox_events, "
                "idempotency_records, payment_changes, transfers, "
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
    request = Request({"type": "http", "client": ("127.0.0.1", 50000)})
    with SessionLocal.begin() as owner:
        owner.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DEMO_ADMISSION_LOCK})
        with SessionLocal() as contender, pytest.raises(ProofError) as error:
            run_canonical_scenario(Response(), contender, request=request)
        assert error.value.code == "demo_busy"
    with SessionLocal() as contender:
        scenario = run_canonical_scenario(Response(), contender, request=request)
        assert scenario.transfer_replayed and scenario.provider_duplicate


def test_worker_can_recover_after_receiver_accepts_before_commit() -> None:
    tenant_id, _, _ = _ledger_fixture()
    with SessionLocal.begin() as session:
        event = OutboxEvent(tenant_id=tenant_id, aggregate_type="test", aggregate_id=uuid.uuid4(),
                            event_type="test.recovery", payload={})
        session.add(event)
        session.flush()
        event_id = event.id

    attempts = []

    def accepted_then_crash(event):
        attempts.append(event.id)
        raise KeyboardInterrupt()

    with SessionLocal() as session, pytest.raises(KeyboardInterrupt):
        dispatch_batch(session, batch_size=1, deliver=accepted_then_crash)
    with SessionLocal() as session:
        assert dispatch_batch(session, batch_size=1, deliver=lambda event: attempts.append(event.id))["published"] == 1
        assert session.get(OutboxEvent, event_id).attempts == 1
    assert attempts == [event_id, event_id]


def test_http_outbox_delivery_uses_stable_idempotency_header() -> None:
    received = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.headers["Idempotency-Key"], body))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            pass

    tenant_id, _, _ = _ledger_fixture()
    with SessionLocal.begin() as session:
        event = OutboxEvent(tenant_id=tenant_id, aggregate_type="test", aggregate_id=uuid.uuid4(),
                            event_type="test.http_delivery", payload={"fictional": True})
        session.add(event)
        session.flush()
        event_id = str(event.id)
    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as receiver:
        thread = Thread(target=receiver.serve_forever, daemon=True)
        thread.start()
        try:
            with SessionLocal() as session:
                sink = HttpSink(f"http://127.0.0.1:{receiver.server_port}/", None)
                assert dispatch_batch(session, batch_size=1, deliver=sink)["published"] == 1
        finally:
            receiver.shutdown()
            thread.join(timeout=3)
    assert len(received) == 1
    key, body = received[0]
    assert key == body["id"] == event_id


def test_retention_only_prunes_expired_anonymous_tenants(monkeypatch) -> None:
    monkeypatch.setattr(maintenance, "settings", SimpleNamespace(environment="sandbox"))
    monkeypatch.setenv("PROOF_DEMO_RETENTION_ENABLED", "1")
    request = Request({"type": "http", "client": ("127.0.0.1", 50000)})
    with SessionLocal() as session:
        ids = [uuid.UUID(run_canonical_scenario(Response(), session, request=request).tenant_id)
               for _ in range(3)]
        issue_operator_credential(session, ids[1], "Named operator", "operator", 1)
        expired = session.scalars(select(DemoCredential).where(DemoCredential.tenant_id.in_(ids[:2])))
        for credential in expired:
            credential.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
        session.commit()
    with SessionLocal() as session:
        assert maintenance.prune_expired_demo_tenants(session) == 1
        assert session.get(Tenant, ids[0]) is not None
    with SessionLocal() as session:
        assert maintenance.prune_expired_demo_tenants(session, apply=True) == 1
        assert session.get(Tenant, ids[0]) is None
        assert session.get(Tenant, ids[1]) is not None
        assert session.get(Tenant, ids[2]) is not None


def test_concurrent_reconciliation_and_adjustment_converge() -> None:
    request = Request({"type": "http", "client": ("127.0.0.1", 50000)})
    with SessionLocal() as session:
        scenario = run_canonical_scenario(Response(), session, request=request)
        tenant = uuid.UUID(scenario.tenant_id)
        credential_id = session.scalar(select(DemoCredential.id).where(DemoCredential.tenant_id == tenant))
        access = TenantAccess(tenant, credential_id, "demo")
    now = datetime.now(timezone.utc)
    command = StatementImportCreate.model_validate({
        "provider": "proof-simulated-payments", "filename": "concurrent.json",
        "period_start": now - timedelta(hours=1), "period_end": now + timedelta(hours=1),
        "lines": [{"provider_reference": "race", "client_reference": scenario.transfer.client_reference,
                   "amount_minor": scenario.transfer.amount_minor, "currency": "NGN",
                   "status": "succeeded", "occurred_at": now - timedelta(hours=2)}],
    })

    def import_and_run(_):
        with SessionLocal() as session:
            statement, _ = reconciliation_service.import_statement(session, tenant, command)
            run, findings = reconciliation_service.reconcile_statement(session, tenant, statement.id)
            return statement.id, run.id, [finding.kind for finding in findings]

    def adjust(_):
        with SessionLocal() as session:
            return adjust_demo_finding(scenario.findings[0].id, session, access).adjustment_journal_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        imports = list(executor.map(import_and_run, range(2)))
        adjustments = list(executor.map(adjust, range(2)))
    assert imports[0] == imports[1] and imports[0][2] == ["timing_difference"]
    assert adjustments[0] is not None and adjustments[0] == adjustments[1]


def test_racing_payment_authorizations_reserve_funds_once() -> None:
    tenant_id, source_id, destination_id = _ledger_fixture()
    with SessionLocal() as session:
        service.post_journal(session, tenant_id, JournalCreate(
            reference="race/funding", description="Fictional opening funds",
            entries=[{"account_id": source_id, "amount_minor": 100},
                     {"account_id": destination_id, "amount_minor": -100}],
        ))
        payment_ids = [
            payment_service.create_transfer(session, tenant_id, f"hold-intent-{index}", TransferCreate(
                client_reference=f"hold-{index}", source_account_id=source_id,
                destination_account_id=destination_id, amount_minor=70, description="Competing hold",
            ), deferred=True)[0].id for index in range(2)
        ]

    def authorize(payment_id):
        with SessionLocal() as session:
            try:
                change, _ = payment_service.change_payment(
                    session, tenant_id, payment_id, "authorize-hold",
                    PaymentAction(action="authorize", reason="Competing hold"), "test",
                )
                return change.to_status
            except ProofError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(authorize, payment_ids)) == ["authorized", "insufficient_funds"]
    with SessionLocal.begin() as session:
        held = session.scalar(select(Transfer).where(Transfer.status == "authorized"))
        held.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        held_id = held.id
    with SessionLocal() as session:
        assert payment_service.expire_due_payment(session)
        assert session.get(Transfer, held_id).status == "expired"
        assert not payment_service.expire_due_payment(session)


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
