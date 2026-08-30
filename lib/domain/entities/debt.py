"""Debt domain entity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import quantize_money


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DebtDirection(str, Enum):
    """Who owes whom."""

    I_OWE = "i_owe"
    OWED_TO_ME = "owed_to_me"


class DebtStatus(str, Enum):
    """Lifecycle status of a debt."""

    ACTIVE = "active"
    OVERDUE = "overdue"
    PAID = "paid"
    ARCHIVED = "archived"


def effective_debt_due(
    *,
    due_date: Optional[datetime],
    next_payment_date: Optional[datetime],
) -> Optional[datetime]:
    """Earliest of installment date and final due (for overdue / reminders)."""
    candidates: list[datetime] = []
    for value in (next_payment_date, due_date):
        if value is None:
            continue
        due = value
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        else:
            due = due.astimezone(timezone.utc)
        candidates.append(due)
    if not candidates:
        return None
    return min(candidates)


def resolve_debt_status(
    *,
    remaining_amount: Decimal,
    due_date: Optional[datetime],
    current: DebtStatus | str | None = None,
    now: Optional[datetime] = None,
    next_payment_date: Optional[datetime] = None,
) -> DebtStatus:
    """Derive status from remaining balance and due / next payment dates.

    ``ARCHIVED`` is sticky until the caller changes it explicitly.
    """
    if isinstance(current, str):
        current = DebtStatus(current)
    if current == DebtStatus.ARCHIVED:
        return DebtStatus.ARCHIVED
    remaining = quantize_money(remaining_amount)
    if remaining <= 0:
        return DebtStatus.PAID
    moment = now or _utc_now()
    effective = effective_debt_due(
        due_date=due_date, next_payment_date=next_payment_date
    )
    if effective is not None and effective < moment:
        return DebtStatus.OVERDUE
    return DebtStatus.ACTIVE


class Debt(BaseModel):
    """A personal debt (owed by or to the user)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    counterparty: str
    amount: Decimal
    remaining_amount: Decimal
    currency: str = "RUB"
    direction: DebtDirection
    status: DebtStatus = DebtStatus.ACTIVE
    interest_rate: Optional[Decimal] = None  # annual percent, e.g. 12.5
    due_date: Optional[datetime] = None
    started_at: datetime = Field(default_factory=_utc_now)
    comment: str = ""
    account_id: Optional[str] = None  # default account for repay / cash
    next_payment_date: Optional[datetime] = None
    next_payment_amount: Optional[Decimal] = None
    accrue_interest: bool = False
    accrued_interest: Decimal = Decimal("0.00")
    last_interest_accrued_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @property
    def progress_ratio(self) -> float:
        """Share of original principal already paid (0..1)."""
        principal = quantize_money(self.amount)
        if principal <= 0:
            return 1.0 if self.remaining_amount <= 0 else 0.0
        paid = principal - min(quantize_money(self.remaining_amount), principal)
        ratio = float(paid / principal)
        return max(0.0, min(1.0, ratio))

    @field_validator("amount", "remaining_amount", "accrued_interest", mode="before")
    @classmethod
    def _quantize_money_fields(cls, value: object) -> Decimal:
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("next_payment_amount", mode="before")
    @classmethod
    def _quantize_optional_amount(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return quantize_money(value)  # type: ignore[arg-type]

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(str(value) if value is not None else "RUB")

    @field_validator("status", mode="before")
    @classmethod
    def _parse_status(cls, value: object) -> object:
        if isinstance(value, DebtStatus):
            return value
        if value is None:
            return DebtStatus.ACTIVE
        return DebtStatus(str(value).lower())

    @field_validator("interest_rate", mode="before")
    @classmethod
    def _coerce_rate(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @field_validator(
        "due_date",
        "next_payment_date",
        "last_interest_accrued_at",
        "started_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def _ensure_utc(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime or None")
