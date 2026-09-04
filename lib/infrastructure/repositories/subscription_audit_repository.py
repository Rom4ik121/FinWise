"""SQLAlchemy subscription audit log repository."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from lib.domain.entities.subscription_audit import SubscriptionAuditEntry
from lib.infrastructure.db_models import SubscriptionAuditLogModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)


class SqlAlchemySubscriptionAuditRepository:
    """Append-only subscription audit persistence."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def append(self, entry: SubscriptionAuditEntry) -> SubscriptionAuditEntry:
        if in_unit_of_work():
            return self._append_sync(entry)
        return await asyncio.to_thread(self._append_sync, entry)

    async def list_for_subscription(
        self, subscription_id: str, *, limit: int = 50
    ) -> list[SubscriptionAuditEntry]:
        if in_unit_of_work():
            return self._list_sync(subscription_id, limit)
        return await asyncio.to_thread(self._list_sync, subscription_id, limit)

    def _append_sync(self, entry: SubscriptionAuditEntry) -> SubscriptionAuditEntry:
        with session_scope(self._session_factory) as session:
            model = SubscriptionAuditLogModel(
                id=entry.id,
                subscription_id=entry.subscription_id,
                action=entry.action,
                details=entry.details,
                created_at=ensure_utc(entry.created_at),
            )
            session.add(model)
            session.flush()
            return entry

    def _list_sync(
        self, subscription_id: str, limit: int
    ) -> list[SubscriptionAuditEntry]:
        with session_scope(self._session_factory) as session:
            stmt = (
                select(SubscriptionAuditLogModel)
                .where(SubscriptionAuditLogModel.subscription_id == subscription_id)
                .order_by(SubscriptionAuditLogModel.created_at.desc())
                .limit(max(1, int(limit)))
            )
            rows = session.scalars(stmt).all()
            return [
                SubscriptionAuditEntry(
                    id=r.id,
                    subscription_id=r.subscription_id,
                    action=r.action,
                    details=dict(r.details) if isinstance(r.details, dict) else r.details,
                    created_at=ensure_utc(r.created_at),
                )
                for r in rows
            ]
