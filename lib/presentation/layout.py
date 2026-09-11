"""Responsive layout helpers for compact mobile-first UI."""

from __future__ import annotations

import asyncio
from typing import Sequence

import flet as ft

# Re-export responsive primitives so pages can import from one place.
from lib.presentation.responsive import (  # noqa: F401
    BP_LG,
    BP_MD,
    BP_SM,
    BP_XL,
    BP_XS,
    LIST_NAV_CLEARANCE,
    MIN_TAP,
    breakpoint,
    calendar_cell_size,
    calendar_day_width,
    card_padding,
    clamp_content_width,
    compact_chart_size,
    content_inset,
    fit_font,
    form_control_width,
    grid_columns,
    is_compact,
    is_narrow,
    is_wide,
    layout_width,
    list_nav_padding,
    note_viewport_size,
    page_height,
    page_width,
    scale_factor,
    scale_font,
    scale_size,
    scale_space,
    shell_max_width,
    wrap_safe_area,
    swipe_action_strip_width,
    swipe_reveal_offset,
    tap_button_style,
    tap_icon_button,
    tap_padding,
    tx_tile_metrics,
)


def _hidden_scrollbar() -> ft.Scrollbar:
    return ft.Scrollbar(
        thumb_visibility=False,
        track_visibility=False,
        interactive=False,
        thickness=0,
    )


def _prevent_h_scroll_reset(control: ft.Control) -> None:
    """Keep a horizontal strip at the end instead of snapping back to the start.

    Only corrects non-user jumps (layout rebuild). Never fights intentional
    flings — that caused vertical/horizontal «teleport» on phones.
    """
    last = [0.0]
    restoring = [False]

    def _on_scroll(e: ft.OnScrollEvent) -> None:
        if restoring[0]:
            return
        try:
            px = float(getattr(e, "pixels", 0) or 0)
            max_ext = float(getattr(e, "max_scroll_extent", 0) or 0)
        except (TypeError, ValueError):
            return
        et = getattr(e, "event_type", None)
        et_name = str(getattr(et, "value", et) or "").lower()
        # Only auto-restore when Flutter resets to ~0 without a user gesture.
        jumped = (
            last[0] > 48
            and px < 4
            and last[0] >= max(40.0, max_ext * 0.55)
            and "user" not in et_name
            and "update" not in et_name
        )
        if jumped:
            restoring[0] = True
            target = last[0]

            async def _restore() -> None:
                try:
                    await asyncio.sleep(0.02)
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


def h_chip_row(*chips: ft.Control, height: int = 44) -> ft.ListView:
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
            padding=list_nav_padding(),
            auto_scroll=False,
            build_controls_on_demand=not eager,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
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
        inner_pad = list_nav_padding()
    elif isinstance(padding, int):
        inner_pad = ft.Padding.only(
            left=padding,
            right=padding,
            top=padding,
            bottom=max(padding, LIST_NAV_CLEARANCE),
        )
    else:
        inner_pad = padding
    return ft.Container(
        expand=True,
        padding=inner_pad,
        content=ft.ListView(
            expand=True,
            spacing=spacing,
            padding=list_nav_padding(),
            auto_scroll=False,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            scroll=_hidden_scrollbar(),
            controls=list(controls),
        ),
    )


def compact_button_row(*buttons: ft.Control) -> ft.Control:
    """Action buttons in a horizontal scroll so they never crush each other."""
    return h_scroll(buttons, spacing=8, height=48)
