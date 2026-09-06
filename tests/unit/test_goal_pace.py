"""Unit tests for flexible goal pace helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from lib.domain.entities.money import quantize_money
from lib.domain.use_cases.goal_insights import (
    required_monthly_for_goal,
    required_pace_for_goal,
)


def test_pace_uses_daily_for_short_deadline() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    remaining = Decimal("300")
    pace = required_pace_for_goal(
        remaining, now + timedelta(days=3), now=now
    )
    assert pace is not None
    assert pace.unit == "day"
    assert pace.amount == quantize_money(Decimal("100"))


def test_pace_uses_weekly_for_two_weeks() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    remaining = Decimal("700")
    pace = required_pace_for_goal(
        remaining, now + timedelta(days=14), now=now
    )
    assert pace is not None
    assert pace.unit == "week"
    assert pace.amount == quantize_money(Decimal("350"))


def test_pace_uses_monthly_for_long_deadline() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    remaining = Decimal("1000")
    pace = required_pace_for_goal(
        remaining, now + timedelta(days=120), now=now
    )
    assert pace is not None
    assert pace.unit == "month"
    monthly = required_monthly_for_goal(
        remaining, now + timedelta(days=120), now=now
    )
    assert monthly == pace.amount


def test_pace_overdue_is_total() -> None:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    remaining = Decimal("50")
    pace = required_pace_for_goal(
        remaining, now - timedelta(days=1), now=now
    )
    assert pace is not None
    assert pace.unit == "total"
    assert pace.amount == quantize_money(remaining)
