from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.invoice_extractor import InvoiceExtractionResult, InvoiceMetadataExtractor


@pytest.fixture()
def extractor() -> InvoiceMetadataExtractor:
    return InvoiceMetadataExtractor()


# =====================================================================
# Vendor extraction
# =====================================================================


class TestExtractVendor:
    def test_labelled_vendor(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Some header\nVendor: Acme Corp\nDate: 2025-01-01"
        assert extractor._extract_vendor_from_text(text) == "Acme Corp"

    def test_labelled_supplier(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Supplier: Global Supplies Ltd\nInvoice #12345"
        assert extractor._extract_vendor_from_text(text) == "Global Supplies Ltd"

    def test_labelled_bill_from(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Bill From: Widget Factory\nBill To: My Company"
        assert extractor._extract_vendor_from_text(text) == "Widget Factory"

    def test_labelled_company(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Company: Northern Electric\nAmount: $500"
        assert extractor._extract_vendor_from_text(text) == "Northern Electric"

    def test_fallback_first_non_boilerplate_line(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Widgets International\nInvoice #456\nDate: 2025-03-01\nTotal: $100.00"
        assert extractor._extract_vendor_from_text(text) == "Widgets International"

    def test_skips_invoice_header_line(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Invoice #12345\nWidgets International\nDate: 2025-03-01"
        assert extractor._extract_vendor_from_text(text) == "Widgets International"

    def test_skips_date_and_total_lines(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Date: 2025-01-01\nTotal: $100\nAmount: 50\nSupply House Inc"
        assert extractor._extract_vendor_from_text(text) == "Supply House Inc"

    def test_returns_none_for_empty_text(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_vendor_from_text("") is None

    def test_returns_none_when_all_lines_are_boilerplate(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Invoice\nBill\nReceipt\nDate\nTotal"
        assert extractor._extract_vendor_from_text(text) is None

    def test_rejects_single_char_vendor(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Vendor: X\nOther stuff"
        result = extractor._extract_vendor_from_text(text)
        assert result != "X"


# =====================================================================
# Date extraction
# =====================================================================


class TestExtractDate:
    def test_iso_date(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 2025-01-15") == date(2025, 1, 15)

    def test_iso_date_in_labelled_field(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Invoice Date: 2025-06-30\nTotal: $100"
        assert extractor._extract_date_from_text(text) == date(2025, 6, 30)

    def test_slash_dd_mm_yyyy(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 15/01/2025") == date(2025, 1, 15)

    def test_slash_mm_dd_disambiguated_by_day_gt_12(self, extractor: InvoiceMetadataExtractor) -> None:
        # 25/06/2025 — first number > 12 so it must be day
        assert extractor._extract_date_from_text("Date: 25/06/2025") == date(2025, 6, 25)

    def test_slash_second_number_gt_12_means_day(self, extractor: InvoiceMetadataExtractor) -> None:
        # 06/25/2025 — second number > 12 so it must be day, first is month
        assert extractor._extract_date_from_text("Date: 06/25/2025") == date(2025, 6, 25)

    def test_dot_separator(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 15.03.2025") == date(2025, 3, 15)

    def test_long_form_day_month_year(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 15 January 2025") == date(2025, 1, 15)

    def test_long_form_month_day_year(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: January 15, 2025") == date(2025, 1, 15)

    def test_abbreviated_month(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 22 Mar 2025") == date(2025, 3, 22)

    def test_abbreviated_month_day_year(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: Sep 5, 2025") == date(2025, 9, 5)

    def test_bill_date_label(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Bill Date: 2025-12-01\nAmount: $50"
        assert extractor._extract_date_from_text(text) == date(2025, 12, 1)

    def test_date_of_invoice_label(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Date of Invoice: 10/11/2025"
        assert extractor._extract_date_from_text(text) == date(2025, 11, 10)

    def test_returns_none_for_no_date(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("No date here at all") is None

    def test_returns_none_for_empty_text(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("") is None

    def test_invalid_date_returns_none(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_date_from_text("Date: 2025-13-45") is None


# =====================================================================
# Total extraction
# =====================================================================


class TestExtractTotal:
    def test_total_with_dollar_and_commas(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Subtotal: $800.00\nTax: $80.00\nTotal Due: $1,234.56"
        assert extractor._extract_total_from_text(text) == Decimal("1234.56")

    def test_grand_total(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Subtotal: $500.00\nGrand Total $12,500.00"
        assert extractor._extract_total_from_text(text) == Decimal("12500.00")

    def test_amount_due(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Amount Due: $500.00") == Decimal("500.00")

    def test_balance_due(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Balance Due: 750.25") == Decimal("750.25")

    def test_total_amount_label(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Total Amount: $999.99") == Decimal("999.99")

    def test_plain_total_no_dollar(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Total: 450.00") == Decimal("450.00")

    def test_total_with_colon(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Total: $100.50") == Decimal("100.50")

    def test_total_with_dash(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Total - $200.75") == Decimal("200.75")

    def test_picks_largest_labelled_total(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Subtotal: $800.00\nTotal: $900.00\nGrand Total: $1,000.00"
        assert extractor._extract_total_from_text(text) == Decimal("1000.00")

    def test_falls_back_to_largest_dollar_amount(self, extractor: InvoiceMetadataExtractor) -> None:
        text = "Item A $50.00\nItem B $75.00\nItem C $120.00"
        assert extractor._extract_total_from_text(text) == Decimal("120.00")

    def test_returns_none_for_no_amounts(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("No amounts here") is None

    def test_returns_none_for_empty_text(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("") is None

    def test_large_amount_with_commas(self, extractor: InvoiceMetadataExtractor) -> None:
        assert extractor._extract_total_from_text("Total: $1,000,000.00") == Decimal("1000000.00")


# =====================================================================
# _from_pdf (pdfplumber integration, mocked)
# =====================================================================


class TestFromPdf:
    SAMPLE_PDF_TEXT = (
        "Acme Corp\n"
        "123 Business St\n"
        "Invoice #10042\n"
        "Invoice Date: 2025-03-15\n"
        "Item         Qty   Price\n"
        "Widget A       2   $50.00\n"
        "Widget B       1   $75.00\n"
        "Subtotal: $175.00\n"
        "Tax: $17.50\n"
        "Total Due: $192.50"
    )

    def _mock_pdf(self, text: str | None) -> MagicMock:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        return mock_pdf

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_extracts_all_fields(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        mock_pdfplumber.open.return_value = self._mock_pdf(self.SAMPLE_PDF_TEXT)

        result = extractor._from_pdf(Path("fake.pdf"))

        assert result.vendor_name == "Acme Corp"
        assert result.invoice_date == date(2025, 3, 15)
        assert result.total_amount == Decimal("192.50")

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_empty_pdf_returns_empty_result(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        mock_pdfplumber.open.return_value = self._mock_pdf("")

        result = extractor._from_pdf(Path("empty.pdf"))

        assert result == InvoiceExtractionResult()

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_none_page_text_returns_empty_result(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        mock_pdfplumber.open.return_value = self._mock_pdf(None)

        result = extractor._from_pdf(Path("blank.pdf"))

        assert result == InvoiceExtractionResult()

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_corrupt_pdf_returns_empty_result(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        mock_pdfplumber.open.side_effect = Exception("corrupt file")

        result = extractor._from_pdf(Path("corrupt.pdf"))

        assert result == InvoiceExtractionResult()

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_multi_page_pdf(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        page1 = MagicMock()
        page1.extract_text.return_value = "Acme Corp\nInvoice Date: 2025-04-01"
        page2 = MagicMock()
        page2.extract_text.return_value = "Total Due: $500.00"

        mock_pdf = MagicMock()
        mock_pdf.pages = [page1, page2]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        result = extractor._from_pdf(Path("multi.pdf"))

        assert result.vendor_name == "Acme Corp"
        assert result.invoice_date == date(2025, 4, 1)
        assert result.total_amount == Decimal("500.00")

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_partial_extraction(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor) -> None:
        mock_pdfplumber.open.return_value = self._mock_pdf("Vendor: Quick Parts\nSome random text")

        result = extractor._from_pdf(Path("partial.pdf"))

        assert result.vendor_name == "Quick Parts"
        assert result.invoice_date is None
        assert result.total_amount is None


# =====================================================================
# extract() dispatch (file extension routing)
# =====================================================================


class TestExtractDispatch:
    def test_nonexistent_file_returns_empty(self, extractor: InvoiceMetadataExtractor) -> None:
        result = extractor.extract(Path("does/not/exist.pdf"))
        assert result == InvoiceExtractionResult()

    def test_unknown_extension_returns_empty(self, extractor: InvoiceMetadataExtractor, tmp_path: Path) -> None:
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"fake")
        assert extractor.extract(f) == InvoiceExtractionResult()

    def test_dispatches_json(self, extractor: InvoiceMetadataExtractor, tmp_path: Path) -> None:
        f = tmp_path / "invoice.json"
        f.write_text('{"vendor_name": "TestCo", "date": "2025-05-01", "total": "250.00"}')

        result = extractor.extract(f)

        assert result.vendor_name == "TestCo"
        assert result.invoice_date == date(2025, 5, 1)
        assert result.total_amount == Decimal("250.00")

    def test_dispatches_txt(self, extractor: InvoiceMetadataExtractor, tmp_path: Path) -> None:
        f = tmp_path / "invoice.txt"
        f.write_text("Vendor: TextVendor\nDate: 2025-07-10\nTotal: 400.00")

        result = extractor.extract(f)

        assert result.vendor_name == "TextVendor"
        assert result.invoice_date == date(2025, 7, 10)
        assert result.total_amount == Decimal("400.00")

    @patch("app.services.invoice_extractor.pdfplumber")
    def test_dispatches_pdf(self, mock_pdfplumber: MagicMock, extractor: InvoiceMetadataExtractor, tmp_path: Path) -> None:
        f = tmp_path / "invoice.pdf"
        f.write_bytes(b"fake pdf content")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Vendor: PDF Corp\nDate: 2025-08-20\nTotal: $600.00"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        result = extractor.extract(f)

        assert result.vendor_name == "PDF Corp"
        assert result.invoice_date == date(2025, 8, 20)
        assert result.total_amount == Decimal("600.00")

    def test_case_insensitive_extension(self, extractor: InvoiceMetadataExtractor, tmp_path: Path) -> None:
        f = tmp_path / "invoice.JSON"
        f.write_text('{"vendor": "CaseTest", "total": "99"}')

        result = extractor.extract(f)

        assert result.vendor_name == "CaseTest"
