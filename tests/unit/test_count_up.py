"""Unit tests for money count-up helpers."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.count_up import _format, mark_money_text


def test_mark_money_text_stores_meta() -> None:
    text = ft.Text("x")
    mark_money_text(text, Decimal("12.5"), currency="UZS", compact=True, signed=True)
    assert isinstance(text.data, dict)
    assert text.data["count_up"] is True
    assert text.data["amount"] == "12.5"
    assert text.data["currency"] == "UZS"
    assert text.data["compact"] is True
    assert text.data["signed"] is True


def test_figure_only_keeps_full_amount() -> None:
    meta = {
        "currency": "UZS",
        "compact": False,
        "signed": False,
        "figure_only": True,
    }
    shown = _format(meta, Decimal("8700000"))
    assert "M" not in shown
    assert "8 700 000" in shown


def test_figure_only_compact_abbreviates() -> None:
    meta = {
        "currency": "UZS",
        "compact": True,
        "signed": False,
        "figure_only": True,
    }
    shown = _format(meta, Decimal("8700000"))
    assert "M" in shown


def test_format_starts_from_zero_shape() -> None:
    meta = {
        "currency": "USD",
        "compact": False,
        "signed": False,
        "figure_only": False,
    }
    zero = _format(meta, Decimal("0"))
    full = _format(meta, Decimal("100.00"))
    assert "USD" in zero
    assert "USD" in full
    assert zero != full
