"""Fullscreen icon and color pickers (covers the current form)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Optional

import flet as ft

from lib.presentation.account_icons import icon_is_logo
from lib.presentation.styles import (
    ICON_CATALOG_BADGE,
    ICON_CATALOG_BADGE_BORDER,
    ICON_CATALOG_BADGE_SELECTED,
    page_header,
)
from lib.presentation.haptics import haptic
from lib.presentation.ui_motion import (
    DUR_FAST,
    bind_press,
    motion_animation,
    overlay_enter_style,
)
from lib.presentation.utils import safe_update, tr
from lib.presentation.widgets.fullscreen_form import dismiss_fullscreen, push_overlay

_TILE_SCALE = 1.06

IconRenderer = Callable[[str], ft.Control]
SelectStr = Callable[[str], None]


def _picker_list(*, spacing: float, padding: ft.Padding, controls: list[ft.Control]) -> ft.ListView:
    """Vertical catalog scroll — no nested scrollables (wrap Rows only).

    Uses visible/adaptive scroll so drag-to-scroll works reliably on desktop
    and mobile; ``build_controls_on_demand=False`` so long catalogs measure height.
    """
    return ft.ListView(
        expand=True,
        spacing=spacing,
        padding=padding,
        auto_scroll=False,
        build_controls_on_demand=False,
        scroll=ft.ScrollMode.AUTO,
        controls=controls,
    )


def build_icon_catalog(
    *,
    lang: str,
    groups: Sequence[tuple[str, Sequence[str]]],
    selected: dict[str, str],
    render_icon: IconRenderer,
    on_change: Optional[SelectStr] = None,
    accent: Optional[str] = None,
    page: ft.Page | None = None,
) -> list[ft.Control]:
    """Grouped circular badges with soft fill; logos clip to the circle.

    Uses non-scrolling wrap rows so the outer ListView can scroll vertically
    (nested GridView + ListView fights gesture handling on mobile/desktop).
    """
    accent_color = accent or ft.Colors.PRIMARY
    tiles_by_key: dict[str, list[ft.Container]] = {}

    def _style_tile(key: str, tile: ft.Container) -> None:
        active = key == selected["value"]
        logo = icon_is_logo(key)
        if logo:
            # Logo already paints the disk — keep highlight as a thin ring only.
            tile.bgcolor = ft.Colors.TRANSPARENT
            tile.border = ft.Border.all(
                2 if active else 0,
                accent_color if active else ft.Colors.TRANSPARENT,
            )
        else:
            tile.bgcolor = (
                ICON_CATALOG_BADGE_SELECTED if active else ICON_CATALOG_BADGE
            )
            tile.border = ft.Border.all(
                2 if active else 1,
                accent_color if active else ICON_CATALOG_BADGE_BORDER,
            )
        tile.shadow = (
            ft.BoxShadow(
                blur_radius=8,
                color="#00000028",
                offset=ft.Offset(0, 1),
            )
            if active
            else None
        )
        tile.scale = _TILE_SCALE if active else 1.0

    def _highlight(key: str) -> None:
        try:
            haptic("selection")
        except Exception:  # noqa: BLE001
            pass
        previous = selected["value"]
        selected["value"] = key
        to_refresh: list[ft.Container] = []
        for old in tiles_by_key.get(previous, ()):
            _style_tile(previous, old)
            to_refresh.append(old)
        for new in tiles_by_key.get(key, ()):
            _style_tile(key, new)
            to_refresh.append(new)
        for tile in to_refresh:
            safe_update(tile)
        if on_change is not None:
            on_change(key)

    controls: list[ft.Control] = []
    for group_key, keys in groups:
        if not keys:
            continue
        controls.append(
            ft.Text(
                tr(group_key, lang),
                size=16,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            )
        )
        tiles: list[ft.Control] = []
        for key in keys:
            tile = ft.Container(
                width=56,
                height=56,
                border_radius=999,
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ink=True,
                scale=1,
                animate_scale=motion_animation(DUR_FAST, page),
                on_click=lambda _e, k=key: _highlight(k),
                content=render_icon(key),
            )
            _style_tile(key, tile)
            tiles_by_key.setdefault(key, []).append(tile)
            tiles.append(tile)
        controls.append(
            ft.Row(
                wrap=True,
                spacing=10,
                run_spacing=10,
                controls=tiles,
            )
        )
        controls.append(ft.Container(height=16))
    return controls


def open_icon_picker(
    page: ft.Page,
    *,
    lang: str,
    groups: Sequence[tuple[str, Sequence[str]]],
    selected: str,
    on_select: SelectStr,
    render_icon: IconRenderer,
    overlay_key: str = "icon_picker",
    accent: Optional[str] = None,
) -> None:
    """Open a full-screen grouped icon catalog.

    Tapping an icon highlights it; ``Select`` applies and closes.
    """
    dismiss_fullscreen(page, key=overlay_key)
    current = {"value": selected}

    def _close(_e: object = None) -> None:
        dismiss_fullscreen(page, key=overlay_key)

    def _confirm(_e: object = None) -> None:
        if current["value"]:
            on_select(current["value"])
        _close()

    group_controls = build_icon_catalog(
        lang=lang,
        groups=groups,
        selected=current,
        render_icon=render_icon,
        accent=accent,
        page=page,
    )

    body = _picker_list(
        spacing=4,
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        controls=[*group_controls, ft.Container(height=8)],
    )

    select_btn = ft.FilledButton(
        tr("action.select", lang),
        expand=True,
        height=48,
        on_click=_confirm,
    )
    bind_press(select_btn, haptic_kind="light", page=page)
    overlay = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        bgcolor=ft.Colors.SURFACE,
        data=overlay_key,
        **overlay_enter_style(page),
        content=ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    page_header(
                        tr("picker.icon_catalog", lang),
                        leading=ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            icon_color=ft.Colors.ON_SURFACE,
                            tooltip=tr("action.cancel", lang),
                            on_click=_close,
                        ),
                    ),
                    ft.Container(expand=True, content=body),
                    ft.Container(
                        padding=ft.Padding.only(left=16, right=16, bottom=12, top=4),
                        content=select_btn,
                    ),
                ],
            ),
        ),
    )
    push_overlay(page, overlay)


def open_color_picker(
    page: ft.Page,
    *,
    lang: str,
    colors: Sequence[str],
    selected: str,
    on_select: SelectStr,
    overlay_key: str = "color_picker",
) -> None:
    """Open a full-screen color palette with confirm.

    Tapping a swatch highlights it; ``Select`` applies and closes.
    """
    dismiss_fullscreen(page, key=overlay_key)
    palette = list(colors)
    if selected and selected not in palette:
        palette.insert(0, selected)
    current = {"value": selected or (palette[0] if palette else "#00897B")}
    tiles_by_color: dict[str, ft.Container] = {}

    def _close(_e: object = None) -> None:
        dismiss_fullscreen(page, key=overlay_key)

    def _apply_border(color: str, tile: ft.Container) -> None:
        active = color == current["value"]
        tile.border = ft.Border.all(
            3 if active else 1,
            ft.Colors.ON_SURFACE if active else ft.Colors.OUTLINE_VARIANT,
        )
        tile.scale = _TILE_SCALE if active else 1.0

    def _highlight(color: str) -> None:
        try:
            haptic("selection")
        except Exception:  # noqa: BLE001
            pass
        previous = current["value"]
        current["value"] = color
        old = tiles_by_color.get(previous)
        new = tiles_by_color.get(color)
        if old is not None:
            _apply_border(previous, old)
        if new is not None:
            _apply_border(color, new)
        if old is not None:
            safe_update(old)
        if new is not None:
            safe_update(new)

    def _confirm(_e: object = None) -> None:
        on_select(current["value"])
        _close()

    tiles: list[ft.Control] = []
    for color in palette:
        tile = ft.Container(
            width=56,
            height=56,
            border_radius=999,
            bgcolor=color,
            ink=True,
            scale=1,
            animate_scale=motion_animation(DUR_FAST, page),
            on_click=lambda _e, c=color: _highlight(c),
        )
        _apply_border(color, tile)
        tiles_by_color[color] = tile
        tiles.append(tile)

    body = _picker_list(
        spacing=0,
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        controls=[
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=8,
                controls=tiles,
            ),
            ft.Container(height=8),
        ],
    )

    select_btn = ft.FilledButton(
        tr("action.select", lang),
        expand=True,
        height=48,
        on_click=_confirm,
    )
    bind_press(select_btn, haptic_kind="light", page=page)
    overlay = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        bgcolor=ft.Colors.SURFACE,
        data=overlay_key,
        **overlay_enter_style(page),
        content=ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    page_header(
                        tr("picker.color_title", lang),
                        leading=ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            icon_color=ft.Colors.ON_SURFACE,
                            tooltip=tr("action.cancel", lang),
                            on_click=_close,
                        ),
                    ),
                    ft.Container(expand=True, content=body),
                    ft.Container(
                        padding=ft.Padding.only(left=16, right=16, bottom=12, top=4),
                        content=select_btn,
                    ),
                ],
            ),
        ),
    )
    push_overlay(page, overlay)
