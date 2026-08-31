"""Savings category is one canonical ledger name; UI localizes it."""

from __future__ import annotations

from lib.core.config import (
    DEFAULT_SAVINGS_CATEGORY,
    normalize_savings_category,
)
from lib.infrastructure.services.localization import localize_category_name


def test_normalize_savings_category_collapses_language_aliases() -> None:
    assert normalize_savings_category(None) == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("") == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("Накопление") == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("Savings") == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("Jamg'arma") == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("Jamg‘arma") == DEFAULT_SAVINGS_CATEGORY
    assert normalize_savings_category("Инвестиции") == "Инвестиции"


def test_savings_category_display_follows_language() -> None:
    assert localize_category_name(DEFAULT_SAVINGS_CATEGORY, "ru") == "Накопление"
    assert localize_category_name(DEFAULT_SAVINGS_CATEGORY, "en") == "Savings"
    assert "Jamg" in localize_category_name(DEFAULT_SAVINGS_CATEGORY, "uz")
