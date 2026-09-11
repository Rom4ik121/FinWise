"""Debts CRUD page with filters, projection, and payment history."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.debt import Debt, DebtDirection, DebtStatus
from lib.domain.use_cases.debts import (
    compute_debt_interest,
    debt_credit_amount,
    debt_interest_from_tags,
)
from lib.domain.use_cases.debt_insights import bucket_payments_by_month
from lib.presentation.form_validation import require_name, require_positive_amount
from lib.presentation.notification_badges import (
    DEBT_ALERT_KINDS,
    pending_related_ids,
)
from lib.presentation.dropdown_options import (
    icon_dropdown_option,
)
from lib.core.config import ACCOUNT_COLORS
from lib.presentation.account_icons import (
    account_icon_badge,
    account_icon_control,
    entity_icon_groups,
)
from lib.presentation.debts_templates import DEBT_TEMPLATES, DebtTemplate, debt_template_chip
from lib.presentation.styles import (
    card_surface,
    choice_chips,
    form_hint,
    form_section,
    ICON_CATALOG_GLYPH,
    labeled_switch,
    muted_text,
)
from lib.presentation.money_input import (
    amount_text,
    attach_grouped_digits,
    make_amount_field,
    parse_amount_field,
    parse_optional_amount_field,
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
    try_convert_amount,
)
from lib.presentation.widgets.account_strip_picker import AccountStripPicker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.layout import h_scroll, make_v_scroll
from lib.presentation.components.layout.grid import card_grid
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import replace_controls
from lib.presentation.widgets.appearance_picker import open_color_picker, open_icon_picker
from lib.presentation.widgets.debt_card import DebtCard
from lib.presentation.widgets.debt_progress import debt_projection_card
from lib.presentation.widgets.debt_sparkline import debt_payment_sparkline
from lib.presentation.widgets.debt_summary_ring import debts_summary_ring
from lib.presentation.widgets.debt_swipe_card import swipe_debt_card
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.widgets.loading import fill_loading, loading_indicator

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_PAYMENT_PAGE = 20
_STATUS_FILTERS = ("open", "active", "overdue", "paid", "archived")
_SORT_KEYS = (
    "due_date",
    "remaining",
    "amount",
    "interest",
    "created_at",
    "counterparty",
    "status",
)
_OPEN_STATUSES = frozenset({"active", "overdue"})
_OPEN_FILTER = "open"


class DebtsPage(ft.Column):
    """Manage personal debts and loans."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._list = make_v_scroll(spacing=12)
        self._status_filter = _OPEN_FILTER
        self._direction_filter = "all"
        self._sort_by = "due_date"
        self._interest_only = False
        self._search_query = ""
        self._search_gen = 0
        self._alert_ids: set[str] = set()
        self._token = -1
        self._debt_state_synced = False
        self._cached_debts: list[Debt] | None = None
        self._cache_key: tuple | None = None
        self._search_tf = ft.TextField(
            hint_text=tr("debt.search_hint", state.language),
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
                    title=tr("nav.debts", state.language),
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
        if state.debts_token != self._token:
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

    def _filter_debts(self, debts: list[Debt]) -> list[Debt]:
        q = self._search_query.strip().lower()
        if not q:
            return debts
        return [d for d in debts if q in (d.counterparty or "").lower()]

    def _open_filters(self) -> None:
        lang = self._state.language
        holder = {
            "status": self._status_filter,
            "direction": self._direction_filter,
            "sort": self._sort_by,
            "interest_only": self._interest_only,
        }
        status_chips = choice_chips(
            [(key, tr(f"debt.filter.{key}", lang)) for key in _STATUS_FILTERS],
            value=holder["status"],
            on_changed=lambda value: holder.__setitem__("status", value),
        )
        direction_chips = choice_chips(
            [
                ("all", tr("debt.filter_all_directions", lang)),
                (DebtDirection.I_OWE.value, tr("debt.i_owe", lang)),
                (DebtDirection.OWED_TO_ME.value, tr("debt.owed_to_me", lang)),
            ],
            value=holder["direction"],
            on_changed=lambda value: holder.__setitem__("direction", value),
        )
        sort_chips = choice_chips(
            [(key, tr(f"debt.sort.{key}", lang)) for key in _SORT_KEYS],
            value=holder["sort"],
            on_changed=lambda value: holder.__setitem__("sort", value),
        )
        interest_sw = ft.Switch(
            value=bool(holder["interest_only"]),
            on_change=lambda e: holder.__setitem__(
                "interest_only", bool(getattr(e.control, "value", False))
            ),
        )

        async def _apply() -> None:
            self._status_filter = str(holder["status"] or _OPEN_FILTER)
            self._direction_filter = str(holder["direction"] or "all")
            self._sort_by = str(holder["sort"] or "due_date")
            self._interest_only = bool(holder["interest_only"])
            close()
            await self.reload()

        close = open_fullscreen_form(
            self._page,
            title=tr("action.filters", lang),
            lang=lang,
            overlay_key="debt_filters",
            body=[
                form_section(
                    tr("debt.filter_status", lang),
                    [status_chips],
                    hint=tr("debt.filter_status_hint", lang),
                    icon=ft.Icons.FILTER_LIST,
                ),
                form_section(
                    tr("debt.filter_direction", lang),
                    [direction_chips],
                    hint=tr("debt.filter_direction_hint", lang),
                    icon=ft.Icons.SWAP_HORIZ,
                ),
                form_section(
                    None,
                    [labeled_switch(tr("debt.filter_interest_only", lang), interest_sw)],
                    hint=tr("debt.filter_interest_only_hint", lang),
                    icon=ft.Icons.PERCENT,
                ),
                form_section(
                    tr("debt.filter_sort", lang),
                    [sort_chips],
                    hint=tr("debt.filter_sort_hint", lang),
                    icon=ft.Icons.SORT,
                ),
            ],
            on_save=_apply,
            save_label=tr("action.apply", lang, default=tr("action.save", lang)),
            save_icon=ft.Icons.CHECK,
        )

    async def _sync_debt_state(self) -> None:
        """Run interest accrual and overdue marking once per page session."""
        if self._debt_state_synced:
            return
        self._debt_state_synced = True
        accrue = getattr(self._state.container, "accrue_debt_interest", None)
        if accrue is not None:
            try:
                await accrue.execute()
            except Exception:  # noqa: BLE001
                pass
        mark = getattr(self._state.container, "mark_overdue_debts", None)
        if mark is not None:
            try:
                await mark.execute()
            except Exception:  # noqa: BLE001
                pass

    async def reload(self) -> None:
        """Reload debts list for the current filters."""
        self._token = self._state.debts_token
        lang = self._state.language
        if self._cached_debts is None:
            fill_loading(self._list)
            safe_update(self._list)
        self._alert_ids = pending_related_ids(
            self._state.container,
            self._state.settings,
            DEBT_ALERT_KINDS,
        )
        # Do not auto-mark alerts read on every reload (badge display only).

        await self._sync_debt_state()

        direction = (
            None
            if self._direction_filter in ("", "all", None)
            else self._direction_filter
        )
        cache_key = (
            self._token,
            self._status_filter,
            direction,
            self._sort_by,
            self._interest_only,
        )
        try:
            if self._cached_debts is None or self._cache_key != cache_key:
                status_arg = (
                    None
                    if self._status_filter in (_OPEN_FILTER, "", "all", None)
                    else self._status_filter
                )
                debts = await self._state.container.list_debts.execute(
                    status=status_arg,
                    direction=direction,
                    sort_by=self._sort_by,
                )
                if self._status_filter == _OPEN_FILTER:
                    debts = [
                        d
                        for d in debts
                        if (
                            d.status.value
                            if isinstance(d.status, DebtStatus)
                            else str(d.status)
                        )
                        in _OPEN_STATUSES
                    ]
                if self._interest_only:
                    debts = [d for d in debts if d.interest_rate is not None]
                self._cached_debts = debts
                self._cache_key = cache_key
            else:
                debts = self._cached_debts
            debts = self._filter_debts(debts)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            replace_controls(
                self._list, [EmptyState(tr("error.generic", lang))], self._page
            )
            return

        if not debts:
            search_active = bool(self._search_query.strip())
            if search_active:
                empty_key = "empty.debts_search"
            elif (
                self._status_filter != _OPEN_FILTER
                or self._direction_filter not in ("", "all", None)
                or self._interest_only
            ):
                empty_key = "empty.debts_filtered"
            else:
                empty_key = "empty.debts"
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

        cards: list[ft.Control] = []
        if self._status_filter in _OPEN_STATUSES or self._status_filter == _OPEN_FILTER:
            base = self._state.base_currency
            book = await load_rate_book(self._state.container)
            i_owe = Decimal("0")
            owed_to_me = Decimal("0")
            overdue_count = 0
            fx_ok = True
            for debt in debts:
                if debt.status not in (DebtStatus.ACTIVE, DebtStatus.OVERDUE):
                    continue
                if debt.status == DebtStatus.OVERDUE:
                    overdue_count += 1
                converted = try_convert_amount(
                    book,
                    debt.remaining_amount,
                    debt.currency,
                    base,
                )
                if converted is None:
                    fx_ok = False
                    continue
                if debt.direction == DebtDirection.I_OWE:
                    i_owe += converted
                else:
                    owed_to_me += converted
            if not fx_ok:
                snack(self._page, tr("fx.missing_rates", lang), error=True)
            cards.append(
                debts_summary_ring(
                    i_owe=i_owe,
                    owed_to_me=owed_to_me,
                    currency=base,
                    language=lang,
                    overdue_count=overdue_count,
                    page=self._page,
                )
            )
            cards.append(ft.Container(height=4))

        now = datetime.now(timezone.utc)
        lookback = now - timedelta(days=6 * 31)
        try:
            from lib.presentation.tx_query import fetch_transactions_paged

            recent_txs = await fetch_transactions_paged(
                self._state.container.list_transactions,
                date_from=lookback,
                has_debt=True,
            )
        except Exception:  # noqa: BLE001
            recent_txs = []
        txs_by_debt: dict[str, list] = defaultdict(list)
        for tx in recent_txs:
            if not tx.debt_id or "debt_principal" in (tx.tags or []):
                continue
            txs_by_debt[tx.debt_id].append(tx)

        for debt in debts:
            interest = None
            if debt.interest_rate is not None:
                try:
                    interest = compute_debt_interest(debt).interest_amount
                except Exception:  # noqa: BLE001
                    interest = None
            can_repay = debt.status in (DebtStatus.ACTIVE, DebtStatus.OVERDUE)
            sparkline = None
            buckets = bucket_payments_by_month(
                txs_by_debt.get(debt.id, []), months=6, now=now
            )
            if any(v > 0 for _, v in buckets):
                sparkline = debt_payment_sparkline(
                    buckets,
                    color=getattr(debt, "color", None),
                )
            repay_label = (
                tr("debt.repay", lang)
                if debt.direction == DebtDirection.I_OWE
                else tr("debt.receive", lang)
            )
            card = DebtCard(
                debt,
                language=lang,
                interest_amount=interest,
                alert=debt.id in self._alert_ids,
                sparkline=sparkline,
                on_click=self._open_detail,
                on_edit=self._open_editor,
                on_delete=self._confirm_delete,
                on_repay=self._repay if can_repay else None,
                page=self._page,
            )
            cards.append(
                swipe_debt_card(
                    card,
                    language=lang,
                    repay_label=repay_label,
                    on_repay=(lambda d=debt: self._repay(d)) if can_repay else None,
                    on_edit=lambda d=debt: self._open_editor(d),
                    page=self._page,
                )
            )
        if debts:
            prefix_len = len(cards) - len(debts)
            prefix = cards[:prefix_len]
            entity = cards[prefix_len:]
            replace_controls(
                self._list,
                prefix + card_grid(entity, self._page, min_card=300, maximum=2),
                self._page,
            )
            return
        replace_controls(self._list, cards, self._page)

    def _confirm_delete(self, debt: Debt) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_debt.execute(debt.id, force=True)
            except ValueError as exc:
                # Domain guards (e.g. repayments exist) must be shown to the user.
                snack_exception(self._page, exc, lang=lang)
                return
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh(
                "dashboard", "accounts", "transactions", "debts"
            )
            await self.reload()

        confirm_dialog(
            self._page,
            title=tr("action.confirm_delete", lang),
            message=debt.counterparty,
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    def _repay(self, debt: Debt) -> None:
        lang = self._state.language
        i_owe = debt.direction == DebtDirection.I_OWE
        has_interest = debt.interest_rate is not None

        async def _open() -> None:
            try:
                accounts = await self._state.container.list_accounts.execute(active_only=True, corporate=False)
                book = await load_rate_book(self._state.container)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return
            if not accounts:
                snack(self._page, tr("error.no_accounts", lang), error=True)
                return

            default_account = accounts[0].id
            if debt.account_id and any(a.id == debt.account_id for a in accounts):
                default_account = debt.account_id
            default_principal = debt.remaining_amount
            if (
                debt.next_payment_amount is not None
                and debt.next_payment_amount > 0
                and debt.next_payment_amount <= debt.remaining_amount
            ):
                default_principal = debt.next_payment_amount

            convert_hint = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
            account_picker = AccountStripPicker(
                self._page,
                accounts,
                lang=lang,
                value=default_account,
            )

            principal_tf: Optional[ft.TextField] = None
            interest_tf: Optional[ft.TextField] = None
            amount_tf: Optional[ft.TextField] = None
            body: list[ft.Control]

            if has_interest:
                principal_tf = make_amount_field(
                    lang,
                    label=f"{tr('debt.principal_amount', lang)} ({debt.currency})",
                    value=default_principal,
                    autofocus=True,
                )
                interest_tf = make_amount_field(
                    lang,
                    label=f"{tr('debt.interest_amount', lang)} ({debt.currency})",
                    value="",
                )
                from lib.presentation.form_keyboard import wire_field_chain

                wire_field_chain(self._page, [principal_tf, interest_tf])
                body = [account_picker, principal_tf, interest_tf, convert_hint]

                def _refresh_conversion(_aid: str | None = None) -> None:
                    assert principal_tf is not None and interest_tf is not None
                    account = next(
                        (a for a in accounts if a.id == account_picker.value), accounts[0]
                    )
                    try:
                        principal = parse_amount_field(principal_tf)
                        interest = parse_optional_amount_field(interest_tf)
                    except (InvalidOperation, ValueError):
                        convert_hint.value = ""
                        safe_update(convert_hint)
                        return
                    if principal < 0 or interest < 0 or (principal + interest) <= 0:
                        convert_hint.value = ""
                        safe_update(convert_hint)
                        return
                    debt_total = principal + interest
                    converted = book.convert(
                        debt_total, debt.currency, account.currency
                    )
                    if converted is None:
                        convert_hint.value = tr(
                            "debt.no_rate",
                            lang,
                            pair=f"{debt.currency}/{account.currency}",
                        )
                        convert_hint.color = ft.Colors.ERROR
                    else:
                        convert_hint.value = format_money(converted, account.currency)
                        convert_hint.color = ft.Colors.ON_SURFACE_VARIANT
                    safe_update(convert_hint)

                attach_grouped_digits(
                    principal_tf, lang, extra_on_change=_refresh_conversion
                )
                attach_grouped_digits(
                    interest_tf, lang, extra_on_change=_refresh_conversion
                )
                account_picker.bind_changed(_refresh_conversion)
            else:
                amount_tf = make_amount_field(
                    lang,
                    label=tr("field.amount", lang),
                    value=(
                        default_principal
                        if accounts[0].currency.upper() == debt.currency.upper()
                        or (
                            debt.account_id
                            and next(
                                (
                                    a.currency.upper() == debt.currency.upper()
                                    for a in accounts
                                    if a.id == default_account
                                ),
                                False,
                            )
                        )
                        else ""
                    ),
                    autofocus=True,
                )
                from lib.presentation.form_keyboard import wire_field_chain

                wire_field_chain(self._page, [amount_tf])
                body = [account_picker, amount_tf, convert_hint]

                def _refresh_conversion(_aid: str | None = None) -> None:
                    assert amount_tf is not None
                    account = next(
                        (a for a in accounts if a.id == account_picker.value), accounts[0]
                    )
                    try:
                        amount = parse_amount_field(amount_tf)
                    except (InvalidOperation, ValueError):
                        convert_hint.value = ""
                        safe_update(convert_hint)
                        return
                    if amount <= 0:
                        convert_hint.value = ""
                        safe_update(convert_hint)
                        return
                    converted = book.convert(amount, account.currency, debt.currency)
                    if converted is None:
                        convert_hint.value = tr(
                            "debt.no_rate",
                            lang,
                            pair=f"{account.currency}/{debt.currency}",
                        )
                        convert_hint.color = ft.Colors.ERROR
                    else:
                        convert_hint.value = tr(
                            "debt.converted_amount",
                            lang,
                            amount=format_money(converted, debt.currency),
                        )
                        convert_hint.color = ft.Colors.ON_SURFACE_VARIANT
                    safe_update(convert_hint)

                attach_grouped_digits(
                    amount_tf, lang, extra_on_change=_refresh_conversion
                )
                account_picker.bind_changed(_refresh_conversion)

            async def _save() -> None:
                account_id = account_picker.value or accounts[0].id
                account = next(
                    (a for a in accounts if a.id == account_id), accounts[0]
                )
                interest_amount: Optional[Decimal] = None

                if has_interest:
                    assert principal_tf is not None and interest_tf is not None
                    try:
                        principal = parse_amount_field(principal_tf)
                        interest_amount = parse_optional_amount_field(interest_tf)
                        if principal < 0 or interest_amount < 0:
                            raise InvalidOperation
                        debt_total = principal + interest_amount
                        if debt_total <= 0:
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        snack(self._page, tr("invalid_amount", lang), error=True)
                        return
                    pay_amount = book.convert(
                        debt_total, debt.currency, account.currency
                    )
                    if pay_amount is None:
                        snack(
                            self._page,
                            tr(
                                "debt.no_rate",
                                lang,
                                pair=f"{debt.currency}/{account.currency}",
                            ),
                            error=True,
                        )
                        return
                    if interest_amount <= 0:
                        interest_amount = None
                else:
                    assert amount_tf is not None
                    try:
                        pay_amount = parse_amount_field(amount_tf)
                        if pay_amount <= 0:
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        snack(self._page, tr("invalid_amount", lang), error=True)
                        return
                    converted = book.convert(
                        pay_amount, account.currency, debt.currency
                    )
                    if converted is None:
                        snack(
                            self._page,
                            tr(
                                "debt.no_rate",
                                lang,
                                pair=f"{account.currency}/{debt.currency}",
                            ),
                            error=True,
                        )
                        return

                if i_owe and pay_amount > account.balance:
                    snack(self._page, tr("error.insufficient_funds", lang), error=True)
                    return
                try:
                    await self._state.container.repay_debt.execute(
                        debt.id,
                        pay_amount,
                        account_id=account_id,
                        interest_amount=interest_amount,
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=self._state.language)
                    return
                close()
                self._state.bump_refresh("dashboard", "accounts", "transactions", "debts")
                await self.reload()
                snack(self._page, tr("action.saved", lang))

            close = open_fullscreen_form(
                self._page,
                title=(
                    f"{tr('debt.repay' if i_owe else 'debt.receive', lang)}"
                    f" · {debt.counterparty}"
                ),
                lang=lang,
                overlay_key="debt_repay",
                body=body,
                on_save=_save,
                save_icon=ft.Icons.PAYMENTS_OUTLINED,
            )

        run_async(self._page, _open)

    def _open_detail(self, debt: Debt) -> None:
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
                fresh = await self._state.container.debt_repository.get_by_id(debt.id)
                debt_obj = fresh or debt
                projection = await self._state.container.get_debt_projection.execute(
                    debt_obj.id
                )
                accounts = {
                    a.id: a
                    for a in await self._state.container.list_accounts.execute(
                        active_only=False
                    )
                }
                txs = await self._state.container.list_transactions.execute(
                    debt_id=debt_obj.id,
                    limit=_PAYMENT_PAGE + 1,
                    offset=0,
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return

            has_more = len(txs) > _PAYMENT_PAGE
            shown = [
                t for t in txs[:_PAYMENT_PAGE]
                if "debt_principal" not in (t.tags or [])
            ]
            # Keep pagination offset based on raw fetch; filter principals for display.
            if not shown and txs:
                shown = []
            offset = {"n": len(txs[:_PAYMENT_PAGE])}

            streak = 0
            sparkline_ctrl = ft.Container(height=0)
            series_uc = getattr(
                self._state.container, "get_debt_payment_series", None
            )
            if series_uc is not None:
                try:
                    series = await series_uc.execute(debt_obj.id, months=6)
                    streak = series.streak_months
                    if any(v > 0 for _, v in series.buckets):
                        sparkline_ctrl = debt_payment_sparkline(
                            series.buckets,
                            color=getattr(debt_obj, "color", None),
                        )
                except Exception:  # noqa: BLE001
                    pass

            projection_card = debt_projection_card(
                language=lang,
                currency=debt_obj.currency,
                recommended_monthly=projection.recommended_monthly_payment,
                average_monthly=projection.average_monthly_payment,
                projected_date=projection.projected_payoff_date,
                is_on_track=projection.is_on_track,
                streak_months=streak,
            )

            payments_col = ft.Column(spacing=8, tight=True)
            payments_col.controls = [
                ft.Text(tr("debt.payments", lang), weight=ft.FontWeight.W_700),
            ]
            if not shown:
                payments_col.controls.append(muted_text("—"))
            else:
                for tx in shown:
                    payments_col.controls.append(
                        self._payment_row(debt_obj, tx, accounts, close_holder)
                    )

            async def _more(_e: ft.ControlEvent | None = None) -> None:
                more = await self._state.container.list_transactions.execute(
                    debt_id=debt_obj.id,
                    limit=_PAYMENT_PAGE + 1,
                    offset=offset["n"],
                )
                more_has = len(more) > _PAYMENT_PAGE
                chunk = more[:_PAYMENT_PAGE]
                offset["n"] += len(chunk)
                for tx in chunk:
                    if "debt_principal" in (tx.tags or []):
                        continue
                    payments_col.controls.append(
                        self._payment_row(debt_obj, tx, accounts, close_holder)
                    )
                load_more_btn.visible = more_has
                safe_update(payments_col)
                safe_update(load_more_btn)

            load_more_btn = ft.TextButton(
                tr("action.load_more", lang),
                visible=has_more,
                on_click=lambda e: run_async(self._page, _more, e),
            )

            async def _do_archive(_e: ft.ControlEvent | None = None) -> None:
                await self._archive(debt_obj, close_holder)

            def _edit(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._open_editor(debt_obj)

            def _repay_action(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._repay(debt_obj)

            actions: list[ft.Control] = []
            if debt_obj.status in (DebtStatus.ACTIVE, DebtStatus.OVERDUE):
                actions.append(
                    ft.FilledButton(
                        tr(
                            "debt.repay"
                            if debt_obj.direction == DebtDirection.I_OWE
                            else "debt.receive",
                            lang,
                        ),
                        icon=ft.Icons.PAYMENTS_OUTLINED,
                        on_click=_repay_action,
                    )
                )
            if shown:
                async def _undo(_e: ft.ControlEvent | None = None) -> None:
                    try:
                        await self._state.container.undo_last_debt_payment.execute(
                            debt_obj.id
                        )
                    except Exception as exc:  # noqa: BLE001
                        snack_exception(self._page, exc, lang=self._state.language)
                        return
                    self._state.bump_refresh(
                        "dashboard", "accounts", "transactions", "debts"
                    )
                    await self.reload()
                    refreshed = await self._state.container.debt_repository.get_by_id(
                        debt_obj.id
                    )
                    _close_detail()
                    if refreshed is not None:
                        self._open_detail(refreshed)
                    snack(self._page, tr("action.saved", lang))

                actions.append(
                    ft.OutlinedButton(
                        tr("debt.undo_last", lang),
                        icon=ft.Icons.UNDO,
                        on_click=lambda e: run_async(self._page, _undo, e),
                    )
                )
            actions.append(
                ft.FilledTonalButton(
                    tr("action.edit", lang),
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=_edit,
                )
            )
            if debt_obj.status == DebtStatus.PAID:
                actions.append(
                    ft.OutlinedButton(
                        tr("debt.archive", lang),
                        icon=ft.Icons.ARCHIVE_OUTLINED,
                        on_click=lambda e: run_async(self._page, _do_archive, e),
                    )
                )
            elif debt_obj.status in (DebtStatus.ACTIVE, DebtStatus.OVERDUE):
                async def _forgive(_e: ft.ControlEvent | None = None) -> None:
                    forgive = getattr(self._state.container, "forgive_debt", None)
                    if forgive is None:
                        return
                    try:
                        await forgive.execute(debt_obj.id)
                        audit = getattr(self._state.container, "append_debt_audit", None)
                        if audit is not None:
                            await audit.execute(debt_obj.id, "forgive")
                    except Exception as exc:  # noqa: BLE001
                        snack_exception(self._page, exc, lang=lang)
                        return
                    self._state.bump_refresh("dashboard", "debts")
                    _close_detail()
                    await self.reload()
                    snack(self._page, tr("action.saved", lang))

                actions.append(
                    ft.OutlinedButton(
                        tr("debt.forgive", lang),
                        icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                        on_click=lambda e: run_async(self._page, _forgive, e),
                    )
                )

            async def _duplicate(_e: ft.ControlEvent | None = None) -> None:
                dup = getattr(self._state.container, "duplicate_debt", None)
                if dup is None:
                    return
                try:
                    copy = await dup.execute(debt_obj.id)
                    audit = getattr(self._state.container, "append_debt_audit", None)
                    if audit is not None:
                        await audit.execute(
                            debt_obj.id,
                            "duplicate",
                            details={"copy_id": copy.id},
                        )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                self._state.bump_refresh("debts")
                _close_detail()
                await self.reload()
                snack(self._page, tr("action.saved", lang))

            actions.append(
                ft.TextButton(
                    tr("debt.duplicate", lang),
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda e: run_async(self._page, _duplicate, e),
                )
            )

            interest = None
            if debt_obj.interest_rate is not None:
                try:
                    result = await self._state.container.calculate_debt_interest.execute(
                        debt_obj.id
                    )
                    interest = result.interest_amount
                except Exception:  # noqa: BLE001
                    interest = None

            schedule_btn: ft.Control = ft.Container(height=0)
            if (
                debt_obj.status in (DebtStatus.ACTIVE, DebtStatus.OVERDUE)
                and debt_obj.next_payment_amount is not None
                and debt_obj.next_payment_amount > 0
            ):
                schedule_btn = ft.OutlinedButton(
                    tr(
                        "debt.pay_scheduled",
                        lang,
                        amount=format_money(
                            debt_obj.next_payment_amount, debt_obj.currency
                        ),
                    ),
                    icon=ft.Icons.EVENT,
                    on_click=_repay_action,
                )

            audit_rows: list[ft.Control] = []
            list_audit = getattr(self._state.container, "list_debt_audit", None)
            if list_audit is not None:
                try:
                    entries = await list_audit.execute(debt_obj.id, limit=8)
                    if entries:
                        audit_rows.append(
                            ft.Text(tr("debt.audit", lang), weight=ft.FontWeight.W_700)
                        )
                        for entry in entries:
                            action_key = f"debt.audit.{entry.action}"
                            label = tr(action_key, lang)
                            if label == action_key:
                                label = entry.action
                            audit_rows.append(
                                muted_text(
                                    f"{format_date(entry.created_at)} · {label}"
                                )
                            )
                except Exception:  # noqa: BLE001
                    pass

            body.controls = [
                DebtCard(
                    debt_obj,
                    language=lang,
                    interest_amount=interest,
                    projected_payoff_date=projection.projected_payoff_date,
                    page=self._page,
                ),
                projection_card,
                sparkline_ctrl,
                schedule_btn,
                ft.Row(wrap=True, spacing=8, controls=actions),
                payments_col,
                load_more_btn,
                *audit_rows,
            ]
            safe_update(body)

        close = open_fullscreen_form(
            self._page,
            title=debt.counterparty,
            lang=lang,
            overlay_key="debt_detail",
            body=[body],
            on_save=None,
            show_save=False,
        )
        close_holder["close"] = close
        run_async(self._page, _load)

    def _payment_row(
        self,
        debt: Debt,
        tx: object,
        accounts: dict,
        close_holder: dict,
    ) -> ft.Control:
        lang = self._state.language
        credit = debt_credit_amount(tx)  # type: ignore[arg-type]
        interest = debt_interest_from_tags(tx)  # type: ignore[arg-type]
        account = accounts.get(getattr(tx, "account_id", ""))
        account_name = account.name if account is not None else "—"
        comment = (getattr(tx, "comment", "") or "").strip()
        date_txt = format_date(getattr(tx, "date", None))
        split = ""
        if interest > 0:
            split = tr(
                "debt.payment_split",
                lang,
                principal=format_money(credit, debt.currency),
                interest=format_money(interest, debt.currency),
            )

        def _delete(_e: ft.ControlEvent | None = None) -> None:
            async def _do() -> None:
                try:
                    await self._state.container.delete_debt_payment.execute(
                        getattr(tx, "id"),
                        debt_id=debt.id,
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=self._state.language)
                    return
                self._state.bump_refresh(
                    "dashboard", "accounts", "transactions", "debts"
                )
                closer = close_holder.get("close")
                if callable(closer):
                    closer()
                await self.reload()
                refreshed = await self._state.container.debt_repository.get_by_id(
                    debt.id
                )
                if refreshed is not None:
                    self._open_detail(refreshed)
                snack(self._page, tr("action.saved", lang))

            confirm_dialog(
                self._page,
                title=tr("action.confirm_delete", lang),
                message=format_money(credit, debt.currency),
                confirm_text=tr("action.delete", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=_do,
            )

        return card_surface(
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                f"{date_txt} · {format_money(credit, debt.currency)}",
                                weight=ft.FontWeight.W_600,
                            ),
                            muted_text(account_name),
                            muted_text(tr("debt.payment_type", lang)),
                            muted_text(split) if split else ft.Container(height=0),
                            muted_text(comment) if comment else ft.Container(height=0),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.ERROR,
                        on_click=_delete,
                    ),
                ],
            )
        )

    async def _archive(self, debt: Debt, close_holder: dict) -> None:
        try:
            await self._state.container.archive_debt.execute(debt.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        closer = close_holder.get("close")
        if callable(closer):
            closer()
        self._state.bump_refresh("dashboard", "debts", "analytics")
        await self.reload()
        snack(self._page, tr("action.saved", self._state.language))

    def _open_editor(self, debt: Optional[Debt] = None) -> None:
        lang = self._state.language

        async def _open() -> None:
            accounts: list = []
            try:
                accounts = await self._state.container.list_accounts.execute(active_only=True, corporate=False)
            except Exception:  # noqa: BLE001
                accounts = []

            known: list[str] = []
            try:
                list_cp = getattr(
                    self._state.container, "list_debt_counterparties", None
                )
                if list_cp is not None:
                    known = await list_cp.execute()
            except Exception:  # noqa: BLE001
                known = []

            name_tf = ft.TextField(
                label=tr("field.name", lang),
                value=debt.counterparty if debt else "",
            )
            from lib.presentation.form_keyboard import configure_field, wire_field_chain

            configure_field(name_tf, "name")
            known_dd: Optional[ft.Dropdown] = None
            if known:
                known_dd = ft.Dropdown(
                    label=tr("debt.counterparty_known", lang),
                    options=[
                        ft.DropdownOption(key=n, text=n) for n in known[:80]
                    ],
                    dense=True,
                )

                def _pick_known(_e: ft.ControlEvent | None = None) -> None:
                    if known_dd and known_dd.value:
                        name_tf.value = known_dd.value
                        try:
                            safe_update(name_tf)
                        except Exception:  # noqa: BLE001
                            pass

                bind_dropdown_select(known_dd, _pick_known)

            amount_tf = make_amount_field(
                lang,
                label=tr("field.amount", lang),
                value=debt.amount if debt else "",
            )
            currency_picker = CurrencyTickerPicker(
                self._page,
                lang=lang,
                label=tr("field.currency", lang),
                value=debt.currency if debt else self._state.base_currency,
                include_crypto=True,
                expand=True,
            )
            direction_dd = ft.Dropdown(
                label=tr("field.direction", lang),
                value=(
                    debt.direction.value
                    if debt
                    else DebtDirection.I_OWE.value
                ),
                options=[
                    icon_dropdown_option(
                        DebtDirection.I_OWE.value,
                        tr("debt.i_owe", lang),
                        ft.Icons.CALL_MADE,
                        icon_color=ft.Colors.ERROR,
                    ),
                    icon_dropdown_option(
                        DebtDirection.OWED_TO_ME.value,
                        tr("debt.owed_to_me", lang),
                        ft.Icons.CALL_RECEIVED,
                        icon_color=ft.Colors.PRIMARY,
                    ),
                ],
            )
            rate_tf = ft.TextField(
                label=tr("field.interest", lang),
                value=str(debt.interest_rate)
                if debt and debt.interest_rate is not None
                else "",
            )
            configure_field(rate_tf, "number")
            accrue_sw = ft.Switch(
                value=bool(debt.accrue_interest) if debt else False,
            )
            due_field = DateTimeField(
                self._page,
                lang=lang,
                label=tr("field.date", lang),
                value=debt.due_date if debt and debt.due_date else None,
                allow_clear=True,
            )
            next_pay_field = DateTimeField(
                self._page,
                lang=lang,
                label=tr("debt.next_payment_date", lang),
                value=debt.next_payment_date
                if debt and debt.next_payment_date
                else None,
                allow_clear=True,
            )
            next_amt_tf = make_amount_field(
                lang,
                label=tr("debt.next_payment_amount", lang),
                value=debt.next_payment_amount
                if debt and debt.next_payment_amount is not None
                else "",
            )
            comment_tf = ft.TextField(
                label=tr("field.comment", lang),
                value=debt.comment if debt else "",
            )
            configure_field(comment_tf, "text")
            interval_tf = ft.TextField(
                label=tr("debt.payment_interval", lang),
                value=str(getattr(debt, "payment_interval_months", 1) if debt else 1),
            )
            configure_field(interval_tf, "number")
            wire_field_chain(
                self._page,
                [name_tf, amount_tf, rate_tf, next_amt_tf, interval_tf, comment_tf],
            )

            initial_icon = getattr(debt, "icon", None) or "credit_card"
            initial_color = getattr(debt, "color", None) or "#F87171"
            selected_icon = {"value": initial_icon}
            selected_color = {"value": initial_color}
            icon_preview = ft.Container(
                width=48,
                height=48,
                border_radius=24,
                alignment=ft.Alignment.CENTER,
                bgcolor=initial_color,
                content=account_icon_control(
                    initial_icon,
                    size=24,
                    color=ICON_CATALOG_GLYPH,
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
                    selected_icon["value"],
                    size=24,
                    color=ICON_CATALOG_GLYPH,
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

            _refresh_previews()
            appearance_row = ft.Row(
                spacing=12,
                controls=[
                    ft.GestureDetector(content=icon_preview, on_tap=lambda _e: open_icon_picker(
                        self._page,
                        lang=lang,
                        groups=entity_icon_groups(),
                        selected=selected_icon["value"],
                        on_select=_select_icon,
                        render_icon=lambda key: account_icon_control(
                            key, size=22, color=ICON_CATALOG_GLYPH
                        ),
                        overlay_key="debt_icon_picker",
                    )),
                    ft.GestureDetector(content=color_preview, on_tap=lambda _e: open_color_picker(
                        self._page,
                        lang=lang,
                        colors=ACCOUNT_COLORS,
                        selected=selected_color["value"],
                        on_select=_select_color,
                        overlay_key="debt_color_picker",
                    )),
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

            def _apply_template(template: DebtTemplate) -> None:
                name_tf.value = tr(template.name_key, lang)
                selected_icon["value"] = template.icon
                selected_color["value"] = template.color
                direction_dd.value = template.direction.value
                accrue_sw.value = template.accrue_interest
                interval_tf.value = str(template.payment_interval_months)
                if template.default_amount and not amount_text(amount_tf).strip():
                    amount_tf.value = template.default_amount
                if template.interest_rate:
                    rate_tf.value = template.interest_rate
                else:
                    rate_tf.value = ""
                if template.next_payment_amount:
                    next_amt_tf.value = template.next_payment_amount
                _refresh_previews()
                for ctrl in (name_tf, amount_tf, rate_tf, next_amt_tf, direction_dd):
                    try:
                        safe_update(ctrl)
                    except Exception:  # noqa: BLE001
                        pass

            template_strip = h_scroll(
                [
                    debt_template_chip(t, language=lang, on_click=_apply_template)
                    for t in DEBT_TEMPLATES
                ],
                spacing=10,
                height=52,
                padding=ft.Padding.only(bottom=4),
            )

            controls_main: list[ft.Control] = []
            if known_dd is not None:
                controls_main.append(known_dd)
            controls_main.extend(
                [
                    appearance_row,
                    name_tf,
                    amount_tf,
                    currency_picker,
                    form_hint(tr("debt.currency_change_hint", lang), size=11),
                    direction_dd,
                ]
            )
            account_dd: Optional[AccountStripPicker] = None
            record_cash = ft.Checkbox(
                label=tr("debt.record_cash", lang),
                value=True,
            )
            default_acc = accounts[0].id if accounts else None
            if debt and debt.account_id and any(a.id == debt.account_id for a in accounts):
                default_acc = debt.account_id
            if accounts and default_acc:
                account_dd = AccountStripPicker(
                    self._page,
                    accounts,
                    lang=lang,
                    label=tr("debt.default_account", lang),
                    value=default_acc,
                )
            account_bits: list[ft.Control] = []
            if debt is None and account_dd is not None:
                account_bits.extend(
                    [
                        record_cash,
                        form_hint(tr("debt.record_cash_hint", lang), size=11),
                        account_dd,
                    ]
                )
            elif debt is not None:
                account_bits.append(
                    ft.Text(
                        f"{tr('field.remaining', lang)}: "
                        f"{format_money(debt.remaining_amount, debt.currency)}",
                        size=13,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
                if account_dd is not None:
                    account_bits.append(account_dd)

            interest_bits: list[ft.Control] = [
                rate_tf,
                labeled_switch(tr("debt.accrue_interest", lang), accrue_sw),
                form_hint(tr("debt.accrue_interest_hint", lang), size=11),
            ]
            schedule_bits: list[ft.Control] = [
                due_field,
                next_pay_field,
                next_amt_tf,
                interval_tf,
                form_hint(tr("debt.payment_interval_hint", lang), size=11),
            ]
            detail_bits: list[ft.Control] = [comment_tf]

            body_sections: list[ft.Control] = []
            if debt is None:
                body_sections.append(
                    form_section(
                        tr("debt.templates", lang),
                        [template_strip],
                        hint=tr("debt.templates_hint", lang),
                    )
                )
            body_sections.append(
                form_section(
                    tr("form.section.main", lang),
                    controls_main,
                    icon=ft.Icons.ACCOUNT_BALANCE,
                )
            )
            if account_bits:
                body_sections.append(
                    form_section(
                        tr("form.section.account", lang),
                        account_bits,
                        icon=ft.Icons.WALLET,
                    )
                )
            body_sections.extend(
                [
                    form_section(
                        tr("form.section.interest", lang),
                        interest_bits,
                        icon=ft.Icons.PERCENT,
                    ),
                    form_section(
                        tr("form.section.schedule", lang),
                        schedule_bits,
                        icon=ft.Icons.EVENT,
                    ),
                    form_section(
                        tr("form.section.details", lang),
                        detail_bits,
                        icon=ft.Icons.NOTES,
                    ),
                ]
            )

            async def _save() -> None:
                name = require_name(name_tf, self._page, lang)
                if not name:
                    return
                amount = require_positive_amount(amount_tf, self._page, lang)
                if amount is None:
                    return
                rate = None
                if (rate_tf.value or "").strip():
                    rate = Decimal(str(rate_tf.value).replace(",", "."))
                next_amt = None
                try:
                    next_amt = parse_optional_amount_field(next_amt_tf)
                    if next_amt is not None and next_amt <= 0:
                        next_amt = None
                except (InvalidOperation, ValueError):
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
                try:
                    interval_months = max(
                        1, int(str(interval_tf.value or "1").strip() or "1")
                    )
                except ValueError:
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
                due = due_field.value
                preferred_account = (
                    str(account_dd.value)
                    if account_dd is not None and account_dd.value
                    else (debt.account_id if debt else None)
                )
                entity = Debt(
                    id=debt.id
                    if debt
                    else Debt(
                        counterparty="tmp",
                        amount=1,
                        remaining_amount=1,
                        direction=DebtDirection.I_OWE,
                    ).id,
                    counterparty=name,
                    amount=amount,
                    remaining_amount=debt.remaining_amount if debt else amount,
                    currency=(currency_picker.value or "RUB").upper(),
                    direction=DebtDirection(direction_dd.value),
                    status=debt.status if debt else DebtStatus.ACTIVE,
                    interest_rate=rate,
                    due_date=due,
                    next_payment_date=next_pay_field.value,
                    next_payment_amount=next_amt,
                    accrue_interest=bool(accrue_sw.value),
                    accrued_interest=debt.accrued_interest if debt else Decimal("0"),
                    last_interest_accrued_at=(
                        debt.last_interest_accrued_at if debt else None
                    ),
                    account_id=preferred_account,
                    started_at=debt.started_at if debt else datetime.now(timezone.utc),
                    comment=comment_tf.value or "",
                    icon=selected_icon["value"],
                    color=selected_color["value"],
                    payment_interval_months=interval_months,
                    created_at=debt.created_at if debt else datetime.now(timezone.utc),
                )
                try:
                    if debt:
                        await self._state.container.update_debt.execute(entity)
                        audit = getattr(self._state.container, "append_debt_audit", None)
                        if audit is not None:
                            await audit.execute(debt.id, "update")
                    else:
                        cash_id = None
                        if (
                            record_cash.value
                            and account_dd is not None
                            and account_dd.value
                        ):
                            cash_id = account_dd.value
                            account = next(
                                (a for a in accounts if a.id == cash_id), None
                            )
                            if account is not None:
                                entity.currency = account.currency.upper()
                            if (
                                account is not None
                                and entity.direction == DebtDirection.OWED_TO_ME
                                and amount > account.balance
                            ):
                                snack(
                                    self._page,
                                    tr("error.insufficient_funds", lang),
                                    error=True,
                                )
                                return
                        created = await self._state.container.create_debt.execute(
                            entity,
                            account_id=cash_id,
                        )
                        audit = getattr(self._state.container, "append_debt_audit", None)
                        if audit is not None:
                            await audit.execute(created.id, "create")
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=self._state.language)
                    return
                close()
                self._state.bump_refresh(
                    "dashboard", "accounts", "transactions", "debts"
                )
                await self.reload()
                snack(self._page, tr("action.saved", lang))

            close = open_fullscreen_form(
                self._page,
                title=tr("action.edit", lang) if debt else tr("action.add", lang),
                lang=lang,
                overlay_key="debt_editor",
                wrap_body=False,
                body=body_sections,
                on_save=_save,
            )

        run_async(self._page, _open)
