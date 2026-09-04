"""Paged transaction listing for large ledgers (domain-safe, no UI deps)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DEFAULT_PAGE_SIZE = 500
DEFAULT_MAX_ROWS = 25_000

ListFn = Callable[..., Awaitable[list]]


async def list_transactions_paged(
    list_fn: ListFn,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_rows: int = DEFAULT_MAX_ROWS,
    **filters: Any,
) -> list:
    """Load matching transactions in pages (never unbounded ``list()``)."""
    if list_fn is None:
        return []
    page_size = max(1, int(page_size))
    max_rows = max(page_size, int(max_rows))
    offset = 0
    out: list = []
    while offset < max_rows:
        batch = await list_fn(
            **filters,
            limit=min(page_size, max_rows - offset),
            offset=offset,
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return out


async def fold_transaction_pages(
    list_fn: ListFn,
    callback: Callable[[list], Any],
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_rows: int = DEFAULT_MAX_ROWS,
    **filters: Any,
) -> int:
    """Invoke ``callback(batch)`` per page; return total rows seen."""
    if list_fn is None:
        return 0
    page_size = max(1, int(page_size))
    max_rows = max(page_size, int(max_rows))
    offset = 0
    total = 0
    while offset < max_rows:
        batch = await list_fn(
            **filters,
            limit=min(page_size, max_rows - offset),
            offset=offset,
        )
        if not batch:
            break
        result = callback(batch)
        if hasattr(result, "__await__"):
            await result
        total += len(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return total
