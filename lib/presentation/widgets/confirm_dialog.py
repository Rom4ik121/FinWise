"""Confirmation dialog helper."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

import flet as ft

from lib.presentation.utils import run_async


def confirm_dialog(
    page: ft.Page,
    *,
    title: str,
    message: str,
    confirm_text: str = "Delete",
    cancel_text: str = "Cancel",
    on_confirm: Optional[Callable[[], None] | Callable[[], Awaitable[None]]] = None,
) -> None:
    """Open a destructive-confirm dialog."""

    async def _confirm(_e: ft.ControlEvent) -> None:
        page.pop_dialog()
        if on_confirm is None:
            return
        result = on_confirm()
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]

    dialog = ft.AlertDialog(
        modal=True,
        shape=ft.RoundedRectangleBorder(radius=20),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        title=ft.Row(
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.ERROR, size=22),
                ft.Text(
                    title,
                    weight=ft.FontWeight.W_700,
                    expand=True,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        ),
        content=ft.Text(
            message,
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        actions=[
            ft.TextButton(
                cancel_text,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=999),
                ),
                on_click=lambda _e: page.pop_dialog(),
            ),
            ft.FilledButton(
                confirm_text,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.ERROR,
                    color=ft.Colors.ON_ERROR,
                    shape=ft.RoundedRectangleBorder(radius=999),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                ),
                on_click=lambda e: run_async(page, _confirm, e),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
