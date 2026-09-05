"""Fullscreen form overlay (covers nav / content like a native screen)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Optional

import flet as ft

from lib.presentation.skins import get_active_skin
from lib.presentation.styles import (
    card_surface,
    form_header_bar,
    form_save_button,
    polish_form_control,
)
from lib.presentation.theme import is_dark_mode
from lib.presentation.responsive import clamp_content_width, tap_button_style
from lib.presentation.utils import run_async, safe_update, tr

CloseFn = Callable[[], None]
SaveFn = Callable[[], Awaitable[None]]


def dismiss_fullscreen(page: ft.Page, *, key: str) -> None:
    """Remove any overlay tagged with ``key``."""
    for item in list(page.overlay):
        if getattr(item, "data", None) == key:
            try:
                page.overlay.remove(item)
            except Exception:  # noqa: BLE001
                pass
    try:
        safe_update(page)
    except Exception:  # noqa: BLE001
        pass


def _polish_tree(controls: Sequence[ft.Control]) -> list[ft.Control]:
    out: list[ft.Control] = []
    for item in controls:
        polish_form_control(item)
        out.append(item)
    return out


def build_form_shell(
    page: ft.Page,
    *,
    title: str,
    lang: str,
    body: Sequence[ft.Control],
    leading: Optional[ft.Control] = None,
    actions: Optional[Sequence[ft.Control]] = None,
    wrap_body: bool = True,
) -> ft.Control:
    """Shared chrome: gradient backdrop, glass header, padded scroll body."""
    skin = get_active_skin()
    dark = is_dark_mode(page)
    form_w = clamp_content_width(page, margin=28, max_width=560)
    body_controls = _polish_tree(body)
    if wrap_body:
        panel = card_surface(
            ft.Column(spacing=14, tight=True, controls=body_controls),
            padding=18,
        )
        scroll_kids: list[ft.Control] = [
            ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                content=ft.Container(
                    width=form_w,
                    content=panel,
                ),
            ),
            ft.Container(height=40),
        ]
    else:
        scroll_kids = [
            ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                content=ft.Container(
                    width=form_w,
                    content=ft.Column(spacing=14, tight=True, controls=body_controls),
                ),
            ),
            ft.Container(height=40),
        ]

    close_leading = leading or ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=ft.Colors.ON_SURFACE,
        tooltip=tr("action.cancel", lang),
        style=tap_button_style(horizontal=10, vertical=10),
    )

    return ft.SafeArea(
        expand=True,
        content=ft.Container(
            expand=True,
            gradient=skin.page_gradient(dark=dark),
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    form_header_bar(
                        title,
                        leading=close_leading,
                        actions=list(actions or []),
                    ),
                    ft.Container(
                        expand=True,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                        content=ft.Column(
                            expand=True,
                            spacing=0,
                            scroll=ft.ScrollMode.AUTO,
                            controls=scroll_kids,
                        ),
                    ),
                ],
            ),
        ),
    )


def open_fullscreen_form(
    page: ft.Page,
    *,
    title: str,
    lang: str,
    body: Sequence[ft.Control],
    on_save: SaveFn | None = None,
    overlay_key: str = "fullscreen_form",
    save_icon: ft.IconData = ft.Icons.CHECK,
    save_label: str | None = None,
    show_save: bool = True,
    wrap_body: bool = True,
) -> CloseFn:
    """Show a full-screen form with close + optional save in the header.

    Returns a ``close`` callback the caller can invoke after a successful save.
    """
    dismiss_fullscreen(page, key=overlay_key)

    def _close(_e: Any = None) -> None:
        dismiss_fullscreen(page, key=overlay_key)

    async def _save_click(_e: ft.ControlEvent | None = None) -> None:
        if on_save is not None:
            await on_save()

    actions: list[ft.Control] = []
    if show_save and on_save is not None:
        actions.append(
            form_save_button(
                save_label or tr("action.save", lang),
                icon=save_icon,
                on_click=lambda e: run_async(page, _save_click, e),
            )
        )

    close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=ft.Colors.ON_SURFACE,
        tooltip=tr("action.cancel", lang),
        on_click=lambda _e: _close(),
        style=tap_button_style(horizontal=10, vertical=10),
    )

    overlay = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        width=getattr(page, "width", None) or None,
        height=getattr(page, "height", None) or None,
        expand=True,
        bgcolor=ft.Colors.SURFACE,
        alignment=ft.Alignment.TOP_CENTER,
        data=overlay_key,
        content=build_form_shell(
            page,
            title=title,
            lang=lang,
            body=body,
            leading=close_btn,
            actions=actions,
            wrap_body=wrap_body,
        ),
    )
    page.overlay.append(overlay)
    safe_update(page)
    return _close
