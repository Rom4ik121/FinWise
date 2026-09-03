"""Budget pace, month shift, and spend buckets."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.services.rate_book import RateBook
from lib.domain.use_cases.budget_insights import (
    bucket_spend_by_month,
    budget_pace,
    shift_month,
)


def test_shift_month() -> None:
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)
    assert shift_month(2026, 9, -3) == (2026, 6)


def test_budget_pace_future_and_past() -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    future = budget_pace(
        spent=Decimal("0"),
        limit=Decimal("100"),
        month=10,
        year=2026,
        now=now,
    )
    assert future.days_elapsed == 0
    assert future.on_track is True

    past = budget_pace(
        spent=Decimal("80"),
        limit=Decimal("100"),
        month=8,
        year=2026,
        now=now,
    )
    assert past.days_elapsed == past.days_in_month
    assert past.days_left == 0


def test_budget_pace_mid_month() -> None:
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    pace = budget_pace(
        spent=Decimal("60"),
        limit=Decimal("90"),
        month=9,
        year=2026,
        now=now,
    )
    assert pace.days_elapsed == 15
    assert pace.days_in_month == 30
    assert pace.expected_spent == Decimal("45.00")
    assert pace.on_track is False
    assert pace.daily_allowance == Decimal("2.00")


def test_bucket_spend_converts_and_skips_missing_rate() -> None:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    usd = Transaction(
        account_id="a",
        amount=Decimal("10"),
        category="Food",
        date=now,
        type=TransactionType.EXPENSE,
        currency="USD",
    )
    eur = Transaction(
        account_id="a",
        amount=Decimal("5"),
        category="Food",
        date=now,
        type=TransactionType.EXPENSE,
        currency="EUR",
    )
    book = RateBook.from_pairs({("USD", "RUB"): Decimal("100")})
    buckets = bucket_spend_by_month(
        [usd, eur],
        category="Food",
        months=1,
        now=now,
        rate_book=book,
        to_currency="RUB",
    )
    assert buckets == [("2026-06", Decimal("1000.00"))]
