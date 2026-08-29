"""Reusable modern UI building blocks that adapt to light/dark themes."""

from __future__ import annotations

from typing import Optional, Sequence

import flet as ft

from lib.presentation.skins import get_active_skin


CARD_RADIUS = 18
CHIP_RADIUS = 14
SECTION_GAP = 14

# Catalog tiles: white line-art on muted sage circles (account / category pickers).
ICON_CATALOG_BADGE = "#8FA89A"
ICON_CATALOG_BADGE_SELECTED = "#6B8A7A"
ICON_CATALOG_GLYPH = "#FFFFFF"


def glass_layer(*, elevated: bool = False, opacity: float | None = None) -> dict:
    """Background + backdrop blur for cards, chips, and the nav pill."""
    skin = get_active_skin()
    token = (
        ft.Colors.SURFACE_CONTAINER_HIGH if elevated else ft.Colors.SURFACE_CONTAINER
    )
    if not skin.glass:
        return {"bgcolor": token, "blur": None}
    fill_opacity = opacity if opacity is not None else (0.40 if elevated else 0.32)
    return {
        "bgcolor": skin.glass_fill(token, opacity=fill_opacity),
        "blur": skin.backdrop_blur(),
        "clip_behavior": ft.ClipBehavior.ANTI_ALIAS,
    }


def card_surface(
    content: ft.Control,
    *,
    padding: int | ft.Padding = 16,
    accent: Optional[str] = None,
    ink: bool = False,
    on_click: Optional[ft.ControlEventHandler] = None,
    expand: Optional[bool] = None,
) -> ft.Container:
    """Elevated card with readable border in both themes."""
    skin = get_active_skin()
    border_color = accent or (
        ft.Colors.with_opacity(0.28, ft.Colors.ON_SURFACE)
        if skin.glass
        else ft.Colors.OUTLINE_VARIANT
    )
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=skin.card_radius,
        border=ft.Border.all(1, border_color),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=skin.card_blur,
            color=skin.glow,
            offset=ft.Offset(0, 6),
        ),
        ink=ink,
        on_click=on_click,
        expand=expand,
        animate=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
        **glass_layer(),
    )


def hero_card(
    content: ft.Control,
    *,
    padding: int = 20,
    expand: bool = True,
) -> ft.Container:
    """Primary gradient hero surface (balance / lock / KPI)."""
    skin = get_active_skin()
    extra = glass_layer(elevated=True, opacity=0.22) if skin.glass else {}
    extra.pop("bgcolor", None)
    return ft.Container(
        content=content,
        padding=padding,
        expand=expand,
        border_radius=skin.hero_radius,
        gradient=skin.hero_gradient(dark=True),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=24,
            color=skin.glow,
            offset=ft.Offset(0, 8),
        ),
        **extra,
    )


def section_title(text: str) -> ft.Text:
    """Section heading."""
    return ft.Text(
        text,
        size=15,
        weight=ft.FontWeight.W_700,
        color=ft.Colors.ON_SURFACE,
    )


def muted_text(text: str, *, size: int = 12) -> ft.Text:
    """Secondary / meta text with strong readability."""
    return ft.Text(text, size=size, color=ft.Colors.ON_SURFACE_VARIANT)


def summary_strip(
    rows: Sequence[tuple[str, str, Optional[str]]],
) -> ft.Container:
    """Compact summary card: list of (label, value, optional accent color)."""
    controls: list[ft.Control] = []
    for index, (label, value, accent) in enumerate(rows):
        if index:
            controls.append(ft.Container(height=1, bgcolor=ft.Colors.OUTLINE_VARIANT))
        controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=8,
                controls=[
                    ft.Text(
                        label,
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                        max_lines=2,
                    ),
                    ft.Text(
                        value,
                        size=13,
                        weight=ft.FontWeight.W_700,
                        color=accent or ft.Colors.ON_SURFACE,
                        text_align=ft.TextAlign.END,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            )
        )
    return card_surface(
        ft.Column(spacing=8, tight=True, controls=controls),
        padding=14,
    )


def page_header(
    title: str,
    *,
    actions: Optional[Sequence[ft.Control]] = None,
    leading: Optional[ft.Control] = None,
) -> ft.Container:
    """Page top bar — sits below SafeArea, clear of notch / status bar."""
    left: list[ft.Control] = []
    if leading is not None:
        left.append(leading)
    left.append(
        ft.Text(
            title,
            size=22,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
            expand=True,
        )
    )
    return ft.Container(
        # Horizontal inset + comfortable tap height under Dynamic Island / notch.
        padding=ft.Padding.only(left=16, right=10, top=12, bottom=8),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    controls=left,
                    spacing=4,
                    tight=True,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=list(actions or []),
                    tight=True,
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        ),
    )


def notice_banner(title: str, body: str) -> ft.Container:
    """Theme-aware reminder / alert strip."""
    return ft.Container(
        padding=14,
        border_radius=14,
        bgcolor=ft.Colors.TERTIARY_CONTAINER,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        **(
            {"blur": get_active_skin().backdrop_blur()}
            if get_active_skin().glass
            else {}
        ),
        content=ft.Row(
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color=ft.Colors.ON_TERTIARY_CONTAINER),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            title,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_TERTIARY_CONTAINER,
                            size=13,
                        ),
                        ft.Text(
                            body,
                            size=12,
                            color=ft.Colors.ON_TERTIARY_CONTAINER,
                        ),
                    ],
                ),
            ],
        ),
    )


def shortcut_chip(
    label: str,
    icon: ft.IconData,
    *,
    on_click: Optional[ft.ControlEventHandler] = None,
    width: int | None = None,
    expand: bool = True,
    badge: int = 0,
) -> ft.Container:
    """Quick-nav tile that stretches inside a responsive grid."""
    icon_box = ft.Container(
        width=34,
        height=34,
        border_radius=11,
        bgcolor=get_active_skin().badge_bg(dark=True),
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(icon, color=get_active_skin().badge_fg(dark=True), size=18),
    )
    if badge > 0:
        label_count = "9+" if badge > 9 else str(badge)
        icon_area: ft.Control = ft.Stack(
            width=40,
            height=40,
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                ft.Container(alignment=ft.Alignment.CENTER, content=icon_box),
                ft.Container(
                    right=0,
                    top=0,
                    content=ft.Container(
                        width=18,
                        height=18,
                        border_radius=9,
                        bgcolor=ft.Colors.ERROR,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(
                            label_count,
                            size=10,
                            weight=ft.FontWeight.W_800,
                            color=ft.Colors.ON_ERROR,
                        ),
                    ),
                ),
            ],
        )
    else:
        icon_area = icon_box

    return ft.Container(
        width=width,
        expand=expand,
        padding=ft.Padding.symmetric(horizontal=8, vertical=10),
        border_radius=get_active_skin().chip_radius,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        **glass_layer(elevated=True),
        ink=True,
        on_click=on_click,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
            tight=True,
            controls=[
                icon_area,
                ft.Text(
                    label,
                    size=11,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                ),
            ],
        ),
    )


def alert_corner(
    *,
    tooltip: str = "",
) -> ft.Container:
    """Red exclamation badge for the top-right corner of a card Stack."""
    return ft.Container(
        right=4,
        top=4,
        tooltip=tooltip or None,
        content=ft.Container(
            width=24,
            height=24,
            border_radius=12,
            bgcolor=ft.Colors.ERROR,
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(
                ft.Icons.PRIORITY_HIGH,
                size=14,
                color=ft.Colors.ON_ERROR,
            ),
        ),
    )



def amount_color(is_income: bool, *, dark: bool = True) -> str:
    """Income / expense color tuned for the active style."""
    skin = get_active_skin()
    if is_income:
        return skin.income_hex(dark=dark)
    return skin.expense_hex(dark=dark)


def badge_colors(*, dark: bool = True) -> tuple[str, str]:
    """Icon badge fill and glyph colors for the active style."""
    skin = get_active_skin()
    return skin.badge_bg(dark=dark), skin.badge_fg(dark=dark)


def icon_badge(
    icon: ft.IconData,
    *,
    bgcolor: Optional[str] = None,
    color: Optional[str] = None,
    size: int = 40,
) -> ft.Container:
    """Circular / rounded icon badge."""
    bg, fg = badge_colors()
    return ft.Container(
        width=size,
        height=size,
        border_radius=size // 3,
        bgcolor=bgcolor or bg,
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(
            icon,
            color=color or fg,
            size=int(size * 0.48),
        ),
    )


def labeled_switch(label: str, switch: ft.Switch) -> ft.Control:
    """Switch with wrapping label — avoids clipping long Russian strings."""
    switch.label = ""
    return ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(label, size=13, expand=True, max_lines=3),
            switch,
        ],
    )


def labeled_field(label: str, field: ft.TextField) -> ft.Control:
    """Put the caption above the field so Material labels never overlap values."""
    field.label = None
    field.dense = True
    return ft.Column(
        spacing=6,
        tight=True,
        controls=[
            ft.Text(label, size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=3),
            field,
        ],
    )
