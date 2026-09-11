"""Responsive sizing helpers — fonts, tap targets, viewport clamps.

Use these instead of hard-coded pixel widths so UI stays readable from
iPhone SE (~320) through tablets and desktop windows.
"""

from __future__ import annotations

from typing import Any, Optional

import flet as ft

# Apple HIG / Material minimum touch target (logical px).
MIN_TAP = 44
# Reference width for typography scale (iPhone 14 / common phone).
_REF_WIDTH = 390.0
# Below this → compact phone layout; at/above → room for denser chrome.
COMPACT_MAX = 420
# Desktop / tablet: center content, optional side breathing room.
WIDE_MIN = 720
# Extra-small phones (SE / iPhone 12–14 logical 375 / compact Android).
# 375–390 must use the compact nav so four tab labels stay on-screen.
NARROW_MAX = 400
# Large tablet / desktop split for card grids.
DESKTOP_MIN = 1024
# Centered readable measure on large windows (not a skinny phone column,
# not a stretched 1600px slab). Wide enough for a 3-up 280px card grid.
SHELL_MAX_LG = 840
SHELL_MAX_XL = 960
# Grouped floating tab bar on large windows (mobile chrome, not a spread).
NAV_BAR_MAX_LG = 520
NAV_BAR_MAX_XL = 560
# ListView clearance under the floating nav. The home indicator / notch /
# Dynamic Island are Flutter SafeArea's job (see wrap_safe_area), not a
# per-device pixel offset.
LIST_NAV_CLEARANCE = 104
# Floor applied *with* MediaQuery padding (the greater of the two).
# Not a notch or island height — those come from the OS.
SAFE_MIN_TOP = 8
SAFE_MIN_BOTTOM = 4

Breakpoint = str
BP_XS = "xs"
BP_SM = "sm"
BP_MD = "md"
BP_LG = "lg"
BP_XL = "xl"


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


def uses_column_nav_shell(page: ft.Page | None = None) -> bool:
    """True when the tab bar is a Column sibling, not a Stack overlay.

    Flet Windows desktop blanks every tab body when the shell is a Stack
    (nav still paints). At ≤420px use ``Column([content expand, nav])``.
    """
    return page_width(page) <= COMPACT_MAX


def is_wide(page: ft.Page | None) -> bool:
    """True on tablet / desktop-wide windows."""
    return page_width(page) >= WIDE_MIN


def is_narrow(page: ft.Page | None) -> bool:
    """True on extra-small phones where labels must shrink."""
    return page_width(page) < NARROW_MAX


def breakpoint(page: ft.Page | None) -> Breakpoint:
    """Named viewport band: xs <400, sm <420, md <720, lg <1024, else xl."""
    width = page_width(page)
    if width < NARROW_MAX:
        return BP_XS
    if width < COMPACT_MAX:
        return BP_SM
    if width < WIDE_MIN:
        return BP_MD
    if width < DESKTOP_MIN:
        return BP_LG
    return BP_XL


def scale_factor(
    page: ft.Page | None = None,
    *,
    floor: float = 0.88,
    ceil: float = 1.22,
) -> float:
    """Width-based multiplier around the 390px reference phone."""
    factor = page_width(page) / _REF_WIDTH
    return max(floor, min(ceil, factor))


def scale_size(
    base: float,
    page: ft.Page | None = None,
    *,
    floor: float = 0.88,
    ceil: float = 1.22,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Scale padding, icon, and card metrics with the viewport."""
    value = int(round(float(base) * scale_factor(page, floor=floor, ceil=ceil)))
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def scale_space(base: float, page: ft.Page | None = None) -> int:
    """Spacing / gap that stays tight on phones and roomy on desktop."""
    return scale_size(base, page, floor=0.90, ceil=1.18, minimum=4, maximum=28)


def shell_max_width(page: ft.Page | None = None) -> float | None:
    """Inner content cap on large windows; ``None`` means fill the gutters."""
    bp = breakpoint(page)
    if bp == BP_LG:
        return float(SHELL_MAX_LG)
    if bp == BP_XL:
        return float(SHELL_MAX_XL)
    return None


def content_inset(page: ft.Page | None = None) -> int:
    """Horizontal page gutter (list / dashboard body).

    On lg/xl the gutter also *centers* the shell so cards are not a 1600px
    stretch and not a 400px island in empty space.
    """
    bp = breakpoint(page)
    width = page_width(page)
    if bp == BP_XS:
        return 8
    if bp in (BP_SM, BP_MD):
        return 12
    cap = shell_max_width(page) or float(SHELL_MAX_LG)
    return int(max(16.0, (width - cap) / 2.0))


def layout_width(page: ft.Page | None = None) -> float:
    """Body width after gutters (capped on tablet / desktop)."""
    width = page_width(page)
    usable = max(0.0, width - content_inset(page) * 2)
    cap = shell_max_width(page)
    target = min(usable, cap) if cap is not None else usable
    if target <= 0:
        return width
    return max(min(240.0, width), target)


def card_padding(page: ft.Page | None = None, *, hero: bool = False) -> int:
    """Inner padding for catalog / KPI cards."""
    base = 14 if hero else 12
    return scale_size(base, page, floor=0.90, ceil=1.15, minimum=8, maximum=20)


# Comfortable inner width of a full-bleed phone card (390 − gutters − pad).
_REF_BLOCK = 340.0
# Comfortable inner width of one KPI cell in a 2-up row.
_REF_KPI = 150.0


def content_column_width(page: ft.Page | None = None) -> float:
    """List/body width inside page gutters (not the raw window)."""
    return layout_width(page)


def block_inner_width(
    page: ft.Page | None = None,
    *,
    columns: int = 1,
    padding: int | None = None,
    gap: float | None = None,
) -> float:
    """Estimated inner width of a card sitting in a ``columns``-wide row."""
    usable = content_column_width(page)
    pad = float(padding if padding is not None else card_padding(page))
    space = float(gap if gap is not None else scale_space(8, page))
    cols = max(1, int(columns))
    cell = (usable - space * (cols - 1)) / cols
    return max(96.0, cell - pad * 2)


def fit_factor(
    page: ft.Page | None = None,
    *,
    columns: int = 1,
    ref: float = _REF_BLOCK,
    floor: float = 0.72,
    ceil: float = 1.10,
    padding: int | None = None,
) -> float:
    """Scale relative to the card inner width, not the full viewport."""
    inner = block_inner_width(page, columns=columns, padding=padding)
    return max(floor, min(ceil, inner / max(ref, 1.0)))


def fit_size(
    base: float,
    page: ft.Page | None = None,
    *,
    columns: int = 1,
    ref: float = _REF_BLOCK,
    floor: float = 0.72,
    ceil: float = 1.10,
    minimum: int | None = None,
    maximum: int | None = None,
    padding: int | None = None,
) -> int:
    """Padding / icon / ring size that shrinks with the hosting card."""
    value = int(
        round(
            float(base)
            * fit_factor(
                page,
                columns=columns,
                ref=ref,
                floor=floor,
                ceil=ceil,
                padding=padding,
            )
        )
    )
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def fit_font(
    base: float,
    page: ft.Page | None = None,
    *,
    columns: int = 1,
    ref: float = _REF_BLOCK,
    floor: float = 0.72,
    ceil: float = 1.10,
    minimum: int = 9,
    maximum: int = 28,
    padding: int | None = None,
) -> int:
    """Type size that stays readable inside the hosting card."""
    return fit_size(
        base,
        page,
        columns=columns,
        ref=ref,
        floor=floor,
        ceil=ceil,
        minimum=minimum,
        maximum=maximum,
        padding=padding,
    )


def kpi_card_metrics(
    page: ft.Page | None = None,
    *,
    columns: int = 2,
) -> dict[str, int]:
    """KPI / today / analytics cells that share a row."""
    cols = max(1, columns)
    return {
        "title": fit_font(
            11, page, columns=cols, ref=_REF_KPI, minimum=9, maximum=13
        ),
        "value": fit_font(
            13, page, columns=cols, ref=_REF_KPI, minimum=10, maximum=18
        ),
        "icon": fit_size(
            28, page, columns=cols, ref=_REF_KPI, minimum=22, maximum=34
        ),
        "glyph": fit_size(
            15, page, columns=cols, ref=_REF_KPI, minimum=12, maximum=18
        ),
        "padding": fit_size(
            10, page, columns=cols, ref=_REF_KPI, minimum=6, maximum=14
        ),
        "gap": fit_size(
            8, page, columns=cols, ref=_REF_KPI, minimum=4, maximum=10
        ),
    }


def hero_block_metrics(page: ft.Page | None = None) -> dict[str, int]:
    """Full-width hero: ring + amount + chips."""
    inner = block_inner_width(page, columns=1)
    ring = int(max(56, min(88, inner * 0.26)))
    ring = min(ring, int(inner * 0.34))
    return {
        "ring": ring,
        "title": fit_font(12, page, minimum=10, maximum=14),
        "amount": fit_font(22, page, minimum=16, maximum=24),
        "meta": fit_font(13, page, minimum=10, maximum=15),
        "chip": fit_font(11, page, minimum=9, maximum=12),
        "chip_value": fit_font(13, page, minimum=10, maximum=15),
        "padding": card_padding(page),
        "gap": scale_space(10, page),
        "row_gap": scale_space(12, page),
    }


def tile_ring_metrics(page: ft.Page | None = None) -> dict[str, int]:
    """List/analytics row with a small ring beside text."""
    inner = block_inner_width(page, columns=1)
    ring = int(max(40, min(52, inner * 0.15)))
    return {
        "ring": ring,
        "title": fit_font(14, page, minimum=12, maximum=16),
        "amount": fit_font(14, page, minimum=11, maximum=16),
        "meta": fit_font(12, page, minimum=10, maximum=14),
        "icon": fit_size(28, page, minimum=24, maximum=34),
        "glyph": fit_size(14, page, minimum=12, maximum=16),
        "padding": max(8, card_padding(page) - 2),
        "gap": scale_space(8, page),
    }


def ring_label_font(size: int, label: str) -> int:
    """Percent (or short word) that stays inside a ProgressRing hole."""
    stroke = max(4, int(size) // 10)
    hole = max(12, int(size) - stroke * 2)
    chars = max(1, len(label))
    if chars <= 3:
        return max(8, min(int(size * 0.24), int(hole * 0.38)))
    return max(7, min(int(size * 0.15), int(hole * 0.26)))


def donut_center_metrics(canvas: int) -> dict[str, int]:
    """Three-line stack (percent / amount / caption) inside a donut hole.

    ``canvas`` is the full donut square; the hole is ~58% of that. Percent
    must stay clearly smaller than the ring — not a ProgressRing-sized glyph.
    """
    size = max(96, int(canvas))
    return {
        "percent": max(11, min(15, int(size * 0.072))),
        "amount": max(8, min(10, int(size * 0.045))),
        "caption": max(8, min(9, int(size * 0.038))),
        "spacing": 1,
    }


def grid_columns(
    page: ft.Page | None = None,
    *,
    min_card: float = 280,
    maximum: int = 3,
) -> int:
    """How many equal-width cards fit in the *layout* column (not the window)."""
    usable = layout_width(page)
    cols = max(1, int(usable // min_card))
    return min(maximum, cols)


def tx_tile_metrics(page: ft.Page | None = None) -> dict[str, int]:
    """Transaction row: height, amount column, icon, type sizes."""
    return {
        "height": scale_size(56, page, floor=0.92, ceil=1.18, minimum=52, maximum=72),
        "amount_width": scale_size(
            88, page, floor=0.90, ceil=1.25, minimum=72, maximum=128
        ),
        "icon": scale_size(36, page, floor=0.90, ceil=1.18, minimum=32, maximum=44),
        "title": fit_font(13, page, minimum=11, maximum=16),
        "subtitle": fit_font(10, page, minimum=9, maximum=13),
        "amount": fit_font(12, page, minimum=11, maximum=16),
    }


def entity_card_metrics(page: ft.Page | None = None) -> dict[str, int]:
    """Shared metrics for goal / debt / subscription / budget catalog cards."""
    cols = grid_columns(page, min_card=280, maximum=2)
    return {
        "icon": fit_size(36, page, columns=cols, minimum=30, maximum=44),
        "glyph": fit_size(18, page, columns=cols, minimum=13, maximum=22),
        "title": fit_font(16, page, columns=cols, minimum=12, maximum=20),
        "amount": fit_font(18, page, columns=cols, minimum=13, maximum=24),
        "meta": fit_font(12, page, columns=cols, minimum=10, maximum=15),
        "chip": fit_font(11, page, columns=cols, minimum=9, maximum=13),
        "padding": card_padding(page),
        "gap": scale_space(8, page),
        "ring": fit_size(52, page, columns=cols, minimum=44, maximum=64),
        "ring_tile": fit_size(72, page, columns=cols, minimum=60, maximum=88),
    }


def swipe_action_strip_width(
    page: ft.Page | None = None,
    *,
    buttons: int = 2,
) -> float:
    """Width (px) for Edit/Delete (and optional Sync) reveal strip."""
    w = page_width(page)
    # Compact phones: icon-only-ish buttons; wider screens: icon+label.
    per = 52.0 if w < 360 else (64.0 if w < COMPACT_MAX else 72.0)
    return min(w * 0.55, max(96.0, per * max(1, buttons) + 8.0))


def swipe_reveal_offset(
    page: ft.Page | None = None,
    *,
    strip_width: float | None = None,
    buttons: int = 2,
) -> float:
    """Fraction of card width to slide left so the action strip is fully visible."""
    w = page_width(page)
    strip = strip_width if strip_width is not None else swipe_action_strip_width(
        page, buttons=buttons
    )
    # Slightly more than strip so buttons aren't clipped at the edge.
    return min(0.92, max(0.32, (strip + 12.0) / max(w, 280.0)))


def scale_font(
    base: float,
    page: ft.Page | None = None,
    *,
    floor: float = 0.88,
    ceil: float = 1.22,
    minimum: int = 10,
    maximum: int = 40,
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
    """Usable content width inside horizontal margins (never exceeds viewport)."""
    width = page_width(page)
    usable = max(0.0, width - float(margin) * 2)
    if usable <= 0:
        return min(width, float(max_width))
    return min(usable, float(max_width))


def form_shell_inset(page: ft.Page | None = None) -> int:
    """Horizontal padding around a fullscreen form / picker sheet."""
    bp = breakpoint(page)
    if bp == BP_XS:
        return 10
    if bp == BP_SM:
        return 12
    return 16


def nav_bar_max_width(page: ft.Page | None = None) -> float | None:
    """Cap the floating tab bar so four items stay grouped on large windows."""
    bp = breakpoint(page)
    if bp == BP_LG:
        return float(NAV_BAR_MAX_LG)
    if bp == BP_XL:
        return float(NAV_BAR_MAX_XL)
    return None


def nav_chrome_metrics(page: ft.Page | None = None) -> dict[str, int]:
    """Floating bottom-nav sizes that fit 320px without clipping labels."""
    bp = breakpoint(page)
    cap = nav_bar_max_width(page)
    width = page_width(page)
    if cap is not None:
        margin_h = int(max(12.0, (width - cap) / 2.0))
    elif bp == BP_XS:
        margin_h = 6
    else:
        margin_h = 10
    if bp == BP_XS:
        return {
            "margin_h": margin_h,
            "margin_bottom": 6,
            "margin_top": 4,
            "bar_h": 56,
            "pill_w": 36,
            "pill_h": 26,
            "label": 9,
            "icon": 20,
            "item_pad_h": 1,
            "item_pad_v": 2,
        }
    return {
        "margin_h": margin_h,
        "margin_bottom": 8 if cap is not None else 6,
        "margin_top": 4,
        "bar_h": 54,
        "pill_w": 46,
        "pill_h": 30,
        "label": 11,
        "icon": 22,
        "item_pad_h": 4,
        "item_pad_v": 4,
    }


def nav_overlay_height(page: ft.Page | None = None) -> int:
    """Height of the bottom-nav overlay so it does not steal taps above the bar.

    Includes host padding (4+4) and a few extra pixels so labels are not
    HARD_EDGE-clipped; keep this well under the dashboard tap zone. Cap
    against the window so a short+narrow resize cannot cover the body.
    """
    m = nav_chrome_metrics(page)
    raw = int(m["bar_h"] + m["margin_top"] + m["margin_bottom"] + 16)
    cap = max(56, int(page_height(page) * 0.18))
    return min(raw, cap)


def should_rebuild_layout(
    *,
    old_bp: str | None,
    new_bp: str,
    old_width: float,
    new_width: float,
) -> bool:
    """Whether a window resize must remount cached pages.

    A 64px slack is fine on tablet/desktop. On xs (320–390) even 15px
    (390 fallback → 375 viewport) must rebuild so Home/nav/charts refit.
    """
    if old_bp != new_bp:
        return True
    delta = abs(float(new_width) - float(old_width))
    if new_bp == BP_XS or old_bp == BP_XS:
        return delta >= 8
    return delta >= 64


def list_nav_padding() -> ft.Padding:
    """Bottom inset so ListView rows clear the floating nav.

    Home-indicator / gesture-bar inset is applied by :func:`wrap_safe_area`
    on the shell, not by this padding.
    """
    return ft.Padding.only(bottom=LIST_NAV_CLEARANCE)


def safe_area_minimum(*, top: bool = True, bottom: bool = True) -> ft.Padding:
    """Device-agnostic floor; Flutter still adds the real cutout padding."""
    return ft.Padding.only(
        top=SAFE_MIN_TOP if top else 0,
        bottom=SAFE_MIN_BOTTOM if bottom else 0,
        left=0,
        right=0,
    )


def wrap_safe_area(
    content: ft.Control,
    *,
    top: bool = True,
    bottom: bool = True,
    left: bool = True,
    right: bool = True,
    expand: bool = True,
    minimum: ft.Padding | int | float | None = None,
) -> ft.SafeArea:
    """Inset ``content`` past notch, Dynamic Island, home indicator, and sides.

    Uses Flutter ``SafeArea`` (MediaQuery padding / viewPadding) so SE-with-home
    button, notched X-class phones, Dynamic Island, and landscape all work
    without hard-coded island heights. ``minimum`` is a floor, never a
    substitute for the OS inset.

    Nested SafeAreas do not double the cutout (Flutter consumes padding).
    Pass ``minimum=0`` when this wrapper sits *inside* another SafeArea
    that already applied :func:`safe_area_minimum`.

    ``maintain_bottom_view_padding`` stays on whenever the bottom inset is
    honored so the home indicator does not collapse under the keyboard.
    """
    if minimum is None:
        minimum = safe_area_minimum(top=top, bottom=bottom)
    return ft.SafeArea(
        content=content,
        expand=expand,
        avoid_intrusions_top=top,
        avoid_intrusions_bottom=bottom,
        avoid_intrusions_left=left,
        avoid_intrusions_right=right,
        maintain_bottom_view_padding=bottom,
        minimum_padding=minimum,
    )


def header_title_size(page: ft.Page | None = None, *, base: float = 22) -> int:
    """Page-title size that still ellipsizes beside 44px header actions."""
    if is_narrow(page):
        return scale_font(base, page, minimum=16, maximum=22)
    return scale_font(base, page, minimum=18, maximum=28)


def form_control_width(page: ft.Page | None, *, preferred: float = 280) -> Optional[float]:
    """Width for centered form controls; ``None`` means expand to parent.

    On narrow phones prefer expand so fields never overflow the card.
    """
    usable = clamp_content_width(page, margin=48, max_width=preferred)
    if page_width(page) < preferred + 64:
        return None
    return usable


def tap_padding(*, horizontal: int = 12, vertical: int = 12) -> ft.Padding:
    """Padding that yields ~44×44 hit areas around 20px icons."""
    return ft.Padding.symmetric(horizontal=horizontal, vertical=vertical)


def tap_button_style(
    *,
    horizontal: int = 12,
    vertical: int = 12,
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
    padding: int = 12,
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


def calendar_day_width(page: ft.Page | None = None) -> int:
    """Width of one of 7 weekday columns so Sunday is never clipped."""
    inner = max(240.0, page_width(page) - 56)
    return max(32, int((inner - 24) / 7))


def calendar_cell_size(page: ft.Page | None = None) -> int:
    """Day-cell HEIGHT — at least MIN_TAP; width is ``calendar_day_width``."""
    return max(MIN_TAP, min(52, calendar_day_width(page) + 8))


def compact_chart_size(page: ft.Page | None = None) -> tuple[int, int]:
    """Dashboard / hero sparkline — sized to the hero card, not the window."""
    pad = card_padding(page, hero=True)
    cap = max(1, int(layout_width(page)))
    inner = int(block_inner_width(page, columns=1, padding=pad))
    width = max(1, min(inner, cap))
    h = page_height(page)
    height = max(104, min(148, int(h * 0.16)))
    if page_width(page) < NARROW_MAX:
        height = max(100, height - 8)
    return width, height
