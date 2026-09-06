"""Unit tests for responsive sizing helpers."""

from __future__ import annotations

from lib.presentation.responsive import (
    MIN_TAP,
    calendar_cell_size,
    clamp_content_width,
    compact_chart_size,
    form_control_width,
    is_compact,
    is_wide,
    scale_font,
    swipe_action_strip_width,
    swipe_reveal_offset,
)


class _FakePage:
    def __init__(self, width: float, height: float = 780) -> None:
        self.width = width
        self.height = height
        self.window = type("W", (), {"width": width, "height": height})()


def test_scale_font_clamped_on_se_and_pro_max() -> None:
    se = scale_font(16, _FakePage(320))  # type: ignore[arg-type]
    wide = scale_font(16, _FakePage(430))  # type: ignore[arg-type]
    assert se <= 16
    assert wide >= 16
    assert se >= 10
    assert wide <= 20


def test_compact_and_wide_breakpoints() -> None:
    assert is_compact(_FakePage(360))  # type: ignore[arg-type]
    assert not is_compact(_FakePage(480))  # type: ignore[arg-type]
    assert is_wide(_FakePage(800))  # type: ignore[arg-type]
    assert not is_wide(_FakePage(600))  # type: ignore[arg-type]


def test_form_and_calendar_fit_narrow() -> None:
    se = _FakePage(320)  # type: ignore[arg-type]
    assert form_control_width(se) is None  # type: ignore[arg-type]
    assert clamp_content_width(se, margin=24, max_width=400) <= 320  # type: ignore[arg-type]
    assert calendar_cell_size(se) >= MIN_TAP  # type: ignore[arg-type]
    w, h = compact_chart_size(se)  # type: ignore[arg-type]
    assert w <= 320
    assert 100 <= h <= 180


def test_swipe_strip_shrinks_on_narrow_phones() -> None:
    narrow = swipe_action_strip_width(_FakePage(320), buttons=2)  # type: ignore[arg-type]
    wide = swipe_action_strip_width(_FakePage(430), buttons=2)  # type: ignore[arg-type]
    assert narrow <= wide
    assert narrow >= 96
    frac = swipe_reveal_offset(_FakePage(320), strip_width=narrow, buttons=2)  # type: ignore[arg-type]
    assert 0.32 <= frac <= 0.92
    # Revealed width roughly covers the strip.
    assert frac * 320 >= narrow * 0.85
