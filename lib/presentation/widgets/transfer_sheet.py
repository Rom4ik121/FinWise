"""Fullscreen form for transferring money between accounts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.presentation.money_input import (
    attach_grouped_digits,
    make_amount_field,
    parse_amount,
    parse_optional_amount,
)
from lib.presentation.styles import form_section
from lib.presentation.utils import (
    format_money,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
)
from lib.presentation.widgets.account_strip_picker import AccountStripPicker
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def open_transfer(
    page: ft.Page,
    state: "AppState",
    *,
    accounts: Sequence[Account] | None = None,
    default_from_id: str | None = None,
    default_to_id: str | None = None,
    include_corporate: bool = True,
    on_saved: Optional[Callable[[], None]] = None,
) -> None:
    """Open a fullscreen form to move money from one account to another.

    When ``include_corporate`` is True (default), personal and corporate
    accounts appear so money can move either way and show up in corporate
    analytics. Pass ``default_from_id`` to pre-select the source (e.g. from
    a corporate account card).
    """

    async def _open() -> None:
        lang = state.language
        if state.container.transfer_between_accounts is None:
            snack(page, tr("error.generic", lang), error=True)
            return
        loaded: list[Account]
        try:
            corp_filter: bool | None = None if include_corporate else False
            loaded = list(
                await state.container.list_accounts.execute(
                    active_only=True, corporate=corp_filter
                )
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(page, exc, lang=lang)
            return
        if not loaded and accounts:
            loaded = list(accounts)
        if len(loaded) < 2:
            snack(page, tr("transfer.need_two_accounts", lang), error=True)
            return
        await _show_form(
            page,
            state,
            accounts=loaded,
            default_from_id=default_from_id,
            default_to_id=default_to_id,
            on_saved=on_saved,
        )

    run_async(page, _open)


async def _show_form(
    page: ft.Page,
    state: "AppState",
    *,
    accounts: Sequence[Account],
    default_from_id: str | None,
    default_to_id: str | None,
    on_saved: Optional[Callable[[], None]],
) -> None:
    lang = state.language
    book = await load_rate_book(state.container)
    ids = {a.id for a in accounts}
    from_id = default_from_id if default_from_id in ids else accounts[0].id
    # Prefer a different account as destination (not the same as source).
    if default_to_id in ids and default_to_id != from_id:
        to_id = default_to_id
    else:
        to_id = next((a.id for a in accounts if a.id != from_id), accounts[0].id)

    from_picker = AccountStripPicker(
        page,
        accounts,
        lang=lang,
        label=tr("transfer.from", lang),
        value=from_id,
    )
    to_picker = AccountStripPicker(
        page,
        accounts,
        lang=lang,
        label=tr("transfer.to", lang),
        value=to_id,
    )
    amount_tf = make_amount_field(
        lang,
        label=tr("field.amount", lang),
        expand=True,
        autofocus=True,
    )
    fee_tf = make_amount_field(
        lang,
        label=tr("field.fee", lang),
        expand=True,
    )
    fee_picker = AccountStripPicker(
        page,
        accounts,
        lang=lang,
        label=tr("transfer.fee_account", lang),
        value=from_id,
    )
    convert_hint = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    comment_tf = ft.TextField(label=tr("field.comment", lang), expand=True)
    from lib.presentation.form_keyboard import configure_field, wire_field_chain

    configure_field(comment_tf, "text")
    wire_field_chain(page, [amount_tf, fee_tf, comment_tf])

    def _account(account_id: str | None) -> Account:
        return next((a for a in accounts if a.id == account_id), accounts[0])

    def _sync_fee_account_options() -> None:
        """Offer from/to first, then the rest of active accounts."""
        source = _account(from_picker.value)
        dest = _account(to_picker.value)
        ordered: list[Account] = []
        seen: set[str] = set()
        for account in (source, dest, *accounts):
            if account.id in seen:
                continue
            seen.add(account.id)
            ordered.append(account)
        current_fee = fee_picker.value if fee_picker.value in seen else source.id
        fee_picker.set_accounts(ordered, value=current_fee, notify=False)
        fee_acc = _account(fee_picker.value)
        fee_tf.label = f"{tr('field.fee', lang)} ({fee_acc.currency})"
        try:
            safe_update(fee_tf)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_hint(_e: ft.ControlEvent | None = None) -> None:
        source = _account(from_picker.value)
        dest = _account(to_picker.value)
        fee_acc = _account(fee_picker.value)
        try:
            amount = parse_amount(amount_tf.value)
            fee = parse_optional_amount(fee_tf.value)
        except (InvalidOperation, ValueError):
            convert_hint.value = ""
            safe_update(convert_hint)
            return
        if amount <= 0 or fee < 0:
            convert_hint.value = ""
            safe_update(convert_hint)
            return
        if source.id == dest.id:
            convert_hint.value = tr("transfer.same_account", lang)
            convert_hint.color = ft.Colors.ERROR
            safe_update(convert_hint)
            return
        credit = amount
        if source.currency.upper() != dest.currency.upper():
            converted = book.convert(amount, source.currency, dest.currency)
            if converted is None:
                convert_hint.value = tr("transfer.no_rate", lang)
                convert_hint.color = ft.Colors.ERROR
                safe_update(convert_hint)
                return
            credit = converted
        lines = [
            tr(
                "transfer.will_credit",
                lang,
                amount=format_money(credit, dest.currency),
                account=dest.name,
            ),
            tr(
                "transfer.will_debit",
                lang,
                total=format_money(amount, source.currency),
            ),
        ]
        if fee > 0:
            lines.append(
                tr(
                    "transfer.will_fee",
                    lang,
                    amount=format_money(fee, fee_acc.currency),
                    account=fee_acc.name,
                )
            )
        convert_hint.value = "\n".join(lines)
        convert_hint.color = ft.Colors.ON_SURFACE_VARIANT
        safe_update(convert_hint)

    def _on_accounts_changed(_aid: str | None = None) -> None:
        source = _account(from_picker.value)
        amount_tf.label = f"{tr('field.amount', lang)} ({source.currency})"
        try:
            safe_update(amount_tf)
        except Exception:  # noqa: BLE001
            pass
        _sync_fee_account_options()
        _refresh_hint()

    def _on_fee_account_changed(_aid: str | None = None) -> None:
        fee_acc = _account(fee_picker.value)
        fee_tf.label = f"{tr('field.fee', lang)} ({fee_acc.currency})"
        try:
            safe_update(fee_tf)
        except Exception:  # noqa: BLE001
            pass
        _refresh_hint()

    attach_grouped_digits(amount_tf, lang, extra_on_change=_refresh_hint)
    attach_grouped_digits(fee_tf, lang, extra_on_change=_refresh_hint)
    from_picker.bind_changed(_on_accounts_changed)
    to_picker.bind_changed(_on_accounts_changed)
    fee_picker.bind_changed(_on_fee_account_changed)
    _sync_fee_account_options()
    _on_accounts_changed()

    async def _save() -> None:
        try:
            amount = parse_amount(amount_tf.value)
            fee = parse_optional_amount(fee_tf.value)
            if amount <= 0 or fee < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            snack(page, tr("invalid_amount", lang), error=True)
            return
        source = _account(from_picker.value)
        dest = _account(to_picker.value)
        fee_acc = _account(fee_picker.value)
        if source.id == dest.id:
            snack(page, tr("transfer.same_account", lang), error=True)
            return
        try:
            await state.container.transfer_between_accounts.execute(
                from_account_id=source.id,
                to_account_id=dest.id,
                amount=amount,
                comment=comment_tf.value or "",
                fee=fee,
                fee_account_id=fee_acc.id if fee > 0 else None,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(page, exc, lang=lang)
            return
        close()
        state.bump_refresh("dashboard", "transactions", "accounts", "budgets")
        snack(page, tr("action.saved", lang))
        if on_saved:
            on_saved()

    close = open_fullscreen_form(
        page,
        title=tr("transfers.title_short", lang),
        lang=lang,
        overlay_key="transfer_editor",
        wrap_body=False,
        body=[
            form_section(
                tr("form.section.route", lang),
                [from_picker, to_picker],
                icon=ft.Icons.SWAP_HORIZ,
            ),
            form_section(
                tr("form.section.amount", lang),
                [amount_tf, convert_hint],
                icon=ft.Icons.PAYMENTS,
            ),
            form_section(
                tr("form.section.fee", lang),
                [fee_tf, fee_picker],
                icon=ft.Icons.RECEIPT_LONG,
            ),
            form_section(
                tr("form.section.details", lang),
                [comment_tf],
                icon=ft.Icons.NOTES,
            ),
        ],
        on_save=_save,
    )
