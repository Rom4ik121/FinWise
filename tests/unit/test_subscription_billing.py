"""Pure subscription billing date helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from lib.domain.entities.subscription import Periodicity, Subscription
from lib.domain.use_cases.subscriptions import (
    _add_months,
    _advance_billing_date,
    count_missed_periods,
    monthly_equivalent,
    retreat_billing_date,
)


def test_add_months_clamps_day() -> None:
    jan31 = datetime(2024, 1, 31, tzinfo=timezone.utc)
    feb = _add_months(jan31, 1)
    assert feb.month == 2
    assert feb.day == 29  # 2024 leap year


def test_advance_monthly_and_yearly() -> None:
    base = datetime(2024, 5, 15, 12, 0, tzinfo=timezone.utc)
    monthly = _advance_billing_date(base, Periodicity.MONTHLY)
    yearly = _advance_billing_date(base, Periodicity.YEARLY)
    assert monthly == datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
    assert yearly == datetime(2025, 5, 15, 12, 0, tzinfo=timezone.utc)


def test_advance_weekly_custom_quarterly() -> None:
    base = datetime(2024, 5, 15, 12, 0, tzinfo=timezone.utc)
    weekly = _advance_billing_date(base, Periodicity.WEEKLY)
    custom = _advance_billing_date(
        base, Periodicity.CUSTOM, custom_interval_days=10
    )
    quarterly = _advance_billing_date(base, Periodicity.QUARTERLY)
    assert weekly == datetime(2024, 5, 22, 12, 0, tzinfo=timezone.utc)
    assert custom == datetime(2024, 5, 25, 12, 0, tzinfo=timezone.utc)
    assert quarterly == datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc)


def test_monthly_equivalent() -> None:
    assert monthly_equivalent(Decimal("12"), Periodicity.YEARLY) == Decimal("1.00")
    assert monthly_equivalent(Decimal("30"), Periodicity.MONTHLY) == Decimal("30.00")
    assert monthly_equivalent(
        Decimal("10"), Periodicity.CUSTOM, custom_interval_days=10
    ) == Decimal("30.44")


def test_retreat_is_inverse_of_advance() -> None:
    base = datetime(2024, 5, 15, 12, 0, tzinfo=timezone.utc)
    for period in (
        Periodicity.DAILY,
        Periodicity.WEEKLY,
        Periodicity.BIWEEKLY,
        Periodicity.MONTHLY,
        Periodicity.QUARTERLY,
        Periodicity.YEARLY,
    ):
        fwd = _advance_billing_date(base, period)
        back = retreat_billing_date(fwd, period)
        assert back == base


def test_count_missed_periods() -> None:
    due = datetime.now(timezone.utc) - timedelta(days=70)
    sub = Subscription(
        name="X",
        amount=Decimal("10"),
        account_id="a1",
        next_billing_date=due,
        periodicity=Periodicity.MONTHLY,
    )
    missed = count_missed_periods(sub)
    assert missed >= 2
