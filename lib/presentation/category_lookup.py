"""Resolve stored transaction category names against the catalog."""

from __future__ import annotations

from typing import Iterable

from lib.domain.entities.category import (
    Category,
    category_names_equal,
    normalize_category_name,
)


def index_categories(categories: Iterable[Category]) -> dict[str, Category]:
    """Map exact, casefold, and NFC keys onto catalog rows."""
    out: dict[str, Category] = {}
    for cat in categories:
        out[cat.name] = cat
        nfc = normalize_category_name(cat.name)
        out[nfc] = cat
        out[nfc.casefold()] = cat
        out[cat.name.casefold()] = cat
    return out


def lookup_category(
    cat_map: dict[str, object], name: str | None
) -> object | None:
    """Find a catalog row for a ledger category string (NFC + casefold)."""
    key = normalize_category_name(name)
    if not key:
        return None
    found = cat_map.get(key) or cat_map.get(key.casefold())
    if found is not None:
        return found
    for stored, cat in cat_map.items():
        if category_names_equal(str(stored), key):
            return cat
    return None
