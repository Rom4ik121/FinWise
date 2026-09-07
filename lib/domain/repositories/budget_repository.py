"""Abstract budget repository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Sequence

from lib.domain.entities.budget import Budget


class BudgetRepository(ABC):
    """Persistence port for :class:`~lib.domain.entities.budget.Budget`."""

    @abstractmethod
    async def get_by_id(self, budget_id: str) -> Optional[Budget]:
        """Fetch a budget by id."""

    @abstractmethod
    async def get_by_category_and_month(
        self,
        category_id: str,
        month: int,
        year: int,
        *,
        account_id: Optional[str] = None,
    ) -> Optional[Budget]:
        """Fetch the unique budget for a category in a calendar month.

        ``account_id=None`` selects the personal (non-corporate) budget.
        """

    @abstractmethod
    async def list_for_month(
        self,
        month: int,
        year: int,
        category_ids: Optional[Sequence[str]] = None,
        *,
        account_id: Optional[str] = None,
    ) -> list[Budget]:
        """List budgets for a month.

        ``account_id=None`` → personal budgets only.
        ``account_id=<id>`` → budgets for that corporate account.
        """

    @abstractmethod
    async def list_all(self) -> list[Budget]:
        """List every budget row (for export / admin)."""

    @abstractmethod
    async def save(self, budget: Budget) -> Budget:
        """Insert or update a budget."""

    @abstractmethod
    async def delete(self, budget_id: str) -> bool:
        """Delete a budget. Returns ``True`` if a row was removed."""

    @abstractmethod
    async def update_spent(self, budget_id: str, new_spent: Decimal) -> Optional[Budget]:
        """Set ``spent`` for a budget and return the updated entity."""

    @abstractmethod
    async def delete_for_category(
        self, category_id: str, *, account_id: str | None = None
    ) -> int:
        """Delete budgets for a category name within optional account scope."""

    @abstractmethod
    async def reassign_category(
        self,
        old_name: str,
        new_name: str,
        *,
        account_id: str | None = None,
    ) -> int:
        """Rename ``category_id`` on budgets within optional account scope."""
