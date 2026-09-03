"""Debt analytics helpers: sparkline buckets, streak, monthly math."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from lib.domain.entities.money import quantize_money
from lib.domain.use_cases.debts import debt_credit_amount, is_debt_principal_tx

if TYPE_CHECKING:
    from lib.domain.entities.debt import Debt
    from lib.domain.entities.transaction import Transaction


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fractional_months_between(start: datetime, end: datetime) -> float:
    """Approximate fractional months between two UTC datetimes."""
    if end <= start:
        return 0.0
    days = (end - start).total_seconds() / 86400.0
    return max(days / 30.4375, 0.0)


def monthly_interest_for_debt(debt: "Debt") -> Decimal:
    """Monthly share of annual interest on remaining principal."""
    if debt.interest_rate is None:
        return Decimal("0.00")
    remaining = quantize_money(max(Decimal("0"), debt.remaining_amount))
    return quantize_money(
        remaining
        * Decimal(str(debt.interest_rate))
        / Decimal("100")
        / Decimal("12")
    )


def required_monthly_for_debt(
    remaining: Decimal,
    due_date: datetime | None,
    *,
    monthly_interest: Decimal = Decimal("0.00"),
    now: datetime | None = None,
) -> Decimal | None:
    """How much per month is needed to finish by due date (principal + interest)."""
    remaining = quantize_money(remaining)
    if remaining <= 0:
        return Decimal("0.00")
    if due_date is None:
        return None
    ref = now or _utc_now()
    left = fractional_months_between(ref, due_date)
    if left <= 0:
        return quantize_money(remaining)
    return quantize_money(remaining / Decimal(str(left)) + monthly_interest)


def net_debt_payment_flow(transactions: list["Transaction"]) -> Decimal:
    """Net principal paid down from repayment transactions."""
    total = Decimal("0")
    for tx in transactions:
        if not tx.debt_id or is_debt_principal_tx(tx):
            continue
        total += debt_credit_amount(tx)
    return quantize_money(total)


def bucket_payments_by_month(
    transactions: list["Transaction"],
    *,
    months: int = 6,
    now: datetime | None = None,
) -> list[tuple[str, Decimal]]:
    """Return ``[(YYYY-MM, total_credit), ...]`` oldest first."""
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
        if not tx.debt_id or is_debt_principal_tx(tx):
            continue
        when = tx.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        if key not in totals:
            continue
        totals[key] = quantize_money(totals[key] + debt_credit_amount(tx))
    return [(k, totals[k]) for k in keys]


def payment_streak_months(
    transactions: list["Transaction"],
    *,
    now: datetime | None = None,
) -> int:
    """Count consecutive months (including current) with positive repayments."""
    ref = now or _utc_now()
    month_totals: dict[str, Decimal] = {}
    for tx in transactions:
        if not tx.debt_id or is_debt_principal_tx(tx):
            continue
        when = tx.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        month_totals[key] = quantize_money(
            month_totals.get(key, Decimal("0")) + debt_credit_amount(tx)
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


class DebtPaymentSeries(BaseModel):
    """Monthly payment buckets for charts."""

    debt_id: str
    buckets: list[tuple[str, Decimal]] = Field(default_factory=list)
    streak_months: int = 0


class GetDebtPaymentSeriesUseCase:
    """Load repayment history buckets for sparkline / streak."""

    def __init__(self, transactions) -> None:
        self._transactions = transactions

    async def execute(self, debt_id: str, *, months: int = 6) -> DebtPaymentSeries:
        from datetime import timedelta

        now = _utc_now()
        lookback = now - timedelta(days=max(months, 1) * 31)
        txs = await self._transactions.list(debt_id=debt_id, date_from=lookback)
        buckets = bucket_payments_by_month(txs, months=months, now=now)
        streak = payment_streak_months(txs, now=now)
        return DebtPaymentSeries(
            debt_id=debt_id,
            buckets=buckets,
            streak_months=streak,
        )
