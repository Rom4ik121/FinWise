"""Compact floating «Saved» chip at the top (fixed height — never covers the screen)."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import flet as ft

from lib.presentation.utils import run_async, safe_update

_BANNER_MS = 1700
_COALESCE_S = 0.4
_KEY = "_finanse_ui_feedback"
_TAG = "ui_feedback_toast"


class UiFeedback:
    """Small green pill at the top; outer host is a thin transparent strip only."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._busy = False
        self._last_at = 0.0
        self._banner_text = ft.Text(
            "",
            size=13,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_PRIMARY,
        )
        self._banner_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE,
            size=17,
            color=ft.Colors.ON_PRIMARY,
        )
        self._pill = ft.Container(
            padding=ft.Padding.symmetric(horizontal=16, vertical=9),
            border_radius=999,
            bgcolor=ft.Colors.PRIMARY,
            shadow=ft.BoxShadow(
                blur_radius=14,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.40, ft.Colors.PRIMARY),
                offset=ft.Offset(0, 3),
            ),
            content=ft.Row(
                spacing=8,
                tight=True,
                controls=[self._banner_icon, self._banner_text],
            ),
        )
        pill = self._pill
        # CRITICAL: fixed height + transparent host so overlay does not wash the UI.
        self._banner = ft.Container(
            left=0,
            right=0,
            top=0,
            height=64,
            data=_TAG,
            visible=False,
            opacity=0,
            bgcolor=ft.Colors.TRANSPARENT,
            ignore_interactions=True,
            animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.only(top=12),
            content=pill,
        )
        self._purge_stale()
        page.overlay.append(self._banner)

    def _purge_stale(self) -> None:
        for item in list(self.page.overlay):
            if getattr(item, "data", None) == _TAG:
                try:
                    self.page.overlay.remove(item)
                except Exception:  # noqa: BLE001
                    pass

    def show(self, message: str, *, error: bool = False) -> None:
        """Show the save chip (or a red error chip over fullscreen forms)."""
        now = time.monotonic()
        self._apply_tone(error)
        if self._busy and (now - self._last_at) < _COALESCE_S:
            self._banner_text.value = message
            try:
                safe_update(self._banner_text)
                safe_update(self._pill)
            except Exception:  # noqa: BLE001
                pass
            return
        self._last_at = now
        run_async(self.page, self._run, message, error)

    def _apply_tone(self, error: bool) -> None:
        if error:
            self._banner_icon.icon = ft.Icons.ERROR_OUTLINE
            self._pill.bgcolor = ft.Colors.ERROR
            self._pill.shadow = ft.BoxShadow(
                blur_radius=14,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.40, ft.Colors.ERROR),
                offset=ft.Offset(0, 3),
            )
        else:
            self._banner_icon.icon = ft.Icons.CHECK_CIRCLE
            self._pill.bgcolor = ft.Colors.PRIMARY
            self._pill.shadow = ft.BoxShadow(
                blur_radius=14,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.40, ft.Colors.PRIMARY),
                offset=ft.Offset(0, 3),
            )

    def _raise_banner(self) -> None:
        """Keep the toast above fullscreen forms."""
        try:
            items = list(self.page.overlay or [])
            if self._banner in items:
                items.remove(self._banner)
            items.append(self._banner)
            self.page.overlay = items
        except Exception:  # noqa: BLE001
            try:
                self.page.overlay.append(self._banner)
            except Exception:  # noqa: BLE001
                pass

    async def _run(self, message: str, error: bool = False) -> None:
        self._busy = True
        try:
            self._apply_tone(error)
            self._banner_text.value = message
            self._raise_banner()
            self._banner.visible = True
            self._banner.opacity = 1
            try:
                safe_update(self._banner)
            except Exception:  # noqa: BLE001
                pass
            wait_ms = 2600 if error else _BANNER_MS
            await asyncio.sleep(wait_ms / 1000)
            self._banner.opacity = 0
            try:
                safe_update(self._banner)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.22)
            self._banner.visible = False
            try:
                safe_update(self._banner)
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._busy = False


def bind_ui_feedback(page: ft.Page) -> UiFeedback:
    """Attach (or replace) the toast overlay on ``page``."""
    existing = getattr(page, _KEY, None)
    if isinstance(existing, UiFeedback):
        # Re-bind after hot restart / remount.
        try:
            existing._purge_stale()
        except Exception:  # noqa: BLE001
            pass
    fb = UiFeedback(page)
    setattr(page, _KEY, fb)
    return fb


def get_ui_feedback(page: ft.Page | None) -> Optional[UiFeedback]:
    if page is None:
        return None
    existing = getattr(page, _KEY, None)
    return existing if isinstance(existing, UiFeedback) else None


def flash_refresh(page: ft.Page | None) -> None:
    """No-op kept for callers."""
    _ = page


def flash_saved(page: ft.Page | None, message: str) -> bool:
    """Show floating save chip. Returns False if feedback is not bound."""
    try:
        from lib.presentation.haptics import haptic

        haptic("success")
    except Exception:  # noqa: BLE001
        pass
    fb = get_ui_feedback(page)
    if fb is None:
        return False
    fb.show(message)
    return True


def flash_message(page: ft.Page | None, message: str, *, haptic_kind: str | None = "selection") -> bool:
    """Top toast without ``page.update()`` — keeps ListView scroll position."""
    if haptic_kind:
        try:
            from lib.presentation.haptics import haptic

            haptic(haptic_kind)
        except Exception:  # noqa: BLE001
            pass
    fb = get_ui_feedback(page)
    if fb is None:
        return False
    fb.show(message)
    return True


def flash_error(page: ft.Page | None, message: str) -> bool:
    """Red top toast — visible above fullscreen forms (SnackBar is not)."""
    try:
        from lib.presentation.haptics import haptic

        haptic("heavy")
    except Exception:  # noqa: BLE001
        pass
    fb = get_ui_feedback(page)
    if fb is None:
        return False
    fb.show(message, error=True)
    return True
