"""Presentation formatting helpers (no Flet page required)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.presentation.utils import (
    format_date,
    format_money,
    format_money_compact,
    format_money_parts,
    tr,
)


def test_format_money() -> None:
    assert format_money("1234.5", "UZS") == "1 234.50 UZS"
    assert format_money(10, "RUB", signed=True).startswith("+")
    assert "−" in format_money(-5, "RUB", signed=True)


def test_format_money_compact() -> None:
    assert format_money_compact("10590000", "UZS") == "10.6M UZS"
    assert format_money_compact("11664974.07", "UZS") == "11.7M UZS"
    assert format_money_compact("15000", "UZS") == "15K UZS"
    assert format_money_compact("9999.5", "UZS") == "10K UZS"
    assert format_money_compact("2500", "RUB") == "2.5K RUB"
    assert format_money_compact("250", "UZS") == "250 UZS"
    assert format_money_compact("-1074974.07", "UZS").startswith("−")
    assert format_money_compact("2500", "RUB", signed=True).startswith("+")
    figure, code = format_money_parts("2610000", "UZS")
    assert figure == "2.6M"
    assert code == "UZS"


def test_format_date() -> None:
    dt = datetime(2024, 5, 1, 14, 30, tzinfo=timezone.utc)
    assert format_date(dt) == "01.05.2024"
    assert format_date(dt, with_time=True) == "01.05.2024 14:30"
    assert format_date(None) == "—"


def test_tr_format_kwargs() -> None:
    text = tr("subscription.next_billing", "en", date="01.01.2025")
    assert "01.01.2025" in text
    assert tr("nav.home", "uz") == "Bosh sahifa"
    assert tr("analytics.tab.goals", "ru") == "Цели"
    assert tr("analytics.tab.budget", "en") == "Budget"
    assert tr("action.close", "ru") == "Закрыть"
