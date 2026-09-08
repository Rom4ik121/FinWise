"""Compact action strip under subscription list cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.presentation.components.layout.actions import (
    card_action_button,
    card_with_actions,
)
from lib.presentation.utils import tr


def swipe_subscription_card(
    card: ft.Control,
    *,
    language: str,
    on_charge: Optional[Callable[[], None]] = None,
    on_pause: Optional[Callable[[], None]] = None,
    on_edit: Optional[Callable[[], None]] = None,
    pause_label: str | None = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Card with a small action row beneath."""
    actions: list[ft.Control] = []
    if on_charge is not None:
        actions.append(
            card_action_button(
                tr("subscription.charge_now", language),
                icon=ft.Icons.PAYMENTS_OUTLINED,
                on_click=on_charge,
                outlined=True,
                page=page,
            )
        )
    if on_pause is not None:
        actions.append(
            card_action_button(
                pause_label or tr("subscription.pause", language),
                icon=ft.Icons.PAUSE_CIRCLE_OUTLINE,
                on_click=on_pause,
                page=page,
            )
        )
    elif on_edit is not None:
        actions.append(
            card_action_button(
                tr("action.edit", language),
                icon=ft.Icons.EDIT_OUTLINED,
                on_click=on_edit,
                page=page,
            )
        )
    return card_with_actions(card, actions, page=page)
