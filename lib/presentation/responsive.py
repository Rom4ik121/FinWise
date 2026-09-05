"""Responsive sizing helpers — fonts, tap targets, viewport clamps.

Use these instead of hard-coded pixel widths so UI stays readable from
iPhone SE (~320) through tablets and desktop windows.
"""

from __future__ import annotations

from typing import Any, Optional

import flet as ft

# Material-ish minimum touch target (logical px).
MIN_TAP = 40
# Reference width for typography scale (iPhone 14 / common phone).
_REF_WIDTH = 390.0
# Below this → compact phone layout; at/above → room for denser chrome.
COMPACT_MAX = 420
# Desktop / tablet: center content, optional side breathing room.
WIDE_MIN = 720


def page_width(page: ft.Page | None) -> float:
    """Best-effort viewport width in logical pixels."""
    if page is None:
        return _REF_WIDTH
    raw = getattr(page, "width", None)
    if not raw:
        raw = getattr(getattr(page, "window", None), "width", None)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _REF_WIDTH
    return value if value > 0 else _REF_WIDTH


def page_height(page: ft.Page | None) -> float:
    """Best-effort viewport height in logical pixels."""
    if page is None:
        return 720.0
    raw = getattr(page, "height", None)
    if not raw:
        raw = getattr(getattr(page, "window", None), "height", None)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 720.0
    return value if value > 0 else 720.0


def is_compact(page: ft.Page | None) -> bool:
    """True on phone-narrow viewports (SE / small Android)."""
    return page_width(page) < COMPACT_MAX


def is_wide(page: ft.Page | None) -> bool:
    """True on tablet / desktop-wide windows."""
    return page_width(page) >= WIDE_MIN


def scale_font(
    base: float,
    page: ft.Page | None = None,
    *,
    floor: float = 0.88,
    ceil: float = 1.12,
    minimum: int = 10,
    maximum: int = 36,
) -> int:
    """Scale a base font size with viewport width (clamped).

    Keeps SE readable without blowing up Pro Max / Ultra typography.
    """
    factor = page_width(page) / _REF_WIDTH
    factor = max(floor, min(ceil, factor))
    size = int(round(base * factor))
    return max(minimum, min(maximum, size))


def clamp_content_width(
    page: ft.Page | None,
    *,
    margin: float = 24,
    max_width: float = 720,
) -> float:
    """Usable content width inside horizontal margins (never exceeds max)."""
    usable = max(280.0, page_width(page) - margin * 2)
    return min(usable, max_width)


def form_control_width(page: ft.Page | None, *, preferred: float = 280) -> Optional[float]:
    """Width for centered form controls; ``None`` means expand to parent.

    On narrow phones prefer expand so fields never overflow the card.
    """
    usable = clamp_content_width(page, margin=48, max_width=preferred)
    if page_width(page) < preferred + 64:
        return None
    return usable


def tap_padding(*, horizontal: int = 10, vertical: int = 10) -> ft.Padding:
    """Padding that yields ~40×40 hit areas around 20px icons."""
    return ft.Padding.symmetric(horizontal=horizontal, vertical=vertical)


def tap_button_style(
    *,
    horizontal: int = 10,
    vertical: int = 10,
    radius: int = 12,
) -> ft.ButtonStyle:
    """Shared IconButton / TextButton style for finger-friendly taps."""
    return ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=radius),
        padding=tap_padding(horizontal=horizontal, vertical=vertical),
    )


def tap_icon_button(
    *,
    icon: Any,
    on_click: Any = None,
    icon_size: int = 20,
    icon_color: Any = None,
    tooltip: str | None = None,
    padding: int = 10,
) -> ft.IconButton:
    """IconButton with a guaranteed minimum touch target."""
    return ft.IconButton(
        icon=icon,
        icon_size=icon_size,
        icon_color=icon_color,
        tooltip=tooltip,
        on_click=on_click,
        style=tap_button_style(horizontal=padding, vertical=padding),
    )


def calendar_cell_size(page: ft.Page | None = None) -> int:
    """Day-cell edge length — at least MIN_TAP on phones."""
    # 7 cells + gaps must fit; on SE (~320-48 pad) ≈ 38px.
    usable = clamp_content_width(page, margin=32, max_width=420)
    cell = int((usable - 12) / 7)
    return max(MIN_TAP, min(48, cell))


def compact_chart_size(page: ft.Page | None = None) -> tuple[int, int]:
    """Dashboard / hero sparkline dimensions from viewport."""
    w = page_width(page)
    h = page_height(page)
    inset = 28 if w < 420 else 40
    width = max(240, min(int(w - inset), 860))
    # Hero charts stay shorter than full analytics plots.
    height = max(120, min(168, int(h * 0.18)))
    if w < 360:
        height = max(112, height - 8)
    return width, height
