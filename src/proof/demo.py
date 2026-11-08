from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from proof.db import get_session
from proof.ledger import service as ledger_service
from proof.ledger.schemas import JournalCreate
from proof.payments import service as payment_service
from proof.payments.schemas import TransferCreate, TransferRead
from proof.providers import service as provider_service
from proof.providers.schemas import ProviderEventRead
from proof.reconciliation import service as reconciliation_service
from proof.reconciliation.schemas import (
    FindingRead,
    StatementImportCreate,
    StatementImportRead,
    StatementLineCreate,
)

router = APIRouter(prefix="/v1/demo", tags=["guided demo"])


class DemoAccounts(BaseModel):
    system: str
    merchant: str
    customer: str
    provider_fee: str


class CanonicalScenarioRead(BaseModel):
    tenant_id: str
    tenant_name: str
    fictional: bool = True
    accounts: DemoAccounts
    transfer: TransferRead
    provider_event: ProviderEventRead
    statement: StatementImportRead
    reconciliation_run_id: str
    findings: list[FindingRead]


@router.post("/scenarios/canonical", response_model=CanonicalScenarioRead)
def run_canonical_scenario(session: Session = Depends(get_session)) -> CanonicalScenarioRead:
    now = datetime.now(timezone.utc)
    tenant = ledger_service.create_tenant(
        session, f"Northstar Fictional Commerce {now.strftime('%H%M%S')}"
    )
    system = ledger_service.create_account(session, tenant.id, "System clearing", "NGN", True)
    merchant = ledger_service.create_account(session, tenant.id, "Merchant available", "NGN")
    customer = ledger_service.create_account(session, tenant.id, "Customer payable", "NGN")
    provider_fee = ledger_service.create_account(session, tenant.id, "Provider fee expense", "NGN")
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
    transfer, _ = payment_service.create_transfer(
        session,
        tenant.id,
        f"demo-{tenant.id}",
        TransferCreate(
            client_reference=f"northstar-order-{now.strftime('%H%M%S')}",
            source_account_id=merchant.id,
            destination_account_id=customer.id,
            amount_minor=2_500_000,
            description="Fictional NGN 25,000 merchant settlement",
        ),
    )
    provider_event, _ = provider_service.build_demo_event(
        session, tenant.id, transfer.client_reference, "amount_mismatch", now
    )
    statement_command = StatementImportCreate(
        provider="proof-simulated-payments",
        filename=f"fictional-settlement-{transfer.id}.json",
        period_start=now - timedelta(hours=1),
        period_end=now + timedelta(hours=1),
        lines=[
            StatementLineCreate(
                provider_reference=provider_event.provider_transfer_id,
                client_reference=transfer.client_reference,
                amount_minor=2_475_000,
                currency="NGN",
                status="succeeded",
                occurred_at=now,
            )
        ],
    )
    statement, _ = reconciliation_service.import_statement(session, tenant.id, statement_command)
    run, findings = reconciliation_service.reconcile_statement(session, tenant.id, statement.id)
    return CanonicalScenarioRead(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        accounts=DemoAccounts(
            system=str(system.id),
            merchant=str(merchant.id),
            customer=str(customer.id),
            provider_fee=str(provider_fee.id),
        ),
        transfer=TransferRead.model_validate(transfer),
        provider_event=ProviderEventRead.model_validate(provider_event),
        statement=StatementImportRead.model_validate(statement),
        reconciliation_run_id=str(run.id),
        findings=[FindingRead.model_validate(finding) for finding in findings],
    )
