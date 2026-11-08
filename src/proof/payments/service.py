from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from proof.errors import NotFoundError, ProofError, TenantBoundaryError
from proof.ledger import service as ledger_service
from proof.ledger.models import Account, JournalEntry, JournalTransaction
from proof.ledger.schemas import JournalCreate
from proof.messaging.models import OutboxEvent
from proof.payments.models import IdempotencyRecord, Transfer
from proof.payments.schemas import TransferCreate

OPERATION = "transfer.create"


def _hash_command(command: TransferCreate) -> str:
    canonical = json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_outcome(
    session: Session,
    tenant_id: uuid.UUID,
    key: str,
    request_hash: str,
) -> Transfer | None:
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.operation == OPERATION,
            IdempotencyRecord.key == key,
        )
    )
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise ProofError(
            "idempotency_key_conflict",
            "the idempotency key was already used with different request content",
            409,
        )
    if record.status != "completed" or record.resource_id is None:
        raise ProofError("idempotency_in_progress", "the original command is still in progress", 409)
    transfer = session.get(Transfer, record.resource_id)
    if transfer is None:
        raise ProofError("idempotency_outcome_missing", "the stored command outcome is unavailable", 500)
    return transfer


def create_transfer(
    session: Session,
    tenant_id: uuid.UUID,
    idempotency_key: str,
    command: TransferCreate,
) -> tuple[Transfer, bool]:
    if not 8 <= len(idempotency_key) <= 160:
        raise ProofError("invalid_idempotency_key", "Idempotency-Key must be 8 to 160 characters")

    ledger_service.require_tenant(session, tenant_id)
    request_hash = _hash_command(command)
    existing = _existing_outcome(session, tenant_id, idempotency_key, request_hash)
    if existing is not None:
        return existing, True

    record = IdempotencyRecord(
        tenant_id=tenant_id,
        operation=OPERATION,
        key=idempotency_key,
        request_hash=request_hash,
        status="pending",
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError:
        session.expire_all()
        existing = _existing_outcome(session, tenant_id, idempotency_key, request_hash)
        if existing is None:
            raise ProofError("idempotency_race", "the command outcome could not be resolved", 409)
        return existing, True

    account_ids = sorted(
        {command.source_account_id, command.destination_account_id}, key=str
    )
    accounts = session.scalars(
        select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()
    ).all()
    if len(accounts) != 2:
        raise NotFoundError("account")
    if any(account.tenant_id != tenant_id for account in accounts):
        raise TenantBoundaryError()
    by_id = {account.id: account for account in accounts}
    source = by_id[command.source_account_id]
    destination = by_id[command.destination_account_id]
    if source.currency != destination.currency:
        raise ProofError("currency_mismatch", "transfer accounts must use the same currency")

    source_balance = int(
        session.scalar(
            select(func.coalesce(func.sum(JournalEntry.amount_minor), 0))
            .join(JournalTransaction, JournalTransaction.id == JournalEntry.journal_id)
            .where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.account_id == source.id,
                JournalTransaction.status == "posted",
            )
        )
        or 0
    )
    if not source.allow_negative and source_balance < command.amount_minor:
        raise ProofError("insufficient_funds", "source account has insufficient available funds", 409)

    transfer_id = uuid.uuid4()
    journal = ledger_service.post_journal(
        session,
        tenant_id,
        JournalCreate(
            reference=f"transfer/{transfer_id}",
            description=command.description,
            entries=[
                {"account_id": source.id, "amount_minor": -command.amount_minor},
                {"account_id": destination.id, "amount_minor": command.amount_minor},
            ],
        ),
        commit=False,
    )
    now = datetime.now(timezone.utc)
    transfer = Transfer(
        id=transfer_id,
        tenant_id=tenant_id,
        client_reference=command.client_reference,
        source_account_id=source.id,
        destination_account_id=destination.id,
        amount_minor=command.amount_minor,
        currency=source.currency,
        status="succeeded",
        journal_id=journal.id,
        created_at=now,
        completed_at=now,
    )
    session.add(transfer)
    session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type="transfer",
            aggregate_id=transfer.id,
            event_type="transfer.succeeded",
            payload={
                "transfer_id": str(transfer.id),
                "tenant_id": str(tenant_id),
                "amount_minor": transfer.amount_minor,
                "currency": transfer.currency,
                "journal_id": str(journal.id),
            },
        )
    )
    record.status = "completed"
    record.resource_id = transfer.id
    record.response_status = 201
    record.completed_at = now
    session.commit()
    session.refresh(transfer)
    return transfer, False


def get_transfer(session: Session, tenant_id: uuid.UUID, transfer_id: uuid.UUID) -> Transfer:
    transfer = session.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFoundError("transfer")
    if transfer.tenant_id != tenant_id:
        raise TenantBoundaryError()
    return transfer
