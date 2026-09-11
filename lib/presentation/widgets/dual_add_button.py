"""Full-width dual action control: expense / income."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.skins import get_active_skin
from lib.presentation.ui_motion import bind_press
from lib.presentation.utils import tr


def dual_add_button(
    lang: str,
    *,
    on_expense: Optional[Callable[[], None]] = None,
    on_income: Optional[Callable[[], None]] = None,
    dark: bool = True,
    page: ft.Page | None = None,
) -> ft.Container:
    """One long button: left = expense, right = income."""
    from lib.presentation.responsive import MIN_TAP, scale_font, scale_size

    skin = get_active_skin()
    pad_h = scale_size(14, page, minimum=10, maximum=18)
    pad_v = scale_size(14, page, minimum=10, maximum=18)
    icon_sz = scale_size(18, page, minimum=16, maximum=22)
    label_sz = scale_font(13, page, minimum=11, maximum=16)

    def _side(
        *,
        label: str,
        icon: ft.IconData,
        bgcolor: str,
        color: str,
        on_click: Optional[Callable[[], None]],
    ) -> ft.Container:
        side = ft.Container(
            expand=True,
            bgcolor=bgcolor,
            ink=True,
            ink_color=ft.Colors.TRANSPARENT,
            padding=ft.Padding.symmetric(horizontal=pad_h, vertical=pad_v),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
                tight=True,
                controls=[
                    ft.Icon(icon, size=icon_sz, color=color),
                    ft.Text(
                        label,
                        size=label_sz,
                        weight=ft.FontWeight.W_700,
                        color=color,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
            ),
        )
        bind_press(
            side,
            haptic_kind="light",
            on_click=(lambda _e: on_click() if on_click else None),
            page=page,
        )
        return side

    return ft.Container(
        height=max(MIN_TAP + 8, 52),
        border_radius=16,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        shadow=ft.BoxShadow(
            blur_radius=14,
            color="#00000033",
            offset=ft.Offset(0, 4),
        ),
        content=ft.Row(
            spacing=0,
            expand=True,
            controls=[
                _side(
                    label=tr("transaction.expense", lang),
                    icon=ft.Icons.REMOVE_ROUNDED,
                    bgcolor=skin.action_expense_bg(dark=dark),
                    color=skin.action_expense_fg(dark=dark),
                    on_click=on_expense,
                ),
                _side(
                    label=tr("transaction.income", lang),
                    icon=ft.Icons.ADD_ROUNDED,
                    bgcolor=skin.action_income_bg(dark=dark),
                    color=skin.action_income_fg(dark=dark),
                    on_click=on_income,
                ),
            ],
        ),
    )
