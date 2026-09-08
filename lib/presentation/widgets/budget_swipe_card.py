"""Compact action strip under budget cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.components.layout.actions import (
    card_action_button,
    card_with_actions,
)
from lib.presentation.utils import tr


def swipe_budget_card(
    card: ft.Control,
    *,
    language: str,
    on_edit: Optional[Callable[[], None]] = None,
    on_delete: Optional[Callable[[], None]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    actions: list[ft.Control] = []
    if on_edit is not None:
        actions.append(
            card_action_button(
                tr("action.edit", language),
                icon=ft.Icons.EDIT_OUTLINED,
                on_click=on_edit,
                outlined=True,
                page=page,
            )
        )
    if on_delete is not None:
        actions.append(
            card_action_button(
                tr("action.delete", language),
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=on_delete,
                page=page,
            )
        )
    return card_with_actions(card, actions, page=page)
