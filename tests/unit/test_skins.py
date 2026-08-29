"""Visual styles: classic default plus neon, each in its own module."""

from __future__ import annotations

from lib.core.config import DEFAULT_UI_STYLE
from lib.domain.entities.settings import AppSettings
from lib.presentation.skins import (
    get_active_skin,
    get_skin,
    list_skins,
    normalize_skin_id,
    set_active_skin,
)


def test_classic_is_default() -> None:
    assert normalize_skin_id(None) == DEFAULT_UI_STYLE
    assert normalize_skin_id("unknown") == "classic"
    assert get_skin().id == "classic"


def test_neon_skin_is_registered() -> None:
    ids = {skin.id for skin in list_skins()}
    assert ids == {"classic", "neon"}
    neon = get_skin("neon")
    assert neon.dark_primary == "#00FF99"
    assert neon.dark_expense == "#FF4D4D"
    assert neon.chart_kind == "glow"
    assert neon.accent_fill == "solid"
    assert neon.card_radius < get_skin("classic").card_radius
    assert neon.badge_fg(dark=True) == neon.dark_on_primary
    assert neon.income_hex(dark=True) == "#00FF99"
    assert neon.glass is True
    assert neon.backdrop_blur() is not None
    assert get_skin("classic").glass is False


def test_set_active_skin_switches_palette() -> None:
    previous = get_active_skin().id
    try:
        set_active_skin("neon")
        assert get_active_skin().id == "neon"
        assert get_active_skin().dark_bg == "#0B0E11"
    finally:
        set_active_skin(previous)


def test_settings_unknown_style_falls_back() -> None:
    settings = AppSettings(ui_style="hologram")
    assert settings.ui_style == "classic"
    settings = AppSettings(ui_style="NEON")
    assert settings.ui_style == "neon"


def test_theme_hides_scrollbar_thumb() -> None:
    import flet as ft

    from lib.presentation.theme import build_theme

    theme = build_theme(dark=True)
    bar = theme.scrollbar_theme
    assert bar is not None
    assert bar.thickness == 0
    assert bar.thumb_visibility is False
    assert bar.thumb_color == ft.Colors.TRANSPARENT
