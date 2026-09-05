"""Currency and exchange-rate use cases."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Protocol, Sequence

from lib.domain.entities.currency import Currency, ExchangeRate
from lib.domain.entities.money import quantize_money, quantize_rate
from lib.domain.repositories.currency_repository import CurrencyRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeRateProvider(Protocol):
    """Port for an external FX / crypto rate source."""

    async def fetch_rates(
        self,
        base: str,
        quotes: Sequence[str],
    ) -> Sequence[ExchangeRate]:
        """Fetch rates for ``base`` against each quote code."""


class UpdateExchangeRatesUseCase:
    """Refresh stored exchange rates from an external provider."""

    def __init__(
        self,
        currencies: CurrencyRepository,
        provider: Optional[ExchangeRateProvider] = None,
    ) -> None:
        self._currencies = currencies
        self._provider = provider

    async def execute(
        self,
        *,
        base: str = "RUB",
        quotes: Optional[Sequence[str]] = None,
        rates: Optional[Sequence[ExchangeRate]] = None,
    ) -> list[ExchangeRate]:
        """Update rates either from ``rates`` payload or via ``provider``.

        Args:
            base: Base currency code.
            quotes: Quote codes to request when using the provider.
            rates: Precomputed rates to upsert (skips provider).

        Returns:
            Persisted exchange rates.
        """
        base = base.upper()
        if rates is not None:
            normalized = [
                r.model_copy(
                    update={
                        "base": r.base.upper(),
                        "quote": r.quote.upper(),
                        "rate": quantize_rate(r.rate, crypto=True),
                        "updated_at": r.updated_at or _utc_now(),
                    }
                )
                for r in rates
            ]
            saved = await self._currencies.upsert_rates(normalized)
            from lib.domain.services.rate_cache import invalidate_rate_book_cache

            invalidate_rate_book_cache()
            return saved

        if self._provider is None:
            raise RuntimeError(
                "No exchange-rate provider configured and no rates supplied"
            )

        if not quotes:
            known = await self._currencies.list_currencies(include_crypto=True)
            quotes = [c.code for c in known if c.code != base]

        fetched = await self._provider.fetch_rates(base, quotes)
        normalized = [
            r.model_copy(
                update={
                    "rate": quantize_rate(r.rate, crypto=True),
                    "updated_at": _utc_now(),
                }
            )
            for r in fetched
        ]
        saved = await self._currencies.upsert_rates(normalized)
        from lib.domain.services.rate_cache import invalidate_rate_book_cache

        invalidate_rate_book_cache()
        return saved





class ConvertCurrencyUseCase:
    """Convert an amount between currencies using stored rates."""

    def __init__(self, currencies: CurrencyRepository) -> None:
        self._currencies = currencies

    async def execute(
        self,
        amount: Decimal,
        *,
        from_currency: str,
        to_currency: str,
        quantize: bool = True,
    ) -> Decimal:
        """Convert ``amount`` from ``from_currency`` to ``to_currency``.

        Uses the process-wide RateBook cache (one SQLite rates load per TTL)
        so N UI conversions do not issue N rate lookups.
        """
        from lib.domain.services.rate_cache import get_cached_rate_book

        raw_amount = Decimal(str(amount))
        amount = quantize_money(raw_amount) if quantize else raw_amount
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return amount

        book = await get_cached_rate_book(self._currencies)
        converted = book.convert(amount, src, dst, quantize=quantize)
        if converted is None:
            raise ValueError(f"No exchange rate found for {src}/{dst}")
        return converted

    async def execute_many(
        self,
        items: Sequence[tuple[Decimal, str, str]],
        *,
        quantize: bool = True,
    ) -> list[Decimal]:
        """Batch-convert ``(amount, from, to)`` rows with one RateBook load.

        Raises ``ValueError`` on the first missing rate (fail-closed).
        """
        from lib.domain.services.rate_cache import get_cached_rate_book

        if not items:
            return []
        book = await get_cached_rate_book(self._currencies)
        out: list[Decimal] = []
        for amount, from_currency, to_currency in items:
            raw = Decimal(str(amount))
            value = quantize_money(raw) if quantize else raw
            src = from_currency.upper()
            dst = to_currency.upper()
            if src == dst:
                out.append(value)
                continue
            converted = book.convert(value, src, dst, quantize=quantize)
            if converted is None:
                raise ValueError(f"No exchange rate found for {src}/{dst}")
            out.append(converted)
        return out


class ListCurrenciesUseCase:
    """List known currencies."""

    def __init__(self, currencies: CurrencyRepository) -> None:
        self._currencies = currencies

    async def execute(self, *, include_crypto: bool = True) -> list[Currency]:
        """Return currency definitions."""
        return await self._currencies.list_currencies(include_crypto=include_crypto)


class SeedCurrenciesUseCase:
    """Seed currency catalog from a JSON asset after wipe / first run."""

    def __init__(self, currencies: CurrencyRepository) -> None:
        self._currencies = currencies

    async def execute(self, path: object) -> int:
        """Return number of upserted currency rows."""
        return await self._currencies.seed_from_json(path)
