"""Empty-state placeholder for lists."""

from __future__ import annotations

from typing import Optional

import flet as ft


from lib.presentation.skins import get_active_skin
from lib.presentation.ui_motion import apply_enter_motion, play_enter_motion


class EmptyState(ft.Container):
    """Centered icon + message (+ optional action) when a list is empty."""

    def __init__(
        self,
        message: str,
        *,
        icon: ft.IconData = ft.Icons.INBOX_OUTLINED,
        hint: Optional[str] = None,
        action_label: Optional[str] = None,
        on_action: Optional[ft.ControlEventHandler] = None,
        page: ft.Page | None = None,
    ) -> None:
        from lib.presentation.haptics import haptic
        from lib.presentation.responsive import scale_font, scale_size

        skin = get_active_skin()
        badge = scale_size(56, page, minimum=48, maximum=72)
        action = on_action

        def _act(e: ft.ControlEvent) -> None:
            haptic("light")
            if action is not None:
                action(e)

        controls: list[ft.Control] = [
            ft.Container(
                width=badge,
                height=badge,
                border_radius=18,
                bgcolor=skin.badge_bg(dark=True),
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    icon,
                    size=scale_size(28, page, minimum=22, maximum=36),
                    color=skin.badge_fg(dark=True),
                ),
            ),
            ft.Text(
                message,
                text_align=ft.TextAlign.CENTER,
                size=scale_font(14, page, minimum=12, maximum=18),
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE,
            ),
        ]
        if hint:
            controls.append(
                ft.Text(
                    hint,
                    text_align=ft.TextAlign.CENTER,
                    size=scale_font(12, page, minimum=11, maximum=15),
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
        if action_label and on_action:
            controls.append(
                ft.FilledButton(
                    action_label,
                    icon=ft.Icons.ADD,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                    ),
                    on_click=_act,
                )
            )
        super().__init__(
            padding=20,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
                tight=True,
                controls=controls,
            ),
        )
        apply_enter_motion(self, page)

    def did_mount(self) -> None:
        super().did_mount()
        play_enter_motion(self)
