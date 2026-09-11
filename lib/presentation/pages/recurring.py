"""Recurring income/expense templates (auto-create into the ledger)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.recurring_rule import RecurringInterval, RecurringRule
from lib.domain.entities.transaction import TransactionType
from lib.domain.use_cases.recurring import preview_recurring_dates
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.dropdown_options import icon_dropdown_option
from lib.presentation.form_keyboard import configure_field, wire_field_chain
from lib.presentation.form_validation import require_positive_amount
from lib.presentation.layout import make_v_scroll
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.styles import card_surface, form_hint, labeled_switch, muted_text
from lib.presentation.ui_motion import replace_controls
from lib.presentation.utils import format_date, format_money, run_async, snack, snack_exception, tr
from lib.presentation.widgets.account_strip_picker import AccountStripPicker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def _interval_label(interval: RecurringInterval, lang: str) -> str:
    key = interval.value if isinstance(interval, RecurringInterval) else str(interval)
    return tr(f"recurring.interval.{key}", lang)


class RecurringPage(ft.Column):
    """List and edit recurring transaction templates."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._list = make_v_scroll(spacing=8)
        self._accounts: list = []
        lang = state.language
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.recurring", lang),
                    body=self._list,
                    page=page,
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.add", lang),
                            on_click=lambda _e: run_async(page, self._open_editor),
                        ),
                    ],
                ),
                page=page,
            )
        )
        self._reload_gate = ReloadGate(page, self, self.reload)
        self._reload_gate.request()

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    async def reload(self, animate: bool = False) -> None:
        lang = self._state.language
        try:
            self._accounts = await self._state.container.list_accounts.execute(
                active_only=True, corporate=False
            )
            items = await self._state.container.list_recurring_rules.execute(
                include_paused=True
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        if not items:
            replace_controls(
                self._list,
                [
                    EmptyState(
                        tr("recurring.empty", lang),
                        icon=ft.Icons.EVENT_REPEAT,
                        action_label=tr("action.add", lang),
                        on_action=lambda _e: run_async(self._page, self._open_editor),
                        page=self._page,
                    )
                ],
                self._page,
            )
            return
        cards = [self._card(rule, lang) for rule in items]
        replace_controls(self._list, cards, self._page)

    def _card(self, rule: RecurringRule, lang: str) -> ft.Control:
        type_key = (
            rule.type.value if isinstance(rule.type, TransactionType) else str(rule.type)
        )
        kind_label = tr(f"transaction.{type_key}", lang)
        nxt = format_date(
            datetime(rule.next_run.year, rule.next_run.month, rule.next_run.day, tzinfo=timezone.utc)
        )
        upcoming = preview_recurring_dates(
            rule.next_run, rule.interval, interval_count=rule.interval_count, count=3
        )
        preview = ", ".join(d.isoformat() for d in upcoming)
        paused = bool(rule.paused)
        return card_surface(
            ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Text(rule.name, weight=ft.FontWeight.W_700, expand=True),
                            ft.Text(
                                format_money(rule.amount, rule.currency),
                                weight=ft.FontWeight.W_700,
                            ),
                        ],
                    ),
                    muted_text(
                        f"{kind_label} · {_interval_label(rule.interval, lang)}",
                        size=12,
                    ),
                    muted_text(tr("recurring.next", lang, date=nxt), size=12),
                    muted_text(tr("recurring.preview", lang, dates=preview), size=11),
                    ft.Row(
                        spacing=6,
                        wrap=True,
                        controls=[
                            ft.TextButton(
                                tr("action.edit", lang),
                                on_click=lambda _e, r=rule: run_async(
                                    self._page, self._open_editor, r
                                ),
                            ),
                            ft.TextButton(
                                tr("recurring.resume", lang) if paused else tr("recurring.pause", lang),
                                on_click=lambda _e, r=rule, p=not paused: run_async(
                                    self._page, self._pause, r, p
                                ),
                            ),
                            ft.TextButton(
                                tr("recurring.skip", lang),
                                on_click=lambda _e, r=rule: run_async(
                                    self._page, self._skip, r
                                ),
                            ),
                            ft.TextButton(
                                tr("action.delete", lang),
                                on_click=lambda _e, r=rule: self._confirm_delete(r),
                            ),
                        ],
                    ),
                ],
            ),
            padding=12,
        )

    async def _pause(self, rule: RecurringRule, paused: bool) -> None:
        try:
            await self._state.container.pause_recurring_rule.execute(rule.id, paused=paused)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        snack(self._page, tr("action.saved", self._state.language))
        await self.reload()

    async def _skip(self, rule: RecurringRule) -> None:
        try:
            await self._state.container.skip_recurring_occurrence.execute(rule.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        snack(self._page, tr("action.saved", self._state.language))
        await self.reload()

    def _confirm_delete(self, rule: RecurringRule) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_recurring_rule.execute(rule.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            snack(self._page, tr("action.saved", lang))
            await self.reload()

        confirm_dialog(
            self._page,
            title=tr("action.delete", lang),
            message=rule.name,
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    async def _open_editor(self, rule: Optional[RecurringRule] = None) -> None:
        lang = self._state.language
        if not self._accounts:
            try:
                self._accounts = await self._state.container.list_accounts.execute(
                    active_only=True, corporate=False
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
        if not self._accounts:
            snack(self._page, tr("error.no_accounts", lang), error=True)
            return
        name_tf = ft.TextField(label=tr("field.name", lang), value=rule.name if rule else "")
        configure_field(name_tf, "name")
        amount_tf = make_amount_field(
            lang, label=tr("field.amount", lang), value=rule.amount if rule else ""
        )
        type_dd = ft.Dropdown(
            label=tr("field.type", lang),
            value=(
                rule.type.value
                if rule and hasattr(rule.type, "value")
                else (str(rule.type) if rule else TransactionType.EXPENSE.value)
            ),
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
        interval_dd = ft.Dropdown(
            label=tr("recurring.interval", lang),
            value=(
                rule.interval.value
                if rule and hasattr(rule.interval, "value")
                else (str(rule.interval) if rule else RecurringInterval.MONTHLY.value)
            ),
            options=[
                icon_dropdown_option(i.value, _interval_label(i, lang), ft.Icons.EVENT)
                for i in RecurringInterval
            ],
        )
        count_tf = ft.TextField(
            label=tr("recurring.interval_count", lang),
            value=str(rule.interval_count if rule else 1),
        )
        configure_field(count_tf, "number")
        category_tf = ft.TextField(
            label=tr("field.category", lang),
            value=rule.category if rule else "",
        )
        comment_tf = ft.TextField(
            label=tr("field.comment", lang),
            value=rule.comment if rule else "",
        )
        configure_field(comment_tf, "text")
        wire_field_chain(self._page, [name_tf, amount_tf, count_tf, category_tf, comment_tf])
        account_picker = AccountStripPicker(
            self._page,
            self._accounts,
            lang=lang,
            value=rule.account_id if rule else self._accounts[0].id,
        )
        next_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("field.date", lang),
            value=(
                datetime.combine(rule.next_run, datetime.min.time(), tzinfo=timezone.utc)
                if rule
                else datetime.now(timezone.utc)
            ),
        )
        auto_sw = ft.Switch(value=bool(rule.auto_create) if rule else True)
        preview_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        def _refresh_preview(_e: object = None) -> None:
            try:
                start = next_field.value
                start_d = start.date() if isinstance(start, datetime) else date.today()
                interval = RecurringInterval(interval_dd.value or RecurringInterval.MONTHLY.value)
                count = int(count_tf.value or "1")
                dates = preview_recurring_dates(start_d, interval, interval_count=count, count=3)
                preview_text.value = tr(
                    "recurring.preview", lang, dates=", ".join(d.isoformat() for d in dates)
                )
            except Exception:  # noqa: BLE001
                preview_text.value = ""
            try:
                preview_text.update()
            except Exception:  # noqa: BLE001
                pass

        interval_dd.on_change = _refresh_preview
        count_tf.on_change = _refresh_preview
        _refresh_preview()

        async def _save() -> None:
            name = (name_tf.value or "").strip()
            if not name:
                snack(self._page, tr("error.generic", lang), error=True)
                return
            try:
                amount = parse_amount(amount_tf.value)
                require_positive_amount(amount)
            except Exception:
                snack(self._page, tr("invalid_amount", lang), error=True)
                return
            try:
                count = int(count_tf.value or "1")
            except ValueError:
                snack(self._page, tr("invalid_amount", lang), error=True)
                return
            start = next_field.value
            if start is None:
                snack(self._page, tr("invalid_date", lang), error=True)
                return
            start_d = start.date() if isinstance(start, datetime) else start
            account = next(
                (a for a in self._accounts if a.id == account_picker.value),
                self._accounts[0],
            )
            entity = RecurringRule(
                id=rule.id if rule else RecurringRule(name=name, amount=amount, account_id=account.id).id,
                name=name,
                amount=amount,
                currency=account.currency,
                account_id=account.id,
                category=(category_tf.value or name).strip() or name,
                comment=comment_tf.value or "",
                type=TransactionType(type_dd.value or TransactionType.EXPENSE.value),
                interval=RecurringInterval(interval_dd.value or RecurringInterval.MONTHLY.value),
                interval_count=count,
                next_run=start_d,
                paused=rule.paused if rule else False,
                skip_next=rule.skip_next if rule else False,
                auto_create=bool(auto_sw.value),
                last_created_at=rule.last_created_at if rule else None,
                created_at=rule.created_at if rule else datetime.now(timezone.utc),
            )
            try:
                if rule:
                    await self._state.container.update_recurring_rule.execute(entity)
                else:
                    await self._state.container.create_recurring_rule.execute(entity)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            snack(self._page, tr("action.saved", lang))
            await self.reload()

        close_holder: dict = {}
        close = open_fullscreen_form(
            self._page,
            title=tr("action.edit", lang) if rule else tr("action.add", lang),
            lang=lang,
            overlay_key="recurring_editor",
            body=[
                name_tf,
                type_dd,
                amount_tf,
                account_picker,
                category_tf,
                comment_tf,
                interval_dd,
                count_tf,
                next_field,
                preview_text,
                labeled_switch(tr("recurring.auto_create", lang), auto_sw),
            ],
            on_save=_save,
        )
        close_holder["close"] = close
