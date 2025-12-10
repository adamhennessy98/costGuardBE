from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.file_storage import InvoiceFileStorage
from app.services.invoice_extractor import InvoiceMetadataExtractor


def get_db() -> Generator[Session, None, None]:
    """Provide a scoped database session dependency."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_invoice_storage() -> InvoiceFileStorage:
    """Return a file storage helper for invoice uploads."""

    settings = get_settings()
    base_dir = Path(settings.invoice_storage_dir)
    return InvoiceFileStorage(base_dir)


def get_invoice_extractor() -> InvoiceMetadataExtractor:
    """Return the invoice metadata extractor service."""

    return InvoiceMetadataExtractor()
