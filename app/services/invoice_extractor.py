from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class InvoiceExtractionResult:
    vendor_name: str | None = None
    invoice_date: date | None = None
    total_amount: Decimal | None = None


class InvoiceMetadataExtractor:
    """Best-effort invoice metadata extractor with PDF support via pdfplumber."""

    def extract(self, file_path: Path) -> InvoiceExtractionResult:
        """Extract vendor name, invoice date, and total from a file.

        Supports PDF, JSON, and line-based text files.
        Returns empty fields when no data can be derived.
        """

        if not file_path.exists():
            return InvoiceExtractionResult()

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._from_pdf(file_path)
        if suffix == ".json":
            return self._from_json(file_path)
        if suffix in {".txt", ".log"}:
            return self._from_text(file_path)
        return InvoiceExtractionResult()

    # ------------------------------------------------------------------
    # PDF extraction
    # ------------------------------------------------------------------

    def _from_pdf(self, file_path: Path) -> InvoiceExtractionResult:
        try:
            with pdfplumber.open(file_path) as pdf:
                pages_text: list[str] = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                full_text = "\n".join(pages_text)
        except Exception:
            logger.warning("Failed to read PDF: %s", file_path, exc_info=True)
            return InvoiceExtractionResult()

        if not full_text.strip():
            return InvoiceExtractionResult()

        vendor_name = self._extract_vendor_from_text(full_text)
        invoice_date = self._extract_date_from_text(full_text)
        total_amount = self._extract_total_from_text(full_text)

        return InvoiceExtractionResult(
            vendor_name=vendor_name,
            invoice_date=invoice_date,
            total_amount=total_amount,
        )

    @staticmethod
    def _extract_vendor_from_text(text: str) -> str | None:
        """Attempt to pull a vendor / supplier name from the PDF body."""

        labelled = re.search(
            r"(?:vendor|supplier|bill\s*from|from|company)\s*[:\-]\s*(.+)",
            text,
            re.IGNORECASE,
        )
        if labelled:
            candidate = labelled.group(1).strip().split("\n")[0].strip()
            if 2 <= len(candidate) <= 120:
                return candidate

        lines = text.strip().splitlines()
        for line in lines[:5]:
            cleaned = line.strip()
            if cleaned and not re.match(r"^(invoice|bill|receipt|date|total|amount|tax|page)\b", cleaned, re.IGNORECASE):
                if 2 <= len(cleaned) <= 120:
                    return cleaned

        return None

    @staticmethod
    def _extract_date_from_text(text: str) -> date | None:
        """Search for the most likely invoice date in the text."""

        labelled = re.search(
            r"(?:invoice\s*date|date\s*of\s*invoice|bill\s*date|date)\s*[:\-]\s*(.+)",
            text,
            re.IGNORECASE,
        )
        date_region = labelled.group(1).strip()[:40] if labelled else text

        # ISO-style: 2025-01-15
        iso_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_region)
        if iso_match:
            return _safe_date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

        # DD/MM/YYYY or MM/DD/YYYY (assume DD/MM for ambiguous cases)
        slash_match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", date_region)
        if slash_match:
            a, b, year = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
            if a > 12:
                return _safe_date(year, b, a)
            if b > 12:
                return _safe_date(year, a, b)
            return _safe_date(year, b, a)

        # "15 January 2025" or "January 15, 2025"
        long_match = re.search(
            r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
            date_region,
        )
        if long_match:
            day, month_str, year = int(long_match.group(1)), long_match.group(2).lower(), int(long_match.group(3))
            month = _MONTH_NAMES.get(month_str)
            if month:
                return _safe_date(year, month, day)

        long_match2 = re.search(
            r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
            date_region,
        )
        if long_match2:
            month_str, day, year = long_match2.group(1).lower(), int(long_match2.group(2)), int(long_match2.group(3))
            month = _MONTH_NAMES.get(month_str)
            if month:
                return _safe_date(year, month, day)

        return None

    @staticmethod
    def _extract_total_from_text(text: str) -> Decimal | None:
        """Find the final / grand total amount on the invoice.

        Looks for labelled totals first (e.g. "Total Due: $1,234.56"),
        then falls back to the largest currency-formatted number.
        """

        total_patterns = [
            r"(?:grand\s*total|total\s*due|amount\s*due|balance\s*due|total\s*amount|net\s*total|total)\s*[:\-]?\s*\$?\s*([\d,]+\.?\d*)",
        ]
        candidates: list[Decimal] = []
        for pattern in total_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                val = _parse_currency(match.group(1))
                if val is not None:
                    candidates.append(val)

        if candidates:
            return max(candidates)

        currency_amounts: list[Decimal] = []
        for match in re.finditer(r"\$\s*([\d,]+\.\d{2})", text):
            val = _parse_currency(match.group(1))
            if val is not None:
                currency_amounts.append(val)

        if currency_amounts:
            return max(currency_amounts)

        return None

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Plain-text extraction
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_currency(raw: str) -> Decimal | None:
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except (InvalidOperation, ValueError):
        return None
