from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from proof.errors import NotFoundError, ProofError, TenantBoundaryError
from proof.ledger.models import Account, JournalEntry, JournalTransaction, Tenant
from proof.ledger.schemas import JournalCreate


def create_tenant(session: Session, name: str) -> Tenant:
    tenant = Tenant(name=name.strip())
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


def require_tenant(session: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("tenant")
    return tenant


def create_account(
    session: Session,
    tenant_id: uuid.UUID,
    name: str,
    currency: str,
    allow_negative: bool = False,
) -> Account:
    require_tenant(session, tenant_id)
    account = Account(
        tenant_id=tenant_id,
        name=name.strip(),
        currency=currency,
        allow_negative=allow_negative,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def require_account(session: Session, tenant_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise NotFoundError("account")
    if account.tenant_id != tenant_id:
        raise TenantBoundaryError()
    return account


def post_journal(
    session: Session,
    tenant_id: uuid.UUID,
    command: JournalCreate,
    *,
    reverses_id: uuid.UUID | None = None,
    commit: bool = True,
) -> JournalTransaction:
    require_tenant(session, tenant_id)
    account_ids = sorted({entry.account_id for entry in command.entries}, key=str)
    accounts = session.scalars(
        select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()
    ).all()
    if len(accounts) != len(account_ids):
        raise NotFoundError("account")
    if any(account.tenant_id != tenant_id for account in accounts):
        raise TenantBoundaryError()

    accounts_by_id = {account.id: account for account in accounts}
    totals: dict[str, int] = defaultdict(int)
    for entry in command.entries:
        account = accounts_by_id[entry.account_id]
        totals[account.currency] += entry.amount_minor
    if any(total != 0 for total in totals.values()):
        raise ProofError("unbalanced_journal", "entries must sum to zero for every currency")

    journal = JournalTransaction(
        tenant_id=tenant_id,
        reference=command.reference,
        description=command.description,
        status="draft",
        reverses_id=reverses_id,
    )
    session.add(journal)
    session.flush()
    for position, entry in enumerate(command.entries):
        account = accounts_by_id[entry.account_id]
        session.add(
            JournalEntry(
                tenant_id=tenant_id,
                journal_id=journal.id,
                account_id=account.id,
                position=position,
                amount_minor=entry.amount_minor,
                currency=account.currency,
            )
        )
    session.flush()
    journal.status = "posted"
    journal.posted_at = datetime.now(timezone.utc)
    if commit:
        session.commit()
    else:
        session.flush()
    return get_journal(session, tenant_id, journal.id)


def get_journal(session: Session, tenant_id: uuid.UUID, journal_id: uuid.UUID) -> JournalTransaction:
    query: Select[tuple[JournalTransaction]] = (
        select(JournalTransaction)
        .options(selectinload(JournalTransaction.entries))
        .where(JournalTransaction.id == journal_id)
    )
    journal = session.scalar(query)
    if journal is None:
        raise NotFoundError("journal")
    if journal.tenant_id != tenant_id:
        raise TenantBoundaryError()
    return journal


def reverse_journal(
    session: Session, tenant_id: uuid.UUID, journal_id: uuid.UUID, reference: str, reason: str
) -> JournalTransaction:
    original = get_journal(session, tenant_id, journal_id)
    if original.status != "posted":
        raise ProofError("journal_not_posted", "only posted journals can be reversed")
    existing = session.scalar(
        select(JournalTransaction).where(JournalTransaction.reverses_id == original.id)
    )
    if existing is not None:
        raise ProofError("already_reversed", "journal already has a reversal", 409)
    command = JournalCreate(
        reference=reference,
        description=reason,
        entries=[
            {"account_id": entry.account_id, "amount_minor": -entry.amount_minor}
            for entry in original.entries
        ],
    )
    return post_journal(session, tenant_id, command, reverses_id=original.id)


def account_balance(session: Session, tenant_id: uuid.UUID, account_id: uuid.UUID) -> tuple[Account, int]:
    account = require_account(session, tenant_id, account_id)
    balance = session.scalar(
        select(func.coalesce(func.sum(JournalEntry.amount_minor), 0))
        .join(JournalTransaction, JournalTransaction.id == JournalEntry.journal_id)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.account_id == account_id,
            JournalTransaction.status == "posted",
        )
    )
    return account, int(balance or 0)
