"""SQLAlchemy exchange connection repository."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from lib.domain.entities.exchange_connection import ExchangeConnection
from lib.domain.repositories.exchange_connection_repository import (
    ExchangeConnectionRepository,
)
from lib.infrastructure.db_models import ExchangeConnectionModel
from lib.infrastructure.repositories._base import SessionFactory, ensure_utc, session_scope

logger = logging.getLogger("finanse.infrastructure.repositories.exchange_connection")


def _to_entity(model: ExchangeConnectionModel) -> ExchangeConnection:
    holdings = model.holdings_json if isinstance(model.holdings_json, list) else []
    return ExchangeConnection(
        id=model.id,
        account_id=model.account_id,
        provider=model.provider,
        credentials_encrypted=model.credentials_encrypted or "",
        last_sync_at=ensure_utc(model.last_sync_at),
        last_error=model.last_error or "",
        holdings_json=list(holdings),
        created_at=ensure_utc(model.created_at) or datetime.now(timezone.utc),
    )


def _apply(model: ExchangeConnectionModel, entity: ExchangeConnection) -> None:
    model.id = entity.id
    model.account_id = entity.account_id
    model.provider = entity.provider
    model.credentials_encrypted = entity.credentials_encrypted
    model.last_sync_at = ensure_utc(entity.last_sync_at)
    model.last_error = entity.last_error or ""
    model.holdings_json = list(entity.holdings_json or [])
    model.created_at = ensure_utc(entity.created_at) or datetime.now(timezone.utc)


class SqlAlchemyExchangeConnectionRepository(ExchangeConnectionRepository):
    """Persist exchange API links."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def upsert(self, connection: ExchangeConnection) -> ExchangeConnection:
        return await asyncio.to_thread(self._upsert_sync, connection)

    async def get_by_account_id(self, account_id: str) -> Optional[ExchangeConnection]:
        return await asyncio.to_thread(self._get_by_account_sync, account_id)

    async def list(self) -> list[ExchangeConnection]:
        return await asyncio.to_thread(self._list_sync)

    async def delete_by_account_id(self, account_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, account_id)

    def _upsert_sync(self, entity: ExchangeConnection) -> ExchangeConnection:
        with session_scope(self._session_factory) as session:
            model = session.scalar(
                select(ExchangeConnectionModel).where(
                    ExchangeConnectionModel.account_id == entity.account_id
                )
            )
            if model is None:
                model = session.get(ExchangeConnectionModel, entity.id)
            if model is None:
                model = ExchangeConnectionModel()
                session.add(model)
            _apply(model, entity)
            session.flush()
            return _to_entity(model)

    def _get_by_account_sync(self, account_id: str) -> Optional[ExchangeConnection]:
        with session_scope(self._session_factory) as session:
            model = session.scalar(
                select(ExchangeConnectionModel).where(
                    ExchangeConnectionModel.account_id == account_id
                )
            )
            return _to_entity(model) if model else None

    def _list_sync(self) -> list[ExchangeConnection]:
        with session_scope(self._session_factory) as session:
            rows = session.scalars(select(ExchangeConnectionModel)).all()
            return [_to_entity(row) for row in rows]

    def _delete_sync(self, account_id: str) -> bool:
        with session_scope(self._session_factory) as session:
            model = session.scalar(
                select(ExchangeConnectionModel).where(
                    ExchangeConnectionModel.account_id == account_id
                )
            )
            if model is None:
                return False
            session.delete(model)
            return True
