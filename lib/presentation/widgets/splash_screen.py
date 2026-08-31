"""Branded launch screen shown while FinWise initializes."""

from __future__ import annotations

import flet as ft

from lib.presentation.utils import tr

# Match classic dark shell (same atmosphere as the main app).
_SPLASH_TOP = "#0B1220"
_SPLASH_MID = "#121A2B"
_SPLASH_BOTTOM = "#0B1220"
_FG = "#FFFFFF"


def build_launch_splash(*, language: str = "ru") -> ft.Control:
    """Splash: app gradient, Material wallet icon, FinWise, loader — no tagline."""
    return ft.Container(
        expand=True,
        bgcolor=_SPLASH_BOTTOM,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[_SPLASH_TOP, _SPLASH_MID, _SPLASH_BOTTOM],
        ),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
            tight=True,
            controls=[
                ft.Icon(
                    ft.Icons.ACCOUNT_BALANCE_WALLET,
                    size=120,
                    color=_FG,
                ),
                ft.Text(
                    tr("app.name", language),
                    size=36,
                    weight=ft.FontWeight.W_700,
                    color=_FG,
                ),
                ft.Container(
                    width=72,
                    height=3,
                    border_radius=2,
                    bgcolor=_FG,
                ),
                ft.Container(height=20),
                ft.ProgressRing(
                    width=34,
                    height=34,
                    color=_FG,
                    stroke_width=3,
                ),
            ],
        ),
    )
