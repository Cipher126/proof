from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderWebhook(BaseModel):
    event_type: Literal["transfer.status_changed"] = "transfer.status_changed"
    provider_transfer_id: str = Field(min_length=1, max_length=160)
    client_reference: str = Field(min_length=1, max_length=160)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["submitted", "succeeded", "failed"]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ProviderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    provider: str
    event_id: str
    event_type: str
    provider_transfer_id: str
    client_reference: str
    amount_minor: int
    currency: str
    provider_status: str
    classification: str
    transfer_id: uuid.UUID | None
    provider_timestamp: datetime
    received_at: datetime


class ProviderEventResponse(BaseModel):
    event: ProviderEventRead
    duplicate: bool


class DemoProviderEventCreate(BaseModel):
    client_reference: str = Field(min_length=1, max_length=160)
    scenario: Literal["matched", "duplicate", "out_of_order", "amount_mismatch"]
