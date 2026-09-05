"""Map OS / UI locale tags + timezone to FinWise language + default currency."""

from __future__ import annotations

# Fallbacks when locale is missing or unrecognized.
FALLBACK_LANGUAGE = "en"
FALLBACK_CURRENCY = "USD"

# IANA timezone → ISO 3166-1 alpha-2 (where people live; beats OS language region).
_TZ_REGION: dict[str, str] = {
    "Asia/Tashkent": "UZ",
    "Asia/Samarkand": "UZ",
    "Asia/Almaty": "KZ",
    "Asia/Aqtobe": "KZ",
    "Asia/Atyrau": "KZ",
    "Asia/Oral": "KZ",
    "Asia/Qostanay": "KZ",
    "Asia/Qyzylorda": "KZ",
    "Asia/Bishkek": "KG",
    "Asia/Dushanbe": "TJ",
    "Asia/Ashgabat": "TM",
    "Asia/Baku": "AZ",
    "Asia/Yerevan": "AM",
    "Asia/Tbilisi": "GE",
    "Europe/Minsk": "BY",
    "Europe/Kyiv": "UA",
    "Europe/Kiev": "UA",
    "Europe/Moscow": "RU",
    "Europe/Kaliningrad": "RU",
    "Europe/Samara": "RU",
    "Asia/Yekaterinburg": "RU",
    "Asia/Novosibirsk": "RU",
    "Asia/Vladivostok": "RU",
    "Europe/Istanbul": "TR",
    "Europe/London": "GB",
    "Europe/Berlin": "DE",
    "Europe/Paris": "FR",
    "America/New_York": "US",
    "America/Los_Angeles": "US",
    "America/Chicago": "US",
    "America/Toronto": "CA",
    "Asia/Tokyo": "JP",
    "Asia/Shanghai": "CN",
    "Asia/Dubai": "AE",
    "Australia/Sydney": "AU",
}

# ISO 3166-1 alpha-2 → ISO 4217 (common personal-finance regions).
_REGION_CURRENCY: dict[str, str] = {
    "US": "USD",
    "PR": "USD",
    "GU": "USD",
    "AS": "USD",
    "VI": "USD",
    "GB": "GBP",
    "UK": "GBP",
    "IE": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "PT": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "FI": "EUR",
    "GR": "EUR",
    "SK": "EUR",
    "SI": "EUR",
    "EE": "EUR",
    "LV": "EUR",
    "LT": "EUR",
    "LU": "EUR",
    "MT": "EUR",
    "CY": "EUR",
    "HR": "EUR",
    "RU": "RUB",
    "UZ": "UZS",
    "KZ": "KZT",
    "BY": "BYN",
    "UA": "UAH",
    "KG": "KGS",
    "TJ": "TJS",
    "TM": "TMT",
    "AZ": "AZN",
    "AM": "AMD",
    "GE": "GEL",
    "TR": "TRY",
    "CN": "CNY",
    "JP": "JPY",
    "KR": "KRW",
    "IN": "INR",
    "AE": "AED",
    "SA": "SAR",
    "CH": "CHF",
    "PL": "PLN",
    "CZ": "CZK",
    "SE": "SEK",
    "NO": "NOK",
    "DK": "DKK",
    "CA": "CAD",
    "AU": "AUD",
    "NZ": "NZD",
    "BR": "BRL",
    "MX": "MXN",
    "SG": "SGD",
    "HK": "HKD",
    "IL": "ILS",
    "EG": "EGP",
    "ZA": "ZAR",
}

# Language subtag → FinWise UI language (only ru / en / uz are live).
_LANG_MAP: dict[str, str] = {
    "en": "en",
    "ru": "ru",
    "uz": "uz",
    # Close languages → Russian UI until more locales are wired.
    "be": "ru",
    "uk": "ru",
    "kk": "ru",
    "ky": "ru",
    "tg": "ru",
}


def _normalize_tag(tag: str | None) -> str:
    text = (tag or "").strip().replace("_", "-")
    if not text:
        return ""
    # OS tags often look like ``ru_RU.UTF-8`` / ``en_US.utf8`` — drop encoding.
    if "." in text:
        text = text.split(".", 1)[0]
    return text.strip()


def parse_locale_parts(tag: str | None) -> tuple[str, str]:
    """Return ``(language, region)`` lower/upper; empty strings if unknown."""
    text = _normalize_tag(tag)
    if not text:
        return "", ""
    parts = [p for p in text.split("-") if p]
    lang = parts[0].lower()
    region = ""
    for part in parts[1:]:
        # Prefer ISO region (2 letters); skip script tags like Latn/Cyrl.
        if len(part) == 2 and part.isalpha():
            region = part.upper()
    return lang, region


def language_from_locale_tag(tag: str | None) -> str:
    """Map a locale tag to ``ru`` / ``en`` / ``uz`` (fallback English)."""
    lang, _region = parse_locale_parts(tag)
    if not lang:
        return FALLBACK_LANGUAGE
    mapped = _LANG_MAP.get(lang)
    if mapped:
        return mapped
    return FALLBACK_LANGUAGE


def currency_from_region(region: str | None) -> str | None:
    """Map ISO country code to currency, or ``None`` if unknown."""
    if not region:
        return None
    return _REGION_CURRENCY.get(region.upper())


def currency_from_locale_tag(tag: str | None) -> str:
    """Map a locale tag to a currency code (fallback USD)."""
    _lang, region = parse_locale_parts(tag)
    mapped = currency_from_region(region)
    if mapped:
        return mapped
    return FALLBACK_CURRENCY


def region_from_timezone(tz_name: str | None) -> str | None:
    """Map IANA timezone (e.g. ``Asia/Tashkent``) to a country code."""
    key = (tz_name or "").strip()
    if not key:
        return None
    return _TZ_REGION.get(key)


def prefs_from_locale_tag(
    tag: str | None,
    *,
    timezone: str | None = None,
) -> tuple[str, str]:
    """Return ``(language, currency)`` for first-run defaults.

    Language follows the OS/UI locale. Currency stays at the USD fallback —
    the first created account sets the real display currency once.
    ``timezone`` is accepted for API compatibility / suggested picker use.
    """
    _ = timezone
    return language_from_locale_tag(tag), FALLBACK_CURRENCY


def suggested_currency_from_device(
    tag: str | None = None,
    *,
    timezone: str | None = None,
) -> str:
    """Best-effort currency for the first-account picker (not written to settings)."""
    tz_currency = currency_from_region(region_from_timezone(timezone))
    if tz_currency:
        return tz_currency
    return currency_from_locale_tag(tag)
