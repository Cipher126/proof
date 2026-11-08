from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from proof.ledger.schemas import EntryCreate


class StatementLineCreate(BaseModel):
    provider_reference: str = Field(min_length=1, max_length=160)
    client_reference: str = Field(min_length=1, max_length=160)
    amount_minor: int = Field(strict=True, gt=0, le=2**63 - 1)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["submitted", "succeeded", "failed"]
    occurred_at: AwareDatetime


class StatementImportCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    filename: str = Field(min_length=1, max_length=240)
    period_start: AwareDatetime
    period_end: AwareDatetime
    lines: list[StatementLineCreate] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def valid_period(self) -> "StatementImportCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


class StatementImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    provider: str
    filename: str
    content_hash: str
    period_start: datetime
    period_end: datetime
    row_count: int
    imported_at: datetime


class StatementImportResponse(BaseModel):
    statement: StatementImportRead
    duplicate: bool


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    statement_line_id: uuid.UUID | None
    transfer_id: uuid.UUID | None
    kind: str
    status: str
    explanation: str
    expected: dict | None
    actual: dict | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    resolution: str | None
    resolution_reason: str | None
    adjustment_journal_id: uuid.UUID | None


class ReconciliationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    statement_import_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    findings: list[FindingRead] = Field(default_factory=list)


class FindingResolutionCreate(BaseModel):
    resolution: Literal["acknowledged", "adjusted"]
    reason: str = Field(min_length=3, max_length=1000)
    adjustment_description: str | None = Field(default=None, max_length=500)
    adjustment_entries: list[EntryCreate] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def adjustment_shape(self) -> "FindingResolutionCreate":
        if self.resolution == "adjusted" and len(self.adjustment_entries) < 2:
            raise ValueError("adjusted resolutions require at least two entries")
        if self.resolution == "acknowledged" and self.adjustment_entries:
            raise ValueError("acknowledged resolutions cannot include adjustment entries")
        return self


class SettlementBatchRead(BaseModel):
    statement: StatementImportRead
    status: Literal["imported", "needs_review", "ready_to_close", "closed"]
    run_id: uuid.UUID | None
    open_findings: int
    provider_totals_minor: dict[str, int]
    closed_at: datetime | None


class SettlementClose(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
