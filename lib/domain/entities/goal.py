"""Savings goal domain entity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import quantize_money


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoalStatus(str, Enum):
    """Lifecycle of a savings goal."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class GoalItemStatus(str, Enum):
    """Lifecycle of a sub-position inside a goal."""

    OPEN = "open"
    CLOSED = "closed"


class GoalItem(BaseModel):
    """One savings line inside a goal (e.g. laptop + case + warranty)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0.00")
    status: GoalItemStatus = GoalItemStatus.OPEN
    closed_at: Optional[datetime] = None
    sort_order: int = 0

    @field_validator("target_amount", "current_amount", mode="before")
    @classmethod
    def _quantize_money_fields(cls, value: object) -> Decimal:
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("target_amount")
    @classmethod
    def _positive_target(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Goal item target_amount must be positive")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _parse_item_status(cls, value: object) -> object:
        if isinstance(value, GoalItemStatus):
            return value
        if value is None:
            return GoalItemStatus.OPEN
        return GoalItemStatus(str(value).lower())

    @field_validator("closed_at", mode="before")
    @classmethod
    def _ensure_item_utc(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime or None")

    @property
    def remaining_amount(self) -> Decimal:
        left = self.target_amount - self.current_amount
        return quantize_money(left if left > 0 else Decimal("0"))

    @property
    def is_closed(self) -> bool:
        status = self.status
        if isinstance(status, GoalItemStatus):
            return status == GoalItemStatus.CLOSED
        return str(status).lower() == GoalItemStatus.CLOSED.value

    @property
    def progress_ratio(self) -> Decimal:
        """Fraction of the item target saved (0–1+)."""
        if self.target_amount == 0:
            return Decimal("0")
        return self.current_amount / self.target_amount


class Goal(BaseModel):
    """A savings target with optional deadline, currency, and status."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0.00")
    currency: str = "RUB"
    deadline: Optional[datetime] = None
    priority: int = Field(default=3, ge=1, le=5)
    category_link: str = "Накопление"
    status: GoalStatus = GoalStatus.ACTIVE
    is_completed: bool = False
    cached_projection: Optional[dict[str, Any]] = None
    items: list[GoalItem] = Field(default_factory=list)
    closed_early: bool = False
    icon: str = "flag"
    color: str = "#2DD4BF"
    planned_monthly_contribution: Optional[Decimal] = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("planned_monthly_contribution", mode="before")
    @classmethod
    def _quantize_planned_monthly(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("target_amount", "current_amount", mode="before")
    @classmethod
    def _quantize_money_fields(cls, value: object) -> Decimal:
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(str(value) if value is not None else "RUB")

    @field_validator("status", mode="before")
    @classmethod
    def _parse_status(cls, value: object) -> object:
        if isinstance(value, GoalStatus):
            return value
        if value is None:
            return GoalStatus.ACTIVE
        return GoalStatus(str(value).lower())

    @field_validator("deadline", "created_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime or None")

    @field_validator("target_amount")
    @classmethod
    def _positive_target(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Goal target_amount must be positive")
        return value

    @model_validator(mode="after")
    def _sync_completed_flag(self) -> "Goal":
        if self.items:
            target = sum(i.target_amount for i in self.items)
            current = sum(i.current_amount for i in self.items)
            object.__setattr__(self, "target_amount", quantize_money(target))
            object.__setattr__(self, "current_amount", quantize_money(current))
            all_closed = all(i.is_closed for i in self.items)
            if self.closed_early and self.status == GoalStatus.ARCHIVED:
                object.__setattr__(self, "is_completed", False)
                return self
            if all_closed and self.status != GoalStatus.ARCHIVED:
                object.__setattr__(self, "status", GoalStatus.COMPLETED)
                object.__setattr__(self, "is_completed", True)
            elif self.status not in (GoalStatus.ARCHIVED, GoalStatus.COMPLETED):
                object.__setattr__(self, "is_completed", False)
            return self

        if self.closed_early and self.status == GoalStatus.ARCHIVED:
            object.__setattr__(self, "is_completed", False)
            return self
        if self.status == GoalStatus.COMPLETED:
            object.__setattr__(self, "is_completed", True)
        elif self.status == GoalStatus.ARCHIVED:
            object.__setattr__(
                self,
                "is_completed",
                self.current_amount >= self.target_amount,
            )
        else:
            object.__setattr__(
                self,
                "is_completed",
                self.current_amount >= self.target_amount,
            )
            if self.is_completed:
                object.__setattr__(self, "status", GoalStatus.COMPLETED)
        return self

    @property
    def progress_ratio(self) -> Decimal:
        """Fraction of the target already saved (0–1+)."""
        if self.target_amount == 0:
            return Decimal("0")
        return self.current_amount / self.target_amount

    @property
    def remaining_amount(self) -> Decimal:
        """How much is left to reach the target (never negative)."""
        left = self.target_amount - self.current_amount
        return quantize_money(left if left > 0 else Decimal("0"))
