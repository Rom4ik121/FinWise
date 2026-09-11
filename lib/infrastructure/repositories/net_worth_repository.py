"""SQLAlchemy net-worth snapshot repository."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from lib.domain.entities.net_worth import NetWorthSnapshot
from lib.domain.repositories.net_worth_repository import NetWorthRepository
from lib.infrastructure.db_models import NetWorthSnapshotModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)


def _to_entity(model: NetWorthSnapshotModel) -> NetWorthSnapshot:
    return NetWorthSnapshot(
        id=model.id,
        captured_on=model.captured_on,
        amount=Decimal(str(model.amount)),
        currency=model.currency,
        captured_at=ensure_utc(model.captured_at),
    )


def _apply_entity(model: NetWorthSnapshotModel, entity: NetWorthSnapshot) -> None:
    model.id = entity.id
    model.captured_on = entity.captured_on
    model.amount = entity.amount
    model.currency = entity.currency
    model.captured_at = ensure_utc(entity.captured_at) or entity.captured_at


class SqlAlchemyNetWorthRepository(NetWorthRepository):
    """Net-worth snapshots via SQLAlchemy sync session + ``asyncio.to_thread``."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def upsert(self, snapshot: NetWorthSnapshot) -> NetWorthSnapshot:
        if in_unit_of_work():
            return self._upsert_sync(snapshot)
        return await asyncio.to_thread(self._upsert_sync, snapshot)

    async def get_for_date(self, captured_on: date) -> Optional[NetWorthSnapshot]:
        if in_unit_of_work():
            return self._get_for_date_sync(captured_on)
        return await asyncio.to_thread(self._get_for_date_sync, captured_on)

    async def list(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[NetWorthSnapshot]:
        args = (date_from, date_to, limit)
        if in_unit_of_work():
            return self._list_sync(*args)
        return await asyncio.to_thread(self._list_sync, *args)

    def _upsert_sync(self, entity: NetWorthSnapshot) -> NetWorthSnapshot:
        with session_scope(self._session_factory) as session:
            existing = session.scalar(
                select(NetWorthSnapshotModel).where(
                    NetWorthSnapshotModel.captured_on == entity.captured_on
                )
            )
            if existing is None:
                model = NetWorthSnapshotModel()
                _apply_entity(model, entity)
                session.add(model)
            else:
                keep_id = existing.id
                _apply_entity(existing, entity)
                existing.id = keep_id
                model = existing
            session.flush()
            return _to_entity(model)

    def _get_for_date_sync(self, captured_on: date) -> Optional[NetWorthSnapshot]:
        with session_scope(self._session_factory) as session:
            model = session.scalar(
                select(NetWorthSnapshotModel).where(
                    NetWorthSnapshotModel.captured_on == captured_on
                )
            )
            return _to_entity(model) if model else None

    def _list_sync(
        self,
        date_from: Optional[date],
        date_to: Optional[date],
        limit: Optional[int],
    ) -> list[NetWorthSnapshot]:
        with session_scope(self._session_factory) as session:
            stmt = select(NetWorthSnapshotModel).order_by(
                NetWorthSnapshotModel.captured_on.asc()
            )
            if date_from is not None:
                stmt = stmt.where(NetWorthSnapshotModel.captured_on >= date_from)
            if date_to is not None:
                stmt = stmt.where(NetWorthSnapshotModel.captured_on <= date_to)
            if limit is not None:
                stmt = stmt.limit(limit)
            return [_to_entity(row) for row in session.scalars(stmt).all()]
