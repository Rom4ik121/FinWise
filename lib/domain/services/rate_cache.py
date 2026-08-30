"""Process-wide RateBook cache shared by UI and domain.

Keeps FX conversion fast across screens without re-hitting SQLite on every
budget sync / dashboard paint. Invalidate after any rates write.
"""

from __future__ import annotations

import time
from typing import Any

from lib.domain.services.rate_book import RateBook

_RATE_BOOK_TTL_SECONDS = 90.0
_rate_book_cache: dict[int, tuple[float, RateBook]] = {}


def invalidate_rate_book_cache() -> None:
    """Drop cached FX books (call after rates upsert / wipe)."""
    _rate_book_cache.clear()


async def get_cached_rate_book(
    currencies: Any,
    *,
    force: bool = False,
) -> RateBook:
    """Return RateBook for ``currencies.list_rates()`` with a short TTL cache."""
    if currencies is None or not hasattr(currencies, "list_rates"):
        return RateBook(())
    cache_key = id(currencies)
    now = time.monotonic()
    if not force:
        cached = _rate_book_cache.get(cache_key)
        if cached is not None:
            stamp, book = cached
            if now - stamp < _RATE_BOOK_TTL_SECONDS:
                return book
    try:
        rates = await currencies.list_rates()
    except Exception:  # noqa: BLE001
        return RateBook(())
    book = RateBook(rates)
    _rate_book_cache[cache_key] = (now, book)
    return book
