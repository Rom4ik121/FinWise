"""Transactions list page with search, filters, grouping, and CRUD dialogs."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.core.config import DEFAULT_SAVINGS_CATEGORY, SAVINGS_CATEGORIES, normalize_savings_category
from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.use_cases.goals import strip_goal_allocation_tags
from lib.domain.use_cases.transactions import FEE_CATEGORY, StatsPeriod, make_fee_expense
from lib.infrastructure.services.localization import localize_category_name
from lib.infrastructure.services.notification_service import NotificationKind
from lib.presentation.category_lookup import index_categories, lookup_category
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.count_up import mark_money_text, play_count_ups
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.dropdown_options import icon_dropdown_option
from lib.presentation.frequent_account import prepare_tx_account_choices
from lib.presentation.money_input import (
    make_amount_field,
    parse_amount,
    parse_optional_amount,
)
from lib.presentation.utils import format_date, format_money, run_async, safe_update, snack, snack_exception, tr, bind_dropdown_select
from lib.presentation.form_validation import require_positive_amount
from lib.presentation.widgets.account_strip_picker import AccountStripPicker
from lib.presentation.widgets.category_picker import CategoryPicker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.layout import make_v_scroll
from lib.presentation.ui_motion import replace_controls
from lib.presentation.widgets.line_items_editor import LineItemsEditor
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.transaction_tile import TransactionTile

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_PAGE_SIZE = 60


def _parse_date(value: str, *, end_of_day: bool = False) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            if fmt == "%Y-%m-%d" and end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise ValueError("invalid date")


def _period_key(dt: datetime, group_by: str) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if group_by == StatsPeriod.WEEK.value:
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if group_by == StatsPeriod.MONTH.value:
        return dt.strftime("%Y-%m")
    return format_date(dt)


def _user_tags(tx: Transaction) -> list[str]:
    """Tags safe to show/edit — hide internal goal allocation markers."""
    return strip_goal_allocation_tags(tx.tags)


class TransactionsPage(ft.Column):
    """Searchable / filterable transaction list with day/week/month grouping."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._token = -1
        self._meta_token = -1
        self._accounts: list = []
        self._corporate_ids: set[str] = set()
        self._goals: list = []
        self._category_map: dict[str, object] = {}
        self._list = make_v_scroll(spacing=6)
        self._offset = 0
        self._has_more = False
        self._shown: list[Transaction] = []
        self._search_gen = 0
        self._last_group: str | None = None
        lang = state.language
        self._search = ft.TextField(
            label=tr("field.search", lang),
            prefix_icon=ft.Icons.SEARCH,
            on_change=lambda _e: run_async(page, self._debounced_search),
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            expand=True,
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(self._search, "search")
        wire_field_chain(page, [self._search])

        # --- Day / range navigator ---
        self._selected_date: date = date.today()
        self._range_mode = False  # True when user sets date_from/date_to in filters
        self._range_from: date | None = None
        self._range_to: date | None = None
        self._day_label = ft.Text(
            self._format_day_label(lang),
            weight=ft.FontWeight.W_700,
            size=15,
            expand=True,
            text_align=ft.TextAlign.CENTER,
        )
        self._nav_prev = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            on_click=lambda _e: self._shift_day(-1),
        )
        self._nav_next = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            on_click=lambda _e: self._shift_day(1),
        )
        self._day_nav = ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self._nav_prev,
                self._day_label,
                self._nav_next,
            ],
        )

        # Filter values (controls are created fresh inside the dialog).
        self._type_value = "all"
        self._category_value = "all"
        self._account_value = "all"
        self._amount_min_value = ""
        self._amount_max_value = ""
        _init_fr, _init_to = self._day_date_range()
        self._date_from_value = _init_fr
        self._date_to_value = _init_to
        self._group_by_value = StatsPeriod.DAY.value
        self._filter_summary = ft.Text(
            "",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
            expand=True,
        )
        from lib.presentation.responsive import scale_space

        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.transactions", lang),
                    body=self._list,
                    page=page,
                    extra=[
                        ft.Column(
                            spacing=scale_space(8, page),
                            tight=True,
                            controls=[
                                self._search,
                                self._day_nav,
                            ],
                        ),
                    ],
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.TUNE,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.filters", lang),
                            on_click=lambda _e: self._open_filters(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.UPLOAD_FILE,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.import_csv", lang),
                            on_click=lambda _e: self._state.open_secondary("import_csv"),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", lang),
                            on_click=lambda _e: self._reload_gate.request(True),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.add", lang),
                            on_click=lambda _e: run_async(page, self._open_editor_async),
                        ),
                    ],
                ),
                page=page,
            )
        )
        state.subscribe(self._on_state)
        self._reload_gate = ReloadGate(page, self, self.reload)
        self._restore_filters()
        pending_q = getattr(state, "pending_tx_query", None)
        if pending_q:
            self._search.value = pending_q
            state.pending_tx_query = None
        self._reload_gate.request()

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    def _on_state(self, state: "AppState") -> None:
        if state.transactions_token != self._token:
            self._reload_gate.request()

    # --- Day navigation ---

    def _format_day_label(self, lang: str) -> str:
        if self._range_mode and self._range_from and self._range_to:
            return self._format_range_label(self._range_from, self._range_to, lang)
        d = self._selected_date
        today = date.today()
        yesterday = today - timedelta(days=1)
        month = tr(f"date.month.{d.month}", lang)
        if d == today:
            return f"{tr('date.today', lang)}, {d.day} {month}"
        if d == yesterday:
            return f"{tr('date.yesterday', lang)}, {d.day} {month}"
        return f"{d.day} {month} {d.year}"

    def _format_range_label(self, fr: date, to: date, lang: str) -> str:
        f_str = f"{fr.day} {tr(f'date.month.{fr.month}', lang)}"
        t_str = f"{to.day} {tr(f'date.month.{to.month}', lang)}"
        if fr.year != to.year:
            f_str += f" {fr.year}"
            t_str += f" {to.year}"
        return f"{f_str} – {t_str}"

    def _shift_day(self, delta: int) -> None:
        if self._range_mode and self._range_from and self._range_to:
            span = (self._range_to - self._range_from).days + 1
            shift = timedelta(days=span * delta)
            self._range_from += shift
            self._range_to += shift
        else:
            self._selected_date += timedelta(days=delta)
        self._apply_day_filter()

    def _day_date_range(self) -> tuple[str, str]:
        """UTC date window that fully covers the selected local day or range."""
        if self._range_mode and self._range_from and self._range_to:
            return (
                (self._range_from - timedelta(days=1)).strftime("%Y-%m-%d"),
                (self._range_to + timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        d = self._selected_date
        return (
            (d - timedelta(days=1)).strftime("%Y-%m-%d"),
            (d + timedelta(days=1)).strftime("%Y-%m-%d"),
        )

    @staticmethod
    def _tx_local_date(tx: Transaction) -> date:
        dt = tx.date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().date()

    def _tx_in_selected_range(self, tx: Transaction) -> bool:
        """Check if a transaction falls within the selected day or range."""
        local = self._tx_local_date(tx)
        if self._range_mode and self._range_from and self._range_to:
            return self._range_from <= local <= self._range_to
        return local == self._selected_date

    def _apply_day_filter(self) -> None:
        lang = self._state.language
        fr, to = self._day_date_range()
        self._date_from_value = fr
        self._date_to_value = to
        self._day_label.value = self._format_day_label(lang)
        safe_update(self._day_label)
        self._reload_gate.request()

    def _dump_filters(self) -> dict:
        return {
            "type": self._type_value,
            "category": self._category_value,
            "account": self._account_value,
            "amount_min": self._amount_min_value,
            "amount_max": self._amount_max_value,
            "group_by": self._group_by_value,
            "range_mode": bool(self._range_mode),
            "range_from": self._range_from.isoformat() if self._range_from else None,
            "range_to": self._range_to.isoformat() if self._range_to else None,
            "selected_date": self._selected_date.isoformat(),
        }

    def _restore_filters(self) -> None:
        data = getattr(self._state, "tx_filter_state", None)
        if not data:
            raw = getattr(self._state.settings, "tx_filters_json", None)
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
        if not isinstance(data, dict):
            return
        self._type_value = str(data.get("type") or "all")
        self._category_value = str(data.get("category") or "all")
        self._account_value = str(data.get("account") or "all")
        self._amount_min_value = str(data.get("amount_min") or "")
        self._amount_max_value = str(data.get("amount_max") or "")
        self._group_by_value = str(data.get("group_by") or StatsPeriod.DAY.value)
        self._range_mode = bool(data.get("range_mode"))
        try:
            fr = data.get("range_from")
            to = data.get("range_to")
            self._range_from = date.fromisoformat(fr) if fr else None
            self._range_to = date.fromisoformat(to) if to else None
            sel = data.get("selected_date")
            if sel:
                self._selected_date = date.fromisoformat(str(sel))
        except ValueError:
            self._range_mode = False
        fr, to = self._day_date_range()
        self._date_from_value = fr
        self._date_to_value = to

    def _filters_active(self) -> bool:
        if (self._search.value or "").strip():
            return True
        if self._type_value not in (None, "all"):
            return True
        if self._category_value not in (None, "all"):
            return True
        if self._account_value not in (None, "all"):
            return True
        if (self._amount_min_value or "").strip() or (self._amount_max_value or "").strip():
            return True
        if self._range_mode:
            return True
        return False

    def _clear_all_filters(self) -> None:
        self._type_value = "all"
        self._category_value = "all"
        self._account_value = "all"
        self._amount_min_value = ""
        self._amount_max_value = ""
        self._group_by_value = StatsPeriod.DAY.value
        self._range_mode = False
        self._range_from = None
        self._range_to = None
        self._selected_date = date.today()
        self._search.value = ""
        self._apply_day_filter()
        run_async(self._page, self._persist_filters)

    async def _persist_filters(self) -> None:
        payload = self._dump_filters()
        self._state.tx_filter_state = payload
        uc = getattr(self._state.container, "update_settings", None)
        if uc is None:
            return
        try:
            current = self._state.settings
            saved = await uc.execute(
                current.model_copy(update={"tx_filters_json": json.dumps(payload)})
            )
            self._state.set_settings(saved, notify=False)
        except Exception:  # noqa: BLE001
            pass

    def _filter_summary_text(self) -> str:
        lang = self._state.language
        parts: list[str] = []
        if self._type_value not in (None, "all"):
            if self._type_value == "transfer":
                key = "transaction.transfer"
            else:
                key = (
                    "transaction.income"
                    if self._type_value == TransactionType.INCOME.value
                    else "transaction.expense"
                )
            parts.append(tr(key, lang))
        if self._category_value not in (None, "all"):
            parts.append(str(self._category_value))
        if self._account_value not in (None, "all"):
            acc = next((a for a in self._accounts if a.id == self._account_value), None)
            parts.append(acc.name if acc is not None else self._account_value)
        if (self._amount_min_value or "").strip() or (self._amount_max_value or "").strip():
            parts.append(
                f"{self._amount_min_value.strip() or '…'}–{self._amount_max_value.strip() or '…'}"
            )
        if self._date_from_value.strip() or self._date_to_value.strip():
            parts.append(
                f"{self._date_from_value.strip() or '…'} – "
                f"{self._date_to_value.strip() or '…'}"
            )
        group_label = {
            StatsPeriod.DAY.value: tr("filter.group.day", lang),
            StatsPeriod.WEEK.value: tr("filter.group.week", lang),
            StatsPeriod.MONTH.value: tr("filter.group.month", lang),
        }.get(self._group_by_value, self._group_by_value)
        parts.append(group_label)
        return " · ".join(parts)

    def _open_filters(self) -> None:
        run_async(self._page, self._open_filters_async)

    async def _open_filters_async(self) -> None:
        lang = self._state.language
        type_dd = ft.Dropdown(
            label=tr("field.type", lang),
            value=self._type_value,
            options=[
                icon_dropdown_option(
                    "all", tr("filter.all", lang), ft.Icons.FILTER_LIST
                ),
                icon_dropdown_option(
                    TransactionType.INCOME.value,
                    tr("transaction.income", lang),
                    ft.Icons.ARROW_DOWNWARD,
                    icon_color=ft.Colors.PRIMARY,
                ),
                icon_dropdown_option(
                    TransactionType.EXPENSE.value,
                    tr("transaction.expense", lang),
                    ft.Icons.ARROW_UPWARD,
                    icon_color=ft.Colors.ERROR,
                ),
                icon_dropdown_option(
                    "transfer",
                    tr("transaction.transfer", lang),
                    ft.Icons.SWAP_HORIZ,
                ),
            ],
            dense=True,
            expand=True,
        )
        cat_names: list[str] = []
        if self._state.container.list_categories is not None:
            cats = await self._state.container.list_categories.execute()
            cat_names = [c.name for c in cats]
        category_dd = ft.Dropdown(
            label=tr("field.category", lang),
            value=self._category_value,
            options=[ft.DropdownOption(key="all", text=tr("filter.all", lang))]
            + [ft.DropdownOption(key=c, text=c) for c in cat_names],
            dense=True,
            expand=True,
        )
        await self._ensure_meta()
        account_dd = ft.Dropdown(
            label=tr("filter.account", lang),
            value=self._account_value if self._account_value else "all",
            options=[ft.DropdownOption(key="all", text=tr("filter.all", lang))]
            + [ft.DropdownOption(key=a.id, text=a.name) for a in self._accounts],
            dense=True,
            expand=True,
        )
        amount_min_tf = make_amount_field(
            lang,
            label=tr("filter.amount_min", lang),
            value=self._amount_min_value,
        )
        amount_max_tf = make_amount_field(
            lang,
            label=tr("filter.amount_max", lang),
            value=self._amount_max_value,
        )

        group_dd = ft.Dropdown(
            label=tr("filter.group_by", lang),
            value=self._group_by_value,
            options=[
                icon_dropdown_option(
                    StatsPeriod.DAY.value,
                    tr("filter.group.day", lang),
                    ft.Icons.TODAY,
                ),
                icon_dropdown_option(
                    StatsPeriod.WEEK.value,
                    tr("filter.group.week", lang),
                    ft.Icons.DATE_RANGE,
                ),
                icon_dropdown_option(
                    StatsPeriod.MONTH.value,
                    tr("filter.group.month", lang),
                    ft.Icons.CALENDAR_MONTH,
                ),
            ],
            dense=True,
            expand=True,
        )
        _df_init = (
            datetime.combine(self._range_from, datetime.min.time()).replace(tzinfo=timezone.utc)
            if self._range_mode and self._range_from
            else None
        )
        _dt_init = (
            datetime.combine(self._range_to, datetime.min.time()).replace(tzinfo=timezone.utc)
            if self._range_mode and self._range_to
            else None
        )
        date_from = DateTimeField(
            self._page,
            lang=lang,
            label=tr("filter.date_from", lang),
            value=_df_init,
            allow_clear=True,
        )
        date_to = DateTimeField(
            self._page,
            lang=lang,
            label=tr("filter.date_to", lang),
            value=_dt_init,
            allow_clear=True,
        )
        close_holder: dict = {}

        def _stamp_fields() -> None:
            self._type_value = type_dd.value or "all"
            self._category_value = category_dd.value or "all"
            self._account_value = account_dd.value or "all"
            self._amount_min_value = (amount_min_tf.value or "").strip()
            self._amount_max_value = (amount_max_tf.value or "").strip()
            self._group_by_value = group_dd.value or StatsPeriod.DAY.value

        def _apply_preset(days: int | None) -> None:
            today = date.today()
            if days is None:
                self._range_from = today - timedelta(days=365 * 5)
                self._range_to = today
            else:
                self._range_from = today - timedelta(days=int(days))
                self._range_to = today
            self._range_mode = True
            _stamp_fields()
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            self._apply_day_filter()
            run_async(self._page, self._persist_filters)

        period_row = ft.Row(
            spacing=6,
            wrap=True,
            controls=[
                ft.TextButton(tr("filter.period.7d", lang), on_click=lambda _e: _apply_preset(7)),
                ft.TextButton(tr("filter.period.30d", lang), on_click=lambda _e: _apply_preset(30)),
                ft.TextButton(tr("filter.period.90d", lang), on_click=lambda _e: _apply_preset(90)),
                ft.TextButton(tr("filter.period.365d", lang), on_click=lambda _e: _apply_preset(365)),
                ft.TextButton(tr("filter.period.all", lang), on_click=lambda _e: _apply_preset(None)),
            ],
        )

        async def _apply() -> None:
            _stamp_fields()
            df_text = date_from.date_text.strip()
            dt_text = date_to.date_text.strip()
            if df_text and dt_text:
                try:
                    self._range_from = datetime.strptime(df_text[:10], "%Y-%m-%d").date()
                    self._range_to = datetime.strptime(dt_text[:10], "%Y-%m-%d").date()
                    if self._range_from > self._range_to:
                        self._range_from, self._range_to = (
                            self._range_to,
                            self._range_from,
                        )
                    if (self._range_to - self._range_from).days > 365 * 5:
                        self._range_from = self._range_to - timedelta(days=365 * 5)
                    self._range_mode = True
                except ValueError:
                    self._range_mode = False
            elif df_text or dt_text:
                self._range_mode = False
            close()
            self._apply_day_filter()
            await self._persist_filters()

        def _reset(_e: ft.ControlEvent | None = None) -> None:
            self._type_value = "all"
            self._category_value = "all"
            self._account_value = "all"
            self._amount_min_value = ""
            self._amount_max_value = ""
            self._group_by_value = StatsPeriod.DAY.value
            self._range_mode = False
            self._range_from = None
            self._range_to = None
            self._selected_date = date.today()
            self._search.value = ""
            close()
            self._apply_day_filter()
            run_async(self._page, self._persist_filters)

        close = open_fullscreen_form(
            self._page,
            title=tr("action.filters", lang),
            lang=lang,
            overlay_key="transaction_filters",
            save_label=tr("action.apply", lang),
            body=[
                type_dd,
                category_dd,
                account_dd,
                amount_min_tf,
                amount_max_tf,
                group_dd,
                period_row,
                date_from,
                date_to,
                ft.OutlinedButton(
                    tr("filter.clear_all", lang),
                    icon=ft.Icons.RESTART_ALT,
                    on_click=_reset,
                ),
            ],
            on_save=_apply,
        )
        close_holder["close"] = close

    async def _debounced_search(self) -> None:
        """Wait briefly so typing does not reload on every keystroke."""
        self._search_gen += 1
        gen = self._search_gen
        await asyncio.sleep(0.35)
        if gen != self._search_gen:
            return
        await self.reload()

    async def _ensure_meta(self) -> None:
        """Load accounts / goals / categories only when data tokens change."""
        token = self._state.transactions_token
        if self._meta_token == token and self._accounts:
            return
        c = self._state.container
        self._accounts = await c.list_accounts.execute(
            active_only=True, corporate=False
        )
        corporate = await c.list_accounts.execute(corporate=True)
        self._corporate_ids = {a.id for a in corporate}
        self._goals = await c.list_goals.execute(include_completed=False)
        if c.list_categories is not None:
            cats = await c.list_categories.execute(active_only=False)
            self._category_map = index_categories(cats)
        self._meta_token = token

    def _list_filters(self) -> dict:
        """Shared list() kwargs for type / category / account / amount filters."""
        category = None
        if self._category_value not in (None, "all"):
            category = self._category_value
        filters: dict = {"category": category}
        if self._account_value not in (None, "all"):
            filters["account_id"] = self._account_value
        amin = parse_optional_amount(self._amount_min_value)
        amax = parse_optional_amount(self._amount_max_value)
        if amin is not None:
            filters["amount_min"] = amin
        if amax is not None:
            filters["amount_max"] = amax
        if self._type_value == "transfer":
            filters["has_transfer"] = True
        elif self._type_value not in (None, "all"):
            filters["transaction_type"] = TransactionType(self._type_value)
            filters["has_transfer"] = False
        return filters

    def _load_more_button(self, lang: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=8),
            content=ft.OutlinedButton(
                tr("action.load_more", lang),
                icon=ft.Icons.EXPAND_MORE,
                on_click=lambda _e: run_async(self._page, self._load_more),
            ),
            alignment=ft.Alignment.CENTER,
        )

    def _render_list(
        self,
        items: list[Transaction],
        *,
        lang: str,
        incremental: bool = False,
    ) -> None:
        if not items and not incremental:
            if self._filters_active():
                replace_controls(
                    self._list,
                    [
                        EmptyState(
                            tr("empty.transactions_filtered", lang),
                            icon=ft.Icons.FILTER_ALT_OFF,
                            action_label=tr("filter.clear_all", lang),
                            on_action=lambda _e: self._clear_all_filters(),
                            page=self._page,
                        )
                    ],
                    self._page,
                )
            else:
                replace_controls(
                    self._list,
                    [
                        EmptyState(
                            tr("empty.transactions", lang),
                            action_label=tr("action.add", lang),
                            on_action=lambda _e: run_async(
                                self._page, self._open_editor_async
                            ),
                            page=self._page,
                        )
                    ],
                    self._page,
                )
            self._last_group = None
            return

        if not incremental:
            self._last_group = None
        extra = self._build_item_controls(items, lang=lang)
        if self._has_more:
            extra.append(self._load_more_button(lang))
        if incremental and self._list.controls:
            last = self._list.controls[-1]
            if isinstance(last, ft.Container):
                self._list.controls.pop()
            self._list.controls.extend(extra)
            safe_update(self._list)
            return
        replace_controls(self._list, extra, self._page)

    def _build_item_controls(
        self, items: list[Transaction], *, lang: str
    ) -> list[ft.Control]:
        if not items:
            return []
        group_mode = self._group_by_value or StatsPeriod.DAY.value
        grouped: dict[str, list[Transaction]] = defaultdict(list)
        for tx in items:
            grouped[_period_key(tx.date, group_mode)].append(tx)

        extra: list[ft.Control] = []
        for period, period_items in grouped.items():
            if period != self._last_group:
                extra.append(
                    ft.Text(
                        period,
                        weight=ft.FontWeight.W_700,
                        size=13,
                        color=ft.Colors.PRIMARY,
                    )
                )
            self._last_group = period
            for tx in period_items:
                extra.append(
                    TransactionTile(
                        tx,
                        category=lookup_category(self._category_map, tx.category),  # type: ignore[arg-type]
                        language=lang,
                        page=self._page,
                        on_open=self._open_detail,
                        on_edit=lambda t: run_async(
                            self._page, self._open_editor_async, t
                        ),
                        on_delete=self._confirm_delete,
                    )
                )
        return extra

    async def _load_more(self) -> None:
        """Append the next page of transactions."""
        if not self._has_more:
            return
        lang = self._state.language
        query = (self._search.value or "").strip()
        c = self._state.container
        try:
            date_from = _parse_date(self._date_from_value)
            date_to = _parse_date(self._date_to_value, end_of_day=True)
        except ValueError:
            return
        try:
            rows = await c.list_transactions.execute(
                date_from=date_from,
                date_to=date_to,
                query=query or None,
                limit=_PAGE_SIZE + 1,
                offset=self._offset,
                **self._list_filters(),
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        rows = [
            tx
            for tx in rows
            if getattr(tx, "account_id", None) not in self._corporate_ids
        ]
        self._has_more = len(rows) > _PAGE_SIZE
        chunk = rows[:_PAGE_SIZE]
        self._shown.extend(chunk)
        self._offset += len(chunk)
        self._render_list(chunk, lang=lang, incremental=True)

    async def reload(self, animate: bool = False) -> None:
        """Reload the first page of filtered transactions."""
        self._token = self._state.transactions_token
        lang = self._state.language
        pending_q = getattr(self._state, "pending_tx_query", None)
        if pending_q:
            self._search.value = pending_q
            self._state.pending_tx_query = None
        self._filter_summary.value = self._filter_summary_text()
        had_list = bool(self._list.controls)
        # Avoid spinner flash when the list already has tiles (search storms).
        if not had_list:
            fill_loading(self._list)
        safe_update(self._filter_summary)

        c = self._state.container
        try:
            date_from = _parse_date(self._date_from_value)
            date_to = _parse_date(self._date_to_value, end_of_day=True)
        except ValueError:
            snack(self._page, tr("invalid_date", lang), error=True)
            replace_controls(
                self._list, [EmptyState(tr("invalid_date", lang))], self._page
            )
            return

        try:
            await self._ensure_meta()
            query = (self._search.value or "").strip()
            filters = self._list_filters()
            rows = await c.list_transactions.execute(
                date_from=date_from,
                date_to=date_to,
                query=query or None,
                limit=_PAGE_SIZE + 1,
                offset=0,
                **filters,
            )
            rows = [tx for tx in rows if self._tx_in_selected_range(tx)]
            rows = [
                tx
                for tx in rows
                if getattr(tx, "account_id", None) not in self._corporate_ids
            ]
            self._has_more = len(rows) > _PAGE_SIZE
            self._shown = rows[:_PAGE_SIZE]
            self._offset = len(self._shown)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            replace_controls(
                self._list, [EmptyState(tr("error.generic", lang))], self._page
            )
            return

        self._render_list(self._shown, lang=lang)
        pending_id = getattr(self._state, "pending_edit_transaction_id", None)
        if pending_id:
            self._state.pending_edit_transaction_id = None
            target = next((t for t in self._shown if t.id == pending_id), None)
            if target is None:
                repo = getattr(c, "transaction_repository", None)
                if repo is not None:
                    try:
                        target = await repo.get_by_id(pending_id)
                    except Exception:  # noqa: BLE001
                        target = None
            if target is not None:
                # Align day filter to the transaction so the list stays coherent.
                self._selected_date = self._tx_local_date(target)
                self._range_mode = False
                run_async(self._page, self._open_editor_async, target)
        if animate:
            await play_count_ups(self._list, self._page)

    def _open_detail(self, tx: Transaction) -> None:
        """Show a read-only detail sheet; edit/delete from actions."""
        lang = self._state.language
        account_name = next(
            (a.name for a in self._accounts if a.id == tx.account_id),
            tx.account_id,
        )
        is_income = tx.type == TransactionType.INCOME
        type_label = tr(
            "transaction.income" if is_income else "transaction.expense",
            lang,
        )
        if tx.is_transfer:
            type_label = tr("transaction.transfer", lang)
        amount_text = format_money(tx.amount, tx.currency)
        if not is_income:
            amount_text = f"−{amount_text}"
        else:
            amount_text = f"+{amount_text}"

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
            self._detail_row(tr("field.type", lang), type_label),
            self._detail_row(tr("field.account", lang), account_name),
            self._detail_row(
                tr("field.date", lang),
                format_date(tx.date, with_time=True),
            ),
            self._detail_row(
                tr("field.comment", lang),
                tx.comment or tr("tx.no_comment", lang),
            ),
        ]
        from lib.presentation.widgets.attachment_picker import attachment_gallery

        rows.extend(
            attachment_gallery(
                list(tx.attachments or []),
                page=self._page,
                lang=lang,
            )
        )
        if _user_tags(tx):
            rows.append(
                self._detail_row(
                    tr("field.tags", lang),
                    ", ".join(f"#{t}" for t in _user_tags(tx)),
                )
            )
        if tx.has_items:
            rows.append(ft.Divider(height=12))
            rows.append(
                ft.Text(
                    tr("tx.items", lang),
                    weight=ft.FontWeight.W_700,
                    size=14,
                )
            )
            for item in tx.items:
                rows.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border_radius=10,
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Column(
                                    spacing=2,
                                    tight=True,
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            item.name or item.category,
                                            weight=ft.FontWeight.W_600,
                                            size=13,
                                        ),
                                        ft.Text(
                                            localize_category_name(
                                                item.category or tx.category, lang
                                            ),
                                            size=11,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                ),
                                ft.Text(
                                    format_money(item.amount, tx.currency),
                                    weight=ft.FontWeight.W_700,
                                    size=13,
                                ),
                            ],
                        ),
                    )
                )

        def _edit(_e: ft.ControlEvent | None = None) -> None:
            close()
            run_async(self._page, self._open_editor_async, tx)

        def _delete(_e: ft.ControlEvent | None = None) -> None:
            close()
            self._confirm_delete(tx)

        rows.append(ft.Container(height=8))
        rows.append(
            ft.Row(
                spacing=10,
                controls=[
                    ft.FilledButton(
                        tr("action.edit", lang),
                        icon=ft.Icons.EDIT_OUTLINED,
                        expand=True,
                        on_click=_edit,
                    ),
                    ft.OutlinedButton(
                        tr("action.delete", lang),
                        icon=ft.Icons.DELETE_OUTLINE,
                        expand=True,
                        on_click=_delete,
                    ),
                ],
            )
        )

        close = open_fullscreen_form(
            self._page,
            title=tr("tx.detail_title", lang),
            lang=lang,
            overlay_key="transaction_detail",
            show_save=False,
            body=rows,
        )

    @staticmethod
    def _detail_row(label: str, value: str) -> ft.Control:
        return ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(value, size=14, weight=ft.FontWeight.W_500),
            ],
        )

    def _confirm_delete(self, tx: Transaction) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_transaction.execute(tx.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "transactions", "accounts", "budgets")
            snack(self._page, tr("action.saved", lang))

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

    def _open_series(self, tx: Transaction) -> None:
        if not tx.subscription_id:
            return
        self._state.pending_edit_subscription_id = tx.subscription_id
        self._state.open_secondary("subscriptions")

    async def _open_editor_async(self, tx: Optional[Transaction] = None) -> None:
        """Always refresh accounts/goals, then open the editor."""
        lang = self._state.language
        try:
            self._accounts = await self._state.container.list_accounts.execute(active_only=True, corporate=False)
            self._goals = await self._state.container.list_goals.execute(
                include_completed=False
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return

        accounts = self._accounts
        if not accounts:
            snack(self._page, tr("empty.accounts", lang), error=True)
            return

        if tx is not None and tx.is_transfer:
            await self._open_transfer_editor(tx)
            return

        frequent_id: str | None = None
        if tx is None:
            accounts, default_account_id = await prepare_tx_account_choices(
                self._state, accounts
            )
            frequent_id = default_account_id
        else:
            default_account_id = tx.account_id
            _, frequent_id = await prepare_tx_account_choices(self._state, accounts)
            if default_account_id not in {a.id for a in accounts}:
                # Never silently remap a corporate (or missing) account to personal.
                try:
                    owned = await self._state.container.account_repository.get_by_id(
                        default_account_id
                    )
                except Exception:  # noqa: BLE001
                    owned = None
                if owned is not None:
                    accounts = [owned, *accounts]
                else:
                    snack(
                        self._page,
                        tr("error.no_accounts", lang),
                        error=True,
                    )
                    return

        type_dd = ft.Dropdown(
            label=tr("field.type", lang),
            value=(tx.type.value if tx else TransactionType.EXPENSE.value),
            options=[
                icon_dropdown_option(
                    TransactionType.EXPENSE.value,
                    tr("transaction.expense", lang),
                    ft.Icons.ARROW_UPWARD,
                    icon_color=ft.Colors.ERROR,
                ),
                icon_dropdown_option(
                    TransactionType.INCOME.value,
                    tr("transaction.income", lang),
                    ft.Icons.ARROW_DOWNWARD,
                    icon_color=ft.Colors.PRIMARY,
                ),
            ],
        )
        amount_tf = make_amount_field(
            lang,
            label=tr("field.amount", lang),
            value=tx.amount if tx else "",
        )
        items_editor = LineItemsEditor(lang)

        def _sync_amount_visibility() -> None:
            amount_tf.visible = not items_editor.enabled
            safe_update(amount_tf)

        items_editor.set_on_changed(_sync_amount_visibility)
        if tx is not None and tx.has_items:
            items_editor.set_items(list(tx.items))
            amount_tf.visible = False

        fee_tf = make_amount_field(
            lang,
            label=tr("field.fee", lang),
        )

        def _sync_fee_visibility() -> None:
            show = (
                tx is None
                and (type_dd.value or TransactionType.EXPENSE.value)
                == TransactionType.EXPENSE.value
            )
            fee_tf.visible = show
            safe_update(fee_tf)

        account_picker = AccountStripPicker(
            self._page,
            accounts,
            lang=lang,
            value=default_account_id,
            frequent_id=frequent_id,
        )
        edit_account = next(
            (a for a in accounts if a.id == default_account_id), None
        )
        category_scope = (
            edit_account.id
            if edit_account is not None
            and bool(getattr(edit_account, "is_corporate", False))
            else ""
        )
        category_picker = CategoryPicker(
            self._page,
            self._state,
            tx_type=(tx.type.value if tx else TransactionType.EXPENSE.value),
            initial_name=tx.category if tx else None,
            account_id=category_scope,
        )
        await category_picker.reload()
        if category_picker.is_empty:
            category_picker.prompt_if_empty()
        def _on_type(_e: ft.ControlEvent | None = None) -> None:
            category_picker.set_tx_type(
                type_dd.value or TransactionType.EXPENSE.value
            )
            _sync_fee_visibility()

        bind_dropdown_select(type_dd, _on_type)
        _sync_fee_visibility()
        goal_options = [
            ft.DropdownOption(key="", text=tr("none", lang)),
        ] + [
            ft.DropdownOption(key=g.id, text=g.name) for g in self._goals
        ]
        goal_dd = ft.Dropdown(
            label=tr("field.goal", lang),
            value=tx.goal_id if tx and tx.goal_id else "",
            options=goal_options,
        )
        comment_tf = ft.TextField(
            label=tr("field.comment", lang),
            value=tx.comment if tx else "",
        )
        tags_tf = ft.TextField(
            label=tr("field.tags", lang),
            value=", ".join(_user_tags(tx)) if tx else "",
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(comment_tf, "text")
        configure_field(tags_tf, "text")
        wire_field_chain(self._page, [amount_tf, fee_tf, comment_tf, tags_tf])
        date_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("field.date", lang),
            value=tx.date if tx else datetime.now(timezone.utc),
            with_time=True,
            quick_strip=True,
        )
        from lib.presentation.widgets.attachment_picker import AttachmentPicker

        attachments = AttachmentPicker(
            self._page,
            lang=lang,
            transaction_id=tx.id if tx else None,
            existing=list(tx.attachments or []) if tx else None,
        )

        async def _save() -> None:
            occurred = date_field.value
            if occurred is None:
                snack(self._page, tr("invalid_date", lang), error=True)
                return

            account = next(
                (a for a in accounts if a.id == account_picker.value), accounts[0]
            )
            tags = [
                p.strip().lstrip("#")
                for p in (tags_tf.value or "").split(",")
                if p.strip()
            ]
            category = category_picker.selected_name
            if not category:
                snack(self._page, tr("field.category", lang), error=True)
                return
            tx_type = TransactionType(type_dd.value or TransactionType.EXPENSE.value)
            cat_scope = (
                account.id
                if bool(getattr(account, "is_corporate", False))
                else ""
            )
            if (
                self._state.container.find_or_create_category is not None
                and not category_picker.has_category(category)
            ):
                await self._state.container.find_or_create_category.execute(
                    category,
                    kind=(
                        CategoryKind.INCOME
                        if tx_type == TransactionType.INCOME
                        else CategoryKind.EXPENSE
                    ),
                    account_id=cat_scope,
                )
            goal_id = goal_dd.value or None
            if goal_id == "":
                goal_id = None
            if goal_id and category not in SAVINGS_CATEGORIES:
                category = DEFAULT_SAVINGS_CATEGORY
            elif goal_id:
                category = normalize_savings_category(category)

            line_items = items_editor.collect(default_category=category)
            try:
                fee = parse_optional_amount(fee_tf.value)
                if fee < 0:
                    raise InvalidOperation
                if line_items is None:
                    amount = require_positive_amount(amount_tf, self._page, lang)
                    if amount is None:
                        return
                    items: list = []
                else:
                    if len(line_items) < 1:
                        raise InvalidOperation
                    amount = sum((i.amount for i in line_items), Decimal("0"))
                    items = line_items
            except (InvalidOperation, ValueError):
                snack(self._page, tr("invalid_amount", lang), error=True)
                return

            tx_id = tx.id if tx else attachments.transaction_id
            attachments.set_transaction_id(tx_id)
            paths = attachments.collected_paths()
            entity = Transaction(
                id=tx_id,
                account_id=account.id,
                amount=amount,
                category=category,
                tags=tags,
                date=occurred,
                comment=comment_tf.value or "",
                type=tx_type,
                currency=account.currency,
                created_at=tx.created_at if tx else datetime.now(timezone.utc),
                goal_id=goal_id,
                items=items,
                attachments=paths,
            )
            try:
                if tx:
                    await self._state.container.update_transaction.execute(entity)
                    if fee > 0 and tx_type == TransactionType.EXPENSE:
                        if self._state.container.find_or_create_category is not None:
                            await self._state.container.find_or_create_category.execute(
                                FEE_CATEGORY,
                                kind=CategoryKind.EXPENSE,
                                icon="receipt_long",
                                account_id=cat_scope,
                            )
                        await self._state.container.add_transaction.execute(
                            make_fee_expense(
                                account_id=account.id,
                                currency=account.currency,
                                amount=fee,
                                date=entity.date,
                                comment=entity.comment or FEE_CATEGORY,
                            )
                        )
                else:
                    saved = await self._state.container.add_transaction.execute(entity)
                    await self._maybe_notify_goal(saved.goal_id)
                    if fee > 0 and tx_type == TransactionType.EXPENSE:
                        try:
                            if self._state.container.find_or_create_category is not None:
                                await self._state.container.find_or_create_category.execute(
                                    FEE_CATEGORY,
                                    kind=CategoryKind.EXPENSE,
                                    icon="receipt_long",
                                    account_id=cat_scope,
                                )
                            await self._state.container.add_transaction.execute(
                                make_fee_expense(
                                    account_id=account.id,
                                    currency=account.currency,
                                    amount=fee,
                                    date=saved.date,
                                    comment=saved.comment or FEE_CATEGORY,
                                )
                            )
                        except Exception:
                            await self._state.container.delete_transaction.execute(
                                saved.id
                            )
                            raise
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return
            close()
            self._state.bump_refresh("dashboard", "transactions", "accounts", "budgets")
            snack(self._page, tr("action.saved", lang))

        close = open_fullscreen_form(
            self._page,
            title=tr("action.edit", lang) if tx else tr("action.add", lang),
            lang=lang,
            overlay_key="transaction_editor",
            body=[
                *([
                    ft.Text(tr("subscription.series_hint", lang), size=12),
                    ft.TextButton(
                        tr("subscription.edit_series", lang),
                        icon=ft.Icons.EVENT_REPEAT,
                        on_click=lambda _e: self._open_series(tx),
                    ),
                ] if tx is not None and tx.subscription_id else []),
                type_dd,
                amount_tf,
                items_editor,
                fee_tf,
                account_picker,
                category_picker,
                goal_dd,
                date_field,
                comment_tf,
                tags_tf,
                attachments,
            ],
            on_save=_save,
        )

    async def _open_transfer_editor(self, tx: Transaction) -> None:
        """Comment/tags only — amount and accounts of a transfer stay locked."""
        lang = self._state.language
        amount_tf = make_amount_field(
            lang,
            label=tr("field.amount", lang),
            value=tx.amount,
            read_only=True,
        )
        comment_tf = ft.TextField(
            label=tr("field.comment", lang),
            value=tx.comment,
        )
        tags_tf = ft.TextField(
            label=tr("field.tags", lang),
            value=", ".join(_user_tags(tx)),
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
            entity = tx.model_copy(update={"comment": comment_tf.value or "", "tags": tags})
            try:
                await self._state.container.update_transaction.execute(entity)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return
            close()
            self._state.bump_refresh("dashboard", "transactions", "accounts", "budgets")
            snack(self._page, tr("action.saved", lang))

        close = open_fullscreen_form(
            self._page,
            title=tr("transaction.transfer", lang),
            lang=lang,
            overlay_key="transfer_leg_editor",
            body=[amount_tf, comment_tf, tags_tf],
            on_save=_save,
        )

    async def _maybe_notify_goal(self, goal_id: Optional[str]) -> None:
        if (
            not goal_id
            or not self._state.settings.notifications_enabled
            or not self._state.settings.goal_milestones
        ):
            return
        goal = await self._state.container.goal_repository.get_by_id(goal_id)
        if goal and goal.is_completed:
            msg = f"{tr('notify.goal_reached', self._state.language)} {goal.name}"
            self._state.push_notification(msg)
            notifier = getattr(self._state.container, "notification_service", None)
            if notifier is not None:
                notifier.push(
                    title=tr("notify.goal_reached", self._state.language),
                    body=goal.name,
                    kind=NotificationKind.GOAL_MILESTONE,
                    related_id=goal.id,
                )
