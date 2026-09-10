"""Motion tokens, reduced-motion, and haptic cooldown."""

from __future__ import annotations

from lib.presentation.haptics import reset_haptic_gate, should_emit_haptic
from lib.presentation.ui_motion import (
    DUR_FAST,
    DUR_MED,
    DUR_SLOW,
    cache_reduced_motion,
    motion_animation,
    motion_ms,
    prefers_reduced_motion,
    reduce_motion_from_env,
)


def test_motion_durations_are_short() -> None:
    assert 150 <= DUR_FAST <= 180
    assert 180 <= DUR_MED <= 240
    assert 240 <= DUR_SLOW <= 300


def test_motion_ms_zero_when_reduced(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_REDUCE_MOTION", "1")
    assert reduce_motion_from_env() is True
    assert prefers_reduced_motion() is True
    assert motion_ms(220) == 0
    assert motion_animation(220) is None
    monkeypatch.delenv("FINANCE_REDUCE_MOTION", raising=False)
    assert reduce_motion_from_env() is False
    assert motion_ms(220) == 220
    anim = motion_animation(220)
    assert anim is not None
    duration = getattr(anim, "duration", 220)
    ms = getattr(duration, "in_milliseconds", None)
    if ms is None:
        ms = getattr(duration, "milliseconds", duration)
    assert int(ms) == 220


def test_page_cache_reduced_motion() -> None:
    class _Page:
        pass

    page = _Page()
    assert prefers_reduced_motion(page) is False  # type: ignore[arg-type]
    cache_reduced_motion(page, True)  # type: ignore[arg-type]
    assert prefers_reduced_motion(page) is True  # type: ignore[arg-type]


def test_haptic_cooldown_blocks_spam() -> None:
    reset_haptic_gate()
    assert should_emit_haptic("light", now=1.0, last_at=0.0) is True
    assert should_emit_haptic("light", now=1.02, last_at=1.0) is False
    assert should_emit_haptic("light", now=1.10, last_at=1.0) is True
    assert should_emit_haptic("success", now=1.10, last_at=1.0) is False
    assert should_emit_haptic("success", now=1.30, last_at=1.0) is True


def test_skeleton_list_builds() -> None:
    from lib.presentation.widgets.loading import skeleton_list, skeleton_row

    row = skeleton_row()
    assert row is not None
    host = skeleton_list(rows=3)
    assert len(host.controls) == 3
