"""Quick income / expense fullscreen form."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.use_cases.transactions import FEE_CATEGORY, make_fee_expense
from lib.presentation.dropdown_options import account_dropdown_options, icon_dropdown_option
from lib.presentation.frequent_account import (
    account_option_label,
    prepare_tx_account_choices,
)
from lib.presentation.money_input import (
    format_amount_value,
    make_amount_field,
    parse_amount,
    parse_optional_amount,
)
from lib.presentation.styles import form_hint, form_section
from lib.presentation.utils import bind_dropdown_select, run_async, safe_update, snack, snack_exception, tr
from lib.presentation.widgets.category_picker import CategoryPicker
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.widgets.line_items_editor import LineItemsEditor

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def open_quick_add(
    page: ft.Page,
    state: "AppState",
    *,
    accounts: Sequence[Account] | None = None,
    default_type: TransactionType = TransactionType.EXPENSE,
    on_saved: Optional[Callable[[], None]] = None,
) -> None:
    """Open a fullscreen form for quickly adding income or expense."""

    async def _open() -> None:
        lang = state.language
        loaded: list[Account]
        try:
            loaded = list(
                await state.container.list_accounts.execute(active_only=True)
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(page, exc, lang=lang)
            return
        if not loaded and accounts:
            loaded = list(accounts)
        if not loaded:
            snack(page, tr("empty.accounts", lang), error=True)
            return
        await _show_form(
            page,
            state,
            accounts=loaded,
            default_type=default_type,
            on_saved=on_saved,
        )

    run_async(page, _open)


async def _show_form(
    page: ft.Page,
    state: "AppState",
    *,
    accounts: Sequence[Account],
    default_type: TransactionType,
    on_saved: Optional[Callable[[], None]],
) -> None:
    lang = state.language
    accounts, default_account_id = await prepare_tx_account_choices(state, accounts)
    type_dd = ft.Dropdown(
        label=tr("field.type", lang),
        value=default_type.value,
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
        expand=True,
    )
    amount_tf = make_amount_field(
        lang,
        label=tr("field.amount", lang),
        expand=True,
        autofocus=True,
    )
    items_editor = LineItemsEditor(
        lang,
        on_changed=lambda: _sync_amount_visibility(),
    )

    def _sync_amount_visibility() -> None:
        amount_tf.visible = not items_editor.enabled
        safe_update(amount_tf)

    fee_tf = make_amount_field(
        lang,
        label=tr("field.fee", lang),
        expand=True,
    )
    fee_hint = form_hint(tr("field.fee_hint", lang), size=11)
    account_dd = ft.Dropdown(
        label=tr("field.account", lang),
        value=default_account_id,
        options=account_dropdown_options(
            accounts,
            label_fn=lambda a: account_option_label(
                a, frequent_id=default_account_id, lang=lang
            ),
        ),
        expand=True,
    )
    category_picker = CategoryPicker(
        page,
        state,
        tx_type=default_type.value,
    )
    await category_picker.reload()
    if category_picker.is_empty:
        category_picker.prompt_if_empty()

    def _sync_fee_visibility() -> None:
        show = (type_dd.value or TransactionType.EXPENSE.value) == TransactionType.EXPENSE.value
        fee_tf.visible = show
        fee_hint.visible = show
        safe_update(fee_tf)
        safe_update(fee_hint)

    def _on_type(_e: ft.ControlEvent) -> None:
        category_picker.set_tx_type(type_dd.value or TransactionType.EXPENSE.value)
        _sync_fee_visibility()

    bind_dropdown_select(type_dd, _on_type)
    _sync_fee_visibility()

    comment_tf = ft.TextField(label=tr("field.comment", lang), expand=True)
    tags_tf = ft.TextField(
        label=tr("field.tags", lang),
        hint_text=tr("tags.hint", lang),
        expand=True,
    )
    from lib.presentation.form_keyboard import configure_field, wire_field_chain

    configure_field(comment_tf, "text")
    configure_field(tags_tf, "text")
    wire_field_chain(page, [amount_tf, fee_tf, comment_tf, tags_tf])
    voice_status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

    async def _listen_voice() -> None:
        from lib.infrastructure.services.speech import get_speech_service, listen_speech
        from lib.infrastructure.services.voice_parse import parse_voice_expense

        if get_speech_service() is None:
            snack(page, tr("voice.unavailable", lang), error=True)
            return
        voice_status.value = tr("voice.listening", lang)
        safe_update(voice_status)
        spoken = await listen_speech(language=lang)
        if not spoken:
            voice_status.value = tr("voice.empty", lang)
            safe_update(voice_status)
            snack(page, tr("voice.empty", lang), error=True)
            return
        draft = parse_voice_expense(spoken)
        type_dd.value = draft.tx_type.value
        category_picker.set_tx_type(draft.tx_type.value)
        _sync_fee_visibility()
        if draft.amount is not None:
            amount_tf.value = format_amount_value(draft.amount, lang)
        if draft.category and draft.category != "Прочее":
            category_picker.select_name(draft.category)
        comment_tf.value = spoken
        voice_status.value = spoken
        safe_update(type_dd)
        safe_update(amount_tf)
        safe_update(comment_tf)
        safe_update(voice_status)
        if draft.amount and draft.amount > 0 and category_picker.selected_name:
            await _save()
            return
        snack(page, tr("voice.filled", lang))

    mic = ft.OutlinedButton(
        tr("voice.button", lang),
        icon=ft.Icons.MIC,
        on_click=lambda _e: run_async(page, _listen_voice),
    )
    from lib.infrastructure.services.biometric import feature_voice_available

    voice_body: list[ft.Control] = []
    if feature_voice_available():
        voice_body = [mic, voice_status]

    async def _save() -> None:
        account = next((a for a in accounts if a.id == account_dd.value), accounts[0])
        tags = [
            part.strip().lstrip("#")
            for part in (tags_tf.value or "").split(",")
            if part.strip()
        ]
        tx_type = TransactionType(type_dd.value or TransactionType.EXPENSE.value)
        category_name = category_picker.selected_name
        if not category_name:
            snack(page, tr("field.category", lang), error=True)
            return
        if (
            state.container.find_or_create_category is not None
            and not category_picker.has_category(category_name)
        ):
            await state.container.find_or_create_category.execute(
                category_name,
                kind=(
                    CategoryKind.INCOME
                    if tx_type == TransactionType.INCOME
                    else CategoryKind.EXPENSE
                ),
            )

        line_items = items_editor.collect(default_category=category_name)
        try:
            fee = parse_optional_amount(fee_tf.value)
            if fee < 0:
                raise InvalidOperation
            if line_items is None:
                amount = parse_amount(amount_tf.value)
                if amount <= 0:
                    raise InvalidOperation
                items = []
            else:
                if len(line_items) < 1:
                    raise InvalidOperation
                amount = sum((i.amount for i in line_items), Decimal("0"))
                items = line_items
        except (InvalidOperation, ValueError):
            snack(
                page,
                tr("invalid_amount", lang),
                error=True,
            )
            return

        tx = Transaction(
            account_id=account.id,
            amount=amount,
            category=category_name,
            tags=tags,
            date=datetime.now(timezone.utc),
            comment=comment_tf.value or "",
            type=tx_type,
            currency=account.currency,
            items=items,
        )
        try:
            saved = await state.container.add_transaction.execute(tx)
            if fee > 0 and tx_type == TransactionType.EXPENSE:
                try:
                    if state.container.find_or_create_category is not None:
                        await state.container.find_or_create_category.execute(
                            FEE_CATEGORY,
                            kind=CategoryKind.EXPENSE,
                            icon="receipt_long",
                        )
                    await state.container.add_transaction.execute(
                        make_fee_expense(
                            account_id=account.id,
                            currency=account.currency,
                            amount=fee,
                            date=saved.date,
                            comment=saved.comment or FEE_CATEGORY,
                        )
                    )
                except Exception:
                    await state.container.delete_transaction.execute(saved.id)
                    raise
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
        title=tr("action.quick_add", lang),
        lang=lang,
        overlay_key="quick_add_editor",
        wrap_body=False,
        body=[
            form_section(
                tr("form.section.type", lang),
                [type_dd, amount_tf, items_editor, fee_tf, fee_hint, *voice_body],
                icon=ft.Icons.CREDIT_CARD,
            ),
            form_section(
                tr("form.section.category", lang),
                [account_dd, category_picker],
                icon=ft.Icons.CATEGORY,
            ),
            form_section(
                tr("form.section.details", lang),
                [comment_tf, tags_tf],
                icon=ft.Icons.NOTES,
            ),
        ],
        on_save=_save,
    )
