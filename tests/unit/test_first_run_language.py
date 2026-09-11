"""First-run language from device vs explicit Settings choice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lib.domain.entities.settings import AppSettings
from lib.infrastructure.services.locale_prefs import resolve_device_language
from lib.main import _maybe_refine_locale_from_page
from tests.conftest import run_async


def test_resolve_prefers_page_over_english_os(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "de_DE",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "en_US",
    )
    assert resolve_device_language(page=object()) == "de"


def test_resolve_keeps_os_when_page_is_english_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "en_US",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "uk_UA",
    )
    assert resolve_device_language(page=object()) == "uk"


def test_resolve_unsupported_falls_back_to_en(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.locale_tag_from_page",
        lambda _page: "ar_SA",
    )
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.detect_system_locale_tag",
        lambda: "he_IL",
    )
    assert resolve_device_language(page=object()) == "en"


def test_refine_skips_when_user_chose_language(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_language",
        lambda **_kwargs: "de",
    )

    async def _run() -> None:
        container = SimpleNamespace(update_settings=MagicMock())
        container.update_settings.execute = AsyncMock()
        settings = AppSettings(language="en", language_user_set=True)
        await _maybe_refine_locale_from_page(container, object(), settings)
        container.update_settings.execute.assert_not_called()

    run_async(_run())


def test_refine_applies_device_lang_until_user_sets(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.locale_prefs.resolve_device_language",
        lambda **_kwargs: "de",
    )

    async def _run() -> None:
        execute = AsyncMock()
        container = SimpleNamespace(update_settings=MagicMock())
        container.update_settings.execute = execute
        settings = AppSettings(language="en", language_user_set=False)
        await _maybe_refine_locale_from_page(container, object(), settings)
        execute.assert_awaited_once()
        updated = execute.await_args.args[0]
        assert updated.language == "de"
        assert updated.language_user_set is False

    run_async(_run())
