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
from lib.presentation.utils import format_money, format_money_parts, safe_update
from lib.presentation.responsive import (
    MIN_TAP,
    fit_font,
    fit_size,
    grid_columns,
    swipe_action_strip_width,
    swipe_reveal_offset,
    tap_icon_button,
)

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
        page: ft.Page | None = None,
    ) -> None:
        from lib.presentation.utils import tr

        cols = grid_columns(page, min_card=280, maximum=3)
        self._revealed = False
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
            tooltip=tr("account.include_in_total", language),
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
        include_row = ft.Column(
            spacing=4,
            tight=True,
            visible=on_include_in_total is not None,
            controls=[
                ft.Text(
                    tr("account.include_in_total", language),
                    size=fit_font(12, page, columns=cols, minimum=10, maximum=14),
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
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
                size=fit_font(11, page, columns=cols, minimum=9, maximum=13),
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
        )

        self._arrow_container = ft.Container(
            width=MIN_TAP,
            height=MIN_TAP,
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

        quick_actions: list[ft.Control] = []
        if on_edit is not None:
            quick_actions.append(
                tap_icon_button(
                    icon=ft.Icons.EDIT_OUTLINED,
                    tooltip=tr("action.edit", language),
                    on_click=lambda _e, acc=account: on_edit(acc),
                )
            )
        if on_delete is not None:
            quick_actions.append(
                tap_icon_button(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.ERROR,
                    tooltip=tr("action.delete", language),
                    on_click=lambda _e, acc=account: on_delete(acc),
                )
            )

        header = ft.Row(
            spacing=8,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                account_icon_badge(
                    icon_key,
                    color=accent,
                    size=fit_size(46, page, columns=cols, minimum=36, maximum=56),
                    glyph_size=fit_size(24, page, columns=cols, minimum=18, maximum=28),
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
                            size=fit_font(16, page, columns=cols, minimum=12, maximum=20),
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        muted_text(subtitle, page=page),
                    ],
                ),
                self._arrow_container,
            ],
        )
        actions_row = ft.Row(
            spacing=4,
            wrap=True,
            visible=bool(quick_actions),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=quick_actions,
        )

        figure, code = format_money_parts(account.balance, account.currency)
        # Prefer full figure when it fits; parts already compact for huge values.
        full_native = format_money(account.balance, account.currency)
        full_figure = full_native.rsplit(" ", 1)[0] if " " in full_native else full_native
        balance_figure = full_figure if len(full_figure) <= 14 else figure
        balance_row = ft.Row(
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=False,
            controls=[
                mark_money_text(
                    ft.Text(
                        balance_figure,
                        size=fit_font(20, page, columns=cols, minimum=14, maximum=26),
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=True,
                    ),
                    account.balance,
                    currency=account.currency,
                ),
                muted_text(code, size=fit_font(12, page, columns=cols, minimum=10, maximum=14)),
            ],
        )

        # Keep Edit/Delete/switch outside the open-detail hit target. A parent
        # ``on_click`` (and bind_press) swallows child IconButton taps on web.
        detail = ft.Container(
            ink=True,
            content=ft.Column(
                spacing=12,
                tight=True,
                controls=[
                    header,
                    ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            balance_row,
                            *converted_line,
                        ],
                    ),
                    corporate_badge,
                ],
            ),
        )
        from lib.presentation.ui_motion import bind_press

        bind_press(
            detail,
            haptic_kind="light",
            on_click=lambda _e: self._on_front_click(account, on_click, on_edit),
            page=page,
        )
        body = ft.Column(
            spacing=12,
            tight=True,
            controls=[
                detail,
                include_row,
                actions_row,
            ],
        )

        styled = card_surface(body, accent=accent)
        # Glass fill is translucent — swipe layers must be opaque or the
        # card "shows through" onto the action buttons.
        _opaque = ft.Colors.SURFACE_CONTAINER
        action_count = sum(
            1 for h in (on_sync, on_edit, on_delete) if h is not None
        )
        strip_w = swipe_action_strip_width(page, buttons=max(action_count, 1))
        # Horizontal reveal strip — vertical stacks clipped on phone-width cards.
        _action_width = max(64.0, min(88.0, strip_w / max(action_count, 1)))
        self._reveal_frac = swipe_reveal_offset(
            page,
            strip_width=_action_width * max(action_count, 1) + 16,
            buttons=max(action_count, 1),
        )

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
                height=72,
                bgcolor=bg,
                border_radius=12,
                ink=True,
                on_click=on_click,
                alignment=ft.Alignment.CENTER,
                tooltip=label,
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(icon, color=fg, size=22),
                        ft.Text(
                            label,
                            size=10,
                            weight=ft.FontWeight.W_700,
                            color=fg,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
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
            content=ft.Row(
                spacing=8,
                tight=True,
                alignment=ft.MainAxisAlignment.END,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=back_actions,
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
        try:
            from lib.presentation.haptics import haptic

            haptic("selection")
        except Exception:  # noqa: BLE001
            pass
        frac = swipe_reveal_offset(
            getattr(self, "page", None),
            strip_width=100,
            buttons=1,
        )
        stored = getattr(self, "_reveal_frac", None)
        if isinstance(stored, (int, float)) and stored > 0:
            frac = max(frac, float(stored))
        self._front.offset = ft.Offset(-frac, 0)
        self._arrow_container.rotate = ft.Rotate(pi)
        safe_update(self._front)
        safe_update(self._arrow_container)

    def _close(self) -> None:
        global _currently_open
        if _currently_open is self:
            _currently_open = None
        self._revealed = False
        self._front.offset = ft.Offset(0, 0)
        self._arrow_container.rotate = ft.Rotate(0)
        safe_update(self._front)
        safe_update(self._arrow_container)
