"""Reusable modern UI building blocks that adapt to light/dark themes."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import flet as ft

from lib.presentation.skins import get_active_skin


CARD_RADIUS = 18
CHIP_RADIUS = 14
SECTION_GAP = 14

# Catalog tiles: opaque dark disks (Flutter treats 8-digit hex as AARRGGBB —
# values like #FFFFFF14 become yellow and hide white glyphs).
ICON_CATALOG_BADGE = "#252B32"
ICON_CATALOG_BADGE_SELECTED = "#0F2A21"
ICON_CATALOG_GLYPH = "#F5F7FA"
ICON_CATALOG_BADGE_BORDER = "#3A424A"


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
    animate: bool = True,
) -> ft.Container:
    """Elevated card with readable border in both themes."""
    skin = get_active_skin()
    border_color = accent or (
        ft.Colors.with_opacity(0.28, ft.Colors.ON_SURFACE)
        if skin.glass
        else ft.Colors.OUTLINE_VARIANT
    )
    kwargs: dict = {
        "content": content,
        "padding": padding,
        "border_radius": skin.card_radius,
        "border": ft.Border.all(1, border_color),
        "shadow": ft.BoxShadow(
            spread_radius=0,
            blur_radius=skin.card_blur,
            color=skin.glow,
            offset=ft.Offset(0, 6),
        ),
        "ink": ink,
        "on_click": on_click,
        "expand": expand,
        **glass_layer(),
    }
    if animate:
        kwargs["animate"] = ft.Animation(220, ft.AnimationCurve.EASE_OUT)
    return ft.Container(**kwargs)


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


def section_title(text: str, *, page: ft.Page | None = None) -> ft.Text:
    """Section heading (viewport-scaled)."""
    from lib.presentation.responsive import scale_font

    return ft.Text(
        text,
        size=scale_font(15, page),
        weight=ft.FontWeight.W_700,
        color=ft.Colors.ON_SURFACE,
    )


def muted_text(
    text: str, *, size: int = 12, page: ft.Page | None = None
) -> ft.Text:
    """Secondary / meta text with strong readability."""
    from lib.presentation.responsive import scale_font

    return ft.Text(
        text,
        size=scale_font(size, page, minimum=10, maximum=18),
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


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
    page: ft.Page | None = None,
) -> ft.Container:
    """Page top bar — sits below SafeArea, clear of notch / status bar."""
    from lib.presentation.responsive import scale_font

    left: list[ft.Control] = []
    if leading is not None:
        left.append(leading)
    left.append(
        ft.Text(
            title,
            size=scale_font(22, page, minimum=18, maximum=26),
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
        width=40,
        height=40,
        border_radius=12,
        bgcolor=get_active_skin().badge_bg(dark=True),
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(icon, color=get_active_skin().badge_fg(dark=True), size=20),
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
        ink_color=ft.Colors.TRANSPARENT,
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
    polish_form_control(field)
    return ft.Column(
        spacing=6,
        tight=True,
        controls=[
            ft.Text(label, size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=3),
            field,
        ],
    )


FORM_FIELD_RADIUS = 14
FORM_MENU_RADIUS = 16


def dropdown_menu_style() -> ft.MenuStyle:
    """Rounded elevated menu for Dropdown option sheets."""
    return ft.MenuStyle(
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        elevation=10,
        padding=ft.Padding.symmetric(horizontal=6, vertical=8),
        shape=ft.RoundedRectangleBorder(radius=FORM_MENU_RADIUS),
        shadow_color=ft.Colors.with_opacity(0.35, ft.Colors.SHADOW),
    )


def style_popup_menu(button: ft.PopupMenuButton) -> ft.PopupMenuButton:
    """Neon-friendly shape / padding for ⋮ overflow menus."""
    button.shape = ft.RoundedRectangleBorder(radius=FORM_MENU_RADIUS)
    button.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
    button.elevation = 10
    button.menu_padding = ft.Padding.symmetric(horizontal=6, vertical=8)
    button.shadow_color = ft.Colors.with_opacity(0.35, ft.Colors.SHADOW)
    return button


def polish_form_control(control: ft.Control) -> ft.Control:
    """Softer corners / density for form inputs (walks nested layouts)."""
    if isinstance(control, ft.TextField):
        control.border_radius = FORM_FIELD_RADIUS
        control.filled = True
        if getattr(control, "dense", None) is None:
            control.dense = True
    elif isinstance(control, ft.Dropdown):
        control.border_radius = FORM_FIELD_RADIUS
        control.filled = True
        if getattr(control, "dense", None) is None:
            control.dense = True
        if getattr(control, "menu_style", None) is None:
            control.menu_style = dropdown_menu_style()
    elif isinstance(control, ft.PopupMenuButton):
        style_popup_menu(control)
    elif isinstance(control, ft.Column):
        for child in list(getattr(control, "controls", None) or []):
            polish_form_control(child)
    elif isinstance(control, ft.Row):
        for child in list(getattr(control, "controls", None) or []):
            polish_form_control(child)
    elif isinstance(control, ft.Container):
        inner = getattr(control, "content", None)
        if inner is not None:
            polish_form_control(inner)
    return control


def form_hint(text: str, *, size: int = 12) -> ft.Control:
    """Explanatory helper lines are suppressed app-wide (kept as API stub)."""
    del text, size
    return ft.Container(visible=False, height=0, padding=0, margin=0)


def form_section(
    title: str | None,
    controls: Sequence[ft.Control],
    *,
    hint: str | None = None,
    icon: Optional[ft.IconData] = None,
) -> ft.Container:
    """Grouped card of related fields — used inside fullscreen editors."""
    del hint  # section explanations disabled
    kids: list[ft.Control] = []
    if title:
        title_row: list[ft.Control] = []
        if icon is not None:
            title_row.append(
                ft.Icon(icon, size=18, color=ft.Colors.PRIMARY),
            )
        title_row.append(
            ft.Text(
                title,
                size=13,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
                expand=True,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
        kids.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=title_row,
            )
        )
    for item in controls:
        polish_form_control(item)
        kids.append(item)
    return card_surface(
        ft.Column(spacing=12, tight=True, controls=kids),
        padding=16,
    )


def form_save_button(
    label: str,
    *,
    icon: ft.IconData = ft.Icons.CHECK,
    on_click: Optional[ft.ControlEventHandler] = None,
    content: Optional[ft.Control] = None,
) -> ft.FilledButton:
    """Pill primary action used in form headers."""
    kwargs: dict = {
        "icon": icon,
        "style": ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=999),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=ft.Colors.PRIMARY,
            color=ft.Colors.ON_PRIMARY,
        ),
        "on_click": on_click,
    }
    if content is not None:
        return ft.FilledButton(content=content, **kwargs)
    return ft.FilledButton(label, **kwargs)


def form_header_bar(
    title: str,
    *,
    leading: Optional[ft.Control] = None,
    actions: Optional[Sequence[ft.Control]] = None,
) -> ft.Container:
    """Compact form top bar with glass strip (titles stay readable)."""
    left: list[ft.Control] = []
    if leading is not None:
        left.append(leading)
    left.append(
        ft.Text(
            title,
            size=18,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
            expand=True,
        )
    )
    skin = get_active_skin()
    return ft.Container(
        padding=ft.Padding.only(left=8, right=12, top=10, bottom=10),
        border=ft.Border.only(
            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, ft.Colors.OUTLINE_VARIANT))
        ),
        **glass_layer(elevated=True, opacity=0.28 if skin.glass else None),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    controls=left,
                    spacing=2,
                    tight=True,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=list(actions or []),
                    tight=True,
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        ),
    )


def choice_chips(
    options: Sequence[tuple[str, str]],
    *,
    value: str,
    on_changed: Callable[[str], None],
) -> ft.Row:
    """Compact selectable chips (priority etc.) — avoids plain dropdown sheets."""
    selected = {"value": value}
    row = ft.Row(spacing=8, wrap=True, tight=True, controls=[])

    def _rebuild() -> None:
        chips: list[ft.Control] = []
        for key, label in options:
            active = selected["value"] == key
            chips.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                    border_radius=999,
                    bgcolor=(
                        ft.Colors.PRIMARY_CONTAINER
                        if active
                        else ft.Colors.SURFACE_CONTAINER
                    ),
                    border=ft.Border.all(
                        1,
                        ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT,
                    ),
                    ink=True,
                    on_click=lambda _e, k=key: _pick(k),
                    content=ft.Text(
                        label,
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=(
                            ft.Colors.ON_PRIMARY_CONTAINER
                            if active
                            else ft.Colors.ON_SURFACE
                        ),
                    ),
                )
            )
        row.controls = chips
        try:
            from lib.presentation.utils import safe_update

            safe_update(row)
        except Exception:  # noqa: BLE001
            pass

    def _pick(key: str) -> None:
        if selected["value"] == key:
            return
        selected["value"] = key
        _rebuild()
        on_changed(key)

    _rebuild()
    row.data = selected  # type: ignore[attr-defined]
    return row
