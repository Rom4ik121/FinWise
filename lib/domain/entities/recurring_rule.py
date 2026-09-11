"""Recurring income/expense templates that auto-create ledger rows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import TransactionType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _utc_now().date()


class RecurringInterval(str, Enum):
    """Cadence for a recurring template."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class RecurringRule(BaseModel):
    """Template that creates income or expense transactions when due."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    amount: Decimal
    currency: str = "RUB"
    account_id: str
    category: str = "Прочее"
    comment: str = ""
    type: TransactionType = TransactionType.EXPENSE
    interval: RecurringInterval = RecurringInterval.MONTHLY
    interval_count: int = 1
    next_run: date = Field(default_factory=_utc_today)
    paused: bool = False
    skip_next: bool = False
    auto_create: bool = True
    last_created_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("Name is required")
        return text

    @field_validator("amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value: object) -> Decimal:
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Amount must be positive")
        return value

    @field_validator("interval_count", mode="before")
    @classmethod
    def _positive_count(cls, value: object) -> int:
        number = int(value or 1)
        if number < 1 or number > 365:
            raise ValueError("Interval count must be between 1 and 365")
        return number

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return (value or "RUB").strip().upper() or "RUB"

    @field_validator("last_created_at", "created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime or None")
