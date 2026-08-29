"""FinanseSpeech — on-device speech-to-text via speech_to_text."""

from __future__ import annotations

from typing import Any, Optional

import flet as ft

from flet.controls.control_event import EventHandler

__all__ = ["FinanseSpeech"]


@ft.control("FinanseSpeech")
class FinanseSpeech(ft.Service):
    """Non-visual service that captures a short voice phrase."""

    on_voice_request: Optional[EventHandler] = None

    async def is_available(self) -> bool:
        return bool(await self._invoke_method("is_available"))

    async def take_pending_voice(self) -> bool:
        """True when the OS launched FinWise via the voice shortcut."""
        return bool(await self._invoke_method("take_pending_voice"))

    async def listen(self, *, locale: str = "ru_RU", seconds: int = 8) -> dict[str, Any]:
        result = await self._invoke_method(
            "listen",
            {"locale": locale, "seconds": int(seconds)},
            timeout=max(12, int(seconds) + 6),
        )
        if isinstance(result, dict):
            return {
                "ok": bool(result.get("ok")),
                "text": str(result.get("text") or ""),
                "error": result.get("error"),
            }
        if isinstance(result, str):
            return {"ok": bool(result.strip()), "text": result, "error": None}
        return {"ok": False, "text": "", "error": "empty"}
