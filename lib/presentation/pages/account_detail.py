"""Per-account statistics: KPIs, charts, recent activity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.exchange_connection import ExchangeConnection
from lib.domain.exchanges import exchange_title
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.account_icons import account_icon_badge, resolve_account_icon_key
from lib.presentation.account_stats import aggregate_account_period
from lib.presentation.analytics_period import (
    ANALYTICS_PERIOD_KEYS,
    DEFAULT_ANALYTICS_PERIOD,
    enumerate_period_keys,
    fill_time_series,
    format_chart_period_label,
    resolve_analytics_period,
)
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import (
    card_surface,
    glass_layer,
    muted_text,
    page_header,
    section_title,
    amount_color,
)
from lib.presentation.theme import is_dark_mode
from lib.presentation.utils import (
    format_date,
    format_money,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    tr,
)
from lib.presentation.widgets.charts import (
    build_line_chart_image,
    build_pie_chart_image,
    chart_layout,
)
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.layout import h_chip_row, make_v_scroll
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.summary_card import SummaryCard
from lib.presentation.widgets.transaction_tile import TransactionTile

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


class AccountDetailPage(ft.Column):
    """Statistics for a single account opened from the accounts list."""

    def __init__(self, page: ft.Page, state: "AppState", account_id: str) -> None:
        self._page = page
        self._state = state
        self._account_id = account_id
        self._body = make_v_scroll(spacing=12)
        self._period = DEFAULT_ANALYTICS_PERIOD
        self._token = -1
        self._period_row = h_chip_row()
        self._period_chip_map: dict[str, ft.Container] = {}
        self._syncing = False
        self._sync_btn = ft.IconButton(
            icon=ft.Icons.SYNC,
            icon_color=ft.Colors.PRIMARY,
            tooltip=tr("account.sync.now", state.language),
            visible=False,
            on_click=lambda _e: run_async(page, self._sync_now),
        )
        super().__init__(
            expand=True,
            spacing=0,
            controls=[
                page_header(
                    tr("account.stats.title", state.language),
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        self._sync_btn,
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: run_async(page, self.reload),
                        ),
                    ],
                ),
                ft.Container(
                    height=42,
                    padding=ft.Padding.only(left=12, right=12, bottom=8),
                    content=self._period_row,
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.only(left=12, right=12, top=6),
                    content=self._body,
                ),
            ],
        )
        state.subscribe(self._on_state)
        run_async(page, self.reload)

    def _on_state(self, state: "AppState") -> None:
        token = state.accounts_token + state.transactions_token
        if token != self._token:
            run_async(self._page, self.reload)

    def _chip(self, label: str, *, selected: bool, on_click) -> ft.Container:
        skin = get_active_skin()
        dark = is_dark_mode(self._page, self._state.theme_mode)
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

    def _rebuild_period_row(self, lang: str) -> None:
        if self._period_chip_map:
            self._tint_period_chips()
            return
        chips = [
            self._chip(
                tr(f"dashboard.period.{key}", lang),
                selected=key == self._period,
                on_click=lambda _e, k=key: self._set_period(k),
            )
            for key in ANALYTICS_PERIOD_KEYS
        ]
        self._period_chip_map = {
            key: chip for key, chip in zip(ANALYTICS_PERIOD_KEYS, chips)
        }
        self._period_row.controls = [*chips, ft.Container(width=28)]
        safe_update(self._period_row)

    def _tint_period_chips(self) -> None:
        skin = get_active_skin()
        dark = is_dark_mode(self._page, self._state.theme_mode)
        for key, chip in self._period_chip_map.items():
            selected = key == self._period
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

    def _set_period(self, key: str) -> None:
        if self._period == key:
            return
        self._period = key
        self._tint_period_chips()
        run_async(self._page, self.reload)

    async def _sync_now(self) -> None:
        if self._syncing:
            return
        lang = self._state.language
        sync = getattr(self._state.container, "sync_exchange_account", None)
        if sync is None:
            snack(self._page, tr("error.exchange_unavailable", lang), error=True)
            return
        self._syncing = True
        self._sync_btn.disabled = True
        safe_update(self._sync_btn)
        snack(self._page, tr("account.sync.working", lang))
        try:
            result = await sync.execute(self._account_id)
        except Exception as exc:  # noqa: BLE001
            snack(
                self._page,
                tr("error.sync_failed", lang, detail=str(exc)[:240]),
                error=True,
            )
            return
        finally:
            self._syncing = False
            self._sync_btn.disabled = False
            safe_update(self._sync_btn)
        self._state.bump_refresh("dashboard", "accounts", "transactions", "budgets")
        snack(self._page, tr("account.sync.ok", lang, count=result.imported))

    def _exchange_section(
        self,
        link: ExchangeConnection,
        *,
        currency: str,
        lang: str,
    ) -> ft.Control:
        when = (
            format_date(link.last_sync_at, with_time=True)
            if link.last_sync_at
            else tr("account.exchange.never_synced", lang)
        )
        rows: list[ft.Control] = [
            ft.Text(
                exchange_title(link.provider),
                size=14,
                weight=ft.FontWeight.W_700,
            ),
            muted_text(
                tr("account.exchange.last_sync", lang, when=when),
                size=11,
            ),
        ]
        if link.last_error:
            rows.append(
                ft.Text(
                    link.last_error,
                    size=11,
                    color=ft.Colors.ERROR,
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        holdings = list(link.holdings_json or [])
        if holdings:
            rows.append(muted_text(tr("account.holdings", lang), size=12))
        for item in holdings[:16]:
            asset = str(item.get("asset") or "")
            try:
                amount = Decimal(str(item.get("amount") or "0"))
            except Exception:  # noqa: BLE001
                amount = Decimal("0")
            try:
                value = Decimal(str(item.get("value") or "0"))
            except Exception:  # noqa: BLE001
                value = Decimal("0")
            rows.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=0,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(asset, size=13, weight=ft.FontWeight.W_600),
                                muted_text(f"{amount.normalize()} {asset}", size=11),
                            ],
                        ),
                        ft.Text(
                            format_money(value, currency),
                            size=13,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                )
            )
        return card_surface(ft.Column(spacing=8, tight=True, controls=rows), padding=14)

    def _hero(
        self,
        *,
        name: str,
        currency: str,
        color: str,
        icon: str,
        balance: Decimal,
        base_line: str | None,
        lang: str,
    ) -> ft.Control:
        return card_surface(
            ft.Column(
                spacing=10,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            account_icon_badge(
                                icon,
                                color=color,
                                size=48,
                                glyph_size=24,
                                glyph_color=ft.Colors.WHITE,
                            ),
                            ft.Column(
                                spacing=2,
                                tight=True,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        name,
                                        size=18,
                                        weight=ft.FontWeight.W_700,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    muted_text(currency, size=12),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(
                        format_money(balance, currency),
                        size=26,
                        weight=ft.FontWeight.W_700,
                    ),
                    *([muted_text(base_line)] if base_line else []),
                ],
            ),
            accent=color,
            padding=16,
        )

    async def reload(self) -> None:
        """Load the account and rebuild KPIs / charts."""
        self._token = (
            self._state.accounts_token + self._state.transactions_token
        )
        lang = self._state.language
        self._rebuild_period_row(lang)
        fill_loading(self._body, message=tr("action.refresh", lang))
        safe_update(self._body)

        c = self._state.container
        now = datetime.now(timezone.utc)
        dark = is_dark_mode(self._page, self._state.theme_mode)
        chart_w, chart_h = chart_layout(self._page)
        period_cfg = resolve_analytics_period(self._period, now)
        period_label = tr(f"dashboard.period.{period_cfg.key}", lang)

        try:
            account = await c.account_repository.get_by_id(self._account_id)
            if account is None:
                self._body.controls = [
                    EmptyState(
                        tr("account.stats.missing", lang),
                        icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                    )
                ]
                safe_update(self._body)
                return
            txs = await c.list_transactions.execute(
                account_id=account.id,
                date_from=period_cfg.date_from,
                date_to=period_cfg.date_to,
            )
            link = None
            repo = getattr(c, "exchange_connection_repository", None)
            if repo is not None:
                link = await repo.get_by_account_id(account.id)
        except Exception as exc:  # noqa: BLE001
            snack(self._page, str(exc), error=True)
            self._body.controls = [
                EmptyState(tr("error.generic", lang), icon=ft.Icons.ERROR_OUTLINE)
            ]
            safe_update(self._body)
            return

        currency = account.currency
        self._sync_btn.visible = link is not None
        self._sync_btn.tooltip = tr("account.sync.now", lang)
        safe_update(self._sync_btn)
        base = self._state.base_currency
        base_line = None
        if currency.upper() != base.upper():
            book = await load_rate_book(c)
            converted = book.convert(account.balance, currency, base)
            if converted is not None:
                base_line = f"≈ {format_money(converted, base)}"

        stats = aggregate_account_period(txs, period_cfg.group_by)
        net = stats.income - stats.expense
        net_accent = amount_color(net >= 0, dark=dark)

        controls: list[ft.Control] = [
            self._hero(
                name=account.name,
                currency=currency,
                color=account.color or ft.Colors.PRIMARY,
                icon=resolve_account_icon_key(
                    account.icon, link.provider if link else ""
                ),
                balance=account.balance,
                base_line=base_line,
                lang=lang,
            ),
        ]
        if link is not None:
            controls.append(self._exchange_section(link, currency=currency, lang=lang))
        controls.extend(
            [
            section_title(tr("dashboard.period_summary", lang, period=period_label)),
            ft.Row(
                spacing=10,
                controls=[
                    SummaryCard(
                        title=tr("dashboard.period_income", lang, period=period_label),
                        value=format_money(stats.income, currency),
                        icon=ft.Icons.TRENDING_UP,
                        accent=amount_color(True, dark=dark),
                        expand=True,
                        dark=dark,
                    ),
                    SummaryCard(
                        title=tr("dashboard.period_expense", lang, period=period_label),
                        value=format_money(stats.expense, currency),
                        icon=ft.Icons.TRENDING_DOWN,
                        accent=amount_color(False, dark=dark),
                        expand=True,
                        dark=dark,
                    ),
                ],
            ),
            card_surface(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            controls=[
                                muted_text(
                                    tr(
                                        "dashboard.period_net",
                                        lang,
                                        period=period_label,
                                    ),
                                    size=12,
                                ),
                                ft.Text(
                                    format_money(net, currency),
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    color=net_accent,
                                ),
                            ],
                        ),
                        muted_text(
                            tr(
                                "account.stats.count",
                                lang,
                                count=stats.tx_count,
                            ),
                            size=12,
                        ),
                    ],
                ),
                padding=14,
            ),
            ]
        )

        if stats.transfer_in > 0 or stats.transfer_out > 0:
            controls.append(
                card_surface(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                tight=True,
                                controls=[
                                    muted_text(tr("account.stats.transfer_in", lang)),
                                    ft.Text(
                                        format_money(stats.transfer_in, currency),
                                        weight=ft.FontWeight.W_700,
                                        color=amount_color(True, dark=dark),
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=2,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                                controls=[
                                    muted_text(tr("account.stats.transfer_out", lang)),
                                    ft.Text(
                                        format_money(stats.transfer_out, currency),
                                        weight=ft.FontWeight.W_700,
                                        color=amount_color(False, dark=dark),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    padding=14,
                )
            )

        if not txs:
            controls.append(
                EmptyState(
                    tr("account.stats.empty", lang),
                    icon=ft.Icons.ANALYTICS_OUTLINED,
                )
            )
            self._body.controls = controls
            safe_update(self._body)
            return

        pie_cats = stats.by_category[:6]
        pie = build_pie_chart_image(
            [localize_category_name(cat, lang) for cat, _amt in pie_cats],
            [amt for _cat, amt in pie_cats],
            title="",
            width=chart_w,
            height=chart_h,
            dark=dark,
            language=lang,
            show_legend=False,
            page=self._page,
        )
        series = fill_time_series(
            stats.by_period,
            enumerate_period_keys(
                period_cfg, existing=[p[0] for p in stats.by_period]
            ),
        )
        if period_cfg.max_chart_points and len(series) > period_cfg.max_chart_points:
            series = series[-period_cfg.max_chart_points :]
        line = build_line_chart_image(
            [format_chart_period_label(p[0], period_cfg.group_by) for p in series],
            [p[1] for p in series],
            [p[2] for p in series],
            title="",
            width=chart_w,
            height=chart_h,
            dark=dark,
            language=lang,
            page=self._page,
        )

        palette = list(get_active_skin().chart_colors) or [
            "#2DD4BF",
            "#38BDF8",
            "#4ADE80",
            "#FBBF24",
            "#F87171",
            "#A78BFA",
        ]
        category_rows: list[ft.Control] = []
        spend_total = stats.ops_expense or Decimal("0")
        for idx, (cat, amount) in enumerate(pie_cats):
            share = (amount / spend_total * 100) if spend_total > 0 else Decimal("0")
            category_rows.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(
                            spacing=8,
                            expand=True,
                            controls=[
                                ft.Container(
                                    width=10,
                                    height=10,
                                    border_radius=5,
                                    bgcolor=palette[idx % len(palette)],
                                ),
                                ft.Text(
                                    localize_category_name(cat, lang),
                                    size=12,
                                    expand=True,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    max_lines=1,
                                ),
                            ],
                        ),
                        ft.Text(
                            f"{format_money(amount, currency)}  ({share:.0f}%)",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_600,
                            no_wrap=True,
                            max_lines=1,
                        ),
                    ],
                )
            )

        controls.extend(
            [
                section_title(tr("dashboard.charts", lang)),
                card_surface(
                    ft.Column(
                        spacing=10,
                        tight=True,
                        controls=[
                            ft.Text(
                                tr("account.stats.spend_chart", lang),
                                size=14,
                                weight=ft.FontWeight.W_700,
                            ),
                            muted_text(tr("account.stats.spend_hint", lang), size=11),
                            pie,
                            *category_rows,
                        ],
                    ),
                    padding=12,
                ),
                card_surface(
                    ft.Column(
                        spacing=10,
                        tight=True,
                        controls=[
                            ft.Text(
                                tr("dashboard.dynamics", lang),
                                size=14,
                                weight=ft.FontWeight.W_700,
                            ),
                            muted_text(tr("dashboard.dynamics_hint", lang), size=11),
                            line,
                        ],
                    ),
                    padding=12,
                ),
                section_title(tr("account.stats.recent", lang)),
            ]
        )
        for tx in txs[:10]:
            controls.append(TransactionTile(tx, language=lang))
        self._body.controls = controls
        safe_update(self._body)
