from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime


class AccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("currency must contain three letters")
        return value.upper()


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    currency: str
    created_at: datetime


class EntryCreate(BaseModel):
    account_id: uuid.UUID
    amount_minor: int

    @field_validator("amount_minor")
    @classmethod
    def non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("entry amount cannot be zero")
        return value


class JournalCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    entries: list[EntryCreate] = Field(min_length=2, max_length=100)


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    account_id: uuid.UUID
    position: int
    amount_minor: int
    currency: str


class JournalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    reference: str
    description: str
    status: str
    reverses_id: uuid.UUID | None
    created_at: datetime
    posted_at: datetime | None
    entries: list[EntryRead]


class BalanceRead(BaseModel):
    account_id: uuid.UUID
    currency: str
    balance_minor: int
