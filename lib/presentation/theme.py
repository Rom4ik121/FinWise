"""FinWise visual system — palettes live in ``lib.presentation.skins``.

Classic (default) is slate + mint. Neon is matte black + #00FF99.
"""

from __future__ import annotations

import flet as ft

from lib.presentation.skins import get_active_skin, set_active_skin

# Classic tokens kept as import-time aliases (the default look).
# Runtime widgets should use ``get_active_skin()`` so Neon can recolor them.
DARK_BG = "#0B1220"
DARK_SURFACE = "#121A2B"
DARK_SURFACE_2 = "#1A2438"
DARK_SURFACE_3 = "#243049"
DARK_BORDER = "#2C3A55"
DARK_TEXT = "#F1F5F9"
DARK_MUTED = "#94A3B8"
DARK_PRIMARY = "#2DD4BF"
DARK_PRIMARY_DIM = "#14B8A6"
DARK_ON_PRIMARY = "#042F2E"
DARK_INCOME = "#4ADE80"
DARK_EXPENSE = "#F87171"
DARK_WARN = "#FBBF24"

LIGHT_BG = "#F1F5F9"
LIGHT_SURFACE = "#FFFFFF"
LIGHT_SURFACE_2 = "#F8FAFC"
LIGHT_SURFACE_3 = "#E2E8F0"
LIGHT_BORDER = "#CBD5E1"
LIGHT_TEXT = "#0F172A"
LIGHT_MUTED = "#475569"
LIGHT_PRIMARY = "#0F766E"
LIGHT_PRIMARY_DIM = "#0D9488"
LIGHT_ON_PRIMARY = "#FFFFFF"
LIGHT_INCOME = "#15803D"
LIGHT_EXPENSE = "#B91C1C"
LIGHT_WARN = "#B45309"

SEED_COLOR = DARK_PRIMARY
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_DISPLAY = "Segoe UI Semibold"


def _mobile_runtime(page: ft.Page | None = None) -> bool:
    """True on iOS/Android packaged Flet apps (system fonts only)."""
    from lib.infrastructure.services.biometric import is_mobile_platform, mobile_runtime

    if mobile_runtime():
        return True
    return is_mobile_platform(page)


def light_color_scheme() -> ft.ColorScheme:
    """Light scheme for the active visual style."""
    return get_active_skin().light_color_scheme()


def dark_color_scheme() -> ft.ColorScheme:
    """Dark scheme for the active visual style."""
    return get_active_skin().dark_color_scheme()


def _no_ink_overlay() -> ft.ButtonStyle:
    """Kill Material grey hover / focus / press ripples on buttons."""
    clear = ft.Colors.TRANSPARENT
    return ft.ButtonStyle(
        overlay_color={
            ft.ControlState.HOVERED: clear,
            ft.ControlState.FOCUSED: clear,
            ft.ControlState.PRESSED: clear,
            ft.ControlState.DRAGGED: clear,
            ft.ControlState.DEFAULT: clear,
        }
    )


def build_theme(*, dark: bool = False, page: ft.Page | None = None) -> ft.Theme:
    """Build a Material theme for the active skin."""
    skin = get_active_skin()
    clear = ft.Colors.TRANSPARENT
    no_overlay = _no_ink_overlay()
    kwargs: dict = {
        "color_scheme_seed": skin.seed,
        "color_scheme": skin.color_scheme(dark=dark),
        # No grey glow when hovering / focusing any Material control.
        "hover_color": clear,
        "splash_color": clear,
        "highlight_color": clear,
        "icon_button_theme": ft.IconButtonTheme(style=no_overlay),
        "text_button_theme": ft.TextButtonTheme(style=no_overlay),
        "button_theme": ft.ButtonTheme(style=no_overlay),
        "outlined_button_theme": ft.OutlinedButtonTheme(style=no_overlay),
        "filled_button_theme": ft.FilledButtonTheme(style=no_overlay),
        # Hide the grey Material thumb on every scrollable (pages, lists, sheets).
        "scrollbar_theme": ft.ScrollbarTheme(
            thumb_visibility=False,
            track_visibility=False,
            thickness=0,
            cross_axis_margin=0,
            main_axis_margin=0,
            interactive=False,
            thumb_color=ft.Colors.TRANSPARENT,
            track_color=ft.Colors.TRANSPARENT,
            track_border_color=ft.Colors.TRANSPARENT,
        ),
    }
    # Segoe UI is missing on iPhone/Android and breaks glyph metrics (letters split).
    if not _mobile_runtime(page):
        kwargs["font_family"] = FONT_FAMILY
    return ft.Theme(**kwargs)


def resolve_theme_mode(mode: str | ft.ThemeMode | None) -> ft.ThemeMode:
    """Map a settings string / ThemeMode to :class:`ft.ThemeMode`."""
    if isinstance(mode, ft.ThemeMode):
        return mode
    value = str(mode or "dark").lower()
    # Handle enum string forms like "ThemeMode.DARK" / "dark"
    if "." in value:
        value = value.split(".")[-1]
    if value == "light":
        return ft.ThemeMode.LIGHT
    if value == "system":
        return ft.ThemeMode.SYSTEM
    return ft.ThemeMode.DARK


def is_dark_mode(page: ft.Page, mode: str | ft.ThemeMode | None = None) -> bool:
    """Best-effort dark-mode detection for conditional styling."""
    source = mode if mode is not None else getattr(page, "theme_mode", None)
    resolved = resolve_theme_mode(source)
    if resolved == ft.ThemeMode.DARK:
        return True
    if resolved == ft.ThemeMode.LIGHT:
        return False
    # SYSTEM — prefer dark as product default when platform is unknown.
    platform_brightness = getattr(page, "platform_brightness", None)
    if platform_brightness is not None and str(platform_brightness).lower().endswith(
        "light"
    ):
        return False
    return True


def apply_theme(
    page: ft.Page,
    mode: str | None = "dark",
    style: str | None = None,
) -> None:
    """Apply visual style, light/dark themes, and theme mode to the page."""
    if style is not None:
        set_active_skin(style)
    page.theme = build_theme(dark=False, page=page)
    page.dark_theme = build_theme(dark=True, page=page)
    page.theme_mode = resolve_theme_mode(mode)
    dark = is_dark_mode(page, page.theme_mode)
    skin = get_active_skin()
    page.bgcolor = skin.dark_bg if dark else skin.light_bg
    page.decoration = ft.BoxDecoration(gradient=skin.page_gradient(dark=dark))
    if _mobile_runtime(page):
        page.theme.font_family = None
        page.dark_theme.font_family = None
    else:
        page.fonts = {
            "Segoe UI": "Segoe UI",
            "Segoe UI Semibold": "Segoe UI Semibold",
        }
    # Floating nav lives in FinanseApp shell (rounded host), not page.navigation_bar.


def apply_theme_from_settings(page: ft.Page, settings: object) -> None:
    """Apply theme + UI style from a settings snapshot."""
    from lib.core.config import DEFAULT_UI_STYLE

    apply_theme(
        page,
        getattr(settings, "theme", None),
        getattr(settings, "ui_style", None) or DEFAULT_UI_STYLE,
    )


def page_gradient(dark: bool) -> ft.LinearGradient:
    """Subtle atmospheric background gradient for shells / lock screen."""
    return get_active_skin().page_gradient(dark=dark)
