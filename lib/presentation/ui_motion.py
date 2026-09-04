"""UI motion helpers: refresh animation flag and list scroll memory."""

from __future__ import annotations

import asyncio
import contextvars
from contextlib import contextmanager
from typing import Iterator, Sequence

import flet as ft

from lib.presentation.utils import run_async, safe_update

_ANIMATE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "finwise_ui_animate", default=False
)
_SCROLL_ATTR = "_fw_scroll"
_RESTORING_ATTR = "_fw_restoring"


def is_ui_animating() -> bool:
    """True while a page is rebuilding for an entrance animation."""
    return bool(_ANIMATE.get())


def set_ui_animating(enabled: bool) -> contextvars.Token:
    """Set the animation flag for this async task. Restore with the token."""
    return _ANIMATE.set(bool(enabled))


def reset_ui_animating(token: contextvars.Token) -> None:
    """Undo :func:`set_ui_animating`."""
    _ANIMATE.reset(token)


@contextmanager
def ui_animation(enabled: bool) -> Iterator[None]:
    """Mark widgets built inside so bars/rings start empty and play after mount."""
    token = _ANIMATE.set(bool(enabled))
    try:
        yield
    finally:
        _ANIMATE.reset(token)


def snapshot_scroll(control: ft.Control) -> float:
    """Last reported ListView offset, or 0."""
    try:
        return float(getattr(control, _SCROLL_ATTR, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def remember_scroll(control: ft.ListView) -> ft.ListView:
    """Record vertical (or horizontal) pixels so reload can restore them."""
    if getattr(control, "_fw_scroll_bound", False):
        return control
    setattr(control, "_fw_scroll_bound", True)
    setattr(control, _SCROLL_ATTR, 0.0)

    def _on_scroll(e: ft.OnScrollEvent) -> None:
        if getattr(control, _RESTORING_ATTR, False):
            return
        try:
            setattr(control, _SCROLL_ATTR, float(getattr(e, "pixels", 0) or 0))
        except (TypeError, ValueError):
            pass

    control.on_scroll = _on_scroll
    return control


async def restore_scroll(control: ft.Control, offset: float) -> None:
    """Jump a ListView back after its children were replaced."""
    target = float(offset or 0)
    if target <= 8:
        return
    setattr(control, _RESTORING_ATTR, True)
    try:
        for delay in (0.03, 0.1, 0.22):
            await asyncio.sleep(delay)
            try:
                await control.scroll_to(offset=target, duration=0)
                setattr(control, _SCROLL_ATTR, target)
                return
            except Exception:  # noqa: BLE001
                continue
    finally:
        setattr(control, _RESTORING_ATTR, False)


def replace_controls(
    host: ft.Control,
    controls: Sequence[ft.Control],
    page: ft.Page | None,
) -> None:
    """Assign ``host.controls`` and keep the previous scroll offset."""
    offset = snapshot_scroll(host)
    setattr(host, _RESTORING_ATTR, True)
    host.controls = list(controls)
    safe_update(host)
    if page is not None and offset > 8:
        run_async(page, restore_scroll, host, offset)
    else:
        setattr(host, _RESTORING_ATTR, False)
