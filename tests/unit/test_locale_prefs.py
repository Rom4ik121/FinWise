"""Locale → language / currency first-run defaults."""

from __future__ import annotations

from lib.domain.locale_prefs import (
    FALLBACK_CURRENCY,
    FALLBACK_LANGUAGE,
    _REGION_CURRENCY,
    catalog_fiat_codes,
    currency_from_locale_tag,
    currency_from_region,
    language_from_locale_tag,
    prefs_from_locale_tag,
    region_from_timezone,
    suggested_currency_from_device,
)


def test_fallback_when_empty() -> None:
    assert prefs_from_locale_tag(None) == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("") == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)
    assert prefs_from_locale_tag("C") == (FALLBACK_LANGUAGE, FALLBACK_CURRENCY)


def test_language_and_region_currency_from_locale() -> None:
    """First-run settings: language from OS, currency from region (not language)."""
    assert prefs_from_locale_tag("uz_UZ") == ("uz", "UZS")
    assert prefs_from_locale_tag("ru_RU.UTF-8") == ("ru", "RUB")
    assert prefs_from_locale_tag("en_US") == ("en", "USD")
    assert prefs_from_locale_tag("de_DE") == ("de", "EUR")
    assert prefs_from_locale_tag("uk-UA") == ("uk", "UAH")
    assert prefs_from_locale_tag("en-GB") == ("en", "GBP")
    assert prefs_from_locale_tag("fr-FR") == ("fr", "EUR")
    # Region wins over language (English UI in Ukraine still → UAH).
    assert prefs_from_locale_tag("en-UA") == ("en", "UAH")
    assert prefs_from_locale_tag("ru-KZ") == ("ru", "KZT")


def test_unknown_country_falls_back_to_usd() -> None:
    assert currency_from_locale_tag("en-NG") == FALLBACK_CURRENCY
    assert currency_from_locale_tag("fr-MA") == FALLBACK_CURRENCY
    assert currency_from_region("ZZ") is None
    # Language-only tag has no region → USD (do not guess from language).
    assert currency_from_locale_tag("uk") == FALLBACK_CURRENCY
    assert currency_from_locale_tag("uz") == FALLBACK_CURRENCY


def test_region_currency_mapping_table() -> None:
    cases = {
        "UA": "UAH",
        "US": "USD",
        "UZ": "UZS",
        "RU": "RUB",
        "KZ": "KZT",
        "BY": "BYN",
        "DE": "EUR",
        "FR": "EUR",
        "IT": "EUR",
        "ES": "EUR",
        "GB": "GBP",
        "UK": "GBP",
        "TR": "TRY",
        "PL": "PLN",
        "JP": "JPY",
        "CN": "CNY",
        "KR": "KRW",
        "IN": "INR",
        "ID": "IDR",
        "BR": "BRL",
        "AU": "AUD",
        "CA": "CAD",
        "CH": "CHF",
        "SE": "SEK",
        "MX": "MXN",
        "AE": "AED",
        "TW": "TWD",
        "HU": "HUF",
        "RO": "RON",
        "GE": "GEL",
    }
    for region, expected in cases.items():
        assert currency_from_region(region) == expected, region


def test_mapped_currencies_exist_in_fiat_catalog() -> None:
    catalog = catalog_fiat_codes()
    assert FALLBACK_CURRENCY in catalog
    missing = sorted(
        {code for code in _REGION_CURRENCY.values() if code not in catalog}
    )
    assert missing == []


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


def test_suggested_currency_prefers_locale_region_over_timezone() -> None:
    assert region_from_timezone("Asia/Tashkent") == "UZ"
    # Locale region RU wins over Tashkent timezone.
    assert suggested_currency_from_device(
        "ru_RU.UTF-8", timezone="Asia/Tashkent"
    ) == "RUB"
    # Language-only tag: timezone fills the missing region.
    assert suggested_currency_from_device("ru", timezone="Asia/Tashkent") == "UZS"
    assert suggested_currency_from_device("ru_RU", timezone="Europe/Moscow") == "RUB"
    assert currency_from_locale_tag("uz_UZ") == "UZS"
    assert language_from_locale_tag("ru") == "ru"
