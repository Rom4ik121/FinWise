"""Responsive card / KPI grids that wrap by viewport width."""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from lib.presentation.responsive import grid_columns, scale_space


def card_grid(
    items: Sequence[ft.Control],
    page: ft.Page | None = None,
    *,
    spacing: int | None = None,
    min_card: float = 280,
    maximum: int = 3,
) -> list[ft.Control]:
    """Pack cards into equal-width rows (1 / 2 / 3 columns).

    Returns a list of rows (or the original items when only one column fits)
    so callers can drop the result into a ListView.
    """
    cards = [item for item in items if item is not None]
    if not cards:
        return []
    cols = grid_columns(page, min_card=min_card, maximum=maximum)
    gap = spacing if spacing is not None else scale_space(10, page)
    if cols <= 1:
        return list(cards)
    rows: list[ft.Control] = []
    for index in range(0, len(cards), cols):
        chunk = list(cards[index : index + cols])
        while len(chunk) < cols:
            chunk.append(ft.Container(expand=True))
        rows.append(
            ft.Row(
                spacing=gap,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(expand=True, content=child) for child in chunk
                ],
            )
        )
    return rows
