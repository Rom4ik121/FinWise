"""Analytics chart period presets for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from lib.domain.use_cases.transactions import GetTransactionStatsUseCase, StatsPeriod

ANALYTICS_PERIOD_KEYS = ("1d", "7d", "30d", "90d", "180d", "365d", "all")
EXPORT_PERIOD_KEYS = ("7d", "30d", "90d", "180d", "365d", "all", "custom")
DEFAULT_ANALYTICS_PERIOD = "30d"


@dataclass(frozen=True)
class AnalyticsPeriodConfig:
    """Resolved date range and grouping for dashboard charts."""

    key: str
    date_from: datetime | None
    date_to: datetime
    group_by: StatsPeriod
    max_chart_points: int | None


def resolve_analytics_period(key: str, now: datetime) -> AnalyticsPeriodConfig:
    """Map a preset key to query bounds and chart granularity."""
    if key == "1d":
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=1),
            date_to=now,
            group_by=StatsPeriod.DAY,
            max_chart_points=None,
        )
    if key == "7d":
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=7),
            date_to=now,
            group_by=StatsPeriod.DAY,
            max_chart_points=None,
        )
    if key == "90d":
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=90),
            date_to=now,
            group_by=StatsPeriod.WEEK,
            max_chart_points=None,
        )
    if key == "180d":
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=180),
            date_to=now,
            group_by=StatsPeriod.WEEK,
            max_chart_points=None,
        )
    if key == "365d":
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=365),
            date_to=now,
            group_by=StatsPeriod.MONTH,
            max_chart_points=None,
        )
    if key == "all":
        # Bound "all time" so phones with years of history stay responsive.
        # Charts still downsample to max_chart_points; UI label stays "all".
        return AnalyticsPeriodConfig(
            key=key,
            date_from=now - timedelta(days=365 * 5),
            date_to=now,
            group_by=StatsPeriod.MONTH,
            max_chart_points=36,
        )
    # Default and explicit 30d.
    return AnalyticsPeriodConfig(
        key="30d",
        date_from=now - timedelta(days=30),
        date_to=now,
        group_by=StatsPeriod.DAY,
        max_chart_points=None,
    )


def resolve_export_period(
    key: str,
    now: datetime,
    *,
    custom_from: datetime | None = None,
    custom_to: datetime | None = None,
) -> AnalyticsPeriodConfig:
    """Period bounds for PDF export, including an explicit custom range."""
    if key != "custom":
        return resolve_analytics_period(key, now)
    if custom_from is None or custom_to is None:
        raise ValueError("Custom period requires dates")
    start = custom_from if custom_from <= custom_to else custom_to
    end = custom_to if custom_to >= custom_from else custom_from
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = max(0, (end - start).days)
    if delta <= 45:
        group_by = StatsPeriod.DAY
    elif delta <= 200:
        group_by = StatsPeriod.WEEK
    else:
        group_by = StatsPeriod.MONTH
    return AnalyticsPeriodConfig(
        key="custom",
        date_from=start,
        date_to=end,
        group_by=group_by,
        max_chart_points=36 if delta > 400 else None,
    )


def format_chart_period_label(period: str, group_by: StatsPeriod) -> str:
    """Short x-axis label for chart buckets."""
    if group_by == StatsPeriod.DAY:
        return period[-5:] if len(period) >= 5 else period
    if group_by == StatsPeriod.WEEK:
        if "-W" in period:
            return f"W{period.split('-W', 1)[1]}"
        return period[-3:]
    return period[5:7] if len(period) >= 7 else period


def _parse_period_key(key: str, group_by: StatsPeriod) -> datetime | None:
    try:
        if group_by == StatsPeriod.DAY:
            parsed = datetime.strptime(key, "%Y-%m-%d")
        elif group_by == StatsPeriod.WEEK:
            year_s, week_s = key.split("-W", 1)
            parsed = datetime.fromisocalendar(int(year_s), int(week_s), 1)
        else:
            parsed = datetime.strptime(key, "%Y-%m")
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def enumerate_period_keys(
    cfg: AnalyticsPeriodConfig,
    *,
    existing: Sequence[str] = (),
) -> list[str]:
    """Every bucket in the selected range, including empty days/weeks/months."""
    start = cfg.date_from
    end = cfg.date_to
    if start is None:
        parsed = [_parse_period_key(key, cfg.group_by) for key in existing]
        known = [item for item in parsed if item is not None]
        if not known:
            return list(existing)
        start = min(known)
    keys: list[str] = []
    cursor = start
    guard = 0
    while cursor <= end and guard < 4000:
        key = GetTransactionStatsUseCase._period_key(cursor, cfg.group_by)
        if not keys or keys[-1] != key:
            keys.append(key)
        cursor = cursor + timedelta(days=1)
        guard += 1
    return keys


def fill_time_series(
    by_period: Sequence[tuple[str, Decimal, Decimal]],
    keys: Sequence[str],
) -> list[tuple[str, Decimal, Decimal]]:
    """Insert zero income/expense for buckets that had no operations."""
    zero = Decimal("0.00")
    lookup = {key: (income, expense) for key, income, expense in by_period}
    return [
        (key, lookup[key][0], lookup[key][1]) if key in lookup else (key, zero, zero)
        for key in keys
    ]


def cumulative_net(
    series: Sequence[tuple[str, Decimal, Decimal]],
) -> list[Decimal]:
    """Running net for the period: income lifts the line, expense drops it."""
    running = Decimal("0")
    out: list[Decimal] = []
    for _key, income, expense in series:
        running += Decimal(str(income)) - Decimal(str(expense))
        out.append(running)
    return out
