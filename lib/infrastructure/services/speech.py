"""On-device speech recognition bridge for mobile builds."""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger("finanse.infrastructure.services.speech")

_LOCALE = {"ru": "ru_RU", "en": "en_US", "uz": "uz_UZ"}

_speech_service: "SpeechBridge | None" = None


class SpeechBridge(Protocol):
    async def is_available(self) -> bool: ...

    async def listen(self, *, locale: str = "ru_RU", seconds: int = 8) -> dict[str, Any]: ...


def set_speech_service(service: SpeechBridge | None) -> None:
    global _speech_service
    _speech_service = service


def get_speech_service() -> SpeechBridge | None:
    return _speech_service


def speech_locale(language: str) -> str:
    return _LOCALE.get((language or "ru").split("-")[0], "ru_RU")


def register_speech_service(page: Any) -> bool:
    """Attach FinanseSpeech as a non-visual Flet service on mobile."""
    try:
        from lib.infrastructure.services.biometric import is_mobile_platform
        from lib.infrastructure.services.flet_services import attach_page_service

        if not is_mobile_platform(page):
            return False
        from flet_speech import FinanseSpeech

        speech = FinanseSpeech()
        if not attach_page_service(page, speech):
            return False
        set_speech_service(speech)
        logger.info("Speech service registered (platform=%s)", getattr(page, "platform", "?"))
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to register speech service")
        return False


async def listen_speech(*, language: str = "ru", seconds: int = 8) -> str:
    """Return recognized text or an empty string."""
    service = _speech_service
    if service is None:
        return ""
    try:
        payload = await service.listen(locale=speech_locale(language), seconds=seconds)
    except Exception:  # noqa: BLE001
        logger.exception("Speech listen failed")
        return ""
    if payload.get("ok"):
        return str(payload.get("text") or "").strip()
    return ""


async def prepare_speech_permissions() -> dict[str, Any]:
    """Ask for microphone and speech recognition. Does not open Settings."""
    service = _speech_service
    if service is None:
        return {"ok": False, "error": "unavailable"}
    try:
        req = getattr(service, "request_permissions", None)
        if req is not None:
            payload = await req()
            if isinstance(payload, dict):
                return {
                    "ok": bool(payload.get("ok")),
                    "error": payload.get("error"),
                }
            return {"ok": bool(payload)}
        ok = await service.is_available()
        return {"ok": bool(ok), "error": None if ok else "permission"}
    except Exception:  # noqa: BLE001
        logger.exception("Speech permission request failed")
        return {"ok": False, "error": "permission"}


async def open_os_app_settings(page: Any) -> None:
    """Open this app's system Settings page (Microphone, Speech, etc.)."""
    service = _speech_service
    opener = getattr(service, "open_settings", None)
    if opener is not None:
        try:
            if await opener():
                return
        except Exception:  # noqa: BLE001
            logger.debug("native open_settings failed", exc_info=True)
    plat = str(getattr(page, "platform", "")).lower()
    urls = ["app-settings:"]
    if "android" in plat:
        urls = [
            "intent:#Intent;action=android.settings.APPLICATION_DETAILS_SETTINGS;"
            "scheme=package;package=com.finanse.app;end",
            "package:com.finanse.app",
            "app-settings:",
        ]
    launch = getattr(page, "launch_url", None)
    if not callable(launch):
        return
    for url in urls:
        try:
            launch(url)
            return
        except Exception:  # noqa: BLE001
            logger.debug("launch_url %s failed", url, exc_info=True)
