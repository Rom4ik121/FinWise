"""Compact action strip under goal list cards (replaces broken swipe stack)."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.components.layout.actions import (
    card_action_button,
    card_with_actions,
)
from lib.presentation.utils import tr


def swipe_goal_card(
    card: ft.Control,
    *,
    language: str,
    on_contribute: Optional[Callable[[], None]] = None,
    on_edit: Optional[Callable[[], None]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Card with a small action row beneath — reliable on desktop and mobile."""
    actions: list[ft.Control] = []
    if on_contribute is not None:
        actions.append(
            card_action_button(
                tr("goal.contribute", language),
                icon=ft.Icons.ADD,
                on_click=on_contribute,
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
