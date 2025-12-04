from datetime import datetime, date
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Invoice(Base):
    """Invoice records ingested for anomaly detection."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index("invoices_vendor_date_idx", "vendor_id", "invoice_date"),
        Index("invoices_duplicate_check_idx", "vendor_id", "invoice_date", "total_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_file_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="invoices")
    vendor = relationship("Vendor", back_populates="invoices")
    anomalies = relationship("Anomaly", back_populates="invoice", cascade="all, delete-orphan")
