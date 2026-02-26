import uuid
from decimal import Decimal

import pytest

from app.models.enums import AnomalySeverity, AnomalyType
from app.services.anomaly_detector import (
    _check_abnormal_total,
    _check_price_creep,
)

INVOICE_ID = uuid.uuid4()


# =====================================================================
# Price creep detection
# =====================================================================


class TestPriceCreep:
    def test_flags_three_consecutive_increases_above_threshold(self) -> None:
        # Chronological: 100 -> 105 -> 112 -> 125 (new)
        # recent_totals is newest-first: [112, 105, 100]
        recent = [Decimal("112"), Decimal("105"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("125"), recent)

        assert result is not None
        assert result.type == AnomalyType.PRICE_CREEP
        assert result.severity == AnomalySeverity.MEDIUM
        assert "3 consecutive increases" in result.reason_text
        assert "25.0%" in result.reason_text

    def test_flags_four_consecutive_increases(self) -> None:
        # Chronological: 100 -> 105 -> 110 -> 115 -> 122 (new)
        recent = [Decimal("115"), Decimal("110"), Decimal("105"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("122"), recent)

        assert result is not None
        assert "4 consecutive increases" in result.reason_text

    def test_no_flag_when_below_cumulative_threshold(self) -> None:
        # Chronological: 100 -> 101 -> 102 -> 103 (new) -- only 3% increase
        recent = [Decimal("102"), Decimal("101"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("103"), recent)

        assert result is None

    def test_no_flag_when_streak_broken(self) -> None:
        # Chronological: 100 -> 120 -> 105 -> 115 (new)
        # recent newest-first: [105, 120, 100]
        # 115 > 105 (ok), but 105 < 120 (breaks streak)
        recent = [Decimal("105"), Decimal("120"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("115"), recent)

        assert result is None

    def test_no_flag_with_fewer_than_three_prior_invoices(self) -> None:
        recent = [Decimal("105"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("112"), recent)

        assert result is None

    def test_no_flag_with_empty_history(self) -> None:
        result = _check_price_creep(INVOICE_ID, Decimal("100"), [])

        assert result is None

    def test_no_flag_when_current_is_decrease(self) -> None:
        # Chronological: 100 -> 105 -> 110 -> 108 (new) -- latest is a decrease
        recent = [Decimal("110"), Decimal("105"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("108"), recent)

        assert result is None

    def test_no_flag_when_totals_are_equal(self) -> None:
        # Flat: 100 -> 100 -> 100 -> 100 (new)
        recent = [Decimal("100"), Decimal("100"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("100"), recent)

        assert result is None

    def test_exact_10_percent_cumulative_triggers(self) -> None:
        # Chronological: 100 -> 103 -> 106 -> 110 (new) -- exactly 10%
        recent = [Decimal("106"), Decimal("103"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("110"), recent)

        assert result is not None
        assert result.type == AnomalyType.PRICE_CREEP

    def test_reason_text_includes_baseline_and_current(self) -> None:
        recent = [Decimal("112"), Decimal("105"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("125"), recent)

        assert result is not None
        assert "100.00" in result.reason_text
        assert "125.00" in result.reason_text

    def test_long_streak_with_small_increments(self) -> None:
        # 100 -> 104 -> 108 -> 112 -> 116 -> 120 (new) -- 5 increases, 20%
        recent = [Decimal("116"), Decimal("112"), Decimal("108"), Decimal("104"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("120"), recent)

        assert result is not None
        assert "5 consecutive increases" in result.reason_text

    def test_streak_stops_at_flat_segment(self) -> None:
        # Chronological: 100 -> 100 -> 105 -> 112 -> 125 (new)
        # newest-first: [112, 105, 100, 100]
        # 125 > 112 > 105 > 100, but 100 == 100 breaks the strict > check
        recent = [Decimal("112"), Decimal("105"), Decimal("100"), Decimal("100")]
        result = _check_price_creep(INVOICE_ID, Decimal("125"), recent)

        assert result is not None
        assert "3 consecutive increases" in result.reason_text

    def test_ignores_zero_baseline(self) -> None:
        recent = [Decimal("5"), Decimal("3"), Decimal("0")]
        result = _check_price_creep(INVOICE_ID, Decimal("10"), recent)

        assert result is None


# =====================================================================
# Abnormal total detection
# =====================================================================


class TestAbnormalTotal:
    def test_flags_spike_above_150_percent(self) -> None:
        recent = [Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100")]
        results = _check_abnormal_total(INVOICE_ID, Decimal("160"), recent)

        assert len(results) == 1
        assert results[0].type == AnomalyType.ABNORMAL_TOTAL
        assert results[0].severity == AnomalySeverity.HIGH
        assert "150%" in results[0].reason_text

    def test_no_flag_below_150_percent(self) -> None:
        recent = [Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100")]
        results = _check_abnormal_total(INVOICE_ID, Decimal("140"), recent)

        assert len(results) == 0

    def test_flags_low_outlier_via_stddev(self) -> None:
        tight = [Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("101")]
        results = _check_abnormal_total(INVOICE_ID, Decimal("40"), tight)

        assert len(results) == 1
        assert results[0].type == AnomalyType.ABNORMAL_TOTAL
        assert "lower" in results[0].reason_text

    def test_no_flag_with_empty_history(self) -> None:
        results = _check_abnormal_total(INVOICE_ID, Decimal("100"), [])

        assert len(results) == 0

    def test_stddev_needs_at_least_5_invoices(self) -> None:
        # 4 prior invoices -- not enough for std dev check
        recent = [Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100")]
        results = _check_abnormal_total(INVOICE_ID, Decimal("40"), recent)

        assert len(results) == 0

    def test_does_not_double_flag_spike_and_stddev(self) -> None:
        tight = [Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("101")]
        results = _check_abnormal_total(INVOICE_ID, Decimal("200"), tight)

        assert len(results) == 1
        assert "150%" in results[0].reason_text
