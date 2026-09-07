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
# Restore any meaningful scroll — previously 40px left mid-page jumps unrestored.
_RESTORE_MIN = 1.0


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
        prev = snapshot_scroll(control)
        et = getattr(e, "event_type", None)
        et_name = str(getattr(et, "value", et) or "").lower()
        # Overlay dismiss / page.update() often snaps ListView to 0 without a
        # user gesture — ignore that so reload can still restore the old offset.
        if (
            prev >= 8
            and px < 4
            and "user" not in et_name
        ):
            return
        # Ignore tiny noise / rubber-band that causes restore jumps.
        if abs(px - prev) < 1.5 and px > 0:
            return
        setattr(control, _SCROLL_ATTR, px)

    control.on_scroll = _on_scroll
    return control


async def restore_scroll(control: ft.Control, offset: float) -> None:
    """Jump a ListView back after its children were replaced.

    Immediate scroll_to + one layout retry. Cancels if a newer replace started.
    """
    target = float(offset or 0)
    if target < _RESTORE_MIN:
        setattr(control, _RESTORING_ATTR, False)
        return
    gen = int(getattr(control, _RESTORE_GEN, 0) or 0) + 1
    setattr(control, _RESTORE_GEN, gen)
    setattr(control, _RESTORING_ATTR, True)

    async def _apply(pos: float) -> None:
        try:
            max_ext = float(getattr(control, "max_scroll_extent", 0) or 0)
        except (TypeError, ValueError):
            max_ext = 0.0
        aim = min(pos, max_ext) if max_ext > 0 else pos
        try:
            await control.scroll_to(offset=aim, duration=0)
            setattr(control, _SCROLL_ATTR, aim)
        except Exception:  # noqa: BLE001
            pass

    try:
        # First shot ASAP — reduce visible flash to top.
        await _apply(target)
        await asyncio.sleep(0.05)
        if int(getattr(control, _RESTORE_GEN, 0) or 0) != gen:
            return
        # Second shot after layout knows max_scroll_extent.
        await _apply(target)
        await asyncio.sleep(0.05)
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
    # Keep remembered offset across rebuild so late scroll events don't wipe it.
    setattr(host, _SCROLL_ATTR, offset)
    host.controls = list(controls)
    safe_update(host)
    if page is not None and offset >= _RESTORE_MIN:
        run_async(page, restore_scroll, host, offset)
    else:
        setattr(host, _RESTORING_ATTR, False)
