from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_db
from app.schemas.vendor import VendorCreate, VendorRead
from app.services.vendor_normalizer import normalize_vendor_name

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.post("/", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
def create_vendor(
    payload: VendorCreate,
    db: Session = Depends(get_db),
) -> VendorRead:
    """Register a new vendor for a user.

    Normalizes the display name and rejects duplicates for the same user.
    """

    user = db.get(models.User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    normalized = normalize_vendor_name(payload.display_name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor name is invalid")

    existing_stmt = (
        select(models.Vendor)
        .where(models.Vendor.user_id == payload.user_id)
        .where(models.Vendor.name_normalized == normalized)
    )
    if db.scalar(existing_stmt) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vendor with this name already exists for the user",
        )

    vendor = models.Vendor(
        user_id=payload.user_id,
        display_name=payload.display_name.strip(),
        name_normalized=normalized,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


@router.get("/", response_model=list[VendorRead])
def list_vendors(
    user_id: UUID,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[VendorRead]:
    """List vendors for a user, optionally filtered by a search term."""

    stmt = (
        select(models.Vendor)
        .where(models.Vendor.user_id == user_id)
    )

    if search:
        normalized_search = normalize_vendor_name(search)
        stmt = stmt.where(models.Vendor.name_normalized.contains(normalized_search))

    stmt = stmt.order_by(models.Vendor.display_name).limit(limit)

    return db.scalars(stmt).all()


@router.get("/{vendor_id:uuid}", response_model=VendorRead)
def get_vendor(
    vendor_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
) -> VendorRead:
    """Return a single vendor by ID."""

    stmt = (
        select(models.Vendor)
        .where(models.Vendor.id == vendor_id)
        .where(models.Vendor.user_id == user_id)
    )
    vendor = db.scalar(stmt)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found for user")
    return vendor
