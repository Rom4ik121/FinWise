"""Compact action strip under debt list cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.components.layout.actions import (
    card_action_button,
    card_with_actions,
)
from lib.presentation.utils import tr


def swipe_debt_card(
    card: ft.Control,
    *,
    language: str,
    repay_label: str,
    on_repay: Optional[Callable[[], None]] = None,
    on_edit: Optional[Callable[[], None]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Card with a small action row beneath."""
    actions: list[ft.Control] = []
    if on_repay is not None:
        actions.append(
            card_action_button(
                repay_label,
                icon=ft.Icons.PAYMENTS_OUTLINED,
                on_click=on_repay,
                outlined=True,
                page=page,
            )
        )
    if on_edit is not None:
        actions.append(
            card_action_button(
                tr("action.edit", language),
                icon=ft.Icons.EDIT_OUTLINED,
                on_click=on_edit,
                page=page,
            )
        )
    return card_with_actions(card, actions, page=page)
