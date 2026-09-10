"""Light haptic feedback on phones; no-op on desktop and in tests.

Never fire on scroll. Coalesce repeats so nav + toast do not buzz twice.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("finanse.presentation.haptics")

# Minimum gap between emissions of the same (or any) kind. Keep generous so
# a tab switch + toast cannot stack two impacts.
_GAP_S: dict[str, float] = {
    "light": 0.08,
    "selection": 0.10,
    "medium": 0.14,
    "success": 0.28,
    "warning": 0.22,
    "heavy": 0.28,
}
_DEFAULT_GAP = 0.12
_last_at = 0.0
_last_kind = ""


def should_emit_haptic(
    kind: str,
    *,
    now: float,
    last_at: float,
    min_gap: float | None = None,
) -> bool:
    """Pure cooldown: True when ``kind`` may fire at ``now``."""
    gap = min_gap if min_gap is not None else _GAP_S.get(kind, _DEFAULT_GAP)
    return (now - last_at) >= gap


def haptic(kind: str = "light") -> None:
    """Fire a platform haptic if the mobile notifications bridge is attached."""
    global _last_at, _last_kind
    token = (kind or "light").strip().lower() or "light"
    if token == "warning":
        token = "heavy"
    now = time.monotonic()
    if not should_emit_haptic(token, now=now, last_at=_last_at):
        return
    try:
        from lib.infrastructure.services.push_notifier import get_android_notifications

        svc: Any = get_android_notifications()
    except Exception:  # noqa: BLE001
        return
    if svc is None:
        return
    fn = getattr(svc, "haptic", None)
    if not callable(fn):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.create_task(fn(token))
        _last_at = now
        _last_kind = token
    except Exception:  # noqa: BLE001
        logger.debug("Haptic skipped", exc_info=True)


def reset_haptic_gate() -> None:
    """Test helper: clear the in-process cooldown."""
    global _last_at, _last_kind
    _last_at = 0.0
    _last_kind = ""
