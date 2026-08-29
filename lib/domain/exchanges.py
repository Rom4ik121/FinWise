"""Catalog of supported spot exchanges (ccxt ids)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeSpec:
    """One connected exchange / crypto venue."""

    id: str
    title: str
    ccxt_id: str
    needs_passphrase: bool = False
    uses_wallet: bool = False
    icon: str = "token"
    color: str = "#F59E0B"


EXCHANGES: tuple[ExchangeSpec, ...] = (
    ExchangeSpec("binance", "Binance", "binance", color="#F3BA2F"),
    ExchangeSpec("coinbase", "Coinbase", "coinbase", needs_passphrase=True, color="#0052FF"),
    ExchangeSpec("okx", "OKX", "okx", needs_passphrase=True, color="#000000"),
    ExchangeSpec("bybit", "Bybit", "bybit", color="#F7A600"),
    ExchangeSpec("kraken", "Kraken", "kraken", color="#5741D9"),
    ExchangeSpec("kucoin", "KuCoin", "kucoin", needs_passphrase=True, color="#23AF91"),
    ExchangeSpec("gateio", "Gate.io", "gate", color="#17E5A1"),
    ExchangeSpec("bitget", "Bitget", "bitget", needs_passphrase=True, color="#00F0FF"),
    ExchangeSpec("mexc", "MEXC", "mexc", color="#1E4DFF"),
    ExchangeSpec("bitmart", "BitMart", "bitmart", color="#00C2B2"),
    ExchangeSpec("htx", "HTX", "htx", color="#2EBD85"),
    ExchangeSpec(
        "hyperliquid",
        "Hyperliquid",
        "hyperliquid",
        uses_wallet=True,
        color="#50D2C1",
    ),
    ExchangeSpec("bitmex", "BitMEX", "bitmex", color="#E3B23C"),
    ExchangeSpec("woo", "WOO X", "woo", color="#8B5CF6"),
    ExchangeSpec("cryptocom", "Crypto.com", "cryptocom", color="#103F68"),
    ExchangeSpec("bitfinex", "Bitfinex", "bitfinex", color="#16B157"),
    ExchangeSpec("bitstamp", "Bitstamp", "bitstamp", color="#1B3A4B"),
    ExchangeSpec("bingx", "BingX", "bingx", color="#0047FF"),
    ExchangeSpec("hashkey", "HashKey Global", "hashkey", color="#0B5FFF"),
    ExchangeSpec("cex", "CEX.IO", "cex", color="#00B4E6"),
)

EXCHANGE_BY_ID: dict[str, ExchangeSpec] = {item.id: item for item in EXCHANGES}


def get_exchange(exchange_id: str) -> ExchangeSpec | None:
    """Look up a catalog entry."""
    return EXCHANGE_BY_ID.get((exchange_id or "").strip().lower())


def exchange_title(exchange_id: str) -> str:
    """Human-readable venue name, or the raw id if unknown."""
    spec = get_exchange(exchange_id)
    return spec.title if spec is not None else (exchange_id or "").strip()


# SVGs from https://github.com/0xa3k5/web3icons (MIT).
# Tuple is (folder, file stem, variant). BingX and CEX.IO are not in that set.
WEB3_ICONS: dict[str, tuple[str, str, str]] = {
    "binance": ("exchanges", "binance", "background"),
    "coinbase": ("exchanges", "coinbase", "background"),
    "okx": ("exchanges", "okx", "background"),
    "bybit": ("exchanges", "bybit", "background"),
    "kraken": ("exchanges", "kraken", "background"),
    "kucoin": ("exchanges", "kucoin", "background"),
    "gateio": ("exchanges", "gate-io", "background"),
    "bitget": ("exchanges", "bitget", "background"),
    "cryptocom": ("exchanges", "crypto-com", "background"),
    "bitstamp": ("exchanges", "bitstamp", "background"),
    "hyperliquid": ("networks", "hyper-evm", "background"),
    "hashkey": ("networks", "hashkey", "background"),
    "htx": ("tokens", "HT", "background"),
    "mexc": ("tokens", "MX", "background"),
    "woo": ("tokens", "WOO", "mono"),
    "bitfinex": ("tokens", "LEO", "background"),
    "bitmart": ("tokens", "BMX", "background"),
    "bitmex": ("tokens", "BMEX", "background"),
}
