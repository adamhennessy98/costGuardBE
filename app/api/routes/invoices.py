from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_db, get_invoice_extractor, get_invoice_storage
from app.schemas.invoice import InvoiceCreate, InvoiceRead
from app.services.file_storage import InvoiceFileStorage
from app.services.invoice_extractor import InvoiceExtractionResult, InvoiceMetadataExtractor

router = APIRouter(prefix="/invoices", tags=["invoices"])


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
        normalized_name = vendor_name_candidate.strip().lower()
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
    db.commit()
    db.refresh(invoice)
    return invoice
