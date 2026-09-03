"""Compact action strip under budget cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.utils import tr


def swipe_budget_card(
    card: ft.Control,
    *,
    language: str,
    on_edit: Optional[Callable[[], None]] = None,
    on_delete: Optional[Callable[[], None]] = None,
) -> ft.Control:
    if on_edit is None and on_delete is None:
        return card
    btn_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )
    actions: list[ft.Control] = []
    if on_edit is not None:
        actions.append(
            ft.OutlinedButton(
                tr("action.edit", language),
                icon=ft.Icons.EDIT_OUTLINED,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_edit(),
            )
        )
    if on_delete is not None:
        actions.append(
            ft.TextButton(
                tr("action.delete", language),
                icon=ft.Icons.DELETE_OUTLINE,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_delete(),
            )
        )
    return ft.Column(
        spacing=6,
        tight=True,
        controls=[card, ft.Row(spacing=8, controls=actions)],
    )
