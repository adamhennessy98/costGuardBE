from __future__ import annotations

from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.models.enums import AnomalySeverity, AnomalyStatus, AnomalyType

PRICE_CREEP_MIN_STREAK = 3
PRICE_CREEP_MIN_CUMULATIVE_PCT = Decimal("0.10")

ABNORMAL_TOTAL_THRESHOLD = Decimal("1.5")
ABNORMAL_TOTAL_STD_DEV_FACTOR = Decimal("3")
ABNORMAL_TOTAL_MIN_HISTORY = 5

RECENT_HISTORY_LIMIT = 25


def detect_anomalies(
    db: Session,
    invoice: models.Invoice,
    vendor_id: UUID,
    total_amount: Decimal,
) -> list[models.Anomaly]:
    """Run all anomaly checks against a newly created invoice.

    Returns a list of Anomaly model instances (not yet added to the session).
    """
    anomalies: list[models.Anomaly] = []

    duplicate = _check_duplicate(db, invoice, vendor_id, total_amount)
    if duplicate:
        anomalies.append(duplicate)

    recent_totals = _fetch_recent_totals(db, invoice.id, vendor_id)

    abnormal = _check_abnormal_total(invoice.id, total_amount, recent_totals)
    anomalies.extend(abnormal)

    creep = _check_price_creep(invoice.id, total_amount, recent_totals)
    if creep:
        anomalies.append(creep)

    return anomalies


def _check_duplicate(
    db: Session,
    invoice: models.Invoice,
    vendor_id: UUID,
    total_amount: Decimal,
) -> models.Anomaly | None:
    stmt = (
        select(models.Invoice)
        .where(models.Invoice.vendor_id == vendor_id)
        .where(models.Invoice.invoice_date == invoice.invoice_date)
        .where(models.Invoice.total_amount == total_amount)
        .where(models.Invoice.id != invoice.id)
    )
    if db.scalar(stmt) is not None:
        return models.Anomaly(
            invoice_id=invoice.id,
            type=AnomalyType.DUPLICATE,
            severity=AnomalySeverity.MEDIUM,
            status=AnomalyStatus.UNREVIEWED,
            reason_text="Potential duplicate invoice: matches vendor, date, and total amount.",
        )
    return None


def _fetch_recent_totals(
    db: Session,
    current_invoice_id: UUID,
    vendor_id: UUID,
) -> list[Decimal]:
    """Return up to RECENT_HISTORY_LIMIT prior totals, newest-first."""
    stmt = (
        select(models.Invoice.total_amount)
        .where(models.Invoice.vendor_id == vendor_id)
        .where(models.Invoice.id != current_invoice_id)
        .order_by(models.Invoice.invoice_date.desc())
        .limit(RECENT_HISTORY_LIMIT)
    )
    raw = db.scalars(stmt).all()
    return [v if isinstance(v, Decimal) else Decimal(str(v)) for v in raw if v is not None]


def _check_abnormal_total(
    invoice_id: UUID,
    total_amount: Decimal,
    recent_totals: list[Decimal],
) -> list[models.Anomaly]:
    """150%-of-average threshold check and 3x-std-dev outlier check."""
    if not recent_totals:
        return []

    average = sum(recent_totals) / Decimal(len(recent_totals))
    anomalies: list[models.Anomaly] = []

    high_threshold = average * ABNORMAL_TOTAL_THRESHOLD
    if total_amount >= high_threshold:
        anomalies.append(models.Anomaly(
            invoice_id=invoice_id,
            type=AnomalyType.ABNORMAL_TOTAL,
            severity=AnomalySeverity.HIGH,
            status=AnomalyStatus.UNREVIEWED,
            reason_text=(
                "Invoice total exceeds 150% of recent vendor average "
                f"({total_amount} vs {average.quantize(Decimal('0.01'))})."
            ),
        ))
        return anomalies

    if len(recent_totals) >= ABNORMAL_TOTAL_MIN_HISTORY:
        with localcontext() as ctx:
            ctx.prec = 28
            variance = sum((a - average) ** 2 for a in recent_totals) / Decimal(len(recent_totals))
            std_dev = variance.sqrt() if variance > 0 else Decimal("0")

        if std_dev > 0:
            deviation = (total_amount - average).copy_abs()
            if deviation >= std_dev * ABNORMAL_TOTAL_STD_DEV_FACTOR:
                direction = "higher" if total_amount > average else "lower"
                anomalies.append(models.Anomaly(
                    invoice_id=invoice_id,
                    type=AnomalyType.ABNORMAL_TOTAL,
                    severity=AnomalySeverity.HIGH,
                    status=AnomalyStatus.UNREVIEWED,
                    reason_text=(
                        f"Invoice total is {direction} than normal for this vendor; deviation "
                        f"{deviation.quantize(Decimal('0.01'))} vs std dev {std_dev.quantize(Decimal('0.01'))}."
                    ),
                ))

    return anomalies


def _check_price_creep(
    invoice_id: UUID,
    total_amount: Decimal,
    recent_totals: list[Decimal],
) -> models.Anomaly | None:
    """Detect sustained upward drift across consecutive invoices.

    recent_totals is ordered newest-first (excluding the current invoice).
    The chronological sequence is:
        ... recent_totals[2] -> recent_totals[1] -> recent_totals[0] -> total_amount

    We walk backwards from the current invoice and count how many consecutive
    increases there are. If the streak reaches PRICE_CREEP_MIN_STREAK and the
    cumulative % increase from the streak baseline exceeds
    PRICE_CREEP_MIN_CUMULATIVE_PCT, we flag it.
    """
    if len(recent_totals) < PRICE_CREEP_MIN_STREAK:
        return None

    streak = 0
    previous = total_amount
    for older_total in recent_totals:
        if previous > older_total > 0:
            streak += 1
            previous = older_total
        else:
            break

    if streak < PRICE_CREEP_MIN_STREAK:
        return None

    baseline = previous
    if baseline <= 0:
        return None

    cumulative_pct = (total_amount - baseline) / baseline

    if cumulative_pct < PRICE_CREEP_MIN_CUMULATIVE_PCT:
        return None

    pct_display = (cumulative_pct * 100).quantize(Decimal("0.1"))
    return models.Anomaly(
        invoice_id=invoice_id,
        type=AnomalyType.PRICE_CREEP,
        severity=AnomalySeverity.MEDIUM,
        status=AnomalyStatus.UNREVIEWED,
        reason_text=(
            f"Price creep detected: {streak} consecutive increases totalling "
            f"{pct_display}% over the period "
            f"(from {baseline.quantize(Decimal('0.01'))} to {total_amount.quantize(Decimal('0.01'))})."
        ),
    )
