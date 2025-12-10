from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass
class InvoiceExtractionResult:
    vendor_name: str | None = None
    invoice_date: date | None = None
    total_amount: Decimal | None = None


class InvoiceMetadataExtractor:
    """Best-effort invoice metadata extractor (MVP stub)."""

    def extract(self, file_path: Path) -> InvoiceExtractionResult:
        """Extract vendor name, invoice date, and total from a file.

        Currently supports simple JSON payloads or line-based text files.
        Returns empty fields when no data can be derived.
        """

        if not file_path.exists():
            return InvoiceExtractionResult()

        suffix = file_path.suffix.lower()
        if suffix == ".json":
            return self._from_json(file_path)
        if suffix in {".txt", ".log"}:
            return self._from_text(file_path)
        return InvoiceExtractionResult()

    def _from_json(self, file_path: Path) -> InvoiceExtractionResult:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            return InvoiceExtractionResult()

        vendor_name = self._coalesce(data, ["vendor_name", "vendor", "supplier"])  # type: ignore[arg-type]
        invoice_date_value = self._coalesce(data, ["invoice_date", "date"])  # type: ignore[arg-type]
        total_value = self._coalesce(data, ["total_amount", "amount", "total"])  # type: ignore[arg-type]

        invoice_date = self._parse_date(invoice_date_value)
        total_amount = self._parse_decimal(total_value)
        return InvoiceExtractionResult(vendor_name=vendor_name, invoice_date=invoice_date, total_amount=total_amount)

    def _from_text(self, file_path: Path) -> InvoiceExtractionResult:
        vendor_name = None
        invoice_date = None
        total_amount = None

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return InvoiceExtractionResult()

        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("vendor:"):
                vendor_name = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("date:"):
                invoice_date = self._parse_date(stripped.split(":", 1)[1].strip())
            elif stripped.lower().startswith("total:"):
                total_amount = self._parse_decimal(stripped.split(":", 1)[1].strip())

        return InvoiceExtractionResult(vendor_name=vendor_name, invoice_date=invoice_date, total_amount=total_amount)

    @staticmethod
    def _coalesce(mapping: dict, keys: list[str]) -> str | None:
        for key in keys:
            if key in mapping and mapping[key] is not None:
                value = mapping[key]
                if isinstance(value, str):
                    return value.strip()
                return str(value)
        return None

    @staticmethod
    def _parse_date(raw: str | None) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    @staticmethod
    def _parse_decimal(raw: str | float | int | None) -> Decimal | None:
        if raw is None:
            return None
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
