"""User-defined transaction category."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_category_name(name: str | None) -> str:
    """Strip and NFC-normalize a stored category label (Cyrillic-safe)."""
    return unicodedata.normalize("NFC", (name or "").strip())


def category_names_equal(left: str | None, right: str | None) -> bool:
    """True when labels match after NFC + casefold (SQLite LOWER is ASCII-only)."""
    a = normalize_category_name(left)
    b = normalize_category_name(right)
    if not a or not b:
        return False
    return a == b or a.casefold() == b.casefold()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CategoryKind(str, Enum):
    """Which transaction types a category applies to."""

    EXPENSE = "expense"
    INCOME = "income"
    BOTH = "both"


class Category(BaseModel):
    """Named category with icon and color for income / expense."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    icon: str = "category"
    color: str = "#00897B"
    kind: CategoryKind = CategoryKind.BOTH
    # Empty string = personal (shared) ledger; set for corporate account scopes.
    account_id: str = ""
    is_system: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("account_id", mode="before")
    @classmethod
    def _normalize_account_id(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        text = normalize_category_name(value)
        if not text:
            raise ValueError("Category name is required")
        return text

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime")

    def matches_type(self, tx_type: str) -> bool:
        """Return True if this category can be used for ``tx_type``."""
        if self.kind == CategoryKind.BOTH:
            return True
        return self.kind.value == tx_type
