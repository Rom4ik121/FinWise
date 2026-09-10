"""Home dashboard — balance, quick add, analytics entry, shortcuts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.transaction import TransactionType
from lib.presentation.count_up import flush_chart_draws, mark_money_text, play_count_ups, mark_progress
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import replace_controls, ui_animation
from lib.presentation.haptics import haptic
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
    section_title,
    shortcut_chip,
)
from lib.presentation.utils import (
    format_money,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tappable_compact_money,
    tr,
)
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.category_lookup import index_categories, lookup_category
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.widgets.charts import build_line_chart_image
from lib.presentation.responsive import card_padding, compact_chart_size, fit_font, kpi_card_metrics, scale_size, tap_button_style
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


def _home_budget_bar(percent: float, color: str) -> ft.Control:
    from lib.presentation.ui_motion import is_ui_animating

    clamped = min(float(percent) / 100.0, 1.0)
    animate = is_ui_animating()
    bar = ft.ProgressBar(
        value=0.0 if animate else clamped,
        color=color,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )
    if animate:
        mark_progress(bar, clamped)
    return bar


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
        self._animate_charts = False
        # Stable slots for in-place toggle mutate (avoid full ListView rebuild).
        self._balance_label: ft.Text | None = None
        self._balance_code_label: ft.Text | None = None
        self._eye_btn: ft.IconButton | None = None
        self._chart_btn: ft.IconButton | None = None
        self._today_row: ft.Row | None = None
        self._chart_slot: ft.Container | None = None
        self._sections_body: ft.Column | None = None
        self._sections_chevron: ft.Icon | None = None
        self._sections_hint: ft.Text | None = None
        self._sections_slot: ft.Container | None = None
        self._budget_slot: ft.Container | None = None
        self._add_slot: ft.Container | None = None
        self._slots_ready = False
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.home", state.language),
                    body=self._body,
                    page=page,
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: self._reload_gate.request(True),
                        ),
                    ],
                ),
                page=page,
            )
        )
        state.subscribe(self._on_state)
        self._reload_gate = ReloadGate(page, self, self.reload)
        # First paint without entrance animation — animate only on manual refresh.
        self._reload_gate.request(False)

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    def _open_first_account(self) -> None:
        """Home empty CTA → Accounts tab + create form."""
        self._state.pending_open_account_create = True
        self._state.set_tab(self._state.TAB_ACCOUNTS)

    def _on_state(self, state: "AppState") -> None:
        if state.dashboard_token != self._token:
            self._reload_gate.request()

    async def _total_in_base(self, accounts: list, base: str) -> tuple[Decimal, bool]:
        """Convert account balances into ``base`` currency.

        Skips accounts with ``include_in_total=False`` (home total only).
        """
        from lib.domain.services.ledger_fx import sum_balances_in_base

        book = await load_rate_book(self._state.container)
        return sum_balances_in_base(accounts, base=base, book=book)

    async def _cashflow_month(
        self, base: str, *, days: int = _CHART_DAYS
    ) -> tuple[Decimal, Decimal, list[str], list[Decimal], list[Decimal], bool]:
        """Today income/expense + series for the last ``days`` (base FX).

        Day boundaries use the **local** calendar. Buckets stay ≤36 points.
        Returns ``fx_ok=False`` when any tx was skipped for a missing rate.
        """
        from lib.domain.services.ledger_fx import amount_to_base

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
                from lib.presentation.tx_query import fetch_transactions_paged

                txs = await fetch_transactions_paged(
                    list_uc,
                    date_from=period_start,
                    date_to=period_end,
                    has_transfer=False,
                )
                corporate = await self._state.container.list_accounts.execute(
                    corporate=True
                )
                corporate_ids = {a.id for a in corporate}
            except Exception:  # noqa: BLE001
                txs = []
                corporate_ids = set()
            for tx in txs:
                if getattr(tx, "transfer_id", None):
                    continue
                if getattr(tx, "account_id", None) in corporate_ids:
                    continue
                when = tx.date
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                key = when.astimezone(tz).date().isoformat()
                if key not in by_income_day:
                    continue
                converted = amount_to_base(book, tx.amount, tx.currency or base, base)
                if converted is None:
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
        self._apply_visibility()

    def _toggle_chart(self, _e: ft.ControlEvent | None = None) -> None:
        self._hide_chart = not self._hide_chart
        self._apply_visibility()
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
        haptic("light")
        self._sections_open = not self._sections_open
        self._apply_visibility()

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
            await self.reload(True)

        from lib.presentation.widgets.fullscreen_form import open_fullscreen_form

        close = open_fullscreen_form(
            self._page,
            title=tr("dashboard.chart_period", lang),
            lang=lang,
            overlay_key="dashboard_chart_period",
            body=[
                period_dd,
            ],
            on_save=_apply,
            save_label=tr("action.apply", lang, default=tr("action.save", lang)),
        )

    def _render_from_cache(self) -> None:
        """Full rebuild from last successful load (fallback if slots missing)."""
        cache = self._balance_cache
        if not cache or "build" not in cache:
            return
        replace_controls(self._body, cache["build"](), self._page)

    def _apply_visibility(self, *, animate_chart: bool = False) -> None:
        """Mutate balance/chart/sections slots without rebuilding the ListView."""
        cache = self._balance_cache
        if not self._slots_ready or not cache:
            self._render_from_cache()
            return
        lang = str(cache.get("lang") or self._state.language)
        total = cache.get("total", Decimal("0"))
        base = str(cache.get("base") or self._state.base_currency)
        today_income = cache.get("today_income", Decimal("0"))
        today_expense = cache.get("today_expense", Decimal("0"))
        periods = cache.get("periods") or []
        incomes = cache.get("incomes") or []
        expenses = cache.get("expenses") or []
        hidden = self._hide_balance

        if self._balance_label is not None:
            if hidden:
                self._balance_label.value = _HIDDEN_MONEY
                data = getattr(self._balance_label, "data", None)
                if isinstance(data, dict):
                    data.pop("count_up", None)
            else:
                figure = format_money(total, base).rsplit(" ", 1)[0]
                self._balance_label.value = figure
                mark_money_text(
                    self._balance_label, total, currency=base, figure_only=True
                )
            safe_update(self._balance_label)
        if getattr(self, "_balance_code_label", None) is not None:
            self._balance_code_label.value = "" if hidden else base
            self._balance_code_label.visible = not hidden
            safe_update(self._balance_code_label)

        if self._eye_btn is not None:
            self._eye_btn.icon = (
                ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY
            )
            self._eye_btn.tooltip = tr(
                "dashboard.hide_balance" if not hidden else "dashboard.show_balance",
                lang,
            )
            safe_update(self._eye_btn)

        if self._today_row is not None:
            self._today_row.controls = [
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
            ]
            safe_update(self._today_row)

        if self._chart_btn is not None:
            self._chart_btn.icon = (
                ft.Icons.SHOW_CHART if self._hide_chart else ft.Icons.EXPAND_LESS
            )
            self._chart_btn.tooltip = tr(
                "dashboard.show_chart" if self._hide_chart else "dashboard.hide_chart",
                lang,
            )
            safe_update(self._chart_btn)

        if self._chart_slot is not None:
            self._chart_slot.visible = not self._hide_chart
            if not self._hide_chart:
                zeros = [Decimal("0")] * max(len(incomes), 1)
                chart_w, chart_h = compact_chart_size(self._page)
                self._chart_slot.content = build_line_chart_image(
                    periods,
                    incomes if not hidden else zeros,
                    expenses if not hidden else zeros,
                    width=chart_w,
                    height=chart_h,
                    language=lang,
                    dark=True,
                    show_income=True,
                    show_expense=True,
                    page=self._page,
                    compact=True,
                    animate=bool(animate_chart) and not hidden,
                )
            safe_update(self._chart_slot)

        if self._sections_body is not None:
            self._sections_body.visible = self._sections_open
            safe_update(self._sections_body)
        if self._sections_hint is not None:
            self._sections_hint.visible = not self._sections_open
            safe_update(self._sections_hint)
        if self._sections_chevron is not None:
            self._sections_chevron.icon = (
                ft.Icons.EXPAND_LESS
                if self._sections_open
                else ft.Icons.EXPAND_MORE
            )
            safe_update(self._sections_chevron)

    def _today_box(
        self,
        *,
        label: str,
        amount: Decimal,
        currency: str,
        color: str,
        hidden: bool,
    ) -> ft.Control:
        kpi = kpi_card_metrics(self._page, columns=2)
        if hidden:
            display = _HIDDEN_SMALL
            tip = None
        else:
            display = format_money(amount, currency)
            tip = display
        amount_label = ft.Text(
            display,
            size=kpi["value"],
            weight=ft.FontWeight.W_700,
            color=color,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            no_wrap=True,
        )
        if not hidden:
            mark_money_text(
                amount_label,
                amount,
                currency=currency,
                compact=False,
            )
        return ft.Container(
            expand=True,
            tooltip=tip,
            padding=ft.Padding.symmetric(horizontal=max(6, kpi["padding"]), vertical=max(6, kpi["gap"])),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.22, ft.Colors.SURFACE),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        label,
                        size=kpi["title"],
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    amount_label,
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
        figure = _HIDDEN_MONEY if hidden else format_money(total, base).rsplit(" ", 1)[0]
        eye_icon = ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY
        zeros = [Decimal("0")] * max(len(incomes), 1)
        balance_label = ft.Text(
            figure,
            size=fit_font(20, self._page, minimum=16, maximum=24),
            weight=ft.FontWeight.W_700,
            color=skin.text_hex(dark=True),
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            no_wrap=True,
        )
        balance_code = ft.Text(
            "" if hidden else base,
            size=fit_font(12, self._page, minimum=10, maximum=14),
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=not hidden,
        )
        if not hidden:
            mark_money_text(
                balance_label, total, currency=base, figure_only=True
            )
        self._balance_label = balance_label
        self._balance_code_label = balance_code
        eye_btn = ft.IconButton(
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
            style=tap_button_style(horizontal=10, vertical=10),
        )
        self._eye_btn = eye_btn
        chart_btn = ft.IconButton(
            icon=(
                ft.Icons.SHOW_CHART
                if self._hide_chart
                else ft.Icons.EXPAND_LESS
            ),
            icon_size=20,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
            tooltip=tr(
                "dashboard.show_chart"
                if self._hide_chart
                else "dashboard.hide_chart",
                lang,
            ),
            on_click=self._toggle_chart,
            style=tap_button_style(horizontal=10, vertical=10),
        )
        self._chart_btn = chart_btn
        today_row = ft.Row(
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
        )
        self._today_row = today_row
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
                    eye_btn,
                ],
            ),
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=False,
                controls=[
                    balance_label,
                    balance_code,
                    ft.Container(expand=True),
                    chart_btn,
                ],
            ),
            today_row,
        ]
        chart_w, chart_h = compact_chart_size(self._page)
        chart = build_line_chart_image(
            periods,
            incomes if not hidden else zeros,
            expenses if not hidden else zeros,
            width=chart_w,
            height=chart_h,
            language=lang,
            dark=True,
            show_income=True,
            show_expense=True,
            page=self._page,
            compact=True,
            animate=bool(self._animate_charts),
        )
        chart_slot = ft.Container(
            ink=True,
            on_click=self._open_chart_period,
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            tooltip=tr("dashboard.chart_period_hint", lang),
            visible=not self._hide_chart,
            content=chart,
        )
        self._chart_slot = chart_slot
        panel_controls.append(chart_slot)
        return ft.Container(
            padding=card_padding(self._page, hero=True),
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
        budgets_badge: int,
        subs_badge: int,
    ) -> ft.Control:
        skin = get_active_skin()
        open_now = self._sections_open
        chevron = ft.Icon(
            ft.Icons.EXPAND_LESS if open_now else ft.Icons.EXPAND_MORE,
            size=20,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._sections_chevron = chevron
        hint = ft.Text(
            tr("dashboard.shortcuts_hint", lang),
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            visible=not open_now,
        )
        self._sections_hint = hint
        header = ft.Container(
            ink=True,
            on_click=self._toggle_sections,
            border_radius=14,
            padding=ft.Padding.symmetric(vertical=2),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=10,
                        tight=True,
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=32,
                                height=32,
                                border_radius=10,
                                bgcolor=skin.badge_bg(dark=True),
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(
                                    ft.Icons.APPS_OUTLINED,
                                    size=18,
                                    color=skin.badge_fg(dark=True),
                                ),
                            ),
                            ft.Column(
                                spacing=0,
                                tight=True,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        tr("dashboard.shortcuts", lang),
                                        size=15,
                                        weight=ft.FontWeight.W_700,
                                        color=ft.Colors.ON_SURFACE,
                                    ),
                                    hint,
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        width=32,
                        height=32,
                        border_radius=16,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        alignment=ft.Alignment.CENTER,
                        content=chevron,
                    ),
                ],
            ),
        )
        body = ft.Column(
            spacing=8,
            visible=open_now,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        shortcut_chip(
                            tr("nav.goals", lang),
                            ft.Icons.FLAG_OUTLINED,
                            badge=goals_badge,
                            page=self._page,
                            on_click=lambda _e: self._state.open_secondary("goals"),
                        ),
                        shortcut_chip(
                            tr("nav.debts", lang),
                            ft.Icons.CREDIT_SCORE,
                            badge=debts_badge,
                            page=self._page,
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
                            page=self._page,
                            on_click=lambda _e: self._state.open_secondary(
                                "subscriptions"
                            ),
                        ),
                        shortcut_chip(
                            tr("nav.currencies", lang),
                            ft.Icons.CURRENCY_EXCHANGE,
                            page=self._page,
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
                            page=self._page,
                            on_click=lambda _e: self._state.open_secondary(
                                "budgets"
                            ),
                        ),
                    ],
                ),
            ],
        )
        self._sections_body = body
        return card_surface(
            ft.Column(spacing=12, tight=True, controls=[header, body]),
            padding=14,
        )

    def _analytics_button(self, lang: str) -> ft.Container:
        """Full-width entry to the analytics secondary screen."""
        return ft.Container(
            height=scale_size(52, self._page, minimum=48, maximum=64),
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

    async def reload(self, animate: bool = False) -> None:
        """Reload dashboard data from use cases."""
        self._token = self._state.dashboard_token
        self._animate_charts = bool(animate)
        lang = self._state.language
        # Keep chart period in sync with settings (e.g. after restore).
        prefs = self._state.settings
        days = int(getattr(prefs, "dashboard_chart_days", None) or _CHART_DAYS)
        if days in _CHART_PERIODS:
            self._chart_days = days
        self._hide_chart = bool(getattr(prefs, "dashboard_hide_chart", False))
        # Soft reload: keep painted UI while data refreshes (no spinner / jump).
        keep_layout = (
            self._slots_ready
            and bool(self._body.controls)
            and self._budget_slot is not None
        )
        if not keep_layout:
            fill_loading(self._body, message=tr("action.refresh", lang))
        c = self._state.container
        if animate:
            # Manual refresh: drop FX cache so totals/charts recompute cleanly.
            try:
                from lib.presentation.utils import invalidate_rate_book_cache

                invalidate_rate_book_cache()
            except Exception:  # noqa: BLE001
                pass
        try:
            accounts = await c.list_accounts.execute(
                active_only=True, corporate=False
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            replace_controls(
                self._body,
                [
                    EmptyState(
                        tr("error.generic", lang), icon=ft.Icons.ERROR_OUTLINE
                    )
                ],
                self._page,
            )
            self._slots_ready = False
            safe_update(self._body)
            return
        if not accounts:
            replace_controls(
                self._body,
                [
                    EmptyState(
                        tr("empty.accounts", lang),
                        icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                        hint=tr("onboarding.home_hint", lang),
                        action_label=tr("empty.accounts_action", lang),
                        on_action=lambda _e: self._open_first_account(),
                    )
                ],
                self._page,
            )
            self._slots_ready = False
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
        now = datetime.now(timezone.utc)
        # Spent is kept current via apply_expense_delta; full month scan only
        # on explicit refresh so home stays fast with large ledgers.
        if animate:
            recalc = getattr(c, "recalculate_budget_spent", None)
            if recalc is not None:
                try:
                    await recalc.execute(month=now.month, year=now.year)
                except Exception:  # noqa: BLE001
                    pass
        try:
            motion = animate
            with ui_animation(motion):
                budget_widget = await self._budgets_widget(lang, base)

                def _add_button() -> ft.Control:
                    return dual_add_button(
                        lang,
                        page=self._page,
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
                    )

                def _host(slot_name: str, content: ft.Control) -> ft.Container:
                    slot = getattr(self, slot_name)
                    if slot is None:
                        slot = ft.Container(content=content)
                        setattr(self, slot_name, slot)
                    else:
                        slot.content = content
                    return slot

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
                        _host("_add_slot", _add_button()),
                        self._analytics_button(lang),
                        _host(
                            "_sections_slot",
                            self._sections_panel(
                                lang,
                                goals_badge=goals_badge,
                                debts_badge=debts_badge,
                                subs_badge=subs_badge,
                                budgets_badge=budgets_badge,
                            ),
                        ),
                        _host("_budget_slot", budget_widget),
                        ft.Container(height=10),
                    ]

                self._balance_cache = {
                    "build": _build,
                    "lang": lang,
                    "total": total,
                    "base": base,
                    "today_income": today_income,
                    "today_expense": today_expense,
                    "periods": periods,
                    "incomes": incomes,
                    "expenses": expenses,
                }
                if keep_layout:
                    try:
                        self._apply_visibility(
                            animate_chart=bool(self._animate_charts)
                        )
                        if self._add_slot is not None:
                            self._add_slot.content = _add_button()
                            safe_update(self._add_slot)
                        if self._sections_slot is not None:
                            self._sections_slot.content = self._sections_panel(
                                lang,
                                goals_badge=goals_badge,
                                debts_badge=debts_badge,
                                subs_badge=subs_badge,
                                budgets_badge=budgets_badge,
                            )
                            safe_update(self._sections_slot)
                        self._budget_slot.content = budget_widget
                        safe_update(self._budget_slot)
                    except Exception as exc:  # noqa: BLE001
                        snack_exception(self._page, exc, lang=lang)
                        self._slots_ready = False
                        replace_controls(
                            self._body,
                            [
                                EmptyState(
                                    tr("error.generic", lang),
                                    icon=ft.Icons.ERROR_OUTLINE,
                                )
                            ],
                            self._page,
                        )
                else:
                    try:
                        controls = _build()
                    except Exception as exc:  # noqa: BLE001
                        snack_exception(self._page, exc, lang=lang)
                        controls = [
                            EmptyState(
                                tr("error.generic", lang),
                                icon=ft.Icons.ERROR_OUTLINE,
                            )
                        ]
                        self._slots_ready = False
                    else:
                        self._slots_ready = True
                    replace_controls(self._body, controls, self._page)
            if animate and self._slots_ready:
                await play_count_ups(self._body, self._page)
        finally:
            await flush_chart_draws()
            self._animate_charts = False

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
        cat_map: dict[str, object] = {}
        list_cats = getattr(self._state.container, "list_categories", None)
        if list_cats is not None:
            try:
                cat_map = index_categories(
                    await list_cats.execute(active_only=False)
                )
            except Exception:  # noqa: BLE001
                cat_map = {}
        if not shown:
            body: ft.Control = ft.Text(
                tr("dashboard.budgets_empty", lang),
                size=fit_font(13, self._page, minimum=11, maximum=15),
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        else:
            rows: list[ft.Control] = []
            for progress in shown:
                percent = progress.percent
                color = ft.Colors.ERROR if percent > 100 else (
                    ft.Colors.AMBER if percent >= 80 else ft.Colors.GREEN
                )
                cat = lookup_category(cat_map, progress.category_id)
                rows.append(
                    ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Row(
                                spacing=8,
                                controls=[
                                    account_icon_badge(
                                        getattr(cat, "icon", None) or "category",
                                        color=getattr(cat, "color", None) or "#546E7A",
                                        size=28,
                                        glyph_size=14,
                                        glyph_color="#FFFFFF",
                                    ),
                                    ft.Text(
                                        localize_category_name(
                                            progress.category_id, lang
                                        ),
                                        expand=True,
                                        size=fit_font(13, self._page, minimum=11, maximum=15),
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"{percent:.0f}%",
                                        size=fit_font(13, self._page, minimum=11, maximum=15),
                                        color=color,
                                    ),
                                ],
                            ),
                            _home_budget_bar(percent, color),
                            ft.Row(
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    muted_text(
                                        f"{tr('budgets.overspend', lang) if progress.is_over_budget else tr('budgets.remaining', lang)}:"
                                    ),
                                    tappable_compact_money(
                                        self._page,
                                        progress.remaining,
                                        currency,
                                        signed=progress.is_over_budget,
                                        language=lang,
                                        size=12,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
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
