"""Transaction list tile sizing / subtitle helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.domain.entities.transaction import Transaction, TransactionType
from lib.presentation.widgets.transaction_tile import (
    _TILE_HEIGHT,
    _display_tags,
    _is_internal_tag,
    _subtitle_line,
)


def test_internal_tags_hidden() -> None:
    assert _is_internal_tag("fee")
    assert _is_internal_tag("xfer_fee:884ab507-f5a8")
    assert _is_internal_tag("debt_principal")
    assert _is_internal_tag("debt_interest:1.50")
    assert _is_internal_tag("binance:fee:abc")
    assert not _is_internal_tag("food")
    assert not _is_internal_tag("vacation")


def test_display_tags_filters_system() -> None:
    assert _display_tags(["fee", "xfer_fee:x", "lunch", "trip"]) == ["#lunch", "#trip"]


def test_subtitle_skips_duplicate_category_and_ids() -> None:
    tx = Transaction(
        account_id="a",
        amount=Decimal("500"),
        category="Комиссия",
        tags=["fee", "xfer_fee:884ab507-f5a8-430b-8c2f-c434852342de"],
        comment="Комиссия · → Долоры",
        type=TransactionType.EXPENSE,
        currency="UZS",
        date=datetime(2026, 8, 31, 11, 18, tzinfo=timezone.utc),
    )
    line = _subtitle_line(tx, language="ru")
    assert "xfer_fee" not in line
    assert "#fee" not in line
    assert "→ Долоры" in line or "Долоры" in line
    assert line.count("Комиссия") == 0  # title already shows category


def test_tile_height_constant() -> None:
    assert _TILE_HEIGHT == 56
