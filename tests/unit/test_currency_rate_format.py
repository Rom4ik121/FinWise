"""Currency page helpers."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.currency import Currency
from lib.presentation.pages.currencies import (
    _format_rate,
    _matches_query,
    _money_figure_and_code,
    _result_size,
)


def test_format_rate_trims_zeros() -> None:
    assert _format_rate(Decimal("12500.00")) == "12500"
    assert _format_rate(Decimal("0.00080")) == "0.0008"
    assert _format_rate(Decimal("1.25")) == "1.25"


def test_matches_query_by_ticker_name_symbol() -> None:
    usd = Currency(code="USD", name="US Dollar", symbol="$", is_crypto=False)
    assert _matches_query(usd, "")
    assert _matches_query(usd, "usd")
    assert _matches_query(usd, "doll")
    assert _matches_query(usd, "$")
    assert not _matches_query(usd, "btc")


def test_money_figure_keeps_full_amount() -> None:
    figure, code = _money_figure_and_code(Decimal("1234567.89"), "UZS")
    assert code == "UZS"
    assert "1 234 567.89" == figure
    assert "K" not in figure and "M" not in figure


def test_result_size_shrinks_for_long_figures() -> None:
    assert _result_size("12.50") == 22
    assert _result_size("1 234 567.89") == 19
    assert _result_size("12 345 678 901.00") == 16
