"""Abstract recurring-rule repository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from lib.domain.entities.recurring_rule import RecurringRule


class RecurringRuleRepository(ABC):
    """Persistence port for :class:`~lib.domain.entities.recurring_rule.RecurringRule`."""

    @abstractmethod
    async def create(self, rule: RecurringRule) -> RecurringRule:
        """Persist a new rule."""

    @abstractmethod
    async def update(self, rule: RecurringRule) -> RecurringRule:
        """Update an existing rule."""

    @abstractmethod
    async def delete(self, rule_id: str) -> bool:
        """Delete a rule. Returns ``True`` if a row was removed."""

    @abstractmethod
    async def get_by_id(self, rule_id: str) -> Optional[RecurringRule]:
        """Fetch a rule by id."""

    @abstractmethod
    async def list(self, *, include_paused: bool = True) -> list[RecurringRule]:
        """List templates, newest first."""

    @abstractmethod
    async def list_due(self, as_of: date) -> list[RecurringRule]:
        """Active auto-create rules whose ``next_run`` is on or before ``as_of``."""
