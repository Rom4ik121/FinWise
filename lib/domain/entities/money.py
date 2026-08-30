"""Money and rate quantization helpers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from lib.core.config import (
    CRYPTO_CURRENCY_CODES,
    CRYPTO_MONEY_QUANTIZE,
    CRYPTO_RATE_QUANTIZE,
    FIAT_RATE_QUANTIZE,
    MONEY_QUANTIZE,
)

_MONEY_Q = Decimal(MONEY_QUANTIZE)
_CRYPTO_MONEY_Q = Decimal(CRYPTO_MONEY_QUANTIZE)
_FIAT_RATE_Q = Decimal(FIAT_RATE_QUANTIZE)
_CRYPTO_Q = Decimal(CRYPTO_RATE_QUANTIZE)


def is_crypto_currency(code: str | None) -> bool:
    """True for well-known crypto tickers (case-insensitive)."""
    if not code:
        return False
    return code.strip().upper() in CRYPTO_CURRENCY_CODES


def money_quantum(currency: str | None = None) -> Decimal:
    """Return the quantization step for ``currency`` (8 dp crypto, else 2 dp)."""
    return _CRYPTO_MONEY_Q if is_crypto_currency(currency) else _MONEY_Q


def quantize_money(
    value: Decimal | int | float | str,
    *,
    currency: str | None = None,
) -> Decimal:
    """Quantize a monetary amount (2 dp fiat / 8 dp known crypto)."""
    q = money_quantum(currency)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal | int | float | str, *, crypto: bool = False) -> Decimal:
    """Quantize an exchange rate to high precision.

    Fiat and crypto both use 8 decimal places so weak currencies (UZS, etc.)
    are not rounded to 0.00.
    """
    q = _CRYPTO_Q if crypto else _FIAT_RATE_Q
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)
