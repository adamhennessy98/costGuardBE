from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import AnomalySeverity, AnomalyStatus, AnomalyType


class AnomalyRead(BaseModel):
    id: UUID
    invoice_id: UUID
    type: AnomalyType
    severity: AnomalySeverity
    status: AnomalyStatus
    reason_text: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnomalyUpdate(BaseModel):
    status: AnomalyStatus
    note: str | None = None
