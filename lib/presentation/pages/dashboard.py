"""Home dashboard — balance, quick add, analytics entry, shortcuts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.transaction import TransactionType
from lib.presentation.notification_badges import (
    BUDGET_ALERT_KINDS,
    DEBT_ALERT_KINDS,
    GOAL_ALERT_KINDS,
    SUBSCRIPTION_ALERT_KINDS,
    pending_counts,
)
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import (
    card_surface,
    muted_text,
    page_header,
    section_title,
    shortcut_chip,
)
from lib.presentation.utils import (
    format_money,
    format_money_compact,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    tr,
)
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.widgets.charts import build_line_chart_image
from lib.presentation.widgets.dual_add_button import dual_add_button
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.layout import make_v_scroll
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.quick_add_sheet import open_quick_add

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_CHART_DAYS = 30
_CHART_PERIODS = (7, 30, 90, 365)
_HIDDEN_MONEY = "••••••"
_HIDDEN_SMALL = "••••"


class DashboardPage(ft.Column):
    """Total balance, quick actions, and section shortcuts."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._body = make_v_scroll(spacing=12)
        self._token = -1
        self._hide_balance = False
        prefs = state.settings
        self._hide_chart = bool(getattr(prefs, "dashboard_hide_chart", False))
        days = int(getattr(prefs, "dashboard_chart_days", None) or _CHART_DAYS)
        self._chart_days = days if days in _CHART_PERIODS else _CHART_DAYS
        self._sections_open = True
        self._balance_cache: dict = {}
        super().__init__(
            expand=True,
            spacing=0,
            controls=[
                page_header(
                    tr("nav.home", state.language),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: run_async(page, self.reload),
                        ),
                    ],
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=12),
                    content=self._body,
                ),
            ],
        )
        state.subscribe(self._on_state)
        run_async(page, self.reload)

    def _on_state(self, state: "AppState") -> None:
        if state.dashboard_token != self._token:
            run_async(self._page, self.reload)

    async def _total_in_base(self, accounts: list, base: str) -> tuple[Decimal, bool]:
        """Convert account balances into ``base`` currency.

        Skips accounts with ``include_in_total=False`` (home total only).
        """
        base = normalize_currency_code(base)
        book = await load_rate_book(self._state.container)
        total = Decimal("0.00")
        ok = True
        for account in accounts:
            if not getattr(account, "include_in_total", True):
                continue
            src = normalize_currency_code(account.currency)
            converted = book.convert(account.balance, src, base)
            if converted is not None:
                total += converted
            elif src == base:
                total += account.balance
            else:
                ok = False
        return total, ok

    async def _cashflow_month(
        self, base: str, *, days: int = _CHART_DAYS
    ) -> tuple[Decimal, Decimal, list[str], list[Decimal], list[Decimal], bool]:
        """Today income/expense + series for the last ``days`` (base FX).

        Day boundaries use the **local** calendar. Buckets stay ≤36 points.
        Returns ``fx_ok=False`` when any tx was skipped for a missing rate.
        """
        base = normalize_currency_code(base)
        book = await load_rate_book(self._state.container)
        local_now = datetime.now().astimezone()
        today_local = local_now.date()
        period_start_local = today_local - timedelta(days=days - 1)
        tz = local_now.tzinfo
        period_start = datetime(
            period_start_local.year,
            period_start_local.month,
            period_start_local.day,
            tzinfo=tz,
        ).astimezone(timezone.utc)
        period_end = datetime(
            today_local.year,
            today_local.month,
            today_local.day,
            tzinfo=tz,
        ).astimezone(timezone.utc) + timedelta(days=1)
        # Cap point count so the compact home chart stays readable.
        max_buckets = 36
        bucket = 7 if days > 90 else 1
        if days > max_buckets:
            bucket = max(bucket, (days + max_buckets - 1) // max_buckets)
        bucket_count = max(1, (days + bucket - 1) // bucket)
        day_keys = [
            (period_start_local + timedelta(days=i)).isoformat() for i in range(days)
        ]
        by_income_day = {k: Decimal("0.00") for k in day_keys}
        by_expense_day = {k: Decimal("0.00") for k in day_keys}
        today_income = Decimal("0.00")
        today_expense = Decimal("0.00")
        today_key = today_local.isoformat()
        fx_ok = True
        list_uc = getattr(self._state.container, "list_transactions", None)
        if list_uc is not None:
            try:
                txs = await list_uc.execute(
                    date_from=period_start,
                    date_to=period_end,
                    has_transfer=False,
                )
            except Exception:  # noqa: BLE001
                txs = []
            for tx in txs:
                if getattr(tx, "transfer_id", None):
                    continue
                when = tx.date
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                key = when.astimezone(tz).date().isoformat()
                if key not in by_income_day:
                    continue
                src = normalize_currency_code(tx.currency or base)
                converted = book.convert(tx.amount, src, base)
                if converted is None:
                    if src == base:
                        converted = tx.amount
                    else:
                        fx_ok = False
                        continue
                if tx.type == TransactionType.INCOME:
                    by_income_day[key] += converted
                    if key == today_key:
                        today_income += converted
                elif tx.type == TransactionType.EXPENSE:
                    by_expense_day[key] += converted
                    if key == today_key:
                        today_expense += converted

        incomes: list[Decimal] = []
        expenses: list[Decimal] = []
        labels: list[str] = []
        for b in range(bucket_count):
            start_i = b * bucket
            chunk = day_keys[start_i : start_i + bucket]
            if not chunk:
                continue
            inc = sum((by_income_day[k] for k in chunk), Decimal("0.00"))
            exp = sum((by_expense_day[k] for k in chunk), Decimal("0.00"))
            incomes.append(inc)
            expenses.append(exp)
            label_key = chunk[0]
            if days > 90:
                labels.append(label_key[5:])  # MM-DD
            elif b == 0 or b == bucket_count - 1 or b % max(1, bucket_count // 5) == 0:
                labels.append(label_key[8:] if bucket == 1 else label_key[5:])
            else:
                labels.append("")
        return today_income, today_expense, labels, incomes, expenses, fx_ok

    def _toggle_balance(self, _e: ft.ControlEvent | None = None) -> None:
        self._hide_balance = not self._hide_balance
        self._render_from_cache()

    def _toggle_chart(self, _e: ft.ControlEvent | None = None) -> None:
        self._hide_chart = not self._hide_chart
        self._render_from_cache()
        run_async(self._page, self._persist_chart_prefs)

    async def _persist_chart_prefs(self) -> None:
        """Save chart visibility and period so they survive app restart."""
        try:
            current = self._state.settings
            updated = current.model_copy(
                update={
                    "dashboard_hide_chart": bool(self._hide_chart),
                    "dashboard_chart_days": int(self._chart_days),
                }
            )
            saved = await self._state.container.update_settings.execute(updated)
            self._state.settings = saved
        except Exception:  # noqa: BLE001
            pass

    def _toggle_sections(self, _e: ft.ControlEvent | None = None) -> None:
        self._sections_open = not self._sections_open
        self._render_from_cache()

    def _open_chart_period(self, _e: ft.ControlEvent | None = None) -> None:
        lang = self._state.language
        period_dd = ft.Dropdown(
            label=tr("dashboard.chart_period", lang),
            value=str(self._chart_days),
            options=[
                ft.DropdownOption(
                    key="7", text=tr("dashboard.chart_period.week", lang)
                ),
                ft.DropdownOption(
                    key="30", text=tr("dashboard.chart_period.month", lang)
                ),
                ft.DropdownOption(
                    key="90", text=tr("dashboard.chart_period.quarter", lang)
                ),
                ft.DropdownOption(
                    key="365", text=tr("dashboard.chart_period.year", lang)
                ),
            ],
            expand=True,
        )

        async def _apply() -> None:
            try:
                days = int(period_dd.value or self._chart_days)
            except ValueError:
                days = _CHART_DAYS
            if days not in _CHART_PERIODS:
                days = _CHART_DAYS
            self._chart_days = days
            close()
            await self._persist_chart_prefs()
            await self.reload()

        from lib.presentation.widgets.fullscreen_form import open_fullscreen_form

        close = open_fullscreen_form(
            self._page,
            title=tr("dashboard.chart_period", lang),
            lang=lang,
            overlay_key="dashboard_chart_period",
            body=[
                muted_text(tr("dashboard.chart_period_hint", lang), size=12),
                period_dd,
            ],
            on_save=_apply,
            save_label=tr("action.apply", lang, default=tr("action.save", lang)),
        )

    def _render_from_cache(self) -> None:
        cache = self._balance_cache
        if not cache:
            return
        self._body.controls = cache["build"]()
        safe_update(self._body)

    @staticmethod
    def _abbrev_today_amount(amount: Decimal, currency: str) -> tuple[str, str, bool]:
        """Return (display, full, abbreviated) for the today KPI boxes."""
        full = format_money(amount, currency)
        if abs(amount) >= Decimal("10000") or len(full) > 14:
            return format_money_compact(amount, currency), full, True
        return full, full, False

    def _today_box(
        self,
        *,
        label: str,
        amount: Decimal,
        currency: str,
        color: str,
        hidden: bool,
    ) -> ft.Control:
        if hidden:
            display = _HIDDEN_SMALL
            on_tap = None
            tip = None
        else:
            display, full, abbreviated = self._abbrev_today_amount(amount, currency)

            def on_tap(_e: ft.ControlEvent | None = None, *, _full: str = full) -> None:
                from lib.presentation.haptics import haptic

                haptic("selection")
                snack(self._page, _full)

            tip = (
                tr("dashboard.today_amount_tap", self._state.language)
                if abbreviated
                else full
            )
            if not abbreviated:
                on_tap = None
        return ft.Container(
            expand=True,
            ink=on_tap is not None,
            on_click=on_tap,
            tooltip=tip,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.22, ft.Colors.SURFACE),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        label,
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        display,
                        size=13,
                        weight=ft.FontWeight.W_700,
                        color=color,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def _balance_panel(
        self,
        lang: str,
        total: Decimal,
        base: str,
        today_income: Decimal,
        today_expense: Decimal,
        periods: list[str],
        incomes: list[Decimal],
        expenses: list[Decimal],
    ) -> ft.Control:
        skin = get_active_skin()
        hidden = self._hide_balance
        balance_txt = _HIDDEN_MONEY if hidden else format_money(total, base)
        eye_icon = ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY
        zeros = [Decimal("0")] * max(len(incomes), 1)
        panel_controls: list[ft.Control] = [
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=28,
                        height=28,
                        border_radius=8,
                        bgcolor=skin.badge_bg(dark=True),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(
                            ft.Icons.ACCOUNT_BALANCE_WALLET,
                            size=15,
                            color=skin.badge_fg(dark=True),
                        ),
                    ),
                    ft.Text(
                        tr("dashboard.total_balance", lang),
                        size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=eye_icon,
                        icon_size=20,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT,
                        tooltip=tr(
                            "dashboard.hide_balance"
                            if not hidden
                            else "dashboard.show_balance",
                            lang,
                        ),
                        on_click=self._toggle_balance,
                        style=ft.ButtonStyle(padding=4),
                    ),
                ],
            ),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        balance_txt,
                        size=20,
                        weight=ft.FontWeight.W_700,
                        color=skin.text_hex(dark=True),
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=(
                            ft.Icons.SHOW_CHART
                            if self._hide_chart
                            else ft.Icons.EXPAND_LESS
                        ),
                        icon_size=18,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT,
                        tooltip=tr(
                            "dashboard.show_chart"
                            if self._hide_chart
                            else "dashboard.hide_chart",
                            lang,
                        ),
                        on_click=self._toggle_chart,
                        style=ft.ButtonStyle(padding=2),
                    ),
                ],
            ),
            ft.Row(
                spacing=8,
                controls=[
                    self._today_box(
                        label=tr("dashboard.today_income", lang),
                        amount=today_income,
                        currency=base,
                        color=ft.Colors.SECONDARY,
                        hidden=hidden,
                    ),
                    self._today_box(
                        label=tr("dashboard.today_expense", lang),
                        amount=today_expense,
                        currency=base,
                        color=ft.Colors.ERROR,
                        hidden=hidden,
                    ),
                ],
            ),
        ]
        if not self._hide_chart:
            page_w = getattr(self._page, "width", None) or 360
            try:
                chart_w = max(280, int(page_w) - 48)
            except (TypeError, ValueError):
                chart_w = 320
            chart = build_line_chart_image(
                periods,
                incomes if not hidden else zeros,
                expenses if not hidden else zeros,
                width=chart_w,
                height=136,
                language=lang,
                dark=True,
                show_income=True,
                show_expense=True,
                page=self._page,
                compact=True,
                animate=False,
            )
            panel_controls.append(
                ft.Container(
                    ink=True,
                    on_click=self._open_chart_period,
                    border_radius=12,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    tooltip=tr("dashboard.chart_period_hint", lang),
                    content=chart,
                )
            )
        return ft.Container(
            padding=12,
            border_radius=skin.hero_radius,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            gradient=skin.hero_gradient(dark=True),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=12,
                color=skin.glow,
                offset=ft.Offset(0, 3),
            ),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=panel_controls,
            ),
        )

    def _sections_panel(
        self,
        lang: str,
        *,
        goals_badge: int,
        debts_badge: int,
        subs_badge: int,
        budgets_badge: int,
    ) -> ft.Control:
        chevron = (
            ft.Icons.KEYBOARD_ARROW_DOWN
            if self._sections_open
            else ft.Icons.KEYBOARD_ARROW_UP
        )
        header = ft.Container(
            ink=True,
            on_click=self._toggle_sections,
            padding=ft.Padding.symmetric(vertical=4),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        tr("dashboard.shortcuts", lang),
                        size=15,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.ON_SURFACE,
                        expand=True,
                    ),
                    ft.Icon(chevron, size=22, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
            ),
        )
        body = ft.Column(
            spacing=8,
            visible=self._sections_open,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        shortcut_chip(
                            tr("nav.goals", lang),
                            ft.Icons.FLAG_OUTLINED,
                            badge=goals_badge,
                            on_click=lambda _e: self._state.open_secondary("goals"),
                        ),
                        shortcut_chip(
                            tr("nav.debts", lang),
                            ft.Icons.CREDIT_SCORE,
                            badge=debts_badge,
                            on_click=lambda _e: self._state.open_secondary("debts"),
                        ),
                    ],
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        shortcut_chip(
                            tr("nav.subscriptions", lang),
                            ft.Icons.EVENT_REPEAT,
                            badge=subs_badge,
                            on_click=lambda _e: self._state.open_secondary(
                                "subscriptions"
                            ),
                        ),
                        shortcut_chip(
                            tr("nav.currencies", lang),
                            ft.Icons.CURRENCY_EXCHANGE,
                            on_click=lambda _e: self._state.open_secondary(
                                "currencies"
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        shortcut_chip(
                            tr("nav.budgets", lang),
                            ft.Icons.PIE_CHART,
                            badge=budgets_badge,
                            on_click=lambda _e: self._state.open_secondary(
                                "budgets"
                            ),
                        ),
                    ],
                ),
            ],
        )
        return ft.Column(spacing=8, tight=True, controls=[header, body])

    def _analytics_button(self, lang: str) -> ft.Container:
        """Full-width entry to the analytics secondary screen."""
        return ft.Container(
            height=52,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            shadow=ft.BoxShadow(
                blur_radius=14,
                color="#00000033",
                offset=ft.Offset(0, 4),
            ),
            ink=True,
            on_click=lambda _e: self._state.open_secondary("analytics"),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=10,
                        tight=True,
                        controls=[
                            ft.Container(
                                width=32,
                                height=32,
                                border_radius=10,
                                bgcolor=get_active_skin().badge_bg(dark=True),
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(
                                    ft.Icons.INSIGHTS,
                                    size=18,
                                    color=get_active_skin().badge_fg(dark=True),
                                ),
                            ),
                            ft.Text(
                                tr("nav.analytics", lang),
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.ON_SURFACE,
                            ),
                        ],
                    ),
                    ft.Icon(
                        ft.Icons.CHEVRON_RIGHT,
                        size=22,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            ),
        )

    async def reload(self) -> None:
        """Reload dashboard data from use cases."""
        self._token = self._state.dashboard_token
        lang = self._state.language
        fill_loading(self._body, message=tr("action.refresh", lang))
        c = self._state.container
        try:
            accounts = await c.list_accounts.execute(active_only=True)
        except Exception as exc:  # noqa: BLE001
            snack(self._page, str(exc), error=True)
            self._body.controls = [
                EmptyState(tr("error.generic", lang), icon=ft.Icons.ERROR_OUTLINE)
            ]
            safe_update(self._body)
            return
        base = normalize_currency_code(self._state.base_currency)
        total, fx_ok = await self._total_in_base(accounts, base)
        if not fx_ok and c.update_exchange_rates is not None:
            try:
                await c.update_exchange_rates.execute(base=base)
                from lib.presentation.utils import invalidate_rate_book_cache

                invalidate_rate_book_cache()
                total, fx_ok = await self._total_in_base(accounts, base)
            except Exception:  # noqa: BLE001
                pass
        if not fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)
        (
            today_income,
            today_expense,
            periods,
            incomes,
            expenses,
            cashflow_fx_ok,
        ) = await self._cashflow_month(base, days=self._chart_days)
        if not cashflow_fx_ok and fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)
        settings = self._state.settings
        badges = pending_counts(
            c,
            settings,
            {
                "goals": GOAL_ALERT_KINDS,
                "debts": DEBT_ALERT_KINDS,
                "subs": SUBSCRIPTION_ALERT_KINDS,
                "budgets": BUDGET_ALERT_KINDS,
            },
        )
        goals_badge = badges["goals"]
        debts_badge = badges["debts"]
        subs_badge = badges["subs"]
        budgets_badge = badges["budgets"]
        budget_widget = await self._budgets_widget(lang, base)

        def _build() -> list[ft.Control]:
            return [
                self._balance_panel(
                    lang,
                    total,
                    base,
                    today_income,
                    today_expense,
                    periods,
                    incomes,
                    expenses,
                ),
                dual_add_button(
                    lang,
                    on_expense=lambda: open_quick_add(
                        self._page,
                        self._state,
                        accounts=accounts,
                        default_type=TransactionType.EXPENSE,
                    ),
                    on_income=lambda: open_quick_add(
                        self._page,
                        self._state,
                        accounts=accounts,
                        default_type=TransactionType.INCOME,
                    ),
                ),
                self._analytics_button(lang),
                self._sections_panel(
                    lang,
                    goals_badge=goals_badge,
                    debts_badge=debts_badge,
                    subs_badge=subs_badge,
                    budgets_badge=budgets_badge,
                ),
                budget_widget,
                ft.Container(height=10),
            ]

        self._balance_cache = {"build": _build}
        self._body.controls = _build()
        safe_update(self._body)

    async def _budgets_widget(self, lang: str, currency: str) -> ft.Control:
        """Category budgets for the current month."""
        now = datetime.now(timezone.utc)
        uc = getattr(self._state.container, "get_budgets_for_month", None)
        title = section_title(tr("dashboard.budgets", lang))
        if uc is None:
            return ft.Column(tight=True, spacing=8, controls=[title])
        try:
            items = await uc.execute(now.month, now.year)
        except Exception:  # noqa: BLE001
            items = []
        shown = sorted(items, key=lambda p: p.percent, reverse=True)
        if not shown:
            body: ft.Control = ft.Text(
                tr("dashboard.budgets_empty", lang),
                size=13,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        else:
            rows: list[ft.Control] = []
            for progress in shown:
                percent = progress.percent
                color = ft.Colors.ERROR if percent > 100 else (
                    ft.Colors.AMBER if percent >= 80 else ft.Colors.GREEN
                )
                rows.append(
                    ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        localize_category_name(
                                            progress.category_id, lang
                                        ),
                                        expand=True,
                                        size=13,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(f"{percent:.0f}%", size=13, color=color),
                                ],
                            ),
                            ft.ProgressBar(
                                value=min(float(percent) / 100.0, 1.0),
                                color=color,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            ),
                        ],
                    )
                )
            body = ft.Column(spacing=10, tight=True, controls=rows)
        return card_surface(
            ft.Column(
                spacing=10,
                tight=True,
                controls=[title, body],
            ),
            ink=True,
            on_click=lambda _e: self._state.open_secondary("budgets"),
        )
