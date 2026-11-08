from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.errors import NotFoundError, ProofError
from proof.identity import DemoCredential, TenantAccess, active_tenant, issue_demo_credential
from proof.ledger import service as ledger_service
from proof.ledger.models import Account
from proof.ledger.schemas import EntryCreate, JournalCreate
from proof.payments import service as payment_service
from proof.payments.schemas import TransferCreate, TransferRead
from proof.providers import service as provider_service
from proof.providers.schemas import ProviderEventRead
from proof.reconciliation import service as reconciliation_service
from proof.reconciliation.models import ReconciliationFinding
from proof.reconciliation.schemas import (
    FindingRead,
    FindingResolutionCreate,
    StatementImportCreate,
    StatementImportRead,
    StatementLineCreate,
)

router = APIRouter(prefix="/v1/demo", tags=["guided demo"])
tenant_router = APIRouter(prefix="/v1/tenants", tags=["guided demo"])
CUSTOMER_ACCOUNT = "Customer payable"
FEE_ACCOUNT = "Provider fee expense"
MAX_SCENARIOS_PER_HOUR = 60
MAX_RETAINED_SCENARIOS = 2_000
DEMO_ADMISSION_LOCK = 1_347_570_511


class DemoAccounts(BaseModel):
    system: str
    merchant: str
    customer: str
    provider_fee: str


class CanonicalScenarioRead(BaseModel):
    tenant_id: str
    access_token: str
    tenant_name: str
    fictional: bool = True
    accounts: DemoAccounts
    transfer: TransferRead
    provider_event: ProviderEventRead
    transfer_replayed: bool
    provider_duplicate: bool
    statement: StatementImportRead
    reconciliation_run_id: str
    findings: list[FindingRead]


@router.post("/scenarios/canonical", response_model=CanonicalScenarioRead)
def run_canonical_scenario(
    response: Response, session: Session = Depends(get_session)
) -> CanonicalScenarioRead:
    with session.begin():
        connection = session.connection()
        if connection.dialect.name == "postgresql":
            acquired = session.scalar(select(func.pg_try_advisory_xact_lock(DEMO_ADMISSION_LOCK)))
            if not acquired:
                raise ProofError("demo_busy", "A scenario is starting. Try again in a moment.", 429)
        total, recent = session.execute(select(
            func.count(),
            func.count().filter(DemoCredential.expires_at > func.now()),
        ).select_from(DemoCredential)).one()
        if total >= MAX_RETAINED_SCENARIOS:
            raise ProofError("demo_storage_limit", "The demo database reached its scenario limit.", 429)
        if recent >= MAX_SCENARIOS_PER_HOUR:
            raise ProofError("demo_hourly_limit", "The hourly demo limit was reached. Try again later.", 429)
        # Existing services commit their units of work. The enclosing transaction
        # owns the actual commit so a failed step cannot leave a partial scenario.
        with Session(bind=connection, join_transaction_mode="rollback_only", expire_on_commit=False) as unit:
            scenario = _create_scenario(unit)
    response.headers["Cache-Control"] = "no-store"
    return scenario


def _create_scenario(session: Session) -> CanonicalScenarioRead:
    now = datetime.now(timezone.utc)
    tenant = ledger_service.create_tenant(
        session, f"Northstar Fictional Commerce {now.strftime('%H%M%S')}"
    )
    system = ledger_service.create_account(session, tenant.id, "System clearing", "NGN", True)
    merchant = ledger_service.create_account(session, tenant.id, "Merchant available", "NGN")
    customer = ledger_service.create_account(session, tenant.id, CUSTOMER_ACCOUNT, "NGN")
    provider_fee = ledger_service.create_account(session, tenant.id, FEE_ACCOUNT, "NGN")
    ledger_service.post_journal(
        session,
        tenant.id,
        JournalCreate(
            reference=f"demo/{tenant.id}/funding",
            description="Fictional opening funds for the guided incident",
            entries=[
                {"account_id": system.id, "amount_minor": -2_500_000},
                {"account_id": merchant.id, "amount_minor": 2_500_000},
            ],
        ),
    )
    command = TransferCreate(
        client_reference=f"northstar-order-{now.strftime('%H%M%S')}",
        source_account_id=merchant.id,
        destination_account_id=customer.id,
        amount_minor=2_500_000,
        description="Fictional NGN 25,000 merchant settlement",
    )
    key = f"demo-{tenant.id}"
    transfer, _ = payment_service.create_transfer(session, tenant.id, key, command)
    _, transfer_replayed = payment_service.create_transfer(session, tenant.id, key, command)
    provider_event, _ = provider_service.build_demo_event(
        session, tenant.id, transfer.client_reference, "amount_mismatch"
    )
    _, provider_duplicate = provider_service.build_demo_event(
        session, tenant.id, transfer.client_reference, "amount_mismatch"
    )
    provider_service.build_demo_event(session, tenant.id, transfer.client_reference, "out_of_order")
    statement_command = StatementImportCreate(
        provider="proof-simulated-payments",
        filename=f"fictional-settlement-{transfer.id}.json",
        period_start=now - timedelta(hours=1),
        period_end=now + timedelta(hours=1),
        lines=[
            StatementLineCreate(
                provider_reference=provider_event.provider_transfer_id,
                client_reference=transfer.client_reference,
                amount_minor=provider_event.amount_minor,
                currency="NGN",
                status="succeeded",
                occurred_at=provider_event.received_at,
            )
        ],
    )
    statement, _ = reconciliation_service.import_statement(session, tenant.id, statement_command)
    run, findings = reconciliation_service.reconcile_statement(session, tenant.id, statement.id)
    token = issue_demo_credential(session, tenant.id)
    return CanonicalScenarioRead(
        tenant_id=str(tenant.id),
        access_token=token,
        tenant_name=tenant.name,
        accounts=DemoAccounts(
            system=str(system.id),
            merchant=str(merchant.id),
            customer=str(customer.id),
            provider_fee=str(provider_fee.id),
        ),
        transfer=TransferRead.model_validate(transfer),
        provider_event=ProviderEventRead.model_validate(provider_event),
        transfer_replayed=transfer_replayed,
        provider_duplicate=provider_duplicate,
        statement=StatementImportRead.model_validate(statement),
        reconciliation_run_id=str(run.id),
        findings=[FindingRead.model_validate(finding) for finding in findings],
    )


@tenant_router.post("/{tenant_id}/demo/findings/{finding_id}/adjust", response_model=FindingRead)
def adjust_demo_finding(
    finding_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    access: Annotated[TenantAccess, Depends(active_tenant)],
) -> FindingRead:
    actor = access.audit_actor
    if actor is None:
        raise ProofError("invalid_demo_credential", "a valid demo bearer credential is required", 401)
    finding = session.scalar(
        select(ReconciliationFinding).where(
            ReconciliationFinding.id == finding_id,
            ReconciliationFinding.tenant_id == access.tenant_id,
        )
    )
    if finding is None:
        raise NotFoundError("reconciliation finding")
    if finding.kind != "amount_mismatch" or finding.transfer_id is None:
        raise ProofError("unsupported_demo_finding", "this finding has no guided fee adjustment", 409)

    transfer = payment_service.get_transfer(session, access.tenant_id, finding.transfer_id)
    reported_amount = (finding.actual or {}).get("amount_minor")
    if not isinstance(reported_amount, int) or not 0 < reported_amount < transfer.amount_minor:
        raise ProofError("invalid_demo_difference", "the evidence does not describe a withheld fee", 409)
    fee_account = session.scalar(select(Account).where(
        Account.tenant_id == access.tenant_id,
        Account.name == FEE_ACCOUNT,
        Account.currency == transfer.currency,
    ))
    if fee_account is None:
        raise NotFoundError("demo fee account")
    difference = transfer.amount_minor - reported_amount
    result = reconciliation_service.resolve_finding(
        session, access.tenant_id, finding.id, actor,
        FindingResolutionCreate(
            resolution="adjusted",
            reason="Recognize the fictional provider settlement fee.",
            adjustment_description="Provider fee reconciliation adjustment",
            adjustment_entries=[
                EntryCreate(account_id=transfer.destination_account_id, amount_minor=-difference),
                EntryCreate(account_id=fee_account.id, amount_minor=difference),
            ],
        ),
    )
    return FindingRead.model_validate(result)
