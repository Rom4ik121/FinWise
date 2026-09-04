"""Paged transaction loading for large ledgers (thousands of rows)."""

from __future__ import annotations

from typing import Any

from lib.domain.transaction_paging import (
    DEFAULT_MAX_ROWS,
    DEFAULT_PAGE_SIZE,
    fold_transaction_pages,
    list_transactions_paged,
)

__all__ = [
    "DEFAULT_MAX_ROWS",
    "DEFAULT_PAGE_SIZE",
    "fetch_transactions_paged",
    "for_each_transaction_page",
]


async def fetch_transactions_paged(
    list_uc: Any,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_rows: int = DEFAULT_MAX_ROWS,
    **filters: Any,
) -> list:
    """Load matching transactions via use-case ``execute`` in pages."""
    if list_uc is None:
        return []
    return await list_transactions_paged(
        list_uc.execute,
        page_size=page_size,
        max_rows=max_rows,
        **filters,
    )


async def for_each_transaction_page(
    list_uc: Any,
    callback,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_rows: int = DEFAULT_MAX_ROWS,
    **filters: Any,
) -> int:
    """Invoke ``callback(batch)`` for each page; return total rows seen."""
    if list_uc is None:
        return 0
    return await fold_transaction_pages(
        list_uc.execute,
        callback,
        page_size=page_size,
        max_rows=max_rows,
        **filters,
    )
