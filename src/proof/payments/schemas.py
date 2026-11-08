from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransferCreate(BaseModel):
    client_reference: str = Field(min_length=1, max_length=160)
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount_minor: int = Field(strict=True, gt=0, le=2**63 - 1)
    description: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def distinct_accounts(self) -> "TransferCreate":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source and destination accounts must differ")
        return self


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    client_reference: str
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount_minor: int
    currency: str
    status: str
    journal_id: uuid.UUID | None
    hold_expires_at: datetime | None
    refunded_minor: int
    created_at: datetime
    completed_at: datetime | None


class PaymentAction(BaseModel):
    action: Literal["authorize", "submit", "capture", "fail", "cancel", "expire", "refund"]
    reason: str = Field(min_length=1, max_length=500)
    amount_minor: int | None = Field(default=None, strict=True, gt=0, le=2**63 - 1)
    fee_minor: int = Field(default=0, strict=True, ge=0, le=2**63 - 1)
    fee_account_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> "PaymentAction":
        if (self.action == "refund") != (self.amount_minor is not None):
            raise ValueError("a refund requires an amount, and only refunds accept an amount")
        if bool(self.fee_minor) != (self.fee_account_id is not None):
            raise ValueError("a fee requires a fee account and positive amount")
        if self.fee_minor and self.action != "capture":
            raise ValueError("fees are only accepted on capture")
        return self


class PaymentChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    transfer_id: uuid.UUID
    action: str
    from_status: str
    to_status: str
    amount_minor: int
    fee_minor: int
    journal_id: uuid.UUID | None
    reason: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, timestamp: datetime) -> datetime:
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
