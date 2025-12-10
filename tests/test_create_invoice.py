from datetime import date
import json
from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from app import models
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _create_user_and_vendor() -> tuple[uuid.UUID, uuid.UUID]:
    with SessionLocal() as session:
        user = models.User(
            email=f"{uuid.uuid4()}@example.com",
            business_name="Test Biz",
        )
        session.add(user)
        session.flush()

        vendor = models.Vendor(
            user_id=user.id,
            name_normalized="acme corp",
            display_name="ACME Corp",
        )
        session.add(vendor)
        session.commit()

        return user.id, vendor.id


def _cleanup_records(user_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        user = session.get(models.User, user_id)
        if user is not None:
            session.delete(user)
            session.commit()


def test_create_invoice_success() -> None:
    today = date.today()
    user_id, vendor_id = _create_user_and_vendor()

    payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": today.isoformat(),
        "total_amount": "123.45",
        "currency": "usd",
        "source_file_url": "s3://bucket/invoice.pdf",
    }

    response = client.post("/api/invoices/", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["user_id"] == str(user_id)
    assert data["vendor_id"] == str(vendor_id)
    assert data["invoice_date"] == today.isoformat()
    assert data["currency"] == "USD"
    assert data["total_amount"] == "123.45"

    _cleanup_records(user_id)


def test_create_invoice_with_file() -> None:
    user_id, vendor_id = _create_user_and_vendor()

    metadata = {
        "user_id": str(user_id),
        "currency": "eur",
    }

    extracted_payload = {
        "vendor_name": "ACME Corp",
        "invoice_date": date.today().isoformat(),
        "total_amount": "99.99",
    }

    files = {
        "file": ("invoice.json", json.dumps(extracted_payload).encode(), "application/json"),
    }
    response = client.post(
        "/api/invoices/",
        data={"metadata": json.dumps(metadata)},
        files=files,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["vendor_id"] == str(vendor_id)
    assert data["invoice_date"] == extracted_payload["invoice_date"]
    assert data["total_amount"] == extracted_payload["total_amount"]
    file_path = Path(data["source_file_url"])
    assert file_path.exists()
    assert json.loads(file_path.read_text()) == extracted_payload

    file_path.unlink()
    _cleanup_records(user_id)
