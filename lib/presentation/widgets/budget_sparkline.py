"""Compact sparkline for category spend."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.skins import get_active_skin


def budget_spend_sparkline(
    buckets: list[tuple[str, Decimal]],
    *,
    height: int = 40,
    color: str | None = None,
) -> ft.Control:
    if not buckets:
        return ft.Container(height=0)
    values = [float(v) for _, v in buckets]
    peak = max(values) if values else 0.0
    if peak <= 0:
        return ft.Container(height=0)
    bar_color = color or get_active_skin().primary_hex(dark=True)
    bars: list[ft.Control] = []
    for val in values:
        h = max(4.0, (val / peak) * (height - 8))
        bars.append(
            ft.Container(
                expand=True,
                height=h,
                border_radius=4,
                bgcolor=bar_color if val > 0 else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            )
        )
    return ft.Container(
        height=height,
        padding=ft.Padding.symmetric(horizontal=4),
        content=ft.Row(
            spacing=3,
            vertical_alignment=ft.CrossAxisAlignment.END,
            expand=True,
            controls=bars,
        ),
    )
