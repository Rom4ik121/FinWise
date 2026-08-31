"""Account icon keys: thematic Material icons + currency/crypto glyphs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import flet as ft

from lib.core.config import ACCOUNT_ICON_GROUPS, ACCOUNT_ICONS
from lib.presentation.icon_registry import resolve_icon

CURRENCY_ICON_PREFIX = "ccy_"
EXCHANGE_ICON_PREFIX = "exch_"


def currency_icon_key(code: str) -> str:
    """Build a stored icon key for a currency code."""
    return f"{CURRENCY_ICON_PREFIX}{code.strip().upper()}"


def parse_currency_icon_key(key: str | None) -> str | None:
    """Return currency code when ``key`` is a currency glyph key."""
    if not key or not key.startswith(CURRENCY_ICON_PREFIX):
        return None
    code = key[len(CURRENCY_ICON_PREFIX) :].strip().upper()
    return code or None


def exchange_icon_key(exchange_id: str) -> str:
    """Stored icon key for a catalog exchange."""
    return f"{EXCHANGE_ICON_PREFIX}{(exchange_id or '').strip().lower()}"


def parse_exchange_icon_key(key: str | None) -> str | None:
    """Return exchange id when ``key`` is an exchange logo key."""
    if not key or not key.startswith(EXCHANGE_ICON_PREFIX):
        return None
    exchange_id = key[len(EXCHANGE_ICON_PREFIX) :].strip().lower()
    return exchange_id or None


def _exchange_icon_file(exchange_id: str) -> Path | None:
    name = f"{(exchange_id or '').strip().lower()}.png"
    bundled = Path(__file__).resolve().parents[2] / "assets" / "icons" / "exchanges" / name
    if bundled.is_file():
        return bundled
    rel = Path("assets") / "icons" / "exchanges" / name
    if rel.is_file():
        return rel.resolve()
    return None


def exchange_icon_src(exchange_id: str) -> str | None:
    """Filesystem path for a vendored web3icons PNG, if present."""
    path = _exchange_icon_file(exchange_id)
    return str(path) if path is not None else None


def _crypto_icons_dir() -> Path:
    bundled = Path(__file__).resolve().parents[2] / "assets" / "icons" / "crypto"
    if bundled.is_dir():
        return bundled
    rel = Path("assets") / "icons" / "crypto"
    return rel.resolve() if rel.is_dir() else bundled


def _crypto_icon_file(code: str) -> Path | None:
    name = f"{(code or '').strip().upper()}.png"
    path = _crypto_icons_dir() / name
    return path if path.is_file() else None


def crypto_icon_src(code: str) -> str | None:
    """Filesystem path for a vendored token PNG, if present."""
    path = _crypto_icon_file(code)
    return str(path) if path is not None else None


def exchange_logo_fills_badge(exchange_id: str) -> bool:
    """True when the PNG is a full-bleed colored badge."""
    from lib.domain.exchanges import WEB3_ICONS

    source = WEB3_ICONS.get((exchange_id or "").strip().lower())
    return bool(source and source[2] == "background")


def exchange_icon_keys() -> tuple[str, ...]:
    from lib.domain.exchanges import EXCHANGES

    return tuple(exchange_icon_key(spec.id) for spec in EXCHANGES)


def resolve_account_icon_key(icon: str | None, exchange_id: str = "") -> str:
    """Prefer a vendored exchange logo when the account is linked to a venue."""
    current = (icon or "").strip()
    if parse_exchange_icon_key(current):
        return current
    provider = (exchange_id or "").strip().lower()
    if provider:
        key = exchange_icon_key(provider)
        if is_valid_account_icon(key):
            return key
    return current or "wallet"


def account_icon_badge(
    key: str | None,
    *,
    color: str,
    size: float = 46,
    glyph_size: float = 24,
    glyph_color: str | None = None,
) -> ft.Container:
    """Rounded badge: full-bleed exchange/token PNG or tinted Material/currency glyph."""
    fills = icon_is_logo(key)
    clip = getattr(ft, "ClipBehavior", None)
    kwargs: dict = {}
    if clip is not None:
        kwargs["clip_behavior"] = clip.ANTI_ALIAS
    return ft.Container(
        width=size,
        height=size,
        border_radius=999 if fills else (14 if size >= 40 else 12),
        alignment=ft.Alignment.CENTER,
        bgcolor=None if fills else color,
        content=account_icon_control(
            key,
            size=size if fills else glyph_size,
            color=glyph_color,
        ),
        **kwargs,
    )


def _currencies_json_path() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "data" / "currencies.json"


@lru_cache(maxsize=1)
def _currency_catalog() -> tuple[dict[str, str], ...]:
    path = _currencies_json_path()
    if not path.exists():
        return (
            {"code": "RUB", "symbol": "₽", "is_crypto": "0"},
            {"code": "USD", "symbol": "$", "is_crypto": "0"},
            {"code": "EUR", "symbol": "€", "is_crypto": "0"},
            {"code": "BTC", "symbol": "₿", "is_crypto": "1"},
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for item in data:
        rows.append(
            {
                "code": str(item["code"]).upper(),
                "symbol": str(item.get("symbol") or item["code"]),
                "is_crypto": "1" if item.get("is_crypto") else "0",
            }
        )
    return tuple(rows)


# Distinct 1–2 character marks for well-known coins (catalog tiles).
_CRYPTO_GLYPHS: dict[str, str] = {
    "BTC": "₿",
    "ETH": "Ξ",
    "USDT": "₮",
    "USDC": "$",
    "BNB": "B",
    "XRP": "✕",
    "SOL": "S",
    "TRX": "T",
    "DOGE": "Ð",
    "LTC": "Ł",
    "XMR": "ɱ",
    "ZEC": "ⓩ",
    "ADA": "A",
    "DOT": "●",
    "TON": "◎",
    "SHIB": "š",
    "PEPE": "P",
    "DAI": "◈",
    "LINK": "⬡",
    "AVAX": "A",
    "MATIC": "M",
    "POL": "M",
    "ATOM": "⚛",
    "XLM": "*",
    "BCH": "฿",
    "ETC": "ξ",
    "FIL": "⨎",
    "UNI": "U",
    "AAVE": "A",
    "NEAR": "N",
    "APT": "A",
    "ARB": "A",
    "SUI": "S",
    "HBAR": "ℏ",
    "CRO": "C",
    "OKB": "O",
    "KCS": "K",
    "ALGO": "A",
    "QNT": "Q",
    "RENDER": "R",
    "JUP": "J",
    "PI": "π",
    "KAS": "K",
    "MNT": "M",
    "TAO": "τ",
    "PAXG": "Au",
    "XAUT": "Au",
}


def currency_glyph_label(code: str, symbol: str | None = None) -> str:
    """Short label for a currency tile (symbol if compact, else ticker)."""
    code = code.upper()
    glyph = _CRYPTO_GLYPHS.get(code)
    if glyph:
        return glyph
    if symbol is None:
        for row in _currency_catalog():
            if row["code"] == code:
                symbol = row["symbol"]
                break
    text = (symbol or code).strip()
    if text and len(text) <= 2:
        return text
    if text and len(text) <= 3 and not text.isascii():
        return text
    return code if len(code) <= 4 else code[:4]


def account_icon_groups(*, include_exchanges: bool = True) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Thematic groups plus fiat / crypto currency glyph groups.

    Exchange logos are omitted for regular (manual) account pickers.
    """
    fiat_keys: list[str] = []
    crypto_keys: list[str] = []
    for row in _currency_catalog():
        key = currency_icon_key(row["code"])
        if row["is_crypto"] == "1":
            crypto_keys.append(key)
        else:
            fiat_keys.append(key)
    extra: list[tuple[str, tuple[str, ...]]] = []
    if fiat_keys:
        extra.append(("icon_group.fiat", tuple(fiat_keys)))
    if crypto_keys:
        extra.append(
            ("icon_group.crypto", tuple(crypto_keys) + extra_crypto_icon_keys())
        )
    if include_exchanges:
        extra.append(("icon_group.exchanges", exchange_icon_keys()))
    return ACCOUNT_ICON_GROUPS + tuple(extra)


def icon_is_logo(key: str | None) -> bool:
    """True when the key resolves to a vendored PNG (token or exchange)."""
    exchange_id = parse_exchange_icon_key(key)
    if exchange_id and exchange_icon_src(exchange_id):
        return True
    code = parse_currency_icon_key(key)
    return bool(code and crypto_icon_src(code))


def catalog_icon_control(
    key: str | None,
    *,
    tile_size: float = 48,
    glyph_size: float = 22,
    glyph_color: str | None = None,
) -> ft.Control:
    """Icon for catalog grids: logos clipped to a circle that fills the tile."""
    if icon_is_logo(key):
        return ft.Container(
            width=tile_size,
            height=tile_size,
            border_radius=999,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=account_icon_control(key, size=tile_size),
        )
    return account_icon_control(
        key,
        size=glyph_size,
        color=glyph_color,
    )


def all_account_icon_keys() -> tuple[str, ...]:
    """Flat unique list of valid account icon keys (themes + currencies)."""
    keys: list[str] = list(ACCOUNT_ICONS)
    for _label, group in account_icon_groups():
        keys.extend(group)
    return tuple(dict.fromkeys(keys))


def extra_crypto_icon_keys() -> tuple[str, ...]:
    """Token logos on disk that are not already in the currency catalog."""
    folder = _crypto_icons_dir()
    if not folder.is_dir():
        return ()
    known = {
        row["code"] for row in _currency_catalog() if row["is_crypto"] == "1"
    }
    extras: list[str] = []
    for path in sorted(folder.glob("*.png")):
        code = path.stem.strip().upper()
        if code and code not in known:
            extras.append(currency_icon_key(code))
    return tuple(extras)


def crypto_icon_keys() -> tuple[str, ...]:
    """Stored keys for every crypto ticker in the bundled catalog."""
    return tuple(
        currency_icon_key(row["code"])
        for row in _currency_catalog()
        if row["is_crypto"] == "1"
    )


def is_valid_account_icon(key: str | None) -> bool:
    if not key:
        return False
    if key in ACCOUNT_ICONS:
        return True
    if parse_currency_icon_key(key) is not None:
        return True
    from lib.domain.exchanges import get_exchange

    return get_exchange(parse_exchange_icon_key(key) or "") is not None


def account_icon_control(
    key: str | None,
    *,
    size: float = 20,
    color: str | None = None,
) -> ft.Control:
    """Build an Icon, currency glyph, or exchange logo for a stored icon key."""
    exchange_id = parse_exchange_icon_key(key)
    if exchange_id is not None:
        src = exchange_icon_src(exchange_id)
        if src:
            return ft.Image(
                src=src,
                width=size,
                height=size,
                fit=ft.BoxFit.COVER,
            )
        return ft.Icon(
            resolve_icon("token", default="token"),
            size=size,
            color=color,
        )
    code = parse_currency_icon_key(key)
    if code is not None:
        src = crypto_icon_src(code)
        if src:
            return ft.Image(
                src=src,
                width=size,
                height=size,
                fit=ft.BoxFit.COVER,
            )
        label = currency_glyph_label(code)
        # Compact codes (USDT, MATIC) need a smaller type size.
        if len(label) >= 4:
            font_size = max(8, int(size * 0.38))
        elif len(label) == 3:
            font_size = max(9, int(size * 0.45))
        else:
            font_size = max(11, int(size * 0.58))
        return ft.Text(
            label,
            size=font_size,
            weight=ft.FontWeight.W_700,
            color=color,
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
        )
    return ft.Icon(
        resolve_icon(key, default="wallet"),
        size=size,
        color=color,
    )
