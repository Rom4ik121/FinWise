"""Per-account statistics: KPIs, charts, recent activity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.domain.entities.budget import Budget
from lib.domain.entities.category import CategoryKind
from lib.domain.entities.exchange_connection import ExchangeConnection
from lib.domain.entities.transaction import TransactionType
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
from lib.presentation.category_lookup import index_categories, lookup_category
from lib.presentation.count_up import flush_chart_draws, mark_money_text, play_count_ups
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import (
    chart_enter,
    replace_controls,
    reset_ui_animating,
    set_ui_animating,
)
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import (
    card_surface,
    form_section,
    glass_layer,
    muted_text,
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
    snack_exception,
    tappable_compact_money,
    tr,
    user_facing_error,
)
from lib.presentation.widgets.category_picker import CategoryPicker
from lib.presentation.widgets.charts import (
    build_line_chart_image,
    build_pie_chart_image,
    chart_layout,
)
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.layout import h_chip_row, make_v_scroll
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.responsive import scale_font
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.summary_card import SummaryCard
from lib.presentation.widgets.transaction_tile import TransactionTile
from lib.presentation.widgets.quick_add_sheet import open_quick_add
from lib.presentation.widgets.transfer_sheet import open_transfer
from lib.presentation.widgets.dual_add_button import dual_add_button
from lib.presentation.widgets.budget_summary_ring import budget_list_card

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


# Tests and older call sites still import this name.
_lookup_category = lookup_category


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
        self._account = None
        self._analytics_open = True
        self._analytics_body: ft.Column | None = None
        self._analytics_chevron: ft.Icon | None = None
        self._budgets_open = True
        self._budgets_body: ft.Column | None = None
        self._budgets_chevron: ft.Icon | None = None
        self._last_txs: list = []
        self._last_stats = None
        self._last_period_label = ""
        self._charts_entered_keys: set[str] = set()
        self._sync_btn = ft.IconButton(
            icon=ft.Icons.SYNC,
            icon_color=ft.Colors.PRIMARY,
            tooltip=tr("account.sync.now", state.language),
            visible=False,
            on_click=lambda _e: run_async(page, self._sync_now),
        )
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("account.stats.title", state.language),
                    body=self._body,
                    page=page,
                    extra=[
                        ft.Container(height=42, content=self._period_row),
                    ],
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        self._sync_btn,
                        ft.IconButton(
                            icon=ft.Icons.PICTURE_AS_PDF_OUTLINED,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("account.export_pdf", state.language),
                            on_click=lambda _e: run_async(page, self._open_pdf_export),
                        ),
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
        self._reload_gate.request()

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    def _on_state(self, state: "AppState") -> None:
        token = (
            state.accounts_token
            + state.transactions_token
            + getattr(state, "budgets_token", 0)
        )
        if token != self._token:
            self._reload_gate.request()

    def _toggle_analytics(self, _e: ft.ControlEvent | None = None) -> None:
        self._analytics_open = not self._analytics_open
        if self._analytics_body is not None:
            self._analytics_body.visible = self._analytics_open
            safe_update(self._analytics_body)
        if self._analytics_chevron is not None:
            self._analytics_chevron.name = (
                ft.Icons.KEYBOARD_ARROW_DOWN
                if self._analytics_open
                else ft.Icons.KEYBOARD_ARROW_UP
            )
            safe_update(self._analytics_chevron)

    def _toggle_budgets(self, _e: ft.ControlEvent | None = None) -> None:
        self._budgets_open = not self._budgets_open
        if self._budgets_body is not None:
            self._budgets_body.visible = self._budgets_open
            safe_update(self._budgets_body)
        if self._budgets_chevron is not None:
            self._budgets_chevron.name = (
                ft.Icons.KEYBOARD_ARROW_DOWN
                if self._budgets_open
                else ft.Icons.KEYBOARD_ARROW_UP
            )
            safe_update(self._budgets_chevron)

    def _analytics_header(self, lang: str) -> ft.Control:
        self._analytics_chevron = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN
            if self._analytics_open
            else ft.Icons.KEYBOARD_ARROW_UP,
            size=22,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        return ft.Container(
            ink=True,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            on_click=self._toggle_analytics,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        tr("account.stats.analytics", lang),
                        size=15,
                        weight=ft.FontWeight.W_700,
                    ),
                    self._analytics_chevron,
                ],
            ),
        )

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
            chip.border = None
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
        self._reload_gate.request()

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
            snack_exception(self._page, exc, lang=lang)
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
                    user_facing_error(link.last_error, lang),
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
                        tappable_compact_money(
                            self._page,
                            value,
                            currency,
                            language=lang,
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
        base_currency: str,
        base_converted: Decimal | None,
        lang: str,
        is_corporate: bool = False,
    ) -> ft.Control:
        badge = (
            [
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=999,
                    bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY),
                    content=ft.Text(
                        tr("account.corporate_badge", lang),
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY,
                    ),
                )
            ]
            if is_corporate
            else []
        )
        base_row: list[ft.Control] = []
        if base_converted is not None:
            base_row.append(
                ft.Row(
                    spacing=4,
                    tight=True,
                    controls=[
                        muted_text("≈", size=12),
                        tappable_compact_money(
                            self._page,
                            base_converted,
                            base_currency,
                            language=lang,
                            size=12,
                            weight=ft.FontWeight.W_500,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            compact=False,
                        ),
                    ],
                )
            )
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
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    muted_text(currency, size=12),
                                    *badge,
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        tight=True,
                        wrap=False,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            tappable_compact_money(
                                self._page,
                                balance,
                                currency,
                                language=lang,
                                size=scale_font(28, self._page, maximum=32),
                                weight=ft.FontWeight.W_700,
                                compact=False,
                            ),
                        ],
                    ),
                    *base_row,
                ],
            ),
            padding=16,
        )

    async def _corporate_budgets_section(
        self, account: Account, *, lang: str
    ) -> list[ft.Control]:
        now = datetime.now(timezone.utc)
        month, year = now.month, now.year
        base = self._state.base_currency
        rows: list[ft.Control] = []
        uc = getattr(self._state.container, "get_budgets_for_month", None)
        items = []
        if uc is not None:
            try:
                items = await uc.execute(month, year, account_id=account.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
        if not items:
            rows = []
        for progress in items:
            rows.append(
                budget_list_card(
                    progress,
                    language=lang,
                    currency=base,
                    category_name=localize_category_name(
                        progress.category_id, lang
                    ),
                    compact=True,
                    page=self._page,
                    on_open=lambda p=progress: self._open_corporate_budget_editor(
                        account, p.budget
                    ),
                )
            )

        self._budgets_chevron = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN
            if self._budgets_open
            else ft.Icons.KEYBOARD_ARROW_UP,
            size=22,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        header = ft.Container(
            padding=ft.Padding.symmetric(horizontal=2, vertical=2),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        expand=True,
                        ink=True,
                        border_radius=12,
                        padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                        on_click=self._toggle_budgets,
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    tr("account.corporate_budgets", lang),
                                    size=15,
                                    weight=ft.FontWeight.W_700,
                                    expand=True,
                                ),
                                self._budgets_chevron,
                            ],
                        ),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY_OUTLINED,
                        icon_size=20,
                        icon_color=ft.Colors.PRIMARY,
                        tooltip=tr("budgets.copy_previous", lang),
                        on_click=lambda _e, acc=account: run_async(
                            self._page, self._copy_corporate_budgets, acc
                        ),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_size=20,
                        icon_color=ft.Colors.PRIMARY,
                        tooltip=tr("budgets.add", lang),
                        on_click=lambda _e, acc=account: self._open_corporate_budget_editor(
                            acc
                        ),
                    ),
                ],
            ),
        )
        self._budgets_body = ft.Column(
            spacing=8,
            tight=True,
            visible=self._budgets_open,
            controls=rows,
        )
        return [header, self._budgets_body]

    async def _copy_corporate_budgets(self, account: Account) -> None:
        uc = getattr(self._state.container, "copy_budgets_from_previous", None)
        if uc is None:
            return
        lang = self._state.language
        now = datetime.now(timezone.utc)
        try:
            count = await uc.execute(now.month, now.year, account_id=account.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._state.bump_refresh("dashboard", "budgets", "accounts", "analytics")
        snack(self._page, tr("budgets.copied", lang, count=str(count)))
        self._reload_gate.request(False)

    def _open_corporate_budget_editor(
        self, account: Account, budget: Optional[Budget] = None
    ) -> None:
        run_async(self._page, self._open_corporate_budget_editor_async, account, budget)

    async def _open_corporate_budget_editor_async(
        self, account: Account, budget: Optional[Budget] = None
    ) -> None:
        lang = self._state.language
        now = datetime.now(timezone.utc)
        month, year = now.month, now.year
        picker = CategoryPicker(
            self._page,
            self._state,
            tx_type=TransactionType.EXPENSE.value,
            initial_name=budget.category_id if budget else None,
            account_id=account.id,
        )
        await picker.reload()
        limit_tf = make_amount_field(
            lang,
            label=tr("budgets.limit", lang),
            value=budget.amount_limit if budget else "",
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
        )

        async def _save() -> None:
            name = picker.selected_name
            if not name:
                snack(self._page, tr("budgets.category_required", lang), error=True)
                return
            try:
                limit = parse_amount(limit_tf.value)
            except (InvalidOperation, ValueError):
                snack(self._page, tr("budgets.limit_required", lang), error=True)
                return
            try:
                await self._state.container.set_budget.execute(
                    name, month, year, limit, account_id=account.id
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            close()
            self._state.bump_refresh("budgets", "accounts", "dashboard")
            snack(self._page, tr("budgets.saved", lang))
            self._reload_gate.request(False)

        def _delete() -> None:
            if budget is None:
                return

            async def _do() -> None:
                try:
                    await self._state.container.delete_budget.execute(budget.id)
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                close()
                self._state.bump_refresh("budgets", "accounts")
                self._reload_gate.request(False)

            confirm_dialog(
                self._page,
                title=tr("budgets.delete", lang),
                message=tr(
                    "budgets.delete_confirm", lang, category=budget.category_id
                ),
                confirm_text=tr("budgets.delete", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=_do,
            )

        body = [
            form_section(
                tr("form.section.category", lang),
                [picker, limit_tf],
                icon=ft.Icons.PIE_CHART,
            ),
        ]
        if budget is not None:
            body.append(
                ft.TextButton(
                    tr("budgets.delete", lang),
                    icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    on_click=lambda _e: _delete(),
                )
            )
        close = open_fullscreen_form(
            self._page,
            title=tr("budgets.edit" if budget else "budgets.add", lang),
            lang=lang,
            overlay_key="corporate_budget_form",
            wrap_body=False,
            body=body,
            on_save=_save,
        )

    async def _open_pdf_export(self) -> None:
        lang = self._state.language
        account = self._account
        if account is None:
            snack(self._page, tr("account.export_pdf_need_data", lang), error=True)
            return
        from lib.presentation.widgets.pdf_export_sheet import open_pdf_export_sheet

        try:
            open_pdf_export_sheet(
                self._page,
                lang=lang,
                accounts=[account],
                mode="account",
                locked_account=account,
                default_period=self._period if self._period != "1d" else "30d",
                on_export=self._run_pdf_export,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)

    async def _run_pdf_export(self, choice) -> None:
        lang = self._state.language
        account = self._account
        if account is None:
            snack(self._page, tr("account.export_pdf_need_data", lang), error=True)
            return
        from lib.presentation.file_transfer import offer_saved_file
        from lib.presentation.pdf_export import export_configured_pdf

        try:
            path = await export_configured_pdf(
                self._state.container,
                choice,
                language=lang,
                locked_account=account,
            )
            location = await offer_saved_file(
                self._page, path, title=tr("account.export_pdf", lang)
            )
            snack(
                self._page,
                tr(
                    "account.export_pdf_ok",
                    lang,
                    path=location or str(path),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            raise

    def _edit_tx_from_detail(self, tx) -> None:
        """Edit on this account screen — never jump to global Transactions."""
        lang = self._state.language
        account = self._account

        if getattr(tx, "is_transfer", False):
            self._edit_transfer_leg_local(tx)
            return

        async def _resolve_and_open() -> None:
            lock = account
            if lock is None or getattr(lock, "id", None) != getattr(tx, "account_id", None):
                try:
                    lock = await self._state.container.account_repository.get_by_id(
                        tx.account_id
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
            if lock is None:
                snack(self._page, tr("error.no_accounts", lang), error=True)
                return
            open_quick_add(
                self._page,
                self._state,
                accounts=[lock],
                default_type=tx.type,
                locked_account=lock,
                existing=tx,
                on_saved=lambda: self._reload_gate.request(False),
            )

        run_async(self._page, _resolve_and_open)

    def _edit_transfer_leg_local(self, tx) -> None:
        """Comment/tags only — stay on account detail (no global tab jump)."""
        lang = self._state.language
        amount_tf = make_amount_field(
            lang,
            label=tr("field.amount", lang),
            value=tx.amount,
            read_only=True,
        )
        comment_tf = ft.TextField(
            label=tr("field.comment", lang),
            value=tx.comment or "",
        )
        tags_tf = ft.TextField(
            label=tr("field.tags", lang),
            value=", ".join(
                t for t in (tx.tags or []) if not str(t).startswith("_")
            ),
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(comment_tf, "text")
        configure_field(tags_tf, "text")
        wire_field_chain(self._page, [comment_tf, tags_tf])

        async def _save() -> None:
            tags = [
                p.strip().lstrip("#")
                for p in (tags_tf.value or "").split(",")
                if p.strip()
            ]
            entity = tx.model_copy(
                update={"comment": comment_tf.value or "", "tags": tags}
            )
            try:
                await self._state.container.update_transaction.execute(entity)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            close()
            self._state.bump_refresh(
                "dashboard", "transactions", "accounts", "budgets"
            )
            snack(self._page, tr("action.saved", lang))
            self._reload_gate.request(False)

        close = open_fullscreen_form(
            self._page,
            title=tr("transaction.transfer", lang),
            lang=lang,
            overlay_key="corp_transfer_leg_editor",
            body=[
                muted_text(tr("transfer.edit_hint", lang), size=12),
                amount_tf,
                comment_tf,
                tags_tf,
            ],
            on_save=_save,
        )

    def _confirm_delete_tx(self, tx) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_transaction.execute(tx.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh(
                "dashboard", "transactions", "accounts", "budgets"
            )
            snack(self._page, tr("action.saved", lang))
            self._reload_gate.request(False)

        confirm_dialog(
            self._page,
            title=tr("action.confirm_delete", lang),
            message=(
                tr("transfer.delete_pair", lang)
                if tx.is_transfer
                else (
                    f"{localize_category_name(tx.category, lang)} · "
                    f"{format_money(tx.amount, tx.currency)}"
                )
            ),
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    def _open_tx_detail(self, tx) -> None:
        """Read-only detail with attachments (same idea as transactions page)."""
        from lib.presentation.widgets.attachment_picker import attachment_gallery

        lang = self._state.language
        is_income = tx.type == TransactionType.INCOME
        type_label = tr(
            "transaction.income" if is_income else "transaction.expense",
            lang,
        )
        if tx.is_transfer:
            type_label = tr("transaction.transfer", lang)
        amount_text = format_money(tx.amount, tx.currency)
        amount_text = f"+{amount_text}" if is_income else f"−{amount_text}"
        rows: list[ft.Control] = [
            ft.Text(
                amount_text,
                size=28,
                weight=ft.FontWeight.W_800,
                color=ft.Colors.PRIMARY if is_income or tx.is_transfer else ft.Colors.ERROR,
            ),
            ft.Text(
                localize_category_name(tx.category, lang),
                size=18,
                weight=ft.FontWeight.W_600,
            ),
            ft.Divider(height=16),
            ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(tr("field.type", lang), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(type_label, size=14, weight=ft.FontWeight.W_500),
                ],
            ),
            ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(tr("field.date", lang), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(format_date(tx.date, with_time=True), size=14, weight=ft.FontWeight.W_500),
                ],
            ),
            ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(tr("field.comment", lang), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        tx.comment or tr("tx.no_comment", lang),
                        size=14,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
            ),
            *attachment_gallery(
                list(tx.attachments or []),
                page=self._page,
                lang=lang,
            ),
        ]
        open_fullscreen_form(
            self._page,
            title=tr("tx.detail_title", lang),
            lang=lang,
            overlay_key="account_tx_detail",
            show_save=False,
            body=rows,
        )

    async def reload(self, animate: bool = False) -> None:
        """Load the account and rebuild KPIs / charts."""
        self._token = (
            self._state.accounts_token
            + self._state.transactions_token
            + self._state.budgets_token
        )
        lang = self._state.language
        self._rebuild_period_row(lang)
        # Soft: keep painted body while data loads (no spinner flash / scroll jump).
        fill_loading(self._body, message=tr("action.refresh", lang))

        c = self._state.container
        now = datetime.now(timezone.utc)
        dark = is_dark_mode(self._page, self._state.theme_mode)
        chart_w, chart_h = chart_layout(self._page)
        period_cfg = resolve_analytics_period(self._period, now)
        period_label = tr(f"dashboard.period.{period_cfg.key}", lang)

        try:
            account = await c.account_repository.get_by_id(self._account_id)
            if account is None:
                replace_controls(
                    self._body,
                    [
                        EmptyState(
                            tr("account.stats.missing", lang),
                            icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                        )
                    ],
                    self._page,
                )
                return
            from lib.presentation.tx_query import fetch_transactions_paged

            txs = await fetch_transactions_paged(
                c.list_transactions,
                account_id=account.id,
                date_from=period_cfg.date_from,
                date_to=period_cfg.date_to,
            )
            link = None
            repo = getattr(c, "exchange_connection_repository", None)
            if repo is not None:
                link = await repo.get_by_account_id(account.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            replace_controls(
                self._body,
                [
                    EmptyState(tr("error.generic", lang), icon=ft.Icons.ERROR_OUTLINE)
                ],
                self._page,
            )
            return

        cat_map: dict[str, object] = {}
        list_cats = getattr(c, "list_categories", None)
        if list_cats is not None:
            try:
                scope = account.id if account.is_corporate else ""
                cat_map = index_categories(
                    await list_cats.execute(active_only=False, account_id=scope)
                )
            except Exception:  # noqa: BLE001
                cat_map = {}

        currency = account.currency
        self._account = account
        self._sync_btn.visible = link is not None
        self._sync_btn.tooltip = tr("account.sync.now", lang)
        safe_update(self._sync_btn)
        base = self._state.base_currency
        base_converted: Decimal | None = None
        if currency.upper() != base.upper():
            book = await load_rate_book(c)
            converted = book.convert(account.balance, currency, base)
            if converted is not None:
                base_converted = converted

        stats = aggregate_account_period(txs, period_cfg.group_by)
        self._last_txs = list(txs)
        self._last_stats = stats
        self._last_period_label = period_label
        # Corporate: transfers are part of workspace cash-flow KPIs.
        # Personal: match dashboard — ops only; transfers shown separately.
        if account.is_corporate:
            kpi_income = stats.income
            kpi_expense = stats.expense
        else:
            kpi_income = stats.ops_income
            kpi_expense = stats.ops_expense
        net = kpi_income - kpi_expense
        net_accent = amount_color(net >= 0, dark=dark)

        anim_token = set_ui_animating(animate)
        controls: list[ft.Control] = [
            self._hero(
                name=account.name,
                currency=currency,
                color=account.color or ft.Colors.PRIMARY,
                icon=resolve_account_icon_key(
                    account.icon, link.provider if link else ""
                ),
                balance=account.balance,
                base_currency=base,
                base_converted=base_converted,
                lang=lang,
                is_corporate=account.is_corporate,
            ),
            dual_add_button(
                lang,
                page=self._page,
                on_expense=lambda: open_quick_add(
                    self._page,
                    self._state,
                    accounts=[account],
                    default_type=TransactionType.EXPENSE,
                    locked_account=account,
                    on_saved=lambda: self._reload_gate.request(False),
                ),
                on_income=lambda: open_quick_add(
                    self._page,
                    self._state,
                    accounts=[account],
                    default_type=TransactionType.INCOME,
                    locked_account=account,
                    on_saved=lambda: self._reload_gate.request(False),
                ),
            ),
            ft.OutlinedButton(
                tr("transaction.transfer", lang),
                icon=ft.Icons.SWAP_HORIZ,
                expand=True,
                on_click=lambda _e, acc=account: open_transfer(
                    self._page,
                    self._state,
                    default_from_id=acc.id,
                    include_corporate=True,
                    on_saved=lambda: self._reload_gate.request(False),
                ),
            ),
        ]
        if link is not None:
            controls.append(self._exchange_section(link, currency=currency, lang=lang))

        if account.is_corporate:
            controls.extend(
                await self._corporate_budgets_section(account, lang=lang)
            )

        analytics_children: list[ft.Control] = [
            section_title(tr("dashboard.period_summary", lang, period=period_label)),
            ft.Row(
                spacing=10,
                controls=[
                    SummaryCard(
                        title=tr("transaction.income", lang),
                        value=format_money(kpi_income, currency),
                        icon=ft.Icons.TRENDING_UP,
                        accent=amount_color(True, dark=dark),
                        expand=True,
                        dark=dark,
                        amount=kpi_income,
                        currency=currency,
                        compact=False,
                        page=self._page,
                        language=lang,
                        columns=2,
                    ),
                    SummaryCard(
                        title=tr("transaction.expense", lang),
                        value=format_money(kpi_expense, currency),
                        icon=ft.Icons.TRENDING_DOWN,
                        accent=amount_color(False, dark=dark),
                        expand=True,
                        dark=dark,
                        amount=kpi_expense,
                        currency=currency,
                        compact=False,
                        page=self._page,
                        language=lang,
                        columns=2,
                    ),
                ],
            ),
            card_surface(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    wrap=False,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                muted_text(
                                    tr("dashboard.net", lang),
                                    size=12,
                                ),
                                tappable_compact_money(
                                    self._page,
                                    net,
                                    currency,
                                    signed=True,
                                    language=lang,
                                    size=16,
                                    color=net_accent,
                                    compact=False,
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

        if stats.transfer_in > 0 or stats.transfer_out > 0:
            analytics_children.append(
                card_surface(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=8,
                        controls=[
                            ft.Column(
                                expand=True,
                                spacing=2,
                                tight=True,
                                controls=[
                                    muted_text(
                                        tr("account.stats.transfer_in", lang),
                                        size=11,
                                    ),
                                    tappable_compact_money(
                                        self._page,
                                        stats.transfer_in,
                                        currency,
                                        language=lang,
                                        size=13,
                                        color=amount_color(True, dark=dark),
                                    ),
                                ],
                            ),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                                controls=[
                                    muted_text(
                                        tr("account.stats.transfer_out", lang),
                                        size=11,
                                    ),
                                    tappable_compact_money(
                                        self._page,
                                        stats.transfer_out,
                                        currency,
                                        language=lang,
                                        size=13,
                                        color=amount_color(False, dark=dark),
                                        text_align=ft.TextAlign.END,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    padding=14,
                )
            )

        if not txs:
            analytics_children.append(
                EmptyState(
                    tr("account.stats.empty", lang),
                    icon=ft.Icons.ANALYTICS_OUTLINED,
                )
            )
            self._analytics_body = ft.Column(
                spacing=12,
                tight=True,
                visible=self._analytics_open,
                controls=analytics_children,
            )
            controls.extend(
                [self._analytics_header(lang), self._analytics_body]
            )
            replace_controls(self._body, controls, self._page)
            try:
                if animate:
                    await play_count_ups(self._body, self._page)
            finally:
                reset_ui_animating(anim_token)
                await flush_chart_draws()
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
            animate=bool(animate),
        )
        pie = chart_enter(
            self,
            pie,
            self._page,
            refresh=bool(animate),
            key="pie",
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
            animate=bool(animate),
        )
        line = chart_enter(
            self,
            line,
            self._page,
            refresh=bool(animate),
            key="line",
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
                        ft.Row(
                            spacing=4,
                            tight=True,
                            controls=[
                                tappable_compact_money(
                                    self._page,
                                    amount,
                                    currency,
                                    language=lang,
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    f"({share:.0f}%)",
                                    size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    weight=ft.FontWeight.W_600,
                                    no_wrap=True,
                                ),
                            ],
                        ),
                    ],
                )
            )

        analytics_children.extend(
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
                            line,
                        ],
                    ),
                    padding=12,
                ),
            ]
        )
        self._analytics_body = ft.Column(
            spacing=12,
            tight=True,
            visible=self._analytics_open,
            controls=analytics_children,
        )
        controls.extend([self._analytics_header(lang), self._analytics_body])
        controls.append(section_title(tr("account.stats.recent", lang)))
        for tx in txs[:10]:
            controls.append(
                TransactionTile(
                    tx,
                    category=_lookup_category(cat_map, tx.category),
                    language=lang,
                    page=self._page,
                    on_open=self._open_tx_detail,
                    on_edit=self._edit_tx_from_detail,
                    on_delete=self._confirm_delete_tx,
                )
            )
        replace_controls(self._body, controls, self._page)
        try:
            if animate:
                await play_count_ups(self._body, self._page)
        finally:
            reset_ui_animating(anim_token)
            await flush_chart_draws()
