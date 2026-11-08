from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from proof.errors import NotFoundError, ProofError
from proof.ledger import service as ledger_service
from proof.ledger.models import Account
from proof.ledger.schemas import EntryCreate, JournalCreate
from proof.messaging.models import OutboxEvent
from proof.operations.models import AuditEvent
from proof.payments.models import IdempotencyRecord, PaymentChange, Transfer
from proof.payments.schemas import PaymentAction, TransferCreate

ACTIVE_HOLDS = ("authorized", "submitted")
TERMINAL = {"succeeded", "failed", "cancelled", "expired", "reversed"}
TRANSITIONS = {
    "authorize": ({"created"}, "authorized"),
    "submit": ({"authorized"}, "submitted"),
    "capture": ({"submitted"}, "succeeded"),
    "fail": ({"submitted"}, "failed"),
    "cancel": ({"created", "authorized", "submitted"}, "cancelled"),
    "expire": (set(ACTIVE_HOLDS), "expired"),
    "refund": ({"succeeded"}, "succeeded"),
}


def _claim(
    session: Session, tenant_id: uuid.UUID, operation: str, key: str, command: BaseModel
) -> tuple[IdempotencyRecord, bool]:
    if not 8 <= len(key) <= 160:
        raise ProofError("invalid_idempotency_key", "Idempotency-Key must be 8 to 160 characters")
    canonical = json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    created_id = session.scalar(
        insert(IdempotencyRecord).values(
            tenant_id=tenant_id, operation=operation, key=key, request_hash=digest, status="pending",
        ).on_conflict_do_nothing(
            index_elements=["tenant_id", "operation", "key"]
        ).returning(IdempotencyRecord.id)
    )
    record = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == tenant_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.key == key,
    ))
    if record is None:
        raise ProofError("idempotency_outcome_missing", "the stored command outcome is unavailable", 500)
    if record.request_hash != digest:
        raise ProofError("idempotency_key_conflict", "the idempotency key was reused with different content", 409)
    if created_id is None and (record.status != "completed" or record.resource_id is None):
        raise ProofError("idempotency_in_progress", "the original command is still in progress", 409)
    return record, created_id is None


def _complete(record: IdempotencyRecord, resource_id: uuid.UUID, now: datetime) -> None:
    record.status = "completed"
    record.resource_id = resource_id
    record.response_status = 201
    record.completed_at = now


def _accounts(session: Session, tenant_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Account]:
    accounts = session.scalars(select(Account).where(
        Account.tenant_id == tenant_id, Account.id.in_(ids)
    ).order_by(Account.id).with_for_update()).all()
    if len(accounts) != len(ids):
        raise NotFoundError("account")
    if len({account.currency for account in accounts}) != 1:
        raise ProofError("currency_mismatch", "payment accounts must use the same currency")
    return {account.id: account for account in accounts}


def _require_available(
    session: Session, account: Account, amount: int, now: datetime, *, excluding: uuid.UUID | None = None
) -> None:
    if account.allow_negative:
        return
    _, balance = ledger_service.account_balance(session, account.tenant_id, account.id)
    query = select(func.coalesce(func.sum(Transfer.amount_minor), 0)).where(
        Transfer.tenant_id == account.tenant_id,
        Transfer.source_account_id == account.id,
        Transfer.status.in_(ACTIVE_HOLDS),
        Transfer.hold_expires_at > now,
    )
    if excluding is not None:
        query = query.where(Transfer.id != excluding)
    held = int(session.scalar(query) or 0)
    if balance - held < amount:
        raise ProofError("insufficient_funds", "account has insufficient available funds", 409)


def _emit(session: Session, transfer: Transfer, event_type: str, **detail: object) -> None:
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    if "traceparent" in carrier:
        detail["traceparent"] = carrier["traceparent"]
    session.add(OutboxEvent(
        tenant_id=transfer.tenant_id,
        aggregate_type="transfer",
        aggregate_id=transfer.id,
        event_type=event_type,
        payload={
            "transfer_id": str(transfer.id), "tenant_id": str(transfer.tenant_id),
            "amount_minor": transfer.amount_minor, "currency": transfer.currency,
            "journal_id": str(transfer.journal_id) if transfer.journal_id else None,
            **detail,
        },
    ))


def create_transfer(
    session: Session, tenant_id: uuid.UUID, idempotency_key: str, command: TransferCreate,
    *, deferred: bool = False,
) -> tuple[Transfer, bool]:
    ledger_service.require_tenant(session, tenant_id)
    operation = "payment_intent.create" if deferred else "transfer.create"
    record, replayed = _claim(session, tenant_id, operation, idempotency_key, command)
    if replayed:
        return get_transfer(session, tenant_id, record.resource_id), True
    accounts = _accounts(session, tenant_id, {command.source_account_id, command.destination_account_id})
    source = accounts[command.source_account_id]
    now = datetime.now(timezone.utc)
    transfer_id = uuid.uuid4()
    journal_id = None
    if not deferred:
        _require_available(session, source, command.amount_minor, now)
        journal_id = ledger_service.post_journal(session, tenant_id, JournalCreate(
            reference=f"transfer/{transfer_id}",
            description=command.description,
            entries=[
                EntryCreate(account_id=source.id, amount_minor=-command.amount_minor),
                EntryCreate(account_id=command.destination_account_id, amount_minor=command.amount_minor),
            ],
        ), commit=False).id
    transfer = Transfer(
        id=transfer_id, tenant_id=tenant_id, client_reference=command.client_reference,
        source_account_id=source.id, destination_account_id=command.destination_account_id,
        amount_minor=command.amount_minor, currency=source.currency, description=command.description,
        status="created" if deferred else "succeeded", journal_id=journal_id, created_at=now,
        completed_at=None if deferred else now,
    )
    session.add(transfer)
    _emit(session, transfer, f"transfer.{transfer.status}")
    _complete(record, transfer.id, now)
    session.commit()
    return transfer, False


def get_transfer(session: Session, tenant_id: uuid.UUID, transfer_id: uuid.UUID) -> Transfer:
    transfer = session.scalar(select(Transfer).where(Transfer.tenant_id == tenant_id, Transfer.id == transfer_id))
    if transfer is None:
        raise NotFoundError("transfer")
    return transfer


def change_payment(
    session: Session, tenant_id: uuid.UUID, transfer_id: uuid.UUID, key: str,
    command: PaymentAction, actor: str, request_id: str | None = None,
) -> tuple[PaymentChange, bool]:
    transfer = session.scalar(select(Transfer).where(
        Transfer.tenant_id == tenant_id, Transfer.id == transfer_id
    ).with_for_update().execution_options(populate_existing=True))
    if transfer is None:
        raise NotFoundError("transfer")
    record, replayed = _claim(session, tenant_id, f"payment.{transfer_id}", key, command)
    if replayed:
        change = session.get(PaymentChange, record.resource_id)
        if change is None or change.tenant_id != tenant_id:
            raise ProofError("idempotency_outcome_missing", "the stored command outcome is unavailable", 500)
        return change, True

    allowed, next_status = TRANSITIONS[command.action]
    previous = transfer.status
    if previous not in allowed:
        raise ProofError("invalid_payment_transition", f"cannot {command.action} a {previous} payment", 409)
    account_ids = {transfer.source_account_id, transfer.destination_account_id}
    if command.fee_account_id is not None:
        if command.fee_account_id in account_ids:
            raise ProofError("invalid_fee_account", "fee account must differ from the payment accounts")
        account_ids.add(command.fee_account_id)
    accounts = _accounts(session, tenant_id, account_ids)
    now = datetime.now(timezone.utc)
    expiry = transfer.hold_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    expired = expiry is not None and expiry <= now
    if (command.action in {"submit", "capture"} and expired) or (command.action == "expire" and not expired):
        raise ProofError("invalid_hold_time", "the payment hold is outside the required time window", 409)

    source = accounts[transfer.source_account_id]
    destination = accounts[transfer.destination_account_id]
    change_id = uuid.uuid4()
    amount = transfer.amount_minor if command.amount_minor is None else command.amount_minor
    entries: list[EntryCreate] = []
    if command.action == "authorize":
        _require_available(session, source, amount, now)
        transfer.hold_expires_at = now + timedelta(minutes=15)
    elif command.action == "capture":
        total = amount + command.fee_minor
        if total > 2**63 - 1:
            raise ProofError("payment_amount_out_of_range", "principal plus fee exceeds the ledger amount limit")
        _require_available(session, source, total, now, excluding=transfer.id)
        entries = [
            EntryCreate(account_id=source.id, amount_minor=-total),
            EntryCreate(account_id=destination.id, amount_minor=amount),
        ]
        if command.fee_account_id is not None:
            entries.append(EntryCreate(account_id=command.fee_account_id, amount_minor=command.fee_minor))
    elif command.action == "refund":
        if transfer.refunded_minor + amount > transfer.amount_minor:
            raise ProofError("refund_exceeds_capture", "refund exceeds the unrefunded principal", 409)
        _require_available(session, destination, amount, now)
        entries = [
            EntryCreate(account_id=destination.id, amount_minor=-amount),
            EntryCreate(account_id=source.id, amount_minor=amount),
        ]
        if transfer.refunded_minor + amount == transfer.amount_minor:
            next_status = "reversed"

    journal_id = None
    if entries:
        journal_id = ledger_service.post_journal(session, tenant_id, JournalCreate(
            reference=f"payment-change/{change_id}", description=command.reason, entries=entries,
        ), commit=False).id
    if command.action == "capture":
        transfer.journal_id = journal_id
    if command.action == "refund":
        transfer.refunded_minor += amount
    transfer.status = next_status
    if next_status in TERMINAL and transfer.completed_at is None:
        transfer.completed_at = now
    change = PaymentChange(
        id=change_id, tenant_id=tenant_id, transfer_id=transfer.id, action=command.action,
        from_status=previous, to_status=next_status, amount_minor=amount, fee_minor=command.fee_minor,
        journal_id=journal_id, reason=command.reason, created_at=now,
    )
    event_type = f"transfer.{next_status}" if command.action != "refund" else "transfer.refunded"
    details = {"change_id": str(change_id), "action": command.action,
               "change_journal_id": str(journal_id) if journal_id else None, "change_amount_minor": amount}
    _emit(session, transfer, event_type, **details)
    session.add(AuditEvent(
        tenant_id=tenant_id, actor=actor, action=f"payment.{command.action}", resource_type="transfer",
        resource_id=transfer.id, reason=command.reason, details={**details, "request_id": request_id},
    ))
    session.add(change)
    _complete(record, change.id, now)
    session.commit()
    return change, False


def expire_due_payment(session: Session) -> bool:
    due = session.execute(select(Transfer.tenant_id, Transfer.id).where(
        Transfer.status.in_(ACTIVE_HOLDS),
        Transfer.hold_expires_at <= datetime.now(timezone.utc),
    ).order_by(Transfer.hold_expires_at, Transfer.id).limit(1).with_for_update(skip_locked=True)).one_or_none()
    if due is None:
        return False
    tenant_id, transfer_id = due
    change_payment(
        session, tenant_id, transfer_id, f"scheduled-expiry-{transfer_id}",
        PaymentAction(action="expire", reason="Authorization window expired"),
        actor="hold-scheduler",
    )
    return True
