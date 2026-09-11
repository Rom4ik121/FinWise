"""Motion tokens, reduced-motion, and haptic cooldown."""

from __future__ import annotations

from lib.presentation.haptics import reset_haptic_gate, should_emit_haptic
from lib.presentation.ui_motion import (
    DUR_FAST,
    DUR_MED,
    DUR_SLOW,
    apply_overlay_enter,
    cache_reduced_motion,
    chart_enter,
    motion_animation,
    motion_ms,
    prefers_reduced_motion,
    reduce_motion_from_env,
    wrap_enter,
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


def test_wrap_enter_skips_when_not_playing() -> None:
    import flet as ft

    inner = ft.Container()
    assert wrap_enter(inner, play=False) is inner


def test_wrap_enter_wraps_when_playing() -> None:
    import flet as ft

    inner = ft.Container()
    host = wrap_enter(inner, play=True)
    assert host is not inner
    assert getattr(host, "opacity", 1) == 0


def test_wrap_enter_respects_reduce_motion(monkeypatch) -> None:
    import flet as ft

    monkeypatch.setenv("FINANCE_REDUCE_MOTION", "1")
    inner = ft.Container()
    assert wrap_enter(inner, play=True) is inner
    monkeypatch.delenv("FINANCE_REDUCE_MOTION", raising=False)


def test_chart_enter_plays_once_per_key() -> None:
    import flet as ft

    class _Owner:
        pass

    owner = _Owner()
    first = ft.Text("a")
    second = ft.Text("b")
    wrapped = chart_enter(owner, first, refresh=False, key="pie")
    skipped = chart_enter(owner, second, refresh=False, key="pie")
    refreshed = chart_enter(owner, second, refresh=True, key="pie")
    assert wrapped is not first
    assert skipped is second
    assert refreshed is not second


def test_apply_overlay_enter_stamps_opacity() -> None:
    import flet as ft

    box = ft.Container()
    apply_overlay_enter(box)
    assert box.opacity == 1
    assert box.ignore_interactions is False


def test_overlay_enter_style_web_stays_opaque() -> None:
    from lib.presentation.ui_motion import overlay_enter_style

    class _Page:
        web = True

    style = overlay_enter_style(_Page())  # type: ignore[arg-type]
    assert style["opacity"] == 1
    assert style["ignore_interactions"] is False


def test_overlay_enter_style_desktop_stays_opaque() -> None:
    from lib.presentation.ui_motion import overlay_enter_style

    class _Page:
        web = False
        platform = "windows"

    style = overlay_enter_style(_Page())  # type: ignore[arg-type]
    assert style["opacity"] == 1
    assert style["ignore_interactions"] is False


def test_overlay_enter_style_ios_still_fades() -> None:
    from lib.presentation.ui_motion import overlay_enter_style

    class _Page:
        web = False
        platform = "ios"

    style = overlay_enter_style(_Page())  # type: ignore[arg-type]
    assert style["opacity"] == 0
    assert style["ignore_interactions"] is True


def test_bind_press_skips_tap_down_on_icon_button() -> None:
    import flet as ft

    from lib.presentation.ui_motion import bind_press

    btn = ft.IconButton(icon=ft.Icons.ADD)
    before = getattr(btn, "on_tap_down", None)
    clicked = {"n": 0}
    bind_press(btn, on_click=lambda _e: clicked.__setitem__("n", 1))
    assert getattr(btn, "on_tap_down", None) is before
    btn.on_click(type("E", (), {})())
    assert clicked["n"] == 1


def test_settings_accordion_toggles_without_page() -> None:
    import flet as ft

    from lib.presentation.pages.settings import _settings_section

    section = _settings_section(
        "T",
        ft.Icons.SETTINGS,
        [ft.Text("x")],
        expanded=False,
    )
    apply = (section.data or {}).get("apply")
    body = (section.data or {}).get("body")
    assert callable(apply)
    assert body is not None
    assert body.visible is False
    apply(True)
    assert body.visible is True
    assert body.opacity == 1
    apply(False)
    assert body.visible is False
    assert body.ignore_interactions is True


def test_wrap_enter_skips_fade_on_web() -> None:
    import flet as ft

    from lib.presentation.ui_motion import wrap_enter

    class _Page:
        web = True

    inner = ft.Text("chart")
    wrapped = wrap_enter(inner, _Page())  # type: ignore[arg-type]
    assert wrapped is inner
