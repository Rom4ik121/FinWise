"""Compact sparkline for subscription charges."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.skins import get_active_skin


def subscription_charge_sparkline(
    buckets: list[tuple[str, Decimal]],
    *,
    height: int = 48,
    color: str | None = None,
) -> ft.Control:
    """Simple bar sparkline for monthly charge buckets."""
    if not buckets:
        return ft.Container(height=height)
    values = [float(v) for _, v in buckets]
    peak = max(values) if values else 0.0
    if peak <= 0:
        peak = 1.0
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
                alignment=ft.Alignment.BOTTOM_CENTER,
            )
        )
    return ft.Container(
        height=height,
        padding=ft.Padding.symmetric(horizontal=4),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.END,
            expand=True,
            controls=bars,
        ),
    )
