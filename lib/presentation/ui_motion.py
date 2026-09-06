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
_RESTORE_GEN = "_fw_restore_gen"


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
    setattr(control, _RESTORE_GEN, 0)

    def _on_scroll(e: ft.OnScrollEvent) -> None:
        if getattr(control, _RESTORING_ATTR, False):
            return
        try:
            px = float(getattr(e, "pixels", 0) or 0)
        except (TypeError, ValueError):
            return
        # Ignore tiny noise / rubber-band that causes restore jumps.
        prev = snapshot_scroll(control)
        if abs(px - prev) < 1.5 and px > 0:
            return
        setattr(control, _SCROLL_ATTR, px)

    control.on_scroll = _on_scroll
    return control


async def restore_scroll(control: ft.Control, offset: float) -> None:
    """Jump a ListView back after its children were replaced.

    Single settle + one scroll_to (no multi-shot yank). Skips tiny offsets
    and cancels if a newer replace started meanwhile.
    """
    target = float(offset or 0)
    if target <= 24:
        setattr(control, _RESTORING_ATTR, False)
        return
    gen = int(getattr(control, _RESTORE_GEN, 0) or 0) + 1
    setattr(control, _RESTORE_GEN, gen)
    setattr(control, _RESTORING_ATTR, True)
    try:
        await asyncio.sleep(0.06)
        if int(getattr(control, _RESTORE_GEN, 0) or 0) != gen:
            return
        try:
            max_ext = float(getattr(control, "max_scroll_extent", 0) or 0)
        except (TypeError, ValueError):
            max_ext = 0.0
        if max_ext > 0:
            target = min(target, max_ext)
        try:
            await control.scroll_to(offset=target, duration=1)
            setattr(control, _SCROLL_ATTR, target)
        except Exception:  # noqa: BLE001
            pass
        # Let the scroll settle before recording user gestures again.
        await asyncio.sleep(0.12)
    finally:
        if int(getattr(control, _RESTORE_GEN, 0) or 0) == gen:
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
    if page is not None and offset > 24:
        run_async(page, restore_scroll, host, offset)
    else:
        setattr(host, _RESTORING_ATTR, False)
