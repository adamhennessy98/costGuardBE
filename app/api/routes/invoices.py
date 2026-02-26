from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import get_db, get_invoice_extractor, get_invoice_storage
from app.schemas.anomaly import AnomalyRead, AnomalyUpdate
from app.schemas.invoice import InvoiceCreate, InvoiceRead, InvoiceTimeline, InvoiceWithAnomalies
from app.services.anomaly_detector import detect_anomalies
from app.services.file_storage import InvoiceFileStorage
from app.models.enums import AnomalySeverity, AnomalyStatus, AnomalyType
from app.services.invoice_extractor import InvoiceExtractionResult, InvoiceMetadataExtractor
from app.services.vendor_normalizer import normalize_vendor_name

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/{invoice_id:uuid}", response_model=InvoiceTimeline)
def get_invoice_detail(
    invoice_id: UUID,
    user_id: UUID,
    history_limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> InvoiceTimeline:
    """Return invoice, its anomalies, and recent history for the vendor."""

    invoice_stmt = (
        select(models.Invoice)
        .options(selectinload(models.Invoice.anomalies))
        .where(models.Invoice.id == invoice_id)
        .where(models.Invoice.user_id == user_id)
    )
    invoice = db.scalar(invoice_stmt)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found for user")

    history_stmt = (
        select(models.Invoice)
        .where(models.Invoice.vendor_id == invoice.vendor_id)
        .where(models.Invoice.user_id == user_id)
        .where(models.Invoice.id != invoice.id)
        .order_by(models.Invoice.invoice_date.desc(), models.Invoice.created_at.desc())
        .limit(history_limit)
    )
    history = db.scalars(history_stmt).all()

    return InvoiceTimeline(invoice=invoice, anomalies=invoice.anomalies, vendor_history=history)


@router.patch("/anomalies/{anomaly_id:uuid}", response_model=AnomalyRead)
def update_anomaly_status(
    anomaly_id: UUID,
    payload: AnomalyUpdate,
    user_id: UUID,
    db: Session = Depends(get_db),
) -> AnomalyRead:
    """Update the review status (and optional note) for a specific anomaly."""

    stmt = (
        select(models.Anomaly)
        .join(models.Invoice)
        .where(models.Anomaly.id == anomaly_id)
        .where(models.Invoice.user_id == user_id)
    )
    anomaly = db.scalar(stmt)
    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found for user")

    updates = payload.model_dump(exclude_unset=True)
    anomaly.status = updates["status"]
    if "note" in updates:
        anomaly.note = updates["note"]

    db.commit()
    db.refresh(anomaly)
    return anomaly


@router.get("/flagged", response_model=list[InvoiceWithAnomalies])
def list_flagged_invoices(
    user_id: UUID,
    status: AnomalyStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[InvoiceWithAnomalies]:
    """Return recent invoices that currently have anomalies for the given user."""

    stmt = (
        select(models.Invoice)
        .join(models.Anomaly)
        .where(models.Invoice.user_id == user_id)
    )
    applied_status = status or AnomalyStatus.UNREVIEWED
    stmt = stmt.where(models.Anomaly.status == applied_status)

    stmt = (
        stmt.options(selectinload(models.Invoice.anomalies))
        .order_by(models.Invoice.invoice_date.desc(), models.Invoice.created_at.desc())
        .limit(limit)
    )

    invoices = db.scalars(stmt).unique().all()

    severity_order = {
        AnomalySeverity.HIGH: 0,
        AnomalySeverity.MEDIUM: 1,
        AnomalySeverity.LOW: 2,
    }

    for invoice in invoices:
        invoice.anomalies.sort(
            key=lambda record: (
                severity_order.get(record.severity, 99),
                record.created_at or record.updated_at,
            )
        )

    return invoices


@router.post("/", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request: Request,
    db: Session = Depends(get_db),
    storage: InvoiceFileStorage = Depends(get_invoice_storage),
    extractor: InvoiceMetadataExtractor = Depends(get_invoice_extractor),
) -> InvoiceRead:
    """Persist a new invoice with associated metadata and optional file upload."""

    payload: InvoiceCreate | None = None
    uploaded_file: UploadFile | None = None

    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except Exception as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc
        try:
            payload = InvoiceCreate.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc
    elif content_type.startswith("multipart/form-data"):
        form = await request.form()
        metadata = form.get("metadata")
        if metadata is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice metadata is required")
        try:
            payload = InvoiceCreate.model_validate_json(metadata)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc
        file_candidate = form.get("file")
        if file_candidate is not None and hasattr(file_candidate, "filename"):
            uploaded_file = file_candidate
    else:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported content type")

    if payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice metadata is required")

    extraction: InvoiceExtractionResult = InvoiceExtractionResult()
    if uploaded_file is not None:
        stored_path = await storage.save(uploaded_file)
        payload = payload.model_copy(update={"source_file_url": stored_path})
        extraction = extractor.extract(Path(stored_path))

    vendor: models.Vendor | None = None
    vendor_identifier = payload.vendor_id
    vendor_name_candidate = payload.vendor_name or extraction.vendor_name

    if vendor_identifier is not None:
        vendor = db.get(models.Vendor, vendor_identifier)
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    elif vendor_name_candidate:
        normalized_name = normalize_vendor_name(vendor_name_candidate)
        stmt = (
            select(models.Vendor)
            .where(models.Vendor.user_id == payload.user_id)
            .where(models.Vendor.name_normalized == normalized_name)
        )
        vendor = db.scalar(stmt)
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found for extracted name")
        vendor_identifier = vendor.id
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor information is required")

    user = db.get(models.User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if vendor is None:
        vendor = db.get(models.Vendor, vendor_identifier)
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    if vendor.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor does not belong to user")

    invoice_date_value = payload.invoice_date or extraction.invoice_date
    if isinstance(invoice_date_value, str):
        try:
            invoice_date_value = date.fromisoformat(invoice_date_value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice date") from exc
    if invoice_date_value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice date is required")

    total_amount_value = payload.total_amount or extraction.total_amount
    if isinstance(total_amount_value, (int, float, str)):
        try:
            total_amount_value = Decimal(str(total_amount_value))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid total amount") from exc
    if total_amount_value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice total amount is required")

    invoice = models.Invoice(
        user_id=payload.user_id,
        vendor_id=vendor_identifier,
        invoice_date=invoice_date_value,
        total_amount=total_amount_value,
        currency=payload.currency,
        source_file_url=payload.source_file_url,
    )
    db.add(invoice)
    db.flush()

    anomalies = detect_anomalies(db, invoice, vendor_identifier, total_amount_value)
    for anomaly in anomalies:
        db.add(anomaly)

    db.commit()
    db.refresh(invoice)
    return invoice
