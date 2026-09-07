"""Application bootstrap: logging, DB, DI, background tasks, Flet."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import flet as ft

from lib.core.config import AppConfig, get_default_config
from lib.core.database import init_db
from lib.core.dependencies import Container, build_container
from lib.core.logging_config import setup_logging
from lib.infrastructure.services.localization import normalize_lang
from lib.presentation.app import FinanseApp

logger = logging.getLogger("finanse.main")

_rate_task: Optional[asyncio.Future[Any]] = None
_reminder_task: Optional[asyncio.Future[Any]] = None
_daily_backup_task: Optional[asyncio.Future[Any]] = None


async def _maybe_refine_locale_from_page(
    container: Container,
    page: ft.Page | None,
    settings: Any,
) -> None:
    """If language is still English fallback, prefer richer device/page locale."""
    if page is None or container.update_settings is None:
        return
    from lib.domain.locale_prefs import FALLBACK_LANGUAGE
    from lib.infrastructure.services.locale_prefs import detect_language_and_currency

    if normalize_lang(settings.language) != FALLBACK_LANGUAGE:
        return
    lang, _currency = detect_language_and_currency(page=page)
    if normalize_lang(lang) == FALLBACK_LANGUAGE:
        return
    if normalize_lang(settings.language) == normalize_lang(lang):
        return
    updated = settings.model_copy(update={"language": lang})
    await container.update_settings.execute(updated)
    logger.info("Refined first-run language → %s", lang)


async def _seed_if_needed(container: Container, page: ft.Page | None = None) -> None:
    """Ensure currencies and settings exist (idempotent). No default account."""
    try:
        from pathlib import Path

        currencies_path = (
            Path(__file__).resolve().parents[1] / "assets" / "data" / "currencies.json"
        )
        if (
            container.currency_repository is not None
            and hasattr(container.currency_repository, "seed_from_json")
            and currencies_path.exists()
        ):
            # Upsert on every launch so catalog additions (e.g. top crypto) appear.
            count = await container.currency_repository.seed_from_json(
                currencies_path
            )
            logger.info("Synced %d currencies from JSON", count)
    except Exception:  # noqa: BLE001
        logger.exception("Currency seed failed")

    try:
        if container.get_settings is not None:
            # Warm settings (language from device UI; currency until first account).
            settings = await container.get_settings.execute()
            await _maybe_refine_locale_from_page(container, page, settings)
    except Exception:  # noqa: BLE001
        logger.exception("Settings seed/load failed")


async def _exchange_rate_loop(container: Container) -> None:
    """Periodically refresh FX rates while the app is running."""
    while True:
        minutes = container.config.exchange_update_interval_minutes
        try:
            settings = (
                await container.get_settings.execute()
                if container.get_settings
                else None
            )
            if settings is not None:
                minutes = settings.exchange_update_interval_minutes
                base = settings.default_currency
            else:
                base = container.config.default_currency
            if container.update_exchange_rates is not None:
                await container.update_exchange_rates.execute(base=base)
                try:
                    from lib.presentation.utils import invalidate_rate_book_cache

                    invalidate_rate_book_cache()
                except Exception:  # noqa: BLE001
                    pass
                logger.info("Exchange rates updated (base=%s)", base)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Background exchange-rate update failed: %s", exc)
        await asyncio.sleep(max(5, minutes) * 60)


def _parse_hhmm(value: str) -> tuple[int, int]:
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


async def _daily_backup_loop(container: Container) -> None:
    """Refresh the single rolling ``finanse_daily.db`` at most once per local day."""
    from lib.infrastructure.services.backup_service import BackupService

    while True:
        try:
            path = await asyncio.to_thread(
                BackupService(container.config).ensure_daily_backup
            )
            if path is not None:
                logger.info("Daily backup refreshed: %s", path)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Daily backup check failed")
        await asyncio.sleep(60 * 60)


async def _reminder_loop(container: Container) -> None:
    """Daily in-app reminder sweep for debts and subscriptions."""
    last_run_date: Optional[str] = None
    while True:
        sleep_for = 60.0
        try:
            settings = (
                await container.get_settings.execute()
                if container.get_settings
                else None
            )
            if settings and settings.notifications_enabled:
                hour, minute = _parse_hhmm(settings.reminder_time)
                now_local = datetime.now()
                stamp = now_local.strftime("%Y-%m-%d")
                target = now_local.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if (
                    now_local.hour == hour
                    and now_local.minute == minute
                    and last_run_date != stamp
                ):
                    notifier = container.notification_service
                    if notifier is not None:
                        lang = normalize_lang(settings.language)
                        await schedule_reminders(
                            container,
                            settings,
                            language=lang,
                        )
                        pending = notifier.list_pending()
                        logger.info(
                            "Reminder sweep created/pending=%d", len(pending)
                        )
                    last_run_date = stamp
                    sleep_for = 55.0
                else:
                    delta = (target - now_local).total_seconds()
                    if delta <= 0:
                        # Next day target.
                        delta += 24 * 3600
                    # Wake near the reminder minute, but never sleep longer than 15m
                    # so setting changes still apply reasonably fast.
                    sleep_for = max(20.0, min(delta, 15 * 60))
            else:
                sleep_for = 5 * 60
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Reminder loop failed")
            sleep_for = 60.0
        await asyncio.sleep(sleep_for)


async def _flet_main(page: ft.Page) -> None:
    """Async Flet target: wire container, background task, UI."""
    global _rate_task, _reminder_task, _daily_backup_task

    from lib.presentation.widgets.splash_screen import build_launch_splash

    # Match native splash / classic dark shell so phones never flash white.
    page.padding = 0
    page.bgcolor = "#0B1220"
    try:
        page.theme_mode = ft.ThemeMode.DARK
    except Exception:  # noqa: BLE001
        pass
    page.add(build_launch_splash())
    page.update()

    config = get_default_config()
    setup_logging(log_dir=config.log_dir)
    init_db(config)
    container = build_container(config, init_database=False)
    await _seed_if_needed(container, page)

    if _rate_task is None or _rate_task.done():
        _rate_task = page.run_task(_exchange_rate_loop, container)
    if _reminder_task is None or _reminder_task.done():
        _reminder_task = page.run_task(_reminder_loop, container)
    if _daily_backup_task is None or _daily_backup_task.done():
        _daily_backup_task = page.run_task(_daily_backup_loop, container)

    app = FinanseApp(page, container)

    from lib.infrastructure.services.biometric import register_local_auth_service
    from lib.infrastructure.services.push_notifier import register_android_notifications

    # Keep the splash visible — do not clear the page before the shell is ready.
    register_local_auth_service(page)
    register_android_notifications(page)

    await app.start()

    # Heavy startup work after first frame (faster perceived launch on phones).
    async def _post_start() -> None:
        from lib.infrastructure.services.backup_service import BackupService
        from lib.infrastructure.services.reminder_scheduler import schedule_reminders
        from lib.infrastructure.services.push_notifier import (
            notify_push_ready,
            request_push_permissions,
        )

        # Always request OS notification permission after the first UI frame.
        # iOS only lists FinWise under Settings → Notifications after this.
        try:
            granted = await request_push_permissions()
            settings = await container.get_settings.execute()
            prompt_flag = container.config.data_dir / ".push_permission_asked"
            first_prompt = not prompt_flag.exists()
            logger.info("Push permission granted=%s first=%s", granted, first_prompt)
            if first_prompt:
                try:
                    prompt_flag.write_text("1", encoding="utf-8")
                except OSError:
                    logger.debug(
                        "Could not write push permission flag", exc_info=True
                    )
                if granted and settings.notifications_enabled:
                    try:
                        await notify_push_ready(normalize_lang(settings.language))
                    except Exception:  # noqa: BLE001
                        logger.exception("push ready banner failed")
        except Exception:  # noqa: BLE001
            logger.exception("Push permission request failed")

        try:
            path = await asyncio.to_thread(
                BackupService(container.config).ensure_daily_backup
            )
            if path is not None:
                logger.info("Daily backup refreshed on start: %s", path)
        except Exception:  # noqa: BLE001
            logger.exception("Startup daily backup failed")

        try:
            if container.process_due_subscriptions is not None:
                settings = await container.get_settings.execute()
                await container.process_due_subscriptions.execute(
                    language=normalize_lang(settings.language),
                    notifier=container.notification_service,
                )
        except Exception:  # noqa: BLE001
            logger.exception("process_due_subscriptions failed")
        try:
            settings = await container.get_settings.execute()
            await schedule_reminders(
                container,
                settings,
                language=normalize_lang(settings.language),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Startup reminder scheduling failed")

    page.run_task(_post_start)


def run(config: Optional[AppConfig] = None) -> None:
    """Launch the Finanse desktop / mobile Flet application.

    Prefer ``flet run --android|--ios|--web --host 0.0.0.0 --port 8550 main.py``
    for phone testing — the CLI sets ``FLET_*`` env vars that Flet reads.

    Optional manual overrides:

    * ``FLET_VIEW=web|android|ios|desktop``
    * ``FLET_HOST`` / ``FLET_PORT``
    """
    import os

    cfg = config or get_default_config()
    setup_logging(log_dir=cfg.log_dir)
    logger.info("Starting FinWise (data_dir=%s)", cfg.data_dir)

    # Windows/uvicorn cannot bind host="*"; normalize to 0.0.0.0.
    for key in ("FLET_SERVER_IP", "FLET_HOST"):
        value = (os.environ.get(key) or "").strip()
        if value in {"*", "all"}:
            os.environ[key] = "0.0.0.0"

    # When launched via ``flet run --android/--web``, let Flet consume CLI env.
    if os.environ.get("FLET_FORCE_WEB_SERVER", "").lower() in {"1", "true", "yes"}:
        logger.info(
            "Flet mobile/web server mode (host=%s port=%s)",
            os.environ.get("FLET_SERVER_IP"),
            os.environ.get("FLET_SERVER_PORT"),
        )
        ft.run(_flet_main)
        return

    view_raw = (os.environ.get("FLET_VIEW") or "desktop").strip().lower()
    host = os.environ.get("FLET_HOST")
    port_raw = os.environ.get("FLET_PORT", "").strip()
    port = int(port_raw) if port_raw.isdigit() else 0

    kwargs: dict[str, Any] = {}
    if view_raw in {"web", "browser"}:
        kwargs["view"] = ft.AppView.WEB_BROWSER
        kwargs["host"] = host or "0.0.0.0"
        kwargs["port"] = port or 8550
    elif view_raw in {"android", "ios", "mobile"}:
        kwargs["view"] = ft.AppView.WEB_BROWSER
        kwargs["host"] = host or "0.0.0.0"
        kwargs["port"] = port or 8550
    elif view_raw == "hidden":
        kwargs["view"] = ft.AppView.FLET_APP_HIDDEN

    if kwargs.get("host") in {"*", "all"}:
        kwargs["host"] = "0.0.0.0"

    logger.info(
        "Flet launch view=%s host=%s port=%s",
        kwargs.get("view", ft.AppView.FLET_APP),
        kwargs.get("host"),
        kwargs.get("port") or "auto",
    )
    ft.run(_flet_main, **kwargs)
