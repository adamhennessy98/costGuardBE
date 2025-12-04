from datetime import datetime
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.enums import AnomalySeverity, AnomalyStatus, AnomalyType


class Anomaly(Base):
    """Detected anomalies tied to invoices."""

    __tablename__ = "anomalies"
    __table_args__ = (
        Index("anomalies_invoice_id_idx", "invoice_id"),
        Index("anomalies_status_idx", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[AnomalyType] = mapped_column(Enum(AnomalyType, name="anomaly_type", native_enum=False), nullable=False)
    severity: Mapped[AnomalySeverity] = mapped_column(Enum(AnomalySeverity, name="anomaly_severity", native_enum=False), nullable=False)
    status: Mapped[AnomalyStatus] = mapped_column(
        Enum(AnomalyStatus, name="anomaly_status", native_enum=False),
        nullable=False,
        default=AnomalyStatus.UNREVIEWED,
        server_default=AnomalyStatus.UNREVIEWED.value,
    )
    reason_text: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    invoice = relationship("Invoice", back_populates="anomalies")
