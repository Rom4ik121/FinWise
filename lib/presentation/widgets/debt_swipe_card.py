"""Compact action strip under debt list cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.utils import tr


def swipe_debt_card(
    card: ft.Control,
    *,
    language: str,
    repay_label: str,
    on_repay: Optional[Callable[[], None]] = None,
    on_edit: Optional[Callable[[], None]] = None,
) -> ft.Control:
    """Card with a small action row beneath."""
    if on_repay is None and on_edit is None:
        return card

    btn_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )
    actions: list[ft.Control] = []
    if on_repay is not None:
        actions.append(
            ft.OutlinedButton(
                repay_label,
                icon=ft.Icons.PAYMENTS_OUTLINED,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_repay(),
            )
        )
    if on_edit is not None:
        actions.append(
            ft.TextButton(
                tr("action.edit", language),
                icon=ft.Icons.EDIT_OUTLINED,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_edit(),
            )
        )

    return ft.Column(
        spacing=6,
        tight=True,
        controls=[
            card,
            ft.Row(spacing=8, controls=actions),
        ],
    )
