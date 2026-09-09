"""OS push / local notifications (Windows Toast + Android / iOS)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

logger = logging.getLogger("finanse.infrastructure.services.push_notifier")

APP_ID = "FinWise"
ANDROID_CHANNEL_ID = "finwise_reminders"
ANDROID_CHANNEL_NAME = "FinWise reminders"
ANDROID_CHANNEL_DESC = "Debt, subscription, and goal alerts"


class MobileNotificationsBridge(Protocol):
    """Subset of FinanseLocalNotifications / FletAndroidNotifications."""

    async def request_permissions(self) -> Any: ...

    async def are_notifications_enabled(self) -> Any: ...

    async def show_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        **kwargs: Any,
    ) -> Any: ...

    async def schedule_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        *,
        when_iso: str,
        **kwargs: Any,
    ) -> Any: ...


_mobile_service: MobileNotificationsBridge | None = None
_push_page: Any | None = None
_push_tasks: set[asyncio.Task[Any]] = set()
_seq = 0

# Back-compat aliases used by older tests.
AndroidNotificationsBridge = MobileNotificationsBridge


def set_android_notifications(service: MobileNotificationsBridge | None) -> None:
    """Register the mobile OS notification service."""
    global _mobile_service
    _mobile_service = service


def set_push_page(page: Any | None) -> None:
    """Keep the Flet page so sync ``dispatch_push`` can use ``page.run_task``."""
    global _push_page
    _push_page = page


def get_android_notifications() -> MobileNotificationsBridge | None:
    """Return the registered mobile notification service, if any."""
    return _mobile_service


def push_disabled_by_env() -> bool:
    """Test hook: ``FINANCE_DISABLE_PUSH=1`` skips OS notifications."""
    return os.environ.get("FINANCE_DISABLE_PUSH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def stable_notification_id(kind: str, related_id: str | None = None) -> int:
    """Stable positive int id for replaceable OS notifications."""
    digest = hashlib.md5(f"{kind}:{related_id or ''}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2_000_000_000 or 1


def next_notification_id() -> int:
    """Monotonic fallback id when no related entity exists."""
    global _seq
    _seq += 1
    return 100_000 + (_seq % 1_000_000)


def parse_reminder_hhmm(value: str) -> tuple[int, int]:
    """Parse ``HH:MM`` reminder time; fall back to 09:00."""
    parts = (value or "09:00").strip().split(":")
    if len(parts) != 2:
        return 9, 0
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return 9, 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return 9, 0
    return hour, minute


def reminder_fire_at(
    due: datetime,
    *,
    reminder_time: str = "09:00",
    lead_days: int = 3,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """UTC instant for an OS reminder, or ``None`` if it is already due."""
    due_aware = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    hour, minute = parse_reminder_hhmm(reminder_time)
    local = due_aware.astimezone()
    fire_date = local.date() - timedelta(days=max(0, int(lead_days)))
    fire_local = datetime(
        fire_date.year,
        fire_date.month,
        fire_date.day,
        hour,
        minute,
        tzinfo=local.tzinfo,
    )
    fire_utc = fire_local.astimezone(timezone.utc)
    if fire_utc > moment:
        return fire_utc
    # Still arm an OS alert for due/overdue items (app may be killed).
    return moment + timedelta(seconds=20)


def future_os_fire_at(
    when: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """UTC instant to zoned-schedule, or ``None`` to show immediately."""
    if when is None:
        return None
    when_utc = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    when_utc = when_utc.astimezone(timezone.utc)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if when_utc <= moment + timedelta(seconds=2):
        return None
    return when_utc


def _icon_path() -> str:
    """Prefer PNG for Linux notify-send; ICO for Windows toast."""
    root = Path(__file__).resolve().parents[3] / "assets"
    for name in ("icon.png", "icon_android.png", "icon.ico"):
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    return ""


def _show_windows_toast(title: str, body: str) -> bool:
    """Show a Windows toast notification via winotify."""
    if sys.platform != "win32":
        return False
    try:
        from winotify import Notification
    except Exception:  # noqa: BLE001
        logger.debug("winotify unavailable", exc_info=True)
        return False
    try:
        toast = Notification(
            app_id=APP_ID,
            title=title or APP_ID,
            msg=body or "",
            icon=_icon_path(),
            duration="short",
        )
        toast.show()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Windows toast failed")
        return False


def _show_linux_notification(title: str, body: str) -> bool:
    """Desktop Linux: ``notify-send`` with the FinWise icon when available."""
    if sys.platform != "linux":
        return False
    import shutil
    import subprocess

    if shutil.which("notify-send") is None:
        return False
    cmd = [
        "notify-send",
        "--app-name=FinWise",
        "--urgency=normal",
        "--expire-time=8000",
    ]
    icon = _icon_path()
    if icon:
        cmd.extend(["--icon", icon])
    cmd.extend([title or APP_ID, body or ""])
    try:
        subprocess.run(cmd, check=False, timeout=5)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("notify-send failed", exc_info=True)
        return False


async def request_push_permissions() -> bool:
    """Request OS notification permission when supported."""
    if push_disabled_by_env():
        return False
    svc = _mobile_service
    if svc is None:
        # Desktop toasts (Windows / Linux notify-send) do not need a runtime prompt.
        desktop = sys.platform in {"win32", "linux"} and not _looks_like_ios()
        if not desktop:
            logger.warning(
                "Push permission skipped: native notification service is not "
                "attached (IPA missing plugin, or flet run --ios web client)"
            )
        return desktop
    try:
        granted = await svc.request_permissions()
        logger.info("OS notification permission granted=%s", bool(granted))
        return bool(granted)
    except Exception:  # noqa: BLE001
        logger.exception("OS notification permission request failed")
        return False


def _looks_like_ios() -> bool:
    """True on packaged iPhone / iPad runtimes."""
    try:
        from lib.core.config import _is_ios

        return bool(_is_ios())
    except Exception:  # noqa: BLE001
        return sys.platform == "ios"


async def notify_push_ready(language: str = "ru") -> bool:
    """Show an immediate confirmation banner so the user knows OS push works."""
    from lib.infrastructure.services.localization import t

    return await show_os_notification(
        t("app.name", language),
        t("push.ready", language),
        kind="push_ready",
        related_id="startup",
    )


async def show_os_notification(
    title: str,
    body: str,
    *,
    notification_id: Optional[int] = None,
    kind: str = "info",
    related_id: Optional[str] = None,
) -> bool:
    """Show a system notification on the current platform."""
    if push_disabled_by_env():
        return False

    nid = notification_id
    if nid is None:
        nid = (
            stable_notification_id(kind, related_id)
            if related_id
            else next_notification_id()
        )

    svc = _mobile_service
    if svc is not None:
        try:
            await svc.show_notification(
                nid,
                title or APP_ID,
                body or "",
                channel_id=ANDROID_CHANNEL_ID,
                channel_name=ANDROID_CHANNEL_NAME,
                channel_description=ANDROID_CHANNEL_DESC,
                importance="high",
                play_sound=True,
                enable_vibration=True,
            )
            logger.info("OS notification shown id=%s kind=%s", nid, kind)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Android OS notification failed")

    if _show_windows_toast(title, body):
        return True
    if _show_linux_notification(title, body):
        return True

    logger.debug("No OS notification backend available for this platform")
    return False


async def schedule_os_notification(
    title: str,
    body: str,
    *,
    when: Optional[datetime] = None,
    notification_id: Optional[int] = None,
    kind: str = "info",
    related_id: Optional[str] = None,
) -> bool:
    """Show now, or schedule on the device when ``when`` is in the future."""
    if push_disabled_by_env():
        return False

    nid = notification_id
    if nid is None:
        nid = (
            stable_notification_id(kind, related_id)
            if related_id
            else next_notification_id()
        )

    when_utc = future_os_fire_at(when)

    svc = _mobile_service
    schedule = getattr(svc, "schedule_notification", None) if svc is not None else None
    if when_utc is not None and callable(schedule):
        try:
            await request_push_permissions()
            await schedule(
                nid,
                title or APP_ID,
                body or "",
                when_iso=when_utc.isoformat(),
                channel_id=ANDROID_CHANNEL_ID,
                channel_name=ANDROID_CHANNEL_NAME,
            )
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Failed to schedule OS notification")

    return await show_os_notification(
        title,
        body,
        notification_id=nid,
        kind=kind,
        related_id=related_id,
    )


def _log_push_task(task: asyncio.Task[Any]) -> None:
    _push_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        logger.exception("OS push task crashed")
        return
    if exc is not None:
        logger.exception("OS push failed", exc_info=exc)


def dispatch_push(
    title: str,
    body: str,
    *,
    kind: str = "info",
    related_id: Optional[str] = None,
    notification_id: Optional[int] = None,
) -> None:
    """Fire an OS notification from sync code (schedules async when needed)."""
    if push_disabled_by_env():
        return

    async def _go() -> bool:
        return await show_os_notification(
            title,
            body,
            notification_id=notification_id,
            kind=kind,
            related_id=related_id,
        )

    page = _push_page
    run_task = getattr(page, "run_task", None) if page is not None else None
    if callable(run_task):
        try:
            run_task(_go)
            return
        except Exception:  # noqa: BLE001
            logger.debug("page.run_task push failed; trying asyncio", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop — desktop toast is sync-safe.
        if _mobile_service is None:
            if not _show_windows_toast(title, body):
                _show_linux_notification(title, body)
        else:
            logger.warning("Skipping mobile OS push: no running event loop")
        return

    task = loop.create_task(_go())
    _push_tasks.add(task)
    task.add_done_callback(_log_push_task)


def register_android_notifications(page: Any) -> bool:
    """Attach local notifications on Android and iOS (never as a visual widget)."""
    try:
        from lib.infrastructure.services.biometric import is_mobile_platform
        from lib.infrastructure.services.flet_services import attach_page_service

        logger.info(
            "Push register: platform=%s web=%s mobile=%s",
            getattr(page, "platform", None),
            getattr(page, "web", None),
            is_mobile_platform(page),
        )
        if not is_mobile_platform(page):
            return False
    except Exception:  # noqa: BLE001
        return False

    try:
        from flet_local_notifications import FinanseLocalNotifications
        from lib.infrastructure.services.flet_services import existing_page_service

        bound = existing_page_service(page, FinanseLocalNotifications)
        if bound is None:
            bound = FinanseLocalNotifications()
            if not attach_page_service(page, bound):
                bound = None
        if bound is not None:
            set_android_notifications(bound)
            set_push_page(page)
            logger.info("Local notification service registered")
            return True
    except Exception:  # noqa: BLE001
        logger.exception("FinanseLocalNotifications unavailable")

    try:
        from flet import PagePlatform
        from flet_android_notifications import FletAndroidNotifications

        if getattr(page, "platform", None) not in {
            PagePlatform.ANDROID,
            PagePlatform.ANDROID_TV,
        }:
            return False
        from lib.infrastructure.services.flet_services import (
            attach_page_service,
            existing_page_service,
        )

        bound = existing_page_service(page, FletAndroidNotifications)
        if bound is None:
            bound = FletAndroidNotifications()
            if not attach_page_service(page, bound):
                return False
        set_android_notifications(bound)
        set_push_page(page)
        logger.info("Android push notification service registered")
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to register Android notifications")
        return False
