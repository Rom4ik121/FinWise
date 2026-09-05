"""PIN / biometric unlock screen."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

import flet as ft

from lib.infrastructure.services.biometric import BiometricResult, BiometricStatus
from lib.infrastructure.services.encryption_service import EncryptionService
from lib.presentation.theme import is_dark_mode, page_gradient
from lib.presentation.responsive import (
    clamp_content_width,
    form_control_width,
    page_width,
    scale_font,
)
from lib.presentation.utils import run_async, safe_update, snack, tr


def _biometric_error_key(result: BiometricResult) -> str:
    mapping = {
        BiometricResult.CANCELED: "lock.biometric_canceled",
        BiometricResult.DEVICE_NOT_PRESENT: "lock.biometric_no_device",
        BiometricResult.NOT_CONFIGURED: "lock.biometric_not_configured",
        BiometricResult.DISABLED_BY_POLICY: "lock.biometric_policy",
        BiometricResult.DEVICE_BUSY: "lock.biometric_busy",
        BiometricResult.RETRIES_EXHAUSTED: "lock.biometric_retries",
        BiometricResult.UNSUPPORTED: "lock.biometric_unavailable",
        BiometricResult.FAILED: "lock.biometric_failed",
    }
    return mapping.get(result, "lock.biometric_failed")


class LockScreen(ft.Container):
    """Full-screen lock gate shown when a PIN is configured."""

    def __init__(
        self,
        page: ft.Page,
        *,
        language: str,
        pin_hash: str,
        pin_salt: str,
        biometric_enabled: bool,
        on_unlocked: Callable[[], Awaitable[None] | None],
        encryption: Optional[EncryptionService] = None,
        auto_biometric: bool = True,
    ) -> None:
        self._page = page
        self._lang = language
        self._pin_hash = pin_hash
        self._pin_salt = pin_salt
        self._biometric_enabled = biometric_enabled
        self._auto_biometric = auto_biometric
        self._on_unlocked = on_unlocked
        self._crypto = encryption or EncryptionService()
        self._biometric_busy = False
        self._pin_fails = 0
        self._pin_locked_until = 0.0
        self._countdown_task: asyncio.Task[None] | None = None
        field_w = form_control_width(page, preferred=280)
        if field_w is None:
            field_w = clamp_content_width(page, margin=56, max_width=280)
        self._pin = ft.TextField(
            label=tr("settings.pin", language),
            password=True,
            can_reveal_password=False,
            max_length=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            width=field_w,
            text_align=ft.TextAlign.CENTER,
            border_radius=14,
            filled=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            on_submit=lambda _e: run_async(page, self._try_pin),
            autofocus=not biometric_enabled,
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(self._pin, "number")
        wire_field_chain(page, [self._pin])
        self._error = ft.Text(
            "",
            color=ft.Colors.ERROR,
            size=scale_font(12, page, minimum=11, maximum=14),
        )
        self._bio_btn = ft.OutlinedButton(
            tr("settings.biometric", language),
            icon=ft.Icons.FACE_2,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=14),
                padding=ft.Padding.symmetric(horizontal=18, vertical=14),
            ),
            width=field_w,
            visible=biometric_enabled,
            on_click=lambda _e: run_async(page, self._try_biometric),
        )

        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=14),
            padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        )
        actions: list[ft.Control] = [
            ft.FilledButton(
                tr("lock.unlock", language),
                icon=ft.Icons.LOCK_OPEN,
                style=btn_style,
                width=field_w,
                on_click=lambda _e: run_async(page, self._try_pin),
            ),
            self._bio_btn,
        ]

        dark = is_dark_mode(page)
        card_w = clamp_content_width(page, margin=24, max_width=400)
        super().__init__(
            expand=True,
            alignment=ft.Alignment.CENTER,
            gradient=page_gradient(dark),
            padding=ft.Padding.symmetric(horizontal=16, vertical=24),
            content=ft.Container(
                width=card_w,
                padding=24 if page_width(page) < 360 else 28,
                border_radius=24,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                shadow=ft.BoxShadow(
                    blur_radius=30,
                    color="#00000044",
                    offset=ft.Offset(0, 12),
                ),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                    tight=True,
                    controls=[
                        ft.Container(
                            width=72,
                            height=72,
                            border_radius=22,
                            bgcolor=ft.Colors.PRIMARY_CONTAINER,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                ft.Icons.FACE_2
                                if biometric_enabled
                                else ft.Icons.LOCK,
                                size=34,
                                color=ft.Colors.ON_PRIMARY_CONTAINER,
                            ),
                        ),
                        ft.Text(
                            tr("app.name", language),
                            size=scale_font(28, page, minimum=24, maximum=32),
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.PRIMARY,
                        ),
                        ft.Text(
                            tr(
                                "lock.subtitle_bio" if biometric_enabled else "lock.subtitle",
                                language,
                            ),
                            size=scale_font(14, page, minimum=12, maximum=16),
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        self._pin,
                        self._error,
                        ft.Column(
                            spacing=10,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                            controls=actions,
                        ),
                    ],
                ),
            ),
        )
        if biometric_enabled and auto_biometric:
            run_async(page, self._bootstrap_biometric)

    async def _bootstrap_biometric(self) -> None:
        """Probe OS support, then auto-open Face ID when available."""
        status = await self._crypto.refresh_biometric_status()
        face_ok = status is BiometricStatus.AVAILABLE
        self._bio_btn.visible = self._biometric_enabled and face_ok
        safe_update(self._bio_btn)
        if self._biometric_enabled and face_ok:
            await self._try_biometric()

    async def _finish(self) -> None:
        self._stop_countdown()
        result = self._on_unlocked()
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]

    def _stop_countdown(self) -> None:
        task = self._countdown_task
        self._countdown_task = None
        if task is not None and not task.done():
            task.cancel()

    def _start_countdown(self) -> None:
        """Refresh the lockout message every second until the lock expires."""
        self._stop_countdown()

        async def _tick() -> None:
            try:
                while True:
                    remaining = int(self._pin_locked_until - time.monotonic())
                    if remaining <= 0:
                        self._pin_locked_until = 0.0
                        self._error.value = ""
                        self._pin.disabled = False
                        safe_update(self._error)
                        safe_update(self._pin)
                        safe_update(self)
                        return
                    self._error.value = tr(
                        "lock.throttled", self._lang, seconds=remaining
                    )
                    self._pin.disabled = True
                    safe_update(self._error)
                    safe_update(self._pin)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                return

        self._countdown_task = asyncio.create_task(_tick())

    async def _try_pin(self) -> None:
        now = time.monotonic()
        if now < self._pin_locked_until:
            # Ensure live timer is running even if user taps again.
            if self._countdown_task is None or self._countdown_task.done():
                self._start_countdown()
            return
        pin = (self._pin.value or "").strip()
        if self._crypto.verify_pin(pin, self._pin_hash, self._pin_salt):
            self._pin_fails = 0
            self._pin_locked_until = 0.0
            self._pin.disabled = False
            await self._finish()
            return
        self._pin_fails += 1
        if self._pin_fails >= 5:
            # 30s, then 60s, 120s… after every 5 failures.
            lock_for = 30 * (2 ** max(0, (self._pin_fails // 5) - 1))
            self._pin_locked_until = now + lock_for
            self._pin.value = ""
            self._start_countdown()
            return
        self._error.value = tr("lock.wrong_pin", self._lang)
        self._pin.value = ""
        safe_update(self)

    async def _try_biometric(self) -> None:
        if self._biometric_busy:
            return
        self._biometric_busy = True
        self._error.value = ""
        safe_update(self)
        try:
            result = await self._crypto.authenticate_biometric(
                message=tr("lock.biometric_prompt", self._lang),
            )
            if result is BiometricResult.VERIFIED:
                await self._finish()
                return
            if result is BiometricResult.CANCELED:
                # Soft: user dismissed the prompt — keep PIN field ready.
                return
            msg = tr(_biometric_error_key(result), self._lang)
            self._error.value = msg
            snack(self._page, msg, error=True)
            safe_update(self)
        finally:
            self._biometric_busy = False
