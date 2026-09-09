"""Launch loading screen shown while FinWise initializes."""

from __future__ import annotations

import flet as ft

from lib.presentation.utils import tr

# Match classic dark shell (same atmosphere as the main app).
_SPLASH_TOP = "#0B1220"
_SPLASH_MID = "#121A2B"
_SPLASH_BOTTOM = "#0B1220"
_FG = "#FFFFFF"


def build_launch_splash(*, language: str = "ru") -> ft.Control:
    """Minimal loading screen — dark gradient + spinner (no duplicate branded splash)."""
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
            spacing=14,
            tight=True,
            controls=[
                ft.ProgressRing(
                    width=40,
                    height=40,
                    color=_FG,
                    stroke_width=3,
                ),
                ft.Text(
                    tr("loading", language),
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        ),
    )


def prepare_launch_page(page: ft.Page, *, language: str = "ru") -> None:
    """Paint the loading shell as early as Flet allows (``before_main`` hook)."""
    page.padding = 0
    page.bgcolor = _SPLASH_BOTTOM
    try:
        page.theme_mode = ft.ThemeMode.DARK
    except Exception:  # noqa: BLE001
        pass
    try:
        window = getattr(page, "window", None)
        if window is not None:
            window.bgcolor = _SPLASH_BOTTOM
    except Exception:  # noqa: BLE001
        pass
    if not page.controls:
        page.add(build_launch_splash(language=language))
    page.update()
