"""Account card with multi-currency balance display."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.presentation.account_icons import (
    account_icon_badge,
    resolve_account_icon_key,
)
from lib.presentation.count_up import mark_money_text
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, muted_text, style_popup_menu
from lib.presentation.utils import format_money


class AccountCard(ft.Container):
    """Card showing account name, native balance, and optional base conversion."""

    def __init__(
        self,
        account: Account,
        *,
        base_currency: str = "RUB",
        base_balance: Optional[Decimal] = None,
        language: str = "ru",
        exchange_title: str = "",
        exchange_id: str = "",
        on_click: Optional[Callable[[Account], None]] = None,
        on_edit: Optional[Callable[[Account], None]] = None,
        on_delete: Optional[Callable[[Account], None]] = None,
        on_sync: Optional[Callable[[Account], None]] = None,
        on_include_in_total: Optional[Callable[[Account, bool], None]] = None,
    ) -> None:
        from lib.presentation.utils import tr

        native = format_money(account.balance, account.currency)
        accent = account.color or get_active_skin().primary_hex(dark=True)
        converted_line: list[ft.Control] = []
        if (
            base_balance is not None
            and account.currency.upper() != base_currency.upper()
        ):
            converted_line.append(
                mark_money_text(
                    muted_text(f"≈ {format_money(base_balance, base_currency)}"),
                    base_balance,
                    currency=base_currency,
                )
            )

        menu_items: list[ft.PopupMenuItem] = []
        if on_sync is not None:
            menu_items.append(
                ft.PopupMenuItem(
                    content=ft.Text(tr("account.sync.now", language)),
                    icon=ft.Icons.SYNC,
                    on_click=lambda _e: on_sync(account),
                )
            )
        menu_items.extend(
            [
                ft.PopupMenuItem(
                    content=ft.Text(tr("action.edit", language)),
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=lambda _e: on_edit(account) if on_edit else None,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(tr("action.delete", language)),
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda _e: on_delete(account) if on_delete else None,
                ),
            ]
        )
        menu = style_popup_menu(
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                icon_color=ft.Colors.ON_SURFACE_VARIANT,
                items=menu_items,
            )
        )

        subtitle = (
            f"{exchange_title} · {account.currency}"
            if exchange_title
            else account.currency
        )
        icon_key = resolve_account_icon_key(account.icon, exchange_id)

        include_sw = ft.Switch(
            value=bool(getattr(account, "include_in_total", True)),
            scale=0.85,
            on_change=(
                (
                    lambda e, acc=account: on_include_in_total(
                        acc, bool(getattr(e.control, "value", True))
                    )
                )
                if on_include_in_total is not None
                else None
            ),
        )
        include_row = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    tr("account.include_in_total", language),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    max_lines=2,
                ),
                include_sw,
            ],
        )

        header = ft.Row(
            spacing=12,
            expand=True,
            controls=[
                account_icon_badge(
                    icon_key,
                    color=accent,
                    size=46,
                    glyph_size=24,
                    glyph_color=ft.Colors.WHITE,
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            account.name,
                            weight=ft.FontWeight.W_700,
                            size=16,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        muted_text(subtitle),
                    ],
                ),
            ],
        )
        open_handler = (
            (lambda _e: on_click(account))
            if on_click
            else ((lambda _e: on_edit(account)) if on_edit else None)
        )
        header_tap = ft.Container(
            expand=True,
            ink=True,
            on_click=open_handler,
            content=header,
        )

        body = ft.Column(
            spacing=12,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[header_tap, menu],
                ),
                ft.Container(
                    ink=bool(open_handler),
                    on_click=open_handler,
                    content=ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            mark_money_text(
                                ft.Text(
                                    native,
                                    size=20,
                                    weight=ft.FontWeight.W_700,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                account.balance,
                                currency=account.currency,
                            ),
                            *converted_line,
                        ],
                    ),
                ),
                include_row,
            ],
        )
        card = card_surface(body, accent=accent)
        super().__init__(
            padding=12,
            border_radius=14,
            bgcolor=card.bgcolor,
            border=card.border,
            shadow=card.shadow,
            content=body,
            margin=ft.Margin.only(bottom=8),
        )
