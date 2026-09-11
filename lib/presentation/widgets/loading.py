"""Loading indicators and soft skeleton placeholders."""

from __future__ import annotations

import flet as ft

from lib.presentation.utils import safe_update


def fill_loading(host: ft.Control, *, message: str = "") -> None:
    """Show placeholders only when the host is still empty.

    Replacing populated scroll content with a spinner jumps the page to the top.
    """
    current = getattr(host, "controls", None)
    if current:
        return
    host.controls = [skeleton_list()]
    safe_update(host)


def loading_indicator(*, message: str = "") -> ft.Control:
    """Compact centered progress ring with optional caption.

    Do not use ``expand=True`` here — ListView children with expand collapse
    to zero height and the home screen looks blank while loading.
    """
    controls: list[ft.Control] = [ft.ProgressRing()]
    if message:
        controls.append(ft.Text(message, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Container(
        height=180,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            tight=True,
            controls=controls,
        ),
    )


def skeleton_bar(
    *,
    width: int | float | None = None,
    height: int = 12,
    expand: bool = False,
) -> ft.Control:
    """Soft rounded placeholder bar (no pulse — avoids extra frames)."""
    return ft.Container(
        width=width,
        height=height,
        expand=expand,
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE),
    )


def skeleton_row(*, height: int = 56) -> ft.Control:
    """One list-row skeleton: avatar + two lines."""
    return ft.Container(
        height=height,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=14,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=40,
                    height=40,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE),
                ),
                ft.Column(
                    spacing=8,
                    tight=True,
                    expand=True,
                    controls=[
                        skeleton_bar(height=12, expand=True),
                        skeleton_bar(width=120, height=10),
                    ],
                ),
            ],
        ),
    )


def skeleton_list(*, rows: int = 4) -> ft.Control:
    """Stacked row placeholders used instead of a blank first paint."""
    return ft.Column(
        spacing=8,
        tight=True,
        controls=[skeleton_row() for _ in range(max(1, rows))],
    )


class LoadingOverlay(ft.Container):
    """Semi-transparent overlay used while async work runs."""

    def __init__(self, *, message: str = "") -> None:
        super().__init__(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            visible=False,
            content=ft.Container(
                padding=20,
                border_radius=16,
                bgcolor=ft.Colors.SURFACE,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.ProgressRing(),
                        ft.Text(message),
                    ],
                ),
            ),
        )

    def show(self, message: str | None = None) -> None:
        """Show the overlay, optionally updating the caption."""
        if message is not None and isinstance(self.content, ft.Container):
            col = self.content.content
            if isinstance(col, ft.Column) and len(col.controls) > 1:
                col.controls[1] = ft.Text(message)
        self.visible = True

    def hide(self) -> None:
        """Hide the overlay."""
        self.visible = False
