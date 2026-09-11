"""Shared tab shell: body must paint on narrow (~375) and wide windows."""

from __future__ import annotations

import flet as ft

from lib.presentation.app import FinanseApp


class _FakeWindow:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.min_width = 320
        self.min_height = 560


class _FakePage:
    def __init__(self, width: float, height: float = 780) -> None:
        self.width = width
        self.height = height
        self.window = _FakeWindow(width, height)
        self.web = False
        self.platform = "windows"
        self.overlay: list = []
        self.controls: list = []
        self.padding = 0
        self.on_resize = None

    def update(self) -> None:
        return None

    def add(self, control: object) -> None:
        self.controls.append(control)


def _positioned(control: ft.Control) -> bool:
    return any(
        getattr(control, attr, None) is not None
        for attr in ("left", "top", "right", "bottom")
    )


def _duration_ms(value: object) -> int:
    if value is None:
        return 0
    ms = getattr(value, "in_milliseconds", None)
    if ms is None:
        ms = getattr(value, "milliseconds", value)
    try:
        return int(ms)
    except (TypeError, ValueError):
        return int(getattr(value, "microseconds", 0) or 0) // 1000


def test_narrow_shell_body_is_not_positioned() -> None:
    """375px Windows: nav overlay stays capped; body is a real expanding child."""
    page = _FakePage(375, 667)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    pane = app._content_pane
    overlay = app._nav_overlay
    stack = app._shell_stack
    assert pane.left is None
    assert pane.top is None
    assert pane.right is None
    assert pane.bottom is None
    assert pane.expand is True
    assert pane.opacity == 1
    assert pane.ignore_interactions is False
    assert pane.clip_behavior == ft.ClipBehavior.HARD_EDGE
    assert _positioned(overlay)
    assert overlay.bottom == 0
    assert overlay.height is not None
    assert 56 <= float(overlay.height) < 667 * 0.18
    assert stack.fit == ft.StackFit.EXPAND
    assert stack.controls[0] is pane
    assert stack.controls[1] is overlay
    assert app._stage.expand is True
    assert app._stage.width == 375
    assert app._stage.height == 667
    assert app._content.expand is True
    assert _duration_ms(app._content.duration) == 220


def test_wide_shell_uses_same_body_contract() -> None:
    page = _FakePage(1280, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    pane = app._content_pane
    assert pane.left is None and pane.right is None
    assert pane.expand is True
    assert app._stage.width == 1280
    assert float(app._nav_overlay.height) < 800 * 0.18


def test_narrow_resize_keeps_finite_stage_and_capped_overlay() -> None:
    page = _FakePage(1280, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    page.width = 360
    page.height = 640
    page.window.width = 360
    page.window.height = 640
    app._apply_nav_metrics()
    app._sync_stage_size()
    assert app._stage.width == 360
    assert app._stage.height == 640
    assert app._content_pane.left is None
    assert float(app._nav_overlay.height) < 640 * 0.18
    assert float(app._nav_overlay.height) < 96
