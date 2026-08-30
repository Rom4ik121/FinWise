"""Compatibility re-export — prefer ``lib.domain.services.rate_cache``."""

from __future__ import annotations

from lib.domain.services.rate_cache import (
    get_cached_rate_book,
    invalidate_rate_book_cache,
)

__all__ = ["get_cached_rate_book", "invalidate_rate_book_cache"]
