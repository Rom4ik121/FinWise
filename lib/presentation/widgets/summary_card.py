"""Balance / income / expense summary cards."""

from __future__ import annotations

from typing import Optional

import flet as ft

from lib.presentation.skins import get_active_skin


class SummaryCard(ft.Container):
    """Compact KPI card that stretches to available width."""

    def __init__(
        self,
        *,
        title: str,
        value: str,
        icon: ft.IconData = ft.Icons.ACCOUNT_BALANCE_WALLET,
        accent: Optional[str] = None,
        expand: bool = True,
        hero: bool = False,
        width: Optional[int] = None,
        on_click: Optional[ft.ControlEventHandler] = None,
        dark: bool = True,
    ) -> None:
        skin = get_active_skin()
        color = accent or skin.text_hex(dark=dark)
        badge_bg = skin.badge_bg(dark=dark)
        badge_fg = skin.badge_fg(dark=dark)
        body = ft.Column(
            spacing=8,
            tight=False,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            expand=True,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            width=30,
                            height=30,
                            border_radius=9,
                            bgcolor=badge_bg,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                icon,
                                size=16,
                                color=badge_fg,
                            ),
                        ),
                        ft.Text(
                            title,
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_500,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=2,
                            expand=True,
                        ),
                    ],
                ),
                ft.Text(
                    value,
                    size=15 if hero else 13,
                    weight=ft.FontWeight.W_700,
                    color=color,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=2,
                ),
            ],
        )
        kwargs: dict = {
            "expand": expand,
            "width": width,
            "padding": 14 if hero else 12,
            "border_radius": skin.hero_radius if hero else skin.card_radius,
            "border": ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            "shadow": ft.BoxShadow(
                spread_radius=0,
                blur_radius=12,
                color=skin.glow,
                offset=ft.Offset(0, 3),
            ),
            "ink": on_click is not None,
            "on_click": on_click,
            "content": body,
        }
        if hero:
            kwargs["gradient"] = skin.hero_gradient(dark=dark)
        else:
            kwargs["bgcolor"] = ft.Colors.SURFACE_CONTAINER
        super().__init__(**kwargs)
