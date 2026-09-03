"""FX-aware subscription sparkline buckets."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.services.rate_book import RateBook
from lib.domain.use_cases.subscription_insights import bucket_charges_by_month


def test_bucket_converts_and_skips_missing_rate() -> None:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    usd = Transaction(
        account_id="a",
        amount=Decimal("10"),
        category="x",
        date=now,
        type=TransactionType.EXPENSE,
        currency="USD",
        subscription_id="s1",
    )
    eur = Transaction(
        account_id="a",
        amount=Decimal("5"),
        category="x",
        date=now,
        type=TransactionType.EXPENSE,
        currency="EUR",
        subscription_id="s1",
    )
    book = RateBook.from_pairs({("USD", "RUB"): Decimal("100")})
    buckets = bucket_charges_by_month(
        [usd, eur],
        months=1,
        now=now,
        rate_book=book,
        to_currency="RUB",
    )
    assert buckets == [("2026-06", Decimal("1000.00"))]
