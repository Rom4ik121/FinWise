"""Budget pace, month shift, spend sparkline, and analytics aggregates."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field

from lib.domain.entities.budget import BudgetProgress
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.budget_repository import BudgetRepository
from lib.domain.services.rate_book import RateBook


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return ``(year, month)`` after adding ``delta`` months."""
    total = int(year) * 12 + (int(month) - 1) + int(delta)
    y, m = divmod(total, 12)
    return y, m + 1


class BudgetPace(BaseModel):
    """How current spend compares to a linear month-to-date plan."""

    days_in_month: int
    days_elapsed: int
    days_left: int
    expected_spent: Decimal = Decimal("0")
    daily_allowance: Decimal = Decimal("0")
    on_track: bool = True


def budget_pace(
    *,
    spent: Decimal,
    limit: Decimal,
    month: int,
    year: int,
    now: datetime | None = None,
) -> BudgetPace:
    """Linear pace for ``year``/``month`` relative to ``now`` (UTC)."""
    ref = now or _utc_now()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    days_in_month = monthrange(year, month)[1]
    if (ref.year, ref.month) > (year, month):
        elapsed = days_in_month
    elif (ref.year, ref.month) < (year, month):
        elapsed = 0
    else:
        elapsed = min(ref.day, days_in_month)
    left = max(0, days_in_month - elapsed)
    cap = quantize_money(limit)
    used = quantize_money(spent)
    expected = (
        quantize_money(cap * Decimal(elapsed) / Decimal(days_in_month))
        if days_in_month
        else Decimal("0")
    )
    remaining = cap - used
    daily = (
        quantize_money(remaining / Decimal(left))
        if left > 0 and remaining > 0
        else Decimal("0")
    )
    on_track = used <= expected if elapsed > 0 else True
    return BudgetPace(
        days_in_month=days_in_month,
        days_elapsed=elapsed,
        days_left=left,
        expected_spent=expected,
        daily_allowance=daily,
        on_track=on_track,
    )


def bucket_spend_by_month(
    transactions: list[Transaction],
    *,
    category: str | None = None,
    months: int = 6,
    now: datetime | None = None,
    rate_book: RateBook | None = None,
    to_currency: str | None = None,
) -> list[tuple[str, Decimal]]:
    """``[(YYYY-MM, spent), ...]`` oldest first. Missing FX skips that tx."""
    ref = now or _utc_now()
    keys: list[str] = []
    y, m = ref.year, ref.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = shift_month(y, m, -1)
    keys.reverse()
    totals = {k: Decimal("0") for k in keys}
    want = (category or "").strip().casefold()
    for tx in transactions:
        if tx.type != TransactionType.EXPENSE:
            continue
        if getattr(tx, "transfer_id", None):
            continue
        if getattr(tx, "goal_id", None) or getattr(tx, "goal_credit_amount", None):
            continue
        slices: list[tuple[str, Decimal]]
        items = getattr(tx, "items", None) or []
        if items:
            slices = [
                ((item.category or tx.category or "").strip(), item.amount)
                for item in items
            ]
        else:
            slices = [((tx.category or "").strip(), tx.amount)]
        when = tx.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        if key not in totals:
            continue
        for name, raw in slices:
            if want and name.casefold() != want:
                continue
            if not name:
                continue
            amount = quantize_money(raw)
            if rate_book is not None and to_currency:
                src = (tx.currency or to_currency).upper()
                dst = to_currency.upper()
                if src != dst:
                    converted = rate_book.convert(amount, src, dst)
                    if converted is None:
                        continue
                    amount = quantize_money(converted)
            totals[key] = quantize_money(totals[key] + amount)
    return [(k, totals[k]) for k in keys]


class BudgetAnalytics(BaseModel):
    """Month snapshot plus a 6-month spent/limit trend."""

    total_limit: Decimal = Decimal("0")
    total_spent: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")
    over_count: int = 0
    warning_count: int = 0
    count: int = 0
    monthly_trend: list[dict[str, object]] = Field(default_factory=list)
    items: list[BudgetProgress] = Field(default_factory=list)
    currency: str = "RUB"


class GetBudgetAnalyticsUseCase:
    """Aggregate budgets for a month and a short history trend."""

    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    async def execute(
        self,
        month: int,
        year: int,
        *,
        base_currency: str = "RUB",
        now: datetime | None = None,
    ) -> BudgetAnalytics:
        items = await self._budgets.list_for_month(month, year)
        items.sort(key=lambda b: b.percent_used, reverse=True)
        progress = [BudgetProgress.from_budget(b) for b in items]
        total_limit = quantize_money(
            sum((p.limit for p in progress), Decimal("0"))
        )
        total_spent = quantize_money(
            sum((p.spent for p in progress), Decimal("0"))
        )
        over_count = sum(1 for p in progress if p.is_over_budget)
        warning_count = sum(
            1 for p in progress if (not p.is_over_budget) and p.percent >= 80
        )
        ref = now or _utc_now()
        all_rows = await self._budgets.list_all()
        by_month: dict[str, tuple[Decimal, Decimal]] = {}
        for row in all_rows:
            key = f"{row.year:04d}-{row.month:02d}"
            limit, spent = by_month.get(key, (Decimal("0"), Decimal("0")))
            by_month[key] = (limit + row.amount_limit, spent + row.spent)
        trend: list[dict[str, object]] = []
        y, m = ref.year, ref.month
        keys: list[str] = []
        for _ in range(6):
            keys.append(f"{y:04d}-{m:02d}")
            y, m = shift_month(y, m, -1)
        for key in reversed(keys):
            limit, spent = by_month.get(key, (Decimal("0"), Decimal("0")))
            trend.append(
                {
                    "month": key,
                    "limit": quantize_money(limit),
                    "spent": quantize_money(spent),
                }
            )
        return BudgetAnalytics(
            total_limit=total_limit,
            total_spent=total_spent,
            remaining=quantize_money(total_limit - total_spent),
            over_count=over_count,
            warning_count=warning_count,
            count=len(progress),
            monthly_trend=trend,
            items=progress,
            currency=(base_currency or "RUB").upper(),
        )
