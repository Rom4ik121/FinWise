"""Locale → language / currency first-run defaults."""

from __future__ import annotations

from lib.domain.locale_prefs import (
    FALLBACK_CURRENCY,
    FALLBACK_LANGUAGE,
    currency_from_locale_tag,
    language_from_locale_tag,
    prefs_from_locale_tag,
    region_from_timezone,
    suggested_currency_from_device,
)


def test_fallback_when_empty() -> None:
    assert prefs_from_locale_tag(None) == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("") == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("C") == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)


def test_language_from_locale_currency_stays_fallback() -> None:
    """First-run settings: language from OS, currency until first account."""
    assert prefs_from_locale_tag("uz_UZ") == ("uz", FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("ru_RU.UTF-8") == ("ru", FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("en_US") == ("en", FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("de_DE") == ("de", FALLBACK_CURRENCY)


def test_language_mapping_table() -> None:
    cases = {
        "uk-UA": "uk",
        "uk": "uk",
        "be-BY": "be",
        "kk-KZ": "kk",
        "de-AT": "de",
        "es-MX": "es",
        "fr-CA": "fr",
        "pt-BR": "pt",
        "pt-PT": "pt",
        "it-IT": "it",
        "pl-PL": "pl",
        "tr-TR": "tr",
        "id-ID": "id",
        "in_ID": "id",
        "zh-CN": "zh",
        "zh-Hans": "zh",
        "zh-TW": "zh",
        "ja-JP": "ja",
        "ko-KR": "ko",
        "hi-IN": "hi",
        "ky-KG": "ru",
        "tg-TJ": "ru",
        "ar-SA": "en",
        "he-IL": "en",
        "sv-SE": "en",
    }
    for tag, expected in cases.items():
        assert language_from_locale_tag(tag) == expected, tag


def test_suggested_currency_from_device() -> None:
    assert region_from_timezone("Asia/Tashkent") == "UZ"
    assert suggested_currency_from_device(
        "ru_RU.UTF-8", timezone="Asia/Tashkent"
    ) == "UZS"
    assert suggested_currency_from_device("ru_RU", timezone="Europe/Moscow") == "RUB"
    assert currency_from_locale_tag("uz_UZ") == "UZS"
    assert language_from_locale_tag("ru") == "ru"
