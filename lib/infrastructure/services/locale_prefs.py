"""Detect device locale / timezone for first-run language / currency defaults."""

from __future__ import annotations

import locale
import logging
import os
from pathlib import Path
from typing import Any

from lib.domain.locale_prefs import FALLBACK_CURRENCY, language_from_locale_tag

logger = logging.getLogger("finanse.infrastructure.services.locale_prefs")


def detect_system_locale_tag() -> str | None:
    """Best-effort OS locale tag (e.g. ``ru_RU``, ``en_US``, ``uz_UZ``)."""
    for getter in (
        lambda: os.environ.get("LC_ALL"),
        lambda: os.environ.get("LC_MESSAGES"),
        lambda: os.environ.get("LANG"),
        lambda: (locale.getlocale() or (None, None))[0],
        lambda: (locale.getdefaultlocale() or (None, None))[0],  # type: ignore[attr-defined]
    ):
        try:
            value = getter()
        except Exception:  # noqa: BLE001
            continue
        if value and str(value).strip() and str(value).strip().lower() not in {
            "c",
            "posix",
        }:
            return str(value).strip()
    return None


def detect_system_timezone_name() -> str | None:
    """Best-effort IANA timezone (e.g. ``Asia/Tashkent``)."""
    env_tz = (os.environ.get("TZ") or "").strip()
    if env_tz and "/" in env_tz:
        return env_tz.lstrip(":")
    try:
        resolved = Path("/etc/localtime").resolve()
        parts = resolved.parts
        if "zoneinfo" in parts:
            idx = parts.index("zoneinfo")
            name = "/".join(parts[idx + 1 :])
            if name and "/" in name:
                return name
    except Exception:  # noqa: BLE001
        logger.debug("Could not resolve /etc/localtime", exc_info=True)
    try:
        from datetime import datetime

        info = datetime.now().astimezone().tzinfo
        key = getattr(info, "key", None)
        if key and isinstance(key, str) and "/" in key:
            return key
    except Exception:  # noqa: BLE001
        logger.debug("tzinfo.key unavailable", exc_info=True)
    return None


def locale_tag_from_page(page: Any | None) -> str | None:
    """Read Flet ``page.locale`` when available."""
    if page is None:
        return None
    try:
        loc = getattr(page, "locale", None)
        if loc is None:
            return None
        if isinstance(loc, str) and loc.strip():
            return loc.strip()
        language = getattr(loc, "language_code", None) or getattr(loc, "language", None)
        country = getattr(loc, "country_code", None) or getattr(loc, "country", None)
        if language and country:
            return f"{language}_{country}"
        if language:
            return str(language)
    except Exception:  # noqa: BLE001
        logger.debug("page.locale unavailable", exc_info=True)
    return None


def detect_language_and_currency(
    *,
    page: Any | None = None,
    locale_tag: str | None = None,
    timezone: str | None = None,
) -> tuple[str, str]:
    """Resolve ``(language, currency)`` for first settings row.

    Language comes from the device/UI locale. Currency stays USD until the
    user creates their first account (that currency becomes the app default).
    """
    tag = locale_tag or locale_tag_from_page(page) or detect_system_locale_tag()
    _ = timezone  # currency is not auto-applied at first run
    lang = language_from_locale_tag(tag)
    logger.info(
        "Locale prefs: tag=%r → language=%s currency=%s (until first account)",
        tag,
        lang,
        FALLBACK_CURRENCY,
    )
    return lang, FALLBACK_CURRENCY


def suggested_currency_for_device(*, page: Any | None = None) -> str:
    """Currency to pre-select on the first-account form (not persisted)."""
    from lib.domain.locale_prefs import suggested_currency_from_device

    tag = locale_tag_from_page(page) or detect_system_locale_tag()
    tz = detect_system_timezone_name()
    return suggested_currency_from_device(tag, timezone=tz)