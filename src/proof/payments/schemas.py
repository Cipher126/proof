from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransferCreate(BaseModel):
    client_reference: str = Field(min_length=1, max_length=160)
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount_minor: int = Field(gt=0)
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
    journal_id: uuid.UUID
    created_at: datetime
    completed_at: datetime
