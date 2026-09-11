"""Net-worth snapshot use cases."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.net_worth import NetWorthSnapshot
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.net_worth_repository import NetWorthRepository
from lib.domain.repositories.settings_repository import SettingsRepository
from lib.domain.services.ledger_fx import sum_balances_in_base
from lib.domain.services.rate_cache import get_cached_rate_book

logger = logging.getLogger("finanse.domain.net_worth")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecordNetWorthSnapshotUseCase:
    """Capture today's include-in-total balance (FX-normalized)."""

    def __init__(
        self,
        snapshots: NetWorthRepository,
        accounts: AccountRepository,
        currencies: CurrencyRepository,
        settings: SettingsRepository,
    ) -> None:
        self._snapshots = snapshots
        self._accounts = accounts
        self._currencies = currencies
        self._settings = settings

    async def execute(self, *, as_of: Optional[datetime] = None) -> NetWorthSnapshot:
        moment = as_of or _utc_now()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        day = moment.date()
        cfg = await self._settings.get()
        base = normalize_currency_code(cfg.default_currency)
        accounts = await self._accounts.list(active_only=False)
        book = await get_cached_rate_book(self._currencies)
        total, fx_ok = sum_balances_in_base(accounts, base=base, book=book)
        existing = await self._snapshots.get_for_date(day)
        if not fx_ok:
            logger.warning(
                "Skipping net-worth snapshot for %s: missing FX (partial total would be %s %s)",
                day,
                total,
                base,
            )
            if existing is not None:
                return existing
            return NetWorthSnapshot(
                captured_on=day,
                amount=total,
                currency=base,
                captured_at=moment,
            )
        if existing is not None:
            if existing.amount == total and existing.currency == base:
                return existing
            updated = existing.model_copy(
                update={
                    "amount": total,
                    "currency": base,
                    "captured_at": moment,
                }
            )
            return await self._snapshots.upsert(updated)
        snap = NetWorthSnapshot(
            captured_on=day,
            amount=total,
            currency=base,
            captured_at=moment,
        )
        return await self._snapshots.upsert(snap)


class ListNetWorthSnapshotsUseCase:
    """List snapshots for a chart window."""

    def __init__(self, snapshots: NetWorthRepository) -> None:
        self._snapshots = snapshots

    async def execute(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[NetWorthSnapshot]:
        return await self._snapshots.list(
            date_from=date_from, date_to=date_to, limit=limit
        )
