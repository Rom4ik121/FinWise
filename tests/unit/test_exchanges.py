"""Exchange catalog and idempotency tags."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.domain.exchanges import EXCHANGES, EXCHANGE_BY_ID, exchange_title, get_exchange
from lib.domain.use_cases.exchange_sync import ext_tag
from lib.infrastructure.api.ccxt_exchange_client import (
    ExchangeClientError,
    _map_trade,
    _pick_quote,
    build_exchange,
)


def test_catalog_covers_requested_venues() -> None:
    titles = {spec.title for spec in EXCHANGES}
    assert titles == {
        "Binance",
        "Coinbase",
        "OKX",
        "Bybit",
        "Kraken",
        "KuCoin",
        "Gate.io",
        "Bitget",
        "MEXC",
        "BitMart",
        "HTX",
        "Hyperliquid",
        "BitMEX",
        "WOO X",
        "Crypto.com",
        "Bitfinex",
        "Bitstamp",
        "BingX",
        "HashKey Global",
        "CEX.IO",
    }
    assert len(EXCHANGE_BY_ID) == len(EXCHANGES)
    assert get_exchange("Binance") is not None
    assert get_exchange("unknown") is None
    assert exchange_title("binance") == "Binance"
    assert exchange_title("missing") == "missing"
    assert get_exchange("okx").needs_passphrase
    assert get_exchange("hyperliquid").uses_wallet
    from lib.domain.exchanges import WEB3_ICONS

    assert "binance" in WEB3_ICONS
    assert "bingx" not in WEB3_ICONS


def test_ext_tag_is_stable() -> None:
    assert ext_tag("binance", "trade", "abc") == "ext:binance:trade:abc"


def test_ccxt_ids_resolve() -> None:
    ccxt = pytest.importorskip("ccxt")
    missing = []
    for spec in EXCHANGES:
        if spec.id == "bitmart":
            continue
        names = (spec.ccxt_id,)
        if not any(hasattr(ccxt, name) for name in names):
            missing.append(spec.ccxt_id)
    assert missing == []


def test_map_trade_buy_and_sell() -> None:
    buy = _map_trade(
        {
            "id": "1",
            "side": "buy",
            "cost": "12.5",
            "symbol": "BTC/USDT",
            "timestamp": 1_700_000_000_000,
            "fee": {"cost": "0.1", "currency": "USDT"},
        },
        quote="USDT",
    )
    assert buy is not None
    assert buy.side == "buy"
    assert buy.amount == Decimal("12.50")
    sell = _map_trade(
        {"id": "2", "side": "sell", "price": "2", "amount": "3", "symbol": "ETH/USDT"},
        quote="USDT",
    )
    assert sell is not None
    assert sell.side == "sell"
    assert sell.amount == Decimal("6.00")


def test_pick_quote_from_holdings() -> None:
    assert _pick_quote({"BTC": 1, "EUR": 20}, "AUTO") == "EUR"
    assert _pick_quote({"usdt": "12.5", "BTC": 1}, "AUTO") == "USDT"
    assert _pick_quote({"BTC": 1}, "AUTO") == "BTC"
    assert _pick_quote({}, "AUTO") == "USDT"
    assert _pick_quote({"EUR": 10}, "USD") == "USD"


def test_bitmart_reports_unavailable() -> None:
    ccxt = pytest.importorskip("ccxt")
    spec = get_exchange("bitmart")
    assert spec is not None
    if hasattr(ccxt, "bitmart"):
        assert build_exchange(spec, api_key="k", secret="s") is not None
        return
    with pytest.raises(ExchangeClientError, match="BitMart"):
        build_exchange(spec, api_key="k", secret="s")


def test_is_auth_failure_detects_bingx_key_error() -> None:
    from lib.infrastructure.api.ccxt_exchange_client import (
        INVALID_CREDENTIALS,
        is_auth_failure,
        _raise_client_error,
    )

    exc = RuntimeError(
        'bingx {"code":100413,"msg":"Incorrect apiKey, please check your valid '
        'api key in https://bingx.com/en/account/api"}'
    )
    assert is_auth_failure(exc) is True
    with pytest.raises(ExchangeClientError, match=INVALID_CREDENTIALS):
        _raise_client_error(exc, provider="bingx")


def test_user_facing_maps_exchange_credentials() -> None:
    from lib.presentation.utils import user_facing_error

    msg = user_facing_error("Invalid exchange API credentials", "en")
    assert "key" in msg.lower()
    assert "bingx" not in msg.lower()


def test_user_facing_maps_common_domain_errors() -> None:
    from lib.presentation.utils import user_facing_error

    assert "limit" in user_facing_error("Budget limit must be positive", "en").lower()
    assert "comment" in user_facing_error(
        "Transfer legs cannot be edited independently", "en"
    ).lower()
    assert "archive" in user_facing_error("Only paid debts can be archived", "en").lower()
    assert "categories" in user_facing_error(
        "System categories cannot be deleted", "en"
    ).lower()
