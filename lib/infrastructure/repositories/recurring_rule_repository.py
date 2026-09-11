"""SQLAlchemy recurring-rule repository."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from lib.domain.entities.recurring_rule import RecurringInterval, RecurringRule
from lib.domain.entities.transaction import TransactionType
from lib.domain.repositories.recurring_rule_repository import RecurringRuleRepository
from lib.infrastructure.db_models import RecurringRuleModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)


def _to_entity(model: RecurringRuleModel) -> RecurringRule:
    try:
        tx_type = TransactionType(model.type)
    except ValueError:
        tx_type = TransactionType.EXPENSE
    try:
        interval = RecurringInterval(model.interval)
    except ValueError:
        interval = RecurringInterval.MONTHLY
    return RecurringRule(
        id=model.id,
        name=model.name,
        amount=Decimal(str(model.amount)),
        currency=model.currency,
        account_id=model.account_id,
        category=model.category or "",
        comment=model.comment or "",
        type=tx_type,
        interval=interval,
        interval_count=int(model.interval_count or 1),
        next_run=model.next_run,
        paused=bool(model.paused),
        skip_next=bool(model.skip_next),
        auto_create=bool(model.auto_create),
        last_created_at=ensure_utc(model.last_created_at),
        created_at=ensure_utc(model.created_at) or datetime.now(timezone.utc),
        updated_at=ensure_utc(model.updated_at) or datetime.now(timezone.utc),
    )


def _apply_entity(model: RecurringRuleModel, entity: RecurringRule) -> None:
    model.id = entity.id
    model.name = entity.name
    model.amount = entity.amount
    model.currency = entity.currency
    model.account_id = entity.account_id
    model.category = entity.category or ""
    model.comment = entity.comment or ""
    model.type = (
        entity.type.value if isinstance(entity.type, TransactionType) else str(entity.type)
    )
    model.interval = (
        entity.interval.value
        if isinstance(entity.interval, RecurringInterval)
        else str(entity.interval)
    )
    model.interval_count = int(entity.interval_count or 1)
    model.next_run = entity.next_run
    model.paused = bool(entity.paused)
    model.skip_next = bool(entity.skip_next)
    model.auto_create = bool(entity.auto_create)
    model.last_created_at = ensure_utc(entity.last_created_at)
    model.created_at = ensure_utc(entity.created_at) or datetime.now(timezone.utc)
    model.updated_at = ensure_utc(entity.updated_at) or datetime.now(timezone.utc)


class SqlAlchemyRecurringRuleRepository(RecurringRuleRepository):
    """Recurring templates via SQLAlchemy sync session + ``asyncio.to_thread``."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def create(self, rule: RecurringRule) -> RecurringRule:
        if in_unit_of_work():
            return self._create_sync(rule)
        return await asyncio.to_thread(self._create_sync, rule)

    async def update(self, rule: RecurringRule) -> RecurringRule:
        if in_unit_of_work():
            return self._update_sync(rule)
        return await asyncio.to_thread(self._update_sync, rule)

    async def delete(self, rule_id: str) -> bool:
        if in_unit_of_work():
            return self._delete_sync(rule_id)
        return await asyncio.to_thread(self._delete_sync, rule_id)

    async def get_by_id(self, rule_id: str) -> Optional[RecurringRule]:
        if in_unit_of_work():
            return self._get_by_id_sync(rule_id)
        return await asyncio.to_thread(self._get_by_id_sync, rule_id)

    async def list(self, *, include_paused: bool = True) -> list[RecurringRule]:
        if in_unit_of_work():
            return self._list_sync(include_paused, None)
        return await asyncio.to_thread(self._list_sync, include_paused, None)

    async def list_due(self, as_of: date) -> list[RecurringRule]:
        if in_unit_of_work():
            return self._list_sync(False, as_of)
        return await asyncio.to_thread(self._list_sync, False, as_of)

    def _create_sync(self, entity: RecurringRule) -> RecurringRule:
        with session_scope(self._session_factory) as session:
            model = RecurringRuleModel()
            _apply_entity(model, entity)
            session.add(model)
            session.flush()
            return _to_entity(model)

    def _update_sync(self, entity: RecurringRule) -> RecurringRule:
        with session_scope(self._session_factory) as session:
            model = session.get(RecurringRuleModel, entity.id)
            if model is None:
                raise KeyError(f"Recurring rule not found: {entity.id}")
            _apply_entity(model, entity)
            session.flush()
            return _to_entity(model)

    def _delete_sync(self, rule_id: str) -> bool:
        with session_scope(self._session_factory) as session:
            model = session.get(RecurringRuleModel, rule_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def _get_by_id_sync(self, rule_id: str) -> Optional[RecurringRule]:
        with session_scope(self._session_factory) as session:
            model = session.get(RecurringRuleModel, rule_id)
            return _to_entity(model) if model else None

    def _list_sync(
        self, include_paused: bool, due_on: Optional[date]
    ) -> list[RecurringRule]:
        with session_scope(self._session_factory) as session:
            stmt = select(RecurringRuleModel).order_by(
                RecurringRuleModel.next_run.asc(),
                RecurringRuleModel.name.asc(),
            )
            if not include_paused:
                stmt = stmt.where(RecurringRuleModel.paused.is_(False))
            if due_on is not None:
                stmt = stmt.where(RecurringRuleModel.auto_create.is_(True))
                stmt = stmt.where(RecurringRuleModel.paused.is_(False))
                stmt = stmt.where(RecurringRuleModel.next_run <= due_on)
            return [_to_entity(row) for row in session.scalars(stmt).all()]
