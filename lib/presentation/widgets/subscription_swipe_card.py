"""Compact action strip under subscription list cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.utils import tr


def swipe_subscription_card(
    card: ft.Control,
    *,
    language: str,
    on_charge: Optional[Callable[[], None]] = None,
    on_pause: Optional[Callable[[], None]] = None,
    on_edit: Optional[Callable[[], None]] = None,
    pause_label: str | None = None,
) -> ft.Control:
    """Card with a small action row beneath."""
    if on_charge is None and on_pause is None and on_edit is None:
        return card

    btn_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )
    actions: list[ft.Control] = []
    if on_charge is not None:
        actions.append(
            ft.OutlinedButton(
                tr("subscription.charge_now", language),
                icon=ft.Icons.PAYMENTS_OUTLINED,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_charge(),
            )
        )
    if on_pause is not None:
        actions.append(
            ft.TextButton(
                pause_label or tr("subscription.pause", language),
                icon=ft.Icons.PAUSE_CIRCLE_OUTLINE,
                expand=True,
                style=btn_style,
                on_click=lambda _e: on_pause(),
            )
        )
    elif on_edit is not None:
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
