"""Presentation formatting helpers (no Flet page required)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.presentation.utils import (
    control_page,
    dropdown_select_kwargs,
    format_date,
    format_money,
    format_money_compact,
    format_money_parts,
    safe_update,
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
    point = tr(
        "chart.point",
        "en",
        period="May",
        income="10",
        expense="4",
        net="6",
    )
    assert "May" in point
    assert "10" in point
    assert tr("nav.home", "uz") == "Bosh sahifa"
    assert tr("analytics.tab.goals", "ru") == "Цели"
    assert tr("analytics.tab.budget", "en") == "Budget"
    assert tr("action.close", "ru") == "Закрыть"


def test_control_page_unmounted_does_not_raise() -> None:
    class Unmounted:
        @property
        def page(self):
            raise RuntimeError("Canvas(1) Control must be added to the page first")

        def update(self) -> None:
            raise AssertionError("unmounted control must not update")

    dummy = Unmounted()
    assert control_page(dummy) is None
    safe_update(dummy)


def test_control_page_mounted() -> None:
    class Mounted:
        page = object()

        def update(self) -> None:
            self.updated = True

    dummy = Mounted()
    assert control_page(dummy) is dummy.page
    safe_update(dummy)
    assert dummy.updated is True


def test_dropdown_select_kwargs_match_flet_api() -> None:
    import flet as ft

    kwargs = dropdown_select_kwargs(lambda _e: None)
    ft.Dropdown(
        label="theme",
        value="dark",
        options=[ft.DropdownOption(key="dark", text="Dark")],
        **kwargs,
    )
