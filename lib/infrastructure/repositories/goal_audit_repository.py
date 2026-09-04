"""SQLAlchemy goal audit log repository."""

from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import select

from lib.domain.entities.goal_audit import GoalAuditEntry
from lib.infrastructure.db_models import GoalAuditLogModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)


class SqlAlchemyGoalAuditRepository:
    """Append-only goal audit persistence."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def append(self, entry: GoalAuditEntry) -> GoalAuditEntry:
        if in_unit_of_work():
            return self._append_sync(entry)
        return await asyncio.to_thread(self._append_sync, entry)

    async def list_for_goal(
        self, goal_id: str, *, limit: int = 50
    ) -> list[GoalAuditEntry]:
        if in_unit_of_work():
            return self._list_sync(goal_id, limit)
        return await asyncio.to_thread(self._list_sync, goal_id, limit)

    def _append_sync(self, entry: GoalAuditEntry) -> GoalAuditEntry:
        with session_scope(self._session_factory) as session:
            model = GoalAuditLogModel(
                id=entry.id,
                goal_id=entry.goal_id,
                action=entry.action,
                details=entry.details,
                created_at=ensure_utc(entry.created_at),
            )
            session.add(model)
            session.flush()
            return entry

    def _list_sync(self, goal_id: str, limit: int) -> list[GoalAuditEntry]:
        with session_scope(self._session_factory) as session:
            stmt = (
                select(GoalAuditLogModel)
                .where(GoalAuditLogModel.goal_id == goal_id)
                .order_by(GoalAuditLogModel.created_at.desc())
                .limit(max(1, int(limit)))
            )
            rows = session.scalars(stmt).all()
            return [
                GoalAuditEntry(
                    id=r.id,
                    goal_id=r.goal_id,
                    action=r.action,
                    details=dict(r.details) if isinstance(r.details, dict) else r.details,
                    created_at=ensure_utc(r.created_at),
                )
                for r in rows
            ]
