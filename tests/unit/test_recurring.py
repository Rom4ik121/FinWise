"""Recurring template date math."""

from __future__ import annotations

from datetime import date

from lib.domain.entities.recurring_rule import RecurringInterval
from lib.domain.use_cases.recurring import advance_recurring_date, preview_recurring_dates


def test_advance_recurring_date_intervals() -> None:
    start = date(2026, 1, 31)
    assert advance_recurring_date(start, RecurringInterval.DAILY) == date(2026, 2, 1)
    assert advance_recurring_date(start, RecurringInterval.WEEKLY) == date(2026, 2, 7)
    assert advance_recurring_date(start, RecurringInterval.MONTHLY) == date(2026, 2, 28)
    assert advance_recurring_date(start, RecurringInterval.YEARLY) == date(2027, 1, 31)
    assert advance_recurring_date(
        start, RecurringInterval.MONTHLY, interval_count=2
    ) == date(2026, 3, 31)


def test_preview_recurring_dates_includes_start() -> None:
    dates = preview_recurring_dates(
        date(2026, 3, 1), RecurringInterval.MONTHLY, count=3
    )
    assert dates == [
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
    ]
