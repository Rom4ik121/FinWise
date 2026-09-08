"""Shared action rows under catalog cards (edit / repay / charge)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Callable

import flet as ft

from lib.presentation.responsive import scale_size, scale_space


def card_action_button_style(page: ft.Page | None = None) -> ft.ButtonStyle:
    """Padding that stays tappable on phones without crowding tablets."""
    vpad = scale_size(8, page, minimum=6, maximum=12)
    hpad = scale_size(10, page, minimum=8, maximum=14)
    return ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=hpad, vertical=vpad),
    )


def card_action_button(
    label: str,
    *,
    icon: Any,
    on_click: Callable[[], None],
    outlined: bool = False,
    page: ft.Page | None = None,
) -> ft.Control:
    """Full-width outlined or text button for the strip under a card."""
    style = card_action_button_style(page)
    factory = ft.OutlinedButton if outlined else ft.TextButton
    return factory(
        label,
        icon=icon,
        expand=True,
        style=style,
        on_click=lambda _e: on_click(),
    )


def card_with_actions(
    card: ft.Control,
    actions: Sequence[ft.Control],
    *,
    page: ft.Page | None = None,
) -> ft.Control:
    """Stack a catalog card above an equal-width action row."""
    buttons = [item for item in actions if item is not None]
    if not buttons:
        return card
    return ft.Column(
        spacing=scale_space(6, page),
        tight=True,
        controls=[
            card,
            ft.Row(spacing=scale_space(8, page), controls=list(buttons)),
        ],
    )
