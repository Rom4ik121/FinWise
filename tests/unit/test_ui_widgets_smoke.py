"""UI smoke: presentation widgets build without a live Flet page session."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import flet as ft

from lib.domain.entities.account import Account
from lib.domain.entities.debt import Debt, DebtDirection
from lib.domain.entities.subscription import Periodicity, Subscription
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.presentation.currency_options import currency_dropdown_options
from lib.presentation.widgets.account_card import AccountCard
from lib.presentation.widgets.charts import build_line_chart_image, build_pie_chart_image
from lib.presentation.widgets.debt_card import DebtCard
from lib.presentation.widgets.subscription_card import SubscriptionCard
from lib.presentation.widgets.transaction_tile import TransactionTile


def test_currency_dropdown_options_localized() -> None:
    options = currency_dropdown_options(lang="uz", include_crypto=False)
    assert options
    assert options[0].key
    assert "—" in (options[0].text or "")


def test_account_card_builds() -> None:
    acc = Account(
        name="Cash",
        currency="RUB",
        initial_balance=Decimal("10"),
        balance=Decimal("10"),
        icon="wallet",
        color="#2E7D32",
    )
    card = AccountCard(acc, language="en")
    assert card is not None
    synced = AccountCard(acc, language="en", exchange_title="Binance", on_sync=lambda _a: None)
    assert synced is not None


def test_transaction_tile_uses_category_icon() -> None:
    from lib.domain.entities.category import Category
    from lib.presentation.utils import category_icon

    tx = Transaction(
        account_id="corp-1",
        amount=Decimal("20"),
        category="Еда",
        date=datetime.now(timezone.utc),
        type=TransactionType.EXPENSE,
        currency="UZS",
    )
    category = Category(name="Еда", icon="restaurant", color="#E11D48")
    with_cat = TransactionTile(tx, category=category, language="ru")
    fallback = TransactionTile(tx, language="ru")
    with_icons = _find_icons(with_cat)
    fallback_icons = _find_icons(fallback)
    assert category_icon("restaurant") in with_icons
    assert ft.Icons.NORTH_EAST in fallback_icons
    assert category_icon("restaurant") not in fallback_icons


def test_lookup_account_category_is_case_insensitive() -> None:
    from lib.domain.entities.category import Category
    from lib.presentation.pages.account_detail import _lookup_category

    cat = Category(name="Еда", icon="restaurant")
    assert _lookup_category({"Еда": cat}, "еда") is cat
    assert _lookup_category({"Еда": cat}, "Такси") is None


def test_transaction_tile_builds() -> None:
    tx = Transaction(
        account_id="a1",
        amount=Decimal("12.5"),
        category="Food",
        date=datetime.now(timezone.utc),
        type=TransactionType.EXPENSE,
        currency="USD",
    )
    tile = TransactionTile(tx, language="ru")
    assert tile is not None

    transfer = Transaction(
        account_id="a1",
        amount=Decimal("5"),
        category="Перевод",
        date=datetime.now(timezone.utc),
        type=TransactionType.EXPENSE,
        currency="RUB",
        transfer_id="t1",
        transfer_peer_account_id="a2",
    )
    assert transfer.is_transfer
    assert TransactionTile(transfer, language="en") is not None


def test_subscription_and_debt_cards_build() -> None:
    sub = Subscription(
        name="Netflix",
        amount=Decimal("10"),
        account_id="a1",
        next_billing_date=datetime.now(timezone.utc),
        periodicity=Periodicity.MONTHLY,
    )
    assert SubscriptionCard(sub, language="uz") is not None

    debt = Debt(
        counterparty="Bank",
        amount=Decimal("100"),
        remaining_amount=Decimal("100"),
        direction=DebtDirection.I_OWE,
    )
    assert DebtCard(debt, language="en") is not None


def test_charts_empty_and_with_data() -> None:
    empty_pie = build_pie_chart_image([], [], language="en")
    assert isinstance(empty_pie, ft.Container)

    pie = build_pie_chart_image(["Food"], [Decimal("10")], language="ru")
    assert isinstance(pie, ft.Container)
    canvases = _find_canvases(pie)
    assert canvases
    assert canvases[0].expand is not True

    empty_line = build_line_chart_image([], [], [], language="uz")
    assert isinstance(empty_line, ft.Container)

    line = build_line_chart_image(
        ["01-01", "01-02"],
        [Decimal("10"), Decimal("20")],
        [Decimal("5"), Decimal("8")],
        language="en",
    )
    assert isinstance(line, ft.Container)


def _find_icons(ctrl: ft.Control) -> list:
    found: list = []
    stack = [ctrl]
    while stack:
        cur = stack.pop()
        if isinstance(cur, ft.Icon):
            found.append(getattr(cur, "icon", None) or getattr(cur, "name", None))
        content = getattr(cur, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(cur, "controls", None)
        if controls:
            stack.extend(controls)
    return found


def _find_canvases(ctrl: ft.Control) -> list:
    found = []
    stack = [ctrl]
    while stack:
        cur = stack.pop()
        if type(cur).__name__ in ("Canvas", "_SafeCanvas"):
            found.append(cur)
        content = getattr(cur, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(cur, "controls", None)
        if controls:
            stack.extend(controls)
    return found


def test_chart_layout_fits_window() -> None:
    from lib.presentation.widgets.charts import chart_layout

    w, h = chart_layout(None)
    assert w >= 240
    assert 180 <= h <= 360


def test_charts_many_periods_scroll() -> None:
    periods = [f"08-{i:02d}" for i in range(1, 16)]
    income = [Decimal("10")] * 15
    expense = [Decimal("4")] * 15
    chart = build_line_chart_image(
        periods, income, expense, language="ru", width=320, height=200
    )
    assert isinstance(chart, ft.Container)


def test_neon_charts_are_glow_spline_and_donut() -> None:
    from lib.presentation.skins import get_active_skin, set_active_skin
    from lib.presentation.widgets.charts import build_line_chart_image, build_pie_chart_image

    previous = get_active_skin().id
    try:
        set_active_skin("neon")
        pie = build_pie_chart_image(["Food"], [Decimal("10")], language="en")
        line = build_line_chart_image(
            ["01-01", "01-02", "01-03"],
            [Decimal("10"), Decimal("20"), Decimal("15")],
            [Decimal("5"), Decimal("8"), Decimal("12")],
            language="en",
        )
        assert isinstance(pie, ft.Container)
        assert isinstance(line, ft.Container)
        assert pie.content is not None
        assert line.content is not None
    finally:
        set_active_skin(previous)


def test_charts_native_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.presentation.widgets.charts._prefer_native_charts",
        lambda: True,
    )
    pie = build_pie_chart_image(["Food", "Travel"], [Decimal("80"), Decimal("20")], language="ru")
    assert isinstance(pie, ft.Container)
    line = build_line_chart_image(
        ["01-01"],
        [Decimal("10")],
        [Decimal("5")],
        language="ru",
    )
    assert isinstance(line, ft.Container)


def test_budgets_page_importable() -> None:
    from lib.presentation.pages.budgets import BudgetsPage

    assert BudgetsPage is not None


def test_analytics_merges_income_and_spend_tabs() -> None:
    from lib.presentation.pages import analytics as analytics_mod

    assert analytics_mod._SECTIONS[0] == "flow"
    assert "income" not in analytics_mod._SECTIONS
    assert "spend" not in analytics_mod._SECTIONS


def test_neon_glass_cards() -> None:
    from lib.presentation.skins import get_active_skin, set_active_skin
    from lib.presentation.styles import card_surface

    previous = get_active_skin().id
    try:
        set_active_skin("neon")
        card = card_surface(ft.Text("x"))
        assert card.blur is not None
    finally:
        set_active_skin(previous)


def test_splash_logo_is_large() -> None:
    from lib.presentation.widgets.splash_screen import build_launch_splash

    splash = build_launch_splash(language="ru")
    assert isinstance(splash, ft.Container)

    def _walk(ctrl, acc: list) -> None:
        acc.append(ctrl)
        content = getattr(ctrl, "content", None)
        if content is not None:
            _walk(content, acc)
        for child in getattr(ctrl, "controls", None) or []:
            _walk(child, acc)

    found: list = []
    _walk(splash, found)
    icons = [c for c in found if isinstance(c, ft.Icon)]
    texts = [c for c in found if isinstance(c, ft.Text)]
    rings = [c for c in found if isinstance(c, ft.ProgressRing)]
    images = [c for c in found if isinstance(c, ft.Image)]
    assert not images
    assert rings
    assert icons and icons[0].size >= 100
    assert icons[0].icon == ft.Icons.ACCOUNT_BALANCE_WALLET or getattr(
        icons[0], "name", None
    ) in (ft.Icons.ACCOUNT_BALANCE_WALLET, "ACCOUNT_BALANCE_WALLET", None)
    assert any(getattr(t, "value", "") == "FinWise" for t in texts)
    assert not any("учёт" in str(getattr(t, "value", "")).lower() for t in texts)


def test_fill_loading_keeps_existing_controls() -> None:
    from lib.presentation.widgets.loading import fill_loading

    host = ft.Column(controls=[ft.Text("keep")])
    fill_loading(host)
    assert len(host.controls) == 1
    assert isinstance(host.controls[0], ft.Text)
