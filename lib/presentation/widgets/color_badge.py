"""Shared icon disk used on transaction, budget, and category tiles."""

from __future__ import annotations

import flet as ft

from lib.presentation.responsive import scale_size


def color_badge(
    icon: ft.IconData,
    *,
    bgcolor: str | None = None,
    fgcolor: str = "#FFFFFF",
    size: int = 36,
    glyph_size: int = 18,
    page: ft.Page | None = None,
    radius: int | None = None,
) -> ft.Container:
    """Scaled circular/rounded badge; glyphs stay inside the disk."""
    edge = scale_size(size, page, floor=0.90, ceil=1.18, minimum=28, maximum=48)
    glyph = scale_size(
        glyph_size, page, floor=0.90, ceil=1.18, minimum=14, maximum=26
    )
    return ft.Container(
        width=edge,
        height=edge,
        border_radius=radius if radius is not None else max(8, int(edge * 0.30)),
        bgcolor=bgcolor,
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(icon, size=glyph, color=fgcolor),
    )
