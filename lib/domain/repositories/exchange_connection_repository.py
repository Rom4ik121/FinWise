"""Abstract persistence for exchange API connections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from lib.domain.entities.exchange_connection import ExchangeConnection


class ExchangeConnectionRepository(ABC):
    """CRUD for :class:`ExchangeConnection`."""

    @abstractmethod
    async def upsert(self, connection: ExchangeConnection) -> ExchangeConnection:
        """Insert or replace a connection."""

    @abstractmethod
    async def get_by_account_id(self, account_id: str) -> Optional[ExchangeConnection]:
        """Return the connection for an account, if any."""

    @abstractmethod
    async def list(self) -> list[ExchangeConnection]:
        """All connections."""

    @abstractmethod
    async def delete_by_account_id(self, account_id: str) -> bool:
        """Remove the connection for an account."""
