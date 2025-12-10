from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceCreate(BaseModel):
    user_id: UUID
    vendor_id: UUID | None = None
    vendor_name: str | None = None
    invoice_date: date | None = None
    total_amount: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(min_length=3, max_length=3)
    source_file_url: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class InvoiceRead(BaseModel):
    id: UUID
    user_id: UUID
    vendor_id: UUID
    invoice_date: date
    total_amount: Decimal
    currency: str
    source_file_url: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
