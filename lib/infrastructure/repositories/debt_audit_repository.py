"""SQLAlchemy debt audit log repository."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from lib.domain.entities.debt_audit import DebtAuditEntry
from lib.infrastructure.db_models import DebtAuditLogModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)


class SqlAlchemyDebtAuditRepository:
    """Append-only debt audit persistence."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def append(self, entry: DebtAuditEntry) -> DebtAuditEntry:
        if in_unit_of_work():
            return self._append_sync(entry)
        return await asyncio.to_thread(self._append_sync, entry)

    async def list_for_debt(
        self, debt_id: str, *, limit: int = 50
    ) -> list[DebtAuditEntry]:
        if in_unit_of_work():
            return self._list_sync(debt_id, limit)
        return await asyncio.to_thread(self._list_sync, debt_id, limit)

    def _append_sync(self, entry: DebtAuditEntry) -> DebtAuditEntry:
        with session_scope(self._session_factory) as session:
            model = DebtAuditLogModel(
                id=entry.id,
                debt_id=entry.debt_id,
                action=entry.action,
                details=entry.details,
                created_at=ensure_utc(entry.created_at),
            )
            session.add(model)
            session.flush()
            return entry

    def _list_sync(self, debt_id: str, limit: int) -> list[DebtAuditEntry]:
        with session_scope(self._session_factory) as session:
            stmt = (
                select(DebtAuditLogModel)
                .where(DebtAuditLogModel.debt_id == debt_id)
                .order_by(DebtAuditLogModel.created_at.desc())
                .limit(max(1, int(limit)))
            )
            rows = session.scalars(stmt).all()
            return [
                DebtAuditEntry(
                    id=r.id,
                    debt_id=r.debt_id,
                    action=r.action,
                    details=dict(r.details) if isinstance(r.details, dict) else r.details,
                    created_at=ensure_utc(r.created_at),
                )
                for r in rows
            ]
