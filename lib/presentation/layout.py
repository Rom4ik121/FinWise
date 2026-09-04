"""Responsive layout helpers for compact mobile-first UI."""

from __future__ import annotations

from typing import Sequence

import flet as ft


def _hidden_scrollbar() -> ft.Scrollbar:
    return ft.Scrollbar(
        thumb_visibility=False,
        track_visibility=False,
        interactive=False,
        thickness=0,
    )


def _prevent_h_scroll_reset(control: ft.Control) -> None:
    """Keep a horizontal strip at the end instead of snapping back to the start."""
    last = [0.0]
    restoring = [False]

    def _on_scroll(e: ft.OnScrollEvent) -> None:
        if restoring[0]:
            return
        px = float(getattr(e, "pixels", 0) or 0)
        max_ext = float(getattr(e, "max_scroll_extent", 0) or 0)
        et = getattr(e, "event_type", None)
        et_name = str(getattr(et, "value", et) or "").lower()
        jumped = last[0] > 28 and px < 6 and last[0] >= max(24.0, max_ext * 0.45)
        if jumped and "user" not in et_name:
            restoring[0] = True
            target = last[0]

            async def _restore() -> None:
                try:
                    await control.scroll_to(offset=target, duration=0)
                except Exception:  # noqa: BLE001
                    pass
                restoring[0] = False

            from lib.presentation.utils import control_page, run_async

            page = control_page(control)
            if page is not None:
                run_async(page, _restore)
            else:
                restoring[0] = False
            return
        last[0] = px

    control.on_scroll = _on_scroll


def h_scroll(
    controls: Sequence[ft.Control],
    *,
    spacing: int = 10,
    height: int | None = None,
    padding: int | ft.Padding | None = None,
) -> ft.Container:
    """Horizontal scroll strip — use when items don't fit the viewport width."""
    row = ft.ListView(
        horizontal=True,
        spacing=spacing,
        padding=ft.Padding.only(right=12),
        auto_scroll=False,
        height=height,
        adaptive=False,
        build_controls_on_demand=False,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        scroll=_hidden_scrollbar(),
        controls=list(controls),
    )
    _prevent_h_scroll_reset(row)
    return ft.Container(
        height=height,
        padding=padding,
        content=row,
    )


def h_chip_row(*chips: ft.Control, height: int = 40) -> ft.ListView:
    """Horizontal chip strip that stays at the end instead of jumping back."""
    row = ft.ListView(
        horizontal=True,
        spacing=6,
        padding=ft.Padding.only(right=36),
        auto_scroll=False,
        height=height,
        adaptive=False,
        build_controls_on_demand=False,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        scroll=_hidden_scrollbar(),
        controls=list(chips),
    )
    _prevent_h_scroll_reset(row)
    return row


def make_v_scroll(*, spacing: int = 12, eager: bool = False) -> ft.ListView:
    """Vertical list that keeps offset better than a scrolling Column.

    ``eager=True`` builds all children up front (needed so off-screen charts
    can mount). Default on-demand build keeps long transaction lists light.
    """
    from lib.presentation.ui_motion import remember_scroll

    return remember_scroll(
        ft.ListView(
            expand=True,
            spacing=spacing,
            padding=ft.Padding.only(bottom=40),
            auto_scroll=False,
            build_controls_on_demand=not eager,
            scroll=_hidden_scrollbar(),
        )
    )


def v_scroll_body(
    *controls: ft.Control,
    spacing: int = 12,
    padding: int | ft.Padding | None = 16,
) -> ft.Container:
    """Expanding vertical scroll area for page body content."""
    inner_pad: ft.Padding
    if padding is None:
        inner_pad = ft.Padding.only(bottom=40)
    elif isinstance(padding, int):
        inner_pad = ft.Padding.only(
            left=padding, right=padding, top=padding, bottom=padding + 24
        )
    else:
        inner_pad = padding
    return ft.Container(
        expand=True,
        padding=inner_pad,
        content=ft.ListView(
            expand=True,
            spacing=spacing,
            padding=ft.Padding.only(bottom=40),
            auto_scroll=False,
            scroll=_hidden_scrollbar(),
            controls=list(controls),
        ),
    )


def compact_button_row(*buttons: ft.Control) -> ft.Control:
    """Action buttons in a horizontal scroll so they never crush each other."""
    return h_scroll(buttons, spacing=8, height=48)
