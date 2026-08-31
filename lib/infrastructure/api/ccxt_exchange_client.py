"""Unified crypto-exchange client via ccxt (spot balances, trades, transfers)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from lib.domain.entities.money import quantize_money
from lib.domain.exchanges import ExchangeSpec, get_exchange

logger = logging.getLogger("finanse.infrastructure.api.ccxt_exchange")

_QUOTE_PREF = ("USDT", "USDC", "USD", "EUR", "BTC")
_AUTO_QUOTE = frozenset({"", "AUTO", "AUTODETECT"})
_CCXT_ALIASES: dict[str, tuple[str, ...]] = {
    "gateio": ("gate", "gateio"),
    "woo": ("woo", "woofipro"),
}


@dataclass
class Holding:
    """One asset on the venue."""

    asset: str
    amount: Decimal
    value: Decimal


@dataclass
class NormalizedTrade:
    """Spot fill mapped into FinWise money flow."""

    external_id: str
    kind: str
    side: str
    amount: Decimal
    currency: str
    date: datetime
    comment: str
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    symbol: str = ""


@dataclass
class Snapshot:
    """Balance + recent activity from an exchange."""

    total: Decimal
    currency: str
    holdings: list[Holding] = field(default_factory=list)
    trades: list[NormalizedTrade] = field(default_factory=list)


class ExchangeClientError(RuntimeError):
    """Raised when the venue cannot be queried."""


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _pick_quote(totals: Any, requested: str = "AUTO") -> str:
    """Use an explicit quote, or the first preferred asset the wallet actually holds."""
    requested = (requested or "AUTO").strip().upper()
    if requested not in _AUTO_QUOTE:
        return requested
    data = totals if isinstance(totals, dict) else {}
    for pref in _QUOTE_PREF:
        raw = data.get(pref)
        if raw is None:
            raw = data.get(pref.lower())
        if _as_decimal(raw) > 0:
            return pref
    return "USDT"


def _ts(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        ms = int(value or 0)
    except (TypeError, ValueError):
        ms = 0
    if ms > 10_000_000_000:
        ms = ms // 1000
    if ms <= 0:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ms, tz=timezone.utc)


def _load_ccxt():
    try:
        import ccxt  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        # Packaged builds ship the mobile-safe wheel under vendor/wheels/.
        raise ExchangeClientError("error.exchange_unavailable") from exc
    return ccxt


def build_exchange(
    spec: ExchangeSpec,
    *,
    api_key: str,
    secret: str,
    passphrase: str = "",
):
    """Instantiate a ccxt exchange with spot defaults."""
    ccxt = _load_ccxt()
    candidates = (spec.ccxt_id,) + _CCXT_ALIASES.get(spec.id, ())
    cls = None
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        cls = getattr(ccxt, name, None)
        if cls is not None:
            break
    if cls is None:
        if spec.id == "bitmart":
            raise ExchangeClientError(
                "BitMart is shutting down and no longer supports API sync"
            )
        raise ExchangeClientError(f"Unsupported exchange: {spec.title}")
    params: dict[str, Any] = {
        "apiKey": (api_key or "").strip(),
        "secret": (secret or "").strip(),
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }
    if passphrase:
        params["password"] = passphrase.strip()
    if spec.uses_wallet:
        params["walletAddress"] = (api_key or "").strip()
        params["privateKey"] = (secret or "").strip()
    return cls(params)


def _ticker_price(exchange, symbol: str) -> Optional[Decimal]:
    try:
        ticker = exchange.fetch_ticker(symbol)
    except Exception:  # noqa: BLE001
        return None
    last = ticker.get("last") or ticker.get("close")
    if last is None:
        return None
    price = _as_decimal(last)
    return price if price > 0 else None


def _value_in_quote(exchange, asset: str, amount: Decimal, quote: str) -> Decimal:
    if amount <= 0:
        return Decimal("0")
    if asset.upper() == quote.upper():
        return amount
    for symbol in (f"{asset}/{quote}", f"{quote}/{asset}"):
        price = _ticker_price(exchange, symbol)
        if price is None:
            continue
        if symbol.startswith(f"{quote}/"):
            if price == 0:
                continue
            return amount / price
        return amount * price
    return Decimal("0")


def fetch_snapshot(
    *,
    provider: str,
    api_key: str,
    secret: str,
    passphrase: str = "",
    quote: str = "USDT",
    trade_limit: int = 200,
) -> Snapshot:
    """Pull spot balances and recent fills (blocking — call via to_thread)."""
    spec = get_exchange(provider)
    if spec is None:
        raise ExchangeClientError(f"Unknown exchange: {provider}")
    exchange = build_exchange(
        spec, api_key=api_key, secret=secret, passphrase=passphrase
    )
    try:
        raw_balance = exchange.fetch_balance()
    except Exception as exc:  # noqa: BLE001
        logger.exception("fetch_balance failed for %s", provider)
        raise ExchangeClientError(str(exc) or spec.title) from exc

    totals = raw_balance.get("total") or {}
    quote = _pick_quote(totals, quote)
    holdings: list[Holding] = []
    total_value = Decimal("0")
    for asset, raw_amount in totals.items():
        if not isinstance(asset, str) or asset.startswith("USD"):
            pass
        amount = _as_decimal(raw_amount)
        if amount <= 0:
            continue
        code = asset.upper()
        if code in {"USDT", "USDC", "BUSD", "FDUSD", "DAI"} and quote in {
            "USDT",
            "USDC",
            "USD",
        }:
            value = amount
        else:
            value = _value_in_quote(exchange, code, amount, quote)
        if value <= 0 and code != quote:
            continue
        if code == quote:
            value = amount
        holdings.append(Holding(asset=code, amount=amount, value=quantize_money(value)))
        total_value += value

    holdings.sort(key=lambda item: item.value, reverse=True)

    trades: list[NormalizedTrade] = []
    try:
        raw_trades = exchange.fetch_my_trades(symbol=None, since=None, limit=trade_limit)
    except Exception:  # noqa: BLE001
        logger.debug("fetch_my_trades(all) failed for %s, skipping bulk", provider)
        raw_trades = []
        try:
            markets = list((exchange.markets or exchange.load_markets()).keys())[:12]
        except Exception:  # noqa: BLE001
            markets = []
        for symbol in markets:
            try:
                raw_trades.extend(
                    exchange.fetch_my_trades(symbol=symbol, limit=min(50, trade_limit))
                )
            except Exception:  # noqa: BLE001
                continue
    for item in raw_trades[:trade_limit]:
        mapped = _map_trade(item, quote=quote)
        if mapped is not None:
            trades.append(mapped)

    for kind, fetcher in (
        ("deposit", getattr(exchange, "fetch_deposits", None)),
        ("withdrawal", getattr(exchange, "fetch_withdrawals", None)),
    ):
        if fetcher is None:
            continue
        try:
            rows = fetcher(limit=min(50, trade_limit))
        except Exception:  # noqa: BLE001
            continue
        for item in rows or []:
            mapped = _map_transfer(item, kind=kind, quote=quote, exchange=exchange)
            if mapped is not None:
                trades.append(mapped)

    trades.sort(key=lambda item: item.date)
    return Snapshot(
        total=quantize_money(total_value),
        currency=quote,
        holdings=holdings[:24],
        trades=trades,
    )


def _map_trade(item: dict[str, Any], *, quote: str) -> Optional[NormalizedTrade]:
    side = str(item.get("side") or "").lower()
    if side not in {"buy", "sell"}:
        return None
    cost = _as_decimal(item.get("cost"))
    symbol = str(item.get("symbol") or "")
    fee_info = item.get("fee") or {}
    fee = _as_decimal(fee_info.get("cost") if isinstance(fee_info, dict) else 0)
    fee_ccy = str((fee_info.get("currency") if isinstance(fee_info, dict) else "") or "")
    if cost <= 0:
        price = _as_decimal(item.get("price"))
        amount = _as_decimal(item.get("amount"))
        cost = price * amount
    if cost <= 0:
        return None
    ext = str(item.get("id") or item.get("order") or "")
    if not ext:
        ext = f"{symbol}:{item.get('timestamp')}:{side}:{cost}"
    ts = item.get("datetime") or item.get("timestamp")
    if isinstance(ts, str):
        try:
            date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except ValueError:
            date = _ts(item.get("timestamp"))
    else:
        date = _ts(ts)
    return NormalizedTrade(
        external_id=ext,
        kind="trade",
        side=side,
        amount=quantize_money(cost),
        currency=quote,
        date=date,
        comment=f"{side.upper()} {symbol}".strip(),
        fee=quantize_money(fee) if fee > 0 else Decimal("0"),
        fee_currency=fee_ccy.upper(),
        symbol=symbol,
    )


def _map_transfer(
    item: dict[str, Any],
    *,
    kind: str,
    quote: str,
    exchange,
) -> Optional[NormalizedTrade]:
    amount = _as_decimal(item.get("amount"))
    asset = str(item.get("currency") or item.get("code") or quote).upper()
    if amount <= 0:
        return None
    value = amount if asset == quote else _value_in_quote(exchange, asset, amount, quote)
    if value <= 0:
        value = amount
    ext = str(item.get("id") or item.get("txid") or "")
    if not ext:
        ext = f"{kind}:{asset}:{item.get('timestamp')}:{amount}"
    status = str(item.get("status") or "ok").lower()
    if status in {"canceled", "cancelled", "failed", "rejected"}:
        return None
    return NormalizedTrade(
        external_id=ext,
        kind=kind,
        side="buy" if kind == "deposit" else "sell",
        amount=quantize_money(value),
        currency=quote,
        date=_ts(item.get("timestamp") or item.get("datetime")),
        comment=f"{kind} {asset}",
        symbol=asset,
    )


def test_credentials(
    *,
    provider: str,
    api_key: str,
    secret: str,
    passphrase: str = "",
) -> None:
    """Raise :class:`ExchangeClientError` if keys cannot read a balance."""
    spec = get_exchange(provider)
    if spec is None:
        raise ExchangeClientError(f"Unknown exchange: {provider}")
    exchange = build_exchange(
        spec, api_key=api_key, secret=secret, passphrase=passphrase
    )
    try:
        exchange.fetch_balance()
    except Exception as exc:  # noqa: BLE001
        raise ExchangeClientError(str(exc) or spec.title) from exc
