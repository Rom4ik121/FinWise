"""Subscriptions page with search, filters, templates, and catch-up."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.core.config import ACCOUNT_COLORS
from lib.domain.entities.subscription import (
    Periodicity,
    Subscription,
    SubscriptionStatus,
)
from lib.domain.use_cases.subscription_insights import bucket_charges_by_month
from lib.domain.use_cases.subscriptions import (
    count_missed_periods,
    monthly_equivalent,
)
from lib.presentation.account_icons import account_icon_control, entity_icon_groups
from lib.presentation.dropdown_options import (
    account_dropdown_options,
    icon_dropdown_option,
)
from lib.presentation.form_keyboard import configure_field, wire_field_chain
from lib.presentation.layout import h_scroll, make_v_scroll
from lib.presentation.components.layout.grid import card_grid
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import replace_controls
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.notification_badges import (
    SUBSCRIPTION_ALERT_KINDS,
    pending_related_ids,
)
from lib.presentation.styles import (
    ICON_CATALOG_GLYPH,
    card_surface,
    choice_chips,
    form_hint,
    form_section,
    labeled_switch,
    muted_text,
)
from lib.presentation.subscriptions_templates import (
    SUBSCRIPTION_TEMPLATES,
    SubscriptionTemplate,
    subscription_template_chip,
)
from lib.presentation.utils import (
    bind_dropdown_select,
    format_date,
    format_money,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
)
from lib.presentation.widgets.appearance_picker import open_color_picker, open_icon_picker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.subscription_card import (
    SubscriptionCard,
    periodicity_label,
)
from lib.presentation.widgets.subscription_sparkline import subscription_charge_sparkline
from lib.presentation.widgets.subscription_summary_ring import subscriptions_summary_ring
from lib.presentation.widgets.subscription_swipe_card import swipe_subscription_card

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_CHARGE_PAGE = 20
_STATUS_FILTERS = ("active", "paused", "expired", "cancelled", "all")
_SORT_KEYS = ("next_billing", "amount", "name", "monthly")
_PERIOD_FILTERS = ("all",) + tuple(p.value for p in Periodicity)
_PERIOD_OPTIONS = (
    Periodicity.DAILY,
    Periodicity.WEEKLY,
    Periodicity.BIWEEKLY,
    Periodicity.MONTHLY,
    Periodicity.QUARTERLY,
    Periodicity.SEMI_ANNUAL,
    Periodicity.YEARLY,
    Periodicity.CUSTOM,
)


class SubscriptionsPage(ft.Column):
    """List subscriptions and upcoming billing dates."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._accounts: list = []
        self._list = make_v_scroll(spacing=12)
        self._alert_ids: set[str] = set()
        self._token = -1
        self._status_filter = "active"
        self._period_filter = "all"
        self._sort_by = "next_billing"
        self._auto_only = False
        self._due_soon = False
        self._search_query = ""
        self._search_gen = 0
        self._cached_items: list[Subscription] | None = None
        self._cache_token: int | None = None
        self._search_tf = ft.TextField(
            hint_text=tr("subscription.search_hint", state.language),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            filled=True,
            expand=True,
            on_change=self._on_search_change,
        )
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.subscriptions", state.language),
                    body=self._list,
                    page=page,
                    extra=[self._search_tf],
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.TUNE,
                            tooltip=tr("action.filters", state.language),
                            on_click=lambda _e: self._open_filters(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            tooltip=tr("action.add", state.language),
                            on_click=lambda _e: self._open_editor(),
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
        if state.subscriptions_token != self._token:
            self._reload_gate.request()

    def _on_search_change(self, e: ft.ControlEvent) -> None:
        self._search_query = str(getattr(e.control, "value", "") or "")
        run_async(self._page, self._debounced_search)

    async def _debounced_search(self) -> None:
        """Wait briefly so typing does not reload on every keystroke."""
        self._search_gen += 1
        gen = self._search_gen
        await asyncio.sleep(0.35)
        if gen != self._search_gen:
            return
        self._reload_gate.request()

    def _open_filters(self) -> None:
        lang = self._state.language
        holder = {
            "status": self._status_filter,
            "period": self._period_filter,
            "sort": self._sort_by,
            "auto_only": self._auto_only,
            "due_soon": self._due_soon,
        }
        status_chips = choice_chips(
            [(key, tr(f"subscription.filter.{key}", lang)) for key in _STATUS_FILTERS],
            value=holder["status"],
            on_changed=lambda value: holder.__setitem__("status", value),
        )
        period_chips = choice_chips(
            [
                (
                    key,
                    tr("subscription.filter.all_periods", lang)
                    if key == "all"
                    else periodicity_label(Periodicity(key), lang),
                )
                for key in _PERIOD_FILTERS
                if key != Periodicity.CUSTOM.value
            ]
            + [
                (
                    Periodicity.CUSTOM.value,
                    periodicity_label(Periodicity.CUSTOM, lang),
                )
            ],
            value=holder["period"],
            on_changed=lambda value: holder.__setitem__("period", value),
        )
        sort_chips = choice_chips(
            [(key, tr(f"subscription.sort.{key}", lang)) for key in _SORT_KEYS],
            value=holder["sort"],
            on_changed=lambda value: holder.__setitem__("sort", value),
        )
        auto_sw = ft.Switch(value=bool(holder["auto_only"]))
        due_sw = ft.Switch(value=bool(holder["due_soon"]))
        auto_sw.on_change = lambda e: holder.__setitem__(
            "auto_only", bool(getattr(e.control, "value", False))
        )
        due_sw.on_change = lambda e: holder.__setitem__(
            "due_soon", bool(getattr(e.control, "value", False))
        )

        async def _apply() -> None:
            self._status_filter = str(holder["status"] or "active")
            self._period_filter = str(holder["period"] or "all")
            self._sort_by = str(holder["sort"] or "next_billing")
            self._auto_only = bool(holder["auto_only"])
            self._due_soon = bool(holder["due_soon"])
            close()
            await self.reload()

        close = open_fullscreen_form(
            self._page,
            title=tr("action.filters", lang),
            lang=lang,
            overlay_key="subscription_filters",
            body=[
                form_section(
                    tr("subscription.filter_status", lang),
                    [status_chips],
                    hint=tr("subscription.filter_status_hint", lang),
                    icon=ft.Icons.FILTER_LIST,
                ),
                form_section(
                    tr("subscription.filter_period", lang),
                    [period_chips],
                    icon=ft.Icons.EVENT,
                ),
                form_section(
                    None,
                    [labeled_switch(tr("subscription.filter_auto_only", lang), auto_sw)],
                    hint=tr("subscription.filter_auto_only_hint", lang),
                    icon=ft.Icons.AUTORENEW,
                ),
                form_section(
                    None,
                    [labeled_switch(tr("subscription.filter_due_soon", lang), due_sw)],
                    hint=tr("subscription.filter_due_soon_hint", lang),
                    icon=ft.Icons.UPCOMING,
                ),
                form_section(
                    tr("subscription.filter_sort", lang),
                    [sort_chips],
                    icon=ft.Icons.SORT,
                ),
            ],
            on_save=_apply,
            save_label=tr("action.apply", lang, default=tr("action.save", lang)),
            save_icon=ft.Icons.CHECK,
        )

    def _apply_list_filters(self, items: list[Subscription]) -> list[Subscription]:
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=7)
        q = self._search_query.strip().lower()
        out: list[Subscription] = []
        for sub in items:
            status = (
                sub.status.value
                if isinstance(sub.status, SubscriptionStatus)
                else str(sub.status)
            )
            if self._status_filter not in ("", "all") and status != self._status_filter:
                continue
            period = (
                sub.periodicity.value
                if isinstance(sub.periodicity, Periodicity)
                else str(sub.periodicity)
            )
            if self._period_filter not in ("", "all") and period != self._period_filter:
                continue
            if self._auto_only and not sub.auto_charge:
                continue
            if self._due_soon:
                billed = sub.next_billing_date
                if billed.tzinfo is None:
                    billed = billed.replace(tzinfo=timezone.utc)
                if billed > soon:
                    continue
            if q and q not in (sub.name or "").lower() and q not in (sub.category or "").lower():
                continue
            out.append(sub)
        if self._sort_by == "amount":
            out.sort(key=lambda s: s.amount, reverse=True)
        elif self._sort_by == "name":
            out.sort(key=lambda s: (s.name or "").casefold())
        elif self._sort_by == "monthly":
            out.sort(
                key=lambda s: monthly_equivalent(
                    s.amount, s.periodicity, custom_interval_days=s.custom_interval_days
                ),
                reverse=True,
            )
        else:
            out.sort(key=lambda s: s.next_billing_date)
        return out

    async def reload(self) -> None:
        """Reload subscriptions list."""
        self._token = self._state.subscriptions_token
        lang = self._state.language
        if self._cached_items is None:
            fill_loading(self._list)
            safe_update(self._list)
        self._alert_ids = pending_related_ids(
            self._state.container,
            self._state.settings,
            SUBSCRIPTION_ALERT_KINDS,
        )
        # Do not auto-mark alerts read on every reload (badge display only).
        try:
            if self._cached_items is None or self._cache_token != self._token:
                self._accounts = await self._state.container.list_accounts.execute(active_only=True, corporate=False)
                items_all = await self._state.container.list_subscriptions.execute()
                self._cached_items = items_all
                self._cache_token = self._token
            else:
                items_all = self._cached_items
            items = self._apply_list_filters(items_all)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            replace_controls(
                self._list, [EmptyState(tr("error.generic", lang))], self._page
            )
            return

        if not items:
            if self._search_query.strip():
                empty_key = "empty.subscriptions_search"
            elif items_all:
                empty_key = "empty.subscriptions_filtered"
            else:
                empty_key = "empty.subscriptions"
            replace_controls(
                self._list,
                [
                    EmptyState(
                        tr(empty_key, lang),
                        action_label=tr("action.add", lang),
                        on_action=lambda _e: self._open_editor(),
                    )
                ],
                self._page,
            )
            return

        base = self._state.base_currency
        book = await load_rate_book(self._state.container)
        monthly = Decimal("0")
        yearly = Decimal("0")
        due_week_amount = Decimal("0")
        due_week_count = 0
        active_count = 0
        fx_ok = True
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=7)
        for sub in items:
            if sub.status != SubscriptionStatus.ACTIVE:
                continue
            active_count += 1
            monthly_amt = monthly_equivalent(
                sub.amount,
                sub.periodicity,
                custom_interval_days=sub.custom_interval_days,
            )
            converted = book.convert(monthly_amt, sub.currency, base)
            if converted is None:
                if sub.currency.upper() == base.upper():
                    converted = monthly_amt
                else:
                    fx_ok = False
                    continue
            monthly += converted
            yearly += converted * Decimal("12")
            billed = sub.next_billing_date
            if billed.tzinfo is None:
                billed = billed.replace(tzinfo=timezone.utc)
            if billed <= soon:
                due_converted = book.convert(sub.amount, sub.currency, base)
                if due_converted is None:
                    if sub.currency.upper() == base.upper():
                        due_converted = sub.amount
                    else:
                        fx_ok = False
                        continue
                due_week_amount += due_converted
                due_week_count += 1
        if not fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)

        lookback = now - timedelta(days=6 * 31)
        try:
            from lib.presentation.tx_query import fetch_transactions_paged

            recent_txs = await fetch_transactions_paged(
                self._state.container.list_transactions,
                has_subscription=True,
                date_from=lookback,
            )
        except Exception:  # noqa: BLE001
            recent_txs = []
        txs_by_sub: dict[str, list] = defaultdict(list)
        for tx in recent_txs:
            if tx.subscription_id:
                txs_by_sub[tx.subscription_id].append(tx)

        cards: list[ft.Control] = [
            subscriptions_summary_ring(
                monthly=monthly,
                yearly=yearly,
                currency=base,
                language=lang,
                due_week_count=due_week_count,
                due_week_amount=due_week_amount,
                active_count=active_count,
                page=self._page,
            )
        ]
        due_soon_items = []
        rest_items = []
        for sub in items:
            billed = sub.next_billing_date
            if billed.tzinfo is None:
                billed = billed.replace(tzinfo=timezone.utc)
            if (
                sub.status == SubscriptionStatus.ACTIVE
                and billed <= soon
            ):
                due_soon_items.append(sub)
            else:
                rest_items.append(sub)

        def _card(sub: Subscription) -> ft.Control:
            buckets = bucket_charges_by_month(
                txs_by_sub.get(sub.id, []),
                months=6,
                now=now,
                rate_book=book,
                to_currency=sub.currency or base,
            )
            sparkline = None
            if any(v > 0 for _, v in buckets):
                sparkline = subscription_charge_sparkline(
                    buckets, color=getattr(sub, "color", None)
                )
            can_charge = sub.status in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAUSED,
            )
            pause_cb = None
            pause_label = None
            if sub.status == SubscriptionStatus.ACTIVE:
                pause_cb = lambda s=sub: run_async(self._page, self._pause, s)
                pause_label = tr("subscription.pause", lang)
            elif sub.status == SubscriptionStatus.PAUSED:
                pause_cb = lambda s=sub: run_async(self._page, self._resume, s)
                pause_label = tr("subscription.resume", lang)
            card = SubscriptionCard(
                sub,
                language=lang,
                alert=sub.id in self._alert_ids,
                sparkline=sparkline,
                on_open=self._open_detail,
                on_edit=self._open_editor,
                on_delete=self._confirm_delete,
                page=self._page,
            )
            return swipe_subscription_card(
                card,
                language=lang,
                on_charge=(lambda s=sub: self._charge_or_catchup(s))
                if can_charge
                else None,
                on_pause=pause_cb,
                on_edit=lambda s=sub: self._open_editor(s),
                pause_label=pause_label,
                page=self._page,
            )

        if due_soon_items:
            cards.append(
                ft.Text(
                    tr("subscription.section_due_soon", lang),
                    size=13,
                    weight=ft.FontWeight.W_700,
                )
            )
            cards.extend(
                card_grid(
                    [_card(s) for s in due_soon_items],
                    self._page,
                    min_card=300,
                    maximum=2,
                )
            )
            if rest_items:
                cards.append(
                    ft.Text(
                        tr("subscription.section_other", lang),
                        size=13,
                        weight=ft.FontWeight.W_700,
                    )
                )
        cards.extend(
            card_grid(
                [_card(s) for s in rest_items],
                self._page,
                min_card=300,
                maximum=2,
            )
        )
        replace_controls(self._list, cards, self._page)

    async def _pause(self, sub: Subscription) -> None:
        try:
            await self._state.container.pause_subscription.execute(sub.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        self._state.bump_refresh("dashboard", "subscriptions", "analytics")
        await self.reload()

    async def _resume(self, sub: Subscription) -> None:
        try:
            await self._state.container.resume_subscription.execute(sub.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        self._state.bump_refresh("dashboard", "subscriptions", "analytics")
        await self.reload()

    def _confirm_delete(self, sub: Subscription) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_subscription.execute(sub.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh(
                "dashboard", "accounts", "transactions", "subscriptions"
            )
            await self.reload()

        confirm_dialog(
            self._page,
            title=tr("action.confirm_delete", lang),
            message=tr("subscription.delete_hint", lang, name=sub.name),
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    def _charge_or_catchup(self, sub: Subscription) -> None:
        missed = count_missed_periods(sub)
        if missed > 1:
            self._open_catchup(sub, missed)
            return
        run_async(self._page, self._charge_now, sub)

    async def _charge_now(self, sub: Subscription) -> None:
        lang = self._state.language
        try:
            await self._state.container.charge_subscription_now.execute(sub.id)
            audit = getattr(self._state.container, "append_subscription_audit", None)
            if audit is not None:
                await audit.execute(sub.id, "charge")
        except ValueError as exc:
            if str(exc) == "insufficient_funds":
                snack(self._page, tr("subscription.insufficient_funds", lang), error=True)
                return
            snack_exception(self._page, exc, lang=lang)
            return
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._state.bump_refresh(
            "dashboard", "accounts", "transactions", "subscriptions"
        )
        snack(self._page, tr("action.saved", lang))
        await self.reload()

    def _open_catchup(self, sub: Subscription, missed: int) -> None:
        lang = self._state.language

        async def _one() -> None:
            close()
            await self._catchup(sub, max_charges=1)

        async def _all() -> None:
            close()
            await self._catchup(sub, max_charges=0)

        async def _skip() -> None:
            close()
            try:
                await self._state.container.skip_subscription_period.execute(
                    sub.id, skip_all_missed=True
                )
                audit = getattr(self._state.container, "append_subscription_audit", None)
                if audit is not None:
                    await audit.execute(sub.id, "skip", details={"missed": missed})
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "subscriptions", "analytics")
            snack(self._page, tr("action.saved", lang))
            await self.reload()

        close = open_fullscreen_form(
            self._page,
            title=tr("subscription.catchup_title", lang),
            lang=lang,
            overlay_key="subscription_catchup",
            body=[
                muted_text(tr("subscription.catchup_body", lang, count=str(missed))),
                ft.FilledButton(
                    tr("subscription.catchup_one", lang),
                    icon=ft.Icons.PAYMENTS_OUTLINED,
                    on_click=lambda e: run_async(self._page, _one, e),
                ),
                ft.FilledTonalButton(
                    tr("subscription.catchup_all", lang),
                    icon=ft.Icons.LIBRARY_ADD_CHECK,
                    on_click=lambda e: run_async(self._page, _all, e),
                ),
                ft.OutlinedButton(
                    tr("subscription.catchup_skip", lang),
                    icon=ft.Icons.SKIP_NEXT,
                    on_click=lambda e: run_async(self._page, _skip, e),
                ),
            ],
            on_save=None,
            show_save=False,
        )

    async def _catchup(self, sub: Subscription, *, max_charges: int | None) -> None:
        lang = self._state.language
        try:
            txs = await self._state.container.process_due_subscriptions.execute(
                subscription_id=sub.id,
                max_charges=max_charges,
                ignore_auto_charge=True,
            )
            audit = getattr(self._state.container, "append_subscription_audit", None)
            if audit is not None:
                await audit.execute(
                    sub.id, "catchup", details={"count": len(txs)}
                )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        if not txs:
            snack(self._page, tr("subscription.catchup_none", lang), error=True)
            return
        self._state.bump_refresh(
            "dashboard", "accounts", "transactions", "subscriptions"
        )
        snack(self._page, tr("action.saved", lang))
        await self.reload()

    def _open_detail(self, sub: Subscription) -> None:
        lang = self._state.language
        body = ft.Column(spacing=12, scroll=ft.ScrollMode.HIDDEN, expand=True)
        close_holder: dict[str, object] = {}

        def _close_detail() -> None:
            closer = close_holder.get("close")
            if callable(closer):
                closer()

        async def _load() -> None:
            body.controls = [loading_indicator()]
            try:
                safe_update(body)
            except Exception:  # noqa: BLE001
                pass
            try:
                get_sub = getattr(self._state.container, "get_subscription", None)
                if get_sub is not None:
                    fresh = await get_sub.execute(sub.id)
                else:
                    fresh = sub
                sub_obj = fresh or sub
                accounts = {
                    a.id: a
                    for a in await self._state.container.list_accounts.execute(
                        active_only=False
                    )
                }
                txs = await self._state.container.list_transactions.execute(
                    subscription_id=sub_obj.id,
                    limit=_CHARGE_PAGE + 1,
                    offset=0,
                )
                book = await load_rate_book(self._state.container)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return

            has_more = len(txs) > _CHARGE_PAGE
            shown = txs[:_CHARGE_PAGE]
            offset = {"n": len(shown)}

            sparkline_ctrl: ft.Control = ft.Container(height=0)
            buckets = bucket_charges_by_month(
                txs,
                months=6,
                rate_book=book,
                to_currency=sub_obj.currency or self._state.base_currency,
            )
            if any(v > 0 for _, v in buckets):
                sparkline_ctrl = subscription_charge_sparkline(
                    buckets, color=getattr(sub_obj, "color", None)
                )

            charges_col = ft.Column(spacing=8, tight=True)
            charges_col.controls = [
                ft.Text(
                    tr("subscription.charge_history", lang),
                    weight=ft.FontWeight.W_700,
                ),
            ]
            if not shown:
                charges_col.controls.append(muted_text("—"))
            else:
                for idx, tx in enumerate(shown):
                    charges_col.controls.append(
                        self._charge_row(
                            sub_obj,
                            tx,
                            accounts,
                            close_holder,
                            is_latest=idx == 0,
                        )
                    )

            async def _more(_e: ft.ControlEvent | None = None) -> None:
                more = await self._state.container.list_transactions.execute(
                    subscription_id=sub_obj.id,
                    limit=_CHARGE_PAGE + 1,
                    offset=offset["n"],
                )
                more_has = len(more) > _CHARGE_PAGE
                chunk = more[:_CHARGE_PAGE]
                offset["n"] += len(chunk)
                for tx in chunk:
                    charges_col.controls.append(
                        self._charge_row(
                            sub_obj, tx, accounts, close_holder, is_latest=False
                        )
                    )
                load_more_btn.visible = more_has
                safe_update(charges_col)
                safe_update(load_more_btn)

            load_more_btn = ft.TextButton(
                tr("action.load_more", lang),
                visible=has_more,
                on_click=lambda e: run_async(self._page, _more, e),
            )

            async def _pause(_e: ft.ControlEvent | None = None) -> None:
                await self._pause(sub_obj)
                await _load()

            async def _resume(_e: ft.ControlEvent | None = None) -> None:
                await self._resume(sub_obj)
                await _load()

            async def _charge(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._charge_or_catchup(sub_obj)

            async def _skip(_e: ft.ControlEvent | None = None) -> None:
                try:
                    await self._state.container.skip_subscription_period.execute(
                        sub_obj.id
                    )
                    audit = getattr(
                        self._state.container, "append_subscription_audit", None
                    )
                    if audit is not None:
                        await audit.execute(sub_obj.id, "skip")
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                self._state.bump_refresh("dashboard", "subscriptions", "analytics")
                snack(self._page, tr("action.saved", lang))
                await _load()
                await self.reload()

            async def _duplicate(_e: ft.ControlEvent | None = None) -> None:
                dup = getattr(self._state.container, "duplicate_subscription", None)
                if dup is None:
                    return
                try:
                    copy = await dup.execute(
                        sub_obj.id,
                        name_suffix=tr("subscription.copy_suffix", lang),
                    )
                    audit = getattr(
                        self._state.container, "append_subscription_audit", None
                    )
                    if audit is not None:
                        await audit.execute(
                            sub_obj.id, "duplicate", details={"copy_id": copy.id}
                        )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                self._state.bump_refresh("dashboard", "subscriptions", "analytics")
                _close_detail()
                await self.reload()
                snack(self._page, tr("action.saved", lang))

            async def _cancel(_e: ft.ControlEvent | None = None) -> None:
                cancel = getattr(self._state.container, "cancel_subscription", None)
                if cancel is None:
                    return
                try:
                    await cancel.execute(sub_obj.id)
                    audit = getattr(
                        self._state.container, "append_subscription_audit", None
                    )
                    if audit is not None:
                        await audit.execute(sub_obj.id, "cancel")
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                self._state.bump_refresh("dashboard", "subscriptions", "analytics")
                _close_detail()
                await self.reload()
                snack(self._page, tr("action.saved", lang))

            def _edit(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._open_editor(sub_obj)

            actions: list[ft.Control] = [
                ft.FilledButton(
                    tr("subscription.charge_now", lang),
                    icon=ft.Icons.PAYMENTS_OUTLINED,
                    on_click=lambda e: run_async(self._page, _charge, e),
                ),
                ft.OutlinedButton(
                    tr("subscription.skip_period", lang),
                    icon=ft.Icons.SKIP_NEXT,
                    on_click=lambda e: run_async(self._page, _skip, e),
                ),
                ft.FilledTonalButton(
                    tr("action.edit", lang),
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=_edit,
                ),
            ]
            auto_sw = ft.Switch(
                label=tr("subscription.auto_charge", lang),
                value=bool(sub_obj.auto_charge),
            )
            sub_holder = {"sub": sub_obj}

            async def _toggle_auto(_e: ft.ControlEvent | None = None) -> None:
                current = sub_holder["sub"]
                try:
                    updated = await self._state.container.update_subscription.execute(
                        current.model_copy(update={"auto_charge": bool(auto_sw.value)})
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                sub_holder["sub"] = updated
                self._state.bump_refresh("dashboard", "subscriptions", "analytics")
                snack(self._page, tr("action.saved", lang))

            auto_sw.on_change = lambda e: run_async(self._page, _toggle_auto, e)
            if sub_obj.status == SubscriptionStatus.ACTIVE:
                actions.append(
                    ft.OutlinedButton(
                        tr("subscription.pause", lang),
                        icon=ft.Icons.PAUSE_CIRCLE_OUTLINE,
                        on_click=lambda e: run_async(self._page, _pause, e),
                    )
                )
                actions.append(
                    ft.TextButton(
                        tr("subscription.cancel", lang),
                        icon=ft.Icons.CANCEL_OUTLINED,
                        on_click=lambda e: run_async(self._page, _cancel, e),
                    )
                )
            elif sub_obj.status == SubscriptionStatus.PAUSED:
                actions.append(
                    ft.OutlinedButton(
                        tr("subscription.resume", lang),
                        icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                        on_click=lambda e: run_async(self._page, _resume, e),
                    )
                )
            actions.append(
                ft.TextButton(
                    tr("subscription.duplicate", lang),
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda e: run_async(self._page, _duplicate, e),
                )
            )

            audit_rows: list[ft.Control] = []
            list_audit = getattr(self._state.container, "list_subscription_audit", None)
            if list_audit is not None:
                try:
                    entries = await list_audit.execute(sub_obj.id, limit=8)
                    if entries:
                        audit_rows.append(
                            ft.Text(
                                tr("subscription.audit", lang),
                                weight=ft.FontWeight.W_700,
                            )
                        )
                        for entry in entries:
                            action_key = f"subscription.audit.{entry.action}"
                            label = tr(action_key, lang)
                            if label == action_key:
                                label = entry.action
                            audit_rows.append(
                                muted_text(f"{format_date(entry.created_at)} · {label}")
                            )
                except Exception:  # noqa: BLE001
                    pass

            meta = ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Text(
                        periodicity_label(
                            sub_obj.periodicity,
                            lang,
                            custom_interval_days=sub_obj.custom_interval_days,
                        )
                    ),
                    ft.Text(
                        tr(
                            "subscription.next_billing",
                            lang,
                            date=format_date(sub_obj.next_billing_date),
                        )
                    ),
                    ft.Text(
                        f"{tr('subscription.start_date', lang)}: "
                        f"{sub_obj.start_date.isoformat()}"
                    ),
                    ft.Text(
                        f"{tr('subscription.end_date', lang)}: "
                        f"{sub_obj.end_date.isoformat() if sub_obj.end_date else '—'}"
                    ),
                    ft.Text(
                        f"{tr('subscription.max_payments', lang)}: "
                        f"{sub_obj.max_payments if sub_obj.max_payments is not None else '—'} "
                        f"({sub_obj.payments_made})"
                    ),
                    auto_sw,
                ],
            )

            body.controls = [
                SubscriptionCard(sub_obj, language=lang, page=self._page),
                sparkline_ctrl,
                card_surface(meta),
                ft.Row(wrap=True, spacing=8, controls=actions),
                charges_col,
                load_more_btn,
                *audit_rows,
            ]
            safe_update(body)

        close = open_fullscreen_form(
            self._page,
            title=sub.name,
            lang=lang,
            overlay_key="subscription_detail",
            body=[body],
            on_save=None,
            show_save=False,
        )
        close_holder["close"] = close
        run_async(self._page, _load)

    def _charge_row(
        self,
        sub: Subscription,
        tx,
        accounts: dict,
        close_holder: dict,
        *,
        is_latest: bool,
    ) -> ft.Control:
        lang = self._state.language
        account = accounts.get(tx.account_id)
        account_name = account.name if account else tx.account_id
        subtitle = account_name
        if tx.comment:
            subtitle = f"{account_name} · {tx.comment}"

        async def _delete(_e: ft.ControlEvent | None = None) -> None:
            confirm_dialog(
                self._page,
                title=tr("action.confirm_delete", lang),
                message=tr("subscription.delete_charge_hint", lang),
                confirm_text=tr("action.delete", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=lambda: run_async(self._page, _do_delete),
            )

        async def _do_delete() -> None:
            try:
                await self._state.container.delete_subscription_charge.execute(
                    tx.id, subscription_id=sub.id
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh(
                "dashboard", "accounts", "transactions", "subscriptions"
            )
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            await self.reload()
            self._open_detail(sub)

        trailing: list[ft.Control] = [
            ft.Text(format_money(tx.amount, tx.currency), weight=ft.FontWeight.W_600)
        ]
        if is_latest:
            trailing.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.ERROR,
                    on_click=lambda e: run_async(self._page, _delete, e),
                )
            )
        return card_surface(
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(format_date(tx.date), weight=ft.FontWeight.W_600),
                            muted_text(subtitle),
                        ],
                    ),
                    ft.Row(spacing=4, tight=True, controls=trailing),
                ],
            )
        )

    def _open_editor(self, sub: Optional[Subscription] = None) -> None:
        run_async(self._page, self._open_editor_async, sub)

    async def _open_editor_async(self, sub: Optional[Subscription] = None) -> None:
        lang = self._state.language
        if not self._accounts:
            try:
                self._accounts = await self._state.container.list_accounts.execute(active_only=True, corporate=False)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
        if not self._accounts:
            snack(self._page, tr("empty.accounts", lang), error=True)
            return

        name_tf = ft.TextField(
            label=tr("field.name", lang), value=sub.name if sub else ""
        )
        configure_field(name_tf, "name")
        amount_tf = make_amount_field(
            lang,
            label=tr("field.amount", lang),
            value=sub.amount if sub else "",
        )
        account_dd = ft.Dropdown(
            label=tr("field.account", lang),
            value=sub.account_id if sub else self._accounts[0].id,
            options=account_dropdown_options(self._accounts),
        )
        default_ccy = (
            sub.currency
            if sub
            else next(
                (a.currency for a in self._accounts if a.id == account_dd.value),
                self._accounts[0].currency,
            )
        )
        currency_picker = CurrencyTickerPicker(
            self._page,
            lang=lang,
            label=tr("field.currency", lang),
            value=default_ccy,
            include_crypto=True,
        )
        comment_tf = ft.TextField(
            label=tr("field.comment", lang),
            value=sub.comment if sub else "",
        )
        configure_field(comment_tf, "text")
        _period_icons = {
            Periodicity.DAILY: ft.Icons.TODAY,
            Periodicity.WEEKLY: ft.Icons.DATE_RANGE,
            Periodicity.BIWEEKLY: ft.Icons.DATE_RANGE,
            Periodicity.MONTHLY: ft.Icons.CALENDAR_MONTH,
            Periodicity.QUARTERLY: ft.Icons.CALENDAR_VIEW_MONTH,
            Periodicity.SEMI_ANNUAL: ft.Icons.CALENDAR_VIEW_MONTH,
            Periodicity.YEARLY: ft.Icons.EVENT_AVAILABLE,
            Periodicity.CUSTOM: ft.Icons.TUNE,
        }
        period_dd = ft.Dropdown(
            label=tr("field.period", lang),
            value=(sub.periodicity.value if sub else Periodicity.MONTHLY.value),
            options=[
                icon_dropdown_option(
                    p.value,
                    periodicity_label(p, lang),
                    _period_icons.get(p, ft.Icons.EVENT),
                )
                for p in _PERIOD_OPTIONS
            ],
        )
        custom_tf = ft.TextField(
            label=tr("subscription.custom_interval", lang),
            value=(
                str(sub.custom_interval_days)
                if sub and sub.custom_interval_days
                else ""
            ),
            visible=(sub.periodicity == Periodicity.CUSTOM) if sub else False,
        )
        configure_field(custom_tf, "number")
        start_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("subscription.start_date", lang),
            value=(
                datetime.combine(
                    sub.start_date, datetime.min.time(), tzinfo=timezone.utc
                )
                if sub
                else datetime.now(timezone.utc)
            ),
        )
        end_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("subscription.end_date", lang),
            value=(
                datetime.combine(
                    sub.end_date, datetime.min.time(), tzinfo=timezone.utc
                )
                if sub and sub.end_date
                else None
            ),
        )
        max_payments_tf = ft.TextField(
            label=tr("subscription.max_payments", lang),
            value=(
                str(sub.max_payments) if sub and sub.max_payments is not None else ""
            ),
            border_radius=14,
            filled=True,
        )
        configure_field(max_payments_tf, "number")
        wire_field_chain(
            self._page, [name_tf, amount_tf, custom_tf, max_payments_tf, comment_tf]
        )
        next_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("field.date", lang),
            value=(sub.next_billing_date if sub else datetime.now(timezone.utc)),
        )
        locked_status = sub is not None and sub.status in (
            SubscriptionStatus.EXPIRED,
            SubscriptionStatus.CANCELLED,
        )
        _status_icons = {
            SubscriptionStatus.ACTIVE: ft.Icons.CHECK_CIRCLE_OUTLINE,
            SubscriptionStatus.PAUSED: ft.Icons.PAUSE_CIRCLE_OUTLINE,
        }
        status_dd: ft.Dropdown | None = None
        if locked_status:
            status_controls: list[ft.Control] = [
                muted_text(
                    tr(f"subscription.status.{sub.status.value}", lang),
                    size=14,
                ),
                form_hint(tr("subscription.status_locked_hint", lang), size=11),
            ]
        else:
            status_dd = ft.Dropdown(
                label=tr("field.active", lang),
                value=(sub.status.value if sub else SubscriptionStatus.ACTIVE.value),
                options=[
                    icon_dropdown_option(
                        s.value,
                        tr(f"subscription.status.{s.value}", lang),
                        _status_icons.get(s, ft.Icons.CIRCLE_OUTLINED),
                    )
                    for s in (
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAUSED,
                    )
                ],
            )
            status_controls = [status_dd]
        auto_sw = ft.Switch(
            value=bool(sub.auto_charge) if sub else True,
        )

        initial_icon = getattr(sub, "icon", None) or "autorenew"
        initial_color = getattr(sub, "color", None) or "#A78BFA"
        selected_icon = {"value": initial_icon}
        selected_color = {"value": initial_color}
        icon_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            alignment=ft.Alignment.CENTER,
            bgcolor=initial_color,
            content=account_icon_control(
                initial_icon, size=24, color=ICON_CATALOG_GLYPH
            ),
        )
        color_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            bgcolor=initial_color,
            border=ft.Border.all(2, ft.Colors.OUTLINE_VARIANT),
        )

        def _refresh_previews() -> None:
            icon_preview.content = account_icon_control(
                selected_icon["value"], size=24, color=ICON_CATALOG_GLYPH
            )
            icon_preview.bgcolor = selected_color["value"]
            color_preview.bgcolor = selected_color["value"]
            try:
                safe_update(icon_preview)
                safe_update(color_preview)
            except Exception:  # noqa: BLE001
                pass

        def _select_icon(key: str) -> None:
            selected_icon["value"] = key
            _refresh_previews()

        def _select_color(color: str) -> None:
            selected_color["value"] = color
            _refresh_previews()

        appearance_row = ft.Row(
            spacing=12,
            controls=[
                ft.GestureDetector(
                    content=icon_preview,
                    on_tap=lambda _e: open_icon_picker(
                        self._page,
                        lang=lang,
                        groups=entity_icon_groups(),
                        selected=selected_icon["value"],
                        on_select=_select_icon,
                        render_icon=lambda key: account_icon_control(
                            key, size=22, color=ICON_CATALOG_GLYPH
                        ),
                        overlay_key="subscription_icon_picker",
                    ),
                ),
                ft.GestureDetector(
                    content=color_preview,
                    on_tap=lambda _e: open_color_picker(
                        self._page,
                        lang=lang,
                        colors=ACCOUNT_COLORS,
                        selected=selected_color["value"],
                        on_select=_select_color,
                        overlay_key="subscription_color_picker",
                    ),
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(tr("picker.choose_icon", lang), size=13),
                        ft.Text(
                            tr("picker.choose_color", lang),
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                ),
            ],
        )

        def _apply_template(template: SubscriptionTemplate) -> None:
            name_tf.value = tr(template.name_key, lang)
            amount_tf.value = template.default_amount
            period_dd.value = template.periodicity.value
            custom_tf.visible = template.periodicity == Periodicity.CUSTOM
            selected_icon["value"] = template.icon
            selected_color["value"] = template.color
            _refresh_previews()
            for ctrl in (name_tf, amount_tf, period_dd, custom_tf):
                try:
                    safe_update(ctrl)
                except Exception:  # noqa: BLE001
                    pass

        template_strip = h_scroll(
            [
                subscription_template_chip(t, language=lang, on_click=_apply_template)
                for t in SUBSCRIPTION_TEMPLATES
            ],
            spacing=10,
            height=52,
            padding=ft.Padding.only(bottom=4),
        )

        def _on_period(_e: ft.ControlEvent) -> None:
            custom_tf.visible = period_dd.value == Periodicity.CUSTOM.value
            try:
                safe_update(custom_tf)
            except Exception:  # noqa: BLE001
                pass

        bind_dropdown_select(period_dd, _on_period)
        close_holder: dict[str, object] = {}

        async def _save(_e: ft.ControlEvent | None = None) -> None:
            try:
                amount = parse_amount(amount_tf.value)
                if amount <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                snack(self._page, tr("invalid_amount", lang), error=True)
                return
            next_date = next_field.value
            start_dt = start_field.value
            if next_date is None or start_dt is None:
                snack(self._page, tr("invalid_date", lang), error=True)
                return
            start = start_dt.date() if isinstance(start_dt, datetime) else start_dt
            end_dt = end_field.value
            end: Optional[date] = None
            if end_dt is not None:
                end = end_dt.date() if isinstance(end_dt, datetime) else end_dt
            custom_days = None
            periodicity = Periodicity(period_dd.value)
            if periodicity == Periodicity.CUSTOM:
                try:
                    custom_days = int(custom_tf.value or "0")
                    if custom_days < 1:
                        raise ValueError
                except ValueError:
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
            max_payments = None
            raw_max = (max_payments_tf.value or "").strip()
            if raw_max:
                try:
                    max_payments = int(raw_max)
                    if max_payments < 1:
                        raise ValueError
                except ValueError:
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
            account = next(
                (a for a in self._accounts if a.id == account_dd.value),
                self._accounts[0],
            )
            if locked_status:
                status = sub.status
            else:
                status = SubscriptionStatus(
                    (status_dd.value if status_dd is not None else None)
                    or SubscriptionStatus.ACTIVE.value
                )
            entity = Subscription(
                id=(
                    sub.id
                    if sub
                    else Subscription(
                        name="tmp",
                        amount=1,
                        account_id=account.id,
                        next_billing_date=next_date,
                    ).id
                ),
                name=(name_tf.value or "").strip() or "Subscription",
                amount=amount,
                currency=(currency_picker.value or account.currency).upper(),
                account_id=account.id,
                category=(name_tf.value or "").strip() or "Subscription",
                periodicity=periodicity,
                custom_interval_days=custom_days,
                start_date=start,
                end_date=end,
                max_payments=max_payments,
                payments_made=sub.payments_made if sub else 0,
                next_billing_date=next_date,
                status=status,
                auto_charge=bool(auto_sw.value),
                last_charged_at=sub.last_charged_at if sub else None,
                last_skip_date=sub.last_skip_date if sub else None,
                comment=comment_tf.value or "",
                icon=selected_icon["value"],
                color=selected_color["value"],
                created_at=sub.created_at if sub else datetime.now(timezone.utc),
            )
            try:
                if sub:
                    await self._state.container.update_subscription.execute(entity)
                    # Pause/resume are audited inside UpdateSubscriptionUseCase;
                    # only record a plain field update when status did not change.
                    if entity.status == sub.status:
                        audit = getattr(
                            self._state.container, "append_subscription_audit", None
                        )
                        if audit is not None:
                            await audit.execute(sub.id, "update")
                else:
                    await self._state.container.create_subscription.execute(entity)
                    # Create is audited inside CreateSubscriptionUseCase.
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            self._state.bump_refresh("dashboard", "subscriptions", "analytics")
            await self.reload()
            snack(self._page, tr("action.saved", lang))

        body = [
            template_strip,
            form_section(
                tr("form.section.main", lang),
                [
                    appearance_row,
                    name_tf,
                    amount_tf,
                    currency_picker,
                    account_dd,
                    comment_tf,
                ],
                icon=ft.Icons.AUTORENEW,
            ),
            form_section(
                tr("form.section.schedule", lang),
                [
                    period_dd,
                    custom_tf,
                    start_field,
                    end_field,
                    max_payments_tf,
                    form_hint(tr("subscription.max_payments_hint", lang), size=11),
                    next_field,
                ],
                icon=ft.Icons.EVENT,
            ),
            form_section(
                tr("form.section.options", lang),
                [
                    *status_controls,
                    labeled_switch(tr("subscription.auto_charge", lang), auto_sw),
                ],
                icon=ft.Icons.TUNE,
            ),
        ]
        close = open_fullscreen_form(
            self._page,
            title=tr("action.edit", lang) if sub else tr("action.add", lang),
            lang=lang,
            overlay_key="subscription_editor",
            wrap_body=False,
            body=body,
            on_save=_save,
        )
        close_holder["close"] = close
