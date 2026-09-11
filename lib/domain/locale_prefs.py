"""Map OS / UI locale tags + timezone to FinWise language + default currency."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Fallbacks when locale is missing or unrecognized.
# Unknown country / currency not in the fiat catalog → USD (global default, not EUR).
FALLBACK_LANGUAGE = "en"
FALLBACK_CURRENCY = "USD"

# IANA timezone → ISO 3166-1 alpha-2. Used only when the locale tag has no region.
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
    "Europe/Chisinau": "MD",
    "Europe/Moscow": "RU",
    "Europe/Kaliningrad": "RU",
    "Europe/Samara": "RU",
    "Asia/Yekaterinburg": "RU",
    "Asia/Novosibirsk": "RU",
    "Asia/Vladivostok": "RU",
    "Europe/Istanbul": "TR",
    "Europe/London": "GB",
    "Europe/Dublin": "IE",
    "Europe/Berlin": "DE",
    "Europe/Paris": "FR",
    "Europe/Madrid": "ES",
    "Europe/Rome": "IT",
    "Europe/Amsterdam": "NL",
    "Europe/Brussels": "BE",
    "Europe/Vienna": "AT",
    "Europe/Warsaw": "PL",
    "Europe/Prague": "CZ",
    "Europe/Budapest": "HU",
    "Europe/Bucharest": "RO",
    "Europe/Sofia": "BG",
    "Europe/Belgrade": "RS",
    "Atlantic/Reykjavik": "IS",
    "Europe/Stockholm": "SE",
    "Europe/Oslo": "NO",
    "Europe/Copenhagen": "DK",
    "Europe/Helsinki": "FI",
    "Europe/Athens": "GR",
    "Europe/Lisbon": "PT",
    "Europe/Zurich": "CH",
    "America/New_York": "US",
    "America/Los_Angeles": "US",
    "America/Chicago": "US",
    "America/Denver": "US",
    "America/Toronto": "CA",
    "America/Sao_Paulo": "BR",
    "America/Mexico_City": "MX",
    "America/Argentina/Buenos_Aires": "AR",
    "America/Santiago": "CL",
    "America/Bogota": "CO",
    "Asia/Tokyo": "JP",
    "Asia/Seoul": "KR",
    "Asia/Shanghai": "CN",
    "Asia/Hong_Kong": "HK",
    "Asia/Singapore": "SG",
    "Asia/Taipei": "TW",
    "Asia/Kolkata": "IN",
    "Asia/Jakarta": "ID",
    "Asia/Bangkok": "TH",
    "Asia/Kuala_Lumpur": "MY",
    "Asia/Manila": "PH",
    "Asia/Ho_Chi_Minh": "VN",
    "Asia/Dubai": "AE",
    "Asia/Riyadh": "SA",
    "Asia/Jerusalem": "IL",
    "Africa/Cairo": "EG",
    "Africa/Johannesburg": "ZA",
    "Australia/Sydney": "AU",
    "Pacific/Auckland": "NZ",
}

# ISO 3166-1 alpha-2 → ISO 4217. Only catalog fiat codes are applied at lookup.
# Countries whose tender is not in currencies.json are omitted (fallback USD).
_REGION_CURRENCY: dict[str, str] = {
    # USD
    "US": "USD",
    "PR": "USD",
    "GU": "USD",
    "AS": "USD",
    "VI": "USD",
    "MP": "USD",
    "UM": "USD",
    "EC": "USD",
    "SV": "USD",
    "PA": "USD",
    "TL": "USD",
    "MH": "USD",
    "FM": "USD",
    "PW": "USD",
    "BQ": "USD",
    "VG": "USD",
    "TC": "USD",
    "IO": "USD",
    # EUR (euro area + EUR-using territories / microstates)
    "AD": "EUR",
    "AT": "EUR",
    "AX": "EUR",
    "BE": "EUR",
    "BL": "EUR",
    "CY": "EUR",
    "DE": "EUR",
    "EE": "EUR",
    "ES": "EUR",
    "FI": "EUR",
    "FR": "EUR",
    "GF": "EUR",
    "GP": "EUR",
    "GR": "EUR",
    "HR": "EUR",
    "IE": "EUR",
    "IT": "EUR",
    "LT": "EUR",
    "LU": "EUR",
    "LV": "EUR",
    "MC": "EUR",
    "ME": "EUR",
    "MF": "EUR",
    "MQ": "EUR",
    "MT": "EUR",
    "NL": "EUR",
    "PM": "EUR",
    "PT": "EUR",
    "RE": "EUR",
    "SI": "EUR",
    "SK": "EUR",
    "SM": "EUR",
    "TF": "EUR",
    "VA": "EUR",
    "XK": "EUR",
    "YT": "EUR",
    "GB": "GBP",
    "UK": "GBP",
    "GG": "GBP",
    "JE": "GBP",
    "IM": "GBP",
    "CH": "CHF",
    "LI": "CHF",
    "JP": "JPY",
    "CN": "CNY",
    "CA": "CAD",
    "AU": "AUD",
    "CX": "AUD",
    "CC": "AUD",
    "NF": "AUD",
    "TV": "AUD",
    "KI": "AUD",
    "NZ": "NZD",
    "CK": "NZD",
    "NU": "NZD",
    "TK": "NZD",
    "SE": "SEK",
    "NO": "NOK",
    "SJ": "NOK",
    "BV": "NOK",
    "DK": "DKK",
    "GL": "DKK",
    "FO": "DKK",
    "PL": "PLN",
    "CZ": "CZK",
    "HU": "HUF",
    "TR": "TRY",
    "IN": "INR",
    "KR": "KRW",
    "SG": "SGD",
    "HK": "HKD",
    "TW": "TWD",
    "TH": "THB",
    "MY": "MYR",
    "ID": "IDR",
    "PH": "PHP",
    "VN": "VND",
    "BR": "BRL",
    "MX": "MXN",
    "AR": "ARS",
    "CL": "CLP",
    "CO": "COP",
    "ZA": "ZAR",
    "EG": "EGP",
    "AE": "AED",
    "SA": "SAR",
    "IL": "ILS",
    "RU": "RUB",
    "UZ": "UZS",
    "KZ": "KZT",
    "BY": "BYN",
    "UA": "UAH",
    "KG": "KGS",
    "TJ": "TJS",
    "AZ": "AZN",
    "AM": "AMD",
    "GE": "GEL",
    "MD": "MDL",
    "RO": "RON",
    "BG": "BGN",
    "RS": "RSD",
    "IS": "ISK",
}

# Language subtag → FinWise UI language (LTR set; RTL ar/he deferred → en).
_LANG_MAP: dict[str, str] = {
    "en": "en",
    "ru": "ru",
    "uk": "uk",
    "be": "be",
    "uz": "uz",
    "kk": "kk",
    "de": "de",
    "es": "es",
    "fr": "fr",
    "pt": "pt",
    "it": "it",
    "pl": "pl",
    "tr": "tr",
    "id": "id",
    "in": "id",  # legacy Indonesian
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "hi": "hi",
    # Close languages without a dedicated UI → Russian.
    "ky": "ru",
    "tg": "ru",
}


@lru_cache(maxsize=1)
def catalog_fiat_codes() -> frozenset[str]:
    """ISO codes from ``assets/data/currencies.json`` excluding crypto."""
    path = Path(__file__).resolve().parents[2] / "assets" / "data" / "currencies.json"
    codes: set[str] = {FALLBACK_CURRENCY}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return frozenset(codes)
    for item in data:
        if item.get("is_crypto"):
            continue
        code = str(item.get("code") or "").strip().upper()
        if code:
            codes.add(code)
    return frozenset(codes)


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
    """Map a locale tag to a live UI language (fallback English)."""
    lang, _region = parse_locale_parts(tag)
    if not lang:
        return FALLBACK_LANGUAGE
    mapped = _LANG_MAP.get(lang)
    if mapped:
        return mapped
    return FALLBACK_LANGUAGE


def currency_from_region(region: str | None) -> str | None:
    """Map ISO country code to a catalog fiat currency, or ``None`` if unknown."""
    if not region:
        return None
    mapped = _REGION_CURRENCY.get(region.upper())
    if not mapped:
        return None
    if mapped not in catalog_fiat_codes():
        return None
    return mapped


def currency_from_locale_and_timezone(
    tag: str | None,
    *,
    timezone: str | None = None,
) -> str:
    """Region from the locale tag wins; timezone fills in when region is missing."""
    _lang, region = parse_locale_parts(tag)
    mapped = currency_from_region(region)
    if mapped:
        return mapped
    tz_mapped = currency_from_region(region_from_timezone(timezone))
    if tz_mapped:
        return tz_mapped
    return FALLBACK_CURRENCY


def currency_from_locale_tag(tag: str | None) -> str:
    """Map a locale tag to a currency code (fallback USD)."""
    return currency_from_locale_and_timezone(tag)


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

    Language follows the OS/UI locale. Currency follows the **region**
    (``uk-UA`` → UAH, ``en-US`` → USD), not the language subtag. Timezone is
    used only when the tag has no country. Unknown region → **USD**.
    """
    return language_from_locale_tag(tag), currency_from_locale_and_timezone(
        tag, timezone=timezone
    )


def suggested_currency_from_device(
    tag: str | None = None,
    *,
    timezone: str | None = None,
) -> str:
    """Best-effort currency for first-run settings and the first-account picker."""
    return currency_from_locale_and_timezone(tag, timezone=timezone)
