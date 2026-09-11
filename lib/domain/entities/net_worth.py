"""Daily net-worth snapshot for the analytics chart."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lib.domain.entities.money import quantize_money


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _utc_now().date()


class NetWorthSnapshot(BaseModel):
    """One captured total of accounts included in the home balance."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    captured_on: date = Field(default_factory=_utc_today)
    amount: Decimal
    currency: str = "RUB"
    captured_at: datetime = Field(default_factory=_utc_now)

    @field_validator("amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value: object) -> Decimal:
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return (value or "RUB").strip().upper() or "RUB"

    @field_validator("captured_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime")
