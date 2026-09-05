"""Account card with multi-currency balance display and swipe actions."""

from __future__ import annotations

from decimal import Decimal
from math import pi
from typing import Callable, Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.presentation.account_icons import (
    account_icon_badge,
    resolve_account_icon_key,
)
from lib.presentation.count_up import mark_money_text
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, muted_text
from lib.presentation.utils import format_money

_SLIDE_DURATION = 200
_currently_open: Optional["AccountCard"] = None


class AccountCard(ft.Container):
    """Card showing account name, balance, and swipe Edit / Delete actions."""

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

        self._revealed = False
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
            visible=on_include_in_total is not None,
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
        corporate_badge = ft.Container(
            visible=bool(getattr(account, "is_corporate", False)),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY),
            content=ft.Text(
                tr("account.corporate_badge", language),
                size=11,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
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

        self._arrow_container = ft.Container(
            width=28,
            alignment=ft.Alignment.CENTER,
            ink=True,
            border_radius=8,
            on_click=lambda _e: self._toggle(),
            rotate=ft.Rotate(0),
            animate_rotation=ft.Animation(_SLIDE_DURATION, ft.AnimationCurve.EASE_OUT),
            content=ft.Icon(
                ft.Icons.CHEVRON_LEFT_ROUNDED,
                color=ft.Colors.ON_SURFACE_VARIANT,
                size=20,
            ),
        )

        body = ft.Column(
            spacing=12,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[header, self._arrow_container],
                ),
                ft.Column(
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
                corporate_badge,
                include_row,
            ],
        )

        styled = card_surface(body, accent=accent)
        # Glass fill is translucent — swipe layers must be opaque or the
        # card "shows through" onto the action buttons.
        _opaque = ft.Colors.SURFACE_CONTAINER
        _action_width = 112

        def _action_tile(
            *,
            icon: str,
            label: str,
            fg: str,
            bg: str,
            on_click,
        ) -> ft.Control:
            return ft.Container(
                width=_action_width,
                expand=True,
                bgcolor=bg,
                border_radius=12,
                ink=True,
                on_click=on_click,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    spacing=4,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(icon, color=fg, size=22),
                        ft.Text(
                            label,
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=fg,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=1,
                        ),
                    ],
                ),
            )

        self._front = ft.Container(
            padding=12,
            border_radius=14,
            bgcolor=_opaque,
            border=styled.border,
            offset=ft.Offset(0, 0),
            animate_offset=ft.Animation(_SLIDE_DURATION, ft.AnimationCurve.EASE_OUT),
            ink=True,
            on_click=lambda _e: self._on_front_click(account, on_click, on_edit),
            content=body,
        )

        def _edit_click(_e: ft.ControlEvent) -> None:
            self._close()
            if on_edit:
                on_edit(account)

        def _delete_click(_e: ft.ControlEvent) -> None:
            self._close()
            if on_delete:
                on_delete(account)

        def _sync_click(_e: ft.ControlEvent) -> None:
            self._close()
            if on_sync:
                on_sync(account)

        back_actions: list[ft.Control] = []
        if on_sync is not None:
            back_actions.append(
                _action_tile(
                    icon=ft.Icons.SYNC,
                    label=tr("account.sync.now", language),
                    fg=ft.Colors.ON_SECONDARY_CONTAINER,
                    bg=ft.Colors.SECONDARY_CONTAINER,
                    on_click=_sync_click,
                )
            )
        if on_edit is not None:
            back_actions.append(
                _action_tile(
                    icon=ft.Icons.EDIT_OUTLINED,
                    label=tr("action.edit", language),
                    fg=ft.Colors.ON_PRIMARY,
                    bg=ft.Colors.PRIMARY,
                    on_click=_edit_click,
                )
            )
        if on_delete is not None:
            back_actions.append(
                _action_tile(
                    icon=ft.Icons.DELETE_OUTLINE,
                    label=tr("action.delete", language),
                    fg="#FFFFFF",
                    bg=ft.Colors.ERROR,
                    on_click=_delete_click,
                )
            )

        back = ft.Container(
            left=0,
            right=0,
            top=0,
            bottom=0,
            border_radius=14,
            bgcolor=_opaque,
            padding=ft.Padding.only(right=8, top=8, bottom=8),
            alignment=ft.Alignment.CENTER_RIGHT,
            content=ft.Container(
                width=_action_width,
                expand=True,
                content=ft.Column(
                    expand=True,
                    spacing=8,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=back_actions,
                ),
            ),
        )

        super().__init__(
            border_radius=14,
            bgcolor=_opaque,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            margin=ft.Margin.only(bottom=8),
            alignment=ft.Alignment.CENTER_LEFT,
            content=ft.Stack(controls=[back, self._front]),
        )

    def _on_front_click(
        self,
        account: Account,
        on_click: Optional[Callable[[Account], None]],
        on_edit: Optional[Callable[[Account], None]],
    ) -> None:
        if self._revealed:
            self._close()
            return
        if on_click:
            on_click(account)
        elif on_edit:
            on_edit(account)

    def _toggle(self) -> None:
        if self._revealed:
            self._close()
        else:
            self._open()

    def _open(self) -> None:
        global _currently_open
        if _currently_open is not None and _currently_open is not self:
            _currently_open._close()
        _currently_open = self
        self._revealed = True
        self._front.offset = ft.Offset(-0.38, 0)
        self._arrow_container.rotate = ft.Rotate(pi)
        self._front.update()
        self._arrow_container.update()

    def _close(self) -> None:
        global _currently_open
        if _currently_open is self:
            _currently_open = None
        self._revealed = False
        self._front.offset = ft.Offset(0, 0)
        self._arrow_container.rotate = ft.Rotate(0)
        self._front.update()
        self._arrow_container.update()
