from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VendorCreate(BaseModel):
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=200)


class VendorRead(BaseModel):
    id: UUID
    user_id: UUID
    name_normalized: str
    display_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
