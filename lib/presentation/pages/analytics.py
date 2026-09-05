"""Dedicated analytics screen — swipeable sections with tappable amounts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Sequence

import flet as ft

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.debt import DebtDirection, DebtStatus
from lib.domain.entities.goal import GoalStatus
from lib.domain.entities.transaction import TransactionType
from lib.domain.services.rate_book import RateBook
from lib.domain.use_cases.transactions import GetTransactionStatsUseCase
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.analytics_period import (
    ANALYTICS_PERIOD_KEYS,
    DEFAULT_ANALYTICS_PERIOD,
    enumerate_period_keys,
    fill_time_series,
    format_chart_period_label,
    resolve_analytics_period,
)
from lib.presentation.styles import (
    amount_color,
    card_surface,
    glass_layer,
    muted_text,
    page_header,
    section_title,
)
from lib.presentation.count_up import flush_chart_draws, mark_money_text, play_count_ups
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import restore_scroll, reset_ui_animating, set_ui_animating, snapshot_scroll
from lib.presentation.skins import get_active_skin
from lib.presentation.theme import is_dark_mode
from lib.presentation.utils import (
    format_money,
    format_money_parts,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
)
from lib.presentation.widgets.charts import (
    build_line_chart_image,
    build_pie_chart_image,
    chart_layout,
)
from lib.presentation.layout import h_chip_row
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.debt_summary_ring import (
    analytics_debt_tile,
    analytics_debts_summary,
)
from lib.presentation.widgets.goal_summary_ring import (
    analytics_goal_tile,
    analytics_goals_summary,
)
from lib.presentation.widgets.budget_summary_ring import (
    analytics_budget_tile,
    budgets_summary_ring,
)
from lib.presentation.widgets.subscription_summary_ring import (
    analytics_subscription_tile,
    analytics_subscriptions_summary,
)
from lib.presentation.widgets.loading import fill_loading

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_PALETTE = (
    "#2DD4BF",
    "#38BDF8",
    "#4ADE80",
    "#FBBF24",
    "#F87171",
    "#A78BFA",
)


def _chart_palette() -> Sequence[str]:
    colors = get_active_skin().chart_colors
    return colors if colors else _PALETTE

_SECTIONS = (
    "flow",
    "goals",
    "debts",
    "subscriptions",
    "budget",
)


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _to_base(
    book: RateBook, amount: Decimal, currency: str, base: str
) -> Decimal | None:
    """Convert to base currency; ``None`` when the rate is missing."""
    from lib.domain.services.ledger_fx import amount_to_base

    return amount_to_base(book, amount, currency, base)


class AnalyticsPage(ft.Column):
    """Period KPIs and swipeable analytics sections."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._analytics_period = DEFAULT_ANALYTICS_PERIOD
        self._section = "flow"
        self._token = -1
        self._period_row = h_chip_row()
        self._kpi_host = ft.Column(spacing=4, tight=True)
        self._section_chips = h_chip_row()
        self._period_chip_map: dict[str, ft.Container] = {}
        self._section_chip_map: dict[str, ft.Container] = {}
        self._animate_charts = False
        self._section_hosts: dict[str, ft.Container] = {}
        self._section_lists: dict[str, ft.ListView] = {}
        self._section_offsets: dict[str, float] = {}
        self._pager = ft.PageView(
            expand=True,
            horizontal=True,
            snap=True,
            pad_ends=False,
            keep_page=True,
            implicit_scrolling=False,
            on_change=self._on_pager_change,
        )
        super().__init__(
            expand=True,
            spacing=0,
            controls=[
                page_header(
                    tr("nav.analytics", state.language),
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: self._reload_gate.request(True),
                        ),
                    ],
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.only(left=12, right=12, bottom=8),
                    content=ft.Column(
                        expand=True,
                        spacing=6,
                        controls=[
                            ft.Container(height=40, content=self._period_row),
                            self._kpi_host,
                            ft.Container(height=40, content=self._section_chips),
                            self._pager,
                        ],
                    ),
                ),
            ],
        )
        state.subscribe(self._on_state)
        self._reload_gate = ReloadGate(page, self, self.reload)
        self._reload_gate.request(True)

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    def _data_token(self, state: "AppState") -> int:
        return (
            state.analytics_token
            + state.transactions_token
            + state.goals_token
            + state.debts_token
            + state.subscriptions_token
            + state.budgets_token
        )

    def _on_state(self, state: "AppState") -> None:
        token = self._data_token(state)
        if token != self._token:
            self._reload_gate.request()

    def _show_full_amount(
        self,
        label: str,
        amount: Decimal | float | int | str,
        currency: str,
        *,
        signed: bool = False,
    ) -> None:
        lang = self._state.language
        dialog = ft.CupertinoAlertDialog(
            modal=True,
            title=ft.Text(
                label or tr("analytics.full_amount", lang),
                size=13,
                text_align=ft.TextAlign.CENTER,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                content=ft.Text(
                    format_money(amount, currency, signed=signed),
                    size=17,
                    weight=ft.FontWeight.W_800,
                    text_align=ft.TextAlign.CENTER,
                    selectable=True,
                ),
            ),
            actions=[
                ft.CupertinoDialogAction(
                    tr("action.close", lang),
                    default=True,
                    on_click=lambda _e: self._page.pop_dialog(),
                ),
            ],
        )
        self._page.show_dialog(dialog)

    def _money(
        self,
        amount: Decimal | float | int | str,
        currency: str,
        *,
        label: str,
        color: Optional[str] = None,
        size: int = 13,
        signed: bool = False,
        weight: ft.FontWeight = ft.FontWeight.W_800,
        align: ft.TextAlign = ft.TextAlign.END,
        stacked: bool = False,
    ) -> ft.Control:
        figure, code = format_money_parts(amount, currency, signed=signed)
        figure_text = ft.Text(
            figure,
            size=size,
            weight=weight,
            color=color or ft.Colors.ON_SURFACE,
            text_align=align,
            no_wrap=True,
            max_lines=1,
        )
        mark_money_text(
            figure_text,
            amount,
            currency=currency,
            signed=signed,
            figure_only=True,
        )
        code_text = ft.Text(
            code,
            size=9,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=align,
            no_wrap=True,
        )
        if stacked:
            body: ft.Control = ft.Column(
                spacing=0,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[figure_text, code_text],
            )
        else:
            body = ft.Row(
                spacing=3,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[figure_text, code_text],
            )
        return ft.Container(
            ink=True,
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=1, vertical=1),
            on_click=lambda _e, a=amount, c=currency, l=label, s=signed: (
                self._show_full_amount(l, a, c, signed=s)
            ),
            content=body,
        )

    def _chip(
        self,
        label: str,
        *,
        selected: bool,
        on_click,
    ) -> ft.Control:
        skin = get_active_skin()
        dark = self._dark()
        return ft.Container(
            height=28,
            padding=ft.Padding.symmetric(horizontal=10, vertical=3),
            border_radius=999,
            alignment=ft.Alignment.CENTER,
            **(
                {
                    "bgcolor": skin.badge_bg(dark=dark),
                    "blur": None,
                }
                if selected
                else glass_layer()
            ),
            border=ft.Border.all(
                1,
                skin.primary_hex(dark=dark) if selected else ft.Colors.OUTLINE_VARIANT,
            ),
            ink=True,
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
            on_click=on_click,
            content=ft.Text(
                label,
                size=11,
                weight=ft.FontWeight.W_600,
                no_wrap=True,
                color=(
                    skin.badge_fg(dark=dark)
                    if selected
                    else ft.Colors.ON_SURFACE_VARIANT
                ),
            ),
        )

    def _aggregate_period(
        self,
        accounts: list,
        txs: list,
        base: str,
        group_by,
        book: RateBook,
    ) -> tuple[
        Decimal,
        Decimal,
        Decimal,
        list[tuple[str, Decimal]],
        list[tuple[str, Decimal]],
        list[tuple[str, Decimal, Decimal]],
        bool,
    ]:
        """Single-pass KPI + chart aggregation using an in-memory rate book."""
        from lib.domain.services.ledger_fx import aggregate_cashflow_period

        return aggregate_cashflow_period(
            accounts,
            txs,
            base=base,
            book=book,
            period_key=GetTransactionStatsUseCase._period_key,
            group_by=group_by,
        )

    def _period_chip(self, key: str, lang: str) -> ft.Control:
        return self._chip(
            tr(f"dashboard.period.{key}", lang),
            selected=key == self._analytics_period,
            on_click=lambda _e, k=key: self._set_period(k),
        )

    def _section_chip(self, key: str, lang: str) -> ft.Control:
        return self._chip(
            tr(f"analytics.tab.{key}", lang),
            selected=key == self._section,
            on_click=lambda _e, k=key: self._set_section(k),
        )

    def _set_period(self, key: str) -> None:
        if self._analytics_period == key:
            return
        self._analytics_period = key
        self._tint_period_chips()
        self._reload_gate.request()

    def _rebuild_period_row(self, lang: str) -> None:
        if self._period_chip_map:
            self._tint_period_chips()
            return
        chips = [self._period_chip(key, lang) for key in ANALYTICS_PERIOD_KEYS]
        self._period_chip_map = {
            key: chip  # type: ignore[misc]
            for key, chip in zip(ANALYTICS_PERIOD_KEYS, chips)
        }
        self._period_row.controls = [*chips, ft.Container(width=28)]
        safe_update(self._period_row)

    def _rebuild_section_chips(self) -> None:
        if self._section_chip_map:
            self._tint_section_chips()
            return
        lang = self._state.language
        chips = [self._section_chip(key, lang) for key in _SECTIONS]
        self._section_chip_map = {
            key: chip  # type: ignore[misc]
            for key, chip in zip(_SECTIONS, chips)
        }
        self._section_chips.controls = [*chips, ft.Container(width=28)]
        safe_update(self._section_chips)

    def _tint_period_chips(self) -> None:
        self._tint_chip_map(self._period_chip_map, self._analytics_period)

    def _tint_section_chips(self) -> None:
        self._tint_chip_map(self._section_chip_map, self._section)

    def _tint_chip_map(self, mapping: dict[str, ft.Container], selected_key: str) -> None:
        skin = get_active_skin()
        dark = self._dark()
        for key, chip in mapping.items():
            selected = key == selected_key
            chip.bgcolor = skin.badge_bg(dark=dark) if selected else None
            chip.border = ft.Border.all(
                1,
                skin.primary_hex(dark=dark) if selected else ft.Colors.OUTLINE_VARIANT,
            )
            label = chip.content
            if isinstance(label, ft.Text):
                label.color = (
                    skin.badge_fg(dark=dark)
                    if selected
                    else ft.Colors.ON_SURFACE_VARIANT
                )
                safe_update(label)
            safe_update(chip)

    def _set_section(self, key: str, *, from_pager: bool = False) -> None:
        if key in {"spend", "income"}:
            key = "flow"
        if key not in _SECTIONS:
            key = "flow"
        if self._section == key:
            return
        self._section = key
        if not from_pager:
            self._pager.selected_index = _SECTIONS.index(key)
            safe_update(self._pager)
        self._tint_section_chips()

    def _on_pager_change(self, e: ft.ControlEvent) -> None:
        control = getattr(e, "control", None) or self._pager
        raw = getattr(e, "data", None)
        if raw is not None and str(raw).isdigit():
            idx = int(raw)
        else:
            idx = int(getattr(control, "selected_index", 0) or 0)
        last = len(_SECTIONS) - 1
        idx = max(0, min(idx, last))
        prev = _SECTIONS.index(self._section) if self._section in _SECTIONS else 0
        wrapped = (prev == last and idx == 0) or (prev == 0 and idx == last)
        if wrapped:
            async def _stay() -> None:
                try:
                    await self._pager.jump_to_page(prev)
                except Exception:  # noqa: BLE001
                    self._pager.selected_index = prev
                    safe_update(self._pager)

            self._pager.selected_index = prev
            run_async(self._page, _stay)
            return
        self._set_section(_SECTIONS[idx], from_pager=True)

    def _metric_cell(
        self,
        label: str,
        amount: Decimal | float | int | str,
        currency: str,
        *,
        color: Optional[str] = None,
        signed: bool = False,
        plain: Optional[str] = None,
    ) -> ft.Control:
        value: ft.Control
        if plain is not None:
            value = ft.Text(
                plain,
                size=15,
                weight=ft.FontWeight.W_800,
                color=color or ft.Colors.ON_SURFACE,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
            )
        else:
            value = self._money(
                amount,
                currency,
                label=label,
                color=color,
                size=15,
                signed=signed,
                align=ft.TextAlign.CENTER,
                stacked=True,
            )
        return ft.Container(
            expand=True,
            content=ft.Column(
                spacing=1,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        label,
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    value,
                ],
            ),
        )

    def _metrics_card(self, cells: list[ft.Control]) -> ft.Control:
        return card_surface(
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=cells,
            ),
            padding=8,
        )

    def _kv_row(
        self,
        label: str,
        amount: Decimal | float | int | str,
        currency: str,
        *,
        color: Optional[str] = None,
        signed: bool = False,
        trailing: str | None = None,
    ) -> ft.Control:
        right: list[ft.Control] = [
            self._money(
                amount,
                currency,
                label=label,
                color=color,
                signed=signed,
            )
        ]
        if trailing:
            right.append(
                ft.Text(
                    trailing,
                    size=11,
                    no_wrap=True,
                    max_lines=1,
                    text_align=ft.TextAlign.END,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    label,
                    size=12,
                    expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=2,
                    color=ft.Colors.ON_SURFACE,
                ),
                *right,
            ],
        )

    def _scroll_page(self, key: str, controls: Sequence[ft.Control]) -> ft.Control:
        from lib.presentation.layout import make_v_scroll

        lv = self._section_lists.get(key)
        if lv is None:
            lv = make_v_scroll(spacing=8, eager=True)
            host = ft.Container(
                expand=True,
                padding=ft.Padding.only(right=2),
                content=lv,
            )
            self._section_lists[key] = lv
            self._section_hosts[key] = host
            lv.controls = list(controls)
            return host
        self._section_offsets[key] = snapshot_scroll(lv)
        lv.controls = list(controls)
        return self._section_hosts[key]

    def _category_card(
        self,
        *,
        title: str,
        cats: list[tuple[str, Decimal]],
        total: Decimal,
        base: str,
        lang: str,
        dark: bool,
        chart_w: int,
        chart_h: int,
        empty_key: str,
        empty_chart: str,
    ) -> ft.Control:
        pie_cats = cats[:6]
        pie = build_pie_chart_image(
            [localize_category_name(cat, lang) for cat, _amt in pie_cats],
            [amt for _cat, amt in pie_cats],
            title="",
            width=chart_w,
            height=chart_h,
            dark=dark,
            language=lang,
            show_legend=False,
            empty_message=empty_chart,
            page=self._page,
            animate=bool(self._animate_charts),
        )
        rows: list[ft.Control] = []
        denom = total if total > 0 else Decimal("0")
        palette = _chart_palette()
        for idx, (cat, amount) in enumerate(pie_cats):
            share = (amount / denom * 100) if denom > 0 else Decimal("0")
            name = localize_category_name(cat, lang)
            rows.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=8,
                            height=8,
                            border_radius=4,
                            bgcolor=palette[idx % len(palette)],
                        ),
                        ft.Text(
                            name,
                            size=12,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                        ),
                        ft.Row(
                            spacing=6,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                self._money(
                                    amount, base, label=name, size=11, color=None
                                ),
                                ft.Text(
                                    f"{share:.0f}%",
                                    size=11,
                                    no_wrap=True,
                                    max_lines=1,
                                    text_align=ft.TextAlign.END,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                        ),
                    ],
                )
            )
        if not pie_cats:
            rows = [muted_text(tr(empty_key, lang), size=12)]
        return card_surface(
            ft.Column(
                spacing=8,
                tight=True,
                controls=[section_title(title), pie, *rows],
            ),
            padding=10,
        )

    async def reload(self, animate: bool = False) -> None:
        """Reload analytics KPIs and section pages."""
        self._token = self._data_token(self._state)
        self._animate_charts = bool(animate)
        lang = self._state.language
        self._rebuild_period_row(lang)
        self._rebuild_section_chips()
        fill_loading(self._kpi_host, message=tr("action.refresh", lang))

        c = self._state.container
        now = datetime.now(timezone.utc)
        dark = is_dark_mode(self._page, self._state.theme_mode)
        chart_w, chart_h = chart_layout(self._page)

        if animate:
            try:
                from lib.presentation.utils import invalidate_rate_book_cache

                invalidate_rate_book_cache()
            except Exception:  # noqa: BLE001
                pass
        # Refresh stored budget spend so rings/bars match the ledger.
        # Full scan only on explicit refresh — passive opens use incremental spent.
        if animate:
            recalc = getattr(c, "recalculate_budget_spent", None)
            if recalc is not None:
                try:
                    await recalc.execute(month=now.month, year=now.year)
                except Exception:  # noqa: BLE001
                    pass

        try:
            personal = await c.list_accounts.execute(
                active_only=True, corporate=False
            )
            corporate = await c.list_accounts.execute(corporate=True)
            accounts = [*personal, *corporate]
            period_cfg = resolve_analytics_period(self._analytics_period, now)
            from lib.presentation.tx_query import fetch_transactions_paged

            period_txs = await fetch_transactions_paged(
                c.list_transactions,
                date_from=period_cfg.date_from,
                date_to=period_cfg.date_to,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            self._kpi_host.controls = [
                EmptyState(tr("error.generic", lang), icon=ft.Icons.ERROR_OUTLINE)
            ]
            safe_update(self._kpi_host)
            return

        base = normalize_currency_code(self._state.base_currency)
        book = await load_rate_book(c, force=bool(animate))
        (
            total_balance,
            period_income,
            period_expense,
            by_expense,
            by_income,
            by_period,
            fx_ok,
        ) = self._aggregate_period(
            accounts, period_txs, base, period_cfg.group_by, book
        )
        if not fx_ok and c.update_exchange_rates is not None:
            try:
                await c.update_exchange_rates.execute(base=base)
                from lib.presentation.utils import invalidate_rate_book_cache

                invalidate_rate_book_cache()
                book = await load_rate_book(c)
                (
                    total_balance,
                    period_income,
                    period_expense,
                    by_expense,
                    by_income,
                    by_period,
                    fx_ok,
                ) = self._aggregate_period(
                    accounts, period_txs, base, period_cfg.group_by, book
                )
            except Exception:  # noqa: BLE001
                pass
        if not fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)

        sub_analytics = None
        if getattr(c, "get_subscription_analytics", None) is not None:
            try:
                sub_analytics = await c.get_subscription_analytics.execute(
                    base_currency=base,
                    date_from=period_cfg.date_from,
                    date_to=period_cfg.date_to,
                )
            except Exception:  # noqa: BLE001
                sub_analytics = None

        goals: list = []
        if getattr(c, "list_goals", None) is not None:
            try:
                goals = await c.list_goals.execute(include_completed=True)
            except Exception:  # noqa: BLE001
                goals = []
        debts: list = []
        if getattr(c, "list_debts", None) is not None:
            try:
                debts = await c.list_debts.execute()
            except Exception:  # noqa: BLE001
                debts = []
        budgets: list = []
        budget_analytics = None
        budget_cats: dict[str, object] = {}
        if getattr(c, "get_budget_analytics", None) is not None:
            try:
                budget_analytics = await c.get_budget_analytics.execute(
                    now.month, now.year, base_currency=base
                )
                budgets = list(budget_analytics.items)
            except Exception:  # noqa: BLE001
                budget_analytics = None
        if not budgets and getattr(c, "get_budgets_for_month", None) is not None:
            try:
                budgets = await c.get_budgets_for_month.execute(now.month, now.year)
            except Exception:  # noqa: BLE001
                budgets = []
        if getattr(c, "list_categories", None) is not None:
            try:
                budget_cats = {
                    cat.name: cat
                    for cat in await c.list_categories.execute(active_only=False)
                }
            except Exception:  # noqa: BLE001
                budget_cats = {}

        net = period_income - period_expense
        net_color = amount_color(net >= 0, dark=dark)
        income_ops = 0
        expense_ops = 0
        for tx in period_txs:
            if getattr(tx, "transfer_id", None):
                continue
            if tx.type == TransactionType.INCOME:
                income_ops += 1
            else:
                expense_ops += 1
        if period_cfg.date_from is None:
            days = 365
        else:
            days = max(
                1,
                (period_cfg.date_to.date() - period_cfg.date_from.date()).days,
            )
        avg_expense_day = (
            (period_expense / Decimal(days)) if days else period_expense
        )
        avg_income_day = (
            (period_income / Decimal(days)) if days else period_income
        )
        savings = (
            f"{((net / period_income) * 100):.0f}%"
            if period_income > 0
            else "—"
        )

        anim_token = set_ui_animating(animate)
        try:
            self._kpi_host.controls = [
                self._metrics_card(
                    [
                        self._metric_cell(
                            tr("analytics.income", lang),
                            period_income,
                            base,
                            color=amount_color(True, dark=dark),
                        ),
                        self._metric_cell(
                            tr("analytics.expense", lang),
                            period_expense,
                            base,
                            color=amount_color(False, dark=dark),
                        ),
                        self._metric_cell(
                            tr("analytics.net", lang),
                            net,
                            base,
                            color=net_color,
                            signed=True,
                        ),
                    ]
                ),
                self._metrics_card(
                    [
                        self._metric_cell(
                            tr("analytics.balance", lang),
                            total_balance,
                            base,
                        ),
                        self._metric_cell(
                            tr("analytics.savings", lang),
                            0,
                            base,
                            plain=savings,
                        ),
                    ]
                ),
            ]
            safe_update(self._kpi_host)

            series = fill_time_series(
                by_period,
                enumerate_period_keys(period_cfg, existing=[p[0] for p in by_period]),
            )
            if period_cfg.max_chart_points and len(series) > period_cfg.max_chart_points:
                series = series[-period_cfg.max_chart_points :]
            period_labels = [
                format_chart_period_label(p[0], period_cfg.group_by) for p in series
            ]
            series_income = [p[1] for p in series]
            series_expense = [p[2] for p in series]

            flow_page = self._scroll_page(
            "flow",
            [
                self._metrics_card(
                    [
                        self._metric_cell(
                            tr("analytics.avg_income_day", lang),
                            avg_income_day,
                            base,
                            color=amount_color(True, dark=dark),
                        ),
                        self._metric_cell(
                            tr("analytics.avg_day", lang),
                            avg_expense_day,
                            base,
                            color=amount_color(False, dark=dark),
                        ),
                        self._metric_cell(
                            tr("analytics.ops", lang),
                            0,
                            base,
                            plain=str(income_ops + expense_ops),
                        ),
                    ]
                ),
                self._category_card(
                    title=tr("analytics.spend_cats", lang),
                    cats=by_expense,
                    total=period_expense,
                    base=base,
                    lang=lang,
                    dark=dark,
                    chart_w=chart_w,
                    chart_h=chart_h,
                    empty_key="empty.transactions",
                    empty_chart=tr("chart.no_expenses", lang),
                ),
                self._category_card(
                    title=tr("analytics.income_cats", lang),
                    cats=by_income,
                    total=period_income,
                    base=base,
                    lang=lang,
                    dark=dark,
                    chart_w=chart_w,
                    chart_h=chart_h,
                    empty_key="empty.transactions",
                    empty_chart=tr("chart.no_income", lang),
                ),
                card_surface(
                    ft.Column(
                        spacing=8,
                        tight=True,
                        controls=[
                            section_title(tr("dashboard.dynamics", lang)),
                            build_line_chart_image(
                                period_labels,
                                series_income,
                                series_expense,
                                title="",
                                width=chart_w,
                                height=max(chart_h, 180),
                                dark=dark,
                                language=lang,
                                show_income=True,
                                show_expense=True,
                                page=self._page,
                                animate=bool(self._animate_charts),
                            ),
                        ],
                    ),
                    padding=10,
                ),
            ]
        )

            pages = [
                flow_page,
                self._scroll_page("goals", self._goals_controls(goals, book, base, lang)),
                self._scroll_page("debts", self._debts_controls(debts, book, base, lang)),
                self._scroll_page(
                    "subscriptions",
                    self._subscription_analytics_controls(
                        sub_analytics,
                        lang,
                        base,
                    ),
                ),
                self._scroll_page(
                    "budget",
                    self._budget_controls(
                        budgets,
                        lang,
                        base,
                        now.month,
                        now.year,
                        analytics=budget_analytics,
                        categories=budget_cats,
                    ),
                ),
            ]
            if not self._pager.controls:
                self._pager.controls = pages
            if self._section not in _SECTIONS:
                self._section = "flow"
            self._pager.selected_index = _SECTIONS.index(self._section)
            self._rebuild_section_chips()
            safe_update(self._kpi_host)
            safe_update(self._pager)
        finally:
            reset_ui_animating(anim_token)
            from lib.presentation.utils import run_async

            for key, lv in self._section_lists.items():
                off = float(self._section_offsets.get(key, 0) or 0)
                if off > 8:
                    run_async(self._page, restore_scroll, lv, off)
            try:
                if animate:
                    await play_count_ups(self, self._page)
            finally:
                await flush_chart_draws()
                self._animate_charts = False

    def _dark(self) -> bool:
        return is_dark_mode(self._page, self._state.theme_mode)

    def _goals_controls(
        self,
        goals: list,
        book: RateBook,
        base: str,
        lang: str,
    ) -> list[ft.Control]:
        visible = [
            g
            for g in goals
            if _status_value(g.status) != GoalStatus.ARCHIVED.value
        ]
        if not visible:
            return [
                EmptyState(
                    tr("empty.goals", lang),
                    icon=ft.Icons.FLAG_OUTLINED,
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._state.open_secondary("goals"),
                )
            ]
        target = Decimal("0")
        saved = Decimal("0")
        remaining = Decimal("0")
        fx_ok = True
        for g in visible:
            t = _to_base(book, g.target_amount, g.currency, base)
            s = _to_base(book, g.current_amount, g.currency, base)
            if t is None or s is None:
                fx_ok = False
                continue
            target += t
            saved += s
            if _status_value(g.status) == GoalStatus.ACTIVE.value:
                r = _to_base(book, g.remaining_amount, g.currency, base)
                if r is None:
                    fx_ok = False
                    continue
                remaining += r
        rows: list[ft.Control] = []
        if not fx_ok:
            rows.append(muted_text(tr("fx.missing_rates", lang)))
        if fx_ok and target > 0:
            rows.append(
                analytics_goals_summary(
                    saved=saved,
                    target=target,
                    remaining=remaining,
                    currency=base,
                    language=lang,
                    goal_count=len(visible),
                )
            )
            rows.append(section_title(tr("analytics.goals_breakdown", lang)))
        visible.sort(
            key=lambda g: (
                0 if _status_value(g.status) == GoalStatus.ACTIVE.value else 1,
                -int(g.priority or 3),
                -float(g.progress_ratio),
                g.name.lower(),
            )
        )
        for goal in visible:
            rows.append(
                analytics_goal_tile(
                    goal,
                    language=lang,
                    base_currency=base,
                )
            )
        return rows

    def _debts_controls(
        self,
        debts: list,
        book: RateBook,
        base: str,
        lang: str,
    ) -> list[ft.Control]:
        live = [
            d
            for d in debts
            if _status_value(d.status)
            in {DebtStatus.ACTIVE.value, DebtStatus.OVERDUE.value}
        ]
        if not live:
            return [
                EmptyState(
                    tr("empty.debts", lang),
                    icon=ft.Icons.CREDIT_SCORE,
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._state.open_secondary("debts"),
                )
            ]
        i_owe = Decimal("0")
        owed = Decimal("0")
        overdue_count = 0
        fx_ok = True
        for debt in live:
            remaining = _to_base(book, debt.remaining_amount, debt.currency, base)
            if remaining is None:
                fx_ok = False
                continue
            if _status_value(debt.status) == DebtStatus.OVERDUE.value:
                overdue_count += 1
            direction = _status_value(debt.direction)
            if direction == DebtDirection.I_OWE.value:
                i_owe += remaining
            else:
                owed += remaining
        rows: list[ft.Control] = []
        if not fx_ok:
            rows.append(muted_text(tr("fx.missing_rates", lang)))
        if fx_ok:
            rows.append(
                analytics_debts_summary(
                    i_owe=i_owe,
                    owed_to_me=owed,
                    currency=base,
                    language=lang,
                    debt_count=len(live),
                    overdue_count=overdue_count,
                )
            )
            rows.append(section_title(tr("analytics.debts_breakdown", lang)))
        live.sort(
            key=lambda d: (
                0 if _status_value(d.status) == DebtStatus.OVERDUE.value else 1,
                d.due_date is None,
                d.due_date or datetime.max.replace(tzinfo=timezone.utc),
                d.counterparty.lower(),
            )
        )
        for debt in live:
            rows.append(
                analytics_debt_tile(
                    debt,
                    language=lang,
                    base_currency=base,
                )
            )
        return rows


    def _budget_controls(
        self,
        budgets: list,
        lang: str,
        base: str,
        month: int,
        year: int,
        *,
        analytics=None,
        categories: dict | None = None,
    ) -> list[ft.Control]:
        cat_map = categories or {}
        if not budgets:
            return [
                EmptyState(
                    tr("budgets.no_budgets", lang),
                    icon=ft.Icons.PIE_CHART,
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._state.open_secondary("budgets"),
                ),
            ]
        total_limit = (
            analytics.total_limit
            if analytics is not None
            else sum((item.limit for item in budgets), Decimal("0"))
        )
        total_spent = (
            analytics.total_spent
            if analytics is not None
            else sum((item.spent for item in budgets), Decimal("0"))
        )
        remaining = (
            analytics.remaining
            if analytics is not None
            else total_limit - total_spent
        )
        over_count = (
            analytics.over_count
            if analytics is not None
            else sum(1 for item in budgets if item.is_over_budget)
        )
        warning_count = (
            analytics.warning_count
            if analytics is not None
            else sum(
                1
                for item in budgets
                if (not item.is_over_budget) and item.percent >= 80
            )
        )
        rows: list[ft.Control] = [
            budgets_summary_ring(
                spent=total_spent,
                limit=total_limit,
                remaining=remaining,
                currency=base,
                language=lang,
                over_count=over_count,
                warning_count=warning_count,
                count=len(budgets),
            ),
            section_title(tr("analytics.budgets_breakdown", lang)),
        ]
        for progress in budgets:
            cat = cat_map.get(progress.category_id)
            rows.append(
                analytics_budget_tile(
                    progress,
                    language=lang,
                    currency=base,
                    category_icon=getattr(cat, "icon", None) or "category",
                    category_color=getattr(cat, "color", None) or "#546E7A",
                    category_name=localize_category_name(progress.category_id, lang),
                )
            )
        return rows

    def _subscription_analytics_controls(
        self,
        analytics,
        lang: str,
        base: str,
    ) -> list[ft.Control]:
        empty = analytics is None or (
            getattr(analytics, "total_active", 0) == 0
            and getattr(analytics, "total_spent", Decimal("0")) == 0
            and not getattr(analytics, "top_subscriptions", None)
        )
        if empty:
            return [
                EmptyState(
                    tr("analytics.no_subs", lang),
                    icon=ft.Icons.EVENT_REPEAT,
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._state.open_secondary("subscriptions"),
                )
            ]
        yearly = getattr(analytics, "total_yearly_cost", None)
        if yearly is None:
            yearly = analytics.total_monthly_cost * Decimal("12")
        rows: list[ft.Control] = [
            analytics_subscriptions_summary(
                spent=analytics.total_spent,
                monthly=analytics.total_monthly_cost,
                yearly=yearly,
                currency=base,
                language=lang,
                active_count=analytics.total_active,
            )
        ]
        items = list(getattr(analytics, "top_subscriptions", None) or [])
        if items:
            rows.append(section_title(tr("analytics.subscriptions_breakdown", lang)))
            for item in items:
                spent = item.get("amount") or Decimal("0")
                monthly = item.get("monthly") or Decimal("0")
                share = float(item.get("share") or 0)
                rows.append(
                    analytics_subscription_tile(
                        name=str(item.get("name") or "—"),
                        icon=str(item.get("icon") or "autorenew"),
                        color=str(item.get("color") or "#A78BFA"),
                        spent=spent,
                        monthly=monthly,
                        currency=base,
                        language=lang,
                        share=share,
                        period_start=item.get("start_date"),
                        period_end=item.get("end_date"),
                    )
                )
        return rows
