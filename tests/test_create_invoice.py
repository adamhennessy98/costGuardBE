from datetime import date
import json
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.db.session import SessionLocal
from app.main import app
from app.models.enums import AnomalyStatus
from app.services.vendor_normalizer import normalize_vendor_name

client = TestClient(app)


def _create_user_and_vendor(display_name: str = "ACME Corp") -> tuple[uuid.UUID, uuid.UUID]:
    with SessionLocal() as session:
        user = models.User(
            email=f"{uuid.uuid4()}@example.com",
            business_name="Test Biz",
        )
        session.add(user)
        session.flush()

        vendor = models.Vendor(
            user_id=user.id,
            name_normalized=normalize_vendor_name(display_name),
            display_name=display_name,
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


def test_create_invoice_with_vendor_alias() -> None:
    user_id, vendor_id = _create_user_and_vendor("Amazon Web Services")

    payload = {
        "user_id": str(user_id),
        "vendor_name": "AWS",
        "invoice_date": date.today().isoformat(),
        "total_amount": "200.00",
        "currency": "usd",
    }

    response = client.post("/api/invoices/", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["vendor_id"] == str(vendor_id)
    assert data["total_amount"] == "200.00"

    _cleanup_records(user_id)


def test_duplicate_invoice_creates_anomaly() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    base_payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "150.00",
        "currency": "usd",
    }

    first_response = client.post("/api/invoices/", json=base_payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/invoices/", json=base_payload)
    assert second_response.status_code == 201

    duplicate_invoice_id = uuid.UUID(second_response.json()["id"])

    with SessionLocal() as session:
        anomalies = session.scalars(
            select(models.Anomaly).where(models.Anomaly.invoice_id == duplicate_invoice_id)
        ).all()

    assert anomalies, "Expected a duplicate anomaly to be recorded"
    assert anomalies[0].type.value == "DUPLICATE"

    _cleanup_records(user_id)


def test_high_amount_invoice_creates_anomaly() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    base_payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "currency": "usd",
    }

    for amount in ["100.00", "105.00", "95.00", "110.00"]:
        payload = base_payload | {"total_amount": amount}
        response = client.post("/api/invoices/", json=payload)
        assert response.status_code == 201

    spike_payload = base_payload | {"total_amount": "300.00"}
    spike_response = client.post("/api/invoices/", json=spike_payload)
    assert spike_response.status_code == 201

    spike_invoice_id = uuid.UUID(spike_response.json()["id"])

    with SessionLocal() as session:
        anomalies = session.scalars(
            select(models.Anomaly).where(models.Anomaly.invoice_id == spike_invoice_id)
        ).all()

    assert anomalies, "Expected a high-amount anomaly to be recorded"
    assert anomalies[0].type.value == "ABNORMAL_TOTAL"

    _cleanup_records(user_id)


def test_low_outlier_invoice_creates_anomaly() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    base_payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "currency": "usd",
    }

    baseline_amounts = [
        "100.00",
        "101.25",
        "98.75",
        "102.40",
        "99.90",
        "100.60",
        "101.10",
    ]
    for amount in baseline_amounts:
        payload = base_payload | {"total_amount": amount}
        response = client.post("/api/invoices/", json=payload)
        assert response.status_code == 201

    outlier_payload = base_payload | {"total_amount": "40.00"}
    outlier_response = client.post("/api/invoices/", json=outlier_payload)
    assert outlier_response.status_code == 201

    outlier_invoice_id = uuid.UUID(outlier_response.json()["id"])

    with SessionLocal() as session:
        anomalies = session.scalars(
            select(models.Anomaly).where(models.Anomaly.invoice_id == outlier_invoice_id)
        ).all()

    assert anomalies, "Expected an outlier anomaly to be recorded"
    assert anomalies[0].type.value == "ABNORMAL_TOTAL"
    assert "lower" in anomalies[0].reason_text.lower()

    _cleanup_records(user_id)


def test_flagged_invoices_endpoint_returns_unreviewed_by_default() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "200.00",
        "currency": "usd",
    }

    first_response = client.post("/api/invoices/", json=payload)
    assert first_response.status_code == 201

    duplicate_response = client.post("/api/invoices/", json=payload)
    assert duplicate_response.status_code == 201

    flagged_response = client.get(
        "/api/invoices/flagged",
        params={"user_id": str(user_id)},
    )

    assert flagged_response.status_code == 200
    data = flagged_response.json()
    assert len(data) == 1
    flagged_invoice = data[0]
    assert flagged_invoice["id"] == duplicate_response.json()["id"]
    assert flagged_invoice["anomalies"], "Expected anomalies to be included"
    assert flagged_invoice["anomalies"][0]["type"] == "DUPLICATE"

    _cleanup_records(user_id)


def test_flagged_invoices_endpoint_respects_status_filter() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "200.00",
        "currency": "usd",
    }

    client.post("/api/invoices/", json=payload)
    second_response = client.post("/api/invoices/", json=payload)
    assert second_response.status_code == 201

    duplicate_invoice_id = uuid.UUID(second_response.json()["id"])

    with SessionLocal() as session:
        anomaly = session.scalar(
            select(models.Anomaly).where(models.Anomaly.invoice_id == duplicate_invoice_id)
        )
        assert anomaly is not None
        anomaly.status = AnomalyStatus.VALID
        session.commit()

    default_response = client.get(
        "/api/invoices/flagged",
        params={"user_id": str(user_id)},
    )

    assert default_response.status_code == 200
    assert default_response.json() == []

    valid_response = client.get(
        "/api/invoices/flagged",
        params={"user_id": str(user_id), "status": AnomalyStatus.VALID.value},
    )

    assert valid_response.status_code == 200
    data = valid_response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(duplicate_invoice_id)
    assert data[0]["anomalies"][0]["status"] == AnomalyStatus.VALID.value

    _cleanup_records(user_id)


def test_invoice_detail_endpoint_includes_history_and_anomalies() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    base_payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "100.00",
        "currency": "usd",
    }

    invoice_ids: list[uuid.UUID] = []
    for amount in ["100.00", "105.00", "102.50", "110.00", "250.00"]:
        payload = base_payload | {"total_amount": amount}
        response = client.post("/api/invoices/", json=payload)
        assert response.status_code == 201
        invoice_ids.append(uuid.UUID(response.json()["id"]))

    flagged_invoice_id = invoice_ids[-1]

    detail_response = client.get(
        f"/api/invoices/{flagged_invoice_id}",
        params={"user_id": str(user_id), "history_limit": 3},
    )

    assert detail_response.status_code == 200
    data = detail_response.json()
    assert data["invoice"]["id"] == str(flagged_invoice_id)
    assert data["anomalies"], "Expected anomalies to be returned"
    assert len(data["vendor_history"]) == 3
    assert all(entry["vendor_id"] == str(vendor_id) for entry in data["vendor_history"])

    missing_response = client.get(
        f"/api/invoices/{uuid.uuid4()}",
        params={"user_id": str(user_id)},
    )
    assert missing_response.status_code == 404

    _cleanup_records(user_id)


def test_update_anomaly_status_and_note() -> None:
    user_id, vendor_id = _create_user_and_vendor("ACME Corp")

    payload = {
        "user_id": str(user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "200.00",
        "currency": "usd",
    }

    client.post("/api/invoices/", json=payload)
    second_response = client.post("/api/invoices/", json=payload)
    assert second_response.status_code == 201

    duplicate_invoice_id = uuid.UUID(second_response.json()["id"])

    with SessionLocal() as session:
        anomaly = session.scalar(
            select(models.Anomaly).where(models.Anomaly.invoice_id == duplicate_invoice_id)
        )
        assert anomaly is not None
        anomaly_id = anomaly.id

    first_update = client.patch(
        f"/api/invoices/anomalies/{anomaly_id}",
        params={"user_id": str(user_id)},
        json={"status": AnomalyStatus.VALID.value},
    )
    assert first_update.status_code == 200
    assert first_update.json()["status"] == AnomalyStatus.VALID.value
    assert first_update.json()["note"] is None

    second_update = client.patch(
        f"/api/invoices/anomalies/{anomaly_id}",
        params={"user_id": str(user_id)},
        json={"status": AnomalyStatus.ISSUE.value, "note": "Confirmed overcharge"},
    )
    assert second_update.status_code == 200
    payload = second_update.json()
    assert payload["status"] == AnomalyStatus.ISSUE.value
    assert payload["note"] == "Confirmed overcharge"

    _cleanup_records(user_id)


def test_update_anomaly_status_rejects_wrong_user() -> None:
    owner_user_id, vendor_id = _create_user_and_vendor("ACME Corp")
    other_user_id, _ = _create_user_and_vendor("Other Corp")

    payload = {
        "user_id": str(owner_user_id),
        "vendor_id": str(vendor_id),
        "invoice_date": date.today().isoformat(),
        "total_amount": "200.00",
        "currency": "usd",
    }

    client.post("/api/invoices/", json=payload)
    duplicate_response = client.post("/api/invoices/", json=payload)
    assert duplicate_response.status_code == 201
    duplicate_invoice_id = uuid.UUID(duplicate_response.json()["id"])

    with SessionLocal() as session:
        anomaly = session.scalar(
            select(models.Anomaly).where(models.Anomaly.invoice_id == duplicate_invoice_id)
        )
        assert anomaly is not None
        anomaly_id = anomaly.id

    unauthorized_response = client.patch(
        f"/api/invoices/anomalies/{anomaly_id}",
        params={"user_id": str(other_user_id)},
        json={"status": AnomalyStatus.VALID.value},
    )

    assert unauthorized_response.status_code == 404

    _cleanup_records(owner_user_id)
    _cleanup_records(other_user_id)
