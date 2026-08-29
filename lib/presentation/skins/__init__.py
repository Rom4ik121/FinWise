"""Registry of application visual styles (one file per look)."""

from __future__ import annotations

from lib.core.config import DEFAULT_UI_STYLE, KNOWN_UI_STYLES
from lib.presentation.skins._base import UiSkin
from lib.presentation.skins.classic import SKIN as CLASSIC
from lib.presentation.skins.neon import SKIN as NEON

_SKINS: dict[str, UiSkin] = {
    CLASSIC.id: CLASSIC,
    NEON.id: NEON,
}
_ACTIVE = DEFAULT_UI_STYLE


def list_skins() -> list[UiSkin]:
    """Registered styles in display order."""
    return [_SKINS[key] for key in KNOWN_UI_STYLES if key in _SKINS]


def normalize_skin_id(value: str | None) -> str:
    key = (value or DEFAULT_UI_STYLE).strip().lower()
    if key in _SKINS:
        return key
    return DEFAULT_UI_STYLE


def get_skin(skin_id: str | None = None) -> UiSkin:
    return _SKINS[normalize_skin_id(skin_id)]


def get_active_skin() -> UiSkin:
    return get_skin(_ACTIVE)


def set_active_skin(skin_id: str | None) -> UiSkin:
    global _ACTIVE
    _ACTIVE = normalize_skin_id(skin_id)
    return get_skin(_ACTIVE)


__all__ = [
    "UiSkin",
    "CLASSIC",
    "NEON",
    "list_skins",
    "normalize_skin_id",
    "get_skin",
    "get_active_skin",
    "set_active_skin",
]
