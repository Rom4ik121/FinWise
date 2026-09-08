"""Category name matching (NFC + casefold) used by catalog lookup."""

from __future__ import annotations

from lib.domain.entities.category import (
    category_names_equal,
    normalize_category_name,
)
from lib.presentation.category_lookup import index_categories, lookup_category
from tests.factories import make_category


def test_nfc_and_casefold_match() -> None:
    composed = "Сигареты"
    padded = "  Сигареты "
    lower = "сигареты"
    assert normalize_category_name(padded) == composed
    assert category_names_equal(composed, lower)
    assert category_names_equal(composed, padded)
    assert not category_names_equal(composed, "Еда")


def test_lookup_uses_indexed_keys() -> None:
    cat = make_category(name="Сигареты")
    indexed = index_categories([cat])
    assert lookup_category(indexed, "сигареты") is cat
    assert lookup_category(indexed, "  Сигареты") is cat
    assert lookup_category(indexed, "") is None
