"""Light haptic feedback on phones; no-op on desktop and in tests."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("finanse.presentation.haptics")


def haptic(kind: str = "light") -> None:
    """Fire a platform haptic if the mobile notifications bridge is attached."""
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
        loop.create_task(fn(kind))
    except Exception:  # noqa: BLE001
        logger.debug("Haptic skipped", exc_info=True)
