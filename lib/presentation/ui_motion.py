"""UI motion helpers: refresh animation flag, list scroll memory, light motion."""

from __future__ import annotations

import asyncio
import contextvars
import os
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, Sequence

import flet as ft

from lib.presentation.utils import run_async, safe_update

_ANIMATE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "finwise_ui_animate", default=False
)
_SCROLL_ATTR = "_fw_scroll"
_RESTORING_ATTR = "_fw_restoring"
_RESTORE_GEN = "_fw_restore_gen"
_REDUCE_ATTR = "_fw_reduce_motion"
_OVERLAY_GEN = "_fw_overlay_gen"
_PRESS_BOUND = "_fw_press_bound"
# Restore any meaningful scroll — previously 40px left mid-page jumps unrestored.
_RESTORE_MIN = 1.0

# Tasteful iPhone-length motion. Prefer opacity / transform over blur.
DUR_FAST = 150
DUR_MED = 220
DUR_SLOW = 280
CURVE = ft.AnimationCurve.EASE_OUT
PRESS_SCALE = 0.98


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


def reduce_motion_from_env() -> bool:
    """True when tests / users force reduced motion via env."""
    return os.environ.get("FINANCE_REDUCE_MOTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def prefers_reduced_motion(page: ft.Page | None = None) -> bool:
    """Honor iOS Reduce Motion / disable-animations, or ``FINANCE_REDUCE_MOTION``."""
    if reduce_motion_from_env():
        return True
    if page is None:
        return False
    cached = getattr(page, _REDUCE_ATTR, None)
    return bool(cached)


def cache_reduced_motion(page: ft.Page | None, enabled: bool) -> None:
    """Store the platform accessibility snapshot on ``page``."""
    if page is None:
        return
    setattr(page, _REDUCE_ATTR, bool(enabled))


def motion_ms(duration: int, page: ft.Page | None = None) -> int:
    """Duration in ms, or ``0`` when motion should be skipped."""
    if prefers_reduced_motion(page):
        return 0
    return max(0, int(duration))


def motion_animation(
    duration: int = DUR_MED,
    page: ft.Page | None = None,
    *,
    curve: ft.AnimationCurve | None = None,
) -> ft.Animation | None:
    """Ease-out animation, or ``None`` when reduced motion is on."""
    ms = motion_ms(duration, page)
    if ms <= 0:
        return None
    return ft.Animation(ms, curve or CURVE)


async def probe_reduced_motion(page: ft.Page | None) -> bool:
    """Ask the platform for Reduce Motion / disable-animations (best-effort)."""
    if page is None:
        return reduce_motion_from_env()
    if reduce_motion_from_env():
        cache_reduced_motion(page, True)
        return True
    try:
        from lib.infrastructure.services.flet_services import (
            attach_page_service,
            existing_page_service,
        )

        svc = existing_page_service(page, ft.SemanticsService)
        if svc is None:
            svc = ft.SemanticsService()
            if not attach_page_service(page, svc, native_extension=False):
                cache_reduced_motion(page, False)
                return False
        features = await svc.get_accessibility_features()
        reduced = bool(
            getattr(features, "reduce_motion", False)
            or getattr(features, "disable_animations", False)
        )
        cache_reduced_motion(page, reduced)
        return reduced
    except Exception:  # noqa: BLE001
        cache_reduced_motion(page, False)
        return False


def bind_press(
    control: ft.Control,
    *,
    haptic_kind: str = "light",
    scale: float = PRESS_SCALE,
    on_click: Optional[Callable[[Any], Any]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Ink + slight scale on press. Light haptic. No-op when already bound."""
    if getattr(control, _PRESS_BOUND, False):
        return control
    setattr(control, _PRESS_BOUND, True)
    reduced = prefers_reduced_motion(page)
    previous = on_click or getattr(control, "on_click", None)
    if not reduced and hasattr(control, "animate_scale"):
        try:
            control.animate_scale = motion_animation(DUR_FAST, page)
            if getattr(control, "scale", None) is None:
                control.scale = 1
        except Exception:  # noqa: BLE001
            pass

    def _down(_e: Any) -> None:
        if reduced:
            return
        try:
            control.scale = scale
            safe_update(control)
        except Exception:  # noqa: BLE001
            pass

    def _click(e: Any) -> None:
        if not reduced:
            try:
                control.scale = 1
                safe_update(control)
            except Exception:  # noqa: BLE001
                pass
        try:
            from lib.presentation.haptics import haptic

            haptic(haptic_kind)
        except Exception:  # noqa: BLE001
            pass
        if callable(previous):
            previous(e)

    try:
        if hasattr(control, "on_tap_down"):
            control.on_tap_down = _down
        control.on_click = _click
    except Exception:  # noqa: BLE001
        pass
    return control


def apply_enter_motion(
    control: ft.Control,
    page: ft.Page | None = None,
    *,
    duration: int = DUR_MED,
) -> ft.Control:
    """Fade a control in on first mount (empty states, toasts)."""
    anim = motion_animation(duration, page)
    try:
        control.animate_opacity = anim
        if prefers_reduced_motion(page):
            control.opacity = 1
        else:
            control.opacity = 0
    except Exception:  # noqa: BLE001
        return control
    return control


def play_enter_motion(control: ft.Control) -> None:
    """Flip opacity to 1 so :func:`apply_enter_motion` can ease in."""
    try:
        if getattr(control, "opacity", 1) == 1:
            return
        control.opacity = 1
        safe_update(control)
    except Exception:  # noqa: BLE001
        pass


def overlay_enter_style(page: ft.Page | None = None) -> dict[str, Any]:
    """Kwargs for a fullscreen overlay that fades/slides in."""
    if prefers_reduced_motion(page):
        return {"opacity": 1, "offset": ft.Offset(0, 0)}
    return {
        "opacity": 0,
        "offset": ft.Offset(0, 0.03),
        "animate_opacity": motion_animation(DUR_MED, page),
        "animate_offset": motion_animation(DUR_MED, page),
    }


def bump_overlay_gen(control: ft.Control) -> int:
    """Invalidate in-flight overlay fade-out. Returns the new generation."""
    gen = int(getattr(control, _OVERLAY_GEN, 0) or 0) + 1
    setattr(control, _OVERLAY_GEN, gen)
    return gen


def overlay_generation(control: ft.Control) -> int:
    return int(getattr(control, _OVERLAY_GEN, 0) or 0)


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
