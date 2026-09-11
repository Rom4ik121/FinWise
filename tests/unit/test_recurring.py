"""Recurring template date math."""

from __future__ import annotations

from datetime import date

from lib.domain.entities.recurring_rule import RecurringInterval, RecurringRule
from lib.domain.use_cases.recurring import advance_recurring_date, preview_recurring_dates
from lib.presentation.money_input import parse_amount


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


def test_recurring_rule_accepts_parsed_template_amount() -> None:
    """QA: monthly template save must accept a typed ``10`` (ru grouped field)."""
    rule = RecurringRule(
        name="QA monthly",
        amount=parse_amount("10"),
        account_id="acc-1",
        interval=RecurringInterval.MONTHLY,
        interval_count=1,
    )
    assert rule.amount == parse_amount("10")
    assert rule.interval is RecurringInterval.MONTHLY
