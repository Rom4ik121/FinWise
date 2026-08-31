"""Hands-free voice capture from a phone shortcut / deep link."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import flet as ft

from lib.infrastructure.services.speech import get_speech_service, listen_speech
from lib.infrastructure.services.voice_capture import save_spoken_transaction
from lib.presentation.utils import run_async, snack, tr

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

logger = logging.getLogger("finanse.presentation.voice_shortcut")


def is_voice_route(route: str | None) -> bool:
    """True when the OS opened FinWise via the voice shortcut URL."""
    text = (route or "").strip().casefold()
    if not text:
        return False
    if "finwise://voice" in text:
        return True
    path = text.split("?", 1)[0].rstrip("/")
    return path in {"voice", "/voice", "//voice"} or path.endswith("/voice")


def install_voice_shortcut(page: ft.Page, state: "AppState") -> None:
    """Listen for ``finwise://voice`` and the speech-service hotkey event."""
    busy = {"on": False}

    async def _run_capture() -> None:
        if busy["on"]:
            return
        if not state.is_unlocked:
            state.pending_voice_capture = True
            return
        busy["on"] = True
        lang = state.language
        try:
            from lib.infrastructure.services.speech import (
                open_os_app_settings,
                prepare_speech_permissions,
            )

            granted = await prepare_speech_permissions()
            if not granted.get("ok"):
                snack(page, tr("voice.permission_denied", lang), error=True)
                await open_os_app_settings(page)
                return
            snack(page, tr("voice.listening", lang))
            spoken = await listen_speech(language=lang, seconds=10)
            if not spoken:
                snack(page, tr("voice.empty", lang), error=True)
                return
            result = await save_spoken_transaction(state.container, spoken)
            if not result.ok:
                key = {
                    "need_amount": "voice.need_amount",
                    "need_category": "voice.need_category",
                    "no_account": "empty.accounts",
                }.get(result.error, "voice.empty")
                snack(page, tr(key, lang), error=True)
                return
            state.bump_refresh("dashboard", "transactions", "accounts", "budgets")
            snack(
                page,
                tr("voice.saved", lang).format(
                    category=result.category,
                    amount=result.amount_text,
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Voice shortcut capture failed")
            snack(page, tr("voice.empty", lang), error=True)
        finally:
            busy["on"] = False

    def _maybe_from_route(route: str | None) -> None:
        if is_voice_route(route):
            run_async(page, _run_capture)

    def _on_route(e: Any) -> None:
        _maybe_from_route(getattr(e, "route", None) or getattr(page, "route", None))

    def _on_lifecycle(_e: Any) -> None:
        if state.pending_voice_capture and state.is_unlocked:
            state.pending_voice_capture = False
            run_async(page, _run_capture)
            return

        async def _poll() -> None:
            service = get_speech_service()
            take = getattr(service, "take_pending_voice", None)
            if callable(take) and await take():
                await _run_capture()
                return
            _maybe_from_route(getattr(page, "route", None))

        run_async(page, _poll)

    page.on_route_change = _on_route
    previous_lifecycle = page.on_app_lifecycle_state_change

    def _on_lifecycle_chained(e: Any) -> None:
        if callable(previous_lifecycle):
            try:
                previous_lifecycle(e)
            except Exception:  # noqa: BLE001
                logger.exception("Chained lifecycle handler failed")
        _on_lifecycle(e)

    page.on_app_lifecycle_state_change = _on_lifecycle_chained
    _maybe_from_route(getattr(page, "route", None))

    service = get_speech_service()
    if service is not None and hasattr(service, "on_voice_request"):
        service.on_voice_request = lambda _e: run_async(page, _run_capture)

    state.voice_capture = _run_capture
