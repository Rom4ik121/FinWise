"""High-level page chrome: header + padded expanding body."""

from __future__ import annotations

from typing import Any, Callable

import flet as ft

from lib.presentation.responsive import page_frame_inset, scale_space, tap_icon_button
from lib.presentation.styles import page_header


def secondary_back_button(
    on_back: Callable[[], Any],
    *,
    lang: str | None = None,
) -> ft.IconButton:
    """Leading Back control that leaves a secondary route."""
    from lib.presentation.utils import tr

    return tap_icon_button(
        icon=ft.Icons.ARROW_BACK,
        tooltip=tr("action.close", lang or "en"),
        on_click=lambda _e: on_back(),
    )


def page_frame(
    *,
    title: str,
    body: ft.Control,
    page: ft.Page | None = None,
    lang: str | None = None,
    leading: ft.Control | None = None,
    actions: list[ft.Control] | None = None,
    extra: list[ft.Control] | None = None,
    on_back: Callable[[], Any] | None = None,
) -> list[ft.Control]:
    """Standard column children: header, optional toolbar, expanding body.

    Screens pass callbacks via ``actions`` / ``leading``; this helper only
    applies viewport gutters (``content_inset`` also centers lg/xl shells)
    and does not load data. Cutouts (notch / island / home indicator) are
    handled by ``wrap_safe_area`` on the app shell, not by extra header pixels.

    Pass ``on_back`` on every secondary route so the header has a Back
    control (``leading`` wins if both are set).
    """
    if leading is None and on_back is not None:
        leading = secondary_back_button(on_back, lang=lang)
    inset = page_frame_inset(page)
    kids: list[ft.Control] = [
        page_header(title, actions=actions, leading=leading, page=page),
    ]
    if extra:
        extra_pad = ft.Padding.only(
            left=inset,
            right=inset,
            top=scale_space(8, page),
            bottom=scale_space(4, page),
        )
        for item in extra:
            kids.append(ft.Container(padding=extra_pad, content=item))
    kids.append(
        ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(horizontal=inset),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=body,
        )
    )
    return kids


def page_column(
    controls: list[ft.Control],
    *,
    page: ft.Page | None = None,
) -> dict:
    """Kwargs for ``ft.Column`` used as a full-screen page root."""
    _ = page
    return {"expand": True, "spacing": 0, "controls": controls}
