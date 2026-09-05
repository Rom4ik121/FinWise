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
from lib.presentation.styles import form_section
from lib.presentation.utils import bind_dropdown_select, run_async, safe_update, snack, snack_exception, tr
from lib.presentation.widgets.attachment_picker import AttachmentPicker
from lib.presentation.widgets.category_picker import CategoryPicker
from lib.presentation.widgets.date_time_field import DateTimeField
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
    locked_account: Account | None = None,
    on_saved: Optional[Callable[[], None]] = None,
) -> None:
    """Open a fullscreen form for quickly adding income or expense.

    When ``locked_account`` is set (e.g. corporate workspace), only that
    account is used and the account picker is hidden.
    """

    async def _open() -> None:
        lang = state.language
        loaded: list[Account]
        try:
            if locked_account is not None:
                loaded = [locked_account]
            else:
                loaded = list(
                    await state.container.list_accounts.execute(
                        active_only=True, corporate=False
                    )
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
            locked_account=locked_account,
            on_saved=on_saved,
        )

    run_async(page, _open)


async def _show_form(
    page: ft.Page,
    state: "AppState",
    *,
    accounts: Sequence[Account],
    default_type: TransactionType,
    locked_account: Account | None,
    on_saved: Optional[Callable[[], None]],
) -> None:
    lang = state.language
    if locked_account is not None:
        accounts = [locked_account]
        default_account_id = locked_account.id
    else:
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
        visible=locked_account is None,
        disabled=locked_account is not None,
    )
    locked_account_label = (
        ft.Text(
            tr(
                "account.locked_for_tx",
                lang,
                name=locked_account.name,
            ),
            size=13,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        )
        if locked_account is not None
        else None
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
        safe_update(fee_tf)

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
    attachments = AttachmentPicker(page, lang=lang)
    # Corporate (locked) workspace: pick any past/future date via inline calendar.
    allow_custom_date = locked_account is not None and bool(
        getattr(locked_account, "is_corporate", False)
    )
    date_field: DateTimeField | None = None
    if allow_custom_date:
        date_field = DateTimeField(
            page,
            lang=lang,
            label=tr("field.date", lang),
            value=datetime.now(timezone.utc),
            with_time=True,
        )
    from lib.presentation.form_keyboard import configure_field, wire_field_chain

    configure_field(comment_tf, "text")
    configure_field(tags_tf, "text")
    wire_field_chain(page, [amount_tf, fee_tf, comment_tf, tags_tf])

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

        occurred = datetime.now(timezone.utc)
        if date_field is not None:
            picked = date_field.value
            if picked is None:
                snack(page, tr("invalid_date", lang), error=True)
                return
            occurred = picked

        tx_id = attachments.transaction_id
        paths = attachments.collected_paths()
        tx = Transaction(
            id=tx_id,
            account_id=account.id,
            amount=amount,
            category=category_name,
            tags=tags,
            date=occurred,
            comment=comment_tf.value or "",
            type=tx_type,
            currency=account.currency,
            items=items,
            attachments=paths,
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
                [type_dd, amount_tf, items_editor, fee_tf],
                icon=ft.Icons.CREDIT_CARD,
            ),
            form_section(
                tr("form.section.category", lang),
                [
                    *(
                        [locked_account_label]
                        if locked_account_label is not None
                        else []
                    ),
                    account_dd,
                    category_picker,
                ],
                icon=ft.Icons.CATEGORY,
            ),
            form_section(
                tr("form.section.details", lang),
                [
                    *([date_field] if date_field is not None else []),
                    comment_tf,
                    tags_tf,
                    attachments,
                ],
                icon=ft.Icons.NOTES,
            ),
        ],
        on_save=_save,
    )
