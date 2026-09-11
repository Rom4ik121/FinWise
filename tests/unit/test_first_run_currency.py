"""First-run default currency from device region vs explicit Settings / first account."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lib.domain.entities.settings import AppSettings
from lib.infrastructure.services.locale_prefs import (
    detect_language_and_currency,
    resolve_device_currency,
)
from lib.main import _maybe_refine_locale_from_page
from tests.conftest import run_async


def test_resolve_currency_prefers_page_region_over_os(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "de_DE",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "en_US",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_timezone_name",
        lambda: None,
    )
    assert resolve_device_currency(page=object()) == "EUR"


def test_resolve_currency_keeps_os_region_when_page_is_english_default(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "en_US",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "uk_UA",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_timezone_name",
        lambda: None,
    )
    assert resolve_device_currency(page=object()) == "UAH"


def test_resolve_currency_timezone_when_locale_has_no_region(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "ru",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "ru",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_timezone_name",
        lambda: "Asia/Tashkent",
    )
    assert resolve_device_currency(page=object()) == "UZS"


def test_resolve_currency_unknown_region_is_usd(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "en_NG",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "en_NG",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_timezone_name",
        lambda: None,
    )
    assert resolve_device_currency(page=object()) == "USD"


def test_detect_language_and_currency_uses_region(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "uz_UZ",
    )
    lang, currency = detect_language_and_currency(locale_tag="uz_UZ")
    assert lang == "uz"
    assert currency == "UZS"


def test_refine_skips_currency_when_user_chose(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_language",
        lambda **_kwargs: "de",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_currency",
        lambda **_kwargs: "EUR",
    )

    async def _run() -> None:
        container = SimpleNamespace(update_settings=MagicMock())
        container.update_settings.execute = AsyncMock()
        settings = AppSettings(
            language="en",
            language_user_set=True,
            default_currency="USD",
            currency_user_set=True,
        )
        await _maybe_refine_locale_from_page(container, object(), settings)
        container.update_settings.execute.assert_not_called()

    run_async(_run())


def test_refine_applies_device_currency_until_user_sets(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_language",
        lambda **_kwargs: "en",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_currency",
        lambda **_kwargs: "UAH",
    )

    async def _run() -> None:
        execute = AsyncMock()
        container = SimpleNamespace(update_settings=MagicMock())
        container.update_settings.execute = execute
        settings = AppSettings(
            language="en",
            language_user_set=True,
            default_currency="USD",
            currency_user_set=False,
        )
        await _maybe_refine_locale_from_page(container, object(), settings)
        execute.assert_awaited_once()
        updated = execute.await_args.args[0]
        assert updated.default_currency == "UAH"
        assert updated.currency_user_set is False
        assert updated.language == "en"

    run_async(_run())
