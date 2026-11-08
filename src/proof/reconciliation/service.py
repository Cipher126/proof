from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from proof.errors import NotFoundError, ProofError, TenantBoundaryError
from proof.ledger import service as ledger_service
from proof.ledger.schemas import JournalCreate
from proof.operations.models import AuditEvent
from proof.payments.models import Transfer
from proof.reconciliation.models import (
    ReconciliationFinding,
    ReconciliationRun,
    StatementImport,
    StatementLine,
)
from proof.reconciliation.schemas import FindingResolutionCreate, StatementImportCreate


def import_statement(
    session: Session, tenant_id: uuid.UUID, command: StatementImportCreate
) -> tuple[StatementImport, bool]:
    ledger_service.require_tenant(session, tenant_id)
    evidence = command.model_dump(mode="json")
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(StatementImport).where(
            StatementImport.tenant_id == tenant_id,
            StatementImport.provider == command.provider,
            StatementImport.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing, True
    statement = StatementImport(
        tenant_id=tenant_id,
        provider=command.provider,
        filename=command.filename,
        content_hash=content_hash,
        period_start=command.period_start,
        period_end=command.period_end,
        row_count=len(command.lines),
        raw_evidence=evidence,
    )
    session.add(statement)
    session.flush()
    for index, line in enumerate(command.lines, start=1):
        session.add(
            StatementLine(
                tenant_id=tenant_id,
                statement_import_id=statement.id,
                line_number=index,
                provider_reference=line.provider_reference,
                client_reference=line.client_reference,
                amount_minor=line.amount_minor,
                currency=line.currency.upper(),
                provider_status=line.status,
                occurred_at=line.occurred_at,
                raw_data=line.model_dump(mode="json"),
            )
        )
    session.commit()
    session.refresh(statement)
    return statement, False


def _statement(session: Session, tenant_id: uuid.UUID, statement_id: uuid.UUID) -> StatementImport:
    statement = session.get(StatementImport, statement_id)
    if statement is None:
        raise NotFoundError("statement")
    if statement.tenant_id != tenant_id:
        raise TenantBoundaryError()
    return statement


def reconcile_statement(
    session: Session, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> tuple[ReconciliationRun, list[ReconciliationFinding]]:
    statement = _statement(session, tenant_id, statement_id)
    existing = session.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.statement_import_id == statement.id
        )
    )
    if existing is not None:
        return existing, list_findings(session, tenant_id, existing.id)
    run = ReconciliationRun(
        tenant_id=tenant_id, statement_import_id=statement.id, status="running"
    )
    session.add(run)
    session.flush()
    lines = session.scalars(
        select(StatementLine)
        .where(StatementLine.statement_import_id == statement.id)
        .order_by(StatementLine.line_number)
    ).all()
    counts = Counter(line.client_reference for line in lines)
    seen: set[str] = set()
    referenced: set[str] = set()
    findings: list[ReconciliationFinding] = []
    for line in lines:
        referenced.add(line.client_reference)
        if counts[line.client_reference] > 1 and line.client_reference in seen:
            findings.append(
                ReconciliationFinding(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    statement_line_id=line.id,
                    kind="duplicate_provider",
                    status="open",
                    explanation="Provider statement repeats a client reference.",
                    expected={"occurrences": 1},
                    actual={"occurrences": counts[line.client_reference]},
                )
            )
            continue
        seen.add(line.client_reference)
        transfer = session.scalar(
            select(Transfer).where(
                Transfer.tenant_id == tenant_id,
                Transfer.client_reference == line.client_reference,
            )
        )
        if transfer is None:
            findings.append(
                ReconciliationFinding(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    statement_line_id=line.id,
                    kind="missing_internal",
                    status="open",
                    explanation="Provider evidence has no matching internal transfer.",
                    expected=None,
                    actual={"provider_reference": line.provider_reference},
                )
            )
            continue
        kind = None
        explanation = ""
        expected: dict | None = None
        actual: dict | None = None
        if transfer.amount_minor != line.amount_minor:
            kind = "amount_mismatch"
            explanation = "Provider and internal transfer amounts differ."
            expected = {"amount_minor": transfer.amount_minor}
            actual = {"amount_minor": line.amount_minor}
        elif transfer.currency != line.currency:
            kind = "currency_mismatch"
            explanation = "Provider and internal transfer currencies differ."
            expected = {"currency": transfer.currency}
            actual = {"currency": line.currency}
        elif transfer.status != line.provider_status:
            kind = "unexpected_state"
            explanation = "Provider and internal transfer states differ."
            expected = {"status": transfer.status}
            actual = {"status": line.provider_status}
        if kind:
            findings.append(
                ReconciliationFinding(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    statement_line_id=line.id,
                    transfer_id=transfer.id,
                    kind=kind,
                    status="open",
                    explanation=explanation,
                    expected=expected,
                    actual=actual,
                )
            )
    internal = session.scalars(
        select(Transfer).where(
            Transfer.tenant_id == tenant_id,
            Transfer.created_at >= statement.period_start,
            Transfer.created_at <= statement.period_end,
        )
    ).all()
    for transfer in internal:
        if transfer.client_reference not in referenced:
            findings.append(
                ReconciliationFinding(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    transfer_id=transfer.id,
                    kind="missing_provider",
                    status="open",
                    explanation="Internal transfer is absent from the provider statement.",
                    expected={"client_reference": transfer.client_reference},
                    actual=None,
                )
            )
    session.add_all(findings)
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    session.commit()
    return run, list_findings(session, tenant_id, run.id)


def list_findings(
    session: Session, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> list[ReconciliationFinding]:
    run = session.get(ReconciliationRun, run_id)
    if run is None:
        raise NotFoundError("reconciliation run")
    if run.tenant_id != tenant_id:
        raise TenantBoundaryError()
    return session.scalars(
        select(ReconciliationFinding)
        .where(ReconciliationFinding.run_id == run_id)
        .order_by(ReconciliationFinding.created_at, ReconciliationFinding.id)
    ).all()


def resolve_finding(
    session: Session,
    tenant_id: uuid.UUID,
    finding_id: uuid.UUID,
    actor: str,
    command: FindingResolutionCreate,
) -> ReconciliationFinding:
    finding = session.scalar(
        select(ReconciliationFinding)
        .where(ReconciliationFinding.id == finding_id, ReconciliationFinding.tenant_id == tenant_id)
        .with_for_update()
    )
    if finding is None:
        raise NotFoundError("reconciliation finding")
    if finding.status == "resolved":
        return finding
    adjustment_id = None
    if command.resolution == "adjusted":
        journal = ledger_service.post_journal(
            session,
            tenant_id,
            JournalCreate(
                reference=f"reconciliation/{finding.id}",
                description=command.adjustment_description or command.reason,
                entries=command.adjustment_entries,
            ),
            commit=False,
        )
        adjustment_id = journal.id
    now = datetime.now(timezone.utc)
    finding.status = "resolved"
    finding.resolved_at = now
    finding.resolved_by = actor
    finding.resolution = command.resolution
    finding.resolution_reason = command.reason
    finding.adjustment_journal_id = adjustment_id
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor=actor,
            action="reconciliation.finding_resolved",
            resource_type="reconciliation_finding",
            resource_id=finding.id,
            reason=command.reason,
            details={
                "resolution": command.resolution,
                "adjustment_journal_id": str(adjustment_id) if adjustment_id else None,
            },
        )
    )
    session.commit()
    session.refresh(finding)
    return finding
