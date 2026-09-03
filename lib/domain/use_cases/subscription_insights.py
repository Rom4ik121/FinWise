"""Subscription analytics helpers: sparkline buckets and missed periods."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from lib.domain.entities.money import quantize_money
from lib.domain.services.rate_book import RateBook

if TYPE_CHECKING:
    from lib.domain.entities.transaction import Transaction


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tx_amount(
    tx: "Transaction",
    *,
    rate_book: RateBook | None = None,
    to_currency: str | None = None,
) -> Decimal | None:
    """Amount in ``to_currency`` when a rate book is provided; else ledger amount."""
    amount = quantize_money(tx.amount)
    if rate_book is None or not to_currency:
        return amount
    src = (tx.currency or to_currency).upper()
    dst = to_currency.upper()
    if src == dst:
        return amount
    converted = rate_book.convert(amount, src, dst)
    if converted is None:
        return None
    return quantize_money(converted)


def bucket_charges_by_month(
    transactions: list["Transaction"],
    *,
    months: int = 6,
    now: datetime | None = None,
    rate_book: RateBook | None = None,
    to_currency: str | None = None,
) -> list[tuple[str, Decimal]]:
    """Return ``[(YYYY-MM, total_amount), ...]`` oldest first.

    When ``rate_book`` and ``to_currency`` are set, each charge is converted
    (missing rate → that tx is skipped, never silently mixed).
    """
    ref = now or _utc_now()
    keys: list[str] = []
    for i in range(months - 1, -1, -1):
        y = ref.year
        m = ref.month - i
        while m <= 0:
            m += 12
            y -= 1
        keys.append(f"{y:04d}-{m:02d}")
    totals = {k: Decimal("0") for k in keys}
    for tx in transactions:
        if not getattr(tx, "subscription_id", None):
            continue
        amount = _tx_amount(tx, rate_book=rate_book, to_currency=to_currency)
        if amount is None:
            continue
        when = _as_utc(tx.date)
        key = f"{when.year:04d}-{when.month:02d}"
        if key not in totals:
            continue
        totals[key] = quantize_money(totals[key] + amount)
    return [(k, totals[k]) for k in keys]


def charge_streak_months(
    transactions: list["Transaction"],
    *,
    now: datetime | None = None,
    rate_book: RateBook | None = None,
    to_currency: str | None = None,
) -> int:
    """Count consecutive months (including current) with charges."""
    ref = now or _utc_now()
    month_totals: dict[str, Decimal] = {}
    for tx in transactions:
        if not getattr(tx, "subscription_id", None):
            continue
        amount = _tx_amount(tx, rate_book=rate_book, to_currency=to_currency)
        if amount is None:
            continue
        when = _as_utc(tx.date)
        key = f"{when.year:04d}-{when.month:02d}"
        month_totals[key] = quantize_money(
            month_totals.get(key, Decimal("0")) + amount
        )
    streak = 0
    y, m = ref.year, ref.month
    while True:
        key = f"{y:04d}-{m:02d}"
        if month_totals.get(key, Decimal("0")) <= 0:
            break
        streak += 1
        m -= 1
        if m <= 0:
            m = 12
            y -= 1
    return streak


class SubscriptionChargeSeries(BaseModel):
    """Monthly charge buckets for charts."""

    subscription_id: str
    buckets: list[tuple[str, Decimal]] = Field(default_factory=list)
    streak_months: int = 0


class GetSubscriptionChargeSeriesUseCase:
    """Load charge history buckets for sparkline / streak."""

    def __init__(self, transactions) -> None:
        self._transactions = transactions

    async def execute(
        self,
        subscription_id: str,
        *,
        months: int = 6,
        rate_book: RateBook | None = None,
        to_currency: str | None = None,
    ) -> SubscriptionChargeSeries:
        from datetime import timedelta

        now = _utc_now()
        lookback = now - timedelta(days=max(months, 1) * 31)
        txs = await self._transactions.list(
            subscription_id=subscription_id, date_from=lookback
        )
        return SubscriptionChargeSeries(
            subscription_id=subscription_id,
            buckets=bucket_charges_by_month(
                txs,
                months=months,
                now=now,
                rate_book=rate_book,
                to_currency=to_currency,
            ),
            streak_months=charge_streak_months(
                txs, now=now, rate_book=rate_book, to_currency=to_currency
            ),
        )
