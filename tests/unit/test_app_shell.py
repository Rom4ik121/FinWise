"""Shared tab shell: Column nav on narrow, no AnimatedSwitcher fade."""

from __future__ import annotations

import flet as ft

from lib.presentation.app import FinanseApp
from lib.presentation.responsive import uses_column_nav_shell


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


def test_uses_column_nav_shell_at_phone_widths() -> None:
    assert uses_column_nav_shell(_FakePage(320)) is True  # type: ignore[arg-type]
    assert uses_column_nav_shell(_FakePage(375)) is True  # type: ignore[arg-type]
    assert uses_column_nav_shell(_FakePage(420)) is True  # type: ignore[arg-type]
    assert uses_column_nav_shell(_FakePage(421)) is False  # type: ignore[arg-type]
    assert uses_column_nav_shell(_FakePage(1280)) is False  # type: ignore[arg-type]


def test_narrow_shell_is_column_not_stack() -> None:
    """≤420px Windows: Column([expand body, nav]) so expand=True actually flexes."""
    page = _FakePage(375, 667)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    pane = app._content_pane
    nav = app._nav_overlay
    assert app._column_shell_active is True
    assert app._shell.content is app._shell_column
    assert app._shell_column.controls == [pane, nav]
    assert app._shell_stack.controls == []
    assert pane.expand is True
    assert pane.left is None and pane.top is None
    assert pane.right is None and pane.bottom is None
    assert pane.opacity == 1
    assert pane.ignore_interactions is False
    assert not _positioned(nav)
    assert nav.expand is False
    assert nav.height is not None
    assert float(nav.height) < 667 * 0.18
    assert isinstance(app._content, ft.Container)
    assert not isinstance(app._content, ft.AnimatedSwitcher)
    assert app._content.expand is True
    assert app._content.opacity == 1
    assert app._content.alignment == ft.Alignment.TOP_CENTER
    assert app._stage.width == 375
    assert app._stage.height == 667


def test_wide_shell_keeps_stack_overlay() -> None:
    page = _FakePage(1280, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    pane = app._content_pane
    nav = app._nav_overlay
    assert app._column_shell_active is False
    assert app._shell.content is app._shell_stack
    assert app._shell_stack.controls == [pane, nav]
    assert pane.expand is True
    assert pane.left is None
    assert nav.left == 0 and nav.right == 0 and nav.bottom == 0
    assert float(nav.height) < 800 * 0.18
    assert not isinstance(app._content, ft.AnimatedSwitcher)


def test_resize_wide_to_narrow_switches_to_column() -> None:
    page = _FakePage(1280, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    assert app._column_shell_active is False
    page.width = 360
    page.height = 640
    page.window.width = 360
    page.window.height = 640
    app._apply_nav_metrics()
    app._apply_shell_mode()
    app._sync_stage_size()
    assert app._column_shell_active is True
    assert app._shell.content is app._shell_column
    assert app._shell_column.controls == [app._content_pane, app._nav_overlay]
    assert not _positioned(app._nav_overlay)
    assert app._stage.width == 360
    assert app._content_pane.expand is True
    pad = app._content_pane.padding
    assert float(getattr(pad, "left", 0) or 0) == 0
    assert app._content_pane.clip_behavior == ft.ClipBehavior.NONE
    assert not isinstance(app._shell, ft.SafeArea)


def test_desktop_gutters_move_to_shell_and_clear_on_squeeze() -> None:
    """Stale page_frame 200px inset must not stay when the window is squeezed."""
    page = _FakePage(1400, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    pad = app._content_pane.padding
    assert float(getattr(pad, "left", 0) or 0) >= 180
    assert not isinstance(app._shell, ft.SafeArea)
    page.width = 320
    page.height = 667
    page.window.width = 320
    page.window.height = 667
    app._apply_nav_metrics()
    app._apply_shell_mode()
    app._sync_stage_size()
    pad = app._content_pane.padding
    assert float(getattr(pad, "left", 0) or 0) == 0
    assert float(getattr(pad, "right", 0) or 0) == 0
    assert app._content_pane.expand is True
    assert app._column_shell_active is True


def test_resize_narrow_to_wide_restores_stack() -> None:
    page = _FakePage(375, 667)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    page.width = 1100
    page.height = 800
    page.window.width = 1100
    page.window.height = 800
    app._apply_nav_metrics()
    app._apply_shell_mode()
    app._sync_stage_size()
    assert app._column_shell_active is False
    assert app._shell.content is app._shell_stack
    assert app._nav_overlay.bottom == 0


def test_resize_event_notes_viewport_before_inset_math() -> None:
    """Event size wins when both page.width and window.width stay at 1266."""
    from lib.presentation.responsive import page_width

    page = _FakePage(1266, 800)
    app = FinanseApp(page, object())  # type: ignore[arg-type]
    app._render = lambda **_kw: None  # type: ignore[method-assign]
    app._forget_cached_views = lambda: None  # type: ignore[method-assign]
    app._install_resize_handler()
    page.on_resize(type("Resize", (), {"width": 312, "height": 640})())
    assert page_width(page) == 312  # type: ignore[arg-type]
    assert app._column_shell_active is True
    pad = app._content_pane.padding
    assert float(getattr(pad, "left", 0) or 0) == 0
    assert float(getattr(pad, "right", 0) or 0) == 0
