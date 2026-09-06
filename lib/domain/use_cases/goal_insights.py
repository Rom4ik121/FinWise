"""Goal analytics helpers: sparkline buckets, streak, flexible pace math."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING, Literal, NamedTuple

from pydantic import BaseModel, Field

from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import TransactionType
from lib.domain.use_cases.goals import goal_credit_amount

if TYPE_CHECKING:
    from lib.domain.entities.transaction import Transaction

PaceUnit = Literal["day", "week", "month", "total"]


class GoalPaceNeed(NamedTuple):
    """Required contribution amount for a display/calendar unit."""

    amount: Decimal
    unit: PaceUnit


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fractional_months_between(start: datetime, end: datetime) -> float:
    """Approximate fractional months between two UTC datetimes."""
    if end <= start:
        return 0.0
    days = (end - start).total_seconds() / 86400.0
    return max(days / 30.4375, 0.0)


def days_between(start: datetime, end: datetime) -> float:
    """Fractional days from ``start`` to ``end`` (0 when end is not later)."""
    if end <= start:
        return 0.0
    return (end - start).total_seconds() / 86400.0


def months_between(start: datetime, end: datetime) -> int:
    """Whole calendar months from start to end (minimum 1 when end is after start)."""
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(1, months)


def required_pace_for_goal(
    remaining: Decimal,
    deadline: datetime | None,
    *,
    now: datetime | None = None,
) -> GoalPaceNeed | None:
    """Required contribution paced to the deadline horizon.

    Short deadlines use day/week units so a 3-day goal is not shown as a
    huge “per month” figure.
    """
    if remaining <= 0:
        return GoalPaceNeed(Decimal("0.00"), "month")
    if deadline is None:
        return None
    ref = now or _utc_now()
    days = days_between(ref, deadline)
    if days <= 0:
        return GoalPaceNeed(quantize_money(remaining), "total")
    if days <= 7:
        return GoalPaceNeed(
            quantize_money(remaining / Decimal(str(max(days, 1.0 / 24)))),
            "day",
        )
    if days <= 45:
        weeks = max(days / 7.0, 1.0 / 7.0)
        return GoalPaceNeed(
            quantize_money(remaining / Decimal(str(weeks))),
            "week",
        )
    months = max(days / 30.4375, 1.0 / 30.4375)
    return GoalPaceNeed(
        quantize_money(remaining / Decimal(str(months))),
        "month",
    )


def required_monthly_for_goal(
    remaining: Decimal,
    deadline: datetime | None,
    *,
    now: datetime | None = None,
) -> Decimal | None:
    """Monthly-equivalent pace (for caches / reminders)."""
    pace = required_pace_for_goal(remaining, deadline, now=now)
    if pace is None:
        return None
    if pace.unit == "day":
        return quantize_money(pace.amount * Decimal("30.4375"))
    if pace.unit == "week":
        return quantize_money(pace.amount * Decimal("4.348125"))
    if pace.unit == "total":
        return quantize_money(pace.amount)
    return pace.amount


def net_goal_credit_flow(transactions: list["Transaction"]) -> Decimal:
    """Net credits to the goal: contributions minus withdrawals."""
    total = Decimal("0")
    for tx in transactions:
        if not tx.goal_id:
            continue
        credit = goal_credit_amount(tx)
        if tx.type == TransactionType.EXPENSE:
            total += credit
        elif tx.type == TransactionType.INCOME:
            total -= credit
    return quantize_money(total)


_MAX_PROJECTION_MONTHS = 600  # 50 years — beyond this a completion hint is not useful


def projected_date_from_planned(
    remaining: Decimal,
    planned_monthly: Decimal,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """When the goal would finish at a fixed monthly pace."""
    if remaining <= 0 or planned_monthly <= 0:
        return None
    ref = now or _utc_now()
    months_needed = int(
        (remaining / planned_monthly).to_integral_value(rounding=ROUND_CEILING)
    )
    months_needed = max(1, months_needed)
    if months_needed > _MAX_PROJECTION_MONTHS:
        return None
    year = ref.year + (ref.month - 1 + months_needed) // 12
    month = (ref.month - 1 + months_needed) % 12 + 1
    if not 1 <= year <= 9999:
        return None
    return ref.replace(year=year, month=month, day=min(ref.day, 28))


def bucket_contributions_by_month(
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
        if not tx.goal_id:
            continue
        when = tx.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        if key not in totals:
            continue
        credit = goal_credit_amount(tx)
        if tx.type == TransactionType.EXPENSE:
            totals[key] = quantize_money(totals[key] + credit)
        elif tx.type == TransactionType.INCOME:
            totals[key] = quantize_money(totals[key] - credit)
    return [(k, totals[k]) for k in keys]


def contribution_streak_months(
    transactions: list["Transaction"],
    *,
    now: datetime | None = None,
) -> int:
    """Count consecutive months (including current) with net positive savings."""
    ref = now or _utc_now()
    month_net: dict[str, Decimal] = {}
    for tx in transactions:
        if not tx.goal_id:
            continue
        when = tx.date
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = f"{when.year:04d}-{when.month:02d}"
        credit = goal_credit_amount(tx)
        if tx.type == TransactionType.EXPENSE:
            month_net[key] = quantize_money(month_net.get(key, Decimal("0")) + credit)
        elif tx.type == TransactionType.INCOME:
            month_net[key] = quantize_money(month_net.get(key, Decimal("0")) - credit)
    streak = 0
    y, m = ref.year, ref.month
    while True:
        key = f"{y:04d}-{m:02d}"
        if month_net.get(key, Decimal("0")) <= 0:
            break
        streak += 1
        m -= 1
        if m <= 0:
            m = 12
            y -= 1
    return streak


class GoalContributionSeries(BaseModel):
    """Monthly contribution buckets for charts."""

    goal_id: str
    buckets: list[tuple[str, Decimal]] = Field(default_factory=list)
    streak_months: int = 0


class GetGoalContributionSeriesUseCase:
    """Load contribution history buckets for sparkline / streak."""

    def __init__(self, transactions) -> None:
        self._transactions = transactions

    async def execute(self, goal_id: str, *, months: int = 6) -> GoalContributionSeries:
        from datetime import timedelta

        now = _utc_now()
        lookback = now - timedelta(days=max(months, 1) * 31)
        txs = await self._transactions.list(goal_id=goal_id, date_from=lookback)
        buckets = bucket_contributions_by_month(txs, months=months, now=now)
        streak = contribution_streak_months(txs, now=now)
        return GoalContributionSeries(
            goal_id=goal_id,
            buckets=buckets,
            streak_months=streak,
        )
