"""Transaction domain entity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lib.domain.entities.money import quantize_money


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TransactionType(str, Enum):
    """Direction of a cash-flow transaction."""

    INCOME = "income"
    EXPENSE = "expense"


class TransactionItem(BaseModel):
    """One line inside a multi-position income/expense (e.g. receipt row)."""

    model_config = ConfigDict(from_attributes=True)

    name: str = ""
    amount: Decimal
    category: str = ""

    @field_validator("amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value: object) -> object:
        return quantize_money(value)

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Line amount must be positive")
        return value

    @field_validator("name", "category", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if value is None:
            return ""
        return str(value).strip()


class Transaction(BaseModel):
    """A single income or expense entry linked to an account.

    Optional ``items`` hold receipt-style lines; ``amount`` is always the total
    (sum of lines when items are present). Budgets sync per line category.
    """

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    amount: Decimal
    category: str
    tags: list[str] = Field(default_factory=list)
    date: datetime
    comment: str = ""
    type: TransactionType
    currency: str = "RUB"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    goal_id: Optional[str] = None
    debt_id: Optional[str] = None
    subscription_id: Optional[str] = None
    # Amount credited to the linked goal in the goal's currency (FX-aware).
    goal_credit_amount: Optional[Decimal] = None
    # Amount applied to the linked debt remaining in the debt's currency (FX-aware).
    debt_credit_amount: Optional[Decimal] = None
    # Shared id for a pair of transfer legs (outgoing expense + incoming income).
    transfer_id: Optional[str] = None
    transfer_peer_account_id: Optional[str] = None
    items: list[TransactionItem] = Field(default_factory=list)

    @field_validator("amount", "goal_credit_amount", "debt_credit_amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value: object) -> object:
        if value is None:
            return None
        return quantize_money(value)

    @field_validator("date", "created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime")

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Transaction amount must be positive")
        return value

    @model_validator(mode="after")
    def _sync_items_total(self) -> Transaction:
        ccy = self.currency
        amount = quantize_money(self.amount, currency=ccy)
        if not self.items:
            if amount != self.amount:
                self.amount = amount
            return self
        total = quantize_money(
            sum((i.amount for i in self.items), Decimal("0")),
            currency=ccy,
        )
        if total <= 0:
            raise ValueError("Transaction items must sum to a positive amount")
        filled: list[TransactionItem] = []
        for item in self.items:
            cat = item.category or self.category
            filled.append(
                item.model_copy(
                    update={
                        "amount": quantize_money(item.amount, currency=ccy),
                        "category": cat,
                        "name": item.name or cat,
                    }
                )
            )
        primary = self.category or filled[0].category
        self.amount = total
        self.category = primary
        self.items = filled
        return self

    @property
    def is_transfer(self) -> bool:
        """True when this row is one leg of an account-to-account transfer."""
        return bool(self.transfer_id)

    @property
    def has_items(self) -> bool:
        """True when this transaction stores multiple line positions."""
        return len(self.items) > 0

    def items_summary(self, *, limit: int = 3) -> str:
        """Short label for lists (first N line names)."""
        if not self.items:
            return self.comment or self.category
        names = [i.name or i.category for i in self.items if (i.name or i.category)]
        if not names:
            return self.comment or self.category
        head = ", ".join(names[:limit])
        if len(names) > limit:
            head = f"{head}…"
        return head
