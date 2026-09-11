"""Abstract net-worth snapshot repository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from lib.domain.entities.net_worth import NetWorthSnapshot


class NetWorthRepository(ABC):
    """Persistence port for :class:`~lib.domain.entities.net_worth.NetWorthSnapshot`."""

    @abstractmethod
    async def upsert(self, snapshot: NetWorthSnapshot) -> NetWorthSnapshot:
        """Insert or replace the snapshot for ``captured_on``."""

    @abstractmethod
    async def get_for_date(self, captured_on: date) -> Optional[NetWorthSnapshot]:
        """Fetch the snapshot for a calendar day, if any."""

    @abstractmethod
    async def list(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[NetWorthSnapshot]:
        """List snapshots oldest-first within an optional date window."""
